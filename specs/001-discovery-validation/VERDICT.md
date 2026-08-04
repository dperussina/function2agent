# Feature 001 — Discovery and Validation: closing verdict

**Date**: 2026-08-02
**Status**: **CLOSED.** The authority is [`plan.md`](./plan.md) **OD-07**, which concludes the
ceiling test on its per-family evidence, declines the authorized $120 full battery, and names the
production specification as the next artifact. *(Superseded on that last clause 2026-08-03 by
~~**OD-11**: the next artifact is the verifier-versus-LLM-judge experiment, and the production
specification is blocked behind it~~ **OD-11 and then, the same day, by OD-14, which retires OD-11's
blocking condition and restores the production specification as the next artifact** — declaring the
verifier's margin over an LLM judge UNMEASURED and deferring the measurement to production, recorded
there as a deliberate departure from this feature's prove-before-build discipline. Three further
owner decisions post-date this document and are
annotated where they bite — **OD-10** makes v1 read-only, **OD-08** closed O-01, and **OD-14**
unblocks the spec. Feature 001 is
not re-opened by any of them. **All three v1 capabilities now ship without measurement; that is
stated once at [§2](#all-three-v1-capabilities-ship-unmeasured) and is the fastest way to understand
what this feature leaves behind.**)*
**Total model spend**: ~~**≈ $24.82**~~ **≈ $35.17** against **$300** authorized by SC-003 — a program total across
findings, ~~**$24.82 ($24.73 + $0.09 + $0.0003)**~~ **$35.17 ($35.0817 + $0.09 + $0.0003)**, of which the ceiling test is the ~~**$24.73**~~ **$35.0817**
([finding 013](./findings/013-ceiling-test-budget-parity.md)), E5 the **$0.09**
([finding 003](./findings/003-runtime-provider-agnosticism.md)) and E6 the **$0.0003**
([finding 006](./findings/006-graph-loop-primitives.md)). *(Ceiling-test figure on the
**artifact-exact** basis; E5 and E6 are spend-incurred and are not re-derivable from committed rows,
so the total is mixed-basis and is quoted to the cent it can support. **Restated 2026-08-03 —
superseded, not wrong: $24.82 was correct for the four E7 sessions this document covered, and two
more ran afterwards.** The two bases and the six-cent gap between them are set out in §6. No single
finding reports the total, because it spans several — the components are the citable figures. E8 cost
**$0.00** and adds nothing: it was dry-run only, and every `spent_usd` in its committed results is
`0.0`.)*
**What this document is**: the adjudication of [`spec.md`](./spec.md) against what was measured. It
decides nothing new. Where it disagrees with a finding it says so and cites the correction.

---

## How to read this

This is not a success story and it is not a failure. Fifteen experiments were planned and nine were
reached. They produced an analysis layer measured good enough to extend, a runtime that clears
provider-agnosticism and fails two of four loop-safety primitives, contract extraction that clears
its gate on one reading and misses on the other, a reachability mechanism whose headline exactness
turned out to be a property of the test subject, and a ceiling test that found **no capability
advantage** for the thing the product was going to sell.

Several of those are negative. The point of the feature was to make them **known, cheaply, before
implementation** — and at ~~$24.82~~ **≈ $35.17** they are. A reader who thinks the product is a bad idea should be
able to use this document to argue that; that is the standard it is written to.

**Three findings carry in-place corrections and the corrected reading governs throughout.**
Finding 001's verb filter is retracted as a general rule by finding 004 (C-12). Finding 004's
statement that a running instance closes the computed-path gap is corrected by finding 010 (U-29).
Finding 010's "either `M1` alone" ablation claim and its account of what a missing schema costs are
both corrected by finding 011 (U-38, U-34). Numbers below are quoted from the correcting finding,
not the original.

---

## 1. The answer, in one page

**The question the feature existed to answer was whether a small, curated set of
application-specific tools makes an agent measurably better than a capable general agent with a
shell.** The answer is **no, on capability**, and the answer is **consistently yes, on cost**.

Across the three task families scored — 41 tasks, every outcome decided programmatically — the
curated tool surface **never won a family on success rate**
([finding 012](./findings/012-ceiling-test-per-family.md)):

| family | tasks | tool arm | shell baseline | verdict |
|---|---|---|---|---|
| `R1`+`R2` lookup | 27 | 27/27 | 26/27 | tie on one attempt each; tool arm **5.06× cheaper per attempted task** (5.25× per solved) |
| `R4` join-and-arithmetic | 10 | 9/10 | 10/10 | tie; tool arm ~~2.8×~~ **2.20× cheaper per solved** |
| `R4` per-record | 4 | 2/4 | **4/4** | **baseline wins**; tool arm **9.3× cheaper** on the two tasks a tool reaches — *cross-session, cross-fingerprint, n = 2; direction only, no magnitude (§8 item 5)* — and **3.84× more expensive per solved over the family as a whole** |

> **Correction, 2026-08-03 — the join ratio in the row above was 2.8× and is 2.20×, and the lookup
> and join figures were quoted adjacently on different denominators. No verdict in this document
> changes.** See [finding 009](./findings/009-ceiling-test.md) §Limb 1 and
> [finding 012](./findings/012-ceiling-test-per-family.md) §The headline for the recomputations.
>
> What was believed: that the join family's cost ratio was 2.8× per solved task, and that 5.0×,
> 2.8× and 9.3× were three comparable per-family figures.
>
> What is now known: finding 009's cost row divided post-fix cost totals by *pre-fix* solved counts
> of 8 and 7 while the success row above it was the post-fix 9 and 10. On the post-fix basis that
> governs throughout this record — $1.5444 over 9 solved against $3.7687 over 10 solved — the ratio
> is **$0.1716 against $0.3769, or 2.20×.** Consistently pre-fix it would be 2.73×. Separately,
> "5.0×" was per *attempted* task while "2.8× per solved" was per *solved*, so the two were never
> on one basis; both are now labelled. **Two qualifications travel with the join figure and are
> stated in finding 009**: removing `R4.001` moves it to **4.20×** — a 91% shift on one task of ten,
> on a task that consumed 94% of the raised token cap and would have failed under the prior one —
> and it ranges over **2.17×–2.73×** depending on which attempt on the three re-measured tasks is
> authoritative. **The magnitude is a bound on one budget configuration, not a rate.**
>
> **This figure has now been wrong in two successive directions.** `plan.md` OD-07 already
> corrected the range once, from "3–9×" up to "2.8×–9.3×", to stop quoting a lower bound the data
> did not support; the corrected lower bound is 2.2×, so the replacement was too generous as well.
> That history is recorded rather than smoothed over, because a figure that has moved twice on
> recomputation from unchanged artifacts is one to quote with its basis attached.

The lookup family was the region most favourable to the thesis and it was measured last. It tied.

**What replicated in every family is cost, and only cost — with one qualifier that has to travel
with it.** The finding's own wording is *wherever the tool arm succeeds at all*, and the per-record
family shows why: on the two tasks aggregation reaches, the tool arm solved both for **$0.057**
against the baseline's **$0.529**; across all four it spent **$2.03** to the baseline's **$1.06**,
because it burned **$1.97** failing on the two it could not reach. So the cost advantage is real,
large, and conditional on the question falling inside the tool surface — which is the same fact as
the liability in §7. The direction never reversed where the arm succeeded. That is the surviving
half of the product claim, and OD-07 states the revision plainly: ~~**cheaper and safer, not more
capable.**~~ **cheaper *within session*, and safer *only for hand-written surfaces*, not more
capable** — see the withdrawal note below.

**"Safer" rests on exactly one observation.** On the single lookup the baseline failed, it did not
fail to find the endpoint — it read the schema, found the correct endpoint and parameter, listed the
category collection so it held the correct identifiers, then queried by display name instead of slug
and the application **failed open**: 60 recipes returned where 7 were correct, with no error and no
empty result ([finding 012](./findings/012-ceiling-test-per-family.md) §Limb 2). A tool that
encodes the identifier discipline cannot fail that way. That names a mechanism where the original
thesis named a hypothesis — and the hypothesis, discoverability, was falsified in the same run,
because the baseline found the right endpoint on **all 27** lookups.

**Replication of that one observation was designed, priced at roughly $15, and deliberately
declined** in favour of proceeding (OD-07). It is n = 1. ~~The production specification must carry
"safer" as an assumption under validation and never as an established property.~~ That condition is
part of OD-07, not a caveat added here.

> **⚠️ WITHDRAWN AS STATED AND RE-SCOPED, 2026-08-03 — and this is a withdrawal rather than a
> narrowing, because the paragraph above names the wrong binding limit.**
>
> **What was believed:** that "safer" was a real but thinly-evidenced property of *a curated tool
> surface*, limited by **n = 1**, and that replication would settle it.
>
> **What is now known:** the fail-open immunity is a property of **a human declining to use the
> API's own filter**, not of the tool abstraction
> ([finding 014](./findings/014-ceiling-test-replication-and-noise-floor.md);
> [14](../../research/14-architecture-synthesis.md) **C-18**). The tool the baseline lost to was
> hand-written by someone who already knew the `categories` filter was untrustworthy. **A synthesized
> tool over the same operation would use the declared filter and inherit the defect**, and no
> mechanism to detect that has been built or designed.
>
> **The surviving claim, and it is narrower than "an assumption under validation."** *A hand-written
> surface can encode identifier discipline that a shell baseline missed once.* That may be stated,
> with n = 1 attached. **"Synthesis is safer" may not be stated at all** — it is not an unvalidated
> assumption, it is a claim this evidence points *against*. **The transfer question, not the sample
> size, is the binding limit**, and replicating the original observation would not touch it.

---

## 2. What the evidence supports, and what it does not

Stated before the adjudication tables, because everything below inherits it.

### All three v1 capabilities ship unmeasured

> **⚠️ ADDED 2026-08-03. This is the single most important thing to know about the product this
> feature leaves behind, and until now it was distributed across three registers where nobody would
> assemble it.**
>
> **v1 is a spec-aware runtime, a contract-derived verifier, and drift detection** (OD-09, D-21).
> **Not one of those three has a measured differentiating claim.** Stated together, once:
>
> | v1 capability | what is unmeasured | why it was never measured | where it is recorded |
> |---|---|---|---|
> | **Drift detection** | everything. No detection rate, no false-alarm rate, no latency to detect, on either of its two clocks | scheduled for [11](../../research/11-validation-plan.md) §7 **Phase 5** (H6); **that phase never ran**, and E13 never had a deployment-drift arm. It was promoted from fourth of four to half the product **by subtraction**, when the other half of the product was cut | O-04; `plan.md` OD-09 |
> | **The write gate's effect-classification precision** | the precision of the verb→tier mapping, against anything | never scheduled and never sampled. **This is why v1 is read-only**: because the classifier has never been scored, the interception point denies everything it cannot resolve as a read, and U-43 became the *exit condition* from read-only rather than a risk being carried | **D-22**, **U-43**; `plan.md` OD-10 |
> | **The verifier's margin over an LLM judge** | whether a general-purpose LLM judge catches the same failures. The verifier's *mechanism* is demonstrated — see below — but its *marginal* value is not | scheduled for §8 **Phase 2**, which never ran; then pre-registered as E8, built, self-tested and dry-run at **$0.00**, then **not executed** because its corpus cannot answer the question at any price this feature would pay | `plan.md` **OD-14**; forthcoming finding on E8's structural results |
>
> **One of the three is sharper than it looks and one is softer, and the difference matters.**
>
> - **Softer than "unmeasured" suggests: the verifier.** Its *mechanism* is demonstrated and was not
>   fitted. The postcondition arm detects **all 9 numeric value errors, including all 3 sub-1%
>   near-misses**, ~~with zero false alarms across 220 clean positives~~ **and raises zero false
>   alarms on the 96 oracle-positives whose own run manifest declares the battery under test, 93 of
>   which it actually compared** — *the offline full-corpus sweep, restricted to records that need no
>   cross-battery join to attest; the `FPR_c2 = 0/60` quoted elsewhere is the judge-scored sample and
>   a smaller population again, and the three must never be merged
>   ([14](../../research/14-architecture-synthesis.md) §3.2,
>   [finding 018](./findings/018-verifier-false-alarm-attested-denominator.md))* —
>   through a six-rung precision
>   ladder committed before any derivation was written that **contains no numeric constant**. What is
>   unmeasured is strictly the *comparison*: no judge call was ever billed, and every judge figure in
>   the committed artifacts is a stub. **The verifier works; nobody knows whether it is needed.**
>
>   > *(Restated 2026-08-03 on the attested denominator — **the result is stronger, not weaker, and
>   > the struck figure was not wrong.**
>   > [Finding 017](./findings/017-evaluation-contemporaneity.md)'s survey ranked this sentence its
>   > top suspect, because 220 of the 226 oracle-positives sit in a corpus where 143 of 246 records
>   > ran under a superseded battery: 124 of the 220 are cross-battery, and 84 of those are kept in
>   > scope only by a value test that
>   > [finding 015](./findings/015-verifier-vs-judge-not-run.md) shows is blind to wording
>   > drift. The census was re-run under that restriction and
>   > [finding 018](./findings/018-verifier-false-alarm-attested-denominator.md) reports it: **the
>   > narrow rate is also zero**, and the value-attested half is separately zero too, so the pooled
>   > figure was not carried by the unattestable records. **Two things did change.** The pooled 220
>   > counts 45 records the arm declined as `unverifiable` and therefore could never have raised an
>   > alarm on — 40 of them the entire unattested class — so **0 of 220 is not a rate**; the pooled
>   > rate is 0 of 175 compared. And the sentence had been pairing a detection numerator over the
>   > eligible population with a false-alarm denominator over the clean-positive population, which
>   > are different populations. On the attested population alone both sides share one denominator
>   > and read **2 of 2 false successes flagged, 0 false alarms on 96 positives**. The narrow figure
>   > buys its provenance with a wider interval — 0.0–3.8 pp against 0.0–1.7 pp — and with thinner
>   > coverage of `R4`, the family the drift touched.)*
> - **Sharper than "unmeasured" suggests: drift detection.** It has no mechanism demonstrated, no
>   harness, no pre-registration, and **no experiment scheduled**. The other two at least have a
>   named measurement and a reason it did not happen.
>
> **The consequence, stated plainly.** Feature 001 was run to prove things before building them, and
> it did that — it killed the capability half of its own thesis on pre-registered evidence. **What it
> is handing to the production specification is a product whose three components are individually
> unproven as differentiators.** The surviving *measured* results are about a hand-written surface's
> cost (§1), the analysis layer, contract extraction accuracy, and reachability — none of which is
> one of the three capabilities above. **OD-14 is the point at which this stopped being a schedule
> and became a decision**, and it is recorded there as a deliberate departure from the discipline.
>
> **This does not mean the product is unfounded.** It means every one of its three load-bearing
> claims is an assumption the production build must instrument and validate against real traffic,
> and that a reader who takes "measured good enough to extend" (the analysis layer) as licence for
> "the product is measured" has read this document backwards.

### Supported

- **A curated tool surface is materially cheaper wherever it succeeds at all.** **5.06× per
  attempted lookup task** (5.25× per solved), ~~2.8×~~ **2.20× per solved join**, 9.3× on the two
  per-record tasks aggregation reaches; replicated in every family measured, and not net-positive on
  a family where two of four questions fall outside the surface
  ([finding 012](./findings/012-ceiling-test-per-family.md)). *(Join figure and basis labels
  corrected 2026-08-03; see §1.)*
  ~~*The lookup figure is a cross-run pairing at a 6× budget asymmetry, disclosed in finding 012
  §The headline — neither arm came near binding.*~~
  **Caveat discharged 2026-08-03, and the figure is not revised**
  ([finding 013](./findings/013-ceiling-test-budget-parity.md)). The cross-run pairing and the
  realized 6× asymmetry both happened and remain on the record; **the threat they named is closed.**
  Budget's contribution to the ratio is a factor of **1.0000**, measured by a single-variable
  diagnostic that re-ran the tool arm's old surface at the new budget and moved its spend by zero
  tokens on two of three tasks and three tokens on the third — a budget that never binds cannot
  inflate the arm it does not bind. A paired re-run of the same 27 tasks in **one** run at **one**
  fingerprint returns **4.366×**, and the historical 5.059× sits inside that run's bootstrap
  interval of [3.384, 5.423], so the movement between them may not be reported as a difference
  ([finding 014](./findings/014-ceiling-test-replication-and-noise-floor.md) §The §9.3 adjudication).
  The amendment attribution also moves: the committed 3× ratio is **A1.1**, which **A3.1** preserved
  while doubling both arms, and A3.1 is what `config.json` carries.
  **What replaces the discharged caveat is a different one, on a different figure.** The
  **9.3×** is itself a cross-run, cross-fingerprint pairing at n = 2 on a post-hoc-selected subset,
  which had not been recorded anywhere; with a between-session shift now measured at up to 2.55× on
  byte-deterministic tasks, it establishes the direction and pins no magnitude. The defensible
  within-session range is **2.20×–4.366×** — restated and flagged for the owner at
  [`plan.md`](./plan.md#od-07--e7-concludes-without-a-full-battery-discovery-ends-the-claim-is-revised)
  OD-07 and derived in full at [14](../../research/14-architecture-synthesis.md) §3.1 (§8 item 5;
  U-46).
- **A synthesis-design constraint, and it is worth more than the headline:** *tools that return
  answers help; tools that return records do not.* One aggregation tool took `R4.014` from
  *exhausted 300,000 tokens and submitted nothing* to *answered in two turns* at **1/35th** the cost.
  The 20-tool surface that returns records lost the same family to a `jq` pipeline — and that
  20-tool surface is exactly what a naive one-tool-per-endpoint synthesis pass emits.
- **The analysis layer is good enough to extend, measured against machine-generated keys at $0.00.**
  Route recall **0.8961** (69 of 77) at precision **1.0000** inside the application source tree,
  symbol recall **0.9987**, route-to-handler linkage **69/69**
  ([finding 004](./findings/004-recall-against-authoritative-key.md)).
- **Contracts are derivable on this class of target.** Parameters exactly — **207 derived against
  207 expected, zero mismatches**; return types **53 agreements, zero disagreements**
  ([finding 007](./findings/007-contract-extraction.md)).
- **Reachability resolves by probing a running deployment, at path granularity.** Precision
  **1.0000** at path level on all seven targets, and unchanged when the schema is removed four
  different ways ([finding 011](./findings/011-reachability-without-schema.md)).
- **Bring-your-own credentials works and ~~the runtime~~ *the runtime that was probed* is genuinely
  provider-agnostic.** Five providers authenticate
  ([finding 002](./findings/002-provider-credentials.md)); ADK drove four to a
  passing tool call including a chained two-tool sequence
  ([finding 003](./findings/003-runtime-provider-agnosticism.md)). **Narrowed 2026-08-03 (OD-15,
  OD-16): v1 ships neither ADK nor `litellm`, so the provider-capability half of this transfers and
  the adapter-implementation half does not. Nothing has measured any vendor's own SDK doing it in
  our hands, and the same finding's result 7 counted the adapter this replaces referencing xAI's
  opaque reasoning field zero times.**

### Not supported

- **That application-specific tools make an agent more capable.** On 41 tasks across three families
  they did not; the baseline matched or beat the tool surface everywhere. OD-07: the specification
  **must not assert it**.
- **That "safer" is a property rather than a hypothesis.** One observation, replication declined
  (§1; U-41). **Hardened 2026-08-03: "safer" is withdrawn as stated and scoped to *hand-written*
  surfaces.** The immunity traces to a human declining to use the API's own filter, so **a
  synthesized tool inherits the defect** — "synthesis is safer" is not an open hypothesis, it is a
  claim the evidence points against (C-18; §1).
- **Any pooled E7 verdict.** There is not one, by design — OD-05 restructured the experiment to
  report per family precisely because an average across a 5.06×, a ~~2.8×~~ **2.20×** and a 9.3×
  "describes nothing."
- **That the fail-open mechanism generalises.** n = 1, one parameter, one application.
- **That the cost magnitudes are portable.** Direction replicated; magnitudes depend on a budget
  configuration amended three times.
- **That any of the E7 differences are outside noise.** Every figure is single-attempt. ~~There is no
  noise floor anywhere in the experiment~~ **There is a *within-session* noise floor and it is a
  lower bound on the *between-pass* one [11](../../research/11-validation-plan.md) §9.3 requires** —
  8.109% paired / 14.620% unpaired at n = 5, scaling to 2× bars of 6.98% / 12.58% on a 27-task pooled
  ratio ([finding 014](./findings/014-ceiling-test-replication-and-noise-floor.md)) — **and both ties
  were adjudicated before it existed**, so they are judgments that a 1-in-27 and a 1-in-10
  gap are noise rather than measurements of noise (U-42; U-46). *(Amended 2026-08-03: the flat
  absence was being quoted as though it were a measurement. The ties remain ties — both gaps sit
  inside even the lower bound — now for a stated reason rather than an assumed one.)*
- **That reachability is exact.** It is exact at *path* granularity. At operation granularity a
  single ordinary route that serves `GET` and gates `POST` behind a flag takes precision to
  **0.8000** — E14's apparent exactness was a property of `adk-python`, which contains no such route
  ([finding 011](./findings/011-reachability-without-schema.md)).
- **That configuration parsing has a shippable partial form.** The tuned parser predicts **0.0000**
  operations with its mechanisms disabled, and the naive first pass scored **worse than doing
  nothing** at all eight configurations, with **0.75** false inclusion over the null set (U-38).
- **Anything about a second language, a second model, a second application, or a real deployment
  topology.** One model against one application in E7; three Python routers and one real application
  in E14/E15; nothing reaches Express, Rails, Spring, Go, or gRPC.

### Unmeasured, and named as such

**Effect classification was never measured.** User Story 4's preliminary reading was scheduled into
this feature and did not happen; E12 sits in the deferred stage. The write half of the product
remains gated behind a number nobody has ([`plan.md`](./plan.md) E12; U-02 in the synthesis).

---

## 3. Success criteria, adjudicated

Every criterion in [`spec.md`](./spec.md) §Success Criteria, including the awkward ones.

| # | Criterion | Verdict | Evidence |
|---|---|---|---|
| SC-001 | Structure-recovery precision and recall reported at **zero** model spend | **MET** | Recall **0.8961**, precision **1.0000**, at **$0.00** ([finding 004](./findings/004-recall-against-authoritative-key.md)); [finding 001](./findings/001-structure-recovery.md) also $0.00 |
| SC-002 | A documented go/no-go on the core value proposition, **100%** of outcomes decided programmatically and **0%** by a model | **MET on the integrity half; the go/no-go delivered is not the one specified** | Integrity holds absolutely: every E7 outcome across findings 005, 008, 009 and 012 was decided by a programmatic check against the application's observable state, and no model judged any result. But the pre-registered instrument was a full battery, and the decision is OD-07 on three per-family probes over 41 tasks with no noise floor. It is documented, dated, and reasoned; it is not the measurement SC-002 anticipated |
| SC-003 | Completes within **one engineer-week and under $300** of model spend | **MET** | ~~**≈ $24.82**~~ **≈ $35.17** total (§6) *(restated 2026-08-03; two further E7 sessions post-date the original figure, and the verdict is unaffected — $35.17 clears $300 by the same margin in kind)*. Every finding is dated 2026-08-02, so elapsed time is inside the ceiling; effort-hours were not separately instrumented, so the time half is met on elapsed rather than on measured effort |
| SC-004 | **100%** of in-scope open questions closed with a citation or recorded open with a reason; none unmentioned | **MET** | The synthesis registers carry D-01…D-22, C-01…C-19, U-01…U-49 and O-01…O-06, each closed with a citation or annotated open *(ranges refreshed 2026-08-03; they grew after this verdict was written, and `research/14-architecture-synthesis.md` is the authority for their extent — the checker's `register-range` rule watches this sentence for drift. **The 2026-08-03 late refresh added C-17 and U-44**, both from the egress analysis behind `plan.md` OD-12: Principle IV's network-allowlist bullet is unmet by v1, and the egress guarantee is conditional on an unmeasured property of the target application. **C-17 closed later the same day** — `plan.md` **OD-12** decided, **OD-13** taking the constitution to v1.2.0 — **and U-44 stayed open**, which is the intended behaviour of these registers rather than an omission. **A further refresh the same day added C-18, U-45 and U-46** from [finding 013](./findings/013-ceiling-test-budget-parity.md) and [finding 014](./findings/014-ceiling-test-replication-and-noise-floor.md): the curated surface's safety argument pointing the opposite way from the synthesis argument, the lookup family voiding its own capability limb, and an unexplained between-session shift that is blocking for every cross-session comparison in the feature. **All three opened rather than closed**, and the third is the one that moved OD-07's range. **A fourth refresh, 2026-08-03, added C-19 and U-47** from [finding 015](./findings/015-verifier-vs-judge-not-run.md): a negative control that passed, correctly, on an arm whose only non-trivial output was fabricated, and a hash-pinned trace corpus that rebased onto edited prompts while every hash check kept passing. **Both opened; U-47 is blocking.** **A fifth refresh, 2026-08-03, added U-48** from `plan.md` **OD-15**: dropping ADK moves nine capabilities from adopt to build with no estimate in any committed artifact. **Opened and blocking**, and the same decision *closes* **U-12** for v1 and *re-opens* **U-03** in a new shape — the four-provider result was measured through a path v1 no longer ships, so SC-010 becomes a test rather than an inheritance. **A sixth refresh, 2026-08-03, added U-49** from [finding 018](./findings/018-verifier-false-alarm-attested-denominator.md): a false-alarm denominator that counts records the detector declined is inflated by cases that could never have contributed to its numerator, so `0 of 220` is a statement rather than a rate and the pooled rate is 0 of 175 compared. **Opened and non-blocking** — the figure it corrects survives the correction, since the attested rate is separately zero — and it is a reporting rule that becomes binding on the next false-alarm rate this project publishes. Read ~~C-01…C-18~~ and ~~U-01…U-46~~ **and ~~U-01…U-48~~** as **stale rather than wrong** — they were accurate when written and under-counted the moment the two entries landed, which is precisely the drift the `register-range` rule watches this sentence for, and the fourth time it has caught it)*. The one question that could have gone unmentioned — effect classification — is recorded open at U-02 and in [`plan.md`](./plan.md) E12 |
| SC-005 | An engineer who did not build the harness can reproduce any reported number from the committed configuration | **MISSED, and the miss is now structural rather than accidental. See the re-adjudication below** | Every experiment that ran now has a committed harness; two of them can still never satisfy the criterion, because their numbers are properties of artifacts that cannot be shared. No independent engineer attempted reproduction of anything |
| SC-006 | A false-success rate reported for every arm that ran | **MET** | Both arms on the lookup family, **0** for the tool arm and **1** for the baseline ([finding 012](./findings/012-ceiling-test-per-family.md)); **3 of 4** failures for the tool arm in calibration ([finding 008](./findings/008-ceiling-test-calibration.md)); the negative control's false success is what found the write-check defect ([finding 005](./findings/005-ceiling-test-harness.md)). Caveat: the three final per-family probes contained **no null tasks**, so false success there rests on answer-versus-oracle mismatch alone |
| SC-007 | Every claim traces to a run record, or is explicitly marked an inference | **MET** | Each finding carries its results directory; the build estimates in [finding 006](./findings/006-graph-loop-primitives.md) are marked engineering judgment rather than measurement; [finding 010](./findings/010-deployment-reachability.md) labels its post-hoc eighth configuration as post-hoc everywhere it appears |
| SC-008 | The record enumerates what the results do not support, including unrepresented populations | **MET** | Every finding carries a "what this does not license" section; §2 above consolidates them |
| SC-009 | Elapsed time from "results are in" to "the next spec can begin" is limited only by the decision | **MET** | Nothing the production spec needs is missing from the record. Three inputs are *open* rather than *absent* — the deployment model (O-01), the schema-free verb promise (U-39), and "safer" (U-41) — and each is written down with its resolution path (§7) |

### SC-005, re-adjudicated 2026-08-02

> **Correction, 2026-08-02 — the harness count in the row above was wrong when written and is
> wrong differently now. The verdict does not change. See
> [`harness/README.md`](./harness/README.md).**
>
> ~~Five harnesses are committed and re-runnable — `ceiling-test`, `contract-extraction`,
> `deployment-reachability`, `reachability-without-schema`, `recall-adk-fastapi`. But **E5 and
> E6's probe scripts are scratch artifacts in `/tmp/f2a-probe-runtime/`, explicitly not
> committed**, so the runtime numbers behind OD-01 and OD-02 are not reproducible from committed
> configuration.~~
>
> What was believed: that E5's and E6's probes were gone, and that five of the experiments had
> harnesses.
>
> What is now known, on both halves:
>
> **The denominator.** `plan.md` numbers experiments E1–E15, but **eight ever ran and produced a
> finding** — E1, E2, E4, E5, E6, E7, E14, E15. E3 was absorbed into E2 and never ran as its own
> experiment; E8–E13 never ran at all. SC-005 applies to those eight, plus finding 002's
> credential probe, which sits outside the ladder. Nine harness directories now exist, one per
> position:
>
> | position | harness | re-runnable | reported numbers reproducible |
> |---|---|---|---|
> | E1 | [`structure-recovery`](./harness/structure-recovery/) | method only — no target exists | **no, structurally** |
> | E2 | [`recall-adk-fastapi`](./harness/recall-adk-fastapi/) | yes | yes |
> | E4 | [`contract-extraction`](./harness/contract-extraction/) | yes | yes for the primary measurement; the TypeScript secondary column needs an index you supply |
> | E5 | [`runtime-provider-agnosticism`](./harness/runtime-provider-agnosticism/) | yes | most; **Gaps** names five claims whose scripts did not survive |
> | E6 | [`graph-loop-primitives`](./harness/graph-loop-primitives/) | yes | most; **Gaps** names what the surviving artifacts do not cover |
> | E7 | [`ceiling-test`](./harness/ceiling-test/) | yes | yes |
> | E14 | [`deployment-reachability`](./harness/deployment-reachability/) | yes | yes |
> | E15 | [`reachability-without-schema`](./harness/reachability-without-schema/) | yes | yes; adjudication byte-identical across two independent full runs |
> | (002) | [`provider-credentials`](./harness/provider-credentials/) | yes | **no, structurally** — the shape reproduces, the integers cannot |
>
> **E5 and E6 are committed.** Their scripts survived in `/tmp` and were recovered on 2026-08-02;
> they are the code that ran, not rewrites ([finding 006](./findings/006-graph-loop-primitives.md)
> §Reproduction, corrected). The runtime numbers behind OD-01 and OD-02 are now reproducible from
> committed configuration, subject to each harness's named **Gaps** — probes whose scripts did not
> survive, five-run repeats done by hand — which are enumerated rather than papered over.
>
> **The criterion still fails, and now for reasons no further work removes.** "*Any* reported
> number" is a universal claim, and two positions cannot meet it:
>
> - **Finding 002** reports which of one person's specific credentials authenticate and how many
>   models each enumerates. The harness reproduces the *shape* — that a canonically-named key can
>   be dead while a differently-named one works — against whatever dotenv tree you name. The
>   integers are properties of that tree at that moment and of vendor model catalogues that drift
>   weekly. They are unreproducible by construction.
> - **Finding 001** measured a private production monorepo's analysis index that is deliberately
>   not vendored. Its queries are now committed
>   ([`harness/structure-recovery/`](./harness/structure-recovery/)), so the method is
>   inspectable — and that is worth having, because the finding's two retracted claims were both
>   legible in the SQL long before E2 re-measured them. A stranger still has no target, so no
>   number in it is checkable.
>
> **Verdict unchanged: MISSED.** What changed is the character of the miss. As originally
> adjudicated it was an accident of housekeeping affecting two experiments; it is now a
> two-position structural limit, disclosed at each position, with the other seven met. That is
> materially closer and it is not a pass, and it must not be recorded as one.

**Nothing in `spec.md` turned out to be unanswerable in principle.** Two things went unanswered for
different reasons, and the distinction matters: SC-005's reproduction clause was **not executed**
(nobody tried, and two of the nine positions cannot be reproduced by anyone at all), while User
Story 4's measurement was **descoped by sequencing** — it needed the analyzer, the analyzer
arrived, and the reading was never taken before OD-07 closed the feature.

### Functional requirements not met

FRs are not adjudicated exhaustively here; these are the ones that failed or partly failed.

- **FR-012 — measure preliminary effect-classification precision, reporting critical
  misclassifications separately: UNMET.** Never measured. [finding 004](./findings/004-recall-against-authoritative-key.md)
  is explicit that verbs were used only to identify routes and that nothing about effect
  classification was established. **Consequence recorded 2026-08-03 (`plan.md` OD-10): because it was
  never measured, v1 ships read-only.** That is the pre-registered response to this exact miss —
  [11](../../research/11-validation-plan.md) §7 Phase 5 says *precision < 0.98 → writes do not ship*,
  and an unmeasured precision is not ≥ 0.98. The unmet requirement is carried as a shipped constraint
  rather than as an outstanding risk.
- **FR-016 — a re-runnable harness such that another engineer can reproduce any reported number:
  PARTLY MET.** ~~Five committed harnesses; E5 and E6 in `/tmp`.~~ **Corrected 2026-08-02:** one
  committed harness per experiment position that ran, and all but one of them re-runnable.
  *(Re-stated 2026-08-03 without a fixed count, because the count is a claim about a directory that
  lives in a different file from the directory: `harness/` is the authority for how many there are.)* Still partly met, for
  the two structural reasons in the SC-005 re-adjudication above — finding 001's target is a
  private monorepo and finding 002's integers are properties of one person's credentials.
- **FR-003 — null tasks in every battery: PARTLY MET.** Null tasks exist in the battery and were
  exercised in the smoke and calibration passes; the three final per-family probes ran without them.

### One spec assumption did not hold

`spec.md` assumes **"Both agent classes are measured, not one"**, on the reasoning that a comparison
measuring only one cannot resolve the class question. **Only Class B — operating *through* the
running application — was measured.** Class A's experiment is E10, deferred to the successor
feature. The class decision therefore leaves this feature undecided, which
[`plan.md`](./plan.md) records under open items and which P-01 in the synthesis still carries.

---

## 4. The four user stories

**User Story 1 — prove or disprove the core value proposition (P1). Answered, negatively on
capability and positively on cost, and concluded without the full battery.**
All five acceptance scenarios were satisfied by the runs that happened: outcomes programmatic
(scenario 1), success/cost/turns reported per arm with the baseline holding at least the same budget
and in practice a larger one — 900,000 tokens against 300,000 (scenario 2), false successes counted
separately (scenario 3), null tasks scored as false successes where they ran (scenario 4), and the
recorded outcome is a plainly stated result rather than a re-interpretation (scenario 5). **Scenario
5 is satisfied in its letter and is worth reading precisely**: results did *not* fall below the
pre-registered kill criterion, because that criterion is a conjunction and its cost limb fails ~~by a
wide margin~~ **decisively on lookups and narrowly on joins** — so a "no-go" was not owed and OD-07
does not manufacture one. *(Corrected 2026-08-03. "By a wide margin" was true of the lookup family,
where the ratio is **0.19** against a 0.5 threshold, and not true of joins, where the corrected
ratio is **0.455** — a 9% margin. In the per-record family the limb is **satisfied**, not failed.
The conjunction still does not fire, because the lookup family alone defeats it; the corrected
per-family table is in §5.)* What did fire is the
pivot row, and its named consequence is not adjudicated (§5).

**User Story 2 — establish how much structure can be recovered (P2). Answered, and it is the
feature's most solid result.**
Precision and recall against an authoritative artifact (scenario 1); non-obvious declaration forms
reported separately as four named causes over eight misses (scenario 2); per-repository coverage,
runtime and failure modes recorded (scenario 3); determinism verified for the non-model
measurements (scenario 4); and the answer key adjudicated by hand where it disagreed, with the
corrected key committed (scenario 5). Verdict: **extend `codegraph`** — 0.8961 falls in the
pre-registered 0.75–0.90 band, not the ≥ 0.90 band, so *extend with a named, sized gap-fill* rather
than *adopt* (D-14).

**User Story 3 — choose the substrate (P3). Answered, and it produced two disqualifications rather
than one recommendation.**
Multi-provider support probed rather than read: ADK drove four providers to passing tool calls
([finding 003](./findings/003-runtime-provider-agnosticism.md)), and the Claude Agent SDK was
disqualified as a default because every provider it enumerates is a hosting surface for Claude
models, which collides with bring-your-own-credentials as a hard requirement (OD-02). ADK cleared
the loop-safety gate — **two of four primitives missing against a threshold of three** — and the
owner declined the binary reading, keeping ADK's execution and rejecting all four of its safety
primitives (OD-01), at **2.5–3.5 weeks** of build work moved onto the critical path
([finding 006](./findings/006-graph-loop-primitives.md), $0.0003 against a $5 ceiling).
**Reversed in part 2026-08-03 by OD-15, and the story this paragraph tells changes at the end
rather than in the middle.** Both measurements stand. What changed is the substrate: the production
plan established that three of OD-01's four grounds have no subject or no evidence against a
one-agent, one-loop v1 — including that finding 003 result 7 counted the provider adapter
referencing xAI's opaque reasoning field **zero times under every counting rule**, which the
production spec's FR-037 and SC-010 require — and the owner dropped ADK entirely. **The 2.5–3.5
weeks was scoped to loop safety with the runtime adopted and now covers none of nine capabilities
that moved to build; no re-derived figure exists** ([14](../../research/14-architecture-synthesis.md)
**U-48**). `litellm` is dropped for its undeclared license (**OD-16**) and Linux is the only
supported platform (**OD-17**). Licensing
recorded: the SDK is MIT and the CLI it bundles is not, which is a redistribution constraint on
emitted packs (U-01, C-06).

**User Story 4 — measure whether operation effects can be classified safely (P4). Not delivered.**
No effect labels were produced and no precision was reported, so none of its four acceptance
scenarios was exercised. The write half of the product stays behind D-16's ≥ 0.98 precision gate
with no measurement against it. This is the clearest gap in the feature and it is a scheduling
outcome, not a measurement outcome.

---

## 5. The experiment ladder

Fifteen numbered experiments. **Nine positions were reached; six were deferred.** One finding —
[finding 002](./findings/002-provider-credentials.md), the live credential probe — sits outside the
ladder entirely, which is why there are twelve findings across nine positions.

*Eight of those nine positions ran as experiments.* E3 was answered by E2 and never ran as its own
experiment, so it produced no finding and has no harness. **Eight is the denominator SC-005 uses**;
nine is the count of ladder positions with an outcome.

| # | Experiment | Outcome |
|---|---|---|
| E1 | Route extraction precision | **Ran.** [finding 001](./findings/001-structure-recovery.md), $0.00. 1,161 `route` nodes, of which **74.6%** are real HTTP endpoints on a 96%-TypeScript monorepo. Its verb filter looked like the fix and **is retracted as a general rule** by E2 (C-12) |
| E2 | Route extraction recall | **Ran.** [finding 004](./findings/004-recall-against-authoritative-key.md), $0.00. Recall **0.8961**, precision **1.0000**, gate band cleared as *extend* |
| E3 | Handler linkage | **Not run as its own experiment; answered by E2.** Python linkage is exact, 69/69, because the framework resolver emits a direct route-to-handler edge. Finding 001's 58%-ambiguity figure is scoped to TypeScript (C-13) |
| E4 | Contract extraction | **Ran.** [finding 007](./findings/007-contract-extraction.md), $0.00. Literal **0.8696** clears ≥ 0.80; validated **0.7681** misses |
| E5 | Runtime provider agnosticism | **Ran.** [finding 003](./findings/003-runtime-provider-agnosticism.md), ≈ **$0.09** against a $2.00 ceiling |
| E6 | Graph-loop primitives | **Ran.** [finding 006](./findings/006-graph-loop-primitives.md), **$0.0003** against $5. Clears at two of four missing against a threshold of three |
| E7 | The ceiling test | **Ran, and concluded without its full battery.** Four sessions, four findings — [005](./findings/005-ceiling-test-harness.md), [008](./findings/008-ceiling-test-calibration.md), [009](./findings/009-ceiling-test.md), [012](./findings/012-ceiling-test-per-family.md) — **$24.73** against **$120** *(spend-actually-incurred basis; **$24.67** on committed artifacts alone — §6)*. The battery failed calibration at 96% and again at 93% against a table voiding any run above 85%; the OD-04 rebalance was halted by its own pre-declared stop condition; OD-05 restructured it to report per family; OD-07 concluded on that evidence |
| E8–E9 | Synthesis quality; promotion selection | **Not run.** Both require a throwaway generator that does not exist. Deferred to feature 002 |
| E10–E11 | Agent graph; memory graph | **Not run.** Both require generated output. Deferred to feature 002 — E10 is the missing half of the agent-class question |
| E12–E13 | Effect classification; drift detection | **Not run.** E12's preliminary reading was scheduled into this feature under User Story 4 and did not happen; E13 is deferred, and OD-06 has since opened a second drift mode it has no arm for |
| E14 | Deployment reachability | **Ran.** [finding 010](./findings/010-deployment-reachability.md), $0.00. Probe **1.0000/1.0000** on all eight configurations; configuration parsing 1.0000 on seven and **0.9538** on the post-hoc eighth, clearing its 0.95 gate by **less than one operation** |
| E15 | Reachability without a published schema | **Ran.** [finding 011](./findings/011-reachability-without-schema.md), $0.00. Seven targets. Four-state schema classification **7/7**; path-level precision **1.0000** everywhere; **the ≥ 0.95 operation-level gate missed on all three pre-registered arms**, at 0.8750 and 0.8000, and not because the schema was absent |

**Why E7 stopped where it did**, stated as OD-07 states it: the primary metric is pinned at its
ceiling — the tool arm sits at **1.00 on 27 of 41** measured tasks against a pre-registered
calibration band of **0.25–0.85** — and OD-04 refused to swap the primary metric to rescue it, so
the experiment as designed cannot answer its question and more n buys precision rather than
information. There was also no authorized battery left to spend on: the 61-task intermediate
composition is forbidden by OD-05, and the rebalance that would have replaced it was stopped by its
own rule.

### How the result reads against the pre-registered kill criteria

The gate authority is [`research/11-validation-plan.md`](../../research/11-validation-plan.md) §7,
Phase 0. Its rows do not all point the same way. This is recorded because FR-006 pre-registered them
and a closing document that quietly skips them would be doing the thing FR-006 exists to prevent.

- **The KILL row does not fire.** As written it is `TSR(A8) − TSR(A0) < 15 pp` **and** token ratio
  above 0.5 — and A0 was never run, so strictly the row cannot be evaluated. Read against the arm
  that did run, the conjunction fails anyway, and it fails on the cost limb. ~~The ratio is
  **0.11–0.36** in every family.~~ *(The row is written in tokens; cost per solved task is the
  recorded proxy, at identical model and pricing across arms.)*

  > **Correction, 2026-08-03 — the conclusion holds and the supporting claim was wrong twice.
  > The kill row still does not fire.**
  >
  > What was believed: that the tool-arm-to-shell-arm cost ratio "is 0.11–0.36 in every family,"
  > clearing the row's 0.5 threshold by a wide margin everywhere.
  >
  > What is now known, on both defects:
  >
  > **It is not every family, and in one the cost limb is *satisfied* rather than failed.** On the
  > per-record family the ratio is **3.84** on the v2 tool surface and **11.57** on v1 — the tool
  > arm is several times *more* expensive per solved task, far above 0.5. This document already says
  > as much elsewhere (§1, §2), so the two statements were in conflict. The **0.11** endpoint is
  > the reciprocal of the 9.3× figure, which is computed over a **post-hoc-selected two-task
  > subset** — the two per-record tasks aggregation happens to reach — and not over a family at all.
  >
  > **The join margin was overstated.** On the corrected post-fix pairing the join ratio is
  > **0.455**, a **9% margin** below the 0.5 threshold rather than a wide one. Across the eight
  > internally coherent attributions of the three re-measured tasks — both arms held to the same
  > attempt on each task — it runs from **0.366** to **0.460**, so the closest approach is an 8%
  > margin. Allowing the two arms to be attributed to *different* attempts reaches **0.513**, which
  > is above the threshold; that is not a defensible rule, because it is the same mixed-basis error
  > that produced the 2.8× in the first place, and it is recorded here only to show how little
  > separates this gate from firing on a bookkeeping choice.
  >
  > | family | tool-to-shell cost ratio per solved | clears the 0.5 threshold? |
  > |---|---|---|
  > | lookup | **0.19** | fails by a wide margin — this one genuinely is wide |
  > | join | **0.455** (0.366–0.460 across coherent attributions) | fails, by 9% at the governing pairing and 8% at the closest |
  > | per-record (v2) | **3.84** (11.57 on v1) | **satisfied** |
  >
  > **Scope of this correction.** The conclusion is unchanged: the row does not fire. It cannot,
  > because the lookup family fails the cost limb decisively at 0.19 and the row was never evaluated
  > per family in the first place. **What must be recorded plainly is the methodological fact: a
  > pre-registered gate was adjudicated on a figure that sits 8–9% from its threshold and moves
  > across a range that nearly reaches it on a bookkeeping choice.** That is not a comfortable
  > margin, and saying so is worth more than reporting the one that was quoted.
- **The PIVOT row fires, in all three families.** `TSR(A0b)` within 5 pp of `TSR(A8)` is satisfied
  on lookups (3.7 pp) and exceeded outright on the other two, where the baseline is ahead. Its
  named consequence is *"the product is a spec-aware runtime plus a verifier plus drift detection —
  real, but ~10× smaller than the current plan. Re-scope before proceeding."* **OD-07 revises the
  claim but does not adjudicate the re-scope**, and that is carried forward in §7 as an open item
  rather than treated as settled.
- **The mis-calibration row fires and its instruction was not followed.** `A8 > 85% TSR` says *fix
  the task set and re-run before drawing any conclusion*. OD-07 draws a conclusion instead, and
  gives its reasons above. The methodological consequence is worth stating precisely, because it
  cuts against over-reading the headline in the *other* direction: **on the two tie families both
  arms sit near the ceiling, so what was measured is "no difference detectable at this difficulty,"
  not "no difference exists."** OD-07's wording — the capability half is **not supported** — is the
  correct strength for that, and it should not be quoted as *refuted*. The per-record family is the
  exception, and it is the one place a capability *disadvantage* was measured rather than merely
  not shown: the tool arm scored 2/4, nowhere near a ceiling.
- **The arm the plan's own decision rule names was never run.** E7 compared A8 against **A0b** — a
  baseline with shell, `curl` and the target's OpenAPI schema — and never against A0, which has
  neither. [finding 005](./findings/005-ceiling-test-harness.md) flagged that substitution at the
  time and named its exact cost: this run **cannot distinguish "curated tools do not help" from
  "curated tools help, but access alone already captures most of it."** Discovery is closed and the
  arm will not be run, so that distinction stays unresolved permanently rather than pending.

---

## 6. Spend

| Experiment | Finding | Model spend | Against |
|---|---|---|---|
| E1 | 001 | $0.00 | — |
| (credential probe) | 002 | $0.00 | — |
| E5 | 003 | ≈ $0.09 | $2.00 |
| E2 | 004 | $0.00 | — |
| E6 | 006 | $0.0003 | $5.00 |
| E4 | 007 | $0.00 | — |
| E14 | 010 | $0.00 | — |
| E15 | 011 | $0.00 | — |
| E7 (four sessions) | 005, 008, 009, 012 | **$24.73** | **$120** |
| **Total** | | **≈ $24.82** | **$300** (SC-003) |

**Six of the twelve findings cost nothing at all, and two more cost under a dime.** Everything
outside the ceiling test came to **$0.09**; E7 is **99.6%** of the bill. The $120 authorized for the
full battery was never spent and OD-07 declines it.

> **⚠️ THE TOTAL ROW IS SUPERSEDED, 2026-08-03 — and the label on it was the recurring error, not the
> arithmetic. Read the two rows below as answering two different questions.**
>
> | question | figure | basis |
> |---|---:|---|
> | **what did the ceiling test (E7) cost?** | **$35.0817** | artifact-exact, six sessions, fourteen run directories |
> | **what did the whole feature cost?** | **≈ $35.17** | E7 artifact-exact **+** E5 and E6 spend-incurred |
>
> **$35.0817 is E7's total, not the feature's.** It is exactly what the committed E7 rows sum to —
> **$34.227372** across 301 per-attempt rows plus **$0.854300** of committed negative-control spend —
> with no remainder to apportion. Recompute it rather than trusting this table; the harness README
> carries the same snippet:
>
> ```bash
> cd specs/001-discovery-validation/harness/ceiling-test
> python3 - <<'PY'
> import glob, json
> rows = sum(json.loads(l)["cost_usd"] for f in glob.glob("results/*/results.jsonl") for l in open(f))
> neg  = sum(json.load(open(f))["spent_usd"] for f in glob.glob("results/negative-control/*.json"))
> print(f"per-attempt {rows:.6f} + negative-control {neg:.6f} = {rows + neg:.6f}")
> PY
> ```
>
> It prints `per-attempt 34.227372 + negative-control 0.854300 = 35.081672`.
>
> **The whole-feature figure adds the only two other experiments that cost anything:** E5 at
> **≈ $0.09** ([finding 003](./findings/003-runtime-provider-agnosticism.md)) and E6 at **$0.0003**
> ([finding 006](./findings/006-graph-loop-primitives.md)). $35.081672 + $0.09 + $0.0003 =
> **$35.171972 → ≈ $35.17**. Every other experiment in the table above is $0.00, and **E8 is $0.00
> too** — it was dry-run only and every `spent_usd` in `harness/verifier-vs-judge/results/*` is `0.0`.
>
> **The total is mixed-basis and says so.** E5's and E6's figures were read from provider usage after
> the fact and are *not* re-derivable from committed rows — both harness READMEs say so in their own
> self-audits — so **≈ $35.17 cannot be tightened past two decimal places** and the `≈` is load-bearing.
> **The spend-incurred column is deliberately not extended to a whole-feature figure**, here or in
> the harness README: findings 013 and 014 report artifact-exact figures only, so carrying that
> column forward would mean inventing a basis neither finding used. The six-cent gap between the two
> bases is unchanged in character and is still the uncommitted session-1 negative-control spend.
>
> **Why this keeps going wrong is worth naming, because it has now gone wrong three times and never
> once through arithmetic.** Each failure was a **basis** confusion: *artifact-exact vs.
> spend-incurred* (the six-cent gap, §8 item 2), *per-attempted vs. per-solved* (the 5.0× / 2.8×
> adjacency, §1), and now *component vs. total* — quoting E7's $35.0817 where the feature total
> belongs, or the feature's $24.82 where E7's belongs. **A spend figure in this corpus is not usable
> without its basis and its scope attached; both, not either.**
>
> **What does not change.** SC-003 is still MET, the $120 full-battery authorisation is still
> unspent, and no verdict in this document turns on the difference.

*Basis, added 2026-08-03: the E7 row is on the **spend-actually-incurred** basis, which is the sum of
the per-session figures each finding reports. On the **artifact-verifiable** basis — summing only the
committed per-attempt and negative-control rows in `results/` — E7 is ~~**$24.67**~~ **$24.67 across
those four sessions**, and the roughly six-cent difference carries through to the total unchanged in
character. Both bases are quoted below; neither is an error.*

> **⚠️ SUPERSEDED AS A TOTAL, 2026-08-03 — not corrected. E7 ran two more sessions after this
> document was written, and the table above stops at four.**
>
> **The artifact-exact E7 total is now $35.0817**, decomposed in
> [finding 013](./findings/013-ceiling-test-budget-parity.md): **$34.2274** from the committed
> per-attempt rows across all fourteen runs plus **$0.8543** of committed negative-control spend, the
> latter recorded only to four decimal places. Sessions five and six are
> [finding 013](./findings/013-ceiling-test-budget-parity.md) at **$5.5168** and
> [finding 014](./findings/014-ceiling-test-replication-and-noise-floor.md) at **$4.8944**, each
> against a $6.00 session authorisation; finding 014 deliberately left **$1.1056** unspent rather
> than buy five more copies of a fixed point, and that decision is recorded there so it is auditable
> rather than looking like an underrun.
>
> | basis | four sessions, as at OD-07 | six sessions, current |
> |---|---:|---:|
> | artifact-verifiable | $24.67 | **$35.0817** |
> | spend-actually-incurred | $24.73 | not re-tallied — sessions 5 and 6 report artifact-exact only |
>
> **Why superseded and not wrong.** Every figure in the table above was accurate for the four
> sessions it covers, and the E7 row still is; what expired is its use as *the* ceiling-test total.
> **Nothing about SC-003, the $120 full-battery authorisation, or any verdict in this document
> changes** — the battery still has not run and its $120 is still unspent. The
> spend-actually-incurred column is left un-extended on purpose: findings 013 and 014 report
> artifact-exact figures only, so extending it would mean inventing a basis neither finding used.

*Arithmetic note, recorded because it is the kind of thing this feature was strict about elsewhere:*
~~*[finding 009](./findings/009-ceiling-test.md) reports "$18.09 across three sessions" where the
component figures sum to $18.15 ($7.59 + $10.56). The four-session total of $24.73 is consistent
with $18.15, so the $18.09 is a six-cent transcription error in the intermediate figure and the
total is right.*~~

> **Correction, 2026-08-03 — this note ran backwards. It called the artifact-exact figure an error
> and blessed the one that is six cents high. No verdict and no budget conclusion changes.**
>
> What was believed: that $18.09 was a six-cent transcription error, and that $18.15 and the
> four-session $24.73 were the correct figures because they are mutually consistent.
>
> What is now known, recomputed from the committed rows in
> [`harness/ceiling-test/results/`](./harness/ceiling-test/results/):
>
> | figure | basis | value |
> |---|---|---|
> | sessions 1–3 | sum of committed per-attempt costs plus committed negative-control rows | **$18.0912 → $18.09** |
> | all four sessions | the same | **$24.6705 → $24.67** |
> | sessions 1–3, as reported | sum of the rounded per-session figures ($7.59 + $10.56) | $18.15 |
> | all four sessions, as reported | the same, plus $6.58 | $24.73 |
>
> **$18.09 is artifact-exact and finding 009's provenance statement — "as tallied from the recorded
> per-attempt costs in `results/`" — is accurate.** The committed-artifact grand total is **$24.67**,
> so **$24.73 is the figure that is about six cents high**, not $18.09.
>
> **The two reconcile, and that is why neither is an error.** $24.73 and $18.15 are the sums of the
> rounded per-session figures, and the session-1 figure of $7.59 runs about eight cents above the
> **$7.51** the committed artifacts hold. That excess is consistent with roughly **$0.05 of genuine
> session-1 negative-control spend that was never committed to `results/`**, plus stacked rounding
> across three session figures. So these are **two accounting bases** — an **artifact-verifiable
> floor** at $18.09 / $24.67, and a **spend-actually-incurred** figure at $18.15 / $24.73 — and each
> should be quoted with its basis rather than one being deleted in favour of the other. About
> $0.008 of the gap is residual rounding that does not resolve to a named row.
>
> **Scope of this correction.** The note exists to model arithmetic discipline, and it was
> discharging that duty in the wrong direction. Nothing about SC-003, the $120 authorisation, or
> any verdict turns on a six-cent difference. See
> [finding 009](./findings/009-ceiling-test.md)'s spend correction and
> [finding 008](./findings/008-ceiling-test-calibration.md)'s basis note.

---

## 7. What carries into the production specification

### Decided, and not to be relitigated without new evidence

The full register is [`research/14-architecture-synthesis.md`](../../research/14-architecture-synthesis.md)
§3.1. The load-bearing ones:

- **D-01** — synthesized tools call the target over its existing external interface, never
  in-process.
- **D-05 / OD-01 / OD-02** — ~~live inside ADK's graph execution, lifecycle, HTTP/SSE serving and
  provider abstraction~~; rely on **none** of its four loop-safety primitives; ~~build the
  coding-node executor on ADK~~ with the Claude SDK as an opt-in Anthropic path. ~~**2.5–3.5
  weeks** on the critical path.~~ **Partially reversed 2026-08-03 by OD-15: v1 runs on no agent
  framework. The seam D-05 draws — execution versus safety — is unchanged and is what OD-15 acted
  on; the execution side is now empty, nine capabilities move to build, and the 2.5–3.5 weeks
  covers none of them with no re-derived figure anywhere (U-48). OD-16 drops `litellm` for its
  undeclared license; OD-17 makes Linux the only supported platform.**
- **D-06** — MCP is the export adapter and headline artifact, never the internal calling convention.
- **D-07** — two physically separate credential planes; no secret in model context.
- **D-14** — extend `codegraph`, with a named gap-fill whose largest item is a **type resolver, not
  a better parser**.
- **D-17** — provenance, independent validation, provisional marking, and deployment identity on
  every derived field. **Decided but not yet enforceable**: OD-03 drafted the constitution sentence
  that would give it force and deferred it pending E7. **E7 has now returned and did not retire the
  thesis, so the deferral's condition is discharged and applying that amendment is an owner action
  the production spec should carry.**
- **D-18 / OD-06** — reachability resolves by probing a named deployment, in a stage **above**
  analysis rather than inside it; exact at path granularity; the `Allow` header is forbidden.
- **D-19 (new)** — the claim is ~~**cheaper and safer, not more capable**~~ **cheaper *within
  session* (2.20×–4.366×) and safer *only for hand-written surfaces*, not more capable**, quoted per
  family and never pooled. ~~with "safer" carried as an assumption under validation.~~ *(Narrowed on
  cost and withdrawn-then-re-scoped on safety, 2026-08-03 — see §1. The 9.3× is demoted from a range
  endpoint; "synthesis is safer" may not be asserted at all, because a synthesized tool inherits the
  fail-open defect the hand-written one avoided by human judgement — C-18.)*

### Blocking, and each is an input the spec must resolve rather than inherit

- **U-41 — "safer" is n = 1 and its replication was declined.** Blocking for any customer-facing
  safety claim. Two cheaper prerequisites before the $15 probe: count how often fail-open parameters
  even occur, and decide whether the mitigation is the tool surface at all rather than a
  contract-derived validation (D-09) or a `validated: false` marking (D-17) — if it is the latter,
  "safer" is a property of the verification layer and the claim moves rather than strengthens.
- **U-39 — method-level reachability may be schema-only.** A schema-free catalogue either carries
  paths without verbs, carries verbs it cannot verify, or requires an introspectable target. That is
  a promise to a customer, not a measurement, and no further measuring resolves it.
- **U-30 — no layer of the stack enforces a spend ceiling that survives a crash and resume.** ADK's
  resets; the providers' are unverified (U-06). Both candidate layers have now been found not to
  supply one. **Worse as of 2026-08-03 (OD-15): ADK's resettable ceiling is not merely inadequate,
  it is absent, so nothing occupies the interim position until our own budget channel exists.**
- **U-02 — effect-classification precision is entirely unmeasured**, ~~and D-16 gates every write
  behind ≥ 0.98 of it.~~ **Updated 2026-08-03 (`plan.md` OD-10):** the quantity moved from a static
  per-tool label to a per-call tier and is recorded as **U-43**; D-16 is **dormant** rather than
  gating, because **v1 ships no writes at all** until that precision is measured. It remains blocking
  — as the *exit condition* from read-only rather than as a risk being carried — and it narrowed to
  one error shape, a side-effecting endpoint reached by a safe method.
- ~~**O-01 — the deployment model.** Commercial, not experimental. Multi-tenancy, the credential
  architecture and the iframe tier all fall out of it.~~ ✅ **RESOLVED 2026-08-02 by `plan.md` OD-08
  (D-20), after this section was written:** ship self-hosted, design so a hosted tier stays reachable
  without a rewrite. The three consequences landed in three different places — multi-tenancy deferred
  rather than absent, the credential architecture half-discharged, the iframe tier deferred with the
  hosted model.
- ~~**NEW, and it is the one the spec cannot start without — `plan.md` OD-11, 2026-08-03. The
  production specification is blocked on the verifier-versus-LLM-judge experiment.**~~
  **BLOCKING CONDITION RETIRED 2026-08-03 by `plan.md` OD-14 — superseded, not answered.** All three
  surviving v1 capabilities are unmeasured; the verifier holds headline status on
  [finding 007](./findings/007-contract-extraction.md)'s *extraction accuracy* rather than on the
  *marginal detection over a judge* that Phase 2 was going to measure and never ran. **That remains
  true. What changed is the disposition:** the experiment was built and dry-run at $0.00, its corpus
  cannot answer the question — 2 discriminative traces, three pre-registered riders capping the
  verdict independently, four of seven families lost to the eligibility rule — and the owner declared
  the margin **UNMEASURED**, unblocked the spec, and deferred the measurement to production traffic.
  **The next artifact named at the top of this document is a specification again.** The obligation
  travels with it: instrument the verifier and a shadow judge in production, gate unchanged. See
  [§2](#all-three-v1-capabilities-ship-unmeasured) for all three capabilities stated together, and
  note that the harness's **§4.1 human adjudication pass was never performed and is open
  independently**.
- **The PIVOT consequence, unadjudicated.** The pre-registered rule that fired names a re-scope to a
  roughly 10× smaller product (§5). OD-07 revises the claim without deciding the scope, so the spec
  inherits that decision explicitly rather than by default.

### Architecture requirements that emerged rather than being designed

These are the ones no one specified and the measurements produced.

1. **A general fallback path (OD-07).** A tool surface is a bet that the question falls inside it,
   and losing that bet costs everything — three of four per-record failures were budget exhaustion
   rather than wrong answers, against a shell arm that exhausted nothing in 31 scored attempts. So
   the emitted stack cannot be synthesized tools alone. *(Two scope notes on that comparison, neither
   of which changes it: the 31 counts the 27 lookups and 4 per-record attempts and omits the 10
   joins, where the shell arm also exhausted nothing, so it understates; and the shell arm did
   exhaust its budget ~~once~~ **twice** outside that window — on the same **null** task `N.001` in
   **both** smoke passes, at the pre-tripling 225,000-token budget, at 238,673 and 234,459 tokens
   respectively, [finding 005](./findings/005-ceiling-test-harness.md). *(Corrected 2026-08-03: this
   read "once"; it happened in both smoke runs of the same task.)* The claim is exact as OD-07 scopes
   it and should not be quoted as "the shell arm never exhausts.")* **This collides directly with a stated
   design position**: a general fallback pushes toward fusing the two agent classes, which
   [`research/07-product-vision.md`](../../research/07-product-vision.md) §3.4 identifies as
   assembling the lethal trifecta — private data, untrusted content, egress — **by construction**.
   OD-07 assigns the reconciliation to the specification and requires it to be made against
   constitution Principle IV rather than inherited silently. Recorded as **C-15**, which enumerates
   the three shapes available; the one thing not available is the status quo, because the current
   design has no fallback and the measured cost of that is a run that spends everything and returns
   nothing. *(Extended 2026-08-03: the reconciliation OD-07 assigns to the specification now has one
   named, cheap component and one unresolved question. **The component** — default-deny network
   egress pinned to the target — is Principle IV's *first* bullet, is unmet by v1, and had never been
   cited in any Principle IV argument here; it cuts the direct exfiltration channel without costing
   v1 any capability it claims, and it does **not** cut the trifecta's egress leg, because the target
   application's own URL-fetching endpoints make it a confused deputy
   ([`research/14-architecture-synthesis.md`](../../research/14-architecture-synthesis.md) **C-17**,
   **U-44**; [`plan.md`](./plan.md) **OD-12**, ~~proposed and not decided~~ **decided 2026-08-03**).
   ~~**The unresolved question** is whether the general fallback path executes at all under OD-10:
   §2.6's ladder never resolves a shell command to read-only, so with `UNKNOWN → deny` it denies the
   very fallback this item requires.~~ **✅ ANSWERED 2026-08-03 by OD-12, and answered by dissolving
   the question rather than by picking one of its two readings: both controls move into a single
   mandatory egress proxy that sees a shell-originated request and a runtime-originated one
   identically, so nothing classifies a shell command for effect and **v1's general fallback path
   executes**. C-17 is closed. The component above is now decided rather than merely named, and its
   *"does not cut the egress leg"* clause is unchanged — U-44 is untouched.)*
2. **Two artifacts on two clocks (OD-06).** Analysis emits a source-derived candidate set;
   a separate reachability annotation says what a named deployment serves. This was forced by a
   constitution constraint and it turned out to buy something: codebase drift and deployment drift
   become **separately** detectable, which a fused artifact cannot do.
3. **Provenance as a safety mechanism, not metadata (D-17, U-40).** Three independent measurements
   produced confidently-wrong derived fields by three unrelated mechanisms. The fourth instance is
   the one that generalises furthest: a safety property held by the static extractor's failing
   closed would be **silently removed by an unrelated recall improvement** in that extractor, so the
   coupling has to be written down as an interface obligation before either component is touched.
4. **The reachability precondition cannot ship classified read-only on probe design alone.** Handler
   invocation is eliminable and was eliminated — 13 invocations to **0** across seven targets by
   probing with a verb no route declares — but middleware runs before routing regardless of method,
   so read-only classification becomes a property of a tool **and a deployment**, which is a kind of
   obligation Principle IV does not currently express.

---

## 8. Verification notes

Every quantitative claim above was checked against its source. Three discrepancies were found in the
record while doing so. None changes a verdict; all three are recorded because a closing document
that quietly normalises its inputs is worth less than one that says where they disagree.

**A second pass on 2026-08-03 re-derived every cost figure from the committed artifacts and found
that two of the three notes below were themselves wrong.** Both are corrected in place. That the
verification section needed verifying is the most useful thing in it, and the standing lesson is
recorded in item 4.

1. ~~**[finding 012](./findings/012-ceiling-test-per-family.md)'s headline says the tool surface is
   cheaper "by 5× to 9×", and its own table reports 2.8× for the join family** — outside the stated
   range. Its closing section says 3–9×, and OD-07 quotes 3–9×. **Use the per-family figures: 5.0×,
   2.8×, 9.3×.**~~ **Corrected 2026-08-03.** The discrepancy was real and the resolution named the
   wrong figures. The join ratio itself was wrong: 2.8× divided a post-fix cost total by a pre-fix
   solved count, and on the post-fix basis it is **2.20×**. The per-family figures to use are
   **5.06× per attempted lookup task** (5.25× per solved), **2.20× per solved join**, and 9.3× on the
   two aggregable per-record tasks — with the lookup and join figures now labelled, because they were
   never on the same denominator. See §1. **Narrowed again 2026-08-03 (item 5): the defensible
   within-session range is 2.20×–4.366×, and the 9.3× is no longer a range endpoint.**
2. ~~**[finding 009](./findings/009-ceiling-test.md) reports "$18.09 across three sessions" where its
   components sum to $18.15** ($7.59 + $10.56). The four-session total of $24.73 is consistent with
   $18.15, so the intermediate figure carries a six-cent error and the total is right.~~
   **Corrected 2026-08-03: this ran backwards.** $18.09 is the artifact-exact sum of committed
   per-attempt and negative-control rows for sessions 1–3 ($18.0912), and the committed-artifact
   grand total is **$24.67**, so $24.73 is the figure that is about six cents high. The two are
   different accounting bases and neither is an error (§6). **Extended 2026-08-03: $24.67 is
   superseded as a total and remains exact as a four-session figure.** Two further E7 sessions ran
   after this document was written and the artifact-exact E7 total is now **$35.0817** —
   [finding 013](./findings/013-ceiling-test-budget-parity.md) holds the decomposition, and §6
   carries both bases side by side.
3. **OD-07's "never exhausted its budget in 31 scored attempts" is exact as scoped and easy to
   over-read** — it omits 10 join attempts where the shell arm also exhausted nothing, and there are
   **two** exhaustions outside the window, on the same null task in **both** smoke passes at the
   earlier budget (§7). *(Corrected 2026-08-03 from "one exhaustion".)*
4. **The standing lesson, and it applies to this section as much as to the record it checks.**
   Every figure corrected on 2026-08-03 was recomputable from artifacts that had not changed since
   the day they were written, and two of them had already survived one verification pass that
   asserted completeness. **A cost figure is not verified by being consistent with another quoted
   cost figure; it is verified by being re-derived from the committed rows, with its basis named.**
   Mutual consistency is what made $18.15 look right, and a mixed-basis division is what made 2.8×
   look right.
5. **A third pass on 2026-08-03, prompted by [finding 014](./findings/014-ceiling-test-replication-and-noise-floor.md)'s
   between-session shift, traced every cost figure to the *runs* its two arms came from — and found
   one defect the two earlier passes had not, because neither had looked at provenance.**
   **The per-record 9.3× is a cross-run, cross-fingerprint pairing** — tool arm from
   `20260802T173226-reprobe-perrecord-v2` (`f9abf1d35e94e32e`), shell arm from
   `20260802T164929-bias-probe-perrecord` (`3c10a64b0ffe7749`) — which the harness's own rule
   forbids pooling. [14](../../research/14-architecture-synthesis.md) U-42 records exactly this
   defect for the *lookup* comparison and does not record it here, and no document in the corpus
   did. At n = 2 on a post-hoc-selected subset, with a between-session component now measured at up
   to 2.55× on tasks that are byte-deterministic within a session, **the 9.3× pins no magnitude**;
   the range is restated accordingly and flagged for the owner at
   [`plan.md`](./plan.md#od-07--e7-concludes-without-a-full-battery-discovery-ends-the-claim-is-revised)
   OD-07 and [14](../../research/14-architecture-synthesis.md) §3.1. *(The join figure pools two
   fingerprints as well, but symmetrically — every task's arm-to-arm contrast sits inside one run —
   so it carries no such exposure. The difference between those two situations is the whole finding.)*
   **The standing lesson in item 4 extends: a cost figure is not verified by being re-derived from
   the committed rows either, unless the derivation also asks which runs the two arms came from.**
6. **A fourth pass on 2026-08-03 found the spend label wrong for a third time, and again through a
   basis confusion rather than arithmetic — this one *component versus total*.** The header and the
   §6 total row carried **≈ $24.82** as the feature total while the boxed note in §6 carried
   **$35.0817** as the E7 total; a reader reconciling them would take $35.0817 for the feature and be
   short the two non-E7 experiments, or take $24.82 and be short two E7 sessions. **Both figures were
   correct and both labels were being read past their scope.** Restated: E7 is **$35.0817**
   artifact-exact, the feature is **≈ $35.17**, and §6 now shows the recomputation rather than
   asserting either. **The three failures form a set worth naming together — artifact-exact vs.
   spend-incurred (item 2), per-attempted vs. per-solved (item 1), component vs. total (this one) —
   and none of the three was an arithmetic slip.** The standing lesson extends once more: *a figure
   in this corpus needs its basis **and** its scope attached, and a derivation that supplies only one
   of them is not a verification.*

---

## 9. What this document does not license

- **Quoting any E7 number as a rate.** Single attempt, ~~no noise floor~~ **a within-session noise
  floor that is a lower bound on the one [11](../../research/11-validation-plan.md) §9.3 asks for,
  and which post-dates every tie in this document** (§2), one model, one application,
  and the same person authored both the tasks and the tools.
- **Quoting the cost advantage as a magnitude.** "A large advantage that replicated in every family"
  is supported; "5×" as a product claim is not, because the budget configuration behind it was
  amended three times.
- **Treating "not supported" as "refuted."** Two of the three families were measured with both arms
  near the ceiling (§5).
- **Generalising the analysis numbers past one Python framework and one TypeScript monorepo**, or
  the reachability numbers past three Python routers, one real application, and a single local
  process with no gateway, proxy or replica (U-36).
- **Reading this feature as having tested the product.** It tested a ceiling with hand-written
  tools. Nothing here measures generated output, because the generator does not exist — which was
  the point, and is what feature 002 is for.

---

*Feature 001 closes here. Its findings are immutable; corrections to them live in the registers and
in this document. The next artifact is the production specification.*
