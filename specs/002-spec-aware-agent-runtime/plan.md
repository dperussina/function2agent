# Implementation Plan: Spec-Aware Agent Runtime

**Feature**: `002-spec-aware-agent-runtime` | **Date**: 2026-08-03 | **Spec**: [`spec.md`](./spec.md)

**Input**: Feature specification from `specs/002-spec-aware-agent-runtime/spec.md`
(54 functional requirements, 28 success criteria, five user stories, four deviation records)

**Constitution**: v1.2.0 | **Inherited decisions**: **OD-01** through ~~**OD-14**~~ **OD-17**
*(extended 2026-08-03 after the owner reviewed this gate — see the banner under Summary)*
([feature 001 plan](../001-discovery-validation/plan.md)) | **Evidence base**:
[feature 001 verdict](../001-discovery-validation/VERDICT.md)

**Phase 0**: [`research.md`](./research.md) · **Phase 1**: [`data-model.md`](./data-model.md),
[`contracts/`](./contracts/), [`quickstart.md`](./quickstart.md)

---

## Summary

v1 admits one deployed application whose source the operator controls, derives verification signals
statically from that source, and then runs **one agent, one loop, read-only against the target**,
behind an enforcement point that resolves every outbound call per call rather than per tool. What a
caller gets back is a result that has been recomputed against a source-derived contract, or is
labelled as not verifiable, or is labelled as stale — never a claim the runtime cannot support.

The stack is largely not chosen here. It was chosen by measurement in feature 001 and recorded as
**OD-01** (Google ADK for execution, lifecycle, serving and providers; every safety primitive ours —
**partially reversed 2026-08-03 by OD-15**, which drops ADK from v1 entirely; the safety-primitive
half is untouched and was always the load-bearing half),
**OD-02** (our own executor, the Claude Agent SDK an opt-in path rather than the default) and
**OD-12** (one mandatory proxy enforcing destination and method together, re-originating from a
cleartext endpoint rather than intercepting TLS, `CONNECT` denied). This plan applies those and
supplies what they left open.

Three of **OD-01**'s four limbs do not survive contact with a v1 design unchanged, and the plan says
so rather than building against a reading that will not hold — its graph-execution limb has no
subject because v1 emits no graph, its provider-abstraction limb is **measured non-compliant with
FR-037 for one of SC-010's four providers**, and its serving limb is the one thing in OD-01 with no
measurement behind it at all. Each is narrowed or answered in [`research.md`](./research.md) §1.1,
without moving the seam OD-01 actually draws. *(**Superseded in part 2026-08-03 by OD-15**: the owner
read the same three findings and drew the further conclusion that the fourth limb alone does not
justify the dependency. The three findings are unchanged; only the disposition is. See the banner
below.)*

The plan also supplies the three mechanisms the specification deliberately withheld — a per-session
mount namespace for FR-048, cgroup v2 for FR-049, and a four-layer construction for FR-050 in which
**revocation is the default and continuation is the thing that requires work**, so that a crash
revokes without any cleanup code running. It builds instrumentation for all three unmeasured
capabilities rather than the capabilities alone, and it reports two places where a success criterion
is not reachable as written instead of softening it.

~~**Eleven architectural decisions with no evidence behind them and a high cost to reverse are flagged
for the owner** in [`research.md`](./research.md) §5, each with a recommendation. The plan proceeds
on the recommendations.~~

> ## ✅ OWNER REVIEW COMPLETE 2026-08-03 — eleven answered, three not as recommended
>
> **Eight accepted as recommended** (Q-01, Q-02, Q-03, Q-05, Q-06, Q-07, Q-09, Q-10). Three answered
> against the recommendation and promoted to owner decisions in
> [feature 001's plan](../001-discovery-validation/plan.md):
>
> - **OD-15 — ADK is dropped for v1** (answers Q-04 with (b)). This **partially reverses OD-01**.
>   Three of OD-01's four limbs lost their subject or their evidence against a v1 design — graph
>   execution has no graph, provider abstraction is measured non-compliant with FR-037 for one of
>   SC-010's four providers, and serving rests on nothing measured — and the owner held that the one
>   surviving limb, lifecycle, does not justify the dependency. **OD-01 is not deleted and was not
>   wrong**; the product it was taken for is the thing that changed, at OD-09.
> - **OD-16 — `litellm` is not shipped** (answers Q-08 with (b) now rather than later). It declares
>   no license. Each provider is reached through its own SDK.
> - **OD-17 — Linux only** (answers Q-11 as recommended, promoted to an OD because it is a
>   customer-facing product limit rather than a technical-context line).
>
> **What this costs, recorded here because a plan that loses its runtime should say so at the top.**
> OD-15 leaves **eight capabilities with no owner** — the session store, the runner and the loop,
> checkpoint and resume, tool-schema translation, the per-provider cost table, `max_llm_calls` as a
> backstop, the raw terminal signals, and the event stream T-03's surface renders. Finding 006's
> **2.5–3.5 weeks** does not cover any of them and **no re-derived estimate exists in any committed
> artifact.** Two evidence claims narrow with it: finding 006's "two of four missing against a
> threshold of three" was about ADK and is no longer about v1's substrate, and finding 003's
> four-provider result was measured through ADK and LiteLLM, so **SC-010 becomes a test v1 must pass
> rather than a result it inherits.** Both are set out in OD-15 and OD-16.
>
> **The sections below are annotated rather than rewritten.** Every verdict in the Constitution
> Check stands; three of them rested in part on ADK and say so now.

---

## Technical Context

**Language/Version**: Python 3.12 (analysis, runtime, supervisor); Go (the egress enforcement point,
a single static binary — [`research.md`](./research.md) T-05, flagged as **Q-01**); Node 20+ for
`codegraph`, invoked as a subprocess at analysis time only and absent from every run-time image.

**Primary Dependencies**: ~~`google-adk` at its agent/runner and session tier only, not its graph
workflow tier (T-01)~~ — **superseded 2026-08-03 by OD-15: no agent framework at all.** The loop, the
runner and the session store are ours. A `provider_state` opaque envelope of ours (T-02), now held
directly over each vendor's own SDK rather than above a middleware adapter (**OD-16** — no
`litellm`); `codegraph`, version-pinned with a schema-hash assertion in CI (**U-04**); a thin
HTTP/SSE surface of ours (T-03). No agent framework, no graph framework, no durable-execution
engine, no message broker, no vector store, no knowledge-graph store. **The provider driver is the
one place this list got bigger**, and it is the only dependency v1 has on the model-facing path.

**Storage**: SQLite in WAL mode per deployment for sessions, leases, traces, the budget ledger, the
turn journal and drift signals; a content-addressed `objects/<sha256>` store for versioned artifact
payloads; every row keyed by `tenant_id` and `deployment_id` from the first commit (**OD-08**,
FR-035). All access behind one repository interface, no engine-specific SQL above the connection
layer, single-writer-per-table ownership across the three processes (T-06, flagged as **Q-02**).

**Testing**: `pytest` with cassette-backed provider fixtures (constitution Principle VII); `go test`
for the enforcement point, including a framing-ambiguity corpus; committed fixture batteries for
each measurement obligation; an import-graph test asserting the judge module is unreachable from the
result-record path (FR-052); a determinism test asserting byte-identical artifacts across two
analyses of one fixture (T-12).

**Target Platform**: **Linux only**, with cgroup v2, user and mount namespaces, and `seccomp` user
notification. The three mechanisms of FR-048, FR-049 and FR-050 are kernel facilities with no
equivalent elsewhere, so under FR-053 every other platform is **unsupported rather than
best-effort** — operators run the bundle in a Linux VM (~~**Q-11**~~ — **ratified 2026-08-03 as
OD-17**, so this is a recorded product limit rather than a plan assumption).

**Project Type**: Self-hosted multi-container service (**OD-08**): analysis, runtime, supervisor and
enforcement point, plus a per-session sandbox image, shipped as OCI images with a compose bundle we
author (T-11).

**Performance Goals**: None inherited and none invented. SC-001's fifteen-minute window is the only
time-shaped criterion and [`research.md`](./research.md) §7.2 reports that it contains an unbounded
analysis step. The one performance quantity this plan owes a measurement is the syscall supervisor's
overhead on the reference application (**Q-09**), measured before the mechanism is committed.

**Constraints**: Read-only against the target for the life of v1 (**OD-10**). One destination, whose
base-URL string we control — the condition **OD-12**'s re-origination posture depends on and does not
outlive. Bring-your-own-credentials across at least four providers (FR-032, SC-010). No dependency
resolution at run time (FR-021). No model judgement on the success path (constitution Principle I,
FR-052).

**Scale/Scope**: One tenant, one admitted deployment, one agent, one loop. Namespaceable storage
while exactly one tenant exists, because retrofitting it is a migration (**OD-08**).

**Configured values with nothing behind them**, every one bound to FR-043 and forbidden from
travelling externally as validated: FR-049's memory and processor bounds (this plan recommends
failing closed when unset rather than shipping a number — **Q-10**), FR-047's staleness ceiling,
FR-046's detection window, and the credential lease interval this plan introduces at
[`research.md`](./research.md) §3.3.

> **Extended 2026-08-03 — FR-005's four session ceilings belong on this list and were not on it.**
> Spend, token consumption, wall-clock time and turns have no evidence base behind any figure either,
> and the specification was extended the same day to take **Q-10's** treatment rather than FR-047's:
> **required configuration, startup fails loudly when unset, no default stated at all**. They are
> therefore not *configured values with nothing behind them* in FR-047's sense — there is no default to
> mark unvalidated — and they are recorded here because this is the list a reader consults to find out
> which numbers the product invents. **It invents none of these four.** The distinction is deliberate:
> an unvalidated staleness ceiling is a number nobody has checked, whereas an invented spend ceiling is
> an unbounded liability wearing one. `research/14-architecture-synthesis.md` **U-30** is why this
> mattered enough to state — **OD-15** removed ADK's `max_llm_calls`, so nothing occupies the position
> at all until this plan's budget channel is built, and **U-31** is the seam on which the cumulative
> property becomes enforceable rather than merely stated.

---

## Constitution Check

*GATE: evaluated before Phase 0, re-evaluated after Phase 1. Result below is post-Phase-1.*

**Result: PASS**, with three accepted deviations, **one deviation record rejected in part on
substance**, and four obligations this plan adds that the specification did not state. Everything the
plan cannot satisfy is in [Complexity Tracking](#complexity-tracking); nothing is left in a gap
nobody records.

### Principle I — Contract-Derived Verification

**PASS.** v1's derivation is static, with no model in it (T-13) — which costs nothing, since
[finding 007](../001-discovery-validation/findings/007-contract-extraction.md) measured static
derivation at zero model spend. FR-023 makes recomputation against an independently derived path the
only route to a verified result, and FR-024 forbids the derivation and the reported value sharing a
source.

**The v1.1.0 clause — validate a derived verifier against an artifact its own derivation did not
produce, or mark it provisional — is satisfied structurally.** FR-002 makes the target's published
specification an *admission criterion*, so that independent artifact is in hand for every admitted
target before any session starts (T-14). The two-clock structure **OD-06** forced for an unrelated
reason turns out to supply Principle I's independence requirement for free. Contracts that agree with
it are validated; the rest are provisional with provenance and confidence, per FR-026. Finding 007's
measured ratio on one target and one framework suggests roughly a quarter provisional, recorded so
that share is expected rather than alarming, and not generalized.

**The model-judge clause boundary is preserved, and the plan strengthens how.** The specification
scopes the clause to the success path and declares the shadow judge outside it. The plan does not
rely on that being a policy. The caller-visible result record is constructed only by the verification
stage, from the reported value, the recomputed value and the derivation; **the construction path has
no read access to the judge's table, and an import-graph test asserts that the result-record and
gate-decision modules do not depend on the judge module.** The judge consumes the trace stream
asynchronously and writes to a table nothing on the success path reads. So no model judgement can
reach caller-visible behaviour, with or without the pairwise-and-calibrated conditions — the
conditions are not the only thing standing in the way.

One consequence has to be recorded rather than assumed: **FR-040's third gate branch reads the
judge's own discrimination, which needs human ground truth that does not exist**, and the corpus
records that the one adjudication pass it needed was never performed. See
[Complexity Tracking](#complexity-tracking) row 1.

### Principle II — Topology Encodes Protocol · deviation record ACCEPTED, with an obligation added

**Verdict: the spec's argument from scope is correct on the emission clause, and I reject the
counter-reading.** v1 emits no agent system. There is no serialized topology, no node graph, no
promoted function and no artifact for a downstream consumer to read. The clause's subject is absent
because **OD-09** deferred synthesis to v2, and a deferral is not a cancellation — the moment v2
emits a topology the principle binds in full and unchanged.

I looked specifically for a reading on which v1 *does* emit topology, because passing a deviation on
form is the failure mode here. The closest candidate is the served-operation set: it is structured,
versioned, content-addressed and consumed by the enforcement point. It is **data a component resolves
against**, not a control-flow graph and not an emitted agent, and treating it as topology would make
every configuration file a topology. Rejected.

**But the principle's second paragraph is achievable in v1 and the plan adopts it, which the
specification did not require.** v1 has mandatory sequences with real structure — admission precedes
inspection precedes session start; within a call, resolve the effect tier, then allow or deny, then
verify, then report. The plan declares these as a **versioned, machine-checkable invariants file with
tests that run on every change**, in exactly the form the principle asks for and at the cost it
promises. Sample invariants, all testable in milliseconds with no model: no code path constructs a
caller-visible result without a verification outcome; no HTTP client in the sandbox image can reach
any address but the enforcement point; the result-record module does not import the judge module;
every deny disposition carries a rule identifier. This is an addition, not a weakening.

### Principle III — Default to the Loop · deviation record ACCEPTED, and applied to a live choice

**Verdict: correct, and it did real work at this gate rather than being a formality.** v1 promotes no
functions and emits no node graph, so the clause about promoting a function to a node has no subject.

The principle's underlying preference — do not pay for graph machinery you have not earned — **binds
a choice this plan actually had to make**. **OD-01** says the runtime lives inside ADK's *graph*
execution. v1 is one agent and one loop. Running it on ADK's `Workflow` graph tier would be *graph
for a `for` loop*, the failure mode the principle names by that name. So the plan uses ADK's
agent/runner and session tier and not its graph tier (T-01), and forfeits the checkpoint-and-resume
primitive that tier supplies. The forfeit is nominal: finding 006 measured a loop hosted inside a
node losing **4 of 4** completed inner turns on resume, so node-boundary checkpointing would have
journalled nothing v1 needs. This is recorded in [`research.md`](./research.md) §1.1(a) as a
**narrowing** of OD-01 under the house convention, and flagged as **Q-04**.

> **Q-04 answered 2026-08-03 with (b) — [`OD-15`](../001-discovery-validation/plan.md). The verdict
> above is unchanged and the tradeoff it recorded is not.** The principle's application was correct
> and did the work claimed; what changed is what the plan sits on afterwards. The resume tradeoff
> re-runs as follows, and OD-15 carries the full reassessment:
>
> - **The "nominal" argument survives and strengthens.** It rested on finding 006's **4 of 4** inner
>   turns lost, which is a fact about hosting a loop inside a checkpointed node, not about which ADK
>   tier we sat on. v1's loop is the top-level loop either way.
> - **The granularity constraint is gone.** ~~"we forfeit the checkpoint-and-resume primitive that
>   tier supplies"~~ — there is no tier and nothing to forfeit. We are no longer bound to
>   node-boundary granularity by anybody, and T-07's turn-and-step journal is exactly the
>   granularity finding 006 measured ADK unable to offer. Under T-01 that journal would have run
>   inside a loop ADK's own persistence could not see — two mechanisms, two granularities, one
>   session. Now there is one.
> - **And v1 has no measured resume machinery at all, which is worse.** Checkpoint and resume was
>   the primitive finding 006 measured **present and working, reproducible 5/5** — on ADK's
>   event-sourced replay over `SqliteSessionService`. That does not transfer to a journal nobody has
>   written. **Finding 006's "two of four missing against a threshold of three" was about ADK and is
>   not a statement about v1's substrate**; nothing in this plan may cite it as reassurance about
>   v1 any more.
>
> The forfeit was nominal; **the inheritance was not**, and OD-15 spends it deliberately.

### Principle IV — Structural Safety Boundaries

**PASS**, and this is the principle the plan spends most of its mechanism on. Bullet 1 was amended at
v1.2.0 *because* v1 did not satisfy the original, so it gets the closest reading.

| Bullet-1 term | v1 mechanism |
|---|---|
| filesystem scope declared positively | per-session mount namespace containing exactly the declared set; a location outside it is **absent**, not permission-denied ([`research.md`](./research.md) §3.1, FR-048) |
| bounded processor and memory, enforced from outside | cgroup v2 created and owned by the supervisor before the container starts; no writable `cgroup` mount inside; `memory.max` with `memory.oom.group`, `cpu.max` as a rate, cumulative `cpu.stat` as a total, `pids.max` (§3.2, FR-049) |
| egress default-deny with an explicit allowlist | the mandatory re-originating proxy; the sandbox's only route (**OD-12**, FR-014 through FR-019) |
| no credential that outlives the session | the environment holds no long-lived credential at all — the proxy authenticates on its behalf — and its session capability is an opaque handle resolved against a lease on every request (§3.3, FR-050) |

**The interception-point requirement is one component, not four.** Every allow-or-deny decision that
reaches the target passes the proxy, which resolves per call, records the rule that produced the
disposition, and cannot be reached, modified or reconfigured from inside the sandbox because its
configuration is in a different mount namespace and its control plane is in a different network
plane.

**Two additions beyond what the specification requires, both recorded as additions.** The runtime
gets its own default-deny egress plane pinned to the model provider (T-10) — the principle's concern
is the process that puts attacker-influenceable text into a model, and FR-014 through FR-019 do not
cover the runtime. And **the drift scheduler's specification re-fetch runs through the same proxy**,
because otherwise FR-014's single-enforcement-point guarantee is true of the sandbox and false of the
system; that path is continuous and nobody had flagged it
([`research.md`](./research.md) §1.3(b), §8 item 3).

Injection is **not** claimed handled. FR-051 and **U-44** stand as recorded, and
[`research.md`](./research.md) §1.3(c) writes down for the first time that the proxy holding the
target credential makes the effect gate the entire authorization boundary, stacking with U-44.

### Principle V — Two-Tier Provider Abstraction

**PASS, and the plan corrects a measured non-compliance rather than inheriting it.** FR-037 requires
provider-opaque reasoning state to be first-class, round-tripped verbatim, never dropped or merged.
Finding 003 result 7 measured ADK's provider adapter referencing one provider's opaque reasoning
field **zero times**, and finding 003 states the consequence in this principle's own words: silent
degradation of multi-turn tool use rather than an error. SC-010 requires four providers.

So living inside ADK's provider abstraction unmodified would ship the exact failure Principle V
exists to prevent. The plan holds the `provider_state` opaque envelope **above** the adapter, on our
turn record (T-02), which is the two-tier rule applied at the point the measurement says the bottom
tier is thin in the wrong place. ADK remains the transport. A per-provider round-trip conformance
fixture over a long chained tool sequence on a reasoning model asserts byte identity — finding 003
declined to read its passing two-hop case as clearance, and so does this plan.

`litellm`'s undeclared package license is a **distribution** question for a shipped product that no
document in this corpus has treated as one; keeping the driver thin is what keeps it replaceable
(**Q-08**).

> **Answered 2026-08-03 by [`OD-16`](../001-discovery-validation/plan.md) with (b) — replaced now,
> not kept thin against a future swap. The verdict above stands and its mechanism improves.**
> ~~"ADK remains the transport."~~ The transport is each vendor's own SDK, so FR-037's round-trip is
> discharged **in** the driver rather than compensated for above an adapter that references one
> provider's opaque field zero times. That is this principle's two-tier rule in its intended shape
> rather than as a mitigation, and it is the strongest single argument in OD-15's favour.
>
> **The cost is on the other side of the same result and it is not small.** Finding 003 drove four
> providers to a passing chained tool call **through ADK and LiteLLM**. The provider-capability half
> of that transfers — the vendors' APIs do support chained tool calling — and the
> adapter-implementation half does not, because nothing in this corpus has measured any vendor's own
> SDK doing it in our hands. **SC-010 is now a test v1 must pass rather than a result it inherits**,
> and until it passes, no document may cite finding 003 as evidence that the *shipped* configuration
> is provider-agnostic. The conformance fixture at `tests/conformance/` is what closes it.

### Principle VI — Observability Is a Prerequisite

**PASS.** Every model call, tool call, state transition and decision point is traced with inputs,
outputs, timing and cost (FR-005, FR-030). Every denial carries the rule that produced it (FR-011),
and FR-048's filesystem denials are recorded in the same shape — which is the clause that forces the
syscall supervisor (**Q-09**), a cost this plan reports rather than avoids by weakening the clause.
The budget ledger is journalled outside the container as consumption accrues, so a cgroup kill loses
no accounting. **U-47**'s four-part fix is adopted verbatim in the measurement harness, per FR-053.

### Principle VII — Test-First and Fixture-Backed · deviation record **ACCEPTED IN PART, REJECTED IN PART**

This is the one deviation record the plan does not pass as written.

**Accepted.** The generator clause has no subject: v1 emits no agent system, so there is no generated
artifact to test. Same ground as Principle II, and correct for the same reason.

**Accepted.** The analyzer clause binds and is closed — fixture repositories with known-correct
expected output, per FR-053's requirement that fixtures be committed alongside the capability.

**Accepted.** The integration-surface clause binds and is closed by FR-033's fail-loud configuration
and FR-044's contract tests, over the HTTP/SSE surface of T-03.

**Rejected in part — the determinism clause.** The record said the byte-stability half "has no
subject either" because v1 emits no artifacts. **It has a subject: FR-054's eight artifact kinds.**

> ~~The correction was carried here, in full, because the plan phase does not edit `spec.md`
> mid-gate.~~ **Moved 2026-08-03 into the specification, where it belongs.** The narrowing is now
> **FR-055** — canonical serialization as a requirement, with byte-identical re-derivation from
> unchanged input — measured by **SC-029**, and the Principle VII disposition in
> [`spec.md`](./spec.md) carries the struck clause and the pointer. **This record no longer carries
> the correction; it records that the rejection was made and where it landed.** The substance is
> unchanged: content addressing over a non-canonical serialization yields a different address on
> every re-analysis of identical input, and a changed address on the source-derived artifact is
> exactly what FR-028 reads as source drift — a false-alarm generator aimed at the one v1 capability
> with no measured false-alarm rate.

The obligation the plan took on is now a stated requirement rather than a plan-side addition:
**canonical serialization for every artifact FR-054 names, with a determinism test asserting byte
identity across two analyses of one fixture** (T-12, FR-055, SC-029). Sorted keys, fixed numeric
formatting, `LF`, `UTF-8` without a byte-order mark, and no timestamp, path or hostname inside the
hashed payload.

Also added, since the specification does not capture it for v1: **cassette-backed provider tests**,
which the principle requires by name.

### Principle VIII — Versioned Artifacts, Earned Complexity · deviation record ACCEPTED

**Verdict: correct on the versioned-artifact clause's *emitted* subject, and the earned-complexity
clause binds in full and is discharged item by item.** FR-054 already gives v1 versioning, content
addressing, rollback and one-command restoration for the artifacts it does produce, so the clause's
substance is satisfied even where its literal subject is absent.

Every new layer, justified against a named failure mode:

| Layer | Failure it prevents |
|---|---|
| ~~ADK, at its agent and session tier~~ — **removed 2026-08-03 by OD-15** | ~~rebuilding the four-provider tool-calling path finding 003 measured working, which is SC-010's entire basis~~. **This row's justification inverted rather than lapsing, and that is the honest reading**: v1 *is* now rebuilding that path, so the failure this layer prevented is one v1 has taken on. It is spent knowingly against three limbs of OD-01 that had no subject or no evidence, and SC-010 becomes a test rather than an inheritance (**OD-16**) |
| **our own loop, runner and session store** *(added 2026-08-03)* | nothing prevents a named failure here — this layer exists because OD-15 removed the one that supplied it. It is a **cost of that decision, not a justification**, and it is recorded in this table so it is not invisible. Eight capabilities, no committed estimate |
| **a provider driver of ours over each vendor's SDK** *(added 2026-08-03)* | FR-037's round-trip failing silently for one of SC-010's four providers — finding 003 result 7 measured the adapter this replaces referencing xAI's opaque field **zero times** — plus the undeclared package license OD-16 names |
| our own safety layer over it | two of four loop-safety primitives measured missing against a threshold of three (finding 006) |
| the enforcement point as a separate process | Principle IV bullet 1's egress term, and an allow-or-deny decision the sandbox can reach |
| **Go for that process specifically** | a parser differential at the one point where disagreeing with the target about the method and path defeats FR-018 entirely (**Q-01**) |
| the syscall supervisor | FR-048's recording clause and SC-022, which a mount namespace enforces and cannot record (**Q-09**) |
| the turn journal | **U-30** — nothing in the stack supplies a spend ceiling surviving a crash and resume |
| the adjudication queue | FR-040's third branch, uncomputable without human labels |

**Rejected as unearned for v1**, each named rather than silently omitted: a durable-execution engine
(**Q-03**), a graph framework, PostgreSQL (**Q-02**), a knowledge-graph or vector store, a message
broker, Kubernetes, and OD-02's opt-in Claude Agent SDK path (**Q-06**).

**Added obligation**: v1 both consumes and produces schema'd artifacts, so schema versioning with a
migration path is required from the first commit, and a breaking change to a consumed or produced
schema is a MAJOR bump under FR-034.

### Deferred scope — OD-09 checked item by item

A plan is where deferred scope creeps back in. Tool synthesis, promotion selection, static per-tool
effect classification, the knowledge-graph memory layer, the iframe and multi-agent artifact trading
are each checked against every decision in [`research.md`](./research.md) §6. **None is present.**
The `codegraph` index is an analysis-time input, not a memory tier; the served-operation set is data
the enforcement point resolves against, not a generated tool surface; effect resolution is per call
at the enforcement point, which is the obligation staying while the differentiator defers.

---

## Project Structure

### Documentation (this feature)

```text
specs/002-spec-aware-agent-runtime/
├── spec.md                      # Input (/speckit-specify)
├── checklists/requirements.md   # Input (/speckit-checklist), 16/16
├── plan.md                      # This file (/speckit-plan)
├── research.md                  # Phase 0 — decisions T-01..T-14, mechanisms, owner questions Q-01..Q-11
├── data-model.md                # Phase 1 — entities, lifecycles, invariants
├── contracts/
│   ├── README.md
│   ├── configuration.md         # FR-033 environment injection, fail-loud rules, required-vs-unset
│   ├── egress-policy.md         # FR-008..FR-019 — what the enforcement point accepts and denies
│   ├── result-record.md         # FR-025, FR-026, FR-047 — the caller-visible contract
│   ├── trace-record.md          # FR-030, FR-053 — span shape and the U-47 pinning terms
│   └── artifact-versioning.md   # FR-027, FR-034, FR-054 — canonical form, addressing, rollback
├── quickstart.md                # Phase 1 — the SC-001 path and the validation scenarios
└── tasks.md                     # Phase 2 (/speckit-tasks — NOT created by /speckit-plan)
```

### Source code (repository root)

The repository has no source tree yet; this feature creates it. Four deployable components plus a
sandbox image, matching the process boundaries the safety design depends on — the boundaries are
load-bearing, so the layout follows them rather than a layered convention.

```text
src/
├── analysis/            # Python. Admission, codegraph subprocess, contract and check derivation,
│                        # canonical serialization, the content-addressed artifact store
├── runtime/             # Python. The agent loop, runner and session store — ours, on no
│                        # framework (OD-15); the provider driver over each vendor's SDK
│                        # (OD-16); the opaque
│                        # provider-state envelope; budget ledger; turn journal; verification
│                        # stage; drift scheduler; the HTTP/SSE surface; the shadow judge
│                        # (isolated — nothing on the success path imports it)
├── supervisor/          # Python. Session lifecycle, mount-namespace assembly, cgroup ownership,
│                        # the seccomp notification listener, lease renewal, teardown
├── proxy/               # Go. The single enforcement point: method+destination allowlists,
│                        # per-call effect resolution, TLS re-origination, credential injection,
│                        # session-handle resolution, the decision log
├── contracts/           # Python. Shared schemas, canonical serializer, schema versions/migrations
└── sandbox/             # The execution environment image: shell and toolchain, no secrets,
                         # no package index reachable, dependencies resolved at build time

tests/
├── contract/            # HTTP/SSE surface, egress policy, result record, configuration fail-loud
├── integration/         # End-to-end against the reference application
├── unit/
├── invariants/          # Principle II's machine-checkable invariant set (import graph,
│                        # reachability, constructor paths, rule-identifier presence)
├── conformance/         # Per-provider opaque-state round-trip, cassette-backed
├── fixtures/            # Committed per FR-053: analyzer repos, drift corpora, adversarial
│                        # batteries, the credential-replay fixture, effect-gate corpus
└── batteries/           # The measurement harnesses for FR-039..FR-042

deploy/
├── compose/             # The bundle we author (T-11); reference-application values marked FR-043
└── images/
```

**Structure Decision.** Component boundaries follow **process and privilege** boundaries, because
that is what makes the safety properties checkable rather than asserted: the supervisor owns
resources the runtime must not be able to raise, the enforcement point holds a credential the sandbox
must never see, and the sandbox holds nothing. `tests/invariants/` exists as a first-class directory
because Principle II's second paragraph is adopted as an obligation, and `tests/conformance/` because
FR-037's round-trip is a per-provider property that unit tests cannot express.

---

## Complexity Tracking

Everything the plan cannot satisfy, in the section that records it.

| Violation / unsatisfied item | Why it stands | Simpler alternative rejected because |
|---|---|---|
| **SC-013's thirty-day window is not reachable as written.** FR-040's third gate branch reads the judge's own discrimination, which requires human ground truth. The corpus records the one adjudication pass it needed was never performed, and a model stood in | Constitution Principle I requires calibration against human labels. The plan builds an adjudication queue — pre-registered sampling, an operator surface, `human_label` rows — and reports that the window opens only once labelling capacity exists | Using the verifier's verdict as ground truth is circular: the verifier is the thing being compared. Using a model is the exact substitution FR-052 exists to prevent |
| **SC-001 contains an unbounded step.** A *verified* first answer requires analysis to complete, and **U-21** records `codegraph`'s scale claim as untested with one small-repository datapoint | Reported, not softened. The plan instruments analysis wall time separately and states the reference application's size wherever SC-001 is reported, so the criterion is assessable rather than quietly true on small inputs | Excluding analysis from the window would weaken the criterion; bounding the reference application would change what SC-001 measures. Both are owner calls, not plan calls |
| **SC-024's recording clause is not uniform.** A replay reaching the enforcement point is denied and recorded; a replay with no path to it is refused by unreachability and recorded only as a drop counter | The topology, not the design, produces the difference — nothing receives a connection that cannot be made. The fixture exercises both arms and reports them separately | Pooling both into one **100%** would report a recording property the topology does not have |
| **FR-050 leaves a residual window of one lease interval** in the narrow case where the supervisor survives but the session row was not updated | Disclosed, configurable, marked unvalidated under FR-043, and measured by the replay fixture. The common crash closes instantly, because the per-session listener is a file descriptor the kernel closes when the supervisor dies | A self-describing token with an expiry is honoured by anyone who can verify it, whether or not anything is alive to revoke it — which is the failure this requirement names. A shutdown-path revocation assumes a cleanup path runs; finding 006 used `SIGKILL` from a separate process precisely to make that assumption false |
| **FR-048's recording clause forces a syscall supervisor whose overhead is unmeasured** | SC-022 requires **100%** of refusals recorded, and a mount namespace records nothing — the attempt fails inside the container and nothing outside learns. Reported as a cost; measured on the reference application before commitment (**Q-09**) | Namespace-only satisfies the enforcement clause and fails the recording clause. Inferring denials from command output is heuristic and would be classification, which FR-013 forbids |
| **A second language (Go) at the enforcement point** | A parser differential between the proxy and the target defeats FR-018 completely, and FR-018 is what makes the method allowlist meaningful (**Q-01**) | Python keeps one toolchain and gives a weaker framing-ambiguity posture at the one component where that bug class is fatal. Envoy is strong but puts a large dependency in a self-hosted install for a single-upstream policy, and the security-critical decision stays ours regardless |
| **Deployment-clock drift latency is not measurable on real traffic** unless the customer emits a deployment event, which FR-046 says may not be assumed | A property of the world: a deployment change generally has no observable change time. Measurable on the committed synthetic corpus, which controls the change time, and on real traffic only where the optional trigger exists | Inferring the change time from first observation measures the detector against itself |
| **FR-041's threshold is left unset** | Pre-registration for a **per-call** gate is an owner act preceding measurement. **OD-10** records why the superseded per-tool number does not travel: different base rate, different blast radius | Inventing a threshold here is the inherited-number failure arriving through a new door — the failure this corpus has caught repeatedly |
| **Linux-only, with no degraded mode elsewhere** (~~**Q-11**~~ → **OD-17**, 2026-08-03) | All three FR-048/049/050 mechanisms are kernel facilities | A degraded mode is a sandbox missing one of Principle IV bullet 1's terms, and the bullet's own words are that a configuration missing any term does not satisfy it |

---

## Phase status

| Phase | Status | Output |
|---|---|---|
| 0 — Outline & Research | Complete | [`research.md`](./research.md) — T-01..T-14, the three mechanisms, the three measurement obligations, Q-01..Q-11, impracticalities, unflagged findings |
| 1 — Design & Contracts | Complete | [`data-model.md`](./data-model.md), [`contracts/`](./contracts/), [`quickstart.md`](./quickstart.md) |
| Constitution re-check after Phase 1 | PASS | Above; nothing in Phase 1 changed a verdict |
| 2 — Tasks | Not run | `/speckit-tasks`, after owner review of this gate |

**No `NEEDS CLARIFICATION` marker survives.** What remains open is eleven owner decisions with
recommendations ([`research.md`](./research.md) §5) and four configured values with nothing behind
them, each bound to FR-043.
