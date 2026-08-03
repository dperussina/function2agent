# Feature Specification: Spec-Aware Agent Runtime

**Feature Branch**: `002-spec-aware-agent-runtime`

**Created**: 2026-08-03

**Status**: Draft

**Input**: User description: "Ship v1 of function2agent: a spec-aware agent runtime that operates a customer's running application through the application's own published specification, a contract-derived verifier that recomputes reported results against an independent source, and drift detection that fails closed when either the analysed source or the deployed surface moves. v1 is read-only, self-hosted first, provider-agnostic on bring-your-own credentials, and confines all outbound traffic to a single enforcement point outside the agent's control. All three capabilities ship with their differentiating claims unmeasured, so instrumenting and reporting those measurements against real traffic is part of the deliverable."

## Context

This is the production specification. It follows feature 001, which planned fifteen numbered
experiments, reached nine ladder positions, ran eight of them, and closed with a verdict
([`VERDICT.md`](../001-discovery-validation/VERDICT.md)). Its binding scope decisions are the owner
decision log OD-01 through ~~OD-14~~ ~~OD-17~~ **OD-20** in [`plan.md`](../001-discovery-validation/plan.md)
*(extended 2026-08-03: **OD-15** drops ADK for v1 and partially reverses OD-01, **OD-16** removes
`litellm` from the shipped product, and **OD-17** makes Linux the only supported platform. None of
the three changes a requirement in this document; all three change what the plan builds against)*.
**Extended again 2026-08-03 with OD-18, OD-19 and OD-20, and these three are not inherited scope —
they are this document's own clarify-session decisions, finally written down.** They were taken on
2026-08-03, applied to the requirement text below on the day, and never recorded in the decision log,
so until now FR-002, FR-044, FR-025, FR-045, FR-029 and FR-046 rested on an owner authority that
appeared nowhere. No requirement changes; each now names the decision that authorises it. **OD-18 is
the consequential one** — a published machine-readable specification is an admission criterion, which
narrows what v1 accepts.

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
> retroactive record and why. The **fourth** answer below — the staleness disposition that became
> FR-047 — **still has no decision record**, and recording it is an owner act rather than a
> propagation one; the note at OD-20 says so rather than leaving it implicit.

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
  which it denies (FR-047, SC-021).

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
  > FR-047 exists to prevent.
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
- **FR-017**: Loopback, private, link-local and cloud-metadata addresses MUST be denied even when
  they are reached through an allowlisted host.
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
  > what may be inferred from the disable-the-affected-operation clause, not its truth.
- **FR-031**: Every drift signal MUST state which of the two clocks moved, the artifact versions
  before and after, and the deployment identity it applies to.

  > **Narrowed 2026-08-03 by FR-047 — narrowed, not wrong.** Where the drift signal is a *failed
  > re-fetch* under FR-047 there is no "after" artifact version to state, because no artifact was
  > obtained. In that one case the after term is the specification state found, named from FR-044's
  > four-state classification, together with the timestamp of the last successful fetch. Every other
  > term of this requirement is unchanged, and no other drift signal is affected.
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

- **FR-038**: From the first shipped capability, every session MUST produce one trace record per
  executed node carrying a versioned node identity, a typed terminal, the routing decision together
  with the inputs its predicate saw, precondition and postcondition results, an explicit distinction
  between a retry and a repair, and per-node cost.

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

**Artifact versioning and rollback**

- **FR-054**: Every artifact the system produces or consumes as configuration or as derived state —
  the served-operation set, derived contracts and derived checks, the effect-gate rule set and its
  deny list, the egress policy, FR-048's declared location set and FR-049's bounds, and the admission
  decision — MUST be versioned and content-addressed, and **restoring the immediately prior version
  of any one of them MUST be a single operator action**: no hand-editing of individual entries, no
  reconstruction from a trace, and no restart of the runtime. A restoration MUST be recorded exactly
  as a widening is under FR-019 — the operator, the version restored from, the version restored to —
  and MUST be subject to the same review as FR-012. FR-026 and FR-027 already require provenance,
  content hashing, and the two drift artifacts to be versioned independently; what this requirement
  adds is that those versions be **navigable**, because a version nobody can return to is a record
  rather than a control, and constitution Principle VIII requires rollback to be one command.
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
  on a matched corpus of correct results.
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
- **SC-012**: For **100%** of sessions, a failure can be attributed from the trace alone to a versioned
  node, a typed terminal, and the routing decision that reached it, without re-running the session.
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
  because none is pre-registered.
- **SC-020**: On the synthetic deployment-drift corpus, **100%** of withdrawn operations are detected
  within the configured detection window under the default automated trigger and with no event
  supplied by a deployment pipeline, and **100%** are detected on demand under manual invocation.
- **SC-021**: On a fixture that withdraws an admitted target's published specification and later
  restores it, **100%** of results returned while the served-operation set is stale carry a
  machine-readable stale marking with the set's age; **zero** calls are served after the configured
  staleness ceiling elapses; **zero** sessions end in a generic error at the ceiling; and **100%**
  of the operations that differ between the last-known-good set and the restored set are reported as
  drift rather than adopted silently.
- **SC-022**: Across an adversarial battery run from inside the agent's execution environment, **zero**
  reads and **zero** writes succeed outside the declared set of filesystem locations — including
  attempts against the effect-gate rule set, against the egress policy, and against another session's
  artifacts — **zero** partially succeed, and **100%** of the refusals are recorded in the trace with
  the rule that produced them.
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
| **D-01** | Calls reach the target over its existing external interface, never in process |
| **D-07** | Two physically separate credential planes; no secret in model context |
| **D-17** | Provenance, independent validation, provisional marking and deployment identity on every derived field |

## Dependencies

- **The constitution at v1.2.0** ([`.specify/memory/constitution.md`](../../.specify/memory/constitution.md)).
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
  per-node cost to be *observable* and Principle I lists cost among a node contract's fields; neither
  requires a ceiling, and observability is not enforcement. FR-005's other three dimensions therefore
  rest on this specification and on `research/14-architecture-synthesis.md` **U-30**, not on a
  principle. That is recorded here rather than closed: whether the constitution should carry a spend
  bound is an amendment question and an owner act.

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
  measured, [`plan.md`](../001-discovery-validation/plan.md) for OD-01 through ~~OD-14~~ **OD-17**, and
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
