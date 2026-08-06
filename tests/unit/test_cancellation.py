"""T047 — a cancelled consumer leaves no error and no partial state.

**Why this file is separate from `test_runner.py`.** Finding 006 reported a
teardown defect against the runtime it probed, and cancellation is routine in an
agent product rather than exceptional: a consumer closing a tab is the common
case, not the failure case. A defect here shows up as a leaked lease or a
half-journalled turn, and both are invisible to a test that only checks the
caller got an answer.

**The two claims, and what a broken teardown would look like against each.**

- *No error.* A cancelled run must not raise at the caller and must not record a
  fault outcome. It **must** end the session, in FR-006's already-declared
  `terminated.operator_terminated` — cancellation is terminal as of 2026-08-05,
  and `src/runtime/runner.py`'s module docstring carries why. A cancelled run
  that left the session in `INTERRUPTED` would be resumable by `attach()`, which
  is the defect that routing had.
- *No partial state.* The journal's turn count and the number of returned turn
  records must agree. A runner that abandoned a turn mid-flight leaves a model
  call accrued against a turn no record describes, and the next resume would
  either re-run it or skip it — both silently.

**The teardown handshake is asserted through `honoured_at`, not through the
state string.** The point of standing the session down is that the enforcement
point stops honouring the capability; `SessionRow.honoured_at` is the predicate
the proxy actually evaluates, so that is what is read here. A test asserting the
state string alone would pass for a state rename that left the predicate true.
"""

from __future__ import annotations

import json
import threading

import pytest

from src.contracts import terminal
from src.contracts.repository import Repository
from src.contracts.transition import ST_OPERATOR_TERMINATED
from src.runtime.dispatch import ToolCall
from src.runtime.loop import ModelResponse
from src.runtime.progress import StallPolicy
from src.runtime.providers.costs import PROVENANCE_OPERATOR
from src.runtime.result_bound import ResultBound, RetentionStore
from src.runtime.runner import CancelToken, Runner, RunnerError
from src.runtime.session_state import SessionStateError, SessionStateMachine
from src.runtime.session_store import Ceilings, SessionStore
from src.runtime.trace import (
    MODEL_CALL,
    OUTCOME_OK,
    STATE_TRANSITION,
    ArtifactVersions,
    SpanWriter,
)
from src.runtime.journal import TurnJournal
from src.runtime.ledger import BudgetLedger, ReservationPolicy
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
        self.budget = BudgetLedger(
            BudgetJournal(self.repo, session_root=tmp_path / "root"),
            # Small but non-zero: the reservation wiring is exercised without
            # a reservation being large enough to reach a ceiling on its own,
            # which would make every arm here a budget test.
            policy=ReservationPolicy(spend_usd=0.001, tokens=1,
                                     wall_clock_seconds=0.001))
        self.journal = TurnJournal(self.repo)
        self.spans = SpanWriter(self.repo)
        self.machine = SessionStateMachine(self.lifecycle)
        self.runner = Runner(
            store=self.store,
            lifecycle=self.lifecycle,
            machine=self.machine,
            budget=self.budget,
            journal=self.journal,
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
            # T067. A cancellation arm drives the same tool call until the
            # consumer cancels, which is a stall by FR-006's predicate. A
            # threshold that fired would end these runs as
            # `terminated.no_progress` and the file would stop being about
            # cancellation at all — the exact confusion T068 exists to rule
            # out, arriving through the configuration instead of the code.
            stall=StallPolicy(consecutive_turns=1_000),
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


# `spend_usd=0.0` is stated rather than left to default. The default is `None`,
# meaning nothing priced the turn, and the loop refuses that rather than
# accruing zero; a fake provider that reaches no vendor genuinely costs nothing,
# which is a measurement and not a stand-in. `spend_provenance` is `operator`
# (OD-27) because the zero is this harness's declaration and there is no vendor
# page behind it.
def _asks(name: str = "t") -> ModelResponse:
    return ModelResponse(provider="test", provider_state=b"state", text="",
                         spend_usd=0.0,
                         spend_provenance=PROVENANCE_OPERATOR,
                         tool_calls=(ToolCall(index=0, call_id="c0", name=name),))


def _finish() -> ModelResponse:
    return ModelResponse(provider="test", provider_state=b"state", text="done",
                         spend_usd=0.0,
                         spend_provenance=PROVENANCE_OPERATOR)


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
    assert outcome.terminal_state == terminal.OPERATOR_TERMINATED.name, (
        f"a cancelled run reported {outcome.terminal_state!r}. The session ended "
        "and the row says so, so a caller told otherwise is told something the "
        "record contradicts."
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


def test_the_cancellation_is_on_the_trace_as_a_transition(tmp_path) -> None:
    """Principle VI. A teardown nothing recorded is one nobody can audit."""
    rig = Rig(tmp_path)
    token = CancelToken()
    token.cancel()

    _start(rig, lambda c: _finish(), lambda c: "r", token)

    transitions = [row for row in rig.spans.spans(SESSION)
                   if row["kind"] == STATE_TRANSITION]
    assert transitions, "the cancellation left no state_transition span"
    payload = json.loads(transitions[-1]["payload"])["transition"]
    assert payload["to_state"] == "TERMINATED"
    assert payload["terminal_state"] == terminal.OPERATOR_TERMINATED.name
    assert payload["deciding_rule"] == ST_OPERATOR_TERMINATED.rule_id, (
        f"the cancellation was attributed to {payload['deciding_rule']!r}. "
        "Principle VI wants the identity of the rule that produced the "
        "transition, and the rule for this edge is the operator-terminated one."
    )
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


def test_a_cancelled_session_cannot_be_attached_to(tmp_path) -> None:
    """The defect this file's routing exists to close, asserted as behaviour.

    `CancelToken` is one-way because "a token that could be cleared would let a
    race produce a run that continued after cancellation". While cancellation
    routed to `INTERRUPTED`, `attach()` *automatically resumed* the session it
    found there — so the outcome the token was made irreversible to prevent was
    reachable one call later. Cancelling and then attaching silently resumed the
    cancelled run.

    **Asserted against the terminal state in the message, not merely against
    `RunnerError`.** `attach` has two refusal branches and both name the state,
    so a match on `TERMINATED` alone would pass on the fallback "has no edge"
    branch. Only the `STATE_TERMINATED` branch interpolates `row.terminal_state`,
    so requiring the taxonomy name in the message is what proves *which* branch
    was reached.

    **The second assertion moved 2026-08-05 and the reason is the point of the
    change.** It used to require `"no edge out of"`, which was the message's
    citation of `data-model.md` §2.1 — a citation that held only vacuously,
    because §2.1 declared no `TERMINATED` state for an edge to leave. `OD-26`
    settled the direction and the message now names `SessionStateMachine`, which
    is what actually refuses. The assertion follows it, and it stays a
    *branch-discriminating* assertion rather than a change-detector: the fallback
    branch names no mechanism at all, so a run that reached it fails both lines.
    """
    rig = Rig(tmp_path)
    token = CancelToken()
    token.cancel()
    _start(rig, lambda c: _finish(), lambda c: "r", token)

    with pytest.raises(RunnerError) as caught:
        rig.runner.attach(session_id=SESSION, prompt="p",
                          model=lambda c: _finish(), execute=lambda c: "r")

    message = str(caught.value)
    assert terminal.OPERATOR_TERMINATED.name in message, (
        f"attach refused, but not from the branch that reads the terminal "
        f"state: {message!r}. The fallback branch names the state and not the "
        "outcome, so a cancelled session refused there would be refused for "
        "the wrong reason."
    )
    assert "SessionStateMachine refuses every transition out of" in message, (
        f"attach refused without naming the mechanism that refuses: {message!r}. "
        "The fallback branch names a state and no mechanism, so this line is "
        "the second half of the branch discrimination and not a wording pin."
    )
    rig.close()


def test_a_cancelled_run_names_operator_terminated_as_its_terminal_state(
    tmp_path,
) -> None:
    """Cancellation is terminal, and the name is read from three places.

    The caller-visible field, the supervisor's row and the trace span must
    agree. A runner that moved the row without reporting the name would leave a
    caller believing nothing ended, and a runner that reported a name it never
    wrote would be the same defect facing the other way.
    """
    rig = Rig(tmp_path)
    token = CancelToken()
    token.cancel()

    outcome = _start(rig, lambda c: _finish(), lambda c: "r", token)

    assert outcome.cancelled is True
    assert outcome.terminal_state == terminal.OPERATOR_TERMINATED.name

    row = rig.lifecycle.get(SESSION)
    assert row.state == "TERMINATED"
    assert row.terminal_state == terminal.OPERATOR_TERMINATED.name

    terminals = [row["terminal_state"] for row in rig.spans.spans(SESSION)
                 if row["kind"] == STATE_TRANSITION]
    assert terminals[-1] == terminal.OPERATOR_TERMINATED.name, (
        f"the trace's last transition names {terminals[-1]!r}. Principle VI "
        "wants the run's named terminal state on the record, and a record "
        "disagreeing with the row is worse than an absent one."
    )
    rig.close()


def test_a_completed_session_and_a_cancelled_one_are_both_unresumable(
    tmp_path,
) -> None:
    """The control arm for the routing, read through the resume edge itself.

    Without it, the two arms above are satisfied by a runner that terminates
    everything, and this one would still hold. What it adds is that the *machine*
    refuses the edge — `attach`'s guard and the lifecycle's guard are two
    mechanisms, and a test reading only the first proves only the first.
    """
    rig = Rig(tmp_path)
    token = CancelToken()
    token.cancel()
    _start(rig, lambda c: _finish(), lambda c: "r", token)

    with pytest.raises(SessionStateError, match="already terminated"):
        rig.machine.resume(SESSION, at=100.0, lease_expires_at=LEASE)
    assert rig.lifecycle.get(SESSION).state == "TERMINATED"
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
    assert to_states.count("TERMINATED") == 1, (
        f"the teardown ran {to_states.count('TERMINATED')} times"
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
