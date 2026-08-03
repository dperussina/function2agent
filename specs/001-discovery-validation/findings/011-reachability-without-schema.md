# Finding 011 — Reachability without a published schema

**Experiment**: E15, specified in [`plan.md`](../plan.md) §"E15 — Reachability without a published
schema", pre-registered in
[`harness/reachability-without-schema/PREREGISTRATION.md`](../harness/reachability-without-schema/PREREGISTRATION.md).
**Date**: 2026-08-02. **Model spend**: **$0.00** — no model was called at any point.
**Harness**: [`harness/reachability-without-schema/`](../harness/reachability-without-schema/),
reproducible via `run.sh`, results committed, gate adjudication byte-identical across two
independent full runs.

---

## Gate adjudication, stated before anything else

| Gate | Threshold | Result | Verdict |
|---|---|---|---|
| **Schema state detected and distinguished** | 1.0000, absolute | **7 / 7** on the four-state reading, 7 / 7 on the plan's three-state reading | **CLEARS** |
| **Schema-free path-level served-set precision, every configuration** — arm `P-e14`, the design D-18 currently specifies | ≥ 0.95 | worst **0.8750** | **MISSES** |
| **Same gate, arm `P-global`** — pre-registered probe-design fix | ≥ 0.95 | worst **0.8000** | **MISSES** |
| **Same gate, arm `P-global+Allow`** — derived post-hoc | ≥ 0.95 | worst **1.0000** | **CLEARS**, at a recall cost of 23% |

**Gate 1 misses, and the reason is not the missing schema.** On all four FastAPI configurations —
including the one with no schema and the one with the schema behind a 401 — the schema-free probe
scored **precision 1.0000 and recall 1.0000**, identical to the schema-present control. The gate is
missed on the three non-FastAPI targets, and it is missed because **a path-level probe cannot
discriminate methods**, so it cannot answer an operation-granularity question at all. Every single
false positive across all three arms and all seven targets is a method-level error. There are no
path-level errors anywhere: path-granularity precision is 1.0000 for `P-e14` on all seven targets.

**E14's 1.0000 was a property of the target, not of the mechanism.** `adk-python` contains no path
that serves some methods and withholds others, so an operation-granularity score and a
path-granularity score are the same number there. Add one such path — one route registering `GET`
unconditionally and `POST` behind a configuration flag, which is an ordinary shape — and precision
falls to 0.8000. The mechanism was never measured on the case that breaks it.

**Gate 2 clears, and the state the plan did not name is the one that catches a real pipeline.** All
four states classify correctly. A pipeline that decides schema availability by asking whether the
fetch succeeded — the obvious implementation — is correct on **6 of 7** targets. It fails on
`EMPTY`: a 200 response carrying `{"openapi": "3.1.0", "paths": {}}`. That is a successful fetch
that means nothing, and reading it as `PRESENT` emits a catalogue of zero operations and reports
success. That is the failure mode U-34 predicted, one state further along than it predicted it.

---

## 1. The narrowing survived, and it was right — but it is incomplete in a direction that matters

Finding 010 said that without a schema *"R2 contributes nothing and the fallback is R1-tuned."* The
propagation narrowed that: the path-level probe needs a reachable process, not a schema, so
configuration parsing is the fallback for targets that cannot be **run**, not for targets that
cannot be **introspected**.

**The narrowing is correct and my original sentence was wrong.** Measured directly:

| Configuration | Schema state | `R2-openapi` precision | `R2-openapi` recall | `P-global` precision | `P-global` recall |
|---|---|---|---|---|---|
| `web` (control) | `PRESENT` | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| `web_no_schema` | `ABSENT` | — | **0.0000** | **1.0000** | **1.0000** |
| `web_schema_401` | `FORBIDDEN` | — | **0.0000** | **1.0000** | **1.0000** |
| `web_empty_schema` | `EMPTY` | — | **0.0000** | **1.0000** | **1.0000** |

Removing the schema takes `R2` to zero recall and leaves the schema-free arm **exactly where it
was**. Configuration parsing is not needed for these three populations. The register should carry
the narrowing.

**What the narrowing does not cover, and should.** The path-level probe is only a *filter* on the
static candidate set. The schema is also an *enumerator*: E14 measured 8 of 77 served operations
outside `S`, two of them real `a2a` operations that static analysis missed and that no probe
recovers, because a probe can only ask about paths it was given. So schema-free reachability is
exact about what static analysis proposed and **blind to what static analysis missed**, and the
size of that blindness is unmeasurable without the schema you do not have. Accuracy transfers.
Coverage does not.

**And the cost asymmetry the plan flagged is real and larger than it sounds.** One schema fetch is
**1 request**. The schema-free path is **67 requests** on this target, one per candidate path, each
of which is a method-mismatch probe against a production deployment. That is not merely slower; it
is 67 anomalous requests in the target's access log and error metrics.

---

## 2. The ablation narrowing is wrong, and it is my prose that caused it

D-18 part 3 as propagated says disabling **`M1_class_dispatch` specifically** collapses the
configuration parser. Re-reading finding 010's own committed ablation data:

| Ablation | Operations predicted, all 8 configurations | Min precision | Min recall | Reading |
|---|---|---|---|---|
| none disabled | 324 | 1.0000 | 1.0000 | — |
| **`off-M1_class_dispatch`** | **0** | 0.0000 | 0.0000 | **collapse** |
| **`off-M2_kwarg_flow`** | **2** | 0.0000 | 0.0000 | **collapse** |
| `off-M3_attribute_flow` | 321 | 1.0000 | 0.9565 | survivable |
| `off-M4_membership` | 321 | 1.0000 | 0.9565 | survivable |
| `off-M5_optional_import` | 324 | 1.0000 | 1.0000 | no effect (dead code) |
| `off-M6_explicit_presence` | 312 | 1.0000 | 0.9385 | survivable |
| `off-M7_class_attrs` | 321 | 1.0000 | 0.9565 | survivable |
| `off-M8_comprehension` | 321 | 1.0000 | 0.9565 | survivable |
| all disabled | 0 | 0.0000 | 0.0000 | collapse |

**Two mechanisms are collapse-inducing, not one.** `off-M2_kwarg_flow` predicts 2 operations of 324
at minimum precision 0.0000 — a collapse by any reading. The propagation followed finding 010's
prose, which named only M1, rather than finding 010's table, which shows both. The error is mine
and D-18 part 3 should read "disabling either `M1_class_dispatch` or `M2_kwarg_flow`". No new
measurement was needed; the existing numbers were re-read.

---

## 3. The result that matters most: path-level reachability cannot answer an operation-level question

Every false positive produced by any arm on any target is a method-level error. Listed exhaustively
for the Starlette fixture, and identical in kind on Flask and Django:

| Predicted operation | Path routed? | Operation served? | Why the probe is wrong |
|---|---|---|---|
| `POST /gated` | **yes** — `GET /gated` is served | **no** — `POST` is behind a configuration flag | The probe asked about the path and the path is genuinely routed. Nothing in a 405 distinguishes *this method is not served* from *this method is not served on this path but another is*. |
| `POST /items/f2a-phantom-beta` | **yes** — matches `GET /items/{name}` | **no** | A fabricated null path that happens to be a literal instance of a real parameterised template. The path really is routed. The operation really is not served. |

The second row is the more instructive one, because it is a **null operation that the probe
accepts**, and E14's design would have counted it as a clean 0.0000 false-inclusion rate. Here
`P-global`'s null false-inclusion rate is **0.2500** on all three fixtures.

**`P-e14` scores better on that null, and only because of its defect.** It probes
`/items/f2a-phantom-beta` with `GET`, the sibling `GET /items/{name}` absorbs it, the handler runs,
and the handler returns its own 404 — which the probe reads as "unrouted". It reaches the right
answer by executing application code and misinterpreting the result. Its false-inclusion rate of
0.0000 is not a strength; it is two bugs cancelling.

### The three arms map a trade space in which no point is good at everything

| Arm | Worst operation precision | Worst operation recall | Handler invocations across 7 targets | Gate 1 |
|---|---|---|---|---|
| **`P-e14`** — what D-18 currently specifies | 0.8750 | 0.8750 | **13** | MISSES |
| **`P-global`** | 0.8000 | **1.0000** | **0** | MISSES |
| **`P-global+Allow`** — derived | **1.0000** | 0.7692 | **0** | CLEARS |

`P-global+Allow` clears the precision gate at 1.0000 on every target with zero handler
invocations — by reading the `Allow` header, which **D-18 part 4 explicitly forbids**, and the
forbidding was correct: its recall on FastAPI is 0.7692, silently dropping 15 of 65 real
operations. So the honest summary is that **a schema-free mechanism can be accurate, or complete,
or safe, and you may pick two.** There is no schema-free arm here that is all three.

---

## 4. The non-FastAPI result, and what it does to framework generality

`plan.md` proposed "a plain Starlette or Flask application" as one configuration. Plain Starlette
**is** the router FastAPI sits on, so it can only re-confirm E14; it was retained as a deliberate
control and two genuinely different routers were added. That decision changed the answer, because
the three routers disagree.

### Method mismatch: U-37's question, answered

| Behaviour | Starlette | Flask / Werkzeug | Django |
|---|---|---|---|
| Method mismatch on a routed path | **405** | **405** | **405** — *when the view declares its methods* |
| Method mismatch on a view that dispatches internally | cannot be expressed | cannot be expressed | **the handler runs** |
| E14's verb rule on a literal path with a parameterised sibling | **404, handler invoked** | **404, handler invoked** | 405 |
| Globally-unused verb, same path | 405, no handler | 405, no handler | 405, no handler |

**U-37's specific fear — a framework answering 404 rather than 405 — did not materialise on any of
the three.** All three separate path matching from method matching and all three answer 405. The
precondition mechanism's core assumption holds across three routers.

**A different and worse failure appeared instead, and only Django can express it.** Django's URL
resolver carries **no method information at all**: `path("both", view)` maps a path to one
callable, and method dispatch is application code. A view decorated with `require_http_methods`
answers 405 and the mechanism works. **A view that dispatches internally answers whatever it
likes, and the handler body runs first.** Probing Django's undecorated view with the fabricated
verb returned **400 with the handler executed** — the probe got the correct reachability answer by
running application code. Neither Starlette nor Flask can express this shape, because both default
an undecorated route to `GET` only.

**One structural mitigation, and it is conditional.** That view never entered the candidate set,
because static analysis could not recover its methods either — the AST walk reported
`/anymethod (view anymethod: no method decorator)` as unresolved, so no tool was emitted for it and
the probe never visited it in the scored run. It had to be reached by a **declared adversarial
probe outside the candidate set** to be measured at all. So a *conservative* extractor that drops
what it cannot resolve never probes the unsafe shape. An extractor that guessed `GET, POST` would
probe it, and would invoke the handler. **The safety of the precondition on Django is a property of
the extractor's fail-closed behaviour, not of the probe.** That is a coupling between two
components that were designed independently, and it is not currently written down anywhere.

### `Allow` is wrong on three routers in three different ways

| Router | What `Allow` reports on a 405 | Precision | Recall | Failure mode |
|---|---|---|---|---|
| **Starlette** (plain fixture) | the **first matching route's** methods | 1.0000 | 0.8750 | under-reports; **and the "first match" can be a different path template entirely** |
| **FastAPI** (Starlette router, real target) | as above | 1.0000 | **0.7692** | under-reports on **9 of 51** routed paths; 15 of 65 operations dropped |
| **Flask / Werkzeug** | the **union across all matching rules**, siblings included | **0.8889** | 1.0000 | **over-reports** — attributes a parameterised sibling's methods to a literal path |
| **Django** | the matched view's own declared list | 1.0000 | 1.0000 | correct where declared; **absent where the view does not declare** |

**No router's `Allow` header is the set of methods served on that path template.** Three
implementations, three distinct wrong answers, one of them wrong in the opposite direction from the
others. Reading the header requires knowing which router you are talking to, which is exactly what
you cannot determine from outside.

**A sharpening of E14 defect A.** In the reconnaissance fixture Starlette reported
`Allow: GET, HEAD` for a path whose only declared method is `POST`, because a parameterised sibling
was registered first. Reordering the two registrations changed the header to `POST`. So the
header's correctness is **a function of route registration order**, and the failure is not merely
incompleteness — it can name a different route's methods entirely. E14 recorded this as
under-reporting because on `adk-python` the first partial match happened to be a real route for
that path.

---

## 5. A provably side-effect-free probe: the answer is *almost*, and the residue is not removable

The question was worth more than the gate, so it is answered precisely.

**The design.** Probe every candidate path with a verb **no route in the application declares** — a
fabricated token such as `F2APROBE` rather than a real verb the operation happens not to use. This
is a one-line change from E14's rule and it is the difference between 13 handler invocations and 0.

**What is provable.** In any router that matches path before method, a request whose method no
route declares can only produce a partial match, so the router answers 405 and no handler is
reachable. The harness asserts the precondition — that the verb really is undeclared — before
probing, because the argument is void otherwise. Independently, the status code carries its own
proof: under such a probe **a router can only answer 404 or 405, so any other status is proof that
application code ran.**

**What is measured.** Zero handler invocations under `P-global` on all seven targets, against 13
under `P-e14` — counted from the servers' own logs on the three fixtures, and detected on the four
FastAPI configurations by an instrument first validated to be **exact on all six fixture
framework-arm pairs**.

**Three residues, and the first two are why the claim is *almost*.**

1. **Middleware is irreducible.** Middleware runs before routing for every request regardless of
   method. Audit logging, rate-limit counters, and session creation are ordinary middleware
   behaviours, and no probe design avoids them. This is not a gap in the measurement; it is a
   property of HTTP.
2. **A framework that puts method dispatch in application code breaks the proof.** Django does,
   measured in §4. The precondition on such a framework is safe only because a conservative
   extractor never emits the affected route.
3. **A path parameter can be a resource identifier.** `POST /items/special` probed with `F2APROBE`
   answers 405, but the request still arrived at the deployment carrying a concretised path
   segment. Nothing executes, so nothing is written — but a WAF, a rate limiter, or an audit trail
   sees it.

**So the strongest available claim is the one pre-registered as the standard, and it is not the one
asked for:** *provably free of handler invocation, subject to a per-framework check that the router
separates path matching from method matching, with middleware as an irreducible residue.* That is
strictly stronger than finding 010's "probably side-effect-free" and strictly weaker than
"side-effect-free". **Principle IV forbids unclassified side effects, and middleware execution is
an unclassified side effect this design cannot eliminate.** The constitutional problem is therefore
reduced, not resolved, and the precondition cannot ship as side-effect-free on any framework.

**The subtlest thing found in this experiment.** E14's recall shortfall of 0.9655–0.9701 on the
path-level probe **disappeared here without the defect being fixed.** E14 concretised path
parameters as `__f2a_probe__`, a valid Python identifier, so `adk-python`'s `app_name` validator
accepted it and the absorbed handler proceeded to look for a file and return its own 404 — read as
"unrouted", costing recall. E15 used `f2a-probe`, which the same validator rejects with 400 — read
as "routed", costing nothing. **The same defect, the same two handlers invoked, and an accuracy
metric that moved from 0.9655 to 1.0000 because of a hyphen.** A safety defect was masquerading as
an accuracy metric, and the accuracy metric was sensitive to an incidental harness constant. Any
recall figure for this mechanism should be read as conditional on the sentinel value.

---

## 6. Contracts with the schema removed: the count does not change, and that is the problem

Reported as a measurement, not gated.

Checked against E4's committed harness rather than assumed: **`extract_contracts.py` takes
`--repo`, `--db` and `--out` and accepts no schema input.** The schema was only ever ground truth.
So with the schema absent:

| Component | With schema | Without schema | Change |
|---|---|---|---|
| Endpoints with a derived contract | 60 / 69 (**0.8696**) | 60 / 69 (**0.8696**) | **none** |
| Parameters derived | 207 | 207 | **none** |
| Return types derived | 53 | 53 | **none** |
| Endpoints whose contract can be **validated** | 53 / 69 (**0.7681**) | **0 / 69** | **total loss** |

**Every derived component is retained and nothing can be checked.** The literal reading is
unchanged; the validated reading — finding 007's second row, the one that misses E4's gate at
0.7681 — becomes **uncomputable**. All 69 contracts drop from *agrees with the framework's own
schema* to *unverified*, and the count that a dashboard would show does not move at all.

This is exactly the failure D-17 exists to forbid, and it is worse than a lower number: **the
degradation is invisible in every quantity the pipeline produces.** Finding 007's headline result
was that switching off one derivation rule leaves 15 of 69 endpoints fluent, plausible and wrong
about every field name with nothing in the output indicating it. Removing the schema removes the
only mechanism that would have caught that class of error, and reduces no visible metric. A
catalogue generated against a schema-free target must therefore carry a per-contract
`validated: false`, or the pipeline is asserting agreement with an authority it never consulted.

---

## What this finding does NOT license

- **Four of the seven targets are the same application and the same router.** The three FastAPI
  configurations plus the control differ only in schema availability; they are one datapoint on
  framework generality, not four.
- **The three non-FastAPI targets are fixtures I wrote, not real applications.** They contain 8–10
  served operations against `adk-python`'s 71. They were built to contain specific adversarial
  shapes, and a real Flask or Django application will contain shapes I did not think of. Nothing
  here is a recall or precision estimate for those frameworks in general — it is an existence
  proof about specific route shapes.
- **`POST /gated` decides gate 1, and I chose to include it.** One route shape, deliberately
  added because it is absent from `adk-python`, moves precision from 1.0000 to 0.8000. Its
  *prevalence* in real codebases is unmeasured, so the frequency of the failure is unknown even
  though its existence is now certain. Only one such shape was included, pre-registered as one, to
  avoid manufacturing the verdict.
- **Three routers is not framework generality.** All three are Python WSGI/ASGI. Nothing here
  transfers to Express, Rails, Spring, Go `net/http`, or gRPC, and gRPC has no method-mismatch
  concept at all.
- **Still one process.** U-36 is untouched: every probe reached a single local process with no
  proxy, no gateway, no load balancer, and no replica. A gateway that answers 404 for unknown
  methods before reaching the application would invert every result in §4.
- **Middleware side effects were not measured, only argued.** None of the seven targets runs
  middleware that writes. The claim that middleware is the irreducible residue is structural, not
  observed, and a target with an audit-logging middleware would give it a number.
- **`EMPTY` was produced synthetically.** A route returning a pathless schema was added; no real
  deployment observed doing this. The state is real and the classifier handles it, but its
  prevalence is unmeasured.
- **`openapi_url=None` could not be tested through the target's documented entry point.**
  `get_fast_api_app()` accepts no such argument and forwards no `**kwargs`, so the `ABSENT` state
  was produced by removing the four schema routes from the constructed application. That is
  semantically what FastAPI's own switch does, but it is not the code path an ADK operator would
  execute — and it means **an ADK deployment cannot easily turn its schema off**, which narrows
  U-34's population for this target specifically while leaving it wide for FastAPI generally.

---

## Register entries needing change

| Entry | Current | Should become |
|---|---|---|
| **U-34** — the primary reachability mechanism assumes a schema endpoint production deployments disable | Blocking; three configurations scheduled as E15; asks whether method-level reachability is a schema-only capability and whether contracts degrade visibly | **Resolved on reachability, and it splits into a resolution plus one new blocking entry.** ① **The narrowing this entry already made is confirmed by measurement**: schema-free path-level reachability scored precision 1.0000 and recall 1.0000 on `ABSENT`, `FORBIDDEN` and `EMPTY`, identical to the schema-present control, while `R2` fell to 0.0000 recall. Configuration parsing is **not** the fallback for un-introspectable targets. ② **One thing this entry did not anticipate, and it should carry it: the schema is an *enumerator* as well as a filter.** E14 measured 8 of 77 served operations outside `S`, two of them real; no probe recovers them, and without the schema the size of that blindness is unmeasurable. Accuracy transfers, coverage does not. ③ **Cost is 67 requests against 1**, per deployment, all of them method-mismatch probes visible in the target's logs. ④ **Method-level discrimination is answered, negatively, and it is now U-39 rather than part of this entry.** ⑤ **Contracts are answered and the answer is worse than "degrades silently": nothing degrades at all.** Every derived component is retained; only the ability to validate is lost, taking finding 007's validated reading from 0.7681 to uncomputable while no visible metric moves. Requires a per-contract `validated: false`. ⑥ **The `EMPTY` state must be added to this entry's hazard list.** A pipeline splitting on 2xx is correct on 6 of 7 targets and reads a pathless 200 schema as `PRESENT`. ⑦ For `adk-python` specifically, `get_fast_api_app()` exposes no `openapi_url`, so this deployment cannot easily withhold its schema. |
| **U-37** — the precondition rests on two Starlette properties, one of which means it is not known to be side-effect-free | Blocking on ship; framework generality "measured for free by E15's third configuration"; asks for a body-discrimination fix or an accepted recall loss | **Partly resolved, partly replaced, and the framing was wrong in a way worth recording.** ① **The feared failure did not occur.** Three routers were measured, not one: Starlette (control), Flask/Werkzeug, Django. All three answer **405** for a method mismatch on a declared route. No framework answered 404. ② **Defect A does not generalise, and it fails in *opposite directions*.** Starlette under-reports (recall 0.7692 on the real target, 9 of 51 paths wrong); **Flask over-reports**, attributing a parameterised sibling's methods to a literal path (precision 0.8889); Django is exact where the view declares methods. C-14's rule stands and strengthens: no router's `Allow` is the served method set for that path template. ③ **Defect A is sharper than recorded**: Starlette's header can name a *different route's* methods entirely, and reordering two registrations changes it. Correctness is a function of registration order. ④ **Defect B is solved, and the fix is one line.** A verb no route in the application declares yields **0 handler invocations on all seven targets** against 13 for E14's rule. The body-discrimination fix this entry asked for is **not needed** and should not be built. D-18 part 4 must specify the verb rule. ⑤ **The recall loss this entry asked us to accept or fix does not exist as stated** — it was an artifact of the sentinel value, not the mechanism. E14's 0.9655 became 1.0000 because the concretised segment changed from a valid Python identifier to a hyphenated one, while the same two handlers were invoked either way. **A safety defect was masquerading as an accuracy metric.** ⑥ **A new failure replaces the old one, and it is narrower and worse: `U-40`.** |
| **D-18** — reachability by probing, per configuration, with a precondition on every emitted tool | Part 1 probes `/openapi.json` as primary; part 3 is configuration parsing as fallback, with "predicts zero with them disabled" and the propagated claim that `M1_class_dispatch` specifically collapses it; part 4 forbids reading `Allow` and calls the check *probably* side-effect-free | **Four amendments, one of them a correction to a claim propagation introduced.** ① **Part 1 gains an explicit schema-state precondition.** Classify `/openapi.json` four ways — `PRESENT`, `ABSENT` (404), `FORBIDDEN` (401/403), `EMPTY` (2xx, pathless) — before using it, and never treat any non-`PRESENT` state as "serves nothing". Measured 7/7. ② **Part 3's ablation claim is wrong as propagated and must be corrected: `M1_class_dispatch` *or* `M2_kwarg_flow`, either one.** `off-M2` predicts 2 operations of 324 at precision 0.0000. This came from finding 010's prose naming only M1 while its table showed both; the error is the finding's, not the propagation's. ③ **Part 3's scope narrows**: it is the fallback for targets that cannot be **run**, and specifically *not* for targets that cannot be introspected, which the schema-free arm handles at 1.0000/1.0000. ④ **Part 4 needs three changes.** Specify the probe verb as **one no route in the target declares**, which is what makes the check handler-free. Keep the prohibition on `Allow` — it is now measured wrong in *both* directions across routers. And replace *"probably side-effect-free"* with the strongest supportable claim: ***provably free of handler invocation, subject to a per-framework check that the router separates path matching from method matching, with middleware as an irreducible residue.*** ⑤ **A fourth part-4 constraint is new**: the precondition must not be scored at operation granularity, because a path-level probe cannot answer that question — precision 0.8000 where a path serves some methods and withholds others. Either the precondition is stated as path-level, or it needs a method-level input, and **the only schema-free one available is the `Allow` header that part 4 forbids.** |
| **New: U-39** | — | **NEWLY OPENED — method-level reachability may be a schema-only capability, and the alternative is forbidden.** Path-level probing is exact at path granularity (1.0000 on all seven targets, `P-e14`) and cannot reach 0.95 at operation granularity on a target that gates individual methods on a shared path (0.8000). The only schema-free refinement, the `Allow` header, is exact on Django, under-reports by 23% on FastAPI, and over-reports on Flask. Deriving `P-global+Allow` reaches precision 1.0000 on all seven targets **at recall 0.7692** — 15 of 65 real operations dropped silently, which is precisely why D-18 part 4 forbids the header. **So a schema-free mechanism can be accurate, complete, or safe, and only two at once.** The decision this forces is a product one: either a schema-free catalogue carries paths without verbs, or it carries verbs it cannot verify, or method-level tools require an introspectable target. **Blocking for any promise about emitting verb-bearing tools against a target that publishes no schema.** |
| **New: U-40** | — | **NEWLY OPENED — the precondition's safety on a framework whose method dispatch is application code depends on the static extractor failing closed, and the two components were designed independently.** Django's URL resolver carries no method information, so `require_http_methods` answering 405 is application code, not routing. A view that dispatches internally **executes on a probe with a fabricated verb** — measured: 400 returned, handler invoked. It was safe in the scored run only because static analysis also could not recover its methods, so it never entered the candidate set and was never probed; it required a declared adversarial probe to reach. **An extractor that guessed `GET, POST` for an undecorated view would invoke that handler.** This is a coupling between the extractor's conservatism and the probe's safety that no register entry, decision, or interface records, and it is the kind that is broken by an unrelated recall improvement. Narrower than U-37 and worse: it has a named trigger and a named framework. |
| **C-14** — the same framework's metadata is exact on one question and wrong on the next | Records Starlette's `Allow` as under-reporting by 24–28% while `GET /openapi.json` is exact | **Strengthen with the cross-framework evidence, because the rule is now demonstrated rather than inferred from one case.** Three routers produce three different wrong answers for the same field: Starlette under-reports and can name a *different route's* methods depending on registration order, Flask over-reports by unioning across matching rules, Django is exact only where the view declares. **A framework-served field can be wrong in opposite directions across implementations of the same specification**, which means a correction learned on one router is not merely non-transferable — applying it to another router makes the answer worse. |
| **U-35** — environment blindness | Newly opened, no upper bound | **Unchanged by this experiment, and worth noting explicitly**: E15 varied schema availability and framework, not installed package sets. No new evidence either way. |
| **U-36** — a probe's answer is scoped to the process it reached | Newly opened, unmeasured | **Unchanged and now more load-bearing.** E15 makes the schema-free probe the primary mechanism for three deployment populations, and every number behind it came from a single local process with no proxy or gateway. A gateway answering 404 for unrecognised methods before reaching the application would invert §4 entirely. |
| **Constitution, Principle IV** | Requires every emitted tool classified and enforced; finding 010 flagged that an unclassified probe crosses a tier boundary | **The conflict is reduced but not resolved, and the residue is now named.** Handler invocation is eliminable and was eliminated. **Middleware execution is not**, and it is an unclassified side effect on the request path of a check D-18 puts in front of every emitted tool. So the precondition cannot be classified read-only on the strength of probe design alone; it can only be classified read-only for a target whose middleware stack has been inspected. That is a per-target determination, which is a different kind of obligation from the one Principle IV currently expresses. |
