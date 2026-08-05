"""A miniature terminal-state taxonomy that its document agrees with.

The clean counterpart to `known-bad/src/contracts/terminal.py`. Every member
here has a `member` row in `specs/001-fixture/data-model.md`, and the two rows
that document carries which are *not* members are marked `owed` and `struck` —
the two legitimate constructs, which a check that only knew about membership
would report as defects.
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
OPERATOR_TERMINATED = TerminalState(
    "terminated.operator_terminated", "FR-006", "ended from outside the run")

# Declared, never listed. A binding that is not in the tuple is not a member,
# and reading the bindings instead of the tuple would make this one look like
# a taxonomy entry the document had forgotten.
NEVER_ADOPTED = TerminalState(
    "terminated.never_adopted", "FR-006", "drafted and not adopted")

TAXONOMY: tuple[TerminalState, ...] = (
    COMPLETED,
    SPEND_CEILING,
    OPERATOR_TERMINATED,
)

NAMES: frozenset[str] = frozenset(state.name for state in TAXONOMY)
