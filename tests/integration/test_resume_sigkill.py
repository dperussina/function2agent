"""T054 — resume across a real crash. `SIGKILL`, from a separate process.

**What makes this different from every other resume test in the tree.**
`tests/unit/test_loop.py` and `tests/unit/test_resume.py` build a half-finished
journal and then resume from it. Both are worth having and neither can find the
class of defect this file exists for, because both construct the pre-crash state
themselves. Here the pre-crash state is whatever a process that was **killed**
happened to leave on disk, and the question is whether the next process reads it
correctly.

That distinction is the one T050 measured the hard way. `Repository.insert` left
an implicit transaction open on `IntegrityError` and held a write lock until the
busy timeout; it survived two phases of single-process testing and was findable
only across processes. A crash test that simulated the crash in-process would be
in that family — it would be testing the simulation.

So: the session runs in a child process started with `subprocess.Popen`; the
child announces the instant it has reached and then waits; and the signal is sent
by a **third** process, `kill -KILL`, exactly as
`tests/integration/test_lease_revocation.py` does and for the reason it gives —
no `finally`, no `atexit`, no flush, and no argument that the victim cooperated.

## The three arms and the two claims

FR-007's clause has two halves and each arm asserts both:

- **no completed inner turn re-executes** — asserted on the model calls the
  second attempt made, counted from a file the child appends to, not from
  anything the child reports about itself;
- **no recorded local effect repeats** — asserted on the effects file, where a
  repeat is a duplicate line.

`turn:2` kills at a turn boundary. `step:1:1` kills inside a step, with call 0's
outcome committed and call 1's effect performed but unrecorded. `model:1` kills
with a reservation outstanding, which is the arm T053 is for.

**The `step` arm's asymmetry is deliberate and is the reason the arm exists.**
Call 1 *does* run again, because its intent is on disk and its outcome is not —
`src/runtime/journal.py`'s table calls that row ambiguous and resolves it towards
re-running. Call 0 must not. An arm that asserted no effect at all repeated would
fail for the correct behaviour; an arm that asserted nothing about call 0 would
pass for a resume with no step granularity at all. Both halves are needed and
neither is the other.

## What this file does not establish

It measures one platform, one process pair, one kill per session. It is not a
statement about resume under concurrent resumers — two processes resuming the
same session at once is `tests/integration/test_store_concurrent_writers.py`'s
subject, and the uniqueness that makes it safe is the store's, not this file's.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
FIXTURE = REPO / "tests" / "fixtures" / "resume_session.py"

# Long enough that a loaded CI box is not mistaken for a hang; short enough that
# a genuine hang does not hold the suite for minutes. A child that never
# announces is a failure with a message, never a timeout with none.
READY_TIMEOUT = 60


@pytest.fixture()
def killer():
    """Sends `SIGKILL` from a **third** process. Finding 006's technique.

    Copied deliberately rather than imported from
    `tests/integration/test_lease_revocation.py`: importing it would make one
    file's fixture the other's dependency for no gain, and the four lines are
    the whole point of the arm.
    """
    def kill(pid: int) -> None:
        subprocess.run(
            ["kill", "-KILL", str(pid)], check=True,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    return kill


def _spawn(root: Path, *, pause: str, turns: int = 4, tools: int = 2):
    return subprocess.Popen(
        [sys.executable, str(FIXTURE),
         "--root", str(root), "--pause", pause,
         "--turns", str(turns), "--tools", str(tools)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )


def _await_ready(child, marker: str) -> None:
    """Block until the child says it reached `marker`, or say why it did not."""
    assert child.stdout is not None
    line = child.stdout.readline().strip()
    if line != f"READY {marker}":
        _, err = child.communicate(timeout=READY_TIMEOUT)
        raise AssertionError(
            f"the child never reached {marker}; it said {line!r} and then:\n{err}"
        )


def _lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [line for line in path.read_text().splitlines() if line]


def _finish(root: Path, *, turns: int = 4, tools: int = 2) -> dict:
    """Resume in a fresh process and run to a terminal state."""
    done = subprocess.run(
        [sys.executable, str(FIXTURE),
         "--root", str(root), "--pause", "none",
         "--turns", str(turns), "--tools", str(tools)],
        capture_output=True, text=True, timeout=READY_TIMEOUT,
    )
    assert done.returncode == 0, (
        f"the resumed attempt failed:\n{done.stdout}\n{done.stderr}")
    reported = [line for line in done.stdout.splitlines()
                if line.startswith("DONE ")]
    assert len(reported) == 1, f"the resumed attempt reported {reported}"
    return json.loads(reported[0][len("DONE "):])


def _crash(root: Path, killer, *, pause: str, turns: int = 4, tools: int = 2):
    """Run until `pause`, kill from outside, and return what was on disk."""
    child = _spawn(root, pause=pause, turns=turns, tools=tools)
    try:
        _await_ready(child, pause)
        before_effects = _lines(root / "effects")
        before_injected = _lines(root / "injected")
        killer(child.pid)
        assert child.wait(timeout=READY_TIMEOUT) == -signal.SIGKILL, (
            "the child did not die of SIGKILL, so something ran on the way "
            "down and this is not the crash path"
        )
    finally:
        if child.poll() is None:  # pragma: no cover — only on an assert above
            child.kill()
    return before_effects, before_injected


def _repeats(before: list[str], after: list[str]) -> list[str]:
    """Effects that appear more often after the resume than they were recorded.

    Counted rather than set-differenced. A set difference is blind to the exact
    defect FR-007 forbids: an effect that ran twice is *in* both sets.
    """
    counts = Counter(after)
    return sorted(
        f"{line} ×{counts[line]}"
        for line in set(before) if counts[line] > 1
    )


# ---------------------------------------------------------------------------
# Arm 1 — the turn boundary.


def test_a_turn_boundary_crash_re_executes_no_completed_turn(tmp_path, killer):
    """Two turns complete, the process dies between turns, a new one finishes.

    The assertion that carries the weight is on **`model_calls`**: the resumed
    process must call the provider only for the turns that had not happened.
    Finding 006 measured 4 of 4 completed inner turns re-executing, and every
    output-shaped assertion passed while it did — a re-executed turn produces a
    plausible answer.
    """
    root = tmp_path / "boundary"
    root.mkdir()
    before_effects, before_injected = _crash(root, killer, pause="turn:2")

    assert [line.split()[0] for line in before_injected] == ["0", "1"], (
        f"the child was killed at the wrong instant: {before_injected}"
    )
    assert len(before_effects) == 4, (
        f"two turns of two tools should have left four effects: {before_effects}"
    )

    report = _finish(root)

    assert report["terminal_state"] == "terminated.completed"
    assert report["model_calls"] == 2, (
        f"the resumed attempt called the provider {report['model_calls']} "
        "times. Turns 0 and 1 were already complete, so only turns 2 and 3 "
        "are outstanding; finding 006 measured all of the completed ones "
        "re-executing."
    )
    assert report["turns"] == [0, 1, 2, 3], (
        f"the session's transcript reads {report['turns']}. §2.2 requires the "
        "numbering dense and monotonic across the session, not per attempt."
    )

    after = _lines(root / "effects")
    assert _repeats(before_effects, after) == [], (
        "a recorded local effect ran a second time after the resume"
    )
    # And the two attempts really were two processes.
    assert len(set(_lines(root / "attempts"))) == 2


# ---------------------------------------------------------------------------
# Arm 2 — inside a step.


def test_a_mid_step_crash_re_executes_no_recorded_step(tmp_path, killer):
    """The granularity T052 exists for, at the level below the turn.

    Turn 1's model call is committed and so is its call 0. Call 1's *effect*
    happened and its outcome did not. So on resume: no model call for turn 1, no
    second run of call 0, and call 1 runs again — which is correct and is why
    the two halves are asserted separately.
    """
    root = tmp_path / "midstep"
    root.mkdir()
    before_effects, before_injected = _crash(root, killer, pause="step:1:1")

    assert [line.split()[0] for line in before_injected] == ["0", "1"]
    recorded = [line for line in before_effects if line.startswith("1/t1c0")]
    assert recorded, (
        f"turn 1's call 0 never ran, so there is no recorded step for this "
        f"arm to assert about: {before_effects}"
    )

    report = _finish(root)

    assert report["terminal_state"] == "terminated.completed"
    assert report["model_calls"] == 2, (
        f"the resumed attempt made {report['model_calls']} model calls. Turn "
        "1's response is on disk, so only turns 2 and 3 need the provider — a "
        "third call would be a second charge for an answer already recorded."
    )

    after = Counter(_lines(root / "effects"))
    assert after["1/t1c0"] == 1, (
        f"turn 1's call 0 ran {after['1/t1c0']} times. Its outcome was "
        "committed before the crash, and FR-007 forbids a recorded effect "
        "repeating."
    )
    assert after["0/t0c0"] == 1 and after["0/t0c1"] == 1, (
        "turn 0's effects repeated, so the resume is at turn granularity or "
        "coarser"
    )
    assert after["1/t1c1"] == 2, (
        f"turn 1's call 1 ran {after['1/t1c1']} times. Exactly two is the "
        "correct answer and the arm asserts it rather than tolerating it: its "
        "intent was journalled and its outcome was not, which is the one "
        "ambiguous row in the journal's table, and a resume that skipped it "
        "would drop an effect the session's result depends on."
    )


# ---------------------------------------------------------------------------
# Arm 3 — a reservation outstanding at the moment of death (U-30).


def test_a_crash_inside_the_model_call_over_counts_rather_than_under(
    tmp_path, killer
):
    """T053's reason for existing, measured on a real kill.

    The child dies with turn 1's intent journalled, its reservation on the
    ledger and no outcome. Before this task the loop accrued *after* the call,
    so this crash lost the spend entirely and a resumed session read a total
    lower than what had really been spent.

    The arm asserts the direction, not a figure: the total after the resume is
    strictly greater than the number of *completed* turns times the per-turn
    charge, because the abandoned turn's estimate is still standing.
    """
    root = tmp_path / "inflight"
    root.mkdir()
    _crash(root, killer, pause="model:1")

    report = _finish(root)
    assert report["terminal_state"] == "terminated.completed"

    from tests.fixtures.resume_session import RESERVE_SPEND, SPEND_PER_TURN

    # Turn 1 was abandoned, so its index is never handed back out and the
    # session's completed turns are 0, 2 and 3.
    assert report["turns"] == [0, 2, 3], (
        f"the transcript reads {report['turns']}. Turn 1's model call may have "
        "reached the provider, so reusing its index would risk a duplicate "
        "charge; the gap is the safe answer and `resume.py` reports it."
    )
    completed = 3
    assert report["spend_usd"] == pytest.approx(
        completed * SPEND_PER_TURN + RESERVE_SPEND), (
        f"the total reads {report['spend_usd']}. The three completed turns "
        f"account for {completed * SPEND_PER_TURN}; the abandoned turn's "
        f"{RESERVE_SPEND} estimate must still be standing, because nothing "
        "released it and nothing knows what the call really cost."
    )
    assert report["spend_usd"] > completed * SPEND_PER_TURN, (
        "the crash lost the abandoned call's spend, which is U-30's "
        "under-count: a resumed session reads less than was really spent and "
        "a ceiling that should have fired does not"
    )
    assert report["turn_total"] == completed + 1, (
        f"the turn total reads {report['turn_total']} for {completed} "
        "completed turns. The abandoned turn consumed a position and must "
        "consume a turn of the ceiling too, or a session could cycle "
        "indefinitely by crashing."
    )


# ---------------------------------------------------------------------------
# The controls. An arm whose instrument cannot register the defect proves nothing.


def test_the_effect_log_would_register_a_repeat(tmp_path, killer):
    """`_repeats` is the instrument arm 1 asserts an empty result from.

    An instrument that always returned empty would make that arm pass over any
    behaviour at all, so it is pointed at a run in which an effect provably ran
    twice: the mid-step arm's call 1, which repeats **by design** because its
    outcome was never recorded.

    The two assertions are the two halves of a usable instrument. It registers
    the repeat that happened, and it stays silent about the effects whose
    outcomes *were* committed. A `_repeats` that could only do the first would
    make arm 1's empty result meaningless; one that could only do the second
    would be the always-empty instrument this control exists to rule out.
    """
    root = tmp_path / "control"
    root.mkdir()
    before, _ = _crash(root, killer, pause="step:1:1")
    _finish(root)
    after = _lines(root / "effects")

    assert _repeats(before, after) == ["1/t1c1 ×2"], (
        "the instrument did not register the one effect that is known to have "
        "run twice, so its silence about the others means nothing"
    )
    recorded = [line for line in before if line != "1/t1c1"]
    assert _repeats(recorded, after) == [], (
        "the instrument flagged an effect whose outcome was committed, so it "
        "cannot tell a recorded effect from an unrecorded one and arm 1's "
        "empty result would be empty for the wrong reason"
    )


def test_the_child_really_is_a_separate_process(tmp_path, killer):
    """The premise the whole file rests on, asserted rather than assumed.

    A fixture that had silently degraded to running in the test process would
    measure the in-process case and report it as the crash case. The pid is
    read from the file the child writes, so it is the child's own view.
    """
    root = tmp_path / "pid"
    root.mkdir()
    child = _spawn(root, pause="turn:1")
    try:
        _await_ready(child, "turn:1")
        recorded = _lines(root / "attempts")
        assert recorded == [str(child.pid)], (
            f"the child reported pid {recorded} and the parent spawned "
            f"{child.pid}"
        )
        assert child.pid != os.getpid()
        killer(child.pid)
        assert child.wait(timeout=READY_TIMEOUT) == -signal.SIGKILL
    finally:
        if child.poll() is None:  # pragma: no cover
            child.kill()
