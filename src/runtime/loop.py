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

5. **Every effectful step is journalled before it happens and after it finishes**
   (T051), and **every model call is reserved on the ledger before it is made**
   (T053). Both are ordered that way round for the same reason: after a
   `SIGKILL` there is no unwind, so anything recorded only afterwards is
   recorded only when nothing went wrong. The consequences are asymmetric on
   purpose — a crash leaves a step that *may* have run, and a spend counted at
   its estimate rather than not at all.

6. **A resumed attempt starts from the journal, not from zero** (T052). The plan
   is built at the top of `run()` unconditionally, including on a fresh session
   where it is empty, so there is no resume flag for a caller to forget. A turn
   whose steps all have committed outcomes is reconstructed and never re-run,
   which is finding 006's 4-of-4 measurement; a turn half-done has only its
   outstanding steps handed back out.

**What this slice still does not do.** Wall-clock consumption is not accrued —
`wall_clock_seconds` reaches the ledger only through the reservation policy — and
the reservation figures are the operator's declaration until T062's cost table
exists. `src/runtime/ledger.py` states what that costs: the crash window loses
`actual − reserved` when the actual is larger, which is a residue this ordering
reduces rather than removes.
"""

from __future__ import annotations

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
from src.runtime.journal import (
    MODEL_STEP_INDEX,
    STEP_MODEL_CALL,
    STEP_TOOL_CALL,
    TurnJournal,
    tool_step_index,
)
from src.runtime.ledger import BudgetLedger
from src.runtime.result_bound import BoundFields, ResultBound, RetentionStore
from src.runtime.resume import (
    ResumePlan,
    UnfinishedTurn,
    encode_model_outcome,
    encode_tool_outcome,
    plan_resume,
)
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

# Re-exported rather than defined here: `resume.py` builds a `TurnRecord` and
# this module reads a `ResumePlan`, which would be an import cycle. See
# `src/runtime/turn.py` for why the types moved down and the names did not.
from src.runtime.turn import (  # noqa: F401 — the public names live here
    LoopError,
    ModelResponse,
    TurnRecord,
    state_digest,
)


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
        budget: BudgetLedger,
        journal: TurnJournal,
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
        # A `BudgetLedger` rather than a `BudgetJournal`, and required rather
        # than accepted as either: the journal alone accrues after the call,
        # which is the under-count U-30 names. Taking the wider type would make
        # reserve-then-reconcile an opt-in safety property, and
        # `BudgetJournal.__init__`'s own docstring records what that cost the
        # last time it happened here.
        self.budget = budget
        self.journal = journal
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

        # T052. Built unconditionally, including on a fresh session where it is
        # empty. There is no `resume=True` for a caller to forget, and no branch
        # here that a first attempt takes and a resumed one does not — the two
        # differ only in what the journal already holds.
        plan = plan_resume(self.journal, self.session_id)
        turns: list[TurnRecord] = list(plan.records)
        merged: dict[str, Any] = {}
        # The merged state is replayed from the reconstructed results rather
        # than starting empty. A resumed session that lost it would re-derive it
        # by re-running the tools that produced it, which is finding 006's
        # re-execution arriving under a different name.
        for record in plan.records:
            writes = _contributions(record.tool_results)
            if writes:
                merged = self.merge_policy.merge(merged, writes)
        pending_turn: UnfinishedTurn | None = plan.unfinished
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

            if pending_turn is not None:
                # A turn whose model call finished before the crash. Its
                # response is on disk, so the provider is not called again, and
                # only its outstanding steps run.
                record, writes = self._finish_turn(pending_turn)
                pending_turn = None
            else:
                # The turn index is the **journal's**, not `len(turns)` and not
                # the ledger's turn total. `len(turns)` is this attempt's, and a
                # resumed attempt would restart the numbering §2.2 requires to be
                # dense and monotonic across the session. The ledger's total is
                # the wrong authority for a different reason: it deliberately
                # over-counts (T053), so a turn abandoned mid-call inflates it
                # and the next turn would skip a position the journal does not
                # know about. Position and consumption are different questions
                # and conflating them is what makes one of the two wrong.
                turn_index = self.journal.next_turn_index(self.session_id)
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

        # **Intent, then reservation, then the call.** The intent goes first
        # because the journal is what numbers turns: a reservation written
        # against a turn the journal has never heard of would be a reservation
        # for a position `next_turn_index` is about to hand out again. Between
        # the two the crash costs nothing — an index consumed, no money spent.
        self.journal.intend(
            session_id=self.session_id, turn_index=turn_index,
            step_index=MODEL_STEP_INDEX, step_kind=STEP_MODEL_CALL,
            effect_id="model", effectful=True,
            payload={"turns_in_context": len(turns),
                     "dropped_turns": context.dropped_turns},
            at=self.clock())
        reservation = self.budget.reserve(
            self.session_id, turn=turn_index, at=self.clock())
        response = self.model(context)
        # Reconciled after, which is where the estimate is replaced by the
        # measurement. A crash between the two lines above and this one leaves
        # the reservation standing, and that is the point: the spend is counted
        # at its estimate rather than not at all (U-30).
        self.budget.reconcile(
            reservation, spend_usd=response.spend_usd, tokens=response.tokens,
            wall_clock_seconds=0.0, at=self.clock())
        self.journal.commit_outcome(
            session_id=self.session_id, turn_index=turn_index,
            step_index=MODEL_STEP_INDEX,
            payload=encode_model_outcome(response),
            provider_state=response.provider_state, at=self.clock())
        self._write_model_span(turn_index, response)

        results = self._run_calls(turn_index, response.tool_calls)
        return self._record(turn_index, response, results)

    def _finish_turn(
        self, pending: UnfinishedTurn
    ) -> tuple[TurnRecord, list[Contribution]]:
        """Complete a turn the crash caught between its steps (T052).

        Three things this deliberately does **not** do. It does not call the
        model — the response is reconstructed, and re-calling it would be a
        second charge for an answer already on disk. It does not reserve — the
        earlier attempt's reservation for this turn was either reconciled or is
        still outstanding, and a second one would count the turn twice. And it
        does not re-run `pending.completed` — those are the recorded effects
        FR-007 forbids repeating.

        The outstanding calls run **sequentially** rather than through
        `dispatch`. `dispatch` requires the declared indexes to be dense over
        `0..n-1` and a pending subset is sparse by construction, so fanning out
        would mean renumbering the calls and mapping them back — and the index a
        span carries is the provider's declared one. Losing parallelism on a
        crash-recovery path is a cost worth paying to keep that mapping from
        existing; the parallel path itself is unchanged and still under T043's
        ordering invariant.
        """
        turn_index = pending.turn_index
        results = list(pending.completed)
        for call in pending.pending:
            # `intend_once`, not `intend`. A pending call is pending for either
            # of two reasons — never intended, or intended and unrecorded — and
            # the second already has its row. `intend` refuses a second intent
            # and is right to; this path is the retry that row exists for.
            self._reintend_call(turn_index, call)
            result = self._bounded_body(call)
            self._commit_call(turn_index, result)
            self._write_tool_span(turn_index, result)
            results.append(result)
        results.sort(key=lambda result: result.index)
        return self._record(turn_index, pending.response, results)

    def _run_calls(
        self, turn_index: int, calls: Sequence[ToolCall]
    ) -> list[ToolResult]:
        if not calls:
            return []
        # Every intent is committed **before the fan-out starts**, in declared
        # order, rather than inside each branch. A branch that wrote its own
        # intent would be writing it concurrently with the effect it precedes on
        # another thread, and "before" would then be true per branch and
        # unordered across them.
        for call in calls:
            self._intend_call(turn_index, call)
        outcome = dispatch(
            calls,
            lambda call: self._bounded_body(call),
            record=lambda result: self._record_call(turn_index, result),
        )
        return list(outcome.results)

    def _record_call(self, turn_index: int, result: ToolResult) -> None:
        """The journal first, then the span.

        `dispatch` calls this in declared order and does not catch what it
        raises, on the grounds that *"a journal that failed to record a step is
        not something to carry on past"*. The journal is written first for the
        same reason: a step recorded on the trace and not in the journal would
        be re-run on resume with a trace already claiming it happened.
        """
        self._commit_call(turn_index, result)
        self._write_tool_span(turn_index, result)

    def _intend_call(self, turn_index: int, call: ToolCall) -> None:
        self.journal.intend(**self._call_intent(turn_index, call))

    def _reintend_call(self, turn_index: int, call: ToolCall) -> None:
        """The resume path's intent. See `_finish_turn`."""
        self.journal.intend_once(**self._call_intent(turn_index, call))

    def _call_intent(self, turn_index: int, call: ToolCall) -> dict[str, Any]:
        """One description of a tool step, for both of the ways to record it.

        Built in one place because the two must agree on the `effect_id`: the
        idempotency key is derived from it, and `intend_once` compares keys to
        decide whether it is looking at a retry or at a different effect. Two
        constructions of this dict would be two chances for a resumed attempt to
        name the call slightly differently and be refused for it.
        """
        return {
            "session_id": self.session_id,
            "turn_index": turn_index,
            "step_index": tool_step_index(call.index),
            "step_kind": STEP_TOOL_CALL,
            "effect_id": call.call_id,
            "effectful": True,
            "payload": {"name": call.name, "arguments": dict(call.arguments)},
            "at": self.clock(),
        }

    def _commit_call(self, turn_index: int, result: ToolResult) -> None:
        self.journal.commit_outcome(
            session_id=self.session_id, turn_index=turn_index,
            step_index=tool_step_index(result.index),
            payload=encode_tool_outcome(
                outcome=result.outcome, body=result.body,
                started_at=result.started_at, finished_at=result.finished_at,
                writes=result.writes),
            at=self.clock())

    def _record(
        self,
        turn_index: int,
        response: ModelResponse,
        results: Sequence[ToolResult],
    ) -> tuple[TurnRecord, list[Contribution]]:
        record = TurnRecord(
            turn_index=turn_index,
            provider=response.provider,
            provider_state=response.provider_state,
            tool_calls=tuple(response.tool_calls),
            tool_results=tuple(results),
            text=response.text,
            at=self.clock(),
        )
        return record, _contributions(results)

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

        Read off the **journal** rather than the ledger's turn total, for the
        reason `run()` gives: the ledger over-counts by design, so a turn
        abandoned mid-call would place this span one position past the last turn
        that actually exists.
        """
        turn = self.journal.next_turn_index(self.session_id)
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


def _contributions(results: Sequence[ToolResult]) -> list[Contribution]:
    """The merge contributions a turn's results carry.

    Shared by the live path and the reconstruction path so that a resumed
    session's merged state is built by the same rule as a fresh one's. Two
    implementations would be two chances for a resume to merge differently from
    the attempt it is resuming.
    """
    return [
        Contribution(branch=r.call.call_id, index=r.index, writes=r.writes)
        for r in results if r.writes
    ]


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
