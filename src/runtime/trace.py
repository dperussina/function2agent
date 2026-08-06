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
carried as data, and the ordinal is what ordering uses. The total order is held
by a **unique index on the table**, not by a writer: `SpanWriter` allocates
ordinals monotonically and seeds its counter from the store, but what makes two
spans unable to tie is the index, because the claim has to hold across two
writers over one repository and across the crash a resumed session survives.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field, fields
from typing import Any, Mapping

from src.contracts.repository import Repository, UniquenessError
from src.contracts.secret import refuse_secrets
from src.contracts.terminal import is_terminal
from src.contracts.transition import StateTransition
from src.runtime.result_bound import BoundFields

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
    result_bound: "BoundFields | None" = None
    terminal_state: str | None = None
    pre: Mapping[str, Any] | None = None
    post: Mapping[str, Any] | None = None
    detail: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # FR-036 first, and over every field, because the credential question
        # has to be answered before any other refusal can pre-empt it: a span
        # with a Secret in `pre` and a misspelled `kind` should be reported as
        # the credential it is, not as the typo.
        _refuse_secrets_anywhere(self)

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

        # FR-058's third obligation. **On every `tool_call`, not only on the
        # ones where the bound bit** — a field written only on truncation cannot
        # distinguish a result that fitted from a bound that was never applied,
        # which is the vacuous-instrument shape this corpus keeps finding. The
        # sibling precedent is FR-038's own requirement that a decision and its
        # matched inputs are recorded for permits as well as denials.
        if self.kind == TOOL_CALL and self.result_bound is None:
            raise SpanError(
                "a tool_call span must carry FR-058's seven result-bound "
                "fields: that the bound was applied, the bound in force, the "
                "unit, whether a byte proxy stood in for it, the full size, "
                "the amount admitted, and the disposition. This is required on "
                "every tool_call and not only where the bound bit, because a "
                "bound recorded only where it bit is unfalsifiable in absence."
            )
        if self.kind != TOOL_CALL and self.result_bound is not None:
            raise SpanError(
                f"a {self.kind} span carries result-bound fields; FR-058 bounds "
                "what FR-004's capabilities return, which is called through a "
                "tool_call, and putting the fields elsewhere makes the check "
                "miss the span that needed them."
            )

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
        if self.result_bound is not None:
            record["result_bound"] = self.result_bound.to_record()
        if self.pre is not None:
            record["pre"] = dict(self.pre)
        if self.post is not None:
            record["post"] = dict(self.post)
        return record


def _refuse_secrets_anywhere(span: Span) -> None:
    """FR-036 over the whole span, derived from the type rather than a list.

    **Why this is not six calls to `_refuse_secrets`.** It was one call, on
    `detail`, under a test named as though it covered the type. Writing the
    other five out would fix today's gap and rebuild the mechanism that
    produced it: the seventh field would arrive, its author would not know
    there was a list to extend, and the guard would silently narrow again.

    Enumerating `dataclasses.fields(span)` means the guard's coverage is the
    type's shape. A field cannot be added without being scanned, because
    nobody has to remember anything for that to happen.

    **The walk itself moved to `src/contracts/secret.py` when T069 needed the
    same rule for the caller-visible event stream.** What stays here is which
    object is walked and what the refusal is called; the descent — mapping keys
    as well as values, sequences, and nested dataclasses — is one implementation
    for both channels, because two copies of a nesting rule are two chances for
    one of them to stop one hop short.
    """
    for f in fields(span):
        _refuse_secrets(getattr(span, f.name), f.name)


def _refuse_secrets(value: Any, path: str) -> None:
    """FR-036: a Secret must never reach a trace.

    `Secret` has no serializer, so it would render as a redaction marker rather
    than a credential — but a marker in a trace is a field somebody will later
    "fix" by unwrapping. Refusing it here means the credential never gets close.
    """
    refuse_secrets(value, path, raise_as=SpanError, destination="a trace")


class SpanWriter:
    """Allocates ordinals and persists spans. Owned by the runtime (T017)."""

    def __init__(self, repository: Repository) -> None:
        self.repo = repository
        self._lock = threading.Lock()
        self._next: dict[tuple[str, int], int] = {}
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
        }, unique=[("session_id", "turn", "ordinal")])

    def next_ordinal(self, session_id: str, turn: int) -> int:
        """The next free position in `turn`, seeded from the store.

        Seeded rather than started at zero, because a `SpanWriter` is
        constructed once per process and a session outlives one. FR-049's
        memory bound kills a session with no unwind, and the runtime that
        resumes it builds a new writer over the same store — a counter that
        began at zero would hand out positions the table already holds.
        """
        with self._lock:
            key = (session_id, turn)
            ordinal = self._next.get(key)
            if ordinal is None:
                ordinal = self._highest_written(session_id, turn) + 1
            self._next[key] = ordinal + 1
            return ordinal

    def _highest_written(self, session_id: str, turn: int) -> int:
        """The largest ordinal already at `(session_id, turn)`, or -1."""
        rows = self.repo.select(
            TABLE, where={"session_id": session_id, "turn": turn},
            order_by="ordinal", descending=True, limit=1)
        return rows[0]["ordinal"] if rows else -1

    def write(self, span: Span) -> None:
        """Persist one span. The store refuses a duplicate position.

        **The uniqueness check is the index and not a set held here.** A
        per-instance set is a property of this object: a second writer over the
        same repository, or a writer built after a crash, agrees with it about
        nothing. It also could not be unwound — a position was claimed before
        the insert and kept whatever the insert did, so a write that failed in
        the encoder spent a position permanently and refused the retry.
        """
        from src.contracts.canonical import dumps

        record = {
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
        }
        try:
            self.repo.insert(TABLE, record)
        except UniquenessError as exc:
            raise SpanError(
                f"a span already occupies position {span.position}. "
                "FR-038 requires positions sufficient to order a session "
                "totally, and two spans at one position is a tie."
            ) from exc

    def spans(self, session_id: str) -> list[dict[str, Any]]:
        rows = self.repo.select(
            TABLE, where={"session_id": session_id}, order_by="ordinal")
        return sorted(rows, key=lambda r: (r["turn"], r["ordinal"]))
