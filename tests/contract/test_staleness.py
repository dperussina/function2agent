"""T147–T152 — the stale last-known-good set, against T157's fixture.

## What has to be asserted here that "it marked stale" would miss

T147's domain is five states where FR-047's sentence says three. A suite that
only entered on `absent` would leave `unreachable` (the state that decided
T140, and that `withdraw-past-ceiling` exercises) and `unparseable`
unwatched. `spec_withdrawn.non_admissible_states_exercised()` reports the
three and **excludes `unreachable`**, so it is not this module's entering
domain — the classifier minus admissible is.

T148 stamps `Result.staleness` via `replace`, not a fourth verification
value and not a `Result(` construction. T149's age is wall-clock from the
last successful fetch; measuring from entry, or comparing against 3600,
would serve T157's past-ceiling calls. T150 names
`terminated.staleness_ceiling_reached`, not `terminated.unrecoverable_fault`.
T151's identical restoration is the negative control. T152 is admission,
not tick, and is a function: there is no serve loop (OD-36).

SC-021 is scored against this fixture as conformance to FR-047. It is not
evidence the disposition is right. E13 never ran.
"""

from __future__ import annotations

import ast
import datetime as dt
import json
from pathlib import Path
from typing import Any, Mapping

import pytest

from src.analysis.admission import (
    ABSENT,
    FetchResponse,
    UNPARSEABLE,
    UNREACHABLE,
    UNREADABLE_BY_CREDENTIAL,
)
from src.analysis.deputy_inspection import Codebase
from src.analysis.drift_signal import (
    SPECIFICATION_STATE_FOUND,
    ArtifactDrift,
    FailedRefetch,
)
from src.contracts import terminal
from src.contracts.config import SUPERVISOR_KEYS
from src.contracts.result import (
    STALENESS_NOT_STATED,
    Corroboration,
    Result,
    StaleMarking,
    VerificationOutcome,
)
from src.contracts.transition import ST_STALENESS_CEILING
from src.runtime.drift.scheduler import CheckResult
from src.runtime.staleness import (
    CEILING_DENIAL_RULE,
    DEFAULT_CEILING_SECONDS,
    ENTERING_STATES,
    Ceiling,
    CeilingDenial,
    Restore,
    StaleSet,
    StalenessError,
    crossed,
    deny_call,
    enter,
    in_flight_terminal,
    mark_result,
    may_serve,
    observe,
    recover,
    restore,
)
from tests.contract.test_drift_scheduler import (
    DEPLOYMENT_ID,
    ENFORCEMENT,
    LAST_OK,
    OPS_BY_ID,
    ScriptedTransport,
    _absent,
    _body,
    _published,
    _reading,
    _scheduler,
    _unreachable,
)
from tests.fixtures.drift_corpora import spec_withdrawn as withdrawn

REPO = Path(__file__).resolve().parents[2]
MODULE = REPO / "src" / "runtime" / "staleness.py"
CEILING_SECONDS = withdrawn.staleness_ceiling_seconds()


def _epoch(instant: str) -> float:
    text = instant[:-1] + "+00:00" if instant.endswith("Z") else instant
    parsed = dt.datetime.fromisoformat(text)
    assert parsed.tzinfo is not None
    return parsed.timestamp()


def _ceiling(deployment_id: str = DEPLOYMENT_ID, seconds: float = CEILING_SECONDS) -> Ceiling:
    return Ceiling(seconds=seconds, deployment_id=deployment_id)


def _verified() -> Result:
    return Result(
        VerificationOutcome.VERIFIED,
        payload={"ok": True},
        corroboration=Corroboration.CORROBORATED,
    )


def _op(oid: str) -> dict[str, Any]:
    if oid in OPS_BY_ID:
        return OPS_BY_ID[oid]
    template = next(iter(OPS_BY_ID.values()))
    return {**template, "operation_id": oid}


def _published_any(ids: list[str], *, peer: str = ENFORCEMENT) -> ScriptedTransport:
    return ScriptedTransport(
        peer=peer,
        status=200,
        body=json.dumps({"operations": [_op(i) for i in ids]}).encode(),
    )


def _unreadable(*, peer: str = ENFORCEMENT) -> ScriptedTransport:
    return ScriptedTransport(peer=peer, status=403, body=None)


def _empty_ops(*, peer: str = ENFORCEMENT) -> ScriptedTransport:
    return ScriptedTransport(
        peer=peer, status=200, body=json.dumps({"operations": []}).encode()
    )


def _unparseable(*, peer: str = ENFORCEMENT) -> ScriptedTransport:
    return ScriptedTransport(peer=peer, status=200, body=b"not a specification")


def _transport_for(fetch: dict[str, Any]) -> ScriptedTransport:
    state = fetch["state"]
    if state == "published_non_empty":
        return _published_any(list(fetch["operations"]))
    if state == "absent":
        return _absent()
    if state == "unreachable":
        return _unreachable()
    if state == "unreadable_by_credential":
        return _unreadable()
    if state == "readable_no_operations":
        return _empty_ops()
    if state == "unparseable":
        return _unparseable()
    raise AssertionError(f"no transport for {state!r}")


def _raw_scenarios() -> dict[str, Any]:
    return {s["scenario_id"]: s for s in json.loads(withdrawn.CORPUS_FILE.read_text())["scenarios"]}


def _play(scenario_id: str) -> tuple[StaleSet | Restore | None, list[CheckResult]]:
    """Drive T141's ticker through a T157 scenario, then T147's observer."""
    raw = _raw_scenarios()[scenario_id]
    fetches = raw["fetches"]
    first = fetches[0]
    scheduler = _scheduler(
        _published(list(first["operations"])),
        last_ids=list(raw["last_known_good"]),
        last_successful_fetch=first["at"],
        deployment_id=raw["deployment_id"],
    )
    ceiling = _ceiling(raw["deployment_id"])
    state: StaleSet | None = None
    last: StaleSet | Restore | None = None
    checks: list[CheckResult] = []
    for fetch in fetches[1:]:
        scheduler._transport = _transport_for(fetch)
        check = scheduler.tick(now=fetch["at"])
        checks.append(check)
        last = observe(state, check, now=_epoch(fetch["at"]), ceiling=ceiling)
        state = None if isinstance(last, Restore) or last is None else last
    return last, checks


def _enter_on(transport: ScriptedTransport, *, last_ids: list[str] | None = None) -> StaleSet:
    scheduler = _scheduler(transport, last_ids=last_ids)
    check = scheduler.tick(now="2026-08-13T00:05:00Z")
    return enter(check, ceiling=_ceiling())


# ---------------------------------------------------------------------------
# T147 — entering. Five states, residual against FR-047's three.


def test_entering_states_are_the_classifier_minus_admissible() -> None:
    assert ENTERING_STATES == SPECIFICATION_STATE_FOUND
    assert "published_non_empty" not in ENTERING_STATES
    assert {ABSENT, UNREADABLE_BY_CREDENTIAL, UNREACHABLE, UNPARSEABLE} <= ENTERING_STATES
    assert withdrawn.non_admissible_states_exercised() < ENTERING_STATES
    assert UNREACHABLE not in withdrawn.non_admissible_states_exercised()
    assert UNREACHABLE in ENTERING_STATES


def test_the_first_absent_refetch_marks_the_set_stale_rather_than_discarding_it() -> None:
    scheduler = _scheduler(_absent())
    check = scheduler.tick(now="2026-08-13T00:05:00Z")
    assert isinstance(check.signals[0], FailedRefetch)
    stale = enter(check, ceiling=_ceiling())
    assert stale.last_successful_fetch == LAST_OK
    assert stale.last_successful == check.last_successful
    assert stale.specification_state == ABSENT
    assert stale.entering_signal is check.signals[0]
    assert not hasattr(stale.entering_signal, "version_after")


def test_unreachable_enters_stale_on_the_same_rule_as_absent() -> None:
    """The five-vs-three disposition, as a firing arm.

    A three-member ENTERING_STATES cannot represent a first re-fetch that
    returns `unreachable`. T157's `withdraw-past-ceiling` later fetches are
    that state; this arm is the first-fetch case the corpus does not isolate.
    """
    stale = _enter_on(_unreachable())
    assert stale.specification_state == UNREACHABLE
    assert stale.last_successful_fetch == LAST_OK


def test_unparseable_enters_stale_on_the_same_rule_as_absent() -> None:
    stale = _enter_on(_unparseable())
    assert stale.specification_state == UNPARSEABLE


def test_all_three_of_fr044s_non_admissible_states_enter() -> None:
    assert _enter_on(_absent()).specification_state == ABSENT
    assert _enter_on(_unreadable()).specification_state == UNREADABLE_BY_CREDENTIAL
    assert _enter_on(_empty_ops()).specification_state == "readable_no_operations"


def test_an_admissible_check_does_not_enter_stale() -> None:
    served = list(OPS_BY_ID)
    check = _scheduler(_published(served), last_ids=served).tick(now=LAST_OK)
    with pytest.raises(StalenessError, match="no failed re-fetch"):
        enter(check, ceiling=_ceiling())
    assert observe(None, check, now=_epoch(LAST_OK), ceiling=_ceiling()) is None


# ---------------------------------------------------------------------------
# T148 — caller-visible marking. Separate field, snapshot age.


def test_a_verified_result_can_be_stale() -> None:
    stale = _enter_on(_absent())
    marked = mark_result(
        _verified(), stale, now=_epoch(LAST_OK) + 360.0, ceiling=_ceiling()
    )
    assert marked.is_verified
    assert marked.is_stale
    assert marked.staleness.marking is StaleMarking.STALE
    assert marked.staleness.age_seconds == pytest.approx(360.0)
    assert marked.staleness.specification_state == ABSENT
    assert marked.verification is VerificationOutcome.VERIFIED


def test_silence_is_not_stamped_fresh() -> None:
    result = _verified()
    assert result.staleness is STALENESS_NOT_STATED
    out = mark_result(result, None, now=0.0, ceiling=_ceiling())
    assert out.staleness.marking is StaleMarking.NOT_STATED
    assert out is result


def test_mark_result_past_the_ceiling_is_refused() -> None:
    stale = _enter_on(_absent())
    with pytest.raises(StalenessError, match="forbids serving"):
        mark_result(
            _verified(), stale, now=_epoch(LAST_OK) + 1260.0, ceiling=_ceiling()
        )


def test_the_producer_does_not_construct_a_result() -> None:
    tree = ast.parse(MODULE.read_text(), filename=str(MODULE))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id != "Result", (
                "T148 stamps via dataclasses.replace; a Result( construction "
                "here would be a second runtime site INV-001 forbids"
            )


# ---------------------------------------------------------------------------
# T149 — wall-clock from last successful fetch. Crossed is `>`.


def test_the_declared_default_is_fifteen_minutes_not_an_hour() -> None:
    key = next(k for k in SUPERVISOR_KEYS if k.name == "STALENESS_CEILING_SECONDS")
    assert key.default == "900.0"
    assert key.unvalidated is True
    assert key.requirement == "FR-047"
    assert DEFAULT_CEILING_SECONDS == 900.0
    assert float(key.default) == DEFAULT_CEILING_SECONDS
    assert CEILING_SECONDS == 900


def test_age_is_measured_from_the_last_successful_fetch_not_from_entry() -> None:
    """T157's distinction, executed against this module.

    Last successful fetch 02:00, stale entered 02:05, call 02:16. Age from
    the successful fetch is 960 s (deny). Age from entry is 660 s (serve).
    """
    last, _ = _play("withdraw-past-ceiling")
    assert isinstance(last, StaleSet)
    ceiling = _ceiling(last.deployment_id)
    deny_at = _epoch("2026-08-14T02:16:00Z")
    assert last.age_seconds(deny_at) == pytest.approx(960.0)
    assert last.last_successful_fetch == "2026-08-14T02:00:00Z"
    assert crossed(last.age_seconds(deny_at), ceiling.seconds)
    assert not may_serve(last, now=deny_at, ceiling=ceiling)


def test_exactly_at_the_ceiling_is_still_served_marked_stale() -> None:
    """`>` not `>=`. T157 plants no call at 900 s; this is the statement."""
    stale = _enter_on(_absent())
    now = _epoch(LAST_OK) + 900.0
    ceiling = _ceiling()
    assert not crossed(stale.age_seconds(now), ceiling.seconds)
    assert may_serve(stale, now=now, ceiling=ceiling)
    marked = mark_result(_verified(), stale, now=now, ceiling=ceiling)
    assert marked.is_stale
    assert marked.staleness.age_seconds == pytest.approx(900.0)


def test_a_call_at_960s_is_denied_against_a_900s_ceiling() -> None:
    stale = _enter_on(_absent())
    now = _epoch(LAST_OK) + 960.0
    ceiling = _ceiling()
    assert not may_serve(stale, now=now, ceiling=ceiling)
    denial = deny_call(stale, now=now, ceiling=ceiling, operation_id="get_part")
    assert isinstance(denial, CeilingDenial)
    assert denial.age_seconds == pytest.approx(960.0)
    assert denial.rule_id == CEILING_DENIAL_RULE == ST_STALENESS_CEILING.rule_id


def test_lengthening_the_interval_does_not_widen_the_ceiling() -> None:
    source = MODULE.read_text()
    assert "interval_seconds" not in source
    assert "DRIFT_CHECK_INTERVAL" in source  # named as what must not widen it
    stale = _enter_on(_absent())
    now = _epoch(LAST_OK) + 960.0
    assert crossed(stale.age_seconds(now), 900.0)
    # A four-times-longer interval (the 3600 default this slice removed) would
    # still have to deny: the ceiling is not a tick count.
    assert crossed(stale.age_seconds(now), 900.0)


def test_the_module_does_not_read_the_clock() -> None:
    tree = ast.parse(MODULE.read_text(), filename=str(MODULE))
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in {"now", "time"}:
            if isinstance(node.value, ast.Name) and node.value.id in {"dt", "datetime", "time"}:
                raise AssertionError(f"staleness.py reads the clock: {ast.dump(node)}")


def test_a_non_positive_ceiling_is_refused() -> None:
    with pytest.raises(StalenessError, match="not a positive duration"):
        Ceiling(seconds=0.0, deployment_id=DEPLOYMENT_ID)
    with pytest.raises(StalenessError, match="not a positive duration"):
        crossed(1.0, 0.0)


# ---------------------------------------------------------------------------
# T150 — deny past the ceiling; named terminal; functions, not a loop.


def test_calls_past_the_ceiling_are_denied() -> None:
    raw = _raw_scenarios()["withdraw-past-ceiling"]
    scenario = next(
        s for s in withdrawn.load_scenarios() if s.scenario_id == "withdraw-past-ceiling"
    )
    fetches = raw["fetches"]
    first = fetches[0]
    scheduler = _scheduler(
        _published(list(first["operations"])),
        last_ids=list(raw["last_known_good"]),
        last_successful_fetch=first["at"],
        deployment_id=raw["deployment_id"],
    )
    ceiling = _ceiling(raw["deployment_id"])
    state: StaleSet | None = None
    fetch_i = 1
    for call in scenario.calls:
        while fetch_i < len(fetches) and fetches[fetch_i]["at"] <= call.at:
            scheduler._transport = _transport_for(fetches[fetch_i])
            check = scheduler.tick(now=fetches[fetch_i]["at"])
            obs = observe(
                state, check, now=_epoch(fetches[fetch_i]["at"]), ceiling=ceiling
            )
            state = None if isinstance(obs, Restore) or obs is None else obs
            fetch_i += 1
        assert isinstance(state, StaleSet)
        now = _epoch(call.at)
        if call.served:
            assert may_serve(state, now=now, ceiling=ceiling)
            marked = mark_result(_verified(), state, now=now, ceiling=ceiling)
            assert marked.is_stale
            assert (
                marked.staleness.specification_state
                == call.specification_state_last_found
            )
            assert marked.staleness.age_seconds == pytest.approx(call.age_seconds)
        else:
            assert not may_serve(state, now=now, ceiling=ceiling)
            denial = deny_call(
                state, now=now, ceiling=ceiling, operation_id=call.operation_id
            )
            assert denial.age_seconds == pytest.approx(call.age_seconds)
            assert denial.specification_state == call.specification_state_last_found
            assert denial.set_version == state.last_successful.version
            with pytest.raises(StalenessError, match="forbids serving"):
                mark_result(_verified(), state, now=now, ceiling=ceiling)


def test_deny_below_the_ceiling_is_refused() -> None:
    stale = _enter_on(_absent())
    with pytest.raises(StalenessError, match="FR-030 has no member"):
        deny_call(
            stale,
            now=_epoch(LAST_OK) + 360.0,
            ceiling=_ceiling(),
            operation_id="get_part",
        )


def test_in_flight_terminal_names_the_staleness_ceiling_not_a_generic_fault() -> None:
    last, _ = _play("withdraw-past-ceiling")
    assert isinstance(last, StaleSet)
    named = in_flight_terminal(
        last, now=_epoch("2026-08-14T02:16:00Z"), ceiling=_ceiling(last.deployment_id)
    )
    assert named is terminal.STALENESS_CEILING
    assert named.name == "terminated.staleness_ceiling_reached"
    assert named.requirement == "FR-047"
    assert named is not terminal.UNRECOVERABLE_FAULT
    assert "stale" in named.name
    fr005 = {s.name for s in terminal.TAXONOMY if s.requirement == "FR-005"}
    assert named.name not in fr005


def test_in_flight_terminal_below_the_ceiling_is_refused() -> None:
    stale = _enter_on(_absent())
    with pytest.raises(StalenessError, match="first-failed-re-fetch"):
        in_flight_terminal(
            stale, now=_epoch(LAST_OK) + 360.0, ceiling=_ceiling()
        )


def test_never_withdrawn_marks_nothing_stale() -> None:
    last, checks = _play("never-withdrawn")
    assert last is None
    assert all(c.signals == () for c in checks)
    for call in next(
        s for s in withdrawn.load_scenarios() if s.scenario_id == "never-withdrawn"
    ).calls:
        assert not call.stale
        marked = mark_result(_verified(), None, now=_epoch(call.at), ceiling=_ceiling())
        assert not marked.is_stale


# ---------------------------------------------------------------------------
# T151 — restore below the ceiling evaluates the difference as drift.


def test_identical_restore_below_the_ceiling_is_zero_drift() -> None:
    last, _ = _play("withdraw-restore-identical-below-ceiling")
    assert isinstance(last, Restore)
    assert last.signals == ()
    assert last.last_successful_fetch == "2026-08-14T00:12:00Z"


def test_changed_restore_below_the_ceiling_is_deployment_clock_drift() -> None:
    last, _ = _play("withdraw-restore-changed-below-ceiling")
    assert isinstance(last, Restore)
    assert last.signals
    assert all(isinstance(s, ArtifactDrift) for s in last.signals)
    assert all(s.clock == "deployment" for s in last.signals)
    scenario = next(
        s
        for s in withdrawn.load_scenarios()
        if s.scenario_id == "withdraw-restore-changed-below-ceiling"
    )
    assert scenario.drift_on_restore


def test_restore_past_the_ceiling_is_refused() -> None:
    last, checks = _play("withdraw-past-ceiling")
    assert isinstance(last, StaleSet)
    served = list(OPS_BY_ID)
    check = _scheduler(
        _published(served),
        last_ids=served,
        last_successful=last.last_successful,
        last_successful_fetch=last.last_successful_fetch,
    ).tick(now="2026-08-14T02:16:00Z")
    with pytest.raises(StalenessError, match="admission.check then inspect_admission"):
        restore(
            last,
            check,
            now=_epoch("2026-08-14T02:16:00Z"),
            ceiling=_ceiling(last.deployment_id),
        )
    with pytest.raises(StalenessError, match="full admission sequence"):
        observe(
            last,
            check,
            now=_epoch("2026-08-14T02:16:00Z"),
            ceiling=_ceiling(last.deployment_id),
        )


def test_compare_each_is_not_called() -> None:
    tree = ast.parse(MODULE.read_text(), filename=str(MODULE))
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            assert node.id != "compare_each"


# ---------------------------------------------------------------------------
# T152 — recovery is admission, unwired.


def _clean_inspection(operation_ids: list[str]) -> tuple[Mapping[str, str], Codebase]:
    source = "def handle():\n    return None\n"
    return {op: "handle" for op in operation_ids}, Codebase.from_sources({"app.py": source})


def test_recovery_below_the_ceiling_is_refused() -> None:
    stale = _enter_on(_absent())
    ids = list(OPS_BY_ID)
    index, codebase = _clean_inspection(ids)
    with pytest.raises(StalenessError, match="Below the ceiling a"):
        recover(
            stale,
            FetchResponse(status=200, body=_body(ids), location=ENFORCEMENT),
            now=_epoch(LAST_OK) + 360.0,
            ceiling=_ceiling(),
            handler_index=index,
            codebase=codebase,
        )


def test_recovery_past_the_ceiling_runs_inspection() -> None:
    last, _ = _play("withdraw-past-ceiling")
    assert isinstance(last, StaleSet)
    ids = list(OPS_BY_ID)
    index, codebase = _clean_inspection(ids)
    outcome = recover(
        last,
        FetchResponse(status=200, body=_body(ids), location=ENFORCEMENT),
        now=_epoch("2026-08-14T02:16:00Z"),
        ceiling=_ceiling(last.deployment_id),
        handler_index=index,
        codebase=codebase,
    )
    assert outcome.recovered is True
    assert outcome.decision.admitted is True
    assert outcome.inspection is not None
    assert outcome.decision.state == "published_non_empty"


def test_recovery_past_the_ceiling_records_a_rejected_admission() -> None:
    last, _ = _play("withdraw-past-ceiling")
    assert isinstance(last, StaleSet)
    index, codebase = _clean_inspection(["health"])
    outcome = recover(
        last,
        FetchResponse(status=404, body=None, location=ENFORCEMENT),
        now=_epoch("2026-08-14T02:16:00Z"),
        ceiling=_ceiling(last.deployment_id),
        handler_index=index,
        codebase=codebase,
    )
    assert outcome.recovered is False
    assert outcome.decision.admitted is False
    assert outcome.inspection is None
    assert outcome.decision.state == ABSENT


def test_recovery_does_not_call_tick() -> None:
    source = MODULE.read_text()
    tree = ast.parse(source, filename=str(MODULE))
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == "tick":
            raise AssertionError("staleness.py must not tick; recovery is admission")
    assert "inspect_admission" in source
    assert "admission_check" in source


def test_readable_no_operations_restore_is_zero_drift() -> None:
    last, _ = _play("withdraw-readable-no-operations-restore-identical")
    assert isinstance(last, Restore)
    assert last.signals == ()


def test_stay_updates_the_specification_state_last_found() -> None:
    last, checks = _play("withdraw-past-ceiling")
    assert isinstance(last, StaleSet)
    assert last.specification_state == UNREACHABLE
    assert last.entering_signal.specification_state == ABSENT
    assert last.last_successful_fetch == "2026-08-14T02:00:00Z"
    assert isinstance(checks[-1].signals[0], FailedRefetch)
    assert checks[-1].signals[0].specification_state == UNREACHABLE


def test_no_http_client_and_no_target_credential() -> None:
    source = MODULE.read_text()
    for needle in ("urllib", "http.client", "requests", "Authorization"):
        assert needle not in source
