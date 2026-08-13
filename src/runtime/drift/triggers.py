"""T144 — the two additional configurable triggers (FR-046).

After T141's scheduled default, FR-046 requires at least these additional
triggers configurable in place of, or alongside, it:

- a **deployment event emitted by the customer's own rollout mechanism**,
  which is the lowest-latency trigger where a customer can emit one and
  **MUST NOT be assumed available**;
- a **re-check at session start**.

The per-operation path-level reachability precondition is T145's backstop and
is not a trigger this module emits.

## What is not assumed, and what is not required

The scheduled trigger (T141) is the default that needs no pipeline event.
FR-029's "at least one automated trigger MUST be configurable" is already
satisfied by that interval. This module adds two more that *may* be
configured. A constructor or selection that *requires* a deployment-event
endpoint would make the product blind on self-hosted deployments (OD-08,
OD-20) that cannot emit one. `TriggerSelection` defaults both additional
triggers off. There is no endpoint field.

The event, where configured, is inbound: the customer's rollout notifies us.
This module does not dial a pipeline, does not open a client, and does not
hold a URL to one.

## Session start is a deployment-clock re-fetch

FR-046 states the session-start trigger in the deployment-drift-check
paragraph. It is `Scheduler.tick(trigger=SESSION_START)`, the same Plane A
path T142 binds, not a source-clock re-analysis and not a spec fetch that
bypasses the enforcement point.

There is no live session loop to hang it on (OD-36: `Registry` constructed
nowhere; `src/runtime/main.py` still report+exit). `on_session_start` is the
callable the assembler would invoke. `src/runtime/loop.py` and
`src/runtime/runner.py` are not edited to invent a call site.

## Trigger names against §2.6

`event` is §2.6's slot. `session_start` is FR-046's additional trigger with
no slot in the three-word list — the same named residual as T143's `manual`.
Neither is stuffed into `scheduled`. `path-level probe` is refused by `tick`.

Both callables call `tick`. The Plane A refusal is one function, not two.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.runtime.drift.scheduler import (
    EVENT,
    SESSION_START,
    CheckResult,
    Scheduler,
)


class TriggerError(RuntimeError):
    """An additional trigger that was not configured, or that would assume
    a pipeline event the product must not require.
    """


@dataclass(frozen=True)
class TriggerSelection:
    """Which additional automated triggers are configured.

    Both default off. The scheduled trigger is T141's and is not a field
    here: this selection cannot turn the default off by omitting it, and
    cannot make a pipeline event mandatory by requiring it.

    Manual invocation is not a field. FR-029 / OD-20: always available, not
    configurable away. A flag here whose False disabled T143 would be that
    configuration.

    There is no endpoint, URL, or webhook field. FR-046: a customer-emitted
    event must not be assumed available, and under OD-08 it cannot be.
    """

    deployment_event: bool = False
    session_start: bool = False


class Triggers:
    """The two additional triggers, optional, sharing T141's Plane A check.

    Constructed around a `Scheduler` so the peer check, the Authorization
    refusal, and the one-clock `compare` are the same function the interval
    already calls. Selection defaults to both-off: the product with only the
    scheduler and manual is already a complete automated+manual pair.
    """

    def __init__(
        self,
        scheduler: Scheduler,
        selection: TriggerSelection | None = None,
    ) -> None:
        self._scheduler = scheduler
        self._selection = (
            selection if selection is not None else TriggerSelection()
        )

    def on_deployment_event(self, *, now: str) -> CheckResult:
        """A customer-emitted rollout event, if that trigger was configured.

        The event is the *reason* to check, not the bytes checked. The check
        is still a Plane A re-fetch of the published specification. No
        pipeline URL is dialed.
        """
        if not self._selection.deployment_event:
            raise TriggerError(
                "a deployment event was presented but that trigger is not "
                "configured. FR-046: a customer-emitted event MUST NOT be "
                "assumed available; the default automated trigger is the "
                "scheduler T141 ships, which needs no pipeline event."
            )
        return self._scheduler.tick(now=now, trigger=EVENT)

    def on_session_start(self, *, now: str) -> CheckResult:
        """A deployment-clock re-fetch at session start, if configured.

        Not a source-clock re-analysis. Not a spec fetch that bypasses Plane
        A. The assembler invokes this; nothing in `loop.py` or `runner.py`
        calls it today (OD-36).
        """
        if not self._selection.session_start:
            raise TriggerError(
                "a session-start re-check was requested but that trigger is "
                "not configured. FR-046 lists it as an additional trigger, "
                "configurable in place of or alongside the default, not as "
                "an imposed one."
            )
        return self._scheduler.tick(now=now, trigger=SESSION_START)
