"""SPIKE - E18 arm 2/4 — OpenAI. The limb whose vendor quote carries explicit error language.

Opaque field: `encrypted_content` on a `reasoning` item in the Responses API,
returned only when the caller both asks for it
(`include=["reasoning.encrypted_content"]`) and declines server-side state
(`store=False`).

**Why `store=False` is the configuration under test rather than a detail.** With
`store=True` the round-trip is the provider's problem and a dropped state is
invisible. With `store=False` the provider keeps nothing, the chain is entirely
ours, and a dropped state is the silent multi-turn degradation FR-037 exists to
prevent. It is also the configuration a self-hosted product wants.

**The prediction, and where it comes from.**
[`src/runtime/context.py`](../../../../src/runtime/context.py)`::states_for`
quotes the vendor as saying, of these items, *"The API will error if these are
not included"*. That is explicit error language rather than an imperative — one
of the two limbs of the four that
[finding 030](../../findings/030-provider-state-chain-derived-not-measured.md) §1
records as documentation-derived **with** an error claim in the source. It has
still never been measured from this repository, in any condition.

**The journal body for a turn is `{"items": [...]}`, not a message.** The
Responses API's conversation is a flat list of items rather than a list of
messages, so one assistant turn is several entries. Wrapping them keeps the
journal's one-body-per-turn shape, which is what makes the withheld-state
ordinal mean the same thing here as on the other three providers.

## Reasoning effort is `medium`, and the reason is measured rather than chosen

At `effort: "low"` — which is what
[`wire_openai.py`](../../../../src/runtime/providers/wire_openai.py) configures
for `gpt-5-mini` specifically — this chain produced an `encrypted_content` on
**turn 0 only**, measured and committed at
[`results/calibration/`](./results/calibration/). One state cannot be given a
hole, so condition B would have been unconstructible on the one provider whose
vendor quote carries the words *"The API will error"*. At `medium` and at `high`
the same chain carries state on all six turns; `medium` is the effort the same
driver configures for every other model, so it is the runtime's own setting
rather than an invention.

**This was decided before conditions B and C ran and it is recorded here rather
than in a footnote**, because changing a knob after seeing a result is exactly
what Rule 5 of the [`experiment-design`](../../../../.cursor/skills/experiment-design/SKILL.md)
skill forbids. What was changed is not a threshold and not a scoring rule: it is
the precondition for the treatment existing at all, which is the same choice
finding 016 made when it ran `claude-sonnet-4-5` rather than a model that
emitted nothing. Row A was re-run under `medium` so that all three conditions
share one configuration and the deltas stay one-variable.
"""
from __future__ import annotations

import json
import sys

import openai

import chain
import credentials
import loop

DEFAULT_MODEL = "gpt-5-mini"

#: See the module docstring. `low` emits state on one turn of this chain and
#: makes condition B unconstructible; `medium` emits it on all six.
EFFORT = "medium"


class OpenAIAdapter:
    provider = "openai"
    sdk = "openai"
    opaque_field = "reasoning.encrypted_content"

    def __init__(self, model: str, key: str) -> None:
        self.model = model
        self.sdk_version = openai.__version__
        self.client = openai.OpenAI(api_key=key, max_retries=0)

    def first_user(self):
        return {"role": "user", "content": chain.QUESTION}

    def flatten(self, kind, body):
        # Assistant turns and tool-result turns are both several entries; the
        # opening user message is one.
        return list(body["items"]) if "items" in body else [body]

    def send(self, entries):
        return self.client.responses.create(
            model=self.model, instructions=chain.SYSTEM, input=list(entries),
            tools=[{"type": "function", "name": t["name"],
                    "description": t["description"],
                    "parameters": t["parameters"]} for t in chain.TOOLS],
            store=False, include=["reasoning.encrypted_content"],
            reasoning={"effort": EFFORT})

    def assistant(self, response):
        items = [it.model_dump(exclude_none=True) if hasattr(it, "model_dump")
                 else dict(it) for it in response.output]
        paths = [["items", position, "encrypted_content"]
                 for position, item in enumerate(items)
                 if item.get("type") == "reasoning"
                 and item.get("encrypted_content")]
        return {"items": items}, paths

    def usage(self, response):
        usage = response.usage
        if usage is None:
            return 0, 0, None
        return usage.input_tokens, usage.output_tokens, None

    def tool_calls(self, body):
        return [(it["call_id"], it["name"], loop.json_args(it.get("arguments")))
                for it in body["items"] if it.get("type") == "function_call"]

    def tool_entry(self, results):
        # One journal body, several request entries — same wrapper as an
        # assistant turn, for the same reason.
        return {"items": [{"type": "function_call_output", "call_id": call_id,
                           "output": json.dumps(out)}
                          for call_id, _name, out in results]}

    def text(self, body):
        out = []
        for item in body["items"]:
            if item.get("type") != "message":
                continue
            for piece in item.get("content") or ():
                if piece.get("type") == "output_text":
                    out.append(piece.get("text") or "")
        return "".join(out)

    def classify(self, exc):
        if isinstance(exc, openai.APIStatusError):
            kind = ("environmental" if exc.status_code in (401, 403, 429)
                    else "capability")
            return exc.status_code, kind
        if isinstance(exc, openai.APIConnectionError):
            return None, "environmental"
        return None


def factory(model: str):
    key, var, fingerprint = credentials.key_for("openai")
    return OpenAIAdapter(model, key), var, fingerprint


if __name__ == "__main__":
    sys.exit(loop.main(factory, DEFAULT_MODEL))
