"""T046 — session start and attach, loop invocation, cancellation, and the
teardown handshake with the supervisor.

**Why this is not a wrapper around the loop.** The loop knows how to run a turn
and nothing about a session's beginning or its end. Admission, the capability
handle, the lease and standing the session down are the supervisor's. The runner
is the only component that holds both, which makes it the only place that can
guarantee the property that matters:

> **the session is stood down on every exit path**, including the one nobody
> planned for.

A runner that tears down on the happy path is indistinguishable from a correct
one until the first unhandled exception, at which point the session is left
`RUNNING` with a live lease and the enforcement point keeps honouring a
capability whose owner is gone. So the teardown is in a `finally`, it reads the
row back, and a failure *inside* the teardown never replaces the exception that
caused it — the first exception is the diagnosis.

**Cancellation terminates. It is not an interruption.** A cancelled session ends
in `terminated.operator_terminated`, and the interrupt edge is left to the one
event that really is resumable: an attempt bounded short by
`max_turns_this_attempt`.

> **Decided 2026-08-05, and it needed no taxonomy addition.** The earlier reading
> here routed cancellation to `INTERRUPTED` and recorded that making it terminal
> "is a taxonomy addition and an owner decision". **The first half was wrong**,
> and it is why the decision went this way: `OPERATOR_TERMINATED` already
> existed, so the closed set stays closed. What the earlier reading cost was a
> live defect. `STATE_INTERRUPTED` is FR-007's *resume* state, and `attach()`
> below resumes a session it finds in it automatically — so cancelling a session
> and then attaching to it silently resumed the cancelled run. `CancelToken` is
> one-way precisely so that "a race cannot produce a run that continued after
> cancellation", and the state it cancelled into was resumable by design. That
> contradiction, not the ambiguity, is what settled this.
>
> The name is wider than the event by one term and was widened rather than
> renamed: a `CancelToken` is set by a *consumer*, which may be programmatic
> rather than human. `src/contracts/terminal.py` carries the widened meaning;
> the name is a wire string the Go enforcement point reads and does not move.

> **`attach()`'s refusal message cites the state machine rather than the diagram,
> corrected 2026-08-05 under `OD-26`.** It used to read *"data-model.md §2.1 has
> no edge out of it"*. The refusal was right and the citation was **vacuously**
> true: §2.1 had no edge out of `TERMINATED` because §2.1 had no `TERMINATED` —
> every branch in it was labelled with a terminal-state *name* rather than a
> state ([finding 027](../../specs/002-spec-aware-agent-runtime/findings/027-lifecycle-edge-set-divergence.md)).
> A contributor checking the citation would not have found what the sentence
> promised. `SessionStateMachine._move` is what actually refuses, it refuses
> unconditionally, and it fails if it stops.

**Resume reconstruction is now the loop's, and this is where it changed.** Until
T052 this docstring said *"the transcript of the earlier attempt does not come
back yet"*. It does now: `AgentLoop.run()` builds a `ResumePlan` from the journal
at the top of every attempt, so a `RunOutcome` from `attach()` carries the
reconstructed turns **and** the new ones. That is a caller-visible change —
`outcome.turns` after a resume is the session's turns, not the attempt's — and it
is deliberate: the alternative is a caller that has to read the journal itself to
find out what it is continuing from.

The runner's own part is unchanged: it takes the resume edge, and the journal and
the ledger it hands the loop are the session's, not the attempt's.
"""

from __future__ import annotations

import sys
import threading
from dataclasses import dataclass
from typing import Callable, Mapping

from src.contracts import terminal
from src.contracts.transition import (
    STATE_INTERRUPTED,
    STATE_RUNNING,
    STATE_STARTING,
    STATE_TERMINATED,
)
from src.runtime.context import ContextAssembler
from src.runtime.dispatch import ToolCall
from src.runtime.loop import AgentLoop, LoopOutcome, ModelClient, TurnRecord
from src.runtime.result_bound import ResultBound, RetentionStore
from src.runtime.session_state import SessionStateMachine
from src.runtime.session_store import Ceilings, LifecycleGateway, SessionStore
from src.runtime.signals import (
    REASON_CANCELLED,
    REASON_FAULTED,
    EndOfRun,
    ErrorIdentity,
    require_paired,
)
from src.runtime.state_merge import MergePolicy
from src.runtime.journal import TurnJournal
from src.runtime.ledger import BudgetLedger
from src.runtime.trace import ArtifactVersions, SpanWriter
from src.supervisor.session_table import capability_digest


class RunnerError(RuntimeError):
    """A session that cannot be started, attached to, or torn down."""


class CancelToken:
    """A one-way flag a consumer sets and the loop reads at turn boundaries.

    One way on purpose: there is no `uncancel`. A token that could be cleared
    would let a race between the consumer going away and the loop checking the
    flag produce a run that continued after cancellation, which is the state a
    consumer cancelled to avoid.

    **The lifecycle now matches that, and for a while it did not.** The session a
    set token ends is terminated, so there is no edge out of it and no second
    attempt to race against. While cancellation routed to `INTERRUPTED` the
    token's irreversibility bought nothing: `attach()` resumed the session, and
    the run continued after cancellation by the ordinary path rather than by a
    race.

    Thread-safe because the consumer and the loop are not the same thread — a
    plain attribute would work on CPython today and is the kind of assumption
    that stops being true quietly.
    """

    __slots__ = ("_event",)

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    def is_cancelled(self) -> bool:
        return self._event.is_set()

    def __call__(self) -> bool:
        return self._event.is_set()


@dataclass(frozen=True)
class RunOutcome:
    """What one `start()` or `attach()` produced.

    `terminal_state` is `None` exactly when the attempt stopped without the
    session ending, which since cancellation became terminal leaves one case:
    an attempt bounded short by `max_turns_this_attempt`. A cancelled run now
    carries `terminated.operator_terminated` here, because the row does.

    The two fields stay separate rather than collapsing into one nullable name
    because a caller asking "did this end?" and a caller asking "why did it end?"
    are asking different questions. `cancelled` is now the narrower of the two:
    every cancelled run is terminated, and not every terminated run was
    cancelled.
    """

    session_id: str
    turns: tuple[TurnRecord, ...]
    terminal_state: str | None
    text: str
    cancelled: bool
    merged_state: Mapping[str, object]
    #: T066's explicit end-of-run marker, paired with `terminal_state` above.
    #: This is the field finding 006 found missing: the removed dependency's
    #: caller could not tell a clean completion from a mid-loop cancellation,
    #: because the only marker that separated them was behind a default-off
    #: experimental flag. Here the two are different members of a closed set,
    #: and a run that ended cannot report a terminal state without one.
    end_of_run: EndOfRun | None = None

    def __post_init__(self) -> None:
        require_paired(self.terminal_state, self.end_of_run)


class Runner:
    """Starts and attaches sessions, drives the loop, and tears down."""

    def __init__(
        self,
        *,
        store: SessionStore,
        lifecycle: LifecycleGateway,
        machine: SessionStateMachine,
        budget: BudgetLedger,
        journal: TurnJournal,
        spans: SpanWriter,
        bound: ResultBound,
        retention: Callable[[str], RetentionStore],
        versions: ArtifactVersions,
        tenant_id: str,
        deployment_id: str,
        clock: Callable[[], float],
        lease_interval_seconds: float,
        assembler: ContextAssembler | None = None,
        merge_policy: MergePolicy | None = None,
    ) -> None:
        self.store = store
        self.lifecycle = lifecycle
        self.machine = machine
        self.budget = budget
        self.journal = journal
        self.spans = spans
        self.bound = bound
        # A factory rather than an instance: FR-058 requires the retention
        # location to be unreadable from another session's environment, and one
        # shared store handed to every session is the shape that fails that.
        self.retention = retention
        self.versions = versions
        self.tenant_id = tenant_id
        self.deployment_id = deployment_id
        self.clock = clock
        self.lease_interval_seconds = lease_interval_seconds
        self.assembler = assembler
        self.merge_policy = merge_policy

    # -- start -------------------------------------------------------------

    def start(
        self,
        *,
        session_id: str,
        prompt: str,
        ceilings: Ceilings,
        capability_handle: str,
        model: ModelClient,
        execute: Callable[[ToolCall], str],
        cancel: CancelToken | None = None,
        max_turns_this_attempt: int | None = None,
    ) -> RunOutcome:
        """Admit a new session and run it.

        The order is deliberate: the ceilings are persisted **before** the
        session becomes `RUNNING`. A session the enforcement point honours and
        whose ceilings are not yet on disk is a session running unbounded for as
        long as that window lasts, and FR-005's whole subject is that the
        ceilings outlive the process enforcing them.
        """
        token = _require_token(cancel)
        if self.lifecycle.get(session_id) is not None:
            raise RunnerError(
                f"{session_id!r} already exists. A second start would either "
                "overwrite a live session's admission or revive a terminated "
                "one under its own id; attach() is the resume path."
            )
        self.lifecycle.create(
            session_id=session_id,
            tenant_id=self.tenant_id,
            deployment_id=self.deployment_id,
            capability_sha256=capability_digest(capability_handle),
            lease_expires_at=self.clock() + self.lease_interval_seconds,
            now=self.clock(),
        )
        self.store.create(session_id=session_id, ceilings=ceilings)
        transition = self.machine.start(session_id, at=self.clock())

        loop = self._loop(session_id, model, execute, token)
        loop.write_transition_span(transition)
        return self._drive(
            loop, session_id, prompt, token, max_turns_this_attempt)

    # -- attach ------------------------------------------------------------

    def attach(
        self,
        *,
        session_id: str,
        prompt: str,
        model: ModelClient,
        execute: Callable[[ToolCall], str],
        cancel: CancelToken | None = None,
        max_turns_this_attempt: int | None = None,
    ) -> RunOutcome:
        """Attach to an existing session and run the next attempt.

        The ceilings are **not** re-supplied. Finding 006 measured a ceiling of 3
        permitting 6 cycles because the counter was rebuilt per attempt; an
        `attach` that accepted ceilings would be that measurement with a
        parameter, and every individual attempt would still be compliant.

        **The earlier attempt's turns do come back**, since T052. `AgentLoop.run`
        reconstructs them from the journal, so `RunOutcome.turns` here is the
        session's transcript rather than this attempt's. A completed inner turn
        is never re-run — that is finding 006's 4-of-4 measurement — and a turn
        the crash caught between its steps has only its outstanding steps
        performed.
        """
        token = _require_token(cancel)
        row = self.lifecycle.get(session_id)
        if row is None or self.store.load(session_id) is None:
            raise RunnerError(f"{session_id!r} has no session to attach to")
        if row.state == STATE_TERMINATED:
            raise RunnerError(
                f"{session_id!r} is {STATE_TERMINATED} as "
                f"{row.terminal_state!r}. SessionStateMachine refuses every "
                "transition out of TERMINATED (src/runtime/session_state.py), "
                "and a revived session would carry a second outcome for a run "
                "FR-006 says already has one."
            )

        transition = None
        if row.state == STATE_INTERRUPTED:
            transition = self.machine.resume(
                session_id, at=self.clock(),
                lease_expires_at=self.clock() + self.lease_interval_seconds)
        elif row.state == STATE_STARTING:
            transition = self.machine.start(session_id, at=self.clock())
        elif row.state != STATE_RUNNING:  # pragma: no cover - closed set
            raise RunnerError(f"{session_id!r} is {row.state}, which has no edge")

        loop = self._loop(session_id, model, execute, token)
        if transition is not None:
            loop.write_transition_span(transition)
        return self._drive(
            loop, session_id, prompt, token, max_turns_this_attempt)

    # -- the one place a loop runs and a session is stood down --------------

    def _drive(
        self,
        loop: AgentLoop,
        session_id: str,
        prompt: str,
        token: CancelToken,
        max_turns_this_attempt: int | None,
    ) -> RunOutcome:
        outcome: LoopOutcome | None = None
        recorded: EndOfRun | None = None
        try:
            outcome = loop.run(
                prompt, max_turns_this_attempt=max_turns_this_attempt)
        finally:
            recorded = self._stand_down(loop, session_id, outcome)

        # Built after the teardown, not inside the `try`, because the terminal
        # state a cancelled run ends in is the one teardown writes. Returning
        # the loop's `None` here would report "nothing ended" for a session the
        # row says ended as `terminated.operator_terminated`.
        #
        # **One marker decides both fields**, rather than the name and the
        # signal being resolved separately. Two resolutions of the same question
        # are two chances for the caller-visible name and the caller-visible
        # marker to come from different branches, and `RunOutcome` would then be
        # refusing a disagreement it created itself.
        marker = outcome.end_of_run if outcome.end_of_run is not None else recorded
        return RunOutcome(
            session_id=session_id,
            turns=outcome.turns,
            terminal_state=None if marker is None else marker.terminal_state,
            text=outcome.text,
            cancelled=outcome.cancelled,
            merged_state=outcome.merged_state,
            end_of_run=marker,
        )

    def _stand_down(
        self, loop: AgentLoop, session_id: str, outcome: LoopOutcome | None
    ) -> EndOfRun | None:
        """Leave the session in a state the enforcement point will not honour.

        Returns the end-of-run marker it recorded, or `None` where it recorded
        no terminal state — either because the loop had already ended the
        session or because the attempt was bounded short and the session is
        resumable.

        **The marker rather than the bare name, since T066.** The two terminal
        edges this method takes are the two whose *cause* was previously
        nowhere: a cancellation had no signal at all, and a fault recorded
        `terminated.unrecoverable_fault` while the exception's identity went out
        with the traceback. Returning the marker is what carries both to the
        caller and to the span.

        Wrapped so that a teardown failure cannot replace the exception that
        brought us here. The suppression is narrow — it covers only the
        transition — and it is the reason `_stand_down` reads the row first
        rather than blindly writing: a session the loop already ended is left
        alone, so an attempt to terminate it twice never arises.
        """
        row = self.lifecycle.get(session_id)
        if row is None or row.state == STATE_TERMINATED:
            return None
        if row.state != STATE_RUNNING:
            # Already interrupted by something else. Not ours to move.
            return None
        recorded: EndOfRun | None = None
        failure: BaseException | None = None
        # Read once, before anything here can raise and displace it. This is the
        # exception the loop raised, and the fault branch below is the only
        # place its identity can still be recovered — after this method returns
        # it exists only in a traceback.
        raised = sys.exc_info()[1]
        try:
            if outcome is not None and outcome.cancelled:
                # Cancellation ends the session. This branch and the next used to
                # be one — both interrupted — and merging them is what left a
                # cancelled session sitting in FR-007's resume state.
                # `recorded` is read off the transition after the write, never
                # set ahead of it: a name assigned before a `terminate()` that
                # then raised would be reported to the caller with no row
                # holding it.
                transition = self.machine.terminate(
                    session_id,
                    terminal_state=terminal.OPERATOR_TERMINATED.name,
                    at=self.clock())
                recorded = EndOfRun(session_id=session_id,
                                    reason=REASON_CANCELLED, at=transition.at)
            elif outcome is not None:
                # The loop returned without ending the session and without
                # being cancelled: `max_turns_this_attempt` bounded the attempt.
                # Interrupting is the honest record — the session did not end,
                # and this is now the only event that takes FR-007's edge.
                transition = self.machine.interrupt(
                    session_id, at=self.clock())
            else:
                # The loop raised. FR-006's named member for a fault the runtime
                # cannot classify further; reaching it is a defect report rather
                # than a normal outcome, which is exactly why it is recorded.
                transition = self.machine.terminate(
                    session_id,
                    terminal_state=terminal.UNRECOVERABLE_FAULT.name,
                    at=self.clock())
                # **The identity, not a classification.** FR-006's member says
                # the runtime could not classify the fault further; T066's
                # signal says which fault it was, and the two are compatible
                # exactly because the second is not a terminal state. A loop
                # that returned `None` without raising leaves nothing to name,
                # and a fault with no identity is refused rather than invented.
                recorded = EndOfRun(
                    session_id=session_id, reason=REASON_FAULTED,
                    at=transition.at,
                    error=ErrorIdentity.from_exception(
                        raised if raised is not None
                        else RuntimeError(
                            "the loop returned no outcome and raised nothing")),
                )
            loop.write_transition_span(transition, end_of_run=recorded)
        except Exception as exc:  # noqa: BLE001 - see the docstring
            # Deliberately swallowed, and only here. The alternative is that a
            # teardown failure becomes the reported cause and the real one is
            # gone. What is *not* swallowed is the effect: the row is re-read
            # below, and a session still honoured is escalated.
            failure = exc

        after = self.lifecycle.get(session_id)
        if after is None or not after.honoured_at(self.clock()):
            return recorded

        # The session is still honoured. This is the leak the handshake exists to
        # prevent, and it must not pass quietly — but *how* it is surfaced
        # depends on whether something is already propagating.
        #
        # **Two obligations that conflict here, resolved rather than ranked.**
        # A still-honoured session must be surfaced; and the exception that
        # brought us into teardown is the diagnosis and must not be replaced.
        # Raising satisfies the first and breaks the second, so it is done only
        # when nothing is in flight. When something is, the leak is attached to
        # it as a note: visible in the traceback, so not silent, and the original
        # type still propagates, so a caller matching on it still matches.
        #
        # What neither branch can do is *fix* the leak. The lease is not ours to
        # write and the supervisor's own write just failed. The lease lapsing is
        # FR-050's `capability_lapsed` path and is the fail-closed direction, so
        # the leak is bounded by the lease interval rather than unbounded — which
        # is why this is a report and not a retry loop.
        message = (
            f"{session_id!r} is still honoured after teardown "
            f"({after.state}, lease {after.lease_expires_at}). The capability "
            "outlives the run until the lease lapses, which is the leak the "
            "teardown handshake exists to prevent."
            + (f" The teardown itself failed: {failure!r}"
               if failure is not None else "")
        )
        in_flight = sys.exc_info()[1]
        if in_flight is None:
            raise RunnerError(message) from failure
        in_flight.add_note(f"runner teardown: {message}")

    def _loop(
        self,
        session_id: str,
        model: ModelClient,
        execute: Callable[[ToolCall], str],
        token: CancelToken,
    ) -> AgentLoop:
        return AgentLoop(
            session_id=session_id,
            store=self.store,
            budget=self.budget,
            journal=self.journal,
            spans=self.spans,
            machine=self.machine,
            bound=self.bound,
            retention=self.retention(session_id),
            model=model,
            execute=execute,
            versions=self.versions,
            clock=self.clock,
            assembler=self.assembler,
            merge_policy=self.merge_policy,
            cancel=token,
        )


def _require_token(cancel: CancelToken | None) -> CancelToken:
    """A `CancelToken`, or a fresh one that is never set.

    Typed rather than duck-typed because `cancel=True` is the plausible mistake:
    a bare truthy value is callable in no useful sense, and if it were accepted
    as a predicate every run would cancel before its first turn — a silent
    no-op that looks like a working runner.
    """
    if cancel is None:
        return CancelToken()
    if not isinstance(cancel, CancelToken):
        raise RunnerError(
            f"cancel must be a CancelToken, not {type(cancel).__name__}. A "
            "truthy value passed here would read as 'already cancelled' and "
            "every run would return before its first turn."
        )
    return cancel
