# E1 — structure recovery: the method, without the numbers

Holds the SQL behind
[`findings/001-structure-recovery.md`](../../findings/001-structure-recovery.md).

> **This harness cannot reproduce a single number in finding 001, and no future
> work will make it able to.** It is committed as an *inspectable method*. Read
> [§Why this is committed anyway](#why-this-is-committed-anyway) before reading
> anything else here, because that reasoning is the only justification for the
> directory existing.

| | |
|---|---|
| Experiment | E1 — route extraction precision |
| Model spend | $0.00 — no model was called |
| Target | a real, private, production monorepo; **not vendored, not copied** |
| Provenance | **recovered from the session transcript 2026-08-02**, not rewritten from the finding |
| Reproducible? | **No.** Method only. |

## Why the numbers are unreproducible

Finding 001 is read-only SQL against a pre-existing `codegraph` index of a
private production monorepo — 4,496 files, 63,783 nodes, 207,722 edges, indexed
about five weeks before the measurement. That repository is deliberately not
vendored and not copied, and the index is a 215 MB artifact belonging to it.

A third party has no target. Every integer in the finding is a property of that
one index at that one moment, so no amount of committed code makes them
checkable by anyone else. This is not a lost-artifact problem of the kind the
three `/tmp`-recovered harnesses had — it is structural, and it does not have a
fix.

Run `./run.sh` against some other codegraph index and every query executes and
returns that index's own numbers. Those numbers are not comparable to finding
001's and must not be quoted against them.

**All nine blocks were executed once, on 2026-08-02, against the `adk-python`
index that [`../recall-adk-fastapi`](../recall-adk-fastapi/) builds** — a Python
repository, not the TypeScript monorepo E1 measured. That establishes exactly
one thing: the SQL is valid against the real `codegraph` schema and returns rows
rather than errors. It establishes nothing about finding 001's numbers, and the
output was not kept. It is worth knowing because a committed query that no
longer parses is worse than no query at all.

## Why this is committed anyway

Because finding 001 contained two overclaims that survived until an unrelated
experiment happened to re-measure them, and **both were visible in the SQL.**

1. **The verb filter.** §1 claims that requiring an HTTP verb "takes precision
   from 74.6% to essentially 100%" and does so with "no per-framework special
   casing." [Finding 004](../../findings/004-recall-against-authoritative-key.md)
   §3 later measured the same filter on a Python FastAPI target, where it
   removed **zero of 41** false positives. The query that produced the original
   claim is `name LIKE 'GET %' OR name LIKE 'POST %' OR …` — a prefix test on a
   node's *name string*. Anyone reading that can see it is a statement about how
   one extractor formats one field: it must be a no-op wherever the extractor
   always emits a verb, and it must misfire on any name beginning with a
   verb-shaped token, which is exactly how 32 `@mock.patch(...)` call sites
   survived it on the Python target.

2. **Handler disambiguation.** §4 sizes "roughly 58% of endpoints reach two or
   more callees" as *the* net-new work item for the analysis layer. Finding 004
   §5 later measured that ambiguity at **zero** on the Python target, because
   that extractor emits a direct route-to-handler edge. The query counts
   `COUNT(DISTINCT e.target)` over `kind='calls'` with no filter on the target at
   all. It is call-graph fan-out, and nothing in it tries to identify a handler.

Neither retraction needed a second experiment. Both needed someone to read the
query. **An inspectable method with unreproducible numbers is strictly better
than neither, and this is the experiment that proves it** — which is how the
open owner call recorded in [`../README.md`](../README.md) was resolved, on
2026-08-02, in favour of committing.

A third overclaim is visible the same way and has *not* been caught elsewhere:
§4's two tables report **71** dead-end endpoints and **60** dead-end endpoints
over the same 866, and the finding reconciles them nowhere. The queries show
why — one restricts callees to `('function','method')` and the other counts any
call target. See [§Discrepancies](#discrepancies-visible-in-the-queries).

## Layout

| File | Purpose |
|---|---|
| `queries.sql` | The nine recovered blocks, annotated with the finding section and reported values each produced. |
| `run.sh` | Executes them against an index you name, opened **read-only**. No default path. |

There is no `results/` directory. Raw output was never captured to a file; the
finding's tables were transcribed from the terminal. Nothing survives that could
honestly be committed as a run record, and against an unreproducible target a
fabricated one would be worse than useless.

## What "recovered" means here

The statements in `queries.sql` are the ones that ran, lifted from the session
transcript. They were not rewritten from the finding's prose, and nothing here
is a reconstruction in the sense that
[`../runtime-provider-agnosticism/count_reasoning_fields.py`](../runtime-provider-agnosticism/count_reasoning_fields.py)
is one.

Two disclosed changes, neither of which alters a query:

| Change | Why | Affects a result? |
|---|---|---|
| Literal subproject directory name → `:subproject`, supplied by `run.sh` | It is an internal directory name inside a private repository. The finding calls it "the largest subproject" and never names it either. | No. Same predicate, operator-supplied. |
| Literal database path → required argument, opened `mode=ro` | It named a path on the author's laptop. | No. |

The transcript also preserves three **failed** first attempts — joins through
`nodes.file_id`/`files.path`, and edge lookups through `edges.source_id` /
`edges.target_id`. Only the corrected forms are committed; the schema those
attempts established is documented at the top of `queries.sql`, because getting
it wrong silently returns an empty result rather than an error.

## Discrepancies visible in the queries

| What | Where |
|---|---|
| **71 vs 60 dead-end endpoints**, same 866 endpoints, unreconciled in the finding. Block 8 counts a callee only if it is a `function` or `method`; block 9 counts any `calls` target. Both tables appear in §4 within a few lines of each other. | `queries.sql` blocks 8 and 9 |
| **The verb filter is a name-string prefix test**, not a property of route extraction. Retracted by finding 004 §3 (C-12). | block 4 |
| **The 58% ambiguity figure counts call-graph fan-out**, with no attempt to identify a handler. Scoped to TypeScript by finding 004 §5 (C-13). | block 9 |

## Gaps — claims in finding 001 that these queries do not produce

Recorded rather than filled. Writing a plausible query for a method that was not
recorded would produce a harness that silently differs from what ran.

| Finding 001 claim | Status | Why |
|---|---|---|
| §2 — "`return_type` is empty across **all 63,783 nodes**" | **Not this query.** | The recovered coverage query (block 6) is scoped to seven node kinds. The six the finding tabulates sum to 28,304 nodes, under half the index; the seventh, `type_alias`, the finding does not report at all. No all-node query was recorded. The claim may well be true; nothing committed here establishes it. |
| §3 — "**211** of 1,161 route nodes have no edges whatsoever" | **Derived, not queried.** | Block 7's third query returns the routes that *do* participate in an edge. 211 is 1,161 minus that. The complement was computed by hand and no query for it was recorded. |
| §Target — "index format v1.1.1, extraction version 24" | **Partial.** | `SELECT * FROM project_metadata` is recovered, but which columns carried those two values was not recorded, so the mapping from output to claim is not committed. |
| §Target — file counts by extension (3,029 `.ts`, 1,032 `.tsx`, 270 `.js`, 152 Python) | **Partial.** | Block 2 groups `files` by `language`, not by extension. Whether the finding's per-extension split came from this query's output or from a second pass is not recorded. |
| §"What this means" 4 — "the target publishes no OpenAPI" | **No query.** | Established by listing the subproject and running `rg -l -i 'openapi\|swagger'` over it. That is a shell recon step against the private tree, not SQL, and it is not committed: it would be a path into the private repository, and against any other target it means nothing. |

## Safety

Every statement is a `SELECT`. `run.sh` opens the index through a
`file:…?mode=ro` URI, so the connection cannot write even if a statement were
wrong. Nothing is written to the index, to the repository it describes, or
anywhere outside stdout.
