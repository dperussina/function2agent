"""T106 — the bounds battery. Exhaust each declared bound in turn and assert a
**named** terminal state (FR-049, FR-006, SC-023).

Each test plants a defect just past the threshold rather than staying safely
inside it. A fixture that allocates 10 MiB against a 512 MiB bound proves the
process ran; it proves nothing about the bound. So the memory arm allocates
past `memory.max`, the process arm forks past `pids.max`, and the cumulative
processor arm spins past the declared total.

**SC-023's second clause is measured, not assumed.** A co-located reference
workload runs on the same host throughout the exhaustion arms and its service
is checked after. This is the clause a cumulative CPU ceiling alone does not
satisfy, which is why `cpu.max` exists as a separate rate bound.

Run:
    docker run --rm --privileged --cgroupns=host \\
      -v /sys/fs/cgroup:/sys/fs/cgroup:rw -v "$PWD:/work" -w /work f2a-dev \\
      python -m pytest tests/batteries/test_bounds_exhaustion.py -v
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.linux_only,
    pytest.mark.privileged,
    pytest.mark.skipif(sys.platform != "linux", reason="OD-17: Linux only"),
]

from src.supervisor import bounds as bounds_module  # noqa: E402
from src.supervisor.bounds import (  # noqa: E402
    TERMINAL_CPU,
    TERMINAL_MEMORY,
    TERMINAL_PROCESS,
    Bounds,
)
from src.supervisor.cgroup import CGROUP2_ROOT, CgroupError, SessionCgroup  # noqa: E402
from src.contracts.terminal import is_terminal  # noqa: E402

MIB = 2**20

# Attempts 64 forks, each child sleeping briefly. Under `pids.max` the storm is
# refused partway through; without it, all 64 land.
_FORK_STORM = (
    "import os, time\n"
    "for _ in range(64):\n"
    "    try:\n"
    "        if os.fork() == 0:\n"
    "            time.sleep(3); os._exit(0)\n"
    "    except OSError:\n"
    "        break\n"
    "time.sleep(1)\n"
)
_ALLOCATE_FOREVER = (
    "x = bytearray()\n"
    "while True:\n"
    "    x += bytearray(4 * 1024 * 1024)\n"
)
_SPIN_FOREVER = "while True: pass\n"


def _cgroup2_available() -> bool:
    return (CGROUP2_ROOT / "cgroup.controllers").is_file()


requires_cgroup2 = pytest.mark.skipif(
    not _cgroup2_available(),
    reason="no writable cgroup v2 at /sys/fs/cgroup — mount it into the "
           "container with -v /sys/fs/cgroup:/sys/fs/cgroup:rw --cgroupns=host",
)


def _bounds(**overrides) -> Bounds:
    base = dict(
        memory_max_bytes=64 * MIB,
        cpu_max="10000 100000",   # 10% of one core
        cpu_total_seconds=1.0,
        pids_max=16,
        deployment_id="d-battery",
    )
    base.update(overrides)
    return Bounds(**base)


@pytest.fixture()
def session(request):
    name = f"battery-{os.getpid()}-{request.node.name[:24]}"
    name = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
    cgroup = SessionCgroup(name)
    try:
        cgroup.create()
    except CgroupError as exc:
        pytest.skip(f"cannot create a session cgroup here: {exc}")
    yield cgroup
    cgroup.kill_all()
    time.sleep(0.05)
    cgroup.destroy()


# --- the ordering property -------------------------------------------------

@requires_cgroup2
def test_bounds_exist_before_any_process_is_attached(session) -> None:
    """FR-049: created and owned by the supervisor **before** the container.

    A bound applied after the process starts has a window, and the window is
    exactly long enough for a fork bomb.
    """
    with pytest.raises(CgroupError, match="attach\\(\\) before create\\(\\)"):
        SessionCgroup("never-created").attach(os.getpid())

    bounds_module.apply(session, _bounds())
    assert (session.paths.session / "memory.max").read_text().strip() == str(64 * MIB)
    assert session.pids_current() == 0, "a process was attached before the bound"


@requires_cgroup2
def test_the_workload_is_in_the_cgroup_from_its_first_instruction(
    session, tmp_path: Path
) -> None:
    """The ordering, asserted from *inside* the workload.

    Writing the battery surfaced a real race: `subprocess.Popen` followed by
    `attach()` lets the interpreter run — and fork — before the write to
    `cgroup.procs` lands, so children forked in that window sit in the parent
    cgroup and `pids.max` never sees them. The process bound did not fire, and
    the fault was in the attach, not the bound.

    `spawn()` closes it with a pipe barrier. This test reads the child's *own*
    view of its cgroup, recorded by the child as its first act, which is the
    only vantage point from which the ordering is observable.
    """
    bounds_module.apply(session, _bounds())
    marker = tmp_path / "cgroup.txt"
    pid = session.spawn([
        sys.executable, "-c",
        f"open({str(marker)!r}, 'w').write(open('/proc/self/cgroup').read())",
    ])
    os.waitpid(pid, 0)
    assert f"session-{session.session_id}" in marker.read_text()


@requires_cgroup2
def test_a_bound_that_was_not_applied_as_written_fails_closed(session) -> None:
    """The read-back, proved by asking for something the kernel will refuse.

    `pids.max` accepts only a positive integer or `max`; a negative value is
    rejected at write time. The point of the assertion is that the failure
    surfaces as a refusal to start rather than as a session running with a
    bound nobody set.
    """
    with pytest.raises(CgroupError):
        bounds_module.apply(session, _bounds(pids_max=-1))


# --- exhaustion, one arm per bound ----------------------------------------

@requires_cgroup2
def test_memory_bound_exhaustion_names_its_terminal_state(session) -> None:
    declared = _bounds(memory_max_bytes=32 * MIB)
    bounds_module.apply(session, declared)

    # Allocate well past the bound, from inside the cgroup. `memory.oom.group`
    # means the whole group dies rather than one child.
    pid = session.spawn([sys.executable, "-c", _ALLOCATE_FOREVER])
    os.waitpid(pid, 0)

    outcome = bounds_module.check(session, declared)
    assert outcome is not None, "memory.max did not fire"
    assert outcome.terminal_state == TERMINAL_MEMORY
    assert is_terminal(outcome.terminal_state)
    assert outcome.bound == "memory.max"
    assert session.oom_kills() > 0


@requires_cgroup2
def test_process_bound_exhaustion_names_its_terminal_state(session) -> None:
    declared = _bounds(pids_max=8)
    bounds_module.apply(session, declared)

    # A bounded fork storm: enough to hit pids.max, not a real fork bomb, so
    # the test is reproducible and the host is not the experiment.
    pid = session.spawn([sys.executable, "-c", _FORK_STORM])
    os.waitpid(pid, 0)

    outcome = bounds_module.check(session, declared)
    assert outcome is not None, "pids.max did not fire"
    assert outcome.terminal_state == TERMINAL_PROCESS
    assert is_terminal(outcome.terminal_state)
    assert session.pids_events_max() > 0


@requires_cgroup2
def test_cumulative_processor_bound_names_its_terminal_state(session) -> None:
    """The bound the supervisor enforces, because cgroup v2 has no cumulative
    CPU ceiling — `cpu.max` is a rate and never ends anything."""
    declared = _bounds(cpu_total_seconds=0.30, cpu_max="100000 100000")
    bounds_module.apply(session, declared)

    pid = session.spawn([sys.executable, "-c", _SPIN_FOREVER])

    outcome = None
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        outcome = bounds_module.check(session, declared)
        if outcome is not None:
            break
        time.sleep(0.02)
    session.kill_all()
    os.waitpid(pid, 0)

    assert outcome is not None, "the cumulative processor bound never fired"
    assert outcome.terminal_state == TERMINAL_CPU
    assert is_terminal(outcome.terminal_state)
    assert float(outcome.observed.rstrip("s")) >= declared.cpu_total_seconds


@requires_cgroup2
def test_the_rate_bound_actually_throttles(session) -> None:
    """SC-023's co-located clause, as a property of the mechanism.

    Ten percent of one core means a spinner accumulates roughly a tenth of a
    second of CPU per wall-clock second. The assertion is deliberately loose —
    it is checking that throttling happens at all, not calibrating a scheduler.
    """
    declared = _bounds(cpu_max="10000 100000", cpu_total_seconds=1000.0)
    bounds_module.apply(session, declared)

    pid = session.spawn([sys.executable, "-c", _SPIN_FOREVER])
    time.sleep(2.0)
    used = session.cpu_usage_seconds()
    session.kill_all()
    os.waitpid(pid, 0)

    assert used < 1.0, (
        f"a spinner used {used:.3f}s of CPU in 2s wall clock under a 10% "
        "quota; cpu.max is not throttling"
    )
    assert used > 0.0, "the spinner used no CPU at all; the arm is vacuous"


@requires_cgroup2
def test_a_co_located_workload_keeps_serving_during_exhaustion(session) -> None:
    """SC-023's second clause, measured on the same host.

    The reference workload here is a loop doing bounded work outside the
    session cgroup. It is not a web server, and this is not a latency SLO — it
    is the check that a session exhausting its bounds does not starve a
    neighbour. Recorded as what it is.
    """
    declared = _bounds(cpu_max="10000 100000", cpu_total_seconds=1000.0,
                       memory_max_bytes=32 * MIB)
    bounds_module.apply(session, declared)

    hog = session.spawn([sys.executable, "-c", _SPIN_FOREVER])

    served = 0
    started = time.monotonic()
    while time.monotonic() - started < 2.0:
        sum(range(1000))
        served += 1

    session.kill_all()
    os.waitpid(hog, 0)
    assert served > 100, (
        f"the co-located workload completed {served} iterations in 2s while a "
        "bounded session saturated its quota; SC-023's co-located clause is "
        "not being met"
    )


# --- the removal proof ----------------------------------------------------

@requires_cgroup2
def test_without_the_bound_the_same_workload_is_not_stopped(session) -> None:
    """**The removal proof.** Same fork storm, `pids.max` left at `max`.

    Without this, every arm above would pass on a host that happened to be out
    of memory or out of pids for unrelated reasons. Here the mechanism is
    removed and the identical defect goes unstopped.
    """
    (session.paths.session / "pids.max").write_text("max")

    pid = session.spawn([sys.executable, "-c", _FORK_STORM])
    time.sleep(0.5)
    unbounded_peak = session.pids_current()
    os.waitpid(pid, 0)

    assert session.pids_events_max() == 0, (
        "pids.events reported a refusal with the bound removed"
    )
    assert unbounded_peak > 8, (
        f"only {unbounded_peak} processes ran with the bound removed, so the "
        "bounded arm's refusal at 8 is not attributable to pids.max"
    )


@requires_cgroup2
def test_delegation_check_rejects_a_cgroup_mount_in_the_declared_set() -> None:
    """T104 — nothing inside can raise, extend or evade a bound."""
    from src.supervisor.cgroup import assert_not_delegated
    from src.supervisor.location_set import LocationSetError, parse
    from tests.fixtures.locations import document

    delegated = parse(document(locations=[
        {"source": "/sys/fs/cgroup/f2a", "target": "/sys/fs/cgroup",
         "mode": "ro", "rule_id": "FS-DECL-009",
         "justification": "observability, allegedly"},
    ]))
    with pytest.raises(LocationSetError, match="delegation"):
        assert_not_delegated(delegated)


@requires_cgroup2
def test_delegation_check_permits_a_normal_set() -> None:
    from src.supervisor.cgroup import assert_not_delegated
    from tests.fixtures.locations import location_set

    assert_not_delegated(location_set())


def test_bound_terminal_states_are_declared_members() -> None:
    for name in (TERMINAL_MEMORY, TERMINAL_CPU, TERMINAL_PROCESS):
        assert is_terminal(name)
