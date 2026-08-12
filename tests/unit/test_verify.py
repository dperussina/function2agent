"""T124 and T125 — the recomputing verifier, and its named refusals.

**T124** owns obtaining the recomputed value by an independent path and turning
a disagreement into an outcome. **T125** owns refusing, with a named reason,
where no check of stated precision can be derived — never falling back to a
default tolerance.

## What is real in each arm, stated per arm rather than once

No committed artifact in this tree supplies a **real derivation** and a **real
deployment** for the same quantity, and that is a fact about the fixtures rather
than a gap in this file:

- `derive_module` walks module-level functions. The reference application's five
  served operations are **methods on `Application`**, so deriving from `app.py`
  yields four contracts carrying nothing but `shape` checks —
  `test_the_reference_applications_own_source_derives_no_recomputation` asserts
  exactly that, so the claim is checked rather than asserted in prose.
- The analyzer fixture `inventory-service/` derives three real recomputations
  over a collection named `lots`, and **there is no deployment serving `lots`**.

So each arm names which half is real. The pair that is never real at once is
recorded at T124 in `tasks.md` as the unexercised half.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import sys
import threading
import urllib.request
from pathlib import Path
from types import ModuleType
from typing import Any, Sequence

import pytest

from src.analysis.derive import (
    CheckKind,
    DerivedCheck,
    DerivedContract,
    Recomputation,
    derive_module,
)
from src.analysis.provenance import (
    FR_023_ARTIFACT_CLASSES,
    Provenance,
    ValidationStatus,
    hash_source_construct,
)
from src.analysis.validate import (
    ProvisionalContract,
    ProvisionalReason,
    ValidatedContract,
    Verified,
)
from src.contracts.result import VerificationOutcome
from src.runtime.verify import (
    ConsultedSource,
    Disagreement,
    PathUnavailable,
    Refusal,
    RefusalReason,
    ReportedResult,
    SourcedValue,
    VerificationError,
    recompute,
    reported_quantity,
    verify_quantity,
)

REPO = Path(__file__).resolve().parents[2]
FIXTURE = REPO / "tests" / "fixtures" / "reference-app"
ANALYZER = REPO / "tests" / "fixtures" / "analyzer" / "inventory-service"
VERIFY_SOURCE = REPO / "src" / "runtime" / "verify.py"


def _load(name: str) -> ModuleType:
    """Load a reference-app module, on `test_reference_app.py`'s convention."""
    if str(FIXTURE) not in sys.path:
        sys.path.insert(0, str(FIXTURE))
    spec = importlib.util.spec_from_file_location(
        f"_verify_refapp_{name}", FIXTURE / f"{name}.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


app_mod = _load("app")


# ---------------------------------------------------------------------------
# The independent paths. Both reach a **real** application; neither is handed
# the reported result, and neither could accept one — see
# `tests/contract/test_independent_derivation.py`, which asserts that as a
# property of the signatures rather than of these two classes.


class InProcessPath:
    """`Application.call`, which T116 holds to the same program as the socket."""

    def __init__(self, application: Any, method: str, target: str) -> None:
        self._application = application
        self._method = method
        self._target = target

    def source(self) -> str:
        return f"in-process {self._method} {self._target}"

    def collection(self, name: str) -> Sequence[Any]:
        status, body = self._application.call(self._method, self._target)
        if status != 200:
            raise PathUnavailable(
                f"{self._method} {self._target} answered {status}: {body}"
            )
        if name not in body:
            raise PathUnavailable(
                f"{self._method} {self._target} returned no {name!r}; it "
                f"returned {sorted(body)}"
            )
        return list(body[name])


class SocketPath:
    """The same application over its HTTP origin, which is the arm T101 drives."""

    def __init__(self, base: str, method: str, target: str) -> None:
        self._base = base
        self._method = method
        self._target = target

    def source(self) -> str:
        return f"{self._base} {self._method} {self._target}"

    def collection(self, name: str) -> Sequence[Any]:
        with urllib.request.urlopen(f"{self._base}{self._target}") as response:
            body = json.loads(response.read())
        if name not in body:
            raise PathUnavailable(f"the origin returned no {name!r}")
        return list(body[name])


class StaticCollectionPath:
    """A collection supplied by the test, for the arms whose *check* is real.

    Labelled rather than hidden: this is **not** a deployment. It exists so that
    a check `derive_module` genuinely produced from committed source can be
    executed at all, because nothing in this tree serves the collection that
    check names.
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


# ---------------------------------------------------------------------------
# Contract and check construction.


def _provenance(rule: str, symbol: str, *, validated: bool) -> Provenance:
    return Provenance(
        derivation_rule=rule,
        source_symbol=symbol,
        source_file="app.py",
        content_hash=hash_source_construct(symbol),
        validation_status=(
            ValidationStatus.VALIDATED if validated else ValidationStatus.PROVISIONAL
        ),
        validated_against="served_operations.json" if validated else None,
    )


def _recomputing_check(
    *,
    operation_id: str = "app:list_shipments",
    quantity: str = "shipment_count",
    operator: str = "count",
    over: str = "shipments",
    element_field: str | None = None,
) -> DerivedCheck:
    return DerivedCheck(
        operation_id=operation_id,
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
        provenance=_provenance("aggregate_binding", "list_shipments", validated=False),
    )


def _shape_check(operation_id: str = "app:list_shipments") -> DerivedCheck:
    return DerivedCheck(
        operation_id=operation_id,
        quantity="<return>",
        check_kind=CheckKind.SHAPE,
        expression="isinstance(<return>, dict)",
        provenance=_provenance("return_annotation", "list_shipments", validated=False),
    )


def _contract(check: DerivedCheck, *, reads: tuple[str, ...] = ()) -> DerivedContract:
    return DerivedContract(
        operation_id=check.operation_id,
        reads=reads,
        writes=(),
        preconditions=(),
        postconditions=(check.expression,),
        failure_taxonomy=(),
        provenance=_provenance("aggregate_binding", "list_shipments", validated=False),
        checks=(check,),
    )


def _validated(check: DerivedCheck, **kwargs: Any) -> ValidatedContract:
    """A promoted contract.

    Built here rather than promoted from a committed specification, and
    `test_the_committed_published_specification_promotes_nothing` is the
    executable statement of why: the one published specification in this tree
    declares no parameters, so `validate_contract` correctly reads it as silent
    and promotes nothing. This is T122's residual inherited, not a shortcut.
    """
    return ValidatedContract(
        contract=_contract(check, **kwargs),
        validated_against="file://tests/fixtures/reference-app/served_operations.json",
        agreed_on=("part_id",),
        deployment_id="d-reference-app",
    )


def _provisional(check: DerivedCheck) -> ProvisionalContract:
    return ProvisionalContract(
        contract=_contract(check),
        reason=ProvisionalReason.NO_SPECIFICATION,
        detail="no published specification was supplied",
    )


def _shipments_for(part_id: str) -> list[dict[str, Any]]:
    application = app_mod.from_committed_state()
    _status, body = application.call("GET", f"/shipments?part_id={part_id}")
    return list(body["shipments"])


# ---------------------------------------------------------------------------
# T124 — the recomputation, against the real application.


def test_a_recomputing_check_that_agrees_yields_verified() -> None:
    """The whole point, over the reference application's own API.

    Real deployment; the check is constructed here because `app.py` derives
    none — see this module's docstring and the assertion below it.
    """
    application = app_mod.from_committed_state()
    rows = _shipments_for("P-0011")
    check = _recomputing_check()

    report = verify_quantity(
        contract=_validated(check),
        check=check,
        result=ReportedResult(
            source="agent answer to Q-004", payload={"shipment_count": len(rows)}
        ),
        path=InProcessPath(application, "GET", "/shipments?part_id=P-0011"),
    )

    assert isinstance(report, Verified), report
    assert report.outcome() is VerificationOutcome.VERIFIED
    assert report.agreement.value == len(rows)


def test_the_socket_arm_reaches_the_same_verdict_as_the_in_process_arm() -> None:
    """T116 holds the two surfaces to one program; the verifier must see one too."""
    served = app_mod.from_committed_state()
    server = app_mod.build_server(served, host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address[0], server.server_address[1]
        rows = _shipments_for("P-0011")
        check = _recomputing_check()
        over_socket = verify_quantity(
            contract=_validated(check),
            check=check,
            result=ReportedResult(
                source="agent answer to Q-004", payload={"shipment_count": len(rows)}
            ),
            path=SocketPath(
                f"http://{host}:{port}", "GET", "/shipments?part_id=P-0011"
            ),
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert isinstance(over_socket, Verified), over_socket


def test_a_sum_over_an_element_field_recomputes_from_the_collection() -> None:
    application = app_mod.from_committed_state()
    rows = _shipments_for("P-0011")
    total = sum(row["quantity"] for row in rows)
    check = _recomputing_check(
        quantity="total_quantity",
        operator="sum",
        over="shipments",
        element_field="quantity",
    )

    report = verify_quantity(
        contract=_validated(check),
        check=check,
        result=ReportedResult(
            source="agent answer", payload={"total_quantity": total}
        ),
        path=InProcessPath(application, "GET", "/shipments?part_id=P-0011"),
    )

    assert isinstance(report, Verified), report


# ---------------------------------------------------------------------------
# The two negative controls Rule 8 requires of a verifier that reports
# agreement: it must be shown able to report a disagreement, and shown to
# detect a fault. A verifier that only ever agrees is indistinguishable from
# `return VERIFIED`.


def test_a_planted_disagreement_is_reported_as_a_disagreement() -> None:
    """Negative control 1 — the verifier can say no at all.

    Every arm above asserts an agreement, and an agreement is the *absence* of
    a failure signal. Without this arm the whole file is satisfied by a
    verifier that returns `Verified` unconditionally.
    """
    application = app_mod.from_committed_state()
    rows = _shipments_for("P-0011")
    check = _recomputing_check()

    report = verify_quantity(
        contract=_validated(check),
        check=check,
        result=ReportedResult(
            source="agent answer", payload={"shipment_count": len(rows) + 7}
        ),
        path=InProcessPath(application, "GET", "/shipments?part_id=P-0011"),
    )

    assert isinstance(report, Disagreement), report
    assert report.outcome() is VerificationOutcome.FAILED
    assert report.reported.value == len(rows) + 7
    assert report.recomputed.value == len(rows)


def test_a_planted_fault_smaller_than_one_percent_is_detected() -> None:
    """Negative control 2 — the fault class **SC-005** names, at its hard end.

    Feature 001 measured ~~8~~ **9** schema-blind numeric false successes and 3
    sub-1% near-misses. A verifier that catches a fault of 7 and misses a fault
    of 1 on a total of 200+ has not covered the class the product is sold on.
    The plant here is **one unit**, which is under one percent of the correct
    sum.

    *Corrected 2026-08-12 from `E8-VIABILITY.md` §6: the numeric count is 9, not
    8 (the split is 9 numeric and 2 set-typed). The sub-1% figure of 3 beside it
    was already the corrected one — §7's table advances it from 2 — so this
    sentence had been carrying one corrected figure and one superseded one at
    the same time, and the two now agree.*
    """
    application = app_mod.from_committed_state()
    _status, body = app_mod.from_committed_state().call("GET", "/shipments")
    correct = sum(row["quantity"] for row in body["shipments"])
    faulted = correct + 1
    # The plant is one unit. This assertion is not decoration: the whole
    # collection is used rather than the part-filtered one precisely because a
    # plant of one on the smaller collection is 2.9% and would make this arm a
    # statement about a class it does not cover.
    assert abs(faulted - correct) / correct < 0.01, (
        "this control is only about the sub-1% class if the plant is inside "
        f"it; correct={correct}, faulted={faulted}"
    )

    check = _recomputing_check(
        quantity="total_quantity",
        operator="sum",
        over="shipments",
        element_field="quantity",
    )
    report = verify_quantity(
        contract=_validated(check),
        check=check,
        result=ReportedResult(
            source="agent answer", payload={"total_quantity": faulted}
        ),
        path=InProcessPath(application, "GET", "/shipments"),
    )

    assert isinstance(report, Disagreement), (
        f"a fault of one unit on a total of {correct} was not detected; this "
        "is exactly the class a schema-conformant verifier is blind to"
    )


def test_a_shape_only_check_cannot_reach_verified() -> None:
    """FR-022's explicit clause, as an outcome rather than as an exception.

    `validate.py` already makes `Verified` unconstructible from a shape check.
    What this asserts is that the verifier does not *raise* over it — a caller
    holding only shape checks gets a named not-verifiable, which is the state
    FR-025 requires and T130 reports the share of.
    """
    application = app_mod.from_committed_state()
    check = _shape_check()

    report = verify_quantity(
        contract=_validated(check),
        check=check,
        result=ReportedResult(source="agent answer", payload={"<return>": {}}),
        path=InProcessPath(application, "GET", "/shipments"),
    )

    assert isinstance(report, Refusal), report
    assert report.reason is RefusalReason.NO_RECOMPUTING_CHECK
    assert report.outcome() is VerificationOutcome.NOT_VERIFIABLE


def test_a_provisional_contract_refuses_and_never_verifies() -> None:
    """T123's barrier, surfaced at the verifier as a named outcome."""
    application = app_mod.from_committed_state()
    rows = _shipments_for("P-0011")
    check = _recomputing_check()

    report = verify_quantity(
        contract=_provisional(check),
        check=check,
        result=ReportedResult(
            source="agent answer", payload={"shipment_count": len(rows)}
        ),
        path=InProcessPath(application, "GET", "/shipments?part_id=P-0011"),
    )

    assert isinstance(report, Refusal), report
    assert report.reason is RefusalReason.CONTRACT_PROVISIONAL
    assert report.outcome() is VerificationOutcome.NOT_VERIFIABLE


def test_the_reference_applications_own_source_derives_no_recomputation() -> None:
    """The fixture fact this file's arm labelling rests on, asserted not assumed.

    If a future change makes `app.py` derive a recomputation, the arms above
    can stop constructing a check and this test is where that is noticed.
    """
    contracts = derive_module(FIXTURE / "app.py", relative_to=FIXTURE)
    kinds = {
        check.check_kind for contract in contracts for check in contract.checks
    }
    assert kinds == {CheckKind.SHAPE}, (
        f"app.py now derives {kinds}. The served operations are methods on "
        "`Application` and `derive_module` walks module-level functions, so "
        "this was shape-only when T124 was written"
    )


def test_a_real_derived_check_runs_against_a_collection_the_test_supplies() -> None:
    """Real **derivation**, constructed collection. The mirror of the arms above.

    The check is whatever `derive_module` genuinely produces from the committed
    analyzer fixture — not written here — and it is executed rather than
    inspected.
    """
    contracts = derive_module(ANALYZER / "service.py", relative_to=ANALYZER)
    check = next(
        c
        for contract in contracts
        for c in contract.checks
        if c.quantity == "total_units"
    )
    assert check.recomputation is not None
    assert check.recomputation.over == "lots"

    lots = [{"quantity": 3}, {"quantity": 4}, {"quantity": 5}]
    report = verify_quantity(
        contract=_validated(check),
        check=check,
        result=ReportedResult(source="reported stock report", payload={"total_units": 12}),
        path=StaticCollectionPath("lots", lots, source="lots supplied by the test"),
    )

    assert isinstance(report, Verified), report


def test_a_real_derived_check_whose_collection_no_deployment_serves_refuses() -> None:
    """Real derivation **and** real deployment, and the honest answer is a refusal.

    The check names `lots`; the reference application serves `parts` and
    `shipments`. The verifier must say so rather than reach for something
    shaped like a collection.
    """
    contracts = derive_module(ANALYZER / "service.py", relative_to=ANALYZER)
    check = next(
        c
        for contract in contracts
        for c in contract.checks
        if c.quantity == "lot_count"
    )
    application = app_mod.from_committed_state()

    report = verify_quantity(
        contract=_validated(check),
        check=check,
        result=ReportedResult(source="reported stock report", payload={"lot_count": 3}),
        path=InProcessPath(application, "GET", "/shipments"),
    )

    assert isinstance(report, Refusal), report
    assert report.reason is RefusalReason.COLLECTION_UNAVAILABLE
    assert "lots" in report.detail


def test_a_check_from_another_contract_is_refused_rather_than_joined() -> None:
    """T122's rule, one level down: a join between two artifacts is declared."""
    check = _recomputing_check(operation_id="app:list_parts")
    other = _recomputing_check(operation_id="app:list_shipments")

    with pytest.raises(VerificationError, match="does not belong"):
        verify_quantity(
            contract=_validated(other),
            check=check,
            result=ReportedResult(source="agent answer", payload={"shipment_count": 1}),
            path=StaticCollectionPath("shipments", [], source="anything"),
        )


# ---------------------------------------------------------------------------
# T125 — refusal with a named reason, and never a default tolerance.


def test_a_float_pair_refuses_with_a_named_reason_naming_the_silent_sources() -> None:
    """FR-024, both halves of it.

    The refusal is named, **and** it names which sources were consulted and
    found silent — which is the requirement's closing sentence and the thing a
    bare exception cannot carry.
    """
    check = _recomputing_check(
        quantity="total_value",
        operator="sum",
        over="lots",
        element_field="value",
    )
    lots = [{"value": 1.5}, {"value": 2.25}]

    report = verify_quantity(
        contract=_validated(check),
        check=check,
        result=ReportedResult(source="agent answer", payload={"total_value": 3.75}),
        path=StaticCollectionPath("lots", lots, source="lots supplied by the test"),
    )

    assert isinstance(report, Refusal), report
    assert report.reason is RefusalReason.PRECISION_NOT_STATED
    assert report.consulted, "a refusal that names no consulted source says nothing"
    assert all(isinstance(entry, ConsultedSource) for entry in report.consulted)
    assert all(entry.supplied is None for entry in report.consulted), (
        "every consulted source on a PRECISION_NOT_STATED refusal must have "
        "been found silent; one that supplied a precision would mean the "
        "refusal was wrong"
    )
    names = {entry.artifact_class for entry in report.consulted}
    assert names <= FR_023_ARTIFACT_CLASSES | {"published_specification"}, (
        "FR-024 property 4 fixes the admissible sources; a consulted source "
        f"outside that set is invented: {sorted(names)}"
    )


def test_the_float_refusal_is_not_a_disagreement_even_when_the_values_agree() -> None:
    """The sharp end: two equal floats must refuse, not verify.

    Exact equality over floats would *pass* here, and passing would be the
    accident FR-024 forbids — a comparison whose precision nobody stated,
    reading as verification.
    """
    check = _recomputing_check(
        quantity="total_value", operator="sum", over="lots", element_field="value"
    )
    lots = [{"value": 1.5}, {"value": 2.5}]

    report = verify_quantity(
        contract=_validated(check),
        check=check,
        result=ReportedResult(source="agent answer", payload={"total_value": 4.0}),
        path=StaticCollectionPath("lots", lots, source="lots supplied by the test"),
    )

    assert isinstance(report, Refusal), report
    assert report.reason is RefusalReason.PRECISION_NOT_STATED


def test_a_boolean_reported_quantity_refuses_rather_than_agreeing_with_one() -> None:
    """`True == 1` in Python, so a boolean agrees with a count of one."""
    check = _recomputing_check(over="lots")
    report = verify_quantity(
        contract=_validated(check),
        check=check,
        result=ReportedResult(source="agent answer", payload={"shipment_count": True}),
        path=StaticCollectionPath("lots", [{"a": 1}], source="one row"),
    )

    assert isinstance(report, Refusal), report
    assert report.reason is RefusalReason.QUANTITY_NOT_A_MAGNITUDE


def test_a_quantity_absent_from_the_reported_result_refuses() -> None:
    check = _recomputing_check()
    report = verify_quantity(
        contract=_validated(check),
        check=check,
        result=ReportedResult(source="agent answer", payload={"something_else": 3}),
        path=StaticCollectionPath("shipments", [], source="empty"),
    )

    assert isinstance(report, Refusal), report
    assert report.reason is RefusalReason.QUANTITY_ABSENT_FROM_RESULT


def test_every_refusal_names_at_least_one_consulted_source() -> None:
    """A refusal that consulted nothing is indistinguishable from an untried one."""
    with pytest.raises(VerificationError, match="consulted"):
        Refusal(
            reason=RefusalReason.PRECISION_NOT_STATED,
            detail="nothing was looked at",
            consulted=(),
        )


def test_a_refusal_cannot_name_a_source_outside_fr_024s_admissible_set() -> None:
    """FR-024 property 4 fixes the sources. An invented one is fabricated provenance.

    Finding 007 measured a clause naming in its provenance string an endpoint
    it never read; this is that defect arriving in a refusal instead of in a
    contract, and the constructor is where it is stopped.
    """
    with pytest.raises(VerificationError, match="admissible source"):
        ConsultedSource(
            artifact_class="a model looked at it",
            supplied=None,
            detail="invented",
        )


def test_an_empty_collection_refuses_rather_than_aggregating_to_zero() -> None:
    """`sum([])` is 0, and a reported 0 would verify against nothing at all.

    This is the sharpest false-success available to a recomputing verifier: the
    independent path returns nothing, the aggregate over nothing is a number,
    and the number agrees. An empty aggregate is not zero.
    """
    check = _recomputing_check(
        quantity="total_units", operator="sum", over="lots", element_field="quantity"
    )
    report = verify_quantity(
        contract=_validated(check),
        check=check,
        result=ReportedResult(source="agent answer", payload={"total_units": 0}),
        path=StaticCollectionPath("lots", [], source="a collection with no rows"),
    )

    assert isinstance(report, Refusal), (
        f"an empty collection produced {report!r}; if that is a Verified, the "
        "verifier just agreed with a number nothing was computed from"
    )
    assert report.reason is RefusalReason.COLLECTION_UNAVAILABLE


def test_a_reported_result_with_no_named_source_is_refused_at_construction() -> None:
    """An unnamed source would pass the independence comparison by omission.

    An empty `source` is not equal to any path's `source()`, so a reported
    result that names no producer would compare as independent of everything
    while having been read from anywhere — including from the path itself.
    """
    with pytest.raises(VerificationError, match="names the path that produced it"):
        ReportedResult(source="   ", payload={"shipment_count": 3})


def test_a_disagreement_between_two_values_from_one_retrieval_is_refused() -> None:
    """A disagreement is a claim about the target, so its operands must be two.

    Reachable by a direct constructor call rather than through
    `verify_quantity`, which refuses one retrieval earlier — and it is held
    here because T126 and T127 will build records from these types without
    going through this module's entry point.
    """
    one = SourcedValue(value=3, retrieval="one response", field="shipment_count")
    other = SourcedValue(value=4, retrieval="one response", field="shipments")

    with pytest.raises(VerificationError, match="defect in the verifier"):
        Disagreement(reported=one, recomputed=other, detail="they differ")


def test_no_tolerance_constant_exists_anywhere_in_the_module() -> None:
    """T125's rule as a property of the source, not of a code review.

    Scans identifiers and numeric literals rather than text, so the module's
    own prose about tolerances — which is extensive and load-bearing — cannot
    satisfy or trip it.
    """
    tree = ast.parse(VERIFY_SOURCE.read_text())

    floats = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, float)
    ]
    assert not floats, (
        "src/runtime/verify.py carries a float literal at line(s) "
        f"{[n.lineno for n in floats]}. FR-024 forbids a default tolerance and "
        "a float constant in a comparison module is one however it is named"
    )

    banned = {"tolerance", "epsilon", "eps", "atol", "rtol", "delta", "isclose"}
    identifiers = {
        node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
    } | {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    } | {
        node.arg for node in ast.walk(tree) if isinstance(node, ast.arg)
    }
    found = {name for name in identifiers if name.lower() in banned}
    assert not found, (
        f"src/runtime/verify.py names {sorted(found)}. A tolerance introduced "
        "here would settle FR-024's open question by accident"
    )


def test_the_refusal_reasons_are_closed_and_each_one_is_reachable() -> None:
    """A member nothing produces is a reason nobody can be given.

    Held as a declared set so that adding a member forces the author to say
    what produces it, which is the same discipline `EXPECTED_PROOFS` applies to
    the proof set.
    """
    assert {member.name for member in RefusalReason} == {
        "CONTRACT_PROVISIONAL",
        "NO_RECOMPUTING_CHECK",
        "QUANTITY_ABSENT_FROM_RESULT",
        "QUANTITY_NOT_A_MAGNITUDE",
        "COLLECTION_UNAVAILABLE",
        "PRECISION_NOT_STATED",
        "SOURCES_NOT_INDEPENDENT",
    }


def test_reported_quantity_and_recompute_agree_with_what_verify_quantity_used() -> None:
    """The two halves are separately callable, which is what T129 introspects."""
    application = app_mod.from_committed_state()
    check = _recomputing_check()
    path = InProcessPath(application, "GET", "/shipments?part_id=P-0011")

    reported = reported_quantity(
        ReportedResult(source="agent answer", payload={"shipment_count": 3}), check
    )
    recomputed = recompute(check, path)

    assert isinstance(reported, SourcedValue)
    assert isinstance(recomputed, SourcedValue)
    assert reported.retrieval != recomputed.retrieval
    assert recomputed.value == len(_shipments_for("P-0011"))
