"""T038 — budget spans written as consumption accrues, journalled outside the container.

**The failure this exists to prevent, named.** FR-049's memory bound is enforced
by `memory.oom.group`, which kills every process in the session cgroup with no
unwind and no final flush. Accounting held in the workload's memory at that
moment is gone. U-30 and finding 006 are the same shape: **finding 006's failure
was exactly a counter living in the wrong place.**

So two properties, and neither is optional:

1. **Written as consumption accrues, not at the end of a turn.** A ledger
   appended once per turn loses the whole turn to a kill, and a turn is where
   most of the spend is.
2. **Journalled outside the container.** The `Repository` handed in belongs to
   the supervisor-side state directory, not to any path in the session's mount
   namespace. `assert_outside_session_root` checks it, because "outside" is
   easy to believe and easy to get wrong once a scratch volume exists.

**Why the ledger is append-only.** A running total kept as a mutable row is one
interrupted write away from being wrong in the direction that matters — under
the real figure, so a ceiling that should have fired does not. Totals are the
sum of the appended rows, and `totals()` recomputes rather than reading a cached
number.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.contracts.repository import Repository

TABLE = "budget_ledger"


class BudgetError(RuntimeError):
    pass


class JournalLocationError(BudgetError):
    """The ledger is somewhere a cgroup kill would take with it."""


@dataclass(frozen=True)
class Consumption:
    """One increment. Never a total — totals are derived."""

    session_id: str
    turn: int
    ordinal: int
    spend_usd: float
    tokens: int
    wall_clock_seconds: float
    turns: int
    at: float

    def __post_init__(self) -> None:
        for name in ("spend_usd", "tokens", "wall_clock_seconds", "turns"):
            if getattr(self, name) < 0:
                raise BudgetError(
                    f"{name} is negative. A ledger that can be decremented is "
                    "a ledger a ceiling can be walked back under."
                )


@dataclass(frozen=True)
class Totals:
    spend_usd: float
    tokens: int
    wall_clock_seconds: float
    turns: int


def assert_outside_session_root(journal_path: str | Path, session_root: str | Path) -> None:
    """Refuse a journal inside the session's mount namespace root.

    A cgroup kill takes the workload with it; anything written to a path only
    the workload can see goes too. The check is a real path comparison rather
    than a naming convention, because the convention holds until the first
    scratch volume is mounted somewhere convenient.
    """
    journal = Path(journal_path).resolve()
    root = Path(session_root).resolve()
    if journal == root or root in journal.parents:
        raise JournalLocationError(
            f"the budget journal {journal} is inside the session root {root}. "
            "FR-049's memory bound kills the session with no unwind, so a "
            "journal in there loses exactly the accounting that explains why "
            "(U-30; finding 006's counter lived in the wrong place)."
        )


class BudgetJournal:
    """Append-only consumption ledger, outside the container."""

    def __init__(self, repository: Repository, *, session_root: str | Path | None = None,
                 journal_path: str | Path | None = None) -> None:
        if session_root is not None and journal_path is not None:
            assert_outside_session_root(journal_path, session_root)
        self.repo = repository
        self._lock = threading.Lock()
        self.repo.create_table(TABLE, {
            "session_id": "text not null",
            "turn": "int not null",
            "ordinal": "int not null",
            "spend_usd": "real not null",
            "tokens": "int not null",
            "wall_clock_seconds": "real not null",
            "turns": "int not null",
            "at": "real not null",
        })

    def accrue(self, consumption: Consumption) -> Totals:
        """Append one increment and return the totals as at that increment.

        The write happens before the totals are computed and returned, so a
        caller that crashes on the way back has still journalled the spend.
        """
        with self._lock:
            self.repo.insert(TABLE, {
                "session_id": consumption.session_id,
                "turn": consumption.turn,
                "ordinal": consumption.ordinal,
                "spend_usd": consumption.spend_usd,
                "tokens": consumption.tokens,
                "wall_clock_seconds": consumption.wall_clock_seconds,
                "turns": consumption.turns,
                "at": consumption.at,
            })
        return self.totals(consumption.session_id)

    def totals(self, session_id: str) -> Totals:
        """Recomputed from the rows every time. No cached number to drift."""
        rows = self.repo.select(TABLE, where={"session_id": session_id})
        return Totals(
            spend_usd=sum(r["spend_usd"] for r in rows),
            tokens=sum(r["tokens"] for r in rows),
            wall_clock_seconds=sum(r["wall_clock_seconds"] for r in rows),
            turns=sum(r["turns"] for r in rows),
        )

    def entries(self, session_id: str) -> list[dict[str, Any]]:
        rows = self.repo.select(TABLE, where={"session_id": session_id})
        return sorted(rows, key=lambda r: (r["turn"], r["ordinal"]))
