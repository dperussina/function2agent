"""T207 — the preflight must ask about `pivot_root` as well as about `unshare`.

The defect this file exists to hold closed is a **coverage** gap rather than a
wrong answer. Under `--cap-add=SYS_ADMIN` with Docker's *unmodified* default
seccomp profile, `unshare` succeeds — so `_check_namespaces` reports
`available`, and it is right to. But `pivot_root` appears in **no rule of that
profile at all**, so it still returns `EPERM` with the capability held, and
`run_checks()` had no `pivot_root` check. An operator in that configuration got
a wholly green preflight on a host where the mount sequence builds the entire
mount tree correctly and then fails at the one step that establishes
containment. Measured as arms A5/A6 and probe arms P1/P2 in
`specs/002-spec-aware-agent-runtime/findings/025-preflight-unshare-pair-measured.md`.

**The trap, and it inverts the verdict if you get it wrong.** `pivot_root`
returns `EBUSY` when it *is* permitted and its preconditions are unmet — which
is always, for `pivot_root("/", "/")`, because the new root may not be the
current root. So `EBUSY` is the **success** reading: the call reached the kernel.
Finding 025 measured exactly this as NC-6 — `EPERM` under the default profile,
`EBUSY` under the bundle's profile, one flag changed. A check that scored
`EBUSY` as failure would report a refusal on a host that permits the syscall.

**The second trap: `EPERM` alone does not name seccomp.** The kernel's own gate
on `pivot_root` is `CAP_SYS_ADMIN` and it *also* returns `EPERM`, so the
attribution is only sound in a process that holds the capability. There is no
no-op arm for `pivot_root` the way `unshare(0)` is one for `unshare`, so the
posture has to be read instead — from `/proc/self/status`, not asserted from
the invocation, which is finding 024's overflow-uid lesson.

**These tests read `check.ok` and `check.layer`.** Never a requirement id and a
keyword: the old `cgroup.kill` test asserted the id and the word "fork", never
read the outcome, and passed identically for a probe that could not succeed.

**Nothing here runs a real `pivot_root`.** Every cell is constructed by
injecting the attempt and the capability posture, so the whole table is
exercisable on a macOS laptop that can run none of it. T206's own first test
called the real probe and asserted `not ok`, which was true on macOS only
because libc exports no `unshare` symbol and false under `--privileged` — an
expectation that was a property of the host it happened to run on.
"""

from __future__ import annotations

import pytest

from src.supervisor import preflight

EPERM = 1
EBUSY = 16
ENOSYS = 38

# Read off finding 025's measured arms rather than invented. `CapEff` for
# Docker's default capability set (A4) and for that set with CAP_SYS_ADMIN
# added (A5). Bit 21 is CAP_SYS_ADMIN; the two differ in exactly that bit.
CAPEFF_DOCKER_DEFAULT = "a80425fb"
CAPEFF_WITH_SYS_ADMIN = "a82425fb"


def _attempt(*, ok: bool, errno: int | None = None, attempted: bool = True):
    return preflight.PivotRootAttempt(
        attempted=attempted, ok=ok, errno=errno,
        note="constructed by a test, no syscall was made",
    )


def _returning(attempt):
    """An injectable probe standing in for the forked-child `pivot_root` call.

    Records that it was called, so a test can assert the check actually asked
    rather than trusting that a hard-coded verdict came from a syscall.
    """
    calls: list[int] = []

    def probe():
        calls.append(1)
        return attempt

    probe.calls = calls  # type: ignore[attr-defined]
    return probe


def _check(attempt, sys_admin):
    return preflight._check_pivot_root(
        attempt=_returning(attempt), sys_admin=sys_admin)


# ---------------------------------------------------------------------------
# The defect itself: the check has to exist and has to be its own check.


def test_run_checks_asks_about_pivot_root_after_it_asks_about_unshare(
    monkeypatch,
):
    """The whole of the coverage gap, as one assertion on the check set.

    `run_checks()` ran seven checks and none of them touched `pivot_root`, so
    the step FR-048's containment rests on was invisible to the entire
    preflight. It is ordered after `namespaces` because a host that cannot
    `unshare` at all will never reach `pivot_root`, and an operator should read
    the two in the order the mount sequence performs them.
    """
    monkeypatch.setattr("platform.system", lambda: "Linux")
    monkeypatch.setattr(
        preflight, "_attempt_pivot_root", lambda: _attempt(ok=False, errno=EBUSY))
    names = [c.name for c in preflight.run_checks()]
    assert "pivot_root" in names, (
        "run_checks() has no pivot_root check. Under --cap-add=SYS_ADMIN with "
        "Docker's default profile every check it does run reports green, and "
        "pivot_root is still refused (finding 025, arms A5/A6 and probe P1), "
        f"so the preflight is green on a host where enter() cannot contain. "
        f"checks were: {names}"
    )
    assert names.index("pivot_root") > names.index("namespaces")


def test_the_namespaces_check_stays_green_where_unshare_genuinely_works(
    monkeypatch,
):
    """The constraint that makes this a second check rather than a wider one.

    Folding `pivot_root` into `_check_namespaces` would make that check report
    a refusal in the `--cap-add=SYS_ADMIN` arm, where `unshare` is measured
    *permitted* on both arms (finding 025, A5 and A6). That would be a false
    statement about the syscall the check measures, and it would trade one
    wrong reading for another. The existing check is correct; the check set was
    what had the gap.

    `/proc` is the sibling suite's fixture rather than this host's. Read from
    the real one, this test would pass on macOS for want of `/proc/self/ns/` —
    the kernel-build pre-gate short-circuits before the pair is ever
    classified — which is an expectation that is a property of the laptop and
    not of the check.
    """
    from tests.unit.test_namespace_probe import _ProcSaysYes, _pair

    monkeypatch.setattr(preflight, "Path", _ProcSaysYes)
    check = preflight._check_namespaces(attempt=_pair(noop_ok=True, newuser_ok=True))
    assert check.name == "namespaces"
    assert check.ok is True, (
        "the namespaces check now reports a refusal on a pair that was "
        "permitted on both arms. That is a false statement about unshare(2), "
        "which is the syscall this check measures.\n"
        f"detail was: {check.detail}"
    )
    assert check.layer == preflight.LAYER_AVAILABLE


# ---------------------------------------------------------------------------
# The three-way reading. EBUSY is a pass, and getting that backwards inverts
# the verdict on every permitting host.


def test_ebusy_is_permitted_because_the_call_reached_the_kernel():
    """NC-6's control arm, and the cell a naive implementation gets wrong.

    `pivot_root("/", "/")` cannot succeed — the kernel refuses a new root that
    is the current root — so a permitted call fails, and `EBUSY` is what that
    failure looks like. Finding 025 measured it under the bundle's profile
    while holding CAP_SYS_ADMIN (P2), one flag from the arm that returns
    `EPERM` (P1). Scoring it as a refusal would report the containment step
    broken on precisely the hosts where it works.
    """
    check = _check(_attempt(ok=False, errno=EBUSY), sys_admin=True)
    assert check.name == "pivot_root"
    assert check.ok is True, (
        "EBUSY was scored as a refusal. It is the permitted reading: the "
        "syscall passed the seccomp filter and the kernel rejected the "
        "arguments, which is the answer this check is asking for. Measured as "
        "finding 025 probe arm P2 / NC-6.\n"
        f"detail was: {check.detail}"
    )
    assert check.layer == preflight.LAYER_AVAILABLE


def test_a_successful_pivot_root_is_also_permitted():
    """The cell no host produces, kept because the classifier must not fall
    through it into a refusal.

    `pivot_root("/", "/")` returns `EBUSY` on every kernel that implements the
    root check, so this is DERIVED and was not constructed anywhere. It is here
    because "the call returned 0" reaching a refusing branch would be the same
    inverted verdict as the `EBUSY` cell, one step further along.
    """
    check = _check(_attempt(ok=True), sys_admin=True)
    assert check.ok is True
    assert check.layer == preflight.LAYER_AVAILABLE


def test_eperm_while_holding_cap_sys_admin_names_the_seccomp_profile():
    """The measured refusal, and the only posture in which it is attributable.

    Finding 025 probe arm P1: Docker's unmodified default profile with
    `--cap-add=SYS_ADMIN`, uid 0, not `--privileged`. The kernel's own gate on
    `pivot_root` is `CAP_SYS_ADMIN`, so with the capability held an `EPERM` can
    only have come from a filter.
    """
    check = _check(_attempt(ok=False, errno=EPERM), sys_admin=True)
    assert check.ok is False, (
        "pivot_root was refused and the check reported green. The mount tree "
        "builds and enter() then fails at the containment step."
    )
    assert check.layer == preflight.LAYER_RUNTIME_SECCOMP, check.detail
    assert "seccomp" in check.detail.lower()


def test_the_remedy_warns_off_cap_add_sys_admin_and_says_it_does_not_work():
    """The highest-value line in the message, and it is a negative.

    This is the one arm where the operator is *already holding* the capability
    the `namespaces` remedy warns against, and is being told something is
    wrong. Finding 024 and finding 025 both measured that `pivot_root` appears
    in no rule of the default profile, so the capability cannot help — saying
    only "seccomp refused this" would leave the most likely next change looking
    like the fix.
    """
    detail = _check(_attempt(ok=False, errno=EPERM), sys_admin=True).detail
    assert "--cap-add=SYS_ADMIN" in detail
    assert "does not work" in detail.lower(), (
        "naming --cap-add=SYS_ADMIN without saying it fails leaves the "
        "operator with a suggestion rather than a warning"
    )
    assert "no rule" in detail.lower(), (
        "the remedy must say why the capability cannot help: pivot_root is in "
        "no rule of the default profile, so it falls to defaultAction "
        "regardless of what is held"
    )
    assert "427" in detail and "426" in detail, (
        "'use a custom profile' with no size on it reads as a larger change "
        "than seccomp=unconfined rather than a much smaller one"
    )
    assert "seccomp=unconfined" in detail


def test_the_seccomp_cell_says_which_arms_measured_it():
    """Evidential status in the string, as the rest of this preflight does."""
    detail = _check(_attempt(ok=False, errno=EPERM), sys_admin=True).detail
    assert "MEASURED" in detail


# ---------------------------------------------------------------------------
# The cell the brief did not have: EPERM is only attributable under one
# posture, and there is no no-op arm to substitute for it.


@pytest.mark.parametrize("posture", [False, None])
def test_eperm_without_the_capability_is_not_attributed_to_seccomp(posture):
    """Two sources, one errno, and the check must not pick.

    `create_user_ns`'s sibling gate on `pivot_root` is `CAP_SYS_ADMIN` and
    returns `EPERM`; Docker's default profile refuses unlisted syscalls with
    `SCMP_ACT_ERRNO`/`defaultErrnoRet` 1, which is also `EPERM`. A process
    without the capability cannot tell them apart, and `None` — a posture that
    could not be read — is not a "no". Naming seccomp here would send an
    operator to ship a profile that may not be their problem, which is the
    failure `_check_namespaces` spends a whole extra syscall avoiding.
    """
    check = _check(_attempt(ok=False, errno=EPERM), sys_admin=posture)
    assert check.ok is False
    assert check.layer == preflight.LAYER_REFUSED_UNATTRIBUTED, check.detail
    assert "427" not in check.detail, (
        "the custom-profile remedy is offered on a reading that cannot "
        "attribute the refusal to a profile at all"
    )
    assert "CAP_SYS_ADMIN" in check.detail, (
        "the message must say what posture would make the reading "
        "attributable, because re-running with the capability is free and an "
        "unattributed refusal is not actionable"
    )


def test_the_unattributed_cell_names_the_arms_that_measured_the_ambiguity():
    """The ambiguity is measured, and the limit on it is stated separately.

    T207 arms P3, P4 and P5 produced this same `EPERM` at uid 1000 with
    `--cap-drop=ALL` under Docker's default profile, under the bundle's profile
    which *allows* `pivot_root`, and under `seccomp=unconfined` with no filter
    installed at all. P5 is what makes naming seccomp here indefensible rather
    than merely unproven: there was no filter to name.

    What stays derived is that the list of two candidates is complete, and the
    message has to keep saying so — no LSM refusal was constructible on the
    measuring host, which is the same gap finding 024 and finding 025 both
    carry.
    """
    check = _check(_attempt(ok=False, errno=EPERM), sys_admin=False)
    assert "MEASURED" in check.detail
    assert "P5" in check.detail, (
        "the cell claims the ambiguity is measured without naming the arm "
        "that measured it, which is a claim a reader cannot check"
    )
    assert "DERIVED" in check.detail, (
        "the cell must still say which part of it is not measured: that the "
        "two candidates it names are the only two"
    )


def test_an_unexpected_errno_is_reported_rather_than_forced_into_a_cell():
    """Report what was found; do not resolve it into a remedy.

    A profile whose `defaultErrnoRet` is `ENOSYS` — Podman's is — refuses with
    a different errno, and a kernel that did not implement the syscall would
    too. The check has no way to separate those, so the errno goes in the
    message and the attribution does not.
    """
    check = _check(_attempt(ok=False, errno=ENOSYS), sys_admin=True)
    assert check.ok is False
    assert check.layer == preflight.LAYER_REFUSED_UNATTRIBUTED, check.detail
    assert "ENOSYS" in check.detail or str(ENOSYS) in check.detail
    assert "DERIVED, NOT MEASURED" in check.detail, (
        "no arm ever produced an errno here other than EPERM and EBUSY, so "
        "this branch must not read as though the path was observed"
    )
    eperm = _check(_attempt(ok=False, errno=EPERM), sys_admin=True)
    assert check.detail != eperm.detail, (
        "two different errnos produced an identical message, so the check is "
        "not reporting what it found"
    )


def test_a_probe_that_could_not_run_is_not_a_refusal():
    """"I could not ask" and "the host said no" call for different responses.

    `preflight()` has no degraded mode, so every failure it prints is read by
    an operator looking for a way past it, and reporting an absence of evidence
    as a refusal sends them after a change they do not need. Same discipline as
    the `cgroup.kill` probe reporting its `mkdir` failure rather than reporting
    the facility absent.
    """
    check = _check(_attempt(ok=False, attempted=False), sys_admin=True)
    assert check.ok is False
    assert check.layer == preflight.LAYER_NOT_ATTEMPTED, check.detail
    assert "--cap-add=SYS_ADMIN" not in check.detail


def test_the_check_actually_calls_the_probe():
    """A hard-coded verdict would satisfy every assertion above."""
    probe = _returning(_attempt(ok=False, errno=EBUSY))
    preflight._check_pivot_root(attempt=probe, sys_admin=True)
    assert probe.calls == [1]


# ---------------------------------------------------------------------------
# The child's exit code is the only thing that crosses back, so its decoding
# is where a wrong syscall number becomes a wrong answer.


def test_a_return_value_that_is_neither_zero_nor_minus_one_is_not_evidence():
    """The guard against a syscall number that is wrong for this architecture.

    `pivot_root` returns 0 or -1 and nothing else. `syscall(41, ...)` is
    `pivot_root` on `aarch64` and `dup` on Darwin, and a call that returns a
    file descriptor would otherwise be read as "the syscall succeeded, the
    mechanism is available". A number that cannot be right must produce an
    absence of evidence, not a green check.
    """
    attempt = preflight._decode_pivot_root_exit(
        preflight._CODE_RETURN_UNEXPECTED)
    assert attempt.attempted is False
    assert attempt.ok is False
    check = preflight._check_pivot_root(
        attempt=_returning(attempt), sys_admin=True)
    assert check.ok is False
    assert check.layer == preflight.LAYER_NOT_ATTEMPTED, check.detail


@pytest.mark.parametrize(
    "code, attempted, ok, errno",
    [
        (0, True, True, None),
        (EPERM, True, False, EPERM),
        (EBUSY, True, False, EBUSY),
        (201, False, False, None),   # the child raised before reporting
        (202, True, False, None),    # an errno too large for an exit code
        (203, False, False, None),   # a return value pivot_root cannot make
    ],
)
def test_every_exit_code_the_child_can_speak_decodes_to_one_state(
    code, attempted, ok, errno
):
    """The codes are literals here, never read back out of `preflight`.

    A parametrization built from the module's own constants is true of whatever
    those constants happen to be, which is the watch-set defect this repository
    has already caught once. The three above 200 are asserted to be the ones
    `preflight` uses, so the copy cannot drift silently either.
    """
    assert (preflight._CODE_CHILD_FAILED,
            preflight._CODE_ERRNO_UNENCODABLE,
            preflight._CODE_RETURN_UNEXPECTED) == (201, 202, 203)
    attempt = preflight._decode_pivot_root_exit(code)
    assert (attempt.attempted, attempt.ok, attempt.errno) == (attempted, ok, errno)


# ---------------------------------------------------------------------------
# The posture, read rather than asserted.


def _status(directory, body: str):
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "status"
    path.write_text(body)
    return path


def test_the_capability_posture_is_read_from_proc_and_not_from_the_uid(tmp_path):
    """Finding 024's overflow-uid bug is why this is a read.

    That probe inferred a posture instead of reading one and wrote a uid map
    naming a uid the process did not own; every later `ok` in the sequence was
    meaningless. The two `CapEff` values below are the ones finding 025 read in
    arms A4 and A5 — Docker's default capability set, and that set with
    CAP_SYS_ADMIN added. They differ in bit 21 and in nothing else.
    """
    without = _status(
        tmp_path / "a", f"Name:\tpy\nCapEff:\t{CAPEFF_DOCKER_DEFAULT}\n")
    assert preflight._read_cap_sys_admin(without) is False
    with_it = _status(
        tmp_path / "b", f"Name:\tpy\nCapEff:\t{CAPEFF_WITH_SYS_ADMIN}\n")
    assert preflight._read_cap_sys_admin(with_it) is True


def test_an_unreadable_posture_is_none_rather_than_false(tmp_path):
    """A third state, because "no" and "I could not tell" have different
    consequences: `False` sends the reading into the unattributed cell with a
    statement about this process that was never observed."""
    assert preflight._read_cap_sys_admin(tmp_path / "absent") is None
    assert preflight._read_cap_sys_admin(
        _status(tmp_path / "no-capeff", "Name:\tpy\nUid:\t0\t0\t0\t0\n")) is None
    assert preflight._read_cap_sys_admin(
        _status(tmp_path / "malformed", "CapEff:\tnot-a-number\n")) is None


# ---------------------------------------------------------------------------
# The syscall number, and the platform guard around it.


def test_the_syscall_number_agrees_with_the_binding_the_mechanism_uses():
    """`preflight` carries its own copy, so it must not drift from `_linux`.

    It carries its own copy for the same reason it carries `CLONE_NEWUSER`:
    `_linux` resolves every symbol against the platform libc at import time and
    preflight has to run on the platform it is about to refuse. The literals
    are asserted too, so this cannot pass by both sides drifting together.
    """
    from src.supervisor import _linux

    assert preflight._PIVOT_ROOT_NR_BY_MACHINE["x86_64"] == 155
    assert preflight._PIVOT_ROOT_NR_BY_MACHINE["aarch64"] == 41
    for machine, table in _linux._SYSCALL_NUMBERS.items():
        assert preflight._PIVOT_ROOT_NR_BY_MACHINE[machine] == table["pivot_root"]


def test_the_probe_refuses_to_call_a_linux_syscall_number_on_another_kernel(
    monkeypatch,
):
    """A number from Linux's table means something else on another kernel.

    `platform.machine()` is `arm64` on an Apple Silicon laptop and `aarch64` on
    Linux, and 41 is `pivot_root` on one and `dup` on the other. The platform
    is monkeypatched rather than read, so this asserts the guard on every host
    instead of asserting a property of the host it runs on.
    """
    monkeypatch.setattr("platform.system", lambda: "Darwin")
    attempt = preflight._attempt_pivot_root()
    assert attempt.attempted is False
    assert "Linux" in attempt.note


def test_an_architecture_with_no_recorded_number_does_not_guess(monkeypatch):
    monkeypatch.setattr("platform.system", lambda: "Linux")
    monkeypatch.setattr("platform.machine", lambda: "s390x")
    attempt = preflight._attempt_pivot_root()
    assert attempt.attempted is False
    assert "s390x" in attempt.note


# ---------------------------------------------------------------------------
# The one test that touches the kernel.


@pytest.mark.linux_only
def test_the_probe_does_not_move_the_process_that_ran_it():
    """`pivot_root(2)` mutates the calling process's mount namespace.

    `pivot_root("/", "/")` cannot succeed, so this is belt and braces — but the
    probe forks anyway, and the property worth asserting is the one finding
    025's NC-7 asserted for the `unshare` probe: the process that asked the
    question is not moved by having asked it.
    """
    import os

    before = os.readlink("/proc/self/ns/mnt")
    preflight._attempt_pivot_root()
    assert os.readlink("/proc/self/ns/mnt") == before, (
        "the preflight changed this process's mount namespace while checking "
        "whether it could pivot"
    )
