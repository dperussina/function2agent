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
