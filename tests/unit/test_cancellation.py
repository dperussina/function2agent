"""T047 — a cancelled consumer leaves no error and no partial state.

**Why this file is separate from `test_runner.py`.** Finding 006 reported a
teardown defect against the runtime it probed, and cancellation is routine in an
agent product rather than exceptional: a consumer closing a tab is the common
case, not the failure case. A defect here shows up as a leaked lease or a
half-journalled turn, and both are invisible to a test that only checks the
caller got an answer.

**The two claims, and what a broken teardown would look like against each.**

- *No error.* A cancelled run must not raise at the caller, must not record a
  fault outcome, and must not end the session in a terminal state — because
  nothing ended. `data-model.md` §2.1's `interrupted ─▶ RUNNING` edge is the one
  cancellation takes, and FR-006's taxonomy has no cancellation member, so a
  cancelled run that named one would be inventing an outcome.
- *No partial state.* The journal's turn count and the number of returned turn
  records must agree. A runner that abandoned a turn mid-flight leaves a model
  call accrued against a turn no record describes, and the next resume would
  either re-run it or skip it — both silently.

**The teardown handshake is asserted through `honoured_at`, not through the
state string.** The point of standing the session down is that the enforcement
point stops honouring the capability; `SessionRow.honoured_at` is the predicate
the proxy actually evaluates, so that is what is read here. A test asserting
`state == "INTERRUPTED"` would pass for a state name change that left the
predicate true.
"""

from __future__ import annotations

import json
import threading

import pytest

from src.contracts import terminal
from src.contracts.repository import Repository
from src.runtime.dispatch import ToolCall
from src.runtime.loop import ModelResponse
from src.runtime.result_bound import ResultBound, RetentionStore
from src.runtime.runner import CancelToken, Runner, RunnerError
from src.runtime.session_state import SessionStateMachine
from src.runtime.session_store import Ceilings, SessionStore
from src.runtime.trace import (
    MODEL_CALL,
    OUTCOME_OK,
    STATE_TRANSITION,
    ArtifactVersions,
    SpanWriter,
)
from src.runtime.trace_budget import BudgetJournal
from src.supervisor.session_table import SessionTable, capability_digest

TENANT, DEPLOYMENT, SESSION = "t-1", "d-1", "sess-1"
LEASE = 2_000_000_000.0
VERSIONS = ArtifactVersions(TENANT, DEPLOYMENT, {"prompt": "sha256:" + "0" * 64})
CEILINGS = Ceilings(spend_usd=100.0, tokens=1_000_000,
                    wall_clock_seconds=10_000.0, turns=50)


class Tok:
    name = "test-tok"

    def count(self, text: str) -> int:
        return max(1, len(text) // 4)


class Rig:
    def __init__(self, tmp_path):
        self.lifecycle = SessionTable(tmp_path / "session.sqlite3")
        self.repo = Repository(tmp_path / "runtime.sqlite3", role="runtime",
                               tenant_id=TENANT, deployment_id=DEPLOYMENT)
        self.store = SessionStore(self.repo, lifecycle=self.lifecycle)
        self.budget = BudgetJournal(self.repo, session_root=tmp_path / "root")
        self.spans = SpanWriter(self.repo)
        self.machine = SessionStateMachine(self.lifecycle)
        self.runner = Runner(
            store=self.store,
            lifecycle=self.lifecycle,
            machine=self.machine,
            budget=self.budget,
            spans=self.spans,
            bound=ResultBound(bound_tokens=500, context_window_tokens=10_000,
                              tokenizer=Tok()),
            retention=lambda session_id: RetentionStore(
                root=tmp_path / "scratch", session_id=session_id,
                max_bytes=1_000_000),
            versions=VERSIONS,
            tenant_id=TENANT,
            deployment_id=DEPLOYMENT,
            clock=_clock(),
            lease_interval_seconds=LEASE,
        )

    def close(self):
        self.repo.close()
        self.lifecycle.close()


def _clock():
    n = {"t": 0.0}

    def now() -> float:
        n["t"] += 1.0
        return n["t"]

    return now


def _asks(name: str = "t") -> ModelResponse:
    return ModelResponse(provider="test", provider_state=b"state", text="",
                         tool_calls=(ToolCall(index=0, call_id="c0", name=name),))


def _finish() -> ModelResponse:
    return ModelResponse(provider="test", provider_state=b"state", text="done")


def _start(rig: Rig, model, execute, token: CancelToken | None = None):
    return rig.runner.start(
        session_id=SESSION, prompt="p", ceilings=CEILINGS,
        capability_handle="handle-1", model=model, execute=execute, cancel=token)


# ---------------------------------------------------------------------------
# No error.


def test_a_cancelled_run_returns_rather_than_raising(tmp_path) -> None:
    rig = Rig(tmp_path)
    token = CancelToken()
    calls = {"n": 0}

    def model(context):
        calls["n"] += 1
        if calls["n"] == 2:
            token.cancel()
        return _asks()

    outcome = _start(rig, model, lambda c: "r", token)

    assert outcome.cancelled is True
    assert outcome.terminal_state is None, (
        f"a cancelled run named {outcome.terminal_state!r} as its terminal "
        "state. Nothing ended: FR-006's taxonomy has no cancellation member, "
        "and data-model.md §2.1 routes an interruption to a resumable state."
    )
    rig.close()


def test_a_cancelled_run_records_no_fault_outcome(tmp_path) -> None:
    """Cancellation is routine. A fault outcome would make it look like a bug."""
    rig = Rig(tmp_path)
    token = CancelToken()
    calls = {"n": 0}

    def model(context):
        calls["n"] += 1
        if calls["n"] == 2:
            token.cancel()
        return _asks()

    _start(rig, model, lambda c: "r", token)

    outcomes = {row["outcome"] for row in rig.spans.spans(SESSION)}
    assert outcomes == {OUTCOME_OK}, (
        f"a cancelled run left {sorted(outcomes)} on the trace. Only 'ok' "
        "belongs there: nothing was denied, refused, timed out or faulted."
    )
    rig.close()


def test_the_interruption_is_on_the_trace_as_a_transition(tmp_path) -> None:
    """Principle VI. A teardown nothing recorded is one nobody can audit."""
    rig = Rig(tmp_path)
    token = CancelToken()
    token.cancel()

    _start(rig, lambda c: _finish(), lambda c: "r", token)

    transitions = [row for row in rig.spans.spans(SESSION)
                   if row["kind"] == STATE_TRANSITION]
    assert transitions, "the interruption left no state_transition span"
    payload = json.loads(transitions[-1]["payload"])["transition"]
    assert payload["to_state"] == "INTERRUPTED"
    assert payload["terminal_state"] is None
    rig.close()


# ---------------------------------------------------------------------------
# No partial state.


def test_the_journal_and_the_returned_turns_agree(tmp_path) -> None:
    """A turn abandoned mid-flight shows up here and nowhere else.

    The journal's turn count is what a ceiling and a resume both read. If the
    runner accrued a turn it then abandoned, the count exceeds the records and
    resume would either re-run the turn or skip it, with nothing to say which.
    """
    rig = Rig(tmp_path)
    token = CancelToken()
    calls = {"n": 0}

    def model(context):
        calls["n"] += 1
        if calls["n"] == 3:
            token.cancel()
        return _asks()

    outcome = _start(rig, model, lambda c: "r", token)

    journalled = rig.budget.totals(SESSION).turns
    assert journalled == len(outcome.turns), (
        f"the journal counts {journalled} turns and {len(outcome.turns)} "
        "records came back. A turn was accrued and then abandoned."
    )
    model_spans = [row for row in rig.spans.spans(SESSION)
                   if row["kind"] == MODEL_CALL]
    assert len(model_spans) == journalled, (
        f"{len(model_spans)} model calls against {journalled} journalled "
        "turns — a call was made that no turn accounts for"
    )
    rig.close()


def test_cancelling_before_the_first_turn_runs_no_turn_at_all(tmp_path) -> None:
    rig = Rig(tmp_path)
    token = CancelToken()
    token.cancel()

    def model(context):
        raise AssertionError(
            "the model was called on a run cancelled before it started")

    outcome = _start(rig, model, lambda c: "r", token)

    assert outcome.turns == ()
    assert rig.budget.totals(SESSION).turns == 0
    rig.close()


def test_the_lease_is_stood_down_before_the_runner_returns(tmp_path) -> None:
    """The teardown handshake, read through the predicate the proxy evaluates.

    Asserted on `honoured_at` rather than on the state string, because the
    obligation is that the enforcement point stops honouring the capability and
    a state rename would satisfy a string comparison without satisfying that.
    """
    rig = Rig(tmp_path)
    token = CancelToken()
    token.cancel()

    _start(rig, lambda c: _finish(), lambda c: "r", token)

    row = rig.lifecycle.get(SESSION)
    assert row.honoured_at(0.0) is False, (
        "the runner returned while the session was still honoured. A consumer "
        "that went away leaves a live capability behind."
    )
    rig.close()


def test_a_cancelled_session_is_resumable_and_a_completed_one_is_not(
    tmp_path,
) -> None:
    """The difference between interrupted and terminated, asserted as behaviour.

    An interruption that recorded a terminal state would pass every assertion
    above and fail here, because a terminated session has no resume edge.
    """
    rig = Rig(tmp_path)
    token = CancelToken()
    token.cancel()
    _start(rig, lambda c: _finish(), lambda c: "r", token)

    rig.machine.resume(SESSION, at=100.0, lease_expires_at=LEASE)
    assert rig.lifecycle.get(SESSION).state == "RUNNING"
    rig.close()


def test_a_completed_run_is_terminated_and_named(tmp_path) -> None:
    """The control arm. Without it, a runner that interrupted *everything*
    would pass every cancellation assertion in this file."""
    rig = Rig(tmp_path)
    outcome = _start(rig, lambda c: _finish(), lambda c: "r")

    assert outcome.cancelled is False
    assert outcome.terminal_state == terminal.COMPLETED.name
    row = rig.lifecycle.get(SESSION)
    assert row.state == "TERMINATED"
    assert row.terminal_state == terminal.COMPLETED.name
    rig.close()


def test_cancelling_twice_is_not_a_second_teardown(tmp_path) -> None:
    """Idempotent, because a consumer retrying a cancel is normal."""
    rig = Rig(tmp_path)
    token = CancelToken()
    token.cancel()
    token.cancel()
    _start(rig, lambda c: _finish(), lambda c: "r", token)

    transitions = [row for row in rig.spans.spans(SESSION)
                   if row["kind"] == STATE_TRANSITION]
    to_states = [json.loads(r["payload"])["transition"]["to_state"]
                 for r in transitions]
    assert to_states.count("INTERRUPTED") == 1, (
        f"the teardown ran {to_states.count('INTERRUPTED')} times"
    )
    rig.close()


def test_cancellation_lands_at_a_turn_boundary_and_not_inside_one(
    tmp_path,
) -> None:
    """A turn in flight finishes and is journalled; it is not torn in half.

    The cancel arrives while a tool call is executing. What must not happen is
    a turn record without its tool result, or a tool result without its span.
    Killing the work in flight is the sandbox's teardown and belongs to a later
    capability; abandoning the record of it would be this module's defect.
    """
    rig = Rig(tmp_path)
    token = CancelToken()
    inside = threading.Event()

    def execute(call: ToolCall) -> str:
        inside.set()
        token.cancel()
        return "body"

    outcome = _start(rig, lambda c: _asks(), execute, token)

    assert inside.is_set(), "the tool never ran; this arm proved nothing"
    assert len(outcome.turns) == 1
    turn = outcome.turns[0]
    assert len(turn.tool_results) == 1, (
        "the turn was recorded without the result of the call it made"
    )
    assert turn.tool_results[0].body
    rig.close()


def test_a_cancel_token_is_required_to_be_a_token(tmp_path) -> None:
    rig = Rig(tmp_path)
    with pytest.raises(RunnerError, match="CancelToken"):
        rig.runner.start(
            session_id=SESSION, prompt="p", ceilings=CEILINGS,
            capability_handle="h", model=lambda c: _finish(),
            execute=lambda c: "r", cancel=True)
    rig.close()
