"""FR-050's mechanism test: **ceasing to act revokes**, and the capability
does not outlive the run.

The requirement's hard clause is the crash case — the authority must lapse
*without any code having run*. So the fixture kills the supervisor the way
finding 006 killed its probes: `SIGKILL` delivered **from a separate OS
process**, chosen precisely so that no `finally` block, no `atexit` hook and no
graceful-shutdown path can execute. A test that called `renewer.stop()` would
prove only that the orderly path works, which is the path that was never in
doubt.

Three layers, three arms:

  layer 1  the handle is opaque, so there is nothing in it to honour offline
  layer 2  the lease lapses when nothing renews  ← the SIGKILL arm
  layer 3  the listener descriptor closes with the process  ← the second
           SIGKILL arm, and the one that makes the common crash instant

**SC-024's replay fixture, both arms.** A handle captured during a session and
replayed from inside a later session's environment is *denied and recorded*.
Replayed from a position with no path to the enforcement point it is *refused
by unreachability* and recorded only as a drop — because nothing receives the
connection to record anything else.

Run:
    docker run --rm -v "$PWD:/work" -w /work f2a-dev \\
        python -m pytest tests/integration/test_lease_revocation.py -v
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

from src.contracts.repository import StoreBusyError, StoreWedgedError
from src.supervisor.capability import Capability, issue
from src.supervisor.lease import (
    LEASE_TTL_MULTIPLE,
    TOLERATED_CONSECUTIVE_BUSY,
    LeaseRenewer,
    LeaseTerms,
)
from src.supervisor.listener import SessionListener, is_reachable
from src.supervisor.session_table import (
    STATE_RUNNING,
    SessionTable,
    capability_digest,
)

INTERVAL = 0.20


@pytest.fixture()
def table(tmp_path: Path) -> SessionTable:
    with SessionTable(tmp_path / "sessions.db") as handle:
        yield handle


def _start(table: SessionTable, session_id: str, now: float) -> Capability:
    capability = issue(session_id)
    table.create(
        session_id=session_id,
        tenant_id="t-1",
        deployment_id="d-1",
        capability_sha256=capability.digest,
        lease_expires_at=now + INTERVAL * LEASE_TTL_MULTIPLE,
        now=now,
    )
    table.mark_running(session_id)
    return capability


# --- layer 1: the handle is opaque ----------------------------------------

def test_the_handle_carries_no_claim_and_no_expiry() -> None:
    capability = issue("s-1")
    handle = capability.header_value()
    assert len(handle) == 64 and int(handle, 16) >= 0, "not opaque hex"
    for structure in (".", "{", "eyJ", "-----BEGIN"):
        assert structure not in handle, (
            f"the handle contains {structure!r}; a self-describing credential "
            "is honoured by anyone who can parse it, for as long as its own "
            "expiry says, whether or not anything is alive to revoke it"
        )
    assert capability.digest == capability_digest(handle)


def test_the_table_stores_a_digest_and_never_the_handle(table) -> None:
    capability = _start(table, "s-1", time.time())
    row = table.get("s-1")
    assert row is not None
    assert row.capability_sha256 == capability.digest
    raw = Path(table.path).read_bytes()
    assert capability.header_value().encode() not in raw, (
        "the handle itself is in the database, so a read-only reader — the "
        "proxy included — holds something it could replay"
    )


def test_the_handle_is_not_printable(caplog) -> None:
    capability = issue("s-1")
    assert capability.header_value() not in f"{capability}"
    assert capability.header_value() not in repr(capability)


# --- layer 2: the lease --------------------------------------------------

def test_a_renewed_lease_is_honoured(table) -> None:
    now = time.time()
    capability = _start(table, "s-1", now)
    renewer = LeaseRenewer(table, LeaseTerms("s-1", INTERVAL))
    assert renewer.renew_once(now)
    row = table.resolve(capability.digest)
    assert row is not None and row.honoured_at(now)


def test_an_unrenewed_lease_lapses(table) -> None:
    now = time.time()
    capability = _start(table, "s-1", now)
    row = table.resolve(capability.digest)
    assert row is not None
    assert row.honoured_at(now)
    assert not row.honoured_at(now + INTERVAL * LEASE_TTL_MULTIPLE + 0.001), (
        "the lease is still honoured past its expiry"
    )


def test_renewal_of_a_terminated_session_does_nothing(table) -> None:
    now = time.time()
    _start(table, "s-1", now)
    table.terminate("s-1", "terminated.completed")
    renewer = LeaseRenewer(table, LeaseTerms("s-1", INTERVAL))
    assert not renewer.renew_once(now), (
        "a renewer extended a terminated session's lease, which defeats the "
        "layer silently"
    )


def test_the_renewer_thread_actually_renews(table) -> None:
    """A regression guard on a defect the crash fixture surfaced.

    `sqlite3`'s same-thread guard killed the renewer thread with no symptom
    except a lease that would not renew. Asserting the renewal *count* from
    the main thread catches that; asserting only that the lease was honoured
    at some point does not.
    """
    _start(table, "s-1", time.time())
    renewer = LeaseRenewer(table, LeaseTerms("s-1", 0.05))
    renewer.start()
    time.sleep(0.30)
    renewer.stop()
    assert renewer.renewals >= 3, (
        f"only {renewer.renewals} renewals in 0.3s at a 0.05s interval; the "
        f"loop stopped: {renewer.stopped_because}"
    )
    assert renewer.stopped_because is None


def test_the_renewer_says_why_it_stopped(table) -> None:
    _start(table, "s-1", time.time())
    renewer = LeaseRenewer(table, LeaseTerms("s-1", 0.05))
    renewer.start()
    table.terminate("s-1", "terminated.completed")
    time.sleep(0.20)
    renewer.stop()
    assert renewer.stopped_because == "session is no longer RUNNING"


_PLANTED_RENEWER = textwrap.dedent(
    """
    import sqlite3, sys, time
    sys.path.insert(0, {repo!r})
    from src.supervisor.lease import LeaseRenewer, LeaseTerms
    from src.supervisor.session_table import SessionTable

    table = SessionTable({db!r})
    calls = []
    real = table.renew

    def one_busy(session_id, expiry):
        calls.append(1)
        if len(calls) == 2:
            raise sqlite3.OperationalError("database is locked")
        return real(session_id, expiry)

    table.renew = one_busy
    renewer = LeaseRenewer(table, LeaseTerms({session!r}, {interval!r}))
    renewer.start()
    print("READY", flush=True)
    time.sleep({lifetime!r})
    print("RENEWALS", renewer.renewals, flush=True)
    """
)


def test_a_failed_renewal_is_not_silent(tmp_path) -> None:
    """One momentary `SQLITE_BUSY`, and the lapse has to be attributable.

    **The lease lapses either way, and that is not what this asserts.** A
    swallowed exception and a raised one produce the same 1 renewal, the same
    `RUNNING` row and the same expired lease. What differs is whether an
    operator can find out why a *healthy* session's authority ended:
    swallowing leaves the reason on an attribute nothing in `src/` reads, and
    puts zero bytes anywhere a human looks.

    Out of process on purpose. `pytest` installs its own
    `threading.excepthook` and turns thread exceptions into warnings, so
    asserting inside the test process would measure the plugin rather than the
    channel a deployed supervisor has. The child also outlives the raise by an
    order of magnitude, which keeps the arm out of the interpreter-shutdown
    window the comment at the change site measures.
    """
    db = tmp_path / "sessions.db"
    repo = str(Path(__file__).resolve().parent.parent.parent)
    now = time.time()
    with SessionTable(db) as table:
        capability = _start(table, "s-busy", now)

    child = subprocess.run(
        [sys.executable, "-c", _PLANTED_RENEWER.format(
            repo=repo, db=str(db), session="s-busy",
            interval=0.05, lifetime=0.6)],
        capture_output=True, text=True, timeout=30,
    )

    assert child.returncode == 0, (
        f"the child did not exit cleanly (rc={child.returncode}), so this arm "
        f"is measuring a crash and not the renewer's report:\n{child.stderr}"
    )
    assert "READY" in child.stdout, "the renewer never started"
    assert "RENEWALS 1" in child.stdout, (
        f"the planted failure did not stop renewal where this arm expects, so "
        f"the stderr assertions below are not about it: {child.stdout!r}"
    )

    assert child.stderr, (
        "the renewer died and said nothing. One momentary SQLITE_BUSY — the "
        "class the repository layer labels *retrying is reasonable* — ended "
        "renewal for a live session, and the only surviving symptom is a "
        "lease that stopped moving"
    )
    assert "sqlite3.OperationalError: database is locked" in child.stderr, (
        f"stderr carries no engine error, so the reason did not survive:\n"
        f"{child.stderr}"
    )
    assert "_loop" in child.stderr and "lease-s-busy" in child.stderr, (
        f"stderr does not name the renewer thread or its loop, so a reader "
        f"cannot tell which mechanism stopped:\n{child.stderr}"
    )

    # The outcome half, asserted so the arm records that re-raising bought
    # visibility and changed nothing else.
    with SessionTable(db) as table:
        row = table.resolve(capability.digest)
    assert row is not None
    assert row.state == STATE_RUNNING, (
        "the row is no longer RUNNING, so the lapse came from termination "
        "rather than from renewal stopping"
    )
    assert not row.honoured_at(time.time()), (
        "the lease is still honoured, so renewal did not stop and the arm "
        "proves nothing about a lapse"
    )


# --- the two branches of `_loop`, which are a single decision -------------
#
# `StoreBusyError` is tolerated up to the budget the lease already grants;
# everything else stops renewal at once. The three arms below are written so
# that no one of them passes if the branch it is about is deleted: the
# tolerated arm fails if the split collapses into re-raise, the exhaustion arm
# fails if it collapses into swallow, and the wedged arm fails if the split is
# made on `StoreUnavailableError` — the common base — instead of on the busy
# subclass. Each asserts the number of *attempts* the table saw, which is a
# value the guard decides, rather than a word in a message some other module
# might also contain.

class _PlantedRenew:
    """A real table whose `renew` raises from the n-th call onward."""

    def __init__(self, table: SessionTable, exc: Exception, *,
                 fail_on: int, forever: bool = False) -> None:
        self._table = table
        self._exc = exc
        self._fail_on = fail_on
        self._forever = forever
        self.attempts = 0

    def renew(self, session_id: str, lease_expires_at: float) -> int:
        self.attempts += 1
        if self.attempts == self._fail_on or (
                self._forever and self.attempts >= self._fail_on):
            raise self._exc
        return self._table.renew(session_id, lease_expires_at)


def _run_planted(table, planted, *, intervals: int = 8, interval: float = 0.05):
    renewer = LeaseRenewer(planted, LeaseTerms("s-1", interval))
    renewer.start()
    time.sleep(interval * intervals)
    alive = renewer._thread.is_alive()
    renewer.stop()
    return renewer, alive


def test_one_momentary_contention_does_not_end_a_healthy_lease(table) -> None:
    """The repair, stated as the outcome rather than as the branch taken.

    `LEASE_TTL_MULTIPLE` already budgets the lease for one missed renewal, and
    before this the loop spent that budget on the first `SQLITE_BUSY` it saw:
    measured at **1 renewal of 12** with the thread dead and the lease 0.501s
    in the past, against a control of 12 of 12. The assertion that matters is
    the last one — the lease is *in the future* when the dust settles, which a
    stopped renewer cannot produce and which no message check would catch.
    """
    _start(table, "s-1", time.time())
    planted = _PlantedRenew(
        table, StoreBusyError("momentary contention"), fail_on=2)
    renewer, alive = _run_planted(table, planted)

    assert renewer.renewals >= 4, (
        f"only {renewer.renewals} renewals survived one momentary "
        f"SQLITE_BUSY, so the loop is still spending the whole lease budget "
        f"on contention that had already cleared: {renewer.stopped_because}"
    )
    assert alive, "the renewer thread died on a single momentary refusal"
    assert renewer.stopped_because is None
    row = table.get("s-1")
    assert row.lease_expires_at > time.time(), (
        "the lease is in the past, so renewal stopped even though the thread "
        "is alive and the session is still RUNNING"
    )


def test_contention_beyond_the_lease_budget_stops_renewal(table) -> None:
    """The bound, asserted as a count so it cannot drift silently.

    Tolerance is `TOLERATED_CONSECUTIVE_BUSY`, derived from
    `LEASE_TTL_MULTIPLE`. The loop must stop on the *first* failure past it and
    not on the second or the tenth, so this counts attempts rather than
    asserting merely that it eventually stopped — an unbounded `continue`
    would also eventually be interrupted by `stop()` and would pass a weaker
    check.
    """
    _start(table, "s-1", time.time())
    planted = _PlantedRenew(
        table, StoreBusyError("held lock"), fail_on=2, forever=True)
    renewer, alive = _run_planted(table, planted)

    # start() takes attempt 1 on the calling thread; the loop then tolerates
    # exactly TOLERATED_CONSECUTIVE_BUSY and stops on the one after.
    expected = 1 + TOLERATED_CONSECUTIVE_BUSY + 1
    assert planted.attempts == expected, (
        f"the table saw {planted.attempts} renewal attempts, expected "
        f"{expected}. Fewer means the tolerance is not being spent; more "
        f"means the loop is retrying past the budget the lease grants, which "
        f"is the unbounded retry T108 refused"
    )
    assert not alive, "the renewer thread outlived a lock it cannot wait out"
    assert renewer.stopped_because is not None
    assert renewer.stopped_because.startswith("StoreBusyError:")


def test_the_tolerance_is_consecutive_and_not_cumulative(table) -> None:
    """The counter reset, which is the difference between a budget and a quota.

    Without it, `consecutive_busy` counts every refusal a long-lived session
    ever saw, so a supervisor running for hours dies on the second momentary
    contention of its life — hours after the first, with the lease healthy the
    whole time in between. The arm above cannot see this: it plants one
    failure, and one is under the bound either way.
    """
    _start(table, "s-1", time.time())
    planted = _PlantedRenew(table, StoreBusyError("first"), fail_on=2)
    renewer = LeaseRenewer(planted, LeaseTerms("s-1", 0.05))
    renewer.start()
    time.sleep(0.20)
    # A second, separate contention several successful renewals later.
    planted._fail_on = planted.attempts + 2
    planted._exc = StoreBusyError("second, much later")
    time.sleep(0.25)
    alive = renewer._thread.is_alive()
    renewer.stop()

    assert alive and renewer.stopped_because is None, (
        f"the renewer died on the second non-consecutive contention, so the "
        f"tolerance is a lifetime quota rather than a budget the lease "
        f"renews: {renewer.stopped_because}"
    )
    assert table.get("s-1").lease_expires_at > time.time()


def test_a_wedged_store_stops_renewal_without_spending_the_budget(table) -> None:
    """The half that tells the split apart from tolerating every store error.

    `StoreWedgedError` means the busy handler ran to *exhaustion* — the lock
    outlived the whole timeout, so nothing healthy holds it and waiting longer
    is waiting for something that is not coming. A loop that split on
    `StoreUnavailableError`, the shared base, would tolerate this one too and
    would still pass the arm above; the attempt count is what separates them.
    """
    _start(table, "s-1", time.time())
    planted = _PlantedRenew(
        table, StoreWedgedError("lock outlived the busy timeout"), fail_on=2)
    renewer, alive = _run_planted(table, planted)

    assert planted.attempts == 2, (
        f"the table saw {planted.attempts} attempts; a wedged store is "
        f"tolerated for a while, so the split is on StoreUnavailableError "
        f"rather than on the busy case"
    )
    assert not alive
    assert renewer.stopped_because is not None
    assert renewer.stopped_because.startswith("StoreWedgedError:")


def test_terminate_requires_a_named_state(table) -> None:
    """FR-006 — a *member* of the taxonomy, which is stronger than non-empty.

    The empty string was the only case this asserted, and the check it asserted
    was `if not terminal_state`. That passed for `"OPERATOR_TERMINATED"`, which
    is not in the taxonomy at all — and the committed conformance fixture was
    seeded with exactly that string through this method. The namespaced case is
    the one that matters: a generic error wearing a plausible name is what
    FR-006 forbids, and a non-empty check cannot see it.
    """
    _start(table, "s-1", time.time())
    for invented in ("", "OPERATOR_TERMINATED", "terminated.error",
                     "terminated.something_someone_invented"):
        with pytest.raises(ValueError, match="taxonomy"):
            table.terminate("s-1", invented)
    assert table.get("s-1").state == "RUNNING", (
        "a refused terminal state still moved the row, so the session is "
        "terminated with a state FR-006 forbids and there is no way back"
    )
    assert table.terminate("s-1", "terminated.completed") == 1


# --- layer 2, the crash arm: SIGKILL from a separate process --------------

_SUPERVISOR = textwrap.dedent(
    """
    import os, sys, time
    sys.path.insert(0, {repo!r})
    from src.supervisor.lease import LeaseRenewer, LeaseTerms
    from src.supervisor.session_table import SessionTable

    table = SessionTable({db!r})
    renewer = LeaseRenewer(table, LeaseTerms({session!r}, {interval!r}))
    renewer.start()
    print("READY", flush=True)
    while True:
        time.sleep(0.05)
    """
)


@pytest.fixture()
def killer():
    """Kills a pid from a *separate* OS process. Finding 006's technique.

    Delivering the signal from inside the test process would still be a
    `SIGKILL`, but routing it through a third process removes any argument
    that the victim's runtime cooperated in its own death.
    """
    def kill(pid: int) -> None:
        subprocess.run(
            ["kill", "-KILL", str(pid)], check=True,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    return kill


def test_a_sigkilled_supervisor_lets_the_lease_lapse(tmp_path, killer) -> None:
    """**The requirement's hard clause.** Nothing renews, so it lapses.

    No cleanup path runs. Nothing revokes. The authority ends because the
    thing that was keeping it alive stopped, which is the only revocation
    mechanism that works when the revoker is what crashed.
    """
    db = tmp_path / "sessions.db"
    repo = str(Path(__file__).resolve().parent.parent.parent)
    now = time.time()
    with SessionTable(db) as table:
        capability = _start(table, "s-crash", now)

    child = subprocess.Popen(
        [sys.executable, "-c", _SUPERVISOR.format(
            repo=repo, db=str(db), session="s-crash", interval=INTERVAL)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    # The child never exits on its own — that is the point of it — so the kill
    # below is the only thing that ends it, and every assertion between here and
    # there is a way of not reaching the kill. Three of these outlived their run
    # by four days, renewing every 200ms against a basetemp whose pytest process
    # had long exited. `finally` is the sibling idiom: `test_resume_sigkill.py`,
    # `test_ceilings_under_resume.py` and `test_provider_state_resume.py` all
    # spawn the same shape and all wrap it.
    try:
        assert child.stdout is not None
        assert child.stdout.readline().strip() == "READY"

        # Renewal is live: the lease keeps moving forward.
        time.sleep(INTERVAL * 2)
        with SessionTable(db) as table:
            before = table.resolve(capability.digest)
        assert before is not None and before.honoured_at(time.time()), (
            "the lease was not being renewed before the kill, so the arm proves "
            "nothing about the kill"
        )
        assert before.state == STATE_RUNNING

        killer(child.pid)
        assert child.wait(timeout=10) == -signal.SIGKILL
    finally:
        if child.poll() is None:  # pragma: no cover — only on an assert above
            child.kill()

    # Nothing ran on the way down. The state is untouched — still RUNNING —
    # and the lease is the only thing standing between the handle and the
    # enforcement point.
    with SessionTable(db) as table:
        after = table.resolve(capability.digest)
    assert after is not None
    assert after.state == STATE_RUNNING, (
        "the session was marked terminated, so something ran during the "
        "SIGKILL and this arm is not testing the crash path"
    )

    lapse_at = after.lease_expires_at
    assert after.honoured_at(time.time()), "already lapsed; the window is real"

    deadline = lapse_at + 0.05
    while time.time() < deadline:
        time.sleep(0.02)
    assert not after.honoured_at(time.time()), (
        "the lease is still honoured after the supervisor died"
    )


def test_the_residual_window_is_bounded_by_the_configured_interval(
    tmp_path, killer
) -> None:
    """FR-050's disclosed gap, measured against its configured value.

    The window is `LEASE_TTL_MULTIPLE * interval`, and the value of `interval`
    is unvalidated under FR-043. The assertion is that the *mechanism* honours
    the configured value, not that the value is right — nothing here measures
    whether 5 seconds is a defensible default, and nothing should pretend to.
    """
    db = tmp_path / "sessions.db"
    now = time.time()
    with SessionTable(db) as table:
        capability = _start(table, "s-window", now)
        renewer = LeaseRenewer(table, LeaseTerms("s-window", INTERVAL))
        renewer.renew_once(now)
        row = table.resolve(capability.digest)

    assert row is not None
    window = row.lease_expires_at - now
    assert abs(window - INTERVAL * LEASE_TTL_MULTIPLE) < 0.01, (
        f"the residual window is {window:.3f}s, not the configured "
        f"{INTERVAL * LEASE_TTL_MULTIPLE:.3f}s"
    )


# --- layer 3: the kernel closes the path ----------------------------------

_HOLDER = textwrap.dedent(
    """
    import sys, time
    sys.path.insert(0, {repo!r})
    from src.supervisor.listener import SessionListener

    listener = SessionListener({session!r}, {directory!r})
    handle = listener.open()
    print("READY", handle.socket_path, flush=True)
    while True:
        time.sleep(0.05)
    """
)


def test_a_sigkilled_holder_closes_the_listener_instantly(tmp_path, killer) -> None:
    """Layer 3. The kernel performs the revocation; no cleanup is involved.

    This is what narrows layer 2's residual window from *every crash* to the
    narrow case where the supervisor survives but the session row was not
    updated.
    """
    repo = str(Path(__file__).resolve().parent.parent.parent)
    directory = tmp_path / "run"
    child = subprocess.Popen(
        [sys.executable, "-c", _HOLDER.format(
            repo=repo, session="s-listener", directory=str(directory))],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    # Same shape and the same reason as the arm above: `_HOLDER` is a
    # `while True`, so anything that stops this test short of the kill leaves it
    # running. This one holds an `AF_UNIX` socket rather than a lease, so a
    # survivor keeps a path bound that a later run's `is_reachable` would find.
    try:
        assert child.stdout is not None
        ready = child.stdout.readline().split()
        assert ready[0] == "READY"
        socket_path = ready[1]

        assert is_reachable(socket_path), "the listener never came up"

        killer(child.pid)
        assert child.wait(timeout=10) == -signal.SIGKILL
    finally:
        if child.poll() is None:  # pragma: no cover — only on an assert above
            child.kill()

    # No wait, no poll, no grace period. The descriptor closed with the
    # process, so the very next connection is refused.
    assert not is_reachable(socket_path), (
        "the socket still accepts connections after its holder was SIGKILLed"
    )
    assert os.path.exists(socket_path), (
        "the socket file was removed, which means a cleanup path ran — the "
        "arm is then testing unlink, not the descriptor closing"
    )


# --- the children these arms spawn, and a failure on the way to the kill ---
#
# The two arms above spawn a process that never exits on its own. Both now wrap
# the spawn in `try/finally`, and this is what makes that wrapping a mechanism
# rather than a habit: it drives the committed arm to fail *where it actually
# failed* and asks whether the child was gone by the time the test finished.
#
# "By the time the test finished" is the whole assertion. `tests/conftest.py`
# also sweeps unowned children, but it does so at session scope — so a run
# whose third test leaked a supervisor would still be clean at the end, having
# spent twelve hundred tests alongside a process writing to a store five times
# a second. `pytest_runtest_logfinish` is the earliest hook that fires after
# the test's own `finally`, which is exactly the boundary the wrapping moves.

#: What the crash arm's child looks like in `ps`. Its own argv, not a name this
#: file chose — and **not unique**, which is the whole reason both scans below
#: carry a second condition. It is an ordinary construction that ordinary source
#: may contain, and `ps -e` does not stop at a tree boundary, so on a host
#: running several checkouts at once this string alone names other people's
#: processes as readily as it names this run's. Finding 039 measured that: with
#: a decoy holding it alive the arm below failed 10 times out of 10 and SIGKILLed
#: the decoy 10 times out of 10. The marker says *what shape* to look for; the
#: scope beside it says *whose*.
_CRASH_CHILD_MARKER = "LeaseTerms('s-crash'"

_LEAK_OBSERVER = textwrap.dedent(
    '''
    """Fail the arm where its predecessor failed, then look for the child."""
    import os
    import subprocess

    MARKER = {marker!r}
    VERDICT = {verdict!r}


    def pytest_configure(config):
        # The historical failure reproduced at its own line. A concurrent run
        # had deleted this run's basetemp, so the row read back after the
        # spawn was simply not there and the arm stopped at
        # `assert before is not None` — between the spawn and the kill.
        from src.supervisor.session_table import SessionTable
        SessionTable.resolve = lambda self, digest: None


    def pytest_runtest_logfinish(nodeid, location):
        # Scoped to this process's own children, which is what
        # `tests/conftest.py` does for its own sweep and what this did not do.
        # Unscoped, a concurrent checkout's supervisor is reported as this
        # run's leak.
        #
        # Direct parentage and not a descendant walk, because the crash arm's
        # child is a direct child of this process — `Popen` from inside the
        # test function, no shell and no re-exec. That was measured rather
        # than read off the spawn, because the failure mode of guessing it is
        # a scan that finds nothing, writes DEAD, and passes over a mechanism
        # that never ran. The committed removal proof for this arm is what
        # keeps that honest: it requires this read to *find* a live child.
        mine = os.getpid()
        listing = subprocess.run(["ps", "-eo", "pid=,ppid=,state=,command="],
                                 capture_output=True, text=True).stdout
        alive = []
        for line in listing.splitlines():
            fields = line.split(maxsplit=3)
            if len(fields) != 4:
                continue
            try:
                parent = int(fields[1])
            except ValueError:
                continue
            # A killed child is a zombie until its parent reaps it, and a
            # zombie is not a process that is still renewing anything.
            if parent != mine or fields[2].startswith("Z"):
                continue
            if MARKER in fields[3]:
                alive.append(fields[3])
        with open(VERDICT, "w") as handle:
            handle.write("ALIVE" if alive else "DEAD")
    '''
)


def _kill_children_matching(marker: str, scope: str) -> list[str]:
    """Kill every live process carrying `marker` **and** `scope` in its argv.

    `scope` is the calling test's own `tmp_path`. The child carries it without
    being asked to: its store is created under the nested run's `--basetemp`,
    which is a directory inside that `tmp_path`, so the path is already in the
    argv `ps` reports. That makes the match this run's by construction rather
    than by the marker happening to be unique, which it is not.

    **Parentage is not the discriminator here, and a descendant walk would be
    vacuous.** By the time this runs the nested pytest has returned, so
    anything it left behind is an orphan reparented to init and has no
    ancestry left to test. On an ordinary run there is nothing here to find at
    all — the nested run's own `tests/conftest.py` sweep reaps the child
    before that process exits, which was measured. What is left for this to
    catch is the nested run that died without reaching its own sweep, and that
    is exactly the case where the ancestry is gone.
    """
    listing = subprocess.run(["ps", "-eo", "pid=,state=,command="],
                             capture_output=True, text=True).stdout
    killed = []
    for line in listing.splitlines():
        fields = line.split(maxsplit=2)
        if len(fields) < 3 or fields[1].startswith("Z"):
            continue
        if marker not in fields[2] or scope not in fields[2]:
            continue
        killed.append(fields[2])
        try:
            os.kill(int(fields[0]), signal.SIGKILL)
        except (OSError, ValueError):
            pass
    return killed


def test_the_crash_arms_child_does_not_outlive_a_failing_test(tmp_path) -> None:
    """The leak, planted rather than argued, and observed at the test boundary.

    Measured against this file without the `finally`: the arm fails, pytest
    reports one failure, and a supervisor renewing `s-crash` every 200ms is
    still running — reparented to init, holding its `sessions.db` open, and
    outliving the pytest process that started it by however long nobody looks.
    Three were found four days after the runs that made them.

    The nested run is the only vantage point from which this is observable. A
    check inside the arm itself would be asserting about a child the arm has
    just killed; what has to be shown is that the child is gone *after a run of
    the arm that did not reach the kill*, and there is no way to have both that
    failure and an assertion about it in one process.
    """
    root = Path(__file__).resolve().parents[2]
    plugin_dir = tmp_path / "plugin"
    plugin_dir.mkdir()
    verdict = tmp_path / "verdict.txt"
    (plugin_dir / "leakobserver.py").write_text(
        _LEAK_OBSERVER.format(marker=_CRASH_CHILD_MARKER, verdict=str(verdict)))

    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join([str(plugin_dir), str(root)])

    try:
        inner = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-p", "leakobserver",
             "--basetemp", str(tmp_path / "basetemp"),
             f"{Path(__file__).resolve()}::"
             "test_a_sigkilled_supervisor_lets_the_lease_lapse"],
            capture_output=True, text=True, timeout=180,
            cwd=str(root), env=environment,
        )

        assert inner.returncode != 0, (
            "the planted arm passed, so this run never reached the window "
            f"between the spawn and the kill and proves nothing:\n"
            f"{inner.stdout[-2000:]}"
        )
        assert verdict.exists(), (
            "the observer never wrote a verdict, so the nested run did not "
            f"reach a test boundary:\n{inner.stdout[-2000:]}\n{inner.stderr[-2000:]}"
        )
        assert verdict.read_text() == "DEAD", (
            "the crash arm's supervisor was still running when the test that "
            "spawned it finished. It renews a lease every 200ms and never "
            "exits on its own, so nothing that happens later in this run — or "
            "in any run — will end it."
        )
    finally:
        # Unconditional and silent. On the tampered run the child *is* alive,
        # and an assertion here would replace the one above — which names what
        # went wrong — with one that only says it happened.
        #
        # `tmp_path` is the scope: the nested run's basetemp is inside it, so
        # this run's child carries it and nobody else's does.
        _kill_children_matching(_CRASH_CHILD_MARKER, str(tmp_path))


# --- the two scans, scoped, and both halves of each ------------------------
#
# The marker above is a construction ordinary source contains, and `ps -e` does
# not stop at a tree boundary, so before these arms both scans reached every
# checkout on the host. Finding 039 established that by planting: with a decoy
# holding the marker alive the arm above failed **10 of 10**, and its `finally`
# **SIGKILLed the decoy 10 of 10**. The read half hands another pass a false
# red; the kill half kills that pass's supervisor.
#
# **Each scan gets both arms, and the second is the one that matters.** A scope
# that excludes other people's processes by excluding everything is not a
# repair — it makes the read report DEAD over a live child and the kill reap
# nothing, which is a green over a mechanism that never ran. So every negative
# arm below is paired with a positive one that requires the scan to still find
# its own, and neither is worth anything without the other.
#
# The two scans are scoped on *different* things, because they run at different
# vantage points and the answer is not the same at both:
#
#   read half  runs inside the nested pytest while that process is alive, and
#              the child is a direct child of it — measured, not assumed — so
#              `ppid == mine` is available and is what `tests/conftest.py`
#              already uses.
#   kill half  runs in this process after the nested pytest has returned, so
#              anything left is an orphan with no ancestry to test. It is
#              scoped on `tmp_path`, which the child carries in its argv.

#: A process holding the marker in its argv and nothing else. The comment is
#: the payload: it puts the marker in the command line `ps` reports without the
#: process importing anything from `src/`, which is what a *concurrent
#: checkout's* supervisor looks like from here.
_DECOY = "import time  # {marker}, decoy)\nwhile True: time.sleep(0.05)\n"


def _is_running(pid: int) -> bool:
    """Alive and not a zombie. Absent from `ps` entirely reads as gone."""
    state = subprocess.run(["ps", "-o", "state=", "-p", str(pid)],
                           capture_output=True, text=True).stdout.strip()
    return bool(state) and not state.startswith("Z")


def _spawn_decoy(code: str) -> int:
    """Start a marker-bearing process that is **not** a child of this one.

    A direct child would be excluded by the read half's scope for the wrong
    reason and would be swept by `tests/conftest.py` at the end of the run. The
    launcher exits immediately, so the decoy is reparented to init — which is
    exactly what another checkout's supervisor looks like from this process.
    """
    # The decoy's own streams go to `/dev/null`. Inheriting the launcher's
    # captured pipe would keep its write end open after the launcher exits, so
    # the `subprocess.run` below would wait for EOF from a process written
    # never to end and time out instead of returning a pid.
    launcher = (
        "import subprocess, sys\n"
        f"child = subprocess.Popen([sys.executable, '-c', {code!r}],\n"
        "    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,\n"
        "    stdin=subprocess.DEVNULL)\n"
        "print(child.pid, flush=True)\n"
    )
    started = subprocess.run([sys.executable, "-c", launcher],
                             capture_output=True, text=True, timeout=30)
    assert started.returncode == 0, f"the decoy launcher failed: {started.stderr}"
    pid = int(started.stdout.strip())
    deadline = time.time() + 10
    while time.time() < deadline and not _is_running(pid):
        time.sleep(0.01)
    assert _is_running(pid), (
        f"the decoy ({pid}) never came up, so any arm about it is vacuous")
    return pid


def _reap(pid: int) -> None:
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass


def _observer_verdict(tmp_path: Path) -> str:
    """Run the real observer's hook here and return what it wrote.

    The template is rendered and executed rather than reimplemented, so these
    arms are about the text that actually ships to the nested run. Only
    `pytest_runtest_logfinish` is called: `pytest_configure` monkeypatches
    `SessionTable.resolve` for the whole process and belongs to the nested run
    alone.
    """
    verdict = tmp_path / "observer-verdict.txt"
    namespace: dict = {}
    exec(_LEAK_OBSERVER.format(marker=_CRASH_CHILD_MARKER,
                               verdict=str(verdict)), namespace)
    namespace["pytest_runtest_logfinish"]("nodeid", "location")
    return verdict.read_text()


def test_the_leak_read_ignores_another_runs_supervisor(tmp_path) -> None:
    """The read half's negative arm — the false red, planted.

    Unscoped, this is the failure finding 039 reproduced 10 times in 10: a
    marker-bearing process belonging to *somebody else's* checkout is reported
    as this run's leaked child, and the arm above fails with
    `assert 'ALIVE' == 'DEAD'` over a run that leaked nothing.
    """
    decoy = _spawn_decoy(_DECOY.format(marker=_CRASH_CHILD_MARKER))
    try:
        assert _observer_verdict(tmp_path) == "DEAD", (
            f"the observer reported a live marker-bearing process ({decoy}) "
            "that is not this process's child as this run's leaked child. "
            "That is a red handed to whichever pass happens to be running "
            "beside this one, for a leak that did not happen"
        )
    finally:
        _reap(decoy)


def test_the_leak_read_still_finds_its_own_supervisor(tmp_path) -> None:
    """The read half's positive arm, **without which the one above is free.**

    A scope tight enough to find nothing satisfies the arm above and reports
    `DEAD` over a child that is still running — the vacuous green this
    repository keeps having to undo. This requires the scan to still see its
    own, so the two arms together pin the scope from both sides.
    """
    child = subprocess.Popen(
        [sys.executable, "-c", _DECOY.format(marker=_CRASH_CHILD_MARKER)])
    try:
        deadline = time.time() + 10
        while time.time() < deadline and not _is_running(child.pid):
            time.sleep(0.01)
        assert _is_running(child.pid), (
            f"the child ({child.pid}) never came up, so this arm is vacuous")

        assert _observer_verdict(tmp_path) == "ALIVE", (
            f"the observer did not see its own live child ({child.pid}). The "
            "scope excludes the thing it exists to find, so the nested run "
            "would report DEAD over a supervisor that is still renewing a "
            "lease — a pass over a mechanism that never ran"
        )
    finally:
        child.kill()
        child.wait(timeout=10)


def test_the_kill_leaves_another_runs_supervisor_alone(tmp_path) -> None:
    """The kill half's negative arm — **the destructive one.**

    This is the half that does damage rather than reporting it. Unscoped, the
    `finally` above SIGKILLs every marker-bearing process on the host, which
    finding 039 measured at 10 decoys killed in 10 trials. The victim is
    another pass's supervisor child, and that pass then sees a crash it did
    not cause.
    """
    decoy = _spawn_decoy(_DECOY.format(marker=_CRASH_CHILD_MARKER))
    try:
        killed = _kill_children_matching(_CRASH_CHILD_MARKER, str(tmp_path))

        assert not any(str(decoy) in line or "decoy" in line
                       for line in killed), (
            f"the sweep reported killing the decoy ({decoy}): {killed}")
        time.sleep(0.10)
        assert _is_running(decoy), (
            f"the decoy ({decoy}) was SIGKILLed. It carries the marker and "
            "nothing of this run, so it stands for a concurrent checkout's "
            "supervisor — and killing it is this test reaching outside its "
            "own run to end somebody else's process"
        )
    finally:
        _reap(decoy)


def test_the_kill_still_reaps_its_own_supervisor(tmp_path) -> None:
    """The kill half's positive arm, and the reason the scope is a path.

    Scoping the kill by parentage would pass the arm above and reap nothing
    ever: by the time the `finally` runs the nested pytest has returned, so
    what it left is an orphan. The scope is therefore the one thing the child
    carries that is this run's — `tmp_path`, which its store sits under — and
    this arm is what stops that from being a string nothing matches.
    """
    mine = _spawn_decoy(
        f"import time  # SessionTable('{tmp_path}/basetemp/x/sessions.db')\n"
        f"# {_CRASH_CHILD_MARKER}, 0.2)\n"
        "while True: time.sleep(0.05)\n")
    try:
        killed = _kill_children_matching(_CRASH_CHILD_MARKER, str(tmp_path))

        assert killed, (
            "the sweep found nothing to kill against a process carrying both "
            f"the marker and this run's tmp_path ({tmp_path}). The scope "
            "matches nothing the child actually has, so the sweep is switched "
            "off and says so nowhere"
        )
        deadline = time.time() + 10
        while time.time() < deadline and _is_running(mine):
            time.sleep(0.02)
        assert not _is_running(mine), (
            f"the sweep named {mine} and left it running, so the `finally` "
            "describes a leak rather than ending one"
        )
    finally:
        _reap(mine)


# --- SC-024: the replay fixture, both arms --------------------------------

def test_replay_from_a_later_session_is_denied_and_recorded(table) -> None:
    """Arm one. The handle resolves, and the row says no."""
    now = time.time()
    captured = _start(table, "s-first", now)
    table.terminate("s-first", "terminated.completed")

    _start(table, "s-second", now)

    row = table.resolve(captured.digest)
    assert row is not None, "the handle no longer resolves, so nothing records"
    assert not row.honoured_at(now), "a replayed handle was honoured"
    assert row.terminal_state == "terminated.completed"
    assert row.session_id == "s-first", (
        "the replayed handle resolved to the *current* session, which would "
        "hand the second session's authority to the first session's handle"
    )


def test_replay_with_no_path_to_the_enforcement_point_is_unreachable(
    tmp_path,
) -> None:
    """Arm two. Refused by unreachability, recorded only as a drop.

    Nothing receives the connection, so nothing can record a denial with a
    rule identifier. That asymmetry is the finding, not a gap: the two arms
    produce different evidence and SC-024 asks for both.
    """
    listener = SessionListener("s-live", tmp_path / "run")
    handle = listener.open()
    assert is_reachable(handle.socket_path)
    listener.close()

    # A later session's environment has no such socket in its namespace at
    # all — the path does not exist, which is FR-048's absence again.
    assert not is_reachable(handle.socket_path)
    assert not os.path.exists(handle.socket_path)


# --- the removal proof ----------------------------------------------------

def test_without_the_lease_check_a_dead_sessions_handle_is_honoured(table) -> None:
    """**The removal proof.** Resolve the handle without checking the lease.

    Every arm above would pass if `honoured_at` were the only caller of the
    lease and the proxy checked something else. This asserts that the *state*
    alone is not sufficient: after a crash the row still says `RUNNING`, and a
    resolver that stopped at the state would honour a dead session's handle.
    """
    now = time.time()
    capability = _start(table, "s-1", now)
    later = now + INTERVAL * LEASE_TTL_MULTIPLE + 1.0

    row = table.resolve(capability.digest)
    assert row is not None
    assert row.state == STATE_RUNNING, (
        "the crashed session's row does not say RUNNING, so a state-only "
        "check would already refuse and this proof is vacuous"
    )
    assert not row.honoured_at(later), "the lease check did not refuse"
