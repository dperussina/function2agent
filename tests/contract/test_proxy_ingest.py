"""T093 — the enforcement point's decision log ingested into the trace stream.

The mechanism under test is `src/runtime/proxy_ingest.py`. Three properties
carry the task and each is scored twice where a single reading could be free:

| Property | Structural arm | Behavioural arm |
|---|---|---|
| the runtime never writes the proxy's store | the connection is opened `mode=ro` | a write through it is refused by SQLite, and the file is byte-identical after a full ingest |
| nothing is re-tagged | the module holds no rule-identifier literal | a *deliberately wrong* requirement on a *registered* rule travels through unchanged |
| no new span kind (FR-038) | `egress_decision` is already one of the seven | the ingested spans read back under that kind |

**The fixture's schema is derived, not transcribed.** `_go_decision_schema()`
lifts the `CREATE TABLE` out of `src/proxy/decisionlog.go`'s own
`decisionSchema` constant, so a column renamed on the Go side changes this
fixture rather than silently diverging from it. That catches a rename but not a
divergence between the schema constant and what `Write` actually stores, so one
further arm runs the **real Go writer** (`TestDecisionLogExportForRuntimeIngest`
in `src/proxy/decisionlog_export_test.go`) and ingests the database it produced.
That arm skips without a Go toolchain; the derived-schema arms do not.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from src.contracts.repository import Repository
from src.runtime import proxy_ingest, trace
from src.runtime.proxy_ingest import (
    COLUMNS,
    DISPOSITION_OUTCOME,
    PHYSICAL_TABLE,
    DecisionRow,
    IngestResult,
    ProxyDecisionReader,
    ProxyIngestError,
    ingest,
    outcome_of,
    span_for,
    unattributed,
    watermark,
)
from src.runtime.trace import ArtifactVersions, Cost, SpanWriter

REPO = Path(__file__).resolve().parents[2]
GO_MODULE = REPO / "src" / "proxy"
DECISIONLOG_GO = GO_MODULE / "decisionlog.go"

VERSIONS = ArtifactVersions(
    tenant_id="t-1", deployment_id="d-1",
    by_kind={"egress_policy": "sha256:" + "2" * 64})
COST = Cost(0.0, 0, 0.0, 0, 0.0, 0, 0.0, 1)

#: A requirement label the Go registry never produces. Planted on a *registered*
#: rule id, so a module that re-derived the requirement from the rule would
#: overwrite it with `FR-015` and this value would vanish. That is the whole
#: point: the assertion fails on re-tagging and on nothing else.
PLANTED_REQUIREMENT = "FR-000-PLANTED-BY-T093-TEST"
PLANTED_REASON = "planted_reason_not_in_the_registry"


# ---------------------------------------------------------------------------
# The fixture's schema, derived from the Go writer's own constant.
# ---------------------------------------------------------------------------


def _go_decision_schema() -> str:
    source = DECISIONLOG_GO.read_text()
    match = re.search(r"const decisionSchema = `(.*?)`", source, re.DOTALL)
    assert match, (
        "no `decisionSchema` constant in src/proxy/decisionlog.go. This "
        "fixture derives its schema from the Go writer rather than "
        "transcribing it, so a constant that has moved or been renamed is a "
        "hard failure and not a fixture that quietly falls back to a copy."
    )
    return match.group(1)


def _decision_db(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.executescript(_go_decision_schema())
    return conn


def _insert(conn: sqlite3.Connection, **overrides: object) -> None:
    row: dict[str, object] = {
        "ts": 1000.5,
        "disposition": "deny",
        "rule_id": "EG-METH-001",
        "reason": "method_not_allowed",
        "requirement": "FR-015",
        "method": "POST",
        "path": "/orders/O-1/cancel",
        "resolved_tier": "unresolved",
        "session_id": "sess-1",
        "policy_version": "sha256:" + "a" * 64,
        "absolute_https_denied": 0,
        "credential_fpr": "",
        "detail": "",
    }
    row.update(overrides)
    names = ", ".join(row)
    marks = ", ".join("?" for _ in row)
    conn.execute(
        f"INSERT INTO {PHYSICAL_TABLE} ({names}) VALUES ({marks})",
        tuple(row.values()),
    )
    conn.commit()


@pytest.fixture()
def proxy_db(tmp_path) -> Path:
    path = tmp_path / "decisions.sqlite3"
    conn = _decision_db(path)
    conn.close()
    return path


@pytest.fixture()
def writer(tmp_path):
    repo = Repository(tmp_path / "trace.sqlite3", role="runtime",
                      tenant_id="t-1", deployment_id="d-1")
    yield SpanWriter(repo)
    repo.close()


def _ingest(path: Path, writer: SpanWriter, *, session: str = "sess-1",
            turn: int = 0) -> IngestResult:
    with ProxyDecisionReader(path) as reader:
        return ingest(reader, writer, session_id=session, turn=turn,
                      versions=VERSIONS, cost=COST)


def _details(writer: SpanWriter, session: str = "sess-1") -> list[dict]:
    out = []
    for stored in writer.spans(session):
        payload = json.loads(stored["payload"])
        if payload["kind"] == trace.EGRESS_DECISION:
            out.append(payload)
    return out


# ---------------------------------------------------------------------------
# The derivation itself. Without these the fixture could be silently empty.
# ---------------------------------------------------------------------------


def test_the_derived_schema_is_the_go_writers_and_is_not_empty() -> None:
    ddl = _go_decision_schema()
    assert PHYSICAL_TABLE in ddl
    assert ddl.count("CREATE TABLE") == 1, (
        "the constant declares more than one table; the fixture would build "
        "an ambiguous store"
    )


def test_the_modules_column_list_matches_the_go_schema_exactly(tmp_path) -> None:
    """The vacuity floor for every arm below.

    If `COLUMNS` drifted from the Go schema the reads would fail loudly, but if
    the *fixture* drifted with it they would agree with each other and disagree
    with production. Comparing both against the parsed DDL closes that.
    """
    conn = _decision_db(tmp_path / "schema.sqlite3")
    got = tuple(r[1] for r in conn.execute(f"PRAGMA table_info({PHYSICAL_TABLE})"))
    conn.close()
    assert got, "the derived schema created no columns"
    assert set(COLUMNS) == set(got), (
        f"proxy_ingest.COLUMNS is {sorted(COLUMNS)}; the Go writer's table is "
        f"{sorted(got)}. These are one schema across a language boundary."
    )
    assert len(COLUMNS) == len(set(COLUMNS)) == len(got)


def test_a_renamed_column_breaks_the_ingest_rather_than_being_skipped(tmp_path) -> None:
    """The control on the derivation: it is load-bearing, not decorative."""
    path = tmp_path / "renamed.sqlite3"
    conn = sqlite3.connect(path)
    conn.executescript(_go_decision_schema().replace("requirement ", "obligation "))
    conn.commit()
    conn.close()
    with ProxyDecisionReader(path) as reader:
        with pytest.raises(sqlite3.OperationalError, match="requirement"):
            reader.rows_after("sess-1", 0)


# ---------------------------------------------------------------------------
# Ownership direction — the runtime reads and never writes.
# ---------------------------------------------------------------------------


def test_a_write_through_the_ingest_connection_is_refused(proxy_db) -> None:
    """`mode=ro`, asserted at the engine rather than by convention.

    The message is matched on `readonly`, which only a read-only connection
    produces — a module that opened the database read-write and merely declined
    to write would fail this, which is the case the test exists for.
    """
    with ProxyDecisionReader(proxy_db) as reader:
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            reader._conn.execute(
                f"INSERT INTO {PHYSICAL_TABLE} (ts, disposition, rule_id, reason, "
                "requirement, method, path, resolved_tier, session_id, "
                "policy_version, absolute_https_denied, credential_fpr, detail) "
                "VALUES (1,'deny','EG-METH-001','r','FR-015','POST','/x',"
                "'unresolved','s','v',0,'','')"
            )


def test_the_proxy_database_is_byte_identical_after_a_full_ingest(
    proxy_db, writer
) -> None:
    conn = _decision_db(proxy_db)
    _insert(conn, disposition="allow", rule_id="EG-ALLOW-000", reason="allowed",
            requirement="FR-011", method="GET", path="/orders/O-1")
    _insert(conn)
    conn.close()

    before = hashlib.sha256(proxy_db.read_bytes()).hexdigest()
    sidecars_before = sorted(p.name for p in proxy_db.parent.iterdir())
    result = _ingest(proxy_db, writer)
    assert result.ingested == 2, "the ingest moved nothing, so the digest is free"
    after = hashlib.sha256(proxy_db.read_bytes()).hexdigest()

    assert before == after, "the ingest modified the enforcement point's database"
    assert sorted(p.name for p in proxy_db.parent.iterdir()) == sidecars_before, (
        "the ingest left a journal or WAL sidecar beside the proxy's database"
    )


def test_the_reader_refuses_a_table_the_ownership_map_does_not_let_it_read(
    monkeypatch, proxy_db
) -> None:
    """The declared authority is checked, not assumed.

    `require_read` is called with the ownership map's own row name. Pointing it
    at a table the runtime is not a declared reader of must refuse, so the call
    is doing work rather than naming a row that happens to permit everything.
    """
    from src.contracts.ownership import OwnershipError

    monkeypatch.setattr(proxy_ingest, "OWNED_TABLE", "judge_verdict")
    with pytest.raises(OwnershipError, match="judge_verdict"):
        ProxyDecisionReader(proxy_db)


def test_an_absent_decision_database_is_not_reported_as_an_empty_log(tmp_path) -> None:
    with pytest.raises(ProxyIngestError, match="no decision database"):
        ProxyDecisionReader(tmp_path / "never-created.sqlite3")


# ---------------------------------------------------------------------------
# No re-tagging. The structural arm and the behavioural arm.
# ---------------------------------------------------------------------------


def test_the_ingest_module_holds_no_rule_identifier_literal() -> None:
    """Structural: a second registry on the reading side would need one.

    `src/proxy/rules.go` stamps the requirement into the decision log *and*
    into the client-visible error body, so a label that disagrees here
    disagrees with what an operator was shown. A map from rule to reason or to
    requirement on this side cannot be written without naming rule ids.
    """
    source = Path(proxy_ingest.__file__).read_text()
    found = re.findall(r"\bEG-[A-Z]+-\d{3}\b", source)
    assert not found, (
        f"src/runtime/proxy_ingest.py names rule identifiers {sorted(set(found))}. "
        "The rule registry is src/proxy/rules.go's; a copy here is a second "
        "opinion on a label the operator reads off a denial."
    )


def test_a_wrong_requirement_on_a_registered_rule_travels_verbatim(
    proxy_db, writer
) -> None:
    """Behavioural: the arm a structural scan cannot cover.

    A re-tagging module keyed on the *reason* rather than on the rule id would
    hold no rule literal and pass the scan above. Here the rule id is one the
    registry knows and the requirement is one it never emits, so any recompute
    on this side replaces the planted value.
    """
    conn = _decision_db(proxy_db)
    _insert(conn, rule_id="EG-METH-001", reason=PLANTED_REASON,
            requirement=PLANTED_REQUIREMENT)
    conn.close()

    assert _ingest(proxy_db, writer).ingested == 1
    detail = _details(writer)[0]["detail"]
    assert detail["requirement"] == PLANTED_REQUIREMENT
    assert detail["reason"] == PLANTED_REASON


@pytest.mark.parametrize("missing", ["rule_id", "reason", "requirement"])
def test_a_row_missing_a_label_is_refused_rather_than_completed(
    tmp_path, writer, missing
) -> None:
    path = tmp_path / f"missing-{missing}.sqlite3"
    conn = sqlite3.connect(path)
    # The Go schema's CHECK forbids an empty rule_id, which is the writer's
    # guarantee. The reading side must not depend on it: this fixture drops the
    # constraint precisely so the runtime's own refusal is what is measured.
    conn.executescript(_go_decision_schema().replace(
        "CHECK (length(rule_id) > 0)", "CHECK (1)"))
    conn.commit()
    conn.close()
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    _insert(conn, **{missing: ""})
    conn.close()

    with pytest.raises(ProxyIngestError, match=missing):
        _ingest(path, writer)


def test_a_row_with_no_requirement_is_refused(tmp_path, writer) -> None:
    """The dedicated arm the removal proof names.

    The parametrized version above covers all three labels; `check_tampers.py`
    refuses a proof naming a parametrized selector, because pytest exits 4 on
    one it cannot resolve and the harness would read that as proved.
    """
    path = tmp_path / "no-requirement.sqlite3"
    conn = sqlite3.connect(path)
    conn.executescript(_go_decision_schema())
    conn.commit()
    conn.close()
    conn = sqlite3.connect(path)
    _insert(conn, requirement="")
    conn.close()

    with pytest.raises(ProxyIngestError, match="carries no requirement"):
        _ingest(path, writer)


def test_unattributed_finds_a_row_with_no_rule_and_is_empty_otherwise() -> None:
    def row(rule_id: str, seq: int) -> DecisionRow:
        return DecisionRow(
            seq=seq, ts=1.0, disposition="deny", rule_id=rule_id, reason="r",
            requirement="FR-011", method="GET", path="/x",
            resolved_tier="unresolved", session_id="s", policy_version="v",
            absolute_https_denied=0, credential_fpr="", detail="")

    assert unattributed([row("EG-METH-001", 1), row("EG-ALLOW-000", 2)]) == []
    assert unattributed([row("EG-METH-001", 1), row("  ", 2)]) == [2]


# ---------------------------------------------------------------------------
# The disposition map — named YES values, no complement.
# ---------------------------------------------------------------------------


def test_the_two_known_dispositions_map_to_declared_outcomes() -> None:
    assert set(DISPOSITION_OUTCOME) == {"allow", "deny"}
    assert outcome_of("allow") == trace.OUTCOME_OK
    assert outcome_of("deny") == trace.OUTCOME_DENIED
    for value in DISPOSITION_OUTCOME.values():
        assert value in trace.OUTCOMES


@pytest.mark.parametrize("unknown", ["quarantine", "ALLOW", "", "allow "])
def test_an_unclassified_disposition_is_refused_not_folded_into_a_denial(
    unknown,
) -> None:
    with pytest.raises(ProxyIngestError, match="not a disposition"):
        outcome_of(unknown)


def test_an_unclassified_disposition_stops_the_ingest(proxy_db, writer) -> None:
    """The dedicated, non-parametrized arm the removal proof names.

    `tools/check_tampers.py` refuses a proof naming a parametrized selector,
    because pytest exits 4 on one it cannot resolve and the harness would read
    that as proved.
    """
    conn = _decision_db(proxy_db)
    _insert(conn, disposition="quarantine")
    conn.close()
    with pytest.raises(ProxyIngestError, match="quarantine"):
        _ingest(proxy_db, writer)


# ---------------------------------------------------------------------------
# FR-038 — the span set stays closed, and an allow is recorded too.
# ---------------------------------------------------------------------------


def test_the_ingested_span_kind_is_one_fr038_already_declares(
    proxy_db, writer
) -> None:
    conn = _decision_db(proxy_db)
    _insert(conn)
    conn.close()
    _ingest(proxy_db, writer)

    kinds = {json.loads(s["payload"])["kind"] for s in writer.spans("sess-1")}
    assert kinds == {trace.EGRESS_DECISION}
    assert kinds <= set(trace.KINDS), "the ingest introduced a kind FR-038 does not declare"


def test_an_allow_is_ingested_and_not_only_a_denial(proxy_db, writer) -> None:
    """FR-038's fourth clause: for every decision and not only for denials."""
    conn = _decision_db(proxy_db)
    _insert(conn, disposition="allow", rule_id="EG-ALLOW-000", reason="allowed",
            requirement="FR-011", method="GET", path="/orders/O-1",
            resolved_tier="read_only")
    conn.close()
    _ingest(proxy_db, writer)

    payload = _details(writer)[0]
    assert payload["outcome"] == trace.OUTCOME_OK
    assert payload["decision"]["rule_id"] == "EG-ALLOW-000"
    assert payload["decision"]["resolved_tier"] == "read_only"


def test_the_span_carries_the_inputs_the_rule_matched_on(proxy_db, writer) -> None:
    conn = _decision_db(proxy_db)
    _insert(conn, method="POST", path="/orders/O-1/cancel",
            policy_version="sha256:" + "b" * 64, absolute_https_denied=7,
            credential_fpr="sha256:0123456789abcdef", detail="stage=method")
    conn.close()
    _ingest(proxy_db, writer)

    payload = _details(writer)[0]
    assert payload["decision"]["matched"] == {
        "method": "POST", "path": "/orders/O-1/cancel",
        "policy_version": "sha256:" + "b" * 64}
    assert payload["detail"]["absolute_https_denied"] == 7
    assert payload["detail"]["credential_fingerprint"] == "sha256:0123456789abcdef"
    assert payload["detail"]["detail"] == "stage=method"
    assert payload["at"] == 1000.5


def test_no_credential_value_shape_reaches_the_trace(proxy_db, writer) -> None:
    """The fingerprint is a digest and the span carries no bearer-shaped value.

    Scored with the same patterns `tests/contract/test_trace_redaction.py`
    uses, imported rather than restated so the two cannot drift.
    """
    from tests.contract.test_trace_redaction import credential_findings

    conn = _decision_db(proxy_db)
    _insert(conn, credential_fpr="sha256:0123456789abcdef",
            detail="target=api.example.test")
    conn.close()
    _ingest(proxy_db, writer)
    assert not credential_findings(json.dumps(writer.spans("sess-1")))


# ---------------------------------------------------------------------------
# The watermark, derived from the trace itself.
# ---------------------------------------------------------------------------


def test_a_second_ingest_over_an_unchanged_log_moves_nothing(
    proxy_db, writer
) -> None:
    conn = _decision_db(proxy_db)
    _insert(conn)
    _insert(conn, disposition="allow", rule_id="EG-ALLOW-000",
            reason="allowed", requirement="FR-011")
    conn.close()

    first = _ingest(proxy_db, writer)
    assert first.ingested == 2 and first.highest_seq == 2
    again = _ingest(proxy_db, writer)
    assert again.ingested == 0
    assert len(writer.spans("sess-1")) == 2, "the second pass duplicated spans"


def test_an_ingest_resumes_after_the_last_span_that_landed(
    proxy_db, writer
) -> None:
    conn = _decision_db(proxy_db)
    _insert(conn)
    conn.close()
    assert _ingest(proxy_db, writer).ingested == 1

    conn = _decision_db(proxy_db)
    _insert(conn, path="/second")
    _insert(conn, path="/third")
    conn.close()

    second = _ingest(proxy_db, writer)
    assert second.ingested == 2
    paths = [p["decision"]["matched"]["path"] for p in _details(writer)]
    assert paths == ["/orders/O-1/cancel", "/second", "/third"]


def test_the_watermark_comes_from_the_spans_and_not_from_a_cursor(
    proxy_db, writer
) -> None:
    conn = _decision_db(proxy_db)
    _insert(conn)
    conn.close()
    assert watermark(writer, "sess-1") == 0
    _ingest(proxy_db, writer)
    assert watermark(writer, "sess-1") == 1
    assert watermark(writer, "sess-never-seen") == 0


def test_only_the_named_sessions_decisions_are_ingested(proxy_db, writer) -> None:
    conn = _decision_db(proxy_db)
    _insert(conn, session_id="sess-1")
    _insert(conn, session_id="sess-2", path="/other")
    conn.close()

    result = _ingest(proxy_db, writer, session="sess-1")
    assert result.ingested == 1
    assert not writer.spans("sess-2")


def test_a_span_that_cannot_be_written_does_not_advance_the_watermark(
    proxy_db, writer
) -> None:
    """The watermark's whole argument: there is nothing to disagree with it.

    The first row is fine, the second is unrepresentable. The ingest raises
    part-way; the next pass resumes after the span that actually landed,
    because "what has been ingested" is read out of the spans rather than out
    of a cursor that a partial pass could have advanced.
    """
    conn = _decision_db(proxy_db)
    _insert(conn, path="/first")
    _insert(conn, path="/second", disposition="quarantine")
    _insert(conn, path="/third")
    conn.close()

    with pytest.raises(ProxyIngestError):
        _ingest(proxy_db, writer)
    assert watermark(writer, "sess-1") == 1
    assert [p["decision"]["matched"]["path"] for p in _details(writer)] == ["/first"]


# ---------------------------------------------------------------------------
# The SQL this module issues.
# ---------------------------------------------------------------------------


def test_the_ingest_issues_no_write_statement_at_all() -> None:
    """`src/runtime/proxy_ingest.py` is on the permitted list for the
    engine-specific-SQL invariant, which suspends that check for the whole
    file. This narrows the exemption back down: the SQL in it must be a read.
    """
    source = Path(proxy_ingest.__file__).read_text()
    forbidden = re.findall(
        r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|REPLACE|PRAGMA|VACUUM|ATTACH)\b",
        source)
    assert not forbidden, (
        f"write- or schema-bearing SQL in the ingest: {sorted(set(forbidden))}. "
        "The proxy owns this store."
    )
    assert "SELECT" in source, (
        "no SELECT in the module, so the check above passed over nothing"
    )


# ---------------------------------------------------------------------------
# Against a database the real Go writer produced.
# ---------------------------------------------------------------------------


@pytest.mark.skipif(shutil.which("go") is None, reason="no Go toolchain")
def test_the_ingest_reads_a_database_the_go_writer_actually_wrote(
    tmp_path, writer
) -> None:
    """The arm the derived schema cannot give: fidelity to what `Write` stores.

    Scored on the exported file rather than on the Go exit code. `go test`
    exits 0 over a package with no test files and `-run` exits 0 when its
    pattern matches nothing, so a green exit here would be consistent with
    nothing having run at all; the file's existence and its contents are not.
    """
    export = tmp_path / "from-go.sqlite3"
    proc = subprocess.run(
        ["go", "test", "-count=1", "-run",
         "^TestDecisionLogExportForRuntimeIngest$", "./..."],
        cwd=GO_MODULE, capture_output=True, text=True,
        env={**os.environ, "F2A_DECISIONLOG_EXPORT": str(export)})
    assert export.is_file(), (
        "the Go export test produced no database, so nothing ran:\n"
        f"{proc.stdout}\n{proc.stderr}")

    result = _ingest(export, writer, session="sess-ingest")
    assert result.ingested >= 2, (
        f"the exported log yielded {result.ingested} decisions for the session; "
        "an ingest over one row cannot show a per-rule label travelling")
    assert len(set(result.rule_ids)) >= 2

    payloads = _details(writer, "sess-ingest")
    outcomes = {p["outcome"] for p in payloads}
    assert outcomes == {trace.OUTCOME_OK, trace.OUTCOME_DENIED}, (
        f"the exported log covered only {outcomes}; an ingest scored over "
        "denials alone says nothing about FR-038's 'and not only for denials'")
    for payload in payloads:
        assert payload["detail"]["requirement"].startswith("FR-")
        assert payload["detail"]["reason"]
        assert payload["decision"]["rule_id"]
