"""T042 — the context assembler and its truncation policy.

**Two of these arms assert a refusal rather than a fit.** A context assembler
that trims the prompt to fit, or that drops the newest turn, passes every
assertion about size and produces an agent working on a question nobody asked or
one that cannot see its own last action. Both are silent, so both are asserted
here as refusals with the reason named.

The last two arms are on the opaque state: it must not be rendered into the text
(FR-037, T-02), and it must not cross a provider boundary.
"""

from __future__ import annotations

import pytest

from src.runtime.context import ContextAssembler, ContextError
from src.runtime.loop import TurnRecord


class Tok:
    """A tokenizer, not an average. FR-058 disqualifies an average by name."""

    name = "test-tok"

    def count(self, text: str) -> int:
        return max(1, len(text) // 4)


def test_the_assembled_context_is_bounded_in_tokens() -> None:
    assembler = ContextAssembler(budget_tokens=100, tokenizer=Tok())
    turns = tuple(
        TurnRecord(turn_index=i, provider="p", provider_state=b"s",
                   tool_calls=(), tool_results=(), text="x" * 400, at=float(i))
        for i in range(50)
    )
    context = assembler.assemble(prompt="the task", turns=turns, provider="p")

    assert Tok().count(context.render()) <= 100, (
        f"{Tok().count(context.render())} tokens against a budget of 100"
    )


def test_the_context_keeps_the_prompt_and_the_most_recent_turns() -> None:
    """What is dropped is the oldest, and the task is never dropped.

    A context assembler that drops the prompt to fit produces an agent working
    on nothing, and one that drops the newest turn produces an agent that
    cannot see the result it just asked for.
    """
    assembler = ContextAssembler(budget_tokens=120, tokenizer=Tok())
    turns = tuple(
        TurnRecord(turn_index=i, provider="p", provider_state=b"s",
                   tool_calls=(), tool_results=(), text=f"turn-{i} " + "y" * 100,
                   at=float(i))
        for i in range(20)
    )
    rendered = assembler.assemble(
        prompt="THE-TASK", turns=turns, provider="p").render()

    assert "THE-TASK" in rendered
    assert "turn-19" in rendered
    assert "turn-0 " not in rendered


def test_a_prompt_that_alone_exceeds_the_budget_is_refused_not_trimmed() -> None:
    """Silently trimming the task is worse than refusing to start."""
    assembler = ContextAssembler(budget_tokens=10, tokenizer=Tok())
    with pytest.raises(ContextError, match="prompt"):
        assembler.assemble(prompt="z" * 10_000, turns=(), provider="p")


def test_the_context_carries_only_the_current_providers_state() -> None:
    assembler = ContextAssembler(budget_tokens=1_000, tokenizer=Tok())
    turns = (
        TurnRecord(turn_index=0, provider="one", provider_state=b"a",
                   tool_calls=(), tool_results=(), text="t", at=0.0),
        TurnRecord(turn_index=1, provider="two", provider_state=b"b",
                   tool_calls=(), tool_results=(), text="t", at=1.0),
    )
    assert assembler.assemble(
        prompt="p", turns=turns, provider="two").provider_state == b"b"
    assert assembler.assemble(
        prompt="p", turns=turns, provider="three").provider_state is None


def test_the_rendered_context_never_contains_the_opaque_state() -> None:
    """It is round-tripped beside the context, not serialized into it."""
    assembler = ContextAssembler(budget_tokens=1_000, tokenizer=Tok())
    turns = (
        TurnRecord(turn_index=0, provider="one", provider_state=b"MARKER-9c1",
                   tool_calls=(), tool_results=(), text="t", at=0.0),
    )
    rendered = assembler.assemble(prompt="p", turns=turns, provider="one").render()
    assert "MARKER-9c1" not in rendered
