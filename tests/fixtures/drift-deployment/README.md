# T155 — the deployment-change synthetic corpus

**Task**: T155. **Criteria**: SC-009 and **SC-020**.

- **SC-009** — *"**100%** of operations withdrawn by the deployment in a
  synthetic deployment-drift corpus are detected and disabled, and **zero**
  unaffected operations are disabled alongside them."*
- **SC-020** — *"On the synthetic deployment-drift corpus, **100%** of withdrawn
  operations are detected within the configured detection window under the
  default automated trigger and with no event supplied by a deployment pipeline,
  and **100%** are detected on demand under manual invocation."*

| File | What it holds |
| --- | --- |
| `corpus.json` | Five scenarios, each with a declared change time and two arms |
| `../drift_corpora/deployment.py` | The loader and the latency recomputation |
| `../../unit/test_drift_fixtures.py` | The asserted expected output |

## Why this corpus exists, which is a fact about the world rather than a convenience

[`plan.md` line 830](../../../specs/002-spec-aware-agent-runtime/plan.md),
Complexity Tracking:

> **Deployment-clock drift latency is not measurable on real traffic** unless
> the customer emits a deployment event, which FR-046 says may not be assumed |
> A property of the world: a deployment change generally has no observable
> change time. Measurable on the committed synthetic corpus, which controls the
> change time, and on real traffic only where the optional trigger exists |
> Inferring the change time from first observation measures the detector against
> itself

So this is **the only population on which a deployment-clock latency can be
computed at all**, and the single property that makes it one is that
`change.at` is primary data rather than something read off an observation.

## The mechanical form of *not derived from an observation*

Prose claiming the change time is controlled is worth nothing. A corpus author
under time pressure sets it equal to the first observation that saw the change,
and every latency in the file still divides cleanly.

`_reject_change_time_read_off_an_observation` refuses that outright: **a
declared change instant may not coincide with any observation instant in any arm
of its scenario.** A change time strictly between two observations cannot have
been read off either of them.

Two tests hold it — `test_no_declared_change_time_coincides_with_an_observation`
reads the committed payload directly, and
`test_a_change_time_read_off_an_observation_is_refused` **plants** a coincident
instant and asserts the loader raises. The second one exists because reading a
guard's source shows what its author intended to cover, which is exactly the
thing in question whenever a gap is suspected.

The latency itself is arithmetic the loader performs — first observation at or
after the change whose served set is missing a withdrawal, minus the declared
change time — and the committed figure is contradicted rather than read.
`test_a_declared_latency_that_disagrees_with_the_clock_is_refused` plants a
wrong one.

## No deployment-pipeline event, and that is asserted

`deployment_events` is `[]`. SC-020 requires detection *with no event supplied
by a deployment pipeline*, and FR-046 says such an event may not be assumed
available. An event added here would make every latency below trivial and would
quietly convert this corpus into a measurement of the one channel the
requirement forbids relying on.
`test_the_corpus_supplies_no_event_from_a_deployment_pipeline` keeps it empty.

## What the scheduled arm cannot falsify, stated rather than left to be found

The configured poll interval is **300 s** and the configured detection window is
**900 s**. Both are defaults marked unvalidated under FR-043; neither has a
measurement behind it.

Because the interval is smaller than the window, the scheduled arm's latency is
bounded above by the interval and **satisfies SC-020's window clause by
construction** on every scenario here. The worst scheduled latency in the corpus
is **230 s**, over the four withdrawal scenarios — the negative control has no
latency and is not folded in as a zero.

That margin is arithmetic on two configured numbers, **not a result**. SC-020's
window clause is not falsifiable on this corpus through the scheduled arm alone,
and `test_the_scheduled_windows_margin_is_a_property_of_the_interval` asserts
the relationship so that widening the interval past the window cannot be a
silent change.

## The population, with its denominator attached

`deployment.counts()` reports:

- **5** scenarios total: **4** carrying a withdrawal, **1** with nothing
  withdrawn;
- **4** distinct operations withdrawn across the 4 withdrawal scenarios, in **8**
  withdrawn-operation instances;
- **23** observations over all 5 scenarios and both arms.

`test_every_total_is_partitioned_by_a_breakdown_that_sums_to_it` asserts the 4
and the 1 add to the 5.

## The two negative controls, and the ablations they defeat

**Rule 8**: both criteria are *100% of withdrawn operations*, and a detector
that disables the whole target on every poll scores perfectly on a corpus made
only of withdrawals.

| Control | Ablation it defeats |
| --- | --- |
| `no-withdrawal` — nothing withdrawn across four polls and a manual check | *disable the target on every poll* |
| `withdraw-one-of-two-neighbours` — `list_shipments` goes, `list_parts` stays | *match on a name prefix or a path stem* |

The second is SC-009's *zero unaffected operations are disabled* clause given
something it could plausibly take down by mistake. Without a confusable
neighbour in the corpus, that clause passes for a detector with no precision at
all. `test_a_detector_that_disables_the_target_on_every_poll_fails_this_corpus`
runs the ablation against the real population.

## Both of SC-020's arms, on every scenario

SC-020 has a clause for the default automated trigger and a separate one for
manual invocation. Every scenario carries both as independent observation
series over the same declared change, so neither clause is scored over nothing.
The loader refuses a scenario missing an arm.

## This corpus does not withdraw the specification

Every observation reports `published_non_empty`. The deployment here stops
serving **operations** while continuing to publish its specification;
withdrawing the document is T157 at `tests/fixtures/spec-withdrawn/`, and it
scores SC-021.
`test_the_deployment_corpus_never_stops_publishing_its_specification` keeps the
two apart.

## ⚠️ The measurement this is not

[`VERDICT.md` line 162](../../../specs/001-discovery-validation/VERDICT.md):
drift detection has *"no detection rate, no false-alarm rate, no latency to
detect, **on either of its two clocks**"*. Both clocks, zero measurements.
[`plan.md` line 831](../../../specs/002-spec-aware-agent-runtime/plan.md)
records that E13, feature 001's only drift experiment, **never ran at all** and
had no deployment-drift arm in any case.

The latencies above are intervals between two instants **this corpus declares**.
They are properties of the fixture, not of a detector: T141 through T146 — the
scheduler, the manual trigger and the disable path SC-009 and SC-020 score — are
all open. Nothing here retires the gap.

## This file is not gated

`tools/corpuscheck/config.json` does not walk `tests`, so
`tools/check_corpus.py` never reads this file. Every load-bearing claim above is
recomputed by the loader or asserted in
`tests/unit/test_drift_fixtures.py`, including the 230 s figure, the interval
relationship, the empty event list, and both ablations.
