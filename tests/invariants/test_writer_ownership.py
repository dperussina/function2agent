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
from src.contracts.repository import Repository, ScopeError

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
        root / "supervisor" / "session_table.py",   # predates T016; see below
        # Reads `sqlite_master` of the *codegraph* database to compute the
        # schema digest T004 pins. That is a foreign artifact this system
        # consumes, not part of its own store, so routing it through the
        # repository would be routing a read of somebody else's database
        # through our tenancy layer.
        root / "analysis" / "codegraph_pin.py",
    }

    offenders: list[str] = []
    for source_file in sorted(root.rglob("*.py")):
        if source_file in permitted:
            continue
        for number, line in sql_bearing_lines(source_file.read_text()):
            offenders.append(f"{source_file.relative_to(root)}:{number}: {line}")

    assert not offenders, (
        "SQL above the repository layer:\n  " + "\n  ".join(offenders) +
        "\nRoute it through src/contracts/repository.py, or add the file to "
        "`permitted` with a reason. `session_table.py` is permitted because it "
        "was built before T016 and is the supervisor's own store; it is a "
        "known migration, recorded here rather than hidden by widening the "
        "scan."
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
