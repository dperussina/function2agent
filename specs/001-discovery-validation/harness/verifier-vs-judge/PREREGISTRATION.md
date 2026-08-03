# E8 verifier-vs-judge — pre-registered thresholds

**Date**: 2026-08-03. **Written before any judge call was made and before any scoring code
existed.** No arm of this experiment had been run when the decision table below was fixed.

**Implements**: `research/11-validation-plan.md` **H2** and **Phase 2 (the judge audit)**, and
the *Verification strategy* row of that document's decision table — the row `research/11` calls
"the most consequential gap in the table." Owner decision **OD-11** places this experiment before
the production spec is written.

**Why now.** A pre-registered criterion fired in Phase 0 and the product was re-scoped roughly
10× to three capabilities: a spec-aware runtime, a contract-derived verifier, and drift detection.
All three are unmeasured. The verifier became half the product on the strength of a
*contract-extraction accuracy* result ([finding 007](../../findings/007-contract-extraction.md)),
not on the *marginal-detection* result that was supposed to earn it. `research/11` states this
plainly: "promoted to headline without the measurement that was supposed to earn it." If a general
LLM judge catches everything a derived verifier catches, the verifier is not a differentiator and
v1 has no product.

**What this document is not.** It is not a harness. No scoring code is written here. A separate
agent builds the harness from this document; anything the harness does that this document does not
authorise is an amendment and must be recorded as one (see *Amendment convention*).

---

## TL;DR of the design decisions a reader should not miss

1. **The existing hand-written task checks cannot serve as the verifier arm.** They are the
   oracle. Using them as arm (c) makes verifier detection 1.0 *by construction* and makes the
   marginal-detection number an identity, not a measurement. This is stronger than the usual
   "upper bound" objection and it drives the whole design. See §3.
2. **Two genuinely derived verifier arms are built instead** — one schema-derived, one
   postcondition-derived — with derivation inputs that never touch `expected.json`. See §4.
3. **The judge half of Phase 2 is decision-grade. The verifier half is not.** The corpus contains
   11 false-success attempts across 6 tasks, 8 of them in one family. The ≥10 pp gate is evaluated
   with ~9 pp granularity and one-family confounding. It is adopted unchanged and its verdict is
   **advisory-only** until the false-success base reaches n ≥ 30 across ≥ 3 families. §9 specifies
   the follow-on experiment (E9) that gets there and prices it.
4. **The primary metric is fail-open detection, not agreement.** A uniformly mediocre judge is far
   less dangerous than one that confidently passes plausible-but-wrong output, because fail-open is
   the mechanism that hands a user a confidently wrong answer. See §6.
5. **Pre-registered prediction that makes this falsifiable:** the schema-derived verifier will
   catch **0 of the 8 numeric value errors**, because a wrong float is a well-typed float. If it
   catches any, there is a ground-truth leak in the harness and the run is void. See §7(5).

---

## 1. The claim under test

**H2, verbatim from `research/11` §H2:**

> Verifiers derived from code contracts (Pydantic response models, status codes, type signatures,
> declared exceptions, existing tests) catch real failures that an LLM judge misses, and
> specifically catch false successes.

**Falsifiable form, as tested here.** Over a frozen set of agent attempt traces with independent
pass/fail ground truth, let *fail-open* mean `oracle = fail AND judge = pass`. Then:

- **H2 survives** if a contract-derived verifier flags ≥ 50% of fail-open traces **and** adds
  ≥ 10 pp of failure detection over the judge alone, while holding a false-alarm rate ≤ 5 pp on
  oracle-passing traces.
- **H2 is falsified** if marginal detection over the judge is < 10 pp, or if the ≥ 10 pp is bought
  with a false-alarm rate above 5 pp (a verifier that flags everything is not a verifier).

**Governing design constraint, and its status.** Constitution Principle I and `research/11` both
rest on a published finding that an LLM judge is **anti-correlated with truth on false-success
detection, AUROC 0.18–0.30** — meaning a confident judge verdict is evidence *in the wrong
direction*. That figure is **inherited from sibling research in other domains**
(arXiv:2606.09863, as cited in the constitution). It is **not established for code and API tasks**,
and part of this experiment's job is testing whether it transfers. It must not be treated as
established here, and no result of this experiment may be written up as though it were assumed.

---

## 2. The corpus, and the fact that it is moving

**Source**: `specs/001-discovery-validation/harness/ceiling-test/results/*/`. Each attempt record
carries a `pass`/`fail` outcome from a hand-written programmatic check, a per-attempt `cost_usd`,
and — in `traces.jsonl` — the full `transcript` and `tool_calls`.

**Measured shape at freeze time (2026-08-03 07:10, counted, not estimated):**

| Quantity | Value |
|---|---|
| Run directories with results | 11 complete, **1 in progress** (`20260803T070942-diag-...`) |
| Attempt records | **246** (`results.jsonl`), 246 matching trace records |
| Outcome split | 226 `pass`, **20 `fail`** |
| Records flagged `false_success: true` | **11**, across **6 distinct tasks** |
| Families | R2 79, R1 68, R4 48, N 16, R3 14, W1 14, NM 7 |
| Arms | A 163, B 83 |
| Distinct tasks | 61 |
| `attempts_per_task` in every manifest | **1** |
| Transcript + tool-call payload | 3.31 MB total, mean 13.4 KB/record, max 85.2 KB |
| Spend already sunk in the corpus | $29.23, mean $0.1188/attempt |

**Two corrections to the record, both of which matter for this design.**

- The task brief describes "188 committed attempt records across nine run directories" and "one
  record carries a `false_success: true` flag: task `R1.012`." Both are **stale, not wrong**: 188
  records across nine directories is exactly the corpus *before* the two runs completed on
  2026-08-03 (4 + 54 = 58 more records). The false-success count is **11**, not 1. `R1.012`
  (arm B) is one of them. The others are `NM.001` (A), `R4.001` (A), `R4.005` (A ×2, B ×1),
  `R4.006` (A ×2, B ×1), `R4.008` (B).
- **A run was writing to `results.jsonl` while this document was being drafted.** The corpus is
  live. **Freeze commitment: the scoring set is fixed by the 11 complete run directories listed
  above and by nothing else.** The harness MUST record, before its first judge call, a manifest
  listing every `(run_id, task_id, arm, attempt)` tuple in scope plus the SHA-256 of each
  `results.jsonl` and `traces.jsonl` it read, and MUST refuse to start if any of those hashes has
  changed. Records from `20260803T070942-diag-...` or later are **out of scope for this
  experiment** and may be used only in E9.

### 2.1 What the 20 negatives actually are — the single most important fact here

The oracle's negative set decomposes exhaustively (7 + 2 + 11 = 20):

| Class | n | Failure reason as recorded | Discriminative? |
|---|---|---|---|
| **No output** | 7 | `no answer submitted (terminal: token_budget_exhausted)` | **No.** Both judge and verifier catch a missing required output trivially. Counting these inflates every detection rate. |
| **Protocol** | 2 | `did not ask for clarification (status=impossible)` | Partly. A contract can encode "impossible ⇒ abstain"; a judge can also read it off the prompt. |
| **False success** | 11 | wrong value, confidently submitted | **Yes. This is the whole experiment.** |

The false-success set decomposes further, and the split is decisive:

| Sub-class | n | Examples | A schema-derived verifier sees… |
|---|---|---|---|
| **Numeric value error, correct type** | 8 | `expected 3.201754, got 3.23`; `expected 33.0, got 36.0`; `expected 13, got 12.0`; `expected 9, got 11.0` | a well-typed number. **Blind.** |
| **Set / cardinality error** | 3 | `NM.001`, `R1.012` — 8 and 53 unexpected members where the truth was the empty set | a list where the contract implies an empty or bounded result. **Can catch, if the contract carries the bound.** |

**Consequence for the design.** Any verifier that only checks *shape* is structurally incapable of
catching 8 of the 11 cases the product claim rests on. Reporting a verifier arm without separating
shape-level from value-level detection would produce a number that cannot be interpreted. §4 splits
the verifier accordingly, and §7(5) pre-registers the blindness as a prediction.

**Also note**: two of the eight numeric errors are near-misses a reasonable human might not call a
hard failure (`3.23` vs `3.201754` is 0.9% off). A judge that passes those is not obviously
malfunctioning. This is reported, and the primary metric is computed both with and without the
sub-1% near-misses (§6.5).

---

## 3. The validity threat, and how it is resolved

### 3.1 The threat as posed

The `pass`/`fail` outcomes in the corpus come from `ceiling-test/checks.py` — **hand-written,
per-task checks** with per-task `expected` values and per-task numeric tolerances. Contract-derived
verification means something different: deriving the check from the application's own contract —
parameters, return types, declared exceptions, status codes, existing tests. `findings/007` measured
exactly that gap and found **literal extraction clears at 0.8696 while *validated* extraction misses
at 0.7681**. So a hand-written check is not an instance of a derived verifier. Constitution
**Principle I** (v1.1.0 amendment) exists to forbid exactly the substitution:

> **A derived verifier MUST be validated against an artifact its own derivation did not produce.
> Where no independent artifact exists, it MUST be marked provisional and carry its provenance and
> confidence — because a verifier that is complete and wrong is indistinguishable from a correct one
> at the point of use.**

### 3.2 The threat is worse than "upper bound." It is circular.

The brief frames the hand-written checks as a *ceiling* on derived-verifier performance. That is
true but understates it. In this corpus the hand-written check **is the ground truth**. If it also
serves as arm (c), then:

```
verifier_detection = |{oracle=fail} ∩ {verifier=fail}| / |{oracle=fail}| = 20/20 = 1.000  (by construction)
marginal_detection = |{oracle=fail ∧ judge=pass ∧ verifier=fail}| / |{oracle=fail}|
                   = |{oracle=fail ∧ judge=pass}| / |{oracle=fail}|
                   = the judge's fail-open rate, exactly
```

The number is an **identity**, not an estimate. It contains no information about any verifier; it is
a restatement of the judge's fail-open rate under a different name. It would clear the ≥ 10 pp gate
whenever the judge fails open on ≥ 3 of 20 negatives, and it would clear it *for any oracle
whatsoever*. Shipping that as "the verifier adds N pp" would be the exact error Principle I was
amended to prevent, and it would be undetectable downstream because the arithmetic is correct.

### 3.3 The resolution adopted

**Chosen option: build two genuinely derived verifier arms, feed the gate only from those, and
report the oracle-as-verifier quantity under its true name.** Specifically:

1. **(d) is retired as an arm.** The hand-written-check-as-verifier number is reported once, in a
   single line, labelled **"MD upper bound ≡ judge fail-open rate"**, with the identity above
   printed next to it. It is a statement about the judge. It MUST NOT appear in any sentence whose
   subject is the verifier, and MUST NOT feed the decision table.
2. **(c1) schema-derived verifier** and **(c2) postcondition-derived verifier** are built with
   derivation inputs that provably exclude `expected.json` and the `expected` / `reason` /
   `outcome` / `false_success` fields of every record (§4, §7(4)).
3. **Principle I compliance.** c1 and c2 are validated against the oracle verdicts — an artifact
   their derivation did not produce. Tasks for which no verifier can be derived are marked
   **provisional**, excluded from the primary metric, and their count reported (§6.6). No derived
   verdict is stated as fact without its provenance field.

### 3.4 What this choice costs in validity — stated plainly, so it can be overruled

| Cost | Magnitude | Why accepted |
|---|---|---|
| c1 and c2 are derived by a **human following a written derivation rule**, not by a shipping extraction pipeline. | Real. `findings/007` puts validated extraction at **0.7681**, so a real pipeline would derive these correctly for ~77% of contracts. | Priced, not hidden: every c2 result is reported **twice** — raw, and **pipeline-discounted at ×0.7681** — and the decision table reads the discounted figure (§6.4). A pipeline does not exist to test; refusing to proceed until it does would mean writing the production spec with this row still blank, which is what OD-11 forbids. |
| The derivation rule is written by someone who has seen the corpus. | Real leakage risk. | Mitigated by three controls: the derivation rule is written and committed **before** any per-task derivation (§7(1)); it must be stated as a general rule over OpenAPI constructs with **no task identifiers in it**; and §7(5)'s predicted-null control fails the run if c1 catches value errors it structurally cannot see. |
| The target is one application (Mealie: 175 paths, 259 operations) in one language, with a published OpenAPI schema. | Bounds generality hard. | Reported as a bound. This experiment licenses no claim about untyped or unspecified targets; `research/11` Phase 4 owns that question. |
| The negative base is 11 false successes across 6 tasks, 8 of them in family R4. | **This is the binding limitation, and it is not fixable with this data.** | §9. The gate is adopted unchanged and its verdict is advisory-only until E9 raises the base. |

### 3.5 The honest answer on what this data can and cannot measure

**It can measure the judge.** 80 traces containing 20 real oracle-negatives, scored in a paired
within-trace design, is thin but real, and the AUROC < 0.5 constitutional gate is a directional
question that survives a modest sample. **The judge half of Phase 2 is decision-grade.**

**It cannot decide the ≥ 10 pp verifier gate.** With 11 false successes, one case is 9.1 pp, so the
gate's resolution is one case wide; the Wilson 95% interval on a proportion at n = 11 spans tens of
points; and 8 of the 11 sit in a single family, so any effect is confounded with R4's numeric
character. A result either side of 10 pp is **consistent with** H2 or its negation and licenses
neither. **This is said here, before the number exists, so that it cannot be argued away after.**
§9 specifies the experiment that can decide it and prices it.

---

## 4. Arms

Every arm scores **the same frozen traces**. No arm reruns an agent. No new agent attempt is
generated by this experiment.

| Arm | Name | Input it is allowed to see | Output |
|---|---|---|---|
| **(a)** | **Oracle** — ground truth | full record incl. `expected` | `pass`/`fail` + reason. Already computed. |
| **(b)** | **LLM judge** | task prompt, transcript, tool calls, final answer | `verdict ∈ {pass, fail}` **and** `p_success ∈ [0,1]` |
| **(b′)** | **Cheap-judge control** | identical to (b) | identical to (b) |
| **(c1)** | **Schema-derived verifier** | OpenAPI response models, status codes, tool signature, submit contract | `pass`/`fail`/`unverifiable` + which clause fired |
| **(c2)** | **Postcondition-derived verifier** | c1's inputs **plus** live re-reads through the app's own API | `pass`/`fail`/`unverifiable` + recomputed value |
| **(d)** | *retired* — see §3.3(1) | — | reported as an identity, not an arm |

### 4.1 Arm (a) — the oracle

The existing `checks.py` verdict, **plus a human adjudication pass** over all 20 negatives and a
random 20 of the 226 positives, to confirm the checks are not themselves wrong. Costs no model
tokens. If adjudication overturns any verdict, the overturn is recorded in an amendment and the
corrected label is used; a >2/40 overturn rate voids the oracle and stops the experiment (§8).

### 4.2 Arm (b) — the LLM judge

Same model family as the agent under test (`claude-sonnet-4-5-20250929`), so the result speaks to
"could we just use a general judge" rather than to a straw model. **The judge sees the task prompt,
the full transcript, the tool calls with their results, and the submitted answer.** It never sees
`expected`, the oracle `reason`, `outcome`, or `false_success` (§7(4) enforces this).

The judge is asked for a **structured verdict**: a boolean `succeeded`, a calibrated
`p_success ∈ [0,1]`, and a one-sentence justification. `p_success` is required because AUROC needs a
continuous score; a boolean-only judge yields a degenerate two-point ROC.

Per Principle I's final clause ("where a model must judge, it MUST be pairwise with order-swapping,
calibrated against human labels, and reported as an estimate"): **this experiment is the calibration
against human labels.** Pairwise order-swapping does not apply — there is no pair to order, the
judge scores a single trace absolutely, which is precisely the mode the product would use and
therefore the mode that must be audited. A pairwise judge is out of scope and remains unmeasured;
that is recorded as a known gap, not silently absorbed.

### 4.3 Arm (b′) — cheap-judge negative control

The same prompt against a small/cheap model. Purpose: distinguish "LLM judges are anti-correlated
on this domain" from "the judge we picked was underpowered." If (b) fails and (b′) matches it, the
finding is about judging; if (b′) is far worse, the finding is partly about model capability and the
write-up must say so.

### 4.4 Arm (c1) — schema-derived verifier

Derived mechanically from artifacts the target already contains — `ceiling-test/groundtruth/
openapi.json` (175 paths, 259 operations) and the synthesized tool signatures — by a **rule written
before any per-task derivation** and containing no task identifiers. The rule's clauses:

1. **Output presence.** The submit contract requires a terminal `submit_answer` with a
   `submitted_status`. A trace with no terminal submission fails.
2. **Status-class conformance.** Any tool call whose declared success class is 2xx and which
   returned an error class fails, unless a declared exception in the schema covers it.
3. **Type conformance.** The submitted answer must parse as the type the invoked operation's
   response model declares for the projected field (number, string, array, boolean).
4. **Enum / membership.** Where the response model declares an enum or a bounded vocabulary, every
   submitted member must be in it.
5. **Cardinality.** Where the operation declares a paginated envelope with a `total`, the submitted
   collection's length must equal the `total` the app returned in-trace.
6. **Abstention contract.** Where the request cannot be satisfied by any declared operation or
   parameter (no declared field matches the requested attribute), the contract requires abstention;
   a confident answer fails.
7. **`unverifiable`** where no clause applies. Not a pass.

Clause 5 and clause 6 are the only clauses with any chance at the false-success set. **Clauses 3–4
are structurally blind to a wrong-but-well-typed number** — see §7(5).

> *(Annotated 2026-08-03 — **narrowed**, not corrected; no clause is altered, and amendment rule 2
> forbids altering one now. Measured on the eligible population, clauses 2, 3, 4 and 6 return no
> verdict at all and clauses 5 and 6 — "the only clauses with any chance at the false-success set"
> — return one verdict between them. `UNV_c1` is 92.0%, so §6.6 already bars describing this arm as
> covering the corpus. Every marginal detection c1 makes over c2 comes from **clause 1**, which
> tests only that a submission exists and derives from the submit contract rather than the schema.
> **E8 has one verifier arm that can make a claim, not two.** Assessment and evidence in
> **Amendment B4.6**; the decision is the owner's.)*

### 4.5 Arm (c2) — postcondition-derived verifier

The arm that can, in principle, catch value errors, and the arm that carries the real product claim.
Derivation rule, again written before any per-task application:

> For any task whose answer is a projection or aggregate over resources reachable through declared
> operations, the postcondition is that the submitted value equals the same projection recomputed
> from the app's own current state through those same operations. Re-issue the reads named by the
> operation's declared parameters, recompute, compare under the type's own equality (exact for
> integers and sets; for floats, the tightest tolerance the response model's declared precision
> supports — **not** a per-task tolerance).

**The derivation input is the schema and the tool's declared parameters. It is never
`expected.json`.** The recomputation is independent of how the agent arrived at its answer, which is
what makes this a verifier rather than a second copy of the oracle.

Where the projection is not expressible over declared operations (underspecified `N`/`NM` families,
write tasks whose pre-state is gone), c2 returns **`unverifiable`** and the trace is marked
**provisional** per Principle I and excluded from the primary metric with its count reported.

**Honest note on the float tolerance.** Choosing "the tightest tolerance the declared precision
supports" is a derivation choice made by a human, and it is the choice that decides whether
`3.23` vs `3.201754` is caught. It is fixed **here, in advance**, at the schema's declared
precision, and §6.5 reports the metric with and without the sub-1% near-misses so that a reader can
see how much of any effect rests on this one decision.

### 4.6 Negative controls — all five are mandatory and all are free

| Control | Expectation | Fires when violated |
|---|---|---|
| **Label-shuffle** | Score (b) against a permuted oracle label vector, 1000 permutations. AUROC must centre on 0.500. | Metric implementation bug. Void the run. |
| **Constant-fail verifier** | A verifier that fails everything. MD = 100%, FPR = 100%. | Anchors why the ≤ 5 pp false-alarm constraint is not optional. Printed in the results table as the degenerate reference row. |
| **Constant-pass verifier** | MD = 0%, FPR = 0%. | The opposite anchor. |
| **Oracle-leak assertion** | No judge or verifier input string may contain `expected`, `reason`, `outcome`, `false_success`, or the literal expected value. Asserted per call. | **Abort immediately, discard all prior calls in the run.** The trace records carry ground truth inline, so this is a live hazard, not a formality. |
| **Predicted-null (c1 blindness)** | c1 catches **0 of the 8** numeric value errors. | If c1 catches any, a leak exists. Void c1 and investigate before any re-run. |

---

## 5. Judge non-determinism, repeats, and what claim survives the missing noise floor

**The problem, stated before it can be excused.** `ceiling-test/PREREGISTRATION.md` Amendment A1.3
fixed **attempts per task per arm at three**, and required that no effect smaller than twice the
resulting noise floor be reported as a difference. **Every one of the 12 run manifests records
`attempts_per_task: 1`.** The corpus therefore has **no measured agent-side noise floor at all.**

### 5.1 What that kills

- No claim about task success rates, per-family TSR, `pass^k`, or "the agent fails X% of the time."
- No generalisation from these 61 tasks to the battery's population behaviour.
- No claim that the 11 false successes are a stable 4.5% rate rather than a one-sample draw.

### 5.2 What survives, and why

This experiment is a **paired within-trace design**: arms (b), (b′), (c1), (c2) all score the
*identical, fixed* artifacts. Agent sampling noise is baked into the traces and is therefore a
*constant* across arms; it cancels in every paired difference. **Marginal detection, fail-open rate,
fail-open capture, and AUROC are all properties of the scorers on a fixed set, and are measurable
without an agent-side noise floor.** What the missing floor costs is *external* validity — whether
this trace set is representative — not *internal* validity of the arm comparison. That distinction
is the claim that survives, and the write-up must state it in those terms.

### 5.3 Judge repeat policy — and the noise floor this experiment does obtain

- **Three independent judge calls per trace per judge arm**, at `temperature = 0`, recorded
  separately. Temperature 0 is **not** determinism under batched or mixture-of-experts serving; that
  is the reason for repeating rather than an argument against it.
- **Primary verdict = majority of three.** `any-fail` and `all-fail` variants reported alongside.
- **AUROC computed on the mean `p_success` across the three**, and additionally per replicate.
- **Judge noise floor := the largest spread of the primary metric across the three single-replicate
  scorings.** Adopting the ceiling test's rule verbatim: **no difference smaller than twice that
  floor may be reported as a difference.** If the floor exceeds 5 pp, the 10 pp gate is not
  measurable at this set size and **that fact is reported rather than worked around.**
- **Verdict-flip rate** — the fraction of traces where the three repeats do not agree — is a
  first-class reported metric. A judge with a high flip rate is unusable regardless of its AUROC,
  and the product may not ship one.
- **Obtaining the judge-side noise floor is one of this experiment's deliverables**, precisely
  because the ceiling test never obtained the agent-side one.

---

## 6. Metrics — exact definitions

Let **S** be the frozen scoring set, **N = {t ∈ S : oracle(t) = fail}**, **P = {t ∈ S : oracle(t) =
pass}**. A verifier verdict of `unverifiable` counts as **not-fail** (it does not detect), and is
counted separately as provisional.

### 6.1 Judge metrics

```
D_judge    = #{t in N : judge(t) = fail} / #N            judge detection
FO_judge   = #{t in N : judge(t) = pass} / #N            FAIL-OPEN RATE — the primary danger metric
CFO_judge  = #{t in N : judge(t) = pass and p_success(t) >= 0.80} / #N    confident fail-open
FPR_judge  = #{t in P : judge(t) = fail} / #P            judge false alarms
AUROC      = MannWhitneyU(p_success over P vs N) / (#P * #N), mid-rank for ties
flip_rate  = #{t : the three repeats disagree on `succeeded`} / #S
```

`AUROC` carries a 95% CI from a stratified bootstrap over traces, 10,000 resamples. **The point
estimate is never reported without the interval.**

### 6.2 Verifier metrics, per verifier arm c ∈ {c1, c2}

```
D_c    = #{t in N : c(t) = fail} / #N
MD_c   = #{t in N : judge(t) = pass and c(t) = fail} / #N
         MARGINAL DETECTION over the judge, in pp. This is the gate metric.
FOC_c  = #{t in N : judge(t) = pass and c(t) = fail} / #{t in N : judge(t) = pass}
         FAIL-OPEN CAPTURE. The >= 50% condition from H2. Undefined, and reported as
         undefined rather than as 0 or 1, when FO_judge = 0.
FPR_c  = #{t in P : c(t) = fail} / #P
UNV_c  = #{t in S : c(t) = unverifiable} / #S            provisional fraction
```

**Admissibility constraint: `MD_c` counts only if `FPR_c ≤ 5 pp`.** A verifier that flags everything
scores `MD = 100%`; the constant-fail control in §4.6 exists to make that unmissable in the results
table.

**`MD_best` = max(MD_c1, MD_c2) among arms satisfying `FPR_c ≤ 5 pp`.** If no arm satisfies the
constraint, `MD_best` is undefined and H2 is **falsified on this corpus**.

### 6.3 Denominator variants — all three reported, none chosen after the fact

`research/11` says "over the subset the judge passed but the oracle failed," with the ≥ 10 pp
expressed over failure detection. The primary computation therefore uses **N (n = 20)** as written.
Because §2.1 shows N is not homogeneous, two further denominators are **also** reported:

- **`N_disc` (n = 13)** — N minus the 7 no-output traces, which every scorer catches trivially.
- **`N_fs` (n = 11)** — false successes only. The phenomenon the product claim actually rests on.

**The gate reads the primary (N).** Divergence between the three is reported prominently, not
reconciled silently. If the gate fires on N but not on `N_fs`, the write-up must say that the effect
is carried by trivially-detectable missing output — which would be a fail of H2 in substance
whatever the arithmetic says, and the decision-maker is to be told so explicitly.

### 6.4 Pipeline discount

Every `MD_c2` and `FOC_c2` is reported **twice**: raw, and **× 0.7681** (validated-extraction rate
from `findings/007`), because c2's derivation is performed by a human following a written rule and a
shipping pipeline would not derive it correctly every time. **The decision table reads the discounted
figure.** Consequence to be honest about: a raw `MD_c2` of 12 pp discounts to 9.2 pp and **does not
clear the gate**. That is intended.

### 6.5 Near-miss sensitivity

Two of the eight numeric false successes are under 1% relative error (`3.23` vs `3.201754`). Every
verifier metric is reported with and without those two traces. If the gate's verdict changes between
the two, the result is reported as **tolerance-dependent** and the verifier claim is downgraded to
provisional regardless of which side of 10 pp it lands on — because in that case the number measures
a tolerance chosen by a human in §4.5, not a property of contract derivation.

### 6.6 Provisional accounting, per Principle I

Every trace where c1 or c2 returns `unverifiable` is **excluded from that arm's primary metric** and
**counted in `UNV_c`**. Each emitted verdict carries `provenance` (which schema construct it was
derived from) and `validated | provisional`. **No derived verdict may be stated as fact in the
finding without those two fields present.** A verifier arm with `UNV_c > 50%` may not be described
as covering the corpus, whatever its `MD`.

### 6.7 Prevalence warning, binding on the write-up

Positives are stratified-sampled (§9.1), so the scoring set's base rate is **not** the ~~corpus~~
**population** base rate ~~(20/246 = 8.13%)~~ **(15/195 = 7.69% on the eligible population;
20/246 = 8.13% on the corpus, which is no longer what is scored — B4.2)**. AUROC is rank-based and
prevalence-invariant, so it is unbiased under this sampling. **Accuracy, PPV, NPV, and F1 are not**, and MUST either be reweighted to 8.13% with the
weights shown, or not reported at all. Preference: not reported.

### 6.8 Decision table — binding

**The gate below is adopted from `research/11` §H2 and the *Verification strategy* row of its
decision table, unchanged. No threshold has been altered.**

| Result | Action |
|---|---|
| `MD_best` (discounted) **≥ 10 pp**, with `FOC ≥ 50%` and `FPR ≤ 5 pp` | **Verifier is a headline feature**; ships with every generated tool. **Subject to §6.9.** |
| `MD_best` (discounted) **< 10 pp** | **H2 false.** Contract-derived verification is a **CI detail**, not a headline differentiator. Adjust the product narrative honestly, in `research/07` and in the spec. |
| No arm satisfies `FPR ≤ 5 pp` | H2 falsified on this corpus. Same action as < 10 pp. |
| `AUROC_judge` **upper 95% bound < 0.5** | **Replicates the published anti-correlation on a code/API domain.** No LLM judge anywhere in the product's success path, ever. **Encode in the constitution** (Principle I already forbids it as default; this makes it absolute). |
| `AUROC_judge` CI **contains 0.5** | No transfer claim in either direction. Principle I's existing default stands unchanged — the judge remains disallowed as default critic, on the inherited evidence, now labelled *not replicated locally*. |
| `AUROC_judge` **lower 95% bound > 0.7** | Surprising and important. Investigate why this domain differs. **Do not relax the evaluation design on one result** (`research/11` Phase 2, verbatim). |
| `flip_rate > 30%` | No stable judge verdict exists. Independently sufficient for the ban row, and reported as such. |

### 6.9 The reporting obligation attached to the gate

The gate is adopted unchanged; **its verdict is advisory-only** and must be labelled
**"underpowered — advisory"** in the finding, until the false-success base reaches **n ≥ 30 across
≥ 3 families** (§9.3). Concretely, and committed in advance:

- A **positive** result (≥ 10 pp) licenses only: *"consistent with H2; underpowered at n = 11 false
  successes across 6 tasks, 8 of them in one family."* It does **not** license "H2 confirmed," and
  it does **not** license the verifier's promotion to headline feature being described as *earned*.
- A **negative** result (< 10 pp) licenses: *"H2 not supported on the only corpus available"* — and
  because a null at this sample size is weak evidence, it triggers **E9** rather than an immediate
  product-narrative rewrite. The CI-detail branch is executed only if E9 also comes back under
  10 pp, or if the owner decides not to fund E9, in which case the narrative changes on the null
  that exists.
- **Every report of `MD` MUST print, in the same sentence: the raw case counts, the Wilson 95%
  interval, and the family composition of the numerator.** One case is 9.1 pp at this size; a reader
  who is shown only "11 pp" has been misled by arithmetic that is technically correct.
- The **AUROC ban row carries no such rider.** It is a directional test that a sample of 20
  negatives and 60 positives can address, and if its CI clears 0.5 it is decision-grade as written.

---

## 7. Protocol commitments

1. **Order of construction is fixed and auditable.** (i) freeze the manifest and hashes; (ii) select
   and record the scoring set with its RNG seed; (iii) commit the c1 and c2 **derivation rules** and
   the judge prompt; (iv) *only then* run any arm. Each step is a separate commit. A harness that
   writes the derivation rule after inspecting per-task failures has invalidated c1 and c2.
2. **The judge prompt is written once, before any judge call, and is not tuned per family, per arm,
   or after seeing any verdict.** Prompt tuning after first sight of results is forbidden
   (`ceiling-test/PREREGISTRATION.md` protocol commitment 2, adopted here).
3. **No task-specific knowledge in c1 or c2.** The derivation rules MUST NOT contain task
   identifiers, expected values, tolerances keyed to a task, or family names. A reviewer must be able
   to read the rule without learning anything about the battery.
4. **Oracle-leak enforcement.** Before every model call, the harness asserts the serialised input
   contains none of `expected`, `reason`, `outcome`, `false_success`, nor the literal string of the
   expected value. **Failure aborts the run and discards prior calls** (§4.6). This is not a
   formality: the trace records carry ground truth inline in the same object as the transcript.
5. **The predicted-null control is binding.** c1 is predicted to catch **0 of the 8** numeric value
   errors, because a wrong float is a well-typed float. If it catches any, c1 is void until the leak
   is found. Recording this prediction *before* the run is what makes c1 falsifiable rather than
   decorative.
6. **A tie is a tie; a null is published.** A negative result is reported with the same prominence as
   a positive one (FR-017). The finding is written whichever way the gate falls, and the "H2 false"
   branch is a publishable outcome, not a failure of the experiment.
7. **Quarantine rule, inherited.** If a task's oracle check turns out satisfiable by an unintended
   shortcut, the task is quarantined, every metric depending on it is recomputed, and the quarantine
   is recorded in an amendment — never silently applied.
8. **The person empowered to call the stop is the project's decision-maker, not the engineer who
   builds the harness.**
9. **Everything is logged per call**: model id, prompt hash, repeat index, input/output token counts,
   cost, verdict, `p_success`, latency. Cost is accumulated live and checked against the ceiling
   before each call, not after the run.

---

## 8. Stop conditions — what ends this experiment early

Any one of these ends the run. Each is written before the run so that stopping is a rule, not a
judgement call made while looking at a number.

| # | Trigger | Action |
|---|---|---|
| **S1** | Oracle adjudication (§4.1) overturns **> 2 of 40** audited verdicts | **Stop.** The ground truth is not trustworthy; nothing downstream is interpretable. Fix the oracle, re-freeze, restart. |
| **S2** | Oracle-leak assertion fires | **Abort immediately**, discard all calls in the run, investigate before any re-run. |
| **S3** | c1 detects any of the 8 numeric value errors | **Void c1.** A structurally impossible detection means a leak. |
| **S4** | Judge `flip_rate > 30%` after the negatives are scored | **Stop after the judge arm.** "No stable judge verdict exists" already satisfies the ban row; further spend buys no additional decision. |
| **S5** | After the 20 negatives and the first 20 positives (40 traces, ≈ $1.55): `FO_judge = 0/20` | **Stop.** The judge missed nothing, so `MD ≤ 0 pp` for every verifier by definition and H2 fails on this corpus without another call. Score only the positives needed for `FPR`, then write the finding. |
| **S6** | c1 ∪ c2 detect **0 of the first 6** false-success traces while the oracle catches all 6 | **Stop.** Conclusion: derivation at the schema and postcondition level cannot carry the product claim on this corpus. Escalate to E9 rather than spending the remaining budget confirming a zero. |
| **S7** | Cumulative spend reaches **$9.00** | **Abort.** Report partial results against the frozen manifest, with the exact set scored. |
| **S8** | Judge noise floor (§5.3) **> 5 pp** | Finish the run, but the 10 pp gate is reported as **not measurable at this set size** rather than as fired or not fired. |

**S5 and S6 are the two cheap outs, and both are more likely than the design's success case.** That
is deliberate: this experiment is built to reach a defensible null fast, because a null here is a
product decision worth more than a marginal positive.

---

## 9. Sample size, power, and the experiment that can actually decide the gate

### 9.1 The scoring set

**80 traces: all 20 oracle-negatives + 60 oracle-positives.** Positives are drawn by seeded RNG,
stratified proportionally by `family` and by `arm`, seed recorded in the manifest before selection.
All 20 negatives are taken — they are the entire discriminative signal and none may be sampled away.

Rationale for not scoring all 246: AUROC is rank-based and prevalence-invariant, so a stratified
positive sample estimates it without bias (§6.7), while scoring all 226 positives would triple the
judge cost to buy precision on the *easy* half of the problem. The trade is stated so it can be
reversed: if budget allows after S5/S6 do not fire, the positive sample may be extended, but only
by re-running the *same* prompt with the *same* seed extension — never by re-selecting.

### 9.2 What this size supports

- **AUROC.** Hanley–McNeil SE at `|P|=60, |N|=20` is ≈ **0.075** near AUROC 0.5 and ≈ **0.069** near
  0.25, so the 95% interval is roughly **±0.14**. The ban row therefore fires only if the point
  estimate is below **≈ 0.35**. The published 0.18–0.30 range sits comfortably inside the detectable
  region; an AUROC of 0.45 will **not** fire the ban, and pre-registering that here prevents a
  mid-range result being argued into one later.
- **Fail-open rate.** On 20 negatives, granularity is 5 pp with a Wilson interval spanning ~40 pp at
  mid-range. Adequate for "does the judge fail open at all," inadequate for "the judge fails open
  X% of the time."
- **The `MD` gate.** On the primary denominator (N = 20), **the gate fires at 2 traces out of 20.**
  On the false-success denominator (N_fs = 11), one case is 9.1 pp. **Two traces decide whether the
  verifier is half the product.** This is the single most important limitation in this document and
  is the entire reason for §6.9's rider.

### 9.3 What it does not support, and the experiment that would

Deciding the ≥ 10 pp gate on its merits needs **n ≥ 30 false successes across ≥ 3 families**, so
that the metric has ~3 pp granularity and is not confounded with R4's numeric character.

**E9 — adversarial false-success harvest** (specified here, *not* run here, *not* funded from this
budget):

- Observed false-success yield: **11/246 = 4.5% overall**, but **8/48 = 16.7% within family R4**
  (numeric composition/aggregation). R4 is the productive vein.
- To harvest 30 across ≥ 3 families, bias the battery toward near-miss-prone tasks: R4-style
  composition, R1/R2 set-membership with empty or bounded truth sets, plus one new family of
  multi-step arithmetic over paginated reads.
- **Cost arithmetic at the corpus's own measured mean of $0.1188/attempt:** at R4's 16.7% yield,
  30 / 0.167 ≈ **180 attempts → 180 × $0.1188 = $21.38**. At a conservative blended 10% yield,
  300 attempts → **$35.64**.
- **Both exceed this experiment's $10 ceiling**, which is why E9 is a separately-budgeted follow-on
  and not folded in. Folding it in would either blow the ceiling or shrink the judge arm below
  decision-grade, and the judge arm is the half of Phase 2 that this data *can* settle.
- **E9 MUST set `attempts_per_task: 3`**, closing the noise-floor gap (§5) that every run in the
  current corpus left open.

---

## 10. Cost — arithmetic shown, ceiling $9.00, budget $10.00

**No agent runs.** This experiment's only model spend is judge scoring. Arms (a), (c1), (c2) are
deterministic code and cost **$0.00** in tokens; c2's re-reads go to the local fixture.

**Measured inputs to the estimate** (from §2, counted): mean `transcript` + `tool_calls` payload
**13,458 bytes** → **≈ 3,365 tokens** at 4 bytes/token; judge rubric and response schema **≈ 700
tokens**; so **≈ 4,065 input tokens per call**. Output is capped at **250 tokens** (boolean +
probability + one sentence). A **pessimistic** variant uses 18 KB mean payload → **5,200 input
tokens**, because the negatives include the largest traces (max 85 KB).

**Call count:** 80 traces × 3 repeats × 2 judge arms = **480 calls** (240 per arm).

| Line | Tokens | Rate | Cost |
|---|---|---|---|
| (b) Sonnet-4.5 input, expected | 240 × 4,065 = **0.976 M** | $3.00/M | **$2.93** |
| (b) Sonnet-4.5 output | 240 × 250 = **0.060 M** | $15.00/M | **$0.90** |
| (b′) Haiku-class input | 240 × 4,065 = **0.976 M** | $0.80/M | **$0.78** |
| (b′) Haiku-class output | 240 × 250 = **0.060 M** | $4.00/M | **$0.24** |
| **Expected subtotal** | | | **$4.85** |
| (b) + (b′) at the pessimistic 5,200 input tokens | 1.248 M each | as above | **$6.62 subtotal** |
| Repair reserve — ≈ 100 extra Sonnet calls at $0.0194/call | | | **$2.00** |
| **Planned total (expected + reserve)** | | | **$6.85** |
| **Planned total (pessimistic + reserve)** | | | **$8.62** |
| **Hard ceiling — abort on reach (S7)** | | | **$9.00** |
| **Budget** | | | **$10.00** |

Per-call unit costs, for the live ceiling check: Sonnet **$0.01935/call**
(4,065 × 3/10⁶ + 250 × 15/10⁶ ≈ $0.0122 + $0.0038, rising to $0.0194 at the pessimistic size);
Haiku-class **$0.0043/call**.

**Pre-registered contingency, so it is not a mid-run improvisation.** Before the first call, the
harness computes the *actual* total input tokens of the selected 80 traces and projects arm (b)'s
cost. **If the projection exceeds $6.50, repeats drop from 3 to 2 on the positives only** — negatives
keep all three, because they carry the discriminative signal — and the reduction is recorded in the
manifest. **Additionally, every transcript is truncated at 24,000 tokens (middle elided, truncation
flagged per record and reported as a count)**, which bounds the worst case regardless of the payload
distribution. Truncated records are reported separately, since truncation could itself hide the
evidence a judge needed.

**Sunk cost for context, not charged here:** the corpus already cost **$29.23** across 246 attempts.
This experiment reuses all of it and adds under $9.

---

## 11. What the result will and will not license the product to claim

**Licensed if the AUROC ban row fires** (upper 95% bound < 0.5): "On our own code/API corpus, an LLM
judge is anti-correlated with truth on separating false success from honest failure. We do not use
one anywhere in the success path." This is decision-grade, and it converts Principle I's inherited
citation into a locally replicated result.

**Licensed if AUROC's CI contains 0.5:** "We tested the published anti-correlation on our domain and
could not replicate it either way at n = 80; Principle I's prohibition stands on the inherited
evidence and is labelled as such." Not a licence to use a judge.

**Licensed about the verifier, at best:** "A verifier derived from the target's own OpenAPI response
models and postconditions catches N of the M failures a general LLM judge passed, on a corpus of 11
false successes across 6 tasks — underpowered and advisory." Plus the honest structural finding,
which holds regardless of the numbers: **schema-level derivation is blind to wrong-but-well-typed
values, so the product's verifier cannot be schema-level only; it must recompute postconditions
through the app's own API.** That is a design consequence this experiment can establish even from a
null.

**Not licensed under any outcome:**

- "The contract-derived verifier is validated." It is validated **against this oracle on this corpus
  for this one application** with a published OpenAPI schema.
- "The verifier is a proven differentiator." The gate is advisory at n = 11 (§6.9).
- Any number describing the *shipping* verifier's detection rate. The derivation here is
  human-executed; `findings/007`'s 0.7681 stands between this and a pipeline (§6.4).
- Any claim about untyped or unspecified targets, other languages, or write-heavy workloads.
- Any claim about agent success rates, per-family TSR, or noise — the corpus has no noise floor
  (§5.1).

---

## 12. Credentials and spend discipline

- **Credential resolution follows `harness/provider-credentials/envroot.py` exactly**:
  `--env-root PATH` on the command line, else the `F2A_ENV_ROOT` environment variable, **no default**,
  exit with an explanation if neither is given. A scorer that silently scans the wrong tree is worse
  than one that will not start.
- **No path into any private repository is hardcoded anywhere in this experiment.**
- **No credential value is read into a log, a trace, a manifest, an error message, or a model
  prompt.** Values stay in local variables; only key *names* may ever be printed.
- Judge prompts are assembled from trace fields only. `.env` contents are never part of a prompt.
- **Spend:** the live accumulator is checked *before* each call against the $9.00 ceiling (S7). This
  document authorises no spend by itself; the harness commit that implements it is what spends, and
  it must print its projection before its first call.

---

## Amendment convention

Adopted from `ceiling-test/PREREGISTRATION.md`. Amendments append; nothing above is edited in place.
Each amendment carries:

```
# Amendment B<n> — <date>, <what was and was not visible when it was made>
**Authorised by**: <who>
**Status**: <why it is permitted — per FR-006, an amendment is permitted only while no
result of the arm it touches is visible>
**Decision table**: <"unchanged" — or the exact rows changed, and why, stated before the
affected arm runs>
## B<n>.1 — <one change per subsection, with its cost or trade stated>
```

Rules that bind amendments here:

1. **No amendment may weaken §6.8 after any judge verdict on a negative trace exists.** The gate is
   fixed the moment discriminative data is visible.
2. **No amendment may add a verifier clause after seeing which traces that clause would catch.** A
   post-hoc clause is a hand-written check wearing a derived verifier's name, which is the exact
   error §3 exists to prevent.
3. Every amendment states its **cost in validity**, not only its rationale.
4. Reducing repeats under §10's contingency is **not** an amendment — it is pre-authorised and
   recorded in the manifest.

---

# Amendment B1 — 2026-08-03, negative taxonomy corrected against the frozen corpus

**Authorised by**: c2 (postcondition arm) construction, before any arm was run.
**Status**: Permitted. **No verifier verdict and no judge verdict exists** on any trace. This
amendment corrects a count of the corpus; it does not touch a gate, a clause, or a metric.
**Decision table**: unchanged.

## B1.1 — The false-success split is 9 numeric / 2 set, not 8 / 3

§2.1 states 11 false successes as 8 `numeric_value_error` and 3 `set_cardinality_error`.
Mechanical classification of the frozen corpus by `corpus.classify` — which reads only the
oracle's own `reason` text — counts **9 numeric and 2 set**. The total, 11, is unchanged; one
record sits on the other side of the line. The nine negatives, by task, are R4.001 (×1),
R4.005 (×4), R4.006 (×3), R4.008 (×1).

*Cost in validity*: none to the design; the affected denominator moves in the direction that
makes the experiment **harder to pass**, since the numeric set c1 is predicted blind to is
larger by one and the set class c1 might plausibly reach is smaller by one.

## B1.2 — There are 3 sub-1% near-misses, not 2

§2.1 states 2. Mechanical classification counts **3**: three separate traces of R4.005
submitting `3.23` against `3.201754`, a relative error of 0.882%. §6.5's requirement to report
every verifier metric with and without the near-misses is unchanged and now covers three
traces rather than two.

*Cost in validity*: the sensitivity analysis §6.5 mandates now removes a larger share of the
numeric set (3 of 9 rather than 2 of 8), so any c2 effect will look **less robust** under it,
not more.

## B1.3 — This discrepancy is now asserted, not remembered

`corpus.taxonomy_discrepancies` recomputes the taxonomy on every load and prints any drift
from the figures recorded in §2.1. A future edit to the corpus that silently changes these
counts is mechanically visible rather than left to a reader to notice.

---

# Amendment B2 — 2026-08-03, the target declares no numeric precision

**Authorised by**: c2 arm construction, before any arm was run.
**Status**: Permitted. No verifier or judge verdict exists. This amendment supplies a missing
referent in §4.5; it does not weaken §6.8.
**Decision table**: unchanged.

## B2.1 — §4.5's "declared precision" does not exist on this target

§4.5 instructs c2 to compare floats at "the tightest tolerance the response model's declared
precision supports". **`groundtruth/openapi.json` declares no such precision anywhere**: across
243 component schemas there is no `multipleOf` and no numeric `format`; every numeric field is
a bare `type: number` or `type: integer`. The instruction as written has no referent here.

This is recorded as a **finding about schema-derived verification**, not as an obstacle. A
verifier derived from an OpenAPI document cannot obtain a numeric tolerance from a document
that declares none, and OpenAPI does not require one. Any product built on §4.5's premise
inherits this gap on any target that omits these constructs.

## B2.2 — What replaces it: an ordered ladder whose last rung is refusal

`derivation-rules.md` commits a six-rung ladder — P0 `exact_identity`, P1 `schema_declared`,
P2 `integer_closed`, P3 `app_serialisation`, P4 `request_declared`, P5 `refuse`. A derivation
takes the **first rung it reaches** and may not shop among them; `c2_postcond.validate_derivation`
rejects any entry whose comparison and rung disagree. Rung **P1 is used zero times** because it
is empty on this target. Rung P5 returns `unverifiable` — there is no default tolerance.

*Why this is not fitted*: the ladder contains **no numeric constant**. Each rung names a
*source* of precision — the schema, the application's own serialised bytes, or the request
text — never a value, so no rung can be reached by knowing an answer. The three sub-1%
near-misses are therefore caught, if they are caught, **by exactness rather than by a chosen
tolerance**: a count is an integer and 12 ≠ 13 however close they are proportionally.

*Cost in validity*: real, and stated rather than hidden. Rungs P3 and P4 derive precision from
the application's behaviour and from the request rather than from the contract, which is a
**weaker provenance** than §4.5 assumed. Seven derivations rest on them (6 on P3, 1 on P4) and
all seven are reported as such. A reader who rejects P3 and P4 as insufficiently
contract-derived should read c2's result as covering only the 28 P2 and 9 P0 projections.

---

# Amendment B3 — 2026-08-03, part of the frozen corpus was graded against an earlier battery

**Authorised by**: c2 arm construction, before any arm was run.
**Status**: Permitted, and **urgent**: this is a corpus-integrity defect that affects every
arm, not only c2. No verifier or judge verdict exists, so it can still be fixed without
discarding data.
**Decision table**: unchanged, but §6 denominators must be recomputed after B3.2 is applied.

## B3.1 — The defect

~~**12 of 246 records carry an `expected` value that disagrees with today's
`tasks/expected.json`.**~~ **7 of 246.** The recorded value is the one the oracle actually
graded against; the file holds the value today's battery would produce. ~~Seven~~ **Four**
tasks are affected:

| Task | Recorded `expected` | Today's `expected.json` |
|---|---|---|
| NM.001 | `[]` | `[8, 0]` |
| NM.002 | `0` | `[21, 0]` |
| NM.003 | `[]` | `[8, 0]` |
| NM.004 | `0` | `[9, 0]` |
| ~~R4.011~~ | ~~`null`~~ | ~~`13`~~ |
| ~~R4.013~~ | ~~`null`~~ | ~~`13`~~ |
| ~~R4.014~~ | ~~`null`~~ | ~~`"Blistered Parsnip Crumble"`~~ |

*(Corrected 2026-08-03 — **wrong**, not narrowed. The three `R4` rows are not stale: those
runs executed today's battery, nothing was submitted so `checks.py` never computed an
`expected`, and sibling records for the same tasks in the same runs carry today's values.
Derivation in **Amendment B4.1**.)*

The NM tasks were revised from a single-count near-miss form into the two-number corroborated
form now in `tasks.json` — the form whose own code comment explains that a second, legitimately
zero component exists "so that 'nothing matched' cannot be reached by abstaining". The recorded
traces predate that revision: their agents answered a **one-part question**, were graded
against a one-part expectation, and passed correctly. Today's `answer_kind` for all four is
`numbers`, which requires two.

**The prompt is the leak.** Every arm is fed `redact.scoring_view(trace, prompt)` where
`prompt` comes from today's battery. For these 12 traces the arms therefore see **a prompt the
agent never saw**, paired with an answer produced for a different question.

## B3.2 — The eligibility rule this requires

A trace whose recorded `expected` disagrees with the battery it is being scored against is
**not eligible for any arm**, and must be excluded from §6's denominators rather than scored.
The comparison is oracle material and so cannot live inside an arm; it belongs in the corpus
layer that already computes denominators, alongside the existing integrity checks. This
amendment records the rule and the defect; **applying it is owned by whoever owns `corpus.py`
and `runner.py`**, which the c2 arm does not.

Until it is applied, every arm will score these 12 traces against the wrong question.

## B3.3 — What it costs, and what it does not touch

~~6 of the 20 negatives (30%)~~ **1 of the 20 negatives** and 6 positives are stale. One of the
two `set_cardinality_error` false successes (NM.001) is among them, so **B1.1's set count
itself rests partly on a stale trace** and will fall to 1 once B3.2 is applied. ~~Five of the
seven `no_output` negatives (R4.011, R4.013, R4.014) are stale, and were graded against a null
expectation — i.e. against a version in which those tasks had no computable answer at all.~~

*(Corrected 2026-08-03 — **wrong**. The positive count is right. The five `no_output` records
are eligible, and the version they are said to have been graded against never existed; see
**B4.1**–**B4.2**. The two claims struck through were the reason B3.1's table listed three
tasks that were not stale.)*

**The nine numeric false successes are all clean.** No trace of R4.001, R4.005, R4.006 or
R4.008 is stale. The claim this experiment exists to test — whether a contract-derived verifier
reaches the numeric false successes c1 is blind to — is unaffected by this defect.

*Cost in validity*: the negative denominator falls from 20 to ~~14~~ **15**, which **widens
every confidence interval** and makes §6.8's gate harder to clear. That is the correct
direction: the alternative is a gate cleared partly on traces scored against a question their
agents were never asked.

*(Corrected 2026-08-03 — **superseded**, and the figure understates the cost. 15, not 14, and
only 1 of the 5 excluded negatives is stale. The larger cost is compositional and is not
stated anywhere in B3: four of seven task families and the whole `protocol` class go to zero.
See **B4.2** and **B4.4**.)*


---

# Amendment B4 — 2026-08-03, B3.2 applied; three of its seven tasks were not stale

**Authorised by**: the `corpus.py` / `runner.py` owner, whom B3.2 names as responsible for
applying the rule. Before any arm was run.
**Status**: Permitted. No verifier and no judge verdict exists on any trace. This amendment
applies B3.2, corrects B3.1's table and B3.3's costs against the frozen corpus, and records
what the rule actually costs. It does not weaken §6.8.
**Decision table**: unchanged. §6's denominators are recomputed as B3 required, and every one
of them now carries the population it is over.

## B4.1 — ~~12 of 246 records~~ **7 of 246** carry a stale `expected`. The three `R4` rows are wrong

B3.1's table lists seven tasks. **Four are stale; three are not.**

| Task | B3.1 said | Derived | Verdict on B3.1 |
|---|---|---|---|
| NM.001 | `[]` vs `[8, 0]` | stale, 2 records | correct |
| NM.002 | `0` vs `[21, 0]` | stale, 2 records | correct |
| NM.003 | `[]` vs `[8, 0]` | stale, 2 records | correct |
| NM.004 | `0` vs `[9, 0]` | stale, 1 record | correct — 1 record, not 2; NM.004 ran only in `recalibration` |
| R4.011 | `null` vs `13` | **not stale** | **wrong** |
| R4.013 | `null` vs `13` | **not stale** | **wrong** |
| R4.014 | `null` vs `"Blistered Parsnip Crumble"` | **not stale** | **wrong** |

**Method.** For each record, compare its stored `expected` against `tasks/expected.json` under
a canonicalisation that is indifferent to JSON number spelling (`13` and `13.0` agree) and to
nothing else — `[]` and `0` disagree, and `[8, 0]` and `[0, 8]` disagree, because list order is
the answer for a corroborated multi-part expectation. A disagreement is stale. Implemented in
`corpus.eligibility`, proved in both directions by `selftest.py`.

**Why the three `R4` rows are wrong.** A stored `null` is not a recorded expectation of "no
answer". `ceiling-test/checks.py` computes `expected_value` only after a submission exists and
returns before that when nothing was submitted, so `null` means *the comparison never ran*.
All five records are from runs executing **today's battery, `1.4.0-probe`** — they are not
cross-battery at all — and each carries the oracle reason `no answer submitted (terminal:
token_budget_exhausted)`. Decisively: **sibling records for the same task in the same run file
carry `expected: 13` and `expected: "Blistered Parsnip Crumble"`, matching today's
`expected.json` exactly.** The battery did not move under these tasks; the agent ran out of
budget. B3.3's gloss that they "were graded against a null expectation — i.e. against a version
in which those tasks had no computable answer at all" describes a version that never existed.

**A null against a non-null current value is therefore not the same kind of staleness as a
changed value, and on this corpus it is not staleness at all.** Where it occurs cross-battery
it is recorded as `ineligible_unattested` (B4.3) — excluded, but for absence of evidence rather
than as a disagreement that was never observed.

B3.1's count of 12 reconstructs exactly as these 7 stale records plus those 5 no-output records.

## B4.2 — ~~6 of 20 negatives and 6 positives~~ **1 negative and 6 positives** are stale

B3.3's positive count is correct. Its negative count is **wrong**, and by the same three rows:
five of its six "stale negatives" are the R4 no-output records of B4.1, which are eligible.
The one genuinely stale negative is `NM.001` in `calibration`, a `false_success`.

Two of B3.3's derived claims survive the correction and are confirmed:

- **"B1.1's set count will fall to 1."** Correct. `set_cardinality_error` is 2 on the corpus
  and 1 on the eligible population; the record removed is the stale `NM.001`.
- **"The nine numeric false successes are all clean."** Correct. `numeric_value_error` is 9
  before and 9 after. The claim this experiment exists to test is untouched by the defect.

B3.3's *cost* figure is **superseded**: the negative denominator falls from 20 to **15**, not to
14, and for a different reason. Only 1 of the 5 excluded negatives is stale; the other 4 are
unattested (2 × `N.001` no-output, 2 × `R3.004` protocol).

## B4.3 — `ineligible_unattested`: a third status B3.2 did not anticipate

B3.2 assumes every record is stale or eligible. A third case exists and is the larger one: a
**cross-battery record with nothing to compare**, because its task's check kind yields no
`expected` under any battery version (`impossible`, `needs_clarification`, `state`) or because
nothing was submitted. Absence of a disagreement is not evidence of agreement — reading it as
agreement is precisely how B3.1 came to list three tasks that were not stale.

Such a record is **excluded** (`config.json: eligibility.on_unattested`), and separately from
the stale ones, so the two are never conflated in a count. `eligibility.on_stale` is not a
tunable and `corpus.partition` refuses to start if it is set to anything but `exclude`.

The resulting ledger, printed by the runner before selection and by
`python3 corpus.py --eligibility`:

| Status | n | negatives | positives | false successes |
|---|---|---|---|---|
| `eligible_same_battery` | 103 | 7 | 96 | 2 |
| `eligible_value_attested` | 92 | 8 | 84 | 8 |
| `ineligible_stale` | 7 | 1 | 6 | 1 |
| `ineligible_unattested` | 44 | 4 | 40 | 0 |

`eligible_value_attested` is deliberately not merged into `eligible_same_battery`: a matching
`expected` attests that the task's **answer** is unchanged, not that its **prompt wording** is.
A prompt can be reworded while the answer stays 13, and no artifact in this corpus would show
it. That residue is the part of B3.1's defect that eligibility cannot close, and 92 of the 195
eligible records rest on it.

## B4.4 — The cost B3.3 did not state: four of seven task families go to zero

B3.3 states the cost as a denominator. The larger cost is **compositional**:

| | Corpus | Eligible |
|---|---|---|
| Records | 246 | 195 |
| Families | 7 (N, NM, R1, R2, R3, R4, W1) | **3 (R1, R2, R4)** |
| Negatives | 20 | 15 |
| `no_output` / `protocol` / `false_success` | 7 / 2 / 11 | 5 / **0** / 10 |

**Every record of every lost family lives in a run that executed a superseded battery**, so no
setting of `eligibility.on_unattested` recovers any of them; only re-running the battery does.
Two consequences bind the write-up:

1. **The `protocol` class is empty.** Both records are `R3.004`. E8 can say nothing about
   whether a verifier catches a protocol violation, because no eligible trace contains one.
   The lost families are exactly the refusal-shaped ones — `impossible`,
   `needs_clarification`, `state` — so E8 is now an experiment about lookup and arithmetic
   tasks, and §11 may not describe its result as covering the corpus's task space.
2. **§6.9's advisory rider can never be discharged on this corpus.** It requires a
   false-success base of n ≥ 30 across ≥ 3 families. The eligible base is 10 across **2**
   (R4 × 9, R1 × 1). The rider is now computed from the scored population rather than quoted,
   so it cannot drift from the numbers it describes.

*Cost in validity*: larger than B3.3 estimated, and in the same direction — every interval
widens and the gate gets harder. Stated here so that a reader meeting `FOC_c2 = 65.8%` knows
it is 65.8% of R1/R2/R4 traces.

## B4.5 — The freeze now pins the battery, and cross-battery joins refuse

The root cause was that `corpus_freeze.json` pinned records but not the question they were
graded against, so the join succeeded and produced a plausible pairing. It now pins:

- the SHA-256 of `tasks.json` **and** `expected.json`;
- each in-scope run's `battery_version`, read from its own `manifest.json`;
- the declared battery version under test (`1.4.0-probe`);
- the cross-battery census itself — **5 runs, 143 records** — so the exposure cannot change
  under a passing hash check.

`freeze.verify` refuses on any drift in these, and a freeze carrying no `battery` block at all
is rejected outright rather than treated as nothing to check: that reading is what made the
defect invisible for the corpus's entire existence. The refusal is also enforced at the point
of use — `select()` requires the eligibility partition and refuses records the rule excluded,
so the rule cannot be skipped by calling the next stage directly.

## B4.6 — Assessment, not a change: §4.4's arm (c1) cannot presently make a claim

Recorded for the owner's decision. **Nothing is deleted and no clause is altered**; amendment
rule 2 forbids touching a clause after seeing what it would catch, and that rule binds here.

Measured over the eligible population, of §4.4's six clauses **two ever return a verdict**:
C1.1 (5 fires) and C1.5 (1). C1.2, C1.3, C1.4 and C1.6 return none. 69 of 75 scored records
reach C1.7 `unverifiable` — **UNV_c1 = 92.0%**, against §6.6's 50% ceiling — so §6.6 already
forbids describing c1 as covering the corpus.

The sharper finding is what its fires consist of. c1 flags 6 negatives; c2 flags 10; 1 overlaps.
c1's 5 marginal catches are **all** C1.1 on R4.011/R4.013/R4.014 — the no-output records of
B4.1 — and C1.1 asserts only that the trace contains no terminal `submit_answer`. Its
provenance field says so: `submit contract`, not the OpenAPI schema. That is a liveness check;
it needs no schema, no `openapi.json` and no derivation, and the oracle already classifies
those records as `no_output` without one. c1's single **schema**-derived fire is C1.5 on
`R1.012`, and c2 catches that record too.

**On the eligible population, the marginal contribution of c1's schema-derived clauses over c2
is zero.** §4.4 anticipated part of this — it says clauses 3–4 are "structurally blind to a
wrong-but-well-typed number" — but not that clauses 5 and 6, "the only clauses with any chance
at the false-success set", would return one verdict between them. No clause of c1 compares a
magnitude to anything, which is why: the false-success set is defined by wrong magnitudes.

Note also that §4.4's own source comments record two earlier silent vacuities in this arm (an
unescaped `total` regex, and an `isinstance(sub, list)` test against a contract that serialises
every answer as text). Both were fixed. A prior pass's claim that "two clauses can never fire"
is **narrowed** by that fix: C1.5 now can and does fire once. C1.4 still never fires.

**Assessment.** E8 has one verifier arm that can make a claim, not two. c1 should be reported
as a **negative control on derivation source** — evidence that a schema alone does not reach
value errors, which is a real and preregistered §7(5) finding — and must not be reported as the
second arm of a two-arm comparison. Whether to run it at all is the owner's call; it is free,
and the predicted-null control S3 depends on it.

*(Corrected 2026-08-03 — **wrong** in its last clause, and the error is in the direction that
matters. "It is free" is only true of money. Running c1 would have printed a fabricated
detection; "the predicted-null control S3 depends on it" is true and is exactly why the arm
could not be left runnable — S3 is scoped to the numeric class and passes while the arm is
broken in the set-typed one. The assessment's first two sentences stand and are the finding.
**Amendment B5** quarantines the arm.)*

---

# Amendment B5 — 2026-08-03, arm (c1) is quarantined; the experiment is not run

**Authorised by**: the project's decision-maker, under protocol commitment 8. Recorded by the
finding author.
**Status**: Permitted, and the permission needs stating precisely because FR-006's usual
ground does not hold. **Verifier verdicts for c1 and c2 are visible** — the 08:22 dry run
computed both for real against the frozen corpus — so this is *not* an amendment made before
results of the arm it touches were visible. It is permitted because it **retires** an arm
rather than tuning one, because it moves every verdict in the conservative direction, and
because no clause, threshold, denominator or metric is altered. Amendment rule 2 is honoured
by *not* repairing the defect below.
**Decision table**: unchanged as written, and now unreachable. `MD_best` is `max` over the
admissible arms; with c1 unscoreable it ranges over c2 alone. No row is edited.

## B5.1 — Clause C1.5 fires three times on the frozen corpus and is wrong all three times

B4.6 recorded that c1's single **schema**-derived fire is C1.5 on one record, measured over
the *eligible* population. Scored over all 246 frozen records the clause fires **three** times.
The two extra fires are on oracle-**positive** traces, both eligible, and neither is in the
60-positive stratified sample — which is why `FPR_c1` reads `0/60` in every dry run.

| record | oracle | submitted | `total` used | envelope the total came from | path C1.5 named |
|---|---|---|---|---|---|
| `20260802T163319-bias-probe/R4.002/B` | **pass** | 3 names | 34 | `/api/households/mealplans` | `/api/households/mealplans` |
| `20260802T163319-bias-probe/R4.004/B` | **pass** | 5 names | 17 | `/api/recipes` (Dessert-filtered) | `/api/recipes` |
| `20260802T173614-baseline-lookup-R1R2/R1.012/B` | fail | 60 names | 8 | `/api/organizers/categories` | `/api/recipes` |

**Corpus-wide precision of C1.5 is 0 of 3.** Two independent defects produce it:

1. **The comparand is unassociated with the path.** `_c1_5_cardinality` takes
   `totals[-1]` — the last `"total": N` anywhere in the serialised transcript — while taking
   its path from the last non-submit tool call. On the `R1.012` trace the agent read the
   recipe total with `jq '.total'`, which prints a bare `60` the regex cannot match, so the
   last *matching* total is the categories envelope's `8`. The clause compares 60 against 8,
   fails the trace, and names `/api/recipes` — which returned 60, equal to the submission.
   **A correct comparison passes this trace.**
2. **The clause's premise is false.** Where the total *does* come from the named operation
   (rows 1 and 2), the submitted answer is a *filtered subset* of the collection the envelope
   counts, so `length != total` is the normal shape of a **correct** answer. §4.4 clause 5
   asserts an identity that holds only when the answer is the whole unfiltered page.

Defect 2 is in the preregistered clause, not only in the implementation. Repairing the
envelope selection would therefore not rescue the clause: it would remove the one apparent
detection and leave both false alarms.

## B5.2 — The predicted-null control passed while the arm was broken

§7(5) and S3 predict c1 detects 0 numeric value errors. It does — 0 of 9 on the eligible
population — so the control passes, and that result is genuine evidence for §7(5). But the
control is **scoped to the numeric class**, and C1.5's fire is set-typed. A control aimed at
one failure class certifies nothing about the others, and this one certified an arm whose only
non-trivial output was fabricated. Recorded because the general lesson outlives E8: a
predicted-null control bounds the class it names and no more.

## B5.3 — What the quarantine does, and what it deliberately does not do

**Does not**: repair C1.5, alter any clause, remove any clause, change a threshold, a
denominator, a metric, or a decision-table row. Amendment rule 2 binds, and the same
discipline that makes the rest of this record trustworthy would be spent by an exception here.

**Does**, so that the arm cannot be run unwittingly:

| Mechanism | Behaviour |
|---|---|
| `c1_schema.verify()` | raises `c1_schema.Quarantined` carrying the defect and a pointer. It refuses rather than returning `unverifiable`, because an `unverifiable` would flow into `UNV_c1` and read as a measurement |
| `c1_schema.verify_clauses_quarantined()` | the preregistered walk, unaltered, reachable only from `selftest.py`, so the clauses can be *proved untouched* without being scoreable |
| `runner.py` | `refuse_quarantined_arms` runs **before** the freeze, the credential and the projection. `--arms … c1` exits with the explanation. c1 leaves the default arm list and stays an accepted value, so asking for it produces the reason rather than an argparse error |
| `controls.predicted_null` | reports **NOT RUN**, not PASS, when there are no c1 verdicts. `ControlResult` gains a `ran` field for the distinction |
| `derivation-rules.md` | a quarantine banner heads the c1 section, and C1.5 carries a dated annotation, so a reader meets the defect before the code |
| `selftest.py` | a `quarantine` group of 12 checks, plus 2 on the NOT RUN state. Total **169 checks, 0 failures**, up from 155 |

## B5.4 — §4.1's human adjudication was never satisfied, at any n

`adjudication/REPORT.md` states in its own §0 that the blind pass over the 40 sampled traces
was performed by a **model**, not a human. §4.1 requires a human, and S1's >2/40 overturn
threshold is defined over that human pass. **The requirement is open and was never closed.**
No E8 result may be written up as resting on validated ground truth. This caps what the
experiment could have claimed independently of sample size, and it is recorded here rather
than in the finding alone because it is a preregistration obligation, not an observation.

*Cost in validity*: none that is not already sunk. E8 is not run and no arm produces a number.
What is lost is the §7(5) *measurement* of c1's blindness as an arm of a two-arm comparison;
what survives is the structural result — a schema alone does not reach value errors — which
B4.6 establishes from the clause census and does not need a scored run. Full derivation in
[`findings/015-verifier-vs-judge-not-run.md`](../../findings/015-verifier-vs-judge-not-run.md).
