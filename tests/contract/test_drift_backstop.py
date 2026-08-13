"""T145 — path-level reachability failure as a backstop, not a trigger.

## What has to be asserted here that a "it returned a record" test would miss

FR-046's load-bearing sentence is that the per-operation path-level
reachability precondition failing in front of a user is a **backstop**
that MUST be recorded as a drift signal, and MUST NOT be relied on as a
trigger design. A test that only checked field presence would pass a
module that emitted `trigger=path-level probe` on `CheckResult`, which
is the thing `Scheduler.tick` already refuses and this slice must not
reverse.

The record cannot honestly be `ArtifactDrift` (no versions obtained) or
`FailedRefetch` (not a specification re-fetch). A third `DriftSignal`
variant would need FR-031's terms without inventing versions that were
not obtained; this file asserts the residual rather than closing it.

T065's `BackstopTripped` is a different backstop. Recording does not halt
the session. Disablement is T146 and is not this recording: using the
path failure to disable would make the backstop a trigger.

Planted facts, not a live request. No HTTP client.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from src.analysis.drift_signal import ArtifactDrift, FailedRefetch
from src.runtime.budget_backstop import BackstopTripped
from src.runtime.drift.backstop import (
    PATH_LEVEL_FAILURE,
    BackstopError,
    PathLevelFailure,
    record,
)
from src.runtime.drift.scheduler import PATH_LEVEL_PROBE, SchedulerError
from tests.contract.test_drift_scheduler import LAST_OK, OPS_BY_ID, _published, _scheduler

REPO = Path(__file__).resolve().parents[2]
MODULE = REPO / "src" / "runtime" / "drift" / "backstop.py"
ORIGIN = "http://203.0.113.10:443"


def _facts(**overrides):
    facts = dict(
        operation_id="cancel_shipment",
        deployment_id="d-reference-app",
        observed="status=404",
        detected_at=LAST_OK,
    )
    facts.update(overrides)
    return facts


# ---------------------------------------------------------------------------
# A planted path failure is recorded. It is not a DriftSignal.


def test_a_planted_path_failure_is_recorded() -> None:
    failure = record(**_facts())
    assert isinstance(failure, PathLevelFailure)
    assert not isinstance(failure, ArtifactDrift)
    assert not isinstance(failure, FailedRefetch)
    assert failure.operation_id == "cancel_shipment"
    assert failure.deployment_id == "d-reference-app"
    assert failure.observed == "status=404"
    assert failure.detected_at == LAST_OK
    assert not hasattr(failure, "version_before")
    assert not hasattr(failure, "version_after")
    assert not hasattr(failure, "kinds_moved")
    assert not hasattr(failure, "specification_state")
    assert not hasattr(failure, "clock")


def test_the_document_is_not_a_trigger() -> None:
    """path-level probe is §2.6's trigger name. The backstop must not emit it."""
    document = record(**_facts()).document()
    assert document["record_kind"] == PATH_LEVEL_FAILURE
    assert "trigger" not in document
    assert PATH_LEVEL_PROBE not in document.values()
    assert PATH_LEVEL_FAILURE in document.values()
    assert document["record_kind"] != PATH_LEVEL_PROBE


def test_tick_still_refuses_path_level_probe_as_a_trigger() -> None:
    """Do not reverse T144. The backstop is not a fifth scheduled trigger."""
    served = list(OPS_BY_ID)
    scheduler = _scheduler(_published(served), last_ids=served)
    with pytest.raises(SchedulerError, match="backstop"):
        scheduler.tick(now=LAST_OK, trigger=PATH_LEVEL_PROBE)


def test_recording_does_not_halt_the_session() -> None:
    """T065 is a different backstop. This one does not raise BackstopTripped."""
    failure = record(**_facts())
    assert isinstance(failure, PathLevelFailure)
    assert not isinstance(failure, BackstopTripped)


# ---------------------------------------------------------------------------
# Every refusal arm reaches exactly one guard.


def test_an_empty_operation_id_is_refused() -> None:
    with pytest.raises(BackstopError, match="no operation"):
        record(**_facts(operation_id=""))


def test_an_empty_deployment_id_is_refused() -> None:
    with pytest.raises(BackstopError, match="no deployment"):
        record(**_facts(deployment_id=""))


def test_an_empty_observation_is_refused() -> None:
    with pytest.raises(BackstopError, match="no observation"):
        record(**_facts(observed=""))


def test_an_empty_detected_at_is_refused() -> None:
    with pytest.raises(BackstopError, match="detected_at"):
        record(**_facts(detected_at=""))


# ---------------------------------------------------------------------------
# No fetch, no comparison, no clock, no logger, not wired.


def test_the_module_does_not_open_a_client_or_invent_versions() -> None:
    tree = ast.parse(MODULE.read_text(), filename=str(MODULE))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    assert "urllib.request" not in imported
    assert "src.analysis.admission" not in imported
    assert "src.analysis.drift_signal" not in imported
    assert "src.analysis.clocks" not in imported
    assert "src.runtime.budget_backstop" not in imported
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
    assert "compare_each" not in called
    assert "from_movement" not in called
    assert "failed_refetch" not in called
    assert "tick" not in called
    assert "fetch" not in called
    assert "getLogger" not in called
    assert "time" not in called


def test_record_does_not_accept_a_transport() -> None:
    assert "transport" not in inspect.signature(record).parameters
    assert "scheduler" not in inspect.signature(record).parameters
    assert "now" not in inspect.signature(record).parameters


def test_the_backstop_is_not_wired_to_a_serve_loop() -> None:
    """OD-36: the function exists; loop.py / runner.py / main.py do not call it."""
    for relative in (
        "src/runtime/loop.py",
        "src/runtime/runner.py",
        "src/runtime/main.py",
        "src/runtime/serving.py",
    ):
        text = (REPO / relative).read_text()
        assert "path_level" not in text, relative
        assert "PathLevelFailure" not in text, relative
        assert "src.runtime.drift.backstop" not in text, relative
