"""SPIKE - E16 arm 4/4 — xAI, through the `xai-sdk`. No abstraction layer.

**This is the arm the spike exists for.** Finding 003 result 7 counted ADK's
LiteLLM adapter referencing `encrypted_content` — xAI's opaque reasoning field
— **zero times under every counting rule**, while referencing the equivalent
field for three other providers 35, 16 and 9 times. Chained tool use still
worked at two hops, so the gap did not announce itself; finding 003 recorded
that as "a weak result and should not be read as clearance."

**OD-16** replaced that adapter with this vendor's own SDK. Whether the
replacement actually carries the field is the question, and it is the one half
of SC-010 that finding 003's four-provider pass does *not* transfer.

Opaque field: ``encrypted_content`` on an assistant message. It is returned
only when the chat is created with ``use_encrypted_content=True``.

``chat.append(response)`` is the SDK's own round-trip: it rebuilds the assistant
message from the response proto. An adapter that rebuilds from role, content
and tool_calls alone — which is the obvious way to write it — silently drops
the field. Reading the digest back off ``chat.proto.messages`` after the append
is what detects that.
"""
from __future__ import annotations

import sys

import xai_sdk
from xai_sdk import chat as xchat

import envroot
import scenario
import verdict

DEFAULT_MODEL = "grok-4.5"


def tool_defs():
    return [
        xchat.tool(
            name=t["name"],
            description=t["description"],
            parameters=t["parameters"],
        )
        for t in scenario.TOOLS
    ]


def appended_opaque(conv) -> list:
    """`encrypted_content` on every assistant message currently in the conversation."""
    out = []
    for m in conv.proto.messages:
        enc = getattr(m, "encrypted_content", "")
        if enc:
            out.append(enc)
    return out


def main() -> int:
    model = DEFAULT_MODEL
    if "--model" in sys.argv:
        model = sys.argv[sys.argv.index("--model") + 1]

    res = verdict.ArmResult(
        provider="xai",
        sdk="xai-sdk",
        sdk_version=getattr(xai_sdk, "__version__", "1.17.0"),
        model=model,
        credential_var="",
        credential_fp="",
        opaque_field="message.encrypted_content",
    )
    key, var, fp = envroot.key_for("xai")
    res.credential_var, res.credential_fp = var, fp
    client = xai_sdk.Client(api_key=key)

    log = scenario.ToolLog()

    try:
        with verdict.Timer() as t:
            conv = client.chat.create(
                model=model,
                tools=tool_defs(),
                use_encrypted_content=True,
            )
            conv.append(xchat.system(scenario.SYSTEM))
            conv.append(xchat.user(scenario.QUESTION))

            seen_before = 0
            for _ in range(4):
                resp = conv.sample()
                res.turns += 1
                usage = getattr(resp, "usage", None)
                if usage:
                    res.input_tokens += getattr(usage, "prompt_tokens", 0) or 0
                    res.output_tokens += (getattr(usage, "completion_tokens", 0) or 0) + (
                        getattr(usage, "reasoning_tokens", 0) or 0
                    )
                # xAI is the one provider here that reports a server-side cost
                # rather than leaving it to a price table.
                turn_cost = getattr(resp, "cost_usd", None)
                if turn_cost is not None:
                    res.cost_usd_reported_by_provider = (
                        res.cost_usd_reported_by_provider or 0.0
                    ) + turn_cost

                enc = getattr(resp, "encrypted_content", "") or ""
                if enc:
                    res.opaque_state_present = True
                    res.digests_in.append(verdict.digest(enc))

                # The SDK's own round-trip: response proto back into the
                # conversation. If it drops encrypted_content, the digest read
                # back off the appended message will not match.
                conv.append(resp)

                after = appended_opaque(conv)
                for value in after[seen_before:]:
                    res.digests_out.append(verdict.digest(value))
                seen_before = len(after)

                calls = list(getattr(resp, "tool_calls", None) or [])
                if not calls:
                    res.final_text = resp.content or ""
                    break

                for call in calls:
                    out = log.dispatch(
                        call.function.name,
                        verdict.json.loads(call.function.arguments or "{}"),
                    )
                    conv.append(xchat.tool_result(verdict.json.dumps(out), call.id))
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
                "no encrypted_content returned despite use_encrypted_content=True; "
                "round-trip untestable on this configuration"
            )
    except Exception as exc:  # noqa: BLE001
        text = str(exc)
        lowered = text.lower()
        environmental = (
            "unauthenticated" in lowered
            or "permission" in lowered
            or "quota" in lowered
            or "resource_exhausted" in lowered
            or "unavailable" in lowered
        )
        res.failure_kind = "environmental" if environmental else "capability"
        res.error = f"{type(exc).__name__}: {text[:400]}"

    return verdict.emit(res)


if __name__ == "__main__":
    sys.exit(main())
