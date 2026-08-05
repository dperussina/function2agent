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
from dataclasses import dataclass
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

# The two errnos this classifier has a reading for. Written as literals rather
# than read from the `errno` module because they must be *Linux's* numbers
# whatever host is doing the reading; both happen to agree with macOS today,
# which is exactly the kind of coincidence that stops being true silently.
_EPERM = 1
_EBUSY = 16

# `CAP_SYS_ADMIN` is capability bit 21. It is the kernel's own gate on
# `pivot_root`, which is why the posture has to be read before an `EPERM` can
# be attributed to anything.
CAP_SYS_ADMIN_BIT = 21

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
# root that is already the root — so the *permitted* reading here is a failure
# with `EBUSY`, meaning the call passed the filter and the kernel rejected the
# arguments. Finding 025 measured the pair as NC-6: `EPERM` under the default
# profile, `EBUSY` under the bundle's profile, one flag changed.
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

    def describe(self) -> str:
        label = 'pivot_root("/", "/")'
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


def _attempt_pivot_root() -> PivotRootAttempt:
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
            rc = syscall(ctypes.c_long(nr), b"/", b"/")
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


def _classify_pivot_root(
    attempt: PivotRootAttempt, sys_admin: bool | None
) -> tuple[bool, str, str]:
    """The cells of the reading, as `(ok, layer, message)`. No syscalls here.

    Kept separate from the probe so the table can be exercised on a host that
    cannot run any of it, which is every developer machine that is not Linux.
    """
    observed = attempt.describe()
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
    if attempt.ok or attempt.errno == _EBUSY:
        return (
            True,
            LAYER_AVAILABLE,
            f"{observed}. {posture}. pivot_root reached the kernel, which is "
            "the whole question: EBUSY is the kernel rejecting these "
            'arguments — pivot_root("/", "/") can never succeed, because the '
            "new root may not be the current root — and a syscall refused by "
            "a seccomp filter never gets that far. Attempted in a forked "
            "child, so this process's mount namespace was not moved.",
        )
    if attempt.errno == _EPERM and sys_admin is True:
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
    return (
        False,
        LAYER_REFUSED_UNATTRIBUTED,
        f"{observed}. {posture}. This errno is not one of the two this check "
        "has a reading for. EPERM is the kernel's capability gate or a "
        "seccomp SCMP_ACT_ERRNO refusal; EBUSY is the call reaching the "
        "kernel. Anything else is reported as found rather than resolved into "
        "a layer: a profile whose defaultErrnoRet is ENOSYS — Podman's is — "
        "and a kernel that does not implement the syscall produce the same "
        "errno by different mechanisms, and this check cannot separate them. "
        "DERIVED, NOT MEASURED: no arm of T207, finding 024 or finding 025 "
        "produced any errno here other than EPERM and EBUSY, so this branch "
        "is reasoned from the profiles' defaultErrnoRet and not observed.",
    )


def _READ_FROM_PROC() -> None:  # pragma: no cover - a sentinel, never called
    """Sentinel default for `_check_pivot_root(sys_admin=...)`.

    `None` cannot be the default, because `None` is a real posture value —
    "could not be read" — and a test must be able to inject it. A sentinel
    keeps that cell reachable.
    """


def _check_pivot_root(attempt=None, sys_admin=_READ_FROM_PROC) -> Check:
    """`pivot_root`, the step FR-048's containment actually rests on.

    Separate from `_check_namespaces` because it is a separate syscall with a
    separate refusal. The two disagree in exactly the configuration an operator
    is most likely to reach — `--cap-add=SYS_ADMIN` under the default profile —
    and collapsing them would make one of the two answers false.
    """
    attempt = _attempt_pivot_root if attempt is None else attempt
    if sys_admin is _READ_FROM_PROC:
        sys_admin = _read_cap_sys_admin()
    ok, layer, message = _classify_pivot_root(attempt(), sys_admin)
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
