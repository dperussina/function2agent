"""table-integrity — every table renders as one table.

Three failures, all of which have happened here:

  table-orphan-row      A blank line inside a table. Markdown ends the table at
                        the blank and renders everything after it as body text.
                        The row is still in the file, still looks right in a
                        diff, and is gone from the rendered page. This has
                        happened twice and neither instance was caught by the
                        pass that introduced it.

  table-column-count    A row with a different number of cells than the header.
                        Cells silently drop or shift.

  table-no-delimiter    Two or more consecutive pipe rows with no `|---|`
                        separator. Renders as literal text with pipes in it.

Cell counting goes through `corpus.split_row`, which respects `\\|` escapes and
inline code spans. An earlier ad-hoc validator in this repository did not, and
reported a false positive on `` `api-key:endpoint:<chat\\|image>` `` in
research/08-auth-identity-and-secrets.md. That exact string is in the fixture.
"""

from __future__ import annotations

from ..corpus import Corpus, is_delimiter_row, looks_like_table_row, split_row
from ..registry import check
from ..report import ERROR, Violation

#: How many blank lines after a table still count as "inside" it.
#:
#: Was 1, on the reasoning that two or more blanks are a deliberate paragraph
#: break and the rows after them are a new table. The second half of that is
#: already enforced, and better, by the delimiter lookahead below — a new table
#: has a `|---|` under its header and is excluded on that ground, at any gap. So
#: the bound was only deciding how far a *broken* row could sit from the table it
#: fell out of, and one blank line of that is slack. Two blanks and a lone pipe
#: row is still a row that renders as body text.
#:
#: It does not go higher. A pipe row far from any table is not reliably a table
#: row: `|P ∩ A_c| / |A_c ∩ (S ∪ N)|` in
#: harness/deployment-reachability/PREREGISTRATION.md is set-cardinality
#: notation, and it is the reason `table-no-delimiter` needs two consecutive
#: rows before it will speak.
MAX_ORPHAN_GAP = 2


def _cell_count(row: str) -> int:
    cells = split_row(row)
    return len(cells) if cells else 0


@check("table-integrity", "Tables render as one table: no orphaned rows, consistent columns.")
def run(corpus: Corpus, ctx: dict) -> list[Violation]:
    violations: list[Violation] = []
    for doc in corpus.markdown():
        violations.extend(_scan(doc))
    return violations


def _scan(doc) -> list[Violation]:
    out: list[Violation] = []
    lines = doc.lines
    n = len(lines)
    i = 0
    while i < n:
        if i in doc.fenced or not looks_like_table_row(lines[i]):
            i += 1
            continue

        header_idx = i
        # A table is a header row followed immediately by a delimiter row.
        if i + 1 < n and i + 1 not in doc.fenced and is_delimiter_row(lines[i + 1]):
            width = _cell_count(lines[header_idx])
            j = i + 2
            last_body = i + 1
            while j < n and j not in doc.fenced:
                line = lines[j]
                if looks_like_table_row(line):
                    got = _cell_count(line)
                    if got != width:
                        out.append(
                            Violation(
                                check="table-integrity",
                                severity=ERROR,
                                path=doc.relpath,
                                line=j + 1,
                                found=f"row has {got} cell(s): {_excerpt(line)}",
                                expected=f"{width} cell(s), matching the header at line {header_idx + 1}",
                                hint="table-column-count; escaped pipes must be written \\| and pipes inside `code` are fine",
                            )
                        )
                    last_body = j
                    j += 1
                    continue
                if not line.strip():
                    # Look past the gap: another table row means the blank cut
                    # this table in half.
                    k = j
                    blanks = 0
                    while k < n and not lines[k].strip():
                        blanks += 1
                        k += 1
                    if (
                        blanks <= MAX_ORPHAN_GAP
                        and k < n
                        and k not in doc.fenced
                        and looks_like_table_row(lines[k])
                        and not is_delimiter_row(lines[k])
                        and not (k + 1 < n and is_delimiter_row(lines[k + 1]))
                    ):
                        out.append(
                            Violation(
                                check="table-integrity",
                                severity=ERROR,
                                path=doc.relpath,
                                line=j + 1,
                                found=f"blank line inside the table started at line {header_idx + 1}",
                                expected="no blank line between the header and the last row",
                                hint=(
                                    f"table-orphan-row; line {k + 1} renders as body text, not a row: "
                                    f"{_excerpt(lines[k])}"
                                ),
                            )
                        )
                        j = k
                        continue
                break
            i = max(j, last_body + 1)
            continue

        # No delimiter after the first pipe row. Two or more in a row means
        # somebody wrote a table and forgot the separator.
        run_len = 0
        j = i
        while j < n and j not in doc.fenced and looks_like_table_row(lines[j]):
            run_len += 1
            j += 1
        if run_len >= 2:
            out.append(
                Violation(
                    check="table-integrity",
                    severity=ERROR,
                    path=doc.relpath,
                    line=i + 1,
                    found=f"{run_len} consecutive pipe rows with no delimiter row",
                    expected="a |---|---| delimiter row directly beneath the header",
                    hint="table-no-delimiter; without it the block renders as literal text",
                )
            )
        i = max(j, i + 1)
    return out


def _excerpt(line: str, width: int = 72) -> str:
    s = line.strip()
    return s if len(s) <= width else s[: width - 1] + "…"
