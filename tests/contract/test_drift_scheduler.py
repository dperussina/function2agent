"""T141 and T142 — the deployment-clock scheduler, forced through Plane A.

## What has to be asserted here that a "it fetched" test would miss

T141's content is a scheduled re-fetch that needs no pipeline event and no
phone-home. T142's content is that the peer of that fetch is the enforcement
point, named by configuration. A scheduler that "works" on a direct socket
to the origin satisfies every field-presence assertion and is the second
continuous path T-10 exists to prevent. INV-003 cannot catch that path on
its own: `admission.fetch_over_http` is not under `SANDBOX_ROOTS`, so a
scheduler that called it with an origin passed in from configuration would
not fire the static scan. The peer check is the live arm.

## The cheap detector, in this file, so Rule 8 can fail it

`_origin_transport` dials a documentation address and returns a valid
published specification. `test_a_transport_that_dials_the_origin_is_refused`
requires the scheduler to raise. A scheduler that skipped the peer check
would classify the body and emit signals, and that test would go green for
the defect.

## Every refusal arm reaches exactly one guard

Construction validates deployment identity, then the enforcement point, then
the last-successful clock, then the last-successful deployment, then the
interval. `tick` validates Authorization, then the peer, then the
non-admissible branch. Each arm below supplies a value that is valid at
every guard except the one it targets.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any, Mapping

import pytest

from src.analysis.admission import (
    ABSENT,
    FetchResponse,
    UNREACHABLE,
)
from src.analysis.clocks import (
    DEPLOYMENT,
    SOURCE,
    Movement,
    compare,
    deployment_reading,
    reading,
)
from src.analysis.drift_signal import (
    ARTIFACT_DRIFT,
    FAILED_REFETCH,
    ArtifactDrift,
    FailedRefetch,
)
from src.analysis.source_drift import source_reading_of
from src.contracts.config import SUPERVISOR_KEYS
from src.runtime.drift.scheduler import (
    CAPABILITY_HEADER,
    SCHEDULED,
    CheckResult,
    Fetch,
    Scheduler,
    SchedulerError,
    deployment_signals_of,
    due,
    origin_of,
)
from tests.fixtures.drift_corpora import deployment as dep
from tests.fixtures.drift_corpora import spec_withdrawn as withdrawn
from tests.fixtures.drift_corpora import source as src

REPO = Path(__file__).resolve().parents[2]
MODULE = REPO / "src" / "runtime" / "drift" / "scheduler.py"

ENFORCEMENT = "http://enforcement-point"
#: RFC 5737 documentation address. A host the scheduler must not accept as
#: a peer, and a string that must not appear in `scheduler.py`.
ORIGIN = "http://203.0.113.10:443"

DEPLOYMENT_ID = "d-reference-app"
ANCHOR = "acme/parts-api@" + "0" * 39 + "a"
LAST_OK = "2026-08-13T00:00:00Z"

REFERENCE_OPS = json.loads(dep.SERVED_OPERATIONS_FILE.read_text())["operations"]
OPS_BY_ID = {op["operation_id"]: op for op in REFERENCE_OPS}


def _ops(ids: list[str]) -> list[dict[str, Any]]:
    return [OPS_BY_ID[i] for i in ids]


def _body(ids: list[str]) -> bytes:
    return json.dumps({"operations": _ops(ids)}).encode()


def _reading(ids: list[str], *, deployment_id: str = DEPLOYMENT_ID):
    return deployment_reading(deployment_id=deployment_id, operations=_ops(ids))


class ScriptedTransport:
    """A transport that reports a chosen peer and a scripted response."""

    def __init__(
        self,
        *,
        peer: str,
        status: int | None,
        body: bytes | None,
        transport_error: str | None = None,
        request_headers: Mapping[str, str] | None = None,
    ) -> None:
        self.peer = peer
        self.status = status
        self.body = body
        self.transport_error = transport_error
        self.request_headers = dict(request_headers or {})
        self.calls = 0

    def fetch(self) -> Fetch:
        self.calls += 1
        return Fetch(
            response=FetchResponse(
                status=self.status,
                body=self.body,
                location=self.peer,
                transport_error=self.transport_error,
            ),
            peer=self.peer,
            request_headers=self.request_headers,
        )


def _published(ids: list[str], *, peer: str = ENFORCEMENT) -> ScriptedTransport:
    return ScriptedTransport(peer=peer, status=200, body=_body(ids))


def _absent(*, peer: str = ENFORCEMENT) -> ScriptedTransport:
    return ScriptedTransport(peer=peer, status=404, body=None)


def _unreachable(*, peer: str = ENFORCEMENT) -> ScriptedTransport:
    return ScriptedTransport(
        peer=peer, status=None, body=None, transport_error="timed out"
    )


def _scheduler(
    transport: ScriptedTransport,
    *,
    last_ids: list[str] | None = None,
    last_successful: Any = None,
    last_successful_fetch: str = LAST_OK,
    interval_seconds: float = 300.0,
    enforcement_point: str = ENFORCEMENT,
    deployment_id: str = DEPLOYMENT_ID,
) -> Scheduler:
    reading_ = last_successful
    if reading_ is None:
        reading_ = _reading(last_ids or list(OPS_BY_ID), deployment_id=deployment_id)
    return Scheduler(
        deployment_id=deployment_id,
        enforcement_point=enforcement_point,
        transport=transport,
        last_successful=reading_,
        last_successful_fetch=last_successful_fetch,
        interval_seconds=interval_seconds,
    )


def _interval_key():
    return next(
        key for key in SUPERVISOR_KEYS if key.name == "DRIFT_CHECK_INTERVAL_SECONDS"
    )


def _raw_deployment_scenarios() -> list[dict[str, Any]]:
    return json.loads(dep.CORPUS_FILE.read_text())["scenarios"]


def _raw_withdrawn_scenarios() -> list[dict[str, Any]]:
    return json.loads(withdrawn.CORPUS_FILE.read_text())["scenarios"]


# ---------------------------------------------------------------------------
# T155 — a change in what the deployment serves is detected; unchanged is quiet.


def test_a_withdrawal_is_detected_while_source_is_unchanged() -> None:
    """FR-029's automatic half, against T155. Disablement is T146 and is not this."""
    raw = {s["scenario_id"]: s for s in _raw_deployment_scenarios()}
    scenario = raw["withdraw-one-operation"]
    served_before = list(scenario["served_before"])
    scheduler = _scheduler(
        _published(served_before),
        last_ids=served_before,
        last_successful_fetch=scenario["arms"]["scheduled"]["observations"][0]["at"],
    )
    # First two polls are identical to admission. Quiet.
    for observation in scenario["arms"]["scheduled"]["observations"][:2]:
        scheduler._transport = _published(observation["served"])
        result = scheduler.tick(now=observation["at"])
        assert result.signals == ()
        assert result.trigger == SCHEDULED

    changed = scenario["arms"]["scheduled"]["observations"][2]
    scheduler._transport = _published(changed["served"])
    result = scheduler.tick(now=changed["at"])
    assert len(result.signals) == 1
    signal = result.signals[0]
    assert isinstance(signal, ArtifactDrift)
    assert signal.clock == DEPLOYMENT
    assert signal.deployment_id == scenario["deployment_id"]
    assert signal.document()["signal_kind"] == ARTIFACT_DRIFT
    assert signal.kinds_moved == ("served_operation_set",)
    assert "cancel_shipment" not in changed["served"]


def test_unchanged_observations_produce_no_signal() -> None:
    """The deployment-clock analogue of T156, scored on T155's negative control."""
    raw = {s["scenario_id"]: s for s in _raw_deployment_scenarios()}
    scenario = raw["no-withdrawal"]
    served = list(scenario["served_before"])
    scheduler = _scheduler(_published(served), last_ids=served)
    raised: list[CheckResult] = []
    for observation in scenario["arms"]["scheduled"]["observations"]:
        scheduler._transport = _published(observation["served"])
        result = scheduler.tick(now=observation["at"])
        raised.extend(result.signals)
        assert result.signals == ()
    assert raised == []


def test_every_t155_withdrawal_moves_the_deployment_clock_only() -> None:
    for scenario in _raw_deployment_scenarios():
        if not scenario["change"]["withdrawn"]:
            continue
        before = list(scenario["served_before"])
        after_ids = [
            op
            for op in before
            if op not in scenario["change"]["withdrawn"]
        ]
        movement = compare(_reading(before), _reading(after_ids))
        assert movement.clock == DEPLOYMENT
        assert movement.moved
        signals = deployment_signals_of((movement,))
        assert len(signals) == 1
        assert signals[0].clock == DEPLOYMENT


# ---------------------------------------------------------------------------
# T157 — a non-admissible re-fetch is a FailedRefetch, not a fake after-version.


def test_a_non_admissible_fetch_is_a_failed_refetch() -> None:
    scheduler = _scheduler(_absent())
    result = scheduler.tick(now="2026-08-14T00:05:00Z")
    assert len(result.signals) == 1
    signal = result.signals[0]
    assert isinstance(signal, FailedRefetch)
    assert signal.clock == DEPLOYMENT
    assert signal.specification_state == ABSENT
    assert signal.last_successful_fetch == LAST_OK
    assert signal.document()["signal_kind"] == FAILED_REFETCH
    assert not hasattr(signal, "version_after")
    assert "version_after" not in signal.document()
    # Last-known-good is not replaced by a fabricated after-version.
    assert result.last_successful_fetch == LAST_OK


def test_unreachable_is_a_failed_refetch_and_does_not_enter_stale() -> None:
    """T157's withdraw-past-ceiling exercises `unreachable`. Stale is T147's."""
    raw = {s["scenario_id"]: s for s in _raw_withdrawn_scenarios()}
    scenario = raw["withdraw-past-ceiling"]
    last_good = list(scenario["last_known_good"])
    first = scenario["fetches"][0]
    assert first["state"] == "published_non_empty"
    scheduler = _scheduler(
        _published(first["operations"]),
        last_ids=last_good,
        last_successful_fetch=first["at"],
    )
    scheduler.tick(now=first["at"])

    absent = scenario["fetches"][1]
    scheduler._transport = _absent()
    result = scheduler.tick(now=absent["at"])
    assert isinstance(result.signals[0], FailedRefetch)
    assert result.signals[0].specification_state == ABSENT

    unreachable = scenario["fetches"][3]
    assert unreachable["state"] == "unreachable"
    scheduler._transport = _unreachable()
    result = scheduler.tick(now=unreachable["at"])
    assert isinstance(result.signals[0], FailedRefetch)
    assert result.signals[0].specification_state == UNREACHABLE
    assert not hasattr(result.signals[0], "version_after")
    # The module has no stale marking to set. Pin the absence.
    assert not hasattr(result, "staleness")
    assert result.last_successful_fetch == first["at"]


# ---------------------------------------------------------------------------
# T142 — the peer is the enforcement point. A direct origin fails.


def test_a_fetch_through_the_enforcement_point_is_accepted() -> None:
    served = list(OPS_BY_ID)
    result = _scheduler(_published(served, peer=ENFORCEMENT), last_ids=served).tick(
        now=LAST_OK
    )
    assert result.signals == ()
    assert origin_of(ENFORCEMENT) == "http://enforcement-point"


def test_a_transport_that_dials_the_origin_is_refused() -> None:
    """The cheap detector. A scheduler that skipped the peer check would pass."""
    served = list(OPS_BY_ID)
    scheduler = _scheduler(_published(served, peer=ORIGIN), last_ids=served)
    with pytest.raises(SchedulerError, match="not the configured enforcement point"):
        scheduler.tick(now=LAST_OK)


def test_a_specification_path_on_the_enforcement_point_is_still_that_point() -> None:
    served = list(OPS_BY_ID)
    peer = ENFORCEMENT + "/served_operations.json"
    result = _scheduler(_published(served, peer=peer), last_ids=served).tick(now=LAST_OK)
    assert result.signals == ()


def test_an_authorization_header_is_refused() -> None:
    served = list(OPS_BY_ID)
    transport = _published(served)
    transport.request_headers = {"Authorization": "Bearer target-secret"}
    scheduler = _scheduler(transport, last_ids=served)
    with pytest.raises(SchedulerError, match="Authorization"):
        scheduler.tick(now=LAST_OK)


def test_the_capability_header_is_not_an_authorization() -> None:
    served = list(OPS_BY_ID)
    transport = _published(served)
    transport.request_headers = {CAPABILITY_HEADER: "opaque-handle"}
    result = _scheduler(transport, last_ids=served).tick(now=LAST_OK)
    assert result.signals == ()


# ---------------------------------------------------------------------------
# The DEPLOYMENT filter, and the source_derived union.


def test_a_source_clock_move_is_not_deployment_drift() -> None:
    """The filter is `Movement.clock == DEPLOYMENT`, not `source_derived`."""
    contracts = src.load_revisions()[0].contract
    before = reading(
        SOURCE,
        deployment_id=DEPLOYMENT_ID,
        versions={
            "derived_contract": "sha256:" + "a" * 64,
            "derived_check": "sha256:" + "b" * 64,
        },
        source_ref=ANCHOR,
    )
    after = source_reading_of(
        contracts, deployment_id=DEPLOYMENT_ID, source_ref=ANCHOR
    )
    movement = Movement(
        clock=SOURCE,
        deployment_id=DEPLOYMENT_ID,
        moved=True,
        version_before=before.version,
        version_after=after.version,
        kinds_moved=("derived_contract",),
    )
    assert deployment_signals_of((movement,)) == ()
    # The same movement is a real source-clock signal if nobody filters.
    assert ArtifactDrift.from_movement(movement).clock == SOURCE


# ---------------------------------------------------------------------------
# Interval, identity, trigger. Unvalidated, not a measurement.


def test_the_interval_is_the_declared_key_and_is_unvalidated() -> None:
    key = _interval_key()
    assert key.default == "300.0"
    assert key.unvalidated is True
    # Residual, named rather than closed: the key cites FR-028 while the
    # description and FR-046's five-minute default are the deployment clock.
    assert key.requirement == "FR-028"
    assert "deployment clock" in key.purpose
    served = list(OPS_BY_ID)
    result = _scheduler(
        _published(served), last_ids=served, interval_seconds=float(key.default)
    ).tick(now=LAST_OK)
    assert result.interval_seconds == 300.0
    assert result.interval_unvalidated is True
    assert result.deployment_id == DEPLOYMENT_ID
    assert result.trigger == SCHEDULED
    assert result.detected_at == LAST_OK


def test_due_is_the_interval_predicate_and_does_not_read_the_clock() -> None:
    assert due(now=0.0, last_tick_at=None, interval_seconds=300.0) is True
    assert due(now=299.0, last_tick_at=0.0, interval_seconds=300.0) is False
    assert due(now=300.0, last_tick_at=0.0, interval_seconds=300.0) is True
    with pytest.raises(SchedulerError, match="not a positive interval"):
        due(now=1.0, last_tick_at=None, interval_seconds=0.0)


# ---------------------------------------------------------------------------
# Construction refusals. One guard reachable per arm.


def test_a_source_clock_last_successful_is_refused() -> None:
    contracts = src.load_revisions()[0].contract
    source = source_reading_of(
        contracts, deployment_id=DEPLOYMENT_ID, source_ref=ANCHOR
    )
    with pytest.raises(SchedulerError, match="source-clock"):
        _scheduler(_published(list(OPS_BY_ID)), last_successful=source)


def test_a_last_successful_for_another_deployment_is_refused() -> None:
    other = _reading(list(OPS_BY_ID), deployment_id="d-other")
    with pytest.raises(SchedulerError, match="d-other"):
        _scheduler(
            _published(list(OPS_BY_ID)),
            last_successful=other,
            deployment_id=DEPLOYMENT_ID,
        )


def test_an_empty_enforcement_point_is_refused() -> None:
    with pytest.raises(SchedulerError, match="no enforcement point"):
        _scheduler(_published(list(OPS_BY_ID)), enforcement_point="   ")


def test_a_scheduler_for_no_deployment_is_refused() -> None:
    with pytest.raises(SchedulerError, match="no deployment"):
        Scheduler(
            deployment_id="",
            enforcement_point=ENFORCEMENT,
            transport=_published(list(OPS_BY_ID)),
            last_successful=_reading(list(OPS_BY_ID)),
            last_successful_fetch=LAST_OK,
            interval_seconds=300.0,
        )


def test_a_non_positive_interval_is_refused() -> None:
    with pytest.raises(SchedulerError, match="not a positive interval"):
        _scheduler(_published(list(OPS_BY_ID)), interval_seconds=0.0)


# ---------------------------------------------------------------------------
# What this module must not grow: a client, a target origin, a Plane B route.


def test_the_module_does_not_open_a_client_or_import_the_default_opener() -> None:
    tree = ast.parse(MODULE.read_text(), filename=str(MODULE))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    assert "urllib.request" not in imported
    assert "src.analysis.admission" in imported
    assert not any(
        name == "src.runtime.egress" or name.startswith("src.runtime.egress")
        for name in imported
    )
    text = MODULE.read_text()
    for banned in ("urlopen", "HTTPConnection", "HTTPSConnection", "httpx", "requests"):
        assert banned not in text, banned
    assert ORIGIN not in text
    called = {
        node.attr if isinstance(node, ast.Attribute) else node.id
        for node in ast.walk(tree)
        if isinstance(node, (ast.Name, ast.Attribute))
    }
    assert "fetch_over_http" not in called


def test_the_runtime_process_is_the_ticker_and_is_not_wired() -> None:
    """OD-36: the runtime entry ends in a report, not a serve loop."""
    main = (REPO / "src" / "runtime" / "main.py").read_text()
    assert "src.runtime.drift" not in main
    assert "Scheduler" not in main
