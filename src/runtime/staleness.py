"""T147–T152 — the stale last-known-good set, its ceiling, and recovery.

**Requirement**: FR-047, authorised by **OD-21**. An admitted target whose
published specification later becomes non-admissible MUST continue on the
last-known-good served-operation set **marked stale**, and MUST deny once a
staleness ceiling measured from the last successful fetch is crossed.

## What this module consumes rather than restates

- **T141** `CheckResult` / `Scheduler.tick`. A non-admissible tick returns
  `FailedRefetch` and does not update last-known-good or the timestamp the
  ceiling is measured from. This module is a state machine over those check
  results. It does not re-fetch. It does not duplicate the Plane A peer check.
- **T140** `FailedRefetch`. No `version_after` attribute. The primitive is the
  timestamp of the last successful fetch; age is derived at the moment someone
  asks. `StaleSet.age_seconds(now)` delegates to that record so the drift
  signal and the caller-visible marking cannot state two different ages.
- **T128** `Result.staleness` / `Staleness` / `StaleMarking`. T148 is the
  **producer** that stamps those fields. There is no second Staleness type.
  `dataclasses.replace` rebuilds the frozen Result; this module does not
  construct one, because `tests/invariants/test_result_constructor.py` keeps
  `Result(` under `src/runtime/` at the T213 seam alone.
- **T137** `compare` + **T139** `signals_from_movements`. A below-ceiling
  restore that changed is deployment-clock drift. `compare_each` is not
  called: it requires both clocks, and inventing a source reading so we
  could call it would be the fused artifact T137 made unconstructible.
- **T073** `admission.check` then **T079** `inspect_admission`. Past-ceiling
  recovery is the full admission sequence, not `tick` alone.

T145 (`backstop.py`), T146 (`disable.py`) and T153 (`reinspect.py`) are not
this module. New operations in a restored set that were not in the last
inspected set are T153's inspect-before-available; T151 evaluates the
difference as drift and stops there.

## The entering-stale domain, and the residual against FR-047's "three"

FR-047's entering clause says *"any of FR-044's three non-admissible states"*.
FR-031's narrowing says the failed-re-fetch state is *"named from FR-044's
four-state classification"*. The classifier reports six (`admission.STATES`);
`FR_044_STATES` is four; `FailedRefetch.SPECIFICATION_STATE_FOUND` is five
(STATES minus admissible). `spec_withdrawn.non_admissible_states_exercised()`
is scoped to FR-044's three and **excludes `unreachable`**.

T140 left this module the disposition of whether `unreachable` (and
`unparseable`) enter the stale state on the same rule as `absent`. The
corpus-as-falsification reading T140 used holds here too, and for a reason
that is about the observation channel rather than about the fixture:

A transport blip (`unreachable`) is indistinguishable, from this side of
FR-046's check, from a specification that has been withdrawn. That
indistinguishability is why FR-047 exists — continue on last-known-good
marked stale, rather than read the failure as a deployment that serves
nothing, and bound the risk with a wall-clock ceiling. Excluding
`unreachable` would make T157's `withdraw-past-ceiling` — whose later
fetches are `unreachable` and whose calls carry
`specification_state_last_found: "unreachable"` — unable to *stay* in a
state the corpus already declares stale, and would make a first-fetch
`unreachable` unable to enter it at all. Folding the blip into "not stale"
would be the other candidate FR-047 rejected: deny (or ignore) on the first
failed re-fetch, wearing a narrower trigger set.

`unparseable` is the same observation-channel failure one step further along:
the origin answered and the bytes are not a specification this system can
read. Holding the last-known-good set as if the published surface were still
the one that admitted the target would be an unfounded belief, which is the
state FR-047 marks rather than discards.

So `ENTERING_STATES` is `SPECIFICATION_STATE_FOUND` — five, subtracted from
the classifier rather than written out. **Residual, named rather than
closed**: FR-047's own sentence still says three. Ruling the sentence wrong
is an owner act; this module does not amend `spec.md`.

## The ceiling is wall-clock from the last successful fetch

Age is `now - last successful fetch`, not from the moment stale was entered,
not from a count of failed ticks. Lengthening `DRIFT_CHECK_INTERVAL_SECONDS`
cannot silently widen it, because this module does not read the interval.
`now` is an argument, as `Scheduler.tick(now=)` already is. The clock is not
read here.

**Crossed** is `age > ceiling`, matching `ServedOperationSet.is_stale` and
FR-047's "once the ceiling is crossed". At exactly the ceiling the set is
still served, marked stale. T157 plants no call at 900 s; this module is
where that boundary is stated.

**The configured default is 900 seconds (fifteen minutes), not 3600.**
FR-047 states fifteen minutes; the T157 corpus is 900; the declared key
default at the start of this slice was `"3600.0"`, which would serve four
times past the requirement's ceiling. 3600 had no other authority — it is
not a measurement, not a corpus figure, and `unvalidated.py`'s provenance
already says "FR-047's stated default". The key default moves to `"900.0"`
with this slice. Tests may still pass an explicit 900; they no longer have
to, to get the requirement's number.

The ceiling is a configured default marked unvalidated under FR-043, and is
recorded with the deployment identity it applies to.

## T150–T152 are functions. There is no serve loop.

OD-36 still holds: `Registry` constructed nowhere; `src/runtime/main.py`
still report+exit. `loop.py`, `runner.py`, `serving.py` and `main.py` were
checked and do not call this module. A comment claiming every result is
marked was not added to `result_join.py`: that seam is T213's verification
join, and T148 is `mark_result` here.

Past the ceiling: `deny_call` names the stale set and its age as the rule
(FR-011); `in_flight_terminal` returns `terminated.staleness_ceiling_reached`
rather than `terminated.unrecoverable_fault` (that member's own text says
reaching it is a defect report) and rather than a `BackstopTripped`-style
exception. Crossing is not terminal for the **runtime**; recovery does not
require an operator restart. It does require the full admission sequence.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Mapping

from src.analysis.admission import AdmissionDecision, FetchResponse
from src.analysis.admission import check as admission_check
from src.analysis.clocks import DEPLOYMENT, Reading, compare
from src.analysis.deputy_inspection import (
    Codebase,
    InspectionReport,
    inspect_admission,
)
from src.analysis.drift_signal import (
    SPECIFICATION_STATE_FOUND,
    DriftSignal,
    FailedRefetch,
    signals_from_movements,
)
from src.contracts import terminal
from src.contracts.result import Result, StaleMarking, Staleness
from src.contracts.transition import ST_STALENESS_CEILING
from src.runtime.drift.scheduler import CheckResult

#: FR-047's stated default, fifteen minutes, as seconds. The key
#: `STALENESS_CEILING_SECONDS` ships the same number, marked unvalidated.
DEFAULT_CEILING_SECONDS = 900.0

#: T147's entering domain: every state a failed re-fetch can have found.
#: Five members where FR-047's sentence says three — see the module docstring.
ENTERING_STATES: frozenset[str] = SPECIFICATION_STATE_FOUND

#: FR-011's rule identifier on a ceiling denial. The transition rule that
#: attributes the in-flight terminal state is the same identity, so a denial
#: and a session ending at the ceiling cannot name two different rules.
CEILING_DENIAL_RULE = ST_STALENESS_CEILING.rule_id


class StalenessError(RuntimeError):
    """A staleness transition that would state something untrue about the set."""


@dataclass(frozen=True)
class Ceiling:
    """FR-047's ceiling, recorded with the deployment it applies to.

    `seconds` is a configured default, not a measurement. `unvalidated` is
    the FR-043 marking; a ceiling that travelled externally without it would
    present an unmeasured number as if it had been chosen against evidence.
    """

    seconds: float
    deployment_id: str
    unvalidated: bool = True

    def __post_init__(self) -> None:
        if self.seconds <= 0:
            raise StalenessError(
                f"ceiling_seconds={self.seconds!r} is not a positive duration. "
                "FR-047's default is a configured number marked unvalidated; "
                "a non-positive value is not that number and is not a "
                "measurement of anything."
            )
        if not self.deployment_id:
            raise StalenessError(
                "a staleness ceiling was bound to no deployment. FR-047 "
                "requires the ceiling recorded with the deployment identity "
                "it applies to, exactly as FR-046 requires of its interval."
            )


def crossed(age_seconds: float, ceiling_seconds: float) -> bool:
    """Whether the wall-clock age has gone **past** the ceiling.

    `>` and not `>=`, matching `ServedOperationSet.is_stale` and FR-047's
    *"once the ceiling is crossed"*. At exactly the ceiling the set is still
    a last-known-good belief, marked stale. A non-positive ceiling is a
    refusal, not "everything is past" — that reading would make a
    misconfigured ceiling deny every call and look like the mechanism working.
    """
    if ceiling_seconds <= 0:
        raise StalenessError(
            f"ceiling_seconds={ceiling_seconds!r} is not a positive duration. "
            "FR-047's default is a configured number marked unvalidated; a "
            "non-positive value is not that number."
        )
    return age_seconds > ceiling_seconds


@dataclass(frozen=True)
class StaleSet:
    """The last-known-good set, marked stale rather than discarded (T147).

    The instant is `entering_signal.last_successful_fetch`. Age is derived
    from that instant at the moment a caller asks; it is not stored, because
    a stored age is a number wrong immediately after it is written. T148's
    `Staleness.age_seconds` on a Result is a snapshot at result-production
    time, derived here at stamp time from the same instant.
    """

    last_successful: Reading
    entering_signal: FailedRefetch
    specification_state: str
    ceiling: Ceiling

    def __post_init__(self) -> None:
        if self.last_successful.clock != DEPLOYMENT:
            raise StalenessError(
                f"a stale set was built from a {self.last_successful.clock}-clock "
                "reading. FR-047 continues to resolve against the last-known-good "
                "**served-operation** set; a source reading here would mark a "
                "source-derived version stale, which is the two clocks back in "
                "one field."
            )
        if self.entering_signal.specification_state not in ENTERING_STATES:
            raise StalenessError(
                f"{self.entering_signal.specification_state!r} is not a state "
                "that enters stale. ENTERING_STATES is SPECIFICATION_STATE_FOUND "
                "(the classifier minus admissible); a successful fetch recorded "
                "here would mark a set stale on the evidence that an artifact "
                "was obtained."
            )
        if self.specification_state not in ENTERING_STATES:
            raise StalenessError(
                f"{self.specification_state!r} is not a specification state "
                "a failed re-fetch can have found."
            )
        if self.ceiling.deployment_id != self.last_successful.deployment_id:
            raise StalenessError(
                f"a stale set of {self.last_successful.deployment_id!r} carries "
                f"a ceiling bound to {self.ceiling.deployment_id!r}. FR-047 "
                "records the ceiling with the deployment it applies to; mixing "
                "two identities applies one target's allowance to the other."
            )

    @property
    def last_successful_fetch(self) -> str:
        """The instant the ceiling is measured from. Not the moment of entry."""
        return self.entering_signal.last_successful_fetch

    @property
    def deployment_id(self) -> str:
        return self.last_successful.deployment_id

    def age_seconds(self, now: float) -> float:
        """Seconds since the last successful fetch, at `now`.

        Delegates to `FailedRefetch.age_seconds` so the drift signal raised
        on the entering run and the caller-visible marking cannot disagree.
        `now` has no default.
        """
        return self.entering_signal.age_seconds(now)


@dataclass(frozen=True)
class Restore:
    """T151 — left stale below the ceiling. Marking cleared; difference evaluated.

    `signals` is empty when the restored set is identical to last-known-good.
    That zero is the negative control: a detector that reports drift on every
    restoration fails T157's `withdraw-restore-identical-below-ceiling`.
    """

    last_successful: Reading
    last_successful_fetch: str
    signals: tuple[DriftSignal, ...]


@dataclass(frozen=True)
class CeilingDenial:
    """T150 — a call refused because the ceiling was crossed (FR-030, FR-011).

    Below the ceiling FR-030 has no member to disable: the observation channel
    failed, no operation was observed. At the ceiling every operation is
    affected. T146 is disable-the-affected-operation for *observed* drift and
    is not this record.
    """

    rule_id: str
    deployment_id: str
    set_version: str
    age_seconds: float
    specification_state: str
    operation_id: str
    ceiling_seconds: float
    ceiling_unvalidated: bool

    def __post_init__(self) -> None:
        if not self.rule_id:
            raise StalenessError(
                "a ceiling denial was built with no rule identifier. FR-011 "
                "makes the rule part of the record; a denial that cannot name "
                "the stale set and its age as the rule that produced it is "
                "the generic error FR-006 forbids wearing a structured shape."
            )


@dataclass(frozen=True)
class Recovery:
    """T152 — past-ceiling admission, not a tick.

    `inspection` is None when FR-044 rejected: T079 refuses a rejected
    decision because there is no operation list to inspect. Recording that
    rejection is the admission decision the sequence produced. `recovered`
    is true only when FR-044 admitted and FR-020 ran.
    """

    decision: AdmissionDecision
    inspection: InspectionReport | None
    recovered: bool


def _failed_refetch_of(check: CheckResult) -> FailedRefetch | None:
    failed = tuple(s for s in check.signals if isinstance(s, FailedRefetch))
    if len(failed) > 1:
        raise StalenessError(
            f"a check of {check.deployment_id!r} produced {len(failed)} failed "
            "re-fetches. One tick classifies one fetch; two failures on one "
            "result are two findings nobody can attribute."
        )
    return failed[0] if failed else None


def enter(check: CheckResult, *, ceiling: Ceiling) -> StaleSet:
    """T147 — mark the set stale on the first non-admissible re-fetch.

    The drift signal is the `FailedRefetch` `tick` already produced. This
    does not replace it with a product-type optional field. Last-known-good
    is kept, not discarded.
    """
    signal = _failed_refetch_of(check)
    if signal is None:
        raise StalenessError(
            f"a check of {check.deployment_id!r} found no failed re-fetch, "
            "so there is no non-admissible state to enter stale on. An "
            "admissible fetch is compared under FR-027; if it moved, that "
            "is ArtifactDrift, not this."
        )
    if signal.specification_state not in ENTERING_STATES:
        raise StalenessError(
            f"{signal.specification_state!r} does not enter the stale state. "
            "ENTERING_STATES is the classifier minus admissible."
        )
    if check.last_successful_fetch != signal.last_successful_fetch:
        raise StalenessError(
            "the check's last-successful-fetch instant disagrees with the "
            "FailedRefetch it raised. FR-047's ceiling is measured from that "
            "instant; two values here are two ages."
        )
    return StaleSet(
        last_successful=check.last_successful,
        entering_signal=signal,
        specification_state=signal.specification_state,
        ceiling=ceiling,
    )


def observe(
    state: StaleSet | None,
    check: CheckResult,
    *,
    now: float,
    ceiling: Ceiling,
) -> StaleSet | Restore | None:
    """The state machine over one `CheckResult`. Not a second scheduler.

    `now` is the instant the caller is asking about (epoch seconds). The
    interval is not an argument, so lengthening it cannot widen the ceiling.
    """
    signal = _failed_refetch_of(check)
    if signal is not None:
        if state is None:
            return enter(check, ceiling=ceiling)
        return StaleSet(
            last_successful=state.last_successful,
            entering_signal=state.entering_signal,
            specification_state=signal.specification_state,
            ceiling=state.ceiling,
        )
    if state is None:
        return None
    if crossed(state.age_seconds(now), ceiling.seconds):
        raise StalenessError(
            f"{state.deployment_id}: the ceiling is crossed "
            f"(age {state.age_seconds(now)} s, ceiling {ceiling.seconds} s). "
            "Past the ceiling the system holds no founded belief about what "
            "the deployment serves; leaving stale is recover() running the "
            "full admission sequence, not tick's re-fetch alone."
        )
    return restore(state, check, now=now, ceiling=ceiling)


def mark_result(
    result: Result,
    state: StaleSet | None,
    *,
    now: float,
    ceiling: Ceiling,
) -> Result:
    """T148 — stamp FR-047's three facts onto a caller-visible result.

    A separate field, not a fourth verification value. A result may be
    verified and stale at once. `state is None` leaves the result as it
    stood — `NOT_STATED`, which makes no claim. Stamping `FRESH` on silence
    would be the boolean defect T128 removed.

    Past the ceiling this refuses rather than marking: the last-known-good
    set must not be served, and a stamped Result would be serving it.
    """
    if state is None:
        return result
    age = state.age_seconds(now)
    if crossed(age, ceiling.seconds):
        raise StalenessError(
            f"{state.deployment_id}: age {age} s is past the ceiling "
            f"({ceiling.seconds} s). FR-047 forbids serving the last-known-good "
            "set once the ceiling is crossed; mark_result would be that "
            "serving, wearing a stale flag."
        )
    return replace(
        result,
        staleness=Staleness(
            StaleMarking.STALE,
            age_seconds=age,
            specification_state=state.specification_state,
        ),
    )


def may_serve(
    state: StaleSet | None, *, now: float, ceiling: Ceiling
) -> bool:
    """Whether a call against this set may still be resolved (FR-010).

    Fresh (no stale state): yes. Stale below the ceiling: yes, that is the
    risk FR-047 accepts. Past the ceiling: no.
    """
    if state is None:
        return True
    return not crossed(state.age_seconds(now), ceiling.seconds)


def deny_call(
    state: StaleSet,
    *,
    now: float,
    ceiling: Ceiling,
    operation_id: str,
) -> CeilingDenial:
    """T150 — deny every call past the ceiling, naming the set and its age.

    Refuses below the ceiling: FR-030 has no member to disable while the
    observation channel has merely failed. That case is T148's marking.
    """
    age = state.age_seconds(now)
    if not crossed(age, ceiling.seconds):
        raise StalenessError(
            f"{state.deployment_id}: age {age} s is not past the ceiling "
            f"({ceiling.seconds} s). Below the ceiling FR-030 has no member "
            "to disable — the observation channel failed, no operation was "
            "observed — and FR-047 marks the set instead of denying the call."
        )
    if not operation_id:
        raise StalenessError(
            "a ceiling denial names no operation. FR-011's denial has to say "
            "what was refused; an empty operation id is a generic error."
        )
    return CeilingDenial(
        rule_id=CEILING_DENIAL_RULE,
        deployment_id=state.deployment_id,
        set_version=state.last_successful.version,
        age_seconds=age,
        specification_state=state.specification_state,
        operation_id=operation_id,
        ceiling_seconds=ceiling.seconds,
        ceiling_unvalidated=ceiling.unvalidated,
    )


def in_flight_terminal(
    state: StaleSet, *, now: float, ceiling: Ceiling
) -> terminal.TerminalState:
    """T150 — the named terminal state an in-flight session ends in.

    Not `terminated.unrecoverable_fault`: that member's own text says reaching
    it is a defect report. Not a generic error. Distinct from FR-005's four
    so an operator can tell this ceiling from spend, tokens, wall clock, or
    turns.
    """
    age = state.age_seconds(now)
    if not crossed(age, ceiling.seconds):
        raise StalenessError(
            f"{state.deployment_id}: age {age} s is not past the ceiling "
            f"({ceiling.seconds} s). An in-flight session below the ceiling "
            "is still resolved against the stale set; terminating it here "
            "would be the first-failed-re-fetch candidate OD-21 rejected."
        )
    return terminal.STALENESS_CEILING


def restore(
    state: StaleSet,
    check: CheckResult,
    *,
    now: float,
    ceiling: Ceiling,
) -> Restore:
    """T151 — replace last-known-good, clear the marking, evaluate as drift.

    A re-fetch that merely succeeds is not evidence that nothing changed.
    Identical restoration produces zero signals (T157's negative control).
    Refuses past the ceiling: that path is `recover()`, admission not tick.
    Does not inspect new operations before they become available — T153.
    """
    if _failed_refetch_of(check) is not None:
        raise StalenessError(
            f"{state.deployment_id}: restore was given a failed re-fetch. "
            "Leaving stale below the ceiling requires a published, readable, "
            "non-empty specification."
        )
    if crossed(state.age_seconds(now), ceiling.seconds):
        raise StalenessError(
            f"{state.deployment_id}: the ceiling is crossed. Recovery past "
            "it runs admission.check then inspect_admission, not tick."
        )
    movement = compare(state.last_successful, check.last_successful)
    return Restore(
        last_successful=check.last_successful,
        last_successful_fetch=check.last_successful_fetch,
        signals=signals_from_movements((movement,)),
    )


def recover(
    state: StaleSet,
    response: FetchResponse,
    *,
    now: float,
    ceiling: Ceiling,
    handler_index: Mapping[str, str],
    codebase: Codebase,
) -> Recovery:
    """T152 — full admission sequence, no operator restart.

    FR-044 (`admission.check`) then FR-020 (`inspect_admission`). A tick is
    not this. Below the ceiling this refuses: that path is `restore()`.
    """
    if not crossed(state.age_seconds(now), ceiling.seconds):
        raise StalenessError(
            f"{state.deployment_id}: age {state.age_seconds(now)} s is below "
            f"the ceiling ({ceiling.seconds} s). Below the ceiling a "
            "successful re-fetch is restore() — replace last-known-good, "
            "clear the marking, evaluate the difference as drift. Recovery "
            "past the ceiling is admission, because the system holds no "
            "founded belief about what the deployment serves."
        )
    decision = admission_check(
        response, deployment_id=state.deployment_id
    )
    if not decision.admitted:
        return Recovery(decision=decision, inspection=None, recovered=False)
    inspection = inspect_admission(
        decision, handler_index=handler_index, codebase=codebase
    )
    return Recovery(decision=decision, inspection=inspection, recovered=True)
