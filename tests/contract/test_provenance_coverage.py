"""T133 — provenance coverage over the population the analyzer actually produces.

**Criterion**: SC-007 — *"**100%** of derived contracts and derived checks carry
provenance and a validation status, and **zero** are presented as validated
without an artifact their own derivation did not produce."*

## THE TWO FIGURES, AND WHY ONLY ONE OF THEM IS FREE

SC-007 states a hundred and a zero, and they have opposite failure modes.

**The 100%** is a coverage claim, and coverage is free over an empty population.
`Provenance` is a required field on both `DerivedContract` and `DerivedCheck`,
so *"every contract carries provenance"* is a statement about the dataclass and
not about the analyzer. What makes it a measurement is running the real
derivation over a committed fixture and counting what comes out —
`POPULATION_CONTRACTS` and `POPULATION_CHECKS` are pinned so an analyzer that
silently stops emitting cannot report a hundred per cent of nothing.

**The zero** is worse, and it is measured rather than asserted here.

## THE ZERO IS VACUOUS OVER THIS TREE, AND THAT IS RECORDED RATHER THAN PASSED

Running `validate_contract` over every pairing of the three derived contracts
against all five operations of the only published specification in this
repository yields **fifteen `ProvisionalContract`s and no promotions**, every
one for `specification_silent`. `test_no_contract_in_this_tree_promotes` is that
measurement, not a prediction.

So there is no contract in the real population that is *presented as validated*
at all, and *"zero are presented as validated without an artifact"* is true
because the numerator and the population are both empty. A test asserting only
that would be this repository's most common defect — a clean bit over a
measurement that was absent.

`NO_VALIDATED_POPULATION` records the absence as a decision, on
`costs.UNPRICED`'s treatment, and four positive arms make the zero
discriminating: the same `presented_as_validated_without_an_artifact` predicate
is shown each way a record can commit that defect and must catch every one, and
is shown one legitimate promotion and must clear it.

| Arm | Shown | Expected |
|---|---|---|
| coverage | 3 contracts, 6 checks from the committed fixture | all carry provenance and a status |
| the zero | the same population | none presented as validated |
| **positive** | validated with no artifact / with its own source file / with an empty citation / a payload asserting it | **caught, four ways** |
| **positive** | one promotion against an independent artifact | **cleared** |

The last row is what separates a predicate that discriminates from one that
refuses everything: a detector that called every record a defect would satisfy
the row above it.

## WHAT THIS FILE DOES NOT DUPLICATE

`Provenance.__post_init__` and `ValidatedContract.__post_init__` already refuse
most of this at construction, and `tests/unit/` covers those refusals on their
own terms. This file does not re-test the constructors. It measures a
**population**, which is the thing a constructor cannot do: a type that makes a
bad record unconstructible says nothing about whether any record was
constructed.

Run:
    python -m pytest tests/contract/test_provenance_coverage.py -v
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

import pytest

from src.analysis.derive import DerivedCheck, DerivedContract, derive_module
from src.analysis.provenance import (
    Provenance,
    ProvenanceError,
    ValidationStatus,
    hash_source_construct,
)
from src.analysis.served_operations import ServedOperationSet
from src.analysis.validate import (
    ProvisionalContract,
    ProvisionalReason,
    ValidatedContract,
    ValidationError,
)
from src.contracts.migrations import migrate

REPO = Path(__file__).resolve().parents[2]
FIXTURE = REPO / "tests" / "fixtures" / "analyzer" / "inventory-service" / "service.py"
OPAQUE = REPO / "tests" / "fixtures" / "analyzer" / "no-derivable-checks" / "opaque.py"
SERVED = REPO / "tests" / "fixtures" / "reference-app" / "served_operations.json"

#: The census, pinned. Read a transition out of this arm's own failure message
#: rather than recomputing it: a hundred per cent over a population that
#: silently shrank is the failure this pin exists to make visible.
POPULATION_CONTRACTS = 3
POPULATION_CHECKS = 6

#: Why SC-007's zero is not evidence on its own, recorded as a decision.
#:
#: `costs.UNPRICED`'s treatment — an absence a reader would otherwise take for
#: an oversight and fill in.
NO_VALIDATED_POPULATION = (
    "No derived contract in this repository is presented as validated, so "
    "SC-007's second clause has an empty numerator AND an empty population. "
    "Measured, not assumed: `test_no_contract_in_this_tree_promotes` pairs "
    "each of the three derived contracts against each of the five operations "
    "the reference app publishes and gets fifteen provisional results, every "
    "one `specification_silent` — the published specification declares no "
    "parameters, so `validate_contract` reads it as silent and promotes "
    "nothing. The zero is therefore free, and it is made discriminating by "
    "the positive arms rather than by being reported on its own."
)


def _population() -> tuple[DerivedContract, ...]:
    return derive_module(FIXTURE, relative_to=FIXTURE.parent)


def _checks(contracts: tuple[DerivedContract, ...]) -> tuple[DerivedCheck, ...]:
    return tuple(check for contract in contracts for check in contract.checks)


CONTRACTS = _population()
CHECKS = _checks(CONTRACTS)


# ---------------------------------------------------------------------------
# THE PREDICATE. One function, shown both a clean population and four defects.


def presented_as_validated_without_an_artifact(
    provenance: Provenance,
) -> tuple[str, ...]:
    """SC-007's second clause as a check over one record. No construction.

    Deliberately reads a **record** rather than calling a constructor: the
    constructors refuse these already, and a predicate that delegated to them
    would be testing that the refusal exists rather than that the population is
    clean. This is the reading a reviewer would do by eye, executed.
    """
    if provenance.validation_status is not ValidationStatus.VALIDATED:
        return ()
    faults: list[str] = []
    if not (provenance.validated_against or "").strip():
        faults.append(
            "status is `validated` and no artifact is cited, which is the "
            "presented-as-validated case Principle I forbids"
        )
    elif provenance.validated_against == provenance.source_file:
        faults.append(
            f"validated against {provenance.validated_against!r}, which is the "
            "source file the derivation read. An artifact its own derivation "
            "produced corroborates nothing"
        )
    return tuple(faults)


def carries_provenance_and_a_status(record: Any) -> tuple[str, ...]:
    """The 100% clause, as a check that can fail. Also shown a stripped record."""
    provenance = getattr(record, "provenance", None)
    if not isinstance(provenance, Provenance):
        return (f"carries no Provenance (got {provenance!r})",)
    faults = [
        f"{field} is empty"
        for field in ("derivation_rule", "source_symbol", "source_file",
                      "content_hash", "analyzer_version")
        if not str(getattr(provenance, field, "")).strip()
    ]
    if not isinstance(provenance.validation_status, ValidationStatus):
        faults.append(
            f"validation_status is {provenance.validation_status!r}, which is "
            "not one of FR-026's two"
        )
    return tuple(faults)


# ---------------------------------------------------------------------------
# THE POPULATION IS REAL, AND IT IS NOT EMPTY.


def test_the_population_is_the_analyzers_own_output_and_is_populated() -> None:
    """A hundred per cent of nothing is a hundred per cent.

    Pinned rather than derived. An analyzer that stopped emitting checks would
    otherwise keep every coverage arm below green while covering nothing.
    """
    assert len(CONTRACTS) == POPULATION_CONTRACTS, (
        f"the derived population moved to {len(CONTRACTS)} contracts: "
        f"{[c.operation_id for c in CONTRACTS]}"
    )
    assert len(CHECKS) == POPULATION_CHECKS, (
        f"the derived population moved to {len(CHECKS)} checks"
    )
    assert not derive_module(OPAQUE, relative_to=OPAQUE.parent), (
        "the negative fixture now yields contracts, so the analyzer emits "
        "something for a module no rule fires on"
    )


def test_every_derived_contract_carries_provenance_and_a_validation_status() -> None:
    """SC-007's first clause over the contracts. 100% of a measured population."""
    uncovered = {
        contract.operation_id: faults
        for contract in CONTRACTS
        if (faults := carries_provenance_and_a_status(contract))
    }
    assert uncovered == {}, uncovered
    assert len(CONTRACTS) == POPULATION_CONTRACTS


def test_every_derived_check_carries_provenance_and_a_validation_status() -> None:
    """SC-007's first clause over the checks, which are the finer population."""
    uncovered = {
        f"{check.operation_id}:{check.quantity}": faults
        for check in CHECKS
        if (faults := carries_provenance_and_a_status(check))
    }
    assert uncovered == {}, uncovered
    assert len(CHECKS) == POPULATION_CHECKS


def test_the_coverage_predicate_catches_a_record_that_carries_nothing() -> None:
    """THE POSITIVE ARM FOR THE 100%.

    A coverage check that returns no faults on everything reports full
    coverage. It is shown a record with no provenance at all and must say so.
    """

    class Stripped:
        provenance = None

    assert carries_provenance_and_a_status(Stripped()), (
        "the coverage predicate passed a record carrying no provenance, so "
        "its hundred per cent above is a property of the predicate"
    )
    assert carries_provenance_and_a_status(object())


# ---------------------------------------------------------------------------
# SC-007's ZERO — measured first, then made discriminating.


def test_no_derived_record_in_the_population_is_presented_as_validated() -> None:
    """SC-007's second clause. Read only with the arm below and the positives."""
    offenders = {
        record_id: faults
        for record_id, provenance in _provenances()
        if (faults := presented_as_validated_without_an_artifact(provenance))
    }
    assert offenders == {}, offenders


def _provenances() -> list[tuple[str, Provenance]]:
    records: list[tuple[str, Provenance]] = [
        (contract.operation_id, contract.provenance) for contract in CONTRACTS
    ]
    records += [
        (f"{check.operation_id}:{check.quantity}", check.provenance)
        for check in CHECKS
    ]
    return records


def test_no_contract_in_this_tree_promotes() -> None:
    """WHY THE ZERO ABOVE IS FREE, stated as a measurement rather than a caveat.

    Every pairing of every derived contract against every published operation.
    If this ever yields a promotion, the zero above stops being vacuous and
    `NO_VALIDATED_POPULATION` has to be rewritten — which is the point of
    asserting it rather than writing it down in prose.
    """
    specification = ServedOperationSet.from_document(
        migrate("served_operation_set", json.loads(SERVED.read_text()))
    )
    from src.analysis.validate import validate_contract

    outcomes = [
        validate_contract(
            contract,
            specification=specification,
            served_operation_id=operation_id,
            deployment_id=specification.deployment_id,
        )
        for contract in CONTRACTS
        for operation_id in specification.operation_ids()
    ]

    assert outcomes, "no pairing was attempted, so this measures nothing"
    assert len(outcomes) == POPULATION_CONTRACTS * len(specification.operation_ids())
    promoted = [o for o in outcomes if isinstance(o, ValidatedContract)]
    assert not promoted, (
        f"{len(promoted)} contract(s) now promote against the published "
        "specification. SC-007's zero is no longer vacuous over this tree — "
        "rewrite NO_VALIDATED_POPULATION and score the second clause over the "
        "promoted population instead of over the positive arms alone."
    )
    assert {o.reason for o in outcomes} == {ProvisionalReason.SPECIFICATION_SILENT}, (
        "the provisional reasons moved; NO_VALIDATED_POPULATION names "
        "`specification_silent` as the one this tree produces"
    )


def test_the_recorded_absence_says_what_is_missing_and_why() -> None:
    """The `UNPRICED` discipline: an absence a reader can act on."""
    assert "specification_silent" in NO_VALIDATED_POPULATION
    assert "Measured, not assumed" in NO_VALIDATED_POPULATION


# ---------------------------------------------------------------------------
# THE POSITIVE ARMS. Four defects caught, one legitimate promotion cleared.


def _provenance(**overrides: Any) -> Provenance:
    fields: dict[str, Any] = {
        "derivation_rule": "aggregate_binding",
        "source_symbol": "stock_report",
        "source_file": "inventory/service.py",
        "content_hash": hash_source_construct("def stock_report(): ..."),
    }
    fields.update(overrides)
    return Provenance(**fields)


def test_the_predicate_catches_a_status_with_no_artifact_behind_it() -> None:
    """Defect one: validated, citing nothing.

    Built by bypassing `__post_init__` with `object.__setattr__`, because the
    constructor refuses it. That is the right way round — the predicate must
    catch a record the constructor would never have made, since the population
    it screens is read back from documents as well as built in process.
    """
    record = _provenance()
    object.__setattr__(record, "validation_status", ValidationStatus.VALIDATED)
    object.__setattr__(record, "validated_against", None)

    faults = presented_as_validated_without_an_artifact(record)
    assert faults, "a record claiming validation with no artifact was cleared"
    assert "Principle I" in faults[0]


def test_the_predicate_catches_a_record_validated_against_its_own_source() -> None:
    """Defect two, and the one SC-007 words most carefully.

    *"an artifact their own derivation did not produce"* — a citation naming
    the source file is a citation of the derivation's own input.
    """
    record = _provenance()
    object.__setattr__(record, "validation_status", ValidationStatus.VALIDATED)
    object.__setattr__(record, "validated_against", record.source_file)

    faults = presented_as_validated_without_an_artifact(record)
    assert faults, "a self-validating record was cleared"
    assert "source file" in faults[0]


def test_the_constructor_refuses_both_defects_as_well() -> None:
    """The type is the first line and the predicate is the second.

    Asserted so that a later relaxation of `Provenance` shows up here rather
    than only in the population, which is currently too small to catch it.
    """
    with pytest.raises(ProvenanceError, match="Principle I"):
        _provenance(validation_status=ValidationStatus.VALIDATED)
    with pytest.raises(ProvenanceError, match="derived from"):
        _provenance(
            validation_status=ValidationStatus.VALIDATED,
            validated_against="inventory/service.py",
        )


def test_a_promotion_that_cites_nothing_cannot_be_built() -> None:
    """Defect three, at the contract layer rather than the record layer."""
    with pytest.raises(ValidationError, match="names the artifact"):
        ValidatedContract(
            contract=CONTRACTS[0],
            validated_against="   ",
            agreed_on=("lots",),
            deployment_id="d-reference-app",
        )


def test_a_payload_asserting_validation_without_an_artifact_is_refused() -> None:
    """Defect four: the document path, which is how a record arrives from disk.

    The population this predicate screens is not only built in process. A
    payload is the shape a promotion takes when it crosses a boundary, and a
    boundary that accepted this would put an uncatchable record into a
    population every arm above reports as clean.
    """
    payload: Mapping[str, Any] = {
        **_provenance().to_payload(),
        "validation_status": ValidationStatus.VALIDATED.value,
        "validated_against": None,
    }
    with pytest.raises(ProvenanceError):
        Provenance.from_payload(payload)


def test_a_legitimate_promotion_is_cleared_by_the_same_predicate() -> None:
    """THE ARM THAT STOPS THE PREDICATE FROM BEING A REFUSAL OF EVERYTHING.

    Three defects caught is satisfied by a predicate that reports a fault on
    every record it is shown, and such a predicate would also report the real
    population as clean only because that population is provisional. So it is
    shown one promotion against an artifact the derivation did not produce and
    must clear it.
    """
    promoted = ValidatedContract(
        contract=CONTRACTS[0],
        validated_against="https://reference-app.invalid/openapi.json",
        agreed_on=("lots",),
        deployment_id="d-reference-app",
    )
    provenance = promoted.provenance()

    assert provenance.validation_status is ValidationStatus.VALIDATED
    assert provenance.validated_against != provenance.source_file
    assert not presented_as_validated_without_an_artifact(provenance), (
        "the predicate flagged a promotion that cites an independent "
        "artifact, so it is refusing everything rather than discriminating"
    )
    assert not carries_provenance_and_a_status(promoted.contract)


def test_a_provisional_contract_still_carries_provenance_and_a_status() -> None:
    """The 100% covers the unpromoted half too, which is all of it today."""
    provisional = ProvisionalContract(
        contract=CONTRACTS[0],
        reason=ProvisionalReason.SPECIFICATION_SILENT,
        detail="the published specification declares no parameters",
    )
    provenance = provisional.provenance()
    assert provenance.validation_status is ValidationStatus.PROVISIONAL
    assert provenance.validated_against is None
    assert not presented_as_validated_without_an_artifact(provenance)
    assert not carries_provenance_and_a_status(provisional.contract)
