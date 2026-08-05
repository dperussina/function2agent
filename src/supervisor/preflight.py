"""T006 — the Linux-facility preflight. **OD-17**: Linux only, no degraded mode.

Each of FR-048, FR-049 and FR-050 depends on a kernel facility, and **the mapping
is not one facility per requirement.** FR-048 has two mechanisms — a mount
namespace that enforces its boundary and a `seccomp` user-notification listener
that records attempts against it, deliberately not collapsed into one; see
`seccomp.py` for why the recorder cannot be the enforcer. So the checks below
outnumber the requirements, and a host missing any one facility cannot supply the
term of constitution Principle IV bullet 1 that rests on it. The bullet's own
words are that a configuration missing any term does not satisfy it. So this
check fails loudly rather than degrading, and there is no flag that turns it off.

Every check reports what it looked for and what it found, because a preflight
that says only "unsupported" makes an operator guess.
"""

from __future__ import annotations

import ctypes
import errno as errno_module
import os
import platform
from dataclasses import dataclass, replace as _dc_replace
from pathlib import Path

CGROUP2_ROOT = Path("/sys/fs/cgroup")

# unshare(2) flags. Duplicated from `_linux.CLONE_NEWUSER` rather than imported:
# `_linux` resolves every symbol against the platform libc at import time and is
# Linux-only by construction, and preflight has to run on the platform it is
# about to refuse. `tests/unit/test_namespace_probe.py` asserts the two agree, so
# the copy cannot drift.
CLONE_NEWUSER = 0x10000000
UNSHARE_NOOP = 0

# `pivot_root(2)` syscall numbers, duplicated from `_linux._SYSCALL_NUMBERS`
# for the same reason `CLONE_NEWUSER` is duplicated: importing `_linux` would
# resolve every symbol against the platform libc at import time, and preflight
# has to run on the platform it is about to refuse.
# `tests/unit/test_pivot_root_probe.py` asserts the two agree and asserts the
# literals, so neither the copy nor the original can drift alone.
#
# **glibc exports no `pivot_root` wrapper**, so this goes through `syscall(2)`
# and the number is the whole interface. A number that is wrong for the running
# architecture calls a different syscall and its answer would be read as this
# one's — 41 is `pivot_root` on `aarch64` and `dup` on Darwin. So an
# architecture absent from this table produces an unattempted probe rather than
# a default, matching `_SECCOMP_NR_BY_MACHINE` below, and `_attempt_pivot_root`
# refuses outright on a non-Linux kernel.
_PIVOT_ROOT_NR_BY_MACHINE = {
    "x86_64": 155,
    "aarch64": 41,
    "arm64": 41,
}

# The errnos this classifier has a reading for. Written as literals rather than
# read from the `errno` module because they must be *Linux's* numbers whatever
# host is doing the reading; all four happen to agree with macOS today, which
# is exactly the kind of coincidence that stops being true silently.
#
# **The split below is `path_pivot_root()`'s own ordering, read from
# `fs/namespace.c`, and it is the whole basis of the classification.** The
# function runs its two authority gates first and every argument check after:
#
#   1. `if (!may_mount()) return -EPERM;`          <- the CAP_SYS_ADMIN gate
#   2. `error = security_sb_pivotroot(old, new);`  <- the LSM hook
#   3. `if (IS_MNT_SHARED(...)) return -EINVAL;`   <- first argument check
#      ... `-EINVAL`, `-ENOENT`, `-EBUSY`, `-EINVAL` ...
#
# So an errno from step 3 onwards is *positive evidence that both authority
# gates passed*. `_AUTHORITY_ERRNOS` is step 1 and step 2;
# `_POST_AUTHORITY_ERRNOS` is what step 3 onwards produces for `("/", "/")`.
#
# **`EACCES` is in the authority set and that is not obvious.** The LSM hook at
# step 2 returns whatever the LSM returns, and AppArmor's returns `-EACCES` —
# `security/apparmor/mount.c`'s `build_pivotroot()` sets `error = -EACCES` and
# clears it only for a profile carrying `AA_MAY_PIVOTROOT`. TOMOYO is the only
# other LSM implementing `sb_pivotroot`; SELinux and Smack register no hook for
# it at all. A classifier built on "any errno other than EPERM proves the call
# reached the kernel" would therefore read an AppArmor refusal as `available`,
# which is the same inverted verdict as scoring `EBUSY` a refusal, reached from
# the other side.
#
# **Why `("/", "/")` answers `EINVAL` on one host and `EBUSY` on another, and
# why that is not about authority.** Step 3's `MS_SHARED` propagation check
# precedes the `new_mnt == root_mnt` check that yields `EBUSY`. On a systemd
# host `/` is mounted shared, so the propagation check fires first and the
# answer is `EINVAL`; inside a container whose root propagation is private it
# does not fire and the answer is `EBUSY`. Docker gave `EBUSY` (finding 026
# arms B2, B3) and the `ubuntu-latest` runner gives `EINVAL` (CI run
# 30970910828) for exactly that reason. The man page documents `EBUSY` as the
# answer for the `new_root == "/"` case and separately documents four `EINVAL`
# causes including the `MS_SHARED` one; the kernel's ordering is what decides
# which of the two a given host reports.
_EPERM = 1
_ENOENT = 2
_EACCES = 13
_EBUSY = 16
_EINVAL = 22

#: The second half of the discriminating pair. A path that does not exist, so
#: `user_path_at()` fails before anything else can run and the kernel's answer is
#: ENOENT. Named rather than computed so it appears verbatim in the message an
#: operator reads, and deliberately not a real mount point: `("/proc", "/proc")`
#: was tried and **returned 0**, pivoting the probe child's root. See
#: `_attempt_pivot_root_pair`.
_ABSENT_PROBE_PATH = b"/f2a-preflight-no-such-path"

#: Refusals by an authority gate. Never evidence the syscall is permitted, at
#: any filter posture.
_AUTHORITY_ERRNOS = frozenset({_EPERM, _EACCES})

#: Errnos `path_pivot_root()` reaches only after both authority gates. Seeing
#: one means the call got through them — *provided* no seccomp filter is
#: installed to have manufactured it. Deliberately a closed list rather than
#: "everything not in `_AUTHORITY_ERRNOS`": an errno nobody has placed in the
#: kernel's control flow must fail closed. `ENOSYS` is the case that makes the
#: difference — with no filter installed it means the kernel does not implement
#: the syscall, which is the opposite of available.
_POST_AUTHORITY_ERRNOS = frozenset({_EBUSY, _EINVAL})

# `CAP_SYS_ADMIN` is capability bit 21. It is the kernel's own gate on
# `pivot_root`, which is why the posture has to be read before an `EPERM` can
# be attributed to anything.
CAP_SYS_ADMIN_BIT = 21

# `Seccomp` in `/proc/self/status`: 0 no filter, 1 strict mode, 2 filter mode.
# Only `0` is load-bearing here — it is the one value that rules out a
# `defaultErrnoRet` — so the other modes are not named as constants and are
# handled as "some filter posture that is not none".
SECCOMP_MODE_DISABLED = 0

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
    # Which layer produced the answer, where the check can tell. Defaulted, so
    # the checks that have only one possible refusing layer are unchanged; it is
    # the `namespaces` check that needs it, because four layers can refuse there
    # and they have four different remedies.
    layer: str | None = None


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


# ---------------------------------------------------------------------------
# T206 — the real `unshare` pair.
#
# **Presence and a sysctl are not evidence a mechanism works.** The check below
# used to establish user namespaces by reading `/proc/self/ns/` and
# `max_user_namespaces`, which report kernel-build presence and an
# administrative setting. Neither is a syscall attempt, so on a host whose
# container runtime refuses `unshare` in its seccomp profile both read yes and
# the check reported green — for a mechanism that does not work there. Measured
# in findings/024-deployment-surface-permission-census.md, which ran one probe
# across eight container configurations, **none of them `--privileged`**.
#
# **Why there are two arms.** Docker's default profile carries no rule about
# `CLONE_NEWUSER`. It carries a rule on the whole `unshare` *syscall*, gated on
# `CAP_SYS_ADMIN`, with `defaultAction` `SCMP_ACT_ERRNO` and `defaultErrnoRet` 1
# (`EPERM`). A rule on the syscall refuses every call, so `unshare(0)` — which
# asks for nothing, and which no kernel namespace check can refuse, because
# there is no namespace to refuse — also returns `EPERM`. That one call is the
# only thing separating a seccomp refusal from every other layer: an LSM hook, a
# sysctl, a chroot and a missing kernel config all permit the no-op and refuse
# the flag. It costs one syscall and it is the entire diagnostic value here.

LAYER_AVAILABLE = "available"
LAYER_RUNTIME_SECCOMP = "runtime-seccomp-profile"
LAYER_KERNEL_OR_LSM = "kernel-sysctl-or-lsm"
LAYER_INCOHERENT = "incoherent"
LAYER_NOT_ATTEMPTED = "not-attempted"
LAYER_KERNEL_BUILD = "kernel-build"
LAYER_SYSCTL_DISABLED = "sysctl-administratively-disabled"
# T207. The `pivot_root` check needs one layer the pair does not, because it
# has no no-op arm. `unshare(0)` separates a syscall-level filter from every
# kernel-side refusal for free; `pivot_root` has no call that asks for nothing,
# so a refusal whose posture does not license an attribution is reported as
# unattributed rather than resolved into the likelier of two remedies.
LAYER_REFUSED_UNATTRIBUTED = "refused-unattributed"

# Exit codes the probe child speaks back through. errno on Linux tops out at 133
# (`EHWPOISON`), so 1..200 encodes an errno unambiguously and the two codes above
# that are reserved for "the child could not make the call at all" — which is an
# absence of evidence and must never be read as a refusal.
_ERRNO_MAX = 200
_CODE_CHILD_FAILED = 201
_CODE_ERRNO_UNENCODABLE = 202
# T207. `pivot_root` returns 0 or -1 and nothing else, so any other return is
# evidence that the syscall number was wrong for this architecture rather than
# evidence about `pivot_root`. It must not be readable as either a success or a
# refusal; it is an absence of evidence, and it is kept distinct from
# `_CODE_CHILD_FAILED` so the message can say which of the two happened.
_CODE_RETURN_UNEXPECTED = 203

_REMEDY_RUNTIME_SECCOMP = (
    "REFUSING LAYER: your container runtime's seccomp profile. Both arms were "
    "refused, and a refused no-op can only come from a rule on the unshare "
    "syscall itself — Docker's default profile gates the whole syscall on "
    "CAP_SYS_ADMIN and falls through to defaultAction SCMP_ACT_ERRNO/EPERM. "
    "MEASURED (finding 024), uid 1000 with --cap-drop=ALL, not --privileged. "
    "REMEDY: run the session with a custom seccomp profile. It is Docker's own "
    "default plus one added syscall name — 426 allow-listed names becomes 427 — "
    "so keyctl, add_key, userfaultfd, kexec_load, swapon and the rest stay "
    "denied. The bundle ships one (T206's sibling T160); the flag is "
    "--security-opt seccomp=<profile.json>. "
    "DO NOT USE --cap-add=SYS_ADMIN. The profile writes its unshare rule as a "
    "capability gate, so that is the change this error invites, it is by a wide "
    "margin the most dangerous one available, and IT DOES NOT WORK: pivot_root "
    "appears in no rule of the profile at all, so it returns EPERM even with the "
    "capability held. The whole mount tree builds correctly and then fails at "
    "the final containment step, which reads as a broken mechanism rather than "
    "as a wrong grant. Do not reach for seccomp=unconfined either; it removes "
    "the entire filter rather than one rule."
)

_REMEDY_KERNEL_OR_LSM = (
    "REFUSING LAYER: not the container runtime's seccomp profile. unshare(0) "
    "was permitted, and a syscall-level seccomp rule would have refused the "
    "no-op too, so shipping a seccomp profile would not help here. What is left "
    "is one of the refusals inside create_user_ns(), and this check cannot tell "
    "them apart, so it reports the errno above rather than naming one: a chroot "
    "(EPERM), the caller's own uid unmapped in the parent namespace (EPERM), the "
    "user.max_user_namespaces ucount limit or a nesting depth over 32 (ENOSPC), "
    "an out-of-tree sysctl such as Debian's kernel.unprivileged_userns_clone, an "
    "LSM hook reached through security_create_user_ns() — Ubuntu 24.04's "
    "kernel.apparmor_restrict_unprivileged_userns is the common case — or a "
    "systemd unit directive, RestrictNamespaces= or PrivateUsers=. REMEDY: the "
    "bundle cannot supply one. The host has to change. "
    "DERIVED, NOT MEASURED: finding 024 could construct neither an LSM refusal "
    "nor a sysctl one on its measuring host — Docker Desktop's linuxkit VM "
    "carries no AppArmor and no SELinux, and the LSM is exactly what refuses on "
    "Ubuntu 24.04 — so this branch's candidate list comes from a source read of "
    "create_user_ns() at v6.12 and not from an observed refusal. Only the ENOSPC "
    "nesting limit was measured (NC-3)."
)


@dataclass(frozen=True)
class UnshareAttempt:
    """One forked-child `unshare(2)` call: what was asked, what the kernel said.

    `attempted` is False when the call could not be made at all — a libc with no
    `unshare` symbol, a `fork` that failed, a child that died on a signal. That
    is deliberately not the same state as a refusal: `preflight()` has no
    degraded mode, so every failure it prints is read by an operator looking for
    a way past it, and reporting "I could not ask" as "the host said no" sends
    them after a change they do not need. Same discipline the `cgroup.kill`
    probe follows when it cannot create a child cgroup.
    """

    flags: int
    attempted: bool
    ok: bool
    errno: int | None
    note: str

    def describe(self) -> str:
        label = "unshare(0)" if self.flags == UNSHARE_NOOP else (
            f"unshare({hex(self.flags)})"
        )
        if not self.attempted:
            return f"{label} NOT ATTEMPTED ({self.note})"
        if self.ok:
            return f"{label} ok"
        if self.errno is None:
            return f"{label} FAILED ({self.note})"
        name = errno_module.errorcode.get(self.errno, str(self.errno))
        return f"{label} {name} (errno {self.errno}: {os.strerror(self.errno)})"


def _attempt_unshare(flags: int) -> UnshareAttempt:
    """`unshare(flags)` in a forked child, so this process is never moved.

    **Forked because `unshare(2)` mutates the calling process.** A preflight that
    put the supervisor into a user namespace as a side effect of asking whether
    it could would have changed the thing it was measuring, and every later check
    would run in a namespace nobody asked for. The child is discarded, so the
    only thing that crosses back is an exit code.
    """
    libc = ctypes.CDLL(None, use_errno=True)
    try:
        libc.unshare
    except AttributeError:
        return UnshareAttempt(
            flags, False, False, None,
            "this libc exports no unshare(2) symbol, so the call was never "
            "made — that is an absence of evidence, not a refusal",
        )
    try:
        pid = os.fork()
    except OSError as exc:
        return UnshareAttempt(
            flags, False, False, None, f"fork() for the probe child failed: {exc}"
        )
    if pid == 0:  # pragma: no cover - the child never returns to the collector
        code = _CODE_CHILD_FAILED
        try:
            ctypes.set_errno(0)
            rc = libc.unshare(ctypes.c_int(flags))
            if rc == 0:
                code = 0
            else:
                err = ctypes.get_errno()
                code = err if 1 <= err <= _ERRNO_MAX else _CODE_ERRNO_UNENCODABLE
        except BaseException:
            code = _CODE_CHILD_FAILED
        os._exit(code)
    _, status = os.waitpid(pid, 0)
    if not os.WIFEXITED(status):
        signal_number = os.WTERMSIG(status) if os.WIFSIGNALED(status) else None
        return UnshareAttempt(
            flags, False, False, None,
            f"the probe child did not exit normally (signal {signal_number}); "
            "nothing can be concluded about the syscall from that",
        )
    code = os.WEXITSTATUS(status)
    if code == 0:
        return UnshareAttempt(flags, True, True, None, "the call returned 0")
    if code == _CODE_CHILD_FAILED:
        return UnshareAttempt(
            flags, False, False, None,
            "the probe child raised before it could report an errno",
        )
    if code == _CODE_ERRNO_UNENCODABLE:
        return UnshareAttempt(
            flags, True, False, None,
            f"the call failed with an errno above {_ERRNO_MAX}, which the "
            "child's exit code cannot carry",
        )
    return UnshareAttempt(flags, True, False, code, "the call failed")


def _classify_unshare_pair(
    noop: UnshareAttempt, newuser: UnshareAttempt
) -> tuple[bool, str, str]:
    """The four cells of the pair, as `(ok, layer, message)`. No syscalls here.

    Kept separate from the probe so the table can be exercised on a host that
    cannot run any of it, which is every developer machine that is not Linux.
    """
    observed = f"{noop.describe()}; {newuser.describe()}"
    if not noop.attempted or not newuser.attempted:
        return (
            False,
            LAYER_NOT_ATTEMPTED,
            f"{observed}. The syscall could not be attempted, so this host is "
            "reported as unverified rather than as refused — there is no "
            "reading here at all, and no remedy follows from one.",
        )
    if noop.ok and newuser.ok:
        return (
            True,
            LAYER_AVAILABLE,
            f"{observed}. Both arms of the pair were permitted, in a forked "
            "child, so this process was not moved into any namespace.",
        )
    if not noop.ok and not newuser.ok:
        return False, LAYER_RUNTIME_SECCOMP, f"{observed}. {_REMEDY_RUNTIME_SECCOMP}"
    if noop.ok and not newuser.ok:
        return False, LAYER_KERNEL_OR_LSM, f"{observed}. {_REMEDY_KERNEL_OR_LSM}"
    return (
        False,
        LAYER_INCOHERENT,
        f"{observed}. The no-op was refused and the real namespace was granted. "
        "No layer produces that: unshare(0) asks for nothing, so anything that "
        "refuses it refuses the flagged call too. This is reported as "
        "incoherent rather than being resolved into a remedy, because guessing "
        "one from a reading nothing produces is how an operator is sent after a "
        "fix for a problem they do not have.",
    )


def _check_namespaces(
    attempt=None,
    ns_root: Path | None = None,
    maxns_path: Path | None = None,
) -> Check:
    """Mount and user namespaces, which FR-048's mechanism is built on.

    Three layers can refuse, and they are asked in the order that keeps each
    answer meaningful. A kernel built without the namespaces cannot have its
    `unshare` refused by a profile, and `max_user_namespaces=0` is an
    administrative refusal with its own fix — so both are read first, and the
    syscall is not attempted when either has already answered. What remains is
    the pair, which is the only arm that can see the container runtime.
    """
    attempt = _attempt_unshare if attempt is None else attempt
    ns_root = Path("/proc/self/ns") if ns_root is None else ns_root
    if maxns_path is None:
        maxns_path = Path("/proc/sys/user/max_user_namespaces")

    missing = [n for n in ("mnt", "user", "pid", "net")
               if not (ns_root / n).exists()]
    if missing:
        return Check(
            "namespaces",
            False,
            f"/proc/self/ns/ is missing {missing} — the kernel was built "
            "without them. Not attempting unshare(2): a kernel with no user "
            "namespaces cannot have one refused by a runtime profile, and "
            "reporting that layer here would be wrong.",
            "FR-048",
            LAYER_KERNEL_BUILD,
        )
    limit = maxns_path.read_text().strip() if maxns_path.is_file() else "unreadable"
    if limit == "0":
        return Check(
            "namespaces",
            False,
            f"mnt/user/pid/net present; max_user_namespaces={limit} — user "
            "namespaces are administratively disabled by the sysctl. Not "
            "attempting unshare(2): the refusal is already located, and it is "
            "raised with `sysctl -w user.max_user_namespaces=<n>` on the host.",
            "FR-048",
            LAYER_SYSCTL_DISABLED,
        )

    ok, layer, message = _classify_unshare_pair(
        attempt(UNSHARE_NOOP), attempt(CLONE_NEWUSER)
    )
    return Check(
        "namespaces",
        ok,
        f"mnt/user/pid/net present; max_user_namespaces={limit}; {message}",
        "FR-048",
        layer,
    )


# ---------------------------------------------------------------------------
# T207 — `pivot_root`, which is a separate syscall and therefore a separate
# check.
#
# **The gap this closes is in the check *set*, not in the check above.** Under
# `--cap-add=SYS_ADMIN` with Docker's unmodified default profile, `unshare`
# genuinely succeeds — measured as arms A5 and A6 of
# findings/025-preflight-unshare-pair-measured.md — so `_check_namespaces`
# reports `available` and is right to. Making it report a refusal there would
# be a false statement about the syscall it measures. But `pivot_root` appears
# in **no rule of that profile at all**, so it still returns `EPERM` with the
# capability held (probe arm P1), and `run_checks()` asked about it nowhere. An
# operator who applies the cgroup half of the bundle and then reaches for the
# capability instead of the profile got a wholly green preflight on a host
# where the mount tree builds correctly and `enter()` fails at the one step
# that establishes containment.
#
# **Permitted does not mean success, and that inverts the verdict if it is
# missed.** `pivot_root("/", "/")` cannot succeed — the kernel refuses a new
# root that is already the root — so the *permitted* reading here is a failure,
# meaning the call passed the filter and the kernel rejected the arguments.
# Finding 025 measured the pair as NC-6: `EPERM` under the default profile,
# `EBUSY` under the bundle's profile, one flag changed.
#
# **Which failure is a property of the host's mount topology, not of its
# authority, and pinning one errno cost this repository a red gate.** T207
# resolved `EBUSY` and nothing else, on six container arms that all produced
# it. CI run 30970910828 then produced `EINVAL` on the `ubuntu-latest` runner
# while holding the full capability set with no filter installed, and the check
# reported `refused-unattributed` — a refusal on a host that refuses nothing,
# which is the inverted verdict T207's own removal proofs were written to catch,
# arriving via a sibling errno the proof did not cover. `_POST_AUTHORITY_ERRNOS`
# above is the generalisation, and the `_EPERM`/`_EACCES` split beside it is the
# limit on it: the class is "errnos `path_pivot_root()` produces after its
# authority gates", not "errnos that are not `EPERM`".
#
# **Why the capability posture is read.** The kernel's own gate on `pivot_root`
# is `CAP_SYS_ADMIN` and it returns `EPERM` too, so `EPERM` has two sources and
# only a process holding the capability can tell them apart. `unshare` gets
# this for free from its no-op arm; there is no call to `pivot_root` that asks
# for nothing. The posture is therefore *read* from `/proc/self/status` rather
# than inferred from the uid or asserted from the invocation — finding 024's
# probe inferred a posture, wrote a uid map naming a uid it did not own, and
# every later `ok` in that sequence was meaningless.

_REMEDY_PIVOT_ROOT_SECCOMP = (
    "REFUSING LAYER: your container runtime's seccomp profile. pivot_root was "
    "refused with EPERM while this process holds CAP_SYS_ADMIN — and "
    "CAP_SYS_ADMIN is the kernel's own gate on pivot_root, so the gate is "
    "satisfied and what is left is a filter. "
    "MEASURED (finding 025, probe arm P1): Docker's unmodified default "
    "profile with --cap-add=SYS_ADMIN, uid 0, not --privileged. Its control "
    "(P2/NC-6) is the same probe with the same capability under the bundle's "
    "profile, which returns EBUSY — the call reaching the kernel. "
    "THE namespaces CHECK ABOVE MAY BE GREEN, AND IT IS RIGHT TO BE: under "
    "--cap-add=SYS_ADMIN unshare genuinely succeeds (finding 025, arms A5 and "
    "A6). pivot_root does not, and no capability changes that, because "
    "pivot_root appears in no rule of the default profile at all — not in the "
    "unconditional allow list and not in the CAP_SYS_ADMIN list — so it falls "
    "to defaultAction SCMP_ACT_ERRNO/EPERM whatever is held. "
    "DO NOT USE --cap-add=SYS_ADMIN. If you already have, this is that "
    "configuration and IT DOES NOT WORK: the whole mount tree builds "
    "correctly and then fails here, at the one step that establishes "
    "containment, which reads as a broken mechanism rather than as a wrong "
    "grant. It is also by a wide margin the most dangerous change available. "
    "REMEDY: run the session with a custom seccomp profile. It is Docker's "
    "own default plus one added syscall name — 426 allow-listed names becomes "
    "427 — and the one name it adds is pivot_root itself, so keyctl, add_key, "
    "userfaultfd, kexec_load, swapon and the rest stay denied. The bundle "
    "ships one (T160); the flag is --security-opt seccomp=<profile.json>. Do "
    "not reach for seccomp=unconfined either; it removes the entire filter "
    "rather than one rule."
)

_UNATTRIBUTED_PIVOT_ROOT = (
    "REFUSING LAYER: not determined, and this check will not guess between "
    "two candidates that produce the same errno. The kernel gates pivot_root "
    "on CAP_SYS_ADMIN and returns EPERM when it is absent; a seccomp profile "
    "with no rule for pivot_root refuses it with EPERM as well, because "
    "Docker's default profile carries defaultAction SCMP_ACT_ERRNO and "
    "defaultErrnoRet 1. unshare separates those two layers for free with its "
    "no-op arm, and pivot_root has no call that asks for nothing, so the only "
    "thing that separates them here is the capability this process holds. "
    "WHAT TO DO: re-run the preflight from a process that holds "
    "CAP_SYS_ADMIN. Under that posture an EPERM can only be the filter and "
    "this check says so, naming the profile to ship. Shipping one on the "
    "reading below would be acting on a refusal that has not been attributed "
    "to a profile at all. "
    "MEASURED (T207 arms P3, P4 and P5): this exact EPERM was produced at uid "
    "1000 with --cap-drop=ALL under three different filter configurations — "
    "Docker's default profile, which denies pivot_root; the bundle's profile, "
    "which allows it; and seccomp=unconfined, which installs no filter at all "
    "(Seccomp mode 0, 0 filters, read from /proc/self/status). Same errno in "
    "all three. P5 is the one that settles it: there was no filter to blame, "
    "so naming the seccomp profile on this reading would have told an "
    "operator to ship a profile on a host that had none — and P4 would have "
    "told one who had already shipped the right profile to ship it again. "
    "WHAT IS STILL DERIVED: that the kernel's capability gate and a filter "
    "are the *only* two sources of an EPERM here. An LSM hook or a "
    "distribution policy could add a third, none was constructible on the "
    "measuring host, and this message names two candidates rather than "
    "claiming the list is closed."
)


_EPERM_WITH_CAPABILITY_AND_NO_FILTER = (
    "REFUSING LAYER: not determined, and specifically NOT the container "
    "runtime's seccomp profile — there is no filter installed to be it. This "
    "process holds CAP_SYS_ADMIN, so the kernel's own may_mount() gate is "
    "satisfied, and Seccomp reads 0, so SCMP_ACT_ERRNO cannot have produced "
    "this either. What is left is the LSM hook path_pivot_root() calls before "
    "any argument check — security_sb_pivotroot(), which AppArmor answers with "
    "EACCES rather than EPERM, and TOMOYO with EPERM — or a distribution "
    "policy this check does not know about. "
    "DO NOT SHIP A SECCOMP PROFILE ON THIS READING. The bundle's profile "
    "would change nothing: no filter is refusing this. "
    "MEASURED, in part (finding 026 arms B6 and T207 arm P5): an EPERM here "
    "with Seccomp 0 and no filter to blame was observed, which is why naming a "
    "profile in this posture is indefensible rather than merely unproven. "
    "DERIVED, NOT MEASURED: those arms did not hold CAP_SYS_ADMIN, so the "
    "combination of a held capability, no filter and an EPERM has not been "
    "constructed anywhere, and the candidates named above are reasoned from "
    "path_pivot_root()'s ordering in fs/namespace.c rather than observed."
)

_EACCES_IS_AN_AUTHORITY_REFUSAL = (
    "REFUSING LAYER: an LSM, on the evidence of the errno itself. "
    "path_pivot_root() calls security_sb_pivotroot() after may_mount() and "
    "BEFORE every argument check, and AppArmor's hook denies with EACCES — "
    "security/apparmor/mount.c's build_pivotroot() sets error = -EACCES and "
    "clears it only for a profile carrying AA_MAY_PIVOTROOT. TOMOYO is the "
    "only other LSM that registers sb_pivotroot; SELinux and Smack register no "
    "hook for it. "
    "THIS IS WHY EACCES IS NOT READ AS THE CALL REACHING THE KERNEL even when "
    "no filter is installed: it is an authority refusal that happens to not be "
    "EPERM, and resolving it into a permit would report containment working on "
    "a host where an LSM refuses the syscall outright. "
    "REMEDY: the bundle cannot supply one, and a seccomp profile is not it. "
    "The host's LSM policy has to grant this profile pivot_root. "
    "DERIVED, NOT MEASURED: no arm of T207, finding 024, finding 025 or "
    "finding 026 produced EACCES here — no measuring surface available to this "
    "project carries an enforcing AppArmor or SELinux policy — so this branch "
    "is reasoned from the two source reads named above and not observed."
)

_UNKNOWN_ERRNO_UNDER_A_FILTER = (
    "This errno is not one this check has a reading for, and a seccomp filter "
    "is installed or its presence could not be read. EPERM is the kernel's "
    "capability gate; EACCES is the LSM hook; EBUSY and EINVAL are the call "
    "reaching the kernel's argument checks. Anything else is reported as found "
    "rather than resolved into a layer: SCMP_ACT_ERRNO with a defaultErrnoRet "
    "of ENOSYS — Podman's is — and a kernel that does not implement the "
    "syscall produce the same errno by different mechanisms, and with a filter "
    "in place this check cannot separate them."
)

_UNKNOWN_ERRNO_WITH_NO_FILTER = (
    "This errno is not one this check has a reading for. No filter is "
    "installed, so a defaultErrnoRet is not a candidate — but that does not "
    "make this a permit. EBUSY and EINVAL are resolved under Seccomp 0 because "
    "path_pivot_root() is known to produce them after its authority gates; an "
    "errno absent from that control flow is resolved into nothing. ENOSYS is "
    "the case that shows why: with no filter installed it means the kernel does "
    "not implement pivot_root at all, which is the opposite of available. So "
    "this cell fails closed rather than reasoning from an errno nobody has "
    "placed in the kernel's path."
)

_PAIR_DISCRIMINATED_PERMIT = (
    "pivot_root reached the kernel, and the PAIR is what establishes that "
    "rather than either errno on its own. Two invocations of the same syscall "
    "number, differing only in their two path pointers, produced two DIFFERENT "
    "errnos — and a seccomp filter cannot produce two different answers to "
    "those two calls. Its BPF program may not dereference pointers "
    "(Documentation/userspace-api/seccomp_filter.rst: 'BPF programs may not "
    "dereference pointers which constrains all filters to solely evaluating "
    "the system call arguments directly'), so it sees the same syscall number "
    "and the same architecture for both and must answer both the same way, "
    "before syscall entry. Something that can tell these two calls apart "
    "decided them, and the only thing that can is the kernel resolving the "
    "paths. Both authority gates were checked first and neither fired. "
    "THIS IS WHY THE SECCOMP MODE NO LONGER GATES THIS CELL: the ambiguity a "
    "defaultErrnoRet creates is resolved by measurement here rather than by "
    "assuming no filter is installed. Attempted in forked children, so this "
    "process's mount namespace was not moved. The absent path cannot succeed "
    "under any circumstances, which is why it is safe to issue: it fails at "
    "user_path_at() before any mount machinery runs. "
    "LIMIT: a SECCOMP_RET_USER_NOTIF or SECCOMP_RET_TRACE supervisor CAN read "
    "the tracee's memory and could answer the two differently. Container "
    "runtimes do not ship those, and the seccomp mode is still reported above "
    "so that posture stays visible."
)

_AUTHORITY_ERRNO_IN_THE_PAIR = (
    "REFUSING LAYER: not determined, and the pair does not license resolving "
    "it. One of the two invocations was refused by an authority gate — EPERM is "
    "may_mount()'s capability check and EACCES is the LSM hook — and an "
    "authority refusal is not evidence the syscall is permitted no matter what "
    "the other invocation answered. THIS CELL EXISTS BECAUSE THE TWO ERRNOS "
    "DIFFERING IS NOT ENOUGH ON ITS OWN: security_sb_pivotroot() runs after "
    "user_path_at() on every kernel, so a host whose LSM refuses answers EACCES "
    "to one call and ENOENT to the other, and mainline hoisted the path lookup "
    "above may_mount() as well, so an unprivileged host there answers EPERM and "
    "ENOENT. Both are pairs that differ while the syscall was refused. "
    "REMEDY: read the errno named above — a capability gate and an LSM denial "
    "need different fixes, and neither is a seccomp profile."
)

_POST_AUTHORITY_ERRNO_UNDER_A_FILTER = (
    "This IS an errno path_pivot_root() produces after both of its authority "
    "gates, so the kernel's own control flow would read it as the call getting "
    "through — but a seccomp filter is installed or its presence could not be "
    "read, and SCMP_ACT_ERRNO's defaultErrnoRet can carry this same errno. So "
    "the reading exists and is being withheld, which is a different statement "
    "from the errno being unrecognised: the check is not missing a cell here, it "
    "is declining to choose between the kernel and the filter. "
    "MEASURED (finding 026, correction arm C): a profile whose only rule is "
    "pivot_root -> SCMP_ACT_ERRNO with errnoRet 22 produces EINVAL at "
    "Seccomp: 2 while holding CAP_SYS_ADMIN, indistinguishable by errno alone "
    "from the same EINVAL a shared-root host produces with no filter at all. "
    "REMEDY: re-read this check with the filter removed — seccomp=unconfined on "
    "Docker, or --security-opt seccomp=unconfined — and the same errno then "
    "resolves. If it does, the filter was not the refusing layer."
)

_UNKNOWN_ERRNO_PROVENANCE = (
    "DERIVED, NOT MEASURED: no arm of T207, finding 024, finding 025 or "
    "finding 026 produced any errno here other than EPERM, EBUSY and EINVAL, "
    "so this branch is reasoned from the profiles' defaultErrnoRet and from "
    "path_pivot_root()'s source and not observed."
)


@dataclass(frozen=True)
class PivotRootAttempt:
    """One forked-child `pivot_root("/", "/")` call, as the child reported it.

    `attempted` is False when the call could not be made at all — a non-Linux
    kernel, an architecture with no recorded syscall number, a failed `fork`,
    or a return value `pivot_root` cannot produce. Same discipline as
    `UnshareAttempt`: `preflight()` has no degraded mode, so every failure it
    prints is read by an operator looking for a way past it, and "I could not
    ask" reported as "the host said no" sends them after a change they do not
    need.
    """

    attempted: bool
    ok: bool
    errno: int | None
    note: str
    #: How this invocation is named in the message. Defaulted so every existing
    #: construction keeps meaning the call it always meant, and carried at all
    #: because the pair prints two of these and an operator has to be able to
    #: tell which invocation produced which errno.
    label: str = 'pivot_root("/", "/")'

    def describe(self) -> str:
        label = self.label
        if not self.attempted:
            return f"{label} NOT ATTEMPTED ({self.note})"
        if self.ok:
            return f"{label} returned 0"
        if self.errno is None:
            return f"{label} FAILED ({self.note})"
        name = errno_module.errorcode.get(self.errno, str(self.errno))
        return f"{label} {name} (errno {self.errno}: {os.strerror(self.errno)})"


def _read_cap_sys_admin(status_path: Path | None = None) -> bool | None:
    """Whether this process holds `CAP_SYS_ADMIN` effectively, read from /proc.

    **Three states, and the third is why this returns `bool | None`.** A
    posture that could not be read is not a "no": reporting it as one would put
    a statement about this process into the message that was never observed,
    and the whole reason this function exists is that finding 024's probe
    inferred a posture instead of reading one.

    `CapEff` rather than `CapPrm` or `CapBnd`, because the kernel's capability
    check reads the effective set. Finding 025's arm A6 is the case that makes
    the distinction load-bearing: `--cap-add=SYS_ADMIN` at uid 1000 leaves
    `CapEff=0` with `CapBnd=a82425fb`, so the container was granted the
    capability and the process does not hold it.
    """
    path = Path("/proc/self/status") if status_path is None else status_path
    try:
        text = path.read_text()
    except OSError:
        return None
    for line in text.splitlines():
        if not line.startswith("CapEff:"):
            continue
        try:
            value = int(line.split(":", 1)[1].strip(), 16)
        except ValueError:
            return None
        return bool(value & (1 << CAP_SYS_ADMIN_BIT))
    return None


def _read_seccomp_mode(status_path: Path | None = None) -> int | None:
    """This process's seccomp mode, read from the same `/proc` line block.

    **`None` and `0` are the two answers that must not be confused, and only
    one of them licenses anything.** `0` says no filter is installed, which is
    what rules out a `defaultErrnoRet` and lets an otherwise-unreadable errno be
    resolved. A `/proc/self/status` that could not be read says nothing at all —
    and it is *absent* on every non-Linux host and hideable inside a container —
    so defaulting it to `0` would turn "I could not tell" into "nothing is
    filtering" and let a real refusal read as `available`. Same three-state
    discipline, and same reason, as `_read_cap_sys_admin`.

    Read from `/proc/self/status` rather than by calling
    `prctl(PR_GET_SECCOMP)`, because that prctl is itself a syscall a filter can
    refuse, and a probe whose answer can be forged by the thing it is measuring
    is not a reading.
    """
    path = Path("/proc/self/status") if status_path is None else status_path
    try:
        text = path.read_text()
    except OSError:
        return None
    for line in text.splitlines():
        if not line.startswith("Seccomp:"):
            continue
        try:
            return int(line.split(":", 1)[1].strip())
        except ValueError:
            return None
    return None


def _decode_pivot_root_exit(code: int) -> PivotRootAttempt:
    """The child's exit code, which is the only thing that crosses back.

    Separated from the fork so every branch is exercisable on a host that can
    make none of these calls, which is the same reason `_classify_unshare_pair`
    is separate from `_attempt_unshare`.
    """
    if code == 0:
        return PivotRootAttempt(True, True, None, "the call returned 0")
    if code == _CODE_CHILD_FAILED:
        return PivotRootAttempt(
            False, False, None,
            "the probe child raised before it could report an errno",
        )
    if code == _CODE_ERRNO_UNENCODABLE:
        return PivotRootAttempt(
            True, False, None,
            f"the call failed with an errno above {_ERRNO_MAX}, which the "
            "child's exit code cannot carry",
        )
    if code == _CODE_RETURN_UNEXPECTED:
        return PivotRootAttempt(
            False, False, None,
            "syscall() returned a value that is neither 0 nor -1, which "
            "pivot_root cannot produce. The syscall number is wrong for this "
            "architecture, so some other syscall answered and its answer is "
            "not evidence about pivot_root",
        )
    return PivotRootAttempt(True, False, code, "the call failed")


def _attempt_pivot_root(
    new_root: bytes = b"/", put_old: bytes = b"/"
) -> PivotRootAttempt:
    """`pivot_root("/", "/")` in a forked child, so this process is never moved.

    **Forked because `pivot_root(2)` mutates the calling process's mount
    namespace.** The arguments chosen cannot succeed, so in practice nothing
    moves — but a preflight that relied on its own probe failing in order to
    stay safe would be one kernel change away from re-rooting the supervisor as
    a side effect of asking a question. The child is discarded and only an exit
    code crosses back.

    **`("/", "/")` is deliberate.** It reaches the kernel's argument checks
    without naming any path that has to exist, so a refusal is attributable to
    the filter rather than to the probe's own setup, and a permitted call
    lands on `EBUSY` rather than on a filesystem error that would need its own
    reading.

    **Arguments are parameters so a *second* invocation can differ from this one
    in nothing but its pointers.** That is the whole of the pair discriminator;
    see `_attempt_pivot_root_pair`. Callers that pass nothing get the call this
    function has always made.
    """
    if platform.system() != "Linux":
        return PivotRootAttempt(
            False, False, None,
            f"platform.system()={platform.system()!r} is not Linux. The "
            "syscall numbers here are Linux's, and issuing one on another "
            "kernel asks a different syscall entirely — 41 is pivot_root on "
            "aarch64 and dup on Darwin — so the call was not made",
        )
    machine = platform.machine()
    nr = _PIVOT_ROOT_NR_BY_MACHINE.get(machine)
    if nr is None:
        return PivotRootAttempt(
            False, False, None,
            f"no pivot_root syscall number is recorded for machine "
            f"{machine!r}; add it to _PIVOT_ROOT_NR_BY_MACHINE rather than "
            "guessing, because a wrong number calls a different syscall and "
            "its answer would be read as this one's",
        )
    libc = ctypes.CDLL(None, use_errno=True)
    try:
        syscall = libc.syscall
    except AttributeError:
        return PivotRootAttempt(
            False, False, None,
            "this libc exports no syscall(2) symbol, so the call was never "
            "made — that is an absence of evidence, not a refusal",
        )
    syscall.restype = ctypes.c_long
    try:
        pid = os.fork()
    except OSError as exc:
        return PivotRootAttempt(
            False, False, None, f"fork() for the probe child failed: {exc}"
        )
    if pid == 0:  # pragma: no cover - the child never returns to the collector
        code = _CODE_CHILD_FAILED
        try:
            ctypes.set_errno(0)
            rc = syscall(ctypes.c_long(nr), new_root, put_old)
            if rc == 0:
                code = 0
            elif rc != -1:
                code = _CODE_RETURN_UNEXPECTED
            else:
                err = ctypes.get_errno()
                code = err if 1 <= err <= _ERRNO_MAX else _CODE_ERRNO_UNENCODABLE
        except BaseException:
            code = _CODE_CHILD_FAILED
        os._exit(code)
    _, status = os.waitpid(pid, 0)
    if not os.WIFEXITED(status):
        signal_number = os.WTERMSIG(status) if os.WIFSIGNALED(status) else None
        return PivotRootAttempt(
            False, False, None,
            f"the probe child did not exit normally (signal {signal_number}); "
            "nothing can be concluded about the syscall from that",
        )
    return _decode_pivot_root_exit(os.WEXITSTATUS(status))


def _attempt_pivot_root_pair() -> PivotRootAttempt:
    """The second invocation, whose *genuine* kernel errno differs from the first.

    **Why a pair exists at all.** A single `pivot_root` call cannot distinguish
    the kernel answering from a seccomp filter answering *as* the kernel:
    `SCMP_ACT_ERRNO` returns an errno of the profile author's choosing, so an
    `EBUSY` from a permitting host and an `EBUSY` forged by a filter are the same
    16. Finding 026's arms B2 and G are that pair of hosts, and they are
    identical in every reading a single call has. This is the same shape as
    T206's `unshare` pair, where `unshare(0)` beside `unshare(CLONE_NEWUSER)` is
    the only thing that separates a seccomp refusal from every other layer.

    **Why a filter cannot tell the two invocations apart.** The kernel's own
    documentation is explicit: "BPF programs may not dereference pointers which
    constrains all filters to solely evaluating the system call arguments
    directly" (`Documentation/userspace-api/seccomp_filter.rst`). Both
    invocations are the same syscall number on the same architecture and differ
    only in two `const char __user *` arguments, so a classic filter's decision
    is necessarily the same for both, and it is taken before syscall entry. If
    the filter refuses, neither call reaches the kernel and both wear the same
    forged constant. If it permits, both reach the kernel and the kernel's own
    control flow separates them.

    **Two documented limits on that, neither of which this closes.** First, a
    filter *can* branch on the pointer's numeric value — `seccomp_data.args`
    carries the raw register — but not on the bytes behind it; the addresses here
    are runtime stack values a profile author cannot predict, so this is
    unreachable rather than impossible. Second, `SECCOMP_RET_USER_NOTIF` and
    `SECCOMP_RET_TRACE` hand the call to a supervisor that *can* read the
    tracee's memory via `ptrace` or `/proc/pid/mem` — the same doc says so — and
    such a supervisor could answer the two differently. Those are not what
    container runtimes ship, and they are why the seccomp mode is still read and
    reported even though it no longer gates resolution.

    **The path must not exist, and that is a safety property rather than a
    convenience.** `("/proc", "/proc")` was measured as the second argument set
    and **returned 0** — it pivoted the child's root. A nonexistent path fails at
    `user_path_at()` before any of the mount machinery runs, so it cannot
    succeed, which is what makes it safe to issue at all. The child is forked
    regardless, and that measurement is why.
    """
    attempt = _attempt_pivot_root(_ABSENT_PROBE_PATH, _ABSENT_PROBE_PATH)
    path = _ABSENT_PROBE_PATH.decode(errors="replace")
    return _dc_replace(attempt, label=f'pivot_root("{path}", "{path}")')


def _classify_pivot_root(
    attempt: PivotRootAttempt,
    sys_admin: bool | None,
    seccomp_mode: int | None = None,
    probe: PivotRootAttempt | None = None,
) -> tuple[bool, str, str]:
    """The cells of the reading, as `(ok, layer, message)`. No syscalls here.

    Kept separate from the probe so the table can be exercised on a host that
    cannot run any of it, which is every developer machine that is not Linux.

    **Two readings, and each resolves a different ambiguity.** `sys_admin`
    separates the kernel's capability gate from a filter when the errno is
    `EPERM`. `seccomp_mode` separates a filter's manufactured errno from the
    kernel's own when the errno is anything else — because `SCMP_ACT_ERRNO` can
    carry *any* errno, and that is the entire reason this check refuses to
    resolve an unfamiliar one. When `Seccomp` reads 0 there is no filter to have
    manufactured anything, so the ambiguity the refusal exists for cannot arise
    and an errno the kernel is known to produce after its authority gates can be
    read as what it is. `seccomp_mode` defaults to `None` — "not read" — so a
    caller that does not supply it gets the pre-existing conservative behaviour
    rather than the permissive one.
    """
    observed = attempt.describe()
    if seccomp_mode == SECCOMP_MODE_DISABLED:
        filtering = (
            "no seccomp filter is installed (Seccomp: 0, read from "
            "/proc/self/status)"
        )
    elif seccomp_mode is not None:
        filtering = (
            f"a seccomp filter is installed (Seccomp: {seccomp_mode}, read "
            "from /proc/self/status)"
        )
    else:
        filtering = (
            "this process's seccomp mode could not be read from "
            "/proc/self/status, which is not the same as no filter being "
            "installed"
        )
    no_filter = seccomp_mode == SECCOMP_MODE_DISABLED
    posture = {
        True: "this process holds CAP_SYS_ADMIN (read from /proc/self/status)",
        False: (
            "this process does not hold CAP_SYS_ADMIN (read from "
            "/proc/self/status)"
        ),
        None: (
            "this process's CAP_SYS_ADMIN could not be read from "
            "/proc/self/status, which is not the same as not holding it"
        ),
    }[sys_admin]

    if not attempt.attempted:
        return (
            False,
            LAYER_NOT_ATTEMPTED,
            f"{observed}. The syscall could not be attempted, so this host is "
            "reported as unverified rather than as refused — there is no "
            "reading here at all, and no remedy follows from one.",
        )
    if attempt.ok:
        return (
            True,
            LAYER_AVAILABLE,
            f"{observed}. {posture}. The syscall returned 0, so it reached the "
            "kernel and the kernel performed it. Attempted in a forked child, "
            "so this process's mount namespace was not moved.",
        )

    # The authority gates are checked across BOTH invocations and BEFORE the
    # pair is allowed to resolve anything, and that ordering is the whole
    # correctness of this function. `security_sb_pivotroot()` runs *after*
    # `user_path_at()` on every kernel, so on a host where an LSM refuses,
    # ("/", "/") answers EACCES while the absent path answers ENOENT — two
    # different errnos, which a bare "they differ, so the call got through"
    # rule would read as permitted on a host that refused it outright. The
    # capability gate has the same shape on new kernels: v6.12 runs may_mount()
    # before the path lookup, so an unprivileged host answers EPERM to both,
    # but mainline hoisted the lookup above it (fs/namespace.c: the syscall
    # resolves both paths, then calls path_pivot_root() which begins with
    # may_mount()), so the same host answers EPERM and ENOENT — distinct again.
    # An authority errno anywhere in the pair therefore has to win first.
    pair = [attempt] + ([probe] if probe is not None else [])
    authority = [a for a in pair if a.attempted and a.errno in _AUTHORITY_ERRNOS]
    if attempt.errno not in _AUTHORITY_ERRNOS and authority:
        other = authority[0]
        return (
            False,
            LAYER_REFUSED_UNATTRIBUTED,
            f"{observed}, but {other.describe()}. {posture}, and {filtering}. "
            f"{_AUTHORITY_ERRNO_IN_THE_PAIR}",
        )

    if (
        probe is not None
        and probe.attempted
        and probe.errno == _ENOENT
        and attempt.errno in _POST_AUTHORITY_ERRNOS
    ):
        return (
            True,
            LAYER_AVAILABLE,
            f"{observed}, and {probe.describe()}. {posture}, and {filtering}. "
            f"{_PAIR_DISCRIMINATED_PERMIT}",
        )
    if attempt.errno in _POST_AUTHORITY_ERRNOS and no_filter:
        return (
            True,
            LAYER_AVAILABLE,
            f"{observed}. {posture}, and {filtering}. pivot_root reached the "
            "kernel, which is the whole question. path_pivot_root() runs its "
            "two authority gates first — may_mount() returning EPERM and "
            "security_sb_pivotroot() returning whatever the LSM says — and "
            "every argument check after them, so this errno is only reachable "
            "once both have passed. With no filter installed there is no "
            "defaultErrnoRet that could have manufactured it either. "
            'pivot_root("/", "/") can never succeed, so a failure is the '
            "permitted reading; which failure depends on the host's mount "
            "topology and not on its authority — the MS_SHARED propagation "
            "check yields EINVAL and precedes the same-root check that yields "
            "EBUSY, so a systemd host whose / is shared answers EINVAL where a "
            "container with private root propagation answers EBUSY. Attempted "
            "in a forked child, so this process's mount namespace was not "
            "moved.",
        )
    if attempt.errno == _EPERM and sys_admin is True:
        # Narrowed by the filter posture rather than by the capability alone.
        # Naming the profile when `Seccomp` reads 0 would tell an operator to
        # ship a profile on a host that has none — the P5 failure the
        # unattributed cell's own text has warned about since T207, which this
        # check could not act on until it read the mode. No measured arm sits in
        # this cell: B1 and P1 both read `Seccomp: 2`.
        if no_filter:
            return (
                False,
                LAYER_REFUSED_UNATTRIBUTED,
                f"{observed}. {posture}, and {filtering}. "
                f"{_EPERM_WITH_CAPABILITY_AND_NO_FILTER}",
            )
        return (
            False,
            LAYER_RUNTIME_SECCOMP,
            f"{observed}. {posture}. {_REMEDY_PIVOT_ROOT_SECCOMP}",
        )
    if attempt.errno == _EPERM:
        return (
            False,
            LAYER_REFUSED_UNATTRIBUTED,
            f"{observed}. {posture}. {_UNATTRIBUTED_PIVOT_ROOT}",
        )
    if attempt.errno == _EACCES:
        return (
            False,
            LAYER_REFUSED_UNATTRIBUTED,
            f"{observed}. {posture}, and {filtering}. "
            f"{_EACCES_IS_AN_AUTHORITY_REFUSAL}",
        )
    if attempt.errno in _POST_AUTHORITY_ERRNOS:
        # Reachable only with a filter installed or its posture unreadable — the
        # `no_filter` arm returned `available` above. Separated from the
        # unrecognised-errno cell below because the two say different things to
        # whoever reads the gate, and arm C is the measurement that showed the
        # unrecognised text going out for an errno the check does have a reading
        # for. Same verdict, different sentence, and the sentence is the product.
        return (
            False,
            LAYER_REFUSED_UNATTRIBUTED,
            f"{observed}. {posture}, and {filtering}. "
            f"{_POST_AUTHORITY_ERRNO_UNDER_A_FILTER}",
        )
    unknown = (
        _UNKNOWN_ERRNO_WITH_NO_FILTER if no_filter
        else _UNKNOWN_ERRNO_UNDER_A_FILTER
    )
    return (
        False,
        LAYER_REFUSED_UNATTRIBUTED,
        f"{observed}. {posture}, and {filtering}. {unknown} "
        f"{_UNKNOWN_ERRNO_PROVENANCE}",
    )


def _READ_FROM_PROC() -> None:  # pragma: no cover - a sentinel, never called
    """Sentinel default for `_check_pivot_root`'s two `/proc` readings.

    `None` cannot be the default for either, because `None` is a real value for
    both — "the capability could not be read", "the seccomp mode could not be
    read" — and a test must be able to inject it. A sentinel keeps those cells
    reachable, and they are the cells that decide whether an unreadable `/proc`
    can turn a refusal into a permit.
    """


def _check_pivot_root(
    attempt=None,
    sys_admin=_READ_FROM_PROC,
    seccomp_mode=_READ_FROM_PROC,
    probe=None,
) -> Check:
    """`pivot_root`, the step FR-048's containment actually rests on.

    Separate from `_check_namespaces` because it is a separate syscall with a
    separate refusal. The two disagree in exactly the configuration an operator
    is most likely to reach — `--cap-add=SYS_ADMIN` under the default profile —
    and collapsing them would make one of the two answers false.

    Both postures come out of `/proc/self/status`, in two reads rather than one,
    so each is separately injectable and separately testable. Neither is
    inferred from the uid or asserted from the invocation: finding 024's probe
    inferred a posture, wrote a uid map naming a uid it did not own, and every
    later `ok` in that sequence was meaningless.
    """
    attempt = _attempt_pivot_root if attempt is None else attempt
    probe = _attempt_pivot_root_pair if probe is None else probe
    if sys_admin is _READ_FROM_PROC:
        sys_admin = _read_cap_sys_admin()
    if seccomp_mode is _READ_FROM_PROC:
        seccomp_mode = _read_seccomp_mode()
    ok, layer, message = _classify_pivot_root(
        attempt(), sys_admin, seccomp_mode, probe()
    )
    return Check("pivot_root", ok, message, "FR-048", layer)


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
        # After `namespaces`, because a host that cannot `unshare` at all will
        # never reach `pivot_root`, and the two read best in the order
        # `enter()` performs them. Not folded into it: see the T207 block.
        checks.append(_check_pivot_root())
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
