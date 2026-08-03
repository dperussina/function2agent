# E15 harness — reachability without a published schema

Measures what survives of [D-18](../../../../research/14-architecture-synthesis.md) when a
deployment publishes no OpenAPI schema, gates it behind authentication, or belongs to a framework
that never had one. Written up as [finding 011](../../findings/011-reachability-without-schema.md).

**Read [`PREREGISTRATION.md`](./PREREGISTRATION.md) first.** It fixes the definitions and
thresholds, and it records four declared departures from `plan.md`'s stated method along with the
reasoning for each. Three of the four widen the measurement; none weakens a gate.

## Reproducing

```bash
ADK_VENV=/tmp/f2a-recall/.venv-adk FIXTURE_VENV=/tmp/f2a-e15/.venv ./run.sh
```

Two environments, deliberately separate: `ADK_VENV` is E14's, with the vendored `adk-python` copy
installed; `FIXTURE_VENV` holds Starlette, Flask, Django and uvicorn. `run.sh` creates the second
if it is absent. **$0.00 in model spend — no model is called.** Nothing under `examples/` is read
or written (FR-018).

## Files

| File | What it does |
|---|---|
| `PREREGISTRATION.md` | Definitions, thresholds, declared departures, and the standard the side-effect claim must meet — all fixed before any configuration was scored. |
| `serve_fastapi.py` | Builds the four FastAPI schema configurations from the read-only vendored target: `web` (`PRESENT`, the positive control), `web_no_schema` (`ABSENT`), `web_schema_401` (`FORBIDDEN`), `web_empty_schema` (`EMPTY`). Also dumps each one's machine-read route table. |
| `fixtures/app_starlette.py` | Plain Starlette. The **control** — isolates whether E14's defects belong to the router or to FastAPI. |
| `fixtures/app_flask.py` | Flask / Werkzeug. First genuinely different router. |
| `fixtures/app_django.py` | Django. The adversarial target: its URL resolver carries no method information, so method dispatch is application code. |
| `fixture_sets.py` | S from fixture source by AST walk, A_c from each framework's own router, N fixed at four per target. |
| `probe.py` | Four-state schema classification, the two probe arms, and handler-invocation detection. |
| `score.py` | Adjudicates both gates, reports the measurements, and derives the post-hoc `P-global+Allow` arm. |
| `results/` | Committed outputs, including a second full run used for the determinism check and `recon.json` from the pre-registration reconnaissance. |

## The three arms, and why there are three

`plan.md` said to reuse E14's probe unchanged. That would have measured a known-defective
instrument, because E14's verb rule is the direct cause of its own handler-invocation defect. So
the probe design is the declared second variable.

| Arm | Probe verb | Provenance |
|---|---|---|
| `P-e14` | the first verb **this operation** does not declare | E14's rule, unchanged, so the numbers stay comparable |
| `P-global` | a verb **no route in the application declares** (`F2APROBE`) | pre-registered |
| `P-global+Allow` | as `P-global`, with the 405's `Allow` header used to reject unlisted methods | **DERIVED, post-hoc, labelled everywhere.** No extra requests. Added once both pre-registered arms turned out to fail for method-level rather than path-level reasons. |

`probe.py` asserts that the globally-unused verb really is unused by the candidate set before it
runs, because `P-global`'s structural argument does not hold otherwise.

## Two things this harness does that the E14 harness could not

**Handler invocation is counted, not inferred.** Every fixture handler prints a line when its body
executes, and each arm runs against its own fresh server process, so attribution is structural
rather than deduced from status codes. An in-band marker request cannot do this — uvicorn at
`--log-level warning` writes no access lines, so there is nothing in the log to split on.

**The detector used on the FastAPI target is validated before it is trusted.** `adk-python`'s
handlers cannot be instrumented (FR-018), so invocation there is detected by two rules: a
*provable* one — under a probe with an undeclared method a router can only answer 404 or 405, so
any other status proves application code ran — and a *calibrated* one, in which each target is
first asked for a path that certainly does not exist and that body becomes the router's own 404
signature. Run against the three fixtures, where the true count is known from the server log, the
pair is **exact on all six framework-arm pairs**. It was not exact on the first attempt: capturing
the signature and the probe response at different truncation lengths made every long HTML 404 body
look handler-generated, which produced four false detections on Flask. That was caught only by the
cross-check.

## Determinism

Gate adjudication and every scored metric are byte-identical across two independent full runs.
Raw probe output is **not**, in two places that do not affect any number: the ephemeral port
recorded in probe URLs, and **the byte order of the `Allow` header**, which Werkzeug and Starlette
both build from a Python `set`. The scorer parses that header into a set. A pipeline that hashed or
string-compared it would see spurious change between processes — worth knowing independently of
this experiment.
