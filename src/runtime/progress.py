"""T067 — FR-006's stall predicate, and the configured threshold that fires it.

**This module exists because the stall condition stopped being unwritable.**
`tasks.md`'s loose-requirements row 6 and `data-model.md` §2.1 both record
`terminated.no_progress` as *owed, predicate unwritable as specified*, and both
were right when written: the taxonomy named the member and no requirement said
what no progress was. **FR-006 defined it on 2026-08-03** — `spec.md`'s *"The
stall condition, defined 2026-08-03"* — and the two notes are older than the
definition. Nothing here is invented; every clause below is a clause of FR-006,
and where this module makes a choice FR-006 left open the choice is named.

## The predicate, as FR-006 states it

> A turn makes progress when it does at least one of two things: it produces
> the session's reported result, or it issues at least one tool call that is
> **new to the session** — meaning the combination of the tool invoked, the
> arguments it was invoked with, and the outcome it returned does not already
> appear in this session. Identity here MUST be decided by the content address
> of the canonically serialized combination under FR-055, not by inspection.

So `call_address` hashes exactly three things, and the third is `ToolResult
.outcome` — FR-038's declared outcome vocabulary — **not the result body**.
That is the one place this module chooses, and the choice is forced:

* FR-006 names three components. A fourth would be an addition to a
  specification, made silently, in a hash nobody can read afterwards.
* **A body in the address would make the member unfireable.** Any tool whose
  result carries a timestamp, a request id or a duration returns different
  bytes every call, so every repeat would read as new and the count would never
  advance. A taxonomy member no configuration can ever fire is the defect
  FR-006's own note warns about, one level down.

`ToolResult.outcome` is also precisely what FR-006's third stall shape asks
for — *"a turn whose every tool call fails in a **way** already recorded in
this session for that call"*. A way, not a body.

## Derived from the journal, never counted on an object

The count is **recomputed from the session's turn records on every evaluation**
rather than incremented on the loop. This is the same property T064 turned out
to be about, and the reason is FR-007: a session is resumed in a **new process**
after a `SIGKILL`, and a counter living on `AgentLoop` would start again at zero
there. An agent that stalls, crashes, resumes and goes on stalling would reset
its own stall count at every crash and never terminate. Recomputing costs a walk
over records the loop is already holding, and it is correct across a resume
boundary because the records come off disk.

It also means the predicate is a **pure function of the records**, so the test
for it does not need a session, a store or a clock.

## The threshold is required configuration, and the reason is not the usual one

FR-006 makes the number required under FR-033 with **no default**, exactly as
FR-005's ceilings and FR-049's bounds are — and `spec.md` records that the
justification does **not** transfer:

> FR-005's ceilings and FR-049's bounds fail loudly when unset because an unset
> one is an unbounded liability. That is not true here: FR-005's turn ceiling
> already bounds every session, so an unset stall threshold costs no money and
> no time. What it costs is **the name**.

So `StallPolicy` has no default value and no `None` that disables it. A
deployment that does not want stall detection sets a threshold above its turn
ceiling, which is a number on the record; there is no configuration that makes
the member unproducible while leaving it declared.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from src.contracts.canonical import content_address
from src.contracts.transition import PredicateInput
from src.runtime.turn import TurnRecord

#: The name the reading carries onto the `state_transition` span. A string
#: rather than an ad-hoc literal at the construction site, because a reader
#: selecting spans on it is selecting on this.
READING_NAME = "consecutive_turns_without_progress"


class StallConfigurationError(ValueError):
    """A stall threshold that cannot be honoured as declared (FR-033)."""


@dataclass(frozen=True)
class StallPolicy:
    """How many consecutive turns without progress end the session.

    One field and no second one. There is deliberately no `enabled` flag: a
    boolean that switches the predicate off is a way for a deployment to leave
    `terminated.no_progress` declared and unproducible, which is the state
    FR-006 spent a paragraph arguing against.
    """

    consecutive_turns: int

    def __post_init__(self) -> None:
        if not isinstance(self.consecutive_turns, int) or isinstance(
            self.consecutive_turns, bool
        ):
            raise StallConfigurationError(
                f"the stall threshold is {self.consecutive_turns!r}; FR-006 "
                "asks for a number of consecutive turns. A bool is refused "
                "explicitly because `True` is an int in Python and would "
                "silently configure a threshold of one."
            )
        if self.consecutive_turns < 1:
            raise StallConfigurationError(
                f"a stall threshold of {self.consecutive_turns} would fire "
                "before any turn had run, or never. FR-006 counts consecutive "
                "turns that make no progress, and the smallest meaningful "
                "count is one."
            )


@dataclass(frozen=True)
class StallVerdict:
    """What the predicate read, whether or not it fired.

    Carries the reading in both cases on purpose. A verdict that only described
    itself when it fired would give the loop nothing to put on a span for the
    turns that did not, and *how close a session came* is the figure an operator
    tuning the threshold needs.
    """

    stalled: bool
    observed: int
    declared: int

    @property
    def reading(self) -> PredicateInput:
        return PredicateInput(
            name=READING_NAME,
            observed=str(self.observed),
            declared=str(self.declared),
            matched=self.stalled,
        )


def call_address(name: str, arguments, outcome: str | None) -> str:
    """FR-055's content address over FR-006's three components.

    `outcome` is `None` for a call with no recorded result — a turn journalled
    with its calls before their results landed. `None` rather than a stand-in
    string: two calls that both have no recorded outcome genuinely are the same
    combination, and a sentinel like `"unknown"` would collide with a tool that
    one day returns that word.
    """
    return content_address({
        "tool": name,
        "arguments": dict(arguments),
        "outcome": outcome,
    })


def turn_addresses(record: TurnRecord) -> tuple[str, ...]:
    """Every call this turn made, addressed.

    Results are matched to calls by the provider's declared index, which is the
    key `data-model.md` §2.2 already makes the ordering authority. Matching by
    list position would silently pair the wrong result with the wrong call on
    any turn where one call produced no result.
    """
    by_index = {r.index: r for r in record.tool_results}
    return tuple(
        call_address(
            call.name,
            call.arguments,
            by_index[call.index].outcome if call.index in by_index else None,
        )
        for call in record.tool_calls
    )


def consecutive_turns_without_progress(records: Sequence[TurnRecord]) -> int:
    """The count at the tail of the session, from the records alone.

    Walks forward accumulating what the session has seen, because *new to the
    session* is a question about everything before a turn and cannot be decided
    backwards. The trailing run of no-progress turns is then the count, and a
    turn that made progress resets it — FR-006 says so in terms, and it is what
    makes a single planning turn between two productive ones cost nothing.
    """
    seen: set[str] = set()
    run = 0
    for record in records:
        addresses = turn_addresses(record)
        # FR-006's first limb. A turn that issues no tool call is the turn that
        # produces the session's reported result — in this runtime it is the
        # turn the loop completes on — so it makes progress. It never actually
        # reaches a later evaluation, because the loop returns on it; the case
        # is handled rather than assumed away, so this function stays a total
        # function of the records a caller might hold.
        if not addresses:
            run = 0
            seen.update(addresses)
            continue
        # FR-006's second limb: **at least one** call new to the session. Not
        # all of them. A turn that repeats four calls and makes a fifth new one
        # has done something the session had not done.
        if any(address not in seen for address in addresses):
            run = 0
        else:
            run += 1
        seen.update(addresses)
    return run


def evaluate_stall(
    records: Sequence[TurnRecord] | Iterable[TurnRecord], policy: StallPolicy
) -> StallVerdict:
    """FR-006's stall condition, as a verdict the loop can act on or record."""
    ordered = tuple(records)
    observed = consecutive_turns_without_progress(ordered)
    return StallVerdict(
        stalled=observed >= policy.consecutive_turns,
        observed=observed,
        declared=policy.consecutive_turns,
    )
