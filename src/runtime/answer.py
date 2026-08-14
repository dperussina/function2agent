"""T214 — the verification call site on the runtime's own answer path.

A run that reported a quantity calls `verify_quantity` and hands the
report to T213's seam. The `Result` a caller then reads off the served
session is **produced by that run**, not assembled from a type.

## Why this module exists

`verify_quantity` lived only in `verify.py`. `result_from_report` lived
only in `result_join.py`. No request reached either. T215 opened the
serve path; this is the call that sits on it.

## What this module must not do

- **Not** call the verifier from `to_result`. That inverts
  `tests/invariants/test_layering.py`. The plant
  `RESULT_COMES_FROM_TO_RESULT` is the counterfactual.
- **Not** construct a `Result` here. The seam is the authorised site.
- **Not** read a report's `outcome()` in place of the seam's tables.
- **Not** emit `MODEL_ASSESSED`. Nothing in `verify.py` produces it.
- **Not** add a vendor SDK. A cassette-shaped reported quantity is
  enough (T058 PARTIAL).
"""

from __future__ import annotations

from typing import Any, Sequence

from src.analysis.derive import (
    CheckKind,
    DerivedCheck,
    DerivedContract,
    Recomputation,
)
from src.analysis.provenance import (
    Provenance,
    ValidationStatus,
    hash_source_construct,
)
from src.analysis.validate import (
    ProvisionalContract,
    ProvisionalReason,
    ValidatedContract,
)
from src.contracts.result import Result
from src.runtime.result_join import result_from_report
from src.runtime.serving import Registry, SurfaceError
from src.runtime.verify import (
    PathUnavailable,
    ReportedResult,
    VerificationReport,
    verify_quantity,
)

# ---------------------------------------------------------------------------
# Planted flags. Each one is a removal-proof needle. Flipping it is the
# defect the named T214 test exists to catch.
# ---------------------------------------------------------------------------

#: The run calls `verify_quantity`. False skips the verifier.
VERIFY_IS_CALLED = True
#: The run hands the report to T213's seam. False skips the join.
JOIN_IS_CALLED = True
#: The forbidden path: `to_result` instead of verify-then-join.
RESULT_COMES_FROM_TO_RESULT = False
#: The run attaches the Result to the served view. False leaves GET 409.
RESULT_IS_ATTACHED = True


class AnswerError(RuntimeError):
    """A run that cannot produce a caller-visible result as described."""


class _CassettePath:
    """Independent retrieval supplied with the cassette, not a live target.

    T058: `ProviderDriver.call` still raises. This path is the second
    retrieval FR-022 requires, handed in with the reported quantity
    rather than fetched through a vendor SDK.
    """

    def __init__(
        self, name: str, rows: Sequence[Any], *, source: str
    ) -> None:
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


def cassette_reported_quantity() -> dict[str, Any]:
    """The quantity a completed run reports, and the check over it.

    Cassette-shaped: a count the independent path can recompute. Not a
    model call. The session identity is not invented here — the caller
    already admitted it.
    """
    provenance = Provenance(
        derivation_rule="aggregate_binding",
        source_symbol="list_lots",
        source_file="app.py",
        content_hash=hash_source_construct("list_lots"),
        validation_status=ValidationStatus.VALIDATED,
        validated_against="served_operations.json",
    )
    check = DerivedCheck(
        operation_id="app:list_lots",
        quantity="lot_count",
        check_kind=CheckKind.RECOMPUTATION,
        expression="lot_count == count(lots)",
        recomputation=Recomputation(
            operator="count", over="lots", element_field=None, reads=("lots",)
        ),
        precision_source="aggregate_over:count",
        provenance=provenance,
    )
    contract = DerivedContract(
        operation_id=check.operation_id,
        reads=(),
        writes=(),
        preconditions=(),
        postconditions=(check.expression,),
        failure_taxonomy=(),
        provenance=provenance,
        checks=(check,),
    )
    return {
        "contract": ValidatedContract(
            contract=contract,
            validated_against=(
                "file://tests/fixtures/reference-app/served_operations.json"
            ),
            agreed_on=("part_id",),
            deployment_id="d-reference-app",
        ),
        "check": check,
        "reported": ReportedResult(
            source="cassette answer", payload={"lot_count": 3}
        ),
        "path": _CassettePath(
            "lots",
            [{"unit_cost": 1} for _ in range(3)],
            source="cassette collection (not a deployment)",
        ),
    }


def result_from_answered_quantity(
    *,
    contract: ProvisionalContract | ValidatedContract,
    check: DerivedCheck,
    reported: ReportedResult,
    path: _CassettePath,
) -> Result:
    """Verify one reported quantity from a run and join it to a `Result`.

    This is the only `src/` caller of `verify_quantity` outside `verify.py`,
    and the only `src/` caller of `result_from_report` outside
    `result_join.py`. A request that completed a run reaches this.
    """
    if RESULT_COMES_FROM_TO_RESULT:
        planted = ProvisionalContract(
            contract=contract.contract,
            reason=ProvisionalReason.NO_SPECIFICATION,
            detail=(
                "planted T214 invert: to_result without calling "
                "verify_quantity"
            ),
        )
        return planted.to_result(payload=dict(reported.payload))
    if not VERIFY_IS_CALLED:
        raise AnswerError(
            "verify_quantity was planted off (T214). A Result without a "
            "recomputing check is the defect FR-025 exists to prevent."
        )
    report: VerificationReport = verify_quantity(
        contract=contract, check=check, result=reported, path=path,
    )
    if not JOIN_IS_CALLED:
        raise AnswerError(
            "result_from_report was planted off (T214). The report exists "
            "and no caller-visible record was produced from it."
        )
    return result_from_report(report, payload=dict(reported.payload))


def complete_served_run(
    registry: Registry,
    session_id: str,
    *,
    contract: ProvisionalContract | ValidatedContract | None = None,
    check: DerivedCheck | None = None,
    reported: ReportedResult | None = None,
    path: _CassettePath | None = None,
) -> Result:
    """The run that fills `view.result`. GET /result then returns it.

    `view.result` is no longer permanently `None` for a completed run that
    reported a quantity. Defaults are the cassette-shaped quantity this
    module reports; a test may override the inputs.
    """
    inputs = cassette_reported_quantity()
    record = result_from_answered_quantity(
        contract=inputs["contract"] if contract is None else contract,
        check=inputs["check"] if check is None else check,
        reported=inputs["reported"] if reported is None else reported,
        path=inputs["path"] if path is None else path,
    )
    if RESULT_IS_ATTACHED:
        try:
            registry.attach_result(session_id, record)
        except SurfaceError as exc:
            raise AnswerError(str(exc)) from exc
    return record
