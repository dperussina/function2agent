"""T039 — every span kind emitted on a full session, no decision span without a rule.

The session below is not a smoke test: it walks a whole run so that "every kind
is emitted" is asserted against something a real session would produce, and so
the total-ordering claim is tested over a trace with more than one turn.
"""

from __future__ import annotations

import pytest

from src.contracts import transition as tr
from src.contracts.repository import Repository
from src.contracts.secret import Secret
from src.runtime import trace
from src.runtime.trace import (
    ArtifactVersions,
    Cost,
    DecisionFields,
    Span,
    SpanError,
    SpanWriter,
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
def writer(tmp_path):
    repo = Repository(tmp_path / "trace.sqlite3", role="runtime",
                      tenant_id="t-1", deployment_id="d-1")
    yield SpanWriter(repo)
    repo.close()


def _full_session(writer: SpanWriter, session_id: str = "sess-1") -> list[Span]:
    """One session that emits all seven kinds across two turns."""
    spans: list[Span] = []

    def emit(turn: int, **kwargs) -> Span:
        span = Span(
            session_id=session_id, turn=turn,
            ordinal=writer.next_ordinal(session_id, turn),
            versions=VERSIONS, cost=_cost(),
            attempt_kind=kwargs.pop("attempt_kind", trace.ATTEMPT_FIRST),
            at=100.0 + len(spans),
            **kwargs,
        )
        writer.write(span)
        spans.append(span)
        return span

    emit(0, kind=trace.STATE_TRANSITION, outcome=trace.OUTCOME_OK,
         transition=tr.StateTransition(
             session_id=session_id, from_state=tr.STATE_STARTING,
             to_state=tr.STATE_RUNNING,
             deciding_rule=tr.ST_SESSION_STARTED.rule_id, at=100.0))

    emit(0, kind=trace.MODEL_CALL, outcome=trace.OUTCOME_OK,
         detail={"model": "test-model", "provider": "test"})

    emit(0, kind=trace.EGRESS_DECISION, outcome=trace.OUTCOME_OK,
         decision=DecisionFields(
             rule_id="EG-ALLOW-001", resolved_tier="read_only",
             matched={"method": "GET", "path": "/orders",
                      "served_operation": "listOrders"}))

    emit(0, kind=trace.TOOL_CALL, outcome=trace.OUTCOME_OK,
         detail={"tool": "listOrders"})

    emit(0, kind=trace.FILESYSTEM_DECISION, outcome=trace.OUTCOME_DENIED,
         decision=DecisionFields(
             rule_id="FS-001", resolved_tier="absent",
             matched={"syscall": "openat", "path": "/etc/shadow"}))

    emit(1, kind=trace.VERIFICATION, outcome=trace.OUTCOME_OK,
         pre={"reachability": "passed"},
         post={"return_type": "list", "state": "verified"},
         attempt_kind=trace.ATTEMPT_REPAIR)

    emit(1, kind=trace.DRIFT_CHECK, outcome=trace.OUTCOME_OK,
         detail={"source_clock": "abc123", "deployment_clock": "abc123"})

    emit(1, kind=trace.STATE_TRANSITION, outcome=trace.OUTCOME_CEILING_REACHED,
         terminal_state="terminated.turn_ceiling_reached",
         transition=tr.StateTransition(
             session_id=session_id, from_state=tr.STATE_RUNNING,
             to_state=tr.STATE_TERMINATED,
             terminal_state="terminated.turn_ceiling_reached",
             deciding_rule=tr.ST_CEILING_REACHED.rule_id,
             predicate_inputs=(
                 tr.PredicateInput("turns", "40", "40", True),
                 tr.PredicateInput("spend_usd", "0.08", "5.00", False),
                 tr.PredicateInput("tokens", "800", "200000", False),
                 tr.PredicateInput("wall_clock_seconds", "4.0", "900.0", False),
             ),
             at=108.0))
    return spans


def test_every_declared_kind_is_emitted_on_a_full_session(writer) -> None:
    _full_session(writer)
    emitted = {row["kind"] for row in writer.spans("sess-1")}
    assert emitted == set(trace.KINDS), (
        f"kinds never emitted: {set(trace.KINDS) - emitted}. A kind the "
        "session cannot produce is a kind nothing tests."
    )


def test_no_decision_span_is_missing_its_rule_id(writer) -> None:
    _full_session(writer)
    for row in writer.spans("sess-1"):
        if row["kind"] in trace.DECISION_KINDS:
            assert row["rule_id"], (
                f"a {row['kind']} span reached storage with no rule "
                "identifier (T037, FR-011)"
            )


def test_a_decision_span_cannot_be_built_without_a_rule(writer) -> None:
    for kind in sorted(trace.DECISION_KINDS):
        with pytest.raises(SpanError, match="rule identifier|decision fields"):
            Span(kind=kind, session_id="s", turn=0, ordinal=0,
                 outcome=trace.OUTCOME_DENIED, attempt_kind=trace.ATTEMPT_FIRST,
                 versions=VERSIONS, cost=_cost(), at=1.0)


def test_a_decision_span_cannot_omit_what_the_rule_matched_on() -> None:
    """FR-038: recorded for permits too, because a permit by the wrong rule is
    the case attribution has to find."""
    with pytest.raises(SpanError, match="matched on"):
        DecisionFields(rule_id="EG-ALLOW-001", resolved_tier="read_only", matched={})


def test_an_undeclared_kind_is_not_writable() -> None:
    with pytest.raises(SpanError, match="seven declared span kinds"):
        Span(kind="audit_note", session_id="s", turn=0, ordinal=0,
             outcome=trace.OUTCOME_OK, attempt_kind=trace.ATTEMPT_FIRST,
             versions=VERSIONS, cost=_cost(), at=1.0)


def test_a_generic_error_is_not_an_outcome() -> None:
    for bad in ("error", "failure", "exception", ""):
        with pytest.raises(SpanError, match="declared outcome"):
            Span(kind=trace.MODEL_CALL, session_id="s", turn=0, ordinal=0,
                 outcome=bad, attempt_kind=trace.ATTEMPT_FIRST,
                 versions=VERSIONS, cost=_cost(), at=1.0)


def test_the_session_orders_totally_without_a_clock(writer) -> None:
    """FR-038's first clause. Proved by ordering with the timestamps removed."""
    _full_session(writer)
    rows = writer.spans("sess-1")
    positions = [(r["turn"], r["ordinal"]) for r in rows]
    assert len(set(positions)) == len(positions), "two spans share a position"
    assert positions == sorted(positions)

    # And the order does not depend on `at`: reverse the timestamps and the
    # position order is unchanged.
    scrambled = sorted(rows, key=lambda r: -r["at"])
    assert sorted((r["turn"], r["ordinal"]) for r in scrambled) == positions


def test_two_spans_cannot_occupy_one_position(writer) -> None:
    span = Span(kind=trace.MODEL_CALL, session_id="s", turn=0, ordinal=0,
                outcome=trace.OUTCOME_OK, attempt_kind=trace.ATTEMPT_FIRST,
                versions=VERSIONS, cost=_cost(), at=1.0)
    writer.write(span)
    with pytest.raises(SpanError, match="already occupies position"):
        writer.write(span)


def test_a_state_transition_span_carries_its_predicate_inputs(writer) -> None:
    """Constitution Principle VI at v1.3.0, wider than FR-038."""
    _full_session(writer)
    import json

    terminal = [r for r in writer.spans("sess-1")
                if r["kind"] == trace.STATE_TRANSITION and r["terminal_state"]]
    assert len(terminal) == 1
    payload = json.loads(terminal[0]["payload"])
    inputs = payload["transition"]["predicate_inputs"]
    assert len(inputs) == 4, "not every ceiling consulted is on the record"
    assert sum(1 for i in inputs if i["matched"]) == 1
    assert payload["transition"]["deciding_rule"] == tr.ST_CEILING_REACHED.rule_id


def test_a_state_transition_span_cannot_omit_its_transition() -> None:
    with pytest.raises(SpanError, match="Principle VI"):
        Span(kind=trace.STATE_TRANSITION, session_id="s", turn=0, ordinal=0,
             outcome=trace.OUTCOME_OK, attempt_kind=trace.ATTEMPT_FIRST,
             versions=VERSIONS, cost=_cost(), at=1.0)


def test_every_span_carries_the_versions_in_force(writer) -> None:
    _full_session(writer)
    import json

    for row in writer.spans("sess-1"):
        payload = json.loads(row["payload"])
        assert payload["artifact_versions"], "a span carries no artifact versions"
        assert payload["tenant_id"] == "t-1"
        assert payload["deployment_id"] == "d-1"
        for address in payload["artifact_versions"].values():
            assert address.startswith("sha256:")


def test_a_span_with_no_versions_in_force_is_refused() -> None:
    with pytest.raises(SpanError, match="versions of the artifacts in force"):
        ArtifactVersions(tenant_id="t-1", deployment_id="d-1", by_kind={})


def test_a_version_that_is_a_label_not_a_content_address_is_refused() -> None:
    with pytest.raises(SpanError, match="content address"):
        ArtifactVersions(tenant_id="t", deployment_id="d",
                         by_kind={"egress_policy": "v2"})


def test_the_retry_repair_distinction_is_three_way(writer) -> None:
    """A boolean would make a first attempt and a repair both 'not a retry'."""
    assert trace.ATTEMPT_KINDS == {"first", "retry", "repair"}
    with pytest.raises(SpanError, match="attempt kind"):
        Span(kind=trace.MODEL_CALL, session_id="s", turn=0, ordinal=0,
             outcome=trace.OUTCOME_OK, attempt_kind="true",
             versions=VERSIONS, cost=_cost(), at=1.0)


def test_every_span_carries_the_running_ceiling_totals(writer) -> None:
    _full_session(writer)
    import json

    for row in writer.spans("sess-1"):
        totals = json.loads(row["payload"])["cost"]["totals"]
        assert set(totals) == {"spend_usd", "tokens", "wall_clock_seconds", "turns"}, (
            "FR-038 requires the running total against each of FR-005's four "
            f"ceilings; this span carries {sorted(totals)}"
        )


def test_a_verification_span_carries_pre_and_post() -> None:
    with pytest.raises(SpanError, match="precondition and postcondition"):
        Span(kind=trace.VERIFICATION, session_id="s", turn=0, ordinal=0,
             outcome=trace.OUTCOME_OK, attempt_kind=trace.ATTEMPT_FIRST,
             versions=VERSIONS, cost=_cost(), at=1.0, pre={"x": 1})


def test_a_terminal_state_outside_the_taxonomy_is_refused() -> None:
    with pytest.raises(SpanError, match="terminal taxonomy"):
        Span(kind=trace.MODEL_CALL, session_id="s", turn=0, ordinal=0,
             outcome=trace.OUTCOME_OK, attempt_kind=trace.ATTEMPT_FIRST,
             versions=VERSIONS, cost=_cost(), at=1.0,
             terminal_state="terminated.something_invented")


def test_a_secret_in_a_span_detail_is_refused() -> None:
    """FR-036 at the trace boundary, before the redaction scan.

    `Secret` has no serializer, so it would render as a marker — but a marker
    in a trace is a field somebody later "fixes" by unwrapping.
    """
    with pytest.raises(SpanError, match="Secret"):
        Span(kind=trace.MODEL_CALL, session_id="s", turn=0, ordinal=0,
             outcome=trace.OUTCOME_OK, attempt_kind=trace.ATTEMPT_FIRST,
             versions=VERSIONS, cost=_cost(), at=1.0,
             detail={"headers": {"authorization": Secret("sk-live-abc", name="k")}})


def test_the_span_table_is_the_runtimes_to_write(tmp_path) -> None:
    from src.contracts.ownership import OwnershipError

    repo = Repository(tmp_path / "t.sqlite3", role="runtime",
                      tenant_id="t-1", deployment_id="d-1")
    SpanWriter(repo)
    repo.close()

    proxy = Repository(tmp_path / "t.sqlite3", role="proxy",
                       tenant_id="t-1", deployment_id="d-1")
    try:
        with pytest.raises(OwnershipError):
            SpanWriter(proxy)
    finally:
        proxy.close()
