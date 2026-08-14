"""T198 — the invariant file and its tests are a bijection.

`tests/invariants/runner.py` already fails the process on drift (T005 /
the invariants job). This file imports that same `reconcile` so a
pytest run sees the drift as T198, not only as a runner print.

Do not invent an INV for `runner.py`. Do not copy the INV list.
"""

from __future__ import annotations

from pathlib import Path

from tests.invariants.runner import HERE, load, reconcile

REPO = Path(__file__).resolve().parents[2]

#: The set T198 confirmed. A silent shrink is the pass over nothing.
EXPECTED_IDS = tuple(f"INV-{i:03d}" for i in range(1, 15))


def test_reconciliation_is_clean_on_this_tree() -> None:
    """The live bijection. An orphan test_*.py or a missing named file fails."""
    problems = reconcile(load())
    assert problems == [], (
        "invariants.yaml drifted from tests/invariants/:\n  "
        + "\n  ".join(problems)
    )


def test_the_declared_ids_are_inv001_through_inv014() -> None:
    """A shorter list is the reconciliation passing over a missing row."""
    ids = [entry["id"] for entry in load()["invariants"]]
    assert ids == list(EXPECTED_IDS), (
        f"the invariant set moved from {list(EXPECTED_IDS)} to {ids}. "
        "T198 confirmed INV-001 … INV-014; adding a row needs a test, "
        "removing one leaves a test without an invariant."
    )


def test_an_orphan_test_file_is_reported(tmp_path: Path) -> None:
    """The T198 plant: test_orphan.py with no yaml row must fail."""
    (tmp_path / "invariants.yaml").write_text(
        (HERE / "invariants.yaml").read_text()
    )
    (tmp_path / "test_orphan.py").write_text(
        '"""T198 plant — a test file with no invariant row."""\n'
        "def test_orphan() -> None:\n    assert True\n"
    )
    for name in HERE.glob("test_*.py"):
        (tmp_path / name.name).write_text(name.read_text())
    problems = reconcile(load(), here=tmp_path, repo=REPO)
    assert any("test_orphan.py" in item for item in problems), (
        "reconcile() did not report tests/invariants/test_orphan.py. "
        "An emptied orphan walk would pass this plant."
    )


def test_a_missing_named_file_is_reported() -> None:
    """The other direction: an INV that names a file that is not there."""
    document = load()
    document["invariants"][0]["test"] = "tests/invariants/test_does_not_exist.py"
    problems = reconcile(document)
    assert any("test_does_not_exist.py" in item for item in problems), (
        "reconcile() did not report a named file that does not exist. "
        "An emptied existence check would pass this plant."
    )


def test_runner_py_is_not_an_invariant() -> None:
    """Do not invent an INV for the runner."""
    declared = {Path(entry["test"]).name for entry in load()["invariants"]}
    assert "runner.py" not in declared
    assert (HERE / "runner.py").is_file()
