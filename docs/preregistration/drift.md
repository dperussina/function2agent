# Drift measurement — pre-registered design (FR-042, SC-015)

**Recorded**: 2026-08-14, before any detection rate, false-alarm rate, or
detection latency was asserted by the harness at
`tests/batteries/test_drift_measurement.py`.

**Authority**: FR-042 — *"Before drift detection is described anywhere as a
product differentiator, its detection rate, false-alarm rate and detection
latency MUST be measured on both clocks against a design pre-registered
before the measurement runs."* SC-015 is the report of those three figures
on both clocks against this document.

Nothing below may be revised once the harness has scored a run. A revision
requires a dated entry naming what changed and why, a new pin in the
harness, and a report that states both the pre-registered and the revised
design. Editing this file without moving the pin is refused as
*edited after the fact*. Scoring without this file is refused as *missing*.

This document is **not** a claim that drift detection is a differentiator.
FR-042 forbids that description until the measurement exists; a synthetic
harness is not that measurement on live traffic, so the description stays
forbidden after this run as well.

---

## What is being measured

The detector under test is T137's one-clock `compare`, applied **per clock**,
never `compare_each` as a one-clock convenience.

- **Source clock.** Two `Reading`s of the source clock, `compare(before,
  after)`. A detection is a moved source clock **and** a breaking
  invalidation (FR-028 / T138's kinds). A hash-only move that does not
  invalidate a caller is not a detection; it is the cheap detector T154's
  non-breaking revisions exist to fail.
- **Deployment clock.** Two `Reading`s of the deployment clock,
  `compare(before, after)`. A detection is a moved deployment clock. The
  filter is `Movement.clock`, never `schemas.source_derived` (that flag is
  the union of both clocks). `FailedRefetch` is a `DriftSignal` and is
  **not** scored here — it is FR-047's shape, and E13 never ran.
  `PathLevelFailure` is not a `DriftSignal` and is not scored.

The two clocks are reported separately. A fused rate is not a figure this
design produces.

---

## Populations, named before any rate is asserted

Each latency figure names the population it is measured on. A count with
no population is the recurring defect this repository keeps catching.

| Figure | Clock | Population |
|---|---|---|
| Detection rate | source | **breaking revisions in tests/fixtures/drift-source** — revisions that have a parent and are breaking |
| False-alarm rate | source | **non-breaking revisions in tests/fixtures/drift-source** — revisions that have a parent and are not breaking, including the identical-input revision |
| Detection latency | source | breaking revisions detected in the **same check run as the commit**; the source clock's change time *is* the revision. On real traffic a commit has a timestamp, so source-clock latency is measurable there as well |
| Detection rate | deployment | **withdrawal scenarios in tests/fixtures/drift-deployment** |
| False-alarm rate | deployment | the **no-withdrawal scenario** in that corpus |
| Detection latency | deployment | the **scheduled arm of withdrawal scenarios** only. The no-withdrawal scenario has no latency and is not folded in as zero. The manual arm is a separate population and is not pooled with the scheduled figure |

Denominators follow experiment-design Rule 7: the detection-rate
denominator is the population the instrument could have fired on
(breaking revisions; withdrawal scenarios). The false-alarm-rate
denominator is the complementary quiet population (non-breaking
revisions; the no-withdrawal scenario). The two are not one sentence.

---

## T184 — deployment-clock latency is a property of the world

Deployment-clock latency is measurable on the synthetic corpus because the corpus controls the change time, and generally not on real traffic unless the customer emits a deployment event FR-046 says may not be assumed. That is a property of the world, not a gap in the design. Inferring the change time from first observation would measure the detector against itself.

The synthetic corpus is therefore not a convenience. It is the only
population on which a deployment-clock latency can be computed at all
without a customer-emitted event, and the single property that makes it
one is that `change.at` is primary data. A change time read off the first
observation that saw the change is refused: the corpus already refuses a
declared instant that coincides with any observation, and this design
refuses a harness that would set `change_at = detected_at`.

FR-046's event trigger remains optional and off by default. This design
does not assume it exists.

---

## What this run is, and what it is not

**Synthetic.** Both corpora are committed fixtures. The figures the
harness reports are properties of those fixtures scored through
`compare`. They are not live production rates.

**E13 never ran.** Feature 001's only drift experiment had three named
mutations, all of which move the source, and it never ran at all. Both
clocks have **zero live measurements**. SC-021 and SC-026 score
conformance of an implementation against a fixture derived from the
requirement they name; they do not retire the live-measurement gap and
must not be read as if they did.

**FR-047 is not this measurement.** A failed re-fetch has no
`version_after` and no controlled change time on real traffic. Folding
`FailedRefetch` into these rates would score a different condition on a
population this design did not name.

**Not a differentiator.** A perfect score on a synthetic corpus whose
change times the authors control is the expected reading of a detector
built against that corpus. It is not evidence that drift detection
discriminates on live traffic, and it is not permission to describe it
as a product differentiator.

---

## Kill criteria (stop, not investigate)

Written before the harness asserts rates, so they cannot be moved after
seeing them.

1. A fused source-plus-deployment rate is reported → the report is
   refused. The clocks stay separate.
2. A live or production rate is claimed for a synthetic run → the report
   is refused.
3. Deployment-clock latency is computed from a change time equal to the
   first detection → the report is refused. That is the detector scored
   against itself.
4. Either clock's latency figure has no named population → the report is
   refused.
5. The pre-registration file is missing, or its digest no longer matches
   the pin recorded in the harness before this run → scoring is refused.

No threshold in this document converts a synthetic score into a
differentiator claim. Inventing one here would be the inherited-number
failure arriving by a new door.
