"""T213 — the verification seam: a `VerificationReport` becomes a `Result`.

**Requirement**: FR-025. **Decision**: `OD-34`.

Until this module existed the verifier and the caller-visible record were both
built, both closed, and joined by nothing — measured rather than read off a
task list, and recorded at `OD-34`: `verify_quantity` and
`verify_declared_quantity` appeared nowhere in `src/` outside their own module,
and `Result` was constructed at exactly two sites, both inside a `to_result`
method in `src/analysis/validate.py`. No verification *outcome* reached a
caller-visible record.

## Why the join is here and not in `to_result`

`OD-34` forecloses the obvious repair and the foreclosure is measured:
`src/runtime/verify.py` imports `src/analysis/validate`, and nothing under
`src/analysis/` imports `src/runtime/` at all. A call from `to_result` into the
verifier would invert the layering `tests/invariants/test_layering.py` and
`test_import_graph.py` enforce, and would be a load-time cycle. `src/runtime/`
already imports `src/analysis/`, so a module here may hold a
`VerificationReport` and a `Result` simultaneously without inverting anything.

`OD-34` ② also declines the other legal route — putting the join in
`verify.py`, which already imports `VerificationOutcome` — because it would
make the module that performs a verification also the module that constructs
the caller-visible record of it, with no independent step between them.

## The mapping, and which arms were free

`VerificationReport` is a four-member union and `Result` takes a
`VerificationOutcome`, a `Corroboration` **and**, since `OD-35`, a `Precision`,
so this is a map into a product and not a rename:

| report                  | outcome          | corroboration | precision    | fixed by |
| ----------------------- | ---------------- | ------------- | ------------ | -------- |
| `Verified`              | `VERIFIED`       | `CORROBORATED`| `NOT_STATED` | `OD-34`  |
| `ProvisionallyVerified` | `VERIFIED`       | `CORROBORATED`| `DECLARED`   | `OD-35`  |
| `Disagreement`          | `FAILED`         | `NOT_STATED`  | `NOT_STATED` | here     |
| `Refusal`               | `NOT_VERIFIABLE` | *by reason*   | `NOT_STATED` | here     |

`Verified`'s `NOT_STATED` precision is not an oversight and is the whole force
of the third column being separate: `Verified` carries a `ValidatedContract` and
a `RecomputationAgreement` and **nothing about where its precision came from**,
so the honest value is *nobody said*. A caller who wants that answered reaches
`result_from_quantity_verification`, which holds a `PrecisionProvenance` and can
say.

**The corroboration column is fixed by `OD-34` for the first two rows only**,
and the rule this module applies to the other two is stated rather than
improvised: *the join claims corroboration only where the report object itself
carries the contract that earns it.* `Verified` and `ProvisionallyVerified`
both carry `issued_by: ValidatedContract` — a contract *"the published
specification agreed with"*, which is what `Corroboration.CORROBORATED` names.
`Disagreement` and `Refusal` carry no contract at all, so a join asserting
`CORROBORATED` for them would be stating a fact it cannot read off its own
input. `NOT_STATED` is the member that exists for exactly that: *nobody said*,
which is a different claim from *nothing corroborated it*.

The one refusal that can say more is `CONTRACT_PROVISIONAL`, which is produced
only where the contract was a `ProvisionalContract`. `REFUSAL_CORROBORATION`
maps it to `PROVISIONAL`, which makes this module agree with
`ProvisionalContract.to_result` rather than merely not contradict it —
`test_the_join_agrees_with_the_bridge_validate_py_already_had` asserts that over
both bridges as records, not as prose.

✅ **The `ProvisionallyVerified` row was `OD-34` ③'s and is now `OD-35`'s, and
neither of the two original readings was right.** ③ fixed it at
`NOT_VERIFIABLE`/`PROVISIONAL`; T212 ruled that *"'Provisional' is NOT
`Corroboration`"* because `Corroboration`'s subject is the **contract** —
necessarily a `ValidatedContract` here, since
`ProvisionallyVerified.__post_init__` refuses anything else — where property 6
marks the **precision**. T212 was right about the subject and `OD-35` adopts it.
But the correction ③'s refutation implies, `VERIFIED`/`CORROBORATED`, produces a
record that is *plain verified*, which FR-024 property 5 forbids in as many
words. With the fields `Result` had, the two requirements had no common
solution. `OD-35` mints the third column above, and the row becomes true about
the contract **and** distinguishable from a plain verification at the record.
`test_the_two_readings_of_a_provisionally_verified_report_are_reconciled` pins
all three cells and the reason, so a pass reverting to either original row fails
and has to say which reading it took.

## `MODEL_ASSESSED` has no source here and must not acquire one

Nothing in `verify.py` produces it, and a join that could emit it would be
constitution Principle I's boundary crossed at the one point built to hold it.
`JOINABLE_OUTCOMES` is computed by **subtracting** it from the enum rather than
by listing the other three, so a fifth member added later is joinable-by-default
and only `MODEL_ASSESSED` is excluded by name; `_refuse_unjoinable` is the
runtime backstop, and `tests/invariants/test_result_constructor.py` reads the
image of the map so the exclusion is a property of the table rather than of a
branch nobody exercised.

## The disclosure a `QuantityVerification` carries, and why it is not optional

`verify_declared_quantity` returns a `QuantityVerification` — a report **and** a
`PrecisionProvenance` — because FR-024 property 5 requires that *"an ignored
declaration MUST be disclosed on the result, not silently dropped"*. A join that
took `qv.report` and threw the provenance away would perform that silent drop at
the precise moment the record becomes caller-visible, which is the FR-058
distinction T212 was careful about: a disclosure in a trace does not discharge a
disclosure on the result. `result_from_quantity_verification` is therefore a
separate entry point that carries the disposition onto the record, and it is the
only way to turn a `QuantityVerification` into one.

It carries it **twice**, and the redundancy is deliberate rather than left over:
into `Result.precision` as a member a consumer can key on, and into
`Result.reason` as the detail behind it. `OD-35` minted the field precisely
because free text is a carrier
`src/runtime/reports/not_verifiable.py`'s `reason_not_recorded` already names as
insufficient — but the detail says *against which sources*, and no enum member
carries that.
"""

from __future__ import annotations

from typing import Any, Mapping, get_args

from src.analysis.validate import Verified
from src.contracts.result import (
    STALENESS_NOT_STATED,
    Corroboration,
    Precision,
    PrecisionBasis,
    Result,
    Staleness,
    VerificationOutcome,
)
from src.runtime.verify import (
    DeclarationDisposition,
    Disagreement,
    ProvisionallyVerified,
    QuantityVerification,
    Refusal,
    RefusalReason,
    VerificationReport,
)

__all__ = [
    "JOINABLE_OUTCOMES",
    "JOINED_CORROBORATION",
    "JOINED_OUTCOME",
    "JOINED_PRECISION",
    "PRECISION_BASIS",
    "REFUSAL_CORROBORATION",
    "REPORT_MEMBERS",
    "UnjoinableReport",
    "result_from_quantity_verification",
    "result_from_report",
]


class UnjoinableReport(TypeError):
    """A value this seam will not turn into a caller-visible record.

    Raised rather than absorbed, and named rather than folded into
    `MissingVerification`: the caller handed over something that is not a member
    of `VerificationReport`, or the tables below stopped being total over one.
    Either way no verification outcome can be read off it, and the one thing
    this module may not do is supply one.

    The precedent is `ModuleTextUnavailable` in
    `src/runtime/reports/not_verifiable.py` — a function whose caller measures
    an absence must not return a benign value, because a record built from a
    guessed outcome is indistinguishable from one built from a verified one.
    """


#: The union's members, read **off the union** rather than retyped. A fifth
#: member added to `VerificationReport` with no row below is then a failing
#: totality arm rather than a report that falls through to a `KeyError` at the
#: first caller who holds one. `REPORTED_STATE` in `src/contracts/result.py` is
#: the same construction one layer down.
REPORT_MEMBERS: tuple[type, ...] = get_args(VerificationReport)

#: `OD-34` ③ fixes three rows and `OD-35` fixes the fourth. Not re-derived
#: here — the entries are the authority and this table is their transcription.
JOINED_OUTCOME: Mapping[type, VerificationOutcome] = {
    Verified: VerificationOutcome.VERIFIED,
    # `OD-35`, replacing `OD-34` ③'s struck NOT_VERIFIABLE. A comparison was
    # made and it agreed; what keeps it from reading as plain verification is
    # `JOINED_PRECISION` below and not a downgrade of the outcome.
    ProvisionallyVerified: VerificationOutcome.VERIFIED,
    Disagreement: VerificationOutcome.FAILED,
    Refusal: VerificationOutcome.NOT_VERIFIABLE,
}

#: The product's second half, for the three members whose corroboration does not
#: depend on a reason. `Refusal` is absent by design and is resolved through
#: `REFUSAL_CORROBORATION`; a row here as well would be a second place for the
#: same question to be answered differently.
JOINED_CORROBORATION: Mapping[type, Corroboration] = {
    # The token carries `issued_by: ValidatedContract`, which is a contract the
    # published specification agreed with. This is the value `Verified.to_result`
    # already writes, and the two are asserted to produce the same record.
    Verified: Corroboration.CORROBORATED,
    # `OD-35`, replacing `OD-34` ③'s struck PROVISIONAL. This token carries the
    # same `issued_by: ValidatedContract` the row above does — its
    # `__post_init__` refuses anything else — so `CORROBORATED` is the true
    # statement about *the contract*, which is the only subject this field has.
    # What was provisional is the precision, and that is the next table's.
    ProvisionallyVerified: Corroboration.CORROBORATED,
    # A `Disagreement` carries the two values and their retrievals and **no
    # contract**. The comparison was independent — `__post_init__` refuses a pair
    # out of one retrieval — but independence of the comparison is not the claim
    # `CORROBORATED` makes, which is about the contract the result was checked
    # against. Nobody said, and that is what is recorded.
    Disagreement: Corroboration.NOT_STATED,
}

#: `OD-35`'s third column, over the union. The one row that is not `NOT_STATED`
#: is `ProvisionallyVerified`, and it is what FR-024 property 5's *"never plain
#: verified"* is carried by on the record: without it that row's outcome and
#: corroboration are byte-identical to `Verified`'s.
#:
#: The three `NOT_STATED` rows are *nobody said* and not *no declaration was
#: made*. None of those three report objects carries a declaration at all — a
#: `Disagreement` reached through `verify_declared_quantity` was compared at one
#: and the token does not record it — so this entry point cannot answer the
#: question and says so. `result_from_quantity_verification` can, and does.
JOINED_PRECISION: Mapping[type, PrecisionBasis] = {
    Verified: PrecisionBasis.NOT_STATED,
    ProvisionallyVerified: PrecisionBasis.DECLARED,
    Disagreement: PrecisionBasis.NOT_STATED,
    Refusal: PrecisionBasis.NOT_STATED,
}

#: Total over `DeclarationDisposition`, and the map `OD-35` ⑤ requires in place
#: of an import: `src/contracts/` is the bottom of the import graph and cannot
#: see `src/runtime/verify.py`, so the two enums are related here, where both
#: are visible, and `test_the_precision_basis_map_is_total_over_the_disposition`
#: is what makes it a check rather than an assumption.
#:
#: `PrecisionBasis.NOT_STATED` has **no row and must not acquire one**. Every
#: disposition is a disclosure — `DeclarationDisposition` has no member meaning
#: *nothing happened* — so a route from one of them to *nobody said* would drop
#: property 5's disclosure at the boundary it exists to survive.
PRECISION_BASIS: Mapping[DeclarationDisposition, PrecisionBasis] = {
    DeclarationDisposition.ADMITTED: PrecisionBasis.DECLARED,
    DeclarationDisposition.IGNORED_ARTIFACT_SUPPLIED: (
        PrecisionBasis.ARTIFACT_DISPLACED_DECLARATION
    ),
    DeclarationDisposition.NOT_REACHED: PrecisionBasis.DECLARATION_NOT_REACHED,
}

#: Total over `RefusalReason`. A member with no row is a failing arm, not a
#: silent default: the two values here are different claims about the contract
#: and picking one by omission is the defect `Corroboration` replaced a boolean
#: to remove.
REFUSAL_CORROBORATION: Mapping[RefusalReason, Corroboration] = {
    # The only reason that reports on the contract itself. Produced by `_obtain`
    # exactly where the contract is a `ProvisionalContract`, so this row is what
    # makes the seam agree with `ProvisionalContract.to_result`.
    RefusalReason.CONTRACT_PROVISIONAL: Corroboration.PROVISIONAL,
    # The remaining six say the ladder could not make a comparison. None of them
    # reports on whether an artifact validated the contract, so none of them may
    # answer that question — `NOT_STATED` is the member that says so.
    RefusalReason.NO_RECOMPUTING_CHECK: Corroboration.NOT_STATED,
    RefusalReason.QUANTITY_ABSENT_FROM_RESULT: Corroboration.NOT_STATED,
    RefusalReason.QUANTITY_NOT_A_MAGNITUDE: Corroboration.NOT_STATED,
    RefusalReason.COLLECTION_UNAVAILABLE: Corroboration.NOT_STATED,
    RefusalReason.PRECISION_NOT_STATED: Corroboration.NOT_STATED,
    RefusalReason.SOURCES_NOT_INDEPENDENT: Corroboration.NOT_STATED,
}

#: Every outcome this seam may emit. **Computed by subtraction**, so the one
#: member excluded is excluded by name and nothing else is excluded by being
#: forgotten. `OD-34` ③: *"`MODEL_ASSESSED` has no source in this union and must
#: not acquire one here"* — nothing in `verify.py` produces it, and a join that
#: could emit it would be the Principle I boundary crossed at the one point
#: built to hold it.
JOINABLE_OUTCOMES: frozenset[VerificationOutcome] = frozenset(
    VerificationOutcome
) - {VerificationOutcome.MODEL_ASSESSED}


def _outcome(report: VerificationReport) -> VerificationOutcome:
    """This report's outcome, from the table. Never from the report's own say-so.

    Every member of the union carries an `outcome()` method and this
    deliberately does not call one. **Under `OD-35` all four now agree**, which
    weakens this arm rather than retiring it and the weakening is stated: while
    `OD-34` ③ stood, calling `outcome()` would have silently taken the
    verifier's reading for one member and the register's for the rest, and the
    disagreement made that visible. Now it would be invisible. What the table
    still buys is authority — a report's own say-so is the thing being recorded,
    not the thing that decides what is recorded — and
    `test_the_seam_does_not_read_the_reports_own_outcome_method` is now the only
    thing holding it, where before the two answers held it themselves.
    """
    outcome = JOINED_OUTCOME.get(type(report))
    if outcome is None:
        raise UnjoinableReport(
            f"{type(report).__name__} is not a member of VerificationReport "
            f"this seam has a row for. Rows: "
            f"{sorted(member.__name__ for member in JOINED_OUTCOME)}. Refused "
            "rather than defaulted: every default available here is a "
            "verification outcome nobody computed."
        )
    return _refuse_unjoinable(outcome, report)


def _refuse_unjoinable(
    outcome: VerificationOutcome, report: VerificationReport
) -> VerificationOutcome:
    """The runtime backstop on `JOINABLE_OUTCOMES`.

    The table is what is checked statically; this is what happens if an edit
    gets past that. It refuses rather than substituting, on the same ground the
    class docstring gives: a record whose outcome this module chose for it is
    exactly what FR-025 admits no result without.
    """
    if outcome not in JOINABLE_OUTCOMES:
        raise UnjoinableReport(
            f"the seam mapped a {type(report).__name__} onto "
            f"{outcome.value}, which is not an outcome it may emit. "
            f"Emittable: {sorted(member.value for member in JOINABLE_OUTCOMES)}"
            ". `MODEL_ASSESSED` has no source in this union (OD-34 ③) and a "
            "join that could emit it would be constitution Principle I's "
            "boundary crossed at the one point built to hold it."
        )
    return outcome


def _corroboration(report: VerificationReport) -> Corroboration:
    """What, if anything, this report says stood behind the contract."""
    if isinstance(report, Refusal):
        corroboration = REFUSAL_CORROBORATION.get(report.reason)
        if corroboration is None:
            raise UnjoinableReport(
                f"{report.reason.value} has no row in REFUSAL_CORROBORATION, "
                "which is required to be total over RefusalReason. A refusal "
                "reason minted without one would take whichever value the "
                "lookup defaulted to, and both available values are claims "
                "about the contract."
            )
        return corroboration
    corroboration = JOINED_CORROBORATION.get(type(report))
    if corroboration is None:
        raise UnjoinableReport(
            f"{type(report).__name__} has no corroboration row. FR-025's two "
            "questions are what state this is in and what established it, and "
            "a seam that can answer only the first builds a record whose "
            "second half nobody chose."
        )
    return corroboration


def _precision(report: VerificationReport) -> Precision:
    """Which rung this report's comparison rested on (`OD-35`).

    The basis comes out of `JOINED_PRECISION` and never off the report's type
    directly, for the reason `_outcome` gives: the table is the transcription of
    the register and the register is the authority. The **source text** does
    come off the report, because `ProvisionallyVerified` is the only member that
    carries a declaration and property 5 requires the text recorded beside the
    basis.
    """
    basis = JOINED_PRECISION.get(type(report))
    if basis is None:
        raise UnjoinableReport(
            f"{type(report).__name__} has no precision row. A record that "
            "cannot say what supplied the precision it was checked at is one "
            "FR-024 property 5 cannot distinguish from a plain verification, "
            "which is the distinction `OD-35` minted the field to keep."
        )
    if basis is PrecisionBasis.DECLARED and isinstance(report, ProvisionallyVerified):
        return Precision(basis, declared_in=report.declared.declared_in)
    return Precision(basis)


def _reason(report: VerificationReport) -> str | None:
    """The report's **own** named reason, never a synthesised one (`OD-34` ③).

    `None` for `Verified` alone: `Result.__post_init__` requires a reason on
    every other outcome, and a verified record has nothing to explain.

    `ProvisionallyVerified` is the one member with **no reason field at all**,
    and under `OD-35` it is also `VERIFIED`, where `Result` permits a reason and
    requires none. The composed sentence is kept anyway: `Result.precision`
    carries the *basis* and the declaration's source text, and this carries the
    part no enum member can — which quantity, and against what. Dropping it
    would leave the record structurally honest and unreadable. It is composed
    from fields already on the report and states only the rung's own
    admissibility premise, in `verify_declared_quantity`'s own words; nothing is
    inferred about the target, the contract or the comparison.
    """
    if isinstance(report, Verified):
        return None
    if isinstance(report, Refusal):
        return f"{report.reason.value}: {report.detail}"
    if isinstance(report, Disagreement):
        return report.detail
    if isinstance(report, ProvisionallyVerified):
        return (
            f"{report.check.operation_id}/{report.check.quantity}: the "
            "reported and recomputed values agreed at the precision declared "
            f"in {report.declared.declared_in!r}. No artifact source supplies "
            "a precision for this quantity, so nothing independent validates "
            "the precision the comparison rests on (FR-024 property 6)."
        )
    raise UnjoinableReport(
        f"{type(report).__name__} has no reason row. A non-verified record "
        "with no reason is indistinguishable from one nobody tried to verify, "
        "which is the distinction FR-025 exists to keep."
    )


def _build(
    report: VerificationReport,
    *,
    payload: Any,
    staleness: Staleness,
    disclosure: str | None,
    precision: Precision | None = None,
) -> Result:
    """The module's **only** `Result` construction, and the only one it may have.

    Both entry points come through here rather than each building their own.
    The reason is the invariant this task added: `Result` construction sites in
    `src/` are enumerated and authorised in
    `tests/invariants/test_result_constructor.py`, and a module with two of them
    is a module where one of them can drift. One site also means the outcome,
    the corroboration and the reason are read out of the tables above on every
    path, with no second path that could assemble them by hand.
    """
    #: Resolved before anything else, so a value the tables do not cover is
    #: refused by the row that names the union rather than by whichever helper
    #: happened to be called first. A caller reading `str has no reason row`
    #: would go looking for a missing reason, not a value that is not a report.
    outcome = _outcome(report)
    reason = _reason(report)
    if disclosure is not None:
        reason = disclosure if reason is None else f"{reason} {disclosure}"
    return Result(
        outcome,
        payload=payload,
        corroboration=_corroboration(report),
        reason=reason,
        staleness=staleness,
        #: `None` means *this caller held no provenance*, which is the
        #: `result_from_report` case, and the table's own answer is then the
        #: best available. It is not a default standing in for a fact: the
        #: table's row for three of the four members is `NOT_STATED`, which
        #: says exactly that.
        precision=_precision(report) if precision is None else precision,
    )


def result_from_report(
    report: VerificationReport,
    *,
    payload: Any,
    staleness: Staleness = STALENESS_NOT_STATED,
) -> Result:
    """The seam. One `VerificationReport`, one caller-visible `Result`.

    `payload` is required and has no default because the verifier does not hold
    it: a report is about a quantity, and what the caller is being handed back
    is the operation's own answer. `staleness` defaults to the marking that
    **makes no claim**, which is `Result`'s own default and is the honest value
    for a verification token — it bears on the contract, not on the freshness of
    the served-operation set (FR-047, and `Verified.to_result`'s own note).
    """
    return _build(report, payload=payload, staleness=staleness, disclosure=None)


def result_from_quantity_verification(
    verification: QuantityVerification,
    *,
    payload: Any,
    staleness: Staleness = STALENESS_NOT_STATED,
) -> Result:
    """The same seam, with FR-024 property 5's disclosure carried onto the record.

    A `QuantityVerification` is a report **and** the provenance of the precision
    the comparison used, and the two are one object precisely so that a consumer
    cannot read the outcome without the disposition. Reaching into `.report` and
    joining that alone would undo it at the boundary — *"an ignored declaration
    MUST be disclosed on the result, not silently dropped"* — so the disposition
    and its detail are appended to `Result.reason`, after the report's own named
    reason rather than in place of it.

    The disclosure is appended even on a `VERIFIED` record, where `Result`
    permits a reason and requires none. That is the case the requirement is
    actually about: a declaration ignored because an artifact source supplied a
    precision produces a plainly verified result, and a caller who cannot see
    the ignored declaration on it is the reader FR-058 says arrives at the
    result and nowhere else.
    """
    provenance = verification.precision
    basis = PRECISION_BASIS.get(provenance.disposition)
    if basis is None:
        raise UnjoinableReport(
            f"{provenance.disposition.value} has no row in PRECISION_BASIS, "
            "which is required to be total over DeclarationDisposition. A "
            "disposition minted without one would take whichever basis the "
            "lookup defaulted to, and every available default is a claim about "
            "where the precision came from."
        )
    return _build(
        verification.report,
        payload=payload,
        staleness=staleness,
        disclosure=(
            f"declared precision {provenance.disposition.value}: "
            f"{provenance.detail}"
        ),
        #: Read off the provenance rather than off the report's type, because
        #: this caller holds the thing `result_from_report` does not. It is the
        #: stronger answer on three of the four members: a `Verified` or a
        #: `Disagreement` reached through the declared rung is `NOT_STATED` at
        #: the other entry point and is named here.
        precision=Precision(
            basis,
            declared_in=(
                provenance.declared.declared_in
                if basis is PrecisionBasis.DECLARED
                else None
            ),
        ),
    )
