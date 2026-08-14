"""T174 — the three inject modes SC-025 names, selectable.

T175 is the differential battery and is not this file. These arms only
assert that agree, disagree, and off exist and produce the three
behaviours that battery will range over: the same label, the other
label, and no function at all.
"""

from __future__ import annotations

import pytest

from src.runtime.judge.inject import (
    MODE_AGREE,
    MODE_DISAGREE,
    MODE_OFF,
    MODES,
    VERDICT_CORRECT,
    VERDICT_INCORRECT,
    VERDICTS,
    JudgeInjectError,
    decide_for,
)

THREE_MODES_ARE_SELECTABLE = True


def test_the_three_modes_are_selectable() -> None:
    """SC-025's population. A shorter tuple is a mode T175 cannot name."""
    assert THREE_MODES_ARE_SELECTABLE
    assert MODES == (MODE_AGREE, MODE_DISAGREE, MODE_OFF)
    assert set(MODES) == {MODE_AGREE, MODE_DISAGREE, MODE_OFF}


def test_agree_writes_the_verifier_label() -> None:
    decide = decide_for(MODE_AGREE)
    assert decide is not None
    assert decide(VERDICT_CORRECT) == VERDICT_CORRECT
    assert decide(VERDICT_INCORRECT) == VERDICT_INCORRECT


def test_disagree_writes_the_other_label() -> None:
    decide = decide_for(MODE_DISAGREE)
    assert decide is not None
    assert decide(VERDICT_CORRECT) == VERDICT_INCORRECT
    assert decide(VERDICT_INCORRECT) == VERDICT_CORRECT


def test_off_writes_no_verdict() -> None:
    """`None`, not a label that means off. A row for 'did not run' is a run."""
    assert decide_for(MODE_OFF) is None


def test_an_unknown_mode_is_refused() -> None:
    with pytest.raises(JudgeInjectError, match="not a judge inject mode"):
        decide_for("calibrate")


def test_the_judge_vocabulary_is_closed_and_is_not_a_verification_outcome() -> None:
    """The names are this package's. Importing VerificationOutcome is T173's scan."""
    assert VERDICTS == {VERDICT_CORRECT, VERDICT_INCORRECT}
    assert "verified" not in VERDICTS
    assert "model_assessed" not in VERDICTS
