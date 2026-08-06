"""T066 — the raw terminal signals, and the two shapes they exist to refuse.

**What is worth testing here and what is not.** A dataclass carrying three
strings needs no test. What needs one is the *pairing*: every rule in
`src/runtime/signals.py` exists because finding 006 measured a marker that could
be absent, and absence was ambiguous. Every arm below either exercises a refusal
or asserts that two runs which ended differently are distinguishable — nothing
here asserts that a field holds the value it was constructed with.

**The reason set is asserted against `terminal.require`, not against a list
written here.** A test that spelled the four members out would agree with a
taxonomy that had renamed one, because both sides would have been edited by the
same person in the same commit. Going through `require()` means the assertion is
made by the module that owns membership (**OD-26**).
"""

from __future__ import annotations

import pytest

from src.contracts import terminal
from src.contracts.transition import PredicateInput
from src.runtime.session_store import CeilingVerdict
from src.runtime.signals import (
    REASON_CANCELLED,
    REASON_CEILING_REACHED,
    REASON_COMPLETED,
    REASON_FAULTED,
    REASONS,
    EndOfRun,
    ErrorIdentity,
    ExhaustionCause,
    SignalError,
    require_paired,
)

SESSION = "sess-1"


def _verdict(fired: str = "tokens") -> CeilingVerdict:
    """A verdict shaped as `evaluate_ceilings` produces one: one match, all read."""
    readings = tuple(
        PredicateInput(name=name, observed="9", declared="4",
                       matched=(name == fired))
        for name in ("spend_usd", "tokens", "wall_clock_seconds", "turns")
    )
    return CeilingVerdict(
        exceeded=True,
        terminal_state=terminal.TOKEN_CEILING.name,
        readings=readings,
    )


# ---------------------------------------------------------------------------
# The marker separates the two runs finding 006 could not tell apart.


def test_completion_and_cancellation_are_different_members_of_a_closed_set() -> None:
    """The whole subject of T066, at the level of the signal itself.

    The removed dependency emitted its end-of-agent marker only under an
    experimental flag that defaults off, so a clean run and a run cut off
    mid-loop produced the same observation. Here they are two members of a
    closed set, and the set has no member meaning *the run did not end*.
    """
    done = EndOfRun(session_id=SESSION, reason=REASON_COMPLETED, at=1.0)
    cut = EndOfRun(session_id=SESSION, reason=REASON_CANCELLED, at=1.0)

    assert done.reason != cut.reason
    assert done.terminal_state != cut.terminal_state
    assert done.to_record() != cut.to_record()


def test_no_reason_means_the_run_did_not_end() -> None:
    """Absence is the only way to say *not ended*, and it is not a reason.

    A reason with that meaning would put back exactly what the flag did: a
    marker present on a run that had not finished, indistinguishable from one
    on a run that had.
    """
    for reason in REASONS:
        marker = EndOfRun(
            session_id=SESSION, reason=reason, at=1.0,
            error=(ErrorIdentity("Boom", "b") if reason == REASON_FAULTED
                   else None),
            exhaustion=(ExhaustionCause.from_verdict(_verdict())
                        if reason == REASON_CEILING_REACHED else None),
        )
        # Through `require`, so the taxonomy is what answers rather than a list
        # copied into this file.
        assert terminal.require(marker.terminal_state).name


def test_an_undeclared_reason_is_refused() -> None:
    for invented in ("ended", "done", "", "interrupted", "bound_exhausted"):
        with pytest.raises(SignalError, match="not a declared end-of-run reason"):
            EndOfRun(session_id=SESSION, reason=invented, at=1.0)


# ---------------------------------------------------------------------------
# A cause is required exactly where there is one, in both directions.


def test_a_fault_without_its_identity_is_refused() -> None:
    """The hole this signal fills, asserted as a refusal rather than a field.

    Before T066 a fault recorded `terminated.unrecoverable_fault` and the
    exception's type and message went out with the traceback. A marker that
    could say `faulted` with nothing attached would be that state again.
    """
    with pytest.raises(SignalError, match="error identity belongs to a fault"):
        EndOfRun(session_id=SESSION, reason=REASON_FAULTED, at=1.0)


def test_a_success_carrying_a_failure_is_refused() -> None:
    with pytest.raises(SignalError, match="error identity belongs to a fault"):
        EndOfRun(session_id=SESSION, reason=REASON_COMPLETED, at=1.0,
                 error=ErrorIdentity("ValueError", "nope"))


def test_a_ceiling_termination_must_say_which_ceiling() -> None:
    with pytest.raises(SignalError, match="Which ceiling fired"):
        EndOfRun(session_id=SESSION, reason=REASON_CEILING_REACHED, at=1.0)
    with pytest.raises(SignalError, match="Which ceiling fired"):
        EndOfRun(session_id=SESSION, reason=REASON_CANCELLED, at=1.0,
                 exhaustion=ExhaustionCause.from_verdict(_verdict()))


def test_an_error_identity_with_no_type_identifies_nothing() -> None:
    with pytest.raises(SignalError, match="identifies nothing"):
        ErrorIdentity(type_name="", message="something went wrong")


def test_the_identity_is_the_exception_class_and_not_its_text() -> None:
    """`type_name` is what a caller branches on; the message is for a human.

    Read off a real exception rather than constructed, because
    `from_exception` is the only constructor the runtime uses and a test that
    built the pair by hand would not exercise it.
    """
    class ProviderRefused(RuntimeError):
        pass

    identity = ErrorIdentity.from_exception(ProviderRefused("no credential"))
    assert identity.type_name == "ProviderRefused"
    assert identity.message == "no credential"
    assert "Traceback" not in identity.message


# ---------------------------------------------------------------------------
# The exhaustion cause reads the verdict's own decision.


def test_the_cause_names_the_ceiling_the_verdict_marked() -> None:
    """Not re-derived here. `evaluate_ceilings` fires the *first* breach and
    marks it; several dimensions can be over at once, so a second pass would be
    a second chance to name a different winner."""
    cause = ExhaustionCause.from_verdict(_verdict(fired="tokens"))
    assert cause.dimension == "tokens"
    assert cause.terminal_state == terminal.TOKEN_CEILING.name
    assert cause.observed == "9" and cause.declared == "4", (
        "the reading that fired is not on the cause. A cause naming only the "
        "dimension cannot tell an overshoot of one from an overshoot of a "
        "million, and those are different reports."
    )


def test_a_verdict_that_reached_no_ceiling_describes_no_exhaustion() -> None:
    within = CeilingVerdict(
        exceeded=False, terminal_state=None,
        readings=(PredicateInput("turns", "1", "4", False),))
    with pytest.raises(SignalError, match="reached no ceiling"):
        ExhaustionCause.from_verdict(within)


def test_a_verdict_with_no_single_winner_is_refused() -> None:
    """`StateTransition` refuses a selection with no winner; so does this.

    Two matched readings would make the recorded cause a coin toss between
    them, and the ordering that decided the real one would be lost.
    """
    both = CeilingVerdict(
        exceeded=True, terminal_state=terminal.SPEND_CEILING.name,
        readings=(PredicateInput("spend_usd", "9", "4", True),
                  PredicateInput("tokens", "9", "4", True)))
    with pytest.raises(SignalError, match="marked as the one that matched"):
        ExhaustionCause.from_verdict(both)


# ---------------------------------------------------------------------------
# The pairing rule the two outcome types share.


def test_a_terminal_state_without_a_marker_is_refused() -> None:
    with pytest.raises(SignalError, match="disagree about whether the run ended"):
        require_paired(terminal.COMPLETED.name, None)


def test_a_marker_without_a_terminal_state_is_refused() -> None:
    with pytest.raises(SignalError, match="disagree about whether the run ended"):
        require_paired(
            None, EndOfRun(session_id=SESSION, reason=REASON_COMPLETED, at=1.0))


def test_a_marker_that_names_a_different_state_is_refused() -> None:
    """The failure a pairing check on presence alone would miss.

    Two fields both populated agree on *that* the run ended and can still
    disagree on *how*. One of them is what the session row holds; nothing at
    this layer can say which, so neither is preferred and the pair is refused.
    """
    with pytest.raises(SignalError, match="names"):
        require_paired(
            terminal.OPERATOR_TERMINATED.name,
            EndOfRun(session_id=SESSION, reason=REASON_COMPLETED, at=1.0))


def test_no_terminal_state_and_no_marker_is_the_resumable_case() -> None:
    """An attempt bounded by `max_turns_this_attempt` ends nothing, and must
    not be forced to invent a marker to say so."""
    require_paired(None, None)


# ---------------------------------------------------------------------------
# The rule reaches the two types callers actually hold.
#
# `require_paired` being correct is worth nothing if the outcome types do not
# call it. These two arms are what fail if either `__post_init__` is deleted —
# without them the calls are removable with the suite green, and the pairing
# becomes a convention rather than a guarantee.


def test_a_loop_outcome_cannot_report_a_terminal_state_with_no_marker() -> None:
    from src.runtime.loop import LoopOutcome

    with pytest.raises(SignalError, match="disagree about whether the run ended"):
        LoopOutcome(turns=(), terminal_state=terminal.COMPLETED.name, text="hi")


def test_a_run_outcome_cannot_report_a_terminal_state_with_no_marker() -> None:
    from src.runtime.runner import RunOutcome

    with pytest.raises(SignalError, match="disagree about whether the run ended"):
        RunOutcome(session_id=SESSION, turns=(),
                   terminal_state=terminal.OPERATOR_TERMINATED.name,
                   text="", cancelled=True, merged_state={})
