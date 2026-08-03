<!--
SYNC IMPACT REPORT — AMENDMENT 1.2.0
====================================
Version change: 1.1.0 → 1.2.0
Bump rationale: MINOR. Materially expanded guidance within an existing principle.
No principle removed, nothing redefined, and no existing artifact invalidated —
which is what the versioning policy reserves MAJOR for. Two further reasons this
is not MAJOR, stated because the amendment does *narrow* what counts as
compliant. First, the artifacts MAJOR protects do not exist: no product code has
been written and no agent pack has been emitted, so there is nothing to
invalidate. Second, no compliant configuration is made non-compliant, because
nothing satisfied the bullet in its prior form either — the emitted stack v1
describes has open outbound network and fails "network allowlisted to named
hosts" as it already stood (research/14-architecture-synthesis.md C-17). This is
the same reasoning and the same bump the 1.1.0 amendment to Principle I took, and
it is matched deliberately rather than re-derived.

Principle amended:
  - IV. Structural Safety Boundaries (NON-NEGOTIABLE) — bullet 1 (Sandboxing with
    a real boundary). "Network allowlisted to named hosts" is replaced by a
    four-term specification: addresses pinned at configuration time; host *and*
    port granularity; DNS denied or proxied; loopback, RFC 1918, link-local and
    the cloud metadata address denied even on an allowlisted host. No other
    bullet, principle, or section is touched.

Owner approval: obtained 2026-08-03, as the amendment procedure requires for a
NON-NEGOTIABLE principle. Recorded as OD-13 in
specs/001-discovery-validation/plan.md.

Migration plan for artifacts emitted under 1.1.0: none required. No product code
exists and no agent pack has been emitted. Identical in substance to the 1.1.0
migration plan and empty for the same reason.

Evidence base for the amendment:
  - research/14-architecture-synthesis.md C-17 — v1's emitted stack has
    unrestricted outbound network, and no safety argument in the corpus had ever
    cited this bullet. Every one of them reasons from bullet 2's permission
    tiers.
  - research/14-architecture-synthesis.md §2.9 non-negotiable 4 — network
    reachability is the real control, and specs/001-discovery-validation/plan.md
    OD-08 degraded it by making co-location the default topology rather than a
    deployment mistake. Under co-location the target application and its database
    routinely share a host, so host-granular allowlisting permits `psql` to the
    allowlisted host.
  - research/08-auth-identity-and-secrets.md §8.1 item 4 — default-deny egress at
    the host, with the metadata endpoint and RFC 1918 blocked, is already listed
    among the hard requirements ("do not ship without these").
  - research/07-product-vision.md §3.2.5 item 5 — egress control is a runtime
    requirement rather than a deployment detail.

Rationale: the prior phrasing named the control and specified it in a way that
does not survive contact with the deployments this project ships into. Each of
the four added terms corresponds to a concrete defeat of the one-line version: a
name-keyed allowlist is DNS-rebindable onto loopback; host granularity permits a
database connection to the very host the allowlist names; a reachable recursive
resolver exfiltrates without ever completing a connection to a blocked
destination; and the cloud metadata address is credential theft reachable from
inside an otherwise correct allowlist. The amendment strengthens the principle
rather than relaxing it. It makes plan.md OD-12 discharge a specification rather
than paraphrase one.

---
PRIOR REPORT — AMENDMENT 1.1.0
==============================
Version change: 1.0.0 → 1.1.0
Bump rationale: MINOR. Materially expanded guidance within an existing
principle. Nothing removed, nothing redefined, no previously-compliant artifact
made non-compliant.

Principle amended:
  - I. Contract-Derived Verification (NON-NEGOTIABLE) — one requirement added to
    the Enforcement paragraph: a derived verifier must be validated against an
    artifact its own derivation did not produce, or be marked provisional and
    carry provenance and confidence.

Owner approval: obtained 2026-08-02, as the amendment procedure requires for a
NON-NEGOTIABLE principle. Recorded as OD-03 in
specs/001-discovery-validation/plan.md.

Migration plan for artifacts emitted under 1.0.0: none required. No product code
exists and no agent pack has been emitted.

Evidence base for the amendment:
  - specs/001-discovery-validation/findings/007-contract-extraction.md §4 —
    disabling one derivation rule left 15 of 69 endpoints (21.7%) with contracts
    that were fluent, plausible, and wrong about every field name on the wire,
    with nothing in the output indicating it.
  - specs/001-discovery-validation/findings/004-recall-against-authoritative-key.md
    — of 355 populated docstring values, exactly one was the real docstring.
  - specs/001-discovery-validation/findings/010-deployment-reachability.md and
    011-reachability-without-schema.md — a mechanism measured at precision
    1.0000 turned out to be exact only because of a property of the test target.

Rationale: Principle I as ratified partitioned nodes into *has a derivable
verifier* and *has none*. Three findings produced a third category by unrelated
mechanisms — a verifier that was derived, looks complete, and is wrong. That
case fits neither branch, and it is the more dangerous of the two failures the
principle already governs, because a missing verifier announces itself and a
wrong one does not. This amendment strengthens the principle rather than
relaxing it. It makes decision D-17 in research/14-architecture-synthesis.md
enforceable.

---
PRIOR REPORT — RATIFICATION 1.0.0
=================================
Version change: none (template) → 1.0.0
Bump rationale: MINOR-from-nothing is not applicable; this is the initial
ratification of a previously unfilled template, so it establishes 1.0.0.

Principles defined (all new — the file previously held only placeholders):
  - [PRINCIPLE_1_NAME] → I. Contract-Derived Verification (NON-NEGOTIABLE)
  - [PRINCIPLE_2_NAME] → II. Topology Encodes Protocol
  - [PRINCIPLE_3_NAME] → III. Default to the Loop
  - [PRINCIPLE_4_NAME] → IV. Structural Safety Boundaries (NON-NEGOTIABLE)
  - [PRINCIPLE_5_NAME] → V. Two-Tier Provider Abstraction
  - added              → VI. Observability Is a Prerequisite
  - added              → VII. Test-First and Fixture-Backed (NON-NEGOTIABLE)
  - added              → VIII. Versioned Artifacts, Earned Complexity

Sections added:
  - [SECTION_2_NAME] → Additional Constraints: Analysis, Emission, Integration
  - [SECTION_3_NAME] → Development Workflow and Quality Gates
  - Governance (filled)

Sections removed: none.

Follow-up TODOs: none. No placeholder tokens deferred.

Evidence base: research/03-graph-and-loop-architecture.md (§8, §10, §11.4, §11.6),
research/04-self-improving-agents.md (§2.3, §5.1, §6, §11.2, §11.4),
research/05-frontier-lab-agent-definitions.md (§4.2, §4.3),
research/02-agent-harnesses.md (Claude Agent SDK permissions/hooks),
research/06-examples-inventory.md (tooling fit).
-->

# function2agent Constitution

`function2agent` statically analyzes an arbitrary codebase in an arbitrary
language, decomposes it into architectural layers and domains, and emits a
multi-agent system whose agents hold both general coding tools and tools
synthesized from the target application's own operations. The generated system
holds shell access, can mutate the target application's data, and is reachable
from untrusted end-user input. These principles exist because that combination
is unforgiving of convenience.

## Core Principles

### I. Contract-Derived Verification (NON-NEGOTIABLE)

Every verification signal in an emitted agent MUST derive from an artifact the
target codebase already contains: function signatures, return types,
precondition assertions, postconditions and invariants, exception classes,
existing tests, and observable state. `function2agent` MUST NOT ship LLM
self-critique, reflection, or LLM-as-judge as the default or only critic for
any emitted node, and MUST NOT let a model decide "did this succeed."

Rationale: intrinsic self-correction without an external signal measurably
*degrades* reasoning, and the apparent gains in early self-correction work were
artifacts of oracle-guided stopping (Huang et al., arXiv:2310.01798). On the
specific task of separating false success from honest failure, LLM judges score
AUROC 0.18–0.30 — anti-correlated with truth (arXiv:2606.09863). Because we
start from functions, we inherit a verifier that most agent frameworks have to
invent, and one that is far harder to reward-hack than a learned or model-based
reward. That inheritance is the product's central differentiator, not an
implementation detail.

Enforcement: a promoted function MUST emit a node contract (reads, writes, pre,
post, cost, idempotency key, failure taxonomy) and a verifier derived from its
return type and postconditions. A node with no derivable verifier MUST be
emitted as explicitly unverified and surfaced to the operator, never silently
backed by a model critic. **A derived verifier MUST be validated against an
artifact its own derivation did not produce. Where no independent artifact
exists, it MUST be marked provisional and carry its provenance and confidence —
because a verifier that is complete and wrong is indistinguishable from a
correct one at the point of use.** Where a model must judge, it MUST be pairwise
with order-swapping, calibrated against human labels, and reported as an
estimate.

### II. Topology Encodes Protocol

Anything an agent MUST NOT skip MUST live in graph structure, not in a system
prompt. A prompt saying "always validate before writing" is a suggestion; an
edge routing `write → validate → commit` is a guarantee. Prompt-level
requirements degrade with context length and under adversarial input; topology
does not.

Every emitted topology MUST be serializable data (not code), diffable,
content-addressed, and versioned, and MUST carry a machine-checkable
`invariants` block — for example, "`charge_card` is unreachable without
`validate_order`" and "every irreversible node is preceded by an approval
node." Those invariants MUST run as topology tests on every change, whether the
change originates from a human pull request or from an optimizer. Topology tests
assert reachability and ordering properties of the compiled graph, require no
model, and run in milliseconds.

Prohibited: a conditional edge whose predicate is a model answering "should we
do the mandatory step?" That moves the prompt into the graph and keeps all of
its unreliability.

### III. Default to the Loop

The default emission for a promoted function MUST be a plain tool plus a loop.
A graph MUST be emitted only when a real constraint is declared: an ordering
constraint, a mandatory step, a human approval gate, or a compensating action.
Graph machinery is a cost paid in exchange for enforcement, not a general
upgrade, and "graph for a `for` loop" is a recognized failure mode.

The trigger for escalating from loop to graph is not "this is getting
complicated." It is "there is a step that must happen and sometimes does not."
Escalation MUST cite the specific declared constraint in the emitted artifact.

### IV. Structural Safety Boundaries (NON-NEGOTIABLE)

Generated agents combine shell access, the ability to mutate a target
application's data, and — via the embeddable iframe integration path —
exposure to untrusted end-user input. Safety for that combination MUST be
structural, never advisory prose in a prompt.

Required, as architecture:

- **Sandboxing with a real boundary.** Filesystem scoped, CPU/memory/wall-time
  capped, no credentials outliving the run, and outbound network **default-deny
  with an egress allowlist meeting all four of the following**. Each term names
  a way the one-line version is defeated in practice; a configuration missing
  any one of them does not satisfy this bullet.
  - **Addresses pinned at configuration time**, never names re-resolved per
    request. A name-keyed allowlist re-resolves, and a re-resolved name can be
    re-pointed at loopback or at the database.
  - **Host *and* port granularity**, never host alone. Where the target
    application and its database share a host — the ordinary case under
    self-hosted co-location — a host-granular allowlist permits a direct
    database connection to the allowlisted host and defeats this requirement by
    way of its own remedy.
  - **DNS denied or proxied.** A reachable recursive resolver exfiltrates
    without ever completing a connection to a blocked destination, and it
    defeats the two terms above outright.
  - **Loopback, RFC 1918, link-local and the cloud metadata address denied even
    on an allowlisted host.** The metadata address is credential theft rather
    than leakage, and it is reachable from inside an otherwise correct
    allowlist.

  Code or a tool synthesized from a spec is untrusted code.
- **Permission tiers.** Every emitted tool MUST be classified read-only,
  reversible-write, or irreversible/destructive, and the tier MUST be
  enforced by an interception point that can *block*, not merely audit.
- **Human gates on destructive operations.** Topology-level, so a caller
  cannot argue past them — the model never gets a vote.
- **Untrusted-input containment.** Input arriving over the iframe or HTTP/SSE
  surface MUST NOT be able to reach an irreversible tool without traversing a
  gate. Tool exposure over that surface is allowlist-only; deny by default.
- **Secrets never inline.** Configuration reaches the generated stack by
  environment-variable injection; secret values MUST NOT be written into
  emitted artifacts, topologies, traces, or the knowledge layer.
- **Traceable lineage.** Every synthesized tool, prompt, and topology revision
  MUST be attributable to an author, an input, and a content hash. Guardrails,
  evals, and the invariant list MUST live where an agent cannot modify them.

Escalation across a tier boundary is a MAJOR change to the constitution's
governance surface and MUST be reviewed as such.

### V. Two-Tier Provider Abstraction

Provider integration MUST be two-tier: thin and universal at the bottom,
opinionated and ours above it. The bottom tier is a driver of roughly
`send(messages, tools, opaque_state) -> {text, tool_calls, opaque_state, usage,
stop_reason}` covering the message, tool, and turn layer only.

Provider-opaque reasoning state — Anthropic thinking blocks, OpenAI reasoning
items, Gemini thought signatures, xAI encrypted content — MUST be a first-class
type on every turn (`provider_state: opaque`), never an adapter-local detail.
It MUST be round-tripped verbatim, never dropped, and never merged across
providers. Dropping it degrades multi-turn tool use silently rather than
erroring, which is precisely why it needs a type.

Hosted/server-side tool execution, provider sandboxes, provider multi-agent
primitives, and provider memory MUST NOT be abstracted. They have no common
shape, and normalizing them yields an interface worse than any original.
Expose them as per-provider capability flags; own our own sandbox, orchestration,
and memory. State ownership standardizes on client-owned, accepting the loss of
provider-side background execution as a deliberate trade.

### VI. Observability Is a Prerequisite

Tracing is built before, not after, the capability it observes. A capability
that cannot be attributed to a versioned node MUST NOT ship.

Every emitted system MUST produce, from day one: one span per node with a
**versioned node identity**; **typed terminals** (each success and failure
outcome named, not a generic error); the **routing decision recorded with its
predicate inputs** for every conditional edge; precondition and postcondition
results; an explicit retry-versus-repair distinction; and per-node cost. The
routing decision is the field teams most often omit and the one failure
attribution most needs.

Rationale: failure localization is a query over traces grouped by
`(terminal_type, failing_node, incoming_edge)`. Versioned node identity and
content-addressed artifact versions are nearly free now and impossible to
retrofit. Everything downstream — evaluation, prompt optimization, rollback —
is unbuildable without them.

### VII. Test-First and Fixture-Backed (NON-NEGOTIABLE)

Tests are written and MUST fail before implementation. For this project that
discipline has a specific shape, because the units under test are an analyzer
and a generator, not a web application:

- **Analyzer**: every supported language and framework MUST have a committed
  fixture repository plus asserted expected decomposition (layers, domains,
  route→handler edges, symbol graph). Language support without a fixture is
  not supported.
- **Generator**: emitted artifacts MUST be asserted structurally — topology
  tests for reachability and ordering invariants, contract tests per node,
  schema tests on the serialized topology and the knowledge layer.
- **Determinism**: analysis of a fixed input MUST be reproducible, and emitted
  artifacts MUST be byte-stable given the same input and version. Model calls
  in tests MUST be served from recorded cassettes keyed by
  `(node_id, step, prompt_hash)`; cassette replay tests the plumbing, and
  evaluations test the prompts.
- **Integration surface**: the HTTP/SSE contract, the iframe embed contract,
  and environment-variable injection MUST each have contract tests that fail
  closed on missing or malformed configuration.

Adding a supported language, a new emitted node kind, or a new tool tier
requires its fixtures and contract tests in the same change.

### VIII. Versioned Artifacts, Earned Complexity

Every artifact `function2agent` produces or consumes MUST be versioned and
content-addressed: the topology, the node contracts, the prompts, the knowledge
layer schema, and the emitted agent pack as a whole. Semantic versioning
applies, and rollback MUST be one command. Breaking changes to an emitted
artifact schema are MAJOR and MUST ship with a migration path for previously
generated systems.

Complexity MUST be earned, not anticipated. Prefer the simplest emission that
satisfies a declared constraint; prefer one agent with more tools over several
agents that must re-explain context to each other, since a handoff costs tokens
and loses information at every boundary. Any new layer, framework dependency,
or agent boundary MUST be justified in the plan against a named failure it
prevents. Unjustified structure is a review defect, not a style preference.

## Additional Constraints: Analysis, Emission, Integration

**Language and stack neutrality.** Analysis MUST be language-agnostic in
architecture. A language is "supported" only when it has committed fixtures and
asserted decomposition output; anything else is explicitly unsupported rather
than best-effort. Architectural inference (layers, domains, bounded contexts) is
a layer we own on top of a symbol-level graph — it is a build, not a
configuration, and MUST be treated as such in planning.

**Knowledge and memory layer.** The knowledge layer is derived from analysis and
MUST record provenance for every fact: source file, symbol, analyzer version,
and content hash. It MUST be rebuildable from the codebase alone. Memory writes
MUST carry provenance and a retention policy, and MUST be restricted to
designated write nodes rather than available to every agent.

**Tool synthesis.** A tool synthesized from the target application's
functionality MUST pass its own test in a sandbox before entering any registry;
this gate fails closed. The tool author and the test author MUST be separate,
and the test author MUST see only the contract — name, signature, purpose — so
the test is adversarial rather than a mirror of the implementation. Run-local
synthesized tools may be automatic; promotion to a shared registry requires
human review.

**Integration surface.** HTTP/SSE and the embeddable iframe snippet are the
supported integration paths. Both MUST enforce the permission tiers of
Principle IV, MUST authenticate before exposing any non-read-only tool, and
MUST treat all payloads as untrusted. Configuration reaches the generated stack
through environment-variable injection with a declared, validated schema;
startup MUST fail loudly on a missing or invalid required variable rather than
degrading silently.

**Self-improvement boundary.** In-context contract-verifier repair loops and
provenance-tagged memory are permitted defaults. Prompt and program
optimization is machine-proposed and human-approved. Tool/skill synthesis and
any topology modification are human-gated with mandatory invariant checks and
one-command rollback. Weight updates are out of scope. The governing question
is "does this change persist?" — if it does, a human approves it.

## Development Workflow and Quality Gates

**Spec-driven development is the process of record.** Work proceeds through
GitHub Spec Kit: constitution → specify → clarify → plan → tasks → analyze →
implement, with `checklist` and `converge` available as needed. Implementation
MUST NOT begin before a spec, a plan, and a task list exist for the work.
Artifacts live under `specs/<NNN>-<short-name>/` and are reviewed as code.

**Constitution check is a plan gate.** Every plan MUST include an explicit
Constitution Check confirming compliance with these principles and naming any
deviation. A deviation MUST be recorded in the plan's complexity-tracking
section with the simpler alternative that was rejected and why. Unrecorded
deviations block merge.

**Review gates.** A change MUST NOT merge unless: tests were written first and
initially failed; fixtures exist for any new language or node kind; topology
invariant tests pass; traces carry versioned node identity, typed terminals,
and recorded routing decisions; and no new capability crosses a permission tier
without a structural gate. Changes touching the sandbox boundary, permission
tiers, human gates, or the invariant list require a second reviewer.

**Research is evidence, not decoration.** Architectural claims in specs and
plans MUST cite the research under `research/` or a primary source. Where the
evidence is weak or contested, the plan MUST say so rather than asserting
confidence the sources do not support.

## Governance

This constitution supersedes all other project practices, conventions, and
prompts. Where a prompt, template, or generated artifact conflicts with it, the
constitution wins and the conflicting artifact MUST be corrected.

**Amendment procedure.** Amendments are proposed as a pull request that edits
this file, states the version bump and its rationale, and includes a Sync Impact
Report as an HTML comment at the top of the file listing version change,
modified principles, added and removed sections, and any deferred placeholders.
Amendments touching a NON-NEGOTIABLE principle require explicit owner approval
and a migration plan for artifacts already emitted under the prior version.

**Versioning policy.** Semantic versioning applies to this document. MAJOR:
backward-incompatible governance changes, principle removals, or redefinitions
that invalidate existing artifacts. MINOR: a new principle or section, or
materially expanded guidance. PATCH: clarifications, wording, and non-semantic
refinements. Every amendment updates the version line and the Last Amended date.

**Compliance review.** Every pull request and review MUST verify compliance
against the review gates above. The Spec Kit `analyze` phase MUST be run before
`implement` on any feature that adds an emitted artifact kind, a permission
tier, or a supported language. Complexity MUST be justified in the plan.
Runtime development guidance for agents working in this repository lives in the
`.cursor/skills/speckit-*` skills and the templates under `.specify/templates/`;
those are subordinate to this document.

**Version**: 1.2.0 | **Ratified**: 2026-08-02 | **Last Amended**: 2026-08-03
