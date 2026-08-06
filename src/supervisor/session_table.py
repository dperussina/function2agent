"""The session and lease tables. **Owned by the supervisor, written by nobody
else** (T-06's single-writer-per-table ownership map).

Pulled forward from Phase 2's storage tier because FR-050 layer 1 makes the
proxy resolve an opaque handle against this table on *every* request, so the
enforcement point cannot be built without it. What was pulled forward was one
table and its writer, with the repository interface of T016, the ownership map
of T017 and the concurrent-writer probe of T050 recorded as owed. **All three
have since landed and this file now sits on all three**: every statement below
goes through `Repository`, the table is declared in `ownership.py` and opened
as the role that owns it, and the cold-start race the migration exists to
remove is exercised by T050's probe.

**What the migration bought, measured rather than argued.** Before it,
`__init__` ran a schema script whose first statement was the WAL journal-mode
pragma, so a second process first-opening a brand-new store was refused with
`SQLITE_BUSY` in 0.163ms — *four orders of magnitude inside* a 5s busy timeout,
because SQLite bypasses the busy handler on the conversion path deliberately
and no timeout ever covered it — and the script aborted **before** the table
was created, leaving a file whose only table was the planted one. Reproduced
with four processes meeting at a barrier, twelve trials of four opens each:
**8 of 12 trials produced at least one loser, 17 losers over 48 opens.** The
race is probabilistic, so that count is the reading of one run and not a
constant; what does not vary across runs is that it is nowhere near zero.
`Repository._enter_wal` converges on the end state instead, and the same probe
run immediately afterwards gives **0 of 12 and 0 of 48**.

All six writes plus construction also leaked raw `sqlite3.OperationalError`,
both reads surviving; under a planted `EXCLUSIVE` holder the same eight calls
now give 0 leaks, 6 `StoreWedgedError` and the same 2 reads. That is what lets
`LeaseRenewer` tell momentary contention from a wedged store instead of dying
on both. Construction under a *permanently* held lock still raises — it must,
since there is no end state to converge on — but it raises `StoreBusyError`
after the convergence window under `RESERVED` and `StoreWedgedError` after the
whole busy timeout under `EXCLUSIVE`, which are different facts rather than one
undifferentiated engine error.

**The one thing this table does differently, and it is declared not improvised.**
`session` is `scope_per_row` in the ownership map. The supervisor is one
process serving every tenant, and `resolve()` looks a row up by an opaque
capability digest *before* the tenant is knowable — so there is no scope a
connection here could be opened as, and FR-035's two columns travel on the row
with this layer requiring them rather than supplying them. See the `session`
row in `ownership.py` for the whole argument.

The handle itself is never stored. The column is a SHA-256 of it, so a reader
of this database — including the proxy, which opens it read-only — holds
nothing it could replay.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from src.contracts import terminal
from src.contracts.ownership import ROLE_SUPERVISOR
from src.contracts.repository import NotEqual, Repository

STATE_STARTING = "STARTING"
STATE_RUNNING = "RUNNING"
STATE_TERMINATED = "TERMINATED"
# `data-model.md` §2.1's interrupted state. See the note on the same constant in
# `src/contracts/transition.py`: not terminal. Both edges are the runner's (T046);
# rebuilding an interrupted attempt's transcript over them is T052's.
STATE_INTERRUPTED = "INTERRUPTED"

TABLE = "session"

#: The table, as column names and portable types rather than as SQL. The two
#: scope columns are **absent on purpose**: `Repository.create_table` declares
#: them itself and refuses a caller that names them, so that a table cannot
#: exist without them and cannot exist with two definitions of them.
COLUMNS = {
    "session_id": "text primary key",
    "state": "text not null",
    "terminal_state": "text",
    "capability_sha256": "text not null",
    "lease_expires_at": "real not null",
    "created_at": "real not null",
}

#: `capability_sha256` is unique **globally**, not per tenant, and that is the
#: same fact as `session` being `scope_per_row`. `resolve()` is handed a digest
#: and nothing else; if two tenants could hold one digest there would be no
#: predicate able to say which row was meant. The repository drops its usual
#: scope prefix on a per-row table's unique groups for exactly this reason.
UNIQUE = [["capability_sha256"]]


@dataclass(frozen=True)
class SessionRow:
    session_id: str
    tenant_id: str
    deployment_id: str
    state: str
    terminal_state: str | None
    capability_sha256: str
    lease_expires_at: float
    created_at: float

    def honoured_at(self, now: float) -> bool:
        """The proxy's stage-1 predicate, stated once so both sides agree."""
        return self.state == STATE_RUNNING and self.lease_expires_at > now


def capability_digest(handle: str) -> str:
    return hashlib.sha256(handle.encode("utf-8")).hexdigest()


class SessionTable:
    """The supervisor's writer. Opens read-write; the proxy opens `?mode=ro`."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Opened AS the supervisor, which is the role `ownership.py` names as
        # `session`'s sole writer, so a future caller that opened this from the
        # runtime is refused before any statement is built rather than after.
        #
        # `unscoped`, because the scope is on the row here — see the module
        # docstring and the `session` entry in the ownership map. It is not a
        # way around FR-035: an unscoped repository cannot touch a table that
        # is not declared `scope_per_row`, and this one requires both columns
        # on every insert.
        #
        # **What used to be here.** A bare `sqlite3.connect` and an
        # `executescript` beginning with `PRAGMA journal_mode=WAL`, plus a
        # `threading.Lock` and `check_same_thread=False` — the latter added
        # because the lease renewer runs on its own thread (FR-050 layer 2)
        # and the default same-thread guard killed that thread *silently*, so
        # the session's lease lapsed for a reason nobody could see. Lapsing is
        # fail-closed, so nothing was unsafe; it was undiagnosable, which is
        # its own defect. All of it is `Repository`'s now: the reentrant lock,
        # the cross-thread connection, the WAL convergence and the error
        # translation, each with its own guard and its own probe.
        self._repo = Repository.unscoped(str(self.path), role=ROLE_SUPERVISOR)
        self._repo.create_table(TABLE, COLUMNS, unique=UNIQUE)

    def close(self) -> None:
        self._repo.close()

    def __enter__(self) -> "SessionTable":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def _guarded(self, session_id: str, *, was: str, **values: Any) -> int:
        """A state-guarded update. Rows changed, so the caller can tell.

        The guard is the whole mechanism, and returning the count is what makes
        it observable: an update that matched nothing is indistinguishable from
        one that worked if the caller is handed `None`.
        """
        return self._repo.update(
            TABLE, where={"session_id": session_id, "state": was}, values=values)

    def create(
        self,
        *,
        session_id: str,
        tenant_id: str,
        deployment_id: str,
        capability_sha256: str,
        lease_expires_at: float,
        now: float | None = None,
    ) -> None:
        created = time.time() if now is None else now
        self._repo.insert(TABLE, {
            "tenant_id": tenant_id,
            "deployment_id": deployment_id,
            "session_id": session_id,
            "state": STATE_STARTING,
            "terminal_state": None,
            "capability_sha256": capability_sha256,
            "lease_expires_at": lease_expires_at,
            "created_at": created,
        })

    def mark_running(self, session_id: str) -> int:
        """STARTING → RUNNING. Returns rows changed.

        The count used to be discarded. A guarded update that matches nothing
        is indistinguishable from one that worked when the caller is handed
        `None`, and the guard is the whole mechanism — so the caller gets the
        count and `SessionStateMachine` refuses on zero.
        """
        return self._guarded(session_id, was=STATE_STARTING, state=STATE_RUNNING)

    def mark_interrupted(self, session_id: str) -> int:
        """RUNNING → INTERRUPTED. Returns rows changed.

        The lease is deliberately left alone. Interruption is not termination:
        FR-007 resumes this same session and never issues a new capability, so
        driving the lease to zero here would make resume indistinguishable from
        a fresh admission. The state alone is enough to stop the enforcement
        point honouring the handle, because `honoured_at` requires RUNNING.
        """
        return self._guarded(
            session_id, was=STATE_RUNNING, state=STATE_INTERRUPTED)

    def mark_resumed(self, session_id: str, lease_expires_at: float) -> int:
        """INTERRUPTED → RUNNING, renewing the lease (FR-007). Rows changed.

        Guarded on INTERRUPTED rather than on "not terminated", so a resume of
        a terminated session changes nothing rather than reviving it.
        """
        return self._guarded(
            session_id, was=STATE_INTERRUPTED,
            state=STATE_RUNNING, lease_expires_at=lease_expires_at)

    def renew(self, session_id: str, lease_expires_at: float) -> int:
        """Extend the lease. Only a `RUNNING` session's lease is renewable.

        Returns the number of rows changed, so a caller can tell renewal of a
        terminated session apart from renewal of a live one — which is the
        difference between the lease lapsing and the lease being extended past
        a terminal state.
        """
        return self._guarded(
            session_id, was=STATE_RUNNING, lease_expires_at=lease_expires_at)

    def terminate(self, session_id: str, terminal_state: str) -> int:
        """FR-006 — a named terminal state, never a generic error. Rows changed.

        The lease is also driven into the past. Termination and lease
        expiry are two independent reasons the proxy refuses, and setting both
        means a reader that somehow saw a stale `state` still refuses on the
        lease.

        **The check used to be `if not terminal_state`**, which accepted any
        non-empty string — and the cross-language conformance fixture was
        seeded through this method with `"OPERATOR_TERMINATED"`, a string that
        is not a member of the taxonomy at all. FR-006's subject is that the
        recorded outcome is a *named* member, and a non-empty check is not that
        test. Membership is now required here, where the row is written, rather
        than only in `transition.py`, where the span is built: the two are
        written by different code paths and only one of them was guarded.
        """
        terminal.require(terminal_state)
        # `NotEqual` rather than a guard on each non-terminal state: the
        # complement is a list this table would have to keep in step with the
        # state machine, and one that drifted would silently permit a second
        # termination to overwrite the first recorded outcome.
        return self._repo.update(
            TABLE,
            where={"session_id": session_id, "state": NotEqual(STATE_TERMINATED)},
            values={
                "state": STATE_TERMINATED,
                "terminal_state": terminal_state,
                "lease_expires_at": 0,
            },
        )

    def get(self, session_id: str) -> SessionRow | None:
        return _first(self._repo.select(TABLE, where={"session_id": session_id}))

    def resolve(self, capability_sha256: str) -> SessionRow | None:
        """By capability digest, and **without a tenant predicate**.

        Not an omission. FR-050 layer 1 resolves an opaque handle before it
        knows whose it is, which is what `session` being `scope_per_row` in the
        ownership map means; `capability_sha256` is unique globally so the
        answer is still exactly one row or none.
        """
        return _first(
            self._repo.select(TABLE, where={"capability_sha256": capability_sha256}))


def _first(rows: list[Mapping[str, Any]]) -> SessionRow | None:
    if not rows:
        return None
    row = rows[0]
    return SessionRow(
        session_id=row["session_id"],
        tenant_id=row["tenant_id"],
        deployment_id=row["deployment_id"],
        state=row["state"],
        terminal_state=row["terminal_state"],
        capability_sha256=row["capability_sha256"],
        lease_expires_at=row["lease_expires_at"],
        created_at=row["created_at"],
    )
