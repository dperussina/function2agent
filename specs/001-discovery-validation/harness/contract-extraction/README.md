# Contract-extraction harness — derived contracts vs. a FastAPI application's own OpenAPI schema

Produces the numbers in
[`findings/007-contract-extraction.md`](../../findings/007-contract-extraction.md).

Run `./run.sh` after [`../recall-adk-fastapi/run.sh`](../recall-adk-fastapi/run.sh)
has left a fresh index and an isolated virtualenv in `/tmp/f2a-recall/`. Zero
model spend. Nothing under `examples/` is modified.

**The secondary measurement is skipped unless you supply a target.** Step 4
scores the same signature parser over a TypeScript corpus, and finding 007's
TypeScript column came from a private production monorepo that is not vendored.
`TS_DB` has **no default** — until 2026-08-02 it defaulted to that repository's
index path, which leaked a private filesystem path into this repository for no
reproducibility benefit, since the variable was always overridable. Point it at
a codegraph index of any TypeScript repository to run the step:

```bash
TS_DB=/path/to/.codegraph/codegraph.db ./run.sh
```

The index is opened read-only and only structural columns are touched. Without
it the primary measurement, the ablation, and the Python half of step 4 all
still run; only `sig-typescript.json` is absent.

## What each piece does

| File | Purpose |
|---|---|
| `run.sh` | End-to-end reproduction: derive, score, ablate, then measure the signature-parsing ceiling on both corpora. |
| `build_contract_key.py` | Instantiates the ADK FastAPI application in five configurations and reads `app.openapi()`. For every `(method, path)` it records the operation's inputs — name, location, required, JSON type, with request bodies expanded to their field level — and the declared success-response schema. This is the answer key, and its provenance is **machine-generated**. |
| `extract_contracts.py` | Derives a contract for each endpoint statically. The route-to-handler link comes from the codegraph index; everything after that comes from the repository's own source via Python's `ast` module. Pydantic models are expanded through their base classes, inherited alias generators are applied, and `raise` sites are collected at the handler and one call hop below it. |
| `score_contracts.py` | Scores derived contracts against the key, keeping agreement, disagreement, and absence distinct for each component. Reports the pre-registered ≥ 0.80 gate three ways. |
| `signature_parse.py` | Runs one parser over the `signature` column of both indexes to measure how far signature-string parsing alone gets. This is a capability ceiling, not an accuracy measurement. |
| `contract-key.json` | The committed key. Regenerate with `REBUILD_KEY=1 ./run.sh`. |
| `results/` | Committed outputs, including the per-rule ablation. |

## Ablation

`extract_contracts.py --disable <rule>` switches off one framework-specific
derivation rule at a time so its contribution is measurable:

| Rule | What it does |
|---|---|
| `field_defaults` | Treats `x: str = Field(description=...)` as **required**, because a bare `Field()` assigns something without supplying a default. |
| `complex_is_body` | Binds a complex-annotated parameter to the request body rather than the query string, per FastAPI's scalar-versus-complex rule. |
| `aliases` | Resolves module-level `TypeAlias` declarations before reading a type. |
| `alias_generator` | Applies an `alias_generator` declared on an inherited `model_config` to field names, so the derived names are the wire names. |
| `response_class` | Reads the decorator's `response_class=` as a third return-type declaration site, alongside `response_model=` and the `-> T` annotation. |

Every one of these rules was written after inspecting what the first pass got
wrong on **this** repository. Finding 004 established that a filter discovered
that way can fail completely on the next codebase, so the all-rules-disabled
figure in `results/ablation-stdout.txt` is the more transferable number.

## Ground truth and its limits

OpenAPI is authoritative for parameters and for the declared success response.
**It declares nothing about thrown exceptions**, so the exception component of
the contract has no answer key here and is reported as recoverability only. The
TypeScript corpus has no OpenAPI ground truth at all and its index is roughly
five weeks stale, so its numbers are a capability ceiling and are labelled as
such throughout.

## Prerequisites

`uv` and Python 3.12, plus the virtualenv the recall harness builds. Rebuilding
the key calls Google Cloud metadata endpoints during construction of the
`enterprise` configuration and takes about a minute; it succeeds without valid
credentials.
