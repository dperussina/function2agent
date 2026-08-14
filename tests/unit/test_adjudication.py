"""T176 — adjudication queue: pre-registered sampling, operator surface, human rows.

FR-040's third branch needs human ground truth. The verifier cannot
supply it (circularity). A model cannot supply it (FR-052). This file
asserts the queue that would collect those labels, and that nobody has.

T214 residual, named rather than closed: no run produces a `Result`.
The queue takes a caller-supplied result id. This file does not invent
T214's call site.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from src.contracts.ownership import (
    ROLE_ANALYSIS,
    ROLE_PROXY,
    ROLE_RUNTIME,
    ROLE_SHADOW_JUDGE,
    ROLE_SUPERVISOR,
    OwnershipError,
    require_read,
)
from src.contracts.repository import Repository
from src.runtime.adjudication.queue import (
    TABLE,
    AdjudicationError,
    AdjudicationQueue,
    Evidence,
    LABEL_CORRECT,
    LABEL_INCORRECT,
    MODEL_STANDINS,
)
from src.runtime.adjudication.sampling import (
    SamplingError,
    SamplingRule,
    register_rule,
)
from tests.invariants.test_import_graph import forbidden_edges

REPO = Path(__file__).resolve().parents[2]
ADJ_DIR = REPO / "src" / "runtime" / "adjudication"
SUCCESS_PATH = (
    REPO / "src" / "runtime" / "loop.py",
    REPO / "src" / "runtime" / "runner.py",
    REPO / "src" / "runtime" / "serving.py",
    REPO / "src" / "runtime" / "main.py",
    REPO / "src" / "contracts" / "result.py",
)
FORBIDDEN_FROM_ADJUDICATION = (
    "src.contracts.result",
    "src.runtime.loop",
    "src.runtime.runner",
    "src.runtime.serving",
    "src.runtime.main",
    "src.runtime.judge",
)
JOIN_NAMES = (
    "result_from_report",
    "result_from_quantity_verification",
)
T214_RESIDUAL_NO_RUN_PRODUCES_A_RESULT = True


class _Clock:
    def __init__(self, start: float = 100.0) -> None:
        self.now = start

    def __call__(self) -> float:
        self.now += 1.0
        return self.now


def _repo(path: Path, role: str = ROLE_SHADOW_JUDGE) -> Repository:
    return Repository(
        path, role=role, tenant_id="t-adj", deployment_id="d-adj",
    )


def _rule(*, now: float = 10.0, starts: float = 20.0) -> SamplingRule:
    return register_rule(
        rate=1.0,
        window_starts_at=starts,
        window_length_seconds=60.0,
        now=now,
    )


def _evidence(result_id: str = "result-1", session_id: str = "sess-1") -> Evidence:
    return Evidence(
        result_id=result_id,
        session_id=session_id,
        verifier_label=LABEL_CORRECT,
        presented="the derivation and the sources an adjudicator reads",
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


# ---------------------------------------------------------------------------
# Sampling rule: registered before the window, never after.


def test_a_rule_registered_before_the_window_is_accepted() -> None:
    rule = register_rule(
        rate=0.1, window_starts_at=50.0, window_length_seconds=30.0, now=10.0,
    )
    assert rule.registered_at == 10.0
    assert rule.window_starts_at == 50.0
    assert rule.registered_at < rule.window_starts_at


def test_a_rule_cannot_be_registered_after_the_window_opens() -> None:
    """The load-bearing refusal. Registering late is selecting on arrivals."""
    with pytest.raises(SamplingError, match="before the window opens"):
        register_rule(
            rate=0.1,
            window_starts_at=10.0,
            window_length_seconds=30.0,
            now=10.0,
        )
    with pytest.raises(SamplingError, match="before the window opens"):
        SamplingRule(
            rate=0.1,
            registered_at=25.0,
            window_starts_at=10.0,
            window_length_seconds=30.0,
        )


def test_a_zero_rate_is_not_a_rule() -> None:
    with pytest.raises(SamplingError, match="in \\(0, 1\\]"):
        register_rule(
            rate=0.0, window_starts_at=20.0, window_length_seconds=10.0, now=1.0,
        )


# ---------------------------------------------------------------------------
# Operator surface and human_label rows.


def test_the_surface_presents_evidence_and_no_suggested_label(tmp_path: Path) -> None:
    clock = _Clock(20.0)
    queue = AdjudicationQueue(_repo(tmp_path / "adj.sqlite3"), _rule(), clock=clock)
    evidence = _evidence()
    assert queue.sample("result-1", "sess-1", evidence, now=25.0)
    view = queue.present("result-1")
    assert view.result_id == "result-1"
    assert view.session_id == "sess-1"
    assert view.evidence.presented == evidence.presented
    assert view.evidence.verifier_label == LABEL_CORRECT
    assert view.suggested_label is None
    assert view.rule.registered_at < view.rule.window_starts_at


def test_a_human_label_carries_the_adjudicator_and_the_time(tmp_path: Path) -> None:
    clock = _Clock(20.0)
    queue = AdjudicationQueue(_repo(tmp_path / "adj.sqlite3"), _rule(), clock=clock)
    queue.sample("result-1", "sess-1", _evidence(), now=25.0)
    queue.label("result-1", "operator-ada", LABEL_INCORRECT)
    rows = queue.labels()
    assert len(rows) == 1
    assert rows[0]["result_id"] == "result-1"
    assert rows[0]["adjudicator"] == "operator-ada"
    assert rows[0]["label"] == LABEL_INCORRECT
    assert rows[0]["at"] == clock.now
    assert rows[0]["rule_registered_at"] == 10.0


def test_an_unlabelled_queue_leaves_the_table_empty(tmp_path: Path) -> None:
    """The honest production state. Nobody has labelled; do not invent a row."""
    queue = AdjudicationQueue(_repo(tmp_path / "adj.sqlite3"), _rule(), clock=_Clock())
    queue.sample("result-1", "sess-1", _evidence(), now=25.0)
    assert queue.labels() == []


def test_an_empty_adjudicator_is_refused(tmp_path: Path) -> None:
    queue = AdjudicationQueue(_repo(tmp_path / "adj.sqlite3"), _rule(), clock=_Clock())
    queue.sample("result-1", "sess-1", _evidence(), now=25.0)
    with pytest.raises(AdjudicationError, match="carries the adjudicator"):
        queue.label("result-1", "", LABEL_CORRECT)
    assert queue.labels() == []


def test_a_model_standin_is_refused(tmp_path: Path) -> None:
    """A model-written label is the defect FR-052 names."""
    queue = AdjudicationQueue(_repo(tmp_path / "adj.sqlite3"), _rule(), clock=_Clock())
    queue.sample("result-1", "sess-1", _evidence(), now=25.0)
    for name in MODEL_STANDINS:
        with pytest.raises(AdjudicationError, match="reserved stand-in"):
            queue.label("result-1", name, LABEL_CORRECT)
    assert queue.labels() == []


def test_an_empty_result_id_is_refused(tmp_path: Path) -> None:
    queue = AdjudicationQueue(_repo(tmp_path / "adj.sqlite3"), _rule(), clock=_Clock())
    with pytest.raises(AdjudicationError, match="empty id keys nothing"):
        queue.sample("", "sess-1", _evidence(), now=25.0)
    queue.sample("result-1", "sess-1", _evidence(), now=25.0)
    with pytest.raises(AdjudicationError, match="a label is keyed to a result"):
        queue.label("", "operator-ada", LABEL_CORRECT)
    assert queue.labels() == []


def test_a_sample_before_the_window_is_refused(tmp_path: Path) -> None:
    queue = AdjudicationQueue(_repo(tmp_path / "adj.sqlite3"), _rule(), clock=_Clock())
    with pytest.raises(AdjudicationError, match="has not opened"):
        queue.sample("result-1", "sess-1", _evidence(), now=15.0)


def test_a_success_path_role_cannot_write_the_table(tmp_path: Path) -> None:
    path = tmp_path / "adj.sqlite3"
    AdjudicationQueue(_repo(path), _rule(), clock=_Clock())
    runtime = _repo(path, ROLE_RUNTIME)
    with pytest.raises(AdjudicationError, match="may not write"):
        AdjudicationQueue(runtime, _rule(), clock=_Clock())
    with pytest.raises(OwnershipError):
        runtime.insert(TABLE, {
            "result_id": "stolen",
            "session_id": "s",
            "adjudicator": "operator-ada",
            "label": LABEL_CORRECT,
            "rule_registered_at": 1.0,
            "rule_rate": 1.0,
            "at": 1.0,
        })


def test_success_path_roles_cannot_read_human_label() -> None:
    """The empty reader set, re-asserted where the writer now exists."""
    for role in (ROLE_RUNTIME, ROLE_PROXY, ROLE_SUPERVISOR, ROLE_ANALYSIS):
        with pytest.raises(OwnershipError):
            require_read(TABLE, role)


# ---------------------------------------------------------------------------
# Structural: no success-path import either way, and T214 is still open.


def _adjudication_import_edges() -> list[str]:
    edges: list[str] = []
    for path in sorted(ADJ_DIR.glob("*.py")):
        relative = path.relative_to(REPO).as_posix()
        for imported in sorted(_imported(path)):
            for forbidden in FORBIDDEN_FROM_ADJUDICATION:
                if imported == forbidden or imported.startswith(forbidden + "."):
                    edges.append(f"{relative} imports {imported}")
    return edges


def test_adjudication_does_not_import_the_success_path_or_the_judge() -> None:
    assert _adjudication_import_edges() == [], (
        "adjudication imported a success-path or judge module:\n  "
        + "\n  ".join(_adjudication_import_edges())
    )


def test_the_adjudication_import_scan_fires_on_a_planted_result_import(
        tmp_path: Path) -> None:
    """The removal proof of the adjudication → result direction."""
    planted = tmp_path / "src" / "runtime" / "adjudication"
    planted.mkdir(parents=True)
    (planted / "queue.py").write_text(
        "from src.contracts.result import Result\n\n"
        "def write(x):\n    return Result\n"
    )
    edges: list[str] = []
    for path in planted.glob("*.py"):
        for imported in _imported(path):
            if imported == "src.contracts.result" or imported.startswith(
                    "src.contracts.result."):
                edges.append(f"{path.name} imports {imported}")
    assert edges, "the adjudication→result scan did not report a planted import"


def test_the_success_path_does_not_import_adjudication() -> None:
    found: list[str] = []
    for path in SUCCESS_PATH:
        relative = path.relative_to(REPO).as_posix()
        for imported in sorted(_imported(path)):
            if imported == "src.runtime.adjudication" or imported.startswith(
                    "src.runtime.adjudication."):
                found.append(f"{relative} imports {imported}")
    assert found == [], (
        "a success-path module imported adjudication:\n  " + "\n  ".join(found)
    )


def test_the_success_path_import_scan_fires_on_a_planted_adjudication_edge(
        tmp_path: Path) -> None:
    """The removal proof of loop/runner/serving/main → adjudication."""
    planted = tmp_path / "loop.py"
    planted.write_text(
        "from src.runtime.adjudication.queue import AdjudicationQueue\n"
    )
    found: list[str] = []
    for imported in _imported(planted):
        if imported == "src.runtime.adjudication" or imported.startswith(
                "src.runtime.adjudication."):
            found.append(imported)
    assert found, "the success-path→adjudication scan did not report a planted import"


def test_forbidden_edges_stay_empty() -> None:
    assert forbidden_edges(REPO) == []


def test_no_run_produces_a_result_t214_is_still_open() -> None:
    """Named residual. The queue takes a caller-supplied id; it does not join."""
    assert T214_RESIDUAL_NO_RUN_PRODUCES_A_RESULT
    scanned = (
        *SUCCESS_PATH,
        *ADJ_DIR.glob("*.py"),
    )
    hits: list[str] = []
    for path in scanned:
        text = path.read_text()
        relative = path.relative_to(REPO).as_posix()
        for name in JOIN_NAMES:
            if name in text:
                hits.append(f"{relative} names {name}")
    assert hits == [], (
        "a success-path or adjudication module called the T213 join; "
        "that call site is T214's and is still open:\n  "
        + "\n  ".join(hits)
    )
