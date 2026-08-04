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

# The pinned release. Bumping this line and the hash below is the only
# supported way to move to a new `codegraph`, and the two must move together.
CODEGRAPH_VERSION = "0.5.4"

# SHA-256 over the canonical schema digest defined by `schema_digest()`.
#
# UNSET on purpose. Feature 001 measured `codegraph` on one small repository
# (U-21) and this pass did not run it, so there is no observed digest to record
# and inventing one would make the assertion pass against nothing. `verify()`
# fails closed while it is None, which is the correct state for an assertion
# whose expected value has never been observed: the analysis stage refuses to
# start rather than reading an unverified schema.
#
# To set it: run `python3 -m src.analysis.codegraph_pin <path-to-codegraph.db>`
# against the artifact produced by the pinned version, and paste the digest.
CODEGRAPH_SCHEMA_SHA256: str | None = None


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
