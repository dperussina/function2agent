"""T009 — the eight artifact kinds FR-054 enumerates, each carrying a schema version.

FR-054's list, read literally and in its own order:

    the served-operation set, derived contracts and derived checks, the
    effect-gate rule set and its deny list, the egress policy, FR-048's
    declared location set and FR-049's bounds, and the admission decision

Eight kinds. The deny list is part of the effect-gate rule set rather than a
ninth: FR-054 joins them with "and its", and separating them would let a rule
set be rolled back to a version whose deny list it never shipped with.

**What a schema declares, and why each part is not optional.**

- `version` is the schema's own version, distinct from the *content* version of
  any artifact under it (Principle VIII, and Principle VI's separation of
  identity from version). Bumping one must not be mistaken for bumping the
  other, so they are two words everywhere.
- `required` is what the payload must carry.
- `volatile` is the FR-055 obligation made declarative: every field whose value
  varies between two runs over the same input. These are moved into the
  envelope BESIDE the hash, never under it. `src/contracts/envelope.py` does
  the moving and refuses to hash a payload that still looks volatile.
- `source_derived` marks the kinds FR-028 reads for drift. A changed content
  address on one of these is what the drift detector treats as source change,
  which is why a non-canonical serializer is a false-alarm generator (FR-055's
  note) and why these kinds get the strictest volatility scan.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

SCHEMA_REGISTRY_VERSION = "1.0.0"


class SchemaError(ValueError):
    """A payload that does not satisfy its declared schema."""


@dataclass(frozen=True)
class ArtifactSchema:
    """One of FR-054's eight kinds."""

    kind: str
    version: str
    requirement: str
    required: tuple[str, ...]
    volatile: tuple[str, ...]
    source_derived: bool
    description: str

    # Fields that look volatile to the scanner but are stable by construction.
    # Every entry needs a justification, because this is the escape hatch and
    # an undocumented escape hatch is how the FR-055 discipline erodes.
    stable_despite_appearance: Mapping[str, str] = field(default_factory=dict)

    def validate(self, payload: Mapping[str, Any]) -> None:
        missing = [k for k in self.required if k not in payload]
        if missing:
            raise SchemaError(
                f"{self.kind}: payload is missing {missing}. Declared required "
                f"fields are {list(self.required)}."
            )
        declared = payload.get("schema_version")
        if declared != self.version:
            raise SchemaError(
                f"{self.kind}: payload declares schema_version "
                f"{declared!r}, registry holds {self.version!r}. A payload "
                "whose schema version is absent or stale is not migrated "
                "silently — see src/contracts/migrations/."
            )


# ---------------------------------------------------------------------------
# The eight.

SERVED_OPERATION_SET = ArtifactSchema(
    kind="served_operation_set",
    version="1.0.0",
    requirement="FR-002, FR-054",
    required=("schema_version", "deployment_id", "operations"),
    volatile=("captured_at", "source_url", "analyzer_host"),
    source_derived=True,
    description="What a named deployment actually serves, established above "
                "analysis from a specification the target publishes.",
)

DERIVED_CONTRACT = ArtifactSchema(
    kind="derived_contract",
    version="1.0.0",
    requirement="FR-054, Principle I",
    required=("schema_version", "deployment_id", "operation_id", "reads",
              "writes", "preconditions", "postconditions", "failure_taxonomy"),
    volatile=("derived_at", "source_path", "analyzer_host"),
    source_derived=True,
    description="What an operation requires and returns, derived from source. "
                "Principle I's node contract.",
)

DERIVED_CHECK = ArtifactSchema(
    kind="derived_check",
    version="1.0.0",
    requirement="FR-054, Principle I",
    required=("schema_version", "deployment_id", "operation_id",
              "check_kind", "expression", "provenance", "confidence"),
    volatile=("derived_at", "source_path"),
    source_derived=True,
    description="A verifier derived from a return type or postcondition. "
                "Carries provenance and confidence because Principle I "
                "requires a verifier with no independent validating artifact "
                "to be marked provisional.",
)

EFFECT_GATE_RULE_SET = ArtifactSchema(
    kind="effect_gate_rule_set",
    version="1.0.0",
    requirement="FR-054",
    required=("schema_version", "deployment_id", "rules", "deny_list"),
    volatile=("published_at",),
    source_derived=False,
    description="The effect-gate rules and the deny list they ship with. One "
                "artifact: FR-054 joins them, and a rule set rolled back to a "
                "deny list it never shipped with is a hole.",
)

EGRESS_POLICY = ArtifactSchema(
    kind="egress_policy",
    version="1.0.0",
    requirement="FR-008 to FR-019, FR-054",
    required=("schema_version", "deployment_id", "allowed_methods",
              "allowed_paths", "deny_rules"),
    volatile=("published_at",),
    source_derived=False,
    description="The allowlist the enforcement point reads. Consumed by the "
                "Go proxy; versioned here.",
    stable_despite_appearance={
        "allowed_paths[]": "a URL path template, not a filesystem path. It is "
                           "operator-declared configuration and is "
                           "byte-identical across two runs over the same "
                           "input, which is the FR-055 test — the scanner "
                           "matches on shape and cannot tell the two apart.",
        "deny_rules[].path": "the same: a URL path pattern in a declared deny "
                             "rule.",
    },
)

DECLARED_LOCATION_SET = ArtifactSchema(
    kind="declared_location_set",
    version="1.0.0",
    requirement="FR-048, FR-054",
    required=("schema_version", "set_version", "deployment_id", "locations"),
    volatile=(),
    source_derived=False,
    description="FR-048's declared filesystem locations. Already implemented "
                "in src/supervisor/location_set.py; registered here so it is "
                "versioned and rollback-navigable with the other seven.",
    stable_despite_appearance={
        "locations[].source": "a declared mount source is configuration the "
                              "operator wrote, not an observation of this "
                              "host. It is identical across two runs over the "
                              "same input, which is the FR-055 test.",
        "locations[].target": "the in-namespace path, fixed by the same "
                              "declaration.",
    },
)

BOUNDS = ArtifactSchema(
    kind="bounds",
    version="1.0.0",
    requirement="FR-049, FR-054, Q-10",
    required=("schema_version", "deployment_id", "memory_max_bytes",
              "cpu_max", "cpu_total_seconds", "pids_max"),
    volatile=(),
    source_derived=False,
    description="FR-049's resource bounds. No value here has a default "
                "(Q-10); the artifact records what was configured, and its "
                "absence is a startup failure rather than a fallback.",
)

ADMISSION_DECISION = ArtifactSchema(
    kind="admission_decision",
    version="1.0.0",
    requirement="FR-020, FR-044, FR-054",
    required=("schema_version", "deployment_id", "admitted", "rule_id",
              "reason"),
    volatile=("decided_at", "decided_by_host"),
    source_derived=False,
    description="The recorded outcome of FR-044 and FR-020 for a named "
                "target.",
)

SCHEMAS: tuple[ArtifactSchema, ...] = (
    SERVED_OPERATION_SET,
    DERIVED_CONTRACT,
    DERIVED_CHECK,
    EFFECT_GATE_RULE_SET,
    EGRESS_POLICY,
    DECLARED_LOCATION_SET,
    BOUNDS,
    ADMISSION_DECISION,
)

BY_KIND = {schema.kind: schema for schema in SCHEMAS}
KINDS = frozenset(BY_KIND)

# FR-054 says eight. Asserted at import so a ninth kind added without reading
# the requirement fails immediately rather than at whatever test runs first.
assert len(SCHEMAS) == 8, (
    f"FR-054 enumerates eight artifact kinds; the registry holds "
    f"{len(SCHEMAS)}. Adding a kind is a specification change."
)
assert len(BY_KIND) == 8, "two schemas share a kind name"


def require(kind: str) -> ArtifactSchema:
    try:
        return BY_KIND[kind]
    except KeyError:
        raise SchemaError(
            f"{kind!r} is not one of FR-054's eight artifact kinds "
            f"({sorted(KINDS)}). An artifact outside the eight is not "
            "versioned, not content-addressed, and not rollback-navigable."
        ) from None
