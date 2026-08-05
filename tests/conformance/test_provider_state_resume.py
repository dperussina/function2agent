"""T056 — FR-037's opaque state, held to across a **crash and resume** boundary.

**Why this boundary needed its own fixture.** Opaque-state loss is invisible to
every output-shaped assertion: a session that regenerated the provider's
reasoning state instead of re-injecting it still produces plausible answers, and
every assertion on the answer passes. `tests/unit/test_loop.py` already asserts
the digest per turn *within* one attempt, which is the property the loop is
responsible for. What nothing asserted is the harder half: the state a provider
returned to a process that was then **killed** must reach the *next* process
byte-identically.

Finding 006 recorded exactly this as untested under *What this does NOT
establish*, over a substrate that also owned the checkpoint. Both halves are ours
now — the journal writes the bytes and the assembler re-injects them — so the
boundary is inside one mechanism, which is why it is assertable at all.

## What "byte-identical" is asserted against, and why not a digest

The pre-crash bytes are known **by construction**: `tests/fixtures/
resume_session.py` derives each turn's state from the turn index, so the expected
value is computable without reading anything the run under test wrote. An
assertion against a digest the run itself produced would be satisfied by a run
that lost the state and re-derived it consistently.

The state deliberately contains `\\x00\\x80\\xfe` — a NUL, and a UTF-8
continuation byte with no lead byte in front of it. Any path that decoded it,
or routed it through the journal's JSON payload rather than its `provider_state`
column, either raises or substitutes U+FFFD. A state made of ASCII would survive
all of those and this fixture would pass while FR-037 was being violated.

## The four arms

1. The bytes the **resumed** process injects into the next model call are the
   bytes the **killed** process's provider returned.
2. Nothing after the resume re-derives them: the state for a turn whose model
   call was already committed is read back from the journal without the provider
   being asked again.
3. `None` and `b""` stay distinguishable across the boundary. The column is
   nullable for that reason, and a resume that collapsed them would report a
   provider's *absence* of state as an empty state.
4. The state is never *readable* on the trace. FR-037 forbids logging it, and the
   span carries a digest — so the raw bytes must not appear anywhere in the
   serialized spans, before or after the resume.
"""

from __future__ import annotations

import json
import signal
import subprocess
import sys
from pathlib import Path

import pytest

from src.contracts.repository import Repository
from src.runtime.journal import (
    MODEL_STEP_INDEX,
    STEP_MODEL_CALL,
    TABLE as JOURNAL_TABLE,
    TurnJournal,
)
from src.runtime.trace import SpanWriter
from src.runtime.turn import state_digest
from tests.fixtures.resume_session import state_for

REPO = Path(__file__).resolve().parents[2]
FIXTURE = REPO / "tests" / "fixtures" / "resume_session.py"
SESSION = "s-resume"
TIMEOUT = 60


@pytest.fixture()
def killer():
    def kill(pid: int) -> None:
        subprocess.run(["kill", "-KILL", str(pid)], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return kill


def _argv(root: Path, pause: str, *, turns: int = 5) -> list[str]:
    return [sys.executable, str(FIXTURE), "--root", str(root),
            "--pause", pause, "--turns", str(turns), "--tools", "1"]


def _crash(root: Path, pause: str, killer, *, turns: int = 5) -> None:
    child = subprocess.Popen(_argv(root, pause, turns=turns),
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             text=True)
    try:
        assert child.stdout is not None
        line = child.stdout.readline().strip()
        if line != f"READY {pause}":
            _, err = child.communicate(timeout=TIMEOUT)
            raise AssertionError(
                f"the child never reached {pause}; it said {line!r}:\n{err}")
        killer(child.pid)
        assert child.wait(timeout=TIMEOUT) == -signal.SIGKILL
    finally:
        if child.poll() is None:  # pragma: no cover
            child.kill()


def _resume(root: Path, *, turns: int = 5) -> dict:
    done = subprocess.run(_argv(root, "none", turns=turns),
                          capture_output=True, text=True, timeout=TIMEOUT)
    assert done.returncode == 0, f"{done.stdout}\n{done.stderr}"
    line = [x for x in done.stdout.splitlines() if x.startswith("DONE ")]
    assert len(line) == 1
    return json.loads(line[0][len("DONE "):])


def _injected(root: Path) -> list[tuple[int, str]]:
    """Every model call the session ever made, with the state it was handed.

    Read from the file the child appends to, which spans both processes. The
    parent's own knowledge of what *should* have been injected comes from
    `state_for`, not from here.
    """
    out: list[tuple[int, str]] = []
    for row in (root / "injected").read_text().splitlines():
        if not row:
            continue
        turn, state = row.split(" ", 1)
        out.append((int(turn), state))
    return out


def _repo(root: Path) -> Repository:
    return Repository(root / "runtime.sqlite3", role="runtime",
                      tenant_id="t-1", deployment_id="d-1")


# ---------------------------------------------------------------------------
# Arm 1 — the bytes cross the boundary unchanged.


def test_the_state_a_killed_process_recorded_is_injected_by_the_next_one(
    tmp_path, killer
):
    """The boundary itself, on the one turn where it can be observed.

    Turns 0 and 1 run in the first process, which is then killed at the turn
    boundary. Turn 2 runs in the second process and its context must carry turn
    1's state — bytes the second process never saw a provider produce.
    """
    root = tmp_path / "across"
    root.mkdir()
    _crash(root, "turn:2", killer)

    before = _injected(root)
    assert [turn for turn, _ in before] == [0, 1], (
        f"the child was killed at the wrong instant: {before}")

    _resume(root)
    after = _injected(root)

    # The state handed to turn 2 is the first reading taken by the second
    # process, and turn 1's provider ran in the first.
    handed_to_turn_2 = dict(after[len(before):])
    assert 2 in handed_to_turn_2, (
        f"the resumed process made no model call for turn 2: {after}")
    assert handed_to_turn_2[2] == state_for(1).hex(), (
        "the resumed process was handed "
        f"{handed_to_turn_2[2]!r} where turn 1's provider returned "
        f"{state_for(1).hex()!r}. FR-037 requires it captured verbatim and "
        "re-injected verbatim, and a digest comparison is the only assertion "
        "that can tell re-injected from regenerated."
    )
    # And the bytes really are ones no text codec round-trips, so the arm above
    # is not passing over an ASCII state that would survive being decoded.
    with pytest.raises(UnicodeDecodeError):
        state_for(1).decode("utf-8")


def test_every_turn_after_the_boundary_carries_its_predecessors_state(
    tmp_path, killer
):
    """Not just the first turn after the resume. The chain continues.

    A resume that re-injected the last recorded state once and then lost the
    thread would pass the arm above. This asserts the whole sequence: every
    model call after turn 0 was handed the state of the turn before it,
    regardless of which process made either call.
    """
    root = tmp_path / "chain"
    root.mkdir()
    _crash(root, "turn:2", killer)
    _resume(root)

    seen = _injected(root)
    assert seen[0] == (0, "NONE"), (
        f"turn 0 was handed {seen[0]!r}. There is no prior turn, so there is no "
        "state — and NONE is a different fact from empty bytes."
    )
    for turn, state in seen[1:]:
        assert state == state_for(turn - 1).hex(), (
            f"turn {turn} was handed {state!r} rather than turn {turn - 1}'s "
            f"{state_for(turn - 1).hex()!r}"
        )
    assert [turn for turn, _ in seen] == [0, 1, 2, 3, 4], (
        f"the session's model calls were {[t for t, _ in seen]}; a repeat would "
        "mean a turn was re-run and a gap that one was skipped"
    )


# ---------------------------------------------------------------------------
# Arm 2 — the state is read back, not regenerated.


def test_a_half_finished_turns_state_comes_off_disk_and_not_from_the_provider(
    tmp_path, killer
):
    """The case where regeneration is most tempting and most wrong.

    The crash lands inside turn 2, after its model outcome was committed. The
    resumed process needs that turn's `provider_state` to build turn 3's
    context, and the provider is not available to ask — it must come out of the
    journal's own column.

    The assertion is on the **model call count**: three calls after the resume
    would mean turn 2's was made again, which is both a second charge and a
    second, different reasoning state.
    """
    root = tmp_path / "halfway"
    root.mkdir()
    _crash(root, "step:2:0", killer)

    repo = _repo(root)
    try:
        journal = TurnJournal(repo)
        step = journal.step(SESSION, 2, MODEL_STEP_INDEX)
        assert step is not None and step.is_complete, (
            "turn 2's model outcome was not committed before the crash, so "
            "there is nothing on disk for this arm to read back"
        )
        assert step.provider_state == state_for(2), (
            f"the journal holds {step.provider_state!r} for turn 2 where the "
            f"provider returned {state_for(2)!r}"
        )
    finally:
        repo.close()

    report = _resume(root)
    assert report["model_calls"] == 2, (
        f"the resumed process made {report['model_calls']} model calls. Turn "
        "2's response is on disk; turns 3 and 4 are what remain."
    )
    handed = dict(_injected(root))
    assert handed[3] == state_for(2).hex(), (
        "turn 3 was not handed turn 2's recorded state, so the resume rebuilt "
        "the context without the state the journal was holding for it"
    )


# ---------------------------------------------------------------------------
# Arm 3 — absent and empty stay different.


def test_no_state_and_empty_state_stay_distinguishable_across_the_boundary(
    tmp_path, killer
):
    """The nullable column's reason, asserted where it is easiest to lose.

    `None` means the provider returned nothing; `b""` means it returned zero
    bytes. A journal that stored the first as the second would be reporting a
    fact the provider did not state, and a resume reading it back could not tell
    which had happened.

    Asserted at the table rather than through the loop, because the loop never
    produces both in one session — and the column is what a resume reads.
    """
    root = tmp_path / "nullable"
    root.mkdir()
    _crash(root, "turn:1", killer)

    repo = _repo(root)
    try:
        journal = TurnJournal(repo)
        # Turn 0's model step, which the killed process committed with real
        # bytes, and two further steps planted with the two empty-ish values.
        assert journal.step(SESSION, 0, MODEL_STEP_INDEX).provider_state == (
            state_for(0))

        for turn, state in ((90, None), (91, b"")):
            journal.intend(
                session_id=SESSION, turn_index=turn,
                step_index=MODEL_STEP_INDEX, step_kind=STEP_MODEL_CALL,
                effect_id="model", effectful=True, payload={}, at=1.0)
            journal.commit_outcome(
                session_id=SESSION, turn_index=turn,
                step_index=MODEL_STEP_INDEX, payload={"provider": "fixture"},
                provider_state=state, at=2.0)

        absent = journal.step(SESSION, 90, MODEL_STEP_INDEX).provider_state
        empty = journal.step(SESSION, 91, MODEL_STEP_INDEX).provider_state
        assert absent is None, f"a provider's absent state came back as {absent!r}"
        assert empty == b"", f"a provider's empty state came back as {empty!r}"
        assert absent is not empty
        # And the digest keeps them apart too, so a trace reader can tell.
        assert state_digest(None) != state_digest(b"")
    finally:
        repo.close()


# ---------------------------------------------------------------------------
# Arm 4 — never logged readably, on both sides of the boundary.


def test_the_opaque_bytes_are_never_readable_on_the_trace_or_in_the_payload(
    tmp_path, killer
):
    """FR-037's third clause, which the other three arms cannot reach.

    A resume that carried the bytes correctly *and* wrote them into the trace
    would satisfy every assertion above. So this one scans the serialized spans
    and the journal's JSON payload column for the bytes themselves, on a session
    that spans a crash — because a span written by the resumed process is written
    by a different code path from one written before the kill.
    """
    root = tmp_path / "trace"
    root.mkdir()
    _crash(root, "turn:2", killer)
    _resume(root)

    repo = _repo(root)
    try:
        spans = json.dumps(SpanWriter(repo).spans(SESSION))
        payloads = " ".join(
            str(row["payload"])
            for row in repo.select(JOURNAL_TABLE, where={"session_id": SESSION})
        )
    finally:
        repo.close()

    for turn in range(5):
        raw = state_for(turn)
        assert raw.hex() not in spans, (
            f"turn {turn}'s opaque state is on the trace in hex. FR-037 "
            "forbids logging it readably; the span carries a digest."
        )
        assert raw.hex() not in payloads, (
            f"turn {turn}'s opaque state is in the journal's JSON payload. It "
            "belongs in the `provider_state` column — JSON is an "
            "interpretation, which is the thing FR-037 forbids."
        )
        # The printable tail is the part a careless `str()` would leak.
        assert f"turn-{turn}" not in spans

    # The control: the digest *is* there, so the scan above is looking at spans
    # that describe the state rather than at an empty document.
    assert state_digest(state_for(0)) in spans, (
        "no state digest appears on the trace at all, so the absence of the "
        "bytes says nothing — the scan could be reading an empty span set"
    )
