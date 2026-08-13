# T158 — an operation added to a specification the target never stops publishing

**Task**: T158. **Criterion**: **SC-026** — *"On a fixture in which the target
adds an operation to its published specification while continuing to publish
that specification throughout, **100%** of newly appearing operations are
inspected before becoming available, **zero** become available uninspected, and
**100%** of those that cannot be inspected are refused."*

| File | What it holds |
| --- | --- |
| `corpus.json` | Six scenarios over a continuously published specification |
| `../drift_corpora/operation_added.py` | The loader and the fetch replay |
| `../../unit/test_drift_fixtures.py` | The asserted expected output |

## The continuity is the fixture, not a setting

*"while continuing to publish that specification throughout"* is the clause that
makes this a different fixture from `tests/fixtures/spec-withdrawn/` rather than
a variation on it. There the specification goes away and the question is what to
serve from a stale set; here it never goes away and the question is what to do
with something new inside it.

Every fetch in this corpus returns `published_non_empty`. The loader refuses any
other state, `test_the_specification_is_published_at_every_single_fetch`
asserts it, and `test_a_withdrawal_planted_into_this_corpus_is_refused`
**plants** a withdrawal and asserts the loader raises — because reading a
guard's source shows what its author intended to cover, which is the thing in
question whenever a gap is suspected.

## What counts as newly appearing is T153's wording, not the obvious one

T153: *"compare the newly fetched set against the last **inspected** set and
inspect every operation present in the first and absent from the second before
it becomes available, failing closed on any it cannot inspect."*

The comparison is against the last **inspected** set — not the last-known-good
set, and not the previous fetch. The loader replays each scenario's fetches
carrying the inspected set forward, so `add-then-republish-unchanged`, whose
third fetch republishes exactly what the second introduced, computes an
**empty** third entry. An implementation that re-inspects on every fetch gets
that wrong, and that scenario exists to separate it from one that does not.

## FR-056's three outcomes, imported rather than spelled

`clean`, `deputy` and `uninspectable` come from
`src/analysis/deputy_inspection.py`, and availability is decided by that
module's `ALLOWED_OUTCOMES` — a one-member frozenset containing `clean`. So this
corpus cannot drift out of step with the procedure that produces the outcomes: a
rename there breaks the load here.

Both non-clean outcomes are present and both are denied. FR-056's words are that
they are *denied alike and reported differently*, and a corpus carrying only one
of them cannot tell whether an implementation kept them distinct.

**`add-one-uninspectable` is load-bearing rather than illustrative.** SC-026's
third clause reads *100% of those that cannot be inspected are refused*, and
without an uninspectable addition anywhere in the corpus that clause is 100% of
zero — satisfied perfectly by a system with no ability to refuse anything.

## `add-three-mixed-in-one-fetch` is the case neither all-or-nothing answer survives

One fetch introduces a clean operation, a deputy and an uninspectable one. The
clean one **must** become available and the other two **must not**. An
implementation that refuses the whole batch because part of it failed inspection
is caught, and so is one that admits the whole batch because part of it passed.
Neither failure is visible in a scenario adding one operation at a time.

## The population, with its denominator attached

`operation_added.counts()` reports:

- **6** scenarios: **5** in which something is added, **1** in which nothing is;
- **7** newly appearing operation instances over all 6 scenarios, of which **4**
  are refused and **3** are admitted after a clean inspection;
- **3** of FR-056's 3 outcomes exercised;
- **14** fetches over all 6 scenarios.

`test_every_total_is_partitioned_by_a_breakdown_that_sums_to_it` asserts the 5
and the 1 add to the 6.

## The negative control, and the ablation it defeats

**Rule 8**: SC-026's middle clause is *zero become available uninspected*, and
an implementation that makes **nothing** available satisfies it perfectly. On a
corpus made only of additions that ablation scores 100% on all three clauses at
once — the exact tell Rule 8 names.

`no-operation-added` is where it fails: three identical republications, zero
newly appearing operations, and every pre-existing operation must stay
available. `test_an_implementation_refusing_every_operation_fails_this_corpus`
runs the ablation against the real population, and asserts both limbs — that a
scenario with nothing added exists, and that some scenario does make an added
operation available, so the first clause is not satisfied by a system that
admits nothing.

## One thing this corpus deliberately does not decide

Whether an operation that inspected `uninspectable` is **re-attempted** on a
later fetch is T153's decision, and no scenario here forces it: every operation
appears once and its outcome is recorded once. A fixture that answered it would
be writing a requirement from test data, which is the substitution this
repository has a standing rule against.

## ⚠️ The measurement this is not

SC-026 will score T153 — the re-inspection path — and **T153 is open**, as is
every other Phase 6 module. This directory is the committed instrument FR-053
requires alongside the capability; it produces no inspection rate and no refusal
rate, and none can be read off it.

More broadly,
[`VERDICT.md` line 162](../../../specs/001-discovery-validation/VERDICT.md)
records that drift detection has *"no detection rate, no false-alarm rate, no
latency to detect, on either of its two clocks"*, and
[`plan.md` line 831](../../../specs/002-spec-aware-agent-runtime/plan.md)
records in bold that **E13 never ran at all**. Committing a corpus does not
change either sentence.

## This file is not gated

`tools/corpuscheck/config.json` does not walk `tests`, so
`tools/check_corpus.py` never reads this file. The counts are recomputed by
`operation_added.counts()`, the replay contradicts every declared expectation,
and the continuity, the outcome coverage, the mixed batch and the ablation are
all asserted in `tests/unit/test_drift_fixtures.py`.
