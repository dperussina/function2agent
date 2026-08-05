"""T058 — the OpenAI driver, on the **Responses** API. Thin over `openai`.

Opaque field: `encrypted_content` on a `reasoning` output item.

**Why Responses and not Chat Completions, and why `store=False`.** The field is
returned only when the caller both asks for it —
`include=["reasoning.encrypted_content"]` — and declines server-side state,
`store=False`. That combination is the one where the provider keeps nothing and
the round-trip is *ours* to get right. With `store=True` an adapter that drops
the field is invisible, because the provider still has it. A self-hosted product
wants `store=False` anyway;
[finding 016](../../../specs/001-discovery-validation/findings/016-provider-sdk-roundtrip.md)
drove that configuration and its arm is where these shapes come from.

**The assistant turn is a list, not a message.** Responses splices output items
straight into the next request's flat `input` array. Modelling it as a message
would mean unwrapping it on the way out, at the one place an unwrap can quietly
drop the reasoning items that are not function calls — which is the whole
failure.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from src.runtime.providers.base import (
    OPENAI,
    ROLE_ASSISTANT,
    ModelCapabilities,
    ParsedTurn,
    ProviderDriver,
    WireTurn,
)
from src.runtime.providers.schema import ToolSchema, calls_from_wire, tools_to_wire
from src.runtime.providers.state import pack, reinject, slot_from_carrier

#: Reasoning effort per model family. `gpt-5-mini` is the model finding 016
#: drove at `low`; everything else is DERIVED and says so in `source`.
_LOW_EFFORT_MODELS: frozenset[str] = frozenset({"gpt-5-mini", "gpt-5-nano"})


class OpenAIDriver(ProviderDriver):
    provider = OPENAI
    sdk_module = "openai"

    def capabilities(self, model: str) -> ModelCapabilities:
        return ModelCapabilities(
            provider=OPENAI,
            model=model,
            opaque_field="reasoning.encrypted_content",
            thinking_request={
                "reasoning": {
                    "effort": "low" if model in _LOW_EFFORT_MODELS else "medium"
                }
            },
            # **Not decoration.** Without both of these the provider returns no
            # opaque state at all and no error to say so, and every conformance
            # arm would report an absent field as a property of the model.
            opt_in={"store": False,
                    "include": ["reasoning.encrypted_content"]},
            emits_opaque_state=True,
            source=(
                "finding 016, measured 2026-08-03 on gpt-5-mini with "
                "store=False and include=[reasoning.encrypted_content]; the "
                "effort row for other models is DERIVED"
            ),
        )

    def build_request(
        self,
        *,
        model: str,
        system: str,
        turns: Sequence[WireTurn],
        tools: Sequence[ToolSchema],
        provider_state: bytes | None = None,
    ) -> dict[str, Any]:
        reinject(OPENAI, turns, provider_state)
        conversation: list[Any] = []
        for turn in turns:
            # A list payload is spliced, not nested. See the module docstring.
            if isinstance(turn.payload, list):
                conversation.extend(turn.payload)
            else:
                conversation.append(turn.payload)
        capabilities = self.capabilities(model)
        request: dict[str, Any] = {
            "model": model,
            "instructions": system,
            "input": conversation,
            "tools": tools_to_wire(OPENAI, tools),
        }
        request.update(capabilities.thinking_request)
        request.update(capabilities.opt_in)
        return request

    def parse_response(self, payload: Mapping[str, Any]) -> ParsedTurn:
        items = list(payload.get("output") or ())
        assistant = WireTurn(role=ROLE_ASSISTANT, payload=items)

        slots = []
        for position, item in enumerate(items):
            if item.get("type") != "reasoning":
                continue
            value = item.get("encrypted_content")
            if not value:
                continue
            slots.append(
                slot_from_carrier((position, "encrypted_content"), value))

        usage = payload.get("usage") or {}
        return ParsedTurn(
            provider=OPENAI,
            text="".join(
                part.get("text") or ""
                for item in items if item.get("type") == "message"
                for part in (item.get("content") or ())
                if part.get("type") == "output_text"
            ),
            tool_calls=calls_from_wire(OPENAI, payload),
            provider_state=pack(OPENAI, slots) if slots else None,
            assistant=assistant,
            input_tokens=int(usage.get("input_tokens") or 0),
            output_tokens=int(usage.get("output_tokens") or 0),
        )
