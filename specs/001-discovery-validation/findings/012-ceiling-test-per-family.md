# Finding 012 — Per family, the tool surface never wins on success and always wins on cost

**Date**: 2026-08-02
**User Story**: 1 (does a curated tool surface beat a capable general agent?)
**Owner decision**: [OD-05](../plan.md#od-05--aggregation-tools-admitted-under-a-task-blind-rule-e7-restructured-to-report-per-family)
**Model spend**: $6.58 this session, **$24.73 across four sessions**, tallied from recorded
per-attempt costs in `results/`. Against the ~$25 authorised for these two limbs, they cost
**$6.58**. The full battery did not run and the $120 authorised for it was not spent.

> **Basis note added 2026-08-03.** The four-session figure has two legitimate bases and $24.73 is
> the looser of the two. Summed directly from the committed per-attempt rows and negative-control
> rows in `results/`, the grand total is **$24.6705 → $24.67**; $24.73 is the sum of the three
> rounded per-session figures ($7.59 + $10.56 + $6.58) and additionally carries roughly $0.05 of
> session-1 negative-control spend that was incurred but never committed. **$24.67 is the
> artifact-verifiable floor; $24.73 is spend actually incurred.** This session's own $6.58 is
> artifact-exact ($6.5793). See [finding 009](009-ceiling-test.md)'s spend correction; nothing about
> any budget conclusion changes at this scale.
**Method**: one aggregation tool added under a rule pre-registered before it was written; the
per-record family re-probed under both tool surfaces; the shell baseline scored for the first
time on the 27 lookup tasks. Every outcome decided programmatically against the application's
observable state; no model judged any result.

Numbering note: `009` is this experiment's, `010` and `011` are the parallel
deployment-reachability work. `012` was the next genuinely free number.

---

## The headline

**Across all three families now measured, the tool surface does not win a single one on success
rate. It ties on two and loses on one. It is cheaper on every family, by ~~5× to 9×~~
2.2× to 9.3× wherever it succeeds at all.** *(Range corrected 2026-08-03. "5× to 9×" excluded this
document's own join figure even as first written; that figure has since been recomputed from 2.8×
to **2.20×**, so the lower bound moves again. See the correction below the table.)*

| family | tasks | tool arm | shell baseline | verdict |
|---|---|---|---|---|
| `R1`+`R2` lookup | 27 | **27/27** (100%) | **26/27** (96%) | tie on success; tool arm **5.06× cheaper per attempted task** (5.25× per solved) |
| `R4` join-and-arithmetic | 10 | 9/10 | 10/10 | tie; tool arm ~~2.8×~~ **2.20× cheaper per solved** |
| `R4` per-record | 4 | 2/4 (v2) · 1/4 (v1) | **4/4** | **baseline wins**; tool arm **3.84× more expensive per solved** (v2), 11.57× (v1) |

The lookup family was the region most favourable to the thesis, and it was the last one
unmeasured. It came back a tie. That is the single most important number in this document,
because if a curated surface cannot beat a shell on lookups it is unlikely to beat one anywhere,
and the remaining case for it has to be made on cost rather than capability.

> **Correction, 2026-08-03 — the join figure in the table above was 2.8× and is 2.20×; the lookup
> and join figures were quoted adjacently on different denominators; and the lookup comparison is
> cross-run.** Success rates and every verdict in this document are unchanged.
>
> What was believed: that the join family's cost ratio was **2.8× per solved task**, that **5.0×**
> and 2.8× were comparable figures, and that the lookup comparison was a paired one.
>
> What is now known, on three separate points:
>
> **1. The join ratio is 2.20×.** [finding 009](009-ceiling-test.md)'s cost row divided post-fix
> cost totals by the *pre-fix* solved counts of 8 and 7, while the success row directly above it
> was the post-fix 9 and 10. On the post-fix basis that governs, the tool arm spent **$1.5444 over
> 9 solved** and the baseline **$3.7687 over 10 solved** — **$0.1716 against $0.3769, a ratio of
> 2.20×.** Consistently pre-fix it would be 2.73×. See finding 009's Limb 1 correction for the
> two qualifications that travel with it: the magnitude is set almost entirely by `R4.001`
> (removing it moves the ratio to **4.20×**, a 91% shift on one task of ten, and that task consumed
> 94% of the raised token cap), and it ranges over **2.17×–2.73×** depending on which of the two
> attempts on the three re-measured tasks is treated as authoritative.
>
> **2. Two of the three headline ratios were on different bases.** "5.0×" was cost per *attempted*
> task; "2.8× per solved" was per *solved*. Either is defensible and presenting them adjacently
> without labels is not. Both bases, computed from the committed rows:
>
> | family | per attempted task | per solved task |
> |---|---|---|
> | lookup | **5.06×** cheaper | **5.25×** cheaper |
> | join | 2.44× cheaper | **2.20×** cheaper |
> | per-record (v2 surface) | 1.92× **more expensive** | **3.84× more expensive** |
>
> **3. The lookup comparison pools two runs with different harness fingerprints, and its budget
> asymmetry is 6× rather than the 3× the pre-registration committed to.** The tool arm's 27
> lookup attempts come from
> [`results/20260802T160705-recalibration/`](../harness/ceiling-test/results/20260802T160705-recalibration/)
> — battery **1.2.0**, fingerprint `35c8ef293cf0611c`, arm-A budget **20 turns / 150,000 tokens /
> $0.60**. The shell arm's come from
> [`results/20260802T173614-baseline-lookup-R1R2/`](../harness/ceiling-test/results/20260802T173614-baseline-lookup-R1R2/)
> — battery **1.4.0-probe**, fingerprint `f9abf1d35e94e32e`, arm-B budget **120 turns / 900,000
> tokens / $3.60**. The harness's own rule is that
> [results carrying different fingerprints must not be pooled](../harness/ceiling-test/README.md),
> and amendment **A1.1** committed to holding arm B at 3× arm A. Across this pairing the ratio is
> **6× on every axis**, because the tool arm's figures predate the OD-04 raise that doubled arm A.
>
> **Scope of this correction.** Neither arm came near binding. The tool arm's worst lookup attempt
> took **3 turns and 19,926 tokens against a 150,000-token cap**; the shell arm's worst took **17
> turns and 127,736 tokens against 900,000**, and it exhausted nothing on any of the 27. So
> **neither arm was constrained by the asymmetry and the 26/27-versus-27/27 tie is not an artifact
> of it.** The
> disclosure is owed anyway: the comparison is cross-run, it was not labelled as such, and a reader
> checking it against the harness's pooling rule would find it in violation. What changes is the
> magnitude and its provenance, not the direction, and not any verdict below.

---

## Limb 1 — aggregation helps exactly where it applies, and nowhere else

OD-05 authorised **one** tool under a rule written into `PREREGISTRATION.md` before the tool
existed (amendment A5.1): *the surface may contain any tool a competent engineer would write
knowing the application domain but blind to the specific tasks.* The rule was appended at 17:30;
`tools/mealie_tools.py` still carried its 15:10 timestamp at that moment.

`aggregate_recipes` computes one number over a filtered recipe set and returns only that number.
It takes **the same filter vocabulary as `search_recipes`** — the two now share one filter
function, so the aggregation tool provably has the search tool's selectivity and not one filter
more. It adds a metric (`count`, `sum`, `mean`, `min`, `max`, `argmax`, `argmin`) and a field
drawn from a complete enumeration of the scalars a single recipe yields.

### It reaches two of the four tasks, and I left it that way

| task | needs | covered? |
|---|---|---|
| `R4.011` count where instruction steps > 4 | a threshold filter on a derived field | **no** |
| `R4.012` sum instruction steps in Dessert | category filter + sum | yes |
| `R4.013` recipes using both cups and grams | a filter on ingredient units | **no** |
| `R4.014` which recipe has the largest total quantity | argmax | yes |

Extending the filter vocabulary would have covered the other two. I did not, because the only
thing available to justify those particular filters is the tasks that need them, which A5.1
forbids. **The coverage gap is reported as a result, not repaired.**

### Both surfaces, side by side

One attempt per task. The v1 result is preserved, not superseded.

| task | aggregable | tool arm v1 (20 tools) | tool arm v2 (21 tools) | shell baseline |
|---|---|---|---|---|
| `R4.011` | no | fail, $0.972, budget exhausted | fail, $1.007, budget exhausted | pass, $0.343 |
| `R4.012` | yes | pass, $0.069, 3 turns | pass, $0.028, 2 turns | pass, $0.201 |
| `R4.013` | no | fail, $1.014, budget exhausted | fail, $0.966, budget exhausted | pass, $0.186 |
| `R4.014` | yes | fail, $1.006, budget exhausted | **pass, $0.029, 2 turns** | pass, $0.328 |
| **total** | | **1/4**, $3.06 | **2/4**, $2.03 | **4/4**, $1.06 |

`R4.014` is the whole effect in one row: the same task, the same model, the same budget, moving
from *exhausted 300,000 tokens and submitted nothing* to *answered in two turns* for **1/35th of
the cost**. Nothing changed except that one tool returned the answer instead of the records.

**On the two tasks aggregation covers, the tool arm solves both for $0.057 against the
baseline's $0.529 — 9.3× cheaper.** On the two it does not cover, the tool arm solves neither
and spends $1.97 failing.

This is the claim OD-05 said may be made, and the evidence supports it in the precise form OD-05
specified: **tools that return answers help; tools that return records do not.** It is a
constraint on tool synthesis, not a win for the product. A generated surface that emits one tool
per endpoint reproduces the v1 result — twenty tools that lose to a `jq` pipeline — and the
20-tool surface is exactly what a naive synthesis pass would produce.

**The tool arm still loses the family, 2 to 4.** One authorised tool moved it from 1 to 2. Two
more would likely have taken it to 4, which is precisely why the rule capping the addition at one
is load-bearing rather than decorative.

---

## Limb 2 — the baseline on the lookup family, the arm nobody had run

27 tasks, one attempt, the shell arm's full 900,000-token budget. Priced before spending at
≈$2.40 expected and ≈$8 worst case, from the two lookup tasks the baseline had run in the smoke;
it came in at **$4.55**, above the point estimate and inside the bound.

| | tool arm (v1, 20 tools) | shell baseline |
|---|---|---|
| passed | **27/27** and **27/27** on two independent passes | **26/27** |
| false successes | 0 | **1** |
| cost | $0.034/task | $0.169/task |
| turns | 2.3 | 9.5 |
| budget exhausted | 0/27 | **0/27** |

The baseline exhausted nothing. It was not handicapped; it simply took four times as many turns
and five times the money to reach the same place.

A 27/27 against 26/27 on a single attempt each is **a tie**. One task on a battery of 27 is not
distinguishable from noise, and with one attempt per task there is no variance estimate to argue
otherwise. Reporting this as a win for the tool surface would be rounding a tie into a result,
which the pre-registration forbids.

### The one failure is more interesting than the score

`R1.012` asked for every recipe in the `Breakfast` category. The baseline answered with **all 60
recipes** and reported success — a D1 false success, the co-primary metric.

I checked whether this was the harness's fault, since every prior session has produced a defect
and the false success landed on the one task in this family I had hand-redesigned. It is not. The
oracle is right, the category exists, and it holds 7 recipes. The trace shows the baseline:

1. read the OpenAPI schema and found the correct endpoint and the correct parameter,
2. listed `/api/organizers/categories`, so it **held the correct identifiers**,
3. then queried `?categories=Breakfast` using the display name, and did not question the result.

The application's filter **fails open**. Verified directly against the running instance:

```
?categories=Breakfast  ->  60 recipes   (display name: filter silently ignored)
?categories=breakfast  ->   7 recipes   (the slug)
?categories=<uuid>     ->   7 recipes
```

**The baseline did not fail to find the endpoint. It found it, held the right values, and was
silently handed the unfiltered collection by a parameter that neither errors nor returns zero on
a plausible-looking wrong value.** `search_recipes(category='Breakfast')` cannot fail this way,
because the identifier discipline is encoded in the tool.

This is the strongest single piece of evidence for the product thesis that E7 has produced, and
it is not the argument the thesis was built on. The premise was discoverability — 259 operations
against 20 named ones. Discoverability was never the problem: the baseline found the right
endpoint on all 27 tasks. **The failure mode a curated tool actually prevents is correctness
against an API that fails open.** That is a narrower claim, it is worth more than the broad one
because it names a mechanism, and it rests on exactly one observation.

---

## What this does to the per-family picture

**There is now no measured family in which the tool arm succeeds more often than the baseline.**

The lookup family was the last plausible candidate and it tied. The joins tied. The per-record
family the baseline wins outright even after the treatment was corrected.

What survives is a consistent, large cost difference wherever the tool arm succeeds at all:
**5.06× per attempted lookup task** (5.25× per solved), ~~2.8×~~ **2.20× per solved join**, and
9.3× on the aggregable per-record tasks. The direction never reverses. It is the one effect in E7
that has replicated across every family measured. *(Join figure and basis labels corrected
2026-08-03; see the correction under §The headline. The 9.3× is computed over the **two** aggregable
tasks and not over the family, which loses 3.84× per solved on the v2 surface.)*

The corresponding liability is also consistent: **where no tool fits the question, the tool arm
does not degrade gracefully — it burns its entire budget and submits nothing.** Three of its four
per-record failures are budget exhaustion, not wrong answers. The shell arm has never once
exhausted its budget across 31 scored attempts. A tool surface is a bet that the question falls
inside it, and the cost of losing that bet is total.

---

## Whether the full battery is still worth running

**My recommendation: do not run it.** Spend a fraction of it on the two things that are actually
undetermined.

The reasoning:

- **The primary metric is saturated.** Success rate on lookups is 100% against 96%, and on joins
  9/10 against 10/10. The pre-registered calibration band is 0.25–0.85 and the tool arm sits at
  1.00 on 27 of the 41 measured tasks. A metric pinned at its ceiling cannot discriminate, and
  OD-04 correctly declined to swap the primary metric to rescue it. The honest consequence of
  both decisions together is that **the experiment as designed cannot answer its question**, and
  a larger n makes a saturated measurement more precise rather than more informative.
- **The battery it would have to run is forbidden.** The 61-task intermediate composition may not
  be used for a full run (A5.6), and OD-04's rebalance was stopped by its own pre-declared stop
  condition. There is no authorised battery to run $120 through.
- **Per-family reporting already delivered the product decision.** OD-05 asked which *kinds* of
  operation deserve tools. The three probes answer it: aggregation and identifier-disciplined
  lookup do; record retrieval does not. A pooled score across 61 tasks would average these into a
  number describing nothing, which is the argument OD-05 made for per-family reporting in the
  first place.

The two things worth buying instead, at maybe $15 total:

1. **Replication of the `R1.012` mechanism.** The fail-open finding rests on one observation and
   is currently the best argument for the product. A handful of tasks built deliberately around
   parameters that fail open would establish whether it is a mechanism or an anecdote. Note the
   hazard honestly: this is designing tasks toward a known tool-arm advantage, so it must be
   pre-registered as a *mechanism probe* and never pooled into a headline success rate.
2. **Three attempts on the tasks that discriminate.** Every number here is single-attempt. There
   is no noise floor anywhere in this finding, and the differences being called ties are being
   called ties on the reasonable but unmeasured assumption that one task in 27 is noise.

---

## Did the task-blind rule hold?

**It held, and it strained in one identifiable place.**

It held where it mattered most. The tool's filter vocabulary is the search tool's filter
vocabulary, shared through one function, so no filter was added for a task. Two of the four tasks
are consequently unreachable and I left them unreachable, at the cost of the limb.

It strained on the **field enumeration**. `instruction_count` and `total_ingredient_quantity` are
exactly the two fields the two covered tasks need, and I knew that when I wrote the list. My
defence is that the list is a *complete* enumeration of the scalars a recipe yields — all eleven
of them — and no principled enumeration of "numbers you can compute from a recipe" excludes the
count of its instructions. A reader should nonetheless know that a task-aware author wrote it, and
that completeness was the only thing standing between that authorship and task-shaped selection.

The rule also did real work in the negative: I twice considered extending the filters to reach
`R4.011` and `R4.013` and stopped, because the only available justification was the tasks. Under
a weaker rule the tool arm would now read 4/4 on this family, and that number would be worthless.

---

## Threats to validity

- **Every figure here is single-attempt.** No noise floor exists for any comparison in this
  document. The two ties are asserted on the judgment that a 1-in-27 and a 1-in-10 gap are within
  noise, not on a measurement of noise.
- **The tool arm's lookup score is from the v1 surface.** Adding `aggregate_recipes` could only
  help, and 27/27 cannot improve, so the comparison is not disadvantaged — but the two surfaces
  were not run on this family under identical conditions.
- **The fail-open finding is n=1.** It is the most consequential observation in this document and
  the least replicated.
- **The per-record family is four tasks.** A 2-versus-4 split on n=4 is suggestive and nothing
  more; the underlying pattern (exhaustion when no tool fits) is what carries weight, not the
  ratio.
- **I authored both the tools and the tasks.** Task-blindness for the new tool is enforced by a
  pre-registered rule and checkable file timestamps, which is better than nothing and weaker than
  independent authorship.
- **One model, one target application.** Nothing here separates properties of curated tool
  surfaces from properties of Claude Sonnet 4.5 against Mealie.
- **Cost ratios depend on the budget configuration**, which has been amended three times. They are
  robust in direction across every family measured; their magnitudes are not portable.
- **The lookup cost comparison is cross-run, and its budget asymmetry is 6× rather than 3×**
  (added 2026-08-03). The two arms come from runs carrying different harness fingerprints, which
  the harness's own rule forbids pooling. Neither arm came near binding, so the tie stands; the
  magnitude carries this provenance. See the correction under §The headline.
- **Two of the three headline ratios were on different denominators** (added 2026-08-03) — the
  lookup figure per *attempted* task, the join figure per *solved* task. Both bases are now
  tabulated; neither is wrong, and quoting them adjacently unlabelled was.

## What this evidence does not license

It does not license the claim that application-specific tools make an agent **more capable**. On
41 tasks across three families, measured, they did not — the baseline matched or beat the tool
surface everywhere. It does not license a pooled E7 verdict of any kind; there isn't one, by
design. It does not license the claim that the fail-open mechanism generalises, on one
observation. And it does not license retiring the thesis either: a consistent ~~3–9×~~ **2.2–9.3×**
cost advantage wherever the tool arm succeeds is a real result, it replicated across every family,
and cost is a legitimate basis for a product — just not the one this experiment was built to test.
*(Range corrected 2026-08-03: the lower bound was 3× here and 2.8× after `plan.md` OD-07's first
correction; on the post-fix basis the join ratio is 2.20×, so it is 2.2×. This figure has now been
wrong in two successive directions and should be quoted with its basis attached.)*
