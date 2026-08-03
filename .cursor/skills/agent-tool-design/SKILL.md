---
name: agent-tool-design
description: Designs and reviews tools exposed to an LLM — names, descriptions, parameter schemas, error messages, return shapes, and tool-set size. Use when defining a tool or MCP server, writing a tool schema or JSON Schema for function calling, synthesizing tools from an existing codebase, deciding how many tools an agent should have, or diagnosing an agent that picks the wrong tool, hallucinates IDs, or burns context on tool results.
---

# Agent tool design

> **Standing: v1, narrowed — this skill outlived the sentence that justified it.** `plan.md` OD-09
> (2026-08-02) removed tool synthesis from v1, so *this project's core job is synthesizing tools from
> arbitrary code* is no longer true of v1. **The skill still applies, to two things.** ① **The tools
> v1 actually emits** — a shell, an HTTP client, a spec reader, a verifier interface. They are few,
> they are hand-written rather than generated, and every rule below about names, descriptions,
> parameter schemas, error messages and return shapes applies to them **more** sharply, because with
> four tools there is nowhere for a bad description to hide. ② **v2 synthesis**, via
> `tool-synthesis-from-code`.
>
> **One finding below is now the most load-bearing thing in the skill and should be read first:**
> a hand-written surface returning **records** lost a whole task family to a `jq` pipeline, while a
> single tool returning an **answer** moved a task by 35× (D-19). Return shape beat tool count in the
> only experiment that measured either.

Source: `research/01-agent-anatomy.md` §5; standing per `research/14-architecture-synthesis.md`
D-19, D-21. ~~This project's core job is synthesizing tools from arbitrary code, so tool quality *is*
product quality.~~ **v1's core job is verifying what the agent did; tool quality is now a property of
a small hand-written surface rather than of a generator.**

**The mental model:** you are writing an API for a capable but amnesiac contractor who reads your
docs exactly once, cannot ask clarifying questions, and is penalized for every token they read.

## Review checklist

Run this against every tool before it ships. Any unchecked box is a defect, not a nitpick.

```
- [ ] Name is verb-first, namespaced, and has no near-synonym in the same tool set
- [ ] Description says what it does, WHEN to use it, and when NOT to
- [ ] Description disambiguates against every sibling tool it could be confused with
- [ ] Every free-string parameter that has a closed domain is an enum instead
- [ ] Parameter object is flat, not deeply nested
- [ ] Required set is minimal; every optional param justifies the decision it imposes
- [ ] No parameter is an opaque ID the model has no discoverable way to obtain
- [ ] Units and formats live in the PARAMETER description, not the tool description
- [ ] Errors are returned as observations, never thrown
- [ ] Every error states: what was wrong, the valid space, the next action, transient vs. terminal
- [ ] Return is summary + handle, not a full payload; output size is hard-capped and says so
- [ ] Tool set is under 30 tools, or has deferred loading (see "Sizing")
- [ ] read_only is declared as metadata (see graph-vs-loop-decision and multi-agent-topology-review)
```

## Naming

`search_customer_orders` beats `query`. Namespace once you aggregate sources
(`stripe_refund_create`), because collisions cause selection failures.

`get_user`, `fetch_user`, and `lookup_user` coexisting is a bug in the tool set, not in the model.
When synthesizing tools from a codebase, near-synonyms are the *default* output — dedupe
aggressively before emitting.

## Descriptions

The description is both the retrieval key and the selection criterion. Its main job in a large tool
set is **disambiguation work against siblings**.

```
Refund a Stripe charge. Use when the customer has an existing completed
payment and you have confirmed the refund amount. Do NOT use for
subscription cancellations (use stripe_subscription_cancel) or for
disputing chargebacks (not supported).
```

Negative test: if a competent engineer reading only the schema would have to guess, the model will
guess worse.

## Error messages are prompts

They are the highest-leverage text in the whole tool implementation, because a model reads them and
decides what to do next.

```
BAD:   Error: 400
BAD:   ValidationError: invalid input
BAD:   <500-line traceback>

GOOD:  Error: invalid `currency` value "dollars".
       Allowed values: USD, EUR, GBP, JPY.
       Retry with a valid currency code.

GOOD:  Error: order ord_8823 not found.
       Use search_orders(customer_email=...) to find valid order IDs.
       Do not guess order IDs.

GOOD:  Error: rate limited. Retry after 4s. This is transient —
       retry the same call; do not change your approach.
```

The transient/terminal flag is the part teams skip. Without it you get both wasteful retry loops on
permanent failures and premature strategy changes on transient ones.

A framework that turns a 404 into an unhandled exception has removed the agent's ability to recover.

## Token-efficient returns

**A tool's return is a prompt fragment, and you pay for every token of it on every subsequent turn.**
A 5,000-token return on turn 2 of a 30-turn run costs 5,000 tokens *twenty-eight more times* unless
compacted away.

- Return a **summary plus a handle**: `{"rows": 1284, "columns": [...], "sample": [...3 rows], "result_id": "res_91f"}` plus a `fetch_result(result_id, offset, limit)` tool.
- Support **projection** so the model can ask for the three fields it needs.
- **Hard-cap output and announce it**: `[truncated: showing 200 of 4,812 lines. Use offset= to page.]`. Silent truncation poisons context.
- Strip nulls, boilerplate metadata, HTML chrome, base64 blobs by default.
- Return machine-actionable structure, not prose. No "I successfully found 3 orders for you!"

## Sizing and the confusion threshold

> Claude's ability to pick the right tool degrades once you exceed **30–50 available tools**
> ([Anthropic tool search docs](https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool)).

And definitions cost context before any work happens: a five-server MCP setup (GitHub, Slack,
Sentry, Grafana, Splunk) is **~55,000 tokens** of tool definitions; dozens of servers reach
~150,000.

Two distinct problems needing two distinct fixes — trimming one relocates the problem to the other:

| Problem | Layer | Fix |
|---|---|---|
| Too many *definitions* eating context and degrading selection | Schema | Deferred loading + tool search |
| Too many *results* and round trips eating context | Execution | Code-execution-as-tool-calling |

**Try curation first.** Does this agent need 200 tools, or 12 and a clear role? Role-scoped
allowlists per agent are cheaper and more predictable than any dynamic mechanism. For a generated
multi-agent stack, per-agent allowlists are the default, not an optimization.

### Escalation ladder

```
< 10 tools, all used most requests, small definitions
    → plain tool calling. The machinery costs more than it saves.

10+ tools, large definition surface, each request touches a few
    → deferred loading (defer_loading: true) + a tool search tool.
      Reported >85% reduction in definition tokens; search tool costs ~500 tokens.
      Keep the 3–5 most-used tools NON-deferred. Never defer the search tool itself.

Large surface AND fan-out / filtering / chaining / big intermediates
    → add code execution on top. This is where 78–99% input-token reduction lives.

Wiring to a wall of MCP servers
    → assume you want both.
```

**Honest costs of code execution**, which the token headlines bury: output tokens roughly double,
latency rose ~7% in a controlled test, and you now operate a code sandbox with resource limits,
egress control, and a real security boundary. Debuggability changes shape — failures move inside
model-written code. Net token win is still large (77.4% total in that test) because input dominates.

**Sharp limitation:** tools provided through an MCP *connector* cannot be called programmatically in
Anthropic's implementation. For those, deferred loading is the only lever unless you run your own
sandbox.

## MCP posture

MCP is the right **export** surface — a promoted function should be able to appear as an MCP tool.
It should not be the **internal** calling convention: connector tools block code mode, the trust
model forces boundary re-validation anyway, and the wire format already broke compatibility once
(the `2026-07-28` stateless revision).

Treat every MCP server as untrusted input. The spec places tool descriptions **outside its trust
boundary** and defines no mechanism to attest a server or detect description drift. Concretely: pin
and hash tool schemas at onboarding and alert on drift, scope credentials per server with
short-lived tokens, log every invocation. Note that MCPSecBench found *larger* models show **higher**
poisoning success rates — you cannot fine-tune your way out of this.

## Applying this to synthesized tools

When emitting tools from a target codebase:

1. **Suppress before you expose.** A discovered function is a candidate, not a tool. The 30–50
   threshold is a hard budget per generated agent.
2. **Exception classes become the error taxonomy.** Map each to a message that follows the
   transient/terminal rule above, mechanically.
3. **Return types become the truncation contract.** A function returning a collection needs a
   summary+handle wrapper generated with it, not after complaints.
4. **`read_only` is derivable and must be first-class metadata**, not a comment. It is the highest-
   leverage safety property extractable at promotion time and it is nearly free — the signature and
   body already tell you.
