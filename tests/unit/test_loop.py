"""T041, T042 — the turn loop, `TurnRecord` construction and the context assembler.

**The opaque-state arms are the ones to read first.** Output-checking tests are
blind to opaque-state loss: a loop that dropped `provider_state` between turns
still produces plausible answers, and every assertion on the answer passes. So
conformance here asserts a **digest** of the state that went out against the
digest of the state that came in, per turn. FR-037 requires it captured verbatim
and re-injected verbatim, and a digest is the only assertion that can tell
"re-injected" from "regenerated".

The other load-bearing arms:

- **Ceilings are consulted before every turn, from the journal.** Finding 006
  measured a ceiling of 3 permitting 6 cycles because the counter lived on a
  context rebuilt per attempt. The arm here drops the loop object between turns
  and asserts the ceiling still bites, because a loop holding its own turn count
  passes every other test in this file.
- **Parallel calls are journalled in declared order**, asserted on a run whose
  completion order provably differed.
- **Every tool result carries FR-058's bound and its seven span fields**,
  including the calls where nothing was withheld.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json

import pytest

from src.contracts import terminal
from src.contracts.repository import Repository
from src.runtime.context import ContextAssembler
from src.runtime.loop import AgentLoop, LoopError, ModelResponse, TurnRecord
from src.runtime.dispatch import ToolCall
from src.runtime.providers.adapter import model_response
from src.runtime.providers.base import ParsedTurn
from src.runtime.providers import costs
from src.runtime.providers.costs import PROVENANCE_OPERATOR
from src.runtime.turn import UnpricedTurnError
from src.runtime.result_bound import ResultBound, RetentionStore
from src.runtime.session_state import SessionStateMachine
from src.runtime.session_store import Ceilings, SessionStore
from src.runtime.trace import ArtifactVersions, SpanWriter, TOOL_CALL
from src.runtime.journal import (
    MODEL_STEP_INDEX,
    STEP_MODEL_CALL,
    TurnJournal,
)
from src.runtime.ledger import BudgetLedger, ReservationPolicy
from src.runtime.resume import encode_model_outcome
from src.runtime.trace_budget import BudgetJournal
from src.supervisor.session_table import SessionTable, capability_digest

TENANT, DEPLOYMENT, SESSION = "t-1", "d-1", "sess-1"
LEASE = 2_000_000_000.0
VERSIONS = ArtifactVersions(TENANT, DEPLOYMENT, {"prompt": "sha256:" + "0" * 64})


class Tok:
    name = "test-tok"

    def count(self, text: str) -> int:
        return max(1, len(text) // 4)


def _ceilings(**over) -> Ceilings:
    values = {"spend_usd": 100.0, "tokens": 1_000_000,
              "wall_clock_seconds": 10_000.0, "turns": 10}
    values.update(over)
    return Ceilings(
        spend_usd=values["spend_usd"], tokens=int(values["tokens"]),
        wall_clock_seconds=values["wall_clock_seconds"], turns=int(values["turns"]))


class Harness:
    """Everything a loop needs, built over one temporary directory."""

    def __init__(self, tmp_path, *, ceilings: Ceilings | None = None,
                 bound_tokens: int = 500, reserve_wall_clock: float = 0.0):
        self.tmp_path = tmp_path
        self.lifecycle = SessionTable(tmp_path / "session.sqlite3")
        self.lifecycle.create(
            session_id=SESSION, tenant_id=TENANT, deployment_id=DEPLOYMENT,
            capability_sha256=capability_digest("h"), lease_expires_at=LEASE,
            now=1.0)
        self.repo = Repository(tmp_path / "runtime.sqlite3", role="runtime",
                               tenant_id=TENANT, deployment_id=DEPLOYMENT)
        self.store = SessionStore(self.repo, lifecycle=self.lifecycle)
        self.store.create(session_id=SESSION, ceilings=ceilings or _ceilings())
        self.budget = BudgetLedger(
            BudgetJournal(self.repo, session_root=tmp_path / "session-root"),
            # Small but non-zero. Zero would exercise the reserve/reconcile
            # wiring while asserting nothing about it; large enough to reach a
            # ceiling would make every arm in this file a budget test.
            #
            # `wall_clock_seconds` is **zero by default here and stated rather
            # than omitted**, because the arms below measure what the loop
            # *accrues*: a non-zero reservation would put a figure on that
            # dimension that no elapsed interval produced, and an arm asserting
            # an exact elapsed total could then pass on the estimate alone.
            policy=ReservationPolicy(spend_usd=0.001, tokens=1,
                                     wall_clock_seconds=reserve_wall_clock))
        self.journal = TurnJournal(self.repo)
        self.spans = SpanWriter(self.repo)
        self.machine = SessionStateMachine(self.lifecycle)
        self.bound = ResultBound(bound_tokens=bound_tokens,
                                 context_window_tokens=bound_tokens * 20,
                                 tokenizer=Tok())
        self.retention = RetentionStore(root=tmp_path / "scratch",
                                        session_id=SESSION, max_bytes=1_000_000)

    def loop(self, model, execute, *, clock=None) -> AgentLoop:
        return AgentLoop(
            session_id=SESSION,
            store=self.store,
            budget=self.budget,
            journal=self.journal,
            spans=self.spans,
            machine=self.machine,
            bound=self.bound,
            retention=self.retention,
            model=model,
            execute=execute,
            versions=VERSIONS,
            clock=clock or _clock(),
        )

    def close(self):
        self.repo.close()
        self.lifecycle.close()


def _clock():
    counter = {"n": 0.0}

    def now() -> float:
        counter["n"] += 1.0
        return counter["n"]

    return now


class WorkClock:
    """A clock that moves when work happens and not when it is read.

    The default `_clock()` above advances on every read, which is fine for the
    arms that only need distinct timestamps and **wrong** for any arm about
    *how much* time a turn took: under it the elapsed figure is a property of
    how many times the loop happened to call `self.clock()`, so a refactor that
    added one read would change the measurement.
    `tests/fixtures/resume_session.py` records the same hazard from the other
    side.

    Here reading is free and the test says when time passes, from inside the
    model stub and the tool body. So a turn's elapsed total is exactly the work
    that turn did, on any host — which is what lets the arms below assert an
    equality rather than an inequality against a wall clock they do not own.
    """

    def __init__(self, start: float = 1_000.0) -> None:
        self.t = start

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


def _model(*turns):
    """A provider stub that returns `turns` in order, then refuses."""
    seen = {"i": 0}

    def call(context):
        i = seen["i"]
        seen["i"] += 1
        if i >= len(turns):
            raise AssertionError(
                f"the loop asked for turn {i} and the stub has {len(turns)}; "
                "the loop did not terminate when the provider stopped asking "
                "for tools"
            )
        response = turns[i]
        return response(context) if callable(response) else response

    call.seen = seen
    return call


# **Why these declare `spend_usd=0.0` rather than leaving it unset.**
# `ModelResponse.spend_usd` defaults to `None`, meaning *nothing priced this
# turn*, and `AgentLoop` refuses such a response rather than accruing zero for
# it — that refusal is the whole point of the field's type. These fakes are a
# different case from an unpriced one: `provider="test"` reaches no vendor, so
# the turn genuinely costs nothing and `0.0` is the measurement rather than a
# stand-in for a figure nobody computed. A test that wants a spend states one,
# as `test_the_reconciled_spend_...` below does.
#
# **And why the provenance beside it is `operator` and not `vendor`.** OD-27
# requires a spend to say where its rate came from, and these zeros came from
# no vendor page — there is no page for `provider="test"`. They came from this
# harness deciding what a fake call costs, which is a declaration and is the
# state `PROVENANCE_OPERATOR` names. Writing `vendor` here would be the fake
# claiming a source it does not have, in the one field that exists to tell
# those apart.
def _finish(text: str = "done", **kw) -> ModelResponse:
    kw.setdefault("spend_usd", 0.0)
    kw.setdefault("spend_provenance", PROVENANCE_OPERATOR)
    return ModelResponse(provider="test", provider_state=b"state", text=text,
                         tool_calls=(), **kw)


def _asks(*names, state: bytes = b"state", **kw) -> ModelResponse:
    kw.setdefault("spend_usd", 0.0)
    kw.setdefault("spend_provenance", PROVENANCE_OPERATOR)
    return ModelResponse(
        provider="test", provider_state=state, text="", tool_calls=tuple(
            ToolCall(index=i, call_id=f"c{i}", name=name)
            for i, name in enumerate(names)
        ), **kw)


# ---------------------------------------------------------------------------
# A turn that runs.


def test_a_single_turn_with_no_tools_completes(tmp_path) -> None:
    h = Harness(tmp_path)
    h.machine.start(SESSION, at=1.0)
    outcome = h.loop(_model(_finish("the answer")), lambda call: "").run("prompt")

    assert outcome.terminal_state == terminal.COMPLETED.name
    assert outcome.text == "the answer"
    assert len(outcome.turns) == 1
    assert outcome.turns[0].turn_index == 0
    assert h.lifecycle.get(SESSION).state == "TERMINATED"
    h.close()


def test_turn_indexes_are_dense_and_monotonic(tmp_path) -> None:
    """`data-model.md` §2.2's first field, asserted rather than assumed."""
    h = Harness(tmp_path)
    h.machine.start(SESSION, at=1.0)
    outcome = h.loop(
        _model(_asks("a"), _asks("b"), _asks("c"), _finish()),
        lambda call: "result",
    ).run("prompt")

    assert [t.turn_index for t in outcome.turns] == [0, 1, 2, 3]
    h.close()


def test_a_tool_call_produces_a_tool_call_span_with_the_bound_fields(tmp_path) -> None:
    h = Harness(tmp_path)
    h.machine.start(SESSION, at=1.0)
    h.loop(_model(_asks("small"), _finish()), lambda call: "tiny").run("p")

    tool_spans = [s for s in h.spans.spans(SESSION) if s["kind"] == TOOL_CALL]
    assert len(tool_spans) == 1
    import json
    payload = json.loads(tool_spans[0]["payload"])
    held = payload["result_bound"]
    assert held["bound_applied"] is True
    assert held["full_size"] == held["admitted"], (
        "nothing was withheld from a four-byte result, so the sizes must match"
    )
    assert held["unit"] == "tokens"
    h.close()


def test_a_result_over_the_bound_reaches_the_model_bounded(tmp_path) -> None:
    """The FR-058 path, end to end, asserted on what the *next* turn was sent."""
    h = Harness(tmp_path, bound_tokens=60)
    h.machine.start(SESSION, at=1.0)
    seen_contexts: list = []

    def model(context):
        seen_contexts.append(context)
        return _asks("big") if len(seen_contexts) == 1 else _finish()

    huge = "x" * 100_000
    h.loop(model, lambda call: huge).run("p")

    second = seen_contexts[1]
    rendered = second.render()
    assert huge not in rendered, "the unbounded body reached the model's context"
    assert "bounded result" in rendered
    assert Tok().count(rendered) <= second.budget_tokens
    h.close()


# ---------------------------------------------------------------------------
# Opaque state — a digest, never the answer.


def test_provider_state_is_reinjected_verbatim(tmp_path) -> None:
    """FR-037. The assertion is on a digest of the bytes, not on the text.

    A loop that regenerated the state, re-encoded it, or dropped it entirely
    would produce the same answers and fail only here.
    """
    h = Harness(tmp_path)
    h.machine.start(SESSION, at=1.0)
    states = [b"\x00opaque-one\xff", b"\x01opaque-two\xfe"]
    injected: list = []

    def model(context):
        injected.append(context.provider_states)
        i = len(injected) - 1
        return _asks("t", state=states[i]) if i < 1 else _finish()

    outcome = h.loop(model, lambda call: "r").run("p")

    assert injected[0] == (), "the first turn has no prior state to carry"
    assert injected[1] == (states[0],), (
        "the state the second turn was given is not the bytes the first turn "
        "returned. Re-injected verbatim is the requirement; re-encoded is not "
        "re-injected."
    )
    digests = [t.provider_state_digest for t in outcome.turns]
    assert digests[0] == "sha256:" + hashlib.sha256(states[0]).hexdigest()
    h.close()


def test_no_trace_span_carries_provider_state_in_readable_form(tmp_path) -> None:
    """FR-037 and trace-record.md: opaque, round-tripped, never logged readably."""
    h = Harness(tmp_path)
    h.machine.start(SESSION, at=1.0)
    marker = b"OPAQUE-REASONING-MARKER-8f3a"
    h.loop(_model(_asks("t", state=marker), _finish()), lambda c: "r").run("p")

    for row in h.spans.spans(SESSION):
        assert marker.decode() not in row["payload"], (
            f"a {row['kind']} span carries the provider's opaque state in "
            "readable form. It may contain provider reasoning and is "
            "round-tripped rather than inspected."
        )
    h.close()


def test_the_turn_record_exposes_a_digest_and_not_the_bytes(tmp_path) -> None:
    h = Harness(tmp_path)
    h.machine.start(SESSION, at=1.0)
    outcome = h.loop(_model(_finish()), lambda c: "").run("p")
    record = outcome.turns[0].to_record()

    assert "provider_state" not in record
    assert record["provider_state_digest"].startswith("sha256:")
    h.close()


def test_every_earlier_turns_state_is_handed_over_in_order(tmp_path) -> None:
    """T-02: never merged. FR-037: **never dropped.**

    ~~The loop hands over the last turn's state and does not accumulate. A loop
    that concatenated states, or that kept the first one, would still produce
    plausible answers.~~ **Rewritten 2026-08-05.** The struck text asserted the
    defect. `states_for` returned a single blob, and all four vendors want
    every state in the current turn: OpenAI *"preserve and replay every
    returned reasoning item"*, Google validates every step of the turn and 400s
    on a miss, xAI *"always pass the full output array back verbatim"*, and an
    Anthropic tool-use loop is one assistant turn within which every thinking
    block must come back. What survives unchanged is *why* this reads the bytes
    rather than the text: a loop that lost them still answers plausibly.

    Order is asserted as well as membership. The states are positionally
    aligned with the assistant entries a driver builds, so a reordering
    attaches one turn's reasoning to another — a request every provider accepts.

    **What this cannot assert, and where that property lives instead.** The
    cross-provider drop is not observable here: the loop calls one provider and
    learns which one only from the response, so it never has the chance to hand
    provider two something of provider one's. The drop is a property of the
    assembler, and `test_the_context_carries_only_the_current_providers_state`
    is the arm on it.
    """
    h = Harness(tmp_path)
    h.machine.start(SESSION, at=1.0)
    injected: list = []
    produced = [b"\x01first", b"\x02second", b"\x03third"]

    def model(context):
        i = len(injected)
        injected.append(context.provider_states)
        if i < 3:
            return _asks("t", state=produced[i])
        return _finish()

    h.loop(model, lambda c: "r").run("p")

    assert injected == [
        (),
        (produced[0],),
        (produced[0], produced[1]),
        (produced[0], produced[1], produced[2]),
    ], "the chain handed to each turn is not every earlier turn's, in order"
    h.close()


# ---------------------------------------------------------------------------
# Ceilings, across a rebuilt loop.


def test_the_turn_ceiling_stops_the_loop_and_names_its_terminal_state(tmp_path) -> None:
    h = Harness(tmp_path, ceilings=_ceilings(turns=3))
    h.machine.start(SESSION, at=1.0)
    outcome = h.loop(
        _model(*[_asks("t")] * 10), lambda c: "r").run("p")

    assert outcome.terminal_state == terminal.TURN_CEILING.name
    assert len(outcome.turns) == 3, (
        f"{len(outcome.turns)} turns ran against a ceiling of 3"
    )
    assert h.lifecycle.get(SESSION).terminal_state == terminal.TURN_CEILING.name
    h.close()


def test_a_ceiling_is_not_restarted_by_a_second_loop_over_the_same_session(
    tmp_path,
) -> None:
    """Finding 006's measurement, at the loop rather than at the store.

    Two loops, the second built after the first is gone, against a ceiling of 3.
    A loop counting its own turns lets the second one run three more — which is
    the ceiling of 3 permitting 6 that finding 006 measured, and every
    individual loop is compliant.

    **What this arm counts changed with T052.** It used to count the records the
    second attempt returned, which is now the session's transcript rather than
    the attempt's, so the number would be three whether one turn ran or three
    did. It counts **provider calls** instead — which is the thing the ceiling is
    supposed to bound and the thing a restarted count would let happen more of.
    """
    h = Harness(tmp_path, ceilings=_ceilings(turns=3))
    h.machine.start(SESSION, at=1.0)
    first_model = _model(*[_asks("t")] * 2)
    first = h.loop(first_model, lambda c: "r")
    first.run("p", max_turns_this_attempt=2)
    assert h.budget.totals(SESSION).turns == 2
    assert first_model.seen["i"] == 2

    del first
    second_model = _model(*[_asks("t")] * 10)
    outcome = h.loop(second_model, lambda c: "r").run("p")

    assert second_model.seen["i"] == 1, (
        f"the second attempt made {second_model.seen['i']} provider calls. Two "
        "turns ran before it and the ceiling is 3, so exactly one is left — "
        "more means the count restarted with the loop."
    )
    assert [t.turn_index for t in outcome.turns] == [0, 1, 2]
    assert outcome.terminal_state == terminal.TURN_CEILING.name
    assert h.budget.totals(SESSION).turns == 3
    h.close()


def test_the_token_ceiling_is_checked_against_the_journal(tmp_path) -> None:
    h = Harness(tmp_path, ceilings=_ceilings(tokens=50))
    h.machine.start(SESSION, at=1.0)
    outcome = h.loop(
        _model(*[_asks("t", tokens=30)] * 10), lambda c: "r").run("p")

    assert outcome.terminal_state == terminal.TOKEN_CEILING.name
    assert h.budget.totals(SESSION).tokens >= 50
    h.close()


# ---------------------------------------------------------------------------
# FR-005's spend dimension, priced end to end.
#
# **A wired path is not a firing ceiling, and this is the arm that tells them
# apart.** Before the pricing seam existed the wiring was complete —
# `reconcile` took a `spend_usd`, the ledger summed it, `ceiling_verdict`
# compared it and `terminated.spend_ceiling_reached` existed — and the ceiling
# still could not fire, because every `ModelResponse` carried the field's `0.0`
# default. That is the same shape finding 029 measured on wall clock:
# *"the comparison, the wiring and `terminated.wall_clock_ceiling_reached` all
# worked; the numerator was missing."* So these arms assert the **total**, not
# only the terminal state: a terminal state can be reached by a reservation
# left outstanding, and an exact total can only come from the table.


def _priced(*names: str, inputs: int = 1_000_000, outputs: int = 1_000_000,
            model: str = "claude-sonnet-5",
            provider: str = "anthropic") -> ModelResponse:
    """One turn, carried through the real adapter and priced by the real table.

    Deliberately not a hand-written `ModelResponse` with a plausible float on
    it. The subject here is that a *provider turn* reaches the ledger as money,
    so the arm has to start where a driver's output starts.
    """
    return model_response(
        ParsedTurn(
            provider=provider, text="", provider_state=b"state",
            input_tokens=inputs, output_tokens=outputs,
            tool_calls=tuple(
                ToolCall(index=i, call_id=f"c{i}", name=name)
                for i, name in enumerate(names)),
        ),
        model=model, as_of=dt.date(2026, 8, 5))


def test_the_spend_ceiling_fires_on_a_turn_priced_from_the_cost_table(
    tmp_path,
) -> None:
    """The planted case: real rates, a real ceiling, and it stops the session.

    `claude-sonnet-5` inside its introductory window is $2.00/Mtok in and
    $10.00/Mtok out, so a turn of one million each is **$12.00**. Against a
    $20.00 ceiling: turn 0 runs and accrues 12, turn 1 sees 12 < 20 and runs to
    24, turn 2 sees 24 >= 20 and terminates. Two turns, $24.00, and the figure
    is checkable against the table by hand.

    The token ceiling is lifted out of the way on purpose — two million tokens
    a turn would trip it first and this arm would then be measuring the wrong
    dimension while still going green.
    """
    h = Harness(tmp_path, ceilings=_ceilings(spend_usd=20.0, tokens=10 ** 9))
    h.machine.start(SESSION, at=1.0)

    outcome = h.loop(_model(*[_priced("t")] * 10), lambda c: "r").run("p")

    assert outcome.terminal_state == terminal.SPEND_CEILING.name
    assert len(outcome.turns) == 2, (
        "the ceiling should be reached at the top of the third turn"
    )
    # **The load-bearing assertion.** The reservation is $0.001 a turn, so a
    # session whose spend never got priced totals about $0.002 here and never
    # reaches $20 at all. Only the table produces $24.00.
    assert h.budget.totals(SESSION).spend_usd == pytest.approx(24.0)
    h.close()


def test_an_unpriced_turn_stops_the_loop_rather_than_accruing_zero(
    tmp_path,
) -> None:
    """The counterfactual, and the defect this whole seam removes.

    A response nobody priced used to accrue `0.0` and let the session run on
    under a spend ceiling that could never be reached. It now refuses at the
    reconcile, which is the earliest point the price could have been known.
    """
    h = Harness(tmp_path, ceilings=_ceilings(spend_usd=20.0))
    h.machine.start(SESSION, at=1.0)
    unpriced = ModelResponse(provider="anthropic", provider_state=b"state",
                             text="", tool_calls=(), tokens=2_000_000)

    with pytest.raises(UnpricedTurnError, match="counted at zero"):
        h.loop(_model(unpriced), lambda c: "r").run("p")

    # The reservation stays outstanding, which over-counts rather than under-
    # counts — the direction `ledger.py` argues for on a crash, arriving here
    # for the same reason: the turn happened and its cost is unknown.
    assert h.budget.totals(SESSION).spend_usd == pytest.approx(0.001)
    h.close()


def test_the_model_call_span_records_the_model_the_price_was_computed_at(
    tmp_path,
) -> None:
    """A spend figure with no model beside it is a number nobody can check.

    FR-038 requires an attribution reproducible from the trace alone, and the
    rate a turn was priced at is keyed on `(provider, model)`.
    """
    h = Harness(tmp_path, ceilings=_ceilings(spend_usd=1_000.0, tokens=10 ** 9))
    h.machine.start(SESSION, at=1.0)
    h.loop(_model(_priced()), lambda c: "r").run("p")

    spans = h.repo.select("trace_span", where={"kind": "model_call"})
    assert len(spans) == 1
    payload = json.loads(spans[0]["payload"])
    detail = payload["detail"]
    assert detail["provider"] == "anthropic"
    assert detail["model"] == "claude-sonnet-5"
    assert detail["input_tokens"] == 1_000_000
    assert detail["output_tokens"] == 1_000_000
    # The rate is `(provider, model, date)` and the span carries the first two,
    # so the figure beside them is recomputable rather than merely recorded.
    assert payload["cost"]["spend_usd"] == pytest.approx(12.0)
    h.close()


def test_the_span_says_whether_the_rate_was_published_or_declared(
    tmp_path,
) -> None:
    """OD-27 on the trace, and the argument is the arm above's continued.

    That arm carries `model` because a price is not reproducible without the
    row it came from. A rate an operator declared has **no row in this
    repository**, so a span naming only `(provider, model)` sends a later
    reader to `costs.PRICES` to check a figure that was never in it — and the
    conclusion they reach is that the table moved, not that the rate was never
    there. Both provenances are run here, because a span hardcoding either one
    satisfies the other half alone.
    """
    declared = costs.OperatorPriceBook([costs.OperatorPrice(
        provider="openai", model="gpt-5-mini", display_name="GPT-5 mini",
        tiers=(costs.Rate(0.25, 2.00),
               costs.Rate(0.50, 4.00, min_input_tokens=128_000)),
        declared_by="platform-eng@example.invalid",
        declaration_ref="contracts/openai-2026-q3.md",
        declared_on="2026-08-01",
        scope="standard synchronous tier, uncached input, text",
    )])

    h = Harness(tmp_path, ceilings=_ceilings(spend_usd=1_000.0, tokens=10 ** 9))
    h.machine.start(SESSION, at=1.0)
    h.loop(_model(
        # Asks for a tool, so the loop takes a second turn and the assertion
        # below compares two spans rather than describing one.
        _priced("t"),
        model_response(
            ParsedTurn(provider="openai", text="", provider_state=b"state",
                       input_tokens=1_000_000, output_tokens=0, tool_calls=()),
            model="gpt-5-mini", as_of=dt.date(2026, 8, 5),
            operator_prices=declared),
    ), lambda c: "r").run("p")

    spans = h.repo.select("trace_span", where={"kind": "model_call"})
    provenances = [json.loads(s["payload"])["detail"]["spend_provenance"]
                   for s in spans]
    assert provenances == [costs.PROVENANCE_VENDOR, costs.PROVENANCE_OPERATOR]
    h.close()


def test_a_loop_on_a_session_that_is_not_running_is_refused(tmp_path) -> None:
    h = Harness(tmp_path)
    with pytest.raises(LoopError, match="STARTING"):
        h.loop(_model(_finish()), lambda c: "").run("p")
    h.close()


# ---------------------------------------------------------------------------
# FR-005's fourth dimension: the elapsed time a turn actually took.
#
# `findings/029-wall-clock-ceiling-unenforced.md` measured a session run for
# 2.044 s under a ceiling of 0.001 s ending `terminated.completed`, against
# three controls on the same harness that fired and a fourth that fires this
# very ceiling at a ceiling of 0.0. So the comparison, the wiring and
# `terminated.wall_clock_ceiling_reached` all worked and the **numerator** was
# absent. These arms are that numerator, stated as behaviour.


def _timed_model(clock: WorkClock, *responses, seconds: float):
    """A provider stub whose call takes `seconds` of the test's clock."""
    inner = _model(*responses)

    def call(context):
        clock.advance(seconds)
        return inner(context)

    call.seen = inner.seen
    return call


def _timed_tool(clock: WorkClock, *, seconds: float):
    def run(_call) -> str:
        clock.advance(seconds)
        return "r"

    return run


def test_the_elapsed_time_a_turn_took_is_accrued_to_the_ledger(tmp_path) -> None:
    """The numerator, asserted as an exact figure rather than as `> 0`.

    Three turns; the first two ask for one tool each and the third finishes.
    Every model call costs 4 and every tool call costs 6, so the session spends
    `(4 + 6) + (4 + 6) + 4 = 24`. Both halves of a turn are named on purpose:
    an implementation that timed only the model call would produce 12 and pass
    a `> 0` assertion, and a session whose time goes into a tool that sleeps is
    the exact shape finding 029's arm 1 had.

    Read off `committed()` rather than `totals()`, because `totals()` includes
    outstanding reservations and this arm is about what was **measured**.
    """
    clock = WorkClock()
    h = Harness(tmp_path)
    h.machine.start(SESSION, at=1.0)

    outcome = h.loop(
        _timed_model(clock, _asks("t"), _asks("t"), _finish(), seconds=4.0),
        _timed_tool(clock, seconds=6.0),
        clock=clock,
    ).run("p")

    assert outcome.terminal_state == terminal.COMPLETED.name
    assert h.budget.committed(SESSION).wall_clock_seconds == pytest.approx(24.0), (
        "the session spent 24 seconds of the clock it was handed and the "
        f"ledger recorded {h.budget.committed(SESSION).wall_clock_seconds}. "
        "FR-005's fourth ceiling is compared against this number."
    )
    h.close()


def test_the_wall_clock_ceiling_stops_a_session_that_ran_too_long(tmp_path) -> None:
    """Finding 029's arm 1, inverted: the session must now stop.

    Twenty turns are available and the wall-clock ceiling permits three.
    `evaluate_ceilings` is `>=` and is read at the top of the loop, so the turn
    that takes the total to or past 25 is the last one that runs.

    **The other three ceilings are held far out of reach**, and the turn
    ceiling explicitly: the default is 10, and at 10 seconds a turn this arm
    would otherwise have ended `terminated.turn_ceiling_reached` — failing
    today for a reason that has nothing to do with wall clock, and passing
    tomorrow for one.
    """
    clock = WorkClock()
    h = Harness(tmp_path,
                ceilings=_ceilings(wall_clock_seconds=25.0, turns=100))
    h.machine.start(SESSION, at=1.0)

    outcome = h.loop(
        _timed_model(clock, *[_asks("t")] * 20, seconds=4.0),
        _timed_tool(clock, seconds=6.0),
        clock=clock,
    ).run("p")

    assert outcome.terminal_state == terminal.WALL_CLOCK_CEILING.name, (
        f"the session ended {outcome.terminal_state!r} after spending "
        f"{h.budget.totals(SESSION).wall_clock_seconds} against a ceiling of "
        "25. This is the arm finding 029 measured completing at 2.044 s under "
        "a ceiling of 0.001 s."
    )
    assert len(outcome.turns) == 3, (
        f"{len(outcome.turns)} turns at 10 seconds each under a ceiling of 25"
    )
    h.close()


def test_the_wall_clock_terminal_is_decided_by_duration_and_not_by_the_reservation(
    tmp_path,
) -> None:
    """The defect finding 029 called the **inverse** of a ceiling, as one arm.

    Two sessions, identical in every input a ceiling reads — same ceiling, same
    reservation policy, same turn count available — and differing only in **how
    long a turn takes**. A dimension that is enforced distinguishes them. A
    dimension whose only content is the reservation estimate cannot, because
    the estimate is a property of the configuration and not of the run: before
    this arm both sessions ended `terminated.completed`, at any duration.

    Written as a pair rather than as a single slow session on purpose. A single
    session terminating proves the ceiling can fire; only the fast arm beside
    it proves that what fired it was the time and not the configuration the two
    share. The turn ceiling is lifted on both, so neither can end on the one
    ceiling that would make the two look different for another reason.
    """
    slow_clock, fast_clock = WorkClock(), WorkClock()
    ceilings = _ceilings(wall_clock_seconds=25.0, turns=100)
    slow = Harness(tmp_path / "slow", ceilings=ceilings)
    fast = Harness(tmp_path / "fast", ceilings=ceilings)
    slow.machine.start(SESSION, at=1.0)
    fast.machine.start(SESSION, at=1.0)

    slow_outcome = slow.loop(
        _timed_model(slow_clock, *[_asks("t")] * 20, seconds=4.0),
        _timed_tool(slow_clock, seconds=6.0),
        clock=slow_clock,
    ).run("p")
    fast_outcome = fast.loop(
        _timed_model(fast_clock, _asks("t"), _asks("t"), _finish(), seconds=0.4),
        _timed_tool(fast_clock, seconds=0.6),
        clock=fast_clock,
    ).run("p")

    assert slow_outcome.terminal_state == terminal.WALL_CLOCK_CEILING.name
    assert fast_outcome.terminal_state == terminal.COMPLETED.name
    assert slow_outcome.terminal_state != fast_outcome.terminal_state, (
        "two sessions with the same ceiling and the same reservation ended the "
        "same way at 10 seconds a turn and at 1 second a turn. The dimension "
        "is blind to duration, which is what makes it fire on failure rather "
        "than on time."
    )
    slow.close()
    fast.close()


def test_a_crash_inside_a_model_call_still_counts_its_wall_clock_estimate(
    tmp_path,
) -> None:
    """The over-count T053 built, held in place while the numerator lands.

    FR-005: *"A crash MUST NOT reduce the total counted against any of the
    four ceilings."* The reservation is what supplies that on this dimension,
    and the tempting repair for finding 029's crash arm — release the orphan,
    since it describes a call that never returned — would delete it.

    The turn below has a model-call intent and no outcome, and a reservation
    that was never reconciled: the state a `SIGKILL` inside `self.model(...)`
    leaves. Its estimate must still be in the total after the loop that
    resumes past it has finished, alongside the elapsed time the resumed
    attempt really spent. Both, not either.
    """
    clock = WorkClock()
    h = Harness(tmp_path, reserve_wall_clock=5.0)
    h.machine.start(SESSION, at=1.0)
    _abandoned_turn(h, 0)
    h.budget.reserve(SESSION, turn=0, at=100.0)

    h.loop(
        _timed_model(clock, _finish(), seconds=4.0),
        _timed_tool(clock, seconds=6.0),
        clock=clock,
    ).run("p")

    committed = h.budget.committed(SESSION).wall_clock_seconds
    total = h.budget.totals(SESSION).wall_clock_seconds
    assert committed == pytest.approx(4.0), (
        f"the resumed attempt measured {committed} seconds; its one turn made "
        "a 4-second model call and no tool call"
    )
    assert total == pytest.approx(9.0), (
        f"the total is {total}. The orphaned reservation of 5 has to keep "
        "counting — that is the over-count FR-005's crash clause requires — "
        "and the 4 seconds the resume really spent has to be counted beside "
        "it. A total of 4 means the orphan was released; a total of 5 means "
        "nothing was measured."
    )
    h.close()


# ---------------------------------------------------------------------------
# T051/T052/T053 at the loop: what a crash-shaped journal makes the loop do.


def _abandoned_turn(h: Harness, turn_index: int, *, at: float = 100.0) -> None:
    """Journal a turn's model-call intent and no outcome.

    This is what a `SIGKILL` between the two commit points leaves behind, built
    directly rather than by killing a process, so the arm reading it is a unit
    test. The cross-process version is `tests/integration/test_resume_sigkill.py`
    and neither substitutes for the other: this one asserts what the loop *does*
    with the state, that one asserts the state is what a real kill produces.
    """
    h.journal.intend(
        session_id=SESSION, turn_index=turn_index,
        step_index=MODEL_STEP_INDEX, step_kind=STEP_MODEL_CALL,
        effect_id="model", effectful=True, payload={"killed": True}, at=at)


def _completed_turn(h: Harness, turn_index: int, response, *,
                    at: float = 10.0) -> None:
    h.journal.intend(
        session_id=SESSION, turn_index=turn_index,
        step_index=MODEL_STEP_INDEX, step_kind=STEP_MODEL_CALL,
        effect_id="model", effectful=True, payload={}, at=at)
    h.journal.commit_outcome(
        session_id=SESSION, turn_index=turn_index,
        step_index=MODEL_STEP_INDEX, payload=encode_model_outcome(response),
        provider_state=response.provider_state, at=at + 1.0)


def test_an_abandoned_turns_index_is_never_handed_back_out(tmp_path) -> None:
    """The case where the journal's count and this attempt's count differ.

    Turn 0 completed; turn 1's model call was intended and never came back. A
    loop numbering from `len(turns)` sees one reconstructed record and calls the
    next turn 1 — re-issuing a call that may already have reached the provider,
    and colliding with turn 1's existing intent on T051's key.

    Both halves are read: the new turn is 2, and turn 1's payload is still the
    one the killed attempt wrote.
    """
    h = Harness(tmp_path)
    h.machine.start(SESSION, at=1.0)
    _completed_turn(h, 0, _asks("t"))
    h.journal.intend(
        session_id=SESSION, turn_index=0, step_index=1,
        step_kind="tool_call", effect_id="c0", effectful=True,
        payload={}, at=12.0)
    h.journal.commit_outcome(
        session_id=SESSION, turn_index=0, step_index=1,
        payload={"outcome": "ok", "body": "r", "started_at": 12.0,
                 "finished_at": 13.0, "writes": {}}, at=13.0)
    _abandoned_turn(h, 1)

    outcome = h.loop(_model(_finish("after the crash")), lambda c: "r").run("p")

    assert [t.turn_index for t in outcome.turns] == [0, 2], (
        f"turns {[t.turn_index for t in outcome.turns]}. Turn 1 was abandoned; "
        "its index is consumed and the gap is the safe direction, because "
        "reusing it would re-issue a paid call."
    )
    assert h.journal.step(SESSION, 1, MODEL_STEP_INDEX).intent == {"killed": True}
    h.close()


def test_a_completed_inner_turn_is_not_re_executed(tmp_path) -> None:
    """Finding 006's 4-of-4, at the loop.

    Four turns are journalled complete before the loop starts. The provider stub
    holds exactly one response, so a loop that replayed any of the four would
    raise from the stub rather than fail an assertion — which is the failure this
    arm is for.
    """
    h = Harness(tmp_path)
    h.machine.start(SESSION, at=1.0)
    for turn in range(4):
        _completed_turn(h, turn, _finish(f"turn {turn}"), at=10.0 + turn * 10)

    model = _model(_finish("the fifth"))
    outcome = h.loop(model, lambda c: "r").run("p")

    assert model.seen["i"] == 1, (
        f"the provider was called {model.seen['i']} times. Four turns were "
        "already complete; finding 006 measured all four re-executing."
    )
    assert [t.turn_index for t in outcome.turns] == [0, 1, 2, 3, 4]
    assert [t.text for t in outcome.turns[:4]] == [
        "turn 0", "turn 1", "turn 2", "turn 3"]
    h.close()


def test_a_recorded_tool_result_is_not_re_executed_on_resume(tmp_path) -> None:
    """The step half of the granularity, and FR-007's *no repeat* clause.

    Turn 0's model call finished and declared two tools; the first ran and was
    recorded, the second did not. On resume only the second may execute, and the
    first's recorded body has to survive rather than being produced again.
    """
    h = Harness(tmp_path)
    h.machine.start(SESSION, at=1.0)
    _completed_turn(h, 0, _asks("a", "b"))
    h.journal.intend(
        session_id=SESSION, turn_index=0, step_index=1,
        step_kind="tool_call", effect_id="c0", effectful=True,
        payload={}, at=12.0)
    h.journal.commit_outcome(
        session_id=SESSION, turn_index=0, step_index=1,
        payload={"outcome": "ok", "body": "ran before the crash",
                 "started_at": 12.0, "finished_at": 13.0, "writes": {}},
        at=13.0)

    executed: list[str] = []

    def execute(call: ToolCall) -> str:
        executed.append(call.call_id)
        return "ran after the crash"

    outcome = h.loop(_model(_finish()), execute).run("p")

    assert executed == ["c1"], (
        f"the resumed attempt executed {executed}. c0's outcome is on disk, so "
        "running it again is the repeat FR-007 forbids — and a tool with a "
        "local effect would have performed it twice."
    )
    resumed_turn = outcome.turns[0]
    assert resumed_turn.turn_index == 0
    assert [r.body for r in resumed_turn.tool_results] == [
        "ran before the crash", "ran after the crash"]
    assert [r.index for r in resumed_turn.tool_results] == [0, 1], (
        "the finished turn's results are out of declared order, so T-08's "
        "ordering did not survive the resume"
    )
    h.close()


def test_the_model_call_of_a_half_finished_turn_is_not_repeated(tmp_path) -> None:
    """A turn caught between its model call and its tools costs one call, not two.

    The provider stub holds one response and the run needs one — for the turn
    *after* the reconstructed one. If the half-finished turn re-called the
    provider it would consume that response and the run would end a turn early
    with the wrong text.
    """
    h = Harness(tmp_path)
    h.machine.start(SESSION, at=1.0)
    _completed_turn(h, 0, _asks("a"))

    model = _model(_finish("the turn after"))
    outcome = h.loop(model, lambda c: "r").run("p")

    assert model.seen["i"] == 1
    assert [t.turn_index for t in outcome.turns] == [0, 1]
    assert outcome.turns[0].text == "", "turn 0's reconstructed text is wrong"
    assert outcome.turns[1].text == "the turn after"
    h.close()


def test_the_reservation_counts_the_call_in_flight(tmp_path) -> None:
    """T053 at the loop, read from inside the model call.

    The totals are sampled *during* the provider call — which is the only moment
    the reservation is observable, and the moment a `SIGKILL` lands in the case
    U-30 names. A loop that accrued after the call would report zero here.
    """
    h = Harness(tmp_path)
    h.machine.start(SESSION, at=1.0)
    during: list = []

    def model(context):
        during.append(h.budget.totals(SESSION))
        return _finish(spend_usd=2.0, tokens=99)

    h.loop(model, lambda c: "r").run("p")

    assert during[0].turns == 1, (
        "the turn in flight was not counted, so a crash during the call would "
        "leave a resumed session believing the turn never happened"
    )
    assert during[0].spend_usd == pytest.approx(0.001)
    assert h.budget.totals(SESSION).spend_usd == pytest.approx(2.0), (
        "the reservation was not replaced by the measurement"
    )
    assert h.budget.outstanding(SESSION) == ()
    h.close()


def test_every_step_is_journalled_before_it_happens(tmp_path) -> None:
    """The write-ahead ordering, observed from inside the effect.

    Both callbacks read the journal at the moment they are called, so the
    assertion is about what was already committed when the effect began rather
    than about what the table holds afterwards.
    """
    h = Harness(tmp_path)
    h.machine.start(SESSION, at=1.0)
    at_model_time: list = []
    at_tool_time: list = []

    def model(context):
        at_model_time.append(h.journal.step(SESSION, 0, MODEL_STEP_INDEX))
        return _asks("a") if not at_model_time[1:] else _finish()

    def execute(call: ToolCall) -> str:
        at_tool_time.append(h.journal.step(SESSION, 0, 1))
        return "r"

    h.loop(model, execute).run("p")

    assert at_model_time[0] is not None, (
        "the model call was made with no intent journalled; a crash during it "
        "would leave no record that the turn was ever attempted"
    )
    assert at_model_time[0].is_complete is False
    assert at_tool_time[0] is not None, "the tool ran with no intent journalled"
    assert at_tool_time[0].is_complete is False
    assert h.journal.is_step_complete(SESSION, 0, 1) is True, (
        "the outcome was never committed after the effect finished"
    )
    h.close()


# ---------------------------------------------------------------------------
# Fan-out, in declared order.


def test_parallel_tool_calls_are_journalled_in_declared_order(tmp_path) -> None:
    """T-08 at the loop. The completion order is forced to differ first."""
    import threading

    h = Harness(tmp_path)
    h.machine.start(SESSION, at=1.0)
    gates = [threading.Event() for _ in range(4)]
    finished: list[int] = []
    lock = threading.Lock()

    def execute(call: ToolCall) -> str:
        # Call 0 waits for call 3, so completion order cannot be declared order.
        if call.index == 0:
            gates[3].wait(timeout=10)
        with lock:
            finished.append(call.index)
        gates[call.index].set()
        return f"body-{call.index}"

    outcome = h.loop(
        _model(_asks("a", "b", "c", "d"), _finish()), execute).run("p")

    assert finished[0] != 0, (
        f"completion order was {finished}; this run cannot distinguish "
        "declared order from completion order"
    )
    turn = outcome.turns[0]
    assert [r.index for r in turn.tool_results] == [0, 1, 2, 3]
    tool_spans = [s for s in h.spans.spans(SESSION) if s["kind"] == TOOL_CALL]
    import json
    recorded = [json.loads(s["payload"])["detail"]["index"] for s in tool_spans]
    assert recorded == [0, 1, 2, 3], (
        f"the tool_call spans are ordered {recorded}, which is the completion "
        "order T-08 forbids recording in"
    )
    h.close()
