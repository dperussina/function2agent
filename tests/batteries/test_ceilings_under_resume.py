"""T055 — SC-030's second clause: a ceiling that survives repeated crashes.

**The failure this battery exists to catch is invisible in review, and that is
why it is a measurement.** Finding 006 measured a ceiling of 3 permitting **6**
cycles, because the counter lived on a context the framework rebuilt per attempt.
Every individual attempt was compliant. Nothing in any single attempt's trace was
wrong. The defect existed only in the relationship between attempts, which is the
one thing no per-attempt assertion can see.

So each arm here crashes the session **three times** and reads the cumulative
total from disk at every boundary. Three rather than one is SC-030's own wording
and its own reason: *"a single resume cannot distinguish a ceiling that resets
from one that holds if the run happens not to reach the ceiling twice."*

## What each arm asserts, and in what order

For the dimension under test, with the other three left loose:

1. **Monotonicity at every boundary.** The total read after resume *n* is never
   lower than the total read immediately before crash *n*. This is the clause
   that matters.
2. **The session ends in the named member of FR-006's taxonomy** for that
   dimension — not merely "some terminal state".
3. **The ceiling bound what actually ran.** The count of turn positions the
   journal ever issued is at most what the ceiling permits. This is finding
   006's 3-permitting-6 stated as an assertion: it is the only one of the three
   that a ceiling resetting on resume would fail while the other two passed.

The three kill points are **not** the same on every arm. `model:N` is used at
least once in each, because it is the only one that leaves a reservation
outstanding, and an arm that crashed only at turn boundaries would never exercise
the half of the ledger T053 exists for.

## The wall-clock arm is partial, and says so

`src/runtime/loop.py`'s docstring records that wall-clock consumption is **not
accrued**: `reconcile` passes `wall_clock_seconds=0.0` and nothing else writes
that dimension. So the only wall-clock figure that reaches the ledger is the
reservation, which is released on every successful reconcile — the committed
wall-clock total is permanently zero and **the wall-clock ceiling cannot fire.**

That arm therefore asserts clause 1 over the reservation channel and reports the
gap through `note_vacuous_invariant`, rather than being written to pass. Two
other shapes were available and both were rejected: skipping the dimension, which
would leave a green run reading as coverage of all four; and having the fixture
call `accrue()` with an elapsed figure, which would be the test supplying the
mechanism it claims to measure. **How wall clock should be measured — session
elapsed time including idle, or the sum of the model calls — is an owner's
decision and not this battery's**, and picking one here would settle it silently.
"""

from __future__ import annotations

import json
import signal
import subprocess
import sys
from pathlib import Path

import pytest

import tests.conftest as conftest
from src.contracts import terminal
from src.contracts.repository import Repository
from src.runtime.journal import TurnJournal
from src.runtime.ledger import BudgetLedger, ReservationPolicy
from src.runtime.session_store import CEILING_ORDER, TERMINAL_BY_CEILING
from src.runtime.trace_budget import BudgetJournal

REPO = Path(__file__).resolve().parents[2]
FIXTURE = REPO / "tests" / "fixtures" / "resume_session.py"
SESSION = "s-resume"
TIMEOUT = 60

# The three kills every arm makes, in order. One of each kind, so that a single
# arm covers a turn boundary, a call in flight and a half-finished turn — and so
# that no arm can pass by only ever crashing at the cheapest point.
KILLS = ("model:0", "turn:2", "step:3:0")

# Per-turn consumption, imported rather than restated so an arm cannot drift out
# of step with the fixture that produces the figures.
from tests.fixtures.resume_session import (  # noqa: E402
    RESERVE_SPEND,
    RESERVE_TOKENS,
    SPEND_PER_TURN,
    TOKENS_PER_TURN,
)

# Reserved wall clock for the partial arm. Non-zero so the reservation channel
# has something in it; the figure itself carries no meaning, which is exactly
# what makes the arm partial.
RESERVE_WALL_CLOCK = 0.5


def _permitted(ceiling: float, per_turn: float, reserved: float) -> int:
    """How many turn positions this ceiling may issue over the three crashes.

    **Derived, not observed.** An expectation copied off a run that happened is a
    change detector; this one is arithmetic, so a run that takes more positions
    than the ceiling can pay for fails rather than teaching the test a new
    number.

    Two terms. The `model:0` crash abandons one position whose reservation is
    never released, and that reservation is the *estimate* rather than a turn's
    real charge — so it contributes `reserved`, not `per_turn`. Everything after
    it is a completed turn at `per_turn`. The ceiling is `>=`
    (`evaluate_ceilings`) and is checked *before* each turn, so the last turn
    that runs is the one that takes the total to or past the ceiling.

    The other two crashes contribute no position of their own: `turn:2` leaves
    nothing journalled for its turn, and `step:3:0` leaves a turn whose model
    call is already accounted for and which the resume finishes in place.
    """
    import math
    completed = math.ceil((ceiling - reserved) / per_turn)
    return 1 + max(0, completed)


class Dimension:
    """One of FR-005's four, with what it takes to drive a session past it."""

    def __init__(self, name: str, ceiling: float, *, per_turn: float,
                 reserved: float, enforceable: bool = True):
        self.name = name
        self.ceiling = ceiling
        self.permitted = _permitted(ceiling, per_turn, reserved)
        self.enforceable = enforceable

    @property
    def terminal_state(self) -> str:
        return TERMINAL_BY_CEILING[self.name]

    def flags(self) -> list[str]:
        loose = {
            "spend_usd": ["--ceiling-spend", "1000.0"],
            "tokens": ["--ceiling-tokens", "10000000"],
            "wall_clock_seconds": ["--ceiling-seconds", "1e12"],
            "turns": ["--ceiling-turns", "500"],
        }
        tight = {
            "spend_usd": ["--ceiling-spend", repr(self.ceiling)],
            "tokens": ["--ceiling-tokens", str(int(self.ceiling))],
            "wall_clock_seconds": ["--ceiling-seconds", repr(self.ceiling)],
            "turns": ["--ceiling-turns", str(int(self.ceiling))],
        }
        out: list[str] = []
        for name in CEILING_ORDER:
            out += tight[name] if name == self.name else loose[name]
        return out


# Ceilings chosen so that more than four turn positions are available: the three
# crashes need somewhere to happen, and the ceiling has to be reached by
# consumption afterwards rather than by the crashes themselves.
DIMENSIONS = {
    "spend_usd": Dimension("spend_usd", 0.30, per_turn=SPEND_PER_TURN,
                           reserved=RESERVE_SPEND),
    "tokens": Dimension("tokens", 70, per_turn=TOKENS_PER_TURN,
                        reserved=RESERVE_TOKENS),
    # A ceiling this arm can never reach; see the module docstring.
    "wall_clock_seconds": Dimension(
        "wall_clock_seconds", 2.0, per_turn=RESERVE_WALL_CLOCK,
        reserved=RESERVE_WALL_CLOCK, enforceable=False),
    # The exact one: a turn costs one turn and reserves one turn, so no rounding
    # sits between the ceiling and the count. It is the arm the tightness control
    # below asserts equality on.
    "turns": Dimension("turns", 9, per_turn=1, reserved=1),
}


def _reader(root: Path):
    """A ledger and a journal over the child's files, opened by the parent.

    The parent reads the store rather than parsing what the child said about
    itself. A total the child reported would be a total living in the child, and
    a count that lives where an attempt can rebuild it is the defect.
    """
    repo = Repository(root / "runtime.sqlite3", role="runtime",
                      tenant_id="t-1", deployment_id="d-1")
    ledger = BudgetLedger(
        BudgetJournal(repo, session_root=root / "session-root"),
        policy=ReservationPolicy(
            spend_usd=RESERVE_SPEND, tokens=RESERVE_TOKENS,
            wall_clock_seconds=RESERVE_WALL_CLOCK))
    return repo, ledger, TurnJournal(repo)


def _read(root: Path, dimension: str) -> tuple[float, int]:
    """The cumulative total on the dimension, and how many positions were issued."""
    repo, ledger, journal = _reader(root)
    try:
        return (
            getattr(ledger.totals(SESSION), dimension),
            len(journal.turn_indexes(SESSION)),
        )
    finally:
        repo.close()


def _argv(root: Path, dim: Dimension, pause: str) -> list[str]:
    return [
        sys.executable, str(FIXTURE),
        "--root", str(root), "--pause", pause,
        # Far more turns than any ceiling here permits, so a session that ended
        # did so because a ceiling fired and not because the script ran out.
        "--turns", "400", "--tools", "1",
        "--reserve-wall-clock", repr(RESERVE_WALL_CLOCK),
    ] + dim.flags()


@pytest.fixture()
def killer():
    def kill(pid: int) -> None:
        subprocess.run(["kill", "-KILL", str(pid)], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return kill


def _crash_at(root: Path, dim: Dimension, pause: str, killer) -> None:
    child = subprocess.Popen(_argv(root, dim, pause),
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             text=True)
    try:
        assert child.stdout is not None
        line = child.stdout.readline().strip()
        if line != f"READY {pause}":
            _, err = child.communicate(timeout=TIMEOUT)
            raise AssertionError(
                f"the {dim.name} arm never reached {pause}; the child said "
                f"{line!r} and then:\n{err}"
            )
        killer(child.pid)
        assert child.wait(timeout=TIMEOUT) == -signal.SIGKILL, (
            "the child did not die of SIGKILL, so this is not a crash")
    finally:
        if child.poll() is None:  # pragma: no cover
            child.kill()


def _run_to_end(root: Path, dim: Dimension) -> dict:
    done = subprocess.run(_argv(root, dim, "none"), capture_output=True,
                          text=True, timeout=TIMEOUT)
    assert done.returncode == 0, (
        f"the {dim.name} arm's final attempt failed:\n{done.stdout}\n{done.stderr}")
    reported = [line for line in done.stdout.splitlines()
                if line.startswith("DONE ")]
    assert len(reported) == 1
    return json.loads(reported[0][len("DONE "):])


def _drive(root: Path, dim: Dimension, killer) -> tuple[list[tuple], dict]:
    """Three crashes, then a run to the end. Returns the boundary readings.

    Each entry is `(pause, before, after)`: the total on the dimension read
    immediately before the kill, and again immediately after the process that
    resumed from it had itself stopped. Read from the store by the parent, twice,
    around each of the three boundaries.
    """
    boundaries: list[tuple] = []
    for pause in KILLS:
        before = _read(root, dim.name)
        _crash_at(root, dim, pause, killer)
        after = _read(root, dim.name)
        boundaries.append((pause, before, after))
    report = _run_to_end(root, dim)
    boundaries.append(("final", boundaries[-1][2], _read(root, dim.name)))
    return boundaries, report


def _assert_monotonic(dim: Dimension, boundaries: list[tuple]) -> None:
    for pause, before, after in boundaries:
        assert after[0] >= before[0], (
            f"{dim.name}: the total read {after[0]} after the {pause} crash "
            f"and {before[0]} before it. SC-030's last clause: the cumulative "
            "total counted after every resume is never lower than the total "
            "recorded before the crash that preceded it. Finding 006's ceiling "
            "of 3 permitted 6 cycles for exactly this reason, and every "
            "individual attempt was compliant."
        )
        assert after[1] >= before[1], (
            f"{dim.name}: {after[1]} turn positions after the {pause} crash "
            f"and {before[1]} before it. A journal that lost positions would "
            "let the numbering restart, which is the same reset wearing a "
            "different name."
        )


# ---------------------------------------------------------------------------
# The three enforceable dimensions.


@pytest.mark.parametrize("name", ["spend_usd", "tokens", "turns"])
def test_a_ceiling_holds_across_three_crashes_and_resumes(name, tmp_path, killer):
    """SC-030's second clause, on the three dimensions the runtime accrues.

    Parametrised rather than written out three times, because the three differ
    only in which ceiling is tight — and a copy per dimension is how one of them
    quietly stops asserting clause 3 while the other two still do.
    """
    dim = DIMENSIONS[name]
    root = tmp_path / name
    root.mkdir()

    boundaries, report = _drive(root, dim, killer)

    _assert_monotonic(dim, boundaries)

    assert report["terminal_state"] == dim.terminal_state, (
        f"{name}: the session ended as {report['terminal_state']!r} rather "
        f"than {dim.terminal_state!r}. SC-030 requires the named member of "
        "FR-006's taxonomy, and a session that ended for some other reason has "
        "not been driven past this ceiling at all."
    )
    assert terminal.is_terminal(report["terminal_state"])

    _, issued = _read(root, name)
    assert issued <= dim.permitted, (
        f"{name}: the journal issued {issued} turn positions under a ceiling "
        f"that permits {dim.permitted}. This is finding 006's measurement — a "
        "ceiling of 3 permitting 6 cycles — and it is the assertion a ceiling "
        "resetting on resume fails while the terminal state and the "
        "monotonicity both still look right."
    )
    # Three crashes really happened, and each in its own process.
    attempts = [line for line in (root / "attempts").read_text().splitlines()
                if line]
    assert len(set(attempts)) == len(KILLS) + 1, (
        f"{name}: {attempts} attempts. Three crashes and a final run is four "
        "processes; fewer means a kill did not land and the arm measured a "
        "shorter history than it claims."
    )


# ---------------------------------------------------------------------------
# The fourth dimension, partial, and reported as such.


def test_the_wall_clock_dimension_is_monotonic_but_cannot_yet_fire(
    tmp_path, killer
):
    """Clause 1 on the wall-clock dimension; clauses 2 and 3 are **not** met.

    The reason is upstream of this battery and is recorded in
    `src/runtime/loop.py`: nothing accrues measured wall clock, so the committed
    wall-clock total is always zero and only outstanding reservations move it.
    That still gives clause 1 a subject — the reservation of an abandoned turn
    is never released, so the total is non-decreasing across resumes — and it
    gives clauses 2 and 3 none at all.

    Written to fail if that ever changes silently. The final assertion is that
    the session did **not** end on the wall-clock ceiling: the day wall clock is
    accrued, this test fails and points at the arm that then needs writing,
    rather than continuing to pass while describing a state of affairs that no
    longer holds.
    """
    dim = DIMENSIONS["wall_clock_seconds"]
    root = tmp_path / "wall"
    root.mkdir()

    boundaries: list[tuple] = []
    for pause in KILLS:
        before = _read(root, dim.name)
        _crash_at(root, dim, pause, killer)
        boundaries.append((pause, before, _read(root, dim.name)))

    _assert_monotonic(dim, boundaries)

    # The one crash that leaves a reservation standing is the only thing that
    # moves this dimension at all, so the arm asserts it moved.
    assert boundaries[0][2][0] > 0.0, (
        "the wall-clock total is still zero after a crash inside a model call. "
        "The reservation channel is the only one that writes this dimension, so "
        "with it silent the monotonicity above holds over nothing."
    )

    repo, ledger, _ = _reader(root)
    try:
        committed = ledger.committed(SESSION).wall_clock_seconds
        held = ledger.totals(SESSION).wall_clock_seconds
    finally:
        repo.close()

    assert committed == 0.0, (
        f"measured wall clock now accrues ({committed}), so this arm's premise "
        "is stale and the wall-clock ceiling has become enforceable. Write the "
        "full three-clause arm for it and delete this one — do not relax this "
        "assertion."
    )
    assert held > committed

    conftest.note_vacuous_invariant(
        "SC-030/wall_clock_seconds",
        "the wall-clock ceiling cannot fire: nothing accrues measured wall "
        "clock (src/runtime/loop.py reconciles 0.0), so only the reservation "
        "channel moves that total. Clause 1 is asserted over the reservation; "
        "clauses 2 and 3 — the named terminal state and the bound on turns — "
        "are NOT discharged for this dimension.",
    )


# ---------------------------------------------------------------------------
# The controls.


def test_the_boundary_reading_is_taken_from_the_store_and_moves(tmp_path, killer):
    """`_read` is the instrument all four arms assert through.

    An instrument that returned a constant would make every monotonicity
    assertion above pass over nothing — `x >= x` is true for any x. So it is
    pointed at a session that provably consumed something between two readings
    and required to have registered the change.
    """
    dim = DIMENSIONS["spend_usd"]
    root = tmp_path / "control"
    root.mkdir()

    empty = _read(root, "spend_usd")
    assert empty == (0.0, 0), (
        f"a session with no journal read {empty}; the instrument is inventing a "
        "figure rather than reading rows"
    )

    _crash_at(root, dim, "turn:2", killer)
    after = _read(root, "spend_usd")
    assert after[0] == pytest.approx(2 * SPEND_PER_TURN), (
        f"two completed turns read {after[0]} rather than "
        f"{2 * SPEND_PER_TURN}. The instrument is not summing the rows the "
        "child wrote."
    )
    assert after[1] == 2


def test_the_permitted_turn_count_is_a_real_bound(tmp_path, killer):
    """Clause 3's expectation has to be capable of being exceeded.

    `permitted` is derived from the ceiling and the per-turn charge, and the
    assertion `issued <= permitted` is worthless if `permitted` is generously
    above anything the runtime could reach. This asserts the two are close: the
    turn arm, whose arithmetic is exact, must land on its bound rather than
    comfortably inside it.
    """
    dim = DIMENSIONS["turns"]
    root = tmp_path / "bound"
    root.mkdir()
    _drive(root, dim, killer)
    _, issued = _read(root, "turns")
    assert issued == dim.permitted, (
        f"the turn arm issued {issued} positions under a ceiling of "
        f"{dim.ceiling}. Anything below the bound would mean clause 3 is "
        "asserting a ceiling the session never approached, and finding 006's "
        "defect — six cycles under a ceiling of three — would sail past it."
    )
    assert TOKENS_PER_TURN > 0 and SPEND_PER_TURN > 0, (
        "the fixture charges nothing per turn, so the spend and token arms "
        "could not reach their ceilings at all"
    )
