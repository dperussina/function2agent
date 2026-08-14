"""T176 — operator surface and `human_label` rows.

**Requirement**: FR-040. **Boundary**: FR-052, Principle I.

The queue presents a sampled result with the evidence an adjudicator
needs to judge it, and writes a `human_label` row carrying the
adjudicator and the time. The writer is `ROLE_SHADOW_JUDGE`. The
reader set is empty: a success-path role that could open this table
for read could start treating a label as a verdict.

## What this is, and what it is not

This is a human row. A model-written label is the defect FR-052
names. Reserved stand-in names are refused rather than stored, because
a row that looks like a human label and was written by a model is the
historical substitution the corpus already records.

It is not T214: no run produces a `Result`. The queue takes a
caller-supplied result id — a test, or T214 when it lands — and does
not invent that call site. It does not import `src.contracts.result`.

It does not import the judge. The judge writes `judge_verdict`; this
package writes `human_label`. The margin report joins them as data.

A queue that nobody has labelled leaves the table empty. That emptiness
is the honest production state: the one adjudication pass this needed
was never performed, and inventing a row to close T177 would be the
same substitution.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from typing import Callable

from src.contracts.ownership import ROLE_SHADOW_JUDGE
from src.contracts.repository import Repository
from src.runtime.adjudication.sampling import SamplingRule

TABLE = "human_label"

COLUMNS = {
    "result_id": "text not null",
    "session_id": "text not null",
    "adjudicator": "text not null",
    "label": "text not null",
    "rule_registered_at": "real not null",
    "rule_rate": "real not null",
    "at": "real not null",
}

LABEL_CORRECT = "correct"
LABEL_INCORRECT = "incorrect"
LABELS = frozenset({LABEL_CORRECT, LABEL_INCORRECT})

#: Names that mean a model stood in. A human row carrying one of these
#: is the substitution FR-052 exists to prevent, stored as if it were
#: ground truth.
MODEL_STANDINS = frozenset({"model", "shadow_judge", "judge"})


class AdjudicationError(ValueError):
    """A sample, a view, or a label this queue refuses."""


@dataclass(frozen=True)
class Evidence:
    """What an adjudicator needs to judge one sampled result.

    T214 residual: no run produces a `Result`. The caller supplies the
    id and the evidence; this package does not construct either from a
    `Result`.
    """

    result_id: str
    session_id: str
    verifier_label: str
    presented: str


@dataclass(frozen=True)
class OperatorView:
    """The operator-facing surface for one sampled result.

    `suggested_label` is always `None`. A suggestion would be a model
    standing in; the field exists so the absence is a value, not a
    missing key a later reader fills.
    """

    result_id: str
    session_id: str
    evidence: Evidence
    rule: SamplingRule
    suggested_label: str | None


@dataclass(frozen=True)
class _Sampled:
    evidence: Evidence


class AdjudicationQueue:
    """Samples under a pre-registered rule; writes `human_label`.

    Constructed as `ROLE_SHADOW_JUDGE` or refused. The rule must already
    have been registered before its window; this object does not
    re-register.
    """

    def __init__(
        self,
        repository: Repository,
        rule: SamplingRule,
        *,
        clock: Callable[[], float] | None = None,
    ) -> None:
        if repository.role != ROLE_SHADOW_JUDGE:
            raise AdjudicationError(
                f"{repository.role!r} may not write {TABLE}; its sole "
                f"writer is {ROLE_SHADOW_JUDGE!r}. The empty reader set "
                "on this table is FR-052: a success-path role that could "
                "open it for write could also open it for read."
            )
        self._repo = repository
        self._rule = rule
        self._clock = clock if clock is not None else time.time
        self._sampled: dict[str, _Sampled] = {}
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        self._repo.create_table(
            TABLE, COLUMNS, unique=[("result_id",)],
        )

    def sample(
        self,
        result_id: str,
        session_id: str,
        evidence: Evidence,
        *,
        now: float | None = None,
    ) -> bool:
        """Consider one result under the pre-registered rule.

        Returns whether it was selected. The id is caller-supplied
        (T214 residual). An empty id keys nothing.
        """
        if not result_id:
            raise AdjudicationError(
                "a sample is keyed to a result; an empty id keys nothing"
            )
        if not session_id:
            raise AdjudicationError(
                "a sample belongs to a session or to nothing"
            )
        if evidence.result_id != result_id or evidence.session_id != session_id:
            raise AdjudicationError(
                "the evidence must name the same result and session as "
                "the sample; a mismatch is two items presented as one"
            )
        at = self._clock() if now is None else now
        if at < self._rule.window_starts_at:
            raise AdjudicationError(
                "the sampling window has not opened. A sample taken "
                "before the window is not a sample the rule governs."
            )
        if at >= self._rule.window_ends_at:
            raise AdjudicationError(
                "the sampling window has closed. A sample taken after "
                "the window is not a sample the rule governs."
            )
        if not _selected(result_id, self._rule.rate):
            return False
        self._sampled[result_id] = _Sampled(evidence)
        return True

    def present(self, result_id: str) -> OperatorView:
        """The operator surface: the sampled result and its evidence.

        `suggested_label` is `None`. Filling it from the verifier or
        from a model is the circularity / FR-052 substitution.
        """
        item = self._sampled.get(result_id)
        if item is None:
            raise AdjudicationError(
                f"{result_id!r} was not sampled; the surface presents "
                "a selected result, not an arbitrary one"
            )
        return OperatorView(
            result_id=result_id,
            session_id=item.evidence.session_id,
            evidence=item.evidence,
            rule=self._rule,
            suggested_label=None,
        )

    def label(self, result_id: str, adjudicator: str, label: str) -> None:
        """Write one `human_label` row. The time is this object's clock.

        The adjudicator is a human. An empty name or a reserved stand-in
        is refused: those are how a model-written label arrives looking
        like ground truth.
        """
        if not result_id:
            raise AdjudicationError(
                "a label is keyed to a result; an empty id keys nothing"
            )
        if not adjudicator:
            raise AdjudicationError(
                "a human_label row carries the adjudicator. An empty "
                "name is not a human and is how a model-written label "
                "arrives without saying so."
            )
        if adjudicator in MODEL_STANDINS:
            raise AdjudicationError(
                f"{adjudicator!r} is a reserved stand-in, not an "
                "adjudicator. A model-written label is the defect "
                "FR-052 names."
            )
        if label not in LABELS:
            raise AdjudicationError(
                f"{label!r} is not a human label ({sorted(LABELS)}). "
                "The queue's vocabulary is not VerificationOutcome."
            )
        item = self._sampled.get(result_id)
        if item is None:
            raise AdjudicationError(
                f"{result_id!r} was not sampled; a label on an "
                "unsampled result is not a label the rule selected"
            )
        self._repo.insert(TABLE, {
            "result_id": result_id,
            "session_id": item.evidence.session_id,
            "adjudicator": adjudicator,
            "label": label,
            "rule_registered_at": self._rule.registered_at,
            "rule_rate": self._rule.rate,
            "at": self._clock(),
        })

    def labels(self) -> list[dict[str, object]]:
        """Rows this writer persisted. The writer may read its own table."""
        rows = self._repo.select(TABLE, order_by="at")
        return [dict(row) for row in rows]


def _selected(result_id: str, rate: float) -> bool:
    """Deterministic draw in [0, 1) against the pre-registered rate."""
    digest = hashlib.sha256(result_id.encode("utf-8")).digest()
    bucket = int.from_bytes(digest[:4], "big") / 2**32
    return bucket < rate
