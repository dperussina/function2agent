"""T144 — additional configurable triggers: deployment event and session start.

## What has to be asserted here that a "it called tick" test would miss

FR-046: a customer-emitted deployment event MUST NOT be assumed available.
A constructor or selection that requires an endpoint is that assumption
wearing a field. The cheap detector is `TriggerSelection()` with no
arguments, plus an `__init__` signature that has no URL.

The session-start trigger is a deployment-clock re-fetch through Plane A,
not a source-clock re-analysis. There is no live session loop (OD-36). A
callable with tests is a landed T144; a comment in `loop.py` is not. This
file asserts the callable, and asserts `loop.py` / `runner.py` / `main.py`
do not invent a call site.

Both callables go through `Scheduler.tick`. The Plane A refusal is one
function. `path-level probe` is refused by that function, not emitted here.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from src.analysis.clocks import DEPLOYMENT, SOURCE
from src.analysis.drift_signal import ArtifactDrift
from src.runtime.drift.scheduler import (
    EVENT,
    MANUAL,
    PATH_LEVEL_PROBE,
    SCHEDULED,
    SESSION_START,
    SchedulerError,
    due,
)
from src.runtime.drift.triggers import (
    TriggerError,
    TriggerSelection,
    Triggers,
)
from tests.contract.test_drift_scheduler import (
    LAST_OK,
    OPS_BY_ID,
    ORIGIN,
    _published,
    _scheduler,
)
from tests.fixtures.drift_corpora import deployment as dep

REPO = Path(__file__).resolve().parents[2]
MODULE = REPO / "src" / "runtime" / "drift" / "triggers.py"


def _triggers(
    transport=None,
    *,
    last_ids=None,
    selection=None,
    peer: str = "http://enforcement-point",
) -> Triggers:
    served = last_ids or list(OPS_BY_ID)
    scheduler = _scheduler(
        transport or _published(served, peer=peer),
        last_ids=served,
    )
    return Triggers(scheduler, selection)


# ---------------------------------------------------------------------------
# Not assumed available. No required endpoint. Default off.


def test_trigger_selection_defaults_both_additional_triggers_off() -> None:
    selection = TriggerSelection()
    assert selection.deployment_event is False
    assert selection.session_start is False
    fields = set(TriggerSelection.__dataclass_fields__)
    assert fields == {"deployment_event", "session_start"}
    for name in fields:
        assert "url" not in name.lower()
        assert "endpoint" not in name.lower()
        assert "webhook" not in name.lower()


def test_triggers_constructor_does_not_require_a_pipeline_endpoint() -> None:
    params = inspect.signature(Triggers.__init__).parameters
    assert "endpoint" not in params
    assert "url" not in params
    assert "webhook" not in params
    assert "event_url" not in params
    assert "deployment_event_url" not in params
    # A scheduler plus default selection is a complete construction.
    triggers = _triggers()
    assert triggers._selection.deployment_event is False


def test_an_unconfigured_deployment_event_is_refused() -> None:
    triggers = _triggers()
    with pytest.raises(TriggerError, match="MUST NOT be assumed available"):
        triggers.on_deployment_event(now=LAST_OK)
    assert triggers._scheduler._transport.calls == 0


def test_an_unconfigured_session_start_is_refused() -> None:
    triggers = _triggers()
    with pytest.raises(TriggerError, match="not configured"):
        triggers.on_session_start(now=LAST_OK)
    assert triggers._scheduler._transport.calls == 0


def test_the_t155_corpus_supplies_no_pipeline_event() -> None:
    """SC-020: 100% detected with no event supplied by a deployment pipeline."""
    assert dep.deployment_events() == []


# ---------------------------------------------------------------------------
# Configured event: same Plane A path, trigger=event, §2.6's slot.


def test_a_configured_deployment_event_re_fetches_through_plane_a() -> None:
    served = list(OPS_BY_ID)
    after = [op for op in served if op != "cancel_shipment"]
    triggers = _triggers(
        _published(after),
        last_ids=served,
        selection=TriggerSelection(deployment_event=True),
    )
    result = triggers.on_deployment_event(now=LAST_OK)
    assert result.trigger == EVENT
    assert result.trigger != SCHEDULED
    assert result.trigger != MANUAL
    assert result.trigger != PATH_LEVEL_PROBE
    assert len(result.signals) == 1
    assert isinstance(result.signals[0], ArtifactDrift)
    assert result.signals[0].clock == DEPLOYMENT


def test_an_origin_dialing_transport_is_refused_on_a_deployment_event() -> None:
    served = list(OPS_BY_ID)
    triggers = _triggers(
        _published(served, peer=ORIGIN),
        last_ids=served,
        selection=TriggerSelection(deployment_event=True),
    )
    with pytest.raises(SchedulerError, match="not the configured enforcement point"):
        triggers.on_deployment_event(now=LAST_OK)


# ---------------------------------------------------------------------------
# Session start: deployment-clock re-fetch, not wired to a session loop.


def test_a_configured_session_start_is_a_deployment_clock_re_fetch() -> None:
    served = list(OPS_BY_ID)
    after = [op for op in served if op != "cancel_shipment"]
    triggers = _triggers(
        _published(after),
        last_ids=served,
        selection=TriggerSelection(session_start=True),
    )
    result = triggers.on_session_start(now=LAST_OK)
    assert result.trigger == SESSION_START
    assert result.trigger != SCHEDULED
    assert result.trigger != EVENT
    assert result.signals[0].clock == DEPLOYMENT
    assert result.signals[0].clock != SOURCE


def test_session_start_does_not_consult_due() -> None:
    assert due(now=1.0, last_tick_at=0.0, interval_seconds=300.0) is False
    served = list(OPS_BY_ID)
    after = [op for op in served if op != "cancel_shipment"]
    triggers = _triggers(
        _published(after),
        last_ids=served,
        selection=TriggerSelection(session_start=True),
    )
    result = triggers.on_session_start(now=LAST_OK)
    assert len(result.signals) == 1


def test_an_origin_dialing_transport_is_refused_at_session_start() -> None:
    served = list(OPS_BY_ID)
    triggers = _triggers(
        _published(served, peer=ORIGIN),
        last_ids=served,
        selection=TriggerSelection(session_start=True),
    )
    with pytest.raises(SchedulerError, match="not the configured enforcement point"):
        triggers.on_session_start(now=LAST_OK)


def test_session_start_is_not_wired_to_a_session_loop() -> None:
    """OD-36: the callable exists; loop.py / runner.py / main.py do not call it."""
    for relative in (
        "src/runtime/loop.py",
        "src/runtime/runner.py",
        "src/runtime/main.py",
        "src/runtime/serving.py",
    ):
        text = (REPO / relative).read_text()
        assert "on_session_start" not in text, relative
        assert "src.runtime.drift" not in text, relative
        assert "SESSION_START" not in text, relative


def test_alongside_the_default_does_not_require_dropping_the_scheduler() -> None:
    """FR-046: in place of, or alongside. Selection cannot turn scheduled off."""
    selection = TriggerSelection(deployment_event=True, session_start=True)
    assert selection.deployment_event is True
    assert selection.session_start is True
    assert not hasattr(selection, "scheduled")


# ---------------------------------------------------------------------------
# path-level probe is not a trigger. Vocabulary lives on tick.


def test_path_level_probe_is_refused_as_a_trigger() -> None:
    served = list(OPS_BY_ID)
    scheduler = _scheduler(_published(served), last_ids=served)
    with pytest.raises(SchedulerError, match="backstop"):
        scheduler.tick(now=LAST_OK, trigger=PATH_LEVEL_PROBE)


def test_an_unknown_trigger_is_refused() -> None:
    served = list(OPS_BY_ID)
    scheduler = _scheduler(_published(served), last_ids=served)
    with pytest.raises(SchedulerError, match="not a drift-check trigger"):
        scheduler.tick(now=LAST_OK, trigger="commit")


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
    assert "src.analysis.source_drift" not in imported
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
    assert "compare_each" not in called
    assert "detect" not in called
    literals = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    assert not any(name.lower() == "authorization" for name in literals)
    assert "tick" in called
    assert "fetch_over_http" not in called
    assert "classify" not in called
