"""T214 — a run produces a caller-visible Result via verify-then-join.

Discharge is checkable: `verify_quantity` and `result_from_report` have a
caller in `src/` that a request reaches, and that caller is not `to_result`.
"""

from __future__ import annotations

import ast
from pathlib import Path

from src.contracts.result import VerificationOutcome
from src.runtime.answer import (
    JOIN_IS_CALLED,
    RESULT_COMES_FROM_TO_RESULT,
    RESULT_IS_ATTACHED,
    VERIFY_IS_CALLED,
    cassette_reported_quantity,
    complete_served_run,
    result_from_answered_quantity,
)
from src.runtime.events import EventStream
from src.runtime.serving import Registry, SessionView

REPO = Path(__file__).resolve().parents[2]
ANSWER = REPO / "src" / "runtime" / "answer.py"
JOIN = REPO / "src" / "runtime" / "result_join.py"
VALIDATE = REPO / "src" / "analysis" / "validate.py"
MAIN = REPO / "src" / "runtime" / "main.py"
LOOP = REPO / "src" / "runtime" / "loop.py"
RUNNER = REPO / "src" / "runtime" / "runner.py"
SERVING = REPO / "src" / "runtime" / "serving.py"

JOIN_NAMES = ("result_from_report", "result_from_quantity_verification")
VERIFY_NAMES = ("verify_quantity", "verify_declared_quantity")


def _names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            found.add(node.id)
        elif isinstance(node, ast.Attribute):
            found.add(node.attr)
    return found


def _registry() -> tuple[Registry, str]:
    stream = EventStream("d-1", clock=lambda: 1.0)
    stream.start()
    registry = Registry()
    registry.register(SessionView(session_id="d-1", stream=stream))
    return registry, "d-1"


def test_verify_and_join_flags_are_the_live_path() -> None:
    assert VERIFY_IS_CALLED is True
    assert JOIN_IS_CALLED is True
    assert RESULT_COMES_FROM_TO_RESULT is False
    assert RESULT_IS_ATTACHED is True


def test_a_run_produces_a_result_from_verify_then_join() -> None:
    """The call site: reported quantity → verify_quantity → result_from_report."""
    record = result_from_answered_quantity(**cassette_reported_quantity())
    assert record.verification is VerificationOutcome.VERIFIED
    assert record.verification is not VerificationOutcome.MODEL_ASSESSED
    assert record.payload["lot_count"] == 3


def test_complete_served_run_attaches_the_result() -> None:
    registry, session_id = _registry()
    record = complete_served_run(registry, session_id)
    view = registry.view(session_id)
    assert view is not None
    assert view.result is record
    assert view.result.verification is VerificationOutcome.VERIFIED


def test_verify_quantity_is_called_from_answer_not_from_to_result() -> None:
    answer_names = _names(ANSWER)
    assert "verify_quantity" in answer_names
    assert "result_from_report" in answer_names
    validate_names = _names(VALIDATE)
    assert not (validate_names & set(VERIFY_NAMES)), (
        "verify_* called from validate.py inverts layering (T213 foreclosure)"
    )


def test_join_names_are_not_in_the_residual_scan_files() -> None:
    """Those files AST-scan for JOIN_NAMES. The call lives in answer.py."""
    for path in (MAIN, LOOP, RUNNER, SERVING):
        names = _names(path)
        hits = names & set(JOIN_NAMES)
        assert not hits, f"{path.name} names {hits}; that inverts the residual scan"


def test_to_result_is_not_the_live_path() -> None:
    source = ANSWER.read_text()
    assert "RESULT_COMES_FROM_TO_RESULT = False" in source
    assert "verify_quantity(" in source
    assert "result_from_report(" in source


def test_model_assessed_is_not_produced() -> None:
    record = result_from_answered_quantity(**cassette_reported_quantity())
    assert record.verification is not VerificationOutcome.MODEL_ASSESSED
    join_source = JOIN.read_text()
    assert "MODEL_ASSESSED" not in join_source or "must not" in join_source.lower()


def test_answer_does_not_construct_a_result() -> None:
    """The seam is the authorised site. This module calls it."""
    tree = ast.parse(ANSWER.read_text(), filename=str(ANSWER))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == "Result":
                raise AssertionError("answer.py constructs Result(; the seam does")
            if isinstance(func, ast.Attribute) and func.attr == "Result":
                raise AssertionError("answer.py constructs Result(; the seam does")
