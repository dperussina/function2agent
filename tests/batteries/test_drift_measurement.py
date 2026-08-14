"""T182 — drift measurement harness, per clock, synthetic only (FR-042, SC-015).

T183's design is `docs/preregistration/drift.md`, pinned here **before**
any rate is asserted. T184's world-property lives on that document.

## What this file reports, and what it must not become

Detection rate, false-alarm rate, and detection latency on the **source**
clock and on the **deployment** clock, separately. The detector is
`clocks.compare` applied to two readings of **one** clock. `compare_each`
is not imported: it requires both clocks, and inventing a reading of the
other so a one-clock measurement could call it would be the fused
artifact T137 made unconstructible arriving as a convenience.

The figures are **synthetic**. E13 never ran. Both clocks have zero live
measurements. SC-021 and SC-026 do not retire that. A report that calls
these live production rates, or that describes drift as a differentiator,
is refused.

Deployment-clock latency uses the corpus's declared `change.at`. Inferring
the change time from first detection would measure the detector against
itself — T184, planted below rather than reasoned about.

## What this file does not do

* T180. The effect-gate oracle is a sibling's file and is unread.
* T185–T188, T214, T215. No `BatteryRun` freeze, no `tick` call from
  `main.py`, no `Result`, no `Registry`.
* Score `FailedRefetch`. That shape has no `version_after` and is FR-047's.
  `PathLevelFailure` is not a `DriftSignal`.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import pytest

from src.analysis.clocks import DEPLOYMENT, SOURCE, Reading, compare, deployment_reading
from src.analysis.source_drift import (
    classify_diff,
    diff_contracts,
    is_breaking,
    source_reading_of,
)
from tests.batteries.evidence import record_evidence
from tests.fixtures.drift_corpora import seconds_between
from tests.fixtures.drift_corpora import deployment as dep
from tests.fixtures.drift_corpora import source as src

REPO = Path(__file__).resolve().parents[2]
THIS = Path(__file__).resolve()
PREREGISTRATION = REPO / "docs" / "preregistration" / "drift.md"

#: Digest of the pre-registration as it stood when this harness was
#: written. Computed over the file bytes, not over a normalised form, so
#: a one-byte edit is a different design. Moving the pin is a new
#: pre-registration and needs a dated entry on the document.
PINNED_PREREGISTRATION_SHA256 = (
    "f1a7bd41f57db2b74064245360368170b27e4b00feb349d9d2edbeabbfddb76f"
)

DEPLOYMENT_ID = "d-reference-app"
ANCHOR = "acme/parts-api@" + "0" * 39 + "a"
SCHEDULED = "scheduled"

REFERENCE_OPS = json.loads(dep.SERVED_OPERATIONS_FILE.read_text())["operations"]
OPS_BY_ID = {op["operation_id"]: op for op in REFERENCE_OPS}


# ---------------------------------------------------------------------------
# Planted flags. Each one is a removal-proof needle. Flipping it is the
# defect the named test exists to catch. Do not "fix" a proof by making
# the flag unused: the test reads the flag, then the behaviour.
# ---------------------------------------------------------------------------

SCORING_WITHOUT_PREREGISTRATION_IS_ALLOWED = False
EDITED_PREREGISTRATION_IS_ACCEPTED = False
COMPARE_EACH_IS_THE_ONE_CLOCK_PATH = False
CLOCKS_ARE_FUSED = False
FIGURES_ARE_LIVE_PRODUCTION_RATES = False
CHANGE_TIME_IS_INFERRED_FROM_FIRST_DETECTION = False
LATENCY_FIGURE_MAY_OMIT_ITS_POPULATION = False
T184_WORLD_PROPERTY_MAY_BE_DROPPED = False
E13_NEVER_RAN = True
FIGURES_ARE_SYNTHETIC = True

#: Populations T183 named before this harness asserted rates. Dropping a
#: row is a latency figure measured on an unnamed set.
NAMED_POPULATIONS = (
    "breaking revisions in tests/fixtures/drift-source",
    "non-breaking revisions in tests/fixtures/drift-source",
    "same check run as the commit",
    "withdrawal scenarios in tests/fixtures/drift-deployment",
    "no-withdrawal scenario",
    "scheduled arm of withdrawal scenarios",
)

T184_SENTENCES = (
    "Deployment-clock latency is measurable on the synthetic corpus because "
    "the corpus controls the change time, and generally not on real traffic "
    "unless the customer emits a deployment event FR-046 says may not be "
    "assumed.",
    "a property of the world, not a gap in the design",
    "Inferring the change time from first observation would measure the "
    "detector against itself.",
)


class PreregistrationError(RuntimeError):
    """Scoring without a live, unedited pre-registration, or a report
    that would state something this design forbids.
    """


@dataclass(frozen=True)
class Design:
    """The pre-registration, loaded and pin-checked before any rate."""

    path: Path
    digest: str
    text: str


@dataclass(frozen=True)
class ClockFigures:
    """One clock's three figures, each with its population attached."""

    clock: str
    synthetic: bool
    live: bool
    detection_rate: float
    detection_n: int
    detection_population: str
    false_alarm_rate: float
    false_alarm_n: int
    false_alarm_population: str
    latency_seconds_mean: float | None
    latency_n: int
    latency_population: str
    latencies: tuple[float, ...]

    def document(self) -> dict[str, Any]:
        return {
            "clock": self.clock,
            "synthetic": self.synthetic,
            "live": self.live,
            "detection_rate": self.detection_rate,
            "detection_n": self.detection_n,
            "detection_population": self.detection_population,
            "false_alarm_rate": self.false_alarm_rate,
            "false_alarm_n": self.false_alarm_n,
            "false_alarm_population": self.false_alarm_population,
            "latency_seconds_mean": self.latency_seconds_mean,
            "latency_n": self.latency_n,
            "latency_population": self.latency_population,
            "latencies": list(self.latencies),
        }


@dataclass(frozen=True)
class Report:
    """Per-clock figures. No fused rate. Not a differentiator claim."""

    design_digest: str
    synthetic: bool
    live: bool
    e13_never_ran: bool
    differentiator_claimed: bool
    by_clock: Mapping[str, ClockFigures]
    fused_detection_rate: float | None

    def document(self) -> dict[str, Any]:
        return {
            "design_digest": self.design_digest,
            "synthetic": self.synthetic,
            "live": self.live,
            "e13_never_ran": self.e13_never_ran,
            "differentiator_claimed": self.differentiator_claimed,
            "fused_detection_rate": self.fused_detection_rate,
            "by_clock": {
                clock: figures.document()
                for clock, figures in self.by_clock.items()
            },
        }


def _ops(ids: list[str] | tuple[str, ...] | frozenset[str]) -> list[dict[str, Any]]:
    return [OPS_BY_ID[i] for i in sorted(ids)]


def _rate(hits: int, n: int) -> float:
    if n == 0:
        raise PreregistrationError(
            "a rate was computed over an empty population. A denominator "
            "of zero is not a rate; it is a figure with no population."
        )
    return hits / n


def load_preregistration(
    path: Path = PREREGISTRATION,
    pinned: str = PINNED_PREREGISTRATION_SHA256,
) -> Design:
    """The design, or a refusal naming why scoring cannot start."""
    if not path.is_file():
        raise PreregistrationError(
            "the pre-registration is missing. FR-042 requires the design "
            "recorded before the measurement runs; scoring without it "
            "would be a rate against nothing."
        )
    text = path.read_text(encoding="utf-8")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != pinned and not EDITED_PREREGISTRATION_IS_ACCEPTED:
        raise PreregistrationError(
            "the pre-registration was edited after the fact. The pin "
            f"is {pinned} and the file hashes to {digest}. A revision "
            "needs a dated entry and a new pin, not a silent edit."
        )
    if not LATENCY_FIGURE_MAY_OMIT_ITS_POPULATION:
        missing = [label for label in NAMED_POPULATIONS if label not in text]
        if missing:
            raise PreregistrationError(
                "a latency or rate figure has no named population: "
                f"{missing}. T183 requires each figure's population "
                "named before the measurement runs."
            )
    if not T184_WORLD_PROPERTY_MAY_BE_DROPPED:
        absent = [sentence for sentence in T184_SENTENCES if sentence not in text]
        if absent:
            raise PreregistrationError(
                "T184's world-property wording is absent: "
                f"{absent}. Inferring the change time from first "
                "observation would measure the detector against itself."
            )
    return Design(path=path, digest=digest, text=text)


def change_time_for(scenario: dep.Scenario, detected_at: str | None) -> str | None:
    """The change instant this design measures latency from.

    The corpus's `change.at` is primary data. Substituting `detected_at`
    is the self-measurement T184 exists to refuse.
    """
    if CHANGE_TIME_IS_INFERRED_FROM_FIRST_DETECTION:
        return detected_at
    return scenario.change_at


def _source_pair(revision: src.Revision) -> tuple[Reading, Reading]:
    parent = {r.revision_id: r for r in src.load_revisions()}[revision.parent]
    before = source_reading_of(
        parent.contract, deployment_id=DEPLOYMENT_ID, source_ref=ANCHOR
    )
    after = source_reading_of(
        revision.contract, deployment_id=DEPLOYMENT_ID, source_ref=ANCHOR
    )
    return before, after


def measure_source(design: Design) -> ClockFigures:
    """Source-clock figures over T154, via `compare` on that clock only."""
    del design  # loaded; the pin already ran
    by_id = {r.revision_id: r for r in src.load_revisions()}
    detections = 0
    detection_n = 0
    false_alarms = 0
    far_n = 0
    latencies: list[float] = []

    for revision in src.load_revisions():
        if revision.parent is None:
            continue
        before, after = _source_pair(revision)
        movement = compare(before, after)
        assert movement.clock == SOURCE
        parent = by_id[revision.parent]
        kinds = classify_diff(
            diff_contracts(parent.contract, revision.contract, revision.renamed)
        )
        breaking = is_breaking(kinds)
        detected = bool(movement.moved) and breaking
        if breaking:
            detection_n += 1
            if detected:
                detections += 1
                # Same check run as the commit: change time is the revision.
                latencies.append(0.0)
        else:
            far_n += 1
            if detected:
                false_alarms += 1

    return ClockFigures(
        clock=SOURCE,
        synthetic=FIGURES_ARE_SYNTHETIC,
        live=FIGURES_ARE_LIVE_PRODUCTION_RATES,
        detection_rate=_rate(detections, detection_n),
        detection_n=detection_n,
        detection_population=NAMED_POPULATIONS[0],
        false_alarm_rate=_rate(false_alarms, far_n),
        false_alarm_n=far_n,
        false_alarm_population=NAMED_POPULATIONS[1],
        latency_seconds_mean=(
            sum(latencies) / len(latencies) if latencies else None
        ),
        latency_n=len(latencies),
        latency_population=NAMED_POPULATIONS[2],
        latencies=tuple(latencies),
    )


def _scheduled_served() -> dict[str, dict[str, list[str]]]:
    """scenario_id → observation instant → served ids, from primary data."""
    raw = json.loads(dep.CORPUS_FILE.read_text())
    out: dict[str, dict[str, list[str]]] = {}
    for entry in raw["scenarios"]:
        out[entry["scenario_id"]] = {
            observation["at"]: list(observation["served"])
            for observation in entry["arms"][SCHEDULED]["observations"]
        }
    return out


def measure_deployment(design: Design) -> ClockFigures:
    """Deployment-clock figures over T155, via `compare` on that clock only."""
    del design
    served_at = _scheduled_served()
    detections = 0
    detection_n = 0
    false_alarms = 0
    far_n = 0
    latencies: list[float] = []

    for scenario in dep.load_scenarios():
        before = deployment_reading(
            deployment_id=scenario.deployment_id,
            operations=_ops(scenario.served_before),
        )
        arm = scenario.arms[SCHEDULED]
        detected_at: str | None = None
        for instant in arm.observation_instants:
            if scenario.change_at is not None:
                if seconds_between(scenario.change_at, instant) < 0:
                    continue
            served = served_at[scenario.scenario_id][instant]
            after = deployment_reading(
                deployment_id=scenario.deployment_id,
                operations=_ops(served),
            )
            movement = compare(before, after)
            assert movement.clock == DEPLOYMENT
            if movement.moved:
                detected_at = instant
                break

        if scenario.is_negative_control:
            far_n += 1
            if detected_at is not None:
                false_alarms += 1
            continue

        detection_n += 1
        if detected_at is not None:
            detections += 1
            change_at = change_time_for(scenario, detected_at)
            if change_at is None:
                raise PreregistrationError(
                    f"{scenario.scenario_id}: a withdrawal has no change "
                    "time, so its latency is undefined rather than zero"
                )
            latencies.append(seconds_between(change_at, detected_at))

    return ClockFigures(
        clock=DEPLOYMENT,
        synthetic=FIGURES_ARE_SYNTHETIC,
        live=FIGURES_ARE_LIVE_PRODUCTION_RATES,
        detection_rate=_rate(detections, detection_n),
        detection_n=detection_n,
        detection_population=NAMED_POPULATIONS[3],
        false_alarm_rate=_rate(false_alarms, far_n),
        false_alarm_n=far_n,
        false_alarm_population=NAMED_POPULATIONS[4],
        latency_seconds_mean=(
            sum(latencies) / len(latencies) if latencies else None
        ),
        latency_n=len(latencies),
        latency_population=NAMED_POPULATIONS[5],
        latencies=tuple(latencies),
    )


def measure(design: Design | None) -> Report:
    """Both clocks, or a refusal. The design must already have been loaded."""
    if design is None and not SCORING_WITHOUT_PREREGISTRATION_IS_ALLOWED:
        raise PreregistrationError(
            "the measurement design was not loaded. FR-042 requires the "
            "design pre-registered before the measurement runs."
        )
    if design is None:
        design = load_preregistration()
    source = measure_source(design)
    deployment = measure_deployment(design)
    fused: float | None = None
    if CLOCKS_ARE_FUSED:
        fused = (source.detection_rate + deployment.detection_rate) / 2
    if fused is not None:
        raise PreregistrationError(
            "a fused source-plus-deployment rate was produced. FR-027 "
            "detects the two clocks separately; a pooled figure is the "
            "fused artifact with the seam drawn in the report."
        )
    if source.live or deployment.live or FIGURES_ARE_LIVE_PRODUCTION_RATES:
        raise PreregistrationError(
            "a live production rate was claimed for a synthetic run. "
            "E13 never ran; both clocks have zero live measurements."
        )
    if not source.synthetic or not deployment.synthetic:
        raise PreregistrationError(
            "a clock's figures are not marked synthetic. This harness "
            "scores committed fixtures and nothing else."
        )
    report = Report(
        design_digest=design.digest,
        synthetic=True,
        live=False,
        e13_never_ran=E13_NEVER_RAN,
        differentiator_claimed=False,
        by_clock={SOURCE: source, DEPLOYMENT: deployment},
        fused_detection_rate=fused,
    )
    record_evidence("drift-measurement", report.document())
    return report


# ---------------------------------------------------------------------------
# T183 / T184 — the design is present, pinned, and names its populations
# before any rate is read.


def test_the_preregistration_exists_and_matches_the_pin() -> None:
    design = load_preregistration()
    assert design.path == PREREGISTRATION
    assert design.digest == PINNED_PREREGISTRATION_SHA256
    assert design.text


def test_a_missing_preregistration_is_refused(tmp_path: Path) -> None:
    """Load-bearing. Scoring without the design is a rate against nothing."""
    assert SCORING_WITHOUT_PREREGISTRATION_IS_ALLOWED is False
    with pytest.raises(PreregistrationError, match="missing"):
        load_preregistration(path=tmp_path / "drift.md")


def test_the_harness_refuses_to_score_without_the_preregistration() -> None:
    assert SCORING_WITHOUT_PREREGISTRATION_IS_ALLOWED is False
    with pytest.raises(PreregistrationError, match="was not loaded"):
        measure(design=None)


def test_an_edited_preregistration_is_refused(tmp_path: Path) -> None:
    """Load-bearing. A silent edit after the pin is a different design."""
    assert EDITED_PREREGISTRATION_IS_ACCEPTED is False
    dest = tmp_path / "drift.md"
    dest.write_text(PREREGISTRATION.read_text(encoding="utf-8") + "\nedited\n")
    with pytest.raises(PreregistrationError, match="edited after the fact"):
        load_preregistration(path=dest)


def test_each_latency_figure_names_its_population() -> None:
    """T183. A figure with no population is the recurring defect."""
    assert LATENCY_FIGURE_MAY_OMIT_ITS_POPULATION is False
    text = PREREGISTRATION.read_text(encoding="utf-8")
    for label in NAMED_POPULATIONS:
        assert label in text, f"population {label!r} is not named on the design"


def test_t184_world_property_is_planted() -> None:
    """T184. The wording is on the document, not reconstructed later."""
    assert T184_WORLD_PROPERTY_MAY_BE_DROPPED is False
    text = PREREGISTRATION.read_text(encoding="utf-8")
    for sentence in T184_SENTENCES:
        assert sentence in text, f"T184 sentence absent: {sentence!r}"


# ---------------------------------------------------------------------------
# T182 — per-clock figures, synthetic, via compare.


def test_the_one_clock_path_is_compare_not_compare_each() -> None:
    assert COMPARE_EACH_IS_THE_ONE_CLOCK_PATH is False
    clocks_import = next(
        line
        for line in THIS.read_text(encoding="utf-8").splitlines()
        if line.startswith("from src.analysis.clocks import")
    )
    assert "compare_each" not in clocks_import, (
        "this harness imported compare_each. A one-clock measurement "
        "uses compare; compare_each requires both clocks."
    )
    assert "compare" in clocks_import


def test_the_clocks_are_not_fused() -> None:
    assert CLOCKS_ARE_FUSED is False
    report = measure(design=load_preregistration())
    assert report.fused_detection_rate is None
    assert SOURCE in report.by_clock
    assert DEPLOYMENT in report.by_clock
    assert report.by_clock[SOURCE].clock == SOURCE
    assert report.by_clock[DEPLOYMENT].clock == DEPLOYMENT
    assert report.differentiator_claimed is False


def test_the_figures_are_synthetic_and_e13_never_ran() -> None:
    assert FIGURES_ARE_SYNTHETIC is True
    assert FIGURES_ARE_LIVE_PRODUCTION_RATES is False
    assert E13_NEVER_RAN is True
    report = measure(design=load_preregistration())
    assert report.synthetic is True
    assert report.live is False
    assert report.e13_never_ran is True
    for figures in report.by_clock.values():
        assert figures.synthetic is True
        assert figures.live is False


def test_source_clock_figures_are_reported_on_the_named_populations() -> None:
    report = measure(design=load_preregistration())
    source = report.by_clock[SOURCE]
    counts = src.counts()
    assert source.detection_n == counts["breaking_revisions"]
    assert source.false_alarm_n == counts["non_breaking_revisions"]
    assert source.detection_rate == 1.0
    assert source.false_alarm_rate == 0.0
    assert source.latency_n == source.detection_n
    assert source.latency_seconds_mean == 0.0
    assert source.latencies == tuple(0.0 for _ in range(source.latency_n))
    assert source.detection_population == NAMED_POPULATIONS[0]
    assert source.false_alarm_population == NAMED_POPULATIONS[1]
    assert source.latency_population == NAMED_POPULATIONS[2]


def test_deployment_clock_figures_are_reported_on_the_named_populations() -> None:
    report = measure(design=load_preregistration())
    deployment = report.by_clock[DEPLOYMENT]
    counts = dep.counts()
    assert deployment.detection_n == counts["scenarios_carrying_a_withdrawal"]
    assert deployment.false_alarm_n == counts["scenarios_with_nothing_withdrawn"]
    assert deployment.detection_rate == 1.0
    assert deployment.false_alarm_rate == 0.0
    expected = tuple(
        sorted(
            s.arms[SCHEDULED].latency_seconds
            for s in dep.load_scenarios()
            if not s.is_negative_control
            and s.arms[SCHEDULED].latency_seconds is not None
        )
    )
    assert tuple(sorted(deployment.latencies)) == expected
    assert deployment.latency_n == len(expected)
    assert deployment.latency_seconds_mean == sum(expected) / len(expected)
    assert deployment.detection_population == NAMED_POPULATIONS[3]
    assert deployment.false_alarm_population == NAMED_POPULATIONS[4]
    assert deployment.latency_population == NAMED_POPULATIONS[5]


def test_deployment_latency_is_not_zero_by_self_measurement() -> None:
    """T184, planted. Inferred change time would make every latency zero."""
    assert CHANGE_TIME_IS_INFERRED_FROM_FIRST_DETECTION is False
    report = measure(design=load_preregistration())
    latencies = report.by_clock[DEPLOYMENT].latencies
    assert latencies
    assert all(latency > 0 for latency in latencies), (
        "a deployment-clock latency of zero on this corpus means the "
        "change time was read off the first detection. Inferring the "
        "change time from first observation would measure the detector "
        "against itself."
    )


def test_the_report_does_not_claim_a_differentiator() -> None:
    report = measure(design=load_preregistration())
    assert report.differentiator_claimed is False
    assert report.live is False
    assert report.synthetic is True
