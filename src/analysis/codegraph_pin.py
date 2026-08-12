"""T004 — pin `codegraph` and assert its schema hash before reading it.

**U-04**: `codegraph`'s SQLite artifact schema is not covered by any stability
guarantee across releases. **D-14** decided the analysis layer reads that
artifact directly rather than going through the TypeScript API, so a schema
change upstream arrives as *changed rows in a table we query* and nothing
announces it.

The failure this module prevents is specific and it is worse than a crash: a
renamed column or a changed table set makes the derived source artifact hash
differently, and FR-028 reads a changed source-artifact hash as **source
drift**. An upstream release would therefore be reported to the operator as
their own code having moved. So a mismatch fails the analysis stage loudly
rather than producing a drift signal.

Nothing here invokes `codegraph`; T119 does that. This module owns the pin and
the assertion, which is all Phase 1 owes.
"""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from pathlib import Path

# The pinned ~~release~~ **revision**. Bumping this line and the hash below is
# the only supported way to move to a new `codegraph`, and the two must move
# together.
#
# **Struck 2026-08-10: this was `"0.5.4"`, and there is no such release.** The
# string occurred at exactly one site tree-wide — its own assignment — and named
# a version nothing in this repository had ever seen.
#
# What replaced it is a *revision*, not a release, and the string says so
# itself rather than relying on this comment. The vendored tree under
# `examples/codegraph` is seven commits past its last tag, so no published
# artifact corresponds to it: `npm install @colbymchenry/codegraph@1.5.0` gets
# different code, and a digest taken from it would not match. The disclosure is
# in the value because the value is what appears in `verify()`'s error message,
# which a reader reaches without ever seeing this comment.
CODEGRAPH_VERSION = (
    "git 49c11fc2e0c02170742be8411e66a31af611f4b7 "
    "(describe v1.5.0-7-g49c11fc; unreleased revision, not an npm version)"
)

# SHA-256 over the canonical schema digest defined by `schema_digest()`.
#
# **Struck 2026-08-10: this was `None`, and the reasoning below it was true when
# it was written.** It read: *no observed digest exists, and inventing one would
# make the assertion pass against nothing.* That is no longer the state — a
# digest has been observed — so the explanation is superseded rather than
# deleted, because it is also the standard the value below has to meet.
#
# OBSERVED, not chosen. Provenance, which is the whole difference between this
# value and an invented one:
#
#   revision  : git 49c11fc2e0c02170742be8411e66a31af611f4b7 (v1.5.0-7-g49c11fc)
#   built by  : node v22.20.0, `npm install && npm run build`, in a scratch
#               tree outside this repository ~~(`examples/` is never built in
#               place)~~ **(struck 2026-08-11 — the reading itself was taken
#               in a scratch tree and that half stands; the parenthetical was
#               a standing rule about the vendored tree and it no longer
#               holds. `examples/codegraph` was built in place on 2026-08-11,
#               which is what made the re-verification below possible.)**
#   indexed   : a copy of `examples/adk-python` — 1,867 files, 48,154 nodes,
#               149,714 edges, a 149,282,816-byte `.codegraph/codegraph.db`
#   command   : `python -m src.analysis.codegraph_pin <that>/.codegraph/codegraph.db`
#   on        : 2026-08-10, macOS 26.2 arm64
#   recipe    : specs/001-discovery-validation/harness/recall-adk-fastapi/run.sh
#
# **The controls, because a single reading is not a measurement.** The same
# build indexed three repositories of different size and language mix —
# `adk-python` (1,867 files), `labs-OO-Agents` (951, and the only one carrying
# TypeScript), `claude-agent-sdk-python` (109) — and produced this one digest
# for all three. `adk-python` was then indexed a second time from an
# independently rebuilt `codegraph` in a separate scratch tree: the two database
# files differ byte-for-byte (`md5` 189682a7… against 1c19a705…) and digest the
# same. So the value is a property of upstream's schema and not of the analysed
# repository, which is exactly what `schema_digest()` claims and what makes the
# pin able to work at all.
#
# A zero-row database built from upstream's own `src/db/schema.sql` digests to
# this same value, which is why `tests/fixtures/codegraph-schema/` can exist and
# why the constant is re-derivable offline. See that directory's README for what
# that does and does not establish.
#
# **Re-verified 2026-08-11, end to end, and it is a second measurement rather
# than a re-reading of the first.** The one link the fixture's README and
# `tests/unit/test_codegraph_pin.py` both decline to claim — that the committed
# SQL is what upstream ships — was measured again, against a `codegraph` built
# **in place** under `examples/`:
#
#   revision  : git 49c11fc2e0c02170742be8411e66a31af611f4b7, `git describe`
#               v1.5.0-7-g49c11fc — unmoved from 2026-08-10. Building in place
#               dirtied neither repository: the vendored tree is its own git
#               repository and reports 0 dirty entries, its `.gitignore`
#               covering `node_modules/` and `dist/`, and the outer
#               repository ignores `examples/` at `.gitignore:156`
#   built by  : node v22.20.0, `npm install && npm run build`, in place in
#               `examples/codegraph` (an owner action, not a gate's)
#   identical : the committed fixture, `examples/codegraph/src/db/schema.sql`
#               and the freshly built `examples/codegraph/dist/db/schema.sql`
#               are byte-identical — md5 99255f39133266fb690fe361300d51a7,
#               194 lines, 8,509 bytes, `diff -q` silent on both pairs
#   indexed   : `node examples/codegraph/dist/bin/codegraph.js init .` over an
#               rsynced copy of `examples/labs-OO-Agents` (`.git` excluded,
#               1,328 files in the tree, of which `codegraph` reports indexing
#               951), in a scratch directory under /tmp — 25,880 nodes,
#               72,239 edges, a 72,695,808-byte `.codegraph/codegraph.db`
#   command   : `verify()` on that artifact, and on a zero-row database built
#               from that same `dist/db/schema.sql`
#   on        : 2026-08-11, Darwin 25.2.0 arm64, euid 501, CPython 3.12.11
#               with `sqlite3` at SQLite 3.53.3
#
# Twelve tables and this constant's value from both databases, and `verify()`
# passed against both.
#
# **The live index is the load-bearing half of that.** A database built from
# the committed fixture, digested and compared against the constant beside it,
# is in the end a file read back to itself; the `init` run is the pin holding
# against an artifact `codegraph` produced from its own source at this
# revision, which is the thing the fixture stands in for.
#
# **What it does not change, because a reader must not take it for coverage.**
# `examples/` is git-ignored, so **nothing in the gate set re-checks any of
# the above** — not a test, not `check_corpus.py`, not a CI job — and that is
# by design rather than an omission: the evidence that would settle it is
# deliberately absent from the repository. A green suite is not evidence that
# the pinned revision still produces this schema. What has changed is that the
# link now rests on two dated measurements instead of one; what has not is
# that it goes stale silently between them.
#
# To move it: run `python -m src.analysis.codegraph_pin <path-to-codegraph.db>`
# against an artifact produced by the new revision, and record the provenance
# above alongside the digest. A digest with no provenance is indistinguishable
# from an invented one.
CODEGRAPH_SCHEMA_SHA256: str | None = (
    "044054b3962ba8315b2e7b2243bbfc1e9ec954cfa6b3b30db11f8eb6cb3f01f4"
)


class CodegraphPinError(RuntimeError):
    """The analysis stage must not proceed. Never a drift signal."""


@dataclass(frozen=True)
class SchemaDigest:
    version: str
    digest: str
    table_count: int


def schema_digest(db_path: str | Path) -> SchemaDigest:
    """A stable digest over `codegraph`'s SQLite schema.

    Only the schema participates, never a row: the digest must change when
    upstream renames a column and must not change when the analysed repository
    does. `sqlite_master.sql` is normalised for whitespace so that a formatting
    change upstream is not read as a schema change.
    """
    path = Path(db_path)
    if not path.is_file():
        raise CodegraphPinError(f"codegraph artifact not found: {path}")

    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            "SELECT type, name, sql FROM sqlite_master "
            "WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%' "
            "ORDER BY type, name"
        ).fetchall()
    finally:
        conn.close()

    h = hashlib.sha256()
    tables = 0
    for kind, name, sql in rows:
        if kind == "table":
            tables += 1
        normalised = " ".join(str(sql).split())
        h.update(f"{kind}\x1f{name}\x1f{normalised}\x1e".encode())
    return SchemaDigest(CODEGRAPH_VERSION, h.hexdigest(), tables)


def verify(db_path: str | Path) -> SchemaDigest:
    """Assert the pinned schema, or fail the analysis stage loudly."""
    found = schema_digest(db_path)
    if CODEGRAPH_SCHEMA_SHA256 is None:
        raise CodegraphPinError(
            "codegraph schema hash is UNSET, so the pin cannot be asserted.\n"
            f"  observed digest for version {CODEGRAPH_VERSION}: {found.digest}\n"
            "  Record it in CODEGRAPH_SCHEMA_SHA256 after confirming the "
            "artifact came from the pinned version.\n"
            "  The analysis stage fails closed rather than reading an "
            "unverified schema (U-04)."
        )
    if found.digest != CODEGRAPH_SCHEMA_SHA256:
        raise CodegraphPinError(
            "codegraph schema hash mismatch — the analysis stage stops here.\n"
            f"  pinned version : {CODEGRAPH_VERSION}\n"
            f"  expected digest: {CODEGRAPH_SCHEMA_SHA256}\n"
            f"  observed digest: {found.digest}\n"
            "  This is an upstream schema change, NOT source drift. It must "
            "never be emitted as a drift signal (U-04, T136)."
        )
    return found


if __name__ == "__main__":  # pragma: no cover - operator utility
    import sys

    if len(sys.argv) != 2:
        sys.exit("usage: python3 -m src.analysis.codegraph_pin <codegraph.db>")
    d = schema_digest(sys.argv[1])
    print(f"version={d.version} tables={d.table_count} digest={d.digest}")
