"""T192 — standing report of every value still marked unvalidated.

FR-043. The configured guesses stay one kind; the Linux kernel floor of
5.14 is DERIVED and NOT TESTED, listed apart. T205 has not run.

Run:
    python -m pytest tests/unit/test_unvalidated_report.py -v
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

from src.contracts import config as cfg
from src.contracts.unvalidated import (
    MARKED_WHEN_REPORTED,
    SHIPPED_DEFAULTS,
    is_marked,
)
from src.runtime.reports import unvalidated as uv
from src.supervisor.preflight import (
    MINIMUM_KERNEL,
    MINIMUM_KERNEL_BASIS,
    MINIMUM_KERNEL_IS_TESTED,
)
from tests.contract.test_configuration_failloud import VALID

REPO = Path(__file__).resolve().parents[2]
REPORT = REPO / "src" / "runtime" / "reports" / "unvalidated.py"
SUCCESS_PATH = (
    REPO / "src" / "runtime" / "loop.py",
    REPO / "src" / "runtime" / "runner.py",
    REPO / "src" / "runtime" / "serving.py",
    REPO / "src" / "runtime" / "main.py",
    REPO / "src" / "contracts" / "result.py",
)
FORBIDDEN_FROM_REPORT = (
    "src.contracts.result",
    "src.runtime.loop",
    "src.runtime.runner",
    "src.runtime.serving",
    "src.runtime.main",
    "src.runtime.judge",
)


def _imported(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return names


def _supervisor() -> cfg.Config:
    return cfg.load(cfg.SUPERVISOR_KEYS, VALID)


# ---------------------------------------------------------------------------
# The configured set. Plant: drop FR-049 because they lack unvalidated=True.


def test_the_report_names_every_configured_fr043_value() -> None:
    document = uv.report(_supervisor()).document()
    names = {entry["name"] for entry in document["configured"]}
    assert SHIPPED_DEFAULTS <= names
    assert MARKED_WHEN_REPORTED <= names
    assert "DRIFT_CHECK_INTERVAL_SECONDS" in names
    assert "STALENESS_CEILING_SECONDS" in names
    assert "CAPABILITY_LEASE_INTERVAL_SECONDS" in names
    assert "REPORTING_WINDOW_SECONDS" in names


def test_fr049_bounds_appear_though_they_lack_unvalidated_true() -> None:
    """FR-049's two bounds are required-with-no-default, not shipped defaults.

    Plant: `_configured_entries` iterates `config.unvalidated` (or
    `SHIPPED_DEFAULTS`) instead of `PROVENANCES`. The bounds vanish because
    they have no `unvalidated=True` default, and a reader concludes they
    were measured.
    """
    loaded = _supervisor()
    assert "SANDBOX_MEMORY_MAX" not in loaded.unvalidated
    assert "SANDBOX_CPU_MAX" not in loaded.unvalidated
    document = uv.report(loaded).document()
    by_name = {entry["name"]: entry for entry in document["configured"]}
    memory = by_name["SANDBOX_MEMORY_MAX"]
    cpu = by_name["SANDBOX_CPU_MAX"]
    assert memory["kind"] == uv.KIND_REQUIRED_NO_DEFAULT
    assert cpu["kind"] == uv.KIND_REQUIRED_NO_DEFAULT
    assert memory["requirement"] == "FR-049"
    assert cpu["requirement"] == "FR-049"
    assert is_marked(memory["value"])
    assert is_marked(cpu["value"])


def test_shipped_defaults_are_a_different_kind_from_required_bounds() -> None:
    document = uv.report(_supervisor()).document()
    by_name = {entry["name"]: entry for entry in document["configured"]}
    for name in SHIPPED_DEFAULTS:
        assert by_name[name]["kind"] == uv.KIND_SHIPPED_DEFAULT
        assert is_marked(by_name[name]["value"])
    for name in MARKED_WHEN_REPORTED:
        if name == "REPORTING_WINDOW_SECONDS":
            assert by_name[name]["kind"] == uv.KIND_REQUIRED_NO_DEFAULT
            assert by_name[name]["value"] is None
            continue
        assert by_name[name]["kind"] == uv.KIND_REQUIRED_NO_DEFAULT


def test_fr028_citation_residual_is_named_on_the_detection_window() -> None:
    """FR-046's detection window is this key. The citation is FR-028 (T141)."""
    document = uv.report(_supervisor()).document()
    by_name = {entry["name"]: entry for entry in document["configured"]}
    assert by_name["DRIFT_CHECK_INTERVAL_SECONDS"]["requirement"] == "FR-028"
    assert "FR-028" in document["residuals"]["fr028_citation"]
    assert "T141" in document["residuals"]["fr028_citation"]
    assert "FR-046" in document["residuals"]["fr028_citation"]


def test_adjacent_fr049_keys_are_named_as_a_residual_and_excluded() -> None:
    document = uv.report().document()
    names = {entry["name"] for entry in document["configured"]}
    assert "SANDBOX_CPU_TOTAL" not in names
    assert "SANDBOX_PIDS_MAX" not in names
    residual = document["residuals"]["fr049_adjacent_keys"]
    assert "SANDBOX_CPU_TOTAL" in residual
    assert "SANDBOX_PIDS_MAX" in residual


# ---------------------------------------------------------------------------
# The kernel floor. Distinct kind. Plant: fold it into configured.


def test_the_kernel_floor_is_a_distinct_kind_not_a_configured_value() -> None:
    """5.14 is DERIVED, NOT TESTED — not one more operator-typed number.

    Plant: `document()` appends `self.kernel_floor.document()` onto
    `configured`. The floor becomes a configured entry and a reader treats
    a preflight constant as a guess they typed.
    """
    document = uv.report().document()
    configured_kinds = {entry["kind"] for entry in document["configured"]}
    assert uv.KIND_DERIVED_NOT_TESTED not in configured_kinds
    floor = document["kernel_floor"]
    assert floor["kind"] == uv.KIND_DERIVED_NOT_TESTED
    assert floor["version"] == f"{MINIMUM_KERNEL[0]}.{MINIMUM_KERNEL[1]}"
    assert floor["version"] == "5.14"
    assert floor["basis"] == MINIMUM_KERNEL_BASIS
    assert floor["derived"] is True
    assert floor["tested"] is False
    assert floor["tested"] is MINIMUM_KERNEL_IS_TESTED


def test_the_kernel_floor_wording_is_not_weaker_than_preflight() -> None:
    """Wording may not drop DERIVED or NOT TESTED.

    Plant: `KERNEL_WORDING` loses `NOT TESTED`, or `tested` becomes True.
    The preflight states the derivation and the untested status together;
    a weaker report is the marking ceasing to be load-bearing.
    """
    document = uv.report().document()
    wording = document["kernel_floor"]["wording"]
    assert "DERIVED" in wording
    assert "NOT TESTED" in wording
    assert wording == uv.KERNEL_WORDING
    assert document["kernel_floor"]["tested"] is False
    assert MINIMUM_KERNEL_IS_TESTED is False
    assert document["kernel_floor"]["t205_ran"] is False
    assert document["kernel_floor"]["t205_status"] == "deferred"
    assert document["kernel_floor"]["closes_by"] == "T205"
    assert "T205" in document["residuals"]["t205"]
    assert "does not claim the matrix ran" in document["residuals"]["t205"]


def test_the_document_is_json() -> None:
    document = uv.report(_supervisor()).document()
    assert json.loads(json.dumps(document)) == document
    assert document["schema_version"] == uv.SCHEMA_VERSION


# ---------------------------------------------------------------------------
# The report does not import the success path.


def test_the_report_does_not_import_the_success_path_or_the_judge() -> None:
    edges: list[str] = []
    for imported in sorted(_imported(REPORT)):
        for forbidden in FORBIDDEN_FROM_REPORT:
            if imported == forbidden or imported.startswith(forbidden + "."):
                edges.append(f"unvalidated.py imports {imported}")
    assert edges == [], (
        "the standing unvalidated report imported a success-path or judge "
        "module:\n  " + "\n  ".join(edges)
    )


def test_the_success_path_does_not_import_the_unvalidated_report() -> None:
    found: list[str] = []
    for path in SUCCESS_PATH:
        relative = path.relative_to(REPO).as_posix()
        for imported in sorted(_imported(path)):
            if imported == "src.runtime.reports.unvalidated" or imported.startswith(
                    "src.runtime.reports.unvalidated."):
                found.append(f"{relative} imports {imported}")
    assert found == [], (
        "a success-path module imported the standing unvalidated report:\n  "
        + "\n  ".join(found)
    )


def test_the_import_scan_fires_on_a_planted_result_import(tmp_path: Path) -> None:
    planted = tmp_path / "unvalidated.py"
    planted.write_text("from src.contracts.result import Result\n")
    found: list[str] = []
    for imported in _imported(planted):
        if imported == "src.contracts.result" or imported.startswith(
                "src.contracts.result."):
            found.append(imported)
    assert found, "the unvalidated→result scan did not report a planted import"
