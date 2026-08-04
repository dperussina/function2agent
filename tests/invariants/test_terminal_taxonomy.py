"""INV-005 — every session terminal state is a named member of the declared
taxonomy (FR-006).

This is the check that stops a generic failure being introduced later. The
failure mode it targets is specific and mundane: someone adds
`terminated.error` or passes a formatted exception string through, and the
record stops being actionable while still looking structured.
"""

from __future__ import annotations

import pytest

from src.contracts.terminal import (
    NAMES,
    TAXONOMY,
    UndeclaredTerminalState,
    is_terminal,
    require,
)
from src.supervisor.bounds import BOUND_TERMINALS


@pytest.mark.parametrize("state", TAXONOMY, ids=lambda s: s.name)
def test_every_member_is_named_and_attributed(state) -> None:
    assert state.name.startswith("terminated.")
    assert state.requirement.startswith("FR-")
    assert state.meaning


def test_membership_is_closed_not_a_prefix_match() -> None:
    """The removal proof for a prefix-match regression.

    `terminated.error` is well-formed by every superficial test — it has the
    prefix, it is a string, it is lowercase. Only closed membership rejects it.
    """
    for invented in (
        "terminated.error",
        "terminated.failed",
        "terminated.something_someone_invented",
        "terminated.",
    ):
        assert not is_terminal(invented)
        with pytest.raises(UndeclaredTerminalState):
            require(invented)


def test_the_generic_names_are_absent() -> None:
    for generic in ("terminated.error", "terminated.failure", "terminated.unknown"):
        assert generic not in NAMES


def test_bounds_module_emits_only_declared_states() -> None:
    """FR-049's three strings and FR-006's taxonomy must be the same strings.

    They are declared in two files, so this is the check that they agree
    instead of drifting into two spellings of the same state.
    """
    for name in BOUND_TERMINALS:
        assert is_terminal(name), (
            f"src/supervisor/bounds.py emits {name!r}, which is not in the "
            "declared taxonomy"
        )


def test_each_ceiling_has_its_own_terminal_state() -> None:
    """FR-005 has four ceilings; one shared state would lose which was hit."""
    ceilings = [s for s in TAXONOMY if s.requirement == "FR-005"]
    assert len(ceilings) == 4
    assert len({s.name for s in ceilings}) == 4


def test_names_are_unique() -> None:
    assert len(NAMES) == len(TAXONOMY)
