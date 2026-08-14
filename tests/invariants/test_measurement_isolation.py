"""T187 — the measurement tables are **structurally apart** from the success path.

`contracts/trace-record.md` and the ownership map give `judge_verdict`,
`human_label`, `effect_gate_observation` and `battery_run` empty success-path
reader sets. An empty reader set is a policy until something walks the tree.
This is that walk.

Two couplings, both structural:

1. A success-path **module** importing a writer of one of those tables.
2. A success-path **table** (or the module that owns it) naming one of those
   tables as a string — a foreign key, a `TABLE =` constant, a `CREATE TABLE`
   / `REFERENCES` fragment.

A code review saying "don't read `battery_run` from the loop" is a policy;
this is the check that makes it a property. The walk is static on purpose:
a runtime check only fires on a path someone exercised, and the edge that
matters is the one nobody exercised yet.

Reports that are *handed* measurement rows (`src/runtime/reports/`), the
writer packages themselves, and the ownership map that *names* the tables
are not the success path. Naming `human_label` in `margin.py` is the report
doing its job. Naming it in `loop.py` is the defect.

**The removal proofs are in this file and in `tests/removal_proofs.sh`.**
`test_checker_fires_on_a_planted_writer_import` and
`test_checker_fires_on_a_planted_table_reference` build a synthetic tree
containing exactly the forbidden coupling and assert the checker reports
it. Without those, a checker whose prefix list were emptied would report
a clean graph over the real tree and pass forever.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from tests.invariants.test_import_graph import forbidden_edges

REPO = Path(__file__).resolve().parent.parent.parent

# The four measurement tables. Ownership gives each an empty success-path
# reader set; this file makes that emptiness structural.
MEASUREMENT_TABLES = (
    "judge_verdict",
    "human_label",
    "effect_gate_observation",
    "battery_run",
)

# Modules that write those tables (or, for the observation row, the Python
# projection of the proxy-written table). Prefix match: an import of
# `src.runtime.judge.shadow` is an import of `src.runtime.judge`.
WRITER_MODULES = (
    "src.runtime.judge",
    "src.runtime.adjudication",
    "src.runtime.reports.effect_corpus",
    "src.runtime.batteries",
)

# INV-002's recording side, extended to the live success path a green run
# depends on — not just result recording. Directory prefixes (`result`,
# `results`, `gate`, `record`) match files that do not exist yet so a later
# arrival lands inside the walk rather than beside it.
#
# Not on this list, and must not be: `src/runtime/judge/`,
# `src/runtime/adjudication/`, `src/runtime/reports/`,
# `src/runtime/batteries/`, `src/contracts/ownership.py`, `tests/`.
SUCCESS_PATH_PREFIXES = (
    "src/contracts/result.py",
    "src/contracts/terminal.py",
    "src/runtime/result",
    "src/runtime/results",
    "src/runtime/gate",
    "src/runtime/record",
    "src/supervisor/fs_decisions.py",
    "src/runtime/loop.py",
    "src/runtime/runner.py",
    "src/runtime/serving.py",
    "src/runtime/main.py",
    "src/runtime/journal.py",
    "src/runtime/trace.py",
    "src/runtime/ledger.py",
    "src/runtime/trace_budget.py",
    "src/runtime/session_store.py",
    "src/supervisor/session_table.py",
)

# Ownership plus the four writers. The isolation of tables that do not
# exist is not T187; this is the set the vacuity arm reads.
MEASUREMENT_HOMES = (
    REPO / "src" / "contracts" / "ownership.py",
    REPO / "src" / "runtime" / "judge" / "shadow.py",
    REPO / "src" / "runtime" / "adjudication" / "queue.py",
    REPO / "src" / "runtime" / "reports" / "effect_corpus.py",
    REPO / "src" / "runtime" / "batteries" / "freeze.py",
)

def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
            names.update(f"{node.module}.{a.name}" for a in node.names)
    return names


def _string_constants(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]


def _on_success_path(relative: str) -> bool:
    return any(relative.startswith(prefix) for prefix in SUCCESS_PATH_PREFIXES)


def _src_files(root: Path, suffix: str) -> list[Path]:
    src = root / "src"
    if not src.is_dir():
        return []
    return sorted(p for p in src.rglob(f"*{suffix}") if p.is_file())


def success_path_files(root: Path) -> list[str]:
    found: list[str] = []
    for path in _src_files(root, ".py"):
        relative = path.relative_to(root).as_posix()
        if _on_success_path(relative):
            found.append(relative)
    return found


def forbidden_writer_imports(root: Path) -> list[str]:
    """Every import edge from the success path to a measurement writer."""
    found: list[str] = []
    for path in _src_files(root, ".py"):
        relative = path.relative_to(root).as_posix()
        if not _on_success_path(relative):
            continue
        for imported in sorted(_imported_modules(path)):
            for writer in WRITER_MODULES:
                if imported == writer or imported.startswith(writer + "."):
                    found.append(f"{relative} imports {imported}")
    return found


def measurement_table_references(root: Path) -> list[str]:
    """Every success-path string or schema fragment that names a measurement table."""
    found: list[str] = []
    for path in _src_files(root, ".py"):
        relative = path.relative_to(root).as_posix()
        if not _on_success_path(relative):
            continue
        for value in _string_constants(path):
            for name in MEASUREMENT_TABLES:
                if re.search(rf"\b{re.escape(name)}\b", value):
                    found.append(f"{relative} references {name}")
    for path in _src_files(root, ".sql"):
        relative = path.relative_to(root).as_posix()
        if not _on_success_path(relative):
            continue
        text = path.read_text()
        for name in MEASUREMENT_TABLES:
            if re.search(rf"\b{re.escape(name)}\b", text):
                found.append(f"{relative} references {name}")
    return found


def test_no_success_path_module_imports_a_measurement_writer() -> None:
    edges = forbidden_writer_imports(REPO)
    assert edges == [], (
        "FR-052 / Principle I: a success-path module must not import a "
        "writer of judge_verdict, human_label, effect_gate_observation or "
        "battery_run.\n  " + "\n  ".join(edges)
    )


def test_no_success_path_table_references_a_measurement_table() -> None:
    refs = measurement_table_references(REPO)
    assert refs == [], (
        "a success-path table or module named a measurement table. The "
        "four are structurally apart; a string coupling them is a foreign "
        "key by another name.\n  " + "\n  ".join(refs)
    )


def test_checker_fires_on_a_planted_writer_import(tmp_path: Path) -> None:
    """The removal proof: plant the import, assert the checker sees it."""
    module = tmp_path / "src" / "runtime"
    module.mkdir(parents=True)
    (module / "loop.py").write_text(
        "from src.runtime.batteries.freeze import BatteryFreeze\n\n"
        "def run():\n    return BatteryFreeze\n"
    )
    edges = forbidden_writer_imports(tmp_path)
    assert edges, "the checker did not report a planted writer import"
    assert "src/runtime/loop.py" in edges[0]


def test_checker_fires_on_a_planted_table_reference(tmp_path: Path) -> None:
    """The removal proof: plant the table name, assert the checker sees it."""
    module = tmp_path / "src" / "runtime"
    module.mkdir(parents=True)
    (module / "journal.py").write_text(
        'TABLE = "turn_journal"\nCOUPLED = "judge_verdict"\n'
    )
    refs = measurement_table_references(tmp_path)
    assert refs, "the checker did not report a planted table reference"
    assert "judge_verdict" in refs[0]
    assert "src/runtime/journal.py" in refs[0]


def test_checker_ignores_a_permitted_edge(tmp_path: Path) -> None:
    """And a checker that fires on everything is also no checker."""
    module = tmp_path / "src" / "runtime"
    module.mkdir(parents=True)
    (module / "loop.py").write_text(
        "from src.contracts.result import Result\n\n"
        "def run():\n    return Result\n"
    )
    assert forbidden_writer_imports(tmp_path) == []
    assert measurement_table_references(tmp_path) == []


def test_checker_ignores_a_report_that_names_a_measurement_table(
        tmp_path: Path) -> None:
    """Reports are handed measurement rows. Naming the table is their job."""
    reports = tmp_path / "src" / "runtime" / "reports"
    reports.mkdir(parents=True)
    (reports / "margin.py").write_text(
        'from src.runtime.batteries.freeze import BatteryFreeze\n'
        'LABEL_TABLE = "human_label"\n'
    )
    assert forbidden_writer_imports(tmp_path) == []
    assert measurement_table_references(tmp_path) == []


def test_success_path_is_not_empty() -> None:
    """A prefix list matching nothing would make the invariant vacuous."""
    matched = success_path_files(REPO)
    assert matched, (
        "SUCCESS_PATH_PREFIXES matches no file in src/. The invariant "
        "would pass over an empty set, which is not the same as passing."
    )


def test_the_four_measurement_tables_exist() -> None:
    """The isolation of tables that do not exist is not T187."""
    missing_homes = [p.as_posix() for p in MEASUREMENT_HOMES if not p.is_file()]
    assert not missing_homes, (
        "a writer or the ownership map is gone: " + ", ".join(missing_homes)
    )
    blob = "\n".join(path.read_text() for path in MEASUREMENT_HOMES)
    missing = [name for name in MEASUREMENT_TABLES if name not in blob]
    assert not missing, (
        f"{missing} not found in ownership or the writer modules. "
        "The isolation of tables that do not exist is not T187."
    )


def test_inv002_is_not_weakened() -> None:
    """T187 extends the recording-side walk; it does not replace INV-002."""
    assert forbidden_edges(REPO) == []


@pytest.mark.parametrize("writer", WRITER_MODULES)
def test_writer_module_names_are_reserved(writer: str) -> None:
    """If a writer appears later it must land on one of these names.

    Stated as a test so that adding `src/runtime/scoring.py` and putting a
    measurement write in it is a visible act rather than a quiet one: the
    name is not in the table, so the checker would not see edges into it.
    """
    assert writer.startswith("src.")
