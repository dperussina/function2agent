# 06 — Vendored Examples Inventory & Fit Assessment

**Last researched: 2026-08-02**

## TL;DR

> | Repo | Version (vendored) | License | Verdict |
> |---|---|---|---|
> | **codegraph** | `v1.5.0-7-g49c11fc` (2026-08-01) | MIT | **Adopt as analysis foundation** — with a mandatory "architecture inference" layer built on top. |
> | **spec-kit** | `v0.1.10-1117-gd1e86f6` (2026-07-31) | MIT | **Adopt as process** — it is prompt templates + a CLI bootstrapper, not a library. Low cost, real value. |
> | **adk-python** | see §3 (verify locally) | Apache-2.0 | **Adopt partially** — best orchestration/serving story; graph + runtime agent construction. |
> | **claude-agent-sdk-python** | see §4 | MIT | **Adopt partially** — best coding-tool suite + sandbox/permissions; weak multi-agent graph. |
> | **claude-code** | see §4 | (see §4) | **Reference only** — distribution/tooling shape, `.claude/` extensibility model. |
> | **claude-cookbooks** | n/a | MIT | **Reference only** — patterns, no reusable machinery. |
>
> **Headline finding on `codegraph`:** it is a genuinely strong, MIT-licensed, tree-sitter-based, 29-language symbol graph with framework-aware **route→handler** extraction, an incremental sync path, a SQLite store, and a first-class programmatic API. It scales (claimed: Linux kernel, 70k files / 2M symbols / 6.4M edges, <12 min on a 2-core VPS). **But it has no concept of architectural layers, domains, modules, or bounded contexts.** Its graph is symbol-level. Deriving agent boundaries from it is a *build*, not a *configure* — though it is the right substrate for that build.
>
> **Headline finding on the harness question:** neither ADK nor the Claude Agent SDK gives you the product. ADK wins on orchestration, graph/workflow semantics, session/state durability, and HTTP/SSE serving. Claude Agent SDK wins on the coding-tool surface (which the vision explicitly demands "equivalent to Claude Code's") and on permission/sandbox hooks. ~~The pragmatic answer is **both**: ADK as the outer graph-loop runtime and serving layer; Claude Agent SDK (or a reimplementation of its tool suite) as the per-node coding executor.~~ **Superseded for v1 2026-08-03 — `specs/001-discovery-validation/plan.md` OD-15: the answer is *neither*, and the first clause of this headline is the one that survived. v1 runs on no agent framework; the Claude Agent SDK stays an opt-in second executor. See §7's Recommendation for the three grounds and for the nine capabilities that moved to build as a result.**

---

## How to read this document

This is a *fit assessment*, not a tutorial. For each repo: what it actually is, what its extension points are, and whether it moves the product forward. Repos 3–6 are surveyed narrowly — a sibling document (`02-agent-harnesses.md`) covers ADK and the Claude Agent SDK from public sources. Here we only ask what the **vendored source** reveals about fit.

All paths are relative to `/Users/djperussina/Code/function2agent/examples/`.

---

## 1. `codegraph` — HIGH PRIORITY

### What it is

A local-first **code knowledge graph** for AI coding agents. It parses a whole repository with tree-sitter, extracts symbols and relationships into a SQLite database at `.codegraph/`, and exposes that graph via a CLI, an MCP server (stdio, daemon-backed), and a programmatic TypeScript API. Its stated purpose is context precision for agents — "surgical context, fewer tool calls" — not architecture visualization.

- **Package:** `@colbymchenry/codegraph`
- **Version:** `1.5.0` (`package.json`); git describe `v1.5.0-7-g49c11fc`, HEAD `49c11fc2` dated 2026-08-01
- **License:** MIT (`examples/codegraph/LICENSE`, "Copyright (c) 2026 Colby Mchenry")
- **Language:** TypeScript (Node ≥20 <25) with an optional **Rust native kernel** (`codegraph-kernel/`)
- **Repo size:** ~155 MB vendored; `src/index.ts` alone is 73 KB, `src/mcp/tools.ts` is 4,947 lines. This is a serious, actively-developed codebase (CHANGELOG.md is 248 KB), not a weekend project.
- **Maturity:** high for what it does. 164 test directories under `__tests__/`, an evaluation harness (`__tests__/evaluation/runner.ts`), telemetry infrastructure, an installer, and a self-hosted telemetry dashboard. Single-maintainer risk is real; adoption risk is mitigated by MIT + the fact that the valuable artifact (the SQLite graph) is trivially readable without the library.

### Architecture

```
source files
   │  tree-sitter (WASM via web-tree-sitter, or native Rust kernel)
   ▼
extraction/            per-language extractors (29 files in src/extraction/languages/)
   │                   + non-tree-sitter extractors: vue, svelte, astro, razor,
   │                     liquid, cfml, dfm, mybatis
   ▼
resolution/            two-phase: extraction emits `unresolved_refs`, a later
   │                   pass resolves names → edges. Framework resolvers
   │                   (25 files in src/resolution/frameworks/) add semantic
   │                   edges (route→handler, DI, bridges).
   ▼
db/  SQLite (node:sqlite, WAL)   nodes / edges / files / unresolved_refs
   │                              + nodes_fts (FTS5) + name_segment_vocab
   ▼
graph/ traversal + queries  ──► CLI  |  MCP daemon  |  library API
```

**Parsing.** tree-sitter, delivered two ways: WASM grammars (`tree-sitter-wasms`, `web-tree-sitter` in `package.json` deps, `.wasm` files copied into `dist/extraction/wasm` by the `copy-assets` build step) and a native Rust kernel with vendored C grammars for dart/kotlin/lua/scala (`codegraph-kernel/grammars/`). The kernel path uses a flat-buffer wire protocol (`ExtractionResult.kernelBuffers` in `src/types.ts:288`) so the main JS thread never materializes per-node objects during bulk indexing — a real engineering investment in throughput.

**No LSP, no compiler front-ends, no embeddings.** Resolution is name-based with heuristics (`src/resolution/name-matcher.ts`, `import-resolver.ts`, `path-aliases.ts`, `workspace-packages.ts`). Search is FTS5 BM25 + fuzzy + identifier-segment matching (`src/search/identifier-segments.ts`), not vector search. There is **no embedding table in the schema** and no vector dependency. Confirmed by reading `src/db/schema.sql` in full.

### Graph schema — the important part

From `src/types.ts:22-71` (these arrays are the wire contract with the Rust kernel; order is load-bearing):

**Node kinds (22):**
`file`, `module`, `class`, `struct`, `interface`, `trait`, `protocol`, `function`, `method`, `property`, `field`, `variable`, `constant`, `enum`, `enum_member`, `type_alias`, `namespace`, `parameter`, `import`, `export`, **`route`**, **`component`**

**Edge kinds (12):**
`contains`, `calls`, `imports`, `exports`, `extends`, `implements`, `references`, `type_of`, `returns`, `instantiates`, `overrides`, `decorates`

**Node columns** (`src/db/schema.sql:20-42`) carry more than location: `docstring`, `signature`, `visibility`, `is_exported`, `is_async`, `is_static`, `is_abstract`, `decorators` (JSON array), `type_parameters`, `return_type`.

Two things stand out for this product:

1. **`route` is a first-class node kind, and there is a route→handler query.** `QueryBuilder.getRoutingManifest()` (`src/db/queries.ts:978-1000`) joins `nodes r WHERE r.kind='route'` to handler nodes over `references`/`calls` edges, returning `{url, handler, handlerFile, handlerLine, handlerKind}`. The comment there is explicit: *"Edge kind varies across framework resolvers: Spring/Rails/Laravel/Drupal emit `references`, Express emits `calls`."* This is exactly the raw material for **deriving app-functionality tools from HTTP surface**.

2. **`decorators` are captured.** Annotation-driven frameworks (Spring `@RestController`, NestJS `@Controller`, FastAPI decorators, .NET attributes) leave their markers in the graph, which is a second independent signal for classifying a symbol's architectural role.

### Framework awareness

`src/resolution/frameworks/index.ts` registers 30 resolvers across: Laravel, Drupal, Express, NestJS, React, Svelte, Vue, Astro, Django, Flask, FastAPI, Rails, Spring, Play, Go (net/http + Gin), GoFrame, Rust, ASP.NET, SwiftUI, UIKit, Vapor, Swift↔ObjC bridge, React Native bridge, Expo modules, Fabric views, CICS, Terraform.

Each resolver has a `detect(context)` gate. Express's (`src/resolution/frameworks/express.ts:56-80`) reads `package.json` deps and falls back to filename/content heuristics (`routes`, `controllers`, `middleware` in the path). Resolvers also maintain reserved-call denylists (`RESERVED_CALLS`, line 39) so framework noise (`res.json`, `res.status`) doesn't pollute the business-flow graph.

**This matters more than the raw graph.** Framework detection is already the closest thing codegraph has to architectural awareness — it knows "this repo is a Django app" and "this symbol is an HTTP handler."

### Languages

39 language identifiers in `LANGUAGES` (`src/types.ts:77-120`), including the long tail that most tools skip: `cobol`, `vbnet`, `pascal`, `cfml`/`cfscript`/`cfquery`, `erlang`, `solidity`, `luau`, `arkts`, `terraform`, `nix`. 29 dedicated extractors in `src/extraction/languages/`, plus 8 template/component extractors at `src/extraction/*-extractor.ts` (vue, svelte, astro, razor, liquid, cfml, dfm, mybatis).

The vision says "any codebase, any language." codegraph gets you closer to that than anything else in this inventory, and degrades gracefully — `unknown` is a valid language value.

### Scale and incrementality

- **Claimed scale** (`README.md:261`): Linux kernel — 70k files, 2M symbols, 6.4M relationships — indexed to completion in **under 12 minutes on a 2-core / 6 GB VPS**. Pipeline is explicitly streaming/disk-first rather than RAM-first, and worker pools are sized from cgroup-aware core counts and measured available RAM (`README.md:258`).
- **Incremental:** yes. `codegraph sync` does content-hash-based incremental update (`files.content_hash`). `CodeGraph.watch()` uses native OS file events with a 2-second debounce (`README.md:495`), and `indexFiles(filePaths)` re-indexes a specific set. `getChangedFiles()` returns `{added, modified, removed}`.
- **Unresolved-ref retry:** the `unresolved_refs` table has a `failed` status with a `name_tail` index so a later sync can retry a reference when a newly-added symbol could satisfy it (`schema.sql:70-92`). Careful design; suggests the incremental path is real, not aspirational.
- **Concurrency:** worker pools for parse (`parse-pool.ts`, `parse-worker.ts`), store (`store-worker.ts`), resolution (`resolver-pool.ts`, `resolver-worker.ts`), and MCP query (`query-pool.ts`, `query-worker.ts`). Plus a WAL valve (`db/wal-valve.ts`) and memory budget (`resolution/memory-budget.ts`).

### Extension points

| Surface | Detail |
|---|---|
| **Library API** | `import CodeGraph from '@colbymchenry/codegraph'`; `CodeGraph.init(path)` / `.open(path)`. ~70 public methods on the class (`src/index.ts`). Also exports `DatabaseConnection`, `QueryBuilder`, `getDatabasePath`, `initGrammars`, `loadGrammarsForLanguages`, `FileLock` (`README.md:596-598`). Requires **Node 22.5+** when embedded (uses built-in `node:sqlite`). |
| **The SQLite file itself** | `.codegraph/*.db`. Four tables, documented schema, stable IDs. **You can query it from Python, Go, anything.** This is the most important extension point for a polyglot product — you are not locked to the TS API. |
| **CLI + `--json`** | `index`, `sync`, `status`, `query`, `explore`, `node`, `files`, `callers`, `callees`, `impact`, `affected`, `daemon`, `serve`. Most carry `-j, --json` (`src/bin/codegraph.ts:909,1112,1472,1852,1931,2009,2115`). Scriptable from any language. |
| **MCP server** | 8 tools: `codegraph_search`, `codegraph_callers`, `codegraph_callees`, `codegraph_impact`, `codegraph_node`, `codegraph_explore`, `codegraph_status`, `codegraph_files` (`src/mcp/tools.ts:549-724`). Daemon-backed with a liveness watchdog; supports `projectPath` per call so one server can serve a monorepo of independently-indexed subprojects (`README.md:458`). |
| **Framework resolvers** | `FrameworkResolver` interface with `{name, languages, detect, ...}` and a central registry array (`src/resolution/frameworks/index.ts:35`). Adding a resolver for a framework the target codebase uses is a contained change. **This is where you would add "emit a `route` node for gRPC services / GraphQL resolvers / Convex functions / Celery tasks."** |
| **Env config** | `CODEGRAPH_DIR` override for the data directory (`src/directory.ts:36`). Custom file-extension mapping via an optional config file. |

### Notable relevant query primitives

Already implemented, and directly useful for boundary inference:

- `getFileDependencies(path)` / `getFileDependents(path)` — file-level import DAG
- `findCircularDependencies()` — returns cycles (`string[][]`)
- `getImpactRadius(nodeId, maxDepth)` — blast radius subgraph
- `findPath(...)` — path between two symbols
- `findDeadCode(kinds?)` — unreferenced symbols
- `getNodeMetrics(nodeId)` — per-symbol metrics
- `getTypeHierarchy(nodeId)`, `getCallGraph(nodeId, depth)`, `getCallers/getCallees`
- `getDetectedFrameworks(): string[]`
- `getRoutingManifest(limit)` — **route→handler manifest**
- `buildContext(task, opts)` — LLM-ready markdown/JSON context bundle
- `getSegmentMatches(words, limit)` — prose word → symbol name matching (`src/index.ts:1322`), backed by `name_segment_vocab`

### The critical question: can it mechanically derive agent boundaries and tool inventories?

**Partially, and only for tool inventories. Not for agent boundaries. Here is the honest split:**

**Tool inventories — mostly yes, with work.** The route→handler manifest is a near-direct mapping to "call this endpoint" tools. `signature`, `return_type`, `type_parameters`, `decorators`, and `docstring` on every node give you enough to synthesize a JSON-Schema tool definition for an exported function. `is_exported` filters the public surface. You would still need to:
- resolve parameter *types* into schemas — codegraph stores a `signature` **string**, not a structured parameter list. There is no `parameters` table; `parameter` is a node kind, and parameters attach via `contains`/`type_of` edges, but reconstructing a typed schema from `type_of` edges plus a signature string is inference work, and unreliable in dynamically-typed languages.
- decide which functions are *domain operations* versus internal helpers. `is_exported` is a weak proxy.
- detect the data-access surface (ORM models, SQL, Convex mutations). There is no `table`/`model`/`query` node kind. You would write framework resolvers for this.

> **Correction, 2026-08-02 — the metadata claim above was read off the schema, not off a populated index, and it does not survive measurement.** `signature`, `return_type`, `decorators`, and `docstring` are columns that *exist*; `signature` holds up, `return_type` and `docstring` do not, and `decorators` has not been measured either way. Measured across two indexes ([finding 001](../specs/001-discovery-validation/findings/001-structure-recovery.md), [finding 004](../specs/001-discovery-validation/findings/004-recall-against-authoritative-key.md)):
>
> - **`return_type` is empty on every node** — all 63,783 on the TypeScript target and all 48,154 on the Python one. Return types survive only as unparsed text inside the `signature` string.
> - **`docstring` is worse than sparse: it is wrong.** Of 10,143 indexed Python functions that genuinely carry a PEP 257 docstring, the index records one for **355**, and exactly **one** of those 355 is the real docstring. The extractor reads *above* the `def` — the JavaScript and Java convention — and captures whatever comment banner sits there. A populated field is therefore not a trustworthy field, and a semantic layer consuming it has no signal that anything went wrong. Treat the field as unusable pending a fix.
> - **`route` nodes carry no contract at all** — zero signatures, zero return types, zero docstrings, on both TypeScript and Python. A route node is `(method, path, file, line)` and nothing more, so every contract must be reached through the handler.
>
> What survives, and it is the load-bearing half: **`signature` is populated on at least 99.6% of functions and methods on both targets** (100% and 99.98% on TypeScript, 99.7% and 99.6% on Python), and the route→handler manifest is exact where a framework resolver emits a direct edge — 69 of 69 links on Python matched the framework's own `route.endpoint.__name__`. The correct reading of this section is that the *structural* raw material is present and the *semantic* raw material largely is not, which is the boundary the product already intended. The new obligation is a field-level validity check rather than a null check.

**Agent boundaries — no.** This is the gap. Searching the README and source, there is **no** notion of:
- architectural layer (UI / API / service / data-access / jobs)
- domain or bounded context
- module clustering / community detection
- package-level or service-level aggregate nodes (the `module` node kind exists in `NODE_KINDS` but is a language-level module, e.g. a Python module, not an architectural module)
- any graph-partitioning algorithm

`src/mcp/dynamic-boundaries.ts` is a false friend — despite the name, it detects **dynamic-dispatch boundaries** (where a static call graph breaks at `handlers['save']`, `getattr`, reflection, a message bus) so `codegraph_explore` can honestly report "the static path ends here." It is deterministic regex over comment-stripped bodies, run at query time, and never mutates the graph. Useful (a generated multi-agent system will hit exactly these walls), but it is not architectural decomposition.

`src/directory.ts` is also a false friend — 39 KB of `.codegraph/` directory management, not directory-structure analysis.

**So: what would you build on top?** The inputs are all there:
1. **Directory structure** (from `nodes.file_path`) — the single strongest layer signal in practice.
2. **File-level import DAG** (`getFileDependencies`) — run a clustering/partitioning pass (Louvain, label propagation, or a simple SCC + topological-layer assignment) to find cohesive modules and the direction of dependency. codegraph gives you the edges; the algorithm is yours.
3. **Framework signals** (`getDetectedFrameworks`, `route` nodes, `decorators`) — classify clusters as UI / API / data / jobs.
4. **Entry points** (`route` nodes, `main` functions, CLI commands) and **sinks** (ORM/driver calls) — anchor the layering.
5. **LLM adjudication** over the cluster summaries — the pragmatic final step, using `buildContext` output as evidence.

That is a real subsystem — call it the *architecture inference layer* — and it is gap G1 in §8.

### Fit assessment — `codegraph`

**Verdict: ADOPT AS FOUNDATION.**

Reasoning:
- MIT, local-first, no network dependency, no per-token cost for analysis. The economics of "analyze any codebase" collapse if analysis is LLM-priced; codegraph makes the bulk of it a deterministic local pass.
- 39 languages with graceful degradation is closer to "any language" than any realistic alternative (LSP-per-language, SCIP indexers, or per-language AST tooling all cost far more to operate).
- The SQLite artifact is the right integration boundary: language-agnostic, queryable from the generated agent stack in any runtime, and durable across sessions — which is exactly what a **knowledge layer** needs.
- Incremental sync + file watching means the knowledge layer can stay fresh as the generated agents modify the codebase. That is a hard requirement the vision implies and codegraph already satisfies.
- The MCP server means you can hand the graph to a coding agent as tools *today*, with zero glue.

Caveats to plan around:
- **Node 22.5+ requirement** for library embedding. If the control plane is Python (likely, given ADK/Claude SDK are Python here), you will either shell out to the CLI with `--json`, run the MCP server, or read the SQLite file directly from Python. **Reading the SQLite file directly is the recommended path** — it is the cheapest, most stable, and least version-coupled.
- **No structured parameter schemas.** Tool synthesis needs a supplementary pass.
- **Name-based resolution is heuristic.** Expect false and missing edges, especially in dynamic languages. The `provenance` column (`tree-sitter` | `scip` | `heuristic`) lets you weight edges by confidence — use it.
- **Single-maintainer project moving fast** (248 KB changelog). Pin a version. Do not depend on internal modules; depend on the schema and the `--json` CLI.
- **Unknown:** whether the SQLite schema is considered stable API. `migrations.ts` exists and the schema comments reference migrations v4 and v6, so it does evolve. `schema_versions` gives you a version to assert on.
- **Added 2026-08-02 — it applies `.gitignore` patterns as an indexing filter without reconciling them against tracked-file status, and so drops committed source silently.** On `adk-python`, every one of the 22 symbol-level misses sat under `src/google/adk/a2a/logs/`, excluded because the repository's `.gitignore` contains `logs/`. Git does not consider those files ignored — they are tracked and `git check-ignore` returns nothing for them — but the indexer excludes them anyway, producing no node of any kind for those files and no error. Reconcile against `git ls-files` before trusting coverage ([finding 004](../specs/001-discovery-validation/findings/004-recall-against-authoritative-key.md) §6).

---

## 2. `spec-kit` — HIGH PRIORITY

### What it is

GitHub's **Spec-Driven Development** toolkit. Critically: it is **not a library and not a runtime**. It is (a) a Python CLI called `specify` that scaffolds a project, and (b) a pile of **markdown prompt templates** that become slash commands in whatever coding agent you use. The "engine" is the agent reading the templates. There is essentially no code that does the work — the templates *are* the product.

- **Package:** `specify-cli`, version `0.15.2.dev0` (`pyproject.toml`)
- **Git:** `v0.1.10-1117-gd1e86f6`, HEAD `d1e86f63` dated 2026-07-31 (1117 commits past the last `v0.1.x` tag; version tagging is inconsistent with `pyproject.toml` — trust `pyproject.toml`)
- **License:** MIT, Copyright GitHub, Inc.
- **Runtime:** Python ≥3.11, `typer` + `rich` + `pyyaml`
- **Maturity:** high and moving fast. 100 KB CHANGELOG, 63 test directories, a documented extension API, a Zenodo DOI (`.zenodo.json`), and claimed support for 30+ agent integrations (`README.md:156-160`).

### The workflow

Core slash commands (`README.md:166-188`, templates in `templates/commands/`):

| Command | Purpose | Produces |
|---|---|---|
| `/speckit.constitution` | Project governing principles | `.specify/memory/constitution.md` |
| `/speckit.specify` | What you're building; requirements + prioritized user stories | `specs/[###-feature]/spec.md` |
| `/speckit.clarify` | Interrogate underspecified areas (optional, pre-plan) | edits to `spec.md` |
| `/speckit.plan` | Technical plan with chosen stack | `plan.md`, `research.md`, `data-model.md`, `quickstart.md`, `contracts/` |
| `/speckit.tasks` | Actionable task list | `tasks.md` |
| `/speckit.analyze` | Cross-artifact consistency & coverage check | report |
| `/speckit.checklist` | "Unit tests for English" — requirement quality checklists | `checklists/` |
| `/speckit.implement` | Execute the tasks | code |
| `/speckit.converge` | Re-assess codebase vs spec/plan/tasks, append remaining work | new tasks |
| `/speckit.taskstoissues` | Convert tasks to GitHub issues | issues |

The artifact tree is fixed (`templates/plan-template.md:47-57`):

```
.specify/memory/constitution.md
specs/[###-feature]/
├── spec.md          # /speckit.specify
├── plan.md          # /speckit.plan
├── research.md      # /speckit.plan  (Phase 0)
├── data-model.md    # /speckit.plan  (Phase 1)
├── quickstart.md    # /speckit.plan  (Phase 1)
├── contracts/       # /speckit.plan  (Phase 1)
└── tasks.md         # /speckit.tasks (Phase 2)
```

`spec.md` is opinionated in a way that matters here: user stories must be **prioritized (P1/P2/P3) and independently testable** — "if you implement just ONE of them, you should still have a viable MVP" (`templates/spec-template.md:13-20`). Acceptance scenarios are Given/When/Then. `plan.md` has a **Technical Context** block that forces explicit `NEEDS CLARIFICATION` markers on unresolved decisions (`templates/plan-template.md:21-37`) and a **Constitution Check** gate.

### How an agent drives it

Three mechanisms, in increasing order of automation:

1. **Slash commands.** `specify init` writes the command templates into the agent's command directory (`.claude/commands/`, `.github/prompts/`, etc. — 30+ integrations). The human types `/speckit.plan`.
2. **Handoffs.** Command frontmatter declares next steps. From `templates/commands/specify.md:1-10`:
   ```yaml
   handoffs:
     - label: Build Technical Plan
       agent: speckit.plan
       prompt: Create a plan for the spec. I am building with...
     - label: Clarify Spec Requirements
       agent: speckit.clarify
       send: true
   ```
   This is a lightweight agent-to-agent chaining protocol embedded in the prompt files.
3. **Workflows.** `workflows/speckit/workflow.yml` is a declarative DAG with typed inputs, per-step `integration` binding, and **human gates**:
   ```yaml
   steps:
     - id: specify   {command: speckit.specify, integration: "{{ inputs.integration }}"}
     - id: review-spec {type: gate, options: [approve, reject], on_reject: abort}
     - id: plan      {command: speckit.plan, ...}
     - id: review-plan {type: gate, ...}
     - id: tasks     {...}
     - id: implement {...}
   ```
   Gates support `abort` / `skip` / `retry` (the HEAD commit is literally a fix to gate `on_reject` validation).

There are also helper scripts in **three languages** (`scripts/bash/`, `scripts/powershell/`, `scripts/python/` — `create_new_feature`, `setup_plan`, `setup_tasks`, `check_prerequisites`) that the templates invoke to do the deterministic filesystem parts (branch creation, directory scaffolding, prerequisite checks). Ruff config pins a no-`shell=True` subprocess posture (`pyproject.toml`, `[tool.ruff.lint]`), which suggests security review has happened.

### Extension points

| Mechanism | What it does |
|---|---|
| **Extensions** | Add new commands + **hooks** into existing commands. `.specify/extensions.yml` declares `hooks.before_specify` etc.; each command template contains explicit pre-execution hook-check logic (`templates/commands/specify.md:22-50`). Bundled: `git`, `agent-context`, `assess`, `bug`. There is a full `EXTENSION-API-REFERENCE.md`, `EXTENSION-DEVELOPMENT-GUIDE.md`, and an RFC. |
| **Presets** | Override/customize existing command templates. Bundled: `lean`, `constitution-sync`, `scaffold`, `self-test`. |
| **Workflows** | Declarative multi-step YAML with gates, published via a catalog (`workflows/catalog.json`, `step-catalog.json`). |
| **Integrations** | Per-agent adapters (`integrations/catalog.json`) — where commands get written and how they're invoked. |
| **Bundles** | Role-based combinations of the above (`bundles/catalog.community.json`). |
| **Constitution** | `.specify/memory/constitution.md` — persistent project principles that every `plan` is checked against. Effectively a project-level system prompt. |

Everything is **offline-bundleable**: `pyproject.toml` force-includes templates, scripts, extensions, workflows, presets, and a community catalog snapshot into the wheel, explicitly "so `specify init` works without network access (air-gapped / enterprise)."

### Fit assessment — `spec-kit`

**Verdict: ADOPT AS PROCESS. Do not expect it to be part of the product.**

What it gives you:
- A **forcing function on the ambiguity in this vision.** The vision as stated has many `NEEDS CLARIFICATION` items — what exactly is an "agent boundary"? what is the artifact-trading protocol? what does the iframe actually render? The `plan.md` Technical Context block and `/speckit.clarify` exist precisely to surface those before code.
- **Prioritized, independently-testable user stories** map unusually well onto this product's natural increments: P1 = "index a repo and emit one agent with codegraph tools"; P2 = "multi-agent graph"; P3 = "iframe embed." Each is a shippable slice.
- **`contracts/`** is the right home for the two protocol specs this product lives or dies on: the HTTP/SSE surface and the inter-agent artifact-trading protocol.
- **The constitution** is a genuinely good fit for encoding non-negotiables like "generated agents never get unsandboxed shell by default" or "every generated tool must have a schema derived from static analysis, not an LLM guess."
- **Zero lock-in.** It's markdown and a scaffolder. Abandoning it costs nothing.

Frictions worth naming:
- **`/speckit.implement` will not build this product.** These templates assume a feature-sized change in an existing app. A code-generation platform with a static-analysis subsystem, a graph runtime, and a serving layer is many features. Expect to run the cycle repeatedly per subsystem, not once.
- **Meta-confusion: two levels of "spec."** Spec Kit produces a spec for *your* system. Your system produces *generated agent stacks* for a user's codebase. The `data-model.md` for feature "agent generation" is about the schema of a generated agent, not about the user's app. This gets confusing fast in shared documents. **Mitigation: adopt explicit vocabulary early** — `platform spec` vs. `generated-stack manifest` — and put it in the constitution.
- **Spec-driven development assumes a human reviews the spec.** The `gate` steps in `workflow.yml` are human approval points. That's correct for building the platform. It is *not* a model you can lift into the generated runtime — the generated agents will need autonomous decision-making with different guardrails.
- **A tempting but dangerous idea:** reusing spec-kit templates *inside* the generated agent stack, so generated agents do spec→plan→tasks→implement on the user's codebase. This is attractive (it is a proven agent workflow, MIT-licensed, and the artifacts are natural trading goods between graph nodes). It is also a scope trap — spec-kit's templates assume a single-agent chat loop with a human, slash-command dispatch, and a git branch per feature. Treat it as **inspiration for the artifact schema**, not as a drop-in.

**Concrete recommendation:** run `specify init` on `function2agent` now, write the constitution, and run `/speckit.specify` + `/speckit.clarify` on the P1 slice only. Do not attempt to spec the whole vision in one pass.

---

## 3. `adk-python` — MEDIUM PRIORITY (narrow focus: generation & serving)

> A sibling doc surveys ADK generally. This section only covers what the vendored source says about **programmatic construction, dynamic tool synthesis, graph semantics, state/session durability, and HTTP/SSE serving.**

### Version verification

**Confirmed: `__version__ = "2.6.1"`** (`src/google/adk/version.py:16`). Git HEAD `f4e72334`, dated 2026-07-31; `git describe` gives `v1.32.0-940-gf4e72334` (tag lag — trust `version.py`). `pyproject.toml` declares `name = "google-adk"`, `requires-python = ">=3.10"`. **License: Apache-2.0.**

**Confirmed: `SequentialAgent` / `ParallelAgent` / `LoopAgent` are deprecated in favor of `Workflow`.** All three carry `@deprecated(...)` decorators from `typing_extensions` with identical wording — e.g. `src/google/adk/agents/loop_agent.py:53-55`: *"LoopAgent is deprecated in favor of Workflow and will be removed in a future release."* Same at `sequential_agent.py:49` and `parallel_agent.py:167`. The sibling doc's finding is correct against this local copy. **Do not build on the `*Agent` workflow primitives.**

### The `Workflow` graph API — and why it fits

`src/google/adk/workflow/` exports (`__init__.py`): `Workflow`, `Graph`, `Edge`, `BaseNode`, `Node`, `node`, `FunctionNode`, `JoinNode`, `START`, `DEFAULT_ROUTE`, `RetryConfig`, `NodeTimeoutError`.

`Workflow` is a **Pydantic `BaseModel`** subclassing `BaseNode` (`_workflow.py:145`):

```python
class Workflow(BaseNode):
  edges: list[EdgeItem] = Field(default_factory=list)
  graph: Graph | None = None
  max_concurrency: int | None = None
  rerun_on_resume: bool = True

  def model_post_init(self, context):
    if self.edges and self.graph is None:
      self.graph = self._build_graph()   # Graph.from_edge_items(...) + validate_graph()
    self._validate_state_schema()
```

`Edge` (`_graph.py:58-69`) is `{from_node: BaseNode, to_node: BaseNode, route: RouteValue | list[RouteValue] | None}`. `Graph.from_edge_items()` compiles a node list from the edges and `validate_graph()` checks it. `Workflow` **is itself a `BaseNode`**, so graphs nest.

**Why this is the single strongest argument for ADK here:** the graph is *data*. Building a workflow is constructing a list of Pydantic models. That is exactly what a code generator wants — no source-file emission, no import gymnastics, no AST templating. You can go straight from a codegraph-derived decomposition to a live `Workflow` object in memory, or serialize it (these are Pydantic models with `SerializeAsAny`) and rehydrate it.

Other graph features that map onto the vision:
- **Routing / conditional edges** via `route` on the `Edge` and `DEFAULT_ROUTE`; `Graph.get_next_pending_nodes()` (`_graph.py:133`) is the scheduler hook.
- **Join semantics** via `JoinNode` — fan-in for artifact merging.
- **Loops** — `_workflow.py` has a `_LoopState` (line 69) and the orchestration loop lives in `_run_impl`. Loops are graph cycles, not a separate `LoopAgent`.
- **Dynamic nodes at runtime** — `ctx.run_node(...)` (`src/google/adk/agents/context.py:423`) with `_schedule_dynamic_node.py` and `_dynamic_node_scheduler.py`. Dynamic nodes are awaited inline by their parent and are *excluded* from `max_concurrency` throttling to avoid deadlock (`_workflow.py:162-167`). **This is the mechanism for an agent spawning a sub-agent it decided on mid-run** — a hard requirement if the generated stack is to adapt.
- **Retry + timeout** as first-class node config (`RetryConfig`, `NodeTimeoutError`).
- **State schema validation** — `Workflow._validate_state_schema()` (`_workflow.py:188-212`) raises `StateSchemaError` if a `FunctionNode`'s parameters aren't declared in the workflow's `state_schema`. A typed blackboard, checked at construction. Good for generated graphs, where a silent typo would otherwise surface at runtime.

### Programmatic agent construction

Three paths, in decreasing order of recommendation:

1. **Direct object construction (recommended).** `LlmAgent(name=..., model=..., instruction=..., tools=[...], ...)` — Pydantic. Generate a Python dict from the codegraph decomposition, validate, instantiate. Nothing needs to be written to disk.
2. **`AgentTool`** (`src/google/adk/tools/agent_tool.py:108`) wraps a `BaseAgent` as a tool, with `_get_input_schema` / `_get_output_schema` pulling from the agent's declared schemas (lines 58, 83). This is the "agent-as-callable" primitive for hierarchical delegation, distinct from graph edges.
3. **YAML config (`AgentConfig`)** — `BaseAgentConfig` / `LlmAgentConfig` with `agent_class`, `tools: list[ToolConfig]`, `sub_agents: list[AgentRefConfig]`, and a published JSON Schema at `src/google/adk/agents/config_schemas/AgentConfig.json`. **Caution: `config_agent_utils.from_config` is decorated `@deprecated` (`config_agent_utils.py:35`).** The declarative surface exists and is schema'd, but Google is signalling it away. Do not make YAML the generation target.

### Dynamic tool synthesis

This is where ADK is unexpectedly strong for this product:

| Mechanism | File | Relevance |
|---|---|---|
| **`FunctionTool`** | `tools/function_tool.py:72` | Wraps any Python callable; declaration auto-derived from the signature via `_automatic_function_calling_util.py` / `_function_parameter_parse_util.py`. To synthesize a tool at runtime you build a callable with the right signature/annotations and wrap it. |
| **`BaseTool` subclassing** | `tools/base_tool.py:51` | `_get_declaration() -> types.FunctionDeclaration` is the one method to override. **You can return a `FunctionDeclaration` you built from a JSON Schema you derived from static analysis** — no Python signature required. This is the cleanest synthesis path. |
| **`BaseToolset`** | `tools/base_toolset.py:63` | `async def get_tools(...)` returns a tool list **at request time**, with a `ToolPredicate` filter and `get_tools_with_prefix()` for namespacing. A generated stack can expose a `CodebaseToolset` that materializes tools lazily from the knowledge graph, and re-materializes them after a re-index. |
| **`OpenAPIToolset`** | `tools/openapi_tool/openapi_spec_parser/openapi_toolset.py:46` | Parses an OpenAPI spec dict into `RestApiTool`s (`_parse`, line 241), with auth and SSL config. **Direct fit:** codegraph's `getRoutingManifest()` → synthesized OpenAPI document → `OpenAPIToolset` → a full set of "call the target app's API" tools, for free. |
| **`MCPToolset`** | `tools/mcp_tool/mcp_toolset.py` | Consume any MCP server as tools. **codegraph ships an MCP server** — the knowledge layer plugs in with zero glue. |
| **`_agent_to_mcp.py`** | `tools/mcp_tool/_agent_to_mcp.py` | The reverse: expose an ADK agent *as* an MCP server. Useful for the integration surface. |
| **`skill_toolset.py`, `toolbox_toolset.py`, `langchain_tool.py`, `crewai_tool.py`** | `tools/` | Adapters. `skill_toolset` + `src/google/adk/skills/` suggests a Claude-Skills-like mechanism landed in ADK 2.x. **Not investigated in depth.** |

### Serving over HTTP/SSE

`get_fast_api_app(...)` in `src/google/adk/cli/fast_api.py:404` builds a FastAPI app. The streaming endpoint is `@app.post("/run_sse")` with `media_type="text/event-stream"` (`src/google/adk/cli/api_server.py:1733`, `:1826`). There are additionally `/api/reasoning_engine` (JSON) and `/api/stream_reasoning_engine` (`StreamingResponse`) for Agent Engine compatibility (`fast_api.py:844-931`), plus a `/builder/*` surface and an Angular web UI served from `ANGULAR_DIST_PATH`.

**This is the single largest thing ADK gives you for free.** The vision requires HTTP/SSE serving of the generated stack; ADK ships it, with sessions, artifacts, and a dev UI attached. Deployment helpers exist too (`cli/cli_deploy.py`, `code_executors/gke_code_executor.py`).

The **iframe embed** requirement is *not* covered — the bundled Angular UI is a developer console, not an embeddable widget, and there is no CORS/origin-scoped embed story visible. That's yours to build (gap G5 in §8).

### State, sessions, memory, artifacts

| Concern | ADK provides |
|---|---|
| **Sessions** | `sessions/`: `InMemorySessionService`, `SqliteSessionService`, `DatabaseSessionService` (SQLAlchemy), `VertexAiSessionService`, plus a `migration/` package and `schemas/`. **Durable session state out of the box.** |
| **State** | `sessions/state.py` with `StateSchema` and `StateSchemaError`; `Workflow.state_schema` typed and validated at graph-build time. |
| **Memory** | `memory/`: `InMemoryMemoryService`, `VertexAiMemoryBankService`, `VertexAiRagMemoryService`. The non-Google options are thin — the vision's "memory layer" will need custom work or a `BaseMemoryService` implementation backed by the codegraph DB. |
| **Artifacts** | `artifacts/`: `BaseArtifactService` with `InMemory`, `File`, and `GCS` implementations, plus `_forwarding_artifact_service.py` in `tools/`. **This is the closest thing in any of these repos to the vision's "artifact trading between agents."** It is a versioned blob store keyed by session — not a typed, negotiated exchange protocol, but a real substrate to build one on. |
| **Env vars** | `load_dotenv` is used in `cli/cli.py`, `cli/fast_api.py`, `cli/service_registry.py`, `cli/cli_tools_click.py`, `cli/utils/agent_loader.py` — per-agent `.env` loading is baked into the agent loader. Adequate for local dev; **not** a secrets-injection story for a multi-tenant generated stack. |
| **Sandboxing** | `code_executors/`: `ContainerCodeExecutor`, `GkeCodeExecutor`, `AgentEngineSandboxCodeExecutor`, `VertexAiCodeExecutor`, `BuiltInCodeExecutor`, and an explicitly-named `UnsafeLocalCodeExecutor`. Container/GKE isolation is real and pluggable. |

### Notable surface not investigated

`a2a/` (Agent-to-Agent protocol — likely relevant to inter-agent messaging), `plugins/`, `skills/`, `optimization/`, `evaluation/`, `labs/`, `features/`, `environment/`, `apps/`, `dependencies/`. Also `tools/bash_tool.py` and `tools/_node_tool.py` — a bash tool exists in ADK, which weakens (but does not eliminate) the argument that you need the Claude SDK for shell access. **Flagged as follow-up.**

### Fit assessment — `adk-python`

**Verdict: ADOPT PARTIALLY — as the orchestration and serving layer.**

Strengths against this vision, ranked:
1. **`Workflow` graphs are declarative Pydantic data.** Generating a graph is generating objects. Nothing else here comes close.
2. **HTTP/SSE + sessions + artifacts ship together.** Weeks of infrastructure you do not write.
3. **`BaseToolset.get_tools()` is async and request-time** — tool inventories can be derived from a live knowledge graph and refreshed after re-indexing.
4. **`OpenAPIToolset` + `MCPToolset`** are ready-made bridges from "the target app has an HTTP API" and "codegraph has an MCP server" to "the agent has tools."
5. **Pluggable sandboxed code execution** (container/GKE) — a hard requirement once generated agents run shell commands against a user's repo.

Risks:
- **Churn.** Deprecating `SequentialAgent`/`ParallelAgent`/`LoopAgent` at 2.6.1 while `from_config` is *also* deprecated is a lot of movement in a load-bearing dependency. Pin hard; wrap the ADK API behind your own thin façade so a 3.x break is contained.
- **Google-centric defaults.** Memory services are Vertex-only in practice; the model layer defaults to Gemini. `models/` supports LiteLLM (not verified in this pass) — **confirm multi-provider support before committing.**
- **Weight.** ADK 2.6.1 is a very large surface (a2a, evaluation, optimization, labs, computer_use, BigQuery/Spanner/Bigtable/PubSub toolsets). Most of it is irrelevant here and is dependency and CVE surface.

---

## 4. `claude-agent-sdk-python` — MEDIUM PRIORITY

### What it is

A Python wrapper around the **Claude Code CLI**. It does *not* reimplement the agent loop — it spawns the `claude` binary as a subprocess and speaks a streaming JSON protocol over stdio (`src/claude_agent_sdk/_internal/transport/subprocess_cli.py`). The SDK ships a bundled CLI (`src/claude_agent_sdk/_bundled/`, `_cli_version.py`, `scripts/download_cli.py`).

- **Version:** `0.2.128` (`pyproject.toml`, `_version.py:3`); git tag `v0.2.128`, HEAD `f8b9ec92` dated 2026-07-25
- **License:** MIT, Copyright (c) 2025 Anthropic, PBC
- **Runtime:** Python ≥3.10, `anyio`, `mcp`
- **Maturity:** high. Extensive `tests/` and `e2e-tests/`, a session-store conformance suite (`src/claude_agent_sdk/testing/session_store_conformance.py`), Postgres/Redis/S3 session-store reference implementations in `examples/session_stores/`.

**Architectural consequence worth internalizing:** the SDK's core value is a *process boundary to a closed-source agent loop*. You get Claude Code's tool suite, harness, context management, and compaction for free — but you cannot restructure the loop. That is the central trade-off versus ADK.

### The built-in tool suite

The vision says "general coding-agent tools equivalent to Claude Code's." The SDK's `tools` option (`types.py:1763-1772`) controls this:

```python
tools: list[str] | ToolsPreset | None = None
# list[str]                                     — e.g. ["Bash", "Read", "Edit"]
# []                                            — disable all built-in tools
# {"type": "preset", "preset": "claude_code"}   — all default Claude Code tools
```

**Important caveat, stated plainly: the SDK does not enumerate the built-in tool names in its type system.** `ToolsPreset` (`types.py:76-80`) is just `{type: "preset", preset: "claude_code"}` — an opaque handle to whatever the CLI's default set is. Tool names appear only in docstrings and examples: `"Bash"`, `"Read"`, `"Edit"`, `"Write"`, `"WebFetch"`, `"Skill"` (`types.py:1766, 1940, 1748`; `README.md:63, 201, 217`). The authoritative list lives in the closed-source CLI, not in this repo.

`ServerToolName` (`types.py:954-963`) is a *different* thing — server-side tools the API executes on the model's behalf: `advisor`, `web_search`, `web_fetch`, `code_execution`, `bash_code_execution`, `text_editor_code_execution`, `tool_search_tool_regex`, `tool_search_tool_bm25`. Don't confuse the two.

**Implication for the vision:** if you want "tools equivalent to Claude Code's" *inside a stack you control*, you have two options — (a) use this SDK and accept the CLI subprocess and its opaque tool set, or (b) reimplement Read/Write/Edit/Glob/Grep/Bash yourself. Option (b) is roughly a week of work for the tools themselves and considerably more for the *quality* details (Edit's exact-match semantics, Grep's ripgrep integration, Bash's persistent-shell and output-truncation behavior) that make the Claude Code suite actually good. **There is no third option where you get the tools as a library.**

### Custom tool registration

Custom tools are **in-process MCP servers** (`README.md:95-135`):

```python
from claude_agent_sdk import tool, create_sdk_mcp_server, ClaudeAgentOptions

@tool("greet", "Greet a user", {"name": str})
async def greet_user(args):
    return {"content": [{"type": "text", "text": f"Hello, {args['name']}!"}]}

server = create_sdk_mcp_server(name="my-tools", version="1.0.0", tools=[greet_user])
options = ClaudeAgentOptions(mcp_servers={"tools": server},
                             allowed_tools=["mcp__tools__greet"])
```

The `@tool(name, description, schema)` decorator takes the schema **as a third argument**, not from the signature — which means **tools can be synthesized at runtime from a schema you computed**, without `exec`-ing generated Python. That is a genuine fit for deriving tools from a code graph. Namespacing is `mcp__{server}__{tool}`. External stdio/HTTP MCP servers are supported alongside in-process ones, so codegraph's MCP server drops in directly.

### Subagents

`AgentDefinition` (`types.py:83-102`) is a plain dataclass:

```python
@dataclass
class AgentDefinition:
    description: str
    prompt: str
    tools: list[str] | None = None
    disallowedTools: list[str] | None = None
    model: str | None = None            # "sonnet"|"opus"|"haiku"|"inherit"|full ID
    skills: list[str] | None = None
    memory: Literal["user","project","local"] | None = None
    mcpServers: list[str | dict[str, Any]] | None = None
    initialPrompt: str | None = None
    maxTurns: int | None = None
    background: bool | None = None
    effort: EffortLevel | int | None = None
    permissionMode: PermissionMode | None = None
```

Passed as `ClaudeAgentOptions.agents: dict[str, AgentDefinition]` (`types.py:1981`). **Fully programmatic** — you can construct a dict of agent definitions from a codegraph decomposition and hand it over. Per-agent tool allowlists, per-agent MCP servers, and per-agent models are exactly the knobs a generated stack needs.

**But:** delegation is via the `Task` tool at the model's discretion — a hub-and-spoke pattern, not a graph with typed edges. There is **no graph, no explicit routing, no join/fan-in, no declared artifact passing between subagents**. Compare `Workflow`/`Edge`/`JoinNode` in ADK. This is the SDK's weakest dimension against the vision.

### Hooks and permissions

`HookEvent` (`types.py:260-271`) — 10 events: `PreToolUse`, `PostToolUse`, `PostToolUseFailure`, `UserPromptSubmit`, `Stop`, `SubagentStop`, `PreCompact`, `Notification`, `SubagentStart`, `PermissionRequest`.

Hooks are registered as `hooks: dict[HookEvent, list[HookMatcher]]` where `HookMatcher(matcher="Bash", hooks=[callback])` scopes by tool name (`README.md:217-220`). A `PreToolUse` hook can return `permissionDecision: "allow" | "deny" | "ask"`.

Separately, `can_use_tool: CanUseTool` (`types.py:1929`) is a per-call approval callback returning `PermissionResultAllow | PermissionResultDeny`. There is careful machinery to warn when `allowed_tools` shadows `can_use_tool` (`_get_can_use_tool_shadowed_warning`, `types.py:1678-1750`) — a subtle footgun they went out of their way to surface.

**This is the best permission model in the inventory, by a wide margin.** For a product where generated agents run arbitrary shell against a user's repository, `PreToolUse` + `can_use_tool` is exactly the interception point you need.

### Sandboxing

`SandboxSettings` (`types.py:874-894`): `enabled` (macOS/Linux bash sandboxing), `autoAllowBashIfSandboxed`, `excludedCommands`, `allowUnsandboxedCommands`, `network`, `ignoreViolations`, `enableWeakerNestedSandbox` (for unprivileged Docker). Filesystem and network restrictions are expressed as **permission rules** (Read deny / Edit allow-deny / WebFetch allow-deny), not as sandbox config.

Compared to ADK's container/GKE code executors, this is *finer-grained but less isolated* — OS-level sandboxing of a bash tool rather than a container boundary. In practice you would want both: container per generated stack, plus in-container permission rules.

### Sessions, state, env

| Concern | SDK provides |
|---|---|
| **Sessions** | `resume: str`, `fork_session: bool`, and a pluggable `session_store: SessionStore` (`types.py:1824, 1977, 2092`). Reference implementations for **Postgres, Redis, S3** in `examples/session_stores/`, plus a published conformance test suite (`testing/session_store_conformance.py`). Session mutation APIs: `fork_session`, `delete_session`, `rename_session`, `tag_session`, `import_session_to_store`, `list_subagents`, `get_subagent_messages` (`__init__.py:28-53`). **This is a more complete session story than I expected, and it beats ADK on pluggability.** |
| **Env vars** | `env: dict[str, str]` (`types.py:1903`) passed to the CLI subprocess. **Direct, clean fit for the vision's environment-variable injection requirement** — each generated stack gets its own env dict. Also `cwd`, `add_dirs`, `settings`, `extra_args`. |
| **State** | No typed shared-state blackboard. State is the conversation transcript plus the filesystem. Compare ADK's `state_schema`. |
| **Artifacts** | None. No artifact service. Files on disk are the medium. |
| **HTTP/SSE** | **None built in.** You wrap it yourself in FastAPI. The cookbook has a reference `server.py` (see §6). |

### Extensibility model — `.claude/` plugins, skills, hooks

`options.plugins: list[SdkPluginConfig]` (`types.py:2031`), `options.skills: list[str] | "all"` (`types.py:1999`), and `options.setting_sources: list[SettingSource]` (`types.py:1987`) expose Claude Code's file-based extensibility. The vendored `claude-agent-sdk-python` repo itself uses it: `.claude/agents/test-agent.md`, `.claude/commands/{commit,generate-changelog,label-issue}.md`, `.claude/skills/verify/SKILL.md`, `.claude/settings.json`.

The plugin shape is visible in `examples/claude-code/plugins/` — e.g. `plugins/feature-dev/` contains `.claude-plugin/plugin.json`, `commands/feature-dev.md`, and `agents/{code-explorer,code-architect,code-reviewer}.md`. A plugin is a directory of markdown + JSON. `.claude-plugin/marketplace.json` at the repo root is the distribution manifest.

**This is a genuinely good model to copy for the generated stack's own extensibility** — the generated agent stack should be a directory of declarative markdown/JSON that a human can read, diff, and edit, rather than opaque generated Python. Steal the *shape*, not the implementation.

### Fit assessment — `claude-agent-sdk-python`

**Verdict: ADOPT PARTIALLY — as the per-node coding executor, not as the orchestrator.**

Use it for:
- The coding-tool suite (the only realistic way to get Claude Code-equivalent tools).
- `PreToolUse` / `can_use_tool` permission interception.
- `env` injection per generated stack.
- Pluggable durable session stores (Postgres/Redis/S3 already written).
- Runtime-synthesized tools via `@tool(name, desc, schema)` + in-process MCP.

Do not use it for:
- Graph orchestration — there is none.
- Artifact passing between agents — there is none.
- HTTP/SSE serving — there is none.
- Typed shared state — there is none.

Additional risks:
- **Subprocess-per-agent.** Every agent instance is a `claude` CLI process. A generated stack with 8 agents is 8 processes plus the orchestrator. Memory and startup cost are real; so is process lifecycle management under concurrency.
- **Vendor lock-in to Anthropic models and to a closed-source loop.** The SDK is MIT, but the CLI it drives is not (see §5). Behavior can change under you between CLI versions; `_cli_version.py` and `scripts/_cli_version_validation.py` exist because this is a known problem.
- **The tool set is not introspectable from code.** You cannot programmatically enumerate the built-in tools to build a UI or an audit log of what a generated agent can do. You have to hardcode a list and keep it in sync.

---

## 5. `claude-code` — MEDIUM PRIORITY

### What it is

**Not the Claude Code source.** It is the public-facing repository for the product: README, a 477 KB CHANGELOG, `feed.xml`, a devcontainer, an issue tracker, and — the only substantive content — a `plugins/` directory of 13 official plugins.

- **Git HEAD:** `7ef6eec9`, dated 2026-07-25
- **License:** `LICENSE.md` reads in full: *"© Anthropic PBC. All rights reserved. Use is subject to Anthropic's Commercial Terms of Service."* **This is proprietary. Nothing here is reusable code.**

### What's actually useful

The `plugins/` directory is a working catalogue of the plugin format, and several plugins are architecturally instructive for this product:

| Plugin | Why it matters here |
|---|---|
| **`feature-dev`** | A 7-phase workflow with three specialist agents — `code-explorer`, `code-architect`, `code-reviewer`. **This is essentially a hand-authored version of what this product wants to generate.** Read `plugins/feature-dev/agents/*.md` for how Anthropic writes specialist agent prompts. |
| **`code-review`** | 5 parallel Sonnet agents with **confidence-based scoring to filter false positives**. A concrete pattern for fan-out + merge with quality gating. |
| **`pr-review-toolkit`** | 6 narrowly-scoped analyst agents (`comment-analyzer`, `silent-failure-hunter`, `type-design-analyzer`, …). Good evidence that **narrow, single-concern agents outperform generalists** — supports the vision's decomposition thesis. |
| **`hookify`** | Generates hooks by analyzing conversation patterns. A meta-generation pattern: an agent that writes agent configuration. |
| **`ralph-wiggum`** | A `Stop` hook that intercepts exit attempts to force continued iteration. **This is a loop implemented as a hook** — a cheap, real technique for the "loop" half of graph-loop, if you go the Claude SDK route. |
| **`plugin-dev`** | 8-phase guided plugin creation with `agent-creator`, `plugin-validator`, `skill-reviewer` agents. Again: agents that generate agents. |
| **`security-guidance`** | A `PreToolUse` hook checking 9 security patterns (command injection, XSS, eval, dangerous HTML, pickle, `os.system`). Directly liftable as a *pattern* for guardrailing generated agents. |

Plugin anatomy (`plugins/feature-dev/`):
```
.claude-plugin/plugin.json
commands/feature-dev.md
agents/code-explorer.md
agents/code-architect.md
agents/code-reviewer.md
README.md
```

### Fit assessment — `claude-code`

**Verdict: REFERENCE ONLY.** Proprietary license, no reusable code. Its value is as a **worked example of the target artifact**: `plugins/feature-dev/` and `plugins/pr-review-toolkit/` are hand-written versions of what this product must generate mechanically. Read the agent prompt files as prior art on prompt structure, scope discipline, and inter-agent handoff phrasing. Do not copy text.

---

## 6. `claude-cookbooks` — MEDIUM PRIORITY (skim only)

MIT-licensed notebook collection. Only two directories are relevant.

**`claude_agent_sdk/`** — 8 notebooks plus supporting packages. Two matter:
- **`07_Hosting_the_agent.ipynb` + `claude_agent_sdk/hosting/`** — the missing HTTP layer for the Claude SDK. Contains `server.py`, `run_once.py`, `entrypoint.sh`, `Dockerfile`, and `docker/`, `kubernetes/`, `modal/` deployment variants. **If you go the Claude-SDK route, this is your starting point for the serving requirement**, and it is the single most directly reusable thing in the cookbooks.
- **`06_The_vulnerability_detection_agent.ipynb`** — an agent that analyzes a codebase. Relevant to the analysis half of the product.

**`managed_agents/`** — cookbooks for **Claude Managed Agents (CMA)**, described in `managed_agents/README.md:1-6` as *"Anthropic's hosted runtime for stateful, tool-using agents. You define an agent and a sandboxed environment once, then run them in sessions that persist files, tool state, and conversation across turns."*

**This was not on the brief and is a material finding.** CMA is a third harness option: a hosted runtime with persistent sandboxed environments and durable sessions — which is a large share of the infrastructure this product needs. Directly relevant notebooks:
- `CMA_explore_unfamiliar_codebase.ipynb` — codebase exploration
- `CMA_coordinate_specialist_team.ipynb` — multi-agent coordination
- `CMA_orchestrate_issue_to_pr.ipynb` — end-to-end orchestration
- `CMA_watch_subagents_live.ipynb` — streaming subagent observability
- `CMA_gate_human_in_the_loop.ipynb` — approval gates
- `CMA_plan_big_execute_small.ipynb` — planning decomposition
- `self_hosted_sandboxes/` — sandbox alternatives

**I did not evaluate CMA's API, pricing, self-hosting story, or availability.** Flagged as a follow-up that could change the harness recommendation, because "hosted sandboxed environment with durable file+session state" is precisely the operational burden that makes this product expensive to run.

**Verdict: REFERENCE ONLY**, with one exception — `claude_agent_sdk/hosting/` is copy-able scaffolding, and CMA warrants its own investigation.

---

## 7. ADK vs. Claude Agent SDK as the harness

Evaluated only on the dimensions this product actually needs. Scores: ● strong, ◐ partial, ○ absent.

| Dimension | ADK 2.6.1 | Claude Agent SDK 0.2.128 | Notes |
|---|:--:|:--:|---|
| **Programmatic agent construction** | ● | ● | Both are dataclass/Pydantic-based. ADK: `LlmAgent(...)`. Claude: `AgentDefinition(...)` dict. Neither requires codegen to disk. Tie. |
| **Dynamic tool synthesis from a schema** | ● | ● | ADK: subclass `BaseTool`, return a `FunctionDeclaration` you built; or `BaseToolset.get_tools()` async at request time. Claude: `@tool(name, desc, schema)` — schema is an argument, not derived from the signature. Both avoid `exec`. ADK edges ahead on *re-materialization* (`get_tools()` is called per request, so a re-index refreshes the inventory). |
| **Tools synthesized from an app's HTTP surface** | ● | ◐ | ADK ships `OpenAPIToolset` → `RestApiTool` with auth. Claude: you'd write the MCP tools yourself. **This is a concrete ADK win given codegraph's route manifest.** |
| **Graph orchestration** | ● | ○ | ADK: `Workflow`/`Graph`/`Edge`/`JoinNode`/`route`/`DEFAULT_ROUTE`, validated at construction, nestable. Claude: hub-and-spoke `Task` delegation at model discretion. **Decisive.** |
| **Loops** | ● | ◐ | ADK: cycles in the graph, `_LoopState`, `RetryConfig`, `NodeTimeoutError`. Claude: `max_turns`, plus the `Stop`-hook trick (`ralph-wiggum`). |
| **Dynamic node spawning at runtime** | ● | ◐ | ADK: `ctx.run_node()` + `_dynamic_node_scheduler`. Claude: model-initiated `Task` spawn, not caller-controlled. |
| **Multi-agent artifact passing** | ◐ | ○ | ADK: `BaseArtifactService` (in-memory/file/GCS) + typed `state_schema` blackboard. Not a negotiated exchange protocol, but a real substrate. Claude: the filesystem. **Neither gives you the vision's "artifact trading"; ADK gives you 60% of the plumbing.** |
| **HTTP/SSE serving** | ● | ○ | ADK: `get_fast_api_app()`, `POST /run_sse` with `text/event-stream`, plus a dev UI and deploy helpers. Claude: nothing; the cookbook has a reference `server.py`. **Decisive.** |
| **Session/state durability** | ● | ● | ADK: Sqlite/SQLAlchemy/Vertex services with migrations. Claude: pluggable `SessionStore` with Postgres/Redis/S3 reference impls **and a conformance suite** — arguably better designed, though narrower. Effectively a tie; Claude is more pluggable, ADK is more integrated. |
| **Typed shared state** | ● | ○ | ADK `state_schema` validated against `FunctionNode` params at graph-build time. Claude has no blackboard. |
| **Env var injection** | ◐ | ● | ADK: `load_dotenv` per agent directory in the CLI loader — a dev-mode convenience. Claude: `ClaudeAgentOptions.env: dict[str,str]` handed to the subprocess — explicit, per-instance, exactly right for multi-tenant. **Claude wins.** |
| **Sandboxing** | ● | ◐ | ADK: `ContainerCodeExecutor`, `GkeCodeExecutor`, `AgentEngineSandboxCodeExecutor` — process/container isolation. Claude: OS-level bash sandbox + permission rules — finer-grained, weaker boundary. Different axes; you want both. |
| **Permission / approval interception** | ◐ | ● | ADK: `tool_confirmation.py`, callbacks, plugins. Claude: 10 hook events + `can_use_tool` + shadowing detection. **Claude clearly ahead.** |
| **Coding tool suite (Read/Write/Edit/Grep/Glob/Bash)** | ◐ | ● | ADK has `bash_tool.py` and code executors but no curated coding suite. Claude has the actual Claude Code tools via `{"type":"preset","preset":"claude_code"}`. **Decisive, and it's what the vision explicitly asks for.** |
| **MCP consumption** | ● | ● | Both. codegraph's MCP server plugs into either. |
| **Model portability** | ◐ | ○ | ADK has a `models/` abstraction (LiteLLM support claimed but **unverified in this pass**). Claude SDK is Anthropic-only by construction. |
| **Openness of the runtime** | ● | ○ | ADK is Apache-2.0 all the way down. The Claude SDK is MIT but drives a **proprietary closed-source CLI** (`examples/claude-code/LICENSE.md`). If a customer needs to self-host with no Anthropic dependency, the Claude SDK is disqualifying. |
| **Dependency weight / churn** | ○ | ◐ | ADK 2.6.1 is enormous and actively deprecating core primitives. Claude SDK is small but couples you to CLI version drift. Both need a version pin and an internal façade. |

### Recommendation

~~**Use ADK as the outer graph-loop runtime and serving layer; use the Claude Agent SDK as the executor inside coding-capable nodes.**~~ **Wrap both behind an internal interface from day one.**

> **Superseded for v1 2026-08-03 — `specs/001-discovery-validation/plan.md` OD-15 and OD-16. v1 runs on no agent framework**: the loop, the runner, the session store and a thin HTTP/SSE surface are ours, each provider is reached through its own SDK, and `litellm` is not shipped because it declares no license. The Claude Agent SDK stays an **opt-in** second executor (OD-02). This recommendation was adopted as OD-01 on 2026-08-02 and partially reversed the next day, not because the fit assessment below was wrong, but because **OD-09 cut v1 to a single agent and a single loop** — against which graph execution has no subject, the provider limb was measured non-compliant (finding 003 result 7 counted the adapter referencing xAI's opaque reasoning field **zero times under every counting rule**), and the serving limb had no measurement behind it. **The surviving clause is the last one, and it is the one this section got most right:** the internal interface from day one is what made the reversal a swap rather than a rewrite. **The cost is nine capabilities moved to build with no estimate anywhere** ([14](./14-architecture-synthesis.md) **U-48**). Everything below stands as a fit assessment of the vendored repos.

Concretely:

```
HTTP / SSE  ──►  ADK FastAPI app  (POST /run_sse)
                     │
                 ADK Workflow (graph, edges, routes, joins, state_schema)
                     │   nodes generated from the codegraph decomposition
        ┌────────────┼────────────┬────────────────┐
        ▼            ▼            ▼                ▼
   UI-layer     API-layer    Data-layer      Jobs-layer     ← generated agents
     node         node          node            node
        │            │            │                │
        └── each node's coding capability = Claude Agent SDK session
            (tools preset claude_code, per-node allowed_tools,
             per-node env, PreToolUse guardrails)
            + app-domain tools:
              · OpenAPIToolset  ← from codegraph route manifest
              · MCPToolset      ← codegraph MCP server (the knowledge layer)
              · synthesized BaseTools ← from graph-derived schemas
                     │
              ADK ArtifactService  ← artifact trading substrate
              ADK SessionService   ← durable state
```

**Honest reasoning for this split:**

1. **The graph requirement is non-negotiable and only ADK has one.** "Graph-loop-style agents" with "artifact trading between agents as they move through the graph" is not expressible in the Claude SDK's `Task` delegation. You would build a graph engine from scratch. ADK's is validated, nestable, supports conditional routing and joins, and is constructed from plain data — which is exactly the property a *generator* needs.

2. **The serving requirement is non-negotiable and only ADK has one.** `POST /run_sse` with `text/event-stream` already exists. The alternative is writing and operating it.

3. **The tool-suite requirement points the other way, and it's real.** "Tools equivalent to Claude Code's" is not something ADK provides, and reimplementing Read/Edit/Grep/Glob/Bash *well* is a deceptively large piece of work. Buying it via the Claude SDK is the right call for v1.

4. **They compose without heroics.** A Claude SDK session is an async generator; wrapping one in an ADK `FunctionNode` or a `BaseAgent` subclass is straightforward. The seam is a process boundary you were paying for anyway.

**The costs of this split, stated honestly:**
- Two session/state systems. ADK owns graph state; the Claude SDK owns per-node conversation state. You must decide which is authoritative and keep them from diverging. **Recommendation: ADK state + artifacts are canonical; treat Claude SDK sessions as ephemeral per-node scratch, resumable but not authoritative.**
- Two permission models. ADK gates at the node/tool level; Claude gates inside the subprocess. Guardrails must be expressed twice or generated from one source.
- Process count. One `claude` subprocess per active coding node.
- Two vendors, two deprecation calendars.

**When to reconsider:**
- **If you must be model-agnostic or self-hostable**, drop the Claude SDK and reimplement the coding tools on ADK. Confirm ADK's LiteLLM support first. **✅ This condition fired and the reconsideration went further than the bullet anticipated, 2026-08-03.** Self-hosting was decided (OD-08) and model-agnosticism is a hard requirement (SC-010) — but LiteLLM support was confirmed *and then rejected on other grounds*: an undeclared package license (OD-16) and an adapter measured dropping one provider's opaque reasoning state. So the coding tools are reimplemented on **our own runtime**, not on ADK (OD-15).
- **If the graph turns out to be shallow** (2–3 agents, mostly linear), the Claude SDK alone plus a thin orchestrator is much less machinery, and you skip ADK's churn entirely. **Prototype P1 both ways before committing.**
- **If Claude Managed Agents (§6) offers hosted sandboxed environments with durable file state at acceptable cost**, it collapses several gaps below into a vendor dependency. Investigate before finalizing.

---

## 8. Gap analysis — what nothing here provides

These are the things you will build. Ordered by how much they determine whether the product works at all.

### G1. Architecture inference — decomposing a codebase into agent boundaries ★ CRITICAL

**Nothing in this inventory does this.** codegraph gives symbol-level nodes and edges plus framework and route detection. Nowhere is there layer classification, domain/bounded-context discovery, module clustering, or graph partitioning. This is the load-bearing invention of the product.

What has to be built:
- A **clustering pass** over the file-level import DAG (`getFileDependencies`) — Louvain / label propagation / SCC + topological layering — to find cohesive modules and dependency direction.
- A **layer classifier** combining directory structure, framework signals (`getDetectedFrameworks`), `route` nodes, decorators, and file naming, to label clusters as UI / API / service / data-access / jobs / infra.
- **Entry-point and sink detection** beyond HTTP routes: CLI commands, cron/queue consumers, message handlers, ORM/driver call sites, external HTTP clients.
- **An adjudication step** — deterministic clustering will be wrong on real codebases; an LLM pass over cluster summaries (using codegraph's `buildContext` as evidence) is the pragmatic tiebreaker.
- **Cost of being wrong is high**: bad boundaries produce agents that constantly need each other's context, and the graph degenerates into chatter. Budget for a human review/override step on the generated decomposition.

### G2. Tool synthesis from static analysis ★ CRITICAL

Both harnesses can *register* a tool from a schema. **Neither can produce the schema.** codegraph stores `signature` as an opaque **string** and has no `parameters` table, no `model`/`table` node kind, and no return-shape modeling.

What has to be built:
- **Signature → JSON Schema** per language. Trivial-ish for TypeScript/Java/C#/Go/Rust; genuinely hard for Python without annotations, and near-impossible for untyped JS/Ruby/PHP without inference or runtime observation.
- **Domain-operation selection.** Which of 40,000 functions become tools? `is_exported` is far too permissive. You need heuristics (route handlers, service-layer public methods, ORM model methods) plus ranking, plus a cap.
- **Data-access surface extraction** — ORM models, migrations, SQL, Convex functions, GraphQL resolvers. codegraph has no node kind for any of this. Likely delivered as **new codegraph framework resolvers** (a contained, upstreamable change).
- **Safety classification.** Read vs. mutate vs. destructive. The vision says "mutate data" and "run this job" — those need approval gates derived automatically, and getting this wrong means a generated agent drops a production table.
- **Execution binding.** A synthesized tool must actually *call* the target app: in-process import, subprocess, or HTTP against a running instance. **Each mode has different environment, auth, and safety requirements, and the vision doesn't specify one.** This is an open design question, not just an implementation gap.

### G3. Artifact trading protocol ★ HIGH

ADK's `BaseArtifactService` is a versioned blob store; the Claude SDK has nothing. The vision wants agents to *trade* artifacts as they traverse the graph — which implies typed artifacts, producer/consumer contracts, provenance, and validation at handoff.

To build: an artifact type system (spec / plan / diff / test-result / analysis / question), a declared produces/consumes contract per node, schema validation at edge traversal, provenance chaining, and a garbage-collection story. ADK's artifact service is a reasonable backing store; the protocol is yours. Spec Kit's artifact set (`spec.md`, `plan.md`, `tasks.md`, `contracts/`) is a useful starting vocabulary.

### G4. Knowledge + memory layer beyond the code graph ★ HIGH

codegraph is a *code* graph — it is structural, derived, and stateless with respect to the agents. The vision's "knowledge layer and memory layer" needs more:
- **Derived architectural knowledge** (the G1 output) persisted and queryable.
- **Episodic memory** — what agents did, what worked, what the user corrected. ADK's memory services are Vertex-only in practice; the Claude SDK's `memory` field is a Claude Code feature, not a store you control.
- **Semantic retrieval.** codegraph is FTS5 + fuzzy, **no embeddings**. Natural-language queries over the codebase will need a vector index you add.
- **Cross-session learning** and **staleness/invalidation** as the codebase changes under the agents. codegraph's incremental sync handles the code graph; it will not invalidate your derived knowledge.

### G5. The embeddable iframe integration surface ★ HIGH

**Zero coverage in any repo.** ADK's bundled Angular app is a developer console, not an embeddable widget. This is a full frontend product:
- A chat/agent widget bundle served from the generated stack.
- A `<script>`/`<iframe>` snippet with origin-scoped auth (the vision's "assuming ports and DNS are configured" is hand-waving a real problem — CORS, CSP, cookie/`postMessage` auth, token scoping).
- Streaming render of SSE events, tool-call visualization, human approval prompts.
- Multi-tenant isolation: an iframe on a customer's site must not be able to drive another tenant's agents.

**This is a security surface, not a convenience feature.** An embeddable widget that can trigger shell commands on the customer's backend is a remote-code-execution vector unless it is designed carefully from the start.

### G6. Generation pipeline and generated-stack packaging ★ HIGH

Nothing here generates an agent system. You need: the **manifest schema** for a generated stack (agents, tools, graph edges, prompts, env requirements), a **template/prompt-generation engine** that turns the G1 decomposition into agent instructions, **validation** of the generated stack before it runs, **versioning and regeneration** semantics (what happens when the codebase changes — full regen? diff? preserve human edits?), and a **packaging format**. The `.claude/` plugin layout (§5) is the right *shape*: declarative markdown + JSON in a directory, human-readable and diffable.

### G7. Multi-tenant runtime isolation and secrets ★ MEDIUM-HIGH

ADK's `load_dotenv` is dev-mode. The Claude SDK's `env: dict[str,str]` is the right primitive but only that — a primitive. Missing: a secrets backend, per-tenant credential scoping, container/network isolation per generated stack, resource quotas, and audit logging of which agent used which secret. **The vision's "environment variable injection" bullet is one line and is actually a whole subsystem.**

### G8. Cost, budget, and observability ★ MEDIUM

The Claude SDK has `max_budget_usd` (`types.py:1840`) — the only budget primitive found in the inventory. Missing: per-tenant cost attribution across a multi-agent graph, token accounting per node, cost-aware routing (cheap model for classification, expensive for synthesis), and an economic story for the analysis phase (codegraph's local analysis is free, which is why it matters). ADK has `telemetry/`; codegraph has telemetry; neither gives you product-level cost control.

### G9. Evaluation of generated stacks ★ MEDIUM

How do you know a generated multi-agent system for an *unseen* codebase is any good? ADK has `evaluation/`, codegraph has `__tests__/evaluation/`, the cookbooks have `evals/` and `tool_evaluation/` — all for evaluating a *given* agent, none for evaluating a *generation process* across a distribution of codebases. You need a benchmark corpus of repos, golden decompositions, and task suites. **This is the thing that will determine whether the product is credible, and it is the easiest to defer and the most expensive to defer.**

### G10. Dynamic analysis ★ MEDIUM (explicitly in the vision, entirely absent)

The brief says "and where useful, dynamically." codegraph is 100% static, and its `dynamic-boundaries.ts` only *reports* where static analysis fails — it does not resolve it. Runtime tracing, test-execution-derived call graphs, and OpenAPI-from-a-running-server would all improve tool synthesis substantially, especially for dynamic languages where G2 is hardest. Nothing here helps.

### G11. Language coverage below codegraph's floor ★ LOW-MEDIUM

39 languages is excellent but not "any." Gaps for a repo that is mostly config/IaC/SQL, or uses a language with no extractor. Mitigation: `unknown` language degradation plus a text-only fallback agent. Cheap to build, worth having.

### Gap summary

| Gap | Severity | Rough shape |
|---|---|---|
| G1 Architecture inference | ★ Critical | New subsystem on codegraph's graph; the core IP |
| G2 Tool synthesis from analysis | ★ Critical | Per-language schema derivation + codegraph resolvers + safety model |
| G3 Artifact trading protocol | High | Type system + contracts on top of ADK artifacts |
| G4 Knowledge/memory beyond code | High | Vector index + episodic store + invalidation |
| G5 Embeddable iframe surface | High | Full frontend + auth/isolation security design |
| G6 Generation pipeline + packaging | High | Manifest schema, prompt generation, regen semantics |
| G7 Multi-tenant isolation + secrets | Med-High | Secrets backend, per-tenant containers, audit |
| G8 Cost/budget/observability | Medium | Attribution across graph nodes |
| G9 Eval of generated stacks | Medium | Benchmark corpus + golden decompositions |
| G10 Dynamic analysis | Medium | Tracing / test-derived graphs |
| G11 Sub-floor language coverage | Low-Med | Text-fallback agent |

---

## 9. Sources

### Files read in `examples/` (all paths relative to `/Users/djperussina/Code/function2agent/examples/`)

**codegraph** (`v1.5.0-7-g49c11fc`)
- `codegraph/package.json` — version, deps (`web-tree-sitter`, `tree-sitter-wasms`), license, engines, build/copy-assets
- `codegraph/LICENSE` — MIT
- `codegraph/src/db/schema.sql` (194 lines, read in full) — nodes/edges/files/unresolved_refs, FTS5, `name_segment_vocab`, indexes, `project_metadata`
- `codegraph/src/types.ts` (682 lines, read in full) — `NODE_KINDS`, `EDGE_KINDS`, `LANGUAGES`, `Node`, `Edge`, `Subgraph`, `TraversalOptions`, `TaskContext`
- `codegraph/src/index.ts` — public API method list (~70 methods; grepped signatures, lines 214–1824)
- `codegraph/src/db/queries.ts:978-1000` — `getRoutingManifest` SQL
- `codegraph/src/mcp/tools.ts:549-724` — the 8 MCP tool names
- `codegraph/src/mcp/dynamic-boundaries.ts:1-60` — dynamic-dispatch boundary detection (not architectural boundaries)
- `codegraph/src/directory.ts:1-70` — `.codegraph/` dir management, `CODEGRAPH_DIR` env override
- `codegraph/src/resolution/frameworks/index.ts:1-60` — the 30-resolver registry
- `codegraph/src/resolution/frameworks/express.ts:1-80` — `detect()` heuristics, `RESERVED_CALLS`
- `codegraph/src/bin/codegraph.ts` — CLI command list and `--json` flags (grepped)
- `codegraph/README.md:193-261, 458-620` — benchmarks, scale claims, MCP notes, Library Usage / embedding requirements
- Directory listings: `src/`, `src/extraction/languages/` (29), `src/resolution/frameworks/` (25 files), `codegraph-kernel/`

**spec-kit** (`v0.1.10-1117-gd1e86f6`, `specify-cli 0.15.2.dev0`)
- `spec-kit/pyproject.toml` — version, deps, wheel force-includes, ruff subprocess rules
- `spec-kit/LICENSE` — MIT, GitHub Inc.
- `spec-kit/workflows/speckit/workflow.yml` (79 lines, read in full) — the gated specify→plan→tasks→implement DAG
- `spec-kit/templates/spec-template.md:1-60` — prioritized, independently-testable user stories
- `spec-kit/templates/plan-template.md:1-106` — Technical Context, Constitution Check, artifact tree, `NEEDS CLARIFICATION`
- `spec-kit/templates/commands/specify.md:1-50` — frontmatter `handoffs`, extension hook pre-execution logic
- `spec-kit/README.md:156-243` — integrations, command tables, extensions/presets
- Directory listings: `templates/commands/` (10), `workflows/`, `presets/`, `extensions/`, `integrations/`, `scripts/{bash,powershell,python}/`, `src/specify_cli/`, `.specify/memory/constitution.md`

**adk-python** (`2.6.1`, HEAD `f4e72334`)
- `adk-python/src/google/adk/version.py:16` — `__version__ = "2.6.1"`
- `adk-python/pyproject.toml`, `LICENSE` — Apache-2.0, Python ≥3.10
- `adk-python/src/google/adk/agents/{loop,sequential,parallel}_agent.py:49-188` — `@deprecated(... in favor of Workflow ...)`
- `adk-python/src/google/adk/workflow/__init__.py` (read in full) — the exported graph API
- `adk-python/src/google/adk/workflow/_workflow.py:55-214` — `Workflow`, `_build_graph`, `_validate_state_schema`, `max_concurrency`, `_LoopState`
- `adk-python/src/google/adk/workflow/_graph.py:58-185` — `Edge`, `Graph`, `from_edge_items`, `get_next_pending_nodes`, `validate_graph`
- `adk-python/src/google/adk/agents/context.py:423-469` — `ctx.run_node()`
- `adk-python/src/google/adk/tools/base_tool.py:51-182` — `BaseTool`, `_get_declaration`
- `adk-python/src/google/adk/tools/base_toolset.py:41-225` — `BaseToolset.get_tools`, `ToolPredicate`, `get_tools_with_prefix`
- `adk-python/src/google/adk/tools/function_tool.py:72-344` — `FunctionTool`
- `adk-python/src/google/adk/tools/openapi_tool/openapi_spec_parser/openapi_toolset.py:46-241` — `OpenAPIToolset._parse`
- `adk-python/src/google/adk/tools/agent_tool.py:58-353` — `AgentTool`, schema extraction
- `adk-python/src/google/adk/agents/{base_agent_config,llm_agent_config}.py`, `config_agent_utils.py:35` — YAML config; `from_config` deprecated
- `adk-python/src/google/adk/cli/fast_api.py:404-931` — `get_fast_api_app`, `/api/stream_reasoning_engine`
- `adk-python/src/google/adk/cli/api_server.py:1733, 1826` — `POST /run_sse`, `text/event-stream`
- Directory listings: `agents/`, `tools/`, `sessions/`, `memory/`, `artifacts/`, `code_executors/`, `workflow/`, `cli/`

**claude-agent-sdk-python** (`v0.2.128`)
- `claude-agent-sdk-python/pyproject.toml`, `src/claude_agent_sdk/_version.py:3`, `LICENSE` — MIT, Anthropic PBC
- `claude-agent-sdk-python/src/claude_agent_sdk/types.py` — `ToolsPreset` (76-80), `AgentDefinition` (83-102), `HookEvent` (260-271), `SandboxSettings` (874-894), `ServerToolName` (954-963), `_get_can_use_tool_shadowed_warning` (1678-1750), `ClaudeAgentOptions` (1760-2092: `tools`, `allowed_tools`, `env`, `cwd`, `agents`, `hooks`, `can_use_tool`, `sandbox`, `plugins`, `skills`, `setting_sources`, `session_store`, `resume`, `fork_session`, `max_budget_usd`)
- `claude-agent-sdk-python/src/claude_agent_sdk/__init__.py:19-95` — public exports, session mutation API
- `claude-agent-sdk-python/README.md:60-230` — custom tools via `@tool` + `create_sdk_mcp_server`, hooks, `allowed_tools`
- Directory listings: `src/claude_agent_sdk/_internal/`, `examples/session_stores/`, `e2e-tests/`, `.claude/`

**claude-code** (HEAD `7ef6eec9`)
- `claude-code/LICENSE.md` — **proprietary**: "© Anthropic PBC. All rights reserved."
- `claude-code/README.md` — product overview; confirms the repo is not the source
- `claude-code/plugins/README.md` — the 13-plugin table with per-plugin contents
- `claude-code/plugins/feature-dev/` — file listing (plugin.json, commands/, agents/)
- `claude-code/.claude-plugin/marketplace.json` — distribution manifest

**claude-cookbooks**
- `claude-cookbooks/README.md` — scope
- `claude-cookbooks/managed_agents/README.md:1-25` — **Claude Managed Agents** description
- Directory listings: `claude_agent_sdk/` (incl. `hosting/{server.py,run_once.py,Dockerfile,docker,kubernetes,modal}`), `managed_agents/`, `patterns/`, `skills/`

### Git metadata commands run (read-only)

`git log -1 --format='%H %ci %s'` and `git describe --tags` inside `examples/{codegraph,spec-kit,adk-python,claude-agent-sdk-python,claude-code}`.

### External URLs

- codegraph on npm: `https://www.npmjs.com/package/@colbymchenry/codegraph` (referenced in `package.json`; not fetched)
- codegraph upstream: `https://github.com/colbymchenry/codegraph` (from `package.json`; not fetched)
- Spec Kit docs: `https://github.github.io/spec-kit/` (referenced in `README.md`; not fetched)
- Claude Code docs: `https://code.claude.com/docs/en/overview` (referenced in `README.md`; not fetched)

**No external URLs were fetched.** Every claim in this document is grounded in the vendored source. Where a claim comes from a README's own marketing (e.g. the Linux-kernel indexing benchmark), it is labelled "claimed."

### Explicitly not investigated

- ADK: `a2a/`, `plugins/`, `skills/`, `optimization/`, `evaluation/`, `labs/`, `features/`, `environment/`, `apps/`, `models/` (**LiteLLM / multi-provider support unverified — verify before committing to ADK**), `tools/bash_tool.py`, `tools/_node_tool.py`
- ADK: `adk-docs/` and `adk-samples/` were not opened at all (deliberate — a sibling doc covers ADK from public sources)
- codegraph: the Rust kernel internals (`codegraph-kernel/src/`), the resolution algorithm's accuracy, whether the SQLite schema is treated as stable API
- Claude SDK: the wire protocol in `_internal/transport/subprocess_cli.py`; the actual authoritative built-in tool list (**lives in the closed-source CLI**)
- **Claude Managed Agents (CMA)** — API, pricing, self-hosting, availability. Potentially a third harness option; **recommended follow-up.**
- spec-kit: the `specify_cli` implementation beyond command discovery; the extension/preset runtime
- claude-cookbooks: all notebook contents (directory-level survey only)
