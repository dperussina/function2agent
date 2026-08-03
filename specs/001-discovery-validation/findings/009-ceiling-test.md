# Finding 009 — The bias probe stopped the rebalance: the baseline wins the composition family

**Date**: 2026-08-02
**User Story**: 1 (does a curated tool surface beat a capable general agent?)
**Owner decision**: [OD-04](../plan.md#od-04--what-e7-measures-rebalance-toward-composition-and-raise-the-budget)
**Model spend**: $10.56 this session, $18.09 across three sessions, as tallied from the
recorded per-attempt costs in `results/`. **The full battery did not run and the $120
authorised for it was not spent.**

> **Correction, 2026-08-03 — the $18.09 is right and the figure that was called right is the one
> that is off. Two accounting bases exist and both are legitimate; neither is an error.**
>
> What was believed: that "$18.09 across three sessions" was a six-cent transcription error,
> because the per-session figures reported in the findings sum to $18.15 ($7.59 + $10.56), and
> that $18.15 and the four-session $24.73 were therefore the correct figures.
> [`VERDICT.md`](../VERDICT.md) §6 and §8 recorded it that way.
>
> What is now known, recomputed from the committed artifacts:
>
> | figure | basis | artifact-exact value |
> |---|---|---|
> | sessions 1–3 | committed per-attempt costs in `results/` plus the committed negative-control rows | **$18.0912 → $18.09** |
> | all four sessions | the same, plus session 4 | **$24.6705 → $24.67** |
>
> So **$18.09 is artifact-exact and this document's provenance statement is accurate.** The
> four-session figure quoted as $24.73 is the one that runs about six cents high against committed
> artifacts, and $18.15 likewise.
>
> The two reconcile, which is why neither is an error. **$18.15 and $24.73 are the sums of the
> rounded per-session figures** the findings report ($7.59 + $10.56 + $6.58), and the session-1
> figure of $7.59 runs about eight cents above the $7.51 the committed artifacts hold. That excess
> is consistent with roughly **$0.05 of genuine session-1 negative-control spend that was incurred
> but never committed to `results/`**, plus stacked rounding across three session figures. So the
> two bases are an **artifact-verifiable floor** ($18.09 / $24.67) and a **spend-actually-incurred**
> figure ($18.15 / $24.73), and a figure should be quoted with the basis attached rather than one
> being deleted in favour of the other.
>
> **Scope of this correction.** No verdict changes and no budget conclusion changes: every figure
> here is a rounding-scale difference against a $120 authorisation that went unspent. What changes
> is the direction of the arithmetic note in `VERDICT.md` §6, which blessed the wrong number.
**Method**: budgets raised per OD-04, then the shell-arm bias probe run *before* the
rebalance as OD-04 sequenced it, with the tool arm run over the same tasks at the new
40-turn budget. Every outcome decided programmatically against the application's observable
state; no model judged any result.

Numbering note: `008` was briefly held by two documents, this experiment's calibration
finding and the parallel deployment-reachability work. The latter has since moved to `010`,
so the collision is resolved and `009` was free.

---

## The headline

**The probe met OD-04's stop condition, so I did not rebalance.**

On the composition family the shell baseline beat the tool arm. On the per-record tasks
that OD-04 newly admits — the ones a raised turn budget was supposed to unlock — the split
was **4 of 4 for the baseline against 1 of 4 for the tool arm**, with the tool arm
exhausting its 300,000-token budget on three of the four. On the join-and-arithmetic tasks
the corrected result was **10 of 10 against 9 of 10**, which is a tie within noise.

Growing `R4` toward twenty-five tasks would have built a battery the baseline wins. OD-04
anticipated exactly this and priced discovering it at $2 rather than after a working
session; it cost $10.56 and it was worth every cent of it.

**A second result matters as much as the first.** Three of the four probe failures were
caused by an ambiguous prompt rather than by either arm getting anything wrong, and the
ambiguity scored against the baseline. **It is the first defect in this harness whose
direction favours the product thesis.** Had I built fifteen more tasks in that style — which
is precisely what the rebalance instructed — I would have manufactured a win.

## The probe, in two limbs

Both limbs: one attempt per task, both arms, tool arm at the new 40-turn/300,000-token
budget, baseline at 120 turns/900,000 tokens.

### Limb 1 — join and arithmetic (the existing ten `R4` tasks)

| | Tool arm | Baseline |
|---|---|---|
| As first measured | 8/10 | 7/10 |
| **After removing prompt ambiguity** | **9/10** | **10/10** |
| ~~Cost per solved task~~ | ~~$0.19~~ | ~~$0.53~~ |
| **Cost per solved task — post-fix basis (governs)** | **$0.1716** | **$0.3769** |
| Cost per solved task — pre-fix basis, shown for comparison only | $0.1930 | $0.5278 |
| Turns per task | 4.6 | 15.0 |
| Budget exhaustion | 0/10 | 0/10 |

The corrected row is the one that counts, and getting to it is the interesting part.

> **Correction, 2026-08-03 — the cost row was computed on the pre-fix denominators while the
> success row above it was the post-fix one, and the resulting ratio was then rounded the wrong
> way. The corrected join ratio is 2.20×, not 2.8×.**
>
> What was believed: that the tool arm cost **$0.19** per solved join task against the baseline's
> **$0.53**, a ratio of 2.73× that was quoted downstream as **2.8×**.
>
> What is now known: those two figures divide the *post-fix* cost totals by the *pre-fix* solved
> counts of 8 and 7. Mixing bases inflates the tool arm's advantage, because it credits the
> baseline with neither of the two tasks the ambiguity wrongly failed it on while charging the tool
> arm against the smaller denominator. Computed consistently on the post-fix basis — the one every
> document in this record states is authoritative — the tool arm spent **$1.5444 over 9 solved
> tasks** and the baseline **$3.7687 over 10 solved tasks**:
>
> | basis | tool arm | baseline | ratio |
> |---|---|---|---|
> | **post-fix (governs)** | **$0.1716** | **$0.3769** | **2.20×** |
> | pre-fix, consistently applied | $0.1930 | $0.5278 | 2.73× |
>
> **Two qualifications the original text omitted, and both bear on whether the magnitude may be
> quoted at all.**
>
> **The magnitude is set almost entirely by one task.** Removing `R4.001` moves the ratio from
> **2.20× to 4.20×** — a 91% shift on one task of ten. That task succeeds *only* because of the
> OD-04 budget raise: it consumed **283,127 tokens, 94% of the raised 300,000 cap**, and under the
> prior 150,000 cap it would have failed. So the comparison sits roughly one turn from being
> budget-bound, and by the standard [finding 012](012-ceiling-test-per-family.md) states against
> itself — magnitudes depend on a budget configuration amended three times and are not portable —
> **2.20× should be read as a bound on this configuration, not as a rate.**
>
> **The figure moves on a bookkeeping choice.** Three tasks were re-measured after the prompt fix,
> so each arm has two attempts on each of them and the ratio depends on which is treated as
> authoritative. Holding both arms to the same attempt per task, the ratio ranges **2.17× to
> 2.73×**; allowing the two arms to be attributed independently widens it to **1.95× to 3.08×**.
> That is a wide band for a figure that was quoted to one decimal place.
>
> **Scope of this correction.** Nothing about the success counts changes: the join family is still
> 9/10 against 10/10 and still a tie within noise. Nothing about the direction changes either —
> the tool arm is cheaper per solved join task on every basis above. What changes is the
> magnitude, and the fact that it is now known to have been wrong in two successive directions:
> `plan.md` OD-07 already corrected this range once, from "3–9×" up to "2.8×–9.3×", specifically
> to stop quoting a lower bound the data did not support. The corrected lower bound is **2.2×**,
> so that replacement was also too generous. That history is the point rather than an
> embarrassment: a figure that has moved twice on recomputation from the same committed artifacts
> is a figure to quote with its basis attached.

Both arms independently answered 36 on `R4.006` where the oracle said 33. Two independent
agents reaching the same wrong answer through completely different mechanisms — twenty
curated tools in one case, `curl` and `jq` in the other — is not what error looks like. One
recipe appears twice in the breakfast slots. The oracle summed distinct recipes; both arms
summed entries. The prompt did not say which.

Auditing the family found the same flaw twice more, and **the baseline's answers were
exactly the per-entry values**: 3.35 where the distinct-recipe mean is 3.20, and 11 where
the distinct-recipe count is 9. The tool arm's `R4.005` answer of 3.23 matched neither
reading and was a genuine arithmetic error. `R4.007` had been written with "count each
recipe once" and both arms passed it, which isolates the cause beyond argument.

I disambiguated all three and re-measured: **the baseline answered all three correctly, the
tool arm two of three.** Every one of the baseline's failures in this limb was the
ambiguity. None was capability.

### Limb 2 — per-record breadth (four new tasks, the type OD-04 admits)

These require a detail fetch per recipe: instruction-step counts, ingredient units, summed
ingredient quantities. They did not exist before this session because at 20 turns they were
unreachable for the tool arm, which is why finding 008 excluded them and why OD-04 raised
the budget to admit them.

| | Tool arm | Baseline |
|---|---|---|
| **Task success** | **1/4 (25%)** | **4/4 (100%)** |
| Budget exhaustion | **3/4 (75%)** | 0/4 (0%) |
| Cost per solved task | **$3.06** | **$0.26** |
| Tokens per solved task | 955,506 | 80,318 |

**The tool arm did not get these wrong. It could not finish them within budget**, which
amendment A1.2 requires be reported as a distinct outcome and never conflated with error.
For the composition question the distinction does not rescue the conclusion, but it changes
what the result means: this is a statement about cost, not about correctness.

The mechanism is structural rather than incidental. Sixty records aggregated in a shell is
one pipeline whose output is a single number, so the model never sees the records. Sixty
records through a tool surface must pass through the model's context, and the transcript is
resent every turn. That is a difference in *where the aggregation happens*, and no amount of
tool-design care changes it.

**Doubling the tool arm's token budget did not fix this and a further raise would not
either.** Three of four attempts exhausted 300,000 tokens. Reaching these tasks might take
600,000 to a million, at which point the tool arm costs several dollars a task against the
baseline's twenty-six cents, and the efficiency claim does not merely weaken — it inverts.

## What the probe implies about bias direction

**On per-record breadth the battery would tilt hard toward the baseline**, and the tilt is
architectural. This is the risk OD-04 named and it is real and large.

**On joins with arithmetic the two arms are indistinguishable on success**, once the prompt
defect is removed, and they fail on the same things: both arms failed `R4.005` before the
fix, and the tool arm still fails it after. That family's difficulty comes from the model's
arithmetic, which both arms share, rather than from anything a tool surface affects. A
battery of such tasks measures the model, not the product.

Put together, **the composition family does not discriminate in the tool arm's favour on
either axis.** Where it separates the arms at all it separates them on cost, and there the
direction depends entirely on which axis you pick: the tool arm is ~~2.8×~~ **2.20×** cheaper per
solved join task and 12× more expensive per solved per-record task. *(Corrected 2026-08-03 —
see the correction under Limb 1. The 2.8× mixed a post-fix cost total with a pre-fix solved
count; on the post-fix basis that governs, the ratio is 2.20×.)*

## The defect this session found, and its direction

Five sessions, five sessions with a defect found. The negative control and the write-check
verifier both came back clean this time — the first clean adversarial pass — and the defect
surfaced from the probe instead.

Every earlier defect was neutral or cut against the tool arm: a write check that credited
inaction, a query engine that silently matched nothing on a misspelled field and failed the
tool arm for a correct answer, near-miss tasks passable by abstaining, a runner that left
the fixture dirty, a guessable expected value. **This one cuts the other way.** An ambiguous
question, scored against a defensible reading, took three tasks off the baseline and none
off the tool arm on net. It reads as a capability gap. It is a wording gap.

It would have been replicated fifteen times over by the rebalance, because the ambiguity is
inherent to the phrasing pattern that composition tasks invite — "recipes on the meal plan"
is ambiguous in exactly the way "recipes" is not. Any future composition task must state
whether repeated scheduling counts once or many times.

## What this does NOT license

- **No conclusion about the thesis.** No full battery has ever run. This is fourteen tasks
  from one family at one attempt each.
- **No claim that the baseline is better.** The join limb is a tie within noise: 10 versus 9
  on ten tasks with a single attempt is not a difference. Only the per-record limb is
  decisive, and it is decisive about **cost under a token budget**, not about capability.
- **No noise floor anywhere.** Every figure here is a single attempt. Nothing may be called
  real on this evidence.
- **No claim that the corrected join figures are a clean measurement.** They splice seven
  tasks from the original probe with three re-measured after the fix. That is the best
  available reading, not a controlled one.
- **No claim that per-record tasks are unfair *to the product*.** A real deployment could
  give a tool the ability to aggregate server-side and return a scalar — which is exactly
  what the baseline's `jq` pipeline does. The finding is that *these twenty hand-written
  tools* push aggregation into the context window. That is a fact about the tool set, and it
  may be the most useful thing this experiment has produced so far.

## What I recommend, and what is the owner's to decide

The rebalance target needs rethinking rather than executing, which is what OD-04 said this
outcome would mean.

The genuinely interesting finding is the one hiding inside the failure: **the tool arm loses
per-record tasks because its tools return records rather than answers.** That is a claim
about tool *design*, not about whether tools help — and it is testable cheaply. Three
options, ranked:

1. **Add server-side aggregation to the tool surface and re-probe the per-record limb.**
   One tool that accepts a filter and an aggregate and returns a scalar would move the
   aggregation out of the context window, which is what the baseline gets for free from
   `jq`. If the tool arm then wins the per-record limb, the product claim sharpens
   considerably: it is not "tools help" but "tools that return answers help, tools that
   return records do not." About $3 to test. **This is the one I would choose.**
2. **Drop per-record tasks and rebalance on joins alone.** Honest, but it builds a battery
   on a family where the arms tie and the difficulty is the model's arithmetic. It would
   most likely produce a null result at a cost of $120.
3. **Run the battery as it stands and report the split result.** Cheapest to reach, least
   informative: a known-mis-calibrated battery with a known ambiguity pattern.

Option 1 changes the tool set, and the tool set is the independent variable. **Changing it
after seeing a result is exactly the manoeuvre pre-registration exists to prevent, and I
will not do it on my own authority.** The defensible version is that the ceiling test asks
what an *ideal* tool surface achieves, aggregation tools are plainly part of an ideal
surface, and their absence was my oversight rather than a finding — but that reasoning is
available to anyone who wants to rescue any result, and it needs a decision on the record
rather than an engineer's judgement.

## Immediate next steps

1. Decide between the three options. Nothing else should proceed first.
2. If option 1: add the aggregation tool, record it as a dated amendment naming it as a
   correction to the tool surface rather than a response to a result, and re-probe the
   per-record limb before any rebalance.
3. Whatever is chosen, **every composition task must state whether a repeatedly scheduled
   recipe counts once or many times.** Three tasks have been fixed; the pattern will recur.
4. The battery currently stands at 61 tasks, which is an intermediate state — neither the
   57-task version 1.3.0 nor a rebalanced composition. **No full run should use it.**
5. Calibration and the full battery remain blocked behind the composition decision. The
   $120 is untouched, and the standing rule that a third failed calibration escalates to the
   owner rather than to another iteration still holds.
