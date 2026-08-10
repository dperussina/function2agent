"""link-target, link-anchor, link-label — relative links resolve, and say what they point at.

Three checks share one link parse.

  link-target   A relative link resolves to a file that exists.
  link-anchor   A `#fragment` resolves to a heading in the target file. Slugs
                follow GitHub's algorithm, including its `-1`, `-2` suffixes
                for repeated headings.
  link-label    The link *text* agrees with the link *target*. This is the one
                worth having: `[finding 010](.../011-reachability...)` is a
                correct link with a wrong label, it survives every existence
                check ever written, and a reader following the prose is sent to
                the wrong document while the link works perfectly.

External URLs are out of scope by design — an earlier checker handled network
liveness and this one does not rebuild it.
"""

from __future__ import annotations

import posixpath
import re
from urllib.parse import unquote

from ..corpus import Corpus, slugify
from ..registry import check
from ..report import ERROR, WARNING, Violation

_LINK = re.compile(r"(?<!!)\[((?:[^\[\]]|\[[^\]]*\])*)\]\(\s*([^)\s]+)(?:\s+\"[^\"]*\")?\s*\)")
_HTML_ANCHOR = re.compile(r"<a\s[^>]*(?:name|id)\s*=\s*[\"']([^\"']+)[\"']", re.IGNORECASE)
_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")

_SKIP_SCHEMES = ("http://", "https://", "mailto:", "tel:", "ftp:", "data:")


def _anchors_for(doc) -> set[str]:
    seen: dict[str, int] = {}
    out: set[str] = set()
    for i, line in enumerate(doc.lines):
        if i in doc.fenced:
            continue
        m = _HEADING.match(line)
        if m:
            slug = slugify(m.group(2))
            if not slug:
                continue
            n = seen.get(slug, 0)
            out.add(slug if n == 0 else f"{slug}-{n}")
            seen[slug] = n + 1
        for am in _HTML_ANCHOR.finditer(line):
            out.add(am.group(1))
    return out


def _iter_links(doc):
    for lineno, masked in enumerate(doc.masked_lines, start=1):
        raw = doc.lines[lineno - 1]
        if "](" not in raw:
            continue
        # Link *targets* are masked out, so match on the raw line but only
        # where the masked line still shows the opening bracket — that keeps
        # links inside fenced blocks and inline code out.
        if not masked.strip():
            continue
        for m in _LINK.finditer(raw):
            if masked[m.start() : m.start() + 1] != "[":
                continue
            yield lineno, m


@check("link-target", "Relative links resolve to a file that exists.")
def link_target(corpus: Corpus, ctx: dict) -> list[Violation]:
    out: list[Violation] = []
    root = corpus.root
    for doc in corpus.markdown():
        for lineno, m in _iter_links(doc):
            target = m.group(2)
            if target.startswith(_SKIP_SCHEMES) or target.startswith("#"):
                continue
            path_part = unquote(target.split("#", 1)[0])
            if not path_part:
                continue
            resolved = (doc.path.parent / path_part).resolve()
            if resolved.exists():
                continue
            try:
                shown = resolved.relative_to(root).as_posix()
            except ValueError:
                shown = str(resolved)
            out.append(
                Violation(
                    check="link-target",
                    severity=ERROR,
                    path=doc.relpath,
                    line=lineno,
                    col=m.start() + 1,
                    found=f"[{_short(m.group(1))}]({target})",
                    expected=f"an existing file at {shown}",
                    hint="relative to the linking file's directory",
                )
            )
    return out


@check("link-anchor", "A #fragment resolves to a heading in the target file.")
def link_anchor(corpus: Corpus, ctx: dict) -> list[Violation]:
    out: list[Violation] = []
    anchor_cache: dict[str, set[str]] = {}

    def anchors(d) -> set[str]:
        if d.relpath not in anchor_cache:
            anchor_cache[d.relpath] = _anchors_for(d)
        return anchor_cache[d.relpath]

    for doc in corpus.markdown():
        for lineno, m in _iter_links(doc):
            target = m.group(2)
            if target.startswith(_SKIP_SCHEMES) or "#" not in target:
                continue
            path_part, frag = target.split("#", 1)
            frag = unquote(frag)
            if not frag:
                continue
            if path_part:
                resolved = (doc.path.parent / unquote(path_part)).resolve()
                other = next((d for d in corpus.documents if d.path.resolve() == resolved), None)
                if other is None:
                    continue  # link-target already reports, or it is out of scope
                available = anchors(other)
                where = other.relpath
            else:
                available = anchors(doc)
                where = doc.relpath
            if frag in available:
                continue
            near = sorted(a for a in available if _close(a, frag))[:3]
            out.append(
                Violation(
                    check="link-anchor",
                    severity=ERROR,
                    path=doc.relpath,
                    line=lineno,
                    col=m.start() + 1,
                    found=f"#{frag} in [{_short(m.group(1))}]({target})",
                    expected=f"a heading in {where} whose slug is {frag}",
                    hint=("did you mean: " + ", ".join("#" + a for a in near)) if near else "",
                )
            )
    return out


_FINDING_IN_TEXT = re.compile(r"\bfinding\s+(\d{1,3})\b", re.IGNORECASE)
_NUMERIC_TEXT = re.compile(r"^`?(\d{2})`?$")
_FILENAME_IN_TEXT = re.compile(r"`([\w./-]+\.(?:md|py|sh|json))`")


@check("link-label", "Link text agrees with the file the link points at.")
def link_label(corpus: Corpus, ctx: dict) -> list[Violation]:
    out: list[Violation] = []
    for doc in corpus.markdown():
        for lineno, m in _iter_links(doc):
            text, target = m.group(1), m.group(2)
            if target.startswith(_SKIP_SCHEMES):
                continue
            path_part = unquote(target.split("#", 1)[0])
            if not path_part:
                continue

            fm = _FINDING_IN_TEXT.search(text)
            if fm and "findings/" in path_part:
                want = f"findings/{int(fm.group(1)):03d}-"
                if want not in path_part:
                    out.append(
                        _mismatch(doc, lineno, m, text, target, f"a path containing {want}")
                    )
                    continue

            nm = _NUMERIC_TEXT.match(text.strip())
            if nm and path_part.endswith(".md"):
                base = path_part.rsplit("/", 1)[-1]
                if not base.startswith(nm.group(1) + "-"):
                    out.append(
                        _mismatch(
                            doc, lineno, m, text, target,
                            f"a filename beginning {nm.group(1)}-",
                        )
                    )
                    continue

            fnm = _FILENAME_IN_TEXT.fullmatch(text.strip())
            if fnm:
                named = fnm.group(1)
                # Against the *resolved* target, not the authored string. A
                # repo-root-relative label beside a document-relative link
                # names the same file, and comparing the unresolved string read
                # that agreement as a mismatch. Resolved with posixpath rather
                # than Path.resolve so the verdict does not depend on the
                # filesystem — the target may not exist, which is link-target's
                # finding and not this one's, and it may be a symlink, whose
                # real path is not what the label is claiming.
                where = posixpath.normpath(
                    posixpath.join(posixpath.dirname(doc.relpath), path_part)
                )
                if not where.endswith(named.lstrip("./")):
                    out.append(
                        _mismatch(doc, lineno, m, text, target, f"a path ending {named}")
                    )
    return out


def _mismatch(doc, lineno, m, text, target, expected) -> Violation:
    return Violation(
        check="link-label",
        severity=WARNING,
        path=doc.relpath,
        line=lineno,
        col=m.start() + 1,
        found=f"[{_short(text)}]({target})",
        expected=expected,
        hint="the link resolves; the label names a different document",
    )


def _short(text: str, width: int = 48) -> str:
    t = " ".join(text.split())
    return t if len(t) <= width else t[: width - 1] + "…"


def _close(a: str, b: str) -> bool:
    return a.startswith(b[:8]) or b.startswith(a[:8]) or a.replace("-", "") == b.replace("-", "")
