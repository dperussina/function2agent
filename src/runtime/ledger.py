"""T053 — the reserve-then-reconcile budget ledger (T-07, **U-30**, SC-030).

`BudgetJournal` accrues *after* the model call. U-30 is what that loses: a
`SIGKILL` during the call — and FR-049's `memory.oom.group` kill is exactly
that, with no unwind and no flush — leaves the spend unrecorded, so a resumed
process reads a total lower than what was really spent and a ceiling that should
have fired does not. **Reserving before the call inverts the error**: the crash
counts the reservation, which is too much rather than too little.

**The claim this makes, stated narrowly because the wide version is false.** The
reservation is an estimate, so a crash loses `actual − reserved` whenever the
actual is larger. That residue cannot be removed without knowing a call's cost
before making it, which is T062's per-provider cost table and does not exist
yet. What this mechanism does establish:

1. the total is never **lower** after a crash than it was before it, because
   nothing is ever removed and an unreconciled reservation keeps counting; and
2. a turn that reached the provider is counted even when nothing came back.

Both hold unconditionally. The stronger reading — that the recorded spend equals
the real spend across a crash — is not available at v1 and is not implied here.

**Append-only, like the ledger it sits on.** `trace_budget.py`'s docstring gives
the reason: *"a running total kept as a mutable row is one interrupted write away
from being wrong in the direction that matters"*. So a reservation is not a row
whose status is flipped — releasing it appends a second row, and *outstanding*
means a `reserve` with no matching `release`. Nothing here rewrites a row, so an
interrupted `reconcile` leaves the reservation outstanding — the over-counting
direction rather than the other one.

**Why `reconcile` is one transaction.** It appends the release and the measured
consumption together. Split, a crash between them would release a reservation
without recording what replaced it — the only ordering that produces an
under-count, and the one thing this module exists to prevent.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any

from src.contracts.repository import UniquenessError
from src.runtime.trace_budget import BudgetJournal, Consumption, Totals

TABLE = "budget_reservation"

# Append-only: a reservation is released by a second row, never by rewriting the
# first. See the module docstring.
KIND_RESERVE = "reserve"
KIND_RELEASE = "release"
KINDS: frozenset[str] = frozenset({KIND_RESERVE, KIND_RELEASE})


class LedgerError(RuntimeError):
    """A reservation that cannot be made, or reconciled, as described."""


@dataclass(frozen=True)
class ReservationPolicy:
    """What goes on the ledger before a call whose cost is not yet known.

    **No default, and the reason is not tidiness.** A default would be a number
    nobody chose standing in for accounting this ledger reports as fact, and it
    would be silently wrong in the under-counting direction the moment a call
    cost more than it. `Ceilings` refuses an unset ceiling on the same grounds:
    FR-005 forbids *"filling it from a default this specification did not
    state"*.

    **These figures are the operator's declaration, not a measurement.** T062
    is the per-provider cost table that will derive them, and finding 003
    already showed per-provider cost cannot be assumed uniform — so a single
    pair of numbers here is an approximation by construction. Its job is to
    bound the crash window, not to price a call.

    `turns` is the one figure that is exact: a call being made is one turn. It
    is therefore fixed at one or more, and a policy claiming zero is refused —
    that would leave the turn ceiling accruing only after the call returns,
    which is an under-count on the one dimension where no estimate is needed.
    """

    spend_usd: float
    tokens: int
    wall_clock_seconds: float = 0.0
    turns: int = 1

    def __post_init__(self) -> None:
        for name in ("spend_usd", "tokens", "wall_clock_seconds", "turns"):
            value = getattr(self, name)
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise LedgerError(f"the {name} reservation is not a number: {value!r}")
            if value < 0:
                raise LedgerError(
                    f"the {name} reservation is negative ({value}). A negative "
                    "reservation lowers the total before the call is made, "
                    "which is the under-count this module exists to prevent."
                )
        if self.turns < 1:
            raise LedgerError(
                f"the turns reservation is {self.turns}. A call being made is "
                "one turn — that figure is exact, not estimated — so reserving "
                "none of it leaves the turn ceiling counting only calls that "
                "came back."
            )


@dataclass(frozen=True)
class Reservation:
    """One outstanding reservation, as the table holds it.

    Carries its own figures rather than a reference to the policy, so that a
    policy changed between the reserve and the reconcile cannot retroactively
    alter what was reserved.
    """

    session_id: str
    turn: int
    ordinal: int
    spend_usd: float
    tokens: int
    wall_clock_seconds: float
    turns: int
    at: float

    @property
    def key(self) -> tuple[str, int, int]:
        return (self.session_id, self.turn, self.ordinal)


class BudgetLedger:
    """`BudgetJournal` plus the reservations that cover the calls in flight.

    `totals()` is the journalled total **plus every outstanding reservation**,
    which is what makes it the number a ceiling may safely be compared against:
    it is never below what has been committed to.
    """

    def __init__(self, journal: BudgetJournal, *, policy: ReservationPolicy) -> None:
        self.journal = journal
        self.policy = policy
        self.repo = journal.repo
        # Covers the read-then-write in `reconcile`. Across processes the unique
        # index below is what refuses a second release.
        self._lock = threading.Lock()
        self.repo.create_table(TABLE, {
            "session_id": "text not null",
            "turn": "int not null",
            "ordinal": "int not null",
            "kind": "text not null",
            "spend_usd": "real not null",
            "tokens": "int not null",
            "wall_clock_seconds": "real not null",
            "turns": "int not null",
            "at": "real not null",
        }, unique=[["session_id", "turn", "ordinal", "kind"]])

    # -- the two halves ----------------------------------------------------

    def reserve(
        self, session_id: str, *, turn: int, ordinal: int = 0, at: float
    ) -> Reservation:
        """Put the policy's figures on the ledger **before** the call.

        Returns the reservation so the caller hands the same object back to
        `reconcile`. Re-deriving the coordinates there would be a second chance
        to name a different turn.
        """
        if turn < 0 or ordinal < 0:
            raise LedgerError(
                f"(turn {turn}, ordinal {ordinal}) is not a position")
        reservation = Reservation(
            session_id=session_id, turn=turn, ordinal=ordinal,
            spend_usd=float(self.policy.spend_usd),
            tokens=int(self.policy.tokens),
            wall_clock_seconds=float(self.policy.wall_clock_seconds),
            turns=int(self.policy.turns),
            at=at,
        )
        self._append(reservation, kind=KIND_RESERVE, at=at,
                     refusal="already reserved")
        return reservation

    def reconcile(
        self,
        reservation: Reservation,
        *,
        spend_usd: float,
        tokens: int,
        wall_clock_seconds: float,
        at: float,
    ) -> Totals:
        """Release the estimate and record the measurement, in one transaction.

        The pair is atomic because the split version has a crash window that
        under-counts: released, with nothing yet in its place.
        """
        with self._lock:
            if reservation.key not in {r.key for r in self.outstanding(
                    reservation.session_id)}:
                raise LedgerError(
                    f"{reservation.key} has no outstanding reservation. Either "
                    "it was already reconciled, or it was never reserved and "
                    "the call it covers was made unbudgeted."
                )
            with self.repo.transaction():
                self._append(reservation, kind=KIND_RELEASE, at=at,
                             refusal="already reconciled")
                self.journal.accrue(Consumption(
                    session_id=reservation.session_id,
                    turn=reservation.turn,
                    ordinal=reservation.ordinal,
                    spend_usd=spend_usd,
                    tokens=tokens,
                    wall_clock_seconds=wall_clock_seconds,
                    turns=reservation.turns,
                    at=at,
                ))
        return self.totals(reservation.session_id)

    # -- reads -------------------------------------------------------------

    def totals(self, session_id: str) -> Totals:
        """The journalled total plus every reservation still outstanding.

        Recomputed from rows on every call. There is no cached number here for
        the same reason there is none in `BudgetJournal` or `SessionStore`:
        finding 006's ceiling of 3 permitted 6 cycles because the count lived
        somewhere a new attempt rebuilt.
        """
        committed = self.journal.totals(session_id)
        held = self.outstanding(session_id)
        return Totals(
            spend_usd=committed.spend_usd + sum(r.spend_usd for r in held),
            tokens=committed.tokens + sum(r.tokens for r in held),
            wall_clock_seconds=(committed.wall_clock_seconds
                                + sum(r.wall_clock_seconds for r in held)),
            turns=committed.turns + sum(r.turns for r in held),
        )

    def committed(self, session_id: str) -> Totals:
        """The journalled total alone, with no reservations in it.

        Exposed so a report can say *what was measured* separately from *what is
        covered*. A single number that silently mixes the two would make an
        over-count indistinguishable from a charge.
        """
        return self.journal.totals(session_id)

    def outstanding(self, session_id: str) -> tuple[Reservation, ...]:
        """Reserves with no matching release, in `(turn, ordinal)` order."""
        rows = self.repo.select(TABLE, where={"session_id": session_id})
        reserved: dict[tuple[int, int], dict[str, Any]] = {}
        released: set[tuple[int, int]] = set()
        for row in rows:
            key = (int(row["turn"]), int(row["ordinal"]))
            kind = str(row["kind"])
            if kind == KIND_RESERVE:
                reserved[key] = row
            elif kind == KIND_RELEASE:
                released.add(key)
            else:
                # Enumerated, never complemented: an unrecognised kind is not
                # read as "not a release, so still outstanding". Either default
                # is wrong for a value nobody anticipated, so neither is taken.
                raise LedgerError(
                    f"unrecognised ledger kind {kind!r} in {TABLE}; the "
                    f"declared set is {sorted(KINDS)}"
                )
        return tuple(
            Reservation(
                session_id=session_id,
                turn=key[0],
                ordinal=key[1],
                spend_usd=float(row["spend_usd"]),
                tokens=int(row["tokens"]),
                wall_clock_seconds=float(row["wall_clock_seconds"]),
                turns=int(row["turns"]),
                at=float(row["at"]),
            )
            for key, row in sorted(reserved.items())
            if key not in released
        )

    # -- pass-through ------------------------------------------------------

    def accrue(self, consumption: Consumption) -> Totals:
        """Record consumption that was measured rather than estimated.

        Not everything is reserved: a figure already known when it is written —
        wall clock at the end of a turn — has nothing to estimate, and putting
        it through a reservation would invent an estimate for a measurement.
        """
        self.journal.accrue(consumption)
        return self.totals(consumption.session_id)

    def entries(self, session_id: str) -> list[dict[str, Any]]:
        return self.journal.entries(session_id)

    # -- internals ---------------------------------------------------------

    def _append(
        self, reservation: Reservation, *, kind: str, at: float, refusal: str
    ) -> None:
        try:
            self.repo.insert(TABLE, {
                "session_id": reservation.session_id,
                "turn": reservation.turn,
                "ordinal": reservation.ordinal,
                "kind": kind,
                "spend_usd": reservation.spend_usd,
                "tokens": reservation.tokens,
                "wall_clock_seconds": reservation.wall_clock_seconds,
                "turns": reservation.turns,
                "at": at,
            })
        except UniquenessError:
            raise LedgerError(
                f"{reservation.key} is {refusal}. The refusal comes from the "
                "store's unique index rather than from this object, because "
                "the second attempt in the case that matters is made by a "
                "different process after the first was killed."
            ) from None
