# Finding 018 — the verifier's zero-false-alarm result survives restriction to the attested subcorpus, and the denominator it was published on counts 45 records the arm never compared

> **⚠️ RENUMBERED: this finding's `E8` is the experiment now called `E19`.** The identifier `E8`
> named two experiments until 2026-08-11, when [`plan.md` **OD-31**](../plan.md#od-31--the-verifier-vs-judge-experiment-is-renumbered-e19-and-the-stage-d-synthesis-experiment-keeps-e8-the-renumber-reaches-live-prose-only-and-the-committed-run-directories-the-fingerprinted-harness-files-and-the-dated-assessments-keep-the-name-they-were-recorded-under)
> assigned `E8` to the Stage-D synthesis experiment and `E19` to the verifier-vs-judge experiment
> this finding is about. **Nothing below is rewritten.** This is an authority document and a dated
> record; the house convention supersedes rather than overwrites, and a strike inside a heading
> corrupts its anchor. **Read every `E8` below as `E19`.** No figure, denominator, population or
> verdict is affected by the renumber.

**Date**: 2026-08-03
**User Story**: 1 (prove or disprove the core value proposition) — hypothesis **H2**. This finding
measures no new system behaviour. It re-runs an existing census under a narrower record filter and
reports what the two populations respectively license.
**Owner decision**: none is changed.
[OD-14](../plan.md) stands: the verifier's margin over an LLM judge remains **UNMEASURED**.
Nothing here speaks to margin.
**Model spend**: **$0.0000.** No model was called, no credential was read, no network request was
made. Every number below comes from re-running the committed E8 harness against the frozen corpus
and the committed offline state fixture.
**Method**: a new thin driver, `harness/verifier-vs-judge/census_c2_false_alarms.py`, calls
`c2_postcond.verify` over all 246 frozen records exactly as `runner.py` does, joins each verdict to
the eligibility status `corpus.partition` already computes, and reports the false-alarm count
stratified by how each record's join is attested. No verdict logic, no eligibility logic and no
rate arithmetic is reimplemented; the driver adds the stratification and nothing else.

Numbering note: `017` was the last finding issued and `018` was free, checked by ripgrep with
`--hidden` across the tree before this file was created. No prior artifact claims the identifier.

---

## Why this was run

[Finding 017](./017-evaluation-contemporaneity.md) surveys the figures in this corpus that may rest
on an evaluation scored against artifacts postdating the defect they were detecting, and ranks the
verifier's false-alarm figure first. [`VERDICT.md`](../VERDICT.md) calls the verifier the one v1
capability *"softer than unmeasured suggests"*, and the evidence it gives is
[finding 015](./015-verifier-vs-judge-not-run.md)'s **zero false alarms across 220 clean
positives**.

The suspicion S1 raises is about the denominator, not the numerator. The 220 is 226 oracle-positives
less the 6 stale ones the arm itself flagged, and that exclusion is sound — finding 015 establishes
those 6 by three routes that never consult the arm. What is left is a population 143 of whose 246
parent records ran under a battery version that no longer exists, and whose membership therefore
rests, for most records, on a value-comparison test that finding 015 shows is **blind to wording
drift**. S1's named check was to re-run the census restricted to records whose run manifest declares
the current battery, where `eligible_same_battery` attests the join with no join performed at all.

That is what this is.

## The census, both ways

Arm (c2) scored over all 246 frozen records against the committed offline fixture, positives
stratified by attestation. `compared` is the number of records on which c2 actually returned a
verdict rather than declining as `unverifiable` — a record it refused to compare cannot raise a
false alarm and carries no information about the rate.

| population | records | compared | false alarms | rate | Wilson 95% |
|---|---:|---:|---:|---:|---|
| all oracle-positives | 226 | 181 | 6 | 2.7 pp | 1.2–5.7 pp |
| **pooled clean** — finding 015's denominator | **220** | 175 | **0** | 0.0 pp | 0.0–1.7 pp |
| — **narrow**: the run manifest declares the current battery | **96** | 93 | **0** | 0.0 pp | 0.0–3.8 pp |
| — cross-battery, value-attested | 84 | 82 | 0 | 0.0 pp | 0.0–4.4 pp |
| — cross-battery, unattested | 40 | **0** | 0 | undefined | — |

The last three rows partition the 220 exactly, and the 6 alarms are exactly the 6 stale positives, so
the pooled figure is reproduced rather than quoted. On the compared subsets the Wilson bounds are
0.0–2.1 pp pooled and 0.0–4.0 pp narrow. The unattested row has no rate because c2 compared none of
its 40 records; the harness prints 0.0 pp over the record count there and that number should not be
read as evidence, which is point 2 below.

**The narrow rate is zero.** Finding 017 anticipated this outcome and said the claim would then be
*stronger* than it reads. That is right, and it needs one qualification it did not anticipate.

## Three things this establishes, one of which was not the question

**1. The zero is not an artifact of the unattested records.** The concern S1 raises is that the
pooled denominator mixes directly-attested records with records kept in scope by a test known to be
blind to the drift at issue. Split apart, **both halves are clean**: 0 of 93 compared on the
same-battery half, 0 of 82 compared on the value-attested half. A contaminated population that owed
its clean rate to the unattestable half would not survive that split. This one does, twice, and the
second half is the half the suspicion was about.

**2. The 220 is inflated by 45 records the arm never compared, and 40 of them are the unattested
class.** This is the part the survey did not predict, and it is a defect in the figure independent
of provenance. `unverifiable` is not a pass. c2 declines a record when no derivation exists for its
request signature, when the derivation is a refusal, or when nothing was submitted — and 45 of the
220 are declined, all 40 unattested positives among them. Those 40 are in the denominator of a
false-alarm rate while being structurally incapable of contributing to its numerator. They tighten
the interval and supply no evidence. **The honest pooled figure is 0 of 175 compared, not 0 of 220**,
and the narrow figure has almost none of this problem: 3 of 96 declined, all three the same task,
`R2.014`, whose projection the precision ladder refuses.

**3. On the attested population the two sides of the sentence finally share one denominator, and the
detection side is much smaller.** `VERDICT.md`'s sentence pairs *all 9 numeric value errors* with
*220 clean positives*. Those are two populations: the detection numerator is over the 15 eligible
negatives, the false-alarm denominator over the 220 clean positives. Restricted to
same-battery records, both sides are over one population of 103 records — 96 positives and 7
negatives — and read: **c2 flags 2 of the 2 false successes and raises 0 false alarms on 96
positives.** The detection count falls from 10 to 2, which is not new; it is exactly the strict
re-scope [`E8-VIABILITY.md`](../E8-VIABILITY.md) §2 reports and finding 015 quotes ahead of the
join-valid 3. **Attestation is cheap on the false-alarm side and expensive on the detection side**,
because the false successes are concentrated in the records the drift touched.

## What narrowing costs, stated because it is not nothing

| | pooled clean | narrow |
|---|---:|---:|
| positives compared | 175 | 93 |
| distinct tasks compared | 40 | 33 |
| families compared | R1, R2, R4 | R1, R2, R4 |
| R4 records compared | 34 | 12 |

**No family is lost.** The pooled stratum holds 12 R3, 14 N and 14 W1 positives, and c2 declines
every one of them — those 40 records *are* the unattested class, exactly, which is the same fact
finding 015 reports from the eligibility side when it says the lost families are the refusal-shaped
ones. They contribute nothing to either figure. The seven tasks narrowing does cost
are all R4 — `R4.001`, `R4.002`, `R4.003`, `R4.004`, `R4.007`, `R4.009`, `R4.010` — and R4 is the
family where the drift and the false successes both live, so the narrow stratum's coverage of the
most interesting family is 12 records against 34.

**And the narrow population would not have caught the defect the pooled one did.** The two records
that exposed c1's fabricated cardinality clause — `R4.002/B` and `R4.004/B` in
`20260802T163319-bias-probe` — ran under battery 1.3.0 and are `eligible_value_attested`. They are
in the 220 and not in the 96. A narrower population is better attested and sees less; finding 015's
C-19 lesson, that a denominator excluding the failure is indistinguishable from one containing none,
applies to any narrowing and applies to this one.

## Contemporaneity of the census itself

Finding 017's rule applied to this work: if the harness has moved since the census was first
computed, re-running it reproduces the same defect one level up. Four checks, all mechanical.

| check | result |
|---|---|
| Has anything under `harness/verifier-vs-judge/` changed since `cee7ff8`? | **No.** `git diff cee7ff8 HEAD` over the harness tree touches only `provider-sdk-roundtrip` and `harness/README.md`. The working tree adds only the new driver, which is not in `FINGERPRINT_FILES` |
| Does the harness fingerprint match the last committed run's? | **Yes** — `6c58910ec3fd9c36`, computed now, is byte-identical to the fingerprint recorded in `results/20260803T092721-final-verify/manifest.json`, over all sixteen fingerprinted files |
| Is the derivation set the one the runs scored against? | **Yes** — `c2_derivations` hashes to `ab4d8b534cd98c72` here and in all twelve committed run manifests |
| Is the frozen corpus intact? | **Yes** — `freeze.py --verify` reports 11 runs, 246 records, 20 negatives, and the battery pins intact |

The driver additionally asserts the reproduction rather than eyeballing it: `--verify-pooled` fails
unless the pooled stratum returns all four of finding 015's published figures — 226 positives, 6
alarms, 220 clean, 0 alarms on the clean set. It passes.

**What this does not prove, and the reason is structural.** The whole harness landed in one commit
alongside finding 015, so history cannot order the census against the code, exactly as finding 017's
S2 records for the checker fixtures. What is available instead is that the fingerprint now equals the
fingerprint at the last committed run, that finding 015's census postdates that run, and that four
published figures reproduce exactly. A census computed against a different byte state would have to
agree on all four by coincidence.

## What each figure licenses

**0 of 220** licenses: *across every oracle-positive in the frozen corpus that is not known-stale,
the postcondition arm raised no false alarm.* It does not license a false-alarm **rate** of 0 of 220,
because 45 of the 220 were never compared. Its tight interval is bought partly with records that
could not have contributed to the numerator.

**0 of 175 compared** licenses the same statement as a rate. The 40 unattested records drop out of
this figure by construction, because none of them was compared, so what remains is 93 same-battery
comparisons and 82 comparisons on records kept in scope by the value test. It is the strongest
figure available that still carries a provenance caveat, and the caveat now applies to 82 of its 175
records rather than to an unknown share of 220.

**0 of 96, of which 93 compared** licenses: *on every oracle-positive whose own run manifest declares
the battery under test, so that no cross-artifact join occurs and nothing rests on the value test,
the arm raised no false alarm.* This is the figure with no provenance caveat attached, and its cost
is a wider interval — 0.0–3.8 pp against 0.0–1.7 pp — and thinner coverage of R4.

**What `VERDICT.md` may now claim.** That the mechanism raises no false alarms on a directly
attested population, quoting **0 of 96**, with the pooled figure beside it and the compared counts
stated. What it may not do is keep quoting *0 of 220* as a rate without the 45 refusals, and it may
not keep pairing a detection numerator over the eligible population with a false-alarm denominator
over the clean-positive population as though they were one measurement. Neither correction weakens
the product claim. The first makes it honest about how much comparison the number represents; the
second makes it a claim about one population.

## Threats to validity

- **A denominator of 96 with 93 comparisons is a small population and its interval says so.** Zero
  false alarms there is consistent with a true rate as high as 3.8 pp. On 175 comparisons it is
  consistent with 2.1 pp. Neither figure licenses "raises no false alarms" as a property; both
  license "raised none here".
- **The narrow stratum's R4 coverage is 12 records.** R4 is where every prompt amendment landed and
  where 9 of the 11 false successes sit. The family most likely to expose a postcondition
  disagreement is the family the attested population covers least.
- **`unverifiable` is not scrutinised here.** This finding counts refusals so they stop inflating a
  denominator. It does not ask whether any of the 45 *should* have been comparable, and a refusal
  rate is its own claim about coverage — `UNV_c2` is already reported at 10.7% on the 75-record
  scoring set and is 20.5% on the pooled clean positives, which is a larger number over a larger
  population and is not a regression.
- **Everything rests on the offline fixture.** Finding 015's fixture-fidelity caveat carries over
  unchanged: the fixture reproduces 44 of 44 oracle expectations and one defect of a shape the trace
  audit could not see was found by a different route.
- **This settles S1 and bounds nothing else.** Finding 017's survey is not exhaustive and its base
  rate is unmeasured. One suspect checked clean is one suspect.

## What this does not establish

It does not change OD-14, or anything about the verifier's margin over an LLM judge. No judge verdict
exists, and a false-alarm census cannot produce one.

It does not license describing the verifier as validated, measured or earned. The mechanism claim is
now stated over a better population; it is still a mechanism claim.

It does not overturn finding 015. Every figure that finding published reproduces exactly. What
changes is what may be quoted from them and on which denominator.

## Register entries needing propagation

Identifiers only, and new entries are described rather than numbered so that nothing cites an
identifier before it exists.

| Entry | Should become |
|---|---|
| **New entry, next free `U` number** | **NEWLY OPENED — a false-alarm denominator that counts records the detector declined is inflated by records that could not have contributed to its numerator.** 45 of the 220 clean positives in E8's headline figure are `unverifiable`, 40 of them the entire unattested class, and every one tightens the interval while supplying no evidence. The fix is to report the compared count beside the denominator on every false-alarm rate, which is a reporting rule rather than a code change. Generalises to any evaluation whose detector may decline. |
| **The verifier rows wherever `0 of 220` is quoted** | **Add the attested figure and the compared count.** The mechanism claim is unchanged and better supported: 0 false alarms on 96 directly attested oracle-positives, 93 of them compared, beside 0 on the 220 clean positives, 175 of them compared. Sites outside this feature's directory were not edited by this pass and still carry the pooled figure alone — the root `README.md`, `research/04`, `research/07`, `research/11`, `research/14`, `.cursor/skills/README.md`, `.cursor/skills/contract-derived-verification/SKILL.md`, and `specs/002-spec-aware-agent-runtime/spec.md`. |

## Reproduction

Everything here is reproducible offline at $0.0000, with no credential, no network and no container.

```bash
cd specs/001-discovery-validation/harness/verifier-vs-judge

python3 freeze.py --verify                              # corpus and battery pins intact
python3 census_c2_false_alarms.py --verify-pooled       # the stratified census, and the check
python3 census_c2_false_alarms.py --json --per-record   # every record's verdict and status
python3 -c "import runner; print(runner.harness_fingerprint())"   # 6c58910ec3fd9c36
```

The narrow stratum is `corpus.ELIGIBLE_SAME_BATTERY`, which for oracle-positives coincides exactly
with *run manifest declares `1.4.0-probe`*: all 96 such positives carry that status, the partition
reports no integrity alarm, and no same-battery record is stale.
