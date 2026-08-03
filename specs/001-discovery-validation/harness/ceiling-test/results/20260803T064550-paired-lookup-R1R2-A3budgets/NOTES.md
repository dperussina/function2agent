# Paired lookup run — does the ≈5× cost advantage survive at the committed budget pair?

**Run** `20260803T064550-paired-lookup-R1R2-A3budgets`
**Harness fingerprint** `365f7debbf2c2ea5` (both arms, one run)
**Battery** 1.4.0-probe · **Fixture** `afd2b135345234ca…` · **Tool surface** v2 · **Attempts** 1
**Target** Mealie v3.22.0, image `sha256:36c28f06…`, verified healthy and at the pinned version before spending.

This file records what was measured. It does not amend any existing document.

---

## The budget pair actually committed to — correcting the brief

The task brief said amendment **A1** commits to a 3× asymmetry and inferred that Arm B's
120 turns / 900k tokens / $3.60 was the inflated side. **A1 is not the operative amendment.**

- **A1.1** raised Arm B from 1.5× to 3× Arm A: 20/150k/$0.60 vs **60/450k/$1.80**.
- **A3.1** (owner decision OD-04) then doubled *both* arms, preserving the 3× ratio:
  Arm A **40/300k/$1.20**, Arm B **120/900k/$3.60**. This is what `config.json` carries and
  what is hashed into the fingerprint.

So the committed pair is **A: 40/300k/$1.20 — B: 120/900k/$3.60**, and the realized 6×
asymmetry came from **Arm A's lookup data being stale (pre-A3, at 20/150k/$0.60)**, not from
Arm B being over-allowanced. Arm B's historical run was already exactly at its committed
budget. The repair is to *raise Arm A*, not to lower Arm B — the opposite of what equalizing
would have done.

`README.md`'s "What is being compared" table still shows the pre-A3 figures (20/150k/$0.60,
60/450k/$1.80) and is stale relative to `config.json`. Not edited here.

## Headline result

| | Arm A ($/attempted) | Arm B ($/attempted) | ratio | $/solved ratio |
|---|---|---|---|---|
| Historical (cross-run, budget-mismatched) | 0.03331 | 0.16850 | **5.059×** | **5.253×** |
| This run (paired, one fingerprint, committed budgets) | 0.03657 | 0.15966 | **4.366×** | **4.366×** |

Per family, this run: **R1 3.222×** (0.08917 / 0.02768) · **R2 4.946×** (0.21606 / 0.04369).

Bootstrap 95% CI on the pooled ratio, resampled over the 27 tasks: **[3.384, 5.423]**.
The historical 5.059× lies inside it. At one attempt per task the two point estimates are
**not statistically distinguishable**.

## How much of the 5× was a budget artifact? None of it.

A dedicated diagnostic settles this. `20260803T070942-diag-armA-v1surface-at-A3budget`
(fingerprint `bc4d54f0e6e79918`, **must not be pooled with this run**) re-ran Arm A on the
**v1** surface at the **raised 300k** budget:

| task | v1 @ 150k (historical) | v1 @ 300k (diagnostic) |
|---|---|---|
| R1.001 | 7,261 tok / $0.0238 | 7,261 tok / $0.0238 |
| R1.011 | 7,258 tok / $0.0236 | 7,258 tok / $0.0236 |
| R2.003 | 14,963 tok / $0.0558 | 14,966 tok / $0.0558 |

Doubling Arm A's allowance moved its spend by **0 tokens on two tasks and 3 tokens on the
third**. Arm A's spend is not budget-sensitive in this regime.

Multiplicative decomposition of 5.059× → 4.366× (factor 0.8630):

| cause | factor | effect on ratio |
|---|---|---|
| budget correction (Arm A 150k → committed 300k) | **1.0000** | **none** |
| Arm A tool surface v1 (20 tools) → v2 (21 tools) | 0.03331/0.03657 = 0.9109 | −8.9% |
| Arm B run-to-run variance at an unchanged 900k | 0.15966/0.16850 = 0.9475 | −5.3% |

0.9109 × 0.9475 = 0.8630; 5.059 × 0.8630 = 4.366 ✓

The v2 effect is a **fixed per-request overhead**, not exploration: on the 21 tasks where Arm A
used exactly 2 turns in both runs, the token delta is a near-constant **+1,083 to +1,114**
(≈551 tokens per request — one extra tool schema resent each turn). `aggregate_recipes`, which
exists only on v2, appears in 10 of 27 new Arm A trajectories and moves cost **both ways**:
R2.003 fell 14,963 → 8,553 tokens (3 turns → 2) because one aggregation call answered it, while
R2.009 and R2.015 each gained a turn.

## The R1.001 "spend scales with allowance" pattern does not replicate

The brief cited R1.001 for Arm B at **$0.0469 / 13,141 tok @ 225k** and **$0.1386 / 42,549 tok
@ 900k** — 2.95× — as direct evidence that a larger allowance inflates spend.

This run, **at 900k**, produced **$0.0470 / 13,149 tok / 5 turns** — the 225k value, to within
8 tokens (0.06%). Both endpoints of the claimed effect have now been observed at the *same*
900k allowance. The 2.95× was **run-to-run variance in the shell agent's exploration path**,
not budget sensitivity.

Arm B's per-task cost ratio between two independent runs at an identical 900k budget:
**min 0.34× · median 0.93× · geomean 0.87× · max 1.81×**. R1.001's 0.34× is inside that
envelope, and four other tasks moved further in one direction or the other (R2.014 0.34×,
R1.010 0.44×, R2.015 1.81×, R2.003 1.62×). Pooled over 27 tasks the variance largely cancels:
**$4.5495 → $4.3109, −5.2%**.

No task in this run shows spend scaling with allowance, because the allowance did not change
for Arm B and did not matter for Arm A.

## Cap utilisation — neither arm bound anything

| arm | caps | max turns | max tokens | max cost | max wall | exhausted |
|---|---|---|---|---|---|---|
| A | 40 / 300,000 / $1.20 / 600s | 4 (10.0%) | 25,633 (8.5%) | $0.0997 (8.3%) | 28s (4.7%) | 0/27 |
| B | 120 / 900,000 / $3.60 / 1800s | 19 (15.8%) | 132,717 (14.7%) | $0.4225 (11.7%) | 65s (3.6%) | 0/27 |

Means: Arm A 2.26 turns / 10,541 tokens; Arm B 9.52 turns / 48,628 tokens. Every one of the 54
attempts terminated `submitted_answer`. Budget-exhaustion rate (A1.2) is **0/27 for both arms**.

## Success and false success

Both arms scored **27/27 (100%)** — R1 12/12, R2 15/15.

**Arm B did not reproduce its false success on `R1.012`.** Historically it terminated
confidently with a ~~9-name list~~ **60-name list** against a 7-name oracle answer (`fail`,
detector `D1`). This run it submitted the correct 7 names and passed. FSR is undefined for both
arms here: there were zero failed attempts, so the denominator is 0.

> **Corrected 2026-08-03. The submitted list was 60 names, not 9, and this note was the sole
> carrier of the wrong figure anywhere in the repository.** The committed row in
> [`../20260802T173614-baseline-lookup-R1R2/results.jsonl`](../20260802T173614-baseline-lookup-R1R2/results.jsonl)
> holds a 60-name answer — the 7 correct names plus 53 extras, with nothing missing, which is the
> entire recipe collection. Its `reason` field lists all 53 unexpected names and an empty missing
> list. [`findings/012`](../../../../findings/012-ceiling-test-per-family.md) §"The one failure is
> more interesting than the score" has it right ("**all 60 recipes**").
>
> The difference matters for what the failure *is*. A 9-name answer would be an over-broad filter;
> 60 is the unfiltered collection, which is the fail-open signature and the thing worth reporting.
> See [`findings/014`](../../../../findings/014-ceiling-test-replication-and-noise-floor.md), which
> establishes the mechanism directly against the application.

Because both arms are at 100%, TSR carries no information at this battery difficulty and
`Δ = 0`. Cost is the only discriminating axis on the lookup families.

## Limitations — what this run cannot settle

1. **One attempt per task.** The preregistration fixes attempts at 3 (A1.3) and forbids
   reporting an effect below twice the noise floor (§9.3). No noise floor is measurable from
   n=1, so the 5.059× → 4.366× move **may not be reported as a difference** under the
   preregistration's own rule. Three attempts on both arms would cost ≈$16 at observed rates,
   over the $6.00 authorization.
2. **Ratio uncertainty is wide.** The bootstrap CI [3.384, 5.423] spans both figures.
3. **Battery version differs from Arm A's historical run** (1.2.0 vs 1.4.0-probe). Incidental
   verification: the v1 diagnostic reproduced the 1.2.0 token counts to within 3 tokens on
   R1.001, R1.011 and R2.003, which means those prompts are byte-identical across the two
   battery versions. Not verified for the other 24.
4. **Battery 1.4.0-probe is the 61-task intermediate state** A4.1 says no *full* run should
   use. This is the R1/R2 limb A5.4 obliges, not a full battery, and A4.3 confirms no task was
   cut from R1 or R2.
5. `TSR(A) = 1.00` is outside the preregistered 0.25–0.85 calibration band, which the decision
   table **VOIDs** for verdict purposes. This run is a cost measurement on a saturated family,
   not a capability verdict, and no decision-table verdict is claimed from it.

## Spend against ceiling

| run | purpose | spend |
|---|---|---|
| `20260803T064400-smoke-paired-precheck` | 2 tasks, both arms, setup de-risk | $0.1153 |
| `20260803T064550-paired-lookup-R1R2-A3budgets` | the paired run, 27 tasks, both arms | $5.2984 |
| `20260803T070942-diag-armA-v1surface-at-A3budget` | v1 surface at raised budget | $0.1032 |
| **total** | | **$5.5168 of $6.00** (headroom $0.4832) |

Enforced by the runner's own `--max-usd` ceiling on every invocation. Nothing halted; the
paired run finished at $5.2984 against a $5.88 cap. Fixture verified clean and matching the
frozen baseline after all runs.

No credential value was read, printed, logged or committed. The dotenv tree was named to the
harness via `F2A_ENV_ROOT` and resolved by `envroot.py`.
