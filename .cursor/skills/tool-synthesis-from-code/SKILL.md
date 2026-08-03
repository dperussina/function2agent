---
name: tool-synthesis-from-code
description: "v2 SCOPE — tool synthesis left v1 under plan.md OD-09; this skill is correct about v2 and does not describe anything v1 builds. Turns analyzed source code into a curated set of LLM-usable tools instead of a mechanical function-to-tool dump. Use when planning or reviewing v2 synthesis work: deciding which discovered functions or endpoints deserve promotion, mapping routes or OpenAPI specs to tools, sizing the tool set, or reviewing any design that emits one tool per function or per endpoint. For v1 effect classification, use agent-safety-and-sandboxing instead — the differentiator deferred, the Principle IV obligation did not."
---

# Tool synthesis from code

> ## Standing: **v2. Deferred, not retired, and not wrong.**
>
> **`plan.md` OD-09 (2026-08-02) removed tool synthesis, promotion selection and generation-time
> effect classification from v1.** A criterion pre-registered in `11-validation-plan.md` §7 fired: a
> baseline agent with a shell, a socket and the app's published spec matched ~20 hand-written ideal
> tools — within 3.7 points on lookups, **ahead** by 10 on joins and 50 on per-record. v1 is a
> spec-aware runtime, a contract-derived verifier and drift detection.
>
> **Everything below remains correct about v2 and is worth keeping intact**, because synthesis
> survives as a *measured* opportunity rather than a hunch: it was **~~2.8×–9.3×~~ ~~2.2×–9.3×~~ 2.20×–4.366× within session cheaper wherever it
> succeeded** *(lower bound corrected 2026-08-03 — the join ratio is **2.20×**, not 2.8×; the 2.8×
> divided a post-fix cost total by a pre-fix solved count. The lower bound has now been wrong in two
> successive directions, 3× → 2.8× → 2.2×. Quote 2.2× as a **bound**, not a rate: removing one task
> of ten, `R4.001`, moves the join ratio to 4.20×, and that task consumes 94% of the raised OD-04
> budget cap. See [finding 009](../../../specs/001-discovery-validation/findings/009-ceiling-test.md)
> Limb 1.)*. Two things travel with that number and must be quoted alongside it. **The liability:**
> outside its surface, the tool arm burned its entire budget and returned nothing, against a shell arm
> that exhausted nothing in 31 scored attempts (OD-07, C-15). **The shape constraint, which is the one
> licensed empirical finding here:** a 20-tool surface returning **records** lost a whole task family
> to a `jq` pipeline, while a single tool returning an **answer** moved a task by 35× (D-19). So the
> open v2 question is not *how few tools* — this skill's framing — but **how far up the abstraction
> each one sits.** Read §"Consolidation" below with that in mind; it is the part the evidence supports
> most directly and the part the rest of the skill subordinates to counting.
>
> **One section does not defer: effect classification.** Constitution Principle IV binds every emitted
> tool, and v1 emits a shell and an HTTP client that can issue `DELETE`. v1 classifies **per call at a
> runtime interception point that can block**, which is `agent-safety-and-sandboxing` → *Effect tiers
> and the interception point* (D-22, C-16). The *static, per-tool, generation-time* version below is
> v2.

Sources: `research/07-product-vision.md` §3.2, `research/09-mcp-as-tool-surface.md` §5.3 and §4.3,
`research/01-agent-anatomy.md` §5; standing per `research/14-architecture-synthesis.md` D-19, D-21,
D-22. ~~Tool quality *is* product quality here, so this is the highest-stakes generation step in the
system.~~ **Was true; v1 has no generation step. It is the highest-stakes step in v2.**

## The anti-pattern this skill exists to prevent

**Mechanical 1:1 function→tool (or endpoint→tool) conversion is a documented, published anti-pattern.**
Jeremiah Lowin, author of FastMCP — which he estimates powers **~70% of MCP servers across all
languages** — wrote [*Stop Converting Your REST APIs to MCP*](https://jlowin.dev/blog/stop-converting-rest-apis-to-mcp):

> "An API built for a human will poison your AI agent… LLMs achieve significantly better performance
> with well-designed, tailored MCP servers than with auto-converted ones."

Auto-converted servers "technically work but fail in practice." FastMCP's own OpenAPI integration docs
now carry this warning inline. Two mechanisms (`09 §5.3`, `01 §5.2`):

1. **Context pollution** — every tool's schema is reprocessed on every reasoning turn.
2. **Atomicity as an agent anti-pattern** — each call is a full reasoning cycle, so forcing the model
   to chain atomic calls is slow, error-prone, and burns tokens.

**The people who built the auto-generation tooling are publicly telling people to stop using it that
way.** A generator that emits one tool per discovered function ships a known-bad artifact at machine
scale. The differentiator is not conversion; it is **curation and consolidation**.

## The counting problem is the whole problem

| Quantity | Typical mid-sized web app |
|---|---|
| Functions | 5,000–50,000 |
| HTTP endpoints | 100–500 |
| Tools before selection accuracy degrades | ~30–50 (`01 §5.2`) |

So the promotion function must be **aggressively lossy by design**. The target is not "expose the
application," it is "expose the smallest tool set that spans what users actually ask for."

> **A 300-endpoint app should yield roughly 20–25 tools plus a search/dispatch tool — a ~15:1
> reduction.** A generator that emits 300 tools has not solved the problem; it has moved the problem
> into the model's context and made it worse.

Both escape valves from `01 §5` are day-one design inputs, not v2 optimizations: deferred/searchable
tool loading (trims *definitions*) and code-execution-as-tool-calling (trims *results* and round
trips, reported 78–99% input-token reductions).

## Synthesize at the trust boundary, not the function boundary

This is the insight that reframes the whole capability (`07 §3.2.4`). **An application function is
not an API.** A function inside a web app expects to run inside a request context: an authenticated
principal, an open DB session or transaction, a tenant scope, feature flags, rate limits, audit
logging. Every one of those is supplied by middleware the function never sees.

Invoking that function **in-process** as a "tool" bypasses all of it. You get a callable that works in
the happy path and **silently violates authorization in every other path**.

> Where the application already exposes an external boundary — an HTTP route, a GraphQL resolver, an
> RPC method, a CLI command — that boundary is where authorization, validation, and audit already
> live. **Generate tools that call it, not tools that reach behind it.**

Consequence for scope: for web applications, derive the tool surface from **routes and handlers**, not
from arbitrary functions. This makes the problem smaller, safer, and far more tractable.

## Promotion gate

A discovered function is a *candidate*, not a tool. A candidate must clear **all** of these
(`07 §3.2.2`):

```
- [ ] Reachable from an external entrypoint (HTTP route, CLI command, job handler,
      GraphQL resolver, exported public API) — not an internal helper
- [ ] Signature stable and typed enough to produce a parameter schema without guessing
- [ ] Corresponds to something a USER would name ("refund an order", not _normalizeAddressLine2)
- [ ] Effect class determinable — or defaulted to the most dangerous class and gated
- [ ] Not a thin wrapper, re-export, or framework-generated duplicate of another candidate
```

**Cheap, strong negative signal:** if no test, no docstring, and no call site outside its own module
reference it, it is almost certainly not a user-facing capability. Suppress it.

## Consolidation: outcome-named tools

Do what the blog posts say humans should do by hand (`09 §5.3`). Consolidate call-graph clusters into
one outcome-named tool. Posta's canonical example:

```
DON'T expose:  check_inventory, reserve_inventory, get_packaging, find_shipper,
               verify_address, request_shipping, get_tracking

DO expose:     fulfill_order(order_id) -> "Order #12345 shipped via carrier X, tracking ABC123."
```

The multi-step orchestration belongs **in the tool, not in the model**. And note the structural
advantage: the same static analysis that finds architectural clusters is the analysis that finds these
consolidation candidates. A spec-based OpenAPI converter sees only endpoints and cannot do this.

Also exclude aggressively: pagination plumbing, internal helpers, read-your-own-writes endpoints,
health checks, per-model CRUD from generated scaffolding (collapse to one parameterized tool).

## Effects metadata is mandatory and is not optional decoration

> **The only section of this skill that is live in v1 — but not in the form written here.** The
> *mandate* is constitutional (Principle IV) and does not defer with synthesis; the *mechanism* below
> — a static class derived at generation time and stored on a tool manifest — has no v1 object,
> because v1 emits a shell and an HTTP client rather than a manifest. **v1 resolves the tier per call
> at a runtime interception point that can block**: `agent-safety-and-sandboxing` → *Effect tiers and
> the interception point* (D-22, C-16).
>
> **Read the three non-negotiable rules below as v1 rules with a v2 mechanism.** Rule 1 becomes a
> per-call default rather than a per-tool opt-in; rules 2 and 3 are already runtime rules and carry
> over verbatim. **The default-deny sentence is the most portable line in this section** — it is what
> makes a crude verb-based proxy safe enough to ship.

Every emitted tool carries an effect class, derived statically where possible (HTTP verb; SQL verb;
ORM method; known-destructive API calls; presence of a transaction decorator) and **defaulted to the
most dangerous class when undeterminable**. Default-deny for unclassifiable candidates.

```
read_only: bool          drives parallelization safety
egress: [string]         drives compile-time lethal-trifecta detection
idempotent: bool
destructive: bool
auth_scope: string
```

Three non-negotiable rules (`07 §3.2.5`):

1. **Read-only by default.** Write tools require explicit per-tool, per-environment opt-in at review.
2. **Destructive operations require out-of-band confirmation — and the confirmation must not be a
   tool the model can call.** It is a runtime interrupt enforced by topology (see
   `graph-vs-loop-decision`).
3. **Multi-step operations that must not partially apply need compensation, which means they need a
   graph.** This is exactly the declared constraint that justifies emitting topology.

**Keep this metadata in a typed internal IR, because MCP schemas have nowhere to put it.** JSON Schema
has no slot for `read_only` or `egress` and MCP defines no convention for them; you could smuggle them
through `_meta` but no client would enforce them (`09 §4.3`, §8.2). If MCP were the canonical
representation, the differentiating safety property would be unrepresentable. See `mcp-export-design`.

## Descriptions are the failure point

Evidence sources for a generated description, ascending in value (`07 §3.2.3`):

| Source | Value |
|---|---|
| Function name | Weak — often lies |
| Signature / types | Structural, reliable, incomplete |
| Docstring | Helpful when present, stale when not |
| **Tests** | **Best** — demonstrate intent, valid inputs, and error conditions simultaneously |

Write for a reader who has never seen the codebase; identifier names alone are semantically thin.
Tool descriptions live in the harness, not the model, so description quality is directly measurable
and must be **evaluated, not assumed**. Measure first-try tool-selection accuracy against the smallest
catalog that covers the job.

## Generation inverts the trust direction

The literature treats an MCP server as untrusted input to *your* agent. When you **emit** the server,
the customer's users become clients of a surface you generated but nobody reviewed (`09 §7`). A
mis-derived tool that exposes an internal admin path is a vulnerability shipped at machine scale
across every customer. The mitigation is the same static analysis that generated it: derive
`read_only` and `egress` per tool, refuse to expose anything failing policy, require confirmation for
destructive tools.

## Do / don't

```
DON'T  emit one tool per function, per endpoint, or per ORM model
DON'T  call an application function in-process and call the result a tool
DON'T  promote a candidate whose effect class you could not determine — gate or drop it
DON'T  trust the function name as the description source
DON'T  ship a tool set over ~30–50 for one agent without deferred loading
DON'T  leave read_only/egress as a comment or a naming convention

DO     derive the surface from routes/handlers/resolvers/CLI commands
DO     consolidate call-graph clusters into one outcome-named tool
DO     use tests as the primary description evidence
DO     collapse framework-generated CRUD to parameterized tools
DO     default-deny unclassifiable candidates
DO     report the suppression ratio (candidates considered vs. tools emitted) as a quality metric
```

## Related skills

`agent-tool-design` for per-tool quality rules (naming, error messages, token-efficient returns,
the 30–50 threshold). `codebase-decomposition` for which agent owns which tool set.
`mcp-export-design` for shipping these as an MCP server. `graph-vs-loop-decision` for confirmation
gates and compensating actions.
