# E14 deployment reachability — pre-registered definitions and thresholds

**Recorded**: 2026-08-02, before any resolution was scored and before any configuration beyond
finding 004's five had been enumerated.

**Authority**: FR-006. Nothing below may be revised once results are visible. A revision requires a
dated entry naming what changed and why, and the report must then state both the pre-registered and
the revised number.

**Source of the threshold**: [`plan.md`](../../plan.md) §"E14 — Deployment reachability" —
*"A resolution must recover served-set precision to ≥ 0.95 across every configuration tested."*
That number is taken as given. Everything this document adds is a **definition**, because the plan
states the threshold without stating what precision is computed over, and that choice decides the
verdict. All definitional choices are fixed here.

---

## What is being compared

Three candidate resolutions, named in the plan, scored against the same target under the same
configurations (FR-004). A fourth row is the do-nothing baseline finding 004 already measured.

| Arm | Mechanism | Needs a running instance? |
|---|---|---|
| **R0** — baseline | Emit every statically recovered operation. No reachability handling. | No |
| **R1** — configuration parsing | Statically derive, per operation, the predicate that gates its registration; evaluate that predicate against the deployment's declared configuration. | No |
| **R2** — probe the running instance | Fetch what the deployment actually serves and intersect with the static set. | **Yes** |
| **R3** — declared precondition | Emit every statically recovered operation, each carrying a reachability precondition verified before first use, failing closed. | Yes, at first use |

R1 is scored in two variants so that the tuning problem findings 004 and 007 both identified is
visible rather than hidden:

- **R1-naive** — only the mechanism a first-pass implementation would have: a lexical `if <name>:`
  in the function that immediately encloses the route declaration, where `<name>` is a parameter of
  that same function and matches a declared configuration key by name. No interprocedural flow, no
  class dispatch, no attribute tracking.
- **R1-tuned** — every gating mechanism the target actually uses, enumerated in `MECHANISMS.md` and
  implemented as named, individually switchable rules so each one's contribution is measurable.

R2 is scored in two variants because they differ in what they can see and only one is deployable:

- **R2-openapi** — `GET /openapi.json` over HTTP from the running server. Credential-free, no
  privileged access, the mechanism finding 004 §4 and finding 007 §5 both proposed.
- **R2-routetable** — in-process introspection of `app.routes`. **This is the same read that
  produces the ground truth, so its precision is tautologically 1.0 and is reported as an upper
  bound, not as a result.** It is included only to size the gap between it and R2-openapi.

## The measurement

Let:

- **S** = the static candidate set: the distinct `(method, path)` pairs codegraph recovers from
  `route` nodes under `src/`, from the same fresh index finding 004 scored. Expected size 69.
- **N** = the null set (below). `S` and `N` are disjoint by construction.
- **A_c** = the served set for configuration *c*: every `(method, path)` the instantiated
  application will dispatch, read off `app.routes`. Machine-generated, per FR-008, by the same
  method finding 004 used. `HEAD` entries Starlette auto-adds beside every `GET` are dropped.
- **P_(R,c)** ⊆ S ∪ N = the set arm *R* declares reachable under configuration *c*.

**Served-set precision** = |P ∩ A_c| / |P|.

**Served-set recall**, reported alongside precision for every arm and every configuration, is
|P ∩ A_c| / |A_c ∩ (S ∪ N)| — the share of *statically visible, actually served* operations the arm
keeps. It is not gated, and it is reported because an arm can reach precision 1.0 by discarding
real operations and that must not read as free.

Paths are compared after one normalisation, taken from finding 007: Starlette's path-converter
suffix is stripped, so `{artifact_name:path}` and `{artifact_name}` are the same parameter. No other
normalisation is applied.

### The gate reading, fixed now

The gate is evaluated on **emission-time precision**: P is what the arm declares reachable at
catalogue-generation time, before any tool has been invoked.

A **runtime precision** is also computed for R3 — the share of tools that are actually served among
those that pass their precondition and execute. It is reported with equal prominence and it is
**not** the gate. The reason for fixing this now is that R3 reaches 1.0 on the runtime reading by
construction, for any target, without analysing anything; a gate that R3 passes tautologically is
not measuring the question the plan asked. Both numbers appear in the finding.

### Disposition of statically unresolvable guards, fixed now

R1 will encounter operations whose gating predicate it cannot evaluate. The primary run resolves
these **fail-closed**: an operation whose guard cannot be evaluated is predicted **not served** and
excluded from P. Fail-open is scored as a secondary and reported.

Fail-closed is the choice that favours R1 on a precision gate, and saying so here is the point of
recording it in advance. The count of unresolvable guards is reported as a first-class number,
because it — not the precision figure it produces — is the honest measure of how much of a
deployment's gating is statically opaque.

## Configurations

At least three are required. Seven are enumerated. The first five are finding 004's, unchanged, so
this experiment's numbers are directly comparable to that one's. Two are added, each to falsify a
specific claim that the first five cannot.

| # | Configuration | Why this one |
|---|---|---|
| 1 | `api_server` — `web=False` | The worst case finding 004 measured: precision 0.3188. |
| 2 | `web` — `web=True` | The dev-UI server; the largest served set. |
| 3 | `web_a2a` — `web=True, a2a=True` | Adds a surface registered at runtime under a computed prefix. |
| 4 | `web_triggers` — `web=True, trigger_sources=["pubsub","eventarc"]` | Two trigger routes, both enabled. |
| 5 | `enterprise` — `web=False, gemini_enterprise_app_name="probe_app"` | Second-worst case: 0.3478. |
| 6 | `api_server_pubsub` — `web=False, trigger_sources=["pubsub"]` | **Added here.** Configuration 4 enables both trigger sources, so an arm that reads `trigger_sources` as merely truthy and registers both routes is indistinguishable from one that evaluates membership per element. This configuration separates them, and an arm that predicts the `eventarc` route here is wrong. |
| 7 | `devserver_no_assets` — `DevServer` constructed directly, `web_assets_dir=None` | **Added here.** In configurations 1–6 the `web_assets_dir` guard is perfectly correlated with the `web` flag, so an arm that ignores `web_assets_dir` entirely scores identically to one that models it. This configuration decorrelates them. It uses a different entry point — the documented embedding path — and that is recorded as a known difference rather than treated as equivalent. |

Every arm is scored on every configuration that can be constructed. A configuration that fails to
construct is reported as a failure, not dropped.

## Null tasks (FR-003)

An arm that declares an operation reachable when no configuration serves it is reporting a false
success. **False-inclusion rate over N is a co-primary metric, not a footnote.**

N has two parts:

1. **Synthetic phantoms** — three `(method, path)` pairs that appear nowhere in the repository:
   `GET /f2a-phantom-alpha`, `POST /apps/{app_name}/f2a-phantom-beta`, `DELETE /f2a/phantom/gamma`.
   The second is shaped to look like a member of a real route family.
2. **Real-but-foreign operations** — route declarations codegraph recovers from elsewhere in the
   repository that belong to *other* applications, principally the demonstration servers under
   `contributing/samples/`. Finding 004 §3 identified nine such pairs. These are the more
   informative null tasks, because they are real source, correctly parsed, and wrong only about
   which application serves them.

Target: **false-inclusion rate 0.0000 on every arm and every configuration.** An arm that includes
any member of N has its precision reported both with and without N in the denominator.

## Secondary measurements, declared now so they are not read as post-hoc

1. **OpenAPI coverage of the served set**, per configuration: |openapi ∩ A_c| / |A_c|. This is the
   evidence for the joint decision the plan requires — whether OpenAPI is an *input* rather than
   only a ground truth — and it is the number that decides whether R2-openapi is a complete probe
   or a partial one.
2. **Per-mechanism ablation for R1-tuned**, each named rule disabled individually, reported in the
   form finding 007 §5 used, including the all-rules-disabled figure.
3. **Whether a reachability precondition can be checked without invoking the operation.** R3 is
   only viable if the check is side-effect-free. The mechanism to be tested is method-mismatch
   discrimination: request the path with a verb the operation does not declare and read the status
   code, on the expectation that a routed path answers 405 and an unrouted one answers 404. If that
   does not hold, R3's cost changes and the finding says so.
4. **Determinism** (FR-007): the static arms are re-run and required to produce byte-identical
   output.

## Cost ceiling

**$0.00.** No model is called at any point. If any step appears to require one, the run stops and
the report says why instead.

## Kill criteria

- If no arm clears 0.95 on every configuration, that is the reportable result and the plan already
  says what follows from it: *"either the product requires a running instance to be accurate, or
  every emitted tool carries a runtime reachability check."*
- If R1-tuned clears only because its unresolvable-guard count is large and fail-closed discards
  them, the finding must lead with the unresolvable count, because precision bought by discarding
  is recall lost silently.
