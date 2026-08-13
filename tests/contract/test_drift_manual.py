"""T143 — on-demand drift check for either clock, not configurable away.

## What has to be asserted here that a "it returned a CheckResult" test would miss

FR-029's on-demand limb is **either clock**, and the two clocks take two
different inputs. A `manual.py` that fetches the origin on the source-clock
path, or that skips the peer check on the deployment-clock path, is a new
second path. The cheap detector for the first is a scheduler handed to
`check(clock=SOURCE, ...)`. The cheap detector for the second is a pair of
artifacts handed to `check(clock=DEPLOYMENT, ...)`. Both must raise.

The Plane A refusal is `Scheduler.tick`, parameterised by `trigger=MANUAL`.
This file does not re-state `origin_of`. A transport that dials the origin
is still refused, and that refusal is T142's proof, not a second copy.

Manual is not configurable away. The suspected absence of a disable key is
phrased as a check: grep `config.py` for a key that would disable it, then
plant a mapping that tries to turn it off and show the check still runs.

SC-020's on-demand limb is T155. The oracle is the loader's `withdrawn` /
`unaffected` / `is_negative_control`, not a second withdrawn-operation
classifier. Disablement is T146 and is not scored here.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from src.analysis.clocks import DEPLOYMENT, SOURCE
from src.analysis.drift_signal import ARTIFACT_DRIFT, ArtifactDrift
from src.contracts.config import RUNTIME_KEYS, SUPERVISOR_KEYS
from src.runtime.drift.manual import (
    ManualError,
    SourceCheckResult,
    check,
    check_deployment,
    check_source,
)
from src.runtime.drift.scheduler import (
    MANUAL,
    SCHEDULED,
    CheckResult,
    SchedulerError,
    due,
)
from tests.contract.test_drift_scheduler import (
    LAST_OK,
    OPS_BY_ID,
    ORIGIN,
    _published,
    _scheduler,
)
from tests.contract.test_source_drift import _both
from tests.fixtures.drift_corpora import deployment as dep
from tests.fixtures.drift_corpora import source as src

REPO = Path(__file__).resolve().parents[2]
MODULE = REPO / "src" / "runtime" / "drift" / "manual.py"
CONFIG = REPO / "src" / "contracts" / "config.py"


def _by_id():
    return {r.revision_id: r for r in src.load_revisions()}


def _detect_inputs(revision):
    parent = _by_id()[revision.parent]
    return dict(
        before=_both(parent.contract),
        after=_both(revision.contract),
        before_contracts=parent.contract,
        after_contracts=revision.contract,
        renamed=revision.renamed,
    )


# ---------------------------------------------------------------------------
# SC-020 on-demand limb against T155. Detection, not disablement.


def test_every_t155_withdrawal_is_detected_on_demand() -> None:
    """SC-020's manual clause. The population is the loader's withdrawals."""
    detected = []
    for scenario in dep.load_scenarios():
        if scenario.is_negative_control:
            continue
        last_ids = sorted(scenario.served_before)
        after_ids = list(scenario.unaffected)
        scheduler = _scheduler(
            _published(after_ids),
            last_ids=last_ids,
            deployment_id=scenario.deployment_id,
        )
        now = scenario.arms["manual"].observation_instants[0]
        result = check(clock=DEPLOYMENT, scheduler=scheduler, now=now)
        assert isinstance(result, CheckResult)
        assert result.trigger == MANUAL
        assert result.trigger != SCHEDULED
        assert len(result.signals) == 1
        signal = result.signals[0]
        assert isinstance(signal, ArtifactDrift)
        assert signal.clock == DEPLOYMENT
        assert signal.deployment_id == scenario.deployment_id
        assert signal.document()["signal_kind"] == ARTIFACT_DRIFT
        assert signal.kinds_moved == ("served_operation_set",)
        for withdrawn in scenario.withdrawn:
            assert withdrawn not in scenario.unaffected
        assert result.detected_at == now
        assert result.detected_at == scenario.arms["manual"].detected_at
        detected.append(scenario.scenario_id)
    figures = dep.counts()
    assert len(detected) == figures["scenarios_carrying_a_withdrawal"]


def test_the_negative_control_is_quiet_on_demand() -> None:
    scenario = next(s for s in dep.load_scenarios() if s.is_negative_control)
    served = sorted(scenario.served_before)
    scheduler = _scheduler(
        _published(served),
        last_ids=served,
        deployment_id=scenario.deployment_id,
    )
    now = scenario.arms["manual"].observation_instants[0]
    result = check(clock=DEPLOYMENT, scheduler=scheduler, now=now)
    assert result.signals == ()
    assert result.trigger == MANUAL


# ---------------------------------------------------------------------------
# Source clock: T138's detect(), no fetch. T154 is the oracle.


def test_every_breaking_revision_is_detected_on_demand() -> None:
    """On-demand FR-028. The oracle is the loader, not a second classifier."""
    for revision in src.load_revisions():
        if not revision.breaking:
            continue
        result = check(clock=SOURCE, now=revision.check_run_id, **_detect_inputs(revision))
        assert isinstance(result, SourceCheckResult)
        assert result.trigger == MANUAL
        assert result.finding is not None
        assert result.finding.signal.clock == SOURCE
        assert result.finding.operations == revision.drifted_operations


def test_non_breaking_revisions_are_quiet_on_demand() -> None:
    for revision in src.load_revisions():
        if revision.parent is None or revision.breaking:
            continue
        result = check(clock=SOURCE, now=revision.check_run_id, **_detect_inputs(revision))
        assert result.finding is None
        assert result.trigger == MANUAL


# ---------------------------------------------------------------------------
# Either clock is two inputs. Mixing them is the cheap detector.


def test_a_transport_on_the_source_clock_path_is_refused() -> None:
    revision = next(r for r in src.load_revisions() if r.breaking)
    scheduler = _scheduler(_published(list(OPS_BY_ID), peer=ORIGIN))
    with pytest.raises(ManualError, match="specification fetch"):
        check(
            clock=SOURCE,
            scheduler=scheduler,
            now=revision.check_run_id,
            **_detect_inputs(revision),
        )
    assert scheduler._transport.calls == 0


def test_artifacts_on_the_deployment_clock_path_are_refused() -> None:
    revision = next(r for r in src.load_revisions() if r.breaking)
    scheduler = _scheduler(_published(list(OPS_BY_ID)))
    inputs = _detect_inputs(revision)
    with pytest.raises(ManualError, match="skip the peer check"):
        check(
            clock=DEPLOYMENT,
            scheduler=scheduler,
            now=LAST_OK,
            before=inputs["before"],
            after=inputs["after"],
        )
    assert scheduler._transport.calls == 0


def test_an_origin_dialing_transport_is_still_refused_on_demand() -> None:
    """T142 still binds. The peer check is tick's, not a second copy."""
    served = list(OPS_BY_ID)
    scheduler = _scheduler(_published(served, peer=ORIGIN), last_ids=served)
    with pytest.raises(SchedulerError, match="not the configured enforcement point"):
        check(clock=DEPLOYMENT, scheduler=scheduler, now=LAST_OK)


def test_a_manual_check_runs_when_a_tick_is_not_due() -> None:
    """At any time. `due` is the scheduler's predicate and is not consulted."""
    assert due(now=1.0, last_tick_at=0.0, interval_seconds=300.0) is False
    served = list(OPS_BY_ID)
    after = [op for op in served if op != "cancel_shipment"]
    scheduler = _scheduler(_published(after), last_ids=served)
    result = check_deployment(scheduler, now=LAST_OK)
    assert result.trigger == MANUAL
    assert len(result.signals) == 1


def test_a_third_clock_is_refused() -> None:
    with pytest.raises(ManualError, match="not a clock"):
        check(clock="fused", now=LAST_OK)


# ---------------------------------------------------------------------------
# Not configurable away. Absence is checked, then a planted disable is ignored.


def test_config_py_has_no_key_that_disables_manual_invocation() -> None:
    """The suspected absence, as a check: grep the declared keys."""
    names = {key.name for key in (*SUPERVISOR_KEYS, *RUNTIME_KEYS)}
    disabling = [
        name
        for name in names
        if "MANUAL" in name
        or (
            "DRIFT" in name
            and any(part in name for part in ("DISABLE", "ENABLE", "ON_DEMAND"))
        )
    ]
    assert disabling == [], disabling
    text = CONFIG.read_text()
    assert "MANUAL_DRIFT" not in text
    assert "DISABLE_MANUAL" not in text
    assert "ENABLE_MANUAL_DRIFT" not in text


def test_a_config_that_tries_to_turn_manual_invocation_off_is_not_consulted() -> None:
    planted = {
        "MANUAL_DRIFT_CHECK": "false",
        "ENABLE_MANUAL_DRIFT": "0",
        "DISABLE_MANUAL_DRIFT": "1",
    }
    served = list(OPS_BY_ID)
    after = [op for op in served if op != "cancel_shipment"]
    scheduler = _scheduler(_published(after), last_ids=served)
    # The check takes no config. The planted mapping is in scope and unread.
    assert inspect.signature(check).parameters.get("config") is None
    assert inspect.signature(check_deployment).parameters.get("enabled") is None
    result = check(clock=DEPLOYMENT, scheduler=scheduler, now=LAST_OK)
    assert result.trigger == MANUAL
    assert len(result.signals) == 1
    assert planted["DISABLE_MANUAL_DRIFT"] == "1"


def test_check_source_does_not_accept_a_transport() -> None:
    assert "scheduler" not in inspect.signature(check_source).parameters
    assert "transport" not in inspect.signature(check_source).parameters


# ---------------------------------------------------------------------------
# One Plane A function. This module does not duplicate the peer check.


def test_the_module_does_not_duplicate_origin_of_or_open_a_client() -> None:
    tree = ast.parse(MODULE.read_text(), filename=str(MODULE))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    assert "urllib.request" not in imported
    assert "src.analysis.admission" not in imported
    text = MODULE.read_text()
    for banned in ("urlopen", "HTTPConnection", "HTTPSConnection", "httpx", "requests"):
        assert banned not in text, banned
    assert ORIGIN not in text
    called = {
        node.attr if isinstance(node, ast.Attribute) else node.id
        for node in ast.walk(tree)
        if isinstance(node, (ast.Name, ast.Attribute))
    }
    assert "origin_of" not in called
    literals = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    assert not any(name.lower() == "authorization" for name in literals)
    assert "tick" in called
    assert "detect" in called
    assert "compare_each" not in called
    assert "fetch_over_http" not in called
    assert "classify" not in called


def test_the_source_clock_path_does_not_call_fetch() -> None:
    tree = ast.parse(MODULE.read_text(), filename=str(MODULE))
    source_fn = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "check_source"
    )
    called = {
        n.attr if isinstance(n, ast.Attribute) else n.id
        for n in ast.walk(source_fn)
        if isinstance(n, (ast.Name, ast.Attribute))
    }
    assert "fetch" not in called
    assert "tick" not in called
    assert "detect" in called
