# Feature Specification: Spec-Aware Agent Runtime

**Feature Branch**: `002-spec-aware-agent-runtime`

**Created**: 2026-08-03

**Status**: Draft

**Input**: User description: "Ship v1 of function2agent: a spec-aware agent runtime that operates a customer's running application through the application's own published specification, a contract-derived verifier that recomputes reported results against an independent source, and drift detection that fails closed when either the analysed source or the deployed surface moves. v1 is read-only, self-hosted first, provider-agnostic on bring-your-own credentials, and confines all outbound traffic to a single enforcement point outside the agent's control. All three capabilities ship with their differentiating claims unmeasured, so instrumenting and reporting those measurements against real traffic is part of the deliverable."

## Context

This is the production specification. It follows feature 001, which planned fifteen numbered
experiments, reached nine ladder positions, ran eight of them, and closed with a verdict
([`VERDICT.md`](../001-discovery-validation/VERDICT.md)). Its binding scope decisions are the owner
decision log OD-01 through ~~OD-14~~ ~~OD-17~~ ~~OD-20~~ **OD-21** in [`plan.md`](../001-discovery-validation/plan.md)
*(extended 2026-08-03: **OD-15** drops ADK for v1 and partially reverses OD-01, **OD-16** removes
`litellm` from the shipped product, and **OD-17** makes Linux the only supported platform. None of
the three changes a requirement in this document; all three change what the plan builds against)*.
**Extended again 2026-08-03 with OD-18, OD-19 and OD-20, and these three are not inherited scope —
they are this document's own clarify-session decisions, finally written down.** They were taken on
2026-08-03, applied to the requirement text below on the day, and never recorded in the decision log,
so until now FR-002, FR-044, FR-025, FR-045, FR-029 and FR-046 rested on an owner authority that
appeared nowhere. No requirement changes; each now names the decision that authorises it. **OD-18 is
the consequential one** — a published machine-readable specification is an admission criterion, which
narrows what v1 accepts. **Extended once more the same day with OD-21, which is the fourth and last
answer of that same clarify session and had the same defect**: FR-047, the narrowings it makes at
FR-001, FR-030 and FR-031, and SC-021 rested on an authority that appeared nowhere. It is recorded
separately from its three siblings because recording it needed the owner rather than a propagation
pass, and the note under OD-20 that named the gap is struck rather than deleted.

**What the product is.** The operator points the system at a codebase and at a *named running
deployment* of that codebase. The system derives contracts from the source, establishes what the
deployment actually serves, and then runs an agent that operates the application through the
application's own published operations — verifying what the agent reported against the code's own
contracts, and failing closed when either the source or the deployment moves out from under it.

**What the product is not, and why.** The original vision was a compiler emitting a multi-agent
system with tools synthesized from the target's CRUD surface, a knowledge-graph memory layer, an
embeddable iframe, and artifact trading between agents
([`07`](../../research/07-product-vision.md) §1.1). A pre-registered pivot rule fired: across three
task families a curated, hand-written tool surface **never won a family on success rate** against a
general agent holding a shell and the application's specification, and in one family it lost
outright. Synthesis, promotion selection, static per-tool effect classification and
decomposition-into-agents left v1 under **OD-09** and **OD-07**. What replicated was a *cost*
advantage, which is recorded as a measured v2 opportunity rather than as v1 scope.

**The three capabilities that remain are the whole of v1**: a spec-aware runtime, a contract-derived
verifier, and drift detection.

### What is measured, and what is not

This specification is written on an evidence base that is unusually explicit about its own gaps, and
it inherits the gaps rather than smoothing them.

**Not one of v1's three capabilities has a measured differentiating claim.** That is stated once, in
one place, at [`VERDICT.md` §2](../001-discovery-validation/VERDICT.md#all-three-v1-capabilities-ship-unmeasured),
and it is the single most important input to this document.

| v1 capability | What is unmeasured | Consequence in this specification |
|---|---|---|
| **Drift detection** | Everything. No detection rate, no false-alarm rate, no latency to detect, on either of its two clocks. No harness, no pre-registration, no experiment ever scheduled that reached it | The capability ships; the *claim* does not. ~~FR-041~~ **FR-042** makes pre-registration and measurement on both clocks a precondition of describing drift as a differentiator, and SC-015 is the report |
| **The effect gate's precision** | The precision of resolving a call to an effect tier, against anything (**U-43**) | This is *why* v1 is read-only (**OD-10**). The gate is carried as a shipped constraint rather than an outstanding risk: FR-009 denies everything it cannot resolve as a read, and ~~FR-040~~ **FR-041** makes the measurement the exit condition from read-only |
| **The verifier's margin over a model judge** | Whether a general-purpose model judge catches the same failures (**OD-14**) | The verifier ships with its *mechanism* demonstrated and its *necessity* unknown. ~~FR-038 and FR-039~~ **FR-039 and FR-040** instrument the comparison against real traffic and apply the pre-registered gate unchanged |

> **Corrected 2026-08-03 — wrong, not narrowed or superseded.** All three rows above pointed one
> requirement low, and consistently: FR-038 is the per-node trace record, FR-039 records the shadow
> judge's verdict, FR-040 reports the margin with the gate applied, FR-041 gates writes on effect-gate
> precision, and FR-042 gates the drift claim. Each identifier resolved, so nothing flagged it; each
> named the wrong requirement. Found while resolving the clarification markers. The Out of Scope
> table's *"the exit condition is FR-041"* was already correct and is unchanged.

**The verifier case needs a distinction kept intact, because both collapses of it have already been
made in this corpus.** Its mechanism is demonstrated and was not fitted to the corpus: the
postcondition arm detected all nine numeric value errors, including all three sub-1% near-misses,
with zero false alarms across 220 clean positives — *the offline full-corpus sweep; the
`FPR_c2 = 0/60` quoted elsewhere is the judge-scored sample and a smaller population, and the two
must never be merged ([14](../../research/14-architecture-synthesis.md) §3.2)* — through a six-rung
precision ladder committed before any derivation was written that contains no numeric constant. Those figures come from a trace
corpus whose freeze pinned the traces and not the prompts they answered, so they are recomputed
detection rates on a corpus with a known defect rather than clean experimental output
([finding 015](../001-discovery-validation/findings/015-verifier-vs-judge-not-run.md)) — which
constrains how firmly the mechanism may be described and does not touch the ladder, which is
model-free and inspectable. Its margin over a much cheaper model judge was never measured — no judge
call was ever billed, and no judge verdict exists to compute a margin against — and **OD-14** declares
it unmeasured and defers the measurement to production, recording that decision as a deliberate
departure from feature 001's prove-before-build discipline. The one-line form is: **the verifier
works; nobody knows whether it is needed.**

**A reader who takes any of this as settled should read `VERDICT.md` §2 before reviewing the rest of
this document.** Where a requirement below rests on something unmeasured, it says so, and the
measurement is itself a requirement.

### Claims this specification may not make

Recorded here because they are load-bearing and each has evidence behind the prohibition.

- **That application-specific tools make an agent more capable.** Measured and not supported
  (**OD-07**, **D-19**). The specification must not assert it.
- **That synthesis is safer.** The one observation behind "safer" traces to a human declining to use
  the target API's own filter — a judgement a generator has no basis for making — so a synthesized
  tool would inherit the defect (**C-18**). This is not an open hypothesis; it is a claim the
  evidence points against. What may be said, with its sample size attached, is that a *hand-written*
  surface once encoded identifier discipline a shell baseline missed.
- **A cost magnitude without its basis and its scope.** The surviving cost advantage is a
  within-session range restated downward after a larger figure turned out to be a cross-run,
  cross-fingerprint pairing at two observations. It belongs to v2's synthesis case, not to v1, and
  wherever it travels it travels with its basis.
- **"Provably read-only."** A method is a convention and a specification lookup is not a proof
  (**OD-10**). The word must not enter the product vocabulary.

## Clarifications

### Session 2026-08-03

> **Recorded as owner decisions 2026-08-03, retroactively — the answers below were applied to the
> requirement text on the day they were given and no decision record was created for any of them.**
> The first three are now **OD-18**, **OD-19** and **OD-20** in
> [`plan.md`](../001-discovery-validation/plan.md), each stating in its own text that it is a
> retroactive record and why. ~~The **fourth** answer below — the staleness disposition that became
> FR-047 — **still has no decision record**, and recording it is an owner act rather than a
> propagation one; the note at OD-20 says so rather than leaving it implicit.~~
> **Closed 2026-08-03 — the owner authorised the record and the fourth answer is now **OD-21**,
> immediately after OD-20 in the same register.** All four of this session's answers are citable. The
> struck sentence is kept because it is why OD-21 is a separate act from the propagation that wrote
> OD-18 through OD-20, and OD-21's own first paragraph turns on that distinction.

- Q: When a target publishes no machine-readable specification of what it serves, what does v1
  support? → A: Nothing. A published machine-readable specification is an **admission criterion**,
  and a target without one is rejected at admission with a stated reason (FR-002, FR-044). **OD-18.**
- Q: What does the runtime do with a result it cannot verify — return it marked unverifiable, or
  withhold it? → A: Return it, marked unverifiable, and measure the share of results that come back
  in that state (FR-025, FR-045). **OD-19.**
- Q: What triggers a deployment-drift check? → A: Both. Manual invocation is always available, and
  at least one automated trigger is configurable, defaulting to a scheduled re-fetch of the target's
  published specification with a stated detection window (FR-029, FR-046). **OD-20.**
- Q: When an admitted target stops publishing the specification that admitted it, does the runtime
  continue on the last-known-good served-operation set or deny? → A: **Continue, marked stale on
  every result**, under a configured staleness ceiling measured from the last successful fetch, past
  which it denies (FR-047, SC-021). **OD-21.**

### ~~Open — asked 2026-08-03, no owner answer yet~~ Asked and answered 2026-08-03

> **These are not deferrals and they are not loose requirements.** Each is a point where resolving a
> loose requirement ran into a **genuine product or constitutional choice that no existing decision
> settles**. In each case the requirement text is written as far as the evidence carries it and the
> undecided part is named here rather than filled in with a preference. ~~Both are stated as questions
> because both have a defensible answer either way.~~
>
> **Both were answered on 2026-08-03, in the same owner session, and the section is retitled rather
> than emptied because the questions are what make the answers legible.** Neither answer was one of
> the two branches the question posed. The Principle VI question offered a deviation record or an
> amendment and got an amendment **of a different shape than the one sketched** — unit-neutral rather
> than v1-scoped. The FR-024 question offered admit-or-exclude and got **neither** — ~~a ratchet
> admitting the source in one direction only~~ **first a ratchet admitting the source in one direction
> only, then, once that ratchet was verified inert against the census, a revision the same day to a
> variant admitting the source in one *region* only: where the ladder would otherwise refuse.** Both
> are recorded below against the question that
> produced them, and both carry an owner decision of their own.

- ~~**Q: Does Principle VI get a v1-scoped deviation record, or an amendment?**~~ **ANSWERED
  2026-08-03 — an amendment. `.specify/memory/constitution.md` is at v1.3.0, recorded as OD-22.**
  Its field list was
  scoped to *"every emitted system"* and so had no v1 subject, on the same argument that disposes of
  Principles II, III and VII; but its ship gate — *"a capability that cannot be attributed to a
  versioned node MUST NOT ship"* — was unscoped, and on a literal reading blocked every v1
  capability,
  because v1 has no nodes. FR-038 requires the same fields against the **span**. **A deviation
  record** would have had to cover *both* clauses, and would have left the graph wording in force the
  moment
  v2 emits a topology. **An amendment** restating identity and cost in unit-neutral terms binds
  v2's emitted graphs to the unit-neutral wording as well. → **The owner took the amendment**, on
  two grounds recorded at OD-22: a deviation record cannot fix an unscoped `MUST NOT`, and the
  principle's own unit word was already *"span"*, so the graph sat in the qualifier rather than in
  the unit. Set out clause by clause in Dependencies, which now records the resolution rather than
  the question.
- ~~**Q: Is a precision declared in the caller's own request an admissible source on FR-024's precision
  ladder?**~~ **ANSWERED 2026-08-03 — ~~admissible only where it tightens~~ admissible only where no
  artifact source supplies any precision, recorded as OD-23 and revised there the same day.**
  It was rung **P4** in the one instance ever built, and the trade was sharp in both
  directions. *For*: on that corpus P4 was the **sole** rung that caught the three sub-one-percent
  near-misses — a mean of `3.23` against `3.201754`, checked at the two decimal places the request
  itself asked for — so excluding it removes the numeric half of the surviving discriminative set,
  which is precisely what
  [finding 015](../001-discovery-validation/findings/015-verifier-vs-judge-not-run.md) says a strict
  reader accepting Amendment B2.2's invitation would lose. *Against*: it is **request-derived rather
  than contract-derived** on a product sold on contract-derived verification, and it lets a caller
  weaken their own verification by asking for fewer decimal places. → **The owner took neither
  branch**, ~~and made the rung a **ratchet**: a declared precision is admitted only where it is
  strictly tighter than the best comparison the ladder derives from a non-request source, and is
  otherwise ignored. This removes the weakening vector structurally. **It does not, on the one census
  available, preserve the catch** — the measured declaration was looser than the exact comparison it
  would now be tested against, so it is ignored and that quantity refuses.~~ **twice.** The first
  answer made the rung a **ratchet**, admitted only where strictly tighter than the best non-request
  comparison — which was then verified **inert**, because the ladder takes the first rung it reaches,
  so the rung is only reached where no artifact source applies and the comparand the ratchet needs is
  empty in exactly the case it could fire. **The second answer, the same day, is the narrower variant
  the first one had recorded as available and not taken**: a declared precision is admissible **only
  where no artifact source supplies any precision at all** — only where the ladder would otherwise
  refuse — and is ignored outright wherever one does, which is *stricter* than the ratchet in the
  region the ratchet governed. **The catch is preserved**: the one measured declaration meets the
  variant's condition on its own recorded derivation, so the census holds at its as-measured 17
  refusals of 61 and the three sub-one-percent near-misses stay detected. **What it costs** is that a
  caller obtains an affirmative, at a precision they chose, where the ladder would otherwise have
  returned an honest not-verifiable — bounded by the state being **provisional** and never plain
  verified, and by the displaced alternative being a refusal, which checks nothing. FR-024's property 5
  states the rule and prices it; SC-005's stratified refusal-share requirement, added when the ratchet
  concentrated the loss in the sub-one-percent stratum, **stays** — the instance is repaired, the
  structural hazard is not. **Provisional marking is
  retained**, as property 6, ~~on the ground that the ratchet governs direction while marking governs
  provenance~~ **and matters more under the variant than under the ratchet: no independent artifact
  exists is the variant's own admissibility premise, so marking is the only disposition Principle I
  leaves**.

**Why the first answer is a safety finding rather than a preference.** The alternative to requiring
a published specification is discovering which methods a path serves by probing it, and
[finding 011](../001-discovery-validation/findings/011-reachability-without-schema.md) §4 measured
what that costs. On Django, whose URL resolver carries no method information at all, an undecorated
view **executes on a probe carrying a fabricated verb**: the probe returned 400 with the handler
already run. Method discovery by probing therefore runs the target's own code, which a read-only
product may not do, so that option closes on safety grounds and not on convenience. The remaining
alternative — an operator declaration of what the deployment serves — was rejected because
everything derived from an unverifiable declaration is provisional under **D-17**, and a product
sold on *verified against the code's own contracts* cannot rest that guarantee on an unchecked
assertion. What is **not** excluded is probing for **path**-level reachability, which is a different
question: finding 011 measured it exact at path granularity on every target it ran against, and it
remains the mechanism behind FR-046's per-operation precondition. The exclusion is of method
discovery by probing, not of probing.

**Why the second answer leaves FR-024 intact.** Returning an unverifiable result marked unverifiable
is the pattern **D-17** already mandates for derived artifacts, which carry provenance and a
validation status rather than being suppressed when they cannot be validated — suppression is what
makes a gap invisible. And v1 is read-only (**OD-10**), so an answer the system could not verify
misleads a human and cannot damage data, which is the asymmetry that makes returning it the cheaper
error. FR-024 is unchanged and is the reason unverifiable results exist at all: refusing to invent a
tolerance is what *produces* the state, and this decision settles only what the caller then sees.
Because nothing in the evidence base estimates how often the state occurs, FR-045 makes the share a
measurement rather than an assumption.

**Why the third answer is two mechanisms rather than one.** **O-04**'s two clocks. The source clock
has the commit as a natural trigger; the deployment clock has no equivalent, because a deployment
moves under configuration, rollout and its installed package set and none of those produces a
commit. Whether a customer can emit a deployment event at all varies by how they deploy, and under a
self-hosted model (**OD-08**) it cannot be assumed — so a product imposing one mechanism would be
blind on some deployments and redundant on others. Where a customer *can* emit deployment events,
that is admissible as a configured trigger and is the lowest-latency one available; it may not be
the only one.

**Why the fourth answer is a consistency argument rather than a preference.** It is the third time
this specification makes the same choice, and the first two are load-bearing. An unverifiable result
is **returned marked** rather than withheld (FR-025). A derived check that cannot be validated
against an artifact its own derivation did not produce **carries provenance and a provisional
marking** rather than being suppressed (FR-026, from **D-17** and constitution Principle I since
v1.1.0). A stale operation set is now
**served marked** rather than denied. In each case suppression is what makes the gap invisible and
the marking is what leaves the caller able to act on it, and choosing to deny here would have been
the single place this corpus reversed itself — with nothing in feature 001 asking it to.

The reason specific to this case is availability, and it is a *distinguishability* argument rather
than an appetite for uptime. Denying on the first failed re-fetch makes a network blip
indistinguishable from a decommissioned specification, and converts any transient gating of the
target's specification endpoint — a restart, a rate limit, a proxy in front of it — into an outage
of this product. There is no compensating safety gain in that first interval, because v1 is
read-only (**OD-10**): the worst a stale set can do is offer an operation the deployment no longer
serves, which fails at the target and is caught by the path-level backstop FR-046 already requires
to be recorded as a drift signal.

**What the ceiling is not.** It is a configured default with nothing behind it. Nothing in feature
001 measures how long a specification endpoint stays down, how long a deployment keeps honouring a
withdrawn operation set, or what an operator would tolerate. The clarify session declined to invent
a threshold for FR-045's not-verifiable share for exactly this reason, and the same restraint
applies here: FR-047 states a default, says it is a default, and binds it to FR-043 so that it
cannot travel externally as a validated number. This corpus has repeatedly caught inherited figures
presented as measured ones — FR-041 exists precisely to stop a threshold pre-registered for a
per-tool gate from carrying over to a per-call one by default — and a ceiling launders easily.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Operate a running application through its own specification, safely (Priority: P1)

A platform engineer points the system at their running application and asks it questions in natural
language. The agent works out which of the application's published operations answer the question,
calls them, and returns an answer. Nothing the agent attempts that is not a read against that one
application reaches the network at all — not from the runtime, and not from a command the agent
composed for itself.

**Why this priority**: This is the product's floor. Without it there is nothing to verify and
nothing to detect drift against. It is also the story that carries every safety obligation, because
the agent holds general tools pointed at live data inside the operator's own trust boundary.

**Independent Test**: Stand up a reference application with seeded state. Configure the runtime
against it. Ask a set of questions whose correct answers are known from the seed. Separately, run an
adversarial set that attempts writes, attempts destinations other than the target, and attempts to
make the enforcement point blind to the method — and confirm every one is denied with a legible
reason, and that the corresponding request never reaches any destination. **Extended 2026-08-03 with
FR-048 and FR-049**: run the same battery's environment arms as well — attempts to read and write
outside the declared set of filesystem locations, including against the runtime's own configuration,
and a workload that exhausts each declared bound in turn.

**Acceptance Scenarios**:

1. **Given** a configured target deployment and its served-operation set, **When** the operator asks
   a question answerable from that set, **Then** the agent returns an answer and the trace shows
   which operations produced it.
2. **Given** the agent attempts an operation whose method is not a safe method in the served-operation
   set, **When** the attempt reaches the enforcement point, **Then** it is denied, the target is never
   contacted, and the denial states the rule that produced it.
3. **Given** the agent composes and runs a command that opens its own connection to an address
   outside the pinned set, **When** the connection is attempted, **Then** it fails, and the failure
   is recorded identically to a denial originating in the runtime.
4. **Given** the agent attempts a request whose method and path the enforcement point cannot read,
   **When** the attempt is made, **Then** it is denied rather than allowed on the destination alone.
5. **Given** a question the served-operation set cannot answer, **When** the session ends, **Then**
   it terminates in a named terminal state within its configured ceilings rather than exhausting
   them, and the ceilings are unchanged by a crash and resume during the session.
6. **Given** a target that publishes no machine-readable specification of what it serves — or one
   that publishes an unreadable or empty specification — **When** the operator configures the runtime
   against it, **Then** admission fails, the failure names which state was found and what would have
   to change, and no agent session starts against that target.
7. **Given** the agent composes a command that reads or writes outside the declared set of filesystem
   locations — including the effect-gate rule set and the egress policy — **When** the command runs,
   **Then** the access fails rather than partially succeeding, and it is recorded with the rule that
   produced it exactly as a denial originating in the runtime is.
8. **Given** a command that exhausts the declared processor bound or the declared memory bound,
   **When** the bound is reached, **Then** the session ends in a named terminal state rather than by
   generic error, the work already performed still counts against the session's ceilings, and
   anything else running on the same host keeps serving.

---

### User Story 2 - Know whether the answer was actually right (Priority: P2)

The same engineer needs to know whether to trust the answer. For every reported result the system
recomputes the reported quantity by an independent path derived from the target's own code, and
reports one of three states: verified, failed verification, or not verifiable.

**Why this priority**: This is the half of the product nobody self-serves. The ceiling test
established that a competent engineer with a shell and the application's specification can already
reach their application; what they cannot do is prove that what came back was right. The failure
that matters is the one where the request was well-formed, the response was well-formed, the answer
matched the application's own reported total, and it was still wrong.

**Independent Test**: Take a corpus of results with injected value faults — including near-misses
small enough that a conformance check cannot see them — and a matched corpus of clean results.
Report detection rate and false-alarm rate. Separately, confirm that a verifier that checks only
shape and type detects none of the value faults, which is the control.

**Acceptance Scenarios**:

1. **Given** a result whose value is wrong but whose shape conforms at every layer, **When**
   verification runs, **Then** it fails verification, and the failure names the independent path
   that disagreed.
2. **Given** a clean result, **When** verification runs, **Then** it passes and raises no alarm.
3. **Given** a reported quantity for which no check of stated precision can be derived, **When**
   verification runs, **Then** it refuses, the result is still returned to the caller carrying the
   not-verifiable state and the named reason, and that state is distinguishable from both pass and
   fail rather than being resolved by a default tolerance.
4. **Given** a derived contract or a derived check, **When** it is inspected, **Then** it carries how
   it was derived, what it was derived from, and whether it was validated against an artifact its own
   derivation did not produce — and if it was not, it is marked provisional.

---

### User Story 3 - Fail closed when the code or the deployment moves (Priority: P3)

Between the day the system was configured and today, either the codebase changed or the deployment
did. The engineer needs the system to notice which one, disable only what is affected, and say so
loudly — rather than continuing to operate on a stale picture and reporting confident, wrong answers.

**Why this priority**: A snapshot of a moving system begins rotting the day it is taken, and a
silently stale check produces false confidence, which is worse than a missing one. It is P3 rather
than P1 because the first two stories deliver value on day one and this one delivers value on day
thirty — and because it is the least evidenced of the three.

**Independent Test**: Two synthetic corpora. In the first, mutate the source so derived contracts no
longer match, leaving the deployment untouched. In the second, change what the deployment serves,
leaving the source untouched. Report, for each, whether the change was detected, whether anything
unaffected was disabled, and how long detection took.

**Acceptance Scenarios**:

1. **Given** a source change that invalidates a derived contract, **When** the automated check runs,
   **Then** the affected operation is reported as drifted in that same run and is disabled for agent
   use.
2. **Given** a deployment that has stopped serving an operation while the source is unchanged,
   **When** drift detection runs, **Then** the operation is reported as drifted, and the signal
   states that the deployment clock moved rather than the source clock.
3. **Given** one operation has drifted, **When** a session runs, **Then** the remaining operations
   stay available and the drifted one is refused with a reason, rather than the whole runtime being
   stopped or the drifted operation silently attempted.
4. **Given** any drift signal, **When** it is inspected, **Then** it identifies the artifact version
   before and after, the deployment identity it applies to, and which of the two clocks moved.
5. **Given** a deployment change and the default automated trigger, **When** the configured detection
   window elapses, **Then** the change has been detected without any event from the customer's
   deployment pipeline; and **Given** the same change, **When** the operator invokes a drift check
   manually, **Then** it is detected on demand without waiting for the window.
6. **Given** an admitted target that has stopped publishing its specification, **When** the drift
   check re-fetches and fails, **Then** the runtime keeps answering from the last-known-good
   served-operation set and every result it returns is marked stale, machine-distinguishably and
   with the set's age; **Given** the staleness ceiling then elapses with no successful re-fetch,
   **When** any call is attempted, **Then** it is denied with the stale set and its age named as the
   rule, and any session in flight ends in a named terminal state; and **Given** the specification
   is published again, **When** the next re-fetch succeeds, **Then** the set is replaced, the
   difference between the two sets is itself reported as drift rather than adopted silently, and the
   stale marking clears.
7. **Given** a target that never stops publishing its specification and adds an operation to it
   between two successful re-fetches, **When** the next re-fetch succeeds, **Then** the new operation
   is inspected before it becomes available to the agent, and is refused rather than made available
   if it cannot be inspected.

---

### User Story 4 - Run it in your own environment, on your own model provider (Priority: P4)

An operator installs the system inside their own boundary and supplies their own model provider
credential and their own target credential. Neither credential leaves their boundary, and neither
appears in anything the model can read.

**Why this priority**: Self-hosted is the shipped deployment model (**OD-08**) and
bring-your-own-credentials is a hard requirement rather than a preference — a customer who brings
one vendor's credential must get a working system. It is P4 because it constrains how the first three
stories are built more than it delivers a separate slice of value.

**Independent Test**: Complete the User Story 1 battery once per supported provider with no change to
the runtime other than configuration, and run an automated scan over every trace, artifact and
persisted record asserting that no secret value appears in any of them. **Extended 2026-08-03 with
FR-050**: scan the agent's execution environment itself on the same standard, and replay every
credential-shaped value found there after the session has ended.

**Acceptance Scenarios**:

1. **Given** a credential for any one supported provider and no others, **When** the runtime starts,
   **Then** it runs the full battery successfully, including sequences of chained tool calls.
2. **Given** a provider that returns opaque reasoning state on a turn, **When** the conversation
   continues over several turns, **Then** that state is returned verbatim on subsequent turns and is
   never merged with another provider's.
3. **Given** any completed session, **When** traces, emitted artifacts and persisted state are
   scanned, **Then** no secret value appears in any of them.
4. **Given** a required configuration value is missing or malformed, **When** the runtime starts,
   **Then** it fails loudly at startup rather than degrading silently.
5. **Given** a completed session, **When** every credential-shaped value observable from inside its
   execution environment during the session is replayed afterwards, **Then** none of them is
   honoured and each refusal is recorded; and **Given** a subsequent session, **When** it starts,
   **Then** nothing written inside the previous session's environment is readable from it.

---

### User Story 5 - Learn from production whether the three claims hold (Priority: P5)

The owner needs the measurements feature 001 could not obtain. The system carries the instrumentation
to produce them from real traffic: a shadow judge run alongside the verifier without affecting
behaviour, an effect-gate precision measurement against real operations, and a pre-registered drift
measurement on both clocks.

**Why this priority**: It is last because it depends on the other four existing, and it is present at
all because shipping three unmeasured capabilities without instrumenting them would convert a
recorded, deliberate exception into an ordinary one. **OD-14** deferred the verifier measurement to
production explicitly, which makes the instrumentation an inherited obligation and not a
nice-to-have.

**Independent Test**: Over a fixed window of production traffic, produce three reports: marginal
detection of the verifier over the shadow judge with the pre-registered gate applied; the effect
gate's read-only precision against a labelled corpus of real operations; and drift detection rate,
false-alarm rate and latency on each clock.

**Acceptance Scenarios**:

1. **Given** production traffic through the verifier, **When** the reporting window closes, **Then**
   marginal detection over the shadow judge is reported, and the pre-registered gate is applied
   unchanged — including the branch that fires on the judge's own discrimination regardless of what
   the verifier does.
2. **Given** the shadow judge disagrees with the verifier, **When** the session runs, **Then** the
   judge's verdict changes nothing about what the caller sees or what the gate permits.
3. **Given** a labelled corpus of real target operations, **When** the effect gate is scored against
   it, **Then** read-only precision is reported with its threshold derived for a per-call gate rather
   than inherited from the superseded per-tool gate.
4. **Given** no drift measurement has been reported, **When** external material describing the
   product is reviewed, **Then** it contains no claim that drift detection is a differentiator.

---

### Edge Cases

- **The target publishes no served-operation specification.** ~~Every call is then unresolvable, and
  a read-only gate that denies what it cannot resolve denies everything. See the clarification at
  FR-002.~~ **Superseded 2026-08-03 by the clarification at FR-002 — the described behaviour was
  correct and it is now unreachable.** Such a target is rejected at admission by FR-044 with a stated
  reason and never starts a session, precisely so that this failure mode — a product that installs
  successfully and then denies every call with no explanation — cannot occur.
- **An admitted target stops publishing its specification.** The condition passes admission and then
  arises later, so FR-044 does not cover it. It is deployment-clock drift affecting every operation
  at once, and ~~the disposition is the open question marked at FR-047.~~ **Resolved 2026-08-03 by
  the clarification at FR-047 — the question was genuinely open and is now closed.** The runtime
  continues on the last-known-good served-operation set, marked stale on every result it produces,
  until a configured staleness ceiling measured from the last successful fetch is crossed; past the
  ceiling every call is denied under FR-030, and recovery runs the full admission sequence rather
  than a bare re-fetch.
- **The specification is stale relative to the deployment.** The specification says an operation is
  served and it is not, or vice versa. This is deployment drift and is User Story 3's second clock;
  the gate must resolve against what is currently believed served, and the belief must carry its own
  freshness — bounded under default configuration by FR-046's detection window. **Narrowed
  2026-08-03 by FR-047 — the bound holds only while re-fetches succeed.** Once they stop succeeding
  the freshness bound is FR-047's staleness ceiling rather than FR-046's detection window, and the
  belief's age stops being merely bounded and becomes caller-visible on every result.
- **A safe-method operation of the target performs an outbound request on the caller's behalf** — a
  link preview, an import-by-URL, a webhook test. The agent that cannot reach the internet can then
  ask the target to reach it. This is unmeasured on any target (**U-44**); FR-020 requires inspection
  and fails closed where inspection is impossible. **Extended 2026-08-03 by FR-051 — extended, not
  wrong.** FR-020 runs at admission, so an operation added to a still-published specification between
  two successful re-fetches would have reached the agent uninspected; FR-051 attaches the inspection
  to every set change instead. The inspection is the same one and the property is still unmeasured.
- **The agent follows an absolute URL** out of a paginated response or out of the specification text
  itself. It points at the target's real address rather than the one the agent was handed, so the
  request fails. This is fail-closed and legible, and it will generate pressure to widen the
  allowlist; FR-019 makes widening a reviewed act.
- **The verifier refuses on a large share of results.** ~~Refusal is honest and it is also a product
  experience; see the clarification at FR-025.~~ **Narrowed 2026-08-03 by the clarification at
  FR-025 — the tension was real and half of it is now settled.** The result is returned to the
  caller marked not verifiable rather than withheld, so a high refusal share degrades the product's
  *assurance* rather than removing its answers. What is not settled is the share itself, which
  nothing in the evidence base estimates; FR-045 makes it a measurement.
- **A recall or coverage improvement in the analysis layer silently removes a safety property** that
  was being supplied by the extractor failing closed. The coupling is an interface obligation, not an
  incidental behaviour (**U-40**).
- **A session crashes mid-run and resumes.** Ceilings must not reset and side effects already
  recorded must not repeat.
- **A legitimately blocked operation has no runtime override.** Nothing escalates to a human during a
  session; the operator's recourse is configuration, reviewed.
- **The operator co-locates the runtime, the target and the target's datastore on one host.** This is
  the ordinary self-hosted topology and it is exactly the condition under which a host-granular
  allowlist would permit a direct database connection. **Extended 2026-08-03**: it is also the
  condition under which an unbounded execution environment starves the very application the product
  exists to operate, which is why FR-049's bounds are enforced from outside that environment and why
  exhausting one may not deny service to anything else on the host.
- **The agent leaves something behind for a later session to pick up.** A file written inside the
  execution environment, or a credential-shaped value cached there, survives into the next session if
  the environment is reused as-is. FR-050's third observable is what forbids it, and it is the term
  that makes "no credentials outliving the run" checkable rather than merely asserted: the check is
  that a value captured in one session is refused after it ends and unreadable from the next one.

## Requirements *(mandatory)*

### Functional Requirements

FR-044 through FR-047 were added by the clarification session of 2026-08-03. Numbering is
append-only so that existing cross-references stay valid, so each new requirement sits with the
requirements it belongs to rather than in numeric order.

**Extended 2026-08-03 — extended, not wrong.** FR-048 through FR-054 close the three Constitution
Check exposures recorded in [`checklists/requirements.md`](./checklists/requirements.md), in the
specification rather than at the plan gate, because two of the three are spec fixes and the plan
phase cannot supply a requirement this document declined to state. FR-048 through FR-050 supply the
three terms of constitution Principle IV bullet 1 that this specification did not require — a scoped
filesystem, a processor and memory bound, and no credential outliving the run — against the four
egress terms it already discharges in full at FR-014 through FR-019. FR-052 states the boundary that
makes FR-039's shadow judge compliant with Principle I rather than leaving it to be inferred.
FR-053 and FR-054 close the two clauses of Principles VII and VIII that apply to v1 and were only
partly met. FR-051 closes an admission-only reading of FR-020. The append-only rule applies to all
of them, and each sits with the requirements it belongs to.

**Extended again 2026-08-03 with FR-055 and SC-029, and this one comes from the plan gate rather
than from a checklist.** The plan phase rejected part of the Principle VII deviation record on
substance: it disposes of the determinism clause's byte-stability half as having no subject, and
FR-054's eight artifact kinds are the subject. FR-055 is that narrowing carried back into
requirement text, where it belongs, instead of living as a correction in a downstream artifact.
Append-only applies to it too.

**Spec-aware runtime**

- **FR-001**: The system MUST require, as configuration, an identified target deployment, and MUST
  obtain that deployment's served-operation set before any agent session begins. If it cannot, the
  system MUST fail loudly at startup rather than starting with an empty or assumed set.

  > **Narrowed 2026-08-03 by FR-047 — narrowed, not wrong.** A runtime restarting while an already
  > admitted target is not publishing MAY start from the **persisted last-known-good set, marked
  > stale**, provided FR-047's staleness ceiling has not been crossed. That set is neither empty nor
  > assumed — it was obtained from the target and it carries its own age — so the clause this
  > requirement actually protects is intact. The fail-loudly rule applies unchanged where no
  > last-known-good set exists, where the target was never admitted, or where the ceiling has been
  > crossed. Without this narrowing a restart during a transient outage of the target's specification
  > endpoint would be indistinguishable from a decommissioned specification, which is the confusion
  > FR-047 exists to prevent. **The authorising decision is OD-21** *(citation added 2026-08-03 when
  > OD-21 was recorded; the narrowing itself is unchanged)*.
- **FR-002**: The served-operation set MUST be produced by a stage separate from and above source
  analysis, and MUST record the deployment identity it describes. Source analysis MUST remain
  reproducible from the codebase alone, with no network input and no dependency on any running
  deployment. The served-operation set MUST be obtained from a **machine-readable specification the
  target itself publishes**, at operation granularity. A target that publishes no such specification
  is **not a supported target in v1**: it MUST be rejected at admission under FR-044, and MUST NOT be
  admitted and then denied call by call at run time. Method-level reachability MUST NOT be
  established by probing the target, and MUST NOT be accepted from an operator declaration.
  Path-level probing is unaffected by this requirement and remains available to FR-046.

  > **Authorising decision named 2026-08-03 — the requirement is unchanged; what it lacked was a
  > citation.** The admission-criterion clause and the two exclusions after it are **OD-18**, taken at
  > this document's clarify session on 2026-08-03 and recorded in the decision log retroactively on the
  > same day. Until that record existed, an admission criterion narrowing v1's supported-target
  > population cited nothing but this document.
- **FR-044**: Before any target is admitted, the system MUST run an admission check that fails closed
  and states its reason. The check MUST classify the target's published specification into at least
  four distinguishable states — published and non-empty; absent; present but not readable by the
  configured credential; and present, readable and carrying no operations — and MUST admit only the
  first. A specification that fetches successfully but carries no operations MUST NOT be read as
  a deployment that serves nothing. On rejection the system MUST name which state it found, which
  admission criterion failed, and what the operator would have to change, and MUST NOT start an agent
  session against that target. **The criterion this check enforces is OD-18**; the four-state
  classification and the fail-closed disposition are this document's own.
- **FR-003**: The agent MUST act on the target only through the target's own external interface. It
  MUST NOT call the target in process and MUST NOT reach the target's datastore directly.

  > **Unchanged 2026-08-03, and recorded here because two downstream artifacts read an obligation
  > into it that it does not carry.** [`data-model.md`](./data-model.md) §1.1 and
  > [`quickstart.md`](./quickstart.md) step 2 both cited this requirement for establishing
  > correspondence between the running deployment and a source commit. **This requirement is about
  > the agent's access path and nothing else** — it is **D-01** — and it gains no correspondence
  > clause. The real obligation underneath the miscitation is a *declared* source reference, which is
  > now **FR-057**; both downstream artifacts are corrected there.
- **FR-057**: The **source reference** — the repository and commit the operator asserts produced the
  admitted deployment — MUST be required configuration under FR-033, MUST be recorded on the
  deployment, and MUST be carried on every source-derived artifact as the anchor of the source clock
  FR-028 and FR-031 depend on. An absent source reference MUST make startup fail loudly, naming what
  is missing, exactly as FR-001 requires of the served-operation set.

  **It MUST be recorded and presented as an operator declaration and MUST NOT be recorded or
  presented as verified correspondence.** v1 has no mechanism that establishes that a given source
  produced a given running instance, and **admission MUST NOT be described — in this specification,
  in any downstream artifact, in the system's interfaces, or in its documentation — as establishing
  that correspondence**. Where the source reference appears beside a derived artifact, its status as
  a declaration MUST be visible in the same place, so that no consumer can read it as evidence.
  Divergence between the declared source and the running deployment is **detected afterwards and
  continuously** by the two-clock drift machinery of FR-028 through FR-031 and FR-046; that is
  detection of divergence, not establishment of correspondence, and the two MUST NOT be conflated.

  > **Added 2026-08-03 to adjudicate a conflict between FR-003 and two downstream artifacts, and the
  > adjudication went partly each way. Read the split, because "the downstream overreached" alone is
  > the wrong summary.**
  >
  > **The overreach is real and is corrected at source.** [`data-model.md`](./data-model.md) §1.1
  > carried a `correspondence_evidence` field glossed *"what established that this source produced
  > this deployment (FR-003)"*, and [`quickstart.md`](./quickstart.md) step 2 said admission
  > *"establishes correspondence between the running deployment and the source commit (FR-001,
  > FR-002, FR-003)"*. **FR-003 says neither, and it is not a near miss**: FR-003 is the access-path
  > requirement — act through the target's external interface, not in process, not into its
  > datastore — inherited from **D-01**. It has no correspondence clause to gain, so extending it
  > would have been the wrong repair. Worse than the miscitation: **nothing in v1 can produce that
  > evidence**, so admission was gated on a step with no mechanism, and both artifacts have been
  > corrected rather than this requirement being bent to fit them.
  >
  > **What survives the correction is not nothing, and dropping it would have broken the drift
  > model.** FR-028 detects source drift and FR-031 requires every drift signal to state *which of the
  > two clocks moved*. **A source clock with no anchor is not a clock**, so the source reference is a
  > genuine requirement — it was simply never stated as one, which is why the downstream artifacts
  > invented a citation for it. It is stated here.
  >
  > **OD-06 is what decides the shape, and it cuts cleanly.**
  > ([`plan.md`](../001-discovery-validation/plan.md) OD-06.) That decision put reachability in a
  > stage *above* analysis precisely so analysis stays rebuildable from the codebase alone —
  > deterministic, cacheable, and testable against committed fixtures, which a network probe would
  > break because *a fixture repository has nothing to probe*. A **verified** deployment-to-commit
  > binding would need something read from the running instance, and would therefore reintroduce the
  > exact dependency OD-06 removed; FR-002 restates the prohibition in this document's own words. A
  > **declared** source reference does not: OD-06 gives deployment identity a home on the reachability
  > annotation, above analysis, and this reference lives there beside it. So the correspondence is
  > **not coherent as a verified admission step and is coherent as a declaration**, which is the
  > distinction this requirement turns on.
  >
  > **This corpus rejected an operator declaration once already, and the difference between the two
  > cases has to be stated rather than assumed.** The clarification session above rejected *an
  > operator declaration of what the deployment serves* on the ground that **everything derived from
  > an unverifiable declaration is provisional under D-17**, and that a product sold on *verified
  > against the code's own contracts* cannot rest that guarantee on an unchecked assertion. That
  > reasoning is not overturned here; it is **distinguished on two points and conceded on a third**.
  > *Distinguished*: the served-operation set had a **verifiable alternative** — the target's own
  > published specification — and this has none, so rejecting the declaration would not buy a better
  > artifact, it would leave FR-028's source clock with no anchor. And the served-operation set is a
  > **safety boundary**, bounding what the agent may call; the source reference bounds nothing, and
  > FR-009's deny-what-cannot-be-resolved rule is unaffected by it. *Conceded*: **D-17's provisional
  > rule is the right instinct**, which is why the presentation clause above exists.
  >
  > **A gross mismatch is caught downstream and a subtle one is not, and the boundary between them is
  > the honest statement of what v1 offers.** Derived contracts are independently validated against
  > the target's **published specification**, which is fetched *from the running deployment* (FR-002,
  > T-14, SC-007), and the two clocks are compared continuously. So a source reference pointing at the
  > **wrong application** surfaces as derived contracts that fail to validate, and as drift. What
  > survives undetected is the **right repository at the wrong commit**, where the published
  > specification still matches and the two clocks agree with each other while both disagree with
  > reality. That is the residual, it is carried in Open Risks Carried, and it is not closed here.
- **FR-004**: The agent MUST hold general-purpose capabilities — command execution and a general
  request capability — rather than a per-operation tool surface, and those capabilities MUST remain
  available as the fallback path when no served operation fits the request. A tool surface is a bet
  that the question falls inside it, and the measured cost of losing that bet was a run that spent
  its entire budget and returned nothing.
- **FR-005**: The runtime MUST enforce per-session ceilings on spend, token consumption, wall-clock
  time and turns. A ceiling MUST survive a crash and resume: the post-resume total MUST be counted
  against the same ceiling rather than restarting it. **All four ceilings are required configuration
  under FR-033 and this specification states no default value for any of them**: a ceiling that is
  unset MUST make startup fail loudly, naming which ceiling is missing, and MUST NOT be treated as
  unbounded or filled from a default this specification invented. **A crash MUST NOT reduce the total
  counted against any of the four ceilings** — consumption already incurred before a crash MUST still
  be counted after the resume, so a session that crashes and resumes repeatedly MUST NOT be able to
  exceed a ceiling by any number of resumes. Every one of the four ceilings, and the cumulative total
  against it, MUST be recorded with the deployment identity it applies to. **SC-030** is the
  measurement.

  > **Extended 2026-08-03 by FR-049 — extended, not wrong and not narrowed.** This requirement is
  > true and complete for the four ceilings it names, all of which are *consumption* ceilings on a
  > session. Constitution Principle IV bullet 1 requires a sandbox capped on **CPU, memory and
  > wall-time**, and this requirement supplies the wall-time term only — so read as the whole of that
  > term it would have satisfied one third of it. The processor and memory bounds are properties of
  > the execution environment rather than of a session's consumption, they are enforced from outside
  > that environment, and they are FR-049.

  > **Extended again 2026-08-03 — extended, not wrong and not narrowed, and the reason is a regression
  > rather than an omission.** This requirement's crash-and-resume clause was correct and remains
  > unchanged. What it did not say is what happens when a ceiling is **unset**, and what happens to
  > consumption a crash destroys the accounting for — and both matter more than they did this
  > morning. **U-30** in [`14`](../../research/14-architecture-synthesis.md) §5.1 records that no layer
  > of the stack has been shown to enforce a spend ceiling surviving a crash and resume;
  > [finding 006](../001-discovery-validation/findings/006-graph-loop-primitives.md) measured ADK's
  > `max_llm_calls` halting a non-terminating graph at exactly its ceiling **and then permitting 6
  > cycles across two attempts against a ceiling of 3**, because the counter lived on a context
  > rebuilt per attempt. **`plan.md` OD-15 dropped ADK, so that ceiling is gone, and inadequate and
  > absent are different**: nothing now occupies the interim position, which is why the unset case had
  > to stop being unstated. **No numeric threshold is invented here.** The treatment is the one
  > [`plan.md`](./plan.md)'s technical context recommends for FR-049's processor and memory bounds —
  > *"failing closed when unset rather than shipping a number"*, its **Q-10** — applied unchanged,
  > because there is no evidence base for a token, turn, time or dollar figure and a default would be
  > the inherited-number failure this corpus keeps catching. It differs from FR-046's interval and
  > FR-047's staleness ceiling deliberately: those ship a stated default marked unvalidated under
  > FR-043, and a spend ceiling with an invented default is not an unvalidated number but an
  > unbounded liability wearing one.
  >
  > **What this requirement states and what it cannot state.** The cumulative-across-resumes property
  > is stated as an observable one and is measurable as written — SC-030 induces the crashes and
  > checks the totals. Whether it is *enforceable* depends on a mechanism this document deliberately
  > does not choose: the accounting has to be durable at a finer grain than the work it accounts for,
  > and finding 006's failure was exactly a counter living in the wrong place. That is a plan-phase
  > obligation, and it is the same seam **U-31** names from the other side — crossing a durable-execution
  > activity boundary silently loses token accounting ([`02`](../../research/02-agent-harnesses.md) §4),
  > which would degrade the very metric this requirement depends on.
- **FR-006**: Every session MUST terminate in a named state drawn from a declared taxonomy in which
  each success and each failure outcome is separately named. A generic error MUST NOT be a terminal
  state.

  **The stall condition, defined 2026-08-03.** The taxonomy's `no_progress` member
  ([`data-model.md`](./data-model.md) §2.1) MUST fire on a predicate over turns, defined as follows.

  **A turn makes progress when it does at least one of two things**: it produces the session's
  reported result, or it issues at least one tool call that is **new to the session** — meaning the
  combination of the tool invoked, the arguments it was invoked with, and the outcome it returned
  does not already appear in this session. Identity here MUST be decided by the content address of
  the canonically serialized combination under FR-055, not by inspection, so that "the same call
  again" is a determinate question rather than a judgement.

  **A turn makes no progress in every other case** — and the cases are worth naming, because each is
  a stall shape a caller has to be able to tell apart from a slow success: a turn that issues no tool
  call and returns no result; a turn whose every tool call repeats a call already made in this
  session with the same arguments and the same outcome; and a turn whose every tool call fails in a
  way already recorded in this session for that call.

  **The session MUST terminate in `no_progress` when a configured number of consecutive turns make
  no progress.** That number MUST be **required configuration** under FR-033; **this specification
  states no default value for it**, and an unset value MUST make startup fail loudly, naming what is
  missing, exactly as FR-005's ceilings and FR-049's bounds do. A turn that makes progress MUST reset
  the count.

  > **Two things this definition is deliberately doing, and one it deliberately is not.**
  >
  > **It counts *consecutive* turns, which is what makes it safe to treat a pure reasoning turn as no
  > progress.** A turn that plans without calling anything is legitimate and common; counting it as
  > progress would hide an unbroken loop of them until the turn ceiling, and counting it as a stall in
  > isolation would kill legitimate planning. Consecutiveness resolves that without a special case:
  > one planning turn between two productive turns resets the count and costs nothing, and only an
  > unbroken run terminates the session.
  >
  > **It takes the plan's Q-10 treatment for its threshold, and the reason differs from Q-10's other
  > users in a way worth recording rather than glossing.** FR-005's ceilings and FR-049's bounds fail
  > loudly when unset because an unset one is an **unbounded liability**. That is not true here:
  > FR-005's turn ceiling already bounds every session, so an unset stall threshold costs no money and
  > no time. What it costs is **the name** — the session would end at `turn_ceiling_reached` when what
  > actually happened was a stall, and this requirement's entire subject is that each outcome be
  > separately named. A taxonomy member no configuration can ever fire is a member with no producer,
  > which is the same defect as a generic error wearing a specific label. So the treatment is the
  > same and the justification is not inherited.
  >
  > **It does not attempt to detect a loop that varies its arguments.** An agent that calls the same
  > tool with a slightly different argument each turn, forever, makes "progress" under this predicate
  > every time. That is a real gap and this definition does not close it; what bounds that session is
  > FR-005, and what makes it *visible* is the trace under FR-038. Closing it would mean judging
  > whether varied calls are meaningfully different, which is a model judgement about success and is
  > exactly what FR-023 forbids as a success signal.
- **FR-007**: A resumed session MUST NOT repeat a side effect already recorded as performed, and work
  performed in parallel MUST be ordered deterministically before it is recorded.

**Effect resolution and the read-only constraint**

- **FR-008**: Every call the agent attempts against the target MUST be resolved to an effect tier at
  an enforcement point that can block, before the call reaches the target.
- **FR-009**: Only a call resolving read-only MAY be permitted. Reversible-write, irreversible, and
  unresolved MUST all be denied outright. Nothing MAY escalate to a human during a session.
- **FR-010**: A call resolves read-only when its method is a safe method of a served operation in the
  set from FR-001 **and** it matches no entry in a maintained deny list of known side-effecting reads.
  This is a stated rule set, not a proof, and the system's documentation and interfaces MUST NOT
  describe it as one.
- **FR-011**: A denial MUST return a reason legible enough for the agent to find a safer path, and
  MUST be recorded in the trace together with the rule that produced it.
- **FR-012**: The deny list and the safe-method rule set MUST be versioned configuration, reviewable
  by the operator before it takes effect, and MUST live where the agent has no write path to it.
- **FR-013**: No requirement in this specification MAY be satisfied by classifying a command the agent
  composed. Command execution is governed by the sandbox boundary and by FR-014 through FR-021; its
  effect on the target is governed at the same enforcement point as any other request.

  > **Extended 2026-08-03 — extended, not wrong.** This requirement deferred command containment to
  > "the sandbox boundary" and to FR-014 through FR-021, and only the second of those two delegates
  > was specified anywhere in this document: the egress terms had requirements behind them and the
  > sandbox boundary had none. It is now FR-048 through FR-050. Nothing about this requirement
  > changes; the term it delegates to stops being undefined, which matters because **OD-12** moved
  > containment onto that boundary and the enforcement point precisely so that nothing would need to
  > classify a shell command.

**The execution environment boundary**

FR-048 through FR-050 were added 2026-08-03. They are the three terms of constitution Principle IV
bullet 1 that this specification did not previously require, and the bullet's own words are that a
configuration missing any one of its terms does not satisfy it. They are load-bearing rather than
boilerplate: the agent holds command execution (FR-004) inside this environment, and **OD-12**
settled that the shell executes and that nothing classifies shell commands for effect *because*
containment lives at this boundary and at the enforcement point. Each is stated as an observable
property of the environment, not as a mechanism; which mechanism supplies it is the plan phase's
question.

- **FR-048**: The agent's execution environment MUST expose only a declared set of filesystem
  locations, and everything outside that set MUST be neither readable nor writable from inside it —
  the operator's wider host, the runtime's own configuration, and the artifacts and working state of
  any other session included. The declared set MUST be configuration under FR-033 and MUST be stated
  positively: a location is reachable because it was declared, never because nothing excluded it. An
  attempted read or write outside the set MUST fail rather than partially succeed, and MUST be
  recorded in the trace with the rule that produced it, identically to a denial under FR-011. The
  effect-gate rule set of FR-012 and the egress policy of FR-014 MUST lie outside the declared set,
  which is what turns FR-012's "no write path" and FR-014's "cannot reach, modify, reconfigure or
  bypass" into checkable properties of one boundary rather than two separate assertions.
- **FR-049**: The agent's execution environment MUST run under a declared bound on processor time and
  a declared bound on memory, both enforced from outside the environment so that nothing running
  inside it — the runtime, a command the agent composed, or a process that command started — can
  raise, extend or evade them. Exhausting either bound MUST end the session in a named terminal state
  under FR-006 rather than by generic error, MUST leave work already performed counted against
  FR-005's ceilings rather than restarting them, and MUST NOT deny service to anything else running
  on the same host — which is the ordinary self-hosted topology and not a deployment mistake
  (**OD-08**, FR-034). Both bounds MUST be recorded with the deployment identity they apply to.
  **This specification states no default value for either bound.** Nothing in feature 001's evidence
  base bears on what an agent's working set is, so whatever default ships is a configured value and
  not a measurement, and MUST be marked unvalidated wherever it appears externally under FR-043 —
  the same discipline FR-046's detection window and FR-047's staleness ceiling already carry, and for
  the same reason.

  > **Extended 2026-08-03 with a pre-exec barrier — extended, not narrowed. Every clause above is
  > unchanged; what this adds is the moment by which they must already hold.** "Enforced from
  > outside" said nothing about *when*, and a bound that exists from outside but only after the
  > workload is running is not the bound the requirement describes.
  >
  > The session cgroup MUST be created and every bound written before the workload process is
  > created, and the workload MUST NOT execute its first instruction until it is a member of that
  > cgroup. Attaching after spawn leaves a window in which the workload can fork unbounded. A test
  > that spawns, attaches, and then observes the bound holding does NOT demonstrate this, because it
  > never exercises the window; the test MUST show the workload blocked before `execve` and released
  > only after membership is established.
  >
  > The last sentence is the load-bearing one and it is written against a specific way of getting
  > this wrong. Attach-after-spawn passes every assertion an ordinary bound test makes — the bound is
  > present, exhaustion still ends the session in its named terminal state, and **SC-023** is
  > satisfied end to end — because none of those observations is taken during the window. The failure
  > is only visible to a test constructed to sit inside it.
- **FR-050**: No credential that outlives a session MAY be present in, or retrievable from, the
  agent's execution environment. "Does not outlive the run" is a lifetime property and a lifetime is
  not directly inspectable, so this requirement states it as three observable ones and is satisfied
  only when all three hold:
  - **Not present.** No secret value MAY be readable from inside the execution environment in any
    form the code running there can reach — an environment variable, a file inside FR-048's declared
    set, or process state. FR-036 keeps secrets out of model context, emitted artifacts, traces and
    persisted state; none of those four is the environment a shell runs in, and FR-033's environment
    injection delivers configuration to the runtime rather than to the agent's environment. The
    operator's own long-lived provider and target credentials therefore stay outside that environment
    entirely, which is what makes bring-your-own-credentials (FR-032, FR-037) compatible with this
    requirement rather than in tension with it: the requirement is about what the environment can
    read, not about how long the operator's own secrets live.
  - **Bounded.** Whatever authority the environment does hold MUST be bound to the single session it
    was issued for and MUST stop being honoured the moment that session reaches a terminal state
    under FR-006 — including a terminal state reached by crash, by a ceiling under FR-005 or FR-049,
    or by denial. Observably: a value captured from inside the environment during a session and
    replayed after that session has terminated MUST be refused, and the refusal MUST be recorded like
    any other denial under FR-011. A credential that still authorizes anything after its session has
    ended has outlived the run, whatever its nominal expiry says.
  - **Not inherited.** Nothing written inside one session's execution environment MAY be readable
    from another session's, so an environment MUST NOT be reused across sessions carrying anything
    the previous session left in it. A session resumed under FR-007 is the same session continuing
    and is not another one.

**Egress containment**

- **FR-014**: All outbound traffic from the agent's execution environment MUST traverse a single
  enforcement point that the agent cannot reach, modify, reconfigure or bypass. Enforcement MUST NOT
  depend on any policy that lives inside the execution environment.
- **FR-015**: The enforcement point MUST apply a destination allowlist and a method allowlist together
  on the same request, and MUST apply them identically whether the request originated in the runtime
  or in a command the agent composed.
- **FR-016**: Destinations MUST be pinned to specific addresses at configuration time, at
  host-**and**-port granularity. Names MUST NOT be re-resolved per request. Name resolution MUST be
  unavailable from the execution environment or mediated entirely by the enforcement point.
- **FR-017**: ~~Loopback, private, link-local and cloud-metadata addresses MUST be denied even when
  they are reached through an allowlisted host.~~ **The private-address clause was replaced
  2026-08-03 — replaced on that class only, and the link-local class is strengthened rather than
  loosened in the same edit.** ~~The struck sentence's **loopback** clause is carried forward verbatim
  below rather than dropped, because the replacement does not name that class and deleting it here
  would retire a denial nobody decided to retire.~~ **The loopback clause was replaced later the same
  day by a second owner decision, on exactly the terms the private-address clause already had.
  Carrying it forward was right while no decision named it and is wrong now that one does; the
  carried-forward sentence is struck rather than deleted so the denial it stated stays legible.**

  ~~Loopback addresses MUST be denied even when they are reached through an allowlisted host.~~

  The enforcement point MUST deny any destination resolving to a link-local address (including the
  cloud metadata service at 169.254.169.254) unconditionally, with no exemption path. It MUST deny
  any destination resolving to an RFC1918 **or loopback** address other than the single explicitly
  declared target origin; a declared loopback origin is exemptible on the same terms as a declared
  RFC1918 one and on no others. The exemption is keyed to that one declared address and MUST NOT be
  expressible as a range, a prefix, or a configuration toggle. It MUST be **one address in total and
  not one address per exemptible class**: a deployment declares one target origin and therefore holds
  one exemption or none, whichever class that origin falls in.

  > **Why ~~one class~~ two classes gained an exemption and another lost the possibility of one.**
  > *(Written when the private-address clause was the only one replaced. The loopback clause joined it
  > later the same day and the argument below carries over unchanged, because it turns on the origin
  > being single and declared rather than on which class it sits in.)* The struck
  > sentence denied RFC1918 unconditionally, which forbids a pinned upstream on a private address —
  > and that is the ordinary self-hosted topology FR-049 and **OD-08** already require the design to
  > survive, so the requirement as written was unsatisfiable against the deployment shape v1 sells
  > into. The exemption is therefore keyed to **one address**, the origin FR-016 already pins at
  > configuration time, and is deliberately not expressible as a range, a prefix or a toggle: each of
  > those three is a shape in which a single declared exemption becomes a class exemption without
  > anyone editing this requirement. **The link-local clause moves the other way.** 169.254.169.254
  > is inside `169.254.0.0/16` and would be denied by the class rule regardless; it is named because
  > reaching it is credential theft rather than exfiltration, and an exemption path that exists for
  > any reason is one an operator can be talked into using.
  >
  > ⚠️ ~~**One reading is left open rather than settled here, and it is an owner question.**~~
  > **CLOSED 2026-08-03 — the question was put to the owner and the answer was to extend. The
  > description of the gap below is kept unstruck, because it is the reasoning *for* the extension
  > rather than a claim the extension superseded.** A
  > same-host deployment reached at `127.0.0.1` is a plausible reading of the co-located topology
  > **OD-08** describes, and under the ~~text above~~ **replacement wording as first written** it is
  > denied with no exemption while the same deployment one hop away on an RFC1918 address is
  > permitted. ~~The replacement wording names the RFC1918 class only, so extending the exemption to
  > loopback would be this document choosing a scope the decision did not grant. Recorded as a gap,
  > not closed.~~ **The owner granted the scope, on the ground that denying one while permitting the
  > other is a distinction without a security difference.** Which of the two a deployment reaches its
  > application over is a fact about where the operator put the two processes — same host, or one hop
  > away on the private network — and not about how much authority either process holds. Both are one
  > declared, single, non-arbitrary origin that FR-016 already pins at configuration time, and neither
  > is the *arbitrary internal address* the deny exists to prevent. **The link-local clause is
  > untouched by this**, and the containment is carried across whole rather than restated: single
  > address, equality comparison, one constructor, the inexemptible classes decided before the
  > exemption is consulted. **One containment is added that a single exemptible class did not need** —
  > the exemption is one address in total, so a deployment cannot hold a loopback exemption and a
  > private-address exemption at the same time.
- **FR-018**: The enforcement point MUST be able to read the method and path of every request it
  allows, and MUST achieve that without requiring a trust anchor inside the execution environment or
  a certificate pin the operator must maintain. Any traffic it cannot interpret as an individual
  request with a readable method and path — an opaque tunnel, a connection upgraded to another
  protocol, or bytes of another protocol entirely — MUST be denied.
- **FR-019**: Any widening of the destination or method allowlist MUST be an explicit operator action,
  recorded as configuration and subject to the same review as FR-012.
- **FR-020**: Before a target is admitted, its safe-method operations MUST be inspected for operations
  that cause the target to issue outbound requests on the caller's behalf; those operations MUST be
  denied. A target whose operations cannot be inspected MUST fail closed. This property is unmeasured
  on any target (**U-44**) and the requirement is a default rather than a finding. This inspection is
  the second stage of one admission sequence and MUST run after FR-044, because the operation list it
  inspects is the one FR-044's published specification supplies.

  > **Extended 2026-08-03 by FR-051 — extended, not wrong and not narrowed.** Every word of this
  > requirement holds at admission, which is the only moment it was written for. FR-046 then made the
  > served-operation set re-fetchable on a schedule, so the set this requirement inspects is no longer
  > fixed after admission, and an operation added to a still-published specification would have become
  > available to the agent uninspected. FR-051 attaches the same inspection to every set change. The
  > inspection, its fail-closed default, and its unmeasured basis (**U-44**) are unchanged.

  > **Given a procedure 2026-08-03 by FR-056 — given, not changed.** This requirement said what to
  > inspect for and what to do when inspection is impossible, and named **no inspection**, so *"cannot
  > be inspected"* had no truth conditions and the fail-closed clause could never be shown to apply.
  > FR-056 supplies the procedure and its three-valued outcome. Two riders. **The unit of failing
  > closed is the operation, not the target**, which is FR-051's wording rather than this
  > requirement's; the target-level sentence above survives as the degenerate case where every
  > operation is uninspectable, and FR-056 records why the two are one rule. And the confused deputy
  > this requirement is about is **the target issuing outbound requests on the caller's behalf**, not
  > the agent-authority sense the research corpus uses that phrase for — see FR-056, where the
  > difference determines the requirement.
- **FR-051**: Every operation that becomes available to the agent MUST have been inspected under
  FR-020 first, whichever fetch introduced it. FR-020 runs at admission, and FR-046 re-fetches the
  target's published specification on a schedule, so a target that never stops publishing may add an
  operation between two successful fetches — and an admission-only reading of FR-020 leaves that
  operation reachable by an agent although no inspection ever saw it. On every successful fetch the
  system MUST therefore compare the newly fetched set against the last **inspected** set, MUST
  inspect every operation present in the first and absent from the second before it becomes
  available, and MUST fail closed on any operation it cannot inspect, exactly as FR-020 requires at
  admission. FR-047's clause requiring the same comparison when a stale interval ends is this
  requirement's special case and is unchanged by it; what changes is that the ordinary case — a
  re-fetch that succeeds against a target that never stopped publishing — is no longer the one path
  by which an uninspected operation reaches the agent. The confused-deputy property being inspected
  for remains unmeasured on any target (**U-44**): moving the point at which it is checked does not
  measure it, and FR-020's default stands unchanged.

  > **Given a procedure 2026-08-03 by FR-056 — given, not changed.** The comparison this requirement
  > specifies is against the last **inspected** set, which presupposes that "inspected" has truth
  > conditions; until FR-056 it had none. This requirement's operation-level unit of failing closed is
  > the one FR-056 adopts, over FR-020's target-level wording. One consequence worth stating: because
  > FR-056's outcome is recorded per operation, the "last inspected set" is **the set of operations
  > whose recorded outcome is `clean`** — an operation previously found `uninspectable` and unchanged
  > since is not silently re-admitted by a later fetch, and an operation whose *handler* changed is
  > not treated as inspected merely because its specification entry did not.
- **FR-056**: The inspection FR-020 and FR-051 require MUST be a **named procedure over the analysed
  codebase with a three-valued outcome per operation**, and an operation's outcome MUST be recorded
  with the operation. The three outcomes are **clean**, **deputy** and **uninspectable**; **both
  `deputy` and `uninspectable` MUST be denied**, and they are distinguished so that the reason is
  reportable, not so that they are treated differently. The procedure has three steps, each of which
  MUST return a determinate answer or return `uninspectable`:

  1. **Resolve the operation to a handler.** Each operation in the set FR-044 admitted MUST resolve to
     **exactly one** handler symbol in the codebase FR-002 analysed. Zero — an operation served by
     something outside the analysed codebase, such as a proxied upstream — or more than one is
     `uninspectable`.
  2. **Enumerate outbound-request call sites reachable from that handler.** The constructs that count
     as issuing an outbound network request MUST be drawn from a **declared catalogue**, which MUST
     be versioned configuration under FR-012 and reviewable before it takes effect. If the handler's
     reachable call graph contains any call the analyser can classify as neither outbound nor
     not-outbound — dynamic dispatch it cannot resolve, reflection, evaluated source, or a dependency
     whose body is not in the analysed codebase — the operation is `uninspectable`. **An unresolved
     call MUST NOT be read as the absence of an outbound request.**
  3. **Decide destination influence at each enumerated call site.** A call site whose destination is
     fixed at build time or read only from the target's own configuration does not make the operation
     a deputy. A call site whose destination is influenced by any input to the operation makes it
     `deputy`. A call site whose destination the analyser cannot trace to one of those two makes the
     operation `uninspectable`.

  **This is a stated rule set, not a proof, and the system's documentation and interfaces MUST NOT
  describe it as one** — identically to FR-010, and for the same reason: step 2's catalogue is
  enumerated rather than derived, and step 3's question is undecidable in the general case, which is
  why the procedure is required to answer `uninspectable` rather than to answer at all costs.

  > **Added 2026-08-03, because FR-020's fail-closed clause was not decidable and a fail-closed rule
  > with an undecidable trigger fails open in practice — nothing ever meets it.** Three things this
  > requirement settles, and one it deliberately does not.
  >
  > **What the threat actually is, because the name is ambiguous and the ambiguity was doing damage.**
  > [`research/08`](../../research/08-auth-identity-and-secrets.md) §3.1 uses "confused deputy" for
  > the *agent* acting with its own authority on an end user's behalf. **FR-020 is not about that
  > case.** It sits inside the egress block, FR-014 through FR-021, and its subject is the *target*
  > issuing outbound requests on the caller's behalf — the target as the agent's deputy. That
  > distinction decides the requirement: FR-014's enforcement point governs traffic leaving **the
  > agent's execution environment**, and a request the target originates from its own network position
  > never traverses it. So the predicate *"any request the enforcement point cannot attribute to a
  > declared operation"* — decidable, and worth having — **is not a substitute for this inspection**,
  > because the requests this inspection exists to prevent are invisible to the enforcement point by
  > construction. It is already carried by FR-015 and FR-018 for the traffic it does cover. Adopting
  > it here would have replaced an undecidable rule with a decidable rule about something else.
  >
  > **Why an inspection can be decidable when the underlying question is not.** It is decidable
  > because its output space includes `uninspectable`. Each step asks something the analyser either
  > answers or declines, and declining is a determinate answer with a defined consequence. This is
  > the same shape as FR-024's refusal and FR-025's not-verifiable state, and it is the shape
  > [`.cursor/skills/agent-safety-and-sandboxing/SKILL.md`](../../.cursor/skills/agent-safety-and-sandboxing/SKILL.md)
  > describes as classifying at the interception point rather than trusting a classification made
  > upstream of it.
  >
  > **FR-020 and FR-051 disagreed about the unit of failing closed, and the disagreement is now
  > resolved rather than papered over.** FR-020 says *"a **target** whose operations cannot be
  > inspected MUST fail closed"*; FR-051 says *"MUST fail closed on any **operation** it cannot
  > inspect"*. **The unit is the operation.** FR-020's target-level sentence is the degenerate case of
  > the same rule: where the analysis precondition itself fails, step 1 returns `uninspectable` for
  > every operation, every operation is denied, and the target has no callable operation left — which
  > FR-044's admission check already refuses rather than admitting a target that serves nothing. No
  > separate target-level threshold is needed and none is invented here.
  >
  > **What this does not do.** It does not measure anything. **U-44** records that the property is
  > unmeasured on any target, FR-020 is a default rather than a finding, and naming a procedure for
  > an unmeasured property does not measure it. It also inherits
  > [`research/08`](../../research/08-auth-identity-and-secrets.md) §3.1's structural warning from the
  > other direction: authorization lives *above* the layer an analyser decomposes, so step 3 finding a
  > destination "fixed at build time" says nothing about whether the operation should have been
  > callable by this caller at all. That is a different problem, and v1 does not solve it.
- **FR-021**: The runtime MUST ship with its dependencies already resolved and MUST NOT resolve
  dependencies at run time.

**Contract-derived verification**

- **FR-022**: For every reported result, the verifier MUST attempt to recompute the reported quantity
  by a path independent of the one that produced it. Conformance of the request or the response to a
  declared shape MUST NOT by itself be accepted as verification; the failure class that matters is
  conformant end to end and wrong.
- **FR-023**: Every verification check MUST derive from an artifact the target codebase already
  contains — signatures, return types, preconditions, postconditions, invariants, exception classes,
  existing tests, or observable state. A model's assessment MUST NOT be the success signal for any
  result.
- **FR-024**: Where no check of stated precision can be derived for a quantity, the verifier MUST
  refuse rather than fall back to a default tolerance, and MUST name the reason for the refusal.
  This requirement is unchanged by the clarification at FR-025: it is what *creates* the not-verifiable
  state, and FR-025 settles only what the caller then sees.

  **Where precision is stated, pinned 2026-08-03.** A precision is **stated** when it is attributable
  to a **named source artifact**, and the admissible sources MUST be fixed by an **ordered precision
  ladder** with all four of the following properties:

  1. It MUST be **committed before any derivation is written against it**, and MUST be versioned
     configuration under FR-012 — reviewable by the operator before it takes effect, and outside the
     agent's write path.
  2. **Every rung MUST name a source of precision and no rung may name a numeric value.** A ladder
     containing a numeric constant is a default tolerance with extra steps, which is the thing this
     requirement exists to forbid.
  3. **Its last rung MUST be refusal.** There is no rung below the last.
  4. Its admissible sources are exactly the artifact classes FR-023 permits — signatures, return
     types, preconditions, postconditions, invariants, exception classes, existing tests, observable
     state — **together with the target's published specification** (FR-002), which is the independent
     artifact FR-023's derived checks are validated against. **A precision a model proposes is not a
     source**, at any rung, under any provenance.
  5. **A precision declared in the caller's own request is admissible only where ~~it tightens, and
     the ladder MUST evaluate it as a ratchet rather than as a rung it falls to~~ no artifact source
     supplies any precision for that quantity at all — that is, only where the ladder would otherwise
     refuse.** Added 2026-08-03 by **OD-23** as a ratchet; **revised 2026-08-03 by OD-23** to the
     narrower variant that decision recorded as available and not taken, after the ratchet was
     verified inert against the census. The reasoning, the measured effect and what the variant costs
     are in the note below.
     - **The admissibility test, stated explicitly.** For the quantity under check, the verifier MUST
       first determine whether **any** source among property 4's artifact classes supplies a
       precision for it. A caller-declared precision is admissible **only if none does**.
     - **Where any artifact source supplies a precision, the declaration MUST be ignored** — whether
       it is tighter, equal or looser — and the ladder MUST proceed exactly as if the declaration were
       absent, taking the artifact-derived rung it would have taken anyway. The declaration MUST NOT
       displace, relax or override an artifact-derived comparison under any circumstance. **A
       caller-declared precision may never be the reason a quantity is checked less strictly than an
       artifact source permits.**
     - **Where no artifact source supplies one, the declaration is admissible**, and the verifier MUST
       record the declaration and its source text as the precision's provenance. This is the only
       circumstance in which a declaration converts what would otherwise be a refusal into a checked
       quantity, and the resulting state is **provisional** and never plain verified.
     - **Where it is admitted it MUST still be marked provisional** under property 6. The
       admissibility test governs *where* the declaration may act; it does not change its
       *provenance*, and under this variant the field is by construction one for which no independent
       artifact exists — so property 6 is not a formality here, it is the only disposition
       constitution Principle I leaves available.
     - **An ignored declaration MUST be disclosed on the result, not silently dropped.** Where a
       declaration was present and an artifact source displaced it, the quantity is **checked at the
       artifact rung** — it does not refuse — and the result MUST record that a declaration was
       present and was not used. Under this variant a declaration can no longer be the *cause* of a
       refusal, which is the substantive difference from the superseded ratchet: a quantity refuses
       only where no artifact source and no usable declaration exists, and that refusal is governed by
       the closing sentence of this requirement, which already requires the silent sources be named.
  6. **A verification whose precision came from the caller's request MUST be marked provisional** on
     its own provenance, under the same rule D-17 and constitution Principle I apply to every derived
     field.

  When a quantity's applicable rung is the refusal rung, the verifier MUST refuse and MUST name
  **which sources were consulted and found silent**, not merely that it refused.

  > **Property 5 added 2026-08-03 — `OD-23`, and the owner's premise was confirmed while the
  > decision's cost estimate was not. Both are recorded here because the second one is a live cost
  > and not a quibble.**
  >
  > **⚠️ Property 5 revised 2026-08-03, later the same day, by the same decision — `OD-23`. Read the
  > whole of this note as the record of how the requirement got to where it is; the *rule in force* is
  > the property above and nothing in this note overrides it.** The ratchet was verified inert against
  > the census — the reasoning is three paragraphs down and it is the decision's own — and the owner
  > took the narrower variant this note recorded as available and not taken. **The two tests are
  > complementary and only one has a non-empty domain**: the ratchet needs a non-request comparand to
  > compare against, the rung is only ever reached where none exists, so the ratchet could never fire.
  > **Where a comparand does exist the variant is the stricter of the two** — the ratchet would admit
  > a declaration that tightened it, the variant ignores the declaration outright — so nothing the
  > ratchet protected was relaxed to make room for this.
  >
  > **What the decision fixes.** The request rung was request-derived on a product sold on
  > contract-derived verification, and — as written before this property — it let a caller weaken
  > their own verification by asking for fewer decimal places. ~~Requiring it to tighten removes that
  > vector completely, and removes it structurally rather than by review.~~ **The variant removes that
  > vector by domain restriction rather than by direction test**: where an artifact source supplies a
  > precision the declaration is ignored outright, and where none does there is no check to weaken
  > because the alternative is refusal, which checks nothing. The vector is absent **by construction**
  > rather than by comparison, which is why the ratchet was replaced rather than relaxed.
  >
  > **The premise checks out.** The claim that the request rung was the sole catcher of the three
  > sub-one-percent near-misses is **confirmed** against the harness that built the ladder.
  > [Finding 015](../001-discovery-validation/findings/015-verifier-vs-judge-not-run.md) records that
  > all three are **one submission** — `3.23` against a recomputed mean of `3.201754`, a relative
  > error of 0.882%, answered by the same arm at three battery versions — and that its projection is
  > the **sole** entry on the request rung, checked at the two decimal places the request text asked
  > for. The harness's own `derivation-rules.md` says the near-misses are caught "by exactness, not by
  > a tolerance"; **that sentence is true of the ladder in general and false of these three**, and it
  > was narrowed on 2026-08-03 in the harness README and in finding 015 for exactly that reason. A
  > mean is not a count.
  >
  > **The cost estimate does not, and this is the finding the revision acts on.** ⚠️ **On the one
  > census available, the ratchet did not preserve that catch — it lost it.** Two facts
  > combine. **The ladder takes the first rung it reaches**, so the request rung is *only ever*
  > reached when no artifact source applies — which means the comparand the ratchet asks for is empty
  > in precisely the case the ratchet can fire. And the one declaration ever measured was
  > **looser** than the alternative it would be compared against: two decimal places admits `3.20`
  > against a true `3.201754`, where exact comparison rejects it. So the declaration does not tighten,
  > it is ignored, and the quantity refuses. ~~**The census moves from seventeen refusals of 61 to
  > eighteen, and the three near-miss records go with it** — from detected to not verifiable.~~
  > **Superseded by the revision.** Under the variant the declaration is admissible — its stored
  > derivation records that no artifact source supplies a precision for that quantity — so it does not
  > move, **the census stands at its as-measured 17 refusals of 61**, and the three near-miss records
  > stay **detected**. The figure is counted from the harness's own rung assignments in
  > `c2_derivations.json` rather than carried from prose.
  >
  > **What that does and does not mean.** It is not a detection *failure*: a refused quantity is
  > returned not verifiable under FR-025 with a named reason, which is the honest state and is the
  > whole reason the last rung is a refusal. It is a real loss of *discriminative* capability, and it
  > is the numeric half of the surviving discriminative set that
  > [finding 015](../001-discovery-validation/findings/015-verifier-vs-judge-not-run.md) says a strict
  > reader would lose. **The corpus already anticipated this outcome and named it**: that finding's
  > Amendment B2.2 invited a strict reader to discount the request rung, and ~~property 5 is the
  > product accepting the invitation~~ **the ratchet was the product accepting the invitation; the
  > variant declines it, and keeps the numeric half of the discriminative set on the record as
  > provisional rather than losing it**.
  >
  > **~~One narrower alternative exists and is recorded rather than taken, because taking it is an
  > owner act.~~ The narrower alternative recorded here has been taken — 2026-08-03, and it is now
  > property 5.** Admitting a declaration where no artifact source supplies *any* precision — on the
  > ground that there is no check there to weaken, only a refusal to convert — keeps the catch
  > and is stricter than the ratchet everywhere a comparand exists. ~~It is not taken here because it
  > is exactly the residual vector OD-23 names: converting a refusal into a caller-chosen verified
  > state is what FR-025 forbids in substance, and the census's single instance would be the whole of
  > the evidence for permitting it.~~ **The residual vector is real and is not waved away.** A caller
  > does obtain an affirmative, at a precision they chose, for a quantity no artifact source can pin,
  > where the ratchet would have refused. Three things bound it. FR-025 forbids **substituting a
  > default tolerance to manufacture a verified state**, and a declaration attributable to a named
  > source is not a default tolerance — property 2 already forbids the ladder holding a numeric
  > constant, and that is untouched. The state produced is **provisional**, never plain verified, so
  > no consumer may read it as contract-derived. And the comparison it displaces is a **refusal**,
  > which checks nothing, so the affirmative cannot be less discriminating than what it replaced.
  > What is genuinely given up is the *honesty of the non-answer*: a `not verifiable` becomes an
  > affirmative that can be wrong, and property 6's marking is what carries that.
  >
  > **Why property 6's marking is kept, and why the variant makes it matter more rather than less.**
  > The two govern different failures. Property 5 governs *where the declaration may act*. Marking
  > governs *provenance*, and an admitted precision is still supplied by the party being verified —
  > constitution Principle I at v1.1.0 requires a derived field validated against an artifact its
  > own derivation did not produce, or marked provisional with provenance and confidence. Under the
  > variant, *no independent artifact exists* is the **premise of admissibility itself**, so marking is
  > not one of two available dispositions here — it is the only one. ~~The residual failure is also
  > real and points the other way from the one property 5 closes: a declaration **tighter** than the
  > quantity genuinely supports produces a **false alarm**, not a missed fault, and SC-005 scores a
  > false-alarm rate of no worse than 1%.~~ **That sentence was sound for the ratchet and is struck
  > because it is not sound for the variant.** The ratchet admitted only tightenings, so over-tightness
  > was its only residual. The variant admits a declaration **whatever its direction**, so a second
  > residual appears: a declaration **looser** than the quantity genuinely supports lets a fault
  > smaller than the declared granularity pass as verified — a **missed fault**, not a false alarm.
  > It is not hypothetical; the one declaration ever measured was the loose kind and caught its
  > near-miss only because `3.23` and `3.20` differ at two decimal places. **Both directions are
  > scored by SC-005**, which the variant returns to a testable state by putting the admitted quantity
  > back into the denominator: a missed fault counts against the **95%** detection rate, a false alarm
  > against the **1%** false-alarm rate, and while the quantity refuses neither is scored at all.
  > Retiring the marking would leave that unattributable, and would be the "a safeguard that can no
  > longer fire reads exactly like one that has been satisfied" failure this corpus has recorded
  > before — a failure **the ratchet had itself become an instance of**, its admissibility set being
  > empty by construction.

  > **Pinned 2026-08-03 against the one instance of this mechanism that was ever built and measured,
  > rather than against a plausible reading. The reason it is a ladder and not a place is a
  > measurement, and it is the opposite of the obvious answer.**
  >
  > The obvious pin is *"precision is stated in the target's published specification"*. **On the only
  > target this was ever run against, that source was empty**:
  > [finding 015](../001-discovery-validation/findings/015-verifier-vs-judge-not-run.md) records that
  > the target declared **no numeric precision anywhere** — no `multipleOf`, no numeric `format`,
  > across **243** component schemas — so the instruction to compare *"at the schema's declared
  > precision"* had no referent and was amended. Pinning to the published specification would have
  > pinned this requirement to a source measured to be silent, and every quantity would refuse.
  >
  > **What was built instead is the ladder, and it is prior art in this corpus rather than a design
  > proposed here**: a **six-rung** ladder committed in the harness's `derivation-rules.md` before any
  > derivation was written, re-inspected for finding 015 and confirmed to contain **no numeric
  > constant**. Its census over 61 requests — **28** integer-closed exactness, **9** text or set
  > identity, **6** the application's own serialisation, **1** a precision the request declared, and
  > **17** refused — is what the four properties above generalise. Property 2 and property 3 are not
  > stylistic: together they are why *no tolerance was chosen, and so none could be fitted to the
  > corpus*, which is the whole reason the mechanism's detection figures mean anything.
  >
  > **What this does to SC-005, stated because SC-005's figures are scored against whatever this
  > resolves to.** A ladder whose last rung is refusal partitions any corpus into quantities it can
  > check and quantities it refuses, and **a fault injected into a refused quantity cannot be
  > detected — only refused**. The refusal share is therefore a property of the corpus and the target
  > jointly, and in the one census available it was **17 of 61**, which is far too large to leave
  > implicit in a detection rate. SC-005's denominator is stated at SC-005 accordingly; the
  > percentages there are unchanged.
  >
  > **Updated 2026-08-03 for property 5 (`OD-23`), then updated again the same day for its revision.**
  > The census above is a measurement and stands as taken. ~~What changed is the ladder it was taken
  > from: the request rung is now a ratchet, its one measured entry does not tighten, and **the ladder
  > as now specified would refuse eighteen of those 61 rather than 17**. The refusal share therefore
  > rises, which is the intended shape of the decision and not a surprise —~~ **Under the ratchet the
  > single request-declared entry moved to refusal and the count rose. Under the revised property 5 it
  > does not move: that entry's own stored derivation records rung P1 empty on this target and the
  > application's serialisation inapplicable, so no artifact source supplies a precision for it, which
  > is exactly the variant's admissibility condition. The ladder as now specified refuses 17 of those
  > 61 — the as-measured figure, and the ladder and the census agree again.** Counted from the rung
  > assignments in `harness/verifier-vs-judge/c2_derivations.json`, not carried from prose.
  > SC-005's denominator *rule* is unchanged throughout, because it was already
  > written as "quantities the ladder does not refuse" rather than as a number. The figure that must
  > move with it is the one SC-005 requires be **reported beside** the rates.
- **FR-025**: Every reported result MUST carry exactly one of three states — verified, failed
  verification, or not verifiable — and the state MUST be visible to the caller. A result the verifier
  could not verify MUST be **returned to the caller carrying the not-verifiable state, together with
  FR-024's named reason**. Withholding it, substituting a default tolerance to manufacture a verified
  state, or presenting it in a form a caller could mistake for verified are all prohibited. The three
  states MUST be distinguishable by a consuming system and not only by a human reading prose.

  > **Authorising decision named 2026-08-03 — the requirement is unchanged.** Returning rather than
  > withholding is **OD-19**, taken at this document's clarify session on 2026-08-03 and recorded in the
  > decision log retroactively on the same day. FR-024 is untouched by it and is what produces the
  > not-verifiable state; OD-19 settles only what the caller then sees, and pairs the disposition with
  > the measurement at FR-045.
- **FR-026**: Every derived contract and every derived check MUST carry, as data, the rule that
  derived it, the source symbol and file it came from, the analyzer version, a content hash, and its
  validation status. A derived check MUST be validated against an artifact its own derivation did not
  produce; where no independent artifact exists it MUST be marked provisional and MUST NOT be
  presented as validated.

**Drift detection**

- **FR-027**: The system MUST maintain the source-derived artifact and the deployment-derived
  artifact as two independently versioned things, and MUST detect drift in each of them separately.
- **FR-028**: A source change that invalidates a derived contract MUST be detected in the same
  automated check run as the change that caused it.
- **FR-029**: A change in what the deployment serves MUST be detected while the source is unchanged.
  A drift check MUST be invocable **manually, on demand, for either clock, at any time** — this mode
  is always available and is not configurable away. A drift check MUST **also** be triggerable
  automatically, and **at least one automated trigger MUST be configurable** rather than imposed:
  the product MUST NOT ship a single automated mechanism as the only one available.

  > **Authorising decision named 2026-08-03 — the requirement is unchanged.** That drift checking is
  > *both* manual and automatic rather than one or the other is **OD-20**, taken at this document's
  > clarify session on 2026-08-03 and recorded in the decision log retroactively on the same day. It
  > authorises FR-046's default trigger as well, and it supplies no figure: FR-046's interval and
  > window remain configured defaults bound to FR-043.
- **FR-046**: The **default** automated trigger for a deployment-drift check is a **scheduled re-fetch
  of the target's published specification**, run by a scheduler the system ships, requiring no event
  from the customer's deployment pipeline, no phone-home, and no outbound request to any destination
  other than the target. Its **default interval is five minutes**, and the **stated detection window
  is one interval plus the duration of one check** — so under default configuration a deployment
  change is detected within approximately five minutes of occurring. Interval and window are
  configuration and MUST be recorded with the deployment identity they apply to. At least these
  additional triggers MUST be configurable in place of, or alongside, the default: a **deployment
  event emitted by the customer's own rollout mechanism**, which is the lowest-latency trigger where
  a customer can emit one and MUST NOT be assumed available; and a **re-check at session start**.
  The per-operation path-level reachability precondition failing in front of a user is a backstop
  that MUST be recorded as a drift signal, and MUST NOT be relied on as a trigger design. The stated
  detection window is a **configured default and not a measurement**: FR-042 measures the achieved
  window against it, and until that measurement exists the window MUST be marked unvalidated wherever
  it appears externally, under FR-043. **The authorising decision is OD-20**, jointly with FR-029.
- **FR-030**: On detected drift the affected operation MUST be disabled and surfaced loudly, and
  unaffected operations MUST keep working. Continuing to serve a drifted operation is prohibited;
  stopping the whole runtime for one drifted operation is not required.

  > **Narrowed 2026-08-03 by FR-047 — narrowed, not wrong and not superseded.** This requirement
  > governs an operation *observed* to have drifted, and it remains true and complete for that case.
  > It was written before a published specification was an admission criterion (FR-002) and before
  > anything re-checked one on a schedule (FR-046), so it gave no rule for the case where the
  > observation channel itself fails and no individual operation is observed at all. FR-047 supplies
  > that case as a specialization rather than an exception: below FR-047's staleness ceiling there is
  > no affected operation to disable and the set is marked stale instead; at the ceiling every
  > operation is affected and this requirement applies to all of them, unchanged. What shrinks is
  > what may be inferred from the disable-the-affected-operation clause, not its truth. **The
  > authorising decision is OD-21** *(citation added 2026-08-03 when OD-21 was recorded; the narrowing
  > itself is unchanged)*.
- **FR-031**: Every drift signal MUST state which of the two clocks moved, the artifact versions
  before and after, and the deployment identity it applies to.

  > **Narrowed 2026-08-03 by FR-047 — narrowed, not wrong.** Where the drift signal is a *failed
  > re-fetch* under FR-047 there is no "after" artifact version to state, because no artifact was
  > obtained. In that one case the after term is the specification state found, named from FR-044's
  > four-state classification, together with the timestamp of the last successful fetch. Every other
  > term of this requirement is unchanged, and no other drift signal is affected. **The authorising
  > decision is OD-21** *(citation added 2026-08-03 when OD-21 was recorded; the narrowing itself is
  > unchanged)*.
- **FR-047**: A target admitted under FR-002 whose published specification later becomes absent,
  unreadable or empty MUST have that condition detected by the same check as FR-046, MUST have it
  reported as deployment-clock drift under FR-031, and MUST NOT have it read as a deployment that
  serves nothing. For the interval during which an admitted target is no longer publishing, the
  runtime MUST continue to operate on the **last-known-good served-operation set, marked stale**,
  and MUST deny once a **staleness ceiling** measured from the last successful fetch is crossed.
  Specifically:
  - **Entering the stale state.** On the first re-fetch returning any of FR-044's three
    non-admissible states, the served-operation set MUST be marked stale rather than discarded, and
    the drift signal of FR-031 MUST be raised on that same run. FR-010 continues to resolve calls
    against that set; that is the risk this disposition accepts, and the ceiling is what bounds it.
  - **What the caller sees.** Every result produced while the set is stale MUST carry — on the same
    caller-visible result record that carries FR-025's verification state, and under the same
    discipline, machine-distinguishable by a consuming system rather than by a human reading prose —
    a marking that the served-operation set was stale, the age of that set, and the specification
    state last found. That marking MUST be a field separate from the verification state and MUST NOT
    become a fourth value of it: a result may be verified and stale at once, and FR-025's three
    states remain exhaustive and mutually exclusive.
  - **The ceiling.** The **default staleness ceiling is fifteen minutes from the last successful
    fetch** — equivalently, three consecutive failed re-fetches under FR-046's default five-minute
    interval, though the ceiling is normatively wall-clock so that lengthening the interval does not
    silently widen it. It is a **configured default and not a measurement**: nothing in feature 001's
    evidence base bears on it, no threshold is pre-registered, and it MUST be marked unvalidated
    wherever it appears externally, under FR-043. Ceiling and interval MUST be recorded with the
    deployment identity they apply to, exactly as FR-046 requires of its own interval.
  - **Crossing the ceiling.** Once the ceiling is crossed the last-known-good set MUST NOT be
    served: every call against that target MUST be denied under FR-030, the denial MUST name the
    stale set and its age as the rule that produced it under FR-011, and any session in flight MUST
    terminate in a named terminal state under FR-006 rather than by generic error.
  - **Leaving the stale state below the ceiling.** On the first re-fetch returning a published,
    readable, non-empty specification, the newly fetched set MUST replace the last-known-good set
    and the stale marking MUST clear — but the difference between the two sets MUST itself be
    evaluated for deployment drift under FR-027 and FR-030, because the deployment may have moved
    while it was unobserved and a re-fetch that merely succeeds is not evidence that nothing changed.
    Any operation present in the newly fetched set that was not in the last inspected set MUST be
    inspected under FR-020 before it becomes available.
  - **Recovering from past the ceiling.** Crossing the ceiling MUST NOT be terminal and recovery
    MUST NOT require the operator to restart the runtime. Recovery MUST, however, run the full
    admission sequence — FR-044 then FR-020 — rather than the drift check's re-fetch alone, and MUST
    record a new admission decision: past the ceiling the system holds no founded belief about what
    the deployment serves, which is precisely the state FR-044 exists to gate.

  **Relation to FR-030 — a specialization, not an exception.** FR-030 disables the *affected
  operation*, and an operation is affected when it has been observed to drift. A failed re-fetch
  observes no operation; what it loses is the freshness of the whole set, not the validity of any
  member, so reading FR-030's disable clause as covering the failure of the observation channel
  itself over-reads it. Below the ceiling nothing is yet known to have drifted, FR-030 has no member
  to disable, and FR-047 marks the set instead. At the ceiling the set stops being a last-known-good
  belief and becomes an unfounded one, every operation *is* affected, and FR-030 applies unchanged
  to all of them. FR-030 is marked accordingly.

  **The authorising decision is OD-21**, recorded 2026-08-03 in
  [`plan.md`](../001-discovery-validation/plan.md) — retroactively, and later than its three siblings
  OD-18, OD-19 and OD-20, because recording it was an owner act rather than part of the propagation
  that wrote those three. *(Citation added when OD-21 was recorded. This requirement's text is
  unchanged: what it lacked was a decision to point at, not a decision.)* OD-21 also authorises the
  narrowings this requirement makes at **FR-001**, **FR-030** and **FR-031**, and **SC-021** measures
  it.

**Deployment, credentials and providers**

- **FR-032**: Every component — analysis, the enforcement point, the runtime and the credentials —
  MUST be able to run entirely inside the operator's own boundary, and no target data or credential
  MUST be required to leave it for the product to function.
- **FR-033**: Configuration MUST reach the system by environment injection against a declared,
  validated schema, and startup MUST fail loudly on a missing or invalid required value. No
  operator-specific path, hostname, address or credential MAY be written into any emitted artifact.
- **FR-034**: The boundary between the analysis stage, the runtime and the target MUST be explicit in
  configuration even when all three run on one host. Co-location MUST NOT be assumed anywhere.
- **FR-035**: Tenant identity and deployment identity MUST be first-class data on every derived
  artifact and every trace, and storage MUST be namespaceable, even while exactly one tenant and one
  deployment exist.
- **FR-036**: Model-provider credentials and target credentials MUST be held in two separate planes.
  No secret value MAY appear in model context, in an emitted artifact, in a trace, or in persisted
  state.
- **FR-037**: The runtime MUST operate against multiple independent model providers with tool calling,
  selected by configuration, with no provider-specific behaviour in its core path. Provider-opaque
  reasoning state MUST be a first-class value on every turn, round-tripped verbatim, never dropped and
  never merged across providers.

**Observability**

- **FR-038**: ~~From the first shipped capability, every session MUST produce one trace record per
  executed node carrying a versioned node identity, a typed terminal, the routing decision together
  with the inputs its predicate saw, precondition and postcondition results, an explicit distinction
  between a retry and a repair, and per-node cost.~~ **Rewritten 2026-08-03 against a v1 subject —
  rewritten, not narrowed and not extended. Six of the struck text's terms named a graph v1 does not
  emit, and the note below records which, what replaced each, and the one part of this that is a
  constitutional question rather than a specification one.**

  From the first shipped capability, every session MUST produce **one trace record per span**. A
  **span** is one of a **declared closed set of kinds** — a model call, a tool call, an egress
  decision, a filesystem decision, a state transition, a verification, or a drift check — and a span
  of an undeclared kind MUST NOT be written. Every span MUST carry:

  - **its kind**, drawn from that set, and **its position in the session** — which session, which
    turn, and where within that turn — sufficient to order every span in a session totally, without
    reference to a clock;
  - **the versions of every artifact in force when the span ran**, drawn from FR-054's
    content-addressed set, together with the tenant and deployment identity FR-035 requires. This is
    the versioned identity available to a system that versions configuration rather than nodes, and
    it is what makes an attribution reproducible after the configuration has moved;
  - **a typed outcome** drawn from a declared set, and, for the span on which the session ends, the
    session's named terminal state under FR-006. A generic error MUST NOT be a span outcome, for the
    same reason FR-006 forbids it as a terminal state;
  - **for every egress and filesystem decision, the decision together with the inputs the rule that
    produced it matched on** — the resolved effect tier, the **rule identifier** (FR-011, FR-048),
    and the method, path and served operation the rule matched or failed to match. This MUST be
    recorded for **every** such decision and not only for denials, because a permit resolved by the
    wrong rule is the case an attribution has to be able to find;
  - **precondition and postcondition results** — FR-046's per-operation path-level reachability
    precondition, and the verification state under FR-025 with FR-024's named reason where it refused;
  - **an explicit distinction between a retry and a repair**; and
  - **per-span cost**, and the running total against each of FR-005's four ceilings as at that span.

  > **Why this was rewritten, what the v1 subject is, and the part that is not this document's to
  > settle.** The struck text is constitution Principle VI's field list transcribed, and it was
  > correct for the product the constitution describes — one that *emits* a multi-agent system.
  > **OD-09 removed that product from v1**, and this specification records the consequence twice
  > already: the Principle II deviation record states that *"v1 emits no agent system — it is one
  > runtime with one agent"*, and [`data-model.md`](./data-model.md) §4 lists *a node, edge or
  > topology entity* among what is deliberately absent. **Six terms of the struck text therefore had
  > no v1 subject**: *executed node* as the record's unit, *versioned node identity*, *routing
  > decision*, *the predicate whose inputs are recorded*, the *conditional edge* Principle VI attaches
  > that predicate to, and *per-node cost*. Nothing in the specification named a substitute for any of
  > them, which made the requirement unbuildable rather than merely loose.
  >
  > **The v1 subject is the span, and it was already the unit in the downstream contract rather than
  > invented here** ([`contracts/trace-record.md`](./contracts/trace-record.md)). The substitutions,
  > term by term: *node* → **span**, the finest unit v1 executes that has an outcome and a cost;
  > *versioned node identity* → **the artifact versions in force**, because what varies between two
  > runs of the same v1 code path is the configuration, not a node version; *routing decision on a
  > conditional edge* → **the egress or filesystem decision with its rule identifier and matched
  > inputs**, which is the only place v1 branches on a predicate over data, and which FR-011 already
  > required for denials only; *per-node cost* → **per-span cost**. *Typed terminals*, *precondition
  > and postcondition results* and the *retry-versus-repair distinction* had v1 subjects already and
  > are carried through unchanged.
  >
  > ⚠️ **The import is a hazard for any later evaluation, and it has already caused one. Read this
  > before scoring anything against this requirement.** The subject above was taken *from*
  > [`contracts/trace-record.md`](./contracts/trace-record.md), so this requirement and that contract
  > share vocabulary by construction rather than by agreement. **Any instrument that measures
  > term overlap between the two is therefore measuring the repair and not the artifact.** That is
  > not hypothetical: the citation advisory scored the *pre-fix* state of that contract against the
  > *rewritten* text of this requirement and appeared to rank it **third of 57**, where against the
  > contemporaneous requirement text — the only state in which the defect it was detecting was ever
  > live — it ranks **tenth of 55** and clears no plausible cutoff. The tool's other known positive,
  > FR-055 against `artifact-versioning.md`, is byte-identical at both revisions and is clean; this
  > one is not, which is why the advisory finds one of its two known defects rather than two.
  > [Finding 017](../001-discovery-validation/findings/017-evaluation-contemporaneity.md) records the
  > account in full, and the transferable half is that **reconstruction has to cover every side of
  > the comparison** — checking the contract out of version control and reading the requirement from
  > the working tree produces a real number, from real historical text, with a revision quoted beside
  > it, and it is contaminated. This clause exists so a future evaluation does not have to rediscover
  > that.
  >
  > ~~**What this does not do, stated because a substitution is easy to read as a discharge.** It does
  > not decide whether Principle VI is *satisfied* by the substitution.~~ **CLOSED 2026-08-03 by the
  > constitution amendment at v1.3.0 (OD-22). The paragraph below was accurate when written and the
  > state it described has moved; it is struck rather than deleted because it is the reasoning the
  > amendment acted on.** ~~**Principle VI's terms do
  > presuppose a graph** — its field list opens *"Every emitted system MUST produce… one span per
  > node"*, which has no v1 subject on the same scope argument that disposes of Principles II, III
  > and VII, while its ship gate — *"a capability that cannot be attributed to a versioned node MUST
  > NOT ship"* — carries no such scope and on a literal reading blocks every v1 capability. Principle
  > VI nonetheless carries **no deviation record**. **That is a constitutional problem and not a
  > specification one**, its remedies are owner acts, and it is set out clause by clause in the
  > Dependencies mapping and carried in
  > [`checklists/requirements.md`](./checklists/requirements.md) rather than decided here.~~
  >
  > **What replaced it, and the one thing this requirement now owes that it did not before.**
  > Principle VI is restated over a **traced unit** whose kind is tier-relative; v1's declared unit
  > is the span, and the closed seven-kind set above is what the amendment means by a *declared
  > closed set of unit kinds*. Every term of this requirement maps onto an amended term rather than
  > substituting for a graph-bound one, so the substitution note above is now a record of how the
  > requirement was derived rather than a caveat on whether it counts. **The amendment adds one
  > obligation this requirement already meets and one it must not lose:** unit identity and artifact
  > version are now *two* obligations rather than the single phrase *"versioned node identity"*, and
  > this requirement satisfies both only because it carries **kind and position** as well as **the
  > versions in force**. Dropping either half would leave it compliant with the superseded wording
  > and non-compliant with the current one.
  >
  > ⚠️ **One place where the amended principle now asks for more than this requirement enumerates,
  > recorded here rather than resolved, because resolving it is a change to what gets built.** The
  > superseded field list required *the routing decision with its predicate inputs* **for every
  > conditional edge** — a graph term with a graph scope. The amendment generalises it to **every
  > decision that selected among alternatives**, carrying the decision, the inputs its predicate
  > matched on, and the identity of the rule or edge that produced it. That generalisation is what
  > makes the clause unit-neutral, and it is also **wider than the fourth bullet above**, which
  > enumerates **egress and filesystem decisions only**. The gap is the **`state_transition`** span
  > kind: a transition that selected among possible next states is a decision among alternatives on
  > the amended reading, and this requirement does not currently ask it to carry the predicate inputs
  > or the identity of the rule that produced it. **Two honest readings exist and neither is picked
  > here.** If v1's state machine is fully determined by the prior state and the typed outcome
  > already recorded, then nothing selected among alternatives, the transition is derivable from
  > fields already present, and there is no gap. If it consults anything else — a retry budget, a
  > ceiling, a policy result — then the amended principle asks for those inputs and this requirement
  > does not. **The narrower requirement does not license the narrower behaviour**: the constitution
  > binds directly, so where the two differ, the principle governs.

**Evidence obligations**

- **FR-039**: For every result the verifier evaluates, the system MUST also record the verdict of a
  general-purpose model judge run in shadow over the same trace. The judge's verdict MUST NOT affect
  what the caller sees, what the gate permits, or any other behaviour.

  > **Scoped 2026-08-03 — a reading recorded, not a change of behaviour.** Constitution Principle I
  > requires that **where a model must judge**, the judgement be pairwise with order-swapping,
  > calibrated against human labels, and reported as an estimate. This requirement introduces a model
  > judge and requires none of the three, which is compliant under exactly one reading of the clause:
  > that it governs judges **in the success path** — the ones the principle's surrounding prohibition
  > is about, whose verdict decides whether something succeeded — and that this judge is outside that
  > path by construction. It is a measurement instrument pointed at the verifier; FR-040 reads its
  > output as data about the verifier's margin, and nothing reads it as a verdict about a result.
  > **The scope of the reading, stated precisely**: the clause is not satisfied here, it does not
  > apply here, and it applies in full to any model judgement that can change what the caller sees,
  > what the gate permits, or any other behaviour. On the alternative reading — that the clause
  > governs any model judgement anywhere — FR-039 is non-compliant with a NON-NEGOTIABLE principle,
  > which is why the reading is stated in this specification rather than left to be inferred at the
  > Constitution Check.
  >
  > **What changes if the shadow judge ever gains influence.** It moves into the success path and the
  > clause binds in full: pairwise evaluation with order-swapping, calibration against **human**
  > labels, and reporting as an estimate would all become preconditions of shipping it, and the
  > change would be a change to a NON-NEGOTIABLE principle's surface rather than a feature toggle.
  > The calibration labels do not exist: the human adjudication pass over the frozen oracle negatives
  > was never performed and a model performed the pass standing in for it (Open Risks), so the work
  > that precondition names is unstarted rather than pending. FR-052 carries that as a standing
  > requirement, and FR-040's third branch — a judge no better than chance triggering a
  > constitutional prohibition on model judges in the success path — is the pre-registered outcome
  > that would close the question in the other direction.
- **FR-052**: No model **judgement about whether something succeeded** — a verdict on a result's
  correctness, on its verification state, or on what the effect gate should permit — MAY influence
  what the caller sees, what the gate permits, or any other behaviour of the system. This governs
  model judgements, not the agent's own operation: the agent is a model and choosing which operation
  answers a question is what it is for, which is precisely why the thing that decides *whether the
  answer was right* may not be one (FR-022, FR-023). This requirement is the standing form at the
  system's edge of the rule FR-023 states per result, and it is what keeps FR-039's judge a
  measurement instrument rather than a component. Any change that would give a model verdict influence over behaviour MUST first satisfy
  all three of constitution Principle I's conditions — pairwise evaluation with order-swapping,
  calibration against human labels, and reporting as an estimate — and MUST be reviewed as a change
  touching a NON-NEGOTIABLE principle. Producing the human labels is a precondition of that change
  and not a formality attached to it, because none exist. Until such a change is made and reviewed,
  the boundary is enforced by construction and MUST be testable as one: the caller-visible result
  record and every gate decision MUST be identical whether the shadow judge agreed with the verifier,
  disagreed with it, or did not run at all.
- **FR-040**: The system MUST report the verifier's marginal detection over the shadow judge with the
  pre-registered gate applied unchanged and all three of its branches intact: a margin at or above ten
  percentage points makes the verifier a headline capability; a smaller margin makes it an internal
  detail; and a judge whose discrimination is no better than chance triggers a constitutional
  prohibition on model judges in the success path, independently of what the verifier scored.
- **FR-041**: Before any write capability ships, the effect gate's read-only precision MUST be measured
  against a labelled corpus of real target operations, against a threshold pre-registered for a
  per-call gate. The threshold from the superseded per-tool gate MUST NOT be inherited by default.
- **FR-042**: Before drift detection is described anywhere as a product differentiator, its detection
  rate, false-alarm rate and detection latency MUST be measured on both clocks against a design
  pre-registered before the measurement runs.
- **FR-043**: Every external claim about the product MUST trace to a measurement or be marked
  unvalidated. In particular: no claim of capability advantage for an application-specific tool
  surface; no claim that synthesis is safer; no cost figure without its basis and its scope; and no
  use of the word "provably" for effect resolution.
- **FR-045**: The system MUST measure and report the **share of reported results returned in the
  not-verifiable state**, broken down by FR-024's named refusal reasons, over each reporting window.
  No threshold is pre-registered for this share, because nothing in the evidence base estimates it
  and a threshold invented here would be the inherited-number failure this corpus catches elsewhere;
  the report is an owner review input, and the share is what decides whether FR-025's disposition was
  the right one. Until the first report exists, the share MUST be described as unmeasured wherever
  the product's verification coverage is described, under FR-043. **The obligation to measure the
  share, rather than to assume it, is the second half of OD-19**; the first half is FR-025's
  disposition, and the decision pairs them deliberately.

  **The reporting window, stated 2026-08-03. Its length is deferred to the owner exactly as the
  threshold is; its surface is not deferred and is stated here.** This requirement measured a share
  *"over each reporting window"* and defined neither term of that phrase. The two gaps had different
  causes and get different answers.

  - **Length — deferred, and deferred explicitly rather than by omission.** The reporting window
    MUST be **required configuration** under FR-033. **This specification states no default value for
    it**; an unset window MUST make startup fail loudly, naming what is missing, and MUST NOT be
    treated as unbounded, as a single window covering all of time, or as a figure this specification
    invented. This is the plan's **Q-10** treatment — the one FR-005's four ceilings and FR-049's
    bounds take — and not FR-047's, because there is no evidence base to draw a default from and a
    default nobody has checked would still be a number the product invents. The window MUST be a
    fixed length so that consecutive reports are comparable; how it is aligned is an implementation
    question this specification does not constrain, because nothing here depends on the alignment.
  - **Surface — stated, because "reported" with no reader is not a measurement.** Each window's
    report MUST be a **versioned, machine-readable artifact obtainable on demand**, carrying the
    interval it covers, the deployment identity and tenant identity FR-035 requires, the total count
    of reported results it is a share of, and the per-reason breakdown FR-024's named refusal reasons
    supply. It MUST be obtainable **without re-running any session and without reading the trace
    store directly**, so that it is available to an owner review rather than only to an operator with
    query access. A report for a window that has not closed MUST be marked as covering a partial
    interval; SC-019's *"first production reporting window"* means the first **closed** one.

  > **Why the two halves are treated differently, recorded because "no window" and "no threshold"
  > look like the same gap and are not.** The missing threshold is **deliberate and stated as such**
  > in this requirement's own text: nothing in the evidence base estimates the share, so a threshold
  > invented here would be the inherited-number failure this corpus catches elsewhere. **The missing
  > window was nowhere stated as deliberate** — it was an unstated term inside a requirement that
  > otherwise explains itself carefully, which is the signature of an oversight rather than a
  > deferral. Making the deferral explicit is the correction; the length remains the owner's, and now
  > says so. **One consequence to carry forward**: SC-019 cannot be evaluated until the owner sets the
  > window, which is the same shape as SC-001's dependency on this requirement already recorded in
  > Open Risks Carried, and it is a precondition rather than a defect.
- **FR-053**: A language, a framework, or a target shape is **supported** only where a committed
  fixture and an asserted expected output for it exist. Anything else MUST be described as
  unsupported rather than as best-effort, and MUST NOT appear in any statement of what the product
  supports. Every measurable outcome above that names a corpus, a battery or a fixture set MUST have
  that fixture committed alongside the capability it exercises rather than assembled when the
  measurement falls due, and any measurement harness built for FR-039 through FR-042 MUST pin its
  inputs as well as its records — a freeze that pins artifacts and not the inputs they answered is
  not a freeze, which this corpus learned from a trace corpus that silently re-joined to whatever the
  task file said that day. This restates as a requirement what the Assumptions section carried as an
  expectation: constitution Principle VII's analyzer clause is not satisfied by an assumption.

  > **The Linux kernel floor, recorded 2026-08-03, and it is DERIVED rather than TESTED. The two
  > halves of that sentence are one claim and MUST NOT be quoted apart.** **OD-17** makes Linux the
  > only supported platform and [`plan.md`](./plan.md)'s Technical Context names the three facilities
  > v1 needs; neither states a minimum release, and the implementation needs one because the
  > alternative is letting an unknown kernel through a preflight that then passes vacuously.
  >
  > **The floor is Linux 5.14**, bound by `cgroup.kill`, the atomic group kill FR-049's session-as-a-
  > unit termination rests on. Two further facilities bind lower and are verified rather than
  > assumed: `SECCOMP_USER_NOTIF_FLAG_CONTINUE`, which FR-048's whole recording design rests on,
  > arrives at 5.5; and `SECCOMP_IOCTL_NOTIF_ID_VALID`'s ioctl number was corrected from `_IOR` to
  > `_IOW` at 5.9. The second is a property of our own code rather than of the kernel — the
  > implementation defines the corrected number, so on 5.5 through 5.8 that ioctl returns `EINVAL`
  > from a call site where the failure is invisible, which is the shape this specification treats as
  > worse than an outright missing facility.
  >
  > ⚠️ **5.14 is a derived lower bound on what could work. It is not a claim that 5.14 does work, and
  > nothing here may be restated as one.** Every run to date was on 6.12. *The facility exists in
  > 5.14* is a weaker statement than *this code works on 5.14*: cgroup delegation semantics,
  > `pivot_root` inside a user namespace, and `seccomp` notification behaviour all moved across the
  > intervening releases. Turning the derived bound into a tested one needs boots on 5.14, 5.15 LTS,
  > 6.1 LTS and 6.6 LTS — a CI matrix that does not exist and is not scheduled. **It is T205, and it
  > is deferred by owner decision 2026-08-03: the owner accepted shipping the derived floor marked
  > NOT TESTED rather than building the matrix now.** That is a decision not to measure, so the
  > caveat above is permanent until an owner decision to measure reverses it — it is not a backlog
  > item that will quietly clear. **Under this
  > requirement's own rule, a release with no committed fixture is unsupported rather than
  > best-effort, so the only *supported* kernel today is the one the fixtures run on.** The floor is
  > the preflight's refusal threshold, not a support claim.
  >
  > The preflight states the caveat wherever it states the floor, and a removal proof fires if the
  > caveat is dropped from the code. **Nothing that quotes 5.14 anywhere else may be weaker than
  > that**, which is why this note states the derivation and the untested status in the same breath
  > rather than footnoting the second.

**Artifact versioning and rollback**

- **FR-054**: Every artifact the system produces or consumes as configuration or as derived state —
  the served-operation set, derived contracts and derived checks, the effect-gate rule set and its
  deny list, the egress policy, FR-048's declared location set and FR-049's bounds, and the admission
  decision — MUST be versioned and content-addressed, and **restoring the immediately prior version
  of any one of them MUST be a single operator action**: no hand-editing of individual entries, no
  reconstruction from a trace, and no restart of the runtime.

  **Restoration is an undo of the most recent change, and it is its own inverse.** *"The immediately
  prior version"* means the version the artifact held before the change now being undone — so a
  restoration performed twice in succession returns the artifact to exactly where the first one
  started. A restoration is itself a change to what the artifact holds, and the version it moved away
  from is therefore what the next restoration restores. **This is a toggle between the last two
  versions and MUST NOT be implemented as a walk backwards through the publication history**: an
  artifact three versions old is not reachable by repeating the operation, and this requirement does
  not ask for it. Republishing content identical to what the artifact already holds is not a new
  version, so it does not become a restoration target and cannot make the operation a no-op.

  A restoration MUST be recorded exactly as a widening is under FR-019 — the operator, the version
  restored from, the version restored to — and MUST be subject to the same review as FR-012.
  FR-026 and FR-027 already require provenance,
  content hashing, and the two drift artifacts to be versioned independently; what this requirement
  adds is that those versions be **navigable**, because a version nobody can return to is a record
  rather than a control, and constitution Principle VIII requires rollback to be one command.

  > **The toggle reading confirmed by the owner 2026-08-03 — a wording change, not a behaviour
  > change.** The implementer flagged *"the immediately prior version"* as ambiguous between a toggle
  > and a history walk, shipped the literal reading, and named it in the test. The owner confirms the
  > toggle is what was intended: rollback undoes the last change, and rolling back twice returns you
  > to where you started. **Nothing in the implementation moves.** The two paragraphs above exist so
  > that a later reader does not recover the ambiguity from the phrase and reimplement the walk —
  > which would be a behaviour change, would silently invalidate the committed rollback test, and
  > would need a different word here rather than a different reading of this one. A walk backwards
  > would also have to distinguish publications from restorations in the retained history, which this
  > requirement neither states nor implies.
- **FR-055**: Every artifact FR-054 enumerates MUST be serialized in a **canonical form** before it
  is content-addressed, and re-deriving any source-derived artifact from unchanged input MUST
  produce a **byte-identical** payload and therefore an identical content address. The canonical
  form MUST be fully determined — key ordering, numeric formatting, line endings and character
  encoding all fixed — and MUST exclude from the hashed payload every value that varies between two
  runs over the same input, including timestamps, filesystem paths and hostnames; those belong in an
  envelope beside the hash rather than underneath it. Determinism MUST be asserted by a committed
  test that analyses one fixture twice and compares payloads byte for byte, not by comparing the
  addresses alone.

  > **Added 2026-08-03 — narrowing the Principle VII deviation record below, which was rejected in
  > part on substance during the plan phase and is corrected here rather than there.** That record
  > disposes of the determinism clause's byte-stability half as having "no subject either" because
  > v1 emits no agent system. **That is true of emitted agent systems and false of v1's own
  > artifacts**: FR-054 enumerates eight kinds and requires them content-addressed. Content
  > addressing over a non-canonical serialization yields a different address on every re-analysis of
  > identical input, and a changed address on the source-derived artifact is exactly what FR-028
  > reads as source drift. A non-canonical serializer is therefore a **false-alarm generator aimed
  > at the one v1 capability with no measured false-alarm rate** — which is why this is a
  > requirement and not a plan-phase preference. The plan phase declined to edit this document
  > mid-gate and recorded the correction in [`plan.md`](./plan.md) instead; that record now points
  > here.

### Key Entities

- **Target deployment**: A named, running instance of the analysed application, with an identity that
  travels on every artifact and trace derived from it. Distinct from the codebase.
- **Served-operation set**: What a named deployment actually serves, established above analysis rather
  than inside it and obtained from a machine-readable specification the target publishes. Carries its
  own version, its deployment identity, and its freshness — and, where the specification that
  produced it can no longer be fetched, its age, the specification state last found, and the
  staleness ceiling that age is measured against (FR-047).
- **Admission decision**: The recorded outcome of FR-044 and FR-020 for a named target — the
  specification state found, the criterion that passed or failed, and the reason given to the
  operator. Produced before any session and retained, because a rejection is a supportable answer and
  not an error.
- **Derived contract**: What an operation requires and returns, derived from the source. Carries
  derivation rule, source symbol, source file, analyzer version, content hash, and validation status.
- **Verification outcome**: One of verified, failed, or not verifiable, attached to a reported result,
  with the independent path that produced it and — on refusal — the reason no check was derivable.
- **Drift signal**: A detected divergence, naming which clock moved, the before and after artifact
  versions, and the affected operations.
- **Effect-gate rule set**: The safe-method rule and the deny list of known side-effecting reads.
  Versioned, operator-reviewed configuration; the only thing standing between the agent and a
  side-effecting read.
- **Egress policy**: The pinned destination set at host-and-port granularity and the permitted method
  set, enforced together at one point outside the agent's reach.
- **Execution environment**: The bounded environment the agent's commands run in — a declared set of
  filesystem locations, a declared processor bound and memory bound, no credential outliving the
  session, and exactly one path off it, which is the enforcement point. It is the "sandbox boundary"
  FR-013 delegates command containment to, specified by FR-048 through FR-050. Its bounds and its
  declared location set are versioned configuration under FR-054, recorded with the deployment
  identity they apply to.
- **Session trace**: The per-node record required by FR-038, including every gate decision and its
  rule.
- **Credential binding**: The association between a plane (model or target), a deployment, and a
  secret the system references but never reads into any artifact — nor, under FR-050, into anything
  the agent's execution environment can read. Whatever authority that environment holds is bound to
  one session and stops being honoured when the session reaches a terminal state.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An operator with a running application reaches a first verified answer in under 15
  minutes from starting configuration, unattended, on a reference application.
- **SC-002**: Across an adversarial battery of attempted operations, **zero** calls that did not
  resolve read-only reach the target, and **100%** of denials state the rule that produced them.
- **SC-003**: Across the same battery, **zero** outbound connections leave the execution environment
  to any destination outside the pinned set — including connections attempted by commands the agent
  composed itself — and zero requests are allowed whose method the enforcement point could not read.
- **SC-004**: **Zero** secret values appear in model context, emitted artifacts, traces or persisted
  state, asserted by an automated scan that runs on every session.
- **SC-005**: On a corpus of injected value faults, including faults smaller than one percent of the
  correct value, the verifier detects at least **95%**, with a false-alarm rate no worse than **1%**
  on a matched corpus of correct results. **Denominator stated 2026-08-03 with FR-024; the two
  percentages are unchanged.** Both rates are computed over **the faults injected into quantities the
  precision ladder does not refuse**, and **the refusal share MUST be reported beside them** rather
  than folded into either. A quantity that refuses is returned not verifiable under FR-025, so a
  fault injected into one is neither detected nor missed, and scoring it either way would make this
  criterion movable by changing the corpus's mix rather than the verifier. **A run that reports the
  two rates without the refusal share does not satisfy this criterion**, because the reader cannot
  tell what they are rates of. FR-045 and SC-019 measure the same share in production, which is where
  it stops being a property of a chosen corpus.

  > **Refusal-share reporting narrowed 2026-08-03 by `OD-23`. The denominator rule is unchanged; what
  > changed is that this criterion acquired a way to pass without testing the case it was written
  > for.** ~~FR-024's property 5 makes the request rung a ratchet, and on the one census available that
  > moves its single entry to refusal.~~ **The hazard was surfaced by property 5 in its ratchet form,
  > which moved the corpus's one sub-one-percent entry into the refusal set; property 5 was revised
  > the same day and that entry is admitted again, so the instance is gone. The requirement below
  > stays, because it was written against the hazard and not against the instance — see the note at
  > the end of this box.** That entry is the **only measured sub-one-percent catch in the
  > corpus** — the 0.882% near-miss in
  > [finding 015](../001-discovery-validation/findings/015-verifier-vs-judge-not-run.md). Follow the
  > denominator rule through: a refused quantity leaves **both** the numerator and the denominator, so
  > if the sub-one-percent faults are concentrated in quantities the ladder refuses, **the first
  > sentence of this criterion becomes vacuous while the criterion still reports 95%**. The corpus
  > would contain sub-one-percent faults, as required, and none of them would be scored.
  >
  > **So the refusal share MUST be reported broken out for the sub-one-percent stratum**, not only in
  > aggregate. A run reporting a single pooled refusal share does not satisfy this criterion. This is
  > the same failure shape the pooled share was introduced to prevent, one level down: an aggregate
  > that looks healthy because the hard stratum was refused out of it rather than passed. The
  > percentages are still unchanged; what is added is a second place the share must be cut.
  >
  > **Confirmed intact 2026-08-03 against property 5's revision, and the wording needs no change.**
  > The revision restores the corpus's one sub-one-percent quantity to the scored set, which removes
  > the *known instance* of the vacuity hazard and removes none of the hazard. Any corpus whose
  > sub-one-percent faults happen to fall in quantities the ladder refuses — for any reason, this
  > decision included or not — reports a healthy aggregate over a stratum it never tested. The
  > requirement is written against that structure and never named the instance, so it survives
  > unaltered. Retiring it now because the one known instance has been repaired would be the
  > "a safeguard that can no longer fire reads exactly like one that has been satisfied" error, and it
  > is a live risk here precisely because the stratum currently has exactly one member: a corpus in
  > which that member is refused for some unrelated reason is one quantity away.
- **SC-006**: A verifier restricted to shape and type conformance detects **none** of the value faults
  in SC-005's corpus, demonstrating that the shipped verifier's detection comes from independent
  recomputation rather than from conformance checking.
- **SC-007**: **100%** of derived contracts and derived checks carry provenance and a validation
  status, and **zero** are presented as validated without an artifact their own derivation did not
  produce.
- **SC-008**: **100%** of breaking source-contract changes in a synthetic drift corpus are detected in
  the same automated check run as the commit that introduced them.
- **SC-009**: **100%** of operations withdrawn by the deployment in a synthetic deployment-drift corpus
  are detected and disabled, and **zero** unaffected operations are disabled alongside them.
- **SC-010**: The full User Story 1 battery completes against at least four independent model
  providers with configuration as the only difference between runs.
- **SC-011**: Under an induced crash and resume, a session's cumulative spend and elapsed time never
  exceed the configured ceilings, and no recorded side effect is repeated.

  > **Narrowed 2026-08-03 by SC-030 — narrowed, not wrong.** This criterion is true and complete for
  > the two ceilings it names and for the side-effect property, and it is the side-effect half that no
  > other criterion covers. What it does not reach: it names **two of FR-005's four ceilings**, it
  > exercises **one** crash-and-resume rather than repeated ones, and it says nothing about an unset
  > ceiling. SC-030 supplies all three, so the shape this one measured was never wrong — it was
  > partial, and partial coverage of a spend ceiling reads exactly like complete coverage in a review.
- **SC-012**: ~~For **100%** of sessions, a failure can be attributed from the trace alone to a versioned
  node, a typed terminal, and the routing decision that reached it, without re-running the session.~~
  **Rewritten 2026-08-03 with FR-038 and against the same v1 subject; see the note there. The
  percentages are unchanged — what changed is what they are percentages *of*.** For **100%** of
  sessions ending in a failure terminal state, the failure can be attributed from the trace alone,
  without re-running the session, to **the span on which it occurred** — identified by kind and by
  position in the session — to **that span's typed outcome** and the session's named terminal state,
  and, where the failure was a denial, to **the rule identifier that produced it**. For **100%** of
  spans, the artifact versions in force and the per-span cost are present. A trace in which a failed
  session's attribution requires reading a second artifact, or requires a human to infer which span
  failed from ordering, does not count toward either figure.
- **SC-013**: Within 30 days of first production traffic, the verifier's marginal detection over the
  shadow judge is reported with the pre-registered gate applied and all three branches evaluated.
- **SC-014**: No write capability is released until the effect gate's read-only precision has been
  reported against a labelled corpus of real operations, against a threshold pre-registered for a
  per-call gate.
- **SC-015**: Drift detection rate, false-alarm rate and detection latency are reported for both
  clocks against a pre-registered design before any external material describes drift detection as a
  differentiator.
- **SC-016**: An audit of all external product material finds **zero** claims of capability advantage
  for an application-specific tool surface, **zero** claims that synthesis is safer, **zero** cost
  figures quoted without basis and scope, and **zero** uses of "provably" for effect resolution.
- **SC-017**: For each deployed runtime, whether it is still serving traffic four weeks after
  installation is measured and reported. A runtime that is installed, demonstrated and then unused is
  recorded as a non-adoption rather than as an install.
- **SC-018**: Across a fixture set covering every specification state — published and non-empty,
  absent, unreadable, and present but carrying no operations — **100%** of the non-admissible targets
  are rejected at admission with a named state and a named criterion, **zero** reach an agent session,
  and **zero** are admitted on a specification that fetched successfully but carried no operations.
- **SC-019**: The share of reported results returned in the not-verifiable state is reported, broken
  down by refusal reason, for the first production reporting window — with no threshold applied,
  because none is pre-registered. **Window and surface stated 2026-08-03 with FR-045; the criterion
  is unchanged and is now evaluable.** "The first production reporting window" means **the first
  window to close** after first production traffic, at the configured length FR-045 requires as
  configuration; the criterion is **not evaluable until that length is set**, and an unset length
  fails startup rather than producing an unbounded window. The report satisfying this criterion is
  FR-045's machine-readable artifact, and it MUST state the interval it covers and the total it is a
  share of — a bare percentage does not satisfy this criterion, because with no threshold applied the
  denominator is the only thing that makes the figure readable.
- **SC-020**: On the synthetic deployment-drift corpus, **100%** of withdrawn operations are detected
  within the configured detection window under the default automated trigger and with no event
  supplied by a deployment pipeline, and **100%** are detected on demand under manual invocation.
- **SC-021**: On a fixture that withdraws an admitted target's published specification and later
  restores it, **100%** of results returned while the served-operation set is stale carry a
  machine-readable stale marking with the set's age; **zero** calls are served after the configured
  staleness ceiling elapses; **zero** sessions end in a generic error at the ceiling; and **100%**
  of the operations that differ between the last-known-good set and the restored set are reported as
  drift rather than adopted silently. *(Authorised by **OD-21**; citation added 2026-08-03 when
  OD-21 was recorded, criterion unchanged.)*
- **SC-022**: Across an adversarial battery run from inside the agent's execution environment, **zero**
  reads and **zero** writes succeed outside the declared set of filesystem locations — including
  attempts against the effect-gate rule set, against the egress policy, and against another session's
  artifacts — **zero** partially succeed, and **100%** of the refusals are recorded in the trace with
  the rule that produced them.

  > **Narrowed 2026-08-03 to the record's existence — narrowed on what the record guarantees, not on
  > how many records there must be.** The clauses above are unchanged and the recording clause is
  > still total. What was never stated, and is stated now, is which *fields* of that record the
  > criterion is evaluable against: the supervisor reads a path out of the workload's own memory, so
  > a field derived from that read is not something the supervisor can vouch for.
  >
  > A filesystem decision on an undeclared path produces a record. The record's `path` is disclosed
  > on a best-effort basis and is marked with its provenance; enforcement does not depend on it. The
  > mount namespace makes an undeclared path absent, so a workload that rewrites the path in its own
  > memory between the supervisor's read and the kernel's resolution misattributes an audit entry and
  > cannot obtain access.
  >
  > **What this criterion is therefore scored on**: the record's existence and the rule identifier
  > FR-048 and FR-011 require, both of which are the supervisor's own and neither of which the
  > workload can influence. A battery arm that asserts the recorded `path` equals the path the
  > adversary asked for is measuring something this design does not claim, and would fail against a
  > correctly-behaving supervisor.
- **SC-023**: Under a workload that deliberately exhausts each declared bound in turn, **100%** of
  affected sessions end in a named terminal state and **zero** end by generic error; **zero** sessions
  exceed the declared processor or memory bound; work already performed still counts against the
  session's ceilings in **100%** of cases; and a co-located reference workload on the same host keeps
  serving throughout, so exhaustion is contained to the session that caused it.
- **SC-024**: On a fixture that scans everything readable from inside the execution environment during
  a session and then, after that session has reached a terminal state, replays every
  credential-shaped value it found: **zero** secret values are readable from inside the environment,
  **zero** replays are honoured, **100%** of the refusals are recorded, and **zero** values written
  inside one session's environment are readable from a later session's.
- **SC-025**: Across a differential battery in which the same sessions are run with the shadow judge
  agreeing, disagreeing, and not running at all, **100%** of caller-visible result records and
  **100%** of gate decisions are identical across the three runs, and **zero** behavioural
  differences are attributable to the judge.
- **SC-026**: On a fixture in which the target adds an operation to its published specification while
  continuing to publish that specification throughout, **100%** of newly appearing operations are
  inspected before becoming available to the agent, **zero** become available uninspected, and
  **100%** of those that cannot be inspected are refused.
- **SC-027**: An audit of every statement of what the product supports finds **zero** supported
  languages, frameworks or target shapes for which no committed fixture and asserted expected output
  exist.
- **SC-028**: For **100%** of versioned artifacts, restoring the immediately prior version is
  completed by a single operator action, with **zero** hand-edits of individual entries and **zero**
  runtime restarts, and **100%** of restorations are recorded with the operator and both versions.
  Restoring twice in succession returns **100%** of artifacts to the version the first restoration
  started from, which is FR-054's undo-and-its-own-inverse reading measured rather than assumed.
- **SC-029**: Analysing one committed fixture twice from unchanged input produces byte-identical
  payloads for **100%** of the artifact kinds FR-054 enumerates, and therefore **zero** content
  addresses that differ between the two runs; across a drift battery in which source is held
  constant and only re-analysis is repeated, **zero** source-clock drift signals are raised.

  > **Added 2026-08-03 with FR-055.** The second clause is the one that matters and it is why this
  > criterion exists as a measurement rather than as a unit test: an identical-address assertion
  > proves the serializer is canonical, and only running the drift detector over a
  > no-change-but-re-analysed corpus proves that the false-alarm channel FR-055 closes is actually
  > closed. It is also the only false-alarm figure v1's drift capability has any way to produce
  > before production, which is worth having given that its real false-alarm rate is unmeasured
  > (**OD-14** ships the capability without the claim).
- **SC-030**: For each of FR-005's four ceilings in turn, on a fixture that starts a session with that
  ceiling **unset**, **100%** of such startups fail and name the missing ceiling, and **zero** sessions
  begin. On a fixture that drives a session past each ceiling under repeated induced crash and resume —
  at least three resumes, so that no single reset can be mistaken for none — **zero** sessions exceed
  the configured ceiling on any of the four dimensions, **100%** end in a named terminal state under
  FR-006, and the cumulative total counted after every resume is never lower than the total recorded
  before the crash that preceded it.

  > **Added 2026-08-03 with FR-005's extension.** The last clause is the one that matters and it is why
  > this is a measurement rather than an assertion: a ceiling that resets on resume is not a ceiling,
  > and the failure is invisible in review because **every individual attempt is compliant**
  > ([finding 006](../001-discovery-validation/findings/006-graph-loop-primitives.md), **U-30**). Three
  > resumes rather than one is deliberate — a single resume cannot distinguish a ceiling that resets
  > from one that holds if the run happens not to reach the ceiling twice. **No threshold is invented
  > here**: every figure in this criterion is a count of failures that must be zero or a proportion that
  > must be total, and the ceiling values themselves are the operator's configuration, which FR-005
  > requires to be set rather than defaulted.

## Assumptions

- **The operator can run the enforcement point and route the agent's environment through it.** ~~This is
  the one operational obligation v1 places on a self-hosted operator~~, and it was chosen over
  alternatives that would have required the operator to generate and maintain trust material.
  **Superseded 2026-08-03 by FR-048 through FR-050 — true of the specification as it stood, and the
  specification has moved.** It is no longer the *one* obligation: the operator must also run the
  agent's commands inside an environment that is filesystem-scoped, processor- and memory-bounded,
  and holds no credential outliving the session. Those were always implied by constitution
  Principle IV bullet 1 and were simply not required by this document, so what changed is what the
  operator is *told*, not what they would have had to do. Both obligations are stated here rather
  than discovered at install.
- **The target is reachable from the system twice** — once to establish what the deployment serves, and
  again at session time to call it. Co-location makes both cheap and is expected in practice, but is
  never assumed by the architecture (FR-034).
- **One agent, not several.** Decomposition into multiple cooperating agents left v1 with synthesis
  (**OD-09**), and the working preference is one agent with more capabilities over several that must
  re-explain context to each other.
- **The analysis layer's v1 role is contract derivation and source-drift detection**, not decomposition
  or tool generation. This is a materially smaller build than the original vision described and must be
  sized as one.
- **Requiring a published specification narrows the addressable population, and by an unmeasured
  amount.** This is stated as a limitation rather than left to be discovered. v1 is sellable only
  into deployments that publish a machine-readable description of their own operations at operation
  granularity; a target that withholds it, gates it behind a credential the system does not hold, or
  publishes an empty one is not a customer for v1 at any level of effort. How large that excluded
  population is has never been measured, and the measurement that would price it — the prevalence of
  the route shape that makes schema-free method discovery fail — is **U-39**'s own first step and
  belongs to whoever scopes widening admission in v2.
- **Reference applications exist for testing.** Language and framework support is claimed only where a
  committed fixture and an asserted expected output exist; anything else is explicitly unsupported
  rather than best-effort. **Promoted 2026-08-03 to FR-053 — unchanged in substance.** The
  discipline is right and an assumption is not a requirement, which is the whole of constitution
  Principle VII's analyzer clause; it now has a requirement and SC-027 behind it.
- **The evidence from feature 001 concerns a hand-written tool surface on one application with one
  model.** None of its magnitudes transfer to v1's claims, and v1's own claims are the unmeasured ones
  enumerated in Context.

## Out of Scope

Each exclusion names the decision that put it there, so that reinstating one is a visible act.

| Excluded from v1 | Decision |
|---|---|
| Tool synthesis from the target's operations, and promotion selection | **OD-09** / **D-21** — deferred to v2 as a measured efficiency opportunity, not as a capability advantage |
| Static per-tool effect classification as a differentiator | **OD-09**; the *obligation* does not defer and is carried per call by FR-008 through FR-012 (**D-22**) |
| Decomposition of a codebase into multiple agents | **OD-09** |
| Any write against the target | **OD-10**; the exit condition is FR-041 |
| Embeddable iframe and any surface exposing the agent to untrusted end-user input | **OD-08** — deferred with the hosted model |
| A hosted, multi-tenant offering | **OD-08** — preserved by design through FR-034 and FR-035, not built |
| Knowledge-graph memory layer and artifact trading between agents | Original vision, deferred; see [`07`](../../research/07-product-vision.md) §1.1 |
| An agent that operates *on* the codebase rather than *through* the running application | Its comparison never ran; the class question stays open |
| An export adapter presenting the catalogue to external clients | **D-06** — it exports the tool catalogue, which is a v2 artifact |
| Targets that publish no machine-readable specification of what they serve | ~~**Clarification 2026-08-03**~~ **OD-18** *(the same 2026-08-03 clarification, which had no decision record until one was written retroactively on 2026-08-03)* (FR-002, FR-044) — method discovery by probing executes target code on at least one measured framework, and an operator declaration would make everything derived from it provisional under **D-17**. Widening admission is a v2 question and **U-39** is its open input |

## Resolved Decisions Inherited

These are settled and are not reopened by this specification. They are listed because a requirement
above depends on each of them.

| Decision | Substance |
|---|---|
| **OD-06** / **D-18** | Reachability is a stage above analysis, so analysis stays rebuildable from the codebase alone and the two artifacts drift on separate clocks |
| **OD-07** / **D-19** | The capability claim is not supported; a general fallback path is required because a surface that does not fit the question costs everything |
| **OD-08** / **D-20** | Self-hosted first, with a hosted tier preserved by discipline rather than built |
| **OD-09** / **D-21** | v1 is a spec-aware runtime, a contract-derived verifier, and drift detection |
| **OD-10** | v1 is read-only; the gate has two dispositions, and nothing escalates to a human at run time |
| **OD-12** | Destination and method controls live at one mandatory enforcement point that sees runtime-originated and command-originated requests identically; the shell therefore executes and nothing classifies commands for effect |
| **OD-13** | Constitution Principle IV bullet 1 is now a four-term specification: pinned addresses, host-and-port granularity, name resolution denied or mediated, and loopback / private / link-local / metadata denied even on an allowlisted host |
| **OD-14** | The verifier's margin over a model judge is unmeasured, the measurement is deferred to production, and the pre-registered gate travels unchanged |
| **OD-15** *(added 2026-08-03)* | v1 depends on no agent framework. The loop, the session lifecycle and the operator-facing surface are ours. This partially reverses **OD-01** and changes no requirement here — the specification names no framework and never did |
| **OD-16** *(added 2026-08-03)* | Each provider is reached through that vendor's own SDK behind a thin driver of ours. FR-037's round-trip is discharged in the driver, and **SC-010 is a test v1 must pass rather than a result it inherits** |
| **OD-17** *(added 2026-08-03)* | Linux is the only supported platform. Every other platform is unsupported rather than best-effort, which is what **FR-053** requires of anything with no committed fixture |
| **OD-18** *(recorded retroactively 2026-08-03)* | A published machine-readable specification, at operation granularity, is an **admission criterion**. A target without one is declined at admission with a stated reason and is not served by a schema-free method-level path. Authorises **FR-002** and **FR-044**. **This is not inherited scope — it is this document's own clarify-session decision, listed here because a requirement above depends on it and nothing recorded it until now** |
| **OD-19** *(recorded retroactively 2026-08-03)* | A result v1 cannot verify is returned with its unverifiability marked, not withheld, and the share returned in that state is measured with no threshold pre-registered. Authorises **FR-025** and **FR-045**. Also this document's own decision rather than inherited |
| **OD-20** *(recorded retroactively 2026-08-03)* | A drift check is both manually invokable and automatically triggerable, with at least one automated trigger configurable rather than imposed. Authorises **FR-029** and **FR-046**. Also this document's own decision rather than inherited |
| **OD-21** *(recorded retroactively 2026-08-03, after OD-18 through OD-20)* | An admitted target that stops publishing the specification which admitted it is served from the **last-known-good set, marked stale**, and denied past a configured staleness ceiling measured from the last successful fetch. Authorises **FR-047** and the narrowings it makes at **FR-001**, **FR-030** and **FR-031**; measured by **SC-021**. The fourth answer of the same clarify session, and also this document's own decision rather than inherited |
| **D-01** | Calls reach the target over its existing external interface, never in process |
| **D-07** | Two physically separate credential planes; no secret in model context |
| **D-17** | Provenance, independent validation, provisional marking and deployment identity on every derived field |

## Dependencies

- **The constitution at ~~v1.2.0~~ v1.3.0** ([`.specify/memory/constitution.md`](../../.specify/memory/constitution.md))
  *(amended 2026-08-03 by **OD-22**, Principle VI — see the disposition below)*.
  Principle I governs FR-022 through FR-026, Principle IV governs FR-008 through FR-021, Principle V
  governs FR-037, and Principle VI governs FR-038. **Extended 2026-08-03 — the four requirements the
  clarification session added had no principle mapping, which would have reached the plan phase as a
  gap rather than as a decision.** Principle IV also governs **FR-044**, the admission gate, and
  **FR-047**, which is what that gate's precondition failing *after* admission means; Principle I
  also governs **FR-045**, which measures the coverage of the verification Principle I mandates.
  **FR-046** is a scope decision recorded at FR-029 and answers to no single principle. ~~The plan
  phase carries a mandatory Constitution Check against all of the principles, including the four
  this specification does not map — II, III, VII and VIII — each of which needs an explicit
  disposition there rather than silence.~~ **Superseded 2026-08-03 — accurate about the state it
  described, and that state has moved: the four dispositions are recorded below rather than deferred
  to the plan.** **Extended again 2026-08-03 for FR-048 through FR-054**, which had no mapping for
  the same reason the previous four did not — they postdate the sentence that mapped the ranges.
  Principle IV governs **FR-048**, **FR-049**, **FR-050** and **FR-051**: the first three are its
  bullet 1 sandbox terms and the fourth is the point at which its inspection obligation attaches.
  Principle I governs **FR-052**, which states where its model-judge clause binds and where it does
  not. Principle VII governs **FR-053** and Principle VIII governs **FR-054**. The plan phase still
  carries the mandatory Constitution Check; what it no longer has to do is invent these dispositions
  at the gate. **Extended once more 2026-08-03 for FR-055**, which Principle VII governs jointly with
  Principle VIII: it is the determinism clause's byte-stability half, and it exists because the
  Principle VII disposition below disposed of that half as having no subject and the plan phase found
  that it does. **Extended once more 2026-08-03 for FR-005, and the mapping is partial for a reason
  worth stating rather than rounding off.** Principle IV bullet 1 governs FR-005's **wall-clock** term
  — it requires a sandbox *"CPU/memory/wall-time capped"*, and FR-049 supplies the first two — but
  **no principle in the constitution names spend, token consumption or turns**. Principle VI requires
  ~~per-node cost~~ **per-unit cost** *(unit-neutral since v1.3.0, OD-22)* to be *observable* and Principle I lists cost among a node contract's fields; neither
  requires a ceiling, and observability is not enforcement. FR-005's other three dimensions therefore
  rest on this specification and on `research/14-architecture-synthesis.md` **U-30**, not on a
  principle. That is recorded here rather than closed: whether the constitution should carry a spend
  bound is an amendment question and an owner act. **Extended once more 2026-08-03 for FR-056 and
  FR-057**, added the same day and mapped when added rather than in a later sweep, because the
  previous four extensions on this line all exist because a requirement arrived unmapped.
  **Principle IV governs FR-056** — it is the procedure behind the inspection obligation the
  principle attaches at FR-051, and mapping it anywhere else would separate a rule from the
  obligation it discharges. **Principle I governs FR-057**, and only through one clause: the
  provenance and provisional-marking rule that D-17 restates. FR-057 requires a *declaration* to be
  carried and presented as a declaration, which is that clause applied to the one input v1 cannot
  validate. **No principle governs FR-057's fail-loudly-when-unset clause**; that rests on this
  specification and on the plan's **Q-10**, exactly as FR-005's three unprincipled dimensions do.

  **~~Principle VI's terms do presuppose a graph~~ — RESOLVED 2026-08-03 by the constitution
  amendment at v1.3.0 (OD-22). They did, and they no longer do. The clause-by-clause reading below is
  kept unedited because it is what the amendment was drafted against; read it as the diagnosis and
  the paragraph after it as the disposition.** The answer was more specific than "they presuppose a
  graph", and the
  specific version is what the plan phase needed. Recorded 2026-08-03 when FR-038 was rewritten, from
  the principle's text rather than from its summary. Principle VI **had two clauses with different
  scopes, and only one of them was graph-bound**:

  - **The field list is scoped to emitted systems and therefore has no v1 subject at all.** Its
    sentence opens *"Every **emitted system** MUST produce, from day one: one span per node…"*, and
    v1 emits no system — the Principle II disposition below says so in terms, and
    [`data-model.md`](./data-model.md) §4 lists *a node, edge or topology entity* among what is
    deliberately absent. This is **the same scope argument that disposes of Principles II, III and
    VII's generator clause**, reached independently and landing in the same place. Four of the
    clause's terms are graph-bound — *versioned node identity*, *the routing decision with its
    predicate inputs* **for every conditional edge**, *per-node cost*, and the per-node unit itself —
    and its rationale groups traces by `(terminal_type, failing_node, incoming_edge)`, two-thirds of
    which v1 has no value for. Worth recording as evidence for the substitution rather than against
    it: **the clause's own unit word is already "span"** — *"one span per node"* — so FR-038 keeping
    the span and dropping the node is the narrower of the two available readings.
  - **The ship gate is not scoped, and it is the one that bites.** *"A capability that cannot be
    attributed to a versioned node MUST NOT ship"* carries no "emitted system" qualifier, so on a
    literal reading **no v1 capability may ship**, because v1 has no nodes to attribute anything to.
    A deviation record scoped to the field list would leave this sentence untouched.

  ~~**This specification cannot close either half**, and it should not~~ — **and it did not: the
  owner did, on 2026-08-03, and the instrument was the second of the two remedies named below.**
  ~~Principle VI is mapped above as
  governing FR-038 and, unlike Principles II, III and VII, carries **no deviation record**, so nothing
  in this corpus authorises reading its terms as other than literal.~~ The remedies — a v1-scoped
  deviation record in the table below covering *both* clauses, or an amendment restating identity and
  cost in unit-neutral terms so the principle binds a loop as well as a graph — are owner acts under
  the constitution's governance section. The choice was not cosmetic: an **amendment** binds v2's
  emitted graphs to the unit-neutral wording as well, whereas a **deviation record** leaves the graph
  wording in force the moment v2 emits a topology.

  **The disposition, recorded 2026-08-03 — `OD-22`, constitution v1.3.0, and Principle VI takes no
  deviation record.** Both clauses are amended rather than exempted. The field list is restated over
  a **traced unit** whose kind the shipping tier declares — the node for an emitted agent system, the
  span for a runtime executing a loop — and the ship gate binds attributability to that tier's own
  declared unit at the artifact versions in force, so the obligation survives intact while the unit
  stops being graph-specific. **Three obligations arrive with it**, and they are the reason
  unit-relativity is not an escape hatch: the unit set must be **closed and declared**, the tier must
  trace at **the finest unit it executes that has an outcome and a cost** so a coarser declaration is
  non-compliant, and **unit identity and artifact version are two terms rather than the single phrase
  *versioned node identity***. FR-038 satisfies all three — the closed seven-kind span set, the span
  as v1's finest costed unit, and kind-and-position carried alongside the versions in force — and
  **SC-012** is the measurement of the ship gate. The reason the second remedy was taken rather than
  the first is recorded at OD-22 and is worth repeating here: a deviation record cannot fix an
  unscoped `MUST NOT`, because a record scoped to v1 leaves the sentence standing for every tier it
  does not name.

  **Dispositions for the four principles this specification does not otherwise map.** Each is a
  deviation record in the form the plan's Constitution Check needs: what does not apply, to which
  scope, on whose decision, and what would reinstate it. **Two things these records must not be read
  as saying.** They do not narrow the constitution — its preamble describes a product that
  statically analyzes a codebase and *emits a multi-agent system*, and that product is still the
  product. And **OD-09 deferred synthesis, promotion selection, per-tool effect classification and
  decomposition-into-agents to v2; it did not cancel them** ([`plan.md`](../001-discovery-validation/plan.md)
  OD-09, and Out of Scope above, which records the deferral per line). So the disposition below is
  *not applicable to v1*, never *not applicable to the product*, and each record names what brings
  the principle back into force.

  | Principle | Disposition for v1 | Scope of the deviation | Authority | What reinstates it |
  |---|---|---|---|---|
  | **II — Topology Encodes Protocol** | **Not applicable to v1 by scope.** The principle governs *emitted* topologies: serializable, diffable, content-addressed graphs carrying a machine-checkable `invariants` block, with topology tests on every change. v1 emits no agent system — it *is* one runtime with one agent (Assumptions), so there is no emitted topology to serialize, diff or invariant-test | The emission clause only. The principle's underlying rule — that anything an agent must not skip lives in structure rather than in a prompt — **is honoured and is load-bearing in v1**: FR-008's blocking enforcement point, FR-009's two dispositions, FR-014's enforcement point outside the agent's reach and FR-048's boundary are all structural, and FR-013 forbids satisfying any requirement by classifying what the agent composed | **OD-09**, owner, 2026-08-02 | v2's decomposition-into-agents and tool synthesis. The moment more than one agent or a generated control flow is emitted, the emission clause binds in full |
  | **III — Default to the Loop** | **Not applicable to v1 by scope.** The principle governs the choice between emitting a plain tool plus a loop and emitting a graph, for a *promoted function*. v1 promotes no functions and emits no node graph | The whole principle, as an emission rule. Its preference is nonetheless the one v1 follows: one agent holding general capabilities (FR-004), not several that must re-explain context (Assumptions) | **OD-09**, owner, 2026-08-02 | v2's synthesis and promotion selection, which is the first point at which there is a promoted function to make this choice about |
  | **VII — Test-First and Fixture-Backed** | **Split: the generator clause is not applicable to v1 by scope; the analyzer, determinism and integration-surface clauses apply and are now required.** v1 emits no artifacts, so *"emitted artifacts MUST be asserted structurally — topology tests, contract tests per node, schema tests on the serialized topology and the knowledge layer"* has no subject | The generator clause, and ~~the half of the determinism clause that asks emitted artifacts to be byte-stable — which has no subject either~~. **Narrowed 2026-08-03 — narrowed, not wrong. The struck clause is true of *emitted agent systems* and false of v1's own artifacts, and the difference is load-bearing: FR-054 enumerates eight artifact kinds and requires them content-addressed, so byte-stability has a subject after all. It is closed by FR-055 and measured by SC-029; see the note at FR-055 for why a non-canonical serializer is a false-alarm generator aimed at FR-028.** **Applies and is closed here**: the analyzer's fixture clause by **FR-053** and **SC-027**; the analyzer half of determinism by FR-002's requirement that source analysis be reproducible from the codebase alone with no network input, **and its byte-stability half by FR-055 and SC-029**; the integration surface's fail-closed configuration contract by FR-033 and FR-044. Test-first itself is a workflow obligation on the plan and tasks phases, not something a specification can discharge | **OD-09**, owner, 2026-08-02, for the generator clause; the rest is not deviated from | v2's emitted artifacts, at which point topology, contract and schema tests are owed in the same change |
  | **VIII — Versioned Artifacts, Earned Complexity** | **Applies in full. It was unmapped rather than deviated from, and it was partly met.** Provenance, content hashing and independent versioning were required (FR-026, FR-027); one-command rollback was required nowhere in this specification | No deviation is claimed. **FR-054** closes the versioning and rollback clause across every artifact v1 produces or consumes, and **SC-028** measures it. The earned-complexity clause is a plan-phase obligation and the plan must justify any new layer against a named failure it prevents | Not deviated from | — |

  **One workflow obligation, recorded here because it is easy to reach `implement` without it.** The
  constitution's compliance-review section makes the `/speckit-analyze` phase **mandatory** before
  `/speckit-implement` for any feature that adds a permission tier, and this feature adds one
  (FR-008 through FR-012).
- **Feature 001's record.** [`VERDICT.md`](../001-discovery-validation/VERDICT.md) for what was
  measured, [`plan.md`](../001-discovery-validation/plan.md) for OD-01 through ~~OD-14~~ ~~OD-17~~ **OD-21**, and
  [`research/14-architecture-synthesis.md`](../../research/14-architecture-synthesis.md) for the
  decision, contradiction and uncertainty registers.
- **A reference application** that is real, data-driven, seedable and publishes its operations, for
  every measurable outcome above that names a corpus or a battery.

## Open Risks Carried, Not Resolved

Stated because a specification that inherits an open risk silently is the failure this project keeps
catching.

- **U-44** — whether a target's own safe-method operations can be induced to make outbound requests is
  unmeasured on every target. FR-020 supplies a default and an inspection, not a finding.
  **Widened 2026-08-03 in coverage and not in evidence.** FR-051 now requires the inspection at every
  successful fetch rather than at admission alone, which closes the case where a target that never
  stopped publishing adds an operation between two fetches. Nothing about that measures the property:
  the risk is unchanged and only the number of doors it can arrive through has shrunk.
- **U-30** — no layer of the stack was found to supply a spend ceiling that survives a crash and
  resume. FR-005 requires one; nothing existing provides it. **Worsened and then covered on
  2026-08-03, and the two halves must not be confused for each other.** *Worsened*: `plan.md`
  **OD-15** dropped ADK, so `max_llm_calls` — the resettable one-dimension ceiling
  [finding 006](../001-discovery-validation/findings/006-graph-loop-primitives.md) measured, which at
  least bounded a single invocation — is gone, and **inadequate and absent are different**. *Covered*:
  FR-005 now also states the unset case (required configuration, startup fails loudly, no invented
  default, following the plan's **Q-10** treatment of FR-049's bounds) and the no-loss-on-crash
  property, and **SC-030** measures both across at least three resumes. **The risk this entry names is
  unchanged and stays open**: requiring a ceiling is not building one, nothing in the evidence base has
  yet shown any layer enforcing one, and the mechanism that would make the cumulative property
  enforceable is a plan-phase choice interacting with **U-31**.
- **U-39** — method-level reachability may be obtainable only where the target publishes or exposes a
  specification. This is a promise to a customer rather than a measurement, and no further measurement
  resolves it. ~~It is the subject of the clarification at FR-002.~~ **Superseded 2026-08-03 — the
  clarification at FR-002, now recorded as OD-18, removed U-39 from v1's critical path without
  resolving it.** By making a
  published specification an admission criterion, v1 no longer needs a schema-free method-level
  mechanism and therefore no longer depends on the trade space U-39 maps. The entry stays open and
  changes owner: it is now the input to any decision to widen admission, and its own first step —
  measuring how common the route shape is that drops schema-free operation-level precision to
  **0.8000** — is what would price that widening.
- **U-40** — a safety property currently supplied by a static extractor failing closed would be
  silently removed by an unrelated coverage improvement in that extractor. The coupling must be written
  down as an interface obligation before either component is touched. **Narrowed 2026-08-03 by the
  clarification at FR-002, and narrowed rather than closed.** The shape U-40 names is a probe reaching
  a route whose methods were *inferred* rather than recovered, and v1 no longer infers methods — they
  come from the target's own published specification. What still probes is FR-046's path-level
  precondition, so the coupling survives at path granularity and the interface obligation is still
  owed.
- **The share of results returned not verifiable is unknown, and one success criterion depends on
  it.** Nothing in feature 001 estimates it, FR-045 makes it a measurement, and no threshold is
  pre-registered. SC-001 asks for a first *verified* answer within fifteen minutes, which a high
  refusal share can defeat without anything in the runtime being wrong — so SC-001 is not independently
  assessable until FR-045 has reported at least once.
- **C-15** — the general fallback path required by FR-004 pushes toward the combination of private
  data, untrusted content and an egress path that the original vision identified as present by
  construction. FR-014 through FR-021 cut the direct channel; they do not cut the target-as-deputy
  channel, which is **U-44**.
- **The source reference is declared, never verified, and one class of wrong declaration is invisible
  to every check in this specification. Added 2026-08-03 with FR-057.** Nothing in v1 establishes that
  the declared repository and commit produced the running deployment, and **OD-06** is the reason
  nothing does: analysis is kept rebuildable from the codebase alone, so no step reads a commit
  identity out of a running instance. A **missing** source reference fails startup loudly (FR-057).
  A **wrong** one splits, and only the narrow half is the risk. Pointing at the **wrong application**
  is caught downstream, because derived contracts are independently validated against the
  specification the deployment itself publishes (FR-002, SC-007) and would fail. Pointing at the
  **right repository at the wrong commit** is caught by nothing: the published specification still
  matches, both clocks agree with each other and disagree only with reality, and **every check in
  this specification passes**, because each is internally consistent with the source it was handed.
  The mitigation available in v1 is honesty about status rather than
  detection, which is why FR-057 requires the reference to be carried and presented as a declaration
  wherever a derived artifact shows it. What would close this is evidence read from the running
  deployment, which is the stage boundary OD-06 drew, so closing it is a decision about that boundary
  and not an implementation task.
- **The human adjudication pass over the frozen oracle negatives was never performed.** A blind pass
  exists and states in its own text that a model performed it. No result resting on that corpus may
  be written up as resting on validated ground truth, and no amount of additional sampling changes
  that. It is open independently of **OD-14**, and it belongs to whoever next touches the corpus.
  **Load-bearing as of 2026-08-03 in a second place.** It is now also the missing precondition on
  FR-052: constitution Principle I would require any model judge in the success path to be calibrated
  against **human** labels, and this is the reason none exist. So the gap does not merely qualify a
  write-up — it is what keeps FR-039's judge in shadow, and closing it is the first step of any
  proposal to give a model verdict influence over behaviour.
- **A freeze that pins artifacts but not their inputs is not a freeze.** The verifier corpus pinned
  246 traces and not the prompts they answered, and every downstream consumer silently re-joined to
  whatever the task file said that day; the join never failed and produced a plausible pairing every
  time. FR-026's provenance requirement is the generalisation of that lesson, and any measurement
  harness built for FR-039 through FR-042 MUST pin its inputs as well as its records.
