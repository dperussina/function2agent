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

**Why the children rendezvous.** `Pool` gives its workers no task affinity: the
workers pull from one shared queue (`multiprocessing/pool.py`, `worker()`), so a
worker that finishes early takes the next task, and a worker still booting takes
none. Measured on this platform, a pool of three handed three cheap tasks ran
all three in *one* process on 149 of 150 loaded runs; and even when three
distinct processes did run, they never all wrote at the same time on 18 of 25
loaded runs — three writers, one after another. Both degradations are silent,
and both are the single-process case wearing the process case's name.

Asserting distinctness afterwards cannot fix this, because `Pool` does not offer
the property being asserted: the assertion just fails at the degradation's own
rate. So the children *rendezvous* instead. Each opens its store, then blocks
until every sibling has reached the same point. A reused worker cannot fill an
N-party barrier, so worker reuse becomes impossible rather than merely detected;
and passing the barrier is what makes the writes genuinely simultaneous rather
than adjacent. If the rendezvous cannot be met, it times out and the arm fails
naming the degradation — the measurement is refused, never quietly weakened.

**What the probe is allowed to conclude.** It measures this substrate on this
platform. A green run here does not make concurrent writing safe in general; it
records that the failure modes the plan sized a +0-to-+4 day risk band for —
lost rows, corrupted rows, a wedged database, and rows that are simply *missing*
without an error — do not occur at this concurrency on SQLite in WAL mode. The
band is collapsed by a measurement, and the measurement is here rather than
described.

**What it has cost and what it has returned.** This probe has now found two
defects that single-process testing could not reach, both in the storage layer,
both having survived the ordinary suite:

1. `Repository.insert` left an implicit transaction open on `IntegrityError`,
   holding a write lock and wedging every other connection for the busy
   timeout. Invisible to a single connection, because the refusal raises
   `UniquenessError` either way and the damage lands elsewhere.
2. `Repository.__init__` let `sqlite3.OperationalError` escape when several
   processes converted a brand-new store to WAL at once — and the same leak was
   then found on four more methods. Invisible to a single connection, because
   an uncontended write never raises at all.

Two is recorded here rather than turned into a rate, and the number is not the
useful part. The shape is: both defects are in error paths that only exist when
a *second* connection does something, so no amount of coverage on one
connection reaches them. Any subsystem whose tests hold one handle to a shared
resource has the same blind spot, and this file is the only instrument in the
tree pointed at it.
"""

from __future__ import annotations

import multiprocessing as mp
import os
import sqlite3
import sys
import threading
import time
from pathlib import Path

import pytest

from src.contracts import ownership
from src.contracts.repository import (
    BUSY_TIMEOUT_S,
    CONVERGENCE_WINDOW_S,
    WAL_ENTRY_PEER,
    Repository,
    StoreBusyError,
    StoreUnavailableError,
    StoreWedgedError,
    UniquenessError,
)

TABLE = "trace_span"          # runtime-owned
CEILING_TABLE = "session_ceiling"
WRITERS = 3
PER_WRITER = 60

# `fork` shares the parent's sqlite connections into the child, which is exactly
# the hazard sqlite documents and not the one being measured. `spawn` gives each
# child its own interpreter and its own connection, which is what three
# processes look like.
_CONTEXT = mp.get_context("spawn")

# Long enough that three spawned interpreters importing this module under a
# loaded machine are never mistaken for a degraded pool, and short enough that a
# genuinely unmeetable rendezvous is not a hang. Nothing correct waits this long.
_RENDEZVOUS_TIMEOUT_S = 30.0

# How long the planted holder keeps its lock after the opener has been let go.
# Two margins have to hold at once and this sits four orders of magnitude
# inside both: the opener reaches its pragma microseconds after the barrier, so
# the lock is certainly still held; and this is well inside
# `CONVERGENCE_WINDOW_S`, so the conversion is certainly seen. Missing either
# is reported as `wal_entry == "self"`, never as a flake.
_HOLD_THE_LOCK_S = 0.1

# Set once per child by the pool initializer. A synchronization primitive cannot
# be pickled through the task queue, but it can be inherited through the worker
# process's own construction, which is what `initargs` uses.
_BARRIER = None


class RendezvousFailed(RuntimeError):
    """The children could not be made to run one-per-process, simultaneously."""


def _receive_barrier(barrier) -> None:
    global _BARRIER
    _BARRIER = barrier


def _open_and_meet_siblings(
    path: str, label: str, timeout: float = _RENDEZVOUS_TIMEOUT_S
) -> Repository:
    """Open this child's own store, then block until every sibling has one.

    The two are deliberately one operation. A child that opened a connection
    without meeting its siblings would be the degradation this file exists to
    exclude, and nothing downstream of it can tell the difference — the writes
    still land. So there is no version of this a caller is trusted to remember
    to call: getting a store *is* meeting the siblings.

    Returning means every task is in a process of its own and all of them are
    about to write at once. Not returning is the only other outcome; no path
    here quietly proceeds with fewer writers.

    `timeout` is a parameter only so the control below can induce the failure
    without waiting out a duration chosen for the loaded case.
    """
    try:
        repo = _repo(path)
    except BaseException:
        # Release the siblings now. Left to time out, the rendezvous failure
        # they would report is a consequence of this one, and it would race the
        # real error for which the pool surfaces first.
        _BARRIER.abort()
        raise
    try:
        _BARRIER.wait(timeout=timeout)
    except threading.BrokenBarrierError:
        repo.close()
        raise RendezvousFailed(
            f"{label} waited {timeout}s and its siblings never "
            "arrived. Either the pool ran two of these tasks in one process — "
            "which collapses the connections the probe exists to keep separate "
            "— or a sibling died before reaching the rendezvous. Either way "
            "this run measured fewer writers than it names, so it is refused "
            "rather than reported."
        ) from None
    return repo


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
    """Child entry point. Returns (pid, written, refused, errors).

    The pid is returned so the arm that consumes the numbers can assert, of the
    very run that produced them, that each writer had a process to itself.
    """
    sys.path.insert(0, repo_root)
    written = 0
    refused = 0
    errors: list[str] = []
    repo = _open_and_meet_siblings(path, label)
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
    return os.getpid(), written, refused, errors


def _claim_ceiling(path: str, label: str, repo_root: str) -> tuple:
    """Every child tries to be the one that pins the session's ceilings.

    Returns (pid, outcome, label, detail).
    """
    sys.path.insert(0, repo_root)
    repo = _open_and_meet_siblings(path, label)
    try:
        try:
            repo.insert(CEILING_TABLE, {
                "session_id": "sess-contended",
                "spend_usd": 1.0, "tokens": 10,
                "wall_clock_seconds": 1.0, "turns": 1,
            })
            return (os.getpid(), "won", label, "")
        except UniquenessError:
            return (os.getpid(), "refused", label, "")
        except Exception as exc:  # noqa: BLE001
            return (os.getpid(), "error", label, f"{type(exc).__name__}: {exc}")
    finally:
        repo.close()


def _repo_root() -> str:
    return str(Path(__file__).resolve().parents[2])


def _pool(parties: int):
    """A pool whose children can find each other.

    `chunksize=1` is explicit rather than inferred, so that a future change to
    the task count cannot silently hand one worker two of them in a batch.
    """
    return _CONTEXT.Pool(
        processes=parties,
        initializer=_receive_barrier,
        initargs=(_CONTEXT.Barrier(parties),),
    )


def _run(target, argsets) -> list:
    with _pool(len(argsets)) as pool:
        return pool.starmap(target, argsets, chunksize=1)


def _assert_one_process_each(pids: list, expected: int) -> None:
    """Assert of *this* run what the rendezvous was supposed to guarantee.

    Sound rather than hopeful: the rendezvous already made a shared process
    impossible, so this cannot fail intermittently the way asserting it of an
    unconstrained pool did. It is here so the arm that reports the number can
    also say how many processes produced it.
    """
    assert os.getpid() not in pids, (
        f"a writer ran in the parent process ({os.getpid()}): {pids}. The probe "
        "degraded to the single-process case and would have reported it as the "
        "process case."
    )
    assert len(set(pids)) == expected, (
        f"{len(set(pids))} processes did {expected} writers' work: {pids}. The "
        "rendezvous should have made this unreachable, so it has been weakened "
        "or removed. The numbers above came from fewer connections than the "
        "arm names, and sequential writes down one connection land fine — which "
        "is why this has to be checked and not assumed."
    )



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

    _assert_one_process_each([pid for pid, _, _, _ in results], WRITERS)

    reported_errors = [e for _, _, _, errs in results for e in errs]
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

    _assert_one_process_each([pid for pid, _, _, _ in results], WRITERS)

    outcomes = [outcome for _, outcome, _, _ in results]
    failures = [detail for _, outcome, _, detail in results if outcome == "error"]
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
    `sqlite3.OperationalError: database is locked`.

    That exception is now `StoreWedgedError`. This docstring used to call it
    "an engine-specific exception the repository layer's second obligation says
    no caller sees", which the obligation does not say: obligation 2 is about
    SQL and its check is a source scanner. The rule about exceptions is real
    but *derived* from the obligation's reason, and it is now written down in
    `repository.py` rather than surviving only as a paraphrase here. The
    paraphrase was load-bearing and wrong at the same time, which is how it
    would have sent the next reader to edit the wrong contract.

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
    pool = _pool(WRITERS)
    async_result = pool.starmap_async(
        _write_spans, [(path, f"r{n}", PER_WRITER, root) for n in range(WRITERS)],
        chunksize=1)

    reader = _repo(path)
    counts: list[int] = []
    while not async_result.ready():
        counts.append(len(reader.select(TABLE)))
    results = async_result.get(timeout=_RENDEZVOUS_TIMEOUT_S * 2)
    pool.close()
    pool.join()

    _assert_one_process_each([pid for pid, _, _, _ in results], WRITERS)
    assert [e for _, _, _, errs in results for e in errs] == []
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
    _assert_one_process_each([pid for pid, _, _, _ in results], 2)
    assert [e for _, _, _, errs in results for e in errs] == []

    raw = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    landed = raw.execute(f"SELECT count(*) FROM {TABLE}").fetchone()[0]
    raw.close()
    assert landed == 2 * PER_WRITER - 5
    assert landed != 2 * PER_WRITER, (
        "the count read from the file did not move when five writes went "
        "missing, so the assertion in the arm above is not reading the outcome"
    )



def test_the_rendezvous_refuses_a_pool_that_reuses_a_worker(tmp_path) -> None:
    """The control for every arm above, planted rather than argued.

    This is the degradation itself, deliberately induced: more tasks than the
    pool has processes, so one worker must take two of them and the rendezvous
    can never be met. The arms are only worth their names if this is loud, so
    the plant is kept here rather than performed once by hand.

    It goes through `_open_and_meet_siblings`, which is the same call the
    measuring children make, so this stays red if the rendezvous is weakened
    there rather than only if this test's own scaffolding changes.

    The predecessor of this test asserted `len(set(pids)) == WRITERS` of a pool
    it built for the purpose. That was unsound — `Pool` promises no task-to-
    worker affinity, its workers pull from one shared queue — so it failed on
    about one run in seven here while nothing was wrong, and it certified a pool
    that none of the measurements ran on. It is not restated: the property it
    reached for is now held by construction inside each arm, and what needed a
    control was the construction.
    """
    path = str(tmp_path / "rendezvous.sqlite3")
    # Created up front exactly as every arm creates its own, so that what this
    # control exercises is the rendezvous and not the first writer's race to
    # put a brand-new file into WAL mode.
    _repo(path).close()

    root = _repo_root()
    barrier = _CONTEXT.Barrier(WRITERS)
    with _CONTEXT.Pool(processes=WRITERS - 1, initializer=_receive_barrier,
                       initargs=(barrier,)) as pool:
        with pytest.raises(RendezvousFailed) as caught:
            pool.starmap(_meet_siblings_only,
                         [(path, f"p{n}", root, 2.0) for n in range(WRITERS)],
                         chunksize=1)

    assert "fewer writers than it names" in str(caught.value), (
        f"the rendezvous failed without saying what degraded: {caught.value}"
    )


def _meet_siblings_only(path: str, label: str, repo_root: str,
                        timeout: float) -> int:
    """A child that takes a store the normal way and then does nothing."""
    sys.path.insert(0, repo_root)
    _open_and_meet_siblings(path, label, timeout).close()
    return os.getpid()


# ---------------------------------------------------------------------------
# The *first* open, which is a different race from every arm above.
#
# Every arm above creates the store before the children run — one of them says
# so in a comment, so that what it exercises is the rendezvous "and not the
# first writer's race to put a brand-new file into WAL mode". That race was
# left alone as out of scope, and it is a real defect: measured here at 21 of
# 120 concurrent first opens raising `sqlite3.OperationalError` straight out of
# `Repository.__init__`, and 0 of 120 once the file is already in WAL.
#
# **Why these plants do not use the pool.** Adding processes does not make the
# race certain: measured at 24/40 trials with three, 28/40 with eight — it
# plateaus around two thirds and never approaches one. So an arm that opened a
# store from N processes and asserted "a loser occurred" would fail about a
# third of the time while nothing was wrong, which is the unsound shape the
# rendezvous was built to replace. Worse, an arm that asserted only "nobody
# raised" would pass a third of the time *without the race happening at all*,
# which is the degradation this file exists to refuse.
#
# So the loser is **constructed instead of raced for**. A second connection
# holds the lock that the conversion needs, which makes losing certain rather
# than likely, and each plant asserts which path was actually taken. A plant
# that failed to induce its condition fails loudly rather than passing on the
# strength of not having tried.


def _hold(path: str, level: str) -> sqlite3.Connection:
    """A second connection holding a real lock on `path`.

    SQLite arbitrates between two connections in one process exactly as it does
    between two processes, so a thread is enough here and a subprocess would
    only add spawn latency to a test whose subject is a lock.

    `IMMEDIATE` takes RESERVED, which is what the WAL conversion is refused by
    without waiting; `EXCLUSIVE` also blocks the shared lock underneath it,
    which is what makes the busy handler run to exhaustion. The two produce the
    two different classifications, so both are needed.

    `check_same_thread=False` because one plant releases this lock from the
    thread standing in for the winner. Without it the release raises
    `ProgrammingError` in that thread, the store is never converted, and the
    plant fails looking exactly like the defect it is testing the repair for.
    """
    conn = sqlite3.connect(path, timeout=BUSY_TIMEOUT_S, isolation_level=None,
                           check_same_thread=False)
    conn.execute(f"BEGIN {level}")
    return conn


def _new_rollback_mode_store(path: str) -> None:
    """A store that exists, has never been in WAL, and is not locked.

    A file that does not exist at all cannot be locked by the holder, and a
    file already in WAL never runs the conversion — `PRAGMA journal_mode=WAL`
    is a no-op when the mode already matches, which is exactly why the warm
    case never failed. So the plants need this third state, which is what a
    brand-new store looks like in the instant before the first opener converts
    it.
    """
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE IF NOT EXISTS _seed (x)")
    conn.commit()
    conn.close()


def test_a_first_open_that_loses_the_wal_race_converges_instead_of_raising(
    tmp_path,
) -> None:
    """The defect, planted so that losing is certain rather than likely.

    A holder takes RESERVED on a brand-new store, so the opener's
    `PRAGMA journal_mode=WAL` **cannot** succeed: SQLite refuses the promotion
    outright rather than waiting, because the conversion runs inside a read
    transaction and the busy handler is bypassed on that path. The holder then
    does what the winner of the real race does — releases and converts — and
    the opener has to notice.

    The assertion that makes this a measurement rather than a hope is
    `wal_entry`. Asserting only that the open succeeded would pass on a run
    where the opener simply won, which is the failure this file's rendezvous
    was written to eliminate. `peer` is reachable by exactly one path.
    """
    path = str(tmp_path / "firstopen.sqlite3")
    _new_rollback_mode_store(path)
    holder = _hold(path, "IMMEDIATE")

    started = threading.Barrier(2)
    failures: list[str] = []

    def release_after_the_open_has_failed() -> None:
        started.wait(timeout=_RENDEZVOUS_TIMEOUT_S)
        # Long enough that the opener's pragma has certainly run and been
        # refused — it runs microseconds after the barrier — and far inside the
        # opener's convergence window, so the conversion is seen. Both margins
        # are four orders of magnitude, and missing either shows up as
        # `wal_entry == "self"` below rather than as a flake.
        time.sleep(_HOLD_THE_LOCK_S)
        try:
            holder.execute("ROLLBACK")
            holder.execute("PRAGMA journal_mode=WAL")
        except BaseException as exc:  # noqa: BLE001
            failures.append(f"{type(exc).__name__}: {exc}")

    winner = threading.Thread(target=release_after_the_open_has_failed)
    winner.start()
    try:
        started.wait(timeout=_RENDEZVOUS_TIMEOUT_S)
        loser = _repo(path)
    finally:
        winner.join(timeout=_RENDEZVOUS_TIMEOUT_S)
        holder.close()

    assert failures == [], f"the plant's own winner failed: {failures}"
    assert loser.wal_entry == WAL_ENTRY_PEER, (
        f"the opener reported {loser.wal_entry!r}, so it won the conversion "
        "rather than losing it and this run measured nothing. The holder's "
        "RESERVED lock should have made winning impossible; either it was "
        "released early or the opener never attempted the pragma."
    )
    assert loser.journal_mode() == "wal", (
        "the opener returned a store that is not in WAL mode. Proceeding "
        "against a store this layer did not finish configuring is worse than "
        "the exception it replaced."
    )
    loser.close()


def test_a_wedged_store_is_not_reported_as_transient(tmp_path) -> None:
    """The control that keeps the repair above from swallowing the last defect.

    A retry loop cannot tell a sibling one millisecond from finishing from a
    lock held by a crashed process, because both refuse the pragma the same
    way. This plants the second — a lock nobody is going to convert — and
    requires it to read differently from the first.

    The lock is `EXCLUSIVE`, so even the shared lock underneath the conversion
    is blocked and SQLite's busy handler *is* consulted and runs to exhaustion.
    That is the evidence the classification rests on: not a guess about the
    holder's health, but the observation that a lock outlasted the entire busy
    timeout. Every write this layer performs is a single statement, so nothing
    healthy does that — and the previous defect found here, a connection left
    holding a write lock by a failed insert, is precisely a thing that does.

    Run against the shipped `BUSY_TIMEOUT_S` rather than a shortened one, so
    what is measured is the configuration that ships.
    """
    path = str(tmp_path / "wedged.sqlite3")
    _new_rollback_mode_store(path)
    holder = _hold(path, "EXCLUSIVE")
    try:
        began = time.monotonic()
        with pytest.raises(StoreWedgedError) as caught:
            _repo(path)
        waited = time.monotonic() - began
    finally:
        holder.execute("ROLLBACK")
        holder.close()

    assert not isinstance(caught.value, StoreBusyError), (
        "a held lock was reported as momentary contention. An operator reading "
        "'retrying is reasonable' about a wedged store retries forever."
    )
    assert waited >= BUSY_TIMEOUT_S * 0.5, (
        f"the refusal came back in {waited:.3f}s, well inside the "
        f"{BUSY_TIMEOUT_S}s busy timeout, so the busy handler did not run to "
        "exhaustion and 'wedged' is not what was measured."
    )


def test_a_momentarily_contended_store_is_not_reported_as_wedged(tmp_path) -> None:
    """The other half of the same distinction, and the one that needs the state.

    Here the holder takes `RESERVED` and never converts. The opener's pragma is
    refused *immediately* — the busy handler is bypassed, exactly as in the
    benign race — so timing alone cannot separate this from the arm two above.
    What separates them is that the store never converges: nobody is putting it
    into WAL, so the window expires and the opener says so.

    This is why the repair waits on the **end state** rather than on the lock.
    A retry loop here would have spent a lock-sized budget and then reported
    the same thing, only slower and with nothing learned.
    """
    path = str(tmp_path / "busy.sqlite3")
    _new_rollback_mode_store(path)
    holder = _hold(path, "IMMEDIATE")
    try:
        began = time.monotonic()
        with pytest.raises(StoreBusyError) as caught:
            _repo(path)
        waited = time.monotonic() - began
    finally:
        holder.execute("ROLLBACK")
        holder.close()

    assert not isinstance(caught.value, StoreWedgedError)
    assert CONVERGENCE_WINDOW_S <= waited < BUSY_TIMEOUT_S * 0.5, (
        f"the opener waited {waited:.3f}s. Below "
        f"{CONVERGENCE_WINDOW_S}s it did not give the store the window it "
        f"documents; at or above {BUSY_TIMEOUT_S * 0.5}s it waited out a lock "
        "instead, which is the retry loop this repair exists not to be."
    )


def test_no_sqlite_exception_escapes_the_write_surface(tmp_path, monkeypatch) -> None:
    """Construction was where it was measured; it was never only there.

    The module docstring's second obligation is about SQL, and the exception
    rule is derived from its reason — a caller that writes
    `except sqlite3.OperationalError` is coupled to SQLite exactly as a caller
    holding SQL is. Derived or not, it was being broken on five methods, and a
    plant that covered only `__init__` would leave four of them to be found
    again later.

    `select` is included and is expected to *succeed*: WAL readers do not block
    on a writer, which is the property WAL was chosen for. It is asserted
    rather than assumed, because a `select` that started raising here would
    mean the store had lost that property.

    The busy timeout is shortened for this arm alone. The arm above measures
    the shipped value once; repeating a five-second wait per method would buy
    nothing but a slower suite, and the classification boundary scales with the
    constant rather than being pinned to it.
    """
    monkeypatch.setattr("src.contracts.repository.BUSY_TIMEOUT_S", 1.0)

    path = str(tmp_path / "surface.sqlite3")
    owner = _repo(path)
    owner.create_table(TABLE, {"span_id": "text not null", "kind": "text not null"},
                       unique=[["span_id"]])
    owner.insert(TABLE, {"span_id": "seed", "kind": "tool_call"})
    owner.close()

    victim = _repo(path)
    holder = _hold(path, "EXCLUSIVE")
    leaked: list[str] = []
    succeeded: list[str] = []

    def attempt(name: str, call) -> None:
        try:
            call()
            succeeded.append(name)
        except sqlite3.Error as exc:
            leaked.append(f"{name}: {type(exc).__name__}: {exc}")
        except StoreUnavailableError:
            pass

    attempt("select", lambda: victim.select(TABLE))
    attempt("insert", lambda: victim.insert(
        TABLE, {"span_id": "b", "kind": "tool_call"}))
    attempt("update", lambda: victim.update(
        TABLE, where={"span_id": "seed"}, values={"kind": "other"}))
    attempt("create_table", lambda: victim.create_table(
        "drift_signal", {"signal_id": "text not null"}))

    try:
        holder.execute("ROLLBACK")
    finally:
        holder.close()
        victim.close()

    assert leaked == [], (
        "an engine exception reached a caller from the ordinary surface:\n  "
        + "\n  ".join(leaked) +
        "\nA caller catching `sqlite3.OperationalError` is a caller that has "
        "to be edited when the substrate moves, which is the thing the second "
        "obligation's own reason rules out."
    )
    assert succeeded == ["select"], (
        f"{succeeded} completed against an exclusively locked store. A read is "
        "expected to succeed — that is what WAL was chosen for — and a write "
        "is not."
    )


def test_the_plants_above_would_notice_the_translation_being_removed(
    tmp_path, monkeypatch
) -> None:
    """The control. A guard asserted only by argument is this repo's own rot.

    `_engine_errors` is what the four `attempt` calls above pass through. This
    checks the check: with a real held lock, the *untranslated* call underneath
    raises the engine exception the arm above requires never to be seen. If
    this stops raising, the arm above is passing because nothing contended,
    not because anything was translated.
    """
    monkeypatch.setattr("src.contracts.repository.BUSY_TIMEOUT_S", 1.0)

    path = str(tmp_path / "control.sqlite3")
    owner = _repo(path)
    owner.create_table(TABLE, {"span_id": "text not null", "kind": "text not null"})
    owner.close()

    victim = _repo(path)
    holder = _hold(path, "EXCLUSIVE")
    try:
        with pytest.raises(sqlite3.OperationalError):
            # Deliberately below the translation, which is the only way to show
            # that the translation is what the arm above is observing.
            victim._conn.execute(                      # noqa: SLF001
                'INSERT INTO "trace_span" ("tenant_id", "deployment_id", '
                '"span_id", "kind") VALUES (?, ?, ?, ?)',
                ("t-1", "d-1", "z", "tool_call"))
    finally:
        holder.execute("ROLLBACK")
        holder.close()
        victim.close()


def test_several_processes_opening_a_brand_new_store_all_get_one(tmp_path) -> None:
    """The end-to-end shape, kept as a regression rather than as the plant.

    This is the configuration the defect was reported from: several processes
    opening a store that does not exist yet. It is *not* the plant, because the
    race it needs occurs on about two thirds of runs and no party count makes
    it certain — so it can only assert the safety property, and it says nothing
    on the third of runs where the processes happened not to collide.

    It is kept because it is the only arm that exercises the real
    configuration, and because a store whose first open is per-process
    unreliable is the thing an operator actually meets.
    """
    path = str(tmp_path / "cold.sqlite3")
    root = _repo_root()
    results = _run(_open_a_brand_new_store,
                   [(path, f"p{n}", root) for n in range(WRITERS)])

    _assert_one_process_each([pid for pid, _, _, _ in results], WRITERS)

    raised = [detail for _, outcome, detail, _ in results if outcome == "raised"]
    assert raised == [], (
        "opening a brand-new store from several processes at once failed:\n  "
        + "\n  ".join(raised)
    )
    modes = {mode for _, _, mode, _ in results}
    assert modes == {"wal"}, (
        f"{modes} — an opener returned a store in a journal mode this layer "
        "does not run against, which is worse than the refusal it replaced."
    )


def _open_a_brand_new_store(path: str, label: str, repo_root: str) -> tuple:
    """Child entry point for the *first-open* race.

    The rendezvous is before the open rather than after it. Every other child
    here takes its store first and then meets its siblings, because what those
    arms race is the writes; what this one races is the open, so the barrier
    has to be on the other side of it.
    """
    sys.path.insert(0, repo_root)
    _BARRIER.wait(timeout=_RENDEZVOUS_TIMEOUT_S)
    try:
        repo = _repo(path)
    except BaseException as exc:  # noqa: BLE001 — the arm's whole subject
        return (os.getpid(), "raised", f"{type(exc).__name__}: {exc}", "")
    try:
        return (os.getpid(), "opened", repo.journal_mode(), repo.wal_entry)
    finally:
        repo.close()
