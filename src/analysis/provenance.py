"""T121 — provenance as data on every derived contract and every derived check.

**Requirement**: FR-026 — *"Every derived contract and every derived check MUST
carry, as data, the rule that derived it, the source symbol and file it came
from, the analyzer version, a content hash, and its validation status. A derived
check MUST be validated against an artifact its own derivation did not produce;
where no independent artifact exists it MUST be marked provisional and MUST NOT
be presented as validated."*

Six fields, and this module's whole job is that none of them can be absent,
free-form or true by default. A provenance record that anything can put anything
into is a comment with a schema.

## Why each field refuses something

- **`derivation_rule`** must name a rule in `DERIVATION_RULES`. A free string
  names nothing a reader can look up, and *"which rule produced this?"* is the
  question finding 007 could only answer because the rules were enumerated:
  disabling exactly one of them — the alias-generator walk — left 15 of 69
  endpoints with a contract that was fluent, plausible and wrong about every
  field name on the wire, **with nothing in the output indicating it**. The rule
  name is what makes that diagnosable after the fact instead of invisible.
- **`source_symbol`** and **`source_file`** must be present, and the file must
  be **repository-relative**. That is not tidiness. `src/contracts/envelope.py`
  scans the hashed payload and moves anything path-shaped out beside the hash
  under FR-055, so an absolute path would be stripped out of the artifact's
  identity and FR-026's *as data* would hold only until the artifact was
  wrapped. A relative path is also stable across two checkouts, which is what
  FR-002's *reproducible from the codebase alone* needs.
- **`analyzer_version`** is ours and is deliberately a different fact from
  `CODEGRAPH_REVISION`. Collapsing them would make one of our releases read as
  an upstream one, which is the confusion **U-04** exists to prevent.
- **`content_hash`** is over the **source construct the rule read**, not over
  this record and not over the derived artifact. FR-028 has to detect *a source
  change that invalidates a derived contract*; hashing the source text of the
  symbol is what makes that a comparison rather than a re-analysis.
- **`validation_status`** defaults to `PROVISIONAL` and `VALIDATED` is
  unconstructible without naming the artifact that validated it — which may not
  be the source the rule read. That is constitution Principle I as amended at
  v1.1.0, held in the constructor rather than in review.

## What this module deliberately does not do

It does not decide whether a contract agrees with the target's published
specification. That is **T122**, and it needs the specification. What is here is
the shape the answer has to arrive in, so that T122 can only record a verdict it
has an artifact for.

## One recorded concern, for whoever builds T122 and T133

`analyzer_version` is carried under the derived artifact's content address, and
`src/contracts/schemas.py` does not list it as volatile. So **bumping this
constant changes the content address of every derived contract and check**, and
FR-028 reads a changed address on a source-derived artifact as source drift.
That is the same false-alarm shape `src/analysis/served_operations.py` argues
about for `schema_version` — *a release of ours is not the source clock ticking*
— arriving one level down. It is **not** fixed here, because the fix is a
schema decision (a new `volatile` entry, or a rule that the address is taken
over a subset) and this task does not own the schema. Recorded so it is a known
open item rather than a surprise the first time the analyzer is versioned.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from src.contracts.canonical import content_address

__all__ = [
    "ANALYZER_VERSION",
    "CODEGRAPH_REVISION",
    "DERIVATION_RULES",
    "DerivationRule",
    "FR_023_ARTIFACT_CLASSES",
    "Provenance",
    "ProvenanceError",
    "ValidationStatus",
    "hash_source_construct",
]

# Our own analyzer, semantically versioned under Principle VIII. Not a
# measurement and not an observation of anything external — it is a declaration,
# unlike `codegraph_pin.CODEGRAPH_VERSION`, which names somebody else's artifact
# and had to be observed before it could be written down.
ANALYZER_VERSION = "0.1.0"

# Carried beside it so the two are visibly separate facts. Imported rather than
# retyped: one string, one owner.
from src.analysis.codegraph_pin import CODEGRAPH_VERSION as CODEGRAPH_REVISION  # noqa: E402


class ProvenanceError(ValueError):
    """A provenance record that does not carry what FR-026 requires."""


class ValidationStatus(Enum):
    """FR-026's two, and there is no third meaning *not looked at yet*.

    A derivation that has not been compared to anything is `PROVISIONAL`, which
    is a claim about the evidence and not about the effort. That is the
    distinction Principle I turns on: absence of validation is a fact to record,
    not a state to leave blank.
    """

    PROVISIONAL = "provisional"
    VALIDATED = "validated"


# FR-023's admissible source classes, quoted from the requirement rather than
# paraphrased: "signatures, return types, preconditions, postconditions,
# invariants, exception classes, existing tests, or observable state".
FR_023_ARTIFACT_CLASSES = frozenset(
    {
        "signature",
        "return_type",
        "precondition",
        "postcondition",
        "invariant",
        "exception_class",
        "existing_test",
        "observable_state",
    }
)


@dataclass(frozen=True)
class DerivationRule:
    """One named way of getting from a source artifact to a contract or check.

    `reads` is constrained to `FR_023_ARTIFACT_CLASSES`, which is how the
    requirement's prohibition on a model's assessment is held as a table rather
    than as a habit: there is no member for it, so no rule can declare one.
    """

    name: str
    reads: str
    emits: str
    description: str


def _rules(*rules: DerivationRule) -> dict[str, DerivationRule]:
    return {rule.name: rule for rule in rules}


#: The rule set. Adding a rule here and nowhere else is deliberate — every
#: derived artifact names one of these, so an unregistered rule cannot reach an
#: artifact and a registered rule that nothing emits is visible as dead.
DERIVATION_RULES: dict[str, DerivationRule] = _rules(
    DerivationRule(
        name="return_annotation",
        reads="return_type",
        emits="shape_check",
        description=(
            "The declared return type becomes a shape check. Weak on purpose "
            "and labelled as such: finding 001 measured 11 false successes, 8 "
            "of them numeric-typed and schema-blind — right shape, wrong value "
            "— so a check of this kind can never be the only one on a quantity."
        ),
    ),
    DerivationRule(
        name="aggregate_binding",
        reads="postcondition",
        emits="recomputation_check",
        description=(
            "A returned key bound to an aggregate over a named collection — "
            "`len(lots)`, `sum(l['quantity'] for l in lots)` — becomes a "
            "recomputation: the verifier recomputes the aggregate from the "
            "collection and compares, never reading the reported number."
        ),
    ),
    DerivationRule(
        name="postcondition_assert",
        reads="postcondition",
        emits="recomputation_check",
        description=(
            "An `assert` in the function body comparing a returned name to an "
            "expression over other observables. The author already wrote the "
            "independent path; this lifts it out of the process being verified."
        ),
    ),
    DerivationRule(
        name="precondition_guard",
        reads="precondition",
        emits="precondition",
        description=(
            "A leading `if <cond>: raise <E>` is a stated precondition and the "
            "exception class it raises is its failure mode."
        ),
    ),
    DerivationRule(
        name="raises_statement",
        reads="exception_class",
        emits="failure_taxonomy_entry",
        description=(
            "An exception class raised in the body. Recoverability, not "
            "accuracy: finding 007 measured this component at 53.6% from the "
            "handler body and it is the only one with no ground truth, so what "
            "it emits is a candidate and is marked provisional like the rest."
        ),
    ),
)


_CONTENT_ADDRESS = re.compile(r"^sha256:[0-9a-f]{64}$")
_WINDOWS_PATH = re.compile(r"^[A-Za-z]:[\\/]")


def hash_source_construct(text: str) -> str:
    """A content address over the source text a rule read.

    Over the text, not over an AST dump: the address has to move when the source
    moves, and two different renderings of the same construct are not the thing
    FR-028 is comparing.
    """
    return content_address(text)


@dataclass(frozen=True)
class Provenance:
    """FR-026's six fields, none of them optional in practice."""

    derivation_rule: str
    source_symbol: str
    source_file: str
    content_hash: str
    analyzer_version: str = ANALYZER_VERSION
    validation_status: ValidationStatus = ValidationStatus.PROVISIONAL
    validated_against: str | None = None

    def __post_init__(self) -> None:
        if self.derivation_rule not in DERIVATION_RULES:
            raise ProvenanceError(
                f"{self.derivation_rule!r} is not a registered derivation rule, "
                "so this record names no rule a reader can look up. Registered: "
                f"{sorted(DERIVATION_RULES)}"
            )
        if not self.source_symbol.strip():
            raise ProvenanceError(
                "source_symbol is empty. FR-026 requires the symbol it came "
                "from, and a file alone does not locate a derivation."
            )
        if not self.source_file.strip():
            raise ProvenanceError("source_file is empty.")
        if self.source_file.startswith("/") or _WINDOWS_PATH.match(self.source_file):
            raise ProvenanceError(
                f"source_file {self.source_file!r} is absolute; it must be "
                "relative to the analysed repository. An absolute path is "
                "volatile under FR-055 — `src/contracts/envelope.py` moves it "
                "out of the hashed payload — so the provenance would be "
                "stripped from the artifact's identity the moment it was "
                "wrapped, and it would differ between two checkouts."
            )
        if not _CONTENT_ADDRESS.match(self.content_hash):
            raise ProvenanceError(
                f"content_hash {self.content_hash!r} is not a lowercase "
                "sha256 content address. Use `hash_source_construct`."
            )
        if not self.analyzer_version.strip():
            raise ProvenanceError("analyzer_version is empty.")

        validated = self.validation_status is ValidationStatus.VALIDATED
        if validated and not self.validated_against:
            raise ProvenanceError(
                "validation_status is `validated` and validated_against is "
                "empty. FR-026 and constitution Principle I require a derived "
                "check to be validated against an artifact its own derivation "
                "did not produce; a status with no artifact is the "
                "presented-as-validated case the requirement forbids."
            )
        if self.validated_against and not validated:
            raise ProvenanceError(
                f"validated_against names {self.validated_against!r} while the "
                "status is `provisional`. The pair moves together, or the "
                "record cites an artifact it did not act on."
            )
        if validated and self.validated_against == self.source_file:
            raise ProvenanceError(
                f"validated_against names {self.validated_against!r}, which is "
                "the source file this record was derived from. Principle I "
                "requires an artifact its own derivation did not produce; "
                "checking a derivation against its own input validates nothing."
            )

    def to_payload(self) -> dict[str, Any]:
        """The record as canonical data, for the `provenance` field of a check."""
        return {
            "derivation_rule": self.derivation_rule,
            "source_symbol": self.source_symbol,
            "source_file": self.source_file,
            "analyzer_version": self.analyzer_version,
            "content_hash": self.content_hash,
            "validation_status": self.validation_status.value,
            "validated_against": self.validated_against,
        }

    @property
    def rule(self) -> DerivationRule:
        return DERIVATION_RULES[self.derivation_rule]
