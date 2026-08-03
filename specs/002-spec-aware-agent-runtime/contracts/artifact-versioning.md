# Contract — Artifact Canonicalization, Versioning and Rollback

**Requirements**: FR-027, FR-028, FR-034, FR-054
**Constitution**: Principle VII (determinism clause — **rejected in part** in
[`../plan.md`](../plan.md)), Principle VIII

---

## Canonical form

Every artifact FR-054 enumerates is serialized by **one** canonical serializer:

- keys sorted, deterministic collation;
- fixed numeric formatting, no locale dependence;
- `LF` newlines, `UTF-8`, no byte-order mark;
- **no timestamp, path, hostname or absolute filesystem location inside the hashed payload** — those
  live in an envelope beside the hash, never under it.

## Why this is a requirement and not hygiene

The specification's Principle VII deviation record says the byte-stability clause "has no subject"
because v1 emits no artifacts. That is true of *emitted agent systems* and untrue of v1's own
artifacts: FR-054 names eight kinds and requires them content-addressed.

Content addressing over a non-canonical serialization yields a different hash on every re-analysis of
identical input. **A changed hash on the source-derived artifact is exactly what FR-028 reads as
source drift.** So a non-canonical serializer is a false-alarm generator pointed at the one v1
capability that ships with no measured false-alarm rate.

Carried into [`../plan.md`](../plan.md)'s Constitution Check as a partial rejection of that deviation
record, and flagged for the owner as a narrowing the specification text should carry. The plan does
not edit `spec.md` during the plan phase.

## Addressing, refs and rollback

`Artifact` is immutable, keyed by `sha256` over the canonical payload, stored at `objects/<sha256>`.
`ArtifactRef` is `(deployment_id, kind) → content_hash` with retained history.

**Rollback is a ref move**, which is what makes FR-054's one-command restoration of a previous
configuration true rather than aspirational. Nothing rewrites an artifact in place.

## Two clocks, versioned independently

FR-027 and **OD-06**. The source-derived artifacts and the served-operation set carry **independent**
versions, because a shared version cannot express that one changed and the other did not — which is
the whole content of drift.

## Schema versioning

Every artifact carries a `schema_version`. A breaking change to a consumed or produced schema is a
MAJOR bump with a migration path (FR-034, constitution Principle VIII). v1 both consumes and produces
schema'd artifacts from the first commit, so migrations exist from the first commit rather than being
retrofitted.

`codegraph`'s schema is **asserted by hash in CI** and the analysis stage fails loudly on a mismatch
(**U-04**), so a changed upstream schema is never read as changed source.

## Tests owed

- **Determinism**: analyse one fixture twice, compare **bytes** — not hashes, since comparing hashes
  would hide a serializer stable only within a process.
- Re-analysing unchanged input produces **no** source-clock drift signal.
- Every artifact kind round-trips through the canonical serializer unchanged.
- Rollback restores a previous configuration in one operation and the restored deployment produces
  the same artifact hashes it produced before.
- A `codegraph` schema-hash mismatch fails the analysis stage rather than emitting a drift signal.
