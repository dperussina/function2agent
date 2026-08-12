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
    STALENESS_NOT_STATED,
    Corroboration,
    MissingVerification,
    Result,
    StaleMarking,
    VerificationOutcome,
)


def test_verification_is_required() -> None:
    with pytest.raises(TypeError):
        Result(  # type: ignore[call-arg]
            payload={"ok": True}, corroboration=Corroboration.NOT_STATED
        )


def test_verification_must_be_a_member_not_a_string() -> None:
    with pytest.raises(MissingVerification):
        Result(  # type: ignore[arg-type]
            "verified",
            payload={"ok": True},
            corroboration=Corroboration.CORROBORATED,
        )


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
        Result(
            VerificationOutcome.NOT_VERIFIABLE,
            payload=None,
            corroboration=Corroboration.NOT_STATED,
        )
    ok = Result(
        VerificationOutcome.NOT_VERIFIABLE,
        payload=None,
        corroboration=Corroboration.PROVISIONAL,
        reason="contract marked provisional",
    )
    assert not ok.is_verified


def test_model_assessment_is_not_a_verification() -> None:
    """Principle I: a model's opinion does not satisfy FR-025."""
    assessed = Result(
        VerificationOutcome.MODEL_ASSESSED,
        payload={"summary": "looks right"},
        corroboration=Corroboration.NOT_STATED,
        reason="no contract to check against",
    )
    assert not assessed.is_verified


def test_provisional_can_never_be_verified() -> None:
    with pytest.raises(MissingVerification):
        Result(
            VerificationOutcome.VERIFIED,
            payload=1,
            corroboration=Corroboration.PROVISIONAL,
        )


def test_corroboration_has_no_default_in_the_source() -> None:
    """The removal proof for T126's required argument, read off the source.

    Every behavioural arm here would keep passing if `corroboration` were given
    a default of `CORROBORATED`: nothing above omits it. This one fails on that
    edit, which is the edit that would restore the defect T126 removed — a
    caller reaching a verified-looking result by saying nothing.
    """
    source = Path(inspect.getfile(result_module)).read_text()
    tree = ast.parse(source)
    (cls,) = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.ClassDef) and n.name == "Result"
    ]
    fields = {
        n.target.id: n
        for n in cls.body
        if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name)
    }
    assert "corroboration" in fields, (
        "Result no longer carries a corroboration field. FR-025's verified "
        "state must say what established it."
    )
    assert fields["corroboration"].value is None, (
        "Result.corroboration has acquired a default. Whatever the default "
        "were, it would be a claim a caller makes by omission, which is the "
        "bool-defaulting-to-False defect T126 removed."
    )


def test_the_staleness_default_makes_no_claim() -> None:
    """FR-047's field may default; what it may not default to is a claim.

    `staleness` is the one field here that does have a default, and the
    asymmetry with `corroboration` is the whole design: `NOT_STATED` says
    nothing, where `FRESH` would say the served-operation set was current on
    the strength of a caller having omitted an argument. That is the boolean
    defect moved one field over, and this arm is what stops it moving.
    """
    assert Result(
        VerificationOutcome.VERIFIED,
        payload=None,
        corroboration=Corroboration.CORROBORATED,
    ).staleness.marking is StaleMarking.NOT_STATED

    assert STALENESS_NOT_STATED.marking is StaleMarking.NOT_STATED


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
