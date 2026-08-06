"""T066 — the raw terminal signals FR-006's taxonomy sits on.

**What this module is for, in the words of the measurement that asks for it.**
[Finding 006](../../specs/001-discovery-validation/findings/006-graph-loop-primitives.md)
primitive 2 drove the removed dependency's graph runtime through four scenarios
and reported what a caller could observe at the end of each. Errors were named
well — `error_code`, `error_message`, and a propagating exception. Budget
exhaustion was named by exception type. And then:

> Consumer cancels after 5 events | generator returned | **Nothing. No marker,
> no signal.**

> What does not exist in any form: a terminal *name* … The raw signals to derive
> two of them are present. **The taxonomy is ours to build.**

So the split this module sits on either side of is not ours to invent: the
**taxonomy** was always ours (`src/contracts/terminal.py`, T067), and the **raw
signals** were the dependency's. **OD-15** removed the dependency, and nothing
replaced the signals. This module is that piece, and it is the one nothing else
in the tree supplies.

**Three signals, and the third is the one that was missing entirely.**

1. **Error identity** — `ErrorIdentity`. The runtime already *propagates* the
   exception that ended a run; what it did not do was put the exception's
   identity anywhere a reader of the record could find it. A session terminated
   as `terminated.unrecoverable_fault` said only that, and the type and message
   lived in a traceback that goes with the process. That is strictly less than
   the removed dependency offered, which is the direction **OD-15** must not
   leave things in.
2. **Budget-exhaustion cause** — `ExhaustionCause`. Which of FR-005's four
   ceilings fired, with the reading that fired it and the ceiling it was read
   against. The `CeilingVerdict` already holds this; what was absent is a shape
   that carries it past the loop's own return.
3. **An explicit end-of-run marker** — `EndOfRun`, separating completion from
   cancellation. This is the row quoted above. The dependency *could* emit one,
   under `Workflow._emit_end_of_agent`, and returned early unless the
   `@experimental` `is_resumable` flag was set — **which it is not by default**,
   so the shipped behaviour was that a run which finished and a run cut off
   mid-loop produced the same observation. `research/03` §3 names that the
   false-success shape and calls it a very common and very expensive bug.

**Why the marker cannot be optional here, structurally rather than by
convention.** The defect above was not the absence of a marker; it was a marker
behind a default-off flag, so *absence* was ambiguous between *this run did not
end* and *nobody turned the marker on*. Two rules keep that from recurring:

- `EndOfRun` has **no reason meaning "the run did not end"**. A caller holding
  no marker holds no marker, and there is no value of `reason` that lets an
  un-ended run masquerade as a completion.
- `LoopOutcome` and `RunOutcome` both refuse to carry a terminal state without
  a marker, and refuse a marker that names a different terminal state than the
  field beside it. The pairing is checked at construction, so the two cannot be
  written by different code paths and disagree.

**The reason set is what the runtime itself produces, and the boundary is
stated rather than left as an omission.** FR-049's three bounds and FR-050's
lapsed capability are terminal states this process does not observe — they are
recorded by the supervisor, which is what `SessionStateMachine.terminate`'s own
refusal message says. A reason for them here would be a signal nothing in this
process can raise.

**Membership stays in `src/contracts/terminal.py` and is not restated here.**
**OD-26** makes that module authoritative for *which names exist*; this one maps
a raw signal to one of them, and every entry in the map is put through
`terminal.require()` at import, so a reason naming a member that does not exist
fails at import rather than at the first run that reaches it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.contracts import terminal
from src.runtime.session_store import CeilingVerdict

# The reasons a run ends, as this process can observe them.
REASON_COMPLETED = "completed"
REASON_CANCELLED = "cancelled"
REASON_CEILING_REACHED = "ceiling_reached"
REASON_FAULTED = "faulted"
REASON_NO_PROGRESS = "no_progress"

#: Reason → the taxonomy member it names, or `None` where the member is carried
#: by the signal's own cause. `ceiling_reached` is the one such case: FR-005 has
#: four ceilings and four members, and collapsing them to one reason with one
#: member would lose which ceiling fired — the thing `TERMINAL_BY_CEILING`
#: exists to keep.
_MEMBER_BY_REASON: dict[str, str | None] = {
    REASON_COMPLETED: terminal.COMPLETED.name,
    REASON_CANCELLED: terminal.OPERATOR_TERMINATED.name,
    REASON_CEILING_REACHED: None,
    REASON_FAULTED: terminal.UNRECOVERABLE_FAULT.name,
    # T067. No cause field beside it, unlike `ceiling_reached`. That one needs
    # one because four members share the reason and the marker would otherwise
    # not say which; this reason names exactly one member, and the reading that
    # fired it is already a predicate input on the `state_transition` span the
    # marker rides in. A second copy there would be the same figure recorded
    # twice with nothing keeping them equal.
    REASON_NO_PROGRESS: terminal.NO_PROGRESS.name,
}

REASONS: frozenset[str] = frozenset(_MEMBER_BY_REASON)

# Checked at import, not at the first run that reaches a reason. A member
# renamed in the taxonomy and not here would otherwise be a failure that waits
# for the one path nobody exercises — which is how `terminated.no_progress` sat
# declared-and-absent for weeks (finding 027).
for _reason, _member in _MEMBER_BY_REASON.items():
    if _member is not None:
        terminal.require(_member)
del _reason, _member


class SignalError(ValueError):
    """A terminal signal that cannot be described as stated."""


@dataclass(frozen=True)
class ErrorIdentity:
    """What ended a run, named — not a formatted traceback.

    Two fields and no third. `type_name` is the identity a caller can branch
    on; `message` is for a human. There is deliberately no traceback field: a
    traceback is not an identity, it is bytes whose content depends on the
    frames the process happened to have, and `src/supervisor/lease.py`'s note
    already records at length why a traceback is a poor operator interface.

    **This is not a terminal state and must not be read as one.** FR-006's
    `terminated.unrecoverable_fault` is *"a fault the runtime cannot classify
    further"*; this says which fault it was. Putting the type name into a
    terminal state instead would be `terminated.<ExceptionClassName>`, which is
    the generic error FR-006 forbids wearing a specific-looking name.
    """

    type_name: str
    message: str

    def __post_init__(self) -> None:
        if not self.type_name:
            raise SignalError(
                "an error identity with no type name identifies nothing. The "
                "whole point of this signal is that "
                "terminated.unrecoverable_fault says a fault happened and not "
                "which one."
            )

    @classmethod
    def from_exception(cls, exc: BaseException) -> "ErrorIdentity":
        return cls(type_name=type(exc).__name__, message=str(exc))

    def to_record(self) -> dict[str, Any]:
        return {"type": self.type_name, "message": self.message}


@dataclass(frozen=True)
class ExhaustionCause:
    """Which of FR-005's four ceilings fired, and on what reading.

    The declared figure travels with the observed one. A cause carrying only
    *"the token ceiling fired"* leaves a reader unable to tell a session that
    overshot by one token from one that overshot by a million, and those are
    different reports: the first is a ceiling working and the second is a
    reservation policy that is not bounding anything.
    """

    dimension: str
    observed: str
    declared: str
    terminal_state: str

    def __post_init__(self) -> None:
        # Through `require()` rather than `is_terminal()`, so the refusal names
        # the offending string and says where to add it.
        terminal.require(self.terminal_state)

    @classmethod
    def from_verdict(cls, verdict: CeilingVerdict) -> "ExhaustionCause":
        """The cause a `CeilingVerdict` already decided, carried forward.

        Reads the **matched** reading rather than re-deriving which ceiling
        won. `evaluate_ceilings` fires only the first breach and marks exactly
        that one, because several can be over at once and the record has to say
        which was seen first; a second pass over the readings here would be a
        second chance to pick a different one.
        """
        if not verdict.exceeded or verdict.terminal_state is None:
            raise SignalError(
                "this verdict reached no ceiling, so there is no exhaustion to "
                "describe. A cause built from a verdict whose own readings say "
                "the session was within its ceilings would report an "
                "exhaustion that did not happen."
            )
        matched = [reading for reading in verdict.readings if reading.matched]
        if len(matched) != 1:
            raise SignalError(
                f"{len(matched)} readings are marked as the one that matched. "
                "`evaluate_ceilings` marks exactly one — the first breach — "
                "and a verdict with none or several has lost which ceiling "
                "was seen."
            )
        reading = matched[0]
        return cls(
            dimension=reading.name,
            observed=reading.observed,
            declared="" if reading.declared is None else reading.declared,
            terminal_state=verdict.terminal_state,
        )

    def to_record(self) -> dict[str, Any]:
        return {
            "dimension": self.dimension,
            "observed": self.observed,
            "declared": self.declared,
            "terminal_state": self.terminal_state,
        }


@dataclass(frozen=True)
class EndOfRun:
    """The explicit marker. A run that ended has one; a run that did not has none.

    **Every reason that has a cause is required to carry it**, in both
    directions. A `faulted` marker with no error identity would be the state the
    runtime was already in before this module existed — the fault named and its
    identity gone — and a `completed` marker carrying one would be a success
    record with a failure attached, which is worse than either.
    """

    session_id: str
    reason: str
    at: float
    error: ErrorIdentity | None = None
    exhaustion: ExhaustionCause | None = None

    def __post_init__(self) -> None:
        if self.reason not in REASONS:
            raise SignalError(
                f"{self.reason!r} is not a declared end-of-run reason; the set "
                f"is {sorted(REASONS)}. FR-049's bounds and FR-050's lapsed "
                "capability are not here on purpose: they are observed by the "
                "supervisor, and a reason this process cannot raise would be a "
                "signal with no emitter."
            )
        if (self.reason == REASON_FAULTED) != (self.error is not None):
            raise SignalError(
                f"reason {self.reason!r} and error={self.error!r} disagree. An "
                "error identity belongs to a fault and to nothing else — a "
                "fault without one is the hole this signal exists to fill, and "
                "any other reason with one is a success record carrying a "
                "failure."
            )
        if (self.reason == REASON_CEILING_REACHED) != (self.exhaustion is not None):
            raise SignalError(
                f"reason {self.reason!r} and exhaustion={self.exhaustion!r} "
                "disagree. Which ceiling fired is the whole content of a "
                "ceiling termination, and no other reason has one."
            )

    @property
    def terminal_state(self) -> str:
        """The taxonomy member this marker names. Never `None`.

        A marker exists only for a run that ended, and FR-006 requires an ended
        run to name a member — so there is no reading under which this is
        absent. The `None` in `_MEMBER_BY_REASON` is *"the member is on the
        cause"*, and `__post_init__` has already refused a `ceiling_reached`
        marker without one.
        """
        member = _MEMBER_BY_REASON[self.reason]
        if member is not None:
            return member
        assert self.exhaustion is not None  # refused in __post_init__
        return self.exhaustion.terminal_state

    def to_record(self) -> dict[str, Any]:
        record: dict[str, Any] = {
            "reason": self.reason,
            "terminal_state": self.terminal_state,
            "at": self.at,
        }
        if self.error is not None:
            record["error"] = self.error.to_record()
        if self.exhaustion is not None:
            record["exhaustion"] = self.exhaustion.to_record()
        return record


def require_paired(terminal_state: str | None, marker: "EndOfRun | None") -> None:
    """Refuse a terminal state without its marker, or one that disagrees with it.

    Shared by `LoopOutcome` and `RunOutcome` rather than written twice. Two
    copies of a pairing rule are two chances for one of them to be relaxed, and
    the relaxation that matters is the same one every time: letting a run report
    a terminal state that no marker witnessed, which is how the marker goes back
    to being decoration.
    """
    if (terminal_state is None) != (marker is None):
        raise SignalError(
            f"terminal_state={terminal_state!r} and end_of_run={marker!r} "
            "disagree about whether the run ended. Finding 006's measurement is "
            "that a caller could not tell a finished run from one cut off "
            "mid-loop; an outcome carrying one of these and not the other puts "
            "that back."
        )
    if marker is not None and marker.terminal_state != terminal_state:
        raise SignalError(
            f"the marker names {marker.terminal_state!r} and the outcome "
            f"reports {terminal_state!r}. One of the two is what the session "
            "row holds and the other is not, and nothing here can say which."
        )
