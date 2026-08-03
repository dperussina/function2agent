---
name: contract-derived-verification
description: Derives verification signals for an agent from code contracts — type signatures, return types, postconditions, assertions, exception classes, and existing tests — instead of from model self-assessment, and validates the derived verifier against an artifact its own derivation did not produce or marks it provisional. Use when adding a critic, reflection, or self-correction loop, designing how an agent decides it is done, writing evals or an LLM-as-judge rubric, defining terminal states or retry policy, emitting a node contract or a derived verifier, deciding whether a derived field may be stated as fact, setting provenance or confidence on anything derived, or reviewing any design where a model grades its own or another model's output. Constitution Principle I (v1.1.0) makes the validate-or-mark-provisional rule merge-blocking in this repository.
---

# Contract-derived verification

Sources: `research/03-graph-and-loop-architecture.md` §3, §7.1, §11.1–11.3;
`research/04-self-improving-agents.md` §2, §11.1;
`.specify/memory/constitution.md` Principle I (v1.1.0);
`research/14-architecture-synthesis.md` D-09, D-17;
`specs/001-discovery-validation/findings/007-contract-extraction.md` §4–5;
`specs/001-discovery-validation/findings/011-reachability-without-schema.md` §6.

> **Standing: v1, and PROMOTED — this is now half the product.** `plan.md` OD-09 (2026-08-02) cut v1
> to a spec-aware runtime, a contract-derived verifier and drift detection. This skill went from
> describing one differentiator among four to describing one of the two things that remain (D-21).
>
> **Three consequences of the promotion, and the third is uncomfortable.** ① **D-09's thin margin is
> no longer a caveat on a feature; it is a thin margin under half the product** — the ≥ 0.80 gate
> cleared at **0.8696 literal** and missed at **0.7681 validated**, and both must always be quoted.
> ② **The strongest empirical case for the verifier came from the experiment that killed synthesis:**
> the one task family where the curated surface beat the baseline did so because the API **failed
> open** — the baseline held the correct identifiers, queried by display name rather than slug, and
> was silently handed 60 records where 7 were right. A contract-derived verifier is exactly what
> catches that; nothing else in the stack does. ③ **The measurement that was supposed to earn this
> headline status was never taken.** `11-validation-plan.md` Phase 2 would have produced the
> verifier's *marginal detection over an LLM judge*; Phase 2 never ran. The promotion rests on
> extraction accuracy plus argument, not on the head-to-head. Say so when citing it.
>
> ~~**⛔ Updated 2026-08-03 — `plan.md` OD-11 turns ③ from a caveat into a gate.** The head-to-head runs
> **before the production specification**, and the spec is blocked until it returns.~~ **The reason to
> state plainly rather than soften: if a general-purpose LLM judge catches everything a
> contract-derived verifier catches, this skill describes a CI detail rather than a product** — and
> with promotion selection and effect classification already in v2, there would be no v1 left. The
> gate is inherited verbatim from `11-validation-plan.md` §8 rather than re-derived: **≥ 10 pp →
> headline feature; < 10 pp → CI detail; judge AUROC < 0.5 → a constitutional ban on LLM judges in the
> success path** (that third branch fires on the judge's own number regardless of what the verifier
> scores). ~~A harness is being built for it.~~ **Until it returns, every claim this skill makes about the
> verifier's advantage over a judge is inherited from other domains (AUROC 0.18–0.30) and must be
> cited as such** — which is Principle I applied to this skill's own headline.
>
> **⛔⛔ SUPERSEDED THE SAME DAY — `plan.md` OD-14 retires the gate, and the *state* it leaves behind
> is worse for this skill than the gate was, not better.** The harness was built, self-tested and
> **dry-run at $0.00**, then **not executed**: the surviving discriminative sample is 2 traces, three
> pre-registered riders cap the verdict independently so no achievable outcome licenses the headline
> claim, and four of seven task families are lost to the eligibility rule. **The verifier's margin
> over an LLM judge is declared UNMEASURED and deferred to production traffic.** The spec is
> unblocked; the gate above travels verbatim into production instrumentation — **and travels
> *unevaluated*.** Every branch of it reads a quantity defined over judge verdicts, no judge verdict
> exists anywhere, so **nothing cleared that gate and nothing failed it.** Read UNMEASURED as a null
> on *power*, not on the hypothesis: the corpus cannot tell, which is not the same as the answer
> being no, and a future measurement is unprejudiced in either direction.
>
> **Hold these two apart when citing this skill, because the record has already blurred them.**
> **The mechanism is demonstrated and was not fitted:** the postcondition arm detects **all 9 numeric
> value errors including all 3 sub-1% near-misses, with zero false alarms across 220 clean
> positives** — *the offline full-corpus sweep; the `FPR_c2 = 0/60` quoted elsewhere is the
> judge-scored sample and a smaller population, and the two must never be merged. See the labelling
> table at [14](../../../research/14-architecture-synthesis.md) §3.2* — through a **six-rung
> precision ladder committed before any derivation was written that
> contains no numeric constant** — each rung names a *source* of precision, never a value, and the
> last rung refuses rather than defaulting to a tolerance. **The margin is not demonstrated:** no
> judge call was ever billed, and every judge figure in the committed artifacts is a stub. **"The
> verifier works" is supported. "The verifier beats a judge" is not, and the inherited-AUROC caveat
> above therefore still governs every comparative claim in this skill.**
>
> **One design constraint this skill must now carry, and it is ~~the most transferable thing E8
> produced~~ the most transferable thing E8 produced *about verifiers*** *(narrowed 2026-08-03, not
> withdrawn — the most transferable thing E8 produced is not about verifiers at all: see
> [U-47](#freeze-the-questions-not-only-the-files) under Evaluation rules)*. The failure that matters
> was **schema-conformant end to end** — the request was
> schema-valid, the response was schema-valid, and the answer matched the application's own reported
> total, while being wrong. A schema-derived verifier is structurally blind to it: the schema-derived
> arm detects **0 of 9** numeric value errors and returns `unverifiable` on 92% of traces. **Specify
> the verifier as recomputation against an independent source, not as a second pass through the same
> contract.**
>
> **Why that last sentence is a structural claim and not a tuning note — the measurement behind it,
> added 2026-08-03 from `research/14` D-21 amendment (4).** The schema arm did not merely score
> badly; **no clause of it compares a magnitude to anything.** It returned `unverifiable` on **69 of
> the 75 records it scored** — `UNV_c1` = **92.0%** against a pre-registered 50% ceiling — and its
> only marginal catches came from a liveness clause whose own provenance field reads `submit
> contract` rather than the schema, checking merely that the trace contains a terminal submission.
> Its single genuinely schema-derived fire was **wrong**, and corpus-wide that clause is right **0 of
> 3** ([C-19](#a-passing-control-is-not-evidence-about-the-component)). **The false-success class is
> *defined* by wrong-but-well-typed values, so a checker that validates shape cannot reach it by
> construction** — no better schema and no additional clauses change that. What reaches it is the
> independent recomputation path, which is what the postcondition arm is and what detects **10 of 10**
> eligible false successes. **Read this as a rule about the derivation, not about the format:** the
> recomputation must be a *second derivation against the application's own API*, not a second pass
> through the contract that produced the first answer. **The v2 corollary, because it is the version
> most likely to be built by accident:** a synthesis layer that emits schema-level checks alongside
> each synthesized tool emits a verifier that **cannot see the failure class the product is sold on.**

Sources continued: `research/11-validation-plan.md` §8 (Phase 2, ~~scheduled 2026-08-03 and blocking the
spec~~ **scheduled and then de-scheduled 2026-08-03; built, dry-run at $0.00, never executed**);
`research/14-architecture-synthesis.md` D-21 **(especially amendment (4))**, P-07, P-09, **C-19,
U-47**, TL;DR 21, **§3.2 labelling table**; `plan.md` ~~OD-11~~ **OD-11 as
retired by OD-14**; `specs/001-discovery-validation/VERDICT.md` §2 (all three v1 capabilities ship
unmeasured); **`specs/001-discovery-validation/findings/015-verifier-vs-judge-not-run.md`** — the
finding all three of those register entries come from, and the only measurement of this skill's
subject that exists.

**The core claim:** a project that starts from *functions* gets a free, hard-to-game verifier that
most agent frameworks have to invent. Use it. Do not substitute model opinion for it.

**The claim that had to be added to it, on measurement:** a derived verifier can also be complete and
wrong, and at the point of use that is indistinguishable from a correct one. Section
[Validate the verifier, or mark it provisional](#validate-the-verifier-or-mark-it-provisional) is
merge-blocking in this repository, not advice.

## The two negative findings that constrain everything here

State both plainly whenever someone proposes a reflection or judge loop.

**1. Intrinsic self-correction degrades reasoning.** Huang et al., *Large Language Models Cannot
Self-Correct Reasoning Yet* (ICLR 2024, [arXiv:2310.01798](https://arxiv.org/abs/2310.01798)): a
model critiquing its own answer with **no external signal** *reduces* accuracy across models and
benchmarks. Apparent gains in earlier work came from **oracle labels** deciding when to stop — that
is oracle-guided filtering, not self-correction. A 2026 follow-up
([arXiv:2601.00828](https://arxiv.org/abs/2601.00828)) found error-detection rates of 10%–82% across
models and, critically, that detection rate **does not predict correction success**.

Read the title as "cannot be *prompted* into self-correction," not "cannot learn to" — SCoRe
([arXiv:2409.12917](https://arxiv.org/abs/2409.12917)) got genuine intrinsic gains via RL. That is a
training-time intervention. You do not get it by adding a critic node.

**2. LLM judges are anti-correlated with truth on false-success detection.** On distinguishing
*false success* (agent claims completion, did not complete) from *honest failure*, judges across
GPT-4o, Sonnet 4.5, and Llama-3.3-70B scored **AUROC 0.18–0.30** — worse than a coin flip, in a
consistent direction ([arXiv:2606.09863](https://arxiv.org/abs/2606.09863)). The mechanism is
anchoring on surface completion signals: confident assertive language reads as success, honest
failure language reads as failure, regardless of ground truth. On AppWorld the same structure
appeared as anchoring on API-call volume, with GET-only sequences read as completing write tasks.
An explicit checklist raised GPT-4o from 0.394 to 0.537 — still far below a purpose-built detector.

**Therefore: never let a judge decide "did it succeed." That is the exact task judges fail at.**

## When a critic is worth its tokens

Exactly when the critic has information the generator did not.

| Verdict | Signal |
|---|---|
| ✅ | Compiler / type checker / test suite output |
| ✅ | Schema validation, API error responses |
| ✅ | State verification — did the database row actually change? |
| ✅ | A retrieval step grounding the critique in source documents |
| ✅ | A different model, or the same model with genuinely different context |
| ❌ | "Review your answer and improve it." |

The clean-context reviewer is the legitimate version of the second-model case: a reviewer sharing
*no* context with the coder catches ~2 bugs per PR, ~58% of them severe. Withholding context helps —
the reviewer reasons backward from the implementation and its short context dodges context rot. That
is categorically different from self-critique.

## Signature → verifier mapping

This is mechanical. Everything below falls out of a type signature and a docstring; nothing is
invented.

| Function artifact | Derived verification asset |
|---|---|
| Parameter types | Input guard; fail fast on a malformed request |
| Documented preconditions ("amount > 0 and ≤ order total") | Guard predicate → route to a gather node, not an exception |
| Return type annotation | Output validator; repair-loop trigger; eval assertion |
| Postconditions / invariants ("refunded_total increases by exactly amount") | **State verification** — the strongest check available |
| Raised exception classes | Typed failure taxonomy; distinct repair vs. retry vs. escalate paths |
| Documented-retryable exceptions | Retry edge with backoff, counting against the shared budget |
| Semantic exceptions (`InsufficientFunds`) | Typed terminal `Failed(...)` — **not** a retry |
| Docstring | Rubric seed and routing hint |
| Existing unit tests | Regression suite for any change to the node |
| Purity | Safe to replay, cache, parallelize |
| Idempotency key | Exactly-once under replay and human-in-the-loop resume |

**The rows are not interchangeable, and as of 2026-08-03 the gap between two of them is measured
rather than argued.** The parameter-type and return-type rows validate **shape**; the postcondition
row recomputes a **value**, and it is the only row that does. Scored against each other on the same
corpus, an arm built from the shape rows alone reached **0 of 9** numeric value errors and abstained
on 92% of traces, while the postcondition row reached **9 of 9** including all 3 sub-1% near-misses
(D-21 amendment (4)). So a build that ships the shape rows and defers the postcondition row has
shipped the cheap half and **left the failure class the verifier exists for entirely uncovered** —
which is worse than having no verifier at all, because the shape checks pass and read as coverage.

A contract-derived verifier is also **much harder to reward-hack** than a learned or LLM-based
reward. That is the RLVR insight available at the framework level, on day one.

**Product principle:** never ship a naive LLM self-critique as the default improvement mechanism.
The evidence says it makes users' agents worse. Ship the contract-derived verifier instead.

## Validate the verifier, or mark it provisional

Added 2026-08-02, when constitution Principle I was amended to v1.1.0. The mapping above is
mechanical, and *mechanical is not the same as correct.* Principle I as originally ratified split
nodes two ways — has a derivable verifier, has none — and three measurements produced a third case by
unrelated mechanisms: **a verifier that was derived, looks complete, and is wrong.**

> A derived verifier MUST be validated against an artifact its own derivation did not produce. Where
> no independent artifact exists, it MUST be marked provisional and carry its provenance and
> confidence — because a verifier that is complete and wrong is indistinguishable from a correct one
> at the point of use.

**Why this is not paranoia.** Disabling one derivation rule — following a Pydantic `alias_generator`
declared on a base class three files away — left 15 of 69 endpoints (21.7%) with contracts carrying
the right field count, locations, types and required flags and **every field name wrong on the wire**,
with nothing in the output indicating it. A tool built from one fails every call it ever makes and
returns a 422 an operator reads as the caller's bug. Separately, 354 of 355 populated `docstring`
values were not docstrings. And removing the target's published schema left **every derived quantity
identical** — 60/69 contracts, 207 parameters, 53 return types — while the *validated* rate went from
0.7681 to uncomputable. **No visible metric moved.** That is the whole problem: the degradation is
invisible in every number the pipeline produces.

**The asymmetry to keep in mind, because it decides the default:** a missing field is safe, because a
consumer can see it is missing. A plausible wrong field is not, because nothing downstream can tell.

### The decision procedure

Run this on every derived verifier, before it is emitted or relied on.

1. **Name the derivation.** Which rule produced it, from which symbol, in which file, at which
   analyzer version. A field read off a handler signature and a field recovered by walking a base
   class three files away are not the same kind of claim, and the artifact must say which it is.
2. **Find an independent artifact.** Independent means *not produced by this derivation*: an OpenAPI
   document, a JSON Schema file, a client SDK, a recorded request/response, an existing test that
   asserts the shape, a published type stub. The framework generating a schema from the same
   annotations you read is still independent of *your derivation* — it is not independent of the
   *source*, and that is the weaker guarantee you actually get. Say which you have.
3. **Check, and record the outcome as data.** `validated_against` plus a pass/fail, not a comment
   saying "derived, not written by a model" — which asserts where a value did *not* come from while
   staying silent on where it did.
4. **If step 2 found nothing, mark it provisional.** `validated_against: none` forces
   `confidence: provisional`. This is not a lower score, it is a different type. A consumer that
   requires a validated verifier **fails closed** rather than proceeding on a provisional one.
5. **Never let step 2's absence be filled by a model.** "No independent artifact exists, so ask an
   LLM whether the contract looks right" is the exact substitution the two negative findings above
   forbid, wearing a different hat.
6. **Score the check on the full population offline, not on the sample.** Added 2026-08-03 from
   C-19. A verifier's own error rate is model-free and therefore *free* to compute over every record
   you hold, so there is no reason to learn it from a sample — and a sample drawn for some other
   component's metric is not sized to expose this one's failure mode. Reserve the sample for the
   metric it was sized for and say, in the artifact, which population each number came from.

### What this looks like when it is done right

```yaml
verifier:
  return_shape: RecipeSummary          # 4 fields, all required
  provenance:
    rule: pydantic_model_walk_v3
    source_symbol: api.recipes.get_recipe
    source_file: mealie/routes/recipes.py
    analyzer_version: 1.5.0
  validated_against: openapi           # or: schema_file | sdk | recorded_request | none
  validation_result: agrees            # or: disagrees | uncomputable
  confidence: validated                # forced to `provisional` when validated_against == none
```

### Where it applies beyond a catalogue field

Twice now this shape has been the answer to a question that was not about metadata, so read
requirements 1 and 4 as a general discipline about derived claims rather than as a schema.

| Derived claim | Independent artifact | If none exists |
|---|---|---|
| Parameter set / return shape | Published schema, SDK, recorded request | Provisional; consumer requiring validation fails closed |
| **Failure taxonomy** (`raises`) | Usually **none** — a framework schema is silent about handler raises | **Always provisional.** This is the normal case, not the exception |
| A method set on a route | The route table, where the router carries one | Record `inferred` rather than `recovered`, and refuse to act on `inferred` |
| A metric in your own harness | A second run varying the arbitrary constants | Re-read a metric that moves as measuring the constant, not the mechanism |

**Two failure modes to name out loud in review.** Reporting a *safety* defect as an *accuracy* metric
— a recall figure moved 3.5 points on a sentinel string while the underlying defect was unchanged,
which is the direction of error that gets a defect deprioritised. And a safety property held by one
component that an unrelated accuracy improvement in another silently removes; the only mitigation is
requirement 1 applied to the decision rather than to the field.

### A passing control is not evidence about the component

Added 2026-08-03 from C-19, and it is the sharpest instance of this section's whole argument: **the
verifier that was complete-and-wrong had a negative control over it, the control passed, and the
control was right to pass.**

The prediction under test was that a schema-derived arm detects **zero numeric value errors**. It
detects zero; the control passes; that pass is genuine evidence and is not withdrawn. In the same
run, the arm's one clause that produced any non-trivial verdict fired three times and **was wrong
all three times** — a cardinality clause comparing a submitted collection's length against a `total`
it took from the last envelope anywhere in the transcript, naming in its provenance string an
endpoint it never read. **Corpus-wide precision 0 of 3.** The control could not see it, because the
control is scoped to the *numeric* class and every one of those fires is *set-typed*.

Then the metric designed to catch exactly this missed it too. Both false alarms fell outside the
seeded 60-positive stratified sample, so the arm's `FPR` read a perfect **0 of 60** in every run
**while the arm was fabricating**. Both records were eligible; they were simply not drawn.

**Three rules, and they generalise past any one harness.**

1. **Every negative control states, in its own output, the class it bounds.** A control that does not
   name its scope will be read as unconditional — it was, by three consecutive artifacts.
2. **A passing control on a component is evidence about the class, never about the component.** A
   predicted-null control is a bound on one failure class and is silent about every other by
   construction.
3. **Where a component's failure mode is unknown, score it on the full population** (decision
   procedure step 6). A denominator that excludes the failure is indistinguishable from a
   denominator that contains none.

**Why this is a contradiction rather than a limitation.** A limitation narrows a claim. This one made
a broken component *look verified*. The pattern to watch for is that **the control and the defect
were designed by the same reasoning**, so the blind spot is shared rather than independent — which
is the same argument requirement 2 makes about independent artifacts, arriving one level up.

## Typed terminals

Every terminal state must be typed and distinguishable:

```
Done(result)
Failed(reason)            # reason drawn from the exception taxonomy
BudgetExhausted(partial)
NeedsHuman(question)
Aborted
```

Collapsing these into "returned a string" destroys your ability to measure anything. The specific
expensive bug: an agent returns a confident summary on budget exhaustion and downstream code treats
it as success — the false-success pattern that judges cannot detect. Typed terminals make it a
non-issue for the common case.

**Separate `evaluate` from `decide`.** If the model decides both "what to do" and "am I done," the
actor and the critic are coupled and you get premature termination and false success. Cheap
deterministic checks (did the file get written? did the API return 2xx? does the output parse?)
belong in `evaluate` and cost nothing.

## Termination conditions — you need all of these

| Condition | Type | Notes |
|---|---|---|
| Model emits final answer | Semantic | The intended exit. **Never the only exit.** |
| Goal predicate satisfied | Programmatic | Best kind. `assert invoice.status == "paid"` |
| Step budget exhausted | Hard | Set 10–40. A framework default of 1000 is a safety net, not a budget |
| Token / cost budget exhausted | Hard | Track in a summing state channel |
| Wall-clock deadline | Hard | Especially for user-facing turns |
| No-progress detector fired | Heuristic | See below |
| Unrecoverable error | Hard | Distinguish from retryable |
| Human interrupt | External | |

**Bound the whole tree, not each loop.** Nested caps multiply: 5 × 5 × 5 = 125 model calls. Carry one
global budget in a summing channel and check it in every loop.

### Non-progress detectors, in order of value

1. **Repeat-action.** Hash `(tool_name, canonicalized_args)`; 3 identical hashes in a window means
   stuck. Respond by *injecting the observation* ("you have called `search('foo')` three times with
   the same result") — this often unsticks it and beats a bare retry.
2. **Oscillation.** `A→B→A→B` with no state delta. Usually a validator rejecting and a generator
   regenerating the same thing. Break by escalating, **never** by raising the limit.
3. **State-delta monitor.** Define a `progress` projection (files written, fields filled, subgoals
   closed). Unchanged across N iterations means thrashing no matter how busy the trace looks. Most
   general detector; most worth building.
4. **Cost-per-progress ratio.** Rising sharply → abort. Also the best online health metric.

**Two anti-patterns.** Raising the recursion limit to fix a stuck agent converts a fast failure into
a slow expensive one and is never the fix. Retrying an identical call after a *semantic* failure
just pays for the same failure again — you must change something (inject the error text, switch to a
repair prompt, escalate).

## Evaluation rules

- **Verify the world, not the last message.** τ-bench checks resulting database state; SWE-bench
  runs the test suite. An agent that says "I booked the flight" without booking it passes a text
  check and fails a state check.
- **Grade the trajectory too, not just the outcome.** They disagree often enough to invert rankings.
  An agent that completes a task by bypassing authorization or fabricating confirmations scores
  *identically* to one that followed every step — "corrupt success"
  ([arXiv:2603.03116](https://arxiv.org/abs/2603.03116)). Trajectory eval is how you verify a
  protocol actually held. Useful metrics: required-step coverage (binary, straight from the trace),
  tool-order fidelity, argument correctness, redundancy ratio, recovery rate, policy-violation
  count, cost per success.
- **Report reliability, not just accuracy.** Run the eval set n≥3 times and report **pass^k**
  alongside pass@1. 80% at one attempt and 30% across four is a different product from a stable 80%.
- **Freeze a held-out set the optimizer never sees.** Train / dev / test, with test touched rarely.
  If offline eval is dramatically better than online quality — a ~10-point gap is the red flag —
  suspect contamination *before* trusting either number. **And freezing the *files* is not freezing
  the *set*** — see [Freeze the questions, not only the files](#freeze-the-questions-not-only-the-files).
- **Sample stratified, not uniform:** failures at 100%, near-misses high, successes at 1–5%.
  **Stratify for one metric and you have sized the sample for one component**; any other component
  scored on the same draw is being measured on a population nobody chose for it, and the number it
  reports can be perfect while it is broken (C-19). Verifier-side error rates cost nothing to
  compute, so compute them on everything you hold and keep the sample for the calls that cost money.

### Freeze the questions, not only the files

Added 2026-08-03 from U-47, which is **blocking** and is the one thing in this skill that is not
about verifiers at all. It applies the moment anyone **re-scores frozen traces later** — which is
what an offline eval of a derived verifier *is*, and what any production instrumentation comparing a
verifier against a shadow judge will be.

**The defect.** A freeze pinned the SHA-256 of all 22 corpus files and refused to start on a change
to any of them. **It did not pin the questions the traces were answers to.** A trace record stores
the transcript and the verdict, and the transcript begins at the agent's first *assistant* turn, so
the prompt is reachable only by joining to an external, mutable task file. Task ids are stable across
battery versions, **so the join is total, and a join that cannot fail cannot warn.** Five battery
versions pooled into one corpus; **143 of 246 records ran under a battery that no longer exists.**

**The obvious detector is blind to the case that matters.** The dangerous drift is *wording*: an
amendment that clarifies a question without changing its answer leaves every stored `expected` value
matching, so a stored-versus-current comparison passes it. **7 of the 9 numeric false successes in
that corpus are prompt-drifted and all 7 pass that test.** And a rebased corpus **cannot be repaired,
only trimmed** — historical prompt text is unrecoverable once transcripts start after the prompt.

**Four fixes, all free at build time and none available afterwards.**

1. **Record the prompt inside the trace record**, so the artifact is self-contained.
2. **Pin the battery version and the task-file hashes** in the freeze, not only the corpus files.
3. **Pin the cross-battery census**, which converts "58% of this corpus is cross-battery" from a fact
   someone once measured into an invariant re-checked on every load.
4. **Make the analysis path refuse a cross-battery join** rather than perform one.

**And one dividend that belongs to this skill specifically.** A postcondition verifier pointed at a
rebased corpus **reports the rebasing as a wall of false alarms**: scored over all 226
oracle-positives, the arm raised 6 alarms and all 6 were the 6 stale records — it reproduced the
stale set exactly, consulting no manifest, no battery version and no eligibility verdict. **Anyone
who has already built the verifier this skill describes has a corpus-drift detector for free**, and
the read to internalise is the inverse: an unexplained cluster of verifier false alarms on a frozen
corpus is evidence about the *corpus* before it is evidence about the verifier.

### If you must use a judge

1. Programmatic first — anything checkable in code must not be judged by a model.
2. Never for "did it succeed."
3. Pairwise, not absolute, with order swapped and both orders averaged.
4. Judge must not be the model family under test. Self-preference bias is *uncorrelated or
   negatively correlated* with capability ([arXiv:2604.22891](https://arxiv.org/abs/2604.22891)) —
   the best models are not the fairest judges.
5. Calibrate against a frozen human-labeled set; track Cohen's κ as a metric that can itself regress.
6. Decompose the rubric into named dimensions (reduced self-preference ~31.5% on average).

Judge bias is **structured and predictable, not random**, occupying a low-dimensional type-specific
activation subspace ([arXiv:2607.11871](https://arxiv.org/abs/2607.11871)). It does **not** average
out across many judgments.

## Loop patterns, ranked by evidence

| Pattern | Cost | Needs external verifier | Verdict |
|---|---|---|---|
| Verifier-in-the-loop (repair) | 1.5–3× | **Yes** | ✅ Highest-ROI loop in agent engineering |
| Generator–critic, LLM critic only | 2–4× | — | ⚠️ Evidence says it hurts reasoning. Style/format only |
| Plan–execute–replan | 1.2–2× | No | ✅ Above ~8 steps, or approval-before-work |
| Best-of-N + programmatic scorer | N× | Yes | ✅ Cheap gen, cheap check, high variance |
| Best-of-N + LLM judge | N×+ | No | ⚠️ Often just selects for verbosity |
| Debate | 3–5× | No | ❌ No better than self-consistency at equal compute |
| ToT / GoT / LATS / MCTS | 5–100× | **Yes** | ⚠️ Narrow. Only with a cheap programmatic scorer for *partial* states, and gate the branching |
