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
returns a *failure* when it **is** permitted and its preconditions are unmet —
which is always, for `pivot_root("/", "/")`, because the new root may not be the
current root. So that failure is the **success** reading: the call reached the
kernel. Finding 025 measured exactly this as NC-6 — `EPERM` under the default
profile, `EBUSY` under the bundle's profile, one flag changed. A check that
scored it as failure would report a refusal on a host that permits the syscall.

**And a proof that pins one errno of a class proves only that errno.** T207
resolved `EBUSY` alone, because all six container arms produced it. CI run
30970910828 produced `EINVAL` on the `ubuntu-latest` runner — full capability
set, `Seccomp: 0` — and the check reported `refused-unattributed`, which is the
inverted verdict this file's own removal proof exists to catch, arriving through
a sibling errno the proof did not cover. `path_pivot_root()` checks `MS_SHARED`
mount propagation (`-EINVAL`) *before* it checks for the same root (`-EBUSY`),
so a systemd host whose `/` is shared answers `EINVAL` where a container with
private root propagation answers `EBUSY`. Same authority, different topology.

**The third trap, and it is the one the obvious fix walks into.** "Any errno
other than `EPERM` proves the call reached the kernel" is false.
`path_pivot_root()` calls `security_sb_pivotroot()` after `may_mount()` and
before every argument check, and AppArmor's hook denies with **`EACCES`**. So the
resolvable class is a closed list of errnos the kernel is known to produce after
its authority gates, and everything off that list — including `ENOSYS`, which
under no filter means the syscall is unimplemented — fails closed.

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
injecting the attempt, the capability posture **and the seccomp mode**, so the
whole table is exercisable on a macOS laptop that can run none of it. T206's own
first test called the real probe and asserted `not ok`, which was true on macOS
only because libc exports no `unshare` symbol and false under `--privileged` — an
expectation that was a property of the host it happened to run on. The seccomp
mode is injected for the same reason and one more: read from this laptop it is
`None`, which is the conservative branch, so every permissive cell would pass
here without ever being evaluated.
"""

from __future__ import annotations

import pytest
from pathlib import Path

from src.supervisor import preflight

EPERM = 1
EACCES = 13
EBUSY = 16
EINVAL = 22
ENOSYS = 38
ENOENT = 2

# `Seccomp` as `/proc/self/status` reports it: 0 no filter, 1 strict, 2 filter.
# Injected in every cell below, never read from the host, for the reason in this
# module's docstring.
NO_FILTER = 0
FILTER_INSTALLED = 2

# Read off finding 025's measured arms rather than invented. `CapEff` for
# Docker's default capability set (A4) and for that set with CAP_SYS_ADMIN
# added (A5). Bit 21 is CAP_SYS_ADMIN; the two differ in exactly that bit.
CAPEFF_DOCKER_DEFAULT = "a80425fb"
CAPEFF_WITH_SYS_ADMIN = "a82425fb"


def _attempt(*, ok: bool = False, errno: int | None = None,
             attempted: bool = True):
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


#: The absent-path invocation's answer on a host that runs it: `user_path_at()`
#: fails before any mount machinery, so the kernel says ENOENT. Injected, never
#: read, like every other cell here.
PROBE_ENOENT = _attempt(ok=False, errno=ENOENT)

#: No second invocation at all — a fork that failed, or a caller from before the
#: pair existed. The cells behind this are the pre-pair behaviour, kept as a
#: floor rather than deleted, because a probe that could not be issued must not
#: read as a probe that discriminated.
NO_PROBE = None


def _check(attempt, sys_admin, seccomp_mode=FILTER_INSTALLED, probe=NO_PROBE):
    """Every cell, with all three readings injected rather than taken from the host.

    `seccomp_mode` defaults to `FILTER_INSTALLED` rather than to "read it from
    /proc" because that is the posture **every measured arm but B3 and B6 was
    taken under** — finding 026's arms B1, B2, B4, P1 and P2 all read
    `Seccomp: 2` — so the assertions written against those arms keep meaning
    what they meant when the mode became load-bearing. A default of "read the
    host" would make each of them a statement about the laptop instead.

    `probe` defaults to **absent** for the same reason: a test that says nothing
    about the second invocation is asking what a single call can establish, and
    that is a real question with its own cells. Tests about the pair pass it
    explicitly.
    """
    return preflight._check_pivot_root(
        attempt=_returning(attempt), sys_admin=sys_admin,
        seccomp_mode=seccomp_mode,
        probe=_returning(probe) if probe is not None else _returning(
            _attempt(attempted=False)),
    )


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
        preflight, "_attempt_pivot_root",
        lambda *a, **k: _attempt(ok=False, errno=EBUSY))
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
    check = _check(_attempt(ok=False, errno=EBUSY), sys_admin=True,
                   probe=PROBE_ENOENT)
    assert check.name == "pivot_root"
    assert check.ok is True, (
        "EBUSY was scored as a refusal. It is the permitted reading: the "
        "syscall passed the seccomp filter and the kernel rejected the "
        "arguments, which is the answer this check is asking for. Measured as "
        "finding 025 probe arm P2 / NC-6.\n"
        f"detail was: {check.detail}"
    )
    assert check.layer == preflight.LAYER_AVAILABLE


@pytest.mark.parametrize("mode", [NO_FILTER, FILTER_INSTALLED, None])
def test_ebusy_is_permitted_whatever_the_filter_posture_when_the_pair_ran(mode):
    """`EBUSY`'s reading does not depend on the seccomp mode — but on the pair.

    Measured under both postures: B2 and P2 read `Seccomp: 2`, B3 read
    `Seccomp: 0`, and all three produced `EBUSY` and classified `available`.
    Those rows are preserved, and **what preserves them changed**. It used to be
    an unconditional `EBUSY -> available` branch, which arm G falsified by
    forging a 16 with `SCMP_ACT_ERRNO` and reading `available` on a host where
    the filter refused the syscall outright. Now the second invocation is what
    carries them: `EBUSY` beside `ENOENT` is a pair no filter can produce, so
    the posture genuinely does not matter and the forged constant no longer
    passes. See `test_a_forged_constant_errno_is_not_resolved_by_the_pair`.
    """
    check = _check(_attempt(ok=False, errno=EBUSY), sys_admin=True,
                   seccomp_mode=mode, probe=PROBE_ENOENT)
    assert check.ok is True, check.detail
    assert check.layer == preflight.LAYER_AVAILABLE


def test_einval_with_no_filter_installed_reached_the_kernel():
    """The reading that turned CI red on a host where `pivot_root` is permitted.

    CI run 30970910828, the privileged arm: `euid=0`,
    `CapEff=000001ffffffffff`, `Seccomp: 0`, and
    `pivot_root("/", "/")` returned **`EINVAL`**. The capability gate was
    satisfied, no filter was installed, and the check reported
    `refused-unattributed` — a refusal on a host that refuses nothing.

    `EINVAL` is produced only *after* both of `path_pivot_root()`'s authority
    gates, so with no filter installed it is positive evidence the call reached
    the kernel's argument checks. `fs/namespace.c` orders the `MS_SHARED`
    propagation check (`-EINVAL`) **before** the `new_mnt == root_mnt` check
    (`-EBUSY`), which is why a systemd host whose `/` is shared answers `EINVAL`
    where a container with private propagation answers `EBUSY`. Same authority,
    different mount topology.
    """
    check = _check(_attempt(ok=False, errno=EINVAL), sys_admin=True,
                   seccomp_mode=NO_FILTER)
    assert check.ok is True, (
        "EINVAL with no seccomp filter installed was scored as a refusal. "
        "There is no defaultErrnoRet to blame when no filter exists, and "
        "EINVAL comes from path_pivot_root() only after may_mount() and "
        "security_sb_pivotroot() have both passed, so the syscall reached the "
        "kernel. This is CI run 30970910828's privileged arm.\n"
        f"detail was: {check.detail}"
    )
    assert check.layer == preflight.LAYER_AVAILABLE
    assert "EINVAL" in check.detail


@pytest.mark.parametrize("mode", [FILTER_INSTALLED, None])
def test_einval_with_a_filter_installed_or_unreadable_stays_unresolved(mode):
    """The guard the fix must not remove, and the reason it is mode-gated.

    A seccomp profile's `defaultErrnoRet` can carry **any** errno, so under an
    installed filter an `EINVAL` is indistinguishable from a filter refusal
    dressed as one. That ambiguity is real and this check still refuses to
    resolve it. `None` — a mode that could not be read — is not "no filter":
    treating it as one would let an unreadable `/proc` turn a refusal into a
    permit, which is the inversion the whole cell exists to prevent.
    """
    check = _check(_attempt(ok=False, errno=EINVAL), sys_admin=True,
                   seccomp_mode=mode)
    assert check.ok is False, (
        "EINVAL was read as permitted while a filter was installed or while "
        "the filter posture was unknown. SCMP_ACT_ERRNO can return any errno, "
        "so this cell cannot be resolved from the errno alone."
    )
    assert check.layer == preflight.LAYER_REFUSED_UNATTRIBUTED, check.detail


@pytest.mark.parametrize("mode", [FILTER_INSTALLED, None])
def test_einval_under_a_filter_is_not_described_as_an_unrecognised_errno(mode):
    """MEASURED arm C, and it caught a wrong sentence rather than a wrong verdict.

    Arm C of finding 026's 2026-08-05 experiment installed a profile whose only
    rule is `pivot_root -> SCMP_ACT_ERRNO, errnoRet: 22`, manufacturing the exact
    errno the permissive branch resolves. The **verdict** was right —
    `refused-unattributed`, the hole stayed shut. The **message** said "this errno
    is not one this check has a reading for", which is false: the check has a
    reading for `EINVAL` and is declining to *apply* it because a filter is
    installed. Those are different statements and an operator acts on them
    differently — the first says "nobody has thought about this errno", the second
    says "this is the argument-check errno and a filter could have forged it".

    **`EBUSY` is deliberately not parametrised here**, and the asymmetry is real
    rather than an oversight: `EBUSY` resolves to `available` at *every* filter
    posture, because arm **B2** measured exactly that — `Seccomp: 2`, a custom
    profile permitting `pivot_root`, `EBUSY` from the kernel, `available`. Gating
    `EBUSY` on the filter posture would move that measured row and produce the
    inverted verdict this whole correction exists to remove. `EINVAL` has no such
    arm, so the newly admitted cell takes the conservative gate. Finding 026
    records the residual consequence: a systemd host with a permissive filter and
    a shared `/` will read `refused-unattributed` here.

    `ENOSYS` must still get the unrecognised text, which
    `test_an_unexpected_errno_is_reported_rather_than_forced_into_a_cell` holds.
    """
    check = _check(_attempt(ok=False, errno=EINVAL), sys_admin=True,
                   seccomp_mode=mode)

    assert check.ok is False, check.detail
    assert check.layer == preflight.LAYER_REFUSED_UNATTRIBUTED, check.detail
    assert "not one this check has a reading for" not in check.detail, (
        "a post-authority errno was described as unrecognised. path_pivot_root() "
        "is known to produce it; what blocks resolving it is the filter, and the "
        "message has to say which of the two it is."
    )
    assert "defaultErrnoRet" in check.detail, (
        "the message must name the mechanism that makes this unresolvable, "
        "because that is the reading the operator needs in order to act."
    )


@pytest.mark.parametrize("errno", [EBUSY, EINVAL, ENOENT, EPERM, EACCES])
def test_a_forged_constant_errno_is_not_resolved_by_the_pair(errno):
    """Arm G's false permit, closed — and closed for every constant, not one.

    A `SCMP_ACT_ERRNO` rule returns the *same* errno to both invocations,
    because the BPF program cannot dereference either path pointer and the two
    calls are otherwise byte-identical. So a forged constant shows up as a pair
    that does **not** differ, whatever constant was chosen. Arm G forged 16 and
    read `available` under the old unconditional branch; this is that arm and
    its four siblings.

    Parametrised over the authority errnos as well, which reach the verdict by
    the other route — an `EPERM` or `EACCES` anywhere in the pair is an
    authority refusal before distinctness is even consulted.
    """
    forged = _attempt(errno=errno)
    check = _check(forged, sys_admin=True, seccomp_mode=FILTER_INSTALLED,
                   probe=forged)

    assert check.ok is False, (
        f"a filter forging a constant {errno} was read as permitted. Both "
        "invocations returned it, which is exactly what SCMP_ACT_ERRNO does "
        "and exactly what the kernel cannot do, since the two calls name "
        "different paths.\n"
        f"detail was: {check.detail}"
    )
    assert check.layer != preflight.LAYER_AVAILABLE, check.detail


@pytest.mark.parametrize("primary", [EBUSY, EINVAL])
def test_the_pair_resolves_without_needing_the_seccomp_mode(primary):
    """The point of the pair: `Seccomp: 0` stops being load-bearing.

    Arm F is this cell. A shared-`/` host running a filter that **permits**
    `pivot_root` answers `EINVAL` to the first call, and the pre-pair classifier
    read `refused-unattributed` because a filter was installed — a false refusal
    on a working host. With the second invocation answering `ENOENT`, the pair
    discriminates and the filter posture is no longer consulted for the verdict.
    """
    check = _check(_attempt(errno=primary), sys_admin=True,
                   seccomp_mode=FILTER_INSTALLED, probe=PROBE_ENOENT)

    assert check.ok is True, (
        "the pair discriminated and the check still withheld the verdict. "
        "Two different errnos from two calls a filter cannot tell apart is a "
        "stronger reading than the seccomp mode, not a weaker one.\n"
        f"detail was: {check.detail}"
    )
    assert check.layer == preflight.LAYER_AVAILABLE
    assert "may not dereference pointers" in check.detail, (
        "the message must carry the reason the pair is evidence, because an "
        "operator reading a green containment gate is entitled to the argument."
    )


@pytest.mark.parametrize("authority", [EPERM, EACCES])
def test_an_authority_errno_beats_a_differing_pair(authority):
    """The correction to the pair rule, and the cell that makes it sound.

    "The errnos differ, so the call reached the kernel" is **false**, and the
    LSM refusal is the counterexample that matters. `security_sb_pivotroot()`
    runs *after* `user_path_at()` on every kernel, so a host whose AppArmor
    policy denies `pivot_root` answers `EACCES` to `("/", "/")` and `ENOENT` to
    the absent path — two different errnos on a host that refused the syscall
    outright. Mainline has the same shape for the capability gate: it hoisted
    the path lookup above `may_mount()`, so an unprivileged host there answers
    `EPERM` and `ENOENT` where v6.12 answers `EPERM` to both.

    **What actually holds this closed is the closed list, and that is worth
    saying precisely because it is not obvious.** The pair only ever resolves a
    *primary* errno drawn from `_POST_AUTHORITY_ERRNOS`, and neither `EPERM` nor
    `EACCES` is in it, so both cases above are excluded by construction rather
    than by a guard. This half of the test is the assertion that the closed list
    keeps doing that job once a second reading exists to tempt it.
    """
    check = _check(_attempt(errno=authority), sys_admin=True,
                   seccomp_mode=NO_FILTER, probe=PROBE_ENOENT)

    assert check.ok is False, (
        f"a pair of ({authority}, ENOENT) was read as permitted because the "
        "two errnos differ. They differ because path resolution runs before "
        "the authority gate, not because the call got through it. This is a "
        "green containment gate on a host that refuses pivot_root.\n"
        f"detail was: {check.detail}"
    )
    assert check.layer != preflight.LAYER_AVAILABLE, check.detail


@pytest.mark.parametrize("authority", [EPERM, EACCES])
def test_an_authority_errno_on_the_second_call_also_blocks_resolution(authority):
    """The other half, and the one the closed list does **not** cover.

    Here the first invocation answers a post-authority errno and the *second*
    is refused by an authority gate. The closed list is satisfied — `EBUSY` is
    on it — and the two errnos differ, so nothing but an explicit check of both
    invocations stops this resolving. No host has been observed answering two
    different authority verdicts to two calls a filter cannot tell apart, so
    this is a guard against a state rather than a measured arm, and it is
    written down as such. It is cheap, and the alternative is a permit derived
    from a reading that contains a refusal.
    """
    check = _check(_attempt(errno=EBUSY), sys_admin=True,
                   seccomp_mode=NO_FILTER, probe=_attempt(errno=authority))

    assert check.ok is False, (
        "the pair contained an authority refusal and still resolved to "
        f"permitted. One of the two calls was refused by a gate ({authority}); "
        "that is not a reading a permit can be built on.\n"
        f"detail was: {check.detail}"
    )
    assert check.layer != preflight.LAYER_AVAILABLE, check.detail


def test_the_absent_path_probe_is_a_path_that_cannot_exist():
    """A safety property, measured the hard way.

    `("/proc", "/proc")` was tried as the second argument set and **returned
    0** — it pivoted the probe child's root, which is only harmless because the
    child is forked and immediately exits. The second invocation must therefore
    name a path that cannot resolve, so it fails at `user_path_at()` before any
    mount machinery runs and has no success path at all.

    **The assertion is on the marker rather than on `exists()`, and the first
    draft of this test got that wrong.** `Path("/proc").exists()` is `False` on
    macOS, so a tamper swapping the probe path to `/proc` passed here while
    being catastrophic on the only kind of host that runs the probe. That is the
    host-dependent-pass defect this file's own docstring is about, reproduced
    inside a test written to prevent a different one. What is checked instead is
    the property that makes the path safe on *every* host: it is namespaced to
    this project, so no OS ships it and no image can contain it by accident.
    The `exists()` check is kept as a second assertion and is meaningful only
    where it can run.
    """
    path = preflight._ABSENT_PROBE_PATH

    assert path.startswith(b"/"), path
    assert b"f2a-" in path, (
        f"the second invocation's path {path!r} carries no project marker, so "
        "it may name something the host actually has. ('/proc', '/proc') was "
        "measured returning 0 — it pivots the child's root. The path has to be "
        "one nothing ships."
    )
    if Path("/proc").exists():  # a host where the probe could actually run
        assert not Path(path.decode()).exists(), (
            f"{path!r} exists on this host, so the second invocation may "
            "resolve it and reach the mount machinery."
        )


@pytest.mark.parametrize("mode", [NO_FILTER, FILTER_INSTALLED, None])
def test_eacces_is_never_read_as_reaching_the_kernel(mode):
    """The hole in "EPERM is the only authority refusal" — it is not.

    `path_pivot_root()` calls `security_sb_pivotroot()` **after**
    `may_mount()` and **before every argument check**, and AppArmor's hook
    denies with **`-EACCES`**, not `EPERM`
    (`security/apparmor/mount.c`, `build_pivotroot()`: `error = -EACCES` unless
    the profile carries `AA_MAY_PIVOTROOT`). So a rule that read "any errno
    other than EPERM proves the call reached the kernel" would report
    `available` on a host where an LSM refused the syscall outright — the same
    inverted verdict as scoring `EBUSY` a refusal, arriving from the other
    direction.

    This is asserted under **all three** filter postures, because the mode is
    not what makes `EACCES` unsafe: it is unsafe because it is an authority
    refusal, and no filter posture changes that.
    """
    check = _check(_attempt(ok=False, errno=EACCES), sys_admin=True,
                   seccomp_mode=mode)
    assert check.ok is False, (
        "EACCES was read as the call reaching the kernel. It is what "
        "AppArmor's security_sb_pivotroot() hook returns, and that hook runs "
        "before every argument check in path_pivot_root(), so an EACCES is a "
        "refusal by an LSM and not evidence of a permitted syscall."
    )
    assert check.layer == preflight.LAYER_REFUSED_UNATTRIBUTED, check.detail
    assert "EACCES" in check.detail
    assert "LSM" in check.detail or "AppArmor" in check.detail, (
        "the message must name the layer that produces this errno, or the "
        "operator is left with an unexplained refusal on a host whose seccomp "
        "profile is irrelevant to it"
    )


def test_eperm_holding_the_capability_with_no_filter_does_not_name_the_profile():
    """The mirror of the EINVAL fix, and it costs no measured row.

    Finding 026 arm P5/B6 already measured that an `EPERM` can arrive with **no
    filter installed** — `seccomp=unconfined`, `Seccomp: 0`. The message
    recorded that as the reason not to name a profile, but the check never read
    the mode, so it could not act on it. With the capability held and no filter
    present, naming the seccomp profile would tell an operator to ship one on a
    host that has none.

    No arm of finding 026 was taken in this posture — B1 and P1 both read
    `Seccomp: 2` — so narrowing the seccomp attribution changes the
    classification of **no measured arm**.
    """
    check = _check(_attempt(ok=False, errno=EPERM), sys_admin=True,
                   seccomp_mode=NO_FILTER)
    assert check.ok is False
    assert check.layer == preflight.LAYER_REFUSED_UNATTRIBUTED, check.detail
    assert "427" not in check.detail, (
        "the custom-profile remedy was offered on a host with no filter "
        "installed, which is the P5 failure the message already warns about"
    )


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


@pytest.mark.parametrize("mode", [NO_FILTER, FILTER_INSTALLED, None])
@pytest.mark.parametrize("posture", [False, None])
def test_eperm_without_the_capability_is_not_attributed_to_seccomp(
    posture, mode
):
    """Two sources, one errno, and the check must not pick.

    `create_user_ns`'s sibling gate on `pivot_root` is `CAP_SYS_ADMIN` and
    returns `EPERM`; Docker's default profile refuses unlisted syscalls with
    `SCMP_ACT_ERRNO`/`defaultErrnoRet` 1, which is also `EPERM`. A process
    without the capability cannot tell them apart, and `None` — a posture that
    could not be read — is not a "no". Naming seccomp here would send an
    operator to ship a profile that may not be their problem, which is the
    failure `_check_namespaces` spends a whole extra syscall avoiding.
    """
    check = _check(_attempt(ok=False, errno=EPERM), sys_admin=posture,
                   seccomp_mode=mode)
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


@pytest.mark.parametrize("mode", [NO_FILTER, FILTER_INSTALLED, None])
def test_an_unexpected_errno_is_reported_rather_than_forced_into_a_cell(mode):
    """Report what was found; do not resolve it into a remedy.

    A profile whose `defaultErrnoRet` is `ENOSYS` — Podman's is — refuses with
    a different errno, and a kernel that did not implement the syscall would
    too. The check has no way to separate those, so the errno goes in the
    message and the attribution does not.

    **Removing the filter does not resolve this one, and that is deliberate.**
    `EINVAL` reads as permitted under `Seccomp: 0` because `EINVAL` is an errno
    `path_pivot_root()` is *known to produce* after its authority gates.
    `ENOSYS` is not: with no filter installed it is evidence the kernel does not
    implement the syscall at all, which is the opposite of available. So this
    cell is resolved from a closed list of post-authority errnos rather than
    from "anything that is not EPERM", and an errno off that list fails
    closed — a red gate somebody reads beats a green one nobody checks.
    """
    check = _check(_attempt(ok=False, errno=ENOSYS), sys_admin=True,
                   seccomp_mode=mode)
    assert check.ok is False, (
        "ENOSYS was resolved into a permit. With no filter installed it means "
        "the kernel does not implement pivot_root, which is not availability."
    )
    assert check.layer == preflight.LAYER_REFUSED_UNATTRIBUTED, check.detail
    assert "ENOSYS" in check.detail or str(ENOSYS) in check.detail
    assert "DERIVED, NOT MEASURED" in check.detail, (
        "no arm ever produced an errno here other than EPERM, EBUSY and "
        "EINVAL, so this branch must not read as though the path was observed"
    )
    eperm = _check(_attempt(ok=False, errno=EPERM), sys_admin=True,
                   seccomp_mode=mode)
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


def test_the_seccomp_mode_is_read_from_the_same_file_as_the_capability(tmp_path):
    """The filter posture is a reading, not an assumption, for the same reason.

    The bodies below are the shape `/proc/self/status` actually carries — the
    unprivileged CI arm of run 30970910828 read `Seccomp: 0` with
    `Seccomp_filters: 0`, and finding 026's arms B1, B2 and B4 read
    `Seccomp: 2`. Both are constructed here rather than sampled from the host,
    so the whole table runs on a laptop with no `/proc` at all.
    """
    body = "Name:\tpy\nCapEff:\t{}\nSeccomp:\t{}\nSeccomp_filters:\t{}\n"
    no_filter = _status(
        tmp_path / "unconfined", body.format(CAPEFF_WITH_SYS_ADMIN, 0, 0))
    assert preflight._read_seccomp_mode(no_filter) == 0
    filtered = _status(
        tmp_path / "filtered", body.format(CAPEFF_DOCKER_DEFAULT, 2, 1))
    assert preflight._read_seccomp_mode(filtered) == 2
    # Strict mode. No arm produced it and nothing this check does distinguishes
    # it from filter mode; it is here so that "some filter posture other than
    # the two I thought of" cannot silently read as "no filter".
    assert preflight._read_seccomp_mode(
        _status(tmp_path / "strict", body.format("0", 1, 0))) == 1


def test_an_unreadable_seccomp_mode_is_none_rather_than_zero(tmp_path):
    """`None` and `0` are the two readings that must never be confused.

    `0` licenses resolving an unknown errno into a permit; a `/proc` that could
    not be read licenses nothing. Defaulting an unreadable mode to `0` would
    make an absent `/proc/self/status` — which is every non-Linux host, and any
    container that hides it — turn a real refusal into `available`.
    """
    assert preflight._read_seccomp_mode(tmp_path / "absent") is None
    assert preflight._read_seccomp_mode(
        _status(tmp_path / "no-seccomp", "Name:\tpy\nCapEff:\t0\n")) is None
    assert preflight._read_seccomp_mode(
        _status(tmp_path / "malformed", "Seccomp:\tnot-a-number\n")) is None


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
