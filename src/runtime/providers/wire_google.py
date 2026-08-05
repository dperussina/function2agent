"""T058 — the Google driver. Thin over `google-genai`.

Opaque field: `thought_signature` on a `Part`.

**This is the arm where dropping the field looks most harmless**, and
[finding 016](../../../specs/001-discovery-validation/findings/016-provider-sdk-roundtrip.md)
says so in its own arm docstring: Gemini 3 attaches the signature to the
*function-call part* rather than to a separate reasoning block, so an adapter
that rebuilds the part from `name` and `args` — which is the obvious way to
write it — loses the signature while appearing to work perfectly.

**It is also the one provider whose field is genuinely binary.** The
`google-genai` SDK hands back `bytes`, not text. That is why
`src/runtime/providers/state.py` frames with lengths rather than a separator and
why it records a text flag: a NUL inside a payload is realistic here and only
here, and a value re-injected as `str` is not the value the provider sent.

**And it is the provider with no call identity on the wire.** See
`schema.py`'s `GoogleAmbiguousCallError` for what that costs and what is refused
rather than guessed.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from src.runtime.providers.base import (
    GOOGLE,
    ROLE_ASSISTANT,
    ModelCapabilities,
    ParsedTurn,
    ProviderDriver,
    WireTurn,
)
from src.runtime.providers.schema import ToolSchema, calls_from_wire, tools_to_wire
from src.runtime.providers.state import pack, reinject, slot_from_carrier


class GoogleDriver(ProviderDriver):
    provider = GOOGLE
    sdk_module = "google.genai"

    def capabilities(self, model: str) -> ModelCapabilities:
        return ModelCapabilities(
            provider=GOOGLE,
            model=model,
            opaque_field="Part.thought_signature",
            # Gemini 3 returns thought signatures without a thinking parameter;
            # what it does need is automatic function calling **off**, or the
            # SDK runs the tools itself and the loop never sees a call.
            thinking_request={},
            opt_in={"automatic_function_calling": {"disable": True}},
            emits_opaque_state=True,
            source=(
                "finding 016, measured 2026-08-03 on gemini-3-flash-preview "
                "with automatic function calling disabled"
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
        reinject(GOOGLE, turns, provider_states)
        capabilities = self.capabilities(model)
        return {
            "model": model,
            "contents": [turn.payload for turn in turns],
            "config": {
                "system_instruction": system,
                "tools": tools_to_wire(GOOGLE, tools),
                **capabilities.opt_in,
            },
        }

    def parse_response(self, payload: Mapping[str, Any]) -> ParsedTurn:
        candidates = payload.get("candidates") or ()
        content = (candidates[0].get("content") or {}) if candidates else {}
        parts = list(content.get("parts") or ())
        assistant = WireTurn(
            role=ROLE_ASSISTANT,
            payload={"role": content.get("role") or "model", "parts": parts},
        )

        slots = []
        for position, part in enumerate(parts):
            value = part.get("thought_signature")
            if not value:
                continue
            slots.append(
                slot_from_carrier(("parts", position, "thought_signature"),
                                  value))

        usage = payload.get("usage_metadata") or {}
        return ParsedTurn(
            provider=GOOGLE,
            text="".join(p.get("text") or "" for p in parts if p.get("text")),
            tool_calls=calls_from_wire(GOOGLE, payload),
            provider_state=pack(GOOGLE, slots) if slots else None,
            assistant=assistant,
            input_tokens=int(usage.get("prompt_token_count") or 0),
            output_tokens=(int(usage.get("candidates_token_count") or 0)
                           + int(usage.get("thoughts_token_count") or 0)),
        )
