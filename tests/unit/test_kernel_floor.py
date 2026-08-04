"""OD-17's missing minimum kernel version, established as a derived lower bound.

OD-17 says Linux and names no release. The floor in `preflight` is derived from
the documented introduction of the facilities the code calls; these tests hold
the derivation to the code, so the floor cannot drift away from what is actually
required, in either direction.

**They do not establish that 5.14 works.** Nothing here has been run on 5.14 —
see `test_the_floor_is_marked_as_derived_and_not_tested`, which asserts the
distinction is stated wherever the floor is reported.
"""

from __future__ import annotations

import pytest

from src.supervisor import preflight


def test_the_floor_is_the_newest_facility_the_code_uses() -> None:
    """5.14 is `cgroup.kill`, and `cgroup.kill` is what `kill_all` requires.

    If the fallback loop were restored the floor could drop to 5.9, so this
    couples the two: the floor is only defensible while the code has no
    degraded path.
    """
    assert preflight.MINIMUM_KERNEL == (5, 14)
    assert "cgroup.kill" in preflight.MINIMUM_KERNEL_BASIS

    from src.supervisor import cgroup

    source = cgroup.SessionCgroup.kill_all.__doc__ or ""
    assert "no fallback" in source.lower(), (
        "kill_all grew a fallback path. If it can degrade to signalling pids "
        "individually then cgroup.kill is no longer required and the 5.14 "
        "floor is overstated — but the fork race is back, which is worse."
    )


def test_the_basis_names_every_facility_that_constrains_it() -> None:
    """A floor with no basis is a number nobody can re-derive or challenge."""
    basis = preflight.MINIMUM_KERNEL_BASIS
    for facility in ("cgroup.kill", "SECCOMP_USER_NOTIF_FLAG_CONTINUE",
                     "SECCOMP_IOCTL_NOTIF_ID_VALID"):
        assert facility in basis, f"the basis does not mention {facility}"
    assert "5.14" in basis and "5.5" in basis and "5.9" in basis


def test_the_floor_is_marked_as_derived_and_not_tested() -> None:
    """Principle I's shape: a derived value states that it is derived.

    "The facility exists in 5.14" is a weaker claim than "this code works on
    5.14", and reporting the floor without that distinction would present the
    first as the second.
    """
    assert preflight.MINIMUM_KERNEL_IS_TESTED is False
    check = preflight._check_kernel_version()
    assert "DERIVED" in check.detail and "NOT TESTED" in check.detail


@pytest.mark.parametrize(
    "release,expected",
    [
        ("6.12.76-linuxkit", (6, 12)),
        ("5.15.0-91-generic", (5, 15)),
        ("5.14", (5, 14)),
        ("6.1.0", (6, 1)),
    ],
)
def test_release_strings_parse(release: str, expected: tuple[int, int]) -> None:
    assert preflight._parse_release(release) == expected


@pytest.mark.parametrize("release", ["", "unknown", "linux", "6", "x.y.z"])
def test_an_unparseable_release_fails_rather_than_defaulting(release: str) -> None:
    """A release string this cannot read must not be assumed new enough."""
    assert preflight._parse_release(release) is None


def test_a_kernel_below_the_floor_fails_the_check(monkeypatch) -> None:
    monkeypatch.setattr("platform.release", lambda: "5.10.0-generic")
    check = preflight._check_kernel_version()
    assert not check.ok
    assert "5.14" in check.detail and "5.10.0-generic" in check.detail


def test_a_kernel_at_the_floor_passes(monkeypatch) -> None:
    monkeypatch.setattr("platform.release", lambda: "5.14.0-generic")
    assert preflight._check_kernel_version().ok


def test_an_unparseable_kernel_fails_the_check(monkeypatch) -> None:
    monkeypatch.setattr("platform.release", lambda: "mystery")
    check = preflight._check_kernel_version()
    assert not check.ok
    assert "could not parse" in check.detail


def test_the_kernel_check_runs_before_the_facility_checks(monkeypatch) -> None:
    """An operator on 5.4 should be told the kernel is old, not that seccomp
    returned EINVAL."""
    monkeypatch.setattr("platform.system", lambda: "Linux")
    names = [c.name for c in preflight.run_checks()]
    assert names.index("kernel_version") < names.index("seccomp_user_notification")


def test_cgroup_kill_is_a_preflight_check() -> None:
    check = preflight._check_cgroup_kill()
    assert check.requirement == "FR-049"
    assert "fork" in check.detail, (
        "the check does not say why cgroup.kill matters, so an operator who "
        "hits it will look for a way to skip it"
    )


def test_kill_all_refuses_rather_than_degrading(tmp_path) -> None:
    """The mechanism, not the preflight: a cgroup mounted without cgroup.kill
    must produce an error and not a kill that silently loses a forking child.
    """
    from src.supervisor.cgroup import CgroupError, SessionCgroup, paths_for

    paths = paths_for("sess-floor", root=tmp_path, parent_name="f2a")
    paths.session.mkdir(parents=True)
    (paths.session / "cgroup.procs").write_text("")

    session = SessionCgroup.__new__(SessionCgroup)
    session.paths = paths

    with pytest.raises(CgroupError, match="killed as a unit|cannot be killed"):
        session.kill_all()
