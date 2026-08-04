---
name: codebase-decomposition
description: "v2 SCOPE — decomposition-into-agents left v1 under plan.md OD-09; v1 is one agent, by decision. This skill is correct about v2 and describes nothing v1 builds. Decides where one generated agent ends and the next begins when decomposing an arbitrary target codebase. Use when planning or reviewing v2 decomposition work: proposing agent boundaries from static analysis, clustering a repo into layers or domains, mapping a codegraph symbol graph onto an agent set, or reviewing a design that proposes a UI agent plus an API agent plus a data agent."
---

# Codebase decomposition

> ## Standing: **v2. Deferred *undecided* — which is different from deferred-because-refuted.**
>
> **`plan.md` OD-09 (2026-08-02) removed decomposition-into-agents from v1.** v1 ships one agent
> **by scope decision, not by evidence**: the arm that would have settled it (P-04 / `11` Phase 3,
> A4 vs. A3 vs. A5) needed a generator, no generator was built, and Phase 3 never ran. `14` records
> this as **D-11 — resolved by scope, unmeasured** and **D-21**.
>
> **Nothing below was refuted and nothing below was confirmed.** The rule that layers are the wrong
> axis and bounded contexts the right one is an argument; the reliability ordering over static signals
> was never validated against a labelled set; the forcing functions were never exercised because there
> was never a second agent to escalate to. **Keep all of it.** When v2 reopens this, the one thing that
> has changed is the starting point: it now starts from a working single-agent runtime, so the forcing
> functions can be observed rather than predicted — which is closer to what §3.1.4 asked for than
> anything the original plan would have delivered.

Sources: `research/07-product-vision.md` §3.1 (the hard problem), `research/06-examples-inventory.md` §1
(what `codegraph` actually provides); standing per `research/14-architecture-synthesis.md` D-11, D-21.
~~This is the crux capability of the product~~ **— it was, and OD-09 is the measure of how far that
moved: the capability the vision called its crux is entirely out of v1, and the one the vision left
unnamed (contract derivation) shipped in its place** — and **the place it is most likely to fail
quietly** — by producing a decomposition that looks plausible in a diagram and performs badly in
practice.

## The one rule that overrides everything

**Default to one agent. Escalate only on a declared forcing function.** Boundary inference is the
least-validated capability in the system; ship it as an advisory *report* with rationale and
confidence, while the runtime defaults to a single agent (`07 §3.1.4`). That is how you collect ground
truth on whether your inference is any good before betting the runtime on it.

If you cannot name which forcing function below justifies the second agent, there is no second agent.

## Layer decomposition is the wrong axis

The intuitive split — UI agent, API agent, data agent — mirrors how the *code* is organized, not what
a *user wants done*. Every user request crosses all three layers, so:

- A "data access agent" cannot complete any user-facing task alone. It can only serve an API agent,
  which can only serve a UI agent.
- You have built **a call stack out of language models**: 3× the tokens, three chances to garble the
  intent, and no agent that owns an outcome.
- Anthropic's numbers: ~4× tokens for a single agentic loop, **~15× for multi-agent** ([Anthropic](https://www.anthropic.com/engineering/multi-agent-research-system)),
  with token spend alone explaining ~80% of performance variance on BrowseComp.
  **Paying 15× to reproduce a function call is a bad trade** ([same source](https://www.anthropic.com/engineering/multi-agent-research-system)).

Vertical slices — bounded contexts like Orders, Billing, Identity, Inventory — are the right axis.
Each owns a coherent operation set, a coherent data scope, and can finish a request end to end.

**The trap:** in a clean layered monolith the layer signal is *strong* and the domain signal is
*weak*. The wrong axis is the legible one. Legibility is not correctness.

## But bounded contexts are not statically recoverable

Domain boundaries live in the heads of the people who wrote the system. Rank your evidence honestly
(`07 §3.1.2`, descending reliability):

| Signal | Reliability | Catch |
|---|---|---|
| Developer-declared boundaries (config file) | Highest | Requires developer work; defeats "point it at a repo" |
| Deployment topology (services, containers, separate DBs) | High | Free on microservices; absent on monoliths |
| Route/module namespacing (`/api/orders/*`, `app/billing/`) | Medium-high | Conventional, common, cheap to extract |
| `CODEOWNERS`, package boundaries, OpenAPI tags | Medium | Encodes team structure ≈ domain (Conway) |
| Community detection on the import/call graph | Low-medium | Produces *plausible* clusters, not *correct* ones. A hint, never a decision |
| LLM reading code and proposing domains | Unknown, unverifiable | Confident, fluent, untestable. Requires a review gate |

Never emit a boundary whose only support is a row from the bottom two.

## What codegraph gives you, and what it does not

`codegraph` is the right substrate and it is MIT, local-first, 39 languages, with an incremental
sync path and a queryable SQLite artifact. **But its graph is symbol-level and it has zero concept
of** (`06 §1`):

- architectural layer (UI / API / service / data-access / jobs)
- domain or bounded context
- module clustering or community detection
- package- or service-level aggregate nodes (`module` is a *language* module, e.g. a Python module)
- any graph-partitioning algorithm at all

So boundary inference is **net-new work you must build**, not a flag you configure. Two false
friends to not waste time on: `src/mcp/dynamic-boundaries.ts` detects *dynamic-dispatch* breaks in
the static call graph (useful, but not decomposition), and `src/directory.ts` is `.codegraph/`
directory management, not directory-structure analysis.

## The recommended pipeline

```
1. Directory structure       from nodes.file_path — the single strongest layer signal in practice
2. File-level import DAG     getFileDependencies / getFileDependents, then cluster
                             (Louvain, label propagation, or SCC + topological layer assignment)
3. Framework signals         getDetectedFrameworks, route nodes, decorators — classify each
                             cluster as UI / API / data / jobs
4. Anchor the layering       entrypoints (route nodes, main, CLI commands) and sinks (ORM/driver calls)
5. LLM adjudication          over cluster summaries only, using buildContext output as evidence
```

Step 5 is last and is *adjudication*, not discovery. An LLM asked to invent domains from raw source
returns fluent, confident, untestable answers. An LLM asked to name and merge already-computed
clusters is checkable against the clustering.

Useful primitives that already exist: `getRoutingManifest(limit)` (route→handler),
`findCircularDependencies()`, `getImpactRadius(nodeId, maxDepth)`, `findDeadCode()`,
`getSegmentMatches(words, limit)`.

## Forcing functions — the only reasons to emit more than one agent

From `07 §3.1.4`:

1. Promoted tool count for one agent exceeds the selection budget even after progressive disclosure
   (degradation past ~30–50 tools).
2. **Two tool groups sit on different trust boundaries** — read vs. destructive, PII vs. non-PII,
   analysis-time vs. runtime.
3. Two tool groups have genuinely different isolation, latency, or availability requirements.
4. The developer declared the boundary explicitly.

**(2) is the only *safety* reason and therefore the only non-negotiable one.** (1) and (3) are budget
arguments — try curation and per-agent allowlists first (see `agent-tool-design`). "The architecture
diagram looks cleaner" is not on this list.

## Codebase shape → what to actually do

| Shape | What happens | Do this |
|---|---|---|
| Clean layered monolith | Worst case: strong layer signal, weak domain signal | Prefer route-prefix clustering over directory layers; flag low confidence |
| Microservices | Boundaries free from deployment | One agent per service — then ask whether you need agents at all |
| Monorepo | Package graph is a good prior, but packages ≠ domains | Filter to packages with entrypoints; ignore leaf libraries |
| Big ball of mud | Clustering returns one giant component or noise | **Do not guess.** One agent, curated tools, surface the mess in the report |
| Framework scaffolding (Rails, Django admin) | Hundreds of near-identical CRUD endpoints | Collapse to parameterized tools; never promote per-model |
| Polyglot (TS front + Go API + Python jobs) | Language boundary ≈ deployment boundary, usually | Use it, but verify against the route table |

## Every emitted boundary carries these fields

A boundary without them is not reviewable and must not ship:

```
- [ ] name                  a domain noun a user would recognize, not "layer 2"
- [ ] rationale             which signal(s) from the reliability table produced it
- [ ] confidence            explicit, and low when the only evidence is clustering or an LLM
- [ ] owned tools           the promoted tool set, within the ~30–50 budget
- [ ] owned data scope      which models/tables/routes it may touch
- [ ] trust boundary class  read-only vs. write vs. destructive; PII vs. not
- [ ] can it complete a user request end to end?   If no, it is a layer, not a boundary — merge it
```

That last question is the cheapest test in this document. Apply it before anything else.

## Do / don't

```
DON'T  emit UI-agent / API-agent / data-agent because the repo has those directories
DON'T  treat Louvain output as ground truth — it is a hint with a confidence score
DON'T  let an LLM invent domain names from raw source with no clustering to check against
DON'T  emit one agent per discovered service on a microservice repo without asking if one suffices
DON'T  promote per-model tools for generated CRUD scaffolding

DO     ship the decomposition as a report first; run the runtime on one agent
DO     use is_exported and the route manifest to find the acting surface, then cluster it
DO     record the forcing function next to every boundary that splits
DO     flag low confidence loudly on layered monoliths and balls of mud
DO     merge any proposed agent that cannot own an outcome
```

## Related skills

`multi-agent-topology-review` for the cost case against splitting, `tool-synthesis-from-code` for
what each boundary's tool set should contain, `agent-tool-design` for the ~30–50 budget that drives
forcing function (1).
