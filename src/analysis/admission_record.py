"""T074 — the admission decision, persisted as a versioned artifact (FR-044).

**Requirement**: FR-044, and FR-054 for the storage shape. *A rejection is a
supportable answer and is retained, not an error.*

## Why a rejection is written rather than raised

FR-044 requires the system to *"name which state it found, which admission
criterion failed, and what the operator would have to change"*. A rejection that
propagated as an exception would name all three to whoever was watching the
process and to nobody afterwards, and three separate readers need it later:

- **SC-018** measures the share of non-admissible targets rejected with a named
  state and a named criterion. That share is computed over records, so an
  unrecorded rejection is a target missing from the denominator.
- **FR-047's recovery path** (T152) re-runs the full admission sequence past the
  staleness ceiling and records *a new admission decision*. "New" is only
  meaningful against a stored old one.
- **FR-031** makes the specification state the "after" term of a drift signal
  raised by a failed re-fetch. That term is read off this record.

So `record()` writes both dispositions through the same path, and `admitted` is
a field rather than the difference between writing and not writing.

## Where it is stored, and why `admission_decision` is not a new table

`ArtifactStore` (T019) already holds FR-054's eight kinds content-addressed with
the ref history retained, `admission_decision` is one of the eight, and the
ownership map already makes `artifact`, `artifact_ref` and
`artifact_ref_history` the analysis role's. A dedicated table would be a fourth
place decisions live, outside FR-054's rollback navigation, and it would need an
ownership-map entry for a fact the store already holds.

The consequence worth stating: the current ref for `admission_decision` is the
**most recent** decision, admitted or not. A consumer must read `admitted`, and
a re-check that rejects moves the ref onto the rejection — which is the correct
reading of FR-047, where past the ceiling *"the system holds no founded belief
about what the deployment serves"*.

## The two guards, and why they are two

`AdmissionRecord.__post_init__` refuses two different incoherent records, and
they are separate refusals with separate messages because they are separate
defects with opposite causes:

1. **A rejection missing its criterion or its remedy.** This is FR-044's own
   requirement unmet — a decline with nothing an operator can act on, which the
   specification's Edge Cases section names as the failure mode admission
   exists to prevent.
2. **An admission carrying a failed criterion or a remedy.** This is the
   opposite error and it is not harmless: a consumer that reads
   `operator_action` to decide whether anything is outstanding would find an
   outstanding action against an admitted target.

One combined guard would be satisfied by either half, and a removal proof
against it could not tell which half it had removed.
"""

from __future__ import annotations

import datetime as dt
import json
import socket
from dataclasses import dataclass
from typing import Any, Mapping

from src.analysis.admission import (
    ADMISSIBLE_STATES,
    STATES,
    AdmissionDecision,
    AdmissionError,
    criterion_for,
)
from src.analysis.artifact_store import ArtifactStore, StoredArtifact

KIND = "admission_decision"

#: What `produced_by` and `moved_by` say on the artifact rows. A fixed string
#: rather than a hostname: those two columns say which *component* wrote the
#: record, and the host is on the record itself under FR-055's envelope.
PRODUCER = "src.analysis.admission_record"


class AdmissionRecordError(AdmissionError):
    """A record that does not state what FR-044 requires it to state."""


@dataclass(frozen=True)
class AdmissionRecord:
    """One admission decision, in the shape the artifact carries.

    Built from an `AdmissionDecision` by `from_decision`, or read back from a
    stored document by `from_document`. The two directions exist because a
    record has two readers: the stage that just decided, and every later stage
    that has to know what was decided.
    """

    deployment_id: str
    admitted: bool
    specification_state: str
    rule_id: str
    #: What the criterion required. Present on both dispositions: on a
    #: rejection it is the criterion that failed, and on an admission the one
    #: that was satisfied.
    criterion: str
    reason: str
    #: FR-044's third named thing. Empty exactly when admitted.
    operator_action: str
    #: Where the specification was fetched from, and what the classifier read
    #: off the response. Both are hashed rather than volatile — see the
    #: `stable_despite_appearance` entries on the schema for why, and note that
    #: the alternative would have been not retaining them at all.
    specification_source: str
    evidence: str

    def __post_init__(self) -> None:
        if self.specification_state not in STATES:
            raise AdmissionRecordError(
                f"{self.specification_state!r} is not one of FR-044's "
                f"classified states ({list(STATES)}). A record whose state is "
                "not in the closed set cannot be compared against a later "
                "admission, which is what FR-047's recovery path does."
            )
        if self.admitted != (self.specification_state in ADMISSIBLE_STATES):
            raise AdmissionRecordError(
                f"admitted={self.admitted} recorded against state "
                f"{self.specification_state}; FR-044 admits exactly "
                f"{sorted(ADMISSIBLE_STATES)}."
            )
        if not self.rule_id or not self.criterion or not self.reason:
            raise AdmissionRecordError(
                "a decision record names the criterion by identifier and in "
                "words, and says what was found. FR-011's discipline applies "
                "here for the same reason it applies to a denial: the rule is "
                "part of the record rather than an annotation on it."
            )

        # Guard 1 — a rejection with nothing an operator can act on.
        if not self.admitted and not self.operator_action:
            raise AdmissionRecordError(
                f"{self.deployment_id} was rejected in state "
                f"{self.specification_state} and the record says nothing "
                "about what the operator would have to change. FR-044 "
                "requires that third term, and a rejection without it is the "
                "failure mode the specification's Edge Cases section names — "
                "a product that installs successfully and then declines with "
                "no explanation."
            )

        # Guard 2 — an admission carrying an outstanding remedy. The opposite
        # defect, refused separately so that removing either guard is
        # attributable to the assertion that covers it.
        if self.admitted and self.operator_action:
            raise AdmissionRecordError(
                f"{self.deployment_id} was admitted and the record carries an "
                f"operator action ({self.operator_action!r}). Nothing has to "
                "change about an admitted target, and a consumer reading this "
                "field to decide whether anything is outstanding would find "
                "an outstanding requirement against a target that passed."
            )

    # -- construction ------------------------------------------------------

    @classmethod
    def from_decision(cls, decision: AdmissionDecision) -> "AdmissionRecord":
        """The record for a decision the classifier just produced.

        Every field is taken from the decision and its criterion; nothing is
        re-derived here. A second derivation would be a second classifier, and
        the two would disagree on the day one of them was edited.
        """
        return cls(
            deployment_id=decision.deployment_id,
            admitted=decision.admitted,
            specification_state=decision.state,
            rule_id=decision.criterion.rule_id,
            criterion=decision.criterion.criterion,
            reason=decision.criterion.reason,
            operator_action=decision.criterion.operator_action,
            specification_source=decision.specification_source,
            evidence=decision.evidence,
        )

    @classmethod
    def from_document(cls, document: Mapping[str, Any]) -> "AdmissionRecord":
        """Read a stored decision back.

        A pre-1.1.0 record migrated forward carries `None` for the three fields
        FR-044 requires (see `src/contracts/migrations/`), and this refuses it
        rather than substituting a state. The record genuinely named no state;
        supplying one at load time would put a classification on a decision no
        classifier ever made.
        """
        state = document.get("specification_state")
        if state is None:
            raise AdmissionRecordError(
                "this record carries no specification state. A decision "
                "stored before schema 1.1.0 recorded none, and the migration "
                "marks that rather than inventing one — so there is nothing "
                "here to read back as an FR-044 classification. Re-run "
                "admission against the target to obtain one."
            )
        return cls(
            deployment_id=str(document["deployment_id"]),
            admitted=bool(document["admitted"]),
            specification_state=str(state),
            rule_id=str(document["rule_id"]),
            criterion=str(document["failed_criterion"]),
            reason=str(document["reason"]),
            operator_action=str(document.get("operator_action") or ""),
            specification_source=str(document.get("specification_source") or ""),
            evidence=str(document.get("evidence") or ""),
        )

    # -- the artifact ------------------------------------------------------

    def document(self) -> dict[str, Any]:
        """The `admission_decision` payload, at the registry's current version.

        `failed_criterion` holds the criterion text on both dispositions. The
        name is FR-044's — *"which admission criterion failed"* — and on an
        admitted record it names the criterion that was **satisfied**, which is
        why `admitted` is what a reader keys off rather than the presence of
        this field. Naming it per disposition would have needed two fields, and
        a schema where one of two fields is always absent is a schema a
        consumer has to branch on to read at all.
        """
        return {
            "schema_version": "1.1.0",
            "deployment_id": self.deployment_id,
            "admitted": self.admitted,
            "rule_id": self.rule_id,
            "reason": self.reason,
            "specification_state": self.specification_state,
            "failed_criterion": self.criterion,
            "operator_action": self.operator_action,
            "specification_source": self.specification_source,
            "evidence": self.evidence,
        }

    def operator_action_or_none(self) -> str | None:
        return self.operator_action or None


def record(
    store: ArtifactStore,
    decision: AdmissionDecision,
    *,
    now: float,
    decided_by_host: str | None = None,
    decided_at: str | None = None,
) -> StoredArtifact:
    """Persist `decision`, admitted or not, and point the ref at it.

    `now` has no default for the reason nothing in this tree takes a clock by
    default: a record's timestamp is a fact about when the caller decided, and a
    module that reads the clock itself cannot be tested against a specific one.

    `decided_at` is a parameter for the same reason and falls back to `now` in
    ISO form only when the caller does not supply one. Both it and
    `decided_by_host` are volatile under FR-055 and travel in the envelope.
    """
    entry = AdmissionRecord.from_decision(decision)
    document = entry.document()
    document["decided_at"] = decided_at if decided_at is not None else _iso(now)
    document["decided_by_host"] = (
        decided_by_host if decided_by_host is not None else socket.gethostname()
    )
    return store.publish(
        KIND, document, produced_by=PRODUCER, moved_by=PRODUCER, now=now)


def latest(store: ArtifactStore) -> AdmissionRecord | None:
    """The most recent decision for this deployment, or None if there is none.

    **Admitted or not.** The ref points at the last decision taken, and a
    caller asking "was this target admitted" reads `admitted` off the record
    rather than inferring it from the record existing. Inferring it would make
    a rejection indistinguishable from a first run, which is the difference
    between "declined, here is why" and "never checked".
    """
    address = store.current_ref(KIND)
    if address is None:
        return None
    return AdmissionRecord.from_document(json.loads(store.get_bytes(address)))


def history(store: ArtifactStore) -> list[str]:
    """Every content address this kind has held, newest first.

    FR-047's recovery path records a *new* decision past the staleness ceiling;
    this is what makes the previous one still findable afterwards.
    """
    return [row["content_hash"] for row in store.history(KIND)]


def _iso(seconds: float) -> str:
    return (
        dt.datetime.fromtimestamp(seconds, tz=dt.timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


def criterion_text(state: str) -> str:
    """The criterion text a record for `state` carries.

    Exported so a consumer can compare a stored record against the registry
    without importing the criterion objects — and so a test can assert that a
    record's wording is the registry's rather than a paraphrase written at the
    call site.
    """
    return criterion_for(state).criterion
