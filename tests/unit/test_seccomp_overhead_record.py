"""T101 — which result file a run writes, checked on any host.

`tests/batteries/test_seccomp_overhead.py` is `linux_only` and `privileged`.
Everything it computes that is not a timing is nonetheless a pure function of
readings, and `record_filename` is one such: it chooses between the two result
files from the environment, and the choice is what a test named *the measurement
is recorded* has to be about.

That test was `assert (RESULTS / "seccomp-overhead.json").is_file()` until
2026-08-10. The file is **tracked in git**, so the assertion was true on a fresh
checkout and could not fail for the reason its name gave; what an ordinary run
produces is `seccomp-overhead.latest.json`, and the durable file is written only
under `F2A_RECORD_MEASUREMENTS=1`. Every CI run to date passed it against a file
the run never touched. `tools/README.md` counts at least eight instruments of
that family; `ci.yml` already reasons correctly one level up — *"the file is
missing exactly when the measurement did not happen."*

**Why this file is in `tests/unit/` and not beside the battery**, which is the
argument `tests/unit/test_seccomp_overhead_caveat.py` makes in full: a test of
this placed inside the battery would run on privileged Linux and nowhere else,
which is precisely the condition under which the defect shipped — nothing on the
developer's macOS host could see it. There is no `skipif` in this file and there
must not be one. Loading the battery by path is the mechanism
`test_seccomp_overhead_caveat.py` and
`tests/unit/test_reference_app.py::test_t101s_reference_application_workloads_run_on_any_platform`
both already use to reach that module from a platform-independent test.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

BATTERY = (
    Path(__file__).resolve().parents[1] / "batteries" / "test_seccomp_overhead.py"
)


@pytest.fixture(scope="module")
def battery():
    spec = importlib.util.spec_from_file_location("_t101_battery_record", BATTERY)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_two_record_names_are_different_files(battery) -> None:
    """The distinction the repaired assertion rests on.

    If these ever became one name, an existence check would be satisfied by the
    tracked file again and the vacuity would be back with every test still
    green.
    """
    assert battery.DURABLE_RECORD != battery.LATEST_RECORD


def test_the_durable_record_is_the_tracked_one_and_the_latest_is_not(
    battery,
) -> None:
    """The property that made the original assertion vacuous, asserted as a
    fact about the checkout rather than argued in prose.

    `seccomp-overhead.json` is committed — it is Q-09's recorded figure — so its
    presence says nothing about any run. `seccomp-overhead.latest.json` is
    gitignored, so its presence is a statement about the run that produced it.
    A commit that started tracking the second would silently restore the defect,
    and this is what would notice.
    """
    results = BATTERY.parent / "results"
    assert (results / battery.DURABLE_RECORD).is_file(), (
        "the recorded Q-09 figure is missing from the checkout, so the "
        "reasoning this file rests on no longer describes the repository"
    )
    # Matched as a whole line rather than as a substring, because a substring
    # test here would be satisfied by the pattern appearing inside a comment or
    # inside a longer path — the exact hole `numeric-provenance` was hardened
    # out of on 2026-08-03, where `0.8961` was satisfied by `0.89612`.
    repo = Path(__file__).resolve().parents[2]
    ignored = {
        line.strip()
        for line in (repo / ".gitignore").read_text().splitlines()
        if not line.lstrip().startswith("#")
    }
    pattern = f"{results.relative_to(repo).as_posix()}/*.latest.json"
    assert pattern in ignored, (
        f"`{pattern}` is no longer a gitignore line, so the file a run "
        "produces may now be present on a fresh checkout and asserting its "
        "existence is vacuous again"
    )


def test_an_unset_request_selects_the_file_an_ordinary_run_produces(
    battery,
) -> None:
    assert battery.record_filename({}) == battery.LATEST_RECORD


def test_the_request_selects_the_durable_record(battery) -> None:
    assert (
        battery.record_filename({battery.RECORD_REQUEST: "1"})
        == battery.DURABLE_RECORD
    )


def test_the_two_settings_select_different_files(battery) -> None:
    """The load-bearing one, and the shape a constant cannot pass.

    An implementation that stopped reading the environment — returning either
    name unconditionally — satisfies one of the two tests above and fails here
    whichever name it picked.
    """
    assert battery.record_filename({}) != battery.record_filename(
        {battery.RECORD_REQUEST: "1"}
    )


@pytest.mark.parametrize("value", ["", "0", "true", "yes", "2", "1 "])
def test_only_the_exact_value_one_requests_recording(battery, value) -> None:
    """The committed record is overwritten on this branch, so the gate is
    deliberately exact rather than truthy.

    `F2A_RECORD_MEASUREMENTS=0` reading as a request would destroy Q-09's
    recorded figure on a run that spelled the refusal out.
    """
    assert (
        battery.record_filename({battery.RECORD_REQUEST: value})
        == battery.LATEST_RECORD
    ), f"{value!r} was read as a request to overwrite the recorded figure"
