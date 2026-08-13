"""T139 and T140 — the drift signal as a sum over two shapes (FR-031, FR-047).

## What has to be asserted here that a field-by-field test would miss

The requirement these two rows share is not *"a record with these fields"*. It
is that **two different things** are both drift signals and that one of them
has no *after* artifact version, because FR-047 says *"no artifact was
obtained"*. A test suite that only checked field presence would pass over the
product type this module exists not to be — one record with
`version_after: str | None` satisfies every field-presence assertion and
reintroduces the repository's worst recorded defect class, a missing quantity
indistinguishable from a measured one.

So the structural arms below assert **absence**:
`test_the_narrowed_shape_has_no_after_version_attribute` and
`test_the_narrowed_document_carries_no_after_version_key`. Their removal proofs
are the product type itself — the tamper adds the optional field back — which
makes "sum, not product" a claim with a counterfactual behind it rather than a
sentence in a docstring.

## Every refusal arm reaches exactly one guard

A refusal test that trips two guards passes with either removed, and its
removal proof then reports `UNPROVEN` or, worse, `proved` for the wrong
mechanism. `ArtifactDrift` validates clock, then deployment identity, then the
version pair, then the moved kinds; `FailedRefetch` validates admissibility,
then vocabulary, then the instant. Each arm below supplies a value that is
valid at every guard except the one it targets.

## The positive controls, and the one that is a falsification test

Every refusal here is a `pytest.raises`, which is Rule 8's shape: a module that
refused everything would pass all of them.
`test_a_signal_is_built_from_a_real_deployment_movement` and
`test_a_failed_refetch_is_built_for_every_state_the_classifier_can_find` are
the floor that stops that.

`test_every_spec_withdrawn_scenario_is_representable` and
`test_the_derived_age_matches_what_the_corpus_declares` are different in kind.
T157's corpus was committed before any of this existed and declares its own
expectations; the second arm recomputes FR-047's age from the instant **this**
record holds and asserts it against a number the corpus wrote down
independently. A shape that could not carry those scenarios would be the wrong
shape, and that check is what set this module's state vocabulary — see the
module docstring of `src/analysis/drift_signal.py`.
"""

from __future__ import annotations

import datetime as dt

import pytest

from src.analysis.admission import (
    ABSENT,
    ADMISSIBLE_STATES,
    PUBLISHED_NON_EMPTY,
    READABLE_NO_OPERATIONS,
    STATES,
    UNREADABLE_BY_CREDENTIAL,
)
from src.analysis.clocks import (
    DEPLOYMENT,
    SOURCE,
    Movement,
    compare,
    compare_each,
    deployment_reading,
    reading,
)
from src.analysis.drift_signal import (
    ARTIFACT_DRIFT,
    FAILED_REFETCH,
    SPECIFICATION_STATE_FOUND,
    ArtifactDrift,
    DriftSignalError,
    FailedRefetch,
    document_of,
    failed_refetch,
    signals_from_movements,
)
from src.contracts.result import SPECIFICATION_STATES, StaleMarking, Staleness
from tests.fixtures.drift_corpora import spec_withdrawn

DEPLOYMENT_ID = "d-reference-app"
ANCHOR = "acme/parts-api@" + "0" * 39 + "a"

CONTRACT_V1 = "sha256:" + "1" * 64
CONTRACT_V2 = "sha256:" + "2" * 64
CHECK_V1 = "sha256:" + "3" * 64

FETCHED_AT = "2026-08-14T00:00:00Z"

OPERATIONS = [
    {"operation_id": "get_part", "method": "GET", "path_template": "/parts/{id}"},
    {"operation_id": "list_parts", "method": "GET", "path_template": "/parts"},
]
OPERATIONS_AFTER_WITHDRAWAL = OPERATIONS[:1]


def source_reading(contract: str = CONTRACT_V1):
    return reading(
        SOURCE,
        deployment_id=DEPLOYMENT_ID,
        versions={"derived_contract": contract, "derived_check": CHECK_V1},
        source_ref=ANCHOR,
    )


def epoch(instant: str) -> float:
    text = instant[:-1] + "+00:00" if instant.endswith("Z") else instant
    return dt.datetime.fromisoformat(text).timestamp()


# ---------------------------------------------------------------------------
# T139 — the both-artifacts-obtained shape, built from T137's comparison.


def test_a_signal_is_built_from_a_real_deployment_movement() -> None:
    """The positive control. Everything below it is a refusal."""
    before = deployment_reading(deployment_id=DEPLOYMENT_ID, operations=OPERATIONS)
    after = deployment_reading(
        deployment_id=DEPLOYMENT_ID, operations=OPERATIONS_AFTER_WITHDRAWAL
    )

    signal = ArtifactDrift.from_movement(compare(before, after))

    assert signal.clock == DEPLOYMENT
    assert signal.deployment_id == DEPLOYMENT_ID
    assert signal.version_before == before.version
    assert signal.version_after == after.version
    assert signal.kinds_moved == ("served_operation_set",)


def test_only_the_clock_that_moved_produces_a_signal() -> None:
    """FR-031's *which of the two clocks moved*, end to end through T137.

    The deployment's served surface changes and the source is untouched. One
    signal, on the deployment clock. A detector reporting both would be OD-06's
    fused artifact reassembled at the signal layer.
    """
    before = {
        SOURCE: source_reading(),
        DEPLOYMENT: deployment_reading(
            deployment_id=DEPLOYMENT_ID, operations=OPERATIONS
        ),
    }
    after = {
        SOURCE: source_reading(),
        DEPLOYMENT: deployment_reading(
            deployment_id=DEPLOYMENT_ID, operations=OPERATIONS_AFTER_WITHDRAWAL
        ),
    }

    signals = signals_from_movements(compare_each(before, after))

    assert len(signals) == 1
    assert signals[0].clock == DEPLOYMENT


def test_a_source_change_produces_a_signal_on_the_source_clock_only() -> None:
    """The other direction, so the arm above is not passing by coincidence."""
    deployment = deployment_reading(
        deployment_id=DEPLOYMENT_ID, operations=OPERATIONS
    )
    before = {SOURCE: source_reading(CONTRACT_V1), DEPLOYMENT: deployment}
    after = {SOURCE: source_reading(CONTRACT_V2), DEPLOYMENT: deployment}

    signals = signals_from_movements(compare_each(before, after))

    assert [s.clock for s in signals] == [SOURCE]
    assert signals[0].kinds_moved == ("derived_contract",)


def test_unchanged_input_produces_no_signal_at_all() -> None:
    """The phase's Independent Test, in as many words.

    *"Plus the negative: re-analysing unchanged input produces no signal at
    all."* A detector that emits one signal per clock per run reports drift on
    a system at rest, and every downstream count of operations disabled would
    then be measured against something that always fires.
    """
    side = {
        SOURCE: source_reading(),
        DEPLOYMENT: deployment_reading(
            deployment_id=DEPLOYMENT_ID, operations=OPERATIONS
        ),
    }

    assert signals_from_movements(compare_each(side, side)) == ()


def test_a_signal_from_an_unmoved_clock_is_refused() -> None:
    """`compare_each` returns unmoved movements; turning one into a signal is
    a false alarm, and the refusal is what makes the filter above a mechanism
    rather than a convention."""
    deployment = deployment_reading(
        deployment_id=DEPLOYMENT_ID, operations=OPERATIONS
    )

    with pytest.raises(DriftSignalError, match="did not move"):
        ArtifactDrift.from_movement(compare(deployment, deployment))


def test_a_signal_on_a_third_clock_is_refused() -> None:
    with pytest.raises(DriftSignalError, match="not a clock"):
        ArtifactDrift(
            clock="wall",
            deployment_id=DEPLOYMENT_ID,
            version_before="sha256:aa",
            version_after="sha256:bb",
            kinds_moved=("derived_contract",),
        )


def test_a_signal_for_no_deployment_is_refused() -> None:
    """FR-031's third term. A responder disabling the affected operation under
    FR-030 has to know whose deployment it belongs to."""
    with pytest.raises(DriftSignalError, match="no deployment"):
        ArtifactDrift(
            clock=SOURCE,
            deployment_id="",
            version_before="sha256:aa",
            version_after="sha256:bb",
            kinds_moved=("derived_contract",),
        )


def test_a_signal_whose_two_versions_are_equal_is_refused() -> None:
    """A signal that reports drift and states none."""
    with pytest.raises(DriftSignalError, match="both the before and the after"):
        ArtifactDrift(
            clock=SOURCE,
            deployment_id=DEPLOYMENT_ID,
            version_before="sha256:aa",
            version_after="sha256:aa",
            kinds_moved=("derived_contract",),
        )


def test_a_signal_naming_no_moved_kind_is_refused() -> None:
    """A composed clock version moves only because some kind on it moved, so a
    signal that can name none was not built from a comparison."""
    with pytest.raises(DriftSignalError, match="no artifact"):
        ArtifactDrift(
            clock=SOURCE,
            deployment_id=DEPLOYMENT_ID,
            version_before="sha256:aa",
            version_after="sha256:bb",
            kinds_moved=(),
        )


# ---------------------------------------------------------------------------
# T140 — the narrowed shape, where no artifact was obtained.


@pytest.mark.parametrize("state", sorted(SPECIFICATION_STATE_FOUND))
def test_a_failed_refetch_is_built_for_every_state_the_classifier_can_find(
    state: str,
) -> None:
    """The positive control for the narrowed shape, over its whole domain."""
    before = deployment_reading(deployment_id=DEPLOYMENT_ID, operations=OPERATIONS)

    signal = failed_refetch(
        before, specification_state=state, last_successful_fetch=FETCHED_AT
    )

    assert signal.clock == DEPLOYMENT
    assert signal.deployment_id == DEPLOYMENT_ID
    assert signal.version_before == before.version
    assert signal.specification_state == state
    assert signal.last_successful_fetch == FETCHED_AT


def test_the_narrowed_shape_has_no_after_version_attribute() -> None:
    """The whole point of the sum type, asserted structurally.

    Not *"`version_after` is `None` here"* — that is the product type, and a
    `None` cannot be told apart from a field nobody filled in. The attribute
    does not exist, so a consumer that reads it fails loudly at the read
    instead of quietly carrying an ambiguous value onward.
    """
    signal = failed_refetch(
        deployment_reading(deployment_id=DEPLOYMENT_ID, operations=OPERATIONS),
        specification_state=ABSENT,
        last_successful_fetch=FETCHED_AT,
    )

    assert not hasattr(signal, "version_after")
    with pytest.raises(AttributeError):
        signal.version_after  # type: ignore[attr-defined]


def test_the_narrowed_document_carries_no_after_version_key() -> None:
    """The same absence at the serialization boundary.

    A `"version_after": null` key would restore the ambiguity the type removed,
    for every consumer reading the record rather than the object.
    """
    signal = failed_refetch(
        deployment_reading(deployment_id=DEPLOYMENT_ID, operations=OPERATIONS),
        specification_state=ABSENT,
        last_successful_fetch=FETCHED_AT,
    )

    assert "version_after" not in signal.document()


def test_the_two_documents_are_distinguishable_by_an_explicit_discriminant() -> None:
    """Which shape a record is must be stated, not inferred from missing keys.

    Inferring it from key presence is the optional-field ambiguity arriving one
    layer later: a truncated or migrated record missing `version_after` would
    read as a failed re-fetch.
    """
    before = deployment_reading(deployment_id=DEPLOYMENT_ID, operations=OPERATIONS)
    after = deployment_reading(
        deployment_id=DEPLOYMENT_ID, operations=OPERATIONS_AFTER_WITHDRAWAL
    )

    drift = document_of(ArtifactDrift.from_movement(compare(before, after)))
    failed = document_of(
        failed_refetch(
            before, specification_state=ABSENT, last_successful_fetch=FETCHED_AT
        )
    )

    assert drift["signal_kind"] == ARTIFACT_DRIFT
    assert failed["signal_kind"] == FAILED_REFETCH
    assert drift["signal_kind"] != failed["signal_kind"]


def test_a_successful_fetch_is_refused_in_the_failed_refetch_shape() -> None:
    """The load-bearing refusal of the whole module.

    `published_non_empty` is a fetch that *worked*. Recording it in the shape
    that means *no artifact was obtained* makes the two arms of the sum
    overlap, which is the same collapse the optional field would have caused —
    arriving through the value domain rather than through the type.
    """
    before = deployment_reading(deployment_id=DEPLOYMENT_ID, operations=OPERATIONS)

    with pytest.raises(DriftSignalError, match="FR-044 admits"):
        failed_refetch(
            before,
            specification_state=PUBLISHED_NON_EMPTY,
            last_successful_fetch=FETCHED_AT,
        )


def test_a_state_no_classifier_produces_is_refused() -> None:
    before = deployment_reading(deployment_id=DEPLOYMENT_ID, operations=OPERATIONS)

    with pytest.raises(DriftSignalError, match="not a specification state"):
        failed_refetch(
            before,
            specification_state="withdrawn",
            last_successful_fetch=FETCHED_AT,
        )


def test_a_failed_refetch_from_a_source_reading_is_refused() -> None:
    """FR-047 reports this as **deployment-clock** drift.

    There is nothing to fail to re-fetch on the source clock: the re-fetch is
    of the target's published specification. A source reading here would put a
    source-derived version in the last-known-good served surface's place.
    """
    with pytest.raises(DriftSignalError, match="deployment-clock"):
        failed_refetch(
            source_reading(),
            specification_state=ABSENT,
            last_successful_fetch=FETCHED_AT,
        )


def test_an_unparseable_last_successful_fetch_is_refused() -> None:
    before = deployment_reading(deployment_id=DEPLOYMENT_ID, operations=OPERATIONS)

    with pytest.raises(DriftSignalError, match="not an ISO-8601 instant"):
        failed_refetch(
            before, specification_state=ABSENT, last_successful_fetch="last tuesday"
        )


def test_a_naive_last_successful_fetch_is_refused() -> None:
    """The more dangerous of the two, because it produces an answer.

    A naive instant parses, yields an age, and that age is compared against
    FR-047's ceiling and believed — wrong by the offset between two machines
    that nobody wrote down.
    """
    before = deployment_reading(deployment_id=DEPLOYMENT_ID, operations=OPERATIONS)

    with pytest.raises(DriftSignalError, match="no timezone"):
        failed_refetch(
            before,
            specification_state=ABSENT,
            last_successful_fetch="2026-08-14T00:00:00",
        )


def test_the_before_terms_come_off_one_reading_and_cannot_disagree() -> None:
    """FR-031's surviving terms are consistent by construction.

    `failed_refetch` takes a `Reading`, not three strings, so a signal cannot
    name one deployment's identity beside another deployment's version.
    """
    before = deployment_reading(deployment_id=DEPLOYMENT_ID, operations=OPERATIONS)
    other = deployment_reading(deployment_id="d-other", operations=OPERATIONS)

    signal = failed_refetch(
        before, specification_state=ABSENT, last_successful_fetch=FETCHED_AT
    )

    assert signal.deployment_id == before.deployment_id
    assert signal.version_before == before.version
    assert other.deployment_id != signal.deployment_id


# ---------------------------------------------------------------------------
# The age is derived, not stored — so it cannot disagree with FR-047's marking.


def test_the_age_is_derived_from_the_instant_this_record_holds() -> None:
    signal = failed_refetch(
        deployment_reading(deployment_id=DEPLOYMENT_ID, operations=OPERATIONS),
        specification_state=ABSENT,
        last_successful_fetch="2026-08-14T00:00:00Z",
    )

    assert signal.age_seconds(epoch("2026-08-14T00:06:00Z")) == 360.0


def test_a_fetch_stamped_in_the_future_is_not_clamped_to_zero() -> None:
    """Reporting a negative age as zero would present the set as freshly
    fetched on precisely the evidence that its timestamp cannot be trusted."""
    signal = failed_refetch(
        deployment_reading(deployment_id=DEPLOYMENT_ID, operations=OPERATIONS),
        specification_state=ABSENT,
        last_successful_fetch="2026-08-14T00:10:00Z",
    )

    assert signal.age_seconds(epoch("2026-08-14T00:00:00Z")) == -600.0


# ---------------------------------------------------------------------------
# One vocabulary, shared with FR-047's caller-visible marking (T148's subject).


def test_the_state_vocabulary_agrees_with_the_caller_visible_marking() -> None:
    """The duplicated pair that must not be allowed to disagree.

    `src/contracts/result.py` duplicates the classifier's states rather than
    importing them, because `src/contracts/` is the bottom of the import graph
    — and says of that duplication that *"a test asserts the two agree, which
    is a check, where an import would be an assumption"*. This is that check
    extended to the third site: the drift signal must not admit a state the
    caller-visible marking would reject, nor the reverse.
    """
    assert SPECIFICATION_STATES == frozenset(STATES)
    assert SPECIFICATION_STATE_FOUND == frozenset(STATES) - ADMISSIBLE_STATES
    assert SPECIFICATION_STATE_FOUND < SPECIFICATION_STATES


@pytest.mark.parametrize("state", sorted(SPECIFICATION_STATE_FOUND))
def test_every_state_this_shape_admits_the_staleness_marking_also_admits(
    state: str,
) -> None:
    """The agreement exercised rather than asserted set-wise.

    FR-047 names the specification state in both places. A drift signal that
    could be raised for a state no `Staleness` can carry would leave the
    caller-visible marking unable to state what the drift channel found.
    """
    Staleness(
        marking=StaleMarking.STALE, age_seconds=60.0, specification_state=state
    )


# ---------------------------------------------------------------------------
# The falsification test: T157's corpus, which predates all of this.


def test_every_spec_withdrawn_scenario_is_representable() -> None:
    """A shape that cannot carry the committed scenarios is the wrong shape.

    This is what settled the state vocabulary. `withdraw-past-ceiling` declares
    two fetches in state `unreachable`, which is **not** one of FR-044's four —
    `admission.py` declares it as one of two additions beyond the requirement's
    list. A domain restricted to FR-047's literal three non-admissible states
    could not represent a scenario this repository has already committed.
    """
    scenarios = spec_withdrawn.load_scenarios()
    assert scenarios, "the corpus loaded no scenarios; this arm would be vacuous"

    before = deployment_reading(deployment_id=DEPLOYMENT_ID, operations=OPERATIONS)
    built = 0
    for scenario in scenarios:
        last_ok: str | None = None
        for instant, state in zip(scenario.fetch_instants, scenario.fetch_states):
            if state == PUBLISHED_NON_EMPTY:
                last_ok = instant
                continue
            assert last_ok is not None, (
                f"{scenario.scenario_id} fails a re-fetch before any has "
                "succeeded, which FR-047 cannot describe: its ceiling is "
                "measured from the last successful fetch"
            )
            signal = failed_refetch(
                before,
                specification_state=state,
                last_successful_fetch=last_ok,
            )
            assert not hasattr(signal, "version_after")
            built += 1

    assert built >= 9, f"only {built} failed re-fetches exercised; expected the corpus's nine"
    assert spec_withdrawn.non_admissible_states_exercised() <= SPECIFICATION_STATE_FOUND


def test_the_derived_age_matches_what_the_corpus_declares() -> None:
    """The strongest arm here: two independent computations of one number.

    The corpus wrote `age_seconds` down for every call before this module
    existed. `FailedRefetch.age_seconds` recomputes it from the instant the
    record holds. If the record carried a stored age instead of the instant,
    this is the arm that would have nothing to check.
    """
    before = deployment_reading(deployment_id=DEPLOYMENT_ID, operations=OPERATIONS)
    checked = 0

    for scenario in spec_withdrawn.load_scenarios():
        fetches = list(zip(scenario.fetch_instants, scenario.fetch_states))
        for call in scenario.calls:
            if not call.stale:
                continue
            at_or_before = [f for f in fetches if epoch(f[0]) <= epoch(call.at)]
            last_ok = [i for i, state in at_or_before if state == PUBLISHED_NON_EMPTY]
            state_found = at_or_before[-1][1]

            signal = failed_refetch(
                before,
                specification_state=state_found,
                last_successful_fetch=last_ok[-1],
            )

            assert signal.age_seconds(epoch(call.at)) == float(call.age_seconds), (
                f"{scenario.scenario_id} at {call.at}: the age derived from "
                "the instant this record holds disagrees with the age the "
                "corpus declares"
            )
            assert signal.specification_state == call.specification_state_last_found
            checked += 1

    assert checked >= 7, (
        f"only {checked} stale calls checked; the corpus declares more and this "
        "arm would be passing on a subset"
    )


def test_the_corpus_exercises_more_than_one_non_admissible_state() -> None:
    """A vacuity floor for the two arms above.

    A corpus in which every failure were `absent` would let a shape supporting
    exactly one state pass both of them.
    """
    exercised = spec_withdrawn.non_admissible_states_exercised()

    assert {ABSENT, UNREADABLE_BY_CREDENTIAL, READABLE_NO_OPERATIONS} <= exercised


def test_the_corpus_reaches_a_state_outside_fr_044s_four() -> None:
    """The fact that decided this module's state vocabulary, asserted directly.

    `spec_withdrawn.non_admissible_states_exercised()` deliberately reports only
    FR-044's **three**, so it cannot carry this: `unreachable` is one of the two
    states `admission.py` declares beyond the requirement's list. It appears in
    `withdraw-past-ceiling`, so a `FailedRefetch` restricted to FR-047's literal
    three could not describe a committed scenario — which is why
    `SPECIFICATION_STATE_FOUND` is the classifier's states minus the admissible
    one rather than FR-047's three.

    If this arm ever fails because the corpus stopped exercising `unreachable`,
    the widening above loses the evidence that justified it and should be
    revisited rather than kept.
    """
    reached = {
        state
        for scenario in spec_withdrawn.load_scenarios()
        for state in scenario.fetch_states
    }

    assert "unreachable" in reached
    assert "unreachable" not in spec_withdrawn.non_admissible_states_exercised()
    assert "unreachable" in SPECIFICATION_STATE_FOUND


# ---------------------------------------------------------------------------
# The sum, dispatched once.


def test_the_dispatch_handles_both_arms() -> None:
    before = deployment_reading(deployment_id=DEPLOYMENT_ID, operations=OPERATIONS)
    after = deployment_reading(
        deployment_id=DEPLOYMENT_ID, operations=OPERATIONS_AFTER_WITHDRAWAL
    )

    for signal in (
        ArtifactDrift.from_movement(compare(before, after)),
        failed_refetch(
            before, specification_state=ABSENT, last_successful_fetch=FETCHED_AT
        ),
    ):
        document = document_of(signal)
        assert document["clock"] == DEPLOYMENT
        assert document["deployment_id"] == DEPLOYMENT_ID
        assert document["version_before"] == before.version
        assert document["signal_kind"] in (ARTIFACT_DRIFT, FAILED_REFETCH)


def test_both_shapes_state_all_of_fr_031s_surviving_terms() -> None:
    """FR-031's terms that the narrowing leaves unchanged: *"Every other term
    of this requirement is unchanged."*"""
    before = deployment_reading(deployment_id=DEPLOYMENT_ID, operations=OPERATIONS)
    after = deployment_reading(
        deployment_id=DEPLOYMENT_ID, operations=OPERATIONS_AFTER_WITHDRAWAL
    )

    for signal in (
        ArtifactDrift.from_movement(compare(before, after)),
        failed_refetch(
            before, specification_state=ABSENT, last_successful_fetch=FETCHED_AT
        ),
    ):
        assert signal.clock in (SOURCE, DEPLOYMENT)
        assert signal.deployment_id
        assert signal.version_before


def test_a_hand_built_movement_still_goes_through_the_guards() -> None:
    """`Movement` is a public frozen dataclass and is constructible directly,
    so `from_movement` cannot rely on `compare` having vetted its input."""
    with pytest.raises(DriftSignalError, match="did not move"):
        ArtifactDrift.from_movement(
            Movement(
                clock=SOURCE,
                deployment_id=DEPLOYMENT_ID,
                moved=False,
                version_before="sha256:aa",
                version_after="sha256:bb",
                kinds_moved=("derived_contract",),
            )
        )
