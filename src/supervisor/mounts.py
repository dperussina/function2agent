"""T097 — FR-048's mechanism: a per-session mount namespace with an **empty
root** into which only the declared locations are mounted.

The property this buys, and the reason it is a mount namespace rather than
filesystem permissions: a location outside the declared set is **absent**, not
permission-denied. `open("/etc/shadow")` inside the session returns `ENOENT`
because there is no `/etc` — not `EACCES` because something said no. That is
what makes FR-048's *"a location is reachable because it was declared, never
because nothing excluded it"* a structural property instead of a policy, and
it is the difference the test asserts: the errno, not merely the failure.

**What this mechanism does not do, stated here because it is the whole reason
a second component exists.** A mount namespace enforces perfectly and
**records nothing**. The attempt fails inside the container and no component
outside it ever learns, so namespace-only satisfies FR-048's enforcement
clause and fails its recording clause and SC-022's 100%. The recording is
`seccomp.py`'s, and it emits *before* the kernel acts.

Sequence, which is `pivot_root(2)`'s and not ours to vary:

    unshare(CLONE_NEWNS)
    mount(/, MS_REC|MS_PRIVATE)      so nothing propagates back to the host
    tmpfs at <staging>               the empty root
    bind each declared location      then remount it with its declared flags
    pivot_root(<staging>, .oldroot)
    umount2(/.oldroot, MNT_DETACH)   the host root becomes unreachable
    rmdir(/.oldroot)
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Callable

from src.supervisor import _linux
from src.supervisor.location_set import DeclaredLocation, LocationSet

OLD_ROOT = ".oldroot"


class MountError(RuntimeError):
    """The namespace could not be built. The session does not start."""


@dataclass(frozen=True)
class MountPlan:
    """What will be mounted, computed before anything is mounted.

    Kept separate from the doing so that the plan is inspectable in a test and
    recordable in the trace without requiring privilege.
    """

    session_id: str
    new_root: str
    entries: tuple[tuple[DeclaredLocation, str], ...]  # (declaration, dest)
    location_set_address: str

    def as_record(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "location_set_address": self.location_set_address,
            "mounts": [
                {
                    "target": loc.target,
                    "mode": loc.mode,
                    "nosuid": loc.nosuid,
                    "nodev": loc.nodev,
                    "noexec": loc.noexec,
                    "rule_id": loc.rule_id,
                }
                for loc, _ in self.entries
            ],
        }


def plan(location_set: LocationSet, session_id: str, staging_root: str) -> MountPlan:
    new_root = os.path.join(staging_root, f"session-{session_id}")
    entries = tuple(
        (loc, os.path.join(new_root, loc.target.lstrip("/")))
        for loc in location_set.locations
    )
    return MountPlan(
        session_id=session_id,
        new_root=new_root,
        entries=entries,
        location_set_address=location_set.content_address(),
    )


def _flags_for(loc: DeclaredLocation) -> int:
    flags = 0
    if loc.mode == "ro":
        flags |= _linux.MS_RDONLY
    if loc.nosuid:
        flags |= _linux.MS_NOSUID
    if loc.nodev:
        flags |= _linux.MS_NODEV
    if loc.noexec:
        flags |= _linux.MS_NOEXEC
    return flags


def enter(mount_plan: MountPlan) -> None:
    """Build the namespace and pivot into it. **Runs in the child process.**

    Every step raises on failure. There is no partial namespace: a failure here
    leaves the child in the unshared namespace with an incomplete root, and the
    caller's contract is to exit non-zero rather than continue.
    """
    _linux.unshare(_linux.CLONE_NEWNS)

    # Detach from the host's propagation tree first. Without this the tmpfs and
    # the binds below can propagate back into the host mount namespace, which
    # would make FR-048's boundary leak in the direction nobody checks.
    _linux.mount(None, "/", None, _linux.MS_REC | _linux.MS_PRIVATE)

    os.makedirs(mount_plan.new_root, exist_ok=True)
    # The empty root. Nothing is in it until something is declared.
    _linux.mount("tmpfs", mount_plan.new_root, "tmpfs",
                 _linux.MS_NOSUID | _linux.MS_NODEV, "mode=0755")

    for loc, dest in mount_plan.entries:
        if not os.path.exists(loc.source):
            raise MountError(
                f"declared location {loc.target!r} names source {loc.source!r}, "
                "which does not exist. A declared location that cannot be "
                "mounted fails the session closed rather than being skipped: "
                "skipping would make the set's positive statement false."
            )
        if os.path.isdir(loc.source):
            os.makedirs(dest, exist_ok=True)
        else:
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "wb"):
                pass
        _linux.mount(loc.source, dest, None, _linux.MS_BIND | _linux.MS_REC)
        # A bind mount ignores the flags on the initial call; they take effect
        # only on a remount. Skipping this second call is the classic way a
        # read-only bind mount turns out to be writable.
        _linux.mount(None, dest, None,
                     _linux.MS_REMOUNT | _linux.MS_BIND | _flags_for(loc))

    old = os.path.join(mount_plan.new_root, OLD_ROOT)
    os.makedirs(old, exist_ok=True)
    _linux.pivot_root(mount_plan.new_root, old)
    os.chdir("/")
    _linux.umount2("/" + OLD_ROOT, _linux.MNT_DETACH)
    os.rmdir("/" + OLD_ROOT)


def run_in_namespace(
    mount_plan: MountPlan,
    body: Callable[[], Any],
) -> dict[str, Any]:
    """Fork, enter the namespace, run `body`, return its JSON-able result.

    Forking is not incidental. `enter()` is irreversible for the process that
    calls it — after `pivot_root` the host root is gone — so the supervisor
    must not call it on itself. The supervisor stays outside, which is also
    what FR-049 requires of the cgroup owner and FR-050 of the lease renewer.
    """
    read_fd, write_fd = os.pipe()
    pid = os.fork()
    if pid == 0:  # child
        os.close(read_fd)
        code = 0
        try:
            enter(mount_plan)
            payload = {"ok": True, "result": body()}
        except BaseException as exc:  # noqa: BLE001 - reported, then exit
            payload = {
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
            }
            code = 1
        try:
            os.write(write_fd, json.dumps(payload).encode("utf-8"))
        finally:
            os.close(write_fd)
        os._exit(code)

    os.close(write_fd)
    chunks = []
    while True:
        chunk = os.read(read_fd, 65536)
        if not chunk:
            break
        chunks.append(chunk)
    os.close(read_fd)
    _, status = os.waitpid(pid, 0)

    raw = b"".join(chunks)
    if not raw:
        raise MountError(
            f"child produced no result; wait status {status}. The namespace "
            "build died before it could report."
        )
    payload = json.loads(raw.decode("utf-8"))
    payload["exit_status"] = status
    return payload
