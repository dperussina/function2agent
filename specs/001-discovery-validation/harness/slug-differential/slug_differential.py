#!/usr/bin/env python3
"""The slug differential — `corpuscheck.corpus.slugify` against GitHub's renderer.

`slugify` computes the heading anchor that `link-anchor` resolves every
`#fragment` against. Until it was measured it was described from GitHub's
documented algorithm, and while it was only described it invented anchors no
rendered page carried and two committed links were written to match the
invention. This is the instrument that measures it instead: for every markdown
document in the corpus, the headings are enumerated locally and the anchors
GitHub actually emitted are read off the rendered page, and the two are compared
position by position.

Posture, stated because a harness that reaches the network owes it
--------------------------------------------------------------------
* **Network: yes, outbound HTTPS to `api.github.com` only, `GET` only.** This is
  the whole point — the renderer is the oracle and it is not vendorable. It is
  why this cannot live in `tools/`, which is declared standard-library-only and
  no network at the top of `tools/README.md`.
* **Privilege: none.** Runs at any euid; needs no root, no container, no kernel
  facility. It writes nothing anywhere: not into the repository, not into
  `/tmp`, not into `examples/`.
* **Model spend: $0.00.** No model is called.
* **Credentials: a GitHub token is read but never printed, logged or returned.**
  Only its source is named. A token is optional for a small run and required for
  a whole-corpus one: unauthenticated `api.github.com` allows 60 requests an
  hour and the corpus is well over a hundred documents.

The endpoint, and the detail a rebuild has already got wrong
------------------------------------------------------------
The ground truth comes from the **contents endpoint**::

    GET https://api.github.com/repos/<owner>/<repo>/contents/<path>?ref=<ref>
    Accept: application/vnd.github.html+json

That `Accept` is what makes it return rendered HTML rather than JSON metadata.
Two neighbouring endpoints are the wrong ones and fail differently: the plain
`Accept: application/vnd.github+json` returns base64 source with no anchors at
all, and `POST /markdown` renders GFM but emits bare ``<h2 dir="auto">`` with
**no `id` and no anchor element** — so a rebuild that reaches for `/markdown`
measures nothing and cannot tell.

**The `id` is not on the heading element.** The contents endpoint emits::

    <h2 dir="auto">Title<a id="user-content-title" class="anchor" href="#title">…</a></h2>

The anchor is an ``<a class="anchor">`` **beside the heading text**, and the
``<hN>`` element itself carries no `id`. A rebuild that read `id` off the `<hN>`
returned **zero ids for every document**, and because zero ids is also a wrong
*count*, it reported a heading-count mismatch on all 136 documents rather than an
error — a reading whose plain meaning is "the corpus moved under the harness",
pointing a reader at the corpus instead of at the harness. That is the failure
this file is written against, and it is why `_anchor_count_or_die` runs before
any count is compared and why `--self-test` drives the misbuild deliberately.

Each anchor carries its slug twice — `id` with a `user-content-` prefix that
GitHub adds for DOM-collision reasons and `href` as a bare `#fragment`. Both are
read and a disagreement between them is an error rather than something averaged
away.

Two enumeration details that are load-bearing
----------------------------------------------
* **Blockquoted headings count.** `crossrefs._anchors_for` matches `^(#{1,6})\\s+`
  anchored at the start of the line, so a heading written ``> ## Title`` never
  enters the anchor set the checker builds. GitHub strips the blockquote prefix
  and emits a real heading with an anchor for it. A differential handed only the
  `^#` subset is blind to that population, and two consecutive differentials were
  — the excluded set held 109 headings. This walker strips the prefix.
* **Duplicate suffixes are numbered over the whole document**, across both
  populations together, because that is what the renderer does.

Why the text is read from git and not from the working tree
-----------------------------------------------------------
The rendered page is pinned to a commit, so the source text must be too.
Comparing a newer working tree against an older rendered page produces a heading
count mismatch that looks exactly like a parser defect — it happened, and it
cost a reader the conclusion that the enumerator was broken. Every document's
text here comes from ``git show <ref>:<path>``, so both sides are the same
revision by construction and a dirty tree cannot perturb the result.

What it cannot do
------------------
It cannot certify `slugify` against a corpus it did not walk, and it cannot be
replaced by a committed table of ids: a recorded ground truth stops being ground
truth the moment the renderer changes, and the renderer is not ours. There is
deliberately no `results/` directory here for that reason. The figure it produced
is dated to a commit at its two reading sites — `slugify`'s docstring and
`tools/README.md`'s `link-anchor` row — rather than carried here as a live total.

Usage
-----
::

    export PATH="$PWD/.venv/bin:$PATH"
    python specs/001-discovery-validation/harness/slug-differential/slug_differential.py --self-test
    python specs/001-discovery-validation/harness/slug-differential/slug_differential.py
    python specs/001-discovery-validation/harness/slug-differential/slug_differential.py --path tools

Exits non-zero on any divergence, any count mismatch, any zero-anchor document,
any `id`/`href` disagreement, and on a ref the renderer cannot resolve.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

#: Repository root, derived from this file's own location so that no absolute
#: path into anybody's filesystem is committed and no default points at one.
#: Stated as a refusal rather than left to raise `IndexError`, because the
#: committed depth is four directories and a copy taken somewhere shallower
#: otherwise dies in a traceback that names pathlib instead of the cause.
_HERE = Path(__file__).resolve()
if len(_HERE.parents) < 5:
    raise SystemExit(
        f"{_HERE} sits {len(_HERE.parents) - 1} directories below its filesystem "
        "root, and this file derives the repository root four above itself. Pass "
        "--root, or run it from where it is committed."
    )
_DEFAULT_ROOT = _HERE.parents[4]

#: `slugify` is the subject of the measurement, so it is imported from the tree
#: under test rather than reimplemented here. A second copy would drift, and a
#: differential against a copy of the thing measures nothing.
sys.path.insert(0, str(_DEFAULT_ROOT / "tools"))

from corpuscheck.corpus import build_masked, load, slugify  # noqa: E402

_ACCEPT = "application/vnd.github.html+json"
_API = "https://api.github.com"

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
#: A blockquote prefix, which GitHub strips before it looks for a heading.
_BLOCKQUOTE_RE = re.compile(r"^(?: {0,3}>)+ ?")


# ---------------------------------------------------------------------------
# Reading the renderer's answer.


class AnchorIds(HTMLParser):
    """Heading anchors in document order, `user-content-` prefix removed.

    Reads ``<a class="anchor">`` elements, which is where the contents endpoint
    puts the `id`. See this module's docstring: the `<hN>` element carries none,
    and a parser that looks there finds nothing and says so as a count.
    """

    name = "sibling-anchor (correct)"

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.ids: list[str] = []
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        d = dict(attrs)
        if "anchor" not in (d.get("class") or "").split():
            return
        value, href = d.get("id"), d.get("href") or ""
        if not value:
            return
        prefix = "user-content-"
        self.ids.append(value[len(prefix):] if value.startswith(prefix) else value)
        self.hrefs.append(href[1:] if href.startswith("#") else href)


class HeadingElementIds(AnchorIds):
    """The known misbuild, kept so `--self-test` can drive it rather than mock it.

    Reads `id` off the `<hN>` element, where a rebuild placed it twice. The
    contents endpoint never puts one there, so this finds zero on real input.
    """

    name = "heading-element (the known misbuild)"

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag not in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            return
        value = dict(attrs).get("id")
        if not value:
            return
        prefix = "user-content-"
        self.ids.append(value[len(prefix):] if value.startswith(prefix) else value)
        self.hrefs.append(self.ids[-1])


class ZeroAnchors(RuntimeError):
    """Raised where a wrong count would otherwise have been reported."""


def _anchor_count_or_die(parser: AnchorIds, relpath: str, walked: int) -> list[str]:
    """The loud floor, and it runs before any count is compared.

    Zero anchors from a document that has headings is an extraction failure, and
    every way extraction can break produces it. Reported as a count it reads as
    the corpus having moved; reported here it reads as what it is.
    """
    if parser.ids:
        return parser.ids
    raise ZeroAnchors(
        f"{relpath}: the rendered page yielded ZERO heading anchors while the "
        f"source has {walked} heading(s). This is an extraction failure, not a "
        f"corpus difference. Under `{parser.name}` the likely cause is the "
        f"parser looking for `id` on the <hN> element; the contents endpoint "
        f"puts it on a sibling <a class=\"anchor\">. Refusing to report a count."
    )


# ---------------------------------------------------------------------------
# Reading our own answer, at the same revision.


def git_text(root: Path, ref: str, relpath: str) -> str:
    """The document as of `ref`, so both sides of the comparison are one commit."""
    out = subprocess.run(
        ["git", "-C", str(root), "show", f"{ref}:{relpath}"],
        capture_output=True,
        check=True,
    )
    return out.stdout.decode("utf-8", "replace")


def walked_headings(text: str, *, blockquotes: bool = True) -> list[tuple[int, str, str]]:
    """Every heading the renderer emits an anchor for, in document order.

    Returns `(lineno, heading text, expected slug)`. `blockquotes=False`
    reproduces `crossrefs._anchors_for` exactly, which is the subset the checker
    enumerates and the subset two differentials were confined to without saying
    so.
    """
    lines = text.splitlines()
    _, fenced = build_masked(lines)

    seen: dict[str, int] = {}
    out: list[tuple[int, str, str]] = []
    for i, line in enumerate(lines):
        if i in fenced:
            continue
        candidate = line
        if blockquotes:
            candidate = _BLOCKQUOTE_RE.sub("", line)
            candidate = re.sub(r"^ {1,3}(?=#)", "", candidate)
        m = _HEADING_RE.match(candidate)
        if not m:
            continue
        slug = slugify(m.group(2))
        if not slug:
            continue
        n = seen.get(slug, 0)
        out.append((i + 1, m.group(2), slug if n == 0 else f"{slug}-{n}"))
        seen[slug] = n + 1
    return out


# ---------------------------------------------------------------------------
# Fetching.


def _token() -> tuple[str | None, str]:
    """A token and the name of where it came from. The value is never printed."""
    for var in ("GITHUB_TOKEN", "GH_TOKEN"):
        if os.environ.get(var):
            return os.environ[var], f"${var}"
    try:
        out = subprocess.run(
            ["gh", "auth", "token"], capture_output=True, text=True, check=True
        )
        value = out.stdout.strip()
        if value:
            return value, "`gh auth token`"
    except (OSError, subprocess.CalledProcessError):
        pass
    return None, "none — unauthenticated, 60 requests an hour"


def fetch_html(owner: str, repo: str, relpath: str, ref: str, token: str | None) -> str:
    url = f"{_API}/repos/{owner}/{repo}/contents/{relpath}?ref={ref}"
    req = urllib.request.Request(url)
    req.add_header("Accept", _ACCEPT)
    req.add_header("User-Agent", "f2a-slug-differential")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=45) as response:
        return response.read().decode("utf-8", "replace")


def _origin_slug(root: Path) -> tuple[str, str]:
    url = subprocess.run(
        ["git", "-C", str(root), "remote", "get-url", "origin"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    tail = url.rsplit(":", 1)[-1] if url.startswith("git@") else url.split("github.com/")[-1]
    owner, _, repo = tail.removesuffix(".git").partition("/")
    if not owner or not repo:
        raise SystemExit(f"could not read owner/repo out of origin url {url!r}")
    return owner, repo


# ---------------------------------------------------------------------------
# The offline self-test, which plants the misbuild.

#: A rendered heading in the shape the contents endpoint returns it. This is a
#: *parser* fixture and not a ground truth: it certifies which element position
#: each extractor reads, and it certifies nothing about `slugify`. A recorded
#: corpus of real ids would be the self-certifying artifact this tree refuses.
_FIXTURE = (
    '<h2 dir="auto">A heading'
    '<a id="user-content-a-heading" class="anchor" aria-hidden="true" href="#a-heading">'
    "</a></h2>\n"
    '<h3 dir="auto">Another<a id="user-content-another" class="anchor" href="#another">'
    "</a></h3>\n"
)


def self_test() -> int:
    print("the zero-anchor floor, planted\n")
    print(f"fixture: {len(_FIXTURE.splitlines())} rendered headings, anchors on the sibling <a>\n")

    failures: list[str] = []

    correct = AnchorIds()
    correct.feed(_FIXTURE)
    print(f"  extractor : {correct.name}")
    print(f"  ids       : {correct.ids}")
    try:
        _anchor_count_or_die(correct, "fixture", len(correct.ids))
        print("  floor     : passes, as it must — anchors were found\n")
    except ZeroAnchors as exc:
        failures.append(f"the correct extractor tripped the floor: {exc}")
        print(f"  floor     : UNEXPECTEDLY RAISED — {exc}\n")

    misbuilt = HeadingElementIds()
    misbuilt.feed(_FIXTURE)
    print(f"  extractor : {misbuilt.name}")
    print(f"  ids       : {misbuilt.ids}")
    if misbuilt.ids:
        failures.append(
            "the misbuild found ids in the fixture, so the fixture no longer "
            "carries the sibling-anchor shape this test is about"
        )
    try:
        _anchor_count_or_die(misbuilt, "fixture", 2)
        failures.append(
            "THE FLOOR DID NOT FIRE on zero anchors. This is the vacuity the "
            "harness exists to refuse: the run would have reported a heading "
            "count mismatch of 2 against 0 and exited as though it had measured."
        )
        print("  floor     : DID NOT FIRE — the harness is vacuous\n")
    except ZeroAnchors as exc:
        print("  floor     : fires, loudly, before any count is compared")
        print(f"  error     : {exc}\n")

    if failures:
        for f in failures:
            print(f"FAIL {f}")
        return 1
    print("both directions hold: anchors found is a pass, zero anchors is an error.")
    return 0


# ---------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--root",
        type=Path,
        default=_DEFAULT_ROOT,
        help="repository root; defaults to the tree this file is committed in",
    )
    ap.add_argument(
        "--ref",
        default=None,
        help="commit the renderer is asked for; defaults to HEAD. Must be pushed.",
    )
    ap.add_argument(
        "--path",
        action="append",
        default=None,
        help="restrict to documents under this prefix. Repeatable.",
    )
    ap.add_argument(
        "--no-blockquotes",
        action="store_true",
        help="walk only `^#` headings, reproducing the scope of the two "
        "differentials that missed the blockquoted population",
    )
    ap.add_argument(
        "--self-test",
        action="store_true",
        help="offline; plant the known misbuild and show the floor firing",
    )
    args = ap.parse_args()

    if args.self_test:
        return self_test()

    root: Path = args.root.resolve()
    if not (root / "tools/corpuscheck/config.json").is_file():
        raise SystemExit(f"{root} does not look like the repository root")

    ref = args.ref or subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    owner, repo = _origin_slug(root)
    token, token_source = _token()

    config = json.loads((root / "tools/corpuscheck/config.json").read_text())
    corpus = load(root, config)
    docs = sorted(
        (d for d in corpus.documents if d.is_markdown), key=lambda d: d.relpath
    )
    if args.path:
        docs = [d for d in docs if any(d.relpath.startswith(p) for p in args.path)]
    if not docs:
        raise SystemExit("no markdown documents selected; refusing to report a total of zero")

    print(f"slug differential — {owner}/{repo} at {ref[:7]}")
    print(f"  endpoint    : GET {_API}/repos/{owner}/{repo}/contents/<path>?ref={ref[:7]}")
    print(f"  accept      : {_ACCEPT}")
    print(f"  auth        : {token_source}")
    print(f"  source text : git show {ref[:7]}:<path> — not the working tree")
    print(f"  documents   : {len(docs)}")
    print(f"  population  : {'^# only' if args.no_blockquotes else '^# and blockquoted'}\n")

    compared = agreeing = 0
    walked_anchored = walked_blockquoted = 0
    errors: list[str] = []
    diverged: list[tuple[str, int, str, str, str]] = []

    for d in docs:
        try:
            text = git_text(root, ref, d.relpath)
        except subprocess.CalledProcessError:
            errors.append(
                f"{d.relpath}: not present at {ref[:7]}. The working tree and the "
                f"ref disagree about which documents exist; pick a ref that has it."
            )
            continue

        headings = walked_headings(text, blockquotes=not args.no_blockquotes)
        if not headings:
            continue
        anchored = walked_headings(text, blockquotes=False)
        walked_anchored += len(anchored)
        walked_blockquoted += len(headings) - len(anchored)

        try:
            html = fetch_html(owner, repo, d.relpath, ref, token)
        except urllib.error.HTTPError as exc:
            detail = "ref not pushed, or path absent at that ref" if exc.code == 404 else ""
            errors.append(f"{d.relpath}: HTTP {exc.code} {exc.reason}. {detail}".rstrip())
            continue
        except (urllib.error.URLError, TimeoutError) as exc:
            errors.append(f"{d.relpath}: unreachable — {exc}")
            continue

        parser = AnchorIds()
        parser.feed(html)
        try:
            truth = _anchor_count_or_die(parser, d.relpath, len(headings))
        except ZeroAnchors as exc:
            errors.append(str(exc))
            continue

        if parser.ids != parser.hrefs:
            errors.append(
                f"{d.relpath}: the anchors' `id` and `href` disagree, so the two "
                f"readings of the same slug are not one value."
            )
            continue
        if len(truth) != len(headings):
            errors.append(
                f"{d.relpath}: heading count mismatch — walked {len(headings)}, "
                f"rendered {len(truth)}. Both sides are at {ref[:7]}, so this is "
                f"an enumeration difference and not corpus drift."
            )
            continue

        for (lineno, heading_text, ours), theirs in zip(headings, truth):
            compared += 1
            if ours == theirs:
                agreeing += 1
            else:
                diverged.append((d.relpath, lineno, heading_text, ours, theirs))
        time.sleep(0.05)

    if compared == 0:
        print("compared 0 headings. Nothing was measured; this is not a pass.")
        for message in errors:
            print(f"  ERROR {message}")
        return 1

    print(f"compared : {compared}   ({walked_anchored} anchored at ^#, {walked_blockquoted} blockquoted)")
    print(f"agreeing : {agreeing}")
    print(f"diverged : {len(diverged)}")

    for relpath, lineno, heading_text, ours, theirs in diverged:
        print(f"\n  {relpath}:{lineno}")
        print(f"    heading : {heading_text!r}")
        print(f"    slugify : {ours!r}")
        print(f"    github  : {theirs!r}")

    if errors:
        print(f"\nerrors : {len(errors)}")
        for message in errors:
            print(f"  {message}")

    return 1 if (diverged or errors) else 0


if __name__ == "__main__":
    raise SystemExit(main())
