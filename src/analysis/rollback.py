"""T020 — rollback as a ref move, with the restoration record FR-054 requires.

FR-054, in its own words:

    restoring the immediately prior version of any one of them MUST be a single
    operator action: no hand-editing of individual entries, no reconstruction
    from a trace, and no restart of the runtime. A restoration MUST be recorded
    exactly as a widening is under FR-019 — the operator, the version restored
    from, the version restored to.

**Three prohibitions, and how each is discharged structurally rather than by
being careful:**

- *No hand-editing.* `restore_previous` takes a kind and an operator and
  nothing else. There is no argument through which an entry could be supplied,
  so there is no version of this call that edits one.
- *No reconstruction from a trace.* The prior address comes from
  `artifact_ref_history`, which the ref move writes in the same transaction.
  Nothing reads a trace.
- *No restart.* The ref is a row. Readers resolve `(deployment_id, kind)` on
  each read, so a moved ref is visible to a running process without anything
  being reloaded. `test_rollback.py` asserts this against a reader that was
  opened before the move.

**The restoration record is written in the same transaction as the move.** A
restoration whose record failed would be an unattributed configuration change,
which is the thing FR-019's review requirement exists to make impossible.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.analysis.artifact_store import ArtifactStore
from src.contracts.repository import Repository

RESTORATION_TABLE = "restoration_record"


class RollbackError(RuntimeError):
    pass


@dataclass(frozen=True)
class Restoration:
    """FR-019's three fields, and the kind they apply to."""

    kind: str
    operator: str
    restored_from: str
    restored_to: str
    at: float

    def to_record(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "operator": self.operator,
            "restored_from": self.restored_from,
            "restored_to": self.restored_to,
            "at": self.at,
        }


def ensure_schema(repository: Repository) -> None:
    repository.create_table(RESTORATION_TABLE, {
        "artifact_kind": "text not null",
        "operator": "text not null",
        "restored_from": "text not null",
        "restored_to": "text not null",
        "at": "real not null",
    })


def restore_previous(
    store: ArtifactStore,
    kind: str,
    *,
    operator: str,
    now: float,
) -> Restoration:
    """The single operator action. One call, one kind, one named human."""
    if not operator:
        raise RollbackError(
            "a restoration must name the operator (FR-054, FR-019). An "
            "unattributed configuration change is not reviewable, and FR-012's "
            "review is what this record feeds."
        )

    current = store.current_ref(kind)
    if current is None:
        raise RollbackError(
            f"{kind} has no current version, so there is nothing to restore "
            "from. This is a first publish, not a rollback."
        )
    previous = store.previous_ref(kind)
    if previous is None:
        raise RollbackError(
            f"{kind} has only ever held one version ({current}). FR-054 asks "
            "for the immediately prior version and there is not one; "
            "restoring would be inventing a target."
        )

    # The move and its record are ONE transaction. `set_ref` opens a nested
    # one, which joins this rather than committing separately — a restoration
    # whose record was committed while the move failed, or the reverse, is an
    # unattributed configuration change, and FR-019's review reads this record.
    with store.repo.transaction():
        store.repo.insert(RESTORATION_TABLE, {
            "artifact_kind": kind,
            "operator": operator,
            "restored_from": current,
            "restored_to": previous,
            "at": now,
        })
        store.set_ref(kind, previous, moved_by=operator, now=now)

    return Restoration(
        kind=kind,
        operator=operator,
        restored_from=current,
        restored_to=previous,
        at=now,
    )


def restorations(repository: Repository, kind: str | None = None) -> list[dict[str, Any]]:
    where = {"artifact_kind": kind} if kind else None
    return repository.select(RESTORATION_TABLE, where=where, order_by="at")
