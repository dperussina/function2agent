"""The caller-visible result, which **cannot be constructed without a
verification outcome** (FR-025) or without saying what corroborated it.

Pulled forward from Phase 2 for one reason: the invariants file the plan
committed to names "no code path constructs a caller-visible result without a
verification outcome" as an invariant, and an invariant with no type to check
is a comment. What is here is the constructor constraint, FR-025's three
reported states and FR-047's staleness marking — the result's payload schema,
its storage and its trace linkage are Phase 6's and are still owed.

**Structural, not checked.** `VerificationOutcome` has no default and no
`None` member, so there is no value of the field that means "not verified yet".
A caller with nothing to report must say `NOT_VERIFIABLE` and give a reason,
which is a different claim from silence and is recorded as one.

This is constitution Principle I's boundary in the type system: a model's
opinion cannot become a verification outcome by being placed in this field,
because `MODEL_ASSESSED` is a distinct member that the accompanying
`test_import_graph` invariant keeps the judge module from reaching.

## Four outcomes, three reported states

FR-025 requires *"exactly one of three states"* and `VerificationOutcome` has
**four** members, because a model's assessment is a distinct thing to be told
and collapsing it into one of the three is exactly what Principle I forbids.
`REPORTED_STATE` reconciles the two: it is a total, disjoint map from every
outcome onto one state, so the three stay exhaustive and mutually exclusive
over everything the record can carry. `MODEL_ASSESSED` reports as
`NOT_VERIFIABLE` — nothing was verified, and FR-025 requires that case returned
marked rather than dressed as anything else.

Reading the map rather than a written-out list is what makes the exhaustiveness
tests in `tests/contract/test_result_record.py` fail when a member is added
without anyone telling them about it.

## `corroboration`, and the boolean it replaces

This field was `provisional: bool = False` until T126. `False` meant both *this
contract was corroborated* and *nobody said*, with the claim-making value as the
default — the `spend_usd is None` against a measured zero defect wearing a
boolean, and sitting on the field that gates verification. It is now a
three-member enum with **no default**, so *nobody said* is a thing a caller
states rather than a thing a caller omits, and `NOT_STATED` is the name it says
it under. A verified state is unconstructible from either absent reading.

## `staleness`, and why its default is not the same mistake

FR-047 requires the stale marking to be a field separate from the verification
state which *"MUST NOT become a fourth value of it"*. It defaults, where
`corroboration` does not, and the asymmetry is deliberate: its default is
`NOT_STATED`, which **makes no claim**. A default of `FRESH` would be the
boolean defect moved one field over — silence reading as an assertion that the
served-operation set was current.

## `precision`, and the third subject

Three fields, three subjects, and `OD-35` is where that became explicit.
`verification` is about the **state**. `corroboration` is about the
**contract** — its `PROVISIONAL` member names FR-026's contract state and
nothing else. `precision` is about the **precision the comparison was made
at**, which FR-024 properties 5 and 6 mark independently of both.

The field exists because the union of two requirements was unsatisfiable
without it. Property 5 says an admitted caller-declared precision produces a
state that is *"provisional and never plain verified"*; FR-025 admits three
states and `CORROBORATED` is the only value a `VERIFIED` result may carry. So
`VERIFIED`/`CORROBORATED` alone is *plain verified*, and the only thing left to
distinguish it was free text in `reason` — which
`src/runtime/reports/not_verifiable.py` already names as a carrier a consumer
cannot key on. Reusing `Corroboration.PROVISIONAL` was the other candidate and
is worse: it states something false about a contract that is necessarily
validated.

**It defaults, and the rule above is what decides that rather than
convenience.** A field may default iff its default makes no claim.
`PrecisionBasis.NOT_REACHED` — *a declaration was in hand and the ladder never
reached it* — is a claim, and defaulting to it would be the `FRESH` defect a
third time: a producer that never saw a declaration would be recorded as having
resolved one. `NOT_STATED` is *nobody told this record*, which is what silence
actually means here, and it is the honest value at `validate.py`'s two
`to_result` sites, neither of which can see a precision at all.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class VerificationOutcome(Enum):
    """Every value a result's verification can take. There is no absent value."""

    VERIFIED = "verified"
    FAILED = "failed"
    # A contract exists but was marked provisional, so it can produce this and
    # never VERIFIED (T123 enforces the same thing at the analysis boundary).
    NOT_VERIFIABLE = "not_verifiable"
    # A model said something about it. Deliberately **not** a verification: it
    # is recorded in the same field so that a reader cannot mistake it for one,
    # and it is the value Principle I exists to keep distinct.
    MODEL_ASSESSED = "model_assessed"


class ReportedState(Enum):
    """FR-025's three, as the caller sees them. Machine-distinguishable."""

    VERIFIED = "verified"
    FAILED_VERIFICATION = "failed_verification"
    NOT_VERIFIABLE = "not_verifiable"


#: The wording FR-025 uses for each state, reconciled against `spec.md` rather
#: than trusted. A state the requirement does not name is one nobody authorised,
#: and a requirement that grows a fourth without the code following is the same
#: divergence in the other direction — `lifecycle-taxonomy` in
#: `tools/corpuscheck/` was written after that pair went unnoticed for weeks
#: over the terminal-state taxonomy.
FR_025_PHRASES: Mapping[ReportedState, str] = {
    ReportedState.VERIFIED: "verified",
    ReportedState.FAILED_VERIFICATION: "failed verification",
    ReportedState.NOT_VERIFIABLE: "not verifiable",
}

#: Total and disjoint over `VerificationOutcome`. An outcome with no row here
#: is a result that carries none of FR-025's three states.
REPORTED_STATE: Mapping[VerificationOutcome, ReportedState] = {
    VerificationOutcome.VERIFIED: ReportedState.VERIFIED,
    VerificationOutcome.FAILED: ReportedState.FAILED_VERIFICATION,
    VerificationOutcome.NOT_VERIFIABLE: ReportedState.NOT_VERIFIABLE,
    # Nothing was verified. FR-025 returns that marked, and Principle I keeps
    # the outcome distinct so the reason survives into the record.
    VerificationOutcome.MODEL_ASSESSED: ReportedState.NOT_VERIFIABLE,
}

VERIFYING_OUTCOMES = frozenset({VerificationOutcome.VERIFIED})


class Corroboration(Enum):
    """What, if anything, stood behind the verification (T126).

    Three members and not a boolean, because the two absent readings of `False`
    are different claims and a consumer has to be able to tell them apart.
    """

    #: An independent artifact validated the contract this result was checked
    #: against. The only value a VERIFIED result may carry.
    CORROBORATED = "corroborated"
    #: The contract was marked provisional under FR-026. It can produce
    #: NOT_VERIFIABLE and never VERIFIED (constitution Principle I, v1.1.0).
    PROVISIONAL = "provisional"
    #: Nobody said. Not a claim that nothing corroborated it — a claim that the
    #: question was not answered, which is what the old `False` hid.
    NOT_STATED = "not_stated"


class PrecisionBasis(Enum):
    """FR-024's rung, on the record. What supplied the precision, as a member.

    Four members and not two, because property 5 asks the record to disclose
    three different things about a declaration — it was used, it was displaced,
    it was never reached — and the fourth is the absent case, named.

    The first three correspond to `DeclarationDisposition` in
    `src/runtime/verify.py`, and the correspondence is a **map** rather than an
    import: `src/contracts/` is the bottom of the import graph, the same reason
    `SPECIFICATION_STATES` above is duplicated. `PRECISION_BASIS` in
    `src/runtime/result_join.py` holds it, where both enums are visible, and a
    totality arm is what makes it a check instead of an assumption.
    """

    #: The caller's own declaration was admitted, because no artifact source
    #: supplied a precision for the quantity (FR-024 property 5). Property 6
    #: marks such a verification provisional **on its own provenance**, and this
    #: member is that marking: a record carrying it is not plain verified.
    DECLARED = "declared"
    #: An artifact source supplied the precision and the declaration was
    #: ignored — tighter, equal or looser alike. Property 5's closing
    #: sub-bullet, *"an ignored declaration MUST be disclosed on the result, not
    #: silently dropped"*, carried by a member rather than by free text.
    ARTIFACT_DISPLACED_DECLARATION = "artifact_displaced_declaration"
    #: A declaration was in hand and the ladder never reached the precision
    #: question. Distinct from the member above, because claiming an artifact
    #: displaced a declaration when none did is fabricated provenance.
    DECLARATION_NOT_REACHED = "declaration_not_reached"
    #: Nobody said. **Not** a claim that no declaration was made — a claim that
    #: this record was not told, which is the only reading a default can carry.
    NOT_STATED = "not_stated"


class StaleMarking(Enum):
    """FR-047's marking. A field beside the state, never a value of it."""

    FRESH = "fresh"
    STALE = "stale"
    #: No served-operation set bears on this result, or none was consulted.
    NOT_STATED = "not_stated"


#: The specification states `src/analysis/admission.py` can report, duplicated
#: rather than imported: `src/contracts/` is the bottom of the import graph and
#: importing `src/analysis/` into it would invert that. The same construction
#: `src/contracts/transition.py` uses for the session-lifecycle constants — a
#: test asserts the two agree, which is a check, where an import would be an
#: assumption.
SPECIFICATION_STATES: frozenset[str] = frozenset(
    {
        "published_non_empty",
        "absent",
        "unreadable_by_credential",
        "readable_no_operations",
        "unparseable",
        "unreachable",
    }
)


class MissingVerification(TypeError):
    """A result was constructed with no verification outcome (FR-025)."""


@dataclass(frozen=True)
class Staleness:
    """FR-047's three facts: the marking, the age, the state last found.

    A bare flag would satisfy the sentence's letter and lose what bounds the
    risk: the ceiling is measured from the last successful fetch, so a stale
    marking that cannot say how old it is records the exposure without
    recording the thing that closes it.
    """

    marking: StaleMarking
    age_seconds: float | None = None
    specification_state: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.marking, StaleMarking):
            raise ValueError(
                "Staleness.marking must be a StaleMarking member; got "
                f"{type(self.marking).__name__}"
            )
        stale = self.marking is StaleMarking.STALE
        if stale:
            if self.age_seconds is None:
                raise ValueError(
                    "a stale marking must carry the age of the set it marks. "
                    "FR-047's ceiling is measured from the last successful "
                    "fetch, and an age nobody recorded cannot be compared "
                    "against it."
                )
            if self.specification_state is None:
                raise ValueError(
                    "a stale marking must carry the specification state last "
                    "found (FR-047)"
                )
        else:
            if self.age_seconds is not None:
                raise ValueError(
                    f"a {self.marking.value} marking carries no age; this one "
                    f"carries {self.age_seconds!r}. Two fields that can "
                    "disagree will."
                )
            if self.specification_state is not None:
                raise ValueError(
                    f"a {self.marking.value} marking carries no specification "
                    "state"
                )
        if (
            self.specification_state is not None
            and self.specification_state not in SPECIFICATION_STATES
        ):
            raise ValueError(
                f"{self.specification_state!r} is not a specification state "
                "the admission check can report. FR-047 asks for the state "
                "last found, and a string nothing produces is not one."
            )


#: The absent case, named. A result whose producer has nothing to say about the
#: served-operation set says this rather than saying `FRESH`.
STALENESS_NOT_STATED = Staleness(StaleMarking.NOT_STATED)


@dataclass(frozen=True)
class Precision:
    """FR-024's two facts: what supplied the precision, and whose word it was.

    A dataclass and not a bare enum, for `Staleness`'s reason one field over. A
    `DECLARED` basis that cannot say **where** the declaration came from records
    the exposure — this comparison rests on the caller's own word — without
    recording the thing that lets a reader weigh it. Property 5 names both
    nouns, *"the declaration and its source text"*.

    **The recording obligation itself is the verifier's and is discharged
    there**: `DeclaredPrecision.__post_init__` refuses a blank source text
    citing property 5. What lands here is the *disclosure*, which property 5
    puts on the result in as many words, and which was travelling as free text
    inside `Result.reason` until `OD-35`. `decimal_places` is deliberately not
    carried: it is how strict the comparison was, not where its authority came
    from, and nothing writes it to a record.
    """

    basis: PrecisionBasis
    #: The declaration's own source text. Set on `DECLARED` and nothing else.
    declared_in: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.basis, PrecisionBasis):
            raise ValueError(
                "Precision.basis must be a PrecisionBasis member; got "
                f"{type(self.basis).__name__}"
            )
        declared = self.basis is PrecisionBasis.DECLARED
        if declared and not (self.declared_in or "").strip():
            raise ValueError(
                "a declared basis must carry the source text the declaration "
                "was made in. FR-024 property 5 requires the declaration and "
                "its source text recorded as the precision's provenance, and a "
                "record saying a comparison rests on the caller's own word "
                "without saying whose word states the exposure and withholds "
                "what closes it."
            )
        if not declared and self.declared_in is not None:
            raise ValueError(
                f"a {self.basis.value} basis names {self.declared_in!r} as the "
                "text a precision was declared in. Nothing was declared into "
                "this comparison, and a source cited for a declaration that "
                "did not act is fabricated provenance."
            )


#: The absent case, named, on `STALENESS_NOT_STATED`'s pattern. A producer that
#: cannot see a precision says this rather than saying no declaration was made.
PRECISION_NOT_STATED = Precision(PrecisionBasis.NOT_STATED)


@dataclass(frozen=True)
class Result:
    """A caller-visible result. One constructor, and it takes the provenance.

    `verification` is positional and required. It is first among the fields
    with no default on purpose: a contributor adding a field cannot end up with
    a signature where the verification outcome is optional. `corroboration`
    sits with it for the same reason — the two questions FR-025 turns on are
    *what state is this in* and *what established it*, and neither has a value
    a caller can reach by omission.
    """

    verification: VerificationOutcome
    payload: Any
    corroboration: Corroboration
    # Why, when the outcome is anything but VERIFIED. Required in those cases,
    # because "not verifiable" with no reason is indistinguishable from nobody
    # having tried.
    reason: str | None = None
    # FR-047. Defaults to the marking that makes no claim — see the module
    # docstring on why this one may default and `corroboration` may not.
    staleness: Staleness = field(default=STALENESS_NOT_STATED)
    # FR-024 properties 5 and 6, `OD-35`. Same asymmetry, same reason: the
    # default is the basis that makes no claim, and `NOT_REACHED` would be the
    # one that does.
    precision: Precision = field(default=PRECISION_NOT_STATED)

    def __post_init__(self) -> None:
        if not isinstance(self.verification, VerificationOutcome):
            raise MissingVerification(
                "Result.verification must be a VerificationOutcome member; "
                f"got {type(self.verification).__name__}. FR-025 admits no "
                "result without one."
            )
        if not isinstance(self.corroboration, Corroboration):
            raise MissingVerification(
                "Result.corroboration must be a Corroboration member; got "
                f"{type(self.corroboration).__name__}. A boolean here was the "
                "defect T126 removed."
            )
        if not isinstance(self.staleness, Staleness):
            raise MissingVerification(
                "Result.staleness must be a Staleness; got "
                f"{type(self.staleness).__name__}"
            )
        if not isinstance(self.precision, Precision):
            raise MissingVerification(
                "Result.precision must be a Precision; got "
                f"{type(self.precision).__name__}"
            )
        if (
            self.precision.basis is PrecisionBasis.DECLARED
            and self.corroboration is Corroboration.PROVISIONAL
        ):
            raise MissingVerification(
                "this result says the precision came from the caller's own "
                "declaration and that the contract behind it was provisional. "
                "Both cannot be true of one contract: a declaration is "
                "admissible only against a contract the ladder validated, and "
                "a provisional one refuses at CONTRACT_PROVISIONAL before the "
                "precision question is reached. The two fields have different "
                "subjects, and this pair is OD-34 ③'s struck row half-restored "
                "beside OD-35's."
            )
        if self.verification is not VerificationOutcome.VERIFIED and not self.reason:
            raise MissingVerification(
                f"Result with verification={self.verification.value} needs a "
                "reason. An unexplained non-verification is not "
                "distinguishable from an untried one."
            )
        if self.verification is VerificationOutcome.VERIFIED:
            if self.corroboration is Corroboration.PROVISIONAL:
                raise MissingVerification(
                    "a provisional contract can produce NOT_VERIFIABLE and "
                    "never VERIFIED (constitution Principle I, v1.1.0)"
                )
            if self.corroboration is not Corroboration.CORROBORATED:
                raise MissingVerification(
                    "a VERIFIED result must say what corroborated it; this one "
                    f"carries corroboration={self.corroboration.value}. Nobody "
                    "said is not the same claim as it was checked, and a "
                    "verified state built on the first is the defect FR-025 "
                    "calls a form a caller could mistake for verified."
                )

    @property
    def state(self) -> ReportedState:
        """FR-025's state, as a consuming system reads it."""
        return REPORTED_STATE[self.verification]

    @property
    def is_verified(self) -> bool:
        return self.verification in VERIFYING_OUTCOMES

    @property
    def is_stale(self) -> bool:
        """True only where the marking says so. `NOT_STATED` is not `FRESH`."""
        return self.staleness.marking is StaleMarking.STALE
