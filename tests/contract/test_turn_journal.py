"""T051 — the write-ahead intent journal, and the two commit points that make it one.

**What a journal has to establish that a log does not.** A log records what
happened. This has to answer a question asked by a *different process* after the
first one was killed with no unwind: *did step (turn 3, step 2) already happen?*
FR-007 needs that answer to be recoverable from disk alone, so the two commit
points are ordered rather than merely present —

- the **intent** is committed *before* the effect, so a step that ran is never
  invisible; and
- the **outcome** is committed *after* it, so a step whose outcome is recorded
  is one that definitely finished.

The consequence of that ordering is deliberately asymmetric: a crash can leave
an intent with no outcome, and that reads as *maybe it ran*, which is the safe
direction. It can never leave an outcome with no intent, and `commit_outcome`
refuses to create one — a journal that accepted an orphan outcome would have a
second way to record a step, and the resume reader would have to guess which
came first.

**Why the uniqueness lives in the store.** `Repository.create_table`'s own
docstring gives the reason: an in-process guard guards one object in one
process, and *"a resumed one after a crash shares nothing with the first"*.
Recording an outcome twice is exactly the repeat FR-007 forbids, so it is
refused by an index rather than by a check somebody could be holding a stale
copy of.
"""

from __future__ import annotations

import pytest

from src.contracts.repository import Repository
from src.runtime.journal import (
    KIND_INTENT,
    KIND_OUTCOME,
    MODEL_STEP_INDEX,
    STEP_MODEL_CALL,
    STEP_TOOL_CALL,
    JournalError,
    TurnJournal,
    idempotency_key,
    tool_step_index,
)

TENANT, DEPLOYMENT, SESSION = "t-1", "d-1", "sess-1"


def _journal(tmp_path) -> TurnJournal:
    repo = Repository(tmp_path / "runtime.sqlite3", role="runtime",
                      tenant_id=TENANT, deployment_id=DEPLOYMENT)
    return TurnJournal(repo)


def _intend_model(journal: TurnJournal, turn: int, *, at: float = 1.0) -> str:
    return journal.intend(
        session_id=SESSION, turn_index=turn, step_index=MODEL_STEP_INDEX,
        step_kind=STEP_MODEL_CALL, effect_id="model", effectful=True,
        payload={"turns_in_context": turn}, at=at)


# ---------------------------------------------------------------------------
# The key.


def test_the_key_is_the_session_the_turn_and_the_step(tmp_path) -> None:
    journal = _journal(tmp_path)
    _intend_model(journal, 0)
    journal.intend(
        session_id=SESSION, turn_index=0, step_index=tool_step_index(0),
        step_kind=STEP_TOOL_CALL, effect_id="c0", effectful=True,
        payload={"name": "read"}, at=2.0)
    _intend_model(journal, 1)

    steps = journal.steps(SESSION)
    assert [(s.turn_index, s.step_index) for s in steps] == [(0, 0), (0, 1), (1, 0)]
    journal.repo.close()


def test_the_model_call_is_step_zero_and_tool_calls_follow_it() -> None:
    """The step index has to be dense within the turn, and the model call is
    the step that produced the tool calls, so it cannot share a position with
    one of them."""
    assert MODEL_STEP_INDEX == 0
    assert tool_step_index(0) == 1
    assert tool_step_index(3) == 4


def test_a_step_index_below_zero_is_refused(tmp_path) -> None:
    journal = _journal(tmp_path)
    with pytest.raises(JournalError, match="position"):
        journal.intend(
            session_id=SESSION, turn_index=0, step_index=-1,
            step_kind=STEP_TOOL_CALL, effect_id="c", effectful=True,
            payload={}, at=1.0)
    journal.repo.close()


def test_the_idempotency_key_is_the_same_on_a_retry_and_differs_per_step() -> None:
    """The property that makes a retry safe rather than a second effect.

    A key derived from anything that changes between attempts — a clock, a
    uuid, a process id — is a *new* key on the retry, which is the same as
    having none. So it is derived from the step's coordinates and the effect's
    own identity, and nothing else.
    """
    first = idempotency_key(SESSION, 3, 2, "call-abc")
    again = idempotency_key(SESSION, 3, 2, "call-abc")
    assert first == again

    assert idempotency_key(SESSION, 3, 2, "call-abc") != \
        idempotency_key(SESSION, 3, 3, "call-abc")
    assert idempotency_key(SESSION, 3, 2, "call-abc") != \
        idempotency_key(SESSION, 4, 2, "call-abc")
    assert idempotency_key(SESSION, 3, 2, "call-abc") != \
        idempotency_key("other", 3, 2, "call-abc")
    assert idempotency_key(SESSION, 3, 2, "call-abc") != \
        idempotency_key(SESSION, 3, 2, "call-abd")


def test_an_effectful_step_always_carries_a_key(tmp_path) -> None:
    journal = _journal(tmp_path)
    key = _intend_model(journal, 0)
    assert key == idempotency_key(SESSION, 0, MODEL_STEP_INDEX, "model")
    assert journal.steps(SESSION)[0].idempotency_key == key
    journal.repo.close()


def test_a_model_or_tool_step_cannot_declare_itself_effectless(tmp_path) -> None:
    """`effectful` is recorded, so it has to mean something.

    A flag a caller may set either way on a step that always spends money or
    always runs a tool is decoration, and decoration is what an auditor reads
    as a fact. Both known step kinds are effectful, so declaring otherwise is
    refused rather than recorded.
    """
    journal = _journal(tmp_path)
    with pytest.raises(JournalError, match="effectful"):
        journal.intend(
            session_id=SESSION, turn_index=0, step_index=MODEL_STEP_INDEX,
            step_kind=STEP_MODEL_CALL, effect_id="model", effectful=False,
            payload={}, at=1.0)
    journal.repo.close()


def test_an_unknown_step_kind_is_refused(tmp_path) -> None:
    journal = _journal(tmp_path)
    with pytest.raises(JournalError, match="step kind"):
        journal.intend(
            session_id=SESSION, turn_index=0, step_index=0,
            step_kind="sleep", effect_id="x", effectful=True,
            payload={}, at=1.0)
    journal.repo.close()


# ---------------------------------------------------------------------------
# The two commit points, in order.


def test_the_intent_is_readable_before_the_outcome_exists(tmp_path) -> None:
    """The crash-window state, asserted directly.

    This is the row a resume reader actually finds after a `SIGKILL` between
    the two commit points, so it is asserted here rather than inferred from the
    integration battery.
    """
    journal = _journal(tmp_path)
    _intend_model(journal, 0)

    step = journal.step(SESSION, 0, MODEL_STEP_INDEX)
    assert step is not None
    assert step.intent == {"turns_in_context": 0}
    assert step.outcome is None
    assert step.is_complete is False
    assert journal.is_step_complete(SESSION, 0, MODEL_STEP_INDEX) is False
    journal.repo.close()


def test_an_outcome_with_no_intent_is_refused(tmp_path) -> None:
    """The write-ahead half, enforced rather than documented.

    Accepting this would give the journal a second way to record a step — one
    that says nothing about whether the effect preceded it — and the resume
    reader has no way to tell the two apart afterwards.
    """
    journal = _journal(tmp_path)
    with pytest.raises(JournalError, match="no intent"):
        journal.commit_outcome(
            session_id=SESSION, turn_index=0, step_index=MODEL_STEP_INDEX,
            payload={"outcome": "ok"}, at=2.0)
    journal.repo.close()


def test_a_completed_step_carries_both_and_reports_complete(tmp_path) -> None:
    journal = _journal(tmp_path)
    _intend_model(journal, 0)
    journal.commit_outcome(
        session_id=SESSION, turn_index=0, step_index=MODEL_STEP_INDEX,
        payload={"provider": "test", "text": "hi"}, at=2.0)

    step = journal.step(SESSION, 0, MODEL_STEP_INDEX)
    assert step.intent == {"turns_in_context": 0}
    assert step.outcome == {"provider": "test", "text": "hi"}
    assert step.is_complete is True
    assert step.intended_at == 1.0
    assert step.completed_at == 2.0
    journal.repo.close()


def test_the_same_outcome_cannot_be_committed_twice(tmp_path) -> None:
    """FR-007's *no recorded local effect repeats*, at the recording layer.

    Refused by the store's unique index rather than by an attribute on this
    object: the second attempt in the case that matters comes from a **second
    process** after the first was killed, and the two share no memory.
    """
    journal = _journal(tmp_path)
    _intend_model(journal, 0)
    journal.commit_outcome(
        session_id=SESSION, turn_index=0, step_index=MODEL_STEP_INDEX,
        payload={"n": 1}, at=2.0)

    with pytest.raises(JournalError, match="already recorded"):
        journal.commit_outcome(
            session_id=SESSION, turn_index=0, step_index=MODEL_STEP_INDEX,
            payload={"n": 2}, at=3.0)

    assert journal.step(SESSION, 0, MODEL_STEP_INDEX).outcome == {"n": 1}, (
        "the refused second outcome overwrote the first"
    )
    journal.repo.close()


def test_the_same_intent_cannot_be_committed_twice(tmp_path) -> None:
    journal = _journal(tmp_path)
    _intend_model(journal, 0)
    with pytest.raises(JournalError, match="already recorded"):
        _intend_model(journal, 0)
    journal.repo.close()


# ---------------------------------------------------------------------------
# The retry path. `intend_once` exists because the table's middle row does.


def test_re_intending_the_same_step_writes_nothing_and_keeps_the_first_row(
    tmp_path,
) -> None:
    """The resume case, and the one `intend` is right to refuse.

    A crash between a tool call's intent and its outcome leaves the ambiguous
    middle row: the step may have run. A resumed attempt runs it again, and the
    intent it would write is already there. `intend_once` returns the same key
    and leaves the row — including its **original timestamp**, which is the
    assertion that distinguishes "wrote nothing" from "wrote the same thing
    again". A second write would move `intended_at` to the retry's clock and the
    journal would then say the intent was recorded after the effect it preceded.
    """
    journal = _journal(tmp_path)
    first = journal.intend(
        session_id=SESSION, turn_index=0, step_index=tool_step_index(0),
        step_kind=STEP_TOOL_CALL, effect_id="c0", effectful=True,
        payload={"name": "read"}, at=1.0)

    again = journal.intend_once(
        session_id=SESSION, turn_index=0, step_index=tool_step_index(0),
        step_kind=STEP_TOOL_CALL, effect_id="c0", effectful=True,
        payload={"name": "read"}, at=99.0)

    assert again == first
    step = journal.step(SESSION, 0, tool_step_index(0))
    assert step.intended_at == 1.0, (
        f"the intent's timestamp moved to {step.intended_at}, so the retry "
        "rewrote the row rather than recognising it"
    )
    assert step.is_complete is False
    journal.repo.close()


def test_re_intending_a_step_that_was_never_intended_writes_it(tmp_path) -> None:
    """The other reason a call is outstanding on resume: it never started.

    Both reasons arrive at `intend_once` and it cannot tell them apart from the
    caller's arguments, only from the table. This is the branch that writes.
    """
    journal = _journal(tmp_path)
    key = journal.intend_once(
        session_id=SESSION, turn_index=0, step_index=tool_step_index(2),
        step_kind=STEP_TOOL_CALL, effect_id="c2", effectful=True,
        payload={"name": "write"}, at=4.0)

    assert key == idempotency_key(SESSION, 0, tool_step_index(2), "c2")
    step = journal.step(SESSION, 0, tool_step_index(2))
    assert step.intent == {"name": "write"}
    assert step.intended_at == 4.0
    journal.repo.close()


def test_a_different_effect_at_the_same_step_is_refused_even_on_the_retry_path(
    tmp_path,
) -> None:
    """**The tolerance is keyed, and this is what the key buys.**

    `intend_once` tolerating any existing intent would be the dangerous version:
    a resumed attempt whose provider declared a different call at position 2
    would inherit the previous call's intent and then commit *its* outcome
    against it. The journal would hold one step whose intent names one effect and
    whose outcome describes another, and no reader afterwards could tell.

    So the comparison is on the idempotency key, which is derived from the
    effect's own identity. Same key, same step, retry it. Different key, refuse.
    """
    journal = _journal(tmp_path)
    journal.intend(
        session_id=SESSION, turn_index=0, step_index=tool_step_index(2),
        step_kind=STEP_TOOL_CALL, effect_id="c2", effectful=True,
        payload={"name": "read"}, at=1.0)

    with pytest.raises(JournalError, match="different idempotency key"):
        journal.intend_once(
            session_id=SESSION, turn_index=0, step_index=tool_step_index(2),
            step_kind=STEP_TOOL_CALL, effect_id="c-other", effectful=True,
            payload={"name": "read"}, at=2.0)

    step = journal.step(SESSION, 0, tool_step_index(2))
    assert step.idempotency_key == idempotency_key(
        SESSION, 0, tool_step_index(2), "c2"), (
        "the refused call replaced the recorded effect's identity"
    )
    journal.repo.close()


def test_the_retry_path_still_refuses_a_completed_step_a_second_outcome(
    tmp_path,
) -> None:
    """`intend_once` is tolerance about the *intent*, and nothing more.

    A step that already has both rows is finished. Re-intending it is harmless —
    the row is there and matches — but committing a second outcome is the repeat
    FR-007 forbids, and the retry path must not have opened a route to it.
    """
    journal = _journal(tmp_path)
    journal.intend(
        session_id=SESSION, turn_index=0, step_index=tool_step_index(0),
        step_kind=STEP_TOOL_CALL, effect_id="c0", effectful=True,
        payload={"name": "read"}, at=1.0)
    journal.commit_outcome(session_id=SESSION, turn_index=0,
                           step_index=tool_step_index(0),
                           payload={"body": "first"}, at=2.0)

    journal.intend_once(
        session_id=SESSION, turn_index=0, step_index=tool_step_index(0),
        step_kind=STEP_TOOL_CALL, effect_id="c0", effectful=True,
        payload={"name": "read"}, at=3.0)

    with pytest.raises(JournalError, match="already recorded"):
        journal.commit_outcome(session_id=SESSION, turn_index=0,
                               step_index=tool_step_index(0),
                               payload={"body": "second"}, at=4.0)
    assert journal.step(SESSION, 0, tool_step_index(0)).outcome == {"body": "first"}
    journal.repo.close()


def test_a_second_journal_over_the_same_file_sees_the_first_ones_steps(
    tmp_path,
) -> None:
    """The whole point: the answer comes off disk, not out of an object.

    A journal whose state lived on the instance would report a clean slate
    here, and every resume decision downstream would be made against it.
    """
    journal = _journal(tmp_path)
    _intend_model(journal, 0)
    journal.commit_outcome(session_id=SESSION, turn_index=0,
                           step_index=MODEL_STEP_INDEX,
                           payload={"provider": "test"}, at=2.0)
    journal.repo.close()

    reopened = _journal(tmp_path)
    assert reopened.is_step_complete(SESSION, 0, MODEL_STEP_INDEX) is True
    assert reopened.next_turn_index(SESSION) == 1
    reopened.repo.close()


# ---------------------------------------------------------------------------
# Completeness is an enumeration, never a complement.


def test_completeness_refuses_a_kind_it_does_not_know(tmp_path) -> None:
    """`tools/README.md`: never state a classifier as a complement.

    *"Anything but intent means done"* fails open on the first value nobody
    anticipated — and a journal gains kinds over time. So the yes-states are
    enumerated and an unrecognised kind raises. The row is planted through the
    repository rather than through `intend`, because `intend` is exactly what
    would refuse it, and the case under test is a row that reached the table
    some other way: an older writer, a migration, a hand edit.
    """
    journal = _journal(tmp_path)
    _intend_model(journal, 0)
    journal.repo.insert(journal.table, {
        "session_id": SESSION, "turn_index": 0, "step_index": 0,
        "kind": "provisional", "step_kind": STEP_MODEL_CALL,
        "idempotency_key": "k", "effectful": 1, "payload": "{}",
        "provider_state": None, "at": 9.0,
    })
    with pytest.raises(JournalError, match="unrecognised journal kind"):
        journal.steps(SESSION)
    journal.repo.close()


def test_the_two_kinds_are_the_declared_set() -> None:
    assert KIND_INTENT == "intent"
    assert KIND_OUTCOME == "outcome"


# ---------------------------------------------------------------------------
# Turn numbering.


def test_the_next_turn_index_is_zero_on_an_empty_journal(tmp_path) -> None:
    journal = _journal(tmp_path)
    assert journal.next_turn_index(SESSION) == 0
    journal.repo.close()


def test_an_abandoned_turn_never_gets_its_index_reused(tmp_path) -> None:
    """The direction chosen where the two bad options are a gap and a repeat.

    A turn whose model-call intent is journalled and whose outcome is not is a
    turn that *may* have reached the provider. Reusing its index would re-issue
    that call — a duplicate spend against a live account, and the one effect
    nothing downstream can undo. A gap in the reconstructed transcript is
    recoverable by reading the journal; a second charge is not.
    """
    journal = _journal(tmp_path)
    _intend_model(journal, 0)
    journal.commit_outcome(session_id=SESSION, turn_index=0,
                           step_index=MODEL_STEP_INDEX,
                           payload={"provider": "test"}, at=2.0)
    _intend_model(journal, 1, at=3.0)  # killed here

    assert journal.next_turn_index(SESSION) == 2, (
        "turn 1 was intended, so it may have reached the provider; handing its "
        "index back out would re-issue the call"
    )
    journal.repo.close()


def test_turn_numbering_is_per_session(tmp_path) -> None:
    journal = _journal(tmp_path)
    _intend_model(journal, 0)
    assert journal.next_turn_index("another-session") == 0
    journal.repo.close()


# ---------------------------------------------------------------------------
# FR-037: the opaque state does not go through the payload.


def test_opaque_bytes_are_stored_beside_the_payload_and_not_in_it(tmp_path) -> None:
    """FR-037 forbids interpreting the provider state, and JSON is an
    interpretation. It rides in its own column, and comes back byte-identical."""
    journal = _journal(tmp_path)
    _intend_model(journal, 0)
    state = bytes(range(256))
    journal.commit_outcome(
        session_id=SESSION, turn_index=0, step_index=MODEL_STEP_INDEX,
        payload={"provider": "test"}, provider_state=state, at=2.0)

    step = journal.step(SESSION, 0, MODEL_STEP_INDEX)
    assert step.provider_state == state
    assert type(step.provider_state) is bytes
    journal.repo.close()


def test_a_payload_carrying_bytes_is_refused(tmp_path) -> None:
    """The one way the opaque state could reach the payload by accident.

    Refused with a message naming the column it belongs in, because the
    plausible mistake is a caller putting `provider_state` in the dict it
    already has rather than reaching for a second argument.
    """
    journal = _journal(tmp_path)
    with pytest.raises(JournalError, match="provider_state"):
        journal.intend(
            session_id=SESSION, turn_index=0, step_index=MODEL_STEP_INDEX,
            step_kind=STEP_MODEL_CALL, effect_id="model", effectful=True,
            payload={"state": b"\x00\x01"}, at=1.0)
    journal.repo.close()


def test_a_payload_that_is_not_serialisable_is_refused_not_coerced(tmp_path) -> None:
    journal = _journal(tmp_path)
    with pytest.raises(JournalError, match="not serialisable"):
        journal.intend(
            session_id=SESSION, turn_index=0, step_index=MODEL_STEP_INDEX,
            step_kind=STEP_MODEL_CALL, effect_id="model", effectful=True,
            payload={"clock": object()}, at=1.0)
    journal.repo.close()
