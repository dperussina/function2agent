"""SPIKE - E18 arm 3/4 — Google. The limb whose vendor quote carries an explicit status code.

Opaque field: `thought_signature` on a `Part`. Gemini 3 attaches it to the
function-call part rather than returning it as a separate reasoning block, which
makes this the provider where dropping the field is *most* likely to look
harmless: the signature rides on a part an adapter already has to forward, so an
adapter that rebuilds the part from name and args alone loses it while appearing
to work.

**The prediction.**
[`src/runtime/context.py`](../../../../src/runtime/context.py)`::states_for`
quotes the vendor with a **400** attached, which is the second of the two limbs
[finding 030](../../findings/030-provider-state-chain-derived-not-measured.md) §1
records as documentation-derived with an explicit failure claim. Never measured
from this repository.

**The carrier, and one honest asymmetry with the other three arms.**
`thought_signature` is genuinely `bytes`. `Content.model_dump(mode="json")`
renders it as URL-safe base64 and `Content.model_validate` reads that back to
the identical bytes — verified before this arm was written — so the journal here
holds a base64 **string** where the other three hold the vendor's own string.
The digests this arm reports are therefore over base64 text rather than over raw
bytes. That is an identity handle and not a byte-fidelity assertion; finding 016
measured byte fidelity on all four providers and this harness does not
re-measure it.
"""
from __future__ import annotations

import sys

from google import genai
from google.genai import types as gt

import chain
import credentials
import loop

DEFAULT_MODEL = "gemini-3-flash-preview"


class GoogleAdapter:
    provider = "google"
    sdk = "google-genai"
    opaque_field = "Part.thought_signature"

    def __init__(self, model: str, key: str) -> None:
        self.model = model
        self.sdk_version = getattr(genai, "__version__", "unknown")
        self.client = genai.Client(api_key=key)
        self.config = gt.GenerateContentConfig(
            system_instruction=chain.SYSTEM,
            tools=[gt.Tool(function_declarations=[
                gt.FunctionDeclaration(name=t["name"],
                                       description=t["description"],
                                       parameters=t["parameters"])
                for t in chain.TOOLS])],
            automatic_function_calling=gt.AutomaticFunctionCallingConfig(
                disable=True),
        )

    def first_user(self):
        return {"role": "user", "parts": [{"text": chain.QUESTION}]}

    def flatten(self, kind, body):
        return [body]

    def send(self, entries):
        return self.client.models.generate_content(
            model=self.model, contents=list(entries), config=self.config)

    def assistant(self, response):
        content = response.candidates[0].content
        body = content.model_dump(mode="json", exclude_none=True)
        body.setdefault("role", "model")
        paths = [["parts", position, "thought_signature"]
                 for position, part in enumerate(body.get("parts") or ())
                 if part.get("thought_signature")]
        return body, paths

    def usage(self, response):
        meta = response.usage_metadata
        if meta is None:
            return 0, 0, None
        out = (meta.candidates_token_count or 0) + (
            getattr(meta, "thoughts_token_count", 0) or 0)
        return meta.prompt_token_count or 0, out, None

    def tool_calls(self, body):
        calls = []
        for position, part in enumerate(body.get("parts") or ()):
            call = part.get("function_call")
            if not call:
                continue
            # Gemini's function-call parts have no id of their own; the
            # position is the handle, and the response part is matched by name.
            calls.append((f"part-{position}", call["name"],
                          dict(call.get("args") or {})))
        return calls

    def tool_entry(self, results):
        return {"role": "user",
                "parts": [{"function_response": {"name": name,
                                                 "response": out}}
                          for _call_id, name, out in results]}

    def text(self, body):
        return "".join(part.get("text") or ""
                       for part in body.get("parts") or ())

    def classify(self, exc):
        status = getattr(exc, "code", None) or getattr(exc, "status_code", None)
        text = str(exc)
        if status is None and "APIError" not in type(exc).__name__:
            # Not one of the SDK's own error types; the loop records it as a
            # harness fault rather than scoring it as a provider verdict.
            if "google" not in type(exc).__module__:
                return None
        lowered = text.lower()
        environmental = (status in (401, 403, 429)
                         or "api key not valid" in lowered
                         or "quota" in lowered
                         or "resource_exhausted" in lowered)
        return status, "environmental" if environmental else "capability"


def factory(model: str):
    key, var, fingerprint = credentials.key_for("google")
    return GoogleAdapter(model, key), var, fingerprint


if __name__ == "__main__":
    sys.exit(loop.main(factory, DEFAULT_MODEL))
