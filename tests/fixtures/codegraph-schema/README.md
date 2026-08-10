# `codegraph`'s schema, frozen at the pinned revision

`schema.sql` is a **byte-verbatim** copy of `src/db/schema.sql` from the
`codegraph` revision that `src/analysis/codegraph_pin.py` pins. It is 194 lines
and 8,509 bytes, and its SHA-256 is
`ba0c16b0b5e6b9e69850b4fd96ece0dd90f17d1d65d9885184d0a2a0c461f743`.

| | |
|---|---|
| Upstream | `@colbymchenry/codegraph`, MIT |
| Revision | `49c11fc2e0c02170742be8411e66a31af611f4b7` |
| `git describe` | `v1.5.0-7-g49c11fc` |
| `package.json` `version` | `1.5.0` — **seven commits behind the tree this came from** |
| Copied from | `examples/codegraph/src/db/schema.sql` |
| Copied on | 2026-08-10 |

## Why a copy exists at all

`examples/` is git-ignored, so upstream's own file is not in the repository and
a test cannot read it. Without this copy `CODEGRAPH_SCHEMA_SHA256` is 64
characters of hex that **no committed artifact can be used to re-derive**, and a
fabricated value is then indistinguishable from an observed one — which is the
exact failure the constant's `None` was protecting against before it was set.

With the copy, `tests/unit/test_codegraph_pin.py` builds a zero-row database
from this file and re-computes the digest. The constant stops being an opaque
assertion and becomes a claim a reviewer can check by reading 194 lines of SQL.

## What this fixture does *not* establish

**That this file is what upstream ships.** Verifying that is one command against
a tree this repository does not contain:

```
diff examples/codegraph/src/db/schema.sql tests/fixtures/codegraph-schema/schema.sql
```

The link from "upstream revision `49c11fc` ships this SQL" to "this SQL is in
`tests/fixtures/`" is a copy performed once, on the date above, and recorded
here. It is not re-checked by any test, and it cannot be: the only evidence
that would settle it is the git-ignored tree itself.

## Why it may be used in place of a real index

Measured 2026-08-10, and the whole reason the fixture works: **a zero-row
database built from this file digests identically to a 149 MB index of
`adk-python` built by the pinned revision** — 1,867 files, 48,154 nodes,
149,714 edges, `044054b3962ba8315b2e7b2243bbfc1e9ec954cfa6b3b30db11f8eb6cb3f01f4`
either way. That is `schema_digest()`'s central claim — only the schema
participates, never a row — holding against upstream's real schema rather than
against a synthetic stand-in.

The equality was reproduced across three SQLite builds: node's `better-sqlite3`
(which wrote the index), the macOS `sqlite3` CLI at 3.51.0, and CPython's
`sqlite3` at 3.53.3 (which is what the test uses). `sqlite_master.sql` stores
the `CREATE` statement as written, so the digest is a property of this DDL text
and not of the engine that executed it.

## Updating it

Both halves of the pin and this fixture move together, in one commit:

1. `rsync` the new `codegraph` into a scratch tree, `npm install && npm run build`.
2. `node codegraph/dist/bin/codegraph.js init ./<some-repo>`.
3. `python -m src.analysis.codegraph_pin <that>/.codegraph/codegraph.db`.
4. Copy the new `src/db/schema.sql` here; update the table above.
5. Set `CODEGRAPH_VERSION` and `CODEGRAPH_SCHEMA_SHA256` from steps 2–3.

Step 3 is not optional and step 4 is not a substitute for it. Deriving the
digest from this file alone would pin the schema this repository *believes*
upstream has, which is the assertion-against-nothing the constant refuses.
