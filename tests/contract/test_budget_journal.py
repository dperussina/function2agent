"""T038 — the budget ledger survives what FR-049's memory bound does to a session.

`memory.oom.group` kills every process in the cgroup with no unwind and no
final flush. This asserts the two properties that make the accounting survive
that: it is written as consumption accrues, and it lives outside the container.

The kill is simulated by discarding the writer without any flush, which is
what the workload's in-memory state amounts to after an OOM kill. A test that
called a `close()` would be testing the graceful path, which is not the one
that loses data.
"""

from __future__ import annotations

import pytest

from src.contracts.repository import Repository
from src.runtime.trace_budget import (
    BudgetError,
    BudgetJournal,
    Consumption,
    JournalLocationError,
    assert_outside_session_root,
)


@pytest.fixture()
def journal(tmp_path):
    repo = Repository(tmp_path / "budget.sqlite3", role="runtime",
                      tenant_id="t-1", deployment_id="d-1")
    yield BudgetJournal(repo)
    repo.close()


def _c(ordinal: int, spend: float = 0.25, turn: int = 0) -> Consumption:
    return Consumption(session_id="sess-1", turn=turn, ordinal=ordinal,
                       spend_usd=spend, tokens=100,
                       wall_clock_seconds=1.0, turns=0, at=float(ordinal))


def test_consumption_is_journalled_as_it_accrues_not_at_turn_end(journal) -> None:
    for i in range(5):
        journal.accrue(_c(i))
    assert len(journal.entries("sess-1")) == 5, (
        "a turn's spend arrived as one entry. A ledger appended once per turn "
        "loses the whole turn to a cgroup kill, and a turn is where the spend is."
    )


def test_the_ledger_survives_a_kill_with_no_flush(tmp_path) -> None:
    """The property U-30 and finding 006 are about."""
    db = tmp_path / "budget.sqlite3"
    repo = Repository(db, role="runtime", tenant_id="t-1", deployment_id="d-1")
    journal = BudgetJournal(repo)
    for i in range(3):
        journal.accrue(_c(i, spend=0.25))

    # The kill: no close, no flush, no unwind. Drop the references.
    del journal
    repo.close()

    reader = Repository(db, role="runtime", tenant_id="t-1", deployment_id="d-1")
    try:
        recovered = BudgetJournal(reader).totals("sess-1")
        assert recovered.spend_usd == pytest.approx(0.75), (
            f"the ledger lost spend across the kill: {recovered.spend_usd} of 0.75"
        )
        assert recovered.tokens == 300
    finally:
        reader.close()


def test_a_journal_inside_the_session_root_is_refused(tmp_path) -> None:
    root = tmp_path / "session-root"
    (root / "var").mkdir(parents=True)
    with pytest.raises(JournalLocationError, match="inside the session root"):
        assert_outside_session_root(root / "var" / "budget.sqlite3", root)
    with pytest.raises(JournalLocationError):
        assert_outside_session_root(root, root)


def test_a_journal_outside_the_session_root_is_permitted(tmp_path) -> None:
    root = tmp_path / "session-root"
    root.mkdir()
    supervisor = tmp_path / "supervisor-state"
    supervisor.mkdir()
    assert_outside_session_root(supervisor / "budget.sqlite3", root)


def test_the_location_check_is_not_fooled_by_a_relative_path(tmp_path) -> None:
    """`<supervisor>/../session-root/x` is inside, whatever it looks like."""
    root = tmp_path / "session-root"
    root.mkdir()
    supervisor = tmp_path / "supervisor-state"
    supervisor.mkdir()
    with pytest.raises(JournalLocationError):
        assert_outside_session_root(
            supervisor / ".." / "session-root" / "budget.sqlite3", root)


def test_the_journal_constructor_enforces_the_location(tmp_path) -> None:
    root = tmp_path / "session-root"
    root.mkdir()
    inside = root / "budget.sqlite3"
    repo = Repository(tmp_path / "elsewhere.sqlite3", role="runtime",
                      tenant_id="t-1", deployment_id="d-1")
    try:
        with pytest.raises(JournalLocationError):
            BudgetJournal(repo, session_root=root, journal_path=inside)
    finally:
        repo.close()


def test_totals_are_recomputed_and_not_cached(journal) -> None:
    journal.accrue(_c(0, spend=1.0))
    assert journal.totals("sess-1").spend_usd == pytest.approx(1.0)
    journal.accrue(_c(1, spend=2.0))
    assert journal.totals("sess-1").spend_usd == pytest.approx(3.0)


def test_accrue_returns_the_totals_as_at_that_increment(journal) -> None:
    """The caller checks a ceiling against this, so it has to include the
    increment that just landed."""
    assert journal.accrue(_c(0, spend=1.0)).spend_usd == pytest.approx(1.0)
    assert journal.accrue(_c(1, spend=1.5)).spend_usd == pytest.approx(2.5)


def test_the_ledger_cannot_be_decremented(journal) -> None:
    """A ledger that can go down is a ceiling that can be walked back under."""
    with pytest.raises(BudgetError, match="negative"):
        journal.accrue(_c(0, spend=-5.0))
    for name in ("tokens", "wall_clock_seconds", "turns"):
        kwargs = {"session_id": "s", "turn": 0, "ordinal": 0, "spend_usd": 0.0,
                  "tokens": 0, "wall_clock_seconds": 0.0, "turns": 0, "at": 0.0}
        kwargs[name] = -1
        with pytest.raises(BudgetError, match="negative"):
            Consumption(**kwargs)


def test_sessions_do_not_share_a_ledger(journal) -> None:
    journal.accrue(_c(0, spend=1.0))
    journal.accrue(Consumption(session_id="sess-2", turn=0, ordinal=0,
                               spend_usd=99.0, tokens=1, wall_clock_seconds=0.0,
                               turns=0, at=0.0))
    assert journal.totals("sess-1").spend_usd == pytest.approx(1.0)
    assert journal.totals("sess-2").spend_usd == pytest.approx(99.0)


def test_entries_order_without_a_clock(journal) -> None:
    journal.accrue(_c(1, turn=0))
    journal.accrue(_c(0, turn=1))
    journal.accrue(_c(0, turn=0))
    positions = [(e["turn"], e["ordinal"]) for e in journal.entries("sess-1")]
    assert positions == [(0, 0), (0, 1), (1, 0)]


def test_the_ledger_is_the_runtimes_to_write(tmp_path) -> None:
    from src.contracts.ownership import OwnershipError

    repo = Repository(tmp_path / "b.sqlite3", role="runtime",
                      tenant_id="t-1", deployment_id="d-1")
    BudgetJournal(repo)
    repo.close()

    analysis = Repository(tmp_path / "b.sqlite3", role="analysis",
                          tenant_id="t-1", deployment_id="d-1")
    try:
        with pytest.raises(OwnershipError):
            BudgetJournal(analysis)
    finally:
        analysis.close()
