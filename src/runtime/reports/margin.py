"""T177 — FR-040's gate report, three branches intact, SC-013 gated on labels.

**Requirement**: FR-040. **Criterion**: SC-013. **Boundary**: FR-052.

The report is the verifier's marginal detection over the shadow judge,
with the pre-registered gate applied unchanged:

* a margin at or above ten percentage points makes the verifier a
  headline capability;
* a smaller margin makes it an internal detail;
* a judge whose discrimination is no better than chance triggers a
  constitutional prohibition on model judges in the success path,
  independently of what the verifier scored.

## What this module will not do

**1. It will not invent a human label.** `human_label` is a human row.
The verifier's verdict cannot supply ground truth (circularity). A
model cannot supply it (the substitution FR-052 exists to prevent).
If no human has labelled, the input is empty, the three branches stay
present and unevaluated, and SC-013's window does not open.

**2. It will not open SC-013's window over an empty table.** The
precondition is that the window opens only once labelling capacity
exists. An empty `human_label` table is not labelling capacity. The
corpus records that the one adjudication pass this needed was never
performed and that a model stood in; that sentence is carried on every
document rather than closed by a fabricated row.

**3. It will not change `Result`, a gate, or the loop.** This module
reads measurement rows it is handed. It does not import
`src.contracts.result`, `src.runtime.loop`, `src.runtime.serving`, or
the judge package. It is not a success-path reader of `human_label`:
the ownership map's empty reader set is unread.

## The historical pass

The frozen-oracle-negatives adjudication was never performed. A model
stood in. That is a fact about the corpus, not about this deployment's
table, and it is stated on every document so a green margin cannot be
read as closing it.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

SCHEMA_VERSION = "1.0.0"

#: Pre-registered. FR-040 applies this number unchanged. Changing it
#: here is changing the gate, not reporting against it.
MARGIN_THRESHOLD_PP = 10.0

BRANCH_HEADLINE = "headline"
BRANCH_INTERNAL = "internal"
BRANCH_CHANCE = "chance"
BRANCHES: tuple[str, ...] = (BRANCH_HEADLINE, BRANCH_INTERNAL, BRANCH_CHANCE)

BRANCH_MEANINGS: Mapping[str, str] = {
    BRANCH_HEADLINE: (
        "a margin at or above ten percentage points makes the verifier "
        "a headline capability"
    ),
    BRANCH_INTERNAL: (
        "a smaller margin makes the verifier an internal detail"
    ),
    BRANCH_CHANCE: (
        "a judge whose discrimination is no better than chance triggers "
        "a constitutional prohibition on model judges in the success "
        "path, independently of what the verifier scored"
    ),
}

HISTORICAL_PASS_NEVER_PERFORMED = (
    "The one human adjudication pass this needed was never performed. "
    "A model stood in. Recorded rather than closed: inventing labels "
    "here would be the substitution FR-052 exists to prevent, and "
    "using the verifier's verdict as ground truth would be circular."
)

SC013_WINDOW_PRECONDITION = (
    "SC-013's thirty-day window opens only once labelling capacity "
    "exists. An empty human_label table is not labelling capacity."
)

CHANCE_RATE = 0.5


class MarginInputError(ValueError):
    """A row or a join this report will not compute over."""


class ModuleTextUnavailable(RuntimeError):
    """This module's own text could not be located for the arm that reads it."""


@dataclass(frozen=True)
class LabelRow:
    """One `human_label` row, as the report is handed it.

    Constructed by a caller that already read the table. This module
    does not invent one from a verifier label or a judge verdict.
    """

    result_id: str
    adjudicator: str
    label: str
    at: float


@dataclass(frozen=True)
class VerdictRow:
    """One `judge_verdict` row, as the report is handed it."""

    result_id: str
    verdict: str


@dataclass(frozen=True)
class VerifierRow:
    """The verifier's label for one result, as the report is handed it."""

    result_id: str
    label: str


@dataclass(frozen=True)
class MarginReport:
    """FR-040's artifact. All three branches present; applied only with labels."""

    deployment_id: str
    tenant_id: str
    labelled_count: int
    window_open: bool
    applied_branch: str | None
    margin_pp: float | None
    judge_discrimination: float | None
    historical_pass: str
    sc013_precondition: str

    def document(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "deployment_id": self.deployment_id,
            "tenant_id": self.tenant_id,
            "labelled_count": self.labelled_count,
            "sc013_window_open": self.window_open,
            "applied_branch": self.applied_branch,
            "margin_pp": self.margin_pp,
            "judge_discrimination": self.judge_discrimination,
            "threshold_pp": MARGIN_THRESHOLD_PP,
            "branches": dict(BRANCH_MEANINGS),
            "historical_pass": self.historical_pass,
            "sc013_precondition": self.sc013_precondition,
        }


def report(
    human_labels: Iterable[LabelRow],
    judge_verdicts: Iterable[VerdictRow],
    verifier_calls: Iterable[VerifierRow],
    *,
    deployment_id: str,
    tenant_id: str,
) -> MarginReport:
    """Score the verifier's margin against human labels, or refuse to.

    An empty `human_labels` sequence is the honest production state.
    The other two sequences are then unused for scoring: they are not
    a substitute ground truth. SC-013's window stays closed. The three
    branches stay on the document, unevaluated.
    """
    if not deployment_id or not tenant_id:
        raise MarginInputError(
            "a report carries FR-035's two scope columns. Without them "
            "the margin belongs to no deployment and no tenant."
        )

    labelled: Sequence[LabelRow] = tuple(human_labels)
    if not labelled:
        return MarginReport(
            deployment_id=deployment_id,
            tenant_id=tenant_id,
            labelled_count=0,
            window_open=False,
            applied_branch=None,
            margin_pp=None,
            judge_discrimination=None,
            historical_pass=HISTORICAL_PASS_NEVER_PERFORMED,
            sc013_precondition=SC013_WINDOW_PRECONDITION,
        )

    judges = {row.result_id: row.verdict for row in judge_verdicts}
    verifiers = {row.result_id: row.label for row in verifier_calls}
    verifier_hits = 0
    judge_hits = 0
    for row in labelled:
        if not row.adjudicator:
            raise MarginInputError(
                "a human_label row without an adjudicator is not ground "
                "truth"
            )
        if row.result_id not in judges:
            raise MarginInputError(
                f"{row.result_id!r} is labelled and has no judge verdict"
            )
        if row.result_id not in verifiers:
            raise MarginInputError(
                f"{row.result_id!r} is labelled and has no verifier label"
            )
        if verifiers[row.result_id] == row.label:
            verifier_hits += 1
        if judges[row.result_id] == row.label:
            judge_hits += 1

    n = len(labelled)
    verifier_rate = verifier_hits / n
    judge_rate = judge_hits / n
    margin_pp = (verifier_rate - judge_rate) * 100.0
    judge_discrimination = judge_rate - CHANCE_RATE
    applied = _apply_gate(margin_pp, judge_discrimination)
    return MarginReport(
        deployment_id=deployment_id,
        tenant_id=tenant_id,
        labelled_count=n,
        window_open=True,
        applied_branch=applied,
        margin_pp=margin_pp,
        judge_discrimination=judge_discrimination,
        historical_pass=HISTORICAL_PASS_NEVER_PERFORMED,
        sc013_precondition=SC013_WINDOW_PRECONDITION,
    )


def _apply_gate(margin_pp: float, judge_discrimination: float) -> str:
    """The pre-registered gate, chance first so a large margin cannot hide it."""
    if judge_discrimination <= 0:
        return BRANCH_CHANCE
    if margin_pp >= MARGIN_THRESHOLD_PP:
        return BRANCH_HEADLINE
    return BRANCH_INTERNAL


def module_source() -> str:
    """This module's own text, for the arm that reads it for a substitution."""
    module = inspect.getmodule(report)
    if module is None:
        raise ModuleTextUnavailable(
            "inspect.getmodule() could not locate the module defining "
            "report(), so this module's own text cannot be read. "
            "Refused rather than returned empty: the arm that calls "
            "this searches the text for a label invented from the "
            "verifier or the judge, and text that was never read finds "
            "none either."
        )
    return inspect.getsource(module)
