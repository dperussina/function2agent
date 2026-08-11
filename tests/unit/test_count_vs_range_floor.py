"""The floor under `count-versus-range`, and the one arm no fixture can hold.

`tools/fixtures/known-bad/` and `known-good/` hold seven of this check's eight
decision branches between them — the register noun that scopes it, the
de-emphasising copy, the struck count, the last-unstruck bound, the hard-wrap
window, the subset guard and the connector test. Each was probed by
neutralising it and watching `selftest.py` go red.

The eighth cannot be held there, and the reason is the branch itself. It is the
announcement that fires when the rule reads **nothing** — the floor every count
check in this repository carries, because a rule whose pattern has stopped
matching reports zero findings and a rule whose corpus is clean reports zero
findings, and those are the same output. A fixture cannot plant that state: the
fixture roots are where the rule must find something, and a root where it finds
nothing is a root where `selftest.py`'s "every check must fire" direction fails
for a different reason and hides the one being tested.

So the empty corpus is built here instead.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "tools"))

from corpuscheck.runner import load_config, run_checks  # noqa: E402

CHECK = "count-versus-range"


def _corpus(root: Path, plan: str) -> Path:
    """A feature whose register runs to OD-04 and whose plan says `plan`."""
    feature = root / "specs" / "001-f"
    feature.mkdir(parents=True, exist_ok=True)
    (feature / "spec.md").write_text("# Spec\n")
    (feature / "plan.md").write_text(
        f"# Plan\n\n{plan}\n\n"
        "## Owner decisions\n\n"
        "- **OD-01**: The first.\n"
        "- **OD-02**: The second.\n"
        "- **OD-03**: The third.\n"
        "- **OD-04**: The fourth.\n"
    )
    return root


def _run(root: Path):
    cfg = load_config()
    cfg["include"] = ["specs"]
    cfg["exclude"] = []
    return run_checks(root, config=cfg, names=[CHECK])[0]


def test_a_rule_that_read_nothing_says_so(tmp_path):
    """Zero findings from an unread rule and from a clean corpus differ.

    The register is here and the count is here, but nothing pairs them — the
    noun the rule keys on never appears. Without the announcement this run
    prints exactly what a verified corpus prints.
    """
    _corpus(tmp_path, "There are four decisions of record, OD-01 through OD-04.")
    result = _run(tmp_path)
    assert result.violations == []
    assert [c for c, _ in result.skipped] == [CHECK], (
        "the rule paired nothing and reported it as a clean result, which is "
        "indistinguishable from having checked something"
    )
    assert "nothing read" in result.skipped[0][1]


def test_a_rule_that_read_something_does_not_announce(tmp_path):
    """The floor is not always-on; it reports the state it is named for."""
    _corpus(tmp_path, "**four** owner decisions (OD-01 through OD-04) were taken.")
    result = _run(tmp_path)
    assert result.violations == []
    assert result.skipped == [], (
        f"the rule read a live pairing and announced anyway: {result.skipped}"
    )


def test_the_count_and_the_range_are_compared_to_each_other(tmp_path):
    """The defect this rule was built for, in the shape it actually had.

    `specs/001-discovery-validation/plan.md:16` read *thirty owner decisions
    (OD-01 through OD-31)* for a day: the range is generated and advanced with
    the register, the count is prose, and the two halves drifted apart. Neither
    `register-range` nor `definition-count` reads the pair.
    """
    _corpus(tmp_path, "**three** owner decisions (OD-01 through OD-04) were taken.")
    result = _run(tmp_path)
    assert [v.severity for v in result.violations] == ["warning"]
    assert "4, the number of OD entries" in result.violations[0].expected
