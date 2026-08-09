"""The suite must not leave processes running after it finishes.

Several suites spawn a child that never exits on its own and kill it from
outside, because that is the only way to test a crash. Any failure between the
spawn and the kill leaks it. Three such children — supervisors renewing a lease
every 200ms — were found four days after the runs that made them, still
running, reparented to init, still holding open a `sessions.db` under a
`basetemp` whose pytest process had long exited.

The spawn sites carry their own `try/finally`. These test the backstop in
`tests/conftest.py`, which catches the site that forgets: at the end of the run
every fixture has been finalized, so a process still parented to pytest is a
process nobody owns.
"""

from __future__ import annotations

import multiprocessing
import multiprocessing.resource_tracker
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import conftest as suite_conftest  # noqa: E402

#: A child that will not exit on its own — the shape the crash arms spawn.
_NEVER_EXITS = "import time\nwhile True: time.sleep(0.05)\n"


def _spawn_a_child_that_never_exits() -> subprocess.Popen:
    return subprocess.Popen([sys.executable, "-c", _NEVER_EXITS])


def _pids(children: list[tuple[int, str]]) -> set[int]:
    return {pid for pid, _ in children}


def test_a_child_that_outlives_its_owner_is_found() -> None:
    """The detection, over a child of exactly the shape that leaked."""
    child = _spawn_a_child_that_never_exits()
    try:
        found = suite_conftest._surviving_children()
        assert child.pid in _pids(found), (
            f"a live child ({child.pid}) is not in {found}. The sweep reports "
            "nothing where there is something, which is the same output it "
            "produces on a clean run."
        )
    finally:
        child.kill()
        child.wait(timeout=10)


def test_the_reaper_kills_what_it_reports() -> None:
    """Reporting without killing leaves the process, which is the whole harm."""
    child = _spawn_a_child_that_never_exits()
    try:
        reaped = suite_conftest._reap_leaked_children()

        assert child.pid in _pids(reaped), (
            f"the child ({child.pid}) was not reported as reaped: {reaped}"
        )
        deadline = time.time() + 10
        while time.time() < deadline and child.poll() is None:
            time.sleep(0.02)
        assert child.poll() is not None, (
            "the child was named in the report and is still running, so the "
            "report is a description of a leak rather than the end of one"
        )
    finally:
        if child.poll() is None:  # pragma: no cover — only if the reap failed
            child.kill()
            child.wait(timeout=10)


def test_a_finished_child_nobody_waited_on_is_not_a_leak() -> None:
    """The false positive that would have made this unusable.

    A `Popen` whose child has exited but has not been waited on is a zombie
    still parented here. It is not running, holds nothing open, and disappears
    when pytest exits — and the suite creates them routinely. A sweep that
    called those leaks would report on nearly every run, and a report that
    fires on every run is one nobody reads.
    """
    child = subprocess.Popen([sys.executable, "-c", ""])
    try:
        # Neither `poll()` nor `wait()` may be called here: both reap, and a
        # reaped child is not the state this arm is about.
        deadline = time.time() + 10
        while time.time() < deadline and not _is_zombie(child.pid):
            time.sleep(0.01)
        assert _is_zombie(child.pid), (
            f"{child.pid} never became an unreaped zombie, so this arm has no "
            "subject and its assertion below is vacuous"
        )

        assert child.pid not in _pids(suite_conftest._surviving_children()), (
            f"the zombie {child.pid} was reported as a surviving child"
        )
    finally:
        child.wait(timeout=10)


def _is_zombie(pid: int) -> bool:
    """`Z` on Linux, `Z`-prefixed on macOS ("Z+", "Zs")."""
    listing = subprocess.run(["ps", "-o", "state=", "-p", str(pid)],
                             capture_output=True, text=True).stdout.strip()
    return listing.startswith("Z")


def test_the_multiprocessing_resource_tracker_is_never_reaped() -> None:
    """The exemption, over the one long-lived child the stdlib owns.

    `multiprocessing`'s resource tracker is a direct child of any process that
    has used a spawn context and lives until that process exits by design.
    `tests/integration/test_store_concurrent_writers.py` starts one on every
    run. Killing it is not cleanup; it breaks the interpreter that is still
    running. The exemption is read off the module that owns it rather than
    matched against a command line, and this is what asserts that.
    """
    with multiprocessing.get_context("spawn").Pool(1) as pool:
        pool.map(abs, [-1])

    tracker = multiprocessing.resource_tracker._resource_tracker._pid
    assert tracker is not None, (
        "no resource tracker is running, so this test is vacuous — the "
        "exemption it is meant to exercise has nothing to exempt"
    )
    assert tracker in suite_conftest._stdlib_helper_pids()
    assert tracker not in _pids(suite_conftest._surviving_children()), (
        f"the resource tracker ({tracker}) is reported as a leaked child, so "
        "the sweep would kill a process the interpreter still needs"
    )


#: Carried in the leaked child's own argv so the arm below can find it in `ps`
#: without matching on an interpreter path every python process shares.
_LEAK_PROBE = "F2A-CONFTEST-LEAK-PROBE"

_A_TEST_THAT_LEAKS = (
    "import subprocess, sys\n"
    "def test_leaks_a_child():\n"
    "    child = subprocess.Popen([sys.executable, '-c',\n"
    "        'import time  # {marker}\\nwhile True: time.sleep(0.05)'])\n"
    "    open({pidfile!r}, 'w').write(str(child.pid))\n"
)


def test_a_run_that_leaks_a_child_kills_it_and_says_so() -> None:
    """The wiring, which none of the arms above touch.

    Every test above calls the sweep directly, so all of them stay green if the
    call is deleted from `pytest_terminal_summary` — the mechanism would be
    intact, never invoked, and invisible. That is this repository's own rot:
    a check whose subject is reachable only from a caller nobody asserts.

    So this runs a real pytest whose one test leaks a child, and reads both
    halves off it: the process is gone afterwards, and the run *said* so.
    Loading `tests/conftest.py` with `-p` rather than putting the leaky test
    under `tests/` keeps the nested run from writing into the tree it is
    measuring.
    """
    tests_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    root = os.path.dirname(tests_dir)
    scratch = tempfile.mkdtemp(prefix="f2a-leak-wiring-")

    # The child is identified by the pid it records, never by matching `ps`
    # against the marker: this file's own name for the probe ends up in the
    # command line of whatever shell invoked pytest, so a `ps` match reports
    # the harness as its own leak.
    pidfile = os.path.join(scratch, "child.pid")
    leaky = os.path.join(scratch, "test_leaky.py")
    with open(leaky, "w") as handle:
        handle.write(_A_TEST_THAT_LEAKS.format(
            marker=_LEAK_PROBE, pidfile=pidfile))

    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join([tests_dir, root])

    try:
        inner = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-p", "conftest",
             "-p", "no:cacheprovider",
             "--basetemp", os.path.join(scratch, "basetemp"), leaky],
            capture_output=True, text=True, timeout=180, cwd=scratch,
            env=environment,
        )

        assert "1 passed" in inner.stdout, (
            "the nested run did not report a passing test, so it never got as "
            f"far as leaking one:\n{inner.stdout[-2000:]}\n{inner.stderr[-2000:]}"
        )
        assert os.path.exists(pidfile), (
            f"the leaky test never recorded a child:\n{inner.stdout[-2000:]}")
        leaked_pid = int(open(pidfile).read())

        assert "child processes this run left behind" in inner.stdout, (
            "a run that leaked a child reported nothing about it. The leak is "
            "invisible in exactly the way that let three of them survive four "
            f"days:\n{inner.stdout[-2000:]}"
        )
        assert str(leaked_pid) in inner.stdout, (
            f"the report does not name the process ({leaked_pid}) it is "
            f"about:\n{inner.stdout[-2000:]}"
        )
        assert _LEAK_PROBE in inner.stdout, (
            "the report names a pid and not a command line, so a reader whose "
            "process is already dead cannot tell which test to go and fix:\n"
            f"{inner.stdout[-2000:]}"
        )
        assert not _is_running(leaked_pid), (
            f"the run named the leaked child ({leaked_pid}) and left it "
            "running. Naming it is the signal; killing it is the repair, and "
            "this arm requires both."
        )
    finally:
        if os.path.exists(pidfile):
            stray = int(open(pidfile).read())
            if _is_running(stray):  # pragma: no cover — only if the sweep failed
                try:
                    os.kill(stray, signal.SIGKILL)
                except OSError:
                    pass
        shutil.rmtree(scratch, ignore_errors=True)


def _is_running(pid: int) -> bool:
    """Alive and not a zombie. Absent from `ps` entirely reads as gone."""
    state = subprocess.run(["ps", "-o", "state=", "-p", str(pid)],
                           capture_output=True, text=True).stdout.strip()
    return bool(state) and not state.startswith("Z")


def test_a_sweep_that_could_not_run_is_reported_and_not_scored_as_clean(
    monkeypatch,
) -> None:
    """Finding 034's shape, refused here rather than met again.

    An unavailable `ps` and a clean run produce the same empty list and the
    opposite facts. Returning the first as the second is an instrument scoring
    full marks precisely when it measured nothing — which is how this
    repository's removal-proof harness once reported 48 proved on a host with
    no pytest.
    """
    monkeypatch.setattr(suite_conftest, "_children_unchecked", None)

    def no_ps(*args, **kwargs):
        raise FileNotFoundError(2, "No such file or directory: 'ps'")

    monkeypatch.setattr(suite_conftest.subprocess, "Popen", no_ps)

    assert suite_conftest._surviving_children() == []
    assert suite_conftest._children_unchecked is not None, (
        "the sweep could not run and said nothing, so a run that swept no "
        "child reads exactly like a run that leaked none"
    )
    assert "ps" in suite_conftest._children_unchecked
