# Finding 013 — The budget mismatch was real and contributed nothing: the lookup cost advantage survives at parity

**Date**: 2026-08-03
**User Story**: 1 (does a curated tool surface beat a capable general agent?)
**Owner decision**: [OD-05](../plan.md#od-05--aggregation-tools-admitted-under-a-task-blind-rule-e7-restructured-to-report-per-family)
(per-family reporting; amendment A5.4 obliges the lookup limb) and
[OD-04](../plan.md#od-04--what-e7-measures-rebalance-toward-composition-and-raise-the-budget)
(the budget raise this finding tests)
**Model spend**: **$5.5168** this session, artifact-exact from the committed per-attempt rows in
`results/`, against a $6.00 session authorisation. Across all six E7 sessions the artifact-exact
total is now **$35.0817** — $34.2274 from the per-attempt rows plus $0.8543 of negative-control
spend, the latter recorded only to four decimal places. The full battery still has not run and the
$120 authorised for it is still unspent.
**Method**: one paired run of the 27 lookup tasks — both arms, one run, one harness fingerprint,
the budgets `config.json` actually carries — plus a $0.10 single-variable diagnostic that re-ran the
tool arm's *old* tool surface at the *new* budget. Every outcome decided programmatically against
the application's observable state; no model judged any result (FR-001).

Numbering note: `012` was the last finding issued. `013` and `014` were both free; `008` was
briefly held by two documents and renumbered, so the sequence was checked before either was
written.

---

## The headline

[Finding 012](012-ceiling-test-per-family.md) reported the tool arm as **5.06× cheaper per
attempted lookup task** and then disclosed, in its own correction, that the comparison pooled two
runs whose budget asymmetry was **6× on every axis** rather than the 3× the pre-registration
committed to. The obvious worry is that the shell arm was simply given more room and spent it.

**It was not. Budget's contribution to the ratio is a factor of 1.0000.**

| basis | Arm A $/attempted | Arm B $/attempted | ratio | ratio per solved |
|---|---:|---:|---:|---:|
| historical — cross-run, budget-mismatched | 0.03331 | 0.16850 | **5.059×** | **5.253×** |
| this run — paired, one fingerprint, committed budgets | 0.03657 | 0.15966 | **4.366×** | **4.366×** |

Per family in the paired run: **R1 3.222×** and **R2 4.946×**, against a historical **R1 4.898×**
and **R2 5.137×**.

The run's own bootstrap 95% confidence interval on the pooled ratio, resampled over the 27 tasks,
is **[3.384, 5.423]**, and the historical 5.059× lies inside it. At one attempt per task the two
point estimates are not statistically distinguishable, and
[finding 014](014-ceiling-test-replication-and-noise-floor.md) reaches the same conclusion by an
independent route and forbids reporting the movement as a difference at all.

## The diagnostic that settled it, for ten cents

The paired run changes three things at once against the historical comparison — the budget, the
tool surface, and the session. A pooled figure cannot attribute a movement across three variables,
so a separate three-task run moved exactly one.
[`results/20260803T070942-diag-armA-v1surface-at-A3budget/`](../harness/ceiling-test/results/20260803T070942-diag-armA-v1surface-at-A3budget/)
re-ran Arm A on the **v1** surface — the twenty tools the historical figures came from — at the
**raised 300,000-token** budget. It carries fingerprint `bc4d54f0e6e79918` and **must not be pooled**
with the paired run.

| task | v1 at 150,000 (historical) | v1 at 300,000 (diagnostic) | delta |
|---|---:|---:|---:|
| `R1.001` | 7,261 tok · $0.023823 | 7,261 tok · $0.023823 | 0 |
| `R1.011` | 7,258 tok · $0.023562 | 7,258 tok · $0.023562 | 0 |
| `R2.003` | 14,963 tok · $0.055785 | 14,966 tok · $0.055806 | +3 |

Doubling the tool arm's allowance moved its spend by **zero tokens on two tasks and three tokens on
the third**. The tool arm terminates at two turns because it has the answer, not because anything
is pressing on it: its worst attempt in the paired run used 25,633 of 300,000 tokens, and it
exhausted nothing in 27 attempts or in 27 historical ones. **A budget that never binds cannot
inflate the arm it does not bind**, and this is the direct measurement of that rather than an
inference from headroom.

The diagnostic carries a second result nobody asked it for: reproducing the 1.2.0 token counts to
within three tokens on three tasks means **those three prompts are byte-identical between battery
1.2.0 and 1.4.0-probe**. That is not verified for the other 24.

### Decomposition of 5.059× into 4.366×

The whole movement is a factor of 0.8630, and it decomposes cleanly:

| cause | factor | effect on the ratio |
|---|---:|---|
| budget correction — Arm A from 150,000 to the committed 300,000 | **1.0000** | **none** |
| Arm A tool surface v1 (20 tools) to v2 (21 tools) | **0.9109** | −8.9% |
| Arm B run-to-run movement at an unchanged 900,000 | **0.9475** | −5.3% |

0.9109 × 0.9475 = 0.8630, and 5.059 × 0.8630 = 4.366.

## Which arm was stale, and why the repair went the other way

The pre-registration's amendment history matters here, because reading it wrong points the repair
at the wrong arm.

- **A1.1** raised Arm B from 1.5× to 3× Arm A: 20 turns / 150,000 tokens / $0.60 against
  60 / 450,000 / $1.80.
- **A3.1**, under owner decision OD-04, then **doubled both arms**, preserving that 3× ratio:
  Arm A **40 / 300,000 / $1.20 / 600s**, Arm B **120 / 900,000 / $3.60 / 1800s**.

A3.1 is what `config.json` carries and what is hashed into the harness fingerprint, so **A3.1, not
A1.1, is the operative pair.** The shell arm's historical lookup run was therefore sitting exactly
at its committed budget; the tool arm's data predated the doubling. The realized 6× asymmetry came
from **the tool arm being stale, not from the baseline being over-allowanced**, and the repair is
to raise the tool arm. Equalizing by lowering the baseline would have moved the wrong arm and
violated A1.1's whole purpose, which is that the control must never lose on headroom.

The misreading had a concrete cause, and it is now fixed:
[`harness/ceiling-test/README.md`](../harness/ceiling-test/README.md#what-is-being-compared)'s
"What is being compared" table still showed the pre-A3 figures. See §Corrections below.

## The v2 tool surface costs a fixed overhead, not exploration

The 0.9109 factor is the price of the twenty-first tool, and it is almost entirely one extra tool
schema resent on every request rather than any change in what the model does.

Of the 27 lookup tasks, 21 used exactly two turns on both surfaces. On **18 of those 21** the
v1→v2 token delta sits in a band of **+1,083 to +1,114**, which at two requests per attempt is
**541 to 557 tokens per request** and modally 553. Three of the 21 sit outside the band, and all
three are explained by the trajectory changing rather than by the overhead varying:

| task | v1 tokens | v2 tokens | delta | what changed |
|---|---:|---:|---:|---|
| `R2.008` | 8,665 | 8,480 | **−185** | `search_recipes` → `aggregate_recipes`: a scalar replaces rows, saving more than the schema costs |
| `R2.001` | 7,542 | 8,383 | **+841** | `find_recipes_by_ingredient` → `aggregate_recipes`, same effect, smaller |
| `R2.002` | 8,518 | 9,587 | **+1,069** | same trajectory both surfaces; 14 tokens below the band and unremarkable |

Across all 21 the mean delta is +1,028.

`aggregate_recipes`, which exists only on v2, appears in **11 of the paired run's 27 Arm A
trajectories** and moves cost in both directions: `R2.003` fell from 14,963 tokens at three turns
to 8,553 at two because a single aggregation call answered it, while `R2.009` and `R2.015` each
gained a turn. This is the same effect [finding 012](012-ceiling-test-per-family.md) §Limb 1
measured on the per-record family, seen here as a small tax on tasks the tool does not help and a
large rebate on the ones it does.

## The evidence that motivated the whole investigation does not replicate

The reason to suspect a budget artifact was a specific observation: `R1.001` on the shell arm cost
**$0.046887 for 13,141 tokens at a 225,000-token budget** and **$0.138639 for 42,549 tokens at
900,000** — a 2.95× spread that reads as direct evidence that a larger allowance invites more
spending.

**At 900,000 tokens this run produced $0.047007 for 13,149 tokens in 5 turns** — the low value.
That is 8 tokens from the 225,000-budget observation in
[`results/20260802T151714-smoke/`](../harness/ceiling-test/results/20260802T151714-smoke/), and it
is *exactly* the figure the second smoke run recorded at 225,000 in
[`results/20260802T152825-smoke2/`](../harness/ceiling-test/results/20260802T152825-smoke2/), to
the token and the tenth of a cent. Both endpoints of the claimed effect have now been observed at
the same 900,000 allowance, which means the allowance is not what produced them.

What produced them is run-to-run movement in the shell agent's exploration path. Between two
independent runs at an identical 900,000-token budget, Arm B's per-task cost ratio ranges
**min 0.339× · median 0.930× · geomean 0.867× · max 1.814×**. `R1.001`'s 0.339× is the minimum of
that envelope and four other tasks moved comparably far — `R2.014` 0.343×, `R1.010` 0.443×,
`R2.015` 1.814×, `R2.003` 1.620×. Pooled over 27 tasks most of it cancels: **$4.5495 → $4.3109**, a
5.2% fall.

> That envelope is *not* what it looks like, and [finding 014](014-ceiling-test-replication-and-noise-floor.md)
> §An open question shows why: three of those five tasks are
> internally deterministic across five repeats, so a sampling process cannot be producing their
> spread. Something changes between sessions that repeated attempts within a session cannot see.
> It is an open question, and it bears on every cross-session comparison in this record.

## Cap utilisation — neither arm bound anything

| arm | caps | max turns | max tokens | max cost | max wall | exhausted |
|---|---|---|---|---|---|---|
| A | 40 / 300,000 / $1.20 / 600s | 4 (10.0%) | 25,633 (8.5%) | $0.0997 (8.3%) | 28s (4.7%) | 0 of 27 |
| B | 120 / 900,000 / $3.60 / 1800s | 19 (15.8%) | 132,717 (14.7%) | $0.4225 (11.7%) | 65s (3.6%) | 0 of 27 |

Means: Arm A 2.26 turns and 10,541 tokens; Arm B 9.52 turns and 48,628 tokens. All 54 attempts
terminated `submitted_answer`. Budget-exhaustion rate (amendment A1.2) is **0 of 27 for both
arms**. The largest single consumer of any cap is the shell arm at 15.8% of its turn allowance.

## The lookup family voids its own capability limb

**Both arms scored 27 of 27.** R1 12 of 12, R2 15 of 15, both arms, no exceptions.

That is not a win and it is not even a measurement. `TSR(A) = 1.00` sits outside the pre-registered
0.25–0.85 calibration band, and the decision table's fourth row **VOIDs** the run for verdict
purposes at exactly that condition. No decision-table verdict is claimed from this run, and none
may be.

The consequence for the thesis is worth stating plainly rather than filing under limitations.
**On the lookup family the entire case for a curated tool surface now rests on cost**, measured
once per task, on a battery too easy to discriminate capability between the two arms. `Δ = 0` here
carries no information at all — a metric pinned at its ceiling cannot separate anything — and
[finding 012](012-ceiling-test-per-family.md) already recorded that there is no measured family in
which the tool arm succeeds more often than the baseline. This run does not change that; it
removes the last available excuse for the cost figure and leaves the capability question exactly
where it was, which is unanswered by a battery that cannot ask it.

This is a **limitation of the task design**, not a property of the arms. Building lookup tasks that
land inside the discriminating band was possible and was not done, and the pre-registration's own
A2.5 required re-calibration to land inside the band before Phase 3 ran. It did not.

## Where the run's own notes and the artifacts disagree

Both were resolved in favour of the artifacts.

| claim in [`NOTES.md`](../harness/ceiling-test/results/20260803T064550-paired-lookup-R1R2-A3budgets/NOTES.md) | artifact |
|---|---|
| the v1→v2 delta is "a near-constant **+1,083 to +1,114**" on "the 21 tasks where Arm A used exactly 2 turns in both runs" | true of **18** of the 21. `R2.008` is **−185**, `R2.001` is **+841**, `R2.002` is **+1,069**. The band is right and its scope is not; the two large exceptions are trajectory changes, tabulated above |
| `aggregate_recipes` "appears in **10** of 27 new Arm A trajectories" | **11** of 27 |
| Arm B's `R1.012` "terminated confidently with a **9-name** list against a 7-name oracle" | **60 names.** Corrected in place; see §Corrections |

## Corrections made to the harness record

**1. The `R1.012` false-success size, in the paired run's `NOTES.md`.** The submitted answer in
[`results/20260802T173614-baseline-lookup-R1R2/results.jsonl`](../harness/ceiling-test/results/20260802T173614-baseline-lookup-R1R2/results.jsonl)
is a 60-name list — the 7 correct names plus 53 extras, with nothing missing, which is the entire
recipe collection. [Finding 012](012-ceiling-test-per-family.md) has it right ("all 60 recipes");
the paired run's note was the sole carrier of the 9-name figure anywhere in the repository, and it
is now struck through with a dated note rather than overwritten.

**2. The budget table in [`harness/ceiling-test/README.md`](../harness/ceiling-test/README.md#what-is-being-compared).**
It showed Arm A at 20 turns / 150,000 tokens / $0.60 / 300s and Arm B at 60 / 450,000 / $1.80 /
900s — the pre-A3 figures, stale since amendment A3.1. **This directly caused the misreading that
A1.1 was the operative amendment and that the baseline was the over-allowanced arm.** The table now
carries the A3.1 figures, and a dated note names `config.json` as the authority, since `config.json`
is what the runner reads and what is hashed into the harness fingerprint. A README is documentation
of a configuration and can drift from it; the fingerprint cannot.

## Threats to validity

- **One attempt per task.** Amendment A1.3 fixes attempts at three. Nothing in this document is a
  variance estimate; [finding 014](014-ceiling-test-replication-and-noise-floor.md) measures a
  floor separately, and its §9.3 adjudication forbids reporting the 5.059× → 4.366× movement as a
  difference.
- **The bootstrap interval is wide and the two figures sit inside it.** [3.384, 5.423] spans both.
  Re-running the resample independently at 20,000 draws reproduces [3.39, 5.45]; the published
  figure's own seed is not recorded, so the endpoints are reproducible only to resampling noise.
- **Battery version differs from the tool arm's historical run** (1.2.0 against 1.4.0-probe). The
  diagnostic verifies prompt-identity on three tasks and not on the other 24.
- **Battery 1.4.0-probe is the 61-task intermediate state** that amendment A4.1 says no *full* run
  may use. This is the R1/R2 limb A5.4 obliges rather than a full battery, and A4.3 confirms no
  task was cut from R1 or R2.
- **The v1→v2 comparison is cross-session as well as cross-surface.** The 0.9109 factor is measured
  between two runs on different days. The diagnostic isolates *budget* within a session; nothing
  isolates *surface* within a session, so 0.9109 carries an unmeasured between-session component
  of the kind [finding 014](014-ceiling-test-replication-and-noise-floor.md) identifies.
- **One model, one target application, one battery.** Nothing here separates properties of curated
  tool surfaces from properties of Claude Sonnet 4.5 against Mealie.
- **The $6.00 session authorisation is recorded in the run notes and nowhere in the corpus.**
  Every other spend ceiling in this feature has an amendment or an owner decision behind it. This
  one has neither, and the gap should be closed by whoever authorised it rather than by this
  document asserting it.

## What this evidence does not license

It does not license quoting 4.366× as a *correction* of 5.059×. The two are statistically
indistinguishable at n=1 and [finding 014](014-ceiling-test-replication-and-noise-floor.md)
refuses the movement under the pre-registration's own §9.3 rule. What is licensed is the narrower
and more useful claim: **the ≈5× lookup cost advantage is not a budget artifact**, and the residual
movement is attributable to the tool surface and to session-to-session variation in the shell arm.

It does not license any capability claim on the lookup family in either direction. The family is
saturated and VOID.

It does not license carrying the cost magnitude to another application. Cost ratios depend on the
budget configuration, which has been amended three times, and on a tool surface a human wrote.

## Register entries needing propagation

Identifiers only. A separate pass edits
[`research/14-architecture-synthesis.md`](../../../research/14-architecture-synthesis.md), and new
entries are described rather than numbered here so that no identifier is cited before it exists.

| Entry | Current | Should become |
|---|---|---|
| **D-21** — synthesis, promotion selection, effect classification and decomposition are v2 | The v2 efficiency case carries the 2.2×–9.3× cost range, with the lookup end flagged as cross-run and 6×-budget-mismatched | **The provenance caveat on the lookup figure is discharged; the figure itself is not revised.** Budget contributed a factor of 1.0000, verified by a single-variable diagnostic. The paired figure is 4.366× and the historical 5.059× is inside its bootstrap interval, so **the range is not restated** — [finding 014](014-ceiling-test-replication-and-noise-floor.md) forbids reporting the movement as a difference. What changes is that "cross-run and 6× mismatched" stops travelling with the number as an unresolved threat and starts travelling as: measured, and the mismatch did nothing. **Add to the v2 cost model** that each tool on the surface costs a near-constant 541–557 tokens per request on every task it does not help, repaid many times over on the ones it does — a synthesized surface pays that tax per tool with no guarantee of the rebate. |
| **New entry, next free `U` number** | — | **NEWLY OPENED — the lookup family cannot answer the question it was built for, and no one has proposed a battery that can.** Both arms score 27 of 27, `TSR(A) = 1.00` is outside the 0.25–0.85 band, and the decision table VOIDs it. Amendment A2.5 required re-calibration into the band before Phase 3; it was never achieved and Phase 3 never ran. Every lookup-family claim in the record is therefore a cost claim resting on single-attempt measurements. Blocking for any capability claim about curated tool surfaces; not blocking for the cost claim. |
| **§2 cost-of-synthesis discussion** | Quotes the lookup ratio with a cross-run provenance caveat | **Replace the caveat.** The cross-run disclosure stands as history; the open threat it named is closed. |

## Reproduction

The harness is committed at [`harness/ceiling-test/`](../harness/ceiling-test/) and the convention
for re-running it is in its
[README](../harness/ceiling-test/README.md#reproducing-a-run). Both runs behind this finding are
committed with their manifests, per-attempt rows, and full traces:

| run | fingerprint | surface | arms | attempts | spend |
|---|---|---|---|---|---|
| [`20260803T064400-smoke-paired-precheck`](../harness/ceiling-test/results/20260803T064400-smoke-paired-precheck/) | `365f7debbf2c2ea5` | v2 | A, B | 1 | $0.1153 |
| [`20260803T064550-paired-lookup-R1R2-A3budgets`](../harness/ceiling-test/results/20260803T064550-paired-lookup-R1R2-A3budgets/) | `365f7debbf2c2ea5` | v2 | A, B | 1 | $5.2984 |
| [`20260803T070942-diag-armA-v1surface-at-A3budget`](../harness/ceiling-test/results/20260803T070942-diag-armA-v1surface-at-A3budget/) | `bc4d54f0e6e79918` | v1 | A | 1 | $0.1032 |

Session total **$5.5168** against a $6.00 authorisation, headroom $0.4832. The rounded components
above sum to a tenth of a cent more; the unrounded total is $5.516817. Nothing halted, and the
paired run finished under the `--max-usd` ceiling of $5.88 it was launched with. The fixture
matched the frozen baseline before and after every run. No credential value was read, printed,
logged or committed; the dotenv tree was named to the harness through `F2A_ENV_ROOT` and resolved
by [`envroot.py`](../harness/ceiling-test/envroot.py) (FR-020).

**The two fingerprints must not be pooled**, which is why the diagnostic is reported as a
three-task attribution of one variable and never merged into the 27-task figures.
