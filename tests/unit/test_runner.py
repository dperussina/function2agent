"""T046 — session start, attach, loop invocation and the teardown handshake.

**What the runner is for, stated because otherwise it looks like a wrapper.**
The loop knows how to run a turn and nothing about a session's beginning or its
end. Admission, the capability handle, the lease and standing the session down
are the supervisor's, and the runner is the one place that talks to both — so it
is the only place that can guarantee **the session is stood down on every exit
path, including the one nobody planned for**. That guarantee is what the arms
below read.

The load-bearing arm is `test_a_fault_in_the_loop_still_stands_the_session_down`.
A runner that tears down only on the happy path passes every other test here and
leaks a live capability on the first exception in production.
"""

from __future__ import annotations

import pytest

from src.contracts import terminal
from src.contracts.repository import Repository
from src.runtime.loop import ModelResponse
from src.runtime.providers.costs import PROVENANCE_OPERATOR
from src.runtime.result_bound import ResultBound, RetentionStore
from src.runtime.runner import Runner, RunnerError
from src.runtime.session_state import SessionStateMachine
from src.runtime.session_store import Ceilings, SessionStore
from src.runtime.trace import ArtifactVersions, SpanWriter
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


# `spend_usd=0.0` is stated rather than left to default here and below. The
# default is `None` — nothing priced this turn — and the loop refuses that
# rather than accruing zero. A fake provider reaching no vendor costs nothing,
# so zero is the measurement. Its provenance is `operator` (OD-27) for the same
# reason: the zero came from this harness declaring it, not from a page, and
# `vendor` would be a source claimed rather than held.
def _finish(text: str = "done") -> ModelResponse:
    return ModelResponse(provider="test", provider_state=b"s", text=text,
                         spend_usd=0.0,
                         spend_provenance=PROVENANCE_OPERATOR)


def _start(rig, **over):
    kwargs = dict(session_id=SESSION, prompt="p", ceilings=CEILINGS,
                  capability_handle="handle-1", model=lambda c: _finish(),
                  execute=lambda c: "r")
    kwargs.update(over)
    return rig.runner.start(**kwargs)


# ---------------------------------------------------------------------------
# Start.


def test_start_admits_the_session_and_runs_it_to_a_named_terminal_state(
    tmp_path,
) -> None:
    rig = Rig(tmp_path)
    outcome = _start(rig, model=lambda c: _finish("the answer"))

    assert outcome.text == "the answer"
    assert outcome.terminal_state == terminal.COMPLETED.name
    row = rig.lifecycle.get(SESSION)
    assert row.state == "TERMINATED"
    assert row.terminal_state == terminal.COMPLETED.name
    rig.close()


def test_the_capability_handle_is_stored_only_as_a_digest(tmp_path) -> None:
    """The handle is a bearer token. A reader of the table holds no replayable
    copy, which is the property `session_table.py` exists to keep."""
    rig = Rig(tmp_path)
    _start(rig, capability_handle="secret-handle-9f2")

    row = rig.lifecycle.get(SESSION)
    assert row.capability_sha256 == capability_digest("secret-handle-9f2")
    assert "secret-handle-9f2" not in str(row)
    rig.close()


def test_the_ceilings_reach_the_store_and_not_only_the_loop(tmp_path) -> None:
    """FR-005: the ceilings must survive the process that enforced them."""
    rig = Rig(tmp_path)
    _start(rig, ceilings=Ceilings(spend_usd=7.5, tokens=99,
                                  wall_clock_seconds=8.25, turns=4))

    held = rig.store.load(SESSION).ceilings
    assert (held.spend_usd, held.tokens, held.wall_clock_seconds, held.turns) \
        == (7.5, 99, 8.25, 4)
    rig.close()


def test_starting_the_same_session_twice_is_refused(tmp_path) -> None:
    rig = Rig(tmp_path)
    _start(rig)
    with pytest.raises(RunnerError, match="exists"):
        _start(rig)
    rig.close()


# ---------------------------------------------------------------------------
# Attach.


def test_attach_resumes_an_interrupted_session_and_keeps_its_ceilings(
    tmp_path,
) -> None:
    """FR-007 resumes *this* session. The ceilings are the ones already set.

    A ceiling reset on attach is finding 006's measurement exactly: a limit of
    3 permitting 6, where every individual attempt is compliant.

    **The interruption comes from `max_turns_this_attempt`, not from a cancel.**
    Since cancellation became terminal (2026-08-05) that is the only event that
    takes FR-007's edge, so it is the only way to reach the state under test.
    """
    rig = Rig(tmp_path)

    def model(context):
        return ModelResponse(
            provider="test", provider_state=b"s", text="", spend_usd=0.0,
            spend_provenance=PROVENANCE_OPERATOR, tool_calls=(_call(),))

    first = _start(rig, ceilings=Ceilings(
        spend_usd=100.0, tokens=1_000_000, wall_clock_seconds=10_000.0,
        turns=3), model=model, max_turns_this_attempt=2)
    assert first.terminal_state is None, (
        "the attempt was bounded short, so the session did not end and there is "
        "no terminal state to name"
    )
    assert first.cancelled is False
    assert rig.lifecycle.get(SESSION).state == "INTERRUPTED"
    before = rig.budget.totals(SESSION).turns
    assert before > 0

    second = rig.runner.attach(
        session_id=SESSION, prompt="p", model=lambda c: _finish(),
        execute=lambda c: "r")

    assert second.terminal_state == terminal.COMPLETED.name
    assert rig.budget.totals(SESSION).turns == before + 1, (
        "the resumed attempt did not accrue against the same journal"
    )
    held = rig.store.load(SESSION).ceilings
    assert held.turns == 3, "attach reset the turn ceiling"
    rig.close()


def test_turn_indexes_continue_across_attempts(tmp_path) -> None:
    """`data-model.md` §2.2: dense and monotonic **across the session**.

    A second attempt that restarted numbering at 0 would collide on T051's
    `(session_id, turn_index, step_index)` key — which since T051 is a unique
    index in the store, so the collision is now a refusal rather than a
    transcript with two turn 0s in it.

    **The expectation changed with T052 and the reason is worth stating.** This
    used to assert `[2]`: the resumed attempt's own turns. Resume reconstruction
    brings the earlier attempt's turns back, so the outcome now carries the
    *session's* transcript. What the arm reads is therefore the whole sequence,
    and the load-bearing part is that turn 2 follows turns 0 and 1 rather than
    re-numbering from zero.

    The turn *ceiling* arm in `test_loop.py` does not cover this: the ceiling is
    compared against the journal directly and is indifferent to what a turn calls
    itself. The two mechanisms read the same number for different reasons.
    """
    rig = Rig(tmp_path)

    def model(context):
        return ModelResponse(provider="test", provider_state=b"s", text="",
                             spend_usd=0.0,
                             spend_provenance=PROVENANCE_OPERATOR,
                             tool_calls=(_call(),))

    first = _start(rig, model=model, max_turns_this_attempt=2)
    assert [t.turn_index for t in first.turns] == [0, 1]

    asked = {"n": 0}

    def second_model(context):
        asked["n"] += 1
        return _finish()

    second = rig.runner.attach(session_id=SESSION, prompt="p",
                               model=second_model, execute=lambda c: "r")
    assert [t.turn_index for t in second.turns] == [0, 1, 2], (
        f"the resumed attempt numbered its turns {[t.turn_index for t in second.turns]}; "
        "two turns already happened, so the next one is turn 2 and the two "
        "before it are reconstructed rather than renumbered"
    )
    assert asked["n"] == 1, (
        f"the provider was called {asked['n']} times on the resumed attempt. "
        "Two turns were already complete; calling for them again is finding "
        "006's re-execution and the transcript would look identical either way."
    )
    rig.close()


def test_attach_refuses_a_session_that_does_not_exist(tmp_path) -> None:
    rig = Rig(tmp_path)
    with pytest.raises(RunnerError, match="no session"):
        rig.runner.attach(session_id="nope", prompt="p",
                          model=lambda c: _finish(), execute=lambda c: "r")
    rig.close()


def test_attach_refuses_a_terminated_session(tmp_path) -> None:
    """A terminated session has no resume edge, and reviving one under its own
    id would produce a second outcome for a session FR-006 says already has
    one."""
    rig = Rig(tmp_path)
    _start(rig)
    with pytest.raises(RunnerError, match="TERMINATED"):
        rig.runner.attach(session_id=SESSION, prompt="p",
                          model=lambda c: _finish(), execute=lambda c: "r")
    rig.close()


# ---------------------------------------------------------------------------
# Teardown, on every exit path.


def test_a_fault_in_the_loop_still_stands_the_session_down(tmp_path) -> None:
    """The arm that matters. Teardown on the unplanned path.

    The session must not be left RUNNING with a live lease because the model
    raised. `unrecoverable_fault` is FR-006's named member for a fault the
    runtime cannot classify further — reaching it is a defect report, which is
    why it is recorded rather than swallowed.
    """
    rig = Rig(tmp_path)

    def model(context):
        raise ZeroDivisionError("the provider adapter blew up")

    with pytest.raises(ZeroDivisionError):
        _start(rig, model=model)

    row = rig.lifecycle.get(SESSION)
    assert row.honoured_at(0.0) is False, (
        "the session is still honoured after the loop faulted. The fault "
        "propagated and the capability outlived the run."
    )
    assert row.terminal_state == terminal.UNRECOVERABLE_FAULT.name
    rig.close()


def test_the_original_fault_is_not_replaced_by_a_teardown_fault(tmp_path) -> None:
    """A teardown that raises must not hide what actually went wrong.

    The first exception is the diagnosis; a teardown failure raised in its place
    is how a root cause disappears.
    """
    rig = Rig(tmp_path)

    def model(context):
        raise ZeroDivisionError("the real cause")

    def exploding_terminate(session_id, terminal_state):
        raise RuntimeError("teardown also failed")

    rig.lifecycle.terminate = exploding_terminate
    with pytest.raises(ZeroDivisionError, match="the real cause") as caught:
        _start(rig, model=model)

    # Preserved is not the same as ignored. The leak is attached to the
    # exception that propagates, so a traceback shows both; without this the
    # suppression above would be a silent swallow.
    notes = getattr(caught.value, "__notes__", [])
    assert any("still honoured" in note for note in notes), (
        f"the leaked capability left no trace on the propagating exception: "
        f"{notes!r}"
    )
    rig.close()


def test_a_failed_teardown_with_nothing_in_flight_is_raised(tmp_path) -> None:
    """The other half of the same resolution.

    When no exception is propagating there is nothing to preserve, so a session
    the teardown failed to stand down must raise. A runner that only ever
    attached a note would return a `RunOutcome` describing a completed run whose
    capability is still live.

    Driven through the *interrupt* write rather than the terminate write, so this
    arm and `test_the_original_fault_is_not_replaced_by_a_teardown_fault` break
    two different supervisor calls. Both breaking `terminate` would leave the
    interrupt teardown path with no failure arm at all.
    """
    rig = Rig(tmp_path)

    def exploding_interrupt(session_id):
        raise RuntimeError("the supervisor refused the write")

    rig.lifecycle.mark_interrupted = exploding_interrupt

    with pytest.raises(RunnerError, match="still honoured"):
        _start(rig,
               model=lambda c: ModelResponse(
                   provider="test", provider_state=b"s", text="",
                   spend_usd=0.0, spend_provenance=PROVENANCE_OPERATOR,
                   tool_calls=(_call(),)),
               max_turns_this_attempt=1)
    rig.close()


def test_a_ceiling_reached_run_is_torn_down_with_the_ceilings_state(
    tmp_path,
) -> None:
    rig = Rig(tmp_path)
    outcome = _start(
        rig,
        ceilings=Ceilings(spend_usd=100.0, tokens=1_000_000,
                          wall_clock_seconds=10_000.0, turns=2),
        model=lambda c: ModelResponse(provider="test", provider_state=b"s",
                                      text="", spend_usd=0.0,
                                      spend_provenance=PROVENANCE_OPERATOR,
                                      tool_calls=(_call(),)))

    assert outcome.terminal_state == terminal.TURN_CEILING.name
    assert rig.lifecycle.get(SESSION).honoured_at(0.0) is False
    rig.close()


def _call():
    from src.runtime.dispatch import ToolCall
    return ToolCall(index=0, call_id="c0", name="t")


# ---------------------------------------------------------------------------
# T066 — the raw signals, read where the runtime actually produces them.
#
# `tests/unit/test_signals.py` reads the shapes; these read the *wiring*. A
# signal type that nothing populates is a type, and the two arms below are the
# ones that fail if the loop or the teardown stops attaching a cause.


def _end_of_run_detail(rig) -> dict:
    """The marker as a reader of the trace sees it, not as the caller does.

    Read off the persisted span rather than off the returned `RunOutcome`,
    because the record is the durable artefact and the return value is not. A
    marker that reached the caller and not the trace would leave an operator
    reading `terminated.unrecoverable_fault` with the identity still gone.
    """
    import json

    for row in reversed(rig.spans.spans(SESSION)):
        detail = json.loads(row["payload"]).get("detail") or {}
        if "end_of_run" in detail:
            return detail["end_of_run"]
    raise AssertionError(
        "no span carries an end-of-run marker. Every terminal edge mints one; "
        "a session that ended without one is finding 006's measurement back.")


def test_a_faulted_run_records_which_exception_ended_it(tmp_path) -> None:
    """The gap T066 exists to close, at the point it was open.

    `test_a_fault_in_the_loop_still_stands_the_session_down` above asserts the
    session is named `terminated.unrecoverable_fault` — which says *a fault the
    runtime could not classify further* and nothing about which fault. Before
    this the type and message existed only in a traceback that goes with the
    process. This arm is the one that fails if they go back there.
    """
    rig = Rig(tmp_path)

    def model(context):
        raise ZeroDivisionError("the provider adapter blew up")

    with pytest.raises(ZeroDivisionError):
        _start(rig, model=model)

    marker = _end_of_run_detail(rig)
    assert marker["reason"] == "faulted"
    assert marker["terminal_state"] == terminal.UNRECOVERABLE_FAULT.name
    assert marker["error"]["type"] == "ZeroDivisionError", (
        f"the exception's identity is not on the record: {marker!r}. The "
        "terminal state says a fault happened; only this says which.")
    assert "blew up" in marker["error"]["message"]
    rig.close()


def test_a_ceiling_termination_records_which_ceiling_and_on_what_reading(
    tmp_path,
) -> None:
    """FR-005 has four ceilings and the marker must say which one fired.

    The *reading* travels with it for the reason `ExhaustionCause` states: a
    cause naming only the dimension cannot distinguish a session that overshot
    by one turn from one that overshot by a thousand, and those are a ceiling
    working and a reservation policy that is not bounding anything.
    """
    rig = Rig(tmp_path)
    _start(rig,
           ceilings=Ceilings(spend_usd=100.0, tokens=1_000_000,
                             wall_clock_seconds=10_000.0, turns=2),
           model=lambda c: ModelResponse(
               provider="test", provider_state=b"s", text="", spend_usd=0.0,
               spend_provenance=PROVENANCE_OPERATOR, tool_calls=(_call(),)))

    marker = _end_of_run_detail(rig)
    assert marker["reason"] == "ceiling_reached"
    assert marker["terminal_state"] == terminal.TURN_CEILING.name
    assert marker["exhaustion"]["dimension"] == "turns", (
        f"the marker does not say which of FR-005's four ceilings fired: "
        f"{marker!r}")
    assert marker["exhaustion"]["declared"] == "2", (
        "the ceiling the reading was taken against is missing, so the record "
        "cannot say how far past it the session got.")
    rig.close()
