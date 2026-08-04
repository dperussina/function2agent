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
    provider_state: bytes | None
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
        kept: list[str] = []
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
            kept.append(block)
            room -= cost

        return Context(
            prompt=prompt,
            rendered=head + "".join(reversed(kept)),
            provider_state=state_for(turns, provider),
            budget_tokens=self.budget_tokens,
            dropped_turns=dropped,
        )


def render_turn(turn: "TurnRecord") -> str:
    """One turn as text. **The opaque state is not rendered.**"""
    lines = [f"[turn {turn.turn_index}] {turn.text}"]
    for result in turn.tool_results:
        lines.append(f"  <{result.call.name}:{result.outcome}> {result.body}")
    return "\n".join(lines) + "\n"


def state_for(turns: "Sequence[TurnRecord]", provider: str) -> bytes | None:
    """The most recent state, and only if the same provider produced it.

    T-02: never merged across providers. Handing another provider's state over
    would hand an opaque blob to something that cannot read it, and the failure
    mode is a silently degraded turn rather than an error — which is why this
    scans backwards and stops at the first foreign provider instead of
    filtering for a match further back.
    """
    for turn in reversed(list(turns)):
        if turn.provider != provider:
            return None
        if turn.provider_state is not None:
            return turn.provider_state
    return None


class ByteTokenizer:
    """The fallback when no tokenizer is in force. One byte, one token.

    Conservative for the same reason `conservative_byte_ceiling` is: it cannot
    under-count. Named rather than inlined so that a reader looking for the
    `4.0` divisor FR-058 disqualifies finds this instead.
    """

    name = "bytes-conservative"

    def count(self, text: str) -> int:
        return len(text.encode("utf-8"))
