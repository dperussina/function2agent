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
source for SC-029's second clause. `C-008` is one identical-input revision
inside the population SC-008 is measured over, so that population is not made
exclusively of revisions where something moved. Scoring C-008 quiet does not
discharge T156.

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

from src.analysis import source_drift as _detector
from src.analysis.source_drift import SourceDriftError
from tests.fixtures.drift_corpora import CorpusInconsistent

FIXTURES = Path(__file__).resolve().parent.parent
CORPUS_FILE = FIXTURES / "drift-source" / "corpus.json"

#: The reference application's published set, used to anchor the base revision.
#: A corpus describing five invented operation names would be internally
#: consistent and about nothing.
SERVED_OPERATIONS_FILE = FIXTURES / "reference-app" / "served_operations.json"

#: The breaking verdict lives in `src.analysis.source_drift`, which is the
#: detector SC-008 scores. Re-exporting the same objects is what keeps the
#: loader from growing a second classifier that can disagree with it.
BREAKING_KINDS = _detector.BREAKING_KINDS
NON_BREAKING_KINDS = _detector.NON_BREAKING_KINDS
ALL_KINDS = _detector.ALL_KINDS


def _as_corpus(exc: SourceDriftError) -> CorpusInconsistent:
    return CorpusInconsistent(str(exc))


def diff_contracts(
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    renamed: tuple[tuple[str, str], ...] = (),
) -> tuple[tuple[str, str], ...]:
    """The atomic change set, via T138's classifier — not a second one."""
    try:
        return _detector.diff_contracts(before, after, renamed)
    except SourceDriftError as exc:
        raise _as_corpus(exc) from exc


def classify_diff(diff: tuple[tuple[str, str], ...]) -> frozenset[str]:
    try:
        return _detector.classify_diff(diff)
    except SourceDriftError as exc:
        raise _as_corpus(exc) from exc


def is_breaking(kinds: frozenset[str]) -> bool:
    return _detector.is_breaking(kinds)


def drifted_operations(diff: tuple[tuple[str, str], ...]) -> tuple[str, ...]:
    return _detector.drifted_operations(diff)


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
