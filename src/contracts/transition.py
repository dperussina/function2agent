"""`state_transition` records carrying their predicate inputs and deciding rule.

**Constitution Principle VI at v1.3.0, and which of its two readings held.**

The amendment generalised the superseded *"the routing decision with its
predicate inputs for every conditional edge"* to **"every decision that selected
among alternatives"** — the decision, the inputs its predicate matched on, and
the identity of the rule that produced it. FR-038 enumerates egress and
filesystem decisions only, so the span kind the principle reaches and the
requirement does not is `state_transition`. The spec records two honest readings
and picks neither. **The constitution binds directly, so the reading has to be
settled against the code, and it is settled here.**

*The second reading holds: v1's state machine is not determined by the prior
state and the typed outcome.* The evidence is `src/supervisor/bounds.py`'s
`check()`, which selects among three terminal states by consulting
`memory.events oom_kill`, `pids.events max` and `cpu.stat usage_usec` against
three declared limits, **in a fixed order that is itself part of the decision** —
a session that exhausted memory and forked past `pids.max` in the same interval
terminates as `memory_bound_exhausted` because memory is read first. None of
that is recoverable from the prior state plus the resulting terminal state:
`terminated.memory_bound_exhausted` tells a reader *which* alternative won and
nothing about what the others read. FR-005's four ceilings have the same shape.

So transitions carry predicate inputs and a deciding rule. Three consequences
that are deliberate:

1. **Every consulted input is recorded, not only the matching one.** The
   principle asks for "the inputs the predicate matched on"; recording the
   non-matching readings too is what makes the ordering visible, and Principle
   VI's own rationale — failure localization as a query over
   `(terminal_type, failing_unit, deciding_rule)` — is answerable only if a
   reader can see that the process bound was also breached.
2. **`deciding_rule` has no default.** Same discipline as FR-011's `rule_id` on
   an egress denial, for the same reason: a rule that is part of the record
   cannot be an annotation added later.
3. **A transition with no predicate inputs must say it is determined.** Empty
   is then a claim someone made rather than a field someone forgot. This is
   what keeps the first reading available where it is actually true — the
   `STARTING → RUNNING` edge really does select among nothing — without letting
   it be assumed everywhere.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.contracts.canonical import content_address
from src.contracts.terminal import is_terminal

# Session lifecycle states. Duplicated from session_table's constants
# deliberately: an invariant test asserts the two agree, which is a check, where
# an import would be an assumption.
STATE_STARTING = "STARTING"
STATE_RUNNING = "RUNNING"
STATE_TERMINATED = "TERMINATED"
# `data-model.md` §2.1's `interrupted ─▶ RUNNING` edge. Not a terminal state: a
# session that resumes has not ended, which is why it carries no member of the
# taxonomy. Added with T049, and **nothing drives the outward edge yet** — the
# producer is T052's resume reconstruction. It is declared here rather than
# later because the alternative is retrofitting a state into a closed set, and
# `STATES` is closed on purpose.
STATE_INTERRUPTED = "INTERRUPTED"
STATES = frozenset({
    STATE_STARTING, STATE_RUNNING, STATE_TERMINATED, STATE_INTERRUPTED,
})


@dataclass(frozen=True)
class TransitionRule:
    """A rule that can produce a transition.

    `selects_among_alternatives` is the honest half of the taxonomy: it is
    False only where the edge is genuinely determined by the prior state, and a
    rule that claims it while carrying predicate inputs is a contradiction the
    record refuses to hold.
    """

    rule_id: str
    reason: str
    selects_among_alternatives: bool
    description: str


# The registry. Stable identifiers, never indices.
ST_SESSION_STARTED = TransitionRule(
    "ST-001", "session_started", False,
    "STARTING → RUNNING. Determined by the prior state: the supervisor has "
    "brought the session up and there is no alternative to select among.",
)
ST_LEASE_RENEWED = TransitionRule(
    "ST-002", "lease_renewed", False,
    "RUNNING → RUNNING. Guarded on the prior state being RUNNING and on "
    "nothing else (FR-050).",
)
ST_WORK_COMPLETED = TransitionRule(
    "ST-003", "work_completed", False,
    "RUNNING → TERMINATED with terminated.completed. The run finished; no "
    "limit was consulted.",
)
ST_BOUND_EXHAUSTED = TransitionRule(
    "ST-004", "bound_exhausted", True,
    "RUNNING → TERMINATED selecting among FR-049's three bounds. The "
    "predicate inputs are the three cgroup readings against the three "
    "declared limits, and the order memory → process → processor decides "
    "which wins when more than one is breached.",
)
ST_CEILING_REACHED = TransitionRule(
    "ST-005", "ceiling_reached", True,
    "RUNNING → TERMINATED selecting among FR-005's four ceilings — spend, "
    "tokens, wall clock, turns — by consulting each accrued value against "
    "its declared ceiling.",
)
ST_CAPABILITY_LAPSED = TransitionRule(
    "ST-006", "capability_lapsed", True,
    "RUNNING → TERMINATED because the lease expired without renewal. The "
    "predicate input is the lease expiry against the observing clock; it "
    "selects among alternatives because a session that is also over a bound "
    "could terminate either way and the reader needs to know which was seen.",
)
ST_OPERATOR_TERMINATED = TransitionRule(
    "ST-007", "operator_terminated", False,
    "RUNNING → TERMINATED by a human act. No limit was consulted; the "
    "operator's identity belongs on the record, not in the predicate.",
)
ST_UNRECOVERABLE_FAULT = TransitionRule(
    "ST-008", "unrecoverable_fault", False,
    "RUNNING → TERMINATED on a fault the runtime cannot classify further. "
    "Reaching it is a defect report (FR-006).",
)

ST_SESSION_INTERRUPTED = TransitionRule(
    "ST-009", "session_interrupted", False,
    "RUNNING → INTERRUPTED. The session stopped without ending; no limit was "
    "consulted and no terminal state is named, because FR-007 resumes this "
    "same session.",
)
ST_SESSION_RESUMED = TransitionRule(
    "ST-010", "session_resumed", False,
    "INTERRUPTED → RUNNING. `data-model.md` §2.1's resume edge. Determined by "
    "the prior state: a session is resumable exactly when it is interrupted.",
)

RULES: tuple[TransitionRule, ...] = (
    ST_SESSION_STARTED, ST_LEASE_RENEWED, ST_WORK_COMPLETED,
    ST_BOUND_EXHAUSTED, ST_CEILING_REACHED, ST_CAPABILITY_LAPSED,
    ST_OPERATOR_TERMINATED, ST_UNRECOVERABLE_FAULT,
    ST_SESSION_INTERRUPTED, ST_SESSION_RESUMED,
)
RULES_BY_ID = {rule.rule_id: rule for rule in RULES}


@dataclass(frozen=True)
class PredicateInput:
    """One reading the transition's predicate consulted.

    `declared` is None where the predicate has no limit to compare against.
    `matched` says whether this reading was the one that fired, which is what
    makes an ordered selection legible after the fact.
    """

    name: str
    observed: str
    declared: str | None
    matched: bool

    def to_record(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "observed": self.observed,
            "declared": self.declared,
            "matched": self.matched,
        }


class TransitionError(ValueError):
    """A transition record that cannot be built as described."""


@dataclass(frozen=True)
class StateTransition:
    """One `state_transition` span's payload."""

    session_id: str
    from_state: str
    to_state: str
    deciding_rule: str
    at: float
    terminal_state: str | None = None
    predicate_inputs: tuple[PredicateInput, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.from_state not in STATES:
            raise TransitionError(f"unknown from_state {self.from_state!r}")
        if self.to_state not in STATES:
            raise TransitionError(f"unknown to_state {self.to_state!r}")

        rule = RULES_BY_ID.get(self.deciding_rule)
        if rule is None:
            raise TransitionError(
                f"{self.deciding_rule!r} is not a registered transition rule. "
                "Principle VI requires the identity of the rule that produced "
                "the transition, and an unregistered string is not an "
                "identity — add it to RULES in src/contracts/transition.py."
            )

        # FR-006: reaching TERMINATED means naming a member of the taxonomy.
        if self.to_state == STATE_TERMINATED:
            if not self.terminal_state:
                raise TransitionError(
                    "a transition into TERMINATED must name a terminal state "
                    "(FR-006)"
                )
            if not is_terminal(self.terminal_state):
                raise TransitionError(
                    f"{self.terminal_state!r} is not in the declared "
                    "terminal-state taxonomy (FR-006)"
                )
        elif self.terminal_state is not None:
            raise TransitionError(
                "a transition that does not reach TERMINATED must not name a "
                "terminal state"
            )

        # The Principle VI obligation, enforced structurally in both
        # directions so neither half can drift into decoration.
        if rule.selects_among_alternatives and not self.predicate_inputs:
            raise TransitionError(
                f"{rule.rule_id} ({rule.reason}) selects among alternatives, so "
                "constitution Principle VI requires the inputs its predicate "
                "matched on. Recording the outcome without them makes the "
                "selection unrecoverable — which alternative won is on the "
                "record and what the others read is not."
            )
        if not rule.selects_among_alternatives and self.predicate_inputs:
            raise TransitionError(
                f"{rule.rule_id} ({rule.reason}) is declared determined by the "
                "prior state, but predicate inputs were supplied. One of the "
                "two is wrong: either the rule selects among alternatives and "
                "its registry entry should say so, or these inputs are not "
                "predicate inputs."
            )
        if rule.selects_among_alternatives and not any(
            p.matched for p in self.predicate_inputs
        ):
            raise TransitionError(
                f"{rule.rule_id} selected among alternatives but no predicate "
                "input is marked as the one that matched. A selection with no "
                "winner is not a selection."
            )

    def to_record(self) -> dict[str, Any]:
        return {
            "kind": "state_transition",
            "session_id": self.session_id,
            "from_state": self.from_state,
            "to_state": self.to_state,
            "terminal_state": self.terminal_state,
            "deciding_rule": self.deciding_rule,
            "reason": RULES_BY_ID[self.deciding_rule].reason,
            "predicate_inputs": [p.to_record() for p in self.predicate_inputs],
            "at": self.at,
        }

    def content_address(self) -> str:
        return content_address(self.to_record())


def from_bound_outcome(
    *,
    session_id: str,
    outcome: Any,
    readings: tuple[PredicateInput, ...],
    at: float,
) -> StateTransition:
    """Build the transition `bounds.check()` produced.

    `readings` is every bound consulted in the pass, not only the one that
    fired, so the ordering that decided the outcome is on the record.
    """
    return StateTransition(
        session_id=session_id,
        from_state=STATE_RUNNING,
        to_state=STATE_TERMINATED,
        terminal_state=outcome.terminal_state,
        deciding_rule=ST_BOUND_EXHAUSTED.rule_id,
        predicate_inputs=readings,
        at=at,
    )
