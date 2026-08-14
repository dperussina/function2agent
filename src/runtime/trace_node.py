"""T194 — map FR-038's per-node terms onto v1's nearest subject.

Loose-requirements item 1: the struck text asked for one trace record per
executed **node**, carrying a versioned node identity, a routing decision
and its predicate, and per-node cost. v1 emits no graph, no nodes, no
routing and no predicates — Principle II's deviation record is accepted
on exactly that ground. This module is the mapping, not a second span
writer.

**Nearest v1 subjects for "node": the turn, and the step.** A step is
where within that turn; the span field that holds it is `ordinal`. The
record written is one span of FR-038's closed kinds. Versioned identity
is the artifact versions in force plus tenant and deployment
(FR-035 / FR-054), not a node id.

Terms with no v1 subject are recorded in `NO_V1_SUBJECT` rather than
invented. A function that repairs a missing node identity by minting
one is the defect this file exists to catch.

Retry versus repair is not defined here. That pair is T195's, in
docs/open-definitions.md. This file points at that register and does
not supply a definition.

T193 reads stored span records through `attribute_failure`. Attribution
is a walk of the trace, not a second run of the session.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from src.contracts.terminal import COMPLETED, is_terminal
from src.runtime.trace import OUTCOME_DENIED

# ---------------------------------------------------------------------------
# Planted flags. Each one is a removal-proof needle. Flipping it is the
# defect the named T193 / T194 test exists to catch.
# ---------------------------------------------------------------------------

#: Drop span position and pick the last record in list order.
INFER_FAILED_SPAN_FROM_ORDERING = False
#: A denial with no rule_id still counts as attributed.
DENIAL_WITHOUT_RULE_ID_IS_ATTRIBUTABLE = False
#: Score 100% over no sessions. Vacuous; SC-012 forbids it.
EMPTY_POPULATION_IS_ONE_HUNDRED_PERCENT = False
#: Repair a missing node identity by minting one. v1 has no node id.
MINT_NODE_ID = False
#: Invented retry/repair text. None: T195's register owns the pair.
RETRY_DEFINITION = None
#: Import the loop so attribution re-runs the session.
ATTRIBUTION_IMPORTS_THE_LOOP = False


TURN = "turn"
STEP = "step"
SPAN_STEP_FIELD = "ordinal"

ARTIFACT_VERSIONS = "artifact versions in force plus tenant and deployment"
TYPED_OUTCOME = "span typed outcome"
SESSION_TERMINAL = "session terminal on the ending span"
PER_SPAN_COST = "per-span cost"

# Struck "node" terms that have a v1 subject. The substitute is turn and
# step for the unit; the other rows are the FR-038 rewrite's own mappings
# onto the span, not a graph.
MAPPED_ONTO: Mapping[str, tuple[str, ...]] = {
    "executed node": (TURN, STEP),
    "versioned node identity": (ARTIFACT_VERSIONS,),
    "typed terminal": (TYPED_OUTCOME, SESSION_TERMINAL),
    "per-node cost": (PER_SPAN_COST,),
}

# Struck terms that still have no v1 subject. Recording the absence is
# the close. Inventing a node id, a routing decision, a predicate, a
# conditional edge, or a graph is the defect.
NO_V1_SUBJECT: frozenset[str] = frozenset({
    "node id",
    "routing decision",
    "predicate",
    "conditional edge",
    "graph",
})

RETRY_REPAIR_REGISTER = "docs/open-definitions.md"

_PER_SPAN_COST_FIELDS: frozenset[str] = frozenset({
    "spend_usd", "tokens", "wall_clock_seconds", "turns",
})


class NoV1Subject(ValueError):
    """A FR-038 term v1 has no subject for. Inventing one is the defect."""


class AttributionError(ValueError):
    """A failed session that cannot be attributed from the trace alone."""


@dataclass(frozen=True)
class Attribution:
    """SC-012's attribution, read off the stored span record."""

    session_id: str
    kind: str
    turn: int
    step: int
    outcome: str
    terminal_state: str
    rule_id: str | None
    tenant_id: str
    deployment_id: str
    artifact_versions: Mapping[str, str]

    @property
    def position(self) -> tuple[str, int, int]:
        return (self.session_id, self.turn, self.step)


def v1_subject(term: str) -> tuple[str, ...]:
    """The v1 subject for a struck FR-038 term, or a recorded absence."""
    if term in NO_V1_SUBJECT:
        raise NoV1Subject(
            f"{term!r} has no v1 subject. v1 emits no graph, no nodes, "
            "no routing and no predicates; recording that is the close, "
            "not inventing a substitute."
        )
    mapped = MAPPED_ONTO.get(term)
    if mapped is None:
        raise NoV1Subject(
            f"{term!r} is not mapped onto a v1 subject and is not in "
            "the recorded-absent set"
        )
    return mapped


def mint_node_id(session_id: str, turn: int, step: int) -> str:
    """Invent a node identity. v1 has none; the live path raises.

    The planted path returns a minted id so the test that forbids this
    can fail when the flag flips.
    """
    if MINT_NODE_ID:
        return f"node:{session_id}:{turn}:{step}"
    raise NoV1Subject(
        "v1 has no node id. Minting one invents a graph v1 does not emit. "
        "Versioned identity is artifact versions plus tenant and deployment."
    )


def retry_versus_repair() -> str:
    """Point at T195's register. Do not define either term."""
    if RETRY_DEFINITION is not None:
        return str(RETRY_DEFINITION)
    return f"undefined; see {RETRY_REPAIR_REGISTER}"


def attribute_failure(records: Sequence[Mapping[str, object]]) -> Attribution:
    """Attribute a failed session from stored span records alone.

    Does not re-run the session. Does not read a second artifact. A
    human must not infer which span failed from list order.
    """
    if ATTRIBUTION_IMPORTS_THE_LOOP:
        raise AttributionError(
            "attribution is planted to re-run the session; SC-012 requires "
            "the trace alone"
        )

    if not records:
        raise AttributionError(
            "a session with no spans cannot be attributed from the trace"
        )

    failed = _failed_span(records)
    _require_versions_and_cost((failed,))
    position = _position(failed)
    terminal = failed.get("terminal_state")
    if not isinstance(terminal, str) or not is_terminal(terminal):
        raise AttributionError(
            "the failed span must carry the session's named terminal state "
            "(FR-006) on the record itself"
        )
    if terminal == COMPLETED.name:
        raise AttributionError(
            f"{terminal} is not a failure terminal; SC-012 scores sessions "
            "that ended in a failure"
        )

    outcome = failed.get("outcome")
    if not isinstance(outcome, str) or not outcome:
        raise AttributionError("the failed span carries no typed outcome")

    kind = failed.get("kind")
    if not isinstance(kind, str) or not kind:
        raise AttributionError("the failed span carries no kind")

    rule_id = _rule_id(failed)
    if outcome == OUTCOME_DENIED and not rule_id:
        if not DENIAL_WITHOUT_RULE_ID_IS_ATTRIBUTABLE:
            raise AttributionError(
                "a denial is not attributable from the trace without the "
                "rule identifier that produced it (FR-011, SC-012)"
            )

    versions = failed.get("artifact_versions")
    tenant = failed.get("tenant_id")
    deployment = failed.get("deployment_id")
    if not isinstance(versions, Mapping) or not versions:
        raise AttributionError("the failed span carries no artifact versions")
    if not isinstance(tenant, str) or not tenant:
        raise AttributionError("the failed span carries no tenant identity")
    if not isinstance(deployment, str) or not deployment:
        raise AttributionError("the failed span carries no deployment identity")

    return Attribution(
        session_id=position[0],
        kind=kind,
        turn=position[1],
        step=position[2],
        outcome=outcome,
        terminal_state=terminal,
        rule_id=rule_id,
        tenant_id=tenant,
        deployment_id=deployment,
        artifact_versions=dict(versions),
    )


def score_failed_sessions(
    sessions: Sequence[Sequence[Mapping[str, object]]],
) -> float:
    """SC-012 over a named population of failed-session traces.

    Empty is vacuous and refused. 100% means every session in `sessions`
    attributes from its stored records, and every span carries artifact
    versions and per-span cost.
    """
    if not sessions:
        if EMPTY_POPULATION_IS_ONE_HUNDRED_PERCENT:
            return 1.0
        raise AttributionError(
            "empty population is vacuous; SC-012 is not scored over nothing"
        )
    hits = 0
    for records in sessions:
        require_every_span_carries_versions_and_cost(records)
        attribute_failure(records)
        hits += 1
    return hits / len(sessions)


def require_every_span_carries_versions_and_cost(
    records: Sequence[Mapping[str, object]],
) -> None:
    """SC-012's second figure: 100% of spans, not only the failing one."""
    if not records:
        raise AttributionError("a session with no spans has no per-span cost")
    _require_versions_and_cost(records)


def _failed_span(
    records: Sequence[Mapping[str, object]],
) -> Mapping[str, object]:
    if INFER_FAILED_SPAN_FROM_ORDERING:
        return records[-1]
    named = [row for row in records if row.get("terminal_state")]
    if len(named) != 1:
        raise AttributionError(
            "which span failed is not on the trace: "
            f"{len(named)} spans carry a terminal_state. Inferring the "
            "failed span from list order does not count toward SC-012."
        )
    return named[0]


def _position(record: Mapping[str, object]) -> tuple[str, int, int]:
    if INFER_FAILED_SPAN_FROM_ORDERING:
        session = record.get("session_id")
        if not isinstance(session, str) or not session:
            session = ""
        turn = record.get("turn")
        step = record.get(SPAN_STEP_FIELD)
        return (
            session if isinstance(session, str) else "",
            turn if isinstance(turn, int) else 0,
            step if isinstance(step, int) else 0,
        )
    session = record.get("session_id")
    turn = record.get("turn")
    step = record.get(SPAN_STEP_FIELD)
    if not isinstance(session, str) or not session:
        raise AttributionError(
            "the failed span carries no session_id; a human would have to "
            "infer which session this is"
        )
    if not isinstance(turn, int) or not isinstance(step, int):
        raise AttributionError(
            "the failed span carries no position (turn and step). A human "
            "would have to infer which span failed from ordering, which "
            "does not count toward SC-012."
        )
    if turn < 0 or step < 0:
        raise AttributionError("turn and step are positions, not counters")
    return (session, turn, step)


def _rule_id(record: Mapping[str, object]) -> str | None:
    decision = record.get("decision")
    if isinstance(decision, Mapping):
        value = decision.get("rule_id")
        if isinstance(value, str) and value:
            return value
    return None


def _require_versions_and_cost(
    records: Sequence[Mapping[str, object]],
) -> None:
    for record in records:
        versions = record.get("artifact_versions")
        if not isinstance(versions, Mapping) or not versions:
            raise AttributionError(
                "a span is missing artifact versions in force (SC-012)"
            )
        tenant = record.get("tenant_id")
        deployment = record.get("deployment_id")
        if not isinstance(tenant, str) or not tenant:
            raise AttributionError("a span is missing tenant identity (FR-035)")
        if not isinstance(deployment, str) or not deployment:
            raise AttributionError(
                "a span is missing deployment identity (FR-035)"
            )
        cost = record.get("cost")
        if not isinstance(cost, Mapping):
            raise AttributionError("a span is missing per-span cost (SC-012)")
        missing = _PER_SPAN_COST_FIELDS - set(cost)
        if missing:
            raise AttributionError(
                f"a span's cost is missing {sorted(missing)} (SC-012)"
            )
