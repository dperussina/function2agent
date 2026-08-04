# Tasks: Spec-Aware Agent Runtime

**Feature**: `002-spec-aware-agent-runtime` | **Date**: 2026-08-03 | **Phase**: 2 (`/speckit-tasks`)

**Input**: Design documents from `specs/002-spec-aware-agent-runtime/` —
[`spec.md`](./spec.md) (55 functional requirements, 30 success criteria, five user stories),
[`plan.md`](./plan.md) (Constitution Check, deviation records, Complexity Tracking),
[`research.md`](./research.md) (T-01..T-14, the three mechanisms, Q-01..Q-11 all resolved),
[`data-model.md`](./data-model.md), [`contracts/`](./contracts/), [`quickstart.md`](./quickstart.md)

**Constitution**: v1.2.0 ([`constitution.md`](../../.specify/memory/constitution.md)) ·
**Inherited decisions**: **OD-01** onward, in
[feature 001's plan](../001-discovery-validation/plan.md)

**Total tasks**: ~~204~~ **205**, in nine phases *(T205 added 2026-08-03 — the kernel boot matrix
that would turn the derived 5.14 floor into a tested one, and **deferred by owner decision the same
day**; it is counted here because it is recorded work, not because it is scheduled)* · **Estimate**: derived for
[the nine capabilities U-48 opened](#the-re-derived-estimate-for-u-48s-nine-capabilities), **not**
derived for anything else, and the reason is stated there rather than left as an omission.

---

## Summary

This is the last artifact before implementation, so it is written to be built from rather than
agreed with. Three things shape it beyond the ordinary decomposition.

**The nine capabilities OD-15 left without an owner get one.** Phase 3 exists for exactly that, its
tasks are enumerated against the nine, and a re-derived estimate follows with per-task arithmetic.
**All nine are now sized.** Two were marked unknown in the first pass; both closed on 2026-08-03,
one by reading a decision that had already been taken and one by running the spike it was waiting
on. What replaced them is arithmetic and, on row 4, an explicit risk band naming the single
unmeasured thing that could move it.

**The obligations the plan phase took on are tasks, not prose.** The invariants file, the canonical
serializer, the import-graph test, the syscall-supervisor overhead measurement, failing closed on
unset bounds and ceilings, the lease-revocation replay fixture, the per-provider round-trip
conformance fixture, and the three measurement obligations including the adjudication queue — each
has task identifiers and a file path.

**Where a requirement is too loose to write a task against, the task records the gap instead of
inventing the missing decision.** Six such requirements are named in
[Loose requirements](#loose-requirements-reported-not-worked-around). None is a failure of this
pass; each is a decision that has to be taken before the task it blocks can be completed.

**Tests are not optional in this feature.** The template makes them conditional; constitution
Principle VII is NON-NEGOTIABLE and **FR-053** makes a committed fixture with asserted expected
output the definition of *supported*. So fixture and battery tasks sit beside the capability they
exercise rather than in a trailing phase.

---

## Format

`- [ ] [TaskID] [P?] [Story?] Description with file path`

- **[P]** — parallelizable: a different file, and no dependency on an incomplete task.
- **[Story]** — `[US1]` … `[US5]`, on user-story phase tasks only. Setup, Foundational and Polish
  tasks carry no story label.

Paths follow [`plan.md`](./plan.md)'s Project Structure, whose component boundaries are **process
and privilege** boundaries: `src/analysis/`, `src/runtime/`, `src/supervisor/`, `src/proxy/` (Go),
`src/contracts/`, `src/sandbox/`, and `tests/{contract,integration,unit,invariants,conformance,fixtures,batteries}/`.

**Two foundational phases, and the split is deliberate.** Phase 2 is the shared substrate every
story needs. Phase 3 is the runtime core that **OD-15** moved from adopt to build. Keeping them
apart is what lets the estimate below attach to the second one without being diluted by the first,
and it is the only departure from the template's phase structure.

---

## Phase 1: Setup (shared infrastructure)

**Purpose**: the tree, the two toolchains, and the platform floor. Nothing here is negotiable
later: **FR-021** forbids run-time dependency resolution and **OD-17** makes Linux the only
supported platform, so both are settled at initialization rather than discovered at install.

- [X] T001 Create the component tree of [`plan.md`](./plan.md)'s Project Structure — `src/{analysis,runtime,supervisor,proxy,contracts,sandbox}/`, `tests/{contract,integration,unit,invariants,conformance,fixtures,batteries}/`, `deploy/{compose,images}/`
- [X] T002 Initialize the Python 3.12 project with every dependency pinned and fully resolved at build time in `pyproject.toml` and a committed lock file (FR-021)
- [X] T003 [P] Initialize the Go module for the enforcement point as a single static binary with `go test` wired, in `src/proxy/go.mod` (T-05, Q-01)
- [ ] T004 [P] Pin `codegraph`'s version and assert its schema hash, failing the analysis stage loudly on a mismatch, in `src/analysis/codegraph_pin.py` (**U-04**)
  - **PARTIAL** — the pin and the schema-digest check are implemented and fail closed; `CODEGRAPH_SCHEMA_SHA256` is deliberately `None` until a hash is observed from a real `codegraph` database, so the check currently fails loudly rather than passing vacuously.
- [X] T005 [P] CI running `pytest`, `go test` and the invariants suite on every change, in `.github/workflows/ci.yml`
- [X] T006 [P] Linux-facility preflight — cgroup v2, user and mount namespaces, `seccomp` user notification — failing loudly on any missing facility, in `src/supervisor/preflight.py` (**OD-17**, FR-053)
  - **Kernel floor added 2026-08-03: 5.14, DERIVED and NOT TESTED.** Bound by `cgroup.kill`; `SECCOMP_USER_NOTIF_FLAG_CONTINUE` (5.5) and the corrected `SECCOMP_IOCTL_NOTIF_ID_VALID` ioctl number (5.9) bind lower, and the second is a property of our own definition — 5.5 through 5.8 return `EINVAL` from a call site where the failure is invisible. An unparseable release fails rather than being assumed new enough. The check states the derivation and the untested status in the same string and a removal proof fires if the caveat is dropped; T205 is the boot matrix that would make the floor tested, ~~and it does not exist~~ **and it is deferred by owner decision 2026-08-03 — the derived floor ships marked NOT TESTED rather than the matrix being built now, so the caveat is permanent until an owner decision to measure rather than pending on scheduled work**
- [X] T007 [P] Development container image identical to the runtime image, so the toolchain question finding 003 raised for a laptop never reaches the shipped configuration, in `deploy/images/dev.Dockerfile`
- [X] T008 [P] Declare FR-053's committed-fixture discipline and the fixture inventory each capability owes, in `tests/fixtures/README.md`

---

## Phase 2: Foundational A — contracts, storage, canonical form, configuration, invariants

**Purpose**: the substrate all five stories sit on. **⚠️ No user story work begins until this phase
completes**, and two items in it are load-bearing for a capability rather than merely useful:
without T010's canonical serializer, drift detection false-alarms every interval (**FR-055**,
T-12); without T022's invariants file, constitution Principle II's second paragraph is an intention.

### Shared schemas and the canonical form

- [X] T009 Define schemas for the eight artifact kinds **FR-054** enumerates, each carrying `schema_version`, in `src/contracts/schemas.py` (FR-034, FR-054)
- [X] T010 Implement the one canonical serializer — sorted keys with deterministic collation, fixed locale-independent numeric formatting, `LF`, `UTF-8` without a byte-order mark — in `src/contracts/canonical.py` (**FR-055**, T-12)
  - **PARTIAL** — the canonical serializer is implemented and used for content addressing. FR-055's full envelope and the eight artifact schemas are **not**.
- [X] T011 Implement the envelope that holds every value varying between two runs over the same input — timestamps, filesystem paths, hostnames — **beside** the hash and never underneath it, in `src/contracts/envelope.py` (FR-055)
- [X] T012 Determinism test: analyse one committed fixture twice and compare **payload bytes**, not content addresses, in `tests/contract/test_canonical_determinism.py` (**SC-029** first clause; comparing addresses would hide a serializer stable only within a process)
- [X] T013 [P] Round-trip test: every one of the eight artifact kinds through the canonical serializer unchanged, in `tests/contract/test_canonical_roundtrip.py`
- [X] T014 Schema-version migration framework with one migration exercised from the first commit, in `src/contracts/migrations/`
- [X] T015 [P] CI gate: a breaking change to a consumed or produced schema is a MAJOR bump, in `tests/contract/test_schema_versions.py` (FR-034, Principle VIII)

### Storage, addressing and rollback

- [X] T016 Repository interface over SQLite in WAL mode, every row carrying `tenant_id` and `deployment_id`, with no engine-specific SQL above the connection layer, in `src/contracts/repository.py` (T-06, FR-035, **OD-08**)
- [X] T017 Encode [`data-model.md`](./data-model.md)'s single-writer-per-table ownership map as data the repository enforces, in `src/contracts/ownership.py`
- [X] T018 Invariant test for writer ownership across the three processes, in `tests/invariants/test_writer_ownership.py` — finding 006 explicitly did not test its session service under concurrent writers, and T-06's narrowing records that v1's store now has **no** observed substrate rather than one
- [X] T019 Content-addressed `objects/<sha256>` payload store with `Artifact` immutable and `ArtifactRef` keyed `(deployment_id, kind)` with retained history, in `src/analysis/artifact_store.py` (FR-054)
- [X] T020 Rollback as a ref move, plus the restoration record naming the operator, the version restored from and the version restored to, in `src/analysis/rollback.py` (FR-054, FR-019)
- [X] T021 [P] Rollback contract test: one operator action, zero hand-edits, zero runtime restarts, and the restored deployment produces the artifact hashes it produced before, in `tests/contract/test_rollback.py` (**SC-028**)
  - ~~**AMBIGUITY IN FR-054, IMPLEMENTED LITERALLY**~~ **RESOLVED BY OWNER DECISION 2026-08-03 — the toggle reading is the intended one and the shipped behaviour is correct** — "the immediately prior version" makes a second rollback a *toggle* between the last two unique versions, not a walk backwards through history. Implemented and tested as the toggle; the test names the reading. ~~If walking back was intended, FR-054 needs a word for it and this becomes a behaviour change rather than a bug fix.~~ **The owner confirms rollback is an undo of the most recent change and is its own inverse. Nothing in the implementation moved; FR-054 gained the word it needed so that the phrase cannot be re-read as a history walk, and `contracts/artifact-versioning.md` and SC-028 were corrected where they restated it loosely.**

### The invariants file, and the four invariants the plan named

- [X] T022 Create the **versioned, machine-checkable invariants file** in `tests/invariants/invariants.yaml`, each entry carrying an identifier, the principle or requirement it discharges, and the test that checks it (constitution Principle II, second paragraph — adopted by [`plan.md`](./plan.md) as an obligation the specification did not state)
- [X] T023 Invariant runner executing the whole set on every change, in milliseconds and with no model in it, in `tests/invariants/runner.py`, wired into T005's CI
- [X] T024 [P] Invariant: **no code path constructs a caller-visible result without a verification outcome**, in `tests/invariants/test_result_constructor.py` (FR-025)
- [X] T025 [P] Invariant: **import-graph — the result-record and gate-decision modules do not import the judge module**, in `tests/invariants/test_import_graph.py` (**FR-052**, constitution Principle I; this is what keeps the model-judge boundary structural rather than a policy)
- [X] T026 [P] Invariant: **no HTTP client in the sandbox image can reach any address but the enforcement point**, in `tests/invariants/test_sandbox_reachability.py` (FR-014)
  - **VACUOUS-BUT-PRESENT** — the static arm is implemented and its removal proof fires on a planted destination, but `src/sandbox/` and `src/runtime/drift/` contain no modules yet, so it scans an empty set and says so. The topological arm is what carries FR-014 until then. Phase 2 added no sandbox-side module, so it is still vacuous; it is now reported in a terminal-summary block rather than as one skip line, the declared roots are asserted to exist so a rename cannot switch the scan off silently, and an empty `__init__.py` does not count as coverage.
- [X] T027 [P] Invariant: **every deny disposition carries a rule identifier**, in `tests/invariants/test_rule_id_present.py` (FR-011; a disposition with no rule identifier fails the suite, because FR-011 makes the rule part of the record and not an annotation on it)
- [X] T028 [P] Invariant: every session terminal state is a named member of the declared taxonomy, in `tests/invariants/test_terminal_taxonomy.py` (FR-006 — this is the check that stops a generic failure being introduced later)

### Configuration, and failing closed

- [X] T029 Declared configuration schema with environment injection at process start and startup failing loudly on any missing or invalid required value, in `src/contracts/config.py` (FR-033, [`contracts/configuration.md`](./contracts/configuration.md))
- [X] T030 **Fail closed when FR-049's bounds are unset** — `SANDBOX_MEMORY_MAX`, `SANDBOX_CPU_MAX`, `SANDBOX_CPU_TOTAL` are required with no default, and startup names the missing one (**Q-10**, accepted as recommended)
- [X] T031 **Fail closed when any of FR-005's four ceilings is unset** — spend, tokens, wall-clock, turns — naming which is missing and treating none as unbounded or defaulted (FR-005, **SC-030** first clause; the same treatment as Q-10, extended to the ceilings the day the specification was extended)
- [X] T032 [P] Fail-loud contract tests: each required key unset in turn, then malformed in turn, asserting startup fails, names the key, and starts nothing, in `tests/contract/test_configuration_failloud.py`
- [X] T033 [P] Marking machinery for every configured value with no measurement behind it — `STALENESS_CEILING`, `DRIFT_CHECK_INTERVAL`, `CAPABILITY_LEASE_INTERVAL` — in `src/contracts/unvalidated.py` (FR-043)
- [X] T034 [P] Contract test: every FR-043-marked value appears marked on every external surface that emits it, in `tests/contract/test_unvalidated_marking.py`
- [X] T035 A `Secret` type with **no serializer**, so a credential cannot be logged by a code path that forgets to redact — redaction structural rather than a filter, in `src/contracts/secret.py` (FR-036)

### Tracing, from the first shipped capability

- [X] T036 Span writer for the seven span kinds — `model_call`, `tool_call`, `egress_decision`, `filesystem_decision`, `state_transition`, `verification`, `drift_check` — carrying inputs, outputs, timing, cost, and the artifact versions in force, in `src/runtime/trace.py` (FR-030, FR-031, Principle VI)
- [X] T037 Required `rule_id` on `egress_decision` and `filesystem_decision` spans, enforced by T023's suite (FR-011, FR-048)
- [X] T038 Budget spans written **as consumption accrues** and journalled outside the container, so a cgroup kill loses no accounting, in `src/runtime/trace_budget.py` (FR-049, **U-30**)
  - The append-per-increment property and the survives-without-a-flush property are both tested. "Outside the container" is enforced as a resolved-path check against the session root and tested against relative-path evasion, but it has **not** been exercised against a live session whose mount namespace is up — that arm belongs with the integration battery, not here.
- [X] T039 [P] Trace contract test: every span kind emitted on a full session and no decision span missing its `rule_id`, in `tests/contract/test_trace_spans.py`
- [X] T040 [P] Trace scan test: no credential-shaped value and no readable `provider_state` in any trace, in `tests/contract/test_trace_redaction.py` (FR-036, FR-037)

**Checkpoint**: the substrate exists, the invariants suite runs, and configuration fails closed.
Phase 3 can begin.

---

## Phase 3: Foundational B — the runtime core OD-15 left unowned (**U-48**)

**Purpose**: this phase is the answer to **U-48**. **OD-15** dropped ADK, and nine capabilities the
plan phase had assumed available moved from adopt to build with no owner and no estimate. Every one
of the nine is named below with the tasks that own it, and the estimate follows the phase.

> **What may not be quoted, restated here because this is where it would happen.** **U-48** carries
> a standing rule: no document may quote the superseded ~~2.5–3.5 week~~ figure as the v1 runtime
> estimate until a re-derivation exists. That figure was scoped to *loop safety with the runtime
> adopted*, its four component estimates were ADK-shaped, and their anchors are gone — there is no
> `run_async` to wrap, no plugin callback to ride, and no upstream event stream for the journal to
> sit above. The derivation below **replaces** it for the runtime core and does not add to it, so
> the two must not be summed. Two items are already known to sit outside any figure and stay
> outside this one: **OD-02**'s coding-node executor, which v1 does not build, and the per-call
> effect classifier **OD-09** added, which is Phase 4's enforcement point.

### Capability 1 — the agent loop

- [ ] T041 Turn loop: turn dispatch, the model-response-to-tool-call step, and `TurnRecord` construction, in `src/runtime/loop.py` (FR-004, [`data-model.md`](./data-model.md) §2.2)
- [ ] T042 Context assembler and truncation policy, in `src/runtime/context.py`
- [ ] T043 Parallel tool-call dispatcher: execute concurrently, journal and record in the **provider's declared index order** and never in completion order, in `src/runtime/dispatch.py` (T-08, FR-007)
- [ ] T044 Explicit per-key merge rules for shared state a concurrent step writes, with last-write-wins forbidden, in `src/runtime/state_merge.py` (T-08)
- [ ] T045 [P] Invariant tests for declared-order recording and for a concurrent write that cannot be lost, in `tests/invariants/test_fanout_ordering.py`

> **Why T043 through T045 exist in a v1 that emits no graph, since this was nearly lost.** Finding
> 006 measured fan-out producing **5 distinct orderings in 8 runs** under overlapping latencies, and
> a **silent lost update** where one of two parallel branches writing a shared key vanished with no
> error and no warning. Those were read as *graph* properties. They are not: every provider in
> **SC-010**'s set can emit several tool calls in one turn, so a single-agent loop fans out whether
> or not it has a graph. **The hazard is the providers'; the measurements were ADK's.** With ADK
> gone the mitigation is ours, and T-08 is now a design rule with a known-real hazard and **no
> measurement behind it** — which is why T045 is an invariant rather than a comment.

### Capability 2 — the runner

- [ ] T046 Runner: session start and attach, loop invocation, cancellation, and the teardown handshake with the supervisor, in `src/runtime/runner.py`
- [ ] T047 [P] Cancellation test asserting a cancelled consumer leaves no error on the stream and no partial state, in `tests/unit/test_cancellation.py` — cancellation is routine in an agent product, which is why finding 006 reported a teardown defect against the runtime it probed

### Capability 3 — the session store

- [ ] T048 Session store: create, load and persist `Session` with `session_id`, `state`, `terminal_state`, `lease_expires_at` and the four ceilings, in `src/runtime/session_store.py` (**OD-15** — ours, on no framework)
- [ ] T049 Session state machine and named-terminal recording over [`data-model.md`](./data-model.md) §2.1's lifecycle, in `src/runtime/session_state.py` (FR-006)
- [ ] T050 Concurrent-writer probe for **our own** store under the three processes, in `tests/integration/test_store_concurrent_writers.py` — finding 006 states it did not test this, and T-06's narrowing records that what it observed on SQLite was a session service v1 does not ship

### Capability 4 — checkpoint and resume · **12–17 days, band +0 to +4**

- [ ] T051 Write-ahead intent journal keyed `(session_id, turn_index, step_index)` with an idempotency key per effectful step — intent committed before the effect, outcome committed after — in `src/runtime/journal.py` (T-07)
- [ ] T052 Resume reconstruction at **turn-and-step granularity**, so a resumed session skips completed inner turns, in `src/runtime/resume.py` — finding 006 measured a loop hosted inside a checkpointed node re-executing **4 of 4** completed inner turns, which is what this granularity exists to avoid
- [ ] T053 Reserve-then-reconcile budget ledger — reserved before the model call, reconciled after — so a crash **over**-counts rather than under-counts, in `src/runtime/ledger.py` (T-07, **U-30**)
- [ ] T054 Induced-crash resume battery: `SIGKILL` from a separate process at a turn boundary and inside a step, asserting no completed inner turn re-executes and no recorded local effect repeats, in `tests/integration/test_resume_sigkill.py` (FR-007, SC-011)
- [ ] T055 Repeated crash-and-resume ceiling battery — **at least three resumes**, on each of the four dimensions in turn, asserting the cumulative total after every resume is never lower than the total before the crash that preceded it, in `tests/batteries/test_ceilings_under_resume.py` (**SC-030** second clause; finding 006 measured a ceiling of 3 permitting **6** cycles because the counter lived on a context rebuilt per attempt, and the failure is invisible in review because every individual attempt is compliant)
- [ ] T056 Extend the opaque-state conformance fixture across a **resume boundary**, in `tests/conformance/test_provider_state_resume.py` — finding 006's *What this does NOT establish* records provider-opaque reasoning state surviving a resume as untested, and with the journal and the envelope now both ours that boundary is inside one mechanism instead of across two

### Capability 5 — provider transport and tool-schema translation · **15–20 days**

- [ ] T057 One internal tool-call representation plus per-provider translation in both directions across the differing function-calling wire formats, in `src/runtime/providers/schema.py` (FR-037)
- [ ] T058 A thin driver per provider over that vendor's **own SDK**, behind one interface, in `src/runtime/providers/` (**OD-16** — no `litellm`, which declares no license; constitution Principle V's thin bottom tier)
- [ ] T059 `provider_state` as opaque bytes on every turn record — captured verbatim from the raw response, re-injected verbatim, keyed by provider, never merged, never interpreted, never logged in a form readable as content — in `src/runtime/providers/state.py` (T-02, FR-037)
- [ ] T060 Cassette recording and replay harness for provider fixtures, in `tests/conformance/cassettes/` (constitution Principle VII, which names cassette-backed provider tests by name)
- [ ] T061 **Per-provider round-trip conformance fixture** over a long chained tool sequence on a reasoning model, asserting **byte identity of the opaque field** — and asserting it as a **conditional**, *whenever the field is present it survives byte-identical*, never as an unconditional presence check — in `tests/conformance/test_provider_state_roundtrip.py`. [Finding 016](../001-discovery-validation/findings/016-provider-sdk-roundtrip.md) measured both constraints: its negative control stripped the field and **chaining still succeeded with the correct answer**, so an output-checking fixture would pass an adapter that drops it; and `claude-sonnet-5` under adaptive thinking emitted opaque state on only **2 of 6** runs in the committed batch, so an unconditional presence assertion is flaky

> **SC-010 is a test v1 must pass, not a result it inherits, and this is the task that closes it.**
> Finding 003 drove four providers to a passing chained tool call **through ADK and LiteLLM**. The
> provider-capability half of that transfers — the vendors' APIs do support chained tool calling —
> and the adapter-implementation half does not (**OD-16**).
>
> **Updated 2026-08-03.** The provider-capability half is no longer inherited either:
> [finding 016](../001-discovery-validation/findings/016-provider-sdk-roundtrip.md) measured all
> four vendors' own SDKs chaining and round-tripping their opaque state directly, including xAI's
> `encrypted_content` — the field finding 003 result 7 counted ADK's adapter referencing **zero**
> times. What remains ours is the adapter implementation, and until T061 and T164 pass no document
> may cite either finding as evidence that the *shipped* configuration is provider-agnostic.
>
> Finding 003 declined to read its passing two-hop case as clearance. **Finding 016 proved that
> caution correct by measurement**: with the opaque field stripped entirely, its two-hop chain still
> succeeded and still answered correctly. A two-hop scenario cannot detect opaque-state loss
> behaviourally — which is exactly why T061 specifies a long chain, and why it must assert the
> digest rather than the answer.

### Capability 6 — the per-provider cost table

- [ ] T062 Per-provider token cost table as **versioned configuration** with a stated source per entry and no assumption of uniformity, in `src/runtime/providers/costs.py` — finding 003 showed per-provider cost cannot be assumed uniform, and this table was never on anyone's list because the removed dependency supplied it
- [ ] T063 Fail closed when a model in use has no cost entry, in `src/runtime/providers/costs.py` — otherwise the spend ceiling silently becomes unenforceable for exactly the model nobody priced

### Capability 7 — the spend backstop

- [ ] T064 Budget channel enforcing all four of FR-005's ceilings from **session state** rather than from a per-attempt context, in `src/runtime/budget.py` (FR-005, **U-30**)
- [ ] T065 A low call-count backstop independent of the cost table, in `src/runtime/budget_backstop.py` — this occupies the position the removed dependency's one enforced ceiling held, and it exists so that a missing price cannot remove every ceiling at once

### Capability 8 — the raw terminal signals

- [ ] T066 Emit the raw terminal signals the taxonomy sits on — error identity, budget-exhaustion cause, and an explicit end-of-run marker distinguishing completion from cancellation — in `src/runtime/signals.py` (finding 006 primitive 2: the taxonomy was always ours, and the raw signals were the dependency's)
- [ ] T067 Terminal taxonomy over those signals, with a named member per ceiling, per bound, plus `no_progress`, `denied_operation` and `completed`, in `src/runtime/terminal.py` (FR-006, [`data-model.md`](./data-model.md) §2.1)
- [ ] T068 [P] Test that a clean completion and a mid-loop cancellation are distinguishable from the caller's side, in `tests/unit/test_terminal_distinguishable.py` — the indistinguishable case is the false-success shape the corpus names as a very common and very expensive bug

### Capability 9 — the event stream the serving surface renders

- [ ] T069 Session event stream emitter, in `src/runtime/events.py` — T-03 assumed our surface would render the dependency's stream, and after **OD-15** nothing produces one
- [ ] T070 Thin HTTP/SSE surface carrying the caller-visible result record and the session event stream, in `src/runtime/serving.py` (T-03, **Q-05** subsumed rather than chosen)
- [ ] T071 [P] Surface contract tests over the event stream and the result-record rendering, in `tests/contract/test_serving_surface.py` (constitution Principle VII names the integration-surface contract)
- [ ] T072 [P] Assert the event stream carries no secret value and no readable `provider_state`, in `tests/contract/test_event_stream_redaction.py` (FR-036, FR-037)

**Checkpoint**: the runtime core exists and is ours end to end. User-story phases can begin.

---

## The re-derived estimate for U-48's nine capabilities

**What this is.** Engineering judgment calibrated against measured behaviour, per task, summed —
**not a measurement**, and it says so in the same words the superseded figure used. **U-48**'s own
resolution names this method and calls it owed. Every row states the anchor its judgment is
calibrated against, so a reader can disagree with a specific number rather than with a total.

**What it is not.** It is not a schedule, it contains no contingency, and it is a lower bound
because two of the nine are unsized. Seven days is not the same as one week: the figures are
engineer-days of focused work.

| # | Capability | Tasks | Days, low | Days, high | Anchor the judgment is calibrated against |
|---|---|---|---|---|---|
| 1 | Agent loop, dispatcher, merge discipline | T041–T045 | 8 | 11 | T043's 1–2 days re-uses the fan-out item's shape; **OD-15** records that as a construction requirement of our own dispatcher rather than a discipline imposed on somebody else's scheduler, and calls it the easier of the two |
| 2 | Runner | T046–T047 | 3 | 4 | No prior sizing anywhere. Judged against T048's shape, with which it shares the session handshake |
| 3 | Session store | T048–T050 | 5 | 7 | No prior sizing: the store was inside the removed dependency. T050 is sized as a probe rather than a fix, because a fix's size depends on what the probe finds |
| 4 | Checkpoint and resume | T051–T056 | **12** | **17** | Re-derived under **OD-10** per T-07's instruction, not inherited. Carries a **+0 to +4 day risk band**; both are derived below |
| 5 | Provider transport and tool-schema translation | T057–T061 | **15** | **20** | Measured by [finding 016](../001-discovery-validation/findings/016-provider-sdk-roundtrip.md), which drove all four vendor SDKs directly. Derived below |
| 6 | Per-provider cost table | T062–T063 | 2 | 3 | Was a sub-item of the superseded budget estimate, supplied by the removed dependency's cost map. Sized as data plus a fail-closed path, not as logic |
| 7 | Spend backstop and budget channel | T064–T065 | 4 | 5 | The superseded budget item was 4–5 days *including* the cost table and riding plugin callbacks that no longer exist. Netting the table out to row 6 and adding our own hook points lands in the same place, which is why this row is unchanged rather than reduced |
| 8 | Raw terminal signals and the taxonomy | T066–T068 | 4 | 6 | The superseded terminal-condition item was 2–3 days and **assumed the raw signals existed**. T066 is the increment **OD-15** adds; T067 is that item |
| 9 | Event stream and the HTTP/SSE surface | T069–T072 | 6 | 9 | No prior sizing: this limb of **OD-01** was the one with no measurement behind it at all, so there is nothing to re-base and the judgment is unanchored except by T070's contract |
| — | **Subtotal — all nine** | — | **59** | **82** | Low: 8 + 3 + 5 + 12 + 15 + 2 + 4 + 4 + 6 = 59. High: 11 + 4 + 7 + 17 + 20 + 3 + 5 + 6 + 9 = 82. Row 4's band sits **on top** of this and is not folded in |

At five working days to the week that is **11.8 to 16.4 weeks for one engineer, for the runtime core
alone** and for nothing else in this task list.

> **This is the figure that replaces the one U-48 forbade quoting.** The superseded estimate was
> 2.5–3.5 weeks. The re-derivation lands at 11.8–16.4 weeks — **about 4.7× larger at the midpoint**,
> 14.1 weeks against 3.0 — and the gap is not a correction to the old arithmetic. It is what
> **OD-15** did: the old figure
> sized a slice of loop-safety work on top of a framework that supplied the loop, the runner, the
> session store, the provider adapter, the cost table and the event stream. Seven of the nine rows
> above did not exist as build items when that figure was written. Rows 2, 3, 5, 6 and 9 had no
> prior sizing of any kind.

### Rows 4 and 5, derived — both were unknown in the first pass and both closed on 2026-08-03

#### Row 4 — checkpoint and resume · 12–17 days, band +0 to +4

The first pass gave three reasons this could not be sized. **One of them was wrong**, and the
correction is worth recording rather than quietly dropping: it read **U-31** being open as leaving
v1's substrate undecided. It does not. **Q-03 is ACCEPTED as (a) — our own journal** — with (b)
named as the v2 option rather than dismissed, and its disposition reads *"ACCEPTED 2026-08-03 as
recommended, and the argument behind it got weaker rather than stronger."* The argument weakened;
the verdict did not move. U-31 remains open as a standing question about whether to adopt durable
execution **ever**, and that is a different question from what v1 builds on. v1's substrate is
fixed, so it cannot make v1's sizing indeterminate.

Of the remaining two, the second was also miscategorised. **T-07's re-derivation is work to do, not
a blocker**, and it is done here. Only the unmeasured store is a genuine unknown, and it is a band
on a sized item rather than a reason to refuse the item.

**The re-derivation, per task.** T-07's instruction is that **OD-10** makes v1 read-only against the
target, so *"repeating a target call cannot corrupt the target — it can only cost budget. The
effects that must not repeat in v1 are the local ones."*

| task | days | derivation |
|---|---|---|
| T051 journal | 2–3 | **This is the task OD-10 shrinks.** The superseded 5–7.5 day journaling item was sized for a side-effecting product, where the expensive part is per-operation idempotency against a target you cannot generically ask *"did my write land?"*. Read-only removes that half entirely. What is left is a table, one key, and two commit points |
| T052 resume reconstruction | 3–4 | **Not shrunk by OD-10.** Re-executing a completed inner turn is a correctness defect whether the effect was local or remote. Finding 006 measured **4 of 4** completed inner turns re-executing, and turn-and-step granularity is what prevents it |
| T053 reserve-then-reconcile ledger | 2–3 | **Not shrunk by OD-10** — T-07 says so directly: *"it is not zero, because budget correctness is exactly what U-30 says nothing supplies."* Distinct from row 7, which is the enforcement channel; this is the durable accounting underneath it, and T-07 assigns reserve-then-reconcile here |
| T054 induced-crash battery | 2 | Harness plus assertions. The technique is finding 006's own and needs no invention: `SIGKILL` from a separate process, chosen so no `finally`, no `atexit` and no graceful shutdown can run |
| T055 repeated-resume ceiling battery | 2–3 | Twelve arms — three resumes across four dimensions — reusing T054's kill harness. **An addition, not a re-basing**: SC-030's second clause did not exist when the superseded figure was written |
| T056 resume-boundary opaque-state arm | 1–2 | Reuses T060's cassettes and T061's fixture; adds a kill across the boundary. Also an addition — finding 006 recorded this boundary as untested rather than sizing it |
| | **12–17** | low 2+3+2+2+2+1; high 3+4+3+2+3+2 |

**The band: +0 to +4 days.** Resume correctness rides on our own SQLite store under three concurrent
writers, and *nothing has measured it* — T-06 narrowed finding 006's SQLite observation to **ADK's**
`SqliteSessionService`, which v1 does not ship, and **Q-02**'s disposition records the multi-process
writer risk as *"now unmeasured for our own store as well as for the one we are not shipping."*

The band is **judgment, not measurement**, and it is bounded rather than open: a hostile probe result
forces rework of the two tasks that *write* — T051 and T053, 4–6 days of the 12–17 — and does not
touch resume reconstruction or the three batteries. **T050 collapses it**, which is why T050 is
listed below as a pre-implementation item. A clean probe collapses the band to +0; a probe finding
lock contention the single-writer-per-table ownership map does not already handle spends it.

#### Row 5 — provider transport and tool-schema translation · 15–20 days

The spike ran. [**Finding 016**](../001-discovery-validation/findings/016-provider-sdk-roundtrip.md)
drove a chained, dependent two-hop tool sequence with a verbatim opaque-state round-trip through
each of the four vendors' own SDKs — `anthropic` 0.120.2, `openai` 2.52.1, `google-genai` 2.16.0,
`xai-sdk` 1.17.0 — with no abstraction layer in any path. **All four chained; all four round-tripped
their opaque field byte-identically; all four accepted it back**, including xAI's
`encrypted_content`, the field ADK's LiteLLM adapter referenced zero times.

**What that measurement does to the estimate is not what it looks like.** It removes the largest
uncertainty — the four wire formats do *not* need a translation layer, because each SDK already
carries its own opaque field correctly, so the driver's job is **to not lose it** rather than to
reconstruct it. But the spike's negative control raised the cost of the test half, and by more than
it lowered the transport half.

| task | days | derivation |
|---|---|---|
| T057 internal representation and per-provider translation | 3–4 | The spike wrote this four times and each SDK-specific extractor was small. Production adds error mapping, streaming, and the full tool-shape surface the spike's two functions do not exercise |
| T058 thin driver per provider | 4–5 | The spike built four minimal drivers in under a day, so the happy path is cheap. **Finding 016 result 9 is what makes this the largest row**: `claude-sonnet-5` rejects the extended-thinking request shape `claude-sonnet-4-5` requires, with an HTTP 400. The request shape is model-specific *within a single vendor*, so a driver cannot be one function per provider — it needs a per-model capability branch, and that branch tracks vendor releases |
| T059 `provider_state` as opaque bytes | 2–3 | Measured simple: verbatim capture and re-injection worked on all four. The residue is the never-merged, never-interpreted, never-logged-readably discipline and its tests, not the transport |
| T060 cassette record and replay | 3–4 | **Unmeasured — the spike ran live and built no cassettes.** Sized by judgment against T059's shape, and it is the least anchored figure in this row |
| T061 round-trip conformance fixture | 3–4 | **Finding 016 raised this rather than lowering it**, on two measured grounds. Its negative control stripped the opaque field and **chaining still succeeded with the correct answer** — so a fixture that checks output would have passed ADK's adapter while it was dropping the field, and the assertion must be byte identity. And presence is **not deterministic**: `claude-sonnet-5` under adaptive thinking emitted opaque state on **2 of 6** runs in the committed batch, so `assert present` is flaky and the fixture must assert the conditional *whenever present, it survives* |
| | **15–20** | low 3+4+2+3+3; high 4+5+3+4+4 |

**No band on this row.** The transport is measured on all four providers. T060 is the one unanchored
figure and it is 3–4 days, inside the row's own spread.

> ⚠️ **Reopened 2026-08-03 by Phase 2's measured defect density, and deliberately not re-quantified.**
> The sentence above is a judgement about *transport*, and T059 is not transport — it is the
> never-merged, never-interpreted, never-logged-readably discipline over an opaque field, which is a
> serialization boundary and therefore in the class where Phase 2 measured defects roughly six times
> denser than assumed. Finding 016's own negative control is the argument: chaining **succeeded with
> the correct answer** while the opaque field was being dropped, so this row's silent-failure mode is
> demonstrated rather than hypothesised. Re-quantifying needs a cost per defect that nothing in this
> corpus has measured; see
> [Phase 2's measured defect density](#phase-2s-measured-defect-density--the-first-calibration-anchor-this-section-said-it-did-not-have).

> **Two things finding 016 establishes that belong outside this document**, reported here because
> this pass may not edit the files that carry them. First, **SC-010's provider-capability half now
> has direct evidence under OD-15 and OD-16** — the four-provider result no longer rests only on a
> measurement taken through two removed layers. Second, **U-48's row for this capability is now
> sized**, and the finding is the anchor. Neither
> [`spec.md`](./spec.md) nor [`research/14-architecture-synthesis.md`](../../research/14-architecture-synthesis.md)
> is edited here.

### Phase 2's measured defect density — the first calibration anchor this section said it did not have

**Added 2026-08-03, after Phase 2 completed.** It is recorded here rather than in a phase heading
because this is the section that explains why the other phases carry no number, and one of its three
reasons has partially moved.

**First, what did *not* change, because a re-sizing was asked for and none is possible.** Nothing in
this document, and nothing in [`plan.md`](./plan.md), sizes anything against a defect rate. The nine
rows above are engineer-days derived per task from task shape, each anchored to a named finding or to
a superseded sizing; no row multiplies a line count by a defect density, and Phases 1, 2 and 4
through 9 carry no estimate at all. **So there is no figure here that a corrected defect rate makes
stale, and no total moves below.** Anyone arriving with a corrected rate should read the next two
paragraphs for what it *does* bear on.

**Second, and this is the part that blocks arithmetic rather than merely complicating it: a defect
rate predicts defects, not days.** Converting one into the other needs a cost per defect, and this
corpus has never measured one. Deriving days from a defect density here would introduce a second
unmeasured number to launder the first, which is the inherited-number failure this section already
refuses twice in its own text.

**What was measured.** Phase 2 produced **five real defects across roughly 2,300 lines** — about
**one per 460**. The line count is the new Phase 2 sources in the working tree; the defect count is
the implementation pass's own, and **neither has a findings document behind it**, which is recorded
below as an outstanding item rather than glossed. Against a working assumption of one per 3,000 that
is roughly six times denser.

**Why, and the *why* is what makes this usable rather than just alarming.** The five were: a
non-reentrant lock that deadlocked only under a nesting pattern one caller uses; a rollback that
split its restoration record and its ref move across two transactions; a volatility scanner with **no
positive control**, which could have returned the empty list unconditionally and passed every test; a
redaction marker that did not name which credential it stood for, making a redacted trace useless for
the diagnosis it was kept for; and a benchmark that overwrote its own committed measurement on every
run, so a real regression would arrive as ordinary noise.

Not one of those is caught by the thing that catches kernel-mechanism defects. **Kernel mechanism
code fails loudly — the kernel returns `EPERM` and the test stops.** Serialization and storage code
fails quietly: it returns a plausible value, the assertion passes, and the defect is in what the
value *means*. Three of the five are instruments that would have reported success while measuring
nothing, which is the failure class this repository already has a name for.

**So the rate is not one number, and applying one per 500 uniformly would overcorrect exactly as
badly as one per 3,000 underestimated.** The working split:

| Rate | Applies to | Why |
|---|---|---|
| **~1 per 500** | anything crossing a storage or serialization boundary — persisted records, cross-process handoffs, canonical form, redaction, ledgers and journals, and **any instrument whose output is a measurement** | The failure is a plausible wrong value, and nothing outside the code checks it. All five Phase 2 defects are here |
| **~1 per 3,000** | code the kernel checks for you — namespaces, cgroups, `seccomp`, capabilities, file descriptors | A wrong call fails at the syscall with a named errno, so the defect surfaces on first execution rather than at review |

**Classifying the remaining phases against that split, because the point of an anchor is that
somebody can use it.** Phase 4 is the one that matters and it is **mixed, not predominantly either**:

| Phase 4 group | Tasks | Rate |
|---|---|---|
| Execution-environment mechanisms | T097, T099, T102–T106, T109, T110 | kernel-checked |
| Enforcement-point protocol stages | T083–T091, T094 | kernel-checked in part only — T085 and T094 are parser-differential work, where a wrong parse is a plausible value and the failure is silent |
| Admission, effect rules, pinning | T073–T082 | storage boundary — every one persists a versioned record another stage reads |
| Decision log, trace ingest, spans | T092, T093, T100 | storage boundary, and cross-process |
| Capability, lease, session state | T107, T108, T111, T112 | storage boundary |
| Batteries, fixtures, instruments | T101, T114–T118 | **instrument** — the volatility-scanner defect is this class exactly |

Phases 5, 6, 8 and 9 are **predominantly storage-and-instrument**: derivation provenance, result
records, drift artifacts, the measurement substrate and the reporting surfaces are all persisted or
all instruments. Phase 7 is the serving surface and is mixed on the same pattern as Phase 4. **No
phase is predominantly kernel-checked except the execution-environment group inside Phase 4**, which
is a smaller share of the remaining work than the loud failures it produces makes it feel.

**What this does to the two rows that were unknown in the first pass.** Both are affected and neither
can be re-derived here. Row 4 is storage-shaped almost throughout — T051 is a journal and T053 a
durable ledger, and both are named above as the tasks a hostile probe result would force rework of.
Row 5 contains one storage-boundary task, T059's opaque-state handling, whose whole discipline is
*never merged, never interpreted, never logged readably* — a discipline whose violations are silent
by construction, and finding 016's negative control already demonstrated that chaining **succeeds
with the correct answer** while the field is being dropped. **Row 5's "no band on this row" was
written before Phase 2 measured anything and rests on the assumption this section has just
contradicted.** It is flagged rather than replaced: putting a number on it needs the cost per defect
nobody has.

**The honest effect on the interval is to widen it, not to shift it, and the widening is not
quantified here.** A six-fold miss on the one phase with a measurement is evidence about the spread
of these estimates and not only about their centre — but the nine rows were derived by task shape
rather than by density, so there is no multiplier to apply to them, and inventing one would be worse
than leaving the interval honestly unbounded on the high side. What is stated instead: **59–82 is a
lower bound whose upper end is now less trustworthy than its lower end**, and row 5's absent band is
the specific place to start when someone re-derives with a cost per defect in hand.

**Two outstanding items this creates**, both flagged rather than resolved:

- **The measurement has no findings document.** Five defects in roughly 2,300 lines is a
  measurement of this project's own output and it currently lives only in this section and in the
  implementation pass that produced it. Feature 002 has no `findings/` directory, so filing it is a
  structural act rather than a propagation one.
- **The classification is reasoned, not measured.** One phase produced the split. Whether kernel
  code really is six times cleaner, or whether Phase 2 was simply the harder phase, is not
  established by a single phase, and the next phase to complete is the one that tests it.

### Nothing else in this task list is sized, and that is a statement rather than an omission

**U-48**'s re-derivation obligation is scoped to the nine capabilities it opened, and this pass
discharges exactly that. No estimate is offered for Phase 1, Phase 2, or Phases 4 through 9, for
three reasons, each traceable:

- **There is no calibration anchor.** Feature 001 measured a code graph, a provider path, loop-safety
  primitives, contract extraction and a ceiling test. It measured **no** build item for the
  enforcement point, the three kernel mechanisms, the analysis stage, the verifier or the
  measurement harnesses. Sizing them here would be judgment calibrated against nothing, which is the
  inherited-number failure arriving by a new door.
- **One of them contains an unbounded step and must not be hidden inside a confident number.**
  **SC-001**'s fifteen minutes requires a *verified* first answer, which requires the codebase
  indexed and analysed first, and **U-21** records `codegraph`'s scale claim as untested with one
  small-repository datapoint. T118 and T203 instrument and report that step separately rather than
  letting it disappear into an estimate.
- **Two of them are gated on things effort does not shorten.** **SC-013**'s window opens only once
  human labelling capacity exists (T176, T177), and **SC-017** measures whether a runtime is still
  serving traffic four weeks after installation. Neither is an effort quantity.

**So the honest total for v1 is still not a figure — but the reason has changed, and the change is
the point of this pass.** It is now:

**59–82 engineer-days for all nine runtime-core capabilities**, plus a **+0 to +4 day band** on row
4 that T050 collapses, **plus** six unsized phases with no calibration anchor in the evidence base,
**plus** an unbounded analysis step, **plus** two calendar dependencies.

Five terms became four, and the one that closed was the one that mattered: **the runtime core is no
longer a hole in the middle of the estimate.** It is 11.8–16.4 weeks for one engineer, derived per
task, with every row anchored — five of them against measurements in this corpus, and row 5 against
a measurement taken specifically to close it.

What remains unsized is unsized for reasons effort does not fix:

- **Six phases have no calibration anchor.** Feature 001 measured a code graph, a provider path,
  loop-safety primitives, contract extraction, a ceiling test and now four vendor SDKs. It has
  measured **no** build item for the enforcement point, the three kernel mechanisms, the analysis
  stage, the verifier or the measurement harnesses. Sizing those here would be judgment calibrated
  against nothing — the inherited-number failure arriving by a new door. This is the largest
  remaining term and it is larger than the nine capabilities.
- **One unbounded step must not hide inside a confident number.** **SC-001**'s fifteen minutes
  requires a *verified* first answer, which requires the codebase indexed and analysed first, and
  **U-21** records `codegraph`'s scale claim as untested on one small-repository datapoint.
- **Two are calendar, not effort.** **SC-013**'s window opens only once human labelling capacity
  exists; **SC-017** measures whether a runtime is still serving traffic four weeks after install.
  No amount of engineering shortens either.

Anyone who needs a single number should read that list as the derivation of why they cannot have one
yet — and should note that the cheapest remaining move is **not** another spike on the runtime core.
It is a calibration anchor for the enforcement point and the kernel, which is where the unsized mass
actually sits.

---

## Phase 4: User Story 1 — Operate a running application through its own specification, safely (Priority: P1) 🎯 MVP

**Goal**: one agent, one loop, read-only against one admitted target, behind an enforcement point
that resolves every outbound call per call, inside an execution environment that is
filesystem-scoped, processor- and memory-bounded, and holds no credential outliving the session.

**Independent Test**: stand up the reference application with seeded state, configure the runtime
against it, and ask questions whose correct answers are known from the seed. Separately run the
adversarial batteries: attempted writes, attempted destinations outside the pinned set, attempts to
make the enforcement point blind to the method, attempted reads and writes outside the declared
filesystem set including against the effect-gate rule set and the egress policy, and a workload that
exhausts each declared bound in turn.

**This story carries every safety obligation**, because the agent holds general-purpose capabilities
pointed at live data inside the operator's own trust boundary.

### Admission — one sequence, two stages, fail closed

- [ ] T073 [US1] Published-specification fetch with **FR-044**'s four-state classification — published and non-empty, absent, present but unreadable by the configured credential, present and readable with no operations — admitting only the first, in `src/analysis/admission.py`
- [ ] T074 [US1] Persist the admission decision with the state found, the criterion that failed, and what the operator would have to change, in `src/analysis/admission_record.py` (FR-044; a rejection is a supportable answer and is retained, not an error)
- [ ] T075 [P] [US1] Fixture set covering all four specification states, in `tests/fixtures/admission/` (FR-053)
- [ ] T076 [P] [US1] Admission contract test: 100% of non-admissible targets rejected with a named state and a named criterion, zero reaching a session, zero admitted on a specification that fetched successfully but carried no operations, in `tests/contract/test_admission.py` (**SC-018**)
- [ ] T077 [US1] Served-operation set produced by a stage **above** source analysis, carrying deployment identity, its own version and its freshness, at operation granularity, in `src/analysis/served_operations.py` (FR-002, **OD-06**)
- [ ] T078 [US1] Record the correspondence evidence establishing that this source produced this deployment, failing closed when none can be produced, in `src/analysis/correspondence.py` — **the specification states no procedure for establishing correspondence; see [Loose requirements](#loose-requirements-reported-not-worked-around) item 3**
- [ ] T079 [US1] **FR-020** confused-deputy inspection as the second admission stage, running after T073 over the operation list that stage supplied, denying the operations it finds and failing closed where inspection is impossible, in `src/analysis/deputy_inspection.py` — the property is unmeasured on any target (**U-44**) and the inspection procedure is unspecified; see [Loose requirements](#loose-requirements-reported-not-worked-around) item 2
- [ ] T080 [US1] Pin destination addresses at host-and-port granularity at admission, with no per-request re-resolution, in `src/analysis/pinning.py` (FR-016)

### The effect rule set, reviewable before it takes effect

- [ ] T081 [US1] Effect rule set and the deny list of known side-effecting reads as versioned configuration, every entry carrying a **rule identifier**, a matcher, a resolved tier and its reviewable justification, in `src/analysis/effect_rules.py` (FR-010, FR-012, FR-054)
- [ ] T082 [US1] Operator review gate before an effect rule set, a deny list or an egress policy takes effect, with any widening recorded as configuration, in `src/analysis/review_gate.py` (FR-012, FR-019)

### The single enforcement point (Go)

- [X] T083 [US1] Proxy skeleton: a cleartext listener presented to the agent as the target's base URL, in front of an origin-validating TLS client to one pinned upstream, in `src/proxy/main.go` (T-05, **OD-12**)
- [X] T084 [US1] Stage 1, capability: resolve the opaque session handle against the session table on **every** request, honouring it only while the session is `RUNNING` and the lease unexpired, in `src/proxy/capability.go` (FR-050)
- [X] T085 [US1] Stage 2, form: `CONNECT` denied, `Upgrade` denied, non-HTTP bytes refused, and ambiguous framing — conflicting length and chunking headers — **rejected outright rather than normalized**, in `src/proxy/form.go` (FR-018; normalizing is what lets the enforcement point and the target disagree about what the request is)
- [X] T086 [US1] Stage 3, destination: origin-form paths and absolute-form `http` targets naming the pinned origin accepted; absolute `https` denied with a named reason **and a counter**, in `src/proxy/destination.go` (T-09, **Q-07** — the counter is the instrument and it is owed)
- [X] T087 [US1] Stage 4, method: the method allowlist evaluated **together with** the destination on the same request, and identically whether the request originated in the runtime or in a command the agent composed, in `src/proxy/method.go` (FR-015)
- [X] T088 [US1] Stage 5, effect: match the path against the served-operation set, consult the deny list, resolve the tier **per call**, and block before anything is sent, in `src/proxy/effect.go` (FR-008, FR-009, FR-010)
- [X] T089 [US1] Stage 6: an operation the served set does not describe is **denied, not guessed**, in `src/proxy/effect.go` (FR-010)
- [X] T090 [US1] ~~Deny loopback, private, link-local and cloud-metadata addresses even when reached through an allowlisted host~~ ~~**Deny loopback and link-local (including the cloud metadata address) unconditionally with no exemption path, and deny every RFC1918 address other than the single explicitly declared target origin — the exemption keyed to that one address and not expressible as a range, a prefix or a toggle**~~ **Deny link-local (including the cloud metadata address), unique-local and the unspecified address unconditionally with no exemption path, and deny every RFC1918 and loopback address other than the single explicitly declared target origin — the exemption keyed to that one address, not expressible as a range, a prefix or a toggle, and one address in total rather than one per exemptible class**, in `src/proxy/addresses.go` (FR-017 as replaced 2026-08-03 on the private-address class and extended the same day to loopback; the first struck wording forbade a pinned upstream on an RFC1918 address, which is the ordinary self-hosted topology, and the second denied the same topology on a single host)
  - **EXTENDED TO LOOPBACK BY OWNER DECISION 2026-08-03** — the exemptible set is two classes and the exemption is still one address. All three containments were re-verified against two classes rather than assumed to carry: the equality comparison and the sole constructor are class-agnostic, and the ordering is unchanged because loopback moved *out* of the inexemptible set rather than into it. The one containment two classes newly require — one exemption in total, not one per class — is asserted against the type in `TestTheExemptionHoldsExactlyOneAddress` and behaviourally in `TestOneDeclaredOriginExemptsExactlyOneAddress`. The four Go removal proofs became **seven**; two of the original four had tamper strings that `gofmt` invalidated when the map gained a second entry, and both were reported rather than passing silently.
- [X] T091 [US1] Stage 7: re-originate with target-credential injection and ordinary certificate validation, with **no TLS interception and no response-body rewriting**, in `src/proxy/reoriginate.go` (**OD-12**, and rewriting is rejected rather than deferred because it would transform untrusted bytes on the enforcement path)
- [X] T092 [US1] Decision log carrying the rule identifier, method, path, resolved tier, session and named reason for every disposition, in `src/proxy/decisionlog.go` (FR-011)
- [ ] T093 [US1] Ingest the proxy's decision log into the trace stream, the proxy owning its own database and the runtime reading it, in `src/runtime/proxy_ingest.py` (T-06)
- [X] T094 [P] [US1] Framing-ambiguity corpus, in `src/proxy/framing_test.go` — a parser differential here is a complete defeat of FR-018 and is the named failure the second language buys against (**Q-01**)
- [ ] T095 [P] [US1] Egress-policy contract tests over every named denial reason in [`contracts/egress-policy.md`](./contracts/egress-policy.md), in `tests/contract/test_egress_policy.py`

### The execution environment — FR-048, FR-049 and FR-050's mechanisms

- [ ] T096 [US1] Sandbox image: shell and toolchain with dependencies resolved at build time, no secret, and no package index reachable, in `deploy/images/sandbox.Dockerfile` (FR-021 — which the egress policy already enforces, so this is one control and not a second mechanism)
- [X] T097 [US1] Per-session mount namespace with an **empty root** into which only the declared locations are mounted, so a location outside the set is *absent* rather than permission-denied, in `src/supervisor/mounts.py` (FR-048)
- [X] T098 [US1] Declared location set as versioned configuration stated **positively**, with the effect-gate rule set and the egress policy deliberately outside it, in `src/supervisor/location_set.py` (FR-048, FR-054 — this is what turns FR-012's no-write-path and FR-014's cannot-reach into one checkable boundary)
- [X] T099 [US1] `seccomp` user-notification listener **outside** the container holding the notification descriptor for path-taking syscalls, seeing each attempt before the kernel performs it, in `src/supervisor/seccomp.py` (FR-048's recording clause, which a mount namespace enforces and cannot record)
- [X] T100 [US1] `filesystem_decision` spans carrying the rule that produced the refusal, identical in shape to an egress denial, in `src/supervisor/fs_decisions.py` (FR-048, **SC-022**)
- [ ] T101 [US1] **Measure the syscall supervisor's overhead on the reference application before the mechanism is committed**, recording the figure and the shell-heavy arm that stresses it, in `tests/batteries/test_seccomp_overhead.py` (**Q-09** — accepted *with* the measurement, not with a prediction of its result; if it is prohibitive the recorded fallback is an audit channel that keeps SC-022 and loses the before-execution property)
  - **PARTIAL — the figure is measured and recorded** in `tests/batteries/results/seccomp-overhead.json`, on three proxy workloads. T101 asks for the **reference application**, which does not exist, so that clause is **outstanding**.
- [X] T102 [US1] Session cgroup created and owned by the supervisor **before the container starts**, in `src/supervisor/cgroup.py` (FR-049)
  - **Extended 2026-08-03 by FR-049's pre-exec barrier clause, and this task as written does not discharge it.** Creating the cgroup before the container starts is one end; the other is that every bound is written before the workload process exists and the workload does not execute its first instruction until it is a member. The test that demonstrates it must show the workload **blocked before `execve`** and released only after membership — a test that spawns, attaches, and then observes the bound holding never enters the window and proves nothing about it
- [X] T103 [US1] The four controls — `memory.max` with `memory.oom.group`, `cpu.max` as a rate, cumulative `cpu.stat` against a declared total, and `pids.max` — in `src/supervisor/bounds.py` (FR-049; processor time is two bounds because **SC-023** asks two different things of one requirement, and `pids.max` is an addition marked as one because a fork bomb is the cheapest way to defeat the co-located-workload clause)
- [X] T104 [US1] No writable `cgroup` mount and no delegation inside the container, so nothing running inside can raise, extend or evade a bound, in `src/supervisor/cgroup.py` (FR-049's enforced-from-outside clause)
- [X] T105 [US1] Bound exhaustion ends the session in the matching named terminal state — `terminated.memory_bound_exhausted`, `terminated.cpu_bound_exhausted`, `terminated.process_bound_exhausted` — never by generic error, in `src/supervisor/bounds.py` (FR-049, FR-006)
- [X] T106 [P] [US1] Bounds battery: exhaust each declared bound in turn, asserting a named terminal state, that work already performed still counts against FR-005's ceilings, and that a co-located reference workload on the same host keeps serving throughout, in `tests/batteries/test_bounds_exhaustion.py` (**SC-023**)
- [X] T107 [US1] Capability handle as **opaque random bytes** — not a claim, not signed, nothing offline-verifiable — in `src/supervisor/capability.py` (FR-050 layer 1)
- [X] T108 [US1] Supervisor lease renewal on a short interval, with the proxy honouring `RUNNING` only while `lease_expires_at` is in the future, so that on a crash **nothing renews and the authority lapses without any code having run**, in `src/supervisor/lease.py` (FR-050 layer 2)
- [X] T109 [US1] Per-session listener whose socket the supervisor holds open by its own file descriptor inside the session's network namespace, so the kernel performs the revocation when the supervisor dies, in `src/supervisor/listener.py` (FR-050 layer 3)
- [X] T110 [US1] Fresh container and fresh scratch volume per session, both keyed by session id, with a resumed session reattaching **its own** scratch because FR-007 makes it the same session, in `src/supervisor/session_env.py` (FR-050's not-inherited clause)
- [ ] T111 [US1] **Lease-revocation replay fixture**: capture the capability handle from inside a live session, `SIGKILL` the session **from a separate process** so no cleanup path can run, then replay from inside a later session's environment (denied and recorded) and from a position with no path to the enforcement point (refused by unreachability, recorded only as a drop counter), **reporting the two arms separately**, in `tests/fixtures/credential-replay/` (**SC-024**; the separate-process kill is finding 006's technique, chosen for exactly this reason, and the two arms are not pooled because the topology gives them different recording properties)
  - **DONE, different location** — `tests/integration/test_lease_revocation.py`, kept with the other FR-050 arms rather than split into `tests/fixtures/credential-replay/`, because the two replay arms only mean anything next to the `SIGKILL` fixture they share a setup with. Both arms reported separately.
- [ ] T112 [US1] Measure the residual lease window against its configured value and mark that value unvalidated wherever it appears, in `tests/batteries/test_lease_residual_window.py` (FR-043, FR-050 — the window is disclosed rather than denied, and it applies only where the supervisor survives but the session row was not updated)
  - **DONE, different location** — `test_the_residual_window_is_bounded_by_the_configured_interval` in `tests/integration/test_lease_revocation.py`.

### The runtime's own plane, the batteries, and the SC-001 path

- [ ] T113 [US1] The runtime's own default-deny egress plane pinned to the model provider, in `src/runtime/egress.py` (T-10 — an addition beyond what the specification requires, because FR-014 through FR-019 scope to the execution environment and the principle's concern is the process that puts attacker-influenceable text into a model)
- [ ] T114 [P] [US1] Adversarial battery for **SC-002** and **SC-003**: zero calls that did not resolve read-only reach the target, 100% of denials state their rule, zero outbound connections leave for a destination outside the pinned set including those a command opened itself, and zero requests allowed whose method could not be read, in `tests/batteries/test_adversarial_egress.py`
- [ ] T115 [P] [US1] Adversarial battery for **SC-022**: zero reads and zero writes succeed outside the declared set — including against the effect-gate rule set, the egress policy and another session's artifacts — zero partially succeed, and 100% of refusals are recorded with their rule, in `tests/batteries/test_adversarial_filesystem.py`
  - **Scored on the record's existence and its rule, per SC-022's 2026-08-03 narrowing.** No arm may assert that the recorded `path` equals the path the adversary asked for: the supervisor reads that path out of the workload's own memory, so a workload rewriting it between the read and the kernel's resolution misattributes an audit entry — and obtains no access, because the mount namespace makes an undeclared path absent. An arm asserting path equality would fail against a correctly-behaving supervisor. The `path` is best-effort and carries its provenance; the rule identifier is the supervisor's own and is what this battery scores
- [ ] T116 [US1] Reference application with seeded state and known-correct answers, plus its **stated size**, in `tests/fixtures/reference-app/` (FR-053)
- [ ] T117 [US1] Unattended first-verified-answer harness measuring the **SC-001** path from starting configuration, in `tests/integration/test_sc001_first_answer.py`
- [ ] T118 [US1] **Instrument analysis wall time separately from the rest of the SC-001 window, and state the reference application's size wherever SC-001 is reported**, in `src/analysis/timing.py` — SC-001 is a compound of a bounded step and an unbounded one, **U-21** records `codegraph`'s scale claim as untested, and reporting the two together is what makes the criterion quietly true on small inputs and quietly false on large ones

**Checkpoint**: User Story 1 is independently testable — a verified answer on the reference
application, with every adversarial arm denied and recorded.

---

## Phase 5: User Story 2 — Know whether the answer was actually right (Priority: P2)

**Goal**: for every reported result, recompute the reported quantity by a path independent of the
one that produced it, and report exactly one of three states with the state visible to the caller.

**Independent Test**: a corpus of results with injected value faults including near-misses smaller
than one percent of the correct value, and a matched corpus of clean results. Report detection rate
and false-alarm rate. Separately, confirm a verifier restricted to shape and type conformance
detects **none** of the value faults — the control that demonstrates detection comes from
recomputation rather than from conformance checking.

- [ ] T119 [US2] `codegraph` invoked as a subprocess at analysis time only, absent from every run-time image, in `src/analysis/codegraph.py` (T-11, **D-14**)
- [ ] T120 [US2] Static derivation of contracts and checks from source with **no model call anywhere in it**, in `src/analysis/derive.py` (T-13, FR-023 — static derivation was measured at zero model spend, so this costs nothing that was ever measured to be worth having)
- [ ] T121 [US2] Provenance as data on every derived contract and check — the derivation rule, the source symbol, the source file, the analyzer version, a content hash and a validation status — in `src/analysis/provenance.py` (FR-026)
- [ ] T122 [US2] Mark a derived contract `validated` when it agrees with the target's **published specification** and `provisional` with provenance and confidence otherwise, in `src/analysis/validate.py` (T-14, FR-026, constitution Principle I as amended at v1.1.0 — the independent artifact is in hand for every admitted target because FR-002 makes it an admission criterion)
- [ ] T123 [P] [US2] Enforce at the type level that a `provisional` contract can produce **not verifiable** and never **verified**, in `src/analysis/validate.py` and `tests/invariants/test_provisional_never_verified.py`
- [ ] T124 [US2] Verifier recomputing the reported quantity by an independent path, with conformance to a declared shape explicitly **not** accepted as verification, in `src/runtime/verify.py` (FR-022 — the failure class that matters is conformant end to end and wrong)
- [ ] T125 [US2] Refuse with a named reason where no check of stated precision can be derived, never falling back to a default tolerance, in `src/runtime/verify.py` (FR-024) — **"stated precision" is undefined in the specification; see [Loose requirements](#loose-requirements-reported-not-worked-around) item 4**
- [ ] T126 [US2] `ResultRecord` with **exactly one constructor**, taking a `VerificationOutcome`, in `src/runtime/result.py` (FR-025, and the first of the three structural facts that make FR-052 a construction rather than a policy)
- [ ] T127 [US2] Three exhaustive, mutually exclusive states — verified, not verifiable, refused — distinguishable by a consuming system rather than by a human reading prose, in `src/runtime/result.py` (FR-025, **OD-19**)
- [ ] T128 [US2] Staleness as a **separate field** on the same record, never a fourth state, so that verified-and-stale and unverifiable-and-stale are both representable and distinguishable, in `src/runtime/result.py` (FR-047)
- [ ] T129 [P] [US2] Assert the derivation reference and the reported value never share a source, in `tests/contract/test_independent_derivation.py` (FR-024)
- [ ] T130 [US2] Report the share of results returned in the not-verifiable state, broken down by FR-024's named refusal reasons, per reporting window, with **no threshold applied because none is pre-registered**, in `src/runtime/reports/not_verifiable.py` (FR-045, **SC-019**, the second half of **OD-19**)
- [ ] T131 [P] [US2] Injected value-fault corpus including faults smaller than one percent of the correct value, plus a matched corpus of correct results, in `tests/fixtures/value-faults/` (**SC-005**)
- [ ] T132 [P] [US2] Shape-and-type-only control verifier asserted to detect **none** of T131's faults, in `tests/batteries/test_conformance_control.py` (**SC-006**)
- [ ] T133 [P] [US2] Coverage test: 100% of derived contracts and checks carry provenance and a validation status, and zero are presented as validated without an artifact their own derivation did not produce, in `tests/contract/test_provenance_coverage.py` (**SC-007**)
- [ ] T134 [P] [US2] Result-record contract tests over every state, every stale-and-state combination, and the exhaustiveness of the three, in `tests/contract/test_result_record.py`
- [ ] T135 [US2] Analyzer fixture repositories with known-correct expected output, committed alongside the capability, in `tests/fixtures/analyzer/` (FR-053, constitution Principle VII's analyzer clause)
- [ ] T136 [P] [US2] Assert a `codegraph` schema-hash mismatch fails the analysis stage rather than emitting a drift signal, in `tests/contract/test_codegraph_schema_pin.py` (**U-04** — a changed upstream schema must never be read as changed source)

> **Expect a provisional share and do not read it as a fault.** Finding 007 measured this comparison
> on one target and one framework: the literal reading of its gate is **0.8696** and the validated
> reading **0.7681**, so roughly a quarter provisional on a comparable target is the expectation.
> That is one framework whose design premise is that the signature is the schema, and it must not be
> generalized — it is recorded so the share is expected rather than alarming.

**Checkpoint**: User Stories 1 and 2 both work independently.

---

## Phase 6: User Story 3 — Fail closed when the code or the deployment moves (Priority: P3)

**Goal**: two independently versioned clocks, drift detected separately on each, only the affected
operation disabled, and the whole thing loud rather than silent.

**Independent Test**: two synthetic corpora, each controlling its own change time. In the first,
mutate source so derived contracts no longer match, leaving the deployment untouched. In the second,
change what the deployment serves, leaving source untouched. Report detection, whether anything
unaffected was disabled, and how long detection took. **Plus the negative**: re-analysing unchanged
input produces no signal at all.

- [ ] T137 [US3] Source-derived and deployment-derived artifacts as two **independently** versioned things, in `src/analysis/clocks.py` (FR-027, **OD-06** — a shared version cannot express that one changed and the other did not, which is the whole content of drift)
- [ ] T138 [US3] Source-drift detection in the **same automated check run** as the change that caused it, in `src/analysis/source_drift.py` (FR-028, **SC-008**)
- [ ] T139 [US3] Drift signal record stating which clock moved, the artifact versions before and after, and the deployment identity, in `src/analysis/drift_signal.py` (FR-031)
- [ ] T140 [US3] The failed-re-fetch signal shape, where there is no *after* artifact version: the specification state found, named from FR-044's four-state classification, plus the timestamp of the last successful fetch, in `src/analysis/drift_signal.py` (FR-031's narrowing, FR-047)
- [ ] T141 [US3] Deployment-drift scheduler performing a re-fetch of the target's published specification, requiring no event from the customer's pipeline, no phone-home and no outbound request to any destination other than the target, in `src/runtime/drift_scheduler.py` (FR-046, FR-029)
- [ ] T142 [US3] **Route the scheduler's re-fetch through the enforcement point**, in `src/runtime/drift_scheduler.py` — otherwise this is a second, continuous path to the target, and FR-014's single-enforcement-point guarantee is true of the sandbox and false of the system. That path is continuous and nobody had flagged it (**OD-12**, T-10)
- [ ] T143 [US3] Manual on-demand drift check for **either clock at any time**, always available and not configurable away, in `src/runtime/drift_manual.py` (FR-029, **OD-20**)
- [ ] T144 [US3] The two additional configurable triggers — a deployment event emitted by the customer's own rollout mechanism, which **must not be assumed available**, and a re-check at session start — in `src/runtime/drift_triggers.py` (FR-046)
- [ ] T145 [US3] Record a failing path-level reachability precondition as a drift signal **backstop**, and never rely on it as a trigger design, in `src/runtime/drift_backstop.py` (FR-046)
- [ ] T146 [US3] On detected drift disable the affected operation and surface it loudly while unaffected operations keep working, in `src/runtime/drift_disable.py` (FR-030, **SC-009**)
- [ ] T147 [US3] Enter the stale state on the first re-fetch returning any of FR-044's three non-admissible states: mark the served-operation set stale rather than discarding it, and raise the drift signal on that same run, in `src/runtime/staleness.py` (FR-047, **OD-21** — which authorises FR-047 and the narrowings it makes at FR-001, FR-030 and FR-031, and which was recorded while this task list was being written; no requirement text changed with it)
- [ ] T148 [US3] Carry the stale marking, the set's age and the specification state last found on every result produced while the set is stale, machine-distinguishably, in `src/runtime/staleness.py` (FR-047, **SC-021**)
- [ ] T149 [US3] Enforce the staleness ceiling as **wall-clock from the last successful fetch**, so lengthening the interval cannot silently widen it, in `src/runtime/staleness.py` (FR-047; the ceiling is a configured default marked unvalidated under FR-043)
- [ ] T150 [US3] Past the ceiling: deny every call under FR-030 with the stale set and its age named as the rule, and terminate any in-flight session in a **named** terminal state rather than by generic error, in `src/runtime/staleness.py` (FR-047, FR-011, FR-006)
- [ ] T151 [US3] Leaving the stale state below the ceiling: replace the last-known-good set, clear the marking, and **evaluate the difference between the two sets as drift** rather than adopting it silently, in `src/runtime/staleness.py` (FR-047 — a re-fetch that merely succeeds is not evidence that nothing changed)
- [ ] T152 [US3] Recovery from past the ceiling running the **full admission sequence** — T073 then T079 — and recording a new admission decision, with no operator restart required, in `src/runtime/staleness.py` (FR-047; past the ceiling the system holds no founded belief about what the deployment serves)
- [ ] T153 [US3] On every successful fetch, compare the newly fetched set against the last **inspected** set and inspect every operation present in the first and absent from the second before it becomes available, failing closed on any it cannot inspect, in `src/analysis/reinspect.py` (FR-051, **SC-026**)
- [ ] T154 [P] [US3] Source-change synthetic corpus controlling its own change time, committed alongside the capability, in `tests/fixtures/drift-source/` (FR-053, SC-008)
- [ ] T155 [P] [US3] Deployment-change synthetic corpus controlling its own change time, in `tests/fixtures/drift-deployment/` (SC-009, **SC-020**)
- [ ] T156 [P] [US3] **Negative test: across a battery in which source is held constant and only re-analysis is repeated, zero source-clock drift signals are raised**, in `tests/batteries/test_drift_negative.py` (**SC-029** second clause — this is the only false-alarm figure v1's drift capability has any way to produce before production, and it is the clause that proves T010 actually closed the false-alarm channel)
- [ ] T157 [P] [US3] Fixture withdrawing an admitted target's published specification and later restoring it, in `tests/fixtures/spec-withdrawn/` (**SC-021**)
- [ ] T158 [P] [US3] Fixture adding an operation to a specification the target never stops publishing, in `tests/fixtures/operation-added/` (**SC-026**)

**Checkpoint**: all three core capabilities are independently functional.

---

## Phase 7: User Story 4 — Run it in your own environment, on your own model provider (Priority: P4)

**Goal**: every component inside the operator's boundary, bring-your-own-credentials across at least
four providers, and no secret anywhere the model or the environment can read.

**Independent Test**: complete the User Story 1 battery once per supported provider with
configuration as the only difference, and scan every trace, artifact and persisted record — and the
execution environment itself — asserting no secret value appears.

**Dependency worth stating.** This story *constrains* the first three more than it delivers a
separate slice, which is why the provider driver sits in Phase 3 and only the four-provider battery
and the credential planes sit here.

- [ ] T159 [US4] Four OCI images — analysis, runtime, supervisor, enforcement point — plus the sandbox base image, in `deploy/images/` (T-11, **OD-08**)
- [ ] T160 [US4] The compose bundle we author, with reference-application values marked under FR-043 as fixture configuration rather than product defaults, in `deploy/compose/` (T-11)
- [ ] T161 [US4] Two credential planes: the provider credential held by the runtime, the target credential held by the enforcement point and injected on re-origination, neither reaching the execution environment, in `src/contracts/credentials.py` (FR-036, FR-050)
- [ ] T162 [US4] The analysis/runtime/target boundary explicit in configuration even when all three run on one host, with co-location never assumed, in `src/contracts/topology.py` (FR-034)
- [ ] T163 [US4] Provider selection by configuration with **no provider-specific behaviour in the core path**, in `src/runtime/providers/select.py` (FR-037)
- [ ] T164 [US4] Run the full User Story 1 battery against **at least four independent providers** with configuration as the only difference between runs, in `tests/batteries/test_four_providers.py` (**SC-010** — now a test v1 must pass rather than a result it inherits)
- [ ] T165 [P] [US4] Automated secret scan over model context, emitted artifacts, traces and persisted state, running on **every** session, in `tests/batteries/test_secret_scan.py` (FR-036, **SC-004**)
- [ ] T166 [P] [US4] In-container scan asserting no secret is readable from the environment, the process table, or any mount in the declared set, in `tests/batteries/test_in_container_scan.py` (FR-050's not-present clause, **SC-024**)
- [ ] T167 [P] [US4] Not-inherited test: nothing written inside one session's environment is readable from a later session's, in `tests/batteries/test_environment_not_inherited.py` (FR-050, SC-024)
- [ ] T168 [P] [US4] Assert no operator-specific path, hostname, address or credential is written into any emitted artifact, in `tests/contract/test_artifact_portability.py` (FR-033)
- [ ] T169 [US4] Operator-boundary check: every component runs inside the operator's boundary and no target data or credential is required to leave it, in `tests/integration/test_operator_boundary.py` (FR-032)
- [ ] T170 [P] [US4] Cassette-backed provider tests over the core path, in `tests/conformance/` (constitution Principle VII, added because the specification does not capture it for v1)
- [ ] T171 [US4] Exercise the fail-loud startup path end to end through the shipped bundle, in `tests/integration/test_bundle_failloud.py` (FR-033)
- [ ] T172 [P] [US4] Assert every supported-platform surface states **Linux only with no degraded mode**, in `tests/contract/test_platform_statement.py` (**OD-17**, FR-053, SC-027 — a degraded mode is a sandbox missing one of Principle IV bullet 1's terms)

**Checkpoint**: the product is installable and portable across providers inside an operator's own
boundary.

---

## Phase 8: User Story 5 — Learn from production whether the three claims hold (Priority: P5)

**Goal**: the instrumentation, not just the capabilities. All three of v1's differentiating claims
ship unmeasured, so this phase builds what would measure them.

**Independent Test**: over a fixed window, produce three reports — the verifier's marginal detection
over the shadow judge with the pre-registered gate applied and all three branches intact; the effect
gate's read-only precision against a labelled corpus of real operations; and drift detection rate,
false-alarm rate and latency on each clock.

### The verifier's margin over a shadow judge

- [ ] T173 [US5] Shadow judge consuming the trace stream **asynchronously**, never in the request path, writing `judge_verdict` rows keyed to a result in a table nothing on the success path reads, in `src/runtime/judge/shadow.py` (FR-039)
- [ ] T174 [US5] Make the judge injectable so the same sessions can run with it agreeing, disagreeing, and not running at all, in `src/runtime/judge/inject.py` (**SC-025**)
- [ ] T175 [P] [US5] Differential battery asserting 100% of caller-visible result records and 100% of gate decisions are identical across the three runs, with zero behavioural differences attributable to the judge, in `tests/batteries/test_judge_differential.py` (**SC-025**, FR-052 — T025's import-graph test is the structural half of the same guarantee)
- [ ] T176 [US5] **Adjudication queue**: a sampling rule pre-registered **before** the window opens, an operator-facing surface presenting a sampled result with the evidence needed to judge it, and `human_label` rows carrying the adjudicator and the time, in `src/runtime/adjudication/` — **FR-040**'s third branch reads the judge's own discrimination, which needs human ground truth; the verifier's verdict cannot supply it without circularity and a model is the exact substitution **FR-052** exists to prevent
- [ ] T177 [US5] **FR-040** gate report with all three branches intact — ten percentage points or more makes the verifier a headline capability, a smaller margin makes it an internal detail, and a judge no better than chance triggers a constitutional prohibition independently of the verifier's score — carrying the stated precondition that **SC-013**'s window opens only once labelling capacity exists, in `src/runtime/reports/margin.py` ([`plan.md`](./plan.md) Complexity Tracking row 1; the corpus records that the one adjudication pass this needed was never performed and that a model stood in)

### The effect gate's read-only precision

- [ ] T178 [US5] Record per request at the enforcement point: the resolved tier, the rule identifier, the matched operation template, the method, the specification metadata that operation carried, and the disposition, in `src/proxy/observation.go` (FR-041 — that record *is* the corpus)
- [ ] T179 [US5] Corpus exporter producing the labelled set FR-041 scores against, in `src/runtime/reports/effect_corpus.py`
- [ ] T180 [US5] State-diff oracle on the reference application — snapshot the application's state, issue the call, diff — labelling read-only precision by **observable state** and not by any model judgement, in `tests/batteries/effect_gate_oracle.py` (FR-041, constitution Principle I's admissible artifacts)
- [ ] T181 [US5] Record the per-call threshold as **unset** and block every write capability until a threshold is pre-registered *for a per-call gate* and measured, in `src/runtime/reports/effect_precision.py` (FR-041, **SC-014**, **OD-10** — the superseded per-tool number does not travel: different base rate, different blast radius, and inventing one here is the inherited-number failure arriving by a new door)

### Drift detection on both clocks

- [ ] T182 [US5] Drift measurement harness reporting detection rate, false-alarm rate and detection latency **per clock**, in `tests/batteries/test_drift_measurement.py` (FR-042, **SC-015**)
- [ ] T183 [US5] Pre-register the measurement design **before the measurement runs**, naming which population each latency figure is measured on, in `docs/preregistration/drift.md` (FR-042)
- [ ] T184 [US5] Record that deployment-clock latency is measurable on the synthetic corpus because the corpus controls the change time, and generally **not** on real traffic unless the customer emits a deployment event FR-046 says may not be assumed, in `docs/preregistration/drift.md` — a property of the world, not a gap in the design, and inferring the change time from first observation would measure the detector against itself

### The measurement substrate all three depend on

- [ ] T185 [US5] `BatteryRun` freeze carrying **U-47**'s four terms — the prompt and request text **inside** the trace record, the battery version and task-file hashes pinned in the freeze, the cross-battery census pinned as an invariant re-checked on load, and an analysis path that **refuses** a cross-battery join — in `src/runtime/batteries/freeze.py` (FR-053)
- [ ] T186 [P] [US5] Four loader-refusal tests, one per U-47 term: an edited prompt, a changed battery version, a census mismatch, and an attempted cross-battery join, each **failing rather than warning**, in `tests/contract/test_battery_loader.py` — U-47 is the register entry recording a hash-pinned trace corpus that rebased onto edited prompts while every hash check kept passing
- [ ] T187 [P] [US5] Assert the measurement tables are structurally apart: no success-path table references `judge_verdict`, `human_label`, `effect_gate_observation` or `battery_run`, and no success-path module imports their writers, in `tests/invariants/test_measurement_isolation.py`
- [ ] T188 [US5] Define FR-045's reporting window as configuration and mark it unvalidated, in `src/runtime/reports/windows.py` — **the specification defines no window; see [Loose requirements](#loose-requirements-reported-not-worked-around) item 5**
- [ ] T189 [P] [US5] Audit every external product surface for the four prohibited claim shapes — capability advantage for an application-specific tool surface, synthesis being safer, a cost figure without basis and scope, and "provably" for effect resolution — in `docs/claims-audit.md` (FR-043, **SC-016**)
- [ ] T190 [P] [US5] Audit every statement of what the product supports for a language, framework or target shape with no committed fixture and asserted expected output, in `docs/support-audit.md` (FR-053, **SC-027**)
- [ ] T191 [US5] Measure, per deployed runtime, whether it is still serving traffic four weeks after installation, recording an installed-demonstrated-then-unused runtime as a **non-adoption** rather than an install, in `src/runtime/reports/adoption.py` (**SC-017**)
- [ ] T192 [US5] Standing report of every value still marked unvalidated — FR-046's detection window, FR-047's staleness ceiling, FR-049's two bounds, the lease interval — in `src/runtime/reports/unvalidated.py` (FR-043)
  - **Extended 2026-08-03**: the report also carries **the Linux kernel floor of 5.14 as DERIVED and NOT TESTED**, listed as a distinct kind rather than folded in with the four. The four are values an operator configures; the floor is a preflight constant read out of documented feature introduction rather than out of a boot, and it is the only entry a measurement would close (T205, **deferred by owner decision 2026-08-03**, so this entry stays on the report indefinitely rather than until a scheduled matrix run clears it). Whatever wording the report uses, it may not be weaker than the preflight's own, which states the derivation and the untested status together and has a removal proof behind it (**OD-17**, FR-053, FR-043)
- [ ] T205 [US5] **DEFERRED BY OWNER DECISION 2026-08-03 — not planned work for v1.** **Boot the supported-kernel matrix and convert the derived floor into a tested one** — 5.14, 5.15 LTS, 6.1 LTS and 6.6 LTS, running the FR-048, FR-049 and FR-050 mechanism batteries on each — in `.github/workflows/kernel-matrix.yml` (**OD-17**, FR-053). Until this exists, **every run to date was on 6.12** and 5.14 is a lower bound on what *could* work rather than a statement that it does. Recording the boots is the whole task: cgroup delegation semantics, `pivot_root` in a user namespace and `seccomp` notification behaviour all moved across the intervening releases, so a green 6.12 run is evidence about 6.12 and about nothing below it
  - **DEFERRED, NOT DROPPED, AND THE CAVEAT IS NOT RELAXED IN EXCHANGE** — the owner accepted shipping the derived floor **marked NOT TESTED** rather than building the matrix now, so this task is a recorded non-decision to measure and is not work anybody is waiting on. The task keeps its number and its full description because deferring the measurement is what makes the marking load-bearing: **5.14 remains DERIVED and NOT TESTED wherever it appears**, the preflight goes on stating the derivation and the untested status in one string, and the removal proof that fires when that caveat is dropped stays in the suite. Reinstated by an owner decision to measure, and by nothing else — in particular, not by a green run on any single kernel

**Checkpoint**: every claim the product makes either traces to a measurement or is marked
unvalidated, and the instruments that would close the three unmeasured ones exist.

---

## Phase 9: Polish and cross-cutting concerns

- [ ] T193 Attribution test: for 100% of sessions a failure is attributable **from the trace alone** to a versioned identity, a typed terminal and the decision that reached it, without re-running the session, in `tests/contract/test_attribution.py` (**SC-012**)
- [ ] T194 Map FR-038's per-node trace record onto v1's nearest subject — the turn and the step — and **record, rather than invent, the terms that have no v1 subject**, in `src/runtime/trace_node.py`; see [Loose requirements](#loose-requirements-reported-not-worked-around) item 1
- [ ] T195 [P] Record the retry-versus-repair distinction FR-038 requires as **undefined in this specification**, in `docs/open-definitions.md` — the requirement names the distinction and nothing in the corpus defines either term
- [ ] T196 [P] Run every [`quickstart.md`](./quickstart.md) validation scenario end to end, in `tests/integration/test_quickstart_scenarios.py`
- [ ] T197 [P] Operator documentation of both obligations the Assumptions section states — running the enforcement point and routing the environment through it, **and** running the agent's commands inside an environment that is filesystem-scoped, bounded, and holds no credential outliving the session — in `docs/operator-obligations.md`
- [ ] T198 [P] Reconciliation pass over `tests/invariants/invariants.yaml`: every invariant has a test and every test in `tests/invariants/` has an invariant
- [ ] T199 [P] Record T101's measured syscall-supervisor overhead figure wherever the mechanism is described, in `docs/overhead.md` (**Q-09**)
- [ ] T200 [P] Reconcile the committed fixture inventory against FR-053 — every measurable outcome naming a corpus, battery or fixture set has it committed alongside the capability — in `tests/fixtures/README.md`
- [ ] T201 Run `tools/gen_claims.py` and `tools/check_corpus.py` in CI so a stale generated claim or a dangling identifier fails the build, in `.github/workflows/ci.yml`
- [ ] T202 [P] Security review of the enforcement point against its named failure classes — parser differential, request smuggling, ambiguous framing, and the confused-deputy composition where the proxy holds the target credential and stacks with **U-44** — in `docs/security-review.md`
- [ ] T203 [P] Record the reference application's size and the one measured `codegraph` datapoint wherever **SC-001** is reported, in `docs/sc001-scope.md` (**U-21** — the scale claim is untested and extrapolates nothing)
- [ ] T204 Constitution re-check against all eight principles after implementation, in `docs/constitution-recheck.md`

---

## Loose requirements, reported not worked around

Six requirements are specified too loosely for a complete task to be written against them. In each
case a task exists and it does the part that is determined, records the gap as data, and fails
closed where the missing decision would otherwise be guessed. **None of these is fixed here**: this
pass writes only `tasks.md`.

| # | Requirement | What a task cannot be written against | Task that carries the gap |
|---|---|---|---|
| 1 | **FR-038** and **SC-012** | The requirement asks for one trace record **per executed node**, carrying a versioned *node* identity, the *routing decision* together with the inputs its *predicate* saw, precondition and postcondition results, an explicit distinction between a *retry* and a *repair*, and per-*node* cost. **v1 emits no graph, no nodes, no routing and no predicates** — Principle II's deviation record is accepted on exactly that ground. So six of the requirement's terms have no v1 subject, and the specification does not say what the substitute is: a turn, a step, or a tool call. SC-012 inherits the same three terms | T193, T194, T195 |
| 2 | **FR-020**, restated by **FR-051** | It requires safe-method operations to be *inspected* for confused-deputy behaviour and to **fail closed where inspection is impossible** — but states no inspection procedure, so "cannot be inspected" is not decidable. What evidence in a published specification constitutes an inspection outcome is unspecified, and the property is unmeasured on any target (**U-44**) | T079, T153 |
| 3 | **FR-003** and admission | [`data-model.md`](./data-model.md) gives `Deployment` a `correspondence_evidence` field described as "what established that this source produced this deployment (FR-003)", and [`quickstart.md`](./quickstart.md) step 2 says admission "establishes correspondence between the running deployment and the source commit". **FR-003 says neither.** It requires the agent to act only through the external interface; nothing in the specification says how correspondence is established or what evidence suffices — yet admission cannot complete without it | T078 |
| 4 | **FR-024** | "Where no check of **stated precision** can be derived" creates the entire not-verifiable state, and where precision is stated is unspecified — in the derived check, in the caller's request, or in the target's published specification. **SC-005**'s detection and false-alarm figures are scored against whatever this resolves to, so the criterion's meaning moves with it | T125 |
| 5 | **FR-045** and **SC-019** | Both speak of "each reporting window" and "the first production reporting window" with no window length and no report surface defined. The *absence of a threshold* here is deliberate and correct; the absence of a window is not stated as deliberate anywhere | T130, T188 |
| 6 | **FR-006**'s stall condition | [`data-model.md`](./data-model.md) names `terminated.no_progress` as an FR-006 stall condition. Neither FR-006 nor any success criterion defines what no progress is, so the predicate that fires it is unwritable as specified | T067 |

**Two further items are deferred by decision rather than loose, and the difference matters.**
**FR-041**'s threshold is unset because pre-registration for a per-call gate is an owner act that
precedes measurement (T181), and **SC-013**'s window is gated on labelling capacity that does not
exist (T176, T177). Both are recorded in [`plan.md`](./plan.md)'s Complexity Tracking. Neither is a
specification defect.

---

## Complexity carried forward, not softened

[`plan.md`](./plan.md)'s Complexity Tracking reports nine items as impractical rather than
weakening them. Each is carried into a task rather than left in prose, and the four the owner
flagged specifically are the first four rows.

| Item as recorded | How this task list carries it |
|---|---|
| **SC-001 contains an unbounded step** — a verified answer requires analysis to complete and **U-21** records `codegraph`'s scale claim as untested on one small-repository datapoint | T118 instruments analysis wall time separately; T116 states the reference application's size; T203 requires both to be reported wherever SC-001 appears. **No task in Phase 4 or Phase 5 carries an estimate**, and the reason is stated in the estimate section rather than being absorbed into a confident number |
| **SC-013's thirty-day window is not reachable as written** — FR-040's third branch needs human ground truth that does not exist | T176 builds the adjudication queue; T177 reports the gate with the precondition stated. The verifier's own verdict is not substituted (circular) and no model is substituted (the thing FR-052 prevents) |
| **SC-024's recording clause is not uniform** — a replay reaching the enforcement point is denied and recorded; a replay with no path to it is refused by unreachability and recorded only as a drop counter | T111 exercises both arms and **reports them separately**, rather than pooling them into one figure the topology does not support |
| **FR-048's recording clause forces a syscall supervisor whose overhead is unmeasured** | T099 builds it; T101 **measures it on the reference application before the mechanism is committed** and records the fallback branch; T199 carries the figure wherever the mechanism is described (**Q-09**) |
| **FR-050 leaves a residual window of one lease interval** in the narrow case where the supervisor survives but the session row was not updated | T108 and T109 make the common crash close instantly through a descriptor the kernel closes; T112 measures the residual window against its configured value; T033 marks that value unvalidated |
| **A second language at the enforcement point** | T003, T083–T092 and T094's framing corpus. The named failure is a parser differential at the one point where disagreeing with the target about the method and path defeats FR-018 entirely (**Q-01**) |
| **Deployment-clock drift latency is not measurable on real traffic** unless the customer emits a deployment event FR-046 says may not be assumed | T183 and T184 state which population each figure is measured on; T155 supplies the corpus that controls its own change time |
| **FR-041's threshold is left unset** | T181 records it unset and blocks write capability until it is pre-registered for a per-call gate and measured |
| **Linux only, with no degraded mode** | T006's preflight and T172's platform-statement audit (**OD-17**) |

---

## Dependencies and execution order

### Phase dependencies

- **Phase 1 (Setup)** — no dependencies.
- **Phase 2 (Foundational A)** — depends on Phase 1. **Blocks everything.** T010's canonical
  serializer is a precondition of drift detection specifically: without it the source-derived
  artifact's hash changes on every run and drift reports a false alarm every interval.
- **Phase 3 (Foundational B, the runtime core)** — depends on Phase 2. **Blocks every user story**,
  because after **OD-15** there is no framework supplying any of it.
- **Phases 4–8 (user stories)** — depend on Phase 3. In priority order, or in parallel if staffed.
- **Phase 9 (Polish)** — depends on the stories in scope.

### Cross-story dependencies, stated because two of them break the usual independence

- **US4 is not independent of US1 and does not pretend to be.** **SC-010** runs *the User Story 1
  battery* per provider, so T164 depends on Phase 4 completing. The specification says as much: US4
  constrains how the first three stories are built more than it delivers a separate slice.
- **US5 depends on all four.** It instruments them. T178 lives in the enforcement point US1 builds,
  T180's oracle needs US1's reference application, and T182 needs US3's corpora.
- **US2 and US3 are genuinely independent of each other** and of US1 beyond Phase 3, and can be
  built in parallel.
- **US3's T142 reaches back into US1's boundary.** Routing the drift scheduler through the
  enforcement point is what keeps FR-014's guarantee true of the system rather than only of the
  sandbox, so it is a US3 task with a US1 acceptance consequence.

### Within a phase

Schemas and the canonical form before storage; storage before the artifact store; the invariants
file before the invariants; configuration before anything that reads it; the loop before the runner;
the journal before resume; the drivers before the conformance fixture; the enforcement point before
its observation record.

### Parallel opportunities

**62 tasks carry `[P]`.** The largest clusters:

| Cluster | Tasks | Why they are independent |
|---|---|---|
| Setup | T003–T008 | Different toolchains and different files |
| Invariants | T024–T028 | One test file each, over an interface Phase 2 has already fixed |
| Configuration and marking | T032–T034 | Separate contract-test files |
| Trace contracts | T039, T040 | Separate assertions over one writer |
| Fixture sets | T075, T131, T135, T154, T155, T157, T158 | Committed data, one directory each, and FR-053 requires them alongside the capability rather than later |
| Adversarial batteries | T114, T115 | Different boundaries, different assertions |
| Verification contracts | T129, T132, T133, T134, T136 | Separate files over T124–T128's interface |
| Credential and secret scans | T165–T168, T170, T172 | Separate batteries over one completed session |
| Measurement isolation and audits | T186, T187, T189, T190 | Separate files, no shared state |
| Polish | T195–T200, T202, T203 | Documentation and reconciliation, no code dependency |

Once Phase 3 completes, US2 and US3 can be developed by different people with no coordination.
US1 does not parallelize well internally: T083 through T092 are seven pipeline stages in one
process, each fail-closed and each requiring the previous stage's allow.

---

## Implementation strategy

### MVP — Phase 1, Phase 2, Phase 3, Phase 4

Setup, both foundational phases, then User Story 1. Stop and validate: a verified answer on the
reference application, unattended, with every adversarial arm of **SC-002**, **SC-003**, **SC-022**,
**SC-023** and **SC-024** denied and recorded. That is the product's floor — without it there is
nothing to verify and nothing to detect drift against.

**Two things must not be deferred out of the MVP even though they look deferrable.** T101's overhead
measurement, because **Q-09** was accepted *with* the measurement and committing the mechanism
without it is the thing that acceptance excluded. And T012's byte-identity determinism test, because
the capability it protects is in a later phase and the defect it prevents is introduced in this one.

### Incremental delivery

1. Phases 1–3 → the substrate and the runtime core exist.
2. Phase 4 → the MVP. Validate, then demonstrate.
3. Phase 5 → verification. This is the half nobody self-serves; the ceiling test established that a
   competent engineer with a shell and a specification can already reach their application.
4. Phase 6 → drift. Value on day thirty rather than day one, and the least evidenced of the three.
5. Phase 7 → the four-provider battery closes **SC-010** as a test.
6. Phase 8 → the instruments. Nothing external may describe any of the three capabilities as a
   differentiator until the corresponding report exists (FR-042, FR-043).
7. Phase 9 → polish.

### Before implementation starts — two of three are discharged, one remains

This list had three items. Two closed on 2026-08-03.

1. ~~**Answer U-31**~~ — **not required for v1's sizing, and the first pass was wrong to list it.**
   **Q-03** had already fixed v1's substrate as our own journal, with a durable-execution engine
   named as the v2 option. U-31 stays open as a standing question about whether to adopt one *ever*;
   it does not gate this estimate and never did.
2. ~~**Run the four-arm provider spike**~~ — **run.**
   [Finding 016](../001-discovery-validation/findings/016-provider-sdk-roundtrip.md) sized row 5 and
   supplied direct evidence for SC-010's provider-capability half. It also changed how T061 must be
   written, which is a better outcome than the estimate it was run for.
3. **Run T050's concurrent-writer probe early**, ahead of its phase. **This one is still owed, and
   it is now the only cheap thing standing between this document and a fully banded runtime-core
   figure** — it is what collapses row 4's +0 to +4. It is the substrate question finding 006
   explicitly did not answer, and both the session store and resume sit on the answer.

---

## Notes

- `[P]` means a different file and no dependency on an incomplete task.
- Every task names a file path, because a task an implementer has to interpret is a decision taken
  without a record.
- Fixtures are committed **with** the capability, never assembled when the measurement falls due
  (FR-053). A freeze that pins artifacts and not the inputs they answered is not a freeze, which
  this corpus learned from a trace corpus that silently re-joined to whatever the task file said that
  day (**U-47**).
- Nothing in this list re-admits **OD-09**'s deferred scope. There is no tool synthesis, no promotion
  selection, no static per-tool effect label, no knowledge-graph memory tier, no iframe and no
  multi-agent path. The `codegraph` index is an analysis-time input; the served-operation set is data
  the enforcement point resolves against. The obligation stays per call while the differentiator
  defers.
- **v1 is read-only against the target for its whole life** (**OD-10**). T181 is the gate on that
  changing, and no task here ships a write path.
