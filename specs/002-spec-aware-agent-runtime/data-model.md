# Phase 1 Data Model — Spec-Aware Agent Runtime

**Feature**: `002-spec-aware-agent-runtime` | **Date**: 2026-08-03 | **Phase**: 1 (`/speckit-plan`)

**Spec**: [`spec.md`](./spec.md) · **Plan**: [`plan.md`](./plan.md) · **Phase 0**:
[`research.md`](./research.md)

---

## Scope of this document

The entities behind the specification's Key Entities section, with the fields the requirements
actually force, the lifecycles that carry named terminal states, and the invariants that are
machine-checked rather than asserted.

Two conventions apply throughout and are not repeated per entity.

**Every persisted row carries `tenant_id` and `deployment_id`** from the first commit. FR-035 and
**OD-08** require namespaceable storage while exactly one tenant exists, because retrofitting it is a
migration rather than a change.

**Every artifact is content-addressed over a canonical serialization** (T-12). The hash covers the
payload only. Timestamps, paths and hostnames live in an envelope beside the hash, never under it,
because a hash that changes when nothing changed is read by FR-028 as source drift.

Storage is SQLite in WAL mode plus an `objects/<sha256>` payload store (T-06, **Q-02**), behind one
repository interface. **Writer ownership is single per table** across the three processes, because
finding 006 explicitly did not test the session service under concurrent writers.

| Table group | Sole writer | Readers |
|---|---|---|
| session, lease, capability | supervisor | runtime, proxy |
| turn journal, budget ledger, trace, result, drift signal | runtime | analysis (read-only), reporting |
| artifact, artifact ref | analysis | runtime, proxy |
| proxy decision log | proxy | runtime (ingests into trace) |
| judge verdict, human label | shadow judge / adjudication queue | reporting only — **never the success path** |

---

## 1. Analysis-side entities

### 1.1 `Deployment`

The admitted pairing of a running application and the source ~~that produced it~~ **the operator
declares produced it**. Created by admission (FR-001, FR-002, ~~FR-003~~ **FR-057**), and nothing
downstream exists without one.

| Field | Notes |
|---|---|
| `deployment_id` | stable identity carried by every artifact, trace, signal and report (FR-031) |
| `source_ref` | repository and commit — the source clock's anchor. **Required configuration and an operator declaration, never verified** (FR-057) |
| `target_base_url` | the target's real origin. **Held by the enforcement point and the drift scheduler. Never presented to the agent** (T-09) |
| `pinned_addresses` | resolved host and port set, pinned at admission (FR-016) |
| `published_spec_artifact` | the target's own specification. An admission criterion (FR-002), and the independent artifact that validates derived contracts (T-14) |
| ~~`correspondence_evidence`~~ **removed 2026-08-03** | ~~what established that this source produced this deployment (FR-003)~~ **The field had no producer. See the note below** |
| `admission_state` | `admitted` \| `refused`, with the reason and the missing criterion on refusal |

> **Corrected 2026-08-03. This entity claimed an admission step that no requirement stated and no
> mechanism performs.** Two things were wrong and they are different sizes. The small one: **FR-003
> was miscited** — it is the access-path requirement (act through the target's external interface,
> not in process, not into its datastore, from **D-01**) and says nothing about source commits. The
> large one: **`correspondence_evidence` had no producer anywhere in v1.** Nothing reads a commit
> identity from a running instance, and **OD-06** is why nothing does — reachability sits above
> analysis specifically so that analysis stays rebuildable from the codebase alone, and a verified
> deployment-to-commit binding would reintroduce the running-deployment dependency that decision
> removed. A field that can only ever be empty, on the entity gating every session, invites a
> downstream reader to treat an empty value as a passed check.
>
> **`source_ref` stays, and is now required rather than assumed**: FR-028 and FR-031 model two
> clocks, and the source clock has no anchor without it. **FR-057** states it, requires it as
> configuration, and requires it to be carried and presented as an **operator declaration**.
> Divergence between the declared source and the running deployment is detected afterwards by the
> drift machinery (FR-028–FR-031, FR-046) — that is detection of divergence, not establishment of
> correspondence. A wrongly declared `source_ref` is a **named residual risk** carried in
> [`spec.md`](./spec.md), not something admission catches.

**Invariant.** No session may start against a deployment that is not `admitted`. Enforced at the type
level: the session constructor takes an `AdmittedDeployment`, which has no other constructor.

### 1.2 `Artifact` and `ArtifactRef`

FR-054 enumerates eight kinds. `Artifact` is the immutable content-addressed payload; `ArtifactRef`
is the mutable pointer a deployment currently uses, which is what makes rollback a pointer move.

| `Artifact` | Notes |
|---|---|
| `content_hash` | `sha256` over the canonical serialization. The primary key |
| `kind` | `served_operation_set` \| `derived_contract` \| `derived_check` \| `effect_rule_set` \| `location_set` \| `bound_set` \| `config_snapshot` \| `codegraph_index` |
| `schema_version` | independently versioned; a breaking change is a MAJOR bump (FR-034) |
| `produced_by` | tool and version, including `codegraph`'s pinned version and asserted schema hash (**U-04**) |

`ArtifactRef` is `(deployment_id, kind) → content_hash`, with history retained so a previous
configuration is restorable in one operation (FR-054).

**Invariant.** Serializing the same logical artifact twice produces byte-identical output. Tested by
analysing one fixture twice and comparing bytes, not hashes — comparing hashes would hide a
serializer that is stable only within a process.

### 1.3 `DerivedContract` and `DerivedCheck`

Produced statically from source. **No model participates** (T-13, FR-023).

| Field | Notes |
|---|---|
| `operation_key` | method and path template, the join to the served-operation set |
| `derivation` | the independent path — the recomputation FR-023 requires and FR-024 forbids sharing a source with the reported value |
| `provenance` | which source construct produced it |
| `validation_state` | `validated` when it agrees with `published_spec_artifact`, else `provisional` (FR-026, Principle I as amended at v1.1.0) |
| `confidence` | present and required whenever `provisional` |

**Invariant.** A `provisional` contract may produce a result whose verification state is
*not verifiable*, never *verified*. Enforced at the type level rather than by a check.

### 1.4 `ServedOperationSet` and `EffectRuleSet`

What the deployment actually serves (the deployment clock), and the rules that resolve a call's
effect tier.

`ServedOperationSet` entries carry the method, the path template, and the specification metadata that
operation declared — the metadata the effect-gate corpus later labels against (§4.2 of
[`research.md`](./research.md)).

`EffectRuleSet` entries carry a **rule identifier**, a matcher, a resolved tier, and the reviewable
justification FR-012 requires. The deny list of known side-effecting reads lives here.

**Invariant.** Every rule has an identifier, and every disposition the enforcement point records
names one. Machine-checked; a disposition with no rule identifier fails the invariant suite, because
FR-011 makes the rule part of the record and not an annotation on it.

**Not a tool catalogue.** This set is data the enforcement point resolves against. Nothing generates
tools from it — **OD-09**.

---

## 2. Runtime entities

### 2.1 `Session`

| Field | Notes |
|---|---|
| `session_id` | the key for the scratch volume, the cgroup, the namespace and the capability |
| `state` | see the lifecycle below |
| `terminal_state` | a **named** member of the taxonomy, never a generic failure (FR-006) |
| `lease_expires_at` | renewed by the supervisor; the mechanism that makes a crash revoke authority (§3.3) |
| `budget` | the four declared ceilings of FR-005 |

**Lifecycle — the shape.**

```text
CREATED ─▶ RUNNING ─┬─▶ TERMINATED  ⟨terminal_state⟩   one named member, and no edge out
                    │
                    └─▶ INTERRUPTED ─▶ RUNNING          resume — the same session, FR-007
```

One non-terminal state, one resume edge back to it, and **no edge out of `TERMINATED`**: a revived
session would carry a second outcome for a run FR-006 says already has one. Which member the
`terminal_state` column holds is the table below and not the picture.

**Lifecycle — the terminal states.** This table is a **derived view of
[`src/contracts/terminal.py`](../../src/contracts/terminal.py)'s `TAXONOMY`**, which is authoritative
for membership under FR-006 — **OD-26**. `check_corpus.py`'s `lifecycle-taxonomy` check reconciles the
two and errors in either direction, so a member added there and not here fails the gate, and so does a
row here that names no member.

| Terminal state | Requirement | Status |
|---|---|---|
| `terminated.completed` | FR-006 | member |
| `terminated.turn_ceiling_reached` | FR-005 | member |
| `terminated.token_ceiling_reached` | FR-005 | member |
| `terminated.wall_clock_ceiling_reached` | FR-005 | member |
| `terminated.spend_ceiling_reached` | FR-005 | member |
| `terminated.memory_bound_exhausted` | FR-049 | member |
| `terminated.cpu_bound_exhausted` | FR-049 | member |
| `terminated.process_bound_exhausted` | FR-049 | member |
| `terminated.capability_lapsed` | FR-050 | member |
| `terminated.operator_terminated` | FR-006 | member |
| `terminated.unrecoverable_fault` | FR-006 | member |
| `terminated.no_progress` | FR-006 | owed — **T067**, predicate unwritable as specified |
| ~~`terminated.denied_operation`~~ | — | struck — **OD-26**, 2026-08-05 |

**`member` means the taxonomy carries it; `owed` means it does not yet and a task says so; `struck`
means it never will.** The check reads all three in the forbidding direction as well as the
permitting one, so an `owed` row whose member has since landed fails the gate rather than going quiet.

> **Five corrections here, all dated 2026-08-05, and the reason they were all found at once is that
> nothing had ever read this section against the code.**
> [Finding 027](./findings/027-lifecycle-edge-set-divergence.md) took the census; **OD-26** settled
> which artifact wins; `check_corpus.py`'s `lifecycle-taxonomy` check is what stops it recurring, and
> it was written and observed firing on every one of these before any of them was repaired.
>
> **① The lifecycle had no `TERMINATED` state at all.** Every branch out of `RUNNING` was labelled
> with a terminal-state *name*, so this diagram had nothing for the code's `STATE_TERMINATED` to
> correspond to, and the question *"does §2.1 declare a `RUNNING → TERMINATED` edge"* had no literal
> answer in its own vocabulary. The shape above now says what the code implements: **one** edge,
> carrying a `terminal_state`.
>
> **② Three members the runtime already reaches were missing** — `terminated.capability_lapsed`,
> `terminated.operator_terminated` and `terminated.unrecoverable_fault`. The last has been the
> runner's teardown state for an unclassifiable fault since **T046**, with its own arm in the suite,
> and it was as absent from here as the other two. That asymmetry is what decided OD-26: a rule
> reading this diagram as the closed set would, applied evenly, have invalidated a path that ships.
>
> **③ The bare label `completed` is now `terminated.completed`.** Every other branch carried the
> prefix; the odd one out is the one the invariant suite's `name.startswith("terminated.")` assertion
> would have rejected if anything had read it off this diagram.
>
> **④ ~~`terminated.denied_operation`~~ is struck rather than owed, on OD-26's grounds.** A refusal by
> the egress enforcement point or by the supervisor's filesystem decision is **a disposition the loop
> continues past**, not an outcome of the session — **SC-022 counts denials as records**, and
> [`contracts/filesystem-decision.md`](./contracts/filesystem-decision.md) scores the criterion on the
> record's existence rather than on the session ending. FR-006 names exactly one producer of its own,
> the stall condition below, and no requirement in this specification wants a denial to be terminal.
> A terminal state for one would make the *first* refusal fatal.
>
> **⑤ `terminated.no_progress` is owed, not struck, and the difference is deliberate.** Its predicate
> is *unwritable as specified* under [`tasks.md`](./tasks.md) **T067** — a recorded debt, and striking
> it would convert a gap something is tracking into one nothing is.

**Invariants.** Only `RUNNING` with a live lease is honoured by the enforcement point. A resumed
session keeps its `session_id` and its capability handle; resume renews the lease and never issues a
new capability. Every exit is a named member of the taxonomy — the suite fails on a terminal state
not in it, which is what stops a generic failure from being introduced later.

> **`terminated.no_progress` gained a definition 2026-08-03 and it lives at FR-006, not here.** This
> lifecycle named the state and called it *"the FR-006 stall condition"*, and FR-006 defined no stall
> condition — so the one member of this taxonomy with no producer was the one this diagram implied
> was already specified. FR-006 now defines progress per turn, requires the consecutive-turn count as
> configuration with no default, and records why an unset count fails startup even though FR-005's
> turn ceiling would bound the session anyway.

### 2.2 `TurnRecord`

| Field | Notes |
|---|---|
| `turn_index` | dense and monotonic |
| `provider` | which provider produced the turn |
| `provider_state` | **opaque bytes, ours, above the adapter** (T-02, FR-037). Captured verbatim, re-injected verbatim, never merged across providers, never interpreted |
| `tool_calls[]` | in the **provider's declared index order** (T-08) |

**Invariant, and it is the one finding 006 makes non-obvious.** Where several tool calls are executed
concurrently, they are journalled and recorded in declared index order and never in completion order,
and shared state is merged by an explicit per-key rule. Finding 006 measured completion-order fan-out
producing **5 distinct orderings in 8 runs** and a **silent lost update** on a shared key. Those were
read as graph properties; every provider in SC-010's set emits parallel tool calls in a single turn,
so a single-agent loop has the same hazard.

### 2.3 `JournalEntry` and `BudgetLedgerEntry`

The write-ahead intent journal, keyed `(session_id, turn_index, step_index)` with an idempotency key
per effectful step: intent committed before the effect, outcome committed after (T-07).

The ledger is **reserve-then-reconcile** — reserved before the model call, reconciled after — so a
crash over-counts rather than under-counts. **U-30** records that nothing in the stack supplies a
spend ceiling surviving a crash and resume, and the failure direction is the whole point.

**Invariant.** Consumption is durable outside the container before the effect that consumes it, so a
cgroup kill loses no accounting. This is what FR-049's "work already performed still counts" needs.

### 2.4 `CapabilityHandle`

The environment's entire authority. See [`research.md`](./research.md) §3.3.

| Field | Notes |
|---|---|
| `handle` | **opaque random bytes. Not a claim, not signed, nothing offline-verifiable** |
| `session_id` | resolved by the enforcement point on **every** request |
| `socket_path` | a per-session listener whose descriptor the supervisor holds open |

**Invariants.** The enforcement point honours a handle only when its session is `RUNNING` **and** the
lease is unexpired. A handle presented after termination is denied and the denial recorded like any
other FR-011 denial. Nothing in the system can honour a handle by inspecting it.

### 2.5 `ResultRecord`

The caller-visible contract. Full shape in
[`contracts/result-record.md`](./contracts/result-record.md).

Three verification states, exhaustive and mutually exclusive (FR-025): **verified**,
**not verifiable**, **refused**. Staleness is a **separate field**, not a fourth state (FR-047).

**Invariants, both structural.** The record has exactly one constructor and it takes a
`VerificationOutcome`; there is no path that produces a caller-visible result without one. And the
module defining it does not import the judge module — asserted by an import-graph test, so **no model
judgement can reach caller-visible behaviour** (FR-052, constitution Principle I). The boundary is
enforced by construction, not by policy.

### 2.6 `DriftSignal`

| Field | Notes |
|---|---|
| `clock` | `source` \| `deployment` — independently versioned, **OD-06**, FR-027 |
| `version_before`, `version_after` | the artifact hashes on that clock |
| `detected_at`, `trigger` | scheduled, event, or path-level probe (FR-046) |
| `change_at` | present on the synthetic corpora, which control it; **generally absent for the deployment clock on real traffic** |

**Invariant.** A drift signal on the source clock must not fire when the analysis is re-run over
unchanged input. This is a determinism test on T-12's serializer, and it is the reason the serializer
is a requirement rather than hygiene.

---

## 3. Measurement entities

Kept structurally apart from everything above, because the separation is the requirement.

`JudgeVerdict` — written asynchronously by the shadow judge from the trace stream, keyed to a result.
**No table in §2 references it and no module in §2 imports the module that writes it.**

`HumanLabel` — the adjudication queue's output (§4.1 of [`research.md`](./research.md)), carrying the
adjudicator, the time, and the pre-registered sampling rule that selected the item. FR-040's third
gate branch is not computable without it.

`EffectGateObservation` — one row per request seen by the enforcement point: resolved tier, rule
identifier, matched operation template, method, the operation's specification metadata, disposition.
The corpus FR-041 scores against; labelled on the reference application by **observable state diff**
before and after the call, which is contract-derived evidence and not a model judgement.

`BatteryRun` — the frozen measurement artifact, carrying **U-47**'s four terms as required by FR-053:
the prompt text **inside** the record, the battery version and task-file hashes pinned in the freeze,
the cross-battery census pinned as an invariant re-checked on load, and a loader that **refuses** a
cross-battery join rather than performing one.

---

## 4. What is deliberately absent

| Absent | Why |
|---|---|
| A tool catalogue, or any generated tool entity | **OD-09**. FR-004's capabilities are general; the served-operation set is resolution data |
| A promotion or selection record | **OD-09** |
| A per-tool static effect label | **OD-09** deferred the differentiator. Resolution is per call, at the enforcement point (FR-008..FR-012) |
| A knowledge graph, memory tier, or vector store | **OD-09**. The `codegraph` index is an analysis-time input; nothing writes it at run time and no agent reads it |
| A node, edge or topology entity | v1 emits no topology — Principle II's deviation record, accepted in [`plan.md`](./plan.md) |
| Any secret value in any table reachable from the sandbox | FR-050. The target credential lives with the enforcement point; the model credential lives with the runtime |
