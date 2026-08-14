"""T181 — the per-call threshold is unset, and writes stay blocked.

FR-041, SC-014, OD-10. The superseded per-tool number does not travel.
T180 is the residual that produces the labels the measurement needs.

Run:
    python -m pytest tests/unit/test_effect_precision.py -v
"""

from __future__ import annotations

import ast
import json

import pytest

from src.analysis import effect_rules as er
from src.runtime.reports import effect_precision as precision
from src.supervisor.fs_decisions import DENY, decide
from tests.fixtures.locations import document, scratch_entry
from src.supervisor.location_set import parse


THRESHOLD_NAMES = frozenset({
    "PER_CALL_THRESHOLD",
    "per_call_threshold",
    "threshold",
})


def numeric_threshold_defaults(source: str) -> list[str]:
    """Every assignment of a number to a threshold-named name.

    **The whole assignment, not a string search.** A comment that names 0.98
    as the number that must not be inherited is not a default. An
    `AnnAssign` or `Assign` that puts 0.98 (or 0.95, or any number) on a
    threshold name is.
    """
    found: list[str] = []
    tree = ast.parse(source)
    for node in ast.walk(tree):
        names: list[str] = []
        value = None
        if isinstance(node, ast.AnnAssign):
            value = node.value
            if isinstance(node.target, ast.Name):
                names.append(node.target.id)
        elif isinstance(node, ast.Assign):
            value = node.value
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.append(target.id)
        if value is None or not names:
            continue
        if not any(name in THRESHOLD_NAMES for name in names):
            continue
        if isinstance(value, ast.Constant) and isinstance(value.value, (int, float)):
            found.append(ast.unparse(node))
    return found


# ---------------------------------------------------------------------------
# Unset. No numeric default. Plant: PER_CALL_THRESHOLD = 0.98.


def test_the_threshold_has_no_numeric_default() -> None:
    """Inventing 0.95 or copying 0.98 is the inherited-number failure.

    Plant: `PER_CALL_THRESHOLD: object = UNSET` becomes
    `PER_CALL_THRESHOLD: object = 0.98`. The sentinel is no longer the
    value, and the AST scan finds a number on a threshold name.
    """
    assert precision.PER_CALL_THRESHOLD is precision.UNSET
    assert not isinstance(precision.PER_CALL_THRESHOLD, (int, float))
    offending = numeric_threshold_defaults(precision.module_source())
    assert not offending, (
        f"a threshold name carries a numeric default: {offending}. "
        "FR-041 forbids inheriting the superseded per-tool number and "
        "forbids inventing a stand-in. The honest state is unset."
    )


def test_the_document_records_the_threshold_as_unset() -> None:
    document = precision.report().document()
    assert document["per_call_threshold"] is None
    assert document["per_call_threshold_state"] == "unset"
    assert document["threshold_absent_because"] == precision.THRESHOLD_UNSET_BECAUSE
    assert "0.98" in precision.THRESHOLD_UNSET_BECAUSE
    assert "FR-041" in precision.THRESHOLD_UNSET_BECAUSE
    assert "SC-014" in precision.THRESHOLD_UNSET_BECAUSE
    assert "OD-10" in precision.THRESHOLD_UNSET_BECAUSE
    assert json.loads(json.dumps(document)) == document


def test_the_measurement_has_not_run_and_t180_is_named() -> None:
    assert precision.MEASURED_AGAINST_LABELLED_CORPUS is False
    document = precision.report().document()
    assert document["measured_against_labelled_corpus"] is False
    assert document["t180_residual"] == precision.T180_RESIDUAL
    assert "T180" in precision.T180_RESIDUAL


# ---------------------------------------------------------------------------
# Writes stay blocked. Plant: the unset branch returns True.


def test_writes_stay_blocked_while_the_threshold_is_unset() -> None:
    """SC-014 on this side of the gate.

    Plant: `if PER_CALL_THRESHOLD is UNSET: return False` becomes
    `return True`. A write capability is then released while the
    threshold is still unset.
    """
    assert precision.PER_CALL_THRESHOLD is precision.UNSET
    assert precision.write_capability_released() is False
    assert precision.report().document()["write_capability_released"] is False
    with pytest.raises(precision.WriteCapabilityBlocked, match="unset"):
        precision.refuse_unreleased_write()


def test_existing_write_capabilities_remain_refused() -> None:
    """OD-10 / FR-009, observed rather than re-implemented.

    The report does not import these modules. The test does, so a write
    becoming allowable at the enforcement point or the filesystem
    classifier while the threshold is unset fails here as well as there.
    """
    assert er.PERMITTED_TIERS == frozenset({er.TIER_READ_ONLY}), (
        f"PERMITTED_TIERS is {er.PERMITTED_TIERS}. FR-009 permits only "
        "read_only; a write tier becoming allowable while the per-call "
        "threshold is unset is SC-014 failing."
    )
    assert er.TIER_REVERSIBLE_WRITE not in er.PERMITTED_TIERS
    assert er.TIER_IRREVERSIBLE not in er.PERMITTED_TIERS

    location_set = parse(document(locations=[
        {"source": "/srv/app", "target": "/workspace", "mode": "ro",
         "rule_id": "FS-DECL-001", "justification": "the analyzed application"},
        scratch_entry("/var/lib/f2a/scratch"),
    ]))
    decision = decide(
        location_set,
        session_id="s1", syscall="unlinkat", path="/scratch/x",
        pid=7, flags=None, now=0.0,
    )
    assert decision.disposition == DENY
    assert decision.rule_id == "FS-003", (
        f"a write at a declared-writable location was {decision.rule_id}. "
        "OD-10 ships no write path; FS-003 is the clause that says so. "
        "A write becoming allowable while the threshold is unset fails."
    )
    assert precision.write_capability_released() is False
