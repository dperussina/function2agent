"""T118 — the **SC-001** window, split into its two spans and reported with the
size of the thing it was measured over.

**Criterion**: SC-001 — *an operator with a running application reaches a first
verified answer in under 15 minutes from starting configuration, unattended, on
a reference application.*

## Why one number is the wrong instrument

SC-001 is a compound of a **bounded** step and an **unbounded** one. Everything
after analysis is work whose cost is a function of the question; analysis is
work whose cost is a function of the *repository*, and **U-21** records
`codegraph`'s scale claim as untested on a single small-repository datapoint
(`adk-python`, 1,867 files, 48,154 nodes, 7.8 s — a small fraction of the
claimed file count, extrapolating nothing).

Reported as one figure the criterion is quietly true on small inputs and
quietly false on large ones, and no reader can tell which they are holding.
So this module refuses to produce a window that does not carry:

- `analysis_seconds` and `remainder_seconds` **separately**, never only a
  total;
- the **size** of the subject the window was measured over, because a wall
  time without its denominator is a figure nobody can divide;
- FR-045's **not-verifiable share** over the same run, because SC-001 asks for
  a first *verified* answer and a high refusal share can defeat it without
  anything in the runtime being wrong.

## The third of those is the one that is easy to leave out, and the
## specification says so in as many words

> *"SC-001 asks for a first verified answer within fifteen minutes, which a
> high refusal share can defeat without anything in the runtime being wrong —
> so SC-001 is not independently assessable until FR-045 has reported at least
> once."*

That is why `Sc001Report` has **no verdict member meaning "met"**. It reports
where the first verified answer landed relative to the window, and it reports
whether the criterion is assessable at all — which is a property of FR-045
having reported over *production* traffic (SC-019: "the first window to close
after first production traffic"), not of anything a harness can arrange for
itself. A harness run supplies `production=False` and the report says
`assessable=False` in the same breath as its timing.

**No threshold is applied to the share and none is invented here.** FR-045
pre-registers none, deliberately, and a number chosen in this module would be
the inherited-number failure the corpus catches elsewhere. The share is
reported, with its denominator and its breakdown by refusal reason, and the
owner reads it.

## `codegraph` has not been run against anything this module has timed

**T004** pins `codegraph` and asserts its schema hash, and it is separately
open: `CODEGRAPH_SCHEMA_SHA256` is `None`, so `codegraph_pin.verify()` fails
closed rather than passing vacuously, and **T119 — which would invoke
`codegraph` at all — does not exist.** An analysis span measured today
therefore times an analysis step that **does not include the unbounded work
U-21 is about**.

That does not make this instrument premature; it makes the marking
load-bearing. `codegraph_invoked` defaults to `False` and a report carrying
`False` states in its own payload that its analysis figure is not a datapoint
against U-21's open question. The failure being prevented is a later reader
finding a small `analysis_seconds` in a committed artifact and reading it as
evidence that analysis is cheap at scale.
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Iterator

#: SC-001's window. Read off the criterion — *"in under 15 minutes"* — and not
#: chosen here. It is a bound to compare against, never a budget to spend.
SC001_WINDOW_SECONDS = 15 * 60.0

#: What a report says about its analysis span when `codegraph` did not run.
#: Carried in the payload rather than in a comment, because the artifact
#: outlives the module a reader would have to go and find.
NO_CODEGRAPH_CAVEAT = (
    "codegraph was NOT invoked in this run, so analysis_seconds does not "
    "include the step U-21's untested scale claim is about. T004 leaves "
    "CODEGRAPH_SCHEMA_SHA256 unset and T119 — which would invoke codegraph — "
    "does not exist. This figure is not a datapoint against U-21."
)

#: Why SC-001 is not assessable from a harness run alone. Quoted from the
#: specification rather than paraphrased, so the artifact carries the reason
#: and not a summary of it.
NOT_INDEPENDENTLY_ASSESSABLE = (
    "SC-001 asks for a first verified answer within fifteen minutes, which a "
    "high refusal share can defeat without anything in the runtime being "
    "wrong — so SC-001 is not independently assessable until FR-045 has "
    "reported at least once over production traffic (SC-019)."
)


class Sc001ReportError(ValueError):
    """A window or a report that would be unreadable. Never defaulted around."""


class Sc001Verdict(Enum):
    """Where the first verified answer landed.

    **There is no member meaning "met".** A verdict here is one half of the
    pair SC-001 needs; `Sc001Report.assessable` is the other, and it is the
    half that a timing-only reading drops.
    """

    NO_VERIFIED_ANSWER = "no_verified_answer"
    FIRST_VERIFIED_ANSWER_WITHIN_WINDOW = "first_verified_answer_within_window"
    FIRST_VERIFIED_ANSWER_OUTSIDE_WINDOW = "first_verified_answer_outside_window"


# ---------------------------------------------------------------------------
# The subject's size.


@dataclass(frozen=True)
class SubjectSize:
    """The size of the application an SC-001 window was measured over.

    Four figures rather than one, because `codegraph` is described in files,
    nodes and edges and a size in lines alone is not comparable to the single
    datapoint U-21 has. `codegraph_nodes` and `codegraph_edges` are `None`
    until something has actually run `codegraph`; **no arithmetic anywhere
    turns a line count into a node count.**
    """

    files: int
    lines: int
    code_lines: int
    definitions: int
    measured_by: str
    codegraph_nodes: int | None = None
    codegraph_edges: int | None = None

    def __post_init__(self) -> None:
        for name in ("files", "lines", "code_lines", "definitions"):
            value = getattr(self, name)
            if not isinstance(value, int) or value <= 0:
                raise Sc001ReportError(
                    f"SubjectSize.{name} must be a positive integer; got "
                    f"{value!r}. A size of zero is a measurement that did not "
                    "happen, and it divides nothing."
                )
        if not self.measured_by:
            raise Sc001ReportError(
                "SubjectSize.measured_by must name what took the measurement. "
                "A size with no provenance cannot be re-taken."
            )

    @classmethod
    def from_document(cls, document: Mapping[str, Any]) -> SubjectSize:
        """Read a `size.json`-shaped document.

        Every key is required and none is defaulted. A size document that has
        lost a field is a stale artifact, and filling the hole in here would
        make the staleness invisible at exactly the moment it matters.
        """
        required = (
            "application_files",
            "application_lines",
            "application_code_lines",
            "application_definitions",
            "measured_by",
        )
        missing = [key for key in required if key not in document]
        if missing:
            raise Sc001ReportError(
                f"size document is missing {', '.join(missing)}. It is not "
                "defaulted: a missing figure means the document and its "
                "generator have drifted apart."
            )
        return cls(
            files=document["application_files"],
            lines=document["application_lines"],
            code_lines=document["application_code_lines"],
            definitions=document["application_definitions"],
            measured_by=document["measured_by"],
            codegraph_nodes=document.get("codegraph_nodes"),
            codegraph_edges=document.get("codegraph_edges"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "files": self.files,
            "lines": self.lines,
            "code_lines": self.code_lines,
            "definitions": self.definitions,
            "measured_by": self.measured_by,
            "codegraph_nodes": self.codegraph_nodes,
            "codegraph_edges": self.codegraph_edges,
        }


# ---------------------------------------------------------------------------
# FR-045's share.


@dataclass(frozen=True)
class NotVerifiableShare:
    """FR-045's share of reported results returned not-verifiable.

    **The denominator is the set of results the run attempted**, never the set
    it liked. That is the whole mechanism: a harness that divided by the
    verified count would report `0.0` on a run where three questions in four
    refused, and would then hand SC-001 a green timing produced by the one
    question that happened to answer.
    """

    attempted: int
    not_verifiable: int
    by_reason: Mapping[str, int] = field(default_factory=dict)
    #: Whether this is FR-045's production reporting window. A harness supplies
    #: `False`; nothing a harness can do makes it `True`, which is the point.
    production: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.attempted, int) or self.attempted <= 0:
            raise Sc001ReportError(
                f"NotVerifiableShare.attempted must be a positive integer; got "
                f"{self.attempted!r}. A share over an empty population is not "
                "a low share, it is no measurement (FR-045)."
            )
        if not isinstance(self.not_verifiable, int) or self.not_verifiable < 0:
            raise Sc001ReportError(
                "NotVerifiableShare.not_verifiable must be a non-negative "
                f"integer; got {self.not_verifiable!r}."
            )
        if self.not_verifiable > self.attempted:
            raise Sc001ReportError(
                f"NotVerifiableShare has {self.not_verifiable} not-verifiable "
                f"results out of {self.attempted} attempted. The denominator "
                "is the attempted set; a numerator above it means the two "
                "were counted over different populations."
            )
        counted = sum(self.by_reason.values())
        if counted != self.not_verifiable:
            raise Sc001ReportError(
                f"by_reason accounts for {counted} results but "
                f"{self.not_verifiable} were not verifiable. FR-045 requires "
                "the share broken down by refusal reason, and a breakdown "
                "that does not sum to its own total describes neither."
            )

    @property
    def share(self) -> float:
        return self.not_verifiable / self.attempted

    def to_dict(self) -> dict[str, Any]:
        return {
            "attempted": self.attempted,
            "not_verifiable": self.not_verifiable,
            "share": self.share,
            "by_reason": dict(sorted(self.by_reason.items())),
            "production_window": self.production,
            # Stated in the payload, because a bare share invites a threshold
            # and FR-045 pre-registers none on purpose.
            "threshold": None,
            "threshold_note": (
                "no threshold is pre-registered for this share (FR-045); it "
                "is an owner review input, not a pass mark"
            ),
        }


# ---------------------------------------------------------------------------
# The window.


@dataclass(frozen=True)
class Sc001Window:
    """One SC-001 window, as two spans that are never fused.

    `analysis_seconds` is not optional and has no default. A window that
    reached this constructor without one would be a single fused total, which
    is the exact defect T118 exists to prevent.
    """

    total_seconds: float
    analysis_seconds: float
    #: `None` when the run reached no verified answer at all — which is a
    #: different fact from a slow one and is reported as one.
    first_verified_answer_seconds: float | None

    def __post_init__(self) -> None:
        if self.total_seconds < 0 or self.analysis_seconds < 0:
            raise Sc001ReportError(
                "an SC-001 span cannot be negative; got total="
                f"{self.total_seconds!r} analysis={self.analysis_seconds!r}"
            )
        if self.analysis_seconds > self.total_seconds:
            raise Sc001ReportError(
                f"analysis took {self.analysis_seconds}s of a "
                f"{self.total_seconds}s window. The analysis span is a part "
                "of the window, so a part larger than the whole means the two "
                "were timed over different intervals."
            )
        if (
            self.first_verified_answer_seconds is not None
            and self.first_verified_answer_seconds > self.total_seconds
        ):
            raise Sc001ReportError(
                "the first verified answer landed after the window closed, "
                "which means it was not timed inside it"
            )

    @property
    def remainder_seconds(self) -> float:
        """Everything in the window that was not analysis.

        The bounded half. Named rather than left to subtraction, because the
        subtraction is what nobody does when they read one number.
        """
        return self.total_seconds - self.analysis_seconds

    def verdict(self) -> Sc001Verdict:
        if self.first_verified_answer_seconds is None:
            return Sc001Verdict.NO_VERIFIED_ANSWER
        if self.first_verified_answer_seconds < SC001_WINDOW_SECONDS:
            return Sc001Verdict.FIRST_VERIFIED_ANSWER_WITHIN_WINDOW
        return Sc001Verdict.FIRST_VERIFIED_ANSWER_OUTSIDE_WINDOW


class Sc001Timer:
    """Times an SC-001 window and the analysis span inside it.

    The clock is injected. A timing instrument whose expectation is a property
    of the host it happens to run on is a recurring defect in this tree, and a
    fake clock is what lets both the split and its refusals be asserted
    identically everywhere.
    """

    def __init__(self, clock: Callable[[], float] = time.perf_counter):
        self._clock = clock
        self._started: float | None = None
        self._analysis_total = 0.0
        self._analysis_spans = 0
        self._first_verified: float | None = None

    def start(self) -> None:
        if self._started is not None:
            raise Sc001ReportError("this timer has already been started")
        self._started = self._clock()

    def _since_start(self) -> float:
        if self._started is None:
            raise Sc001ReportError(
                "the SC-001 window was never started, so nothing here is "
                "measured from starting configuration"
            )
        return self._clock() - self._started

    @contextmanager
    def analysis(self) -> Iterator[None]:
        """The unbounded step. Entered explicitly so it can be subtracted."""
        self._since_start()  # refuses a span outside any window
        began = self._clock()
        try:
            yield
        finally:
            self._analysis_total += self._clock() - began
            self._analysis_spans += 1

    def first_verified_answer(self) -> None:
        """Mark the instant SC-001 is actually about. Idempotent on purpose:
        the *first* verified answer is the one the criterion names, so a later
        call must not move it."""
        if self._first_verified is None:
            self._first_verified = self._since_start()

    def close(self) -> Sc001Window:
        total = self._since_start()
        if self._analysis_spans == 0:
            raise Sc001ReportError(
                "no analysis span was recorded, so this window is a single "
                "fused total. SC-001 is a compound of a bounded step and an "
                "unbounded one (U-21) and must not be reported as one figure."
            )
        return Sc001Window(
            total_seconds=total,
            analysis_seconds=self._analysis_total,
            first_verified_answer_seconds=self._first_verified,
        )


# ---------------------------------------------------------------------------
# The report — the only thing anybody outside this module should be quoting.


@dataclass(frozen=True)
class Sc001Report:
    """Everything that must appear **wherever SC-001 is reported**.

    Three of the four fields are required and have no default. That is the
    mechanism: there is no way to build this object holding a timing and
    nothing else, so there is no artifact a reader can quote a green SC-001
    out of without the size it was measured over and the refusal share that
    produced it.
    """

    window: Sc001Window
    subject_size: SubjectSize
    not_verifiable: NotVerifiableShare
    subject: str
    codegraph_invoked: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.subject_size, SubjectSize):
            raise Sc001ReportError(
                "Sc001Report.subject_size must be a SubjectSize. SC-001's "
                "window is meaningless without the size of the application it "
                "was measured over (T118, U-21)."
            )
        if not isinstance(self.not_verifiable, NotVerifiableShare):
            raise Sc001ReportError(
                "Sc001Report.not_verifiable must be a NotVerifiableShare. "
                "SC-001 asks for a first *verified* answer, so a report "
                "without FR-045's share does not say what produced its timing."
            )
        if not self.subject:
            raise Sc001ReportError("Sc001Report.subject must name the application")

    @property
    def assessable(self) -> bool:
        """Whether SC-001 can be assessed from this report at all.

        Derived, never asserted. It is `True` exactly when FR-045 has reported
        over a production window — which is what the specification makes the
        precondition, and which no harness run can arrange for itself.
        """
        return self.not_verifiable.production

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "criterion": "SC-001",
            "subject": self.subject,
            "window_seconds": SC001_WINDOW_SECONDS,
            "verdict": self.window.verdict().value,
            "assessable": self.assessable,
            "total_seconds": self.window.total_seconds,
            "analysis_seconds": self.window.analysis_seconds,
            "remainder_seconds": self.window.remainder_seconds,
            "first_verified_answer_seconds": (
                self.window.first_verified_answer_seconds
            ),
            "subject_size": self.subject_size.to_dict(),
            "not_verifiable": self.not_verifiable.to_dict(),
            "codegraph_invoked": self.codegraph_invoked,
        }
        if not self.assessable:
            payload["not_assessable_because"] = NOT_INDEPENDENTLY_ASSESSABLE
        if not self.codegraph_invoked:
            payload["analysis_coverage_caveat"] = NO_CODEGRAPH_CAVEAT
        return payload
