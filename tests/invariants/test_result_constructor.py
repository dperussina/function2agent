"""INV-001 — no caller-visible result without a verification outcome (FR-025).

The check is structural: `Result` has no default for `verification`, so the
absence is a `TypeError` from the constructor rather than a `None` that a later
reader has to notice.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from src.contracts import result as result_module
from src.contracts.result import (
    MissingVerification,
    Result,
    VerificationOutcome,
)


def test_verification_is_required() -> None:
    with pytest.raises(TypeError):
        Result(payload={"ok": True})  # type: ignore[call-arg]


def test_verification_must_be_a_member_not_a_string() -> None:
    with pytest.raises(MissingVerification):
        Result("verified", payload={"ok": True})  # type: ignore[arg-type]


def test_no_absent_member_exists() -> None:
    """There is no value of the field meaning 'not verified yet'.

    A `PENDING` or `UNKNOWN` member would reintroduce exactly the state FR-025
    forbids, wearing a name that looks deliberate.
    """
    names = {member.name for member in VerificationOutcome}
    for forbidden in ("PENDING", "UNKNOWN", "NONE", "ABSENT", "UNSET"):
        assert forbidden not in names


def test_non_verified_outcome_requires_a_reason() -> None:
    with pytest.raises(MissingVerification):
        Result(VerificationOutcome.NOT_VERIFIABLE, payload=None)
    ok = Result(
        VerificationOutcome.NOT_VERIFIABLE,
        payload=None,
        reason="contract marked provisional",
    )
    assert not ok.is_verified


def test_model_assessment_is_not_a_verification() -> None:
    """Principle I: a model's opinion does not satisfy FR-025."""
    assessed = Result(
        VerificationOutcome.MODEL_ASSESSED,
        payload={"summary": "looks right"},
        reason="no contract to check against",
    )
    assert not assessed.is_verified


def test_provisional_can_never_be_verified() -> None:
    with pytest.raises(MissingVerification):
        Result(VerificationOutcome.VERIFIED, payload=1, provisional=True)


def test_verification_has_no_default_in_the_source() -> None:
    """The removal proof, read off the source rather than the behaviour.

    Behaviour tests above would keep passing if someone gave `verification` a
    default of `VERIFIED` — the constructor would accept a missing argument and
    every assertion above still holds. This one fails on that edit.
    """
    source = Path(inspect.getfile(result_module)).read_text()
    tree = ast.parse(source)
    (cls,) = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.ClassDef) and n.name == "Result"
    ]
    fields = [n for n in cls.body if isinstance(n, ast.AnnAssign)]
    assert fields, "Result has no annotated fields"
    first = fields[0]
    assert isinstance(first.target, ast.Name)
    assert first.target.id == "verification", (
        "verification must be the first field, so a later field with a "
        "default cannot make it optional"
    )
    assert first.value is None, (
        "Result.verification has acquired a default. FR-025 admits no result "
        "without a verification outcome, and a default is one."
    )
