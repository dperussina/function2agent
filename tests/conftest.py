"""Marker handling for the two kinds of test this suite cannot run everywhere.

`linux_only` and `privileged` are declared in `pyproject.toml`. They are
handled here rather than with a `skipif` on each test so that the reason a test
did not run is one sentence in one place.

**Skipped is reported, never silent.** A skipped kernel-mechanism test is not
evidence the mechanism works, and a run that skipped all of them should not
read as a green run. `pytest_terminal_summary` prints the count and says so.

**And it counts the reports pytest filed, not the markers it dispatched, because
the paragraph above is not true of the whole tree.** Five modules — the mount,
seccomp and bounds suites, which are exactly the FR-048 and FR-049 mechanism
tests — carry a module-level `pytest.mark.skipif(sys.platform != "linux")`
instead of the marker. Those never reach `pytest_runtest_setup`'s counters, so on
a macOS host the banner stayed silent through a run whose 45 skips were 44
kernel-mechanism skips and one vacuous invariant. A warning that a green run is
not evidence is worthless if the run that most needs it is the run that suppresses
it, so the count is derived from `terminalreporter.stats` and is independent of
how the skip was raised.

**And a run also reports the child processes it left behind.** Several suites
spawn a child that never exits on its own — `while True: time.sleep(...)` — and
kill it from outside, because that is the only way to test a crash. Four of the
five files that do this wrap the spawn in `try/finally`; one did not, and any
failure between the spawn and the kill leaked a supervisor that went on renewing
a lease five times a second. Three of them were found four days later, still
running. Nothing in the suite was looking, which is why they lasted four days
rather than four seconds: the run that leaks one is usually red for the failure
that caused the leak, and the leaked process is not part of any report. The
sweep below is that report, and it kills what it names.
"""

from __future__ import annotations

import ctypes
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time

import pytest

_skipped_privileged = 0
_skipped_linux = 0
_vacuous_invariants: dict[str, str] = {}

# `sun_path` in `struct sockaddr_un`: 104 bytes on the BSDs and macOS, 108 on
# Linux. The smaller one is the budget, because a path that binds on one and not
# the other is a portability trap rather than a fix.
_SUN_PATH_MAX = 104
# What the longest socket-binding test appends below `tmp_path`: pytest's own
# `<test-name-truncated-to-30>0/` plus `run/session-s-listener.sock`.
_TMP_PATH_SUFFIX_BUDGET = 64


def pytest_configure(config: pytest.Config) -> None:
    """Keep `tmp_path` short enough that a test can bind a socket inside it.

    On macOS `$TMPDIR` is a ~49-character per-user path under `/var/folders`,
    and pytest builds `tmp_path` beneath it. `SessionListener` then binds an
    `AF_UNIX` socket in that directory and the address overflows `sun_path`,
    so two lease-revocation tests fail with `OSError: AF_UNIX path too long`
    and one of them fails as an `IndexError` on the child's empty stdout,
    which does not name the cause anywhere.

    That is an environmental fault wearing a result's clothes — the same shape
    as a removal proof that reports `proved` because pytest was missing — so it
    is fixed rather than documented. The redirect is conditional on the budget
    actually being exceeded, so on Linux and in CI nothing changes.

    **The directory is keyed by pid, not by uid alone.** Keyed by uid it was
    shared, and this hook begins by deleting it: a second run starting while a
    first was still going deleted the live tree underneath it, surfacing as a
    `FileNotFoundError` from whichever test next touched `tmp_path` and naming
    nothing about the cause. That is the fault above wearing different clothes,
    and it reaches exactly the concurrent runs this repository does routinely.
    Reaping is therefore narrowed to directories whose owning process is gone.
    """
    if config.option.basetemp is not None:
        return
    if len(tempfile.gettempdir()) + _TMP_PATH_SUFFIX_BUDGET <= _SUN_PATH_MAX:
        return
    root = os.path.join("/tmp", f"f2a-pytest-{os.getuid()}")
    _reap_abandoned_basetemps(root)
    short = os.path.join(root, str(os.getpid()))
    # Failing loudly here rather than proceeding: a redirect that overflows the
    # budget reintroduces the very overflow it exists to prevent, and would do
    # it silently, since the socket error names the path and not this hook.
    if len(short) + _TMP_PATH_SUFFIX_BUDGET > _SUN_PATH_MAX:
        raise RuntimeError(
            f"redirected basetemp {short!r} still exceeds the sun_path budget "
            f"({len(short)} + {_TMP_PATH_SUFFIX_BUDGET} > {_SUN_PATH_MAX})"
        )
    shutil.rmtree(short, ignore_errors=True)
    os.makedirs(short, exist_ok=True)
    config.option.basetemp = short


def _reap_abandoned_basetemps(root: str) -> None:
    """Remove per-pid basetemps whose owning process has exited.

    Per-pid directories leak where a shared one did not, so they are cleaned on
    the next run instead. Liveness is the only safe predicate available: mtime
    would delete the tree of a long run that happened to be idle.
    """
    try:
        names = os.listdir(root)
    except FileNotFoundError:
        return
    for name in names:
        if not name.isdigit():
            continue
        try:
            os.kill(int(name), 0)
        except ProcessLookupError:
            shutil.rmtree(os.path.join(root, name), ignore_errors=True)
        except PermissionError:
            continue  # Alive and owned by someone else.


# --- the child processes a run left behind -------------------------------
#
# Why this is at session scope and not per test. Per test it would cost a `ps`
# for each of ~1300 outcomes to catch a fault that has occurred three times in
# a week, and — worse — it would be wrong: several fixtures legitimately hold a
# child across the tests that share them, so a per-test sweep would either kill
# a module-scoped enforcement point or need a list of exemptions that goes stale
# silently. At session scope there is no such case. Every fixture has been
# finalized by the time `pytest_terminal_summary` runs, so a process still
# parented to this one is a process nobody owns.
#
# **This is the backstop and not the repair.** It fires at the end of the run,
# so a child leaked by the third test spins alongside the remaining twelve
# hundred. The spawn sites keep their own `try/finally`, which kills the child
# where it was leaked; this catches the site that forgets, which is the one
# failure that has actually happened.

#: Why the sweep did not run, when it could not. `None` means it ran.
_children_unchecked: str | None = None


def _stdlib_helper_pids() -> set[int]:
    """Pids of long-lived children the standard library starts and owns.

    Asked of the modules that started them rather than matched against a
    command line. `multiprocessing`'s resource tracker is a direct child of any
    process that has used a spawn context, and it lives until that process
    exits *by design* — killing it is not cleanup, it is breaking a running
    interpreter. An argv match would also be wrong in the other direction: a
    test whose own command line mentions the tracker would be exempted.
    """
    pids: set[int] = set()
    for module_name, owner_attr, pid_attr in (
        ("multiprocessing.resource_tracker", "_resource_tracker", "_pid"),
        ("multiprocessing.forkserver", "_forkserver", "_forkserver_pid"),
    ):
        module = sys.modules.get(module_name)
        pid = getattr(getattr(module, owner_attr, None), pid_attr, None)
        if isinstance(pid, int):
            pids.add(pid)
    return pids


def _surviving_children() -> list[tuple[int, str]]:
    """Live direct children of this process, and what each is running.

    **A sweep that cannot run says so rather than returning nothing.** An empty
    list and an unavailable `ps` are the same value and opposite facts, and
    reporting the second as the first is finding 034's shape exactly — an
    instrument scoring a clean sweep over a measurement it never took. The
    reason is recorded in `_children_unchecked` and printed.

    Zombies are excluded: a `Popen` whose child has exited but has not been
    waited on is still parented here and is not a leak. The probe excludes
    *itself* by pid rather than by pattern, because `ps` appears in its own
    output as a child of this process.
    """
    global _children_unchecked
    try:
        probe = subprocess.Popen(
            ["ps", "-eo", "pid=,ppid=,state=,command="],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        out, err = probe.communicate(timeout=30)
    except (OSError, subprocess.SubprocessError) as exc:
        _children_unchecked = f"ps did not run: {type(exc).__name__}: {exc}"
        return []
    if probe.returncode != 0:
        _children_unchecked = f"ps exited {probe.returncode}: {err.strip()}"
        return []

    mine = os.getpid()
    exempt = _stdlib_helper_pids() | {probe.pid}
    found: list[tuple[int, str]] = []
    for line in out.splitlines():
        fields = line.split(maxsplit=3)
        if len(fields) < 4:
            continue
        try:
            pid, parent = int(fields[0]), int(fields[1])
        except ValueError:
            continue
        # `state` is `Z` on Linux and `Z`-prefixed on macOS ("Z+", "Zs").
        if parent != mine or pid in exempt or fields[2].startswith("Z"):
            continue
        found.append((pid, fields[3]))
    return found


def _abridge(command: str, budget: int = 200) -> str:
    """Shorten a command line without losing the half that identifies it.

    Truncating the tail loses the wrong half. The interpreter path alone is 121
    characters on a Homebrew macOS python, so a cap much under that shows a
    reader nothing but where python lives — and by the time the report is read
    the process is dead, so the command line is the only clue left about which
    test spawned it.
    """
    if len(command) <= budget:
        return command
    keep = (budget - 5) // 2
    return f"{command[:keep]} ... {command[-keep:]}"


def _reap_leaked_children() -> list[tuple[int, str]]:
    """Kill every unowned child and return what was killed.

    `SIGKILL` rather than `SIGTERM`: these are, by construction, processes that
    outlived the test that started them, and the ones this has caught are crash
    probes whose whole purpose is to have no shutdown path. Waiting politely for
    one to handle a signal it was written to ignore would only make the end of
    the run slower.
    """
    leaked = _surviving_children()
    for pid, _ in leaked:
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            continue  # Exited between the listing and the signal.
    for pid, _ in leaked:
        # Bounded, so a process that cannot be reaped delays the summary rather
        # than replacing it with a hang.
        for _ in range(100):
            try:
                if os.waitpid(pid, os.WNOHANG)[0] == pid:
                    break
            except ChildProcessError:
                break  # Already reaped by `subprocess`.
            except OSError:
                break
            time.sleep(0.01)
    return leaked


def note_vacuous_invariant(invariant_id: str, reason: str) -> None:
    """Record an invariant that passed over nothing.

    An invariant with no subject is *true*, and pytest reports true the same way
    whether it was earned or free. That is exactly how a check gets quietly
    switched off: the tree it scans is renamed, the assertion keeps passing, and
    the green run is read as coverage. Vacuity gets its own summary block so a
    reader sees it without having to know which skip line to look for.
    """
    _vacuous_invariants[invariant_id] = reason


def _has_cap_sys_admin() -> bool:
    """Try the cheapest privileged operation there is and undo nothing.

    `unshare(CLONE_NEWNS)` in a forked child either succeeds or returns
    `EPERM`. Reading `/proc/self/status` CapEff would also work but means
    parsing a bitmask against a header this file does not have.
    """
    if sys.platform != "linux":
        return False
    pid = os.fork()
    if pid == 0:
        libc = ctypes.CDLL("libc.so.6", use_errno=True)
        os._exit(0 if libc.unshare(0x00020000) == 0 else 1)
    _, status = os.waitpid(pid, 0)
    return os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0


HAS_LINUX = sys.platform == "linux"
HAS_PRIVILEGE = _has_cap_sys_admin()


def pytest_runtest_setup(item: pytest.Item) -> None:
    global _skipped_privileged, _skipped_linux
    if "linux_only" in item.keywords and not HAS_LINUX:
        _skipped_linux += 1
        pytest.skip(
            "OD-17: Linux only. Run inside the dev image: "
            "docker run --rm --privileged -v \"$PWD:/work\" -w /work f2a-dev "
            "python -m pytest"
        )
    if "privileged" in item.keywords and not HAS_PRIVILEGE:
        _skipped_privileged += 1
        pytest.skip(
            "needs CAP_SYS_ADMIN (mount namespaces, cgroup writes, seccomp "
            "listener). Add --privileged to the docker run."
        )


def _skip_reason(report) -> str:
    longrepr = getattr(report, "longrepr", None)
    if isinstance(longrepr, tuple) and len(longrepr) == 3:
        return str(longrepr[2])
    return str(longrepr or "")


def _mechanism_skips(terminalreporter) -> tuple[int, int]:
    """Platform and privilege skips, counted from the reports pytest filed.

    Taken from the reports rather than from the marker counters because the
    modules holding the FR-048 and FR-049 mechanism tests skip by `skipif` and
    never touch those counters. See this file's own docstring.
    """
    platform_skips = privilege_skips = 0
    for report in terminalreporter.stats.get("skipped", []):
        reason = _skip_reason(report).lower()
        if "cap_sys_admin" in reason or "privileg" in reason:
            privilege_skips += 1
        elif "od-17" in reason or "linux only" in reason or "cgroup v2" in reason:
            platform_skips += 1
    return platform_skips, privilege_skips


def pytest_terminal_summary(terminalreporter, exitstatus, config) -> None:
    platform_skips, privilege_skips = _mechanism_skips(terminalreporter)
    # The marker path and the report path see the same skip on a Linux run, so
    # this is a floor rather than a sum; adding them would double-count there.
    platform_skips = max(platform_skips, _skipped_linux)
    privilege_skips = max(privilege_skips, _skipped_privileged)
    if privilege_skips or platform_skips:
        terminalreporter.write_sep("=", "kernel mechanisms not exercised")
        terminalreporter.write_line(
            f"  {platform_skips} skipped for platform, "
            f"{privilege_skips} for privilege.\n"
            "  This run is NOT evidence that FR-048, FR-049 or FR-050 hold. "
            "Those requirements are\n"
            "  discharged only by a privileged Linux run."
        )
    if _vacuous_invariants:
        terminalreporter.write_sep("=", "invariants that passed over nothing")
        for invariant_id, reason in sorted(_vacuous_invariants.items()):
            terminalreporter.write_line(f"  {invariant_id}: {reason}")
        terminalreporter.write_line(
            "  A vacuous invariant is true and carries no weight. It is listed "
            "here so a green\n  run is not mistaken for coverage of it."
        )

    # Last, and side-effecting on purpose. Both halves live in this one hook
    # rather than splitting the kill into `pytest_sessionfinish`, because the
    # terminal reporter calls this hook *from* its own `sessionfinish` and the
    # order between two implementations of that hook is not something this file
    # should be depending on. By here every fixture is finalized.
    leaked = _reap_leaked_children()
    if leaked or _children_unchecked:
        terminalreporter.write_sep("=", "child processes this run left behind")
    for pid, command in leaked:
        terminalreporter.write_line(f"  killed {pid}: {_abridge(command)}")
    if leaked:
        terminalreporter.write_line(
            f"  {len(leaked)} process(es) outlived the test that started them "
            "and have been killed.\n"
            "  This is a defect in the test that spawned them, not in the "
            "process: a child left\n"
            "  running holds its store open and goes on writing long after the "
            "run that made it."
        )
    if _children_unchecked:
        terminalreporter.write_line(
            f"  NOT CHECKED — {_children_unchecked}\n"
            "  No child was swept, so this run is not evidence that it leaked "
            "none."
        )
