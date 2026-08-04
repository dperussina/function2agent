"""The caller-visible result, which **cannot be constructed without a
verification outcome** (FR-025).

Pulled forward from Phase 2 for one reason: the invariants file the plan
committed to names "no code path constructs a caller-visible result without a
verification outcome" as an invariant, and an invariant with no type to check
is a comment. What is here is the constructor constraint and nothing else — the
result's payload schema, its storage and its trace linkage are Phase 6's and
are still owed.

**Structural, not checked.** `VerificationOutcome` has no default and no
`None` member, so there is no value of the field that means "not verified yet".
A caller with nothing to report must say `NOT_VERIFIABLE` and give a reason,
which is a different claim from silence and is recorded as one.

This is constitution Principle I's boundary in the type system: a model's
opinion cannot become a verification outcome by being placed in this field,
because `MODEL_ASSESSED` is a distinct member that the accompanying
`test_import_graph` invariant keeps the judge module from reaching.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


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


VERIFYING_OUTCOMES = frozenset({VerificationOutcome.VERIFIED})


class MissingVerification(TypeError):
    """A result was constructed with no verification outcome (FR-025)."""


@dataclass(frozen=True)
class Result:
    """A caller-visible result.

    `verification` is positional and required. It is first among the fields
    with no default on purpose: a contributor adding a field cannot end up with
    a signature where the verification outcome is optional.
    """

    verification: VerificationOutcome
    payload: Any
    # Why, when the outcome is anything but VERIFIED. Required in those cases,
    # because "not verifiable" with no reason is indistinguishable from nobody
    # having tried.
    reason: str | None = None
    provisional: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.verification, VerificationOutcome):
            raise MissingVerification(
                "Result.verification must be a VerificationOutcome member; "
                f"got {type(self.verification).__name__}. FR-025 admits no "
                "result without one."
            )
        if self.verification is not VerificationOutcome.VERIFIED and not self.reason:
            raise MissingVerification(
                f"Result with verification={self.verification.value} needs a "
                "reason. An unexplained non-verification is not "
                "distinguishable from an untried one."
            )
        if self.provisional and self.verification is VerificationOutcome.VERIFIED:
            raise MissingVerification(
                "a provisional contract can produce NOT_VERIFIABLE and never "
                "VERIFIED (constitution Principle I, v1.1.0)"
            )

    @property
    def is_verified(self) -> bool:
        return self.verification in VERIFYING_OUTCOMES
