"""The human-facing channel: what it writes, and that it cannot abort a process.

The second half is the point. `OperatorLog` exists because
`src/supervisor/lease.py`'s terminal branch re-raises on a daemon thread, and a
daemon thread reporting through a *buffered* stream while the main thread
finalizes the interpreter takes the whole process down with
`_enter_buffered_busy` and SIGABRT. That is a measured crash and the tests below
plant it rather than cite it: `test_the_stock_hook_can_abort_the_process` is
expected to *observe the fault*, and `test_the_adopted_hook_does_not_abort` is
the same plant with the fix installed. A pair, because a regression test for a
fix whose fault nothing reproduces is a test that would pass with the fix
deleted.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
import threading

import pytest

from src.contracts.operator_log import EXIT_STARTUP_REFUSED, OperatorLog

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

#: Trials per arm of the abort plant. Small because each is a process; the
#: forced-overlap design is what makes a small number informative — the sweep
#: design needed 87 to see 4 aborts, and this one sees them in the majority of
#: trials. The module docstring of `src/contracts/operator_log.py` carries the
#: 120-trial run this is the standing residue of.
TRIALS = 12


def read(fd_pair) -> str:
    read_fd, write_fd = fd_pair
    os.close(write_fd)
    with os.fdopen(read_fd, "r", encoding="utf-8") as handle:
        return handle.read()


@pytest.fixture
def channel():
    """A log writing into a pipe, and the pipe's reading end."""
    read_fd, write_fd = os.pipe()
    yield OperatorLog("test", fd=write_fd, clock=lambda: 0.0), (read_fd, write_fd)


def test_a_message_is_stamped_and_named(channel) -> None:
    log, fds = channel
    log.say("ready")
    assert read(fds) == "1970-01-01T00:00:00Z test: ready\n"


def test_every_line_of_a_multi_line_report_is_prefixed(channel) -> None:
    """The configuration report runs to twelve keys and their reasons. A prefix
    only on its head would make every line but one ungreppable, and an operator
    tailing two processes could not tell whose report they were reading."""
    log, fds = channel
    log.say("one\ntwo\nthree")
    lines = read(fds).splitlines()
    assert len(lines) == 3
    assert all(line.startswith("1970-01-01T00:00:00Z test: ") for line in lines)


def test_a_report_larger_than_one_write_arrives_whole(channel) -> None:
    """A report far larger than a pipe's buffer arrives entire.

    A property of the channel, not a proof of the resumption loop — see
    `OperatorLog.say`: fd 2 is blocking, so the kernel does not return short
    and the loop does not iterate here. What this does establish is that a
    kilobyte-scale configuration report survives the trip, which is the
    message the channel exists for.
    """
    log, (read_fd, write_fd) = channel
    body = "\n".join(f"line {i}" for i in range(20_000))
    expected = len("\n".join(f"1970-01-01T00:00:00Z test: line {i}"
                             for i in range(20_000))) + 1
    assert expected > 64 * 1024, "the message is small enough to fit one write"

    thread = threading.Thread(target=log.say, args=(body,), daemon=True)
    thread.start()
    chunks = []
    got = 0
    while got < expected:
        chunk = os.read(read_fd, 1 << 16)
        if not chunk:
            break
        chunks.append(chunk)
        got += len(chunk)
    thread.join(timeout=10)
    os.close(write_fd)
    os.close(read_fd)

    lines = b"".join(chunks).decode().splitlines()
    assert len(lines) == 20_000
    assert lines[-1] == "1970-01-01T00:00:00Z test: line 19999"


def test_refuse_reports_the_reason_and_exits_nonzero(channel) -> None:
    log, fds = channel
    with pytest.raises(SystemExit) as caught:
        log.refuse("SANDBOX_MEMORY_MAX is unset")
    assert caught.value.code == EXIT_STARTUP_REFUSED != 0
    text = read(fds)
    assert "startup refused: SANDBOX_MEMORY_MAX is unset" in text


def test_a_secret_interpolated_into_a_message_is_redacted(channel) -> None:
    """Relied on rather than restated: `Secret.__str__` yields the marker, so
    the channel is safe by construction rather than by review. Asserted here
    because the property is what licences having no redaction step."""
    from src.contracts.secret import Secret

    log, fds = channel
    log.say(f"upstream key {Secret('sk-live-abcdef', name='UPSTREAM_KEY')}")
    text = read(fds)
    assert "sk-live-abcdef" not in text
    assert "<redacted:Secret UPSTREAM_KEY>" in text


def test_a_thread_dying_reports_through_the_channel(channel) -> None:
    log, fds = channel
    log, _ = channel
    stock = threading.excepthook
    try:
        log.adopt_thread_exceptions()

        def die() -> None:
            raise ValueError("the store is wedged")

        thread = threading.Thread(target=die, name="lease-s1", daemon=True)
        thread.start()
        thread.join(timeout=10)
    finally:
        threading.excepthook = stock
    text = read(fds)
    assert "thread 'lease-s1' died and was not restarted" in text
    assert "ValueError: the store is wedged" in text


def test_a_thread_calling_sys_exit_is_named_as_such(channel) -> None:
    """`SystemExit` on a non-main thread stops that thread and nothing else.
    The stock hook is silent about it, which is how a renewer that thought it
    was stopping the process ends up having stopped only itself."""
    log, fds = channel
    stock = threading.excepthook
    try:
        log.adopt_thread_exceptions()
        thread = threading.Thread(target=sys.exit, args=(3,), name="quitter",
                                  daemon=True)
        thread.start()
        thread.join(timeout=10)
    finally:
        threading.excepthook = stock
    assert "A thread cannot stop this process that way" in read(fds)


# ---------------------------------------------------------------------------
# The plant. A daemon thread reporting in a tight loop while the main thread
# exits shortly after, which forces the overlap rather than sweeping for it.
#
# **This module deliberately crashes a process, and the cost is bounded on
# purpose.** macOS runs a crash reporter per SIGABRT, which is slow and runs
# *after* the child is reaped, so a dozen of them saturate the host while the
# rest of the suite is still going. That is not hypothetical: one removal-proof
# run took a baseline in which 116 outcomes were failing — the harness scored
# nothing and reported 20 arms UNUSABLE, which is its guard working — and a
# re-run was clean. So the control below stops at its **first** abort, which
# makes exactly one per suite run, and the two arms that assert *zero* are the
# only ones that run to `TRIALS`. Do not remove the early exit to "get a better
# rate"; the rate is recorded in `src/contracts/operator_log.py` and this is
# the standing regression, not the measurement.
# ---------------------------------------------------------------------------

_PLANT = textwrap.dedent(
    """
    import os, sys, threading, time
    sys.path.insert(0, {repo!r})
    from src.contracts.operator_log import OperatorLog

    log = OperatorLog("plant", fd=2)
    vehicle = {vehicle!r}
    if vehicle == "raise-adopted":
        log.adopt_thread_exceptions()

    def report():
        if vehicle == "buffered":
            sys.stderr.write("the store is wedged\\n")
            sys.stderr.flush()
        elif vehicle == "unbuffered":
            log.say("the store is wedged")
        else:
            raise RuntimeError("the store is wedged")

    def loop():
        while True:
            report()

    for _ in range(24):
        threading.Thread(target=loop, daemon=True).start()
    time.sleep(0.02)
    """
)

#: `subprocess` reports SIGABRT as -6; a shell reports 134. Both are the same
#: `Fatal Python error: _enter_buffered_busy`.
ABORTED = (-6, 134)


def _aborts(vehicle: str, *, stop_on_abort: bool = False) -> tuple[int, list[int]]:
    """Run the plant `TRIALS` times and count the aborts.

    `stop_on_abort` is for the control, and it is a runtime economy rather than
    a weakening: the control's claim is *this plant can produce the fault*, for
    which one occurrence is the whole of the evidence. An abort costs about two
    seconds on macOS because the crash reporter runs, so twelve of them would
    put half a minute onto every suite run to re-establish a rate that is
    already recorded.
    """
    codes: list[int] = []
    for _ in range(TRIALS):
        done = subprocess.run(
            [sys.executable, "-c", _PLANT.format(repo=REPO, vehicle=vehicle)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60,
        )
        codes.append(done.returncode)
        if stop_on_abort and done.returncode in ABORTED:
            break
    return sum(1 for code in codes if code in ABORTED), codes


def test_a_buffered_write_from_a_daemon_thread_aborts_the_process() -> None:
    """The fault, observed. This is a **control**, not a regression test.

    Without it the arm below is unfalsifiable: a plant that could not produce
    the crash would report zero aborts with the fix deleted, and an assertion
    that passes for the wrong reason proves nothing. The two arms differ in
    exactly one thing — the call the daemon thread makes to report — so a
    difference between them is attributable to the vehicle and to nothing else.

    Recorded at 38 of 40 on CPython 3.12.11 / macOS 26.2 arm64. Asserted as
    `> 0` because the rate belongs to the host's scheduler, and skipped rather
    than passed if the host does not reproduce it, because a control that did
    not fire has not licensed the arm below.
    """
    aborts, codes = _aborts("buffered", stop_on_abort=True)
    if aborts == 0:
        pytest.skip(
            f"this host did not reproduce `_enter_buffered_busy` in {TRIALS} "
            f"trials (exit codes {sorted(set(codes))}). The unbuffered arm is "
            "therefore not evidence on this run, and this says so rather than "
            "passing quietly."
        )
    assert aborts > 0


def test_an_unbuffered_write_from_a_daemon_thread_does_not() -> None:
    """The same plant, the same threads, the same timing — `os.write`."""
    aborts, codes = _aborts("unbuffered")
    assert aborts == 0, (
        f"{aborts} of {TRIALS} trials aborted while writing through "
        f"`OperatorLog.say` (exit codes {sorted(set(codes))}). The single "
        "unbuffered write is the whole of what stands between a daemon "
        "thread's report and SIGABRT, and it has stopped standing."
    )


def test_the_adopted_thread_hook_does_not_abort() -> None:
    """The lease renewer's own shape: the daemon thread *raises*, and delivery
    is `threading.excepthook`'s.

    The stock hook aborts here too — 7 of 120 in the recorded run, an order of
    magnitude rarer than a direct buffered write because the hook does more
    work before it reaches the stream. Twelve trials cannot see a 6% event
    reliably, so that comparison is not asserted per-run; the control above
    carries the falsifiability and this arm carries the property that matters,
    which is that `src/supervisor/lease.py`'s `raise` can no longer take the
    process down.
    """
    aborts, codes = _aborts("raise-adopted")
    assert aborts == 0, (
        f"{aborts} of {TRIALS} trials aborted with `adopt_thread_exceptions()` "
        f"installed (exit codes {sorted(set(codes))}). The renewer's terminal "
        "branch has lost the vehicle lease.py's note says it has."
    )
