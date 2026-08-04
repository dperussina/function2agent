"""Marker handling for the two kinds of test this suite cannot run everywhere.

`linux_only` and `privileged` are declared in `pyproject.toml`. They are
handled here rather than with a `skipif` on each test so that the reason a test
did not run is one sentence in one place.

**Skipped is reported, never silent.** A skipped kernel-mechanism test is not
evidence the mechanism works, and a run that skipped all of them should not
read as a green run. `pytest_terminal_summary` prints the count and says so.
"""

from __future__ import annotations

import ctypes
import os
import shutil
import sys
import tempfile

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
    """
    if config.option.basetemp is not None:
        return
    if len(tempfile.gettempdir()) + _TMP_PATH_SUFFIX_BUDGET <= _SUN_PATH_MAX:
        return
    short = os.path.join("/tmp", f"f2a-pytest-{os.getuid()}")
    shutil.rmtree(short, ignore_errors=True)
    os.makedirs(short, exist_ok=True)
    config.option.basetemp = short


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


def pytest_terminal_summary(terminalreporter, exitstatus, config) -> None:
    if _skipped_privileged or _skipped_linux:
        terminalreporter.write_sep("=", "kernel mechanisms not exercised")
        terminalreporter.write_line(
            f"  {_skipped_linux} skipped for platform, "
            f"{_skipped_privileged} for privilege.\n"
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
