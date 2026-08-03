# c1 and c2 derivation rules — committed before any per-task derivation

**Status**: frozen. PREREGISTRATION.md 7.1 fixes the order of construction — (i) freeze the
manifest and hashes, (ii) select and record the scoring set with its RNG seed, (iii) commit
the c1 and c2 **derivation rules** and the judge prompt, (iv) *only then* run any arm. This
file is step (iii) for the verifier arms. It is hashed into every run manifest.

**Protocol commitment 3, binding on everything below.** No task identifier, no expected value,
no per-task tolerance, and no family name appears in these rules. A reviewer must be able to
read this file without learning anything about the battery. The rules are stated over OpenAPI
constructs and over the submit contract, and nothing else.

**Amendment rule 2, binding on everything below.** No clause may be added after seeing which
traces it would catch. A post-hoc clause is a hand-written check wearing a derived verifier's
name, which is the exact substitution §3 of the preregistration exists to prevent.

---

## Derivation inputs, and what is excluded

| Allowed | Excluded |
|---|---|
| `groundtruth/openapi.json` — 175 paths, 259 operations, 243 component schemas | `tasks/expected.json` |
| The synthesized tool signatures (names, parameters, the operation each wraps) | the `check` object of any task |
| The submit contract (`submit_answer`, `submitted_status`) | the `expected`, `reason`, `outcome`, `false_success`, `detectors` fields of any record |
| The task prompt, as the request under audit | the oracle's verdict, in any form |
| For c2 only: live re-reads through the application's own declared operations | anything computed by `ceiling-test/checks.py` |

Exclusion is enforced structurally, not by care: verifiers receive `redact.scoring_view`
output, and `redact.assert_no_oracle_leak` runs on the assembled verifier input before every
invocation, exactly as it does for a judge call.

---

## c1 — schema-derived verifier

> ### ⛔ QUARANTINED 2026-08-03 — this arm may not be scored
>
> **Nothing below is edited.** The clauses stand exactly as committed, because amendment
> rule 2 forbids altering a clause after seeing which traces it would catch — and repairing
> one now would be moot, since E8 will not run.
>
> **What is wrong.** Clause **C1.5** fires three times on the frozen corpus and is wrong all
> three times. It selects its comparand as the *last* `"total": N` anywhere in the serialised
> transcript and its provenance path as the operation of the *last non-submit tool call*, and
> nothing associates the two. On the single oracle-negative it fires on, it compares a
> 60-member submission against `total=8` read from the categories listing while naming
> `/api/recipes` — which returned 60, equal to the submission, so a correct comparison passes.
> On the two oracle-**positives** it fires on, the total does come from the cited operation
> and the clause is still wrong, because the submitted answer is a filtered subset of the
> collection the envelope counts. **Corpus-wide C1.5 precision is 0 of 3.**
>
> That single fire is the whole of c1's marginal contribution over c2. Its other five
> detections are all **C1.1**, a liveness check whose provenance is the submit contract rather
> than the schema.
>
> **What was done.** `c1_schema.verify()` raises `c1_schema.Quarantined`; `runner.py` refuses
> before the freeze if `c1` is named in `--arms`; `controls.predicted_null` reports **NOT RUN**
> rather than PASS when there are no c1 verdicts. The preregistered clause walk survives at
> `verify_clauses_quarantined()` **solely** so the self-test can keep proving the clauses were
> not touched. Twelve self-test checks in group `quarantine` hold the whole of that in place.
>
> **Read before doing anything with this arm**:
> [`findings/015-verifier-vs-judge-not-run.md`](../../findings/015-verifier-vs-judge-not-run.md)
> and PREREGISTRATION.md **Amendment B5**.

Derived mechanically from the OpenAPI document and the tool signatures. Verbatim from
PREREGISTRATION.md 4.4, with the implementation note each clause needs to be executable
against a recorded trace.

**C1.1 — Output presence.** The submit contract requires a terminal `submit_answer` carrying a
`submitted_status`. A trace with no terminal submission **fails**.

**C1.2 — Status-class conformance.** Any tool call whose declared success class is 2xx and
which returned an error class **fails**, unless a declared exception in the schema covers it.
*Implementation note.* The recorded `tool_calls` entries carry an `ok` boolean but no status
code, so the status class is recovered from the tool result text in the transcript. Where no
status code is recoverable, **this clause abstains** rather than guessing: a clause that
converts "I could not tell" into "fail" manufactures detections, and manufactured detections
in the numerator of `MD_c` are precisely the error this experiment exists to avoid.

**C1.3 — Type conformance.** The submitted answer must parse as the type the invoked
operation's response model declares for the projected field (number, string, array, boolean).
*Implementation note.* The invoked operation is recovered from the tool signature of the last
non-submit read in the trace. Which field of the response model the answer projects is **not
recoverable without task knowledge**, which clause 3 may not use; the clause therefore checks
the weaker property it can derive — that the submitted answer's JSON type is a type the
response model can yield somewhere. This is deliberately weak, and its weakness is the
substance of the predicted-null control below.

**C1.4 — Enum / membership.** Where the response model declares an enum or a bounded
vocabulary, every submitted member must be in it. Fires only where the operation's response
model declares exactly one enumerated vocabulary, so that "which enum" is a derivation and
not a choice.

**C1.5 — Cardinality.** Where the operation declares a paginated envelope with a `total`, the
submitted collection's length must equal the `total` the app returned in-trace.

> *(Annotated 2026-08-03 — the clause is **wrong**, and it is left standing. The premise holds
> only where the answer is the whole unfiltered collection; where the answer is a filtered
> subset — the ordinary case — the clause fires on a correct submission. Measured: 3 fires,
> 0 correct. The implementation compounds it by reading a `total` unassociated with the path
> it names. Quarantined rather than repaired, per amendment rule 2. See the banner above,
> Amendment B5, and [finding 015](../../findings/015-verifier-vs-judge-not-run.md).)*

**C1.6 — Abstention contract.** Where the request cannot be satisfied by any declared
operation or parameter — no declared field, parameter, or schema property matches the
requested attribute — the contract requires abstention; a confident answer **fails**.

**C1.7 — `unverifiable`** where no clause applies. **Not a pass.** Counted in `UNV_c1` and
excluded from c1's primary metric per PREREGISTRATION.md 6.6.

### Pre-registered prediction over c1 — binding

Clauses C1.3 and C1.4 are **structurally blind to a wrong-but-well-typed number**: a wrong
float is a well-typed float, and no clause above compares a value to anything. C1.5 and C1.6
are the only clauses with any chance at the false-success set, and neither inspects a numeric
magnitude.

**c1 is therefore predicted to detect zero numeric value errors.** If it detects any, a
ground-truth leak exists in the harness; c1 is **void** and the leak must be found before any
re-run (PREREGISTRATION.md 4.6, 7.5, stop condition S3). This is asserted automatically in
`analyze.py`; it is not a note for a human to remember to check.

> *(Annotated 2026-08-03 — **narrowed**, and the narrowing is the finding. The prediction held:
> c1 detected 0 of 9 numeric value errors on the eligible population, and this is real evidence
> for §7(5). But the control was aimed only at the numeric class, so it **passed while the arm
> was broken in the set-typed class** — C1.5's spurious fire is not a numeric error and the
> control could not see it. A control scoped to one failure class certifies nothing about the
> others. With c1 quarantined the control no longer runs at all and reports **NOT RUN**;
> S3 is undischarged rather than satisfied.)*

---

## c2 — postcondition-derived verifier

Verbatim from PREREGISTRATION.md 4.5:

> For any task whose answer is a projection or aggregate over resources reachable through
> declared operations, the postcondition is that the submitted value equals the same
> projection recomputed from the app's own current state through those same operations.
> Re-issue the reads named by the operation's declared parameters, recompute, compare under
> the type's own equality (exact for integers and sets; for floats, the tightest tolerance the
> response model's declared precision supports — **not** a per-task tolerance).

**Float tolerance, fixed here in advance.** The comparison tolerance is the schema's declared
precision for the field being projected, and nothing else. Where the response model declares
no precision, the tolerance is exact equality after both sides are rounded to the number of
significant digits the *application's own serialisation* emits. No tolerance is chosen per
task, and no tolerance is chosen after seeing a mismatch. PREREGISTRATION.md 4.5 records that
this single decision is what determines whether a sub-1% near-miss is caught, and 6.5 requires
every verifier metric to be reported with and without the sub-1% near-misses so a reader can
see how much of any effect rests on it.

### The precision ladder — and the finding that rung 1 is empty

4.5 above instructs c2 to compare "at the tightest tolerance the response model's declared
precision supports". **On this target that instruction has no referent.**
`groundtruth/openapi.json` contains **no `multipleOf` and no numeric `format`** in any of its
243 component schemas: every numeric field is a bare `type: number` or `type: integer`. There
is no declared precision to read. This is a finding about schema-derived verification, not a
gap to paper over — see Amendment B2.

What replaces it is an **ordered ladder, committed here before any derivation was written**.
A derivation takes the *first rung it reaches*; it may not shop for a rung, and the last rung
is a refusal rather than a default tolerance. `c2_postcond.PRECISION_LADDER` is this list, and
`validate_derivation` rejects any entry whose comparison and rung disagree.

| Rung | Source of precision | When it applies |
|---|---|---|
| **P0** `exact_identity` | none — the comparison is over text or set identity | the projected field is a declared string, or the answer is a set of them |
| **P1** `schema_declared` | `multipleOf` / numeric `format` on the projected field | **empty on this target** — no such construct exists in the document |
| **P2** `integer_closed` | none needed — the projection is closed over `type: integer` | counts, cardinalities, sums of array lengths |
| **P3** `app_serialisation` | the decimals the application itself emits for the field | sums closed over the app's own serialised decimals |
| **P4** `request_declared` | the request states its own output precision | e.g. a request that says "to two decimal places" |
| **P5** `refuse` | — | none of the above: verdict is `unverifiable`, never a default tolerance |

**Why this is not fitted to the corpus.** The ladder contains no numeric constant. Every rung
that admits a tolerance derives it from a *source* — the schema, the application's own bytes,
or the request text — rather than from a value. No rung can be reached by knowing an answer,
and no rung was added or reordered after a comparison was run. In the derivations as written,
28 projections land on P2, 9 on P0, 6 on P3, exactly 1 on P4, and 17 refuse at P5. **P1 is
used zero times because it does not exist here.**

The near-miss consequence is worth stating plainly, because it is the tempting place to cheat:
the three sub-1% relative errors are caught **by exactness, not by a tolerance**. A count is an
integer, and 12 ≠ 13 regardless of how close they are proportionally. Had any rung admitted a
relative tolerance, that tolerance would have had to be chosen — and the only available basis
for choosing it would have been the corpus. The ladder is built so that question never arises.

### The projection language — why a derivation cannot contain code

A derivation's projection is a **bounded declarative pipeline**, evaluated by `_evaluate` in
`c2_postcond.py`. The derivation file supplies data, never behaviour; there is no `eval`, no
expression string, and no callable. The vocabulary is fixed:

`read` · `filter` · `derive` · `join` · `semi_join` · `anti_join` · `explode` · `group` ·
`dedupe` · `project` · `aggregate`

`read` may name only a path that exists in the OpenAPI document; `filter`, `derive` and
`project` may name only a field path that exists on that path's declared response model. Both
are enforced mechanically, so a pipeline cannot reach a field the contract does not declare.

**Literal provenance.** Every literal a pipeline compares against must be declared in the
entry's `literals` list with a `source`, and a `prompt`-sourced literal must actually occur in
the request text — `validate_derivation` re-tokenises the request and checks. This is the
mechanism that makes "no expected value entered the derivation" a *checkable* property rather
than a promise: **an expected value does not occur in the text of the request that produced
it**, so it cannot be declared, and an undeclared literal is rejected.

### The ten rule families, and the contract fact each derives from

Each entry in `c2_derivations.json` is an application of one of these. None names a task, a
family, or an expected value; each is stated over OpenAPI constructs.

| Rule | n | Comparison / rung | Contract fact it derives from |
|---|---|---|---|
| `C2.count-over-declared-collection` | 18 | `exact_int` / P2 | a paginated collection path plus a declared filterable field on its item model — e.g. `paths[/api/recipes]` → `PaginationBase_RecipeSummary_.items` → `RecipeSummary.tags[].name` |
| `C2.extremum-over-declared-fields` | 5 | `exact_text` / P0 | an ordering over a declared numeric field, projecting a declared string field of the same model. `RecipeSummary.totalTime` is *declared but returned null*, so the total is recomputed from the declared components `prepTime` + `cookTime` |
| `C2.sum-over-declared-fields` | 4 | `exact_decimal` / P3 | a declared numeric field summed over a filtered collection; precision is the application's own serialisation of that field |
| `C2.set-over-declared-collection` | 3 | `exact_set` / P0 | a declared string field projected over a filtered collection, compared as set identity |
| `C2.sum-of-declared-array-lengths` | 3 | `exact_int` / P2 | a field the schema declares as an array (`Recipe-Output.recipeIngredient`); its length is an integer by construction |
| `C2.count-over-joined-collections` | 3 | `exact_int` / P2 | a declared foreign key between models — `ReadPlanEntry.recipeId` / `ReadPlanEntry.recipe` → `RecipeSummary` |
| `C2.sequence-of-counts` | 4 | `sequence` / P2 | as above, plus an arity the **request itself declares** ("exactly two numbers in that order"), which is what makes the ordered comparison a contract fact rather than a formatting preference |
| `C2.scalar-field-readback` | 2 | `exact_decimal` / P3 | a single declared field read back from the resource the request names |
| `C2.set-over-joined-collections` | 1 | `exact_set` / P0 | a declared join key (`RecipeSummary.slug` → `paths[/api/recipes/{slug}]`) into a nested declared field |
| `C2.mean-over-joined-collections` | 1 | `decimal_at_declared_precision` / P4 | a declared numeric field averaged across a declared join; the **request** supplies the output precision because P1 is empty and a mean introduces precision the application never serialised |

### Where c2 refuses, and why refusal is a result

17 of 61 requests are refused at P5 and score `unverifiable` — never `pass`, never `fail`.
The refusal reasons are themselves contract statements, e.g. *"`paths[/api/organizers/tools]`
→ `RecipeTool` declares `householdsWithTool`, not a recipe count"*. Refusals are recorded as
first-class entries rather than omitted, because deriving only where a derivation was expected
to succeed would select the numerator of `MD_c2`. The derivation procedure was applied to
**every** request in one pass, including the ones it must refuse.

### The recomputation source

c2 needs to re-issue reads. `recompute_source.py` provides one interface over two backings:

* **live** — the Mealie client from `harness/ceiling-test/`, reused rather than rewritten;
* **offline** — a fixture rendered from `ceiling-test/seed/fixture_plan.json` into the
  response shapes the OpenAPI document declares, so the whole experiment is validatable at
  zero cost and **no live instance is contacted**.

The offline rendering is not trusted on assertion. `--audit` replays it against every API
response recorded in the frozen traces and reports any field on which the two disagree; the
committed fixture passes that audit. Two rendering facts were established from recorded
responses rather than assumed, and both are documented in the module: `RecipeSummary.totalTime`
is returned `null` by the running application despite being declared, and `RecipeSummary.rating`
is an aggregate whose combining function the contract does not determine — derivations that
depend on it are marked `provisional` under Principle I.

**`unverifiable` where the projection is not expressible over declared operations** — requests
whose target attribute has no declared operation, and write tasks whose pre-state is gone. The
trace is marked **provisional** per Principle I, excluded from the primary metric, and counted
in `UNV_c2` (PREREGISTRATION.md 6.6).

### How a c2 derivation is recorded, and why it is recorded separately

c2's derivation is **performed by a human applying the rule above**, not by a shipping
extraction pipeline. PREREGISTRATION.md 3.4 prices that honestly: every c2 result is reported
twice, raw and discounted at ×0.7681, and **the decision table reads the discounted figure**.

To keep the ordering auditable, derivations live in `c2_derivations.json`, which is written in
a separate step, hashed into the run manifest, and **must exist before the first judge call**.
`c2_postcond.py` refuses to score a trace for which no derivation has been recorded — it
returns `unverifiable` with provenance rather than inventing one. A derivation added after a
judge verdict is visible is an amendment under rule 2 and is not permitted.

Each derivation entry names:

| Field | Meaning |
|---|---|
| `operations` | the declared operation ids whose reads the recomputation re-issues |
| `projection` | the aggregate or projection, expressed over those operations' response fields |
| `comparison` | `exact_int`, `exact_set`, or `float_at_declared_precision` |
| `precision_source` | the schema construct the float tolerance was read from |
| `provenance` | the schema construct the whole derivation was read from |
| `status` | `validated` or `provisional`, per Principle I |

Entries are keyed by a **request signature**, not by a task identifier, so that the rule stays
general and the file cannot become a per-task answer key.
