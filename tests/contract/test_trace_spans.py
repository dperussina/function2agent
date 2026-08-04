"""T039 — every span kind emitted on a full session, no decision span without a rule.

The session below is not a smoke test: it walks a whole run so that "every kind
is emitted" is asserted against something a real session would produce, and so
the total-ordering claim is tested over a trace with more than one turn.
"""

from __future__ import annotations

import dataclasses

import pytest

from src.contracts import transition as tr
from src.contracts.repository import Repository
from src.contracts.secret import Secret
from src.runtime import trace
from src.runtime.result_bound import (
    DISPOSITION_RETAINED,
    UNIT_TOKENS,
    BoundFields,
)
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

    # FR-058's seven fields are required on every `tool_call`, so a full session
    # cannot be emitted without them. This one fits inside the bound, which is
    # the case an implementation writing the fields only at the bound gets wrong.
    emit(0, kind=trace.TOOL_CALL, outcome=trace.OUTCOME_OK,
         detail={"tool": "listOrders"},
         result_bound=BoundFields(
             bound_applied=True, bound_in_force=2_000, unit=UNIT_TOKENS,
             byte_proxy=False, full_size=48, admitted=48,
             disposition=DISPOSITION_RETAINED, tokenizer_name="test-tok"))

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


def _span(session_id: str = "s", turn: int = 0, ordinal: int = 0, **kwargs) -> Span:
    return Span(kind=trace.MODEL_CALL, session_id=session_id, turn=turn,
                ordinal=ordinal, outcome=trace.OUTCOME_OK,
                attempt_kind=trace.ATTEMPT_FIRST, versions=VERSIONS,
                cost=_cost(), at=1.0, **kwargs)


def test_two_spans_cannot_occupy_one_position(writer) -> None:
    span = _span()
    writer.write(span)
    with pytest.raises(SpanError, match="already occupies position"):
        writer.write(span)


def test_two_writers_over_one_repository_cannot_share_a_position(tmp_path) -> None:
    """Uniqueness has to live in the store, not in one writer's memory.

    A per-instance Python set is a property of one object in one process.
    FR-038 asks for "position sufficient to order every span in a session
    totally", which is a property of the *data*, and two `SpanWriter`s over one
    `Repository` — a construction this suite performs in
    `test_a_trace_scan_over_a_full_session_is_clean` — each hold their own set.
    """
    repo = Repository(tmp_path / "trace.sqlite3", role="runtime",
                      tenant_id="t-1", deployment_id="d-1")
    try:
        first, second = SpanWriter(repo), SpanWriter(repo)
        first.write(_span())
        with pytest.raises(SpanError, match="already occupies position"):
            second.write(_span())
        positions = [(r["turn"], r["ordinal"]) for r in first.spans("s")]
        assert positions == [(0, 0)], (
            f"two spans landed at one position: {positions}. The total order "
            "FR-038 requires is not a property of this table."
        )
    finally:
        repo.close()


def test_a_resumed_writer_does_not_reissue_an_ordinal(tmp_path) -> None:
    """The crash the budget journal three files away exists to survive.

    A session resumed after a `memory.oom.group` kill constructs a new
    `SpanWriter` over the same store. An ordinal counter that starts at zero
    hands out a position that is already occupied.
    """
    repo = Repository(tmp_path / "trace.sqlite3", role="runtime",
                      tenant_id="t-1", deployment_id="d-1")
    try:
        before = SpanWriter(repo)
        for _ in range(3):
            before.write(_span(ordinal=before.next_ordinal("s", 0)))

        resumed = SpanWriter(repo)
        assert resumed.next_ordinal("s", 0) == 3, (
            "a resumed writer re-issued an ordinal the store already holds"
        )
        resumed.write(_span(ordinal=3))
        assert [(r["turn"], r["ordinal"]) for r in resumed.spans("s")] == [
            (0, 0), (0, 1), (0, 2), (0, 3)]
    finally:
        repo.close()


def test_a_refused_insert_does_not_burn_the_position(writer) -> None:
    """A position recorded before the insert, and never unwound, is spent.

    The write below fails in the canonical encoder, after the position was
    claimed and before any row landed. A legitimate retry at the same position
    is then rejected for a collision with a span that does not exist.
    """
    from src.contracts.canonical import NonCanonicalValue

    with pytest.raises(NonCanonicalValue):
        writer.write(_span(detail={"latency": float("nan")}))
    assert writer.spans("s") == [], "the failed write left a row behind"

    writer.write(_span(detail={"latency": 0.5}))
    assert [(r["turn"], r["ordinal"]) for r in writer.spans("s")] == [(0, 0)]


def test_one_position_per_tenant_not_per_table(tmp_path) -> None:
    """Uniqueness is scoped the way every other query on this table is.

    Every read goes through the repository's tenant and deployment predicate,
    so an index that ignored the scope columns would refuse a second tenant's
    first span for colliding with a row that tenant cannot see.
    """
    path = tmp_path / "trace.sqlite3"
    first = Repository(path, role="runtime", tenant_id="t-1", deployment_id="d-1")
    second = Repository(path, role="runtime", tenant_id="t-2", deployment_id="d-1")
    try:
        SpanWriter(first).write(_span())
        SpanWriter(second).write(_span())
        assert len(SpanWriter(first).spans("s")) == 1
        assert len(SpanWriter(second).spans("s")) == 1
    finally:
        first.close()
        second.close()


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


@pytest.mark.parametrize("field_name", [f.name for f in dataclasses.fields(Span)])
def test_no_field_of_a_span_may_hold_a_secret(field_name: str) -> None:
    """FR-036 over the whole type, and the parametrization is the point.

    The predecessor of this test scanned `detail` three times and the other
    five fields not at all, while being named as though it covered the type.
    The list of cases here is `dataclasses.fields(Span)`, so a seventh field
    is a seventh case the day it is declared and there is no list to forget
    to update. That is the only version of this test that cannot quietly stop
    covering the type.
    """
    kwargs = dict(kind=trace.MODEL_CALL, session_id="s", turn=0, ordinal=0,
                  outcome=trace.OUTCOME_OK, attempt_kind=trace.ATTEMPT_FIRST,
                  versions=VERSIONS, cost=_cost(), at=1.0)
    kwargs[field_name] = Secret("sk-live-abc", name="k")
    with pytest.raises(SpanError, match="Secret"):
        Span(**kwargs)


def test_a_secret_nested_in_any_carrier_field_is_refused() -> None:
    """The five fields the `detail`-only guard walked straight past.

    Each of these is a real place a credential arrives: a matched request
    header on an egress decision, a predicate input on a transition, a
    verification result that echoed what it checked.
    """
    s = Secret("sk-live-abc", name="k")
    base = dict(session_id="s", turn=0, ordinal=0, outcome=trace.OUTCOME_OK,
                attempt_kind=trace.ATTEMPT_FIRST, versions=VERSIONS,
                cost=_cost(), at=1.0)

    with pytest.raises(SpanError, match="decision.*Secret|Secret"):
        Span(kind=trace.EGRESS_DECISION, decision=DecisionFields(
            rule_id="EG-001", resolved_tier="read_only",
            matched={"authorization": s}), **base)

    with pytest.raises(SpanError, match="Secret"):
        Span(kind=trace.STATE_TRANSITION, transition=tr.StateTransition(
            session_id="s", from_state=tr.STATE_RUNNING,
            to_state=tr.STATE_TERMINATED,
            terminal_state="terminated.capability_lapsed",
            deciding_rule=tr.ST_CAPABILITY_LAPSED.rule_id, at=1.0,
            predicate_inputs=(tr.PredicateInput(
                name="lease_token", observed=s, declared=None,
                matched=True),)), **base)

    with pytest.raises(SpanError, match="Secret"):
        Span(kind=trace.VERIFICATION, pre={"token": s},
             post={"state": "verified"}, **base)

    with pytest.raises(SpanError, match="Secret"):
        Span(kind=trace.VERIFICATION, pre={"reachability": "passed"},
             post={"token": s}, **base)

    with pytest.raises(SpanError, match="Secret"):
        Span(kind=trace.MODEL_CALL,
             versions=ArtifactVersions(tenant_id="t-1", deployment_id="d-1",
                                       by_kind={"egress_policy": s}),
             **{k: v for k, v in base.items() if k != "versions"})


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
