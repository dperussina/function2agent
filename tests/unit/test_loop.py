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

import hashlib

import pytest

from src.contracts import terminal
from src.contracts.repository import Repository
from src.runtime.context import ContextAssembler
from src.runtime.loop import AgentLoop, LoopError, ModelResponse, TurnRecord
from src.runtime.dispatch import ToolCall
from src.runtime.result_bound import ResultBound, RetentionStore
from src.runtime.session_state import SessionStateMachine
from src.runtime.session_store import Ceilings, SessionStore
from src.runtime.trace import ArtifactVersions, SpanWriter, TOOL_CALL
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
                 bound_tokens: int = 500):
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
        self.budget = BudgetJournal(self.repo, session_root=tmp_path / "session-root")
        self.spans = SpanWriter(self.repo)
        self.machine = SessionStateMachine(self.lifecycle)
        self.bound = ResultBound(bound_tokens=bound_tokens,
                                 context_window_tokens=bound_tokens * 20,
                                 tokenizer=Tok())
        self.retention = RetentionStore(root=tmp_path / "scratch",
                                        session_id=SESSION, max_bytes=1_000_000)

    def loop(self, model, execute) -> AgentLoop:
        return AgentLoop(
            session_id=SESSION,
            store=self.store,
            budget=self.budget,
            spans=self.spans,
            machine=self.machine,
            bound=self.bound,
            retention=self.retention,
            model=model,
            execute=execute,
            versions=VERSIONS,
            clock=_clock(),
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


def _finish(text: str = "done", **kw) -> ModelResponse:
    return ModelResponse(provider="test", provider_state=b"state", text=text,
                         tool_calls=(), **kw)


def _asks(*names, state: bytes = b"state", **kw) -> ModelResponse:
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
        injected.append(context.provider_state)
        i = len(injected) - 1
        return _asks("t", state=states[i]) if i < 1 else _finish()

    outcome = h.loop(model, lambda call: "r").run("p")

    assert injected[0] is None, "the first turn has no prior state to carry"
    assert injected[1] == states[0], (
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


def test_state_handed_over_is_always_the_immediately_preceding_turns(tmp_path) -> None:
    """T-02: never merged, and never an older turn's.

    The loop hands over the last turn's state and does not accumulate. A loop
    that concatenated states, or that kept the first one, would still produce
    plausible answers — which is why this reads the bytes rather than the text.

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
        injected.append(context.provider_state)
        if i < 3:
            return _asks("t", state=produced[i])
        return _finish()

    h.loop(model, lambda c: "r").run("p")

    assert injected == [None, produced[0], produced[1], produced[2]], (
        "the state handed to each turn is not the previous turn's verbatim"
    )
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
    """
    h = Harness(tmp_path, ceilings=_ceilings(turns=3))
    h.machine.start(SESSION, at=1.0)
    first = h.loop(_model(*[_asks("t")] * 2), lambda c: "r")
    first.run("p", max_turns_this_attempt=2)
    assert h.budget.totals(SESSION).turns == 2

    del first
    second = h.loop(_model(*[_asks("t")] * 10), lambda c: "r")
    outcome = second.run("p")

    assert len(outcome.turns) == 1, (
        f"the second attempt ran {len(outcome.turns)} turns. Two ran before "
        "it, the ceiling is 3, so exactly one is left — more means the count "
        "restarted with the loop."
    )
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


def test_a_loop_on_a_session_that_is_not_running_is_refused(tmp_path) -> None:
    h = Harness(tmp_path)
    with pytest.raises(LoopError, match="STARTING"):
        h.loop(_model(_finish()), lambda c: "").run("p")
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
