"""T053 — reserve-then-reconcile, so a crash over-counts rather than under-counts.

**The direction is the whole requirement.** `BudgetJournal` accrues *after* the
model call, and U-30 is exactly what that loses: a `SIGKILL` during the call
leaves the spend unrecorded, so the total a resumed process reads is lower than
what was really spent and a ceiling that should have fired does not. Reserving
before the call inverts the error — the crash counts the reservation, which is
too much rather than too little.

**What this mechanism reduces and what it cannot remove.** The reservation is an
estimate, so a crash loses `actual − reserved` when the actual is the larger.
That residue is irreducible without knowing a call's cost before making it,
which is T062's cost table and does not exist yet. So the claim under test here
is the narrow one that is actually true:

- the total is never *lower* after a crash than it was before, because nothing
  is ever removed from the ledger and an unreconciled reservation keeps
  counting; and
- a turn that reached the provider is counted even if nothing came back.

Both are asserted below. The wider claim — that the recorded spend equals the
real spend across a crash — is **not** made, and `ReservationPolicy` says so in
its own docstring rather than leaving a reader to assume it.
"""

from __future__ import annotations

import pytest

from src.contracts.repository import Repository
from src.runtime.ledger import (
    BudgetLedger,
    LedgerError,
    ReservationPolicy,
)
from src.runtime.trace_budget import BudgetJournal, Consumption

TENANT, DEPLOYMENT, SESSION = "t-1", "d-1", "sess-1"
POLICY = ReservationPolicy(spend_usd=0.50, tokens=2_000)


def _ledger(tmp_path, *, policy: ReservationPolicy = POLICY) -> BudgetLedger:
    repo = Repository(tmp_path / "runtime.sqlite3", role="runtime",
                      tenant_id=TENANT, deployment_id=DEPLOYMENT)
    journal = BudgetJournal(repo, session_root=tmp_path / "root")
    return BudgetLedger(journal, policy=policy)


# ---------------------------------------------------------------------------
# The policy refuses what it cannot mean.


def test_the_policy_has_no_default(tmp_path) -> None:
    """A default reservation is a number nobody chose, standing in for one the
    ledger reports as accounting. `Ceilings` refuses an unset ceiling for the
    same reason."""
    with pytest.raises(TypeError):
        ReservationPolicy()  # type: ignore[call-arg]


def test_a_negative_reservation_is_refused() -> None:
    with pytest.raises(LedgerError, match="negative"):
        ReservationPolicy(spend_usd=-1.0, tokens=1)


def test_a_reservation_that_counts_no_turn_is_refused() -> None:
    """The one figure a reservation always knows is that a turn is happening.

    A policy with `turns=0` would leave the turn ceiling accruing only after
    the call returns, which is the under-count for the one dimension where an
    exact estimate is available.
    """
    with pytest.raises(LedgerError, match="turn"):
        ReservationPolicy(spend_usd=0.5, tokens=1, turns=0)


# ---------------------------------------------------------------------------
# Reserve counts immediately.


def test_a_reservation_counts_before_the_call_returns(tmp_path) -> None:
    ledger = _ledger(tmp_path)
    assert ledger.totals(SESSION).turns == 0

    ledger.reserve(SESSION, turn=0, at=1.0)

    totals = ledger.totals(SESSION)
    assert totals.turns == 1, "the turn in flight is not counted"
    assert totals.spend_usd == pytest.approx(0.50)
    assert totals.tokens == 2_000
    ledger.journal.repo.close()


def test_a_second_ledger_over_the_same_file_sees_the_reservation(tmp_path) -> None:
    """The property U-30 is about: the number survives the process.

    A reservation held in memory is exactly the counter finding 006 measured
    living on a context rebuilt per attempt.
    """
    ledger = _ledger(tmp_path)
    ledger.reserve(SESSION, turn=0, at=1.0)
    ledger.journal.repo.close()

    reopened = _ledger(tmp_path)
    assert reopened.totals(SESSION).turns == 1
    assert reopened.totals(SESSION).spend_usd == pytest.approx(0.50)
    assert [r.turn for r in reopened.outstanding(SESSION)] == [0]
    reopened.journal.repo.close()


def test_reserving_the_same_turn_twice_is_refused(tmp_path) -> None:
    """Two reservations for one position would double-count a turn that only
    happened once, and the refusal comes from the store so a resumed process
    cannot make the second one."""
    ledger = _ledger(tmp_path)
    ledger.reserve(SESSION, turn=0, at=1.0)
    with pytest.raises(LedgerError, match="already reserved"):
        ledger.reserve(SESSION, turn=0, at=2.0)
    ledger.journal.repo.close()


# ---------------------------------------------------------------------------
# Reconcile replaces the estimate with the measurement.


def test_reconciling_replaces_the_estimate_with_the_actual(tmp_path) -> None:
    ledger = _ledger(tmp_path)
    reservation = ledger.reserve(SESSION, turn=0, at=1.0)
    ledger.reconcile(reservation, spend_usd=0.10, tokens=42,
                     wall_clock_seconds=0.25, at=2.0)

    totals = ledger.totals(SESSION)
    assert totals.spend_usd == pytest.approx(0.10)
    assert totals.tokens == 42
    assert totals.wall_clock_seconds == pytest.approx(0.25)
    assert totals.turns == 1, "the turn is counted once, not twice"
    assert ledger.outstanding(SESSION) == ()
    ledger.journal.repo.close()


def test_reconciling_twice_is_refused(tmp_path) -> None:
    ledger = _ledger(tmp_path)
    reservation = ledger.reserve(SESSION, turn=0, at=1.0)
    ledger.reconcile(reservation, spend_usd=0.10, tokens=1,
                     wall_clock_seconds=0.0, at=2.0)
    with pytest.raises(LedgerError, match="already reconciled"):
        ledger.reconcile(reservation, spend_usd=0.10, tokens=1,
                         wall_clock_seconds=0.0, at=3.0)
    assert ledger.totals(SESSION).turns == 1
    ledger.journal.repo.close()


def test_an_actual_above_the_estimate_is_recorded_in_full(tmp_path) -> None:
    """The estimate bounds the crash window; it does not cap the charge."""
    ledger = _ledger(tmp_path)
    reservation = ledger.reserve(SESSION, turn=0, at=1.0)
    ledger.reconcile(reservation, spend_usd=9.99, tokens=100_000,
                     wall_clock_seconds=1.0, at=2.0)

    assert ledger.totals(SESSION).spend_usd == pytest.approx(9.99)
    assert ledger.totals(SESSION).tokens == 100_000
    ledger.journal.repo.close()


def test_a_reconcile_belonging_to_another_session_is_refused(tmp_path) -> None:
    ledger = _ledger(tmp_path)
    reservation = ledger.reserve(SESSION, turn=0, at=1.0)
    other = type(reservation)(**{**reservation.__dict__, "session_id": "other"})
    with pytest.raises(LedgerError, match="no outstanding reservation"):
        ledger.reconcile(other, spend_usd=0.1, tokens=1,
                         wall_clock_seconds=0.0, at=2.0)
    ledger.journal.repo.close()


# ---------------------------------------------------------------------------
# The crash direction, which is the requirement.


def test_an_unreconciled_reservation_keeps_counting(tmp_path) -> None:
    """The `SIGKILL`-during-the-call case, in one process.

    No `reconcile` is ever made, exactly as none is made when the process is
    killed. What a resumed reader sees is the reservation, still counted.
    """
    ledger = _ledger(tmp_path)
    ledger.reserve(SESSION, turn=0, at=1.0)
    ledger.journal.repo.close()

    resumed = _ledger(tmp_path)
    assert resumed.totals(SESSION).spend_usd == pytest.approx(0.50), (
        "the reservation for the call in flight was lost, so the resumed "
        "session under-counts what may already have been spent — U-30"
    )
    resumed.journal.repo.close()


def test_the_total_never_falls_across_a_crash_boundary(tmp_path) -> None:
    """SC-030's second clause, at the ledger.

    Three crash-shaped cycles: reserve, abandon, reopen. The sample after each
    reopen is compared against the sample before it, and the sequence has to be
    non-decreasing. Note that the comparison is across *crash* boundaries only —
    within a live attempt `reconcile` can lower the total, and legitimately
    does when the actual comes in under the estimate.
    """
    samples: list[float] = []
    for turn in range(3):
        ledger = _ledger(tmp_path)
        samples.append(ledger.totals(SESSION).spend_usd)
        ledger.reserve(SESSION, turn=turn, at=float(turn))
        samples.append(ledger.totals(SESSION).spend_usd)
        ledger.journal.repo.close()  # the crash

    assert samples == sorted(samples), (
        f"the running total fell across a crash boundary: {samples}"
    )
    assert samples[-1] == pytest.approx(1.50)


def test_a_reconciled_total_is_not_lower_than_before_the_crash(tmp_path) -> None:
    """The mixed case: one turn reconciled, the next abandoned.

    The abandoned turn's estimate stands beside the reconciled turn's
    measurement, so the total after the crash covers both.
    """
    ledger = _ledger(tmp_path)
    first = ledger.reserve(SESSION, turn=0, at=1.0)
    ledger.reconcile(first, spend_usd=0.10, tokens=5,
                     wall_clock_seconds=0.0, at=2.0)
    ledger.reserve(SESSION, turn=1, at=3.0)
    before = ledger.totals(SESSION)
    ledger.journal.repo.close()

    resumed = _ledger(tmp_path)
    after = resumed.totals(SESSION)
    assert after.spend_usd >= before.spend_usd
    assert after.turns >= before.turns
    assert after.spend_usd == pytest.approx(0.60)
    assert after.turns == 2
    resumed.journal.repo.close()


# ---------------------------------------------------------------------------
# It is still the journal underneath.


def test_consumption_that_is_not_a_model_call_still_accrues(tmp_path) -> None:
    """Not everything is reserved. A figure already measured — wall clock at the
    end of a turn — is accrued directly, because there is nothing to estimate."""
    ledger = _ledger(tmp_path)
    ledger.accrue(Consumption(
        session_id=SESSION, turn=0, ordinal=9, spend_usd=0.0, tokens=0,
        wall_clock_seconds=1.5, turns=0, at=1.0))
    assert ledger.totals(SESSION).wall_clock_seconds == pytest.approx(1.5)
    assert ledger.totals(SESSION).turns == 0
    ledger.journal.repo.close()


def test_the_ledger_refuses_a_journal_inside_the_session_root(tmp_path) -> None:
    """Inherited from `BudgetJournal` rather than re-implemented, and asserted
    here so that the inheritance is not something a reader has to check."""
    from src.runtime.trace_budget import JournalLocationError

    repo = Repository(tmp_path / "runtime.sqlite3", role="runtime",
                      tenant_id=TENANT, deployment_id=DEPLOYMENT)
    with pytest.raises(JournalLocationError):
        BudgetJournal(repo, session_root=tmp_path)
    repo.close()


def test_totals_are_per_session(tmp_path) -> None:
    ledger = _ledger(tmp_path)
    ledger.reserve(SESSION, turn=0, at=1.0)
    assert ledger.totals("another").turns == 0
    ledger.journal.repo.close()
