"""T101 — the two **derived** fields of the measurement record, checked on any
host.

`tests/batteries/test_seccomp_overhead.py` is `linux_only` and `privileged`.
Everything it computes that is not a timing is nonetheless a pure function of
readings, and the two such functions here each replaced a defect that had
shipped:

- **`record_filename`** — which of the two result files a run writes. The
  battery's own `test_the_measurement_is_recorded` asserted the presence of
  `seccomp-overhead.json`, which is *tracked in git*, so it was true on a fresh
  checkout and could not fail for the reason its name gave. Every CI run to date
  passed it against a file the run never touched.
- **`notification_rate`** — the per-notification figure the module's docstring
  calls the transferable one. CI run 31403771772 published
  `microseconds_per_notification: -502.82` for the `compute_only` control, over
  78 notifications, because the supervised median came out *below* its own
  baseline. A negative rate is worse than an absent one: it reads as a figure
  and it invites subtraction.

**Why this file is in `tests/unit/` and not beside the battery**, which is the
argument `tests/unit/test_seccomp_overhead_caveat.py` makes in full: a test of
these placed inside the battery would run on privileged Linux and nowhere else,
which is precisely the condition under which both defects shipped — nothing on
the developer's macOS host could see either. There is no `skipif` in this file
and there must not be one. Loading the battery by path is the mechanism
`test_seccomp_overhead_caveat.py` and
`tests/unit/test_reference_app.py::test_t101s_reference_application_workloads_run_on_any_platform`
both already use to reach that module from a platform-independent test.

**The suppression rule carries no threshold, and that is the part to read
before changing it.** Zero is the boundary because the *definition* of the
quantity forbids crossing it — supervision does strictly more work than its own
baseline, so a non-positive difference cannot be a measurement of its cost. It
is emphatically **not** a noise floor. This battery has no measured noise floor,
and inventing one would be a constant silently deciding which figures get
published, which is the FR-043 shape the battery's own
`test_overhead_is_reported_not_asserted_against_a_threshold` exists to refuse.
The cost of refusing is real and is asserted here rather than left implicit, by
`test_a_small_positive_overhead_is_still_published_because_no_floor_is_known`:
the detector is one-sided, a small positive difference on a noisy host still
publishes a rate, and closing that needs a measurement nobody has taken.
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


# --- which file a run writes ----------------------------------------------


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


# --- the rate, and the reason an arm may not have one ---------------------


def test_a_positive_overhead_yields_the_rate_it_implies(battery) -> None:
    """The ordinary case, with an arithmetic the reader can check by hand:
    0.5s over 1000 notifications is 500 microseconds each."""
    rate, unrated = battery.notification_rate(0.5, 1000)
    assert rate == 500.0
    assert unrated is None


def test_the_negative_rate_ci_published_is_withheld_now(battery) -> None:
    """CI run 31403771772's `compute_only` arm, replayed through the function.

    The published figures were `overhead_seconds -0.03922` over 78
    notifications, giving `microseconds_per_notification: -502.82`. The same
    inputs must now produce no rate at all.
    """
    rate, unrated = battery.notification_rate(-0.03922, 78)
    assert rate is None, (
        f"the observation this disposition exists for still publishes {rate}"
    )
    assert unrated == "non-positive-overhead"


def test_no_input_produces_a_negative_rate(battery) -> None:
    """The property, rather than the one observation of it.

    A guard written against `-0.03922` specifically would pass this file and go
    on publishing every other negative.
    """
    for overhead in (-10.0, -1.0, -0.5, -0.001, -1e-9):
        for notifications in (1, 78, 2000):
            rate, unrated = battery.notification_rate(overhead, notifications)
            assert rate is None, (
                f"{overhead}s over {notifications} notifications published "
                f"{rate}, a rate supervision cannot produce"
            )
            assert unrated == "non-positive-overhead"


def test_a_zero_overhead_publishes_no_rate_either(battery) -> None:
    """Zero is on the withholding side, and the reason is the same one.

    A supervised run that exactly equalled its baseline did not measure a cost
    of zero; it failed to resolve one. `0.0` published as a rate would be the
    `spend_usd: 0.0` defect this disposition is modelled on — a missing quantity
    indistinguishable from a measured zero.
    """
    rate, unrated = battery.notification_rate(0.0, 2000)
    assert rate is None
    assert unrated == "non-positive-overhead"


def test_no_notifications_is_a_different_absence_from_a_negative_overhead(
    battery,
) -> None:
    """Two reasons, not one flag.

    An arm the filter never fired on and an arm whose supervised run came back
    faster are different failures with different repairs, and a record that
    called both `null` would need a reader to guess which.
    """
    _, no_denominator = battery.notification_rate(0.5, 0)
    _, wrong_sign = battery.notification_rate(-0.5, 2000)
    assert no_denominator == "no-notifications"
    assert wrong_sign == "non-positive-overhead"
    assert no_denominator != wrong_sign


def test_every_withholding_reason_is_recorded_in_prose(battery) -> None:
    """`UNRATED` is what puts the reason in the artifact.

    A key the record cannot resolve to prose would be an absence recorded as a
    gap, and `costs.UNPRICED` — the table this one is modelled on — exists
    because a gap reads as an oversight and the next reader fills it in.
    """
    reached = {
        battery.notification_rate(-0.5, 78)[1],
        battery.notification_rate(0.5, 0)[1],
        battery.notification_rate(0.0, 78)[1],
    }
    assert reached <= set(battery.UNRATED), (
        f"{reached - set(battery.UNRATED)} names no recorded reason"
    )
    assert set(battery.UNRATED) == reached, (
        f"{set(battery.UNRATED) - reached} is a recorded reason nothing "
        "reaches, so it describes a branch that no longer exists"
    )
    for key, reason in battery.UNRATED.items():
        assert len(reason) > 80, f"{key}'s reason is too short to be one"


def test_the_non_positive_reason_refuses_to_call_itself_a_noise_threshold(
    battery,
) -> None:
    """The trap this disposition was written against, held open in the record.

    "Within noise" needs a basis and this battery has no measured noise floor.
    The reason text therefore has to say that the boundary is the quantity's
    definition, so that a later reader does not read a *sign* test as a
    *magnitude* test and start tuning it.
    """
    reason = battery.UNRATED["non-positive-overhead"]
    assert "noise threshold" in reason
    assert "no measured noise floor" in reason


def test_a_small_positive_overhead_is_still_published_because_no_floor_is_known(
    battery,
) -> None:
    """**The limitation, asserted rather than only admitted.**

    This is the honest cost of refusing to invent a threshold: the detector is
    one-sided. A difference of 40 microseconds over 78 notifications is as
    dominated by run-to-run variation as the negative one this file suppresses,
    and it is published. Making it *not* published requires a measured noise
    floor for this battery, which nobody has measured.

    The test exists so the gap is a checked property of the design rather than a
    sentence in a docstring: an implementation that quietly grew a magnitude
    bound would fail here, and whoever wrote it would have to come and read the
    reasoning before deleting this.
    """
    rate, unrated = battery.notification_rate(0.00004, 78)
    assert unrated is None
    assert rate == 0.51, (
        "a small positive overhead stopped publishing a rate, which means a "
        "magnitude bound was added; this battery has no measured noise floor "
        "to derive one from — see UNRATED['non-positive-overhead']"
    )


def test_the_rate_is_re_derivable_from_the_two_fields_beside_it(battery) -> None:
    """A reader holding the record can check the rate against its own inputs.

    The function takes the **rounded** overhead the record publishes rather than
    the raw difference, so `overhead_seconds`, `notifications_observed` and
    `microseconds_per_notification` are three statements of one fact and the
    corpus's own `ratio-arithmetic` reasoning applies to them.
    """
    for overhead, notifications in ((0.5, 1000), (1.234567, 78), (0.03922, 2000)):
        rate, _ = battery.notification_rate(overhead, notifications)
        assert rate == round(overhead / notifications * 1e6, 2)
