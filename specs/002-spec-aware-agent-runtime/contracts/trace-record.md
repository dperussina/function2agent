# Contract — Trace Records and Measurement Artifacts

**Requirements**: FR-005, FR-006, FR-011, ~~FR-030, FR-031~~ **FR-038**, FR-039–FR-042, FR-053
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
- A `SIGKILL` mid-session: the ledger's durable state accounts for all consumption up to the kill.
- The loader rejects a corpus with an edited prompt, a changed battery version, a census mismatch, or
  a cross-battery join — four separate assertions, one per U-47 term.
- No trace contains a credential-shaped value or a readable `provider_state`.
