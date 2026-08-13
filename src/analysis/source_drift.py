"""T138 — source-drift detection in the same automated check run (FR-028, SC-008).

**Requirement**: FR-028 — *"A source change that invalidates a derived contract
MUST be detected in the same automated check run as the change that caused it."*

**Criterion**: SC-008 — *"**100%** of breaking source-contract changes in a
synthetic drift corpus are detected in the same automated check run as the
commit that introduced them."*

## What this module consumes rather than restates

The two clocks, their independence, and the comparison that says which of them
moved already exist at T137. A second `version_before != version_after` here
could disagree with `compare_each`, so this module does not re-compare versions.
It calls `compare_each`, keeps the source-clock movements, and turns a *moved*
source clock into an `ArtifactDrift` through `signals_from_movements` /
`from_movement` — the only constructor T139 provides.

The signal for a source-clock move is therefore an `ArtifactDrift`, not a third
member of the FR-031 sum. `FailedRefetch` is T140's shape and is not built here;
disablement of the affected operation is T146 and is not built here; the
scheduler is T141 and is not this detection.

## Invalidation is not "the document hashed differently"

FR-028 detects a change that **invalidates** a derived contract. The source
clock moves whenever a source-derived kind's content address moves, which is
the right input and the wrong verdict: an optional parameter, a new operation,
and a summary edit all change the contract document and none of them invalidate
a caller that was correct against the parent.

T154's corpus exists to make that distinction scoreable. Four of its ten
scoreable revisions are not breaking, and one of those four is byte-identical
to its parent, so a detector that reports drift on every revision — or on
every revision whose contract hash moved — scores a perfect 100% on SC-008
while being the cheap detectors the corpus was built to fail. The breaking
verdict and the drifted-operation list are derived here from the atomic diff
and are the same functions T154's loader recomputes against the committed
declarations, so a second classifier cannot silently disagree with the
instrument SC-008 is measured on.

## The same automated check run

SC-008's *"the same automated check run as the commit"* is the analysis run
that accompanies a source change, not T141's scheduled re-fetch of a published
specification. The T154 loader already refuses a check run that observes two
revisions, because a run spanning a range makes the criterion true of any
detection inside its window. This module takes one `before` and one `after`
and returns at most one finding; ranging over revisions is a caller error the
corpus loader already rejects, not a loop this detector should grow.

## What is filtered, and what must not be

`schemas.py`'s `source_derived` boolean is the **union of both clocks**, not
the source clock: `served_operation_set` is flagged `source_derived=True` and
it is the deployment-derived artifact. Filtering on that flag would report a
deployment-clock move as source drift. The partition is `KINDS_ON_CLOCK` in
`clocks.py`. This module filters `Movement.clock == SOURCE`.

A `codegraph` schema-hash mismatch fails the analysis stage (T136) and never
reaches this detector: no source-derived artifact is published, so there is no
pair of readings to compare. This module does not import the pin, does not
classify a pin mismatch, and does not have a branch that could emit FR-028
drift for one.

## The residual this module names rather than closes

A schema release of ours still moves the source clock. Source-derived kinds'
content addresses cover `schema_version`; `served_operations.set_version`
closed the symmetric case for the deployment clock. The repair is a
`set_version` equivalent on `derived_contract` and `derived_check` — a change
to those artifacts, not an input this module can choose differently. If a
schema bump turns this detector's tests red, that is the residual being
visible, which is the honest state. Do not paper over it by excluding
`schema_version` from the source reading.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from src.analysis.clocks import SOURCE, Movement, Reading, compare_each, reading
from src.analysis.drift_signal import ArtifactDrift, signals_from_movements
from src.contracts.canonical import content_address

#: A change that invalidates a caller which was correct against the parent.
#: Derived from the atomic diff; never read off a committed `"breaking"` flag.
BREAKING_KINDS = frozenset({
    "operation_removed",
    "operation_renamed",
    "required_parameter_added",
    "parameter_removed",
    "parameter_type_changed",
    "parameter_made_required",
    "return_field_removed",
    "return_field_type_changed",
})

#: A change a correct caller survives. The two sets are asserted disjoint and
#: exhaustive over everything `classify_diff` can emit, so a kind added to the
#: classifier without a verdict fails rather than defaulting to non-breaking.
NON_BREAKING_KINDS = frozenset({
    "operation_added",
    "optional_parameter_added",
    "parameter_made_optional",
    "return_field_added",
    "summary_changed",
})

ALL_KINDS = BREAKING_KINDS | NON_BREAKING_KINDS


class SourceDriftError(RuntimeError):
    """A source-drift finding that would state something untrue about source."""


def _parameters(op: Mapping[str, Any]) -> Mapping[str, Mapping[str, Any]]:
    return op.get("parameters", {})


def _returns(op: Mapping[str, Any]) -> Mapping[str, str]:
    return op.get("returns", {})


def _signature(op: Mapping[str, Any]) -> tuple[Any, ...]:
    """Everything a caller binds to. Deliberately excludes `summary`.

    A rename claim is verified by comparing this between the vanished operation
    and the appeared one. Including the summary would let a renamed operation
    whose prose was also touched read as an unrelated remove-plus-add.
    """
    params = tuple(sorted(
        (name, spec["type"], bool(spec["required"]))
        for name, spec in _parameters(op).items()
    ))
    returns = tuple(sorted(_returns(op).items()))
    return (params, returns)


def diff_contracts(
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    renamed: Sequence[tuple[str, str]] = (),
) -> tuple[tuple[str, str], ...]:
    """The atomic change set, as `(kind, operation_id)` pairs.

    `renamed` is a claim, and it is *verified* rather than trusted: a pair
    whose two signatures differ raises, because a rename that changes the
    signature is a rename and a breaking signature change, and reporting it
    as one thing loses the other.
    """
    out: list[tuple[str, str]] = []
    renamed_from = {old for old, _ in renamed}
    renamed_to = {new for _, new in renamed}

    for old, new in renamed:
        if old not in before:
            raise SourceDriftError(
                f"rename claims {old!r} was present before, and it was not"
            )
        if new not in after:
            raise SourceDriftError(
                f"rename claims {new!r} is present after, and it is not"
            )
        if _signature(before[old]) != _signature(after[new]):
            raise SourceDriftError(
                f"{old!r} to {new!r} is declared a rename, but the two "
                "signatures differ. A rename that also changes the signature "
                "carries two changes and must declare both."
            )
        # Both sides. The vanished name is what existing callers are bound to,
        # and the appeared name is what a drift signal has to point them at;
        # FR-031 wants the before and the after, so naming only one of them
        # would report half the change.
        out.append(("operation_renamed", old))
        out.append(("operation_renamed", new))

    for op_id in sorted(set(after) - set(before) - renamed_to):
        out.append(("operation_added", op_id))
    for op_id in sorted(set(before) - set(after) - renamed_from):
        out.append(("operation_removed", op_id))

    for op_id in sorted(set(before) & set(after)):
        was, now = before[op_id], after[op_id]
        old_params, new_params = _parameters(was), _parameters(now)

        for name in sorted(set(new_params) - set(old_params)):
            kind = ("required_parameter_added"
                    if new_params[name]["required"]
                    else "optional_parameter_added")
            out.append((kind, op_id))
        for name in sorted(set(old_params) - set(new_params)):
            out.append(("parameter_removed", op_id))
        for name in sorted(set(old_params) & set(new_params)):
            if old_params[name]["type"] != new_params[name]["type"]:
                out.append(("parameter_type_changed", op_id))
            was_required = bool(old_params[name]["required"])
            now_required = bool(new_params[name]["required"])
            if was_required != now_required:
                out.append((
                    "parameter_made_required" if now_required
                    else "parameter_made_optional",
                    op_id,
                ))

        old_returns, new_returns = _returns(was), _returns(now)
        for field in sorted(set(new_returns) - set(old_returns)):
            out.append(("return_field_added", op_id))
        for field in sorted(set(old_returns) - set(new_returns)):
            out.append(("return_field_removed", op_id))
        for field in sorted(set(old_returns) & set(new_returns)):
            if old_returns[field] != new_returns[field]:
                out.append(("return_field_type_changed", op_id))

        if was.get("summary") != now.get("summary"):
            out.append(("summary_changed", op_id))

    return tuple(out)


def classify_diff(diff: tuple[tuple[str, str], ...]) -> frozenset[str]:
    """The set of change kinds present. Unknown kinds raise rather than pass."""
    kinds = frozenset(kind for kind, _ in diff)
    unknown = kinds - ALL_KINDS
    if unknown:
        raise SourceDriftError(
            f"{sorted(unknown)} has no breaking verdict. Every kind the "
            "classifier can emit must sit in exactly one of BREAKING_KINDS "
            "and NON_BREAKING_KINDS, or a new kind silently defaults to safe."
        )
    return kinds


def is_breaking(kinds: frozenset[str]) -> bool:
    return bool(kinds & BREAKING_KINDS)


def drifted_operations(diff: tuple[tuple[str, str], ...]) -> tuple[str, ...]:
    """Only the operations a BREAKING kind touched.

    An operation touched exclusively by a non-breaking change is not drifted,
    which is what makes `C-010` — one breaking and one non-breaking change in
    the same commit — score differently from a revision carrying either alone.
    A detector that flags the whole commit as one blob cannot produce this
    list, and is not SC-008.
    """
    return tuple(sorted({
        op_id for kind, op_id in diff if kind in BREAKING_KINDS
    }))


def source_reading_of(
    contracts: Mapping[str, Any],
    *,
    deployment_id: str,
    source_ref: str,
    checks: Mapping[str, Any] | None = None,
) -> Reading:
    """The source clock, read off the derived artifacts through T010.

    One version per kind, each a content address over the documents of that
    kind. Several operations produce several documents; the composition is
    through the one canonical serializer, so a change confined to one
    operation moves the kind's version and a re-analysis of unchanged
    documents does not.

    The deployment clock is not read here. `reading()` would refuse a served
    surface on this clock, and composing one in would be the fused artifact
    T137 already made unconstructible.
    """
    return reading(
        SOURCE,
        deployment_id=deployment_id,
        versions={
            "derived_contract": content_address(dict(contracts)),
            "derived_check": content_address(
                dict(checks) if checks is not None else {}
            ),
        },
        source_ref=source_ref,
    )


def source_movements_of(
    before: Mapping[str, Reading],
    after: Mapping[str, Reading],
) -> tuple[Movement, ...]:
    """The source-clock slice of T137's comparison. Not a second comparison.

    `compare_each` returns one movement per clock whether or not it moved.
    Filtering on `Movement.clock == SOURCE` is the partition; filtering on
    `schemas.source_derived` would treat a deployment-clock move as source
    drift, because that flag is the union of both clocks.
    """
    return tuple(
        movement for movement in compare_each(before, after)
        if movement.clock == SOURCE
    )


@dataclass(frozen=True)
class Invalidation:
    """A derived contract was invalidated, in this check run.

    The signal is an `ArtifactDrift` built from a `Movement`. This is not a
    third `DriftSignal` variant: the FR-031 sum remains `ArtifactDrift |
    FailedRefetch`. What this record adds is the operations the breaking half
    of the diff named — the thing a commit-level blob cannot say.
    """

    signal: ArtifactDrift
    operations: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.signal.clock != SOURCE:
            raise SourceDriftError(
                f"a source-drift finding was raised on the "
                f"{self.signal.clock!r} clock. FR-028 detects a source change "
                "that invalidates a derived contract; a finding on the "
                "deployment clock is FR-029's, and mixing them is the fused "
                "artifact OD-06 separated the clocks to prevent."
            )


def detect(
    before: Mapping[str, Reading],
    after: Mapping[str, Reading],
    *,
    before_contracts: Mapping[str, Any],
    after_contracts: Mapping[str, Any],
    renamed: Sequence[tuple[str, str]] = (),
) -> Invalidation | None:
    """FR-028 in one check run: an `ArtifactDrift` naming the drifted operations, or quiet.

    Quiet when the source clock did not move, and quiet when it moved for a
    change that does not invalidate a caller — the four non-breaking revisions
    in T154, including the identical-input one. Loud only when the source clock
    moved *and* the atomic diff carries a breaking kind, and then the finding
    names only the operations that kind touched.

    A breaking diff against an unmoved source clock is a refusal, not a quiet:
    the versions were not computed from these contracts, so the comparison
    T137 made and the classification this module made have come apart, and
    agreeing with either one silently would hide the disagreement.
    """
    movements = source_movements_of(before, after)
    diff = diff_contracts(before_contracts, after_contracts, renamed)
    classify_diff(diff)
    invalidated = drifted_operations(diff)
    if not invalidated:
        return None
    signals = signals_from_movements(movements)
    if not signals:
        raise SourceDriftError(
            "the contract diff is breaking and the source clock did not move. "
            "FR-028 reads a changed content address on a source-derived "
            "artifact; a breaking change that left both versions equal means "
            "the readings were not taken from these contracts, and a quiet "
            "here would be a miss SC-008 cannot see."
        )
    return Invalidation(signal=signals[0], operations=invalidated)
