"""The session and lease tables. **Owned by the supervisor, written by nobody
else** (T-06's single-writer-per-table ownership map).

Pulled forward from Phase 2's storage tier because FR-050 layer 1 makes the
proxy resolve an opaque handle against this table on *every* request, so the
enforcement point cannot be built without it. What is pulled forward is one
table and its writer; the repository interface of T016, the ownership map of
T017 and the concurrent-writer probe of T050 are **not** here and are still
owed. T050 in particular is the probe that collapses the +0-to-+4 band on the
runtime-core estimate, and nothing in this slice substitutes for it.

The handle itself is never stored. The column is a SHA-256 of it, so a reader
of this database — including the proxy, which opens it read-only — holds
nothing it could replay.
"""

from __future__ import annotations

import hashlib
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path

STATE_STARTING = "STARTING"
STATE_RUNNING = "RUNNING"
STATE_TERMINATED = "TERMINATED"

SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS session (
  session_id        TEXT PRIMARY KEY,
  tenant_id         TEXT NOT NULL,
  deployment_id     TEXT NOT NULL,
  state             TEXT NOT NULL,
  terminal_state    TEXT,
  capability_sha256 TEXT NOT NULL UNIQUE,
  lease_expires_at  REAL NOT NULL,
  created_at        REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS session_by_capability
  ON session(capability_sha256);
"""


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
        # `check_same_thread=False` with an explicit lock, rather than the
        # default same-thread guard. The lease renewer runs on its own thread
        # (FR-050 layer 2) and the default raises `ProgrammingError` there —
        # which killed the renewer thread *silently*, and the session's lease
        # then lapsed for a reason nobody could see. Lapsing is the fail-closed
        # direction, so nothing was unsafe; it was undiagnosable, which is its
        # own defect. Writing the crash fixture is what surfaced it.
        #
        # This is not a substitute for T050's concurrent-writer probe. One
        # process with one lock is the single-writer case T-06 assumes; the
        # cross-process case is still unmeasured.
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(
            str(self.path), isolation_level=None, check_same_thread=False
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def __enter__(self) -> "SessionTable":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def _exec(self, sql: str, params: tuple) -> sqlite3.Cursor:
        """The one place the connection is touched. Serialized by the lock."""
        with self._lock:
            return self._conn.execute(sql, params)

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
        self._exec(
            "INSERT INTO session (session_id, tenant_id, deployment_id, state, "
            "terminal_state, capability_sha256, lease_expires_at, created_at) "
            "VALUES (?,?,?,?,NULL,?,?,?)",
            (session_id, tenant_id, deployment_id, STATE_STARTING,
             capability_sha256, lease_expires_at, created),
        )

    def mark_running(self, session_id: str) -> None:
        self._exec(
            "UPDATE session SET state=? WHERE session_id=? AND state=?",
            (STATE_RUNNING, session_id, STATE_STARTING),
        )

    def renew(self, session_id: str, lease_expires_at: float) -> int:
        """Extend the lease. Only a `RUNNING` session's lease is renewable.

        Returns the number of rows changed, so a caller can tell renewal of a
        terminated session apart from renewal of a live one — which is the
        difference between the lease lapsing and the lease being extended past
        a terminal state.
        """
        return self._exec(
            "UPDATE session SET lease_expires_at=? "
            "WHERE session_id=? AND state=?",
            (lease_expires_at, session_id, STATE_RUNNING),
        ).rowcount

    def terminate(self, session_id: str, terminal_state: str) -> None:
        """FR-006 — a named terminal state, never a generic error.

        The lease is also driven into the past. Termination and lease
        expiry are two independent reasons the proxy refuses, and setting both
        means a reader that somehow saw a stale `state` still refuses on the
        lease.
        """
        if not terminal_state:
            raise ValueError(
                "terminate() requires a named terminal state; FR-006 forbids "
                "a generic error as a terminal state"
            )
        self._exec(
            "UPDATE session SET state=?, terminal_state=?, lease_expires_at=0 "
            "WHERE session_id=?",
            (STATE_TERMINATED, terminal_state, session_id),
        )

    def get(self, session_id: str) -> SessionRow | None:
        return _row(self._exec(
            "SELECT * FROM session WHERE session_id=?", (session_id,)
        ).fetchone())

    def resolve(self, capability_sha256: str) -> SessionRow | None:
        return _row(self._exec(
            "SELECT * FROM session WHERE capability_sha256=?",
            (capability_sha256,),
        ).fetchone())


def _row(row: sqlite3.Row | None) -> SessionRow | None:
    if row is None:
        return None
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
