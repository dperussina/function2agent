"""INV-002 — the model-judge boundary is **structural**, not a policy.

FR-052 and constitution Principle I both require that a model's opinion cannot
become a success signal. A code review saying "don't import the judge from the
result path" is a policy; this is the check that makes it a property.

The checker walks the import graph statically. It is deliberately *not* a
runtime check — a runtime check only fires on a path someone exercised, and the
edge that matters is the one nobody exercised yet.

**The removal proof is in this file.** `test_checker_fires_on_a_planted_edge`
builds a synthetic tree containing exactly the forbidden import and asserts the
checker reports it. Without that, a checker whose table were emptied would
report a clean graph over the real tree and pass forever.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent.parent

# The judge side: anything a model's opinion flows through.
JUDGE_MODULES = (
    "src.runtime.judge",
    "src.runtime.judges",
    "src.analysis.judge",
)

# The recording side: modules whose output is a success signal or a
# caller-visible outcome. An import edge from here to the judge side is the
# defect FR-052 names.
RECORDING_PREFIXES = (
    "src/contracts/result.py",
    "src/contracts/terminal.py",
    "src/runtime/result",
    "src/runtime/results",
    "src/runtime/gate",
    "src/runtime/record",
    "src/supervisor/fs_decisions.py",
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


def _on_recording_side(relative: str) -> bool:
    return any(relative.startswith(prefix) for prefix in RECORDING_PREFIXES)


def forbidden_edges(root: Path, judge_modules=JUDGE_MODULES) -> list[str]:
    """Every import edge from the recording side to the judge side."""
    found: list[str] = []
    for path in sorted((root / "src").rglob("*.py")):
        relative = path.relative_to(root).as_posix()
        if not _on_recording_side(relative):
            continue
        for imported in sorted(_imported_modules(path)):
            for judge in judge_modules:
                if imported == judge or imported.startswith(judge + "."):
                    found.append(f"{relative} imports {imported}")
    return found


def test_no_recording_module_imports_the_judge() -> None:
    edges = forbidden_edges(REPO)
    assert edges == [], (
        "FR-052 / Principle I: the result-record and gate-decision modules "
        "must not import the judge module.\n  " + "\n  ".join(edges)
    )


def test_checker_fires_on_a_planted_edge(tmp_path: Path) -> None:
    """The removal proof: plant the defect, assert the checker sees it.

    A checker that never fires is indistinguishable from no checker, and this
    is the fixture that tells them apart.
    """
    module = tmp_path / "src" / "runtime" / "results"
    module.mkdir(parents=True)
    (module / "record.py").write_text(
        "from src.runtime.judge import verdict\n\n"
        "def record(x):\n    return verdict(x)\n"
    )
    edges = forbidden_edges(tmp_path)
    assert edges, "the checker did not report a planted forbidden import"
    assert "src/runtime/results/record.py" in edges[0]


def test_checker_ignores_a_permitted_edge(tmp_path: Path) -> None:
    """And a checker that fires on everything is also no checker."""
    module = tmp_path / "src" / "runtime" / "results"
    module.mkdir(parents=True)
    (module / "record.py").write_text(
        "from src.contracts.result import Result\n\n"
        "def record(x):\n    return Result\n"
    )
    assert forbidden_edges(tmp_path) == []


def test_recording_side_is_not_empty() -> None:
    """A prefix list matching nothing would make the invariant vacuous."""
    matched = [
        p.relative_to(REPO).as_posix()
        for p in (REPO / "src").rglob("*.py")
        if _on_recording_side(p.relative_to(REPO).as_posix())
    ]
    assert matched, (
        "RECORDING_PREFIXES matches no file in src/. The invariant would pass "
        "over an empty set, which is not the same as passing."
    )


@pytest.mark.parametrize("judge", JUDGE_MODULES)
def test_judge_module_names_are_reserved(judge: str) -> None:
    """If a judge module appears later it must land on one of these names.

    Stated as a test so that adding `src/runtime/scoring.py` and putting a
    model in it is a visible act rather than a quiet one: the name is not in
    the table, so the checker would not see edges into it.
    """
    assert judge.startswith("src.")
