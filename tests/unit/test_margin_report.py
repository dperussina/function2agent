"""T177 — FR-040 gate report: three branches intact, SC-013 gated on labels.

The report is measurement. It does not change `Result`, a gate, or the
loop. It does not invent a human label. When the label table is empty
the chance branch is not applied and SC-013's window does not open.
The corpus records that the one adjudication pass this needed was
never performed and that a model stood in.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from src.runtime.reports import margin as mg
from tests.invariants.test_import_graph import forbidden_edges

REPO = Path(__file__).resolve().parents[2]
MARGIN = REPO / "src" / "runtime" / "reports" / "margin.py"
SUCCESS_PATH = (
    REPO / "src" / "runtime" / "loop.py",
    REPO / "src" / "runtime" / "runner.py",
    REPO / "src" / "runtime" / "serving.py",
    REPO / "src" / "runtime" / "main.py",
    REPO / "src" / "contracts" / "result.py",
)
FORBIDDEN_FROM_MARGIN = (
    "src.contracts.result",
    "src.runtime.loop",
    "src.runtime.runner",
    "src.runtime.serving",
    "src.runtime.main",
    "src.runtime.judge",
)
SCOPE = {"deployment_id": "d-1", "tenant_id": "t-1"}


def _imported(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return names


def _label(result_id: str, label: str, adjudicator: str = "operator-ada") -> mg.LabelRow:
    return mg.LabelRow(
        result_id=result_id, adjudicator=adjudicator, label=label, at=1.0,
    )


def _judge(result_id: str, verdict: str) -> mg.VerdictRow:
    return mg.VerdictRow(result_id=result_id, verdict=verdict)


def _verifier(result_id: str, label: str) -> mg.VerifierRow:
    return mg.VerifierRow(result_id=result_id, label=label)


def _closed() -> mg.MarginReport:
    return mg.report([], [], [], **SCOPE)


# ---------------------------------------------------------------------------
# Empty labels: the honest production state. Window closed, branches intact.


def test_empty_labels_do_not_open_the_sc013_window() -> None:
    """Labelling capacity does not exist. The window stays closed.

    Verdicts and verifier labels are present on purpose: they are not
    ground truth, and using either would close a report that must stay
    open as a gap.
    """
    produced = mg.report(
        [],
        [_judge("r1", "correct"), _judge("r2", "incorrect")],
        [_verifier("r1", "correct"), _verifier("r2", "incorrect")],
        **SCOPE,
    )
    assert produced.labelled_count == 0
    assert produced.window_open is False
    assert produced.applied_branch is None
    assert produced.margin_pp is None
    assert produced.judge_discrimination is None


def test_empty_labels_do_not_apply_the_chance_branch() -> None:
    """A judge no better than chance cannot be scored without ground truth."""
    produced = _closed()
    assert produced.applied_branch is not mg.BRANCH_CHANCE
    assert produced.applied_branch is None
    document = produced.document()
    assert document["applied_branch"] is None
    assert document["sc013_window_open"] is False


def test_all_three_branches_are_present_when_labels_do_not_exist() -> None:
    """FR-040: the gate is intact, not dropped because it cannot fire."""
    document = _closed().document()
    assert set(document["branches"]) == set(mg.BRANCHES)
    assert set(mg.BRANCHES) == {
        mg.BRANCH_HEADLINE, mg.BRANCH_INTERNAL, mg.BRANCH_CHANCE,
    }
    assert mg.BRANCH_CHANCE in document["branches"]
    assert "no better than chance" in document["branches"][mg.BRANCH_CHANCE]
    assert "ten percentage points" in document["branches"][mg.BRANCH_HEADLINE]
    assert "internal detail" in document["branches"][mg.BRANCH_INTERNAL]


def test_the_historical_pass_is_recorded_as_never_performed() -> None:
    document = _closed().document()
    assert "never performed" in document["historical_pass"]
    assert "model stood in" in document["historical_pass"]
    assert document["historical_pass"] == mg.HISTORICAL_PASS_NEVER_PERFORMED
    assert "labelling capacity" in document["sc013_precondition"]


def test_the_threshold_is_the_pre_registered_ten_points() -> None:
    assert mg.MARGIN_THRESHOLD_PP == 10.0
    assert _closed().document()["threshold_pp"] == 10.0


# ---------------------------------------------------------------------------
# With human labels the three branches fire. Chance is independent of margin.


def test_a_margin_of_ten_or_more_is_headline() -> None:
    # 10 labelled: verifier 9/10, judge 7/10 → 20pp, judge above chance.
    labels = [_label(f"r{i}", "correct") for i in range(10)]
    judges = [_judge(f"r{i}", "correct" if i < 7 else "incorrect") for i in range(10)]
    verifiers = [_verifier(f"r{i}", "correct" if i < 9 else "incorrect") for i in range(10)]
    produced = mg.report(labels, judges, verifiers, **SCOPE)
    assert produced.window_open is True
    assert produced.applied_branch == mg.BRANCH_HEADLINE
    assert produced.margin_pp == pytest.approx(20.0)
    assert produced.judge_discrimination == pytest.approx(0.2)


def test_a_smaller_margin_is_an_internal_detail() -> None:
    # verifier 8/10, judge 7/10 → 10pp is headline; 8 vs 8 is 0; use 8 vs 7 = 10
    # exactly 10 is headline. Smaller: verifier 8/10, judge 7.5... use 10 items:
    # verifier 8/10, judge 8/10 wait that's 0. verifier 8/10, judge 7/10 = 10pp.
    # Need < 10: verifier 8/10, judge 7.2 would need more items.
    # 20 items: verifier 16/20 = 0.8, judge 15/20 = 0.75 → 5pp.
    labels = [_label(f"r{i}", "correct") for i in range(20)]
    judges = [_judge(f"r{i}", "correct" if i < 15 else "incorrect") for i in range(20)]
    verifiers = [_verifier(f"r{i}", "correct" if i < 16 else "incorrect") for i in range(20)]
    produced = mg.report(labels, judges, verifiers, **SCOPE)
    assert produced.applied_branch == mg.BRANCH_INTERNAL
    assert produced.margin_pp == pytest.approx(5.0)
    assert produced.judge_discrimination == pytest.approx(0.25)


def test_a_judge_at_chance_is_the_chance_branch_even_when_the_margin_is_large() -> None:
    """Independence: a 40pp margin does not hide a chance-level judge."""
    labels = [_label(f"r{i}", "correct") for i in range(10)]
    judges = [_judge(f"r{i}", "correct" if i < 5 else "incorrect") for i in range(10)]
    verifiers = [_verifier(f"r{i}", "correct" if i < 9 else "incorrect") for i in range(10)]
    produced = mg.report(labels, judges, verifiers, **SCOPE)
    assert produced.margin_pp == pytest.approx(40.0)
    assert produced.judge_discrimination == pytest.approx(0.0)
    assert produced.applied_branch == mg.BRANCH_CHANCE


def test_the_historical_pass_is_still_never_performed_when_labels_exist() -> None:
    """Test labels are not the frozen-oracle pass. The corpus fact stays."""
    labels = [_label("r1", "correct")]
    produced = mg.report(
        labels, [_judge("r1", "correct")], [_verifier("r1", "correct")], **SCOPE,
    )
    assert "never performed" in produced.historical_pass
    assert "model stood in" in produced.historical_pass


# ---------------------------------------------------------------------------
# The report does not invent labels, and does not import the success path.


def test_the_report_does_not_copy_the_verifier_into_a_human_label() -> None:
    """Circularity. A fill from the verifier would open the window."""
    source = mg.module_source()
    empty_arm = source.split("if not labelled:")[1].split("judges =")[0]
    assert "LabelRow(" not in empty_arm, (
        "the empty-labels arm constructs a LabelRow. That is inventing "
        "a human label inside the report."
    )
    assert "verifier_calls" not in empty_arm, (
        "the empty-labels arm reads verifier_calls. Using the verifier "
        "as ground truth is the circularity FR-040 forbids."
    )


def test_the_report_does_not_import_the_success_path_or_the_judge() -> None:
    edges: list[str] = []
    for imported in sorted(_imported(MARGIN)):
        for forbidden in FORBIDDEN_FROM_MARGIN:
            if imported == forbidden or imported.startswith(forbidden + "."):
                edges.append(f"margin.py imports {imported}")
    assert edges == [], (
        "the margin report imported a success-path or judge module:\n  "
        + "\n  ".join(edges)
    )


def test_the_margin_import_scan_fires_on_a_planted_result_import(
        tmp_path: Path) -> None:
    planted = tmp_path / "margin.py"
    planted.write_text("from src.contracts.result import Result\n")
    found: list[str] = []
    for imported in _imported(planted):
        if imported == "src.contracts.result" or imported.startswith(
                "src.contracts.result."):
            found.append(imported)
    assert found, "the margin→result scan did not report a planted import"


def test_the_success_path_does_not_import_the_margin_report() -> None:
    found: list[str] = []
    for path in SUCCESS_PATH:
        relative = path.relative_to(REPO).as_posix()
        for imported in sorted(_imported(path)):
            if imported == "src.runtime.reports.margin" or imported.startswith(
                    "src.runtime.reports.margin."):
                found.append(f"{relative} imports {imported}")
    assert found == [], (
        "a success-path module imported the margin report:\n  "
        + "\n  ".join(found)
    )


def test_forbidden_edges_stay_empty() -> None:
    assert forbidden_edges(REPO) == []
