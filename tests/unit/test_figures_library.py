"""The decision branches of `tools/corpuscheck/figures.py`, held one at a time.

`figures.py` decides what counts as a quoted measurement, and seven checks read
through it — `numeric-provenance` and `sum-arithmetic` for arithmetic and figure
shape, and `inventory-count`, `register-range`, `count-versus-range`,
`definition-count` and `dry-run-verdict` for `struck_spans` and `inside_spans`.
It is a library rather than a gate, so nothing runs it directly and every branch
in it is held, if at all, through whatever a check happens to ask of it.

A 2026-08-11 census of the checker's decision branches measured this module at
**10 of 20 unheld against `tools/selftest.py`** — the worst rate in either
population it covered — where unheld means the branch was neutralised and the
self-test stayed green. Re-scored against the gate set rather than against the
self-test alone, four of those ten turn out to be held by `check_corpus.py` and
six by nothing at all:

    figures#006  `"percent_decimal" in kinds`   check_corpus, 95 new violations
    figures#008  `"|" not in line`              check_corpus, 1 new violation
    figures#011  `_RATE_HEADER.search(text)`    check_corpus, the same 1
    figures#012  `start <= col - 1 < end`       check_corpus, the same 1

Three of those four rest on **one line of the real corpus** —
`research/05-frontier-lab-agent-definitions.md:413`, a `$2.50` cell under a rate
header — so editing one prose line silently unholds the whole rate-column
mechanism. That is a hold by accident and not a hold by design, which is why the
four are pinned here beside the six.

**Why these are unit tests rather than fixture rows.** `tools/fixtures/known-bad`
is the idiom for a corpus check and it is the wrong instrument for this module
twice over. A fixture holds a branch only through a violation some check emits,
so it cannot reach a pure function whose result never becomes one — `table_cells`
returns offsets and `digit_neighbours` returns a hint fragment. And a fixture
that changes what counts as a quoted figure moves the corpus: the two fixture
roots share this repository's `config.json`, and `percent_decimal` is off in it by
design, so no fixture can enable the kind without enabling it for the gate.

The one thing here a fixture does hold is the *wiring* from `digit_neighbours`
into a violation's hint, and `tools/selftest.py` carries two rows for it. The
plants were already in `known-bad` and no needle read them.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "tools"))

from corpuscheck.figures import (  # noqa: E402
    _ratio_aliases,
    _trim_zeros,
    column_of,
    digit_neighbours,
    extract,
    rate_columns,
    table_cells,
)

#: A rate header, a spend header, and a plain one, in one row. `Model spend` is
#: the case the module's own comment names as a header that must *not* suppress:
#: it is a total, not a denominator.
_HEADER = "| Tool | Cost / 1k calls | Model spend |"

#: The four ways markdown writes a table row. All four are legal and a renderer
#: reads them identically, which is the property the trimming exists to produce.
_PIPE_STYLES = (
    ("both", "| Tool | Cost / 1k calls | Model spend |"),
    ("leading only", "| Tool | Cost / 1k calls | Model spend"),
    ("trailing only", "Tool | Cost / 1k calls | Model spend |"),
    ("neither", "Tool | Cost / 1k calls | Model spend"),
)


# ---------------------------------------------------------------------------
# figures#000 — the dot guard in `_trim_zeros`
# ---------------------------------------------------------------------------


def test_trimming_zeros_leaves_an_integer_alone() -> None:
    """`40` is not `4`, and the guard is the only thing between them.

    `_trim_zeros` is reached with an integer from the multiplier kind, whose
    pattern admits `40×` with no decimal part. Without the guard the trailing
    `rstrip("0")` runs on it and every round multiplier loses a digit.
    """
    assert _trim_zeros("40") == "40"
    assert _trim_zeros("100") == "100"
    assert _trim_zeros("0.5000") == "0.5"


def test_a_unit_ratio_reaches_the_percentage_a_finding_would_write() -> None:
    """`1.0000` aliases to `100`, which is the case the coarse form was dropped for.

    `_ratio_aliases`'s docstring records that a one-decimal percentage alias was
    removed because it left the last digit of a four-decimal ratio unguarded, and
    that `1.0000` still reaches `100` through `.4f` and `.2f` both trimming to it.
    Nothing held that sentence; the trimming it depends on is this branch.
    """
    assert _ratio_aliases("1.0000") == ("1", "100")
    assert _ratio_aliases("0.8961") == ("0.8961", "89.61")


# ---------------------------------------------------------------------------
# figures#006 — the `percent_decimal` kind gate in `extract`
# ---------------------------------------------------------------------------


def test_a_decimal_percentage_is_extracted_only_when_its_kind_is_asked_for() -> None:
    """Both directions, because `percent_decimal` is off in the shipped config.

    `config.json` sets `numeric_kinds` to ratios, money and multipliers and
    records why: turning percentages on produces roughly 125 violations over
    documents that legitimately quote other people's figures. So the true arm of
    this gate is never taken by the gate, and the kind is a documented capability
    with nothing establishing that it still works when asked for. Neutralising
    the gate adds 95 violations to the real corpus, which `check_corpus.py`
    notices; deleting the body it guards is invisible to every instrument.
    """
    line = "recall reached 53.6% across the sweep"

    asked = extract(line, 1, {"percent_decimal"})
    assert [(f.kind, f.key) for f in asked] == [("percent_decimal", "53.6")]
    assert "0.536" in asked[0].aliases

    not_asked = extract(line, 1, {"ratio4", "money_cents", "multiplier"})
    assert not_asked == [], "a kind that was not asked for was extracted anyway"


# ---------------------------------------------------------------------------
# figures#008, #009, #010 — the pipe handling in `table_cells`
# ---------------------------------------------------------------------------


def test_a_line_with_no_pipe_has_no_cells() -> None:
    """The early return, and the shape of what happens without it.

    Every caller treats an empty result as "not a table row". Without the guard a
    line of prose yields one cell spanning the whole line, and `column_of` then
    answers 0 for any offset in any sentence in the corpus.
    """
    assert table_cells("a sentence about $2.50 per call") == []
    assert table_cells("") == []
    assert table_cells(_HEADER), "a real table row produced no cells"


def test_the_delimiting_pipes_are_not_cells() -> None:
    """Three headers, three cells, and no empty cell at either end.

    The two trims are what make a cell index mean the same thing in a header row
    and in a body row. Each of them dropped, the indices move by one and the
    suppression in `numeric-provenance` reads the wrong column.
    """
    cells = table_cells(_HEADER)
    assert [text for _, _, text in cells] == [
        " Tool ",
        " Cost / 1k calls ",
        " Model spend ",
    ]
    # A row that is nothing but a delimiter has no cells rather than one empty
    # one, which is the `and spans` half of the trailing trim.
    assert table_cells("|") == []


def test_a_column_index_means_the_same_thing_in_all_four_pipe_styles() -> None:
    """The invariant the trims exist to produce, stated across the styles.

    A markdown table may write the leading and trailing pipes or omit either, and
    a renderer reads all four the same way. So must this: a header and a body row
    in different styles is a table the corpus is free to contain, and the
    suppression compares an index from one against an index from the other.
    """
    for label, header in _PIPE_STYLES:
        assert sorted(rate_columns(header)) == [1], label
        offset = header.index("Model spend") + 1
        assert column_of(header, offset) == 2, label


# ---------------------------------------------------------------------------
# figures#011 — the rate-header test in `rate_columns`
# ---------------------------------------------------------------------------


def test_only_a_header_declaring_a_denominator_is_a_rate_column() -> None:
    """Both directions of the one test that decides whether money is suppressed.

    `Cost / 1k calls` names a denominator and its column holds prices; `Model
    spend` is a total and its column holds measurements that must keep their
    provenance checked. Inverting the test swaps the two, which is a check that
    exempts exactly the figures it exists to read.
    """
    assert sorted(rate_columns(_HEADER)) == [1]
    assert rate_columns("| Tool | Model spend | Findings |") == set()
    assert rate_columns("not a table row at all") == set()


# ---------------------------------------------------------------------------
# figures#012 — the containment test in `column_of`
# ---------------------------------------------------------------------------


def test_an_offset_maps_to_the_cell_it_falls_in_and_to_nothing_else() -> None:
    """A half-open span, tested at both edges and past the end.

    `column_of` answers the question "is this figure in a rate column", so a
    wrong answer either suppresses a measurement or reports a price. Past the
    last cell the answer is `None` rather than a column, because a figure off the
    end of the row is not in any of them.
    """
    row = "| Sonnet | $2.50 | 4 runs |"
    assert column_of(row, row.index("Sonnet") + 1) == 0
    assert column_of(row, row.index("$2.50") + 1) == 1
    assert column_of(row, row.index("4 runs") + 1) == 2
    # The first character of the row is the leading pipe, which is not a cell.
    assert column_of(row, 1) is None
    assert column_of(row, len(row) + 40) is None


# ---------------------------------------------------------------------------
# figures#017, #018, #019 — the two loops in `digit_neighbours`
# ---------------------------------------------------------------------------


def test_a_single_digit_substitution_is_a_neighbour() -> None:
    """The loop that turns "unsupported" into "probably this, mistyped".

    Both of this loop's guards are held here and neither can be separated from
    the other by output: skipping the digits instead of the non-digits, and
    keeping only the identity substitution, both leave the substitution set with
    nothing a findings document contains. The two known-bad plants that exercise
    this are `0.8964` against a finding's `0.8961` and `0.8695` against `0.8696`.
    """
    near = digit_neighbours("0.8964")
    assert "0.8961" in near
    assert "0.8974" in near
    assert "0.8964" not in near, "a value is not its own neighbour"

    # The exact set for a short value, because membership alone does not hold the
    # non-digit skip in the direction that *widens* the set: substituting the
    # decimal point produces `102` as a neighbour of `1.2`, which is not a
    # mistyping of anything.
    assert digit_neighbours("1.2") == {
        "0.2", "2.2", "3.2", "4.2", "5.2", "6.2", "7.2", "8.2", "9.2",
        "1.0", "1.1", "1.3", "1.4", "1.5", "1.6", "1.7", "1.8", "1.9",
    }


def test_a_transposition_of_adjacent_digits_is_a_neighbour() -> None:
    """The second loop, and the plant in `known-bad` that is one.

    `research/01-fixture-metrics.md:6` quotes `0.7861` where the finding measured
    `0.7681` — two digits transposed, which no single substitution reaches. This
    loop is the only thing that names the intended figure, and the guard above it
    is what stops it transposing a digit with the decimal point.
    """
    near = digit_neighbours("0.7861")
    assert "0.7681" in near
    assert ".07861" not in near, "the decimal point was transposed with a digit"
    # Equal adjacent digits transpose to the value itself and contribute nothing.
    assert digit_neighbours("11") == {"01", "10", "12", "13", "14",
                                      "15", "16", "17", "18", "19",
                                      "21", "31", "41", "51",
                                      "61", "71", "81", "91"}
