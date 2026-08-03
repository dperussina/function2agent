# Finding 010 — Deployment reachability

**Date**: 2026-08-02
**User Story**: 2 (how much structure can be recovered from a codebase), resolving U-26
**Model spend**: $0.00 — no model was called
**Method**: three candidate resolutions, named in `plan.md`, scored against the target application's own
route table under eight deployment configurations. Ground truth is machine-generated (FR-008) by
instantiating the application and reading `app.routes`. Two arms talk to real `uvicorn` servers over
loopback HTTP. Nothing under `examples/` was modified (FR-018); the target is the copy the finding 004
harness makes. Metric definitions, the gate reading, the disposition of unresolvable guards, and seven of
the eight configurations were fixed in
[`PREREGISTRATION.md`](../harness/deployment-reachability/PREREGISTRATION.md) before any arm was scored
(FR-006). The harness is committed at
[`harness/deployment-reachability/`](../harness/deployment-reachability/).

## Gate adjudication, stated before anything else

The gate reads: *served-set precision ≥ 0.95 across every configuration tested.* Precision is
`|P ∩ A_c| / |P|`, where P is what an arm declares reachable **at catalogue-generation time** and A_c is
what configuration *c* actually dispatches. That reading — emission-time, not runtime — was fixed in
advance, and §3 explains why it had to be.

**Two of the three resolutions clear the gate cleanly. The third clears it too, but on seven of eight
configurations at 1.0000 and on the eighth at 0.9538, and that 0.0038 of headroom is the most important
number in this document.**

| Arm | Worst precision | Best | Verdict |
|---|---|---|---|
| **R0** — emit everything (do nothing) | **0.3188** | 0.9710 | **MISS** |
| **R1-naive** — lexical guard scan | **0.3099** | 0.8732 | **MISS — worse than doing nothing** |
| **R1-tuned** — interprocedural configuration propagation | **0.9538** | 1.0000 | **PASS**, by 0.0038 at the margin |
| **R2-openapi** — fetch `/openapi.json` from the running instance | **1.0000** | 1.0000 | **PASS** |
| **R3** — declared precondition, *emission-time reading* (pre-registered) | **0.3188** | 0.9710 | **MISS** |
| **R3** — declared precondition, *runtime reading* | **1.0000** | 1.0000 | **PASS**, tautologically |
| *R2-routetable (upper bound, not a result)* | *1.0000* | *1.0000* | *tautological — same read as the ground truth* |

> **Correction, 2026-08-02 — two rows of this table are narrower than they read, and one of them is
> narrower because of the target rather than because of the mechanism. See
> [finding 011](011-reachability-without-schema.md).**
>
> **On the `R2-openapi` row.** Its 1.0000/1.0000 is intact and is not retracted, but the gate it
> clears reads *"across every configuration tested"* and every configuration tested here published
> `/openapi.json` unauthenticated. E15 added four more schema states and measured `R2-openapi` at
> **recall 0.0000** on three of them — `ABSENT`, `FORBIDDEN`, and `EMPTY`. So this row should be
> read as *exact on deployments that publish a schema, and inapplicable on those that do not*, which
> is a scope statement this table does not make. E15 also found a fourth state this finding did not
> imagine: a 200 response carrying `{"paths": {}}`. A pipeline deciding schema availability by
> whether the fetch succeeded reads that as `PRESENT`, emits a catalogue of zero operations, and
> reports success.
>
> **On the path-level probe of §3, which is where the retraction bites.** Its **1.0000 is a
> path-granularity result that this target could not distinguish from an operation-granularity
> one.** `adk-python` contains no path that serves some HTTP methods and withholds others, so the
> two scores are the same number here by construction. E15 added one such route — `GET`
> unconditional, `POST` behind a configuration flag — and operation-granularity precision falls to
> **0.8000**. The mechanism was never measured on the case that breaks it. Path granularity itself
> holds: E15 scored **1.0000 path-granularity precision on all seven of its targets** for this
> probe design, and **every false positive it produced anywhere is a method-level error.**

Four things in that table need saying out loud rather than being left to the reader.

**R1-naive is worse than doing nothing, at all eight configurations.** 0.3099 against R0's 0.3188 at the
worst case, 0.8732 against 0.9710 at the best, and lower at every one in between. A first-pass
implementation of "parse the configuration" does
not partially solve this problem; it makes the number go down while appearing to address it. The cause is
not subtlety — it is that a lexical scan for `if <config_key>:` around a route declaration finds
declarations in *other applications* in the same repository. Its false-inclusion rate over the null set is
**0.75**: nine of the twelve null operations, every one of them a real route belonging to a demonstration
server under `contributing/samples/`, predicted as served by the deployment under test.

**R3's pass is not a result.** On the runtime reading, an arm that emits everything and checks
reachability before each first use is correct by construction, for any target, without analysing anything.
That is why the emission-time reading was pre-registered as the gate. Both numbers are in the table with
equal prominence because R3 is genuinely useful — just not as an answer to the question the gate asks.

**R2-routetable is in the table only to be excluded.** In-process `app.routes` introspection is the same
read that produces the ground truth, so its 1.0000 is arithmetic, not evidence. It is reported to size the
gap to R2-openapi, and that gap turns out to be zero over the candidate set.

**R1-tuned's 0.9538 comes from a configuration added after results were visible, and it is labelled that
way everywhere.** Configuration 8 is post-hoc. On the seven pre-registered configurations R1-tuned scores
**1.0000, seven times out of seven, including the two adversarial cases 6 and 7 were built to be** — so
the pre-registered verdict for R1-tuned is an unqualified pass. It was built because the ablation surfaced a rule
that did nothing, and chasing why revealed a blind spot the pre-registered seven could not see. Reporting
it is the point.

## Target, ground truth, and the candidate set

**Target**: `examples/adk-python` at the same commit and from the same fresh `codegraph` index finding 004
scored. Reachability handling is the only variable (FR-004); nothing about extraction quality moves.

**Candidate set S** = the 69 distinct `(method, path)` pairs codegraph recovers from `route` nodes under
`src/`. Unchanged from finding 004.

**Null set N** (FR-003), 12 operations, disjoint from S: three fabricated pairs that appear nowhere in the
repository, one of them shaped to look like a member of a real route family (`POST
/apps/{app_name}/f2a-phantom-beta`), plus the nine real-but-foreign route declarations finding 004 §3
identified in other applications inside the same repository. The foreign nine are the informative ones:
real source, correctly parsed, wrong only about which application serves them.

**Ground truth A_c** = every `(method, path)` the instantiated application dispatches, read off
`app.routes`, machine-generated per configuration. `HEAD` entries Starlette auto-adds beside every `GET`
are dropped. Separately, and recorded separately because whether they differ is one of the measurements,
what `app.openapi()` publishes.

Paths are compared after exactly one normalisation, carried over from finding 007: Starlette's
path-converter suffix is stripped, so `{artifact_name:path}` and `{artifact_name}` are the same parameter.

**The union of all eight configurations serves 77 pairs and contains all 69 of S.** No configuration
serves all 69. This is the shape of the problem in one sentence: every recovered route is real, and no
single deployment serves them all.

## The eight configurations, and why these

The plan requires at least three. Seven were pre-registered; an eighth was added post-hoc and is labelled
so. The first five are finding 004's, unchanged, so the numbers here are directly comparable to that
finding's.

| # | Configuration | Serves | Of which in S | Why this one |
|---|---|---|---|---|
| 1 | `api_server` — `web=False` | 27 | 22 | Finding 004's worst case, the 0.3188 figure. |
| 2 | `web` — `web=True` | 71 | 65 | The dev-UI server; the largest served set among the pre-registered. |
| 3 | `web_a2a` — `web=True, a2a=True` | 73 | 65 | Adds two routes registered at runtime under a **computed** prefix. Neither static analysis nor OpenAPI sees them. |
| 4 | `web_triggers` — `trigger_sources=["pubsub","eventarc"]` | 73 | 67 | Both trigger routes enabled. |
| 5 | `enterprise` — `gemini_enterprise_app_name` set | 29 | 24 | Finding 004's second-worst case, 0.3478. |
| 6 | `api_server_pubsub` — `trigger_sources=["pubsub"]` | 28 | 23 | **Added at pre-registration, to falsify a specific cheat.** Configuration 4 enables both trigger sources, so an arm that reads `trigger_sources` as merely *truthy* and registers both routes is indistinguishable there from one that evaluates membership element-wise. Here it is distinguishable, and predicting the `eventarc` route is wrong. |
| 7 | `devserver_no_assets` — `DevServer` constructed directly, `web_assets_dir=None` | 63 | 58 | **Added at pre-registration, to break a correlation.** In 1–6 the `web_assets_dir` guard is perfectly correlated with the `web` flag, so an arm that ignores it entirely scores identically to one that models it. Uses the documented embedding entry point, recorded as a known difference rather than treated as equivalent. |
| 8 | `web_no_multipart` — **identical declared configuration to `web`**, `python-multipart` unimportable | 68 | 62 | **POST-HOC. Added after results were visible.** Three routes silently do not register, with nothing in the configuration to indicate it. See §"The configuration that separates the arms." |

Configurations 6 and 7 exist because a gate is only worth passing if it can be failed. Both were declared
before any arm ran, and both did their job: without 6, an arm scoring `trigger_sources` as a boolean
passes; without 7, an arm ignoring `web_assets_dir` passes.

## 1. Configuration parsing (R1): the tuned version is exact, and that is the problem

R1 was scored in two variants deliberately, because findings 004 and 007 both established that rules
discovered by inspecting one codebase's failures should not be assumed to transfer (C-12, U-32), and
collapsing them would have hidden exactly that.

| Configuration | R0 (do nothing) | R1-naive | R1-tuned |
|---|---|---|---|
| `api_server` | 0.3188 | **0.3099** | **1.0000** |
| `api_server_pubsub` | 0.3333 | 0.3099 | 1.0000 |
| `enterprise` | 0.3478 | 0.3288 | 1.0000 |
| `devserver_no_assets` | 0.8406 | 0.8169 | 1.0000 |
| `web` | 0.9420 | 0.8732 | 1.0000 |
| `web_a2a` | 0.9420 | 0.8732 | 1.0000 |
| `web_triggers` | 0.9710 | 0.8732 | 1.0000 |
| `web_no_multipart` *(post-hoc)* | 0.8986 | 0.8310 | **0.9538** |
| **False-inclusion rate over N** | 0.0000 | **0.7500** | 0.0000 |
| **Unresolvable guards** (excluded from P under fail-closed) | n/a | 4 – 7 | **0** |

R1-tuned achieves 1.0000 precision **and 1.0000 recall** on all seven pre-registered configurations. It
predicts exactly the served subset of S, with no false positives and no dropped operations, including the
element-wise `trigger_sources` discrimination configuration 6 was built to catch and the decorrelated
`web_assets_dir` guard configuration 7 was built to catch. Its unresolvable-guard count is **zero**, so
the fail-closed disposition pre-registered as the primary reading never fires, and fail-open scores
identically. The precision was not bought by discarding, which is the failure mode the pre-registration
named in advance.

That is a better result than expected, and it is worth being suspicious of rather than pleased about.

### The eight mechanisms, and the ablation that matters more than the headline

R1-tuned is a depth-limited interprocedural concrete-value propagator over the `ast` module, seeded with
the declared configuration. Nothing is executed. It needs eight distinct capabilities to evaluate this one
application's gating predicates, each implemented as an individually switchable rule so its contribution
is measurable — the form finding 007 §5 used.

| Disabled | Predicted (pooled over 7) | Min precision | Min recall | Unresolvable |
|---|---|---|---|---|
| *none* | 324 | 1.0000 | 1.0000 | 0 |
| `M1_class_dispatch` | **0** | 0.0000 | 0.0000 | 0 |
| `M2_kwarg_flow` | **2** | 0.0000 | 0.0000 | 0 |
| `M3_attribute_flow` | 321 | 1.0000 | 0.9565 | 14 |
| `M4_membership` | 321 | 1.0000 | 0.9565 | 4 |
| `M5_optional_import` | **324** | **1.0000** | **1.0000** | **0** |
| `M6_explicit_presence` | 312 | 1.0000 | 0.9385 | 12 |
| `M7_class_attrs` | 321 | 1.0000 | 0.9565 | 0 |
| `M8_comprehension` | 321 | 1.0000 | 0.9565 | 4 |
| **all** | **0** | 0.0000 | 0.0000 | 0 |

**Three readings of this table, in ascending order of how much they should worry us.**

First, precision never degrades. Every single-mechanism ablation still scores 1.0000 precision, because
fail-closed converts a missing capability into a dropped operation rather than a wrong one. R1's failure
mode is recall loss, not precision loss, and that is a genuinely useful structural property: a
configuration parser that cannot evaluate a guard produces a smaller catalogue, not a wrong one.

Second, **with all mechanisms disabled the arm predicts zero operations, and disabling `M1` alone also
predicts zero.** This is a much sharper version of the warning C-12 and U-32 record. Finding 007's
all-rules-disabled figure was 0.5797 — degraded but functional, so "the rules are refinements" was a
defensible reading. Here it is 0.0000. The mechanism set is not a refinement layer on top of a working
analysis; **it is the analysis.** The honest expectation for this technique on a framework nobody has
tuned it for is not "somewhat worse than 1.0000." It is "recovers nothing until eight specific
capabilities are built, and which eight depends on the framework."

> **Correction, 2026-08-02 — this paragraph names one collapse-inducing mechanism and the table
> above it shows two. See [finding 011](011-reachability-without-schema.md) §2.**
>
> `off-M2_kwarg_flow` predicts **2 operations of 324 at minimum precision 0.0000**, which is a
> collapse by the same reading that makes `off-M1_class_dispatch` one. The number is in this
> finding's own committed ablation table and was correct there; only the prose was wrong, and the
> prose is what propagated. **Read every downstream statement of this result as "disabling either
> `M1_class_dispatch` or `M2_kwarg_flow`."** Nothing was re-measured — the existing numbers were
> re-read.

Third, **`M5_optional_import` does nothing, and finding that out is what produced configuration 8.**
Disabling it changes not one number. The guard it was written for is `try: import multipart / except
ImportError: return`, and the propagator does not execute exception handlers, so it never takes the early
return. The mechanism was dead code that appeared to be load-bearing. The consequence is not cosmetic:
**R1 predicts the three builder routes served whenever `web` is true, whether or not `python-multipart` is
installed.**

### The configuration that separates the arms

Configuration 8 makes `python-multipart` unimportable and changes nothing else. The declared configuration
is byte-identical to `web`. Three routes silently do not register — 68 served instead of 71.

- **R1-tuned predicts 65 and 62 are served: precision 0.9538.**
- **R2-openapi: 1.0000. R3 path-level: 1.0000.**

0.9538 clears 0.95, and the pre-registered verdict is unaffected because this configuration is post-hoc.
But the margin is 0.0038, which is **less than one operation**: a fourth environment-dependent route would
put R1-tuned at 0.9385 and sink it. And there is no upper bound on that count. The failure class is not
configuration blindness — R1 read the configuration correctly and completely. It is **environment
blindness**, and it is a different kind: the fact that decides whether these routes register is not in the
source or in the configuration, it is in the installed package set of the machine the deployment runs on.
No configuration parser reads that, because it is not configuration.

This is the same shape as finding 007's headline result, arriving by a different route. There, a
derivation stopping one inheritance hop short produced contracts that were fluent, plausible, and wrong
about every field name, with nothing in the output to indicate it. Here, a configuration parser that reads
the configuration perfectly produces a catalogue that is wrong about three operations, with nothing in the
output to indicate it. **Both are cases of a derived artifact being confidently wrong, and both were found
only by constructing the adversarial case on purpose.**

## 2. Probing the running instance (R2): exact, and the winner

| Configuration | Precision | Recall | OpenAPI coverage of the *full* served set |
|---|---|---|---|
| `api_server` | 1.0000 | 1.0000 | 0.8148 |
| `api_server_pubsub` | 1.0000 | 1.0000 | 0.8214 |
| `enterprise` | 1.0000 | 1.0000 | 0.8276 |
| `devserver_no_assets` | 1.0000 | 1.0000 | 0.9206 |
| `web` | 1.0000 | 1.0000 | 0.9155 |
| `web_a2a` | 1.0000 | 1.0000 | 0.8904 |
| `web_triggers` | 1.0000 | 1.0000 | 0.9178 |
| `web_no_multipart` | 1.0000 | 1.0000 | 0.9118 |

`GET /openapi.json` over HTTP, intersected with S. Credential-free, no privileged access, no in-process
hook. **Precision 1.0000 and recall 1.0000 on all eight configurations, dropping zero served operations
anywhere.** Every one of the 69 recovered routes is a FastAPI `APIRoute`, and every served `APIRoute`
appears in the published schema, so over the candidate set the schema and the route table are the same
set. The gap to the tautological in-process upper bound is exactly zero.

> **Correction, 2026-08-02 — "the winner" needs a population attached to it. See
> [finding 011](011-reachability-without-schema.md) §1.**
>
> Every number in the table above is intact and R2 remains the mechanism of choice **on a deployment
> that publishes a schema**. What this section does not say, because no configuration here could have
> shown it, is that R2 has no graceful degradation: E15 measured its recall at **0.0000** on
> `ABSENT`, `FORBIDDEN`, and `EMPTY` alike, while the schema-free path-level probe scored **precision
> 1.0000 and recall 1.0000 on all four FastAPI schema states**, identical to the schema-present
> control. So R2 wins among the mechanisms available on an *introspectable* target, and the
> mechanism that covers the rest is the §3 probe rather than the configuration parser — see the
> correction under §4.
>
> **One thing R2 supplies that no probe does, and this section does not distinguish it either.** The
> schema is an *enumerator* as well as a filter. This finding measured 8 of 77 served operations
> lying outside S, two of them real `a2a` operations; a probe can only ask about paths it was given,
> so it recovers none of them, and without a schema **the size of that blindness is unmeasurable.**
> Accuracy transfers to the schema-free case; coverage does not.

**The coverage column is the caveat, and it is the evidence for the OpenAPI decision below.** Against the
*full* served surface — not the intersection with S — the schema covers 0.8148 to 0.9206. What it misses
is consistent and explicable:

- `GET /docs`, `GET /docs/oauth2-redirect`, `GET /redoc`, `GET /openapi.json` — framework-generated
  documentation routes.
- `MOUNT /dev-ui` — a Starlette `StaticFiles` mount, which has no operation to describe.
- `WS /run_live` — a WebSocket route. OpenAPI 3.x has no representation for one.
- Under `web_a2a` only: `POST /a2a/probe_app` and `GET
  /a2a/probe_app/.well-known/agent-card.json` — added at runtime under a computed prefix.

**Static analysis misses every one of these too.** They are outside S by construction. So the schema is
*complete over the intersection with what static analysis can recover* and *incomplete over the served
surface*, and the incompleteness is in exactly the region static analysis was never going to reach either.
The a2a pair is the interesting one, because it is real application functionality registered under a
computed prefix, invisible to both mechanisms — direct evidence for the concern U-29 records about
computed paths, now observed rather than hypothesised.

## 3. Declared precondition (R3): the mechanism works, and it invoked handlers

R3 emits everything and verifies reachability before first use. The pre-registered question was whether
the check can be performed **without invoking the operation**, because R3 is not viable otherwise. The
mechanism tested: request the path with a verb the operation does not declare, on the expectation that a
routed path answers 405 and an unrouted one answers 404.

| Variant | Precision (all 8) | Recall | Note |
|---|---|---|---|
| Emission-time (the pre-registered gate reading) | 0.3188 – 0.9710 | 1.0000 | Identical to R0. R3 declares everything. |
| **Path-level probe** | **1.0000** | 0.9655 – 1.0000 | The mechanism that works. |
| `Allow`-header method discovery | 1.0000 | **0.7241 – 0.7612** | **Broken. See below.** |

> **Correction, 2026-08-02 — the path-level probe's precision row is a path-granularity number, and
> its recall row is a property of a harness constant. See
> [finding 011](011-reachability-without-schema.md) §3 and §5.**
>
> **Precision.** 1.0000 here is precision over *paths this target routes*, and on this target that
> is indistinguishable from precision over *operations it serves*, because no `adk-python` path
> serves some methods and withholds others. Add one route of that ordinary shape and the
> operation-granularity figure is **0.8000**. E15 confirms path granularity holds — 1.0000 on all
> seven of its targets for this probe design, with every false positive anywhere a method-level
> error — so the row is not wrong, it is answering a narrower question than the gate asks. **A
> path-level probe cannot answer an operation-granularity question at all.**
>
> **Recall.** The 0.9655 floor **is not a property of the mechanism.** E15 ran the same defective
> probe and scored recall 1.0000, because it concretised path parameters as `f2a-probe` rather than
> `__f2a_probe__`. `adk-python`'s `app_name` validator accepts the second as a valid Python
> identifier and rejects the first, so the absorbed handler's response flipped from its own 404
> (read as "unrouted", costing recall) to a 400 (read as "routed", costing nothing). **Same defect,
> same two handlers invoked, accuracy metric moved because of a hyphen.** Read any recall figure for
> this mechanism as conditional on the sentinel value, and see the correction under defect B.

The 404/405 discrimination does work: only those two status codes were ever observed, and precision is
1.0000 on all eight configurations. But two defects turned up, and both were verified directly against a
running instance rather than inferred — `verify_probe_defects.py` in the harness, output committed.

### Defect A — the `Allow` header under-reports, silently

The obvious refinement is to read the `Allow` header on the 405 and get the exact served method set for
free. It does not work. Probing `PUT /apps/{app_name}/users/{user_id}/sessions/{session_id}` returns
`Allow: GET`. The route table serves **`DELETE`, `GET`, `PATCH`, and `POST`** on that path.

Starlette reports the methods of the *first* matching route, not the union across routes sharing a path.
Trusting it costs **24–28% of real operations**, dropped with no error and no signal. Recall falls to
0.7241 at worst — from a field that looks authoritative, is served by the framework itself, and is wrong.
Third instance of that pattern in three findings: finding 004's `.gitignore` filter, finding 007's alias
generator, and now this.

A second, smaller variant of the same class: `/dev-ui/config` returns 405 with **no `Allow` header at
all**, because the `StaticFiles` mount at `/dev-ui/` intercepts the request before the `APIRoute` can
report a method mismatch.

> **Correction, 2026-08-02 — "under-reports" is the Starlette case, not the general one, and even on
> Starlette it is sharper than recorded. See
> [finding 011](011-reachability-without-schema.md) §4.**
>
> **The header is wrong in opposite directions across routers.** Measured on three: Starlette
> under-reports (precision 1.0000, recall 0.7692 on this target, wrong on 9 of 51 routed paths);
> **Flask/Werkzeug over-reports**, unioning across every matching rule so a parameterised sibling's
> methods are attributed to a literal path (precision 0.8889, recall 1.0000); Django is exact where
> the view declares its methods and silent where it does not. **A correction learned on one router
> makes another worse**, which is a stronger reason to forbid reading the header than
> under-reporting alone.
>
> **And the Starlette failure is not merely incompleteness.** In E15's reconnaissance the header
> named `GET, HEAD` for a path whose only declared method is `POST`, because a parameterised sibling
> was registered first; reordering the two registrations changed the header to `POST`. So the
> header's correctness is **a function of route registration order, and it can name a different
> route's methods entirely.** This finding recorded it as under-reporting because on `adk-python`
> the first partial match happened to be a real route for that path.

### Defect B — a handler-generated 404 is indistinguishable from an unrouted 404, and it means a handler ran

Probing `GET /dev/apps/{app_name}/tests/rebuild` returns **404**, so the probe concludes the path is
unrouted. It is not: `POST` on that path is served. The `GET` matched the sibling parameterised route `GET
/dev/apps/{app_name}/tests/{test_name}` with `test_name="rebuild"`, **the handler executed**, and the
handler returned 404 with body `{"detail":"Test file not found"}`.

Two consequences, and the second is worse than the first.

The recall shortfall is entirely explained by this. The operations R3 drops are exactly `POST
/dev/apps/{app_name}/tests/rebuild` and `POST /dev/apps/{app_name}/tests/run`, on every configuration
where they are served, and nothing else. There is a cheap fix: the router's 404 carries body `{"detail":
"Not Found"}` and the handler's carries a different body, so the two are distinguishable — verified
directly. That fix is a body inspection, not a status-code read, and it is a heuristic on a
framework-specific default message. It has not been implemented or scored here.

**The more important consequence is that the side-effect-freedom claim is qualified, not established.** A
probe designed specifically not to invoke handlers invoked at least two, because path-parameter routes
absorb probes aimed at their literal siblings. On this application the absorbed handler read a file and
returned an error, which is harmless. Nothing about the method-mismatch design guarantees that. A sibling
route whose handler writes before it validates would have been written to. R3's cost is therefore higher
than the pre-registration assumed, and the pre-registration said it would say so if that happened.

> **Correction, 2026-08-02 — this defect is eliminable and has been eliminated, and the body-
> discrimination fix proposed above should not be built. See
> [finding 011](011-reachability-without-schema.md) §5.**
>
> **The fix is the probe verb, not the response body.** Probing with a verb **no route in the
> application declares** — a fabricated token, not a real verb the operation happens not to use —
> yields **0 handler invocations across all seven E15 targets, against 13 for the rule used here.**
> In a router that matches path before method, a request whose method no route declares can only
> produce a partial match, so the router answers 405 and no handler is reachable; and under such a
> probe a router can only answer 404 or 405, so any other status is itself proof that application
> code ran. One line, and it makes the body heuristic — a guess at a framework-specific default
> message — unnecessary.
>
> **What that does not buy is the claim this section wanted.** Three residues remain, and the first
> two are why. Middleware runs before routing for every request regardless of method, so audit
> logging, rate-limit counters, and session creation are not avoidable by any probe design. A
> framework that puts method dispatch in application code breaks the proof outright — Django does,
> and an undecorated view **executed** on a fabricated-verb probe. And a concretised path segment
> still arrives at the deployment where a WAF or an audit trail can see it. So *probably
> side-effect-free* should become **provably free of handler invocation, subject to a per-framework
> check that the router separates path matching from method matching, with middleware as an
> irreducible residue** — strictly stronger than what is written here, and strictly weaker than
> side-effect-free.
>
> **And the recall shortfall this section explains does not survive as an accuracy result.** E15 ran
> the same defect with a different sentinel and scored 1.0000, with the same two handlers invoked.
> **A safety defect was masquerading as an accuracy metric.** The two dropped operations are still
> dropped for the reason given above; what is retracted is the idea that a recall figure measures
> it.

## 4. The joint decision: OpenAPI is an input, with a label

`plan.md` requires this decided jointly with reachability, because finding 007 and R2 want the same fetch
from the same running instance. Deciding it separately would pay for the fetch twice and, worse, could
reach two incompatible answers.

**Decision: where a target publishes an OpenAPI schema, fetch it once per deployment configuration and
use it as a pipeline input for both reachability and contracts. It is not a substitute for static
analysis, and every artifact derived from it carries a label saying which configuration it came from.**

The evidence for the reachability half:

1. **Over the intersection with statically recovered routes, the schema is exact.** Precision 1.0000 and
   recall 1.0000 on eight configurations, dropping zero served operations. The gap to in-process
   introspection is zero.
2. **It is the only arm that is exact on all eight**, including the environment-dependent case where
   configuration parsing degrades. It reports what the running process actually assembled, so environment
   blindness cannot arise.
3. **It costs one unauthenticated HTTP GET.** R1-tuned costs eight framework-specific analysis
   mechanisms, discovered by inspecting one codebase, that collectively predict nothing when disabled.

Three conditions, each measured here rather than assumed:

1. **Per configuration, never once.** The schema describes the deployment that served it. `api_server`
   publishes 22 operations and `web_triggers` 67, from the same source tree. A schema fetched from staging
   and applied to production is the original bug wearing a different hat.
2. **Labelled as the OpenAPI-visible subset.** Coverage of the full served surface is 0.8148–0.9206. The
   gap is WebSockets, static mounts, framework documentation routes, and runtime-registered computed
   prefixes. A catalogue built only from the schema would be silently missing `WS /run_live` and the two
   a2a operations — real functionality.
3. **A floor for contracts, not a ceiling.** Finding 007's counter-example stands unchanged: for `POST
   /run_sse` the framework publishes an empty response schema while the static walk recovers all nine
   request body fields and two raise sites with literal status codes. The schema is authoritative about
   *what is served*; it is not uniformly the richest description of *what an operation takes and returns*.
   Static derivation remains necessary for exceptions, where finding 007 showed it is strictly more
   informative than the schema — this application's schema declares `{200, 422}` and nothing else, while
   37 endpoints raise literal status codes it never mentions.

**And the condition that is not measured, which is the largest hole in this decision.** Every number above
comes from a deployment that publishes `/openapi.json` unauthenticated. Production FastAPI deployments
routinely pass `openapi_url=None` or put the schema behind authentication, and **no configuration here
tested either.** If the schema is absent, R2 contributes nothing and the fallback is R1-tuned — which
means falling back to the arm whose all-disabled figure is 0.0000 and whose margin on the one adversarial
configuration is 0.0038. That is a materially worse position than the eight-configuration table suggests,
and it is recorded as a new uncertainty rather than absorbed.

> **Correction, 2026-08-02 — the sentence "the fallback is R1-tuned" is wrong, and it is wrong in
> the direction that made this hole look worse than it is. See
> [finding 011](011-reachability-without-schema.md) §1.**
>
> Measured directly on four FastAPI configurations differing only in schema availability: with the
> schema `ABSENT`, `FORBIDDEN`, or `EMPTY`, the **schema-free path-level probe of §3 scored precision
> 1.0000 and recall 1.0000, identical to the schema-present control**, while `R2-openapi` fell to
> 0.0000 recall. Configuration parsing is therefore the fallback for targets that cannot be **run**,
> and specifically not for targets that cannot be **introspected** — different populations, and the
> second one does not need it.
>
> **Three things are genuinely lost with the schema, and none of them is precision.** Coverage: the
> schema enumerates, a probe only filters (see the correction under §2). Method-level
> discrimination: a path-level probe cannot supply it and the only schema-free refinement is the
> `Allow` header this finding forbids. And cost: **67 requests against 1** on this target, one per
> candidate path, every one a method-mismatch probe visible in the deployment's access log and error
> metrics.

## 5. Determinism holds

FR-007. Both static arms were re-run from the same inputs and compared byte for byte: R1-tuned identical,
the static-set extractor identical. One defect was found and fixed in the course of checking — the
extractor sorted a record set on a partial key, leaving tied entries in hash order. The route-table and
schema reads were also re-run and are identical across runs, though that is a property of the application
rather than of this harness and is not claimed as one.

## What this means for the product

**1. U-26 is resolved, and the resolution requires a running instance.** The mechanism is *probe the
deployment*, primary. The plan anticipated the alternative — *"either the product requires a running
instance to be accurate, or every emitted tool carries a runtime reachability check"* — and the answer is
the first, with the second as a complement rather than a substitute.

**2. Reachability is a pipeline stage with a hard precondition, not a filter applied at the end.** The
candidate set is a multiple of the served surface: a factor of 3.1 at worst here (69 declared against 22
served-and-recovered). Emitting the candidate set and filtering later means the filter decides the
catalogue, so it belongs where its inputs are available, and its input is a running deployment.

**3. Configuration parsing is the fallback, and it should be built and priced as one.** It scored 1.0000
on the pre-registered seven, which is a real result. But: eight framework-specific mechanisms; 0.0000
predicted with them disabled; one of the eight was dead code; and a blind spot to environment that no
amount of further tuning addresses, because the fact it needs is not in the source. Build it for targets
that cannot be run, quote 0.0000 as the untuned expectation, and never present it as equivalent to the
probe.

**4. Every emitted tool carries a reachability precondition anyway, and it is cheap.** Not because it
closes the gate — on the pre-registered reading it does not move at all — but because a deployment's
served set changes after the catalogue is generated, and a 404 at generation time is a support ticket
while a 404 in front of a user is the product failing. The 404/405 mechanism works at path level with
precision 1.0000. **Do not read the `Allow` header** (defect A), and treat the check as
*probably* side-effect-free rather than *provably* so (defect B).

> **Correction, 2026-08-02 — both clauses of the last sentence change, in opposite directions, and
> the precision figure needs a granularity attached. See
> [finding 011](011-reachability-without-schema.md).**
>
> **The `Allow` prohibition is upheld and strengthened**: the header is now measured wrong in
> *both* directions across three routers, so a correction learned on one makes another worse.
> **The side-effect clause improves but does not reach *provably***: switching the probe verb to one
> no route declares takes handler invocations from 13 to 0, leaving middleware execution as an
> irreducible residue that no probe design removes. The supportable wording is *provably free of
> handler invocation, subject to a per-framework router check, with middleware as an irreducible
> residue.* **The precondition therefore cannot ship as side-effect-free on any framework**, which
> leaves the Principle IV conflict this finding opened reduced rather than resolved.
> **And "precision 1.0000" is path-level in the strict sense**: on a target with a path that serves
> some methods and withholds others, operation-granularity precision is 0.8000, so the precondition
> must be stated as path-level or given a method-level input the schema-free case does not have.

**5. The generated catalogue must record which deployment it describes, as data.** Not a footnote in a
README — a field, alongside the provenance and confidence D-17 already requires. A catalogue generated
against `api_server` and applied to a `web` deployment silently omits 43 real operations; the reverse
silently includes 43 that 404. Neither is detectable from the catalogue as currently shaped.

## What this does NOT license

**One target, one framework, one language, one process.** FastAPI on Starlette, Python, single-process
`uvicorn`. Both instrumentation defects are Starlette properties: the `Allow` semantics are its
`Router.__call__`, and the mount shadowing is its `Mount` precedence. Neither transfers as a claim, and
neither transfers as a *reassurance* — a framework that answers 404 for method mismatch would break the
R3 mechanism entirely, and nothing here would have caught that.

**R1-tuned's 1.0000 is a best case, and unlike finding 007's it does not degrade gracefully.** Finding 007
could carry 0.5797 forward as the untuned expectation. The equivalent figure here is **0.0000 operations
predicted**. Do not carry 1.0000 anywhere outside this document without the all-disabled figure beside it.

**Precision is computed over S ∪ N, not over the served set.** An arm is scored on what it does with the
69 recovered operations plus 12 nulls. Nothing here measures the 8 served operations that are outside S in
the union — mounts, WebSockets, computed prefixes — because no arm can predict them and finding 004
already recorded them as out of scope.

**R3's 1.0000 on the runtime reading is arithmetic**, and R2-routetable's 1.0000 is the ground truth
grading itself. Neither is evidence of anything.

**Configuration 8 is post-hoc** and the pre-registered verdict excludes it. It is reported because the
ablation exposed the mechanism it tests, and suppressing it would have left a 1.0000-across-the-board
result that is true and misleading.

**No target that publishes no schema was measured, and no schema behind authentication was measured.**
This is the largest single hole and it sits directly under the primary recommendation.

**The side-effect-freedom of the precondition check is not established.** It was designed to be free and
was observed invoking at least two handlers. What was measured is that the two it invoked did no damage on
this application.

**Nothing here measures multi-process, multi-replica, or gateway-fronted deployments.** A probe reaches
one replica. If replicas differ, or if an API gateway or service mesh admits a subset of what the
application serves, the probe's answer is about the process it reached and the finding says nothing about
whether that generalises. This is a plausible production shape and it is entirely unmeasured.

**Static analysis missed the two a2a operations and so did OpenAPI.** They are real and served. The
finding does not license a claim that a probe recovers the served surface — only that it recovers the
served subset of what static analysis proposed.

## Register entries needing propagation

Identifiers only; a separate pass edits
[`research/14-architecture-synthesis.md`](../../../research/14-architecture-synthesis.md).

| Entry | Current | Should become |
|---|---|---|
| **U-26** — configuration blindness | Blocking; three candidate resolutions, *"which one is right is unresolved"*; owned by E14 | **Resolved, and moved out of §5.1 Blocking.** Resolution (b), probing the running instance, is chosen: precision 1.0000 and recall 1.0000 on eight configurations, dropping zero served operations, at the cost of one unauthenticated HTTP GET. Resolution (a) is the fallback for un-runnable targets, at 1.0000 on the seven pre-registered configurations but 0.0000 predicted with its mechanisms disabled and 0.9538 on an environment-varied configuration. Resolution (c) is a complement, not a substitute: on the pre-registered emission-time reading it scores identically to doing nothing. Two residual holes are **not** closed by this and are recorded separately as U-34 and U-35. |
| **New: U-34** | — | **NEWLY OPENED — the primary reachability mechanism assumes a schema endpoint that production deployments routinely disable.** Every R2 number comes from a deployment publishing `/openapi.json` unauthenticated. `openapi_url=None` and auth-gated schemas are common and **neither was tested**. Without the schema the fallback is R1-tuned, whose all-mechanisms-disabled figure is 0.0000. Blocking for any customer promise about targets we cannot run. Resolve by measuring a schema-disabled configuration and a target that publishes nothing — both cost $0. |
| **New: U-35** | — | **NEWLY OPENED — environment blindness is a distinct failure class from configuration blindness, and it has no upper bound.** A configuration parser that reads the deployment configuration perfectly and completely still predicted three unserved operations, because whether they register depends on the installed package set, not on the source or the configuration (precision 0.9538, margin to the gate 0.0038 — less than one operation). Optional-dependency guards, feature detection, and platform checks all sit in this class and none is enumerated. Non-blocking only because the probe does not have this failure mode; it becomes blocking the moment configuration parsing is on a customer path. |
| **New: U-36** | — | **NEWLY OPENED — probe results are scoped to the process the probe reached.** Multi-replica, multi-process, and gateway- or mesh-fronted deployments are entirely unmeasured. If replicas differ or a gateway admits a subset, the probe describes one process and this finding says nothing about generalisation. Resolve before any claim about production topologies. |
| **C-12** — heuristics discovered from one codebase's failures | Extended by finding 007; carry-forward figure 0.5797 | **Extend again, and sharpen the carry-forward.** A third rule population, discovered the same way: all eight R1-tuned mechanisms were written after inspecting this repository's gating constructs. The all-disabled figure is **0.0000 predicted**, not "degraded" — so unlike finding 007's rules these are not refinements on a working analysis, they *are* the analysis. Also: `M5_optional_import` was dead code that scored as load-bearing until ablated, which is an argument for ablating every rule rather than reporting the tuned figure. |
| **U-32** — every contract number is a best case | 0.5797 as the untuned expectation | **Extend with the reachability parallel.** The same argument now has a second, more extreme instance: 0.0000 rather than 0.5797. Reinforces the standing recommendation to measure a non-signature framework before generalising anything from FastAPI. |
| **U-29** — path accuracy under router prefixes and computed paths | Unmeasured; the largest self-declared hole in finding 004 | **Partially discharged, in the direction the entry feared.** Two real operations registered at a computed prefix (`POST /a2a/{app}`, `GET /a2a/{app}/.well-known/agent-card.json`) were missed by static analysis **and** by the published schema. Observed, not hypothesised. Still open for `APIRouter`/`include_router`, which this target does not use. |
| **D-17** — provenance and confidence on every derived artifact | Three requirements: provenance, validation, confidence | **Add a fourth: deployment identity.** Every emitted catalogue records which deployment configuration it describes, as data. The same source tree yields 22 or 67 served operations depending on configuration, and neither the omission nor the over-inclusion is detectable from the catalogue as currently shaped. |
| **New: D-18** | — | **NEW — reachability is resolved by probing, per configuration, with a precondition on every emitted tool.** (1) Probe the running deployment and intersect with the static candidate set; this is a pipeline precondition, not a post-filter. (2) Fetch the target's schema **once per configuration** and use it as an input for reachability *and* contracts, labelled as the OpenAPI-visible subset — one fetch settles both questions. (3) Configuration parsing is the fallback for un-runnable targets, priced at eight framework-specific mechanisms and quoted with its 0.0000 untuned figure. (4) Every emitted tool carries a path-level reachability precondition verified before first use; **do not** read the `Allow` header, and treat the check as probably rather than provably side-effect-free. |
| **§2 analysis-layer rule 4** — *"a declared endpoint is not a served endpoint"* | *"Which mechanism closes it is unresolved — see U-26"* | **Rule stands, mechanism now named.** Replace the unresolved clause with D-18. The factor-of-2.6 figure should become **3.1** (69 declared against 22 served-and-recovered in the `api_server` configuration), which is the same measurement stated against the recovered set rather than the served total. |
| **§2 "OpenAPI as input"** | Two cautions, decision *"owned by E14"* | **Decided.** Yes, an input — for reachability and contracts jointly, one fetch. Both cautions were measured and both hold: per configuration, never once (22 vs. 67 operations from one source tree), and a floor rather than a ceiling (coverage of the full served set is 0.8148–0.9206). A third caution is added: it is unavailable by design on some production deployments (U-34). |
| **C-14 (new contradiction)** | — | **NEW — framework-published metadata is authoritative about what is served and unreliable about what is served *where*.** The same OpenAPI fetch that recovers reachability at precision 1.0000 covers only 0.8148–0.9206 of the served surface, and the `Allow` header from the same framework under-reports served methods by 24–28%. Resolution: use framework metadata as an input where it is exact over a defined subset, label the subset, and never treat a framework-populated field as authoritative without checking it against the route table. Third instance of this pattern in three findings — finding 004's `.gitignore`, finding 007's alias generator, and now the `Allow` header. |

## Immediate next steps

1. **Measure a target that publishes no schema, and one that gates it behind authentication.** $0, and it
   sits directly under the primary recommendation (U-34).
2. **Measure a non-FastAPI target.** Both defects here are Starlette properties, and a framework that
   answers 404 for method mismatch breaks the precondition mechanism outright.
3. **Implement and score the body-discrimination fix for defect B** — or decide that R3 accepts a
   3%-of-operations recall loss and record it. Currently neither.
4. **Enumerate the environment-dependent guard class** before configuration parsing goes anywhere near a
   customer path (U-35). Optional imports, feature detection, platform checks: one target's count is not a
   bound.

> **Correction, 2026-08-02 — steps 1 through 3 are discharged by E15, and step 3's answer is "do
> neither." See [finding 011](011-reachability-without-schema.md).**
>
> Step 1 ran: four schema states on FastAPI, plus three targets that publish nothing. Step 2 ran:
> Starlette, Flask/Werkzeug and Django, and **all three answer 405 for a method mismatch**, so the
> feared 404 behaviour did not appear on any of them. Step 3 is retracted rather than completed —
> the body-discrimination fix should not be built, because changing the probe verb removes the
> defect it was meant to work around. Step 4 stands untouched: E15 varied schema availability and
> framework, not installed package sets.
