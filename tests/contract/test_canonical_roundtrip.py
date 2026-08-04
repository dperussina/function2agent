"""T013 — every one of FR-054's eight artifact kinds through the serializer.

A round-trip test is worth little if it only proves that `loads(dumps(x)) == x`,
because this serializer has no `loads`: it is a one-way canonical byte form for
hashing. What is actually round-tripped is the *document* — through `wrap`, into
a payload and an envelope, and back to a document that is equal to the original.
That is the property a rollback depends on (T020): a stored artifact has to
reconstitute into the document that produced it, or the version restored is not
the version that was saved.

The eight fixtures are exercised by kind, driven off the registry, so a ninth
kind cannot be added without a fixture.
"""

from __future__ import annotations

import pytest

from src.contracts import envelope, schemas
from src.contracts.canonical import NonCanonicalValue, dumps

# One realistic document per kind. Kept in this file rather than in
# tests/fixtures/ because they exist to exercise the schema registry rather
# than to back a measured claim — FR-053's discipline is about the latter.
DOCUMENTS: dict[str, dict] = {
    "served_operation_set": {
        "schema_version": "1.0.0",
        "deployment_id": "d-1",
        "operations": [{"id": "listOrders", "method": "GET"}],
        "captured_at": "2026-08-03T12:00:00Z",
        "source_url": "https://api.example.com/openapi.json",
        "analyzer_host": "runner-7",
    },
    "derived_contract": {
        "schema_version": "1.0.0",
        "deployment_id": "d-1",
        "operation_id": "listOrders",
        "reads": ["orders"],
        "writes": [],
        "preconditions": ["page >= 1"],
        "postconditions": ["len(result) <= per_page"],
        "failure_taxonomy": ["not_found", "rate_limited"],
        "derived_at": "2026-08-03T12:00:01Z",
        "source_path": "/srv/app/api/orders.py",
        "analyzer_host": "runner-7",
    },
    "derived_check": {
        "schema_version": "1.0.0",
        "deployment_id": "d-1",
        "operation_id": "listOrders",
        "check_kind": "return_type",
        "expression": "isinstance(result, list)",
        "provenance": "signature",
        "confidence": 0.9,
        "derived_at": "2026-08-03T12:00:01Z",
        "source_path": "/srv/app/api/orders.py",
    },
    "effect_gate_rule_set": {
        "schema_version": "1.0.0",
        "deployment_id": "d-1",
        "rules": [{"rule_id": "EG-TIER-001", "tier": "read_only"}],
        "deny_list": [{"rule_id": "EG-DENY-001", "operation_id": "deleteOrder"}],
        "published_at": "2026-08-03T12:00:02Z",
    },
    "egress_policy": {
        "schema_version": "1.0.0",
        "deployment_id": "d-1",
        "allowed_methods": ["GET", "HEAD"],
        "allowed_paths": ["/orders", "/orders/*"],
        "deny_rules": [{"rule_id": "EG-POL-001", "path": "/admin/*"}],
        "published_at": "2026-08-03T12:00:02Z",
    },
    "declared_location_set": {
        "schema_version": "1.0.0",
        "set_version": "2026.08.03-1",
        "deployment_id": "d-1",
        "locations": [{
            "source": "/srv/app", "target": "/workspace", "mode": "ro",
            "rule_id": "FS-DECL-001", "justification": "the analysed application",
        }],
    },
    "bounds": {
        "schema_version": "1.0.0",
        "deployment_id": "d-1",
        "memory_max_bytes": 536870912,
        "cpu_max": "200000 100000",
        "cpu_total_seconds": 120.0,
        "pids_max": 64,
    },
    "admission_decision": {
        "schema_version": "1.0.0",
        "deployment_id": "d-1",
        "admitted": True,
        "rule_id": "ADM-001",
        "reason": "the target published a machine-readable operation set",
        "decided_at": "2026-08-03T12:00:03Z",
        "decided_by_host": "runner-7",
    },
}


def test_every_registered_kind_has_a_fixture() -> None:
    assert set(DOCUMENTS) == schemas.KINDS, (
        "a kind was added to or removed from the registry without a "
        f"round-trip fixture: {set(DOCUMENTS) ^ schemas.KINDS}"
    )
    assert len(DOCUMENTS) == 8, "FR-054 enumerates eight"


@pytest.mark.parametrize("kind", sorted(DOCUMENTS))
def test_the_document_reconstitutes_from_payload_and_envelope(kind: str) -> None:
    """Payload plus context equals the document. Rollback depends on this."""
    document = DOCUMENTS[kind]
    wrapped = envelope.wrap(kind, document)
    reconstituted = {**wrapped.payload, **wrapped.context}
    assert reconstituted == document, (
        f"{kind}: the split lost or altered a field, so a stored artifact "
        "cannot be restored to what was saved (FR-054, T020)"
    )


@pytest.mark.parametrize("kind", sorted(DOCUMENTS))
def test_the_payload_serializes_and_is_stable(kind: str) -> None:
    wrapped = envelope.wrap(kind, DOCUMENTS[kind])
    assert wrapped.payload_bytes() == envelope.wrap(kind, DOCUMENTS[kind]).payload_bytes()
    assert wrapped.address.startswith("sha256:")
    assert wrapped.payload_bytes().endswith(b"\n")
    assert not wrapped.payload_bytes().startswith(b"\xef\xbb\xbf"), "byte-order mark"
    assert b"\r" not in wrapped.payload_bytes(), "CR in a canonical payload"


@pytest.mark.parametrize("kind", sorted(DOCUMENTS))
def test_each_kind_declares_its_volatile_fields_honestly(kind: str) -> None:
    """Every declared volatile field is actually present in the fixture.

    A `volatile` tuple naming a field no document carries is dead declaration,
    and dead declaration is how the scanner's coverage silently shrinks.
    """
    schema = schemas.require(kind)
    document = DOCUMENTS[kind]
    for name in schema.volatile:
        assert name in document, (
            f"{kind} declares {name!r} volatile but no fixture carries it"
        )


def test_a_document_at_the_wrong_schema_version_is_refused() -> None:
    stale = {**DOCUMENTS["bounds"], "schema_version": "0.9.0"}
    with pytest.raises(schemas.SchemaError, match="schema_version"):
        envelope.wrap("bounds", stale)


def test_a_missing_required_field_is_refused() -> None:
    incomplete = {k: v for k, v in DOCUMENTS["bounds"].items() if k != "pids_max"}
    with pytest.raises(schemas.SchemaError, match="pids_max"):
        envelope.wrap("bounds", incomplete)


def test_a_kind_outside_the_eight_is_refused() -> None:
    with pytest.raises(schemas.SchemaError, match="eight artifact kinds"):
        envelope.wrap("session_trace", {"schema_version": "1.0.0"})


def test_an_unserializable_value_is_refused_rather_than_repr_ed() -> None:
    """The failure mode this replaces: `repr()` of an object in a hashed
    payload, which embeds a memory address and changes every run."""
    class Opaque:
        pass

    with pytest.raises(NonCanonicalValue):
        dumps({"schema_version": "1.0.0", "thing": Opaque()})


def test_nan_and_infinity_have_no_canonical_form() -> None:
    for bad in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(NonCanonicalValue):
            dumps({"v": bad})
