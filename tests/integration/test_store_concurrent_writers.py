"""T050 — the concurrent-writer probe against **our own** store.

**Why this exists and what it is worth.** T-06 records that v1's store has no
observed substrate: finding 006's session service was never exercised under
concurrent writers, and OD-15 removed it anyway. `tests/invariants/
test_writer_ownership.py` already asserts that a non-owner is *refused*. That is
the half ownership gives us. This file probes the half ownership does not: **what
the owner's own writes do when there are several of them, from several
processes, at once.**

The distinction matters because single-writer-per-*table* is not
single-writer-per-*process*. The runtime is one role and may be more than one
process — the runner, a resumed runner after a crash, and a supervisor-side
sweeper all open the store as `runtime`. Ownership permits all three. Nothing
until now measured what SQLite in WAL mode does with them.

**Real processes, not threads.** `test_writer_ownership.py` uses threads, which
share one interpreter and one lock; a `threading.Lock` inside `Repository` makes
that case safe by construction and says nothing about two OS processes. These
are `multiprocessing` children with separate connections, which is the shape the
three-process architecture actually has.

**What the probe is allowed to conclude.** It measures this substrate on this
platform. A green run here does not make concurrent writing safe in general; it
records that the failure modes the plan sized a +0-to-+4 day risk band for —
lost rows, corrupted rows, a wedged database, and rows that are simply *missing*
without an error — do not occur at this concurrency on SQLite in WAL mode. The
band is collapsed by a measurement, and the measurement is here rather than
described.
"""

from __future__ import annotations

import multiprocessing as mp
import os
import sqlite3
import sys
from pathlib import Path

import pytest

from src.contracts import ownership
from src.contracts.repository import Repository, UniquenessError

TABLE = "trace_span"          # runtime-owned
CEILING_TABLE = "session_ceiling"
WRITERS = 3
PER_WRITER = 60

# `fork` shares the parent's sqlite connections into the child, which is exactly
# the hazard sqlite documents and not the one being measured. `spawn` gives each
# child its own interpreter and its own connection, which is what three
# processes look like.
_CONTEXT = mp.get_context("spawn")

_CEILING_COLUMNS = {
    "session_id": "text not null",
    "spend_usd": "real not null",
    "tokens": "int not null",
    "wall_clock_seconds": "real not null",
    "turns": "int not null",
}


def _ceiling_row(session_id: str) -> dict:
    return {
        "session_id": session_id, "spend_usd": 1.0, "tokens": 10,
        "wall_clock_seconds": 1.0, "turns": 1,
    }


def _repo(path: str, *, tenant: str = "t-1") -> Repository:
    return Repository(
        path, role=ownership.ROLE_RUNTIME, tenant_id=tenant, deployment_id="d-1")


def _write_spans(path: str, label: str, count: int, repo_root: str) -> tuple:
    """Child entry point. Returns (written, refused, errors)."""
    sys.path.insert(0, repo_root)
    written = 0
    refused = 0
    errors: list[str] = []
    repo = _repo(path)
    try:
        for i in range(count):
            try:
                repo.insert(TABLE, {"span_id": f"{label}-{i}", "kind": "tool_call"})
                written += 1
            except UniquenessError:
                refused += 1
            except Exception as exc:  # noqa: BLE001 — the probe's whole subject
                errors.append(f"{type(exc).__name__}: {exc}")
    finally:
        repo.close()
    return written, refused, errors


def _claim_ceiling(path: str, label: str, repo_root: str) -> tuple:
    """Every child tries to be the one that pins the session's ceilings."""
    sys.path.insert(0, repo_root)
    repo = _repo(path)
    try:
        try:
            repo.insert(CEILING_TABLE, {
                "session_id": "sess-contended",
                "spend_usd": 1.0, "tokens": 10,
                "wall_clock_seconds": 1.0, "turns": 1,
            })
            return ("won", label, "")
        except UniquenessError:
            return ("refused", label, "")
        except Exception as exc:  # noqa: BLE001
            return ("error", label, f"{type(exc).__name__}: {exc}")
    finally:
        repo.close()


def _repo_root() -> str:
    return str(Path(__file__).resolve().parents[2])


def _run(target, argsets) -> list:
    with _CONTEXT.Pool(processes=len(argsets)) as pool:
        return pool.starmap(target, argsets)



def test_three_processes_writing_the_owned_table_lose_no_row(tmp_path) -> None:
    """The measurement the +0-to-+4 band was sized for.

    The assertion is on the **count of rows in the file**, read through a
    connection none of the writers held. A probe that asked the writers how many
    rows they wrote would be asking the thing under test.
    """
    path = str(tmp_path / "concurrent.sqlite3")
    owner = _repo(path)
    owner.create_table(TABLE, {"span_id": "text not null", "kind": "text not null"},
                       unique=[["span_id"]])
    owner.close()

    root = _repo_root()
    results = _run(_write_spans, [
        (path, f"p{n}", PER_WRITER, root) for n in range(WRITERS)
    ])

    reported_errors = [e for _, _, errs in results for e in errs]
    assert reported_errors == [], (
        "a writer in the owning role failed. Single-writer-per-table does not "
        "mean single-writer-per-process, and these are all the runtime:\n  "
        + "\n  ".join(reported_errors)
    )

    # Counted from the file, not from the writers.
    raw = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    landed = raw.execute(f"SELECT count(*) FROM {TABLE}").fetchone()[0]
    distinct = raw.execute(
        f"SELECT count(DISTINCT span_id) FROM {TABLE}").fetchone()[0]
    integrity = raw.execute("PRAGMA integrity_check").fetchone()[0]
    raw.close()

    assert integrity == "ok", f"the database is corrupt after the run: {integrity}"
    assert landed == WRITERS * PER_WRITER, (
        f"{landed} rows landed for {WRITERS * PER_WRITER} writes with no error "
        "reported. A write that neither landed nor raised is finding 006's "
        "silent lost update at the storage layer."
    )
    assert distinct == landed, "rows duplicated under concurrency"



def test_exactly_one_process_wins_a_contended_unique_key(tmp_path) -> None:
    """Pinning a session's ceilings, raced.

    Three processes resume the same session at once — the shape a supervisor
    restart produces — and all three try to pin its ceilings. Exactly one may
    win. Two winners would mean two ceiling rows for one session, and `load()`
    reads the first, so the session would run under whichever number the read
    happened to see.
    """
    path = str(tmp_path / "ceilings.sqlite3")
    owner = _repo(path)
    owner.create_table(CEILING_TABLE, {
        "session_id": "text not null",
        "spend_usd": "real not null",
        "tokens": "int not null",
        "wall_clock_seconds": "real not null",
        "turns": "int not null",
    }, unique=[["session_id"]])
    owner.close()

    root = _repo_root()
    results = _run(_claim_ceiling, [(path, f"p{n}", root) for n in range(WRITERS)])

    outcomes = [outcome for outcome, _, _ in results]
    failures = [detail for outcome, _, detail in results if outcome == "error"]
    assert failures == [], "a claimant failed for a reason other than the key:\n  " \
        + "\n  ".join(failures)
    assert outcomes.count("won") == 1, (
        f"{outcomes.count('won')} processes pinned the same session's ceilings "
        f"({outcomes}). More than one means the ceiling a session runs under "
        "depends on which row a read happens to see; none means the store "
        "refused the first writer too."
    )
    assert outcomes.count("refused") == WRITERS - 1

    raw = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    rows = raw.execute(f"SELECT count(*) FROM {CEILING_TABLE}").fetchone()[0]
    raw.close()
    assert rows == 1, f"{rows} ceiling rows for one session"



def test_the_unique_guard_is_in_the_store_and_not_in_the_process(tmp_path) -> None:
    """The control for the arm above.

    If uniqueness were guarded by a check inside `SessionStore`, the previous
    test would still pass whenever the OS happened to serialize the children —
    and fail intermittently under load, which is the worst version. This asserts
    the constraint is in the file: a *second connection* that never saw the
    first one's insert is refused.
    """
    path = str(tmp_path / "guard.sqlite3")
    first = _repo(path)
    first.create_table(CEILING_TABLE, {
        "session_id": "text not null",
        "spend_usd": "real not null",
        "tokens": "int not null",
        "wall_clock_seconds": "real not null",
        "turns": "int not null",
    }, unique=[["session_id"]])
    first.insert(CEILING_TABLE, {
        "session_id": "s-1", "spend_usd": 1.0, "tokens": 1,
        "wall_clock_seconds": 1.0, "turns": 1,
    })

    second = _repo(path)
    with pytest.raises(UniquenessError):
        second.insert(CEILING_TABLE, {
            "session_id": "s-1", "spend_usd": 2.0, "tokens": 2,
            "wall_clock_seconds": 2.0, "turns": 2,
        })

    # And the constraint is scoped, so another tenant's identical key is fine.
    # An unscoped unique index would refuse a row the refusing tenant cannot see.
    other = _repo(path, tenant="t-2")
    other.insert(CEILING_TABLE, {
        "session_id": "s-1", "spend_usd": 3.0, "tokens": 3,
        "wall_clock_seconds": 3.0, "turns": 3,
    })
    assert len(other.select(CEILING_TABLE)) == 1
    assert len(first.select(CEILING_TABLE)) == 1

    for repo in (first, second, other):
        repo.close()



def test_a_refused_insert_does_not_wedge_another_connection(tmp_path) -> None:
    """The defect this probe found, kept found.

    A statement that fails inside an implicit transaction does not end it. Before
    the rollback in `Repository.insert`, one refused uniqueness insert left its
    connection holding a write lock, and the next write from *any other*
    connection blocked for SQLite's busy timeout and then raised
    `sqlite3.OperationalError: database is locked` — an engine-specific
    exception the repository layer's second obligation says no caller sees.

    The arm asserts the *unrelated* write succeeds. Asserting only that the
    refusal raises `UniquenessError` was true the whole time and is what let the
    defect through.
    """
    path = str(tmp_path / "wedge.sqlite3")
    writer = _repo(path)
    writer.create_table(CEILING_TABLE, _CEILING_COLUMNS, unique=[["session_id"]])
    writer.insert(CEILING_TABLE, _ceiling_row("s-1"))

    refused = _repo(path)
    with pytest.raises(UniquenessError):
        refused.insert(CEILING_TABLE, _ceiling_row("s-1"))

    unrelated = _repo(path)
    unrelated.insert(CEILING_TABLE, _ceiling_row("s-2"))
    assert len(unrelated.select(CEILING_TABLE)) == 2, (
        "the write after the refusal did not land, so the refused connection "
        "is still holding the lock"
    )
    # And the refused connection is usable rather than stuck in its own
    # aborted transaction.
    refused.insert(CEILING_TABLE, _ceiling_row("s-3"))
    assert len(refused.select(CEILING_TABLE)) == 3

    for repo in (writer, refused, unrelated):
        repo.close()


def test_a_refusal_inside_a_transaction_still_rolls_the_whole_group_back(
    tmp_path,
) -> None:
    """The control for the rollback's guard.

    The rollback is conditional on not being inside a `transaction()`, because
    an unconditional one would discard the outer group's earlier writes at the
    moment the caller might still catch the refusal and carry on. This asserts
    the group is still atomic: the earlier write must not survive.
    """
    path = str(tmp_path / "txn.sqlite3")
    repo = _repo(path)
    repo.create_table(CEILING_TABLE, _CEILING_COLUMNS, unique=[["session_id"]])
    repo.insert(CEILING_TABLE, _ceiling_row("existing"))

    with pytest.raises(UniquenessError):
        with repo.transaction():
            repo.insert(CEILING_TABLE, _ceiling_row("new"))
            repo.insert(CEILING_TABLE, _ceiling_row("existing"))

    keys = {row["session_id"] for row in repo.select(CEILING_TABLE)}
    assert keys == {"existing"}, (
        f"{keys} — the first write in the group survived a failed transaction"
    )
    repo.close()


def test_a_reader_sees_a_consistent_database_while_processes_write(tmp_path) -> None:
    """WAL's reason for being chosen, measured across processes.

    A reader that saw a torn write, or blocked until the writers finished, would
    make the store's read path unusable from the supervisor while a session
    runs — and the enforcement point reads on every request.
    """
    path = str(tmp_path / "readwhile.sqlite3")
    owner = _repo(path)
    owner.create_table(TABLE, {"span_id": "text not null", "kind": "text not null"})
    assert owner.journal_mode().lower() == "wal"
    owner.close()

    root = _repo_root()
    pool = _CONTEXT.Pool(processes=WRITERS)
    async_result = pool.starmap_async(
        _write_spans, [(path, f"r{n}", PER_WRITER, root) for n in range(WRITERS)])

    reader = _repo(path)
    counts: list[int] = []
    while not async_result.ready():
        counts.append(len(reader.select(TABLE)))
    results = async_result.get(timeout=60)
    pool.close()
    pool.join()

    assert [e for _, _, errs in results for e in errs] == []
    assert counts, "the reader never completed a read while the writers ran"
    assert counts == sorted(counts), (
        f"a read saw fewer rows than an earlier read ({counts[:20]}...). Rows "
        "do not disappear, so this would be a reader seeing an inconsistent "
        "snapshot."
    )
    assert len(reader.select(TABLE)) == WRITERS * PER_WRITER
    reader.close()



def test_the_probe_would_notice_a_lost_write(tmp_path) -> None:
    """The control. A probe whose assertions cannot fail proves nothing.

    One writer is asked for fewer writes than the assertion expects, standing in
    for a lost one, and the count read from the file has to disagree.
    """
    path = str(tmp_path / "control.sqlite3")
    owner = _repo(path)
    owner.create_table(TABLE, {"span_id": "text not null", "kind": "text not null"},
                       unique=[["span_id"]])
    owner.close()

    root = _repo_root()
    results = _run(_write_spans, [
        (path, "p0", PER_WRITER, root),
        (path, "p1", PER_WRITER - 5, root),
    ])
    assert [e for _, _, errs in results for e in errs] == []

    raw = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    landed = raw.execute(f"SELECT count(*) FROM {TABLE}").fetchone()[0]
    raw.close()
    assert landed == 2 * PER_WRITER - 5
    assert landed != 2 * PER_WRITER, (
        "the count read from the file did not move when five writes went "
        "missing, so the assertion in the arm above is not reading the outcome"
    )



def test_the_probe_ran_under_more_than_one_process(tmp_path) -> None:
    """`spawn` children really are separate processes.

    A probe that silently degraded to running everything in the parent would
    measure the threading case again and report it as the process case. The pids
    are read from the children.
    """
    root = _repo_root()
    with _CONTEXT.Pool(processes=WRITERS) as pool:
        pids = pool.map(_pid_of, [root] * WRITERS)
    assert len(set(pids)) == WRITERS, f"children shared pids: {pids}"
    assert os.getpid() not in pids, "a child ran in the parent process"


def _pid_of(repo_root: str) -> int:
    sys.path.insert(0, repo_root)
    return os.getpid()
