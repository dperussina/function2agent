"""T130 — the not-verifiable share, per window, broken down by refusal reason.

**Requirement**: FR-045. **Criterion**: SC-019. **Also**: the second half of
OD-19.

What this module produces is *"the share of results returned in the
not-verifiable state, broken down by the named refusal reasons, per reporting
window"* — and nothing else. In particular it applies **no threshold**, because
none is pre-registered. See `NO_THRESHOLD`.

OD-19's second half is quoted rather than paraphrased, because it names the
thing this module is for: *"the obligation to measure the share, rather than to
assume it, is the second half of OD-19"*. FR-025's disposition — a result v1
cannot verify is returned marked rather than withheld — is the first half. The
pairing is deliberate: marking a result unverifiable and never counting how
often that happens is a disposition nobody can review.

Until a report exists, FR-045 requires the share to be **described as
unmeasured** wherever the product's verification coverage is described, under
FR-043. This module is what makes that description stop being the only honest
one; it does not itself make any claim about coverage.

## THE THREE THINGS THIS MODULE REFUSES TO DO, AND WHY EACH IS A REFUSAL

**1. It will not compare the share against anything.** FR-041 exists because a
threshold pre-registered for one gate was carried over to a different one by
default, and a share is exactly the shape that invites a number beside it. There
is no comparison operator anywhere below and
`test_the_module_contains_no_threshold_comparison` reads the source to keep it
that way. `threshold_applied` is `None` on every document, with
`NO_THRESHOLD` quoted beside it so a reader is told the absence was chosen.

**2. It will not report a share over an empty window as zero.** No results means
*there is no share*, which is not the same fact as *the share is zero* and does
not belong in the same field. `share` is `None` in that case and
`share_absent_because` names which of the two it is. This is
`costs.UNPRICED`'s treatment — an absence recorded as a decision, because a gap
reads as an oversight and the next reader fills it.

**3. It will not let a not-verifiable result go uncounted.** The breakdown is
**total over `RefusalReason`** and every member appears as a key even at zero,
so the document describes the specification's named set rather than the traffic
that happened to arrive. A window in which nothing was refused for
`SOURCES_NOT_INDEPENDENT` reports that reason at zero; it does not omit it,
because an omitted key and a key nobody could produce look identical.

## THE GAP IN THE NAMED SET, WHICH IS REAL AND IS NOT FOLDED AWAY

`RefusalReason` is the verifier's closed set, and it is **not total over the
not-verifiable population**. `REPORTED_STATE` in `src/contracts/result.py` maps
*two* outcomes onto `ReportedState.NOT_VERIFIABLE`:

* `VerificationOutcome.NOT_VERIFIABLE` — the verifier ran and refused, and there
  is a `RefusalReason`; and
* `VerificationOutcome.MODEL_ASSESSED` — **the verifier never ran**. Nothing
  consulted a precision ladder, so there is no refusal reason and there was no
  refusal. Principle I is what keeps this outcome distinct in the first place.

A breakdown keyed only on `RefusalReason` therefore cannot sum to the
not-verifiable total. Folding model-assessed results into
`NO_RECOMPUTING_CHECK` would make it sum, and would be false: those two are
different facts about a result and the whole point of the enum is that the
reason survives into the record.

So there is a second, equally closed set — `UNATTRIBUTED` — and the document
carries both. `_check_totals` asserts the two sum to the not-verifiable count,
which is what stops a record from falling between the branches.

### An open question this touches and does not resolve

[Finding 018](../../../specs/001-discovery-validation/findings/018-verifier-false-alarm-attested-denominator.md)
newly opened a contradiction whose subject is exactly this shape: *a denominator
that counts records the detector declined is inflated by records that could not
have contributed to its numerator*, and its recorded fix is a reporting rule —
report the compared count beside the denominator on every rate.

Here the declined records are in the **numerator**, so that defect is not this
one. But the adjacent question is live and is left open rather than answered:
whether a model-assessed result — one the verifier never attempted — belongs in
the same share as one it attempted and refused. FR-025 puts both in the
not-verifiable state and this module reports what FR-025 defines. `UNATTRIBUTED`
is what keeps the two separable by a reader who decides otherwise later. Nothing
here rules on it.

## WHAT IS OWED AND IS NOT BUILT

* **The record source.** This module is handed `ReportedOutcome` records. What
  writes them per session, and the store they are read back out of, is not in
  this task and not in this file. FR-045's *"obtainable without re-running any
  session and without reading the trace store directly"* is discharged in shape
  — the document is computed from records and never from a replay — and the
  store behind it is owed.
* **A registered artifact kind.** FR-045 asks for a *versioned, machine-readable
  artifact*, and `document()` carries `SCHEMA_VERSION`. It is deliberately **not**
  registered in `src/contracts/schemas.py`: OD-33 declines to mint a further
  artifact kind and defers the gating that would come with one. The consequence
  is stated rather than left implicit — **no schema gate reads this document's
  shape**, and the tests in `tests/unit/test_not_verifiable_report.py` are the
  only thing that does.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from src.contracts.result import REPORTED_STATE, ReportedState, VerificationOutcome
from src.runtime.reports.windows import ReportingWindow, interval_document
from src.runtime.verify import RefusalReason

#: Bumped when a field is added, removed or given a new meaning. Carried on the
#: document rather than declared in `src/contracts/schemas.py` — see the module
#: docstring on OD-33, and on what that costs.
SCHEMA_VERSION = "1.0.0"


#: Why no threshold is applied to the share, recorded as a decision.
#:
#: `costs.UNPRICED`'s treatment: an absence a reader would otherwise read as an
#: oversight and fill in. The number that would go here does not exist, and the
#: requirement is the thing that says so.
NO_THRESHOLD = (
    "No threshold is applied and none is pre-registered. T130 states this in "
    "its own text — *'no threshold applied because none is pre-registered'* — "
    "and FR-041 is why the omission is load-bearing rather than pending: a "
    "threshold pre-registered for one gate does not carry over to a different "
    "one by default, and a share with a number beside it is indistinguishable "
    "from a share that was compared against it. A reader who needs a bound "
    "must pre-register one against this share, over this window, and say so."
)


#: The ways a result can be in the not-verifiable state carrying **no** FR-024
#: refusal reason. Closed, and total together with `RefusalReason` over that
#: state — `_check_totals` is what holds the two totalities together.
UNATTRIBUTED: Mapping[str, str] = {
    "model_assessed": (
        "`VerificationOutcome.MODEL_ASSESSED`. The verifier did not run, so it "
        "did not refuse and there is no reason to name — a model said "
        "something about the result and `REPORTED_STATE` puts that in the "
        "not-verifiable state so it cannot be mistaken for a verification. "
        "Principle I is what keeps the outcome distinct. Counted here rather "
        "than under `NO_RECOMPUTING_CHECK`, which is a *refusal* the verifier "
        "reached after looking; these two are different facts and the enum "
        "exists so they stay different."
    ),
    "reason_not_recorded": (
        "The producer returned a not-verifiable result and named no "
        "`RefusalReason`. This is reachable today rather than hypothetical: "
        "`Result.reason` in `src/contracts/result.py` is `str | None` and its "
        "`__post_init__` requires only that it be non-empty, so free text "
        "satisfies the type while naming nothing this breakdown can key on. "
        "Counted and named, because a record silently dropped from a "
        "breakdown moves the share of every other reason without appearing "
        "anywhere."
    ),
}


class ReportInputError(ValueError):
    """A record or a window the report will not compute over.

    Raised rather than absorbed. Every value this refuses is one that would
    otherwise produce a document that looks like every other document.
    """


class ModuleTextUnavailable(RuntimeError):
    """This module's own text could not be located for the arm that reads it.

    Not a `ReportInputError`: nothing was passed in and no report is being
    computed. It is an introspection failure, and it is separate so that the
    arm reading this module cannot mistake it for a record it handed over.

    Raised rather than absorbed, for the reason `module_source` states: the
    only caller measures an absence, so text that was never read and text that
    is clean produce the same result.
    """


@dataclass(frozen=True)
class ReportedOutcome:
    """One reported result, in the only shape this report can count.

    **Not `Result`, and that is the point.** `Result` carries a
    `VerificationOutcome` and a free-text `reason`; it does not carry a
    `RefusalReason`, so a breakdown built from `Result` alone would have to
    parse prose or guess. This record makes the attribution the producer's
    explicit act: a not-verifiable result arrives carrying either a member of
    the named set or a member of `UNATTRIBUTED`, and `__post_init__` refuses
    anything else.
    """

    outcome: VerificationOutcome
    #: Set when the verifier refused. `None` otherwise.
    refusal_reason: RefusalReason | None = None
    #: A key of `UNATTRIBUTED`. Set when the state is not-verifiable and no
    #: refusal reason exists.
    unattributed: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.outcome, VerificationOutcome):
            raise ReportInputError(
                f"outcome must be a VerificationOutcome, got {self.outcome!r}"
            )
        attributed = self.refusal_reason is not None
        unattributed = self.unattributed is not None

        if self.state is not ReportedState.NOT_VERIFIABLE:
            if attributed or unattributed:
                raise ReportInputError(
                    f"{self.outcome.value} is reported as "
                    f"{self.state.value} and carries an attribution. Only a "
                    "not-verifiable result has one, and a reason attached to "
                    "a verified result would be counted into a breakdown it "
                    "is not part of."
                )
            return

        if attributed == unattributed:
            raise ReportInputError(
                "a not-verifiable result carries exactly one attribution: a "
                "RefusalReason, or a key of UNATTRIBUTED naming why there is "
                f"none. This one carries {'both' if attributed else 'neither'}"
                f" (refusal_reason={self.refusal_reason!r}, "
                f"unattributed={self.unattributed!r})."
            )
        if unattributed and self.unattributed not in UNATTRIBUTED:
            raise ReportInputError(
                f"{self.unattributed!r} is not a declared unattributed "
                f"reason. Declared: {sorted(UNATTRIBUTED)}. A free-text reason "
                "here would make the breakdown's second half open, and an "
                "open breakdown is a description of the traffic."
            )
        if self.outcome is VerificationOutcome.MODEL_ASSESSED and attributed:
            raise ReportInputError(
                "a model-assessed result carries a RefusalReason. The verifier "
                "did not run, so it did not refuse; use "
                "unattributed='model_assessed'."
            )

    @property
    def state(self) -> ReportedState:
        return REPORTED_STATE[self.outcome]


@dataclass(frozen=True)
class NotVerifiableReport:
    """FR-045's artifact. Every field it names, and no comparison.

    Constructed by `report()` rather than by hand; `__post_init__` re-checks
    the totals so a document that lost a record cannot be built at all.
    """

    deployment_id: str
    tenant_id: str
    window: ReportingWindow
    interval_closed: bool
    #: SC-019: *"a bare percentage does not satisfy this"*. The total is here
    #: so a reader can recompute the share instead of accepting it.
    total_results: int
    not_verifiable_total: int
    #: Total over `RefusalReason`. Every member present, zeroes included.
    by_reason: Mapping[RefusalReason, int]
    #: Total over `UNATTRIBUTED`. Same discipline.
    by_unattributed: Mapping[str, int]

    def __post_init__(self) -> None:
        _check_totals(self)

    @property
    def share(self) -> float | None:
        """The not-verifiable share, or `None` when there is no share.

        `None` over an empty window rather than `0.0`. A window in which
        nothing was reported has no share; reporting zero would make an idle
        deployment and a flawless one indistinguishable, and the second is a
        claim.
        """
        if self.total_results == 0:
            return None
        return self.not_verifiable_total / self.total_results

    @property
    def share_absent_because(self) -> str | None:
        if self.total_results:
            return None
        return (
            "No result was reported in this interval, so there is no "
            "population to take a share of. Reported as an absence rather "
            "than as 0.0: a share of zero is a statement that results arrived "
            "and none was unverifiable, which is not what happened here."
        )

    def document(self) -> dict[str, Any]:
        """The machine-readable form. Every key FR-045 names.

        Enum members are rendered by `.value` so the document is JSON without
        a custom encoder, and the reasons are sorted so two reports over
        different traffic diff cleanly.
        """
        return {
            "schema_version": SCHEMA_VERSION,
            "deployment_id": self.deployment_id,
            "tenant_id": self.tenant_id,
            "interval": interval_document(
                self.window, closed=self.interval_closed,
            ),
            "total_results": self.total_results,
            "not_verifiable_total": self.not_verifiable_total,
            "share": self.share,
            "share_absent_because": self.share_absent_because,
            "by_refusal_reason": {
                reason.value: self.by_reason[reason]
                for reason in sorted(RefusalReason, key=lambda r: r.value)
            },
            "by_unattributed": {
                key: self.by_unattributed[key] for key in sorted(UNATTRIBUTED)
            },
            "unattributed_reasons": dict(sorted(UNATTRIBUTED.items())),
            "threshold_applied": None,
            "threshold_absent_because": NO_THRESHOLD,
        }


def _check_totals(report: NotVerifiableReport) -> None:
    """The two breakdowns are each total, and together they account for the state.

    Three separate ways a record can vanish, and each has cost somebody a
    reading somewhere: a reason key silently missing, a count that does not add
    up, and a not-verifiable total larger than the population it is a share of.
    """
    missing = set(RefusalReason) - set(report.by_reason)
    if missing:
        raise ReportInputError(
            f"the breakdown omits {sorted(r.value for r in missing)}. Every "
            "member of the named set appears, zeroes included: an omitted key "
            "and a key nothing can produce are indistinguishable to a reader."
        )
    missing_unattributed = set(UNATTRIBUTED) - set(report.by_unattributed)
    if missing_unattributed:
        raise ReportInputError(
            f"the unattributed breakdown omits {sorted(missing_unattributed)}"
        )
    counted = sum(report.by_reason.values()) + sum(report.by_unattributed.values())
    if counted != report.not_verifiable_total:
        raise ReportInputError(
            f"the breakdowns account for {counted} results and the "
            f"not-verifiable total is {report.not_verifiable_total}. A record "
            "that falls between the two moves the share of every reason that "
            "did get counted."
        )
    if report.not_verifiable_total > report.total_results:
        raise ReportInputError(
            f"{report.not_verifiable_total} not-verifiable results in a "
            f"population of {report.total_results}"
        )


def report(
    outcomes: Iterable[ReportedOutcome],
    *,
    window: ReportingWindow,
    deployment_id: str,
    tenant_id: str,
    now: float,
) -> NotVerifiableReport:
    """Count one window's outcomes into FR-045's document.

    `deployment_id` and `tenant_id` are required rather than optional: FR-035's
    two scope columns are what make one deployment's share not another's, and a
    report that omits them is a number without an owner.
    """
    if not deployment_id or not tenant_id:
        raise ReportInputError(
            "a report carries FR-035's two scope columns. Without them the "
            "share belongs to no deployment and no tenant, and two reports "
            "from different ones are indistinguishable."
        )

    records: Sequence[ReportedOutcome] = tuple(outcomes)
    by_reason: dict[RefusalReason, int] = {reason: 0 for reason in RefusalReason}
    by_unattributed: dict[str, int] = {key: 0 for key in UNATTRIBUTED}
    not_verifiable = 0

    for record in records:
        if record.state is not ReportedState.NOT_VERIFIABLE:
            continue
        not_verifiable += 1
        if record.refusal_reason is not None:
            by_reason[record.refusal_reason] += 1
        else:
            # `__post_init__` has already refused a record carrying neither,
            # so this branch is total rather than a fallback.
            by_unattributed[str(record.unattributed)] += 1

    return NotVerifiableReport(
        deployment_id=deployment_id,
        tenant_id=tenant_id,
        window=window,
        interval_closed=window.has_closed(now),
        total_results=len(records),
        not_verifiable_total=not_verifiable,
        by_reason=by_reason,
        by_unattributed=by_unattributed,
    )


def module_source() -> str:
    """This module's own text, for the arm that reads it for a comparison.

    A function rather than a path the test reconstructs: a test that guesses
    the file location silently stops reading anything when the module moves,
    and an arm that reads nothing finds no threshold in it.

    **`inspect.getmodule` returns `ModuleType | None`, and the `None` is
    refused here rather than passed on.** It is the same vacuity one step
    earlier: handed `None`, `getsource` raises `TypeError: ... got NoneType`,
    which names the argument's type and not the module that went missing, and
    any handling that turned it into `""` would leave the caller searching
    empty text for a threshold and finding none. The caller is
    `test_the_share_is_never_compared_against_anything`, whose whole result is
    that search coming back empty — so an empty read is indistinguishable from
    a clean one. Loud, and naming what could not be located.
    """
    module = inspect.getmodule(report)
    if module is None:
        raise ModuleTextUnavailable(
            "inspect.getmodule() could not locate the module defining "
            "report(), so this module's own text cannot be read. Refused "
            "rather than returned empty: the arm that calls this searches "
            "the text for a threshold comparison and reports finding none, "
            "and text that was never read finds none either."
        )
    return inspect.getsource(module)
