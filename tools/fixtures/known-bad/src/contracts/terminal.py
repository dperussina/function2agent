"""A miniature terminal-state taxonomy, for `lifecycle-taxonomy`.

Not the real one. This is the *code* side of a reconciliation fixture: the
document side is `specs/001-fixture/data-model.md`, and the two disagree in
every direction the check speaks on.

Written in the real module's shape rather than as a bare list, because the
parser reads `NAME = TerminalState("...", ...)` bindings and the tuple that
lists them. A fixture that declared its members some easier way would pin a
parser nobody runs.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TerminalState:
    name: str
    requirement: str
    meaning: str


COMPLETED = TerminalState(
    "terminated.completed", "FR-006", "the run finished its work")
SPEND_CEILING = TerminalState(
    "terminated.spend_ceiling_reached", "FR-005", "the spend ceiling was hit")

# Absent from the fixture document altogether. This is the shape three real
# members were in for weeks: reachable by the runtime, unmentioned by the
# specification, and nothing anywhere comparing the two.
OPERATOR_TERMINATED = TerminalState(
    "terminated.operator_terminated", "FR-006", "ended from outside the run")

# The document marks this one `owed`. It is not owed; it is here. A marking
# read only in the exempting direction would keep saying `not yet` about a
# member that ships, which is the blindness this fixture exists to refuse.
NO_PROGRESS = TerminalState(
    "terminated.no_progress", "FR-006", "consecutive turns made no progress")

# And the document has this one struck, as history. A struck name reappearing
# in the taxonomy means the strike was reversed without the table being told.
DENIED_OPERATION = TerminalState(
    "terminated.denied_operation", "FR-011", "an operation was refused")

TAXONOMY: tuple[TerminalState, ...] = (
    COMPLETED,
    SPEND_CEILING,
    OPERATOR_TERMINATED,
    NO_PROGRESS,
    DENIED_OPERATION,
)

NAMES: frozenset[str] = frozenset(state.name for state in TAXONOMY)
