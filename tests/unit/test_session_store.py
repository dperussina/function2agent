"""T048, T049 — the session store and the session state machine.

**The load-bearing test in this file is the resume one**, and it is written
against a measured failure rather than against the interface. Finding 006
measured a ceiling of 3 that permitted **6** cycles, because the counter lived
on a context rebuilt per attempt — and the failure is invisible in review
because every individual attempt is compliant. FR-005 states the property
directly: a crash MUST NOT reduce the total counted against any of the four
ceilings.

So `test_a_ceiling_survives_a_rebuilt_process` drops every in-process object and
rebuilds from the file, which is the only arm that can tell durable accounting
from a counter that resets. The rest of the file is ordinary lifecycle coverage.

**The ownership arm is here too**, because the design decision it checks is easy
to undo. `session` is the supervisor's table in `data-model.md`'s single-writer
map; the runtime reads it and writes its own. A store that opened `session` for
write from the runtime role would work in every test in this file except that
one.
"""

from __future__ import annotations

import pytest

from src.contracts.ownership import OwnershipError, ROLE_RUNTIME
from src.contracts.repository import Repository
from src.contracts import terminal
from src.contracts.transition import STATE_RUNNING, STATE_TERMINATED
from src.runtime.session_store import (
    CEILING_ORDER,
    Ceilings,
    CeilingsError,
    SessionStore,
    evaluate_ceilings,
)
from src.runtime.session_state import (
    STATE_INTERRUPTED,
    SessionStateError,
    SessionStateMachine,
)
from src.runtime.trace_budget import BudgetJournal, Consumption, Totals
from src.supervisor.session_table import SessionTable, capability_digest

TENANT = "tenant-test"
DEPLOYMENT = "deploy-test"
SESSION = "sess-1"


def _ceilings(**overrides: float) -> Ceilings:
    values: dict[str, float] = {
        "spend_usd": 10.0,
        "tokens": 1_000,
        "wall_clock_seconds": 60.0,
        "turns": 5,
    }
    values.update(overrides)
    return Ceilings(
        spend_usd=values["spend_usd"],
        tokens=int(values["tokens"]),
        wall_clock_seconds=values["wall_clock_seconds"],
        turns=int(values["turns"]),
    )


def _repo(tmp_path, role: str = ROLE_RUNTIME) -> Repository:
    return Repository(
        tmp_path / "state.sqlite3",
        role=role,
        tenant_id=TENANT,
        deployment_id=DEPLOYMENT,
    )


LEASE = 2_000_000_000.0
NOW = 1_000_000_001.0


def _open_lifecycle(tmp_path) -> SessionTable:
    """Reopen the owner's store without seeding it — the post-crash handle."""
    return SessionTable(tmp_path / "session.sqlite3")


def _lifecycle(tmp_path) -> SessionTable:
    table = _open_lifecycle(tmp_path)
    table.create(
        session_id=SESSION,
        tenant_id=TENANT,
        deployment_id=DEPLOYMENT,
        capability_sha256=capability_digest("handle-1"),
        lease_expires_at=LEASE,
        now=1_000_000_000.0,
    )
    return table


# ---------------------------------------------------------------------------
# Ceilings — required, durable, and named when they fire.


def test_a_ceiling_set_to_none_cannot_be_constructed() -> None:
    """FR-005 and Q-10: no default, and an unset ceiling is not unbounded."""
    with pytest.raises(CeilingsError) as raised:
        Ceilings(spend_usd=None, tokens=1, wall_clock_seconds=1.0, turns=1)
    assert "spend_usd" in str(raised.value)
    assert "unbounded" in str(raised.value)


def test_a_negative_ceiling_is_refused() -> None:
    with pytest.raises(CeilingsError):
        Ceilings(spend_usd=-1.0, tokens=1, wall_clock_seconds=1.0, turns=1)


def test_every_ceiling_has_a_named_terminal_state() -> None:
    """The four ceilings and the taxonomy agree, checked rather than assumed."""
    for name in CEILING_ORDER:
        verdict = evaluate_ceilings(
            _ceilings(**{name: 0 if name in ("tokens", "turns") else 0.0}),
            Totals(spend_usd=1.0, tokens=1, wall_clock_seconds=1.0, turns=1),
        )
        assert verdict.exceeded
        assert terminal.is_terminal(verdict.terminal_state)


def test_the_verdict_names_which_ceiling_fired_and_what_the_others_read() -> None:
    """Principle VI: every consulted input, not only the matching one."""
    verdict = evaluate_ceilings(
        _ceilings(tokens=100),
        Totals(spend_usd=0.5, tokens=250, wall_clock_seconds=1.0, turns=1),
    )
    assert verdict.exceeded
    assert verdict.terminal_state == terminal.TOKEN_CEILING.name
    assert [r.name for r in verdict.readings] == list(CEILING_ORDER)
    matched = [r.name for r in verdict.readings if r.matched]
    assert matched == ["tokens"]


def test_the_declared_order_decides_which_of_two_breached_ceilings_wins() -> None:
    """The order is part of the decision, as it is in bounds.check."""
    verdict = evaluate_ceilings(
        _ceilings(spend_usd=1.0, tokens=100),
        Totals(spend_usd=5.0, tokens=250, wall_clock_seconds=1.0, turns=1),
    )
    assert verdict.terminal_state == terminal.SPEND_CEILING.name
    breached = [r.name for r in verdict.readings if r.matched]
    assert breached == ["spend_usd"], (
        "both spend and tokens are over; exactly one may be marked as the one "
        "that matched, and it must be the first in CEILING_ORDER"
    )


def test_a_session_under_every_ceiling_is_not_exceeded() -> None:
    verdict = evaluate_ceilings(
        _ceilings(),
        Totals(spend_usd=1.0, tokens=10, wall_clock_seconds=1.0, turns=1),
    )
    assert not verdict.exceeded
    assert verdict.terminal_state is None
    # The readings are still recorded. A verdict that carried them only when a
    # ceiling fired could not distinguish "not exceeded" from "not checked".
    assert [r.name for r in verdict.readings] == list(CEILING_ORDER)


def test_a_ceiling_reached_exactly_is_reached() -> None:
    """`>=`, not `>`. A ceiling of 5 turns permits 5 turns, not 6."""
    verdict = evaluate_ceilings(
        _ceilings(turns=5),
        Totals(spend_usd=0.0, tokens=0, wall_clock_seconds=0.0, turns=5),
    )
    assert verdict.exceeded
    assert verdict.terminal_state == terminal.TURN_CEILING.name


# ---------------------------------------------------------------------------
# The store.


def test_the_store_persists_and_reloads_the_four_ceilings(tmp_path) -> None:
    with _lifecycle(tmp_path) as lifecycle:
        repo = _repo(tmp_path)
        store = SessionStore(repo, lifecycle=lifecycle)
        store.create(session_id=SESSION, ceilings=_ceilings(tokens=1234))

        session = store.load(SESSION)
        assert session.ceilings.tokens == 1234
        assert session.state == "STARTING"
        assert session.terminal_state is None
        assert session.lease_expires_at == 2_000_000_000.0
        repo.close()


def test_creating_the_same_session_twice_is_refused(tmp_path) -> None:
    with _lifecycle(tmp_path) as lifecycle:
        repo = _repo(tmp_path)
        store = SessionStore(repo, lifecycle=lifecycle)
        store.create(session_id=SESSION, ceilings=_ceilings())
        with pytest.raises(CeilingsError, match="already"):
            store.create(session_id=SESSION, ceilings=_ceilings(tokens=1))
        repo.close()


def test_loading_an_unknown_session_returns_none(tmp_path) -> None:
    with _lifecycle(tmp_path) as lifecycle:
        repo = _repo(tmp_path)
        store = SessionStore(repo, lifecycle=lifecycle)
        assert store.load("sess-nobody") is None
        repo.close()


def test_a_ceiling_survives_a_rebuilt_process(tmp_path) -> None:
    """Finding 006's measured failure, as an assertion.

    Everything in process is dropped between the two halves: the store, the
    ledger, the repository and the lifecycle handle. A counter living on any of
    them resets here, the session comes back under its ceiling, and the run
    that already spent the budget is permitted to spend it again.
    """
    ceilings = _ceilings(tokens=100)

    with _lifecycle(tmp_path) as lifecycle:
        repo = _repo(tmp_path)
        store = SessionStore(repo, lifecycle=lifecycle)
        store.create(session_id=SESSION, ceilings=ceilings)
        journal = BudgetJournal(repo, session_root=tmp_path / "session-root")
        journal.accrue(Consumption(
            session_id=SESSION, turn=0, ordinal=0,
            spend_usd=0.0, tokens=60, wall_clock_seconds=0.0, turns=1,
            at=1.0,
        ))
        before = store.ceiling_verdict(SESSION, journal)
        assert not before.exceeded, (
            "the pre-crash half is already over the ceiling, so the arm cannot "
            "distinguish a surviving total from a reset one"
        )
        repo.close()

    # The crash. Nothing above is reachable from here.
    with _open_lifecycle(tmp_path) as lifecycle:
        repo = _repo(tmp_path)
        store = SessionStore(repo, lifecycle=lifecycle)
        journal = BudgetJournal(repo, session_root=tmp_path / "session-root")

        resumed = store.load(SESSION)
        assert resumed is not None
        assert resumed.ceilings.tokens == 100, (
            "the ceiling itself did not survive the rebuild"
        )
        assert journal.totals(SESSION).tokens == 60, (
            "consumption incurred before the crash is not counted after it, "
            "which is finding 006's ceiling of 3 permitting 6 cycles"
        )

        journal.accrue(Consumption(
            session_id=SESSION, turn=1, ordinal=0,
            spend_usd=0.0, tokens=60, wall_clock_seconds=0.0, turns=1,
            at=2.0,
        ))
        after = store.ceiling_verdict(SESSION, journal)
        assert after.exceeded, (
            "120 tokens against a ceiling of 100 is under the ceiling only if "
            "the pre-crash 60 was forgotten"
        )
        assert after.terminal_state == terminal.TOKEN_CEILING.name
        repo.close()


def test_the_runtime_role_cannot_write_the_supervisors_session_table(tmp_path) -> None:
    """The ownership map, asserted against the role the store actually opens.

    This is the arm that fails if the store is ever changed to write `session`
    itself. Every other test in this file would still pass.
    """
    repo = _repo(tmp_path)
    with pytest.raises(OwnershipError) as raised:
        repo.insert("session", {"session_id": SESSION})
    assert "supervisor" in str(raised.value)
    repo.close()


# ---------------------------------------------------------------------------
# The state machine.


def test_the_lifecycle_walks_starting_running_terminated(tmp_path) -> None:
    with _lifecycle(tmp_path) as lifecycle:
        machine = SessionStateMachine(lifecycle)
        started = machine.start(SESSION, at=1.0)
        assert started.to_state == STATE_RUNNING
        assert lifecycle.get(SESSION).state == STATE_RUNNING

        ended = machine.complete(SESSION, at=2.0)
        assert ended.to_state == STATE_TERMINATED
        assert ended.terminal_state == terminal.COMPLETED.name
        assert lifecycle.get(SESSION).terminal_state == terminal.COMPLETED.name


def test_a_session_cannot_be_started_twice(tmp_path) -> None:
    with _lifecycle(tmp_path) as lifecycle:
        machine = SessionStateMachine(lifecycle)
        machine.start(SESSION, at=1.0)
        with pytest.raises(SessionStateError, match="STARTING"):
            machine.start(SESSION, at=2.0)


def test_a_terminated_session_cannot_be_terminated_again(tmp_path) -> None:
    """The second terminal state would overwrite the first, and FR-006's whole
    subject is that the recorded outcome is the one that happened."""
    with _lifecycle(tmp_path) as lifecycle:
        machine = SessionStateMachine(lifecycle)
        machine.start(SESSION, at=1.0)
        machine.complete(SESSION, at=2.0)
        with pytest.raises(SessionStateError, match="already terminated"):
            machine.terminate(
                SESSION,
                terminal_state=terminal.OPERATOR_TERMINATED.name,
                at=3.0,
            )
        assert lifecycle.get(SESSION).terminal_state == terminal.COMPLETED.name


def test_a_terminated_session_cannot_be_restarted(tmp_path) -> None:
    with _lifecycle(tmp_path) as lifecycle:
        machine = SessionStateMachine(lifecycle)
        machine.start(SESSION, at=1.0)
        machine.complete(SESSION, at=2.0)
        with pytest.raises(SessionStateError):
            machine.resume(SESSION, at=3.0, lease_expires_at=LEASE)


def test_terminating_with_an_undeclared_state_is_refused(tmp_path) -> None:
    with _lifecycle(tmp_path) as lifecycle:
        machine = SessionStateMachine(lifecycle)
        machine.start(SESSION, at=1.0)
        with pytest.raises(Exception) as raised:
            machine.terminate(
                SESSION, terminal_state="terminated.something_invented", at=2.0)
        assert "taxonomy" in str(raised.value)
        assert lifecycle.get(SESSION).state == STATE_RUNNING, (
            "the refusal has to happen before the row moves, or the session is "
            "terminated with a state FR-006 forbids"
        )


def test_an_interrupted_session_is_not_honoured_and_can_resume(tmp_path) -> None:
    """`data-model.md` §2.1's `interrupted ─▶ RUNNING` edge.

    The honouring assertion matters more than the transition: FR-050 layer 1
    honours a capability only while the session is `RUNNING`, and an
    interrupted session that kept being honoured would leave the enforcement
    point answering for a runtime that is not there.
    """
    with _lifecycle(tmp_path) as lifecycle:
        machine = SessionStateMachine(lifecycle)
        machine.start(SESSION, at=1.0)

        interrupted = machine.interrupt(SESSION, at=2.0)
        assert interrupted.to_state == STATE_INTERRUPTED
        assert interrupted.terminal_state is None, (
            "interrupted is not a terminal state; a session that resumes has "
            "not ended"
        )
        row = lifecycle.get(SESSION)
        assert row.state == STATE_INTERRUPTED
        assert not row.honoured_at(NOW), (
            "an interrupted session was still honoured. Its lease is "
            "deliberately untouched, so the state is the only thing refusing."
        )

        resumed = machine.resume(SESSION, at=3.0, lease_expires_at=LEASE)
        assert resumed.from_state == STATE_INTERRUPTED
        assert resumed.to_state == STATE_RUNNING
        assert lifecycle.get(SESSION).honoured_at(NOW)


def test_a_ceiling_termination_records_every_reading_it_consulted(tmp_path) -> None:
    with _lifecycle(tmp_path) as lifecycle:
        machine = SessionStateMachine(lifecycle)
        machine.start(SESSION, at=1.0)
        verdict = evaluate_ceilings(
            _ceilings(turns=2),
            Totals(spend_usd=0.1, tokens=5, wall_clock_seconds=1.0, turns=2),
        )
        transition = machine.terminate_on_ceiling(SESSION, verdict, at=2.0)
        assert transition.terminal_state == terminal.TURN_CEILING.name
        assert [r.name for r in transition.predicate_inputs] == list(CEILING_ORDER)
        assert sum(1 for r in transition.predicate_inputs if r.matched) == 1


def test_terminating_on_a_verdict_that_did_not_fire_is_refused(tmp_path) -> None:
    """A verdict is evidence, and a termination with no breach has none."""
    with _lifecycle(tmp_path) as lifecycle:
        machine = SessionStateMachine(lifecycle)
        machine.start(SESSION, at=1.0)
        verdict = evaluate_ceilings(
            _ceilings(),
            Totals(spend_usd=0.0, tokens=0, wall_clock_seconds=0.0, turns=0),
        )
        with pytest.raises(SessionStateError, match="no ceiling"):
            machine.terminate_on_ceiling(SESSION, verdict, at=2.0)
        assert lifecycle.get(SESSION).state == STATE_RUNNING
