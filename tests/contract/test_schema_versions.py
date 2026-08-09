"""T015 — a breaking change to a schema is a MAJOR bump (FR-034, Principle VIII).

**What this gate actually catches.** A contributor removes a required field, or
renames one, or changes a schema's meaning, and bumps the patch digit — or does
not bump at all. Consumers written against the old shape then fail at runtime
against data that is structurally valid. Principle VIII requires versioned
artifacts; this is the check that the version means something.

**How it knows what the schema used to be.** By a committed baseline in this
file. There is no clever introspection of git history: the baseline is data a
human wrote down, and changing it is a visible diff in the same commit as the
schema change, which is precisely where a reviewer should see it. A gate whose
expectations live in git history is a gate you cannot review.
"""

from __future__ import annotations

import pytest

from src.contracts import migrations, schemas

# The committed baseline. Every entry is (version, sorted required fields).
# CHANGING AN ENTRY HERE IS THE POINT: if you removed or renamed a required
# field, this file must change in the same commit, and the version you write
# has to be a MAJOR bump. If you only added an optional field, the version is a
# MINOR bump and `required` is unchanged.
BASELINE: dict[str, tuple[str, tuple[str, ...]]] = {
    # **Moved to 1.1.0 by T077**, which added `set_version` and `captured_at`
    # to `required`. A MINOR bump and not a MAJOR one because nothing was
    # removed or renamed and a 1.0.0 document migrates forward — `set_version`
    # is recovered from the document's own operations rather than invented,
    # which is the difference from the `admission_decision` migration below.
    "served_operation_set": ("1.1.0", (
        "captured_at", "deployment_id", "operations", "schema_version",
        "set_version")),
    "derived_contract": ("1.0.0", (
        "deployment_id", "failure_taxonomy", "operation_id", "postconditions",
        "preconditions", "reads", "schema_version", "writes")),
    "derived_check": ("1.0.0", (
        "check_kind", "confidence", "deployment_id", "expression",
        "operation_id", "provenance", "schema_version")),
    "effect_gate_rule_set": ("1.0.0", (
        "deny_list", "deployment_id", "rules", "schema_version")),
    "egress_policy": ("1.0.0", (
        "allowed_methods", "allowed_paths", "deny_rules", "deployment_id",
        "schema_version")),
    "declared_location_set": ("1.0.0", (
        "deployment_id", "locations", "schema_version", "set_version")),
    "bounds": ("1.0.0", (
        "cpu_max", "cpu_total_seconds", "deployment_id", "memory_max_bytes",
        "pids_max", "schema_version")),
    # **Deliberately left at 1.0.0 by T074, which moved this kind to 1.1.0.**
    # The three fields T074 added are FR-044's three named things — the state
    # found, the criterion that failed, and what the operator would have to
    # change — and MINOR is the right bump because a 1.0.0 consumer still reads
    # every field it knew.
    #
    # The entry is not advanced to 1.1.0 because advancing it silences the
    # three guards that check the move. With the baseline at 1.0.0,
    # `test_an_added_required_field_is_at_least_a_minor_bump` asserts the
    # version moved and `test_every_superseded_version_has_a_migration` asserts
    # the 1.0.0 -> 1.1.0 migration is registered; with it at 1.1.0 both return
    # early and assert nothing. The docstring above says changing an entry is
    # the point, and it is — for a *removal*, where the diff is the review. For
    # an *addition* the entry is what the guard compares against, and updating
    # it in the same commit is how this file becomes a tautology. That tension
    # is in the instrument rather than in this change, and is recorded here
    # rather than resolved unilaterally.
    "admission_decision": ("1.0.0", (
        "admitted", "deployment_id", "reason", "rule_id", "schema_version")),
}


def _major(version: str) -> int:
    return int(version.split(".")[0])


def test_the_baseline_covers_every_kind() -> None:
    assert set(BASELINE) == schemas.KINDS, (
        "a kind was added or removed without updating the version baseline: "
        f"{set(BASELINE) ^ schemas.KINDS}"
    )


@pytest.mark.parametrize("kind", sorted(BASELINE))
def test_a_removed_or_renamed_required_field_is_a_major_bump(kind: str) -> None:
    baseline_version, baseline_required = BASELINE[kind]
    schema = schemas.require(kind)
    current_required = tuple(sorted(schema.required))

    removed = set(baseline_required) - set(current_required)
    if not removed:
        return

    assert _major(schema.version) > _major(baseline_version), (
        f"{kind} dropped required field(s) {sorted(removed)} but moved from "
        f"{baseline_version} to {schema.version}. Removing a field a consumer "
        "reads is a breaking change and Principle VIII requires a MAJOR bump."
    )


@pytest.mark.parametrize("kind", sorted(BASELINE))
def test_an_added_required_field_is_at_least_a_minor_bump(kind: str) -> None:
    """A newly required field breaks producers, not consumers.

    Treated as at least MINOR rather than MAJOR because the artifacts already
    written stay readable — a consumer that ignores the new field still works.
    A producer that omits it fails loudly at `validate`, which is the correct
    place for that to surface.
    """
    baseline_version, baseline_required = BASELINE[kind]
    schema = schemas.require(kind)
    added = set(schema.required) - set(baseline_required)
    if not added:
        return
    assert schema.version != baseline_version, (
        f"{kind} added required field(s) {sorted(added)} without moving off "
        f"{baseline_version}. Two different shapes now claim the same schema "
        "version, and nothing can tell them apart."
    )


@pytest.mark.parametrize("kind", sorted(BASELINE))
def test_the_version_never_moves_backwards(kind: str) -> None:
    baseline_version, _ = BASELINE[kind]
    schema = schemas.require(kind)
    assert _tuple(schema.version) >= _tuple(baseline_version), (
        f"{kind} moved from {baseline_version} back to {schema.version}"
    )


def _tuple(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


@pytest.mark.parametrize("kind", sorted(schemas.KINDS))
def test_every_superseded_version_has_a_migration(kind: str) -> None:
    """A version bump with no migration strands the artifacts already stored.

    FR-054 requires restoring the immediately prior version to be one operator
    action. If the prior version's schema cannot be brought forward, that
    action restores something the runtime cannot read.
    """
    schema = schemas.require(kind)
    baseline_version, _ = BASELINE[kind]
    if baseline_version == schema.version:
        return
    assert (kind, baseline_version) in migrations._BY_SOURCE, (
        f"{kind} moved from {baseline_version} to {schema.version} with no "
        f"registered migration. Artifacts stored at {baseline_version} are "
        "now unreadable, and FR-054's rollback is a rollback to something "
        "that cannot be loaded."
    )


def test_the_schema_version_is_distinct_from_the_content_version() -> None:
    """Principle VI separates identity from version; Principle VIII versions
    artifacts. These are two different numbers and the registry must not
    conflate them: `schema.version` describes the shape, and the content
    address describes the instance.
    """
    from src.contracts import envelope
    from tests.contract.test_canonical_roundtrip import DOCUMENTS

    a = envelope.wrap("bounds", DOCUMENTS["bounds"])
    changed = {**DOCUMENTS["bounds"], "pids_max": 128}
    b = envelope.wrap("bounds", changed)

    assert a.schema_version == b.schema_version, (
        "changing a value moved the schema version; the shape did not change"
    )
    assert a.address != b.address, (
        "changing a value did not move the content address; the instance did "
        "change"
    )
