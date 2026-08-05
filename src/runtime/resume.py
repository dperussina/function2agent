"""T052 — resume reconstruction at turn-and-step granularity (FR-007, SC-011).

**The measurement this exists to avoid.** Finding 006 measured a loop hosted
inside a checkpointed node **re-executing 4 of 4 completed inner turns** on
resume. The checkpoint was per node; the turns were inside it; the resume
replayed the node from its start and therefore replayed all four. Granularity is
the entire fix, and it has to be *two* levels rather than one — restoring only
the turn leaves the steps inside it to be redone, which is the same defect one
level down.

So a plan answers three questions, kept separate because each has a different
wrong answer:

| question                        | wrong answer                        |
| ------------------------------- | ----------------------------------- |
| which turns are finished?       | re-run them — finding 006's 4 of 4  |
| which turn is half-done?        | re-run its completed steps too      |
| which turn index comes next?    | reuse an abandoned turn's index     |

**What a resumed loop is allowed to re-perform, exactly.** A step with a
committed outcome: never. A step with an intent and no outcome: yes, under the
idempotency key its intent recorded — the intent means *maybe it ran*, and the
safe reading of maybe is to run it again with the identity that lets the far side
recognise it. A model call whose outcome is committed: never, because the answer
is on disk; re-calling it would be a second charge for a turn already paid for.

**The gap, which is deliberate and is reported.** A turn whose model-call intent
is journalled with no outcome may have reached the provider. Its index is not
handed back out (`journal.next_turn_index`), so the reconstructed transcript has
a hole where it was. `abandoned` carries those indexes, because a hole a caller
can read is a fact and a hole it cannot is a discrepancy.

**Nothing here writes.** A plan is a pure function of the journal, so building
one twice cannot produce a different session, and a crash while planning leaves
nothing behind to reconcile.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from src.runtime.dispatch import ToolCall, ToolResult
from src.runtime.journal import (
    MODEL_STEP_INDEX,
    JournalStep,
    TurnJournal,
    tool_step_index,
)
from src.runtime.turn import ModelResponse, TurnRecord


class ResumeError(RuntimeError):
    """A journal that cannot be reconstructed as this loop's own history."""


# ---------------------------------------------------------------------------
# The payload schema, defined once and used by both sides.
#
# The loop writes these and this module reads them. Defining the shape in the
# writer and re-deriving it in the reader is two definitions of one format, and
# the failure mode is silent: a renamed key reconstructs a turn with a default
# in it rather than raising.


def encode_model_outcome(response: ModelResponse) -> dict[str, Any]:
    """A model call's outcome, without the opaque state.

    `provider_state` is **absent** rather than present-and-empty, because this
    dict goes through JSON and FR-037 forbids interpreting the state. It travels
    in `turn_journal.provider_state`, which `commit_outcome` takes as its own
    argument.
    """
    return {
        "provider": response.provider,
        "text": response.text,
        "spend_usd": float(response.spend_usd),
        "tokens": int(response.tokens),
        "tool_calls": [
            {
                "index": call.index,
                "call_id": call.call_id,
                "name": call.name,
                "arguments": dict(call.arguments),
            }
            for call in response.tool_calls
        ],
    }


def encode_tool_outcome(
    *,
    outcome: str,
    body: str,
    started_at: float,
    finished_at: float,
    writes: Mapping[str, Any],
) -> dict[str, Any]:
    """One tool call's outcome.

    `outcome` is FR-038's declared name and not a boolean: a branch that faulted
    has to be reconstructed as the failure it was, and a boolean collapses
    `upstream_fault` into the same value as every other non-success.
    """
    return {
        "outcome": outcome,
        "body": body,
        "started_at": float(started_at),
        "finished_at": float(finished_at),
        "writes": dict(writes),
    }


def _decode_model_outcome(step: JournalStep) -> ModelResponse:
    payload = step.outcome
    if payload is None:  # pragma: no cover — callers check `is_complete` first
        raise ResumeError(
            f"turn {step.turn_index}'s model call has no committed outcome")
    try:
        calls = tuple(
            ToolCall(
                index=int(item["index"]),
                call_id=str(item["call_id"]),
                name=str(item["name"]),
                arguments=dict(item.get("arguments") or {}),
            )
            for item in payload["tool_calls"]
        )
        return ModelResponse(
            provider=str(payload["provider"]),
            provider_state=step.provider_state,
            text=str(payload["text"]),
            tool_calls=tuple(sorted(calls, key=lambda c: c.index)),
            spend_usd=float(payload["spend_usd"]),
            tokens=int(payload["tokens"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ResumeError(
            f"turn {step.turn_index}'s journalled model outcome does not carry "
            f"what a response is made of ({exc!r}). It is refused rather than "
            "filled in: a reconstruction with a default in it is a record of "
            "something that did not happen."
        ) from None


def _decode_tool_outcome(step: JournalStep, call: ToolCall) -> ToolResult:
    payload = step.outcome
    if payload is None:  # pragma: no cover — callers check `is_complete` first
        raise ResumeError(
            f"turn {step.turn_index} step {step.step_index} has no outcome")
    try:
        return ToolResult(
            call=call,
            outcome=str(payload["outcome"]),
            body=str(payload["body"]),
            started_at=float(payload["started_at"]),
            finished_at=float(payload["finished_at"]),
            writes=dict(payload.get("writes") or {}),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ResumeError(
            f"turn {step.turn_index} step {step.step_index}'s journalled "
            f"outcome does not carry what a result is made of ({exc!r})"
        ) from None


# ---------------------------------------------------------------------------
# The plan.


@dataclass(frozen=True)
class UnfinishedTurn:
    """The one turn whose model call finished and whose steps did not.

    `response` is reconstructed, so the loop finishes this turn without calling
    the provider again. `completed` are results already on disk and must be
    carried forward untouched. `pending` are the only calls a resumed loop may
    execute.
    """

    turn_index: int
    response: ModelResponse
    completed: tuple[ToolResult, ...]
    pending: tuple[ToolCall, ...]

    def __post_init__(self) -> None:
        if not self.pending:
            raise ResumeError(
                f"turn {self.turn_index} has no pending steps, so it is "
                "finished and belongs in `records`. An UnfinishedTurn with "
                "nothing outstanding would be handed to the loop to complete "
                "and would produce a second record for one turn."
            )
        overlap = ({r.call.call_id for r in self.completed}
                   & {c.call_id for c in self.pending})
        if overlap:
            raise ResumeError(
                f"turn {self.turn_index}: {sorted(overlap)} is both completed "
                "and pending. A call in both sets is the repeat FR-007 forbids, "
                "arriving through the plan rather than through the loop."
            )


@dataclass(frozen=True)
class ResumePlan:
    """What a resumed attempt starts from. Pure; built from the journal alone."""

    session_id: str
    records: tuple[TurnRecord, ...]
    unfinished: UnfinishedTurn | None
    next_turn_index: int
    abandoned: tuple[int, ...]

    @property
    def is_fresh(self) -> bool:
        """True only for a session with nothing journalled at all.

        Stated over the three fields rather than as `next_turn_index == 0`,
        because the second reads as fresh for a journal whose only turn is
        turn 0 half-done — which is the opposite of fresh.
        """
        return (not self.records and self.unfinished is None
                and not self.abandoned)

    @property
    def completed_turn_indexes(self) -> tuple[int, ...]:
        return tuple(record.turn_index for record in self.records)


def plan_resume(journal: TurnJournal, session_id: str) -> ResumePlan:
    """Reconstruct what has already happened, at turn-and-step granularity.

    Reads only. Called at the top of every attempt, including the first, so
    there is no flag anybody can forget to set: on a fresh session the plan is
    empty and the loop proceeds as it would have.
    """
    steps = journal.steps(session_id)
    by_turn: dict[int, dict[int, JournalStep]] = {}
    for step in steps:
        by_turn.setdefault(step.turn_index, {})[step.step_index] = step

    records: list[TurnRecord] = []
    abandoned: list[int] = []
    unfinished: UnfinishedTurn | None = None

    for turn_index in sorted(by_turn):
        turn_steps = by_turn[turn_index]
        model = turn_steps.get(MODEL_STEP_INDEX)
        if model is None:
            raise ResumeError(
                f"turn {turn_index} of {session_id!r} has no model-call step. "
                "Every turn this loop runs journals its model call as step "
                f"{MODEL_STEP_INDEX}, so a turn without one was written by "
                "something else — and reconstructing a response for it would "
                "mean inventing the provider's half of the turn."
            )
        if not model.is_complete:
            # Intent with no outcome: the call may have reached the provider.
            # See the module docstring on why the index is not reused.
            abandoned.append(turn_index)
            continue

        response = _decode_model_outcome(model)
        completed: list[ToolResult] = []
        pending: list[ToolCall] = []
        for call in response.tool_calls:
            step = turn_steps.get(tool_step_index(call.index))
            if step is not None and step.is_complete:
                completed.append(_decode_tool_outcome(step, call))
            else:
                pending.append(call)

        if pending:
            if unfinished is not None:
                raise ResumeError(
                    f"{session_id!r} has more than one turn with outstanding "
                    f"steps ({unfinished.turn_index} and {turn_index}). Turns "
                    "are sequential, so at most one can be half-done. Choosing "
                    "between them would record a guess as a reconstruction."
                )
            unfinished = UnfinishedTurn(
                turn_index=turn_index,
                response=response,
                completed=tuple(sorted(completed, key=lambda r: r.index)),
                pending=tuple(sorted(pending, key=lambda c: c.index)),
            )
            continue

        records.append(TurnRecord(
            turn_index=turn_index,
            provider=response.provider,
            provider_state=response.provider_state,
            tool_calls=response.tool_calls,
            tool_results=tuple(sorted(completed, key=lambda r: r.index)),
            text=response.text,
            # The turn finished when its last step did. Taken from the journal
            # rather than from a clock here, so a reconstructed record carries
            # the time the turn happened and not the time it was read back.
            at=max(
                (step.completed_at for step in turn_steps.values()
                 if step.completed_at is not None),
                default=float(model.intended_at or 0.0),
            ),
        ))

    if unfinished is not None and unfinished.turn_index != max(by_turn):
        raise ResumeError(
            f"{session_id!r}: turn {unfinished.turn_index} has outstanding "
            f"steps but is not the last turn ({max(by_turn)} is). Finishing it "
            "now would append its record after turns that came later, and "
            "§2.2's turn order would no longer be the order they happened in."
        )

    return ResumePlan(
        session_id=session_id,
        records=tuple(records),
        unfinished=unfinished,
        next_turn_index=journal.next_turn_index(session_id),
        abandoned=tuple(abandoned),
    )
