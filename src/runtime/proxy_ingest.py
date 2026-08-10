"""T093 — the enforcement point's decision log, ingested into the trace stream.

**The ownership direction is the design constraint, not a detail of it.** The
proxy owns `egress_decision` and is its only writer (`src/proxy/decisionlog.go`,
FR-011); the ownership map declares the runtime a **reader** of it
(`proxy_decision` in `src/contracts/ownership.py`). So this module reads and
never writes, and it is the *engine* that enforces that rather than this
module's discipline: the connection is opened `mode=ro`, so a write is refused
by SQLite. A read-only reader that merely refrains from writing is a convention,
and T017's whole argument is that a convention holds until somebody is in a
hurry.

**No re-tagging, and this is the one place in the repository where a wrong
requirement label is not merely documentation.** `src/proxy/rules.go` stamps a
`Requirement` string into every decision-log record *and* into the
client-visible error body, so the label an operator reads off a denial and the
label in the log are one value produced by one registry. This module therefore
holds **no** mapping from a rule identifier to a reason or to a requirement. It
carries `rule_id`, `reason` and `requirement` through verbatim, and a row
missing any of them is **refused** rather than completed — inventing the missing
half here would put a second, silently-diverging registry on the reading side of
a cross-process boundary that has exactly one writer.

**FR-038's span set is closed and this adds no kind.** An enforcement-point
disposition is an `egress_decision`, which is already one of the seven, and it
is already the kind FR-038's fourth clause names — *the decision together with
the inputs the rule that produced it matched on … for every such decision and
not only for denials*. So an **allow** is ingested too.

**The watermark is derived from the trace, not held beside it.** There is no
cursor table. `watermark()` reads the highest `decision_seq` already present in
the session's own ingested spans, so "what has been ingested" and "where to
resume" are one fact rather than two that can disagree. A crash between writing
a span and updating a cursor is the ordinary way a second source of truth goes
wrong, and here there is no second one: an interrupted ingest resumes after the
last span that actually landed.

**What this does not do.** It does not reconcile the proxy's record against the
target's record of what it served — T114 is the battery that does that, and it
scores the *target*, on the ground that the enforcement point's own log is the
thing under test rather than the oracle for it. Nothing here should be read as
evidence that the log is complete; it is evidence about what the log says.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

from src.contracts.ownership import ROLE_RUNTIME, require_read
from src.runtime.trace import (
    ATTEMPT_FIRST,
    EGRESS_DECISION,
    OUTCOME_DENIED,
    OUTCOME_OK,
    ArtifactVersions,
    Cost,
    DecisionFields,
    Span,
    SpanWriter,
)

#: The logical table in the ownership map. The read below rests on this row —
#: `proxy_decision`, written by the proxy and read by the runtime — and the
#: authority is checked at construction rather than assumed, so a future edit
#: that removed the runtime from that row's readers would fail here.
OWNED_TABLE = "proxy_decision"

#: The physical table `src/proxy/decisionlog.go` creates. It differs in name
#: from the logical row above, which is stated rather than quietly reconciled:
#: the map is `data-model.md`'s vocabulary and this is the Go writer's.
PHYSICAL_TABLE = "egress_decision"

#: Columns this module reads, in the order it reads them. Named explicitly and
#: never `SELECT *`, so a column added on the Go side arrives as a field nobody
#: reads instead of as a positional shift.
COLUMNS: tuple[str, ...] = (
    "seq", "ts", "disposition", "rule_id", "reason", "requirement",
    "method", "path", "resolved_tier", "session_id", "policy_version",
    "absolute_https_denied", "credential_fpr", "detail",
)

#: The dispositions the Go writer produces, mapped onto FR-038's declared
#: outcome set. **Stated as the values that mean each answer, never as a
#: complement.** A disposition outside this map is refused: the disposition
#: space belongs to another process in another language, so "anything that is
#: not `deny` is an allow" would silently record a future third disposition as
#: a permitted call.
DISPOSITION_OUTCOME: Mapping[str, str] = {
    "allow": OUTCOME_OK,
    "deny": OUTCOME_DENIED,
}


class ProxyIngestError(RuntimeError):
    """A decision row that cannot be ingested as it stands.

    Raised rather than skipped. A row the runtime cannot represent is a
    disposition the enforcement point took and the trace does not show, and
    dropping it quietly is worse than failing: FR-038 requires the record for
    **every** egress decision, so a gap that nothing reports is a gap nobody
    finds.
    """


@dataclass(frozen=True)
class DecisionRow:
    """One row of the proxy's log, as read. No field is computed here."""

    seq: int
    ts: float
    disposition: str
    rule_id: str
    reason: str
    requirement: str
    method: str
    path: str
    resolved_tier: str
    session_id: str
    policy_version: str
    absolute_https_denied: int
    credential_fpr: str
    detail: str


class ProxyDecisionReader:
    """A read-only view of the enforcement point's own decision database.

    Opened `mode=ro` through a URI, which is what makes the ownership direction
    a property of the connection. The database is a **foreign store** from the
    runtime's point of view — another process's, in another language, with its
    own schema and none of FR-035's scope columns — so it is not reached through
    `src/contracts/repository.py`. `src/analysis/codegraph_pin.py` reads
    `codegraph`'s artifact on exactly that footing, and routing either through
    our tenancy layer would be routing a read of somebody else's database
    through our tenancy.
    """

    def __init__(self, path: str | Path) -> None:
        require_read(OWNED_TABLE, ROLE_RUNTIME)
        self.path = Path(path)
        if not self.path.is_file():
            raise ProxyIngestError(
                f"no decision database at {self.path}. The enforcement point "
                "creates it at startup, so an absent file means the proxy has "
                "not run — which is a different fact from a proxy that took no "
                "decisions, and is not reported as an empty log."
            )
        self._conn = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True)
        self._conn.row_factory = sqlite3.Row

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "ProxyDecisionReader":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def rows_after(self, session_id: str, seq: int) -> list[DecisionRow]:
        """Every decision for `session_id` beyond `seq`, in the log's order.

        Ordered by the proxy's own `seq`, which is the writer's insertion order.
        Ordering by `ts` instead would order by a clock, and FR-038 asks for a
        position that orders a session **without reference to one**.
        """
        columns = ", ".join(COLUMNS)
        cursor = self._conn.execute(
            f"SELECT {columns} FROM {PHYSICAL_TABLE} "  # noqa: S608 - fixed identifiers
            "WHERE session_id = ? AND seq > ? ORDER BY seq ASC",
            (session_id, int(seq)),
        )
        return [_row(dict(r)) for r in cursor.fetchall()]


def _row(record: Mapping[str, Any]) -> DecisionRow:
    return DecisionRow(
        seq=int(record["seq"]),
        ts=float(record["ts"]),
        disposition=str(record["disposition"]),
        rule_id=str(record["rule_id"]),
        reason=str(record["reason"]),
        requirement=str(record["requirement"]),
        method=str(record["method"]),
        path=str(record["path"]),
        resolved_tier=str(record["resolved_tier"]),
        session_id=str(record["session_id"]),
        policy_version=str(record["policy_version"]),
        absolute_https_denied=int(record["absolute_https_denied"]),
        credential_fpr=str(record["credential_fpr"]),
        detail=str(record["detail"]),
    )


def outcome_of(disposition: str) -> str:
    """FR-038's typed outcome for one disposition, or a refusal.

    The refusal is the point. `DISPOSITION_OUTCOME` names the values that mean
    *allowed* and the values that mean *denied*; a value in neither is not
    classified by elimination, because the set of dispositions is another
    process's to extend.
    """
    try:
        return DISPOSITION_OUTCOME[disposition]
    except KeyError:
        raise ProxyIngestError(
            f"{disposition!r} is not a disposition this runtime can record "
            f"(known: {sorted(DISPOSITION_OUTCOME)}). It is refused rather "
            "than treated as a denial or as an allow: the enforcement point "
            "owns the disposition vocabulary, and guessing at a new member "
            "records a call the trace cannot be trusted about."
        ) from None


def span_for(
    row: DecisionRow,
    *,
    turn: int,
    ordinal: int,
    versions: ArtifactVersions,
    cost: Cost,
) -> Span:
    """One `egress_decision` span from one decision row.

    Every field the enforcement point stamped travels verbatim. Nothing here
    derives `reason` from `rule_id` or `requirement` from either: those three
    are one registry's output (`src/proxy/rules.go`), the same registry supplies
    the client-visible denial body, and a second opinion formed on this side is
    a label that can disagree with the one the operator was shown.
    """
    for field_name in ("rule_id", "reason", "requirement"):
        if not getattr(row, field_name).strip():
            raise ProxyIngestError(
                f"decision seq={row.seq} carries no {field_name}. It is "
                "refused rather than completed here: the enforcement point's "
                "registry is the sole source of all three, and filling one in "
                "on the reading side puts a second registry on a boundary "
                "that has exactly one writer."
            )
    return Span(
        kind=EGRESS_DECISION,
        session_id=row.session_id,
        turn=turn,
        ordinal=ordinal,
        outcome=outcome_of(row.disposition),
        attempt_kind=ATTEMPT_FIRST,
        versions=versions,
        cost=cost,
        at=row.ts,
        decision=DecisionFields(
            rule_id=row.rule_id,
            resolved_tier=row.resolved_tier,
            matched={
                "method": row.method,
                "path": row.path,
                "policy_version": row.policy_version,
            },
        ),
        detail={
            "source": "proxy_decision_log",
            "decision_seq": row.seq,
            "disposition": row.disposition,
            "reason": row.reason,
            "requirement": row.requirement,
            "detail": row.detail,
            # Q-07 asks whether absolute-https denial dominates real traffic.
            # The counter is on the record so the question is answerable from
            # the trace as well as from the proxy's own database.
            "absolute_https_denied": row.absolute_https_denied,
            # A truncated SHA-256 of the target credential, never the value.
            # Carried because it is the only thing that attributes a
            # re-originated call to the credential it used.
            "credential_fingerprint": row.credential_fpr,
        },
    )


def watermark(writer: SpanWriter, session_id: str) -> int:
    """The highest decision `seq` already in this session's trace, or 0.

    Read out of the spans themselves. There is no cursor table, so there is no
    second record of progress that can survive a crash the spans did not, or
    fail to survive one they did.
    """
    highest = 0
    for span in _ingested_spans(writer, session_id):
        seq = span.get("decision_seq")
        if isinstance(seq, int) and seq > highest:
            highest = seq
    return highest


def _ingested_spans(writer: SpanWriter, session_id: str) -> Iterator[dict[str, Any]]:
    """The `detail` block of every span this module wrote for a session."""
    for stored in writer.spans(session_id):
        if stored.get("kind") != EGRESS_DECISION:
            continue
        payload = json.loads(stored["payload"])
        detail = payload.get("detail") or {}
        if detail.get("source") == "proxy_decision_log":
            yield detail


@dataclass(frozen=True)
class IngestResult:
    """What one pass moved. `highest_seq` is the watermark after the pass."""

    ingested: int
    highest_seq: int
    rule_ids: tuple[str, ...]


def ingest(
    reader: ProxyDecisionReader,
    writer: SpanWriter,
    *,
    session_id: str,
    turn: int,
    versions: ArtifactVersions,
    cost: Cost,
) -> IngestResult:
    """Move every decision beyond the watermark into the trace, in log order.

    `turn` and the two artifact-and-cost arguments are the caller's because the
    enforcement point does not have them: it knows nothing of turns, of which
    artifact versions were in force in the runtime, or of what the session has
    spent. FR-038 requires all three on every span, so they are passed in rather
    than defaulted — a default here would be this module inventing the position
    and the attribution of a record it did not produce.
    """
    from_seq = watermark(writer, session_id)
    rows = reader.rows_after(session_id, from_seq)
    written: list[str] = []
    highest = from_seq
    for row in rows:
        span = span_for(
            row,
            turn=turn,
            ordinal=writer.next_ordinal(session_id, turn),
            versions=versions,
            cost=cost,
        )
        writer.write(span)
        written.append(row.rule_id)
        highest = row.seq
    return IngestResult(
        ingested=len(written), highest_seq=highest, rule_ids=tuple(written)
    )


def unattributed(rows: Sequence[DecisionRow]) -> list[int]:
    """Decision sequences carrying no rule identifier.

    FR-011's property read from the *reader's* side. The Go writer's schema has
    `CHECK (length(rule_id) > 0)`, so this should always be empty against a log
    that component wrote; it is computed here because the check that matters is
    over the log the runtime actually read, not over the schema it was promised.
    """
    return [row.seq for row in rows if not row.rule_id.strip()]
