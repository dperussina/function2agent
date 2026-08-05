"""T058 — the xAI driver. Thin over `xai-sdk`.

Opaque field: `encrypted_content` on an assistant message, returned only when
the chat is created with `use_encrypted_content=True`.

**This is the arm the whole capability exists for.** Finding 003 result 7
counted ADK's LiteLLM adapter referencing `encrypted_content` **zero times under
every counting rule**, against 35, 16 and 9 for the other three providers'
fields — and chained tool use still worked, so the gap did not announce itself.
[Finding 016](../../../specs/001-discovery-validation/findings/016-provider-sdk-roundtrip.md)
then measured the negative control directly: with the field stripped entirely,
the chain still ran and still answered correctly. **OD-16** replaced that
adapter with this driver, and nothing but a byte-identity assertion can tell the
replacement from the thing it replaced.

**Shape note, stated rather than implied.** `xai-sdk` is protobuf underneath;
`chat.append(response)` is the SDK's own round-trip and the wire is not JSON.
The mappings this driver reads and writes are the OpenAI-chat-compatible shape
the service also speaks, which is what makes a JSON cassette possible at all.
`tests/conformance/cassettes/README.md` records that this is a **shape
equivalence, not a recording of the proto path**.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from src.runtime.providers.base import (
    ROLE_ASSISTANT,
    XAI,
    ModelCapabilities,
    ParsedTurn,
    ProviderDriver,
    WireTurn,
)
from src.runtime.providers.schema import ToolSchema, calls_from_wire, tools_to_wire
from src.runtime.providers.state import pack, reinject, slot_from_carrier


class XaiDriver(ProviderDriver):
    provider = XAI
    sdk_module = "xai_sdk"

    def capabilities(self, model: str) -> ModelCapabilities:
        return ModelCapabilities(
            provider=XAI,
            model=model,
            opaque_field="message.encrypted_content",
            thinking_request={},
            # Without this the field is never returned, and an arm reporting an
            # absent field would be reporting our own omission as a property of
            # the model.
            opt_in={"use_encrypted_content": True},
            emits_opaque_state=True,
            source="finding 016, measured 2026-08-03 on grok-4.5",
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
        reinject(XAI, turns, provider_state)
        messages: list[Any] = [{"role": "system", "content": system}]
        messages.extend(turn.payload for turn in turns)
        capabilities = self.capabilities(model)
        return {
            "model": model,
            "messages": messages,
            "tools": tools_to_wire(XAI, tools),
            **capabilities.opt_in,
        }

    def parse_response(self, payload: Mapping[str, Any]) -> ParsedTurn:
        choices = payload.get("choices") or ()
        message = dict(choices[0].get("message") or {}) if choices else {}
        assistant = WireTurn(role=ROLE_ASSISTANT, payload=message)

        slots = []
        value = message.get("encrypted_content")
        if value:
            slots.append(slot_from_carrier(("encrypted_content",), value))

        usage = payload.get("usage") or {}
        return ParsedTurn(
            provider=XAI,
            text=message.get("content") or "",
            tool_calls=calls_from_wire(XAI, payload),
            provider_state=pack(XAI, slots) if slots else None,
            assistant=assistant,
            input_tokens=int(usage.get("prompt_tokens") or 0),
            output_tokens=(int(usage.get("completion_tokens") or 0)
                           + int(usage.get("reasoning_tokens") or 0)),
            # **Deliberately not populated from `cost_in_usd_ticks`.** xAI is
            # the one provider that reports a server-side cost, and finding 016
            # read it off the SDK's already-converted `cost_usd` attribute
            # rather than off the raw proto — so the tick scale has never been
            # observed in our hands. A divisor written here would be an
            # unsourced number in the one field T063 fails closed on, and a
            # wrong one would make the spend ceiling wrong rather than absent.
            # The converted attribute belongs to the transport half; T062's
            # cost table is where the conversion is owed a source.
            cost_usd=None,
        )
