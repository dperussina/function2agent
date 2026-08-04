"""T102, T104 — FR-049's mechanism: a session cgroup created and owned by the
supervisor **before the container starts**, with no writable `cgroup` mount and
no delegation inside it.

FR-049's operative words are *enforced from outside the environment so that
nothing running inside it — the runtime, a command the agent composed, or a
process that command started — can raise, extend or evade them*. Two things
follow, and they are the two things this module is:

1. The cgroup exists and carries its values **before** the first process is
   attached to it. A bound applied after the process starts has a window, and
   the window is exactly long enough for a fork bomb.
2. The controls are unreachable from inside. `assert_not_delegated()` checks
   the declared location set for any path under the cgroup hierarchy and fails
   closed, because the mount namespace's positive statement is the *only*
   thing standing between the sandbox and `memory.max`.

The four controls are in `bounds.py`. This module owns the lifecycle.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from src.supervisor.location_set import LocationSet, LocationSetError

CGROUP2_ROOT = Path("/sys/fs/cgroup")
PARENT_NAME = "f2a"

# Controllers the session cgroup needs enabled in its parent's subtree_control.
REQUIRED = ("memory", "cpu", "pids")


class CgroupError(RuntimeError):
    """The bound could not be established. The session does not start."""


@dataclass(frozen=True)
class CgroupPaths:
    root: Path
    parent: Path
    session: Path


def paths_for(session_id: str, root: Path = CGROUP2_ROOT,
              parent_name: str = PARENT_NAME) -> CgroupPaths:
    parent = root / parent_name
    return CgroupPaths(root=root, parent=parent, session=parent / f"session-{session_id}")


def _write(path: Path, value: str) -> None:
    try:
        path.write_text(value)
    except OSError as exc:
        raise CgroupError(
            f"cannot write {value!r} to {path}: {exc}. FR-049 requires the "
            "bound to be enforced from outside the environment, so a "
            "supervisor that cannot set it must not start the session."
        ) from None


def _read(path: Path) -> str:
    try:
        return path.read_text()
    except OSError as exc:
        raise CgroupError(f"cannot read {path}: {exc}") from None


def assert_not_delegated(location_set: LocationSet,
                         root: Path = CGROUP2_ROOT) -> None:
    """T104 — nothing inside can raise, extend or evade a bound.

    The check is on the declared location set rather than on the running
    namespace, because it has to hold *before* the session starts. A declared
    location anywhere under the cgroup hierarchy would put `memory.max` inside
    the sandbox, and a writable one would make FR-049's enforced-from-outside
    clause false while every other part of the mechanism still looked correct.
    """
    hierarchy = PurePosixPath(str(root))
    offending = [
        loc for loc in location_set.locations
        if PurePosixPath(loc.source) == hierarchy
        or hierarchy in PurePosixPath(loc.source).parents
        or PurePosixPath(loc.source) in hierarchy.parents
    ]
    if offending:
        raise LocationSetError(
            "The declared location set reaches the cgroup hierarchy:\n"
            + "\n".join(
                f"    {loc.target!r} <- {loc.source!r} ({loc.mode}, rule "
                f"{loc.rule_id})"
                for loc in offending
            )
            + "\n\n  FR-049 requires the bounds to be enforced from outside "
            "the execution environment. A cgroup mount inside it — writable "
            "or not — is delegation, and delegation is what the requirement "
            "forbids. This session does not start."
        )


class SessionCgroup:
    """One session's cgroup. Created by the supervisor, never by the session."""

    def __init__(self, session_id: str, root: Path = CGROUP2_ROOT,
                 parent_name: str = PARENT_NAME) -> None:
        self.session_id = session_id
        self.paths = paths_for(session_id, root, parent_name)
        self._created = False

    # --- lifecycle -------------------------------------------------------
    def prepare_parent(self) -> None:
        """Create the parent and enable the controllers the session needs.

        cgroup v2's "no internal process" rule means a controller has to be
        enabled in a cgroup's `subtree_control` before a child can use it, so
        this runs against the root and then the parent.
        """
        available = set(_read(self.paths.root / "cgroup.controllers").split())
        missing = [c for c in REQUIRED if c not in available]
        if missing:
            raise CgroupError(
                f"cgroup v2 at {self.paths.root} does not offer {missing}; "
                f"available={sorted(available)}. OD-17 makes this platform "
                "unsupported rather than degraded."
            )
        self.paths.parent.mkdir(parents=True, exist_ok=True)
        for level in (self.paths.root, self.paths.parent):
            enabled = set(_read(level / "cgroup.subtree_control").split())
            want = [c for c in REQUIRED if c not in enabled]
            if want:
                _write(level / "cgroup.subtree_control",
                       " ".join(f"+{c}" for c in want))

    def create(self) -> None:
        """Create the session cgroup. Bounds are applied by `bounds.apply`."""
        self.prepare_parent()
        self.paths.session.mkdir(parents=True, exist_ok=True)
        self._created = True

    def attach(self, pid: int) -> None:
        """Move a process in. Only ever called *after* the bounds are written."""
        if not self._created:
            raise CgroupError(
                "attach() before create(): FR-049 requires the bound to exist "
                "before the process does. A process attached to a cgroup whose "
                "limits are not yet written has an unbounded window."
            )
        _write(self.paths.session / "cgroup.procs", str(pid))

    def spawn(self, argv: list[str]) -> int:
        """Start a process **already inside** the cgroup. Returns its pid.

        `attach()` after `subprocess.Popen()` looks equivalent and is not. The
        interpreter starts running the moment `execve` returns, and it can fork
        several times before the supervisor's write to `cgroup.procs` lands —
        those children are then in the *parent* cgroup and `pids.max` never
        sees them. Writing the battery is what surfaced this: with `Popen` plus
        `attach` the process bound did not fire, and the reason was a race in
        the attach, not a fault in the bound.

        FR-049's "created and owned by the supervisor before the container
        starts" is satisfied by ordering, so the ordering is here:

            fork                      the child blocks on a pipe
            write cgroup.procs        the supervisor attaches it
            signal                    the child unblocks
            execve                    the workload begins, already bounded

        The child runs no user code before the barrier, so there is no window.
        """
        if not self._created:
            raise CgroupError(
                "spawn() before create(): FR-049 requires the bound to exist "
                "before the process does."
            )
        read_fd, write_fd = os.pipe()
        pid = os.fork()
        if pid == 0:  # child
            os.close(write_fd)
            # Blocks until the supervisor has attached us. A closed pipe with
            # no byte means the supervisor failed; exiting is the only correct
            # response, because continuing would run unbounded.
            if os.read(read_fd, 1) != b"\x01":
                os._exit(127)
            os.close(read_fd)
            try:
                os.execv(argv[0], argv)
            except OSError:
                os._exit(126)
        os.close(read_fd)
        try:
            self.attach(pid)
        except CgroupError:
            os.close(write_fd)  # the child sees EOF and exits 127
            os.waitpid(pid, 0)
            raise
        os.write(write_fd, b"\x01")
        os.close(write_fd)
        return pid

    def destroy(self) -> None:
        try:
            self.paths.session.rmdir()
        except OSError:
            # A cgroup with live processes cannot be removed. Reclaiming it is
            # housekeeping, never a safety property — the bound was enforced
            # while it mattered.
            pass

    # --- observation, for the supervisor's watch loop --------------------
    def cpu_usage_seconds(self) -> float:
        for line in _read(self.paths.session / "cpu.stat").splitlines():
            if line.startswith("usage_usec "):
                return int(line.split()[1]) / 1_000_000
        raise CgroupError(
            f"cpu.stat in {self.paths.session} has no usage_usec line; the "
            "cumulative processor bound cannot be watched"
        )

    def memory_peak_bytes(self) -> int | None:
        path = self.paths.session / "memory.peak"
        return int(_read(path).strip()) if path.is_file() else None

    def oom_kills(self) -> int:
        path = self.paths.session / "memory.events"
        if not path.is_file():
            return 0
        for line in _read(path).splitlines():
            if line.startswith("oom_kill "):
                return int(line.split()[1])
        return 0

    def pids_current(self) -> int:
        return int(_read(self.paths.session / "pids.current").strip())

    def pids_events_max(self) -> int:
        """How many forks `pids.max` refused. Non-zero means the bound fired."""
        path = self.paths.session / "pids.events"
        if not path.is_file():
            return 0
        for line in _read(path).splitlines():
            if line.startswith("max "):
                return int(line.split()[1])
        return 0

    def live_pids(self) -> list[int]:
        raw = _read(self.paths.session / "cgroup.procs").split()
        return [int(p) for p in raw]

    def kill_all(self) -> None:
        """`cgroup.kill` — the kernel kills the group as a unit.

        There is no fallback. Signalling each pid from `cgroup.procs` in a loop
        loses the race `cgroup.kill` exists to close: a process forks between
        the listing and the kill and the child survives the round, which under
        a workload that is forking — the case FR-049's process bound is for —
        means the session does not die. Degrading to that loop would leave the
        operator with a bound they configured and the system does not hold, so
        the absence is an error. `preflight._check_cgroup_kill` catches it at
        startup; this is the second line, for a cgroup mounted since.
        """
        path = self.paths.session / "cgroup.kill"
        if not path.is_file():
            raise CgroupError(
                f"{path} is absent, so this session cannot be killed as a "
                "unit. The per-pid fallback loses the fork race and would "
                "leave FR-049's process bound unenforceable; refusing rather "
                "than reporting a kill that did not happen. Requires Linux "
                "5.14 or later."
            )
        _write(path, "1")
