# Contract — Artifact Canonicalization, Versioning and Rollback

**Requirements**: FR-027, FR-028, FR-034, FR-054, **FR-055** *(added 2026-08-03 — see below; the
canonical-form section had no requirement behind it)*
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

~~Carried into [`../plan.md`](../plan.md)'s Constitution Check as a partial rejection of that deviation
record, and flagged for the owner as a narrowing the specification text should carry. The plan does
not edit `spec.md` during the plan phase.~~

> **Citation corrected 2026-08-03, and it is the same defect as the one corrected in
> [`trace-record.md`](./trace-record.md) on the same day: a contract whose central shape had no
> requirement behind it.** The struck paragraph was accurate when written and describes a state that
> has moved — the narrowing *was* carried back into the specification, as **FR-055**, measured by
> **SC-029**. The consequence while it stood was that **the canonical-form section above cited
> nothing**: FR-027 is the two-clocks requirement, FR-028 is source-change detection, FR-034 is the
> schema boundary and FR-054 requires artifacts be content-addressed — **none of the four says a word
> about canonical serialization**, which is this contract's title subject and its first section.
> FR-055 supplies it directly and is now cited above. The near-miss that made the gap invisible is
> the same one FR-054 created for trace-record: FR-054 requires content addressing, canonical form is
> a precondition of content addressing being stable, and a reader supplies the missing step without
> noticing it is missing.

## Addressing, refs and rollback

`Artifact` is immutable, keyed by `sha256` over the canonical payload, stored at `objects/<sha256>`.
`ArtifactRef` is `(deployment_id, kind) → content_hash` with retained history.

**Rollback is a ref move**, which is what makes FR-054's one-command restoration of ~~a previous~~
**the immediately prior** configuration true rather than aspirational. Nothing rewrites an artifact
in place.

**Rollback is an undo, and it is its own inverse** *(wording corrected 2026-08-03 — the owner
confirmed FR-054's toggle reading, and "a previous configuration" above read as a walk backwards
through history, which is a different operation from the one that ships)*. It moves the ref to the
version the artifact held before the change being undone. Performed twice in succession it returns
the ref to where the first one started; it does not step further back, and an artifact three versions
old is not reachable by repeating it. Retained history is what makes the prior version *findable*,
not a stack the operation pops. Consecutive duplicate addresses are skipped when the prior version is
located, because a republication of identical content is the same version and not a new one.

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
- Rollback restores ~~a previous~~ **the immediately prior** configuration in one operation and the
  restored deployment produces the same artifact hashes it produced before.
- Rollback is its own inverse: performed twice in succession it returns the artifact to the version
  the first one started from, rather than stepping a second time backwards through history.
- A `codegraph` schema-hash mismatch fails the analysis stage rather than emitting a drift signal.
