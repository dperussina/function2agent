"""T193 — SC-012 over a named population of failed-session traces.

For 100% of sessions in FAILED_SESSION_IDS ending in a failure terminal,
the failure is attributable from the stored span records alone, without
re-running the session, to:

1. the span on which it occurred — kind and position (session, turn, step)
2. that span's typed outcome and the session's named terminal state
3. where the failure was a denial, the rule_id that produced it

For 100% of spans in those sessions: artifact versions and per-span cost.

The population is the four failed sessions this file writes through
SpanWriter. It is not a claim about production traffic. An empty
population is vacuous and refused.

T194's mapping is pinned here too: struck node terms map onto turn and
step, or are recorded as having no v1 subject. Minting a node id, or
inventing a retry definition, is the defect.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from src.contracts import transition as tr
from src.contracts.repository import Repository
from src.contracts.terminal import COMPLETED, SPEND_CEILING, TURN_CEILING
from src.runtime import trace
from src.runtime.trace import (
    ArtifactVersions,
    Cost,
    DecisionFields,
    Span,
    SpanWriter,
)
from src.runtime.trace_node import (
    ARTIFACT_VERSIONS,
    ATTRIBUTION_IMPORTS_THE_LOOP,
    DENIAL_WITHOUT_RULE_ID_IS_ATTRIBUTABLE,
    EMPTY_POPULATION_IS_ONE_HUNDRED_PERCENT,
    INFER_FAILED_SPAN_FROM_ORDERING,
    MAPPED_ONTO,
    MINT_NODE_ID,
    NO_V1_SUBJECT,
    PER_SPAN_COST,
    RETRY_DEFINITION,
    RETRY_REPAIR_REGISTER,
    SESSION_TERMINAL,
    SPAN_STEP_FIELD,
    STEP,
    TURN,
    TYPED_OUTCOME,
    AttributionError,
    NoV1Subject,
    attribute_failure,
    mint_node_id,
    retry_versus_repair,
    score_failed_sessions,
    v1_subject,
)
from tests.contract.test_open_definitions import invented_definitions

REPO = Path(__file__).resolve().parents[2]
TRACE_NODE = REPO / "src" / "runtime" / "trace_node.py"

# SC-012 is scored over these four failed sessions, written through
# SpanWriter in this file. Not production traffic.
FAILED_SESSION_IDS: tuple[str, ...] = (
    "fixture-denial-fs",
    "fixture-denial-eg",
    "fixture-ceiling-turns",
    "fixture-ceiling-spend",
)
COMPLETED_SESSION_ID = "fixture-completed"

POPULATION = (
    "the four failed sessions in FAILED_SESSION_IDS, written through "
    "SpanWriter in tests/contract/test_attribution.py: two denials "
    "(filesystem, egress) and two ceiling terminals (turns, spend). "
    "Not production traffic."
)

VERSIONS = ArtifactVersions(
    tenant_id="t-1", deployment_id="d-1",
    by_kind={
        "served_operation_set": "sha256:" + "1" * 64,
        "egress_policy": "sha256:" + "2" * 64,
    },
)


def _cost(spend: float = 0.01, tokens: int = 100) -> Cost:
    return Cost(
        spend_usd=spend, tokens=tokens, wall_clock_seconds=0.5, turns=0,
        total_spend_usd=spend, total_tokens=tokens,
        total_wall_clock_seconds=0.5, total_turns=1,
    )


@pytest.fixture()
def writer(tmp_path: Path):
    repo = Repository(tmp_path / "trace.sqlite3", role="runtime",
                      tenant_id="t-1", deployment_id="d-1")
    yield SpanWriter(repo)
    repo.close()


def _emit(writer, session_id: str, turn: int, **kwargs) -> Span:
    span = Span(
        session_id=session_id, turn=turn,
        ordinal=writer.next_ordinal(session_id, turn),
        versions=VERSIONS, cost=_cost(),
        attempt_kind=kwargs.pop("attempt_kind", trace.ATTEMPT_FIRST),
        at=100.0,
        **kwargs,
    )
    writer.write(span)
    return span


def _model_call(writer: SpanWriter, session_id: str, turn: int = 0) -> Span:
    return _emit(
        writer, session_id, turn, kind=trace.MODEL_CALL,
        outcome=trace.OUTCOME_OK,
        detail={"model": "test-model", "provider": "test"},
    )


def write_population(writer: SpanWriter) -> None:
    """The named SC-012 population, plus a completed session that is not in it."""
    _model_call(writer, "fixture-denial-fs")
    _emit(
        writer, "fixture-denial-fs", 0,
        kind=trace.FILESYSTEM_DECISION, outcome=trace.OUTCOME_DENIED,
        terminal_state="terminated.unrecoverable_fault",
        decision=DecisionFields(
            rule_id="FS-001", resolved_tier="absent",
            matched={"syscall": "openat", "path": "/etc/shadow"},
        ),
    )

    _model_call(writer, "fixture-denial-eg")
    _emit(
        writer, "fixture-denial-eg", 0,
        kind=trace.EGRESS_DECISION, outcome=trace.OUTCOME_DENIED,
        terminal_state="terminated.unrecoverable_fault",
        decision=DecisionFields(
            rule_id="EG-DENY-001", resolved_tier="absent",
            matched={"method": "POST", "path": "/admin",
                     "served_operation": "adminWipe"},
        ),
    )

    _model_call(writer, "fixture-ceiling-turns")
    _emit(
        writer, "fixture-ceiling-turns", 1,
        kind=trace.STATE_TRANSITION, outcome=trace.OUTCOME_CEILING_REACHED,
        terminal_state=TURN_CEILING.name,
        transition=tr.StateTransition(
            session_id="fixture-ceiling-turns",
            from_state=tr.STATE_RUNNING, to_state=tr.STATE_TERMINATED,
            terminal_state=TURN_CEILING.name,
            deciding_rule=tr.ST_CEILING_REACHED.rule_id,
            predicate_inputs=(
                tr.PredicateInput("turns", "40", "40", True),
                tr.PredicateInput("spend_usd", "0.08", "5.00", False),
                tr.PredicateInput("tokens", "800", "200000", False),
                tr.PredicateInput("wall_clock_seconds", "4.0", "900.0", False),
            ),
            at=108.0,
        ),
    )

    _model_call(writer, "fixture-ceiling-spend")
    _emit(
        writer, "fixture-ceiling-spend", 1,
        kind=trace.STATE_TRANSITION, outcome=trace.OUTCOME_CEILING_REACHED,
        terminal_state=SPEND_CEILING.name,
        transition=tr.StateTransition(
            session_id="fixture-ceiling-spend",
            from_state=tr.STATE_RUNNING, to_state=tr.STATE_TERMINATED,
            terminal_state=SPEND_CEILING.name,
            deciding_rule=tr.ST_CEILING_REACHED.rule_id,
            predicate_inputs=(
                tr.PredicateInput("spend_usd", "5.00", "5.00", True),
                tr.PredicateInput("turns", "2", "40", False),
                tr.PredicateInput("tokens", "800", "200000", False),
                tr.PredicateInput("wall_clock_seconds", "4.0", "900.0", False),
            ),
            at=108.0,
        ),
    )

    _model_call(writer, COMPLETED_SESSION_ID)
    _emit(
        writer, COMPLETED_SESSION_ID, 0,
        kind=trace.STATE_TRANSITION, outcome=trace.OUTCOME_OK,
        terminal_state=COMPLETED.name,
        transition=tr.StateTransition(
            session_id=COMPLETED_SESSION_ID,
            from_state=tr.STATE_RUNNING, to_state=tr.STATE_TERMINATED,
            terminal_state=COMPLETED.name,
            deciding_rule=tr.ST_WORK_COMPLETED.rule_id, at=109.0,
        ),
    )


def payloads(writer: SpanWriter, session_id: str) -> list[dict[str, object]]:
    return [json.loads(row["payload"]) for row in writer.spans(session_id)]


def failed_sessions(writer: SpanWriter) -> list[list[dict[str, object]]]:
    write_population(writer)
    return [payloads(writer, session_id) for session_id in FAILED_SESSION_IDS]


# ---------------------------------------------------------------------------
# T193 — SC-012 over the named population.
# ---------------------------------------------------------------------------


def test_the_population_is_named_and_not_empty() -> None:
    assert FAILED_SESSION_IDS, "empty population is vacuous"
    assert "SpanWriter" in POPULATION
    assert "Not production traffic" in POPULATION
    assert COMPLETED_SESSION_ID not in FAILED_SESSION_IDS


def test_an_empty_population_is_vacuous() -> None:
    assert EMPTY_POPULATION_IS_ONE_HUNDRED_PERCENT is False
    with pytest.raises(AttributionError, match="vacuous"):
        score_failed_sessions([])


def test_every_failed_session_in_the_fixture_is_attributable_from_the_trace(
    writer: SpanWriter,
) -> None:
    sessions = failed_sessions(writer)
    assert len(sessions) == len(FAILED_SESSION_IDS)
    assert score_failed_sessions(sessions) == 1.0


def test_each_failed_session_names_kind_position_outcome_and_terminal(
    writer: SpanWriter,
) -> None:
    write_population(writer)
    expected = {
        "fixture-denial-fs": (
            trace.FILESYSTEM_DECISION, trace.OUTCOME_DENIED,
            "terminated.unrecoverable_fault", "FS-001",
        ),
        "fixture-denial-eg": (
            trace.EGRESS_DECISION, trace.OUTCOME_DENIED,
            "terminated.unrecoverable_fault", "EG-DENY-001",
        ),
        "fixture-ceiling-turns": (
            trace.STATE_TRANSITION, trace.OUTCOME_CEILING_REACHED,
            TURN_CEILING.name, None,
        ),
        "fixture-ceiling-spend": (
            trace.STATE_TRANSITION, trace.OUTCOME_CEILING_REACHED,
            SPEND_CEILING.name, None,
        ),
    }
    for session_id, (kind, outcome, terminal, rule_id) in expected.items():
        attr = attribute_failure(payloads(writer, session_id))
        assert attr.kind == kind
        assert attr.outcome == outcome
        assert attr.terminal_state == terminal
        assert attr.rule_id == rule_id
        assert attr.session_id == session_id
        assert attr.position == (session_id, attr.turn, attr.step)
        assert attr.artifact_versions
        assert attr.tenant_id == "t-1"
        assert attr.deployment_id == "d-1"


def test_a_completed_session_is_not_in_the_population(writer: SpanWriter) -> None:
    write_population(writer)
    records = payloads(writer, COMPLETED_SESSION_ID)
    assert records
    with pytest.raises(AttributionError, match="not a failure terminal"):
        attribute_failure(records)


def test_a_trace_missing_span_position_is_not_attributed_by_ordering(
    writer: SpanWriter,
) -> None:
    """SC-012: inferring the failed span from list order does not count."""
    assert INFER_FAILED_SPAN_FROM_ORDERING is False
    write_population(writer)
    records = payloads(writer, "fixture-denial-fs")
    stripped = []
    for record in records:
        copy = dict(record)
        copy.pop("turn", None)
        copy.pop("ordinal", None)
        stripped.append(copy)
    with pytest.raises(AttributionError, match="position|ordering"):
        attribute_failure(stripped)


def test_attribution_survives_reversing_the_record_list(
    writer: SpanWriter,
) -> None:
    """Position, not list order, names the failed span."""
    write_population(writer)
    records = payloads(writer, "fixture-denial-fs")
    forward = attribute_failure(records)
    reversed_attr = attribute_failure(list(reversed(records)))
    assert reversed_attr.position == forward.position
    assert reversed_attr.kind == forward.kind


def test_a_denial_without_rule_id_is_not_attributable(
    writer: SpanWriter,
) -> None:
    assert DENIAL_WITHOUT_RULE_ID_IS_ATTRIBUTABLE is False
    write_population(writer)
    records = payloads(writer, "fixture-denial-fs")
    stripped = []
    for record in records:
        copy = dict(record)
        if copy.get("outcome") == trace.OUTCOME_DENIED:
            raw_decision = copy.get("decision")
            decision = dict(raw_decision) if isinstance(raw_decision, dict) else {}
            decision.pop("rule_id", None)
            copy["decision"] = decision
        stripped.append(copy)
    with pytest.raises(AttributionError, match="rule identifier"):
        attribute_failure(stripped)


def test_a_span_missing_artifact_versions_does_not_count(
    writer: SpanWriter,
) -> None:
    write_population(writer)
    records = payloads(writer, "fixture-ceiling-turns")
    stripped = []
    for record in records:
        copy = dict(record)
        copy.pop("artifact_versions", None)
        stripped.append(copy)
    with pytest.raises(AttributionError, match="artifact versions"):
        score_failed_sessions([stripped])


def test_a_span_missing_per_span_cost_does_not_count(
    writer: SpanWriter,
) -> None:
    write_population(writer)
    records = payloads(writer, "fixture-ceiling-turns")
    stripped = []
    for record in records:
        copy = dict(record)
        copy.pop("cost", None)
        stripped.append(copy)
    with pytest.raises(AttributionError, match="per-span cost"):
        score_failed_sessions([stripped])


def test_attribution_does_not_re_run_the_session() -> None:
    assert ATTRIBUTION_IMPORTS_THE_LOOP is False
    tree = ast.parse(TRACE_NODE.read_text(), filename=str(TRACE_NODE))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    assert "src.runtime.loop" not in imported
    assert "src.runtime.events" not in imported
    assert "src.runtime.main" not in imported


def test_attribution_does_not_read_a_second_artifact(writer: SpanWriter) -> None:
    """The trace payload is enough. EventStream is a different channel."""
    write_population(writer)
    records = payloads(writer, "fixture-denial-eg")
    attr = attribute_failure(records)
    assert attr.rule_id == "EG-DENY-001"
    source = TRACE_NODE.read_text()
    assert "EventStream" not in source


# ---------------------------------------------------------------------------
# T194 — mapping, recorded absences, no invented node / retry.
# ---------------------------------------------------------------------------


def test_executed_node_maps_onto_turn_and_step() -> None:
    assert MAPPED_ONTO["executed node"] == (TURN, STEP)
    assert v1_subject("executed node") == (TURN, STEP)
    assert SPAN_STEP_FIELD == "ordinal"


def test_the_other_mapped_terms() -> None:
    assert v1_subject("versioned node identity") == (ARTIFACT_VERSIONS,)
    assert v1_subject("typed terminal") == (TYPED_OUTCOME, SESSION_TERMINAL)
    assert v1_subject("per-node cost") == (PER_SPAN_COST,)


def test_terms_with_no_v1_subject_are_recorded_not_invented() -> None:
    for term in (
        "node id", "routing decision", "predicate", "conditional edge", "graph",
    ):
        assert term in NO_V1_SUBJECT
        with pytest.raises(NoV1Subject, match="no v1 subject"):
            v1_subject(term)


def test_a_missing_node_identity_is_not_repaired_by_minting_one() -> None:
    assert MINT_NODE_ID is False
    with pytest.raises(NoV1Subject, match="no node id"):
        mint_node_id("fixture-denial-fs", 0, 1)


def test_retry_versus_repair_points_at_the_register_and_does_not_define() -> None:
    assert RETRY_DEFINITION is None
    assert RETRY_REPAIR_REGISTER == "docs/open-definitions.md"
    pointed = retry_versus_repair()
    assert RETRY_REPAIR_REGISTER in pointed
    assert invented_definitions(TRACE_NODE.read_text()) == []
    assert invented_definitions(pointed) == []


def test_the_module_is_not_a_second_span_writer() -> None:
    tree = ast.parse(TRACE_NODE.read_text(), filename=str(TRACE_NODE))
    names = {
        node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
    }
    assert "write" not in names
    assert "mint_node_id" in names
