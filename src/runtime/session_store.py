"""T048 — the runtime's session store and FR-005's four ceilings (**OD-15**).

**Why the store reads one table and writes another.** `data-model.md` §0 makes
`session` the supervisor's, read by the runtime; §2.1 puts `budget` — the four
ceilings — on the `Session` entity; and T048 puts the store that persists them
in `src/runtime/`. Those three cannot all be honoured literally. The reading
taken here:

- **State, terminal state and lease are read, never written.** They belong to
  the process that owns the session's existence. `LifecycleGateway` is the seam;
  in this process it is the supervisor's `SessionTable`, and across processes it
  is whatever carries the same four calls. The runtime *computes* the transition
  (`session_state.py`) and the owner *applies* it.
- **The four ceilings are written here**, into `session_ceiling`, which the
  runtime owns. FR-005's last clause requires every ceiling and its cumulative
  total to be recorded with the deployment identity it applies to; the totals
  are already `budget_ledger`, and this puts the ceilings beside them under the
  same FR-035 scope columns.

**Why the ceilings are stored at all, given they are configuration.** FR-005
requires the post-resume total to be counted against *the same ceiling*. Read
back from configuration on resume, "the same ceiling" is whatever the
environment says at the moment of resume — so a session that crashed under a
ceiling of 100 can resume under 10 000 with nothing anywhere recording that the
number moved. The ceiling is pinned at creation and reloaded from the store, and
configuration is consulted once.

**What the resume property actually rests on.** Not this module: the totals it
compares against come from `BudgetJournal`, which is append-only and lives
outside the container. This module contributes the other half — the ceiling
survives too — and `evaluate_ceilings` is a pure function of the two so that
neither half can hold a counter. Finding 006's ceiling of 3 permitted 6 cycles
because the counter lived on a context rebuilt per attempt; there is nothing
here for a counter to live on.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from src.contracts import terminal
from src.contracts.config import Config
from src.contracts.repository import Repository, UniquenessError
from src.contracts.transition import PredicateInput
from src.runtime.trace_budget import Totals


class TotalsSource(Protocol):
    """Whatever can answer *what has this session consumed so far*.

    A protocol rather than the concrete `BudgetJournal`, because there are two
    honest answers to that question and a ceiling wants the wider one: the
    committed total (`BudgetJournal`) and the committed total plus the calls in
    flight (`BudgetLedger`, T053). Naming the narrow class here would have made
    the safe reading the harder one to pass in.
    """

    def totals(self, session_id: str) -> Totals: ...

TABLE = "session_ceiling"

# The order is part of the decision, exactly as the three cgroup readings are in
# `bounds.check()`. A session over both its spend and its token ceiling in the
# same pass terminates as `spend_ceiling_reached` **because spend is read
# first**, and that is not recoverable from the resulting terminal state — which
# is why `ST_CEILING_REACHED` declares that it selects among alternatives and
# why every reading is recorded rather than only the one that fired.
CEILING_ORDER: tuple[str, ...] = (
    "spend_usd", "tokens", "wall_clock_seconds", "turns",
)

# Which member of FR-006's taxonomy each ceiling names when it fires.
TERMINAL_BY_CEILING: Mapping[str, str] = {
    "spend_usd": terminal.SPEND_CEILING.name,
    "tokens": terminal.TOKEN_CEILING.name,
    "wall_clock_seconds": terminal.WALL_CLOCK_CEILING.name,
    "turns": terminal.TURN_CEILING.name,
}

CONFIG_BY_CEILING: Mapping[str, str] = {
    "spend_usd": "SESSION_CEILING_SPEND_USD",
    "tokens": "SESSION_CEILING_TOKENS",
    "wall_clock_seconds": "SESSION_CEILING_WALL_CLOCK_SECONDS",
    "turns": "SESSION_CEILING_TURNS",
}


class CeilingsError(RuntimeError):
    """A ceiling that cannot be established, or a session that cannot be."""


@dataclass(frozen=True)
class Ceilings:
    """FR-005's four, all four required.

    `None` is refused rather than read as unbounded. FR-005 is explicit that an
    unset ceiling *"MUST NOT be treated as unbounded"*, and the natural Python
    reading of a missing number — compare against `None`, or skip the check —
    is exactly that treatment. Refusing at construction means no later code has
    to remember.
    """

    spend_usd: float
    tokens: int
    wall_clock_seconds: float
    turns: int

    def __post_init__(self) -> None:
        for name in CEILING_ORDER:
            value = getattr(self, name)
            if value is None:
                raise CeilingsError(
                    f"the {name} ceiling is unset. FR-005 forbids treating an "
                    "unset ceiling as unbounded or filling it from a default "
                    "this specification did not state (Q-10)."
                )
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise CeilingsError(f"the {name} ceiling is not a number: {value!r}")
            if value < 0:
                raise CeilingsError(
                    f"the {name} ceiling is negative ({value}). A negative "
                    "ceiling is reached before the session starts, which is a "
                    "typo rather than a policy."
                )

    @classmethod
    def from_config(cls, config: Config) -> "Ceilings":
        """The four declared keys, and nothing else.

        `load()` has already refused an unset one — this reads what it
        resolved rather than re-deriving the requirement.
        """
        return cls(
            spend_usd=float(config.raw(CONFIG_BY_CEILING["spend_usd"])),
            tokens=int(config.raw(CONFIG_BY_CEILING["tokens"])),
            wall_clock_seconds=float(
                config.raw(CONFIG_BY_CEILING["wall_clock_seconds"])),
            turns=int(config.raw(CONFIG_BY_CEILING["turns"])),
        )

    def to_row(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in CEILING_ORDER}


@dataclass(frozen=True)
class CeilingVerdict:
    """The outcome of one pass over the four ceilings.

    `readings` carries all four whether or not any fired, so that "not
    exceeded" and "not checked" are different records. A field written only on
    the breach is unfalsifiable in absence.
    """

    exceeded: bool
    terminal_state: str | None
    readings: tuple[PredicateInput, ...]


def evaluate_ceilings(ceilings: Ceilings, totals: Totals) -> CeilingVerdict:
    """Compare accrued totals against declared ceilings, in `CEILING_ORDER`.

    A pure function of its two arguments. That is the point: there is no
    instance for a count to accumulate on, so the only way to answer this
    question is to hand over a total that came from somewhere durable.

    `>=` rather than `>`. A ceiling of five turns permits five turns; a session
    that has taken its fifth has reached it. `>` would permit one more than the
    declared number at every ceiling, which is the off-by-one that makes a
    ceiling of 3 look like a ceiling of 4.
    """
    readings: list[PredicateInput] = []
    fired: str | None = None
    for name in CEILING_ORDER:
        declared = getattr(ceilings, name)
        observed = getattr(totals, name)
        breached = observed >= declared
        # Only the first breach is `matched`. Several can be over at once, and
        # the record has to say which one won rather than which ones were over
        # — `StateTransition` refuses a selection with no single winner.
        matched = breached and fired is None
        if matched:
            fired = TERMINAL_BY_CEILING[name]
        readings.append(PredicateInput(
            name=name,
            observed=repr(observed),
            declared=repr(declared),
            matched=matched,
        ))
    return CeilingVerdict(
        exceeded=fired is not None,
        terminal_state=fired,
        readings=tuple(readings),
    )


@dataclass(frozen=True)
class Session:
    """`data-model.md` §2.1, assembled from the two stores it spans."""

    session_id: str
    state: str
    terminal_state: str | None
    lease_expires_at: float
    ceilings: Ceilings


class LifecycleGateway(Protocol):
    """The owner of `session`, as the runtime is allowed to see it.

    Deliberately narrow. The runtime reads a row and asks for a transition; it
    cannot create a session, cannot renew a lease and cannot reach the
    connection. Anything wider and the ownership map would be enforced by
    everyone remembering it.
    """

    def get(self, session_id: str) -> Any: ...
    def mark_running(self, session_id: str) -> int: ...
    def mark_interrupted(self, session_id: str) -> int: ...
    def mark_resumed(self, session_id: str, lease_expires_at: float) -> int: ...
    def terminate(self, session_id: str, terminal_state: str) -> int: ...


class SessionStore:
    """The runtime's view of a session, plus the ceilings it enforces."""

    def __init__(self, repository: Repository, *, lifecycle: LifecycleGateway) -> None:
        self.repo = repository
        self.lifecycle = lifecycle
        self._lock = threading.Lock()
        # `session_id` unique in the store rather than in this object. A second
        # instance over the same file — or a resumed one after a crash — shares
        # no in-process guard with the first, which is the case a `if
        # self.load(...)` check silently fails.
        self.repo.create_table(TABLE, {
            "session_id": "text not null",
            "spend_usd": "real not null",
            "tokens": "int not null",
            "wall_clock_seconds": "real not null",
            "turns": "int not null",
        }, unique=[["session_id"]])

    def create(self, *, session_id: str, ceilings: Ceilings) -> Session:
        """Pin the ceilings for a session the owner has already admitted.

        The session must exist in the lifecycle store first. Creating the
        ceiling row for a session nobody admitted would leave a ceiling with no
        session, and the reverse — a session with no ceiling — is what
        `load()` refuses.
        """
        if self.lifecycle.get(session_id) is None:
            raise CeilingsError(
                f"{session_id!r} is not in the session table. The supervisor "
                "admits a session; the runtime records what bounds it."
            )
        with self._lock:
            try:
                self.repo.insert(TABLE, {
                    "session_id": session_id, **ceilings.to_row()})
            except UniquenessError:
                raise CeilingsError(
                    f"{session_id!r} already has recorded ceilings. Rewriting "
                    "them would move a ceiling under a running session, which "
                    "is the failure FR-005's crash clause is about."
                ) from None
        loaded = self.load(session_id)
        assert loaded is not None  # just inserted, under the lock
        return loaded

    def load(self, session_id: str) -> Session | None:
        """The session as both stores have it, or None if the owner has no row.

        A session the owner knows about but that has no ceiling row raises
        rather than returning a `Session` with something invented, because the
        only two honest answers to "what bounds this session" are the recorded
        number and a refusal.
        """
        row = self.lifecycle.get(session_id)
        if row is None:
            return None
        recorded = self.repo.select(TABLE, where={"session_id": session_id})
        if not recorded:
            raise CeilingsError(
                f"{session_id!r} exists but has no recorded ceilings. FR-005 "
                "forbids treating that as unbounded, so it is a refusal."
            )
        held = recorded[0]
        return Session(
            session_id=session_id,
            state=row.state,
            terminal_state=row.terminal_state,
            lease_expires_at=row.lease_expires_at,
            ceilings=Ceilings(
                spend_usd=held["spend_usd"],
                tokens=int(held["tokens"]),
                wall_clock_seconds=held["wall_clock_seconds"],
                turns=int(held["turns"]),
            ),
        )

    def ceiling_verdict(
        self, session_id: str, journal: TotalsSource
    ) -> CeilingVerdict:
        """The recorded ceilings against the journalled totals.

        Both halves come off disk on every call. That is what makes the answer
        survive a crash: nothing in this object is the count.

        Typed as `TotalsSource` rather than as `BudgetJournal` so that T053's
        `BudgetLedger` — the journal plus the reservations covering the calls in
        flight — is what the loop actually passes. The narrower annotation would
        have read as a claim that the *committed* total is the right one to
        compare a ceiling against, and it is not: the reservation exists so that
        a call in flight counts.
        """
        session = self.load(session_id)
        if session is None:
            raise CeilingsError(f"{session_id!r} has no session row")
        return evaluate_ceilings(session.ceilings, journal.totals(session_id))
