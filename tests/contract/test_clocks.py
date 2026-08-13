"""T137 — the two clocks, independently versioned (FR-027, **OD-06**).

## What is actually being asserted, and what would be a tautology

FR-027 asks for two things: the two artifacts **independently versioned**, and
drift **detected in each of them separately**.

Half of that is easy to assert vacuously. Two readings built from disjoint
inputs are byte-stable under each other's changes *by arithmetic*, and a test
observing it would pass over a module with no guard in it at all. So the
independence arms here are the **end-to-end** form — a pair in which only one
clock's input moved, run through `compare_each`, with the other clock's movement
asserted unmoved and its two versions asserted equal — and the mechanism that
makes independence a property of the code rather than of the caller is
`reading()`'s refusal of a foreign kind, which has its own arm and its own
removal proof.

## Every refusal arm reaches exactly one guard

A refusal test that trips two guards passes with either one removed, and its
removal proof then reports `UNPROVEN` — or worse, `proved` for the wrong
mechanism. Each arm below is built so that precisely one branch of `reading()`,
`compare()` or `assert_partition_total()` can fire on its input:

- the foreign-kind arm supplies **every** kind on the clock *and* the foreign
  one, so the missing-kind branch cannot fire;
- the subset arm supplies no foreign kind;
- the blank-version arm supplies a complete kind set and an anchor;
- the cross-clock comparison uses one deployment identity, so the
  cross-deployment branch cannot fire, and the cross-deployment comparison uses
  one clock.

## The positive controls, and why they are not decoration

Every refusal here is a `pytest.raises`, which is Rule 8's shape: a module that
refused everything would pass all of them. `test_a_reading_is_built_on_each_clock`
and `test_two_identical_readings_move_neither_clock` are the floor that stops
that, and the second is also the negative the phase's Independent Test names
outright — *re-analysing unchanged input produces no signal at all*.
"""

from __future__ import annotations

from dataclasses import fields, replace

import pytest

from src.analysis import clocks
from src.analysis.clocks import (
    CLOCKS,
    DEPLOYMENT,
    KINDS_ON_CLOCK,
    SOURCE,
    ClockError,
    ClockPartitionError,
    Movement,
    Reading,
    assert_partition_total,
    compare,
    compare_each,
    deployment_reading,
    reading,
)
from src.analysis.served_operations import set_version_of
from src.contracts import schemas
from src.contracts.schemas import SCHEMAS, ArtifactSchema

DEPLOYMENT_ID = "d-reference-app"
ANCHOR = "acme/parts-api@" + "0" * 39 + "a"

CONTRACT_V1 = "sha256:" + "1" * 64
CONTRACT_V2 = "sha256:" + "2" * 64
CHECK_V1 = "sha256:" + "3" * 64

OPERATIONS = [
    {"operation_id": "get_part", "method": "GET", "path_template": "/parts/{id}"},
    {"operation_id": "list_parts", "method": "GET", "path_template": "/parts"},
]
OPERATIONS_AFTER_WITHDRAWAL = OPERATIONS[:1]


def _source(contract: str = CONTRACT_V1, check: str = CHECK_V1) -> Reading:
    return reading(
        SOURCE,
        deployment_id=DEPLOYMENT_ID,
        versions={"derived_contract": contract, "derived_check": check},
        source_ref=ANCHOR,
    )


def _deployment(operations=OPERATIONS) -> Reading:
    return deployment_reading(deployment_id=DEPLOYMENT_ID, operations=operations)


# ---------------------------------------------------------------------------
# The partition. Two clocks, and every kind drift reads on exactly one of them.


def test_the_two_clocks_are_the_two_data_model_names() -> None:
    """`data-model.md` §2.6 and both synthetic corpora spell them this way."""
    assert CLOCKS == ("source", "deployment")
    assert set(KINDS_ON_CLOCK) == set(CLOCKS)


def test_the_partition_is_total_over_the_registry_and_overlaps_nowhere() -> None:
    assert_partition_total(SCHEMAS)

    assigned = [kind for clock in CLOCKS for kind in KINDS_ON_CLOCK[clock]]
    assert len(assigned) == len(set(assigned)), "a kind sits on both clocks"
    assert set(assigned) == {s.kind for s in SCHEMAS if s.source_derived}


def test_the_deployment_derived_artifact_is_on_the_deployment_clock() -> None:
    """The reading `schemas.source_derived` cannot express, stated here.

    `served_operation_set` is flagged `source_derived=True` in the registry and
    is the **deployment**-derived artifact: `served_operations.py` produces it
    above source analysis from a specification the target publishes. The flag
    is the union of the two clocks; this is the partition.
    """
    assert "served_operation_set" in KINDS_ON_CLOCK[DEPLOYMENT]
    assert "served_operation_set" not in KINDS_ON_CLOCK[SOURCE]
    assert KINDS_ON_CLOCK[SOURCE] == {"derived_contract", "derived_check"}


def test_the_partition_check_reads_a_registry_that_is_not_empty() -> None:
    """The floor under the totality arm.

    `assert_partition_total` over a registry with no drift-relevant kind agrees
    with any partition at all, including an empty one.
    """
    drift_relevant = {s.kind for s in SCHEMAS if s.source_derived}
    assert len(drift_relevant) == 3, drift_relevant


def _schema(kind: str, *, source_derived: bool) -> ArtifactSchema:
    return ArtifactSchema(
        kind=kind,
        version="1.0.0",
        requirement="FR-027",
        required=("schema_version",),
        volatile=(),
        source_derived=source_derived,
        description="a synthetic registry entry for this test",
    )


def test_a_kind_drift_reads_and_no_clock_reads_is_refused() -> None:
    """A drift-relevant kind on neither clock is detected in neither."""
    widened = SCHEMAS + (_schema("newly_derived_thing", source_derived=True),)

    with pytest.raises(ClockPartitionError, match="sits on neither clock"):
        assert_partition_total(widened)


def test_a_clock_kind_the_registry_does_not_read_for_drift_is_refused() -> None:
    """The other direction: a clock reading over a kind no channel publishes."""
    narrowed = tuple(
        _schema(s.kind, source_derived=False)
        if s.kind == "served_operation_set" else s
        for s in SCHEMAS
    )

    with pytest.raises(ClockPartitionError, match="is on a clock and is not"):
        assert_partition_total(narrowed)


def test_a_kind_on_both_clocks_is_refused(monkeypatch) -> None:
    """OD-06's fused artifact, with the seam drawn in a different place.

    One version moved by either cause gives *which clock moved* two answers,
    which is the same as having none.
    """
    monkeypatch.setattr(clocks, "KINDS_ON_CLOCK", {
        SOURCE: frozenset({"derived_contract", "derived_check",
                           "served_operation_set"}),
        DEPLOYMENT: frozenset({"served_operation_set"}),
    })

    with pytest.raises(ClockPartitionError, match="is on both the"):
        assert_partition_total(SCHEMAS)


# ---------------------------------------------------------------------------
# The positive controls. Without these every refusal below is free.


def test_a_reading_is_built_on_each_clock() -> None:
    for value in (_source(), _deployment()):
        assert value.clock in CLOCKS
        assert value.deployment_id == DEPLOYMENT_ID
        assert value.version.startswith("sha256:")
        assert dict(value.versions).keys() == set(KINDS_ON_CLOCK[value.clock])


def test_two_identical_readings_move_neither_clock() -> None:
    """The phase's declared negative: unchanged input produces no signal."""
    movements = compare_each(
        {SOURCE: _source(), DEPLOYMENT: _deployment()},
        {SOURCE: _source(), DEPLOYMENT: _deployment()},
    )

    assert [m.clock for m in movements] == list(CLOCKS)
    assert not any(m.moved for m in movements)
    assert all(m.kinds_moved == () for m in movements)
    assert all(m.version_before == m.version_after for m in movements)


def test_the_deployment_clock_reads_the_version_t077_defines() -> None:
    """Consumption, not a second hash: the version IS `set_version_of`.

    Asserted against a moving input as well as a fixed one, because equality
    against one constant would also hold if both sides were constants.
    """
    assert dict(_deployment().versions)["served_operation_set"] == \
        set_version_of(OPERATIONS)

    withdrawn = _deployment(OPERATIONS_AFTER_WITHDRAWAL)
    assert dict(withdrawn.versions)["served_operation_set"] == \
        set_version_of(OPERATIONS_AFTER_WITHDRAWAL)
    assert withdrawn.version != _deployment().version


# ---------------------------------------------------------------------------
# Independence, in the form that is not arithmetic.


def test_a_deployment_change_moves_the_deployment_clock_only() -> None:
    movements = {
        m.clock: m
        for m in compare_each(
            {SOURCE: _source(), DEPLOYMENT: _deployment()},
            {SOURCE: _source(),
             DEPLOYMENT: _deployment(OPERATIONS_AFTER_WITHDRAWAL)},
        )
    }

    assert movements[DEPLOYMENT].moved
    assert movements[DEPLOYMENT].kinds_moved == ("served_operation_set",)
    assert not movements[SOURCE].moved
    assert movements[SOURCE].version_before == movements[SOURCE].version_after, (
        "the deployment moved and the source clock's reading moved with it, "
        "which is the fused artifact FR-027 exists to rule out"
    )


def test_a_source_change_moves_the_source_clock_only() -> None:
    movements = {
        m.clock: m
        for m in compare_each(
            {SOURCE: _source(), DEPLOYMENT: _deployment()},
            {SOURCE: _source(contract=CONTRACT_V2), DEPLOYMENT: _deployment()},
        )
    }

    assert movements[SOURCE].moved
    assert movements[SOURCE].kinds_moved == ("derived_contract",)
    assert not movements[DEPLOYMENT].moved
    assert movements[DEPLOYMENT].version_before == \
        movements[DEPLOYMENT].version_after


def test_a_change_confined_to_the_derived_checks_moves_the_source_clock() -> None:
    """Why the subset refusal matters, shown rather than argued.

    A source clock read over `derived_contract` alone would answer *unchanged*
    here.
    """
    movement = compare(_source(), _source(check="sha256:" + "4" * 64))

    assert movement.moved
    assert movement.kinds_moved == ("derived_check",)


# ---------------------------------------------------------------------------
# The refusals. One guard reachable per arm.


def test_a_deployment_version_is_refused_on_the_source_clock() -> None:
    """The mechanism behind independence.

    Every source kind is supplied as well, so the missing-kind branch cannot
    fire and this arm reaches the foreign-kind branch alone.
    """
    with pytest.raises(ClockError, match="is not read by the 'source' clock"):
        reading(
            SOURCE,
            deployment_id=DEPLOYMENT_ID,
            versions={
                "derived_contract": CONTRACT_V1,
                "derived_check": CHECK_V1,
                "served_operation_set": set_version_of(OPERATIONS),
            },
            source_ref=ANCHOR,
        )


def test_the_refusal_names_the_clock_the_foreign_kind_belongs_to() -> None:
    """An operator holding a mapping needs to know where the entry goes."""
    with pytest.raises(ClockError, match="it is on the 'deployment' clock"):
        reading(
            SOURCE,
            deployment_id=DEPLOYMENT_ID,
            versions={
                "derived_contract": CONTRACT_V1,
                "derived_check": CHECK_V1,
                "served_operation_set": set_version_of(OPERATIONS),
            },
            source_ref=ANCHOR,
        )


def test_a_clock_read_over_a_subset_of_its_kinds_is_refused() -> None:
    with pytest.raises(ClockError, match=r"without \['derived_check'\]"):
        reading(
            SOURCE,
            deployment_id=DEPLOYMENT_ID,
            versions={"derived_contract": CONTRACT_V1},
            source_ref=ANCHOR,
        )


def test_a_blank_version_is_refused() -> None:
    """Two blank versions compare equal, so the clock reports a false quiet."""
    with pytest.raises(ClockError, match="blank version"):
        reading(
            SOURCE,
            deployment_id=DEPLOYMENT_ID,
            versions={"derived_contract": CONTRACT_V1, "derived_check": "  "},
            source_ref=ANCHOR,
        )


def test_the_source_clock_is_refused_with_no_anchor() -> None:
    """FR-057, as `correspondence.py` states it: no anchor, no clock."""
    with pytest.raises(ClockError, match="source clock was read with no anchor"):
        reading(
            SOURCE,
            deployment_id=DEPLOYMENT_ID,
            versions={"derived_contract": CONTRACT_V1, "derived_check": CHECK_V1},
        )


def test_the_deployment_clock_is_refused_with_an_anchor() -> None:
    """A commit on the deployment clock is the two clocks in one field again."""
    with pytest.raises(ClockError, match="deployment clock was read anchored"):
        reading(
            DEPLOYMENT,
            deployment_id=DEPLOYMENT_ID,
            versions={"served_operation_set": set_version_of(OPERATIONS)},
            source_ref=ANCHOR,
        )


def test_the_two_clocks_are_not_comparable_against_each_other() -> None:
    """Both readings name one deployment, so only the cross-clock branch fires."""
    with pytest.raises(ClockError, match="was compared against"):
        compare(_source(), _deployment())


def test_two_deployments_are_not_comparable_on_one_clock() -> None:
    """One clock on both sides, so only the cross-deployment branch fires."""
    other = deployment_reading(deployment_id="d-other", operations=OPERATIONS)

    with pytest.raises(ClockError, match="was compared against one of"):
        compare(_deployment(), other)


def test_a_reading_for_no_deployment_is_refused() -> None:
    with pytest.raises(ClockError, match="read for no deployment"):
        reading(
            SOURCE,
            deployment_id="",
            versions={"derived_contract": CONTRACT_V1, "derived_check": CHECK_V1},
            source_ref=ANCHOR,
        )


def test_a_third_clock_is_refused() -> None:
    with pytest.raises(ClockError, match="is not a clock"):
        reading("build", deployment_id=DEPLOYMENT_ID, versions={})


def test_a_clock_absent_from_one_side_is_not_reported_as_unmoved() -> None:
    with pytest.raises(ClockError, match=r"no \['source'\] reading on the after"):
        compare_each(
            {SOURCE: _source(), DEPLOYMENT: _deployment()},
            {DEPLOYMENT: _deployment()},
        )


# ---------------------------------------------------------------------------
# The shape T139 and T140 have to be able to build on.


def test_a_reading_is_complete_with_no_successor() -> None:
    """FR-031 is narrowed by FR-047, and this file must not foreclose it.

    Where the drift signal is a failed re-fetch there is **no after artifact
    version**, because no artifact was obtained; the after term becomes
    FR-044's specification state and the timestamp of the last successful
    fetch. A `Reading` that required a successor — a mandatory `next`, an
    `after` field, a constructor taking a pair — would force T140 to invent an
    empty one, and an empty version is exactly the false quiet the blank-version
    refusal exists to stop.
    """
    names = {f.name for f in fields(Reading)}
    assert names == {"clock", "deployment_id", "versions", "source_ref"}
    assert not names & {"after", "next", "successor", "version_after",
                        "previous", "before"}

    lone = _deployment()
    assert lone.document()["version"] == lone.version
    assert not hasattr(lone, "compare"), (
        "comparison is a module function on purpose: a method reads as "
        "something every reading is expected to get a partner for"
    )


def test_movement_carries_every_term_fr_031_requires() -> None:
    movement = compare(_deployment(), _deployment(OPERATIONS_AFTER_WITHDRAWAL))
    document = movement.document()

    assert document["clock"] == DEPLOYMENT
    assert document["deployment_id"] == DEPLOYMENT_ID
    assert document["version_before"] != document["version_after"]
    assert document["kinds_moved"] == ["served_operation_set"]


def test_a_movement_that_did_not_move_names_no_kind() -> None:
    """`kinds_moved` empty exactly when `moved` is false, in both directions."""
    unmoved = compare(_source(), _source())
    moved = compare(_source(), _source(contract=CONTRACT_V2))

    assert (unmoved.moved, unmoved.kinds_moved) == (False, ())
    assert moved.moved and moved.kinds_moved


def test_the_anchor_is_beside_the_version_and_not_inside_it() -> None:
    """Symmetric with T077 keeping the deployment identity out of `set_version`.

    Folding the commit in would move the source clock for a commit that changed
    nothing derived, and would let an operator move it by editing configuration.
    """
    one = _source()
    other = replace(one, source_ref="acme/parts-api@" + "b" * 40)

    assert one.source_ref != other.source_ref
    assert one.version == other.version
    assert one.document()["source_ref"] == ANCHOR


def test_the_deployment_reading_carries_no_anchor_field_value() -> None:
    assert _deployment().source_ref is None
    assert _deployment().document()["source_ref"] is None


# ---------------------------------------------------------------------------
# Vacuity floors.


def test_the_module_reads_the_real_schema_registry() -> None:
    """An arm asserting a raise also passes over a module that imports nothing.

    `assert_partition_total(SCHEMAS)` runs at import; this states that the
    registry it ran against is the real one and carries FR-054's eight.
    """
    assert len(schemas.SCHEMAS) == 8
    assert clocks.SCHEMAS is schemas.SCHEMAS


def test_the_movements_are_returned_in_a_declared_order() -> None:
    """A detector reading positionally must not depend on dict ordering."""
    movements = compare_each(
        {DEPLOYMENT: _deployment(), SOURCE: _source()},
        {SOURCE: _source(), DEPLOYMENT: _deployment()},
    )

    assert isinstance(movements[0], Movement)
    assert tuple(m.clock for m in movements) == CLOCKS
