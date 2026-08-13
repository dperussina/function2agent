"""T213 — the verification seam, scored against reports the verifier produced.

**Requirement**: FR-025. **Decision**: `OD-34`.

## Every report here is produced, not hand-built

`verify_quantity` and `verify_declared_quantity` are called and their return
values are joined. That is the discipline the arm is worth anything under: a
hand-constructed `Refusal` or `Verified` would let the seam be scored against
the four types rather than against the four **states the verifier can actually
reach**, and a mapping that is total over the union but never sees a value the
verifier emits is a table nobody has run.

The one thing supplied rather than served is the collection under the float
check, and it is labelled as such — `test_declared_precision.py` makes the same
disclosure for the same reason: nothing in this tree serves a collection whose
elements carry a float, and the caller-declared rung is only ever reached by a
float.

## The negative control this file exists beside

Before T213 nothing in `src/` called either verifier and `Result` was built at
two sites in `src/analysis/validate.py`, so **no verification outcome reached a
caller-visible record at all** (`OD-34`, measured). Every arm below is therefore
about a route that did not exist, and
`tests/invariants/test_result_constructor.py` is what keeps a second, unjoined
route from opening beside it.
"""

from __future__ import annotations

from typing import Any, Sequence

import pytest

from src.analysis.derive import CheckKind, DerivedCheck, DerivedContract, Recomputation
from src.analysis.provenance import Provenance, ValidationStatus, hash_source_construct
from src.analysis.validate import (
    ProvisionalContract,
    ProvisionalReason,
    ValidatedContract,
    Verified,
)
from src.contracts.result import (
    Corroboration,
    ReportedState,
    StaleMarking,
    Staleness,
    VerificationOutcome,
)
from src.runtime.result_join import (
    JOINABLE_OUTCOMES,
    JOINED_CORROBORATION,
    JOINED_OUTCOME,
    REFUSAL_CORROBORATION,
    REPORT_MEMBERS,
    UnjoinableReport,
    result_from_quantity_verification,
    result_from_report,
)
from src.runtime.verify import (
    DeclarationDisposition,
    DeclaredPrecision,
    Disagreement,
    PathUnavailable,
    ProvisionallyVerified,
    Refusal,
    RefusalReason,
    ReportedResult,
    verify_declared_quantity,
    verify_quantity,
)

#: `OD-23`'s measured pair, reused so the float arms here score against the same
#: instance the decision was taken on.
TRUE_VALUE = 3.201754
DECLARED_PLACES = 2


class SuppliedCollection:
    """A collection supplied by the test. **Not a deployment**, and labelled."""

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


def _provenance() -> Provenance:
    return Provenance(
        derivation_rule="aggregate_binding",
        source_symbol="list_lots",
        source_file="app.py",
        content_hash=hash_source_construct("list_lots"),
        validation_status=ValidationStatus.VALIDATED,
        validated_against="served_operations.json",
    )


def _check(
    *, quantity: str, operator: str, over: str, element_field: str | None = None
) -> DerivedCheck:
    return DerivedCheck(
        operation_id="app:list_lots",
        quantity=quantity,
        check_kind=CheckKind.RECOMPUTATION,
        expression=f"{quantity} == {operator}({over})",
        recomputation=Recomputation(
            operator=operator, over=over, element_field=element_field, reads=(over,)
        ),
        precision_source=f"aggregate_over:{operator}",
        provenance=_provenance(),
    )


def _contract(check: DerivedCheck) -> DerivedContract:
    return DerivedContract(
        operation_id=check.operation_id,
        reads=(),
        writes=(),
        preconditions=(),
        postconditions=(check.expression,),
        failure_taxonomy=(),
        provenance=_provenance(),
        checks=(check,),
    )


def _validated(check: DerivedCheck) -> ValidatedContract:
    return ValidatedContract(
        contract=_contract(check),
        validated_against="file://tests/fixtures/reference-app/served_operations.json",
        agreed_on=("part_id",),
        deployment_id="d-reference-app",
    )


def _integer_case(*, reported: int, rows: int) -> dict[str, Any]:
    """A `count`, which an artifact source states the precision of: exact."""
    check = _check(quantity="lot_count", operator="count", over="lots")
    return {
        "contract": _validated(check),
        "check": check,
        "result": ReportedResult(
            source="agent answer", payload={"lot_count": reported}
        ),
        "path": SuppliedCollection(
            "lots",
            [{"unit_cost": 1} for _ in range(rows)],
            source="supplied collection (not a deployment)",
        ),
    }


def _float_case(*, reported: float) -> dict[str, Any]:
    """A `max` over floats, which no artifact source states a precision for."""
    check = _check(
        quantity="unit_cost_high",
        operator="max",
        over="lots",
        element_field="unit_cost",
    )
    return {
        "contract": _validated(check),
        "check": check,
        "result": ReportedResult(
            source="agent answer", payload={"unit_cost_high": reported}
        ),
        "path": SuppliedCollection(
            "lots",
            [{"unit_cost": TRUE_VALUE}],
            source="supplied collection (not a deployment)",
        ),
    }


def _provisional_case() -> dict[str, Any]:
    """A contract nothing corroborated. The verifier refuses before the ladder."""
    check = _check(quantity="lot_count", operator="count", over="lots")
    return {
        "contract": ProvisionalContract(
            contract=_contract(check),
            reason=ProvisionalReason.NO_SPECIFICATION,
            detail="no published specification was supplied for this deployment",
        ),
        "check": check,
        "result": ReportedResult(source="agent answer", payload={"lot_count": 3}),
        "path": SuppliedCollection(
            "lots",
            [{"unit_cost": 1} for _ in range(3)],
            source="supplied collection (not a deployment)",
        ),
    }


def _declaration(places: int = DECLARED_PLACES) -> DeclaredPrecision:
    return DeclaredPrecision(
        decimal_places=places,
        declared_in=f"caller request: report the value to {places} decimal places",
    )


# ---------------------------------------------------------------------------
# The four rows OD-34 ③ fixes, each against a report the verifier produced.


def test_a_verified_report_becomes_a_verified_corroborated_record() -> None:
    report = verify_quantity(**_integer_case(reported=3, rows=3))
    assert isinstance(report, Verified), report

    record = result_from_report(report, payload={"lot_count": 3})

    assert record.verification is VerificationOutcome.VERIFIED
    assert record.corroboration is Corroboration.CORROBORATED
    assert record.state is ReportedState.VERIFIED
    assert record.is_verified
    assert record.reason is None


def test_the_join_agrees_with_the_bridge_validate_py_already_had() -> None:
    """Two independently written producers, one record. Asserted, not assumed.

    `Verified.to_result` predates this seam and writes the same pair. A join
    that disagreed with it would put two caller-visible records for one
    verification in the tree — which is the divergence `REPORTED_STATE` and
    `SPECIFICATION_STATES` are both structured to make impossible one layer
    down, checked rather than asserted in prose.
    """
    report = verify_quantity(**_integer_case(reported=3, rows=3))
    assert isinstance(report, Verified), report

    assert result_from_report(report, payload=None) == report.to_result(payload=None)


def test_the_join_agrees_with_the_provisional_bridge_on_a_provisional_contract() -> None:
    """The other pre-existing bridge, over the one refusal that reports on the contract.

    `ProvisionalContract.to_result` writes `NOT_VERIFIABLE` with
    `PROVISIONAL`, and `REFUSAL_CORROBORATION`'s `CONTRACT_PROVISIONAL` row is
    what makes the seam agree rather than merely not contradict. The reasons
    differ in wording — the bridge writes the contract's own, the seam writes
    the refusal's, which additionally names the machine-readable member — so
    the two are compared on the fields FR-025 defines and the reason is checked
    for containing the same cause.
    """
    case = _provisional_case()
    report = verify_quantity(**case)
    assert isinstance(report, Refusal), report
    assert report.reason is RefusalReason.CONTRACT_PROVISIONAL

    record = result_from_report(report, payload=None)
    bridge = case["contract"].to_result(payload=None)

    assert record.verification == bridge.verification
    assert record.corroboration == bridge.corroboration
    assert record.state is ReportedState.NOT_VERIFIABLE
    assert record.reason is not None
    assert ProvisionalReason.NO_SPECIFICATION.value in record.reason


def test_a_disagreement_becomes_a_failed_record_that_says_nobody_corroborated() -> None:
    """`OD-34` ③ fixes `FAILED`; `NOT_STATED` is this module's and is defended.

    A `Disagreement` carries the two values and their retrievals and **no
    contract**. The comparison was independent — its `__post_init__` refuses a
    pair out of one retrieval — but that is not the claim `CORROBORATED` makes,
    which is about the contract the result was checked against. The seam claims
    corroboration only where the report object carries the contract that earns
    it, and this one does not.
    """
    report = verify_quantity(**_integer_case(reported=4, rows=3))
    assert isinstance(report, Disagreement), report

    record = result_from_report(report, payload={"lot_count": 4})

    assert record.verification is VerificationOutcome.FAILED
    assert record.state is ReportedState.FAILED_VERIFICATION
    assert not record.is_verified
    assert record.corroboration is Corroboration.NOT_STATED
    # OD-34: the report's OWN named reason, not a synthesised one.
    assert record.reason == report.detail


def test_a_refusal_becomes_a_not_verifiable_record_naming_its_own_reason() -> None:
    report = verify_quantity(**_float_case(reported=3.23))
    assert isinstance(report, Refusal), report
    assert report.reason is RefusalReason.PRECISION_NOT_STATED

    record = result_from_report(report, payload={"unit_cost_high": 3.23})

    assert record.verification is VerificationOutcome.NOT_VERIFIABLE
    assert record.state is ReportedState.NOT_VERIFIABLE
    assert record.corroboration is Corroboration.NOT_STATED
    assert record.reason is not None
    # Both halves: the machine-readable member and the detail behind it. A
    # breakdown cannot key on `Result.reason` (see `reports/not_verifiable.py`),
    # and the member being in the text is the most a free-text field can offer.
    assert record.reason.startswith(f"{RefusalReason.PRECISION_NOT_STATED.value}:")
    assert report.detail in record.reason


def test_a_provisionally_verified_report_reaches_no_verified_record() -> None:
    """`OD-34` ③'s one arm that *"cannot be chosen freely"*, as it fixes it.

    ⚠️ **This arm pins a reading the register and the verifier disagree about,
    and the disagreement is recorded rather than resolved here.**
    `ProvisionallyVerified.outcome()` returns `VERIFIED`; `OD-34` ③ fixes the
    *record* at `NOT_VERIFIABLE` with `PROVISIONAL`. The seam follows the
    register because it is the register, and
    `test_the_two_readings_of_a_provisionally_verified_report_are_both_named`
    below names the other reading and what would change under it. Whichever way
    the owner rules, it is one row in `JOINED_OUTCOME`, one in
    `JOINED_CORROBORATION` and these two arms.
    """
    verification = verify_declared_quantity(
        **_float_case(reported=3.20), declared=_declaration()
    )
    assert isinstance(verification.report, ProvisionallyVerified), verification.report
    assert verification.precision.disposition is DeclarationDisposition.ADMITTED

    record = result_from_report(verification.report, payload={"unit_cost_high": 3.20})

    assert record.verification is VerificationOutcome.NOT_VERIFIABLE
    assert record.corroboration is Corroboration.PROVISIONAL
    assert not record.is_verified
    # OD-34 fixes the member at NOT_VERIFIABLE, and `Result` refuses that
    # outcome without a reason. `ProvisionallyVerified` carries no reason field,
    # so the seam composes one out of fields already on the report.
    assert record.reason is not None
    assert "unit_cost_high" in record.reason
    assert _declaration().declared_in in record.reason


def test_the_two_readings_of_a_provisionally_verified_report_are_both_named() -> None:
    """The contradiction, executable rather than only written down.

    The verifier says `VERIFIED`. The register says the record is
    `NOT_VERIFIABLE`. This asserts **both facts as they stand today**, so a
    later edit that silently aligns one to the other fails here and has to say
    which it chose. It is not an assertion that the current disposition is
    right — `OD-34` and T212 are the documents that argue that, and they argue
    opposite ways.
    """
    verification = verify_declared_quantity(
        **_float_case(reported=3.20), declared=_declaration()
    )
    report = verification.report
    assert isinstance(report, ProvisionallyVerified)

    assert report.outcome() is VerificationOutcome.VERIFIED
    assert JOINED_OUTCOME[ProvisionallyVerified] is VerificationOutcome.NOT_VERIFIABLE
    assert JOINED_CORROBORATION[ProvisionallyVerified] is Corroboration.PROVISIONAL


def test_the_seam_does_not_read_the_reports_own_outcome_method() -> None:
    """Which of the two answers the seam transcribes, as a property of the source.

    The three other members' `outcome()` agrees with the table, so an arm
    comparing them proves nothing about which one was consulted. This reads the
    module's own syntax instead: a seam that called `report.outcome()` would
    silently take the verifier's reading for `ProvisionallyVerified` and the
    register's for everything else, which is the worst of the two.

    Parsed rather than grepped. The module's docstrings discuss `outcome()` at
    length — they have to, since the disagreement is the thing being recorded —
    and a substring search would report the explanation as the defect.
    """
    import ast
    import inspect

    from src.runtime import result_join

    tree = ast.parse(inspect.getsource(result_join))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "outcome"
    ]
    assert calls == [], (
        "the seam calls a report's own outcome() at line(s) "
        f"{[node.lineno for node in calls]}. OD-34 ③ fixes the record's "
        "outcome and ProvisionallyVerified.outcome() disagrees with it, so a "
        "call here picks a reading without saying so."
    )


# ---------------------------------------------------------------------------
# Totality, and the one member that must stay unreachable.


def test_the_join_is_total_over_the_union_read_off_the_union() -> None:
    """A fifth member of `VerificationReport` fails here, named nowhere below.

    `REPORT_MEMBERS` is `get_args(VerificationReport)`, so this compares the
    table against the union itself rather than against a list somebody kept up
    to date. The `REPORTED_STATE` arms in `tests/contract/test_result_record.py`
    are the same construction one layer down.
    """
    assert set(REPORT_MEMBERS) == set(JOINED_OUTCOME), (
        "the seam's outcome table and VerificationReport have diverged. "
        f"union={sorted(m.__name__ for m in REPORT_MEMBERS)} "
        f"table={sorted(m.__name__ for m in JOINED_OUTCOME)}"
    )
    assert set(JOINED_CORROBORATION) == set(REPORT_MEMBERS) - {Refusal}, (
        "every member but Refusal takes its corroboration from "
        "JOINED_CORROBORATION, and Refusal takes its from REFUSAL_CORROBORATION"
    )


def test_the_refusal_corroboration_table_is_total_over_the_reason_set() -> None:
    """A newly minted `RefusalReason` fails here rather than taking a default.

    Both available values are claims about the contract, so a member arriving
    without a row would answer that question by omission — the defect
    `Corroboration` replaced a boolean to remove.
    """
    assert set(REFUSAL_CORROBORATION) == set(RefusalReason), (
        "REFUSAL_CORROBORATION is not total over RefusalReason. Missing: "
        f"{sorted(r.value for r in set(RefusalReason) - set(REFUSAL_CORROBORATION))}"
    )


def test_the_seam_can_never_emit_a_model_assessment() -> None:
    """`OD-34` ③, and constitution Principle I at the one point built to hold it.

    Read off the table's **image** rather than off the four calls above,
    because the property is about what the seam can emit and not about what
    four fixtures happened to make it emit.
    """
    assert VerificationOutcome.MODEL_ASSESSED not in JOINABLE_OUTCOMES
    assert VerificationOutcome.MODEL_ASSESSED not in set(JOINED_OUTCOME.values()), (
        "a row maps a VerificationReport member onto MODEL_ASSESSED. Nothing "
        "in verify.py produces one, so this would be a model's opinion "
        "reaching a caller-visible record through the seam — the boundary "
        "tests/invariants/test_import_graph.py keeps closed structurally."
    )
    assert JOINABLE_OUTCOMES == set(VerificationOutcome) - {
        VerificationOutcome.MODEL_ASSESSED
    }


def test_the_backstop_refuses_an_outcome_the_table_should_never_hold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The runtime half of the `MODEL_ASSESSED` exclusion, exercised.

    The arm above reads the table, which is what catches an edit to it. This
    one forces the table to hold the forbidden row and requires the seam to
    refuse anyway, so the exclusion is not carried by the table alone — a
    checker and its backstop that are the same check are one check.

    Patched rather than planted as a fifth union member: adding one would need
    an edit to `verify.py`, and what is under test here is the seam's response
    to a table it cannot trust rather than the union's membership.
    """
    report = verify_quantity(**_float_case(reported=3.23))
    assert isinstance(report, Refusal), report
    monkeypatch.setitem(
        JOINED_OUTCOME,  # type: ignore[arg-type]
        Refusal,
        VerificationOutcome.MODEL_ASSESSED,
    )

    with pytest.raises(UnjoinableReport, match="not an outcome it may emit"):
        result_from_report(report, payload=None)


def test_a_value_that_is_not_a_report_is_refused_by_name() -> None:
    """The `ModuleTextUnavailable` precedent: refuse, never substitute.

    Every default available here is a verification outcome nobody computed, so
    the seam has nothing benign to return.
    """
    with pytest.raises(UnjoinableReport, match="not a member of VerificationReport"):
        result_from_report("verified", payload=None)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# FR-024 property 5's disclosure, carried onto the record rather than dropped.


def test_an_ignored_declaration_is_disclosed_on_the_caller_visible_record() -> None:
    """*"An ignored declaration MUST be disclosed on the result, not silently dropped."*

    The `count` case: an artifact source supplies the precision, so the
    declaration is ignored and the quantity is checked at the artifact rung.
    The record is plainly `VERIFIED` — and a caller who cannot see the ignored
    declaration on it is the reader FR-058 says arrives at the result and
    nowhere else. `Result` permits a reason on a verified record and requires
    none, which is exactly why this has to be an arm.
    """
    verification = verify_declared_quantity(
        **_integer_case(reported=3, rows=3), declared=_declaration()
    )
    assert (
        verification.precision.disposition
        is DeclarationDisposition.IGNORED_ARTIFACT_SUPPLIED
    )

    record = result_from_quantity_verification(verification, payload={"lot_count": 3})

    assert record.verification is VerificationOutcome.VERIFIED
    assert record.reason is not None
    assert DeclarationDisposition.IGNORED_ARTIFACT_SUPPLIED.value in record.reason
    assert verification.precision.detail in record.reason


def test_the_disclosure_is_added_to_the_reports_reason_and_not_instead_of_it() -> None:
    """Both facts survive onto one field, because both are owed.

    A refusal's own named reason is `OD-34` ③'s requirement; the disposition is
    FR-024 property 5's. A seam that overwrote one with the other would
    discharge one requirement by breaking the other.
    """
    verification = verify_declared_quantity(
        **_provisional_case(), declared=_declaration()
    )
    assert isinstance(verification.report, Refusal)
    assert verification.precision.disposition is DeclarationDisposition.NOT_REACHED

    record = result_from_quantity_verification(verification, payload=None)

    assert record.reason is not None
    assert verification.report.detail in record.reason
    assert verification.precision.detail in record.reason


def test_the_admitted_declaration_reaches_the_record_carrying_its_disposition() -> None:
    verification = verify_declared_quantity(
        **_float_case(reported=3.20), declared=_declaration()
    )
    assert verification.precision.disposition is DeclarationDisposition.ADMITTED

    record = result_from_quantity_verification(
        verification, payload={"unit_cost_high": 3.20}
    )

    assert record.verification is VerificationOutcome.NOT_VERIFIABLE
    assert record.corroboration is Corroboration.PROVISIONAL
    assert record.reason is not None
    assert DeclarationDisposition.ADMITTED.value in record.reason


# ---------------------------------------------------------------------------
# FR-047 — the field the seam passes through and does not fill in.


def test_the_seam_makes_no_staleness_claim_by_default() -> None:
    """`NOT_STATED`, not `FRESH`. A verification bears on the contract.

    `Verified.to_result` makes the same choice for the same reason. A default
    of `FRESH` here would be an assertion that the served-operation set was
    current, made by a caller having omitted an argument.
    """
    report = verify_quantity(**_integer_case(reported=3, rows=3))
    record = result_from_report(report, payload=None)

    assert record.staleness.marking is StaleMarking.NOT_STATED
    assert not record.is_stale


def test_a_stale_marking_supplied_by_the_caller_survives_the_join() -> None:
    """FR-047's marking is a field beside the state, and the seam carries it.

    Written as an arm rather than left to Phase 6's T148: a seam that dropped
    the argument would leave the only sanctioned construction site unable to
    record staleness, and the repair would be a second construction site —
    which is the thing `tests/invariants/test_result_constructor.py` now
    reports.
    """
    report = verify_quantity(**_integer_case(reported=3, rows=3))
    stale = Staleness(
        marking=StaleMarking.STALE,
        age_seconds=900.0,
        specification_state="published_non_empty",
    )

    record = result_from_report(report, payload=None, staleness=stale)

    assert record.is_stale
    assert record.staleness == stale
    # FR-047: never a fourth value of the state.
    assert record.verification is VerificationOutcome.VERIFIED
