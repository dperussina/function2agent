"""T181 — the per-call threshold, recorded unset, and the write gate it holds.

**Requirement**: FR-041. **Criterion**: SC-014. **Also**: OD-10.

FR-041: before any write capability ships, the effect gate's read-only
precision MUST be measured against a labelled corpus, against a threshold
pre-registered for a **per-call** gate. The threshold from the superseded
per-tool gate MUST NOT be inherited by default.

SC-014: no write capability is released until that measurement exists.

OD-10: v1 is read-only against the target for its whole life. The exit
condition is FR-041. This module is the record that the exit has not
opened.

## THE HONEST STATE, AND WHY A NUMBER HERE IS THE DEFECT

The per-call threshold is **unset**. That is not a pending fill-in. It is
the decision. Pre-registration for a per-call gate is an owner act that
precedes measurement. The superseded per-tool number was **0.98**, chosen
for a static label over a curated catalogue. A per-call gate over a general
shell has a different base rate and a different blast radius. Copying 0.98
here, or inventing 0.95 to look like a new decision, is the
inherited-number failure arriving by a new door — the failure FR-041 was
written after.

`PER_CALL_THRESHOLD` is the sentinel `UNSET`. It has no default numeric
value. `test_the_threshold_has_no_numeric_default` plants one.

## WRITES STAY BLOCKED WHILE IT IS UNSET

`write_capability_released` returns `False` while the threshold is unset.
That is SC-014 on this side of the gate. OD-10 / FR-009 already refuse
every write at the enforcement point and at the filesystem classifier;
this module does not re-implement those paths and does not import them.
What it records is that a write capability **may not ship** until a
threshold is pre-registered for a per-call gate *and* measured against
T180's labelled corpus.

`test_writes_stay_blocked_while_the_threshold_is_unset` plants the unset
branch returning `True`, which is a write becoming allowable while the
threshold is still unset.

T180 is the residual that produces the labels the measurement needs.
This module does not score. Inventing a precision figure so the gate
could open is the same inherited-number failure as inventing the
threshold.

## WHAT THIS MUST NOT BECOME

* A success-path read that changes allow/deny. `loop.py`, `serving.py`,
  and `result.py` do not import this module.
* T180. No snapshot, no call, no diff, no claim that the corpus is labelled.
* T176 / T177. Adjudication and the margin report are a sibling's files.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any


class Unset:
    """The per-call threshold has not been pre-registered. Not a number.

    A dedicated type so `None` cannot be read as an oversight and filled
    with 0.98, and so `isinstance(..., (int, float))` is false by
    construction rather than by a comment.
    """

    def __repr__(self) -> str:
        return "UNSET"

    def __bool__(self) -> bool:
        return False


UNSET = Unset()

#: The per-call threshold. Unset. No default numeric value. Assigning
#: 0.98 (the superseded per-tool number) or 0.95 (an invented stand-in)
#: is the inherited-number failure FR-041 exists to stop.
PER_CALL_THRESHOLD: object = UNSET

#: T180 has not labelled the corpus, so the measurement FR-041 requires
#: has not run. Named rather than implied: a `True` here while the
#: threshold is still unset would be a measurement against nothing.
MEASURED_AGAINST_LABELLED_CORPUS = False

THRESHOLD_UNSET_BECAUSE = (
    "No per-call threshold is pre-registered. FR-041 requires the "
    "threshold to be pre-registered for a per-call gate before any write "
    "capability ships, and forbids inheriting the superseded per-tool "
    "number (0.98) by default: different base rate, different blast "
    "radius. Inventing 0.95 here is the same failure arriving by a new "
    "door. SC-014 holds the write capability until the measurement "
    "exists. OD-10 is why v1 is read-only until that exit opens. T180 "
    "is the residual that produces the labels the measurement scores."
)

T180_RESIDUAL = (
    "T180's state-diff oracle labels the corpus by observable state. "
    "Until it runs there is no labelled set to measure against, so "
    "MEASURED_AGAINST_LABELLED_CORPUS stays False and the threshold "
    "stays unset. This module records that fact; it does not snapshot "
    "the reference application."
)


class WriteCapabilityBlocked(RuntimeError):
    """A write capability was asked for while FR-041's exit is closed."""


class ModuleTextUnavailable(RuntimeError):
    """This module's own text could not be located for the arm that reads it."""


def write_capability_released() -> bool:
    """SC-014. False until a per-call threshold is pre-registered and measured.

    The unset branch returns False on purpose. Flipping it to True is a
    write becoming allowable while the threshold is still unset — the
    plant `test_writes_stay_blocked_while_the_threshold_is_unset` applies.
    """
    if PER_CALL_THRESHOLD is UNSET:
        return False
    if not MEASURED_AGAINST_LABELLED_CORPUS:
        return False
    return True


def refuse_unreleased_write() -> None:
    """Raise rather than return a flag a caller could ignore."""
    if not write_capability_released():
        raise WriteCapabilityBlocked(
            "no write capability is released: the per-call threshold is "
            "unset and the labelled-corpus measurement has not run "
            "(FR-041, SC-014, OD-10)"
        )


@dataclass(frozen=True)
class EffectPrecision:
    """FR-041's gate record. Constructed by `report()`, not by hand."""

    per_call_threshold: object
    measured_against_labelled_corpus: bool
    write_capability_released: bool

    def document(self) -> dict[str, Any]:
        unset = self.per_call_threshold is UNSET
        return {
            "per_call_threshold": None if unset else self.per_call_threshold,
            "per_call_threshold_state": "unset" if unset else "registered",
            "threshold_absent_because": (
                THRESHOLD_UNSET_BECAUSE if unset else None
            ),
            "measured_against_labelled_corpus": (
                self.measured_against_labelled_corpus
            ),
            "measurement_absent_because": (
                None if self.measured_against_labelled_corpus
                else T180_RESIDUAL
            ),
            "write_capability_released": self.write_capability_released,
            "t180_residual": T180_RESIDUAL,
        }


def report() -> EffectPrecision:
    """The honest record: unset, unmeasured, writes not released."""
    return EffectPrecision(
        per_call_threshold=PER_CALL_THRESHOLD,
        measured_against_labelled_corpus=MEASURED_AGAINST_LABELLED_CORPUS,
        write_capability_released=write_capability_released(),
    )


def module_source() -> str:
    """This module's own text, for the arm that reads it for a number."""
    module = inspect.getmodule(report)
    if module is None:
        raise ModuleTextUnavailable(
            "inspect.getmodule() could not locate the module defining "
            "report(), so this module's own text cannot be read. Refused "
            "rather than returned empty: the arm that calls this searches "
            "the text for a numeric threshold and reports finding none, "
            "and text that was never read finds none either."
        )
    return inspect.getsource(module)
