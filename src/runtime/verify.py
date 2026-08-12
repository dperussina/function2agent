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
- **`ProvisionallyVerified`** — the values agreed at a precision the **caller**
  declared (T212). `VERIFIED`, and a distinct type from `Verified` so that
  FR-024 property 5's *"never plain verified"* is held by the taxonomy rather
  than by a flag a consumer can overlook.
- **`Disagreement`** — the recomputation disagreed. `FAILED`.
- **`Refusal`** — no comparison of stated precision could be made, with a named
  reason and the sources consulted. `NOT_VERIFIABLE`.

**FR-025 still has three states and T212 adds no fourth.** The declared rung
adds one route to `VERIFIED` and one to `FAILED` and **no** new route to
`NOT_VERIFIABLE`, so it adds no `RefusalReason` member and cannot disturb the
sum `_check_totals` asserts in `src/runtime/reports/not_verifiable.py`. It can
only ever move a quantity *out* of the not-verifiable population.

`ResultRecord` is **T126 and T127's**, not this module's, and these three are
deliberately not a fourth enum beside `VerificationOutcome`. Each maps onto an
existing member through `outcome()`.

## No tolerance, and where the rest of FR-024 is not

`RecomputationAgreement` compares by exact equality. This module adds nothing
to that and introduces no constant: `tests/unit/test_verify.py::test_no_tolerance_constant_exists_anywhere_in_the_module`
scans this file's identifiers and numeric literals so that the property is a
fact about the source rather than about a review.

⚠️ **What is built here is FR-024's refusal and its caller-declared rung, and
still not FR-024's ladder as an object.** The requirement fixes an **ordered
precision ladder** with six properties. **Five are carried; property 1 is not,
and property 1 is not a task.**

- **Property 1** requires the ladder to be *versioned configuration under
  FR-012, committed before any derivation is written against it* — and the
  ordering is already **inverted**, because `derive.py` writes a
  `precision_source` against a ladder that is not a reviewable artifact. No
  amount of work in this module fixes an ordering that has already happened.
  Its disposition is an owner decision rather than a task: gating it under
  FR-012 means making it an artifact kind first, and `OD-33` declines to mint a
  ninth kind, defers the gating, and expires that deferral at the second
  producer to write a `precision_source`.
- **Property 2** is `derive.py`'s refusal of a numeric `precision_source`.
  Nothing added for T212 weakens it: `DeclaredPrecision.decimal_places` arrives
  from the caller at run time and is not a value this module names.
- **Property 3** — *its last rung MUST be refusal* — is carried **in behaviour
  and not as structure**: an unstated precision does reach refusal, through
  `_admissible_precision`, and what is absent is a ladder object for that
  refusal to be the last rung *of*. T212 moves the refusal one rung further
  down without changing that: the declared rung sits **above** refusal, so
  refusal is still last.
- **Property 4** is `ADMISSIBLE_PRECISION_SOURCES` and the `ConsultedSource`
  constructor below, which now also governs the disclosure — a displacement
  citing a source FR-024 does not admit is refused at construction.
- **Properties 5 and 6** are `verify_declared_quantity` and
  `PrecisionProvenance`, built for **T212** against `OD-23`.

**What property 5 and 6 being carried does not settle**, and it is one step
further in: the properties fix *which artifacts* may state a precision and not
*how one is read out of them*. `_consult_precision` reports both sources it
consults as silent because **nothing in v1 extracts a precision from a
postcondition, an exception class or a published specification** — that is
`tasks.md`'s loose-requirement row 4, narrowed on 2026-08-12 and deliberately
not struck. So the admissibility test below is answerable today in exactly one
direction from a float: no artifact source supplies one, so a declaration is
admitted. The `IGNORED_ARTIFACT_SUPPLIED` branch is **not** dead — an integer
aggregate names its own precision through `check.precision_source`, which is
28 of the 61 entries in `OD-23`'s census — but the branch that would ignore a
declaration because a *postcondition* stated a precision has no producer, and
will not until the extraction is written.

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
    "DeclarationDisposition",
    "DeclaredPrecision",
    "Disagreement",
    "IndependentPath",
    "PathUnavailable",
    "PrecisionProvenance",
    "ProvisionallyVerified",
    "QuantityVerification",
    "Refusal",
    "RefusalReason",
    "ReportedResult",
    "SourcedValue",
    "VerificationError",
    "VerificationReport",
    "recompute",
    "reported_quantity",
    "verify_declared_quantity",
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


# ---------------------------------------------------------------------------
# T212 — FR-024's caller-declared precision rung (properties 5 and 6, `OD-23`).
#
# The rung is a narrow domain and that is the point. It acts on **one** state:
# the ladder about to refuse for want of a stated precision. Everywhere else a
# declaration is ignored, and everywhere it is ignored it is disclosed.


@dataclass(frozen=True)
class DeclaredPrecision:
    """A precision declared in the caller's own request.

    **`declared_in` is required and carries the declaration's source text**,
    because FR-024 property 5 requires the verifier to *"record the declaration
    and its source text as the precision's provenance"*. Without it nothing
    distinguishes a precision the caller asked for from one the agent supplied
    on the caller's behalf — and property 4 is explicit that *"a precision a
    model proposes is not a source, at any rung, under any provenance"*.

    `decimal_places` is **not** a tolerance and admits negative values, which
    is the coarse direction — *to the nearest hundred*. Refusing them would
    make the type quietly incapable of expressing the weakening a caller can
    attempt, and the admissibility test below is what makes that attempt inert
    rather than the type's inability to spell it.
    """

    decimal_places: int
    declared_in: str

    def __post_init__(self) -> None:
        if not isinstance(self.decimal_places, int) or isinstance(
            self.decimal_places, bool
        ):
            raise VerificationError(
                "a declared precision is a number of decimal places, as an "
                f"int; got {type(self.decimal_places).__name__}. A float here "
                "would be a tolerance wearing the name of a place count."
            )
        if not self.declared_in.strip():
            raise VerificationError(
                "a declared precision carries the source text it was declared "
                "in. FR-024 property 5 requires the declaration and its source "
                "text to be recorded as the precision's provenance, and a "
                "precision attributable to nobody is the one thing property 4 "
                "excludes at every rung."
            )


class DeclarationDisposition(Enum):
    """What became of a caller's declaration. Closed, and every case discloses.

    There is no member meaning *nothing happened*: a declaration the verifier
    was handed and did not act on is `IGNORED_ARTIFACT_SUPPLIED` or
    `NOT_REACHED`, and both are disclosures. FR-024 property 5's closing
    sub-bullet — *"an ignored declaration MUST be disclosed on the result, not
    silently dropped"* — is carried by the enum being total rather than by a
    branch remembering to say so.
    """

    #: No artifact source supplied a precision, so the ladder would otherwise
    #: have refused. The declaration was used, and property 6 marks it.
    ADMITTED = "admitted"
    #: An artifact source supplied one. The declaration was ignored — tighter,
    #: equal or looser alike — and the quantity was checked at the artifact
    #: rung, exactly as if the declaration were absent.
    IGNORED_ARTIFACT_SUPPLIED = "ignored_artifact_supplied"
    #: The ladder never reached the precision question: it refused for a reason
    #: no precision answers, or it compared without consulting a source at all.
    #: Distinct from the member above because claiming an artifact displaced the
    #: declaration when none did is finding 007's fabricated provenance
    #: arriving in a disclosure.
    NOT_REACHED = "not_reached"


@dataclass(frozen=True)
class PrecisionProvenance:
    """Where this quantity's precision came from, and what became of the declaration.

    **This is the disclosure, and it rides on the result rather than in a
    trace.** The distinction is not pedantry: FR-058's bounded-result
    disclosure cost this corpus a pass for exactly this, because a reader
    arrives at the result and nowhere else.
    """

    disposition: DeclarationDisposition
    declared: DeclaredPrecision
    #: The artifact source that displaced the declaration. Set on
    #: `IGNORED_ARTIFACT_SUPPLIED` and on nothing else.
    displaced_by: ConsultedSource | None
    detail: str

    def __post_init__(self) -> None:
        ignored = self.disposition is DeclarationDisposition.IGNORED_ARTIFACT_SUPPLIED
        if ignored and self.displaced_by is None:
            raise VerificationError(
                "a declaration reported as ignored names no source that "
                "displaced it. FR-024 property 5 ignores a declaration because "
                "an artifact source supplied a precision instead, and a "
                "disclosure that cannot say which one leaves the caller unable "
                "to tell an artifact rung from a dropped declaration."
            )
        if not ignored and self.displaced_by is not None:
            raise VerificationError(
                f"a {self.disposition.value} declaration names "
                f"{self.displaced_by.artifact_class!r} as having displaced it. "
                "Nothing displaced it — it was admitted, or the ladder never "
                "reached the precision question — and a source cited for a "
                "displacement that did not happen is fabricated provenance."
            )
        if not self.detail.strip():
            raise VerificationError(
                f"a {self.disposition.value} disclosure with no detail is not "
                "actionable. The member says what became of the declaration; "
                "the detail says against what."
            )

    @property
    def is_provisional(self) -> bool:
        """FR-024 property 6's marking, **read off the disposition**.

        Not a stored field. A second field could disagree with the disposition,
        and a marking that disagrees with the reason for it is worse than none
        — it is the shape `Result.provisional` was before T126 replaced it with
        `Corroboration`, where one value meant two different things.
        """
        return self.disposition is DeclarationDisposition.ADMITTED


@dataclass(frozen=True)
class ProvisionallyVerified:
    """The two values agreed at a precision the **caller** declared.

    **A distinct type from `Verified`, and that is property 5's *"never plain
    verified"* held structurally rather than by a flag.** `Verified` is
    `src/analysis/validate.py`'s token and the thing a consumer asks
    `isinstance` about; this is not it, so a caller cannot reach the plain
    state by ignoring a field.

    It could not be `Verified` even if that were wanted:
    `RecomputationAgreement` refuses a float pair by raising, and this rung is
    only ever reached by a float. The type distinction is therefore forced by
    the construction as well as chosen for the requirement.

    `outcome()` is `VERIFIED` because a comparison was made and it agreed —
    FR-025 has three states and *provisionally verified* is not a fourth. What
    keeps it from reading as plain verification is this type and the
    `PrecisionProvenance` that always accompanies it.
    """

    issued_by: ValidatedContract
    check: DerivedCheck
    reported: SourcedValue
    recomputed: SourcedValue
    declared: DeclaredPrecision

    def __post_init__(self) -> None:
        if not isinstance(self.issued_by, ValidatedContract):
            raise VerificationError(
                "ProvisionallyVerified.issued_by must be a ValidatedContract; "
                f"got {type(self.issued_by).__name__}. A provisional contract "
                "can produce NOT_VERIFIABLE and never a verified state of any "
                "kind (constitution Principle I as amended at v1.1.0), and a "
                "caller-declared precision is not a route around it."
            )
        # Spelled through a named local rather than as a bare comparison, and
        # the reason is mechanical rather than stylistic: `Disagreement` above
        # carries the identical condition and that line is a removal-proof
        # target. An exact textual duplicate makes that tamper AMBIGUOUS and
        # the proof unscoreable — which `check_tampers.py` caught the moment
        # this type was added, rather than being noticed later.
        one_retrieval_for_both = self.reported.retrieval == self.recomputed.retrieval
        if one_retrieval_for_both:
            raise VerificationError(
                "the reported and recomputed values both came out of "
                f"{self.reported.retrieval!r}. A declared precision does not "
                "make one retrieval into two paths (FR-022)."
            )

    def outcome(self) -> VerificationOutcome:
        return VerificationOutcome.VERIFIED


VerificationReport = Verified | ProvisionallyVerified | Disagreement | Refusal


@dataclass(frozen=True)
class QuantityVerification:
    """A verified quantity **and** the provenance of the precision it used.

    Both fields are required. A disclosure a consumer can read the outcome
    without is one a consumer will read the outcome without, so there is no
    value of this type that carries an outcome and no disposition.
    """

    report: VerificationReport
    precision: PrecisionProvenance

    def outcome(self) -> VerificationOutcome:
        return self.report.outcome()


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


def _obtain(
    contract: ProvisionalContract | ValidatedContract,
    check: DerivedCheck,
    result: ReportedResult,
    path: IndependentPath,
) -> Refusal | tuple[ValidatedContract, SourcedValue, SourcedValue]:
    """Everything up to the precision question, shared by both entry points.

    **Extracted for T212 rather than duplicated**, so that FR-024 property 5's
    *"the ladder MUST proceed exactly as if the declaration were absent"* is
    the same code and not two copies that can drift. It returns the narrowed
    contract with the pair, because the caller needs the narrowing and a
    second `isinstance` would be a second place to get it wrong.
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

    return contract, reported, recomputed


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

    **There is no parameter here for a caller-declared precision, and that is
    deliberate** (T212). A declaration carries a disclosure obligation under
    FR-024 property 5, and this function's return type has nowhere to put one —
    so a caller holding a declaration cannot hand it to a function that would
    silently drop it. `verify_declared_quantity` is the entry point that takes
    one, and it returns a record that cannot omit the disclosure.
    """
    obtained = _obtain(contract, check, result, path)
    if isinstance(obtained, Refusal):
        return obtained
    validated, reported, recomputed = obtained

    refusal = _admissible_precision(check, validated, reported, recomputed)
    if refusal is not None:
        return refusal

    try:
        agreement = RecomputationAgreement(
            reported=reported.value, recomputed=recomputed.value
        )
    except ValidationError as exc:
        return Disagreement(reported=reported, recomputed=recomputed, detail=str(exc))

    return validated.verified(check, agreement)


def _artifact_supplied_precision(check: DerivedCheck) -> ConsultedSource | None:
    """The artifact source that states this quantity's precision, or `None`.

    **A precision is stated when it is attributable to a named source
    artifact** — FR-024's own pin. So this asks the check whether its
    derivation named one, and reports `check.precision_source` as what that
    source supplied. It does not compute a precision and it does not name a
    number: property 2 forbids any rung naming a numeric value, and
    `derive.py` already refuses a numeric `precision_source` on that ground.

    Returning `None` where the check names nothing is not a gap being papered
    over. It is the state FR-024 calls silence, and the caller of this function
    turns it into a disposition rather than into a precision.
    """
    if check.precision_source is None:
        return None
    return ConsultedSource(
        artifact_class=check.provenance.rule.reads,
        supplied=check.precision_source,
        detail=(
            f"rule {check.provenance.derivation_rule!r} read "
            f"{check.provenance.source_symbol!r} and derived "
            f"{check.precision_source!r}, which the ladder compares at "
            "exactly. FR-024 property 5 ignores a caller's declaration "
            "wherever an artifact source supplies a precision — tighter, "
            "equal or looser alike."
        ),
    )


def _compare_at(
    reported: SourcedValue, recomputed: SourcedValue, declared: DeclaredPrecision
) -> bool:
    """The two values at the precision the caller declared.

    `round` to the declared number of places and compare exactly. **No constant
    is written here and none is derivable from here**: the number of places
    arrives from the caller at run time, which is what makes this a *source*
    under property 2 rather than the default tolerance FR-024 exists to forbid.
    """
    reported_at_declared = round(reported.value, declared.decimal_places)
    recomputed_at_declared = round(recomputed.value, declared.decimal_places)
    return reported_at_declared == recomputed_at_declared


def verify_declared_quantity(
    *,
    contract: ProvisionalContract | ValidatedContract,
    check: DerivedCheck,
    result: ReportedResult,
    path: IndependentPath,
    declared: DeclaredPrecision,
) -> QuantityVerification:
    """FR-024's caller-declared rung. **The admissibility test runs first.**

    > A precision declared in the caller's own request is admissible only where
    > no artifact source supplies any precision for that quantity at all — that
    > is, only where the ladder would otherwise refuse. (property 5, `OD-23`)

    So this is not `verify_quantity` with an extra argument, and the separate
    entry point is the mechanism rather than a naming choice: it returns a
    `QuantityVerification`, which **cannot be constructed without the
    disclosure**. A caller holding a declaration has nowhere to put it on
    `verify_quantity`, and a caller receiving an answer from here cannot read
    the outcome without the disposition being present on the same object.

    The rung acts on exactly one state — a `PRECISION_NOT_STATED` refusal — and
    everywhere else the ladder proceeds **as if the declaration were absent**,
    which is literal here rather than aspirational: the same `_obtain` and the
    same `_admissible_precision` run, and their results are used unchanged.
    """
    obtained = _obtain(contract, check, result, path)
    if isinstance(obtained, Refusal):
        return QuantityVerification(
            report=obtained,
            precision=PrecisionProvenance(
                disposition=DeclarationDisposition.NOT_REACHED,
                declared=declared,
                displaced_by=None,
                detail=(
                    f"the ladder refused at {obtained.reason.value} before any "
                    "precision was consulted, so the declaration was neither "
                    "used nor displaced. A declared precision answers the "
                    "question *how close is close enough*; it does not supply "
                    "a quantity, a collection or a contract."
                ),
            ),
        )

    validated, reported, recomputed = obtained
    refusal = _admissible_precision(check, validated, reported, recomputed)

    if refusal is not None and refusal.reason is RefusalReason.PRECISION_NOT_STATED:
        # The one state this rung acts on: no artifact source supplies a
        # precision, so the ladder would otherwise refuse. Property 5's
        # *"only circumstance in which a declaration converts what would
        # otherwise be a refusal into a checked quantity"*.
        # The consulted list is obtained from `_consult_precision` rather than
        # read off `refusal.consulted`, and the difference is not cosmetic: it
        # keeps this branch from dereferencing the refusal object at all. With
        # the dereference in place, the removal proof that drops the
        # admissibility test crashed on a `NoneType` instead of reaching the
        # comparison — an arm that scores because a tamper broke something
        # incidental proves nothing about the mechanism it names.
        consulted = _consult_precision(check, validated)
        provenance = PrecisionProvenance(
            disposition=DeclarationDisposition.ADMITTED,
            declared=declared,
            displaced_by=None,
            detail=(
                f"{check.operation_id}/{check.quantity}: every source "
                "consulted was silent — "
                f"{[entry.artifact_class for entry in consulted]} — so "
                "the ladder would otherwise have refused. The declaration in "
                f"{declared.declared_in!r} is admitted and the verification is "
                "provisional on its own provenance (FR-024 property 6): no "
                "independent artifact exists to validate this precision "
                "against, which is this rung's own admissibility premise."
            ),
        )
        if _compare_at(reported, recomputed, declared):
            return QuantityVerification(
                report=ProvisionallyVerified(
                    issued_by=validated,
                    check=check,
                    reported=reported,
                    recomputed=recomputed,
                    declared=declared,
                ),
                precision=provenance,
            )
        return QuantityVerification(
            report=Disagreement(
                reported=reported,
                recomputed=recomputed,
                detail=(
                    f"{check.operation_id}/{check.quantity}: the reported "
                    f"{reported.value!r} and the independently recomputed "
                    f"{recomputed.value!r} differ at the precision declared in "
                    f"{declared.declared_in!r}. The comparison was made at the "
                    "caller's declared precision because no artifact source "
                    "supplies one (FR-024 property 5); without this rung the "
                    "quantity refuses and the difference is neither detected "
                    "nor missed."
                ),
            ),
            precision=provenance,
        )

    if refusal is not None:
        return QuantityVerification(
            report=refusal,
            precision=PrecisionProvenance(
                disposition=DeclarationDisposition.NOT_REACHED,
                declared=declared,
                displaced_by=None,
                detail=(
                    f"the ladder refused at {refusal.reason.value}, which no "
                    "precision answers. Declaring how close is close enough "
                    "does not make a quantity a magnitude."
                ),
            ),
        )

    # No refusal: the ladder compares. Whatever precision that comparison rests
    # on came from an artifact, so the declaration is ignored — and disclosed.
    displaced_by = _artifact_supplied_precision(check)
    if displaced_by is None:
        provenance = PrecisionProvenance(
            disposition=DeclarationDisposition.NOT_REACHED,
            declared=declared,
            displaced_by=None,
            detail=(
                f"{check.operation_id}/{check.quantity}: the ladder compared "
                "without consulting any source, because this check names no "
                "`precision_source`. Nothing displaced the declaration by "
                "name, so nothing is cited as having done so — but the "
                "comparison made is exact equality, which is stricter than any "
                "declaration could ask for. **Not reachable from `derive.py`**, "
                "which sets a `precision_source` on every recomputation check "
                "it emits; a check reaching here was built by hand."
            ),
        )
    else:
        provenance = PrecisionProvenance(
            disposition=DeclarationDisposition.IGNORED_ARTIFACT_SUPPLIED,
            declared=declared,
            displaced_by=displaced_by,
            detail=(
                f"{check.operation_id}/{check.quantity}: "
                f"{displaced_by.artifact_class} supplies "
                f"{displaced_by.supplied!r}, so the declaration in "
                f"{declared.declared_in!r} was ignored and the quantity was "
                "checked at the artifact rung. A caller-declared precision may "
                "never be the reason a quantity is checked less strictly than "
                "an artifact source permits (FR-024 property 5)."
            ),
        )

    try:
        agreement = RecomputationAgreement(
            reported=reported.value, recomputed=recomputed.value
        )
    except ValidationError as exc:
        return QuantityVerification(
            report=Disagreement(
                reported=reported, recomputed=recomputed, detail=str(exc)
            ),
            precision=provenance,
        )

    return QuantityVerification(
        report=validated.verified(check, agreement), precision=provenance
    )
