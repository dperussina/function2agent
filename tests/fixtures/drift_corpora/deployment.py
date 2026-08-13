"""T155 — the deployment-change synthetic corpus, and its controlled change time.

The corpus is `tests/fixtures/drift-deployment/corpus.json`; this module loads
it. **Criteria**: SC-009 and **SC-020**.

- **SC-009** — *"**100%** of operations withdrawn by the deployment in a
  synthetic deployment-drift corpus are detected and disabled, and **zero**
  unaffected operations are disabled alongside them."*
- **SC-020** — *"On the synthetic deployment-drift corpus, **100%** of
  withdrawn operations are detected within the configured detection window
  under the default automated trigger and with no event supplied by a
  deployment pipeline, and **100%** are detected on demand under manual
  invocation."*

## Why this corpus exists at all, which is a sentence about the real world

[`plan.md`](../../../specs/002-spec-aware-agent-runtime/plan.md) line 830
records, in Complexity Tracking:

> **Deployment-clock drift latency is not measurable on real traffic** unless
> the customer emits a deployment event, which FR-046 says may not be assumed
> — a property of the world: a deployment change generally has no observable
> change time. Measurable on the committed synthetic corpus, which controls the
> change time, and on real traffic only where the optional trigger exists.
> Inferring the change time from first observation measures the detector
> against itself.

So the synthetic corpus is not a convenience. It is **the only population on
which a deployment-clock latency can be computed at all**, and the single
property that makes it one is that `change.at` is primary data.

## The mechanical form of *not derived from an observation*

Prose saying the change time is controlled is worth nothing; a corpus author
under time pressure sets it to the first observation that saw the change and
the arithmetic still works. `_reject_change_time_read_off_an_observation`
refuses that: a declared change instant **may not coincide with any
observation instant in any arm of its scenario**.

That is checkable, it is checked at load time, and it fails loudly. A change
time strictly between two observations cannot have been read off either of
them.

The second half is the same discipline applied to the latency: this module
**computes** `detected_at` as the first observation at or after the change
whose served set is missing a withdrawn operation, computes the latency as the
difference from the declared change time, and contradicts the committed
figures rather than reading them.

## What the scheduled arm cannot falsify, stated rather than left to be found

The configured poll interval is **300 s** and the configured detection window
is **900 s**. Both are defaults marked unvalidated under FR-043 and neither has
a measurement behind it. Because the interval is smaller than the window, the
scheduled arm's latency is bounded above by the interval and **satisfies the
window by construction** for every scenario here.

That is a property of the two configured numbers, not a result. SC-020's window
clause is therefore not falsifiable on this corpus by the scheduled arm alone,
and `max_scheduled_latency_seconds()` exists so the margin is visible rather
than implied. Widening the interval past the window is what would make the
clause bite, and nothing here does that.

## The negative control, and the ablation it defeats

`no-withdrawal` is the scenario in which nothing is withdrawn across four
scheduled polls and one manual invocation. Both criteria are written as *100%
of withdrawn operations*, and a detector that disables the target on every poll
scores a perfect 100% on a corpus made only of withdrawals — the
experiment-design skill's **Rule 8**, and its tell is exactly that perfect
ablation score.

`withdraw-one-of-two-neighbours` is the second control and it is a different
one: it gives SC-009's *zero unaffected operations* clause a confusable
neighbour to take down. Without it, a detector matching on a name prefix passes.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from tests.fixtures.drift_corpora import (
    CorpusInconsistent,
    instant,
    seconds_between,
)

FIXTURES = Path(__file__).resolve().parent.parent
CORPUS_FILE = FIXTURES / "drift-deployment" / "corpus.json"
SERVED_OPERATIONS_FILE = FIXTURES / "reference-app" / "served_operations.json"

#: The two arms SC-020 names. Both are required of every scenario, because the
#: criterion has a clause for each and a scenario carrying one arm scores half
#: a criterion while reading like a whole one.
REQUIRED_ARMS = ("scheduled", "manual")

TRIGGERS = {
    "scheduled": "default_automated",
    "manual": "manual_on_demand",
}


@dataclass(frozen=True)
class Arm:
    """One trigger's observation series over a single scenario's change."""

    name: str
    trigger: str
    observation_instants: tuple[str, ...]
    detected_at: str | None
    latency_seconds: float | None


@dataclass(frozen=True)
class Scenario:
    """One deployment change, its controlled instant, and both arms."""

    scenario_id: str
    deployment_id: str
    served_before: frozenset[str]
    change_at: str | None
    withdrawn: tuple[str, ...]
    unaffected: tuple[str, ...]
    arms: Mapping[str, Arm]
    why: str

    @property
    def is_negative_control(self) -> bool:
        return not self.withdrawn


def _config() -> Mapping[str, int]:
    return json.loads(CORPUS_FILE.read_text())["configured"]


def detection_window_seconds() -> int:
    return _config()["detection_window_seconds"]


def poll_interval_seconds() -> int:
    return _config()["poll_interval_seconds"]


def deployment_events() -> list[Any]:
    """SC-020 requires this empty. It is returned so a test can say so."""
    return json.loads(CORPUS_FILE.read_text())["deployment_events"]


def _reject_change_time_read_off_an_observation(
    scenario: Mapping[str, Any],
) -> None:
    """The load-bearing check. A change time equal to an observation is refused.

    plan.md line 830: *"Inferring the change time from first observation
    measures the detector against itself."* A change instant that coincides
    with an observation instant is indistinguishable from one that was read off
    it, so the corpus is not allowed to contain one.
    """
    change_at = scenario["change"]["at"]
    if change_at is None:
        return
    for arm_name, arm in scenario["arms"].items():
        for observation in arm["observations"]:
            if observation["at"] == change_at:
                raise CorpusInconsistent(
                    f"{scenario['scenario_id']}: the declared change time "
                    f"{change_at!r} is also an observation instant in the "
                    f"{arm_name!r} arm. A change time that coincides with an "
                    "observation cannot be distinguished from one inferred "
                    "from it, which is the failure this corpus exists to "
                    "avoid — see plan.md line 830."
                )


def _computed_withdrawal(
    served_before: frozenset[str], arm: Mapping[str, Any]
) -> frozenset[str]:
    """What the observations say went away, recomputed from the served sets."""
    gone: set[str] = set()
    for observation in arm["observations"]:
        gone |= served_before - frozenset(observation["served"])
    return frozenset(gone)


def _computed_detection(
    change_at: str | None,
    withdrawn: frozenset[str],
    arm: Mapping[str, Any],
) -> tuple[str | None, float | None]:
    """First observation at or after the change that is missing a withdrawal."""
    if change_at is None or not withdrawn:
        return None, None
    change = instant(change_at)
    for observation in arm["observations"]:
        if instant(observation["at"]) < change:
            continue
        if withdrawn - frozenset(observation["served"]):
            return (
                observation["at"],
                seconds_between(change_at, observation["at"]),
            )
    raise CorpusInconsistent(
        "a scenario declares a withdrawal that no observation in this arm "
        "ever sees, so its latency is undefined rather than large"
    )


def load_scenarios() -> tuple[Scenario, ...]:
    """Every scenario, with the change time verified and both arms recomputed."""
    raw = json.loads(CORPUS_FILE.read_text())["scenarios"]
    window = detection_window_seconds()
    scenarios: list[Scenario] = []

    for entry in raw:
        _reject_change_time_read_off_an_observation(entry)

        served_before = frozenset(entry["served_before"])
        declared_withdrawn = frozenset(entry["change"]["withdrawn"])
        change_at = entry["change"]["at"]

        if bool(declared_withdrawn) != (change_at is not None):
            raise CorpusInconsistent(
                f"{entry['scenario_id']}: a withdrawal needs a change time and "
                "a scenario with no withdrawal must not carry one"
            )

        missing_arms = set(REQUIRED_ARMS) - set(entry["arms"])
        if missing_arms:
            raise CorpusInconsistent(
                f"{entry['scenario_id']}: SC-020 has a clause for the default "
                f"automated trigger and one for manual invocation; "
                f"{sorted(missing_arms)} is absent, so one clause would be "
                "scored over nothing"
            )

        arms: dict[str, Arm] = {}
        for arm_name in REQUIRED_ARMS:
            arm = entry["arms"][arm_name]
            if arm["trigger"] != TRIGGERS[arm_name]:
                raise CorpusInconsistent(
                    f"{entry['scenario_id']}/{arm_name}: trigger is "
                    f"{arm['trigger']!r}, expected {TRIGGERS[arm_name]!r}"
                )

            computed_withdrawn = _computed_withdrawal(served_before, arm)
            if computed_withdrawn != declared_withdrawn:
                raise CorpusInconsistent(
                    f"{entry['scenario_id']}/{arm_name}: declares "
                    f"{sorted(declared_withdrawn)} withdrawn, and the observed "
                    f"served sets lose {sorted(computed_withdrawn)}"
                )

            detected_at, latency = _computed_detection(
                change_at, declared_withdrawn, arm
            )
            if detected_at != arm["expected_detected_at"]:
                raise CorpusInconsistent(
                    f"{entry['scenario_id']}/{arm_name}: declares detection at "
                    f"{arm['expected_detected_at']!r}; the first observation "
                    f"after the change that is missing a withdrawal is "
                    f"{detected_at!r}"
                )
            if latency != arm["expected_latency_seconds"]:
                raise CorpusInconsistent(
                    f"{entry['scenario_id']}/{arm_name}: declares a latency of "
                    f"{arm['expected_latency_seconds']!r} s; "
                    f"{detected_at} minus {change_at} is {latency!r} s"
                )
            if latency is not None and latency > window:
                raise CorpusInconsistent(
                    f"{entry['scenario_id']}/{arm_name}: latency {latency} s "
                    f"exceeds the configured detection window of {window} s"
                )

            arms[arm_name] = Arm(
                name=arm_name,
                trigger=arm["trigger"],
                observation_instants=tuple(
                    o["at"] for o in arm["observations"]
                ),
                detected_at=detected_at,
                latency_seconds=latency,
            )

        computed_unaffected = tuple(sorted(served_before - declared_withdrawn))
        if tuple(sorted(entry["change"]["unaffected"])) != computed_unaffected:
            raise CorpusInconsistent(
                f"{entry['scenario_id']}: declares "
                f"{sorted(entry['change']['unaffected'])} unaffected; "
                f"served_before minus withdrawn is {list(computed_unaffected)}"
            )
        if tuple(sorted(entry["expected_disabled"])) != tuple(
            sorted(declared_withdrawn)
        ):
            raise CorpusInconsistent(
                f"{entry['scenario_id']}: SC-009 disables exactly the "
                "withdrawn operations, and expected_disabled differs"
            )
        if tuple(sorted(entry["expected_remain_enabled"])) != computed_unaffected:
            raise CorpusInconsistent(
                f"{entry['scenario_id']}: SC-009's second clause keeps exactly "
                "the unaffected operations enabled, and "
                "expected_remain_enabled differs"
            )

        scenarios.append(Scenario(
            scenario_id=entry["scenario_id"],
            deployment_id=entry["deployment_id"],
            served_before=served_before,
            change_at=change_at,
            withdrawn=tuple(sorted(declared_withdrawn)),
            unaffected=computed_unaffected,
            arms=arms,
            why=entry["why"],
        ))

    return tuple(scenarios)


def every_specification_state_seen() -> frozenset[str]:
    """The FR-044 states the observations report.

    This corpus is about a deployment that **withdraws operations while
    continuing to publish its specification**. A non-published state here would
    make it `tests/fixtures/spec-withdrawn/`, which is a different task and a
    different criterion.
    """
    raw = json.loads(CORPUS_FILE.read_text())["scenarios"]
    return frozenset(
        observation["specification_state"]
        for scenario in raw
        for arm in scenario["arms"].values()
        for observation in arm["observations"]
    )


def reference_app_operation_ids() -> frozenset[str]:
    doc = json.loads(SERVED_OPERATIONS_FILE.read_text())
    return frozenset(op["operation_id"] for op in doc["operations"])


def max_scheduled_latency_seconds() -> float:
    """The worst scheduled latency, over withdrawal scenarios only.

    Named that way on purpose: the negative control has no latency, and folding
    it in as a zero would report a mean over a population that includes a case
    with nothing to detect.
    """
    latencies = [
        s.arms["scheduled"].latency_seconds
        for s in load_scenarios()
        if not s.is_negative_control
    ]
    return max(x for x in latencies if x is not None)


def counts() -> Mapping[str, int]:
    """Every figure with its population named, never a bare total."""
    scenarios = load_scenarios()
    withdrawals = [s for s in scenarios if not s.is_negative_control]
    return {
        "scenarios_total": len(scenarios),
        "scenarios_carrying_a_withdrawal": len(withdrawals),
        "scenarios_with_nothing_withdrawn": len(scenarios) - len(withdrawals),
        "distinct_operations_withdrawn_across_withdrawal_scenarios": len({
            op for s in withdrawals for op in s.withdrawn
        }),
        "withdrawn_operation_instances_over_withdrawal_scenarios": sum(
            len(s.withdrawn) for s in withdrawals
        ),
        "observations_over_all_scenarios_and_both_arms": sum(
            len(a.observation_instants)
            for s in scenarios for a in s.arms.values()
        ),
    }
