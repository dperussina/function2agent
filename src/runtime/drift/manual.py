"""T143 — on-demand drift check for either clock, at any time (FR-029, OD-20).

Manual invocation is always available and is not configurable away. There is
no key in `src/contracts/config.py` that disables it, and this module reads
none. A config mapping that tries to turn it off is not consulted.

## Either clock is two different inputs

- **Source clock.** T138's `detect()` over artifacts. No specification fetch.
  The caller supplies the readings `detect` already requires — both clocks on
  both sides, with the deployment pair held at last-known-good, not re-fetched.
  Inventing a deployment reading *inside* this module so a source-only call
  could satisfy `compare_each` would be the fused artifact T137 made
  unconstructible arriving as a convenience. Passing a scheduler on this path
  is a refusal: that object exists to fetch.
- **Deployment clock.** A re-fetch through Plane A. T142 still binds. This
  path calls `Scheduler.tick(trigger=MANUAL)` and does not grow a second
  `origin_of` / `Authorization` / peer check. Passing artifacts on this path
  is a refusal: that would skip the peer check.

`compare_each` is not called here. Source-clock invalidation is T138's. The
deployment-clock comparison is `tick`'s `compare` on the deployment pair.

## `trigger=manual`, and the residual against §2.6

`data-model.md` §2.6 lists `trigger` as "scheduled, event, or path-level
probe (FR-046)". Manual is FR-029's, not FR-046's. Stuffing it into
`scheduled` would be a false record — a scheduled check that never waited for
the interval. `path-level probe` is T145's backstop. The honest name is
`manual`. Ruling §2.6's list incomplete is an owner act; this field carries
the name and the residual stays named.

Disablement is T146. Staleness is T147–T152. Re-inspection is T153. Path-level
reachability is T145. None of them are built here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from src.analysis.clocks import DEPLOYMENT, SOURCE, Reading
from src.analysis.source_drift import Invalidation, detect
from src.runtime.drift.scheduler import MANUAL, CheckResult, Scheduler


class ManualError(RuntimeError):
    """An on-demand check that would state something untrue about which clock
    it read, or that would fetch on the path that must not.
    """


@dataclass(frozen=True)
class SourceCheckResult:
    """One on-demand source-clock check. No fetch happened.

    `finding` is T138's `Invalidation` or quiet. `trigger` is `manual`. This
    is not a `CheckResult`: that type carries `last_successful_fetch` and the
    interval, which are facts about a specification re-fetch.
    """

    deployment_id: str
    finding: Invalidation | None
    detected_at: str
    trigger: str = MANUAL


def check_source(
    before: Mapping[str, Reading],
    after: Mapping[str, Reading],
    *,
    before_contracts: Mapping[str, Any],
    after_contracts: Mapping[str, Any],
    renamed: Sequence[tuple[str, str]] = (),
    now: str,
) -> SourceCheckResult:
    """FR-028 on demand: T138's `detect()`, with `trigger=manual`.

    No transport, no `origin_of`, no `classify`. The Plane A path is the
    other function.
    """
    finding = detect(
        before,
        after,
        before_contracts=before_contracts,
        after_contracts=after_contracts,
        renamed=renamed,
    )
    return SourceCheckResult(
        deployment_id=before[SOURCE].deployment_id,
        finding=finding,
        detected_at=now,
        trigger=MANUAL,
    )


def check_deployment(scheduler: Scheduler, *, now: str) -> CheckResult:
    """FR-029 on demand: the same Plane A re-fetch as a scheduled tick.

    Does not consult `due`. A check that is not owed on the interval is still
    owed on demand. T142's peer check lives in `tick`; this function does not
    re-state it.
    """
    return scheduler.tick(now=now, trigger=MANUAL)


def check(
    *,
    clock: str,
    now: str,
    scheduler: Scheduler | None = None,
    before: Mapping[str, Reading] | None = None,
    after: Mapping[str, Reading] | None = None,
    before_contracts: Mapping[str, Any] | None = None,
    after_contracts: Mapping[str, Any] | None = None,
    renamed: Sequence[tuple[str, str]] = (),
) -> CheckResult | SourceCheckResult:
    """Either clock, two different inputs. Mixing them is a refusal."""
    if clock == SOURCE:
        if scheduler is not None:
            raise ManualError(
                "source-clock on-demand reads artifacts; a transport on this "
                "path would be a specification fetch, which is the deployment "
                "clock's input and T142's subject. FR-029's either-clock "
                "check is two inputs, not one API that always fetches."
            )
        if (
            before is None
            or after is None
            or before_contracts is None
            or after_contracts is None
        ):
            raise ManualError(
                "source-clock on-demand needs the artifact pair T138's "
                "detect() already takes. This module does not invent a "
                "deployment reading so compare_each can be called, and it "
                "does not fetch a specification."
            )
        return check_source(
            before,
            after,
            before_contracts=before_contracts,
            after_contracts=after_contracts,
            renamed=renamed,
            now=now,
        )
    if clock == DEPLOYMENT:
        if before is not None or after is not None:
            raise ManualError(
                "deployment-clock on-demand re-fetches through Plane A; "
                "passing artifacts here would skip the peer check T142 binds "
                "and would be a second comparison of a surface nobody just "
                "fetched."
            )
        if scheduler is None:
            raise ManualError(
                "deployment-clock on-demand needs a scheduler whose transport "
                "dials the enforcement point. T142 still binds on a manual "
                "check; this module does not open a client."
            )
        return check_deployment(scheduler, now=now)
    raise ManualError(
        f"{clock!r} is not a clock. FR-027 maintains source and deployment; "
        "an on-demand check on a third would be a clock no drift signal can "
        "attribute movement to."
    )
