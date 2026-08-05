"""T017 — data-model.md's single-writer-per-table map, as data the repository enforces.

data-model.md states writer ownership in a table and gives the reason:

    Writer ownership is single per table across the three processes, because
    finding 006 explicitly did not test the session service under concurrent
    writers.

That reason is why this is a mechanism and not a convention. **T-06 records that
v1's store has no observed substrate** — finding 006 measured a session service
that was never exercised under concurrent writers, so there is no evidence that
concurrent writes to these tables behave. Single-writer ownership is how v1
avoids depending on evidence it does not have. A convention would hold until the
first contributor who needed to write a row from the wrong process.

**Enforcement is at the connection, not at the call site.** A `Repository` is
opened *as* a role, and a write to a table that role does not own raises. There
is no "write anyway" argument, because the failure this prevents is somebody
being in a hurry.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

# The three processes, plus the two data-model.md names that are not processes
# but are writers in the map.
ROLE_SUPERVISOR = "supervisor"
ROLE_RUNTIME = "runtime"
ROLE_PROXY = "proxy"
ROLE_ANALYSIS = "analysis"
ROLE_SHADOW_JUDGE = "shadow_judge"

ROLES = frozenset({
    ROLE_SUPERVISOR, ROLE_RUNTIME, ROLE_PROXY, ROLE_ANALYSIS, ROLE_SHADOW_JUDGE,
})


class OwnershipError(PermissionError):
    """A write from a role that does not own the table."""


@dataclass(frozen=True)
class TableOwnership:
    table: str
    writer: str
    readers: frozenset[str]
    note: str = ""


def _own(table: str, writer: str, *readers: str, note: str = "") -> TableOwnership:
    return TableOwnership(table, writer, frozenset(readers), note)


# data-model.md's table, transcribed row by row. The group names there are
# expanded into the individual tables they cover, because ownership is enforced
# per table and a group is not something a connection writes to.
OWNERSHIP: tuple[TableOwnership, ...] = (
    # session, lease, capability → supervisor; read by runtime and proxy.
    _own("session", ROLE_SUPERVISOR, ROLE_RUNTIME, ROLE_PROXY),
    _own("lease", ROLE_SUPERVISOR, ROLE_RUNTIME, ROLE_PROXY),
    _own("capability", ROLE_SUPERVISOR, ROLE_RUNTIME, ROLE_PROXY),

    # turn journal, budget ledger, trace, result, drift signal → runtime.
    _own("turn_journal", ROLE_RUNTIME, ROLE_ANALYSIS),
    _own("budget_ledger", ROLE_RUNTIME, ROLE_ANALYSIS),
    _own("budget_reservation", ROLE_RUNTIME, ROLE_ANALYSIS,
         note="T053's reserve-then-reconcile half (U-30). The measured "
              "consumption is `budget_ledger`; this holds what was reserved "
              "before a call whose cost is not yet known, so that a SIGKILL "
              "during the call over-counts rather than under-counts. "
              "**A second table rather than more rows in budget_ledger**, "
              "because a reservation is released by appending a release row "
              "and `Consumption` refuses a negative — a release expressed as "
              "a correction in budget_ledger would have to be one. Same "
              "writer, same reader, and the same FR-035 scope columns, so the "
              "two are summed by one caller (src/runtime/ledger.py)."),
    _own("session_ceiling", ROLE_RUNTIME, ROLE_ANALYSIS,
         note="FR-005's last clause: 'Every one of the four ceilings, and the "
              "cumulative total against it, MUST be recorded with the "
              "deployment identity it applies to.' The totals are "
              "budget_ledger; this is the ceilings, beside them, in the same "
              "role's store and under the same FR-035 scope columns. "
              "**This row extends data-model.md §0's map rather than "
              "transcribing it** — §2.1 puts `budget` on the Session entity, "
              "whose table is the supervisor's, and T048 puts the store that "
              "persists the four ceilings in src/runtime/. Both cannot be "
              "honoured at once. Recording them from the enforcing role is "
              "the reading that violates neither the ownership map nor the "
              "requirement; writing the supervisor's table from the runtime "
              "would violate the first, and the ceiling not surviving a "
              "resume would violate the second."),
    _own("trace_span", ROLE_RUNTIME, ROLE_ANALYSIS),
    _own("result", ROLE_RUNTIME, ROLE_ANALYSIS),
    _own("drift_signal", ROLE_RUNTIME, ROLE_ANALYSIS),

    # artifact, artifact ref → analysis; read by runtime and proxy.
    _own("artifact", ROLE_ANALYSIS, ROLE_RUNTIME, ROLE_PROXY),
    _own("artifact_ref", ROLE_ANALYSIS, ROLE_RUNTIME, ROLE_PROXY),
    _own("artifact_ref_history", ROLE_ANALYSIS, ROLE_RUNTIME, ROLE_PROXY,
         note="FR-054's retained history. Written by the same role that moves "
              "the ref, so a move and its record cannot come apart."),
    _own("restoration_record", ROLE_ANALYSIS, ROLE_RUNTIME,
         note="FR-054/FR-019: operator, version restored from, version "
              "restored to."),

    # proxy decision log → proxy; read by runtime, which ingests into the trace.
    _own("proxy_decision", ROLE_PROXY, ROLE_RUNTIME),
    _own("filesystem_decision", ROLE_SUPERVISOR, ROLE_RUNTIME,
         note="The seccomp listener runs in the supervisor, so the "
              "filesystem analogue of the proxy decision log is the "
              "supervisor's to write."),

    # judge verdict, human label → shadow judge; reporting only.
    _own("judge_verdict", ROLE_SHADOW_JUDGE,
         note="FR-052 and Principle I: NEVER read by the success path. The "
              "empty reader set is the point — tests/invariants/"
              "test_import_graph.py keeps the module boundary structural."),
    _own("human_label", ROLE_SHADOW_JUDGE,
         note="Adjudication queue. Same reader restriction."),
)

BY_TABLE: Mapping[str, TableOwnership] = {row.table: row for row in OWNERSHIP}
TABLES = frozenset(BY_TABLE)

# Every row in the map names a role that exists.
for _row in OWNERSHIP:
    if _row.writer not in ROLES:
        raise OwnershipError(f"{_row.table}: unknown writer role {_row.writer!r}")
    for _reader in _row.readers:
        if _reader not in ROLES:
            raise OwnershipError(f"{_row.table}: unknown reader role {_reader!r}")


def writer_of(table: str) -> str:
    try:
        return BY_TABLE[table].writer
    except KeyError:
        raise OwnershipError(
            f"{table!r} has no declared writer. Every table has exactly one "
            "(data-model.md §0). A table with no entry is a table nobody "
            "decided the ownership of, which is how two processes end up "
            "writing it."
        ) from None


def require_write(table: str, role: str) -> None:
    owner = writer_of(table)
    if role != owner:
        raise OwnershipError(
            f"{role!r} may not write {table!r}; its sole writer is {owner!r} "
            "(data-model.md §0). v1 has no observed evidence that concurrent "
            "writes to this store behave — finding 006 did not test it — so "
            "single-writer ownership is load-bearing rather than tidy."
        )


def require_read(table: str, role: str) -> None:
    row = BY_TABLE.get(table)
    if row is None:
        raise OwnershipError(f"{table!r} has no declared ownership")
    if role != row.writer and role not in row.readers:
        raise OwnershipError(
            f"{role!r} may not read {table!r}; declared readers are "
            f"{sorted(row.readers) or 'none'} and its writer is {row.writer!r}."
            + (f" {row.note}" if row.note else "")
        )
