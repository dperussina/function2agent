"""SPIKE - E18. One loop, four providers, one treatment. Do not import from product code.

**Rule 3 of the [`experiment-design`](../../../../.cursor/skills/experiment-design/SKILL.md)
skill is why this file exists rather than four arms with four copies of the same
loop in them**: *"hold the harness fixed — it swings 10–20 points."* Twelve cells
whose only intended difference is provider and condition cannot afford a
fifth-copy divergence in when a state is withheld, how a request is rebuilt, or
what counts as an error. So the journal, the rebuild, the shape classification,
the token ceiling and the error handling live here, and each arm supplies only
the four or five things that are genuinely the vendor's.

**There is no retry anywhere.** `max_retries=0` on every client that offers it,
and the first provider error ends the arm. Conditions B and C error *by design*,
so a retry loop on a 400 is the failure mode that spends a budget without
producing a reading — [finding 030](../../findings/030-provider-state-chain-derived-not-measured.md)
§6 names it specifically.

## The journal

`[(kind, body)]` where `kind` is `"user"`, `"tool"` or `"assistant"`. Assistant
entries are `PersistedTurn`s whose opaque leaves have been deleted and whose
bodies have been through `json.dumps`. **Every request is rebuilt from the
journal**, states written back or withheld according to the condition. Nothing
is mutated in place and no request shares a dict with a previous one, which is
the second of the two aliasing blindnesses
[`test_provider_state_roundtrip.py`](../../../../tests/conformance/test_provider_state_roundtrip.py)
had to be repaired for — the first repair sanitised once and the objects were
then reused across iterations.
"""
from __future__ import annotations

import json
import sys
import time
from typing import Any, Protocol, Sequence

import chain
import conditions as C


class Adapter(Protocol):
    """What a provider has to supply. Everything else is in `run`."""

    provider: str
    sdk: str
    sdk_version: str
    opaque_field: str
    model: str

    def flatten(self, kind: str, body: Any) -> list[Any]:
        """One journal body as the entries a request carries for it."""

    def send(self, entries: Sequence[Any]) -> Any:
        """One request. Raises the vendor's own exception types."""

    def assistant(self, response: Any) -> tuple[dict, list[list]]:
        """The assistant turn as a JSON body, and where its opaque leaves sit."""

    def usage(self, response: Any) -> tuple[int, int, float | None]:
        """(input tokens, output tokens, provider-reported cost or None)."""

    def tool_calls(self, body: dict) -> list[tuple[str, str, dict]]:
        """[(call id, tool name, arguments)] on an assistant body."""

    def tool_entry(self, results: list[tuple[str, str, dict]]) -> Any:
        """[(call id, tool name, output)] as the journal body that answers them."""

    def text(self, body: dict) -> str:
        """The assistant turn's plain text."""

    def classify(self, exc: BaseException) -> tuple[int | None, str] | None:
        """(status, "environmental"|"capability") for a provider error, else None."""


def run(adapter: Adapter, condition: str, first_user: Any) -> C.ArmResult:
    """Drive `chain`'s six turns under one condition and return the cell."""
    res = C.ArmResult(
        provider=adapter.provider, condition=condition, sdk=adapter.sdk,
        sdk_version=adapter.sdk_version, model=adapter.model,
        opaque_field=adapter.opaque_field)
    if condition == C.DROP_ONE:
        res.withheld_ordinal = C.DROP_ORDINAL

    log = chain.ToolLog()
    journal: list[tuple[str, Any]] = [("user", first_user)]
    started = time.time()

    try:
        for _ in range(C.MAX_TURNS):
            entries: list[Any] = []
            present: list[bool] = []
            ordinal = 0
            for kind, body in journal:
                if kind != "assistant":
                    entries.extend(adapter.flatten(kind, body))
                    continue
                carry = body.carried_state and C.carries(condition, ordinal)
                rebuilt, written = C.rebuild(body, carry=carry)
                entries.extend(adapter.flatten(kind, rebuilt))
                if body.carried_state:
                    present.append(carry)
                    res.digests_reinjected.extend(written)
                    ordinal += 1

            shape = C.shape_of(present)
            res.request_shapes.append(shape)
            res.last_request_shape = shape
            if shape in (C.SHAPE_TRAILING_GAP, C.SHAPE_INTERIOR_HOLE,
                         C.SHAPE_ALL_ABSENT):
                res.treatment_applied = True

            response = adapter.send(entries)
            res.turns += 1
            got_in, got_out, cost = adapter.usage(response)
            res.input_tokens += got_in
            res.output_tokens += got_out
            if cost is not None:
                res.cost_usd_reported_by_provider = (
                    res.cost_usd_reported_by_provider or 0.0) + cost

            body, paths = adapter.assistant(response)
            persisted = C.persist(body, paths)
            if persisted.carried_state:
                res.state_turns += 1
                res.state_turn_indices.append(res.turns - 1)
                res.digests_emitted.extend(
                    C.digest(carrier) for _p, carrier, _t in persisted.slots)
            journal.append(("assistant", persisted))

            calls = adapter.tool_calls(persisted.body)
            if not calls:
                res.final_text = adapter.text(persisted.body)
                break

            results = [(call_id, name, log.dispatch(name, args))
                       for call_id, name, args in calls]
            journal.append(("tool", adapter.tool_entry(results)))

            if res.input_tokens > C.MAX_INPUT_TOKENS:
                res.note(f"stopped at the per-arm {C.MAX_INPUT_TOKENS} "
                         "input-token ceiling")
                break
        res.provider_errored = False
        res.ok = True
    except Exception as exc:  # noqa: BLE001 - every vendor raises its own types
        classified = adapter.classify(exc)
        if classified is None:
            res.error_kind = "harness"
            res.error = f"{type(exc).__name__}: {str(exc)[:600]}"
        else:
            status, kind = classified
            res.provider_errored = True
            res.error_status = status
            res.error_kind = kind
            res.error = f"{type(exc).__name__} {status}: {str(exc)[:600]}"
            res.ok = True

    res.elapsed_s = time.time() - started
    res.tool_calls = log.names
    res.hops_linked = log.hops_linked()
    res.chained = log.chained()
    res.answer_correct = chain.answer_correct(res.final_text)
    if condition != C.FULL and res.state_turns == 0:
        res.note("the model emitted no opaque state, so nothing was withheld "
                 "and this arm measures nothing about a miss")
    if (condition == C.DROP_ONE and res.provider_errored is False
            and 0 < res.state_turns <= C.DROP_ORDINAL):
        res.note(f"only {res.state_turns} assistant turn(s) carried opaque "
                 "state, so a chain with a hole in it cannot be built on this "
                 "provider for this chain — drop-one and drop-all coincide")
    elif condition != C.FULL and res.state_turns and not res.treatment_applied:
        res.note("state was emitted but the arm ended before a request "
                 "carrying the gap was sent")
    # Scored here rather than at print time, so that a caller reading the
    # record programmatically sees the same verdict a committed artifact does.
    res.score()
    return res


def json_args(raw: Any) -> dict:
    """Arguments as a mapping, whichever of the two shapes the vendor used."""
    if isinstance(raw, dict):
        return dict(raw)
    try:
        return json.loads(raw or "{}")
    except (TypeError, ValueError):
        return {}


def main(adapter_factory, default_model: str) -> int:
    """Shared entry point: parse the two flags, resolve one key, run, print."""
    condition = C.condition_arg(sys.argv)
    model = C.model_arg(sys.argv, default_model)
    over = C.ledger_exceeded()
    if over is not None:
        print(json.dumps({"verdict": "CEILING", "condition": condition,
                          "model": model, "reason": over}, indent=2))
        return 3
    adapter, var, fingerprint = adapter_factory(model)
    result = run(adapter, condition, first_user=adapter.first_user())
    result.credential_var, result.credential_fp = var, fingerprint
    C.ledger_add(result)
    return C.emit(result)
