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
`VerificationOutcome` **and** a `Corroboration`, so this is a map into a product
and not a rename. `OD-34` ③ fixes the outcome column for all four:

| report                  | outcome          | corroboration | fixed by |
| ----------------------- | ---------------- | ------------- | -------- |
| `Verified`              | `VERIFIED`       | `CORROBORATED`| `OD-34`  |
| `ProvisionallyVerified` | `NOT_VERIFIABLE` | `PROVISIONAL` | `OD-34`  |
| `Disagreement`          | `FAILED`         | `NOT_STATED`  | here     |
| `Refusal`               | `NOT_VERIFIABLE` | *by reason*   | here     |

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

⚠️ **`OD-34` ③'s `ProvisionallyVerified` row contradicts T212's ruling, is
implemented as the register fixes it, and is flagged rather than diverged
from.** `ProvisionallyVerified.outcome()` in `verify.py` returns **`VERIFIED`**,
and `tasks.md`'s T212 notes rule explicitly that *"'Provisional' is NOT
`Corroboration`"* on the ground that `Corroboration`'s subject is the
**contract** — necessarily a `ValidatedContract` here, since
`ProvisionallyVerified.__post_init__` refuses anything else — where property 6
marks the **precision**. So the register and the module it maps disagree about
the same object. This module follows the register, because a join that quietly
took the other reading would leave the two disagreeing with nothing recording
it. `test_the_two_readings_of_a_provisionally_verified_report_are_both_named`
pins the reading actually shipped and names the other, so a reversal is one row
and one arm. The disposition is an owner decision and is recorded as a dated
annotation at `OD-34` and at T213.

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
separate entry point that carries the disposition into `Result.reason`, and it
is the only way to turn a `QuantityVerification` into a record.

`Result` has no field for a precision disposition and this task does not mint
one: the payload schema is still owed (see `src/contracts/result.py`'s module
docstring), and `reason` is the field FR-025 already reserves for *why*.
"""

from __future__ import annotations

from typing import Any, Mapping, get_args

from src.analysis.validate import Verified
from src.contracts.result import (
    STALENESS_NOT_STATED,
    Corroboration,
    Result,
    Staleness,
    VerificationOutcome,
)
from src.runtime.verify import (
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

#: `OD-34` ③ fixes every row. Not re-derived here — the entry is the authority
#: and this table is its transcription.
JOINED_OUTCOME: Mapping[type, VerificationOutcome] = {
    Verified: VerificationOutcome.VERIFIED,
    ProvisionallyVerified: VerificationOutcome.NOT_VERIFIABLE,
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
    # `OD-34` ③. See the module docstring on the contradiction with T212 that
    # this row implements rather than resolves.
    ProvisionallyVerified: Corroboration.PROVISIONAL,
    # A `Disagreement` carries the two values and their retrievals and **no
    # contract**. The comparison was independent — `__post_init__` refuses a pair
    # out of one retrieval — but independence of the comparison is not the claim
    # `CORROBORATED` makes, which is about the contract the result was checked
    # against. Nobody said, and that is what is recorded.
    Disagreement: Corroboration.NOT_STATED,
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

    `Verified`, `Disagreement` and `Refusal` each carry an `outcome()` method,
    and this deliberately does not call it: `ProvisionallyVerified.outcome()`
    returns `VERIFIED` where `OD-34` ③ fixes the record at `NOT_VERIFIABLE`, so
    the two answers exist and the seam has to say which one it is transcribing.
    It is the register's, and the disagreement is recorded rather than hidden
    behind a method call that would silently pick the other.
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


def _reason(report: VerificationReport) -> str | None:
    """The report's **own** named reason, never a synthesised one (`OD-34` ③).

    `None` for `Verified` alone: `Result.__post_init__` requires a reason on
    every other outcome, and a verified record has nothing to explain.

    `ProvisionallyVerified` is the one member with **no reason field at all**,
    which `OD-34` ③ does not account for — it fixes the member at
    `NOT_VERIFIABLE`, and `Result` refuses that outcome without a reason. What
    is written here is composed from fields already on the report (the check's
    operation and quantity, and the declaration's own source text) and states
    only the rung's own admissibility premise, which
    `verify_declared_quantity` states in the same words. Nothing is inferred
    about the target, the contract or the comparison.
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
    disposition = verification.precision.disposition.value
    return _build(
        verification.report,
        payload=payload,
        staleness=staleness,
        disclosure=(
            f"declared precision {disposition}: {verification.precision.detail}"
        ),
    )
