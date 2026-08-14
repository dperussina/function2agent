"""T179 — the FR-041 corpus exporter.

**Requirement**: FR-041. **Criterion**: SC-014. **Also**: T178's table is the
corpus; this module exports it.

What this module produces is the set FR-041 scores against — every
`effect_gate_observation` row, allow and deny — and nothing else. In
particular it does **not** label the rows. Labelling is T180's state-diff
oracle, which snapshots observable state, issues the call, and diffs. Until
that residual runs, every exported row is unlabelled and the document says
so. Claiming the corpus is labelled because the observations exist is the
defect this module exists to make impossible.

## THE THREE THINGS THIS MODULE REFUSES TO DO, AND WHY EACH IS A REFUSAL

**1. It will not restate the decision log.** `egress_decision` already carries
resolved tier, rule id, method, and disposition. The observation row is the
FR-041 projection of those four plus the matched operation template, the
specification metadata that operation carried, and `decision_seq` back to the
decision. Ranging over `egress_decision` would drop the two fields the
decision log does not have and would make the corpus a second copy of a log
T178 already refused to be. `PHYSICAL_TABLE` is `effect_gate_observation`
and `test_the_exporter_ranges_over_the_observation_table_not_the_decision_log`
plants the other name.

**2. It will not invent a label.** A row arrives as T178 wrote it. `label` is
`None` on every row this slice can produce. `labelled` is `False` unless
every row carries a label *and* there is at least one row — an empty export
is not a labelled set of zero. T180 is named on the document as the residual
that produces labels. A boolean that flipped to `True` because observations
existed would let SC-014's measurement start over an unlabelled set.

**3. It will not be a success-path read.** The ownership row for
`effect_gate_observation` has an empty reader set, and that is the point: a
mapped reader role could start deciding allow or deny from the corpus.
This module is a **report** reader. It does not call `require_read`. It is
not imported by `loop.py`, `serving.py`, or `result.py`. The connection is
opened `mode=ro` so a write is refused by SQLite rather than by convention.

## WHAT IS OWED AND IS NOT BUILT

* **T180 — the state-diff oracle.** Labels by observable state on the
  reference application. Named here rather than sketched: this exporter
  ships the unlabelled rows; the oracle is what makes them a labelled set.
* **T181 — the per-call threshold.** Unset, in `effect_precision.py`. This
  module does not score, compare, or inherit a number.
* **T187 — measurement isolation.** Will assert this table is structurally
  apart from every success-path table. The empty reader set and the
  success-path import scan are what this slice can hold until then.
"""

from __future__ import annotations

import inspect
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

#: Bumped when a field is added, removed or given a new meaning. Not
#: registered in `src/contracts/schemas.py` — OD-33 declines a further
#: artifact kind. The tests in `tests/unit/test_effect_corpus.py` are the
#: only thing that gates this shape.
SCHEMA_VERSION = "1.0.0"

#: The physical table `src/proxy/observation.go` creates. Named here and
#: never `egress_decision`: that log is a different table with a different
#: writer-facing purpose, and ranging over it is restating it.
PHYSICAL_TABLE = "effect_gate_observation"

#: Columns this module reads, in the order it reads them. Named explicitly
#: and never `SELECT *`, so a column added on the Go side arrives as a field
#: nobody reads instead of as a positional shift. This is the documented
#: projection of `effect_gate_observation`. It is not a projection of
#: `egress_decision`: `matched_template` and `spec_metadata` are the two
#: fields that table does not have.
COLUMNS: tuple[str, ...] = (
    "decision_seq",
    "resolved_tier",
    "rule_id",
    "matched_template",
    "method",
    "spec_metadata",
    "disposition",
)

#: The dispositions T178 persists. A third value is not one of those, and
#: treating it as either would silently enlarge the corpus.
DISPOSITIONS = frozenset({"allow", "deny"})

#: Why no row is labelled, recorded as a decision rather than as a gap.
T180_RESIDUAL = (
    "T180's state-diff oracle produces the labels: snapshot the reference "
    "application's state, issue the call, diff. That is constitution "
    "Principle I's admissible artifact — observable state, not a model "
    "judgement. This exporter ships the observation rows T178 wrote. It "
    "does not snapshot the application, it does not issue the call, and it "
    "does not claim the corpus is labelled because the rows exist. FR-041 "
    "scores a labelled set; an unlabelled export is the honest state until "
    "T180 runs."
)


class CorpusExportError(ValueError):
    """A row or a store the exporter will not range over.

    Raised rather than absorbed. Every value this refuses is one that would
    otherwise produce a document that looks like every other document.
    """


class ModuleTextUnavailable(RuntimeError):
    """This module's own text could not be located for the arm that reads it.

    Raised rather than returned empty: the arm that calls this searches the
    text for a restated decision log and reports finding none, and text that
    was never read finds none either.
    """


@dataclass(frozen=True)
class ObservationRow:
    """One `effect_gate_observation` row, as the documented projection.

    `label` is T180's field. This slice never sets it. A caller that already
    ran the oracle may pass a label through; this module will not invent one
    and will not report the export as labelled unless every row has one.
    """

    decision_seq: int
    resolved_tier: str
    rule_id: str
    matched_template: str
    method: str
    spec_metadata: str
    disposition: str
    label: str | None = None

    def __post_init__(self) -> None:
        if not self.rule_id:
            raise CorpusExportError(
                "an observation with no rule identifier is not a corpus "
                "row. T178 refuses to write one; this exporter refuses to "
                "export one."
            )
        if self.disposition not in DISPOSITIONS:
            raise CorpusExportError(
                f"{self.disposition!r} is not an allow or a deny. FR-041's "
                "corpus is every request the decision log already records, "
                "and a third disposition is not one of those."
            )


@dataclass(frozen=True)
class CorpusExport:
    """The labelled set FR-041 scores against — or the honest unlabelled one.

    Constructed by `export` / `export_rows` rather than by hand.
    """

    rows: tuple[ObservationRow, ...]

    @property
    def labelled(self) -> bool:
        """True only when every row carries a T180 label and there is one.

        An empty export is not a labelled set of zero. A row without a label
        is an observation, not a scored example. Either case is `False`.
        """
        if not self.rows:
            return False
        return all(row.label is not None for row in self.rows)

    @property
    def label_absent_because(self) -> str | None:
        if self.labelled:
            return None
        return T180_RESIDUAL

    def document(self) -> dict[str, Any]:
        """The machine-readable form. Observation fields, not decision-log ones."""
        return {
            "schema_version": SCHEMA_VERSION,
            "physical_table": PHYSICAL_TABLE,
            "labelled": self.labelled,
            "label_absent_because": self.label_absent_because,
            "t180_residual": T180_RESIDUAL,
            "row_count": len(self.rows),
            "rows": [_row_document(row) for row in self.rows],
        }


def _row_document(row: ObservationRow) -> dict[str, Any]:
    return {
        "decision_seq": row.decision_seq,
        "resolved_tier": row.resolved_tier,
        "rule_id": row.rule_id,
        "matched_template": row.matched_template,
        "method": row.method,
        "spec_metadata": _metadata_document(row.spec_metadata),
        "disposition": row.disposition,
        "label": row.label,
    }


def _metadata_document(raw: str) -> Any:
    try:
        parsed: Any = json.loads(raw)
    except json.JSONDecodeError:
        return raw
    return parsed


class ObservationReader:
    """A read-only view of the enforcement point's observation table.

    Opened `mode=ro` through a URI. The database is a foreign store — the
    proxy's, in Go, with none of FR-035's scope columns — so it is not
    reached through `src/contracts/repository.py`. The same footing as
    `src/runtime/proxy_ingest.py`, with one difference that is the point:
    this reader does not call `require_read`, because the ownership row has
    no success-path readers and a report is not one.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        if not self.path.is_file():
            raise CorpusExportError(
                f"no observation database at {self.path}. The enforcement "
                "point creates it at startup, so an absent file means the "
                "proxy has not run — which is a different fact from a "
                "proxy that took no decisions, and is not reported as an "
                "empty corpus."
            )
        self._conn = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True)
        self._conn.row_factory = sqlite3.Row

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "ObservationReader":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def rows(self) -> list[ObservationRow]:
        """Every observation, in the writer's insertion order.

        Ordered by the proxy's own `seq`. The SELECT names
        `effect_gate_observation` via `PHYSICAL_TABLE` and the documented
        projection via `COLUMNS`. It does not name `egress_decision`.
        """
        columns = ", ".join(COLUMNS)
        cursor = self._conn.execute(
            f"SELECT {columns} FROM {PHYSICAL_TABLE} ORDER BY seq ASC"  # noqa: S608
        )
        return [_row(dict(record)) for record in cursor.fetchall()]


def _row(record: Mapping[str, Any]) -> ObservationRow:
    return ObservationRow(
        decision_seq=int(record["decision_seq"]),
        resolved_tier=str(record["resolved_tier"]),
        rule_id=str(record["rule_id"]),
        matched_template=str(record["matched_template"]),
        method=str(record["method"]),
        spec_metadata=str(record["spec_metadata"]),
        disposition=str(record["disposition"]),
    )


def export_rows(rows: Iterable[ObservationRow]) -> CorpusExport:
    """Range over an already-read projection of `effect_gate_observation`."""
    records: Sequence[ObservationRow] = tuple(rows)
    return CorpusExport(rows=tuple(records))


def export(path: str | Path) -> CorpusExport:
    """Read `effect_gate_observation` out of the proxy's database and export it."""
    with ObservationReader(path) as reader:
        return export_rows(reader.rows())


def module_source() -> str:
    """This module's own text, for the arm that reads it for a restated log.

    A function rather than a path the test reconstructs: a test that guesses
    the file location silently stops reading anything when the module moves,
    and an arm that reads nothing finds no `egress_decision` in it.
    """
    module = inspect.getmodule(export)
    if module is None:
        raise ModuleTextUnavailable(
            "inspect.getmodule() could not locate the module defining "
            "export(), so this module's own text cannot be read. Refused "
            "rather than returned empty: the arm that calls this searches "
            "the text for a restated decision log and reports finding none, "
            "and text that was never read finds none either."
        )
    return inspect.getsource(module)
