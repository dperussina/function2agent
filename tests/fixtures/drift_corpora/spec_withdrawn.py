"""T157 — withdrawing an admitted target's published specification, and restoring it.

The corpus is `tests/fixtures/spec-withdrawn/corpus.json`; this module loads it.
**Criterion**: **SC-021** — *"On a fixture that withdraws an admitted target's
published specification and later restores it, **100%** of results returned
while the served-operation set is stale carry a machine-readable stale marking
with the set's age; **zero** calls are served after the configured staleness
ceiling elapses; **zero** sessions end in a generic error at the ceiling; and
**100%** of the operations that differ between the last-known-good set and the
restored set are reported as drift rather than adopted silently."*

## ⚠️ SC-021 IS NOT THE MEASUREMENT AND MUST NOT BE READ AS IT

This is the first thing to know about this directory, and it is quoted rather
than paraphrased. [`specs/002-spec-aware-agent-runtime/plan.md`](../../../specs/002-spec-aware-agent-runtime/plan.md)
line 831, third column:

> **SC-021 is not the measurement and must not be read as it.** It scores an
> implementation's conformance to FR-047 against a fixture derived from FR-047
> — a conformance test, not evidence the disposition is right. Calling it
> coverage would be the substitution this corpus has caught repeatedly.
> Manufacturing the corpus here is worse than absent: any withdrawal schedule
> we invent would encode the transient-versus-permanent ratio the measurement
> exists to discover.

The same row's first column states the gap this fixture does **not** close:

> **FR-047 ships unmeasured — no experiment has ever run the scenario it
> governs.** [...] **E13 never ran at all.** So FR-047's disposition (serve the
> last-known-good set marked stale, deny past the ceiling), its fifteen-minute
> ceiling, and its deployment-clock detection latency all ship with **zero**
> supporting evidence.

[`specs/001-discovery-validation/VERDICT.md`](../../../specs/001-discovery-validation/VERDICT.md)
line 162 says the same of the capability: drift detection has *"no detection
rate, no false-alarm rate, no latency to detect, **on either of its two
clocks**"*. Both clocks. Zero measurements.

**What this fixture is**: the committed artifact FR-053 requires alongside the
capability, and the thing SC-021 will be scored on. **What it is not**:
evidence that serving a last-known-good set marked stale is the right
disposition, or that 900 seconds is the right ceiling. The deciding quantity —
how often a published specification stops being reachable *transiently* rather
than permanently — is a property of real deployments and real networks, plan.md
says it cannot be manufactured here, and the obligation is deferred to
production. The withdrawal schedule below is **invented**, deliberately, and it
encodes no claim about that ratio.

## The ceiling is wall clock from the last successful fetch

T149's wording, and `_age_at` implements it: the age of a call is
`call - last successful fetch at or before it`, never `call - the moment
staleness was entered`. The difference is the whole of T149 — measuring from
entry means lengthening the re-fetch interval silently widens the ceiling.

Every declared `age_seconds`, every `stale` flag and every `served` flag is
**recomputed** from the fetch timeline and contradicted on disagreement. The
declarations are here to be checked, not read.

## The terminal state SC-021's third clause needs does not exist yet

`src/contracts/terminal.py` is a **closed** taxonomy of twelve members, guarded
by `tests/invariants/test_terminal_taxonomy.py`, and **not one of them names
the staleness ceiling**. T150 requires an in-flight session past the ceiling to
end in a named terminal state rather than by generic error; the name it will
need is not in the taxonomy at the time this fixture was committed.

So `withdraw-past-ceiling` declares `expected_terminal_state: null` and asserts
only the negative — that the session must not end generically — and
`tests/unit/test_drift_fixtures.py::test_the_taxonomy_still_has_no_staleness_terminal_state`
asserts the absence itself. The day T150 adds the member, that test fails and
this paragraph has to move. A gap stated in prose goes stale; this one is
wired to a failure.

`_reject_undeclared_terminal_state` refuses any non-null name that is not
already a taxonomy member, so a future edit cannot smuggle one in through the
corpus.

## The two negative controls, and the ablations they defeat

**Rule 8** of the experiment-design skill: a fixture whose positive result is a
failure signal needs a negative control, and a perfect ablation score is the
tell that one is missing. SC-021's four clauses are all *100%* or *zero*, which
is exactly that shape.

| Control | Clause it protects | Ablation it defeats |
|---|---|---|
| `never-withdrawn` | first — *100% of results while stale* | an implementation marking **every** result stale. Its denominator here is zero and it must produce zero markings |
| `withdraw-restore-identical-below-ceiling` | fourth — *100% of differing operations reported as drift* | an implementation reporting drift on **every** restoration. Zero operations differ, so zero drift is the only correct answer |

Without the first, *100% of stale results carry a marking* is satisfied by
marking everything. Without the second, *100% of differing operations are
reported* is satisfied by reporting everything.

## All three non-admissible states, because T147 names three

T147 enters the stale state on *"the first re-fetch returning any of FR-044's
three non-admissible states"*. A corpus exercising only `absent` leaves two of
the three unexercised, so the scenarios use `absent`,
`unreadable_by_credential` and `readable_no_operations`, and
`non_admissible_states_exercised()` reports which — with the population named.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from src.analysis.admission import (
    ABSENT,
    PUBLISHED_NON_EMPTY,
    READABLE_NO_OPERATIONS,
    UNREADABLE_BY_CREDENTIAL,
)
from src.contracts import terminal
from tests.fixtures.drift_corpora import (
    CorpusInconsistent,
    instant,
    seconds_between,
)

FIXTURES = Path(__file__).resolve().parent.parent
CORPUS_FILE = FIXTURES / "spec-withdrawn" / "corpus.json"
SERVED_OPERATIONS_FILE = FIXTURES / "reference-app" / "served_operations.json"

#: FR-044's three non-admissible states, named from `src/analysis/admission.py`
#: rather than spelled here, so a rename in the classifier breaks this rather
#: than leaving a fixture describing states that no longer exist.
NON_ADMISSIBLE_STATES = frozenset({
    ABSENT, UNREADABLE_BY_CREDENTIAL, READABLE_NO_OPERATIONS,
})


@dataclass(frozen=True)
class Call:
    """One call, with age, staleness and disposition all recomputed."""

    at: str
    operation_id: str
    served: bool
    stale: bool
    age_seconds: float
    specification_state_last_found: str


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    deployment_id: str
    last_known_good: frozenset[str]
    restored_at: str | None
    restored_set: frozenset[str] | None
    drift_on_restore: tuple[str, ...] | None
    calls: tuple[Call, ...]
    fetch_instants: tuple[str, ...]
    fetch_states: tuple[str, ...]
    expected_terminal_state: str | None
    why: str


def staleness_ceiling_seconds() -> int:
    return json.loads(CORPUS_FILE.read_text())["configured"][
        "staleness_ceiling_seconds"
    ]


def _last_successful_fetch_at_or_before(
    fetches: list[Mapping[str, Any]], when: str
) -> Mapping[str, Any]:
    """T149's anchor: the last fetch that actually succeeded, not the last try."""
    moment = instant(when)
    candidates = [
        f for f in fetches
        if instant(f["at"]) <= moment and f["state"] == PUBLISHED_NON_EMPTY
    ]
    if not candidates:
        raise CorpusInconsistent(
            f"no successful fetch precedes {when!r}; a scenario must be "
            "admitted before its specification can be withdrawn"
        )
    return max(candidates, key=lambda f: instant(f["at"]))


def _last_fetch_at_or_before(
    fetches: list[Mapping[str, Any]], when: str
) -> Mapping[str, Any]:
    moment = instant(when)
    candidates = [f for f in fetches if instant(f["at"]) <= moment]
    if not candidates:
        raise CorpusInconsistent(f"no fetch precedes {when!r}")
    return max(candidates, key=lambda f: instant(f["at"]))


def _reject_undeclared_terminal_state(name: str | None, where: str) -> None:
    """A terminal state this corpus names must already be in the taxonomy.

    FR-006 forbids a generic error, and `src/contracts/terminal.py` says
    membership is closed. A fixture is not a place to open it.
    """
    if name is None:
        return
    if name not in terminal.NAMES:
        raise CorpusInconsistent(
            f"{where}: {name!r} is not in the declared terminal-state "
            "taxonomy. FR-006 requires a named member; a fixture may not "
            "introduce one — add it to src/contracts/terminal.py under the "
            "task that owns it (T150) and the invariant test will notice."
        )


def load_scenarios() -> tuple[Scenario, ...]:
    """Every scenario, with age, staleness and disposition all recomputed."""
    raw = json.loads(CORPUS_FILE.read_text())["scenarios"]
    ceiling = staleness_ceiling_seconds()
    scenarios: list[Scenario] = []

    for entry in raw:
        where = entry["scenario_id"]
        fetches = entry["fetches"]
        last_known_good = frozenset(entry["last_known_good"])

        session = entry.get("in_flight_session_at_ceiling")
        expected_terminal = (
            session.get("expected_terminal_state") if session else None
        )
        _reject_undeclared_terminal_state(expected_terminal, where)

        calls: list[Call] = []
        for call in entry["calls"]:
            anchor = _last_successful_fetch_at_or_before(fetches, call["at"])
            age = seconds_between(anchor["at"], call["at"])
            latest = _last_fetch_at_or_before(fetches, call["at"])
            stale = latest["state"] != PUBLISHED_NON_EMPTY
            served = (not stale) or age < ceiling

            if age != call["age_seconds"]:
                raise CorpusInconsistent(
                    f"{where} at {call['at']}: declares an age of "
                    f"{call['age_seconds']} s; wall clock from the last "
                    f"successful fetch at {anchor['at']} is {age} s"
                )
            if age == ceiling:
                raise CorpusInconsistent(
                    f"{where} at {call['at']}: an age of exactly the ceiling "
                    "has no stated disposition. T149 and T150 own that "
                    "boundary and a fixture may not decide it."
                )
            if stale != call["stale"]:
                raise CorpusInconsistent(
                    f"{where} at {call['at']}: declares stale="
                    f"{call['stale']}; the last fetch at or before it "
                    f"returned {latest['state']!r}"
                )
            if served != call["served"]:
                raise CorpusInconsistent(
                    f"{where} at {call['at']}: declares served="
                    f"{call['served']}; stale={stale} at age {age} s against "
                    f"a ceiling of {ceiling} s recomputes to {served}"
                )
            if latest["state"] != call["specification_state_last_found"]:
                raise CorpusInconsistent(
                    f"{where} at {call['at']}: declares the last state found "
                    f"as {call['specification_state_last_found']!r}; the last "
                    f"fetch returned {latest['state']!r}"
                )

            calls.append(Call(
                at=call["at"],
                operation_id=call["operation_id"],
                served=served,
                stale=stale,
                age_seconds=age,
                specification_state_last_found=latest["state"],
            ))

        restored_at = entry["restored_at"]
        restored_set: frozenset[str] | None = None
        drift: tuple[str, ...] | None = None
        if restored_at is not None:
            matches = [
                f for f in fetches
                if f["at"] == restored_at and f["state"] == PUBLISHED_NON_EMPTY
            ]
            if not matches:
                raise CorpusInconsistent(
                    f"{where}: restored_at {restored_at!r} names no successful "
                    "fetch"
                )
            restored_set = frozenset(matches[0]["operations"])
            drift = tuple(sorted(last_known_good ^ restored_set))

        if drift != (
            tuple(sorted(entry["expected_drift_on_restore"]))
            if entry["expected_drift_on_restore"] is not None else None
        ):
            raise CorpusInconsistent(
                f"{where}: declares drift on restore "
                f"{entry['expected_drift_on_restore']!r}; the symmetric "
                f"difference of the last-known-good and restored sets is "
                f"{list(drift) if drift is not None else None}"
            )

        scenarios.append(Scenario(
            scenario_id=where,
            deployment_id=entry["deployment_id"],
            last_known_good=last_known_good,
            restored_at=restored_at,
            restored_set=restored_set,
            drift_on_restore=drift,
            calls=tuple(calls),
            fetch_instants=tuple(f["at"] for f in fetches),
            fetch_states=tuple(f["state"] for f in fetches),
            expected_terminal_state=expected_terminal,
            why=entry["why"],
        ))

    return tuple(scenarios)


def non_admissible_states_exercised() -> frozenset[str]:
    """Which of FR-044's three non-admissible states any scenario reaches."""
    return frozenset(
        state
        for scenario in load_scenarios()
        for state in scenario.fetch_states
        if state in NON_ADMISSIBLE_STATES
    )


def taxonomy_names_the_staleness_ceiling() -> bool:
    """Whether any declared terminal state names staleness. False at T157.

    Asserted false by `tests/unit/test_drift_fixtures.py`. When T150 adds the
    member, that assertion fails, which is the point: the note in this module's
    docstring and in the corpus is then wrong and has to move.
    """
    return any(
        "stale" in name or "staleness" in state.meaning.lower()
        for name, state in terminal.BY_NAME.items()
    )


def reference_app_operation_ids() -> frozenset[str]:
    doc = json.loads(SERVED_OPERATIONS_FILE.read_text())
    return frozenset(op["operation_id"] for op in doc["operations"])


def counts() -> Mapping[str, int]:
    """Every figure with its population named, never a bare total."""
    scenarios = load_scenarios()
    all_calls = [c for s in scenarios for c in s.calls]
    stale_calls = [c for c in all_calls if c.stale]
    restorations = [s for s in scenarios if s.restored_at is not None]
    return {
        "scenarios_total": len(scenarios),
        "scenarios_in_which_the_specification_is_withdrawn": sum(
            1 for s in scenarios
            if any(st in NON_ADMISSIBLE_STATES for st in s.fetch_states)
        ),
        "scenarios_in_which_it_is_never_withdrawn": sum(
            1 for s in scenarios
            if not any(st in NON_ADMISSIBLE_STATES for st in s.fetch_states)
        ),
        "scenarios_reaching_a_restoration": len(restorations),
        "restorations_whose_set_is_unchanged": sum(
            1 for s in restorations if not s.drift_on_restore
        ),
        "calls_over_all_scenarios": len(all_calls),
        "calls_made_while_the_set_is_stale": len(stale_calls),
        "stale_calls_denied_past_the_ceiling": sum(
            1 for c in stale_calls if not c.served
        ),
        "non_admissible_states_exercised_of_the_three_fr_044_names": len(
            non_admissible_states_exercised()
        ),
    }
