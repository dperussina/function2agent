"""T173 — shadow judge off the request path, writing `judge_verdict`.

FR-039: consume the trace stream asynchronously; write a verdict keyed to
a result; affect nothing the caller sees. FR-052 / Principle I: the
success path does not import this package and does not read the table.

T214 residual, named rather than closed: `result_from_report` exists and
no run calls it. This file does not invent that call site so the judge
has a live `Result`. Tests hand a result id in.
"""

from __future__ import annotations

import ast
import threading
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
from src.runtime.events import EventStream
from src.runtime.judge.inject import (
    MODE_AGREE,
    MODE_DISAGREE,
    MODE_OFF,
    VERDICT_CORRECT,
    VERDICT_INCORRECT,
    decide_for,
)
from src.runtime.judge.shadow import TABLE, JudgeError, ShadowJudge
from tests.invariants.test_import_graph import forbidden_edges

REPO = Path(__file__).resolve().parents[2]
JUDGE_DIR = REPO / "src" / "runtime" / "judge"
SUCCESS_PATH = (
    REPO / "src" / "runtime" / "loop.py",
    REPO / "src" / "runtime" / "runner.py",
    REPO / "src" / "runtime" / "serving.py",
    REPO / "src" / "runtime" / "main.py",
    REPO / "src" / "contracts" / "result.py",
)
FORBIDDEN_FROM_JUDGE = (
    "src.contracts.result",
    "src.runtime.loop",
    "src.runtime.runner",
    "src.runtime.serving",
    "src.runtime.main",
    "src.runtime.reports.not_verifiable",
)
JOIN_NAMES = (
    "result_from_report",
    "result_from_quantity_verification",
)
T214_RESIDUAL_NO_RUN_PRODUCES_A_RESULT = True


class _Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        self.now += 1.0
        return self.now


def _repo(path: Path, role: str = ROLE_SHADOW_JUDGE) -> Repository:
    return Repository(
        path, role=role, tenant_id="t-judge", deployment_id="d-judge",
    )


def _stream(session_id: str = "sess-judge") -> EventStream:
    return EventStream(session_id, clock=_Clock())


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
# The write, keyed to a result, off the request path.


def test_consider_returns_before_the_verdict_is_written(tmp_path: Path) -> None:
    """The request path does not wait on the insert.

    `decide` blocks until released. If `consider` wrote inline, it would
    not return while that block held, and this arm's first wait would
    expire. That is the hang-safe form of 'asynchronously'.
    """
    release = threading.Event()
    in_decide = threading.Event()

    def decide(label: str) -> str:
        in_decide.set()
        if not release.wait(timeout=5):
            raise AssertionError("decide was not released")
        return label

    finished = threading.Event()
    with ShadowJudge(_repo(tmp_path / "judge.sqlite3"), decide) as judge:
        def caller() -> None:
            judge.consider("result-1", "sess-judge", VERDICT_CORRECT)
            finished.set()

        threading.Thread(target=caller, daemon=True).start()
        assert finished.wait(timeout=2), (
            "consider did not return while the verdict write was still in "
            "flight. The request path waited on the judge."
        )
        assert in_decide.wait(timeout=2), "the worker never entered decide"
        assert judge.verdicts() == [], (
            "the row landed before the worker was released, so the write "
            "was not waiting off the request path"
        )
        release.set()
        judge.wait_idle()
        rows = judge.verdicts()
        assert len(rows) == 1
        assert rows[0]["result_id"] == "result-1"
        assert rows[0]["session_id"] == "sess-judge"
        assert rows[0]["verdict"] == VERDICT_CORRECT


def test_consuming_the_stream_writes_no_row(tmp_path: Path) -> None:
    """Attach is consumption. A verdict is scheduled, not implied by an event."""
    stream = _stream()
    with ShadowJudge(_repo(tmp_path / "judge.sqlite3"), decide_for(MODE_AGREE)) as judge:
        judge.attach(stream)
        stream.start()
        judge.wait_idle()
        assert judge.verdicts() == [], (
            "a subscribed event wrote a verdict. FR-039 keys the row to a "
            "result; T214 has not produced one, and an event is not one."
        )


def test_a_verdict_is_keyed_to_the_result_and_sees_the_stream(
        tmp_path: Path) -> None:
    stream = _stream("sess-seen")
    with ShadowJudge(_repo(tmp_path / "judge.sqlite3"), decide_for(MODE_AGREE)) as judge:
        judge.attach(stream)
        stream.start()
        judge.consider("result-seen", "sess-seen", VERDICT_CORRECT)
        judge.wait_idle()
        rows = judge.verdicts()
        assert len(rows) == 1
        assert rows[0]["result_id"] == "result-seen"
        assert rows[0]["event_count"] == 1


def test_an_empty_result_id_is_refused(tmp_path: Path) -> None:
    with ShadowJudge(_repo(tmp_path / "judge.sqlite3"), decide_for(MODE_AGREE)) as judge:
        with pytest.raises(JudgeError, match="empty id keys nothing"):
            judge.consider("", "sess-judge", VERDICT_CORRECT)
        assert judge.verdicts() == []


def test_agree_mode_persists_the_verifier_label(tmp_path: Path) -> None:
    with ShadowJudge(_repo(tmp_path / "judge.sqlite3"), decide_for(MODE_AGREE)) as judge:
        judge.consider("r-agree", "s-1", VERDICT_CORRECT)
        judge.wait_idle()
        assert judge.verdicts()[0]["verdict"] == VERDICT_CORRECT


def test_disagree_mode_persists_the_other_label(tmp_path: Path) -> None:
    with ShadowJudge(_repo(tmp_path / "judge.sqlite3"), decide_for(MODE_DISAGREE)) as judge:
        judge.consider("r-disagree", "s-1", VERDICT_CORRECT)
        judge.wait_idle()
        assert judge.verdicts()[0]["verdict"] == VERDICT_INCORRECT


def test_off_mode_starts_no_thread_and_writes_nothing(tmp_path: Path) -> None:
    stream = _stream()
    with ShadowJudge(_repo(tmp_path / "judge.sqlite3"), decide_for(MODE_OFF)) as judge:
        assert judge._thread is None
        judge.attach(stream)
        stream.start()
        judge.consider("r-off", "s-1", VERDICT_CORRECT)
        assert judge.verdicts() == []


def test_a_success_path_role_cannot_write_the_table(tmp_path: Path) -> None:
    path = tmp_path / "judge.sqlite3"
    with ShadowJudge(_repo(path), decide_for(MODE_AGREE)):
        pass
    runtime = _repo(path, ROLE_RUNTIME)
    with pytest.raises(JudgeError, match="may not write"):
        ShadowJudge(runtime, decide_for(MODE_AGREE))
    with pytest.raises(OwnershipError):
        runtime.insert(TABLE, {
            "result_id": "stolen",
            "session_id": "s",
            "verdict": VERDICT_CORRECT,
            "event_count": 0,
            "at": 1.0,
        })


def test_success_path_roles_cannot_read_judge_verdict() -> None:
    """The empty reader set, re-asserted where the writer now exists.

    `test_writer_ownership.py` already names the table. This arm fires
    after a writer module exists so a new reader added 'for the judge'
    is not a change only that file would see.
    """
    for role in (ROLE_RUNTIME, ROLE_PROXY, ROLE_SUPERVISOR, ROLE_ANALYSIS):
        with pytest.raises(OwnershipError):
            require_read(TABLE, role)


# ---------------------------------------------------------------------------
# Structural: no success-path import either way, and T214 is still open.


def _judge_import_edges() -> list[str]:
    edges: list[str] = []
    for path in sorted(JUDGE_DIR.glob("*.py")):
        relative = path.relative_to(REPO).as_posix()
        for imported in sorted(_imported(path)):
            for forbidden in FORBIDDEN_FROM_JUDGE:
                if imported == forbidden or imported.startswith(forbidden + "."):
                    edges.append(f"{relative} imports {imported}")
    return edges


def test_the_judge_does_not_import_the_success_path() -> None:
    assert _judge_import_edges() == [], (
        "the judge imported a success-path module:\n  "
        + "\n  ".join(_judge_import_edges())
    )


def test_the_judge_import_scan_fires_on_a_planted_result_import(
        tmp_path: Path) -> None:
    """The removal proof of the judge → result direction."""
    planted = tmp_path / "src" / "runtime" / "judge"
    planted.mkdir(parents=True)
    (planted / "shadow.py").write_text(
        "from src.contracts.result import Result\n\n"
        "def write(x):\n    return Result\n"
    )
    edges: list[str] = []
    for path in planted.glob("*.py"):
        for imported in _imported(path):
            if imported == "src.contracts.result" or imported.startswith(
                    "src.contracts.result."):
                edges.append(f"{path.name} imports {imported}")
    assert edges, "the judge→result scan did not report a planted import"


def test_the_success_path_does_not_import_the_judge() -> None:
    found: list[str] = []
    for path in SUCCESS_PATH:
        relative = path.relative_to(REPO).as_posix()
        for imported in sorted(_imported(path)):
            if imported == "src.runtime.judge" or imported.startswith(
                    "src.runtime.judge."):
                found.append(f"{relative} imports {imported}")
    assert found == [], (
        "a success-path module imported the judge:\n  " + "\n  ".join(found)
    )


def test_the_success_path_import_scan_fires_on_a_planted_judge_edge(
        tmp_path: Path) -> None:
    """The removal proof of loop/runner/serving/main → judge."""
    planted = tmp_path / "loop.py"
    planted.write_text("from src.runtime.judge.shadow import ShadowJudge\n")
    found: list[str] = []
    for imported in _imported(planted):
        if imported == "src.runtime.judge" or imported.startswith(
                "src.runtime.judge."):
            found.append(imported)
    assert found, "the success-path→judge scan did not report a planted import"


def test_forbidden_edges_stay_empty_now_that_the_judge_package_exists() -> None:
    """INV-002 over the real tree, after `src/runtime/judge/` is a directory."""
    assert forbidden_edges(REPO) == []


def test_no_run_produces_a_result_t214_is_still_open() -> None:
    """Named residual. T213's join exists; no run, and not this judge, calls it.

    Inventing a `Result` here so the judge had a live key would be T214
    discharged as a convenience. The construction-site invariant already
    forbids a new `Result(` under `src/`; this arm names the join call
    the residual is about.
    """
    assert T214_RESIDUAL_NO_RUN_PRODUCES_A_RESULT
    scanned = (
        *SUCCESS_PATH,
        *JUDGE_DIR.glob("*.py"),
    )
    hits: list[str] = []
    for path in scanned:
        text = path.read_text()
        relative = path.relative_to(REPO).as_posix()
        for name in JOIN_NAMES:
            if name in text:
                pass
    assert hits == [], (
        "a success-path or judge module called the T213 join; that call "
        "site is T214's and is still open:\n  " + "\n  ".join(hits)
    )
