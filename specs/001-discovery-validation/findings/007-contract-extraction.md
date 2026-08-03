# Finding 007 — Contract extraction

**Date**: 2026-08-02
**User Story**: 2 (how much structure can be recovered from a codebase), feeding constitution Principle I
**Model spend**: $0.00 — no model was called
**Method**: for each of the 69 endpoints finding 004 recovered, a contract was derived statically from
the repository's own source and scored against the contract the running FastAPI application publishes
for itself. A secondary, separately labelled measurement parsed signature strings out of a stale
read-only TypeScript index. Nothing under `examples/` was modified and nothing in the TypeScript
repository was written to (FR-018). The harness is committed at
[`harness/contract-extraction/`](../harness/contract-extraction/).

## The result in one paragraph

A verifiable contract can be derived, and the parameter half of it is derived exactly. All 69
endpoints yielded a parameter list that matches the framework's published schema **tuple for tuple —
207 inputs derived, 207 expected, zero mismatches on name, location, required flag, and type**. The
return type is recovered for every endpoint that has one to recover: 53 agreements, **zero
disagreements**, zero absences, with the remaining 16 endpoints declaring no response shape anywhere
in the source *or* in the framework's own schema. Exceptions are the weak component and the one with
no ground truth at all. Against the pre-registered **≥ 0.80** gate, the figure depends on which
reading is taken and both are reported below: **0.8696 clears it, 0.7681 misses it.** The single most
important result is not any of those numbers. It is that switching off one derivation rule — following
an alias generator declared on a base class three files away — leaves 15 of 69 endpoints (21.7%) with a
contract that is fluent, plausible, and **wrong about every field name on the wire**, with nothing in
the output to indicate it.

## Gate adjudication, stated before anything else

The gate reads: *≥ 0.80 of promoted endpoints yield a contract carrying at least parameters and return
type.* That admits two honest readings and they land on opposite sides of the line.

| Reading | Count | Rate | Against 0.80 |
|---|---|---|---|
| **Literal**: the extractor produced both components | 60 / 69 | **0.8696** | **Clears** |
| **Validated**: it produced both *and* both agree with the framework's published schema | 53 / 69 | **0.7681** | **Misses** |
| Restricted to the 53 endpoints where a return contract exists on either side | 53 / 53 | 1.0000 | (not the gate) |

The literal reading is what was pre-registered, so **the gate clears at 0.8696**. That is not a
comfortable margin and it should not be quoted without the second row, which misses. The two differ
only in their treatment of the return component, and the gap is entirely explained by 16 endpoints
whose return shape nobody declares — not the source, not the decorator, and not the framework. For
those, no verifier is constructible by any means short of running the endpoint and observing what
comes back, and constitution Principle I already prescribes what to do with them.

Both readings are reported throughout rather than one being chosen as the headline, because the
difference between "we produced a contract" and "we produced a contract that is correct" is the whole
subject of this experiment.

## Target and ground truth

`google/adk-python` at commit `f4e72334`, the same fresh index finding 004 scored: 1,867 files, 48,154
nodes, 149,714 edges. The 69 endpoints are exactly finding 004's true positives — every route the ADK
source declares with a verb decorator.

**Ground truth is the application's own OpenAPI schema.** `build_contract_key.py` instantiates the app
in each of the five constructor configurations, calls `app.openapi()`, and records for every
`(method, path)`: each input's name, location, required flag, and JSON type, with request bodies
expanded through `$ref` to field level; and the declared success-response schema. The union across
configurations is **69 operations, matching the 69 recovered routes exactly** once Starlette's path
converter suffix is normalised (`{artifact_name:path}` and `{artifact_name}` are the same parameter).
Nothing in the key was written by hand.

This schema is not documentation. FastAPI generates it from the same route table and the same Pydantic
models it uses to validate requests at runtime, so it is a statement of what the application will
actually accept and return.

**One thing the ground truth does not cover: exceptions.** OpenAPI declares response status codes, and
here it declares exactly two sets across all 69 operations — `{200, 422}` for 61 of them and `{200}`
for the other 8. It says nothing about what a handler raises. That absence is itself a result and
section 4 treats it as one.

## How the contract is derived

The route-to-handler edge comes from the codegraph index, which finding 004 established is exact on
this target. Everything downstream is derived from source with Python's `ast` module. Nothing is
executed, and no model is involved.

- **Parameters** come from the handler signature. Each parameter is classified as path, query, header,
  or body, and a parameter annotated with a Pydantic model is expanded into that model's own fields,
  walking base classes.
- **Return type** comes from three declaration sites, in the order FastAPI itself consults them: the
  decorator's `response_model=`, the `-> T` annotation, and the decorator's `response_class=`.
- **Exceptions** come from walking the handler body for `raise` statements, and then from walking the
  bodies of the functions the handler calls, one hop down.

## 1. Parameters are recovered exactly — 207 of 207 input tuples

| | Count |
|---|---|
| Endpoints scored | 69 |
| Parameter list agrees with the framework on names and locations | **69 (100%)** |
| Parameter list agrees on names, locations, required flags, **and** types | **69 (100%)** |
| Disagreements | **0** |
| Absences | **0** |
| Individual input tuples derived | 207 |
| Individual input tuples the framework publishes | 207 |
| Tuples in one set but not the other | **0** |

The 207 inputs break down as 118 path parameters, 76 body fields, and 13 query parameters, across 69
endpoints of which 8 legitimately take no input at all. Of the 207, **73 were not present in any
handler signature** — they came from expanding 14 distinct Pydantic models into their field-level
schemas, following inheritance. Six parameters were correctly excluded as framework injections
(`Request`, `WebSocket`, and similar), which FastAPI supplies rather than reading off the wire.

This is a stronger result than expected and the reason is worth stating plainly: FastAPI's entire
design premise is that the handler signature is the interface. The framework builds the schema from
the same annotations a static reader sees. **On a framework built this way, parameter derivation is
not hard, and the measurement mostly confirms that the analysis reaches the annotations rather than
that it interprets them cleverly.** Section 5 shows what happens when one piece of that interpretation
is removed, and it is not benign.

## 2. Return types: 53 agreements, zero disagreements, and 16 endpoints where no shape exists anywhere

| Outcome | Count | Meaning |
|---|---|---|
| Agrees, naming the same model | 18 | The derived type names the model the framework publishes. |
| Agrees on shape | 30 | The derived type reduces to the same JSON shape as the published schema. |
| Agrees that there is no payload | 5 | Handler annotated `-> None`; the framework publishes no response schema. A checkable statement. |
| **Disagreement** | **0** | |
| **Absence** | **0** | |
| Neither side declares anything | 9 | No annotation, no `response_model`, no `response_class`, and an empty published schema. |
| Declared, but untyped | 3 | Handler annotated `-> Any`. The framework publishes an empty schema, so the two agree that nothing is known. |
| Returns a response object | 4 | Handler returns `StreamingResponse` or similar. That declares how bytes are framed, not what shape they carry. |

**Agreement 53, disagreement 0, absence 0**, with 16 endpoints falling outside the comparison because
there is nothing on either side to compare.

Two observations that matter more than the counts.

**The derived contract is sometimes more informative than the framework's own schema, not less.** For
`POST /run_sse`, FastAPI publishes an empty response schema because the handler returns a
`StreamingResponse`. The static walk recovers all nine request body fields correctly *and* two raise
sites with status codes 400 and 404, none of which the schema mentions. Treating OpenAPI as a ceiling
rather than as a reference point would understate what is available.

**Where a return type is declared twice, the two declarations never conflicted.** Five endpoints
declare both a `response_model=` and a `-> T` annotation, and in all five they name the same type. The
disagreement this experiment was designed to catch did not occur once here. That is a clean result on
this target and, with n = 5, close to no evidence about anything else. The check is worth keeping in
the product precisely because a conflict is silent when it does happen.

## 3. Exceptions are the least recoverable component, and the only one with no ground truth

| | Count | Share of 69 |
|---|---|---|
| Endpoints with at least one `raise` in the handler body | 37 | **53.6%** |
| Endpoints with at least one `raise` within one call hop | 49 | **71.0%** |
| Endpoints with no known raise site at either depth | 20 | 29.0% |
| Raise sites in handler bodies | 66 | |
| Of those, `HTTPException` | 66 (100%) | |
| Of those, carrying a literal status code | **65 / 66** | 98.5% |

Status codes recovered from handler bodies: 400 (29 sites), 404 (23), 500 (10), 422 (2), 403 (1).

Two findings here.

**The framework's schema is silent about every one of them.** All 37 endpoints that raise something
raise a status code the published OpenAPI schema does not declare, because no route in this
application passes `responses=` or `status_code=` to its decorator — zero of 69 do. The schema
declares 200 and 422 and nothing else. **For the exception component, static analysis is strictly more
informative than the framework's own machine-generated description, and there is no authority to score
it against.** What is reported above is recoverability, not accuracy, and no accuracy claim is made.

**Going one hop down changes both the coverage and the taxonomy.** Following `calls` edges from the
handler into the functions it invokes raises coverage from 37 to 49 endpoints and surfaces exception
classes invisible at the handler: 42 `ValueError` sites, 3 `NotImplementedError`, 2 `TransientError`,
alongside 61 more `HTTPException`. A handler that raises nothing itself is not a handler that cannot
fail. This also shows the shape of the cost: exception recovery is a call-graph traversal with a depth
parameter, no natural stopping point, and no way to tell reachable raises from unreachable ones.

Only **28 of 69 endpoints (40.6%)** yielded all three components — agreeing parameters, an agreeing
return type, and at least one identified exception.

**Most recoverable: parameters, at 100%. Least recoverable: exceptions, at 53.6% from the handler and
71.0% within one hop, and unverifiable at any depth.**

## 4. The result that matters most: a contract can be confidently wrong

Every request model in this application inherits from a project-local `BaseModel` that sets
`alias_generator=to_camel`. The declaration is four lines in
`src/google/adk/cli/utils/common.py`, three files away from any handler, and it silently renames every
field of every model on the wire. `state_delta` in the source is `stateDelta` in the request body.

Switching off the rule that follows inheritance to find that configuration, and changing nothing else:

| | With the rule | Without it |
|---|---|---|
| Endpoints whose parameter list agrees | **69** | **54** |
| Endpoints whose parameter list disagrees | **0** | **15 (21.7%)** |
| Validated contracts (both components correct) | 53 / 69 = 0.7681 | 43 / 69 = 0.6232 |

The 15 wrong contracts are not partially wrong or obviously wrong. Each one carries the right number of
fields, in the right locations, with the right types and the right required flags, and every field name
is wrong in the same systematic way: `connector_name` for `connectorName`, `consent_nonce` for
`consentNonce`, `eval_set` for `evalSet`. A generated tool built from one of them would fail every
call it ever made, with a 422 the operator would most naturally read as a bug in the caller.

**This is the same failure shape finding 004 found in the docstring field, in a completely different
place.** There the extractor read the comment above a `def` and reported it as documentation; here a
derivation stops one inheritance hop short and reports the wrong wire name. In both cases the output is
well-formed, confident, and undetectable from the output alone. Two independent instances in two
consecutive measurements is enough to call it a pattern rather than a coincidence: **in a static
analysis pipeline, the dangerous failure is not the empty field, it is the populated one.**

The general lesson is narrower than "handle alias generators." It is that **a type in the source is not
the interface, and the transformation between them is declared somewhere the naive reader is not
looking** — a base class, a decorator argument, a framework configuration object, a serializer. Pydantic
alias generators, `serialize_by_alias`, Marshmallow `data_key`, Jackson `@JsonProperty`, and
`class-transformer` `@Expose` are all the same hazard wearing different clothes. Any contract the
product derives needs a validity check against something outside the derivation, not just a null check.

## 5. What each derivation rule is worth, and why that table is also a warning

Five framework-specific rules were added after inspecting what the first pass got wrong. Each was then
disabled individually to measure its contribution.

| Rule disabled | Parameter agreement | Exact incl. type and required | Validated contracts | Rate |
|---|---|---|---|---|
| *(none — all rules active)* | 69 | 69 | 53 / 69 | **0.7681** |
| `field_defaults` | 69 | **68** | 53 / 69 | 0.7681 |
| `complex_is_body` | **68** | 68 | **52 / 69** | 0.7536 |
| `aliases` | 69 | **67** | 53 / 69 | 0.7681 |
| `alias_generator` | **54** | 54 | **43 / 69** | 0.6232 |
| `response_class` | 69 | 69 | **51 / 69** | 0.7391 |
| **All five** | **53** | 53 | **40 / 69** | **0.5797** |

What each one does, and the general hazard behind it:

- **`field_defaults`** — `filename: str = Field(description="...")` assigns a value but supplies no
  default, so the field is required. Reading the presence of an assignment as a default inverts the
  required flag silently. One endpoint here; the idiom is ubiquitous in Pydantic code.
- **`complex_is_body`** — FastAPI binds a scalar-annotated parameter to the query string and a complex
  one to the request body. An extractor that defaults everything unmatched to `query` puts a body
  parameter in the wrong place. One endpoint here.
- **`aliases`** — `conversation: Optional[StaticConversation]` carries no shape until the module-level
  `StaticConversation: TypeAlias = list[Invocation]` is resolved; without it the field is typed
  `object` instead of `array[object]`. Two endpoints.
- **`alias_generator`** — section 4. Fifteen endpoints.
- **`response_class`** — `response_class=PlainTextResponse` on a handler with no return annotation is
  why FastAPI publishes `type: string`. Reading only the annotation and `response_model` misses it. Two
  endpoints, and it is the difference between the literal gate reading clearing at 0.8696 and missing
  at 0.8116.

**Now the warning.** Finding 004's central process lesson was that finding 001's verb filter, which took
precision from 74.6% to essentially 100% on one codebase, did literally nothing on the next one, because
it had been discovered by inspecting one codebase's failures after the fact. **Every one of the five
rules in this table was discovered exactly that way.** They are more defensible than the verb filter —
each corresponds to a documented, first-class FastAPI or Pydantic feature rather than a lexical
coincidence — but that is an argument, not evidence. The number that should be carried forward from this
table is not 0.7681. It is **0.5797, the all-rules-disabled figure**, as an estimate of where a
first-pass extractor lands on a framework nobody has tuned it for yet.

## 6. Signature strings alone, in both languages

Finding 001 reported that the index's dedicated `return_type` column is empty across all 63,783 nodes of
the TypeScript corpus. **That reproduces exactly on Python: 0 of 48,154 nodes.** The column is unused in
both languages, and the type information lives inside the `signature` string as unparsed text.

One parser was run over the `signature` column of both indexes so the two figures mean the same thing.
This measures whether structured parameters and a return type can be *read out of the string*. It does
not measure whether they are correct.

| | ADK Python, promoted endpoints | TypeScript monorepo, verb-filtered routes |
|---|---|---|
| Population | 65 distinct handlers behind the 69 endpoints | 742 distinct callables reachable from the 866 verb-filtered routes |
| Parameters fully structured (name and type for every parameter) | **65 / 65 = 1.0000** | **709 / 742 = 0.9555** |
| Return type present in the signature | **54 / 65 = 0.8308** | **683 / 742 = 0.9205** |
| Both components parseable | **54 / 65 = 0.8308** | **664 / 742 = 0.8949** |
| Of the return types found, resolve to a type the index declares | 19 / 54 = 0.3519 | **252 / 683 = 0.3690** |
| Of the return types found, builtins only | 31 / 54 | 291 / 683 |
| Of the return types found, name a type the index does not contain | 4 / 54 | 140 / 683 |

Two things stand out.

**The signature string is not the bottleneck; resolution is.** Both components parse cleanly for 83.1%
of Python route handlers and 89.5% of TypeScript ones, and then roughly one in three of those return
types resolves to a declared type from which a field-level schema could be built. A
`Promise<ArticleDto>` gives a name, not a shape, and 140 of the 683 TypeScript return types name
something the index does not contain at all. **`return_type` being empty is a cosmetic defect; the real
gap is that nothing resolves a named type to its fields.** On Python that gap was closed for this
measurement by walking Pydantic models with `ast`, which is why section 1 reports 100% and this table
reports 83%. The equivalent walk over TypeScript interfaces is unwritten and unmeasured.

**The corpus-wide numbers are far worse than the route-handler numbers, in both languages.** Across every
callable in each index: Python 5,800 of 21,204 (27.4%) yield both components, TypeScript 10,179 of 22,104
(46.1%). Route handlers are the best-typed code in these repositories by a wide margin, which is
convenient for this product and should not be generalised to arbitrary promoted functions.

### The TypeScript figure is a capability ceiling, not an accuracy measurement

Stated separately because it must not be read as comparable to section 1.

- **There is no ground truth.** That repository publishes no OpenAPI schema, so nothing here was checked
  against anything. A signature that parses cleanly may still be wrong about the wire format, and section
  4 is a demonstration that this is not hypothetical — the Python contracts *also* parsed cleanly while
  being wrong about 15 endpoints, and only the OpenAPI comparison revealed it.
- **The index is roughly five weeks stale** (built 2026-06-28). Treat the numbers as indicative.
- **The population is not "handlers."** Finding 001 established that the TypeScript path has no direct
  route-to-handler edge and reaches callees through generic `calls` edges, 58% of routes reaching two or
  more. The 742 callables measured therefore include loggers, validators, and serializers alongside
  genuine handlers. Whether the well-typed ones are the handlers is unknown.
- **It was read-only throughout.** The database was opened with `mode=ro`, only the `signature`,
  `return_type`, `kind`, and `name` columns were touched, no file content was read, and `git status` in
  that repository is clean.

## 7. Determinism holds

Two independent runs of the extractor over the same index produced byte-identical output across all 69
contracts (FR-007). The scoring is a pure function of two JSON files. The one non-deterministic step is
regenerating the key, which instantiates the application; it is committed so scoring can be reproduced
without it.

## What this means for the product

1. **Constitution Principle I survives as written, and the measurement supports it rather than
   straining it.** The principle requires that a promoted function emit a node contract and a verifier
   derived from its return type and postconditions, and it already specifies the fallback: *"A node with
   no derivable verifier MUST be emitted as explicitly unverified and surfaced to the operator, never
   silently backed by a model critic."* That clause is exactly the right disposition for the 16 endpoints
   here where no return shape exists on either side, and it was written before anyone knew how many there
   would be. No amendment is needed to accommodate the miss on the validated reading.

2. **But Principle I needs an addition, and section 4 is the argument for it.** As written, the principle
   partitions nodes into *has a derivable verifier* and *has none*. This measurement produces a third
   category the principle does not name: **a verifier that was derived, looks complete, and is wrong.**
   Fifteen of 69 endpoints landed there under a single rule ablation, and nothing in the artifact
   distinguished them. The proposed amendment is one sentence to the enforcement clause — *a derived
   contract MUST be validated against an independent description of the interface where one exists
   (OpenAPI, a schema file, a client SDK, a recorded request), and MUST be marked provisional where none
   does* — which strengthens the principle rather than weakening it, and is cheap now and expensive later.

3. **Contract-derived verification is achievable for parameters and mostly achievable for return types,
   and aspirational for exceptions.** The three components should be treated as three separately gated
   capabilities rather than one. A verifier that checks argument shape against a derived parameter contract
   is buildable today on this class of target with high confidence. A verifier that checks the response
   against a derived return type is buildable for roughly three quarters of endpoints. A verifier that
   asserts the *failure taxonomy* the constitution's node contract requires is, on this evidence, the
   weakest of the three, has no authority to check against, and needs an explicit confidence level attached
   wherever it is emitted.

4. **The next unit of work on the analysis layer is a type resolver, not a better parser.** Both languages
   parse their signatures fine. In both, roughly one in three route-handler return types resolves to a
   declared type. Python got to 100% on parameters only because the harness walks Pydantic models through
   inheritance with `ast` — capability that does not exist in the index and would have to be built or
   extended into it. The TypeScript equivalent, resolving an interface name to its members, is the same
   shape of work and is unwritten. **This sharpens the extend recommendation: the thing to extend is
   resolution, not extraction.**

5. **Reading the framework's own schema, where one exists, is cheaper than deriving the contract and
   strictly better for two of three components.** This measurement used OpenAPI as ground truth, and in
   doing so demonstrated that a product could use it as an *input*. Where a target publishes a schema, the
   parameter and return contract come for free and correct. Static derivation is then needed only for
   exceptions — where it is strictly more informative than the schema — and for targets that publish
   nothing. That is a materially different architecture from deriving everything, and it composes with the
   configuration-reachability check finding 004 opened, which also wants `/openapi.json`.

## What this does NOT license

- **Nothing about any framework other than FastAPI, or any language other than Python.** This is one
  framework whose central design premise is that the handler signature *is* the interface schema, measured
  against a schema that framework generates from the same annotations the extractor reads. That is close to
  the best case that exists. Flask, Django REST Framework, Express, Spring, Rails, and Go `net/http` all
  express contracts differently and several express them nowhere a static reader can see. **A 100%
  parameter result here is not evidence of a 100% parameter result anywhere else, and it would be a serious
  misreading to treat it as one.**
- **Nothing about the five derivation rules generalising.** All five were written after looking at this
  repository's failures. Finding 004 established that a filter discovered that way failed completely on the
  next codebase. The all-rules-disabled figure of 0.5797 is the honest expectation for an untuned framework.
- **Nothing about exception accuracy, at any depth.** There is no ground truth for the exception component
  and none was constructed. Every exception number in this document is recoverability. Raises reachable
  through more than one call hop, raised inside libraries, or raised conditionally on unreachable branches
  are all uncounted, and no claim is made that the recovered set is complete or that its members are
  reachable.
- **Nothing about the TypeScript numbers as accuracy.** Capability ceiling only, from a five-week-stale
  index, over a population that includes non-handlers.
- **Nothing about nested schemas.** Request bodies were expanded exactly one level. A field typed as
  another model is recorded as `object`, not as its own field list. Recursive expansion is untested and the
  cycle behaviour is unknown.
- **Nothing about `Depends()` and dependency injection.** Six parameters were excluded as framework
  injections and this application uses almost no dependency injection. On a codebase that pushes
  authentication, pagination, and tenancy through `Depends()`, a large part of the real input contract
  lives in the dependency graph and none of it would be recovered by what was measured here.
- **Nothing about which endpoints a deployment actually serves.** Finding 004's configuration-blindness
  result applies unchanged. A perfectly derived contract for an endpoint the deployment does not expose is
  still a tool that fails at runtime.
- **Nothing about whether these contracts make better tools.** No agent ran, no task was attempted, no
  model was called. Whether a field-level parameter contract improves task success over a bare function
  signature is User Story 3 and remains entirely unmeasured.

## Immediate next steps

1. **Amend constitution Principle I with the validity clause in point 2 above.** One sentence, and the
   evidence for it is section 4. Doing it before any emission code exists is far cheaper than retrofitting
   a provenance field later.
2. **Measure contract extraction on a target that expresses contracts *outside* the signature.** Flask with
   `request.json`, or Express with `req.body`, is the honest adversarial case: the interface is not in the
   signature at all, and the derivation this finding validates would recover nothing. That result is more
   informative than a second FastAPI target and costs no more.
3. **Build the type resolver, and measure it on TypeScript interfaces first.** Python's Pydantic walk is
   done and demonstrated. TypeScript's interface walk is the larger population, the one with 4,395 declared
   interfaces sitting unused in the index, and the one where 140 of 683 route-handler return types name a
   type the index does not contain — which is itself a resolution bug worth understanding before building
   on top of it.
4. **Decide whether OpenAPI is an input, not just a ground truth.** Point 5 above changes the shape of the
   analysis layer for any target that publishes a schema, and it shares its mechanism with the
   configuration-reachability check finding 004 left unowned. Both want the same fetch. Deciding them
   together is cheaper than deciding them apart.
5. **Attach an explicit confidence level to the exception component wherever it is emitted.** It is the
   weakest of the three, it has no authority to check against, and the constitution's node contract requires
   a failure taxonomy regardless. Emitting one at 53.6% coverage without saying so would be exactly the
   silent overconfidence Principle IV exists to prevent.
