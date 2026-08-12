"""T014 — the migration framework, exercised through ~~the one migration that
exists~~ **the first of the five the registry now holds. Corrected 2026-08-12.**

**The digit is struck rather than substituted because the sentence carried a
second error that advancing it alone would have preserved.** This module drives
**one** kind from end to end and never did exercise the registry, so "the five
migrations that exist" would be a fresh falsehood wearing the shape of a
correction. The four later ones — `admission_decision`, `served_operation_set`,
`derived_contract` and `derived_check`, each 1.0.0 to 1.1.0 — are exercised where
their kinds are: `tests/contract/test_admission.py`,
`tests/contract/test_served_operations.py` and `tests/unit/test_derived_record.py`.

What *is* registry-wide here is `test_two_migrations_cannot_claim_the_same_source`,
which iterates `MIGRATIONS` itself. At one entry it was vacuous — a single key
cannot collide with itself — and at five it is a live check, so the arm the count
made pointless is the one the count moving repaired.

The migration this module drives is real rather than illustrative:
`declared_location_set` entries did not originally carry `rule_id` and
`justification`, and they were added when FR-048 required each declaration to
name the rule that declares it.
"""

from __future__ import annotations

import pytest

from src.contracts import envelope, migrations, schemas

PRE_1_0_0 = {
    "schema_version": "0.9.0",
    "set_version": "2026.07.30-1",
    "deployment_id": "d-legacy",
    "locations": [
        {"source": "/srv/app", "target": "/workspace", "mode": "ro"},
        {"source": "/opt/toolchain", "target": "/opt/toolchain", "mode": "ro"},
    ],
}


def test_the_migration_brings_a_legacy_document_to_the_current_version() -> None:
    migrated = migrations.migrate("declared_location_set", PRE_1_0_0)
    assert migrated["schema_version"] == "1.0.0"
    schemas.require("declared_location_set").validate(migrated)
    for entry in migrated["locations"]:
        assert entry["rule_id"]
        assert entry["justification"]


def test_the_migration_does_not_fabricate_a_rule_identifier() -> None:
    """The unrecoverable field is marked, not invented.

    Same choice `fs_decisions` makes for an unreadable path: a value that
    cannot be recovered is recorded as such rather than presented as fact. An
    operator reading `FS-DECL-MIGRATED` learns the declaration predates the
    requirement; one reading a plausible-looking `FS-DECL-001` learns something
    false.
    """
    migrated = migrations.migrate("declared_location_set", PRE_1_0_0)
    for entry in migrated["locations"]:
        assert entry["rule_id"] == "FS-DECL-MIGRATED"
        assert "not recoverable" in entry["justification"]


def test_a_migrated_document_survives_wrapping() -> None:
    """The point of migrating: the artifact becomes usable, not merely valid."""
    migrated = migrations.migrate("declared_location_set", PRE_1_0_0)
    wrapped = envelope.wrap("declared_location_set", migrated)
    assert wrapped.address.startswith("sha256:")


def test_a_document_already_current_passes_through_unchanged() -> None:
    current = migrations.migrate("declared_location_set", PRE_1_0_0)
    again = migrations.migrate("declared_location_set", current)
    assert again == current


def test_a_document_with_no_path_forward_is_refused_not_passed_through() -> None:
    """The failure this framework exists to prevent.

    A migrate() that returned the document unchanged when it did not recognise
    the version would hand a consumer a shape it cannot read, and the failure
    would surface as a field access somewhere else entirely.
    """
    orphan = {**PRE_1_0_0, "schema_version": "0.1.0"}
    with pytest.raises(migrations.MigrationError, match="no migration from"):
        migrations.migrate("declared_location_set", orphan)


def test_a_kind_with_no_migrations_still_refuses_a_stale_version() -> None:
    with pytest.raises(migrations.MigrationError, match="no migration from"):
        migrations.migrate("bounds", {"schema_version": "0.5.0"})


def test_two_migrations_cannot_claim_the_same_source() -> None:
    """Asserted against the registry as built, because the check runs at import
    and a duplicate would otherwise only be caught by whoever noticed."""
    seen = set()
    for migration in migrations.MIGRATIONS:
        key = (migration.kind, migration.from_version)
        assert key not in seen, f"{key} has two migrations"
        seen.add(key)


def test_an_undeclared_lossy_migration_is_refused() -> None:
    """A migration that drops a field it did not declare must fail.

    Built here rather than shipped, because the registry contains no lossy
    migration yet and the guard would otherwise be untested until the first one
    is written — which is exactly when it is needed.
    """
    lossy = migrations.Migration(
        kind="declared_location_set",
        from_version="0.8.0",
        to_version="1.0.0",
        reason="test double",
        apply=lambda d: {
            "schema_version": "1.0.0",
            "set_version": d["set_version"],
            "deployment_id": d["deployment_id"],
            "locations": [],  # silently discards every declared location
        },
    )
    original = migrations._BY_SOURCE.get(("declared_location_set", "0.8.0"))
    migrations._BY_SOURCE[("declared_location_set", "0.8.0")] = lossy
    try:
        with pytest.raises(migrations.MigrationError, match="without declaring"):
            migrations.migrate(
                "declared_location_set", {**PRE_1_0_0, "schema_version": "0.8.0"})
    finally:
        if original is None:
            del migrations._BY_SOURCE[("declared_location_set", "0.8.0")]
        else:
            migrations._BY_SOURCE[("declared_location_set", "0.8.0")] = original


def test_a_declared_lossy_migration_is_permitted() -> None:
    """The other half: losing a field is allowed when it is written down."""
    declared = migrations.Migration(
        kind="declared_location_set",
        from_version="0.8.0",
        to_version="1.0.0",
        reason="test double",
        apply=lambda d: {
            "schema_version": "1.0.0",
            "set_version": d["set_version"],
            "deployment_id": d["deployment_id"],
            "locations": [
                {**e, "rule_id": "FS-DECL-MIGRATED", "justification": "x"}
                for e in d["locations"]
            ],
        },
        drops=("locations[].mode",),
    )
    key = ("declared_location_set", "0.8.0")
    migrations._BY_SOURCE[key] = declared
    try:
        source = {
            **PRE_1_0_0,
            "schema_version": "0.8.0",
            "locations": [{"source": "/srv/app", "target": "/workspace", "mode": "ro"}],
        }
        result = migrations.migrate("declared_location_set", source)
        assert result["schema_version"] == "1.0.0"
    finally:
        del migrations._BY_SOURCE[key]


def test_a_migration_that_lands_on_the_wrong_version_is_refused() -> None:
    liar = migrations.Migration(
        kind="bounds", from_version="0.9.0", to_version="1.0.0",
        reason="test double",
        apply=lambda d: {**d, "schema_version": "0.9.1"},
    )
    key = ("bounds", "0.9.0")
    migrations._BY_SOURCE[key] = liar
    try:
        with pytest.raises(migrations.MigrationError, match="claimed to produce"):
            migrations.migrate("bounds", {"schema_version": "0.9.0"})
    finally:
        del migrations._BY_SOURCE[key]
