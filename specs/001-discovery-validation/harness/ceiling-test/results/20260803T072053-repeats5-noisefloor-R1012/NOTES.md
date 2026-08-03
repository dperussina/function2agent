# Repeats ×5 — the `R1.012` fail-open rate, and the first measured noise floor

**Run** `20260803T072053-repeats5-noisefloor-R1012`
**Harness fingerprint** `365f7debbf2c2ea5` (both arms, one run) — **matches** `20260803T064550-paired-lookup-R1R2-A3budgets`, so the two are poolable.
**Battery** 1.4.0-probe · **Fixture** `afd2b135345234ca…` · **Tool surface** v2 · **Attempts** 5
**Budgets** A 40 / 300,000 / $1.20 / 600s — B 120 / 900,000 / $3.60 / 1800s (`config.json`, amendment A3.1)
**Target** Mealie v3.22.0, image `sha256:36c28f06…` — digest and `/api/app/about` version both checked against `config.json` before spending.
**Design** 5 tasks × 5 attempts × 2 arms = 50 attempts. Tasks: `R1.012` (gap 1) plus `R2.014`, `R1.010`, `R2.015`, `R2.003` (gap 2, the four most volatile).

This file records what was measured. It amends no existing document and states no verdict
that belongs to one.

---

## Read this first: three claims in the record come out weaker

1. **The `R1.012` false success was 60 names, not 9.** The paired run's `NOTES.md` says Arm B
   "terminated confidently with a 9-name list against a 7-name oracle". The committed artifact
   says otherwise: 60 names — all 7 correct ones plus **53 extras**, i.e. the entire recipe
   collection. `findings/012` §"The one failure is more interesting than the score" has it
   right ("**all 60 recipes**"); the paired-run note is the sole carrier of the 9-name figure.
   Nothing was edited here.

2. **The false-success *rate* is not measurable by repeating attempts**, which is what this run
   was asked to do. `R1.012` turns out to be a **deterministic fixed point** within a
   fingerprint — see §Gap 1. Five repeats bought roughly one independent observation, not five.

3. **"Arm A appears near-deterministic" is true of 4 of the 5 tasks and false of the fifth.**
   Arm A's `R2.003` has a **41.8% coefficient of variation**, the largest of any (arm, task)
   cell except Arm B's `R2.014`. See §Gap 2.

Against that, one claim in the record comes out **stronger**, and structurally so: the fail-open
mechanism is a verified property of the target API, not an anecdote. See §Gap 1.

---

## Gap 1 — `R1.012`, the fail-open case

### The rate

| arm | attempts, this run | false successes | pooled at fingerprint `365f7deb` (this run + paired) |
|---|---|---|---|
| A | 5 | 0 | **0 / 6** |
| B | 5 | 0 | **0 / 6** |

Both arms passed 5/5 with the correct 7 names. Clopper-Pearson 95% intervals for 0 events:

- 0/5 → **[0, 45.1%]**
- 0/6 (pooled with the paired run, same fingerprint) → **[0, 39.3%]**

**Those intervals are not trustworthy, and reporting them alone would overstate the evidence.**
Clopper-Pearson assumes independent Bernoulli draws. These attempts are not independent:

| | turns | tool sequence | tokens | submitted |
|---|---|---|---|---|
| Arm A ×5 + paired | 2, every time | `search_recipes` → `submit_answer`, every time | **8,889, all six, exactly** | identical 7 names |
| Arm B ×5 + paired | 9, every time | 8 × `bash` → `submit_answer`, every time | 47,157 ×4 / 47,125 ×2 (spread **0.07%**) | identical 7 names |

At temperature 0 the harness is reproducing one trajectory, not sampling a distribution. The
effective number of independent observations is closer to **one session** than to six attempts.
Taken at the session level the record holds **1 failure in 2 sessions** — 95% CI
**[1.3%, 98.7%]**, which is no constraint at all.

**Failure mode of each occurrence: none occurred.** There is nothing to report per-occurrence,
and that is the honest answer to the question as asked.

I did **not** buy five more Arm B attempts with the remaining headroom. They would have moved
the naive interval from [0, 39.3%] to [0, 23.8%] while being five more copies of a fixed point —
a tighter-looking number backed by no additional information. That would be manufacturing
precision.

### The mechanism — verified directly, and it is real

The 2026-08-02 failure and every pass here run through the *same* first move: both ask
`/api/organizers/categories` for the category list. They diverge on one substitution.

| | filter used | result |
|---|---|---|
| historical (`f9abf1d3`, failed) | `?categories=Breakfast` — the **name** | 60 recipes |
| this run ×5 + paired (passed) | `?categories=906d5da2-b4c9-…` — the **UUID** | 7 recipes |

Probed against the live instance directly, with no model in the loop and at no cost:

| `categories=` value | `.total` | |
|---|---:|---|
| `906d5da2-b4c9-4aee-97c7-57a30013e22e` (valid UUID) | **7** | filtered |
| `Breakfast` (the name) | **60** | **fail-open** |
| `zzzz-not-real` (nonsense) | **60** | **fail-open** |
| *(empty string)* | **60** | **fail-open** |
| *(parameter omitted)* | 60 | collection size |

Mealie answers HTTP 200 and silently returns the **entire unfiltered collection** for any
`categories` value it cannot resolve to a UUID. This is a deterministic property of the target,
not a model quirk — so the *hazard* is confirmed beyond the single observation the record rests
on, even though the *rate at which an agent trips it* is not.

The historical trajectory also called `jq '.total'` and saw `60` before submitting. It had the
disconfirming number in hand and submitted anyway.

**Why Arm A cannot trip this.** `search_recipes` does not pass `category` to that query
parameter at all — it fetches recipe details and filters in Python on
`c["name"].lower() == category.lower()` (`tools/mealie_tools.py`). The fail-open path is
**structurally unreachable** through the curated tool. That is a stronger claim than "the tool
arm got it right", and it does not need a rate to stand up.

**The caveat the thesis needs to absorb.** Arm A is immune because a human wrote a tool that
filters client-side. A tool *synthesized* from `GET /api/recipes` would wrap the vulnerable
parameter and inherit the fail-open exactly as the shell agent did. This run shows a
well-written tool can encapsulate the hazard — which is what "ceiling" means — and shows nothing
about whether synthesis would produce one.

---

## Gap 2 — the noise floor

### Per-task coefficient of variation in spend, n = 5

| task | Arm A mean $ | Arm A sd | **Arm A CV** | Arm B mean $ | Arm B sd | **Arm B CV** |
|---|---:|---:|---:|---:|---:|---:|
| `R1.010` | 0.02791 | 0.00000 | **0.00%** | 0.01585 | 0.00000 | **0.00%** |
| `R1.012` | 0.02955 | 0.00000 | **0.00%** | 0.15570 | 0.00014 | **0.09%** |
| `R2.003` | 0.04166 | 0.01742 | **41.82%** | 0.25700 | 0.05954 | **23.17%** |
| `R2.014` | 0.02747 | 0.00001 | **0.02%** | 0.11548 | 0.06955 | **60.23%** |
| `R2.015` | 0.04524 | 0.00065 | **1.44%** | 0.24824 | 0.00041 | **0.16%** |

Variance is **not** a smooth property of an arm. It is bimodality on specific tasks, and it is
discrete: the arm takes one of two solution paths and the token count follows.

- Arm A `R2.003`: 2 turns / 8,553 tok (×3) vs 3 turns / 16,619–16,631 (×2). The 2-turn path uses
  `aggregate_recipes`, which exists only on surface **v2**. The `20260803T070942` diagnostic that
  found Arm A stable to within 3 tokens ran the **v1** surface, where that fork does not exist.
  **Adding the 21st tool is what introduced Arm A's variance on this task.**
- Arm B `R2.014`: 7 turns / 18,743–20,106 (×3), 8 turns / 43,103, 12 turns / 69,984 — a 3.44×
  spread, the widest cell measured.

### The quoted "run-to-run variance" envelope is mostly not run-to-run variance

The paired run characterised Arm B's spread between two independent 900k runs as
min 0.34× / median 0.93× / geomean 0.87× / max 1.81×, and named four tasks. Set that against
their within-fingerprint behaviour:

| task | cross-run paired/hist | **within-fingerprint max/min (this run, n=5)** |
|---|---:|---:|
| `R1.010` | 0.44× | **1.00×** (4,079 tok, six times, exactly) |
| `R2.015` | 1.81× | **1.00×** (76,73x–76,846, six times) |
| `R1.012` | 0.93× | **1.00×** (47,125/47,157) |
| `R2.003` | 1.62× | 1.90× |
| `R2.014` | 0.34× | 3.44× |

Three of the five are internally **deterministic** yet sat at different values in the two runs —
`R1.010` at 10,392 tokens then 4,079 (2.55×), `R2.015` at 40,951 then 76,845 (1.88×). A
deterministic process cannot produce a 2.55× swing by sampling. The 0.34×–1.81× envelope
therefore conflates two components:

- **σ_w, within-session replicate noise** — real, but confined to `R2.003` and `R2.014`;
- **σ_b, a between-session shift** — larger per-task, and **not estimable from repeats**.

This matters for §9.3 because the two figures being compared were measured in different
sessions at different fingerprints. Everything below measures σ_w only, so **every floor here is
a lower bound on the floor that actually applies.**

### The floor on the ratio — arithmetic

The reported quantity is ρ = (mean Arm B $/task) / (mean Arm A $/task), so its variance draws on
both arms. Per-round pooled figures over the 5 tasks (each round is one independent replicate of
the whole 5-task set):

```
round             1         2         3         4         5
Arm A $/task   0.03827   0.03167   0.03828   0.03192   0.03168     mean 0.03436  sd 0.00357  CV_A = 10.397%
Arm B $/task   0.18619   0.15358   0.15421   0.14295   0.15534     mean 0.15845  sd 0.01629  CV_B = 10.279%
ratio B/A      4.8649    4.8492    4.0282    4.4791    4.9031      mean 4.6249   sd 0.3750   CV_ρ =  8.109%
```

Two constructions, because the two figures in question were not built the same way:

- **Paired** (both arms from one run, as in 4.366×). Observed directly on the ratio column:
  **CV_ρ = 8.109%**. Lower than the arms individually because they co-vary across rounds
  (r = 0.650) and the shared component cancels.
- **Unpaired** (arms from different runs, as in 5.059×). Delta method, errors independent:
  CV_ρ = √(CV_A² + CV_B²) = √(0.10397² + 0.10279²) = √0.021376 = **14.620%**.

Scaling from the 5 measured tasks to the 27-task set the figures are reported over. For a fixed
task list, between-task variation cancels and only within-task run-to-run variance contributes,
so SE of the pooled mean shrinks by √(27/5) = 2.324:

| construction | CV_ρ at n = 5 | **2× floor** | CV_ρ scaled to n = 27 | **2× floor** |
|---|---:|---:|---:|---:|
| paired | 8.109% | **16.22%** | 3.49% | **6.98%** |
| unpaired | 14.620% | **29.24%** | 6.29% | **12.58%** |

The movement to be tested: 5.059× → 4.366× is a factor 0.8630, a **−13.70%** relative change
(**14.73%** in log units).

### Is the 5.059× → 4.366× movement reportable under §9.3? **No.**

| construction | 2× floor | movement 13.70% | |
|---|---:|---:|---|
| paired, n = 5 (measured) | 16.22% | below | **not reportable** |
| unpaired, n = 5 (measured) | 29.24% | below | **not reportable** |
| unpaired, n = 27 (scaled) | 12.58% | above by 1.12 pp | marginal |
| paired, n = 27 (scaled) | 6.98% | above | would be reportable |

It clears the bar under **one of four** constructions outright and one marginally, and the
reasons to refuse it are not close:

1. **The applicable construction is the unpaired one.** The 5.059× pairs Arm A from
   `20260802T160705-recalibration` with Arm B from `20260802T173614-baseline-lookup-R1R2` — no
   shared run, no shared fingerprint, so the arms' errors do not cancel. At n = 27 that is a
   12.58% bar against a 13.70% effect: a margin of 1.12 percentage points, smaller than the
   uncertainty in the √(27/5) extrapolation that produced it.
2. **σ_b is missing from every number in that table**, and this run proves σ_b is real and
   per-task larger than σ_w (2.55× and 1.88× shifts on tasks with zero replicate variance). The
   comparison spans sessions; its true floor is strictly above the lower bounds computed here.
3. **The n = 5 → 27 scaling leans on 22 unmeasured tasks**, using an average per-task variance
   drawn from a sample selected *for* volatility.
4. **An independent route already agrees.** The paired run's bootstrap 95% CI on the pooled
   ratio, [3.384, 5.423], contains 5.059.

§9.3 is a bar an effect must clear, not a coin-flip it must win. An effect that survives only
the most favourable of four constructions, by less than the error in that construction, and
against a floor known to be understated, has not cleared it. **The movement may not be reported
as a difference.** The two figures remain statistically indistinguishable, which is what the
paired run already concluded from a different direction.

What *is* now reportable, and was not before: **a measured within-session noise floor exists**
(CV_ρ = 8.1% paired / 14.6% unpaired at n = 5), and the A1.3 requirement of 3 attempts per task
has a concrete price attached — see below.

---

## Cap utilisation — nothing bound, in any of the 50 attempts

| arm | caps | max turns | max tokens | max cost | max wall | exhausted |
|---|---|---|---|---|---|---|
| A | 40 / 300,000 / $1.20 / 600s | 3 (7.5%) | 16,631 (5.5%) | $0.0608 (5.1%) | 17s (2.8%) | **0/25** |
| B | 120 / 900,000 / $3.60 / 1800s | 13 (10.8%) | 89,015 (9.9%) | $0.2862 (8.0%) | 56s (3.1%) | **0/25** |

Means: Arm A 2.28 turns / 10,224 tok / $0.03436 — Arm B 8.84 turns / 48,404 tok / $0.15845.
All 50 attempts terminated `submitted_answer`; no `run_budget_halt`, so no attempt was truncated
by the run ceiling and no row is contaminated by it. Budget-exhaustion rate (A1.2) **0/25 both
arms**. Success 25/25 both arms; false success 0 in 50.

Per-task totals: Arm A $0.8591 over 25 attempts, Arm B $3.9613 over 25.

Ratio on **this 5-task subset** is 4.625× (Arm B $0.15845 / Arm A $0.03436) — reported for
completeness, not comparable to the 27-task figures, since the task mix differs and four of five
tasks were volatility-selected.

## Spend against the ceiling

| run | purpose | spend |
|---|---|---|
| `20260803T071942-smoke-precheck-gapfill` | `R1.001`, both arms, setup de-risk | $0.0740 |
| `20260803T072053-repeats5-noisefloor-R1012` | 5 tasks × 5 attempts × 2 arms | $4.8204 |
| **total** | | **$4.8944 of $6.00** (headroom **$1.1056**) |

Enforced by the runner's own `--max-usd` on every invocation ($0.30 on the smoke, $5.70 on the
main run, so the worst case was $5.77). Projected cost before launching was $4.9494 from the
paired run's per-task figures; actual $4.8944, 1.1% under. Nothing halted.

Headroom was deliberately left unspent — see §Gap 1 for why more `R1.012` repeats would have
bought a tighter interval and no more information.

## Provenance and safety

- Harness fingerprint `365f7debbf2c2ea5` reproduced from source **before** any spend, via
  `python3 -c "import runner; print(runner.harness_fingerprint('v2'))"`, and matches the paired
  run's manifest. `v1` also reproduces `bc4d54f0e6e79918`. The runner reprinted `365f7debbf2c2ea5`
  in both run headers and stamped it on all 52 result rows.
- Target verified before spending: `docker inspect` digest identical to `config.json`'s pin, and
  `/api/app/about` reporting `v3.22.0`.
- Fixture verified against the frozen baseline **before** (`afd2b135345234ca…`, match, and every
  frozen expected value re-derived with no mismatch) and **after** (same fingerprint, clean).
  No write tasks were in scope; no restore was triggered.
- No credential value was read, printed, logged or committed. The dotenv tree was named to the
  harness through `F2A_ENV_ROOT` and resolved by `envroot.py`; no path to it appears in this
  repository, in this file, or in any artifact of these runs.

## Limitations

1. **σ_b is unmeasured.** Repeats within one ~20-minute window cannot see between-session drift,
   which this run shows to be the dominant component for the comparison at issue. Measuring it
   needs runs separated in time, not attempts separated in sequence.
2. **Five tasks, four of them volatility-selected.** Per-task CVs here are not a random sample of
   the battery, and the extrapolation to n = 27 inherits that.
3. **`R1.012`'s FSR is still effectively unmeasured** at n ≈ 1 independent observation per
   session, for the reason in §Gap 1. Temperature is pinned at 0; a rate estimate would need
   either independent sessions or a deliberate perturbation, and neither is in this design.
4. **A1.3's 3 attempts per task now has a price.** At this run's observed rates a 3-attempt,
   57-task, two-arm battery is ≈$33; the 27-task R1/R2 limb alone is ≈$15.6. Neither fits a
   $6.00 authorization.
5. Both arms are at 100% on these five tasks, so TSR carries no information and no
   decision-table verdict is claimed from this run. `TSR(A) = 1.00` remains outside the
   preregistered 0.25–0.85 calibration band, which **VOIDs** the decision table for verdict
   purposes.
