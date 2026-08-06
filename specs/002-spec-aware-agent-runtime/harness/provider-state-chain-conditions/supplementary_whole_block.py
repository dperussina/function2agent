"""SPIKE - E18 supplementary. **Not one of the twelve cells.** Two arms, one question.

    python3 supplementary_whole_block.py --provider anthropic|openai

## Why this exists, and why the twelve-cell table needs it

The twelve arms withhold **the opaque field**, leaving the block or item it sat
on in place — because that is what
[`src/runtime/context.py`](../../../../src/runtime/context.py)`::states_for`
returning `None` produces in a journal-backed runtime, and it is what
[`tests/conformance/test_provider_state_roundtrip.py`](../../../../tests/conformance/test_provider_state_roundtrip.py)`::_persisted`
models. Run that way, **Anthropic 400s** with
`thinking.signature: Field required` and **OpenAI does not error at all**.

Both readings have a second explanation the twelve cells cannot exclude, and
they are opposite explanations:

- **Anthropic** may be rejecting a *malformed block* rather than a *missing
  state*. A `thinking` block whose `signature` is absent violates the request
  schema whatever the field means. An adapter that dropped the **whole thinking
  block** — which is [finding 003](../../../001-discovery-validation/findings/003-runtime-provider-agnosticism.md)
  result 7's actual defect shape, an adapter rebuilding the message from role,
  content and tool calls — sends a *well-formed* request with the state gone.
  Whether that one errors is the question the negative control was really
  supposed to be about, and the twelve cells do not answer it.
- **OpenAI**'s vendor quote — *"The API will error if these are not included"* —
  is about **the reasoning items not being included**. The twelve cells left
  every reasoning item in place and removed only `encrypted_content` from it.
  So a tolerated cell there narrows the docstring's claim without touching the
  vendor's, and separating the two needs the item omitted outright.

Each arm here drives the same six-turn chain and **omits the whole carrier** on
every assistant turn — condition C's severity, applied one level up. There is no
drop-one variant: a conversation with one block removed and the rest present is
a fourth condition nobody has asked for yet.

**What a tolerated result here would and would not mean.** It would mean the
provider accepts the request. It would **not** mean the provider is undamaged:
this scenario is too small to have an answer that depends on the withheld
reasoning, which is the same limit
[finding 016](../../../001-discovery-validation/findings/016-provider-sdk-roundtrip.md)
recorded about its own. *Not erroring* and *not degrading* remain two claims and
this arm reaches only the first.
"""
from __future__ import annotations

import json
import sys

import chain
import conditions as C
import credentials

MAX_TURNS = 8


def _record(provider: str, model: str, sdk: str, version: str,
            carrier: str) -> C.ArmResult:
    result = C.ArmResult(provider=provider, condition="D-whole-carrier-omitted",
                         sdk=sdk, sdk_version=version, model=model,
                         opaque_field=carrier)
    result.note("SUPPLEMENTARY — not one of the twelve cells. The whole "
                "carrier is omitted, not just the opaque field.")
    return result


def _finish(result: C.ArmResult, log: chain.ToolLog) -> int:
    result.tool_calls = log.names
    result.hops_linked = log.hops_linked()
    result.chained = log.chained()
    result.answer_correct = chain.answer_correct(result.final_text)
    if result.state_turns == 0:
        result.verdict = "UNTESTABLE-NO-STATE"
    elif result.provider_errored:
        result.verdict = "ERRORED"
    else:
        result.verdict = "TOLERATED"
    C.ledger_add(result)
    print(json.dumps(result.as_dict(), indent=2, default=str))
    return 2 if result.error_kind == "environmental" else 0


def run_anthropic() -> int:
    import anthropic

    import arm_anthropic

    key, var, fingerprint = credentials.key_for("anthropic")
    model = arm_anthropic.DEFAULT_MODEL
    result = _record("anthropic", model, "anthropic", anthropic.__version__,
                     "the whole thinking block")
    result.credential_var, result.credential_fp = var, fingerprint
    client = anthropic.Anthropic(api_key=key, max_retries=0)
    log = chain.ToolLog()
    messages: list[dict] = [{"role": "user", "content": chain.QUESTION}]

    with C.Timer() as timer:
        try:
            for _ in range(MAX_TURNS):
                response = client.messages.create(
                    model=model, max_tokens=arm_anthropic.MAX_TOKENS,
                    system=chain.SYSTEM,
                    tools=[{"name": t["name"], "description": t["description"],
                            "input_schema": t["parameters"]}
                           for t in chain.TOOLS],
                    messages=messages,
                    extra_headers={"anthropic-beta":
                                   arm_anthropic.INTERLEAVED_BETA},
                    **{"thinking": {"type": "enabled",
                                    "budget_tokens":
                                        arm_anthropic.THINKING_BUDGET}})
                result.turns += 1
                result.input_tokens += response.usage.input_tokens
                result.output_tokens += response.usage.output_tokens

                blocks = [b.model_dump(exclude_none=True)
                          for b in response.content]
                if any(b.get("type") in arm_anthropic.OPAQUE_BLOCKS
                       and b.get(arm_anthropic.OPAQUE_BLOCKS[b["type"]])
                       for b in blocks):
                    result.state_turns += 1
                    result.state_turn_indices.append(result.turns - 1)

                # THE TREATMENT. The whole reasoning block goes, not the field
                # on it — which is what an adapter that rebuilds the assistant
                # message from role, content and tool calls does by omission.
                kept = [b for b in blocks
                        if b.get("type") not in arm_anthropic.OPAQUE_BLOCKS]
                result.request_shapes.append(
                    C.SHAPE_ALL_ABSENT if len(kept) != len(blocks)
                    else C.SHAPE_NO_STATE_YET)
                result.last_request_shape = result.request_shapes[-1]
                if len(kept) != len(blocks):
                    result.treatment_applied = True
                messages.append(json.loads(json.dumps(
                    {"role": "assistant", "content": kept})))

                uses = [b for b in kept if b.get("type") == "tool_use"]
                if not uses:
                    result.final_text = "".join(
                        b.get("text") or "" for b in kept
                        if b.get("type") == "text")
                    break
                messages.append({"role": "user", "content": [
                    {"type": "tool_result", "tool_use_id": use["id"],
                     "content": json.dumps(
                         log.dispatch(use["name"], dict(use.get("input") or {})))}
                    for use in uses]})
            result.provider_errored = False
            result.ok = True
        except anthropic.APIStatusError as exc:
            result.provider_errored = True
            result.error_status = exc.status_code
            result.error_kind = ("environmental"
                                 if exc.status_code in (401, 403, 429)
                                 else "capability")
            result.error = f"{type(exc).__name__} {exc.status_code}: {str(exc)[:600]}"
            result.ok = True
        except Exception as exc:  # noqa: BLE001
            result.error_kind = "harness"
            result.error = f"{type(exc).__name__}: {str(exc)[:600]}"
    result.elapsed_s = timer.elapsed
    return _finish(result, log)


def run_openai() -> int:
    import openai

    import arm_openai

    key, var, fingerprint = credentials.key_for("openai")
    model = arm_openai.DEFAULT_MODEL
    result = _record("openai", model, "openai", openai.__version__,
                     "the whole reasoning item")
    result.credential_var, result.credential_fp = var, fingerprint
    client = openai.OpenAI(api_key=key, max_retries=0)
    log = chain.ToolLog()
    conversation: list = [{"role": "user", "content": chain.QUESTION}]

    with C.Timer() as timer:
        try:
            for _ in range(MAX_TURNS):
                response = client.responses.create(
                    model=model, instructions=chain.SYSTEM,
                    input=list(conversation),
                    tools=[{"type": "function", "name": t["name"],
                            "description": t["description"],
                            "parameters": t["parameters"]}
                           for t in chain.TOOLS],
                    store=False, include=["reasoning.encrypted_content"],
                    reasoning={"effort": arm_openai.EFFORT})
                result.turns += 1
                if response.usage:
                    result.input_tokens += response.usage.input_tokens
                    result.output_tokens += response.usage.output_tokens

                items = [it.model_dump(exclude_none=True)
                         for it in response.output]
                if any(it.get("type") == "reasoning"
                       and it.get("encrypted_content") for it in items):
                    result.state_turns += 1
                    result.state_turn_indices.append(result.turns - 1)

                # THE TREATMENT. Every reasoning item is dropped outright,
                # which is the condition the vendor's own error language is
                # about — the twelve cells removed only the field on it.
                kept = [it for it in items if it.get("type") != "reasoning"]
                result.request_shapes.append(
                    C.SHAPE_ALL_ABSENT if len(kept) != len(items)
                    else C.SHAPE_NO_STATE_YET)
                result.last_request_shape = result.request_shapes[-1]
                if len(kept) != len(items):
                    result.treatment_applied = True
                conversation.extend(json.loads(json.dumps(kept)))

                calls = [it for it in kept if it.get("type") == "function_call"]
                if not calls:
                    result.final_text = "".join(
                        piece.get("text") or ""
                        for it in kept if it.get("type") == "message"
                        for piece in it.get("content") or ()
                        if piece.get("type") == "output_text")
                    break
                for call in calls:
                    out = log.dispatch(call["name"],
                                       json.loads(call.get("arguments") or "{}"))
                    conversation.append({"type": "function_call_output",
                                         "call_id": call["call_id"],
                                         "output": json.dumps(out)})
            result.provider_errored = False
            result.ok = True
        except openai.APIStatusError as exc:
            result.provider_errored = True
            result.error_status = exc.status_code
            result.error_kind = ("environmental"
                                 if exc.status_code in (401, 403, 429)
                                 else "capability")
            result.error = f"{type(exc).__name__} {exc.status_code}: {str(exc)[:600]}"
            result.ok = True
        except Exception as exc:  # noqa: BLE001
            result.error_kind = "harness"
            result.error = f"{type(exc).__name__}: {str(exc)[:600]}"
    result.elapsed_s = timer.elapsed
    return _finish(result, log)


def main() -> int:
    if "--provider" not in sys.argv:
        raise SystemExit("--provider anthropic|openai is required")
    provider = sys.argv[sys.argv.index("--provider") + 1]
    over = C.ledger_exceeded()
    if over is not None:
        print(json.dumps({"verdict": "CEILING", "reason": over}, indent=2))
        return 3
    if provider == "anthropic":
        return run_anthropic()
    if provider == "openai":
        return run_openai()
    raise SystemExit(f"no supplementary arm for {provider!r}")


if __name__ == "__main__":
    sys.exit(main())
