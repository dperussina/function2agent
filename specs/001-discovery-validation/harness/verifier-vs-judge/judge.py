"""SPIKE - E8 verifier-vs-judge. Delete after 2026-11-30. Do not import from product code.

Arms (b) and (b'): the LLM judge and its cheap-model control.

PREREGISTRATION.md 4.2, 4.3, 5.3. Both arms use ``prompts/judge_v1.md`` byte-for-byte at
temperature 0, three independent calls per trace, recorded separately. The only difference
between the arms is the model id, so a difference between them is a difference in the model
and not in what it was asked.

Two things here are load-bearing and are written to be hard to get wrong:

* :func:`build_payload` assembles the prompt **only** from :func:`redact.scoring_view` output,
  and :func:`redact.assert_no_oracle_leak` runs on the assembled payload immediately before
  every call. A leak raises and the caller aborts the run (S2).
* :class:`StubJudge` answers from recorded fixtures, so ``--dry-run`` exercises the whole
  pipeline — payload assembly, leak assertion, truncation, repeats, parsing, ledger, metrics —
  for zero dollars. It is deterministic and is never used in a priced run.

The credential is resolved through ``../provider-credentials/envroot.py``: the process
environment, else a dotenv tree the operator names with ``--env-root`` / ``F2A_ENV_ROOT``,
**no default**. Its value is held in a local variable, passed to the client, and never
written to a log, a trace, a manifest, an error message, or a prompt.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass
from typing import Any, Protocol

import cost as cost_mod
import redact

HERE = os.path.dirname(os.path.abspath(__file__))


# --------------------------------------------------------------- credential resolution

def _envroot_module(cfg: dict):
    path = os.path.abspath(os.path.join(HERE, cfg["credentials"]["envroot_module_rel"]))
    d = os.path.dirname(path)
    if d not in sys.path:
        sys.path.insert(0, d)
    import envroot  # noqa: PLC0415
    return envroot


def load_api_key(cfg: dict, env_root_arg: str | None = None) -> str:
    """The credential, from the environment or a tree the operator names. No default path.

    Returns the value. It is the caller's job to keep it in a local variable. Nothing in this
    module prints, logs, or serialises it, and only the *name* of the variable ever appears in
    output.
    """
    var = cfg["credentials"]["api_key_var"]
    if os.environ.get(var):
        return os.environ[var]

    envroot = _envroot_module(cfg)
    argv = ["--env-root", env_root_arg] if env_root_arg else []
    root = envroot.resolve(argv)  # exits with a usage message if neither source is given
    for path in envroot.find_env_files(root):
        value = envroot.parse(path).get(var)
        if value:
            return value
    sys.exit(
        f"{var} was not found in any .env file under the search root you named.\n"
        f"  Export {var} directly, or point --env-root / F2A_ENV_ROOT at a tree that\n"
        f"  defines it. The value is never printed."
    )


# --------------------------------------------------------------- prompt assembly

def load_prompt(cfg: dict) -> tuple[str, str, str]:
    """Returns (system, user_template, sha256). The hash goes in the manifest."""
    path = os.path.join(HERE, cfg["judge_prompt"]["path"])
    with open(path, encoding="utf-8") as fh:
        raw = fh.read()
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    body = re.sub(r"^<!--.*?-->\s*", "", raw, flags=re.S)
    if "# SYSTEM" not in body or "# USER" not in body:
        raise SystemExit(f"judge prompt {path} must contain '# SYSTEM' and '# USER' sections")
    _, rest = body.split("# SYSTEM", 1)
    system, user = rest.split("# USER", 1)
    return system.strip(), user.strip(), digest


def build_payload(view: dict, record: dict, system: str, user_template: str,
                  cfg: dict) -> dict[str, Any]:
    """Assemble the model input from a redacted view, then assert no ground truth is in it.

    The assertion runs here, on the fully assembled object, rather than at the client, so no
    call path can reach the provider without passing it.
    """
    c = cfg["cost"]
    transcript, truncated, _ = cost_mod.truncate_transcript(
        list(view.get("transcript") or []), c["transcript_truncation_tokens"], c["bytes_per_token"]
    )

    def blob(x: Any) -> redact.AgentText:
        return redact.AgentText(json.dumps(x, indent=1, default=str))

    filled = user_template
    for token, value in (
        ("{{TASK_PROMPT}}", view["task_prompt"]),
        ("{{TERMINAL}}", redact.AgentText(str(view.get("terminal") or "unknown"))),
        ("{{TOOL_CALLS}}", blob(view.get("tool_calls") or [])),
        ("{{TRANSCRIPT}}", blob(transcript)),
        ("{{SUBMITTED_STATUS}}", redact.AgentText(str(view.get("submitted_status") or "none"))),
        ("{{SUBMITTED}}", blob(view.get("submitted"))),
    ):
        filled = filled.replace(token, str(value))
    if "{{" in filled:
        raise SystemExit(f"unfilled placeholder in the judge prompt: {re.findall(r'{{[A-Z_]+}}', filled)}")

    # Reassemble as a tagged structure so the leak assertion can tell harness text from agent
    # text. The scalar `filled` string is the concatenation of both, so it is handed over as
    # its parts, not as one opaque blob.
    payload = {
        "system": system,
        "user_parts": {
            "template": _template_skeleton(user_template),
            "task_prompt": view["task_prompt"],
            "terminal": redact.AgentText(str(view.get("terminal") or "unknown")),
            "tool_calls": blob(view.get("tool_calls") or []),
            "transcript": blob(transcript),
            "submitted_status": redact.AgentText(str(view.get("submitted_status") or "none")),
            "submitted": blob(view.get("submitted")),
        },
        "_rendered": redact.AgentText(filled),
        "_truncated": truncated,
    }
    redact.assert_no_oracle_leak(payload, record, where=f"judge payload {record.get('task_id')}")
    return {"system": system, "user": filled, "truncated": truncated}


def _template_skeleton(user_template: str) -> str:
    """The harness-authored part of the user message: the template with slots emptied."""
    return re.sub(r"{{[A-Z_]+}}", "", user_template)


# --------------------------------------------------------------- verdict parsing

VERDICT_RE = re.compile(r"\{.*\}", re.S)


@dataclass
class Verdict:
    succeeded: bool | None
    p_success: float | None
    justification: str
    parse_ok: bool
    raw: str


def parse_verdict(text: str) -> Verdict:
    """Parse the judge's JSON. A malformed reply is recorded as unparsed, never guessed at.

    Coercing an unparseable reply to `fail` would quietly manufacture detections; coercing it
    to `pass` would quietly manufacture fail-opens. Both bias the primary metric, so neither
    is done: the call is flagged and the repair reserve exists to re-issue it.
    """
    m = VERDICT_RE.search(text or "")
    if not m:
        return Verdict(None, None, "", False, text or "")
    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError:
        return Verdict(None, None, "", False, text or "")
    s = obj.get("succeeded")
    p = obj.get("p_success")
    if not isinstance(s, bool) or not isinstance(p, (int, float)) or not 0.0 <= float(p) <= 1.0:
        return Verdict(None, None, str(obj.get("justification") or ""), False, text or "")
    return Verdict(bool(s), float(p), str(obj.get("justification") or ""), True, text or "")


# --------------------------------------------------------------- clients

class JudgeClient(Protocol):
    def complete(self, model: str, system: str, user: str, temperature: float,
                 max_tokens: int) -> tuple[str, int, int]: ...


class AnthropicClient:
    """Thin client. Constructed with the key; never stores it anywhere reachable by a log."""

    def __init__(self, api_key: str) -> None:
        try:
            import anthropic  # noqa: PLC0415
        except ImportError:  # pragma: no cover - environment dependent
            raise SystemExit(
                "the `anthropic` package is not installed.\n"
                "  pip install anthropic\n"
                "  (--dry-run needs neither the package nor a credential)"
            ) from None
        self._client = anthropic.Anthropic(api_key=api_key)

    def complete(self, model: str, system: str, user: str, temperature: float,
                 max_tokens: int) -> tuple[str, int, int]:
        resp = self._client.messages.create(
            model=model, system=system, temperature=temperature, max_tokens=max_tokens,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        return text, int(resp.usage.input_tokens), int(resp.usage.output_tokens)


class StubJudge:
    """Deterministic recorded-fixture judge. Used by --dry-run; never by a priced run.

    Its verdicts are a **fixed function of the trace key**, not of anything oracle-derived, so
    a dry run cannot accidentally produce a flattering result. It exists to exercise the
    pipeline, not to predict one.
    """

    def __init__(self, fixture_path: str | None = None) -> None:
        self.fixtures: dict[str, dict] = {}
        if fixture_path and os.path.isfile(fixture_path):
            with open(fixture_path, encoding="utf-8") as fh:
                self.fixtures = json.load(fh)

    def complete(self, model: str, system: str, user: str, temperature: float,
                 max_tokens: int) -> tuple[str, int, int]:
        h = hashlib.sha256((model + user).encode("utf-8")).hexdigest()
        canned = self.fixtures.get(h)
        if canned is None:
            n = int(h[:8], 16)
            p = round((n % 1000) / 1000.0, 3)
            canned = {"succeeded": p >= 0.5, "p_success": p,
                      "justification": "stub verdict; no model was called"}
        text = json.dumps(canned)
        return text, cost_mod.est_tokens(system + user, 4.0), cost_mod.est_tokens(text, 4.0)


# --------------------------------------------------------------- the arm

def score_trace(client: JudgeClient, arm_key: str, cfg: dict, view: dict, record: dict,
                system: str, user_template: str, repeats: int,
                ledger: cost_mod.Ledger, priced: bool) -> list[dict]:
    """Run one trace through one judge arm, ``repeats`` times, logging every call.

    PREREGISTRATION.md 7.9: model id, prompt hash, repeat index, token counts, cost, verdict,
    p_success and latency are logged per call. Cost is checked against the ceiling **before**
    each call.
    """
    import time

    spec = cfg["judge_arms"][arm_key]
    price = spec["price_usd_per_mtok"]
    payload = build_payload(view, record, system, user_template, cfg)

    est_in = cost_mod.est_tokens(payload["system"] + payload["user"], cfg["cost"]["bytes_per_token"])
    est_call = cost_mod.call_cost(est_in, cfg["cost"]["output_tokens_per_call"], price)

    out: list[dict] = []
    for i in range(1, repeats + 1):
        if priced:
            ledger.check_before(est_call)
        t0 = time.time()
        text, in_tok, out_tok = client.complete(
            spec["id"], payload["system"], payload["user"],
            spec["temperature"], spec["max_output_tokens"],
        )
        latency = round(time.time() - t0, 3)
        if priced:
            usd = ledger.bill(arm_key, in_tok, out_tok, price)
        else:
            usd = 0.0
            ledger.calls += 1  # counted, not billed: a dry run must still report its volume
        v = parse_verdict(text)
        out.append({
            "arm": arm_key, "model_id": spec["id"], "repeat": i,
            "run_id": record["run_id"], "task_id": record["task_id"],
            "trace_arm": record["arm"], "attempt": record["attempt"],
            "succeeded": v.succeeded, "p_success": v.p_success,
            "justification": v.justification, "parse_ok": v.parse_ok,
            "input_tokens": in_tok, "output_tokens": out_tok,
            "cost_usd": round(usd, 6), "latency_s": latency,
            "truncated": payload["truncated"], "priced": priced,
        })
    return out


def aggregate(calls: list[dict]) -> dict:
    """Majority of three, with the any-fail / all-fail variants and the flip flag (5.3)."""
    parsed = [c for c in calls if c["parse_ok"]]
    if not parsed:
        return {"verdict": None, "p_success_mean": None, "flip": None,
                "any_fail": None, "all_fail": None, "n_parsed": 0}
    fails = sum(1 for c in parsed if c["succeeded"] is False)
    return {
        "verdict": "fail" if fails * 2 > len(parsed) else "pass",
        "p_success_mean": sum(c["p_success"] for c in parsed) / len(parsed),
        "p_success_per_repeat": [c["p_success"] for c in parsed],
        "flip": len({c["succeeded"] for c in parsed}) > 1,
        "any_fail": fails > 0,
        "all_fail": fails == len(parsed),
        "n_parsed": len(parsed),
    }
