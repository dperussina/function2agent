"""T122 — promotion to `validated` against the target's **published specification**.

**Requirement**: FR-026 and constitution Principle I as amended at v1.1.0 —
a derived check *"MUST be validated against an artifact its own derivation did
not produce; where no independent artifact exists it MUST be marked provisional
and MUST NOT be presented as validated."*

## The defect these arms exist to prevent

**Absence read as agreement.** The cheap implementation of this feature promotes
a contract whenever nothing contradicts it, and that implementation passes every
arm a suite writes about the agreeing case. So the arms below are weighted the
other way: most of them supply a specification that is *absent*, *silent on the
operation*, or *silent on the field*, and assert `PROVISIONAL` with a reason that
names which of the three it was. A single `is_validated` boolean cannot express
that difference, which is why `ProvisionalReason` is a closed enum and why these
arms assert the member and not merely the falsity.

This is the same pair `tests/unit/test_derived_record.py` holds apart —
**absent** against **provisional** — one level up: there, no record against a
record claiming nothing; here, no corroborating artifact against an artifact that
corroborated nothing.

## What `validated` is asserted to mean, and what it is not

`validated` is a claim about the **derivation**: an artifact the derivation did
not produce agreed with it. It is **not** a claim that any response is correct,
and no arm here asserts that it is. Conformance to a declared shape is explicitly
not verification (T124), so promotion is a *necessary* condition for a later
`Verified` and never a sufficient one — `tests/invariants/test_provisional_never_verified.py`
holds the other half.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.analysis.derive import derive_module
from src.analysis.provenance import ValidationStatus
from src.analysis.served_operations import ServedOperation, ServedOperationSet
from src.analysis.validate import (
    ProvisionalContract,
    ProvisionalReason,
    ValidatedContract,
    validate_contract,
)
from src.contracts.schemas import DERIVED_CONTRACT

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "analyzer"


def _contract(name: str = "reserve"):
    """One derived contract off the committed fixture, by symbol name."""
    contracts = derive_module(
        FIXTURES / "inventory-service" / "service.py",
        relative_to=FIXTURES / "inventory-service",
    )
    for contract in contracts:
        if contract.operation_id.endswith(f":{name}"):
            return contract
    raise AssertionError(
        f"the inventory-service fixture derived no contract for {name!r}; "
        f"it derived {[c.operation_id for c in contracts]}. This test reads the "
        "committed fixture rather than a hand-built contract, so a fixture "
        "change surfaces here rather than being absorbed."
    )


def _specification(
    *,
    operation_id: str,
    parameters: list | None,
    deployment_id: str = "dep-1",
) -> ServedOperationSet:
    """A published specification, as the served-operation set FR-002 produces.

    Built as a test input and labelled as one. It is **not** a fixture file: a
    specification hand-written from the same `service.py` the derivation read
    would be an artifact its own derivation did produce, which is the exact
    thing Principle I forbids relying on. Here it is a constructed input to the
    comparison operator, and no arm treats it as evidence about the fixture.
    """
    entry: dict = {
        "operation_id": operation_id,
        "method": "POST",
        "path_template": "/reservations",
    }
    if parameters is not None:
        entry["parameters"] = parameters
    return ServedOperationSet(
        deployment_id=deployment_id,
        operations=(ServedOperation.from_entry(entry, index=0),),
        captured_at="2026-08-12T00:00:00Z",
        source_url="https://target.example/openapi.json",
    )


# ---------------------------------------------------------------------------
# Absence. Four separate absences, and none of them may promote.


def test_no_specification_at_all_yields_provisional_naming_the_absence():
    contract = _contract()
    outcome = validate_contract(contract, specification=None, served_operation_id=None)

    assert isinstance(outcome, ProvisionalContract)
    assert outcome.reason is ProvisionalReason.NO_SPECIFICATION


def test_absence_of_a_specification_is_not_the_same_reason_as_disagreement():
    """The pair this module exists to keep apart.

    A single boolean makes these equal, and the safe-looking implementation —
    *promote unless something contradicts* — makes the first one promote.
    """
    contract = _contract()
    absent = validate_contract(contract, specification=None, served_operation_id=None)
    disagreeing = validate_contract(
        contract,
        specification=_specification(
            operation_id="reserve", parameters=["wildly", "different"]
        ),
        served_operation_id="reserve",
    )

    assert absent.reason is ProvisionalReason.NO_SPECIFICATION
    assert disagreeing.reason is ProvisionalReason.SPECIFICATION_DISAGREES
    assert absent.reason is not disagreeing.reason


def test_an_operation_the_specification_does_not_serve_is_provisional():
    contract = _contract()
    outcome = validate_contract(
        contract,
        specification=_specification(operation_id="reserve", parameters=["sku"]),
        served_operation_id="an-operation-this-specification-does-not-carry",
    )

    assert isinstance(outcome, ProvisionalContract)
    assert outcome.reason is ProvisionalReason.OPERATION_NOT_SERVED


def test_an_entry_that_declares_no_parameters_is_provisional_not_agreeing():
    """Absence one level down, and the same rule applies to it.

    A specification entry that declares no parameters contradicts nothing. The
    cheap reading is that nothing contradicted the derivation, so it agrees;
    the correct reading is that there was nothing to agree with.
    """
    contract = _contract()
    outcome = validate_contract(
        contract,
        specification=_specification(operation_id="reserve", parameters=None),
        served_operation_id="reserve",
    )

    assert isinstance(outcome, ProvisionalContract)
    assert outcome.reason is ProvisionalReason.SPECIFICATION_SILENT


def test_an_entry_declaring_an_empty_parameter_list_is_not_silent():
    """An explicit empty list is a claim: this operation takes no parameters.

    Distinguished from the silent case because it is a different fact, and
    because a derivation that read three parameters genuinely disagrees with it.
    """
    contract = _contract()
    outcome = validate_contract(
        contract,
        specification=_specification(operation_id="reserve", parameters=[]),
        served_operation_id="reserve",
    )

    assert isinstance(outcome, ProvisionalContract)
    assert outcome.reason is ProvisionalReason.SPECIFICATION_DISAGREES


# ---------------------------------------------------------------------------
# Agreement, which is the only path that promotes.


def test_a_specification_that_agrees_promotes_to_validated():
    contract = _contract()
    outcome = validate_contract(
        contract,
        specification=_specification(
            operation_id="reserve", parameters=list(contract.reads)
        ),
        served_operation_id="reserve",
    )

    assert isinstance(outcome, ValidatedContract)
    assert outcome.provenance().validation_status is ValidationStatus.VALIDATED


def test_a_parameter_declared_as_an_object_with_a_name_is_read():
    """OpenAPI's own shape, not just a list of bare strings."""
    contract = _contract()
    outcome = validate_contract(
        contract,
        specification=_specification(
            operation_id="reserve",
            parameters=[{"name": name, "in": "body"} for name in contract.reads],
        ),
        served_operation_id="reserve",
    )

    assert isinstance(outcome, ValidatedContract)


def test_a_promoted_contract_names_the_artifact_that_validated_it():
    contract = _contract()
    outcome = validate_contract(
        contract,
        specification=_specification(
            operation_id="reserve", parameters=list(contract.reads)
        ),
        served_operation_id="reserve",
    )

    provenance = outcome.provenance()
    assert provenance.validated_against
    assert provenance.validated_against != provenance.source_file


def test_promotion_cannot_name_the_source_file_as_its_own_validator():
    """Principle I's independence clause, held by the constructor upstream.

    Asserted here rather than assumed, because this module is the one that
    chooses what `validated_against` says, and choosing the source file would
    make every derivation self-validating.
    """
    contract = _contract()
    outcome = validate_contract(
        contract,
        specification=_specification(
            operation_id="reserve", parameters=list(contract.reads)
        ),
        served_operation_id="reserve",
    )

    assert outcome.validated_against != contract.provenance.source_file


def test_a_specification_that_disagrees_yields_provisional_with_the_difference_named():
    """Disagreement is the FR-057 signal, so it has to say what differed.

    *"A source reference pointing at the wrong application surfaces as derived
    contracts that fail to validate."* A reason member alone does not let an
    operator act on that; the two set differences do.
    """
    contract = _contract()
    outcome = validate_contract(
        contract,
        specification=_specification(
            operation_id="reserve", parameters=["sku", "warehouse"]
        ),
        served_operation_id="reserve",
    )

    assert isinstance(outcome, ProvisionalContract)
    assert outcome.reason is ProvisionalReason.SPECIFICATION_DISAGREES
    # What the derivation read and what the specification declares, both named.
    assert "lots" in outcome.detail
    assert "sku" in outcome.detail
    assert "warehouse" in outcome.detail


def test_promotion_does_not_promote_the_contracts_checks():
    """A specification agreeing about parameters does not validate a recomputation.

    Held as an arm because the tempting "fix" is to promote everything under a
    validated contract, and that would be the derived-but-wrong verifier
    arriving through the mechanism built to catch it. Nothing in a published
    specification declares an aggregate relationship, so no check-level
    independent artifact exists in v1.
    """
    contract = _contract()
    outcome = validate_contract(
        contract,
        specification=_specification(
            operation_id="reserve", parameters=list(contract.reads)
        ),
        served_operation_id="reserve",
    )

    assert isinstance(outcome, ValidatedContract)
    assert contract.checks, "the fixture contract carries no checks"
    for check in outcome.contract.checks:
        assert check.provenance.validation_status is ValidationStatus.PROVISIONAL
        assert check.provenance.validated_against is None


def test_a_parameter_declaration_with_no_readable_name_is_provisional():
    """Unreadable is a third thing: not silence, not agreement."""
    contract = _contract()
    outcome = validate_contract(
        contract,
        specification=_specification(operation_id="reserve", parameters=[{"in": "body"}]),
        served_operation_id="reserve",
    )

    assert isinstance(outcome, ProvisionalContract)
    assert outcome.reason is ProvisionalReason.SPECIFICATION_UNREADABLE


def test_a_specification_citing_no_source_cannot_validate_anything():
    """A promotion has to name the artifact, so an uncited specification cannot."""
    contract = _contract()
    specification = _specification(
        operation_id="reserve", parameters=list(contract.reads)
    )
    uncited = ServedOperationSet(
        deployment_id=specification.deployment_id,
        operations=specification.operations,
        captured_at=specification.captured_at,
        source_url="",
    )

    outcome = validate_contract(
        contract, specification=uncited, served_operation_id="reserve"
    )

    assert isinstance(outcome, ProvisionalContract)
    assert outcome.reason is ProvisionalReason.SPECIFICATION_UNREADABLE


def test_the_order_of_declared_parameters_does_not_decide_agreement():
    """Named parameters have no meaningful order in a published specification."""
    contract = _contract()
    outcome = validate_contract(
        contract,
        specification=_specification(
            operation_id="reserve", parameters=list(reversed(contract.reads))
        ),
        served_operation_id="reserve",
    )

    assert isinstance(outcome, ValidatedContract)


# ---------------------------------------------------------------------------
# The schema ruling, asserted rather than asserted about in prose.


def test_a_promoted_contract_still_validates_at_the_registry_version():
    """No schema bump. `validation_status` was already required at 1.1.0.

    T121 put `validation_status` inside `provenance` and
    `FR_026_PROVENANCE_FIELDS` already requires it, so promotion changes a
    field's **value** and adds no field. This arm is the ruling's evidence: a
    promoted document validates against the registry at the version the
    registry already holds.
    """
    contract = _contract()
    outcome = validate_contract(
        contract,
        specification=_specification(
            operation_id="reserve", parameters=list(contract.reads)
        ),
        served_operation_id="reserve",
    )

    document = outcome.to_document(deployment_id="dep-1")
    assert document["schema_version"] == DERIVED_CONTRACT.version
    DERIVED_CONTRACT.validate(document)
    assert document["provenance"]["validation_status"] == "validated"


def test_a_provisional_document_and_a_validated_one_differ_in_the_stored_field():
    """The distinction survives storage, which is where a reader meets it."""
    contract = _contract()
    provisional = validate_contract(
        contract, specification=None, served_operation_id=None
    ).to_document(deployment_id="dep-1")
    validated = validate_contract(
        contract,
        specification=_specification(
            operation_id="reserve", parameters=list(contract.reads)
        ),
        served_operation_id="reserve",
    ).to_document(deployment_id="dep-1")

    assert provisional["provenance"]["validation_status"] == "provisional"
    assert validated["provenance"]["validation_status"] == "validated"
    assert provisional["provenance"]["validated_against"] is None
    DERIVED_CONTRACT.validate(provisional)


# ---------------------------------------------------------------------------
# The two committed fixtures, and which status each one actually yields.


def test_the_inventory_service_fixture_is_provisional_for_every_contract():
    """No specification is reachable for a fixture, so nothing promotes.

    The fixture is source on disk. There is no running deployment, therefore no
    published specification (FR-002 fetches it from one), therefore no
    independent artifact — and `provisional` for all three contracts is the
    correct and safe outcome rather than a gap in this test.
    """
    contracts = derive_module(
        FIXTURES / "inventory-service" / "service.py",
        relative_to=FIXTURES / "inventory-service",
    )
    assert contracts, "the fixture derived nothing; the analyzer or the fixture moved"

    for contract in contracts:
        outcome = validate_contract(
            contract, specification=None, served_operation_id=None
        )
        assert isinstance(outcome, ProvisionalContract)
        assert outcome.reason is ProvisionalReason.NO_SPECIFICATION


def test_the_no_derivable_checks_fixture_yields_no_contract_and_so_no_status():
    """A fixture that derives nothing has no validation status to hold.

    Stated as its own arm because *"which status does this fixture yield"* has
    no answer for this one, and an answer of `provisional` would be wrong in a
    way that matters: it would mean a contract existed.
    """
    contracts = derive_module(
        FIXTURES / "no-derivable-checks" / "opaque.py",
        relative_to=FIXTURES / "no-derivable-checks",
    )

    assert contracts == ()


# ---------------------------------------------------------------------------
# The comparison is against a fetched artifact, and this module may not fetch.


def test_this_module_reads_no_network_and_no_running_deployment():
    """FR-002: source analysis stays reproducible from the codebase alone.

    The specification arrives as an argument. A module under `src/analysis/`
    that fetched one would merge the two stages OD-06 separates, and the
    convention is the thing that erodes — so it is scanned rather than trusted.
    """
    import src.analysis.validate as module

    text = Path(module.__file__).read_text()
    for forbidden in ("requests", "urllib", "httpx", "socket", "http.client"):
        assert f"import {forbidden}" not in text, (
            f"src/analysis/validate.py names `import {forbidden}`. FR-002 "
            "requires source analysis to be reproducible from the codebase "
            "alone with no network input; the published specification is "
            "fetched by the admission stage above this one and passed in."
        )


def test_a_specification_for_another_deployment_is_not_silently_accepted():
    """The set records the deployment it describes (FR-002).

    A caller that hands over a specification captured from a different
    deployment is naming an artifact that describes something else, and the
    promotion would cite it. Refused rather than compared.
    """
    contract = _contract()
    specification = _specification(
        operation_id="reserve",
        parameters=list(_contract().reads),
        deployment_id="dep-OTHER",
    )

    with pytest.raises(ValueError, match="dep-OTHER"):
        validate_contract(
            contract,
            specification=specification,
            served_operation_id="reserve",
            deployment_id="dep-1",
        )
