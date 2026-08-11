"""The floor under `preserved-evidence`'s scope filter.

`tools/fixtures/known-bad/` holds a unit per failure kind, which is the idiom for
a corpus check here, and every kind that can be scoped to a fixture root is
fixtured there rather than tested from Python. One kind cannot be: `undeclared`,
a unit carrying no `root.marker`. The three roots — this repository, `known-bad`
and `known-good` — share a single `config.json`, and a unit that declares no root
is by construction in scope in all three, so a fixture for it would turn the real
gate red. This file is where that kind is exercised instead.

The regression underneath all of it. Scope was keyed on `attestation.is_file()`,
so a unit whose witness was missing or whose path carried a typo was dropped from
the run and reported nothing at all — `0 error(s), 0 warning(s)` and, because the
per-check skip fired only when *no* unit survived the filter, no skip line
either. That is what a fully attested tree prints. A tree could be believed
attested while nothing read it, which is the class `preserved-evidence` exists to
close, reproduced one layer up inside the guard. `test_a_witness_absent_under_a_
declared_root_is_not_silent` is the arm that fails if scope is keyed back onto the
witness.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "tools"))

from corpuscheck.runner import load_config, run_checks  # noqa: E402

CHECK = "preserved-evidence"


def _run(root: Path, units: list[dict]):
    """The check alone, over `root`, with `units` standing in for the real list."""
    cfg = load_config()
    cfg["preserved_evidence"] = {"units": units}
    result, _ = run_checks(root, config=cfg, names=[CHECK])
    return result


def _tree(root: Path, rel: str) -> Path:
    tree = root / rel
    tree.mkdir(parents=True, exist_ok=True)
    (tree / "manifest.json").write_text('{"run_id": "r"}\n', encoding="utf-8")
    return tree


def _kinds(result) -> list[str]:
    return sorted(v.found.rsplit("(", 1)[-1].rstrip(")") for v in result.violations)


# ---------------------------------------------------------------------------
# The negative control. Without it every arm below could pass over a check that
# reports something for any input at all.


def test_a_declared_root_that_is_attested_reports_nothing(tmp_path) -> None:
    from corpuscheck import attest

    _tree(tmp_path, "evidence/records")
    unit = {
        "name": "u",
        "tree": "evidence/records",
        "attestation": "witness.json",
        "root": {"marker": "evidence", "why": "the fixture's own root"},
    }
    _text, digest = attest.build(tmp_path, unit, reason="test", attested_at="2026-08-11")
    unit["attestation_sha256"] = digest

    result = _run(tmp_path, [unit])
    assert result.violations == [], _kinds(result)


def test_a_unit_declaring_no_root_marker_is_reported(tmp_path) -> None:
    """The kind no fixture root can hold, because all three share one config."""
    _tree(tmp_path, "evidence/records")
    result = _run(tmp_path, [{
        "name": "undeclared-unit",
        "tree": "evidence/records",
        "attestation": "witness.json",
    }])

    assert _kinds(result) == ["undeclared"]
    only = result.violations[0]
    assert only.path == "tools/corpuscheck/config.json"
    assert "undeclared-unit" in only.found
    assert "root.marker" in only.expected
    # Nothing was declared to be elsewhere, so there is nothing to announce as
    # out of scope, and the violation is not swallowed by the empty-scope return.
    assert [r for name, r in result.skipped if name == CHECK] == []


def test_an_empty_root_marker_is_reported_as_undeclared(tmp_path) -> None:
    """A present-but-empty marker is the typo shape, and reads as no marker."""
    _tree(tmp_path, "evidence/records")
    result = _run(tmp_path, [{
        "name": "blank-marker",
        "tree": "evidence/records",
        "attestation": "witness.json",
        "root": {"marker": "", "why": "left blank by accident"},
    }])

    assert _kinds(result) == ["undeclared"]


def test_a_witness_absent_under_a_declared_root_is_not_silent(tmp_path) -> None:
    """The whole point. This is the plant the old filter passed over.

    Keying scope back onto `attestation.is_file()` makes this arm fail, and it is
    the only arm here that does not survive that change.
    """
    _tree(tmp_path, "evidence/records")
    result = _run(tmp_path, [{
        "name": "witness-gone",
        "tree": "evidence/records",
        "attestation": "tools/typod_witness.json",
        "root": {"marker": "evidence", "why": "the fixture's own root"},
        "attestation_sha256": "0" * 64,
    }])

    assert _kinds(result) == ["malformed"]
    only = result.violations[0]
    assert only.path == "tools/typod_witness.json"
    assert "the attestation is missing" in only.found
    # The expectation names the tree the missing witness should have covered,
    # rather than the per-kind sentence about an attestation agreeing with itself.
    assert "evidence/records" in only.expected


def test_a_unit_whose_root_is_elsewhere_is_out_of_scope_and_says_so(tmp_path) -> None:
    """Absent marker is another root's unit, and the word is not `disabled`."""
    result = _run(tmp_path, [{
        "name": "somebody-elses",
        "tree": "evidence/records",
        "attestation": "witness.json",
        "root": {"marker": "not-here", "why": "belongs to another corpus"},
    }])

    assert result.violations == []
    announced = [r for name, r in result.skipped if name == CHECK]
    assert len(announced) == 1, result.skipped
    assert "out of scope" in announced[0]
    assert "somebody-elses at not-here" in announced[0]
    assert "disabled" not in announced[0]


def test_an_absent_tree_under_a_declared_root_is_still_reported(tmp_path) -> None:
    """The earlier defect stays fixed: the marker is not the protected tree.

    Scope keyed on `tree` is what let deleting the protected directory take this
    check to `skipped`. A marker that is neither the tree nor the witness is what
    keeps a deleted tree loud.
    """
    from corpuscheck import attest

    _tree(tmp_path, "evidence/records")
    unit = {
        "name": "tree-gone",
        "tree": "evidence/records",
        "attestation": "witness.json",
        "root": {"marker": "evidence", "why": "the fixture's own root"},
    }
    _text, digest = attest.build(tmp_path, unit, reason="test", attested_at="2026-08-11")
    unit["attestation_sha256"] = digest

    (tmp_path / "evidence" / "records" / "manifest.json").unlink()
    (tmp_path / "evidence" / "records").rmdir()

    result = _run(tmp_path, [unit])
    assert _kinds(result) == ["removed"]
    assert result.violations[0].path == "evidence/records"


def test_the_committed_unit_list_declares_a_root_for_every_unit() -> None:
    """The real config, read as the corpus reads it.

    Every arm above runs on a synthetic list, so none of them would notice the
    committed list losing a marker.
    """
    units = json.loads(
        (REPO / "tools" / "corpuscheck" / "config.json").read_text(encoding="utf-8")
    )["preserved_evidence"]["units"]

    assert units, "the unit list is empty, which every other arm here would tolerate"
    missing = [u["name"] for u in units if not (u.get("root") or {}).get("marker")]
    assert missing == [], f"units declaring no root.marker: {missing}"

    # A marker that is the tree or the witness is the two keyings that were each
    # defeated by the thing they keyed on going missing.
    for unit in units:
        marker = unit["root"]["marker"]
        assert marker != unit["tree"], unit["name"]
        assert marker != unit["attestation"], unit["name"]
