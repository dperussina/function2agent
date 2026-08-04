# Phase 0 Research — Spec-Aware Agent Runtime

**Feature**: `002-spec-aware-agent-runtime` | **Date**: 2026-08-03 | **Phase**: 0 (`/speckit-plan`)

**Spec**: [`spec.md`](./spec.md) · **Plan**: [`plan.md`](./plan.md) · **Constitution**: ~~v1.2.0~~ **v1.3.0** *(OD-22, 2026-08-03)*

---

## How to read this

This is the first artifact in the feature that is allowed to name a technology. Everything before it
deliberately did not: the specification names no language, framework, library or wire protocol, and
its own quality checklist scored that as a deliberate pass.

Most of the stack is **not** decided here. It was decided in feature 001 and recorded as owner
decisions **OD-01** through ~~**OD-14**~~ **OD-21** in that feature's
[`plan.md`](../001-discovery-validation/plan.md), which is the authority for the register's extent.
*(**Range corrected 2026-08-03**, and the reasoning is recorded because a prior pass deliberately
left it alone. The sentence was read as a claim about **provenance** — which decisions came out of
measurement in feature 001 — on which reading stopping at OD-14 was defensible, since what followed
came from owner sessions instead. **It is an extent claim.** The corpus uses this exact construction
at three other live sites — twice in [`spec.md`](./spec.md) and once in the header of
[`plan.md`](./plan.md) — and maintains each of them by striking the superseded bound and advancing
it, so this one is corrected to match rather than reworded around. *(A fourth occurrence, in
[`checklists/requirements.md`](./checklists/requirements.md), is left at OD-14 on purpose: it records
what a dated validation run read, and advancing it would claim coverage that run did not have.)* The provenance point is true and
is now carried in words instead of by the bound: **the first fourteen came out of feature 001's
measurements and adjudications; OD-15, OD-16 and OD-17 are the owner's answers to §5 below; and
OD-18, OD-19, OD-20 and OD-21 came from the production specification's clarify session and were
recorded retroactively.** The words `by measurement` were dropped from the sentence above for the
same reason — true of the first fourteen, not of the seven after them, and the split is now stated
rather than smuggled into a bound. **And a note on what guards this, which is nothing**: `tools/README.md`
records `register-range` as unable to read a whole-register claim written as ordinary prose, and
neither the checker nor `gen_claims.py` treats the sentence above as a site — verified 2026-08-03 by
running both. This bound is maintained by a reader noticing, which is how it came to be seven entries
behind while the corpus's other three sites were kept current.)* §1 records how each binding one is honoured, and —
*(**Updated 2026-08-03.** The owner has since answered every question in §5, and three answers became
**OD-15**, **OD-16** and **OD-17**. OD-15 partially reverses OD-01 and is annotated at §1.1, T-01,
T-02, T-03, T-04, T-06 and T-08. Nothing below is deleted and no measurement is amended.)* —
more usefully — **the three places where one of them does not survive contact with a v1 design**.
§2 decides what feature 001 left open. §3 supplies the three mechanisms the specification
deliberately withheld. §4 builds the three measurement obligations. §5 is the list of choices that
have no evidence behind them, would be expensive to reverse, and are therefore **flagged for the
owner rather than made silently**.

Two things this document is not allowed to do, restated so they can be checked against it. It may
not **weaken** the specification: where a requirement turned out to be impractical, §7 says so
rather than softening it. And it may not **re-admit** what **OD-09** deferred; §6 is the standing
list, checked item by item against every decision below.

Identifiers in this document: **`T-nn`** is a technology decision made here, **`Q-nn`** is a
decision flagged for the owner. Neither namespace exists elsewhere in the corpus, so nothing here
can be mistaken for an inherited decision.

---

## 1. Inherited decisions, and where they meet a v1 design

### 1.1 OD-01 — ADK for execution, lifecycle, serving and providers; every safety primitive ours

> ## ⚠️ SUPERSEDED IN PART 2026-08-03 BY **OD-15** — READ THIS BEFORE §1.1
>
> **The owner read this section and drew the opposite conclusion from it.** §1.1 finds three of
> OD-01's four limbs unable to survive contact with a v1 design and narrows each one; **OD-15** finds
> that a fourth limb standing alone does not justify the dependency and **drops ADK for v1
> entirely**. v1 owns the loop, the session lifecycle and the operator-facing surface, and reaches
> each provider through that vendor's own SDK under **OD-16**.
>
> **§1.1 is left as written and is not struck**, because it is the analysis the decision was taken
> on and because every one of its three findings is still correct — what changed is only the
> conclusion drawn from them. Read it as the *argument*, not as the disposition. Where it says
> "ADK remains the transport" (b) or "we are not on the graph tier" (a), those are the readings
> OD-15 replaced.
>
> **What OD-15 costs, so it is visible here and not only two documents away.** Eight capabilities
> ADK was carrying have no owner in v1 — the session store, the runner and the agent loop itself,
> checkpoint and resume, tool-schema translation across four wire formats, the per-provider token
> cost table, `max_llm_calls` as a backstop, the raw terminal signals, and the event stream the
> serving surface renders. Finding 006's **2.5–3.5 weeks** was scoped to loop safety on top of an
> adopted runtime and does not cover any of them; **no re-derived figure exists and none is invented
> here or in OD-15.** The resume-primitive tradeoff and the fan-out hazard are both reassessed in
> OD-15 rather than here.

**Honoured.** The seam **OD-01** draws is *execution versus safety*, and the plan draws it in the
same place. What v1 takes from ADK is agent execution, session lifecycle and persistence, and the
provider adapter. What v1 builds is the whole of the safety layer: budget accounting across all four
of FR-005's dimensions surviving resume, the named terminal taxonomy of FR-006, journaling and
idempotency for FR-007, and deterministic ordering under fan-out.

That is not a re-litigation. It is the decision applied, and it rests on
[finding 003](../001-discovery-validation/findings/003-runtime-provider-agnosticism.md), which drove
four providers to a passing chained tool call, and
[finding 006](../001-discovery-validation/findings/006-graph-loop-primitives.md), which found two of
four loop-safety primitives missing against a pre-registered threshold of three.

**Three of OD-01's four limbs need something said before they can be built against.** None of the
three is a disagreement with the decision; each is the decision meeting a v1 that did not exist when
it was written.

#### (a) "Graph execution" has no subject in v1 — narrowed to agent execution

**OD-01** says we live inside ADK's *graph* execution, and finding 006 measured that tier. v1 emits
no graph and promotes no functions: it is one agent holding general capabilities (FR-004), which the
specification's Assumptions state and its Principle III deviation record restates. Running a
single-agent loop on ADK's `Workflow` graph tier would be *graph for a `for` loop* — the failure mode
constitution Principle III names by that name.

**Decision (T-01, below): v1 uses ADK's agent/runner and session tier, not the graph workflow tier.**

The cost of that has to be stated, because it forfeits the one primitive finding 006 found working.
Checkpoint and resume is supplied at the `Workflow` tier by event-sourced replay; leaving that tier
means supplying resume ourselves. **The forfeit is nominal rather than real**, and finding 006 is
what says so: it measured a loop hosted inside a node losing **4 of 4** completed inner turns on
resume, because ADK checkpoints at node boundaries and a hosted loop is opaque to it. v1's loop *is*
the top-level loop, so ADK's node-boundary resume would have journalled nothing v1 needs. The turn
journal was already the largest item in **OD-01**'s estimate and it is unchanged by this.

> **What this narrows, in the house form.** ~~"We live inside ADK's graph execution."~~
> **Narrowed 2026-08-03 — narrowed, not wrong and not superseded.** True of the product OD-01 was
> written for, which emitted graphs. v1 emits none, so the clause has no subject and the operative
> reading is *ADK's execution and lifecycle*. Nothing about the seam moves: ADK still executes, we
> still own every safety primitive. **OD-09** is what removed the subject, and the moment v2 emits a
> topology the clause binds again in full.

#### (b) "Provider abstraction" is measured non-compliant with FR-037 for one of the four providers

This one is a genuine conflict and, as far as this pass can tell, **nobody has connected the two
sides of it**.

FR-037 requires provider-opaque reasoning state to be a first-class value on every turn,
round-tripped verbatim, never dropped and never merged — which is constitution Principle V restated
as a requirement. SC-010 requires the User Story 1 battery to complete against at least four
independent providers.

Finding 003 result 7 measured ADK's `LiteLlm` adapter against exactly that clause. The adapter
handles Anthropic thinking blocks and Gemini thought signatures; it references xAI's opaque
reasoning field **zero times, under every counting rule the finding's own correction enumerates**.
Finding 003 states the consequence in Principle V's own words — dropping it "degrades multi-turn tool
use silently rather than erroring" — and explicitly declines to read its passing two-hop chained
tool call as clearance.

So *living inside ADK's provider abstraction unmodified* would ship a v1 that drops opaque state on
one of the four providers SC-010 requires, silently, in the direction that produces wrong behaviour
rather than an error.

**Design response (T-02).** The `provider_state: opaque` envelope is **ours**, held on our turn
record, above the adapter — captured from the raw provider response and re-injected into the next
request, per provider, with no merging across providers and no interpretation of the bytes. ADK
remains the transport. This is precisely constitution Principle V's two-tier rule applied at the
point where the measurement says the bottom tier is thin in the wrong place, and it is what finding
003's own third packaging consequence argues for independently.

**And it needs a test that would actually catch the loss**, which finding 003's next step 5 asks for
in as many words: a long chained tool sequence on a reasoning model per provider, asserting the
opaque field is byte-identical on the way out to what came in — not the two-hop trivial case that
passed.

#### (c) "HTTP/SSE serving" is the one limb of OD-01 with no measurement behind it at all

Finding 003's *What this does NOT license* says plainly: nothing about ADK's HTTP/SSE serving layer,
sessions, graph workflows or Agent Engine coupling. Finding 006 says the same and adds an
interaction: graph-based workflows do not support live streaming, so the terminal-condition wrapper
and the serving surface interact in a way neither probe touched.

v1 needs *an* operator-facing surface — SC-001 measures an operator reaching a first verified answer,
and constitution Principle VII requires the HTTP/SSE contract to have contract tests that fail closed
on malformed configuration.

**Design response (T-03).** v1 owns a thin operator-facing HTTP/SSE surface over our own loop rather
than adopting ADK's serving layer. Three reasons, in order of weight. It is the only limb of OD-01
resting on nothing measured. Under (a) we are not on the graph tier, so the streaming interaction
finding 006 flagged is not even the relevant question any more. And the surface must carry v1-specific
fields nothing in ADK models — FR-025's three verification states, FR-047's stale marking as a
separate field, and the FR-011 denial record — so adopting a generic surface would mean wrapping it
anyway.

This is the one place the plan takes *less* of ADK than OD-01 permits. It is recorded as **Q-05** for
the owner because OD-01 named serving explicitly.

### 1.2 OD-02 — our own executor; the Claude Agent SDK as an opt-in fast path

**Honoured, and v1 declines the opt-in half for lack of a subject.**

**OD-02**'s binding reason is bring-your-own-credentials as a hard requirement, not a performance
trade: a customer bringing only one vendor's credential must get a working system. v1 restates that
as FR-032, FR-037 and SC-010, so the decision applies unchanged and the executor is ours on ADK.
*(**Narrowed 2026-08-03 by OD-15**: the executor is ours, full stop — the trailing "on ADK" has no
subject. OD-02's binding reason and this section's conclusion are untouched.)*

The opt-in half was scoped to **coding nodes**, and v1 has none — it emits no code and promotes no
functions. Its shell (FR-004) is a general fallback for operating the target, not a coding harness.
Shipping the Claude Agent SDK path in v1 would therefore buy no v1 capability while spending the
input-context tax finding 003 measured at forty times ADK's for identical work, against FR-005's
token ceiling.

**Decision: v1 does not build the Claude Agent SDK path.** This is OD-02 applied, not amended —
OD-02 says the SDK *stays available*, which is a permission and not an obligation. Recorded as
**Q-06** so the owner sees the declination rather than discovering it.

### 1.3 OD-12 — one mandatory re-originating proxy, destination and method together, CONNECT denied

**Honoured in full, and it is the load-bearing mechanism of the whole design.** The proxy is where
FR-008's blocking resolution, FR-014's single enforcement point, FR-015's paired allowlists,
FR-016's pinned addresses, FR-017's address-class denials and FR-018's readable method and path all
land, on one component.

The posture is **re-origination and not interception**, exactly as OD-12 ratified it. The sandbox is
handed a cleartext endpoint on the proxy as the target's base URL; the proxy reads method and path in
the clear, applies the method allowlist and the deny list of known side-effecting reads, resolves the
request against the served-operation set, and then makes its own TLS connection outbound to the
pinned address with ordinary certificate validation. No CA enters the sandbox, no certificate pin is
required of the operator, and the sandbox needs no resolver because its only reachable address is the
proxy. `CONNECT` is denied, `Upgrade` is denied, and non-HTTP bytes are denied by having nothing to
speak to.

OD-12 also records why this works and where it stops: it works **because v1 has exactly one
legitimate destination whose base-URL string we control**, and it does not generalize past that. The
plan carries that boundary forward verbatim rather than inheriting it.

**Three things about OD-12 that do not survive contact with a design unchanged.**

#### (a) The absolute-URL cost is systematic for paginated targets, not an inconvenience

OD-12 lists this as cost ① — a pagination `next` link or a URL copied out of the specification points
at the target's real hostname, the sandbox cannot make that connection, and the request fails
closed. That description is correct and it understates the frequency: for any target that paginates
with absolute links, it is not an edge case, it is *every page after the first*. The
target's published specification also names its real origin in its own server block, so the agent is
being handed the wrong address by the very artifact admission required it to publish.

**Design response (T-09), in three parts, none of which is TLS interception or body rewriting.**

1. The served-operation set is presented to the agent as **method and path templates relative to the
   proxy base URL**. The agent is never handed the target's real origin.
2. The proxy **accepts an absolute-form request-target naming the pinned target's origin** over the
   cleartext link and re-originates it identically, under the same method allowlist. An agent that
   echoes an absolute `http://` URL out of a response body therefore still works, and it is still one
   destination and one policy.
3. An absolute `https://` URL still fails, because making it work requires either terminating TLS in
   the sandbox — rejected by OD-12 for four stated reasons — or rewriting response bodies, which is a
   content transformation applied to untrusted data and a new injection surface. **It fails closed
   with a named denial reason and a counter.** The counter is the point: if that reason dominates
   real traffic, that is evidence for revisiting the posture in v2, and OD-12 already says
   re-origination does not generalize. Recorded as **Q-07**.

Body rewriting is rejected rather than deferred. Nothing in v1 should transform attacker-influenceable
bytes on the enforcement point's path.

#### (b) FR-014's "single enforcement point" is true of the sandbox and there are two other egress paths

FR-014 scopes its single-enforcement-point rule to *the agent's execution environment*. Two other
things in v1 make outbound connections, and neither is inside that environment:

- **The runtime calls the model provider.** It must — it holds the model credential, which FR-050
  forbids the execution environment from being able to read at all.
- **The drift scheduler re-fetches the target's published specification** every interval (FR-046),
  forever, for the life of the deployment.

The second one matters and **nobody appears to have flagged it**: if the scheduler fetches the
specification on its own socket, then there is a second, unenforced path to the target running
continuously, and FR-014's guarantee is true of the sandbox while being false of the system.

**Design response (T-10).** Two egress planes, one enforcement point each, and they are not the same
point.

| Plane | Who | Enforcement point | Pinned destinations |
|---|---|---|---|
| **A — agent** | the execution environment | the mandatory proxy (OD-12) | the target, host-and-port, one address |
| **B — runtime** | the runtime and the scheduler | the runtime container's own default-deny egress policy | the configured model-provider endpoints, host-and-port |

**The specification fetch runs through Plane A's proxy**, not Plane B, so there is genuinely one
policy governing every byte that reaches the target. Plane B carries no route to the target at all.

Plane B is an **addition** to what the specification requires, not a reading of it: FR-014 through
FR-019 govern Plane A and say nothing about the runtime. It is added because constitution Principle
IV bullet 1 applies to the process that puts attacker-influenceable text into a model, and because a
runtime with open outbound network is **C-17** re-arriving one container over.

#### (c) The proxy holds the target credential, which is a confused deputy of our own construction

This falls out of re-origination and it is the mechanism that discharges FR-050's *not present* term
for the target plane — see §3.3 — so it is a strong result. It also has to be said plainly: **the
proxy authenticates every request the sandbox makes, using the operator's target credential, so the
effect gate is the entire authorization boundary.** Anything that reaches the proxy from inside the
sandbox is the operator, as far as the target is concerned.

That is the intended design and there is no cheaper one — the agent must be able to call the target.
It stacks with **U-44**, the target's own safe-method operations acting as a deputy, which is
unmeasured on every target. Recorded here so that the two are visible together rather than in two
registers.

---

## 2. Technology decisions

Each decision names what was chosen, why, what else was considered, and what it answers to. Where
the basis is an owner decision or a finding, that is cited; where there is no evidence, the decision
says so and appears again in §5.

### T-01 — ADK's agent and session tier, not its graph workflow tier

> **Superseded 2026-08-03 by [`OD-15`](../001-discovery-validation/plan.md) — superseded, not
> wrong.** The owner answered T-01's own **Q-04** with (b). ~~Build the loop on `google-adk`'s
> agent/runner and session-service tier.~~ **v1 depends on no `google-adk` at any tier.** The loop,
> the runner and the session store are ours. T-01's reasoning against the `Workflow` graph tier is
> unaffected and still correct; what it selected instead no longer exists in the design. The `Pins`
> paragraph below has no subject. **The alternative T-01 recorded as "a real option" — no framework
> at all — is what ships**, and its cost is the eight unowned capabilities OD-15 enumerates.

**Decision.** Build the loop on `google-adk`'s agent/runner and session-service tier. Do not use the
`Workflow` graph tier.

**Rationale.** §1.1(a). v1 has one agent and one loop; the graph tier has no subject and using it is
constitution Principle III's named failure mode. The resume machinery it would supply is measured not
to help a hosted loop.

**Alternatives considered.** *ADK's `Workflow` tier* — rejected above. *LangGraph* — rejected: it has
identical super-step semantics, so it does not remove the journaling item
(finding 006, *The largest build item is not ADK's fault*), and it would discard the four-provider
tool-calling result that **OD-01** rests on. *No framework at all* — a real option, since v1 uses a
narrow slice of ADK; rejected because the slice that remains is exactly the slice finding 003
measured working across four providers, and rebuilding it buys nothing. Recorded as **Q-04** because
the slice is now small enough that the question is fair to ask.

**Pins.** `google-adk` pinned to the version the findings measured, with the version and the
`ResumabilityConfig` behaviour re-verified on every upgrade — finding 006's step 3 flags the flag as
`@experimental`.

### T-02 — the opaque provider-state envelope is ours, above the adapter

**Decision.** A `provider_state` value of opaque bytes on every turn record, captured from the raw
provider response and re-injected verbatim, keyed by provider, never merged, never interpreted, never
logged in a form that could be read as content.

**Rationale.** §1.1(b). FR-037 and constitution Principle V require it; finding 003 result 7
measures the adapter not doing it for one provider.

**Alternatives considered.** *Rely on the adapter* — rejected on the measurement. *Patch or fork ADK*
— rejected: OD-01 says wrap rather than fork, and an upstream patch is not a shipping plan.
*Drop the provider* — rejected; SC-010 requires four.

**Test owed.** A per-provider round-trip conformance fixture over a long chained tool sequence on a
reasoning model, asserting byte identity of the opaque field. Cassette-backed, per constitution
Principle VII.

> **Narrowed 2026-08-03 by [`OD-15`](../001-discovery-validation/plan.md) and
> [`OD-16`](../001-discovery-validation/plan.md) — the envelope stays, the tier under it changes.**
> ~~"ADK remains the transport."~~ There is no ADK and no `litellm`; the transport is each vendor's
> own SDK behind a thin driver of ours. **The decision is unchanged and gets easier**: FR-037's
> round-trip is now discharged *in* the driver rather than compensated for above an adapter that
> drops one provider's field, which is constitution Principle V's two-tier rule in its intended
> shape rather than as a mitigation. **The test owed is unchanged and grows one obligation**: with
> the journal also ours, the fixture should extend to a resume boundary, which finding 006's *What
> this does NOT establish* records as untested for opaque state. **And the alternatives above lose
> their subject** — there is no adapter to rely on and nothing to fork.

### T-03 — v1 owns its operator-facing HTTP/SSE surface

**Decision.** A thin HTTP/SSE surface of ours, carrying the caller-visible result record
([`contracts/result-record.md`](./contracts/result-record.md)) and the session event stream.

**Rationale.** §1.1(c). Flagged as **Q-05**.

**Alternatives considered.** *ADK's serving layer* — the only limb of OD-01 with nothing measured
behind it, and finding 006 records an untested interaction between it and the terminal-condition
wrapper this plan must build. *A CLI only* — rejected: it would make SC-001's unattended-operator
measurement and the FR-045 reporting surface awkward, and Principle VII names the HTTP/SSE contract
specifically.

> **Confirmed 2026-08-03 by [`OD-15`](../001-discovery-validation/plan.md), and its flag closed.**
> T-03's decision is unchanged and its first alternative no longer exists. **Q-05 is subsumed rather
> than answered**: it asked "ours or ADK's" and there is no longer a second option. One obligation
> arrives with the confirmation — T-03 assumed our surface would render **ADK's** event stream, and
> nothing now produces that stream. Emitting it is one of the eight capabilities OD-15 records as
> unowned.

### T-04 — Python for the runtime, the supervisor and the analysis layer

**Decision.** Python 3.12 for the analysis stage, the runtime and the session supervisor.

**Rationale.** ADK is Python and both findings measured it on Python 3.12. One language for three of
the four components. The analysis layer reads `codegraph`'s SQLite directly rather than its
TypeScript API, which **D-14** already decided, so nothing forces a second runtime there.

**Alternatives considered.** *TypeScript throughout* — would put the runtime on a provider path
nothing in this corpus has measured. *Rust or Go throughout* — would discard the ADK result entirely.

**Carried caveats from finding 003, both of which bite here.** `litellm` stopped publishing macOS
wheels after the release the probe pinned, so the documented multi-provider path needs a Rust
toolchain on an Apple-silicon laptop. Production is a Linux container, so this is a *developer
environment* problem, and the answer is that development happens in the same container image.
Separately, and more seriously: `litellm`'s published package metadata declares no license at all,
and its repository is MIT except for a proprietary subtree. **That is a distribution question for a
product we ship to customers, and no document in this corpus has treated it as one** — finding 003
records it as an observation. It is **Q-08**.

> **Resolved 2026-08-03 by [`OD-16`](../001-discovery-validation/plan.md); one limb of the rationale
> withdrawn by [`OD-15`](../001-discovery-validation/plan.md).** Both caveats stop biting because
> `litellm` is not shipped: the license question is answered by removal, and OD-17 makes the wheel
> question moot for shipping in any case, exactly as finding 003 classified it. **The rationale
> loses its first limb** — ~~"ADK is Python and both findings measured it on Python 3.12"~~ is no
> longer a reason for anything, since v1 depends on no ADK. **Python still stands** on the two
> reasons that survive: one language across the analysis stage, the runtime and the supervisor, and
> `codegraph` read through its SQLite artifact rather than its TypeScript API (**D-14**). The
> alternative *Rust or Go throughout* no longer "discards the ADK result", because that result is
> already outside the shipped configuration under OD-16; what now argues against it is only that it
> is a rewrite of three components for no named failure.

### T-05 — the enforcement point is a component we own, in Go

**Decision.** Write the egress proxy ourselves, as a single static Go binary: an HTTP server with a
strict request filter in front of an origin-validating TLS client to one pinned upstream.

**Rationale.** Three properties, in order. The **policy** is the product's central safety mechanism,
must be versioned data reviewable before it takes effect (FR-012, FR-019, FR-054), and cannot live in
a third party's configuration language without becoming unreviewable. The **parser** is the one place
where a difference between what the proxy reads as the method and path and what the target reads is
a complete defeat of FR-018 — request smuggling and parser-differential attacks are the named failure
this choice prevents, and Go's HTTP server rejects the ambiguous framing those attacks depend on. And
a **static binary** with no runtime dependency resolution is the cleanest form of FR-021.

**Alternatives considered.** *Envoy plus an external authorization service of ours* — genuinely
strong: a hardened data plane, native TLS origination, and the policy still ours. Rejected for v1
because it puts a large operational dependency into a self-hosted operator's install for a
single-upstream, single-destination policy, and because the security-critical decision ends up in our
code either way. *Squid or any CONNECT-oriented proxy* — rejected: it sees a host and a port, so the
method allowlist silently degrades into a destination allowlist, which is the exact failure OD-12
tested for and rejected. *`mitmproxy`* — rejected: interception, against OD-12. *Python, so the whole
stack is one language* — a fair call and the reason this is **Q-01**; the cost is a weaker
framing-ambiguity posture at the one component where that class of bug is fatal.

**Constitution Principle VIII obligation discharged.** A second language is a new layer, so it is
justified against a named failure: a parser differential at the single enforcement point that makes
every other safety property in v1 true.

### T-06 — storage is SQLite in WAL mode plus a content-addressed object store

**Decision.** One SQLite database per deployment for sessions, traces, the budget ledger, the turn
journal, drift signals and artifact refs; a `objects/<sha256>` file store for artifact payloads.
Every row carries `tenant_id` and `deployment_id`. All access behind one repository interface with no
engine-specific SQL beyond the connection layer.

**Rationale.** FR-035 requires namespaceable storage while exactly one tenant exists, and **OD-08**
makes that a discipline enforced from the first commit rather than a migration. FR-054 requires
content addressing and one-command restoration, which a CAS plus a refs table gives directly.
Self-hosted (OD-08) argues hard for zero additional services. Finding 006's resume results are
specific to SQLite on a local filesystem, so this is also the only substrate any of this has been
observed on.

> **Narrowed 2026-08-03 by [`OD-15`](../001-discovery-validation/plan.md) — one limb withdrawn, the
> decision unchanged.** ~~"Finding 006's resume results are specific to SQLite on a local
> filesystem, so this is also the only substrate any of this has been observed on."~~ What finding
> 006 observed on SQLite was **ADK's `SqliteSessionService`**, which v1 does not ship, so that
> sentence no longer supports the choice. **FR-054's content addressing and OD-08's zero-extra-
> services argument are untouched and were always the load-bearing ones.** The consequence is that
> v1's session store has *no* observed substrate rather than one — which makes the concurrent-writer
> risk below worse, not better, and it is restated on that footing.

**The risk, stated rather than assumed.** Finding 006 says explicitly that it did not test
`SqliteSessionService` under concurrent writers. v1 has three processes with an interest in this data
— the runtime, the supervisor and the proxy. **Mitigation: single-writer-per-table ownership.** The
supervisor owns the session and lease tables; the runtime owns traces, ledger and journal; the proxy
owns its own decision log in its own database and the runtime ingests it into the trace. The proxy
*reads* the session table and never writes it.

**Alternatives considered.** *PostgreSQL* — the right answer for the hosted tier OD-08 preserves, and
the wrong first ask of a self-hosted operator. The repository interface is what keeps it reachable.
*Everything in flat files* — loses transactional budget accounting, which is FR-005's whole point.
Flagged as **Q-02**.

### T-07 — the session journal is ours; no durable-execution engine in v1

**Decision.** A write-ahead intent journal keyed by `(session_id, turn_index, step_index)` with an
idempotency key per effectful step: intent written and committed before the effect, outcome committed
after. Budget is **reserved before** the model call and **reconciled after**, so a crash over-counts
rather than under-counts.

**Rationale.** FR-005, FR-007 and **U-30**, which records that no layer of the stack supplies a spend
ceiling surviving a crash and resume. Reserve-then-reconcile is what makes the failure direction
safe.

**One estimate the owner should know has moved, stated as a reason to re-estimate and not as a new
number.** Finding 006 sized idempotency and inner-loop journaling as the largest build item, and it
sized it for a product that emitted side-effecting nodes. **OD-10** makes v1 read-only against the
target, so repeating a target call cannot corrupt the target — it can only cost budget. The effects
that must not repeat in v1 are the *local* ones: the budget ledger, the trace, and scratch writes.
That is a materially smaller obligation than the one that was sized, and the estimate should be
re-derived rather than inherited. It is not zero, because budget correctness is exactly what U-30
says nothing supplies.

**Alternatives considered.** *Temporal, Restate or DBOS underneath* — the only thing that removes the
item, per finding 006, and rejected for v1 under constitution Principle VIII: it is a new service a
self-hosted operator must run, bought against a build item that just got smaller. Recorded as the
named v2 option in **Q-03**.

### T-08 — parallel tool calls are executed concurrently and recorded in declared order

**Decision.** Where a provider emits several tool calls in one turn, execute them concurrently and
journal and record them in the **provider's declared index order**, never in completion order. Any
shared state a step writes is merged by an explicit per-key rule, never by last-write-wins.

**Rationale.** FR-007's second clause requires work performed in parallel to be ordered
deterministically before it is recorded, and finding 006 measured both halves of why: fan-out
ordering in ADK is completion-time driven, producing **5 distinct orderings in 8 runs** under
overlapping latencies, and two parallel branches writing one shared key produced a **silent lost
update** with no error and no warning.

**Worth stating because nobody appears to have connected them.** Finding 006's fan-out results were
read as a property of *graph* parallelism, and v1 emits no graph — so the natural reading is that
they do not apply. They do. Every provider in SC-010's set can emit multiple tool calls in a single
turn, so a single-agent loop has fan-out whether or not it has a graph.

> **Confirmed and re-based 2026-08-03 by [`OD-15`](../001-discovery-validation/plan.md), and the
> evidence behind it is thinner than it was.** The paragraph above is correct and OD-15 does not
> weaken it: the hazard is a property of providers emitting several tool calls in one turn, not of
> anybody's graph engine, so it survives ADK's removal intact and **T-08 remains its owner**. Two
> things change. T-08 stops being a discipline imposed on somebody else's scheduler and becomes a
> **construction requirement of our own dispatcher**, which is the easier of the two and belongs in
> `tests/invariants/`. And the measurements behind it — **5 distinct orderings in 8 runs** under
> overlapping latencies, and the silent lost update where one of two parallel branches writing a
> shared key vanished with no error and no warning — are measurements of **ADK's** completion-order
> scheduler and **ADK's** reducer-free state model. They are why the hazard is known to be real;
> they are not evidence about a dispatcher nobody has written. **T-08 is now a design rule with no
> measurement behind it.**

### T-09 — absolute-URL handling at the proxy

Stated at §1.3(a). Recorded here so it has a decision identifier: relative presentation, absolute-form
`http` request-targets accepted for the pinned origin, absolute `https` denied with a named reason and
a counter, no body rewriting.

### T-10 — two egress planes

Stated at §1.3(b).

### T-11 — packaging is OCI images plus a compose bundle we author

**Decision.** Four images — analysis, runtime, supervisor, proxy — plus a sandbox base image; one
compose bundle authored by us; every dependency resolved at build time; no package index reachable
from anywhere at run time.

**Rationale.** FR-021, and OD-12 item 4's observation that under self-hosting we ship the
specification and the customer instantiates it, and a compose file is ours to author. FR-021 needs no
separate mechanism: dependency resolution at run time is an outbound request to a destination that is
not the target, so the egress policy already denies it. Two requirements, one control.

**Supported platform.** Linux with cgroup v2 and user namespaces. The three mechanisms in §3 are
Linux kernel facilities; there is no macOS or Windows implementation of them and none is planned.
Under FR-053 that makes Linux the only supported platform and everything else **unsupported rather
than best-effort** — operators on other systems run the bundle in a Linux VM, which is what Docker
Desktop already is.

**`codegraph`.** A Node CLI, invoked as a subprocess by the analysis image at analysis time only. It
is never present in the runtime or the sandbox. **U-04** — schema stability across releases — is
adopted as written: pin the version, assert a schema hash in CI, and fail the analysis stage loudly
on a mismatch rather than reading a changed schema as changed source.

### T-12 — canonical serialization for every versioned artifact

**Decision.** One canonical serializer for every artifact FR-054 enumerates: sorted keys, fixed
numeric formatting, `LF` newlines, `UTF-8` without a byte-order mark, and **no timestamp, path or
hostname inside the hashed payload** — those live in an envelope beside the hash, not under it. A
determinism test analyses a fixture twice and asserts byte identity.

**Rationale, and this is a correction to a deviation record rather than a preference.** The
specification's Principle VII disposition says the byte-stability half of the determinism clause
"has no subject either" because v1 emits no artifacts. **v1 produces artifacts** — FR-054 lists
eight kinds and requires them content-addressed. Content addressing over a non-canonical
serialization produces a different hash on every run of the same analysis over the same input, and a
changed hash on the source-derived artifact is precisely what FR-028 reads as source drift. So a
non-canonical serializer is a **false-alarm generator aimed at the one v1 capability with no measured
false-alarm rate.**

This is carried into the plan's Constitution Check as a partial rejection of that record, and flagged
for the owner as a narrowing the specification text should carry.

### T-13 — contract derivation contains no model call

**Decision.** v1's derivation of contracts and checks from source is static. No model participates in
producing a verification signal or a derived contract.

**Rationale.** Constitution Principle I, FR-023, and the fact that
[finding 007](../001-discovery-validation/findings/007-contract-extraction.md) measured static
derivation at zero model spend, so this costs nothing that was ever measured to be worth having. A
model-assisted derivation would be a derived artifact whose provenance is a model, which FR-026 would
require to be marked provisional, and which nothing would validate.

### T-14 — the independent artifact that validates a derived check is the target's published specification

**Decision.** A derived contract is marked **validated** when it agrees with the target's own
published specification for the same operation, and **provisional** with its provenance and
confidence otherwise, per FR-026 and constitution Principle I as amended at v1.1.0.

**Rationale, and it is a piece of luck worth naming.** Principle I's v1.1.0 clause requires a derived
verifier to be validated against an artifact its own derivation did not produce. FR-002 already makes
the target's published specification an **admission criterion**, so v1 has that independent artifact
in hand for every admitted target, by construction, before any session starts. The two-clock
structure **OD-06** forced for a different reason turns out to supply Principle I's independence
requirement for free.

**The honest expectation.** Finding 007 measured this exact comparison on one target and one
framework: the literal reading of its gate is **0.8696** and the validated reading — the extractor
produced both components *and* both agree with the published schema — is **0.7681**. Read across, a
comparable target would leave roughly a quarter of derived contracts provisional. That is one
framework whose design premise is that the signature is the schema, and it must not be generalized;
it is recorded so the provisional share is expected rather than alarming.

---

## 3. The three mechanisms the specification left to the plan

FR-048, FR-049 and FR-050 are stated as observable properties with no mechanism named. That was
correct discipline and it means the plan owes a mechanism for each. All three are Linux kernel
facilities, which is why T-11 makes Linux the supported platform.

### 3.1 FR-048 — the declared filesystem scope

**Mechanism: a per-session mount namespace whose contents are exactly the declared set.**

The execution environment is an OCI container created per session with an **empty root** into which
only declared locations are mounted:

| Mount | Mode | Why it is declared |
|---|---|---|
| toolchain layer | read-only, `nosuid`, `nodev` | the shell and the general request capability of FR-004, dependencies pre-resolved (FR-021) |
| session scratch | read-write, `noexec`, `nosuid`, `nodev` | working space; a fresh volume keyed by session id |
| served-operation set | read-only | the agent needs to know what it may call |
| a single static hosts entry | read-only | legibility of the proxy address; not a resolver |

Nothing else exists **in the namespace**, which is the difference that matters: a location outside
the declared set is not permission-denied, it is *absent*. That is what makes FR-048's "stated
positively — a location is reachable because it was declared, never because nothing excluded it" a
structural property rather than a policy. The runtime's configuration, the operator's wider host,
the effect-gate rule set of FR-012 and the egress policy of FR-014 are all outside the namespace and
outside the container's network reach, which is what turns FR-012's "no write path" and FR-014's
"cannot reach, modify, reconfigure or bypass" into one checkable boundary rather than two assertions.

**The recording clause is what forces a second component, and it is a real cost.** FR-048 requires an
attempted access outside the set to be "recorded in the trace with the rule that produced it,
identically to a denial under FR-011", and SC-022 requires **100%** of refusals recorded. A mount
namespace enforces perfectly and **records nothing** — the attempt fails with `ENOENT` inside the
container and no component outside it ever learns. Namespace-only therefore satisfies FR-048's
enforcement clause and fails its recording clause and SC-022.

**Mechanism for the recording clause: a `seccomp` user-notification supervisor**, outside the
container, holding the notification file descriptor for the path-taking syscalls. It sees each
attempt before the kernel performs it, which also gives FR-048's "fail rather than partially
succeed" in the strong form — denied before execution rather than interrupted during it — and emits
the FR-011-shaped record.

**Costs, stated because a supervisor on `openat` is not free.** Every path-taking syscall becomes a
userspace round trip, and a shell-heavy workload makes many. The overhead is unmeasured and this plan
does not guess at it; the implementation owes a measurement on the reference application before the
mechanism is committed, and **Q-09** records the fallback if it proves prohibitive — an audit-based
channel that records after the fact rather than before, which keeps SC-022 and loses the
"before execution" property.

**Alternatives considered.** *Filesystem permissions and a dedicated user* — fails "stated
positively" outright and leaves `/proc`, `/etc` and other sessions readable. *`chroot`* — a weaker
form of the same idea with well-known escapes for a process that can obtain a directory file
descriptor. *A microVM (Firecracker) or gVisor* — stronger isolation, and both are reasonable v2
answers; rejected for v1 as unearned complexity against a boundary a mount namespace already
supplies, and because gVisor's syscall interposition would in fact make the recording clause cheaper,
which is worth revisiting if **Q-09** goes the wrong way.

### 3.2 FR-049 — the processor and memory bounds

**Mechanism: cgroup v2, with the session's cgroup created and owned by the supervisor.**

| Bound | Control | Terminal state |
|---|---|---|
| memory | `memory.max` on the session cgroup, with `memory.oom.group` set so the session dies as a unit rather than losing a random child | `terminated.memory_bound_exhausted` |
| processor, as a rate | `cpu.max` — a quota over a period, not a weight | — (this bound protects the host; it does not end the session) |
| processor, as a total | cumulative `cpu.stat` usage watched by the supervisor against a declared ceiling | `terminated.cpu_bound_exhausted` |
| process count | `pids.max` | `terminated.process_bound_exhausted` |

**Enforced from outside** in the sense FR-049 requires: the cgroup is created by the supervisor
before the container starts, the container has no writable `cgroup` mount and no delegation, so
nothing running inside can raise, extend or evade a bound.

**Why "processor time" is implemented as two bounds and not one.** FR-049 asks for one, and SC-023
asks for two different things from it: *zero sessions exceed the declared processor bound*, and *a
co-located reference workload on the same host keeps serving throughout*. A cumulative CPU-seconds
ceiling satisfies the first and does nothing for the second, because a session can saturate every
core for a short time and still be under its total. A rate quota satisfies the second and never ends
a session. Both are needed and the plan says so rather than picking one and hoping. This is an
interpretation of FR-049, not a narrowing of it — both bounds are declared, both recorded with the
deployment identity, both enforced from outside.

`pids.max` is beyond what FR-049 requires and is included because a fork bomb is the cheapest way to
defeat SC-023's co-located-workload clause. It is an addition, marked as one.

**Exhaustion accounting.** FR-049 requires work already performed to still count against FR-005's
ceilings. T-07's reserve-then-reconcile ledger is journalled outside the container as consumption
accrues, so a cgroup kill loses no accounting: the ledger is already durable at the moment of the
kill.

**No default values, and the plan does not need any.** FR-049 states no default for either bound
because nothing in feature 001's evidence base bears on an agent's working set. This plan's
recommendation is stronger than shipping a marked default: **both bounds are required configuration
and startup fails loudly when either is unset**, under FR-033. That removes the inherited-number
failure mode entirely rather than mitigating it. The compose bundle we author for the *reference
application* carries values so the fixture batteries can run; those are fixture configuration, they
are marked unvalidated under FR-043 wherever they appear, and they are not product defaults.
Recorded as **Q-10** because it is a usability decision the owner may want to take the other way,
and if it is taken the other way the shipped number is a configured value with nothing behind it and
carries FR-043's marking everywhere.

**Alternatives considered.** *`ulimit` / `setrlimit`* — per-process rather than per-session, so a
child escapes the accounting; and it is set from inside, which FR-049 forbids. *A VM with a fixed
allocation* — satisfies the bound and defeats "must not deny service to anything else on the host"
by reserving the memory whether or not it is used.

### 3.3 FR-050 — no credential outliving the session, including by crash

FR-050 decomposes a lifetime into three observable properties. Each gets a mechanism, and the second
one is the hard one.

#### Not present

**Mechanism: the execution environment never holds a long-lived credential, because the proxy
authenticates on its behalf.**

The target credential is injected by the proxy on re-origination (§1.3(c)). The model credential
never leaves the runtime, which is a different container in a different network plane (T-10). No
secret value is passed into the container's environment, written into any mount in FR-048's declared
set, or present in its process state — and FR-033's environment injection delivers configuration to
the *runtime*, which is not the environment a shell runs in. That distinction is FR-050's first
bullet and the design satisfies it by construction rather than by scrubbing.

This is also what makes bring-your-own-credentials compatible with FR-050 rather than in tension
with it: the operator's own long-lived secrets keep their normal lifetimes, outside the environment
entirely.

#### Bounded — and this is where a session-scoped authority survives its own session

What the environment *does* hold is a **session capability**: the ability to reach the proxy and be
authenticated as the operator. FR-050 requires that authority to stop being honoured the moment the
session reaches a terminal state **including a terminal state reached by crash**.

The failure mode is specific and it is the one the specification's own checklist points at. A
self-describing credential with an expiry — a signed token — is honoured by anyone who can verify the
signature, for as long as its expiry says, **whether or not anything is still alive to revoke it**.
A revocation step in a shutdown path is worse: finding 006 killed its probes with `SIGKILL` in a
separate process precisely so that no `finally` block, no `atexit` hook and no graceful shutdown
could run, and that is the crash this requirement has to survive.

**So the design makes revocation the default and continuation the thing that requires work.** Four
layers, and each closes a different failure:

1. **The capability is an opaque handle, not a claim.** There is nothing offline-verifiable. The
   proxy resolves the handle on **every request** against the session table. A handle whose session
   row is not `RUNNING` is denied and the denial is recorded under FR-011. There is no state of the
   world in which something honours the handle because it looked at the handle.

2. **`RUNNING` is a lease, so ceasing to act revokes.** The supervisor renews the session's lease on
   a short interval while the session is live. The proxy honours `RUNNING` only while
   `lease_expires_at` is in the future. On a crash of the runtime, the supervisor, or both, **nothing
   renews and the authority lapses without any code having run.** This is the term that answers the
   crash case, and its cost is honest: **between the crash and the lapse there is a residual window
   of one lease interval during which the handle is still honoured.** The interval is a configured
   value with nothing behind it and carries FR-043's marking.

3. **The path is bound to a live process, so the common crash closes instantly.** The sandbox reaches
   the proxy over a per-session listener whose socket is held open by the supervisor's own file
   descriptor, inside the session's network namespace. When the supervisor process dies the
   descriptor closes with it and the listener is gone — **the kernel performs the revocation and no
   cleanup code is involved.** When the session's namespace is destroyed the path is gone with it. So
   layer 2's residual window applies only to the narrower case where the supervisor is alive and the
   session row was not updated, rather than to every crash.

4. **A resumed session is the same session (FR-007), so resume renews the lease rather than issuing a
   new capability**, and the handle's identity does not change across a crash and resume.

**Where SC-024's recording clause is satisfiable and where it is not, stated rather than assumed.**
SC-024 requires zero replays honoured and **100%** of the refusals recorded. A replay that can reach
the proxy — from inside a later session's execution environment, which is the fixture arm that
matters — resolves to a terminated session, is denied, and is recorded exactly like any other FR-011
denial. A replay from a position with **no path to the proxy at all** is refused by unreachability,
and the only thing that can record it is the enforcement point's own drop counter, because nothing
receives the connection. The plan states both arms and builds the fixture to exercise both, rather
than claiming a uniform recording property the topology does not have.

#### Not inherited

**Mechanism: a fresh container and a fresh scratch volume per session, both keyed by session id, and
mounts declared per session.**

Nothing from a previous session is ever mounted, so inheritance is prevented by the same positive
declaration that satisfies FR-048 — not by a reaper running. A resumed session reattaches *its own*
scratch, because FR-007 makes it the same session. A session that crashes and is never resumed leaves
a scratch volume that no later session can mount, because a later session's mount set names a
different session id; reclaiming the disk is a housekeeping concern and not a safety one, which is
the right way round.

---

## 4. Building the three measurement obligations

The specification converts three unmeasured capabilities into measurement obligations gating the
corresponding claims. The plan owes the **instrumentation**, not just the capability. Each of the
three needs something that does not exist yet, and one of them needs something the corpus has already
recorded as never having been produced.

### 4.1 The verifier's margin over a shadow judge — FR-039, FR-040, FR-052; SC-013, SC-025

**Built now.**

- A **shadow judge** consuming the trace stream asynchronously, never in the request path, writing
  `judge_verdict` rows keyed to a result. It is injectable, so SC-025's differential battery can run
  the same sessions with the judge agreeing, disagreeing, and not running at all.
- A **structural boundary** rather than a policy one. The caller-visible result record is constructed
  by the verification stage from the reported value, the recomputed value and the derivation; the
  construction path has no read access to the judge's table, and an **import-graph test** asserts that
  the result-record and gate-decision modules do not depend on the judge module. That is FR-052
  enforced by construction and testable as one, which is what FR-052 asks for.
- A **measurement harness that pins its inputs as well as its records**. This is not optional and it
  is not generic hygiene: **U-47** is the register entry that a hash-pinned trace corpus rebased onto
  edited prompts while every hash check kept passing, and FR-053 restates the fix as a requirement.
  Its four terms are adopted verbatim — the prompt lives *inside* the trace record so the artifact is
  self-contained; the battery version and task-file hashes are pinned in the freeze; the cross-battery
  census is pinned as an invariant the harness re-checks on load; and the analysis path **refuses** a
  cross-battery join rather than performing one.

**What FR-040's gate needs that nothing supplies, and it must be said rather than discovered.** The
gate has three branches and the third fires on the **judge's own discrimination** — a judge no better
than chance triggers a constitutional prohibition, independently of what the verifier scores.
Computing discrimination needs ground truth about whether each result was actually right. The
verifier's verdict cannot be that ground truth, because the verifier is the thing being compared.
Constitution Principle I requires calibration against **human** labels, and the specification's Open
Risks section records that the human adjudication pass over the frozen oracle negatives **was never
performed**, that a model performed it instead, and that this is now the missing precondition on
FR-052.

So the instrumentation must include **an adjudication queue**: a sampling rule pre-registered before
the window opens, an operator-facing surface that presents a sampled result with the evidence needed
to judge it, and `human_label` rows carrying the adjudicator and the time. Without it FR-040's third
branch is not computable and SC-013's thirty-day window is not reachable. See §7.1 — this is reported
as a dependency the specification does not state, not softened.

### 4.2 The effect gate's read-only precision — FR-041; SC-014

**Built now.** The proxy records, for every request it sees: the resolved tier, the rule identifier
that produced the resolution, the matched operation template, the method, the specification metadata
that operation carried, and the disposition. That record is the corpus. A corpus exporter produces
the labelled set FR-041 scores against.

**Where the labels come from, and this one has a cheap and legitimate source.** The measurement is
*read-only precision*: of the calls resolved read-only, what share were in fact side-effect-free. On
the reference application that is answerable by **observable state**, which is exactly what
constitution Principle I calls an admissible verification artifact — snapshot the application's
state, issue the call, diff. No model judges anything. On a real target the operator supplies the
label, and the same record is what they label.

**The threshold is not set here, deliberately.** FR-041 requires a threshold pre-registered **for a
per-call gate** and forbids inheriting the superseded per-tool one. **OD-10** already records why the
old number does not travel: it was chosen for a static label over a curated catalogue, and a per-call
gate over a general shell has a different base rate and a different blast radius. Pre-registration is
an owner act that happens before the measurement runs; this plan builds the harness and records the
threshold as **unset**. Inventing one here would be the inherited-number failure arriving by a new
door.

### 4.3 Drift detection on both clocks — FR-042; SC-008, SC-009, SC-015, SC-020

**Built now.** Two independently versioned artifacts (FR-027), the scheduler and its configurable
triggers (FR-046), and the drift-signal record carrying the clock, both artifact versions and the
deployment identity (FR-031). Plus **two committed synthetic corpora**, because FR-053 requires the
fixture to be committed alongside the capability rather than assembled when the measurement falls
due: one that mutates source while the deployment stands still, one that changes what the deployment
serves while source stands still.

**Detection latency is measurable on the synthetic corpora because the corpus controls the change
time.** On real traffic the two clocks differ: a source change has a commit timestamp, so source-clock
latency is measurable; a deployment change generally has **no observable change time at all** unless
the customer emits a deployment event, which FR-046 explicitly says may not be assumed available. So
deployment-clock latency in production is measurable only where that optional trigger exists. That
is a property of the world rather than a gap in the design, and FR-042's pre-registered design must
say which population it is measured on.

**T-12 is a precondition of all of this.** Without canonical serialization the source-derived
artifact's hash changes on every run and drift detection reports a false alarm every interval.

> **Added 2026-08-03 — a third fixture is owed here, and the two corpora above must not be read as
> covering it.** Both corpora are about drift being *detected*; **FR-047** is about the observation
> channel *failing*, which is a different condition and needs the fixture **SC-021** describes —
> withdraw an admitted target's published specification, then restore it. **That fixture measures
> conformance to FR-047 and measures nothing about whether FR-047's disposition is correct**, because
> feature 001 never ran the scenario: E13's three mutations all move the source and E13 never ran.
> **FR-047 therefore ships unmeasured**, recorded as such in [`plan.md`](./plan.md)'s Complexity
> Tracking table and at `research/14-architecture-synthesis.md` **O-04**, which stays open.

---

## 5. Flagged for the owner

Each of these is a genuine architectural choice with no evidence behind it and a high cost to
reverse. Each carries a recommendation. None has been decided silently.

> ## ✅ ANSWERED 2026-08-03 — all eleven, and three of them not as recommended
>
> **The owner reviewed this section and closed every row.** A **Disposition** column has been added
> rather than the table rewritten, so the recommendation each answer was taken against stays legible
> beside it.
>
> - **Eight accepted as recommended**: Q-01, Q-02, Q-03, Q-05, Q-06, Q-07, Q-09, Q-10.
> - **Three answered against the recommendation, and each became an owner decision** in
>   [feature 001's plan](../001-discovery-validation/plan.md): **Q-04 → OD-15** (drop ADK for v1),
>   **Q-08 → OD-16** (`litellm` is not shipped), **Q-11 → OD-17** (Linux only — this one *was* the
>   recommendation; it is an OD because it is a customer-facing product limit, not because it
>   differed).
> - **Q-05 is subsumed rather than chosen.** It asked whether the operator-facing surface is ours or
>   ADK's. Under OD-15 there is no ADK surface to choose between, so the question has no second
>   option left and the framing above is stale. It is marked accepted because the outcome T-03
>   describes is what ships, not because the choice was live.
> - **Q-09's acceptance carries its measurement obligation intact**: the syscall supervisor's
>   overhead is **measured on the reference application before the mechanism is committed**, not
>   assumed. Accepting (a) accepts the measurement, not a prediction of its result.
>
> **Two accepted rows have rationales that OD-15 changed, and neither changes its verdict.** Both are
> annotated in their Disposition cell rather than left to be discovered: **Q-02** loses the "only
> substrate finding 006 observed" limb, because what finding 006 observed was ADK's session service;
> and **Q-03**'s build item got *larger* rather than smaller, which strengthens the case for the
> option it declines while leaving the Principle VIII reason it declines it untouched. The other six
> are unaffected by OD-15 — Q-01, Q-07 and Q-09 concern the enforcement point and the kernel, Q-06's
> subject is a path v1 does not build either way, and Q-10 is a configuration policy.

| # | Question | Options | Recommendation | Disposition |
|---|---|---|---|---|
| **Q-01** | **What language is the enforcement point written in?** It is the component every other safety property depends on | (a) Go, a static binary with a framing-strict HTTP server; (b) Python, so the stack is one language; (c) Envoy plus an external authorization service of ours | **(a) Go.** The named failure is a parser differential at the one point where a disagreement about the method and path is a complete defeat of FR-018. Cost: a second language and toolchain | **ACCEPTED 2026-08-03 as recommended.** Unaffected by OD-15: the enforcement point is a separate process that never involved ADK |
| **Q-02** | **Storage substrate for analysis artifacts, sessions, traces and the versioned-artifact store** | (a) SQLite in WAL plus a content-addressed file store; (b) PostgreSQL; (c) files only | **(a).** Zero extra services for a self-hosted operator (**OD-08**), and the only substrate finding 006 observed. Kept behind one repository interface so (b) stays reachable for the hosted tier. The risk is multi-process writers, mitigated by single-writer-per-table ownership | **ACCEPTED 2026-08-03 as recommended, with one limb of the rationale withdrawn.** ~~"the only substrate finding 006 observed"~~ — what finding 006 observed on SQLite was **ADK's** `SqliteSessionService`, which OD-15 removes, so that limb no longer supports the choice. **OD-08**'s zero-extra-services argument is untouched and was always the stronger one. The multi-process-writer risk is unchanged and is now unmeasured for our own store as well as for the one we are not shipping |
| **Q-03** | **Does a durable-execution engine underneath the loop belong in v1?** | (a) our own journal; (b) Temporal / Restate / DBOS | **(a).** Finding 006 says (b) is the only thing that removes the journaling item — and **OD-10**'s read-only constraint has already made that item smaller. (b) is a new service in a self-hosted install, unearned under Principle VIII. Named as the v2 option rather than dismissed | **ACCEPTED 2026-08-03 as recommended, and the argument behind it got weaker rather than stronger.** OD-15 makes the surrounding build *larger* — a runner and a session store join the journal — which pushes at the margin toward (b), not away from it. The reason (b) is declined is the Principle VIII one, a new service in a self-hosted install, and OD-15 does not touch it. Recorded so the verdict is not read as having got easier |
| **Q-04** | **Is ADK still worth its dependency now that v1 uses a narrow slice of it?** | (a) keep ADK for agent execution, sessions and the provider adapter; (b) drop it and own the loop directly on provider SDKs | **(a), for v1.** The slice that remains is precisely the slice finding 003 measured across four providers, which is SC-010's whole basis. Worth re-asking once T-02's opaque-state envelope exists, because that is the piece the adapter was carrying | **ANSWERED 2026-08-03 with (b), against this recommendation — [`OD-15`](../001-discovery-validation/plan.md).** The owner did not accept that one surviving limb of OD-01 justifies the dependency. Read OD-15 for what loses an owner as a result: eight capabilities, of which the session store, the runner and the per-provider cost table were in nobody's estimate |
| **Q-05** | **Operator-facing surface: ours or ADK's?** **OD-01** named ADK's HTTP/SSE serving explicitly | (a) ours, thin; (b) ADK's | **(a).** It is the one limb of OD-01 with nothing measured behind it, finding 006 records an untested interaction with the terminal wrapper, and the surface must carry v1-specific fields nothing in ADK models. This is the one place the plan takes less of ADK than OD-01 permits, so it is flagged rather than assumed | **ACCEPTED 2026-08-03, and SUBSUMED by [`OD-15`](../001-discovery-validation/plan.md) rather than chosen.** Option (b) does not exist any more: with ADK dropped there is no ADK serving layer to take. The framing above — *"this is the one place the plan takes less of ADK than OD-01 permits"* — is stale, because v1 now takes none of it. T-03's outcome is what ships |
| **Q-06** | **Does v1 build OD-02's opt-in Claude Agent SDK path?** | (a) no; (b) yes | **(a) no.** OD-02 scoped it to coding nodes and v1 has none, so it would buy no v1 capability while spending the context tax finding 003 measured. OD-02 permits the path; it does not require it | **ACCEPTED 2026-08-03 as recommended.** Unaffected in verdict by OD-15; §1.2's clause that the executor is ours *on ADK* is what OD-15 strikes, and the executor is simply ours |
| **Q-07** | **Absolute `https` URLs out of target responses fail closed. Accept, or revisit the posture?** | (a) accept, count the denials, treat the count as evidence; (b) rewrite response bodies; (c) terminate TLS in the sandbox | **(a).** (b) transforms untrusted bytes on the enforcement path; (c) is what **OD-12** rejected for four stated reasons. The counter is the instrument, and OD-12 already records that re-origination does not generalize | **ACCEPTED 2026-08-03 as recommended.** Unaffected by OD-15. The denial counter is the instrument and it is owed |
| **Q-08** | **`litellm` declares no license in its published package metadata and its repository is MIT except for a proprietary subtree** (finding 003 result 8). v1 ships to customers | (a) keep the provider driver ours and thin so the dependency is replaceable; (b) replace it now with direct provider SDKs; (c) obtain clarity from upstream | **(a) now, with (b) costed.** Nothing in this corpus has treated this as a *shipping* question and it is one. Constitution Principle V's thin bottom tier is what makes (b) a swap rather than a rewrite | **ANSWERED 2026-08-03 with (b) now, against this recommendation — [`OD-16`](../001-discovery-validation/plan.md).** OD-15 is what made (b) cheap: `litellm` was in the tree as a transitive dependency of ADK's documented multi-provider path. The cost OD-16 records is that finding 003's four-provider result was measured *through* that path, so **SC-010 becomes a test v1 must pass rather than a result it inherits** |
| **Q-09** | **FR-048's recording clause needs a syscall supervisor, whose overhead is unmeasured** | (a) `seccomp` user-notification, denying before execution; (b) an audit channel recording after the fact; (c) gVisor, where interposition is already the execution model | **(a), with the overhead measured on the reference application before it is committed.** (b) is the fallback and it loses the before-execution property. If (a) is prohibitive, (c) becomes attractive for a reason unrelated to isolation | **ACCEPTED 2026-08-03 as recommended, measurement obligation included and not waived.** The overhead is measured on the reference application **before** the mechanism is committed. Accepting (a) accepts the measurement, not a prediction of its result; if the measurement says prohibitive, the fallback is (b) with the before-execution property lost, or (c). Unaffected by OD-15 |
| **Q-10** | **FR-049's bounds have no default. Fail closed when unset, or ship a marked default?** | (a) required configuration, startup fails loudly; (b) ship a default marked unvalidated under FR-043 | **(a).** It removes the inherited-number failure rather than mitigating it. If the owner prefers (b) for install ergonomics, the number is a configured value with nothing behind it and carries FR-043's marking on every external surface | **ACCEPTED 2026-08-03 as recommended.** Required configuration; startup fails loudly when either bound is unset. Unaffected by OD-15 |
| **Q-11** | **Supported platform is Linux only** (cgroup v2, mount namespaces, `seccomp`) | (a) Linux only, everything else explicitly unsupported under FR-053; (b) a degraded mode elsewhere | **(a).** A degraded mode is a sandbox missing one of Principle IV bullet 1's terms, and the bullet's own words are that a configuration missing any term does not satisfy it | **ACCEPTED 2026-08-03 as recommended, and promoted to [`OD-17`](../001-discovery-validation/plan.md)** so that it is recorded as a customer-facing supported-platform limit rather than as a line in a technical-context table |

---

## 6. What this plan does not re-admit

**OD-09** deferred five things to v2 rather than cancelling them. A plan is where deferred scope
creeps back in, so each is checked against every decision above.

| Deferred by OD-09 | Checked |
|---|---|
| Tool synthesis from the target's operations | Not present. FR-004's capabilities are general — command execution and a general request capability — and the served-operation set is **data the proxy resolves against**, never a generated tool surface |
| Promotion selection | Not present. Nothing selects functions; nothing is promoted |
| Static per-tool effect classification | Not present. Resolution is **per call, at the proxy**, against the served-operation set and the deny list (FR-008 through FR-012). The obligation does not defer; the differentiator does |
| Knowledge-graph memory layer | Not present. The `codegraph` index is an analysis input, read at analysis time to derive contracts and to detect source drift. It is not a memory tier, nothing writes to it at run time, and no agent reads it |
| The embeddable iframe, and multi-agent artifact trading | Not present. One agent, one operator-facing surface, no untrusted end-user input path |

One near miss worth recording rather than passing over. T-14 uses the target's published
specification to validate derived contracts, which is a *comparison* between two artifacts the system
already holds for other reasons. It selects nothing, promotes nothing and generates no tool, so it is
not synthesis by another name — but it is the closest anything in this plan comes, and it is where
scope would creep first.

---

## 7. What this plan found impractical, and reports rather than softens

### 7.1 SC-013's thirty-day window has an unstated dependency on labels nobody has produced

Covered at §4.1. FR-040's third branch reads the judge's own discrimination, which needs ground
truth; Principle I requires human labels; the corpus records that the one human adjudication pass it
needed was never performed and that a model stood in for it. **SC-013 is reachable only after an
adjudication capability exists**, and the plan builds one. The criterion is not softened and no
alternative ground truth is substituted — substituting the verifier's own verdict would make the
comparison circular, and substituting a model would be the thing FR-052 exists to prevent.

### 7.2 SC-001's fifteen minutes silently includes an analysis stage of unbounded duration

SC-001 measures an operator reaching a first verified answer within fifteen minutes of starting
configuration, unattended, on a reference application. Reaching a *verified* answer requires derived
contracts, which requires the codebase indexed and analysed first. **U-21** records that
`codegraph`'s scale claim is untested and that the one measured datapoint is a small repository,
extrapolating nothing.

So SC-001 is a compound of a bounded step and an unbounded one, and on a large codebase it is not
achievable for reasons that have nothing to do with the runtime. **Nobody has flagged this.** The
plan's response is to instrument and report analysis wall time separately, and to state the reference
application's size wherever SC-001 is reported, so the criterion is assessable rather than quietly
true on small inputs and quietly false on large ones. The criterion itself is left exactly as
written.

### 7.3 SC-001 is already recorded as not independently assessable, and that stands

The specification's Open Risks section says SC-001 depends on the share of results returned not
verifiable, which FR-045 makes a measurement with no threshold. Nothing in this plan changes that.
Taken with §7.2, SC-001 has two independent dependencies on quantities nobody has.

### 7.4 SC-024's recording clause is not uniformly satisfiable, and the plan says which arm is which

Covered at §3.3. A replay that can reach the enforcement point is denied and recorded. A replay with
no path to it is refused by unreachability and recorded only as a drop counter, because nothing
receives the connection. The fixture is built to exercise both arms and to report them separately
rather than pooling them into a single **100%**.

### 7.5 FR-048's recording clause forces a mechanism the enforcement clause does not need

Covered at §3.1 and **Q-09**. This is a cost report rather than an objection: the clause is right,
and a boundary whose denials are invisible is exactly the sort of thing this corpus catches later.

---

## 8. Things nobody had flagged

Collected in one place because they are distributed across documents that do not cite each other.

1. **ADK's provider adapter drops one of the four providers' opaque reasoning state, and FR-037
   forbids dropping it.** Finding 003 result 7 measured the zero; FR-037 and SC-010 were written
   later and independently. No document connects them. §1.1(b), T-02. **This item is what OD-15's
   provider limb rests on**; connecting the two is what turned an inherited adopt into a reversal.
2. **Byte-stability of serialized artifacts has a subject in v1, and the specification's Principle
   VII deviation record says it has none.** Without a canonical serializer, content addressing makes
   every re-analysis look like source drift — a false-alarm generator pointed at the one capability
   with no measured false-alarm rate. §T-12.
3. **The drift scheduler is a second, continuous path to the target**, outside the proxy unless the
   design puts it inside. FR-014's single-enforcement-point guarantee is scoped to the execution
   environment and does not cover it. §1.3(b), T-10.
4. **Finding 006's fan-out results apply to v1 even though v1 emits no graph**, because every
   provider in SC-010's set can emit parallel tool calls in one turn. The silent lost update it
   measured is a single-agent hazard, not a graph hazard. §T-08. **Still true after OD-15, with the
   evidence re-based**: the hazard is the providers', the measurements were ADK's, and T-08 keeps
   the hazard while losing the measurement.
5. **SC-001's window contains an unbounded analysis step.** §7.2.
6. **`litellm`'s license is unresolvable by an automated scan of the installed wheel, in a product we
   ship.** Recorded in finding 003 as an observation about licensing hygiene, never as a distribution
   blocker. **Q-08**. **Closed 2026-08-03 by OD-16**: it is not shipped.
7. **The proxy holding the target credential makes the effect gate the entire authorization
   boundary**, and it stacks with **U-44**'s target-as-deputy channel. Both are known; the
   composition is not written down anywhere. §1.3(c).
8. **FR-021 and the egress policy are the same control.** Run-time dependency resolution is an
   outbound request to a destination that is not the target, so the proxy already denies it. Worth
   knowing so that nobody builds a second mechanism for it. §T-11.

---

## 9. Unknowns remaining after Phase 0

No `NEEDS CLARIFICATION` marker survives into the plan. What remains is of two kinds and both are
declared rather than hidden:

- ~~**Eleven decisions flagged for the owner** (§5). Each has a recommendation and each is reversible
  at the cost stated. The plan proceeds on the recommendation; an owner answer that differs changes
  the artifact rather than invalidating it.~~ ✅ **CLOSED 2026-08-03 — all eleven answered.** Eight
  accepted as recommended; three answered against the recommendation and promoted to owner decisions
  — **OD-15**, **OD-16**, **OD-17**. Exactly as this bullet predicted, the differing answers changed
  the artifact rather than invalidating it: §1.1, T-01, T-02, T-03, T-04, T-06 and T-08 carry dated
  narrowings and one supersession, and no measurement anywhere was rewritten. **What OD-15 adds that
  this list did not anticipate is a build of unknown size** — eight capabilities with no owner, and
  no committed artifact from which to re-derive an estimate.
- **Four quantities with no measurement and no scheduled measurement**: FR-049's two bounds,
  FR-047's staleness ceiling, FR-046's detection window, and the lease interval introduced by §3.3.
  Every one of them is bound to FR-043 and none may travel externally as a validated number. The
  lease interval is the only one this plan adds, and it is added because the alternative is a
  self-describing credential that a crash cannot revoke.
