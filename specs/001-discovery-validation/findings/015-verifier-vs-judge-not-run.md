# Finding 015 — E8 was built, self-tested, dry-run at $0.00, and deliberately not run; its corpus had silently rebased onto edited prompts

**Date**: 2026-08-03
**User Story**: 1 (prove or disprove the core value proposition) — hypothesis **H2**, does a
contract-derived verifier catch real agent failures that an LLM judge misses
**Owner decision**: [OD-14](../plan.md#od-14--the-verifiers-margin-over-an-llm-judge-is-declared-unmeasured-the-production-spec-is-unblocked-and-the-measurement-is-deferred-to-production)
— the verifier's margin is declared **UNMEASURED**, the production specification is unblocked, and
the measurement is deferred to production traffic. That retires
[OD-11](../plan.md#od-11--the-verifier-versus-llm-judge-experiment-runs-before-the-production-spec-is-written-the-blocking-condition-is-retired-superseded-2026-08-03-by-od-14)'s
blocking condition, and OD-14 records itself as a **knowing departure** from this feature's
prove-before-build discipline. This finding is the evidence that departure rests on. It does not
soften it.
**Model spend**: **$0.0000.** No judge call was ever billed. Twelve run directories exist under
`harness/verifier-vs-judge/results/` and every one carries `dry_run: true`; all 5,490 recorded
judge-call rows across them are stub rows at `cost_usd: 0.0` with `model: null`. **Nothing in this
document is a result of running E8.** Every number below is recomputed from the frozen corpus, the
committed derivation rules, and the harness's own deterministic verifier arms.
**Method**: read-only recomputation over the 246 frozen records and 246 traces pinned by
`corpus_freeze.json`, plus a fresh census of both verifier arms against the offline recomputation
fixture. No live target was contacted, no credential was read, and no model was called by this
document either. Where a claim was inherited from an earlier artifact it was re-derived rather
than quoted; where the re-derivation disagreed, the disagreement is reported below rather than
reconciled.

Numbering note: `014` was the last finding issued. `015` was free — checked by ripgrep with
`--hidden` across the tree before this file was created, and the only prior claims on the
identifier were the forward references this work planted in `c1_schema.py`, `selftest.py`,
`derivation-rules.md` and Amendment B5, which point here.

---

## The headline, and it is not about verifiers

**A frozen trace corpus silently rebased itself onto edited prompts, and stayed that way for its
entire existence.**

`corpus_freeze.json` pinned the SHA-256 of all 22 corpus files and refused to start on any change
to any of them. It did not pin **the questions the traces were answers to**. Trace records store
the agent's transcript and the oracle's verdict; they do not store the prompt the agent was shown.
So every downstream consumer — the LLM judge, both derived verifier arms, and a 40-trace blind
adjudication — joined each trace to whatever `tasks/tasks.json` said **today**.

The join never failed. It produced a plausible pairing every time.

| battery in force at run time | records |
|---|---:|
| 1.0.0 | 20 |
| 1.1.0 | 46 |
| 1.2.0 | 57 |
| 1.3.0 | 20 |
| **1.4.0-probe (current)** | **103** |
| total | **246** |

**Five battery versions were pooled into one corpus, and 143 of 246 records — 58% — ran under a
battery that no longer exists.** For most tasks the wording did not move and the join is harmless.
For eight tasks it did move, and the corpus carries no way to notice:

- **Provable drift, four tasks.** `NM.001`–`NM.004` were reformulated from a one-part question
  into a two-number corroborated pair. Frozen `expected` values are scalars (`0`) or empty sets
  (`[]`) against today's pairs (`[8, 0]`, `[21, 0]`, `[9, 0]`). Those traces **cannot** have come
  from the current prompt.
- **Behavioural drift, three tasks, and this is the dangerous kind.** Amendment A4.2 added "Count
  each recipe once however many times it is scheduled" to `R4.005`, `R4.006` and `R4.008`. **The
  expected values did not change** — the amendment clarified the question, not the answer. So no
  value-comparison detector can see it. It is visible only in behaviour: `R4.006` and `R4.008`
  flip from the per-entry answers (36 and 11) to the deduplicated answers (33 and 9) exactly at
  the first 1.4.0-probe run, and pass.

### Why it took three arrivals to see it, and why that is the finding

The defect was invisible for the corpus's whole life and then surfaced **three times inside an
hour, from three unrelated directions**, none of which was looking for it:

| # | Route | What it was actually doing |
|---|---|---|
| 1 | `adjudication/REPORT.md` §3 | A blind pass re-derived ground truth, disagreed with the oracle on traces it should have agreed with, and traced the disagreements back to prompt text. |
| 2 | PREREGISTRATION.md **B3.1** | Compared every record's stored `expected` against today's `expected.json` and found 12 disagreements. |
| 3 | `E8-VIABILITY.md` §1 | Joined each record's `run_id` to its run manifest's `battery_version` to date every trace exactly. |

A fourth arrival exists that nobody has recorded, and it is the cleanest of the four because it
came from an arm that knows nothing about batteries. **Arm (c2) independently reproduces the stale
set exactly.** Scored over all 226 oracle-positives in the frozen corpus, c2 raises **6** false
alarms — and all 6 are precisely the 6 stale positives. The 7th stale record is an oracle-negative
and c2 flags that too. c2 consults no manifest, no `battery_version` and no eligibility verdict; it
recomputes the answer from the application's declared fields and compares. **A postcondition
verifier pointed at a rebased corpus reports the rebasing as a wall of false alarms**, which is a
detection channel nobody designed and one any project could use.

**The general lesson, which is the transferable part.** Hash-pinning a trace corpus proves the
*traces* did not change. It says nothing about whether the *questions* changed underneath them, and
a hash check that passes is actively reassuring while the corpus is wrong. Three properties made
this specific instance survivable and none of them is unusual:

1. **The trace does not carry its own prompt.** Transcripts here begin at the agent's first
   *assistant* turn. The prompt is reachable only by joining to an external, mutable file.
2. **The join is total.** Task ids are stable across battery versions, so the join always
   succeeds. A join that cannot fail cannot warn.
3. **The obvious detector is blind to the dangerous case.** Comparing stored expectations against
   current ones catches value drift and misses *wording* drift entirely — and wording drift is
   what a prompt amendment is. Seven of the nine numeric false successes here are prompt-drifted
   and every one of them passes the value comparison.

**Anyone freezing a trace corpus to evaluate agents can have this defect.** The fix costs nothing
and is now applied here: record the prompt inside the trace record, pin the battery version and
the task-file hashes in the freeze, pin the cross-battery census itself so exposure cannot change
under a passing hash check, and make the analysis path *refuse* a cross-battery join rather than
perform one (Amendment B4.5). Pinning the census is the part worth copying — it converts "58% of
this corpus is cross-battery" from a fact someone once measured into an invariant the harness
re-checks on every load.

**What it cannot fix is the corpus already collected.** Historical prompt text is unrecoverable:
the repository has a single commit, manifests record task ids but no prompt strings, and traces
start after the prompt. Re-scoping can only *exclude* traces. **A corpus that has rebased cannot be
repaired, only trimmed** — which is exactly why the eligibility rule below costs so much.

---

## Three derivations of the discriminative sample gave three answers, and a fourth is running in the harness

The number E8's entire power calculation rests on is *how many traces are discriminative* — false
successes, where the oracle failed but the agent looked right. Four artifacts state it. They say
**11, 5, 2 and 10**. The disagreement is the finding; flattening it to one number would discard
what each attempt got right.

| # | Says | Where | The question it actually answers | Verdict |
|---|---:|---|---|---|
| 1 | **11** | PREREGISTRATION.md §2.1 | How many records did the oracle flag `false_success` in the frozen 246? | **Correct, and not the number the experiment needs.** |
| 2 | **5** | `adjudication/REPORT.md` §7 | Of those 11, how many are *genuinely wrong answers* under any reading of the prompt? | **Correct — for verdict robustness. Not a join-validity count.** |
| 3 | **2** | `E8-VIABILITY.md` §2 | How many survive restriction to runs that executed **today's** battery? | **Correct, and the strictest defensible reading.** |
| 4 | **10** | `corpus.py`, the rule the harness would actually have scored | How many are in the eligible population under Amendment B3.2 as corrected by B4? | **Correct arithmetic; the rule is too generous, and by a measurable amount.** |

### 11 → 5 is a change of question, not a correction

The adjudication classified all 11: **5 genuine**, **5 artifacts of an ambiguous prompt**, **1
oracle error** (`NM.001`, a correct answer mislabelled — a real overturn, recorded and used).

That decomposition is right and it is about *verdict robustness*: is this trace really a wrong
answer? E8 needs a different property — *join validity*: can this trace be shown to a judge or a
verifier **alongside the prompt the agent actually saw**? The two come apart cleanly on one task.
The three `R4.005` arm A traces submitting `3.23` are **genuinely wrong under either reading** of
the ambiguous prompt, so they pass the robustness test — and **two of the three ran under the
pre-A4.2 prompt**, so they fail the join test. The 5 is the right answer to the wrong question, and
the report's own §7 says so obliquely by noting that "by distinct failure phenomenon there are
three".

Two further inflations sit inside the 5 and neither is an error:

- **Three of the five are one event.** `R4.005` arm A answered `3.23` at 1.2.0, at 1.3.0 and at
  1.4.0-probe. Replicate cells in this corpus are near-deterministic — 48 of 50 repeated
  `(task, arm, battery)` cells returned byte-identical submissions — so at temperature 0 these are
  one trajectory replayed, not three draws.
- **By phenomenon there are three**: a summation slip, a dropped list member, a category-filter
  collapse.

### 5 → 2 is the same change of question, carried to its conclusion

Restricting to runs whose manifest declares `1.4.0-probe` leaves 103 records, 7 oracle-negatives
and **2** false successes — the `R4.005` summation slip and the `R1.012` filter collapse. Two
traces, two phenomena, one numeric and one set-typed. This is the strictest reading and it is the
one that is *provably* free of prompt drift, because same-battery needs no attestation.

### 2 → 10 is a real disagreement, and the 10 is the one the harness would have used

This is the only genuine conflict in the set, and it matters because **10 is not a historical
number — it is what `corpus.py` computes today and what a run would have scored.** Both rules claim
to answer join validity. They differ on one question: *does a matching `expected` value attest that
the prompt is unchanged?*

The implemented rule (B3.2, corrected by B4) keeps a cross-battery record when its stored
`expected` still equals today's — status `eligible_value_attested`. That admits **8** false
successes the strict rule excludes. Decomposing those 8 against the drift evidence:

| Of the 10 eligible false successes | n | Prompt-drift status |
|---|---:|---|
| `eligible_same_battery` — `R4.005`@1.4.0-probe, `R1.012`@1.4.0-probe | **2** | No join to attest. Sound. |
| `eligible_value_attested`, and **provably prompt-drifted** — `R4.005` ×2, `R4.006` ×3, `R4.008` ×1, all pre-A4.2 | **7** | **The value test passes and the prompt changed anyway.** This is exactly the case A4.2 creates: clarify the question, leave the answer alone. |
| `eligible_value_attested`, drift status unknown — `R4.001`@1.2.0 | **1** | Rests on absence of a `quarantine_history` entry. The `NM` reformulation proves a prompt can change without one. |

**So 7 of the 10 records the harness would have scored are known to have been graded against a
prompt the agent never saw, and the rule keeps them because the amendment that broke them did not
touch their answers.** `corpus.eligibility`'s own docstring concedes the residue — value
attestation "attests that the task's *answer* is unchanged, not that its *wording* is" — and B4.3
records that 92 of the 195 eligible records rest on it. What was not stated anywhere is the
concentration: the residue is not spread evenly across the corpus, it is piled almost entirely on
the discriminative set. **The strict rule's 2 and the implemented rule's 10 differ by 7 records
whose defect is documented and 1 that is unknowable.**

### The 12-versus-7, which is fully diagnosable

Separately, two counts of *stale records* are on the record: **12** (B3.1) and **7** (B4.1). This
one is not a change of question. It is a detector with a false-positive mode, and it reconstructs
exactly.

```
12  =  7 genuinely stale  +  5 not stale at all
       └ NM.001 ×2, NM.002 ×2, NM.003 ×2, NM.004 ×1
         stored expected is a scalar or [] against today's corroborated pair
       └ R4.011 ×2, R4.013 ×2, R4.014 ×1
         stored expected is null
```

The five nulls are **not** drift, and the proof is inside a single run file. All five ran under
`1.4.0-probe` — **today's battery**, so no drift is possible by construction — and each carries the
oracle reason `no answer submitted (terminal: token_budget_exhausted)`. `ceiling-test/checks.py`
computes an expected value only after a submission exists and returns before that when nothing was
submitted, so `null` means **the comparison never ran**. Decisively, in run
`20260802T164929-bias-probe-perrecord`, adjacent rows for the same tasks in the same file carry
today's values:

| task | arm | terminal | stored `expected` |
|---|---|---|---|
| `R4.011` | A | `token_budget_exhausted` | `null` |
| `R4.011` | B | `submitted_answer` | `13` |
| `R4.013` | A | `token_budget_exhausted` | `null` |
| `R4.013` | B | `submitted_answer` | `13` |
| `R4.014` | A | `token_budget_exhausted` | `null` |
| `R4.014` | B | `submitted_answer` | `"Blistered Parsnip Crumble"` |

**How the wrong answer was reached: a missing value was read as a disagreement.** B3.1 compared
`stored` to `current` and treated `null ≠ 13` as drift, when `null` records the absence of a
comparison. Left in place the rule would have discarded **5 of the 7 no-output negatives in the
entire corpus** — valid data, deleted on a runner artifact. B4.3's fix is the right shape and
generalises: absence of a disagreement is not evidence of agreement, and absence of a value is not
a disagreement. The harness now carries **four** statuses, not two — `eligible_same_battery`,
`eligible_value_attested`, `ineligible_stale`, `ineligible_unattested` — and never conflates
"excluded because it disagrees" with "excluded because nothing could be compared".

The 7 is independently confirmed twice. `corpus.py --eligibility` reports `ineligible_stale` at
n=7 (1 negative, 6 positives), and — from a component with no knowledge of eligibility — **c2's
complete false-alarm set on the frozen corpus is exactly those 7 records.**

---

## The experiment was unanswerable for at least three independent reasons

Any one of these would have been sufficient. **That three hold simultaneously, and that all three
were computable before the first call, is the reason not running it was the correct decision rather
than a convenient one.**

### 1. Power — the gate's boundary sits inside one trace

`MD_c` counts traces where the oracle failed, the judge passed, and the verifier failed. The gate
is `MD_best` × 0.7681 ≥ 10 pp.

On the strict re-scope's primary denominator of **7 negatives**:

| MD | raw | discounted | Wilson 95% | width |
|---|---:|---:|---|---:|
| 0 of 7 | 0.00% | 0.00 pp | 0.0% – 35.4% | 35.4 pp |
| **1 of 7** | **14.29%** | **10.97 pp** | 2.6% – 51.3% | 48.7 pp |
| 2 of 7 | 28.57% | 21.95 pp | 8.2% – 64.1% | 55.9 pp |

**One trace is worth 14.29 pp raw and 10.97 pp discounted, so a single detection clears a 10 pp
gate on its own.** The gate boundary lies between zero detections and one. Whether the verifier is
"a headline feature that ships with every generated tool" or "a CI detail" is decided by one judge
verdict on one trace.

On the denominator the harness would actually have used — 15 eligible negatives — the boundary
merely moves: 1 of 15 is 5.12 pp discounted and 2 of 15 is 10.24 pp, so the gate turns on whether
the count is one or two. And **the numerator is capped**, because 5 of the 15 are no-output traces
that the preregistration itself says every scorer catches trivially. `MD` can take four values.
Every attainable Wilson interval is wider than 28 pp and every one of them contains both "adds
almost nothing" and "catches a third of what the judge misses". §6.9 already requires the interval
to be printed in the same sentence as the point estimate; doing so honestly produces a sentence
that says nothing.

A property worth naming because it makes running it *worse than silence*: the trace most likely to
produce a detection is a recomputable arithmetic error that a postcondition verifier catches with
certainty. **The most probable output of running E8 as built is a nominal gate pass that no rider
permits anyone to cite** — a number that flatters the product and that the protocol forbids using.

### 2. Structure — three preregistered riders cap the verdict before any call

None of these needs a result.

- **§6.9 caps the verdict at "underpowered — advisory"** until the false-success base reaches
  **n ≥ 30 across ≥ 3 families**. The eligible base is **10 across 2** — R4 ×9, R1 ×1. The rider
  cannot lift on this corpus at any spend, and B4.4 already establishes it can never lift, because
  every record of every lost family lives in a cross-battery run.
- **S8 forces "not measurable" on any judge instability.** The noise floor is the largest spread of
  the primary metric across three single-replicate scorings, and S8 fires above **5 pp**. One
  verdict flip on one negative is **6.67 pp** on the eligible denominator and **14.29 pp** on the
  strict one. **A single flip anywhere, in either judge arm, across three repeats on 15 negatives,
  fires S8.** The stop condition is satisfied unless the judge is perfectly stable.
- **§6.5 forces "provisional" if the verdict changes with the near-misses removed.** All three
  sub-1% near-misses are the same `3.23` submission, and they are 3 of the 10 eligible false
  successes. On the strict re-scope the flip is by construction: remove the near-miss and the only
  remaining discriminative trace is `R1.012`, which no faithful schema derivation catches, so `MD`
  is 0 and the gate fails; keep it and the gate can fire. This rider is conditional where the other
  two are not, but its condition is structural rather than lucky.

**The decision table's first row — "verifier is a headline feature" — is unreachable.** A result at
or above 10 pp is pre-committed to *provisional* by §6.5 and *advisory* by §6.9; a result below
10 pp is pre-committed to triggering E9 rather than a narrative rewrite. The experiment could not
have earned the verdict **even if it had run and won**.

### 3. Coverage — the only sound eligibility rule costs four of seven task families

| | Corpus | Eligible |
|---|---:|---:|
| Records | 246 | **195** |
| Families | 7 (N, NM, R1, R2, R3, R4, W1) | **3 (R1, R2, R4)** |
| Negatives | 20 | 15 |
| `no_output` / `protocol` / `false_success` | 7 / 2 / 11 | 5 / **0** / 10 |

**The `protocol` negative class is empty.** Both records are `R3.004`, both cross-battery, both
unattestable. E8 can say nothing whatever about whether a verifier catches a protocol violation.

The four lost families are not a random 4: they are **exactly the refusal-shaped ones** —
`impossible`, `needs_clarification`, `state`. Those check kinds yield no `expected` value under any
battery version, so nothing can attest their join and no policy setting recovers them; only
re-running the battery does. E8 therefore degenerates into an experiment about **lookup and
arithmetic**, on a corpus where 9 of the 10 discriminative traces sit in one family, against a
rider demanding three.

**Unflagged consequence, recorded here for the first time: the coverage loss silently collapses
§6.3's three-denominator safeguard into two.** §6.3 requires N, `N_disc` and `N_fs` to be reported
together specifically so that divergence between them is visible — "if the gate fires on N but not
on `N_fs`, the write-up must say the effect is carried by trivially-detectable missing output". On
the eligible population `N_disc` = 10 and `N_fs` = 10, **identical by construction**, because
`N_disc` is N minus no-output minus protocol and the protocol class is empty. The two denominators
that were meant to disagree cannot. A safeguard that can no longer trigger reads exactly like a
safeguard that has been satisfied.

---

## Result: a schema alone does not reach value errors

**Arm (c1) is a negative control on derivation source, not the second arm of a two-arm
comparison.** This is a preregistered §7(5) finding, it is real, and it is the only substantive
thing E8 establishes about the schema-derived approach. Two analyses converged on it from opposite
directions.

**From the coverage side (B4.6).** Of §4.4's six clauses, **two ever return a verdict** on the
eligible population: C1.1 (5 fires) and C1.5 (1). C1.2, C1.3, C1.4 and C1.6 return none. 69 of the
75 scored records reach C1.7 `unverifiable` — **`UNV_c1` = 92.0%**, against §6.6's 50% ceiling, so
§6.6 already forbids describing c1 as covering the corpus. c1 flags 6 negatives in all, and **5 of
those 6 are C1.1**, which asserts only that the trace contains no terminal `submit_answer`. Its own
provenance field says `submit contract` — not the OpenAPI schema. **That is a liveness check.** It
needs no schema, no `openapi.json` and no derivation, and the oracle already classifies those
records as `no_output` without one. c1's single genuinely *schema*-derived fire is C1.5 on
`R1.012` — and c2 catches that record too. **The marginal contribution of c1's schema-derived
clauses over c2 is zero.**

**From the evidence side (E8-VIABILITY §6).** That one C1.5 fire does not survive inspection
either. Its verdict reads:

> `C1.5` — "submitted collection has 60 member(s); the paginated envelope the app returned declared
> total=8", provenance "openapi paginated envelope `total` on /api/recipes".

**There is no `/api/recipes` envelope in that trace declaring 8.** Event 9 is
`GET /api/organizers/categories`, whose envelope reports `total: 8` — the number of *categories*.
Event 11 is `GET /api/recipes?categories=Breakfast&perPage=1 | jq '.total'`, and it returns **60**.
Ground truth is 7. So the clause compared the 60-name submission against the **categories** count
while naming an endpoint it never read — and the endpoint it named returned 60, **equal to the
submission**, so a correct comparison *passes* this trace. It reached the right verdict from the
wrong evidence, and its provenance string, the mechanism meant to make derivations auditable,
recorded an endpoint the clause never consulted.

### The whole clause is wrong, not just this evaluation

The earlier assessments both looked at the single trace they had. Scored over all 246 frozen
records, **C1.5 fires three times and is wrong all three times**:

| record | oracle | submitted | `total` used | envelope it came from | path C1.5 named |
|---|---|---:|---:|---|---|
| `20260802T163319-bias-probe/R4.002/B` | **pass** | 3 | 34 | `/api/households/mealplans` | `/api/households/mealplans` |
| `20260802T163319-bias-probe/R4.004/B` | **pass** | 5 | 17 | `/api/recipes` (Dessert-filtered) | `/api/recipes` |
| `20260802T173614-baseline-lookup-R1R2/R1.012/B` | fail | 60 | 8 | `/api/organizers/categories` | `/api/recipes` |

**Corpus-wide precision: 0 of 3.** Two independent defects produce it, and only one of them is an
implementation bug:

1. **The comparand is unassociated with the path.** `_c1_5_cardinality` takes `totals[-1]` — the
   last `"total": N` anywhere in the serialised transcript — and takes its path from the last
   non-submit tool call. Nothing associates the two. On `R1.012` the agent read the recipe total
   with `jq '.total'`, which prints a bare `60` the regex cannot match, so the last *matching*
   total is the categories envelope's `8`.
2. **The preregistered clause's premise is false.** On the two positives the total *does* come from
   the operation named, and the clause is still wrong: the submitted answer is a **filtered
   subset** of the collection the envelope counts, so `length ≠ total` is the normal shape of a
   *correct* answer. §4.4 clause 5 asserts an identity that holds only when the answer is the whole
   unfiltered page — which is the unusual case, not the ordinary one.

Because defect 2 lives in the clause rather than the code, **repairing the envelope selection would
not rescue it**: it would remove the one apparent detection and leave both false alarms standing.

### Two things nobody flagged

**The sampled positive set would have hidden both false alarms.** Neither `R4.002/B` nor
`R4.004/B` falls in the seeded 60-positive stratified sample, so `FPR_c1` reads **0 of 60** in
every dry run. The arm's false-alarm rate — the one metric designed to catch exactly this — would
have been reported as perfect. Both records are *eligible*; they were simply not drawn. A
stratified sample sized for the judge's false-alarm rate is not automatically sized to expose a
verifier clause's failure mode, and this one missed both instances of it.

**The predicted-null control passed while the arm was broken.** §7(5) and S3 predict c1 detects 0
numeric value errors. It does — **0 of 9** on the eligible population — so the control passes, and
that pass is genuine evidence for §7(5). But the control is **scoped to the numeric class**, and
C1.5's fires are set-typed, so it could not see them. **A control aimed at one failure class
certifies nothing about the others.** This one certified an arm whose only non-trivial output was
fabricated, and it is the second time in this harness's short life that a c1 control has been
technically correct and substantively empty — the README already records two clauses that were
silently vacuous until planted fixtures caught them. The generalisable rule: state the class a
predicted-null control bounds, and treat everything outside that class as unchecked.

**What survives, and it is a real result.** Strip the fabrication away and c1's record is: zero
numeric value errors, zero set-typed errors correctly caught, `UNV_c1` at 92.0%, and its only
marginal catches produced by a liveness clause whose provenance is the submit contract. **A
schema alone does not reach value errors.** No clause of c1 compares a magnitude to anything —
which is precisely why, since the false-success set is *defined* by wrong magnitudes. §4.4
anticipated part of this for clauses 3–4 ("structurally blind to a wrong-but-well-typed number")
but not that clauses 5 and 6, named as "the only clauses with any chance at the false-success set",
would return one verdict between them and that one would be spurious.

---

## The one positive result, and the sharp line around it

**Arm (c2) detects all 9 numeric value errors in the eligible population, including all 3 sub-1%
near-misses, with zero false alarms across 220 clean positives.** It also catches the one eligible
set-typed error, so it flags **10 of 10** eligible false successes — and correctly declines the 5
no-output negatives as `unverifiable` rather than collecting them for free. `UNV_c2` is 10.7% on
the 75-record scoring set, comfortably inside §6.6's ceiling.

The false-alarm claim is the strong one and it is stated precisely. Over all 226 oracle-positives
c2 raises 6 alarms; all 6 are the stale positives of the packaging defect, so on the **220 clean
positives** it raises none, and on the 180 *eligible* positives it raises none. Its false alarms
are not noise — they are the corpus defect, detected.

> *(Annotated 2026-08-03 — **not a correction. Every figure in this section reproduces exactly**,
> and [finding 018](./018-verifier-false-alarm-attested-denominator.md) asserts that reproduction
> mechanically rather than by inspection. Two readings of the 220 do need narrowing, both raised by
> [finding 017](./017-evaluation-contemporaneity.md)'s survey. **The 220 is a mixed population**:
> most of its members are cross-battery and are kept in scope by the same value test this document
> shows is blind to wording drift. Re-run restricted to records whose manifest declares the current
> battery, the census gives **0 alarms on 96 positives, 93 of them compared** — and the
> value-attested half is separately clean, so the pooled zero was not resting on the unattestable
> records. **And 0 of 220 is not a rate**: 45 of the 220 are `unverifiable`, 40 of them the entire
> unattested class, and a record the arm declined to compare cannot appear in the numerator. The
> pooled rate is 0 of 175 compared.)*

**And the mechanism has no tunable threshold.** The target declares no numeric precision anywhere —
no `multipleOf`, no numeric `format`, across 243 component schemas — so §4.5's "compare at the
schema's declared precision" has no referent (Amendment B2). What replaced it is a six-rung
precision ladder committed *before* any derivation was written, and re-inspected for this finding:
**it contains no numeric constant.** Every rung names a *source* of precision, never a value; every
comparison is exact equality or exact equality at a derived number of decimal places; and the last
rung is a **refusal**, not a default tolerance. The census across all 61 requests: 28 integer-closed
exactness, 9 text/set identity, 6 the application's own serialisation, 1 request-declared, **17
refused**. The derivation was applied to all 61 in one pass, including the 17 it must refuse,
because deriving only where success was expected would have selected `MD_c2`'s own numerator; every
literal must be declared with a source and a prompt-sourced literal must actually occur in the
request text, which `validate_derivation` re-tokenises and checks. **No tolerance was chosen, so
none could be fitted to the corpus.**

### Two qualifications, both of which narrow the claim

**The near-misses are not caught by integer exactness.** The README's framing — "a count is an
integer, so 12 ≠ 13 however close they are proportionally" — is true of the ladder in general and
**false of the three near-misses specifically**. All three are the same submission, `3.23` against
a true mean of `3.201754`. A mean is not a count. That projection is the **sole** entry on rung
**P4**, whose two decimal places are read out of the request text's own phrase "to two decimal
places" — and c2 labels it `provisional` on its own provenance, exactly as Principle I requires.
So the near-misses are caught by *exactness at a precision the prompt declared*, which is
threshold-free but **request-derived rather than contract-derived**, on an experiment whose subject
is contract derivation. Amendment B2.2 invited a strict reader to discount P3 and P4; a reader who
accepts that invitation removes the numeric half of the surviving discriminative set.

**The mechanism is demonstrated; the marginal value is not measured. This is the whole of the
distinction OD-14 turns on.** Everything above is a *detection* rate: how many failures c2 finds.
The gate reads `MD` — **marginal** detection, restricted to traces **the judge passed**. No judge
verdict exists and none ever will. So:

| Claim | Status |
|---|---|
| A postcondition verifier detects value errors a schema-derived one structurally cannot | **Demonstrated**, 10 of 10, model-free |
| Its comparison mechanism has no fitted or tunable threshold | **Demonstrated** by inspection of the committed ladder |
| It raises no false alarms on clean traces | **Demonstrated**, ~~0 of 220~~ **0 of 96 attested positives (93 compared); 0 of 175 compared across all 220 clean positives** *(restated 2026-08-03, [finding 018](./018-verifier-false-alarm-attested-denominator.md))* |
| **It catches failures an LLM judge would miss** | **UNMEASURED, and deferred to production** |

The fourth row is the product claim. Nothing in E8 speaks to it. `D_c2` = 10/15 = 66.7% raw and
51.2 pp discounted is a detection rate that says nothing about margin, and any write-up that
compares it to the 10 pp gate has substituted the measurable quantity for the interesting one. The
README did exactly that and it is struck.

### And the ceiling nobody can raise by spending more

**§4.1's human adjudication requirement was never satisfied, at any n.** §4.1 requires a human pass
over all 20 negatives and a random 20 of the 226 positives to confirm the checks are not themselves
wrong; S1 voids the oracle on >2/40 overturns. A blind 40-trace pass exists, it is careful, and it
states in its own §0 that it was performed by **a model, not a human** — and names the reason it
matters: *"I am a language model adjudicating language-model transcripts… A human would not fail in
the same places, which is most of what a human check buys."* It also found one genuine oracle error
that both it and the oracle initially agreed on.

**No E8 result may be written up as resting on validated ground truth.** That caps what the
experiment could have claimed independently of sample size, budget, or corpus repair, and it is the
one limitation on this list that harvesting 500 new tasks would not touch.

---

## The quarantine: c1 is unrunnable, and the defect is deliberately not fixed

**The defect is not repaired, and that is the point.** Amendment rule 2 forbids altering a verifier
clause after seeing which traces it would catch. Repairing C1.5 now would spend exactly the
discipline that makes the rest of this record worth reading, to buy a correction that is moot —
E8 will not run. It is also foreclosed on the merits: the clause that would *legitimately* catch
`R1.012` — verify that a filter actually filtered — is not in the committed clause list, and
amendment rule 2 forbids adding one now.

What is prevented instead is the failure mode that actually threatens a stranger six months from
now: **running the arm and believing the output.**

| Mechanism | Behaviour |
|---|---|
| `c1_schema.verify()` | raises `c1_schema.Quarantined`, carrying the defect and a pointer to this finding. It **refuses** rather than returning `unverifiable`, because an `unverifiable` would flow into `UNV_c1` and read as a measurement |
| `c1_schema.verify_clauses_quarantined()` | the preregistered clause walk, **unaltered**, reachable only from `selftest.py` — so the clauses can be *proved untouched* without being scoreable |
| `runner.py` | `refuse_quarantined_arms` runs **before** the freeze, the credential and the cost projection. `--arms … c1` exits with the explanation. c1 leaves the default arm list and **stays an accepted value**, so asking for it produces the reason rather than an argparse error |
| `controls.predicted_null` | reports **NOT RUN**, not PASS, when there are no c1 verdicts. `ControlResult` gains a `ran` field so a control that never executed can never be printed as a control that passed; `analyze.format_report` renders it |
| `derivation-rules.md` | a quarantine banner heads the c1 section and C1.5 carries its own dated annotation — a reader meets the defect **before** the code |
| `README.md` | the status block leads with the closure and the quarantine, and every superseded claim below it is struck in place |
| `PREREGISTRATION.md` | Amendment **B5**, under the document's own amendment convention, stating what is permitted and why FR-006's usual ground does not apply |

**Self-tests: 155 → 169 checks, 0 failures.** Fourteen new checks, twelve of them in a new
`quarantine` group, hold the whole of it in place: that `verify` raises; that the notice names both
the finding and the amendment; **that the finding file it points at actually exists** — a pointer to
a missing file is worse than no pointer, and this check failed until this document was written;
that `refuse_quarantined_arms` exits on c1 and does **not** exit on the live arms; that c1 is
absent from the default arm list and present in the accepted values; and that no clause logic was
quietly removed or rewritten while the arm was being retired — including a check that C1.5 still
reads `totals[-1]`, pinning the exact defect described above so that a future "tidy-up" cannot
silently repair it and invalidate this finding. Two further checks assert the `NOT RUN` state is
reported and is not fatal.

A dry run confirms the whole path end to end at $0.00: `--arms b b_prime c1 c2` exits with the
quarantine notice before touching the freeze, and a run without c1 prints
`NOT RUN  predicted-null (c1)` in its report rather than a pass.

---

## Threats to validity

- **The strict re-scope's `R4.001` join-validity rests on absence of evidence.** No artifact
  records historical prompt text, and the `NM` reformulation proves a prompt can change without an
  amendment recording it. Any join-validity claim for a task with no `quarantine_history` entry is
  weaker than it looks, which is why the strict 2 is quoted ahead of the join-valid 3.
- **`R1.012` is a roughly 1-in-7 event, not a task property.** That arm-and-task cell has been run
  seven times at 1.4.0-probe under identical budgets at temperature 0; it failed once — the frozen
  trace — and passed six times with byte-identical submissions. It is a legitimate frozen artifact
  for a within-trace paired design and carries no external validity.
- **c2's positive result is measured against an offline fixture, not the live application.** The
  fixture is audited by replay against every API response recorded in the frozen traces and
  reproduces 44 of 44 oracle expectations, but one fixture-fidelity defect was already found this
  way (a missing bootstrap administrator) and was surfaced by the validation pass rather than by
  the trace audit, which could not see it — no recorded trace contains a users listing. Other
  defects of the same shape would be invisible to the same audit.
- **C1.5's precision of 0 of 3 is measured on three fires.** The claim that the *clause* is wrong
  rather than only its implementation rests on the two positives, where the total does come from
  the cited operation; that argument is structural rather than statistical, and three is not a
  sample.
- **Everything here is one model against one target application.** The fail-open filter behaviour
  that produces `R1.012` is a Mealie property; its *class* — unresolvable filter values silently
  ignored, answered HTTP 200 with the full collection — is common enough to generalise as a hazard,
  but nothing here measures how common.
- **The corpus-rebasing result is one instance.** The mechanism is fully diagnosed and the fix is
  cheap and general, but this finding demonstrates the defect once, in one harness, and does not
  establish a base rate for it anywhere else.

## What this evidence does not license

It does not license any statement about the verifier's **margin over an LLM judge**, in either
direction. E8 produced no judge verdict. "Verifier catches what the judge misses" is unmeasured;
so is its negation.

It does not license describing the verifier as validated, measured, or *earned* in the production
specification or in the product narrative. OD-14 ships it as **asserted**, and says so.

It does not license reading c1's null as a clean §7(5) confirmation without the qualification
above. The prediction held on the numeric class and the control that verified it could not see the
class where the arm was broken.

It does not license reading `D_c2` as anything but a detection rate on a corpus with 7 known
prompt-drifted records in a discriminative set of 10.

It does not license retiring H2. E8 is a null on **power**, not on the hypothesis: the corpus
cannot tell, which is not the same as the answer being no.

## Register entries needing propagation

Identifiers only, and new entries are **described rather than numbered** so that no identifier is
cited before it exists. A separate pass edits
[`research/14-architecture-synthesis.md`](../../../research/14-architecture-synthesis.md); a
concurrent agent holds that file.

| Entry | Current | Should become |
|---|---|---|
| **New entry, next free `U` number** | — | **NEWLY OPENED — a hash-pinned trace corpus can rebase onto edited prompts and every hash check still passes.** The freeze pinned 22 files; it did not pin the questions. Traces carry no prompt, task ids are stable, so the join to the task file is total and cannot warn. 143 of 246 records were cross-battery for the corpus's entire existence. The dangerous drift is *wording*, which leaves expected values untouched and is therefore invisible to the obvious value-comparison detector — 7 of 9 numeric false successes here are prompt-drifted and all 7 pass that test. **Generalises to any project evaluating agents against a frozen trace corpus.** Fix, at zero cost: record the prompt in the trace record, pin the battery version and task-file hashes, pin the cross-battery census itself so exposure is re-checked on load, and make the join *refuse* rather than perform. A rebased corpus cannot be repaired retrospectively, only trimmed. |
| **New entry, next free `C` number** | — | **NEWLY OPENED — a control scoped to one failure class certifies nothing about the others, and reads as a clean pass while the component is broken elsewhere.** E8's predicted-null control asserts the schema arm detects zero *numeric* value errors. It passed, correctly. The arm's defect was in the *set-typed* class, where a cardinality clause fired three times with precision 0 of 3, and the control was structurally incapable of seeing it. Compounded by a second sampling gap: both false alarms fell outside the seeded 60-positive stratified sample, so the arm's own false-positive-rate metric read 0 of 60. Resolution requires that every negative control state the class it bounds, and that a sample sized for one arm's metric not be assumed adequate for another's failure mode. |
| **D-21** — synthesis, promotion selection, effect classification and decomposition are v2 | Carries the v2 efficiency case, the "burns its budget outside its surface" liability, and (from finding 014) the withdrawn fail-open safety claim | **Add the verification liability, which points the same way.** A schema-derived verifier over this target reaches **zero** value errors: 92.0% unverifiable, no clause comparing a magnitude to anything, and its only marginal catches produced by a liveness check whose provenance is the submit contract rather than the schema. Catching wrong-but-well-typed values requires an **independent recomputation path** — a postcondition derived from declared fields, not a second pass through the same contract. A v2 synthesis layer that emits schema-level checks emits a verifier that cannot see the failure class the product is sold on. |
| **C-14** — the same framework's published metadata is exact on one question and quietly wrong on the next | Four instances, the fourth being the runtime fail-open filter from finding 014 | **Extend with the derived-verifier corollary.** The published schema is accurate *and* insufficient: `openapi.json` declares no numeric precision anywhere across 243 component schemas, so §4.5's "compare at the declared precision" has no referent on this target at all. A verifier derived from published metadata alone must either invent a tolerance or refuse; E8's ladder refuses 17 of 61 projections and reads one precision out of the *request text*. Contract-derived verification is bounded by what the contract happens to declare, and this contract declares less than the design assumed. |
| **The H2 / verifier row of the validation register**, wherever `research/11`'s decision table is mirrored | Pending E8 | **Closed as UNMEASURED, not as answered.** E8 built, self-tested, dry-run at $0.00, deliberately not run (OD-14). Null on **power**, not on H2. Record all three independent blockers — one trace worth 14.29 pp against a 10 pp gate; §6.9, S8 and §6.5 each capping the verdict before any call; four of seven families lost to eligibility — plus the uncapped one: **§4.1's human adjudication was never performed**, so no E8 result at any n could have rested on validated ground truth. Record too that a positive result was the *likeliest* outcome and would have been uncitable. |

## Reproduction

Everything in this document is reproducible offline at $0.00, with no credential, no network and no
container.

```bash
cd specs/001-discovery-validation/harness/verifier-vs-judge

python3 freeze.py --verify        # 22 files, hashes, battery pins, cross-battery census
python3 freeze.py --battery       # the 5 batteries and the 143 cross-battery records
python3 corpus.py --eligibility   # the 195-of-246 ledger, four statuses, itemised exclusions
python3 corpus.py                 # taxonomy + the discrepancies against §2.1
python3 selftest.py               # 169 checks, 0 failures
python3 runner.py --dry-run --arms b b_prime c1 c2   # refuses: c1 is quarantined
python3 runner.py --dry-run       # full pipeline, stub judge, $0.00, predicted-null NOT RUN
```

The c1 and c2 verdict censuses quoted above come from calling
`c1_schema.verify_clauses_quarantined` and `c2_postcond.verify` directly over all 246 frozen
records against the committed offline fixture — the quarantined walk is reachable for exactly this
purpose. The 60-positive stratified sample is regenerated deterministically by `select.select` from
the seed pinned in `config.json` (`20260803`), which is how the two C1.5 false alarms were
confirmed to fall outside it.

No credential value was read, printed, logged or committed. No live target was contacted. **No
model was called by E8 or by this finding, and $0.0000 was spent.**
