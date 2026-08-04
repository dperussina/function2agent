"""T049 — `data-model.md` §2.1's lifecycle, and FR-006's named terminal states.

**The division of labour, because it is not the obvious one.** The runtime
decides a transition and the supervisor applies it. `session` is the
supervisor's table; the runtime is the process that knows a ceiling was reached,
that the work completed, or that a fault could not be classified further. So
this module validates the edge against the lifecycle, builds the
`StateTransition` record with its predicate inputs and deciding rule, and then
asks the `LifecycleGateway` to move the row — and **reads the row back** to
confirm it moved.

**Why the read-back.** Every write here is a guarded update: `STARTING → RUNNING`
matches only a row in `STARTING`. A guarded update that matches nothing looks
exactly like one that worked unless the caller checks, and the two differ by
whether the session is in the state the rest of the system now believes it is
in. The count is checked *and* the row is re-read, because the count says the
statement matched and the row says what it matched to.

**Who drives the two non-terminal edges.** `interrupt()` and `resume()` are the
runner's: T046 interrupts on cancellation and on an attempt bounded short, and
`attach()` resumes. What is still *not* here is resume **reconstruction** —
replaying the journal to rebuild the turns an interrupted attempt produced. That
is T052's, and the difference matters: the edge carries the ceilings and the turn
numbering, because both read the journal, and it does not carry the transcript.
"""

from __future__ import annotations

from src.contracts import terminal
from src.contracts.transition import (
    ST_CEILING_REACHED,
    ST_OPERATOR_TERMINATED,
    ST_SESSION_INTERRUPTED,
    ST_SESSION_RESUMED,
    ST_SESSION_STARTED,
    ST_UNRECOVERABLE_FAULT,
    ST_WORK_COMPLETED,
    STATE_INTERRUPTED,
    STATE_RUNNING,
    STATE_STARTING,
    STATE_TERMINATED,
    StateTransition,
    TransitionRule,
)
from src.runtime.session_store import CeilingVerdict, LifecycleGateway

# Which rule ends a session, for the terminal states a caller names directly.
# A rule per reason rather than one `terminate(reason)`, because Principle VI
# wants the identity of the rule and `deciding_rule` has no default.
_RULE_BY_TERMINAL: dict[str, TransitionRule] = {
    terminal.COMPLETED.name: ST_WORK_COMPLETED,
    terminal.OPERATOR_TERMINATED.name: ST_OPERATOR_TERMINATED,
    terminal.UNRECOVERABLE_FAULT.name: ST_UNRECOVERABLE_FAULT,
    terminal.SPEND_CEILING.name: ST_CEILING_REACHED,
    terminal.TOKEN_CEILING.name: ST_CEILING_REACHED,
    terminal.WALL_CLOCK_CEILING.name: ST_CEILING_REACHED,
    terminal.TURN_CEILING.name: ST_CEILING_REACHED,
}


class SessionStateError(RuntimeError):
    """A transition the declared lifecycle does not have."""


class SessionStateMachine:
    """Validates an edge, records it, and has the owner apply it."""

    def __init__(self, lifecycle: LifecycleGateway) -> None:
        self.lifecycle = lifecycle

    # -- edges -------------------------------------------------------------

    def start(self, session_id: str, *, at: float) -> StateTransition:
        return self._move(
            session_id,
            expect=STATE_STARTING,
            to_state=STATE_RUNNING,
            rule=ST_SESSION_STARTED,
            apply=lambda: self.lifecycle.mark_running(session_id),
            at=at,
        )

    def interrupt(self, session_id: str, *, at: float) -> StateTransition:
        return self._move(
            session_id,
            expect=STATE_RUNNING,
            to_state=STATE_INTERRUPTED,
            rule=ST_SESSION_INTERRUPTED,
            apply=lambda: self.lifecycle.mark_interrupted(session_id),
            at=at,
        )

    def resume(
        self, session_id: str, *, at: float, lease_expires_at: float
    ) -> StateTransition:
        """`interrupted ─▶ RUNNING`, the same session (FR-007).

        The lease is renewed rather than reissued. §2.4's invariant is that a
        resumed session keeps its capability handle, so a resume that minted a
        new one would be a different session wearing the same id.

        **`lease_expires_at` is required.** It was briefly `at + 1.0` when
        omitted, which is the runtime inventing a lease interval that
        `CAPABILITY_LEASE_INTERVAL_SECONDS` already declares and the supervisor
        already owns — and a resumed session whose lease expired a second later
        would be revoked for a reason nothing chose.
        """
        lease = lease_expires_at
        return self._move(
            session_id,
            expect=STATE_INTERRUPTED,
            to_state=STATE_RUNNING,
            rule=ST_SESSION_RESUMED,
            apply=lambda: self.lifecycle.mark_resumed(session_id, lease),
            at=at,
        )

    def complete(self, session_id: str, *, at: float) -> StateTransition:
        return self.terminate(
            session_id, terminal_state=terminal.COMPLETED.name, at=at)

    def terminate(
        self, session_id: str, *, terminal_state: str, at: float
    ) -> StateTransition:
        """FR-006 — end in a named member, with the rule that produced it.

        The taxonomy is checked before the row moves. A session driven into
        `TERMINATED` and *then* refused for its terminal state would be a
        session whose recorded outcome FR-006 forbids, with no way back.
        """
        state = terminal.require(terminal_state).name
        rule = _RULE_BY_TERMINAL.get(state)
        if rule is None:
            raise SessionStateError(
                f"{state!r} is in the taxonomy but no transition rule here "
                "produces it. Terminal states reached from outside the runtime "
                "— FR-049's three bounds and FR-050's lapsed capability — are "
                "recorded by the process that observes them."
            )
        if rule is ST_CEILING_REACHED:
            raise SessionStateError(
                f"{state!r} is one of FR-005's ceilings, which selects among "
                "four alternatives. Use terminate_on_ceiling() so the readings "
                "of the other three are on the record (Principle VI)."
            )
        return self._move(
            session_id,
            expect=STATE_RUNNING,
            to_state=STATE_TERMINATED,
            rule=rule,
            terminal_state=state,
            apply=lambda: self.lifecycle.terminate(session_id, state),
            at=at,
        )

    def terminate_on_ceiling(
        self, session_id: str, verdict: CeilingVerdict, *, at: float
    ) -> StateTransition:
        """FR-005's four, carrying every reading the pass consulted.

        The verdict is required rather than a terminal state, because the
        readings are what makes the ordered selection legible and they exist
        only on the verdict. A caller holding a terminal state and no verdict
        has already lost the other three readings.
        """
        if not verdict.exceeded or verdict.terminal_state is None:
            raise SessionStateError(
                "no ceiling was reached in this verdict, so there is nothing "
                "to terminate on. A termination whose own evidence says the "
                "session was within its ceilings is a defect, not an edge."
            )
        state = verdict.terminal_state
        return self._move(
            session_id,
            expect=STATE_RUNNING,
            to_state=STATE_TERMINATED,
            rule=ST_CEILING_REACHED,
            terminal_state=state,
            predicate_inputs=verdict.readings,
            apply=lambda: self.lifecycle.terminate(session_id, state),
            at=at,
        )

    # -- the one place a row moves -----------------------------------------

    def _move(
        self,
        session_id: str,
        *,
        expect: str,
        to_state: str,
        rule: TransitionRule,
        apply,
        at: float,
        terminal_state: str | None = None,
        predicate_inputs: tuple = (),
    ) -> StateTransition:
        row = self.lifecycle.get(session_id)
        if row is None:
            raise SessionStateError(f"{session_id!r} has no session row")
        if row.state == STATE_TERMINATED:
            raise SessionStateError(
                f"{session_id!r} is already terminated as "
                f"{row.terminal_state!r}. A second terminal state would "
                "overwrite the first, and FR-006's whole subject is that the "
                "recorded outcome is the one that happened."
            )
        if row.state != expect:
            raise SessionStateError(
                f"{session_id!r} is {row.state}, and {rule.rule_id} "
                f"({rule.reason}) is an edge out of {expect}. "
                "data-model.md §2.1's lifecycle has no such transition."
            )

        # Built before the write, so an invalid record cannot be one the row
        # already reflects.
        transition = StateTransition(
            session_id=session_id,
            from_state=row.state,
            to_state=to_state,
            terminal_state=terminal_state,
            deciding_rule=rule.rule_id,
            predicate_inputs=tuple(predicate_inputs),
            at=at,
        )

        changed = apply()
        if changed != 1:
            raise SessionStateError(
                f"{session_id!r}: the guarded update for {rule.rule_id} "
                f"changed {changed} rows. The row moved between the read and "
                "the write, so the transition this would have recorded is not "
                "the one that happened."
            )
        after = self.lifecycle.get(session_id)
        if after is None or after.state != to_state:
            raise SessionStateError(
                f"{session_id!r}: the update reported success but the row "
                f"reads {after.state if after else None!r}, not {to_state!r}."
            )
        return transition
