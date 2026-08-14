"""T018 / INV-009 — single-writer ownership across the three processes.

**Why this is an invariant and not a unit test.** data-model.md gives the
reason: *"finding 006 explicitly did not test its session service under
concurrent writers"*, and T-06's narrowing records that v1's store now has **no**
observed substrate rather than one. Single-writer ownership is how v1 avoids
depending on evidence nobody has. Every other guarantee in the storage layer
sits on top of it, so a violation has to fail the invariant suite in
milliseconds rather than surface as a corrupted row under load.

Two arms:

- **Structural** — every table has exactly one declared writer, every role in
  the map exists, and a write from a non-owner raises before any SQL is built.
- **Concurrent** — real threads standing in for the three processes, all
  writing at once against one database file, asserting that only the owner's
  rows land and that the non-owners were refused rather than serialized.
"""

from __future__ import annotations

import sqlite3
import threading

import pytest

from src.contracts import ownership
from src.contracts.repository import (
    NotEqual,
    Repository,
    ScopeError,
    UniquenessError,
)

TABLE = "trace_span"  # owned by the runtime


def _repo(path, role: str) -> Repository:
    return Repository(path, role=role, tenant_id="t-1", deployment_id="d-1")


# ---------------------------------------------------------------------------
# Structural.

def test_every_table_has_exactly_one_writer() -> None:
    seen: dict[str, str] = {}
    for row in ownership.OWNERSHIP:
        assert row.table not in seen, (
            f"{row.table} appears twice in the ownership map, claimed by "
            f"{seen.get(row.table)} and {row.writer}"
        )
        seen[row.table] = row.writer
    assert len(seen) == len(ownership.OWNERSHIP)


def test_every_role_named_in_the_map_exists() -> None:
    for row in ownership.OWNERSHIP:
        assert row.writer in ownership.ROLES
        assert row.readers <= ownership.ROLES


def test_the_judge_tables_have_no_readers_in_the_success_path() -> None:
    """FR-052 and Principle I, at the ownership layer.

    The import-graph invariant keeps the module boundary structural; this keeps
    the *data* boundary structural, which is the half a new consumer would
    otherwise cross without importing anything.
    """
    for table in ("judge_verdict", "human_label"):
        row = ownership.BY_TABLE[table]
        assert row.readers == frozenset(), (
            f"{table} gained reader {sorted(row.readers)}. A model judge's "
            "verdict must not be reachable from the success path."
        )
        for consumer in (ownership.ROLE_RUNTIME, ownership.ROLE_PROXY,
                         ownership.ROLE_SUPERVISOR, ownership.ROLE_ANALYSIS):
            with pytest.raises(ownership.OwnershipError):
                ownership.require_read(table, consumer)


def test_effect_gate_observation_has_no_success_path_readers() -> None:
    """FR-041's corpus is measurement. T187 will assert the tables are apart.

    The empty reader set is the same shape as `judge_verdict`: a success-path
    role that could open it for read could start deciding allow/deny from it.
    """
    row = ownership.BY_TABLE["effect_gate_observation"]
    assert row.writer == ownership.ROLE_PROXY
    assert row.readers == frozenset(), (
        f"effect_gate_observation gained reader {sorted(row.readers)}. "
        "The corpus is not a success-path input."
    )
    for consumer in (ownership.ROLE_RUNTIME, ownership.ROLE_SUPERVISOR,
                     ownership.ROLE_ANALYSIS, ownership.ROLE_SHADOW_JUDGE):
        with pytest.raises(ownership.OwnershipError):
            ownership.require_read("effect_gate_observation", consumer)


def test_an_undeclared_table_has_no_writer() -> None:
    with pytest.raises(ownership.OwnershipError, match="no declared writer"):
        ownership.writer_of("some_table_nobody_decided")


@pytest.mark.parametrize("row", ownership.OWNERSHIP, ids=lambda r: r.table)
def test_only_the_owner_may_write_each_table(row) -> None:
    ownership.require_write(row.table, row.writer)
    for other in ownership.ROLES - {row.writer}:
        with pytest.raises(ownership.OwnershipError, match="sole writer"):
            ownership.require_write(row.table, other)


# ---------------------------------------------------------------------------
# Concurrent, across the three processes (threads standing in for them).

def test_concurrent_writers_are_refused_not_serialized(tmp_path) -> None:
    """The case finding 006 did not test.

    Three roles write the same table simultaneously. Only the runtime owns it.
    The assertion is not merely that the data is intact — it is that the two
    non-owners were **refused**, because a store that serialized them would be
    relying on concurrency behaviour v1 has no evidence for.
    """
    path = tmp_path / "concurrent.sqlite3"
    owner = _repo(path, ownership.ROLE_RUNTIME)
    owner.create_table(TABLE, {"span_id": "text not null", "kind": "text not null"})

    refusals: list[Exception] = []
    accepted: list[int] = []
    barrier = threading.Barrier(3)
    lock = threading.Lock()

    def writer(role: str, count: int) -> None:
        repo = _repo(path, role)
        try:
            barrier.wait(timeout=10)
            for i in range(count):
                try:
                    repo.insert(TABLE, {"span_id": f"{role}-{i}", "kind": "model_call"})
                    with lock:
                        accepted.append(1)
                except ownership.OwnershipError as error:
                    with lock:
                        refusals.append(error)
        finally:
            repo.close()

    threads = [
        threading.Thread(target=writer, args=(role, 25))
        for role in (ownership.ROLE_RUNTIME, ownership.ROLE_SUPERVISOR,
                     ownership.ROLE_PROXY)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
        assert not thread.is_alive(), "a writer thread hung; the store deadlocked"

    assert len(accepted) == 25, "the owner's writes did not all land"
    assert len(refusals) == 50, (
        f"{len(refusals)} refusals for 50 non-owner writes. A non-owner write "
        "that succeeded means ownership is advisory."
    )

    rows = owner.select(TABLE)
    assert len(rows) == 25
    assert all(row["span_id"].startswith("runtime-") for row in rows)
    owner.close()


def test_readers_are_not_blocked_by_the_writer(tmp_path) -> None:
    """WAL is chosen for the access pattern ownership already forces.

    If a reader blocked behind the writer, the single-writer design would cost
    availability rather than buying safety, and someone would reasonably want
    to remove it.
    """
    path = tmp_path / "wal.sqlite3"
    owner = _repo(path, ownership.ROLE_RUNTIME)
    owner.create_table(TABLE, {"span_id": "text not null", "kind": "text not null"})
    assert owner.journal_mode().lower() == "wal"

    reader = _repo(path, ownership.ROLE_ANALYSIS)
    read_counts: list[int] = []
    stop = threading.Event()

    def read_loop() -> None:
        while not stop.is_set():
            read_counts.append(len(reader.select(TABLE)))

    thread = threading.Thread(target=read_loop, daemon=True)
    thread.start()
    try:
        for i in range(200):
            owner.insert(TABLE, {"span_id": f"s-{i}", "kind": "tool_call"})
    finally:
        stop.set()
        thread.join(timeout=15)

    assert not thread.is_alive(), "the reader never finished; it was blocked"
    assert read_counts, "the reader never completed a read while writing"
    assert max(read_counts) > 0
    reader.close()
    owner.close()


# ---------------------------------------------------------------------------
# FR-035's scope columns.

def test_every_row_carries_tenant_and_deployment(tmp_path) -> None:
    path = tmp_path / "scope.sqlite3"
    repo = _repo(path, ownership.ROLE_RUNTIME)
    repo.create_table(TABLE, {"span_id": "text not null", "kind": "text not null"})
    repo.insert(TABLE, {"span_id": "s-1", "kind": "model_call"})

    raw = sqlite3.connect(path)
    raw.row_factory = sqlite3.Row
    rows = [dict(r) for r in raw.execute(f"SELECT * FROM {TABLE}")]
    raw.close()
    assert rows[0]["tenant_id"] == "t-1"
    assert rows[0]["deployment_id"] == "d-1"
    repo.close()


def test_a_caller_cannot_set_its_own_scope(tmp_path) -> None:
    """Cross-tenant writes are a typo away if the caller supplies the column."""
    path = tmp_path / "scope2.sqlite3"
    repo = _repo(path, ownership.ROLE_RUNTIME)
    repo.create_table(TABLE, {"span_id": "text not null", "kind": "text not null"})
    with pytest.raises(ScopeError):
        repo.insert(TABLE, {"span_id": "s", "kind": "x", "tenant_id": "t-other"})
    with pytest.raises(ScopeError):
        repo.insert(TABLE, {"span_id": "s", "kind": "x", "deployment_id": "d-other"})
    repo.close()


def test_a_read_never_crosses_a_tenant(tmp_path) -> None:
    path = tmp_path / "tenants.sqlite3"
    one = _repo(path, ownership.ROLE_RUNTIME)
    one.create_table(TABLE, {"span_id": "text not null", "kind": "text not null"})
    one.insert(TABLE, {"span_id": "s-1", "kind": "model_call"})

    other = Repository(path, role=ownership.ROLE_RUNTIME,
                       tenant_id="t-2", deployment_id="d-1")
    assert other.select(TABLE) == [], "a read reached another tenant's rows"
    other.insert(TABLE, {"span_id": "s-2", "kind": "model_call"})
    assert len(one.select(TABLE)) == 1
    assert len(other.select(TABLE)) == 1
    one.close()
    other.close()


def test_an_update_with_no_predicate_is_refused(tmp_path) -> None:
    path = tmp_path / "update.sqlite3"
    repo = _repo(path, ownership.ROLE_RUNTIME)
    repo.create_table(TABLE, {"span_id": "text not null", "kind": "text not null"})
    with pytest.raises(Exception, match="no predicate"):
        repo.update(TABLE, where={}, values={"kind": "x"})
    repo.close()


# ---------------------------------------------------------------------------
# FR-035 where the scope travels on the row instead of on the connection.
#
# One table is declared this way — `session`, because FR-050 layer 1 resolves an
# opaque digest before the tenant is knowable. The obligation is *inverted*, not
# waived, and the arms below assert both directions of that inversion. Each is
# written so it fails for one reason: an unscoped handle that could reach an
# ordinary table, a scoped handle that could reach this one, a row admitted
# without the columns, and a unique key that stopped being global. A single arm
# that only checked "a session row can be written" would pass with any three of
# those four broken.

SESSION_COLUMNS = {
    "session_id": "text primary key",
    "capability_sha256": "text not null",
    "state": "text not null",
}


def _session_repo(path) -> Repository:
    repo = Repository.unscoped(path, role=ownership.ROLE_SUPERVISOR)
    repo.create_table("session", SESSION_COLUMNS,
                      unique=[["capability_sha256"]])
    return repo


def test_only_the_session_table_carries_its_scope_on_the_row() -> None:
    """The declaration is a fact about the map, so it is asserted there.

    Stated as a set rather than as "session is per-row" because the claim that
    matters is the *count*: this is an inversion of FR-035's mechanism granted
    for one unanswerable read, and a second table acquiring it silently is the
    way it would become a general escape hatch.
    """
    per_row = {row.table for row in ownership.OWNERSHIP if row.scope_per_row}
    assert per_row == {"session"}, (
        f"{sorted(per_row)} carry their scope on the row. Only `session` has "
        f"the reason — an opaque capability digest resolved before the tenant "
        f"is known. Any other table adopting this is dropping the connection "
        f"scope, not inverting it"
    )
    assert ownership.scope_is_per_row("session")
    assert not ownership.scope_is_per_row(TABLE)


def test_an_unscoped_repository_cannot_reach_an_ordinary_table(tmp_path) -> None:
    """The half that keeps `unscoped` from being a way around FR-035.

    Without this refusal, any caller wanting to skip the tenant predicate on
    any table could open `unscoped` and get rows with no scope at all.
    """
    repo = Repository.unscoped(tmp_path / "unscoped.sqlite3",
                               role=ownership.ROLE_RUNTIME)
    with pytest.raises(ScopeError, match="unscoped repository cannot touch"):
        repo.create_table(TABLE, {"span_id": "text not null"})
    repo.close()


def test_a_scoped_repository_cannot_reach_the_per_row_table(tmp_path) -> None:
    """And the other direction, which is the one that fails silently.

    A connection-scoped handle on `session` would *work*: rows would be
    written, filed under whatever tenant that connection carried, and
    `resolve` would then answer only for that tenant. FR-050's enforcement
    point would start denying every capability issued by a differently-scoped
    supervisor, with no error anywhere to attribute it to.
    """
    repo = Repository(tmp_path / "scoped.sqlite3",
                      role=ownership.ROLE_SUPERVISOR,
                      tenant_id="t-1", deployment_id="d-1")
    with pytest.raises(ScopeError, match="scope travels on the row"):
        repo.create_table("session", SESSION_COLUMNS)
    repo.close()


def test_a_per_row_table_still_requires_both_scope_columns(tmp_path) -> None:
    """FR-035 unweakened: the caller supplies them and the layer refuses without.

    The written row is read back through the raw connection rather than
    through `select`, because `select` on this table carries no scope predicate
    — so asking it would prove the columns are *readable*, not that they hold
    what the caller passed.
    """
    path = tmp_path / "session.sqlite3"
    repo = _session_repo(path)
    for incomplete in (
        {"session_id": "s", "capability_sha256": "a", "state": "STARTING"},
        {"session_id": "s", "capability_sha256": "a", "state": "STARTING",
         "tenant_id": "t-1"},
        {"session_id": "s", "capability_sha256": "a", "state": "STARTING",
         "deployment_id": "d-1"},
    ):
        with pytest.raises(ScopeError, match="not supplied"):
            repo.insert("session", incomplete)

    repo.insert("session", {
        "session_id": "s", "capability_sha256": "a", "state": "STARTING",
        "tenant_id": "t-1", "deployment_id": "d-1",
    })
    raw = sqlite3.connect(path)
    raw.row_factory = sqlite3.Row
    stored = [dict(r) for r in raw.execute("SELECT * FROM session")]
    raw.close()
    assert stored[0]["tenant_id"] == "t-1"
    assert stored[0]["deployment_id"] == "d-1"
    repo.close()


def test_a_per_row_unique_key_is_global_and_a_read_carries_no_tenant(
        tmp_path) -> None:
    """The two halves that only make sense together, asserted together.

    A unique group on an ordinary table is indexed with the scope columns
    prepended, so two tenants may hold the same key. On this table that would
    be unsound *because* the read carries no tenant predicate: `resolve` would
    find two rows for one digest and no predicate able to say which was meant.
    So the index drops the prefix, and the second half asserts the read it
    exists for — a row written under one tenant is found by a digest lookup
    with no tenant anywhere in the call.
    """
    path = tmp_path / "global.sqlite3"
    repo = _session_repo(path)
    repo.insert("session", {
        "session_id": "s-1", "capability_sha256": "deadbeef",
        "state": "RUNNING", "tenant_id": "t-1", "deployment_id": "d-1",
    })
    with pytest.raises(UniquenessError):
        repo.insert("session", {
            "session_id": "s-2", "capability_sha256": "deadbeef",
            "state": "RUNNING", "tenant_id": "t-2", "deployment_id": "d-2",
        })

    found = repo.select("session", where={"capability_sha256": "deadbeef"})
    assert len(found) == 1 and found[0]["session_id"] == "s-1", (
        "a digest lookup with no tenant predicate did not find the row a "
        "differently-scoped writer wrote, so the per-row scope leaked into "
        "the read FR-050 layer 1 depends on"
    )
    repo.close()


def test_not_equal_moves_only_the_rows_that_are_not_the_value(tmp_path) -> None:
    """The one non-equality predicate, and the guard it exists to make possible.

    A second `terminate` has to change **zero** rows so the first recorded
    outcome survives (FR-006). Asserted as the rowcount *and* as the stored
    value, because an unguarded update returns 1 and overwrites — and a
    predicate that matched nothing at all would also return 0 while breaking
    the first termination.
    """
    path = tmp_path / "notequal.sqlite3"
    repo = _session_repo(path)
    repo.insert("session", {
        "session_id": "s-1", "capability_sha256": "a", "state": "RUNNING",
        "tenant_id": "t-1", "deployment_id": "d-1",
    })
    first = repo.update(
        "session", where={"session_id": "s-1", "state": NotEqual("TERMINATED")},
        values={"state": "TERMINATED"})
    assert first == 1, "the guard refused the first termination"

    second = repo.update(
        "session", where={"session_id": "s-1", "state": NotEqual("TERMINATED")},
        values={"state": "TERMINATED_AGAIN"})
    assert second == 0, (
        "a second termination moved the row, so the recorded outcome is the "
        "last one written rather than the one that happened"
    )
    assert repo.select("session")[0]["state"] == "TERMINATED"
    repo.close()


def test_a_transaction_rolls_back_every_write_in_it(tmp_path) -> None:
    """The property FR-054's ref move depends on.

    A ref moved with no history entry is the one unrecoverable state retained
    history exists to prevent, so a partial transaction has to be impossible
    rather than unlikely.
    """
    path = tmp_path / "txn.sqlite3"
    repo = _repo(path, ownership.ROLE_RUNTIME)
    repo.create_table(TABLE, {"span_id": "text not null", "kind": "text not null"})

    with pytest.raises(RuntimeError):
        with repo.transaction():
            repo.insert(TABLE, {"span_id": "a", "kind": "model_call"})
            repo.insert(TABLE, {"span_id": "b", "kind": "model_call"})
            raise RuntimeError("halfway")

    assert repo.select(TABLE) == [], (
        "rows survived a failed transaction; the transaction is a comment"
    )
    repo.close()


def test_no_engine_specific_sql_lives_above_the_repository() -> None:
    """T016's **second** obligation, scanned rather than trusted.

    Numbered as the module docstring numbers it. This said "third" and there
    is no third reading of that list — the drift is small and it is the same
    drift that let a paraphrase in T050's probe restate obligation 2 as a rule
    about exceptions, which it is not.

    T-06 records that v1's store has no observed substrate. Keeping SQL below
    one layer is what makes replacing that substrate a change to one file
    rather than an audit of every caller. A scan is used because the
    alternative — a convention — has no failure mode until someone needs a
    query in a hurry.
    """
    from pathlib import Path

    from src.contracts.repository import sql_bearing_lines

    root = Path(__file__).resolve().parents[2] / "src"
    permitted = {
        root / "contracts" / "repository.py",       # the layer itself
        # `supervisor/session_table.py` used to be the second entry here,
        # carrying the reason `# predates T016; see below`. It is gone because
        # the migration it deferred has happened: every statement that file
        # runs now goes through `Repository`, so the clause holds tree-wide and
        # the exemption has nothing left to suspend. The failure message below
        # no longer names it, and if it reappears the right response is the
        # migration rather than a third entry.
        # Reads `sqlite_master` of the *codegraph* database to compute the
        # schema digest T004 pins. That is a foreign artifact this system
        # consumes, not part of its own store, so routing it through the
        # repository would be routing a read of somebody else's database
        # through our tenancy layer.
        root / "analysis" / "codegraph_pin.py",
        # T093. Reads the *enforcement point's* decision database — another
        # process's store, written by Go, with its own schema and none of
        # FR-035's scope columns. Same footing as `codegraph_pin.py`: routing
        # it through `Repository` would route a read of somebody else's
        # database through our tenancy layer, and `Repository` opens for
        # writing (it sets journal mode), which is exactly the thing the
        # ownership direction forbids here.
        #
        # **This exemption is narrower than it looks, and the narrowing is
        # tested.** `tests/contract/test_proxy_ingest.py`'s
        # `test_the_ingest_issues_no_write_statement_at_all` scans the same
        # file for write- and schema-bearing SQL, so what is suspended is
        # "no engine-specific SQL" and not "no writes".
        root / "runtime" / "proxy_ingest.py",
        # T179. Reads the *enforcement point's* observation table — the same
        # foreign store as the ingest, a different table, still written by
        # Go, still without FR-035's scope columns. A report reader, not a
        # mapped success-path reader: the ownership row's reader set stays
        # empty. Same footing, same narrowing:
        # `tests/unit/test_effect_corpus.py`'s
        # `test_the_exporter_issues_no_write_statement_at_all` scans the
        # file for write- and schema-bearing SQL.
        root / "runtime" / "reports" / "effect_corpus.py",
    }

    offenders: list[str] = []
    for source_file in sorted(root.rglob("*.py")):
        if source_file in permitted:
            continue
        for number, line in sql_bearing_lines(source_file.read_text()):
            offenders.append(f"{source_file.relative_to(root)}:{number}: {line}")

    assert not offenders, (
        "SQL above the repository layer:\n  " + "\n  ".join(offenders) +
        "\nRoute it through src/contracts/repository.py. Adding a file to "
        "`permitted` is the last resort and not the first: the one exemption "
        "this list ever carried for a store of ours — `session_table.py`, "
        "recorded as a known migration rather than hidden by widening the "
        "scan — stood for months and was eventually paid off by moving the "
        "file inside the layer, which is what the entry always said it meant. "
        "If a table needs something the layer does not offer, the answer is "
        "usually that the layer is missing it: `session` needed per-row "
        "scope columns and a non-equality predicate, and both went in below "
        "this line rather than around it."
    )


def test_the_scan_would_actually_catch_something() -> None:
    """A scan with a broken pattern passes silently. This is the control."""
    from src.contracts.repository import sql_bearing_lines

    planted = 'rows = conn.execute("SELECT * FROM trace_span WHERE id = ?")'
    assert sql_bearing_lines(planted), "the SQL scanner matches nothing"
    assert not sql_bearing_lines("x = 1\n# SELECT is mentioned in a comment")


def test_a_nested_transaction_does_not_commit_early(tmp_path) -> None:
    path = tmp_path / "nested.sqlite3"
    repo = _repo(path, ownership.ROLE_RUNTIME)
    repo.create_table(TABLE, {"span_id": "text not null", "kind": "text not null"})

    with pytest.raises(RuntimeError):
        with repo.transaction():
            repo.insert(TABLE, {"span_id": "outer", "kind": "model_call"})
            with repo.transaction():
                repo.insert(TABLE, {"span_id": "inner", "kind": "model_call"})
            raise RuntimeError("after the inner one closed")

    assert repo.select(TABLE) == [], (
        "the inner transaction committed the outer one's writes; a nested "
        "commit ends the outer transaction early"
    )
    repo.close()
