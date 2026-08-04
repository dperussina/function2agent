# Contract — Trace Records and Measurement Artifacts

**Requirements**: FR-005, FR-006, FR-011, ~~FR-030, FR-031~~ **FR-038**, FR-039–FR-042, FR-053,
**FR-058**
**Constitution**: Principle VI *(as amended to **v1.3.0** 2026-08-03, **OD-22** — the field list is
stated over a **traced unit** whose kind the shipping tier declares, and v1's declared unit is the
span this contract already specifies)*

---

## Span shape

Every model call, tool call, state transition and decision point is a span ~~(FR-030)~~ **(FR-038)**,
carrying inputs, outputs, timing, cost, `deployment_id`, `session_id`, `turn_index`, and the artifact
versions in force ~~(FR-031)~~ **(FR-038, FR-035)**.

> **Citation corrected 2026-08-03, and the correction is worth more than a reference fix.** This
> contract cited **FR-030 and FR-031** for the span shape. Those are the two **drift** requirements —
> FR-030 disables a drifted operation, FR-031 states what a drift *signal* must carry — and neither
> says anything about spans. The overlap that made the miscitation plausible is real but narrow:
> FR-031 does require artifact versions and deployment identity, on drift signals only. **The
> consequence was that this contract's central shape had no requirement behind it**, because the one
> tracing requirement in the specification, **FR-038**, was written per *node* and this contract is
> written per *span* — so nothing connected them. FR-038 was rewritten against the span on
> 2026-08-03 and now supplies the citation directly, including the closed span-kind set below, which
> until that rewrite existed only here.

Span kinds: `model_call`, `tool_call`, `egress_decision`, `filesystem_decision`, `state_transition`,
`verification`, `drift_check`. **This set is closed** — FR-038 forbids writing a span of an
undeclared kind — and it is the set FR-038 declares, stated here and there identically.

**Two decision spans have a required `rule_id`**, and the invariant suite fails without it:
`egress_decision` (FR-011) and `filesystem_decision` (FR-048, which requires a filesystem denial
recorded *identically* to an egress denial — the clause that forces the syscall supervisor, **Q-09**).

**Budget spans are written as consumption accrues**, not at the end, because a cgroup kill must lose
no accounting (FR-049). Reserve before the model call, reconcile after, so a crash over-counts
(**U-30**).

**`provider_state` is never written to a trace in a readable form.** It is opaque, it may contain
provider reasoning, and it is round-tripped rather than inspected (FR-037).

## The per-result output bound, on the `tool_call` span

**FR-058 adds fields and does not add a span kind**, and the two halves of that are one decision. It
bounds every result FR-004's two capabilities return, and both of those are called through a
`tool_call`, which already exists in the closed set above — so the obligation lands as a field
obligation on that span and **the seven-kind set is unchanged**. FR-058 says so in its own text, and
the reason it has to say so is the reason the set is closed at all: FR-038 forbids writing a span of
an undeclared kind, so a requirement that wanted a new kind would have to reopen the set rather than
assume it.

**Seven fields, taken from FR-058's third obligation and stated in its terms**:

| Field | What FR-058 requires it to carry |
|---|---|
| bound applied | that the bound was applied to this result |
| bound in force | the configured bound this call was held to |
| unit | the unit the bound was enforced in |
| byte proxy | whether a byte proxy stood in for that unit |
| full size | the full size of the result, before the bound |
| admitted | how much of it was admitted into the context |
| disposition | **retained**, carrying the reference, or **unrecoverable** |

The last two rows are the ones an implementation drops, and FR-058 names the consequence directly:
applying the bound is a decision about what the model was permitted to see, so **a span carrying
only what was admitted describes a result that never existed**. `full size` and `admitted` are
therefore two fields and not one, and the difference between them is the only record that anything
was withheld.

**`byte proxy` is not an implementation detail and is required by a second clause as well.** FR-058
denominates the bound in tokens because the context window is denominated in tokens, permits a byte
enforcement only where the byte figure is derived so it cannot admit more tokens than the bound, and
requires the substitution to be recorded here. So the field answers *was this bound enforced in the
unit it was written in* — and a trace of a run whose tokenizer was unavailable is otherwise
indistinguishable from one whose tokenizer was not.

**`disposition` is where the reference lives.** FR-058's first obligation rules out an object handle
— the capabilities return bytes across an enforcement boundary and there is no in-process object to
point into — so a retained remainder's reference is a path inside FR-048's declared filesystem set,
and that path is what this field carries. Two consequences worth stating because they are easy to
implement wrongly. The `rule_id` obligation above does **not** extend here: this is a `tool_call`,
not one of the two decision spans, and nothing in FR-058 names a rule. And FR-058 requires the
retention location not to outlive the session, so **a retained reference in a trace read after the
session has ended names a path that is gone** — the span records where the remainder was, not a
remainder that can still be fetched, and any analysis that resolves these paths has to run inside
the session's lifetime or accept misses.

> **Written on every such span, not only where the bound bit — and this is a reading, recorded as
> one.** FR-058 says *the span for the call* without restricting itself to calls that reached the
> bound, and the sibling precedent is FR-038's own fourth bullet, which requires the decision and
> its matched inputs for **every** egress and filesystem decision *"and not only for denials,
> because a permit resolved by the wrong rule is the case an attribution has to be able to find"*.
> The same argument transfers unchanged: a bound recorded only where it bit cannot distinguish a
> result that fitted from a bound that was never applied, which is the vacuous-instrument shape this
> corpus keeps finding. Where nothing was withheld, `admitted` equals `full size` and that equality
> is the signal; **no third disposition value is invented here**, because FR-058 names two and a
> contract is not the place to mint a third.

**The span does not discharge FR-058's disclosure obligation, and nothing above should be read as
though it does.** FR-058 has three obligations and only the third is a trace obligation. The second
is a disclosure obligation on **the bytes the model reads**: the result itself must state that it is
bounded, its full size, how much was admitted, and either the reference or that the remainder is
unrecoverable. FR-058 forecloses the substitution in as many words — *a disclosure recorded anywhere
other than in the result does not discharge this* — and the reason is that the model is a reader
that arrives at the result and at nothing else. **A trace is read by an operator, after the fact,
somewhere else.** Four of the seven fields above — that the result was bounded, its full size, the
amount admitted, and the reference or its absence — are therefore written twice, to two different
readers, in two places; the bound in force, the unit and the byte proxy are owed to the trace only.
An
implementation that emits a correct span and a silently shortened result satisfies this contract and
violates FR-058. That surface belongs to [`result-record.md`](./result-record.md)'s neighbours
rather than here; what belongs here is the boundary.

## Measurement artifacts: the U-47 terms

**U-47** records a hash-pinned trace corpus that rebased onto edited prompts while every hash check
kept passing — the corpus's own instance of a measurement artifact quietly ceasing to describe what
it claimed. FR-053 makes the fix a requirement, and all four terms are adopted verbatim.

1. **The prompt and request text live inside the trace record**, so the artifact is self-contained
   and cannot be rebased by editing a file it points at.
2. **The battery version and task-file hashes are pinned in the freeze.**
3. **The cross-battery census is pinned as an invariant** and re-checked on load, so a corpus that
   has silently changed shape fails rather than reports.
4. **The analysis path refuses a cross-battery join** rather than performing one.

A loader that cannot satisfy all four **fails**. It does not warn.

## Fixtures are committed with the capability

FR-053 requires the fixture alongside the capability, not assembled when the measurement falls due.
Committed in `tests/fixtures/`: analyzer repositories with known-correct expected output; the two
drift corpora (source-changes and deployment-changes, each controlling its own change time); the
adversarial batteries for SC-002 and SC-003; the credential-replay fixture with both arms; the
effect-gate corpus with its state-diff oracle.

## Measurement tables

`JudgeVerdict`, `HumanLabel`, `EffectGateObservation` and `BatteryRun` are defined in
[`../data-model.md`](../data-model.md) §3. They are **structurally apart** from the success path: no
success-path table references them and no success-path module imports the modules that write them.

`HumanLabel` exists because FR-040's third gate branch reads the judge's own discrimination, which
needs ground truth the verifier cannot supply without circularity. The corpus records that the one
human adjudication pass it needed **was never performed**. See [`../plan.md`](../plan.md) Complexity
Tracking row 1.

## Tests owed

- Every span kind emitted on a full session; no decision span missing a `rule_id`.
- A result driven past the bound on each of FR-004's two capabilities: the `tool_call` span carries
  all seven FR-058 fields, `full size` exceeds `admitted`, and the span kind is still `tool_call`.
- The same call with a result that fits: the fields are present anyway and `admitted` equals
  `full size`. Without this assertion an implementation that writes them only at the bound passes.
- The unrecoverable branch — retention refused because its own declared bound is reached — records
  `unrecoverable` and no reference.
- A run with no tokenizer available: `byte proxy` is set and `unit` says what was enforced.
- **The disclosure obligation is asserted against the returned bytes, not against the span**, and
  the two assertions are separate: a fixture emitting a correct span beside a result that reads as
  complete must fail. One test that reads only the trace would pass it.
- A `SIGKILL` mid-session: the ledger's durable state accounts for all consumption up to the kill.
- The loader rejects a corpus with an edited prompt, a changed battery version, a census mismatch, or
  a cross-battery join — four separate assertions, one per U-47 term.
- No trace contains a credential-shaped value or a readable `provider_state`.
