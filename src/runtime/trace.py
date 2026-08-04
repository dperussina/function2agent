"""T036 / T037 — the span writer for the seven declared kinds (FR-030, FR-031, FR-038).

FR-038 declares a **closed set of seven kinds** and says a span of an undeclared
kind MUST NOT be written. That is enforced at construction here rather than
validated afterwards, because a span that was written and then found invalid has
already been written.

**The field list, and where each obligation is enforced:**

| FR-038 clause                              | Enforced by                       |
|--------------------------------------------|-----------------------------------|
| kind from the closed set                    | `KINDS` membership at construction |
| position, orderable without a clock         | `(session_id, turn, ordinal)`, monotonic per writer |
| artifact versions in force + tenant/deployment | `ArtifactVersions`, required, non-empty |
| typed outcome, never generic                | `OUTCOMES`; terminal span carries FR-006's name |
| decision + matched inputs + rule identifier | `DecisionFields`, required on the two decision kinds (T037) |
| precondition/postcondition results          | `pre`/`post`, required on `verification` |
| retry-versus-repair                         | `attempt_kind`, an explicit three-way |
| per-span cost + running ceiling totals      | `Cost`, all four totals required |

**Two places this goes beyond FR-038, and why.**

*Constitution Principle VI at v1.3.0* asks for the predicate inputs and the
deciding rule on **every decision that selected among alternatives**, not only
on egress and filesystem decisions. The kind that reaches is `state_transition`,
the reading was settled against `bounds.check` (see
`src/contracts/transition.py`), and the second reading held — so a
`state_transition` span carries a `StateTransition` payload with its predicate
inputs. **The constitution binds directly and FR-038 is narrower**, so the wider
obligation is the one implemented.

*Ordering without a clock.* FR-038 asks for position sufficient to order every
span in a session **totally, without reference to a clock**. A timestamp is
carried as data, and the ordinal is what ordering uses. `SpanWriter` allocates
ordinals monotonically and refuses a duplicate, so two spans cannot tie.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Mapping

from src.contracts.repository import Repository
from src.contracts.secret import Secret
from src.contracts.terminal import is_terminal
from src.contracts.transition import StateTransition

TABLE = "trace_span"

# FR-038's closed set. Adding a kind is a specification change.
MODEL_CALL = "model_call"
TOOL_CALL = "tool_call"
EGRESS_DECISION = "egress_decision"
FILESYSTEM_DECISION = "filesystem_decision"
STATE_TRANSITION = "state_transition"
VERIFICATION = "verification"
DRIFT_CHECK = "drift_check"

KINDS: tuple[str, ...] = (
    MODEL_CALL, TOOL_CALL, EGRESS_DECISION, FILESYSTEM_DECISION,
    STATE_TRANSITION, VERIFICATION, DRIFT_CHECK,
)

# The kinds T037 requires a rule identifier on.
DECISION_KINDS = frozenset({EGRESS_DECISION, FILESYSTEM_DECISION})

# Typed outcomes. FR-038: "a generic error MUST NOT be a span outcome, for the
# same reason FR-006 forbids it as a terminal state."
OUTCOME_OK = "ok"
OUTCOME_DENIED = "denied"
OUTCOME_REFUSED = "refused"
OUTCOME_NOT_VERIFIABLE = "not_verifiable"
OUTCOME_CEILING_REACHED = "ceiling_reached"
OUTCOME_BOUND_EXHAUSTED = "bound_exhausted"
OUTCOME_UPSTREAM_FAULT = "upstream_fault"
OUTCOME_TIMED_OUT = "timed_out"

OUTCOMES = frozenset({
    OUTCOME_OK, OUTCOME_DENIED, OUTCOME_REFUSED, OUTCOME_NOT_VERIFIABLE,
    OUTCOME_CEILING_REACHED, OUTCOME_BOUND_EXHAUSTED, OUTCOME_UPSTREAM_FAULT,
    OUTCOME_TIMED_OUT,
})

# The retry/repair distinction FR-038 asks to be explicit. Three values, not a
# boolean: "neither" is the ordinary case and folding it into "not a retry"
# makes a first attempt indistinguishable from a repair.
ATTEMPT_FIRST = "first"
ATTEMPT_RETRY = "retry"
ATTEMPT_REPAIR = "repair"
ATTEMPT_KINDS = frozenset({ATTEMPT_FIRST, ATTEMPT_RETRY, ATTEMPT_REPAIR})


class SpanError(ValueError):
    """A span that FR-038 forbids writing."""


@dataclass(frozen=True)
class ArtifactVersions:
    """The versions in force, plus FR-035's scope.

    Required and non-empty: FR-038 calls this "what makes an attribution
    reproducible after the configuration has moved", and an empty map is an
    attribution to nothing.
    """

    tenant_id: str
    deployment_id: str
    by_kind: Mapping[str, str]

    def __post_init__(self) -> None:
        if not self.tenant_id or not self.deployment_id:
            raise SpanError("a span must carry tenant and deployment identity (FR-035)")
        if not self.by_kind:
            raise SpanError(
                "a span must carry the versions of the artifacts in force "
                "(FR-038). An empty map makes the span unreproducible once "
                "the configuration moves, which is the case attribution is for."
            )
        for kind, address in self.by_kind.items():
            if not str(address).startswith("sha256:"):
                raise SpanError(
                    f"artifact version for {kind!r} is {address!r}, not a "
                    "content address. FR-054 requires the content-addressed "
                    "version, not a label."
                )


@dataclass(frozen=True)
class Cost:
    """Per-span cost and the running totals against FR-005's four ceilings."""

    spend_usd: float
    tokens: int
    wall_clock_seconds: float
    turns: int

    total_spend_usd: float
    total_tokens: int
    total_wall_clock_seconds: float
    total_turns: int

    def to_record(self) -> dict[str, Any]:
        return {
            "spend_usd": self.spend_usd,
            "tokens": self.tokens,
            "wall_clock_seconds": self.wall_clock_seconds,
            "turns": self.turns,
            "totals": {
                "spend_usd": self.total_spend_usd,
                "tokens": self.total_tokens,
                "wall_clock_seconds": self.total_wall_clock_seconds,
                "turns": self.total_turns,
            },
        }


@dataclass(frozen=True)
class DecisionFields:
    """FR-038's fourth clause, required on both decision kinds (T037).

    Recorded for permits as well as denials, because "a permit resolved by the
    wrong rule is the case an attribution has to be able to find".
    """

    rule_id: str
    resolved_tier: str
    matched: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not self.rule_id:
            raise SpanError(
                "a decision span must carry a rule identifier (FR-011, "
                "FR-048). A disposition with no rule is a record of what "
                "happened and not of what decided it."
            )
        if not self.matched:
            raise SpanError(
                "a decision span must carry the inputs the rule matched on "
                "(FR-038). Without them a permit by the wrong rule looks "
                "exactly like a permit by the right one."
            )


@dataclass(frozen=True)
class Span:
    """One trace record."""

    kind: str
    session_id: str
    turn: int
    ordinal: int
    outcome: str
    attempt_kind: str
    versions: ArtifactVersions
    cost: Cost
    at: float

    decision: DecisionFields | None = None
    transition: StateTransition | None = None
    terminal_state: str | None = None
    pre: Mapping[str, Any] | None = None
    post: Mapping[str, Any] | None = None
    detail: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise SpanError(
                f"{self.kind!r} is not one of FR-038's seven declared span "
                f"kinds ({list(KINDS)}). A span of an undeclared kind MUST NOT "
                "be written."
            )
        if self.outcome not in OUTCOMES:
            raise SpanError(
                f"{self.outcome!r} is not a declared outcome ({sorted(OUTCOMES)}). "
                "A generic error must not be a span outcome, for the same "
                "reason FR-006 forbids it as a terminal state."
            )
        if self.attempt_kind not in ATTEMPT_KINDS:
            raise SpanError(
                f"{self.attempt_kind!r} is not a declared attempt kind "
                f"({sorted(ATTEMPT_KINDS)}). FR-038 requires the "
                "retry-versus-repair distinction to be explicit."
            )
        if self.turn < 0 or self.ordinal < 0:
            raise SpanError("turn and ordinal are positions, not counters")

        # T037 — the rule identifier, required on the two decision kinds.
        if self.kind in DECISION_KINDS and self.decision is None:
            raise SpanError(
                f"a {self.kind} span must carry its decision fields — the "
                "rule identifier, the resolved tier, and the inputs the rule "
                "matched on (FR-011, FR-038, FR-048)."
            )
        if self.kind not in DECISION_KINDS and self.decision is not None:
            raise SpanError(
                f"a {self.kind} span carries decision fields; those belong on "
                "an egress or filesystem decision, and putting them elsewhere "
                "makes the T037 check miss the span that needed them."
            )

        # Principle VI at v1.3.0, wider than FR-038. See the module docstring.
        if self.kind == STATE_TRANSITION and self.transition is None:
            raise SpanError(
                "a state_transition span must carry its StateTransition, "
                "which holds the deciding rule and — where the transition "
                "selected among alternatives — the predicate inputs. "
                "Constitution Principle VI (v1.3.0) requires this for every "
                "decision that selected among alternatives, which is wider "
                "than FR-038's enumeration of egress and filesystem "
                "decisions; the constitution binds directly."
            )
        if self.kind != STATE_TRANSITION and self.transition is not None:
            raise SpanError("only a state_transition span carries a transition")

        if self.kind == VERIFICATION and (self.pre is None or self.post is None):
            raise SpanError(
                "a verification span must carry its precondition and "
                "postcondition results (FR-038, FR-025)."
            )

        if self.terminal_state is not None and not is_terminal(self.terminal_state):
            raise SpanError(
                f"{self.terminal_state!r} is not in FR-006's declared terminal "
                "taxonomy"
            )

        _refuse_secrets(self.detail, "detail")

    @property
    def position(self) -> tuple[str, int, int]:
        """Total order within a session, with no clock in it."""
        return (self.session_id, self.turn, self.ordinal)

    def to_record(self) -> dict[str, Any]:
        record: dict[str, Any] = {
            "kind": self.kind,
            "session_id": self.session_id,
            "turn": self.turn,
            "ordinal": self.ordinal,
            "outcome": self.outcome,
            "attempt_kind": self.attempt_kind,
            "tenant_id": self.versions.tenant_id,
            "deployment_id": self.versions.deployment_id,
            "artifact_versions": dict(self.versions.by_kind),
            "cost": self.cost.to_record(),
            "terminal_state": self.terminal_state,
            "at": self.at,
            "detail": dict(self.detail),
        }
        if self.decision is not None:
            record["decision"] = {
                "rule_id": self.decision.rule_id,
                "resolved_tier": self.decision.resolved_tier,
                "matched": dict(self.decision.matched),
            }
        if self.transition is not None:
            record["transition"] = self.transition.to_record()
        if self.pre is not None:
            record["pre"] = dict(self.pre)
        if self.post is not None:
            record["post"] = dict(self.post)
        return record


def _refuse_secrets(value: Any, path: str) -> None:
    """FR-036: a Secret must never reach a trace.

    `Secret` has no serializer, so it would render as a redaction marker rather
    than a credential — but a marker in a trace is a field somebody will later
    "fix" by unwrapping. Refusing it here means the credential never gets close.
    """
    if isinstance(value, Secret):
        raise SpanError(
            f"{path} holds a Secret. A credential must not reach a trace "
            "(FR-036); pass a reference, not the value."
        )
    if isinstance(value, Mapping):
        for key, item in value.items():
            _refuse_secrets(item, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for item in value:
            _refuse_secrets(item, f"{path}[]")


class SpanWriter:
    """Allocates ordinals and persists spans. Owned by the runtime (T017)."""

    def __init__(self, repository: Repository) -> None:
        self.repo = repository
        self._lock = threading.Lock()
        self._next: dict[tuple[str, int], int] = {}
        self._written: set[tuple[str, int, int]] = set()
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        self.repo.create_table(TABLE, {
            "session_id": "text not null",
            "turn": "int not null",
            "ordinal": "int not null",
            "kind": "text not null",
            "outcome": "text not null",
            "attempt_kind": "text not null",
            "rule_id": "text",
            "terminal_state": "text",
            "at": "real not null",
            "payload": "text not null",
        })

    def next_ordinal(self, session_id: str, turn: int) -> int:
        with self._lock:
            key = (session_id, turn)
            ordinal = self._next.get(key, 0)
            self._next[key] = ordinal + 1
            return ordinal

    def write(self, span: Span) -> None:
        from src.contracts.canonical import dumps

        with self._lock:
            if span.position in self._written:
                raise SpanError(
                    f"a span already occupies position {span.position}. "
                    "FR-038 requires positions sufficient to order a session "
                    "totally, and two spans at one position is a tie."
                )
            self._written.add(span.position)

        self.repo.insert(TABLE, {
            "session_id": span.session_id,
            "turn": span.turn,
            "ordinal": span.ordinal,
            "kind": span.kind,
            "outcome": span.outcome,
            "attempt_kind": span.attempt_kind,
            "rule_id": span.decision.rule_id if span.decision else None,
            "terminal_state": span.terminal_state,
            "at": span.at,
            "payload": dumps(span.to_record()).decode(),
        })

    def spans(self, session_id: str) -> list[dict[str, Any]]:
        rows = self.repo.select(
            TABLE, where={"session_id": session_id}, order_by="ordinal")
        return sorted(rows, key=lambda r: (r["turn"], r["ordinal"]))
