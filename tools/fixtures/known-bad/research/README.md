# Fixture research index

## Document catalog

| Document | Lines | Purpose |
|---|---:|---|
| [`01-fixture-metrics.md`](./01-fixture-metrics.md) | 14 | Count-and-rate pairs. |
| [`14-fixture-synthesis.md`](./14-fixture-synthesis.md) | 12 | Registers and tables. |

The same catalog written the other way, with the count inline instead of in a
column — the shape the skills roster uses, and the one that drifted unwatched:

- [`01-fixture-metrics.md`](./01-fixture-metrics.md) (~40 lines) — a hedge is
  still a claim, and this one is wrong by more than the tolerance.
- [`14-fixture-synthesis.md`](./14-fixture-synthesis.md) (64 lines) — wrong by
  one, which is the size that shipped. `catalog-line-count` carried
  `TOLERANCE = 2` while a catalog row claimed 804 lines for an 806-line
  document, and two is not greater than two. Every other planted drift in this
  fixture is at least 26 lines wide, so restoring that tolerance left the whole
  self-test passing; this row is what makes the tolerance itself testable.
