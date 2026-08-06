"""SPIKE - E18 arm 4/4 — xAI. **The arm that resolves the contradiction.**

Opaque field: `encrypted_content` on an assistant message, returned only when
the chat is created with `use_encrypted_content=True`.

**Why this provider's three cells are the point of the whole run.**
[Finding 030](../../findings/030-provider-state-chain-derived-not-measured.md) §2
found a live measurement already in this repository that contradicts
[`src/runtime/context.py`](../../../../src/runtime/context.py)`::states_for`'s
sentence *"Only Anthropic degrades quietly on a miss; the other three fail the
request."*
[Finding 016](../../../001-discovery-validation/findings/016-provider-sdk-roundtrip.md)'s
negative control blanked `encrypted_content` on **every** assistant message of a
live `grok-4.5` chain and recorded
[`provider_errored: false`](../../../001-discovery-validation/harness/provider-sdk-roundtrip/results/negative-control.json).

**Condition C reproduces that condition and condition B tests a different one.**
A conversation carrying *no* encrypted content reads as an ordinary unencrypted
conversation; a chain with a *hole* is internally inconsistent, and inconsistency
is the thing a validator is for. Those are two requests, not one, and the whole
of why the xAI limb is in doubt is that only the first has ever been sent.

**The persistence boundary here is a proto round-trip, not a blanked field.**
`xai-sdk` carries the conversation as protobuf, so this arm serialises each
assistant message with `json_format.MessageToDict`, deletes the declared opaque
leaf, and rebuilds the whole conversation with `ParseDict` on every turn. That
is the same journal model the other three arms use, and it is stronger than
finding 016's mechanism, which mutated the SDK's live conversation in place.
It reaches the same wire condition for condition C: a proto3 scalar left at its
default is not serialised, so *blanked* and *omitted* are the same bytes.
"""
from __future__ import annotations

import json
import sys

from google.protobuf import json_format

import xai_sdk
from xai_sdk import chat as xchat

import chain
import credentials
import loop

DEFAULT_MODEL = "grok-4.5"


class XAIAdapter:
    provider = "xai"
    sdk = "xai-sdk"
    opaque_field = "message.encrypted_content"

    def __init__(self, model: str, key: str) -> None:
        self.model = model
        self.sdk_version = getattr(xai_sdk, "__version__", "unknown")
        self.client = xai_sdk.Client(api_key=key)
        self._tools = [xchat.tool(name=t["name"], description=t["description"],
                                  parameters=t["parameters"])
                       for t in chain.TOOLS]

    def first_user(self):
        return self._to_dict(xchat.user(chain.QUESTION))

    @staticmethod
    def _to_dict(message) -> dict:
        return json_format.MessageToDict(message,
                                         preserving_proto_field_name=True)

    @staticmethod
    def _to_proto(body: dict):
        return json_format.ParseDict(body, xchat.chat_pb2.Message())

    def flatten(self, kind, body):
        # A turn that answered several tool calls is several messages; the
        # journal holds one body per turn, so it is wrapped and unwrapped here.
        return list(body["_tool_results"]) if "_tool_results" in body else [body]

    def send(self, entries):
        # A fresh conversation every turn, rebuilt from the journal. The SDK's
        # own accumulating `chat` object is exactly the by-reference holding
        # that finding 030 §3 records as the reason finding 016's arms had no
        # persistence boundary at all.
        conversation = self.client.chat.create(
            model=self.model, tools=self._tools, use_encrypted_content=True)
        conversation.append(xchat.system(chain.SYSTEM))
        for body in entries:
            conversation.append(self._to_proto(body))
        return conversation.sample()

    def assistant(self, response):
        message = xchat.chat_pb2.Message(
            role=response._get_output().message.role,
            content=[xchat.text(response.content)],
            reasoning_content=response.reasoning_content,
            encrypted_content=response.encrypted_content,
            tool_calls=response.tool_calls,
        )
        body = self._to_dict(message)
        paths = [["encrypted_content"]] if body.get("encrypted_content") else []
        return body, paths

    def usage(self, response):
        usage = getattr(response, "usage", None)
        if usage is None:
            return 0, 0, None
        out = (getattr(usage, "completion_tokens", 0) or 0) + (
            getattr(usage, "reasoning_tokens", 0) or 0)
        # xAI is the one provider of the four that reports a server-side cost
        # rather than leaving it to a price table this harness does not have
        # and will not invent.
        cost = xchat.cost_usd_from_usage(usage)
        return getattr(usage, "prompt_tokens", 0) or 0, out, cost

    def tool_calls(self, body):
        return [(call["id"], call["function"]["name"],
                 loop.json_args(call["function"].get("arguments")))
                for call in body.get("tool_calls") or ()]

    def tool_entry(self, results):
        # One tool result per call, and the journal holds one body per turn, so
        # the bodies are wrapped and unwrapped by `flatten` below.
        return {"_tool_results": [
            self._to_dict(xchat.tool_result(json.dumps(out), call_id))
            for call_id, _name, out in results]}

    def text(self, body):
        return "".join(piece.get("text") or ""
                       for piece in body.get("content") or ())

    def classify(self, exc):
        import grpc

        if isinstance(exc, grpc.RpcError):
            code = exc.code() if callable(getattr(exc, "code", None)) else None
            name = getattr(code, "name", str(code))
            environmental = name in ("UNAUTHENTICATED", "PERMISSION_DENIED",
                                     "RESOURCE_EXHAUSTED", "UNAVAILABLE")
            return None, "environmental" if environmental else "capability"
        return None


def factory(model: str):
    key, var, fingerprint = credentials.key_for("xai")
    return XAIAdapter(model, key), var, fingerprint


if __name__ == "__main__":
    sys.exit(loop.main(factory, DEFAULT_MODEL))
