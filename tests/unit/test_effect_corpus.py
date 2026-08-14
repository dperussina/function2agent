"""T179 — the FR-041 corpus exporter, and the four ways it could lie.

The exporter ranges over `effect_gate_observation`. It does not restate
`egress_decision`. It does not claim the rows are labelled. T180 is the
residual that produces labels. The success path does not import it.

Run:
    python -m pytest tests/unit/test_effect_corpus.py -v
"""

from __future__ import annotations

import ast
import json
import re
import sqlite3
from pathlib import Path

import pytest

from src.runtime.reports import effect_corpus as corpus

REPO = Path(__file__).resolve().parents[2]
OBSERVATION_GO = REPO / "src" / "proxy" / "observation.go"
SUCCESS_PATH = (
    REPO / "src" / "runtime" / "loop.py",
    REPO / "src" / "runtime" / "serving.py",
    REPO / "src" / "contracts" / "result.py",
)
EXPORTER_MODULES = (
    "src.runtime.reports.effect_corpus",
    "src.runtime.reports.effect_precision",
)

OBSERVATION_SCHEMA = """
CREATE TABLE effect_gate_observation (
  seq               INTEGER PRIMARY KEY AUTOINCREMENT,
  decision_seq      INTEGER NOT NULL,
  resolved_tier     TEXT NOT NULL,
  rule_id           TEXT NOT NULL,
  matched_template  TEXT NOT NULL,
  method            TEXT NOT NULL,
  spec_metadata     TEXT NOT NULL,
  disposition       TEXT NOT NULL
);
"""

#: Same columns as the observation table, under the decision-log name, so a
#: plant that retargets `PHYSICAL_TABLE` still *runs* and returns the wrong
#: population rather than erroring on a missing column.
DECISION_SHAPED_AS_OBSERVATION = """
CREATE TABLE egress_decision (
  seq               INTEGER PRIMARY KEY AUTOINCREMENT,
  decision_seq      INTEGER NOT NULL,
  resolved_tier     TEXT NOT NULL,
  rule_id           TEXT NOT NULL,
  matched_template  TEXT NOT NULL,
  method            TEXT NOT NULL,
  spec_metadata     TEXT NOT NULL,
  disposition       TEXT NOT NULL
);
"""


def _go_observation_schema() -> str:
    source = OBSERVATION_GO.read_text()
    match = re.search(r"const observationSchema = `(.*?)`", source, re.DOTALL)
    assert match, (
        "no `observationSchema` constant in src/proxy/observation.go. "
        "This fixture is derived from that constant, not transcribed."
    )
    return match.group(1)


def _insert(conn: sqlite3.Connection, table: str, **fields: object) -> None:
    columns = (
        "decision_seq", "resolved_tier", "rule_id", "matched_template",
        "method", "spec_metadata", "disposition",
    )
    conn.execute(
        f"INSERT INTO {table} ({', '.join(columns)}) VALUES (?,?,?,?,?,?,?)",
        tuple(fields[name] for name in columns),
    )


def _observation_db(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.executescript(OBSERVATION_SCHEMA)
    conn.executescript(DECISION_SHAPED_AS_OBSERVATION)
    _insert(
        conn, "effect_gate_observation",
        decision_seq=1, resolved_tier="read_only", rule_id="OBS-1",
        matched_template="/orders/{id}", method="GET",
        spec_metadata='{"operation_id":"getOrder","safe":true,'
                      '"operation_rule_id":"EFF-OP-001"}',
        disposition="allow",
    )
    _insert(
        conn, "effect_gate_observation",
        decision_seq=2, resolved_tier="reversible_write", rule_id="OBS-2",
        matched_template="/orders/{id}", method="POST",
        spec_metadata='{"operation_id":"createOrder","safe":false,'
                      '"operation_rule_id":"EFF-OP-002"}',
        disposition="deny",
    )
    _insert(
        conn, "egress_decision",
        decision_seq=99, resolved_tier="read_only", rule_id="DEC-1",
        matched_template="/from-the-decision-log", method="GET",
        spec_metadata="{}",
        disposition="allow",
    )
    conn.commit()
    return conn


def _row(**overrides: object) -> corpus.ObservationRow:
    fields: dict[str, object] = {
        "decision_seq": 1,
        "resolved_tier": "read_only",
        "rule_id": "EFF-OP-001",
        "matched_template": "/orders/{id}",
        "method": "GET",
        "spec_metadata": "{}",
        "disposition": "allow",
    }
    fields.update(overrides)
    return corpus.ObservationRow(**fields)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# The table. Derived from the Go writer's constant, then ranged over.


def test_the_physical_table_is_the_observation_table() -> None:
    assert corpus.PHYSICAL_TABLE == "effect_gate_observation"
    assert "egress_decision" not in corpus.COLUMNS
    assert "matched_template" in corpus.COLUMNS
    assert "spec_metadata" in corpus.COLUMNS


def test_the_go_schema_still_declares_the_table_this_exporter_names() -> None:
    """A rename on the Go side changes the fixture rather than silently diverging."""
    schema = _go_observation_schema()
    assert "effect_gate_observation" in schema
    for column in corpus.COLUMNS:
        assert column in schema, (
            f"{column} is in the documented projection but not in "
            "observation.go's observationSchema"
        )


def test_the_exporter_ranges_over_the_observation_table_not_the_decision_log(
        tmp_path: Path) -> None:
    """The plant retargets PHYSICAL_TABLE at egress_decision.

    Both tables are populated. The observation rows carry OBS-* rule ids;
    the decision-shaped table carries DEC-1. Ranging over the wrong table
    returns DEC-1 and this fails. Erroring on a missing column would be
    BROKEN rather than proved, so the sibling table has the same columns.
    """
    path = tmp_path / "proxy.sqlite3"
    conn = _observation_db(path)
    conn.close()

    exported = corpus.export(path)
    assert [row.rule_id for row in exported.rows] == ["OBS-1", "OBS-2"]
    assert all(row.rule_id != "DEC-1" for row in exported.rows)
    assert exported.document()["physical_table"] == "effect_gate_observation"


def test_an_allow_and_a_deny_both_export(tmp_path: Path) -> None:
    path = tmp_path / "proxy.sqlite3"
    _observation_db(path).close()
    exported = corpus.export(path)
    assert {row.disposition for row in exported.rows} == {"allow", "deny"}
    assert exported.rows[0].matched_template == "/orders/{id}"
    assert exported.rows[0].spec_metadata
    assert exported.rows[0].decision_seq == 1


def test_the_document_is_json(tmp_path: Path) -> None:
    path = tmp_path / "proxy.sqlite3"
    _observation_db(path).close()
    document = corpus.export(path).document()
    assert json.loads(json.dumps(document)) == document
    assert document["schema_version"] == corpus.SCHEMA_VERSION
    assert document["row_count"] == 2


# ---------------------------------------------------------------------------
# Unlabelled. T180 is the residual.


def test_an_unlabelled_export_does_not_claim_to_be_labelled() -> None:
    """Observations existing is not a labelled corpus.

    Plant: `return all(...)` becomes `return True`. An unlabelled row then
    reports labelled, which is SC-014 starting over a set T180 has not
    produced.
    """
    exported = corpus.export_rows([_row(), _row(decision_seq=2, rule_id="EFF-OP-002")])
    assert exported.labelled is False
    assert exported.document()["labelled"] is False
    assert exported.label_absent_because == corpus.T180_RESIDUAL
    assert "T180" in corpus.T180_RESIDUAL
    assert all(row.label is None for row in exported.rows)


def test_an_empty_export_is_not_a_labelled_set_of_zero() -> None:
    exported = corpus.export_rows([])
    assert exported.labelled is False
    assert exported.document()["row_count"] == 0


def test_a_fully_labelled_projection_is_labelled() -> None:
    """The control: T180's field, when present on every row, is what labelled means."""
    exported = corpus.export_rows([
        _row(label="side_effect_free"),
        _row(decision_seq=2, rule_id="EFF-OP-002", label="side_effecting"),
    ])
    assert exported.labelled is True
    assert exported.label_absent_because is None


def test_a_mixed_projection_is_not_labelled() -> None:
    exported = corpus.export_rows([
        _row(label="side_effect_free"),
        _row(decision_seq=2, rule_id="EFF-OP-002"),
    ])
    assert exported.labelled is False


# ---------------------------------------------------------------------------
# Refusals.


def test_a_row_with_no_rule_identifier_is_refused() -> None:
    with pytest.raises(corpus.CorpusExportError, match="rule identifier"):
        _row(rule_id="")


def test_a_third_disposition_is_refused() -> None:
    with pytest.raises(corpus.CorpusExportError, match="allow or a deny"):
        _row(disposition="quarantine")


def test_an_absent_database_is_refused(tmp_path: Path) -> None:
    with pytest.raises(corpus.CorpusExportError, match="has not run"):
        corpus.export(tmp_path / "missing.sqlite3")


# ---------------------------------------------------------------------------
# Read-only. The exemption for engine-specific SQL is narrowed here.


def test_the_reader_is_opened_read_only(tmp_path: Path) -> None:
    path = tmp_path / "proxy.sqlite3"
    _observation_db(path).close()
    before = path.read_bytes()
    with corpus.ObservationReader(path) as reader:
        with pytest.raises(sqlite3.OperationalError):
            reader._conn.execute(
                "INSERT INTO effect_gate_observation "
                "(decision_seq, resolved_tier, rule_id, matched_template, "
                "method, spec_metadata, disposition) "
                "VALUES (3,'read_only','X','/x','GET','{}','allow')"
            )
    assert path.read_bytes() == before


def test_the_exporter_issues_no_write_statement_at_all() -> None:
    """`effect_corpus.py` is on the permitted list for the
    engine-specific-SQL invariant, which suspends that check for the whole
    file. This narrows the exemption back down: the SQL in it must be a read.
    """
    source = Path(corpus.__file__).read_text()
    forbidden = re.findall(
        r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|REPLACE|PRAGMA|VACUUM|ATTACH)\b",
        source,
    )
    assert not forbidden, (
        f"write- or schema-bearing SQL in the exporter: {sorted(set(forbidden))}. "
        "The proxy owns this store."
    )
    assert "SELECT" in source, (
        "no SELECT in the module, so the check above passed over nothing"
    )
    assert "egress_decision" not in re.findall(
        r"FROM\s+(\w+)", source
    ), "the exporter SELECTs from egress_decision; that is a restated decision log"


# ---------------------------------------------------------------------------
# Not a success-path read.


def _imported(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
            names.update(f"{node.module}.{a.name}" for a in node.names)
    return names


def _exporter_imports(path: Path) -> list[str]:
    found: list[str] = []
    relative = path.relative_to(REPO).as_posix() if path.is_relative_to(REPO) else path.name
    for imported in sorted(_imported(path)):
        for module in EXPORTER_MODULES:
            if imported == module or imported.startswith(module + "."):
                found.append(f"{relative} imports {imported}")
    return found


def test_the_success_path_does_not_import_the_exporter() -> None:
    found: list[str] = []
    for path in SUCCESS_PATH:
        found.extend(_exporter_imports(path))
    assert found == [], (
        "a success-path module imported the corpus exporter or the "
        "precision record:\n  " + "\n  ".join(found)
    )


def test_the_success_path_import_scan_fires_on_a_planted_exporter_edge(
        tmp_path: Path) -> None:
    """The removal proof of loop/serving/result → effect_corpus."""
    planted = tmp_path / "loop.py"
    planted.write_text("from src.runtime.reports.effect_corpus import export\n")
    found: list[str] = []
    for imported in _imported(planted):
        for module in EXPORTER_MODULES:
            if imported == module or imported.startswith(module + "."):
                found.append(imported)
    assert found, "the success-path→exporter scan did not report a planted import"


def test_the_success_path_files_the_scan_names_still_exist() -> None:
    missing = [p for p in SUCCESS_PATH if not p.is_file()]
    assert not missing, (
        f"SUCCESS_PATH names a file that is gone: {missing}. The scan "
        "would pass over an empty set."
    )
