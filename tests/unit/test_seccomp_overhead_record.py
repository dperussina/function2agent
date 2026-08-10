"""T101 — the two **derived** fields of the measurement record, checked on any
host.

`tests/batteries/test_seccomp_overhead.py` is `linux_only` and `privileged`.
Everything it computes that is not a timing is nonetheless a pure function of
readings, and the two such functions here each replaced a defect that had
shipped:

- **`record_filename`** — which of the two result files a run writes. The
  battery's own `test_the_measurement_is_recorded` — since renamed
  `test_this_runs_measurement_reached_the_file_it_was_asked_for`, so the old
  name resolves nowhere and is quoted here as history — asserted the presence of
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


# --- where an arm stands against its own run's control --------------------
#
# Two runs of the same arm, both from the four samples recorded in the
# battery's own docstring, chosen because they disagree. `shell_heavy` is the
# arm Q-09 names and the only one of the four load-bearing arms that overlaps
# the control at all, so it is the arm on which a vacuous field would be
# invisible — a field that read the same on both of these would be reporting
# nothing while looking like a disclosure.

#: Run 31434583620's own privileged suite — `shell_heavy` +0.015670 s against
#: that run's control of +0.014906 s. The arm clears, by 1.05x, and the
#: control's draws roamed far enough to cover it.
CLEARING_RUN = (0.015670, 0.014906, (-0.030465, 0.056783))

#: The same run's ninth probe battery — `shell_heavy` +0.016378 s against a
#: control of +0.026519 s. The same arm on the same runner in the same job,
#: and it does not clear.
OVERLAPPING_RUN = (0.016378, 0.026519, (-0.030465, 0.056783))

#: The same run's `path_heavy` — +0.073308 s against the same +0.014906 s
#: control, clearing by 4.92x and standing outside the control's roaming.
WELL_CLEAR_RUN = (0.073308, 0.014906, (-0.030465, 0.056783))


def test_an_arm_that_clears_its_own_runs_control_says_so(battery) -> None:
    key, sentence = battery.control_clearance(*CLEARING_RUN, False)
    assert key == "clears-this-runs-control"
    assert "1.05x" in sentence, (
        "the margin is not on the line, so a reader who arrives at this arm "
        f"by grep cannot see how narrowly it cleared: {sentence}"
    )


def test_a_margin_the_controls_own_roaming_covers_is_marked_on_that_line(
    battery,
) -> None:
    """**The half that stops a 1.05x margin reading as a clean clearance.**

    The verdict is like for like — one difference of medians against another —
    and that is the only comparison a single battery can make. It says nothing
    about whether the margin would survive another draw. The control's own
    excursion is the second range limb ③ names, and where the arm's figure sits
    inside it the sentence has to say so, on the same line, or the margin
    travels alone.
    """
    key, sentence = battery.control_clearance(*CLEARING_RUN, False)
    assert key == "clears-this-runs-control"
    assert "OVERLAPPING" in sentence
    assert "+0.056783" in sentence

    clear_key, clear_sentence = battery.control_clearance(*WELL_CLEAR_RUN, False)
    assert clear_key == "clears-this-runs-control"
    assert "OVERLAPPING" not in clear_sentence, (
        "an arm standing outside the control's roaming was marked as "
        "overlapping it, so the qualifier fires regardless and says nothing"
    )
    assert "standing clear of" in clear_sentence


def test_an_arm_the_control_swallows_says_that_on_the_same_line(battery) -> None:
    key, sentence = battery.control_clearance(*OVERLAPPING_RUN, False)
    assert key == "does-not-clear-this-runs-control"
    assert "NOT clearing" in sentence
    assert "+0.026519" in sentence, (
        "the control's own figure is not on the figure's own line, which is "
        "the disclosure-that-does-not-travel shape this field exists to end"
    )


def test_the_two_directions_produce_visibly_different_records(battery) -> None:
    """**The plant, and it is the whole point of the field.**

    One arm, two runs that really happened, and the records must not read the
    same. A field that returned one value either way is the vacuity this
    repository has hardened nine instruments against — and it would be
    *especially* invisible here, because both of these are `shell_heavy` and
    both figures are of the same order.

    Both halves are asserted: the keys differ, and the sentences differ. A key
    that split while the prose stayed generic would leave the artifact
    consumer — the reader this field was built for, who does not open this
    module — with two identical explanations of two different readings.
    """
    clearing = battery.control_clearance(*CLEARING_RUN, False)
    overlapping = battery.control_clearance(*OVERLAPPING_RUN, False)
    assert clearing[0] != overlapping[0], (
        "the same verdict for an arm that cleared its control and an arm that "
        "did not; the field reports nothing"
    )
    assert clearing[1] != overlapping[1]
    assert battery.CLEARANCE[clearing[0]] != battery.CLEARANCE[overlapping[0]]


def test_the_control_is_not_reported_as_having_cleared_itself(battery) -> None:
    """The reading a boolean would have to call `false`, or worse `true`.

    The control compared with itself has an outcome — arithmetic guarantees
    one — and it is not a finding about syscall interception. Recording it as
    a clearance in either direction would put a claim about the supervisor in
    the record where no claim was measured.
    """
    key, sentence = battery.control_clearance(
        0.014906, 0.014906, (-0.030465, 0.056783), True
    )
    assert key == "is-this-runs-control"
    assert "clear" not in key
    assert "IS" in sentence


def test_a_non_positive_overhead_is_not_the_same_reading_as_an_overlap(
    battery,
) -> None:
    """The second reading a boolean would collapse, and the one that matters.

    An arm the control swallows produced a cost this run could not separate
    from zero. An arm whose own difference came out negative produced no cost
    at all. The first is a figure with a caveat and the second is not a figure,
    and `microseconds_per_notification_absent_because` already withholds the
    rate for it — so a record that called both "did not clear" would be
    claiming the instrument resolved something it did not.
    """
    swallowed, _ = battery.control_clearance(*OVERLAPPING_RUN, False)
    absent, _ = battery.control_clearance(
        -0.03922, 0.026519, (-0.030465, 0.056783), False
    )
    assert swallowed == "does-not-clear-this-runs-control"
    assert absent == "no-overhead-to-clear-with"
    assert swallowed != absent


def test_every_clearance_reading_is_recorded_in_prose(battery) -> None:
    """`CLEARANCE` is what puts the reasoning in the artifact, and the set is
    closed in both directions — the same check `UNRATED` carries.

    A key the record cannot resolve to prose is an absence that reads as a
    gap; a row nothing reaches describes a branch that no longer exists.
    """
    reached = {
        battery.control_clearance(*CLEARING_RUN, False)[0],
        battery.control_clearance(*OVERLAPPING_RUN, False)[0],
        battery.control_clearance(*CLEARING_RUN[:3], True)[0],
        battery.control_clearance(
            -0.03922, 0.026519, (-0.030465, 0.056783), False
        )[0],
    }
    assert reached == set(battery.CLEARANCE), (
        f"{reached ^ set(battery.CLEARANCE)} is a reading with no prose or a "
        "row nothing reaches"
    )
    for key, reason in battery.CLEARANCE.items():
        assert len(reason) > 80, f"{key}'s reason is too short to be one"


def test_no_pooled_range_from_another_run_is_installed_as_a_constant(
    battery,
) -> None:
    """**The threshold that is deliberately absent, asserted rather than
    admitted.**

    Limb ③ asks for the pooled control range beside every figure. In prose a
    human writes that range with its provenance attached. In the *record* it
    would be a constant — the pooled range is `6.17.0-1020-azure` x86_64, and
    a linuxkit aarch64 run writing it into its own artifact would publish an
    azure-derived band as though it were its own reading. That is exactly what
    `what_this_is_a_property_of[0]` stopped being a hardcoded sentence to end.

    So the artifact carries the same-run comparator only, and this is what
    would notice a pooled bound being added later.
    """
    source = BATTERY.read_text()
    for pooled in ("-0.012760", "0.029317", "-0.007711", "0.021070"):
        assert pooled not in source.split("REPEATS = 5")[1], (
            f"{pooled} — a control extreme from a named CI run — appears in "
            "this module's executable half, so a figure measured on one host "
            "is about to be published as another host's own comparator"
        )


def test_the_excursion_is_the_widest_difference_the_draws_admit(battery) -> None:
    """A reading over the draws, not a chosen bound.

    The interval has to be the widest the draws can form. A tighter one — a
    standard error, an interquartile range — would be a constant deciding
    which arms clear, which is the fabricated threshold
    `UNRATED['non-positive-overhead']` refuses at length.
    """
    baseline = [0.20, 0.21, 0.19, 0.205, 0.195]
    supervised = [0.204, 0.212, 0.198, 0.207, 0.201]
    low, high = battery.observed_excursion(baseline, supervised)
    assert low == round(min(supervised) - max(baseline), 6)
    assert high == round(max(supervised) - min(baseline), 6)
    assert low < high


def test_the_verdict_compares_like_with_like_and_the_excursion_never_decides(
    battery,
) -> None:
    """**The comparator this field was corrected to, held there by a test.**

    Every arm publishes a difference of two medians, so the control's
    comparable quantity is its own difference of two medians. The excursion is
    a range of the control's raw *pairwise* differences, which is a wider
    statistic, and testing one against the other biases the answer one way.
    Run 31434583620 made that concrete: with the excursion as comparator three
    of the four load-bearing arms came back as not clearing, while the same
    run's k=10 probe puts all four clear on 10 of 10 draws. An artifact that
    contradicts the better-powered reading of its own instrument is worse than
    one that says less.

    So the excursion qualifies the sentence and never decides the key. Moving
    it must not move a verdict.
    """
    overhead, control, _ = CLEARING_RUN
    verdicts = {
        battery.control_clearance(overhead, control, band, False)[0]
        for band in ((-0.001, 0.002), (-10.0, 10.0), (0.0, 0.0))
    }
    assert verdicts == {"clears-this-runs-control"}, (
        f"the excursion moved the verdict ({verdicts}), so the comparison is "
        "no longer like for like"
    )


# --- the qualification, which the verdict cannot be lifted without ---------
#
# Run 31435892323's record shipped `overhead_against_this_runs_control:
# "clears-this-runs-control"` on `shell_heavy` while the sentence one key away
# said the control's own draws roamed far enough to have produced the
# difference. Both statements were true and only one was machine-readable, so a
# consumer filtering on the verdict took the arm and left the qualification.
# The repair is not a second key — a sibling leaves that filter succeeding and
# reading clean — it is that the verdict and its qualification are one object.

#: Every **committed** record that carries the comparator. Two filters, and
#: each is doing separate work.
#:
#: The `.latest.json` suffix rather than `git ls-files`, and the first shape was
#: the second and had to be given up. An ordinary privileged run leaves
#: `seccomp-overhead.latest.json` in this directory — gitignored, so absent from
#: a fresh checkout and from CI, present on the machine of anyone who has run
#: the battery — and a bare glob reads whichever of those the developer happens
#: to have, which is a test whose subject depends on who runs it. Asking git
#: excludes it exactly. It also makes the test require a repository:
#: `proof_attribution.py` copies the tree into a scratch directory with no
#: `.git`, where `git ls-files` fails and the test errors *before* any tamper,
#: so the arm scored `UNUSABLE` and named nothing. The same would happen in any
#: exported checkout. The suffix is the property that actually matters and it
#: is readable from the filename, so it is read from there; the pattern is the
#: one `test_the_durable_record_is_the_tracked_one_and_the_latest_is_not` pins
#: as a live gitignore line, which is what keeps the two halves in step.
#:
#: Presence of the field rather than a filename for the second filter, which is
#: the rule `tools/README.md` records after a `git diff` emptiness test could
#: not tell "unchanged" from "changed back". `seccomp-overhead.json` is the
#: 2026-08-03 linuxkit record and predates the field entirely; it is excluded by
#: not carrying it, not by being named here, so the next record to carry it is
#: picked up without anyone editing this.
def _records_carrying_the_comparator() -> dict:
    import json

    found = {}
    for path in sorted((BATTERY.parent / "results").glob("*.json")):
        if path.name.endswith(".latest.json"):
            continue
        try:
            record = json.loads(path.read_text())
        except (ValueError, UnicodeDecodeError):
            continue
        if isinstance(record, dict) and "control_excursion_seconds" in record:
            found[path.name] = record
    return found


def test_at_least_one_committed_record_carries_the_comparator(battery) -> None:
    """The vacuity floor for the three tests below, which are all per-record.

    Zero records is zero checks, and a clean exit over an empty set says the
    opposite — the defect `check_tampers.py` printed `0 proofs declared, 0
    errors` for until 2026-08-04. Every assertion below iterates, so this is
    the one that has to refuse an empty tree.
    """
    assert _records_carrying_the_comparator(), (
        "no committed record carries `control_excursion_seconds`, so every "
        "assertion over the committed artifacts below is passing over an "
        "empty set"
    )


def test_the_verdict_cannot_be_lifted_out_of_a_committed_record_alone(
    battery,
) -> None:
    """**The defect, replayed as the consumer met it.**

    This is the filter that took `shell_heavy` and never saw the
    qualification. It must now select nothing at all: the field is an object,
    so the comparison against a string is false for every arm. An empty result
    is a visibly broken filter; a qualified arm wearing a clean verdict is not.

    The honest read is asserted in the same breath, because a field that had
    merely become unreadable would also pass the first half.
    """
    for name, record in _records_carrying_the_comparator().items():
        arms = record["arms"]
        naive = sorted(
            arm
            for arm, body in arms.items()
            if body["overhead_against_this_runs_control"]
            == "clears-this-runs-control"
        )
        assert naive == [], (
            f"{name}: lifting the verdict as a bare string still selects "
            f"{naive}, so a consumer can take the clearance and leave the "
            "qualification exactly as before"
        )
        for arm, body in arms.items():
            stands = body["overhead_against_this_runs_control"]
            assert set(stands) == {
                "verdict",
                "qualified_by",
                "qualified_by_means",
            }, f"{name}/{arm} carries {sorted(stands)}"
            assert stands["verdict"] in battery.CLEARANCE
            assert stands["qualified_by"] in battery.EXCURSION_QUALIFICATION


def test_a_committed_record_plants_both_qualifications(battery) -> None:
    """**The both-directions plant, and it is inside a committed artifact.**

    A field that read the same on every arm would be reporting nothing while
    looking like a disclosure, which is the vacuity this repository has
    hardened nine instruments against. Run 31435892323 is one overlapping arm
    and three standing clear, so the two readings are not a fixture's
    invention — they are what the authoritative environment measured.
    """
    seen = set()
    for record in _records_carrying_the_comparator().values():
        for body in record["arms"].values():
            seen.add(body["overhead_against_this_runs_control"]["qualified_by"])
    assert "overlaps-this-runs-control-excursion" in seen, (
        "no committed record carries an arm the control's own draws reach, so "
        "the qualification has never been observed firing"
    )
    assert "stands-clear-of-this-runs-control-excursion" in seen, (
        "no committed record carries an arm standing outside the control's "
        "roaming, so nothing shows the qualification can come out the other way"
    )


def test_the_committed_qualification_is_a_reading_of_the_figures_beside_it(
    battery,
) -> None:
    """The record's verdict, its qualification and its numbers are three
    statements of one fact, re-derivable by a reader holding only the file.

    This is what makes the migration of 2026-08-10 checkable rather than
    asserted: the committed CI record's derived fields were recomputed from the
    readings it already carried, and nothing measured moved.
    """
    for name, record in _records_carrying_the_comparator().items():
        excursion = tuple(record["control_excursion_seconds"])
        control = record["arms"][battery.CONTROL_ARM]["overhead_seconds"]
        for arm, body in record["arms"].items():
            stands = body["overhead_against_this_runs_control"]
            verdict, _ = battery.control_clearance(
                body["overhead_seconds"], control, excursion,
                arm == battery.CONTROL_ARM,
            )
            qualification = battery.excursion_qualification(
                body["overhead_seconds"], excursion, arm == battery.CONTROL_ARM
            )
            assert stands["verdict"] == verdict, f"{name}/{arm}"
            assert stands["qualified_by"] == qualification, f"{name}/{arm}"
            assert (
                stands["qualified_by_means"]
                == battery.EXCURSION_QUALIFICATION[qualification]
            ), f"{name}/{arm} explains a reading it did not take"


def test_the_recorded_field_is_an_object_a_consumer_cannot_take_half_of(
    battery,
) -> None:
    """**The repair itself, at the one place a proof can reach it.**

    `clearance_field` is what the fixture writes into the record, and the whole
    of this pass's change is that it returns an object rather than the verdict
    alone. Asserted here rather than only against a committed artifact, because
    a record is evidence that the emitter behaved once and this is the emitter.

    The bare-string comparison is asserted to fail, in the exact form the
    consumer wrote it. A field that had merely changed type would satisfy that;
    the destructured read is asserted beside it so the test cannot pass on an
    unreadable field.
    """
    stands, sentence = battery.clearance_field(*CLEARING_RUN, False)
    assert stands != "clears-this-runs-control", (
        "the verdict is a bare string again, so a consumer filtering on it "
        "collects the arm and never reaches the qualification"
    )
    assert stands["verdict"] == "clears-this-runs-control"
    assert stands["qualified_by"] == "overlaps-this-runs-control-excursion"
    assert stands["qualified_by_means"] == battery.EXCURSION_QUALIFICATION[
        "overlaps-this-runs-control-excursion"
    ]
    assert "OVERLAPPING" in sentence


def test_the_qualification_and_the_prose_on_the_same_line_never_disagree(
    battery,
) -> None:
    """**The defect stated exactly: a machine field saying one thing and its
    own sentence saying another.**

    The field is a rendering of the same reading the sentence renders, so the
    two are checked against each other in both directions. A qualification that
    agreed with the prose only on the overlapping branch would be the
    fires-regardless vacuity one step along.
    """
    for reading in (CLEARING_RUN, WELL_CLEAR_RUN, OVERLAPPING_RUN):
        overhead, _, band = reading
        qualification = battery.excursion_qualification(overhead, band, False)
        _, sentence = battery.control_clearance(*reading, False)
        overlaps = qualification == "overlaps-this-runs-control-excursion"
        assert overlaps == ("OVERLAPPING" in sentence), (
            f"{qualification!r} against a sentence that reads {sentence!r} — "
            "the machine-readable half and the prose half of one reading "
            "disagree, which is the defect this field was added to end"
        )
        assert overlaps != ("standing clear of" in sentence)


def test_the_excursion_qualifies_and_still_never_decides_the_verdict(
    battery,
) -> None:
    """The pin one field along, and the direction that matters.

    `test_the_verdict_compares_like_with_like_and_the_excursion_never_decides`
    holds the verdict still while the band moves. That test would also pass if
    the qualification were frozen too — a field indifferent to its own input.
    So this asserts the other half: the same three bands that must not move the
    verdict **must** move the qualification.
    """
    overhead, control, _ = CLEARING_RUN
    bands = ((-0.001, 0.002), (-10.0, 10.0), (0.0, 0.0))
    verdicts = {
        battery.control_clearance(overhead, control, band, False)[0]
        for band in bands
    }
    qualifications = {
        battery.excursion_qualification(overhead, band, False) for band in bands
    }
    assert verdicts == {"clears-this-runs-control"}
    assert qualifications == {
        "overlaps-this-runs-control-excursion",
        "stands-clear-of-this-runs-control-excursion",
    }, (
        f"the excursion moved from {bands} and the qualification read "
        f"{qualifications}, so the field does not read the range it names"
    )


def test_the_qualification_cannot_see_the_comparator_that_decides_the_verdict(
    battery,
) -> None:
    """**The separation is in the signature, so it is checked and not promised.**

    `58a6277` shipped the excursion *as* the comparator and `cc34adb` corrected
    it. What stops that returning is that `excursion_qualification` is not given
    the control's overhead at all — a function that cannot see the comparator
    cannot become one, whatever a later edit does to its body.
    """
    import inspect

    parameters = set(
        inspect.signature(battery.excursion_qualification).parameters
    )
    assert "control_overhead_seconds" not in parameters, (
        "the qualification now takes the verdict's comparator, so the "
        "excursion is one edit away from deciding a verdict again"
    )
    assert parameters == {
        "overhead_seconds",
        "control_excursion",
        "is_the_control",
    }, parameters


def test_the_control_and_a_flat_arm_are_not_qualified_as_overlaps(
    battery,
) -> None:
    """The two readings a boolean would have to call `true` here, and both
    would be wrong for different reasons.

    The control's median difference lies inside the range of the differences it
    is a median of by construction, so `overlaps` there is arithmetic. An arm
    with no overhead has nothing for a range to qualify. Neither is a finding
    about syscall interception.
    """
    band = (-0.030465, 0.056783)
    assert (
        battery.excursion_qualification(0.014906, band, True)
        == "is-this-runs-control-excursion"
    )
    assert (
        battery.excursion_qualification(-0.03922, band, False)
        == "no-overhead-to-qualify"
    )
    assert battery.excursion_qualification(
        0.014906, band, True
    ) != battery.excursion_qualification(0.014906, band, False)


def test_every_excursion_reading_is_recorded_in_prose(battery) -> None:
    """`EXCURSION_QUALIFICATION` is what puts the reasoning in the artifact, and
    the set is closed in both directions — the check `UNRATED` and `CLEARANCE`
    each carry.
    """
    band = (-0.030465, 0.056783)
    reached = {
        battery.excursion_qualification(0.015670, band, False),
        battery.excursion_qualification(0.073308, band, False),
        battery.excursion_qualification(0.014906, band, True),
        battery.excursion_qualification(-0.03922, band, False),
    }
    assert reached == set(battery.EXCURSION_QUALIFICATION), (
        f"{reached ^ set(battery.EXCURSION_QUALIFICATION)} is a reading with "
        "no prose or a row nothing reaches"
    )
    for key, reason in battery.EXCURSION_QUALIFICATION.items():
        assert len(reason) > 80, f"{key}'s reason is too short to be one"


def test_the_qualifications_prose_refuses_to_reverse_the_verdict(
    battery,
) -> None:
    """The misreading this field invites, refused in the record itself.

    An overlap is not a finding that the arm failed to clear — the verdict is
    like for like and it stands. A reader who took the qualification as a
    reversal would re-introduce `58a6277`'s defect by hand, so the prose says
    so where the reader is.
    """
    overlaps = battery.EXCURSION_QUALIFICATION[
        "overlaps-this-runs-control-excursion"
    ]
    assert "does NOT reverse the verdict" in overlaps
    assert "property of this draw" in overlaps


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
