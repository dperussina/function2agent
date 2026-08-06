"""SPIKE - E18 arm 1/4 — Anthropic. **This is the negative control.**

Opaque field: `signature` on a `thinking` block, and `data` on a
`redacted_thinking` block. The second is not a lesser case — a redacted block is
exactly the one an adapter that only knows about `signature` drops.

**Why this arm is the control and not a fourth repetition.** Rule 8 of the
[`experiment-design`](../../../../.cursor/skills/experiment-design/SKILL.md)
skill — *"an experiment whose positive result is a failure signal needs a
negative control"* — governs conditions B and C, because for three of the four
providers the predicted result is an error and **every way the instrument can
break produces that same reading**. Anthropic is predicted to behave in the
opposite direction: to *not* error where the other three do.
[`src/runtime/context.py`](../../../../src/runtime/context.py)`::states_for`
records the vendor's position as degrade-quietly rather than reject.

**One thing this arm cannot do, stated so nobody reads it as more than it is.**
It can measure Anthropic *not erroring*. It cannot measure Anthropic *degrading
quietly*, which is a different claim and is not entailed by the first.
Separating them needs a task whose answer depends on the withheld reasoning, and
[finding 016](../../../001-discovery-validation/findings/016-provider-sdk-roundtrip.md)
already recorded that a scenario of this size is *"too small to supply one."* A
green Anthropic cell is not evidence about quiet degradation in either direction.

**Model.** `claude-sonnet-4-5-20250929`, the model finding 016 measured emitting
a signed thinking block for a task of this size. `claude-sonnet-5` under
adaptive thinking emitted state on 2 of 6 runs in that finding's batch, which
would make conditions B and C vacuous on most runs — and a vacuous arm scored as
a pass is the failure this whole design exists to refuse.

## The interleaved-thinking header, which is a departure and is not a small one

`thinking={"type":"enabled"}` alone — which is exactly what
[`wire_anthropic.py`](../../../../src/runtime/providers/wire_anthropic.py) sends
— produced a signed thinking block on **turn 0 and on no other turn** of this
six-turn chain. Measured, and committed at
[`results/calibration/`](./results/calibration/). A conversation carrying one
opaque state cannot be given a chain with a *hole* in it, so condition B would
have been unconstructible on the negative control, which is the arm the whole
design leans on.

Adding `anthropic-beta: interleaved-thinking-2025-05-14` makes the model think
between tool calls, and the same chain then carries state on all six turns.
**The runtime does not send that header**, so the measured emission pattern is
itself a result: on Anthropic as this repository configures it, *"carry every
turn's opaque state"* is carrying one state on a chain of this shape. That is
recorded in the finding rather than smoothed away, and it is the reason the
calibration artifact is committed beside the twelve cells rather than deleted.
"""
from __future__ import annotations

import json
import sys

import anthropic

import chain
import credentials
import loop

DEFAULT_MODEL = "claude-sonnet-4-5-20250929"
ADAPTIVE_MODELS = ("claude-sonnet-5", "claude-opus-5", "claude-opus-4-8",
                   "claude-opus-4-7")
MAX_TOKENS = 4096
THINKING_BUDGET = 2048

OPAQUE_BLOCKS = {"thinking": "signature", "redacted_thinking": "data"}

#: See the module docstring. Without this the chain carries one opaque state and
#: condition B cannot be built on the negative control.
INTERLEAVED_BETA = "interleaved-thinking-2025-05-14"


class AnthropicAdapter:
    provider = "anthropic"
    sdk = "anthropic"
    opaque_field = "thinking.signature"

    def __init__(self, model: str, key: str) -> None:
        self.model = model
        self.sdk_version = anthropic.__version__
        self.client = anthropic.Anthropic(api_key=key, max_retries=0)

    def first_user(self):
        return {"role": "user", "content": chain.QUESTION}

    def flatten(self, kind, body):
        return [body]

    def thinking_kwargs(self) -> dict:
        if self.model in ADAPTIVE_MODELS:
            return {"thinking": {"type": "adaptive"},
                    "output_config": {"effort": "high"}}
        return {"thinking": {"type": "enabled",
                             "budget_tokens": THINKING_BUDGET}}

    def send(self, entries):
        return self.client.messages.create(
            model=self.model, max_tokens=MAX_TOKENS, system=chain.SYSTEM,
            tools=[{"name": t["name"], "description": t["description"],
                    "input_schema": t["parameters"]} for t in chain.TOOLS],
            messages=list(entries),
            extra_headers={"anthropic-beta": INTERLEAVED_BETA},
            **self.thinking_kwargs())

    def assistant(self, response):
        blocks = [b.model_dump(exclude_none=True) if hasattr(b, "model_dump")
                  else dict(b) for b in response.content]
        paths = []
        for position, block in enumerate(blocks):
            field = OPAQUE_BLOCKS.get(block.get("type"))
            if field and block.get(field):
                paths.append(["content", position, field])
        return {"role": "assistant", "content": blocks}, paths

    def usage(self, response):
        return response.usage.input_tokens, response.usage.output_tokens, None

    def tool_calls(self, body):
        return [(b["id"], b["name"], dict(b.get("input") or {}))
                for b in body["content"] if b.get("type") == "tool_use"]

    def tool_entry(self, results):
        return {"role": "user",
                "content": [{"type": "tool_result", "tool_use_id": call_id,
                             "content": json.dumps(out)}
                            for call_id, _name, out in results]}

    def text(self, body):
        return "".join(b.get("text") or "" for b in body["content"]
                       if b.get("type") == "text")

    def classify(self, exc):
        if isinstance(exc, anthropic.APIStatusError):
            kind = ("environmental" if exc.status_code in (401, 403, 429)
                    else "capability")
            return exc.status_code, kind
        if isinstance(exc, anthropic.APIConnectionError):
            return None, "environmental"
        return None


def factory(model: str):
    key, var, fingerprint = credentials.key_for("anthropic")
    return AnthropicAdapter(model, key), var, fingerprint


if __name__ == "__main__":
    sys.exit(loop.main(factory, DEFAULT_MODEL))
