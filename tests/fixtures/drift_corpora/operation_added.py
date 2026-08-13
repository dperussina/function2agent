"""T158 — an operation added to a specification the target never stops publishing.

The corpus is `tests/fixtures/operation-added/corpus.json`; this module loads
it. **Criterion**: **SC-026** — *"On a fixture in which the target adds an
operation to its published specification while continuing to publish that
specification throughout, **100%** of newly appearing operations are inspected
before becoming available, **zero** become available uninspected, and **100%**
of those that cannot be inspected are refused."*

## The continuity is the fixture, not the setting

*"while continuing to publish that specification throughout"* is the clause
that makes this a different fixture from `tests/fixtures/spec-withdrawn/`
rather than a variation on it. There, the specification goes away and the
question is what to serve from a stale set; here it never goes away and the
question is what to do with something new inside it.

`_reject_a_non_published_fetch` enforces it. A single non-published fetch
would silently convert this corpus into T157's and score SC-026 on a timeline
SC-026 does not describe.

## What counts as newly appearing, which is T153's wording and not the obvious one

T153: *"compare the newly fetched set against the last **inspected** set and
inspect every operation present in the first and absent from the second before
it becomes available, failing closed on any it cannot inspect."*

The comparison is against the last **inspected** set, not the last-known-good
set and not the previous fetch. `_walk` carries the inspected set forward
across fetches, so `add-then-republish-unchanged` — where the third fetch
republishes what the second already introduced — computes an **empty** third
entry. An implementation comparing against the previous fetch gets that right
by luck; one re-inspecting on every fetch gets it wrong, and that is the case
the scenario exists to separate.

## The two non-clean outcomes stay two outcomes

FR-056's vocabulary is imported from `src/analysis/deputy_inspection.py` rather
than spelled here, and availability is decided by that module's
`ALLOWED_OUTCOMES` — a one-member frozenset containing `clean`. So this corpus
cannot drift out of step with the procedure that produces the outcomes: a
rename there breaks the load here.

`deputy` and `uninspectable` are both denied and are **separately present**,
because FR-056 says they are denied alike and reported differently, and a
corpus carrying one of them cannot tell whether an implementation kept them
distinct.

## The negative control, and the ablation it defeats

**Rule 8**: SC-026's middle clause is *zero become available uninspected*, and
an implementation that makes **nothing** available satisfies it perfectly. On a
corpus made only of additions that ablation scores 100% on all three clauses.

`no-operation-added` is where it fails: three identical republications, zero
newly appearing operations, and every pre-existing operation must stay
available. `add-three-mixed-in-one-fetch` is the second control and a different
one — it puts all three outcomes in a single fetch, so an implementation that
refuses a batch because part of it failed, or admits a batch because part of it
passed, is caught by the same scenario.

`add-one-uninspectable` is not a control but it is the same kind of omission
risk: without it SC-026's third clause — *100% of those that cannot be
inspected are refused* — has an empty denominator and is satisfied by a system
that cannot refuse anything.

## One thing this corpus deliberately does not decide

Whether an operation that inspected `uninspectable` is **re-attempted** on a
later fetch is T153's decision and no scenario here forces it: every operation
appears once and its outcome is recorded once. A fixture that answered it would
be writing a requirement, which is the substitution this repository has a
standing rule against.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from src.analysis.admission import PUBLISHED_NON_EMPTY
from src.analysis.deputy_inspection import ALLOWED_OUTCOMES, OUTCOMES
from tests.fixtures.drift_corpora import CorpusInconsistent

FIXTURES = Path(__file__).resolve().parent.parent
CORPUS_FILE = FIXTURES / "operation-added" / "corpus.json"
SERVED_OPERATIONS_FILE = FIXTURES / "reference-app" / "served_operations.json"


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    deployment_id: str
    last_inspected: frozenset[str]
    fetch_instants: tuple[str, ...]
    fetch_states: tuple[str, ...]
    outcomes: Mapping[str, str]
    newly_appearing_per_fetch: tuple[tuple[str, ...], ...]
    available_at_end: tuple[str, ...]
    refused: tuple[str, ...]
    why: str

    @property
    def is_negative_control(self) -> bool:
        return not any(self.newly_appearing_per_fetch)


def _reject_a_non_published_fetch(entry: Mapping[str, Any]) -> None:
    """SC-026's *continuing to publish throughout*, enforced.

    A non-published fetch makes this `tests/fixtures/spec-withdrawn/`, which is
    T157 and a different criterion.
    """
    for fetch in entry["fetches"]:
        if fetch["state"] != PUBLISHED_NON_EMPTY:
            raise CorpusInconsistent(
                f"{entry['scenario_id']} at {fetch['at']}: state is "
                f"{fetch['state']!r}. SC-026 describes a target that keeps "
                "publishing throughout; a withdrawal here would score SC-026 "
                "on T157's timeline."
            )


def _walk(
    entry: Mapping[str, Any],
) -> tuple[tuple[tuple[str, ...], ...], frozenset[str], frozenset[str]]:
    """Replay the fetches, carrying the inspected set forward.

    Returns the newly-appearing set per fetch, what is available at the end,
    and what was refused. All three are computed; none is read.
    """
    outcomes = entry["inspection_outcomes"]
    inspected = set(entry["last_inspected"])
    available = set(entry["last_inspected"])
    refused: set[str] = set()
    per_fetch: list[tuple[str, ...]] = []

    for fetch in entry["fetches"]:
        fetched = frozenset(fetch["operations"])
        newly_appearing = tuple(sorted(fetched - inspected))
        per_fetch.append(newly_appearing)

        for op_id in newly_appearing:
            if op_id not in outcomes:
                raise CorpusInconsistent(
                    f"{entry['scenario_id']}: {op_id!r} appears at "
                    f"{fetch['at']} and no inspection outcome is declared for "
                    "it. FR-051 fails closed, and a fixture that simply omits "
                    "the outcome would be asserting the open behaviour by "
                    "accident."
                )
            outcome = outcomes[op_id]
            if outcome not in OUTCOMES:
                raise CorpusInconsistent(
                    f"{entry['scenario_id']}: {outcome!r} is not one of "
                    f"FR-056's outcomes {list(OUTCOMES)}"
                )
            inspected.add(op_id)
            if outcome in ALLOWED_OUTCOMES:
                available.add(op_id)
            else:
                refused.add(op_id)

    declared = set(outcomes)
    reached = {op for fetch_ops in per_fetch for op in fetch_ops}
    if declared != reached:
        raise CorpusInconsistent(
            f"{entry['scenario_id']}: outcomes are declared for "
            f"{sorted(declared)} and the fetches newly introduce "
            f"{sorted(reached)}. An outcome for an operation that never "
            "appears is an expectation nothing exercises."
        )

    return tuple(per_fetch), frozenset(available), frozenset(refused)


def load_scenarios() -> tuple[Scenario, ...]:
    """Every scenario, replayed and contradicted where the declaration differs."""
    raw = json.loads(CORPUS_FILE.read_text())["scenarios"]
    scenarios: list[Scenario] = []

    for entry in raw:
        where = entry["scenario_id"]
        _reject_a_non_published_fetch(entry)
        per_fetch, available, refused = _walk(entry)

        declared_per_fetch = tuple(
            tuple(sorted(x)) for x in entry["expected_newly_appearing_per_fetch"]
        )
        if declared_per_fetch != per_fetch:
            raise CorpusInconsistent(
                f"{where}: declares newly appearing "
                f"{[list(x) for x in declared_per_fetch]} per fetch; "
                f"replaying against the last INSPECTED set gives "
                f"{[list(x) for x in per_fetch]}"
            )
        if tuple(sorted(entry["expected_available_at_end"])) != tuple(
            sorted(available)
        ):
            raise CorpusInconsistent(
                f"{where}: declares {sorted(entry['expected_available_at_end'])} "
                f"available at the end; the replay makes {sorted(available)} "
                "available"
            )
        if tuple(sorted(entry["expected_refused"])) != tuple(sorted(refused)):
            raise CorpusInconsistent(
                f"{where}: declares {sorted(entry['expected_refused'])} "
                f"refused; the replay refuses {sorted(refused)}"
            )
        if available & refused:
            raise CorpusInconsistent(
                f"{where}: {sorted(available & refused)} is both available and "
                "refused, which is the state SC-026's middle clause forbids"
            )

        scenarios.append(Scenario(
            scenario_id=where,
            deployment_id=entry["deployment_id"],
            last_inspected=frozenset(entry["last_inspected"]),
            fetch_instants=tuple(f["at"] for f in entry["fetches"]),
            fetch_states=tuple(f["state"] for f in entry["fetches"]),
            outcomes=entry["inspection_outcomes"],
            newly_appearing_per_fetch=per_fetch,
            available_at_end=tuple(sorted(available)),
            refused=tuple(sorted(refused)),
            why=entry["why"],
        ))

    return tuple(scenarios)


def outcomes_exercised() -> frozenset[str]:
    """Which of FR-056's three outcomes any scenario reaches."""
    return frozenset(
        outcome
        for scenario in load_scenarios()
        for outcome in scenario.outcomes.values()
    )


def reference_app_operation_ids() -> frozenset[str]:
    doc = json.loads(SERVED_OPERATIONS_FILE.read_text())
    return frozenset(op["operation_id"] for op in doc["operations"])


def counts() -> Mapping[str, int]:
    """Every figure with its population named, never a bare total."""
    scenarios = load_scenarios()
    additions = [s for s in scenarios if not s.is_negative_control]
    appearing = [
        op for s in scenarios for fetch in s.newly_appearing_per_fetch
        for op in fetch
    ]
    return {
        "scenarios_total": len(scenarios),
        "scenarios_in_which_something_is_added": len(additions),
        "scenarios_in_which_nothing_is_added": len(scenarios) - len(additions),
        "newly_appearing_operation_instances_over_all_scenarios": len(appearing),
        "newly_appearing_instances_refused": sum(
            len(s.refused) for s in scenarios
        ),
        "newly_appearing_instances_admitted_after_a_clean_inspection": (
            len(appearing) - sum(len(s.refused) for s in scenarios)
        ),
        "fr_056_outcomes_exercised_of_three": len(outcomes_exercised()),
        "fetches_over_all_scenarios": sum(
            len(s.fetch_instants) for s in scenarios
        ),
    }
