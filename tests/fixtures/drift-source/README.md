# T154 — the source-change synthetic corpus

**Task**: T154. **Requirement**: FR-053. **Criterion**: SC-008 — *"**100%** of
breaking source-contract changes in a synthetic drift corpus are detected in the
same automated check run as the commit that introduced them."*

| File | What it holds |
| --- | --- |
| `corpus.json` | Eleven revisions, each carrying its **full** contract |
| `../drift_corpora/source.py` | The loader, the diff, and the recomputation |
| `../../unit/test_drift_fixtures.py` | The asserted expected output FR-053 requires |

The loader is not in this directory because a hyphen is not a Python
identifier, so `drift-source` cannot be a package. That is the same arrangement
`tests/fixtures/value-faults/` already uses.

## What controls the change time, because the source clock has no wall clock

`tests/fixtures/drift-deployment/` has to manufacture a wall-clock change time.
This corpus does not need one: on the source clock the change **is** the
revision. What it controls instead is the binding SC-008 depends on — exactly
one check run per revision, enforced by `_check_run_bijection` and asserted by
`test_a_check_run_observing_two_revisions_is_refused`.

The moment one run is allowed to observe a range of revisions, *"the same run
as the commit"* is true of any detection inside that window and the criterion
can no longer fail.

## Nothing declared here is the oracle

Every revision carries its whole contract rather than a patch, so the loader can
**diff** a revision against its parent and recompute all four declared fields:
the change kinds, the breaking verdict, the drifted operations, and the run
detection is owed in. A disagreement raises `CorpusInconsistent` at load time.

This is not a precaution. Writing the corpus produced one real disagreement —
`C-003` declared both sides of a rename as drifted while the diff named only
the new one — and the recomputation caught it before the file was committed. A
committed expectation nobody recomputes is a number, and numbers nobody
recomputed are what this repository keeps finding.

## The population, with its denominator attached

`source.counts()` reports, and no figure here is quoted without the population
it is over:

- **11** revisions total, of which **1** is the base revision and can carry no
  diff at all;
- **10** revisions with a parent and therefore scoreable;
- **6** of those 10 breaking, **4** non-breaking;
- **1** of the 4 carries a contract byte-identical to its parent;
- **6** distinct breaking change kinds exercised.

`test_every_total_is_partitioned_by_a_breakdown_that_sums_to_it` asserts the
6 and the 4 add to the 10 rather than to the 11. A subset presented as a total
is this repository's recurring defect and the partition is the guard against it.

## The four non-breaking revisions are the instrument

The experiment-design skill's **Rule 8**: a fixture whose positive result is a
failure signal needs a negative control, and *the tell that one is missing is a
perfect score on an ablation suite*. SC-008 is a **100%** detection figure, so a
detector that reports drift on every revision scores perfectly on a corpus made
only of breaking changes.

Each control defeats a different cheap detector, and they are not
interchangeable:

| Revision | Change | Cheap detector it defeats |
| --- | --- | --- |
| `C-005` | optional parameter added | *the signature is not byte-identical* |
| `C-006` | operation added | *the operation set changed* |
| `C-007` | summary changed | *the contract document's hash changed* |
| `C-008` | nothing — identical contract | *analysis ran, therefore something moved* |

`test_a_detector_that_reports_drift_on_every_revision_fails_this_corpus` runs
that ablation against the real population, and
`test_a_detector_that_reports_drift_on_no_revision_fails_this_corpus` runs the
opposite one so the corpus is not all control and no signal.

`C-010` carries a breaking change and a non-breaking change **in the same
commit**, which is what stops the corpus from being separable into a clean
positive half and a clean negative half.

## `C-008` is not T156

T156 is a battery at `tests/batteries/test_drift_negative.py` scoring SC-029's
second clause over repeated re-analysis of held-constant source. `C-008` is one
identical-input revision inside the population SC-008 is measured over, so that
population is not made exclusively of revisions where something moved. The
false-alarm figure T156 exists to produce is not produced here and is not claimed
here.

## E13's three mutations, and the experiment that never ran

[`plan.md` line 831](../../../specs/002-spec-aware-agent-runtime/plan.md) names
feature 001's only drift experiment and its three mutations — *rename a route,
change a parameter type, delete an endpoint* — and says in bold that **E13 never
ran at all**. All three are present here as `C-003`, `C-001` and `C-002`, and
`test_e13s_three_named_mutations_are_all_present` keeps them present.

⚠️ **That is coverage of the mutation set, not a measurement of rate or latency.**
[`VERDICT.md` line 162](../../../specs/001-discovery-validation/VERDICT.md)
records that drift detection has *"no detection rate, no false-alarm rate, no
latency to detect, on either of its two clocks"* as a **production** figure —
T182/T183/T184 are the Phase 8 harness. T138, the source-drift detector SC-008
scores, now consumes this corpus as a falsification test in
`tests/contract/test_source_drift.py`. Committing an instrument is not taking
the Phase 8 reading.

## This file is not gated, and the claims are held by tests instead

`tools/corpuscheck/config.json` walks `README.md`, `research`, `docs`, `specs`,
`tools`, `.cursor/skills` and `.specify/memory`. **`tests` is in none of them**,
so `tools/check_corpus.py` never reads this file — the same measured fact
`tests/fixtures/value-faults/README.md` records for itself.

So every load-bearing claim above is asserted somewhere that runs. The counts
are recomputed by `source.counts()`, the partition is asserted, the mutation
coverage is asserted, and the two ablations are executed rather than described.
