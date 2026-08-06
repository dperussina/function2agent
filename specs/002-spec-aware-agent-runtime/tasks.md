# Tasks: Spec-Aware Agent Runtime

**Feature**: `002-spec-aware-agent-runtime` | **Date**: 2026-08-03 | **Phase**: 2 (`/speckit-tasks`)

**Input**: Design documents from `specs/002-spec-aware-agent-runtime/` —
[`spec.md`](./spec.md) (~~55~~ **58** functional requirements, 30 success criteria, five user
stories), [`plan.md`](./plan.md) (Constitution Check, deviation records, Complexity Tracking),
[`research.md`](./research.md) (T-01..T-14, the three mechanisms, Q-01..Q-11 all resolved),
[`data-model.md`](./data-model.md), [`contracts/`](./contracts/), [`quickstart.md`](./quickstart.md)

> **Requirement count recounted 2026-08-04 against `spec.md`, and it was stale by three.** The
> struck figure predates FR-056 through FR-058, the last of which was added on 2026-08-04. **The
> success-criteria figure is deliberately not struck** — it was already correct, and striking a
> figure that was right would record a correction that never happened. `plan.md`'s header carried
> the same drift, by three and by two, and was corrected the same day. Both counts are now under
> `definition-count` in [`tools/check_corpus.py`](../../tools/check_corpus.py), which compares a
> prose count against the definitions in the document it describes, so neither can go stale again
> without the gate saying so.

**Constitution**: v1.2.0 ([`constitution.md`](../../.specify/memory/constitution.md)) ·
**Inherited decisions**: **OD-01** onward, in
[feature 001's plan](../001-discovery-validation/plan.md)

**Total tasks**: ~~204~~ ~~205~~ **206**, in nine phases *(T205 added 2026-08-03 — the kernel boot
matrix that would turn the derived 5.14 floor into a tested one, and **deferred by owner decision the
same day**; it is counted here because it is recorded work, not because it is scheduled. **T206 added
2026-08-04** — the preflight's real-`unshare` pair, ~~which is neither deferred nor done~~ **done the same day**)* · **Estimate**: derived for
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
- [X] T206 [P] Extend the preflight's `namespaces` check to **attempt a real `unshare(CLONE_NEWUSER)` in a forked child, and an `unshare(0)` no-op beside it**, reporting which layer refused and what the operator can do about it, in `src/supervisor/preflight.py` (FR-048, **OD-17**, FR-053)
  - **Done 2026-08-04.** `_attempt_unshare` forks and calls `unshare(2)` in the child, so the supervisor is never moved into a namespace by the act of checking; `_classify_unshare_pair` is a pure function over the two attempts, which is what lets all four cells of the table be exercised on a host that can run none of them. `Check` gained a `layer` field, because four layers can refuse here and they have four different remedies. **The presence and sysctl reads are kept and now gate rather than decide**: a kernel with no `/proc/self/ns/user` and a `max_user_namespaces` of 0 are each located before the pair is attempted, since neither can be a runtime-profile refusal and reporting that layer for them would be wrong. Two removal proofs, one per arm — the second removes only the no-op and leaves the mechanism running, which is the harder failure to see because it corrupts the attribution rather than the verdict
  - ⚠️ ~~**The mechanism is untested against a real refusal.**~~ ~~The classification is **derived from [finding 024](./findings/024-deployment-surface-permission-census.md)'s measured table, not re-measured here**~~ — **superseded 2026-08-04 by [finding 025](./findings/025-preflight-unshare-pair-measured.md) for two of the five pair cells, and for those two only.** This check was run unchanged under Docker's unmodified default profile at uid 1000 with `--cap-drop=ALL`, saw a real `EPERM` on both arms, classified it `runtime-seccomp-profile` and emitted the full remedy; a custom profile flipped the same two arms to permitted and the same check to `available`. Three arms produce the refusing cell and five the permitting one, and NC-1 — the fetched profile run unmodified beside the daemon's builtin — makes that a one-variable delta. **The pre-T206 check was run in the same two containers and returns `ok=True` with a byte-identical detail string in both**, so the misreport T206 replaced is measured and not merely described. **What survives unstruck**: every cell in `tests/unit/test_namespace_probe.py` is still constructed by injecting the attempt function, and the suite scores **14 passed in both containers** — it did not break on a real host and it cannot distinguish one, so it is not the artifact that closes this. The one test that touches the kernel asserts only that the probe does not move the process that ran it, and it skips off Linux — though it **ran and passed** in both containers, and the probe left uid and all four namespace links unchanged in all eight arms
  - ⚠️ **The `kernel-sysctl-or-lsm` branch is still derived, and it is the branch that fires on the likeliest self-hosted host.** Unchanged by [finding 025](./findings/025-preflight-unshare-pair-measured.md), which re-verified the reason on its own host rather than inheriting it: no `/sys/kernel/security/lsm`, no AppArmor, no SELinux, and `docker info` reporting `seccomp` and `cgroupns` only. Two routes to constructing the sysctl cell were tried and both were refused — `--sysctl user.max_user_namespaces=0` is not in the runtime's allowlist, and a bind mount over the procfs path is refused by `runc`'s proc-safety check — which upgrades finding 024's *inferred* cause to two *observed* ones without producing the cell. The `DERIVED, NOT MEASURED` string in that branch's message is still accurate and must stay. **Cheap route identified, not taken**: CI already runs this preflight as root on a bare `ubuntu-latest` runner, where both arms pass; an additional non-gating **unprivileged** run on that same runner would plausibly produce the cell, since Ubuntu 24.04 ships `kernel.apparmor_restrict_unprivileged_userns` enabled and root is exempt from it. Derived from the distribution default, not observed. **Route taken 2026-08-04 as T208**; the branch stays `DERIVED, NOT MEASURED` until a CI run publishes a reading, and it stays derived if the reading contradicts the prediction
  - ⚠️ **The gap [finding 025](./findings/025-preflight-unshare-pair-measured.md) found is in the check *set*, not in this check.** Under `--cap-add=SYS_ADMIN` both arms are permitted, so the check reports `available` and emits no remedy — correct about `unshare`, which genuinely works there, and the `DO NOT USE --cap-add=SYS_ADMIN … IT DOES NOT WORK` warning is on the arms an operator reads *before* making the change, which is the only place a preventive warning helps. But `pivot_root` is **still refused by seccomp in that arm** — measured with a control that moves, `EPERM` holding the capability under the default profile against `EBUSY` under the custom one — and **`run_checks()` contains no `pivot_root` check at all**. So an operator who applies the bundle's cgroup half and then reaches for the capability instead of the profile gets a green preflight on a host where the mount sequence fails at the containment step. Whether that becomes a new check, a note on T160 or a documented non-goal is a scoping decision and is **not taken here**. **Taken 2026-08-04 as T207: a new check**, measured in [finding 026](./findings/026-pivot-root-check-measured.md), which re-ran this same arm against the check set and found the `pivot_root` refusal reported where nothing was reported before
  - **Added 2026-08-04 by [finding 024](./findings/024-deployment-surface-permission-census.md); the existing check does not cover this and is not a duplicate of it.** `_check_namespaces` reads `/proc/self/ns/` and `max_user_namespaces` — kernel-build presence and the sysctl. Both can say yes on a host where the mechanism is refused, because the refusal is in the container runtime's seccomp profile and neither of those is a syscall attempt. [Finding 023](./findings/023-user-namespace-privilege-model.md) already asked for the real `unshare`; **what finding 024 adds is the second arm, and the second arm is what makes the diagnostic actionable**
  - **Why the no-op arm is the whole diagnostic, and it costs one syscall.** Docker's default profile carries its rule on the **`unshare` syscall**, not on `CLONE_NEWUSER`, so `unshare(0)` — which creates no namespace, and which no kernel namespace check can refuse — returns `EPERM` under the profile and succeeds without it. So: both refused means *the runtime's profile is blocking this, and here is the profile the bundle ships* (T160); the no-op passing and `CLONE_NEWUSER` failing means *your distribution's LSM or sysctl is blocking this*, which the bundle cannot fix and which needs the host changed. Only the first has a remedy we supply, and a preflight that reports one message for both sends operators after the wrong fix
  - **The remedy text carries the `--cap-add=SYS_ADMIN` warning**, because it is the change an operator reaches for first — the profile's rule is written as a capability gate, so the error invites it — it is the most dangerous change available, and **it does not work**: `pivot_root` is in no rule of the profile at all, so it returns `EPERM` even with the capability held, after the whole mount tree has built correctly. That failure reads as a broken mechanism rather than as a wrong grant unless the preflight says otherwise
  - ⚠️ **The LSM branch is derived, not measured.** The host every arm of finding 024 ran on carries no AppArmor and no SELinux, so an LSM refusal was **unconstructible** there — and ~~the LSM is what refuses on Ubuntu 24.04~~. This branch's message must not read as though the path it describes was observed, and the check must report what it found rather than assert which layer it was, on the same rule the rest of this preflight follows
    - ⚠️ **Corrected 2026-08-05, and the correction is stronger than "still unmeasured": this branch does not fire on Ubuntu 24.04 at all.** [Finding 023](./findings/023-user-namespace-privilege-model.md)'s extension measured the runner directly. Ubuntu **permits** the `unshare` and **confines the result** — the process enters labelled `unconfined` and comes out labelled `unprivileged_userns (enforce)` — and the refusal lands downstream on `setgroups` (`EACCES`) and the `uid_map` write (`EPERM`). So *both* arms of the pair are permitted there, and the arm that reports `kernel-sysctl-or-lsm` cannot be reached. The branch still has a host to describe — a kernel with the sysctl disabled, or an LSM policy that denies `unshare` outright — but Ubuntu 24.04 is **not** that host, and its message must not imply otherwise. Its status moves from *unmeasured* to *measured not to fire on the host it was written for*, which is a different claim and a more useful one
    - **The obligation that follows, and it is owed rather than broken.** Nothing in `run_checks()` probes the `uid_map` write. That is **correct today**: `mounts.py` unshares `CLONE_NEWNS` only, so no map is ever written and the check set matches the mechanism that exists. But finding 023 establishes the map as the **decisive limb** of the privilege model **OD-24** defers — not the cgroup — so when that model is built the preflight needs an arm for it. Without one the check set goes green on the likeliest self-hosted OS over a mechanism that fails at the map, which is the *check-set* gap [finding 025](./findings/025-preflight-unshare-pair-measured.md) found for `pivot_root`, one step later in time. Recorded here so the build cannot land without it; **no check is added now**, because a probe for a namespace the supervisor does not enter would assert a capability nothing uses
    - ⚠️ **Narrowed 2026-08-05 — two conditions on that owed arm, from [finding 028](./findings/028-od24-deferral-re-examination.md).** First, **a boolean is not sufficient**: the map write returns three distinguishable outcomes over three bounding sets — `EACCES` at `CapBnd 0`, `EPERM` with Docker's default 14 (which carry `CAP_SETUID` but not `CAP_SYS_ADMIN`), and `ok` with `CAP_SYS_ADMIN` added — so the arm must report **which** capability is absent or its remedy cannot name the fix. Second, **any remedy naming `newuidmap` must name `CAP_SYS_ADMIN` in the same breath.** Finding 028 measured the helper for the first time and it needs `CAP_SYS_ADMIN` in the bounding set, where writing the map directly needs only `CAP_SETUID`+`CAP_SETGID` — so the helper is the **highest**-authority of **OD-24**'s three routes, not the lowest. A remedy that names it alone prescribes a configuration that does not work, which is T206's existing `--cap-add=SYS_ADMIN` warning arriving from the opposite direction: there a grant too large still fails, here a grant that looks smaller is larger
- [X] T207 [P] Add a **`pivot_root` check** to `run_checks()`, closing the check-*set* gap [finding 025](./findings/025-preflight-unshare-pair-measured.md) found and T206 explicitly did not scope, in `src/supervisor/preflight.py` (FR-048, **OD-17**, FR-053)
  - **Done 2026-08-04**, measured in [finding 026](./findings/026-pivot-root-check-measured.md). `_attempt_pivot_root` forks and calls `pivot_root("/", "/")` in the child, so a *successful* pivot moves a process that is about to exit rather than the supervisor; `_classify_pivot_root` is a pure function over the attempt and the capability posture, which is what lets every cell be exercised on a host that can run none of them. Same `layer` vocabulary as `_check_namespaces`, and the `--cap-add=SYS_ADMIN` warning is carried on the arm that holds the capability
  - **The classification is three-way, and the third way is the trap.** `EBUSY` means `pivot_root` **reached the kernel** and failed on its preconditions — no valid new root, not a mount point — which is the permitted answer the check wants. A check that scores `EBUSY` as a refusal **inverts the verdict on a working host**, and that inversion is a removal proof rather than a comment
  - **`EPERM` is ambiguous and the check refuses to guess.** It is emitted both by the seccomp filter and by the kernel's `CAP_SYS_ADMIN` gate. `_read_cap_sys_admin` reads `CapEff` from `/proc/self/status` — read, not inferred from the uid, which is finding 024's overflow-uid bug — and only an `EPERM` **while holding the capability** is attributed to the profile. Without it the layer is `refused-unattributed` and the remedy asks for one more run rather than naming a layer the evidence does not support
  - ⚠️ **One cell is DERIVED: outright success.** `rc == 0` was never observed in any arm, because every arm that was permitted returned `EBUSY` on preconditions — which is the *correct* behaviour for `pivot_root("/", "/")` and therefore not a gap that more arms of this shape would close. The permitted verdict itself is measured twice over; only the `rc == 0` path into it is derived. `ENOSYS` and the non-Linux and unknown-architecture guards are derived too and say so in their strings
  - **Scope note.** T206 left "whether that becomes a new check, a note on T160 or a documented non-goal" as an untaken scoping decision. This takes it as a new check. It is **not** folded into `_check_namespaces`: under `--cap-add=SYS_ADMIN` `unshare` genuinely works, so making the namespaces check report a refusal there would be a false statement about the syscall it measures. A counterfactual that folds them was built and run, and it reddens the namespaces check on a host where `unshare` works
- [X] T208 [P] Non-gating CI observation of the `unshare` pair **unprivileged**, the one route to the `kernel-sysctl-or-lsm` cell that costs no hardware, in `tools/unshare_pair_observation.py` and `.github/workflows/ci.yml` (FR-048, FR-053)
  - **Done 2026-08-04.** T206 identified this route and did not take it. The step runs our committed checks twice on the same runner — unprivileged, then under `sudo` — and publishes both to the run page and an artifact. **The privileged arm is the negative control**: the positive result here is a *refusal*, which a broken import or a failed fork also produces, so the paired arm differing only in privilege is what licenses reading it
  - **Non-gating by design, not by convenience.** What it measures is a property of a GitHub-hosted runner image; a runner-image change flipping that sysctl would break every build while saying nothing about the merge. `continue-on-error` carries that, and the renderer's non-zero exit on a missing record plus a `::warning::` carries the other half — absence must not be silent, because the file is missing in exactly the case where the measurement did not happen. That is the failure mode that lost the native seccomp-overhead figure
  - ⚠️ **The expectation is DERIVED and the step accepts its own refutation.** `PREDICTED_LAYER = "kernel-sysctl-or-lsm"` is written down before the run, from Ubuntu 24.04's documented default and from no observation of this runner. A contradicting reading renders as the result with `Do not tune this step` beside it, and a test asserts that path, because a step that reports cleanly only when the prediction holds measures nothing
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
  - **PARTIAL — the interface landed and holds; the line's *third* clause does not hold tree-wide, and the one file exempt from it is owned by no task. Recorded 2026-08-06; nothing here is re-sized.** `Repository` is built, is in WAL mode, prefixes `tenant_id` and `deployment_id` onto every table it creates, and since `ff202ae` converges the journal mode rather than racing it. What is not delivered is *no engine-specific SQL above the connection layer*. That clause cannot be read as scoped to `src/contracts/repository.py`, because that file **is** the connection layer and the clause would then be vacuous — it is necessarily a claim about the rest of the tree. The check for it is `test_no_engine_specific_sql_lives_above_the_repository`, and it passes only because `src/supervisor/session_table.py` sits on its `permitted` list. **Measured by deleting that one entry and running the scan: it fails on ten lines** — `PRAGMA journal_mode=WAL`, the `CREATE TABLE`, one `INSERT`, four `UPDATE`s and two `SELECT`s. The property the clause asserts is false of the tree, and the exemption is what makes the checkbox green.
  - **The tick stays `[X]` and the note carries the qualification, on T058's precedent** — a clean checkbox over an unexercised half is the rot; a PARTIAL tick naming *which* half is exercised is not. The distinction that might have rescued a clean tick, that this is a **caller's** debt rather than an incompleteness in the interface, does not survive two facts. `session_table.py` is not a caller of `Repository`; it is a peer that bypasses it, so its debt is to *become* one. And **no task in this file owns that migration** — `session_table`, `SessionTable` and the migration itself appear nowhere in this document — so under the caller's-debt reading the debt is owned by nothing at all. T016's third clause is the only text in any plan artifact that asserts the property the exemption suspends, which makes it the strongest available anchor.
  - **The exemption is a deferral, not a carve-out on the merits**, and its own failure message says so: *"it is a known migration, recorded here rather than hidden by widening the scan."* [Finding 033](./findings/033-session-table-wal-race-unreachable-and-owed-to-migration.md) records what the migration has to reconcile and why it is not mechanical — `resolve()` deliberately carries **no** tenant predicate, because the proxy resolves an opaque handle before it knows whose it is, while `Repository` scopes every read; `session` is not in T017's ownership map; and the schema is a committed cross-language conformance vector the Go proxy reads by column name, so changing it is a two-language change plus a regenerated fixture. **No task is minted here and no figure is touched**, on the [T029 startup seam](#configuration-and-failing-closed)'s precedent: the pass that measures a gap is the wrong pass to price closing it, and a task number minted here would carry an estimate nobody derived.
  - **The condition under which this stops being only a hygiene debt, recorded so it travels with whatever makes it reachable.** Finding 033 measured the WAL first-open race reaching `SessionTable` through `executescript` unchanged, and found it unreachable — but **by current usage with nothing enforcing it**, not by construction. Only the proxy is safe by construction (`mode=ro` plus `query_only`, doubly enforced in Go, and a read-only open of a nonexistent file fails outright). Every other constructor is safe only because it happens to create the file before a second party attaches, and no rule, test or assertion anywhere says it must. **The race is live again the moment two processes first-open a cold session store at once** — the supervisor deployment `SessionTable`'s own class docstring already anticipates. **No task in this file creates that process.** That is the same absence recorded at [the configuration section](#configuration-and-failing-closed): there is no `def main`, no `[project.scripts]` and no `console_scripts` anywhere in Python `src/`, and `src/proxy/main.go` — the one real entry point — is the read-only side that cannot be a party to this race. T159 is where a supervisor process first becomes concrete and carries the pointer.
  - **⚠️ DECIDED 2026-08-06 by [OD-28](../001-discovery-validation/plan.md#od-28--the-sessiontable--repository-migration-stays-deferred-and-the-shape-is-routed-to-t016s-note-rather-than-re-litigated-the-deferral-expires-the-moment-a-supervisor-process-constructs-a-session-store) — the deferral is a *ruling*, not an oversight, and this note is where the shape is routed rather than re-litigated.** The three bullets above record a debt that three separate passes have now re-derived from three directions — the WAL first-open race, the engine-exception leak, and [T108](#the-execution-environment--fr-048-fr-049-and-fr-050s-mechanisms)'s lease renewer, whose own list of live options ends at *complete T016's migration* and names it the one the other three are working around. **The owner has ruled that the migration stays deferred**, on two grounds kept deliberately distinct: **①** nothing it fixes is reachable — re-verified at `7e874d7`, **nothing in `src/` constructs a `SessionTable` at all**, every construction in the tree being a test or a tool that creates the file sequentially first; and **②** Phase 3 is the critical path and the migration is not mechanical, for the three reasons the bullet above already gives. **A future instance of this shape is recorded here and routed to OD-28. It is not re-litigated, and it mints no task** — which is the standing instruction this note now carries, and the reason a fourth pass arriving at the same seam should stop at this bullet.
  - **The expiry condition, and it is the half most likely to be missed.** Ground ① is satisfied by the tree staying as it is, so it is the kind of ground that can stop applying without anyone noticing — the defect **OD-24**'s re-examination found, where one of two grounds had been discharged by being satisfied and the register said nothing for a day. **Ground ① retires the moment a supervisor process constructs a `SessionTable` against a store that may be cold**, and at that instant the race is live and nothing in this tree will report it. The artifact that does it is **a supervisor entry point that opens the session store** — named here because **T159 delivers a supervisor *image* without naming what runs inside it**, so the pointer alone does not cross the gap. It may arrive under T159, under T160's compose bundle, or under a task that does not exist yet; whichever it is, **that change is the trigger to re-read OD-28**, and the check is the one stated above — the store is created once before any second process attaches, *or* the migration is done. **Ground ② retires when Phase 3 closes.** Neither retirement is a measurement, and no further probing will move the deferral. **Nothing is re-sized here and no task is minted**, which OD-28 states in its own terms.
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

> **T029's line says "environment injection at process start", and the Python runtime has no process
> start. Measured and recorded 2026-08-06; nothing here is re-sized.** The schema landed, the
> fail-loud path landed, the reporting landed, and the four tasks above are correctly marked done —
> what is absent is the caller. `config.load()`, `SUPERVISOR_KEYS` and `RUNTIME_KEYS` are referenced
> **only from tests**. `Config` is constructed at exactly one site in all of `src/`
> (`config.py:315`, inside `load()` itself), and exactly one module in `src/` imports the module at
> all — `src/runtime/session_store.py:44`, which imports the `Config` *type* to annotate
> `Ceilings.from_config` and never calls `load()`. The only `__main__` blocks in Python `src/` are
> two operator utilities, both marked `# pragma: no cover`, neither of which reads configuration;
> there is no `[project.scripts]`, no `console_scripts` and no `entry_points` anywhere in the
> packaging.
>
> **What is unreachable is larger than one key, which is why this is recorded against the section
> rather than against a task.** Twelve key declarations carry a `no_default_reason` under **four**
> separate authorities, each specifying the same treatment — required configuration, no default,
> startup fails loudly: `_NO_DEFAULT_BOUND` (FR-049, **Q-10**, four sandbox bounds),
> `_NO_DEFAULT_CEILING` (FR-005, the four ceilings), `_NO_DEFAULT_RESULT_BOUND` (FR-058, three
> keys) and `_NO_DEFAULT_OPERATOR_PRICES` ([**OD-27**](../001-discovery-validation/plan.md), one).
> `_report()` already assembles *"N required value(s) unset:"* and quotes each key's reason back to
> the operator — the comment at `config.py:63` says "quoted back to the operator at startup" — and
> that mechanism has never run outside a test, for any of the four. OD-27's preflight
> `require_priceable` is the same shape one layer out: `costs.py:1062` calls it "OD-27's startup
> gate", and it has no caller in `src/` either. **The pricing seam is not a pricing problem.** It is
> this one, observed through the newest of the four authorities.
>
> **The pattern is built and proven — on the other side of the language boundary.** The enforcement
> point is a real process: `src/proxy/main.go:359` calls `LoadConfig(os.Getenv)` and refuses with
> `startup refused: %v` before it binds anything. So the Go component does exactly what
> `contracts/configuration.md` describes and the Python components have no assembly point at which
> to do it. A census run with Python-shaped patterns misses this, and reads the tree as having no
> entry point at all rather than one.
>
> **No task in this file creates that assembly point, and the absence is the record.** T159's four
> images and T160's compose bundle imply a process per component without naming what each runs;
> **T171** — *exercise the fail-loud startup path end to end through the shipped bundle* —
> presupposes the path rather than building it, and is where the gap will be discovered if it is not
> closed first. **This note deliberately does not size the work or add a task line**, on the same
> ground as the FR-058 seam above: the pass that measured a gap is the wrong pass to price closing
> it, and a task number minted here would carry an estimate nobody derived. What a defensible
> closure would name, stated so the omission is checkable: which components are processes, what each
> one loads (`SUPERVISOR_KEYS`, `RUNTIME_KEYS`, or both), and where `require_priceable` runs relative
> to `load()` — none of which this document currently answers.
>
> ---
>
> **The same seam seen from the output side, measured 2026-08-06: `_report()` assembles the operator
> report and emits none of it — and an entry point alone is the whole fix.** Python `src/` contains
> no `logging`, no `getLogger` and no `warnings.warn`, which is true and was confirmed by two
> independent methods (an AST walk over all 60 files and a regex sweep: **zero** matches each). **The
> conclusion usually drawn from it is wrong, and it is wrong in this repository's recorded direction
> — a claim about behaviour resting on a search of files.** `load()` with an empty environment
> assembles a **3169-character** report and writes **0 bytes** to stdout and stderr, measured with
> fd-level capture: it *raises*. Put the identical call under a bare `if __name__ == "__main__"` with
> no `try`, no logging and nothing else added, and the interpreter's default excepthook delivers
> **3575 bytes to stderr and exit 1** — the report's own *"12 required value(s) unset"* line, and all
> eight of `SUPERVISOR_KEYS`' `no_default_reason` strings quoted verbatim. **So the fail-loud
> configuration path is not waiting on a logging facility. It is waiting on the assembly point
> recorded above, and nothing else.**
>
> **The Go side is not the counter-example it looks like, and reading it as one inverts the
> conclusion.** Its human channel is **one file**: `main.go` is the only non-test file that imports
> stdlib `log`, `log.New(os.Stderr, "f2a-proxy: ", …)` is the **first statement of `main()`**
> (`main.go:360`), and the five emit sites are three `Fatalf`, one `Printf` and the `*log.Logger`
> **parameter** at `main.go:328` that becomes `http.Server.ErrorLog`. There is **no package-level
> logger anywhere in Go.** A count that reads `decisionlog.go`, `pipeline.go`, `effect.go` and
> `capability.go` as logging is counting the *decision log* and the word "log" in prose:
> `decisionlog.go` never imports stdlib `log` at all — it is a SQLite database, and
> `pipeline.go`'s hits are `p.log.Write`. **So in the one component that ships with an entry point,
> the human channel is constituted by that entry point and injected downward.** That is why this is
> recorded here as this seam's output half rather than as a second missing capability: the precedent
> does not have a logger that a Python component is missing, it has a `main()` that a Python
> component is missing, and the logger follows from it.
>
> **The machine-readable half is built, and conflating the two overstates the gap.** `SpanWriter`
> persists to a `Repository` table against FR-038's seven closed kinds (`trace.py:389`), which is the
> structural twin of Go's `DecisionLog` — the same choice on both sides of the boundary, for
> non-`main` code, to write a structured record rather than address a human. **What is absent in
> Python is the entry-point-scoped human channel and only that.** Two shapes do reach a human today
> and both were verified by running, so the absence must not be stated more broadly than it is:
> `python3 -m src.supervisor.preflight` emits **366 bytes to stderr and exits 1** on this platform
> (T206's *"what the operator can do about it"* genuinely arrives), and an uncaught exception on a
> **daemon** thread reaches stderr through `threading.excepthook` — **490 bytes** of traceback,
> planted and observed. Neither is available to library code: the two `print` sites in `src/`
> (`preflight.py:1510`, `codegraph_pin.py:118`) are both inside `__main__` blocks marked
> `# pragma: no cover`.
>
> **Three sites assemble an operator message; one of the three cannot be emitted by any of it**, and
> that one is the reason this note is not purely bookkeeping. `config.py:_report()` and
> `preflight.py:preflight()` both hand their text to an exception, which the excepthook delivers once
> there is a process to raise in. `LeaseRenewer.stopped_because` (`lease.py:74`) is neither raised nor
> printed — it is an attribute, and **nothing in `src/` reads it**; the only reader anywhere is
> `tests/integration/test_lease_revocation.py`. ~~An entry point does not fix that one, which is
> recorded against **T108** under *the execution environment*, where the renewer's defect already
> sits.~~ **Corrected 2026-08-06: the third site is no longer the odd one out.** The attribute itself
> is still neither raised nor printed, but `_loop` now **re-raises** the exception it records, so the
> condition reaches stderr through `threading.excepthook` exactly as the other two reach it through
> the default one — **881 bytes**, measured. It is taken as an **interim** and not as the design, and
> the entry point is still what the durable answer waits on; the ruling, the three routes it does not
> take and the finalization window in which even the traceback is lost are all recorded against
> **T108** under *the execution environment*. **Nothing here is re-sized and no task is added**, on
> this section's own ground above.

### Tracing, from the first shipped capability

- [X] T036 Span writer for the seven span kinds — `model_call`, `tool_call`, `egress_decision`, `filesystem_decision`, `state_transition`, `verification`, `drift_check` — carrying inputs, outputs, timing, cost, and the artifact versions in force, in `src/runtime/trace.py` (FR-030, FR-031, Principle VI)
  - **This is the machine-readable output channel, it is built, and it is closed — so it is not the place a component reports an operator-facing condition.** Verified 2026-08-06 by attempting it: `lease_renewal`, `supervisor_error` and `operator_message` are each refused by `SpanError`, `model_call` is accepted, and `state_transition` refuses without a `StateTransition` carrying a deciding rule. Reaching the check at all requires a tenant, a deployment id and a **content-addressed** artifact version, which is the point — a span is built for reproducible attribution, not for a message to a human. A reader arriving here to record a supervisor-thread failure should read **T108**'s correction and [the configuration section](#configuration-and-failing-closed) first: the channel that is missing is the human-facing one, and it is missing because the entry point that would construct it is.
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

- [X] T041 Turn loop: turn dispatch, the model-response-to-tool-call step, and `TurnRecord` construction, in `src/runtime/loop.py` (FR-004, [`data-model.md`](./data-model.md) §2.2)
- [X] T042 Context assembler and truncation policy, in `src/runtime/context.py`
- [X] T043 Parallel tool-call dispatcher: execute concurrently, journal and record in the **provider's declared index order** and never in completion order, in `src/runtime/dispatch.py` (T-08, FR-007)
- [X] T044 Explicit per-key merge rules for shared state a concurrent step writes, with last-write-wins forbidden, in `src/runtime/state_merge.py` (T-08)
- [X] T045 [P] Invariant tests for declared-order recording and for a concurrent write that cannot be lost, in `tests/invariants/test_fanout_ordering.py`

> **FR-058 landed inside capability 1 on 2026-08-04 and is named in none of its task lines, and the
> seam is recorded here rather than absorbed. Added 2026-08-05.** FR-058 bounds every result either of
> FR-004's capabilities returns to the agent, and FR-004 is T041's requirement — so the work arrived
> inside this capability rather than beside it. What it brought: per-result bounding, the disclosure
> the agent sees in place of the elided body, the retention lifecycle for the full result, the derived
> ceiling and its unit rule, span-field validation on `tool_call`, and ten removal proofs. It shipped
> in `src/runtime/result_bound.py` with fields added to
> [`contracts/trace-record.md`](./contracts/trace-record.md), and `plan.md` **OD-25** authorises it.
>
> **None of T041 through T045 mentions it, and the estimate row for this capability does not either.**
> Row 1 of [the derived estimate](#the-re-derived-estimate-for-u-48s-nine-capabilities) is dated
> before FR-058 existed and its 8–11 days were derived over T041–T045 as those lines read — so the
> figure **does not include FR-058's work**, and reading it as this capability's cost now understates
> it by whatever FR-058 cost.
>
> **This note deliberately does not re-derive the figure, and the reason is the method's own.** A
> re-estimate taken mid-phase, by the pass that just built the thing being sized, is the shape that
> produces a motivated number — and the estimate section's premise is that each row states an anchor a
> reader can disagree with. **What a defensible figure would rest on, stated so that the omission is
> checkable rather than convenient**: the per-task increment FR-058's six items add, judged against the
> same anchors row 1 already cites, by someone who did not implement them; or, better, the elapsed
> cost of the FR-058 pass read off the commit range, which is a measurement rather than a judgment and
> which nothing in this document currently records. Neither exists. The figure is left as it stands,
> marked as excluding FR-058, rather than adjusted by this pass.
>
> **Why T043 through T045 exist in a v1 that emits no graph, since this was nearly lost.** Finding
> 006 measured fan-out producing **5 distinct orderings in 8 runs** under overlapping latencies, and
> a **silent lost update** where one of two parallel branches writing a shared key vanished with no
> error and no warning. Those were read as *graph* properties. They are not: every provider in
> **SC-010**'s set can emit several tool calls in one turn, so a single-agent loop fans out whether
> or not it has a graph. **The hazard is the providers'; the measurements were ADK's.** With ADK
> gone the mitigation is ours, and T-08 is now a design rule with a known-real hazard and **no
> measurement behind it** — which is why T045 is an invariant rather than a comment.

### Capability 2 — the runner

- [X] T046 Runner: session start and attach, loop invocation, cancellation, and the teardown handshake with the supervisor, in `src/runtime/runner.py`
- [X] T047 [P] Cancellation test asserting a cancelled consumer leaves no error on the stream and no partial state, in `tests/unit/test_cancellation.py` — cancellation is routine in an agent product, which is why finding 006 reported a teardown defect against the runtime it probed

> **T047's "on the stream" is discharged against the trace, not against a stream.** The event stream
> is capability 9 (T077–T079) and does not exist, so there is no stream for a cancelled consumer to
> leave an error on. What the arms assert instead is the same claim on the surface that does exist:
> no span carries a fault outcome, the interruption is recorded as a transition, and the journal's
> turn count agrees with the records returned. **When the stream lands, T077's arms owe the same two
> claims on it** — this is a substitution of surface, not a discharge of the obligation.

### Capability 3 — the session store

- [X] T048 Session store: create, load and persist `Session` with `session_id`, `state`, `terminal_state`, `lease_expires_at` and the four ceilings, in `src/runtime/session_store.py` (**OD-15** — ours, on no framework)
- [X] T049 Session state machine and named-terminal recording over [`data-model.md`](./data-model.md) §2.1's lifecycle, in `src/runtime/session_state.py` (FR-006)
- [X] T050 Concurrent-writer probe for **our own** store under the three processes, in `tests/integration/test_store_concurrent_writers.py` — finding 006 states it did not test this, and T-06's narrowing records that what it observed on SQLite was a session service v1 does not ship

### Capability 4 — checkpoint and resume · **12–17 days, band +0 to +4**

- [X] T051 Write-ahead intent journal keyed `(session_id, turn_index, step_index)` with an idempotency key per effectful step — intent committed before the effect, outcome committed after — in `src/runtime/journal.py` (T-07)
- [X] T052 Resume reconstruction at **turn-and-step granularity**, so a resumed session skips completed inner turns, in `src/runtime/resume.py` — finding 006 measured a loop hosted inside a checkpointed node re-executing **4 of 4** completed inner turns, which is what this granularity exists to avoid
- [X] T053 Reserve-then-reconcile budget ledger — reserved before the model call, reconciled after — so a crash **over**-counts rather than under-counts, in `src/runtime/ledger.py` (T-07, **U-30**)
- [X] T054 Induced-crash resume battery: `SIGKILL` from a separate process at a turn boundary and inside a step, asserting no completed inner turn re-executes and no recorded local effect repeats, in `tests/integration/test_resume_sigkill.py` (FR-007, SC-011)
- [X] T055 Repeated crash-and-resume ceiling battery — **at least three resumes**, on each of the four dimensions in turn, asserting the cumulative total after every resume is never lower than the total before the crash that preceded it, in `tests/batteries/test_ceilings_under_resume.py` (**SC-030** second clause; finding 006 measured a ceiling of 3 permitting **6** cycles because the counter lived on a context rebuilt per attempt, and the failure is invisible in review because every individual attempt is compliant)
- [X] T056 Extend the opaque-state conformance fixture across a **resume boundary**, in `tests/conformance/test_provider_state_resume.py` — finding 006's *What this does NOT establish* records provider-opaque reasoning state surviving a resume as untested, and with the journal and the envelope now both ours that boundary is inside one mechanism instead of across two

### Capability 5 — provider transport and tool-schema translation · **15–20 days**

- [X] T057 One internal tool-call representation plus per-provider translation in both directions across the differing function-calling wire formats, in `src/runtime/providers/schema.py` (FR-037)
- [X] T058 A thin driver per provider over that vendor's **own SDK**, behind one interface, in `src/runtime/providers/` (**OD-16** — no `litellm`, which declares no license; constitution Principle V's thin bottom tier)
  - **PARTIAL — the translation half is implemented and exercised; the transport half is not.** All four drivers implement one interface, carry a **per-model** capability branch (finding 016 result 9 measured `claude-sonnet-5` rejecting the request shape `claude-sonnet-4-5-20250929` accepts, so one function per *vendor* sends one of them an HTTP 400), and are driven end to end against cassettes. `ProviderDriver.call` raises `TransportUnavailableError` naming the missing package: no vendor SDK is in `requirements.lock`, and FR-021 requires a resolved, hash-pinned dependency rather than an import that works on the machine that added it. Adding the four SDKs and exercising `call` live is outstanding, and **T164's four-provider battery is where it is discharged** — not here.
- [X] T059 `provider_state` as opaque bytes on every turn record — captured verbatim from the raw response, re-injected verbatim, keyed by provider, never merged, never interpreted, never logged in a form readable as content — in `src/runtime/providers/state.py` (T-02, FR-037)
- [X] T060 Cassette recording and replay harness for provider fixtures, in `tests/conformance/cassettes/` (constitution Principle VII, which names cassette-backed provider tests by name)
- [X] T061 **Per-provider round-trip conformance fixture** over a long chained tool sequence on a reasoning model, asserting **byte identity of the opaque field** — and asserting it as a **conditional**, *whenever the field is present it survives byte-identical*, never as an unconditional presence check — in `tests/conformance/test_provider_state_roundtrip.py`. [Finding 016](../001-discovery-validation/findings/016-provider-sdk-roundtrip.md) measured both constraints: its negative control stripped the field and **chaining still succeeded with the correct answer**, so an output-checking fixture would pass an adapter that drops it; and `claude-sonnet-5` under adaptive thinking emitted opaque state on only **2 of 6** runs in the committed batch, so an unconditional presence assertion is flaky

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

- [X] T062 Per-provider token cost table as **versioned configuration** with a stated source per entry and no assumption of uniformity, in `src/runtime/providers/costs.py` — finding 003 showed per-provider cost cannot be assumed uniform, and this table was never on anyone's list because the removed dependency supplied it
- [X] T063 Fail closed when a model in use has no cost entry, in `src/runtime/providers/costs.py` — otherwise the spend ceiling silently becomes unenforceable for exactly the model nobody priced

> **Landed 2026-08-05, and what is *absent* from the table is the load-bearing part.** Nine models are priced across Anthropic, xAI and Google, each entry carrying two addresses — one for the rate, one for the API identifier, because vendors publish prices against display names and accept requests against ids, and that mapping is the claim most likely to be filled in from memory while the number beside it is dutifully cited — plus the date the pages were read and the tier the figure is scoped to. **OpenAI is priced at nothing, on purpose.** Neither model `wire_openai` branches on appears as a priced row on that vendor's page, and for the models it does price it gives a *"Short context"* and a *"Long context"* column and states no threshold between them: an entry carrying one column would under-charge every long request and an entry carrying both would have to invent the boundary. Under-charging is the direction that makes a spend ceiling fail to fire, so neither was available and T063 refuses the provider. The reason is recorded in `costs.UNPRICED` rather than left as a gap, because a gap reads as an oversight and the next reader fills it. Anthropic's documented **aliases** are absent for a different reason, also recorded there: that vendor's own page says an alias is a pointer that resolves to a dated id, so a price attached to one would be a price for whatever it resolves to next.
>
> **The table is wired to nothing yet, and that is not this task's to fix.** `costs.price_usd` converts provider-reported token counts to USD, but no path in `src/` carries a driver's `ParsedTurn` into the loop's `ModelResponse` — that adapter does not exist, `ModelResponse` carries neither a model identifier nor the input/output token split, and no task in this file names it. So the spend ceiling is still compared against a figure that is zero on every path, for a reason that is now upstream of the price table rather than inside it.

- [X] T210 The `ParsedTurn` → `ModelResponse` pricing seam, in `src/runtime/providers/adapter.py` — the paragraph above names a gap no task owned, and until it closed T062 and T063 were a table nothing could reach

> **Landed 2026-08-05. The task exists because the gap above was real and unowned; what follows is the part that is a decision rather than a wiring diagram.**
>
> **`spend_usd` is now `float | None`, and `None` is not a synonym for zero.** The defect was never that the arithmetic was wrong — it was that `ModelResponse.spend_usd` defaulted to `0.0`, so *"nobody priced this turn"* and *"this turn cost nothing"* were the same value, and FR-005's spend ceiling was compared against the first while reading it as the second. A nullable field distinguishes them and `require_spend_usd()` refuses the null at the point a spend reaches a total. There is deliberately no `spend_usd_or_zero`: the coercion is the whole defect, and a helper offering it would be taken up by the first caller that found the refusal inconvenient.
>
> **The model identifier comes from the caller, not from the response.** A rate is keyed on `(provider, model, date)` and the conformance cassettes show the model as request metadata rather than in the response body, so the adapter takes the same identifier the request was built with and refuses a turn that cannot say which model produced it. Deriving it from the payload would have been a guess on exactly the field the price hangs off.
>
> **A caller census, not a default.** Every `ModelResponse` construction site in the tree was classified: the drivers now go through the adapter; test fakes that genuinely cost nothing state `spend_usd=0.0` rather than inheriting it, each with the reason written at the site; and the journal path is handled by the schema gate below. A structural test walks `src/` with `ast` and fails if any module other than `adapter.py` and `resume.py` constructs a `ModelResponse`, because a second construction site is how the `0.0` default would return under another name.
>
> **The resume migration is a version gate rather than a refusal.** A session journalled before this landed carries `spend_usd: 0.0` — the old default, written by every response nobody priced. Believing it would resume a session with an invented total; refusing the resume would discard turns that actually happened, which is the direction `ledger.py` argues against. So model outcomes now carry a `schema` key, revision-1 payloads are reconstructed with their spend explicitly `None`, and `ResumePlan.unpriced_turns` names the affected turns so a caller reads the hole rather than inferring it from a figure that looks like money. A payload from a *later* revision is refused outright — finding 016's rebuild-from-what-the-adapter-recognised defect, arriving through the journal instead of the wire.
>
> **The ceiling now fires, and that is asserted as a total and not as a terminal state.** `test_the_spend_ceiling_fires_on_a_turn_priced_from_the_cost_table` runs two turns of a million tokens each at `claude-sonnet-5`'s published introductory rates, reaches `$24.00` against a `$20.00` ceiling and terminates. The total is the load-bearing assertion: a terminal state can be reached by an outstanding reservation, and the reservation is `$0.001` a turn, so only the table produces that figure. This is finding 029's shape closed on the spend dimension — *the comparison, the wiring and the terminal state all worked; the numerator was missing.*
>
> ~~**Operator-supplied prices are not admitted by T062's design and were not added.** The question was asked because OpenAI is deliberately unpriced and an operator with their own contract rates is the obvious next request. `costs.py` is a hardcoded Python mapping with a stated source per entry; "versioned configuration" in T062's line describes the dated-source discipline, not a load path, and FR-054 names no operator channel. Adding one would also reopen what T063 closed: an operator figure is uncited by construction, and under-charging is the direction that makes a spend ceiling fail to fire. Recorded here as a determination, not built.~~
>
> **Struck 2026-08-06 by [OD-27](../001-discovery-validation/plan.md), and struck rather than deleted because every sentence in it was true of the design as it stood.** What overtook it is this task itself: with the table wired, an OpenAI session fails closed on spend and cannot run, so the closure the paragraph describes stopped being free the day T210 landed. The owner admitted the path. **Two of the paragraph's claims survive the decision and are load-bearing in it** — an operator figure *is* uncited by construction, which is why `OperatorPrice` is a separate type carrying `declared_by`/`declaration_ref` instead of a `source` field, and why the provenance is written onto `ModelResponse`, the `model_call` span and the journal at schema revision 3; and under-charging *is* the direction that makes a ceiling fail to fire, which is why a single rate is refused for a provider pricing in two context columns with no published boundary. **What is no longer true is the conclusion.** The paragraph is struck rather than left standing because a task recording the path as closed by construction is a live instruction to remove what OD-27 authorises — the same treatment T067 got when OD-26 struck a member it still owed.

### Capability 7 — the spend backstop

- [X] T064 Budget channel enforcing all four of FR-005's ceilings from **session state** rather than from a per-attempt context, in ~~`src/runtime/budget.py`~~ **`src/runtime/session_store.py`, `trace_budget.py`, `ledger.py` and `loop.py`** (FR-005, **U-30**)

> **Extended 2026-08-05 by [finding 029](./findings/029-wall-clock-ceiling-unenforced.md) — extended, not narrowed, and the extension is the part nobody would derive from the line above.** This task's stated subject is *where the counter lives*, which T053 and T055 discharged on `spend_usd`, `tokens` and `turns`. **The fourth dimension has a different defect and this line does not name it: nothing measures elapsed wall clock at all.** Finding 029 measured a session run for 2.044 s under a ceiling of 0.001 s ending `terminated.completed`, against three controls on the same harness that fired, and a fourth control that fires the wall-clock ceiling itself at a ceiling of `0.0` — so the comparison, the wiring and `terminated.wall_clock_ceiling_reached` all work and **the numerator is what is absent**. An implementer satisfying this line as written would close nothing on this dimension. The task is not complete until a session's elapsed wall clock is measured and reconciled, **and the specification question that forces is not this task's to settle**: whether the dead interval between a crash and its resume counts against the ceiling. Finding 029 §6(a).
>
> **The numerator landed the same day, so the paragraph above is a record of why rather than a list of work outstanding — and it differs from finding 029's quoted text in exactly that.** `src/runtime/loop.py` now measures two intervals per turn: the model call, reconciled with the spend and token figures in the same transaction that releases the reservation, and the remainder of the turn, accrued at its end. A turn re-entered after a crash accrues from the moment it re-enters. The wall-clock arm of `tests/batteries/test_ceilings_under_resume.py` is no longer partial: it asserts the same three clauses as the other three dimensions across two SIGKILLs.
>
> **The specification question finding 029 §6(a) left open was determined by FR-005 rather than chosen, so it does not reach the owner as a decision.** Only running intervals are counted, and the derivation is in `AgentLoop._accrue_elapsed`'s docstring: FR-005 says the counted total is *"consumption already incurred"*, its own extension note calls all four *"consumption ceilings on a session"* as against *"properties of the execution environment"*, and its no-number-of-resumes clause is satisfied by a durable sum — which has no reset to exploit — without counting downtime. **What does reach the owner is a wording clarification to FR-005**, handed back rather than written, because this task may not edit `spec.md`.
>
> **What remains under this line is the reservation figure, not the measurement.** `ReservationPolicy.wall_clock_seconds` is now required rather than defaulting to `0.0` — finding 029 §4 measured that default writing nothing to the dimension on any path — but it is still an operator's declaration, and T062 is the table that would derive it.
>
> **Answered 2026-08-05 by T062, and the answer is that it cannot — so the requirement stands.** The table is dollars per million tokens and has no time dimension; a rate has no duration in it, and any function from one to the other would be a latency model, which is a measurement nobody has taken here and not a thing a price list can be read as. Inventing one to close this line would be FR-005's *"filled from a default this specification invented"* on the fourth dimension, which is the one dimension finding 029 already caught being filled that way once. `ReservationPolicy.wall_clock_seconds` therefore remains an operator declaration and this line remains open on that figure alone.
>
> **What T062 did take off this line is the *spend* reservation, which nobody had listed as outstanding.** `ReservationPolicy` carries three estimated figures, and `spend_usd` was a second independent operator guess that could disagree with the `tokens` guess beside it. `costs.reservation_spend_usd` now derives it from the token reservation at the dearer of the model's two rates and at the band the reserved total could reach — over-counting, which is the direction `ledger.py` argues for. The set is enumerated in `costs.DERIVABLE_RESERVATION_FIELDS` rather than stated as a complement, so that the day a per-hour price is added to that module the answer above changes by an entry appearing rather than by nobody noticing.
>
> **⚠️ TICKED 2026-08-06, on measurement rather than on the four notes above, and the tick corrects two things the line itself got wrong.** The notes are a record of passes that each closed part of this; none of them re-read the line afterwards to ask whether anything was left. Re-read and re-measured: nothing is. *(a)* **`src/runtime/budget.py` never existed and must not be created.** The channel this line asks for is four modules that already hold it — `session_store.py` owns `Ceilings` and the pure `evaluate_ceilings`, `trace_budget.py` the append-only journal outside the container, `ledger.py` the reserve-then-reconcile total, `loop.py` the two accrual points and the check at the top of every turn. A fifth module named `budget.py` would be a second place for a counter to live, which is the defect the line is about. Path corrected in the struck-and-replaced style **T067**'s path took. *(b)* **The subject of the line — the counter lives in session state, not on a per-attempt object — is enforced structurally, not asserted.** `evaluate_ceilings` is a pure function of `(Ceilings, Totals)`; `AgentLoop` carries no turn count; `SessionStore.ceiling_verdict` reads both halves off disk on every call. **Observed rather than read**: `tests/batteries/test_ceilings_under_resume.py`, 8 passed in 2.84 s — all four dimensions across three `SIGKILL`s and four separate processes each, asserting monotonicity across every boundary, the named member per dimension, and `issued <= permitted` on the turn positions the journal handed out. Two of the four arms additionally assert `issued == permitted`, so the bound is landed *on* rather than approached, and the control arm proves the reading instrument moves. That is finding 006's ceiling-of-3-permitting-6 measurement, inverted and green.
>
> **What is *not* left behind this tick, said plainly because the note above reads as if something is.** *"This line remains open on that figure alone"* described `ReservationPolicy.wall_clock_seconds` remaining an operator declaration. That is **a determination, not a debt**: the same note derives that no table of dollars per token can supply it, that any function from one to the other would be a latency model nobody has measured, and that inventing one would be FR-005's forbidden default on the one dimension already caught being filled that way. There is no pass that could close it, so carrying it as an open checkbox would mean the box could never be ticked. The figure is already implemented in the only shape available — **required, with no default**, refused at construction with the reason at the refusal site. The tick is therefore full rather than PARTIAL: a PARTIAL says *some named half is unexercised*, and every half of this line is exercised above.

- [X] T065 A low call-count backstop independent of the cost table, in `src/runtime/budget_backstop.py` — this occupies the position the removed dependency's one enforced ceiling held, and it exists so that a missing price cannot remove every ceiling at once

> **Landed 2026-08-05. Three things about it are decisions rather than details, and the third is a limitation.** *(a)* The maximum is **20**, cited rather than chosen — the only published figure for this exact ceiling is Anthropic's Managed Agents capping `max_iterations` at ≤ 20 ([research/13](../../research/13-claude-managed-agents.md) §4.4) — and it **cannot be raised**, only lowered: `research/02` §ADK measured the removed dependency's ceiling defaulting to `None`, and a limit the same configuration channel can widen is not a backstop for that channel. There is no environment key, and a test walks the module's AST to keep it that way. *(b)* It halts with a `BackstopTripped` exception rather than a terminal state, deliberately: FR-006's taxonomy is closed and adding a member is T067's, and the two shapes say different things — a terminal state is *the session concluded* and this is *the session was stopped without concluding*, which is the false-success distinction T068 exists to rule out. *(c)* **The independence is proved by planting, not by asserting.** `tests/removal_proofs.sh` cannot score it directly — the claim is that a test must still *pass* under a tamper and every arm there scores a test failing — so `test_the_backstop_fires_with_the_cost_table_emptied` empties `PRICES` and makes `price_usd` raise on everything before asserting the backstop is unmoved, and the harness instead scores the guard that keeps the module from importing the table.

### Capability 8 — the raw terminal signals

- [X] T066 Emit the raw terminal signals the taxonomy sits on — error identity, budget-exhaustion cause, and an explicit end-of-run marker distinguishing completion from cancellation — in `src/runtime/signals.py` (finding 006 primitive 2: the taxonomy was always ours, and the raw signals were the dependency's)

> **Landed 2026-08-06. Three signals, and the third is the one that was absent
> rather than merely unexposed.** *(a)* **Error identity** — a session recorded
> `terminated.unrecoverable_fault`, which FR-006 defines as *a fault the runtime
> cannot classify further*, and the exception's type and message went out with
> the traceback. `ErrorIdentity` is deliberately **not** a terminal state: a
> member named after an exception class would be the generic error FR-006
> forbids, wearing a specific-looking name. *(b)* **Budget-exhaustion cause** —
> `CeilingVerdict` already decided which of FR-005's four ceilings fired;
> `ExhaustionCause` carries that past the loop's own return, reading the
> **matched** reading rather than re-deriving the winner, because several
> dimensions can be over at once and a second pass is a second chance to name a
> different one. The declared figure travels with the observed one, so a reader
> can tell an overshoot of one from an overshoot of a million. *(c)* **The
> end-of-run marker** — finding 006 primitive 2's own row reads *"Consumer
> cancels after 5 events | generator returned | **Nothing. No marker, no
> signal.**"* The removed dependency **could** emit one, under
> `Workflow._emit_end_of_agent`, which returned early unless the `@experimental`
> `is_resumable` flag was set — **and it is off by default**, so the shipped
> behaviour was that a finished run and a run cut off mid-loop produced the same
> observation.
>
> **The defect was not the missing marker; it was that absence was ambiguous**
> between *this run did not end* and *nobody turned the marker on*. Two
> structural rules, not conventions, keep that from recurring: `EndOfRun` has no
> reason meaning *did not end*, and `require_paired` refuses an outcome carrying
> a terminal state without a marker, a marker without a terminal state, or a
> pair that name different members. The second half of that check is the one a
> presence-only rule would miss — two populated fields agree that the run ended
> and can still disagree on how, and nothing at this layer can say which is the
> one the session row holds, so neither is preferred.
>
> **Membership is not restated here.** **OD-26** makes `src/contracts/terminal.py`
> authoritative for which names exist; `signals.py` maps a reason to one of them
> and puts every entry through `terminal.require()` **at import**, so a member
> renamed there and not here fails at import rather than on the one path nobody
> exercises — which is how `terminated.no_progress` sat declared-and-absent
> (finding 027). The reason set stops at what this process can observe: FR-049's
> bounds and FR-050's lapsed capability are the supervisor's, and a reason for
> them here would be a signal with no emitter.
>
> **Planted, not reasoned.** Four tampers, each watched failing before the arm
> was trusted: the marker dropped from the span's `detail` (both new runner arms
> fail, on the absence rather than on a wrong value); the fault's identity
> replaced with a constant (only the fault arm fails — the tamper is narrow);
> the declared figure dropped from the cause; and the two `__post_init__` calls
> deleted, without which the pairing rule is correct and uncalled. **Two existing
> removal proofs moved with the source and were re-pointed rather than
> weakened** — T047's cancellation pair. The second is now a *narrower* tamper
> than it replaces: the caller's name and the caller's marker are resolved from
> one variable, so dropping teardown's contribution is one edit, and two
> resolutions of one question can no longer disagree with each other.
- [X] T067 Terminal taxonomy over those signals, with a named member per ceiling, per bound, plus `no_progress`, ~~`denied_operation`~~ *(struck 2026-08-05 — **OD-26**)* and `completed`, in ~~`src/runtime/terminal.py`~~ **`src/contracts/terminal.py`** (FR-006, [`data-model.md`](./data-model.md) §2.1)

> **T067's path corrected 2026-08-05, and its remaining work is smaller than the line reads but is
> not a file move.** The struck path named a module that does not exist. **The taxonomy is already
> built**, at `src/contracts/terminal.py`, with `TAXONOMY`, `NAMES`, `is_terminal()` and `require()`,
> and **seven consumers** read it: `src/contracts/transition.py`, `src/runtime/trace.py`,
> `src/runtime/session_state.py`, `tests/invariants/test_terminal_taxonomy.py`,
> `tests/invariants/invariants.yaml` (INV-005), `tests/batteries/test_bounds_exhaustion.py` and
> `tests/removal_proofs.sh`. Building it a second time under the struck path would have been a live
> module duplicated, which is what the wrong path invited.
>
> ~~**What is genuinely left is the two members the taxonomy lacks**, and one of them is blocked.~~
> **Corrected 2026-08-05 by OD-26: what is left is one member, and it is the blocked one.** Every
> ceiling and every bound has its member and `completed` has its member; `no_progress` does not.
> **Row 6 of the loose-requirements table below already records that
> `no_progress`'s predicate is unwritable as specified**, and it is assigned to this task — so T067
> cannot complete while that stands, and closing it would mean inventing the stall condition FR-006
> declines to define. ~~`denied_operation` is unblocked and is recorded as owed nowhere else.~~
> **`denied_operation` is struck rather than owed.** OD-26 establishes that no requirement wants a
> refusal to be terminal: SC-022 counts denials as records the loop continues past, and FR-006 names
> exactly one producer of its own. The struck sentence was right that nothing recorded it as owed, and
> wrong to read that as a debt — it was a name from an earlier design that nothing had ever removed.
> [Finding 027](./findings/027-lifecycle-edge-set-divergence.md) is the census, and it also reported
> the divergence running the other way: three members the runtime already reaches were absent from
> §2.1's own diagram. **All five divergences are now reconciled and `check_corpus.py`'s
> `lifecycle-taxonomy` check is what keeps them so.**
>
> **⚠️ TICKED FULLY 2026-08-06, and the tick overturns the block above rather than working around
> it.** The paragraph reads "T067 cannot complete while that stands", and a PARTIAL tick on T058's
> precedent was the expected outcome. It is the wrong outcome, because **the premise is stale**:
> **FR-006 does define the stall condition.** [`spec.md`](./spec.md) FR-006 names it — a turn makes
> progress when it issues a tool call the session has not issued before, or produces a result — and
> requires the consecutive-turn threshold to be operator-declared with no default. Row 6 of the
> loose-requirements table was true when written and stopped being true when FR-006 was extended; no
> pass re-read it. So the member is built, not deferred, and the block is struck below.
>
> **What landed.** `terminated.no_progress` in the taxonomy; **ST-011** in
> `src/contracts/transition.py` carrying `selects_among_alternatives=True`, because the member is
> chosen over the alternatives rather than forced; `src/runtime/progress.py` holding `StallPolicy`,
> `StallVerdict` and the predicate; `SessionStateMachine.terminate_on_stall()` alongside
> `terminate_on_ceiling()`, with `_NEEDS_READINGS` making the **bare `terminate()` refuse both
> members** so neither can reach the record without the figures that justify it. Per **OD-26** the
> taxonomy carries membership only and `_move` carries the transition; nothing about the edge was
> written into `terminal.py`.
>
> **Three decisions worth the reader's time.** *(a)* **"Not issued before" is a content address of
> `(tool, arguments, outcome)` and deliberately not of the body** — FR-055's canonical
> serialization, so a retry that fails the same way twice is the same call and a retry that starts
> succeeding is not. Addressing the body would make a tool returning a timestamp look like progress
> forever. *(b)* **The count is a pure function of the journal's records, not a counter on the loop
> object.** FR-007 resumes in a new process; a per-attempt counter resets at every crash, so an agent
> that stalls, crashes and goes on stalling would never terminate. A proof holds this. *(c)* **The
> threshold has no default and `StallPolicy` is a required argument** at every `AgentLoop` and
> `Runner` construction site — FR-033 and **Q-10** both refuse a silently-chosen bound, and a
> keyword with a default is exactly the silent choice.
>
> **Observed, not read.** `tests/unit/test_progress.py`, 16 passed. Three tampers scored by
> `removal_proofs.sh`: the loop not consulting the predicate (the arm reads the *name*, because
> T065's backstop and the turn ceiling both still stop a repeating agent — stopping is not the
> claim), the count narrowed to this attempt's turns, and `_NEEDS_READINGS` dropped to the ceiling
> member alone.
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
| 1 | Agent loop, dispatcher, merge discipline | T041–T045 | 8 | 11 | T043's 1–2 days re-uses the fan-out item's shape; **OD-15** records that as a construction requirement of our own dispatcher rather than a discipline imposed on somebody else's scheduler, and calls it the easier of the two. **Excludes FR-058** *(noted 2026-08-05)* — added 2026-08-04, after this row was derived, and it landed inside this capability because it bounds FR-004's results. The seam is set out at [capability 1](#capability-1--the-agent-loop); the figure is **not** re-derived here, and reading it as this capability's cost understates it |
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

**What was measured.** ~~Phase 2 produced **five real defects across roughly 2,300 lines** — about
**one per 460**.~~ **Superseded 2026-08-04 by
[finding 020](./findings/020-phase-2-defect-density-adjudicated.md)**, which adjudicated the count
against a severity bar written before the defects were looked at: **seven Phase 2 defects against the
6,290 lines the commit added, about one per 898 — or six against the 2,337 lines of new source,
about one per 389.** Two of the original five were introduced by Phase 1 and merely fixed by
Phase 2; three the pass fixed were missing from the list; four are still present. The line count is
the new Phase 2 sources in the working tree; the defect count is
~~the implementation pass's own, and **neither has a findings document behind it**, which is recorded
below as an outstanding item rather than glossed~~ now independently adjudicated. Against a working
assumption of one per 3,000 the phase is denser on every population, by between roughly three and
roughly eight times depending on which one is named.

**Why, and the *why* is what makes this usable rather than just alarming.** ~~The five were~~
**Corrected 2026-08-04 — this paragraph still enumerated the composition the paragraph above it had
already struck, so read it as a description of *finding 019's original five* and not of Phase 2's
defect set.** Two of the five below — the redaction marker and the benchmark — were introduced by
Phase 1 and merely fixed by Phase 2, by `git log -S` attribution in
[finding 020](./findings/020-phase-2-defect-density-adjudicated.md); and three Phase 2 defects the
pass fixed are missing from the list entirely. The five were: a
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

> **The inference in the paragraph above does not survive the adjudication, and this is the second
> half of the same 2026-08-04 correction.** *"Not one of those is caught by the thing that catches
> kernel-mechanism defects"* is true of those five and is **not** true of the phase. The counting
> that produced them excluded two pure-cgroup defects, neither of which failed loudly:
> [finding 020](./findings/020-phase-2-defect-density-adjudicated.md)'s **X3**, a `cgroup.kill`
> fallback that returned successfully having killed only some of the processes, and its **P4**, a
> preflight check that reads a path the kernel documents as absent in the root cgroup, gets `False`,
> reports a present facility as missing, and is paired with a test that never reads the check's
> result. **The instrument share survives the recount and the storage-class claim does not** — of the
> seven, P3, P4 and P7 are instrument defects, so *three of the counted defects are instruments*
> remains true over the new population while *all of them sit in the storage class* becomes false.
> The table below carries the same correction on both of its rows; this note exists because the prose
> stated the classification before the table did, and a reader arriving here first would not reach it.

**So the rate is not one number, and applying one per 500 uniformly would overcorrect exactly as
badly as one per 3,000 underestimated.** The working split:

| Rate | Applies to | Why |
|---|---|---|
| **~1 per 500** | anything crossing a storage or serialization boundary — persisted records, cross-process handoffs, canonical form, redaction, ledgers and journals, and **any instrument whose output is a measurement** | The failure is a plausible wrong value, and nothing outside the code checks it. ~~All five Phase 2 defects are here~~ **Corrected 2026-08-04: not all of them are.** Two Phase 2 defects are in cgroup code and neither failed loudly |
| **~1 per 3,000** | code the kernel checks for you — namespaces, cgroups, `seccomp`, capabilities, file descriptors | ~~A wrong call fails at the syscall with a named errno, so the defect surfaces on first execution rather than at review~~ **Contradicted 2026-08-04 by two counterexamples in the phase that produced this table** — see the caption |

> **This table is reasoned from one phase, is not a measurement, and its second row now has observed
> counterexamples — quote it with this sentence attached.** One rate was observed; the other is the
> prior it was measured against, carried forward on an argument about failure modes rather than on any
> count of kernel-mechanism code in this repository.
> [Finding 020](./findings/020-phase-2-defect-density-adjudicated.md) found **two kernel-mechanism
> defects in the same commit, neither of which failed loudly**: `cgroup.kill` degrading silently to a
> racy per-pid signalling loop, and a preflight check that looks for `cgroup.kill` in the root cgroup
> where the kernel documents it as absent, paired with a test that never reads the check's result. The
> claim that all the phase's defects sat in the storage class was true only of the five that were
> counted, and the counting excluded the counterexamples.
> ~~The observed side is itself denominator-sensitive: two of the five defects sit outside
> the line count that produced *one per 460*, and on the one population containing all five the rate
> is one per 1,247.~~ **Superseded**: those two defects sit outside the *phase*, not merely outside
> the denominator — both were introduced by Phase 1 and fixed by Phase 2. Restating the denominator
> diluted a correct numerator rather than repairing it.
> [Finding 019](./findings/019-phase-2-defect-density.md) is the original anchor and
> [finding 020](./findings/020-phase-2-defect-density-adjudicated.md) is the adjudication that
> supersedes its count; read both.

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

**Three outstanding items this creates**, all flagged rather than resolved:

- ~~**The measurement has no findings document.** Five defects in roughly 2,300 lines is a
  measurement of this project's own output and it currently lives only in this section and in the
  implementation pass that produced it. Feature 002 has no `findings/` directory, so filing it is a
  structural act rather than a propagation one.~~ **Discharged 2026-08-03 —
  [`findings/`](./findings/) was opened as the corpus's second authority namespace, continuing
  feature 001's numbering rather than restarting it, and the measurement is filed as
  [finding 019](./findings/019-phase-2-defect-density.md).** The line count is recomputed there from
  the Phase 2 commit with the counting rule stated, and comes to **2,337** — *roughly 2,300* above is
  that figure rounded, not a different measurement. The finding also records a defect in the
  measurement this section did not catch: **two of the five defects lie outside the 2,337 lines**, so
  the numerator and the denominator describe different populations, which is exactly the pairing
  **U-49** was opened for. **Amended 2026-08-04**: the same two defects lie outside the *phase* —
  [finding 020](./findings/020-phase-2-defect-density-adjudicated.md) attributes both to Phase 1 by
  `git log -S` — so the pairing was a numerator error wearing a denominator error's clothes.
- **The classification is reasoned, not measured.** One phase produced the split. Whether kernel
  code really is six times cleaner, or whether Phase 2 was simply the harder phase, is not
  established by a single phase, and the next phase to complete is the one that tests it. *(Still
  outstanding, and now **worse than outstanding**: finding 020 found two kernel-mechanism defects in
  the same commit and neither failed loudly, so the split's second row has counterexamples rather
  than merely an absence of support.
  [Finding 019](./findings/019-phase-2-defect-density.md) states it as its headline
  limitation rather than resolving it, and proposes it for a register entry of its own.)*
- **Four Phase 2 defects are still present, one of which appears to break CI.** Opened 2026-08-04 by
  [finding 020](./findings/020-phase-2-defect-density-adjudicated.md), which found them in a single
  adjudicating pass over a suite that is green. They are unowned by any task in this list. The
  preflight one — `_check_cgroup_kill` reading the root cgroup, where the kernel documents
  `cgroup.kill` as absent — should be looked at before the next privileged run.

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
  - **The renewer stops permanently on the first exception of any kind, and the lease it was extending is already expired by the time anyone could look. Measured 2026-08-06; deliberately not repaired, because every available repair wants a decision this pass may not take.** `LeaseRenewer._loop` catches `Exception`, records it in `stopped_because` and **returns**. Planted arm — one `sqlite3.OperationalError("database is locked")` raised on the second of twelve scheduled renewals, real table, real thread, everything else untouched: renewals stop at **1 of 12**, the thread is dead, the row is still `RUNNING`, and the lease is **0.5 s in the past**. Control arm, the same probe with nothing planted: **12 of 12**, thread alive, lease in the future. So a momentary `SQLITE_BUSY` — precisely the class the repository layer labels *retrying is reasonable* — revokes a **healthy** session's authority. Lapsing is the fail-closed direction so nothing is unsafe, but it is wrong, and it is undiagnosable: `session_table.py`'s constructor comment already names this exact shape as *"its own defect"* after it cost real time once, when the default same-thread guard's `ProgrammingError` killed this thread silently. One cause was fixed there (`check_same_thread=False`); the general shape was left.
  - **The open question, put rather than answered.** The one-line counterfactual — `continue` in place of `return` — was measured on the same probe: **11 of 12** renewals, thread alive, lease healthy. It works because `LEASE_TTL_MULTIPLE = 2.0` **already** budgets for exactly one missed renewal, and the current loop cannot use the tolerance its own constant was chosen to provide. But `continue` retries **forever**, which is the trap the three-way split at `ff202ae` exists to prevent: `StoreBusyError`, `StoreWedgedError` and `StoreUnusableError` were introduced so a caller need not choose between giving up on the first contention and spinning on a wedged resource. **`SessionTable` raises none of them** — it raises raw `sqlite3.OperationalError`, because it sits outside the repository layer ([T016](#storage-addressing-and-rollback)). So each live option costs something: *catch the engine exception here*, which puts engine coupling into a file that is **not** on obligation 2's skip list; *bound the retries*, which is a new unmeasured number in a module whose docstring deliberately declined to add a second one (FR-043, T033); *make the thread die loudly*, ~~which has no vehicle — `src/` contains no `logging`, no `getLogger` and no `warnings.warn` anywhere~~ **whose premise is true and whose conclusion is not — corrected 2026-08-06 in the sub-bullet below**; or *complete T016's migration* and consume the classification that already exists. **The fourth is the one the other three are working around.** This is independent of the WAL race and of the migration in the sense that matters — a renewer that dies silently on any transient exception is wrong whichever layer the table sits behind — but not independent in the sense that would let it be fixed cheaply here. Reachability is the same as everything else in this module: `LeaseRenewer` is constructed only in `tests/integration/test_lease_revocation.py`, never in `src/`. ~~**No test is added**, on finding 033's ground: a test pinning the current behaviour would enshrine the defect and turn the repair into a failure, and a test pinning the desired behaviour presupposes the decision above.~~ **Superseded 2026-08-06: the decision was taken and a test now pins the *desired* behaviour — see the repair bullets below.** Reproduction is a dozen lines — wrap a real `SessionTable`'s `renew` so the *n*-th call raises `sqlite3.OperationalError`, start a real `LeaseRenewer`, sleep past several intervals, and read `renewals`, the thread's liveness and `lease_expires_at - time.time()`.
  - **Correction, measured 2026-08-06: "die loudly" *does* have a vehicle, and the option was ruled out on a search of files rather than on behaviour.** The premise above is exact and reproduces — an AST walk over all 60 files in Python `src/` and an independent regex sweep each return **zero** matches for `logging`, `getLogger` and `warnings.warn`. The conclusion drawn from it does not follow, and it is the failure `tools/README.md` names: a claim about **behaviour** whose evidence is a **file**. Planted and observed with fd-level capture: an uncaught exception on a **daemon** thread reaches stderr through `threading.excepthook` — **490 bytes** of traceback carrying the planted message, thread dead, process alive. So `_loop`'s `except Exception` is not compensating for a missing facility; **it is what closes a channel the interpreter already provides.** Deleting it makes the renewer die loudly with nothing added. Measured on the same probe for contrast: with the `except` in place, the identical planted failure emits **0 bytes** to stdout and stderr, and the reason survives only on `stopped_because` — an attribute **nothing in `src/` reads**, whose one reader anywhere is `tests/integration/test_lease_revocation.py`. That is strictly worse than the other two operator reports in the tree (`config.py:_report()`, `preflight.py:preflight()`), which at least hand their text to an exception.
  - **Still not repaired, and the reason has changed shape rather than gone away.** A traceback is a poor operator interface and choosing the good one is a design decision with a live constraint this pass measured: **the structured alternative is refused.** The non-`main` code on both sides of the language boundary writes a record rather than addressing a human — `SpanWriter` here, `DecisionLog` in Go, which never imports stdlib `log` at all — but FR-038's kind set is **closed** and enforced at construction, verified by attempting it: `lease_renewal`, `supervisor_error` and `operator_message` are each refused by `SpanError`, while `model_call` is accepted. `state_transition`, the nearest declared kind, refuses without a `StateTransition` carrying a deciding rule. **spec.md has already once declined to add a kind on exactly this ground** (line 879: *"does not add a span kind; FR-038's set is closed"*). So the three live options are an eighth span kind, which amends a closed set; an injected logger on Go's pattern, which the entry point recorded at [the configuration section](#configuration-and-failing-closed) does not yet exist to inject from; or the re-raise, accepting a traceback as the interface. ~~**The question is put, not answered**~~ **Answered 2026-08-06 — the third, as an interim; see the next bullet**, and no logging facility is built here: its shape — stdlib versus structured, and its relationship to the trace record and to the decision log Go already writes — is an owner's decision, not a recording pass's.
  - **⚠️ DECIDED and REPAIRED 2026-08-06 — the *re-raise* is taken, explicitly as an interim. The other three routes remain blocked and the fifth is ruled elsewhere.** The owner ruled it on three grounds: the lease lapses either way, so the change is **behaviour-neutral on the outcome** and converts a silent lapse into a visible one rather than altering what happens; `session_table.py`'s constructor comment already rules an undiagnosable lapse *"its own defect"*, which makes the visibility the missing half and not an addition; and it is reversible the moment an entry point exists to inject from. **Reproduced before acting rather than taken from the bullets above**, on this file's own rule that a fix verified against an unobserved failure is not verified — planted arm **1 of 12** renewals, thread dead, row `RUNNING`, lease **0.503 s in the past**, **0 bytes** on stdout and stderr; control arm **12 of 12**, thread alive, lease **+0.083 s**. After the change the same planted arm gives the **identical** 1 of 12, dead thread, `RUNNING` row and 0.505 s-expired lease, plus **881 bytes** of traceback naming the planted engine error — which is the whole of what the change buys, and why "interim" is accurate rather than modest. **The other three stay blocked for the reasons already recorded**: `continue` retries forever and `SessionTable` cannot raise `ff202ae`'s three error types from outside the repository layer; catching the engine exception here puts engine coupling into a file **not** on obligation 2's skip list; bounding the retries mints an unmeasured number in a module that deliberately declined to add a second one. **The fifth — completing T016's migration — is ruled deferred by [OD-28](../001-discovery-validation/plan.md#od-28--the-sessiontable--repository-migration-stays-deferred-and-the-shape-is-routed-to-t016s-note-rather-than-re-litigated-the-deferral-expires-the-moment-a-supervisor-process-constructs-a-session-store) and routed to T016's note; it is not re-litigated here.** **Nothing is re-estimated and no task is minted**, on [T041](#phase-3-foundational-b--the-runtime-core-od-15-left-unowned-u-48)'s ground that a re-estimate taken mid-phase by the pass that just changed the thing produces a motivated number.
  - **The channel's own limit, measured — because "the excepthook delivers it" is not true unconditionally, and the correction above did not test the case where it fails.** `7e874d7` established the vehicle on a daemon thread **mid-run**, which reproduces. It does **not** hold across interpreter finalization: `threading.excepthook` writes to a *buffered* stderr, so a raise coinciding with the main thread's exit is truncated, lost outright, or **aborts the process** — `Fatal Python error: _enter_buffered_busy`, SIGABRT, exit 134. Sweeping the main thread's exit across the raise instant in 0.5 ms steps (n=87): **41 clean, 14 truncated, 32 silent, 4 aborted**. Forcing the overlap with an event instead of sweeping for it: 20 of 20 truncated-or-aborted at 0 ms, **19 of 20 silent at 1 ms**, 20 of 20 silent at 5 ms and beyond. **Reachability is this module's usual and is stated so the figure is not overread**: nothing in `src/` constructs a `LeaseRenewer`, and the one real-process construction in the tree — the `SIGKILL` fixture's child — never exits normally, so the window is not reachable today. It is recorded because it is a **further argument that a traceback is not the operator interface**, not an argument for the swallow, which loses the report in *every* case rather than in a sub-millisecond one. **The durable answer is unchanged: a logger injected from an entry point on Go's pattern** — `log.New(os.Stderr, ...)` as the first statement of `main()` in `src/proxy/main.go`, handed downward, with no package-level logger anywhere in Go — blocked on the seam at [the configuration section](#configuration-and-failing-closed). No logging facility is built here, and the comment at the change site says so in terms.
  - **`stopped_because` is kept and set *before* the raise, and the reasoning is not "setting-then-raising is obviously right".** Its exception-path value has **no reader at all**, not even a test — checked across the tree including dynamic access. But the *attribute* has two: `test_the_renewer_thread_actually_renews` interpolates it into its failure message and asserts it `None` on the healthy path, and `test_the_renewer_says_why_it_stopped` asserts the `"session is no longer RUNNING"` value — which is the **orderly** stop and not this defect. So removing the attribute would delete a correct test to repair an unrelated one, and dropping only the exception-path assignment would make the attribute lie: its documented `None` means *running, or stopped in the orderly way*, and a crash leaving it `None` reports an orderly stop to the one reader it has. `7e874d7`'s charge that it is *"strictly worse than the other two operator reports, which at least hand their text to an exception"* is **discharged by setting *and* raising**, not by deletion. **Blast radius, established rather than assumed**: no existing test asserted the swallow — nothing in the suite plants an exception on this path, which is precisely why the fix was removable in silence; the exception cannot take down anything but the renewer thread outside the finalization window above; and under `pytest` the same exception surfaces as `PytestUnhandledThreadExceptionWarning` rather than an error, there being no `filterwarnings = error` in this repository's configuration.
  - **The proof, added because the fix was removable with the suite still green.** Restoring `return` in place of `raise` left every test passing, so `test_a_failed_renewal_is_not_silent` is added to `tests/integration/test_lease_revocation.py` and declared in `tests/removal_proofs.sh`; `EXPECTED_PROOFS` moves **163 → 164**, read off the guard's own transition message rather than computed from a baseline and a delta. The arm runs the renewer **out of process** on purpose — `pytest` installs its own `threading.excepthook` and demotes thread exceptions to warnings, so an in-process assertion would score the plugin and not the channel a deployed supervisor has — and its child outlives the raise by an order of magnitude, keeping it clear of the finalization window. **It discriminates**: under the tamper its `RENEWALS 1` assertion still passes and only the stderr assertion moves, so it proves the *report* rather than the renewal count, which is the same arm either way.
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
  - **The supervisor image is where a second writer on the session store first becomes possible, and nothing enforces the condition that currently keeps it safe. Recorded 2026-08-06 against [T016](#storage-addressing-and-rollback).** [Finding 033](./findings/033-session-table-wal-race-unreachable-and-owed-to-migration.md) measured `PRAGMA journal_mode=WAL` being refused with `SQLITE_BUSY` **four orders of magnitude inside the busy timeout** when a second party first-opens a *brand-new* store, because SQLite deliberately bypasses the busy retry on the conversion path. `SessionTable.__init__` runs that pragma as its schema script's **first** statement, so a refused conversion aborts before `CREATE TABLE` and leaves the file with no `session` table in it at all. A store already in WAL is immune — a second open succeeds in 0.28 ms even against an `EXCLUSIVE` holder — so the hazard is specifically **concurrency on the conversion**, which happens once in a file's life. The property this deployment must preserve, stated so its loss is checkable: **the session store is created once, before any second process attaches**, *or* `session_table.py` has completed the migration T016 records. Neither is asserted anywhere today, and the supervisor image plus T160's compose bundle is the first artifact that can falsify the first one.
- [ ] T160 [US4] The compose bundle we author, with reference-application values marked under FR-043 as fixture configuration rather than product defaults, in `deploy/compose/` (T-11)
  - **Extended 2026-08-04 by [finding 024](./findings/024-deployment-surface-permission-census.md): the bundle carries two runtime-permission artifacts, and without them the three kernel facilities T006 checks for are present and unreachable.** **(a) Its own seccomp profile**, in `deploy/compose/seccomp/session.json` — the container runtime's own default plus one added `SCMP_ACT_ALLOW` rule naming `unshare`, `mount`, `umount2`, `pivot_root`, `setns`, `mount_setattr`, `move_mount` and `open_tree`, with the argument mask removed from the non-`CAP_SYS_ADMIN` `clone` rule so namespace flags pass; 426 allow-listed syscall names becoming 427. Referenced from the compose file by `security_opt`, so the operator's action is a file we ship rather than a flag they compose. **(b) `/sys/fs/cgroup` mounted read-write with `--cgroupns=host`**, which is a separate change refused by a separate layer — the read-only mount, not seccomp — and is not fixed by any profile decision
  - **Two things this task may not do.** It may **not** offer `seccomp=unconfined` as an alternative or present the choice as default-profile-versus-unconfined: that framing charges the operator the whole filter for a mechanism a named eight-syscall widening buys, and `unconfined` leaves FR-049 exactly as blocked as it was. And it may not describe the cgroup mount's cost as narrower than it is — the supervisor container gets write access to the host's entire cgroup tree rather than to a delegated subtree, and no route to narrowing that has been found (FR-049, **FR-043**)
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
  - **This task presupposes a startup the Python components do not have, measured 2026-08-06 and recorded at [the configuration section](#configuration-and-failing-closed).** `config.load()` has no caller in `src/`, and neither does OD-27's `require_priceable` preflight; twelve no-default keys under four authorities, and the unset-value reporting already written for them, are unreachable for want of an assembly point that no task in this file creates. An implementer starting here will find there is no end-to-end path to exercise before there is one to write the test against
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
- [ ] T205 [US5] **DEFERRED BY OWNER DECISION 2026-08-03 — not planned work for v1.** **Boot the supported-kernel matrix and convert the derived floor into a tested one** — 5.14, 5.15 LTS, 6.1 LTS and 6.6 LTS, running the FR-048, FR-049 and FR-050 mechanism batteries on each — in `.github/workflows/kernel-matrix.yml` (**OD-17**, FR-053). Until this exists, **every run to date was on 6.12 or 6.17** — `6.12.76-linuxkit` locally and `6.17.0-1020-azure` on the `ubuntu-latest` runner, the latter first observed 2026-08-04 when CI ran for the first time — and 5.14 is a lower bound on what *could* work rather than a statement that it does. Recording the boots is the whole task: cgroup delegation semantics, `pivot_root` in a user namespace and `seccomp` notification behaviour all moved across the intervening releases, so a green run on either of those kernels is evidence about that kernel and about nothing below it
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
| ~~6~~ | ~~**FR-006**'s stall condition~~ **DISCHARGED 2026-08-06** | ~~[`data-model.md`](./data-model.md) names `terminated.no_progress` as an FR-006 stall condition. Neither FR-006 nor any success criterion defines what no progress is, so the predicate that fires it is unwritable as specified~~ **The row was true when written and stopped being true when FR-006 was extended.** FR-006 now defines progress — a turn that issues a tool call the session has not issued before, or produces a result — and requires the consecutive-turn threshold to be operator-declared with no default. The predicate is `src/runtime/progress.py` and the member is in the taxonomy. **The count above still reads six; it is five** | ~~T067~~ |

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
| **Linux only, with no degraded mode** | T006's preflight and T172's platform-statement audit (**OD-17**). **Extended 2026-08-04**: T206 adds the real-`unshare` pair that tells a fixable runtime-profile refusal from an LSM one, T160 ships the profile that fixes the first, and T190's support audit now also has to catch **managed container services** — Fargate, Cloud Run, ACI, GKE Autopilot — described as anything other than unsupported. They expose no seccomp knob, so they are foreclosed by the platform rather than degraded |

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
