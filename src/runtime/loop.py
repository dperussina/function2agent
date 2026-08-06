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

7. **The elapsed time a turn took is measured and accrued** (FR-005's fourth
   ceiling). It goes on in two pieces and both are deliberate.
   [finding 029](../../specs/002-spec-aware-agent-runtime/findings/029-wall-clock-ceiling-unenforced.md)
   measured what happened when neither did: a session that ran for 2.044
   seconds under a ceiling of 0.001 seconds ended `terminated.completed`, while
   three controls on the same harness fired on `spend`, `tokens` and `turns`.
   The comparison, the wiring and `terminated.wall_clock_ceiling_reached` all
   worked; the numerator was missing.

   - **The model call's interval rides on `reconcile`**, in the same
     transaction as the release of its reservation. Accruing it afterwards
     would open a window in which the estimate has been released and the
     measurement is not yet written — the only ordering that makes a total go
     *down* across a crash, which is what FR-005's crash clause forbids.
   - **The rest of the turn is accrued at the end of it**, which is the case
     `BudgetLedger.accrue`'s own docstring names: a figure already known when
     it is written has nothing to estimate. It is one span for the whole
     fan-out rather than a sum over branches, because summing parallel tool
     calls would count four seconds of wall clock for a two-second turn.

   **The residue, stated because it is real.** The interval is accrued at two
   points per turn, so a `SIGKILL` between them loses the part since the last
   one — bounded by one turn's tool phase, and covered in the other direction
   by `ReservationPolicy.wall_clock_seconds`, which is required for that
   reason. Time in which no attempt is running is **not** counted; see
   `_accrue_elapsed` for the clause of FR-005 that decides it.

8. **A turn's spend is priced, and an unpriced turn stops the session.** The
   figure `reconcile` accrues comes from `costs.price_usd` by way of
   `providers/adapter.py`, and `ModelResponse.require_spend_usd` refuses a
   response nothing priced rather than accruing `0.0` for it. Before that, the
   field defaulted to zero and this loop accrued zero on every path — the same
   shape finding 029 measured on wall clock, where *"the comparison, the wiring
   and `terminated.wall_clock_ceiling_reached` all worked; the numerator was
   missing."* A provider `costs.py` prices nothing for — OpenAI, on the grounds
   `costs.UNPRICED` records — therefore fails closed here, which is T063's
   intended outcome rather than a defect in this loop.

**What this slice still does not do — corrected 2026-08-05, and the first half
of what stood here is now false.** It read *"the reservation figures are the
operator's declaration until T062's cost table exists"*. The table exists and
is now reached: `costs.reservation_spend_usd` derives the spend reservation
from the token reservation, and the reconcile above replaces it with a priced
measurement. What remains true is the second half. `src/runtime/ledger.py`
states what the ordering costs: the crash window loses `actual − reserved`
when the actual is larger, which is a residue this ordering reduces rather than
removes. `ReservationPolicy.wall_clock_seconds` is still an operator
declaration, and `costs.DERIVABLE_RESERVATION_FIELDS` is the enumerated reason
no table of dollars per token can supply it.
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
from src.runtime.progress import StallPolicy, evaluate_stall
from src.runtime.session_state import SessionStateMachine
from src.runtime.session_store import SessionStore
from src.runtime.signals import (
    REASON_CEILING_REACHED,
    REASON_COMPLETED,
    REASON_NO_PROGRESS,
    EndOfRun,
    ExhaustionCause,
    require_paired,
)
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
from src.runtime.budget_backstop import CallCountBackstop
from src.runtime.trace_budget import Consumption

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

    `end_of_run` is T066's explicit marker and is **paired** with the field
    above rather than sitting beside it: `require_paired` refuses an outcome
    carrying one and not the other. A marker a construction site could omit is
    the shape finding 006 measured — the removed dependency emitted one only
    under a flag that was off by default, so its absence meant either *this run
    did not end* or *nobody turned it on*.

    A cancelled attempt carries **no** marker here, and that is not an omission.
    The loop returns at a turn boundary having ended nothing; the session is
    ended by `Runner._stand_down`, which is the component that owns the
    lifecycle, and it mints the marker there.
    """

    turns: tuple[TurnRecord, ...]
    terminal_state: str | None
    text: str
    cancelled: bool = False
    merged_state: Mapping[str, Any] = field(default_factory=dict)
    end_of_run: EndOfRun | None = None

    def __post_init__(self) -> None:
        require_paired(self.terminal_state, self.end_of_run)


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
        stall: StallPolicy,
        assembler: ContextAssembler | None = None,
        merge_policy: MergePolicy | None = None,
        cancel: Callable[[], bool] | None = None,
        backstop: CallCountBackstop | None = None,
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
        # T067. Required with no default, and the asymmetry with `backstop`
        # two fields down is deliberate rather than an inconsistency. A
        # backstop must not be omittable, so `None` builds one; a *threshold*
        # has no value this specification may invent, so FR-033 makes an
        # omission a refusal at construction. Between them they cover the two
        # ways a limit goes missing: nobody wired it, and nobody chose it.
        self.stall = stall
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
        # T065. `None` builds one rather than switching it off, and there is no
        # value of this argument that disables it: a backstop a construction
        # site can omit is absent from every construction site that predates it.
        # It is given the journal the loop already holds, because the count that
        # survives a crash is the one on disk (finding 006).
        self.backstop = backstop or CallCountBackstop(journal)

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

            # T065, and **before** the configured ceilings on purpose. Those are
            # four numbers off one channel, and the spend one is unenforceable
            # for any model `costs.py` has no entry for. If this ran second, a
            # `ceiling_verdict` that raised — or four ceilings set high in one
            # bad config — would take the backstop with them, which is the
            # simultaneous failure T065 exists to survive.
            #
            # Skipped for a resumed turn whose model call is already on disk:
            # that turn makes no new call, and refusing it would strand a
            # session that has already paid for the answer.
            if pending_turn is None:
                self.backstop.check(self.session_id)

            verdict = self.store.ceiling_verdict(self.session_id, self.budget)
            if verdict.exceeded:
                transition = self.machine.terminate_on_ceiling(
                    self.session_id, verdict, at=self.clock())
                # T066. The cause is built from the same verdict the transition
                # was, so the marker and the predicate inputs on the span cannot
                # name different ceilings.
                marker = EndOfRun(
                    session_id=self.session_id,
                    reason=REASON_CEILING_REACHED,
                    at=transition.at,
                    exhaustion=ExhaustionCause.from_verdict(verdict),
                )
                self.write_transition_span(transition, end_of_run=marker)
                return LoopOutcome(
                    turns=tuple(turns),
                    terminal_state=verdict.terminal_state,
                    text=turns[-1].text if turns else "",
                    merged_state=merged,
                    end_of_run=marker,
                )
            # T067, FR-006's stall condition, and **after** the ceilings on
            # purpose. Both can be true on the same iteration: a session that
            # has been repeating itself is usually also spending turns. The
            # ceilings are the operator's declared liability bound and this is
            # a detection over them, so when the two arrive together the bound
            # is what the record names — and when the threshold is set below
            # the turn ceiling, which is the configuration that makes this
            # member reachable at all, the stall arrives strictly earlier and
            # wins by arriving first. Ordering it the other way would let a
            # stall threshold silently stand in for a ceiling.
            #
            # Evaluated at the top of a turn over `turns`, which on a resumed
            # attempt is the journal's records rather than this process's, so
            # a session that stalls, crashes and resumes goes on counting from
            # where it was instead of starting again at zero.
            stall = evaluate_stall(turns, self.stall)
            if stall.stalled:
                transition = self.machine.terminate_on_stall(
                    self.session_id, stall, at=self.clock())
                marker = EndOfRun(
                    session_id=self.session_id,
                    reason=REASON_NO_PROGRESS,
                    at=transition.at,
                )
                self.write_transition_span(transition, end_of_run=marker)
                return LoopOutcome(
                    turns=tuple(turns),
                    terminal_state=terminal.NO_PROGRESS.name,
                    text=turns[-1].text if turns else "",
                    merged_state=merged,
                    end_of_run=marker,
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
                marker = EndOfRun(
                    session_id=self.session_id,
                    reason=REASON_COMPLETED,
                    at=transition.at,
                )
                self.write_transition_span(transition, end_of_run=marker)
                return LoopOutcome(
                    turns=tuple(turns),
                    terminal_state=terminal.COMPLETED.name,
                    text=record.text,
                    merged_state=merged,
                    end_of_run=marker,
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
        call_started = self.clock()
        response = self.model(context)
        call_finished = self.clock()
        # Reconciled after, which is where the estimate is replaced by the
        # measurement. A crash between the two lines above and this one leaves
        # the reservation standing, and that is the point: the spend is counted
        # at its estimate rather than not at all (U-30).
        #
        # All three measurable dimensions are handed over together. Wall clock
        # used to be passed as `0.0` here, which is why the reservation was the
        # only figure that ever reached it and why an orphaned reservation was
        # the only way to fire the ceiling (finding 029).
        #
        # **`require_spend_usd`, not `spend_usd`, and this is the ceiling's one
        # gate.** The spend figure used to default to `0.0` for every caller,
        # so this line accrued zero on every path and the spend ceiling was
        # unenforceable for the same reason finding 029 measured the wall-clock
        # one to be: the numerator was missing. An unpriced turn now refuses
        # here rather than accruing nothing. It refuses *after* the call, which
        # is the only place it can — the price is a function of the token
        # counts the call returns — and the consequence is the one the ledger
        # is designed around: the reservation stays outstanding and the turn is
        # counted at its estimate, which over-counts rather than under-counts.
        self.budget.reconcile(
            reservation, spend_usd=response.require_spend_usd(),
            tokens=response.tokens,
            wall_clock_seconds=_interval(call_started, call_finished),
            at=call_finished)
        self.journal.commit_outcome(
            session_id=self.session_id, turn_index=turn_index,
            step_index=MODEL_STEP_INDEX,
            payload=encode_model_outcome(response),
            provider_state=response.provider_state, at=self.clock())
        self._write_model_span(turn_index, response)

        results = self._run_calls(turn_index, response.tool_calls)
        self._accrue_elapsed(turn_index, since=call_finished)
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
        resumed_at = self.clock()
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
        # The time this attempt spent finishing the turn, and only that. The
        # model call belonging to this turn was made and paid for by an earlier
        # attempt, which reconciled its interval or died holding the
        # reservation for it; re-counting it here would charge one call's
        # duration twice.
        self._accrue_elapsed(turn_index, since=resumed_at)
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

    def _accrue_elapsed(self, turn_index: int, *, since: float) -> None:
        """Put the interval `since..now` on the ledger as measured wall clock.

        **Only intervals in which an attempt was running are accrued, and that
        is derived from FR-005 rather than chosen here.** The requirement
        states what the counted total is made of: *"**A crash MUST NOT reduce
        the total counted against any of the four ceilings** — consumption
        already incurred before a crash MUST still be counted after the resume,
        so a session that crashes and resumes repeatedly MUST NOT be able to
        exceed a ceiling by any number of resumes."* Three things follow.

        The counted total is *consumption incurred*, and the interval between a
        crash and its resume is not incurred by the session — nothing of it is
        running to incur anything. FR-049's extension note to FR-005 says so in
        the same word, of all four ceilings at once: they are *"consumption
        ceilings on a session"*, as against the processor and memory bounds,
        which are *"properties of the execution environment rather than of a
        session's consumption"*.

        The mischief the last clause names is a **reset**, and a durable sum of
        running intervals has none: every attempt adds to the same total, so no
        number of resumes buys more than the ceiling. Counting downtime is
        therefore not required to satisfy it.

        And the clause only has a subject at all under an accrual reading. A
        ceiling measured as *now minus session start* is a deadline, and a
        crash cannot reduce a deadline, nor can any number of resumes raise
        one — so a requirement that spends a sentence forbidding both is not
        describing one. The same follows from *"the cumulative total against
        it, MUST be recorded"*: a deadline has no cumulative total.

        `turns=0` and no spend or tokens: this row is one dimension's
        measurement and nothing else, and a turn counted here would be a second
        count of the turn the reservation already carries.
        """
        now = self.clock()
        self.budget.accrue(Consumption(
            session_id=self.session_id,
            turn=turn_index,
            ordinal=TURN_TAIL_ORDINAL,
            spend_usd=0.0,
            tokens=0,
            wall_clock_seconds=_interval(since, now),
            turns=0,
            at=now,
        ))

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

    def write_transition_span(
        self, transition: StateTransition, *, end_of_run: EndOfRun | None = None
    ) -> None:
        """Put a lifecycle edge on the trace (Principle VI at v1.3.0).

        Public because the runner takes the edges the loop does not — the
        interruption and the unclassifiable fault — and a second implementation
        of this would be a second chance to omit the `terminal_state` column that
        `contracts/trace-record.md`'s readers select on.

        **`end_of_run` is what puts T066's raw signals on the record**, and it
        is optional here for one reason only: the two non-terminal edges,
        `interrupt` and `resume`, end no run and have no marker to carry. Every
        terminal edge has one, which is what `LoopOutcome`'s pairing enforces on
        the caller-visible side. Its content goes in `detail` rather than in a
        column because a fault's error identity is the only field of it that is
        new to the trace, and adding a column for a value one edge in five
        carries would make every other span state that it is absent.

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
            detail=({} if end_of_run is None
                    else {"end_of_run": end_of_run.to_record()}),
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
            cost=self._cost(response.require_spend_usd(), response.tokens),
            at=self.clock(),
            # The digest, never the bytes.
            detail={
                "provider": response.provider,
                # **The model, not only the provider.** A span carrying a spend
                # figure and no model identifier records a number nobody can
                # check: the rate it was computed at is keyed on
                # `(provider, model)`, and two models on one provider differ by
                # up to 5x. FR-038 requires an attribution reproducible from
                # the trace alone, and a price is not reproducible without the
                # row it came from.
                "model": response.model,
                # **And where the rate came from, on the same argument.** The
                # paragraph above says a price is not reproducible without the
                # row it came from. A rate an operator declared under OD-27 has
                # no row in this repository at all, so a span recording only
                # `(provider, model)` describes a figure a later reader will
                # try to check against `costs.PRICES` and fail to find —
                # concluding the table moved rather than that the rate was
                # never in it. This field is what makes those two readings
                # different, and it is here rather than only in a startup log
                # because a claim about a record that lives in another file is
                # the family `tools/README.md` collects and the log is gone
                # with the process that wrote it.
                "spend_provenance": response.spend_provenance,
                "provider_state_digest": state_digest(response.provider_state),
                "tool_calls": len(response.tool_calls),
                "input_tokens": response.input_tokens,
                "output_tokens": response.output_tokens,
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


def _interval(started: float, finished: float) -> float:
    """`finished - started`, floored at zero.

    Floored rather than trusted, because the clock is a caller's callable and
    `Consumption` refuses a negative figure — *"a ledger that can be
    decremented is a ledger a ceiling can be walked back under"*. A clock that
    stepped backwards would otherwise take the whole turn down with a
    `BudgetError` raised from the accounting rather than from the clock, which
    is a long way from where the fault is. Floored, a non-monotonic clock
    under-counts an interval and nothing else.
    """
    return max(0.0, finished - started)


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

# The ledger ordinal the turn's post-model interval is accrued at. Ordinal 0 is
# the model call's — reserved before it, reconciled after it — so the tail takes
# the next position rather than appending a second row at the same coordinates
# that no reader of `entries()` could tell from the first.
TURN_TAIL_ORDINAL = 1


@dataclass(frozen=True)
class _BoundToolResult(ToolResult):
    """A `ToolResult` carrying the bound fields the span needs.

    A subclass rather than a field on `ToolResult`, because `dispatch` is used
    by callers that have no bound to apply and a required field there would make
    FR-058 look like a property of dispatching.
    """

    fields: BoundFields | None = None
