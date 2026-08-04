"""The declared terminal-state taxonomy (FR-006).

FR-006 requires a session to end in a **named** terminal state, never by
generic error. A taxonomy that lives in prose is one a later contributor adds
`terminated.error` to without noticing; this module is the taxonomy, and
`tests/invariants/test_terminal_taxonomy.py` is the check that stops the
addition.

Membership is closed. `is_terminal()` is not a pattern match on a prefix —
a prefix match would accept `terminated.something_someone_invented`, which is
exactly the generic error FR-006 forbids wearing a namespaced name.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TerminalState:
    name: str
    requirement: str
    meaning: str


# Completion.
COMPLETED = TerminalState(
    "terminated.completed", "FR-006", "the run finished its work")

# FR-005's four ceilings, one terminal state each. A ceiling that ended a run
# without saying which ceiling it was would make the record unactionable.
SPEND_CEILING = TerminalState(
    "terminated.spend_ceiling_reached", "FR-005", "the spend ceiling was hit")
TOKEN_CEILING = TerminalState(
    "terminated.token_ceiling_reached", "FR-005", "the token ceiling was hit")
WALL_CLOCK_CEILING = TerminalState(
    "terminated.wall_clock_ceiling_reached", "FR-005",
    "the wall-clock ceiling was hit")
TURN_CEILING = TerminalState(
    "terminated.turn_ceiling_reached", "FR-005", "the turn ceiling was hit")

# FR-049's three bounds. These are the strings `src/supervisor/bounds.py` emits;
# the invariant test asserts the two agree rather than trusting them to.
MEMORY_BOUND = TerminalState(
    "terminated.memory_bound_exhausted", "FR-049",
    "memory.max was exhausted and memory.oom.group killed the session")
CPU_BOUND = TerminalState(
    "terminated.cpu_bound_exhausted", "FR-049",
    "cumulative CPU-seconds passed the declared total")
PROCESS_BOUND = TerminalState(
    "terminated.process_bound_exhausted", "FR-049", "pids.max was reached")

# Refusals and faults, each named.
CAPABILITY_LAPSED = TerminalState(
    "terminated.capability_lapsed", "FR-050",
    "the lease expired without renewal — the crash path, where nothing ran")
OPERATOR_TERMINATED = TerminalState(
    "terminated.operator_terminated", "FR-006", "a human ended the session")
UNRECOVERABLE_FAULT = TerminalState(
    "terminated.unrecoverable_fault", "FR-006",
    "a fault the runtime cannot classify further. Named, bounded, and "
    "deliberately not a catch-all: reaching it is a defect report, not a "
    "normal outcome, and it exists so that nothing is tempted to invent a "
    "generic error when a fault does not fit above.")

TAXONOMY: tuple[TerminalState, ...] = (
    COMPLETED,
    SPEND_CEILING, TOKEN_CEILING, WALL_CLOCK_CEILING, TURN_CEILING,
    MEMORY_BOUND, CPU_BOUND, PROCESS_BOUND,
    CAPABILITY_LAPSED, OPERATOR_TERMINATED, UNRECOVERABLE_FAULT,
)

NAMES: frozenset[str] = frozenset(state.name for state in TAXONOMY)
BY_NAME = {state.name: state for state in TAXONOMY}


class UndeclaredTerminalState(ValueError):
    """A terminal state outside the taxonomy. FR-006 forbids it."""


def is_terminal(name: str) -> bool:
    return name in NAMES


def require(name: str) -> TerminalState:
    try:
        return BY_NAME[name]
    except KeyError:
        raise UndeclaredTerminalState(
            f"{name!r} is not in the declared terminal-state taxonomy. "
            "FR-006 requires a named member; add it to src/contracts/"
            "terminal.py with its requirement and meaning rather than "
            "passing a string through."
        ) from None
