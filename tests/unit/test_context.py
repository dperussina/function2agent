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
    # The scan stops at the foreign provider rather than filtering past it, so
    # `one`'s state is not in the chain handed to `two` (T-02).
    assert assembler.assemble(
        prompt="p", turns=turns, provider="two").provider_states == (b"b",)
    assert assembler.assemble(
        prompt="p", turns=turns, provider="three").provider_states == ()


def test_every_turns_state_is_carried_and_not_only_the_latest() -> None:
    """FR-037's *never dropped*, on the clause that was not held.

    `states_for` returned one blob until 2026-08-05. All four vendors want the
    whole chain within the current turn and three of them reject a request
    missing one of them: OpenAI *"preserve and replay every returned reasoning
    item"*, Google 400s on any step of the current turn whose first
    `functionCall` part has lost its signature, xAI *"always pass the full
    output array back verbatim"*. Anthropic is the one that degrades silently,
    which is worse rather than better.
    """
    assembler = ContextAssembler(budget_tokens=1_000, tokenizer=Tok())
    turns = tuple(
        TurnRecord(turn_index=i, provider="one",
                   provider_state=f"s{i}".encode(),
                   tool_calls=(), tool_results=(), text="t", at=float(i))
        for i in range(4)
    )
    assert assembler.assemble(
        prompt="p", turns=turns, provider="one").provider_states == (
            b"s0", b"s1", b"s2", b"s3")


def test_a_turn_that_emitted_no_state_holds_its_place_in_the_chain() -> None:
    """The defect that made the drop worse than a drop.

    The old scan skipped a `None` turn and returned an *older* turn's state,
    which the caller then re-attached to the newest assistant entry. On
    Anthropic that put a `signature` key on a `tool_use` block — a value the
    provider signed for a different message. The chain keeps `None` in place so
    the positional alignment with the assistant entries survives, and
    `reinject` refuses when it does not.
    """
    assembler = ContextAssembler(budget_tokens=1_000, tokenizer=Tok())
    turns = (
        TurnRecord(turn_index=0, provider="one", provider_state=b"a",
                   tool_calls=(), tool_results=(), text="t", at=0.0),
        TurnRecord(turn_index=1, provider="one", provider_state=None,
                   tool_calls=(), tool_results=(), text="t", at=1.0),
        TurnRecord(turn_index=2, provider="one", provider_state=b"c",
                   tool_calls=(), tool_results=(), text="t", at=2.0),
    )
    assert assembler.assemble(
        prompt="p", turns=turns, provider="one").provider_states == (
            b"a", None, b"c")


def test_the_state_of_a_dropped_turn_is_dropped_with_it() -> None:
    """One entry per *kept* turn, or the alignment is a lie.

    A state whose turn was truncated out of the context has no assistant entry
    left to be put back on. Carrying it anyway would shift every later state
    one position and attach each one to the wrong message.
    """
    assembler = ContextAssembler(budget_tokens=60, tokenizer=Tok())
    turns = tuple(
        TurnRecord(turn_index=i, provider="one",
                   provider_state=f"s{i}".encode(),
                   tool_calls=(), tool_results=(), text="y" * 100,
                   at=float(i))
        for i in range(10)
    )
    context = assembler.assemble(prompt="p", turns=turns, provider="one")

    assert context.dropped_turns > 0, (
        "the budget was not small enough to force a drop, so this arm is "
        "asserting nothing about truncation")
    assert len(context.provider_states) == len(turns) - context.dropped_turns
    assert context.provider_states[-1] == b"s9"


def test_the_rendered_context_never_contains_the_opaque_state() -> None:
    """It is round-tripped beside the context, not serialized into it."""
    assembler = ContextAssembler(budget_tokens=1_000, tokenizer=Tok())
    turns = (
        TurnRecord(turn_index=0, provider="one", provider_state=b"MARKER-9c1",
                   tool_calls=(), tool_results=(), text="t", at=0.0),
    )
    rendered = assembler.assemble(prompt="p", turns=turns, provider="one").render()
    assert "MARKER-9c1" not in rendered
