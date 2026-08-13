"""T137 — the two clocks, as two independently versioned things (FR-027, **OD-06**).

**Requirement**: FR-027 — *"The system MUST maintain the source-derived artifact
and the deployment-derived artifact as two independently versioned things, and
MUST detect drift in each of them separately."*

**OD-06** is the decision underneath it, and it states the benefit this module
exists to cash: *"Separating the two makes the emitted catalogue a function of
two independently versioned inputs, so drift in the codebase and drift in the
deployment become separately detectable. A tool can go stale because the handler
changed or because the deployment stopped serving it, and those want different
responses — regenerate in the first case, fail closed in the second. A single
fused artifact cannot tell them apart."*

So the content of this module is **not two hash functions**. Both readings are
composed from versions that already exist:

- the deployment clock's is `served_operations.set_version_of`, built at T077
  over the canonical operation list and nothing else;
- the source clock's are the content addresses of the source-derived kinds,
  which is the input `src/contracts/schemas.py` already declares FR-028 reads.

What is owed here is their **independence** and **separate detection**, and both
are held by construction below rather than by a caller's discipline.

## The partition, and why a boolean could not express it

`schemas.py` carries one boolean, `source_derived`, and its own docstring
defines it as *"the kinds FR-028 reads for drift"*. Read against this
requirement that flag is the **union of the two clocks**, not the source clock:
`served_operation_set` is flagged `source_derived=True` and it is the
deployment-derived artifact — produced above source analysis from a
specification the target publishes, by the stage boundary `served_operations.py`
draws in its first paragraph.

That is not a defect to repair by flipping a bit. The flag has two consumers,
`tests/contract/test_canonical_determinism.py` and
`tests/contract/test_codegraph_schema_pin.py`, and both read it as *drift reads
this kind*, which is true of all three. What the flag cannot do is say **which**
clock reads it, and a shared version cannot express that one moved and the other
did not — which is the whole content of drift. `KINDS_ON_CLOCK` is that
partition, and `assert_partition_total` ties it to the registry in **both**
directions, so a ninth kind that a drift channel reads cannot appear without
being assigned to a clock, and a kind cannot be assigned to a clock without
being one a drift channel reads.

## What makes the two independent, mechanically

`reading()` refuses a version for a kind that is not on the clock being read.
That single refusal is the requirement: a source-clock reading **cannot** be
constructed with a deployment-derived input in it, so the day the deployment
moves and the source does not, the source clock's reading is byte-identical to
what it was. Independence asserted only by a test would be independence until
somebody passes the wrong mapping.

It refuses the opposite direction as well — a clock reading built over a
**subset** of its own kinds. A source clock that read `derived_contract` and
skipped `derived_check` would answer *unchanged* for every change confined to
the checks, which is a drift detector that is silent for the case it exists to
catch.

## Where the anchor goes, and where it deliberately does not

`correspondence.py` records FR-057's declared source reference and says of it
that *"a source clock with no anchor is not a clock"*. So a source reading
carries one and is refused without it, and a **deployment** reading is refused
*with* one: a deployment-clock reading anchored to a commit is the two clocks
back in one field, which is the move OD-06 exists to prevent and which
`served_operations.py` declines one level up by keeping `captured_at` from
wearing a second meaning.

The anchor is carried **beside** the version and is not hashed into it. That is
not a preference; it is the same argument T077 makes for `set_version` excluding
the deployment identity. Folding the commit into the source clock's reading
would mean a commit that changed nothing derived moves the source clock — a
false alarm with no derived contract invalidated, which is not what FR-028
detects — and, worse, it would make the source clock movable by **editing
configuration**: re-declaring `F2A_SOURCE_REF` would report source drift across
a tree nobody touched.

## The residual, named because it is real and is not closed here

A **schema release of ours** moves the source clock's reading. The source-derived
kinds' content addresses cover `schema_version`, so bumping `derived_contract`
from 1.1.0 to 1.2.0 moves the source clock with no source change behind it.
`served_operations.py` closes exactly this one level up for the *deployment*
clock, by making `set_version` a function of the served surface rather than the
content address, and says why: *"a schema release of ours is not the deployment
clock ticking"*.

The symmetric repair on the source side is a `set_version`-equivalent on
`derived_contract` and `derived_check` — a change to **those artifacts**, at a
new schema version, and not something this module can do by choosing a different
input. Until then the source clock inherits the content address, which is what
`schemas.py` declares FR-028 reads and what T136 already asserts against. The
false alarm is visible and operator-actionable rather than silent, which is the
disposition FR-055's note takes for the same class of defect.

## Two clock readings, and no assumption that either has a successor

A `Reading` is a complete value on its own. Nothing here requires that a reading
be followed by another one, and `compare` is a separate function rather than a
method or a constructor argument — deliberately, and the reason is in the
requirement text rather than in taste. **FR-031 is narrowed by FR-047**: where
the drift signal is a *failed re-fetch* there is no *after* artifact version
*"because no artifact was obtained"*, and the after term becomes FR-044's
specification state plus the timestamp of the last successful fetch. A drift
signal is therefore a **sum type**, and T139 and T140 build it.

`compare_each` is the both-artifacts-obtained case and requires both clocks on
both sides. T140's shape does not go through it and must not be made to: it
holds a `before` reading and no `after` at all.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from src.analysis.served_operations import set_version_of
from src.contracts.canonical import content_address
from src.contracts.schemas import SCHEMAS, ArtifactSchema

#: The two clock names, spelled as `data-model.md` §2.6 spells the `DriftSignal`
#: field — `source` | `deployment` — and as the two synthetic corpora already
#: declare themselves: `tests/fixtures/drift-source/corpus.json` carries
#: `"clock": "source"` and its deployment twin carries `"clock": "deployment"`.
#: A third spelling here would make the corpora and the detector disagree about
#: which clock a scenario is about.
SOURCE = "source"
DEPLOYMENT = "deployment"

CLOCKS: tuple[str, ...] = (SOURCE, DEPLOYMENT)

#: Which of FR-054's eight artifact kinds each clock reads. The partition is
#: written here rather than derived from `schemas.source_derived`, because that
#: flag is the union of the two and carries no way to say which — see the module
#: docstring. `assert_partition_total` below is what keeps the two from
#: diverging once they are two statements.
KINDS_ON_CLOCK: Mapping[str, frozenset[str]] = {
    SOURCE: frozenset({"derived_contract", "derived_check"}),
    DEPLOYMENT: frozenset({"served_operation_set"}),
}


class ClockError(RuntimeError):
    """A clock reading that cannot answer *which clock moved*."""


class ClockPartitionError(ClockError):
    """The two clocks and the registry disagree about which kinds drift reads."""


def assert_partition_total(schemas: Iterable[ArtifactSchema]) -> None:
    """The partition covers the drift-relevant kinds exactly, and overlaps nowhere.

    Checked in **both** directions against the registry, because a partition
    checked in one direction only goes blind in the other:

    - a kind on two clocks is the fused artifact OD-06 refused. Its version
      would move for either cause and *which clock moved* would have two
      answers, which is the same as having none;
    - a drift-relevant kind on **no** clock is read by nothing. Its changes are
      undetected and the omission is silent, because a detector iterating the
      clocks never visits it;
    - a kind on a clock that the registry does **not** mark drift-relevant is a
      clock reading over an artifact no drift channel publishes movement for,
      so the reading moves for a cause no requirement covers.
    """
    assigned: dict[str, str] = {}
    for clock in CLOCKS:
        for kind in sorted(KINDS_ON_CLOCK[clock]):
            if kind in assigned:
                raise ClockPartitionError(
                    f"{kind!r} is on both the {assigned[kind]!r} clock and the "
                    f"{clock!r} clock. A kind read by both is one version for "
                    "two causes, and FR-031's *which of the two clocks moved* "
                    "then has two answers — which is OD-06's fused artifact "
                    "with the seam drawn in a different place."
                )
            assigned[kind] = clock

    drift_relevant = {schema.kind for schema in schemas if schema.source_derived}
    unassigned = sorted(drift_relevant - set(assigned))
    if unassigned:
        raise ClockPartitionError(
            f"{unassigned} is read for drift by src/contracts/schemas.py and "
            "sits on neither clock, so nothing reads it and nothing says so. "
            "FR-027 requires drift detected in each of the two separately; a "
            "kind belonging to neither is detected in neither."
        )
    unknown = sorted(set(assigned) - drift_relevant)
    if unknown:
        raise ClockPartitionError(
            f"{unknown} is on a clock and is not marked `source_derived` in "
            "src/contracts/schemas.py, whose docstring defines that flag as "
            "the kinds FR-028 reads for drift. A clock reading over a kind no "
            "drift channel reads moves for a cause no requirement covers."
        )


assert_partition_total(SCHEMAS)


@dataclass(frozen=True)
class Reading:
    """One clock's reading: the versions on that clock at one observation.

    A complete value on its own. It names no successor and nothing here
    requires that it get one — FR-047 narrows FR-031 so that a failed re-fetch
    carries a *before* and no *after*, and a type that made the pair mandatory
    would foreclose T140's shape.
    """

    clock: str
    deployment_id: str
    #: `(kind, version)` pairs, sorted by kind. A tuple rather than a mapping so
    #: the reading is immutable and so two readings of the same versions are
    #: equal whatever order the caller built them in.
    versions: tuple[tuple[str, str], ...]
    #: FR-057's declared source reference, on the source clock only. Beside the
    #: version, never inside it — see the module docstring.
    source_ref: str | None = None

    @property
    def version(self) -> str:
        """One address over the whole reading, for FR-031's singular field.

        `data-model.md` §2.6 gives `DriftSignal` a `version_before` and a
        `version_after`, one string each. This is that string, and it is a
        composition over `versions` through the one canonical serializer rather
        than a second hash function: it moves exactly when some kind on this
        clock moves, and the per-kind detail stays readable beside it so a
        signal can say which artifact moved as well as which clock.
        """
        return content_address({kind: value for kind, value in self.versions})

    def document(self) -> dict[str, Any]:
        return {
            "clock": self.clock,
            "deployment_id": self.deployment_id,
            "version": self.version,
            "versions": {kind: value for kind, value in self.versions},
            "source_ref": self.source_ref,
        }


def reading(
    clock: str,
    *,
    deployment_id: str,
    versions: Mapping[str, str],
    source_ref: str | None = None,
) -> Reading:
    """One clock's reading, or a refusal naming what would have fused the two.

    `versions` maps artifact kind to that kind's version. Every kind on the
    clock must be present and no kind off it may be.
    """
    if clock not in KINDS_ON_CLOCK:
        raise ClockError(
            f"{clock!r} is not a clock. FR-027 maintains two and "
            f"data-model.md §2.6 names them {list(CLOCKS)}; a third would be "
            "a clock no drift signal can attribute movement to."
        )
    if not deployment_id:
        raise ClockError(
            f"the {clock!r} clock was read for no deployment. FR-031 requires "
            "every drift signal to state the deployment identity it applies "
            "to, and a reading with no subject cannot supply one."
        )

    expected = KINDS_ON_CLOCK[clock]
    foreign = sorted(set(versions) - expected)
    if foreign:
        other = [c for c in CLOCKS if set(foreign) & KINDS_ON_CLOCK[c]]
        raise ClockError(
            f"{foreign} is not read by the {clock!r} clock"
            + (f"; it is on the {other[0]!r} clock" if other else "")
            + ". FR-027 maintains the two as independently versioned things, "
            "and a reading mixing them moves when either input moves — so the "
            "day one changes and the other does not, the pair reports that "
            "both did, which is the one distinction drift consists of."
        )
    missing = sorted(expected - set(versions))
    if missing:
        raise ClockError(
            f"the {clock!r} clock was read without {missing}. A clock read "
            "over a subset of its own kinds answers *unchanged* for every "
            "change confined to the kinds it skipped, which is a detector "
            "that is silent for the case it exists to catch."
        )
    blank = sorted(kind for kind in versions if not str(versions[kind]).strip())
    if blank:
        raise ClockError(
            f"{blank} carries a blank version on the {clock!r} clock. Two "
            "blank versions compare equal, so a reading carrying one reports "
            "*unmoved* against any other reading that also failed to compute "
            "it — a false negative that looks exactly like a quiet clock."
        )

    if clock == SOURCE and not (source_ref or "").strip():
        raise ClockError(
            "the source clock was read with no anchor. FR-057 carries the "
            "declared source reference on every source-derived artifact as "
            "the anchor of the source clock, and src/analysis/correspondence.py "
            "states the consequence: a source clock with no anchor is not a "
            "clock. Without it a signal can report that something moved and "
            "not which source it moved from."
        )
    if clock == DEPLOYMENT and source_ref is not None:
        raise ClockError(
            f"the deployment clock was read anchored to {source_ref!r}. The "
            "deployment clock reads what a target publishes and nothing about "
            "a commit; anchoring it to one puts the two clocks back in one "
            "field, which is what OD-06 separated them to prevent."
        )

    return Reading(
        clock=clock,
        deployment_id=deployment_id,
        versions=tuple(sorted((kind, str(value)) for kind, value in versions.items())),
        source_ref=source_ref,
    )


def deployment_reading(
    *,
    deployment_id: str,
    operations: Sequence[Mapping[str, Any]],
) -> Reading:
    """The deployment clock, read from the served surface through T077's version.

    The one convenience constructor, and the asymmetry is deliberate. This
    binds `served_operations.set_version_of` so that the deployment clock
    cannot be read off anything else — a caller handing `reading()` a raw
    digest could hand it the served-operation set's **content address**, which
    moves when our own `schema_version` moves and is the false alarm T077
    argues against at length.

    The source clock gets no twin because there is nothing to bind: its
    per-kind versions are the content addresses the artifact store already
    holds, and a constructor that only forwarded them would add a name and no
    guarantee.
    """
    return reading(
        DEPLOYMENT,
        deployment_id=deployment_id,
        versions={"served_operation_set": set_version_of(operations)},
    )


@dataclass(frozen=True)
class Movement:
    """Whether one clock moved between two readings of it, and what moved."""

    clock: str
    deployment_id: str
    moved: bool
    version_before: str
    version_after: str
    #: The kinds whose versions differ. Empty exactly when `moved` is false.
    kinds_moved: tuple[str, ...]

    def document(self) -> dict[str, Any]:
        return {
            "clock": self.clock,
            "deployment_id": self.deployment_id,
            "moved": self.moved,
            "version_before": self.version_before,
            "version_after": self.version_after,
            "kinds_moved": list(self.kinds_moved),
        }


def compare(before: Reading, after: Reading) -> Movement:
    """Movement on one clock, from two readings **of that clock**."""
    if before.clock != after.clock:
        raise ClockError(
            f"a {before.clock!r} reading was compared against an {after.clock!r} "
            "one. FR-031 requires a drift signal to state which of the two "
            "clocks moved, and a cross-clock comparison moves whenever the two "
            "clocks differ from each other — which they do at rest — so it "
            "would answer *moved* on a system where nothing changed at all."
        )
    if before.deployment_id != after.deployment_id:
        raise ClockError(
            f"a reading of {before.deployment_id!r} was compared against one "
            f"of {after.deployment_id!r}. FR-031 binds a drift signal to the "
            "deployment identity it applies to; comparing two deployments "
            "reports the difference between two targets as movement in one."
        )

    before_versions = dict(before.versions)
    after_versions = dict(after.versions)
    kinds_moved = tuple(
        kind
        for kind in sorted(set(before_versions) | set(after_versions))
        if before_versions.get(kind) != after_versions.get(kind)
    )
    return Movement(
        clock=before.clock,
        deployment_id=before.deployment_id,
        moved=bool(kinds_moved),
        version_before=before.version,
        version_after=after.version,
        kinds_moved=kinds_moved,
    )


def compare_each(
    before: Mapping[str, Reading],
    after: Mapping[str, Reading],
) -> tuple[Movement, ...]:
    """FR-027's *separately*: one movement per clock, in `CLOCKS` order.

    Each movement is computed from that clock's own pair and from nothing else,
    so one clock moving cannot move the other's answer.

    Both clocks are required on both sides. A clock absent from one side is not
    *unmoved* — nothing read it — and returning a short tuple would let a
    detector iterate the result and never notice.

    **This is the both-artifacts-obtained case, and it is not the only case.**
    FR-047 narrows FR-031 so that a failed re-fetch has no *after* artifact
    version at all. That signal does not come through here; it carries a
    `before` reading and FR-044's specification state, and T140 builds it.
    """
    for label, side in (("before", before), ("after", after)):
        absent = [clock for clock in CLOCKS if clock not in side]
        if absent:
            raise ClockError(
                f"no {absent} reading on the {label} side. FR-027 requires "
                "drift detected in each of the two clocks separately, and a "
                "clock nobody read is not a clock that did not move."
            )
    return tuple(compare(before[clock], after[clock]) for clock in CLOCKS)
