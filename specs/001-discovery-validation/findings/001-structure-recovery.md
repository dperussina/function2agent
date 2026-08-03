# Finding 001 — Structure recovery against a real production monorepo

**Date**: 2026-08-02
**User Story**: 2 (how much structure can be recovered from a codebase)
**Model spend**: $0.00 — no model was called
**Method**: read-only SQL against a pre-existing analysis index. Nothing was written to,
copied from, or modified in the target repository. The queries are committed at
[`harness/structure-recovery/`](../harness/structure-recovery/) — **method only; see
[§Reproduction](#reproduction) for why no number below is checkable by anyone else.**

## Target

A real, private, production monorepo (referenced here as **the target**; not vendored, not copied).
It carries an analysis index built ~5 weeks before this measurement, by the same analysis tool the
project is considering adopting (index format v1.1.1, extraction version 24).

Scale as indexed: **4,496 files, 63,783 nodes, 207,722 edges.**

Language mix, which is the useful part: **96% TypeScript/TSX** (3,029 `.ts` + 1,032 `.tsx` + 270
`.js`) against **152 Python files**. The vendored reference corpus is 78% Python, so this target is
close to its mirror image and covers the gap the vendored material could not.

## What was measured

### 1. Route extraction precision — the headline number

The index contains **1,161 nodes of kind `route`**. Treated naively as "callable endpoints," that
number is wrong by a quarter:

| Category | Count | Share |
|---|---|---|
| Real HTTP endpoints (GET/POST/PUT/PATCH/DELETE) | 866 | **74.6%** |
| Middleware registrations (`USE`) | 137 | 11.8% |
| Verb-less client-side UI routes | 156 | 13.4% |
| Wildcard (`ALL`) | 2 | 0.2% |

**The analysis tool files server HTTP endpoints and client-side router paths under the same node
kind.** In the largest subproject the split is total and unambiguous: its `server/` tree holds 425
route nodes with **zero** verb-less entries, and its client `src/` tree holds 86 route nodes that
are **100%** verb-less — React Router paths like a login screen or an embed viewer. Those are not
callable endpoints, and synthesizing a tool from one produces a tool that cannot be invoked.

**The good news, and it is genuinely good:** the pollution is separable by a trivial rule. Requiring
a verb in {GET, POST, PUT, PATCH, DELETE} removes middleware, wildcards, and UI routes in one pass
and takes precision from **74.6% to essentially 100%** on the question "is this a callable HTTP
endpoint." No model, no heuristics, no per-framework special casing.

> **Correction, 2026-08-02 — the verb filter does not generalize. See
> [finding 004](004-recall-against-authoritative-key.md) §3.**
>
> What was believed: that requiring an HTTP verb is a general, per-language-agnostic post-filter on
> route extraction, since it recovered essentially all of the lost precision here at zero cost.
>
> What is now known: on `google/adk-python`, a 91%-Python FastAPI target, **the verb filter removes
> zero of 41 false positives.** Every one of the 187 route nodes the index holds there already
> carries a verb, because the Python extractor always emits one, so the filter is a no-op. Worse,
> the dominant false-positive class on that target — 32 of the 41 pairs — is
> `@mock.patch("google.adk...")` in test files, which is lexically identical to an HTTP `PATCH` and
> therefore *survives* the filter. A different one-line filter, requiring the path to begin with
> `/`, does work there (precision 0.6273 to 0.8846), but it too was found only after inspecting that
> codebase's failures.
>
> What caused the difference: both filters were derived by looking at one codebase's failure mode
> after seeing it. The verb filter is a property of the TypeScript extractor's output — which mixes
> verb-less React Router paths into the same node kind — not a property of route extraction. This is
> how heuristics that do not transfer get born, and the methodological lesson is that no
> deterministic filter should be written into the product before a second, independent codebase in a
> different language confirms it.
>
> What does transfer: **scoping analysis to the application's own source tree.** That fixed the
> dominant error class on both targets — 74.6% here, and 0.6273 to 1.0000 on the Python target when
> scored inside `src/` — and it is the durable lever the two measurements agree on.

### 2. Contract metadata coverage — the blocking gap

Constitution Principle I requires verifiers derived from signatures, return types, postconditions,
and exception classes. Coverage in the index:

| Node kind | Total | Has signature | Has return type | Has docstring |
|---|---|---|---|---|
| `function` | 17,546 | **17,546 (100%)** | **0 (0%)** | 5,438 (31%) |
| `method` | 4,558 | 4,557 (99.98%) | **0 (0%)** | 2,312 (51%) |
| `route` | 1,161 | **0 (0%)** | **0 (0%)** | **0 (0%)** |
| `interface` | 4,395 | 0 (0%) | 0 (0%) | 1,015 (23%) |
| `class` | 595 | 0 (0%) | 0 (0%) | 89 (15%) |
| `component` | 49 | 49 (100%) | 0 (0%) | 21 (43%) |

Two findings, and the second is the one that matters:

- **Route nodes carry no contract at all.** Zero signatures, zero return types, zero docstrings
  across all 1,161. A route node is `(method, path, file, line)` and nothing else.
- **`return_type` is empty across all 63,783 nodes.** The column exists and is documented as
  populated for receiver-type inference in some languages; for this TypeScript corpus it is
  universally blank. Return types are *partially* recoverable from the `signature` text field, which
  contains strings like `(): Promise<string[]>` and `(run: any): Promise<string>` — but many are
  bare `()` or untyped `(node, value)`, and none is parsed into structure.

### 3. Route-to-handler linkage

There is **no dedicated route→handler edge kind.** Edge kinds are `calls`, `contains`, `references`,
`imports`, `instantiates`, `extends`, `implements`, `decorates`. Routes do participate in edges —
1,995 outgoing `calls`, 144 `references`, 904 incoming `calls` — so the handler body's call graph is
reachable through generic edges.

But **211 of 1,161 route nodes (18.2%) have no edges whatsoever.** For those, the index knows an
endpoint exists and knows nothing else about it.

### 4. The route → handler → signature bridge — sized

Since route nodes carry no contract, the only path to one is to follow `calls` edges from the route
to a handler function and read *its* signature. Measured across all 866 real HTTP endpoints:

| Outcome | Endpoints | Share |
|---|---|---|
| Reaches at least one **typed** handler | **791** | **91.3%** |
| Reaches a handler, but untyped | 4 | 0.5% |
| No handler reachable at all (dead end) | 71 | 8.2% |

So the bridge works far more often than the raw route nodes suggested. **The problem is not reach —
it is ambiguity.** Counting distinct callees per endpoint:

| Callees per endpoint | Endpoints | Share |
|---|---|---|
| 1 — unambiguous | 303 | 35.0% |
| 2–4 | 409 | 47.2% |
| 5–10 | 88 | 10.2% |
| 11+ | 6 | 0.7% |
| 0 — dead end | 60 | 6.9% |

**Roughly 58% of endpoints reach two or more callees**, and nothing in the index says which one is
the handler as opposed to a logger, a validator, a serializer, or a helper. That is the actual work
item: not *reaching* a contract, but *selecting* the right one.

This is a tractable, well-shaped problem — position in the call sequence, argument shape, and
naming conventions are all available signals, and 35% is free — but it is unambiguously net-new
code and it is exactly the layer research predicted we would have to own.

> **Correction, 2026-08-02 — the 58% figure is a TypeScript-path artifact, not a property of the
> task. See [finding 004](004-recall-against-authoritative-key.md) §5.**
>
> What was believed: that handler ambiguity is intrinsic to recovering a contract from a route, and
> that disambiguation is therefore the major net-new work item for the analysis layer.
>
> What is now known: on the Python target the ambiguity is **zero**. All 69 route nodes in `src/`
> reach exactly one callee — no route reaches two or more, and none is a dead end — and the linked
> function matches the framework's own `route.endpoint.__name__` **69 times out of 69**.
>
> What caused the difference: codegraph's Python framework resolver emits a **direct `references`
> edge from the route node to the `def` that follows the decorator**, which is precisely what the
> decorator syntax means. The TypeScript path has no such edge kind and must infer the handler by
> following generic `calls` edges out of the route, which is why it reaches loggers, validators, and
> serializers alongside the handler.
>
> **Scope of this correction.** The 58% figure remains accurate for TypeScript, and until that path
> gains a direct edge the ambiguity there is real and must still be solved. What changes is the
> shape and size of the work item: it is not "disambiguate handlers" in general but **"emit a direct
> route-to-handler edge for every supported framework, the way the Python resolver already does."**
> That is smaller, better-defined, and already demonstrated by the tool itself in one language.

## What this means for the product

1. **Promotion selection is cheaper than expected at the first cut.** The differentiator identified
   in research as the moat — deciding which operations deserve to be tools — gets a meaningful down
   payment from a deterministic verb filter. That is a real, if partial, positive result.

   > **Correction, 2026-08-02 — this conclusion does not hold as stated. See
   > [finding 004](004-recall-against-authoritative-key.md) §3.** The down payment was attributed to
   > the wrong mechanism. The verb filter removed zero of 41 false positives on a Python FastAPI
   > target, so it is not a general cheapening of promotion selection; it is a repair for one
   > extractor's habit of filing client-side router paths under the same node kind as server
   > endpoints. The claim that survives both measurements is narrower: **cheap deterministic
   > post-filters exist and are worth having, but the specific filter is per-language and
   > per-extractor.** The one lever that worked on both codebases is scoping analysis to the
   > application's own source tree. A product that ships one filter as universal will be wrong on the
   > next framework.

2. **The missing semantics are a division of labor, not a defect.** *(Framing corrected by the
   product owner after the first draft of this finding, which wrongly called this a blocking gap.)*
   The intended architecture is explicit: **the analysis tool produces the deterministic structural
   dump, and an LLM — running on the end user's own provider credentials — produces the semantic
   layer** (tool descriptions, instructions, documentation, prompts). Measured against that
   intention, the absence of docstrings and descriptions on route nodes is not a failure. It is the
   correct boundary, and the tool is doing its half well: 4,496 files parsed, 100% signature
   coverage on functions, 866 endpoints enumerated.

   What remains genuinely net-new is narrower than the raw numbers suggested. The bridge to a typed
   handler already works for **91.3%** of real endpoints, so the raw material is present. The build
   is **handler disambiguation** (58% of endpoints reach two or more callees with nothing marking
   which is the handler), signature-string parsing, and a fallback for the 6.9% dead ends.
   Disambiguation is a good LLM task — it is a judgment call with rich local context, and crucially
   its output is **checkable**, since a proposed handler either does or does not match the route's
   position and argument shape.

   > **Correction, 2026-08-02, on two points. See
   > [finding 004](004-recall-against-authoritative-key.md) §5 and §7.**
   >
   > **On disambiguation:** the work item is smaller than sized here, and differently shaped. On the
   > Python target the ambiguity is 0% because the resolver emits a direct route-to-handler edge, so
   > the build is "emit that direct edge for every framework," not "disambiguate handlers." The 58%
   > figure stands for TypeScript and only for TypeScript.
   >
   > **On missing semantics:** the division-of-labor framing holds for *absent* fields and fails for
   > *wrong* ones. Of 10,143 indexed Python functions that genuinely carry a PEP 257 docstring, the
   > index records a docstring for 355, and exactly **one** of those 355 is the real docstring — the
   > extractor reads *above* the `def` and captures comment banners, so `roll_die` is documented as
   > `--- Roll Die Sub-Agent ---`. An LLM asked to supply a missing description knows it is missing.
   > It has no way to know that a plausible-looking populated field is false. Treat the `docstring`
   > field as unusable until fixed, and add field-level validity checks rather than null checks
   > wherever extracted metadata feeds the semantic layer.

5. **The line the LLM must not cross is narrow and specific.** Authoring content — descriptions,
   instructions, documentation, tool naming, consolidation proposals, handler disambiguation — is
   exactly what a model should do here, and requires no apology. But two things must stay outside
   model judgment, per constitution Principle I: **the effect label** that decides whether an
   operation may be invoked without a human (a model confidently mislabeling a delete as read-only
   is a data-loss path, and the bar is ≥0.98 precision), and **the determination that a task
   succeeded**. The workable pattern is model-*proposes*, contract-*disposes*: let the LLM generate
   the label and the description, then verify the label against a derived signal before it is
   allowed to gate anything irreversible.

3. **The adopt/extend/build recommendation is trending toward "extend."** The tool does the
   expensive, boring part well — 4,496 files parsed into a queryable graph with 100% signature
   coverage on functions. What it does not do is exactly the layer research already predicted we
   would own: architectural meaning, effect classification, and contracts.

4. **A verb-only effect proxy will not be good enough.** The target publishes no OpenAPI, so the
   weak HTTP-verb label is the only effect signal available here, and it cannot distinguish a
   reversible write from an irreversible one. Given the ≥0.98 precision bar before automated writes
   are permitted, this is early evidence that the write half needs a real signal, not a verb.

## What this does NOT license

- **Nothing about recall.** This measures the *composition* of what the index found. It does not
  measure what the index **missed**, because the target publishes no OpenAPI or equivalent
  authoritative self-description. Precision without recall is half a measurement, and the missing
  half is the one that hides silent failure.
- **Nothing about languages other than TypeScript.** 96% of this corpus is one language.
- **Nothing about a fresh index.** The index predates the working tree by roughly five weeks, so
  these are properties of a *stale* index. That is itself a drift-detection datapoint, but it means
  none of these counts should be quoted as current.
- **Nothing about the ceiling test.** No agent ran, no task was attempted, no model was called.

## Immediate next steps

1. **Find or build an authoritative answer key** so recall becomes measurable. Options: a subproject
   that publishes OpenAPI, or a live server enumerating its own routes. Without one, User Story 2
   stays half-measured.

   > **Done, 2026-08-02, on a different target.** A FastAPI application was instantiated and its own
   > `app.routes` table read across five constructor configurations, producing a machine-generated
   > key of 77 distinct `(method, path)` pairs. Recall is 0.8961 and precision 1.0000 within the
   > application source tree. See [finding 004](004-recall-against-authoritative-key.md). This does
   > not measure recall on *this* target, which still publishes no authoritative self-description.
2. ~~Test the route → handler → signature bridge~~ — **done, see §4.** 91.3% reach a typed handler;
   the open problem is disambiguating among 2+ callees in 58% of cases. Next concrete step is to
   test whether a deterministic rule (first callee in source order, or argument-shape matching on
   the framework's request/response types) resolves the ambiguity, and measure its accuracy.
3. **Re-index fresh** to separate stale-index artifacts from genuine extraction failures. Requires
   installing the tool and writing to a scratch location outside the target repo.

## Reproduction

> **Added 2026-08-02 — the SQL is now committed, and it still reproduces nothing.**
> [`harness/structure-recovery/`](../harness/structure-recovery/)

**No number in this document is checkable by a third party, and no future work changes
that.** The target is a private production monorepo that is deliberately not vendored and
not copied, and the numbers are properties of one 215 MB index of it at one moment. Point
`run.sh` at a different index and every query runs and returns that index's own numbers,
which are not comparable to these and must not be quoted against them.

The nine query blocks are committed anyway, as an inspectable method. The reason is this
document specifically: **both claims retracted above were legible in the SQL, and neither
retraction needed a second experiment to see.** The verb filter corrected in §1 is
`name LIKE 'GET %' OR name LIKE 'POST %' OR …`, a prefix test on a node's name string —
visibly a statement about how one extractor formats one field rather than a property of
route extraction. The 58% ambiguity figure corrected in §4 is `COUNT(DISTINCT e.target)`
over `kind='calls'` with no filter on the target at all — visibly call-graph fan-out, with
nothing in it that tries to identify a handler. Both survived until
[finding 004](004-recall-against-authoritative-key.md) happened to re-measure them on an
unrelated target. Had the queries been committed here, a reader could have caught both.

Two things the harness surfaces that this document does not resolve:

- **§4 reports 71 dead-end endpoints in one table and 60 in another, over the same 866,
  and reconciles them nowhere.** The queries show why: one restricts callees to
  `('function','method')` and the other counts any `calls` target. Neither figure is
  wrong; the document should have said which question each answers.
- **Five claims here are not fully backed by a recovered query** — §2's "empty across all
  63,783 nodes" (the recovered coverage query spans seven node kinds totalling 28,304),
  §3's 211 edgeless routes (a subtraction, done by hand), §Target's index-version mapping
  and per-extension file split (partially covered), and §"What this means" 4's "publishes
  no OpenAPI" (a `rg` over the private tree, not SQL). The harness README enumerates all
  five under **Gaps**, rather than shipping plausible queries that would silently differ
  from what ran.
