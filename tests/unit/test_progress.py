"""T067 — FR-006's stall predicate, and the member it fires.

**What each layer here is responsible for.** The predicate is a pure function of
turn records, so most arms need no session, no store and no clock. Two do: the
one that reads the member off a real run, because a predicate nothing calls is a
function, and the one that crosses a resume boundary, because *that* is the
property the predicate was written derived rather than counted in order to have.

**The stall shape these arms use is FR-006's second one** — a turn whose every
tool call repeats a call already made in this session with the same arguments
and the same outcome. The first shape (a turn that issues no call and returns no
result) is unreachable in this runtime: the loop completes on a turn with no
tool calls, which is FR-006's *"it produces the session's reported result"*.
That is asserted below rather than assumed, because if the loop ever stopped
completing on such a turn the predicate would silently start seeing a shape it
currently never sees.
"""

from __future__ import annotations

import pytest

from src.contracts import terminal
from src.contracts.repository import Repository
from src.contracts.transition import RULES_BY_ID, ST_NO_PROGRESS
from src.runtime.dispatch import ToolCall, ToolResult
from src.runtime.journal import TurnJournal
from src.runtime.ledger import BudgetLedger, ReservationPolicy
from src.runtime.loop import AgentLoop, ModelResponse
from src.runtime.progress import (
    StallConfigurationError,
    StallPolicy,
    call_address,
    consecutive_turns_without_progress,
    evaluate_stall,
    turn_addresses,
)
from src.runtime.providers.costs import PROVENANCE_OPERATOR
from src.runtime.result_bound import ResultBound, RetentionStore
from src.runtime.session_state import SessionStateError, SessionStateMachine
from src.runtime.session_store import Ceilings, SessionStore
from src.runtime.trace import ArtifactVersions, SpanWriter
from src.runtime.trace_budget import BudgetJournal
from src.runtime.turn import TurnRecord
from src.supervisor.session_table import SessionTable, capability_digest

TENANT, DEPLOYMENT, SESSION = "t-1", "d-1", "sess-1"
LEASE = 2_000_000_000.0
VERSIONS = ArtifactVersions(TENANT, DEPLOYMENT, {"prompt": "sha256:" + "0" * 64})


def _turn(index: int, calls, *, text: str = "") -> TurnRecord:
    """One record. `calls` is `(name, arguments, outcome)` per call."""
    tool_calls = tuple(
        ToolCall(index=i, call_id=f"c{index}-{i}", name=name, arguments=args)
        for i, (name, args, _outcome) in enumerate(calls)
    )
    results = tuple(
        ToolResult(call=call, outcome=outcome, body="b",
                   started_at=0.0, finished_at=1.0)
        for call, (_n, _a, outcome) in zip(tool_calls, calls)
    )
    return TurnRecord(turn_index=index, provider="test", provider_state=b"s",
                      tool_calls=tool_calls, tool_results=results,
                      text=text, at=float(index))


# ---------------------------------------------------------------------------
# The threshold. Required configuration, no default, no off switch.


def test_a_threshold_below_one_is_refused() -> None:
    for bad in (0, -1, -100):
        with pytest.raises(StallConfigurationError, match="smallest meaningful"):
            StallPolicy(consecutive_turns=bad)


def test_a_boolean_threshold_is_refused_rather_than_read_as_one() -> None:
    """`True == 1` in Python, so a config path that produced a bool would
    configure a threshold of one turn and look like it had been set."""
    with pytest.raises(StallConfigurationError, match="bool is refused"):
        StallPolicy(consecutive_turns=True)


def test_the_policy_has_no_default_and_no_disable() -> None:
    """FR-033: an unset threshold is a refusal, not an inherited number.

    Read off the signature rather than by calling, so the arm fails if a
    default is *added* — calling with no argument only tells you what today's
    default is once one exists.
    """
    import inspect

    param = inspect.signature(StallPolicy).parameters["consecutive_turns"]
    assert param.default is inspect.Parameter.empty, (
        "the stall threshold grew a default. FR-006 states no value for it and "
        "requires an unset one to fail loudly; a default here is the invented "
        "number FR-005's ceilings and FR-049's bounds are also forbidden.")
    assert not any(
        name in ("enabled", "disabled", "off")
        for name in inspect.signature(StallPolicy).parameters
    ), ("a switch here would let a deployment leave terminated.no_progress "
        "declared and unproducible")


# ---------------------------------------------------------------------------
# The predicate, as three components and nothing else.


def test_identity_is_the_tool_the_arguments_and_the_outcome() -> None:
    """FR-006 names three components; changing any one makes a call new."""
    base = call_address("search", {"q": "a"}, "ok")
    assert call_address("search", {"q": "a"}, "ok") == base
    assert call_address("fetch", {"q": "a"}, "ok") != base
    assert call_address("search", {"q": "b"}, "ok") != base
    assert call_address("search", {"q": "a"}, "error") != base


def test_argument_order_does_not_make_a_call_new() -> None:
    """FR-055's canonical serialization sorts keys, which is why the
    requirement names it rather than saying 'compare the arguments'. Two dicts
    that differ only in insertion order are the same call, and an identity
    decided by inspection would have got this wrong."""
    assert (call_address("t", {"a": 1, "b": 2}, "ok")
            == call_address("t", {"b": 2, "a": 1}, "ok"))


def test_the_result_body_is_not_part_of_the_identity() -> None:
    """The one place this module chooses, asserted so the choice is visible.

    A body in the address would make any tool returning a timestamp, a request
    id or a duration look new on every call, and the member would never fire —
    a taxonomy entry with no producer, which is what FR-006 argues against.
    """
    call = ToolCall(index=0, call_id="c0", name="t", arguments={})
    first = TurnRecord(
        turn_index=0, provider="p", provider_state=None, tool_calls=(call,),
        tool_results=(ToolResult(call=call, outcome="ok", body="at 10:00",
                                 started_at=0.0, finished_at=1.0),),
        text="", at=0.0)
    second = TurnRecord(
        turn_index=1, provider="p", provider_state=None, tool_calls=(call,),
        tool_results=(ToolResult(call=call, outcome="ok", body="at 10:01",
                                 started_at=0.0, finished_at=1.0),),
        text="", at=1.0)
    assert turn_addresses(first) == turn_addresses(second)


def test_a_result_is_matched_to_its_call_by_the_declared_index() -> None:
    """Not by list position. A turn where one call produced no result would
    otherwise pair every later result with the wrong call, and the addresses
    would be of combinations that never happened."""
    calls = (ToolCall(index=0, call_id="c0", name="a", arguments={}),
             ToolCall(index=1, call_id="c1", name="b", arguments={}))
    # Only the second call has a result.
    record = TurnRecord(
        turn_index=0, provider="p", provider_state=None, tool_calls=calls,
        tool_results=(ToolResult(call=calls[1], outcome="error", body="",
                                 started_at=0.0, finished_at=1.0),),
        text="", at=0.0)
    assert turn_addresses(record) == (
        call_address("a", {}, None), call_address("b", {}, "error"))


# ---------------------------------------------------------------------------
# Counting consecutive turns.


def test_repeating_the_same_call_accumulates() -> None:
    same = [("t", {"q": 1}, "ok")]
    records = [_turn(i, same) for i in range(4)]
    # The first turn made the call for the first time, so three repeats.
    assert consecutive_turns_without_progress(records) == 3


def test_one_new_call_in_a_turn_resets_the_count() -> None:
    """FR-006's second limb is *at least one* call new to the session, and the
    reset is what makes a productive turn between two stalled ones cost
    nothing."""
    same = [("t", {"q": 1}, "ok")]
    records = [
        _turn(0, same), _turn(1, same), _turn(2, same),
        _turn(3, [("t", {"q": 1}, "ok"), ("t", {"q": 2}, "ok")]),
        _turn(4, same),
    ]
    assert consecutive_turns_without_progress(records) == 1


def test_a_call_that_now_fails_differently_is_new() -> None:
    """FR-006's third shape, inverted: *fails in a way already recorded* is a
    stall, so failing in a way not recorded is progress."""
    records = [_turn(0, [("t", {}, "ok")]), _turn(1, [("t", {}, "error")])]
    assert consecutive_turns_without_progress(records) == 0


def test_a_turn_with_no_tool_calls_is_progress() -> None:
    """FR-006's first limb — it produced the session's reported result."""
    same = [("t", {}, "ok")]
    records = [_turn(0, same), _turn(1, same), _turn(2, [], text="answer")]
    assert consecutive_turns_without_progress(records) == 0


def test_an_empty_session_has_not_stalled() -> None:
    assert consecutive_turns_without_progress([]) == 0
    assert evaluate_stall([], StallPolicy(consecutive_turns=1)).stalled is False


def test_the_verdict_carries_the_reading_whether_or_not_it_fired() -> None:
    same = [("t", {}, "ok")]
    verdict = evaluate_stall([_turn(0, same), _turn(1, same)],
                             StallPolicy(consecutive_turns=5))
    assert verdict.stalled is False
    assert verdict.observed == 1 and verdict.declared == 5
    assert verdict.reading.matched is False
    assert verdict.reading.observed == "1" and verdict.reading.declared == "5"


# ---------------------------------------------------------------------------
# The edge, and the refusal that keeps the reading on the record.


def test_the_rule_is_registered_and_selects_among_alternatives() -> None:
    assert RULES_BY_ID[ST_NO_PROGRESS.rule_id] is ST_NO_PROGRESS
    assert ST_NO_PROGRESS.selects_among_alternatives, (
        "a rule declared determined by the prior state may carry no predicate "
        "inputs, and the reading is the entire content of this record")


def test_the_member_is_in_the_taxonomy() -> None:
    assert terminal.require("terminated.no_progress") is terminal.NO_PROGRESS
    assert terminal.NO_PROGRESS.requirement == "FR-006"


# ---------------------------------------------------------------------------
# The member, read off a real run.


class Tok:
    name = "test-tok"

    def count(self, text: str) -> int:
        return max(1, len(text) // 4)


class Rig:
    def __init__(self, tmp_path, *, threshold: int, turns: int = 50):
        self.lifecycle = SessionTable(tmp_path / "session.sqlite3")
        self.lifecycle.create(session_id=SESSION, tenant_id=TENANT,
                              deployment_id=DEPLOYMENT,
                              capability_sha256=capability_digest("h"),
                              lease_expires_at=LEASE, now=0.0)
        self.lifecycle.mark_running(SESSION)
        self.repo = Repository(tmp_path / "runtime.sqlite3", role="runtime",
                               tenant_id=TENANT, deployment_id=DEPLOYMENT)
        self.store = SessionStore(self.repo, lifecycle=self.lifecycle)
        self.store.create(session_id=SESSION, ceilings=Ceilings(
            spend_usd=100.0, tokens=1_000_000, wall_clock_seconds=10_000.0,
            turns=turns))
        self.budget = BudgetLedger(
            BudgetJournal(self.repo, session_root=tmp_path / "root"),
            policy=ReservationPolicy(spend_usd=0.001, tokens=1,
                                     wall_clock_seconds=0.001))
        self.journal = TurnJournal(self.repo)
        self.spans = SpanWriter(self.repo)
        self.machine = SessionStateMachine(self.lifecycle)
        self.threshold = threshold
        self.tmp_path = tmp_path

    def loop(self, model) -> AgentLoop:
        return AgentLoop(
            session_id=SESSION, store=self.store, budget=self.budget,
            journal=self.journal, spans=self.spans, machine=self.machine,
            bound=ResultBound(bound_tokens=500, context_window_tokens=10_000,
                              tokenizer=Tok()),
            retention=RetentionStore(root=self.tmp_path / "scratch",
                                     session_id=SESSION, max_bytes=1_000_000),
            model=model, execute=lambda call: "same answer every time",
            versions=VERSIONS, clock=_clock(),
            stall=StallPolicy(consecutive_turns=self.threshold))

    def close(self):
        self.repo.close()
        self.lifecycle.close()


def _clock():
    n = {"t": 0.0}

    def now() -> float:
        n["t"] += 1.0
        return n["t"]

    return now


def _repeating_model(context) -> ModelResponse:
    """The same call, forever. `call_id` is constant too, but it is not part of
    the identity — the tool, the arguments and the outcome are."""
    return ModelResponse(
        provider="test", provider_state=b"s", text="", spend_usd=0.0,
        spend_provenance=PROVENANCE_OPERATOR,
        tool_calls=(ToolCall(index=0, call_id="c0", name="t", arguments={}),))


def test_a_repeating_agent_ends_in_no_progress_and_not_at_the_turn_ceiling(
    tmp_path,
) -> None:
    """The member, produced. And the *distinction* is the assertion.

    A run that ended at `terminated.turn_ceiling_reached` would also have
    stopped, so an arm asserting only "the session ended" would pass with the
    predicate deleted. FR-006's whole complaint about an unset threshold is
    that the session ends under the wrong name, so the name is what is read.
    """
    # The turn ceiling is 10 rather than 50 on purpose, and it is below T065's
    # call-count backstop of 20. **Measured, not assumed**: with the stall
    # check removed this run reaches the backstop at 20 calls, so a ceiling
    # above it would make the alternative outcome `BackstopTripped` and this
    # arm would be distinguishing the stall from something it does not name.
    # At 10 the alternative really is `terminated.turn_ceiling_reached`.
    rig = Rig(tmp_path, threshold=3, turns=10)
    outcome = rig.loop(_repeating_model).run("p")

    assert outcome.terminal_state == terminal.NO_PROGRESS.name
    assert rig.lifecycle.get(SESSION).terminal_state == terminal.NO_PROGRESS.name
    # Turn 0 makes the call for the first time; turns 1-3 repeat it; the check
    # at the top of the fifth iteration sees a run of three and fires. Read as
    # a bound rather than as an equality on a count this arm does not control:
    # what matters is that it stopped short of the ceiling it would otherwise
    # have been recorded under.
    assert len(outcome.turns) < 10
    rig.close()


def test_the_marker_and_the_reading_reach_the_record(tmp_path) -> None:
    """T066's marker for T067's member, and the predicate input beside it.

    The reading is the whole content of this outcome — `terminated.no_progress`
    alone says a threshold nobody can see was crossed — so an operator reading
    the trace has to find the observed run and the declared threshold on it.
    """
    import json

    rig = Rig(tmp_path, threshold=2, turns=50)
    outcome = rig.loop(_repeating_model).run("p")
    assert outcome.end_of_run is not None
    assert outcome.end_of_run.reason == "no_progress"

    spans = [json.loads(r["payload"]) for r in rig.spans.spans(SESSION)]
    ends = [s for s in spans if s["terminal_state"] == terminal.NO_PROGRESS.name]
    assert len(ends) == 1, f"expected one terminal span, got {len(ends)}"
    span = ends[0]
    assert span["detail"]["end_of_run"]["reason"] == "no_progress"

    readings = span["transition"]["predicate_inputs"]
    assert len(readings) == 1 and readings[0]["matched"] is True
    assert readings[0]["declared"] == "2", (
        f"the declared threshold is not on the record: {readings[0]!r}. "
        "Without it a reader cannot tell a tight threshold from a stalled "
        "agent.")
    assert int(readings[0]["observed"]) >= 2
    rig.close()


def test_the_bare_terminate_refuses_this_member(tmp_path) -> None:
    """The guard that stops the reading being dropped at the call site.

    `terminate()` would take a bare name and build a transition with no
    predicate inputs — which `StateTransition` refuses, but only after the row
    has been decided. Refusing here names the method to use instead.
    """
    rig = Rig(tmp_path, threshold=3)
    with pytest.raises(SessionStateError, match="terminate_on_stall"):
        rig.machine.terminate(
            SESSION, terminal_state=terminal.NO_PROGRESS.name, at=1.0)
    assert rig.lifecycle.get(SESSION).state == "RUNNING", (
        "the row moved before the refusal, so a session was terminated with "
        "an outcome the record cannot explain")
    rig.close()


def test_a_verdict_that_is_not_a_stall_cannot_terminate(tmp_path) -> None:
    rig = Rig(tmp_path, threshold=3)
    verdict = evaluate_stall([], StallPolicy(consecutive_turns=3))
    with pytest.raises(SessionStateError, match="not a stall"):
        rig.machine.terminate_on_stall(SESSION, verdict, at=1.0)
    rig.close()


def test_the_count_carries_across_an_attempt_boundary(tmp_path) -> None:
    """The property the predicate is derived rather than counted in order to have.

    FR-007 resumes a session **in a new process** after a `SIGKILL`. A count
    held on the loop object would start again at zero there, and an agent that
    stalls, crashes and goes on stalling would reset its own stall count at
    every crash and never terminate. Two `AgentLoop` objects over one store is
    the same discriminator `tests/unit/test_loop.py`'s ceiling arm uses — it
    drops the loop between turns for exactly this reason.

    **The arms are categorical, not a turn count.** The second attempt is
    bounded to one turn, so a count that restarted would leave the session
    resumable with no terminal state at all, and a count that carried fires on
    the turn after. Nothing here reads how many turns happened.
    """
    rig = Rig(tmp_path, threshold=3, turns=50)

    first = rig.loop(_repeating_model).run("p", max_turns_this_attempt=3)
    assert first.terminal_state is None, "the first attempt was not bounded short"

    second = rig.loop(_repeating_model).run("p", max_turns_this_attempt=1)
    assert second.terminal_state == terminal.NO_PROGRESS.name, (
        "the second attempt did not reach the threshold. The three turns the "
        "first attempt journalled were not counted, so the stall count is a "
        "property of the process rather than of the session — which is the "
        "shape that never terminates under FR-007.")
    rig.close()


def test_a_turn_with_no_tool_calls_still_completes_the_run(tmp_path) -> None:
    """The assumption the predicate's first limb rests on, asserted.

    FR-006 says a turn that produces the session's reported result makes
    progress. In this runtime that is a turn with no tool calls, and the loop
    completes on it. If that ever stopped being true, the predicate would start
    seeing a shape it has never seen and this arm is what says so.
    """
    rig = Rig(tmp_path, threshold=1, turns=50)
    outcome = rig.loop(lambda c: ModelResponse(
        provider="test", provider_state=b"s", text="the answer",
        spend_usd=0.0, spend_provenance=PROVENANCE_OPERATOR)).run("p")

    assert outcome.terminal_state == terminal.COMPLETED.name, (
        "with a threshold of one, a first turn read as making no progress "
        "would end this run as a stall")
    rig.close()
