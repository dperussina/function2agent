---
name: provider-abstraction
description: Draws the line between what a model-provider abstraction layer should normalize and what it must never abstract, and specifies opaque continuation state as a first-class type. Use when adding support for a second model provider, writing an adapter or driver for Anthropic, OpenAI, Google, or xAI, designing the core turn/message/tool types, evaluating a middleware framework like LiteLLM or an agent SDK as an abstraction layer, or diagnosing multi-turn tool use that silently degrades after switching providers.
---

# Provider abstraction

Source: `research/05-frontier-lab-agent-definitions.md` §4.1–4.4.

**The split is clean: the labs' *definitions* of an agent are ~90% ignorable; a specific enumerable
set of *API-level* differences is not.** The non-ignorable ones leak into your core types, not just
your adapters.

## The rule: two tiers

**A thin, universal driver at the bottom. Your own opinionated primitives on top. One primary
provider, adapters written on demand.**

```
send(messages, tools, opaque_state)
    -> { text, tool_calls, opaque_state, usage, stop_reason }
```

A few hundred lines per provider. Everything in the "normalize" table below fits in it.

## What to normalize vs. what leaks

| # | Concern | Verdict |
|---|---|---|
| 1 | System prompt vs. `instructions` vs. developer message | Trivial |
| 2 | Message/content-block shapes (text, tool_use, tool_result, image) | Easy |
| 3 | Tool schema dialect — JSON Schema subsets, strict mode, `additionalProperties` | Moderate; per-provider schema sanitization is unavoidable |
| 4 | Tool call IDs and parallel-call semantics | Easy |
| 5 | Streaming event taxonomy | Moderate, tedious |
| 6 | Loop termination + turn-counting units | Easy once documented |
| 7 | Error / refusal / stop-reason taxonomy | Moderate — includes a real `refusal`-and-fallback branch |
| 8 | Token accounting and cache-hit reporting | Moderate |
| 9 | **⚠︎ Opaque continuation state** | **Leaks.** Model as `provider_state: opaque`. Never drop. Never merge across providers |
| 10 | **⚠︎ State locus** (client vs. server) | **Leaks.** Standardize on client-owned; accept that you forfeit some providers' background execution and cheapest paths |
| 11 | **⚠︎ Hosted tool execution** | **Leaks hard.** Cannot be normalized. Expose as a per-provider capability flag; do not pretend it is a tool |
| 12 | **⚠︎ Sandbox / compute** | **Leaks.** No common shape exists. Own your own sandbox |
| 13 | **⚠︎ Multi-agent primitives** | **Leaks.** Handoffs, subagents, A2A, and model-internal swarms are four different things. Build your own; do not adapt theirs |
| 14 | **⚠︎ Compaction / memory** | **Leaks.** One provider's is a server-side context edit, another's a sandbox capability, another's a managed service, another's a model behavior. Implement your own over your own transcript |

**Items 1–8 are a weekend of tedium. Items 9–14 are architecture.** Do not let a design treat them
as the same kind of work.

## Opaque continuation state is a core type

The #1 abstraction leak, and the one that fails **silently**.

All four labs require round-tripping a blob you cannot inspect to preserve reasoning across turns —
Anthropic thinking blocks, OpenAI reasoning items, Gemini thought signatures, xAI
`use_encrypted_content`. They are differently shaped, none are inspectable, none are portable.

**Dropping one does not raise an error. It silently degrades multi-turn tool use.** You get subtly
worse agents with no visible failure and nothing in the logs.

Requirements:

```
- [ ] Every turn/message in your core type carries provider_state: opaque
- [ ] The field is opaque by contract — no code branches on its contents
- [ ] It is never dropped on serialize/deserialize, checkpoint, or resume
- [ ] It is never merged, translated, or reused across providers
- [ ] Provider identity is stored alongside it, so a resume against a different
      provider is a detected error rather than a silent degradation
```

## Anti-patterns

- **Using a third-party middleware framework as your abstraction.** The four labs' SDKs are each
  ~1 year old and have already churned hard (Assistants→Responses, ADK 1.x→2.0 graph engine,
  AgentKit→deprecated). A middleware layer adds a *second* churning dependency between you and a
  churning API, and it will be the last to support each provider's newest capability. Write ~800
  lines of adapter you fully understand instead.

  > **Measured, 2026-08-02, and then acted on, 2026-08-03.** This anti-pattern stopped being a
  > prediction: `specs/001-discovery-validation/findings/003-runtime-provider-agnosticism.md` result
  > 7 counted a middleware adapter (`LiteLlm` under Google ADK) referencing xAI's opaque reasoning
  > field **zero times under every counting rule** — the exact silent degradation the checklist
  > above exists to prevent, in the layer adopted to prevent it. **`plan.md` OD-15 and OD-16 remove
  > both**: v1 talks to each vendor's own SDK behind a driver of ours, and `litellm` is not shipped
  > (it declares no license in its published package metadata — result 8 — which is a separate and
  > independently sufficient reason).
  >
  > **Two things that must travel with this, because the anti-pattern being vindicated is not the
  > whole story.** The four-provider tool-calling result everyone cites was measured **through** that
  > middleware, so the provider-capability half transfers and the adapter-implementation half does
  > not — owning the driver makes it **a test to pass rather than a result to inherit**. And a
  > middleware layer is not disqualified *in general* by one measurement; what the measurement shows
  > is that **you must count the opaque-state references yourself for every provider you claim to
  > support**, whichever layer you use. That count is cheap, and nobody had run it.
- **Normalizing hosted tools into your tool interface.** Every attempt produces a
  lowest-common-denominator interface worse than any of the originals, and it breaks the moment a
  provider ships something new. If your value proposition includes "every tool call is gated and
  auditable," you must either **forbid hosted tools** or accept explicit per-provider capability
  tiers.
- **Modeling both subagents and handoffs.** Pick one context topology for your own anatomy.
- **Defining budgets in a provider's turn units.** Define limits in *your* units and translate per
  provider.
- **Targeting one provider exclusively.** Not for portability piety — for routing economics. The
  2026 numbers show a >2× cost spread and a >15-point capability spread on the *same task class*
  depending on model choice. That routing is only possible if the provider is swappable.

## Pick a primary deliberately

Your defaults, prompts, tool schemas, and eval baselines will over-fit to whichever provider you use
most, whether you intend it or not. Choose on purpose.

For this project — functions → agents, tool-centric, code and filesystem adjacent — **Anthropic is
the reasonable default**: deepest MCP support, first-party context-management APIs, the `SKILL.md`
standard, the best-documented harness reasoning. Budget for the `refusal`-and-fallback branch, which
has no equivalent at the other three labs and must be handled in code.

## Conceptual models worth borrowing

- **Task / workflow / agent as a forcing function.** Maps directly onto the product question: *which
  functions deserve promotion to agents?* Most don't. A function needing three deterministic model
  calls is a workflow and should stay one. Make promotion a deliberate, labeled decision rather than
  a default. This is the single most useful borrowed idea.
- **"Every harness component encodes an assumption about what the model can't do on its own."** Adopt
  as a maintenance discipline: tag every piece of scaffolding with the model deficiency it
  compensates for, and re-test those tags on every model upgrade. Anthropic deleted their entire
  context-reset machinery when a model generation stopped needing it; the tags are what made that
  deletion safe.
- **Brain / hands / session.** Sessions are durable event logs you own; hands are sandboxes you own;
  brains are interchangeable. The right decomposition for a system that wants to swap brains.
- **A typed, serializable run result with resumable state** (OpenAI's `RunState` + resumable
  approvals) is the best-shaped human-in-the-loop primitive of the four.
- **Read the ecosystem conventions off disk.** Grok Build reads `CLAUDE.md`, `AGENTS.md`,
  `.claude/skills/`, `.agents/skills/`, and MCP configs out of the box. Emitted stacks should do the
  same — compatibility with settled conventions is free capability.

## Safely ignorable

The workflow-vs-agent taxonomy debate. A2A, unless you plan cross-org agent interop. Any specific
vendor's graph substrate, unless you adopt it. Governance stacks, unless selling into regulated
enterprise. UI-layer products.
