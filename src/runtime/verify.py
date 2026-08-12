"""T124 and T125 — the recomputing verifier, and its named refusals.

**Requirements.**

> **FR-022**: For every reported result, the verifier MUST attempt to recompute
> the reported quantity by a path independent of the one that produced it.
> Conformance of the request or the response to a declared shape MUST NOT by
> itself be accepted as verification; the failure class that matters is
> conformant end to end and wrong.

> **FR-024**: Where no check of stated precision can be derived for a quantity,
> the verifier MUST refuse rather than fall back to a default tolerance, and
> MUST name the reason for the refusal. […] When a quantity's applicable rung is
> the refusal rung, the verifier MUST refuse and MUST name **which sources were
> consulted and found silent**, not merely that it refused.

## What "an independent path" concretely is here

It is **a second retrieval from the target's own API**, and the independence is
held in three places rather than asserted in one:

1. **`recompute` is not given the reported result.** Its parameters are the
   check and the path, and there is no argument by which the value under check
   could reach the code that recomputes it. Symmetrically,
   `reported_quantity` is not given the path.
2. **The two values carry the retrieval they came out of**, and
   `verify_quantity` refuses when those are equal. Reading two fields out of one
   response is not two paths.
3. **The check itself may not read the quantity it recomputes.**
   `DerivedCheck.__post_init__` refuses that at construction (T120), and
   `tests/contract/test_independent_derivation.py` asserts it over the checks
   the committed fixtures really derive.

The first is the one that matters, because the other two are checks on labels
and a label comparison is exactly the shape check FR-022 says is not
verification. T129's load-bearing arm is therefore **behavioural**: it moves the
reported value across seven plants and asserts the recomputed value does not
move, with a deliberately dependent path as the negative control over that arm.

## Three outcomes, and a disagreement is one of them

`src/analysis/validate.py` holds `RecomputationAgreement`, which carries the two
values and compares them itself, and in which a *disagreement is deliberately
unrepresentable* — it is a result rather than a construction. This module is
where that result is produced:

- **`Verified`** — validate.py's token, reachable only from a `ValidatedContract`
  and a check that recomputes.
- **`Disagreement`** — the recomputation disagreed. `FAILED`.
- **`Refusal`** — no comparison of stated precision could be made, with a named
  reason and the sources consulted. `NOT_VERIFIABLE`.

`ResultRecord` is **T126 and T127's**, not this module's, and these three are
deliberately not a fourth enum beside `VerificationOutcome`. Each maps onto an
existing member through `outcome()`.

## No tolerance, and where the rest of FR-024 is not

`RecomputationAgreement` compares by exact equality. This module adds nothing
to that and introduces no constant: `tests/unit/test_verify.py::test_no_tolerance_constant_exists_anywhere_in_the_module`
scans this file's identifiers and numeric literals so that the property is a
fact about the source rather than about a review.

⚠️ **What is built here is FR-024's refusal, and not FR-024's ladder.** The
requirement also fixes an **ordered precision ladder** with six properties, and
**three** of them are discharged by nothing here: properties **1, 5 and 6**.

- **Property 1** requires the ladder to be *versioned configuration under
  FR-012, committed before any derivation is written against it* — and the
  ordering is already inverted, because `derive.py` writes a `precision_source`
  against a ladder that is not a reviewable artifact. Its disposition is an
  owner decision rather than a task: gating it under FR-012 means making it an
  artifact kind first, and `OD-33` declines to mint a ninth kind, defers the
  gating, and expires that deferral at the second producer to write a
  `precision_source`.
- **Properties 5 and 6** govern the caller-declared rung — admissible only where
  no artifact source supplies a precision, and provisional wherever admitted.
  They are carried by `T212`, which is `OD-23`'s task.

**Properties 2, 3 and 4 are carried.** Property 2 is `derive.py`'s refusal of a
numeric `precision_source`; property 4 is `ADMISSIBLE_PRECISION_SOURCES` and the
`ConsultedSource` constructor below. Property 3 — *its last rung MUST be
refusal* — is carried **in behaviour and not as structure**: an unstated
precision does reach refusal, through `_admissible_precision`, and what is
absent is a ladder object for that refusal to be the last rung *of*. An earlier
revision of this paragraph counted property 3 among the undischarged and then
conceded its behaviour two sentences later; the census was redone
property-by-property on 2026-08-12 and this is its result.

## Why the verified path is exercised but never with both halves real

No committed artifact supplies a real derivation and a real deployment for one
quantity. `derive_module` walks module-level functions and the reference
application's operations are methods on `Application`, so `app.py` derives only
shape checks; the analyzer fixture derives three real recomputations over a
collection called `lots` that nothing serves. And the one real published
specification in the tree, `served_operations.json`, declares no parameters, so
`validate_contract` correctly reads it as silent and promotes nothing. Each of
those three is asserted rather than described — see T124's note in `tasks.md`
for the unexercised half stated as a partial.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Protocol, Sequence

from src.analysis.derive import DerivedCheck, Recomputation
from src.analysis.provenance import FR_023_ARTIFACT_CLASSES
from src.analysis.validate import (
    ProvisionalContract,
    RecomputationAgreement,
    ValidatedContract,
    ValidationError,
    Verified,
)
from src.contracts.result import VerificationOutcome

__all__ = [
    "ADMISSIBLE_PRECISION_SOURCES",
    "ConsultedSource",
    "Disagreement",
    "IndependentPath",
    "PathUnavailable",
    "Refusal",
    "RefusalReason",
    "ReportedResult",
    "SourcedValue",
    "VerificationError",
    "VerificationReport",
    "recompute",
    "reported_quantity",
    "verify_quantity",
]


class VerificationError(ValueError):
    """A verification this module refuses to perform.

    Distinct from every outcome below, and the distinction is the point: an
    outcome is something the target did, and this is something the caller did.
    Folding a caller's mistake into `NOT_VERIFIABLE` would put it in T130's
    per-reason report as though the deployment had been silent.
    """


class PathUnavailable(Exception):
    """An independent path could not supply what a recomputation names.

    Raised by the path, never by this module, and always turned into a named
    refusal rather than propagated: a target that cannot be re-read is a
    not-verifiable result and not a crash.
    """


class IndependentPath(Protocol):
    """The target's own API, reached a second time.

    **There is no method here that takes a reported result, and that is
    deliberate.** FR-022's independence is held as a signature rather than as a
    convention: an implementation cannot read the value under check, because
    nothing hands it one.
    """

    def source(self) -> str:
        """The retrieval this path performs, as an identity two values compare on."""

    def collection(self, name: str) -> Sequence[Any]:
        """The named collection, freshly retrieved. Raises `PathUnavailable`."""


#: FR-024 property 4 — *"its admissible sources are exactly the artifact
#: classes FR-023 permits […] together with the target's published
#: specification"*. Assembled from `FR_023_ARTIFACT_CLASSES` rather than
#: retyped, so a change to FR-023's set cannot leave two lists disagreeing.
ADMISSIBLE_PRECISION_SOURCES = FR_023_ARTIFACT_CLASSES | {"published_specification"}


@dataclass(frozen=True)
class SourcedValue:
    """A value and the retrieval it came out of.

    `retrieval` is the identity two values are compared on for independence.
    `field` is what was read from it. They are separate fields rather than one
    string because the question *"did these come from the same retrieval"* must
    not be answerable differently depending on which field was read.
    """

    value: Any
    retrieval: str
    field: str

    @property
    def source(self) -> str:
        return f"{self.retrieval}#{self.field}"


@dataclass(frozen=True)
class ConsultedSource:
    """One source a refusal looked at, and what it supplied.

    `supplied is None` means **silent**, which is the state FR-024's closing
    sentence requires be named. A refusal listing no consulted source is
    indistinguishable from one that looked at nothing, so `Refusal` requires
    at least one.
    """

    artifact_class: str
    supplied: str | None
    detail: str

    def __post_init__(self) -> None:
        if self.artifact_class not in ADMISSIBLE_PRECISION_SOURCES:
            raise VerificationError(
                f"{self.artifact_class!r} is not an admissible source of "
                "precision. FR-024 property 4 fixes them as FR-023's artifact "
                "classes together with the published specification: "
                f"{sorted(ADMISSIBLE_PRECISION_SOURCES)}. A source outside "
                "that set was invented rather than consulted."
            )


class RefusalReason(Enum):
    """Why no verification was performed. Closed, and each member is a fact.

    Named members rather than a string, for the reason `ProvisionalReason` is
    one level up: T130 reports the **share of results in the not-verifiable
    state broken down by these reasons**, and a free-form string cannot be
    grouped into a breakdown.
    """

    #: T123 — a provisional contract can produce this and never VERIFIED.
    CONTRACT_PROVISIONAL = "contract_provisional"
    #: The check is `shape`. FR-022 refuses conformance as verification.
    NO_RECOMPUTING_CHECK = "no_recomputing_check"
    #: The reported result carries no such quantity, so nothing was reported to
    #: check. Distinct from a disagreement: nothing was claimed.
    QUANTITY_ABSENT_FROM_RESULT = "quantity_absent_from_result"
    #: A boolean where a magnitude was expected. `True == 1` in Python, so this
    #: would otherwise agree with a count of one.
    QUANTITY_NOT_A_MAGNITUDE = "quantity_not_a_magnitude"
    #: The independent path could not supply the collection to recompute over.
    COLLECTION_UNAVAILABLE = "collection_unavailable"
    #: FR-024's own case. No source supplies a precision for this quantity, so
    #: there is no check of *stated* precision to make, and exact equality over
    #: a float is a comparison whose precision nobody stated.
    PRECISION_NOT_STATED = "precision_not_stated"
    #: The two values came out of one retrieval, so the comparison is an
    #: identity. FR-022's independence, refused rather than performed.
    SOURCES_NOT_INDEPENDENT = "sources_not_independent"


@dataclass(frozen=True)
class Refusal:
    """No comparison was made, with a reason and what was consulted."""

    reason: RefusalReason
    detail: str
    consulted: tuple[ConsultedSource, ...]

    def __post_init__(self) -> None:
        if not self.detail.strip():
            raise VerificationError(
                f"a {self.reason.value} refusal with no detail is not "
                "diagnosable after the fact. The member says which kind of "
                "silence it was; the detail says what was looked for."
            )
        if not self.consulted:
            raise VerificationError(
                f"a {self.reason.value} refusal names no consulted source. "
                "FR-024 requires a refusal to name which sources were "
                "consulted and found silent, not merely that it refused — and "
                "a refusal that consulted nothing is indistinguishable from "
                "nobody having tried."
            )

    @property
    def silent_sources(self) -> tuple[ConsultedSource, ...]:
        return tuple(entry for entry in self.consulted if entry.supplied is None)

    def outcome(self) -> VerificationOutcome:
        return VerificationOutcome.NOT_VERIFIABLE


@dataclass(frozen=True)
class Disagreement:
    """The recomputation disagreed with what was reported.

    Both values are carried with their retrievals, because *"they disagreed"*
    with no operands is a claim nobody can check and nobody can triage.
    """

    reported: SourcedValue
    recomputed: SourcedValue
    detail: str

    def __post_init__(self) -> None:
        if self.reported.retrieval == self.recomputed.retrieval:
            raise VerificationError(
                "a disagreement between two values out of the same retrieval "
                f"({self.reported.retrieval!r}) is not a disagreement about "
                "the target — it is a defect in the verifier. FR-022 requires "
                "the recomputation to come by an independent path."
            )

    def outcome(self) -> VerificationOutcome:
        return VerificationOutcome.FAILED


@dataclass(frozen=True)
class ReportedResult:
    """What the producing path returned, and which path produced it.

    `source` is required and has no default. It is the retrieval identity the
    independence comparison is made on, and a default would make two values
    from one response compare as independent by omission.
    """

    source: str
    payload: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not self.source.strip():
            raise VerificationError(
                "a reported result names the path that produced it. Without "
                "it the independence comparison FR-022 requires has nothing to "
                "compare, and an unnamed source would pass it by omission."
            )


VerificationReport = Verified | Disagreement | Refusal


# ---------------------------------------------------------------------------
# The two halves. Neither is given the other's input, and
# `tests/contract/test_independent_derivation.py` asserts that over the
# signatures so a later edit cannot quietly wire them together.


def reported_quantity(
    result: ReportedResult, check: DerivedCheck
) -> SourcedValue | Refusal:
    """The reported value, read out of the result. **No path parameter.**"""
    if check.quantity not in result.payload:
        return Refusal(
            reason=RefusalReason.QUANTITY_ABSENT_FROM_RESULT,
            detail=(
                f"{check.operation_id}/{check.quantity}: the reported result "
                f"from {result.source!r} carries "
                f"{sorted(result.payload)} and no {check.quantity!r}. Nothing "
                "was claimed about this quantity, which is a different fact "
                "from a claim that disagrees."
            ),
            consulted=(
                ConsultedSource(
                    artifact_class="observable_state",
                    supplied=None,
                    detail=(
                        f"the reported result from {result.source!r}, which "
                        "does not carry the quantity"
                    ),
                ),
            ),
        )
    return SourcedValue(
        value=result.payload[check.quantity],
        retrieval=result.source,
        field=check.quantity,
    )


def recompute(check: DerivedCheck, path: IndependentPath) -> SourcedValue | Refusal:
    """The recomputed value, obtained from the target. **No result parameter.**

    This is the whole of FR-022's independent path: it retrieves the collection
    the check names and applies the aggregate the check carries. It cannot read
    the reported number, because nothing gives it one.
    """
    if not check.recomputes() or check.recomputation is None:
        return Refusal(
            reason=RefusalReason.NO_RECOMPUTING_CHECK,
            detail=(
                f"{check.operation_id}/{check.quantity}: this check is "
                f"`{check.check_kind.value}` and carries no recomputation, so "
                "there is no second path to run. Conformance of the response "
                "to a declared shape is explicitly not accepted as "
                "verification (FR-022) — the failure class that matters is "
                "conformant end to end and wrong."
            ),
            consulted=(
                ConsultedSource(
                    artifact_class="postcondition",
                    supplied=None,
                    detail=(
                        "no postcondition or aggregate binding was derived for "
                        f"{check.quantity!r}, so no independent path exists"
                    ),
                ),
            ),
        )

    plan = check.recomputation
    try:
        rows = path.collection(plan.over)
        value = _apply(plan, rows)
    except PathUnavailable as exc:
        return Refusal(
            reason=RefusalReason.COLLECTION_UNAVAILABLE,
            detail=(
                f"{check.operation_id}/{check.quantity}: the recomputation is "
                f"{plan.operator} over {plan.over!r} and the independent path "
                f"{path.source()!r} could not supply it: {exc}"
            ),
            consulted=(
                ConsultedSource(
                    artifact_class="observable_state",
                    supplied=None,
                    detail=f"{path.source()}, which serves no {plan.over!r}",
                ),
            ),
        )

    return SourcedValue(value=value, retrieval=path.source(), field=plan.over)


def _element(row: Any, name: str, over: str) -> Any:
    """One element's field, by the two accesses `derive.py` recognises."""
    if isinstance(row, Mapping):
        if name not in row:
            raise PathUnavailable(
                f"an element of {over!r} carries {sorted(row)} and no {name!r}"
            )
        return row[name]
    if hasattr(row, name):
        return getattr(row, name)
    raise PathUnavailable(
        f"an element of {over!r} is a {type(row).__name__} with no {name!r}"
    )


def _apply(plan: Recomputation, rows: Sequence[Any]) -> Any:
    """Execute the aggregate. Structured data, never a parsed expression."""
    if plan.operator == "count":
        return len(rows)

    if plan.element_field is None:
        values = list(rows)
    else:
        values = [_element(row, plan.element_field, plan.over) for row in rows]

    if not values:
        raise PathUnavailable(
            f"{plan.operator} over an empty {plan.over!r} has no value. An "
            "empty aggregate is not zero and substituting one would "
            "manufacture a comparison."
        )
    if plan.operator == "sum":
        return sum(values)
    if plan.operator == "min":
        return min(values)
    if plan.operator == "max":
        return max(values)
    raise PathUnavailable(
        f"{plan.operator!r} is not an aggregate this verifier can execute. "
        "`Recomputation` admits it, so the two have drifted apart."
    )


def _consult_precision(
    check: DerivedCheck, contract: ValidatedContract
) -> tuple[ConsultedSource, ...]:
    """The sources looked at for a stated precision, and what each supplied.

    Exactly the two that are in hand, rather than a recital of all nine
    admissible classes: the class this check's own derivation rule reads, and
    the published specification the contract was promoted against. A refusal
    listing sources nobody consulted is the fabricated-provenance defect
    finding 007 measured, arriving in a refusal instead of in a contract.
    """
    rule = check.provenance.rule
    return (
        ConsultedSource(
            artifact_class=rule.reads,
            supplied=None,
            detail=(
                f"rule {check.provenance.derivation_rule!r} read "
                f"{check.provenance.source_symbol!r} and derived "
                f"{check.precision_source!r}, which names an aggregate and no "
                "precision. An aggregate is exact over integers and states "
                "nothing about a float."
            ),
        ),
        ConsultedSource(
            artifact_class="published_specification",
            supplied=None,
            detail=(
                f"{contract.validated_against}, which declares no precision "
                "for any quantity. Nothing in v1 reads one out of a published "
                "specification."
            ),
        ),
    )


def _admissible_precision(
    check: DerivedCheck,
    contract: ValidatedContract,
    reported: SourcedValue,
    recomputed: SourcedValue,
) -> Refusal | None:
    """FR-024, applied before any comparison. Returns `None` where one may be made.

    **This runs before `RecomputationAgreement`, and that ordering is the
    mechanism rather than an optimisation.** `RecomputationAgreement` also
    refuses a float and a bool, and it refuses them by raising — which this
    module turns into a `Disagreement`. So without this function a quantity
    with no stated precision is reported as a **failure** rather than refused,
    which is a false alarm where FR-024 requires an honest not-verifiable, and
    the result carries no list of consulted sources at all.
    """
    for label, sourced in (("reported", reported), ("recomputed", recomputed)):
        if isinstance(sourced.value, bool):
            return Refusal(
                reason=RefusalReason.QUANTITY_NOT_A_MAGNITUDE,
                detail=(
                    f"{check.operation_id}/{check.quantity}: the {label} value "
                    f"is the bool {sourced.value!r}, from {sourced.source!r}. "
                    "`True == 1` in Python, so comparing it against a count of "
                    "one would agree with it."
                ),
                consulted=_consult_precision(check, contract),
            )

    for label, sourced in (("reported", reported), ("recomputed", recomputed)):
        if isinstance(sourced.value, float):
            return Refusal(
                reason=RefusalReason.PRECISION_NOT_STATED,
                detail=(
                    f"{check.operation_id}/{check.quantity}: the {label} value "
                    f"is the float {sourced.value!r}, from {sourced.source!r}, "
                    "and no source consulted states a precision for it. "
                    "Refused rather than compared under a default tolerance "
                    "nobody chose (FR-024) — exact equality over floats would "
                    "sometimes pass, and a comparison that passes by accident "
                    "reads as verification."
                ),
                consulted=_consult_precision(check, contract),
            )

    return None


def verify_quantity(
    *,
    contract: ProvisionalContract | ValidatedContract,
    check: DerivedCheck,
    result: ReportedResult,
    path: IndependentPath,
) -> VerificationReport:
    """Verify one reported quantity, or say why it was not verified.

    The join between `contract` and `check` is **declared and never inferred**,
    on T122's reasoning one level up: a check from another contract is refused
    rather than run.
    """
    if check.operation_id != contract.contract.operation_id:
        raise VerificationError(
            f"check {check.operation_id}/{check.quantity} does not belong to "
            f"contract {contract.contract.operation_id}. A join between two "
            "derived artifacts is a declaration; guessing one is how a "
            "contract wrong about every field on the wire arrives looking "
            "fluent and plausible."
        )

    if isinstance(contract, ProvisionalContract):
        outcome = contract.not_verifiable()
        return Refusal(
            reason=RefusalReason.CONTRACT_PROVISIONAL,
            detail=(
                f"{check.operation_id}/{check.quantity}: {outcome.reason} A "
                "provisional contract can produce NOT_VERIFIABLE and never "
                "VERIFIED (constitution Principle I as amended at v1.1.0). "
                "Recomputing against it would produce a number nothing "
                "corroborates."
            ),
            consulted=(
                ConsultedSource(
                    artifact_class="published_specification",
                    supplied=None,
                    detail=(
                        "none was in hand when this contract was validated, "
                        f"which is why it is provisional: {contract.reason.value}"
                    ),
                ),
            ),
        )

    reported = reported_quantity(result, check)
    if isinstance(reported, Refusal):
        return reported

    recomputed = recompute(check, path)
    if isinstance(recomputed, Refusal):
        return recomputed

    if reported.retrieval == recomputed.retrieval:
        return Refusal(
            reason=RefusalReason.SOURCES_NOT_INDEPENDENT,
            detail=(
                f"{check.operation_id}/{check.quantity}: the reported value "
                f"and the recomputed value both came out of "
                f"{reported.retrieval!r}. Reading two fields out of one "
                "response is not two paths, and comparing them is an identity "
                "that agrees whatever the value is (FR-022)."
            ),
            consulted=(
                ConsultedSource(
                    artifact_class="observable_state",
                    supplied=reported.retrieval,
                    detail=(
                        "one retrieval was offered as both the reported and "
                        "the independent source"
                    ),
                ),
            ),
        )

    refusal = _admissible_precision(check, contract, reported, recomputed)
    if refusal is not None:
        return refusal

    try:
        agreement = RecomputationAgreement(
            reported=reported.value, recomputed=recomputed.value
        )
    except ValidationError as exc:
        return Disagreement(reported=reported, recomputed=recomputed, detail=str(exc))

    return contract.verified(check, agreement)
