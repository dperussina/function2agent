"""SPIKE - E16 arm 1/4 — Anthropic, through the `anthropic` SDK. No abstraction layer.

Opaque field: the ``signature`` on a ``thinking`` block (and ``data`` on a
``redacted_thinking`` block). Anthropic validates the signature server-side on
re-injection, which makes ``provider_accepted`` a real independent check here:
a mutated signature is rejected rather than ignored.
"""
from __future__ import annotations

import sys

import anthropic

import envroot
import scenario
import verdict

# Two request shapes, and which one a model accepts is *model-specific*.
#
#   claude-sonnet-5 rejects `thinking={"type":"enabled","budget_tokens":N}` with
#   400 *"'thinking.type.enabled' is not supported for this model. Use
#   'thinking.type.adaptive' and 'output_config.effort'"*.
#
#   claude-sonnet-4-5-20250929 accepts the enabled shape and emits a signed
#   thinking block for this task; sonnet-5 under adaptive emits none, because
#   adaptive declined to think about a task this small.
#
# Both were observed on 2026-08-03 and both are in the finding. The default is
# the model on which the round-trip is *testable*, because an arm that emits no
# opaque state measures nothing about FR-037.
ADAPTIVE_MODELS = ("claude-sonnet-5", "claude-opus-5", "claude-opus-4-8", "claude-opus-4-7")
DEFAULT_MODEL = "claude-sonnet-4-5-20250929"
MAX_TOKENS = 2048
THINKING_BUDGET = 1024


def thinking_kwargs(model: str) -> dict:
    if model in ADAPTIVE_MODELS:
        return {"thinking": {"type": "adaptive"}, "output_config": {"effort": "high"}}
    return {"thinking": {"type": "enabled", "budget_tokens": THINKING_BUDGET}}


def tool_schemas():
    return [
        {"name": t["name"], "description": t["description"], "input_schema": t["parameters"]}
        for t in scenario.TOOLS
    ]


def opaque_values(blocks) -> list:
    """Every opaque reasoning value in an assistant turn, in order."""
    out = []
    for b in blocks:
        btype = getattr(b, "type", None) or (b.get("type") if isinstance(b, dict) else None)
        if btype == "thinking":
            sig = getattr(b, "signature", None) or (b.get("signature") if isinstance(b, dict) else None)
            if sig:
                out.append(sig)
        elif btype == "redacted_thinking":
            data = getattr(b, "data", None) or (b.get("data") if isinstance(b, dict) else None)
            if data:
                out.append(data)
    return out


def to_wire(blocks) -> list[dict]:
    """The assistant turn as the next request needs it.

    This is the round-trip under test: the SDK's response objects become
    request dicts here, and if that conversion drops `signature` the digests
    will not match.
    """
    wire = []
    for b in blocks:
        wire.append(b.model_dump(exclude_none=True) if hasattr(b, "model_dump") else dict(b))
    return wire


def main() -> int:
    model = DEFAULT_MODEL
    if "--model" in sys.argv:
        model = sys.argv[sys.argv.index("--model") + 1]

    res = verdict.ArmResult(
        provider="anthropic",
        sdk="anthropic",
        sdk_version=anthropic.__version__,
        model=model,
        credential_var="",
        credential_fp="",
        opaque_field="thinking.signature",
    )
    try:
        key, var, fp = envroot.key_for("anthropic")
    except SystemExit:
        raise
    res.credential_var, res.credential_fp = var, fp
    client = anthropic.Anthropic(api_key=key)

    log = scenario.ToolLog()
    messages: list[dict] = [{"role": "user", "content": scenario.QUESTION}]

    try:
        with verdict.Timer() as t:
            for _ in range(4):
                resp = client.messages.create(
                    model=model,
                    max_tokens=MAX_TOKENS,
                    system=scenario.SYSTEM,
                    tools=tool_schemas(),
                    messages=messages,
                    **thinking_kwargs(model),
                )
                res.turns += 1
                res.input_tokens += resp.usage.input_tokens
                res.output_tokens += resp.usage.output_tokens

                # Hash the opaque state as received.
                got = opaque_values(resp.content)
                if got:
                    res.opaque_state_present = True
                    res.digests_in.extend(verdict.digest_all(got))

                wire = to_wire(resp.content)

                # Hash it again after the SDK round-trip into request shape.
                res.digests_out.extend(verdict.digest_all(opaque_values(wire)))

                messages.append({"role": "assistant", "content": wire})

                tool_uses = [b for b in resp.content if getattr(b, "type", None) == "tool_use"]
                if not tool_uses:
                    res.final_text = "".join(
                        getattr(b, "text", "") for b in resp.content if getattr(b, "type", None) == "text"
                    )
                    break

                results = []
                for tu in tool_uses:
                    out = log.dispatch(tu.name, dict(tu.input))
                    results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": tu.id,
                            "content": verdict.json.dumps(out),
                        }
                    )
                messages.append({"role": "user", "content": results})
        res.elapsed_s = t.elapsed

        # The provider accepted every re-injection, or we would not be here:
        # Anthropic verifies the thinking signature and 400s on a bad one.
        res.provider_accepted = res.turns > 1 if res.opaque_state_present else None
        if res.digests_in:
            res.sdk_preserved = res.digests_in == res.digests_out
        res.tool_calls = log.names
        res.chained = log.chained()
        res.answer_correct = scenario.answer_correct(res.final_text)
        res.ok = True
        if not res.opaque_state_present:
            res.note("no thinking signature emitted; round-trip untestable on this configuration")
    except anthropic.APIStatusError as exc:
        res.failure_kind = "environmental" if exc.status_code in (401, 403, 429) else "capability"
        res.error = f"{type(exc).__name__} {exc.status_code}: {str(exc)[:400]}"
    except anthropic.APIConnectionError as exc:
        res.failure_kind = "environmental"
        res.error = f"{type(exc).__name__}: {str(exc)[:400]}"
    except Exception as exc:  # noqa: BLE001
        res.failure_kind = "capability"
        res.error = f"{type(exc).__name__}: {str(exc)[:400]}"

    return verdict.emit(res)


if __name__ == "__main__":
    sys.exit(main())
