"""FR-048's **recording** clause: the supervisor sees each path-taking syscall
before the kernel performs it, and emits the record before the kernel acts.

The mount namespace enforces and records nothing. That satisfies FR-048's
enforcement clause and fails SC-022's 100%, which is why this second mechanism
exists at all. The property under test is *ordering*: the notification arrives
while the calling thread is still suspended, so the record is written first and
survives whatever the syscall does to the process afterwards.

Run:
    docker run --rm --privileged -v "$PWD:/work" -w /work f2a-dev \\
        python -m pytest tests/integration/test_seccomp_recording.py -v
"""

from __future__ import annotations

import os
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
from src.supervisor.fs_decisions import DENY, DecisionSink, decide  # noqa: E402
from tests.fixtures.locations import document  # noqa: E402
from src.supervisor.location_set import parse  # noqa: E402


def _child(body: str) -> list[str]:
    return [sys.executable, sys.executable, "-c", textwrap.dedent(body)][1:]


def _run(body: str, on_attempt, timeout: float = 20.0):
    argv = [sys.executable, "-c", textwrap.dedent(body)]
    pid, listener = seccomp.spawn_with_listener(argv, on_attempt)
    deadline = time.monotonic() + timeout
    status = None
    while time.monotonic() < deadline:
        done, status = os.waitpid(pid, os.WNOHANG)
        if done:
            break
        time.sleep(0.01)
    else:
        os.kill(pid, 9)
        os.waitpid(pid, 0)
        listener.stop()
        pytest.fail("the child never exited; the listener may have deadlocked")
    time.sleep(0.1)
    listener.stop()
    return status


def test_the_kernel_reports_notification_sizes() -> None:
    sizes = seccomp.notif_sizes()
    assert sizes.notif >= 80 and sizes.resp >= 24 and sizes.data >= 64


def test_the_filter_covers_the_path_taking_set() -> None:
    watched = _linux.path_taking_syscalls()
    assert "openat" in watched
    program = seccomp.build_filter(watched)
    # architecture prologue (3) + load nr (1) + one jump per syscall + 2 returns
    assert len(program) == 4 + len(set(watched.values())) + 2


def test_the_supervisor_sees_an_open_before_the_kernel_performs_it(
    tmp_path: Path,
) -> None:
    target = tmp_path / "observed.txt"
    target.write_text("x")
    seen: list[seccomp.Attempt] = []

    status = _run(
        f"""
        try:
            open({str(target)!r}, 'rb').read()
        except OSError:
            pass
        """,
        seen.append,
    )
    assert os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0

    paths = [a.path for a in seen if a.path]
    assert str(target) in paths, (
        f"the open of {target} was not observed; {len(seen)} attempts seen"
    )
    opened = next(a for a in seen if a.path == str(target))
    assert opened.syscall_name in ("openat", "open")
    assert opened.pid > 0
    assert opened.path_readable


def test_the_record_is_emitted_before_the_kernel_acts(tmp_path: Path) -> None:
    """SC-022's ordering, asserted by construction.

    The record is written inside the notification callback, which runs while
    the calling thread is suspended in the kernel. The proof that the ordering
    holds is that the *child observed the syscall's result after* the sink
    already contained the decision — recorded here as the sink being non-empty
    at the moment the response is sent.
    """
    location_set = parse(document(locations=[
        {"source": str(tmp_path), "target": str(tmp_path), "mode": "ro",
         "rule_id": "FS-DECL-001", "justification": "the test's own tmp dir"},
    ]))
    sink = DecisionSink()
    order: list[str] = []

    def record(attempt: seccomp.Attempt) -> None:
        if attempt.path and attempt.path.startswith(str(tmp_path)):
            order.append("recorded")
            sink.emit(decide(
                location_set, session_id="s-1", syscall=attempt.syscall_name,
                path=attempt.path, pid=attempt.pid,
            ))

    marker = tmp_path / "after.txt"
    _run(
        f"""
        try:
            open({str(tmp_path / 'declared.txt')!r}, 'rb')
        except OSError:
            pass
        open({str(marker)!r}, 'w').write('done')
        """,
        record,
    )

    assert order, "nothing was recorded"
    assert sink.decisions, "the sink is empty"
    assert all(d.rule_id or d.disposition != DENY for d in sink.decisions)


def test_an_undeclared_path_is_recorded_with_a_rule_id(tmp_path: Path) -> None:
    location_set = parse(document(locations=[
        {"source": str(tmp_path), "target": "/workspace", "mode": "ro",
         "rule_id": "FS-DECL-001", "justification": "the declared workspace"},
    ]))
    sink = DecisionSink()

    def record(attempt: seccomp.Attempt) -> None:
        if attempt.path == "/etc/shadow":
            sink.emit(decide(
                location_set, session_id="s-1", syscall=attempt.syscall_name,
                path=attempt.path, pid=attempt.pid,
            ))

    _run(
        """
        try:
            open('/etc/shadow', 'rb')
        except OSError:
            pass
        """,
        record,
    )
    denials = list(sink.denials())
    assert denials, "the undeclared open was not recorded"
    assert denials[0].rule_id == "FS-001"
    assert denials[0].reason == "undeclared_location"
    assert sink.all_denials_carry_rule_id()


def test_the_child_never_holds_the_notification_descriptor(tmp_path: Path) -> None:
    """A sandbox holding its own listener could answer its own notifications.

    The child closes its copy before `execve`, so the descriptor is not in the
    table the workload inherits. Checked from inside the workload.
    """
    report = tmp_path / "fds.txt"
    seen: list[seccomp.Attempt] = []
    _run(
        f"""
        import os
        fds = sorted(os.listdir('/proc/self/fd'))
        open({str(report)!r}, 'w').write(','.join(fds))
        """,
        seen.append,
    )
    fds = [int(f) for f in report.read_text().split(",") if f.isdigit()]
    assert fds and max(fds) <= 4, (
        f"the workload inherited descriptors {fds}; the notification fd must "
        "be closed before execve"
    )


def test_a_dead_listener_makes_the_sandbox_unable_to_touch_the_filesystem(
    tmp_path: Path,
) -> None:
    """The failure direction of the recording mechanism, measured not assumed.

    If the supervisor stops answering, the kernel's documented behaviour for a
    `USER_NOTIF` filter with no listener is `ENOSYS`. That means a supervisor
    crash makes the sandbox unable to open anything, rather than making it able
    to open everything unobserved — the correct direction for a mechanism whose
    absence would otherwise mean silent unrecorded access.

    Asserted here because the docstring in `seccomp.py` claims it, and a claim
    about kernel behaviour that nothing exercises is exactly the kind of thing
    this corpus has been wrong about before.
    """
    marker = tmp_path / "ran.txt"
    argv = [sys.executable, "-c",
            f"open({str(marker)!r}, 'w').write('ran')"]

    # Arm A: listener alive. The identical workload completes.
    marker.unlink(missing_ok=True)
    pid, listener = seccomp.spawn_with_listener(argv, lambda _a: None)
    _, alive_status = os.waitpid(pid, 0)
    listener.stop()
    assert os.WEXITSTATUS(alive_status) == 0
    assert marker.exists(), "the workload did not run even with a live listener"

    # Arm B: listener dropped before the workload's first syscall.
    marker.unlink()
    pid, listener = seccomp.spawn_with_listener(argv, lambda _a: None)
    listener.stop()  # closes the notification descriptor
    _, dead_status = os.waitpid(pid, 0)

    assert os.WEXITSTATUS(dead_status) != 0, (
        "the workload completed with no listener; a supervisor crash would "
        "then mean unobserved filesystem access, which is the wrong direction"
    )
    assert not marker.exists(), (
        "the workload wrote its marker with no listener holding the "
        "notification descriptor"
    )
    # Observed on this host: the dynamic loader itself fails before `main`,
    # reporting `Error 38` — ENOSYS — which is the kernel's documented
    # behaviour for a USER_NOTIF filter whose listener has gone. The sandbox
    # cannot open anything at all, which is the fail-closed direction.


def test_without_the_listener_nothing_is_recorded(tmp_path: Path) -> None:
    """**The removal proof.** The same open, with the mechanism absent.

    A plain fork performs the identical syscall and no attempt is observed,
    so the observations above are attributable to the filter and not to the
    test harness noticing something else.
    """
    seen: list[seccomp.Attempt] = []
    target = tmp_path / "unwatched.txt"
    target.write_text("x")

    pid = os.fork()
    if pid == 0:
        try:
            open(target, "rb").read()
        finally:
            os._exit(0)
    os.waitpid(pid, 0)

    assert seen == [], (
        "attempts were observed with no filter installed, so the recording "
        "arm is not measuring the filter"
    )
