"""SPIKE - E16 arm 3/4 — Google, through the `google-genai` SDK. No abstraction layer.

Opaque field: ``thought_signature`` on a ``Part``. Gemini 3 returns it attached
to the function-call part rather than as a separate reasoning block, and
Google's documentation is explicit that it must be sent back on the following
turn for multi-turn tool use to behave.

That makes this the arm where dropping the field is *most* likely to look
harmless — the signature rides on a part the adapter already has to forward, so
an adapter that rebuilds the part from name and args alone loses it while
appearing to work.
"""
from __future__ import annotations

import sys

from google import genai
from google.genai import types as gt

import envroot
import scenario
import verdict

DEFAULT_MODEL = "gemini-3-flash-preview"


def tool_declarations() -> gt.Tool:
    return gt.Tool(
        function_declarations=[
            gt.FunctionDeclaration(
                name=t["name"], description=t["description"], parameters=t["parameters"]
            )
            for t in scenario.TOOLS
        ]
    )


def opaque_values(parts) -> list:
    """`thought_signature` on every part that carries one, in order."""
    out = []
    for p in parts or []:
        sig = getattr(p, "thought_signature", None)
        if sig is None and isinstance(p, dict):
            sig = p.get("thought_signature")
        if sig:
            out.append(sig)
    return out


def main() -> int:
    model = DEFAULT_MODEL
    if "--model" in sys.argv:
        model = sys.argv[sys.argv.index("--model") + 1]

    res = verdict.ArmResult(
        provider="google",
        sdk="google-genai",
        sdk_version=getattr(genai, "__version__", "unknown"),
        model=model,
        credential_var="",
        credential_fp="",
        opaque_field="Part.thought_signature",
    )
    key, var, fp = envroot.key_for("google")
    res.credential_var, res.credential_fp = var, fp
    client = genai.Client(api_key=key)

    log = scenario.ToolLog()
    contents: list[gt.Content] = [
        gt.Content(role="user", parts=[gt.Part(text=scenario.QUESTION)])
    ]
    config = gt.GenerateContentConfig(
        system_instruction=scenario.SYSTEM,
        tools=[tool_declarations()],
        automatic_function_calling=gt.AutomaticFunctionCallingConfig(disable=True),
    )

    try:
        with verdict.Timer() as t:
            for _ in range(4):
                resp = client.models.generate_content(
                    model=model, contents=contents, config=config
                )
                res.turns += 1
                if resp.usage_metadata:
                    res.input_tokens += resp.usage_metadata.prompt_token_count or 0
                    res.output_tokens += (
                        resp.usage_metadata.candidates_token_count or 0
                    ) + (getattr(resp.usage_metadata, "thoughts_token_count", 0) or 0)

                cand = resp.candidates[0]
                parts = cand.content.parts or []

                got = opaque_values(parts)
                if got:
                    res.opaque_state_present = True
                    res.digests_in.extend(verdict.digest_all(got))

                # The model turn goes back exactly as received. The SDK's own
                # Content object is the wire form here, so the round-trip is
                # measured by re-reading the signature off what we append.
                contents.append(cand.content)
                res.digests_out.extend(
                    verdict.digest_all(opaque_values(contents[-1].parts or []))
                )

                calls = [p.function_call for p in parts if getattr(p, "function_call", None)]
                if not calls:
                    res.final_text = "".join(
                        p.text for p in parts if getattr(p, "text", None)
                    )
                    break

                response_parts = []
                for call in calls:
                    out = log.dispatch(call.name, dict(call.args or {}))
                    response_parts.append(
                        gt.Part.from_function_response(name=call.name, response=out)
                    )
                contents.append(gt.Content(role="user", parts=response_parts))
        res.elapsed_s = t.elapsed

        res.provider_accepted = res.turns > 1 if res.opaque_state_present else None
        if res.digests_in:
            res.sdk_preserved = res.digests_in == res.digests_out
        res.tool_calls = log.names
        res.chained = log.chained()
        res.answer_correct = scenario.answer_correct(res.final_text)
        res.ok = True
        if not res.opaque_state_present:
            res.note("no thought_signature returned; round-trip untestable on this configuration")
    except Exception as exc:  # noqa: BLE001
        text = str(exc)
        code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
        environmental = code in (401, 403, 429) or "API key not valid" in text or "quota" in text.lower()
        res.failure_kind = "environmental" if environmental else "capability"
        res.error = f"{type(exc).__name__}: {text[:400]}"

    return verdict.emit(res)


if __name__ == "__main__":
    sys.exit(main())
