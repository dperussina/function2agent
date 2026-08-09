"""T077 — the served-operation set, produced above source analysis (FR-002, **OD-06**).

**Requirement**: FR-002 — *"The served-operation set MUST be produced by a stage
separate from and above source analysis, and MUST record the deployment
identity it describes. Source analysis MUST remain reproducible from the
codebase alone, with no network input and no dependency on any running
deployment."* **OD-06** is the layering decision underneath it.

T077 asks for three things on the artifact — **deployment identity, its own
version, and its freshness** — at operation granularity. Each of the three is
a separate section below, because each one is a place this artifact could be
quietly wrong.

## The stage boundary, and how it is held rather than described

    fetch (network)  ->  admission (FR-044)  ->  THIS  ->  ...  source analysis
                                                              (codebase only)

`from_admission` is the **only** constructor that produces a set from a target,
and it takes an `AdmissionDecision`. That has two consequences worth stating:

- **There is no constructor from a codebase.** Nothing here reads a route
  table, a decorator, or a `codegraph` index. If there were such a path, the
  two stages would have merged and OD-06's *analysis stays rebuildable from the
  codebase alone* would hold only by convention. `tests/contract/
  test_served_operations.py` walks this module's imports and fails if one
  reaches the source-analysis side, because the convention is the thing that
  erodes.
- **A non-admitted decision produces nothing.** `from_admission` refuses one.
  FR-044 admits exactly `published_non_empty`, and a served-operation set built
  from a rejected target would be a set describing what a target we refused to
  talk to might serve.

## Deployment identity

`deployment_id`, carried from the admission decision rather than passed in
beside it. Two arguments for one fact is two facts, and the day they disagree
the artifact says it describes one deployment while having been built from
another's specification.

## Its own version, and why it is not the content address

`set_version` is `sha256` over the canonical form of the **operation list
alone**. It is not `schema_version` — `src/contracts/schemas.py` keeps those
two words apart deliberately — and it is deliberately **not** the artifact's
content address either, although the store computes one of those for free.

The content address is over the hashed payload, which is
`{schema_version, deployment_id, set_version, operations}`. So it moves when
**our** schema version moves. FR-028 reads a changed source-derived artifact
address as the clock having moved, and a schema release of ours is not the
deployment clock ticking. That is the FR-055 false-alarm failure one level up:
FR-055 keeps a *timestamp* out of the hash, and this keeps *our own release
cadence* out of the deployment clock's reading.

`set_version` therefore has exactly the property a clock reading needs: two
captures of the same served surface have the same version, whatever URL they
were fetched from, whenever they were taken, and whichever version of this
system took them.

**A `set_version` the target published is ignored.** If the fetched document
carries one, it is not read — this system recomputes. A version asserted by
the subject of the measurement is not a measurement, and accepting one would
let a target hold its own deployment clock still.

## Its freshness — what `captured_at` means, and what it does not

`captured_at` is **the instant this system finished reading the specification
from the target**, on this system's clock. That is all it is, and the
distinction matters because this repository has a standing open problem about
it (**O-04**, two clocks).

**What it does not mean**, each stated because each is a reading somebody will
otherwise take:

1. **It is not when the deployment last changed.** Nothing here observes that.
   `plan.md` records the reason as a property of the world rather than a gap in
   this module: *a deployment change generally has no observable change time*,
   and FR-046 forbids assuming the customer emits a deployment event.
2. **It is not the age of the content.** The document may have been generated
   at build time, cached by a CDN, or served from an artifact written weeks
   ago. `captured_at` bounds how long ago we **looked**, not how long ago the
   answer was **true**.
3. **It is therefore a lower bound on staleness and not an upper bound on
   freshness.** A set captured one second ago may already describe a deployment
   that has moved. `is_stale` answers *have we looked recently enough*, which
   is precisely and only what FR-047's ceiling asks — *"how old a
   served-operation set may be before it is refused"*.

**What this deliberately does not do, so that O-04 stays open rather than
foreclosed.** There is no `deployment_revision` field, no `changed_at`, and no
optional slot for a build identifier — even though a second clock will
eventually want one. Adding an always-empty field for a producer that does not
exist is the mistake `data-model.md` corrected on 2026-08-03 by **deleting**
`correspondence_evidence`: *"A field that can only ever be empty, on the entity
gating every session, invites a downstream reader to treat an empty value as a
passed check."* When a deployment-clock anchor arrives it will be a new field
at a new schema version with a real producer, and it will not be `captured_at`
wearing a second meaning. Overloading this field is the one move that would
foreclose O-04, because after it the two clocks are one field and the
disagreement they exist to expose is unrepresentable.

## Operation granularity

FR-002 requires the set *at operation granularity*, and `ServedOperation`
requires `operation_id` for the reason `admission.parse_operations` does: an
operation with no identifier cannot be resolved against, inspected under FR-020
(T079), or denied by name. `method` and `path_template` are required as well —
they are the join key `data-model.md` §1.3 gives derived contracts, and an
entry missing either is not addressable by the enforcement point.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from src.analysis.admission import (
    ADMISSIBLE_STATES,
    AdmissionDecision,
    AdmissionError,
)
from src.contracts.canonical import content_address

KIND = "served_operation_set"
SCHEMA_VERSION = "1.1.0"

#: What `produced_by` says on the artifact row: the component, never the host.
PRODUCER = "src.analysis.served_operations"

#: The fields an operation entry must carry. Named rather than inlined so that
#: widening the set is an edit to a declaration.
REQUIRED_OPERATION_FIELDS: tuple[str, ...] = (
    "operation_id", "method", "path_template",
)


class ServedOperationSetError(AdmissionError):
    """A served-operation set that is not the artifact FR-002 requires."""


class NotAdmittedForCapture(ServedOperationSetError):
    """A set was asked for from a target admission refused."""


# ---------------------------------------------------------------------------
# The version. A module-level function because two callers need exactly one
# definition of it: the producer below, and the 1.0.0 -> 1.1.0 migration in
# `src/contracts/migrations/`, which recovers the field for documents written
# before it existed. A second copy there would be a second derivation, and the
# two would disagree on the day one of them was edited — which is the reasoning
# `admission_record.from_decision` states for re-deriving nothing.


def set_version_of(operations: Iterable[Mapping[str, Any]]) -> str:
    """The set's own version: `sha256:` over the canonical operation list.

    Over the operations and **nothing else** — not the deployment identity, not
    the schema version, not where it was fetched from, not when. Each of those
    would put something that is not the deployment's served surface inside the
    deployment clock's reading.

    Entries are canonicalised whole, so a change to any field of any operation
    moves the version. Order is significant and is the order the specification
    listed them in: two documents differing only in operation order describe
    the same surface, but this system does not know that they do — a
    specification generator that reordered its output would be reported as a
    change, which is a false alarm the operator can see and act on, whereas
    sorting here would silently discard a real reordering if one ever mattered.
    """
    return content_address([dict(operation) for operation in operations])


# ---------------------------------------------------------------------------
# The operation.


@dataclass(frozen=True)
class ServedOperation:
    """One operation the deployment serves, at FR-002's granularity."""

    operation_id: str
    method: str
    path_template: str
    #: Everything else the specification entry declared, carried whole. The
    #: effect tier lives here rather than in a typed field on purpose: FR-010
    #: and FR-012 make the tier the *effect rule set's* answer (T081), and a
    #: typed field here would be a second place a tier is stated, one of them
    #: outside the review gate FR-012 requires.
    declared: Mapping[str, Any]

    @classmethod
    def from_entry(cls, entry: Mapping[str, Any], *, index: int) -> "ServedOperation":
        missing = [f for f in REQUIRED_OPERATION_FIELDS if not entry.get(f)]
        if missing:
            raise ServedOperationSetError(
                f"operations[{index}] carries no {missing}. FR-002 requires "
                "the served-operation set at operation granularity, and an "
                "entry missing any of "
                f"{list(REQUIRED_OPERATION_FIELDS)} is not addressable: it "
                "cannot be resolved against by the enforcement point, "
                "inspected under FR-020, or denied by name."
            )
        return cls(
            operation_id=str(entry["operation_id"]),
            method=str(entry["method"]).upper(),
            path_template=str(entry["path_template"]),
            declared=dict(entry),
        )

    def document(self) -> dict[str, Any]:
        """The entry as it is stored: what the specification declared, whole.

        The three required fields are re-stated from the parsed values rather
        than left to `declared`, so a specification that wrote `get` gets the
        normalised `GET` in both places instead of one of each.
        """
        return {
            **dict(self.declared),
            "operation_id": self.operation_id,
            "method": self.method,
            "path_template": self.path_template,
        }


# ---------------------------------------------------------------------------
# The set.


@dataclass(frozen=True)
class ServedOperationSet:
    """What a named deployment serves, when we looked, and which set it was."""

    deployment_id: str
    operations: tuple[ServedOperation, ...]
    #: ISO-8601 UTC. See the module docstring for what this means and does not.
    captured_at: str
    #: Where the specification was read from. Volatile under FR-055 and in the
    #: envelope, never under the hash.
    source_url: str

    def __post_init__(self) -> None:
        if not self.deployment_id:
            raise ServedOperationSetError(
                "a served-operation set records the deployment identity it "
                "describes (FR-002). A set with no subject cannot be compared "
                "against the next capture, which is what the deployment clock "
                "is."
            )
        if not self.operations:
            raise ServedOperationSetError(
                "a served-operation set with no operations is the state FR-044 "
                "singles out — a specification that fetched successfully and "
                "carries nothing — recorded as though it were an answer. "
                "FR-044 forbids reading it as a deployment that serves "
                "nothing, and admission rejects it before this point."
            )
        if not self.captured_at:
            raise ServedOperationSetError(
                f"{self.deployment_id}: a served-operation set records when it "
                "was captured. Without it FR-047's staleness ceiling has "
                "nothing to measure against, and a set of unknown age is "
                "indistinguishable from a fresh one at exactly the moment "
                "that difference decides whether the agent may act."
            )
        seen: set[str] = set()
        for operation in self.operations:
            if operation.operation_id in seen:
                raise ServedOperationSetError(
                    f"{self.deployment_id}: operation id "
                    f"{operation.operation_id!r} appears twice. FR-056's "
                    "inspection records an outcome *per operation* and "
                    "FR-051 compares sets by operation, so a duplicated "
                    "identifier makes one of the two entries unaddressable — "
                    "and it is the second one that would silently inherit the "
                    "first's inspection outcome."
                )
            seen.add(operation.operation_id)

    # -- the three things T077 requires ------------------------------------

    @property
    def set_version(self) -> str:
        """This set's own version. See the module docstring."""
        return set_version_of(op.document() for op in self.operations)

    def age_seconds(self, now: float) -> float:
        """How long ago this set was **captured**, in seconds.

        `now` has no default for the reason nothing in this tree takes a clock
        by default: the age is a fact about a moment the caller is asking
        about, and a module that reads the clock itself cannot be tested
        against a specific one.

        Negative is possible and is not corrected here: a capture stamped in
        the future is a clock disagreement between this system and whatever
        recorded it, and clamping it to zero would present the set as fresh on
        precisely the evidence that its timestamp cannot be trusted.
        """
        return now - _epoch(self.captured_at, self.deployment_id)

    def is_stale(self, now: float, ceiling_seconds: float) -> bool:
        """Whether the set is older than FR-047's ceiling.

        **This asks whether we have looked recently enough, and nothing
        else.** `False` is not a statement that the set is accurate; it is a
        statement that the observation behind it is within the ceiling. See
        the module docstring's point 3.
        """
        if ceiling_seconds < 0:
            raise ServedOperationSetError(
                f"a staleness ceiling of {ceiling_seconds} is not a duration. "
                "FR-047's ceiling ships a stated default marked unvalidated "
                "under FR-043; a negative one would make every set stale and "
                "read as the mechanism working."
            )
        return self.age_seconds(now) > ceiling_seconds

    def operation_ids(self) -> tuple[str, ...]:
        return tuple(op.operation_id for op in self.operations)

    def get(self, operation_id: str) -> ServedOperation | None:
        for operation in self.operations:
            if operation.operation_id == operation_id:
                return operation
        return None

    # -- construction ------------------------------------------------------

    @classmethod
    def from_admission(
        cls,
        decision: AdmissionDecision,
        *,
        captured_at: str,
    ) -> "ServedOperationSet":
        """The set for a target admission admitted. The only path from a target.

        Refuses a rejected decision rather than returning an empty set: an
        empty set is a value a caller can go on to use, and FR-044's whole
        disposition is that nothing proceeds against a target it refused.

        `deployment_id` and the operation list both come off the decision. See
        the module docstring for why neither is a separate argument.
        """
        if decision.state not in ADMISSIBLE_STATES:
            raise NotAdmittedForCapture(
                f"{decision.deployment_id} was not admitted (state "
                f"{decision.state}, criterion {decision.rule_id}), so there is "
                "no specification to build a served-operation set from. "
                "FR-044 admits exactly "
                f"{sorted(ADMISSIBLE_STATES)}, and a set built here would "
                "describe what a target this system refused to talk to might "
                "serve."
            )
        return cls(
            deployment_id=decision.deployment_id,
            operations=tuple(
                ServedOperation.from_entry(entry, index=index)
                for index, entry in enumerate(decision.operations)
            ),
            captured_at=captured_at,
            source_url=decision.specification_source,
        )

    @classmethod
    def from_document(cls, document: Mapping[str, Any]) -> "ServedOperationSet":
        """Read a stored set back, at the current schema version.

        A pre-1.1.0 document migrated forward carries `None` for `captured_at`
        (see `src/contracts/migrations/`), and this refuses it rather than
        substituting a clock. The record genuinely recorded no observation
        instant; supplying one at load time would let a set of unknown age pass
        FR-047's ceiling by virtue of having been re-read.
        """
        declared = document.get("schema_version")
        if declared != SCHEMA_VERSION:
            raise ServedOperationSetError(
                f"this document declares schema_version {declared!r}; "
                f"{KIND} is at {SCHEMA_VERSION!r}. Migrate it explicitly with "
                "`src.contracts.migrations.migrate` — a document upgraded "
                "behind the caller's back gets a new content address, and a "
                "new content address on a source-derived artifact is what "
                "FR-028 reads as drift."
            )
        captured_at = document.get("captured_at")
        if captured_at is None:
            raise ServedOperationSetError(
                "this set carries no capture time. A document stored before "
                "schema 1.1.0 recorded none and the migration marks that "
                "rather than inventing one, so there is nothing here to "
                "measure FR-047's ceiling against. Re-capture the set from "
                "the target."
            )
        entries = document.get("operations") or ()
        built = cls(
            deployment_id=str(document["deployment_id"]),
            operations=tuple(
                ServedOperation.from_entry(entry, index=index)
                for index, entry in enumerate(entries)
            ),
            captured_at=str(captured_at),
            source_url=str(document.get("source_url") or ""),
        )
        stored = document.get("set_version")
        if stored is not None and stored != built.set_version:
            raise ServedOperationSetError(
                f"{built.deployment_id}: the stored set_version {stored!r} is "
                f"not the version of the operations stored with it "
                f"({built.set_version!r}). One of the two was edited after the "
                "other, and the deployment clock cannot be read off a document "
                "that disagrees with itself."
            )
        return built

    # -- the artifact ------------------------------------------------------

    def document(self) -> dict[str, Any]:
        """The `served_operation_set` payload, at the registry's version.

        `set_version` is written even though it is recomputable, because a
        reader comparing two stored captures should not have to re-run this
        system's canonical serializer to do it — and `from_document` checks the
        two agree, so the stored copy cannot drift into being the authority.
        """
        return {
            "schema_version": SCHEMA_VERSION,
            "deployment_id": self.deployment_id,
            "set_version": self.set_version,
            "captured_at": self.captured_at,
            "source_url": self.source_url,
            "operations": [op.document() for op in self.operations],
        }


def _epoch(captured_at: str, deployment_id: str) -> float:
    """`captured_at` as epoch seconds, or a refusal naming the value.

    Refuses rather than returning a sentinel. A sentinel age would flow into
    `is_stale` and answer its question with a number nobody computed.
    """
    text = captured_at.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        raise ServedOperationSetError(
            f"{deployment_id}: captured_at {captured_at!r} is not an ISO-8601 "
            "instant, so the set's age is not computable and FR-047's ceiling "
            "cannot be applied to it."
        ) from None
    if parsed.tzinfo is None:
        raise ServedOperationSetError(
            f"{deployment_id}: captured_at {captured_at!r} names no timezone. "
            "An age computed from a naive timestamp is off by the offset "
            "between two machines nobody wrote down, and FR-047's ceiling is "
            "measured in seconds."
        )
    return parsed.timestamp()


def iso(seconds: float) -> str:
    """An epoch instant as the ISO-8601 UTC string `captured_at` carries."""
    return (
        dt.datetime.fromtimestamp(seconds, tz=dt.timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )
