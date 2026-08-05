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

## The wall-clock arm was partial and is not any more

It used to assert clause 1 over the reservation channel alone and report the gap
through `note_vacuous_invariant`, because nothing accrued measured elapsed time:
`reconcile` passed `wall_clock_seconds=0.0`, so the committed total was
permanently zero and the ceiling could not fire.
[finding 029](../../specs/002-spec-aware-agent-runtime/findings/029-wall-clock-ceiling-unenforced.md)
measured what that was worth — a session run for 2.044 s under a ceiling of
0.001 s ending `terminated.completed` — and `src/runtime/loop.py` now measures
the interval and reconciles it. The old arm carried an assertion that it would
fail on the day that happened rather than quietly keep passing; it did, and this
is what replaced it. **All four dimensions now take the same three clauses**,
which is why there is no fourth test below.

**Which intervals count is FR-005's answer and not this battery's.** The old
docstring recorded the choice — session elapsed including idle, or only the time
an attempt was running — as an owner's decision. It is not one:
`AgentLoop._accrue_elapsed` sets out the clause that decides it and the two
readings it rules out. Time between a crash and its resume does not count.

## Why the wall-clock arm runs on a declared clock

Its `permitted` figure is arithmetic over a per-turn cost, and under a real
clock that cost is a property of the machine — so the arm would assert
something about the host, and pass or fail with it. That is the defect this
corpus has now recorded twice, and time is where it is easiest to make. The
fixture's `--clock-step` advances a clock by a declared amount per model call
and per tool call, so a turn costs `step × (1 + tools)` everywhere. Every arm
gets it, not only the wall-clock one, so the four still differ in exactly one
variable.
"""

from __future__ import annotations

import json
import signal
import subprocess
import sys
from pathlib import Path

import pytest

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

# One tool per turn, and a declared amount of clock per model call and per tool
# call. Named rather than inlined into `_argv` because the wall-clock arm's
# per-turn cost is derived from both.
TOOLS_PER_TURN = 1
CLOCK_STEP = 0.25

# Per-turn consumption, imported rather than restated so an arm cannot drift out
# of step with the fixture that produces the figures.
from tests.fixtures.resume_session import (  # noqa: E402
    RESERVE_SPEND,
    RESERVE_TOKENS,
    SPEND_PER_TURN,
    TOKENS_PER_TURN,
)

# The declared estimate for a model call in flight, on the one dimension whose
# crash window has no other cover. Set equal to a whole turn's cost so that the
# `model:0` kill contributes the same figure a completed turn would, which is
# what makes the arithmetic in `_permitted` come out exact for this arm.
WALL_CLOCK_PER_TURN = CLOCK_STEP * (1 + TOOLS_PER_TURN)
RESERVE_WALL_CLOCK = WALL_CLOCK_PER_TURN


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
                 reserved: float):
        self.name = name
        self.ceiling = ceiling
        self.permitted = _permitted(ceiling, per_turn, reserved)

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
    # Exact too, and the derivation is worth stating because a crash *does*
    # cost this dimension something. A turn accrues its model interval when the
    # call is reconciled and the rest of the turn when the turn ends, so a
    # crash inside the tool phase loses that phase's elapsed — but the resume
    # re-runs the same tool and accrues its own, which lands the turn back on
    # `WALL_CLOCK_PER_TURN`. The under-count is against the wall, not against
    # this arithmetic.
    "wall_clock_seconds": Dimension(
        "wall_clock_seconds", 3.0, per_turn=WALL_CLOCK_PER_TURN,
        reserved=RESERVE_WALL_CLOCK),
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
        "--turns", "400", "--tools", str(TOOLS_PER_TURN),
        "--reserve-wall-clock", repr(RESERVE_WALL_CLOCK),
        "--clock-step", repr(CLOCK_STEP),
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
# All four dimensions.


@pytest.mark.parametrize("name", list(CEILING_ORDER))
def test_a_ceiling_holds_across_three_crashes_and_resumes(name, tmp_path, killer):
    """SC-030's second clause, on all four dimensions the runtime accrues.

    Parametrised rather than written out four times, because they differ only
    in which ceiling is tight — and a copy per dimension is how one of them
    quietly stops asserting clause 3 while the others still do. Taken from
    `CEILING_ORDER` rather than from a list written here, so a fifth dimension
    could not be added to FR-005 and left uncovered by this battery.
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


@pytest.mark.parametrize("name", ["turns", "wall_clock_seconds"])
def test_the_permitted_turn_count_is_a_real_bound(name, tmp_path, killer):
    """Clause 3's expectation has to be capable of being exceeded.

    `permitted` is derived from the ceiling and the per-turn charge, and the
    assertion `issued <= permitted` is worthless if `permitted` is generously
    above anything the runtime could reach. This asserts the two are equal on
    the two arms whose arithmetic is exact, so they must land *on* the bound
    rather than comfortably inside it.

    **Wall clock joins this control rather than only the looser one**, and it
    can only do so because `--clock-step` makes a turn cost the same everywhere.
    Under a real clock this equality would be a claim about the machine.
    """
    dim = DIMENSIONS[name]
    root = tmp_path / f"bound-{name}"
    root.mkdir()
    _drive(root, dim, killer)
    _, issued = _read(root, name)
    assert issued == dim.permitted, (
        f"the {name} arm issued {issued} positions under a ceiling of "
        f"{dim.ceiling}, which pays for {dim.permitted}. Anything below the "
        "bound would mean clause 3 is asserting a ceiling the session never "
        "approached, and finding 006's defect — six cycles under a ceiling of "
        "three — would sail past it."
    )
    assert TOKENS_PER_TURN > 0 and SPEND_PER_TURN > 0, (
        "the fixture charges nothing per turn, so the spend and token arms "
        "could not reach their ceilings at all"
    )


def test_the_wall_clock_dimension_carries_a_measurement_and_not_only_an_estimate(
    tmp_path, killer
):
    """The distinction finding 029's crash arm turned on, kept assertable.

    Before this pass the only figure that ever reached this dimension was the
    reservation, and it was released on every reconcile — so the *committed*
    total was permanently zero and the ceiling was reachable by exactly one
    route, crashing. Both halves are asserted here because either alone is
    satisfiable by the broken state: a positive total is satisfied by an
    orphaned estimate, and a session that ends on the ceiling is too.

    So: the committed total — reservations excluded — must be positive, and it
    must be strictly below the total, because the `model:0` crash left an
    estimate outstanding that nothing may release. A measurement without the
    estimate beside it would mean the crash stopped counting.
    """
    dim = DIMENSIONS["wall_clock_seconds"]
    root = tmp_path / "measured"
    root.mkdir()
    _drive(root, dim, killer)

    repo, ledger, _ = _reader(root)
    try:
        committed = ledger.committed(SESSION).wall_clock_seconds
        total = ledger.totals(SESSION).wall_clock_seconds
    finally:
        repo.close()

    assert committed > 0.0, (
        "the committed wall-clock total is zero, so nothing measured any "
        "elapsed time and every wall-clock assertion in this file is holding "
        "over the reservation channel alone (finding 029 §4)."
    )
    assert total == pytest.approx(committed + RESERVE_WALL_CLOCK), (
        f"the total is {total} against a committed {committed}. The `model:0` "
        f"crash left exactly one reservation of {RESERVE_WALL_CLOCK} "
        "outstanding and FR-005 forbids a crash reducing the counted total, "
        "so the difference is that estimate and nothing else."
    )
