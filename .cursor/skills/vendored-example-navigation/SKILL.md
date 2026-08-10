---
name: vendored-example-navigation
description: Routes a question to the right vendored reference repo and file path inside the git-ignored examples/ tree, and states what each repo is not evidence for. Use when looking for prior art on agent harnesses, HTTP/SSE serving, tool synthesis, permissions, orchestration topologies, or code analysis; when about to run a tool against examples/; when picking a validation target; or when treating examples/ as a multi-language corpus.
---

# Navigating `examples/`

Sources: `research/06-examples-inventory.md`, `research/12-examples-as-corpus.md`. Paths below are
relative to `examples/`.

## Two rules before you touch anything

1. **`examples/` is read-only.** Copy to a scratch directory before running anything against it.
   `codegraph init` writes a `.codegraph/` directory into the target; `pip install -e .` writes
   egg-info; `software-bug-assistant` requires editing `tools.yaml`. All violate the constraint
   (`12 §Cross-cutting`).
2. **`claude-code` is proprietary — REFERENCE ONLY.** Read it for structure and approach; **do not
   copy prompt text** (`12 §6.2`).

## The eight repos

The directive that created this tree named nine; **eight exist** (`12 §1`). Do not go looking for the
ninth — if one is wanted it should be vendored deliberately.

| Repo | What it is | Good for |
|---|---|---|
| `adk-python` | Google ADK: SDK + CLI + **HTTP server**. 465k Python LOC | HTTP/SSE serving, OpenAPI→tools, session/artifact/memory service interfaces, agents-as-data. **The one genuine Class B target** |
| `adk-samples` | ~45 sample agents, Python + TS/Go/Java/Kotlin | Polyglot-monorepo behavior; one partial Class B harness |
| `adk-docs` | mkdocs site; 67k Markdown | Little — 3,148 of 4,080 files are pre-built HTML under `site/`. Exclude it |
| `spec-kit` | Python CLI, 153k LOC (51.6k src / 98.4k tests) | Process templates; the corpus's best **dynamic-dispatch** stress case |
| `codegraph` | TS + Rust kernel, CLI + library + MCP server | The analysis substrate; a well-sized 8-tool MCP suite; framework resolvers |
| `claude-cookbooks` | 91 notebooks + Python | Canonical orchestration topologies, memory/compaction, tool evaluation, CMA |
| `claude-agent-sdk-python` | Python SDK, 40k LOC | **The best single harness-surface reference in the corpus** |
| `claude-code` | Plugin/config repo, **no product source** | Hand-authored agent bundles — the artifact you must generate. Proprietary |

**Skew worth internalizing:** two repos carry 76% of all source LOC. Test code frequently *exceeds*
source code (`adk-python` 270,750 test vs. 156,927 src; `spec-kit` 98,376 vs. 51,636). **Any benchmark
that does not separate `src/` from `tests/` reports numbers dominated by test scaffolding.** Also
exclude `adk-samples/python/agents/data-science/flights_dataset/flights_dataset_alloydb.sql` — a single
**165,719-line** data dump that distorts every naive per-file statistic.

## Question → file

**How do I serve agents over HTTP/SSE?**
`adk-python/src/google/adk/cli/fast_api.py:404` — `get_fast_api_app()` (936-LOC file).
`adk-python/src/google/adk/cli/api_server.py` — the **26-route** production surface, including
`POST /run_sse` at `:1733`. `dev_server.py` has 37 more, dev-only. Three same-named
`get_fast_api_app` definitions exist (`fast_api.py:404`, `dev_server.py:1397`, `api_server.py:987`) —
useful as a symbol-resolution disambiguation test.

**How do I turn an OpenAPI spec into tools?**
`adk-python/src/google/adk/tools/openapi_tool/openapi_spec_parser/openapi_toolset.py:46` and
`rest_api_tool.py`. The single most product-relevant module in ADK.

**What does a harness's full surface area look like?**
`claude-agent-sdk-python/src/claude_agent_sdk/types.py` (2,230 LOC) — a complete typed spec.
`AgentDefinition` at `:84` with per-agent `tools`/`model`/`permissionMode` at `:102`, so a
decomposition computed from a code graph is handed over **as data, no source generation**.
`PermissionMode` at `:25`, `PermissionResultAllow`/`Deny` at `:235`/`:244`, `can_use_tool` contract at
`:210`. **Read `:1669` and `:1696-1720` before designing a permission layer** — they handle the footgun
where `permission_mode` silently shadows `can_use_tool`. `HookMatcher` at `:586`. MCP server configs at
`:603-741`.

**How do I build a tool from a computed schema without `exec`?**
The `@tool(name, description, schema)` decorator in `claude-agent-sdk-python` takes the schema **as an
argument, not from the signature**. This is the key mechanism for tool synthesis.

**What orchestration topology should this be?**
`claude-cookbooks/patterns/agents/` — `basic_workflows.ipynb`, `orchestrator_workers.ipynb`,
`evaluator_optimizer.ipynb`, `async_multi_agent_orchestration.ipynb`. The canonical named topologies in
executable form.

**How does a hosted managed-agent runtime work?**
`claude-cookbooks/managed_agents/` — the CMA notebooks (15 of them) plus six self-hosted-sandbox
reference implementations. Start at `managed_agents/README.md`, then
`CMA_explore_unfamiliar_codebase.ipynb`, `CMA_orchestrate_issue_to_pr.ipynb`,
`CMA_coordinate_specialist_team.ipynb`, `CMA_operate_in_production.ipynb`, and
`self_hosted_sandboxes/README.md` for the worker contract.

**How narrow should a subagent's remit be?**
`claude-code/plugins/pr-review-toolkit/agents/` — six single-concern reviewers
(`code-simplifier`, `silent-failure-hunter`, `type-design-analyzer`, …). **The most interesting data
point in the corpus on boundary granularity**: these are not "backend agent" / "frontend agent." That
argues against file-tree-shaped decomposition. Also `claude-code/plugins/feature-dev/agents/` for a
hand-tuned three-agent workflow.

**What does a safety gate look like, minimally?**
`claude-code/examples/hooks/bash_command_validator_example.py`.

**How is route→handler extraction actually implemented?**
`codegraph/src/resolution/frameworks/` — 25 resolvers; read `express.ts`, `python.ts`, `laravel.ts`.
`codegraph/src/db/schema.sql` — ~~four tables~~ **twelve tables**; **design against the schema, not
the TypeScript API**, because the SQLite file is queryable from any language.
**Struck 2026-08-10 on the measurement that corrected `06 §1`, `12 §6.5` and `14 §2.2`; this site
inherited the figure from `06` exactly as those two did.** Built from the 194-line file: 7 ordinary
tables, the `nodes_fts` virtual table itself, and the 4 shadow tables its `content='nodes'` FTS5
declaration materialises — 12 once `src/analysis/codegraph_pin.py`'s `sqlite_%` filter has run,
beside 20 indexes and 3 triggers, 35 objects in all. **All three of those figures count the pin's
population and not `sqlite_master`'s: raw, the table holds 13 tables, 23 indexes and 39 objects.**
The thirteenth table is `sqlite_sequence`, materialised because `edges` and `unresolved_refs` declare
`INTEGER PRIMARY KEY AUTOINCREMENT`. **So a reader who counts the rows by hand gets 13 and has found
the filter rather than an error here**; `06 §1` carries why the filter's two predicates do unequal
work. **The advice is unchanged, because it never
rested on the width**: what makes the schema the right target is that it is documented and
language-neutral. **Size the work against the 7 ordinary tables you would actually query**, not
against either published count. `codegraph/src/mcp/tools.ts` — the 8 MCP tools,
a calibration point for tool-suite sizing. `codegraph/src/mcp/dynamic-boundaries.ts` — where static
call graphs break (`handlers['save']`, `getattr`, reflection, message buses); the name is misleading
but the "the static path ends here" reporting pattern is worth adopting.

**Where do I start a runnable spike?**
`claude-agent-sdk-python/examples/` — 18 short runnable files, 3,367 lines total, covering subagents,
`tool_permission_callback.py`, `hooks.py`, `mcp_calculator.py`, `session_stores/`,
`max_budget_usd.py`, `streaming_mode*.py`. Read this directory before writing harness code.

## `adk-python` is the one real validation target

**Both halves of the loop live in one repo** (`12 §3.2`): the analysis input
(`src/google/adk/cli/api_server.py`, decorated Python handlers with Pydantic models) and the invocation
target (the same code, running) are the same artifact. It has 26 real CRUD routes (15 GET / 6 POST /
2 DELETE / 2 PATCH / 1 WebSocket), a SQLAlchemy + SQLite data layer with migrations, and **FastAPI
auto-publishes `/openapi.json`, which is a free, exact answer key.**

The highest-value single measurement: diff synthesized routes for `api_server.py` against
`/openapi.json` on method, path template, handler symbol, and parameter schema. **Every one of the 26
uses a multi-line decorator** (`api_server.py:1295-1298`), so naive single-line regex extraction misses
them. This is a real adversarial test, not a gimme.

Verify by direct DB inspection of the SQLite session store — **not** by asking the agent whether it
succeeded.

Unverified: whether `adk api_server` serves CRUD without `GOOGLE_API_KEY`. Check first; it changes
setup cost materially.

`adk-samples/python/agents/software-bug-assistant` is a *partial* Class B harness — live Postgres +
MCP-Toolbox over a `tickets` table, but the tools are **hand-authored in
`deployment/mcp-toolbox/tools.yaml`**, so there is no application code they could have been derived
from. It validates the *invoke* half, not the *synthesize* half.

## What `examples/` cannot validate

The corpus is **78.4% Python / 16.3% TypeScript** (869,181 / 180,615 of 1,109,021 total source LOC).
Go, Java, and Kotlin together are **1.5%**, mostly short doc snippets. Dart and Scala appear only as
`codegraph` test fixtures.

> **Zero real PHP, Ruby, C#, or Swift** — yet `codegraph` ships `laravel.ts`, `ruby.ts`, `csharp.ts`,
> and `swift.ts` resolvers this corpus can never exercise. `express` and `nestjs` resolvers are also
> untouched.

Also absent: any conventional MVC web application in any language; any ORM-with-migrations domain model
except ADK's own session store; any meaningful auth or multi-tenancy layer; anything that can be
meaningfully damaged (so nothing here says how a generated agent behaves when a tool actually deletes
a customer record).

> **The practical rule:** treat `examples/` results as a **necessary-but-not-sufficient gate.** Failing
> here is decisive evidence of a problem. Passing licenses exactly one claim — "the analysis layer
> handles well-maintained, mostly-Python SDK repositories" — and **no claim at all** about polyglot
> support or the product's market.

Any go/no-go on Class B, multi-language support, or production readiness requires external repos:
a Django or Rails app with ORM and migrations; a Spring Boot or ASP.NET service; an Express or NestJS
API; a large C/C++ codebase to test the scale claim rather than trusting it.

## Do / don't

```
DON'T  run codegraph index, pip install -e ., or any writing tool inside examples/
DON'T  copy prompt text from claude-code
DON'T  cite examples/ as evidence of polyglot support
DON'T  report analysis metrics without separating src/ from tests/
DON'T  include the 165k-line flights_dataset SQL dump in any per-language statistic
DON'T  treat adk-samples' 13 fast_api_app.py entry points as domain APIs — they serve the agent

DO     copy to a scratch directory first
DO     use adk-python + /openapi.json as the ground-truth answer key
DO     read claude-agent-sdk-python/src/claude_agent_sdk/types.py before designing a harness surface
DO     state explicitly which claim a given examples/ result does and does not license
```

## Related skills

`codebase-decomposition` for what the granularity prior from `pr-review-toolkit` implies.
`tool-synthesis-from-code` for the OpenAPI→tools bridge. `agent-tool-design` for tool-suite sizing
calibrated against `codegraph`'s 8 tools.
