# Finding 014 — The fail-open is a property of the application, not of the tool abstraction; and the first measured noise floor

**Date**: 2026-08-03
**User Story**: 1 (does a curated tool surface beat a capable general agent?)
**Owner decision**: [OD-05](../plan.md#od-05--aggregation-tools-admitted-under-a-task-blind-rule-e7-restructured-to-report-per-family)
— this discharges the two follow-ups [finding 012](012-ceiling-test-per-family.md) §Whether the
full battery is still worth running named as worth buying instead of the full battery
**Model spend**: **$4.8944** this session, artifact-exact from the committed per-attempt rows in
`results/`, against a $6.00 session authorisation. **$1.1056 of authorised budget was deliberately
left unspent**, for the reason in §The rate is not measurable this way. Across all six E7 sessions
the artifact-exact total is now **$35.0817** (see
[finding 013](013-ceiling-test-budget-parity.md) for the decomposition).
**Method**: five tasks × five attempts × two arms — the `R1.012` fail-open case plus the four most
volatile tasks from [finding 013](013-ceiling-test-budget-parity.md) — at one harness fingerprint,
plus direct HTTP probing of the target's filter parameter with no model in the loop. Every outcome
decided programmatically against the application's observable state; no model judged any result
(FR-001).

Numbering note: `013` is the paired budget-parity run from the same day. `008` was briefly held by
two documents and renumbered, so the sequence was checked before either of these was written.

---

## The headline: the fail-open is real, verified, and does not need a rate

[Finding 012](012-ceiling-test-per-family.md) rested its strongest product argument on **one
observation**: the shell arm asked Mealie for the `Breakfast` category by display name, was handed
the entire recipe collection, and submitted it as the answer. One observation, on the one task in
the family that had been hand-redesigned, is exactly the shape of an anecdote.

**It is not an anecdote. It is a deterministic property of the target application, established
model-free.** Probed directly against the running instance at no cost:

| `categories=` value | recipes returned | | source |
|---|---:|---|---|
| `906d5da2-b4c9-4aee-97c7-57a30013e22e` (a valid UUID) | **7** | filtered correctly | this run |
| `breakfast` (the slug) | **7** | filtered correctly | [finding 012](012-ceiling-test-per-family.md) |
| `Breakfast` (the display name) | **60** | **fail-open** | both |
| `zzzz-not-real` (nonsense) | **60** | **fail-open** | this run |
| *(the empty string)* | **60** | **fail-open** | this run |
| *(the parameter omitted)* | 60 | the collection size | this run |

Mealie answers **HTTP 200** and silently returns the entire unfiltered collection for any
`categories` value it cannot resolve. There is no error, no empty result, and nothing in the
response that distinguishes "your filter matched everything" from "your filter was discarded". The
slug and UUID rows are the ones that make this dangerous rather than merely wrong: the parameter
*does* work, for two of the three plausible identifier forms, so an agent that gets it right once
has no reason to doubt it the next time.

The committed traces corroborate the mechanism without needing the probe re-run. Both the
historical failure and every pass since open with the same move — `GET /api/organizers/categories`,
which returns the names *and* the UUIDs — and then diverge on one substitution:

| run | filter used | `jq '.total'` returned |
|---|---|---|
| [`20260802T173614-baseline-lookup-R1R2`](../harness/ceiling-test/results/20260802T173614-baseline-lookup-R1R2/) (failed) | `?categories=Breakfast` | `60` |
| [`20260803T072053-repeats5-noisefloor-R1012`](../harness/ceiling-test/results/20260803T072053-repeats5-noisefloor-R1012/) ×5 and the paired run (passed) | `?categories=906d5da2-…` | `7` |

**The historical agent called `jq '.total'`, read `60`, wrote "There are 60 …" in its own
reasoning, and submitted anyway.** It held the disconfirming number and the correct identifiers at
the same time. That is not a discovery failure and no amount of endpoint discoverability would
have prevented it, which is the point [finding 012](012-ceiling-test-per-family.md) made and this
finding now supports with a mechanism instead of an instance.

## And the caveat, which is a finding about the product

The curated tool cannot fail this way. `search_recipes` never passes `category` to the vulnerable
query parameter at all: it fetches recipe details and filters in Python on
`c["name"].lower() == category.lower()`, through the shared `_select` function in
[`tools/mealie_tools.py`](../harness/ceiling-test/tools/mealie_tools.py). The fail-open path is
**structurally unreachable** through the tool. That is a stronger claim than "the tool arm got it
right on five attempts", and it needs no rate to stand up.

**But the immunity is a property of human authorship at tool-writing time, not a property of the
tool abstraction.** A tool synthesized from `GET /api/recipes` would wrap `categories` — it is a
documented query parameter on a documented operation, exactly the kind of thing a synthesis pass
promotes — and would inherit the defect precisely as the shell agent did. Nothing about being
called through a function signature rather than through `curl` changes what the server does with an
unresolvable value.

This matters because the fail-open was the cleanest safety argument for a curated surface in the
whole record, and **it does not survive in the form it was stated.** What survives is narrower and
still worth having:

- A *well-written* tool can encapsulate the hazard. That is what "ceiling" means, and E7 measured
  the ceiling.
- Nothing here shows that synthesis would produce a well-written one, and the specific thing that
  made this tool safe — declining to use the API's own filter and reimplementing it client-side —
  is a decision a generator has no basis for making.
- Therefore the safety claim **does not transfer to a generated stack absent an explicit mechanism
  for detecting fail-open parameters**, and no such mechanism exists or has been designed.

A generator emitting one tool per operation reproduces the shell arm's failure with a nicer
calling convention. That is the same shape as [finding 012](012-ceiling-test-per-family.md)'s
finding that twenty mechanically-derived tools lose to a `jq` pipeline, arriving from the safety
side rather than the cost side.

## The rate is not measurable this way, and buying more attempts would have manufactured precision

The run was commissioned to measure how often the fail-open is tripped. It cannot be measured by
repeating attempts, and the reason is visible in the data rather than argued from theory.

| arm | attempts this run | false successes | pooled at fingerprint `365f7debbf2c2ea5` |
|---|---:|---:|---:|
| A | 5 | 0 | **0 of 6** |
| B | 5 | 0 | **0 of 6** |

Both arms passed with the correct 7 names every time. The naive Clopper-Pearson bound for zero
events in six draws is **[0, 39.3%]** on a one-sided 95% convention, or **[0, 45.9%]** two-sided.
Neither is trustworthy, because Clopper-Pearson assumes independent Bernoulli draws and these are
not draws at all:

| | turns | trajectory | tokens | submitted |
|---|---|---|---|---|
| Arm A, five repeats plus the paired run | 2, every time | `search_recipes` → `submit_answer`, every time | **8,889, all six, exactly** | the identical 7 names |
| Arm B, five repeats plus the paired run | 9, every time | eight `bash` calls → `submit_answer`, the identical sequence | 47,157 four times, 47,125 twice — a spread of 0.07% | the identical 7 names |

At temperature 0 the harness is replaying one trajectory, not sampling a distribution. **Five
repeats bought roughly one independent observation.** Taken at the level the variation actually
lives at — the session — the record holds **1 failure in 2 sessions**, a two-sided 95% interval of
**[1.3%, 98.7%]**, which constrains nothing whatsoever.

Five more Arm B attempts were affordable and were not bought. They would have moved the naive
one-sided bound from 39.3% to 23.8% while being five more copies of a fixed point: a tighter
number backed by no additional information. **$1.1056 of authorised budget was left unspent for
that reason**, and it is recorded here so that the decision is auditable rather than looking like
an underrun.

> A convention note, because the run's own notes mix two. The bounds quoted as
> "Clopper-Pearson 95%" for zero events — 45.1% at n=5, 39.3% at n=6, 23.8% at n=11 — are
> **one-sided** 95% upper bounds. The session-level [1.3%, 98.7%] is a **two-sided** 95% interval.
> On the two-sided convention the zero-event bounds are 52.2% and 45.9%. Both conventions are
> defensible; quoting them in one paragraph without labels is not, and the labels are added here.

**Failure mode of each occurrence: none occurred.** That is the honest answer to the question as
asked, and it is not the same as an answer of zero.

## The noise floor, measured for the first time

### Per-task coefficient of variation in spend, n = 5

| task | Arm A mean $ | Arm A sd | Arm A CV | Arm B mean $ | Arm B sd | Arm B CV |
|---|---:|---:|---:|---:|---:|---:|
| `R1.010` | 0.02791 | 0.00000 | **0.00%** | 0.01585 | 0.00000 | **0.00%** |
| `R1.012` | 0.02955 | 0.00000 | **0.00%** | 0.15570 | 0.00014 | **0.09%** |
| `R2.003` | 0.04166 | 0.01742 | **41.82%** | 0.25700 | 0.05954 | **23.17%** |
| `R2.014` | 0.02747 | 0.00001 | **0.02%** | 0.11548 | 0.06955 | **60.23%** |
| `R2.015` | 0.04524 | 0.00065 | **1.44%** | 0.24824 | 0.00041 | **0.16%** |

Variance is not a smooth property of an arm. It is **bimodality on specific tasks**, and it is
discrete: the arm takes one of two solution paths and the token count follows the path.

- Arm B `R2.014` is the widest cell measured — 7 turns and 18,743 to 20,106 tokens three times,
  8 turns and 43,103 once, 12 turns and 69,984 once. A 3.44× spread in cost.
- Arm B `R2.003` splits 13 turns (three times) against 12 and 9, a 1.90× cost spread.

### "The tool arm is near-deterministic" holds for four of these five tasks and fails on the fifth

Arm A's `R2.003` carries a **41.8% coefficient of variation**, the second-widest cell in the table.
The cause is the twenty-first tool:

| path | turns | tokens | tools used |
|---|---:|---:|---|
| aggregation | 2 | 8,553 | `aggregate_recipes` → `submit_answer` |
| retrieval | 3 | 16,619 and 16,631 | `search_recipes`, `get_recipe` → `submit_answer` |

Both paths are available only on surface **v2**. The `20260803T070942` diagnostic that found the
tool arm stable to within three tokens ran **v1**, where the fork does not exist. **Adding
`aggregate_recipes` is what introduced the tool arm's variance on this task**, which is the cost
side of the same trade [finding 012](012-ceiling-test-per-family.md) measured as a capability
gain: the model now has a choice, and it does not always make the same one.

### An open question: the quoted "run-to-run variance" envelope is mostly not run-to-run variance

[Finding 013](013-ceiling-test-budget-parity.md) characterises Arm B's spread between two
independent 900,000-token runs as min 0.339× / median 0.930× / geomean 0.867× / max 1.814×, and
names five tasks. Set that against how those same tasks behave when repeated *within* a session at
one fingerprint:

| task | cross-session: paired ÷ historical, cost | within-fingerprint spread over all six attempts, cost max ÷ min |
|---|---:|---|
| `R1.010` | 0.443× | **1.000×** — 4,079 tokens, six times, exactly |
| `R2.015` | 1.814× | **1.003×** — 76,733 to 76,846 tokens, 13 turns every time |
| `R1.012` | 0.930× | **1.002×** — 47,125 or 47,157, 9 turns every time |
| `R2.003` | 1.620× | 2.196× — 9 to 16 turns |
| `R2.014` | 0.343× | 3.436× — 7 to 12 turns |

The five-attempt figures used for the CV table above are 1.899× for `R2.003` and 3.436× for
`R2.014`; pooling the paired run's attempt in widens only the former.

**Three of the five are internally deterministic and yet sat at completely different values in the
two sessions.** `R1.010` was 10,392 tokens in one and 4,079 in the other, a factor of 2.55.
`R2.015` was 40,951 and then 76,845, a factor of 1.88. **A deterministic process cannot produce a
2.55× swing by sampling.** Something changes between sessions that repeated attempts within a
session cannot detect.

The tool arm is not exempt. Arm A's `R2.015` took 4 turns and 17,871 tokens in the paired run and
3 turns and 13,400 to 13,541 tokens in all five repeats, in a session that began thirty-five
minutes later — same fingerprint, same battery, same surface, same temperature, and no
within-session turn variation at all. That instance is unremarked anywhere in the run notes and it
is the cleanest one, because the tool arm's trajectories are otherwise byte-stable.

**This is recorded as an open question and no cause is proposed here.** Provider-side model
serving, cache state, container or fixture state, and time-of-day routing are all candidates and
this run distinguishes none of them. What matters for the record is the consequence: **a
between-session component exists, it is per-task larger than the within-session component, and it
is invisible to the only variance measurement anyone has taken.** It bears on every cross-session
comparison in this feature, including the one this finding was asked to adjudicate.

Note that [`research/11-validation-plan.md`](../../../research/11-validation-plan.md#93-harness-variance)
§9.3 defines the noise floor as the difference between **two independent full passes** — that is,
as a between-pass quantity. The floor measured below is a within-session quantity. **It is a lower
bound on the floor §9.3 actually asks for**, and the gap is not small.

### The floor on the ratio

The reported quantity is the ratio of mean Arm B spend per task to mean Arm A spend per task, so
its variance draws on both arms. Each of the five rounds is one independent replicate of the whole
five-task set:

```
round              1         2         3         4         5      mean       sd        CV
Arm A $/task    0.03827   0.03167   0.03828   0.03192   0.03168   0.03436   0.00357   10.397%
Arm B $/task    0.18619   0.15358   0.15421   0.14295   0.15534   0.15845   0.01629   10.279%
ratio B/A       4.8649    4.8492    4.0282    4.4791    4.9031    4.6249    0.3750     8.109%
```

Two constructions, because the two figures at issue were not built the same way:

- **Paired** — both arms from one run, as the 4.366× is. Read directly off the ratio row:
  **8.109%**. It is lower than either arm alone because the arms co-vary across rounds
  (r = 0.650) and the shared component cancels.
- **Unpaired** — arms from different runs, as the 5.059× is. Delta method with independent errors:
  √(0.10397² + 0.10279²) = **14.620%**.

Scaling from 5 measured tasks to the 27 the figures are reported over: for a fixed task list,
between-task variation cancels and only within-task run-to-run variance contributes, so the
standard error of the pooled mean shrinks by √(27/5) = 2.324.

| construction | CV at n = 5 | 2× floor | CV scaled to n = 27 | 2× floor |
|---|---:|---:|---:|---:|
| paired | 8.109% | **16.22%** | 3.49% | **6.98%** |
| unpaired | 14.620% | **29.24%** | 6.29% | **12.58%** |

## The §9.3 adjudication: the 5.059× → 4.366× movement is NOT reportable as a difference

The movement is a factor of 0.8630 — a **−13.70%** relative change, or **14.73%** in log units.
Against the four floors:

| construction | 2× floor | movement 13.70% | |
|---|---:|---|---|
| paired, n = 5, measured | 16.22% | below | **not reportable** |
| unpaired, n = 5, measured | 29.24% | below | **not reportable** |
| unpaired, n = 27, scaled | 12.58% | above by 1.12 pp | marginal |
| paired, n = 27, scaled | 6.98% | above | would be reportable |

It clears the bar outright under one construction of four and marginally under a second. **The
refusal does not turn on which construction wins a vote**, and there are four independent reasons:

1. **The applicable construction is the unpaired one.** The 5.059× pairs the tool arm from
   `20260802T160705-recalibration` with the shell arm from `20260802T173614-baseline-lookup-R1R2`
   — no shared run and no shared fingerprint, so the arms' errors do not cancel and the paired
   construction does not apply to it. At n = 27 that is a 12.58% bar against a 13.70% effect: a
   margin of 1.12 percentage points, **smaller than the uncertainty in the extrapolation that
   produced the bar**.
2. **Every floor in that table omits the between-session component**, and this run demonstrates
   that the component is real and per-task larger than the one measured — 2.55× and 1.88× shifts
   on tasks with literally zero replicate variance. The comparison at issue spans sessions. Its
   true floor is strictly above every number above.
3. **The n = 5 → 27 scaling leans on 22 unmeasured tasks**, using a per-task variance drawn from a
   five-task sample four of whose members were selected *for* volatility. The extrapolation is in
   the direction of overstating precision.
4. **An independent route already agrees.** [Finding 013](013-ceiling-test-budget-parity.md)'s
   bootstrap 95% interval on the paired ratio, [3.384, 5.423], contains 5.059 — computed from the
   task-level spread within one run, with no reference to this run at all.

§9.3 is a bar an effect must clear, not a coin-flip it must win. An effect that survives only the
most favourable of four constructions, by less than the error in that construction, against a
floor known to be understated, has not cleared it. **The two figures remain statistically
indistinguishable**, which is what [finding 013](013-ceiling-test-budget-parity.md) concluded from
a different direction.

What *is* newly reportable, and was not before: **a measured within-session noise floor exists**,
and amendment A1.3's requirement of three attempts per task now has a price attached.

## Cap utilisation — nothing bound, in any of the 50 attempts

| arm | caps | max turns | max tokens | max cost | max wall | exhausted |
|---|---|---|---|---|---|---|
| A | 40 / 300,000 / $1.20 / 600s | 3 (7.5%) | 16,631 (5.5%) | $0.0608 (5.1%) | 17s (2.8%) | 0 of 25 |
| B | 120 / 900,000 / $3.60 / 1800s | 13 (10.8%) | 89,015 (9.9%) | $0.2862 (8.0%) | 56s (3.1%) | 0 of 25 |

Means: Arm A 2.28 turns, 10,224 tokens, $0.03436; Arm B 8.84 turns, 48,404 tokens, $0.15845. All
50 attempts terminated `submitted_answer`; there was no `run_budget_halt`, so no attempt was
truncated by the run ceiling and no row is contaminated by one. Budget-exhaustion rate (amendment
A1.2) is **0 of 25** for both arms. Success 25 of 25 both arms, false success 0 in 50.

Arm A spent $0.8591 over 25 attempts and Arm B $3.9613 over 25. **On this five-task subset the
ratio of means is 4.611×** and the mean of the five per-round ratios is 4.625×; the run notes quote
the latter while attributing it to the former, and both are reported here because the difference
between them is itself a small illustration of how the ratio is constructed. Neither is comparable
to the 27-task figures: the task mix differs and four of the five were selected for volatility.

## What this costs to do properly

At this run's observed rates, amendment A1.3's three attempts per task per arm prices out at:

| scope | attempts | ≈ cost |
|---|---:|---|
| the 27-task R1/R2 lookup limb, both arms, 3 attempts | 162 | **$15.60** |
| the full 57-task battery, both arms, 3 attempts | 342 | **$33** |

Neither fits a $6.00 authorisation. **Both are floors rather than estimates**, because the rates
come entirely from lookup tasks: [finding 012](012-ceiling-test-per-family.md) records the tool arm
spending about $1 per attempt on the per-record family and exhausting its budget on three of four,
which is thirty times the lookup rate. A 57-task projection built from lookup rates understates
the families that actually cost money.

## Threats to validity

- **The between-session component is unmeasured**, and this run shows it is the dominant one for
  the comparison at issue. Measuring it needs runs separated in time, not attempts separated in
  sequence — which is what §9.3 asked for in the first place.
- **Five tasks, four of them volatility-selected.** The per-task coefficients here are not a random
  sample of the battery and the extrapolation to 27 inherits the selection.
- **`R1.012`'s false-success rate is still effectively unmeasured**, at roughly one independent
  observation per session. Temperature is pinned at 0; a rate would need independent sessions or a
  deliberate perturbation, and neither is in this design.
- **The fail-open probe is recorded but not committed as a script.** Its five rows were run by hand
  against the live instance and appear only in the run's
  [`NOTES.md`](../harness/ceiling-test/results/20260803T072053-repeats5-noisefloor-R1012/NOTES.md).
  The two rows that matter most are independently corroborated by committed traces — `Breakfast`
  returning 60 and the UUID returning 7 — but the `zzzz-not-real` and empty-string rows rest on the
  note alone. Against SC-005's bar, a stranger cannot reproduce those two without writing the probe
  themselves. It costs $0 to fix and has not been fixed.
- **Both arms are at 100% on these five tasks**, so success rate carries no information and no
  decision-table verdict is claimed. `TSR(A) = 1.00` remains outside the pre-registered 0.25–0.85
  band, which **VOIDs** the decision table for verdict purposes.
- **One model, one target application.** The fail-open is a Mealie property. Its *class* —
  unresolvable filter values silently ignored — is common enough to be worth generalising as a
  hazard, but nothing here measures how common.

## What this evidence does not license

It does not license a false-success rate for `R1.012` or for anything else. The measurement was
attempted and the design cannot produce one; reporting [0, 39.3%] as a rate would be reporting the
harness's determinism as evidence about the model.

It does not license the claim that curated tools are safer than a shell. It licenses the claim that
**this** curated tool is immune to **this** hazard because a human declined to use the API's own
filter — and the negation, which is that a synthesized tool over the same operation would not be.

It does not license treating the measured floor as the floor. Every number in §The floor on the
ratio is a lower bound on the quantity §9.3 defines.

## Register entries needing propagation

Identifiers only. A separate pass edits
[`research/14-architecture-synthesis.md`](../../../research/14-architecture-synthesis.md), and new
entries are described rather than numbered here so that no identifier is cited before it exists.

| Entry | Current | Should become |
|---|---|---|
| **D-21** — synthesis, promotion selection, effect classification and decomposition are v2 | The v2 efficiency case carries the cost range and the "burns its budget outside its surface" liability | **Add a second liability, of a different kind.** The fail-open immunity that made the curated surface look *safer* is an artifact of human tool authorship and does not transfer to synthesis. A v2 synthesis layer inherits its target's fail-open parameters unless it detects them, and no detection mechanism exists or has been designed. The efficiency case is unchanged; the safety case is withdrawn as stated. |
| **C-14** — the same framework's published metadata is exact on one question and quietly wrong on the next | Three instances, all in the emission path: `.gitignore`, the alias generator, the `Allow` header | **Fourth instance, and the first where the unreliability is silent, successful, and on the *runtime* path rather than the analysis path.** A documented, correctly-typed query parameter answers HTTP 200 with the entire unfiltered collection for any value it cannot resolve, and the published schema describes the parameter accurately while saying nothing about this. Contract-derived verification that accepts a 200 plus a well-formed body cannot see it. |
| **New entry, next free `U` number** | — | **NEWLY OPENED — a between-session shift exists in the harness that repeated attempts cannot detect, and nobody has explained it.** Three tasks are byte-deterministic across six attempts within a session yet sit at 2.55× and 1.88× different token counts across two sessions at the same fingerprint, same battery, same surface, temperature 0. The tool arm shows it too (`R2.015`, 4 turns against 3). Cause unknown; candidates include provider-side serving, cache state and container state, and this run distinguishes none of them. **Blocking for every cross-session comparison in the record**, which includes the whole E7 cost result. Resolve by running one arm against itself in two sessions separated in time — which is exactly what §9.3 prescribed and what has never been done. |
| **New entry, next free `C` number** | — | **NEWLY OPENED — the safety argument for a curated surface points the opposite way from the synthesis argument.** The curated tool is safe *because a human overrode the API's own filter*, which is precisely the judgement a generator does not have. The better the safety story for hand-written tools, the worse the story for synthesized ones, from the same evidence. Resolution requires either a mechanism that detects fail-open parameters at synthesis time, or an explicit statement that emitted tools inherit their target's defects. |
| **§9.3 harness variance, and every "tie" in the E7 record** | §9.3 prescribes two independent full passes; it was never executed, and every E7 comparison to date is single-attempt | **Record both.** A within-session substitute is now measured — 8.1% paired and 14.6% unpaired at n = 5 — and it is a **lower bound** on the between-pass quantity §9.3 defines. Effects previously described as ties were called ties with no floor to call them against; they remain ties, now for a stated reason rather than an assumed one. Any reader applying the 2× rule to a cross-session figure is applying it against a floor known to be too low. |

## Reproduction

The harness is committed at [`harness/ceiling-test/`](../harness/ceiling-test/); the convention for
re-running it is in its [README](../harness/ceiling-test/README.md#reproducing-a-run).

| run | fingerprint | surface | design | spend |
|---|---|---|---|---|
| [`20260803T071942-smoke-precheck-gapfill`](../harness/ceiling-test/results/20260803T071942-smoke-precheck-gapfill/) | `365f7debbf2c2ea5` | v2 | `R1.001`, both arms, setup de-risk | $0.0740 |
| [`20260803T072053-repeats5-noisefloor-R1012`](../harness/ceiling-test/results/20260803T072053-repeats5-noisefloor-R1012/) | `365f7debbf2c2ea5` | v2 | 5 tasks × 5 attempts × 2 arms | $4.8204 |

Session total **$4.8944** against a $6.00 authorisation. Projected before launching at $4.9494 from
[finding 013](013-ceiling-test-budget-parity.md)'s per-task rates; actual came in 1.1% under.
Nothing halted.

The fingerprint matches [finding 013](013-ceiling-test-budget-parity.md)'s paired run, so the two
are poolable and are pooled where this document says "six attempts". It was reproduced from source
*before* any spend, via `python3 -c "import runner; print(runner.harness_fingerprint('v2'))"`, and
the runner reprinted it in both run headers and stamped it on every result row. The target's image
digest and reported version were both checked against `config.json` before spending, and the
fixture was verified against the frozen baseline before and after. No write tasks were in scope, so
no restore was triggered. No credential value was read, printed, logged or committed; the dotenv
tree was named to the harness through `F2A_ENV_ROOT` and resolved by
[`envroot.py`](../harness/ceiling-test/envroot.py) (FR-020).
