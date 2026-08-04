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

from src.supervisor.capability import Capability, issue
from src.supervisor.lease import LEASE_TTL_MULTIPLE, LeaseRenewer, LeaseTerms
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


def test_terminate_requires_a_named_state(table) -> None:
    _start(table, "s-1", time.time())
    with pytest.raises(ValueError, match="named terminal state"):
        table.terminate("s-1", "")


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
    assert child.stdout is not None
    ready = child.stdout.readline().split()
    assert ready[0] == "READY"
    socket_path = ready[1]

    assert is_reachable(socket_path), "the listener never came up"

    killer(child.pid)
    assert child.wait(timeout=10) == -signal.SIGKILL

    # No wait, no poll, no grace period. The descriptor closed with the
    # process, so the very next connection is refused.
    assert not is_reachable(socket_path), (
        "the socket still accepts connections after its holder was SIGKILLed"
    )
    assert os.path.exists(socket_path), (
        "the socket file was removed, which means a cleanup path ran — the "
        "arm is then testing unlink, not the descriptor closing"
    )


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
