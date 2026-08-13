"""T156 — SC-029's second clause: re-analysing unchanged source raises zero
source-clock drift signals.

**Criterion**: SC-029 — *"Analysing one committed fixture twice from unchanged
input produces byte-identical payloads for 100% of the artifact kinds FR-054
enumerates, and therefore zero content addresses that differ between the two
runs; across a drift battery in which source is held constant and only
re-analysis is repeated, **zero** source-clock drift signals are raised."*

The first clause is T012 (`tests/contract/test_canonical_determinism.py`),
which compares **payload bytes**, not addresses. This file is the second
clause: the drift-signal consequence of that byte identity. If re-analysis of
unchanged source raises a source-clock signal, T010 did not close the
false-alarm channel FR-055 named, and that is a finding, not a test to weaken.

## Why this is not C-008

C-008 is one identical-input revision inside T154's SC-008 population, so that
population is not made exclusively of revisions where something moved. Scoring
C-008 quiet proves the detector does not fire on that one pair. This battery
repeats re-analysis of held-constant *source* — the analyzer fixture, derived
and wrapped as the artifacts the source clock actually reads — and scores the
source-clock signal count over those repetitions.

## Why the repetitions are more than two, and why two in-process is not enough

T012 records that a serializer stable only within a process produces identical
addresses in a single test run and different ones across restarts:
`PYTHONHASHSEED` randomizes string hashing, so set iteration and hash-derived
dict ordering differ between subprocesses. Comparing two in-process derivations
would hide exactly the serializer that breaks the drift detector.

So this battery takes two readings:

1. **In-process, twice.** The minimum that can produce a signal (one
   comparison). Asserted so a cheap detector that stamps a run index into the
   version is known to fire — Rule 8, in this file, not as a comment.
2. **Across processes, with distinct hash seeds.** The arm that would catch a
   serializer T012's in-process clause cannot see. The detector is scored on
   the readings those processes produce, not on their payload bytes: T012
   already compared bytes; this is the signal.

## The cheap detector this file fails

`_analysis_ran_therefore_moved` mixes the run index into the after version, so
it raises a source-clock signal on every re-analysis by construction. If the
battery's "zero signals" assertion could pass for a detector that fires on
every run, this arm would still be red. That is the same shape T154's tests
use against the source corpus.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping

from src.analysis.clocks import DEPLOYMENT, SOURCE, deployment_reading, reading
from src.analysis.derive import derive_module
from src.analysis.drift_signal import ArtifactDrift, signals_from_movements
from src.analysis.source_drift import detect, source_movements_of, source_reading_of
from src.contracts.canonical import content_address
from src.contracts.envelope import wrap

REPO = Path(__file__).resolve().parents[2]
FIXTURE = REPO / "tests" / "fixtures" / "analyzer" / "inventory-service" / "service.py"

DEPLOYMENT_ID = "d-reference-app"
ANCHOR = "acme/parts-api@" + "0" * 39 + "a"

OPERATIONS = [
    {"operation_id": "stock_report", "method": "GET", "path_template": "/stock"},
]


def _analyse() -> tuple[dict[str, Any], dict[str, Any]]:
    """One derivation of the held-constant fixture, wrapped as the artifacts
    the source clock reads.

    Wrapping is the analysis pipeline's address, not a shortcut around it:
    T010's canonical form and T011's envelope are what FR-055 closed the
    false-alarm channel with, and SC-029's second clause is the proof they
    actually closed it.
    """
    derived = derive_module(FIXTURE, relative_to=FIXTURE.parent)
    contracts: dict[str, Any] = {}
    checks: dict[str, Any] = {}
    for contract in derived:
        wrapped = wrap(
            "derived_contract",
            contract.to_document(deployment_id=DEPLOYMENT_ID),
        )
        contracts[contract.operation_id] = dict(wrapped.payload)
        for check in contract.checks:
            check_wrapped = wrap(
                "derived_check",
                check.to_document(deployment_id=DEPLOYMENT_ID),
            )
            checks[f"{check.operation_id}/{check.quantity}"] = dict(
                check_wrapped.payload
            )
    assert contracts, "the fixture derived nothing; the battery would be vacuous"
    assert checks, (
        "the fixture derived no checks; a source clock read over contracts "
        "alone is the subset T137 refuses, and a battery that skipped checks "
        "would not be reading the clock FR-028 reads"
    )
    return contracts, checks


def _readings(
    contracts: Mapping[str, Any], checks: Mapping[str, Any]
) -> dict[str, Any]:
    return {
        SOURCE: source_reading_of(
            contracts,
            deployment_id=DEPLOYMENT_ID,
            source_ref=ANCHOR,
            checks=checks,
        ),
        DEPLOYMENT: deployment_reading(
            deployment_id=DEPLOYMENT_ID, operations=OPERATIONS
        ),
    }


def _source_signals(before: Mapping[str, Any], after: Mapping[str, Any]):
    return signals_from_movements(source_movements_of(before, after))


def _analysis_ran_therefore_moved(
    run_index: int, contracts: Mapping[str, Any], checks: Mapping[str, Any]
) -> str:
    """Cheap detector: every re-analysis is a new version because it ran.

    Mixes the run index into the address so it false-alarms on the second
    observation by construction, even when T010's serializer is canonical.
    """
    return content_address(
        {"run": run_index, "contracts": dict(contracts), "checks": dict(checks)}
    )


def test_reanalysis_of_unchanged_source_raises_zero_source_clock_signals() -> None:
    contracts_a, checks_a = _analyse()
    contracts_b, checks_b = _analyse()
    first = _readings(contracts_a, checks_a)
    second = _readings(contracts_b, checks_b)

    signals = _source_signals(first, second)
    assert signals == (), (
        f"re-analysis of unchanged source raised {len(signals)} source-clock "
        "signal(s). T010 did not close the false-alarm channel FR-055 named."
    )
    assert detect(
        first,
        second,
        before_contracts=contracts_a,
        after_contracts=contracts_b,
    ) is None

    for movement in source_movements_of(first, second):
        assert movement.clock == SOURCE
        assert not movement.moved
        assert movement.version_before == movement.version_after


def test_the_cheap_detector_that_fires_because_analysis_ran_fails_this_battery() -> None:
    """Rule 8. If this passes, 'zero signals' is not discriminating."""
    contracts, checks = _analyse()
    first_addr = _analysis_ran_therefore_moved(0, contracts, checks)
    second_addr = _analysis_ran_therefore_moved(1, contracts, checks)
    assert first_addr != second_addr, (
        "the cheap detector produced the same address on two runs, so it "
        "cannot fail the battery and the negative control is decorative"
    )

    genuine = dict(_readings(contracts, checks)[SOURCE].versions)
    before = {
        SOURCE: reading(
            SOURCE,
            deployment_id=DEPLOYMENT_ID,
            versions={
                "derived_contract": first_addr,
                "derived_check": genuine["derived_check"],
            },
            source_ref=ANCHOR,
        ),
        DEPLOYMENT: deployment_reading(
            deployment_id=DEPLOYMENT_ID, operations=OPERATIONS
        ),
    }
    after = {
        SOURCE: reading(
            SOURCE,
            deployment_id=DEPLOYMENT_ID,
            versions={
                "derived_contract": second_addr,
                "derived_check": genuine["derived_check"],
            },
            source_ref=ANCHOR,
        ),
        DEPLOYMENT: before[DEPLOYMENT],
    }
    cheap_signals = _source_signals(before, after)
    assert cheap_signals, (
        "the cheap detector did not raise a source-clock signal, so a "
        "battery asserting zero signals cannot fail it"
    )
    assert all(isinstance(s, ArtifactDrift) for s in cheap_signals)
    assert all(s.clock == SOURCE for s in cheap_signals)


def test_reanalysis_across_hash_seeds_raises_zero_source_clock_signals() -> None:
    """The arm T012's in-process clause cannot see.

    Two subprocesses, distinct `PYTHONHASHSEED` values, each derives and wraps
    the same fixture. The readings those processes produce are compared here;
    a serializer that depends on hash-derived ordering moves the source clock
    between them.
    """
    script = r"""
import json, sys
sys.path.insert(0, %r)
from tests.batteries.test_drift_negative import _analyse, _readings, SOURCE
contracts, checks = _analyse()
readings = _readings(contracts, checks)
sys.stdout.write(json.dumps({
    "contracts": contracts,
    "checks": checks,
    "source_version": readings[SOURCE].version,
    "source_versions": dict(readings[SOURCE].versions),
}))
""" % str(REPO)

    def run(seed: str) -> dict[str, Any]:
        env = {**os.environ, "PYTHONHASHSEED": seed, "PYTHONPATH": str(REPO)}
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            env=env,
            cwd=str(REPO),
            text=True,
        )
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)

    first, second = run("0"), run("1")
    assert first["source_version"] == second["source_version"], (
        "source-clock versions differ between PYTHONHASHSEED=0 and 1. "
        "T010 is stable within a process and unstable across restarts, "
        "which is the false-alarm channel SC-029's second clause exists to "
        "catch."
    )
    assert first["source_versions"] == second["source_versions"]

    before = _readings(first["contracts"], first["checks"])
    after = _readings(second["contracts"], second["checks"])
    assert _source_signals(before, after) == ()
    assert detect(
        before,
        after,
        before_contracts=first["contracts"],
        after_contracts=second["contracts"],
    ) is None
