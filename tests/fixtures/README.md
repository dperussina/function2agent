# Committed fixtures — FR-053's discipline, and the inventory each capability owes

**Requirement**: FR-053. **Task**: T008, reconciled by **T200**.

## The discipline

Every capability that claims a measured property owes a **committed fixture** that produces it. Not
a description of a test that was run once, not a number in a document: a file in this tree that a
reader can execute.

Three rules, and the third is the one this corpus learned the hard way.

1. **A fixture is committed, not described.** A measurement whose fixture is not in the repository
   is a claim.
2. **A fixture pins its inputs.** Task files, prompts and request text live *inside* the record
   (FR-053, U-47), so a fixture cannot silently drift into measuring a different thing.
3. **A passing fixture is not evidence a mechanism works.** A threshold is pinned only when a
   fixture plants a defect **just past it**. Every mechanism in this repository therefore owes two
   fixtures: one that exercises it, and one that removes it and shows the first fixture failing.
   Rule 3 is why `tests/invariants/invariants.yaml` carries a `removal_proof` field per entry.

## What "removal proof" means concretely

| Mechanism | Exercised by | Removed by |
| --- | --- | --- |
| FR-048 mount namespace | an undeclared path returns `ENOENT` | the same probe in a plain fork, where `/etc/passwd` *is* reachable |
| FR-049 `pids.max` | a fork storm is refused, `pids.events max > 0` | `pids.max` set to `max`, the identical storm unstopped |
| FR-050 lease | a `SIGKILL`ed supervisor's lease lapses | the row still reads `RUNNING`, so a state-only check would honour it |
| FR-048 recording | the listener observes the `openat` before the kernel acts | the same open in a plain fork, observed by nobody |
| FR-052 import graph | the checker reports a planted forbidden import | the checker ignores a permitted one |
| FR-036 `Secret` | every implicit path yields a redaction | an added attribute that discloses the value fails the scan |
| Capability conformance | the proxy reads a supervisor-written table | either side's digest convention or column name changed |

All of them are executable as a set — `bash tests/removal_proofs.sh` edits each mechanism out of a
copy of the tree, runs the test that should depend on it, and reports `UNPROVEN` for any test that
still passes. It covers both languages.

## Inventory

Present, with the requirement each discharges:

| Fixture | Requirement | Location |
| --- | --- | --- |
| Declared location sets | FR-048, FR-054 | `tests/fixtures/locations.py` |
| Mount-namespace absence | FR-048 | `tests/integration/test_mount_namespace.py` |
| Seccomp recording and ordering | FR-048, SC-022 | `tests/integration/test_seccomp_recording.py` |
| Bounds exhaustion, three arms plus co-located workload | FR-049, FR-006, SC-023 | `tests/batteries/test_bounds_exhaustion.py` |
| Lease revocation, `SIGKILL` from a separate process | FR-050, SC-024 | `tests/integration/test_lease_revocation.py` |
| Seccomp overhead | **Q-09**, T101 | `tests/batteries/test_seccomp_overhead.py` |
| The invariant set | Principle II | `tests/invariants/` |
| Egress pipeline, seven stages | FR-008–FR-019 | `src/proxy/*_test.go` |
| Cross-language capability boundary | FR-014, FR-050 | `tests/fixtures/session_conformance.{py,json,sqlite3}` |
| Reference application, seeded state and known-correct answers | FR-053, T116 | `tests/fixtures/reference-app/` |
| Sandbox image FR-021 properties | FR-021, T096 | `deploy/images/sandbox.Dockerfile`, `tests/invariants/test_sandbox_image.py` |
| Admission fixture set, fourteen origin responses | FR-053, T075, SC-018 | `tests/fixtures/admission/` |
| Analyzer fixtures, positive and negative | FR-053, Principle VII, T135 | `tests/fixtures/analyzer/` |
| codegraph schema pin | T118 | `tests/fixtures/codegraph-schema/` |
| Source-change synthetic corpus | FR-053, SC-008, T154 | `tests/fixtures/drift-source/` |
| Deployment-change synthetic corpus | FR-053, SC-009, SC-020, T155 | `tests/fixtures/drift-deployment/` |
| Drift corpus loaders | FR-053 | `tests/fixtures/drift_corpora/` |
| Operation-added corpus | SC-026, T158 | `tests/fixtures/operation-added/` |
| Spec-withdrawn corpus | SC-021, T157 | `tests/fixtures/spec-withdrawn/` |
| Injected value-fault corpus and shape-fault control | SC-005, SC-006, T131, T132 | `tests/fixtures/value-faults/` |
| Resume-across-crash session fixture | FR-007, T054 | `tests/fixtures/resume_session.py` |
| Resume across a crash boundary (`SIGKILL` from a third process) | FR-007, T054 | `tests/integration/test_resume_sigkill.py` |
| Concurrent-writer probe against this store | T-06, T050 | `tests/integration/test_store_concurrent_writers.py` |
| Drift-scheduler egress path | FR-046, OD-12, T141, T142 | `src/runtime/drift/scheduler.py` |
| Provider cassettes | Principle VII, T060 | `tests/conformance/cassettes/` |
| Effect-gate oracle on the reference application | FR-041, T180 | `tests/batteries/effect_gate_oracle.py` |
| Framing-ambiguity cases | **Q-01**, T094 | `src/proxy/framing_test.go` |
| Ceilings under resume | SC-030, T055 | `tests/batteries/test_ceilings_under_resume.py` |

T200 (2026-08-14) walked `tests/fixtures/`, `tests/batteries/`, `tests/conformance/cassettes/`, the analyzer and admission sets, the drift corpora, the effect-gate oracle, and the reference application. A named Present location that is not in the tree, or a committed child of `tests/fixtures/` that this table forgot, fails `tests/contract/test_fixture_inventory.py`.

**Residuals on rows that moved out of Owed, recorded rather than closed.** The scheduler exists; T144's additional triggers are unwired, `due` is the interval predicate, and no thread calls `tick`. T054 measures one platform, one process pair, one kill per session — completed inner turns do not re-execute and recorded local effects do not repeat. Finding 006 measured resume over ADK, which OD-15 dropped; that substrate remains unobserved. T050 measures this store on this platform; it does not make concurrent writing safe in general, and finding 006's session service remains unobserved. T094's framing cases are the cases we thought of, measured on go1.24.3; they are not an independent captured-frame corpus.

`session_conformance.sqlite3` is the one committed **binary** fixture, and it is committed on
purpose: it is a session table written by the supervisor's own writer and read by the enforcement
point's own read-only store, so it holds the two sides to an agreement that nothing in either
language enforces. Regenerate it with `python tests/fixtures/session_conformance.py` — and expect
`src/proxy/conformance_test.go` to fail until the Go side is brought back into agreement, which is
the entire point of it.

**The Go arm reads a byte copy of it in a temporary directory, and the copy is load-bearing rather
than tidy.** The fixture is a WAL-mode database — header bytes 18 and 19 both read `2` —
because the supervisor's own writer puts every store into WAL, and SQLite needs the shared-memory
index on **every** connection to a WAL database, including a `mode=ro` one. Opening the committed
file in place therefore left `session_conformance.sqlite3-shm` and `-wal` beside a tracked file on
every `go test`, and two passes reported them as stray untracked files. They are **not** evidence
of anything opening this database read-write; the Go store passes `mode=ro&_pragma=query_only(1)`
and both guards have their own test. Copying keeps the production open path and the fixture's WAL
mode intact and puts the sidecars somewhere the test framework deletes, which is why the pair is
not gitignored: a `git status` entry nobody created is a signal this repository relies on, and
suppressing these two would suppress a future one that mattered.

The fixture's fifth row, `sess-terminated-live-lease`, is written with raw SQL rather than through
`SessionTable.terminate()`, because `terminate()` also zeroes the lease. Without a row that is
`TERMINATED` while its lease is still live, the fixture cannot tell a state check from an expiry
check, and an enforcement point that checked only expiry would pass every other row in it. The
first version of this fixture did not have that row and did not notice.

Owed, and named here so the absence is visible rather than inferred:

| Fixture | Requirement | Why it is not here yet |
| --- | --- | --- |
| Reference-application overhead | **Q-09**, T101 | ~~The reference application does not exist.~~ **It does now (T116, `tests/fixtures/reference-app/`).** What is still owed is the *measurement*: `tests/batteries/test_seccomp_overhead.py` measures three proxy workloads and records that it does **not** discharge this. T101 also asks for a shell-heavy arm, which the reference application is not — it is an HTTP surface. T101 stays PARTIAL; T199 named this clause and did not close it. |
| Independent captured-frame corpus | **Q-01** | T094 landed the cases we thought of in `src/proxy/framing_test.go` (Present). A corpus of frames captured from a second parser, rather than invented here, was never collected. Do not invent one to close this row. |

## Running them

```bash
# Everything that does not need the kernel
docker run --rm -v "$PWD:/work" -w /work f2a-dev python -m pytest tests -q -m "not privileged"

# The kernel mechanisms
docker run --rm --privileged --cgroupns=host -v /sys/fs/cgroup:/sys/fs/cgroup:rw \
  -v "$PWD:/work" -w /work f2a-dev python -m pytest tests -q

# The invariants, on their own, in milliseconds
docker run --rm -v "$PWD:/work" -w /work f2a-dev python tests/invariants/runner.py

# The enforcement point
cd src/proxy && go test ./...
```

## `F2A_ENV_ROOT`

Fixtures that need credentials read them through `F2A_ENV_ROOT`, the same convention the feature 001
harnesses use, and **exit non-zero when it is unset**. No fixture in this tree hardcodes a home
directory, and none prints a credential value — `src/contracts/secret.py` makes the second
structural rather than a review item.
