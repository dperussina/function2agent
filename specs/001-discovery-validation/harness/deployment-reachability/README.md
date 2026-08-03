# E14 harness — which statically recovered operations a deployment actually serves

Produces the numbers in
[`findings/010-deployment-reachability.md`](../../findings/010-deployment-reachability.md).

Run `./run.sh` and compare what it writes to `/tmp/f2a-recall/e14/` against the copies
committed under `results/`. Zero model spend. Nothing under `examples/` is modified
(FR-018): the target is copied out by the finding 004 harness, which this one reuses.

Thresholds and metric definitions were fixed in
[`PREREGISTRATION.md`](./PREREGISTRATION.md) before any arm was scored, per FR-006.
Read that first — the plan states the gate as a number without stating what the number
is computed over, and that choice decides the verdict.

## What each piece does

| File | Purpose |
|---|---|
| `PREREGISTRATION.md` | Metric definitions, the gate reading, the disposition of unresolvable guards, the seven configurations and why each, the null set, and the kill criteria. Fixed in advance. |
| `run.sh` | End-to-end reproduction. |
| `build_served_key.py` | Ground truth. Instantiates the application in each configuration and reads `(method, path, handler)` off `app.routes`, and separately records what `app.openapi()` publishes. Machine-generated (FR-008); the two are recorded separately because whether they differ is one of the measurements. |
| `static_set.py` | The candidate set **S** (the 69 routes codegraph recovered under `src/`, read from the same E2 index finding 004 scored) and the null set **N** (three synthetic phantoms plus nine real routes belonging to other applications in the repository). |
| `extract_guards.py` | **Arm R1.** Two predictors. `--mode lexical` is R1-naive: enclosing `if` tests within one function, matched to configuration keys by name. The default is R1-tuned: a depth-limited interprocedural concrete-value propagator over `ast`, seeded with the declared configuration, with eight individually switchable mechanisms. Nothing is executed. |
| `probe_runtime.py` | **Arms R2 and R3.** Starts a real uvicorn server per configuration on a loopback port and talks to it over HTTP: `GET /openapi.json` for R2, and a method-mismatch probe per path for R3's precondition. |
| `verify_probe_defects.py` | Confirms the two probe defects directly rather than by inference — the incomplete `Allow` header, and the handler-generated 404 that a routing 404 is indistinguishable from. |
| `config8_environment.py` | Configuration 8, **added after results were visible and labelled as such**. Same declared configuration as `web`, with `python-multipart` made unimportable, so three routes silently do not register. It is the configuration that separates R1 from R2 and R3, and it is reported outside the pre-registered gate. |
| `ablate.sh` | Disables each of R1-tuned's eight mechanisms individually and re-scores, in the form finding 007 §5 used, including the all-disabled figure. |
| `score.py` | Computes served-set precision and recall per arm per configuration, the false-inclusion rate over the null set, OpenAPI coverage of the served set, and the gate verdict. |
| `results/` | Committed outputs. `scores-plus8-stdout.txt` is the summary table; `scores-plus8.json` carries every false positive and every dropped operation individually. |

## R1-tuned's mechanisms

Each is a named capability the propagator needs to evaluate one of the target's gating
predicates, and each can be switched off so its contribution is measurable. Findings 004
and 007 both established that rules discovered by inspecting one codebase's failures
should not be assumed to transfer, and all eight of these were discovered that way.

| Mechanism | What it does | The target's construct that needs it |
|---|---|---|
| `M1_class_dispatch` | Resolves `C = A if cond else B` then `C(...)`, walks the base chain for methods, resolves `super().m()`. | `ServerClass = DevServer if web else ApiServer` |
| `M2_kwarg_flow` | Binds actual arguments to parameters across a call, including `**d` expansion, `d.update(k=v)`, `d.get(k, default)`, and return-value propagation. | `extra_fast_api_args.update(web_assets_dir=...)` then `get_fast_api_app(**extra_fast_api_args)` |
| `M3_attribute_flow` | Carries constructor keyword arguments into `self.attr` reads. | `if self.trigger_sources:` |
| `M4_membership` | Evaluates `"x" in <collection>` element-wise instead of as a truthiness test on the collection. | `if "pubsub" in self._trigger_sources:` |
| `M5_optional_import` | Treats a guard on whether an optional package imports as satisfied when it is importable. | `try: import multipart` — **and see below** |
| `M6_explicit_presence` | Treats an explicitly supplied optional parameter whose value does not evaluate as truthy. **Not sound.** | `if web_assets_dir:`, where the value is a computed `Path` |
| `M7_class_attrs` | Reads class-level assignments through the base chain. | `VALID_TRIGGER_SOURCES = ["pubsub", "eventarc"]` |
| `M8_comprehension` | Evaluates a list or set comprehension over a concrete iterable. | `[s for s in resolved_sources if s in self.VALID_TRIGGER_SOURCES]` |

**`M5` does not work, and the ablation is how that was found.** Disabling it changes
nothing, because the guard it was written for is expressed as `except ImportError:
return` and the propagator does not execute exception handlers, so it never takes the
early return. The consequence is that R1 predicts the three builder routes served
whenever `web` is true, whether or not `python-multipart` is installed. Configuration 8
exists to put a number on that.

## Prerequisites

The finding 004 harness's prerequisites, plus `uvicorn` and `httpx` in the virtualenv
(both are already dependencies of the target). `run.sh` will build the E2 scratch tree
if it is not already there.

The `enterprise` configuration contacts Google Cloud metadata endpoints while the
application is constructed and takes about a minute; it still succeeds without valid
credentials. Every other configuration needs no network beyond loopback.
