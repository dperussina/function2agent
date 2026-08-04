"""T041 — the turn loop, turn dispatch, and `TurnRecord` construction.

The context assembler T042 names is in `context.py`; this module is the loop.


Constitution Principle III: **default to the loop.** This is a loop and not a
graph, and the topology is a `while` with a ceiling check at the top of it.

**Four properties this module exists to hold, each measured rather than imagined.**

1. **The ceiling is read from the journal at the top of every turn, never from a
   counter here.** Finding 006 measured a ceiling of 3 permitting 6 cycles
   because the counter lived on a context rebuilt per attempt, and the failure is
   invisible in review because every individual attempt is compliant. There is
   no turn count on `AgentLoop`. `max_turns_this_attempt` exists for tests and
   bounds *this attempt*; it cannot raise the session's ceiling.

2. **Opaque provider state is round-tripped and never inspected** (FR-037,
   T-02). It travels beside the rendered context rather than inside it, so
   nothing can serialize it by accident, and it is **dropped when the provider
   changes** because it is not a portable format. What reaches a trace is a
   digest.

3. **Tool calls fan out and are recorded in the provider's declared index
   order** (T-08), through `dispatch`. The loop does not re-sort: the dispatcher
   owns the order and the loop owns what to do with it.

4. **Every tool result is bounded before it enters the context** (FR-058), and
   every `tool_call` span carries the seven fields whether or not the bound bit.

**What this slice does not do, stated so it is not mistaken for done.** Turn
records are held for the life of the run and are not written to `turn_journal` —
that table, its `(session_id, turn_index, step_index)` key and the intent-before-
effect commit points are T051's, and resume reconstruction over them is T052's.
Consumption is accrued *after* the model call rather than reserved before it; the
reserve-then-reconcile half is capability 4's, and the direction matters (a crash
under this code under-counts the call in flight, where reserve-then-reconcile
over-counts). Both are named here because a reader of this module would otherwise
have to infer them from an absence.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Protocol, Sequence

from src.contracts import terminal
from src.contracts.transition import (
    ST_CEILING_REACHED,
    STATE_RUNNING,
    StateTransition,
)
from src.runtime.context import ByteTokenizer, Context, ContextAssembler
from src.runtime.dispatch import ToolCall, ToolResult, dispatch
from src.runtime.result_bound import BoundFields, ResultBound, RetentionStore
from src.runtime.session_state import SessionStateMachine
from src.runtime.session_store import SessionStore
from src.runtime.state_merge import Contribution, MergePolicy
from src.runtime.trace import (
    ATTEMPT_FIRST,
    ArtifactVersions,
    Cost,
    MODEL_CALL,
    OUTCOME_CEILING_REACHED,
    OUTCOME_OK,
    STATE_TRANSITION,
    Span,
    SpanWriter,
    TOOL_CALL,
)
from src.runtime.trace_budget import BudgetJournal, Consumption


class LoopError(RuntimeError):
    """A turn that cannot be run as described."""


@dataclass(frozen=True)
class ModelResponse:
    """One provider turn, above the adapter.

    `provider_state` is **opaque bytes, ours** (T-02, FR-037): captured
    verbatim, re-injected verbatim, never merged across providers, never
    interpreted. `None` is a provider that returned none, which is different
    from empty bytes.
    """

    provider: str
    provider_state: bytes | None
    text: str
    tool_calls: tuple[ToolCall, ...] = ()
    spend_usd: float = 0.0
    tokens: int = 0

    def __post_init__(self) -> None:
        if not self.provider:
            raise LoopError("a model response must name the provider")
        if self.provider_state is not None and not isinstance(
            self.provider_state, (bytes, bytearray)
        ):
            raise LoopError(
                "provider_state is opaque bytes. A str would have to be "
                "encoded, and an encoding is an interpretation — FR-037 "
                "requires the state re-injected verbatim."
            )


def state_digest(state: bytes | None) -> str | None:
    """The only form of the opaque state that may reach a record.

    A digest is what makes "re-injected verbatim" assertable without putting
    provider reasoning into a trace. `trace-record.md`: never written in a
    readable form.
    """
    if state is None:
        return None
    return "sha256:" + hashlib.sha256(bytes(state)).hexdigest()


@dataclass(frozen=True)
class TurnRecord:
    """`data-model.md` §2.2."""

    turn_index: int
    provider: str
    provider_state: bytes | None
    tool_calls: tuple[ToolCall, ...]
    tool_results: tuple[ToolResult, ...]
    text: str
    at: float

    def __post_init__(self) -> None:
        if self.turn_index < 0:
            raise LoopError("turn_index is a position, not a counter")
        declared = [c.index for c in self.tool_calls]
        if declared != sorted(declared):
            raise LoopError(
                f"tool_calls are held {declared}; §2.2 says the field is in "
                "the provider's declared index order, so a record holding "
                "them in another order is a record of something else."
            )
        got = [r.index for r in self.tool_results]
        if got != sorted(got):
            raise LoopError(f"tool_results are out of declared order: {got}")

    @property
    def provider_state_digest(self) -> str | None:
        return state_digest(self.provider_state)

    def to_record(self) -> dict[str, Any]:
        """**The opaque state is not in here, by construction.**

        Not redacted on the way out — absent. A field that is present and
        emptied is one somebody later fills in.
        """
        return {
            "turn_index": self.turn_index,
            "provider": self.provider,
            "provider_state_digest": self.provider_state_digest,
            "tool_calls": [
                {"index": c.index, "call_id": c.call_id, "name": c.name}
                for c in self.tool_calls
            ],
            "text": self.text,
            "at": self.at,
        }


@dataclass(frozen=True)
class LoopOutcome:
    """What one attempt produced.

    `terminal_state` is `None` when the attempt stopped without the session
    ending — cancelled, or bounded by `max_turns_this_attempt`. `None` rather
    than `""`: an empty string is a name, and FR-006's whole subject is that a
    session's recorded outcome is a named member of the taxonomy. A caller that
    writes `outcome.terminal_state` into a record would write `""` and pass any
    truthiness check on the way.
    """

    turns: tuple[TurnRecord, ...]
    terminal_state: str | None
    text: str
    cancelled: bool = False
    merged_state: Mapping[str, Any] = field(default_factory=dict)


class ModelClient(Protocol):
    def __call__(self, context: Context) -> ModelResponse: ...


class AgentLoop:
    """One session's turn loop. Holds no count that a ceiling depends on."""

    def __init__(
        self,
        *,
        session_id: str,
        store: SessionStore,
        budget: BudgetJournal,
        spans: SpanWriter,
        machine: SessionStateMachine,
        bound: ResultBound,
        retention: RetentionStore,
        model: ModelClient,
        execute: Callable[[ToolCall], str],
        versions: ArtifactVersions,
        clock: Callable[[], float],
        assembler: ContextAssembler | None = None,
        merge_policy: MergePolicy | None = None,
        cancel: Callable[[], bool] | None = None,
    ) -> None:
        self.session_id = session_id
        self.store = store
        self.budget = budget
        self.spans = spans
        self.machine = machine
        self.bound = bound
        self.retention = retention
        self.model = model
        self.execute = execute
        self.versions = versions
        self.clock = clock
        # The context budget defaults to the model's window minus one result
        # bound, so a full-size bounded result always fits into the next turn.
        self.assembler = assembler or ContextAssembler(
            budget_tokens=max(
                1, bound.context_window_tokens - bound.bound_tokens),
            tokenizer=bound.tokenizer or ByteTokenizer(),
        )
        self.merge_policy = merge_policy or MergePolicy(rules={})
        # Cancellation is cooperative and lands **at a turn boundary**. A turn in
        # flight finishes and is journalled rather than being abandoned: the
        # journal's turn count is what a ceiling and a resume both read, so a
        # turn accrued and then discarded would leave the two disagreeing with
        # nothing to say which is right. Killing work already in flight is the
        # sandbox's teardown and belongs to a later capability.
        self.cancel = cancel or (lambda: False)

    def run(
        self, prompt: str, *, max_turns_this_attempt: int | None = None
    ) -> LoopOutcome:
        """Run turns until a terminal state is reached, or until cancelled.

        `max_turns_this_attempt` bounds **this attempt** and is not a ceiling:
        it cannot raise FR-005's turn ceiling and reaching it produces no
        terminal state, because an attempt that stopped early has not ended the
        session. It exists so a test can produce the half-finished session that
        finding 006's crash-and-resume case needs.
        """
        session = self.store.load(self.session_id)
        if session is None:
            raise LoopError(f"{self.session_id!r} has no session")
        if session.state != STATE_RUNNING:
            raise LoopError(
                f"{self.session_id!r} is {session.state}, not {STATE_RUNNING}. "
                "A loop on a session the enforcement point will not honour "
                "would run without authority."
            )

        turns: list[TurnRecord] = []
        merged: dict[str, Any] = {}
        this_attempt = 0

        while True:
            # Cancellation is checked before the ceiling, so a consumer that
            # went away is not reported as having hit a limit. The two are
            # different events with different consequences: one is resumable and
            # the other is an ended session.
            if self.cancel():
                return LoopOutcome(
                    turns=tuple(turns), terminal_state=None,
                    text=turns[-1].text if turns else "",
                    cancelled=True, merged_state=merged)

            verdict = self.store.ceiling_verdict(self.session_id, self.budget)
            if verdict.exceeded:
                transition = self.machine.terminate_on_ceiling(
                    self.session_id, verdict, at=self.clock())
                self.write_transition_span(transition)
                return LoopOutcome(
                    turns=tuple(turns),
                    terminal_state=verdict.terminal_state,
                    text=turns[-1].text if turns else "",
                    merged_state=merged,
                )
            if (max_turns_this_attempt is not None
                    and this_attempt >= max_turns_this_attempt):
                return LoopOutcome(
                    turns=tuple(turns), terminal_state=None, text="",
                    merged_state=merged)

            # The turn index is the journalled turn count, not `len(turns)`.
            # `len(turns)` is this attempt's, and a resumed attempt would
            # restart the numbering §2.2 requires to be dense and monotonic
            # across the session.
            turn_index = self.budget.totals(self.session_id).turns
            record, writes = self._one_turn(prompt, turns, turn_index)
            turns.append(record)
            this_attempt += 1
            if writes:
                merged = self.merge_policy.merge(merged, writes)

            if not record.tool_calls:
                transition = self.machine.complete(
                    self.session_id, at=self.clock())
                self.write_transition_span(transition)
                return LoopOutcome(
                    turns=tuple(turns),
                    terminal_state=terminal.COMPLETED.name,
                    text=record.text,
                    merged_state=merged,
                )

    # -- one turn ----------------------------------------------------------

    def _one_turn(
        self, prompt: str, turns: Sequence[TurnRecord], turn_index: int
    ) -> tuple[TurnRecord, list[Contribution]]:
        previous_provider = turns[-1].provider if turns else None
        context = self.assembler.assemble(
            prompt=prompt, turns=turns,
            provider=previous_provider or _ANY_PROVIDER)
        response = self.model(context)

        # Accrued after the call, and the turn is counted here so the ceiling
        # check at the top of the next iteration sees it. Counting the turn
        # anywhere else would put the number the ceiling reads somewhere a crash
        # can lose.
        self.budget.accrue(Consumption(
            session_id=self.session_id, turn=turn_index, ordinal=0,
            spend_usd=response.spend_usd, tokens=response.tokens,
            wall_clock_seconds=0.0, turns=1, at=self.clock(),
        ))
        self._write_model_span(turn_index, response)

        results: list[ToolResult] = []
        if response.tool_calls:
            outcome = dispatch(
                response.tool_calls,
                lambda call: self._bounded_body(call),
                record=lambda result: self._write_tool_span(turn_index, result),
            )
            results = list(outcome.results)

        record = TurnRecord(
            turn_index=turn_index,
            provider=response.provider,
            provider_state=response.provider_state,
            tool_calls=tuple(response.tool_calls),
            tool_results=tuple(results),
            text=response.text,
            at=self.clock(),
        )
        contributions = [
            Contribution(branch=r.call.call_id, index=r.index, writes=r.writes)
            for r in results if r.writes
        ]
        return record, contributions

    def _bounded_body(self, call: ToolCall) -> ToolResult:
        """Execute one call and bound its result before anything reads it.

        The bound is applied **here**, inside the branch, rather than after the
        fan-out. Bounding afterwards would mean the unbounded bodies of every
        parallel branch are all held at once, which is the same unbounded
        quantity arriving by a different route.
        """
        started = self.clock()
        body = self.execute(call)
        bounded = self.bound.apply(
            body, retention=self.retention, call_id=call.call_id)
        return _BoundToolResult(
            call=call,
            outcome=OUTCOME_OK,
            body=bounded.text,
            started_at=started,
            finished_at=self.clock(),
            fields=bounded.fields,
        )

    def write_transition_span(self, transition: StateTransition) -> None:
        """Put a lifecycle edge on the trace (Principle VI at v1.3.0).

        Public because the runner takes the edges the loop does not — the
        interruption and the unclassifiable fault — and a second implementation
        of this would be a second chance to omit the `terminal_state` column that
        `contracts/trace-record.md`'s readers select on.

        The turn is the journalled count rather than a position in this attempt,
        so the span sits after the last turn it followed rather than at turn 0 of
        whichever attempt happened to observe the edge.
        """
        turn = self.budget.totals(self.session_id).turns
        self.spans.write(Span(
            kind=STATE_TRANSITION,
            session_id=self.session_id,
            turn=turn,
            ordinal=self.spans.next_ordinal(self.session_id, turn),
            outcome=(OUTCOME_CEILING_REACHED
                     if transition.deciding_rule == ST_CEILING_REACHED.rule_id
                     else OUTCOME_OK),
            attempt_kind=ATTEMPT_FIRST,
            versions=self.versions,
            cost=self._cost(0.0, 0),
            at=transition.at,
            transition=transition,
            terminal_state=transition.terminal_state,
        ))

    def _write_model_span(self, turn_index: int, response: ModelResponse) -> None:
        self.spans.write(Span(
            kind=MODEL_CALL,
            session_id=self.session_id,
            turn=turn_index,
            ordinal=self.spans.next_ordinal(self.session_id, turn_index),
            outcome=OUTCOME_OK,
            attempt_kind=ATTEMPT_FIRST,
            versions=self.versions,
            cost=self._cost(response.spend_usd, response.tokens),
            at=self.clock(),
            # The digest, never the bytes.
            detail={
                "provider": response.provider,
                "provider_state_digest": state_digest(response.provider_state),
                "tool_calls": len(response.tool_calls),
            },
        ))

    def _write_tool_span(self, turn_index: int, result: ToolResult) -> None:
        fields = getattr(result, "fields", None)
        if fields is None:
            # A branch that faulted before the bound ran. The fields are still
            # required — the obligation is on the span, not on the happy path —
            # so the absence is recorded as a zero-size result rather than
            # omitted, which would be indistinguishable from not instrumented.
            fields = BoundFields(
                bound_applied=True,
                bound_in_force=self.bound.bound_tokens,
                unit="tokens" if self.bound.tokenizer else "bytes",
                byte_proxy=self.bound.tokenizer is None,
                full_size=0, admitted=0,
                disposition="retained",
            )
        self.spans.write(Span(
            kind=TOOL_CALL,
            session_id=self.session_id,
            turn=turn_index,
            ordinal=self.spans.next_ordinal(self.session_id, turn_index),
            outcome=result.outcome,
            attempt_kind=ATTEMPT_FIRST,
            versions=self.versions,
            cost=self._cost(0.0, 0),
            at=self.clock(),
            result_bound=fields,
            detail={
                "tool": result.call.name,
                "call_id": result.call.call_id,
                "index": result.index,
                "duration_seconds": result.duration_seconds,
            },
        ))

    def _cost(self, spend: float, tokens: int) -> Cost:
        totals = self.budget.totals(self.session_id)
        return Cost(
            spend_usd=spend, tokens=tokens, wall_clock_seconds=0.0, turns=0,
            total_spend_usd=totals.spend_usd, total_tokens=totals.tokens,
            total_wall_clock_seconds=totals.wall_clock_seconds,
            total_turns=totals.turns,
        )


# A sentinel provider for the first turn, where there is no prior provider and
# therefore no state to carry. Not `""`, so that a provider that somehow reports
# an empty name cannot accidentally match it.
_ANY_PROVIDER = "\x00no-prior-provider"


@dataclass(frozen=True)
class _BoundToolResult(ToolResult):
    """A `ToolResult` carrying the bound fields the span needs.

    A subclass rather than a field on `ToolResult`, because `dispatch` is used
    by callers that have no bound to apply and a required field there would make
    FR-058 look like a property of dispatching.
    """

    fields: BoundFields | None = None
