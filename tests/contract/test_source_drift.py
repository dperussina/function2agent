"""T138 — source-drift detection in the same check run (FR-028, SC-008).

## What has to be asserted here that a clock-moved test would miss

FR-028 detects a source change that **invalidates** a derived contract. The
source clock moving is the input, not the verdict: C-005, C-006 and C-007 all
move the contract document's content address and none of them invalidate a
caller. A test that only asserted `Movement.moved` on the source clock would
pass a detector that fires on every hash change, which is the cheap detector
T154's corpus exists to fail.

SC-008 is scored against that corpus, one check run per revision — the loader
already refuses a run that observes two. The oracle is the loader's recomputed
`breaking` / `drifted_operations` / `expected_detection_run`, not a second
classifier in this file.

## Every refusal arm reaches exactly one guard

`Invalidation` validates clock, then named operations. `detect` validates
breaking-without-a-clock-move after the quiet-on-non-breaking return, so a
non-breaking input cannot reach that raise. `classify_diff` and the rename
signature check are reached by their own planted inputs, not by a corpus
revision.

## The cheap detectors, in this file, so Rule 8 can fail them

T154 already writes two trivially wrong detectors into `test_drift_fixtures.py`
and shows the corpus fails them. This file writes the three the non-breaking
revisions were built to defeat, and requires each one to go loud on the
revision that defeats it. A corpus that had lost its negative control would
let those arms pass.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from src.analysis.clocks import (
    DEPLOYMENT,
    SOURCE,
    compare_each,
    deployment_reading,
    reading,
)
from src.analysis.drift_signal import ARTIFACT_DRIFT, ArtifactDrift, signals_from_movements
from src.analysis.source_drift import (
    BREAKING_KINDS,
    NON_BREAKING_KINDS,
    Invalidation,
    SourceDriftError,
    classify_diff,
    detect,
    diff_contracts,
    drifted_operations,
    source_movements_of,
    source_reading_of,
)
from src.contracts.canonical import content_address
from tests.fixtures.drift_corpora import source as src

REPO = Path(__file__).resolve().parents[2]
MODULE = REPO / "src" / "analysis" / "source_drift.py"

DEPLOYMENT_ID = "d-reference-app"
ANCHOR = "acme/parts-api@" + "0" * 39 + "a"

OPERATIONS = [
    {"operation_id": "get_part", "method": "GET", "path_template": "/parts/{id}"},
    {"operation_id": "list_parts", "method": "GET", "path_template": "/parts"},
]
OPERATIONS_AFTER_WITHDRAWAL = OPERATIONS[:1]

QUIET_REVISIONS = ("C-005", "C-006", "C-007", "C-008")


def _both(contracts, *, operations=OPERATIONS):
    return {
        SOURCE: source_reading_of(
            contracts, deployment_id=DEPLOYMENT_ID, source_ref=ANCHOR
        ),
        DEPLOYMENT: deployment_reading(
            deployment_id=DEPLOYMENT_ID, operations=operations
        ),
    }


def _by_id():
    return {r.revision_id: r for r in src.load_revisions()}


def _detect(revision):
    """One check run, bound to this revision, against its parent."""
    parent = _by_id()[revision.parent]
    return detect(
        _both(parent.contract),
        _both(revision.contract),
        before_contracts=parent.contract,
        after_contracts=revision.contract,
        renamed=revision.renamed,
    )


# ---------------------------------------------------------------------------
# SC-008 against T154, one run per revision.


def test_every_breaking_revision_is_detected_in_its_own_check_run() -> None:
    """SC-008. The population is the loader's breaking revisions, not all 11."""
    detected = []
    for revision in src.load_revisions():
        if not revision.breaking:
            continue
        found = _detect(revision)
        assert found is not None, (
            f"{revision.revision_id} is breaking ({sorted(revision.change_kinds)}) "
            "and the detector was quiet in "
            f"{revision.check_run_id}. SC-008 requires detection in the same "
            "run as the commit."
        )
        assert found.signal.clock == SOURCE
        assert isinstance(found.signal, ArtifactDrift)
        assert found.signal.document()["signal_kind"] == ARTIFACT_DRIFT
        assert found.operations == revision.drifted_operations, (
            f"{revision.revision_id}: detector named {list(found.operations)} "
            f"and the loader recomputed {list(revision.drifted_operations)}"
        )
        detected.append(revision.check_run_id)
        assert revision.expected_detection_run == revision.check_run_id

    figures = src.counts()
    assert len(detected) == figures["breaking_revisions"]
    assert len(detected) == len(set(detected)), (
        "two breaking revisions were scored inside one check run, which is "
        "the bijection the loader already refuses and SC-008 cannot survive"
    )


def test_the_detector_is_quiet_on_every_non_breaking_revision() -> None:
    quiet = []
    for revision in src.load_revisions():
        if revision.parent is None or revision.breaking:
            continue
        found = _detect(revision)
        assert found is None, (
            f"{revision.revision_id} is not breaking "
            f"({sorted(revision.change_kinds) or 'identical'}) and the "
            f"detector raised {found.operations} in {revision.check_run_id}"
        )
        quiet.append(revision.revision_id)

    assert tuple(quiet) == QUIET_REVISIONS
    for revision_id in QUIET_REVISIONS:
        assert revision_id in quiet


def test_c010_names_only_the_operation_the_breaking_half_touched() -> None:
    """The mixed revision. A commit-level blob fails this even if it is loud."""
    revision = _by_id()["C-010"]
    found = _detect(revision)
    assert found is not None
    assert found.operations == ("list_all_shipments",)
    assert "get_part" not in found.operations
    assert "list_parts" not in found.operations


def test_c008_being_quiet_is_not_t156() -> None:
    """C-008 is one identical-input revision inside SC-008's population.

    T156 is a battery over repeated re-analysis of held-constant source. This
    arm exists so a reader who scores C-008 and stops has not scored T156.
    """
    revision = _by_id()["C-008"]
    assert not revision.change_kinds
    assert _detect(revision) is None
    assert (REPO / "tests" / "batteries" / "test_drift_negative.py").is_file(), (
        "C-008 is quiet and T156's battery is absent, so SC-029's second "
        "clause has no measurement"
    )


# ---------------------------------------------------------------------------
# The cheap detectors T154's non-breaking revisions exist to defeat.


def _hash_moved(before, after) -> bool:
    return content_address(dict(before)) != content_address(dict(after))


def _operation_set_moved(before, after) -> bool:
    return set(before) != set(after)


def _signature_moved(before, after) -> bool:
    """Fires when any overlapping operation's parameters or returns moved.

    Ignores summary, so it is not the whole-document hash. Still fires on
    C-005 (optional parameter added).
    """
    for op_id in set(before) & set(after):
        was, now = before[op_id], after[op_id]
        if was.get("parameters") != now.get("parameters"):
            return True
        if was.get("returns") != now.get("returns"):
            return True
    return False


def test_a_detector_that_fires_on_any_hash_change_fails_this_corpus() -> None:
    """C-007. If this passes, the summary-only control has gone missing."""
    c007 = _by_id()["C-007"]
    parent = _by_id()[c007.parent]
    assert _hash_moved(parent.contract, c007.contract)
    assert _detect(c007) is None
    assert not c007.breaking


def test_a_detector_that_fires_on_an_operation_set_change_fails_this_corpus() -> None:
    """C-006."""
    c006 = _by_id()["C-006"]
    parent = _by_id()[c006.parent]
    assert _operation_set_moved(parent.contract, c006.contract)
    assert _detect(c006) is None
    assert not c006.breaking


def test_a_detector_that_fires_on_a_signature_change_fails_this_corpus() -> None:
    """C-005."""
    c005 = _by_id()["C-005"]
    parent = _by_id()[c005.parent]
    assert _signature_moved(parent.contract, c005.contract)
    assert _detect(c005) is None
    assert not c005.breaking


def test_the_source_clock_does_move_on_the_non_breaking_hash_changes() -> None:
    """The clock moving is not the bug; signalling on it is.

    If this failed, C-005/C-006/C-007 would be quiet for the wrong reason —
    the content address would not have moved — and the filter would be
    untested.
    """
    for revision_id in ("C-005", "C-006", "C-007"):
        revision = _by_id()[revision_id]
        parent = _by_id()[revision.parent]
        movements = source_movements_of(_both(parent.contract), _both(revision.contract))
        assert len(movements) == 1
        assert movements[0].clock == SOURCE
        assert movements[0].moved, (
            f"{revision_id} did not move the source clock, so the quiet "
            "verdict is not a filter over a moved clock"
        )
        assert signals_from_movements(movements), (
            f"{revision_id}: signals_from_movements would not emit, so the "
            "detector's quiet cannot be the invalidation filter"
        )


# ---------------------------------------------------------------------------
# Independence from the deployment clock, and from the source_derived union.


def test_a_deployment_clock_move_is_not_source_drift() -> None:
    """The filter is `Movement.clock == SOURCE`, not `source_derived`.

    `served_operation_set` is flagged `source_derived=True` and is the
    deployment-derived artifact. A detector that filtered on the flag would
    raise here.
    """
    contracts = _by_id()["C-000"].contract
    found = detect(
        _both(contracts, operations=OPERATIONS),
        _both(contracts, operations=OPERATIONS_AFTER_WITHDRAWAL),
        before_contracts=contracts,
        after_contracts=contracts,
    )
    assert found is None

    movements = compare_each(
        _both(contracts, operations=OPERATIONS),
        _both(contracts, operations=OPERATIONS_AFTER_WITHDRAWAL),
    )
    by_clock = {m.clock: m for m in movements}
    assert by_clock[DEPLOYMENT].moved
    assert not by_clock[SOURCE].moved
    source_only = source_movements_of(
        _both(contracts, operations=OPERATIONS),
        _both(contracts, operations=OPERATIONS_AFTER_WITHDRAWAL),
    )
    assert len(source_only) == 1
    assert source_only[0].clock == SOURCE
    assert source_only[0].moved is False


def test_the_finding_is_an_artifact_drift_not_a_third_shape() -> None:
    found = _detect(_by_id()["C-001"])
    assert found is not None
    assert type(found.signal) is ArtifactDrift
    assert not hasattr(found, "version_after")
    assert found.signal.version_before != found.signal.version_after
    assert found.signal.kinds_moved == ("derived_contract",)


def test_the_module_does_not_import_runtime_or_the_schema_pin() -> None:
    """T138 lives in analysis and cannot import runtime; T136 is not this slice."""
    tree = ast.parse(MODULE.read_text(), filename=str(MODULE))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    assert not any(name == "src.runtime" or name.startswith("src.runtime.")
                   for name in imported)
    assert not any("codegraph" in name for name in imported)
    assert "src.analysis.clocks" in imported
    assert "src.analysis.drift_signal" in imported


# ---------------------------------------------------------------------------
# Refusals. One guard reachable per arm.


def test_a_finding_on_the_deployment_clock_is_refused() -> None:
    """Every other Invalidation field is valid, so only the clock guard fires."""
    before = deployment_reading(deployment_id=DEPLOYMENT_ID, operations=OPERATIONS)
    after = deployment_reading(
        deployment_id=DEPLOYMENT_ID, operations=OPERATIONS_AFTER_WITHDRAWAL
    )
    signal = ArtifactDrift.from_movement(
        next(
            m
            for m in compare_each(
                {SOURCE: source_reading_of(_by_id()["C-000"].contract,
                                           deployment_id=DEPLOYMENT_ID,
                                           source_ref=ANCHOR),
                 DEPLOYMENT: before},
                {SOURCE: source_reading_of(_by_id()["C-000"].contract,
                                           deployment_id=DEPLOYMENT_ID,
                                           source_ref=ANCHOR),
                 DEPLOYMENT: after},
            )
            if m.clock == DEPLOYMENT
        )
    )
    assert signal.clock == DEPLOYMENT
    with pytest.raises(SourceDriftError, match="deployment clock"):
        Invalidation(signal=signal, operations=("get_part",))


def test_a_breaking_diff_against_an_unmoved_clock_is_refused() -> None:
    """Readings that were not taken from these contracts, not a quiet miss."""
    c001 = _by_id()["C-001"]
    parent = _by_id()[c001.parent]
    unchanged = _both(parent.contract)
    with pytest.raises(SourceDriftError, match="source clock did not move"):
        detect(
            unchanged,
            unchanged,
            before_contracts=parent.contract,
            after_contracts=c001.contract,
        )


def test_a_rename_whose_signature_moved_is_refused() -> None:
    before = {"a": {"summary": "s", "parameters": {}, "returns": {"x": "int"}}}
    after = {"b": {"summary": "s", "parameters": {}, "returns": {"x": "str"}}}
    with pytest.raises(SourceDriftError, match="signatures differ"):
        diff_contracts(before, after, (("a", "b"),))


def test_an_unknown_change_kind_is_refused() -> None:
    with pytest.raises(SourceDriftError, match="no breaking verdict"):
        classify_diff((("invented_kind", "get_part"),))


def test_the_two_kind_sets_are_disjoint_and_the_classifier_is_exhaustive() -> None:
    assert not (BREAKING_KINDS & NON_BREAKING_KINDS)
    kinds = {k for r in src.load_revisions() for k in r.change_kinds}
    assert kinds <= (BREAKING_KINDS | NON_BREAKING_KINDS)


def test_a_source_reading_cannot_be_built_from_the_served_surface() -> None:
    """Independence is T137's refusal; this module must not grow a bypass."""
    with pytest.raises(Exception, match="is not read by the 'source' clock"):
        reading(
            SOURCE,
            deployment_id=DEPLOYMENT_ID,
            versions={
                "derived_contract": content_address({"x": 1}),
                "derived_check": content_address({}),
                "served_operation_set": "sha256:" + "a" * 64,
            },
            source_ref=ANCHOR,
        )


def test_detect_returns_none_on_identical_contracts_and_identical_readings() -> None:
    """The floor under the refusals. A module that refused everything would
    fail SC-008; a module that signalled on identical input would fail this."""
    contracts = _by_id()["C-000"].contract
    both = _both(contracts)
    assert detect(both, both, before_contracts=contracts, after_contracts=contracts) is None


def test_drifted_operations_ignores_operations_touched_only_by_a_non_breaking_kind() -> None:
    """The mechanism behind C-010, reachable without the rest of the corpus."""
    diff = (
        ("optional_parameter_added", "health"),
        ("parameter_removed", "list_all_shipments"),
    )
    assert drifted_operations(diff) == ("list_all_shipments",)
