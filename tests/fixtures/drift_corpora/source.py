"""T154 — the source-change synthetic corpus, and the diff that recomputes it.

The corpus is `tests/fixtures/drift-source/corpus.json`; this module loads it.
See `tests/fixtures/drift_corpora/__init__.py` for why the loader is not in the
fixture directory.

**Requirement**: FR-053 — *a target shape is supported only where a committed
fixture and an asserted expected output for it exist*, and *every measurable
outcome that names a corpus MUST have that fixture committed alongside the
capability it exercises rather than assembled when the measurement falls due*.
**Criterion**: SC-008 — *"**100%** of breaking source-contract changes in a
synthetic drift corpus are detected in the same automated check run as the
commit that introduced them."*

## What controls the change time here, because it is not a clock

The deployment clock has a wall-clock change time and `tests/fixtures/
drift-deployment/` has to manufacture one. The **source** clock does not: its
change time *is* the revision. So what this corpus controls is the binding
between a change and the run that must catch it — exactly one check run per
revision, enforced by `_check_run_bijection`. SC-008's *"the same automated
check run as the commit"* is unfalsifiable the moment one run is allowed to
observe a range of revisions, because then every detection is in the same run
as *some* commit in its window.

## Nothing declared here is the oracle

Every revision carries its **full** contract, not a patch. `diff_contracts`
recomputes the atomic change set between a revision and its parent,
`classify_diff` derives the change kinds from that diff, `is_breaking` derives
the verdict from the kinds, and `drifted_operations` derives the operation list
from the breaking kinds alone. All four computed values are compared against
the committed declaration at load time and a disagreement raises
`CorpusInconsistent`.

That ordering is the point. A committed `"breaking": true` that nobody
recomputes is a number, and this repository has shipped numbers nobody
recomputed. The declaration is here so it can be *contradicted*, not so it can
be read.

## The non-breaking revisions are the instrument, not filler

Four of the eleven revisions carry a change that is **not** breaking, and one
carries no change at all. They are here for the experiment-design skill's
**Rule 8**: SC-008's positive result is a detection, so a detector that reports
drift on every revision scores a perfect **100%** on a corpus made only of
breaking changes, and a perfect score on an ablation suite is the tell that the
negative control is missing.

Each of the four defeats a specific cheap detector, and they are not
interchangeable:

| Revision | Cheap detector it defeats |
|---|---|
| `C-005` optional parameter added | *the signature is not byte-identical* |
| `C-006` operation added | *the operation set changed* |
| `C-007` summary changed | *the contract document's hash changed* |
| `C-008` identical contract | *analysis ran, therefore something moved* |

`C-008` is **not** T156. T156 is a battery at `tests/batteries/
test_drift_negative.py` that scores repeated re-analysis of held-constant
source for SC-029's second clause, and it is not built. `C-008` is one
identical-input revision inside the population SC-008 is measured over, so that
population is not made exclusively of revisions where something moved.

`C-010` is the mixed revision — one breaking change and one non-breaking change
in the same commit — which is what stops the corpus from being separable into a
clean positive half and a clean negative half.

## Populations, because a count with no population is the recurring defect

`counts()` reports every figure with its denominator attached. No module here
states a bare total: `11 revisions` alone does not say that one of them is a
base revision that can carry no diff, and a detection rate whose denominator
silently includes it is a rate over the wrong population.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from tests.fixtures.drift_corpora import CorpusInconsistent

FIXTURES = Path(__file__).resolve().parent.parent
CORPUS_FILE = FIXTURES / "drift-source" / "corpus.json"

#: The reference application's published set, used to anchor the base revision.
#: A corpus describing five invented operation names would be internally
#: consistent and about nothing.
SERVED_OPERATIONS_FILE = FIXTURES / "reference-app" / "served_operations.json"

#: A change that invalidates a caller which was correct against the parent
#: revision. Derived from the atomic diff and never read from the corpus.
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


@dataclass(frozen=True)
class Revision:
    """One commit, its full contract, and the single run bound to it."""

    revision_id: str
    parent: str | None
    check_run_id: str
    contract: Mapping[str, Any]
    change_kinds: frozenset[str]
    breaking: bool
    drifted_operations: tuple[str, ...]
    expected_detection_run: str | None
    renamed: tuple[tuple[str, str], ...]
    why: str


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
    renamed: tuple[tuple[str, str], ...] = (),
) -> tuple[tuple[str, str], ...]:
    """The atomic change set, as `(kind, operation_id)` pairs.

    `renamed` is the corpus's claim, and it is *verified* rather than trusted:
    a pair whose two signatures differ raises, because a rename that changes
    the signature is a rename and a breaking signature change, and reporting it
    as one thing loses the other.
    """
    out: list[tuple[str, str]] = []
    renamed_from = {old for old, _ in renamed}
    renamed_to = {new for _, new in renamed}

    for old, new in renamed:
        if old not in before:
            raise CorpusInconsistent(
                f"rename claims {old!r} was present before, and it was not"
            )
        if new not in after:
            raise CorpusInconsistent(
                f"rename claims {new!r} is present after, and it is not"
            )
        if _signature(before[old]) != _signature(after[new]):
            raise CorpusInconsistent(
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
        raise CorpusInconsistent(
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
    """
    return tuple(sorted({
        op_id for kind, op_id in diff if kind in BREAKING_KINDS
    }))


def _check_run_bijection(raw: list[Mapping[str, Any]]) -> None:
    """One run per revision, in both directions.

    SC-008 says *the same automated check run as the commit*. A run observing
    two revisions makes that true of any detection inside its window, so the
    criterion stops being able to fail.
    """
    runs = [r["check_run_id"] for r in raw]
    revisions = [r["revision_id"] for r in raw]
    if len(set(runs)) != len(runs):
        raise CorpusInconsistent(
            "a check run observes more than one revision, which makes "
            "SC-008's 'same run as the commit' unfalsifiable"
        )
    if len(set(revisions)) != len(revisions):
        raise CorpusInconsistent("a revision identifier is repeated")


def load_revisions() -> tuple[Revision, ...]:
    """Every revision, with all four derived fields recomputed and checked."""
    raw = json.loads(CORPUS_FILE.read_text())["revisions"]
    _check_run_bijection(raw)

    by_id = {r["revision_id"]: r for r in raw}
    revisions: list[Revision] = []

    for entry in raw:
        parent_id = entry["parent"]
        renamed = tuple(
            (pair["from"], pair["to"]) for pair in entry.get("renamed", ())
        )

        if parent_id is None:
            diff: tuple[tuple[str, str], ...] = ()
        else:
            if parent_id not in by_id:
                raise CorpusInconsistent(
                    f"{entry['revision_id']!r} names a parent that is not here"
                )
            diff = diff_contracts(
                by_id[parent_id]["contract"], entry["contract"], renamed
            )

        kinds = classify_diff(diff)
        breaking = is_breaking(kinds)
        drifted = drifted_operations(diff)

        _reject_disagreement(entry, kinds, breaking, drifted)

        revisions.append(Revision(
            revision_id=entry["revision_id"],
            parent=parent_id,
            check_run_id=entry["check_run_id"],
            contract=entry["contract"],
            change_kinds=kinds,
            breaking=breaking,
            drifted_operations=drifted,
            expected_detection_run=entry["expected_detection_run"],
            renamed=renamed,
            why=entry["why"],
        ))

    return tuple(revisions)


def _reject_disagreement(
    entry: Mapping[str, Any],
    kinds: frozenset[str],
    breaking: bool,
    drifted: tuple[str, ...],
) -> None:
    """The committed declaration, contradicted by the recomputation."""
    where = entry["revision_id"]
    if frozenset(entry["change_kinds"]) != kinds:
        raise CorpusInconsistent(
            f"{where}: declared change kinds "
            f"{sorted(entry['change_kinds'])} but the contracts diff to "
            f"{sorted(kinds)}"
        )
    if bool(entry["breaking"]) != breaking:
        raise CorpusInconsistent(
            f"{where}: declared breaking={entry['breaking']} but the kinds "
            f"{sorted(kinds)} recompute to {breaking}"
        )
    if tuple(sorted(entry["drifted_operations"])) != drifted:
        raise CorpusInconsistent(
            f"{where}: declared drifted operations "
            f"{sorted(entry['drifted_operations'])} but the breaking half of "
            f"the diff touches {list(drifted)}"
        )
    expected_run = entry["expected_detection_run"]
    if breaking and expected_run != entry["check_run_id"]:
        raise CorpusInconsistent(
            f"{where}: breaking, so SC-008 requires detection in this "
            f"revision's own run {entry['check_run_id']!r}, and the corpus "
            f"expects {expected_run!r}"
        )
    if not breaking and expected_run is not None:
        raise CorpusInconsistent(
            f"{where}: not breaking, so no run is owed a detection, and the "
            f"corpus expects one in {expected_run!r}"
        )


def base_operation_ids() -> frozenset[str]:
    """The base revision's operation identifiers."""
    return frozenset(load_revisions()[0].contract)


def reference_app_operation_ids() -> frozenset[str]:
    """What the reference application actually publishes."""
    doc = json.loads(SERVED_OPERATIONS_FILE.read_text())
    return frozenset(op["operation_id"] for op in doc["operations"])


def counts() -> Mapping[str, int]:
    """Every figure with its population named, never a bare total."""
    revisions = load_revisions()
    scoreable = [r for r in revisions if r.parent is not None]
    return {
        "revisions_total": len(revisions),
        "revisions_with_a_parent_and_therefore_a_diff": len(scoreable),
        "breaking_revisions": sum(1 for r in scoreable if r.breaking),
        "non_breaking_revisions": sum(1 for r in scoreable if not r.breaking),
        "revisions_whose_contract_is_identical_to_their_parent": sum(
            1 for r in scoreable if not r.change_kinds
        ),
        "distinct_breaking_kinds_exercised": len({
            k for r in scoreable for k in r.change_kinds if k in BREAKING_KINDS
        }),
    }
