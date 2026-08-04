"""T097 — FR-048's mechanism: a per-session mount namespace with an **empty
root** into which only the declared locations are mounted.

The property this buys, and the reason it is a mount namespace rather than
filesystem permissions: a location outside the declared set is **not present as
a reachable object**, rather than present and permission-denied.
`open("/etc/shadow")` inside the session returns `ENOENT` because there is no
`/etc` — not `EACCES` because something said no. That is what makes FR-048's
*"a location is reachable because it was declared, never because nothing
excluded it"* a structural property instead of a policy, and it is the
difference the test asserts: the errno, not merely the failure.

**"There is nothing at it to open" was a false premise and is corrected here
(finding 021).** That sentence, in this file and in `seccomp.py` and in
`filesystem-decision.md`, was doing load-bearing work: it is the reason a
misread path in an audit record was argued to be harmless. It is only true of a
path the workload *cannot create*. Finding 021 measured a workload creating
`/undeclared.txt` and `mkdir /undeclared-dir` directly in the session root as
uid 0, because the root `tmpfs` was mounted without `MS_RDONLY`; the root
listing went from one entry to four. **The correct statement is narrower**: an
undeclared path is unreachable *and* uncreatable, and the second half is a
property this file now has to establish rather than assume. Two mount flags do
it, and both are here:

- the session root is remounted `MS_RDONLY` once the namespace is built, so
  nothing can be created at an undeclared path in it;
- the read-only remount is applied to **every** mount the recursive bind
  copied, not only to the outermost one.

Sequence, which is `pivot_root(2)`'s and not ours to vary:

    unshare(CLONE_NEWNS)
    mount(/, MS_REC|MS_PRIVATE)      so nothing propagates back to the host
    tmpfs at <staging>               the empty root, writable for now
    bind each declared location      MS_REC, so submounts come with it
    remount every mount in that tree with the declaration's flags
    pivot_root(<staging>, .oldroot)
    umount2(/.oldroot, MNT_DETACH)   the host root becomes unreachable
    rmdir(/.oldroot)
    remount / read-only              only now: the steps above write into it

**What this mechanism does not do, stated here because it is the whole reason
a second component exists.** A mount namespace enforces perfectly and
**records nothing**. The attempt fails inside the container and no component
outside it ever learns, so namespace-only satisfies FR-048's enforcement
clause and fails its recording clause and SC-022's 100%. The recording is
`seccomp.py`'s, and it emits *before* the kernel acts.
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


# `mountinfo(5)` escapes exactly these four characters in the mount point field.
# Unescaped, a declared source with a space in it produces a mount point this
# module would fail to match and therefore fail to remount read-only — a
# writable hole selected by a filename.
_MOUNTINFO_ESCAPES = {"040": " ", "011": "\t", "012": "\n", "134": "\\"}


def _unescape_mountinfo(field: str) -> str:
    out, i = [], 0
    while i < len(field):
        if field[i] == "\\" and field[i + 1:i + 4] in _MOUNTINFO_ESCAPES:
            out.append(_MOUNTINFO_ESCAPES[field[i + 1:i + 4]])
            i += 4
        else:
            out.append(field[i])
            i += 1
    return "".join(out)


def mount_points_under(path: str) -> list[str]:
    """Every mount point at or below `path`, shallowest first.

    Read from `/proc/self/mountinfo` rather than assumed, because the set is a
    property of the host tree at this instant and nothing in `LocationSet` can
    express or detect it.

    An unreadable `mountinfo` raises rather than returning `[path]`. Returning
    the bare path would mean the submounts silently keep whatever flags the
    host gave them, which is the defect this function exists to close, wearing
    a successful return value.
    """
    try:
        with open("/proc/self/mountinfo", "r", encoding="utf-8") as fh:
            lines = fh.readlines()
    except OSError as exc:
        raise MountError(
            "/proc/self/mountinfo could not be read, so the mounts inside "
            f"{path!r} cannot be enumerated and cannot be remounted with the "
            "declaration's flags. Failing closed: a bind carries MS_REC and "
            "copies the source's whole subtree, so skipping this step leaves "
            "every submount with the flags the host gave it."
        ) from exc

    prefix = path.rstrip("/") + "/"
    found = []
    for line in lines:
        fields = line.split(" ")
        if len(fields) < 5:
            continue
        point = _unescape_mountinfo(fields[4])
        if point == path or point.startswith(prefix):
            found.append(point)
    # Shallowest first. A remount applies to one mount, so the order does not
    # affect the outcome; it is fixed so that a failure reports the outermost
    # mount that could not be secured rather than an arbitrary one.
    return sorted(set(found), key=lambda p: (p.count("/"), p))


def _seal_root() -> None:
    """Remount the session root read-only. Called last, after `pivot_root`.

    ── WHAT THIS CLOSES ────────────────────────────────────────────────────

    The root is not a declared location and carries no `mode`, so no `FS-*`
    rule governs anything in it. Left writable — which it was, mounted
    `MS_NOSUID | MS_NODEV` and nothing else — a workload could create files and
    directories at undeclared paths, and the classifier would record FS-001
    `undeclared_location` (*the path resolves outside every declared
    location*) about a write the kernel was at that moment completing.
    Finding 021 observed the root listing going from one entry to four.

    ── WHY IT CANNOT HAPPEN EARLIER ────────────────────────────────────────

    Every step of `enter()` writes into this filesystem: the mount point for
    each declared target, and `.oldroot` for `pivot_root` to put the old root
    in. The seal is therefore the last thing that happens, after `.oldroot`
    has been detached and removed.

    ── WHAT IT DOES NOT AFFECT ─────────────────────────────────────────────

    `MS_REMOUNT` applies to one mount. The declared locations mounted into
    this root keep their own flags, so a `mode="rw"` declaration stays
    writable. A workload that needs scratch space has to *declare* it, which
    is FR-048's positive-declaration clause working as intended rather than a
    restriction stacked on top of it.
    """
    _linux.mount(None, "/", None,
                 _linux.MS_REMOUNT | _linux.MS_RDONLY
                 | _linux.MS_NOSUID | _linux.MS_NODEV)


def _remount_tree(dest: str, flags: int) -> None:
    """Apply `flags` to `dest` **and to every mount inside it**.

    ── WHY THIS IS NOT ONE `mount()` CALL ──────────────────────────────────

    The bind above carries `MS_REC`, which copies the source's entire subtree
    as a set of distinct mounts. `MS_REMOUNT | MS_BIND` changes the per-mount
    flags of *one* mount; `MS_REC` alongside it does not make the change
    recursive on the mount(2) interface this module uses. Before this loop
    existed, a declaration of `mode="ro"` produced an outer mount carrying `ro`
    and every submount inside it carrying `rw` — measured in finding 021 as a
    write returning `OK` inside a submount while the identical write one
    directory up returned `EROFS`.

    Whether a production declared source contains a submount is a property of
    the deployment's host tree and is not knowable from here, so the loop runs
    unconditionally and is a no-op when there is nothing inside.

    The declaration's own flags are applied, not `MS_RDONLY` unconditionally:
    a `mode="rw"` declaration must stay writable all the way down, or the
    recursion would silently convert a declared mode into a different one.
    """
    for point in mount_points_under(dest):
        _linux.mount(None, point, None,
                     _linux.MS_REMOUNT | _linux.MS_BIND | flags)


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
    # The empty root. Nothing is in it until something is declared. Writable
    # for the duration of the build only — the mount points below are created
    # in it — and remounted `MS_RDONLY` at the end of this function.
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
        # read-only bind mount turns out to be writable — and applying it to
        # the outermost mount alone is the subtler way the same thing happens
        # one directory further in. See `_remount_tree`.
        _remount_tree(dest, _flags_for(loc))

    old = os.path.join(mount_plan.new_root, OLD_ROOT)
    os.makedirs(old, exist_ok=True)
    _linux.pivot_root(mount_plan.new_root, old)
    os.chdir("/")
    _linux.umount2("/" + OLD_ROOT, _linux.MNT_DETACH)
    os.rmdir("/" + OLD_ROOT)
    _seal_root()


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
