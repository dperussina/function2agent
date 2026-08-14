# Constitution re-check — T204

This is the checkable record, not an essay.
`tests/contract/test_constitution_recheck.py` walks this file. Marking an
unmet principle as held, inventing a ninth principle, or dropping one of
the eight fails that test.

Read against [`.specify/memory/constitution.md`](../.specify/memory/constitution.md)
**v1.3.0**, after implementation, on current HEAD. The constitution is not
amended here. There is no ninth principle. The plan's Phase-1 Constitution
Check is the prior gate; this file is the post-implementation re-check.

Dispositions are exactly three: **Held**, **Held with a named deviation**,
**Unmet**. An unmet residual is not quietly marked held.

## Per-principle disposition

| # | Principle | Disposition |
| --- | --- | --- |
| I | Contract-Derived Verification (NON-NEGOTIABLE) | Held |
| II | Topology Encodes Protocol | Held with a named deviation |
| III | Default to the Loop | Held with a named deviation |
| IV | Structural Safety Boundaries (NON-NEGOTIABLE) | Held |
| V | Two-Tier Provider Abstraction | Held |
| VI | Observability Is a Prerequisite | Unmet |
| VII | Test-First and Fixture-Backed (NON-NEGOTIABLE) | Held |
| VIII | Versioned Artifacts, Earned Complexity | Held |

### I. Contract-Derived Verification — Held

v1 derivation is static (T-13). FR-023 / T214: a run obtains a reported
quantity from the answer path, calls `verify_quantity`, and joins what
comes back to a caller-visible `Result`. That path exists; it is not
only constructible from a type.

**FR-052's judge boundary is preserved.** The shadow judge writes
`judge_verdict`; the success-path construction has no read access to
that table. Import-graph tests keep the judge module off the result
record. Where a model must judge, it is not the default or only critic.

Residual, named, not a failure of the hold: FR-040's third gate still
needs human labels that do not exist. **E13 never ran.** T058's
transport half is PARTIAL and is Principle V's residual, not this
principle's.

### II. Topology Encodes Protocol — Held with a named deviation

**Named deviation (already accepted):** v1 emits no graph, no nodes, and
no routing. OD-09 deferred synthesis to v2. The emission clause has no
subject. The plan's Constitution Check accepted this deviation; this
re-check does not reopen it.

The second paragraph — versioned, machine-checkable invariants with
tests on every change — was adopted in v1 and is not part of the
deviation.

### III. Default to the Loop — Held with a named deviation

**Named deviation (already accepted):** v1 promotes no functions and
emits no node graph, so the "default emission for a promoted function"
clause has no subject. What shipped is one agent and one loop. OD-15
dropped ADK; sitting a single loop on a graph tier would have been the
failure the principle names.

### IV. Structural Safety Boundaries — Held

The six bullets have mechanisms: per-session mount namespace (FR-048);
cgroup v2 bounds written before `execve` (FR-049); mandatory
re-originating proxy with the four egress terms (OD-12, FR-014–FR-019);
no credential outliving the session (FR-050); effect tier resolved per
call at a blocking interception point; HTTP/SSE surface bound (T215,
OD-36 discharged — `main.py` constructs a `Registry`, admits a
`SessionView`, and calls `build_server`; the superseded report-and-exit
sentence is the planted-off branch only).

**T172:** every supported-platform surface states Linux only, no
degraded mode (OD-17).

Residuals, named, not a failure of the hold:

- **U-44 is open.** The egress guarantee is conditional on an unmeasured
  property of the target. This re-check does not close it.
- **OD-17's kernel floor is 5.14, DERIVED NOT TESTED.** Every run to
  date was on 6.12 or 6.17. **T205 is deferred** by owner decision and
  stays `[ ]`. The caveat is not relaxed.

### V. Two-Tier Provider Abstraction — Held

Thin driver per vendor SDK behind one interface (OD-16). Opaque
`provider_state` is first-class on the turn record and is not merged
across providers.

**Named residual: T058 is PARTIAL.** The translation half is
implemented and cassette-exercised. The transport half is not: no
vendor SDK is in `requirements.lock`; `ProviderDriver.call` raises
`TransportUnavailableError` (FR-021). Adding the four SDKs is
outstanding. The hold is on the abstraction's shape, not on a live
round-trip through a vendor package.

### VI. Observability Is a Prerequisite — Unmet

T193 scored SC-012 over a named failed-session fixture: kind, position,
typed outcome, terminal, and `rule_id` on a denial, from stored spans
alone. T194 mapped FR-038's node terms onto turn and step and recorded
the terms with no v1 subject. Those two are done.

FR-038 still requires an explicit retry-versus-repair distinction.
**T195 recorded that distinction as undefined in this specification.**
T194 points at that register and does not define either term.
Recording the gap is not satisfying the field.

v1.3.0 made the unit tier-relative (span, not node). That amendment
removed an unsatisfiable MUST NOT; it did not fill the field. This
principle is **Unmet**. The residual is the undefined retry-versus-repair
distinction. It is not marked Held.

### VII. Test-First and Fixture-Backed — Held

Analyzer fixtures with asserted expected output exist (FR-053).
Integration-surface contract tests exist (FR-033, T215's bind).
Canonical serialization and determinism tests exist (FR-055, SC-029).
Cassette-backed core-path replay exists (T170).

Residuals, named: **T196** (quickstart scenarios end to end) is open.
**T200** (fixture-inventory reconciliation) is open. **T205** (kernel
matrix) is deferred. None of those quietly convert the hold into a
claim that every polish task is done.

### VIII. Versioned Artifacts, Earned Complexity — Held

FR-054 versions and content-addresses the artifacts v1 produces.
Rollback is one command. New layers were justified against named
failures (enforcement point in Go for Q-01; syscall supervisor for
FR-048's recording clause; turn journal for U-30). Unearned structure
was rejected (durable-execution engine, graph framework, PostgreSQL).

**OD-36 is discharged (T215).** The runtime binds a serving surface.
The superseded report-and-exit sentence is the planted-off branch only.

## Residuals this re-check does not close

U-44 remains open. U-21 remains open. T205 remains deferred. E13 never
ran. T196, T198, T200 remain open. T058 transport remains PARTIAL.
