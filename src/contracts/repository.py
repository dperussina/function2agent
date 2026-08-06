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

*This obligation is about SQL and its check is a scanner over source text.* It
has never said anything about exceptions, and two paraphrases elsewhere in the
tree assert that it does. The extension is real but it is **derived**, and it
is stated here rather than left to be inferred from `UniquenessError`'s
docstring: the obligation's own reason — "the substrate can be replaced without
touching a caller" — is not satisfied by a caller that writes
`except sqlite3.OperationalError` around a repository call, because that caller
is edited when the substrate moves for exactly the reason a caller holding SQL
is. So the rule this layer actually enforces is the wider one: **no engine
type crosses this boundary, in either direction.** `UniquenessError` was the
first instance and was for years the only one, which is why the leak below went
unnoticed on five methods at once.

**Scope is the whole surface, construction included.** A caller that must guard
`Repository(...)` against `sqlite3.OperationalError` is as coupled to SQLite as
one that must guard `insert`. Construction is where the leak was measured, but
it was never only there.

**3. Single-writer ownership (T017).** A repository is opened AS a role, and
writing a table that role does not own raises before any SQL is built.

**Why WAL.** One writer and several readers is exactly WAL's shape: readers do
not block the writer and the writer does not block readers. It is chosen for
the access pattern the ownership map already forces, not as a general default.
"""

from __future__ import annotations

import sqlite3
import threading
import time
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

#: How long SQLite's own busy handler may wait for a lock before giving up.
#: Set explicitly rather than left to `sqlite3.connect`'s default, because the
#: classification below asks "did the busy handler run to exhaustion?" and that
#: question has no answer against a number a library may change.
BUSY_TIMEOUT_S = 5.0

#: How long a losing first-opener waits for the *winner* to finish putting a
#: brand-new file into WAL. Measured on this platform at under 3ms, usually on
#: the first read (T050's convergence arm). Two orders of magnitude above that
#: so a loaded machine is never mistaken for a held lock, and an order of
#: magnitude *below* `BUSY_TIMEOUT_S` so that waiting out this window can never
#: be confused with waiting out a lock.
CONVERGENCE_WINDOW_S = 0.5
_CONVERGENCE_POLL_S = 0.002

#: The share of the busy timeout that counts as "the handler ran to
#: exhaustion". Measured refusals fall either side of a four-order-of-magnitude
#: gap — ~0.1ms when the handler is bypassed, ~5000ms when it is exhausted — so
#: nothing observed lands near this threshold and it is not delicate.
_EXHAUSTED_FRACTION = 0.5

#: `Repository.wal_entry`: this connection's own pragma put the file into WAL,
#: or found it already there. The two are one value because SQLite reports the
#: resulting mode either way and telling them apart would cost an extra read
#: for nothing.
WAL_ENTRY_SELF = "self"
#: `Repository.wal_entry`: this connection's pragma was refused and it observed
#: another process's conversion instead. Recorded rather than discarded because
#: it is invisible afterwards — the store ends up identical — and it is the one
#: path that used to raise `sqlite3.OperationalError` out of `__init__`. A test
#: that means to exercise it can otherwise only hope it did.
WAL_ENTRY_PEER = "peer"

#: Every extended result code that means contention rather than damage.
_LOCK_ERRORNAMES = frozenset({
    "SQLITE_BUSY", "SQLITE_BUSY_RECOVERY", "SQLITE_BUSY_SNAPSHOT",
    "SQLITE_BUSY_TIMEOUT", "SQLITE_LOCKED", "SQLITE_LOCKED_SHAREDCACHE",
})


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


class StoreUnavailableError(RepositoryError):
    """The store could not be reached at all.

    Distinct from `ScopeError` and `UniquenessError`, which say the caller
    asked for something the *data* refuses. This says the caller asked for
    something reasonable and the store was not there to do it, so retrying the
    identical call is sometimes right — which is never true of the other two.

    The three subclasses exist because an operator does something different for
    each, and one flat "database error" would throw that decision away. Each is
    raised only on evidence this layer actually has; see `_lock_failure`.
    """


class StoreBusyError(StoreUnavailableError):
    """Another connection held a lock, and SQLite refused without waiting.

    SQLite bypasses the busy handler when waiting could deadlock, so this is
    the shape of *momentary* contention: the refusal came back immediately
    rather than after the busy timeout. The operation did not happen and
    nothing is known to be stuck, so retrying is reasonable.
    """


class StoreWedgedError(StoreUnavailableError):
    """A lock outlasted the entire busy timeout.

    The busy handler ran to exhaustion, which means one connection held the
    lock for `BUSY_TIMEOUT_S` without letting go. Nothing healthy does that:
    the writes this layer performs are single statements. This is the signature
    of the defect T050 already found once — a connection left holding a write
    lock by a statement that failed inside an implicit transaction — and of its
    cousin, a process that died mid-transaction. Retrying will not help; the
    holder has to be found.
    """


class StoreUnusableError(StoreUnavailableError):
    """Not contention at all — the store cannot be used.

    A missing directory, a read-only filesystem, a corrupt file, a full disk.
    Kept apart from the two above because waiting changes nothing here, and an
    operator who reads "busy" for a corrupt file looks in the wrong place.
    """


def _is_lock_error(exc: BaseException) -> bool:
    """Whether an engine error is contention rather than damage.

    `sqlite3` maps `SQLITE_BUSY`, `SQLITE_LOCKED`, a missing file, a read-only
    filesystem and several schema errors all onto `OperationalError`, so the
    class alone does not answer this. `sqlite_errorname` (3.11+) does, and is
    preferred; the message match is the fallback for anything that does not
    carry one.
    """
    name = getattr(exc, "sqlite_errorname", None)
    if name is not None:
        return name in _LOCK_ERRORNAMES
    return "is locked" in str(exc).lower()


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
        # Which of the two ways this connection reached WAL. See the constants.
        self.wal_entry = WAL_ENTRY_SELF
        try:
            self._conn = sqlite3.connect(
                str(path), check_same_thread=False, timeout=BUSY_TIMEOUT_S)
        except sqlite3.Error as exc:
            raise StoreUnusableError(
                f"{self.path}: the store could not be opened ({exc})."
            ) from None
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._enter_wal()
            with self._engine_errors("configuring the connection"):
                self._conn.execute("PRAGMA foreign_keys=ON")
                self._conn.execute("PRAGMA synchronous=NORMAL")

    # -- opening -----------------------------------------------------------

    def _enter_wal(self) -> None:
        """Put the file into WAL, or establish that another process already did.

        **The failure this exists for.** `PRAGMA journal_mode=WAL` on a
        brand-new file is refused with `SQLITE_BUSY` when several processes run
        it at once — measured here at 21 of 120 concurrent first opens, and 0
        of 120 once the file is already in WAL. It is refused *immediately*, in
        about 100 microseconds, with a five-second busy timeout configured and
        in force. That is deliberate, and it is two separate bypasses in
        SQLite's own source rather than an accident:

        - the conversion runs `sqlite3BtreeSetVersion`, which opens a **read**
          transaction and then promotes it, and btree's busy-retry loop is
          gated on `pBt->inTransaction==TRANS_NONE` — so holding the read
          transaction disables it;
        - the promotion then reaches `sqlite3PagerBegin`, whose own comment
          reads "The busy-handler callback can be used when upgrading to the
          EXCLUSIVE lock, but not when obtaining the RESERVED lock."

        Both are the deadlock avoidance `sqlite3_busy_handler` documents: two
        processes each promoting a read lock would wait on each other forever,
        so SQLite refuses one instead of hanging both. **No busy timeout will
        ever cover this**, which rules out the smallest repair.

        **Why this is convergence and not a retry.** A retry loop cannot tell a
        sibling that is one millisecond from succeeding from a lock held by a
        crashed process, because both refuse the pragma identically — so it
        would wait out its budget on the second and turn T050's own earlier
        defect, a held write lock, into a slow open. It is also unnecessary.
        The losers wanted the file in WAL; the winner puts it there. Measured,
        every one of 45 losers observed WAL within 3ms and 34 of them on their
        first read. So the wait here is for the *end state*, not for the lock,
        and a database that is genuinely wedged never reaches it: whoever holds
        that lock is not converting anything, the mode stays `delete`, and the
        window expires into a named error instead of a silent slow success.

        The two waits are also different lengths on purpose — `BUSY_TIMEOUT_S`
        is ten times `CONVERGENCE_WINDOW_S` — so "waited for a sibling" and
        "waited for a lock" cannot be confused by their duration either.
        """
        began = time.monotonic()
        try:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self.wal_entry = WAL_ENTRY_SELF
            return
        except sqlite3.Error as exc:
            refused_in = time.monotonic() - began
            if not _is_lock_error(exc):
                raise StoreUnusableError(
                    f"{self.path}: the store could not be put into WAL mode "
                    f"({exc}). This is not lock contention."
                ) from None
            if refused_in >= BUSY_TIMEOUT_S * _EXHAUSTED_FRACTION:
                # The handler was available here and ran to exhaustion, so
                # there is nothing to converge on: somebody held the lock for
                # the whole timeout. Say so now rather than spending the
                # convergence window re-reading a file nobody is converting.
                raise self._wedged("putting the store into WAL mode",
                                   refused_in) from None

        deadline = time.monotonic() + CONVERGENCE_WINDOW_S
        while True:
            try:
                if self._read_journal_mode() == "wal":
                    self.wal_entry = WAL_ENTRY_PEER
                    return
            except sqlite3.Error as exc:
                if not _is_lock_error(exc):
                    raise StoreUnusableError(
                        f"{self.path}: the store's journal mode could not be "
                        f"read ({exc})."
                    ) from None
            if time.monotonic() >= deadline:
                raise StoreBusyError(
                    f"{self.path}: another process holds a write lock on this "
                    f"store and it did not clear in {CONVERGENCE_WINDOW_S}s, "
                    "so the store was left in a journal mode this layer does "
                    "not run against. Nothing was written and the connection "
                    "is not usable. Either several processes are opening a "
                    "brand-new store under load, in which case retrying will "
                    "work, or a lock is held by a process that is not "
                    "converting it — which the WAL conversion always is, so a "
                    "lock that outlives this window belongs to something else."
                )
            time.sleep(_CONVERGENCE_POLL_S)

    def _read_journal_mode(self) -> str:
        """The mode **the file** is in, not the mode this connection remembers.

        `PRAGMA journal_mode` in its query form returns the pager's own cached
        value and never looks at the file. A connection that opened a
        rollback-journal database and had it converted to WAL underneath it by
        another process goes on answering `delete` indefinitely — measured at
        3.7 million consecutive stale reads over five seconds. The pager only
        notices when it takes a read transaction and re-reads page 1, so one is
        forced first. Getting this wrong would make the convergence check above
        a loop that can never succeed.
        """
        self._conn.execute("SELECT count(*) FROM sqlite_master").fetchone()
        return str(self._conn.execute("PRAGMA journal_mode").fetchone()[0]).lower()

    # -- engine errors -----------------------------------------------------

    def _wedged(self, what: str, waited: float) -> StoreWedgedError:
        return StoreWedgedError(
            f"{self.path}: {what} waited {waited:.1f}s — the whole busy "
            "timeout — and the lock was still held. Every write this layer "
            "performs is a single statement, so nothing healthy holds a lock "
            "that long. Look for a process that died mid-transaction, or a "
            "connection left inside an implicit transaction by a statement "
            "that failed and was not rolled back. Retrying will not clear it."
        )

    @contextmanager
    def _engine_errors(self, what: str) -> Iterator[None]:
        """Translate SQLite's exceptions into this layer's, or let them pass.

        Every statement this class runs goes through here, so that the module
        docstring's second obligation holds on the whole surface rather than
        on the one method somebody remembered. `IntegrityError` is deliberately
        re-raised untouched: `insert` and `_create_unique_index` turn it into
        `UniquenessError` with the table and key in the message, which is more
        than this can say.

        The busy/wedged split is drawn from what SQLite actually did rather
        than from the message, which is `database is locked` for both. For an
        ordinary statement the busy handler *is* available, so a refusal that
        took the whole timeout means a lock was held that long, and one that
        came back immediately means SQLite declined to wait.
        """
        began = time.monotonic()
        try:
            yield
        except sqlite3.IntegrityError:
            raise
        except sqlite3.Error as exc:
            waited = time.monotonic() - began
            if not _is_lock_error(exc):
                raise StoreUnusableError(f"{self.path}: {what} failed ({exc}).") \
                    from None
            if waited >= BUSY_TIMEOUT_S * _EXHAUSTED_FRACTION:
                raise self._wedged(what, waited) from None
            raise StoreBusyError(
                f"{self.path}: {what} was refused because another connection "
                f"holds a lock ({exc}). SQLite returned immediately rather "
                "than waiting, which it does when waiting could deadlock, so "
                "this is momentary contention and nothing is known to be "
                "stuck. Nothing was written. Retrying is reasonable."
            ) from None

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
        with self._lock, self._engine_errors(f"creating {table}"):
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
            self._rollback_if_outermost()
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
        with self._lock, self._engine_errors(f"inserting into {table}"):
            try:
                self._conn.execute(sql, tuple(scoped.values()))
            except sqlite3.IntegrityError as exc:
                # **The rollback is the load-bearing line.** A statement that
                # fails inside an implicit transaction does not end it, so
                # without this the connection sits holding a write lock and
                # *every other process* writing this file gets `database is
                # locked` — for five seconds, and then an engine-specific
                # exception this layer promises no caller will see. T050's
                # probe measured it: one refused uniqueness insert wedged an
                # unrelated write from a second connection.
                self._rollback_if_outermost()
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
        with self._lock, self._engine_errors(f"updating {table}"):
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
        with self._lock, self._engine_errors(f"reading {table}"):
            rows = self._conn.execute(sql, tuple(params)).fetchall()
        return [dict(row) for row in rows]

    # -- lifecycle ---------------------------------------------------------

    def _commit_if_outermost(self) -> None:
        """Commit only when no `transaction()` is open above this write."""
        if self._depth == 0:
            self._conn.commit()

    def _rollback_if_outermost(self) -> None:
        """End the transaction a failed statement left open, and only that one.

        Inside a `transaction()` the rollback belongs to the context manager,
        which owns the whole group; rolling back here would discard the outer
        transaction's earlier writes on a failure the caller may be about to
        catch.
        """
        if self._depth == 0:
            self._conn.rollback()

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
                    with self._engine_errors("rolling back a transaction"):
                        self._conn.rollback()
                raise
            else:
                self._depth -= 1
                if self._depth == 0:
                    with self._engine_errors("committing a transaction"):
                        self._conn.commit()

    def journal_mode(self) -> str:
        """The journal mode of the file, re-read rather than remembered.

        See `_read_journal_mode`: the pragma's query form answers from the
        pager's cache, so a caller asking this of a connection that did not
        itself perform the conversion could be told `delete` about a file that
        has been in WAL for minutes.
        """
        with self._lock, self._engine_errors("reading the journal mode"):
            return self._read_journal_mode()

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
