# `function2agent` — Research Corpus

**Research conducted: 2026-08-02.** Fourteen documents, ~10,400 lines.

This directory holds the pre-spec research for **`function2agent`**. ~~It is a system that statically
analyzes an arbitrary codebase in an arbitrary language, infers where meaningful agent boundaries
lie, and emits a multi-agent stack over that codebase — agents equipped with both Claude-Code-class
coding tools and tools synthesized from the target application's own domain operations, served over
HTTP/SSE.~~ The research exists to make the vision precise, name what is genuinely hard, and settle
enough of the design space that a Spec Kit spec can be written against evidence rather than
intuition. Nothing here is a spec, and only `14-architecture-synthesis.md` is a decision record.

> ### ⚠️ **Read this before reading anything else: the product described above is v2.**
>
> **`specs/001-discovery-validation/plan.md` OD-09 (2026-08-02) re-scoped v1 to roughly a tenth of
> it.** A criterion pre-registered in [`11-validation-plan.md`](./11-validation-plan.md) §7 — written
> before any experiment ran — fired: an agent holding a shell, a socket and the target's own published
> schema matched or beat ~20 hand-written ideal tools in all three measured families.
>
> **v1 points an agent at a running application's own specification, verifies what it did against
> contracts derived from the code, and fails closed when either one moves.** Static analysis shrinks
> from *decompose and synthesize* to *derive contracts where no schema is published, and detect source
> drift*. **Boundary inference, tool synthesis, promotion selection, generation-time effect
> classification, and multi-agent decomposition are all v2** — deferred, and mostly **never measured**,
> since the experiments that would have tested them never ran.
>
> **The corpus is not withdrawn and most of it is still right.** Every affected document carries its
> own scope banner, and the three fates are kept apart deliberately: **wrong** (an argument whose
> premise is gone), **narrowed** (same claim, smaller or relocated subject), **deferred** (correct
> about v2, off the v1 roadmap). [`14-architecture-synthesis.md`](./14-architecture-synthesis.md)
> D-21 is the decision; **D-22 and C-16 record the one clause of OD-09 that could not be propagated as
> written** — constitution Principle IV binds every emitted tool, and v1 emits a shell and an HTTP
> client that can issue `DELETE`, so effect classification moves to a per-call runtime gate rather
> than deferring outright.

---

## Start here

**New to the project.** Read [`07-product-vision.md`](./07-product-vision.md) for what is being
built and why, then [`01-agent-anatomy.md`](./01-agent-anatomy.md) §1–§5 for the vocabulary the
rest of the corpus assumes. Finish with [`14-architecture-synthesis.md`](./14-architecture-synthesis.md)
for where everything landed.

**Making an architecture decision.** Start with
[`14-architecture-synthesis.md`](./14-architecture-synthesis.md), then follow the thread that
matters: control flow → [`03-graph-and-loop-architecture.md`](./03-graph-and-loop-architecture.md)
then [`10-topology-in-practice.md`](./10-topology-in-practice.md) (theory, then what shipping
systems actually do); harness → [`02-agent-harnesses.md`](./02-agent-harnesses.md) then
[`06-examples-inventory.md`](./06-examples-inventory.md) §7 then
[`13-claude-managed-agents.md`](./13-claude-managed-agents.md); tool surface →
[`01-agent-anatomy.md`](./01-agent-anatomy.md) §5 then
[`09-mcp-as-tool-surface.md`](./09-mcp-as-tool-surface.md).

**About to run experiments.** [`11-validation-plan.md`](./11-validation-plan.md) is the whole
program — read §1 (falsifiable hypotheses) and §7 (pre-registered kill criteria) *before* running
anything. Then [`12-examples-as-corpus.md`](./12-examples-as-corpus.md) §5 for the cheapest first
smoke test, and [`13-claude-managed-agents.md`](./13-claude-managed-agents.md) §7 for why the spike
may use a hosted runtime the product will not.

**Writing the spec.** ~~⛔ **Not yet — the production specification is blocked** on the
verifier-versus-LLM-judge experiment (`specs/001-discovery-validation/plan.md` **OD-11**, 2026-08-03;
[`11-validation-plan.md`](./11-validation-plan.md) §8 Phase 2). Read this path to prepare, not to
proceed.~~ ✅ **UNBLOCKED 2026-08-03 by `plan.md` OD-14, which retires OD-11's blocking condition** —
the experiment was built and dry-run at $0.00, its corpus cannot answer the question, and the
verifier's margin over an LLM judge is declared **UNMEASURED** and deferred to production traffic.
**Read [`VERDICT.md` §2](../specs/001-discovery-validation/VERDICT.md#all-three-v1-capabilities-ship-unmeasured)
before this path: all three v1 capabilities ship without measurement**, and OD-14 records that as a
deliberate departure from this feature's prove-before-build discipline rather than as a technicality.
[`07-product-vision.md`](./07-product-vision.md) §5–§6 enumerates the
decisions that must be made first and the proposed v1 cut.
[`14-architecture-synthesis.md`](./14-architecture-synthesis.md) says which of them are now closed.
[`08-auth-identity-and-secrets.md`](./08-auth-identity-and-secrets.md) §8 lists the hard security
requirements a v1 spec cannot omit. Process lives in [`../docs/spec-kit-workflow.md`](../docs/spec-kit-workflow.md).

---

## Document catalog

| Document | Lines | Purpose | Key findings |
|---|---:|---|---|
| [`01-agent-anatomy.md`](./01-agent-anatomy.md) | 1170 | Anatomy of an LLM agent: loop, context, memory, tools, MCP, planning, topologies, guardrails, models, reference architecture. | Harness explains most measured variance (42%→78% on CORE-Bench from scaffold alone); effective context degrades from ~50k tokens inside 1M windows; tool-selection accuracy falls past ~30–50 tools; memory is four tiers and files beat vector DBs for the agent-authored ones. |
| [`02-agent-harnesses.md`](./02-agent-harnesses.md) | 1001 | Survey of 18 harnesses/frameworks and a build-vs-adopt verdict. | Framework/runtime/harness is the only near-consensus taxonomy; coding agents are the battle-tested reference implementations; LangGraph checkpoints at super-step boundaries, not inside nodes; both lab SDKs are still pre-1.0. Verdict: adopt a thin substrate, build the harness. |
| [`03-graph-and-loop-architecture.md`](./03-graph-and-loop-architecture.md) | 990 | Graphs vs. loops as control-flow substrate; protocol enforcement via topology; durability. | The bare loop is the correct default; anything that must not be skipped belongs in topology, not the prompt; static skeleton + LLM-decided branches is the 2026 consensus; search loops (ToT/LATS) cost 5–100× for saturating gains ([2305.10601](https://arxiv.org/abs/2305.10601)); reflection without an external verifier degrades output. |
| [`04-self-improving-agents.md`](./04-self-improving-agents.md) | 724 | Six levels of self-improvement, evals, the graph-to-loop flywheel, prompt optimization, safety. | Only levels 1–3 are production-viable; self-critique without external feedback measurably worsens results ([2310.01798](https://arxiv.org/abs/2310.01798)); LLM judges are anti-correlated with truth on false-success detection (AUROC 0.18–0.30); DSPy GEPA/MIPROv2 work and are CI-cheap; the Darwin Gödel Machine reward-hacked its own detector. |
| [`05-frontier-lab-agent-definitions.md`](./05-frontier-lab-agent-definitions.md) | 863 | How Anthropic, OpenAI, Google, and xAI define "agent"; provider abstraction strategy. | All four agree on the core loop; only Anthropic draws a hard workflow/agent line; xAI publishes no formal definition; the load-bearing divergences are server-side tool execution and opaque reasoning state. Abstract at the message/tool layer only. |
| [`06-examples-inventory.md`](./06-examples-inventory.md) | 859 | Fit assessment of the vendored reference repos as tooling; codegraph verdict; harness recommendation. | `codegraph` (MIT, tree-sitter, 29 languages, route→handler extraction) is the right analysis substrate but has no concept of layers or bounded contexts — decomposition is a build; `spec-kit` adopt as process; recommendation is ADK as outer runtime + Claude Agent SDK as per-node coding executor. |
| [`07-product-vision.md`](./07-product-vision.md) | 693 | Vision and requirements brief: capability decomposition, hard problems, open questions, v1 scope. | The vision is two products (Class A on the codebase, Class B through the running app) and fusing them instantiates the lethal trifecta; boundary inference is not statically solvable in general; tool synthesis is commoditized, selection and verification are not; proposed v1 is one agent, read-only, FastAPI-first. **⚠️ Largely v2 after OD-09: its §3.1 and §3.2 defer in full, its §6 scope cut is superseded, and its §3.5 and §3.7 are promoted to the product. Carries a scope banner and per-section annotations.** |
| [`08-auth-identity-and-secrets.md`](./08-auth-identity-and-secrets.md) | 806 | Two credential planes; confused deputy; secret injection; iframe threat model; audit. | Model plane and resource plane must be separate subsystems; no lab offers third-party delegated OAuth; deterministic policy took attacker success from 74.6% to 0% across 879 attempts ([2603.20953](https://arxiv.org/pdf/2603.20953)); env vars fail when the agent has shell; the iframe path must not run the coding agent. |
| [`09-mcp-as-tool-surface.md`](./09-mcp-as-tool-surface.md) | 520 | Should the generated tool surface be MCP; adoption reality; transports; competitive prior art. | MCP is an export adapter, not the internal calling convention; the `2026-07-28` spec is the fourth breaking change in ~20 months and generated servers must be dual-era; progressive disclosure is not in the protocol; the white space is codebase → domain-operation MCP, which nothing ships today. |
| [`10-topology-in-practice.md`](./10-topology-in-practice.md) | 764 | Empirical survey of what best-in-class shipping systems actually do for control flow. | Claude Code kept the loop and added generated, journaled, replay-capable workflow scripts above it; OpenHands and ADK both built durability on append-only event logs; every fan-out system enforces many-readers/one-writer; unattended operation mandates spend caps, circuit breakers, and non-model termination. |
| [`11-validation-plan.md`](./11-validation-plan.md) | 772 | The falsifiable experiment program: hypotheses, corpus, tasks, arms, metrics, kill criteria. | Phase 0 can kill the thesis for ~1 week and <$300; the mean control is a baseline agent with `curl` + OpenAPI + a live socket; no LLM judge in the primary success path; null tasks measure false success at zero oracle cost; one arm (single agent given the full multi-agent budget) settles the topology question. **✅ Phase 0 ran and its §7 pivot criterion fired — this is the document that re-scoped the product. Phases 1–5 never ran; the §8 table now carries an outcome column saying which decisions were made by evidence and which by the pivot. Two of its unrun gates were then honored anyway, 2026-08-03: Phase 5's read-only branch fired by default (OD-10) and ~~Phase 2 is scheduled ahead of the spec (OD-11)~~ **Phase 2 was scheduled ahead of the spec (OD-11) and then de-scheduled the same day (OD-14) — built, dry-run at $0.00, never executed, and its quantity declared unmeasured and deferred to production.** **A third gate is now recorded as never honored at all:** §9.3's two independent full passes were never run, the within-session substitute is a lower bound on the quantity §9.3 defines, and every "tie" in the record was called against a floor that did not exist (U-46).** |
| [`12-examples-as-corpus.md`](./12-examples-as-corpus.md) | 501 | The vendored repos as analysis targets and test corpus; the first smoke test. | Eight repos, not nine — 1,109,021 source lines across 4,420 files; the one genuine Class B target is `adk-python` itself (26 routes, SQLAlchemy, same-repo source); the corpus is 78% Python with zero real PHP/Ruby/C#/Swift; and it cannot validate anything about a customer's production web app. |
| [`13-claude-managed-agents.md`](./13-claude-managed-agents.md) | 523 | Investigation of Anthropic's hosted agent runtime and its impact on the harness decision. | CMA is real, beta, and launched 2026-04-08; BYO-LLM via Bedrock/Vertex is disqualifying; a managed sandbox cannot reach internal endpoints (self-hosted sandboxes dissolve this); it covers 4 of 13 infrastructure needs; not ZDR/HIPAA-eligible. Use for the spike, not the product. |
| [`14-architecture-synthesis.md`](./14-architecture-synthesis.md) | 1114 | Capstone synthesis: the architecture the corpus converges on and the decisions it closes. | The moat is selection and consolidation, not generation; the two product classes must not be fused in v1; Claude Code already ships model-generated, journaled topology; decompose by bounded context or not at all; loop by default and escalate on "who holds the plan"; MCP schemas cannot carry effect metadata, so it stays an export adapter; the next action is a ~1-week, sub-$300 ceiling test, not a spec. **⚠️ The first of those is now v2 (D-21) and the MCP one is amended (D-06) — the ceiling test ran and re-scoped the product. This is the decision record; read its registers before any other document. Two owner decisions land here 2026-08-03: OD-10 makes v1 read-only (D-22 amended, D-16 dormant, C-16 re-weighed and still open), and ~~OD-11 blocks the production spec on the verifier-versus-judge experiment (P-07, P-09)~~ **OD-11 blocked the production spec on the verifier-versus-judge experiment and OD-14 retired that block the same day, declaring the verifier's margin over a judge UNMEASURED and deferring it to production — TL;DR 21, P-07, P-09**. Later the same day the egress limb OD-10 left open was worked through: C-17 and U-44 are new, and the finding is that Principle IV's network-allowlist bullet is unmet by v1 and had never been cited. That closed the same day: **OD-12** routes all sandbox egress through one mandatory proxy enforcing destination and method together (C-17 closed, the shell contradiction dissolved), and **OD-13** amends the constitution to v1.2.0; U-44 stays open. **A later refresh the same day propagates findings 013 and 014: C-18, U-45 and U-46 are new, D-19's safety limb is withdrawn for synthesized surfaces while its cost limb gets better evidence, and OD-07's cost range is restated to 2.20×–4.366× within session with the 9.3× demoted from a range endpoint — flagged for the owner at §3.1 rather than edited quietly.** |
| [`15-nvidia-oo-agents.md`](./15-nvidia-oo-agents.md) | 929 | External-substrate assessment: NVIDIA's object-oriented agent harness against E7, U-48, v2 synthesis, and the enforcement model. | Its capability suite is saturated at 97.9% and would fail this project's own 0.25–0.85 calibration band, so it corroborates nothing about E7; it reduces none of U-48's nine, and the two rows it could plausibly own are blocked by OD-16's dependency and by an FR-037 non-compliance measured with finding 003's counting rule; methods-as-tools removes schema authoring and leaves promotion selection, effect classification and postcondition derivation exactly where D-21 put them; NVIDIA's own paper and blog place sandboxing outside the agent process, so it is the layer above our enforcement point and not a replacement for it. |

---

## Cross-cutting themes

**Safety and the lethal trifecta.** Defined in [`01`](./01-agent-anatomy.md) §8 (injection-defense
ceilings, deny-rule ordering). Instantiated as a product risk in [`07`](./07-product-vision.md) §3.4
— Class A and Class B fused is the trifecta. Made concrete for credentials and the iframe in
[`08`](./08-auth-identity-and-secrets.md) §3, §5. Memory as an injection write channel in
[`04`](./04-self-improving-agents.md) §9. Security deltas specific to MCP in [`09`](./09-mcp-as-tool-surface.md) §7.
**Adjudicated for v1 in [`14`](./14-architecture-synthesis.md) C-16, and read that row before citing
any of the above:** the pivot removed the compile-time `no_trifecta` check, and **OD-10's read-only v1
does not restore it** — read-only cuts the destructive-action limb and leaves egress, so the trifecta
regression is narrowed rather than closed. **Read [`14`](./14-architecture-synthesis.md) C-17 next,
because it is where the egress limb is worked out and it changes what the corpus is claiming.** The
control that narrows it — default-deny outbound, pinned to the target's API host **and port**, DNS
denied or proxied, enforced at the host — is **not a new mitigation**: constitution Principle IV's
first bullet, [`08`](./08-auth-identity-and-secrets.md) §8.1 item 4 and
[`07`](./07-product-vision.md) §3.2.5 item 5 all require it, **v1 satisfies none of them**, and every
Principle IV argument in this corpus is about a *different* bullet. It discharges
[`14`](./14-architecture-synthesis.md) §2.9's non-negotiable 4, which OD-08 degraded. **It still does
not cut the leg** — the target application's own URL-fetching endpoints make it a confused deputy for
egress (U-44), and the operator-facing response channel is untouched — so the corpus's position is
**enumerated egress with a per-target condition, not a cut leg.** ~~A v1 requirement is drafted at
`plan.md` **OD-12** and is **proposed, not decided**.~~ **✅ Decided 2026-08-03. `plan.md` **OD-12**
makes it a v1 requirement and moves it one layer down: all sandbox egress traverses **one mandatory
proxy** enforcing the destination allowlist and the HTTP method allowlist together, which is what
makes it hold against a shell — the proxy cannot be walked past by a subprocess the way an in-process
`argv` check can (C-17, closed; v1's shell executes and no ladder classifies it). `plan.md`
**OD-13** amends the constitution to **v1.2.0**, replacing bullet 1's *"named hosts"* with the four
terms above in normative language. **The claim in bold two sentences up is unchanged** — a decided
mechanism is exactly when *enumerated egress* is most likely to get quietly upgraded to *prevention*,
and U-44 is as unmeasured as it was.

**Tool design and synthesis.** Quality rules and the ~30–50 tool threshold in
[`01`](./01-agent-anatomy.md) §5. Which functions deserve promotion, and synthesis at the trust
boundary rather than the function boundary, in [`07`](./07-product-vision.md) §3.2. Whether the
emitted surface speaks MCP in [`09`](./09-mcp-as-tool-surface.md), including the anti-auto-generation
lesson from FastMCP's author. Tool synthesis as a self-improvement level in
[`04`](./04-self-improving-agents.md) §6.

**Control flow: loops, graphs, durability.** [`03`](./03-graph-and-loop-architecture.md) is the
theory (loop default, graph on a declared constraint, framework durability ≠ real durability).
[`10`](./10-topology-in-practice.md) is the evidence from shipping systems and refines the rule to
"who holds the plan." [`02`](./02-agent-harnesses.md) §4 and §7 cover what harnesses actually
guarantee. Multi-agent cost and failure modes in [`01`](./01-agent-anatomy.md) §7; the arm that
settles it empirically in [`11`](./11-validation-plan.md) §4.

**Evaluation and verification.** The contract-derived verifier — signatures, response models,
status codes, exception classes as free external ground truth — appears in
[`03`](./03-graph-and-loop-architecture.md) §7.1, [`04`](./04-self-improving-agents.md) §2, and
[`07`](./07-product-vision.md) §3.5. [`11`](./11-validation-plan.md) turns it into oracles, metrics,
and pre-registered thresholds. The negative results about self-critique and LLM-as-judge are stated
in [`04`](./04-self-improving-agents.md) and re-tested as an object of study in [`11`](./11-validation-plan.md) §5.2.

**Provider and vendor strategy.** [`05`](./05-frontier-lab-agent-definitions.md) §4 draws the
two-tier abstraction line and names opaque continuation state as a first-class type.
[`02`](./02-agent-harnesses.md) §6–§7 covers framework lock-in and SDK churn.
[`13`](./13-claude-managed-agents.md) tests the strongest single-vendor option against it.
[`09`](./09-mcp-as-tool-surface.md) covers protocol-level vendor risk.

**Credentials.** [`08`](./08-auth-identity-and-secrets.md) owns this end to end. The BYO-LLM
constraint it establishes is what disqualifies the hosted runtime in
[`13`](./13-claude-managed-agents.md) §2, and deployment model remains an open question in
[`07`](./07-product-vision.md) §5.

---

## Reading conventions

Every document follows the same house style: a dated **`Last researched:`** line, a **TL;DR** block
of numbered load-bearing claims up front, a table of contents for the longer ones, **inline source
links** on every non-obvious claim, **confidence annotations** inline (`[emerging]` and similar),
and an explicit **open questions / could not verify** section near the end. Negative findings are
stated as negative findings, and cross-references point at sibling documents by section rather than
re-deriving. Density over length.

That style is encoded as a skill at
[`../.cursor/skills/research-doc-conventions/SKILL.md`](../.cursor/skills/research-doc-conventions/SKILL.md).
Read it before adding or editing a document here.

---

## Related material outside this directory

- [`../.specify/memory/constitution.md`](../.specify/memory/constitution.md) — the project
  constitution: the non-negotiable principles every spec, plan, and implementation is checked
  against.
- [`../docs/spec-kit-workflow.md`](../docs/spec-kit-workflow.md) — how spec-driven development runs
  here, including the Cursor-flavored hyphenated commands (`/speckit-specify`, `/speckit-plan`,
  `/speckit-tasks`, `/speckit-implement`).
- [`../.cursor/skills/README.md`](../.cursor/skills/README.md) — the project skills roster. Skills
  are how findings in this directory become operative at agent decision time; the roster records
  which are written, which are blocked on research, and which were deliberately deferred.
- `examples/` (git-ignored) — nine vendored reference repositories: `codegraph`, `spec-kit`,
  `adk-python`, `adk-docs`, `adk-samples`, `claude-agent-sdk-python`, `claude-code`,
  `claude-cookbooks`, `labs-OO-Agents`. Assessed as tooling in [`06`](./06-examples-inventory.md)
  and as an analysis corpus in [`12`](./12-examples-as-corpus.md); the ninth arrived later and is
  assessed on its own in [`15`](./15-nvidia-oo-agents.md).

---

## Status

Research is **complete** across documents 01–14, including the capstone synthesis
([`14-architecture-synthesis.md`](./14-architecture-synthesis.md)).

Decisions remain open on: which product v1 is (Class A vs. Class B vs. both), the agent-boundary
inference axis, the deployment model (self-hosted / hosted / both), and whether the iframe surface
ships at all. [`07`](./07-product-vision.md) §5 enumerates them;
[`14`](./14-architecture-synthesis.md) records which the corpus has since closed — consult it rather
than this list for current state.

**Next action:** run Phase 0 of [`11-validation-plan.md`](./11-validation-plan.md) — the ~1 week,
sub-$300 experiment that can kill the thesis — and only then open
[`/speckit-specify`](../docs/spec-kit-workflow.md).
