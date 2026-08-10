"""T004 — the `codegraph` pin's own floors.

**Every fixture here is synthetic and constructed in the test.** No artifact
produced by a real `codegraph` is used, and that is deliberate rather than a
concession: `codegraph` is a git-ignored vendored TypeScript source tree with no
installed build, so a fixture built from a real artifact would make this file's
population depend on a tool nobody running the suite can obtain. It would also
tie the tests to the same unobserved digest **U-04** is open about. The schemas
below therefore resemble `codegraph`'s shape and claim nothing about it — what is
under test is `schema_digest()` and `verify()`, not upstream's table set.

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


def test_the_pinned_hash_is_unset_because_no_digest_has_ever_been_observed():
    """T004's outstanding half, pinned so it cannot be closed by fabrication.

    No `codegraph` artifact has been produced in this repository, so there is no
    observed digest to assert against. A constant invented to make the assertion
    pass would make it pass against nothing. This test fails the moment one is
    written, which is the point: setting it is an owner action taken together
    with a recorded observation, not an edit.
    """
    assert CODEGRAPH_SCHEMA_SHA256 is None


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
