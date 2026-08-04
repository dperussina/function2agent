"""T101 / **Q-09** — measure the syscall supervisor's overhead **before the
mechanism is committed**.

Q-09 was accepted *with* the measurement, not with a prediction of its result.
The recorded fallback, if the overhead is prohibitive, is an audit channel that
keeps SC-022 and loses the before-execution property. This file produces the
number that decides.

**What the number is a property of, stated first because it is the part that
transfers least.** Every figure here is a property of:

  - Docker Desktop's `linuxkit` VM on this host — **not a bare Linux host**.
    Syscall cost inside a virtualized kernel is not the syscall cost on metal,
    and syscall *interception* cost is the thing most sensitive to that.
  - The host's architecture, kernel version and core count, all recorded in
    the result file rather than described here.
  - A **CPython** supervisor answering notifications with `fcntl.ioctl` and a
    `/proc/<pid>/mem` read per attempt. A Go or C supervisor would be faster;
    how much faster is not measured and is not guessed at.
  - The specific workloads below, which are proxies for "shell-heavy" and are
    not the reference application. **T101 asks for the reference application
    and this is not it** — recorded as an outstanding obligation, not as a
    substitution.

This corpus has been burned by exactly this class of error: a measured 1.0000
precision that turned out to be a property of the target rather than of the
mechanism. So the compute-only arm exists specifically to show that the
overhead is attributable to syscall interception — if it moved too, the number
would be measuring the VM's scheduler and nothing else.

Run:
    docker run --rm --privileged -v "$PWD:/work" -w /work f2a-dev \\
        python -m pytest tests/batteries/test_seccomp_overhead.py -s -v
"""

from __future__ import annotations

import json
import os
import platform
import statistics
import sys
import textwrap
import time
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.linux_only,
    pytest.mark.privileged,
    pytest.mark.skipif(sys.platform != "linux", reason="OD-17: Linux only"),
]

from src.supervisor import _linux, seccomp  # noqa: E402

RESULTS = Path(__file__).resolve().parent / "results"
REPEATS = 5

# --- the workloads --------------------------------------------------------

# Shell-heavy: process spawn plus the path resolution every exec performs. This
# is the arm Q-09 names, because an agent that composes shell commands pays
# this cost on every one of them.
SHELL_HEAVY = textwrap.dedent(
    """
    import subprocess
    for _ in range(30):
        subprocess.run(['/bin/sh', '-c', 'true'], check=True)
    """
)

# Path-heavy without exec: isolates the per-notification cost from the cost of
# spawning a process, which the shell arm conflates.
PATH_HEAVY = textwrap.dedent(
    """
    import os
    for i in range(2000):
        try:
            os.stat('/etc/hostname')
        except OSError:
            pass
    """
)

# Compute-only: the control. Takes no paths, so the filter never fires. If this
# arm slows down, the numbers above are measuring something other than
# interception.
COMPUTE_ONLY = textwrap.dedent(
    """
    total = 0
    for i in range(4_000_000):
        total += i
    """
)


def _run_plain(source: str) -> float:
    started = time.perf_counter()
    pid = os.fork()
    if pid == 0:
        try:
            exec(compile(source, "<workload>", "exec"), {"__name__": "__main__"})
        finally:
            os._exit(0)
    os.waitpid(pid, 0)
    return time.perf_counter() - started


def _run_supervised(source: str) -> tuple[float, int]:
    observed = 0

    def count(_attempt: seccomp.Attempt) -> None:
        nonlocal observed
        observed += 1

    argv = [sys.executable, "-c", source]
    started = time.perf_counter()
    pid, listener = seccomp.spawn_with_listener(argv, count)
    os.waitpid(pid, 0)
    elapsed = time.perf_counter() - started
    time.sleep(0.05)
    listener.stop()
    return elapsed, listener.observed


def _run_unsupervised_subprocess(source: str) -> float:
    """The honest baseline for the supervised arm: same `execve`, no filter."""
    argv = [sys.executable, "-c", source]
    started = time.perf_counter()
    pid = os.fork()
    if pid == 0:
        os.execv(argv[0], argv)
    os.waitpid(pid, 0)
    return time.perf_counter() - started


def _median(fn, *args) -> float:
    return statistics.median(fn(*args) for _ in range(REPEATS))


@pytest.fixture(scope="module")
def measurement() -> dict:
    arms = {}
    for name, source in (
        ("shell_heavy", SHELL_HEAVY),
        ("path_heavy", PATH_HEAVY),
        ("compute_only", COMPUTE_ONLY),
    ):
        baseline = _median(_run_unsupervised_subprocess, source)
        supervised_samples = [_run_supervised(source) for _ in range(REPEATS)]
        supervised = statistics.median(t for t, _ in supervised_samples)
        observed = statistics.median(n for _, n in supervised_samples)
        arms[name] = {
            "baseline_seconds": round(baseline, 6),
            "supervised_seconds": round(supervised, 6),
            "ratio": round(supervised / baseline, 4) if baseline else None,
            "overhead_seconds": round(supervised - baseline, 6),
            "notifications_observed": observed,
            "microseconds_per_notification": (
                round((supervised - baseline) / observed * 1e6, 2)
                if observed else None
            ),
        }

    record = {
        "question": "Q-09",
        "task": "T101",
        "measured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "repeats_per_arm": REPEATS,
        "arms": arms,
        "environment": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "kernel": platform.release(),
            "python": sys.version.split()[0],
            "cpu_count": os.cpu_count(),
            "audit_arch": hex(_linux.audit_arch()),
            "watched_syscalls": sorted(_linux.path_taking_syscalls()),
        },
        "what_this_is_a_property_of": [
            "Docker Desktop's linuxkit VM on this host, not a bare Linux host. "
            "Syscall-interception overhead is the measurement most sensitive "
            "to that difference and it may not transfer.",
            "A CPython supervisor doing one ioctl and one /proc/<pid>/mem read "
            "per notification. A Go or C supervisor would be faster by an "
            "unmeasured amount.",
            "These three workloads, which are proxies for 'shell-heavy'. T101 "
            "asks for the measurement on the reference application; the "
            "reference application does not exist yet, so that part of T101 "
            "is OUTSTANDING and this does not discharge it.",
            "SECCOMP_USER_NOTIF_FLAG_CONTINUE as the response. A supervisor "
            "that denied or rewrote arguments would pay more.",
        ],
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(record, indent=2, sort_keys=True) + "\n"

    # The committed record is Q-09's *recorded* measurement. Overwriting it on
    # every privileged run replaced a deliberate figure with whichever run
    # happened last — so a reviewer could not tell an intentional
    # re-measurement from a suite that ran in CI, and a real regression would
    # arrive as ordinary run-to-run noise in a file nobody reads twice.
    # Re-recording is now something you ask for.
    if os.environ.get("F2A_RECORD_MEASUREMENTS") == "1":
        (RESULTS / "seccomp-overhead.json").write_text(serialized)
    else:
        (RESULTS / "seccomp-overhead.latest.json").write_text(serialized)
    return record


def test_the_measurement_is_recorded(measurement) -> None:
    path = RESULTS / "seccomp-overhead.json"
    assert path.is_file()
    print("\n" + json.dumps(measurement["arms"], indent=2))
    print("\nenvironment: " + json.dumps(measurement["environment"], indent=2))


def test_the_filter_actually_fired_so_the_numbers_mean_something(
    measurement,
) -> None:
    """A measured overhead of zero because nothing was intercepted is not a
    measurement of the mechanism."""
    assert measurement["arms"]["path_heavy"]["notifications_observed"] > 1000
    assert measurement["arms"]["shell_heavy"]["notifications_observed"] > 100


def test_the_compute_control_shows_the_overhead_is_attributable(
    measurement,
) -> None:
    """The control arm. Takes no paths, so the filter never fires.

    If this moved with the others, every number here would be a property of
    the VM's scheduler rather than of interception, and the corpus has made
    that mistake before.
    """
    control = measurement["arms"]["compute_only"]
    assert control["notifications_observed"] < 200, (
        f"the compute-only arm triggered {control['notifications_observed']} "
        "notifications; it is not a control"
    )
    path_ratio = measurement["arms"]["path_heavy"]["ratio"]
    assert path_ratio > control["ratio"], (
        f"the path-heavy arm ({path_ratio}x) is not slower than the "
        f"compute-only control ({control['ratio']}x), so the overhead is not "
        "attributable to syscall interception"
    )


def test_overhead_is_reported_not_asserted_against_a_threshold(
    measurement,
) -> None:
    """Q-09 owes a figure, not a pass mark.

    There is no threshold here on purpose. Inventing one would be exactly the
    unvalidated number FR-043 exists to prevent, and the decision Q-09 records
    — commit the mechanism, or fall back to an audit channel — is the owner's
    to make against the recorded figure.
    """
    for name, arm in measurement["arms"].items():
        assert arm["ratio"] is not None, f"{name} produced no ratio"
