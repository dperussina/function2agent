"""OD-32 — reading a stored derived contract or check back, with the version gate.

**Requirement**: FR-026 — *"Every derived contract and every derived check MUST
carry, as data, the rule that derived it, the source symbol and file it came
from, the analyzer version, a content hash, and its validation status."* —
together with FR-054's rollback obligation, which is what decides the disposition
below.

## What this module is for, and why it is a separate module

`src/analysis/derive.py` produces. This reads back. The two directions are
separated for the reason `src/analysis/admission_record.py` is separate from
`src/analysis/admission.py`: a record has two readers, the stage that just
derived it and every later stage that has to know what was derived, and only the
second one can meet an artifact written by an older build.

**It is the only place in the tree that may hold an absent provenance.** The
producer types keep `provenance` mandatory and are unconstructible without it
(`DerivedContract.__post_init__`, `DerivedCheck.__post_init__`). That asymmetry
is deliberate and it is the improvement over the precedent this module is shaped
after — see below.

## The disposition, and the precedent it comes from

The model is the journal's revision-3 migration in `src/runtime/resume.py`. When
the journal gained a model identifier and a token split, older payloads could not
be priced, and the resolution was **neither** to refuse the resume **nor** to
invent a price: a revision-1 turn comes back explicitly unpriced and is *named*
in `ResumePlan.unpriced_turns`. The load-bearing property was that `spend_usd`
became `float | None` **specifically so that UNPRICED and COST NOTHING stopped
being the same value.**

So under OD-32:

- a **1.1.0** document is read with its provenance intact, under the registry's
  own `validate` — all six fields or a refusal;
- a **1.0.0** document is read **at 1.0.0**, and where its derivation recorded no
  provenance it comes back with the provenance **explicitly absent** — `None`,
  never an empty record — and the operation is **named** in
  `LoadedDerivations.unprovenanced_operations`;
- a document from a **later** revision is **refused**. Reading unknown-future
  fields is guessing at a format this code has never seen and the direction of
  the error is unknowable. `READABLE_SCHEMA_VERSIONS` is enumerated rather than
  a bound for the same reason `READABLE_MODEL_OUTCOME_SCHEMAS` is: a bound
  accepts a revision nobody wrote a branch for.

**The absence lives on this object and in no document.** A stored artifact is
never rewritten into a 1.1.0 document with a null provenance: `1.1.0` *means*
FR-026's six fields are present, so a document asserting the version without them
would be an artifact whose declared version is false, and the next one to appear
would be indistinguishable from a current producer's bug. `src/contracts/schemas.py`
therefore refuses a null and `src/contracts/migrations/` cannot emit one — the
1.0.0 migration carries a surviving record forward and refuses everything else,
which is FR-054's rollback obligation and a different job from this one. The
precedent is exact: `decode_model_outcome` returns a `ModelResponse` with
`spend_usd=None`, and the revision-1 payload on disk stays a revision-1 payload.

**Why not refuse a 1.0.0 artifact.** It was argued in OD-32 from the requirement
and from an existing gate rather than from convenience, and the gate is the half
that forecloses it. FR-054 requires restoring the immediately prior version to be
one operator action, and
`tests/contract/test_schema_versions.py::test_every_superseded_version_has_a_migration`
holds that mechanically on the ground that *"a version bump with no migration
strands the artifacts already stored"*. Refusing would make the rollback FR-054
guarantees restore something the runtime cannot load. Refusing also does not make
a 1.0.0 artifact compliant — it makes its non-compliance unreadable, collapsing
*derived-and-untraceable* into *no artifact at all*, which is a third state and
not the one that exists. The FR-026 obligation is discharged by the artifact being
**unusable as evidence**: `require_provenance()` raises, so no consumer can obtain
six fields that were never recorded.

## Three states, not two, and they are separated at every site

`ValidationStatus` has exactly two members and gains no third: it is a claim about
evidence, and there is no evidence-claim meaning *no record exists*. So the third
state belongs here, to the reader, as `ProvenanceState`:

- `ABSENT` — no derivation recorded a provenance. A reader reaches it as
  `is_provenanced is False`, and `require_provenance()` raises.
- `PROVISIONAL` — a derivation recorded one and compared it to nothing. Reached
  as `require_provenance().validation_status`.
- `VALIDATED` — a derivation recorded one and named an independent artifact.
  Reached the same way, plus `validated_against`.

Three mechanisms carry the ABSENT/PROVISIONAL distinction rather than one, because
a single accessor is a single place for it to be lost: the boolean, the raising
accessor, and the closed three-member state. **There is deliberately no
`provenance_or_placeholder`**, on the same reasoning that gives
`ModelResponse.require_spend_usd` no `spend_usd_or_zero` companion — the coercion
is the whole defect, and a helper offering it would be taken up by the first
caller who found this inconvenient.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Mapping

from src.analysis.provenance import (
    Provenance,
    ProvenanceError,
    ValidationStatus,
)
from src.contracts.schemas import DERIVED_CHECK, DERIVED_CONTRACT, require

__all__ = [
    "DERIVED_KINDS",
    "PROVENANCE_REQUIRED_FROM",
    "READABLE_SCHEMA_VERSIONS",
    "DerivedRecord",
    "DerivedRecordError",
    "LoadedDerivations",
    "ProvenanceState",
    "UnprovenancedArtifactError",
    "load_derived",
]

#: The two kinds FR-026 speaks about. A tuple of the schema kinds rather than two
#: retyped strings: one owner.
DERIVED_KINDS: tuple[str, ...] = (DERIVED_CONTRACT.kind, DERIVED_CHECK.kind)

#: The schema version at which provenance became required (OD-32). Read off the
#: registry so this constant cannot disagree with the schema it describes.
PROVENANCE_REQUIRED_FROM = DERIVED_CONTRACT.version

#: Every schema version this build reads back. **Enumerated, not a bound** — a
#: bound accepts a revision nobody wrote a branch for, which is the same
#: reasoning `READABLE_MODEL_OUTCOME_SCHEMAS` carries in `src/runtime/resume.py`.
READABLE_SCHEMA_VERSIONS: frozenset[str] = frozenset({
    "1.0.0",
    PROVENANCE_REQUIRED_FROM,
})


class DerivedRecordError(ProvenanceError):
    """A stored derived artifact that cannot be read back as what it claims."""


class UnprovenancedArtifactError(DerivedRecordError):
    """An artifact with no provenance, asked for its provenance.

    A distinct type, and a subclass so that callers already catching
    `ProvenanceError` keep catching it. The distinction it carries is the one
    OD-32 exists to hold open: **absent is not provisional.** A 1.0.0 artifact
    read forward as `provisional` would be indistinguishable, at every consumer,
    from a derivation that recorded a status — and the first makes FR-026's *as
    data* unverifiable while the second is a fact. `provenance is None` is the
    first; raising this rather than substituting a record is what stops the
    second from absorbing it.
    """


class ProvenanceState(Enum):
    """The three states a reader can actually be in.

    `ABSENT` is not a `ValidationStatus` member and must not become one. A
    validation status is a claim a derivation makes about its own evidence;
    absence is the fact that no derivation made one. Collapsing them is how a
    missing record starts reading as a weak record.
    """

    ABSENT = "absent"
    PROVISIONAL = ValidationStatus.PROVISIONAL.value
    VALIDATED = ValidationStatus.VALIDATED.value


@dataclass(frozen=True)
class DerivedRecord:
    """One stored derived artifact, read back.

    `declared_schema_version` is the version the **document** carried, kept
    because *which revision this artifact was written at* is the fact that
    explains an absence — and because the document is read rather than rewritten,
    it is the version the stored artifact still declares. A caller holding an
    unprovenanced record can therefore say why: the artifact predates the
    requirement. Since a 1.1.0 document cannot lack provenance, an absence here
    always has that one explanation, and the field is what lets a reader confirm
    it rather than assume it.
    """

    kind: str
    deployment_id: str
    operation_id: str
    declared_schema_version: str
    provenance: Provenance | None

    def __post_init__(self) -> None:
        if self.kind not in DERIVED_KINDS:
            raise DerivedRecordError(
                f"{self.kind!r} is not a derived kind ({list(DERIVED_KINDS)}). "
                "FR-026 speaks about derived contracts and derived checks; a "
                "record of another kind read through this path would acquire a "
                "provenance obligation its schema does not carry."
            )
        if not self.operation_id.strip():
            raise DerivedRecordError(
                f"{self.kind}: operation_id is empty, so this record cannot be "
                "named in `unprovenanced_operations` and an absence here would "
                "be disclosed as a blank."
            )

    @property
    def is_provenanced(self) -> bool:
        """Whether a provenance record exists for this artifact.

        **The accepting condition, stated positively.** Not *"not
        unprovenanced"*: a complement over a field that later grows a third
        state answers the wrong way round on the state nobody thought of, and
        the wrong way round here is the one that lets an unprovenanced artifact
        through.
        """
        return self.provenance is not None

    @property
    def provenance_state(self) -> ProvenanceState:
        """`ABSENT`, `PROVISIONAL` or `VALIDATED` — three distinct values."""
        if self.provenance is None:
            return ProvenanceState.ABSENT
        return ProvenanceState(self.provenance.validation_status.value)

    def require_provenance(self) -> Provenance:
        """The provenance record, or a refusal naming why there is none."""
        if self.provenance is None:
            raise UnprovenancedArtifactError(
                f"{self.kind} {self.operation_id}: this artifact carries no "
                "provenance, so FR-026's six fields are not readable off it and "
                "it is refused rather than answered with a placeholder. It "
                f"declares schema_version {self.declared_schema_version!r}; "
                f"provenance became required at {PROVENANCE_REQUIRED_FROM} "
                "under OD-32, and this artifact predates it. The absence is "
                "named here rather than filled in. **This is not the same state "
                "as "
                "`provisional`**: provisional means a derivation recorded a "
                "status and compared itself to nothing, and this means no "
                "derivation recorded anything. Re-derive from source to obtain "
                "one; `LoadedDerivations.unprovenanced_operations` names every "
                "artifact in this state."
            )
        return self.provenance

    @classmethod
    def from_document(
        cls, kind: str, document: Mapping[str, Any]
    ) -> "DerivedRecord":
        """Read one stored document back, at the revision it was written at.

        **The gate is a branch on the declared version, and the document is never
        rewritten.** This is `decode_model_outcome`'s shape rather than
        `migrate`'s: a revision-1 journal payload is decoded into a
        `ModelResponse` with `spend_usd=None`, and no revision-1 payload is
        turned into a revision-3 one to make that possible. Same here. A 1.0.0
        document that recorded no provenance is *read*; it does not become a
        1.1.0 document, because a 1.1.0 document carries FR-026's six fields by
        definition and `ArtifactSchema._validate_provenance` will not let one
        claim the version without them.

        `src/contracts/migrations/` is the other direction and a different
        obligation — FR-054's rollback, rewriting a stored document forward — and
        it succeeds exactly where the six fields survive in the document. This
        method is deliberately not built on it: routing an unprovenanced artifact
        through `migrate` would require the migration to emit a null provenance,
        which is the hole OD-32 closes.

        At **1.1.0** the registry's own `validate` runs, provenance included, so
        a document whose provenance is an empty object is refused here as well as
        at `envelope.wrap` and a reader is not the one place the requirement goes
        unenforced. At **1.0.0** the same required fields are checked *minus*
        `provenance` — read off the registry rather than retyped, so the list
        cannot drift from the schema — and the provenance value gets the three
        dispositions below.
        """
        schema = require(kind)
        declared = document.get("schema_version")
        if declared not in READABLE_SCHEMA_VERSIONS:
            raise DerivedRecordError(
                f"{kind}: this document declares schema_version {declared!r}; "
                f"this build reads {sorted(READABLE_SCHEMA_VERSIONS)}. A "
                "document from a later revision is refused rather than read "
                "for the fields that happen to be recognisable, and one from "
                "an unrecognised earlier revision is refused rather than "
                "read on a best-effort basis — the direction of the error "
                "in either case is unknowable."
            )

        if declared == PROVENANCE_REQUIRED_FROM:
            schema.validate(document)
            provenance: Provenance | None = Provenance.from_payload(
                document["provenance"]
            )
        else:
            missing = [
                name for name in schema.required
                if name != "provenance" and name not in document
            ]
            if missing:
                raise DerivedRecordError(
                    f"{kind}: this {declared} document is missing {missing}. "
                    "Provenance is the only field OD-32 excuses at this "
                    "revision, and it is excused because it was not required "
                    "then; everything else in the schema's `required` was, so a "
                    "document missing one of those is malformed at its own "
                    "version rather than merely old."
                )
            provenance = _provenance_at_1_0_0(kind, document)

        return cls(
            kind=kind,
            deployment_id=str(document["deployment_id"]),
            operation_id=str(document["operation_id"]),
            declared_schema_version=str(declared),
            provenance=provenance,
        )


def _provenance_at_1_0_0(
    kind: str, document: Mapping[str, Any]
) -> Provenance | None:
    """The three dispositions a pre-OD-32 provenance value gets.

    - **absent** — no key, or an explicit `None`: returns `None`, the named
      absence. Every 1.0.0 `derived_contract` written by a build whose producer
      predates FR-026 looks like this, and so does any document a hand-written
      fixture produced, because 1.0.0 listed `provenance` in neither `required`
      nor `volatile` for that kind.
    - **a complete record** — read whole by `Provenance.from_payload`, which
      defaults nothing. This is what every artifact this repository has actually
      produced looks like: FR-026 was implemented in the producer and unenforced
      in the schema, which is the gap rather than a missing feature.
    - **anything else** — refused. A 1.0.0 `derived_check` could satisfy
      `required` with the bare string `"signature"`, and that value is neither a
      record nor an absence. Reading it as a record would invent five fields;
      reading it as an absence would discard the claim it makes. `from_payload`
      refuses a *partial* record for the same reason and with its own message.
    """
    if "provenance" not in document or document["provenance"] is None:
        return None
    value = document["provenance"]
    if not isinstance(value, Mapping):
        raise DerivedRecordError(
            f"{kind}: this 1.0.0 document's provenance is {value!r}, which is "
            "neither a provenance record nor an absence. 1.0.0 constrained the "
            "value's shape not at all — that is the gap OD-32 closes — so a "
            "value like this was permitted, and there is no honest reading of "
            "it: FR-026's six fields are not recoverable from it, and calling "
            "it absent would discard a claim the document makes. Re-derive from "
            "source."
        )
    return Provenance.from_payload(value)


@dataclass(frozen=True)
class LoadedDerivations:
    """A set of read-back artifacts, with the unprovenanced ones named.

    `unprovenanced_operations` is the `ResumePlan.unpriced_turns` of this
    module and it is here for the reason that field is there: *"a hole a caller
    can read is a fact and a hole it cannot is a discrepancy."* A caller holding
    this object can ask *"is any part of this contract set untraceable to
    source?"* without walking the records itself, and the answer survives the
    process that computed it.

    Named as the set that **is** unprovenanced rather than as a share or a
    complement, because a count says how many and a complement goes wrong on the
    state nobody thought of, while a list of identifiers says which.
    """

    kind: str
    records: tuple[DerivedRecord, ...]
    unprovenanced_operations: tuple[str, ...]

    def __post_init__(self) -> None:
        # The disclosure and the records are one fact written twice, so they are
        # cross-checked rather than trusted. A disclosure computed once and then
        # allowed to drift is the write-only field a removal proof cannot tell
        # from a field nothing reads.
        expected = tuple(
            record.operation_id for record in self.records
            if not record.is_provenanced
        )
        if self.unprovenanced_operations != expected:
            raise DerivedRecordError(
                f"{self.kind}: unprovenanced_operations reads "
                f"{list(self.unprovenanced_operations)} and the records say "
                f"{list(expected)}. The disclosure is derived from the records, "
                "so a disagreement means a caller reading one of the two gets a "
                "different answer about which artifacts are traceable."
            )
        for record in self.records:
            if record.kind != self.kind:
                raise DerivedRecordError(
                    f"{self.kind}: a {record.kind} record is in this set. The "
                    "two derived kinds carry different required fields, so one "
                    "set spanning both would disclose against a schema half "
                    "its members were not read under."
                )

    @property
    def has_unprovenanced(self) -> bool:
        return bool(self.unprovenanced_operations)


def load_derived(
    kind: str, documents: Iterable[Mapping[str, Any]]
) -> LoadedDerivations:
    """Read a set of stored documents back and name the unprovenanced ones.

    Pure. Nothing is written, so loading twice cannot produce a different
    answer, and a caller that stops reading half-way leaves nothing to
    reconcile — the same property `plan_resume` has and for the same reason.
    """
    records = tuple(
        DerivedRecord.from_document(kind, document) for document in documents
    )
    return LoadedDerivations(
        kind=kind,
        records=records,
        unprovenanced_operations=tuple(
            record.operation_id for record in records
            if not record.is_provenanced
        ),
    )
