"""T004 — the `codegraph` pin's own floors.

~~**Every fixture here is synthetic and constructed in the test.**~~ **Struck
2026-08-10 — true when written, and half of it still is.** The reasoning was
that `codegraph` is a git-ignored vendored TypeScript tree with no installed
build, so a fixture derived from a real artifact would make this file's
population depend on a tool nobody running the suite can obtain, and would tie
the tests to the digest **U-04** was open about. The first ground held; the
second is spent, because the digest has now been observed.

**There are two fixture populations now, and the difference between them is the
point.** The synthetic schemas below still carry every property test — they
resemble `codegraph`'s shape, claim nothing about it, and what is under test
there is `schema_digest()` and `verify()` rather than upstream's table set. The
second population is `tests/fixtures/codegraph-schema/schema.sql`, a verbatim
copy of upstream's own DDL at the pinned revision, from which a **zero-row**
database is built in the test. No index and no artifact is involved: the whole
reason a 8.5 KB file can stand in for a 149 MB one is the property this module
is testing, that only the schema participates in the digest.

**Nothing here is gated on a platform, a kernel or a privilege.** The only
facilities used are `sqlite3` and a temporary directory, so every assertion is
expected to hold identically on Darwin and on Linux.

Each refusal is matched against **the wording of the mechanism it is aimed at**.
The mismatch arm in particular asserts the error says *upstream schema change*
and *not source drift*: FR-028 reads a changed source-artifact hash as drift, so
a mismatch phrased as drift would report an upstream release to the operator as
their own code having moved, which is the failure the module exists to prevent.
"""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest

from src.analysis import codegraph_pin
from src.analysis.codegraph_pin import (
    CODEGRAPH_SCHEMA_SHA256,
    CODEGRAPH_VERSION,
    CodegraphPinError,
    schema_digest,
    verify,
)

# A synthetic stand-in for the artifact's shape. Two tables and an index, which
# is the smallest schema that can exercise the table count, the ordering and the
# internal-table exclusion at once.
NODES_AND_EDGES = """
CREATE TABLE nodes( id INTEGER PRIMARY KEY, name TEXT, kind TEXT );
CREATE TABLE edges( src INTEGER, dst INTEGER, kind TEXT );
CREATE INDEX idx_nodes_name ON nodes(name);
"""

# Upstream's own DDL at the pinned revision. See that directory's README for
# where it came from and for the one link in the chain it does not establish.
PINNED_SCHEMA_SQL = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "codegraph-schema"
    / "schema.sql"
)


def a_db(tmp_path, script, name="codegraph.db"):
    """Build a database from `script` and return its path."""
    path = tmp_path / name
    conn = sqlite3.connect(path)
    try:
        conn.executescript(script)
        conn.commit()
    finally:
        conn.close()
    return path


def schema_rows(path):
    """Every `sqlite_master` row, unfiltered — the population the digest reads
    from, so a test can assert its own fixture actually contains what it claims."""
    conn = sqlite3.connect(path)
    try:
        return conn.execute("SELECT type, name, sql FROM sqlite_master").fetchall()
    finally:
        conn.close()


def table_names(path):
    conn = sqlite3.connect(path)
    try:
        return [
            name
            for (name,) in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        ]
    finally:
        conn.close()


def a_db_from_the_pinned_schema(tmp_path=None):
    """A **zero-row** database built from upstream's own DDL at the pinned
    revision.

    Not an index and not an artifact: `PINNED_SCHEMA_SQL` is 194 lines of
    committed `CREATE` statements, and nothing is ever inserted here unless a
    test does it deliberately. A real index of the same revision is 149 MB and
    could not be committed; it does not need to be, because the digest under
    test reads `sqlite_master` and nothing else.
    """
    directory = Path(tempfile.mkdtemp()) if tmp_path is None else tmp_path
    return a_db(directory, PINNED_SCHEMA_SQL.read_text(), name="pinned-schema.db")


def insert_rows(path, count):
    conn = sqlite3.connect(path)
    try:
        conn.executemany(
            "INSERT INTO nodes(name, kind) VALUES (?, ?)",
            [(f"symbol_{i}", "function") for i in range(count)],
        )
        conn.commit()
        return conn.execute("SELECT count(*) FROM nodes").fetchone()[0]
    finally:
        conn.close()


# --- the whole point: the digest is a property of the schema, not the repo ---


def test_the_digest_does_not_move_when_rows_are_inserted(tmp_path):
    """The analysed repository changing must not read as upstream changing.

    The row count is asserted to have actually moved, because a fixture whose
    insert silently did nothing would satisfy the equality for the wrong reason.
    """
    path = a_db(tmp_path, NODES_AND_EDGES)
    before = schema_digest(path)
    assert insert_rows(path, 0) == 0

    assert insert_rows(path, 40) == 40
    after = schema_digest(path)

    assert after.digest == before.digest
    assert after.table_count == before.table_count == 2


def test_the_digest_moves_when_a_column_is_renamed(tmp_path):
    """The failure the digest exists to catch. A renamed column changes which
    rows the analysis layer reads, and nothing upstream announces it."""
    original = a_db(tmp_path, NODES_AND_EDGES, name="original.db")
    renamed = a_db(
        tmp_path,
        NODES_AND_EDGES.replace("kind TEXT );", "node_kind TEXT );", 1),
        name="renamed.db",
    )

    assert schema_digest(renamed).digest != schema_digest(original).digest


def test_the_digest_moves_when_the_table_set_changes(tmp_path):
    original = a_db(tmp_path, NODES_AND_EDGES, name="original.db")
    widened = a_db(
        tmp_path,
        NODES_AND_EDGES + "CREATE TABLE files( path TEXT, content_hash TEXT );",
        name="widened.db",
    )

    assert schema_digest(widened).digest != schema_digest(original).digest
    assert schema_digest(widened).table_count == 3
    assert schema_digest(original).table_count == 2


def test_a_reformatted_create_table_does_not_move_the_digest(tmp_path):
    """A formatting change upstream is not a schema change.

    The scope of the normalisation is exactly a **run** of whitespace, and this
    fixture is written to that scope rather than past it: both forms carry
    whitespace in the same places and differ only in how much. A reformat that
    introduces whitespace where there was none — a newline after `(` — does move
    the digest, and this test does not claim otherwise.
    """
    compact = a_db(
        tmp_path,
        "CREATE TABLE nodes( id INTEGER PRIMARY KEY, name TEXT );",
        name="compact.db",
    )
    reformatted = a_db(
        tmp_path,
        "CREATE TABLE nodes(\n    id   INTEGER    PRIMARY KEY,\n    name TEXT\n);",
        name="reformatted.db",
    )

    # The floor: the stored SQL really does differ, so the equality below is
    # the normalisation working rather than two identical inputs agreeing.
    assert schema_rows(compact)[0][2] != schema_rows(reformatted)[0][2]

    assert schema_digest(reformatted).digest == schema_digest(compact).digest


def test_the_digest_does_not_depend_on_the_order_the_schema_was_created_in(tmp_path):
    """`sqlite_master` is in creation order, so without the sort two databases
    carrying one schema digest differently — a false upstream-change signal."""
    one_way = a_db(
        tmp_path,
        "CREATE TABLE nodes( id INTEGER );\nCREATE TABLE edges( src INTEGER );",
        name="one_way.db",
    )
    other_way = a_db(
        tmp_path,
        "CREATE TABLE edges( src INTEGER );\nCREATE TABLE nodes( id INTEGER );",
        name="other_way.db",
    )

    # The floor: the two fixtures really are in opposite creation order.
    assert [name for _, name, _ in schema_rows(one_way)] == ["nodes", "edges"]
    assert [name for _, name, _ in schema_rows(other_way)] == ["edges", "nodes"]

    assert schema_digest(other_way).digest == schema_digest(one_way).digest


def test_sqlite_internal_tables_are_excluded_from_the_digest(tmp_path):
    """`ANALYZE` adds `sqlite_stat*` tables, which are a property of the data
    rather than of upstream's schema. They carry non-null SQL, so the name
    filter is the only thing excluding them."""
    path = a_db(tmp_path, NODES_AND_EDGES)
    insert_rows(path, 10)
    before = schema_digest(path)

    conn = sqlite3.connect(path)
    try:
        conn.execute("ANALYZE")
        conn.commit()
    finally:
        conn.close()

    # The floor: at least one `sqlite_`-prefixed table now exists AND carries
    # SQL, so it is reachable by everything except the name filter. How many
    # appear is a build option (`SQLITE_ENABLE_STAT4`), so the count is not
    # asserted — that would be an expectation about the host.
    internal = [
        name
        for _, name, sql in schema_rows(path)
        if name.startswith("sqlite_") and sql is not None
    ]
    assert internal, "ANALYZE produced no sqlite_ table, so nothing is excluded here"

    assert schema_digest(path).digest == before.digest


def test_the_digest_carries_the_pinned_version(tmp_path):
    path = a_db(tmp_path, NODES_AND_EDGES)
    assert schema_digest(path).version == CODEGRAPH_VERSION


# --- verify(): the assertion, and both directions it fails in ---------------


def test_the_pinned_digest_is_re_derived_from_the_pinned_revisions_own_schema():
    """~~`test_the_pinned_hash_is_unset_because_no_digest_has_ever_been_observed`~~
    **superseded 2026-08-10 — the digest was observed, so the guard changed job
    rather than being retired.**

    The retired test asserted `CODEGRAPH_SCHEMA_SHA256 is None` and existed to
    fail the moment anyone fabricated a hash. That was the strongest available
    guard while no digest existed. It cannot survive the digest existing, and
    the two obvious replacements are both worse than nothing:

    - **Deleting it** leaves the constant with no guard at all, which is the
      state the `None` was invented to avoid.
    - **Asserting the literal string** is a change-detector. An editor who
      fabricates a digest satisfies it by pasting the same fabrication on both
      sides, and it would read to a later reviewer as verification.

    So this asserts the one thing that is *derivable from committed evidence*:
    the constant equals the digest of a database built from upstream's own DDL
    at the pinned revision. **A fabricated constant cannot satisfy this**, because
    satisfying it means producing 194 lines of SQL that digest to the fabrication,
    and the only tractable way to do that is to copy the real schema and compute
    the real digest — which is the honest procedure.

    **What it does not verify, stated plainly rather than left to be assumed.**
    It does not verify that the committed SQL is what upstream ships. Nothing
    offline can: `examples/` is git-ignored, so the only evidence that would
    settle it is absent from the repository by design. That link was established
    once, by measurement, on 2026-08-10 — a real index of `adk-python` built by
    this revision digested to this same value — and it is recorded in the
    constant's provenance block and in the fixture's README, not here. **Nothing
    in this file re-runs `codegraph`, and a green run of it is not evidence that
    the pinned revision still produces this schema.** Only re-running the recipe
    in `specs/001-discovery-validation/harness/recall-adk-fastapi/run.sh` is.
    """
    built = a_db_from_the_pinned_schema()

    # The floor, and it is not decoration. This test's whole weight rests on the
    # fixture actually being upstream's schema; a truncated or empty file would
    # otherwise fail with a digest mismatch that reads like an upstream change.
    found = schema_digest(built)
    assert found.table_count == 12, (
        f"the pinned schema built {found.table_count} tables, not 12 — the "
        "fixture is not upstream's schema, so the equality below would be "
        "comparing against the wrong thing"
    )
    assert {"nodes", "edges", "files"} <= set(table_names(built))

    assert found.digest == CODEGRAPH_SCHEMA_SHA256


def test_the_pinned_version_names_a_revision_that_cannot_be_installed():
    """The version and the digest move together, and only one of them is a hash.

    A digest is self-describing; a version string is not, and `CODEGRAPH_VERSION`
    appears in `verify()`'s mismatch message where a reader reaches it without
    ever seeing the comment above the constant. The vendored tree is seven
    commits past its last tag, so a string that reads as a release invites
    exactly the wrong repair — installing `1.5.0`, getting different code, and
    finding a digest that does not match with nothing explaining why.

    This asserts the disclosure is *in the value*, on the same principle as the
    line-local rule `dry-run-verdict` enforces on the corpus: a caveat somewhere
    else in the file does not travel with the string.
    """
    assert "49c11fc2e0c02170742be8411e66a31af611f4b7" in CODEGRAPH_VERSION
    assert "not an npm version" in CODEGRAPH_VERSION

    # A bare release number would be the specific mistake. `1.5.0` may appear —
    # it is what `package.json` says — but never as the whole of it.
    assert CODEGRAPH_VERSION.strip() != "1.5.0"


def test_verify_accepts_the_pinned_revisions_schema_with_nothing_monkeypatched():
    """The accepting path against the value this module actually ships.

    Every other `verify()` arm substitutes the constant, so all of them would
    pass with a shipped constant that matches no real schema at all. This one
    runs the assertion as an operator gets it: the committed digest, upstream's
    committed DDL, and no patching.
    """
    accepted = verify(a_db_from_the_pinned_schema())

    assert accepted.digest == CODEGRAPH_SCHEMA_SHA256
    assert accepted.version == CODEGRAPH_VERSION
    assert accepted.table_count == 12


def test_rows_in_upstreams_real_schema_do_not_move_the_pinned_digest(tmp_path):
    """Row-independence against upstream's schema rather than a stand-in.

    The synthetic arm above proves the property on two tables and an index.
    Upstream's schema is 12 tables ~~including five FTS5 shadow tables~~
    **— 7 ordinary, the `nodes_fts` virtual table itself, and 4 FTS5 shadow
    tables —** and three triggers that fire on every `nodes` insert, and that
    is a materially different thing to be row-independent about — an insert
    here writes into other tables by itself. `ANALYZE` is run too, because it
    creates `sqlite_stat*` tables and those are a property of the data.

    **Struck 2026-08-10 — the decomposition, never the 12, which is what the
    assertions above check and is correct.** `nodes_fts` appears in
    `sqlite_master` with `type='table'` and its own `CREATE VIRTUAL TABLE`
    text, so it counts in its own right rather than as one of its own shadows;
    and the shadow set is four — `_config`, `_data`, `_docsize`, `_idx` — with
    no `_content`, because the declaration carries `content='nodes'` and SQLite
    materialises no content shadow for an external-content FTS5 table.

    **The 12 is the count `schema_digest()`'s filter leaves, not the number of
    `type='table'` rows, which is 13.** `AUTOINCREMENT` on `edges` and
    `unresolved_refs` also creates `sqlite_sequence`, which carries non-null
    SQL, so `name NOT LIKE 'sqlite_%'` is the only thing excluding it — the
    same filter `test_sqlite_internal_tables_are_excluded_from_the_digest`
    covers from the `sqlite_stat*` side.

    This is the closest a committed test comes to the cross-repository control
    that was actually run on 2026-08-10 — three repositories of different size
    and language mix, one digest. It is not a substitute for it: 500 synthetic
    rows are not a second repository.
    """
    built = a_db_from_the_pinned_schema(tmp_path)
    before = schema_digest(built)

    conn = sqlite3.connect(built)
    try:
        conn.executemany(
            "INSERT INTO nodes(id, kind, name, qualified_name, file_path, "
            "language, start_line, end_line, start_column, end_column, "
            "updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (f"n{i}", "function", f"sym_{i}", f"m.sym_{i}", "a/b.py",
                 "python", i, i + 1, 0, 9, 0)
                for i in range(500)
            ],
        )
        conn.execute("ANALYZE")
        conn.commit()
        # The floor: the inserts landed, the triggers fired into the FTS table,
        # and ANALYZE produced something. Without this the equality below is
        # satisfied by a fixture where nothing happened.
        assert conn.execute("SELECT count(*) FROM nodes").fetchone()[0] == 500
        assert conn.execute("SELECT count(*) FROM nodes_fts").fetchone()[0] == 500
        assert [
            name
            for _, name, sql in schema_rows(built)
            if name.startswith("sqlite_stat") and sql is not None
        ]
    finally:
        conn.close()

    assert schema_digest(built).digest == before.digest == CODEGRAPH_SCHEMA_SHA256


def test_verify_fails_closed_while_the_pinned_hash_is_unset(tmp_path, monkeypatch):
    """An assertion with no expected value refuses rather than passing.

    The observed digest has to be in the message, because recording it is the
    only way an operator closes the gap.
    """
    monkeypatch.setattr(codegraph_pin, "CODEGRAPH_SCHEMA_SHA256", None)
    path = a_db(tmp_path, NODES_AND_EDGES)
    observed = schema_digest(path).digest

    with pytest.raises(CodegraphPinError) as raised:
        verify(path)

    message = str(raised.value)
    assert "UNSET" in message
    assert observed in message


def test_verify_names_a_mismatch_an_upstream_change_and_not_source_drift(
    tmp_path, monkeypatch
):
    """The clause that matters most.

    FR-028 reads a changed source-artifact hash as source drift. A mismatch here
    is an upstream release, so the error has to say so in terms an operator and
    a later reader cannot mistake for drift, and it has to name both digests so
    the mismatch is diagnosable.
    """
    path = a_db(tmp_path, NODES_AND_EDGES)
    observed = schema_digest(path).digest
    someone_elses_schema = "0" * 64
    assert someone_elses_schema != observed
    monkeypatch.setattr(
        codegraph_pin, "CODEGRAPH_SCHEMA_SHA256", someone_elses_schema
    )

    with pytest.raises(CodegraphPinError) as raised:
        verify(path)

    message = str(raised.value)
    assert "upstream schema change" in message
    assert "NOT source drift" in message
    assert "never be emitted as a drift signal" in message
    assert someone_elses_schema in message
    assert observed in message


def test_verify_returns_the_digest_when_the_pinned_hash_matches(tmp_path, monkeypatch):
    """The accepting side, without which every arm above is satisfied by a
    function that raises unconditionally."""
    path = a_db(tmp_path, NODES_AND_EDGES)
    observed = schema_digest(path)
    monkeypatch.setattr(codegraph_pin, "CODEGRAPH_SCHEMA_SHA256", observed.digest)

    accepted = verify(path)

    assert accepted.digest == observed.digest
    assert accepted.version == CODEGRAPH_VERSION
    assert accepted.table_count == 2


# --- a missing artifact is this module's error, not sqlite's ----------------


def test_a_missing_artifact_raises_the_pin_error_rather_than_a_sqlite_error(tmp_path):
    """A `sqlite3` error out of here would surface as a storage fault somewhere
    that has no idea the analysis stage never had an artifact to read."""
    absent = tmp_path / "never-indexed" / "codegraph.db"

    with pytest.raises(CodegraphPinError, match="artifact not found"):
        schema_digest(absent)


def test_a_directory_in_place_of_the_artifact_raises_the_pin_error(tmp_path):
    """`.codegraph/` is a directory and `codegraph.db` is inside it, so being
    handed the wrong one of the two is the ordinary operator mistake here."""
    directory = tmp_path / ".codegraph"
    directory.mkdir()

    with pytest.raises(CodegraphPinError, match="artifact not found"):
        schema_digest(directory)


def test_a_missing_artifact_reaches_verify_as_the_pin_error_too(tmp_path):
    absent = tmp_path / "codegraph.db"

    with pytest.raises(CodegraphPinError, match="artifact not found"):
        verify(absent)


def test_the_pin_error_is_not_a_sqlite_error(tmp_path):
    """Stated as its own assertion because `except sqlite3.Error` around a call
    to this module would swallow nothing, and a reader may assume otherwise."""
    assert not issubclass(CodegraphPinError, sqlite3.Error)
    assert issubclass(CodegraphPinError, RuntimeError)
