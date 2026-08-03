# E8 oracle adjudication — 40 traces

## 0. What produced this document

**This adjudication was performed by an AI model (Claude, running as a Cursor agent). It was not
performed by a human.**

`PREREGISTRATION.md` §4.1 calls for *human* adjudication of the oracle. This document does not
satisfy that requirement and must not be cited as though it did. It is a machine adjudication that
happens to be independent of the oracle's implementation — a different and weaker thing. Anyone
who later needs the preregistered human check still needs to run it.

The distinction matters here specifically because one of this repository's recurring findings is
inherited provenance: a derived artifact acquiring the standing of the thing it was derived from.
If this file is ever summarized as "the oracle was validated," that summary is wrong.

No model was called and no tokens were spent on judging. Every verdict below is the adjudicator's
own reading of a transcript against ground truth it computed itself.

---

## 1. Method

### 1.1 Sample and the rule that chose it

`PREREGISTRATION.md` §4.1 fixes the size at 40 and requires full coverage of the negatives.
The corpus (`corpus_freeze.json`, 11 run directories, 246 traces) splits **226 pass / 20 fail**.

| Stratum | Rule | n |
|---|---|---|
| Negatives | **all** of them — the corpus has exactly 20 | 20 |
| Positives | uniform random from the 226, `random.Random(20260803)`, the seed already in `config.json` | 20 |

The corpus flags 11 traces as `false_success` (a confident wrong answer). **All 11 are negatives,
so taking every negative covers the discriminative set completely — 11/11, not sampled.** That was
the point of the rule.

Cases were then shuffled (`Random(8811403)`) and given opaque ids `A01`–`A40`, so reading order
carries no information about stratum or verdict.

### 1.2 Blindness

`select_sample.py` builds `blind/cases.md` from a **field whitelist**, not a blacklist: a record is
reduced to `arm, terminal, submitted_status, family, turns, transcript, submitted, tool_call_count,
attempt` and a task to `prompt, answer_kind`. `outcome`, `false_success`, `reason`, `expected`,
`detectors` are structurally absent rather than filtered out. (An early blacklist version was
discarded: it searched rendered text for words like "expected" and "reason", which occur legitimately
in prompts and in agent reasoning.)

The independence constraint was honoured: `derivation-rules.md`, `c1_schema.py`, `c2_postcond.py`
and `c2_derivations.json` were never opened.

### 1.3 Ground truth computed independently of the oracle

Rather than adjudicate on impressions, ground truth was recomputed from
`ceiling-test/seed/fixture_plan.json` — the fixture that *seeded* the Mealie instance the traces ran
against — by `truth.py`. This shares no code and no constant with the oracle, so agreement is
evidence rather than tautology. The fixture fingerprint is identical (`afd2b1353452`) across all 11
in-scope runs, so one computation covers the whole corpus.

The one modelling assumption — that a recipe's rating is the mean of its per-user rating rows, and
a recipe with no rows is unrated — was validated against nine rating values quoted verbatim in the
transcripts before being relied on: **9/9 exact** (`truth.py::check_ratings`).

### 1.4 Ordering

`blind/verdicts.md` — all 40 verdicts with reasoning — was written to disk in full **before**
`sealed/key.json` was opened or `compare.py` was run. `digest.py` re-derives the case order from the
committed seeds precisely so that it never has to open the sealed file. Git history and the fact
that `compare.py` parses its verdicts *out of* `blind/verdicts.md` make the ordering auditable.

---

## 2. Headline agreement

```
agreement = 39/40 = 0.975 = 97.5%

                 oracle FAIL   oracle PASS
adjudicator FAIL      20             1
adjudicator PASS       0            19

Cohen's kappa:  po = (20+19)/40 = 0.9750
                pe = ((21/40)(20/40)) + ((19/40)(20/40)) = 0.2625 + 0.2375 = 0.5000
                k  = (0.9750 - 0.5000) / (1 - 0.5000) = 0.9500
```

One disagreement: **A35**. Zero cases where the oracle failed something I would pass.

**That number is misleading, and the rest of this report is about why.** Investigating the single
disagreement uncovered a corpus defect that makes 2 of the 40 adjudications void — including one
where the oracle is wrong and I agreed with it.

---

## 3. The defect: the frozen corpus does not pin the prompt

`corpus_freeze.json` pins the SHA-256 of every `results.jsonl` and `traces.jsonl` in scope. It does
**not** pin the task battery, and the trace records **do not store the prompt the agent was shown**.
Every downstream consumer — the LLM judge, the contract-derived verifiers, and this adjudication —
joins a trace to whatever `tasks/tasks.json` says *today*.

The manifests show the batteries actually differ (`drift.py`):

| battery at run time | traces |
|---|---|
| 1.0.0 | 20 |
| 1.1.0 | 46 |
| 1.2.0 | 57 |
| 1.3.0 | 20 |
| 1.4.0-probe (current) | 103 |

**143 of 246 traces were produced under a battery that no longer exists.** For most tasks the
wording did not change and the join is harmless. For eight tasks it did change, and the corpus
carries no way to notice:

| task | status | evidence |
|---|---|---|
| NM.001, NM.002, NM.003, NM.004 | **provable drift** | current `answer_kind` is `numbers` (a corroborated pair); frozen `expected` is a scalar `0` or a set `[]`. The trace cannot have come from the current prompt. All 7 NM traces in scope are affected. |
| R4.005, R4.006, R4.008 | **behavioural drift** | `quarantine_history` records that the prompt was amended to add "Count each recipe once however many times it is scheduled". `expected` never moved, so the drift is structurally invisible — but pre-amendment arms answer the per-entry value and post-amendment arms answer the deduplicated value (§5). |
| R2.010 | clean | re-pointed 47→38 before any in-scope run; `expected` is 38.0 from 1.1.0 onward. |

This is not an oracle defect. The oracle scored each trace against the battery in force at the time,
which is correct. It is a **corpus-packaging defect**, and it damages E8 directly: the judge and the
derived verifiers will be shown a prompt the agent never saw, disagree with the oracle for that
reason, and have the disagreement scored against *them*.

---

## 4. The disagreement, and the error my agreement hid

### A35 — NM.004 — I said FAIL, oracle said PASS. **The oracle is right.**

Current prompt: *"How many dinner entries are on the meal plan, and how many of those are for a
recipe tagged 'batch-cook' that takes more than an hour in total? Answer with exactly two numbers…"*
Truth is `9, 0`; the agent submitted `0`; I failed it for a missing first number.

But the trace is from battery 1.2.0, where `expected` is the scalar `0` — NM.004 was then a
single-number task, and the pairing was introduced later (`quarantine_history`: *"reformulated as a
corroborated pair after the negative control passed this task by answering 'none'"*). Under the
prompt the agent actually saw, `0` is correct. **My verdict is void; the oracle's stands.**

### A10 — NM.001 — we both said FAIL. **The oracle is wrong, and so was I.**

This is the important one, and it is invisible in the agreement statistic.

The agent submitted: *Blistered Turnip Gratin, Ember Chard Galette, Frosted Pepita Bisque, Rustic
Buckwheat Gratin, Silver Pepita Ragout, Silver Tamarind Stew, Velvet Nettle Tartine, Wild Farro
Skillet.* From the fixture, those are **exactly** the eight recipes requiring the Wok — 8/8, no
omissions, no extras.

The trace is battery 1.1.0, `expected: []`, oracle reason `missing [], unexpected [...all eight...]`.
NM.001's own `quarantine_history` explains why:

> the reference query named the field 'tools' where the oracle calls it 'cooking_tools', and the
> query engine silently returned nothing for the unknown field. Eight recipes do require the Wok,
> and the calibration pass failed Arm A for answering correctly.

So the oracle **failed a demonstrably correct answer**, the project found out, fixed the query
engine and re-pointed the task — **and left the wrong verdict in the frozen corpus**, still flagged
`false_success`, i.e. still counted as a confidently-wrong answer.

I marked it FAIL too, but for an unrelated reason (I was reading the 1.4.0 prompt, which demands two
numbers, and judged the format wrong). **We agreed on the verdict and disagreed on everything that
matters.** A single adjudicator reporting only an agreement rate would have certified this.

### Corrected accounting

| | |
|---|---|
| raw blind agreement | 39/40 = **97.5%** |
| adjudications void (prompt never seen by the agent): A10, A35 | 2 |
| agreement over the 38 valid adjudications | 38/38 = **100%** |
| oracle verdicts I can demonstrate are **wrong** | **1** (A10) |
| oracle verdicts wrong *in the agent's favour* | **0 found** |
| corrected oracle accuracy over the sample | 39/40 = **97.5%** |

The two 97.5% figures are numerically identical and mean opposite things. The first says we agreed
39 times. The second says the oracle is right 39 times. They coincide by accident, because the one
case we disagreed on is one the oracle got right, and the one case the oracle got wrong is one we
agreed on.

---

## 5. Task ambiguity — five more cases

`R4.005/006/008` originally omitted any statement of whether a recipe scheduled twice counts once or
twice. The clause was added later. The evidence that the traces in my sample predate it is
behavioural and clean:

| task | deduplicated answer | per-entry answer | pre-amendment arms answered | post-amendment (1.4.0) arms answered |
|---|---|---|---|---|
| R4.005 | 3.20 | **3.35** | 3.35 (A33) | 3.20 (A20, pass) |
| R4.006 | 33 | **36** | 36 (A07, A11, A37) | 33 (both arms, pass) |
| R4.008 | 9 | **11** | 11 (A12) | 9 (both arms, pass) |

The per-entry values are exact, not approximate: the per-entry mean rating is 3.3533…, and 3.35 is
what A33 submitted. These are not agents getting the sum wrong; they are agents applying the other
reading of a prompt that did not exclude it.

**Five cases — A07, A11, A12, A33, A37 — are scored FAIL for a defensible reading of an ambiguous
prompt.** The oracle applied the expectation it was given; the defect is in the task, and the
project already identified it and amended the wording. What it did not do is drop the
pre-amendment traces from E8's scope.

`R2.010`'s history is often cited alongside these; it is **not** an instance. Its re-pointing
(47→38) predates every in-scope run.

---

## 6. The sub-1% near-misses — A03, A04, A15

All three are the same task (R4.005) submitting `3.23` where the true value is `3.2017543859649122`.
Absolute error 0.0282; **relative error 0.88%**.

**My judgment: wrong, and the tolerance question does not arise.** Two independent reasons.

**(a) The prompt asks for two decimal places.** It says *"Give the answer to two decimal places."*
The correct answer at that precision is `3.20`. The disputed digit is the one the prompt explicitly
requested. A user who specifies a precision and receives a different value at that precision has
been given a wrong answer, however small the absolute gap.

**(b) It is an arithmetic error, not a precision artifact.** The agent's own transcript settles it.
It enumerated 19 rated recipes — the correct 19, with the correct ratings, having correctly
deduplicated the 26 unique plan recipes and correctly excluded the 7 unrated ones. Then:

> Sum = 5.0 + 4.0 + 5.0 + 4.0 + 1.0 + 2.3333… + 2.0 + 1.5 + 5.0 + 4.5 + 4.5 + 2.5 + 2.5 + 3.3333… + 1.5 + 1.6666… + 3.0 + 5.0 + 2.5
> **Sum = 61.3333333333333337**

That list sums to **60.8333**. The agent overstated its own correctly-transcribed list by exactly
0.5, then divided correctly and rounded correctly. Right data, right method, right deduplication,
wrong addition.

So `3.23` is not "3.20 within tolerance." It is the output of a miscalculation that happens to be
small because the error is divided by 19. **A competent user who checked the working would call it
wrong** — the working is visibly wrong on its face. Under no reading of the task is 3.23 correct:
it is neither the deduplicated value (3.20) nor the per-entry value (3.35), so §5's ambiguity does
not rescue it either.

I record explicitly that if these three were reclassified as passes on a tolerance argument, they
would take **three of the five surviving genuine false successes** with them (§7). The experiment's
discriminative set is small enough that this one judgment moves it substantially. I do not think the
tolerance argument succeeds, for the reasons above, but the sensitivity is real and should be stated
rather than buried.

---

## 7. What this does to the discriminative set

The 11 `false_success` traces are the cases E8 exists to measure. All 11 are in my sample. Adjudicated:

| verdict | cases | n |
|---|---|---|
| **genuine false success** | A03, A04, A15 (R4.005, the 0.5 sum slip), A18 (R4.001, omitted Wild Pepita Ragout from 21 recipes rated ≥4 → answered 12 for 13), A22 (R1.012, submitted all 60 recipes for a 7-member category) | **5** |
| **artifact of an ambiguous prompt** (§5) | A07, A11, A12, A33, A37 | **5** |
| **oracle error — a correct answer mislabeled** (§4) | A10 | **1** |

If drifted and ambiguous traces are excluded, the discriminative set falls from **11 to 5**, and
three of those five are the same arithmetic slip on the same task at three battery versions. By
distinct failure phenomenon there are **three**: a summation slip, a dropped list member, and a
category-filter collapse.

E8 is powered to distinguish verdict sources on this set. Five traces exhibiting three phenomena is
a thin basis, and any headline about judge-versus-verifier discrimination should carry that n.

---

## 8. Can the oracle be wrong in the agent's favour?

Nothing in my sample. All 19 of my passes are correct against independently computed truth,
including both write tasks, which I verified by reading the tool calls and the agents' read-back
(A19 creates the list with exactly the two requested unchecked items; A39 sets servings 4, prep 35,
tag `budget`).

Two adjacent observations, neither an oracle error:

- **A39** — the read-back shows a default ingredient (`1 Cup Flour`) the agent never requested. I
  attribute it to the tool's own default and the prompt did not constrain ingredients, so the pass
  stands. Worth knowing that `create_recipe` injects state nobody asked for.
- **NM.002 / NM.003 / NM.004 passes are legitimate but non-discriminative.** Under the pre-1.4.0
  single-number form, the correct answer was `0`/`none`, and the project's own negative control — a
  bluffing agent with no tool access — passed by guessing it. Those passes are correctly scored and
  carry no evidence that the agent did the work. That is exactly why the tasks were reformulated as
  pairs; the pre-reformulation traces still sit in the E8 corpus.

The observed direction of oracle error is the safer one: A10 fails a correct answer rather than
passing a wrong one. It still damages E8, because it injects a trace into the false-success set
where the agent did nothing wrong — any verdict source that correctly calls A10 a pass will be
scored as disagreeing with ground truth.

---

## 9. What one non-human adjudicator establishes

**Establishes.** The oracle's checking logic is sound where it was exercised. Over 38 valid
adjudications against ground truth recomputed from the seed fixture — sharing no code or constant
with the oracle — it agreed 38/38. Numeric comparison, set comparison, the no-answer path, the
status-vocabulary path (`impossible` vs `needs_clarification`), and both write verifications all
behaved correctly. The oracle is not systematically miscalibrated, and its `expected` values are
right wherever I could recompute them.

**Does not establish.**

- **Not the preregistered human check.** §4.1 says human. This is a language model. The requirement
  is open.
- **One rater has no reliability estimate.** κ=0.95 describes this pair of raters on this sample. It
  has no confidence interval and no second opinion. A10 shows the failure mode concretely: two raters
  reaching the same verdict by different and both-wrong routes produce agreement that certifies an
  error.
- **Correlated blind spots.** I am a language model adjudicating language-model transcripts, using
  the same arithmetic and reading faculties that produced the errors. On A03 I initially accepted the
  agent's stated sum and only caught the 0.5 slip on re-derivation. A human would not fail in the
  same places, which is most of what a human check buys.
- **Sampling.** The negatives are exhaustive; the 20 positives are 8.8% of 226. A rare
  oracle-passes-wrong-answer failure would probably not appear here. The direction the brief flags as
  most dangerous is the one this sample is least able to bound.
- **Not the judge or the derived verifiers.** This adjudicates the oracle only.

---

## 10. Bottom line

**The oracle is fit to serve as E8's ground truth. The frozen corpus, as packaged, is not.**

The oracle's checks are sound. Over everything I could verify independently it was right 39 times in
40, its one error is documented in the repository's own quarantine notes, and that error runs in the
safer direction. I found no case where it passed an answer a user would call wrong. Following the
brief's instruction to say so as directly as the opposite finding: **this is a confirmation of the
oracle's checking logic.**

What is not fit is the corpus the oracle's verdicts are packaged in. Three defects, in order of
severity:

1. **The corpus does not pin the prompt.** 143 of 246 traces ran under a superseded battery; the
   records store no prompt; downstream consumers will join to the current one. This corrupted 2 of my
   40 adjudications and will corrupt the judge's and the verifiers' in the same way — and the
   resulting disagreement will be attributed to them rather than to the join.
2. **Five traces are scored FAIL for a defensible reading of a prompt the project has already
   admitted was ambiguous**, and one trace (A10) carries a verdict the project has already
   established is wrong. Both are still in scope and still flagged `false_success`.
3. **The discriminative set is 11 nominally and 5 after adjudication**, three of which are the same
   phenomenon.

Suggested remedies, in the order they matter:

- **Record the prompt in the trace**, or pin `battery_version` in `corpus_freeze.json` and make the
  analysis path refuse to join a trace to a different battery. This is the fix that prevents the
  class of error, not just these instances.
- **Re-scope E8 to battery 1.4.0-probe only** (103 traces), or explicitly exclude the 7 NM traces and
  the pre-amendment R4.005/006/008 traces. Either removes the drifted verdicts; the first is simpler
  to defend.
- **Correct or drop A10's verdict** (NM.001 @ 1.1.0). Leaving a known-wrong `false_success` in the
  set that defines the experiment's signal is the single most damaging item on this list per trace.
- **Restate the expected discriminative n** wherever E8's power is claimed. Whatever that number
  turns out to be, it is not 11.
- **Run the human adjudication §4.1 actually requires.** This document narrows what a human needs to
  look at — the five ambiguity cases, the three near-misses, and A10 — but does not substitute for it.

---

## Artifacts

| file | what it is |
|---|---|
| `select_sample.py` | sampling, blinding (field whitelist), sealed key |
| `blind/cases.md` | the 40 redacted cases, as adjudicated |
| `blind/verdicts.md` | **all 40 verdicts + reasoning, written before any oracle field was read** |
| `truth.py` | ground truth recomputed from the seed fixture, incl. the rating-model cross-check |
| `digest.py` | compact blind view; re-derives case order from seeds so it never opens `sealed/` |
| `compare.py` | parses `blind/verdicts.md`, joins the sealed key, emits agreement + `comparison.json` |
| `drift.py` | battery-drift analysis behind §3 |
| `comparison.json` | per-case machine-readable comparison |
