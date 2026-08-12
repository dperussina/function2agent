"""T122 and T123 — promotion against the published specification, and the gate.

**Requirements**: FR-026 — *"A derived check MUST be validated against an
artifact its own derivation did not produce; where no independent artifact
exists it MUST be marked provisional and MUST NOT be presented as validated."*
— and constitution **Principle I as amended at v1.1.0**, which was amended
specifically to cover the **derived-but-wrong verifier**: a verifier derived
from the same source as the thing it checks can be confidently wrong, and that
case fits neither branch of the principle as originally ratified.

Two jobs, and the second is what makes the first load-bearing:

- **T122** decides `validated` or `provisional`, against the target's published
  specification, with a named reason when it is the second.
- **T123** makes `verified` **unreachable** from a provisional contract, rather
  than merely refused when someone asks for it.

## What the published specification is here, and where it comes from

FR-002 settles this and it is worth stating precisely, because the answer
decides what this module may do:

> The served-operation set MUST be obtained from a **machine-readable
> specification the target itself publishes**, at operation granularity. Source
> analysis MUST remain reproducible from the codebase alone, with no network
> input and no dependency on any running deployment.

So the published specification is a **runtime-fetched artifact** — spec.md is
explicit that it is *"fetched from the running deployment"* — and it arrives here
as a `ServedOperationSet`, produced by the admission stage **above** source
analysis. This module therefore takes it as an argument and **never fetches
it**. `tests/unit/test_validate.py::test_this_module_reads_no_network_and_no_running_deployment`
scans for that rather than trusting the convention, on the same reasoning
`src/analysis/served_operations.py` gives for scanning its own imports.

That layering has a consequence which is a **legitimate outcome and not a gap**:
a target with no running deployment has no published specification, so every
contract derived from it is `provisional`. Both committed analyzer fixtures are
in exactly that position. See the fixture note below.

## Absence is not agreement, at three separate depths

The cheap implementation of this feature promotes a contract whenever nothing
contradicts it. It passes every test written about the agreeing case and it is
wrong at three depths, so `ProvisionalReason` names each one separately:

1. **No specification at all** — `NO_SPECIFICATION`.
2. **A specification that does not serve this operation** —
   `OPERATION_NOT_SERVED`.
3. **An entry that declares nothing about parameters** — `SPECIFICATION_SILENT`.

None of the three is agreement, and a single `is_validated` boolean cannot tell
them apart from each other or from `SPECIFICATION_DISAGREES`. This is the pair
`src/analysis/derived_record.py` holds apart — **absent** against
**provisional** — one level up, and the reasoning transfers: *"a record that
claims nothing is not the same fact as no record."*

An **explicitly empty** parameter list is deliberately *not* silence. It is a
claim that the operation takes no parameters, and a derivation that read three
genuinely disagrees with it.

## What `validated` is asserted to mean, and the three things it is not

`validated` is a claim about the **derivation**: an artifact the derivation did
not produce agreed with it. Stated negatively, because each of these is a
reading somebody will otherwise take:

1. **It is not a claim that any response is correct.** Conformance to a declared
   shape is explicitly **not** accepted as verification (T124, FR-022), and the
   recorded v1 constraint is that a shipping verifier *cannot be schema-only and
   must recompute the reported quantity via the application's own API*.
   Promotion is a **necessary** condition for a later `Verified` and never a
   sufficient one.
2. **It is not verified correspondence between the source and the deployment.**
   `src/analysis/correspondence.py::verified_correspondence` always raises: v1
   has no mechanism binding a commit to a running instance, and FR-057 forbids
   presenting one. So the association between the source symbol this contract
   was derived from and the operation the specification describes rests on an
   operator **declaration**. What promotion does buy is exactly what FR-057
   says it buys — a source reference pointing at the **wrong application**
   surfaces here as contracts that fail to validate. The residual FR-057 names,
   *the right repository at the wrong commit*, survives this check.
3. **It does not promote the contract's checks.** They stay `provisional`. A
   specification agreeing about parameter names says nothing about whether an
   aggregate recomputation is correct, and promoting a check on that evidence
   would be the derived-but-wrong verifier arriving through the mechanism built
   to catch it. Nothing in a published specification declares an aggregate
   relationship, so no check-level artifact exists in v1;
   `test_promotion_does_not_promote_the_contracts_checks` holds this open.

## The schema ruling: **no version bump. 1.1.0 already carries this.**

A validation status is **not** a new field. T121 put `validation_status` inside
`provenance` at 1.1.0 and `src/contracts/schemas.py` already lists it in
`FR_026_PROVENANCE_FIELDS`, so both derived kinds already **require** it. What
promotion changes is a field's **value**, from `provisional` to `validated`, and
the conditional seventh field `validated_against` — which
`FR_026_PROVENANCE_FIELDS` deliberately excludes and which
`ArtifactSchema._validate_provenance` permits, because it checks the presence of
the required six and does not reject additional keys.

So there is no 1.2.0 here, and T121's precedent is **followed rather than
departed from**: 1.1.0 moved because two different *shapes* would otherwise
claim one schema version, and no shape moves now.

The binding consideration — *a contract that reads back with no validation
status must not be indistinguishable from one that read back as `validated`* —
was already discharged by T121 and OD-32, by three mechanisms at three layers,
and this module adds a fourth requirement to none of them:

- the **schema** refuses a 1.1.0 provenance missing `validation_status`;
- `Provenance.from_payload` refuses an absent or unknown status rather than
  defaulting it;
- an absent provenance *entirely* is `ProvenanceState.ABSENT`, a third value
  distinct from both `PROVISIONAL` and `VALIDATED`, and `require_provenance()`
  raises rather than substituting a record.

## T123 — why the gate is a construction and not a check

`src/contracts/result.py` has held a runtime refusal since T021, against the
pair `VERIFIED` and a provisional corroboration.

That satisfies the sentence's letter. It does not satisfy its point: a later
caller can construct the forbidden pair and only find out at run time. **The
sharper defect this paragraph used to describe as live is fixed.** The field was
`provisional: bool = False`, and `False` meant both *this contract was
corroborated* and *nobody said* — the `spend_usd is None` against a measured
zero defect wearing a boolean, with the claim-making value as the default, so a
caller holding a provisional contract who omitted the flag got a `Result`
reading `VERIFIED` that tripped nothing. T126 replaced it with a required
`Corroboration`, whose `NOT_STATED` member is the absent case named, and
`Result` refuses `VERIFIED` alongside either absent reading.

So the mechanism here is **unreachability**:

- `ProvisionalContract` and `ValidatedContract` are **distinct types with no
  inheritance between them**, so no signature demanding the second accepts the
  first.
- `Verified` names `ValidatedContract` in its own constructor. There is no
  argument a holder of a `ProvisionalContract` can pass.
- `ProvisionalContract` has **no method whose return type includes `Verified`**,
  asserted by introspection so a method added later is covered.
- `Verified` additionally requires a check that **recomputes** and a
  `RecomputationAgreement` carrying **two values it compares itself**. There is
  no `agreed=True` shortcut, because a boolean would let a caller assert an
  agreement it never computed.

The recomputation requirement is what keeps **T124 and T132 open**. A
shape-and-type-only control verifier holds no recomputation and therefore cannot
construct `Verified` at all — which is precisely what T132 will assert over an
injected fault corpus. This module defines the *shape of the evidence* and
refuses without it; **T124 still owns obtaining the recomputed value by an
independent path through the application's own API.** Nothing here executes a
recomputation.

## What is type-enforced and what is refused at run time

Stated plainly because the honest partial is this repository's accepted form,
and because one half of it is enforced **only in CI and not on a laptop**:

- **Type-enforced**: the distinct types, the return annotations, and
  `Verified.issued_by`. A type checker rejects the forbidden program. **mypy is
  not in this project's venv**, so the arm exercising this skips with a named
  reason where mypy is absent rather than passing over nothing — but the
  workflow's `invariants` job runs `python -m mypy` over `src/` against a
  declared error count, and `tools/instruments.py` registers that step as a
  gate. A local skip is a fact about the machine, not about the gate set.
- **Construction-enforced, needing no checker**: `Verified` has no constructor
  that does not take a `ValidatedContract`. This holds under a bare interpreter
  and is what most arms assert.
- **Runtime-refused**: an `isinstance` backstop for what Python permits and a
  checker would have caught, plus `Result`'s pre-existing guard.
- **Not covered**: Python has no sealed constructor, so a caller can build a
  `ValidatedContract` by hand. What it cannot build is one naming no artifact,
  or one naming the source file it was derived from — `Provenance.__post_init__`
  refuses that pair. `Result(VERIFIED, payload)` with the corroboration omitted
  is **no longer** constructible — `Corroboration` has no default — which is the
  residual T123 recorded executably and T126 closed.

## No tolerance, anywhere

`RecomputationAgreement` compares by **exact equality** and refuses a float pair
by **raising**. That refusal carries **no named reason, and carries none by
design** — it is a *construction* error, raised because this type was handed an
operand it cannot compare, and FR-024's named reasons are *verification
outcomes*. The machine-readable reason for an unstated precision is
`RefusalReason.PRECISION_NOT_STATED`, which lives beside the verifier in
`src/runtime/verify.py` and is produced there **before** a pair ever reaches
this type.

It is not raised from here and **cannot be**: that module imports this one, so
naming its enum here would close an import cycle. The layering is the reason the
two refusals read alike and are not duplicates — see `_admissible_precision`,
whose docstring states why running ahead of this type is the mechanism rather
than an optimisation.

A tolerance constant here would pick a precision no source stated, which is the
substitution FR-024 exists to forbid.

## The two committed fixtures, and which status each yields

- **`inventory-service/`** — three contracts, **all `provisional`**, reason
  `NO_SPECIFICATION`. It is source on disk with no running deployment, so no
  published specification exists to compare against. This is the safe and
  correct outcome and it is not papered over.
- **`no-derivable-checks/`** — **no contracts at all**, so **no validation
  status**. The question *"which status does this fixture yield"* has no answer
  for it, and an answer of `provisional` would be wrong in a way that matters:
  it would mean a contract existed.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Any, Mapping, Sequence

from src.analysis.derive import DerivedCheck, DerivedContract
from src.analysis.provenance import Provenance, ValidationStatus
from src.analysis.served_operations import ServedOperation, ServedOperationSet
from src.contracts.result import Corroboration, Result, VerificationOutcome

__all__ = [
    "NotVerifiable",
    "ProvisionalContract",
    "ProvisionalReason",
    "RecomputationAgreement",
    "ValidatedContract",
    "ValidationError",
    "Verified",
    "validate_contract",
]


class ValidationError(ValueError):
    """A validation this module refuses to perform or to record."""


class ProvisionalReason(Enum):
    """Why a contract was not promoted. Closed, and each member is a fact.

    Five members rather than one boolean, because *"nothing corroborated this"*
    has four genuinely different causes and the promotion bug is the one that
    reads three of them as agreement.
    """

    #: No published specification was supplied at all.
    NO_SPECIFICATION = "no_specification"
    #: A specification was supplied and does not serve this operation.
    OPERATION_NOT_SERVED = "operation_not_served"
    #: The entry exists and declares nothing this comparison can read.
    SPECIFICATION_SILENT = "specification_silent"
    #: The entry declares something in a shape this comparison cannot read, or
    #: the specification cites no artifact a promotion could name.
    SPECIFICATION_UNREADABLE = "specification_unreadable"
    #: The entry declares parameters and they are not the ones derived.
    SPECIFICATION_DISAGREES = "specification_disagrees"


# ---------------------------------------------------------------------------
# The outcome tokens.
#
# Deliberately **not** a fourth and fifth member of `VerificationOutcome`.
# `src/contracts/result.py` owns that enum and T126/T127 own its reconciliation
# into three exhaustive states; these are analysis-side tokens whose only job is
# to make one combination unconstructible. Each maps to an existing member.


@dataclass(frozen=True)
class NotVerifiable:
    """What a provisional contract can produce. Carries a reason, always.

    A reason is required because *"not verifiable"* with no reason is
    indistinguishable from nobody having tried — the same argument
    `Result.__post_init__` makes, held here so the reason exists before the
    `Result` is built rather than being supplied at the boundary.
    """

    reason: str

    def __post_init__(self) -> None:
        if not self.reason.strip():
            raise ValidationError(
                "a NOT_VERIFIABLE outcome with no reason is indistinguishable "
                "from nobody having tried. FR-025 requires the distinction and "
                "this type refuses to carry the blank."
            )

    def outcome(self) -> VerificationOutcome:
        return VerificationOutcome.NOT_VERIFIABLE


@dataclass(frozen=True)
class RecomputationAgreement:
    """Two values, compared here by exact equality. No tolerance.

    **The two values are the evidence.** There is no `agreed` flag, because a
    boolean would let a caller assert an agreement it never computed, and that
    is the whole failure this type is shaped against.

    This type does **not** obtain either value. T124 owns recomputing the
    reported quantity by an independent path through the application's own API;
    what arrives here is the pair it produced.
    """

    reported: Any
    recomputed: Any

    def __post_init__(self) -> None:
        for label, value in (("reported", self.reported), ("recomputed", self.recomputed)):
            # Before the numeric checks: `True == 1`, so a boolean would compare
            # equal to a count and agree with it.
            if isinstance(value, bool):
                raise ValidationError(
                    f"{label} is the bool {value!r}. A boolean is not a "
                    "recomputed quantity, and `True == 1` in Python — so a "
                    "boolean here would compare equal to a count of one and "
                    "agree with it."
                )
            if isinstance(value, float):
                raise ValidationError(
                    f"{label} is the float {value!r}. This comparison is exact "
                    "equality and no tolerance is defined, so the pair is "
                    "refused rather than compared under a precision no source "
                    "stated (FR-024). This is a construction error and it "
                    "carries no named reason: the machine-readable reason for "
                    "an unstated precision is "
                    "RefusalReason.PRECISION_NOT_STATED in "
                    "src/runtime/verify.py, which refuses there before a pair "
                    "reaches this type. Reaching this message instead means "
                    "the type was constructed directly, bypassing the "
                    "verifier."
                )
        if self.reported != self.recomputed:
            raise ValidationError(
                f"the reported value {self.reported!r} and the independently "
                f"recomputed value {self.recomputed!r} are not equal, so there "
                "is no agreement to record. A disagreement is a *result* and "
                "belongs to the verifier that found it (T124) — this type "
                "holds agreements only, so that holding one is evidence."
            )

    @property
    def value(self) -> Any:
        return self.reported


@dataclass(frozen=True)
class Verified:
    """The only value in this module that means **verified**.

    `issued_by` is a `ValidatedContract` and there is no other constructor. That
    is T123: a `ProvisionalContract` is an unrelated type, so there is no
    argument its holder can pass here, and no method on it returns this.
    """

    issued_by: "ValidatedContract"
    check: DerivedCheck
    agreement: RecomputationAgreement

    def __post_init__(self) -> None:
        if not isinstance(self.issued_by, ValidatedContract):
            raise TypeError(
                "Verified.issued_by must be a ValidatedContract; got "
                f"{type(self.issued_by).__name__}. A provisional contract can "
                "produce NOT_VERIFIABLE and never VERIFIED (constitution "
                "Principle I as amended at v1.1.0, which was amended for the "
                "derived-but-wrong verifier: a verifier derived from the same "
                "source as the thing it checks can be confidently wrong)."
            )
        if not self.check.recomputes():
            raise TypeError(
                f"{self.check.operation_id}/{self.check.quantity}: this check "
                f"is `{self.check.check_kind.value}` and does not recompute, so "
                "it cannot produce VERIFIED. Conformance to a declared shape is "
                "explicitly not accepted as verification (FR-022, T124), and a "
                "shipping verifier cannot be schema-only. This is also what "
                "keeps T132's shape-and-type-only control verifier "
                "distinguishable from the real one: the control holds no "
                "recomputation, so it cannot reach this state at all."
            )
        if not isinstance(self.agreement, RecomputationAgreement):
            raise TypeError(
                "Verified.agreement must be a RecomputationAgreement, which "
                "carries the two values and compares them itself. A boolean or "
                "a truthy placeholder would let a caller assert an agreement "
                "nobody computed."
            )

    def outcome(self) -> VerificationOutcome:
        return VerificationOutcome.VERIFIED

    def to_result(self, *, payload: Any) -> Result:
        """A `Result` this token vouches for. The corroboration is earned.

        `CORROBORATED` is the only value `Result` admits alongside `VERIFIED`,
        and this token is the thing that earns it: it cannot exist without a
        `ValidatedContract` and a check that recomputes. Staleness is left at
        its default — a verification token bears on the contract, not on the
        freshness of the served-operation set, and `NOT_STATED` is the honest
        answer rather than `FRESH`.
        """
        return Result(
            VerificationOutcome.VERIFIED,
            payload=payload,
            corroboration=Corroboration.CORROBORATED,
        )


# ---------------------------------------------------------------------------
# The two contract states. Distinct types, no inheritance.
#
# **`ValidatedContract` is defined first, and the order is load-bearing for the
# removal proof rather than for the code.** With `ProvisionalContract` first, the
# tamper that makes it a subclass of `ValidatedContract` produces a module that
# raises `NameError` on import, so the test that reads the class relationship
# fails because nothing loaded — a failure any tamper would have produced, which
# proves nothing about the type distinction. In this order the tamper yields a
# working module with a genuine subclass relationship, and the test fails for the
# reason its proof names.


@dataclass(frozen=True)
class ValidatedContract:
    """A derived contract the published specification agreed with.

    `validated_against` names the artifact, and `Provenance.__post_init__`
    refuses one that is the source file the derivation read — so this type
    cannot be built to validate a derivation against its own input.
    """

    contract: DerivedContract
    validated_against: str
    agreed_on: tuple[str, ...]
    #: The deployment the validating specification described. **Required, with no
    #: default**, for two reasons. FR-002 makes the served-operation set record
    #: the deployment identity it describes, so a promotion that cannot say which
    #: deployment corroborated it cites an artifact it cannot locate. And a
    #: defaulted field here would make the subclass removal proof unscoreable: a
    #: field with a default followed by `ProvisionalContract`'s two without one
    #: is a dataclass error, so the tampered module would fail to load and the
    #: proof would fail on the import rather than on the class relationship.
    deployment_id: str

    def __post_init__(self) -> None:
        if not self.deployment_id.strip():
            raise ValidationError(
                f"{self.contract.operation_id}: a validated contract names the "
                "deployment whose specification corroborated it. FR-002 makes "
                "the served-operation set record the deployment identity it "
                "describes, and a promotion with no subject cannot be checked "
                "against the artifact it cites."
            )
        if not self.validated_against.strip():
            raise ValidationError(
                f"{self.contract.operation_id}: a validated contract names the "
                "artifact that validated it. FR-026 and Principle I require an "
                "artifact the derivation did not produce, and a status with no "
                "artifact is the presented-as-validated case the requirement "
                "forbids."
            )
        if not self.agreed_on:
            raise ValidationError(
                f"{self.contract.operation_id}: this contract is validated and "
                "names nothing that agreed. A promotion that cannot say what "
                "corroborated it is indistinguishable from one that compared "
                "nothing, which is the absence-read-as-agreement defect this "
                "module exists to prevent."
            )
        # Runs the independence refusal in `Provenance.__post_init__` at
        # construction rather than at `to_document`, so a self-validating record
        # is unconstructible and not merely unpublishable.
        self.provenance()

    def provenance(self) -> Provenance:
        return replace(
            self.contract.provenance,
            validation_status=ValidationStatus.VALIDATED,
            validated_against=self.validated_against,
        )

    def verified(
        self, check: DerivedCheck, agreement: RecomputationAgreement
    ) -> Verified:
        """A `Verified` token, for a check that recomputes and agreed.

        The only path to `Verified` in this module. It does not perform the
        recomputation: `agreement` is T124's product.
        """
        return Verified(issued_by=self, check=check, agreement=agreement)

    def not_verifiable(self, reason: str) -> NotVerifiable:
        """Available here too. Promotion is necessary for `Verified`, not sufficient."""
        return NotVerifiable(reason=reason)

    def to_document(self, *, deployment_id: str) -> dict[str, Any]:
        if deployment_id != self.deployment_id:
            raise ValidationError(
                f"{self.contract.operation_id}: this contract was validated "
                f"against a specification describing {self.deployment_id!r} and "
                f"is being written as an artifact of {deployment_id!r}. FR-002 "
                "makes the served-operation set record the deployment identity "
                "it describes; writing the promotion under another deployment "
                "would cite an artifact that describes something else."
            )
        document = self.contract.to_document(deployment_id=deployment_id)
        document["provenance"] = self.provenance().to_payload()
        return document


@dataclass(frozen=True)
class ProvisionalContract:
    """A derived contract no independent artifact corroborated.

    **This type has no path to `Verified`**, and that is checked by
    introspection over its annotations rather than by a reviewer reading it.
    """

    contract: DerivedContract
    reason: ProvisionalReason
    detail: str

    def __post_init__(self) -> None:
        if not self.detail.strip():
            raise ValidationError(
                f"{self.contract.operation_id}: a provisional contract carries "
                "a reason member and a detail saying what was looked for and "
                "not found. FR-026 requires provisional to be *marked*, and a "
                "member with no detail is not diagnosable after the fact."
            )

    def provenance(self) -> Provenance:
        """The contract's provenance, still `PROVISIONAL`, still citing nothing."""
        return replace(
            self.contract.provenance,
            validation_status=ValidationStatus.PROVISIONAL,
            validated_against=None,
        )

    def not_verifiable(self) -> NotVerifiable:
        """The only outcome this contract can produce."""
        return NotVerifiable(reason=f"{self.reason.value}: {self.detail}")

    def to_result(self, *, payload: Any) -> Result:
        """The sanctioned bridge to a `Result`, which states the corroboration.

        It was the mitigation for a default: `Result.provisional` was a `bool`
        defaulting to `False`, so a caller assembling a `Result` by hand from a
        provisional contract got one that read as corroborated and tripped no
        guard. T126 removed the default rather than the hazard's mitigation —
        `corroboration` is now required — so this bridge is convenience and
        naming, and no longer the only thing standing between a provisional
        contract and a result that misreads it.
        """
        outcome = self.not_verifiable()
        return Result(
            outcome.outcome(),
            payload=payload,
            reason=outcome.reason,
            corroboration=Corroboration.PROVISIONAL,
        )

    def to_document(self, *, deployment_id: str) -> dict[str, Any]:
        document = self.contract.to_document(deployment_id=deployment_id)
        document["provenance"] = self.provenance().to_payload()
        return document


# ---------------------------------------------------------------------------
# The comparison.


def _declared_parameter_names(
    operation: ServedOperation,
) -> tuple[str, ...] | None | ValidationError:
    """The parameter names an entry declares.

    Three outcomes, kept distinct because collapsing any two of them is the
    promotion bug: `None` for **silent**, a `ValidationError` for a shape this
    cannot read, and a tuple — possibly empty — for a **claim**.
    """
    declared = operation.declared.get("parameters")
    if declared is None:
        return None
    if isinstance(declared, (str, bytes)) or not isinstance(declared, Sequence):
        return ValidationError(
            f"the entry for {operation.operation_id!r} declares parameters as "
            f"{type(declared).__name__}, which this comparison cannot read as a "
            "list of names."
        )

    names: list[str] = []
    for item in declared:
        if isinstance(item, str):
            names.append(item)
            continue
        if isinstance(item, Mapping) and isinstance(item.get("name"), str):
            names.append(str(item["name"]))
            continue
        return ValidationError(
            f"the entry for {operation.operation_id!r} declares a parameter as "
            f"{item!r}, which carries no readable name. Read as agreement it "
            "would corroborate nothing; read as silence it would discard a "
            "claim the specification makes."
        )
    return tuple(names)


def validate_contract(
    contract: DerivedContract,
    *,
    specification: ServedOperationSet | None,
    served_operation_id: str | None,
    deployment_id: str | None = None,
) -> ProvisionalContract | ValidatedContract:
    """Promote a derived contract, or mark it provisional with a named reason.

    `specification` is the published specification as the served-operation set
    FR-002 produces, **passed in and never fetched here**. `None` means the
    caller holds none, and it yields `provisional` — absence of a specification
    is not evidence of conformance.

    `served_operation_id` is the operation in that specification this contract
    is claimed to describe. It is **required and never inferred**: a derived
    contract's identifier is `module:function` and a served operation's comes
    from the specification, so any join between them is a declaration. Guessing
    one is how *fluent, plausible and wrong* arrives — finding 007 measured 15 of
    69 endpoints carrying a contract wrong about every field name on the wire
    with nothing in the output indicating it.

    `deployment_id`, when given, is the deployment the caller is validating for,
    and a specification describing a different one is **refused** rather than
    compared.
    """
    if specification is None or served_operation_id is None:
        return ProvisionalContract(
            contract=contract,
            reason=ProvisionalReason.NO_SPECIFICATION,
            detail=(
                "no published specification was supplied. FR-002 obtains it "
                "from a machine-readable specification the target itself "
                "publishes, fetched from the running deployment, and source "
                "analysis holds none. Absence of a specification is not "
                "evidence of conformance, so this contract is marked "
                "provisional rather than promoted."
            ),
        )

    if deployment_id is not None and specification.deployment_id != deployment_id:
        raise ValidationError(
            f"the supplied specification describes deployment "
            f"{specification.deployment_id!r} and this validation is for "
            f"{deployment_id!r}. FR-002 makes the served-operation set record "
            "the deployment identity it describes; comparing against another "
            "deployment's specification and recording the result would cite an "
            "artifact about something else."
        )

    operation = specification.get(served_operation_id)
    if operation is None:
        return ProvisionalContract(
            contract=contract,
            reason=ProvisionalReason.OPERATION_NOT_SERVED,
            detail=(
                f"the published specification for {specification.deployment_id} "
                f"does not serve {served_operation_id!r}; it serves "
                f"{list(specification.operation_ids())}. An operation the "
                "specification does not describe has no independent artifact, "
                "and its absence from the set is not agreement."
            ),
        )

    if not specification.source_url.strip():
        return ProvisionalContract(
            contract=contract,
            reason=ProvisionalReason.SPECIFICATION_UNREADABLE,
            detail=(
                f"the specification for {specification.deployment_id} cites no "
                "source, so a promotion could not name the artifact that "
                "validated it. FR-026 requires the artifact to be named and "
                "`Provenance` refuses a `validated` status without one."
            ),
        )

    declared = _declared_parameter_names(operation)
    if isinstance(declared, ValidationError):
        return ProvisionalContract(
            contract=contract,
            reason=ProvisionalReason.SPECIFICATION_UNREADABLE,
            detail=(
                f"{declared} Refused rather than read either way, because "
                "reading it as agreement would corroborate nothing and reading "
                "it as silence would discard a claim."
            ),
        )
    if declared is None:
        return ProvisionalContract(
            contract=contract,
            reason=ProvisionalReason.SPECIFICATION_SILENT,
            detail=(
                f"the entry for {served_operation_id!r} declares nothing about "
                "parameters, so there was nothing to agree with. Silence is "
                "not agreement: a specification that contradicts nothing "
                "corroborates nothing either. An explicitly empty list would "
                "be a different fact and is compared."
            ),
        )

    # Compared as sets. The order of named parameters carries no meaning in a
    # published specification, unlike the operation order `set_version_of`
    # preserves as a change signal.
    derived = set(contract.reads)
    published = set(declared)
    if derived != published:
        return ProvisionalContract(
            contract=contract,
            reason=ProvisionalReason.SPECIFICATION_DISAGREES,
            detail=(
                f"the derivation read {sorted(derived)} and the published "
                f"specification declares {sorted(published)} for "
                f"{served_operation_id!r}. Derived only: "
                f"{sorted(derived - published)}; declared only: "
                f"{sorted(published - derived)}. This is the signal FR-057 "
                "names — a source reference pointing at the wrong application "
                "surfaces as derived contracts that fail to validate."
            ),
        )

    return ValidatedContract(
        contract=contract,
        validated_against=specification.source_url,
        agreed_on=tuple(sorted(published)),
        deployment_id=specification.deployment_id,
    )
