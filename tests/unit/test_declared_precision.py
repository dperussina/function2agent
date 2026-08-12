"""T212 — FR-024's caller-declared precision rung, and what it may never do.

**The requirement, quoted rather than paraphrased.** FR-024 property 5:

> A precision declared in the caller's own request is admissible only where no
> artifact source supplies any precision for that quantity at all — that is,
> only where the ladder would otherwise refuse. […] Where any artifact source
> supplies a precision, the declaration MUST be ignored — whether it is
> tighter, equal or looser — and the ladder MUST proceed exactly as if the
> declaration were absent. […] A caller-declared precision may never be the
> reason a quantity is checked less strictly than an artifact source permits.
> […] An ignored declaration MUST be disclosed on the result, not silently
> dropped.

Property 6:

> A verification whose precision came from the caller's request MUST be marked
> provisional on its own provenance.

## Why this file exists rather than more arms in `test_verify.py`

`test_verify.py` is the home of T124's and T125's arms and was under concurrent
edit when this rung was built. Splitting is the coordination, not a judgement
about where the arms belong.

## What is real in each arm

The same fixture discipline `test_verify.py` states for itself applies, and for
the same reason: no committed artifact supplies a real derivation and a real
deployment for one quantity. **Every float arm here uses a supplied collection
and says so** — it is not a deployment. What is real is the ladder: the checks
are constructed the way `derive_module` constructs them, and the values that
reach the comparison are produced by the verifier's own recomputation rather
than written into the assertion.

**The float pair is the one OD-23 measured**, `3.23` against `3.201754` — a
relative error of 0.882%, the only sub-one-percent catch in the census of 61 —
so the arms below score the rung against the instance the decision was taken
on rather than against a number chosen here.
"""

from __future__ import annotations

from typing import Any, Sequence

import pytest

from src.analysis.derive import CheckKind, DerivedCheck, DerivedContract, Recomputation
from src.analysis.provenance import Provenance, ValidationStatus, hash_source_construct
from src.analysis.validate import ProvisionalContract, ProvisionalReason, ValidatedContract, Verified
from src.contracts.result import VerificationOutcome
from src.runtime.verify import (
    ConsultedSource,
    DeclarationDisposition,
    DeclaredPrecision,
    Disagreement,
    PathUnavailable,
    PrecisionProvenance,
    ProvisionallyVerified,
    QuantityVerification,
    Refusal,
    RefusalReason,
    ReportedResult,
    VerificationError,
    verify_declared_quantity,
    verify_quantity,
)

#: OD-23's measured pair, named once. `3.23` was submitted against a recomputed
#: mean of `3.201754`; the request asked for two decimal places.
SUBMITTED = 3.23
TRUE_VALUE = 3.201754
DECLARED_PLACES = 2


# ---------------------------------------------------------------------------
# Fixtures. Constructed here rather than imported from `test_verify.py`, which
# was under concurrent edit — see the module docstring.


class SuppliedCollection:
    """A collection supplied by the test. **Not a deployment**, and labelled.

    It exists so that a check can be executed at all: nothing in this tree
    serves a collection whose elements carry a float, and the rung under test
    is only ever reached by a float.
    """

    def __init__(self, name: str, rows: Sequence[Any], *, source: str) -> None:
        self._name = name
        self._rows = list(rows)
        self._source = source

    def source(self) -> str:
        return self._source

    def collection(self, name: str) -> Sequence[Any]:
        if name != self._name:
            raise PathUnavailable(
                f"this path serves {self._name!r} and was asked for {name!r}"
            )
        return list(self._rows)


def _provenance(rule: str, symbol: str) -> Provenance:
    return Provenance(
        derivation_rule=rule,
        source_symbol=symbol,
        source_file="app.py",
        content_hash=hash_source_construct(symbol),
        validation_status=ValidationStatus.VALIDATED,
        validated_against="served_operations.json",
    )


def _check(
    *,
    quantity: str,
    operator: str,
    over: str,
    element_field: str | None = None,
) -> DerivedCheck:
    return DerivedCheck(
        operation_id="app:list_lots",
        quantity=quantity,
        check_kind=CheckKind.RECOMPUTATION,
        expression=f"{quantity} == {operator}({over})",
        recomputation=Recomputation(
            operator=operator,
            over=over,
            element_field=element_field,
            reads=(over,),
        ),
        precision_source=f"aggregate_over:{operator}",
        provenance=_provenance("aggregate_binding", "list_lots"),
    )


def _validated(check: DerivedCheck) -> ValidatedContract:
    return ValidatedContract(
        contract=DerivedContract(
            operation_id=check.operation_id,
            reads=(),
            writes=(),
            preconditions=(),
            postconditions=(check.expression,),
            failure_taxonomy=(),
            provenance=_provenance("aggregate_binding", "list_lots"),
            checks=(check,),
        ),
        validated_against="file://tests/fixtures/reference-app/served_operations.json",
        agreed_on=("part_id",),
        deployment_id="d-reference-app",
    )


def _float_case(reported: float) -> dict[str, Any]:
    """The float quantity: an aggregate whose value no artifact states a precision for."""
    check = _check(
        quantity="unit_cost_high", operator="max", over="lots", element_field="unit_cost"
    )
    return {
        "contract": _validated(check),
        "check": check,
        "result": ReportedResult(source="agent answer", payload={"unit_cost_high": reported}),
        "path": SuppliedCollection(
            "lots",
            [{"unit_cost": TRUE_VALUE}],
            source="supplied collection (not a deployment)",
        ),
    }


def _integer_case(reported: int, rows: int) -> dict[str, Any]:
    """The integer quantity: an aggregate that IS exact, so an artifact rung applies."""
    check = _check(quantity="lot_count", operator="count", over="lots")
    return {
        "contract": _validated(check),
        "check": check,
        "result": ReportedResult(source="agent answer", payload={"lot_count": reported}),
        "path": SuppliedCollection(
            "lots",
            [{"unit_cost": 1} for _ in range(rows)],
            source="supplied collection (not a deployment)",
        ),
    }


def _declaration(places: int = DECLARED_PLACES) -> DeclaredPrecision:
    return DeclaredPrecision(
        decimal_places=places,
        declared_in=f"caller request: report the mean to {places} decimal places",
    )


# ---------------------------------------------------------------------------
# Property 5, first sub-bullet — the admissibility test runs FIRST.


def test_the_ladder_refuses_the_float_without_a_declaration_which_is_what_the_rung_displaces() -> None:
    """The negative control for every arm below, and it runs first on purpose.

    Without it, an arm asserting the rung produced a comparison proves nothing:
    a rung that changed nothing would satisfy it if the ladder had been going
    to compare anyway. FR-024 property 5 calls this *"the only circumstance in
    which a declaration converts what would otherwise be a refusal into a
    checked quantity"*, so the refusal is the thing being converted and it has
    to be shown to exist.
    """
    report = verify_quantity(**_float_case(SUBMITTED))

    assert isinstance(report, Refusal), report
    assert report.reason is RefusalReason.PRECISION_NOT_STATED, report.reason
    assert report.outcome() is VerificationOutcome.NOT_VERIFIABLE


def test_a_declaration_is_admitted_only_where_no_artifact_source_supplies_a_precision() -> None:
    """Property 5's admissibility test, in the direction that admits."""
    verification = verify_declared_quantity(
        **_float_case(SUBMITTED), declared=_declaration()
    )

    assert isinstance(verification, QuantityVerification), verification
    assert verification.precision.disposition is DeclarationDisposition.ADMITTED
    assert verification.precision.displaced_by is None
    # Property 5: the verifier records the declaration AND its source text.
    assert verification.precision.declared is not None
    assert verification.precision.declared.declared_in


def test_a_declaration_is_ignored_where_an_artifact_source_supplies_a_precision() -> None:
    """Property 5's admissibility test, in the direction that ignores.

    A `count` over a collection is **exact**, which is a precision the check's
    own derivation rule supplies — the ladder's integer-closed-exactness rung,
    28 of the 61 entries in OD-23's census. So the declaration is ignored and
    the quantity is checked at the artifact rung, which is what the requirement
    says happens: *"it does not refuse"*.
    """
    verification = verify_declared_quantity(
        **_integer_case(reported=3, rows=3), declared=_declaration()
    )

    assert (
        verification.precision.disposition
        is DeclarationDisposition.IGNORED_ARTIFACT_SUPPLIED
    )
    # Checked at the artifact rung rather than refused.
    assert isinstance(verification.report, Verified), verification.report
    assert verification.outcome() is VerificationOutcome.VERIFIED


def test_a_declaration_may_never_make_a_quantity_be_checked_less_strictly() -> None:
    """The weakening vector, made concrete rather than argued about.

    The caller declares `-2` — *to the nearest hundred* — against a count the
    target got wrong by one. Rounded at the declared precision `395` and `396`
    are both `400` and agree. FR-024 property 5: *"A caller-declared precision
    may never be the reason a quantity is checked less strictly than an
    artifact source permits."* So the declaration is ignored, the exact
    comparison stands, and the fault is reported.

    This is the arm that fails if the admissibility test is dropped or
    inverted, and it fails **into a false negative** — a wrong answer read as
    verified — rather than into a crash.
    """
    verification = verify_declared_quantity(
        **_integer_case(reported=396, rows=395), declared=_declaration(places=-2)
    )

    assert isinstance(verification.report, Disagreement), verification.report
    assert verification.outcome() is VerificationOutcome.FAILED
    assert (
        verification.precision.disposition
        is DeclarationDisposition.IGNORED_ARTIFACT_SUPPLIED
    )


# ---------------------------------------------------------------------------
# Property 5, last sub-bullet — an ignored declaration is disclosed ON THE
# RESULT. A disclosure in a trace does not discharge this: the reader arrives
# at the result and nowhere else, which is what FR-058's bounded-result
# disclosure cost this corpus once already.


def test_an_ignored_declaration_is_disclosed_on_the_result_and_names_what_displaced_it() -> None:
    """*"An ignored declaration MUST be disclosed on the result, not silently dropped."*

    Read off the returned object with nothing else in hand — no trace, no log,
    no second call. The disclosure names three things, and each is separately
    asserted because a disclosure missing any one of them is not actionable:
    that a declaration was present, what it was, and which source displaced it.
    """
    verification = verify_declared_quantity(
        **_integer_case(reported=3, rows=3), declared=_declaration()
    )

    disclosure = verification.precision
    assert disclosure.disposition is DeclarationDisposition.IGNORED_ARTIFACT_SUPPLIED
    assert disclosure.declared == _declaration()
    displaced_by = disclosure.displaced_by
    assert isinstance(displaced_by, ConsultedSource), displaced_by
    # `supplied is None` means silent. An artifact that displaced a declaration
    # is by definition not silent, and a displacement citing a silent source
    # would be finding 007's fabricated provenance in a disclosure.
    assert displaced_by.supplied is not None, displaced_by


def test_the_disclosure_is_not_optional_on_the_object_that_carries_the_outcome() -> None:
    """The structural half of the arm above.

    A disclosure a consumer can read the outcome without is one a consumer
    will read the outcome without. `QuantityVerification` has no constructor
    that omits the precision provenance, so there is no value of the returned
    object that carries an outcome and no disposition.
    """
    with pytest.raises(TypeError):
        QuantityVerification(report=Refusal)  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# Property 6 — provisional wherever admitted.


def test_an_admitted_declaration_is_marked_provisional_and_is_never_plainly_verified() -> None:
    """Property 6, and the reason it is not a formality under this variant.

    *"No artifact source supplies one"* is the variant's own admissibility
    premise, so the precision is by construction a derived field that **cannot**
    be validated against an independent artifact. Constitution Principle I at
    v1.1.0 leaves exactly one disposition for that, and this is it.

    The structural half matters more than the flag: the report is **not**
    `Verified`, which is the token `src/analysis/validate.py` issues and the
    thing a consumer asks `isinstance` about. A caller cannot reach the plain
    state by ignoring a field, because the plain state is a different type.
    """
    verification = verify_declared_quantity(
        **_float_case(TRUE_VALUE), declared=_declaration()
    )

    assert isinstance(verification.report, ProvisionallyVerified), verification.report
    assert not isinstance(verification.report, Verified)
    assert verification.precision.is_provisional
    assert verification.precision.disposition is DeclarationDisposition.ADMITTED


def test_an_ignored_declaration_is_not_marked_provisional() -> None:
    """The other half of the marking, and it is not decoration.

    Property 6 marks *"a verification whose precision came from the caller's
    request"*. Where the declaration was ignored the precision came from an
    artifact, so marking it provisional would understate a verification the
    ladder is entitled to — the mirror of the defect property 6 exists to
    prevent, and the reason `is_provisional` reads the disposition rather than
    being a second field that can disagree with it.
    """
    verification = verify_declared_quantity(
        **_integer_case(reported=3, rows=3), declared=_declaration()
    )

    # Both, and the first is why this arm is not satisfied by a rung that does
    # nothing: `NOT_REACHED` is also not provisional, so asserting only the
    # marking would pass against a verifier that never computed a disposition.
    assert (
        verification.precision.disposition
        is DeclarationDisposition.IGNORED_ARTIFACT_SUPPLIED
    )
    assert not verification.precision.is_provisional


# ---------------------------------------------------------------------------
# What the rung buys, scored against OD-23's own measured instance.


def test_the_admitted_rung_detects_the_sub_one_percent_near_miss_the_census_measured() -> None:
    """OD-23's instance: `3.23` against `3.201754`, a 0.882% error.

    *"The sole entry on the request rung in the census of 61"*, and the only
    measured sub-one-percent catch. At the two decimal places the request asked
    for, `3.23` and `3.20` differ. Without this rung the quantity refuses and
    the fault is neither detected nor missed — which is what SC-005's
    denominator rule means by a quantity leaving both the numerator and the
    denominator.
    """
    verification = verify_declared_quantity(
        **_float_case(SUBMITTED), declared=_declaration()
    )

    assert isinstance(verification.report, Disagreement), verification.report
    assert verification.outcome() is VerificationOutcome.FAILED
    assert verification.precision.disposition is DeclarationDisposition.ADMITTED


def test_a_fault_finer_than_the_declared_granularity_passes_which_is_the_named_residual() -> None:
    """**This asserts a known weakness, deliberately, and it is the decision's own.**

    OD-23 records it in as many words: *"a declaration looser than the quantity
    genuinely supports lets a fault smaller than the declared granularity pass
    as verified — a missed fault […] a submission of `3.20` against the same
    true `3.201754` would have passed."*

    It is pinned here rather than left implicit because it is the residual the
    provisional marking exists to carry, and a residual nothing asserts is one
    a later pass will close by accident and call a bug fix. The marking is
    asserted alongside it: the state this reaches is provisional, never plain
    verified, which is the whole of what bounds it.
    """
    verification = verify_declared_quantity(
        **_float_case(3.20), declared=_declaration()
    )

    assert isinstance(verification.report, ProvisionallyVerified), verification.report
    assert verification.precision.is_provisional


# ---------------------------------------------------------------------------
# What the rung must NOT do. FR-025 has three states and "refused" is not a
# fourth; T130 reports the not-verifiable share broken down by `RefusalReason`
# together with `UNATTRIBUTED`, and `_check_totals` asserts the two sum to the
# not-verifiable total. A rung that reached not-verifiable by a new route would
# break that sum.


def test_the_declared_rung_reaches_no_not_verifiable_state_the_ladder_did_not_already_reach() -> None:
    """The rung strictly shrinks the not-verifiable population, never grows it.

    Asserted over every case this file can build rather than over a chosen one,
    and in the form that survives a case being added: for each, the declared
    entry point's outcome is not-verifiable **only if** the undeclared one was.
    A new route to not-verifiable would need a new attribution and would break
    `_check_totals`' sum in `src/runtime/reports/not_verifiable.py`.
    """
    cases = [
        _float_case(SUBMITTED),
        _float_case(TRUE_VALUE),
        _integer_case(reported=3, rows=3),
        _integer_case(reported=396, rows=395),
    ]

    for case in cases:
        undeclared = verify_quantity(**case).outcome()
        declared = verify_declared_quantity(**case, declared=_declaration()).outcome()
        if declared is VerificationOutcome.NOT_VERIFIABLE:
            assert undeclared is VerificationOutcome.NOT_VERIFIABLE, (
                f"{case['check'].quantity}: the declared rung reached "
                "not-verifiable where the ladder alone did not. That is a new "
                "route into the state T130 reports, and it has no attribution "
                "in RefusalReason or UNATTRIBUTED — the breakdown would stop "
                "summing to the total."
            )


def test_a_declaration_does_not_rescue_a_refusal_that_is_not_about_precision() -> None:
    """A declaration acts on the precision rung and on nothing else.

    A boolean reported against a count refuses as `QUANTITY_NOT_A_MAGNITUDE`,
    and no precision would make that comparison meaningful — `True == 1` in
    Python. The disposition is `NOT_REACHED` rather than
    `IGNORED_ARTIFACT_SUPPLIED`, because no artifact source displaced anything:
    the ladder never got as far as asking.
    """
    case = _integer_case(reported=3, rows=3)
    case["result"] = ReportedResult(source="agent answer", payload={"lot_count": True})

    verification = verify_declared_quantity(**case, declared=_declaration())

    assert isinstance(verification.report, Refusal), verification.report
    assert verification.report.reason is RefusalReason.QUANTITY_NOT_A_MAGNITUDE
    assert verification.precision.disposition is DeclarationDisposition.NOT_REACHED
    assert verification.precision.displaced_by is None
    assert not verification.precision.is_provisional


def test_a_provisional_contract_is_not_rescued_by_a_declaration_either() -> None:
    """T123's rule survives the new rung.

    A `ProvisionalContract` refuses at `CONTRACT_PROVISIONAL` before the
    precision question is reached at all, and a caller-declared precision is
    not a route around constitution Principle I.
    """
    check = _check(
        quantity="unit_cost_high", operator="max", over="lots", element_field="unit_cost"
    )
    contract = ProvisionalContract(
        contract=DerivedContract(
            operation_id=check.operation_id,
            reads=(),
            writes=(),
            preconditions=(),
            postconditions=(check.expression,),
            failure_taxonomy=(),
            provenance=_provenance("aggregate_binding", "list_lots"),
            checks=(check,),
        ),
        reason=ProvisionalReason.NO_SPECIFICATION,
        detail="no published specification was supplied",
    )

    verification = verify_declared_quantity(
        contract=contract,
        check=check,
        result=ReportedResult(source="agent answer", payload={"unit_cost_high": TRUE_VALUE}),
        path=SuppliedCollection(
            "lots", [{"unit_cost": TRUE_VALUE}], source="supplied collection"
        ),
        declared=_declaration(),
    )

    assert isinstance(verification.report, Refusal), verification.report
    assert verification.report.reason is RefusalReason.CONTRACT_PROVISIONAL
    assert verification.precision.disposition is DeclarationDisposition.NOT_REACHED


# ---------------------------------------------------------------------------
# The declaration and its disclosure as types. Property 5 requires the
# declaration AND its source text to be recorded as the precision's
# provenance, so a declaration that cannot say where it came from is refused
# at construction rather than admitted and reported as unattributable.


def test_a_declaration_with_no_source_text_is_refused_at_construction() -> None:
    """*"Record the declaration and its source text as the precision's provenance."*

    An unattributable declaration is exactly what property 4's *"a precision a
    model proposes is not a source"* rules out one level up: without the source
    text nothing distinguishes a precision the caller asked for from one the
    agent supplied on the caller's behalf.
    """
    with pytest.raises(VerificationError, match="source text"):
        DeclaredPrecision(decimal_places=DECLARED_PLACES, declared_in="   ")


def test_a_disclosure_cannot_claim_a_displacement_that_did_not_happen() -> None:
    """Both directions, because either alone is satisfiable by a broken pair.

    An `ADMITTED` disposition naming a source that displaced the declaration is
    a contradiction, and an `IGNORED_ARTIFACT_SUPPLIED` naming none is a
    disclosure with the actionable half missing.
    """
    with pytest.raises(VerificationError, match="displaced"):
        PrecisionProvenance(
            disposition=DeclarationDisposition.ADMITTED,
            declared=_declaration(),
            displaced_by=ConsultedSource(
                artifact_class="postcondition", supplied="exact", detail="d"
            ),
            detail="d",
        )

    with pytest.raises(VerificationError, match="displaced"):
        PrecisionProvenance(
            disposition=DeclarationDisposition.IGNORED_ARTIFACT_SUPPLIED,
            declared=_declaration(),
            displaced_by=None,
            detail="d",
        )


def test_a_displacing_source_must_be_one_fr_024_admits() -> None:
    """Property 4's set governs the disclosure too, and by construction.

    `ConsultedSource.__post_init__` is what refuses this, and the arm is here
    rather than only in `test_verify.py` because the disclosure is a second
    place a fabricated source could enter the record.
    """
    with pytest.raises(VerificationError, match="admissible source"):
        ConsultedSource(
            artifact_class="the callers own request", supplied="two places", detail="d"
        )
