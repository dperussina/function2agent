"""T042 — the context assembler and its truncation policy.

Separate from `loop.py` because the policy is the interesting part and it is
worth reading without the loop around it.

**Two properties, and the reason each is a refusal rather than a fit-to-budget.**

1. **The prompt is never trimmed.** A budget too small for the task alone is a
   configuration error. An agent working on a truncated task produces a
   confident answer to a question nobody asked, and nothing downstream can tell
   that answer from a correct one.

2. **What is dropped is the oldest turn.** The newest turn holds the result the
   agent just asked for; dropping from that end produces a loop that cannot see
   its own last action and repeats it, which is the no-progress shape FR-006
   has a terminal state for.

And one that is structural rather than a policy: **the opaque provider state
rides beside the rendered text, never inside it** (FR-037, T-02). Serializing it
into the context would make it inspectable, sortable and mergeable, and FR-037
forbids all three. The type makes the wrong thing hard rather than documenting
that it is wrong.

**And one that changed.** `states_for` returns one entry per kept turn rather
than a single blob. Until 2026-08-05 it returned the most recent non-`None`
state, which dropped every earlier turn's — against FR-037's *never dropped* —
and, worse, re-attached an older turn's state to the latest assistant entry
whenever an intervening turn emitted none. The per-provider evidence is in
`states_for`'s own docstring.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence, TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - import cycle, types only
    from src.runtime.loop import TurnRecord


class ContextError(RuntimeError):
    """A context that cannot be assembled as described."""


class Tokenizer(Protocol):
    """FR-058's basis. `count` is the tokenizer of the model in force.

    Not a bytes-per-token average: FR-058 disqualifies an average by name,
    because an average fails on exactly the content that needs a bound.
    """

    name: str

    def count(self, text: str) -> int: ...


@dataclass(frozen=True)
class Context:
    """What one model call is given."""

    prompt: str
    rendered: str
    #: **One entry per kept turn, in turn order, `None` where that turn emitted
    #: none.** Not one blob: every vendor requires each assistant entry in the
    #: current turn to carry back the state it was issued with, and the
    #: positional alignment with the kept turns is what lets a driver put each
    #: one back where it came from. See `states_for`.
    provider_states: tuple[bytes | None, ...]
    budget_tokens: int
    dropped_turns: int = 0

    def render(self) -> str:
        return self.rendered


@dataclass(frozen=True)
class ContextAssembler:
    budget_tokens: int
    tokenizer: Tokenizer

    def __post_init__(self) -> None:
        if self.budget_tokens <= 0:
            raise ContextError("the context budget is required and positive")

    def assemble(
        self, *, prompt: str, turns: "Sequence[TurnRecord]", provider: str
    ) -> Context:
        head = f"TASK:\n{prompt}\n"
        head_tokens = self.tokenizer.count(head)
        if head_tokens > self.budget_tokens:
            raise ContextError(
                f"the prompt alone is {head_tokens} tokens against a context "
                f"budget of {self.budget_tokens}. Refused rather than trimmed: "
                "an agent given a truncated task answers a question nobody "
                "asked, and does so confidently."
            )

        room = self.budget_tokens - head_tokens
        blocks: list[str] = []
        kept: list["TurnRecord"] = []
        dropped = 0
        for turn in reversed(list(turns)):
            block = render_turn(turn)
            cost = self.tokenizer.count(block)
            if cost > room:
                # Everything at or below this index is dropped. The loop stops
                # rather than skipping and trying an older turn, because a
                # context with a hole in the middle of it reads as a sequence
                # of events that did not happen in that order.
                dropped = turn.turn_index + 1
                break
            blocks.append(block)
            kept.append(turn)
            room -= cost
        blocks.reverse()
        kept.reverse()

        return Context(
            prompt=prompt,
            rendered=head + "".join(blocks),
            # **Over the kept turns, not over all of them.** A state for a turn
            # the context no longer holds has no assistant entry to be put back
            # on, and re-injecting it anywhere else attaches one turn's
            # reasoning to another.
            provider_states=states_for(kept, provider),
            budget_tokens=self.budget_tokens,
            dropped_turns=dropped,
        )


def render_turn(turn: "TurnRecord") -> str:
    """One turn as text. **The opaque state is not rendered.**"""
    lines = [f"[turn {turn.turn_index}] {turn.text}"]
    for result in turn.tool_results:
        lines.append(f"  <{result.call.name}:{result.outcome}> {result.body}")
    return "\n".join(lines) + "\n"


def states_for(
    turns: "Sequence[TurnRecord]", provider: str
) -> tuple[bytes | None, ...]:
    """**Every** turn's state, in turn order, back to the first foreign provider.

    One entry per turn, `None` where that turn emitted none, so the result is
    positionally aligned with the assistant entries a driver will build from the
    same turns. `src/runtime/providers/state.py::reinject` relies on that
    alignment and refuses a request where it does not hold.

    **Why every one and not the latest.** This returned a single blob until
    2026-08-05 — the most recent non-`None` state — and FR-037 says *never
    dropped*. All four vendors want the whole chain and three of them enforce
    it:

    - **OpenAI Responses**: *"Preserve and replay every returned reasoning
      item"* under `store=False`, and the function-calling cookbook is blunter
      — *"The API will error if these are not included."*
    - **Google**: Gemini 3 validates *every step of the current turn* and
      returns 400 when the first `functionCall` part of any step is missing its
      `thought_signature`.
    - **xAI**: *"Always pass the full `output` array back verbatim"*, and *"do
      not parse, edit, or hand-merge multiple blobs."*
    - **Anthropic**: a tool-use loop **is one assistant turn**, and within one
      *"you must pass the thinking blocks from the assistant message back to the
      API, complete and unmodified."* The "older turns are stripped
      server-side" behaviour is about turns before the current one, and on
      Opus 4.5 / Sonnet 4.6 and later it does not apply at all — those models
      keep every prior turn's blocks.

    Only Anthropic degrades quietly on a miss; the other three fail the request.
    Neither is a reason to send less.

    **T-02 is unchanged and is why this stops rather than filters.** Handing
    another provider's state over would hand an opaque blob to something that
    cannot read it, and the failure mode is a silently degraded turn rather
    than an error — so the scan stops at the first foreign provider instead of
    filtering for a match further back.
    """
    kept: list[bytes | None] = []
    for turn in reversed(list(turns)):
        if turn.provider != provider:
            break
        kept.append(turn.provider_state)
    kept.reverse()
    return tuple(kept)


class ByteTokenizer:
    """The fallback when no tokenizer is in force. One byte, one token.

    Conservative for the same reason `conservative_byte_ceiling` is: it cannot
    under-count. Named rather than inlined so that a reader reaching for the kind
    of average divisor FR-058 disqualifies finds this instead.
    """

    name = "bytes-conservative"

    def count(self, text: str) -> int:
        return len(text.encode("utf-8"))
