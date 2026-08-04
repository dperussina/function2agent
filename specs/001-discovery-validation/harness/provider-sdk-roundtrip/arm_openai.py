"""SPIKE - E16 arm 2/4 — OpenAI, through the `openai` SDK. No abstraction layer.

Opaque field: ``encrypted_content`` on a ``reasoning`` item in the Responses
API. It is only returned when the caller both asks for it
(``include=["reasoning.encrypted_content"]``) and declines server-side state
(``store=False``) — which is the configuration a self-hosted product wants
anyway, because it is the one where the provider keeps nothing.

That combination is the point of testing this provider: with ``store=True`` the
round-trip is the provider's problem and an adapter that drops the field is
invisible. With ``store=False`` it is ours, and dropping it is exactly the
silent multi-turn degradation FR-037 exists to prevent.
"""
from __future__ import annotations

import sys

import openai

import envroot
import scenario
import verdict

DEFAULT_MODEL = "gpt-5-mini"


def tool_schemas():
    return [
        {
            "type": "function",
            "name": t["name"],
            "description": t["description"],
            "parameters": t["parameters"],
        }
        for t in scenario.TOOLS
    ]


def opaque_values(items) -> list:
    """`encrypted_content` on every reasoning item, in order."""
    out = []
    for it in items:
        itype = getattr(it, "type", None) or (it.get("type") if isinstance(it, dict) else None)
        if itype == "reasoning":
            enc = getattr(it, "encrypted_content", None)
            if enc is None and isinstance(it, dict):
                enc = it.get("encrypted_content")
            if enc:
                out.append(enc)
    return out


def to_wire(items) -> list[dict]:
    """Response items as the next request needs them: the round-trip under test."""
    return [it.model_dump(exclude_none=True) if hasattr(it, "model_dump") else dict(it) for it in items]


def main() -> int:
    model = DEFAULT_MODEL
    if "--model" in sys.argv:
        model = sys.argv[sys.argv.index("--model") + 1]

    res = verdict.ArmResult(
        provider="openai",
        sdk="openai",
        sdk_version=openai.__version__,
        model=model,
        credential_var="",
        credential_fp="",
        opaque_field="reasoning.encrypted_content",
    )
    key, var, fp = envroot.key_for("openai")
    res.credential_var, res.credential_fp = var, fp
    client = openai.OpenAI(api_key=key)

    log = scenario.ToolLog()
    conversation: list = [{"role": "user", "content": scenario.QUESTION}]

    try:
        with verdict.Timer() as t:
            for _ in range(4):
                resp = client.responses.create(
                    model=model,
                    instructions=scenario.SYSTEM,
                    input=conversation,
                    tools=tool_schemas(),
                    store=False,
                    include=["reasoning.encrypted_content"],
                    reasoning={"effort": "low"},
                )
                res.turns += 1
                if resp.usage:
                    res.input_tokens += resp.usage.input_tokens
                    res.output_tokens += resp.usage.output_tokens

                got = opaque_values(resp.output)
                if got:
                    res.opaque_state_present = True
                    res.digests_in.extend(verdict.digest_all(got))

                wire = to_wire(resp.output)
                res.digests_out.extend(verdict.digest_all(opaque_values(wire)))

                # Every output item goes back verbatim, reasoning items included.
                conversation.extend(wire)

                calls = [it for it in resp.output if getattr(it, "type", None) == "function_call"]
                if not calls:
                    res.final_text = resp.output_text or ""
                    break

                for call in calls:
                    out = log.dispatch(call.name, verdict.json.loads(call.arguments or "{}"))
                    conversation.append(
                        {
                            "type": "function_call_output",
                            "call_id": call.call_id,
                            "output": verdict.json.dumps(out),
                        }
                    )
        res.elapsed_s = t.elapsed

        res.provider_accepted = res.turns > 1 if res.opaque_state_present else None
        if res.digests_in:
            res.sdk_preserved = res.digests_in == res.digests_out
        res.tool_calls = log.names
        res.chained = log.chained()
        res.answer_correct = scenario.answer_correct(res.final_text)
        res.ok = True
        if not res.opaque_state_present:
            res.note(
                "no reasoning.encrypted_content returned despite include= and store=False; "
                "round-trip untestable on this configuration"
            )
    except openai.APIStatusError as exc:
        res.failure_kind = "environmental" if exc.status_code in (401, 403, 429) else "capability"
        res.error = f"{type(exc).__name__} {exc.status_code}: {str(exc)[:400]}"
    except openai.APIConnectionError as exc:
        res.failure_kind = "environmental"
        res.error = f"{type(exc).__name__}: {str(exc)[:400]}"
    except Exception as exc:  # noqa: BLE001
        res.failure_kind = "capability"
        res.error = f"{type(exc).__name__}: {str(exc)[:400]}"

    return verdict.emit(res)


if __name__ == "__main__":
    sys.exit(main())
