"""T153 — FR-051's ordinary successful-fetch increment, against T158.

## What has to be asserted here that "it inspected" would miss

T153 compares against the last **inspected** (clean) set, not the previous
fetch and not last-known-good. `add-then-republish-unchanged`'s third fetch
is empty; re-inspect-on-every-fetch fails it. `add-three-mixed-in-one-fetch`
requires the clean member to become available and the other two not to —
all-or-nothing either way fails it. `no-operation-added` is the Rule 8
negative control: refuse-everything satisfies "zero uninspected" on a corpus
made only of additions. `add-one-uninspectable` is the refusal clause's
subject; without it SC-026's third clause is 100% of zero.

The procedure is T079's. This file scores the increment, not the three steps.

SC-026 is conformance against a fixture derived from FR-051. U-44 remains:
the property is unmeasured. T158 is not coverage of inspection quality.
E13 never ran.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Iterable, Mapping

import pytest

from src.analysis import admission
from src.analysis.deputy_inspection import (
    ALLOWED_OUTCOMES,
    CLEAN,
    DEPUTY,
    UNINSPECTABLE,
    Codebase,
    DeputyInspectionError,
    InspectionReport,
    NotAdmittedForInspection,
    OperationOutcome,
    gate,
    inspect_operation,
)
from src.analysis.reinspect import (
    Reinspection,
    appearing,
    reinspect,
)
from tests.fixtures.drift_corpora import operation_added as add

MODULE = Path(__file__).resolve().parent.parent.parent / "src" / "analysis" / "reinspect.py"

BASELINE = (
    "health",
    "list_parts",
    "get_part",
    "list_shipments",
    "cancel_shipment",
)

#: Handlers that produce T158's declared outcomes via FR-056, not via a stub.
#: `list_warehouses` is clean (no outbound). `fetch_url` is deputy (destination
#: influenced by an input). `proxy_lookup` is uninspectable at step 3 (the
#: destination traces to neither a build-time constant nor the target's own
#: configuration) — matching the corpus `why`, not a step-1 missing handler.
_SOURCE = """
def health():
    pass
def list_parts():
    pass
def get_part():
    pass
def list_shipments():
    pass
def cancel_shipment():
    pass
def list_warehouses():
    pass
def fetch_url(url):
    requests.get(url)
def proxy_lookup():
    requests.get(unknown_url)
"""

CODEBASE = Codebase.from_sources({"app.py": _SOURCE})
HANDLER_INDEX: dict[str, str] = {
    "health": "health",
    "list_parts": "list_parts",
    "get_part": "get_part",
    "list_shipments": "list_shipments",
    "cancel_shipment": "cancel_shipment",
    "list_warehouses": "list_warehouses",
    "fetch_url": "fetch_url",
    "proxy_lookup": "proxy_lookup",
}


def _decision(
    operation_ids: Iterable[str],
    *,
    deployment_id: str = "d-reference-app",
) -> admission.AdmissionDecision:
    return admission.AdmissionDecision(
        deployment_id=deployment_id,
        admitted=True,
        state=admission.PUBLISHED_NON_EMPTY,
        criterion=admission.criterion_for(admission.PUBLISHED_NON_EMPTY),
        operations=tuple({"operation_id": op} for op in operation_ids),
        evidence="fixture",
        specification_source="file:///fixture",
    )


def _rejected(state: str) -> admission.AdmissionDecision:
    return admission.AdmissionDecision(
        deployment_id="d-reference-app",
        admitted=False,
        state=state,
        criterion=admission.criterion_for(state),
        operations=(),
        evidence="fixture",
        specification_source="file:///fixture",
    )


def _run(
    fetched: Iterable[str],
    last_inspected: Iterable[str],
    *,
    handler_index: Mapping[str, str] | None = None,
    codebase: Codebase | None = None,
) -> Reinspection:
    return reinspect(
        _decision(fetched),
        last_inspected=last_inspected,
        handler_index=HANDLER_INDEX if handler_index is None else handler_index,
        codebase=CODEBASE if codebase is None else codebase,
    )


def _play(scenario: add.Scenario) -> tuple[Reinspection, ...]:
    """Replay one T158 scenario, carrying the clean set forward."""
    last = frozenset(scenario.last_inspected)
    fetched = set(scenario.last_inspected)
    results: list[Reinspection] = []
    for newly in scenario.newly_appearing_per_fetch:
        fetched |= set(newly)
        result = _run(fetched, last)
        results.append(result)
        last = frozenset(result.report.available)
    return tuple(results)


# ---------------------------------------------------------------------------
# SC-026 against T158.
# ---------------------------------------------------------------------------


def test_every_operation_added_scenario_matches_the_loader() -> None:
    """The falsification instrument, scored against the increment."""
    for scenario in add.load_scenarios():
        results = _play(scenario)
        assert tuple(r.newly_appearing for r in results) == (
            scenario.newly_appearing_per_fetch
        ), scenario.scenario_id
        last = results[-1]
        assert tuple(sorted(last.report.available)) == scenario.available_at_end, (
            scenario.scenario_id
        )
        refused = tuple(sorted(
            op
            for result in results
            for op in result.report.denied
        ))
        assert refused == scenario.refused, scenario.scenario_id


def test_newly_appearing_operations_are_inspected_before_they_become_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Inspect before available: the procedure runs while the operation is
    still absent from the last inspected set, and the operation is in
    `report.available` only if the procedure returned a member of
    ALLOWED_OUTCOMES.

    Patch at the call site. `inspect_admission` would not go through this
    binding, so re-inspect-the-whole-set via T079 is visible as a call-list
    that does not equal the newly appearing set.
    """
    inspected: list[str] = []
    real = inspect_operation

    def at_call_site(
        operation_id: str,
        *,
        handler_index: Mapping[str, str],
        codebase: Codebase,
    ) -> OperationOutcome:
        inspected.append(operation_id)
        return real(
            operation_id, handler_index=handler_index, codebase=codebase
        )

    monkeypatch.setattr("src.analysis.reinspect.inspect_operation", at_call_site)

    for scenario in add.load_scenarios():
        inspected.clear()
        last = frozenset(scenario.last_inspected)
        fetched = set(scenario.last_inspected)
        for newly in scenario.newly_appearing_per_fetch:
            fetched |= set(newly)
            before = len(inspected)
            result = _run(fetched, last)
            called = inspected[before:]
            assert tuple(sorted(called)) == newly, scenario.scenario_id
            for op_id in newly:
                assert op_id not in last, (
                    f"{scenario.scenario_id}: {op_id} was already in the last "
                    "inspected set when it was inspected, so it was available "
                    "before the inspection"
                )
                if op_id in result.report.available:
                    assert result.report.outcome_for(op_id).outcome in ALLOWED_OUTCOMES
            last = frozenset(result.report.available)


def test_republishing_an_already_inspected_set_inspects_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T158's add-then-republish-unchanged third fetch. Re-inspect-everything
    fails this; compare-against-previous-fetch can pass it by luck.
    """
    called: list[str] = []
    real = inspect_operation

    def at_call_site(
        operation_id: str,
        *,
        handler_index: Mapping[str, str],
        codebase: Codebase,
    ) -> OperationOutcome:
        called.append(operation_id)
        return real(operation_id, handler_index=handler_index, codebase=codebase)

    monkeypatch.setattr("src.analysis.reinspect.inspect_operation", at_call_site)

    scenarios = {s.scenario_id: s for s in add.load_scenarios()}
    results = _play(scenarios["add-then-republish-unchanged"])
    assert results[2].newly_appearing == ()
    # First fetch inspects nothing; second inspects list_warehouses; third
    # inspects nothing. `called` is across the whole play.
    assert called == ["list_warehouses"]


def test_a_mixed_fetch_admits_the_clean_member_and_refuses_the_others() -> None:
    scenarios = {s.scenario_id: s for s in add.load_scenarios()}
    results = _play(scenarios["add-three-mixed-in-one-fetch"])
    last = results[-1]
    assert "list_warehouses" in last.report.available
    assert last.report.outcome_for("list_warehouses").outcome == CLEAN
    assert last.report.outcome_for("fetch_url").outcome == DEPUTY
    assert last.report.outcome_for("proxy_lookup").outcome == UNINSPECTABLE
    assert tuple(sorted(last.report.denied)) == ("fetch_url", "proxy_lookup")
    for op_id in BASELINE:
        assert op_id in last.report.available


def test_an_uninspectable_addition_is_refused_and_does_not_take_the_target_offline() -> None:
    """Fail closed per operation. The baseline stays available."""
    scenarios = {s.scenario_id: s for s in add.load_scenarios()}
    results = _play(scenarios["add-one-uninspectable"])
    last = results[-1]
    assert "proxy_lookup" not in last.report.available
    assert last.report.outcome_for("proxy_lookup").outcome == UNINSPECTABLE
    for op_id in BASELINE:
        assert op_id in last.report.available
    gate(last.report, "health")
    with pytest.raises(DeputyInspectionError):
        gate(last.report, "proxy_lookup")


def test_pre_existing_operations_stay_available_when_nothing_is_added() -> None:
    """Rule 8: refuse-everything satisfies 'zero uninspected' otherwise."""
    scenarios = {s.scenario_id: s for s in add.load_scenarios()}
    results = _play(scenarios["no-operation-added"])
    for result in results:
        assert result.newly_appearing == ()
        assert tuple(sorted(result.report.available)) == tuple(sorted(BASELINE))
        assert result.report.denied == ()


def test_appearing_is_fetched_minus_the_clean_set_not_the_previous_fetch() -> None:
    fetched = {*BASELINE, "list_warehouses"}
    last_inspected = {*BASELINE, "list_warehouses"}
    assert appearing(fetched, last_inspected) == ()
    assert appearing(fetched, BASELINE) == ("list_warehouses",)


# ---------------------------------------------------------------------------
# Stage boundary, layering, residuals.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "state", sorted(set(admission.STATES) - admission.ADMISSIBLE_STATES)
)
def test_a_non_admissible_fetch_is_refused(state: str) -> None:
    """T153 runs on a successful fetch. A failed re-fetch is T140/T147."""
    with pytest.raises(NotAdmittedForInspection) as raised:
        reinspect(
            _rejected(state),
            last_inspected=BASELINE,
            handler_index=HANDLER_INDEX,
            codebase=CODEBASE,
        )
    assert "successful fetch" in str(raised.value)
    assert "T140/T147" in str(raised.value)


def test_an_uninspectable_operation_is_inspected_again_on_a_later_fetch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Disposition: re-run, because last inspected is the clean set.

    T158 plants no scenario that forces this. FR-051 forbids treating an
    uninspectable operation as inspected; re-running follows from that
    definition. Silent re-admission is still impossible: availability is
    still ALLOWED_OUTCOMES.
    """
    called: list[str] = []
    real = inspect_operation

    def at_call_site(
        operation_id: str,
        *,
        handler_index: Mapping[str, str],
        codebase: Codebase,
    ) -> OperationOutcome:
        called.append(operation_id)
        return real(operation_id, handler_index=handler_index, codebase=codebase)

    monkeypatch.setattr("src.analysis.reinspect.inspect_operation", at_call_site)

    fetched = [*BASELINE, "proxy_lookup"]
    first = _run(fetched, BASELINE)
    assert first.newly_appearing == ("proxy_lookup",)
    assert "proxy_lookup" not in first.report.available
    second = _run(fetched, first.report.available)
    assert second.newly_appearing == ("proxy_lookup",)
    assert "proxy_lookup" not in second.report.available
    assert called == ["proxy_lookup", "proxy_lookup"]


def test_operation_outcome_does_not_carry_a_handler_symbol() -> None:
    """Residual: the inspected-set key is the operation identifier.

    FR-051 says a handler change is not 'already inspected' just because the
    spec entry did not change. OperationOutcome has no handler/symbol field,
    and this module does not invent a second inspection identity.
    """
    fields = OperationOutcome.__dataclass_fields__
    assert "handler" not in fields
    assert "symbol" not in fields
    assert "handler_index" not in fields


def test_the_increment_does_not_call_inspect_admission() -> None:
    source = MODULE.read_text()
    tree = ast.parse(source, filename=str(MODULE))
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == "inspect_admission":
            raise AssertionError(
                "reinspect.py must not call inspect_admission; that is the "
                "full-set admission path (T079, T152), and T158's "
                "add-then-republish-unchanged exists to catch it"
            )
        if isinstance(node, ast.Name) and node.id == "compare_each":
            raise AssertionError("compare_each is T137's two-clock form, not this")
        if isinstance(node, ast.Name) and node.id in {"compare", "signals_from_movements"}:
            raise AssertionError("T151's drift evaluation is not this module")


def test_analysis_does_not_import_runtime_or_staleness() -> None:
    source = MODULE.read_text()
    tree = ast.parse(source, filename=str(MODULE))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    for name in imported:
        assert not name.startswith("src.runtime"), name
        assert "staleness" not in name


def test_no_http_client_no_target_credential_no_clock() -> None:
    source = MODULE.read_text()
    for needle in (
        "urllib",
        "http.client",
        "requests",
        "Authorization",
        "Date.now",
        "time.time",
        "datetime",
    ):
        assert needle not in source


def test_a_carried_clean_operation_is_not_a_replay_of_the_procedure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called: list[str] = []
    real = inspect_operation

    def at_call_site(
        operation_id: str,
        *,
        handler_index: Mapping[str, str],
        codebase: Codebase,
    ) -> OperationOutcome:
        called.append(operation_id)
        return real(operation_id, handler_index=handler_index, codebase=codebase)

    monkeypatch.setattr("src.analysis.reinspect.inspect_operation", at_call_site)
    result = _run(BASELINE, BASELINE)
    assert called == []
    assert tuple(sorted(result.report.available)) == tuple(sorted(BASELINE))
    assert result.newly_appearing == ()


def test_report_available_is_the_clean_set_and_only_the_clean_set() -> None:
    """Do not invent a second available vocabulary."""
    result = _run([*BASELINE, "list_warehouses", "fetch_url"], BASELINE)
    assert result.report.available == tuple(
        o.operation_id for o in result.report.outcomes if not o.denied
    )
    assert "list_warehouses" in result.report.available
    assert "fetch_url" not in result.report.available
    assert isinstance(result.report, InspectionReport)
