"""T146 — disable the observed affected operation (FR-030, **SC-009**).

**Requirement**: FR-030 — *"On detected drift the affected operation MUST
be disabled and surfaced loudly, and unaffected operations MUST keep
working. Continuing to serve a drifted operation is prohibited; stopping
the whole runtime for one drifted operation is not required."*

**Narrowed by FR-047.** This requirement governs an operation *observed*
to have drifted. Below the staleness ceiling, `FailedRefetch` has **no
member to disable** — T147 marks the set stale. At the ceiling T150
already denies every call (`may_serve` / `deny_call`) and names
`terminated.staleness_ceiling_reached`. This module is not a second
deny-all. It does not disable the whole served set because a re-fetch
failed. It does not reimplement T150.

**Criterion**: SC-009 — *"**100%** of operations withdrawn by the
deployment in a synthetic deployment-drift corpus are detected and
disabled, and **zero** unaffected operations are disabled alongside
them."* Scored against T155. Detection without disablement does not
close it.

## What "affected" is

Disable what the **signal** (or the movement it was built from) names,
not a re-derived set that can disagree with T138 / T155.

- **Deployment-clock `ArtifactDrift`.** The signal names
  `kinds_moved=("served_operation_set",)`, not the operations. The
  movement was built from two served-id lists. `withdrawn_from_served`
  is the set difference T155's loader already derives as `withdrawn` —
  present before, absent after. Not a second withdrawn-operation
  classifier: there is no breaking/non-breaking verdict on this clock,
  and this module does not re-diff contracts. `compare_each` is not
  called; the caller supplies the consecutive sets the one-clock
  `compare` already used.
- **Source-clock `ArtifactDrift`.** The signal's `kinds_moved` names
  artifact kinds, not operations. `Invalidation.operations` (T138,
  `drifted_operations`) is what names them. If no finding is supplied,
  this module does not invent an operation and does not disable the
  target. T154 has no `expected_disabled`; that disposition is the
  Done note.
- **`FailedRefetch`.** No member. Always an empty disablement, even if
  consecutive served sets are passed. T147 / T150 own that case.

`source_derived` is the union of both clocks. This module filters on
`ArtifactDrift.clock` / `KINDS_ON_CLOCK`, never that boolean.

## Loud, not silent

`src/contracts/operator_log.py` is the human-facing channel, constructed
by an entry point and handed downward. Nothing in `src/` imports it
except the two entry points, and Python `src/` still has no `logging`
import by design. There is no call site that can emit. `Disablement`
**is** the disablement record (operation ids, deployment id, signal)
and `loudly()` is the payload a future caller can hand to
`OperatorLog.say`. This module does not add `logging.getLogger` and
does not wire `main.py`.

## What this module does not do

No live request path. No HTTP client. No target on Plane B. T161 is
still open. `now` is not read; disablement is a fact about a signal
already raised. `loop.py` / `runner.py` / `main.py` are not edited.
OD-36 still holds. A comment claiming disablement happens is not a
landed T146; this function and its tests are.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence, assert_never

from src.analysis.clocks import DEPLOYMENT, SOURCE
from src.analysis.drift_signal import ArtifactDrift, DriftSignal, FailedRefetch
from src.analysis.source_drift import Invalidation

#: Zero disablements. Named so "no signal, nothing disabled" is a value
#: rather than a missing return, and so T155's `no-withdrawal` control
#: has a node to pin. Disabling the target because a poll happened is
#: the cheap detector that control exists to fail.
NOTHING_DISABLED: tuple["Disablement", ...] = ()

#: Source-clock `ArtifactDrift` names kinds, not operations. Empty is
#: the disposition: do not invent an operation, do not disable the
#: target.
NO_NAMED_OPERATION: tuple[str, ...] = ()


class DisableError(RuntimeError):
    """A disablement that would state something untrue about who drifted."""


@dataclass(frozen=True)
class Disablement:
    """The affected operations, disabled, and the signal that named them.

    Unaffected ids are **absent** from `disabled`. That absence is
    FR-030's second clause, and SC-009 scores it. Surfacing loudly is
    this record plus `loudly()`; there is no logger here.
    """

    deployment_id: str
    disabled: tuple[str, ...]
    signal: DriftSignal

    def loudly(self) -> str:
        """The human-facing line. A payload, not a write.

        `OperatorLog` is constructed by an entry point. This module is
        not one. A future assembler hands this string to `say`.
        """
        names = ", ".join(self.disabled) if self.disabled else "(none)"
        return (
            f"drift: disabled [{names}] on deployment {self.deployment_id}; "
            "unaffected operations keep working"
        )


def withdrawn_from_served(
    served_before: Sequence[str],
    served_after: Sequence[str],
) -> tuple[str, ...]:
    """The identity of a withdrawal: present before, absent after.

    The same set difference T155's loader derives as `withdrawn`. Not a
    second classifier — there is no breaking/non-breaking verdict on the
    deployment clock, and this does not re-diff contracts.
    """
    return tuple(sorted(frozenset(served_before) - frozenset(served_after)))


def remaining(
    served: Sequence[str],
    disablement: Disablement,
) -> tuple[str, ...]:
    """Unaffected keep working: still in `served`, not in `disabled`."""
    blocked = frozenset(disablement.disabled)
    return tuple(
        operation_id for operation_id in served if operation_id not in blocked
    )


def disable(
    signal: DriftSignal,
    *,
    served_before: Sequence[str] | None = None,
    served_after: Sequence[str] | None = None,
    source_finding: Invalidation | None = None,
) -> Disablement:
    """Disable the operations the signal (or its movement) names, and only those.

    `FailedRefetch` disables nothing. A deployment-clock `ArtifactDrift`
    needs the consecutive served-id sets the movement was built from. A
    source-clock `ArtifactDrift` disables `source_finding.operations` when
    a finding is supplied, and nothing when it is not.
    """
    match signal:
        case FailedRefetch():
            return Disablement(
                deployment_id=signal.deployment_id,
                disabled=(),
                signal=signal,
            )
        case ArtifactDrift():
            if signal.clock == DEPLOYMENT:
                if served_before is None or served_after is None:
                    raise DisableError(
                        "a deployment-clock ArtifactDrift names the "
                        "served_operation_set kind, not the operations. "
                        "Disablement takes the consecutive served-id sets "
                        "the movement was built from; inventing the "
                        "affected set from the kind name would disable the "
                        "target or disable nothing, and SC-009 scores both "
                        "mistakes."
                    )
                return Disablement(
                    deployment_id=signal.deployment_id,
                    disabled=withdrawn_from_served(served_before, served_after),
                    signal=signal,
                )
            if signal.clock == SOURCE:
                if source_finding is None:
                    return Disablement(
                        deployment_id=signal.deployment_id,
                        disabled=NO_NAMED_OPERATION,
                        signal=signal,
                    )
                if source_finding.signal.deployment_id != signal.deployment_id:
                    raise DisableError(
                        "a source-clock disablement was given a finding "
                        f"for {source_finding.signal.deployment_id!r} and a "
                        f"signal for {signal.deployment_id!r}. FR-031 binds "
                        "a drift signal to the deployment it applies to; "
                        "mixing two identities disables one target's "
                        "operations on the other's record."
                    )
                if source_finding.signal.clock != SOURCE:
                    raise DisableError(
                        "a source-clock disablement was given a finding "
                        f"on the {source_finding.signal.clock!r} clock. "
                        "T138's Invalidation.operations is the source "
                        "clock's named set; a deployment finding here "
                        "would be a second withdrawn-operation classifier."
                    )
                return Disablement(
                    deployment_id=signal.deployment_id,
                    disabled=source_finding.operations,
                    signal=signal,
                )
            raise DisableError(
                f"{signal.clock!r} is not a clock disablement handles. "
                "FR-027 maintains two; a third would disable against a "
                "clock nothing else reads."
            )
        case _:
            assert_never(signal)


def disablements_of(
    signals: Sequence[DriftSignal],
    *,
    served_before: Sequence[str],
    served_after: Sequence[str],
    source_finding: Invalidation | None = None,
) -> tuple[Disablement, ...]:
    """One disablement per signal. Zero signals is zero disablements.

    T155's `no-withdrawal` control: a poll that observed nothing withdrawn
    produces no signal, and producing a disablement of the target anyway
    is the cheap detector Rule 8 is for.
    """
    if not signals:
        return NOTHING_DISABLED
    return tuple(
        disable(
            signal,
            served_before=served_before,
            served_after=served_after,
            source_finding=source_finding,
        )
        for signal in signals
    )
