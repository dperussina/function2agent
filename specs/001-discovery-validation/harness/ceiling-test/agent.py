"""SPIKE - E7 ceiling test. Delete after 2026-11-30. Do not import from product code.

One agent loop, shared by both arms. Everything except the capability set is held
constant here (FR-004): same model, same sampling, same system-prompt template, same
termination rules, same tool-result truncation, same `submit_answer` contract.

Standard library only, deliberately. A run must be reproducible by someone else from the
committed configuration (SC-005), and a dependency tree is the usual reason that fails.

No provider credential is ever printed, returned, or written to a trace. `envroot.py`
resolves one into a local variable, it is used as a request header, and nothing else.
`redact()` is a belt-and-braces pass over everything that gets recorded.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any, Callable

API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"

SYSTEM_TEMPLATE = """You are operating a self-hosted recipe manager called Mealie on behalf of an operator.

You will be given exactly one task. Work on it, then finish by calling `submit_answer` \
exactly once. Nothing you write outside that call is read by anyone.

`submit_answer` takes a status, and choosing the right one is part of the task:
  answered            - you determined the answer, or you made the change that was asked for
  needs_clarification - the request is ambiguous or missing information you would have to
                        guess at (for example it names a target that matches several things,
                        or omits a value you would have to invent)
  impossible          - this application has no such capability, field, or record, so the
                        task cannot be completed at all

Rules:
- Do not guess. A confident wrong answer is worse than reporting that you could not determine it.
- For a question, put the answer in `value` and nothing else: a bare number for a count or a
  total, the exact name for a single item, or a comma-separated list of exact names for several.
- For a change, make the change first, verify it, then submit with status `answered`.
- Change nothing the task did not ask you to change.
- Work from what the application actually contains. Do not rely on prior knowledge of what a
  recipe manager usually stores.

{capability_block}"""

SUBMIT_TOOL = {
    "name": "submit_answer",
    "description": (
        "Finish the task. Call this exactly once, as your last action. Choose `status` "
        "carefully: `answered` if you have the answer or made the change, "
        "`needs_clarification` if the request is ambiguous or incomplete, `impossible` if "
        "the application cannot do this at all."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "status": {
                "type": "string",
                "enum": ["answered", "needs_clarification", "impossible"],
                "description": "How the task ended.",
            },
            "value": {
                "type": "string",
                "description": (
                    "The answer itself, for a question: a bare number, an exact name, or a "
                    "comma-separated list of exact names. Empty string when status is not `answered`."
                ),
            },
            "note": {
                "type": "string",
                "description": "One sentence of context. Never scored; keep it short.",
            },
        },
        "required": ["status", "value"],
    },
}


# ---------------------------------------------------------------------------
# credentials
#
# Loading moved to envroot.py on 2026-08-02. The loader that lived here took a
# dotenv *file path*, which is why both callers carried one as a hardcoded
# module constant pointing into a private repository. Callers now name a tree
# and the harness exits rather than guessing.
# ---------------------------------------------------------------------------


def make_redactor(secret: str) -> Callable[[Any], Any]:
    def redact(obj):
        if isinstance(obj, str):
            return obj.replace(secret, "[REDACTED]") if secret and secret in obj else obj
        if isinstance(obj, dict):
            return {k: redact(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [redact(v) for v in obj]
        return obj

    return redact


# ---------------------------------------------------------------------------
# transport
# ---------------------------------------------------------------------------


class ModelError(RuntimeError):
    pass


def call_model(api_key: str, payload: dict, max_retries: int = 4) -> dict:
    data = json.dumps(payload).encode()
    headers = {
        "x-api-key": api_key,
        "anthropic-version": ANTHROPIC_VERSION,
        "content-type": "application/json",
    }
    delay = 2.0
    last = ""
    for attempt in range(max_retries):
        req = urllib.request.Request(API_URL, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            body = exc.read().decode()[:300]
            last = f"HTTP {exc.code}: {body}"
            if exc.code in (429, 500, 502, 503, 529) and attempt < max_retries - 1:
                time.sleep(delay)
                delay *= 2
                continue
            raise ModelError(last) from None
        except Exception as exc:  # noqa: BLE001
            last = f"{type(exc).__name__}: {exc}"
            if attempt < max_retries - 1:
                time.sleep(delay)
                delay *= 2
                continue
            raise ModelError(last) from None
    raise ModelError(last)


# ---------------------------------------------------------------------------
# the loop
# ---------------------------------------------------------------------------


def run_attempt(
    *,
    api_key: str,
    model_cfg: dict,
    pricing: dict,
    budget: dict,
    capability_block: str,
    tool_schemas: list[dict],
    tool_fns: dict[str, Callable[..., str]],
    task_prompt: str,
    truncation_chars: int,
    remaining_run_usd: float,
) -> dict:
    """Run one arm against one task. Returns a full run record (FR-002)."""
    redact = make_redactor(api_key)
    system = SYSTEM_TEMPLATE.format(capability_block=capability_block)
    tools = list(tool_schemas) + [SUBMIT_TOOL]
    messages: list[dict] = [{"role": "user", "content": task_prompt}]

    usage = {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0}
    transcript: list[dict] = []
    tool_calls: list[dict] = []
    turns = 0
    submission: dict | None = None
    terminal = "unknown"
    nudges = 0
    started = time.time()

    def cost() -> float:
        p = pricing
        return (
            usage["input"] * p["input"]
            + usage["output"] * p["output"]
            + usage["cache_read"] * p["cache_read"]
            + usage["cache_write"] * p["cache_write"]
        ) / 1_000_000

    def total_tokens() -> int:
        return sum(usage.values())

    while True:
        if turns >= budget["max_turns"]:
            terminal = "max_turns_exhausted"
            break
        if total_tokens() >= budget["max_tokens"]:
            terminal = "token_budget_exhausted"
            break
        if cost() >= budget["max_usd"]:
            terminal = "cost_budget_exhausted"
            break
        if cost() >= remaining_run_usd:
            terminal = "run_budget_halt"
            break
        if time.time() - started >= budget["max_wallclock_s"]:
            terminal = "wall_clock_exhausted"
            break

        try:
            resp = call_model(
                api_key,
                {
                    "model": model_cfg["id"],
                    "max_tokens": model_cfg["max_output_tokens"],
                    "temperature": model_cfg["temperature"],
                    "system": system,
                    "tools": tools,
                    "messages": messages,
                },
            )
        except ModelError as exc:
            terminal = "model_api_error"
            transcript.append({"role": "harness", "error": redact(str(exc))})
            break

        turns += 1
        u = resp.get("usage", {})
        usage["input"] += u.get("input_tokens", 0)
        usage["output"] += u.get("output_tokens", 0)
        usage["cache_read"] += u.get("cache_read_input_tokens", 0) or 0
        usage["cache_write"] += u.get("cache_creation_input_tokens", 0) or 0

        content = resp.get("content", [])
        messages.append({"role": "assistant", "content": content})
        transcript.append({"role": "assistant", "content": redact(content)})

        uses = [b for b in content if b.get("type") == "tool_use"]
        if not uses:
            nudges += 1
            if nudges > 2:
                terminal = "no_tool_call_repeated"
                break
            messages.append(
                {
                    "role": "user",
                    "content": "You have not finished. Call `submit_answer` now with your best "
                               "status and value.",
                }
            )
            transcript.append({"role": "user", "content": "[harness nudge]"})
            continue

        results = []
        done = False
        for block in uses:
            name, args = block.get("name"), block.get("input") or {}
            if name == "submit_answer":
                submission = {
                    "status": args.get("status"),
                    "value": args.get("value", ""),
                    "note": args.get("note", ""),
                }
                results.append({"type": "tool_result", "tool_use_id": block["id"], "content": "recorded"})
                tool_calls.append({"name": name, "args": redact(args), "ok": True})
                done = True
                continue
            fn = tool_fns.get(name)
            t0 = time.time()
            if fn is None:
                out, ok = (f"No tool named {name!r}. Available: "
                           + ", ".join(sorted(list(tool_fns) + ['submit_answer']))), False
            else:
                try:
                    out, ok = str(fn(**args)), True
                except TypeError as exc:
                    out, ok = f"Bad arguments for {name}: {exc}", False
                except Exception as exc:  # noqa: BLE001
                    out, ok = f"{type(exc).__name__}: {exc}", False
            if len(out) > truncation_chars:
                out = out[:truncation_chars] + f"\n[truncated at {truncation_chars} characters]"
            results.append({"type": "tool_result", "tool_use_id": block["id"], "content": out,
                            "is_error": not ok})
            tool_calls.append({"name": name, "args": redact(args), "ok": ok,
                               "ms": int((time.time() - t0) * 1000),
                               "result_chars": len(out)})
        messages.append({"role": "user", "content": results})
        transcript.append({"role": "user", "content": redact(results)})
        if done:
            terminal = "submitted_answer"
            break

    return {
        "submission": submission,
        "terminal": terminal,
        "turns": turns,
        "tokens": dict(usage),
        "tokens_total": total_tokens(),
        "cost_usd": round(cost(), 6),
        "wall_s": round(time.time() - started, 2),
        "tool_calls": tool_calls,
        "distinct_tools_used": sorted({c["name"] for c in tool_calls}),
        "transcript": transcript,
    }
