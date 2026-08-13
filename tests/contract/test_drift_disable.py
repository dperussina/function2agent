"""T146 — disable the observed affected operation (FR-030, SC-009).

## What has to be asserted here that a "it returned a Disablement" test would miss

SC-009 is 100% of withdrawn operations **detected and disabled**, and zero
unaffected disabled. T155's detection half is already scored. This file
scores the disable half. Detection without disablement does not close it.

The oracle is the loader's `withdrawn` / `unaffected` / `expected_disabled`,
not a second withdrawn-operation classifier. Consecutive served-id sets
are what the movement was built from; `withdrawn_from_served` is the same
set difference the loader already derives.

Cheap detectors this corpus exists to fail, planted as tests so Rule 8
can fire:

- disable the target on every poll — `no-withdrawal`
- disable the whole target on a bulk withdrawal — `health` must stay up
- match on a name prefix — `list_shipments` vs `list_parts`

`FailedRefetch` disables nothing: T147 marks stale, T150 denies at the
ceiling. This is not a second deny-all. A source-clock `ArtifactDrift`
that cannot name an operation disables nothing and does not disable the
target. T154 has no `expected_disabled`.
"""

from __future__ import annotations

import ast
import json
import inspect
from pathlib import Path

import pytest

from src.analysis.admission import ABSENT
from src.analysis.clocks import DEPLOYMENT, SOURCE, compare, deployment_reading
from src.analysis.drift_signal import ArtifactDrift, failed_refetch, signals_from_movements
from src.analysis.source_drift import detect
from src.runtime.drift.disable import (
    NO_NAMED_OPERATION,
    NOTHING_DISABLED,
    DisableError,
    Disablement,
    disable,
    disablements_of,
    remaining,
    withdrawn_from_served,
)
from src.runtime.drift.scheduler import PATH_LEVEL_PROBE
from tests.contract.test_drift_scheduler import LAST_OK, OPS_BY_ID, _ops, _reading
from tests.contract.test_source_drift import _both, _by_id
from tests.fixtures.drift_corpora import deployment as dep
from tests.fixtures.drift_corpora import source as src

REPO = Path(__file__).resolve().parents[2]
MODULE = REPO / "src" / "runtime" / "drift" / "disable.py"
ORIGIN = "http://203.0.113.10:443"
FETCHED_AT = "2026-08-13T00:00:00Z"


def _raw_deployment_scenarios() -> list[dict]:
    return json.loads(dep.CORPUS_FILE.read_text())["scenarios"]


def _sets_of(scenario):
    before = sorted(scenario.served_before)
    after = sorted(scenario.served_before - set(scenario.withdrawn))
    return before, after


def _deployment_signals(before: list[str], after: list[str], *, deployment_id: str):
    movement = compare(
        _reading(before, deployment_id=deployment_id),
        _reading(after, deployment_id=deployment_id),
    )
    return signals_from_movements((movement,))


def _disabled_ids(records: tuple[Disablement, ...]) -> tuple[str, ...]:
    return tuple(sorted({op for record in records for op in record.disabled}))


# ---------------------------------------------------------------------------
# SC-009 against T155. Disablement, not detection.


def test_sc009_disables_exactly_the_withdrawn_operations() -> None:
    """100% withdrawn disabled, zero unaffected disabled. Five scenarios."""
    raw = {entry["scenario_id"]: entry for entry in _raw_deployment_scenarios()}
    scored = []
    for scenario in dep.load_scenarios():
        before, after = _sets_of(scenario)
        signals = _deployment_signals(
            before, after, deployment_id=scenario.deployment_id
        )
        records = disablements_of(
            signals, served_before=before, served_after=after
        )
        disabled = _disabled_ids(records)
        expected = tuple(sorted(raw[scenario.scenario_id]["expected_disabled"]))
        remain = tuple(sorted(raw[scenario.scenario_id]["expected_remain_enabled"]))
        assert disabled == expected
        assert disabled == scenario.withdrawn
        assert remain == scenario.unaffected
        for operation_id in scenario.unaffected:
            assert operation_id not in disabled
        if records:
            kept = remaining(before, records[0])
            assert kept == scenario.unaffected
            loud = records[0].loudly()
            for operation_id in disabled:
                assert operation_id in loud
            for operation_id in scenario.unaffected:
                assert operation_id not in loud
        else:
            assert records == NOTHING_DISABLED
            assert disabled == ()
        scored.append(scenario.scenario_id)
    figures = dep.counts()
    assert len(scored) == figures["scenarios_total"]
    assert figures["scenarios_with_nothing_withdrawn"] == 1
    assert figures["scenarios_carrying_a_withdrawal"] == 4


def test_the_negative_control_disables_nothing() -> None:
    """Rule 8: disable-the-target-on-every-poll fails no-withdrawal."""
    scenario = next(s for s in dep.load_scenarios() if s.is_negative_control)
    before, after = _sets_of(scenario)
    assert before == after
    assert withdrawn_from_served(before, after) == ()
    signals = _deployment_signals(
        before, after, deployment_id=scenario.deployment_id
    )
    assert signals == ()
    records = disablements_of(signals, served_before=before, served_after=after)
    assert records == NOTHING_DISABLED
    assert _disabled_ids(records) == ()


def test_bulk_withdrawal_leaves_health_enabled() -> None:
    """Disable-the-whole-target fails the bulk scenario."""
    scenario = next(
        s for s in dep.load_scenarios() if s.scenario_id == "withdraw-all-but-one"
    )
    before, after = _sets_of(scenario)
    signals = _deployment_signals(
        before, after, deployment_id=scenario.deployment_id
    )
    records = disablements_of(signals, served_before=before, served_after=after)
    disabled = _disabled_ids(records)
    assert "health" not in disabled
    assert "health" in scenario.unaffected
    assert remaining(before, records[0]) == ("health",)


def test_a_prefix_match_cannot_take_the_neighbour() -> None:
    """list_shipments goes, list_parts stays."""
    scenario = next(
        s
        for s in dep.load_scenarios()
        if s.scenario_id == "withdraw-one-of-two-neighbours"
    )
    before, after = _sets_of(scenario)
    signals = _deployment_signals(
        before, after, deployment_id=scenario.deployment_id
    )
    records = disablements_of(signals, served_before=before, served_after=after)
    disabled = _disabled_ids(records)
    assert disabled == ("list_shipments",)
    assert "list_parts" not in disabled
    assert "list_parts" in remaining(before, records[0])


# ---------------------------------------------------------------------------
# FailedRefetch: no member. T147 / T150 own that case.


def test_a_failed_refetch_disables_no_operation() -> None:
    """Even when consecutive sets look like a total withdrawal."""
    served = list(OPS_BY_ID)
    signal = failed_refetch(
        deployment_reading(deployment_id="d-reference-app", operations=_ops(served)),
        specification_state=ABSENT,
        last_successful_fetch=FETCHED_AT,
    )
    record = disable(signal, served_before=served, served_after=())
    assert record.disabled == ()
    assert remaining(served, record) == tuple(served)


def test_disable_does_not_import_the_ceiling_deny_path() -> None:
    tree = ast.parse(MODULE.read_text(), filename=str(MODULE))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    assert "src.runtime.staleness" not in imported
    called = {
        node.attr if isinstance(node, ast.Attribute) else node.id
        for node in ast.walk(tree)
        if isinstance(node, (ast.Name, ast.Attribute))
    }
    assert "may_serve" not in called
    assert "deny_call" not in called
    assert "in_flight_terminal" not in called


# ---------------------------------------------------------------------------
# Source clock. T154 has no expected_disabled. Named operations only.


def _detect_inputs(revision):
    parent = _by_id()[revision.parent]
    return dict(
        before=_both(parent.contract),
        after=_both(revision.contract),
        before_contracts=parent.contract,
        after_contracts=revision.contract,
        renamed=revision.renamed,
    )


def test_source_clock_disables_only_named_drifted_operations() -> None:
    """If Invalidation names operations, disable those and only those."""
    for revision in src.load_revisions():
        if not revision.breaking:
            continue
        finding = detect(**_detect_inputs(revision))
        assert finding is not None
        record = disable(finding.signal, source_finding=finding)
        assert record.disabled == revision.drifted_operations
        assert record.signal.clock == SOURCE
        assert record.signal.clock != DEPLOYMENT


def test_c010_does_not_disable_the_non_breaking_half() -> None:
    revision = next(r for r in src.load_revisions() if r.revision_id == "C-010")
    finding = detect(**_detect_inputs(revision))
    assert finding is not None
    record = disable(finding.signal, source_finding=finding)
    assert record.disabled == ("list_all_shipments",)
    assert "list_parts" not in record.disabled
    assert "health" not in record.disabled


def test_a_source_signal_that_cannot_name_an_operation_disables_nothing() -> None:
    """ArtifactDrift names kinds, not operations. Do not invent; do not disable the target."""
    revision = next(r for r in src.load_revisions() if r.breaking)
    finding = detect(**_detect_inputs(revision))
    assert finding is not None
    record = disable(finding.signal)
    assert record.disabled == NO_NAMED_OPERATION
    assert record.disabled == ()


def test_non_breaking_source_revisions_have_no_finding_to_disable() -> None:
    for revision in src.load_revisions():
        if revision.parent is None or revision.breaking:
            continue
        finding = detect(**_detect_inputs(revision))
        assert finding is None


# ---------------------------------------------------------------------------
# Refusals. Each arm reaches exactly one guard.


def test_deployment_artifact_drift_without_served_sets_is_refused() -> None:
    before = ["health", "cancel_shipment"]
    after = ["health"]
    signals = _deployment_signals(before, after, deployment_id="d-reference-app")
    assert len(signals) == 1
    with pytest.raises(DisableError, match="consecutive served-id sets"):
        disable(signals[0])


def test_a_finding_for_the_wrong_deployment_is_refused() -> None:
    revision = next(r for r in src.load_revisions() if r.breaking)
    finding = detect(**_detect_inputs(revision))
    assert finding is not None
    other = ArtifactDrift(
        clock=SOURCE,
        deployment_id="d-other",
        version_before=finding.signal.version_before,
        version_after=finding.signal.version_after,
        kinds_moved=finding.signal.kinds_moved,
    )
    with pytest.raises(DisableError, match="mixing two identities"):
        disable(other, source_finding=finding)


# ---------------------------------------------------------------------------
# Loud record. No logger. Not wired.


def test_loudly_names_the_disabled_and_not_the_unaffected() -> None:
    scenario = next(
        s for s in dep.load_scenarios() if s.scenario_id == "withdraw-one-operation"
    )
    before, after = _sets_of(scenario)
    signals = _deployment_signals(
        before, after, deployment_id=scenario.deployment_id
    )
    record = disable(signals[0], served_before=before, served_after=after)
    assert isinstance(record, Disablement)
    line = record.loudly()
    assert "cancel_shipment" in line
    assert "list_parts" not in line
    assert record.deployment_id in line


def test_disable_does_not_accept_a_trigger() -> None:
    assert "trigger" not in inspect.signature(disable).parameters
    assert PATH_LEVEL_PROBE not in MODULE.read_text()


def test_the_module_does_not_open_a_client_or_reclassify() -> None:
    tree = ast.parse(MODULE.read_text(), filename=str(MODULE))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    assert "urllib.request" not in imported
    assert "src.analysis.admission" not in imported
    assert "src.runtime.staleness" not in imported
    assert "src.runtime.drift.scheduler" not in imported
    assert "logging" not in imported
    text = MODULE.read_text()
    for banned in ("urlopen", "HTTPConnection", "HTTPSConnection", "httpx", "requests"):
        assert banned not in text, banned
    assert ORIGIN not in text
    called = {
        node.attr if isinstance(node, ast.Attribute) else node.id
        for node in ast.walk(tree)
        if isinstance(node, (ast.Name, ast.Attribute))
    }
    assert "tick" not in called
    assert "fetch" not in called
    assert "getLogger" not in called
    assert "may_serve" not in called
    assert "deny_call" not in called
    assert "drifted_operations" not in called
    assert "compare_each" not in called
    assert "withdrawn_from_served" in called


def test_disablement_is_not_wired_to_a_serve_loop() -> None:
    """OD-36: the function exists; loop.py / runner.py / main.py do not call it."""
    for relative in (
        "src/runtime/loop.py",
        "src/runtime/runner.py",
        "src/runtime/main.py",
        "src/runtime/serving.py",
    ):
        text = (REPO / relative).read_text()
        assert "Disablement" not in text, relative
        assert "src.runtime.drift.disable" not in text, relative
        assert "withdrawn_from_served" not in text, relative
