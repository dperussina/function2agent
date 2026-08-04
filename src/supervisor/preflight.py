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

# ---------------------------------------------------------------------------
# The minimum kernel, and how it was arrived at.
#
# **OD-17 says Linux and names no version.** The floor below is derived from the
# documented introduction of the facilities this code actually calls, not from a
# kernel anybody here ran. Each entry names the facility, the release, and the
# call site, so a future reader can re-derive it instead of trusting it.
#
#   5.0   seccomp user notification: SECCOMP_RET_USER_NOTIF,
#         SECCOMP_FILTER_FLAG_NEW_LISTENER, SECCOMP_GET_NOTIF_SIZES.
#   5.5   SECCOMP_USER_NOTIF_FLAG_CONTINUE — FR-048's whole design. Without it
#         the supervisor can only permit or deny, not observe-and-continue.
#   5.9   SECCOMP_IOCTL_NOTIF_ID_VALID's ioctl number was corrected from _IOR to
#         _IOW. `seccomp.py` defines the corrected number, so on 5.5–5.8 that
#         ioctl returns EINVAL. The kernel keeps an alias for the old number, so
#         this is a property of *our* definition and not of the kernel; it is
#         recorded because it is invisible at the call site.
#   5.14  `cgroup.kill` — atomic group kill. `cgroup.kill` is the binding
#         constraint and the reason the floor is not 5.9.
#
# **Why cgroup.kill is required rather than optional.** `CgroupSession.kill_all`
# falls back to iterating `cgroup.procs` and signalling each pid. That loop has
# exactly the fork race `cgroup.kill` was added to close: a process can fork
# between the listing and the kill and the child survives the round. FR-049's
# process bound is what stops a fork bomb, so a silent fallback to the racy path
# on an old kernel weakens the bound the operator believes they configured.
#
# **This floor is DERIVED, NOT TESTED.** Everything here has run on 6.12
# (`6.12.76-linuxkit`, locally) and on 6.17 (`6.17.0-1020-azure`, the
# `ubuntu-latest` runner, first observed 2026-08-04). An earlier version of this
# comment asserted the runner was also 6.12; that was written before CI had ever
# run and the first run falsified it. Nothing was run on 5.14,
# and "the facility exists in 5.14" is a weaker claim than "this code works on
# 5.14" — semantics around cgroup delegation, `pivot_root` in a user namespace,
# and seccomp notification lifetimes have all changed within the 5.x series in
# ways this list does not capture. Establishing a *tested* floor needs boots of
# 5.14, 5.15 LTS, 6.1 LTS and 6.6 LTS, which is a CI matrix and not something
# derivable by reading. Until that runs, the floor is a lower bound on what
# could work, not a statement that 5.14 does.
MINIMUM_KERNEL = (5, 14)
MINIMUM_KERNEL_BASIS = (
    "cgroup.kill (Linux 5.14). Binding over "
    "SECCOMP_USER_NOTIF_FLAG_CONTINUE (5.5) and the corrected "
    "SECCOMP_IOCTL_NOTIF_ID_VALID ioctl number (5.9)."
)
MINIMUM_KERNEL_IS_TESTED = False


def _parse_release(release: str) -> tuple[int, int] | None:
    """`6.12.76-linuxkit` -> (6, 12). None if it does not parse.

    Deliberately refuses to guess: a release string this cannot parse produces
    a failed check naming the string, rather than a default that lets an
    unknown kernel through.
    """
    head = release.split("-", 1)[0]
    parts = head.split(".")
    if len(parts) < 2:
        return None
    try:
        return (int(parts[0]), int(parts[1]))
    except ValueError:
        return None


def _check_kernel_version() -> Check:
    release = platform.release()
    parsed = _parse_release(release)
    if parsed is None:
        return Check(
            "kernel_version", False,
            f"could not parse a version out of release={release!r}. Refusing "
            "to assume it is new enough; the floor is "
            f"{MINIMUM_KERNEL[0]}.{MINIMUM_KERNEL[1]} because of "
            f"{MINIMUM_KERNEL_BASIS}",
            "OD-17, FR-048, FR-049",
        )
    floor = f"{MINIMUM_KERNEL[0]}.{MINIMUM_KERNEL[1]}"
    provenance = (
        "DERIVED from documented feature introduction and NOT TESTED on that "
        "kernel; every run to date was on 6.12 or 6.17"
    )
    if parsed < MINIMUM_KERNEL:
        return Check(
            "kernel_version", False,
            f"kernel {release} is below the {floor} floor. Basis: "
            f"{MINIMUM_KERNEL_BASIS} ({provenance})",
            "OD-17, FR-048, FR-049",
        )
    return Check(
        "kernel_version", True,
        f"kernel {release} >= {floor}. Floor basis: {MINIMUM_KERNEL_BASIS} "
        f"({provenance})",
        "OD-17, FR-048, FR-049",
    )


CGROUP_KILL_PROBE = ".f2a-preflight-kill-probe"

_WHY_CGROUP_KILL = (
    "Without it, killing a session means iterating cgroup.procs and "
    "signalling each pid, which loses the race against a process forking "
    "between the listing and the kill — the race FR-049's process bound "
    "exists to lose safely."
)


def _check_cgroup_kill(root: Path | None = None) -> Check:
    """`cgroup.kill` must exist rather than fall back to the racy loop.

    **Probed in a child cgroup, because the root is where the kernel documents
    it as absent.** cgroup v2 calls `cgroup.kill` "a write-only single value
    file which exists in non-root cgroups", so reading `CGROUP2_ROOT /
    "cgroup.kill"` asks a question whose answer is ABSENT on every correctly
    mounted host. It answered `present` on a developer machine only because a
    container gets a private cgroup namespace, in which the namespace root is
    itself a non-root cgroup — confirmed both ways on `6.12.76-linuxkit`. The
    root half has since been confirmed independently on 6.17: CI run
    30919271659 still carried the pre-fix probe, which read the root and
    reported ABSENT on the `ubuntu-latest` runner, where the cgroup namespace is
    the host's. That is the failure this probe exists to avoid, observed on a
    second kernel.

    So the probe creates a child cgroup, the same way `_check_cgroup_delegation`
    does, and that is also the *kind* of cgroup FR-049's bound is set on and
    that `kill_all` writes to. The check now asks about the cgroup the
    mechanism actually uses.

    A hierarchy that cannot be probed reports the mkdir failure rather than
    ABSENT: `preflight()` has no degraded mode, so a failure here is read by an
    operator looking for a way past it, and "no cgroup.kill on this kernel"
    sends them after an upgrade they may not need.
    """
    root = CGROUP2_ROOT if root is None else root
    probe = root / CGROUP_KILL_PROBE
    try:
        probe.mkdir(exist_ok=True)
    except OSError as exc:
        return Check(
            "cgroup_kill", False,
            f"cannot create a child cgroup at {probe} to probe for "
            f"cgroup.kill: {exc}. The file exists only in non-root cgroups, so "
            "there is nowhere else to look for it, and this is reported as a "
            f"failed probe rather than as an absent facility. {_WHY_CGROUP_KILL}",
            "FR-049",
        )
    try:
        path = probe / "cgroup.kill"
        present = path.exists()
        return Check(
            "cgroup_kill", present,
            f"{path} {'present' if present else 'ABSENT'} in a probe child "
            f"cgroup under {root}. {_WHY_CGROUP_KILL}",
            "FR-049",
        )
    finally:
        try:
            probe.rmdir()
        except OSError:
            pass


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
        checks.append(_check_kernel_version())
        checks.append(_check_cgroup_v2())
        checks.append(_check_cgroup_delegation())
        checks.append(_check_cgroup_kill())
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
