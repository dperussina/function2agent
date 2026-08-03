# E15 reachability without a published schema — pre-registered definitions and thresholds

**Recorded**: 2026-08-02, after reading `plan.md` §E15 and after the reconnaissance recorded in
§"Reconnaissance performed before this document", and **before any configuration was scored**.

**Authority**: FR-006. Nothing below may be revised once results are visible. A revision requires a dated
entry naming what changed and why, and the report must then state both the pre-registered and the revised
number.

**Source of the thresholds**: [`plan.md`](../../plan.md) §"E15 — Reachability without a published schema".
The two gated thresholds are taken as given and are not renegotiated. This document adds **definitions**,
because the plan states thresholds without stating what they are computed over on a target that has no
`codegraph` index, and that choice decides the verdict.

## Departures from the plan's method, declared here rather than discovered later

E15 was written by the propagation pass. Four departures are taken, each because the specified method
cannot answer the question it is asked or cannot be scored as written. All four **widen** the measurement;
none weakens a gate.

| # | The plan says | This harness does | Why |
|---|---|---|---|
| 1 | Configuration 3 is *"a plain Starlette or Flask application"* | **Three** non-FastAPI targets: plain Starlette, Flask, Django | Starlette **is** the router FastAPI sits on, so a plain-Starlette datapoint cannot answer U-37's framework-generality question — it can only re-confirm E14. It is retained as a deliberate **control** proving the defects belong to the router rather than to FastAPI. Reconnaissance showed Flask and Django disagree with Starlette in ways that change the answer, so n=1 would have produced a confidently wrong general claim. |
| 2 | *"Reuse E14's harness unchanged"* and *"add configurations, not arms"* | The path-level probe is scored as **two arms**: `P-e14` (E14's verb rule, unchanged) and `P-global` (a verb unused by the whole application) | E14's rule selects a verb unused by *that operation*, which is the direct cause of defect B and of its recall shortfall. Reusing it unchanged measures a known-defective instrument; replacing it silently would break comparability. Both are scored on every configuration and both are reported. This is a declared second variable, and it is the only way the side-effect question gets answered rather than restated. |
| 3 | Gate 1 is *"path-level served-set precision on every configuration"* | The candidate set for the three non-FastAPI targets is **defined below** | Undefined as written: a hand-written Flask application has no `codegraph` index and therefore no set **S**. The plan states a threshold without stating its denominator, exactly as E14's plan did. |
| 4 | Gate 2 distinguishes *absent* from *forbidden* | **Four** schema states are classified: `PRESENT`, `ABSENT` (404), `FORBIDDEN` (401/403), `EMPTY` (2xx carrying a valid but pathless schema) | `EMPTY` is the dangerous state the plan does not name, because it is a **successful** fetch that means nothing. A pipeline splitting on 2xx-versus-not conflates `EMPTY` with `PRESENT` and emits a catalogue with zero operations while reporting success. Reported against both the plan's three-state reading and this four-state reading. |

A fifth item is a **correction to a register claim rather than a departure**, recorded here so it is dated
before results: D-18 part 3 as propagated says disabling `M1_class_dispatch` *specifically* collapses the
configuration parser. [Finding 010](../../findings/010-deployment-reachability.md)'s ablation table shows
**two** collapse-inducing mechanisms — `off-M1` predicts 0 of 324 and `off-M2_kwarg_flow` predicts 2 of 324,
both at minimum precision 0.0000. The propagation followed that finding's prose, which named only M1,
rather than its table. No new measurement is needed; the existing numbers are re-read.

## Reconnaissance performed before this document

Disclosed because it informed the design above and because a probe design chosen *after* seeing scores
would be worthless. A four-route fixture was implemented three times (Starlette, Flask, Django) and probed
by hand. It established, before anything here was pre-registered:

- E14's verb rule answers **404 with a handler invoked** on Starlette and Flask for a literal path with a
  parameterised sibling.
- A **fabricated verb** (`F2APROBE`) answers **405 with zero handlers invoked** on all three.
- Flask's `Allow` header is the **union** across routes sharing a path; Starlette's is the first matching
  route's only.
- Starlette reported `Allow: GET, HEAD` for a path whose only declared method is `POST`, because a
  parameterised sibling matched first.

None of it is a scored result and none of it is reported as one. The scored measurement re-derives all of it
programmatically. Reconnaissance output is committed at `results/recon.json` for audit.

---

## What is being compared

Five arms. Three are E14's, carried over unchanged so the numbers are directly comparable (FR-004). Two are
new and both are declared above.

| Arm | Mechanism | Needs a schema? | Needs a running process? |
|---|---|---|---|
| **R0** — baseline | Emit every statically recovered operation. | No | No |
| **R1-tuned** — configuration parsing | E14's interprocedural propagator, unchanged. | No | No |
| **R2-openapi** — schema fetch | `GET /openapi.json`, intersected with the candidate set. | **Yes** | Yes |
| **P-e14** — path probe, E14's verb rule | Per candidate path, request it with the first verb **that operation** does not declare; 405 ⇒ routed, 404 ⇒ unrouted. | No | Yes |
| **P-global** — path probe, globally-unused verb | Identical, except the probe verb is one **no route in the application declares**. Default `F2APROBE`. | No | Yes |

`R1-tuned` is scored only on the FastAPI configurations. It is an entry-point-driven analysis of
`adk-python`'s own source, and pointing it at a hand-written Flask application would measure nothing about
either. Its absence on configurations 3–5 is a reported fact, not an omission.

## The measurement

For the three FastAPI configurations, **S** and **N** are E14's, unchanged: 69 statically recovered
`(method, path)` pairs from `src/`, and 12 null operations (3 fabricated, 9 real-but-foreign).

**For the three non-FastAPI targets, fixed here:**

- **S** = every `(method, path)` pair the fixture's source declares, extracted from the fixture module by a
  script rather than transcribed by hand, **including deliberately unserved declarations** so that S ⊋ A_c
  and precision is capable of being less than 1.0. A target where every declared route is served cannot
  falsify anything.
- **N** = 4 fabricated pairs per target, disjoint from S, one of them shaped as a plausible member of a
  real route family.
- **A_c** = read from the framework's own router: `app.routes` for Starlette, `app.url_map` for Flask, the
  resolved URL patterns plus each view's own declared method list for Django. Machine-generated per FR-008.

**Served-set precision** = |P ∩ A_c| / |P|. **Served-set recall** = |P ∩ A_c| / |A_c ∩ (S ∪ N)|, reported
for every arm on every configuration and **not** gated, because an arm can reach precision 1.0 by
discarding real operations and that must not read as free.

**False-inclusion rate over N** is co-primary, per FR-003. Target 0.0000 everywhere.

### Handler invocation is counted, not inferred

Every fixture handler on the three non-FastAPI targets writes a line to stdout when it executes. **Handler
invocations during probing are counted from the server's own log**, not deduced from status codes. This is
the measurement E14 could not make, because `adk-python`'s handlers are not instrumented, and it is the
only way "side-effect-free" becomes a count rather than a claim.

For the FastAPI configurations, where the target is read-only vendored source that must not be modified
(FR-018), handler invocation is detected instead by **response-body discrimination** against the router's
own default 404 body — the mechanism finding 010 §3 verified but did not implement. That is a weaker
instrument and is labelled as one wherever it is used.

## Configurations

| # | Configuration | Schema state | Framework | Why |
|---|---|---|---|---|
| 1 | `web_no_schema` — `web=True, openapi_url=None` | `ABSENT` | FastAPI | The plan's case 1. One constructor argument against E14's configuration 2. |
| 2 | `web_schema_401` — `web=True`, `/openapi.json` and `/docs` behind a middleware answering 401 | `FORBIDDEN` | FastAPI | The plan's case 2. **Implemented as middleware rather than as a route dependency, deliberately**, so the route table is byte-identical to E14's `web` and schema availability is the only variable. It is also the more faithful production shape — an auth proxy in front of the schema. |
| 3 | `starlette_plain` | `ABSENT` | Starlette | **Control.** Isolates whether E14's two defects belong to Starlette's router or to FastAPI. |
| 4 | `flask_plain` | `ABSENT` | Flask / Werkzeug | First genuinely different router. |
| 5 | `django_plain` | `ABSENT` | Django | Second genuinely different router, and structurally the most adversarial: Django's URL resolver carries **no method information at all**, so method dispatch is application code. |
| — | `web` (E14 configuration 2) | `PRESENT` | FastAPI | Re-scored unchanged as the **positive control**, so the schema-free arms are compared against a schema-present baseline measured by the same code in the same run. |
| — | *(reported, not gated)* `EMPTY` state fixture | `EMPTY` | FastAPI | A schema route returning `{"openapi": "3.1.0", "paths": {}}` with status 200, used solely to score the four-state classifier. Not a reachability configuration. |

Configuration 5 carries a deliberately adversarial route that the other four do not: **a Django view that
performs its own method dispatch internally, with no `require_http_methods` decorator.** If a method
mismatch on such a view invokes the handler rather than answering 405, the precondition mechanism is not
merely inaccurate on Django, it is unsafe there, and that is U-37's question stated concretely.

## Gates

| Reading | Threshold | Pre-registered disposition of a miss |
|---|---|---|
| **Schema-free path-level served-set precision, every configuration** | **≥ 0.95** | D-18's fallback ladder does not hold. Adjudicated on **both** probe arms separately; the arm that clears is named, and if only `P-global` clears then the plan's "reuse unchanged" instruction is itself the finding. |
| **Schema state detected and distinguished** | **1.0000, absolute** | A defect to fix, not a result to report. Scored on the plan's three states and on the four including `EMPTY`. |
| Method-level recall, schema-free | **none — measurement** | Reported per framework. No threshold is invented. |
| Contract components retained with the schema removed | **none — measurement** | Reported against finding 007's figures. |
| **Handler invocations during probing** | **none — measurement, and the one to read first** | Counted per arm per configuration. A design with a **structural argument** for zero, confirmed by a count of zero, is reported as *provably free of handler invocation* — and that phrase is chosen carefully, because it is not the same as side-effect-free. See below. |

### What "provably side-effect-free" would require, fixed now so the answer cannot be inflated later

The plan asks whether a probe design exists that is *provably* rather than *probably* side-effect-free.
Three conditions are declared now as the standard that claim must meet.

1. **No handler is invoked.** Provable from the router's dispatch order if the probe verb is declared by no
   route in the application, since a path match with an undeclared method is a partial match in every
   router that separates path matching from method matching.
2. **No middleware with a side effect runs.** **Not provable by any probe design**, because middleware runs
   before routing for every request regardless of method. Audit logging, rate-limit counters, and session
   creation are all ordinary middleware behaviours.
3. **The framework separates path matching from method matching.** Falsifiable per framework, and
   configuration 5 is designed to falsify it.

So the strongest claim available to any network probe is **provably free of handler invocation, subject to a
per-framework check, with middleware as an irreducible residue.** If the measurement supports that, it is
reported in exactly those words and not as "side-effect-free". Recording this in advance is the point: the
weaker claim is the honest one and it must not be upgraded after a clean count.

## Cost ceiling

**$0.00.** No model is called. If any step appears to require one, the run stops and the report says why.

## Kill criteria

- If neither probe arm clears 0.95 on every configuration, D-18 part 1's fallback ladder is wrong and the
  register entry must say so.
- If `P-global` clears everywhere and `P-e14` does not, D-18 part 4 must be amended to specify the verb
  rule, because the mechanism as currently written is the defective one.
- If any framework invokes a handler under `P-global`, the precondition cannot ship unconditionally and the
  finding must say which frameworks it may ship against.
- If the schema-state classifier scores anything below 1.0000, the finding leads with the defect.
