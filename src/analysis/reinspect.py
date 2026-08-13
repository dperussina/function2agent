"""T153 — FR-051's ordinary successful-fetch increment.

**Requirement**: FR-051. Every operation that becomes available MUST have been
inspected under FR-020 first, whichever fetch introduced it. FR-020 runs at
admission; FR-046 re-fetches on a schedule; an admission-only reading leaves
an operation added between two successful fetches reachable uninspected.

On every successful fetch this module compares the newly fetched set against
the last **inspected** set, inspects every operation present in the first and
absent from the second **before** it becomes available, and fails closed on
any it cannot inspect, exactly as FR-020 does at admission.

## What this module consumes rather than restates

- **T073** `admission.check` / `ADMISSIBLE_STATES`. T153 runs on a successful
  fetch (`published_non_empty`). A failed re-fetch is T140/T147. The check
  here refuses a non-admissible decision rather than inspecting an empty or
  invented list.
- **T079** `inspect_operation`, `ALLOWED_OUTCOMES`, `InspectionReport`,
  `gate`. FR-056 already names the three-step procedure; this module does
  not reimplement it. Availability is `InspectionReport.available` — the
  `clean` set and only the `clean` set — and is not given a second name.
- **Not** `inspect_admission`. That is the second admission stage over the
  **full** admitted list (T079 at admission, T152 past the ceiling). This
  is the incremental path: only operations present in the new fetch and
  absent from the last inspected (clean) set.
- **Not** T151 `restore`. Restore evaluates set-difference as **drift**.
  This inspects **new operations** before they become available. Different
  subjects. `compare` / `compare_each` / `signals_from_movements` are not
  called.
- **Not** T152 `recover`. Past-ceiling recovery is admission; this is the
  ordinary successful-fetch increment against a target that never stopped
  publishing — the path FR-051 says this module exists for. FR-047's
  leaving-stale comparison is this requirement's special case and is
  unchanged by it.

## The last inspected set is the clean set

FR-051, given a procedure by FR-056: the last inspected set is **the set of
operations whose recorded outcome is `clean`**. That is
`InspectionReport.available`. An operation previously found `uninspectable`
is not in that set, so a later fetch that still lists it is a newly
appearing operation and is inspected again. It is not treated as already
inspected, and it is not silently re-admitted: availability still requires
`clean`. Carrying the prior denial without re-running the procedure would
also refuse silent re-admission; re-running is the reading that follows
from last-inspected = clean set. T158 plants no scenario that forces the
choice.

## The inspected-set key is the operation identifier

`OperationOutcome` records `operation_id`, `outcome`, `step`, `reason` and
`call_sites`. It does not record the handler symbol as a field. FR-051 says
an operation whose **handler** changed is not treated as inspected merely
because its specification entry did not. There is nothing on the recorded
outcome to detect that, and this module does not invent a second inspection
identity to paper over it. Residual, named rather than closed.

## The unit of failing closed is the operation

A denied sibling does not retract a clean one, and does not take the target
offline. Both `deputy` and `uninspectable` are denied via
`ALLOWED_OUTCOMES` (one member: `clean`), distinguished so the reason is
reportable. `gate` remains T079's: a caller that wants to refuse a named
operation raises rather than returning a boolean.

## Analysis does not fetch

No HTTP client, no target credential, no Plane A/B, no clock. The fetch
has already succeeded; this module is handed the admitted decision.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from src.analysis.admission import ADMISSIBLE_STATES, AdmissionDecision
from src.analysis.deputy_inspection import (
    ALLOWED_OUTCOMES,
    CLEAN,
    Codebase,
    DeputyInspectionError,
    InspectionReport,
    NotAdmittedForInspection,
    OperationOutcome,
    inspect_operation,
)


@dataclass(frozen=True)
class Reinspection:
    """One successful fetch compared against the last inspected (clean) set.

    `newly_appearing` is present in this fetch and absent from that set.
    `report.available` is the clean set after this fetch — carried forward
    from `last_inspected` where still fetched, plus every newly appearing
    operation whose recorded outcome is `clean`. That is FR-051's last
    inspected set, consumed from `InspectionReport.available` rather than
    restated.
    """

    newly_appearing: tuple[str, ...]
    report: InspectionReport


def appearing(
    fetched: Iterable[str],
    last_inspected: Iterable[str],
) -> tuple[str, ...]:
    """Present in the fetched set, absent from the last inspected (clean) set.

    Not "not in the last fetch" and not "not in last-known-good". FR-051's
    comparison is against the last **inspected** set, which is the clean set.
    """
    return tuple(sorted(frozenset(fetched) - frozenset(last_inspected)))


def _still_clean(operation_id: str) -> OperationOutcome:
    """Carry a previously clean operation that is still in this fetch.

    Not a replay of FR-056's three steps — those already ran, which is why
    the operation is in the last inspected set. Re-running them here would
    be re-inspect-on-every-fetch, which T158's `add-then-republish-unchanged`
    exists to catch.
    """
    if CLEAN not in ALLOWED_OUTCOMES:
        raise DeputyInspectionError(
            f"{CLEAN!r} is not in ALLOWED_OUTCOMES; a carried operation "
            "cannot be recorded as available."
        )
    return OperationOutcome(
        operation_id=operation_id,
        outcome=CLEAN,
        step=2,
        reason=(
            f"{operation_id} is in the last inspected set (recorded outcome "
            f"{CLEAN}) and is still in this fetch, so it is not re-inspected. "
            "FR-051 compares against the clean set, not the previous fetch."
        ),
    )


def reinspect(
    decision: AdmissionDecision,
    *,
    last_inspected: Iterable[str],
    handler_index: Mapping[str, str],
    codebase: Codebase,
) -> Reinspection:
    """Inspect every newly appearing operation before it becomes available.

    `last_inspected` is the clean set (`InspectionReport.available`). Newly
    appearing operations are handed to `inspect_operation`; previously clean
    operations still in the fetch are carried, not re-inspected. Denied
    outcomes stay in the report so the reason is reportable and do not become
    available.
    """
    if decision.state not in ADMISSIBLE_STATES:
        raise NotAdmittedForInspection(
            f"{decision.deployment_id} was not admitted (state "
            f"{decision.state}, criterion {decision.rule_id}), so FR-044's "
            "published specification supplied no operation list and there is "
            "nothing for FR-051's inspection to run over. T153 runs on a "
            "successful fetch; a failed re-fetch is T140/T147."
        )

    fetched = frozenset(
        str(entry["operation_id"]) for entry in decision.operations
    )
    inspected = frozenset(last_inspected)
    newly = appearing(fetched, inspected)

    new_outcomes = tuple(
        inspect_operation(
            op_id, handler_index=handler_index, codebase=codebase
        )
        for op_id in newly
    )
    still_available = tuple(
        _still_clean(op_id) for op_id in sorted(fetched & inspected)
    )
    inspected_now = new_outcomes
    report = InspectionReport(
        deployment_id=decision.deployment_id,
        outcomes=(*still_available, *inspected_now),
    )
    return Reinspection(newly_appearing=newly, report=report)
