"""T057 — one internal tool call, four wire formats, both directions.

The arms that matter are the two asymmetries, because they are the two a
translation layer gets wrong in a way no output assertion sees.

**Arguments are a JSON string on OpenAI and xAI and a mapping on Anthropic and
Google.** Forwarding the wrong one hands the tool a single argument whose value
is the string `'{"order_id": "ORD-7731"}'` under a key it does not have. The
tool then reports a missing argument, the model apologises and retries, and the
session burns turns on a translation fault that looks like a model failure.

**Google's calls have no identity.** Every other provider returns an id;
Google's function *response* is matched back by **name**. So the internal
`call_id` — which `dispatch` requires and which the journal's idempotency key is
derived from — is synthesized, and two calls to one tool name in a single turn
cannot be told apart. That is refused rather than paired by position.

And a driver-level arm each: the per-model capability branch finding 016 result
9 makes mandatory, and the round trip of a whole turn through parse and rebuild.
"""

from __future__ import annotations

import json

import pytest

from src.runtime.dispatch import ToolCall, ToolResult
from src.runtime.providers import (
    ANTHROPIC, GOOGLE, OPENAI, PROVIDERS, XAI, driver_for,
)
from src.runtime.providers.base import UnknownProviderError
from src.runtime.providers.schema import (
    GOOGLE_SYNTHETIC_PREFIX,
    GoogleAmbiguousCallError,
    ToolSchema,
    ToolSchemaError,
    calls_from_wire,
    results_to_wire,
    tools_to_wire,
)

TOOL = ToolSchema(name="get_order_total",
                  description="Return the total in USD for an order id.",
                  parameters={"type": "object",
                              "properties": {"order_id": {"type": "string"}},
                              "required": ["order_id"]})

ARGS = {"order_id": "ORD-7731"}

#: One turn per provider, in that provider's own response shape. Transcribed
#: from the four arms of the finding 016 harness, which drove the live APIs.
RESPONSES = {
    ANTHROPIC: {"content": [
        {"type": "text", "text": "looking it up"},
        {"type": "tool_use", "id": "toolu_1", "name": TOOL.name,
         "input": ARGS}]},
    OPENAI: {"output": [
        {"type": "reasoning", "id": "rs_1", "summary": []},
        {"type": "function_call", "id": "fc_1", "call_id": "call_1",
         "name": TOOL.name, "arguments": json.dumps(ARGS)}]},
    GOOGLE: {"candidates": [{"content": {"role": "model", "parts": [
        {"text": "looking it up"},
        {"function_call": {"name": TOOL.name, "args": ARGS}}]}}]},
    XAI: {"choices": [{"message": {
        "role": "assistant", "content": "",
        "tool_calls": [{"id": "call_1", "type": "function",
                        "function": {"name": TOOL.name,
                                     "arguments": json.dumps(ARGS)}}]}}]},
}


# ---------------------------------------------------------------------------
# Declarations, out.


@pytest.mark.parametrize("provider", PROVIDERS)
def test_every_provider_gets_the_schema_under_the_key_it_reads(provider):
    """The four shapes differ in nesting as well as in field name.

    Asserted per provider rather than through a shared normalizer, because a
    normalizer is the thing that would make all four agree by rewriting one of
    them into a shape its provider rejects.
    """
    wire = tools_to_wire(provider, [TOOL])
    flat = json.dumps(wire)
    assert TOOL.name in flat and TOOL.description in flat
    if provider == ANTHROPIC:
        assert wire[0]["input_schema"] == TOOL.parameters
        assert "parameters" not in wire[0]
    elif provider == OPENAI:
        assert wire[0]["type"] == "function"
        assert wire[0]["parameters"] == TOOL.parameters
        assert "function" not in wire[0], (
            "the flat Responses shape, not Chat Completions' nested one")
    elif provider == GOOGLE:
        assert wire[0]["function_declarations"][0]["parameters"] == (
            TOOL.parameters)
    else:
        assert wire[0]["function"]["parameters"] == TOOL.parameters


def test_a_tool_with_no_description_is_refused():
    """It is the only thing the model has to choose the tool by."""
    with pytest.raises(ToolSchemaError, match="no description"):
        ToolSchema(name="x", description="", parameters={})


# ---------------------------------------------------------------------------
# Calls, in — and the argument asymmetry.


@pytest.mark.parametrize("provider", PROVIDERS)
def test_arguments_reach_the_tool_as_a_mapping_whatever_the_wire_said(provider):
    calls = calls_from_wire(provider, RESPONSES[provider])
    assert len(calls) == 1
    assert calls[0].name == TOOL.name
    assert calls[0].arguments == ARGS, (
        f"{provider}: the arguments did not decode to a mapping. On this "
        "provider that means the tool receives a JSON string under no key it "
        "has, and reports a missing argument rather than a translation fault.")
    assert calls[0].index == 0


@pytest.mark.parametrize("provider", (OPENAI, XAI))
def test_a_mapping_where_this_provider_sends_a_string_is_refused(provider):
    """The confusion, planted from the other side.

    A payload from the wrong provider's shape decoding *successfully* is worse
    than one that raises: it produces a plausible call that the wrong endpoint
    then rejects, several layers away from the mistake.
    """
    payload = json.loads(json.dumps(RESPONSES[provider]))
    if provider == OPENAI:
        payload["output"][1]["arguments"] = ARGS
    else:
        payload["choices"][0]["message"]["tool_calls"][0]["function"][
            "arguments"] = ARGS
    with pytest.raises(ToolSchemaError, match="as a mapping"):
        calls_from_wire(provider, payload)


@pytest.mark.parametrize("provider", (ANTHROPIC, GOOGLE))
def test_a_string_where_this_provider_sends_a_mapping_is_refused(provider):
    payload = json.loads(json.dumps(RESPONSES[provider]))
    if provider == ANTHROPIC:
        payload["content"][1]["input"] = json.dumps(ARGS)
    else:
        payload["candidates"][0]["content"]["parts"][1]["function_call"][
            "args"] = json.dumps(ARGS)
    with pytest.raises(ToolSchemaError, match="as a string"):
        calls_from_wire(provider, payload)


def test_the_declared_index_counts_tool_calls_and_not_content_blocks():
    """`dispatch` requires the indexes dense over `0..n-1`.

    Every provider interleaves the calls with something that is not one — text,
    reasoning, a thought part — so a position in the content list is sparse by
    construction and `dispatch` would refuse the fan-out.
    """
    payload = {"content": [
        {"type": "thinking", "signature": "S"},
        {"type": "tool_use", "id": "a", "name": "one", "input": {}},
        {"type": "text", "text": "and"},
        {"type": "tool_use", "id": "b", "name": "two", "input": {}}]}
    assert [c.index for c in calls_from_wire(ANTHROPIC, payload)] == [0, 1]


@pytest.mark.parametrize("provider", (ANTHROPIC, OPENAI, XAI))
def test_a_call_with_no_id_is_refused_on_the_providers_that_send_one(provider):
    """The journal's idempotency key is derived from it."""
    payload = json.loads(json.dumps(RESPONSES[provider]))
    if provider == ANTHROPIC:
        payload["content"][1]["id"] = ""
    elif provider == OPENAI:
        payload["output"][1]["call_id"] = None
    else:
        payload["choices"][0]["message"]["tool_calls"][0]["id"] = ""
    with pytest.raises(ToolSchemaError, match="no id"):
        calls_from_wire(provider, payload)


# ---------------------------------------------------------------------------
# Google's missing identity.


def test_google_calls_get_a_synthesized_id_that_carries_the_name():
    """Because the *response* is matched back by name and nothing else."""
    call = calls_from_wire(GOOGLE, RESPONSES[GOOGLE])[0]
    assert call.call_id.startswith(GOOGLE_SYNTHETIC_PREFIX)
    assert call.call_id.endswith(TOOL.name)
    result = results_to_wire(GOOGLE, [_result(call)])
    assert result[0]["parts"][0]["function_response"]["name"] == TOOL.name


def test_a_google_call_that_does_carry_an_id_uses_it():
    """Newer Gemini populates `FunctionCall.id`. Where it does, the synthesis
    is not used and the ambiguity below does not arise."""
    payload = json.loads(json.dumps(RESPONSES[GOOGLE]))
    payload["candidates"][0]["content"]["parts"][1]["function_call"]["id"] = (
        "fc-real-1")
    call = calls_from_wire(GOOGLE, payload)[0]
    assert call.call_id == "fc-real-1"
    assert not call.call_id.startswith(GOOGLE_SYNTHETIC_PREFIX)


def test_two_google_calls_to_one_name_are_refused_rather_than_paired():
    """The ambiguity is in the wire format and cannot be closed on our side.

    Google matches a function response by name, so two responses under one name
    are indistinguishable **to the provider** however carefully we order them
    locally. Guessing would attribute one call's result to the other's and the
    model would answer confidently from the wrong row.
    """
    payload = {"candidates": [{"content": {"parts": [
        {"function_call": {"name": "get_order_total",
                           "args": {"order_id": "ORD-1"}}},
        {"function_call": {"name": "get_order_total",
                           "args": {"order_id": "ORD-2"}}}]}}]}
    with pytest.raises(GoogleAmbiguousCallError, match="matches a function response by"):
        calls_from_wire(GOOGLE, payload)

    # Two calls to **different** names are fine, so the refusal above is about
    # the ambiguity rather than about parallel calls.
    payload["candidates"][0]["content"]["parts"][1]["function_call"]["name"] = (
        "get_order_lines")
    assert len(calls_from_wire(GOOGLE, payload)) == 2


# ---------------------------------------------------------------------------
# Results, out.


def _result(call: ToolCall) -> ToolResult:
    return ToolResult(call=call, outcome="ok",
                      body=json.dumps({"total_usd": 149.99}),
                      started_at=0.0, finished_at=0.0)


@pytest.mark.parametrize("provider", PROVIDERS)
def test_a_result_goes_back_under_the_identity_the_provider_will_match(provider):
    call = calls_from_wire(provider, RESPONSES[provider])[0]
    wire = results_to_wire(provider, [_result(call)])
    if provider == ANTHROPIC:
        assert wire[0]["role"] == "user"
        assert wire[0]["content"][0]["tool_use_id"] == call.call_id
    elif provider == OPENAI:
        assert wire[0]["type"] == "function_call_output"
        assert wire[0]["call_id"] == call.call_id
    elif provider == GOOGLE:
        assert wire[0]["role"] == "user"
        response = wire[0]["parts"][0]["function_response"]
        # An object, not a string: Google's field is a struct.
        assert response["response"] == {"total_usd": 149.99}
        assert response["name"] == TOOL.name
    else:
        assert wire[0]["role"] == "tool"
        assert wire[0]["tool_call_id"] == call.call_id


def test_a_google_result_that_is_not_json_is_wrapped_rather_than_refused():
    """Google's `response` field is typed as a struct, so a bare string needs a
    key. Inventing one is visible in the request; refusing would end a session
    over a tool that returned plain text."""
    call = calls_from_wire(GOOGLE, RESPONSES[GOOGLE])[0]
    plain = ToolResult(call=call, outcome="ok", body="not json at all",
                       started_at=0.0, finished_at=0.0)
    wire = results_to_wire(GOOGLE, [plain])
    assert wire[0]["parts"][0]["function_response"]["response"] == {
        "result": "not json at all"}


def test_an_empty_result_set_produces_no_message_on_the_wrapping_providers():
    """Anthropic and Google wrap results in a turn. An empty turn is a turn the
    provider rejects, so there must not be one."""
    for provider in (ANTHROPIC, GOOGLE):
        assert results_to_wire(provider, []) == []


# ---------------------------------------------------------------------------
# The driver interface.


def test_an_unknown_provider_is_refused_at_lookup_and_not_at_the_model_call():
    with pytest.raises(UnknownProviderError, match="not one of"):
        driver_for("mistral")


@pytest.mark.parametrize("provider", PROVIDERS)
def test_every_declared_provider_has_a_driver_that_names_itself(provider):
    driver = driver_for(provider)
    assert driver.provider == provider
    assert driver.sdk_module


def test_the_anthropic_request_shape_branches_on_the_model_and_not_the_vendor():
    """Finding 016 result 9, as a fixture.

    `claude-sonnet-5` rejects `thinking={"type":"enabled","budget_tokens":N}`
    with HTTP 400 — *"Use 'thinking.type.adaptive' and 'output_config.effort'"*
    — and `claude-sonnet-4-5-20250929` accepts exactly that shape. One vendor,
    two incompatible bodies. A driver that is one function per provider sends
    one of these models a request it 400s on, and the failure arrives as a
    provider outage rather than as a translation fault.
    """
    driver = driver_for(ANTHROPIC)
    adaptive = driver.capabilities("claude-sonnet-5").thinking_request
    enabled = driver.capabilities("claude-sonnet-4-5-20250929").thinking_request

    assert adaptive["thinking"] == {"type": "adaptive"}
    assert adaptive["output_config"] == {"effort": "high"}
    assert enabled["thinking"]["type"] == "enabled"
    assert "budget_tokens" in enabled["thinking"]
    assert adaptive != enabled, (
        "the two models take the same request shape here, so this driver has "
        "no per-model branch and one of them is being sent a body finding 016 "
        "measured a 400 on")


@pytest.mark.parametrize("provider,keys", [
    (OPENAI, ("store", "include")),
    (XAI, ("use_encrypted_content",)),
    (GOOGLE, ("automatic_function_calling",)),
])
def test_the_opt_ins_that_are_the_difference_between_state_and_none(provider, keys):
    """Two providers return no opaque state at all unless asked, and neither
    errors. A driver that forgot would produce a session with no state and no
    signal, and every conformance arm would report the absence as a property of
    the model."""
    capabilities = driver_for(provider).capabilities("m")
    for key in keys:
        assert key in capabilities.opt_in
    request = driver_for(provider).build_request(
        model="m", system="s", turns=[], tools=[TOOL])
    flat = json.dumps(request, default=str)
    for key in keys:
        assert key in flat, (
            f"{provider} declares {key} in its capabilities and does not put "
            "it in the request, which is the same as not having it")


def test_the_transport_half_says_what_is_missing_rather_than_importing():
    """`call` is not exercised by any cassette and says so at the call site."""
    from src.runtime.providers.base import TransportUnavailableError

    with pytest.raises(TransportUnavailableError, match="pinned dependency"):
        driver_for(ANTHROPIC).call({"model": "m"})
