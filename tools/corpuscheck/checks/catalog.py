"""catalog-line-count — an index that states a document's length must be right.

A failure class nobody had named, and the one with the widest blast radius per
unit of effort. `research/README.md` carries a document catalog with a `Lines`
column. Nothing regenerates it. Every edit to any research document makes it
wrong, and the drift is invisible because the number lives in a different file
from the change — no reviewer of a research-document edit ever sees the row
that just went stale.

The check is generic rather than hard-coded to that one table: any markdown
table with a column headed `Lines` (or `LOC`, or `Length`) whose rows begin
with a relative link is checked against the real line count of the linked file.
Add such a column to any index anywhere in the corpus and it starts being
enforced automatically.

**Two shapes, because the corpus has two catalogs and only one of them uses a
column.** `.cursor/skills/README.md` is a roster of the same kind — an index
whose rows state how long each skill is — but it writes the count inline, as
``[`agent-tool-design`](agent-tool-design/SKILL.md) (185 lines)``. The column
scanner cannot see that, so the skills catalog drifted silently for exactly as
long as the check had existed, which is the failure this module is named after
happening inside the module's own blind spot. The inline scanner below closes
it and is equally generic: any link followed by `(N lines)` is checked.

**A `~` prefix buys no extra tolerance, and that is deliberate.** The roster
wrote `(~290 lines)` against a 303-line file. An approximation that is allowed
to drift is precisely the thing being guarded against, and writing the exact
number costs nothing, so `~290` is held to the same tolerance as `290` — the
hedge is accepted in the text and ignored in the arithmetic.

Severity is warning, not error, because a stale line count misleads a reader
about how long a document is and nothing more; it does not misstate a
measurement or break a reference.

**Amended 2026-08-03 — `tools/gen_claims.py` now writes these counts, and this
check is retained as the trigger rather than retired.** The generator is not
invoked automatically, so the window between "someone edited a `SKILL.md`" and
"someone ran the generator" is real and this rule is the only thing that
notices it. What changed is what the finding means: it now says *run the
generator*, not *retype the number*, and the hint says so.

**~~`TOLERANCE = 2`~~ `TOLERANCE = 0`, same date, and the slack was not
harmless.** The two-line allowance was written for a hand-maintained catalog,
where an index update and a document edit could legitimately race. A generated
claim has no such window — the fix is a command, not a transcription. The
allowance was also concealing a live defect at the moment it was removed:
`research/README.md` listed `08-auth-identity-and-secrets.md` at **804** lines
against an actual **806**, a drift of exactly the tolerance, so the check read
clean on a claim that was wrong. A safeguard that cannot fire on the defect it
is named after reads exactly like one that has been satisfied. Run
`check_corpus.py --report-only` while a document is mid-edit.
"""

from __future__ import annotations

import re
from urllib.parse import unquote

from ..corpus import Corpus, is_delimiter_row, looks_like_table_row, split_row
from ..registry import check
from ..report import WARNING, Violation

_LINK_IN_CELL = re.compile(r"\[[^\]]*\]\(\s*([^)\s#]+)")
_INT = re.compile(r"^[\s*`]*([\d,]+)[\s*`]*$")
_COUNT_HEADER = re.compile(r"^[\s*`]*(lines|loc|length|line count)[\s*`]*$", re.IGNORECASE)

#: A markdown link immediately followed by a parenthesised line count:
#: ``[`skill`](skill/SKILL.md) (185 lines)``, or the hedged `(~185 lines)`.
#: The unit word is required, which is what keeps this off `[x](y) (3 files)`
#: and every other parenthetical that happens to follow a link.
_INLINE_COUNT = re.compile(
    r"\]\(\s*([^)\s#]+?)\s*\)\s*\(\s*(~?)\s*([\d,]+)\s+lines?\s*\)"
)

#: Exact, since `gen_claims.py` writes these and a generated number is never
#: approximately right. See the amendment note in the module docstring for why
#: the previous two-line allowance was removed.
TOLERANCE = 0


@check(
    "catalog-line-count",
    "A stated line count — `Lines` column or inline `(N lines)` — matches the linked file.",
)
def run(corpus: Corpus, ctx: dict) -> list[Violation]:
    out: list[Violation] = []
    for doc in corpus.markdown():
        out.extend(_scan(doc, corpus))
        out.extend(_scan_inline(doc, corpus))
    return out


def _count_lines(target) -> int | None:
    try:
        return len(target.read_text(encoding="utf-8").splitlines())
    except (OSError, UnicodeDecodeError):
        return None


def _relative(target, root) -> str:
    """`target` under `root`, tolerating a root that is not resolved.

    `target` has been through `.resolve()`, so a symlinked root — `/var` on
    macOS, a `--root` passed as a relative path — makes a bare `relative_to`
    raise. Crashing the run while building a label is worse than a long label.
    """
    for base in (root, root.resolve()):
        try:
            return target.relative_to(base).as_posix()
        except ValueError:
            continue
    return target.as_posix()


def _violation(doc, corpus, target, lineno: int, claimed: int, actual: int) -> Violation:
    rel = _relative(target, corpus.root)
    return Violation(
        check="catalog-line-count",
        severity=WARNING,
        path=doc.relpath,
        line=lineno,
        found=f"{rel} listed at {claimed} lines",
        expected=f"{actual} lines",
        hint=f"drift of {actual - claimed:+d}; "
        "run `python3 tools/gen_claims.py` — this count is generated, not transcribed",
    )


def _scan_inline(doc, corpus) -> list[Violation]:
    """Line counts written inline after a link, as the skills roster writes them."""
    out: list[Violation] = []
    for i, line in enumerate(doc.lines):
        if i in doc.fenced:
            continue
        for m in _INLINE_COUNT.finditer(line):
            href, _tilde, digits = m.group(1), m.group(2), m.group(3)
            target = (doc.path.parent / unquote(href)).resolve()
            if not target.is_file():
                continue
            actual = _count_lines(target)
            if actual is None:
                continue
            claimed = int(digits.replace(",", ""))
            if abs(actual - claimed) > TOLERANCE:
                out.append(_violation(doc, corpus, target, i + 1, claimed, actual))
    return out


def _scan(doc, corpus) -> list[Violation]:
    out: list[Violation] = []
    lines = doc.lines
    n = len(lines)
    i = 0
    while i < n - 1:
        if i in doc.fenced or not looks_like_table_row(lines[i]) or not is_delimiter_row(lines[i + 1]):
            i += 1
            continue
        header = split_row(lines[i]) or []
        col = next((k for k, c in enumerate(header) if _COUNT_HEADER.match(c)), None)
        if col is None:
            i += 2
            continue

        j = i + 2
        while j < n and j not in doc.fenced and looks_like_table_row(lines[j]):
            cells = split_row(lines[j]) or []
            if len(cells) > col and cells:
                lm = _LINK_IN_CELL.search(cells[0])
                im = _INT.match(cells[col])
                if lm and im:
                    target = (doc.path.parent / unquote(lm.group(1))).resolve()
                    if target.is_file():
                        actual = _count_lines(target)
                        claimed = int(im.group(1).replace(",", ""))
                        if actual is not None and abs(actual - claimed) > TOLERANCE:
                            out.append(_violation(doc, corpus, target, j + 1, claimed, actual))
            j += 1
        i = j
    return out
