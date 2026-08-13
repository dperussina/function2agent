"""T141 and T142 — the deployment-clock scheduler, and the one path it may dial.

**T141 / FR-046, FR-029 (automatic half).** The default automated trigger for a
deployment-drift check is a scheduled re-fetch of the target's published
specification. The system ships the scheduler. It requires no event from the
customer's deployment pipeline, no phone-home, and no outbound request to any
destination other than the target. The default interval is five minutes, and
that number is a configured default marked unvalidated under FR-043 — it is
not a measurement. The authorising decision is OD-20, jointly with FR-029.

**T142 / OD-12, T-10.** The re-fetch is Plane A's subject-matter: bytes to the
target. It runs through the enforcement point, not through Plane B and not
through a second HTTP client that can name an origin. An unrouted scheduler
would leave one policy governing every byte that reaches the target true of
the sandbox and false of the system. Binding authority is OD-12 and
constitution Principle IV bullet 1, which is what
`tests/invariants/test_sandbox_reachability.py` and this package's
`__init__.py` already cite. FR-014's literal text scopes to the execution
environment; citing it as this module's own requirement would be citing a
property it does not state.

## What this module consumes rather than restates

- **T073** `classify` is the judge. A transport reports evidence and never
  names a state. This module does not teach `admission.py` the proxy:
  analysis cannot import runtime (`tests/invariants/test_layering.py`).
- **T077 / T137** `deployment_reading` / `compare` / `Movement`. A `Reading`
  is a complete value. Independence is a refusal. There is no second version
  comparison here. `compare_each` is not called: it requires both clocks, and
  inventing a source reading so we could call it would be the fused artifact
  T137 made unconstructible arriving as a convenience. The one-clock function
  is `compare`. The filter is `Movement.clock == DEPLOYMENT`, not
  `schemas.source_derived` — that flag is the union of both clocks, and
  filtering on it would treat a source-clock move as deployment drift, the
  inverse of the T138 trap.
- **T139 / T140** `signals_from_movements` / `failed_refetch`.
  `ArtifactDrift.from_movement` is the only constructor for a moved clock.
  A failed re-fetch is a `FailedRefetch` and has no `version_after` attribute
  at all. This module produces those records. It does not enter the stale
  state (T147), does not build `Staleness` (T148), does not disable
  operations (T146), and does not re-inspect (T153).

## The transport, and why this file never opens a client

`tests/contract/test_runtime_egress.py` refuses any outbound constructor under
`src/runtime/` that does not go through Plane B's `guarded()`. Routing the
specification fetch through Plane B is the defect T-10 exists to prevent:
Plane B is pinned to model-provider endpoints and carries no route to the
target. So there is no client here. The assembler later supplies a transport
whose only configured destination is the enforcement point. `tick` refuses a
fetch whose reported peer is not that point. A transport that dials the
origin directly fails that check, which is the cheap detector Rule 8 is for.

INV-003 is necessary and not sufficient: `admission.fetch_over_http` is not
under `SANDBOX_ROOTS`, so a scheduler that called it with an origin passed in
from configuration would not fire the static scan. The peer check is what
does.

The Plane A protocol is the capability header `src/supervisor/capability.py`
names (`X-F2A-Capability`). The proxy injects the target credential on
re-origination. This module does not hold that credential, does not accept
one as an argument, and refuses a transport that presented an `Authorization`
header — that is the target-credential plane, and T161 is still open.

## Which process ticks, and why the module is not under `src/supervisor/`

The interval key `DRIFT_CHECK_INTERVAL_SECONDS` lives on `SUPERVISOR_KEYS`.
The module path is `src/runtime/drift/` because INV-003 scans
`SANDBOX_ROOTS = (src/sandbox/, src/runtime/drift/)`. Moving this file to
`src/supervisor/` to match the key would take it outside the only static
check that catches a literal hostname in sandbox-side source.

The ticker is the **runtime** process. OD-36 scoped the remaining
assembly-point absence to the runtime entry (`Registry` constructed nowhere);
`src/runtime/main.py` ends in a report and an exit, not a serve loop. Nothing
in that entry calls `tick` today. `due` is the interval predicate the
assembler will ask; this module does not start a thread and does not read
the clock itself.

The key cites FR-028 while its description and FR-046's five-minute default
are the deployment-clock scheduler. Using the key is correct. Retagging it
is not this slice.

## What is recorded with the deployment identity

FR-046 requires the interval and the stated detection window recorded with
the deployment they apply to. The interval is a constructor argument and
travels on every `CheckResult`. The stated window is "one interval plus the
duration of one check" and is a configured default, not a measurement; there
is no declared key for it (the T155 corpus carries 900 s as its own
configured window). This module does not invent one. `STALENESS_CEILING_SECONDS`
is T149's and is not enforced here.

## `trigger`, and why it is not on the sum type

`data-model.md` §2.6 lists `trigger` ("scheduled, event, or path-level probe
(FR-046)"). T139 deferred it because there was no producer. T141 put it on
`CheckResult` rather than on the sum: `from_movement` is also T138's
constructor, and a source-clock finding has no FR-046 trigger.

`tick` is that producer, parameterised by trigger so T143 and T144 do not
grow a second Plane A refusal. The default remains `scheduled`. Admissible
names are `scheduled`, `manual`, `event`, and `session_start`. `path-level
probe` is refused — it is T145's backstop, not a trigger this slice emits.

Two of those names are a named residual against §2.6's three-word list:
`manual` is FR-029's, not FR-046's, and `session_start` is FR-046's additional
trigger with no slot in the list. Ruling the list incomplete is an owner act;
the field carries the honest names rather than stuffing either into
`scheduled` or into `event`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Protocol
from urllib.parse import urlsplit, urlunsplit

from src.analysis.admission import ADMISSIBLE_STATES, FetchResponse, classify
from src.analysis.clocks import DEPLOYMENT, Movement, Reading, compare, deployment_reading
from src.analysis.drift_signal import (
    DriftSignal,
    failed_refetch,
    signals_from_movements,
)

#: FR-046 / data-model.md §2.6. The default this producer emits.
SCHEDULED = "scheduled"
#: FR-029 / OD-20. On-demand, either clock. Not in §2.6's three-word list —
#: named residual, not a silent widening of the data model.
MANUAL = "manual"
#: FR-046 / §2.6. A customer-emitted deployment event. Must not be assumed
#: available; T144's selection defaults it off.
EVENT = "event"
#: FR-046's additional trigger. Not in §2.6's three-word list — named residual,
#: same disposition as MANUAL. A deployment-clock re-fetch, not a source
#: re-analysis.
SESSION_START = "session_start"
#: §2.6 lists this. T145's backstop. Refused as a trigger, never emitted.
PATH_LEVEL_PROBE = "path-level probe"

ALLOWED_TRIGGERS = frozenset({SCHEDULED, MANUAL, EVENT, SESSION_START})

#: The header the sandbox presents as its authority to reach the enforcement
#: point. Named so a grep finds both ends: `src/supervisor/capability.py`
#: (`header_value`) and `src/proxy/pipeline.go` (`capabilityHeader`).
CAPABILITY_HEADER = "X-F2A-Capability"


class SchedulerError(RuntimeError):
    """A scheduled check that would state something untrue about drift, or
    that would reach the target by a second path.
    """


def origin_of(url: str) -> str:
    """Scheme and host (and port, if present). Path, query and fragment drop.

    The peer check compares origins, so a fetch of a specification path on
    the enforcement point still counts as that point, and a fetch whose host
    is the target does not become that point by sharing a path prefix.
    """
    parts = urlsplit(url)
    if not parts.scheme or not parts.netloc:
        raise SchedulerError(
            f"{url!r} is not an origin the scheduler can dial. The "
            "enforcement point is named by configuration as a URL with a "
            "scheme and a host; a path-only or empty value cannot be a peer."
        )
    return urlunsplit((parts.scheme, parts.netloc, "", "", ""))


@dataclass(frozen=True)
class Fetch:
    """What a transport returns: evidence, and the peer it actually dialed.

    `response` is T073's evidence shape. The transport never names a state.
    `peer` is the origin the bytes came from, as the transport reports it —
    not as a caller wishes it had been. `tick` compares that value to the
    configured enforcement point and refuses a mismatch.
    """

    response: FetchResponse
    peer: str
    #: Headers the transport sent. Empty unless the transport reports them.
    #: An `Authorization` value is the target-credential plane and is refused.
    request_headers: Mapping[str, str] = field(default_factory=dict)


class SpecificationTransport(Protocol):
    """A fetch whose only configured destination is the enforcement point."""

    def fetch(self) -> Fetch:
        """Evidence from one re-fetch, plus the peer that produced it."""


def due(
    *,
    now: float,
    last_tick_at: float | None,
    interval_seconds: float,
) -> bool:
    """Whether a tick is owed at `now`, given the last tick and the interval.

    `now` and `last_tick_at` are epoch seconds. There is no default clock:
    a module that reads the clock itself cannot be asked about a specific
    one. A non-positive interval is a refusal, not "always due" — that
    reading would make a misconfigured scheduler a tight loop.
    """
    if interval_seconds <= 0:
        raise SchedulerError(
            f"interval_seconds={interval_seconds!r} is not a positive "
            "interval. FR-046's default is a configured number marked "
            "unvalidated; a non-positive value is not that number and is "
            "not a measurement of anything."
        )
    if last_tick_at is None:
        return True
    return now - last_tick_at >= interval_seconds


def deployment_signals_of(movements: tuple[Movement, ...]) -> tuple[DriftSignal, ...]:
    """The deployment-clock slice of a comparison, as T139's signals.

    The filter is `Movement.clock == DEPLOYMENT`. Filtering on
    `schemas.source_derived` would report a source-clock move as deployment
    drift, because that flag is the union of both clocks.
    """
    return signals_from_movements(
        movement for movement in movements if movement.clock == DEPLOYMENT
    )


@dataclass(frozen=True)
class CheckResult:
    """One tick's outcome. Not a stale marking, not a disablement.

    `trigger` lives here rather than on `DriftSignal` — see the module
    docstring. Default is `scheduled`. T143 and T144 pass `manual`, `event`,
    or `session_start` through the same path. `detected_at` is the wall-clock
    instant this check observed, a fact about the check, not about the change.
    `change_at` is not stored: T155 controls it on the corpus, and real
    deployment-clock traffic generally has no observable change time (T184).
    """

    deployment_id: str
    signals: tuple[DriftSignal, ...]
    last_successful: Reading
    last_successful_fetch: str
    detected_at: str
    interval_seconds: float
    interval_unvalidated: bool
    trigger: str = SCHEDULED


class Scheduler:
    """The default automated trigger. One deployment, one enforcement point.

    Constructed with the last successful admission reading. A failed re-fetch
    has no *after* artifact version and needs that reading as *before*; a
    scheduler with no last-known-good cannot produce a `FailedRefetch` that
    states FR-031's surviving terms.
    """

    def __init__(
        self,
        *,
        deployment_id: str,
        enforcement_point: str,
        transport: SpecificationTransport,
        last_successful: Reading,
        last_successful_fetch: str,
        interval_seconds: float,
        interval_unvalidated: bool = True,
    ) -> None:
        if not deployment_id:
            raise SchedulerError(
                "a scheduler was constructed for no deployment. FR-046 "
                "requires the interval recorded with the deployment identity "
                "it applies to, and a check with no subject cannot supply one."
            )
        if not enforcement_point.strip():
            raise SchedulerError(
                "a scheduler was constructed with no enforcement point. "
                "T142 requires the re-fetch's peer to be that point, named "
                "by configuration; an empty value makes every peer a mismatch "
                "or, worse, makes the check accept whatever the transport "
                "dialed."
            )
        # Touches the URL so a scheme-less value fails at construction, not
        # on the first tick, and so the configured name is the origin the
        # peer will be compared against.
        self.enforcement_point = origin_of(enforcement_point)
        if last_successful.clock != DEPLOYMENT:
            raise SchedulerError(
                f"a scheduler for {deployment_id!r} was given a "
                f"{last_successful.clock}-clock reading as last-known-good. "
                "FR-029 detects a change in what the deployment serves; a "
                "source reading here would report a source-derived version as "
                "the last-known-good served surface, which is the two clocks "
                "back in one field."
            )
        if last_successful.deployment_id != deployment_id:
            raise SchedulerError(
                f"a scheduler for {deployment_id!r} was given a last-known-good "
                f"reading of {last_successful.deployment_id!r}. FR-031 binds "
                "a drift signal to the deployment it applies to; mixing two "
                "identities reports one target's movement as the other's."
            )
        if interval_seconds <= 0:
            raise SchedulerError(
                f"interval_seconds={interval_seconds!r} is not a positive "
                "interval. FR-046's default is a configured number marked "
                "unvalidated; a non-positive value is not that number."
            )
        self.deployment_id = deployment_id
        self._transport = transport
        self._last_successful = last_successful
        self._last_successful_fetch = last_successful_fetch
        self.interval_seconds = interval_seconds
        self.interval_unvalidated = interval_unvalidated

    def tick(self, *, now: str, trigger: str = SCHEDULED) -> CheckResult:
        """One check: fetch through Plane A, classify, compare or fail.

        On an admissible fetch: a deployment `Reading`, `compare` against the
        last successful reading, `deployment_signals_of`. An unchanged spec
        produces zero signals. On a non-admissible fetch: `FailedRefetch`
        from the last successful reading. The last-known-good is updated
        only on success — a failed re-fetch does not invent an after-version
        and does not move the timestamp FR-047's ceiling is measured from.

        `trigger` parameterises the same path so T143 and T144 do not grow a
        second peer check. The default is `scheduled`. `path-level probe` is
        refused.
        """
        if trigger not in ALLOWED_TRIGGERS:
            if trigger == PATH_LEVEL_PROBE:
                raise SchedulerError(
                    "path-level probe is FR-046's backstop, not a trigger. "
                    "T145 records a failing path-level reachability "
                    "precondition as a drift signal; relying on it as a "
                    "trigger design is the thing FR-046 forbids."
                )
            raise SchedulerError(
                f"trigger={trigger!r} is not a drift-check trigger this "
                "producer emits. data-model.md §2.6 lists scheduled, event, "
                "or path-level probe; FR-029's manual and FR-046's "
                "session_start are additional names this field carries, and "
                "path-level probe is refused rather than emitted."
            )
        fetched = self._transport.fetch()
        if any(name.lower() == "authorization" for name in fetched.request_headers):
            raise SchedulerError(
                "a scheduled fetch presented an Authorization header. The "
                "target credential is injected by the enforcement point on "
                "re-origination; the Plane A protocol is "
                f"{CAPABILITY_HEADER}, and T161 is still open. A credential "
                "on this request is a second copy of the secret the sandbox "
                "must not hold."
            )
        if origin_of(fetched.peer) != self.enforcement_point:
            raise SchedulerError(
                f"a scheduled fetch dialed {fetched.peer!r}, which is not "
                f"the configured enforcement point {self.enforcement_point!r}. "
                "T-10 puts the specification fetch through Plane A's proxy "
                "so one policy governs every byte that reaches the target; "
                "a transport that dials the origin is the second continuous "
                "path that guarantee exists to prevent."
            )

        classification = classify(fetched.response)
        if classification.state not in ADMISSIBLE_STATES:
            signal = failed_refetch(
                self._last_successful,
                specification_state=classification.state,
                last_successful_fetch=self._last_successful_fetch,
            )
            return CheckResult(
                deployment_id=self.deployment_id,
                signals=(signal,),
                last_successful=self._last_successful,
                last_successful_fetch=self._last_successful_fetch,
                detected_at=now,
                interval_seconds=self.interval_seconds,
                interval_unvalidated=self.interval_unvalidated,
                trigger=trigger,
            )

        after = deployment_reading(
            deployment_id=self.deployment_id,
            operations=classification.operations,
        )
        movement = compare(self._last_successful, after)
        signals = deployment_signals_of((movement,))
        self._last_successful = after
        self._last_successful_fetch = now
        return CheckResult(
            deployment_id=self.deployment_id,
            signals=signals,
            last_successful=after,
            last_successful_fetch=now,
            detected_at=now,
            interval_seconds=self.interval_seconds,
            interval_unvalidated=self.interval_unvalidated,
            trigger=trigger,
        )
