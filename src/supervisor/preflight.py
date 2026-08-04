"""T006 — the Linux-facility preflight. **OD-17**: Linux only, no degraded mode.

All three of FR-048, FR-049 and FR-050's mechanisms are kernel facilities. A
host missing one of them cannot supply the corresponding term of constitution
Principle IV bullet 1, and the bullet's own words are that a configuration
missing any term does not satisfy it. So this check fails loudly rather than
degrading, and there is no flag that turns it off.

Every check reports what it looked for and what it found, because a preflight
that says only "unsupported" makes an operator guess.
"""

from __future__ import annotations

import ctypes
import os
import platform
from dataclasses import dataclass
from pathlib import Path

CGROUP2_ROOT = Path("/sys/fs/cgroup")

# seccomp(2) constants. Values are the kernel's UAPI numbers, identical on every
# Linux architecture.
SECCOMP_SET_MODE_FILTER = 1
SECCOMP_FILTER_FLAG_NEW_LISTENER = 1 << 3
SECCOMP_GET_NOTIF_SIZES = 3

# Controllers FR-049 needs. `cpuset`, `io`, `hugetlb` and `rdma` may be present
# and are not required.
REQUIRED_CGROUP_CONTROLLERS = ("memory", "cpu", "pids")


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str
    requirement: str


class PreflightError(RuntimeError):
    """A required kernel facility is missing. There is no degraded mode."""


def _check_platform() -> Check:
    system = platform.system()
    return Check(
        name="platform",
        ok=system == "Linux",
        detail=f"platform.system()={system!r} release={platform.release()!r}",
        requirement="OD-17",
    )


def _check_cgroup_v2() -> Check:
    controllers_file = CGROUP2_ROOT / "cgroup.controllers"
    if not controllers_file.is_file():
        return Check(
            "cgroup_v2",
            False,
            f"{controllers_file} absent — cgroup v2 is not mounted at "
            f"{CGROUP2_ROOT} (a cgroup v1 host has controller directories "
            "instead of this file)",
            "FR-049",
        )
    available = set(controllers_file.read_text().split())
    missing = [c for c in REQUIRED_CGROUP_CONTROLLERS if c not in available]
    return Check(
        "cgroup_v2",
        not missing,
        f"available={sorted(available)} required={list(REQUIRED_CGROUP_CONTROLLERS)}"
        + (f" MISSING={missing}" if missing else ""),
        "FR-049",
    )


def _check_cgroup_delegation() -> Check:
    """The supervisor must be able to create a child cgroup and set the bounds.

    FR-049 requires the bound to be enforced *from outside* the environment, so
    the supervisor creates and owns the cgroup before the container starts. If
    it cannot write here, T102 cannot run and the bound would have to be set
    from inside, which is what FR-049 forbids.
    """
    probe = CGROUP2_ROOT / ".f2a-preflight-probe"
    try:
        probe.mkdir(exist_ok=True)
    except OSError as exc:
        return Check(
            "cgroup_delegation",
            False,
            f"cannot create a child cgroup under {CGROUP2_ROOT}: {exc}. The "
            "supervisor must own the session cgroup before the container "
            "starts (FR-049's enforced-from-outside clause).",
            "FR-049",
        )
    try:
        subtree = (CGROUP2_ROOT / "cgroup.subtree_control")
        enabled = subtree.read_text().split() if subtree.is_file() else []
        return Check(
            "cgroup_delegation",
            True,
            f"created and removed {probe}; root subtree_control={enabled}",
            "FR-049",
        )
    finally:
        try:
            probe.rmdir()
        except OSError:
            pass


def _check_namespaces() -> Check:
    """Mount and user namespaces, which FR-048's mechanism is built on."""
    missing = [
        n for n in ("mnt", "user", "pid", "net")
        if not Path(f"/proc/self/ns/{n}").exists()
    ]
    if missing:
        return Check(
            "namespaces",
            False,
            f"/proc/self/ns/ is missing {missing} — the kernel was built "
            "without them",
            "FR-048",
        )
    maxns = Path("/proc/sys/user/max_user_namespaces")
    limit = maxns.read_text().strip() if maxns.is_file() else "unreadable"
    ok = limit not in ("0",)
    return Check(
        "namespaces",
        ok,
        f"mnt/user/pid/net present; max_user_namespaces={limit}"
        + ("" if ok else " — user namespaces are administratively disabled"),
        "FR-048",
    )


def _check_seccomp_user_notification() -> Check:
    """SECCOMP_FILTER_FLAG_NEW_LISTENER, which FR-048's *recording* clause needs.

    Probed by asking the kernel for the notification structure sizes. That
    operation exists only on a kernel with user notification compiled in, and
    unlike installing a filter it has no effect on this process.
    """
    if platform.system() != "Linux":
        return Check(
            "seccomp_user_notification",
            False,
            "not Linux",
            "FR-048",
        )
    libc = ctypes.CDLL(None, use_errno=True)

    class Sizes(ctypes.Structure):
        _fields_ = [
            ("seccomp_notif", ctypes.c_uint16),
            ("seccomp_notif_resp", ctypes.c_uint16),
            ("seccomp_data", ctypes.c_uint16),
        ]

    sizes = Sizes()
    ctypes.set_errno(0)
    rc = libc.syscall(
        _SECCOMP_NR,
        ctypes.c_ulong(SECCOMP_GET_NOTIF_SIZES),
        ctypes.c_ulong(0),
        ctypes.byref(sizes),
    )
    if rc != 0:
        err = ctypes.get_errno()
        return Check(
            "seccomp_user_notification",
            False,
            f"seccomp(SECCOMP_GET_NOTIF_SIZES) failed errno={err} "
            f"({os.strerror(err)}) — the kernel lacks "
            "CONFIG_SECCOMP_FILTER user notification. FR-048's recording "
            "clause and SC-022 cannot be satisfied without it, and Q-09's "
            "fallback (an after-the-fact audit channel) is a different "
            "mechanism that must be chosen deliberately, not fallen into.",
            "FR-048",
        )
    return Check(
        "seccomp_user_notification",
        True,
        f"notif={sizes.seccomp_notif}B resp={sizes.seccomp_notif_resp}B "
        f"data={sizes.seccomp_data}B",
        "FR-048",
    )


# __NR_seccomp. Architecture-specific, so it is looked up rather than assumed.
_SECCOMP_NR_BY_MACHINE = {
    "x86_64": 317,
    "aarch64": 277,
    "arm64": 277,
}
_SECCOMP_NR = _SECCOMP_NR_BY_MACHINE.get(platform.machine(), -1)


def run_checks() -> list[Check]:
    """Every check, always all of them, so one failure does not hide another."""
    checks = [_check_platform()]
    if checks[0].ok:
        checks.append(_check_cgroup_v2())
        checks.append(_check_cgroup_delegation())
        checks.append(_check_namespaces())
        if _SECCOMP_NR < 0:
            checks.append(
                Check(
                    "seccomp_user_notification",
                    False,
                    f"__NR_seccomp is unknown for machine "
                    f"{platform.machine()!r}; add it to "
                    "_SECCOMP_NR_BY_MACHINE rather than guessing",
                    "FR-048",
                )
            )
        else:
            checks.append(_check_seccomp_user_notification())
    return checks


def preflight() -> list[Check]:
    """Run every check and raise on the first failing one, naming all of them."""
    checks = run_checks()
    failed = [c for c in checks if not c.ok]
    if failed:
        lines = [
            "Linux-facility preflight FAILED. This platform is unsupported "
            "and there is no degraded mode (OD-17, FR-053).",
            "",
        ]
        for c in checks:
            mark = "ok  " if c.ok else "FAIL"
            lines.append(f"  [{mark}] {c.name} ({c.requirement}): {c.detail}")
        lines += [
            "",
            "A degraded mode would be a sandbox missing one of constitution "
            "Principle IV bullet 1's terms, and the bullet's own words are "
            "that a configuration missing any term does not satisfy it.",
        ]
        raise PreflightError("\n".join(lines))
    return checks


if __name__ == "__main__":  # pragma: no cover - operator utility
    import sys

    try:
        for c in preflight():
            print(f"  [ok  ] {c.name} ({c.requirement}): {c.detail}")
    except PreflightError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
    print("preflight OK")
