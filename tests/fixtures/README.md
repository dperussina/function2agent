# Committed fixtures — FR-053's discipline, and the inventory each capability owes

**Requirement**: FR-053. **Task**: T008.

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

`session_conformance.sqlite3` is the one committed **binary** fixture, and it is committed on
purpose: it is a session table written by the supervisor's own writer and read by the enforcement
point's own read-only store, so it holds the two sides to an agreement that nothing in either
language enforces. Regenerate it with `python tests/fixtures/session_conformance.py` — and expect
`src/proxy/conformance_test.go` to fail until the Go side is brought back into agreement, which is
the entire point of it.

The fixture's fifth row, `sess-terminated-live-lease`, is written with raw SQL rather than through
`SessionTable.terminate()`, because `terminate()` also zeroes the lease. Without a row that is
`TERMINATED` while its lease is still live, the fixture cannot tell a state check from an expiry
check, and an enforcement point that checked only expiry would pass every other row in it. The
first version of this fixture did not have that row and did not notice.

Owed, and named here so the absence is visible rather than inferred:

| Fixture | Requirement | Why it is not here yet |
| --- | --- | --- |
| Reference-application overhead | **Q-09**, T101 | The reference application does not exist. `tests/batteries/test_seccomp_overhead.py` measures three proxy workloads and records that it does **not** discharge this. |
| Concurrent-writer probe | T-06, T050 | Finding 006 did not test its session service under concurrent writers, and T-06's narrowing records that v1's store has **no** observed substrate. One process with one lock is not that measurement. |
| Framing-ambiguity corpus | **Q-01** | The named failure Q-01 buys a second language to prevent. `src/proxy/framing_test.go` covers the cases we thought of; a corpus is a different artefact. |
| Drift-scheduler egress path | FR-046, OD-12 | The scheduler does not exist. When it does, its re-fetch must traverse the same enforcement point or FR-014 is true of the sandbox and false of the system. |
| Resume across a crash boundary | FR-007 | Finding 006 measured resume over a substrate v1 does not ship, so **v1 has no measured resume**. |

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
