# 12 — `examples/` as a Working Corpus

**Last researched: 2026-08-02**

## TL;DR

> - **Eight repos, not nine.** The directive named nine; `examples/` contains eight. Measured: **1,109,021 lines of source** across **4,420 source files** in the counted languages, plus ~212k lines of Markdown, ~100k lines of notebook JSON, and one 165k-line SQL data dump.
> - **There is exactly one genuine Class B target, and it is not in `adk-samples`: it is `adk-python` itself.** `adk api_server` stands up a FastAPI service with **26 routes** (15 GET / 6 POST / 2 DELETE / 2 PATCH / 1 WebSocket), a real SQLAlchemy+SQLite data layer (`sessions/sqlite_session_service.py`, `sessions/database_session_service.py`), session/artifact/memory CRUD, and auto-generated OpenAPI. Crucially, **the application source is in the same repo**, so the full loop — analyze code → derive routes → synthesize tools → invoke live server → compare against ground truth — is testable end to end with `pip install -e . && adk api_server`. No cloud account required.
> - **`adk-samples/python/agents/software-bug-assistant` is a *partial* Class B target.** It gives you a live Postgres + MCP-Toolbox HTTP surface with real CRUD over a `tickets` table. But the tools are **hand-authored in `deployment/mcp-toolbox/tools.yaml`** — there is no application code from which they could have been derived. It validates the *invoke* half, not the *synthesize* half. Useful as a harness; not an end-to-end test.
> - **Everything else is a weak Class B target.** The prior in the directive is correct: SDKs, CLIs, docs sites, and notebook collections. No running app, no data layer, nothing to invoke over a boundary.
> - **As a multi-language *analysis* corpus it is mediocre and lopsided.** 78% of source LOC is Python; 16% TypeScript. Go/Java/Kotlin/Scala/Dart appear only as thin sample or fixture files (≤8.7k LOC each). **Zero real PHP, Ruby, C#, or Swift** — yet `codegraph` ships framework resolvers for `laravel.ts`, `ruby.ts`, `csharp.ts`, and `swift.ts` that this corpus will never exercise.
> - **First smoke test:** `codegraph index` over all eight repos, capture `status --json` + a fixed query battery, and diff `codegraph`'s route extraction for `adk-python/src/google/adk/cli/api_server.py` against the 26 routes enumerated by hand in this document. That is the cheapest ground-truth check available and it needs nothing but Node 20+.
> - **The one thing `examples/` cannot validate:** that the product works on a customer's production web application. There is not a single conventional CRUD web app in this corpus — no ORM-backed domain model with controllers, no auth-guarded multi-tenant service, no migration history. A green run over vendored SDK repos is evidence about the *analysis layer* only.

---

## Contents

1. [Scope, method, and the repo-count discrepancy](#1-scope-method-and-the-repo-count-discrepancy)
2. [Per-repository characterization matrix](#2-per-repository-characterization-matrix)
3. [Class A vs. Class B suitability](#3-class-a-vs-class-b-suitability)
4. [Value as a multi-language analysis corpus](#4-value-as-a-multi-language-analysis-corpus)
5. [`codegraph` self-analysis as the first smoke test](#5-codegraph-self-analysis-as-the-first-smoke-test)
6. [Value as reference implementations](#6-value-as-reference-implementations)
7. [Dogfooding](#7-dogfooding)
8. [Recommendations by validation stage](#8-recommendations-by-validation-stage)
9. [What `examples/` cannot validate](#9-what-examples-cannot-validate)
10. [Open questions and unverified claims](#10-open-questions-and-unverified-claims)

---

## 1. Scope, method, and the repo-count discrepancy

**Discrepancy, flagged up front.** The task described "nine vendored reference repositories" and then listed eight names. `ls examples/` returns eight directories. This document covers those eight. If a ninth was intended (a plausible candidate would be `google/genai-toolbox`, referenced by `software-bug-assistant` but not vendored), it is **not present** and should be added deliberately rather than assumed.

**Method.** All figures below come from `find` / `wc -l` run on 2026-08-02. `tokei`, `cloc`, and `scc` are not installed on this machine, so LOC is raw physical lines including blanks and comments — it overstates logical LOC by roughly 20–30% for Python and TypeScript. Counts exclude `.git/`, `node_modules/`, `.venv/`, `site-packages/`, `dist/`, `build/`, and `adk-docs/site/` (mkdocs build output). Versions come from read-only `git describe --tags --always` and `git log -1` inside each subrepo. **Nothing in `examples/` was modified, built, installed, or executed.**

**Related documents.** `research/06-examples-inventory.md` exists and assesses these repos as *tooling to adopt*; its `codegraph` verdict is quoted in §5. `research/11-validation-plan.md` **does not exist as of this writing** — §8 therefore proposes a phase structure rather than mapping onto one, and must be reconciled once `11` lands. That is a live dependency.

---

## 2. Per-repository characterization matrix

### 2.1 Size and shape

| Repo | Version (vendored) | Files† | Primary language | Source LOC (top langs) | Artifact kind |
|---|---|---|---|---|---|
| `adk-python` | `v1.32.0-940-gf4e72334` (2026-07-31) | 2,353 | Python | py 465,104 (1,709 files); js 8,590 | SDK + CLI + **HTTP server** |
| `adk-samples` | `739bb34` (2026-07-29) | 2,236 | Python (+TS/Go/Java/Kotlin) | py 172,356; tsx 31,094; ts 5,895; go 667; kt 361; java 358; tf 4,157 | Sample collection (~45 agents) |
| `adk-docs` | `308c7831` (2026-07-31) | 4,080‡ | Markdown | md 67,438; go 8,707; js 7,087; py 6,420; ts 3,912; java 3,733; kt 2,007 | Docs site (mkdocs) |
| `spec-kit` | `v0.1.10-1117-gd1e86f6` (2026-07-31) | 530 | Python | py 152,640 (src 51,636 / tests 98,376) | CLI |
| `codegraph` | `v1.5.0-7-g49c11fc` (2026-08-01) | 678 | TypeScript (+Rust) | ts 134,802 (src 79,189 / tests 53,674); rs 24,356 | CLI + library + MCP server |
| `claude-cookbooks` | `85016ca` (2026-07-23) | 620 | Jupyter + Python | ipynb 91,407 (91 nb); py 24,876; ts 3,061 | Recipe / notebook collection |
| `claude-agent-sdk-python` | `v0.2.128` (2026-07-25) | 135 | Python | py 39,893 (src 11,298 / tests 22,499) | SDK |
| `claude-code` | `v2.1.220` (2026-07-25) | 229 | Markdown (+Python/TS) | md 32,337; py 7,575; tf 1,387; ts 748 | Plugin/config repo (**no product source**) |

† Files excluding `.git/`. ‡ 3,148 of `adk-docs`'s 4,080 files are pre-built HTML under `site/`; the meaningful working tree is ~930 files.

**Skew worth internalizing.** Two repos carry 76% of all source LOC (`adk-python` 465k, `adk-samples` 172k+). Test code frequently *exceeds* source code: `adk-python` has 270,750 test LOC vs. 156,927 src LOC; `spec-kit` has 98,376 vs. 51,636; `claude-agent-sdk-python` has 22,499 vs. 11,298. Any analysis-layer benchmark that does not separate `src/` from `tests/` will produce numbers dominated by test scaffolding. Note also `adk-samples/python/agents/data-science/flights_dataset/flights_dataset_alloydb.sql` — a **165,719-line** single-file data dump that will distort any naive per-file or per-language statistic. Exclude it explicitly.

### 2.2 Contracts, services, data, tests, setup cost

| Repo | Type/contract density | Runnable HTTP service? | Data layer? | Tests | Build/setup cost |
|---|---|---|---|---|---|
| `adk-python` | **Very high.** `py.typed`; 200 files reference `BaseModel`; mypy/pyright configured in `pyproject.toml`; agents, tools, and events are Pydantic v2 models | **Yes — `adk api_server` / `adk web`.** 26 routes in `cli/api_server.py`, 37 more in `cli/dev_server.py`, `get_fast_api_app()` at `cli/fast_api.py:404` | **Yes.** `sessions/sqlite_session_service.py`, `sessions/database_session_service.py` (SQLAlchemy), `sessions/migration/`, `artifacts/file_artifact_service.py` | 515 test files, pytest, `tox.ini` | **Low-moderate.** `pip install -e .`; heavy optional Google deps; SQLite default needs no external service |
| `adk-samples` | Mixed. 58 files with `BaseModel`; per-sample quality varies widely | **Per-sample.** 13 `fast_api_app.py` / `main.py` entry points found | **Per-sample.** Postgres (`software-bug-assistant`), BigQuery/AlloyDB (`data-science`), Firestore, vector stores | 222 test files, unevenly distributed | **High and per-sample.** Most assume GCP project, Vertex AI, `gcloud` auth; 76 Terraform files |
| `adk-docs` | N/A — prose plus code excerpts | No (static site) | No | None | Low (`mkdocs`) — but `site/` is prebuilt, so nothing needs running |
| `spec-kit` | **Low-moderate.** No Pydantic; 28 `@dataclass`; no mypy/pyright config | No | No (writes files to disk) | 138 test files, pytest, pre-commit | **Low.** `uv`/`pip`, pure Python |
| `codegraph` | **High (TS).** `tsconfig.json` `strict: true`, `noImplicitAny`, `strictNullChecks`, `strictPropertyInitialization` | **Not HTTP.** `codegraph daemon` / `serve` are **stdio MCP**, not a REST surface | **Yes — SQLite** (`src/db/schema.sql`, `.codegraph/*.db`) | 162 test files, vitest; `npm test`, plus `__tests__/evaluation/` | **Moderate.** `npm ci && npm run build` (Node ≥20 <25); optional Rust kernel build via `scripts/build-kernel.sh` |
| `claude-cookbooks` | Low. 2 `BaseModel`, 3 `@dataclass`; notebooks are inherently loose | Marginal — `claude_agent_sdk/hosting/` and `session_browser_demo/` | No | 12 test files | Moderate; `uv.lock` present; most notebooks need an Anthropic API key |
| `claude-agent-sdk-python` | **High.** `py.typed`; `types.py` is 2,230 LOC of `@dataclass`/`TypedDict`; mypy configured | No | No (subprocess transport to the `claude` CLI) | 43 test files + `e2e-tests/`; `Dockerfile.test` | **Low** to install, but runtime requires the `claude` CLI binary and an API key |
| `claude-code` | N/A — the product source is **not** in this repo | No | No | **0** test files | Trivial (nothing to build) |

**Three characterizations that matter for planning:**

1. **`claude-code` contains no Claude Code source.** It is a public repo of plugins (`plugins/feature-dev/`, `plugins/pr-review-toolkit/`, …), example configs (`examples/hooks/`, `examples/gateway/`, `examples/mdm/`, `examples/settings/`), issue-triage scripts, and 106 Markdown files. As an *analysis target* it is nearly worthless — 7,575 lines of Python triage tooling and 748 lines of TypeScript. As a *reference artifact* it is one of the most valuable things in the corpus (§6).
2. **`codegraph serve`/`daemon` is stdio MCP, not HTTP.** `06-examples-inventory.md` documents 8 MCP tools in `src/mcp/tools.ts`. That is a tool surface, but it is not "a running application with domain operations over HTTP," so `codegraph` is **not** a Class B target in the sense the product means — though it *is* the closest thing to a synthesized-tool consumer already in the tree.
3. **`adk-docs` is mostly build output.** Treat `adk-docs/examples/{python,typescript,go,java,kotlin}/` as the real content: five parallel language trees of the same conceptual examples. That parallelism is genuinely useful for one specific test (§4.3) and useless for everything else.

---

## 3. Class A vs. Class B suitability

### 3.1 Class A (agent operates *on* the codebase)

Every repo is a usable Class A target — that is nearly tautological, since Class A needs only a filesystem. The question worth asking is which ones make a *discriminating* Class A test, i.e. which have enough structure that a wrong answer is detectable.

| Repo | Class A value | Why |
|---|---|---|
| `adk-python` | **Highest** | Deep package hierarchy, 515 test files as an oracle, Pydantic contracts to derive schemas from, and a real service to break. "Add a route and its test" is a checkable task. |
| `codegraph` | **High** | Strict TypeScript + vitest + a Rust subproject. Exercises polyglot Class A (a task touching both `src/` and `codegraph-kernel/`). Type errors give a hard pass/fail signal. |
| `spec-kit` | **High** | 98k lines of tests over 51k lines of source is an unusually strong verification signal for a small, self-contained CLI. Cheap to run. Good "make a change, prove it green" target. |
| `claude-agent-sdk-python` | **High, small** | 11k src / 22k tests, `py.typed`, mypy. Small enough to fit in context; typed enough to grade. The best *fast-iteration* Class A target. |
| `adk-samples` | Moderate | Highly heterogeneous; good for "can the analyzer handle a monorepo of 45 unrelated subprojects," bad for focused coding tasks. |
| `claude-cookbooks` | Low-moderate | Notebooks are a distinct and awkward Class A modality (JSON-wrapped code, execution-order state). Worth *one* deliberate test; not a workhorse. |
| `adk-docs` | Low | Prose. A documentation-editing agent is a real use case but tests almost nothing about code analysis. |
| `claude-code` | Very low | Nothing substantial to operate on. |

### 3.2 Class B (agent operates *through* the running application)

The directive's prior — "mostly SDKs, CLIs, and docs, not CRUD web applications, therefore weak Class B targets" — **is correct for six of eight repos.** But there are two exceptions, and one of them is better than expected.

#### Exception 1 — `adk-python` itself. **A genuine Class B target.** ★

This is the find. `adk-python` is not only a library; it ships a production FastAPI server.

- **Factory:** `get_fast_api_app()` at `examples/adk-python/src/google/adk/cli/fast_api.py:404` (936 LOC file). Two further variants exist: `dev_server.py:1397` and `api_server.py:987`.
- **Route surface (measured by counting `@app.*` decorators):**
  - `src/google/adk/cli/api_server.py` — **26 routes**: 15 `GET`, 6 `POST`, 2 `DELETE`, 2 `PATCH`, 1 `WebSocket`.
  - `src/google/adk/cli/dev_server.py` — **37 routes** (dev-UI, tracing, eval, agent-graph rendering).
  - `src/google/adk/cli/fast_api.py` — 5.
- **The routes are real domain CRUD, not just health checks.** From `api_server.py`: session create/get/list/delete at `/apps/{app_name}/users/{user_id}/sessions[/{session_id}]` (lines 1296, 1311, 1330, 1347, 1371, 1380); an eight-route artifact sub-API including versions and metadata (lines 1430–1609); `PATCH /apps/{app_name}/users/{user_id}/memory` (1621); `POST /run` (1667) and `POST /run_sse` (1733); plus `/list-apps`, `/apps/{app_name}/app-info`, `/health`, `/version`.
- **There is a real data layer.** `src/google/adk/sessions/sqlite_session_service.py` and `database_session_service.py` (SQLAlchemy) with a `sessions/migration/` directory and `sessions/schemas/`. Artifacts persist via `artifacts/file_artifact_service.py`. **Defaults are local** — SQLite and the local filesystem — so no cloud dependency for the core CRUD paths.
- **FastAPI auto-publishes `/openapi.json`**, which gives you a machine-readable ground truth for every synthesized tool, for free.

**Why this is the strongest possible Class B candidate in the tree:** both halves of the product loop are present in one repo. The *analysis* input (`src/google/adk/cli/api_server.py`, decorated Python route handlers with Pydantic request/response models) and the *invocation* target (the same code, running) are the same artifact. You can therefore measure a thing no other repo here permits: **did the tools we synthesized from static analysis match the tools the live server actually exposes?** `/openapi.json` is the answer key.

**How to stand it up (not executed — plan only):**

```bash
cd examples/adk-python                 # NOTE: examples/ is read-only.
                                        # Copy the tree out first, or use a git worktree
                                        # in a scratch dir. Do not create a venv in place.
python -m venv .venv && . .venv/bin/activate
pip install -e .
# needs at least one agent app dir on disk for /list-apps to be non-empty:
adk api_server <path-to-agents-dir> --port 8000
# ground truth:
curl -s localhost:8000/openapi.json > /tmp/adk-openapi.json
curl -s localhost:8000/health
```

Two caveats, both flagged as **unverified** because nothing was executed: (a) `adk api_server` may require a model API key (`GOOGLE_API_KEY` or Vertex credentials) to serve `/run`, even if the session and artifact CRUD routes work without one — the CRUD subset is the interesting part for Class B and is *likely* key-free, but confirm; (b) `--port`/argument names are inferred from `cli_tools_click.py` and should be checked with `adk api_server --help`.

#### Exception 2 — `adk-samples/python/agents/software-bug-assistant`. **A partial Class B harness.**

This is the only sample with a genuine relational domain model and documented local setup. Per `python/agents/software-bug-assistant/README.md`:

- A local PostgreSQL instance with a `tickets` table (`ticket_id SERIAL PRIMARY KEY`, title, description, assignee, priority, status) — schema inline in the README around line 212.
- The **MCP Toolbox for Databases** binary (`genai-toolbox` v0.6.0) run as `./toolbox --tools-file="tools.yaml"` from `deployment/mcp-toolbox/`, serving on **`http://127.0.0.1:5000`**, verifiable at `http://localhost:5000/api/toolset` (README line 297).
- `deployment/mcp-toolbox/tools.yaml` defines real domain operations: `get-ticket-by-id`, `get-tickets-by-assignee`, `get-tickets-by-status`, `create-new-ticket`, `update-ticket-priority`, `update-ticket-status`, `search-tickets` (vector; **GCP-only**, disabled locally per README line 266). The local Postgres source config is present but **commented out** in `tools.yaml` and must be uncommented — which would modify a file inside `examples/`, so **copy the tree out before doing this**.

**The honest limitation.** These tools were written by a human in YAML. There is no application layer between the database and the tool definitions — the domain logic *is* the SQL string. So `function2agent` pointed at `software-bug-assistant/` would find ~2 files of agent glue (`software_bug_assistant/agent.py`, `tools/tools.py`) and a YAML file; it would have nothing to derive CRUD tools *from*. This repo validates **"can an agent drive a live HTTP CRUD surface?"** It does **not** validate **"can we synthesize that surface's tools from source?"** Use it as a control harness, not as an end-to-end test.

Also note: the GCP path (Cloud SQL, Vertex AI embeddings, Cloud Run) is the documented happy path; the local path is a partially-supported subset.

#### The other six — weak, and why

| Repo | Class B verdict |
|---|---|
| `codegraph` | **No.** `daemon`/`serve` are stdio MCP. Real SQLite data layer, but no HTTP domain surface. Would need an HTTP shim written specifically for the test — at which point you are testing your shim. |
| `spec-kit` | **No.** CLI that scaffolds files. No server, no persistence beyond the filesystem. |
| `claude-agent-sdk-python` | **No.** Subprocess transport to the `claude` CLI. No service of its own. |
| `claude-cookbooks` | **No**, with a footnote: `claude_agent_sdk/hosting/` and `session_browser_demo/` are the only server-shaped things, and they host *agents*, not a domain application. |
| `adk-docs` | **No.** Static site. |
| `claude-code` | **No.** No source. |
| Other `adk-samples` | **Mostly no.** The 13 `fast_api_app.py` entry points (e.g. `core/python/ambient-expense-agent/expense_agent/fast_api_app.py`, `python/agents/memory-bank/app/fast_api_app.py`, `python/agents/multiformat-hybrid-rag/app/fast_api_app.py`) are almost all thin `get_fast_api_app()` wrappers that serve **the agent**, not a domain API. `multiformat-hybrid-rag/data_ingestion_pipeline/{preprocess,chunk_index}_service/main.py` are the closest to standalone microservices and merit a second look, but both assume GCP. |

### 3.3 The blunt conclusion

**One end-to-end Class B target (`adk-python`), one invoke-only harness (`software-bug-assistant`), six non-targets.** That is enough to run a Class B *feasibility* spike and nowhere near enough to run a Class B *generalization* study. Class B validation beyond the first spike **requires importing external repos** — a Django or Rails or Laravel app with an ORM, migrations, auth, and a real controller layer. Budget for that; do not let `adk-python`'s convenient existence disguise the fact that it is an SDK's control-plane API, not a business application.

---

## 4. Value as a multi-language analysis corpus

### 4.1 The actual language distribution

Aggregated across all eight repos (excluding Markdown, notebook JSON, and the 165,719-line SQL dump):

| Language | LOC | Share | Where it lives |
|---|---:|---:|---|
| Python | 869,181 | 78.4% | `adk-python` (465k), `adk-samples` (172k), `spec-kit` (153k), `claude-agent-sdk-python` (40k), `claude-cookbooks` (25k), `claude-code` (7.6k), `adk-docs` (6.4k) |
| TypeScript + TSX | 180,615 | 16.3% | `codegraph` (135k), `adk-samples` (37k incl. 31k TSX), `adk-docs` (3.9k), `claude-cookbooks` (3.9k) |
| JavaScript | 17,699 | 1.6% | mostly vendored/bundled assets in `adk-python`, `codegraph` |
| Rust | 24,356 | 2.2% | `codegraph/codegraph-kernel/` only |
| Go | 9,435 | 0.9% | `adk-docs/examples/go` (8.7k), `adk-samples/go` (667) |
| Java | 4,193 | 0.4% | `adk-docs/examples/java` (3.7k), `adk-samples/java` (358) |
| Kotlin | 2,635 | 0.2% | `adk-docs/examples/kotlin` (2.0k), `adk-samples/kotlin` (361) |
| Dart / Scala | 558 / 349 | <0.1% | `codegraph` test fixtures only |
| **Total** | **1,109,021** | | 4,420 source files |

**This is a Python corpus with a TypeScript annex.** The "polyglot" characterization in the directive is directionally true but quantitatively thin: Go, Java, and Kotlin together are **1.5% of source LOC**, and most of that is `adk-docs/examples/`, which contains short illustrative snippets rather than structured programs. `adk-samples/go/agents/` holds two agents totalling 667 lines; `adk-samples/java/agents/` holds two totalling 358; `adk-samples/kotlin/agents/` holds one at 361. Those are not stress tests. They are smoke tests, and worth exactly that much.

### 4.2 Coverage against `codegraph`'s capability surface

`codegraph` ships **28 tree-sitter WASM grammars** (`examples/codegraph/src/extraction/wasm/`): arkts, c, c_sharp, cfml, cfquery, cfscript, cobol, cpp, dart, erlang, go, java, javascript, kotlin, lua, luau, nix, pascal, php, python, r, ruby, rust, scala, swift, terraform, tsx, typescript — plus non-tree-sitter extractors for Astro, Vue, Svelte, Razor, Liquid, MyBatis, DFM, and CFML (`src/extraction/*-extractor.ts`).

It also ships **25 framework resolvers** at `examples/codegraph/src/resolution/frameworks/`: `astro`, `cargo-workspace`, `cics`, `csharp`, `drupal`, `expo-modules`, `express`, `fabric`, `go`, `goframe`, `java`, `laravel`, `nestjs`, `play`, `python`, `react`, `react-native`, `ruby`, `rust`, `svelte`, `swift`, `swift-objc`, `terraform`, `vue`.

Cross-referencing against what `examples/` actually contains:

| Grammar / resolver | Exercised by `examples/`? |
|---|---|
| python, typescript, tsx, javascript | **Heavily.** |
| rust | Yes — `codegraph-kernel/` (24k LOC), one real Cargo workspace. |
| terraform | Yes — 91 `.tf` files (`adk-samples` 76, `claude-code` 8, `adk-python` 7). |
| go, java, kotlin | **Barely** — 667 / 358 / 361 LOC of real project code. |
| scala, dart, c, cpp | **Fixtures only** — a handful of files inside `codegraph/__tests__/`. |
| **php / laravel / drupal** | **Not at all.** 2 `.php` files corpus-wide, both fixtures. |
| **ruby** | **Not at all.** 1 `.rb` file. |
| **c_sharp / fabric** | **Not at all.** 3 `.cs` files. |
| **swift / swift-objc / expo-modules** | **Not at all.** 1 `.swift` file. |
| **cobol / cics / pascal / erlang / lua / luau / nix / r / cfml / arkts** | **Not at all.** Zero files. |
| **express / nestjs / react / vue / svelte / astro / goframe / play** | **Not at all** as real applications. `codegraph` has resolvers for these; nothing in `examples/` is an Express or NestJS app. |

**The gap that matters most.** Route→handler extraction is the single most important `codegraph` capability for this product — it is how synthesized tools get their names, paths, and parameters. In `examples/`, that capability is exercised **only against FastAPI (Python)** and marginally against whatever route shapes appear in the 31k lines of TSX in `adk-samples`. The Express, NestJS, Laravel, Rails, Play, and ASP.NET route resolvers — precisely the ones a real customer's web app would need — are **completely untested by this corpus**. That is a load-bearing hole, and closing it requires external repos, not more of `examples/`.

### 4.3 What each repo does uniquely well as an analysis target

Beyond raw language coverage, these repos exercise *distinct analysis capabilities*. Match them deliberately:

| Capability under test | Best target(s) | Why |
|---|---|---|
| **Deep package hierarchy / module boundary inference** | `adk-python/src/google/adk/` | ~20 top-level subpackages (`agents`, `tools`, `sessions`, `memory`, `auth`, `a2a`, `cli`, `flows`, `models`, `artifacts`, …) with clean, intentional layering. If boundary inference cannot recover *something like* this decomposition, the approach is in trouble. This is the corpus's best boundary-inference oracle. |
| **Contract / schema derivation from types** | `adk-python` (200 Pydantic files), `claude-agent-sdk-python/src/claude_agent_sdk/types.py` (2,230 LOC of dataclasses + TypedDicts) | Both are `py.typed` with mypy configured. Ground truth is machine-checkable. `types.py` is small enough to hand-verify a synthesized schema against. |
| **HTTP route → handler extraction** | `adk-python/src/google/adk/cli/api_server.py` | 26 routes, **and the decorators are multi-line** (see `api_server.py:1295-1298`). Naive single-line regex extraction misses them — my own first `grep` did. This is an excellent adversarial case, and `/openapi.json` provides the answer key. |
| **Monorepo / multi-project partitioning** | `adk-samples` | ~45 independent agents across five language trees, each with its own `pyproject.toml`/`package.json`. Tests whether the analyzer produces one giant graph or correctly identifies project boundaries. `codegraph` claims per-`projectPath` MCP support; this is where to verify it. |
| **Cross-language edges** | `codegraph` itself (TS ↔ Rust via the kernel FFI/wire protocol) | The only genuine cross-language call boundary in the corpus. Almost certainly **not** resolvable by tree-sitter static analysis. Worth measuring precisely so the limitation is documented rather than discovered later. |
| **Dynamic dispatch / registry patterns** | `spec-kit/src/specify_cli/` | `presets/__init__.py` (5,638 LOC), `extensions/__init__.py` (4,931), `workflows/engine.py` (1,715) — a plugin/extension/workflow-registry architecture, i.e. exactly the dynamic-dispatch shape where static call graphs break. `codegraph/src/mcp/dynamic-boundaries.ts` claims to *detect* these; `spec-kit` is the place to check whether it does. |
| **Notebook analysis** | `claude-cookbooks` (91 `.ipynb`, 91,407 lines of JSON) | A distinct and commonly-ignored modality. Unverified whether `codegraph` handles `.ipynb` at all — its grammar list does not mention it. Cheap to check, and "we do not support notebooks" is a legitimate documented answer. |
| **Parallel implementations of one design** | `adk-docs/examples/{python,typescript,go,java,kotlin}/` | Five language trees implementing overlapping concepts. Nearly unique as a *controlled* comparison: does the analyzer produce structurally similar graphs for structurally similar programs in different languages? This is the single best multi-language test in the corpus, and it is small enough to inspect by hand. |
| **Prose / config-only repos** | `claude-code`, `adk-docs` | Degenerate cases. What does the tool do when there is almost no code? It should degrade gracefully, not crash or emit a nonsense agent topology. |

### 4.4 Verdict on corpus quality

**As a multi-language analysis corpus: adequate for a first spike, insufficient for a generalization claim.**

- Good: real scale (1.1M LOC), real depth in Python and TypeScript, one high-quality boundary-inference oracle, one controlled five-language comparison, several distinct architectural paradigms (SDK, CLI, plugin registry, monorepo, native-extension hybrid), and zero acquisition cost.
- Bad: 78% Python; the enterprise-relevant languages (C#, Java at scale, PHP, Ruby) are absent or vestigial; **no conventional MVC web application in any language**; no ORM-with-migrations domain model except ADK's own session store; nothing with a meaningful auth or multi-tenancy layer.
- **Required external additions**, in priority order, to make a "any codebase, any language" claim defensible: (1) a Django or Rails app with an ORM and migrations; (2) a Spring Boot or ASP.NET service — enterprise Java/C# is where the money is and where the corpus is emptiest; (3) an Express or NestJS API, since `codegraph` has resolvers for both and neither is exercised; (4) a large C/C++ codebase, to test the scale claim from `06-examples-inventory.md` (Linux kernel, 70k files) rather than trusting it.

---

## 5. `codegraph` self-analysis as the first smoke test

### 5.1 Why this is the right first move

It is the cheapest possible end-to-end exercise of the analysis layer. No agent needs to exist. No LLM tokens are spent. No API keys, no cloud project, no Postgres. The only prerequisite is Node ≥20 <25 and `npm ci && npm run build` inside a **copy** of `codegraph`. And it directly tests the load-bearing assumption of the whole product.

**The prior from `06-examples-inventory.md`** (verdict quoted, not re-derived):

> **codegraph** — `v1.5.0-7-g49c11fc` (2026-08-01), MIT — **"Adopt as analysis foundation — with a mandatory 'architecture inference' layer built on top."**
>
> "…a genuinely strong, MIT-licensed, tree-sitter-based, 29-language symbol graph with framework-aware **route→handler** extraction, an incremental sync path, a SQLite store, and a first-class programmatic API. It scales (claimed: Linux kernel, 70k files / 2M symbols / 6.4M edges, <12 min on a 2-core VPS). **But it has no concept of architectural layers, domains, modules, or bounded contexts.** Its graph is symbol-level. Deriving agent boundaries from it is a *build*, not a *configure*."

That verdict was reached by reading the code. The smoke test's job is to **verify it by running it** — and specifically to quantify the gap between "symbol graph" and "agent boundaries," because the size of that gap is the size of a work item nobody has scoped yet. Note the count discrepancy worth resolving in passing: `06` says 29 languages; I count **28 `.wasm` grammars** plus separate non-tree-sitter extractors, so the difference is probably a definitional one.

### 5.2 The concrete procedure

Copy the eight repos to a scratch directory (`examples/` stays read-only; `codegraph init` writes a `.codegraph/` directory into the target, which would violate that constraint). Then, per repo:

```bash
/usr/bin/time -l codegraph init  <repo> 
/usr/bin/time -l codegraph index <repo> --json  | tee idx-<repo>.json
codegraph status <repo> --json                  | tee status-<repo>.json
codegraph files  <repo> --json                  | tee files-<repo>.json
```

Then a fixed query battery per repo, so results are comparable run to run:

```bash
codegraph query  "<known-symbol>"  --json
codegraph callers  "<known-symbol>" --json
codegraph callees  "<known-symbol>" --json
codegraph impact   "<known-symbol>" --json
codegraph affected <known-file>     --json
```

(Command names verified from `examples/codegraph/src/bin/codegraph.ts`: `init`, `index`, `sync`, `status`, `query`, `explore`, `node`, `files`, `callers`, `callees`, `impact`, `affected`, `daemon`, `serve`. `--json` availability per command is documented in `06`.)

Seed symbols with known ground truth, one per repo:

| Repo | Seed symbol / file | Why it is a good probe |
|---|---|---|
| `adk-python` | `get_fast_api_app` (`src/google/adk/cli/fast_api.py:404`) | Three same-named definitions exist (`fast_api.py:404`, `dev_server.py:1397`, `api_server.py:987`). Tests name disambiguation, which is where symbol resolution usually fails. |
| `adk-python` | `src/google/adk/cli/api_server.py` | The 26-route ground truth. |
| `codegraph` | `CodeGraph` (`src/index.ts`) | ~70 public methods; a fan-out stress case. |
| `spec-kit` | `src/specify_cli/workflows/engine.py` | Dynamic dispatch — expect the graph to break here, and check whether `dynamic-boundaries.ts` says so honestly. |
| `claude-agent-sdk-python` | `ClaudeAgentOptions` (`src/claude_agent_sdk/types.py`) | Small, fully typed, hand-verifiable. |
| `adk-samples` | whole tree | Partitioning behaviour across ~45 subprojects. |
| `adk-docs` | `examples/{go,java,kotlin,typescript,python}/` | Cross-language structural comparison. |
| `claude-code` | whole tree | Degenerate near-empty case. |

### 5.3 What to measure

**Coverage.** Files discovered vs. `find`-counted source files (numbers in §2 are the denominator). Report per language. Any language where coverage is <90% is a bug or an unsupported extension — determine which. Watch specifically for `.ipynb` (`claude-cookbooks`), `.astro`/`.vue`/`.svelte`, and the 165,719-line SQL file, which is a fine candidate for an OOM or a pathological parse.

**Symbol resolution rate.** Of extracted call/reference edges, what fraction resolve to a defined symbol vs. dangle? This is the headline metric — an unresolved-edge rate above ~30% in a fully-typed Python package like `adk-python` would seriously undermine "derive tools from static analysis." Compute per language; expect Python and TypeScript to do well and everything else to be worse.

**Cross-file and cross-language edges.** Count both. Cross-file edge density is the raw material for boundary inference — a graph that is 95% intra-file has nothing to cluster on. Cross-language edges are almost certainly ~0 (TS↔Rust in `codegraph`, Python↔TSX in `adk-samples`); confirm and document that rather than assuming it.

**Route extraction fidelity — the highest-value single measurement.** Compare `codegraph`'s route→handler output for `adk-python/src/google/adk/cli/api_server.py` against the 26 routes enumerated in §3.2. **Every one of them uses a multi-line decorator** (`api_server.py:1295-1298`), so this is a real test, not a gimme. Score precision and recall on (method, path template, handler symbol). Then repeat against the live server's `/openapi.json` once §3.2's Class B setup is running, which upgrades the answer key from hand-counted to authoritative.

**Runtime and resource use.** Wall clock and peak RSS per repo, and derived LOC/sec and files/sec. Cross-check against the claimed Linux-kernel throughput. `adk-python` at 2,353 files is the largest single repo here and is ~3% of the claimed 70k-file benchmark; if it does not finish in well under a minute, the scale claim needs re-examination.

**Failure modes.** Log every crash, timeout, silently-skipped file, and `language: unknown` classification. Categorize: unsupported extension, parse error, size limit, encoding. The `unknown` bucket size is a direct measure of how far "any language" actually reaches.

**Incrementality.** Run `codegraph sync` after touching one file in the scratch copy. Time it. Incremental sync is what makes the knowledge layer viable while generated agents are editing code; if a one-file change triggers a multi-minute reindex, that is an architectural problem, not a tuning issue.

### 5.4 Pass / fail criteria

**`codegraph` is a viable foundation if:**
- ≥95% file coverage on Python and TypeScript; ≥80% on Go/Java/Kotlin.
- Symbol resolution ≥70% on `adk-python` and `codegraph` (the two strictly-typed repos).
- Route extraction on `api_server.py` at ≥80% recall against the 26 known routes, with correct path templates — **partial credit here is genuinely fine**, because a documented, systematic miss (e.g. "multi-line decorators are dropped") is a fixable upstream contribution under MIT.
- `adk-python` (2,353 files) indexes in <120s on a laptop.
- `codegraph sync` after a one-file edit completes in <5s.
- Zero crashes; unsupported files skipped with a diagnostic rather than a stack trace.

**`codegraph` is not a viable foundation if:**
- Symbol resolution is under ~50% on typed Python — that would mean tool synthesis has to be LLM-driven, which changes the product's unit economics fundamentally (`06`'s core economic argument is that analysis is a *deterministic local pass*).
- Route extraction misses most of the 26 routes **and** the cause is architectural rather than a fixable regex.
- Indexing `adk-python` takes minutes, or memory scales badly enough to rule out large repos.
- The graph turns out to be so intra-file dominated that no meaningful module clustering is possible.

**Expected outcome, stated in advance so the test can surprise us:** coverage and runtime pass comfortably; symbol resolution is good in Python and TypeScript and mediocre elsewhere; route extraction is partial; **and the real finding is the one `06` already predicted — the graph is symbol-level with no architectural layer, so boundary inference is net-new work.** The value of running the test is *quantifying* that gap. If the smoke test merely confirms `06`'s read of the code, it still paid for itself by converting a code-reading judgement into a number.

---

## 6. Value as reference implementations

These are the highest-leverage reads during the spike. The point of this section is that a future engineer should not have to rediscover them. Paths are relative to `examples/`.

### 6.1 Tool suites, permissions, and subagents — `claude-agent-sdk-python`

The single most useful file in the corpus for the agent-runtime design is **`claude-agent-sdk-python/src/claude_agent_sdk/types.py`** (2,230 LOC). It is a complete, typed specification of an agent harness's surface area. Verified line references:

| Concern | Location |
|---|---|
| Programmatic subagent definitions | `types.py:84` — `class AgentDefinition`. Per-agent `tools`, `model`, and `permissionMode` (`:102`). Passed as `ClaudeAgentOptions.agents: dict[str, AgentDefinition]`, so a decomposition computed from a code graph can be handed over as data — no source generation. |
| Permission model | `types.py:25` — `PermissionMode` literal; `:235` `PermissionResultAllow`; `:244` `PermissionResultDeny`; the `can_use_tool` callback contract documented at `:210`. Note `:1669` and `:1696-1720`, which handle the footgun where `permission_mode` silently shadows `can_use_tool` — read this before designing your own permission layer, because it is exactly the mistake you would otherwise make. |
| Hooks | `types.py:586` — `class HookMatcher`. Worked example: `examples/hooks.py`. |
| MCP server configuration | `types.py:603-741` — `McpStdioServerConfig`, `McpSSEServerConfig`, `McpSdkServerConfig`, plus status/health types (`McpServerStatus`, `McpStatusResponse`). Directly relevant to `09-mcp-as-tool-surface.md`. |
| Runtime-synthesized tools | The `@tool(name, description, schema)` decorator takes the schema **as an argument, not from the signature** — per `06-examples-inventory.md`, this is what makes it possible to build tools from a computed schema without `exec`-ing generated Python. This is the key mechanism for tool synthesis. |
| Transport / session lifecycle | `_internal/transport/subprocess_cli.py` (1,069), `_internal/sessions.py` (1,925), `_internal/query.py` (1,034), `_internal/session_resume.py` (536) |
| Conformance-test pattern | `testing/session_store_conformance.py` (327) — a reusable conformance suite shipped *as library code* so third-party implementations can self-verify. Steal this pattern for any pluggable interface in `function2agent`. |

`claude-agent-sdk-python/examples/` is 18 short, runnable files covering exactly the questions that come up: `agents.py` (subagents), `tool_permission_callback.py`, `hooks.py`, `mcp_calculator.py` (in-process MCP), `tools_option.py`, `session_stores/`, `max_budget_usd.py` (cost caps), `streaming_mode*.py`. **Read this directory before writing any harness code.** It is 3,367 lines total and will save days.

### 6.2 The target artifact, hand-written — `claude-code`

`claude-code` has no product source, but it contains hand-authored versions of the thing `function2agent` must generate mechanically. Read them as prior art on scope discipline and inter-agent handoff:

- **`claude-code/plugins/feature-dev/agents/`** — `code-architect.md`, `code-explorer.md`, `code-reviewer.md`. A three-agent decomposition of a feature-development workflow, hand-tuned. If your generated topology for a Class A task looks nothing like this, ask why.
- **`claude-code/plugins/pr-review-toolkit/agents/`** — six specialists: `code-reviewer`, `code-simplifier`, `comment-analyzer`, `pr-test-analyzer`, `silent-failure-hunter`, `type-design-analyzer`. The most interesting data point in the corpus about **how narrow a useful subagent's remit actually is.** These are not "backend agent" / "frontend agent"; they are single-concern reviewers. That is a strong prior for boundary granularity, and it argues against the intuitive file-tree-shaped decomposition.
- **`claude-code/examples/hooks/bash_command_validator_example.py`** — a concrete pre-execution command validator; the smallest real example of a safety gate.
- **`claude-code/.claude-plugin/marketplace.json`** and each plugin's `.claude-plugin/` — the packaging/manifest format for a bundle of agents, commands, skills, and hooks. If `function2agent` emits an installable artifact, this is a shipped format worth conforming to rather than inventing around.
- **License caution:** `06-examples-inventory.md` records this repo as **proprietary — "REFERENCE ONLY."** Read for structure and approach; **do not copy prompt text.**

### 6.3 Programmatic agent construction and HTTP serving — `adk-python`

| Question | Read |
|---|---|
| How do I serve agents over HTTP/SSE? | `src/google/adk/cli/fast_api.py:404` (`get_fast_api_app`), `src/google/adk/cli/api_server.py` (the 26-route production surface), `src/google/adk/cli/dev_server.py` (37 more, dev-only). The product's "HTTP/SSE or iframe" requirement has a working reference here — including `POST /run_sse` at `api_server.py:1733`. |
| How do I turn an OpenAPI spec into tools? | `src/google/adk/tools/openapi_tool/openapi_spec_parser/openapi_toolset.py:46` and `rest_api_tool.py`. Per `06`, this is the direct bridge from "the target app has an HTTP API" to "the agent has tools" — the single most product-relevant module in ADK, and the one that makes Class B cheap if you adopt ADK. |
| How do I consume an MCP server as tools? | `src/google/adk/tools/mcp_tool/mcp_toolset.py` |
| What does a session/memory/artifact service interface look like? | `src/google/adk/sessions/base_session_service.py` and the four implementations beside it; `src/google/adk/artifacts/`; `src/google/adk/memory/`. Note `sessions/migration/` — someone thought about schema evolution, which the knowledge layer will also need. |
| How do agents get built as data rather than code? | Pydantic models throughout; 200 files reference `BaseModel`. Per `06`, a workflow is constructible as a Python dict → validate → instantiate, with no source emission. |
| Deployment packaging | `src/google/adk/cli/cli_deploy.py` |
| Agent-to-agent protocol | `src/google/adk/a2a/utils/agent_to_a2a.py` |

### 6.4 Concrete orchestration patterns — `claude-cookbooks`

- **`claude-cookbooks/patterns/agents/`** — `basic_workflows.ipynb`, `orchestrator_workers.ipynb`, `evaluator_optimizer.ipynb`, `async_multi_agent_orchestration.ipynb`, plus `prompts/` and `util.py`. These are the canonical named topologies in executable form. Cross-reference against `03-graph-and-loop-architecture.md` and whatever `10-topology-in-practice.md` concludes.
- **`claude-cookbooks/claude_agent_sdk/`** — eight worked agents: `00_The_one_liner_research_agent`, `01_The_chief_of_staff_agent`, `02_The_observability_agent`, `03_The_site_reliability_agent`, `04_migrating_from_openai_agents_sdk`, `05_Building_a_session_browser`, `06_The_vulnerability_detection_agent`, `07_Hosting_the_agent`. Notebook 01 (`chief_of_staff_agent/`) is a multi-agent decomposition worth reading closely; notebook 07 plus `hosting/` is the serving reference (`06` flags `hosting/` as copy-able scaffolding).
- **`claude-cookbooks/tool_use/`** — `automatic-context-compaction.ipynb`, `memory_tool.py`/`memory_cookbook.ipynb`, `parallel_tools.ipynb`, `programmatic_tool_calling_ptc.ipynb`, `tool_choice.ipynb`, `context_engineering/`. The memory and compaction material maps directly onto the product's "knowledge/memory layer," and onto the `context-engineering` skill.
- **`claude-cookbooks/tool_evaluation/`** and **`evals/`** — how to evaluate a tool suite. Read these before designing acceptance criteria for synthesized tools; feeds `11-validation-plan.md`.

### 6.5 Analysis substrate — `codegraph`

- **`src/mcp/tools.ts`** — the 8 exposed MCP tools. A worked example of a *good* small tool suite over a graph, and a useful calibration point for the `agent-tool-design` skill's tool-count guidance.
- **`src/resolution/frameworks/`** — 25 resolvers. Read `express.ts`, `python.ts`, and `laravel.ts` to understand how route→handler extraction is actually implemented, because you will be extending this.
- **`src/db/schema.sql`** — ~~four tables~~ **twelve tables**. Per `06`, the SQLite file is the most important extension point for a polyglot product: queryable from Python, Go, anything. **Design against the schema, not the TypeScript API.** **Struck 2026-08-10, and the "Per `06`" survives the correction because it was accurate: `06`'s codegraph extension-points table says "Four tables" itself, so this is an inherited figure and not a compression introduced here. Measured from the 194-line file: 7 ordinary tables, `nodes_fts`, and the 4 shadow tables its FTS5 declaration materialises — 12 in `sqlite_master` — with 20 indexes and 3 triggers, 35 objects, all of them in the digest `src/analysis/codegraph_pin.py` pins. D-14 does not move: designing against the schema rests on the file being documented and language-neutral, not on its width, and a reader sizing that work should size it against 7 tables they will actually query rather than against either published count.**
- **`src/mcp/dynamic-boundaries.ts`** — detects where static call graphs break (`handlers['save']`, `getattr`, reflection, message buses). `06` correctly notes the name is misleading — it is not architectural decomposition — but generated agents will hit exactly these walls, so the honest "the static path ends here" reporting pattern is worth adopting.

### 6.6 Process, not product — `spec-kit`

`06` records the verdict **"ADOPT AS PROCESS. Do not expect it to be part of the product."** The relevant reads are the templates under `.specify/templates/` and the workflow engine at `src/specify_cli/workflows/engine.py`. Its second and less obvious value is as an **analysis target** (§4.3): its plugin/preset/extension registry architecture is the corpus's best dynamic-dispatch stress case.

---

## 7. Dogfooding

### 7.1 The case for it

`function2agent` will be a real codebase — most likely TypeScript and/or Python, with a `codegraph`-derived analysis layer, an agent runtime, and an HTTP/SSE server. Pointing the tool at itself is worth doing for reasons that are mostly about feedback speed, not about proof:

1. **Fastest possible loop.** The person who breaks boundary inference finds out on the next commit, on a codebase whose correct decomposition they hold in their head. No other target has that property.
2. **Free correctness oracle.** You know the right answer for your own repo. Every other target requires constructing ground truth by hand.
3. **It exercises incremental sync under realistic churn.** A repo under active development is the only honest test of `codegraph sync` — synthetic edits do not produce realistic change patterns. If re-indexing after each commit is slow enough to be annoying to *you*, it is slow enough to be disqualifying for a customer.
4. **It forces the degenerate cases early.** An early-stage repo is small, has few tests, has half-built modules and a lot of churn. If the tool only produces a sensible topology for mature codebases, that is a product limitation worth discovering in week two rather than at a customer demo.
5. **`function2agent` will plausibly have an HTTP surface** (the product serves over HTTP/SSE). Once it does, it becomes a modest Class B target for itself — a self-hosting check.

### 7.2 What dogfooding would and would not prove

**Would prove:** that analysis runs end to end on a live, changing repo; that incremental sync is fast enough for interactive use; that the generated topology is *legible* to someone who knows the code — which is the single most important qualitative signal and the hardest to get any other way; that Class A agents can do real work (a generated agent landing a real PR against `function2agent` is a strong, honest demo); and that the tool degrades sanely on a small, immature codebase.

**Would not prove — and this is the part that gets overclaimed:**

- **Nothing about scale.** `function2agent` will be a few tens of thousands of lines for a long time. Scale evidence comes from `adk-python` and, later, external repos.
- **Nothing about language generality.** It is one or two languages, chosen by you, written in your idioms.
- **Nothing about unfamiliar-codebase performance,** which is the actual product. The whole value proposition is comprehension of a codebase nobody on the team wrote. Dogfooding structurally cannot test that, and worse, it *feels* like it does — you will read a mediocre generated topology as correct because you can fill in the gaps from memory. **This is the primary bias risk and it should be stated in the test plan.**
- **Nothing about Class B in a meaningful sense.** Your own control-plane API is not a business application, for the same reason `adk-python`'s is not.
- **It is vulnerable to unconscious accommodation.** Teams that dogfood tend to write code the tool handles well. Guard against this by keeping at least one external target in the continuous-test loop at all times.

### 7.3 Recommended shape

Run it as a **CI job, not a ceremony.** On every push: index `function2agent` plus a fixed rotation of two or three `examples/` repos; emit coverage, symbol-resolution rate, edge counts, and runtime as metrics; **fail the build on regression against a committed baseline, not on absolute thresholds.** Absolute thresholds will be wrong and get muted; deltas stay meaningful. Snapshot the generated topology for `function2agent` and diff it on every run — an unexplained topology change is a signal even when every metric is green.

Keep `examples/` repos in that rotation permanently, precisely to counteract the accommodation bias. A run that is green on `function2agent` and red on `adk-python` is the most informative outcome the loop can produce.

---

## 8. Recommendations by validation stage

**Dependency, stated plainly:** `research/11-validation-plan.md` **does not exist as of 2026-08-02.** The phases below are proposed, not adopted, and **must be reconciled** with `11` once it lands. Where `11` defines different phase names or boundaries, `11` wins.

### Phase 0 — Analysis-layer smoke test (no agent, no LLM)

- Run §5 in full over all eight repos in a scratch copy. This is the gate everything else waits on.
- **Deliverable:** a coverage / resolution / runtime / failure-mode table per repo, plus the route-extraction precision-recall score against the 26 hand-enumerated routes in `adk-python/src/google/adk/cli/api_server.py`.
- **Decision:** adopt `codegraph`, extend it, or replace it. Also produces the first real estimate of the boundary-inference work item that `06` flagged as net-new.

### Phase 1 — Boundary inference (still no agent)

- Primary target **`adk-python/src/google/adk/`**: ~20 intentionally-layered subpackages make it the corpus's best oracle. Score the inferred decomposition against the actual package structure.
- Secondary **`adk-samples`**: does the analyzer correctly split ~45 independent subprojects, or fuse them into one graph?
- Adversarial **`spec-kit`**: registry/plugin dispatch. Expect degradation; measure how it degrades and whether it is reported honestly.
- Degenerate **`claude-code`**, **`adk-docs`**: near-empty and prose-only. Should produce "not enough code," never a crash or a confident nonsense topology.

### Phase 2 — Class A spike (agents operate on the codebase)

- Start with **`claude-agent-sdk-python`** — 11k src / 22k tests, `py.typed`, mypy configured. Small enough to iterate on hourly, typed enough to grade automatically.
- Graduate to **`codegraph`** (strict TS + vitest; a task spanning `src/` and `codegraph-kernel/` tests polyglot Class A) and **`spec-kit`** (98k lines of tests as a verification oracle).
- Verification comes from the repos' own test suites and typecheckers, per the `contract-derived-verification` skill — **not** from model self-assessment. This is the corpus's strongest asset for Class A: four repos with runnable tests and configured typecheckers.
- Read `claude-code/plugins/*/agents/*.md` first as a granularity prior (§6.2).

### Phase 3 — Class B spike (agents operate through the running app)

- **Target: `adk-python` via `adk api_server`** (§3.2). It is the only end-to-end candidate in the corpus.
- Sequence: (1) stand up the server in a scratch copy; (2) capture `/openapi.json` as ground truth; (3) run analysis over `src/google/adk/cli/api_server.py` and synthesize tools; (4) diff synthesized tools against `/openapi.json` on name, method, path, and parameter schema; (5) have an agent perform a real domain task — create a session, write an artifact, list versions, delete the session — and verify by direct DB inspection of the SQLite session store, **not** by asking the agent whether it succeeded.
- **Control:** `adk-samples/python/agents/software-bug-assistant` with local Postgres + MCP Toolbox on `:5000`. This isolates the *invoke* half (its tools are hand-written, so nothing needs to be synthesized). If the agent drives the hand-written toolset well but fails against the synthesized one, the defect is in synthesis, not in the agent loop. That is a genuinely useful A/B and the main reason to bother standing it up.
- **Then stop and import external repos.** Two Class B targets, one of which is an SDK's control plane and the other a hand-written YAML gateway, cannot support a generalization claim.

### Phase 4 — Multi-language generalization

- Use **`adk-docs/examples/{python,typescript,go,java,kotlin}/`** as the controlled comparison: same concepts, five languages, small enough to inspect by hand.
- Use **`adk-samples`** for polyglot-monorepo behaviour.
- **Then import external repos** for the languages the corpus does not cover — PHP, Ruby, C#, Swift, and enterprise-scale Java — and for the framework resolvers (`express`, `nestjs`, `laravel`, `ruby`, `csharp`, `play`) that `codegraph` ships and `examples/` never touches (§4.2). Without this, "any language" is an untested claim.

### Phase 5 — Continuous internal test

- Per §7.3: CI indexes `function2agent` plus a rotating `examples/` subset on every push; regression-vs-baseline gating; topology snapshot diffs.

### Cross-cutting

- **Copy before touching.** Every phase that runs a tool against these repos must operate on a scratch copy. `codegraph init` writes `.codegraph/`; `pip install -e .` writes egg-info; `software-bug-assistant` requires editing `tools.yaml`. All of those violate the read-only constraint on `examples/`.
- **Exclude `adk-samples/python/agents/data-science/flights_dataset/flights_dataset_alloydb.sql`** (165,719 lines) from every statistic, or explicitly justify including it.
- **Separate `src/` from `tests/` in all reporting.** Test code exceeds source code in three of eight repos.

---

## 9. What `examples/` cannot validate

Stated plainly, because this is the caveat most likely to be forgotten once the smoke tests go green:

> **A green run over `examples/` is evidence about the analysis layer on SDK, CLI, and docs repositories. It is not evidence that the product works on a customer's production web application.**

Specifically, `examples/` contains **no instance of any of the following** — each of which is normal in the target market:

1. **A conventional MVC/CRUD web application.** No Django, Rails, Laravel, Spring Boot, ASP.NET, or NestJS app. Not one. The nearest thing is ADK's own control-plane API, which is an SDK's session store, not a business domain.
2. **A domain model with ORM entities and a migration history.** `adk-python/src/google/adk/sessions/migration/` is the only migration directory in the corpus, and it manages an agent-framework's internal schema.
3. **Authentication, authorization, or multi-tenancy in the application layer.** `adk-python/src/google/adk/auth/` handles *outbound* OAuth for tool credentials — the opposite direction from a web app's inbound auth. There is no request-scoped user, no role check, no tenant isolation to reason about. This is a large hole given `08-auth-identity-and-secrets.md`'s scope.
4. **Business logic with real domain invariants.** Nothing in the corpus has the kind of implicit rule — "an order cannot ship before payment clears" — that determines whether a synthesized tool is *safe* to expose. Every domain operation here is CRUD over an agent-runtime record.
5. **A legacy codebase.** Every repo is young, actively maintained, and written in current idioms. No dead code at scale, no vendored third-party trees, no two-generations-of-style layering, no undocumented conventions. Real customer codebases are mostly this, and it is the case most likely to break boundary inference.
6. **Enterprise-language scale.** 4,193 lines of Java and 2,635 of Kotlin corpus-wide, nearly all documentation snippets. A 500k-line Spring monolith is a different problem in kind, not just degree.
7. **PHP, Ruby, C#, Swift.** Zero real code. `codegraph` ships `laravel.ts`, `ruby.ts`, `csharp.ts`, and `swift.ts` resolvers that this corpus cannot exercise at all.
8. **A production database with realistic data volume and shape.** The `software-bug-assistant` local path is a hand-seeded `tickets` table.
9. **Anything about safety or blast radius in production.** No target here can be meaningfully damaged. Every Class B destructive-operation test is against a scratch SQLite file or a local Postgres. That tells you nothing about how a generated agent behaves when a tool actually deletes a customer's record.
10. **Anything about cost or latency at customer scale.** Analysis cost is measurable here; the agent-loop token cost of operating on an unfamiliar 500k-line codebase is not.

**The practical rule:** treat `examples/` results as a **necessary-but-not-sufficient gate.** Failing on `examples/` is decisive evidence of a problem. Passing on `examples/` licenses exactly one claim — "the analysis layer handles well-maintained, mostly-Python SDK repositories" — and no claim at all about the product's actual market. Any go/no-go decision on Class B, on multi-language support, or on production readiness requires external repos that this corpus does not contain.

---

## 10. Open questions and unverified claims

Explicitly flagged so nobody treats these as measured:

| Claim | Status |
|---|---|
| `adk api_server` serves session/artifact CRUD **without** a model API key | **Unverified.** Inferred from the code structure; nothing was executed. Determines whether the Class B spike needs credentials. Check first — it changes the setup cost materially. |
| `adk api_server` flag names (`--port`, positional agents dir) | **Unverified.** Inferred from `cli/cli_tools_click.py`. Confirm with `--help`. |
| The 26/37/5 route counts | **Measured** by counting `@app.*` decorators in `api_server.py` / `dev_server.py` / `fast_api.py`. Not verified against a running server's `/openapi.json` — that comparison *is* the Phase 3 test. |
| `codegraph` handles `.ipynb` | **Unverified and probably no.** Not in the grammar list. Affects `claude-cookbooks` (91 notebooks, 91,407 lines) entirely. |
| `codegraph` supports 28 vs. 29 languages | **Discrepancy.** I count 28 `.wasm` grammars; `06-examples-inventory.md` says 29. Probably definitional (non-tree-sitter extractors counted separately). Minor; resolve during Phase 0. |
| LOC figures | **Measured** with `wc -l` — raw physical lines including blanks and comments, overstating logical LOC by roughly 20–30%. `tokei`/`cloc`/`scc` are not installed; install one before publishing any LOC number externally. |
| `codegraph`'s Linux-kernel scale claim (70k files / 2M symbols / 6.4M edges / <12 min) | **Vendor claim, untested.** `adk-python` at 2,353 files is the largest thing here — ~3% of that benchmark. |
| Whether `adk-samples/python/agents/multiformat-hybrid-rag/data_ingestion_pipeline/{preprocess,chunk_index}_service/` are locally runnable standalone microservices | **Unverified.** They are the only other plausible Class B candidates in `adk-samples`; both appear to assume GCP. Worth 30 minutes if a second Class B target is needed. |
| The ninth repository | **Missing.** The directive named nine; eight exist. If a ninth was intended, identify and vendor it deliberately. |
