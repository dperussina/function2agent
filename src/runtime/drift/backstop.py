"""T145 — a failing path-level reachability precondition, recorded as a backstop.

**Requirement**: FR-046 — *"The per-operation path-level reachability
precondition failing in front of a user is a backstop that MUST be recorded
as a drift signal, and MUST NOT be relied on as a trigger design."*

`Scheduler.tick` already refuses `trigger == "path-level probe"`. This
module does not reverse that. It does not emit `path-level probe` as a
`CheckResult.trigger`. It records a failing precondition on a
**user-facing call**. It is not a fifth scheduled trigger.

## Why this is not a `DriftSignal`

`DriftSignal = ArtifactDrift | FailedRefetch` at
`src/analysis/drift_signal.py`. FR-031 requires clock, versions before and
after (or FR-047's narrowed after-term), and the deployment identity.

- **`ArtifactDrift`** requires both versions obtained, a moved clock, and
  non-empty `kinds_moved`. Built only via `from_movement`. A path-level
  HTTP failure in front of a user obtained no artifact pair and ran no
  comparison. Inventing versions that were not obtained would be a false
  record of FR-031's unnarrowed terms.
- **`FailedRefetch`** is a **specification re-fetch** that returned a
  non-admissible state. It has no `version_after` attribute, and that
  absence is FR-047's fact about the observation channel. A path-level
  HTTP failure is not a specification re-fetch, and stuffing one into this
  shape would report FR-044's classifier having named a state that was
  never classified.
- FR-047's narrowing is the **one** authorised exception to `version_after`,
  and it is specifically the failed specification re-fetch. A second
  narrowing so a path failure could join the sum is an owner act. Adding a
  third sum-type member is a change to T139/T140's module and is not done
  here, because FR-031's terms cannot be stated for this case without
  inventing versions that were not obtained.

So a path-level failure cannot honestly be either existing variant. That
residual is **named rather than closed**: this record is a backstop
observation, not a third `DriftSignal` member, and not stuffed into
`FailedRefetch` or into `scheduled` to make `data-model.md` §2.6's
three-word trigger list look complete. Ruling the list incomplete is an
owner act; T143/T144 already named `manual` and `session_start` as
omitted. This slice does not amend §2.6.

`data-model.md` §2.6 still lists `scheduled, event, or path-level probe`.
The probe is the backstop FR-046 forbids relying on as a trigger. It is
not emitted here.

## What this module consumes rather than restates

The caller already observed the path failure and supplies the facts —
operation id, deployment identity, what was observed, and `detected_at`.
This module records them. It does not open an HTTP client. Plane A still
binds if this module fetched; Plane B has no route to the target.
`tests/contract/test_runtime_egress.py` refuses outbound constructors
under `src/runtime/` that skip Plane B `guarded()`. T161 is still open:
no runtime-held capability or target credential.

T065 `budget_backstop.py` is a different backstop (call-count). This
module does not halt the session with `BackstopTripped`. Disablement of
an operation observed to have drifted is T146 and is not this recording:
using the path failure itself to disable would make the backstop a
trigger, which is the thing FR-046 forbids.

`now` is an argument (`detected_at`). The clock is not read here.
`compare_each` is not called. `from_movement` is not called.
`failed_refetch` is not called.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


#: Discriminant on the serialized record. Not `path-level probe` — that
#: spelling is `CheckResult.trigger`'s refused name, and putting it here
#: would make the backstop look like a trigger the document emitted.
PATH_LEVEL_FAILURE = "path_level_failure"


class BackstopError(RuntimeError):
    """A path-level backstop record that would state something untrue."""


@dataclass(frozen=True)
class PathLevelFailure:
    """A failing path-level reachability precondition, as a backstop record.

    Not a `DriftSignal`. Not a `CheckResult`. Not `BackstopTripped`. The
    caller supplies every field; nothing here was fetched.
    """

    operation_id: str
    deployment_id: str
    #: What the caller observed on the user-facing call — a status, a
    #: transport error, a named refusal. Planted in tests. Not a
    #: specification state: FR-044's classifier did not run.
    observed: str
    #: Wall-clock instant of the observation, supplied by the caller.
    detected_at: str

    def document(self) -> dict[str, Any]:
        """The record. Deliberately no `trigger` key.

        `path-level probe` is §2.6's name for a trigger this producer
        refuses to be. A document carrying that key would report the
        backstop as a trigger design, which is the thing FR-046 forbids.
        """
        return {
            "record_kind": PATH_LEVEL_FAILURE,
            "operation_id": self.operation_id,
            "deployment_id": self.deployment_id,
            "observed": self.observed,
            "detected_at": self.detected_at,
        }


def record(
    *,
    operation_id: str,
    deployment_id: str,
    observed: str,
    detected_at: str,
) -> PathLevelFailure:
    """Record a failing path-level reachability precondition.

    Facts in, record out. No fetch, no comparison, no session halt.
    """
    if not operation_id:
        raise BackstopError(
            "a path-level backstop was recorded for no operation. FR-046's "
            "precondition is per-operation; a record that cannot name whose "
            "path failed cannot be acted on without disabling the target or "
            "disabling nothing."
        )
    if not deployment_id:
        raise BackstopError(
            "a path-level backstop was recorded for no deployment. FR-031 "
            "binds a drift signal to the deployment identity it applies to; "
            "this backstop is not a DriftSignal, but a record with no "
            "subject still cannot say whose path failed."
        )
    if not observed:
        raise BackstopError(
            "a path-level backstop was recorded with no observation. The "
            "caller already saw the path fail and supplies that fact; an "
            "empty observation is a record that something happened and a "
            "statement of nothing."
        )
    if not detected_at:
        raise BackstopError(
            "a path-level backstop was recorded with no detected_at. The "
            "instant is a fact about the user-facing call, supplied by the "
            "caller; this module does not read the clock."
        )
    return PathLevelFailure(
        operation_id=operation_id,
        deployment_id=deployment_id,
        observed=observed,
        detected_at=detected_at,
    )
