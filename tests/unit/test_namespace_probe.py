"""T206 — the preflight's `namespaces` check must attempt the syscall.

The defect this file exists to hold closed: `_check_namespaces` established
that user namespaces were available by reading `/proc/self/ns/` and the
`max_user_namespaces` sysctl. Both report **kernel-build presence and an
administrative setting**. Neither is a syscall attempt, so on a host whose
container runtime refuses `unshare` in its seccomp profile both answered yes
and the check reported green — for a mechanism that does not work there.
Measured in
`specs/002-spec-aware-agent-runtime/findings/024-deployment-surface-permission-census.md`.

**These tests read `check.ok`.** The repository has caught the other kind
twice: the old `cgroup.kill` test asserted a requirement id and the word
"fork" and never read the outcome, so it passed identically for a probe that
could not succeed; and a watch-set test asserted a length it computed from the
watch set itself, so it was true of every watch set. Every expectation below is
a literal, never a value read back out of `preflight`.

**Nothing here runs a real `unshare`.** The four cells of the truth table are
constructed by injecting the attempt function, which is why they run on a
developer's macOS host as well as on Linux. The one test that does touch the
kernel is marked `linux_only` and asserts only that the probe does not move the
process that ran it.
"""

from __future__ import annotations

import pytest

from src.supervisor import preflight

EPERM = 1
ENOSPC = 28


# ---------------------------------------------------------------------------
# Constructing the four cells without a kernel.


def _attempt(flags: int, *, ok: bool, errno: int | None = None,
             attempted: bool = True) -> preflight.UnshareAttempt:
    return preflight.UnshareAttempt(
        flags=flags, attempted=attempted, ok=ok, errno=errno,
        note="constructed by a test, no syscall was made",
    )


def _pair(*, noop_ok: bool, newuser_ok: bool,
          noop_errno: int | None = EPERM, newuser_errno: int | None = EPERM):
    """An injectable attempt function standing in for the forked-child probe.

    Records what it was asked for, so a test can assert the *flags* the check
    passed rather than trusting that it asked the right question.
    """
    asked: list[int] = []

    def attempt(flags: int) -> preflight.UnshareAttempt:
        asked.append(flags)
        if flags == 0:
            return _attempt(flags, ok=noop_ok,
                            errno=None if noop_ok else noop_errno)
        return _attempt(flags, ok=newuser_ok,
                        errno=None if newuser_ok else newuser_errno)

    attempt.asked = asked  # type: ignore[attr-defined]
    return attempt


class _ProcSaysYes:
    """A `/proc` in which presence and the sysctl both answer yes.

    This is the *whole* evidence base the check had before T206, and the point
    of the fixture is that it is not enough. `max_user_namespaces` is 31337,
    which is the value finding 024 read at the top level of a Docker Desktop
    container — a host on which `unshare(CLONE_NEWUSER)` returns `EPERM`
    anyway.
    """

    def __init__(self, path: str = "/proc") -> None:
        self._path = str(path)

    def __truediv__(self, other: str) -> "_ProcSaysYes":
        # `type(self)` rather than the class name, so a subclass overriding
        # `exists` still overrides it after a join. Written as the literal class
        # first, where it silently answered yes for every joined path and made
        # `test_a_kernel_built_without_the_namespaces_still_fails_early` pass a
        # fixture that had no missing namespace in it.
        return type(self)(f"{self._path}/{other}")

    def exists(self) -> bool:
        return True

    def is_file(self) -> bool:
        return True

    def read_text(self) -> str:
        return "31337\n"

    def __str__(self) -> str:
        return self._path


@pytest.fixture()
def proc_says_yes(monkeypatch):
    monkeypatch.setattr(preflight, "Path", _ProcSaysYes)


# ---------------------------------------------------------------------------
# The defect itself.


def test_presence_and_the_sysctl_are_not_evidence_the_mechanism_works(
    proc_says_yes,
):
    """The whole of T206, as one assertion on the outcome field.

    The fixture reproduces exactly what a host running Docker's default seccomp
    profile reads: all four `/proc/self/ns/` entries present, and
    `max_user_namespaces` a large number. Those are the only two reads the
    pre-T206 check made, and both answer yes on a host where
    `unshare(CLONE_NEWUSER)` returns `EPERM`. So the syscall is refused here and
    the outcome must follow the syscall, not the reads.

    **The refusal is injected rather than real**, so this asserts the same thing
    on a macOS laptop, on an unprivileged Linux host and under `--privileged`.
    An earlier version called the real probe and asserted `not ok`, which was
    true on macOS for want of an `unshare` symbol and false under
    `--privileged`, where the call succeeds — a test whose expectation was a
    property of the host it happened to run on.
    """
    check = preflight._check_namespaces(
        attempt=_pair(noop_ok=False, newuser_ok=False))
    assert check.name == "namespaces"
    assert check.ok is False, (
        "the namespaces check reported ok with /proc/self/ns/ present and "
        "max_user_namespaces=31337, while unshare(2) was refused on both arms. "
        "Both of those reads answer yes under Docker's default seccomp "
        "profile, where unshare(CLONE_NEWUSER) returns EPERM (finding 024). A "
        "preflight that green-lights the sandbox on that evidence is the "
        "defect T206 exists to fix.\n"
        f"detail was: {check.detail}"
    )


def test_the_check_asks_for_the_no_op_and_for_clone_newuser_and_nothing_else(
    proc_says_yes,
):
    """Both arms, and the flag values are literals rather than re-read.

    The no-op arm is the entire diagnostic value of the pair, so a check that
    quietly dropped it would still pass a test that only asserted
    `CLONE_NEWUSER` was tried.
    """
    attempt = _pair(noop_ok=True, newuser_ok=True)
    preflight._check_namespaces(attempt=attempt)
    assert sorted(attempt.asked) == [0, 0x10000000], (
        "the check must attempt unshare(0) — the no-op — beside "
        "unshare(CLONE_NEWUSER). It asked for: "
        f"{[hex(f) for f in attempt.asked]}"
    )


def test_the_flag_agrees_with_the_binding_the_mechanism_uses():
    """`preflight` carries its own copy, so it must not drift from `_linux`.

    It carries its own copy on purpose: `_linux` resolves every symbol against
    the platform libc, and preflight has to run on the platform it is about to
    refuse. The literal is asserted too, so this cannot pass by both sides
    drifting together.
    """
    from src.supervisor import _linux

    assert preflight.CLONE_NEWUSER == 0x10000000
    assert preflight.CLONE_NEWUSER == _linux.CLONE_NEWUSER


# ---------------------------------------------------------------------------
# The four cells.


def test_both_arms_succeeding_is_the_only_green(proc_says_yes):
    check = preflight._check_namespaces(
        attempt=_pair(noop_ok=True, newuser_ok=True))
    assert check.ok is True, check.detail


def test_both_arms_refused_is_attributed_to_the_runtime_seccomp_profile(
    proc_says_yes,
):
    """The measured cell. Docker's default profile, uid 1000, --cap-drop=ALL.

    The rule is on the `unshare` *syscall* and not on `CLONE_NEWUSER`, so the
    no-op — which creates no namespace, and which no kernel namespace check
    can refuse — returns EPERM too. That is what licenses naming the layer
    here rather than listing candidates.
    """
    check = preflight._check_namespaces(
        attempt=_pair(noop_ok=False, newuser_ok=False))
    assert check.ok is False
    assert check.layer == preflight.LAYER_RUNTIME_SECCOMP, check.detail
    detail = check.detail
    assert "seccomp" in detail.lower()
    assert "427" in detail, (
        "the remedy must name the custom profile concretely — Docker's own "
        "default plus one syscall name, 426 allow-listed names to 427 — "
        "because 'use a custom profile' with no size on it reads as a larger "
        "change than seccomp=unconfined rather than a much smaller one"
    )
    assert "426" in detail


def test_the_remedy_warns_off_cap_add_sys_admin_and_says_it_does_not_work(
    proc_says_yes,
):
    """The highest-value line in the message, and it is a negative.

    The profile's rule for `unshare` is written as a capability gate, so
    `--cap-add=SYS_ADMIN` is the change the error invites, it is by a wide
    margin the most dangerous one available, and it does not work: `pivot_root`
    is in no rule of the profile at all, so the whole mount tree builds and
    then fails at the containment step. An operator reads that as a broken
    mechanism unless the preflight said so first.
    """
    check = preflight._check_namespaces(
        attempt=_pair(noop_ok=False, newuser_ok=False))
    assert check.ok is False
    detail = check.detail
    assert "--cap-add=SYS_ADMIN" in detail
    assert "pivot_root" in detail
    assert "does not work" in detail.lower(), (
        "naming --cap-add=SYS_ADMIN without saying it fails leaves the "
        "operator with a suggestion rather than a warning"
    )


def test_the_no_op_passing_is_never_attributed_to_seccomp(proc_says_yes):
    """The discriminator doing its job, in the direction that matters.

    A syscall-level seccomp rule refuses the no-op too. So a permitted no-op
    beside a refused CLONE_NEWUSER rules the runtime profile *out*, and the
    bundle's profile — the one remedy we can supply — must not be offered
    here, because it would not help.
    """
    check = preflight._check_namespaces(
        attempt=_pair(noop_ok=True, newuser_ok=False, newuser_errno=EPERM))
    assert check.ok is False
    assert check.layer == preflight.LAYER_KERNEL_OR_LSM, check.detail
    assert "427" not in check.detail, (
        "the custom-profile remedy is offered on a reading that rules the "
        "runtime profile out. That sends the operator to ship a profile that "
        "cannot fix their host."
    )


def test_the_kernel_or_lsm_branch_says_it_is_derived_and_not_measured(
    proc_says_yes,
):
    """Finding 024 could not construct an LSM refusal at all.

    Docker Desktop's linuxkit VM carries neither AppArmor nor SELinux, and the
    LSM is what refuses on Ubuntu 24.04 — the single most likely host for a
    self-hosted install. So this branch is derived from a source read of
    `create_user_ns()`, and it must not read as though the path was observed.
    Same discipline the 5.14 kernel floor carries.
    """
    check = preflight._check_namespaces(
        attempt=_pair(noop_ok=True, newuser_ok=False))
    assert "DERIVED" in check.detail and "NOT MEASURED" in check.detail


def test_the_branch_reports_the_errno_it_saw_rather_than_naming_one_layer(
    proc_says_yes,
):
    """Report what was found; do not assert which layer produced it.

    ENOSPC is the ucount/nesting limit and EPERM is a chroot, an unmapped uid
    or an LSM hook — different remedies, and the check has no way to tell them
    apart. Finding 024's NC-3 measured the ENOSPC arm; the rest is a source
    read. So the errno goes in the message and the attribution does not.
    """
    nospc = preflight._check_namespaces(
        attempt=_pair(noop_ok=True, newuser_ok=False, newuser_errno=ENOSPC))
    assert nospc.ok is False
    assert "ENOSPC" in nospc.detail or str(ENOSPC) in nospc.detail

    eperm = preflight._check_namespaces(
        attempt=_pair(noop_ok=True, newuser_ok=False, newuser_errno=EPERM))
    assert eperm.detail != nospc.detail, (
        "two different errnos produced an identical message, so the check is "
        "not reporting what it found"
    )


def test_a_refused_no_op_beside_a_permitted_clone_newuser_is_incoherent(
    proc_says_yes,
):
    """The fourth cell. No layer produces it, so no layer is named.

    `unshare(0)` asks for nothing; a host that refuses it and grants a real
    namespace is telling us the probe is wrong, not the host. Guessing a
    remedy from an incoherent reading is how a preflight sends an operator
    after a fix for a problem they do not have.
    """
    check = preflight._check_namespaces(
        attempt=_pair(noop_ok=False, newuser_ok=True))
    assert check.ok is False
    assert check.layer == preflight.LAYER_INCOHERENT, check.detail
    assert "--cap-add=SYS_ADMIN" not in check.detail


def test_an_unattemptable_probe_is_not_a_refusal(proc_says_yes):
    """"I could not ask" and "the host said no" call for different responses.

    Same reasoning as the cgroup.kill probe, which reports the mkdir failure
    rather than reporting the facility absent: `preflight()` has no degraded
    mode, so every failure it prints is read by an operator looking for a way
    past it, and a wrong layer sends them after the wrong change.
    """
    def cannot(flags: int) -> preflight.UnshareAttempt:
        return _attempt(flags, ok=False, errno=None, attempted=False)

    check = preflight._check_namespaces(attempt=cannot)
    assert check.ok is False
    assert check.layer == preflight.LAYER_NOT_ATTEMPTED, check.detail
    assert "--cap-add=SYS_ADMIN" not in check.detail


# ---------------------------------------------------------------------------
# The reads that were there before still gate — they just no longer decide.


def test_a_kernel_built_without_the_namespaces_still_fails_early(monkeypatch):
    """Presence is now a precondition rather than the evidence.

    A kernel with no `/proc/self/ns/user` cannot have its `unshare` refused by
    a profile, and telling that operator to ship a seccomp profile would be
    wrong. So the presence read keeps its own message and the syscall is not
    attempted at all.
    """
    class _NoNamespaces(_ProcSaysYes):
        def exists(self) -> bool:
            return not self._path.endswith("/user")

    monkeypatch.setattr(preflight, "Path", _NoNamespaces)
    attempt = _pair(noop_ok=True, newuser_ok=True)
    check = preflight._check_namespaces(attempt=attempt)
    assert check.ok is False
    assert "user" in check.detail
    assert attempt.asked == [], (
        "the syscall was attempted on a kernel that has no user namespaces "
        "to unshare, which can only produce a misleading layer attribution"
    )


def test_the_sysctl_set_to_zero_still_fails(monkeypatch):
    """`max_user_namespaces=0` is an administrative refusal with its own fix.

    It is also the one layer the old check *could* see, so losing it would
    make T206 a trade rather than an improvement.
    """
    class _Disabled(_ProcSaysYes):
        def read_text(self) -> str:
            return "0\n"

    monkeypatch.setattr(preflight, "Path", _Disabled)
    check = preflight._check_namespaces(
        attempt=_pair(noop_ok=True, newuser_ok=True))
    assert check.ok is False
    assert "max_user_namespaces" in check.detail


# ---------------------------------------------------------------------------
# The one test that touches the kernel.


@pytest.mark.linux_only
def test_the_probe_does_not_move_the_process_that_ran_it():
    """`unshare(2)` mutates the caller, so the probe must fork.

    A preflight that put the supervisor into a user namespace as a side effect
    of asking whether it could would have changed the thing it was measuring —
    and every later check would run in a namespace nobody asked for. The
    process's own `user` and `mnt` namespace identities must be the same after
    the probe as before it, whatever the probe reported.
    """
    import os

    before = (os.readlink("/proc/self/ns/user"), os.readlink("/proc/self/ns/mnt"))
    for flags in (0, preflight.CLONE_NEWUSER):
        preflight._attempt_unshare(flags)
    after = (os.readlink("/proc/self/ns/user"), os.readlink("/proc/self/ns/mnt"))
    assert before == after, (
        "the preflight moved this process into a namespace while checking "
        "whether it could create one"
    )
