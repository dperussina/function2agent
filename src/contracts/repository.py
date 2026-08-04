"""T016 — the repository interface over SQLite in WAL mode (T-06, FR-035, OD-08).

Three obligations, each enforced rather than documented:

**1. Every row carries `tenant_id` and `deployment_id` (FR-035).** Not as a
convention the caller follows but as columns this layer supplies and refuses to
let a caller omit or override. A row with no tenant is a row that a
tenant-scoped query either misses or wrongly returns, and both are worse than a
write that fails.

**2. No engine-specific SQL above the connection layer.** Callers pass table
names and column mappings; they never pass SQL. This is what makes T-06's
"v1's store has no observed substrate" survivable — the substrate can be
replaced without touching a caller. `assert_no_sql_above_the_repository` is the
check, and it scans rather than trusts.

**3. Single-writer ownership (T017).** A repository is opened AS a role, and
writing a table that role does not own raises before any SQL is built.

**Why WAL.** One writer and several readers is exactly WAL's shape: readers do
not block the writer and the writer does not block readers. It is chosen for
the access pattern the ownership map already forces, not as a general default.
"""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

from src.contracts.ownership import (
    ROLES,
    OwnershipError,
    require_read,
    require_write,
)

# The two columns FR-035 requires on every row. Supplied by this layer.
TENANT_COLUMN = "tenant_id"
DEPLOYMENT_COLUMN = "deployment_id"
SCOPE_COLUMNS = (TENANT_COLUMN, DEPLOYMENT_COLUMN)


class RepositoryError(RuntimeError):
    """A repository operation that cannot be performed as described."""


class ScopeError(RepositoryError):
    """A row that would be written without, or against, its declared scope."""


class UniquenessError(RepositoryError):
    """A row that would duplicate a key the table declares unique.

    Typed here rather than left as the engine's own exception, because the
    module docstring's second obligation is that no caller sees engine-specific
    SQL — and a caller catching `sqlite3.IntegrityError` is a caller that has
    to be edited when the substrate moves.
    """


def _quote_identifier(name: str) -> str:
    """The one place an identifier reaches SQL.

    Identifiers cannot be bound as parameters, so they are validated against a
    strict character set and quoted. A table or column name that is not a plain
    identifier is refused rather than escaped — there is no legitimate caller
    that needs one, and accepting them is how an identifier becomes an
    injection point.
    """
    if not name or not name.replace("_", "").isalnum() or name[0].isdigit():
        raise RepositoryError(
            f"{name!r} is not a plain identifier. Table and column names are "
            "not parameterizable, so this layer accepts only [A-Za-z0-9_] "
            "beginning with a letter or underscore."
        )
    return f'"{name}"'


class Repository:
    """A connection opened as one role, scoped to one tenant and deployment."""

    def __init__(
        self,
        path: str | Path,
        *,
        role: str,
        tenant_id: str,
        deployment_id: str,
    ) -> None:
        if role not in ROLES:
            raise OwnershipError(
                f"{role!r} is not a declared role ({sorted(ROLES)}). A "
                "repository has to be opened as somebody."
            )
        if not tenant_id or not deployment_id:
            raise ScopeError(
                "tenant_id and deployment_id are both required (FR-035). A "
                "repository with no scope writes rows a scoped query cannot "
                "find and a cross-tenant query wrongly returns."
            )
        self.role = role
        self.tenant_id = tenant_id
        self.deployment_id = deployment_id
        # Resolved and kept, so a caller that has to reason about *where* the
        # store is can ask the store rather than being told. `BudgetJournal`'s
        # location check took the path as an argument, which made it a check on
        # what the caller asserted rather than on where the rows go.
        self.path = Path(path).resolve()
        # Reentrant, because `transaction()` holds the lock across the writes
        # inside it. A plain Lock deadlocks the moment a caller writes two rows
        # in one transaction, which is the shape every FR-054 ref move has.
        self._lock = threading.RLock()
        # Depth, so a write inside a transaction does not commit on its own.
        # Without this, a transaction is a comment: each statement would commit
        # as it ran and a failure halfway would leave the earlier rows
        # committed — for FR-054 that means a ref moved with no history entry,
        # which is exactly the unrecoverable case retained history prevents.
        self._depth = 0
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._conn.execute("PRAGMA synchronous=NORMAL")

    # -- schema ------------------------------------------------------------

    def create_table(
        self,
        table: str,
        columns: Mapping[str, str],
        *,
        unique: Sequence[Sequence[str]] = (),
    ) -> None:
        """Create `table` with the scope columns prepended.

        The scope columns are added here rather than being the caller's job, so
        that a table cannot exist without them.

        `unique` declares key groups the **store** enforces. A caller that
        guards uniqueness in its own process guards one object in one process:
        a second instance over the same file, or a resumed one after a crash,
        shares nothing with the first. Every group is indexed **with the scope
        columns prepended**, because every read on this table already goes
        through the tenant and deployment predicate — an index that ignored
        them would refuse a second tenant's row for colliding with one that
        tenant cannot see.
        """
        require_write(table, self.role)
        for name in columns:
            if name in SCOPE_COLUMNS:
                raise ScopeError(
                    f"{name!r} is supplied by the repository and must not be "
                    "declared by the caller; two definitions would eventually "
                    "disagree."
                )
        parts = [f"{_quote_identifier(c)} TEXT NOT NULL" for c in SCOPE_COLUMNS]
        parts += [
            f"{_quote_identifier(name)} {_column_type(spec)}"
            for name, spec in columns.items()
        ]
        sql = f"CREATE TABLE IF NOT EXISTS {_quote_identifier(table)} ({', '.join(parts)})"
        with self._lock:
            self._conn.execute(sql)
            self._conn.execute(
                f"CREATE INDEX IF NOT EXISTS {_quote_identifier(table + '_scope')} "
                f"ON {_quote_identifier(table)} "
                f"({_quote_identifier(TENANT_COLUMN)}, {_quote_identifier(DEPLOYMENT_COLUMN)})"
            )
            for group in unique:
                self._create_unique_index(table, group)
            self._commit_if_outermost()

    def _create_unique_index(self, table: str, group: Sequence[str]) -> None:
        """One unique index, or a refusal naming the rows that prevent it.

        This runs against a table that may already hold rows, so it is the
        closest thing in this layer to a migration. SQLite will not build a
        unique index over data that violates it, and the failure it raises
        names neither the table nor the duplicates. Reporting it as-is would
        leave an operator with `UNIQUE constraint failed` and nowhere to go;
        skipping the index on failure would be worse, because the table would
        then be silently back to enforcing nothing.
        """
        if not group:
            raise RepositoryError(
                f"{table}: an empty unique group constrains nothing")
        name = f"{table}_unique_" + "_".join(group)
        columns = ", ".join(
            _quote_identifier(c) for c in (*SCOPE_COLUMNS, *group))
        try:
            self._conn.execute(
                f"CREATE UNIQUE INDEX IF NOT EXISTS {_quote_identifier(name)} "
                f"ON {_quote_identifier(table)} ({columns})"
            )
        except sqlite3.IntegrityError as exc:
            keys = ", ".join((*SCOPE_COLUMNS, *group))
            raise UniquenessError(
                f"{table}: cannot declare ({keys}) unique because rows "
                f"already in the table duplicate it ({exc}). The duplicates "
                f"predate the constraint, so reconcile them before opening "
                f"this table again:\n"
                f"  SELECT {keys}, count(*) FROM {table} "
                f"GROUP BY {keys} HAVING count(*) > 1;\n"
                "The index is not skipped on this failure: a table that "
                "silently went back to enforcing nothing is the defect the "
                "constraint was added for."
            ) from None

    # -- writes ------------------------------------------------------------

    def insert(self, table: str, row: Mapping[str, Any]) -> None:
        require_write(table, self.role)
        if any(c in row for c in SCOPE_COLUMNS):
            raise ScopeError(
                f"{table}: the caller supplied a scope column. tenant_id and "
                "deployment_id come from the repository's own scope; letting "
                "a caller set them makes a cross-tenant write a typo away."
            )
        scoped = {
            TENANT_COLUMN: self.tenant_id,
            DEPLOYMENT_COLUMN: self.deployment_id,
            **row,
        }
        columns = ", ".join(_quote_identifier(c) for c in scoped)
        placeholders = ", ".join("?" for _ in scoped)
        sql = f"INSERT INTO {_quote_identifier(table)} ({columns}) VALUES ({placeholders})"
        with self._lock:
            try:
                self._conn.execute(sql, tuple(scoped.values()))
            except sqlite3.IntegrityError as exc:
                raise UniquenessError(f"{table}: {exc}") from None
            self._commit_if_outermost()

    def update(
        self, table: str, *, where: Mapping[str, Any], values: Mapping[str, Any]
    ) -> int:
        require_write(table, self.role)
        if not where:
            raise RepositoryError(
                f"{table}: an update with no predicate would rewrite every row "
                "in the tenant. Pass the key you mean."
            )
        if any(c in values for c in SCOPE_COLUMNS):
            raise ScopeError(f"{table}: a row's scope is not updatable")
        assignments = ", ".join(f"{_quote_identifier(c)} = ?" for c in values)
        predicate = " AND ".join(f"{_quote_identifier(c)} = ?" for c in where)
        sql = (
            f"UPDATE {_quote_identifier(table)} SET {assignments} "
            f"WHERE {_quote_identifier(TENANT_COLUMN)} = ? "
            f"AND {_quote_identifier(DEPLOYMENT_COLUMN)} = ? AND {predicate}"
        )
        params = (
            *values.values(), self.tenant_id, self.deployment_id, *where.values())
        with self._lock:
            cursor = self._conn.execute(sql, params)
            self._commit_if_outermost()
            return cursor.rowcount

    # -- reads -------------------------------------------------------------

    def select(
        self,
        table: str,
        *,
        where: Mapping[str, Any] | None = None,
        order_by: str | None = None,
        descending: bool = False,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        require_read(table, self.role)
        clauses = [
            f"{_quote_identifier(TENANT_COLUMN)} = ?",
            f"{_quote_identifier(DEPLOYMENT_COLUMN)} = ?",
        ]
        params: list[Any] = [self.tenant_id, self.deployment_id]
        for column, value in (where or {}).items():
            clauses.append(f"{_quote_identifier(column)} = ?")
            params.append(value)
        sql = (
            f"SELECT * FROM {_quote_identifier(table)} WHERE {' AND '.join(clauses)}")
        if order_by:
            sql += f" ORDER BY {_quote_identifier(order_by)}"
            sql += " DESC" if descending else " ASC"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(int(limit))
        with self._lock:
            rows = self._conn.execute(sql, tuple(params)).fetchall()
        return [dict(row) for row in rows]

    # -- lifecycle ---------------------------------------------------------

    def _commit_if_outermost(self) -> None:
        """Commit only when no `transaction()` is open above this write."""
        if self._depth == 0:
            self._conn.commit()

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Group writes so a failure halfway leaves none of them.

        Reentrant: a nested `transaction()` joins the outer one rather than
        starting a second, because SQLite has one transaction per connection
        and a nested commit would end the outer one early.
        """
        with self._lock:
            self._depth += 1
            try:
                yield
            except BaseException:
                self._depth -= 1
                if self._depth == 0:
                    self._conn.rollback()
                raise
            else:
                self._depth -= 1
                if self._depth == 0:
                    self._conn.commit()

    def journal_mode(self) -> str:
        with self._lock:
            return self._conn.execute("PRAGMA journal_mode").fetchone()[0]

    def close(self) -> None:
        with self._lock:
            self._conn.close()


_TYPES = {"text": "TEXT", "int": "INTEGER", "real": "REAL", "blob": "BLOB"}


def _column_type(spec: str) -> str:
    base = spec.split()[0].lower()
    if base not in _TYPES:
        raise RepositoryError(
            f"{spec!r} is not a portable column type ({sorted(_TYPES)}). "
            "Engine-specific types belong below this layer."
        )
    suffix = " ".join(spec.split()[1:]).upper()
    allowed = {"", "PRIMARY KEY", "NOT NULL", "NOT NULL PRIMARY KEY", "UNIQUE"}
    if suffix not in allowed:
        raise RepositoryError(
            f"{spec!r} carries an unsupported constraint {suffix!r}. Allowed: "
            f"{sorted(allowed)}."
        )
    return f"{_TYPES[base]} {suffix}".strip()


# ---------------------------------------------------------------------------
# The "no engine-specific SQL above this layer" check, as a callable so both a
# test and a future lint can use it.

_SQL_TOKENS = ("SELECT ", "INSERT INTO", "UPDATE ", "DELETE FROM", "CREATE TABLE",
               "PRAGMA ", "ALTER TABLE", "DROP TABLE")


def sql_bearing_lines(source: str) -> list[tuple[int, str]]:
    """Lines that look like SQL. Used by the invariant test over `src/`.

    Matched case-sensitively on purpose. SQL in this codebase is written in
    upper case, and matching case-insensitively turns every sentence
    containing "select among" or "update the" into a hit — which is how a
    scanner becomes noise and then gets deleted.
    """
    found = []
    for number, line in enumerate(source.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if any(token in stripped for token in _SQL_TOKENS):
            found.append((number, stripped))
    return found


def scope_columns_of(rows: Sequence[Mapping[str, Any]]) -> set[tuple[str, str]]:
    """Every (tenant, deployment) pair present in `rows`."""
    return {(r[TENANT_COLUMN], r[DEPLOYMENT_COLUMN]) for r in rows}
