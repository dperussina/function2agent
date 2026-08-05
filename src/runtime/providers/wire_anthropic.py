"""T058 — the Anthropic driver. Thin over `anthropic`, and **not one function**.

Opaque field: `signature` on a `thinking` block, and `data` on a
`redacted_thinking` block. Both are carried; the second is not a lesser case,
because a redacted block is exactly the one an adapter that only knows about
`signature` drops.

**The per-model branch is the reason this file is longer than a rename.**
[Finding 016](../../../specs/001-discovery-validation/findings/016-provider-sdk-roundtrip.md)
result 9 measured `claude-sonnet-5` rejecting
`thinking={"type":"enabled","budget_tokens":N}` with HTTP 400 — *"'thinking.
type.enabled' is not supported for this model. Use 'thinking.type.adaptive' and
'output_config.effort'"* — while `claude-sonnet-4-5-20250929` accepts exactly
that shape. One vendor, two incompatible request bodies, and the split is by
model.

Anthropic **validates the signature server-side**, so a mutated one is a 400
rather than a silent degradation. That makes this the one provider where losing
the round-trip is loud — and it is the reason the conformance fixture cannot
lean on this arm to speak for the other three.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from src.runtime.providers.base import (
    ANTHROPIC,
    ROLE_ASSISTANT,
    ModelCapabilities,
    ParsedTurn,
    ProviderDriver,
    WireTurn,
)
from src.runtime.providers.schema import ToolSchema, calls_from_wire, tools_to_wire
from src.runtime.providers.state import pack, reinject, slot_from_carrier

#: Models that take the **adaptive** thinking shape. Measured on 2026-08-03 for
#: `claude-sonnet-5` (an observed HTTP 400 on the other shape); the other three
#: rows are the same family and are **derived from the vendor's error text**,
#: not from four separate 400s.
ADAPTIVE_MODELS: frozenset[str] = frozenset({
    "claude-sonnet-5",
    "claude-opus-5",
    "claude-opus-4-8",
    "claude-opus-4-7",
})

DEFAULT_THINKING_BUDGET = 1024
DEFAULT_MAX_TOKENS = 2048

#: The two block types that carry opaque reasoning, and the field on each.
_OPAQUE_BLOCKS: Mapping[str, str] = {
    "thinking": "signature",
    "redacted_thinking": "data",
}


class AnthropicDriver(ProviderDriver):
    provider = ANTHROPIC
    sdk_module = "anthropic"

    def capabilities(self, model: str) -> ModelCapabilities:
        adaptive = model in ADAPTIVE_MODELS
        return ModelCapabilities(
            provider=ANTHROPIC,
            model=model,
            opaque_field="thinking.signature",
            thinking_request=(
                {"thinking": {"type": "adaptive"},
                 "output_config": {"effort": "high"}}
                if adaptive else
                {"thinking": {"type": "enabled",
                              "budget_tokens": DEFAULT_THINKING_BUDGET}}
            ),
            # Adaptive thinking declines to think about small tasks, and finding
            # 016 result 8 measured `claude-sonnet-5` emitting opaque state on
            # 2 of 6 runs. The flag stays True — the model *can* — and the
            # conformance fixture asserts the conditional rather than presence.
            emits_opaque_state=True,
            source=(
                "finding 016 result 9, measured 2026-08-03 for claude-sonnet-5 "
                "and claude-sonnet-4-5-20250929; the other adaptive rows are "
                "DERIVED from the vendor's own error text"
            ),
        )

    def build_request(
        self,
        *,
        model: str,
        system: str,
        turns: Sequence[WireTurn],
        tools: Sequence[ToolSchema],
        provider_states: Sequence[bytes | None] = (),
    ) -> dict[str, Any]:
        reinject(ANTHROPIC, turns, provider_states)
        request: dict[str, Any] = {
            "model": model,
            "max_tokens": DEFAULT_MAX_TOKENS,
            "system": system,
            "tools": tools_to_wire(ANTHROPIC, tools),
            "messages": [turn.payload for turn in turns],
        }
        request.update(self.capabilities(model).thinking_request)
        return request

    def parse_response(self, payload: Mapping[str, Any]) -> ParsedTurn:
        blocks = list(payload.get("content") or ())
        # The assistant turn goes back **as it arrived**. Rebuilding it from the
        # blocks this driver recognises is the defect: a block type added by the
        # vendor next month would be dropped, and every assertion on the answer
        # would still pass.
        assistant = WireTurn(role=ROLE_ASSISTANT,
                             payload={"role": "assistant", "content": blocks})

        slots = []
        for position, block in enumerate(blocks):
            field = _OPAQUE_BLOCKS.get(block.get("type"))
            if not field:
                continue
            value = block.get(field)
            if not value:
                continue
            # The path is relative to the assistant entry above, which is what
            # `reinject` writes into on the next turn.
            slots.append(slot_from_carrier(("content", position, field), value))

        usage = payload.get("usage") or {}
        return ParsedTurn(
            provider=ANTHROPIC,
            text="".join(b.get("text") or "" for b in blocks
                         if b.get("type") == "text"),
            tool_calls=calls_from_wire(ANTHROPIC, payload),
            provider_state=pack(ANTHROPIC, slots) if slots else None,
            assistant=assistant,
            input_tokens=int(usage.get("input_tokens") or 0),
            output_tokens=int(usage.get("output_tokens") or 0),
        )
