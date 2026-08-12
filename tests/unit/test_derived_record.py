"""OD-32 — the provenance requirement at schema 1.1.0, and the version gate.

**Both directions, because a gate tested one way is a filter.** The forward
direction is that a document claiming 1.1.0 without FR-026's six fields is
refused — by the schema, by the envelope and by the reader. The backward
direction is that a 1.0.0 document is still readable and comes back with its
provenance explicitly absent and named. A suite that only asserted the second
would pass over a schema that required nothing.

The defect these arms exist to prevent is the one the journal's pricing seam
removed: `spend_usd` became `float | None` *specifically so that* **unpriced**
and **cost nothing** stopped being the same value. Here the pair is **absent**
and **provisional**, and several arms below assert nothing more than that the two
are different values reached through different mechanisms — which is the point
rather than a tautology, because the cheap implementation of this feature makes
them equal.
"""

from __future__ import annotations

import dataclasses

import pytest

from src.analysis.derived_record import (
    DERIVED_KINDS,
    PROVENANCE_REQUIRED_FROM,
    READABLE_SCHEMA_VERSIONS,
    DerivedRecord,
    DerivedRecordError,
    LoadedDerivations,
    ProvenanceState,
    UnprovenancedArtifactError,
    load_derived,
)
from src.analysis.provenance import (
    Provenance,
    ProvenanceError,
    ValidationStatus,
)
from src.contracts import envelope, migrations, schemas

DEPLOYMENT = "d-1"

# A complete FR-026 record, as data rather than as a constructed `Provenance`,
# because every arm here is about what a *stored document* carries.
FULL_PROVENANCE = {
    "derivation_rule": "return_annotation",
    "source_symbol": "list_orders",
    "source_file": "orders.py",
    "analyzer_version": "0.1.0",
    "content_hash": "sha256:" + "b" * 64,
    "validation_status": "provisional",
    "validated_against": None,
}


def _contract(*, version: str, provenance: object = ...) -> dict:
    """A `derived_contract` document at `version`.

    `provenance` defaults to the sentinel `...` meaning *no key at all*, which is
    what every 1.0.0 contract document looks like: 1.0.0 listed the field in
    neither `required` nor `volatile` for this kind, so nothing put it there and
    nothing missed it.
    """
    document = {
        "schema_version": version,
        "deployment_id": DEPLOYMENT,
        "operation_id": "listOrders",
        "reads": ["orders"],
        "writes": [],
        "preconditions": [],
        "postconditions": [],
        "failure_taxonomy": ["not_found"],
    }
    if provenance is not ...:
        document["provenance"] = provenance
    return document


def _check(*, version: str, provenance: object = ...) -> dict:
    document = {
        "schema_version": version,
        "deployment_id": DEPLOYMENT,
        "operation_id": "listOrders",
        "check_kind": "return_type",
        "expression": "isinstance(result, list)",
        "confidence": 0.9,
    }
    if provenance is not ...:
        document["provenance"] = provenance
    return document


# ---------------------------------------------------------------------------
# The two facts the gate is built on, asserted against the registry rather than
# retyped. A constant that agrees with the schema by coincidence is a constant
# that will disagree with it later.


def test_the_requirement_starts_at_the_version_the_registry_holds() -> None:
    assert PROVENANCE_REQUIRED_FROM == schemas.DERIVED_CONTRACT.version
    assert PROVENANCE_REQUIRED_FROM == schemas.DERIVED_CHECK.version
    assert PROVENANCE_REQUIRED_FROM == "1.1.0"


def test_both_derived_kinds_require_the_six_fields() -> None:
    for kind in DERIVED_KINDS:
        schema = schemas.require(kind)
        assert "provenance" in schema.required, kind
        assert schema.required_provenance == schemas.FR_026_PROVENANCE_FIELDS, kind


def test_the_six_names_here_and_the_dataclass_agree_in_both_directions() -> None:
    """`schemas.py` restates FR-026's six because it may not import the analysis
    layer — see that module's docstring. This is the check that pays for it.

    Both directions, not one: a subset assertion passes when the schema requires
    fewer fields than the record carries, which is precisely the 1.0.0 defect.
    """
    declared = set(schemas.FR_026_PROVENANCE_FIELDS)
    on_the_record = {f.name for f in dataclasses.fields(Provenance)}
    assert declared <= on_the_record, declared - on_the_record
    # `validated_against` is the one field on the record that FR-026 does not
    # name, and it is conditional — requiring it would invalidate every
    # provisional record. So the difference is exactly that field, asserted
    # rather than excused by an inequality.
    assert on_the_record - declared == {"validated_against"}


# ---------------------------------------------------------------------------
# Forward: a document claiming 1.1.0 carries all six or is refused.


def test_a_current_document_with_no_provenance_is_refused_by_the_schema() -> None:
    with pytest.raises(schemas.SchemaError, match="missing \\['provenance'\\]"):
        schemas.require("derived_contract").validate(
            _contract(version=PROVENANCE_REQUIRED_FROM))


def test_a_current_document_with_an_empty_provenance_object_is_refused() -> None:
    """The shape the requirement would otherwise be satisfied by.

    An empty object passes a presence test over top-level keys and carries none
    of FR-026's six. It is also not an absence a reader can enumerate — it is a
    provenance record that claims nothing — so it is refused rather than read as
    one.
    """
    with pytest.raises(schemas.SchemaError, match="provenance is missing"):
        schemas.require("derived_contract").validate(
            _contract(version=PROVENANCE_REQUIRED_FROM, provenance={}))


def test_a_current_document_with_a_partial_provenance_record_is_refused() -> None:
    partial = {k: v for k, v in FULL_PROVENANCE.items()
               if k not in ("analyzer_version", "content_hash")}
    with pytest.raises(schemas.SchemaError, match="analyzer_version"):
        schemas.require("derived_check").validate(
            _check(version=PROVENANCE_REQUIRED_FROM, provenance=partial))


def test_a_current_document_may_not_declare_its_provenance_absent() -> None:
    """**The limb OD-32 turns on, and the one a convenient implementation gets
    wrong.**

    A null here would be a document declaring 1.1.0 while not satisfying 1.1.0.
    Permit it and the schema loses the one capability this bump was made to add:
    telling a pre-requirement artifact from a current producer's omission. The
    absence a 1.0.0 artifact genuinely has lives on the read-back object, which
    the arms further down exercise.
    """
    with pytest.raises(schemas.SchemaError, match="not a provenance record"):
        schemas.require("derived_contract").validate(
            _contract(version=PROVENANCE_REQUIRED_FROM, provenance=None))


def test_a_current_document_whose_provenance_is_a_string_is_refused() -> None:
    """1.0.0's actual `derived_check` hole, closed.

    `provenance` was in `required` for this kind from its first version, so the
    string `"signature"` satisfied the schema and carried none of the six.
    """
    with pytest.raises(schemas.SchemaError, match="not a provenance record"):
        schemas.require("derived_check").validate(
            _check(version=PROVENANCE_REQUIRED_FROM, provenance="signature"))


def test_the_envelope_refuses_an_unprovenanced_current_document() -> None:
    """The requirement holds at the stage that stores, not only at `validate`.

    `envelope.wrap` is what a producer actually calls, so a requirement enforced
    only by a validator nobody invokes on the write path is enforced nowhere.
    """
    with pytest.raises(schemas.SchemaError):
        envelope.wrap("derived_contract",
                      _contract(version=PROVENANCE_REQUIRED_FROM))


def test_a_complete_current_document_wraps_and_reads() -> None:
    """The accepting arm, so the arms above are not passing on a broken fixture."""
    document = _contract(version=PROVENANCE_REQUIRED_FROM,
                         provenance=FULL_PROVENANCE)
    wrapped = envelope.wrap("derived_contract", document)
    assert wrapped.address.startswith("sha256:")

    record = DerivedRecord.from_document("derived_contract", document)
    assert record.is_provenanced is True
    assert record.provenance_state is ProvenanceState.PROVISIONAL
    assert record.require_provenance().source_symbol == "list_orders"
    assert record.declared_schema_version == PROVENANCE_REQUIRED_FROM


def test_the_reader_refuses_a_current_document_the_schema_refuses() -> None:
    """The reader is not the one place the requirement goes unenforced.

    Stated as its own arm because the reader has a legitimate leniency at 1.0.0,
    and a leniency that leaked into the current version would be invisible: the
    absence would simply start reading as a fact everywhere.
    """
    with pytest.raises(schemas.SchemaError):
        DerivedRecord.from_document(
            "derived_contract",
            _contract(version=PROVENANCE_REQUIRED_FROM, provenance={}))


# ---------------------------------------------------------------------------
# Backward: a 1.0.0 document is readable, and its state is named on the object.


def test_a_legacy_contract_is_readable_and_comes_back_unprovenanced() -> None:
    record = DerivedRecord.from_document("derived_contract",
                                         _contract(version="1.0.0"))
    assert record.provenance is None
    assert record.is_provenanced is False
    assert record.provenance_state is ProvenanceState.ABSENT
    # And the artifact survives: refusing was the alternative, and it makes a
    # 1.0.0 artifact's non-compliance unreadable rather than making it compliant.
    assert record.operation_id == "listOrders"
    assert record.deployment_id == DEPLOYMENT
    assert record.declared_schema_version == "1.0.0"


def test_a_legacy_document_is_read_at_its_own_version_not_rewritten() -> None:
    """The precedent's actual mechanism, asserted.

    `decode_model_outcome` reads a revision-1 payload and returns a response with
    `spend_usd=None`; the payload on disk stays a revision-1 payload. So here:
    the record reports the version the **document** declared, and the document is
    not mutated into something claiming 1.1.0.
    """
    document = _contract(version="1.0.0")
    before = dict(document)
    record = DerivedRecord.from_document("derived_contract", document)
    assert document == before
    assert record.declared_schema_version == "1.0.0"
    assert record.declared_schema_version != PROVENANCE_REQUIRED_FROM


def test_asking_an_unprovenanced_artifact_for_its_provenance_raises() -> None:
    """No placeholder, on the reasoning that gives `require_spend_usd` no
    `spend_usd_or_zero` companion: the coercion is the defect."""
    record = DerivedRecord.from_document("derived_contract",
                                         _contract(version="1.0.0"))
    with pytest.raises(UnprovenancedArtifactError, match="carries no provenance"):
        record.require_provenance()


def test_the_refusal_names_the_version_and_the_remedy() -> None:
    """A refusal an operator cannot act on is a refusal they will route around.

    The message has to carry which revision the artifact was written at, where
    the requirement starts, and that re-derivation is the way out — otherwise the
    first reader to hit it will reach for a placeholder.
    """
    record = DerivedRecord.from_document("derived_contract",
                                         _contract(version="1.0.0"))
    with pytest.raises(UnprovenancedArtifactError) as raised:
        record.require_provenance()
    message = str(raised.value)
    assert "1.0.0" in message
    assert PROVENANCE_REQUIRED_FROM in message
    assert "Re-derive from source" in message
    assert "provisional" in message


def test_a_legacy_document_that_kept_its_provenance_keeps_it() -> None:
    """The absence is reported where it exists and nowhere else.

    Every artifact this repository ever wrote looks like this: the producer has
    attached all six fields since T121 and it was the *schema* that required
    nothing. A reader that reported these as unprovenanced because the document
    is old would make the disclosure useless by making it universal.
    """
    record = DerivedRecord.from_document(
        "derived_check", _check(version="1.0.0", provenance=FULL_PROVENANCE))
    assert record.is_provenanced is True
    assert record.provenance_state is ProvenanceState.PROVISIONAL
    assert record.require_provenance().derivation_rule == "return_annotation"


def test_a_legacy_provenance_value_that_is_neither_is_refused() -> None:
    """1.0.0 `derived_check`'s bare string: no honest reading exists.

    Reading it as a record invents five fields; reading it as an absence discards
    the claim it makes. So it is refused, and the population is empty by
    construction of the only producer — which is why this is a recorded refusal
    rather than a migration.
    """
    with pytest.raises(DerivedRecordError, match="neither a provenance record"):
        DerivedRecord.from_document(
            "derived_check", _check(version="1.0.0", provenance="signature"))


def test_a_legacy_partial_provenance_record_is_refused() -> None:
    partial = {k: v for k, v in FULL_PROVENANCE.items() if k != "content_hash"}
    with pytest.raises(ProvenanceError, match="content_hash"):
        DerivedRecord.from_document(
            "derived_check", _check(version="1.0.0", provenance=partial))


def test_a_legacy_document_missing_a_field_1_0_0_did_require_is_refused() -> None:
    """The leniency is scoped to provenance and to nothing else.

    OD-32 excuses `provenance` at 1.0.0 because 1.0.0 did not require it. Every
    other field in `required` was required then, so a document missing one is
    malformed at its own version rather than merely old — and reading it would
    turn this gate into a general-purpose loosening of the schema.
    """
    document = _contract(version="1.0.0")
    del document["failure_taxonomy"]
    with pytest.raises(DerivedRecordError, match="failure_taxonomy"):
        DerivedRecord.from_document("derived_contract", document)


# ---------------------------------------------------------------------------
# Absent is not provisional. Three mechanisms, because one is one place to lose
# it.


def test_absent_and_provisional_are_different_states() -> None:
    absent = DerivedRecord.from_document("derived_contract",
                                         _contract(version="1.0.0"))
    provisional = DerivedRecord.from_document(
        "derived_contract",
        _contract(version=PROVENANCE_REQUIRED_FROM, provenance=FULL_PROVENANCE))

    assert provisional.require_provenance().validation_status is (
        ValidationStatus.PROVISIONAL)
    assert absent.provenance_state is not provisional.provenance_state
    assert absent.is_provenanced is not provisional.is_provenanced
    # The value itself, which is the level the confusion actually happens at.
    assert absent.provenance is None
    assert provisional.provenance is not None


def test_the_validation_status_enum_gains_no_absent_member() -> None:
    """The collapse this decision forbids, asserted at the enum.

    A third member here would make an absence reachable through the same field a
    derivation's own claim is read from, and every consumer keying off
    `validation_status` would then treat *no record* as a weak record.
    """
    assert {s.value for s in ValidationStatus} == {"provisional", "validated"}
    assert "absent" not in {s.value for s in ValidationStatus}
    # And the reader's three-state view is a superset rather than a redefinition:
    # the two status values keep their names, so a reader cannot be reading one
    # vocabulary while a producer writes another.
    assert {s.value for s in ProvenanceState} == {
        "absent", "provisional", "validated"}


def test_no_accessor_offers_a_provenance_placeholder() -> None:
    """The companion that would undo all of this, asserted absent.

    `ModelResponse` has `require_spend_usd` and deliberately no
    `spend_usd_or_zero`. The same shape is refused here: a caller who finds the
    raising accessor inconvenient must handle the absence, not route around it.
    """
    for name in dir(DerivedRecord):
        assert "or_placeholder" not in name
        assert "or_provisional" not in name
        assert "_or_" not in name or name.startswith("__")


# ---------------------------------------------------------------------------
# The disclosure a caller holding the object can read.


def test_the_loaded_set_names_which_artifacts_are_unprovenanced() -> None:
    """`ResumePlan.unpriced_turns`, one field over.

    Specific rather than a set-level flag: with a flag, an old artifact beside a
    current one makes the whole set look untraceable and nobody can act on it.
    """
    loaded = load_derived("derived_contract", [
        _contract(version="1.0.0"),
        {**_contract(version=PROVENANCE_REQUIRED_FROM,
                     provenance=FULL_PROVENANCE),
         "operation_id": "getOrder"},
    ])
    assert loaded.unprovenanced_operations == ("listOrders",)
    assert loaded.has_unprovenanced is True
    assert len(loaded.records) == 2


def test_a_fully_provenanced_set_discloses_nothing() -> None:
    loaded = load_derived("derived_contract", [
        _contract(version=PROVENANCE_REQUIRED_FROM, provenance=FULL_PROVENANCE),
    ])
    assert loaded.unprovenanced_operations == ()
    assert loaded.has_unprovenanced is False


def test_the_disclosure_cannot_disagree_with_the_records() -> None:
    """The disclosure is one fact written twice, so it is cross-checked.

    A disclosure computed once and then allowed to drift is indistinguishable
    from a field nothing reads — and the direction it drifts in is the one where
    an unprovenanced artifact stops being named.
    """
    record = DerivedRecord.from_document("derived_contract",
                                         _contract(version="1.0.0"))
    with pytest.raises(DerivedRecordError, match="unprovenanced_operations"):
        LoadedDerivations(kind="derived_contract", records=(record,),
                          unprovenanced_operations=())


def test_a_set_cannot_span_the_two_derived_kinds() -> None:
    contract = DerivedRecord.from_document("derived_contract",
                                           _contract(version="1.0.0"))
    with pytest.raises(DerivedRecordError, match="derived_contract record"):
        LoadedDerivations(kind="derived_check", records=(contract,),
                          unprovenanced_operations=("listOrders",))


def test_a_record_of_another_kind_is_refused() -> None:
    with pytest.raises(DerivedRecordError, match="not a derived kind"):
        DerivedRecord(kind="bounds", deployment_id=DEPLOYMENT,
                      operation_id="x", declared_schema_version="1.0.0",
                      provenance=None)


def test_an_unnameable_record_is_refused_rather_than_disclosed_blank() -> None:
    """An absence disclosed as an empty identifier is an absence nobody can act
    on, which is the failure mode this whole disclosure exists to avoid."""
    with pytest.raises(DerivedRecordError, match="operation_id is empty"):
        DerivedRecord(kind="derived_contract", deployment_id=DEPLOYMENT,
                      operation_id="  ", declared_schema_version="1.0.0",
                      provenance=None)


# ---------------------------------------------------------------------------
# The gate's outer edges.


def test_a_later_revision_is_refused_rather_than_partially_read() -> None:
    """Finding 016's defect, arriving through the artifact store.

    A document from a revision this build has never seen has fields this build
    does recognise, and reading those is how a rebuild silently drops whatever it
    did not know about.
    """
    with pytest.raises(DerivedRecordError, match="declares schema_version"):
        DerivedRecord.from_document(
            "derived_contract",
            _contract(version="2.0.0", provenance=FULL_PROVENANCE))


def test_an_unrecognised_earlier_revision_is_refused() -> None:
    with pytest.raises(DerivedRecordError, match="this build reads"):
        DerivedRecord.from_document("derived_contract",
                                    _contract(version="0.9.0"))


def test_the_readable_versions_are_enumerated_rather_than_bounded() -> None:
    """A bound accepts a revision nobody wrote a branch for.

    Same reasoning as `READABLE_MODEL_OUTCOME_SCHEMAS`. Asserted as a closed set
    so that adding a version is a visible diff in the commit that adds its
    branch.
    """
    assert READABLE_SCHEMA_VERSIONS == frozenset({"1.0.0", "1.1.0"})


# ---------------------------------------------------------------------------
# The migration, which is FR-054's obligation and a different job from reading.


def test_the_migration_carries_a_surviving_provenance_record_forward() -> None:
    migrated = migrations.migrate(
        "derived_check", _check(version="1.0.0", provenance=FULL_PROVENANCE))
    assert migrated["schema_version"] == PROVENANCE_REQUIRED_FROM
    assert migrated["provenance"] == FULL_PROVENANCE
    # Recovered, not reconstructed: the result validates and stores.
    schemas.require("derived_check").validate(migrated)
    assert envelope.wrap("derived_check", migrated).address.startswith("sha256:")


def test_the_migration_refuses_to_produce_an_unprovenanced_current_document() -> None:
    """**The alternative implementation, refused at the point it would occur.**

    Writing `{"provenance": None, "schema_version": "1.1.0"}` here is the obvious
    sibling of the three migrations already registered, each of which brings a
    document forward with an unrecoverable field marked. It is refused because the
    output would be a document *declaring* 1.1.0 without satisfying it — and one
    such artifact in the store ends the schema's ability to tell a pre-requirement
    artifact from a current producer's omission.
    """
    with pytest.raises(migrations.MigrationError, match="refused deliberately"):
        migrations.migrate("derived_contract", _contract(version="1.0.0"))


def test_the_migration_does_not_invent_a_sentinel_provenance_record() -> None:
    """The location-set migration's move, and why it cannot be made here.

    `declared_location_set` fills an unrecoverable `rule_id` with
    `FS-DECL-MIGRATED`, which is right for a free-form string. A provenance record
    must carry a `validation_status`, and that field has two members with none
    meaning *not looked at* — so a sentinel record necessarily reads
    `provisional`, which is a claim about evidence made on behalf of a derivation
    that compared itself to nothing. That is `spend_usd: 0.0` one field over.
    """
    with pytest.raises(migrations.MigrationError) as raised:
        migrations.migrate("derived_check", _check(version="1.0.0"))
    assert "re-deriving from source" in str(raised.value)
    # Nothing partial escaped: the refusal is total, so no half-migrated document
    # can be picked up by a caller that ignored the exception's type.
    assert "null provenance" in str(raised.value)


def test_the_migration_refuses_a_partial_record_rather_than_completing_it() -> None:
    partial = {k: v for k, v in FULL_PROVENANCE.items()
               if k != "analyzer_version"}
    with pytest.raises(migrations.MigrationError, match="analyzer_version"):
        migrations.migrate("derived_contract",
                           _contract(version="1.0.0", provenance=partial))


# ---------------------------------------------------------------------------
# The asymmetry: the producer holds no absence, and only the reader may.


def test_a_derived_contract_cannot_be_constructed_without_provenance() -> None:
    """**Where the guard is not placed is the improvement over the precedent.**

    The pricing seam had to widen `ModelResponse.spend_usd` because one type
    served both the producer and the reader. Here there are two types, so the
    nullable field is confined to the direction that genuinely has an absence to
    report and no fresh derivation can reach an unprovenanced document by
    omission. Refused at construction rather than at `to_document`, because a
    contract held in memory is read without being wrapped.
    """
    from src.analysis.derive import DerivationError, DerivedContract

    with pytest.raises(DerivationError, match="no provenance"):
        DerivedContract(
            operation_id="listOrders", reads=(), writes=(),
            preconditions=(), postconditions=(), failure_taxonomy=(),
            provenance=None, checks=())


def test_a_derived_check_cannot_be_constructed_without_provenance() -> None:
    from src.analysis.derive import CheckKind, DerivationError, DerivedCheck

    with pytest.raises(DerivationError, match="no provenance"):
        DerivedCheck(
            operation_id="listOrders", quantity="result",
            check_kind=CheckKind.SHAPE,
            expression="isinstance(result, list)", provenance=None)


def test_a_schema_cannot_require_inner_fields_of_a_field_it_permits_omitting()  -> None:
    """The two halves of the requirement have to be declared together.

    `required_provenance` is checked against `payload["provenance"]`, so a schema
    that declared the inner fields without listing `provenance` in `required`
    would be satisfied by a payload that omits provenance entirely — the inner
    check reading a field the outer check does not demand. That is the 1.0.0
    defect reconstructed one level down.
    """
    with pytest.raises(schemas.SchemaError, match="does not list 'provenance'"):
        schemas.ArtifactSchema(
            kind="test_double", version="1.0.0", requirement="none",
            required=("schema_version",), volatile=(), source_derived=False,
            description="a schema that requires the inside of an optional field",
            required_provenance=schemas.FR_026_PROVENANCE_FIELDS)


def test_both_superseded_versions_have_a_registered_migration() -> None:
    """FR-054's rollback demand, asserted here as well as in the schema-version
    gate, because that gate returns early for a kind whose baseline it holds at
    the current version and this one does not depend on the baseline at all."""
    for kind in DERIVED_KINDS:
        assert (kind, "1.0.0") in migrations._BY_SOURCE, kind
