"""T180 — state-diff labels on the reference application, not a model judge.

FR-041, constitution Principle I. Snapshot, call, diff. The exporter
consumes the labels; `labelled` is True only when every row carries one.

Run:
    python -m pytest tests/batteries/test_effect_gate_oracle.py -v
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from src.runtime.reports import effect_corpus as corpus
from src.runtime.reports import effect_precision as precision
from tests.batteries.effect_gate_oracle import (
    FIXTURE,
    LABEL_READ_ONLY_CORRECT,
    LABEL_WRITE_OBSERVED,
    LABELS,
    OracleError,
    T181_THRESHOLD_STAYS_UNSET,
    T214_RESIDUAL_NO_RUN_PRODUCES_A_RESULT,
    fresh_application,
    instantiate,
    label_corpus,
    label_served_operations,
    module_source,
    observe,
    require_label,
    snapshot,
)
from tests.batteries.evidence import record_evidence

REPO = Path(__file__).resolve().parents[2]
ORACLE = REPO / "tests" / "batteries" / "effect_gate_oracle.py"
THIS = Path(__file__).resolve()
STATE_PATH = FIXTURE / "state.json"

JUDGE_MODULES = (
    "src.runtime.judge",
    "src.runtime.judges",
)


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


def _judge_imports(path: Path) -> list[str]:
    found: list[str] = []
    relative = path.relative_to(REPO).as_posix() if path.is_relative_to(REPO) else path.name
    for imported in sorted(_imported(path)):
        for module in JUDGE_MODULES:
            if imported == module or imported.startswith(module + "."):
                found.append(f"{relative} imports {imported}")
    return found


def _row(**overrides: object) -> corpus.ObservationRow:
    fields: dict[str, object] = {
        "decision_seq": 1,
        "resolved_tier": "read_only",
        "rule_id": "REFAPP-OP-001",
        "matched_template": "/health",
        "method": "GET",
        "spec_metadata": '{"operation_id":"health","safe":true}',
        "disposition": "allow",
    }
    fields.update(overrides)
    return corpus.ObservationRow(**fields)  # type: ignore[arg-type]


def _reference_rows() -> tuple[corpus.ObservationRow, corpus.ObservationRow]:
    """One allow that must not mutate, one deny of a call that does."""
    return (
        _row(),
        _row(
            decision_seq=2,
            resolved_tier="write",
            rule_id="REFAPP-OP-005",
            matched_template="/shipments/{shipment_id}/cancel",
            method="POST",
            spec_metadata=(
                '{"operation_id":"cancel_shipment","safe":false,'
                '"operation_rule_id":"REFAPP-OP-005"}'
            ),
            disposition="deny",
        ),
    )


# ---------------------------------------------------------------------------
# Snapshot, call, diff. Plants retarget the comparison, skip the call,
# or take the snapshot after.


def test_a_mutating_call_is_labelled_write_observed() -> None:
    """Plant: `mutated = before != after` becomes `mutated = False`."""
    control = snapshot(fresh_application())
    app = fresh_application()
    diff = observe(app, "POST", "/shipments/S-0001/cancel")
    assert diff.before == control
    assert diff.after != control
    assert diff.mutated is True
    assert diff.label == LABEL_WRITE_OBSERVED
    assert app.calls == [("POST", "/shipments/S-0001/cancel")]


def test_an_unchanged_call_is_labelled_read_only_correct() -> None:
    """Plant: `mutated = before != after` becomes `mutated = True`."""
    control = snapshot(fresh_application())
    app = fresh_application()
    diff = observe(app, "GET", "/health")
    assert diff.before == control
    assert diff.after == control
    assert diff.mutated is False
    assert diff.label == LABEL_READ_ONLY_CORRECT


def test_the_call_is_issued() -> None:
    """Plant: `_issue(app, method, target)` is dropped, so a write never happens."""
    app = fresh_application()
    observe(app, "POST", "/shipments/S-0002/cancel")
    assert app.calls == [("POST", "/shipments/S-0002/cancel")]


def test_the_before_snapshot_is_taken_before_the_call() -> None:
    """Plant: `before = snapshot(app)` moves to after `_issue`.

    Then `before` is the mutated state, the diff is empty, and a write
    is labelled read_only_correct — the same reading as skipping the
    call, for a different reason.
    """
    control = snapshot(fresh_application())
    app = fresh_application()
    diff = observe(app, "POST", "/shipments/S-0003/cancel")
    assert diff.before == control
    assert diff.after != control
    assert diff.label == LABEL_WRITE_OBSERVED


def test_a_non_mutating_write_shaped_call_is_labelled_read_only_correct() -> None:
    """Observable state, not the verb.

    Plant: `if not mutated:` becomes `if method in ("GET", "HEAD", "OPTIONS"):`.
    POST /shipments/S-9999/cancel 404s and leaves state unchanged; labelling
    it write_observed because the method is POST is a specification
    restating itself.
    """
    control = snapshot(fresh_application())
    app = fresh_application()
    diff = observe(app, "POST", "/shipments/S-9999/cancel")
    assert diff.before == control
    assert diff.after == control
    assert diff.label == LABEL_READ_ONLY_CORRECT
    assert app.calls == [("POST", "/shipments/S-9999/cancel")]


def test_every_published_read_is_read_only_correct_and_the_write_is_observed() -> None:
    diffs = label_served_operations()
    labels = [diff.label for diff in diffs]
    assert labels.count(LABEL_READ_ONLY_CORRECT) == 4
    assert labels.count(LABEL_WRITE_OBSERVED) == 1
    assert set(labels) <= LABELS


# ---------------------------------------------------------------------------
# The exporter consumes the labels. labelled is True when every row has one.


def test_the_exported_corpus_is_labelled_after_the_oracle_runs() -> None:
    """Plant: `replace(row, label=labels[row.decision_seq])` sets `label=None`.

    Then every observation exists, none carries a T180 label, and
    `labelled` stays False — SC-014 starting over a set the oracle ran
    and then dropped.
    """
    exported = label_corpus(_reference_rows())
    assert exported.labelled is True
    assert exported.label_absent_because is None
    assert exported.rows[0].label == LABEL_READ_ONLY_CORRECT
    assert exported.rows[1].label == LABEL_WRITE_OBSERVED
    document = exported.document()
    assert document["labelled"] is True
    assert document["row_count"] == 2


def test_attach_labels_refuses_a_row_the_oracle_omitted() -> None:
    with pytest.raises(corpus.CorpusExportError, match="no T180 label"):
        corpus.attach_labels(_reference_rows(), {1: LABEL_READ_ONLY_CORRECT})


def test_an_unlabelled_export_is_still_unlabelled_until_the_oracle_runs() -> None:
    exported = corpus.export_rows(list(_reference_rows()))
    assert exported.labelled is False
    assert all(row.label is None for row in exported.rows)


# ---------------------------------------------------------------------------
# Closed vocabulary. A third value is not an observation.


def test_a_third_label_is_refused() -> None:
    """Plant: `if label not in LABELS:` becomes `if False:`."""
    with pytest.raises(OracleError, match="observable-state label"):
        require_label("the_model_said_so")
    assert require_label(LABEL_READ_ONLY_CORRECT) == LABEL_READ_ONLY_CORRECT
    assert require_label(LABEL_WRITE_OBSERVED) == LABEL_WRITE_OBSERVED


def test_an_unknown_placeholder_is_refused_rather_than_guessed() -> None:
    with pytest.raises(OracleError, match="placeholder"):
        instantiate("GET", "/orders/{id}")


# ---------------------------------------------------------------------------
# The committed fixture is the control. The copy is the treatment.


def test_the_oracle_does_not_touch_the_committed_fixture() -> None:
    on_disk = STATE_PATH.read_bytes()
    app = fresh_application()
    observe(app, "POST", "/shipments/S-0001/cancel")
    assert STATE_PATH.read_bytes() == on_disk


def test_each_row_is_driven_against_a_fresh_copy() -> None:
    """Two cancels of S-0001, two write_observed labels.

    A shared application would make the second a no-op: status is already
    cancelled, the diff is empty, and the corpus would report a write as
    read_only_correct because its baseline moved with it.
    """
    rows = (
        _row(
            decision_seq=1,
            resolved_tier="write",
            rule_id="REFAPP-OP-005",
            matched_template="/shipments/{shipment_id}/cancel",
            method="POST",
            spec_metadata="{}",
            disposition="deny",
        ),
        _row(
            decision_seq=2,
            resolved_tier="write",
            rule_id="REFAPP-OP-005",
            matched_template="/shipments/{shipment_id}/cancel",
            method="POST",
            spec_metadata="{}",
            disposition="deny",
        ),
    )
    exported = label_corpus(rows)
    assert [row.label for row in exported.rows] == [
        LABEL_WRITE_OBSERVED,
        LABEL_WRITE_OBSERVED,
    ]


# ---------------------------------------------------------------------------
# Not a model judge. Not a threshold. Not T214.


def test_the_oracle_does_not_import_the_shadow_judge() -> None:
    found: list[str] = []
    for path in (ORACLE, THIS):
        found.extend(_judge_imports(path))
    assert found == [], (
        "the state-diff oracle imported the shadow judge:\n  "
        + "\n  ".join(found)
    )
    assert module_source(), "the oracle's own text was not read"


def test_the_judge_import_scan_fires_on_a_planted_edge(tmp_path: Path) -> None:
    """The removal proof of effect_gate_oracle → src.runtime.judge."""
    planted = tmp_path / "effect_gate_oracle.py"
    planted.write_text("from src.runtime.judge.shadow import ShadowJudge\n")
    found: list[str] = []
    for imported in _imported(planted):
        for module in JUDGE_MODULES:
            if imported == module or imported.startswith(module + "."):
                found.append(imported)
    assert found, "the oracle→judge scan did not report a planted import"


def test_t181_stays_unset_and_writes_stay_blocked() -> None:
    assert T181_THRESHOLD_STAYS_UNSET is True
    assert precision.PER_CALL_THRESHOLD is precision.UNSET
    assert precision.write_capability_released() is False
    assert precision.MEASURED_AGAINST_LABELLED_CORPUS is False


def test_no_run_produces_a_result_t214_is_still_open() -> None:
    assert T214_RESIDUAL_NO_RUN_PRODUCES_A_RESULT is True
    imported = _imported(ORACLE)
    assert "src.contracts.result" not in imported
    assert "src.runtime.result_join" not in imported
    assert "src.runtime.serving" not in imported


def test_the_residual_is_recorded() -> None:
    record_evidence("fr041-effect-gate-oracle", {
        "requirement": "FR-041",
        "task": "T180",
        "labels": sorted(LABELS),
        "labelled_after_oracle": True,
        "threshold_stays_unset": T181_THRESHOLD_STAYS_UNSET,
        "t214_residual": T214_RESIDUAL_NO_RUN_PRODUCES_A_RESULT,
        "what_this_establishes": [
            "A call is labelled by snapshot, call, diff on a copy of "
            "the reference application's state.",
            "Unchanged state is read_only_correct; mutated state is "
            "write_observed.",
            "T179's exporter reports labelled=True once every row "
            "carries a T180 label.",
            "No shadow judge is consulted. T181's threshold stays unset.",
        ],
    })
