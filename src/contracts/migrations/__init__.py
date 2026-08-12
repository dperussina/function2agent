"""T014 — schema-version migrations, with one exercised from the first commit.

**Why a migration exists on day one.** A migration framework with no migration
in it is untested scaffolding, and the first real migration is always written
under pressure against data that already exists. The one registered here is not
invented for the exercise: it is a schema change this repository actually made.
`declared_location_set` entries did not originally carry `rule_id` and
`justification`; they were added when FR-048's location set was required to name
the rule that declares each location, and the committed fixture had to be
rewritten. That change is what `LocationSet_0_9_0_to_1_0_0` performs.

**The rules this framework enforces, each because the alternative is silent
corruption:**

- A migration is registered for exactly one `(kind, from_version)` pair, so two
  migrations cannot both claim a document.
- Migrating is explicit. `wrap()` refuses a stale `schema_version` rather than
  upgrading behind the caller's back — a payload silently migrated gets a new
  content address, and a new content address on a source-derived artifact is
  what FR-028 reads as source drift.
- A migration must not be lossy without saying so. `drops` names every field
  the migration discards, and a migration that discards a field it did not
  declare is a test failure.
- Chains are resolved and applied in order, and a chain that does not terminate
  at the registry's current version is an error rather than a best effort.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from src.contracts.schemas import (
    FR_026_PROVENANCE_FIELDS,
    SchemaError,
    require,
)


class MigrationError(SchemaError):
    """A document that cannot be brought to the current schema version."""


@dataclass(frozen=True)
class Migration:
    kind: str
    from_version: str
    to_version: str
    reason: str
    apply: Callable[[Mapping[str, Any]], dict[str, Any]]
    drops: tuple[str, ...] = field(default_factory=tuple)


def _location_set_0_9_0_to_1_0_0(document: Mapping[str, Any]) -> dict[str, Any]:
    """Add the rule identifier and justification each declaration now carries.

    A pre-1.0.0 document names locations without saying which rule declared
    them. There is no way to recover the real rule identifier from the
    document, so the migration marks each entry as unattributed rather than
    inventing one — the same choice `fs_decisions` makes for an unreadable
    path. An operator can then see which declarations predate the requirement
    instead of reading a fabricated rule id as fact.
    """
    out = dict(document)
    out["schema_version"] = "1.0.0"
    out["locations"] = [
        {
            **entry,
            "rule_id": entry.get("rule_id", "FS-DECL-MIGRATED"),
            "justification": entry.get(
                "justification",
                "migrated from a pre-1.0.0 location set, which carried no "
                "justification; the original reason for this declaration is "
                "not recoverable from the document",
            ),
        }
        for entry in document.get("locations", [])
    ]
    return out


LOCATION_SET_0_9_0 = Migration(
    kind="declared_location_set",
    from_version="0.9.0",
    to_version="1.0.0",
    reason="FR-048 requires each declared location to name the rule that "
           "declares it and why; pre-1.0.0 documents carry neither.",
    apply=_location_set_0_9_0_to_1_0_0,
)

def _admission_decision_1_0_0_to_1_1_0(
    document: Mapping[str, Any],
) -> dict[str, Any]:
    """Add FR-044's three named fields, marked unrecoverable rather than guessed.

    A 1.0.0 admission decision recorded `admitted`, a rule identifier and a
    reason. FR-044 requires the state found, the criterion that failed and what
    the operator would have to change, and **none of the three is recoverable
    from a 1.0.0 document**: `reason` is prose, and reading a state out of it
    would be a parse of English presented as a field.

    So the three arrive as `None`, which is the same choice the location-set
    migration makes for an unrecoverable rule identifier and the same choice
    `fs_decisions` makes for an unreadable path. A reader that finds `None`
    learns the record predates the requirement. `src/analysis/admission_record.py`
    refuses to reconstruct an `AdmissionDecision` from one, which is correct:
    the decision it describes named no state, and inventing one at load time
    would put a classification on a record no classifier ever ran against.

    Not `drops`: nothing is discarded. Three keys appear that were absent.
    """
    return {
        **document,
        "schema_version": "1.1.0",
        "specification_state": document.get("specification_state"),
        "failed_criterion": document.get("failed_criterion"),
        "operator_action": document.get("operator_action"),
    }


ADMISSION_DECISION_1_0_0 = Migration(
    kind="admission_decision",
    from_version="1.0.0",
    to_version="1.1.0",
    reason="FR-044 requires a rejection to name the specification state found, "
           "the admission criterion that failed and what the operator would "
           "have to change; a 1.0.0 record carries none of the three, and "
           "FR-047's recovery path compares states across admissions.",
    apply=_admission_decision_1_0_0_to_1_1_0,
)

def _served_operation_set_1_0_0_to_1_1_0(
    document: Mapping[str, Any],
) -> dict[str, Any]:
    """Add T077's set version and freshness, and only one of the two is recoverable.

    **`set_version` is recovered, not invented, and that is the whole
    difference from the migration above.** It is a function of the operation
    list, the operation list is in the document, and `set_version_of` is the
    same function the producer runs — so a migrated 1.0.0 document gets the
    version it would have been given had it been written today. Nothing is
    guessed and the value is comparable with a freshly produced one, which is
    the point: FR-028's deployment clock compares this field across captures,
    and a migrated document that carried a placeholder here would read as the
    deployment having moved on the day we released a schema.

    **`captured_at` is not recoverable and arrives as `None`.** A 1.0.0
    document recorded no observation instant, and there is nowhere to read one
    from: the artifact row's timestamp is when it was *stored*, which is a
    different fact, and the file's mtime is a fact about a filesystem.
    `ServedOperationSet.from_document` refuses a `None` here rather than
    substituting the store's clock, on the same reasoning
    `admission_record.from_document` refuses a missing state — a freshness
    value invented at load time would let a stale set pass FR-047's ceiling by
    being re-read.

    Not `drops`: nothing is discarded. Two keys appear that were absent.
    """
    from src.analysis.served_operations import set_version_of  # noqa: PLC0415

    return {
        **document,
        "schema_version": "1.1.0",
        "set_version": set_version_of(document.get("operations") or ()),
        "captured_at": document.get("captured_at"),
    }


SERVED_OPERATION_SET_1_0_0 = Migration(
    kind="served_operation_set",
    from_version="1.0.0",
    to_version="1.1.0",
    reason="T077 requires the served-operation set to carry its own version "
           "and its freshness alongside the deployment identity FR-002 "
           "requires; a 1.0.0 document carries neither.",
    apply=_served_operation_set_1_0_0_to_1_1_0,
)

def _derived_provenance_1_0_0_to_1_1_0(
    document: Mapping[str, Any], kind: str
) -> dict[str, Any]:
    """OD-32 — carry a derived artifact forward only where its provenance survives.

    **This migration recovers; it does not fill in.** A complete six-field record
    is carried forward unchanged, which is every artifact this repository has
    ever produced — `DerivedContract.to_document` has written all six since
    FR-026 was implemented, and 1.0.0's defect was that the *schema* did not
    demand them, not that the producer omitted them. That path has the same
    standing as `set_version` in the served-operation migration above: the value
    is read out of the document, so a migrated artifact is comparable with a
    freshly produced one.

    **Everything else is refused, including — especially — an absent
    provenance.** This is the one place this file departs from its three
    neighbours, all of which bring a document forward with an unrecoverable field
    marked (`FS-DECL-MIGRATED`, or `None`). Marking works there because the
    marked field is free-form prose or a nullable scalar. It does **not** work
    here, for two independent reasons:

    - A provenance record must carry a `validation_status`, and
      `ValidationStatus` has exactly two members with none meaning *not looked
      at*. Any record written for an artifact that recorded none would read
      `provisional` — a claim about evidence, asserted on behalf of a derivation
      that compared itself to nothing. That is `spend_usd: 0.0` one field over.
    - Writing `{"provenance": None, "schema_version": "1.1.0"}` avoids inventing
      a record but produces something worse: a **document claiming 1.1.0 that
      does not satisfy 1.1.0**. Storing that would put an artifact in the store
      whose declared version is a lie, and the next unprovenanced document to
      appear would be indistinguishable from a current producer's bug. So
      `ArtifactSchema._validate_provenance` refuses a null, and this function
      cannot emit one.

    The absence is real and it is not discarded — it is simply **not a document's
    to assert**. `src/analysis/derived_record.py` reads such an artifact at its
    own declared 1.0.0, yields `provenance=None` on the read-back object and
    names the operation in `LoadedDerivations.unprovenanced_operations`. That is
    exactly where `src/runtime/resume.py` puts the same distinction: a revision-1
    turn comes back unpriced from `decode_model_outcome`, and no revision-1
    payload is ever rewritten into a revision-3 one to achieve it.

    So FR-054's rollback reads: an artifact stored at 1.0.0 with its provenance
    intact migrates; one stored without provenance is readable and named
    unprovenanced, and becomes a 1.1.0 document only by being **re-derived from
    source**, which is the only operation that can produce the six fields
    honestly.

    **Not `drops`.** The accepting path discards nothing — every sub-key of a
    complete record survives. A partial record *would* lose sub-keys and
    `migrate`'s undeclared-drop guard would report it; it never reaches that
    guard because this function refuses it first. Declaring `provenance.*` in
    `drops` to make that loss legal is the move this refusal exists instead of.
    """
    value = document.get("provenance")
    if isinstance(value, Mapping):
        absent = [k for k in FR_026_PROVENANCE_FIELDS if k not in value]
        if not absent:
            return {**document, "schema_version": "1.1.0"}
        raise MigrationError(
            f"{kind}: this 1.0.0 document carries a provenance record missing "
            f"{absent}, so it cannot be brought to 1.1.0. Completing it would "
            "invent the fields FR-026 requires as data, and dropping it would "
            "discard the fields it does carry without saying so. Re-derive from "
            "source; src/analysis/derived_record.py reads this document as it "
            "stands and refuses the partial record there too."
        )
    raise MigrationError(
        f"{kind}: this 1.0.0 document's provenance is {value!r}, which is not a "
        "provenance record, so FR-026's six fields are not recoverable and no "
        "1.1.0 document can be written from it. **An absent provenance reaches "
        "this branch and is refused deliberately**: a 1.1.0 document carries "
        "all six or it does not exist, and writing one with a null provenance "
        "would store an artifact whose declared version is a lie. The absence "
        "is held instead on the read-back object — "
        "src/analysis/derived_record.py names it there, and re-deriving from "
        "source is what produces a 1.1.0 document. See OD-32."
    )


DERIVED_CONTRACT_1_0_0 = Migration(
    kind="derived_contract",
    from_version="1.0.0",
    to_version="1.1.0",
    reason="OD-32 makes FR-026's six provenance fields a schema requirement "
           "rather than a producer convention; a 1.0.0 derived contract "
           "required provenance not at all, so the record is carried forward "
           "where the document has it and the document is refused where it does "
           "not — the absence is named on the read-back object instead, because "
           "no 1.1.0 document may claim the version without the six fields.",
    apply=lambda document: _derived_provenance_1_0_0_to_1_1_0(
        document, "derived_contract"),
)

DERIVED_CHECK_1_0_0 = Migration(
    kind="derived_check",
    from_version="1.0.0",
    to_version="1.1.0",
    reason="OD-32, and for this kind `required` already named `provenance` — "
           "what 1.0.0 did not constrain is the value, so the string "
           "`\"signature\"` satisfied it. A complete record is carried forward "
           "and every other value is refused, absence included.",
    apply=lambda document: _derived_provenance_1_0_0_to_1_1_0(
        document, "derived_check"),
)

MIGRATIONS: tuple[Migration, ...] = (
    LOCATION_SET_0_9_0,
    ADMISSION_DECISION_1_0_0,
    SERVED_OPERATION_SET_1_0_0,
    DERIVED_CONTRACT_1_0_0,
    DERIVED_CHECK_1_0_0,
)

_BY_SOURCE: dict[tuple[str, str], Migration] = {}
for _m in MIGRATIONS:
    _key = (_m.kind, _m.from_version)
    if _key in _BY_SOURCE:
        raise MigrationError(
            f"two migrations claim {_key}; a document would have two futures"
        )
    _BY_SOURCE[_key] = _m


def migrate(kind: str, document: Mapping[str, Any]) -> dict[str, Any]:
    """Bring `document` to the registry's current version for `kind`.

    A document already at the current version is returned unchanged. A document
    with no path to the current version is an error, never a pass-through.
    """
    schema = require(kind)
    current = dict(document)
    seen: list[str] = []

    while True:
        version = current.get("schema_version")
        if version == schema.version:
            return current
        if version in seen:
            raise MigrationError(
                f"{kind}: migration chain revisits {version!r}; the registry "
                f"has a cycle ({' -> '.join(seen)})"
            )
        seen.append(str(version))

        migration = _BY_SOURCE.get((kind, str(version)))
        if migration is None:
            raise MigrationError(
                f"{kind}: no migration from schema_version {version!r} to "
                f"{schema.version!r}. A document that cannot be migrated is "
                "not read on a best-effort basis — add the migration or "
                "reject the document."
            )

        before = set(_flatten_keys(current))
        current = migration.apply(current)
        after = set(_flatten_keys(current))

        undeclared = (before - after) - set(migration.drops)
        if undeclared:
            raise MigrationError(
                f"{kind}: migration {migration.from_version} -> "
                f"{migration.to_version} dropped {sorted(undeclared)} without "
                "declaring it in `drops`. A lossy migration is allowed; an "
                "undeclared lossy migration is how a field disappears from "
                "an artifact nobody re-reads for a year."
            )
        if current.get("schema_version") != migration.to_version:
            raise MigrationError(
                f"{kind}: migration claimed to produce "
                f"{migration.to_version!r} but wrote "
                f"{current.get('schema_version')!r}"
            )


def _flatten_keys(value: Any, prefix: str = "") -> list[str]:
    keys: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            here = f"{prefix}.{key}" if prefix else str(key)
            keys.append(here)
            keys.extend(_flatten_keys(item, here))
    elif isinstance(value, (list, tuple)):
        for item in value:
            keys.extend(_flatten_keys(item, f"{prefix}[]"))
    return keys
