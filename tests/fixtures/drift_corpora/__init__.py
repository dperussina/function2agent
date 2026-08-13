"""Loaders for Phase 6's four committed drift corpora — T154, T155, T157, T158.

The four corpora live in hyphenated directories the task list names exactly:

| Task | Corpus directory | Criteria |
|---|---|---|
| T154 | `tests/fixtures/drift-source/` | FR-053, SC-008 |
| T155 | `tests/fixtures/drift-deployment/` | SC-009, **SC-020** |
| T157 | `tests/fixtures/spec-withdrawn/` | **SC-021** |
| T158 | `tests/fixtures/operation-added/` | **SC-026** |

A hyphen is not an identifier, so those directories cannot be Python packages
and their loaders cannot live inside them. That is the same shape
`tests/fixtures/value-faults/` already has — data and prose in the fixture
directory, loading and recomputation in an importable module — and this package
is that module for all four. `tests/fixtures/admission/` puts its loader in its
own `__init__.py` only because `admission` happens to have no hyphen in it.

## What every loader in this package is for, and what none of them is

Each loader **recomputes** the corpus's declared expectations from the corpus's
own primary data and refuses a disagreement. It is not a convenience wrapper
around `json.load`. A committed expectation nobody recomputes is a number, and
the shipped defects this repository keeps finding are numbers nobody
recomputed.

**None of them scores a detector**, because at the time they were committed no
Phase 6 detector existed: T137 through T153 are all open. What is asserted here
is that the corpora are internally consistent, that their populations contain
the cases the criteria need, and — the part that matters — that each contains
a population that a trivially-wrong detector **fails**.

## The measurement none of this is

⚠️ **Drift detection has no detection rate, no false-alarm rate and no latency
on either of its two clocks**, and these four corpora do not change that.
[`specs/001-discovery-validation/VERDICT.md`](../../../specs/001-discovery-validation/VERDICT.md)
line 162 states it for the capability as a whole; feature 001's only drift
experiment, **E13**, has three named mutations that all move the source, no arm
in which the deployment stops serving, and
[`plan.md`](../../../specs/002-spec-aware-agent-runtime/plan.md) line 831 says
in bold that **E13 never ran at all**.

A committed corpus is an instrument, not a reading. Nothing in this package may
be written up as retiring that gap.
"""

from __future__ import annotations

from datetime import datetime, timezone


class CorpusInconsistent(Exception):
    """A committed declaration disagrees with what the corpus recomputes.

    Raised at load time by every loader in this package. It is deliberately
    not a `pytest` failure: a corpus that cannot be loaded is broken for every
    consumer, not only for the test that noticed.
    """


def instant(text: str) -> datetime:
    """One UTC instant, parsed strictly.

    Every timeline in this package is UTC with an explicit `Z`. A naive
    timestamp is refused rather than assumed to be UTC, because the corpora
    whose whole purpose is a controlled change time cannot afford an offset
    nobody stated.
    """
    if not text.endswith("Z"):
        raise CorpusInconsistent(
            f"{text!r} carries no explicit UTC marker. Every instant in these "
            "corpora is a controlled quantity and must say which clock it is on."
        )
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo != timezone.utc:
        raise CorpusInconsistent(f"{text!r} did not parse as UTC")
    return parsed


def seconds_between(earlier: str, later: str) -> float:
    """`later - earlier`, in seconds. Negative if the corpus has them backwards."""
    return (instant(later) - instant(earlier)).total_seconds()
