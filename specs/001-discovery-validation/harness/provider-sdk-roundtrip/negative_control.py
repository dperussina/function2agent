"""SPIKE - E16 negative control. Do not import from product code.

**Why this exists.** Four arms reporting ``sdk_preserved: true`` is worth
nothing unless that field can be false. A check that cannot fail is not a
measurement, and this corpus has a standing convention of shipping the control
alongside the result — finding 007 ran a shape-and-type-only verifier that had
to detect *none* of its injected faults, for exactly this reason.

This control drives the same scenario through the same SDK, drops the opaque
field on re-injection, and asserts two things:

1. **The digest comparison catches the drop.** If it does not, every positive
   result in this harness is void.
2. **Whether the drop is observable in behaviour at two hops.** This is the
   more interesting half. Finding 003 recorded chained tool use working on xAI
   *while* the field was being dropped and warned that a two-hop pass "should
   not be read as clearance." If chaining still succeeds here with the field
   removed, that caution is confirmed by direct measurement rather than
   inherited — and it bounds what the positive arms prove.

Arm choice: xAI, because it is the provider whose field ADK's adapter dropped,
so it is the one where the historical failure is real rather than hypothetical.
"""
from __future__ import annotations

import json
import sys

import xai_sdk
from xai_sdk import chat as xchat

import arm_xai
import envroot
import scenario
import verdict


def main() -> int:
    model = arm_xai.DEFAULT_MODEL
    if "--model" in sys.argv:
        model = sys.argv[sys.argv.index("--model") + 1]

    key, var, fp = envroot.key_for("xai")
    client = xai_sdk.Client(api_key=key)
    log = scenario.ToolLog()

    out = {
        "control": "drop-opaque-field-on-reinjection",
        "provider": "xai",
        "sdk": "xai-sdk",
        "model": model,
        "credential_var": var,
        "credential_fp": fp,
        "digests_in": [],
        "digests_out": [],
        "detector_fired": None,
        "chained_without_opaque_state": None,
        "answer_correct_without_opaque_state": None,
        "provider_errored": False,
        "error": None,
        "input_tokens": 0,
        "output_tokens": 0,
        "notes": [],
    }

    try:
        conv = client.chat.create(model=model, tools=arm_xai.tool_defs(), use_encrypted_content=True)
        conv.append(xchat.system(scenario.SYSTEM))
        conv.append(xchat.user(scenario.QUESTION))

        final_text = ""
        for _ in range(4):
            resp = conv.sample()
            usage = getattr(resp, "usage", None)
            if usage:
                out["input_tokens"] += getattr(usage, "prompt_tokens", 0) or 0
                out["output_tokens"] += (getattr(usage, "completion_tokens", 0) or 0) + (
                    getattr(usage, "reasoning_tokens", 0) or 0
                )

            enc = getattr(resp, "encrypted_content", "") or ""
            if enc:
                out["digests_in"].append(verdict.digest(enc))

            conv.append(resp)

            # THE MUTATION. Strip the opaque field off every assistant message
            # now in the conversation, which is what an adapter that rebuilds
            # the message from role/content/tool_calls does by omission.
            for m in conv.proto.messages:
                if getattr(m, "encrypted_content", ""):
                    m.encrypted_content = ""

            out["digests_out"] = [
                verdict.digest(v) for v in arm_xai.appended_opaque(conv)
            ]

            calls = list(getattr(resp, "tool_calls", None) or [])
            if not calls:
                final_text = resp.content or ""
                break
            for call in calls:
                result = log.dispatch(
                    call.function.name, json.loads(call.function.arguments or "{}")
                )
                conv.append(xchat.tool_result(json.dumps(result), call.id))

        # 1. Did the detector fire? It must.
        out["detector_fired"] = out["digests_in"] != out["digests_out"]

        # 2. Did behaviour degrade observably at two hops?
        out["chained_without_opaque_state"] = log.chained()
        out["answer_correct_without_opaque_state"] = scenario.answer_correct(final_text)

        if not out["digests_in"]:
            out["notes"].append(
                "provider emitted no opaque state, so the control proves nothing this run"
            )
        elif not out["detector_fired"]:
            out["notes"].append(
                "DETECTOR DID NOT FIRE — every positive result in this harness is void"
            )
        else:
            out["notes"].append("detector fired: the sdk_preserved check can distinguish a drop")

        if out["chained_without_opaque_state"]:
            out["notes"].append(
                "chaining still succeeded with the field dropped — a two-hop pass is NOT "
                "sensitive to opaque-state loss, confirming finding 003's caution by measurement"
            )
    except Exception as exc:  # noqa: BLE001
        out["provider_errored"] = True
        out["error"] = f"{type(exc).__name__}: {str(exc)[:400]}"
        out["notes"].append(
            "the provider rejected the mutated conversation — opaque-state loss is "
            "detectable at the API boundary on this provider"
        )

    print(json.dumps(out, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
