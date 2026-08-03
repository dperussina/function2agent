# Finding 004 — Recall against an authoritative answer key

**Date**: 2026-08-02
**User Story**: 2 (how much structure can be recovered from a codebase)
**Model spend**: $0.00 — no model was called
**Method**: a FastAPI application was instantiated in an isolated virtualenv and its own route
table read directly, producing a machine-generated answer key. The same repository was indexed
fresh by the analysis tool and scored against that key. Both the repository and the tool were
copied out of `examples/` before anything ran; nothing under `examples/` was modified (FR-018).
The harness is committed at
[`harness/recall-adk-fastapi/`](../harness/recall-adk-fastapi/).

## Why this measurement exists

[Finding 001](001-structure-recovery.md) produced a precision number and said plainly that it
could not produce a recall number, because its target published no authoritative self-description:
"Precision without recall is half a measurement, and the missing half is the one that hides silent
failure." This closes that gap. A tool that finds a hundred endpoints perfectly while silently
missing four hundred more looks flawless by precision alone and is useless in the product.

## Target

`google/adk-python` at commit `f4e72334` (2026-07-31, two days before this measurement), vendored
under `examples/adk-python` and copied to scratch before use.

Scale as indexed: **1,867 files, 48,154 nodes, 149,714 edges**, built in 7.8 seconds by codegraph
1.5.0 at extraction version 25. The repository contains 1,709 Python files and 102 JavaScript
files, the latter almost entirely the pre-built Angular assets for the developer UI.

**This target is deliberately the complement of finding 001's, not a confirmation of it.** Finding
001 measured a 4,496-file production monorepo that was 96% TypeScript, using an index five weeks
stale. This is a 1,867-file open-source library that is 91% Python on a Python framework, indexed
fresh. Where the two agree, that is two frameworks agreeing. Where they disagree — and on the
central heuristic they do — the disagreement is the finding.

The reason this repository was chosen is that FastAPI builds its route table from the running
application object. Reading `app.routes` off an instantiated app is not a transcription of what a
human thinks the application serves; it is what the framework will actually dispatch. That
satisfies FR-008 directly.

## The answer key

**Provenance: machine-generated.** No entry was hand-written. `build_key.py` calls
`get_fast_api_app(...)` and walks `app.routes`, recording `(method, path, handler_function_name)`
for every `APIRoute`, `Route`, `WebSocketRoute`, and `Mount` the framework holds. `HEAD` entries
that Starlette adds automatically alongside every `GET` are dropped, because they are not
separately declared operations; nothing else is filtered.

The ADK server registers different route sets depending on its constructor arguments, so five
configurations were enumerated rather than one:

| Configuration | Meaning | Entries |
|---|---|---|
| `api_server` | `adk api_server` — headless API, no developer UI | 27 |
| `web` | `adk web` — the developer UI server | 71 |
| `web_a2a` | developer UI plus the Agent-to-Agent protocol surface | 73 |
| `web_triggers` | developer UI plus Pub/Sub and Eventarc trigger routes | 73 |
| `enterprise` | the Gemini Enterprise / Agent Engine surface | 29 |

**The union is 77 distinct `(method, path)` pairs.** That union is the primary key, because a
static analyzer reading source has no way to know which flags a deployment will pass. Section 4
reports what happens when the key is a single configuration instead, and that number is much less
comfortable.

A minimal fixture agent is committed with the harness. Without an agent directory containing an
`agent.json`, the A2A and Gemini Enterprise code paths register no routes at all, and two whole
cause classes would have gone unobserved.

## 1. Recall is 89.6% against everything the application serves, and 100% against everything its source declares

Scoring the 69 `route` nodes the index holds under `src/` against the 77-pair union key:

| | Count |
|---|---|
| Answer key size | 77 |
| Recovered (true positives) | **69** |
| Missed (false negatives) | **8** |
| Spurious (false positives) | **0** |
| **Precision** | **1.0000** |
| **Recall** | **0.8961** |
| **F1** | **0.9452** |

Every one of the eight misses is a route that **no application source line declares** — the
framework or a third-party library registers it at runtime. Partitioning the key by whether an
`@app.<verb>("...")` decorator exists in the application's own source:

| Key subset | Size | Recovered | Recall |
|---|---|---|---|
| Declared by a verb decorator in application source | 69 | 69 | **100.00%** |
| Registered by the framework or a library at runtime | 8 | 0 | **0.00%** |

**Not one route written by an ADK author in the conventional form was missed.** No multi-line
declaration was missed, even though 44 of the 69 span multiple source lines — the extractor's
regex tolerates newlines between the opening parenthesis and the path literal. No path was
mangled: all 69 recovered paths match the framework's own path string character for character,
including awkward ones like
`/apps/{app_name}/users/{user_id}/sessions/{session_id}/artifacts/{artifact_name:path}/versions/{version_id}/metadata`.

This is a better result than finding 001 gave any reason to expect, and it should be read with
the caveat in section 4 firmly attached.

## 2. The eight false negatives, individually

This list is worth more than the headline percentage, because it is the part that generalizes.

| Missed route | Cause |
|---|---|
| `GET /openapi.json` | Added by FastAPI itself. No source declaration exists anywhere in the repository. |
| `GET /docs` | Same — the Swagger UI page. |
| `GET /docs/oauth2-redirect` | Same. |
| `GET /redoc` | Same — the ReDoc page. |
| `WS /run_live` | Declared as `@app.websocket("/run_live")`. The extractor's verb list is `get|post|put|patch|delete|options|head`; `websocket` is not in it. |
| `MOUNT /dev-ui` | Registered by `app.mount("/dev-ui/", StaticFiles(...))`, a function call rather than a decorator. The extractor only recognizes decorators. |
| `POST /a2a/probe_app` | Registered by the `a2a` library via `_compat.attach_a2a_routes_to_app(app, ..., prefix=f"/a2a/{app_name}")`. Both the registration and the path prefix are computed at runtime, per discovered agent directory. |
| `GET /a2a/probe_app/.well-known/agent-card.json` | Same mechanism. |

Grouped by cause:

| Cause class | Count | Recoverable by better static parsing? |
|---|---|---|
| Framework-generated, no source declaration | 4 | **No.** Requires knowing the framework's own built-in routes. |
| Registered at runtime by a library under a computed prefix | 2 | **No.** Requires executing the application. |
| Registration form the extractor does not recognize (`app.mount`) | 1 | **Yes**, cheaply. |
| Verb the extractor does not know (`websocket`) | 1 | **Yes**, trivially — one token in a regex. |

Two of the eight are one-line fixes to the extractor. Four are a fixed, per-framework list that a
product could ship as data. **Only two require the target application to be running**, and both
belong to the same optional protocol integration.

Notably absent from this list: any miss attributable to a decorator spanning multiple lines, an
unrecognized decorator form on a conventional route, or a router mounted with a path prefix. The
ADK server uses no `APIRouter` and no `include_router`, so the prefix-composition failure mode —
the one most likely to hurt on other codebases — **was not exercised here at all**. That is a gap
in this measurement, not a clean bill of health, and section "What this does NOT license" says so
again.

## 3. Precision is 100% inside the server module and 62.7% across the repository, and finding 001's verb filter does not replicate

The index holds **187 `route` nodes across the whole repository**, collapsing to 110 distinct
`(method, path)` pairs. Scored against the same key:

| Scope | Route nodes | Distinct pairs | TP | FP | Precision | Recall |
|---|---|---|---|---|---|---|
| Whole repository | 187 | 110 | 69 | 41 | **0.6273** | 0.8961 |
| `src/` only | 69 | 69 | 69 | 0 | **1.0000** | 0.8961 |
| `src/google/adk/cli/` only | 69 | 69 | 69 | 0 | **1.0000** | 0.8961 |

The 41 spurious pairs split cleanly into two causes:

- **32 pairs are `@mock.patch("...")` decorators in test files.** All 107 route nodes whose "path"
  does not begin with a slash come from `tests/`, and every one of them is a mock patch target such
  as `PATCH google.adk.telemetry.tracing.tracer` or `PATCH time.time`. The extractor's regex
  `@(\w+)\.(get|post|put|patch|delete|options|head)\(...)` cannot distinguish Python's mocking
  idiom from an HTTP `PATCH` route, because they are lexically identical.
- **9 pairs are genuine HTTP routes belonging to other applications in the repository** —
  demonstration servers under `contributing/samples/integrations/`. These are real endpoints; they
  are simply not endpoints of the application under test.

**Finding 001's verb filter removes zero of the 41.** That heuristic required a method in
{GET, POST, PUT, PATCH, DELETE} and lifted precision on the TypeScript target from 74.6% to
essentially 100%. Here every single one of the 187 route nodes already carries such a verb — the
Python extractor always emits one — so the filter is a no-op, and the dominant false-positive class
masquerades as a legitimate `PATCH`. **The heuristic was an artifact of that codebase's
extractor, not a general property of route extraction.**

A different one-line filter does work here. Requiring the path to begin with `/`:

| Filter | Distinct pairs | TP | FP | Precision | Recall | F1 |
|---|---|---|---|---|---|---|
| None | 110 | 69 | 41 | 0.6273 | 0.8961 | 0.7380 |
| HTTP verb in {GET,POST,PUT,PATCH,DELETE} | 110 | 69 | 41 | 0.6273 | 0.8961 | 0.7380 |
| Path begins with `/` | 78 | 69 | 9 | **0.8846** | 0.8961 | 0.8903 |
| Both | 78 | 69 | 9 | 0.8846 | 0.8961 | 0.8903 |

The honest conclusion is not "use the slash filter instead." It is that **each of these filters was
discovered by looking at one codebase's failure mode after the fact, and neither transfers.** The
generalizable statement is weaker and more useful: cheap deterministic post-filters exist and are
worth having, but the specific filter is per-language and per-extractor, and a product that ships
one filter as universal will be wrong on the next framework. Scoping to the application's own
source tree, by contrast, fixed both codebases' dominant error class at once and is the more
durable lever.

## 4. Configuration blindness is the number that should worry us

Everything above scores against the union of five configurations. Against any single
configuration — which is what a real deployment actually serves — precision collapses:

| Configuration | Key size | Predicted | TP | Precision | Recall | Declared in source but not served |
|---|---|---|---|---|---|---|
| `api_server` | 27 | 69 | 22 | **0.3188** | 0.8148 | 47 |
| `enterprise` | 29 | 69 | 24 | **0.3478** | 0.8276 | 45 |
| `web` | 71 | 69 | 65 | 0.9420 | 0.9155 | 4 |
| `web_a2a` | 73 | 69 | 65 | 0.9420 | 0.8904 | 4 |
| `web_triggers` | 73 | 69 | 67 | **0.9710** | 0.9178 | 2 |

Against `adk api_server`, **47 of the 69 recovered routes do not exist.** They are real lines of
real source, correctly parsed, guarded by `if web:`, `if a2a:`, `if trigger_sources:`, or
`if gemini_enterprise_app_name:`. A tool synthesized from any of them would return 404 against
that deployment and would do so at runtime, in front of a user, not at generation time.

This reframes what the 100% figure in section 1 means. **The tool recovers what the source
declares. It does not recover what a deployment serves, and those are different sets by a factor
of 2.6 in the worst configuration measured here.** The gap is not a parsing defect and no better
parser closes it; it is the difference between static text and runtime configuration.

The product implication is concrete and, as far as I can tell, not yet written down anywhere in
the research corpus: **a generated tool catalog needs a reachability check against the running
target before it is trusted**, or it needs the operator to declare the deployment configuration.
The cheapest version of that check is nearly free on a FastAPI or any OpenAPI-publishing target —
fetch `/openapi.json` and intersect. On targets that publish nothing, it is a real problem and it
is currently unowned.

## 5. Route-to-handler linkage is exact, verified against the framework's own dispatch table

Finding 001 identified handler disambiguation as the open work item: 91.3% of TypeScript endpoints
reached a typed handler, but 58% reached two or more callees with nothing marking which was the
handler. That problem **does not exist on this target**, and the reason is architectural rather
than lucky.

| Measure | Result |
|---|---|
| Route nodes in `src/` | 69 |
| Routes with at least one outgoing edge | 69 (100%) |
| Routes reaching exactly one callee | **69 (100%)** |
| Routes reaching two or more callees | 0 |
| Dead ends (no callee) | 0 |
| Linked handler matches the framework's actual endpoint function | **69 / 69 (100.00%)** |

Ground truth for the last row is `route.endpoint.__name__` read off the instantiated application,
unwrapped through any `functools.wraps` chain. This is not an inspection or a judgment call: the
framework itself names the function it will invoke, and the index named the same function 69 times
out of 69.

The mechanism explains the difference. codegraph's Python framework resolver emits a **direct
`references` edge from the route node to the next `def` following the decorator**, which is
exactly what the decorator syntax means. The TypeScript path in finding 001 had no such edge kind
and had to infer the handler by following generic `calls` edges out of the route, which is why it
found loggers and validators mixed in with handlers. **Handler disambiguation is a problem created
by the extraction strategy for one language family, not an intrinsic property of the task.**

Handler signature quality on those 69 edges:

| | Count | Share |
|---|---|---|
| Handler has a parameter list or return annotation | 66 | 95.7% |
| Handler signature is bare `()` | 3 | 4.3% |
| Signature carries an explicit `->` return type | 56 | 81.2% |

The three bare signatures were checked by hand and are faithful: `get_ui_config`,
`redirect_root_to_dev_ui`, and `redirect_dev_ui_add_slash` genuinely take no arguments and carry no
return annotation. There is nothing there to recover. The `return_type` column remains empty for
all 48,154 nodes, exactly as finding 001 reported on TypeScript, so return types are still only
available as unparsed text inside `signature`.

## 6. Symbol-level recall is 99.87%, and the 22 misses have a single cause worth knowing about

Using Python's own `ast` module over the same repository as ground truth:

| | Count |
|---|---|
| Functions and methods found by `ast` | 16,677 |
| Present in the index | **16,655** |
| Missed | 22 |
| In the index but not in `ast` | 0 |
| **Symbol recall** | **0.9987** |
| **Symbol precision** | **1.0000** |

All 22 misses live in two files: `src/google/adk/a2a/logs/log_utils.py` and
`tests/unittests/a2a/logs/test_log_utils.py`. Neither file produced a single node of any kind.

The cause is that the repository's own `.gitignore` contains `logs/`, intended for runtime log
output, and codegraph applies `.gitignore` patterns as an indexing filter. But **git itself does
not consider those files ignored** — they are tracked, and `git check-ignore` returns nothing for
them, because ignore patterns do not apply to tracked files. So a directory of committed
production source is silently invisible to the analyzer.

This is small here — 22 functions, no routes affected — but the mechanism is exactly the silent
recall loss that finding 001 warned about, and it is one that no amount of parser improvement
detects. Any analysis layer that honors `.gitignore` must reconcile it against tracked-file status,
or it will drop real source with no error and no warning.

## 7. Docstring extraction is not sparse, it is wrong — and this is the worst result here

Finding 001 reported docstring coverage of 31% on TypeScript functions and treated the gap as
acceptable, on the reasoning that the semantic layer is the LLM's job. This target says something
different and worse.

| | Count |
|---|---|
| Python functions with a real PEP 257 docstring (per `ast`) | 10,165 |
| Of those, present in the index | 10,143 |
| Index recorded some docstring for them | **355 (3.50%)** |
| Of those 355, the recorded text is actually the function's docstring | **1 (0.28%)** |

The extractor looks for a docstring **preceding** the definition, which is the JavaScript and Java
convention. Python's docstring is the first statement of the function body. So the field is not
merely empty 96.5% of the time — on the 355 occasions it is populated, it is populated with
whatever comment happened to sit above the `def`. The recorded values are section-divider banners
and stray comments:

```
extract_snippets      -> "Loaded OK, no runnable ADK component found (load-only)"
roll_die              -> "--- Roll Die Sub-Agent ---"
get_next_file_group   -> "=========================================================..."
file_analyzer_instruction -> "=========================================================..."
```

**A blank field is safe; a confidently wrong field is not.** A semantic layer that reads
`node.docstring` to write a tool description would ingest `--- Roll Die Sub-Agent ---` as the
documentation for `roll_die` and would have no signal that anything went wrong. This is the exact
shape of failure constitution Principle IV's fail-loudly requirement exists to prevent, and it
would have been invisible to any measurement that only counted coverage rather than checking
fidelity.

The rest of the contract surface behaves as finding 001 described:

| Node kind | Total | Has signature | Has return type | Has docstring |
|---|---|---|---|---|
| `function` | 13,394 | 13,359 (99.7%) | **0 (0%)** | 518 (3.9%) |
| `method` | 7,810 | 7,782 (99.6%) | **0 (0%)** | 57 (0.7%) |
| `class` | 2,100 | 21 (1.0%) | 0 (0%) | 142 (6.8%) |
| `route` | 187 | **0 (0%)** | **0 (0%)** | **0 (0%)** |

Route nodes carry no contract at all, on Python exactly as on TypeScript. That reproduces.

## 8. Determinism holds

FR-007 requires that a re-run with unchanged inputs produce identical results for measurements
that do not involve a model. Two independent copies of the repository were indexed separately, in
separate directories, and both produced **48,154 nodes and 149,714 edges**. A sorted fingerprint of
every node (`kind|name|file_path|start_line`) was byte-identical across the two indexes — zero
diff lines over 48,154 rows. The full scored result JSON was identical as well.

## What this means for the product

1. **The recall question is answered, and the answer is good on this target.** The tool recovers
   100% of conventionally declared routes and 89.6% of everything the application serves, with
   perfect handler attribution. The eight misses are enumerated by cause, and six of the eight are
   addressable without executing the target. This is the first evidence that the analysis layer
   does not silently lose operations, and it moves the **adopt/extend/build recommendation from
   "trending toward extend" to "extend, with confidence"** — the extraction core is sound enough
   to build on, and the work we own is post-processing rather than replacement.

2. **The disambiguation work item shrank, and the reason matters more than the result.** Finding
   001 sized handler disambiguation as the central net-new build, based on 58% of TypeScript
   endpoints reaching multiple callees. On Python that number is 0%, because the extractor emits a
   direct route-to-handler edge instead of relying on generic call edges. The work item is
   therefore **not "disambiguate handlers" but "emit a direct route-to-handler edge for every
   supported framework, the way the Python resolver already does."** That is a smaller, better-shaped
   task, and it is one the tool's own architecture already demonstrates.

3. **A new gate appeared: configuration reachability.** Static analysis recovers declared routes,
   not served routes, and against a single deployment configuration precision fell as low as 31.9%.
   Nothing in the research corpus addresses this. The product needs either a runtime reachability
   check before a tool is trusted, or an operator-declared configuration, and neither is currently
   scoped. On targets that publish OpenAPI this is nearly free; on targets that do not, it is an
   open problem.

4. **Wrong metadata is a distinct risk class from missing metadata, and we now have a concrete
   instance.** The docstring field is populated with comment banners on Python and there is no
   signal distinguishing that from a real docstring. Any pipeline feeding extracted metadata into a
   semantic layer needs a provenance and validity check on each field, per constitution
   Principle IV, not just a null check. This is cheap to add now and expensive to retrofit.

5. **Heuristics validated on one codebase should be assumed not to transfer.** Finding 001's verb
   filter took precision from 74.6% to ~100% there and does literally nothing here. That is a
   process lesson as much as a technical one: every deterministic filter we adopt needs a second
   independent codebase before it is written into the product, and the corpus needs to span
   languages, not just repositories.

## What this does NOT license

- **Nothing about frameworks other than FastAPI, or languages other than Python.** One repository,
  one framework. Finding 001 covered TypeScript with Express and React Router. Together that is two
  data points, which is enough to show that a heuristic failed to transfer and nowhere near enough
  to characterize a population. Django, Flask, Spring, Rails, Go's `net/http`, and ASP.NET are all
  unmeasured, and codegraph ships resolvers for each of them whose quality is unknown.
- **Nothing about routers with path prefixes.** The ADK server declares every route directly on the
  application object. It uses no `APIRouter`, no `include_router`, and no `add_api_route`. Prefix
  composition is the single most likely source of silent path corruption on other FastAPI
  codebases, and this measurement **did not exercise it once**. A 100% path-accuracy result on a
  repository with no prefixes says nothing about a repository with them.
- **Nothing about dynamically constructed paths.** Every path in this repository is a literal
  string in the decorator. F-strings, module constants, and computed prefixes are all untested, and
  the extractor's regex requires a literal quote immediately after the opening parenthesis, so
  there is reason to expect it fails on all three.
- **Nothing about repository scale.** 1,867 files indexed in 7.8 seconds. Finding 001's target was
  4,496 files. Neither is large.
- **Nothing about the union key being the right key.** Section 4 shows the choice of key changes
  precision from 100% to 31.9%. The union is the defensible choice for scoring a
  configuration-blind tool, but it is a choice, and a reader who cares about a specific deployment
  should read the per-configuration table instead of the headline.
- **Nothing about effect classification.** Verbs were used only to identify routes, never to label
  an operation read-only or destructive. User Story 4 remains unmeasured.
- **Nothing about the ceiling test.** No agent ran, no task was attempted, no model was called.

## Immediate next steps

1. **Add a third target in a third language before trusting any filter.** The verb filter's failure
   to replicate is the strongest signal in this document. A Django or Spring target would test both
   a different resolver and a different declaration idiom, and it costs nothing but time.
2. **Find a FastAPI target that uses `APIRouter` with prefixes and measure path accuracy on it.**
   This is the highest-value untested failure mode and it is cheap: any OpenAPI-publishing FastAPI
   application gives the same machine-generated key for free.
3. **Specify the configuration-reachability check.** Decide whether the product intersects the
   generated catalog against a live `/openapi.json`, requires the operator to declare a
   configuration, or ships tools marked "declared but unverified." This is a new open question, not
   a refinement of an existing one, and it belongs in the decision record as newly opened.
4. **Add field-level validity checks to whatever consumes extracted metadata.** The docstring result
   proves that a populated field is not a trustworthy field. A cheap version — reject a "docstring"
   that is entirely punctuation, or that starts with a comment marker — would have caught 354 of
   the 355 bad values here.
5. **Report the `.gitignore` filtering behavior upstream, and treat it as a requirement for
   whatever we build.** Honoring ignore patterns without checking tracked-file status drops
   committed source silently. Twenty-two functions here; there is no reason to assume that bound
   holds elsewhere.
