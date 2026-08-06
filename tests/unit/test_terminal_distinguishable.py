"""T068 — a clean completion and a mid-loop cancellation, side by side.

**Why this is its own file rather than another arm in `test_cancellation.py`.**
That file asserts things about cancellation. This one asserts a *difference*,
and a difference needs both runs in one place: an arm that reads only the
cancelled run cannot tell whether the value it read is distinctive or whether a
completed run reports exactly the same thing. Finding 006 primitive 2 measured
the case where it does — the removed dependency's consumer cancelled after five
events, the generator returned, and the observation was identical to a run that
finished.

**The two runs are built to be identical everywhere the distinction must not
come from.** Same rig shape, same tools, same number of turns before the end,
and — deliberately — **the same reported text**. The payload channel is made
blind on purpose, so that nothing here can pass because the two runs happened to
differ somewhere incidental. `research/03` §3 calls the indistinguishable case a
very common and very expensive bug, and it is expensive precisely because the
*content* usually still looks fine.

**What would regress, and would be caught.** Cancellation routed to
`STATE_INTERRUPTED` rather than to `terminated.operator_terminated` — the live
defect fixed at `e2e2311`, where cancel-then-attach silently resumed a cancelled
run. Under that routing the cancelled run reports no terminal state at all, its
row stays resumable, and `attach()` picks it back up. Three arms below read
those three consequences separately, because a single arm on the terminal-state
string would also pass if the string were right and the row were not.

The rig is imported from `test_cancellation.py` rather than written again. A
second copy of a runner harness is a second place for a `Ceilings` figure or a
stall threshold to drift, and the drift would be invisible: both files would go
on passing while measuring differently configured runs.
"""

from __future__ import annotations

import json

import pytest

import tests.unit.test_cancellation as cancel_fixtures
from src.contracts import terminal
from src.runtime.dispatch import ToolCall
from src.runtime.loop import ModelResponse
from src.runtime.providers.costs import PROVENANCE_OPERATOR
from src.runtime.runner import CancelToken, RunnerError

Rig = cancel_fixtures.Rig
SESSION = cancel_fixtures.SESSION
CEILINGS = cancel_fixtures.CEILINGS

#: Both runs report this. Identical on purpose — see the module docstring.
SHARED_TEXT = ""

#: How many turns each run journals. The completing run spends `TURNS - 1`
#: turns asking for tools and concludes on the next; the cancelled run is cut
#: off on the boundary after its `TURNS`th. One constant for both, so the two
#: cannot drift into different lengths without this arm saying so.
TURNS = 3


def _asks() -> ModelResponse:
    return ModelResponse(
        provider="test", provider_state=b"state", text=SHARED_TEXT,
        spend_usd=0.0, spend_provenance=PROVENANCE_OPERATOR,
        tool_calls=(ToolCall(index=0, call_id="c0", name="t"),))


def _stops() -> ModelResponse:
    """The completing turn: no tool calls, so the loop concludes on it.

    Its text is `SHARED_TEXT` rather than an answer, which is what makes the
    two runs indistinguishable by payload.
    """
    return ModelResponse(
        provider="test", provider_state=b"state", text=SHARED_TEXT,
        spend_usd=0.0, spend_provenance=PROVENANCE_OPERATOR)


def _run_to_completion(rig: Rig, *, turns_before_end: int = TURNS - 1):
    calls = {"n": 0}

    def model(context):
        calls["n"] += 1
        return _asks() if calls["n"] <= turns_before_end else _stops()

    return rig.runner.start(
        session_id=SESSION, prompt="p", ceilings=CEILINGS,
        capability_handle="handle-1", model=model, execute=lambda c: "r")


def _run_cancelled_midway(rig: Rig, *, cancel_after: int = TURNS):
    """Cancelled **mid-loop**: the model is still asking for tools when the
    consumer goes away, so the run is cut off rather than winding down.

    `cancel_after` defaults to `TURNS` so that this run journals exactly as
    many turns as the completing one. Cancellation lands at a turn boundary,
    so the turn that set the token still finishes and is recorded; a token set
    one call earlier would produce a shorter run, and the two would then be
    distinguishable by counting rather than by name.
    """
    token = CancelToken()
    calls = {"n": 0}

    def model(context):
        calls["n"] += 1
        if calls["n"] == cancel_after:
            token.cancel()
        return _asks()

    return rig.runner.start(
        session_id=SESSION, prompt="p", ceilings=CEILINGS,
        capability_handle="handle-1", model=model, execute=lambda c: "r",
        cancel=token)


def _terminal_span(rig: Rig) -> dict:
    spans = [json.loads(r["payload"]) for r in rig.spans.spans(SESSION)]
    ended = [s for s in spans if s.get("terminal_state")]
    assert len(ended) == 1, (
        f"expected exactly one span naming a terminal state, got {len(ended)}")
    return ended[0]


def _observations(rig: Rig, outcome) -> dict:
    """Every channel a caller has, gathered in one shape.

    Gathered rather than asserted one at a time so the comparison below is over
    the whole surface. An arm that checked a single field would be satisfied by
    a runtime that distinguished the two in that field and nowhere else, which
    is a distinction a caller reading anything else would miss.
    """
    row = rig.lifecycle.get(SESSION)
    span = _terminal_span(rig)
    return {
        "outcome.terminal_state": outcome.terminal_state,
        "outcome.cancelled": outcome.cancelled,
        # `getattr` rather than attribute access, so a run carrying **no**
        # marker is reported as a channel reading `None` instead of raising an
        # `AttributeError` here. Absent is one of the values this comparison
        # has to be able to see: it is what the indistinguishable case looks
        # like, and a crash would obscure which channel produced it.
        "outcome.end_of_run.reason": getattr(outcome.end_of_run, "reason", None),
        "session row terminal_state": row.terminal_state,
        "span terminal_state": span["terminal_state"],
        "span deciding_rule": span["transition"]["deciding_rule"],
    }


# ---------------------------------------------------------------------------


def test_the_payload_alone_cannot_tell_the_two_apart(tmp_path) -> None:
    """The control, and it is the arm that makes the rest of this file mean
    something.

    If the two runs differed in their reported text, every assertion below
    could be satisfied by a runtime that distinguished them by accident. This
    states that they do not: the text is the same, the turn count is the same,
    and every distinction the other arms read is a *named* one.
    """
    a, b = Rig(tmp_path / "a"), Rig(tmp_path / "b")
    done = _run_to_completion(a)
    cut = _run_cancelled_midway(b)

    assert done.text == cut.text == SHARED_TEXT
    assert len(done.turns) == len(cut.turns), (
        f"the two runs ran different numbers of turns ({len(done.turns)} and "
        f"{len(cut.turns)}), so a caller could tell them apart by counting. "
        "That is not the distinction FR-006 is about and it would mask a "
        "runtime that named them identically.")
    a.close()
    b.close()


def test_every_channel_a_caller_reads_separates_them(tmp_path) -> None:
    """The subject of T068.

    Compared field by field rather than asserted against two literals, so this
    fails on a runtime that reports the same value for both — including a
    runtime that reports `None` for both, which is what the indistinguishable
    case actually looks like.
    """
    a, b = Rig(tmp_path / "a"), Rig(tmp_path / "b")
    done = _observations(a, _run_to_completion(a))
    cut = _observations(b, _run_cancelled_midway(b))

    same = {k: v for k, v in done.items() if cut[k] == v}
    assert not same, (
        f"a completed run and a cancelled one report the same value on "
        f"{sorted(same)}. Finding 006 measured a caller that could not tell "
        f"the two apart at all; a channel that agrees is that measurement "
        f"surviving in one field.")

    # And the named values, because "they differ" would also be satisfied by
    # two wrong names. FR-006 requires each outcome to be separately *named*,
    # not merely separately encoded.
    assert done["outcome.terminal_state"] == terminal.COMPLETED.name
    assert cut["outcome.terminal_state"] == terminal.OPERATOR_TERMINATED.name
    assert done["outcome.end_of_run.reason"] == "completed"
    assert cut["outcome.end_of_run.reason"] == "cancelled"
    a.close()
    b.close()


def test_the_cancelled_session_is_not_left_resumable(tmp_path) -> None:
    """The routing regression, read off the row rather than off the name.

    Cancellation used to take FR-007's interrupt edge, and the consequence was
    not a wrong string — it was that `attach()` picked the session back up and
    a cancelled run silently continued. A terminal-state assertion alone would
    pass on a runtime that named the state correctly and left the row
    resumable, so this reads the row and then tries the attach.
    """
    rig = Rig(tmp_path)
    _run_cancelled_midway(rig)

    row = rig.lifecycle.get(SESSION)
    assert row.state == "TERMINATED", (
        f"a cancelled session is {row.state}. Cancellation is routed back "
        "through the interrupt edge, so the next attach resumes a run the "
        "consumer ended.")
    with pytest.raises(RunnerError):
        rig.runner.attach(session_id=SESSION, prompt="p",
                          model=lambda c: _stops(), execute=lambda c: "r")
    rig.close()


def test_the_completed_session_is_not_resumable_either_but_for_its_own_reason(
    tmp_path,
) -> None:
    """The other half, so the arm above is not read as *cancelled runs are
    special*. Both are unresumable; what separates them is the recorded name,
    which is exactly FR-006's requirement and not a difference in reachability.
    """
    rig = Rig(tmp_path)
    _run_to_completion(rig)

    row = rig.lifecycle.get(SESSION)
    assert row.state == "TERMINATED"
    assert row.terminal_state == terminal.COMPLETED.name
    with pytest.raises(RunnerError):
        rig.runner.attach(session_id=SESSION, prompt="p",
                          model=lambda c: _stops(), execute=lambda c: "r")
    rig.close()


def test_the_two_terminal_states_are_different_members_of_the_taxonomy(
    tmp_path,
) -> None:
    """Both names are declared, and they are not the same declaration.

    Through `terminal.require` rather than against string literals: the check
    that matters is that FR-006's closed set carries both, which is a question
    for the taxonomy and not for this file.
    """
    a, b = Rig(tmp_path / "a"), Rig(tmp_path / "b")
    done = _run_to_completion(a)
    cut = _run_cancelled_midway(b)

    first = terminal.require(done.terminal_state)
    second = terminal.require(cut.terminal_state)
    assert first is not second
    assert first.meaning != second.meaning
    a.close()
    b.close()
