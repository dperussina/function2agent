# E8 viability after the corpus-packaging defect

**Date**: 2026-08-03. **Status**: assessment, written after `harness/verifier-vs-judge/adjudication/REPORT.md`
and before any judge call. **Scope**: read-only over the committed artifacts. Nothing in
`harness/` was modified.

**What this document decides**: whether experiment E8 can still answer the question it was
pre-registered to answer, once the corpus is restricted to traces whose battery version matches
the task definitions every downstream consumer joins them against.

**Concurrency note.** Amendments **B1, B2 and B3** were appended to
`harness/verifier-vs-judge/PREREGISTRATION.md` while this assessment was being written. B1
independently reproduces two of the count corrections in §7 below, which is corroboration rather
than duplication. **B3 attempts the same repair this document assesses and gets it wrong in both
directions**; §8.1 sets out why, and it is the most consequential item here.

---

## TL;DR

- **The surviving discriminative n is 2**, not 11 and not 5. Restricting the frozen 246 traces to
  the current battery leaves **103 traces, 7 oracle-negatives, and 2 false successes**: one
  summation slip and one category-filter collapse. **Two traces, two phenomena.** A looser
  per-task join-validity rule leaves 3 traces and 3 phenomena.
- **The ≥ 10 pp gate is not answerable at that n, and the failure is not merely low power.** On the
  primary denominator a single trace is worth 14.29 pp, which clears the gate on its own even after
  the ×0.7681 pipeline discount. The gate boundary sits between "no traces detected" and "one trace
  detected". A coin flip on one judge verdict decides whether the verifier is half the product.
- **Three of the preregistration's own riders fire before a single call is made.** §6.5 forces
  *provisional* because the only numeric discriminative case is a sub-1% near-miss and removing it
  necessarily flips the verdict. §6.9 caps the verdict at *advisory* below n ≥ 30 across ≥ 3
  families; we have 2 across 2. S8 forces *not measurable* unless the judge is perfectly stable,
  because one verdict flip on a 7-trace denominator is a 14.29 pp noise floor. **No achievable
  outcome licenses the headline claim.**
- **The two verifier arms are not usefully separable, and the committed c1 arm has a bug that hides
  it.** On the contract, the schema-derived arm detects **0 of 2**: on the set-typed case the
  `/api/recipes` envelope returned `total: 60` and the agent submitted exactly 60 names, so clause 5
  — the one clause the preregistration named as having a chance at set errors — *affirms* the wrong
  answer. The implementation nonetheless returns `fail`, because it compares against `total: 8` from
  the **categories** endpoint while citing `/api/recipes` as its provenance. **That single clause
  evaluation is c1's only non-trivial detection in the entire 80-trace corpus.** Left as is, E8 would
  report marginal detection for a schema-derived verifier that detected nothing.
- **Real verifier verdicts already exist.** A dry run at 08:22 stubs the judge but computes c1 and c2
  for real on all 11 false successes. E8 is no longer in a state where "no result is visible", which
  constrains which amendments remain permissible.
- **The most valuable things left in E8 cost nothing and need no model call.** The set-typed failure
  is a silent server-side filter drop in which the request was schema-conformant, the response was
  schema-conformant, and the answer matched the application's own reported total. A schema-derived
  verifier cannot see that; c2 catches it only by recomputing the member set from a different field
  and never consulting the filter. That contrast — *an independent path to the truth, not a second
  pass through the same contract* — is a sharper design constraint on the product's verifier than
  the number the gate was going to produce.
- **The repair now in flight makes the denominator worse, not better.** Amendment B3 detects
  staleness by comparing each record's `expected` against today's `expected.json`. That detector has
  both a false-positive and a false-negative mode: it would drop 5 legitimate no-output negatives on
  a runner artifact, and it declares the 9 numeric false successes "all clean" when **7 of them ran
  under the pre-amendment `R4.005` / `R4.006` / `R4.008` prompts**. Applied as written it leaves
  N_fs at 10 while asserting the corpus has been repaired. See §8.1.
- **Recommendation**: retire the verifier gate on this corpus as a null on *power*, not on H2; fix
  the packaging and publish the structural findings, both at zero cost; spend at most a reduced
  judge-only run on a re-scoped corpus; do not fund the ≥ 30 harvest until someone decides the
  question is worth $150 to $460 and several hundred new tasks.

---

## 1. Method — how every trace's battery version was determined

Each run directory under `harness/ceiling-test/results/` carries a `manifest.json` with a
`battery_version` field. Every attempt record carries its `run_id`. Joining record to manifest
therefore dates each trace exactly, with no inference. The current battery, from
`harness/ceiling-test/tasks/tasks.json`, is **1.4.0-probe**.

The eleven run directories pinned by `corpus_freeze.json` span five versions:

| battery at run time | traces | oracle-negatives | false successes |
|---|---|---|---|
| 1.0.0 | 20 | 2 | 0 |
| 1.1.0 | 46 | 2 | 1 |
| 1.2.0 | 57 | 4 | 3 |
| 1.3.0 | 20 | 5 | 5 |
| **1.4.0-probe (current)** | **103** | **7** | **2** |
| total | 246 | 20 | 11 |

143 traces ran under a superseded battery, which reproduces the adjudication's count exactly.

I corroborated the version field against three independent signals rather than trusting it alone.

1. **Frozen answer against current answer.** Each record stores the `expected` value in force when
   it ran. Comparing that to `tasks/expected.json` finds exactly **7 records** whose answer moved —
   all `NM` tasks at 1.1.0 and 1.2.0, where a scalar or empty-set expectation became a two-element
   pair. Every other record's frozen expectation equals the current one.
2. **Behaviour.** Amendment A4.2 added "Count each recipe once however many times it is scheduled"
   to `R4.005`, `R4.006` and `R4.008`. That amendment can be dated from the results without reading
   it: `R4.006` and `R4.008` flip from the per-entry answers (36 and 11) to the deduplicated answers
   (33 and 9) precisely at the first 1.4.0-probe run, and pass. Recomputed from the seed fixture the
   deduplicated values are 33 and 9 and the per-entry values are 36 and 11, so the flip is exact
   rather than approximate.
3. **Structural incompatibility.** Three records carry a scalar `expected` against a current
   `answer_kind` of `numbers`, which the current prompt cannot produce.

**A limit on the method, stated because it bounds everything below.** The historical prompt text is
**unrecoverable**. There is no git history (the repository has a single commit); manifests record
`task_ids` but no prompt strings; and trace transcripts begin at the agent's first *assistant* turn,
so the task prompt is not in the trace. Re-scoping can only exclude traces. It cannot repair them.
For any task carrying no `quarantine_history`, join-validity rests on absence of evidence — and the
`NM` pair reformulation shows that a prompt change can happen without an amendment recording it.

---

## 2. The re-scoped corpus

Two defensible re-scopes, the rule amendment B3 proposes, and the frozen corpus for comparison.

| | as frozen | **strict** — run battery equals current | join-valid — per-task | B3 as written |
|---|---|---|---|---|
| rule | none | keep only 1.4.0-probe runs | drop traces whose task provably drifted | drop records whose `expected` differs from today's |
| traces | 246 | **103** | 230 | 234 |
| oracle-positives | 226 | 96 | 218 | 220 |
| oracle-negatives (N) | 20 | **7** | 12 | 14 |
| — no output | 7 | 5 | 7 | 2 |
| — protocol | 2 | 0 | 2 | 2 |
| — **false successes (N_fs)** | **11** | **2** | **3** | **10** |
| distinct phenomena among N_fs | 3 | **2** | 3 | 3 |
| families among N_fs | NM, R4, R1 | R4, R1 | R4, R1 | R4, R1 |
| prompt-drifted traces still in N_fs | 8 | 0 | 0 | **7** |

The join-valid rule excludes 16 traces (7 + 9): the 7 `NM` traces whose answer provably moved, and
the 9 `R4.005` / `R4.006` / `R4.008` traces that predate the A4.2 disambiguation. All 8 of the
negatives it excludes are false successes, which is why N_fs falls from 11 to 3 while N falls only
from 20 to 12.

**The task asked for the strict number, and it is 2.** I report the join-valid variant because it
is the more forgiving reading and because it bounds the answer from above: even under the most
generous rule that is defensible from the artifacts, the discriminative set does not reach 4. The
B3 column is not a fourth defensible rule — it is the rule currently proposed in the harness, shown
here so its effect is visible. §8.1 explains why its N_fs of 10 is not comparable to the other
three columns.

---

## 3. The surviving discriminative set, by phenomenon

**Strict re-scope — 2 traces, 2 phenomena, one of each answer type.**

**P1 — summation slip.** `R4.005`, arm A, run `20260802T165903-ambiguity-recheck`. Submitted `3.23`
against a true mean of 3.2017543859649122. Numeric-typed; relative error 0.882%. The transcript
enumerates the correct 19 rated recipes with the correct ratings, having correctly deduplicated the
26 distinct meal-plan recipes and correctly excluded the 7 unrated ones, then writes
`Sum = 61.3333333333333337` for a list that sums to 60.8333, and divides and rounds correctly from
there. Recomputed from `seed/fixture_plan.json`: the 19 ratings sum to 60.833333 and the mean is
3.2017543859649122. Right data, right method, wrong addition. This is a textbook case for a
postcondition-derived verifier.

**P2 — category-filter collapse.** `R1.012`, arm B, run `20260802T173614-baseline-lookup-R1R2`.
Submitted all 60 recipe names for a category containing 7. Set-typed. §6 below shows this is a
different and more interesting failure than "the agent listed too many things".

**Join-valid re-scope adds P3 — dropped list member.** `R4.001`, arm A, at battery 1.2.0. Submitted
`12` where the truth is 13. Recomputed from the fixture, the 13 recipes rated four or higher and
absent from the meal plan include `Wild Pepita Ragout`, which the agent omitted. Numeric-typed;
relative error 7.7%. Its join-validity rests on the task carrying no `quarantine_history` and its
frozen expectation matching the current one, which is weaker evidence than P1 and P2 enjoy.

**Why phenomena and not traces.** Repeated `(task, arm, battery)` cells in this corpus are
near-deterministic: of 50 such cells with more than one attempt on disk, **48 returned byte-identical
submissions**. `R4.005` arm A answered `3.23` at 1.2.0, at 1.3.0 and at 1.4.0-probe — the same slip
replayed, not three independent draws. Counting those as three cases inflates n without adding
information.

---

## 4. Where I agree with the adjudication, and where I do not

I recomputed the load-bearing facts from `harness/ceiling-test/seed/fixture_plan.json` in code I
wrote for this assessment, without reading `adjudication/truth.py`. Every substantive claim in the
report reproduces:

| adjudication claim | independent recomputation |
|---|---|
| `NM.001`'s 8 submitted names are exactly the Wok set | 8 recipes require the Wok; the submitted names match the set exactly |
| the current `NM.001` pair `[8, 0]` is right | 8 require the Wok, 8 require the Air Fryer, the intersection is empty |
| `R4.001` truth is 13, agent dropped `Wild Pepita Ragout` | 13 recipes rated ≥ 4 and off the plan, `Wild Pepita Ragout` among them |
| `R4.005` truth 3.2017543859649122, agent's list sums to 60.8333 | confirmed to 16 places; per-entry mean 3.353333, which is arm B's `3.35` |
| `R4.006` / `R4.008` deduplicated 33 and 9, per-entry 36 and 11 | confirmed exactly |
| `R1.012` truth is 7 Breakfast recipes | confirmed |

**So I agree with the classification of all eleven.** The five genuine, five ambiguity artifacts and
one oracle error are correctly assigned. Four qualifications follow.

**(a) The "5" answers a different question than the one E8 needs.** It is a *verdict-robustness*
count — which traces are genuinely wrong answers. E8 needs a *join-validity* count — which traces
can be shown to a judge or a verifier alongside the prompt the agent actually saw. `R4.005` arm A at
1.2.0 and 1.3.0 are genuinely wrong under either reading of the ambiguous prompt, so they survive
the first test and fail the second. The report's own §7 says "by distinct failure phenomenon there
are three", which is right; but the figure that propagates is the 5, and 5 is not the surviving n
for E8 under any rule.

**(b) The three `R4.005` replicates are one event.** Given 48-of-50 replicate determinism, the
effective n contributed by that phenomenon is 1, whichever re-scope is used.

**(c) A material omission on `R1.012`, and it changes the separability answer.** See §6. The report
treats the case as a set/cardinality error. It is a silent server-side filter drop, and the
distinction decides whether either derived verifier can catch it.

**(d) A second omission: the surviving numeric case is one of the near-misses the report itself
flags.** §6 of the report notes that reclassifying the three `3.23` traces as passes on a tolerance
argument would take three of the five genuine cases with it, and calls the sensitivity real. After
re-scoping it is worse than sensitive: the single surviving numeric discriminative case *is* a
`3.23` trace, so the tolerance argument does not reduce the set, it empties it of numeric content.

One thing the report says that deserves repeating rather than qualifying: it is not the
preregistered human adjudication. §4.1 requires a human. That requirement is open, and no E8 result
may be written up as resting on validated ground truth until it is closed, at any n.

---

## 5. Is the gate answerable at that n?

`MD_c` counts traces where the oracle failed, the judge passed and the verifier failed, over the
negative set. The gate is `MD_best`, discounted ×0.7681, at ≥ 10 pp.

**Granularity.** On the strict re-scope's primary denominator of 7:

| MD | raw | discounted | Wilson 95% | interval width |
|---|---|---|---|---|
| 0 of 7 | 0.00% | 0.00 pp | 0.0% to 35.4% | 35.4 pp |
| 1 of 7 | 14.29% | 10.97 pp | 2.6% to 51.3% | 48.7 pp |
| 2 of 7 | 28.57% | 21.95 pp | 8.2% to 64.1% | 55.9 pp |

**One trace is worth 14.29 pp raw and 10.97 pp discounted, so a single detection clears the gate by
itself.** The gate boundary lies between zero traces and one trace. On the false-success denominator
of 2 it is worse: one trace is 50.00% raw, 38.41 pp discounted, Wilson 9.5% to 90.5%. On the
join-valid denominator of 12 a single trace is 8.33% raw and 6.40 pp discounted, so two are needed
— out of a maximum of 3.

**The numerator is capped at 2.** Five of the seven strict negatives are no-output traces, which the
preregistration itself says every scorer catches trivially; a judge that fails them contributes
nothing to `MD`. So `MD` over N can only take the values 0, 14.29% or 28.57%, and reaching 28.57%
requires the judge to fail open on *both* surviving false successes and both verifiers to catch
them.

**The 95% interval at every attainable value spans more than a third of the scale.** At 1 of 7 it
runs from 2.6% to 51.3% — an interval that contains both "the verifier adds almost nothing" and "the
verifier catches half of everything the judge misses". §6.9 already requires that every report of
`MD` print the Wilson interval in the same sentence as the point estimate. Doing so honestly at this
n produces a sentence that says nothing.

**Three pre-registered riders fire before any call is made.** This is the decisive part, and none of
it requires knowing a result.

1. **§6.5 forces provisional.** Every verifier metric must be reported with and without the sub-1%
   near-misses. The only numeric discriminative case surviving the strict re-scope *is* a sub-1%
   near-miss. Remove it and the discriminative set is `R1.012` alone, which §6 below shows no
   faithful derivation catches — so `MD` is 0 and the gate fails. Keep it and `MD` can reach
   10.97 pp and the gate fires. **The verdict changes between the two variants by construction**, and
   §6.5 says that downgrades the verifier claim to provisional "regardless of which side of 10 pp it
   lands on".
2. **§6.9 caps the verdict at advisory** until the false-success base reaches n ≥ 30 across ≥ 3
   families. Re-scoped we have 2 across 2 families, or 3 across 2. The rider does not lift.
3. **S8 forces "not measurable" on any judge instability.** The judge noise floor is defined as the
   largest spread of the primary metric across the three single-replicate scorings, and S8 fires
   above 5 pp. On a 7-trace denominator **one verdict flip on one negative is 14.29 pp**. S8
   therefore fires unless all three repeats agree on all seven negatives in both judge arms.

**The honest answer is that no achievable outcome licenses the headline claim.** A result at or
above 10 pp is pre-committed to "provisional" by §6.5 and "advisory" by §6.9; a result below 10 pp
is pre-committed by §6.9 to triggering E9 rather than a narrative rewrite. The decision table's
first row — "verifier is a headline feature" — is unreachable on this corpus, and was already
unreachable at n = 11 before the packaging defect was found. Re-scoping does not create that
problem; it removes the last doubt about it.

**One further property makes running it actively worse than not running it.** Because a single
detection clears the gate, and because the one trace most likely to produce a detection is a genuine
recomputable arithmetic error that a postcondition verifier will certainly catch, the most probable
outcome of running E8 as designed on the re-scoped corpus is a *nominal pass* of a gate that no
rider permits anyone to cite. An instrument whose likeliest output is a number that supports the
project's preferred conclusion and that no one is allowed to use is worse than silence.

---

## 6. Are the two verifier arms separable?

The earlier note that 8 of the 11 false successes were numeric-typed and therefore invisible to a
schema-derived verifier is **arithmetically wrong and directionally right**, and after re-scoping it
stops being the binding problem.

**The corrected split.** Of the 11 false successes, **9 are numeric-typed and 2 are set-typed** — not
8 and 3 (see §7). After the strict re-scope the surviving set is **1 numeric and 1 set**, so the
cases are not all of one type. That would ordinarily be the good news. It is not, because the
schema-derived arm is blind to both.

**The schema-derived arm against P1 (`R4.005`, `3.23`).** A wrong float is a well-typed float.
Clauses 3 and 4 pass it. This is exactly the §7(5) predicted null, and it holds.

**The schema-derived arm against P2 (`R1.012`, 60 names for a 7-member category).** Walking the
committed clause list in §4.4:

| clause | verdict on this trace | why |
|---|---|---|
| 1 output presence | pass | a terminal `submit_answer` exists |
| 2 status-class conformance | pass | every call returned 2xx |
| 3 type conformance | pass | an array of strings, as declared |
| 4 enum / membership | pass | all 60 names are real recipe names in the app's own vocabulary |
| **5 cardinality** | **pass** | the agent queried `perPage=1` and read `total`; the app returned **60**; the agent submitted exactly 60 names, so submitted length equals the in-trace `total` |
| 6 abstention contract | pass | the request is satisfiable by a declared operation |

Clause 5 is the clause the preregistration singled out as one of "the only clauses with any chance at
the false-success set". **On the one set-typed case that survives re-scoping, clause 5 does not merely
miss the error — it certifies the wrong answer as correct.**

**The committed implementation returns `fail` here, and it does so on the wrong evidence.** A dry run
landed at 08:22 while this was being written; it stubs the judge but computes c1 and c2 for real, so
verifier verdicts on all 11 false successes now exist on disk. Its c1 entry for this trace reads:

> `C1.5` — "submitted collection has 60 member(s); the paginated envelope the app returned declared
> total=8", provenance "openapi paginated envelope `total` on /api/recipes".

**There is no `/api/recipes` envelope in this trace declaring 8.** Reading the transcript directly:
event 9 is `GET /api/organizers/categories`, whose envelope reports `total: 8` — the number of
*categories*. Event 11 is `GET /api/recipes?categories=Breakfast&perPage=1 | jq '.total'`, and it
returns `60`. The ground truth is 7 recipes. So the three numbers in play are 7 (truth), 60 (what
`/api/recipes` actually declared, and what the agent submitted) and 8 (an unrelated envelope).

C1.5 compared the submitted 60 against **8, the categories count**, while attributing that figure to
`/api/recipes`. It reached the right verdict from the wrong envelope. Compared against the total the
cited endpoint actually returned — 60, equal to the submission — the clause passes, exactly as the
clause-list walk above predicts. **The contract-derived reading was correct; the implementation
escapes it only through a cross-envelope confusion.**

**Why: this is a silent server-side filter drop, not an agent contract violation.** The agent found
the Breakfast category's UUID, then issued
`GET /api/recipes?categories=Breakfast&perPage=100`. The OpenAPI declares `categories` as
`anyOf[{string, format: uuid4}, {string}]`, so passing the *name* is schema-conformant. The
application accepted a schema-valid value, silently ignored the filter, and returned a
schema-conformant paginated envelope reporting `total: 60`. **Every layer of the contract was
satisfied end to end while the answer was wrong.** This is the same defect class the ceiling test
already found once in its own oracle — amendment A2.1's unknown field that silently matched nothing
— running in the opposite direction, and it is now in the application under test.

**This is c1's only non-trivial detection anywhere in the corpus.** Across all 80 scored traces the
committed c1 arm returns `fail` 8 times: seven are `C1.1` "no terminal submit_answer" — the
no-output negatives, which every scorer including the judge catches for free and which therefore
contribute nothing to *marginal* detection — and the eighth is this `C1.5` firing. The remaining 72
are `C1.7` "no clause applies", i.e. `unverifiable`, carrying status `provisional`. So **c1's entire
marginal contribution to E8 rests on a single clause evaluation that reads the wrong envelope.**
Correct the envelope selection and `MD_c1 = 0` exactly, which is the §7(5) predicted null.

**Amendment B2 narrows the c2 arm further on exactly this trace.** B2.1 establishes that the target
declares no numeric precision anywhere — no `multipleOf`, no numeric `format`, across 243 component
schemas — so §4.5's "declared precision" has no referent and rung P1 (`schema_declared`) is used
zero times. B2.2's defence of the replacement ladder is that "the three sub-1% near-misses are
caught, if they are caught, by exactness rather than by a chosen tolerance: a count is an integer
and 12 ≠ 13". **That defence does not reach P1 (`R4.005`).** `R4.005` is a mean, not a count: its
expected value is `3.201754` and the submission is `3.23`. Exactness on integers cannot resolve it
and P2 (`integer_closed`) does not apply, so its derivation must land on P3 (`app_serialisation`),
P4 (`request_declared`) or P5 (`refuse`). B2.2 concedes P3 and P4 are "a **weaker provenance** than
§4.5 assumed" and invites a strict reader to discount them. **The dry run confirms this inference
exactly**: c2's entry for `R4.005` records `"rule": "P4_request_declared", "decimals": 2`, sourced
from the prompt's own phrase "to two decimal places", and carries `status: provisional`. It is the
single P4 derivation in the committed set. So the tolerance that convicts the one surviving numeric
discriminative case is read **out of the request text, not out of the contract** — on an experiment
whose subject is contract-derived verification. Applying B2.2's own invitation to discount P3 and
P4: **c2's coverage of the surviving discriminative set falls from 2 of 2 to 1 of 2**, and the
numeric half of the comparison disappears.

By contrast c2's entry for `R1.012` is `P0_exact_identity`, `status: validated`, recomputing the
correct 7-member set from `RecipeSummary.recipeCategory[].name` rather than trusting the server's
filter. That is a genuine detection by an independent path to the truth, and it is the strongest
single result in the arm.

**Consequences, stated against the committed implementation rather than against my reading of the
clause list.** On the strict re-scope's 2 discriminative traces:

| | `R4.005` (numeric, 0.88% near-miss) | `R1.012` (set, filter drop) | detection |
|---|---|---|---|
| c1 as implemented | `unverifiable` (C1.7) | `fail` (C1.5, wrong envelope) | 1 of 2, spurious |
| c1 with the envelope bug fixed | `unverifiable` | `pass` | **0 of 2** |
| c2 as implemented | `fail` (P4, provisional) | `fail` (P0, validated) | 2 of 2 |
| c2 under B2.2's strict reading | discounted | `fail` (P0, validated) | 1 of 2 |

- **The arms are nominally separable and substantively not.** As implemented the contrast is
  c1 = 1 of 2 against c2 = 2 of 2, which looks like a working comparison. Both of c1's numbers are
  artefacts: its detection is the envelope bug, and removing that bug returns it to the 0 the §7(5)
  predicted null expects. The honest reading is **c1 = 0, c2 = 1 or 2, on a denominator of 2.**
- **`MD_c1` would be reported as non-zero, and it should be zero.** This is the most consequential
  single item in this document. If E8 runs as it currently stands, it will report that a
  schema-derived verifier caught a real agent error that it did not in fact catch, and the write-up
  will attribute the catch to a cardinality clause reading an endpoint it never read. The
  preregistration's own predicted-null control is what would have caught this — §7(5) predicts c1
  detects none of the numeric errors, and c1 indeed detects none, so the control **passes while the
  arm is broken**, because the control was aimed at the numeric set and the bug is in the set-typed
  one.
- **The §7(5) predicted-null control is close to vacuous either way.** c1 returns `unverifiable` on
  72 of 80 traces and `C1.1 no submit_answer` on 7 more. Once the envelope bug is fixed it detects
  nothing that the judge does not detect trivially, so the control can no longer distinguish a clean
  run from a leaky one and stop condition S3 loses its diagnostic value.
- **`MD_c2` rests on one trace under any strict reading.** `R1.012` is the only c2 detection with
  `status: validated` and contract-grade provenance; `R4.005` is `provisional` on the sole P4
  derivation in the set. Constitution Principle I's validate-or-mark-provisional rule is being
  honoured here — the arm labels its own weak rung — but honouring it leaves exactly one
  citation-grade discriminative detection in the whole experiment.
- **The fix to c1 is visible and foreclosed.** The clause that would legitimately catch `R1.012` —
  verify that a filter actually filtered, or resolve an organizer by identifier rather than by name —
  is not in the committed clause list, and amendment rule 2 forbids adding a verifier clause after
  seeing which traces it would catch. Correcting the envelope selection is a bug fix rather than a
  new clause and is permitted; adding the missing check is not.

So the comparison E8 exists to make cannot be made on this data. Not because the cases are all one
type — after re-scoping they are one numeric and one set — but because one arm scores zero on the
contract and only appears not to because of a defect, and the other arm's numeric half is derived
from the prompt.

---

## 7. Corrections to the preregistration's own counts

None of these changes a decision by itself. Every one of them is a number the write-up would print.

| §2 / §2.1 states | the corpus says |
|---|---|
| 8 numeric value errors, 3 set/cardinality errors | **9 numeric, 2 set** |
| the 11 enumerated as `R1.012`, `NM.001`, `R4.001`, `R4.005` (A ×2, B ×1), `R4.006` (A ×2, B ×1), `R4.008` (B) | that list totals **10**; `R4.005` is **A ×3, B ×1** |
| "two of the eight numeric false successes are under 1% relative error" (§6.5) | **three** are, and all three are `R4.005` arm A submitting `3.23` |
| "8 of them in one family" (§2.1, §3.4) | **9 of 11** are family R4 |
| E9 sizing at "8/48 = 16.7% within family R4" (§9.3) | 9 of 48 as frozen; **1 of 18 at the current battery** |

The first and third of these are load-bearing for controls rather than for prose: §7(5) and S3 name
"the 8" numeric errors as the predicted-null set, and §6.5's near-miss sensitivity is defined over
"those two traces". Both would be implemented against the wrong set.

**Amendment B1 independently reached the first and third of these while this was being written**
(B1.1: 9 numeric / 2 set; B1.2: three sub-1% near-misses). Two agents recomputing from the frozen
records and landing on the same corrections is corroboration, and I record it as such. The second,
fourth and fifth rows are not covered by B1 and still stand. Note that B1.1's set count of 2 is
further reduced to 1 by the strict re-scope, and B3.3 already anticipates this for a different and
incorrect reason — it drops `NM.001` as expected-drifted, which it genuinely is, while retaining
seven prompt-drifted numeric traces it should also have dropped.

---

## 8. Other things nobody has flagged

### 8.1 Amendment B3's staleness detector is wrong in both directions

B3 landed while this was being written and proposes the same repair this document assesses, so it
takes priority over everything else in this section. Its eligibility rule (B3.2) is: exclude a
record if its stored `expected` differs from the value for that task in today's `expected.json`.

That rule excludes exactly 12 of the 246 records, which is where B3.3's "6 of the 20 negatives
(30%) are stale" comes from. Both the detector and that conclusion are wrong, in opposite
directions at once.

**False positives — 5 of those 6 "stale" negatives are not stale.** Seven of the 12 exclusions are
real drift: `NM.001`, `NM.002`, `NM.003` and `NM.004` at batteries 1.1.0 and 1.2.0, whose frozen
`expected` are scalars or empty lists against today's corroborated pairs. The other five are
`R4.011` ×2, `R4.013` ×2 and `R4.014` ×1, all of which store `expected: null`. **All five ran at
1.4.0-probe — the current battery.** No drift is possible for them by construction. The null is a
runner artifact: `expected` is populated only when the attempt submits an answer, and all five
terminated on `token_budget_exhausted`.

B3.3 reads this as evidence of "a version in which those tasks had no computable answer at all".
No such version existed. The proof is inside a single run — `20260802T164929-bias-probe-perrecord`,
battery 1.4.0-probe:

| task | arm | terminal | stored `expected` |
|---|---|---|---|
| `R4.011` | A | `token_budget_exhausted` | `null` |
| `R4.011` | B | `submitted_answer` | `13` |
| `R4.013` | A | `token_budget_exhausted` | `null` |
| `R4.013` | B | `submitted_answer` | `13` |
| `R4.014` | A | `token_budget_exhausted` | `null` |
| `R4.014` | B | `submitted_answer` | `"Blistered Parsnip Crumble"` |

Same run, same battery, same task, adjacent rows. The null tracks the terminal condition, not the
task definition. B3.2 would therefore discard 5 legitimate no-output negatives — 5 of the 7
no-output traces in the whole corpus — as "stale", on a signal that carries no information about
staleness.

**False negatives — the 7 traces that actually are stale stay in.** B3.3 concludes that "the nine
numeric false successes are all clean", that "no trace of R4.001, R4.005, R4.006 or R4.008 is
stale", and therefore that "the claim this experiment exists to test … is unaffected by this
defect". That is the wrong way round: the numeric false successes are the *most* affected group in
the corpus. They are clean only *by the `expected` test*, because amendment A4.2 changed **prompts**
and left expected values alone. Seven of the nine ran at batteries 1.2.0 and 1.3.0 under the
pre-A4.2 prompts for `R4.005`, `R4.006` and `R4.008`:

| task | battery | arm | submitted | expected |
|---|---|---|---|---|
| `R4.005` | 1.2.0 | A | 3.23 | 3.201754 |
| `R4.005` | 1.3.0 | A | 3.23 | 3.201754 |
| `R4.005` | 1.3.0 | B | 3.35 | 3.201754 |
| `R4.006` | 1.2.0 | A | 36 | 33.0 |
| `R4.006` | 1.3.0 | A | 36 | 33.0 |
| `R4.006` | 1.3.0 | B | 36 | 33.0 |
| `R4.008` | 1.3.0 | B | 11 | 9 |

These are precisely the traces the adjudication called ambiguity artifacts, and they are the reason
this assessment exists. An `expected`-only detector cannot see them, because the whole point of a
prompt amendment is that it leaves the answer alone and changes what was asked.

**Net effect.** B3 as written keeps 234 traces, N = 14 and N_fs = 10 — a discriminative set 5× the
strict re-scope and 3.3× the join-valid one — while asserting the corpus has been repaired. It also
happens to cut the no-output negatives from 7 to 2, which incidentally relieves the AUROC bias in
item 4 below; that is a real if accidental benefit, obtained by deleting valid data.

**What a correct rule requires.** Staleness has two independent channels — the expected value and
the prompt — and only the first is recoverable from the records. The second is recoverable only
from `battery_version` in the manifests, which is why §1 uses it. Any eligibility rule that does
not consult `battery_version` cannot detect prompt-only drift, and prompt-only drift is the defect
under discussion. **B3.2 should not be applied as written.** The minimum correction is to gate on
`battery_version` and to exempt records whose `expected` is null because the attempt produced no
answer.

### 8.2 Further items

1. **One of the two surviving discriminative traces is a rare stochastic event.** `R1.012` arm B has
   been run 7 times at battery 1.4.0-probe under identical budgets and temperature 0. It failed once
   — the frozen trace — and passed the other six with byte-identical submissions. The category-filter
   collapse is roughly a 1-in-7 event, not a property of the task. It remains a legitimate frozen
   artifact for a paired within-trace design, but it carries no external validity at all.
2. **The agent-side noise floor §5.1 says the corpus lacks now exists, and it is approximately
   zero.** 48 of 50 repeated `(task, arm, battery)` cells returned byte-identical submissions. The
   two exceptions are `R1.012` arm B above and one `R4.014` cell that differs only because the tool
   surface changed. This is measured in an out-of-scope run and so cannot enter E8, but it should be
   recorded, and it demolishes the harvest economics in §9 below.
3. **A run with `attempts_per_task: 5` now exists.** §5 states that "every one of the 12 run
   manifests records `attempts_per_task: 1`". That remains true of the 11 in-scope runs and is no
   longer true of the results directory.
4. **AUROC's negative set is dominated by traces every scorer catches trivially, and nothing
   corrects for it.** No-output traces are 7 of 20 negatives as frozen, 7 of 12 join-valid, and 5 of
   7 strict. A judge ranks a trace with no submitted answer at the bottom effortlessly, which biases
   AUROC upward and makes the constitutional ban row structurally hard to fire. §6.3 gives `MD`
   three denominators for exactly this reason and gives AUROC only one. The ban row is the single
   decision-grade output E8 was expected to deliver, and its instrument is miscalibrated in the
   direction of exonerating the judge.
5. **The clean re-scope points E8 at a battery the project has declared unfit.** Amendment A4.1 and
   `plan.md` both record that the 61-task 1.4.0-probe state "is an intermediate state that no full
   run should use". Restricting E8 to 1.4.0-probe is the simplest defensible join, and it scopes the
   experiment onto the one battery already ruled out for a full run.
6. **The program spend of record is stale.** `VERDICT.md` reports ≈ $24.82 total against SC-003's
   $300. The ceiling-test attempt records on disk now total **$34.23** across 301 attempts —
   $29.23 inside E8's frozen scope and $5.00 in three post-freeze runs. The figure of record
   understates the ceiling-test line by about $9.56. Headroom against the authorization is still
   large; the binding constraint on E8 is interpretability, not money.
7. **The `NM` pair reformulation is recorded in no amendment.** A1.4, A2.1 and A2.3 cover those
   tasks' creation and re-pointing, and A4 covers the R4 prompt disambiguation, but the change that
   turned four single-number `NM` tasks into corroborated pairs appears only in each task's
   `quarantine_history`. It is the change that produced the provable drift, and it cannot be dated
   from the amendment log. That is the mechanism behind the packaging defect, not just an instance of
   it.

---

## 9. Options and what each costs

Judge-arm costs below use the preregistration's own expected per-call figures — $0.01596 for a
Sonnet call and $0.00425 for a Haiku-class call — at 3 repeats per trace per judge arm.

### Option 1 — run as designed on the frozen 246

**Cost**: $4.85 expected, $6.62 pessimistic, plus the $2.00 repair reserve, against the $9.00
ceiling.

**Establishes**: a judge arm whose negative set is 8 of 11 drift-corrupted on exactly the
discriminative traces, and a verifier `MD` over a denominator already shown to contain one
known-wrong oracle verdict and five ambiguity artifacts. Roughly 6 of the 226 positives are
drifted `NM` traces on which a judge reading the current prompt will be scored as raising a false
alarm, inflating `FPR_judge`.

**Does not establish**: anything about H2 that survives the packaging defect. The write-up would
have to print `MD` over N_fs = 11 while knowing the denominator is wrong.

### Option 2 — fix the packaging and re-scope

**Cost**: the fix itself is **$0** — record the prompt in each trace record, pin `battery_version`
in `corpus_freeze.json`, and make the analysis path refuse a cross-battery join. A judge-only run
on the join-valid set is 12 negatives plus 60 positives, so 216 calls per judge arm:
**$4.37 ($3.45 + $0.92) expected**, about $6.00 pessimistic, inside the ceiling.

**Establishes**: a clean judge arm at |N| = 12. Hanley–McNeil at |P| = 60 and |N| = 12 gives a
standard error near 0.092 and a 95% half-width near ±0.180, so the ban row fires only below 0.320
against 0.353 as designed — a real loss but the published 0.18 to 0.30 range still sits inside the
detectable region. Fail-open rate and flip rate on 12 negatives.

**Does not establish**: the verifier gate, at N_fs = 3. Does not recover the lost prompts. Does not
close §4.1.

### Option 3 — generate fresh traces under a pinned battery and re-run

**Cost, computed from this corpus rather than assumed.** At battery 1.4.0-probe, 68 distinct
`(task, arm)` cells have been run and 2 yielded a false success, a cell-level yield of 2.94%; the
mean attempt costs $0.1496. Reaching §9.3's target of 30 false successes therefore needs about
1,020 cells — roughly 510 new tasks across two arms — at **$152.59 with one attempt per cell and
$457.76 at the three attempts §9.3 itself requires**. The larger figure exceeds the remaining
SC-003 authorization.

§9.3's own estimate of $21.38 to $35.64 rested on R4's 16.7% yield from superseded batteries. R4's
yield at the current battery is 1 of 18. Two further facts make the honest figure worse rather than
better: replicates are near-deterministic, so the unit of harvest is a *new task* and not an
attempt; and the one harvest actually performed since the freeze — the 5-repeat noise-floor run —
spent $4.82 across 50 attempts and produced **zero** new false successes. Raising the yield by
deliberately authoring near-miss-prone tasks is possible, but it selects the corpus on the failure
modes the experimenter imagined, which §3.4 and §7(3) exist to prevent.

**Establishes**: the only route to a gate that can be decided on its merits, at roughly 3 pp
granularity across ≥ 3 families.

**A cheaper partial**: harvesting to N_fs near 10 or 12 at the current battery costs roughly $50 to
$60 and lands back inside §6.9's advisory band, having bought nothing the current corpus does not
already have.

### Option 4 — abandon E8 and reach the verifier question another way

**Cost**: $0.

**Establishes**: no marginal-detection number. But three structural findings are already in hand at
zero cost, and §11 of the preregistration explicitly anticipated that this experiment could
establish exactly this kind of thing "even from a null":

- schema-level derivation is blind to wrong-but-well-typed values, as predicted;
- **schema-level derivation is blind to a silent server-side filter failure**, because the request
  was contract-conformant, the response was contract-conformant, and the answer matched the
  application's own reported total. Only a recomputation that does *not* route through the same
  declared parameter can catch it — which is exactly what c2's `P0_exact_identity` derivation does,
  recomputing the member set from `RecipeSummary.recipeCategory[].name` instead of trusting the
  filter. That contrast is the one clean, citable verifier result in E8; and
- **a contract-derived verifier can reach the right verdict from the wrong evidence, and its own
  provenance string will not reveal it.** c1's C1.5 cites `/api/recipes` and reads the categories
  envelope. The provenance field was the mechanism meant to make derivations auditable, and here it
  recorded an endpoint the clause never consulted.

The second and third are new, are in no finding, and are sharper constraints on the product's
verifier design than the number the gate was going to produce. Together they say: a contract-derived
verifier needs an independent path to the truth rather than a second pass through the same contract,
and its provenance claims need to be checked against the trace rather than trusted.

---

## 10. Recommendation

**Retire the ≥ 10 pp verifier gate on this corpus. Record it as a null on power, not on H2. Fix the
packaging and publish the structural findings, both at zero cost. Spend at most a reduced
judge-only run on the join-valid re-scoped set. Do not fund the ≥ 30 harvest until someone decides
the verifier question is worth $150 to $460 and several hundred new tasks.**

Concretely, in order:

0. **Do not apply amendment B3.2 as written** (§8.1). Its detector drops 5 valid no-output negatives
   on a runner artifact and retains the 7 prompt-drifted numeric false successes that motivated this
   whole assessment, yielding N = 14 and N_fs = 10 under a claim of repair. Any eligibility rule must
   gate on `battery_version`, not on `expected`. This is first because B3.2 is the only item here
   that would actively make the corpus worse if executed, and B3 is marked urgent.
1. **Fix c1's C1.5 envelope selection before anything else is decided** (§6). It currently compares
   the submitted collection size against the `total` of whichever paginated envelope it picked, and
   on `R1.012` that is the categories listing rather than the `/api/recipes` call it names. This is a
   bug fix, not a new clause, so amendment rule 2 permits it — but note that verifier verdicts are
   now visible, so it must be made as a stated correction with the before-and-after recorded, not
   silently. Expect `MD_c1` to go to zero when it lands.
2. **Amend E8 to drop arms c1 and c2 from the decision table** and record the reason: the
   discriminative set is 2 traces exhibiting 2 phenomena, one trace is worth 10.97 pp after the
   discount, and §6.5, §6.9 and S8 each independently pre-commit the verdict to provisional,
   advisory or not-measurable. **Note that FR-006's usual justification no longer applies**: the
   08:22 dry run computed real c1 and c2 verdicts, so results of the arms this touches *are* visible.
   The amendment is still defensible because it retires the arms rather than tuning them, and it
   moves the verdict in the conservative direction, but it must be recorded as an amendment made with
   verifier results in hand.
3. **Publish the three structural findings**, with the `R1.012` clause-5 walkthrough as the evidence.
   These cost nothing, need no model call, and are the strongest thing E8 produces.
4. **Fix the packaging** — prompt in the trace, `battery_version` in the freeze, a join that refuses
   to cross batteries. Zero cost, and it is the fix that prevents the class rather than the instance.
5. **Optionally run the judge arm only**, on the join-valid set, for about $4.40. Report AUROC on
   both N and N_disc and state the no-output-dominance caveat from §8.2, because as specified the
   ban row is biased toward exonerating the judge. If the owner does not want a judge number carrying
   that caveat, spend nothing.
6. **Leave H2 open and unclaimed.** Do not describe the verifier as validated, measured or earned in
   the spec or in `research/07`.

**Why not the alternatives.** Option 1 spends real money to produce a `MD` figure over a denominator
already known to be wrong, and its most likely output is a nominal gate pass that no rider permits
anyone to cite — the worst of both directions. Option 3 is the only design that could answer the
question, and it costs between four and eighteen times what E8 was budgeted, on top of authoring
hundreds of tasks; that is an owner decision about whether the verifier question is worth funding
properly, not a repair to E8. Option 4 alone discards the judge arm, which is the one part of the
corpus that a re-scope leaves usable.

**Against the temptation to keep it alive.** The gate was already advisory-only at n = 11 by the
preregistration's own §6.9, written before any result existed. Re-scoping does not introduce a new
problem; it removes the last argument that the old one might not bite. A pre-registered criterion
that fires inconveniently is the instrument working. The useful result here is "this cannot answer
the question", and it is available for nothing.

---

## 11. What I could not determine

- **Whether `R4.001`'s prompt at battery 1.2.0 is identical to the current one.** No artifact records
  historical prompt text. Its join-validity rests on the absence of a `quarantine_history` entry,
  and the `NM` reformulation proves a prompt can change without an amendment. This is why I lead
  with the strict re-scope's 2 rather than the join-valid 3.
- **Whether c1's C1.5 misreads the envelope on traces beyond `R1.012`.** It is the only C1.5 firing
  in the corpus, so the bug has exactly one observed instance and I cannot tell from one case whether
  the clause picks the last paginated envelope, the first, or the largest. Diagnosing that needs
  `c1_schema.py`, which I did not open — another agent is writing in that directory. What I can say
  is that the cited provenance and the value used disagree on the one trace where the clause fires.
- **Whether c1 would still be at zero after a correct C1.5.** I verified the envelope numbers against
  the raw transcript (`total: 60` from `/api/recipes`, `total: 8` from `/api/organizers/categories`,
  ground truth 7), so a correct comparison passes this trace. I did not re-derive every other clause
  against the implementation, so "c1 = 0 of 2 once fixed" follows from the clause list plus this one
  correction, not from a full re-run.
- I originally recorded that I had read no verifier output at all, to keep my clause-list reading
  independent of the implementation. The 08:22 dry run made that untenable — a real result existed
  and accuracy had to win. §6 now states both readings and where they diverge.
- **Whether the judge fails open on the `R4.005` slip.** That is the experiment, and it is the single
  verdict on which the whole re-scoped gate turns.
- **The exact battery version at which the `NM` pair reformulation landed.** It is after 1.2.0 and at
  or before 1.4.0-probe; no amendment dates it.
- **Whether the 1.3.0 bump carried any prompt change at all.** Amendment A3 records budget changes
  only, and no frozen expectation moved between 1.2.0 and 1.3.0.
- **Whether any task without a `quarantine_history` entry had its prompt edited.** Undetectable in
  principle from the committed artifacts. This is the residual risk that the packaging fix removes
  going forward and cannot remove retrospectively.
