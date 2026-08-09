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

from src.contracts.schemas import SchemaError, require


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

MIGRATIONS: tuple[Migration, ...] = (
    LOCATION_SET_0_9_0,
    ADMISSION_DECISION_1_0_0,
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
