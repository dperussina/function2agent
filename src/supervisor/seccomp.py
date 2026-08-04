"""T099 — a `seccomp` user-notification listener **outside** the container,
holding the notification descriptor for path-taking syscalls and seeing each
attempt *before the kernel performs it*.

**Why this exists at all, given T097 already enforces.** A mount namespace with
an empty root enforces FR-048 perfectly and records *nothing*: an undeclared
path is not present in the session's root, the syscall returns `ENOENT` inside
the container, and the supervisor never hears about it. FR-048's recording
clause and **SC-022**'s 100% both need a `filesystem_decision` emitted for every
refusal, so something has to observe the attempt. That is this file.
**Enforcement and recording are two mechanisms here, not one**, and they are
deliberately not collapsed.

**The watch set is a named subset, and `openat2` is not the exception.**
Finding 021 counted twelve write-capable path-taking syscalls that were wired
and unwatched, four of which ordinary Python reaches without trying —
`os.rename`, `os.symlink`, `os.link` and `os.utime` produced no record at all
inside a declared read-only location. Those four (`renameat`, `symlinkat`,
`linkat`, `utimensat`) are now watched; the rest, `openat2` among them, are
not. Every remaining omission and its reason is listed in
`tests/unit/test_watch_set_wiring.py`, which fails if a listed name is later
watched without the list being updated. `check_watch_set_is_wired` below refuses
a watch set that has been enlarged without the two other tables that have to
move with it.

**The division of labour, stated because getting it backwards is a real
vulnerability.** `SECCOMP_USER_NOTIF_FLAG_CONTINUE` is documented as unsafe for
*security* decisions, and it is: the supervisor reads the path out of the
target's memory, and between that read and the kernel performing the syscall
another thread in the target can rewrite the buffer. Every deep-argument
seccomp filter has this race. So the listener here **does not enforce**. It
records, and returns `CONTINUE`, and the mount namespace — which resolves the
path in the kernel, after the race window, inside a root where the undeclared
location does not exist — is what actually refuses. A TOCTOU win against this
listener buys an attacker a *wrong log line*, not a path out of the namespace.

The one case the listener does answer directly is when the notification's
target has already gone: `SECCOMP_IOCTL_NOTIF_ID_VALID` says so and the
notification is dropped rather than answered against a pid that may have been
reused.

**Fails closed on its own failure.** If the listener thread dies, the
notification descriptor closes, and every subsequent path-taking syscall in the
target returns `ENOSYS` — the kernel's behaviour when a `USER_NOTIF` filter has
no listener. The sandbox becomes unable to touch the filesystem at all. That is
the correct direction for a recording mechanism whose absence would otherwise
mean silent unrecorded access.
"""

from __future__ import annotations

import ctypes
import errno
import fcntl
import os
import struct
import threading
from dataclasses import dataclass
from typing import Callable

from src.supervisor import _linux, fs_decisions

# --- BPF ------------------------------------------------------------------
BPF_LD_W_ABS = 0x20
BPF_JMP_JEQ_K = 0x15
BPF_RET_K = 0x06

OFFSET_NR = 0
OFFSET_ARCH = 4

SECCOMP_RET_KILL_PROCESS = 0x80000000

# `_IOC` from <asm-generic/ioctl.h>. Both x86_64 and aarch64 use the generic
# encoding; an architecture that does not would need its own entry rather than
# this one silently producing a wrong request number.
_IOC_WRITE, _IOC_READ = 1, 2
_SECCOMP_IOC_MAGIC = ord("!")


def _ioc(direction: int, nr: int, size: int) -> int:
    return (direction << 30) | (size << 16) | (_SECCOMP_IOC_MAGIC << 8) | nr


# Which argument holds the path, per syscall. Derived from the kernel's own
# signatures; a syscall absent from this map is not watched, because watching a
# syscall whose path argument is guessed produces a confident wrong record.
_PATH_ARG = {
    "open": 0, "openat": 1,
    "stat": 0, "lstat": 0, "newfstatat": 1, "statx": 1,
    "unlink": 0, "unlinkat": 1,
    "rename": 0, "renameat": 1, "renameat2": 1,
    "mkdir": 0, "mkdirat": 1,
    "readlink": 0, "readlinkat": 1,
    "access": 0, "faccessat": 1, "faccessat2": 1,
    "chdir": 0, "truncate": 0, "chmod": 0, "fchmodat": 1,
    # Two-path syscalls. The index names the path whose *location* the
    # decision is about, and the two families choose differently on purpose:
    #
    #   renameat(olddirfd, oldpath, newdirfd, newpath)     -> 1, oldpath
    #   linkat(olddirfd, oldpath, newdirfd, newpath, flag) -> 3, newpath
    #
    # A rename removes `oldpath`, so the source location is modified and index
    # 1 matches the entry `renameat2` already had. A hard link does not touch
    # `oldpath` at all — it only reads it — so recording index 1 for `linkat`
    # would name a location that was not written to and miss the one that was.
    #
    #   symlinkat(target, newdirfd, linkpath)              -> 2, linkpath
    #
    # Index 0 is the symlink's *contents*, a string the kernel stores and never
    # resolves at this call. Recording it would name a path nothing happened at.
    "linkat": 3, "symlinkat": 2,
    #
    #   utimensat(dirfd, pathname, times[2], flags)        -> 1, pathname
    #
    # **`utimensat` is the one watched syscall whose path argument may legally
    # be NULL.** `futimens(fd, times)` is `utimensat(fd, NULL, times, 0)`, and
    # it operates on the descriptor. `read_target_path` returns None for a null
    # pointer, so `decide()` records FS-005 `path_unreadable_at_notification`.
    # Measured on `6.12.76-linuxkit`/`aarch64`, and pinned by
    # `test_a_null_path_utimensat_is_recorded_as_unreadable`.
    #
    # Left as FS-005 rather than given a rule of its own. The disposition is
    # `deny`, which is the conservative direction and is what SC-022 counts;
    # what is imprecise is the *reason*, which says the path could not be read
    # when there was no path to read. Naming that difference needs a new rule
    # identifier, and rule identifiers are stable strings every emitted record
    # carries — an owner decision, not a wiring fix. Recorded here so the next
    # reader finds it stated rather than rediscovers it.
    "utimensat": 1,
}

# Watched syscalls that cannot modify anything, so `fs_decisions` needs no
# write-set entry for them. Enumerated rather than derived by subtracting the
# write set from the watch set: subtraction would silently classify a
# *forgotten* write syscall as read-only, which is the exact failure
# `check_watch_set_is_wired` exists to prevent.
NON_MODIFYING_SYSCALLS = frozenset({
    "stat", "lstat", "newfstatat", "statx",
    "readlink", "readlinkat",
    "access", "faccessat", "faccessat2",
    "chdir",
})

# Which argument holds the open flag word, per syscall. Separate from
# `_PATH_ARG` because most watched syscalls have no such argument, and an entry
# of `None` would be indistinguishable from a syscall somebody forgot.
#
# The direction of an open is not in its name — `openat` is a read syscall or a
# write syscall depending on this word — so a listener that does not read it
# hands the classifier a question it cannot answer. Defect X4 was exactly that.
#
#   open(path, flags, mode)                → 1
#   openat(dirfd, path, flags, mode)       → 2
#   creat(path, mode)                      → no flag word; O_WRONLY|O_CREAT|
#                                            O_TRUNC by definition
#   openat2(dirfd, path, how *, size)      → `how` is a *pointer* to
#                                            struct open_how, not a flag word
_FLAGS_ARG = {"open": 1, "openat": 2}

# Syscalls whose flag word is implied by the syscall itself rather than passed.
_IMPLIED_FLAGS = {"creat": fs_decisions.O_WRONLY | fs_decisions.O_CREAT
                  | fs_decisions.O_TRUNC}

PATH_MAX = 4096


class SeccompError(RuntimeError):
    """The listener could not be established. The session does not start."""


@dataclass(frozen=True)
class NotifSizes:
    notif: int
    resp: int
    data: int


def notif_sizes() -> NotifSizes:
    """Ask the kernel rather than hardcoding `sizeof`.

    The structures have grown across kernel versions. A hardcoded size produces
    an `EINVAL` on the ioctl at best and a misparsed notification at worst, and
    the kernel offers the query precisely so nobody has to guess.
    """
    buf = (ctypes.c_uint16 * 3)()
    _linux.seccomp(_linux.SECCOMP_GET_NOTIF_SIZES, 0, buf)
    return NotifSizes(notif=buf[0], resp=buf[1], data=buf[2])


def check_watch_set_is_wired(
    syscalls: dict[str, int],
    *,
    path_arg: dict[str, int] | None = None,
) -> None:
    """Refuse a watch set that would produce a record nobody should believe.

    ── WHY THIS IS A RUNTIME CHECK AND NOT A TEST ──────────────────────────

    The watch set is a *parameter*. `spawn_with_listener(..., syscalls=...)`
    and `install_filter(syscalls)` both accept an arbitrary one, and that
    parameter is how finding 021's counterfactual arm added `openat2` without
    editing a source file. A caller can therefore reach a misreporting state at
    runtime with no source edit for a static test to notice.

    ── WHAT IT PREVENTS, MEASURED ──────────────────────────────────────────

    Three tables have to agree before a watched syscall records anything true,
    and they live in three files. Measured against the real listener on
    `6.12.76-linuxkit`/`aarch64`, adding `renameat` to the watch set and
    nothing else:

    ==================================  =================================
    state                               what `decide()` recorded
    ==================================  =================================
    as shipped (unwatched)              nothing at all
    watched, no `_PATH_ARG` entry       ``deny FS-005``
                                        ``path_unreadable_at_notification``
    watched, `_PATH_ARG` entry, no      ``allow  rule_id=None  mode='ro'``
    `fs_decisions.WRITE_SYSCALLS` entry
    ==================================  =================================

    Both partial states are **worse than the silence they replace**. FS-005
    asserts the path could not be read out of the target, about a path the
    listener never went looking for. The `allow` asserts that a rename against
    a read-only declaration was permitted — which is defect X4, the one
    `is_write_open` exists to have fixed, resurrected for a different syscall.

    So the correct disposition for a half-wired watch set is to refuse the
    session, not to record something misleading in it. This is the same
    fail-closed direction as a dead listener making the sandbox unable to touch
    the filesystem at all.
    """
    table = _PATH_ARG if path_arg is None else path_arg

    unmapped = sorted(n for n in syscalls if n not in table)
    if unmapped:
        raise SeccompError(
            f"watched syscalls with no path-argument index: {unmapped}. "
            "Add each to `_PATH_ARG` in this file, with the index taken from "
            "the kernel's own signature. Without it the listener builds an "
            "Attempt with path=None and `decide()` records FS-005 "
            "`path_unreadable_at_notification` — which says the path could "
            "not be read out of the target, about a path never looked for."
        )

    known = (fs_decisions.WRITE_SYSCALLS | fs_decisions.OPEN_SYSCALLS
             | NON_MODIFYING_SYSCALLS)
    unclassifiable = sorted(n for n in syscalls if n not in known)
    if unclassifiable:
        raise SeccompError(
            f"watched syscalls the classifier cannot classify: "
            f"{unclassifiable}. Each must appear in "
            "`fs_decisions.WRITE_SYSCALLS` (it modifies), in "
            "`fs_decisions.OPEN_SYSCALLS` (its direction is in its flag word), "
            "or in `NON_MODIFYING_SYSCALLS` in this file (it cannot modify). "
            "Without one of the three, `decide()` computes modifies=False and "
            "records an *allow* with rule_id=None for a write — which states "
            "that the write was permitted."
        )

    unflagged = sorted(
        n for n in syscalls
        if n in fs_decisions.OPEN_SYSCALLS
        and n not in _FLAGS_ARG and n not in _IMPLIED_FLAGS
    )
    if unflagged:
        raise SeccompError(
            f"watched open-family syscalls with no flag word: {unflagged}. "
            "An open whose direction cannot be read is recorded as FS-006, "
            "which is a refusal of the question rather than of the location. "
            "Add an index to `_FLAGS_ARG` or an implied value to "
            "`_IMPLIED_FLAGS`; `openat2` can have neither, which is why it is "
            "not watched."
        )


def build_filter(syscalls: dict[str, int]) -> ctypes.Array:
    """A `sock_filter` program: notify on the watched set, allow everything else.

    The architecture prologue is not decoration. A filter compiled for one
    architecture and evaluated under another matches syscall numbers that mean
    something entirely different, so a mismatch kills the process rather than
    running a filter whose numbers are meaningless.
    """
    numbers = sorted(set(syscalls.values()))
    if len(numbers) > 250:
        raise SeccompError(
            f"{len(numbers)} watched syscalls exceeds the 8-bit BPF jump "
            "offset; the filter would need a jump table"
        )

    class SockFilter(ctypes.Structure):
        _fields_ = [("code", ctypes.c_uint16), ("jt", ctypes.c_uint8),
                    ("jf", ctypes.c_uint8), ("k", ctypes.c_uint32)]

    n = len(numbers)
    program = [
        SockFilter(BPF_LD_W_ABS, 0, 0, OFFSET_ARCH),
        SockFilter(BPF_JMP_JEQ_K, 1, 0, _linux.audit_arch()),
        SockFilter(BPF_RET_K, 0, 0, SECCOMP_RET_KILL_PROCESS),
        SockFilter(BPF_LD_W_ABS, 0, 0, OFFSET_NR),
    ]
    for i, number in enumerate(numbers):
        # Jump forward to the USER_NOTIF return, which sits one past ALLOW.
        program.append(SockFilter(BPF_JMP_JEQ_K, n - i, 0, number))
    program.append(SockFilter(BPF_RET_K, 0, 0, _linux.SECCOMP_RET_ALLOW))
    program.append(SockFilter(BPF_RET_K, 0, 0, _linux.SECCOMP_RET_USER_NOTIF))

    array = (SockFilter * len(program))(*program)
    return array


def install_filter(syscalls: dict[str, int] | None = None) -> int:
    """Install the filter **in the calling process** and return the listener fd.

    Called in the child after `fork` and before `exec`, so the filter is in
    place for everything the sandbox subsequently runs. The returned descriptor
    is passed out to the supervisor over `SCM_RIGHTS` — the child does not keep
    it, because a sandbox holding its own notification descriptor could answer
    its own notifications.
    """
    watched = _linux.path_taking_syscalls() if syscalls is None else syscalls
    if not watched:
        raise SeccompError("empty watch set: the filter would record nothing")
    check_watch_set_is_wired(watched)

    class SockFprog(ctypes.Structure):
        _fields_ = [("len", ctypes.c_uint16),
                    ("filter", ctypes.c_void_p)]

    program = build_filter(watched)
    fprog = SockFprog(len(program), ctypes.cast(program, ctypes.c_void_p))

    _linux.set_no_new_privs()
    fd = _linux.seccomp(
        _linux.SECCOMP_SET_MODE_FILTER,
        _linux.SECCOMP_FILTER_FLAG_NEW_LISTENER,
        ctypes.cast(ctypes.byref(fprog), ctypes.POINTER(ctypes.c_char)),
    )
    if fd < 0:
        raise SeccompError(f"seccomp(SET_MODE_FILTER) returned {fd}")
    return fd


def spawn_with_listener(
    argv: list[str],
    on_attempt: Callable[[Attempt], None],
    syscalls: dict[str, int] | None = None,
) -> tuple[int, "NotificationListener"]:
    """Start `argv` under the filter, with the listener held **by the caller**.

    The descriptor is created inside the child — `SECCOMP_FILTER_FLAG_NEW_LISTENER`
    returns it to whoever installs the filter — and immediately handed out over
    `SCM_RIGHTS`. The child then closes its copy before `execve`, so the
    sandbox never holds the descriptor that answers its own notifications.

    The child blocks on a barrier until the listener is running. Without it the
    child's first `openat` would arrive at a descriptor nobody is reading, and
    with `USER_NOTIF` that call blocks until someone does — a deadlock that
    looks exactly like a slow start.
    """
    import socket

    # Checked here as well as inside `install_filter`, and before the fork.
    # `install_filter` runs in the child, whose only way to report a failure is
    # `os._exit(126)` — the parent then sees "the child did not hand over a
    # notification fd" and the actual reason is gone.
    check_watch_set_is_wired(
        _linux.path_taking_syscalls() if syscalls is None else syscalls
    )

    parent_sock, child_sock = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    pid = os.fork()
    if pid == 0:  # child
        parent_sock.close()
        try:
            fd = install_filter(syscalls)
            socket.send_fds(child_sock, [b"\x01"], [fd])
            os.close(fd)
            if child_sock.recv(1) != b"\x01":
                os._exit(127)
            child_sock.close()
            os.execv(argv[0], argv)
        except BaseException:
            os._exit(126)

    child_sock.close()
    _msg, fds, _flags, _addr = socket.recv_fds(parent_sock, 1, 1)
    if not fds:
        parent_sock.close()
        os.waitpid(pid, 0)
        raise SeccompError("the child did not hand over a notification fd")
    listener = NotificationListener(fds[0], on_attempt, syscalls)
    listener.start()
    parent_sock.send(b"\x01")
    parent_sock.close()
    return pid, listener


@dataclass(frozen=True)
class Attempt:
    """One path-taking syscall, observed before the kernel performed it."""

    notif_id: int
    pid: int
    syscall_nr: int
    syscall_name: str
    path: str | None
    # False when the path could not be read — the target exited, or the pointer
    # was not readable. Recorded as such rather than as an empty path.
    path_readable: bool
    # The open-family flag word, or None for a syscall that has none. Unlike
    # `path` this is not read out of the target's memory: it is a register
    # value the kernel copied into `seccomp_data.args`, so there is no TOCTOU
    # on it and no way for it to be unreadable. A `None` here for an open means
    # the listener is not wired for that syscall, not that the target raced.
    flags: int | None = None


def read_target_path(pid: int, address: int) -> str | None:
    """Read a NUL-terminated path out of the notifying process's own memory.

    ── THE TOCTOU LIVES HERE, AND THIS IS THE WHOLE OF IT ──────────────────

    The address below is a pointer into `pid`'s address space, and `pid` is
    suspended in the syscall but its *other threads are not*. A second thread
    can rewrite the bytes at `address` between this `read` and the kernel's own
    resolution of the same pointer after `CONTINUE`. When that happens the
    string returned here is a path the kernel never resolved: the record is
    WRONG, not merely imprecise.

    Re-reading and comparing would not close it — that is two races instead of
    one. Copying the path and having the kernel use the copy is what
    `SECCOMP_RET_ERRNO` with a supervisor-supplied answer would buy, and that
    is a different FR-048 design; FR-048 keeps `CONTINUE` (owner decision,
    2026-08-03).

    ── WHY IT IS NOT AN ACCESS-CONTROL HOLE ────────────────────────────────

    **The mount namespace is the enforcement; this function is the recorder.**
    An undeclared location is not present in the session's root, and — since
    the root is remounted `MS_RDONLY` and every mount the recursive bind copied
    carries its declaration's flags — the workload cannot put one there either.
    So whatever string the kernel ends up resolving, a workload that wins this
    race changes which path an audit entry names and gains no reach whatsoever.
    Nothing in the system reads the recorded path to decide anything;
    `fs_decisions.decide` runs on the string read here, but its output is a
    record and never a permission.

    **The second clause used to be assumed and was false.** The argument above
    was originally written as *"there is nothing at it to open"*, which holds
    only for a path the workload cannot create. Finding 021 measured a workload
    creating files and directories directly in the session root as uid 0,
    because the root `tmpfs` carried no `MS_RDONLY`. `mounts.enter()` now
    establishes the uncreatable half; this paragraph depends on it and says so
    rather than assuming it.

    ── WHAT THE RECORD THEREFORE CLAIMS ────────────────────────────────────

    SC-022 is narrowed to the record's *existence*, which is exact: the calling
    thread is suspended in `SECCOMP_IOCTL_NOTIF_RECV` when the record is
    written, so an attempt cannot escape being counted. The path is carried
    with `path_provenance = supervisor_read_unverified` and
    `path_is_authoritative == False`. See the provenance note in
    `fs_decisions.py` for why that marking is applied on the hazard rather than
    on a claim that Principle I compels it.

    Returns None when the pointer is null, unreadable, or not NUL-terminated
    within PATH_MAX — recorded as FS-005 rather than treated as benign.
    """
    if address == 0:
        return None
    try:
        with open(f"/proc/{pid}/mem", "rb", buffering=0) as mem:
            mem.seek(address)
            raw = mem.read(PATH_MAX)
    except (OSError, ValueError, OverflowError):
        return None
    end = raw.find(b"\0")
    if end < 0:
        return None
    return raw[:end].decode("utf-8", errors="replace")


class NotificationListener:
    """Holds the notification descriptor and answers every notification.

    Owned by the supervisor, never by the sandbox.
    """

    def __init__(
        self,
        fd: int,
        on_attempt: Callable[[Attempt], None],
        syscalls: dict[str, int] | None = None,
    ) -> None:
        self.fd = fd
        self.on_attempt = on_attempt
        watched = _linux.path_taking_syscalls() if syscalls is None else syscalls
        # The listener is constructible independently of `install_filter`, so
        # the wiring check is repeated here rather than assumed to have run.
        check_watch_set_is_wired(watched)
        self._names = {number: name for name, number in watched.items()}
        self._path_arg = {
            number: _PATH_ARG[name]
            for name, number in watched.items()
            if name in _PATH_ARG
        }
        self._flags_arg = {
            number: _FLAGS_ARG[name]
            for name, number in watched.items()
            if name in _FLAGS_ARG
        }
        self._implied_flags = {
            number: _IMPLIED_FLAGS[name]
            for name, number in watched.items()
            if name in _IMPLIED_FLAGS
        }
        self.sizes = notif_sizes()
        self._recv = _ioc(_IOC_READ | _IOC_WRITE, 0, self.sizes.notif)
        self._send = _ioc(_IOC_READ | _IOC_WRITE, 1, self.sizes.resp)
        self._id_valid = _ioc(_IOC_WRITE, 2, 8)
        self.observed = 0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # --- one notification --------------------------------------------------

    def _parse(self, buf: bytearray) -> tuple[Attempt, int]:
        # struct seccomp_notif { __u64 id; __u32 pid; __u32 flags;
        #                        struct seccomp_data data; }
        # struct seccomp_data  { __s32 nr; __u32 arch; __u64 ip; __u64 args[6]; }
        notif_id, pid, _flags = struct.unpack_from("<QII", buf, 0)
        nr, _arch, _ip = struct.unpack_from("<iIQ", buf, 16)
        args = struct.unpack_from("<6Q", buf, 32)
        name = self._names.get(nr, f"syscall_{nr}")
        index = self._path_arg.get(nr)
        path = None if index is None else read_target_path(pid, args[index])
        flags_index = self._flags_arg.get(nr)
        if flags_index is not None:
            # Truncated to 32 bits: the flag word is an `int` in the ABI and
            # `args[]` is a `__u64`, so the upper half is sign extension or
            # register residue. Masking keeps a negative-looking flag word from
            # setting every bit and classifying every open as a write.
            flags = args[flags_index] & 0xFFFFFFFF
        else:
            flags = self._implied_flags.get(nr)
        return (
            Attempt(
                notif_id=notif_id,
                pid=pid,
                syscall_nr=nr,
                syscall_name=name,
                path=path,
                path_readable=path is not None,
                flags=flags,
            ),
            notif_id,
        )

    def id_valid(self, notif_id: int) -> bool:
        try:
            fcntl.ioctl(self.fd, self._id_valid, struct.pack("<Q", notif_id))
        except OSError:
            return False
        return True

    def _respond_continue(self, notif_id: int) -> None:
        # struct seccomp_notif_resp { __u64 id; __s64 val; __s32 error;
        #                             __u32 flags; }
        resp = bytearray(self.sizes.resp)
        struct.pack_into(
            "<QqiI", resp, 0, notif_id, 0, 0,
            _linux.SECCOMP_USER_NOTIF_FLAG_CONTINUE,
        )
        try:
            fcntl.ioctl(self.fd, self._send, resp)
        except OSError as exc:
            # ENOENT means the target died between RECV and SEND. Anything else
            # is a defect in this file and is not swallowed.
            if exc.errno != errno.ENOENT:
                raise

    def poll_once(self) -> Attempt | None:
        """Receive and answer exactly one notification. Blocks."""
        buf = bytearray(self.sizes.notif)
        try:
            fcntl.ioctl(self.fd, self._recv, buf)
        except OSError as exc:
            if exc.errno in (errno.EINTR, errno.ENOENT):
                return None
            raise
        attempt, notif_id = self._parse(buf)
        if not self.id_valid(notif_id):
            return None
        self.observed += 1
        self.on_attempt(attempt)
        self._respond_continue(notif_id)
        return attempt

    # --- the loop ----------------------------------------------------------

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.poll_once()
            except OSError:
                # The descriptor went away: the target exited and the filter
                # went with it. Not an error; the session is over.
                return

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._loop, name="seccomp-notify", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        try:
            os.close(self.fd)
        except OSError:
            pass
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
