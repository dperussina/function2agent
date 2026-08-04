"""Thin `ctypes` bindings for the Linux facilities FR-048 through FR-050 use.

Separated from the mechanisms so that the mechanisms read as policy and this
file reads as the kernel interface. Nothing here makes a decision.

**OD-17**: import of this module is Linux-only by construction — every symbol
resolves against the platform libc and the syscall numbers are per-architecture
lookups that fail loudly rather than defaulting.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import os
import platform

_libc = ctypes.CDLL(ctypes.util.find_library("c") or "libc.so.6", use_errno=True)

# --- mount(2) flags --------------------------------------------------------
MS_RDONLY = 1
MS_NOSUID = 2
MS_NODEV = 4
MS_NOEXEC = 8
MS_REMOUNT = 32
MS_BIND = 4096
MS_REC = 16384
MS_PRIVATE = 1 << 18
MS_SLAVE = 1 << 19
MS_SHARED = 1 << 20

# --- umount2(2) ------------------------------------------------------------
MNT_DETACH = 2

# --- clone(2) / unshare(2) namespace flags ---------------------------------
CLONE_NEWNS = 0x00020000
CLONE_NEWUTS = 0x04000000
CLONE_NEWIPC = 0x08000000
CLONE_NEWUSER = 0x10000000
CLONE_NEWPID = 0x20000000
CLONE_NEWNET = 0x40000000

# --- seccomp(2) ------------------------------------------------------------
SECCOMP_SET_MODE_FILTER = 1
SECCOMP_GET_NOTIF_SIZES = 3
SECCOMP_FILTER_FLAG_NEW_LISTENER = 1 << 3

SECCOMP_RET_ALLOW = 0x7FFF0000
SECCOMP_RET_ERRNO = 0x00050000
SECCOMP_RET_USER_NOTIF = 0x7FC00000

SECCOMP_USER_NOTIF_FLAG_CONTINUE = 1

PR_SET_NO_NEW_PRIVS = 38

# Architecture-dependent syscall numbers, looked up rather than assumed.
# A machine that is not in the table fails loudly; guessing a syscall number is
# how a security mechanism silently becomes a no-op.
_SYSCALL_NUMBERS = {
    "x86_64": {
        "seccomp": 317,
        "pivot_root": 155,
        "openat": 257,
        "open": 2,
        "stat": 4,
        "lstat": 6,
        "newfstatat": 262,
        "statx": 332,
        "unlink": 87,
        "unlinkat": 263,
        "rename": 82,
        "renameat2": 316,
        "mkdir": 83,
        "mkdirat": 258,
        "readlink": 89,
        "readlinkat": 267,
        "access": 21,
        "faccessat": 269,
        "faccessat2": 439,
        "chdir": 80,
        "truncate": 76,
        "chmod": 90,
        "fchmodat": 268,
    },
    "aarch64": {
        "seccomp": 277,
        "pivot_root": 41,
        "openat": 56,
        "newfstatat": 79,
        "statx": 291,
        "unlinkat": 35,
        "renameat2": 276,
        "mkdirat": 34,
        "readlinkat": 78,
        "faccessat": 48,
        "faccessat2": 439,
        "chdir": 49,
        "truncate": 45,
        "fchmodat": 53,
    },
}
_SYSCALL_NUMBERS["arm64"] = _SYSCALL_NUMBERS["aarch64"]

# `AUDIT_ARCH_*` from <linux/audit.h>, needed by the seccomp BPF prologue that
# refuses to run a filter written for a different architecture.
AUDIT_ARCH_X86_64 = 0xC000003E
AUDIT_ARCH_AARCH64 = 0xC00000B7
_AUDIT_ARCH = {
    "x86_64": AUDIT_ARCH_X86_64,
    "aarch64": AUDIT_ARCH_AARCH64,
    "arm64": AUDIT_ARCH_AARCH64,
}


class LinuxFacilityError(OSError):
    """A kernel call failed. Always carries errno and the call that failed."""


def machine() -> str:
    return platform.machine()


def audit_arch() -> int:
    try:
        return _AUDIT_ARCH[machine()]
    except KeyError:
        raise LinuxFacilityError(
            f"no AUDIT_ARCH constant recorded for {machine()!r}. Add it rather "
            "than defaulting: a seccomp filter whose architecture check does "
            "not match is a filter that never fires."
        ) from None


def syscall_number(name: str) -> int:
    table = _SYSCALL_NUMBERS.get(machine())
    if table is None:
        raise LinuxFacilityError(
            f"no syscall table recorded for machine {machine()!r}. Add one "
            "rather than guessing a number."
        )
    try:
        return table[name]
    except KeyError:
        raise LinuxFacilityError(
            f"syscall {name!r} has no recorded number on {machine()!r}"
        ) from None


def path_taking_syscalls() -> dict[str, int]:
    """The syscalls FR-048's recording clause has to see.

    Every syscall in this set takes a path and can therefore reach outside the
    declared location set. `open`/`stat`/`lstat` and friends do not exist on
    `aarch64` (glibc uses `openat`/`newfstatat`), so the set is derived from
    the architecture's own table rather than assumed uniform.
    """
    table = _SYSCALL_NUMBERS.get(machine())
    if table is None:
        raise LinuxFacilityError(f"no syscall table for {machine()!r}")
    names = (
        "open", "openat", "stat", "lstat", "newfstatat", "statx",
        "unlink", "unlinkat", "rename", "renameat2", "mkdir", "mkdirat",
        "readlink", "readlinkat", "access", "faccessat", "faccessat2",
        "chdir", "truncate", "chmod", "fchmodat",
    )
    return {n: table[n] for n in names if n in table}


def _check(rc: int, call: str, *detail: object) -> int:
    if rc < 0 or rc == -1:
        err = ctypes.get_errno()
        raise LinuxFacilityError(
            err,
            f"{call}({', '.join(repr(d) for d in detail)}) failed: "
            f"{os.strerror(err)}",
        )
    return rc


def mount(source: str | None, target: str, fstype: str | None,
          flags: int, data: str | None = None) -> None:
    ctypes.set_errno(0)
    rc = _libc.mount(
        source.encode() if source else None,
        target.encode(),
        fstype.encode() if fstype else None,
        ctypes.c_ulong(flags),
        data.encode() if data else None,
    )
    _check(rc, "mount", source, target, fstype, hex(flags), data)


def umount2(target: str, flags: int = 0) -> None:
    ctypes.set_errno(0)
    _check(_libc.umount2(target.encode(), flags), "umount2", target, flags)


def unshare(flags: int) -> None:
    ctypes.set_errno(0)
    _check(_libc.unshare(ctypes.c_int(flags)), "unshare", hex(flags))


def pivot_root(new_root: str, put_old: str) -> None:
    ctypes.set_errno(0)
    rc = _libc.syscall(
        ctypes.c_long(syscall_number("pivot_root")),
        new_root.encode(),
        put_old.encode(),
    )
    _check(rc, "pivot_root", new_root, put_old)


def set_no_new_privs() -> None:
    """Required before `seccomp(SET_MODE_FILTER)` for an unprivileged caller.

    Set unconditionally: a filter installed with `no_new_privs` off can be
    escaped by a setuid exec, and the whole point of the filter is that it
    cannot be.
    """
    ctypes.set_errno(0)
    _check(_libc.prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0), "prctl(NO_NEW_PRIVS)")


def seccomp(operation: int, flags: int, args: ctypes.Array | None) -> int:
    ctypes.set_errno(0)
    rc = _libc.syscall(
        ctypes.c_long(syscall_number("seccomp")),
        ctypes.c_ulong(operation),
        ctypes.c_ulong(flags),
        args,
    )
    return _check(rc, "seccomp", operation, hex(flags))
