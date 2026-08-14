"""T174 — the three inject modes SC-025's differential needs.

**Criterion**: SC-025. **Requirement**: FR-039, FR-052.

The same sessions must be runnable with the shadow judge agreeing with the
verifier, disagreeing with it, and not running at all. T175 is the battery
that will assert caller-visible records and gate decisions are identical
across those three; this module is only the selectable modes that battery
will point at.

A live vendor SDK is not one of the modes. T058's `call` still raises
`TransportUnavailableError`; the decide function here is a typed label
flip, not a model. Principle I's pairwise/calibration clause does not
apply: the judge is outside the success path, and these modes exist to
keep it there while T175 measures that it stayed there.

`None` is the off mode's return, not a fourth verdict. A function that
returned a label meaning "did not run" would write a row for a judge that
did not run, and the empty table is the only honest form of absence.
"""

from __future__ import annotations

from typing import Callable

MODE_AGREE = "agree"
MODE_DISAGREE = "disagree"
MODE_OFF = "off"

#: Stable order so a reader and a parametrize see the same three.
MODES: tuple[str, ...] = (MODE_AGREE, MODE_DISAGREE, MODE_OFF)

#: The judge's own vocabulary. Not `VerificationOutcome` — that type is the
#: success-path record, and this package does not import it.
VERDICT_CORRECT = "correct"
VERDICT_INCORRECT = "incorrect"
VERDICTS = frozenset({VERDICT_CORRECT, VERDICT_INCORRECT})

DecideFn = Callable[[str], str]


class JudgeInjectError(ValueError):
    """A mode or label SC-025 does not name."""


def _agree(verifier_label: str) -> str:
    """Echo the verifier's label. The agreeing mode is this identity."""
    return verifier_label


def _disagree(verifier_label: str) -> str:
    """Write the other closed label. Two members, so the flip is total."""
    if verifier_label == VERDICT_CORRECT:
        return VERDICT_INCORRECT
    return VERDICT_CORRECT


def decide_for(mode: str) -> DecideFn | None:
    """The injectable decide function for one of SC-025's three modes.

    `None` means the judge does not run. The shadow writer treats that as
    no subscribe, no schedule, no thread — not a verdict that says off.
    """
    if mode == MODE_OFF:
        return None
    if mode == MODE_AGREE:
        return _agree
    if mode == MODE_DISAGREE:
        return _disagree
    raise JudgeInjectError(
        f"{mode!r} is not a judge inject mode ({list(MODES)}). "
        "SC-025's three are agree, disagree, and not running at all."
    )
