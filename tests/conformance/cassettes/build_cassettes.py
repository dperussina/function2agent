"""Authors the committed cassettes. **Run deliberately; the output is the fixture.**

FR-053 wants fixtures committed rather than generated at test time, and they
are: `*.json` beside this file are what the conformance fixture reads. This
script is how they were written, kept so that the four wire shapes sit in one
auditable place instead of being duplicated across four hand-typed JSON files
where a typo reads as a provider quirk.

## What is transcribed and what is invented

**Transcribed**, from the four arms of
`specs/001-discovery-validation/harness/provider-sdk-roundtrip/`, which drove
the real APIs on 2026-08-03:

- the tool-declaration shape per provider,
- where each provider puts its tool call, its arguments, and its opaque field,
- that OpenAI needs `store=False` plus `include=[...]` and xAI needs
  `use_encrypted_content=True`,
- that Google's signature rides on the function-call `Part`.

**Invented**: the opaque payload bytes, the ids, the token counts, and the
five-hop scenario. Finding 016 committed digests and verdicts, not transcripts,
so there is no recorded response in this repository to copy. `provenance.kind`
on every file records that, and `harness.require_recorded()` is what stops the
distinction being forgotten.

## The digest pin

`expected_state_digest` is computed here with `src/runtime/providers/state.py`'s
own packer and then **frozen into the file**. That is a pin, not a computation
the fixture repeats: a change to the framing makes every cassette stop matching
and forces a deliberate re-pin, which is the coupling that keeps the carrier
format from drifting silently.

Regenerate with:

    .venv/bin/python tests/conformance/cassettes/build_cassettes.py
"""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from src.runtime.providers.base import (  # noqa: E402
    ANTHROPIC, GOOGLE, OPENAI, XAI,
)
from src.runtime.providers.state import pack, slot_from_carrier  # noqa: E402
from src.runtime.turn import state_digest  # noqa: E402
from tests.conformance.cassettes.harness import (  # noqa: E402
    CASSETTE_VERSION, KIND_DERIVED, OPAQUE_MARKER,
)

HERE = Path(__file__).resolve().parent

# ---------------------------------------------------------------------------
# The scenario. Five dependent hops, six turns.
#
# T061 asks for a **long** chained sequence and the reason is measured: finding
# 016 ran two hops, stripped the opaque field entirely, and the chain still
# answered correctly. Two hops cannot characterise opaque-state loss. Five
# cannot either — the depth at which it bites is unmeasured and this file does
# not claim to know it — but each hop is a turn on which the field has to
# survive, so the chain is what makes the *carrier* work non-trivial rather than
# what makes the loss observable in the answer.
#
# Every hop's argument is the previous hop's return value, and no value is
# derivable from the prompt. The tools in the fixture reject an id they did not
# issue, so a chain that skipped a hop fails loudly.

CHAIN = [
    ("lookup_customer", {"customer_name": "Dana Whitfield"}),
    ("list_orders", {"customer_id": "CUS-4417"}),
    ("get_order_lines", {"order_id": "ORD-7731"}),
    ("get_line_price", {"line_id": "LN-22"}),
    ("apply_tax", {"subtotal_usd": 139.99}),
]
FINAL_TEXT = "The order total for Dana Whitfield is 149.99"
TURNS = len(CHAIN) + 1


def _synthetic_text(provider: str, turn: int) -> str:
    """A text-carrier opaque payload. Shaped like the real thing, not one."""
    stem = f"{provider}-turn{turn}-opaque-".encode()
    return base64.b64encode(stem + bytes(range(0x21, 0x21 + 40))).decode()


def _synthetic_binary(turn: int) -> bytes:
    """Google's carrier is genuinely `bytes`, so this one is hostile on purpose.

    A NUL and a UTF-8 continuation byte with no lead byte in front of it. Any
    carrier that joined values on a separator loses the first; any path that
    decoded the payload raises or substitutes U+FFFD on the second. A payload
    made of base64 would survive both and the fixture would pass while the
    framing was wrong — which is the same trap
    `tests/conformance/test_provider_state_resume.py` planted for the journal.
    """
    return (b"\x00\x80\xfe" + f"google-turn{turn}".encode()
            + bytes(range(0x00, 0x20)) + b"\xff\x00\xfe")


# ---------------------------------------------------------------------------
# Per-provider response shapes.


def _anthropic(turn: int, with_state: bool) -> tuple[dict, list[dict]]:
    content: list[dict] = []
    opaque: list[dict] = []
    if with_state:
        content.append({"type": "thinking",
                        "thinking": f"working on hop {turn}",
                        "signature": {OPAQUE_MARKER: 0}})
        opaque.append({"path": ["content", 0, "signature"], "carrier": "text",
                       "value": _synthetic_text(ANTHROPIC, turn)})
    if turn < len(CHAIN):
        name, args = CHAIN[turn]
        content.append({"type": "tool_use", "id": f"toolu_{turn:02d}",
                        "name": name, "input": args})
    else:
        content.append({"type": "text", "text": FINAL_TEXT})
    return ({"id": f"msg_{turn:02d}", "type": "message", "role": "assistant",
             "content": content,
             "usage": {"input_tokens": 400 + turn * 90,
                       "output_tokens": 60 + turn * 5}},
            opaque)


def _openai(turn: int, with_state: bool) -> tuple[dict, list[dict]]:
    output: list[dict] = []
    opaque: list[dict] = []
    if with_state:
        output.append({"type": "reasoning", "id": f"rs_{turn:02d}",
                       "summary": [],
                       "encrypted_content": {OPAQUE_MARKER: 0}})
        opaque.append({"path": [0, "encrypted_content"], "carrier": "text",
                       "value": _synthetic_text(OPENAI, turn)})
    if turn < len(CHAIN):
        name, args = CHAIN[turn]
        output.append({"type": "function_call", "id": f"fc_{turn:02d}",
                       "call_id": f"call_{turn:02d}", "name": name,
                       # The asymmetry: a JSON **string**, not a mapping.
                       "arguments": json.dumps(args)})
    else:
        output.append({"type": "message", "role": "assistant",
                       "content": [{"type": "output_text",
                                    "text": FINAL_TEXT}]})
    return ({"id": f"resp_{turn:02d}", "object": "response", "output": output,
             "usage": {"input_tokens": 380 + turn * 85,
                       "output_tokens": 55 + turn * 4}},
            opaque)


def _google(turn: int, with_state: bool) -> tuple[dict, list[dict]]:
    part: dict
    if turn < len(CHAIN):
        name, args = CHAIN[turn]
        part = {"function_call": {"name": name, "args": args}}
    else:
        part = {"text": FINAL_TEXT}
    opaque: list[dict] = []
    if with_state:
        # The signature rides on the part itself. An adapter that rebuilt the
        # part from name and args alone loses it and still works.
        part["thought_signature"] = {OPAQUE_MARKER: 0}
        opaque.append({"path": ["parts", 0, "thought_signature"],
                       "carrier": "binary",
                       "value": _synthetic_binary(turn)})
    return ({"candidates": [{"content": {"role": "model", "parts": [part]}}],
             "usage_metadata": {"prompt_token_count": 350 + turn * 80,
                                "candidates_token_count": 40 + turn * 3,
                                "thoughts_token_count": 120}},
            opaque)


def _xai(turn: int, with_state: bool) -> tuple[dict, list[dict]]:
    message: dict = {"role": "assistant", "content": ""}
    opaque: list[dict] = []
    if with_state:
        message["encrypted_content"] = {OPAQUE_MARKER: 0}
        opaque.append({"path": ["encrypted_content"], "carrier": "text",
                       "value": _synthetic_text(XAI, turn)})
    if turn < len(CHAIN):
        name, args = CHAIN[turn]
        message["tool_calls"] = [{"id": f"call_{turn:02d}", "type": "function",
                                  "function": {"name": name,
                                               "arguments": json.dumps(args)}}]
        finish = "tool_calls"
    else:
        message["content"] = FINAL_TEXT
        finish = "stop"
    return ({"id": f"cmpl_{turn:02d}",
             "choices": [{"index": 0, "finish_reason": finish,
                          "message": message}],
             "usage": {"prompt_tokens": 300 + turn * 70,
                       "completion_tokens": 35 + turn * 3,
                       "reasoning_tokens": 90}},
            opaque)


BUILDERS = {ANTHROPIC: _anthropic, OPENAI: _openai,
            GOOGLE: _google, XAI: _xai}

#: Where each provider's opaque field lands in a **request**. Walked by the
#: fixture's own reader, not by the driver's injector.
SELECTORS = {
    ANTHROPIC: [["messages", "*", "content", "*", "signature"]],
    OPENAI: [["input", "*", "encrypted_content"]],
    GOOGLE: [["contents", "*", "parts", "*", "thought_signature"]],
    XAI: [["messages", "*", "encrypted_content"]],
}

SDKS = {
    ANTHROPIC: ("anthropic", "0.120.2"),
    OPENAI: ("openai", "2.52.1"),
    GOOGLE: ("google-genai", "2.16.0"),
    XAI: ("xai-sdk", "1.17.0"),
}

ARM_SOURCE = {
    ANTHROPIC: "arm_anthropic.py",
    OPENAI: "arm_openai.py",
    GOOGLE: "arm_google.py",
    XAI: "arm_xai.py",
}


def build(provider: str, model: str, present: set[int], note: str) -> dict:
    interactions = []
    for turn in range(TURNS):
        response, declared = BUILDERS[provider](turn, turn in present)
        slots = []
        opaque_json = []
        for value in declared:
            raw = value["value"]
            raw_bytes = raw.encode("utf-8") if isinstance(raw, str) else raw
            slots.append(slot_from_carrier(tuple(value["path"]), raw))
            opaque_json.append({"path": value["path"],
                                "carrier": value["carrier"],
                                "b64": base64.b64encode(raw_bytes).decode()})
        digest = state_digest(pack(provider, slots)) if slots else None
        interactions.append({
            "turn": turn,
            # One user entry, then two per completed hop: the assistant turn
            # and the tool-result entry that answers it.
            "request_turns": 1 + 2 * turn,
            "opaque": opaque_json,
            "expected_state_digest": digest,
            "response": response,
        })
    sdk, version = SDKS[provider]
    return {
        "cassette_version": CASSETTE_VERSION,
        "provider": provider,
        "model": model,
        "sdk": sdk,
        "sdk_version": version,
        "provenance": {
            "kind": KIND_DERIVED,
            "shape_source": (
                "specs/001-discovery-validation/harness/"
                f"provider-sdk-roundtrip/{ARM_SOURCE[provider]}"),
            "shape_observed": "2026-08-03, finding 016, against the live API",
            "payload_source": "synthetic",
            "why": (
                "Finding 016 committed digests and verdicts, not transcripts. "
                "There is no recorded provider response in this repository to "
                "build a cassette from, and recording one costs money to "
                "re-measure something finding 016 already measured."),
            "note": note,
        },
        "opaque_selectors": SELECTORS[provider],
        "interactions": interactions,
    }


ALL = range(TURNS)

#: The six committed cassettes. Four are the providers; two exist to hold the
#: **assertion shape** T061 specifies rather than to describe a provider.
PLAN = [
    ("anthropic.json", ANTHROPIC, "claude-sonnet-4-5-20250929", set(ALL),
     "Every turn carries a signature, which is what finding 016's arm measured "
     "on this model."),
    ("openai.json", OPENAI, "gpt-5-mini", set(ALL),
     "store=False with include=[reasoning.encrypted_content], the "
     "configuration where the provider keeps nothing and the round-trip is "
     "ours."),
    ("google.json", GOOGLE, "gemini-3-flash-preview", set(ALL),
     "The one binary carrier. Payloads contain a NUL and a bare UTF-8 "
     "continuation byte on purpose."),
    ("xai.json", XAI, "grok-4.5", set(ALL),
     "The field ADK's LiteLLM adapter referenced zero times."),
    ("anthropic-adaptive-sparse.json", ANTHROPIC, "claude-sonnet-5", {1, 4},
     "Finding 016 result 8: claude-sonnet-5 under adaptive thinking emitted "
     "opaque state on 2 of 6 runs in the committed batch. This cassette is "
     "that ratio, and it is what makes the fixture's assertion a conditional "
     "rather than a presence check."),
    ("anthropic-adaptive-silent.json", ANTHROPIC, "claude-sonnet-5", set(),
     "Zero of six. **Used only by the vacuity guard**, which asserts that the "
     "round-trip check REFUSES this cassette rather than passing over it. A "
     "conditional assertion is vacuously true when the field is always absent, "
     "and a fixture that reported success here would be reporting success "
     "over having tested nothing."),
]


def main() -> int:
    for filename, provider, model, present, note in PLAN:
        document = build(provider, model, present, note)
        (HERE / filename).write_text(
            json.dumps(document, indent=2, sort_keys=False) + "\n")
        carried = sum(1 for i in document["interactions"] if i["opaque"])
        print(f"{filename}: {carried}/{TURNS} turns carry opaque state")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
