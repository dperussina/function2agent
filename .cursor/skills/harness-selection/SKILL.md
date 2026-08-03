---
name: harness-selection
description: Decides whether to adopt an agent framework or build the harness, and which substrate a generated stack compiles into. Use when evaluating LangGraph, the OpenAI Agents SDK, CrewAI, Mastra, Pydantic AI, AutoGen, Semantic Kernel, Microsoft Agent Framework, Google ADK, the Claude Agent SDK, Claude Managed Agents, Temporal, Restate, or DBOS; when adding any dependency to the agent loop or the model-facing path; when choosing what a generated artifact depends on at runtime; or when reviewing a proposal that resolves an orchestration problem by adopting a framework.
---

# Harness selection

Sources: `research/02-agent-harnesses.md` §2, §6; `research/06-examples-inventory.md` §3, §7;
`research/13-claude-managed-agents.md` §4, §7.

**Verdict: adopt a thin substrate, build the harness. Do not adopt a general-purpose agent
framework.** The reason is specific to this product rather than general: **`function2agent` *is* a
harness generator, so adopting a harness means adopting a competitor's opinions about the core
product.** If DeepAgents or the Claude Agent SDK already decides the planning representation,
compaction policy, and subagent semantics, there is very little product left.

## The dependency test — apply this before anything else

> **Avoid third-party abstractions in the model-facing path. Adopt mature third-party
> infrastructure in the execution path. The test is whether the dependency sees prompts and
> tokens.** If it does, it will churn with the model APIs and you should own it. If it does not, it
> is ordinary infrastructure and you should not rebuild it.

| Dependency | Sees prompts/tokens? | Verdict |
|---|---|---|
| LangChain, OpenAI Agents SDK, CrewAI, Mastra, DeepAgents | Yes | **Fail.** Own this layer |
| Temporal / Restate / DBOS | No — sits *behind* the loop | **Pass.** Never build durable execution |
| Sandboxes (E2B, Docker, Modal) | No | **Pass** — but own the `Workspace`-style interface so it is a runtime swap |
| OTel tracing | No | **Pass.** OTel, not a vendor SDK — OpenAI withdrew its Evals platform; OTel outlives vendors |
| DSPy (prompt/description optimization) | Yes, but offline against a metric | Pass once you *have* a metric; orthogonal to the loop |

The strongest evidence for durable execution passing: **four independent teams with the resources to
build durability instead integrated someone else's** — Pydantic AI (Temporal/DBOS/Prefect),
LlamaIndex (DBOS), Mastra (Inngest), Microsoft Agent Framework.

## Build/adopt by layer

| Layer | Call | Why |
|---|---|---|
| HTTP / provider transport (`anthropic`, `openai`) | **Adopt** | Auth, streaming, 429/5xx retries. Least-churning part of each vendor's surface |
| Message / tool / turn abstraction | **Build** — a few hundred lines | This is where vendor churn actually lands. See `provider-abstraction` |
| Agent loop | **Build** — genuinely 50–150 lines | Every framework's loop is a thin wrapper over the same thing plus opinions you didn't choose |
| Harness features (context mgmt, verification, budgets, subagents, hooks) | **Build, stealing designs** | **This is the product.** Copy OpenHands' event log and `Workspace` swap, Claude Code's hook taxonomy and budget-with-subagents, LangChain's middleware shape |
| Sandboxing | **Adopt behind an owned interface** | Security-critical, well-solved, not the differentiator |
| Durable execution | **Adopt — only when a constraint demands it** | Never build it; never add it without a declared durability constraint |
| Tracing | **Adopt OTel** | Export to LangSmith/Logfire/Phoenix as a backend choice, not a coupling |

## Churn is the dominant risk, and it is measured

In the ~12 months the survey covers: **AutoGen → maintenance mode. Semantic Kernel → maintenance
mode.** Assistants API shut down. Agent Builder killed at eight months. OpenAI Evals removed. ADK
superseded its own flagship abstraction. Pydantic AI shipped a breaking V2. Mastra shipped ~25 minor
versions in a quarter. The two lab SDKs with the most agent traffic are **both still pre-1.0 after
18+ months.**

**A generated artifact must outlive its generator's dependencies.** Binding generated code to any of
these means every user's generated agent breaks on someone else's schedule. AutoGen was among the
most-cited agent frameworks of 2024–25 and it is now frozen; assume any framework you bind to
tightly can go into maintenance mode inside two years.

And the abstractions do not even agree with each other. Handoffs (OpenAI) vs. delegation (Anthropic)
vs. super-steps (LangGraph) vs. events (LlamaIndex) vs. roles (CrewAI) vs. capabilities (Pydantic
AI) are not variations on a theme — **they imply different context semantics.** Generating into any
one of them bakes in that framework's model of what an agent is.

### Anti-recommendations, stated flatly

- **Do not start anything new on AutoGen or Semantic Kernel.** Both are in maintenance mode; AutoGen
  is explicitly community-managed with no new features, and the stale `autogen-agentchat` PyPI
  timestamp corroborates that it genuinely stopped shipping. Microsoft Agent Framework is the
  successor and is the obvious pick *only* for a Microsoft/.NET shop accepting Azure lock-in.
- **Do not adopt a framework to solve an orchestration problem you have not yet declared as a
  constraint.** Emit a tool and a loop; see `graph-vs-loop-decision`.
- **Do not generate artifacts that depend on a pre-1.0 agent framework.**

## The settled position for this project: ~~ADK outside, Claude Agent SDK inside~~ **no framework at all for v1**

**REVERSED IN PART 2026-08-03 — `specs/001-discovery-validation/plan.md` OD-15, OD-16.** v1 runs on
**no agent framework**. The loop, the runner, the session store, checkpoint and resume, and a thin
HTTP/SSE serving surface are all ours; each provider is reached through that vendor's own SDK behind
a driver of ours, with **no `litellm`** (OD-16 — it declares no license). The Claude Agent SDK
remains an **opt-in** second executor path, unchanged (OD-02).

**Why, so this is not read as a churn argument** — three of OD-01's four grounds did not survive a
one-agent, one-loop v1:

- **Graph execution has no subject.** One agent and one loop hosted on a workflow tier is *a graph
  for a `for` loop*.
- **Provider abstraction was measured non-compliant.** Finding 003 result 7 counted the adapter
  referencing one provider's opaque reasoning field **zero times under every counting rule**,
  against a production spec requiring that round-trip for four providers.
- **Serving rested on nothing measured.** No experiment ever exercised it.

Lifecycle survived alone, and **one surviving limb does not justify the dependency.**

**Do not repeat this as a general rule.** It is not a finding that ADK is unsuitable; it is a
finding that v1 is a single-agent read-only runtime, which is not the product OD-01 was taken for.
Re-run the four grounds against whatever you are actually building.

**The cost, which must travel with the decision:** nine capabilities moved from adopt to build —
loop, runner, session store, checkpoint/resume, tool-schema translation, per-provider cost table,
spend ceiling, terminal signals, serving event stream — **with no estimate in any committed
artifact** (`research/14-architecture-synthesis.md` **U-48**). The one loop-safety primitive that was
measured *working* was ADK's checkpoint/resume; v1 now has **no measured resume machinery at all**.
And the four-provider tool-calling result was measured *through* the removed path, so it is a test
v1 must pass rather than a result it inherits.

**The pairing cost below is retained because the Claude SDK path still exists, and because it is the
shape of cost any second executor carries:**

- **Two session systems.** ~~ADK sessions~~ **our sessions** and Claude SDK sessions are different
  objects with different lifetimes; something has to reconcile them. *One of the two is now ours,
  so the divergence is closable by design rather than tracked across a vendor's calendar.*
- **Two permission models.** ~~ADK's~~ **Ours** and the Claude SDK's hook/permission surfaces do not
  compose; deny rules must be enforced in *one* place (see `agent-safety-and-sandboxing` for the
  ordering).
- **Two deprecation calendars.** ~~Two vendors, two release cadences~~ — **one vendor now, on the
  opt-in path only.** This is the one line OD-15 genuinely improves.

Accept it for the spike. Revisit if the seam leaks. The internal interface is what makes revisiting
possible, which is why it is day-one work and not cleanup.

## Claude Managed Agents: spike-only, never in a generated artifact

Two disqualifying facts, both verifiable rather than inferred:

1. **A customer's Bedrock or Vertex account cannot run CMA sessions.** Anthropic's pricing page lists
   cloud-platform pricing as *not* applying, reason: "Not available on partner-operated cloud
   platforms." BYO-LLM is therefore **bifurcated, not degraded** — customers on an Anthropic key are
   fully served; customers on Bedrock or Vertex, which is the majority posture for enterprises with
   cloud commitments (and exactly the segment with internal endpoints worth wrapping), cannot be
   served at all.
2. **A managed cloud sandbox cannot reach a customer's internal endpoint** directly — only through a
   research-preview tunnel or a round-trip through your own infrastructure, at which point you are
   the tool-execution path again and have re-taken the job CMA was adopted to do.

It also fails the dependency test outright: it sees prompts *and* tokens *and* owns the loop.

**Where CMA genuinely wins: time-to-first-run** — three API calls versus about a week of container
plumbing. That is the entire basis for using it as a disposable validation spike. Write the stop
condition down before starting: *no CMA call may appear in any code path intended for the generated
artifact, and no spike may be promoted to production without a from-scratch reimplementation on
~~ADK~~ **v1's own runtime (OD-15, 2026-08-03)**.* **Spike drift is the only real risk here and it is
a governance problem, not a technical one.**

## The Claude Agent SDK license: resolved, with one live constraint

**Resolved 2026-08-02.** The npm "SEE LICENSE IN README.md" and the PyPI "MIT" are not in conflict —
they describe different layers.

- **The SDK source is MIT.** Verified in `examples/claude-agent-sdk-python` v0.2.128: `LICENSE` is a
  verbatim MIT license (© 2025 Anthropic, PBC), and `pyproject.toml` declares `license = {text = "MIT"}`
  with the OSI MIT classifier.
- **The bundled Claude Code CLI is not.** The package bundles the CLI (`_cli_version.py` pins
  `2.1.220`; the README says it "is automatically bundled with the package"). That binary is
  closed-source under Anthropic's Commercial Terms of Service.
- The README's terms section resolves the apparent conflict itself, deferring to a component's own
  LICENSE file where one exists. MIT governs the wrapper; Commercial ToS governs the CLI and the
  service.

**The rule that follows.** Using the SDK inside our runtime is fine — each operator brings their own
Claude entitlement. **Emitted agent packs must declare the SDK as a peer dependency the operator
installs. Never vendor it into a generated artifact**, because that redistributes the bundled CLI and
MIT grants no rights to it. Confirm the published wheel's actual bundle contents before shipping any
distribution model, and get written sign-off from Anthropic before one that ships the CLI.

Do not record the SDK as flatly "MIT" in a dependency inventory. Record it as *MIT wrapper +
proprietary bundled runtime*, which is the fact that governs redistribution.

`02` §6.5 named a clean OSS license at 1.0 as the condition that would weaken "build the harness."
That condition is **not** met: the runtime underneath is still proprietary, so the build-the-harness
recommendation stands.

## What would change the verdict

- **Claude Agent SDK reaches 1.0 with a clean OSS license** → "build the harness" weakens
  considerably; it becomes a stable, best-in-class harness to compile into.
- **MCP becomes the universal tool interface** → emit an MCP server and let the user's harness
  consume it, which makes the framework question mostly moot. This is the single most likely thing
  to change the design.
- **A durable-execution-native agent framework reaches 1.0** with agent-shaped ergonomics *and*
  solves memoization-vs-model-upgrade → adopting would beat building.

Two rules that fall out of the architecture and are easy to lose:

- **The unit of checkpointing must be smaller than the unit of side effect.** When a tool is known
  to have side effects, emit it as its own durable step; never inline it with another effect.
- **Sandboxing and durability are runtime swaps, not codegen forks.** The same generated agent runs
  in-process for development and containerized/durable in production by changing configuration, not
  by regenerating.
