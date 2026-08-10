"""Loading the corpus and the one piece of parsing every check shares.

The shared piece is *masking*. Nearly every false positive an ad-hoc validator
produces on this corpus comes from reading something that is not prose: a
number inside a fenced code block, a pipe inside an inline code span, a version
string inside a link target. `Document.masked` is the file with all of those
blanked to spaces — same length, same line count, same column offsets — so a
check can run a naive regex over it and get prose-only matches.
"""

from __future__ import annotations

import fnmatch
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

# Roles decide which checks see which files.
#   authority — findings/, the measured-number source of record
#   consumer  — documents that quote findings: research/, README, plan, skills
#   harness   — experiment code and committed results; searched, rarely checked
ROLE_AUTHORITY = "authority"
ROLE_CONSUMER = "consumer"
ROLE_HARNESS = "harness"
ROLE_OTHER = "other"


@dataclass
class Document:
    path: Path
    relpath: str
    role: str
    text: str
    lines: list[str] = field(default_factory=list)
    masked_lines: list[str] = field(default_factory=list)
    # 0-based line indexes that sit inside a fenced code block (fence rows included).
    fenced: set[int] = field(default_factory=set)

    @property
    def is_markdown(self) -> bool:
        return self.path.suffix.lower() in {".md", ".markdown"}

    def line(self, lineno: int) -> str:
        """1-based line access, for building violation messages."""
        if 1 <= lineno <= len(self.lines):
            return self.lines[lineno - 1]
        return ""


_FENCE_RE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")
_INLINE_CODE_RE = re.compile(r"(?<!`)(`+)(?!`)(.+?)(?<!`)\1(?!`)")
_LINK_TARGET_RE = re.compile(r"\]\(([^)]*)\)")
_AUTOLINK_RE = re.compile(r"<(https?://[^>]*)>")
_BARE_URL_RE = re.compile(r"https?://\S+")
_HTML_COMMENT_OPEN = re.compile(r"<!--")
_HTML_COMMENT_CLOSE = re.compile(r"-->")


def _blank(match: re.Match, group: int = 0) -> str:
    return " " * (match.end(group) - match.start(group))


def _mask_span(line: str, start: int, end: int) -> str:
    return line[:start] + " " * (end - start) + line[end:]


def mask_line(line: str) -> str:
    """Blank inline code spans, link targets and URLs, preserving offsets."""
    out = line
    # Inline code first: a link target inside backticks is already gone after this.
    for m in list(_INLINE_CODE_RE.finditer(out)):
        out = _mask_span(out, m.start(), m.end())
    for m in list(_AUTOLINK_RE.finditer(out)):
        out = _mask_span(out, m.start(), m.end())
    # Link targets, not link text: `[finding 004](path)` keeps "finding 004".
    for m in list(_LINK_TARGET_RE.finditer(out)):
        out = _mask_span(out, m.start(1), m.end(1))
    for m in list(_BARE_URL_RE.finditer(out)):
        out = _mask_span(out, m.start(), m.end())
    return out


def build_masked(lines: list[str]) -> tuple[list[str], set[int]]:
    masked: list[str] = []
    fenced: set[int] = set()
    fence: str | None = None
    in_comment = False
    for i, raw in enumerate(lines):
        m = _FENCE_RE.match(raw)
        if fence is None and m:
            fence = m.group(1)[0] * 3
            fenced.add(i)
            masked.append(" " * len(raw))
            continue
        if fence is not None:
            fenced.add(i)
            masked.append(" " * len(raw))
            if m and m.group(1)[0] * 3 == fence:
                fence = None
            continue

        line = raw
        if in_comment:
            close = _HTML_COMMENT_CLOSE.search(line)
            if close:
                line = _mask_span(line, 0, close.end())
                in_comment = False
            else:
                masked.append(" " * len(raw))
                continue
        while True:
            op = _HTML_COMMENT_OPEN.search(line)
            if not op:
                break
            close = _HTML_COMMENT_CLOSE.search(line, op.end())
            if close:
                line = _mask_span(line, op.start(), close.end())
            else:
                line = _mask_span(line, op.start(), len(line))
                in_comment = True
                break
        masked.append(mask_line(line))
    return masked, fenced


def split_row_spans(row: str) -> list[tuple[str, int, int]] | None:
    """`(text, start, end)` per cell, with offsets into `row` itself.

    Returns None when the line is not a table row. Respects `\\|` escapes and
    pipes inside inline code spans — the two things an earlier ad-hoc validator
    in this repository got wrong, producing a false positive on
    `` `<chat\\|image>` `` in research/08.

    `split_row` is this function with the offsets dropped. They are kept
    separate rather than duplicated because `gen_claims.py` has to write back
    into a cell it located, and a second cell-splitter that disagreed with this
    one about escaped pipes would edit the wrong column.
    """
    if "|" not in row:
        return None
    stripped = row.strip()
    if not stripped:
        return None
    lead = len(row) - len(row.lstrip())

    cells: list[tuple[str, int, int]] = []
    buf: list[str] = []
    start = 0
    i = 0
    tick_run = 0  # length of the backtick fence currently open, 0 when closed
    n = len(stripped)
    while i < n:
        ch = stripped[i]
        if ch == "\\" and i + 1 < n and stripped[i + 1] == "|":
            buf.append("\\|")
            i += 2
            continue
        if ch == "`":
            j = i
            while j < n and stripped[j] == "`":
                j += 1
            run = j - i
            if tick_run == 0:
                tick_run = run
            elif tick_run == run:
                tick_run = 0
            buf.append(stripped[i:j])
            i = j
            continue
        if ch == "|" and tick_run == 0:
            cells.append(("".join(buf), lead + start, lead + i))
            buf = []
            i += 1
            start = i
            continue
        buf.append(ch)
        i += 1
    cells.append(("".join(buf), lead + start, lead + n))

    # A leading and/or trailing pipe produces an empty edge cell; drop those.
    if cells and cells[0][0].strip() == "":
        cells = cells[1:]
    if cells and cells[-1][0].strip() == "":
        cells = cells[:-1]
    return cells


def split_row(row: str) -> list[str] | None:
    """Split one markdown table row into cells. See `split_row_spans`."""
    spans = split_row_spans(row)
    if spans is None:
        return None
    return [text for text, _, _ in spans]


_DELIM_CELL_RE = re.compile(r"^\s*:?-{1,}:?\s*$")


def is_delimiter_row(row: str) -> bool:
    cells = split_row(row)
    if not cells:
        return False
    return all(_DELIM_CELL_RE.match(c) for c in cells)


def looks_like_table_row(row: str) -> bool:
    stripped = row.strip()
    return stripped.startswith("|") and stripped.count("|") >= 2


_CODE_SPAN_RE = re.compile(r"`([^`]*)`")
_PARKED_RE = re.compile(r"\x00(\d+)\x00")
# An emphasis pair whose delimiters are not intraword. `_` opens only where the
# preceding character is not a word character and closes only where the
# following one is not, which is what leaves `cite_advisor` alone.
_EMPHASIS_UNDERSCORE_RE = re.compile(r"(?<!\w)(_{1,2})(?=\S)(.+?)(?<=\S)\1(?!\w)")

_SLUG_KEEP_RE = re.compile(r"[\w\s\-]", re.UNICODE)
#: Categories Python's `\w` admits and GitHub's word class does not.
_SLUG_DROP_CATEGORIES = frozenset({"No"})


def _slug_keeps(ch: str) -> bool:
    """One character's fate in an anchor, as GitHub's renderer decides it."""
    category = unicodedata.category(ch)
    if category in _SLUG_DROP_CATEGORIES:
        return False
    # Combining marks survive the renderer and are not word characters here.
    return category.startswith("M") or bool(_SLUG_KEEP_RE.match(ch))


def slugify(heading: str) -> str:
    r"""Reproduces GitHub's emitted heading `id` on every heading measured.

    ~~"GitHub's heading-anchor algorithm, close enough for link checking."~~
    ~~Measured on 2026-08-10 against ids fetched from GitHub's renderer, over
    the 2,371 headings the corpus walked that day.~~ **That set was the
    non-blockquoted headings only, and nothing said so — the filter is what hid
    a third population of 109 for two differentials running.** Re-measured on
    2026-08-10 at `7a60dd3` over **both** populations — the 2,425 headings
    anchored at `^#` and the 109 written `> ## Title` inside a blockquote,
    2,534 in all — this function agrees with the renderer on **all 2,534**.
    That is a dated count over a named set rather than a live ratio: the walked
    set grows whenever the corpus does. The retired sentence is retired for its
    second clause. *Close enough* is the phrase that licensed nobody checking,
    and while it stood this function invented anchors no rendered page carried,
    `link-anchor` computed every target with the same defect, and two committed
    links were written to match the invention and passed a green gate.

    GitHub renders the heading to HTML and slugs the *text content*, so a
    character's markup role and its literal role have different fates. `*` and
    `~` need no distinction — consumed as markup they vanish, and left literal
    they are dropped anyway for not being word characters. **`_` is the one that
    does**, because `_` *is* a word character: consumed as emphasis it vanishes,
    and left literal inside an identifier it survives into the anchor.
    `#### _Note_: Multiple entry points` renders
    `id="user-content-note-multiple-entry-points"` — emphasis consumed — while
    this repository's own `### OD-26 — ... terminated.denied_operation ...`
    renders `...terminateddenied_operation...`, dropping the `.` and keeping the
    `_` in one token. See tools/README.md for the differential.

    **Three defects were measured and all three are repaired.** Each was
    declined once for a blast radius nobody had counted; counted, the three
    together move **5** of the 2,425 already-enumerated slugs, and those 5 are
    the 5 that were wrong. No live link pointed at any of them.

      * **Trimming happens before the character drop, not after.** GitHub
        trims, *then* drops the characters outside its word class, *then*
        converts every remaining space to `-`. Dropping first and trimming
        after loses a hyphen wherever a dropped character sits at either end
        behind a space. Blast radius over the enumerated population: **1**, the
        trailing `\u2605` in `research/12-examples-as-corpus.md`. The same
        defect at the *leading* edge is the whole of the pictograph family —
        `\u26a0\ufe0f`, `\u2705`, `\u26d4` opening a blockquoted banner heading — so the
        one-site fix and the 40-site fix are the same fix.
      * **Category `No` is dropped.** `\u2460` and `\u2461` are Unicode `No`, which
        Python's `\w` matches because `str.isalnum()` is true for them and
        GitHub's word class does not. Blast radius: **4**.
      * **Combining marks are kept.** A U+FE0F after a pictograph is not a word
        character to Python and is not dropped by the renderer, so the renderer
        emits it into the `id` and this implementation was deleting it. Blast
        radius over the enumerated population: **0**; it reaches 30 blockquoted
        headings and nothing else.

    Category `So` needs no entry: `\u2605` and the pictographs are already outside
    `\w`, so the existing class drops them without help.

    Inline code is parked before the emphasis pass so a `_` inside a code span
    can never pair with one outside it.
    """
    text = heading.strip()
    text = re.sub(r"^#+\s*", "", text)

    parked: list[str] = []

    def _park(m: re.Match) -> str:
        parked.append(m.group(1))
        return f"\x00{len(parked) - 1}\x00"

    text = _CODE_SPAN_RE.sub(_park, text)
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", text)  # links -> text
    text = _EMPHASIS_UNDERSCORE_RE.sub(r"\2", text)
    text = text.replace("*", "").replace("~", "")
    text = _PARKED_RE.sub(lambda m: parked[int(m.group(1))], text)
    text = text.lower().strip()
    text = "".join(ch for ch in text if _slug_keeps(ch))
    return text.replace(" ", "-")


@dataclass
class Corpus:
    root: Path
    documents: list[Document]

    def by_role(self, *roles: str) -> list[Document]:
        wanted = set(roles)
        return [d for d in self.documents if d.role in wanted]

    def markdown(self, *roles: str) -> list[Document]:
        docs = self.by_role(*roles) if roles else self.documents
        return [d for d in docs if d.is_markdown]

    def get(self, relpath: str) -> Document | None:
        for d in self.documents:
            if d.relpath == relpath:
                return d
        return None


def _match_any(relpath: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(relpath, p) for p in patterns)


def load(root: Path, config: dict, *, only: list[str] | None = None) -> Corpus:
    """Walk the configured roots and classify every file into a role.

    `only` restricts the walk to specific paths — used by --path so the fixture
    tree can be checked in isolation.
    """
    include = config["include"]
    exclude = config["exclude"]
    authority = config["authority"]
    consumer = config["consumer"]
    harness = config["harness"]

    candidates: list[Path] = []
    walk_roots = [root / p for p in (only or include)]
    for base in walk_roots:
        if base.is_file():
            candidates.append(base)
            continue
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if path.is_file():
                candidates.append(path)

    documents: list[Document] = []
    seen: set[Path] = set()
    for path in candidates:
        if path in seen:
            continue
        seen.add(path)
        try:
            rel = path.relative_to(root).as_posix()
        except ValueError:
            continue
        if _match_any(rel, exclude):
            continue
        if path.suffix.lower() not in config["extensions"]:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue

        if _match_any(rel, authority):
            role = ROLE_AUTHORITY
        elif _match_any(rel, consumer):
            role = ROLE_CONSUMER
        elif _match_any(rel, harness):
            role = ROLE_HARNESS
        else:
            role = ROLE_OTHER

        lines = text.splitlines()
        masked, fenced = build_masked(lines)
        documents.append(
            Document(
                path=path,
                relpath=rel,
                role=role,
                text=text,
                lines=lines,
                masked_lines=masked,
                fenced=fenced,
            )
        )
    return Corpus(root=root, documents=documents)
