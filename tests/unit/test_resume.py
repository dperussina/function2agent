"""T052 — resume reconstruction at turn-and-step granularity.

**The measurement this exists to avoid.** Finding 006 measured a loop hosted
inside a checkpointed node **re-executing 4 of 4 completed inner turns** on
resume. The checkpoint was per node, the turns were inside it, and the resume
therefore replayed the node from its start. Granularity is the whole fix: a
resume that restores *the turn* leaves the steps inside it to be redone, and a
resume that restores *the step* is the one that re-executes nothing already
recorded.

So the plan this module builds answers three separate questions, and the reason
they are separate is that each has a different wrong answer:

- **which turns are finished** — they come back as records rather than being
  re-run, which is the 4-of-4 case;
- **which single turn is half-done** — its completed steps come back as results
  and only its outstanding steps are handed out to be run, which is the step
  half;
- **which turn index comes next** — one past the highest journalled turn, so an
  abandoned turn's index is never handed back out.

**The gap is deliberate and is reported.** A turn whose model-call intent is
journalled without an outcome may have reached the provider. Reusing its index
would re-issue a paid call; leaving it out leaves a hole in the reconstructed
transcript. `abandoned` carries those indexes so the hole is a fact a caller can
read rather than a discrepancy it has to notice.
"""

from __future__ import annotations

import pytest

from src.contracts.repository import Repository
from src.runtime.dispatch import ToolCall
from src.runtime.journal import (
    MODEL_STEP_INDEX,
    STEP_MODEL_CALL,
    STEP_TOOL_CALL,
    TurnJournal,
    tool_step_index,
)
from src.runtime.resume import (
    LEGACY_MODEL_OUTCOME_SCHEMA,
    MODEL_OUTCOME_SCHEMA,
    ResumeError,
    encode_model_outcome,
    encode_tool_outcome,
    plan_resume,
)
from src.runtime.trace import OUTCOME_OK, OUTCOME_UPSTREAM_FAULT
from src.runtime.turn import ModelResponse

TENANT, DEPLOYMENT, SESSION = "t-1", "d-1", "sess-1"


def _journal(tmp_path) -> TurnJournal:
    repo = Repository(tmp_path / "runtime.sqlite3", role="runtime",
                      tenant_id=TENANT, deployment_id=DEPLOYMENT)
    return TurnJournal(repo)


def _call(index: int) -> ToolCall:
    return ToolCall(index=index, call_id=f"c{index}", name="read",
                    arguments={"path": f"/f{index}"})


def _response(*, text: str = "", calls: tuple[ToolCall, ...] = (),
              state: bytes | None = b"opaque") -> ModelResponse:
    return ModelResponse(provider="test", provider_state=state, text=text,
                         tool_calls=calls, spend_usd=0.25, tokens=17)


def _write_model_step(
    journal: TurnJournal, turn: int, response: ModelResponse, *,
    complete: bool = True, at: float = 1.0,
) -> None:
    journal.intend(
        session_id=SESSION, turn_index=turn, step_index=MODEL_STEP_INDEX,
        step_kind=STEP_MODEL_CALL, effect_id="model", effectful=True,
        payload={"turn": turn}, at=at)
    if complete:
        journal.commit_outcome(
            session_id=SESSION, turn_index=turn, step_index=MODEL_STEP_INDEX,
            payload=encode_model_outcome(response),
            provider_state=response.provider_state, at=at + 1.0)


def _write_tool_step(
    journal: TurnJournal, turn: int, call: ToolCall, *,
    complete: bool = True, body: str = "read it", at: float = 3.0,
    outcome: str = OUTCOME_OK, writes: dict | None = None,
) -> None:
    step = tool_step_index(call.index)
    journal.intend(
        session_id=SESSION, turn_index=turn, step_index=step,
        step_kind=STEP_TOOL_CALL, effect_id=call.call_id, effectful=True,
        payload={"name": call.name, "arguments": dict(call.arguments)}, at=at)
    if complete:
        journal.commit_outcome(
            session_id=SESSION, turn_index=turn, step_index=step,
            payload=encode_tool_outcome(
                outcome=outcome, body=body, started_at=at,
                finished_at=at + 0.5, writes=writes or {}),
            at=at + 0.5)


# ---------------------------------------------------------------------------
# A fresh session.


def test_an_empty_journal_plans_nothing(tmp_path) -> None:
    journal = _journal(tmp_path)
    plan = plan_resume(journal, SESSION)

    assert plan.records == ()
    assert plan.unfinished is None
    assert plan.abandoned == ()
    assert plan.next_turn_index == 0
    assert plan.is_fresh is True
    journal.repo.close()


# ---------------------------------------------------------------------------
# Completed inner turns come back rather than being re-run. Finding 006's case.


def test_four_completed_turns_come_back_as_records(tmp_path) -> None:
    """Finding 006 measured 4 of 4 re-executing. All four are reconstructed."""
    journal = _journal(tmp_path)
    for turn in range(4):
        response = _response(calls=(_call(0),), text=f"t{turn}")
        _write_model_step(journal, turn, response, at=1.0 + turn * 10)
        _write_tool_step(journal, turn, _call(0), at=3.0 + turn * 10)

    plan = plan_resume(journal, SESSION)

    assert [r.turn_index for r in plan.records] == [0, 1, 2, 3]
    assert plan.unfinished is None, (
        "every step of every turn has a committed outcome, so nothing is "
        "outstanding and nothing may be handed back out to be run"
    )
    assert plan.next_turn_index == 4
    assert plan.is_fresh is False
    journal.repo.close()


def test_a_reconstructed_turn_carries_its_calls_results_and_text(tmp_path) -> None:
    journal = _journal(tmp_path)
    response = _response(calls=(_call(0), _call(1)), text="two calls")
    _write_model_step(journal, 0, response)
    _write_tool_step(journal, 0, _call(0), body="first")
    _write_tool_step(journal, 0, _call(1), body="second",
                     outcome=OUTCOME_UPSTREAM_FAULT)

    record = plan_resume(journal, SESSION).records[0]

    assert record.provider == "test"
    assert record.text == "two calls"
    assert [c.index for c in record.tool_calls] == [0, 1]
    assert [c.call_id for c in record.tool_calls] == ["c0", "c1"]
    assert record.tool_calls[0].arguments == {"path": "/f0"}
    assert [r.index for r in record.tool_results] == [0, 1]
    assert record.tool_results[0].body == "first"
    assert record.tool_results[1].outcome == OUTCOME_UPSTREAM_FAULT, (
        "a branch that faulted is an outcome, and its outcome has to survive "
        "the resume as the one it was — reconstructing it as ok would turn a "
        "recorded failure into a recorded success"
    )
    journal.repo.close()


def test_results_are_reconstructed_in_declared_order_not_journal_order(
    tmp_path,
) -> None:
    """T-08's ordering is a property of the record, so a resume has to rebuild
    it rather than inherit whatever order the rows came back in.

    The steps are committed in reverse, which is what a fan-out that finished
    out of order produces.
    """
    journal = _journal(tmp_path)
    response = _response(calls=(_call(0), _call(1), _call(2)))
    _write_model_step(journal, 0, response)
    for call in (_call(2), _call(0), _call(1)):
        _write_tool_step(journal, 0, call, body=f"b{call.index}")

    record = plan_resume(journal, SESSION).records[0]
    assert [r.index for r in record.tool_results] == [0, 1, 2]
    assert [r.body for r in record.tool_results] == ["b0", "b1", "b2"]
    journal.repo.close()


def test_the_opaque_state_comes_back_byte_identical(tmp_path) -> None:
    """FR-037 across the boundary finding 006 recorded as untested."""
    journal = _journal(tmp_path)
    state = bytes(range(256))
    _write_model_step(journal, 0, _response(text="done", state=state))

    record = plan_resume(journal, SESSION).records[0]
    assert record.provider_state == state
    journal.repo.close()


def test_a_provider_that_returned_no_state_is_not_reconstructed_as_empty(
    tmp_path,
) -> None:
    """`None` and `b""` are different answers, and the difference is the one a
    conditional presence assertion depends on (T061's shape)."""
    journal = _journal(tmp_path)
    _write_model_step(journal, 0, _response(text="done", state=None))
    _write_model_step(journal, 1, _response(text="done", state=b""), at=11.0)

    records = plan_resume(journal, SESSION).records
    assert records[0].provider_state is None
    assert records[1].provider_state == b""
    journal.repo.close()


# ---------------------------------------------------------------------------
# The step half: a turn whose model call finished and whose tools did not.


def test_a_half_finished_turn_is_unfinished_not_a_record(tmp_path) -> None:
    journal = _journal(tmp_path)
    response = _response(calls=(_call(0), _call(1)))
    _write_model_step(journal, 0, response)
    _write_tool_step(journal, 0, _call(0), body="already ran")
    _write_tool_step(journal, 0, _call(1), complete=False)

    plan = plan_resume(journal, SESSION)

    assert plan.records == (), "a turn with an outstanding step is not finished"
    assert plan.unfinished is not None
    assert plan.unfinished.turn_index == 0
    assert [r.index for r in plan.unfinished.completed] == [0]
    assert plan.unfinished.completed[0].body == "already ran"
    assert [c.index for c in plan.unfinished.pending] == [1], (
        "only the step with no committed outcome may be handed back out; "
        "handing back step 0 is the repeat FR-007 forbids"
    )
    journal.repo.close()


def test_the_model_call_of_an_unfinished_turn_is_not_handed_back_out(
    tmp_path,
) -> None:
    """The response is reconstructed, so the loop finishes the turn without
    calling the provider again. Re-calling it would be a second charge for a
    turn the journal already holds the answer to."""
    journal = _journal(tmp_path)
    response = _response(calls=(_call(0),), text="the model already spoke",
                         state=b"opaque-state")
    _write_model_step(journal, 0, response)
    _write_tool_step(journal, 0, _call(0), complete=False)

    unfinished = plan_resume(journal, SESSION).unfinished
    assert unfinished.response.text == "the model already spoke"
    assert unfinished.response.provider_state == b"opaque-state"
    assert unfinished.response.spend_usd == pytest.approx(0.25)
    assert unfinished.response.tokens == 17
    journal.repo.close()


def test_a_tool_step_with_an_intent_and_no_outcome_is_pending(tmp_path) -> None:
    """The crash window. An intent with no outcome means *maybe it ran*, and the
    safe reading of maybe is to run it under the same idempotency key."""
    journal = _journal(tmp_path)
    _write_model_step(journal, 0, _response(calls=(_call(0),)))
    _write_tool_step(journal, 0, _call(0), complete=False)

    plan = plan_resume(journal, SESSION)
    assert [c.call_id for c in plan.unfinished.pending] == ["c0"]
    journal.repo.close()


def test_a_tool_step_never_intended_is_also_pending(tmp_path) -> None:
    """The other crash window: killed after the model outcome, before any tool
    intent was written."""
    journal = _journal(tmp_path)
    _write_model_step(journal, 0, _response(calls=(_call(0), _call(1))))

    plan = plan_resume(journal, SESSION)
    assert [c.index for c in plan.unfinished.pending] == [0, 1]
    assert plan.unfinished.completed == ()
    journal.repo.close()


def test_completed_turns_and_one_unfinished_turn_coexist(tmp_path) -> None:
    journal = _journal(tmp_path)
    _write_model_step(journal, 0, _response(calls=(_call(0),)), at=1.0)
    _write_tool_step(journal, 0, _call(0), at=3.0)
    _write_model_step(journal, 1, _response(calls=(_call(0),)), at=11.0)
    _write_tool_step(journal, 1, _call(0), complete=False, at=13.0)

    plan = plan_resume(journal, SESSION)
    assert [r.turn_index for r in plan.records] == [0]
    assert plan.unfinished.turn_index == 1
    assert plan.next_turn_index == 2
    journal.repo.close()


# ---------------------------------------------------------------------------
# Abandoned turns: the gap, reported rather than hidden.


def test_a_turn_whose_model_call_never_returned_is_abandoned(tmp_path) -> None:
    journal = _journal(tmp_path)
    _write_model_step(journal, 0, _response(calls=(_call(0),)), at=1.0)
    _write_tool_step(journal, 0, _call(0), at=3.0)
    _write_model_step(journal, 1, _response(), complete=False, at=11.0)

    plan = plan_resume(journal, SESSION)
    assert plan.abandoned == (1,)
    assert [r.turn_index for r in plan.records] == [0]
    assert plan.unfinished is None
    assert plan.next_turn_index == 2, (
        "turn 1's intent is journalled, so its call may have reached the "
        "provider; handing index 1 back out would re-issue it"
    )
    journal.repo.close()


# ---------------------------------------------------------------------------
# What the plan refuses rather than repairing.


def test_two_unfinished_turns_are_refused(tmp_path) -> None:
    """Turns are sequential, so only the last can be half-done. Two means the
    journal describes something this loop cannot have produced, and picking one
    would be a guess recorded as a reconstruction."""
    journal = _journal(tmp_path)
    for turn in (0, 1):
        _write_model_step(journal, turn, _response(calls=(_call(0),)),
                          at=1.0 + turn * 10)
        _write_tool_step(journal, turn, _call(0), complete=False,
                         at=3.0 + turn * 10)

    with pytest.raises(ResumeError, match="more than one"):
        plan_resume(journal, SESSION)
    journal.repo.close()


def test_an_unfinished_turn_that_is_not_the_last_is_refused(tmp_path) -> None:
    journal = _journal(tmp_path)
    _write_model_step(journal, 0, _response(calls=(_call(0),)), at=1.0)
    _write_tool_step(journal, 0, _call(0), complete=False, at=3.0)
    _write_model_step(journal, 1, _response(text="done"), at=11.0)

    with pytest.raises(ResumeError, match="last turn"):
        plan_resume(journal, SESSION)
    journal.repo.close()


def test_a_turn_with_no_model_step_is_refused(tmp_path) -> None:
    """Every turn this loop runs journals its model call as step 0. A turn
    without one was written by something else, and reconstructing a response
    for it would mean inventing the provider's half."""
    journal = _journal(tmp_path)
    _write_model_step(journal, 0, _response(calls=(_call(0),)))
    _write_tool_step(journal, 0, _call(0))
    journal.intend(
        session_id=SESSION, turn_index=1, step_index=tool_step_index(0),
        step_kind=STEP_TOOL_CALL, effect_id="c0", effectful=True,
        payload={}, at=20.0)

    with pytest.raises(ResumeError, match="no model-call step"):
        plan_resume(journal, SESSION)
    journal.repo.close()


def test_a_plan_is_per_session(tmp_path) -> None:
    journal = _journal(tmp_path)
    _write_model_step(journal, 0, _response(text="done"))
    assert plan_resume(journal, "another").is_fresh is True
    journal.repo.close()


# ---------------------------------------------------------------------------
# The writes a resumed session must not lose.


def test_state_writes_recorded_before_the_crash_are_reconstructed(tmp_path) -> None:
    """A resumed session that lost the merged state would re-derive it by
    re-running the tools that produced it, which is the repeat under a different
    name."""
    journal = _journal(tmp_path)
    _write_model_step(journal, 0, _response(calls=(_call(0),)))
    _write_tool_step(journal, 0, _call(0), writes={"cursor": 7})

    record = plan_resume(journal, SESSION).records[0]
    assert record.tool_results[0].writes == {"cursor": 7}
    journal.repo.close()


# ---------------------------------------------------------------------------
# Journals written before turns carried a price.
#
# The migration question this answers: a session journaled before the pricing
# seam existed has model outcomes with a `spend_usd` of `0.0` — the field's old
# **default**, written by every response nobody priced. Reading that back as a
# price would resume the session with a spend total that is arithmetically valid
# and factually invented, and FR-005's ceiling would then be compared against
# it. So revision 1 payloads come back **unpriced** and the plan says which
# turns they were. Refusing the resume outright was the alternative and is worse
# for the same reason a crash over-counts rather than under-counts: the turns
# happened, and losing them re-runs their tools.


def _legacy_payload(response: ModelResponse) -> dict:
    """What `encode_model_outcome` wrote before the schema key existed."""
    payload = encode_model_outcome(response)
    del payload["schema"]
    for key in ("model", "input_tokens", "output_tokens"):
        payload.pop(key, None)
    # The old default, which is exactly the value that must not be believed.
    payload["spend_usd"] = 0.0
    return payload


def _write_legacy_model_step(journal: TurnJournal, turn: int,
                             response: ModelResponse) -> None:
    journal.intend(
        session_id=SESSION, turn_index=turn, step_index=MODEL_STEP_INDEX,
        step_kind=STEP_MODEL_CALL, effect_id="model", effectful=True,
        payload={"turn": turn}, at=1.0)
    journal.commit_outcome(
        session_id=SESSION, turn_index=turn, step_index=MODEL_STEP_INDEX,
        payload=_legacy_payload(response),
        provider_state=response.provider_state, at=2.0)


def test_a_turn_journaled_before_prices_existed_comes_back_unpriced(
    tmp_path,
) -> None:
    """`0.0` in a revision-1 payload is the old default, not a measurement.

    The payload says `0.0` and the plan still reports the turn as unpriced, so
    what is being asserted is that the recorded figure was **not believed** —
    which is the whole of the migration decision.
    """
    journal = _journal(tmp_path)
    _write_legacy_model_step(journal, 0, _response(text="done"))

    plan = plan_resume(journal, SESSION)
    assert plan.unpriced_turns == (0,)
    assert plan.has_unpriced_spend is True
    # And the turn itself survives: refusing the resume was the alternative, and
    # it loses work that actually happened.
    assert plan.records[0].text == "done"
    journal.repo.close()


def test_the_plan_names_which_resumed_turns_have_no_price(tmp_path) -> None:
    """An unpriced turn the plan did not disclose is one nobody can act on.

    The caller's choice — refuse the resume, re-price, or continue knowing the
    total is a floor — is only available if the plan says *which* turns are
    affected, so this is part of the plan's contract and not a log line.
    """
    journal = _journal(tmp_path)
    _write_legacy_model_step(journal, 0, _response(text="a"))
    _write_model_step(journal, 1, _response(text="b"), at=10.0)

    plan = plan_resume(journal, SESSION)
    # Specific, not a flag on the whole session: turn 1 was written at the
    # current revision and carries a real figure, and a session-level flag would
    # make the two indistinguishable.
    assert plan.unpriced_turns == (0,)
    assert len(plan.records) == 2
    journal.repo.close()


def test_a_payload_from_a_later_revision_is_refused_not_partially_read(
    tmp_path,
) -> None:
    """Finding 016's defect, arriving through the journal rather than the wire.

    A payload this build does not understand has fields this build does
    recognise, and reading those is how a rebuild silently drops whatever it did
    not know about.
    """
    journal = _journal(tmp_path)
    response = _response(text="done")
    payload = encode_model_outcome(response)
    payload["schema"] = MODEL_OUTCOME_SCHEMA + 1
    journal.intend(
        session_id=SESSION, turn_index=0, step_index=MODEL_STEP_INDEX,
        step_kind=STEP_MODEL_CALL, effect_id="model", effectful=True,
        payload={"turn": 0}, at=1.0)
    journal.commit_outcome(
        session_id=SESSION, turn_index=0, step_index=MODEL_STEP_INDEX,
        payload=payload, provider_state=response.provider_state, at=2.0)

    with pytest.raises(ResumeError, match="declares schema"):
        plan_resume(journal, SESSION)
    journal.repo.close()


def test_a_turn_written_now_carries_the_model_the_price_was_computed_at(
    tmp_path,
) -> None:
    """The other half of the gate: revision 2 records what revision 1 lacked.

    A journalled price is only checkable if what it was computed *over* is
    journalled beside it, because the rate is keyed on `(provider, model)` and
    applied to a token split. A lone float is a number no later reader can
    reconcile with the table it supposedly came from.
    """
    journal = _journal(tmp_path)
    response = ModelResponse(
        provider="test", provider_state=b"opaque", text="done", tool_calls=(),
        model="claude-sonnet-5", spend_usd=12.0, tokens=30,
        input_tokens=10, output_tokens=20)
    payload = encode_model_outcome(response)

    assert payload["schema"] == MODEL_OUTCOME_SCHEMA
    assert MODEL_OUTCOME_SCHEMA > LEGACY_MODEL_OUTCOME_SCHEMA
    assert payload["model"] == "claude-sonnet-5"
    assert (payload["input_tokens"], payload["output_tokens"]) == (10, 20)
    assert payload["spend_usd"] == 12.0

    _write_model_step(journal, 0, response)
    plan = plan_resume(journal, SESSION)
    # Priced, so it is absent from the disclosure rather than merely present in
    # the records.
    assert plan.unpriced_turns == ()
    assert plan.has_unpriced_spend is False
    journal.repo.close()


def test_an_unpriced_turn_is_journaled_as_null_and_not_as_zero(tmp_path) -> None:
    """The encoder's half of the same decision, at the other end of the round
    trip: `None` must not become `0.0` on the way to disk, or the next reader
    inherits the defect the decoder above refuses to repeat."""
    response = ModelResponse(
        provider="test", provider_state=b"opaque", text="", tool_calls=())
    payload = encode_model_outcome(response)

    assert payload["spend_usd"] is None
    assert payload["input_tokens"] is None and payload["output_tokens"] is None
