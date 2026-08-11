# Feature 001 findings — measurements of the world the product must work in

**Opened**: 2026-08-02, with the discovery corpus.
**Feature**: `001-discovery-validation` ·
**Plan**: [`../plan.md`](../plan.md) ·
**Specification**: [`../spec.md`](../spec.md) ·
**Closing verdict**: [`../VERDICT.md`](../VERDICT.md)

This is the corpus's **first** authority namespace. The second is
[`../../002-spec-aware-agent-runtime/findings/`](../../002-spec-aware-agent-runtime/findings/), and
both are authoritative in the same sense and by the same rule: `tools/corpuscheck/config.json`
classifies `specs/*/findings/*.md` as `authority`, so `numeric-provenance` treats every figure
written here as a source of record rather than as a quotation needing one.

---

## This index exists because a checked claim made its absence visible

The root [`README.md`](../../../README.md)'s repository map states the corpus-wide total across both
`findings/` directories, and that sentence is the `findings` inventory rule's first live site in the
rule's life. A reader following a checked total previously reached an index covering the other
directory and nothing at all for this one. The asymmetry was there before; what changed is that a
gated sentence now points at it.

Adding this file moves no count. The `findings` rule globs `specs/*/findings/[0-9]*.md` for its
truth, and `README.md` has no numeric prefix, so the directory reads the same 19 documents with this
file present as without it.

## This namespace is closed, and closed does not mean frozen

[`../VERDICT.md`](../VERDICT.md) records feature 001 as **CLOSED**, on the authority of
[`../plan.md`](../plan.md) **OD-07**. The closure is scoped, and the scope is load-bearing enough
that a finding has already been filed against a misreading of it: what does not happen is a *new*
feature 001 finding **about production work**. Correcting, extending and re-scoping the documents
already here does happen, and has — the most recent edits to three of them are dated 2026-08-11.

Two consequences follow for anyone reading this directory. Documents dated 2026-08-02 and 2026-08-03
were written while the feature was live and several have been overtaken since. And the directory
holds one document minted after closure: [031](./031-provider-state-chain-measured.md) measures four
commercial LLM providers, which is a measurement of the world rather than of this project's output,
and an owner decision of 2026-08-05 moved it here from feature 002 with its number preserved.

## Numbering: this namespace opened the corpus-wide sequence

Feature 001 issued **001 through 018**. Feature 002 starts at 019. Finding numbers are unique across
the whole repository rather than per feature, and `findings-numbering` enforces that corpus-wide —
established by planting a cross-directory duplicate and reading the failure, not by argument. The
directory therefore holds 001–018 **and 031**, and the gap between them is not a gap in this index.

## Two kinds of supersession, and this index does not flatten them

**Twelve of the nineteen findings carry an in-place supersession — eleven of them dated — and three
supersede a claim inside their own headline section.** A fourth carries a superseded identifier in
its own H1. Reading titles, or reading the first paragraph under one, would have propagated
retracted claims out of an authority namespace, so every row below is sourced from the document's
current text and states the superseded reading where one exists.

The two kinds are different in what they license, and the rows say which is which:

- **Self-corrected** — the document's own author recomputed, rescoped or restated. The result is a
  better version of the same finding, and the finding remains the authority on its subject.
  [003](./003-runtime-provider-agnosticism.md), [008](./008-ceiling-test-calibration.md),
  [009](./009-ceiling-test.md) and [012](./012-ceiling-test-per-family.md) are of this kind, as is
  one of [006](./006-graph-loop-primitives.md)'s two corrections.
- **Overtaken** — a later finding or an owner decision reached a different answer, and the finding
  is no longer the authority on the part that moved. [001](./001-structure-recovery.md),
  [005](./005-ceiling-test-harness.md), [010](./010-deployment-reachability.md) and
  [016](./016-provider-sdk-roundtrip.md) are overtaken by later findings;
  [006](./006-graph-loop-primitives.md), [015](./015-verifier-vs-judge-not-run.md),
  [017](./017-evaluation-contemporaneity.md), [018](./018-verifier-false-alarm-attested-denominator.md)
  and [031](./031-provider-state-chain-measured.md) by owner decisions.

**One finding is overtaken and does not say so.** [016](./016-provider-sdk-roundtrip.md) carries no
strike, no correction and no forward reference, while
[finding 030](../../002-spec-aware-agent-runtime/findings/030-provider-state-chain-derived-not-measured.md)
records that its arms have no persistence boundary at all and
[finding 031](./031-provider-state-chain-measured.md) measured the question it was read as answering.
A reader who opens 016 alone finds nothing telling them so, and that is the one row here whose
supersession is visible only from outside the document.

## Index

The table below carries one row per finding filed in this directory. There are nineteen; the
corpus-wide total across both namespaces is stated in the root
[`README.md`](../../../README.md), which is where `inventory-count`'s `findings` rule reads it.

**Spend is the figure the document itself reports**, and where a finding recomputed its own spend
against committed artifacts both readings are given — the artifact-verifiable floor and the spend
actually incurred are different numbers and the findings say so.
[016](./016-provider-sdk-roundtrip.md) and [031](./031-provider-state-chain-measured.md) publish no
dollar total at all, because only one of their four providers returns a cost figure and neither
finding invents price tables for the other three.

| Finding | Subject | Spend |
|---|---|---|
| [001](./001-structure-recovery.md) | Structure recovery against a real production monorepo: 1,161 nodes of kind `route`, of which 866 (**74.6%**) are real HTTP endpoints and the rest middleware registrations, wildcards and verb-less client-side UI routes. **Overtaken by [finding 004](./004-recall-against-authoritative-key.md) in four corrections dated 2026-08-02, one of them inside §1 "the headline number"**: the verb filter that took precision *"from 74.6% to essentially 100%"* here **removes zero of 41 false positives** on `google/adk-python`, where the extractor always emits a verb and `@mock.patch` survives the filter as a `PATCH`. The filter is a property of that first target, not a general post-filter; the 58% figure is likewise a TypeScript-path artifact | `$0.00` |
| [002](./002-provider-credentials.md) | Bring-your-own provider credentials, probed live: model-list endpoints answer the authentication and enumeration question for free, since a `200` proves the credential authenticates and enumerates exactly what that key may reach without generating a token. No claim in the document is superseded; one next step is struck as discharged rather than retracted — *"~~Rotate the Gemini key~~ — **not needed.**"* | `$0.00` |
| [003](./003-runtime-provider-agnosticism.md) | Can the candidate runtimes actually be driven by a non-default provider — ADK 2.6.1 through `google.adk.models.lite_llm.LiteLlm`, with chained tool-calling as the load-bearing capability rather than completion. **Self-corrected 2026-08-02**: *"35 times"* is a count of matching source lines and not of references, and all three counts are restated under one stated counting rule after the distinction went unstated | `≈ $0.09` |
| [004](./004-recall-against-authoritative-key.md) | Recall against an authoritative answer key, closing the half [finding 001](./001-structure-recovery.md) said plainly it could not measure — *"precision without recall is half a measurement, and the missing half is the one that hides silent failure."* This is the document that overtakes 001's verb-filter result | `$0.00` |
| [005](./005-ceiling-test-harness.md) | The ceiling test harness, built and smoke-tested, whose most useful product was a defect in itself: a negative control given no tools and told to claim success passed a write task, because the write check evaluated post-state predicates only and credited an agent that had done nothing. **Superseded in part, undated, by [finding 008](./008-ceiling-test-calibration.md)** — the five remediations were carried out, the battery grew from 43 tasks to 57, the baseline's budget was tripled, two calibration passes ran and four further harness defects were found. The description of the target application, the tool set and the two arms remains accurate | `$2.79` |
| [006](./006-graph-loop-primitives.md) | Does ADK supply the loop-safety machinery, or do we build it: **two of four primitives missing against a threshold of three**, with checkpoint-and-resume present at at-least-once and named terminal conditions absent as a taxonomy. **Overtaken 2026-08-03 by [`plan.md` OD-15](../plan.md)**, which drops ADK from v1 entirely and strikes the adopt recommendation — *"that measurement is unchanged and OD-15 does not overturn it"*, and the 2.5–3.5 week estimate was scoped to loop safety with the runtime adopted, so no re-derived figure exists. **Separately self-corrected 2026-08-02** on reproduction: the scripts are committed | `≈ $0.0003` |
| [007](./007-contract-extraction.md) | Contract extraction: **207 inputs derived against 207 expected, zero mismatches** on name, location, required flag and type across all 69 endpoints, with 53 return-type agreements and zero disagreements. Against the pre-registered **≥ 0.80** gate both readings are reported — **0.8696 clears it, 0.7681 misses it** — and the most important result is neither: switching off one alias-generator rule leaves 15 of 69 endpoints with a contract that is fluent, plausible and wrong about every field name on the wire, with nothing in the output to indicate it | `$0.00` |
| [008](./008-ceiling-test-calibration.md) | E7 remediation and calibration: five pre-agreed remediations, a calibration pass of the tool-equipped arm over the whole battery, and the battery still not ready. **Self-corrected by a basis note added 2026-08-03**, which separates two legitimate accounting bases rather than declaring an error — the committed per-attempt rows sum to a lower figure than the one reported, and the difference is negative-control spend incurred but never committed. No calibration verdict depends on it | `$4.80` this session; `$7.59` across two sessions, of which `$7.51` is the artifact-verifiable floor |
| [009](./009-ceiling-test.md) | The bias probe stopped the rebalance and the baseline wins the composition family: **4 of 4 for the baseline against 1 of 4 for the tool arm** on the per-record tasks OD-04 newly admitted, and 10 of 10 against 9 of 10 on join-and-arithmetic. **Self-corrected twice on 2026-08-03, and one of the two defends its own figure against a correction made elsewhere**: the three-session total is right and the figure that was called right is the one that is off, because two accounting bases exist and neither is an error. The second restates the cost row on the post-fix denominators that govern, moving the join ratio from ~~2.8×~~ to **2.20×** | `$10.56` this session; `$18.09` across three sessions |
| [010](./010-deployment-reachability.md) | Deployment reachability: **R1-tuned passes by 0.0038 at the margin** and R2-openapi at 1.0000/1.0000, with R0 and R1-naive both missing and R1-naive worse than doing nothing. **Overtaken in nine corrections dated 2026-08-02 by [finding 011](./011-reachability-without-schema.md), the first of them inside "Gate adjudication, stated before anything else"**: R2-openapi's result holds only on deployments that publish a schema and falls to **recall 0.0000** on `ABSENT`, `FORBIDDEN` and `EMPTY`; *"the fallback is R1-tuned"* is wrong; and the ablation claim names `M1_class_dispatch` **or** `M2_kwarg_flow`, either one, where the prose named only the first while this document's own table showed both | `$0.00` |
| [011](./011-reachability-without-schema.md) | Reachability without a published schema: schema state detected and distinguished **7 / 7**, and the operation-granularity precision gate **missed at worst 0.8750** for the arm the design specifies. The reason is not the missing schema — on all four FastAPI configurations, including the one behind a 401, the schema-free probe scored 1.0000/1.0000. **Every false positive across three arms and seven targets is a method-level error and there are no path-level errors anywhere**, so a schema-free mechanism can be accurate, complete or safe and only two at once | `$0.00` |
| [012](./012-ceiling-test-per-family.md) | Per family, the tool surface never wins on success — it ties on two families and loses on one — and it is cheaper wherever it succeeds at all. **Self-corrected 2026-08-03 inside `## The headline` itself**: the range reads ~~5× to 9×~~ **2.2× to 9.3×**, and the join figure reads ~~2.8×~~ **2.20×** once the cost row is put on the post-fix denominators. Success rates and every verdict are unchanged. A basis note of the same date separates the artifact-verifiable floor from spend incurred | `$6.58` this session; `$24.73` across four sessions, of which `$24.67` is the artifact-verifiable floor |
| [013](./013-ceiling-test-budget-parity.md) | The budget mismatch was real and contributed nothing: **budget's contribution to the cost ratio is a factor of 1.0000**. The paired, one-fingerprint run gives 4.366× against the historical cross-run 5.059×, and the historical value sits inside the run's own bootstrap 95% interval of **[3.384, 5.423]**, so the two point estimates are not statistically distinguishable at one attempt per task | `$5.5168` this session; `$35.0817` artifact-exact across six E7 sessions |
| [014](./014-ceiling-test-replication-and-noise-floor.md) | The fail-open is a property of the application rather than of the tool abstraction, established model-free against the running instance: Mealie answers **HTTP 200** and returns the entire unfiltered collection for any `categories` value it cannot resolve — a display name, nonsense and the empty string all return 60 where a valid UUID returns 7. This converts [finding 012](./012-ceiling-test-per-family.md)'s single observation from an anecdote into a deterministic property, and supplies the feature's first measured noise floor | `$4.8944` this session; the same `$35.0817` cumulative |
| [015](./015-verifier-vs-judge-not-run.md) | A frozen trace corpus silently rebased itself onto edited prompts and stayed that way for its entire existence: the freeze pinned the SHA-256 of all 22 corpus files and did not pin the questions the traces were answers to, so every downstream consumer joined each trace to whatever the task file said that day, and the join never failed. **The identifier in this document's own H1 is superseded**: [`plan.md` OD-31](../plan.md) of 2026-08-11 assigned `E8` to the Stage-D synthesis experiment, so every `E8` here reads `E19`, with nothing below rewritten and no figure affected. **Also overtaken 2026-08-03 by [finding 018](./018-verifier-false-alarm-attested-denominator.md)**, which restates ~~0 of 220~~ as 0 of 96 attested positives and 0 of 175 compared | `$0.0000` |
| [016](./016-provider-sdk-roundtrip.md) | Does the opaque-state round-trip survive each vendor's own SDK, with no abstraction layer in any path: chained tool use **4 / 4**, provider-opaque reasoning state emitted **4 / 4**, and round-trip survival decided by SHA-256 on receipt against SHA-256 in request shape. **Overtaken by later work, and this document carries no note saying so** — [finding 030](../../002-spec-aware-agent-runtime/findings/030-provider-state-chain-derived-not-measured.md) records that its arms have no persistence boundary at all, so nothing was ever at risk of being dropped and it is no evidence about chain length, and [finding 031](./031-provider-state-chain-measured.md) measured that question directly | **25,214 tokens**; `$0.001860` is the only dollar figure measured, xAI's server-side reading over three turns |
| [017](./017-evaluation-contemporaneity.md) | Three times, an evaluation in this corpus was scored against an artifact state postdating the defect it was meant to detect, each caught by accident in the course of doing something else. The survey is explicit that its own base rate is unknown and that three accidental discoveries leave the denominator unmeasured. **S1 is self-resolved 2026-08-03** — ~~Suspect; medium confidence~~ reads **RESOLVED**, checked and clean, and the check found a separate defect in the denominator. **Also carries OD-31's renumber banner** of 2026-08-11, which affects the body and not the title | `$0.0000` |
| [018](./018-verifier-false-alarm-attested-denominator.md) | The verifier's zero-false-alarm result survives restriction to the attested subcorpus, and the denominator it was published on counts **45 records the arm never compared**. The suspicion [finding 017](./017-evaluation-contemporaneity.md) ranked first was about the denominator rather than the numerator, and narrowing costs population — 93 positives compared against 175 pooled, over 33 distinct tasks against 40. **Carries OD-31's renumber banner** of 2026-08-11, which changes no figure, denominator, population or verdict | `$0.0000` |
| [031](./031-provider-state-chain-measured.md) | The twelve-arm probe ran, and **two of the four determinations are wrong in the direction that costs tokens rather than correctness**: xAI tolerates a chain with a hole as well as one with nothing, OpenAI tolerates both despite the only vendor quote carrying explicit error language, Google is the one provider that rejects a broken chain by name, and Anthropic's two 400s are an artifact of the treatment shape that the negative control caught. **Self-superseded on its filing rather than on its measurement**: §11.1 argued for feature 002 on a misquotation of the closure sentence, and is struck and **resolved 2026-08-05 by owner decision**, the document moved here with its number preserved and the argument kept as written because what the pass argued before the ruling is the record | **44,824 input and 3,326 output tokens** over the twelve cells; `$0.014082` is the only measured dollar figure, xAI's, and none is inferred for the other three providers |
