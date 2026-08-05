"""T057 — one internal tool-call representation, four wire formats, both directions.

The internal representation is `src.runtime.dispatch.ToolCall`, unchanged. It is
not redefined here: `dispatch` owns the declared-index ordering FR-007 rests on,
and a second call type would be a second chance for a translation to renumber
what the provider declared.

## The two asymmetries that make this a translation rather than a rename

**Arguments are a JSON string on two providers and a mapping on two.** OpenAI's
`function_call.arguments` and xAI's `tool_calls[].function.arguments` arrive as
text that has to be parsed; Anthropic's `tool_use.input` and Google's
`function_call.args` arrive already structured. A driver that forwards the wrong
one produces a tool call whose arguments are the *string* `'{"order_id": ...}'`
under a key the tool does not have, and the tool reports a missing argument
rather than a translation fault.

**Google's function calls have no identity of their own.** Anthropic returns
`tool_use.id`, OpenAI `function_call.call_id`, xAI `tool_calls[].id`. Google
returns a `Part` with a name and arguments, and a function *response* is matched
back **by name** — `Part.from_function_response(name=..., response=...)`. So the
internal `call_id`, which `dispatch` requires and which the journal's idempotency
key is derived from, has to be synthesized for Google and mapped back on the way
out.

That synthesis has a hole, and this module **refuses** rather than papering over
it: two calls to the *same tool name* in one Google turn cannot be told apart on
the way back, because the response carries only the name. A driver that guessed
would attribute one call's result to the other's, and the model would answer
confidently from the wrong row. `GoogleAmbiguousCallError` names it. Google's
newer `FunctionCall.id` closes the hole where a model populates it, so the
synthesis is used only when it is absent.

## What "both directions" covers here

Tool *declarations* out, tool *calls* in, tool *results* out. Not streaming, not
parallel-call wire quirks beyond ordering, not the vendor error taxonomies —
those sit with the transport half and are named in `base.py` as unexercised.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from src.runtime.dispatch import ToolCall, ToolResult

# Imported for the names only; `base` imports this module, so the constants are
# defined here and re-exported there rather than the other way round.
ANTHROPIC = "anthropic"
OPENAI = "openai"
GOOGLE = "google"
XAI = "xai"


class ToolSchemaError(RuntimeError):
    """A tool shape that cannot be translated as described."""


class GoogleAmbiguousCallError(ToolSchemaError):
    """Two identically named Google calls in one turn, neither carrying an id.

    Refused rather than resolved by position. Google matches a function
    *response* by name, so two responses under one name are indistinguishable to
    the provider however carefully we order them locally — the ambiguity is in
    the wire format and cannot be closed on our side.
    """


@dataclass(frozen=True)
class ToolSchema:
    """One tool, in the one shape the four wire formats are derived from.

    `parameters` is JSON Schema, which is the intersection all four accept. It
    is not validated here: a schema this layer rewrote would be a schema the
    provider was not given, and FR-053's fixture discipline puts the check in a
    test rather than in a silent normalizer.
    """

    name: str
    description: str
    parameters: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name:
            raise ToolSchemaError("a tool needs a name")
        if not self.description:
            raise ToolSchemaError(
                f"{self.name!r} has no description. Every provider passes it "
                "to the model verbatim and it is the only thing the model has "
                "to choose the tool by."
            )


# ---------------------------------------------------------------------------
# Declarations, out.


def tools_to_wire(provider: str, tools: Sequence[ToolSchema]) -> Any:
    """The tool list in one provider's own declaration shape."""
    if provider == ANTHROPIC:
        return [
            {"name": t.name, "description": t.description,
             "input_schema": dict(t.parameters)}
            for t in tools
        ]
    if provider == OPENAI:
        # The Responses API's flat form, which is what finding 016's arm drove.
        # Chat Completions nests the same three keys under "function"; they are
        # different endpoints and this driver targets Responses, because that is
        # where `store=False` plus `include=[...]` puts the opaque round-trip in
        # our hands rather than the provider's.
        return [
            {"type": "function", "name": t.name,
             "description": t.description, "parameters": dict(t.parameters)}
            for t in tools
        ]
    if provider == GOOGLE:
        return [{
            "function_declarations": [
                {"name": t.name, "description": t.description,
                 "parameters": dict(t.parameters)}
                for t in tools
            ]
        }]
    if provider == XAI:
        return [
            {"type": "function",
             "function": {"name": t.name, "description": t.description,
                          "parameters": dict(t.parameters)}}
            for t in tools
        ]
    raise ToolSchemaError(f"no tool declaration shape for {provider!r}")


# ---------------------------------------------------------------------------
# Calls, in.


def calls_from_wire(
    provider: str, payload: Mapping[str, Any]
) -> tuple[ToolCall, ...]:
    """Every tool call in one response, in the provider's declared order.

    The index is the call's position **among the tool calls of this turn**, not
    its position in the content list. `dispatch` requires the indexes dense over
    `0..n-1`, and a content list interleaves text and reasoning blocks that are
    not calls.
    """
    if provider == ANTHROPIC:
        return _anthropic_calls(payload)
    if provider == OPENAI:
        return _openai_calls(payload)
    if provider == GOOGLE:
        return _google_calls(payload)
    if provider == XAI:
        return _xai_calls(payload)
    raise ToolSchemaError(f"no call shape for {provider!r}")


def _anthropic_calls(payload: Mapping[str, Any]) -> tuple[ToolCall, ...]:
    out: list[ToolCall] = []
    for block in payload.get("content") or ():
        if block.get("type") != "tool_use":
            continue
        out.append(ToolCall(
            index=len(out),
            call_id=_require_id(ANTHROPIC, block.get("id")),
            name=block.get("name") or "",
            # A mapping already. Passing it through `json.loads` would raise on
            # the shape this provider actually sends.
            arguments=_require_mapping(ANTHROPIC, block.get("input")),
        ))
    return tuple(out)


def _openai_calls(payload: Mapping[str, Any]) -> tuple[ToolCall, ...]:
    out: list[ToolCall] = []
    for item in payload.get("output") or ():
        if item.get("type") != "function_call":
            continue
        out.append(ToolCall(
            index=len(out),
            call_id=_require_id(OPENAI, item.get("call_id")),
            name=item.get("name") or "",
            arguments=_decode_arguments(OPENAI, item.get("arguments")),
        ))
    return tuple(out)


def _google_calls(payload: Mapping[str, Any]) -> tuple[ToolCall, ...]:
    candidates = payload.get("candidates") or ()
    if not candidates:
        return ()
    parts = (candidates[0].get("content") or {}).get("parts") or ()
    out: list[ToolCall] = []
    synthesized: dict[str, int] = {}
    for position, part in enumerate(parts):
        call = part.get("function_call")
        if not call:
            continue
        name = call.get("name") or ""
        given = call.get("id")
        if given:
            call_id = str(given)
        else:
            # No id on the wire. Synthesize one that is stable within the turn
            # and carries the name, because the name is what the *response* is
            # matched by and the mapping back has to be recoverable from the id
            # alone.
            seen = synthesized.get(name, 0)
            if seen:
                raise GoogleAmbiguousCallError(
                    f"this turn calls {name!r} {seen + 1} times and no call "
                    "carries an id. Google matches a function response by "
                    "name, so two results under one name cannot be attributed "
                    "— by us or by the provider. Refused rather than paired by "
                    "position, which would answer confidently from the wrong "
                    "row."
                )
            synthesized[name] = seen + 1
            call_id = f"{GOOGLE_SYNTHETIC_PREFIX}{position}:{name}"
        out.append(ToolCall(
            index=len(out), call_id=call_id, name=name,
            arguments=_require_mapping(GOOGLE, call.get("args")),
        ))
    return tuple(out)


def _xai_calls(payload: Mapping[str, Any]) -> tuple[ToolCall, ...]:
    choices = payload.get("choices") or ()
    if not choices:
        return ()
    message = choices[0].get("message") or {}
    out: list[ToolCall] = []
    for call in message.get("tool_calls") or ():
        function = call.get("function") or {}
        out.append(ToolCall(
            index=len(out),
            call_id=_require_id(XAI, call.get("id")),
            name=function.get("name") or "",
            arguments=_decode_arguments(XAI, function.get("arguments")),
        ))
    return tuple(out)


#: The marker that says a Google call id is ours rather than the provider's.
#: Named so that `results_to_wire` can recover the tool name from it without
#: needing the call list handed back in.
GOOGLE_SYNTHETIC_PREFIX = "g#"


# ---------------------------------------------------------------------------
# Results, out.


def results_to_wire(
    provider: str, results: Sequence[ToolResult]
) -> list[dict[str, Any]]:
    """The turn's tool results in the shape the next request needs.

    One list per provider, appended to the conversation by the caller. The
    shapes differ in *role* as well as in field names — Anthropic and Google put
    results in a `user` turn, OpenAI puts them in the flat input list, xAI uses
    a `tool` role — which is why this returns whole messages rather than
    fragments a caller would have to wrap correctly four different ways.
    """
    if provider == ANTHROPIC:
        return [{
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": r.call.call_id,
                 "content": _encode_body(r.body)}
                for r in results
            ],
        }] if results else []
    if provider == OPENAI:
        return [
            {"type": "function_call_output", "call_id": r.call.call_id,
             "output": _encode_body(r.body)}
            for r in results
        ]
    if provider == GOOGLE:
        return [{
            "role": "user",
            "parts": [
                {"function_response": {
                    "name": _google_response_name(r.call.call_id, r.call.name),
                    "response": _decode_body(r.body),
                }}
                for r in results
            ],
        }] if results else []
    if provider == XAI:
        return [
            {"role": "tool", "tool_call_id": r.call.call_id,
             "content": _encode_body(r.body)}
            for r in results
        ]
    raise ToolSchemaError(f"no result shape for {provider!r}")


def _google_response_name(call_id: str, name: str) -> str:
    """The name Google matches a response by, recovered from the id.

    Reading it back out of the synthesized id rather than trusting the caller's
    `name` is what keeps the two from drifting: the id is what `dispatch`
    carried through the fan-out and the journal keyed the step on, so it is the
    field that survived every hop.
    """
    if call_id.startswith(GOOGLE_SYNTHETIC_PREFIX):
        _, _, tail = call_id.partition(":")
        return tail or name
    return name


# ---------------------------------------------------------------------------
# The two asymmetries, in one place each.


def _decode_arguments(provider: str, raw: Any) -> Mapping[str, Any]:
    """OpenAI and xAI send arguments as a JSON *string*."""
    if raw is None or raw == "":
        return {}
    if isinstance(raw, Mapping):
        raise ToolSchemaError(
            f"{provider} sent tool arguments as a mapping. This provider's "
            "wire format is a JSON string; a mapping here means the payload "
            "came from somewhere else and the two shapes are about to be "
            "confused."
        )
    if not isinstance(raw, str):
        raise ToolSchemaError(
            f"{provider} tool arguments arrived as {type(raw).__name__}")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ToolSchemaError(
            f"{provider} tool arguments are not JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ToolSchemaError(
            f"{provider} tool arguments decoded to "
            f"{type(parsed).__name__}, not an object")
    return parsed


def _require_mapping(provider: str, raw: Any) -> Mapping[str, Any]:
    """Anthropic and Google send arguments already structured."""
    if raw is None:
        return {}
    if isinstance(raw, str):
        raise ToolSchemaError(
            f"{provider} sent tool arguments as a string. This provider's wire "
            "format is an object; a string here would be parsed by a codec "
            "this provider's path does not have, and the arguments would reach "
            "the tool under no key at all."
        )
    if not isinstance(raw, Mapping):
        raise ToolSchemaError(
            f"{provider} tool arguments arrived as {type(raw).__name__}")
    return dict(raw)


def _encode_body(body: str) -> str:
    """A tool result as text, for the three providers that take text."""
    return body


def _decode_body(body: str) -> Mapping[str, Any]:
    """A tool result as an object, which is what Google's `response` field is.

    A body that is not a JSON object is wrapped rather than refused. Google's
    field is typed as a struct, so a bare string has to be given a key — and
    inventing `{"result": ...}` here is visible in the request, where refusing
    would end a session over a tool that returned plain text.
    """
    try:
        parsed = json.loads(body)
    except (json.JSONDecodeError, TypeError):
        return {"result": body}
    if isinstance(parsed, dict):
        return parsed
    return {"result": parsed}


def _require_id(provider: str, value: Any) -> str:
    if not value:
        raise ToolSchemaError(
            f"{provider} returned a tool call with no id. `dispatch` derives "
            "the journal's idempotency key from it, so a call without one "
            "cannot be recorded as having happened exactly once."
        )
    return str(value)
