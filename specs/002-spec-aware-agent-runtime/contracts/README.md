# Phase 1 Contracts — Spec-Aware Agent Runtime

**Feature**: `002-spec-aware-agent-runtime` | **Date**: 2026-08-03 | **Phase**: 1 (`/speckit-plan`)

**Plan**: [`../plan.md`](../plan.md) · **Phase 0**: [`../research.md`](../research.md) ·
**Data model**: [`../data-model.md`](../data-model.md)

---

These are the interfaces v1 must not break without a MAJOR version bump (FR-034), and the ones
constitution Principle VII requires contract tests for. Each document states the contract, the
requirements it discharges, and the tests owed.

| Contract | What it fixes | Primary requirements |
|---|---|---|
| [`configuration.md`](./configuration.md) | how configuration reaches the runtime, what is required, and what fails loudly | FR-032, FR-033, FR-036, FR-043, FR-049, FR-050, FR-053 |
| [`egress-policy.md`](./egress-policy.md) | exactly what the single enforcement point accepts and denies, and how a denial is recorded | FR-008–FR-019, FR-021, FR-046, FR-050 |
| [`result-record.md`](./result-record.md) | the caller-visible verification contract | FR-022–FR-026, FR-045, FR-047, FR-052 |
| [`trace-record.md`](./trace-record.md) | span shape, and the pinning terms a measurement artifact must carry | FR-005, FR-006, FR-011, ~~FR-030~~ **FR-038**, FR-053 |
| [`artifact-versioning.md`](./artifact-versioning.md) | canonical form, content addressing, rollback | FR-027, FR-028, FR-034, FR-054, **FR-055** |

> **This index was audited against each contract's own header on 2026-08-03 and four of the five rows
> were wrong.** Three were *understatements* — a row naming fewer requirements than the contract
> claims is a stale summary and this column says "primary", so those are corrected quietly by
> widening. **The trace-record row was different in kind and is struck rather than widened**: it
> named **FR-030**, a drift requirement that says nothing about spans, so the row was not incomplete
> but wrong, and it was the index half of the same defect corrected inside
> [`trace-record.md`](./trace-record.md) that day. `artifact-versioning.md` gained **FR-055** in the
> same audit, for the same reason and by the same route — its canonical-form section had no
> requirement behind it either.

**Two properties are common to all five and are not restated in each.**

**Fail loudly, never silently.** Malformed or missing required configuration terminates startup with
a named reason (FR-033). No contract has a permissive fallback.

**Nothing presented as validated that is not.** Any configured value with no measurement behind it
carries FR-043's marking wherever it crosses an external surface — a report, an API response, the
operator UI. The four such values in v1 are enumerated in [`../plan.md`](../plan.md) Technical
Context.
