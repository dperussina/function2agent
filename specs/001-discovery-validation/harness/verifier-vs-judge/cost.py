"""SPIKE - E8 verifier-vs-judge. Delete after 2026-11-30. Do not import from product code.

Cost governance: estimation before the run, accounting during it, and the ceiling that stops it.

PREREGISTRATION.md 10 and 12. Three separate mechanisms, deliberately not one:

* :func:`project` measures the **actual** serialised payload of the selected traces and
  projects the spend. It runs before the first call and prints its arithmetic. 10 requires
  this: "it must print its projection before its first call."
* :func:`truncate_transcript` caps any single transcript at 24,000 tokens, eliding the middle
  and flagging the record. Truncated records are counted and reported separately, because
  truncation could itself hide the evidence a judge needed.
* :class:`Ledger` is the live accumulator. It is checked **before** each call against the
  $9.00 hard ceiling (S7), never after, and it bills **measured** usage from the API response
  rather than the estimate.

The estimate and the bill are kept apart on purpose. ``bytes_per_token`` is a divisor from the
preregistration's own arithmetic, not a tokenizer; using it to bill would launder an estimate
into an accounting figure.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import Any


class BudgetExceeded(RuntimeError):
    """The $9.00 hard ceiling (S7). Abort; report partial results against the frozen manifest."""


def est_tokens(text: str, bytes_per_token: float) -> int:
    return math.ceil(len(text.encode("utf-8")) / bytes_per_token)


def payload_bytes(trace: dict) -> int:
    """The transcript + tool_calls payload, measured the way PREREGISTRATION.md 2 measured it."""
    return len(json.dumps({
        "transcript": trace.get("transcript", []),
        "tool_calls": trace.get("tool_calls", []),
    }).encode("utf-8"))


def truncate_transcript(transcript: list, limit_tokens: int,
                        bytes_per_token: float) -> tuple[list, bool, int]:
    """Cap a transcript at ``limit_tokens``, eliding the middle.

    Returns ``(transcript, was_truncated, est_tokens_after)``. The middle is elided rather
    than the tail because the submitted answer and the final reasoning sit at the end and the
    task setup sits at the start; dropping either end would remove exactly what a judge needs.
    """
    blob = json.dumps(transcript)
    total = est_tokens(blob, bytes_per_token)
    if total <= limit_tokens:
        return transcript, False, total

    keep_msgs = list(transcript)
    marker = {"role": "harness", "content": "[... transcript elided by the harness to fit the "
                                            "24,000-token cap; this record is flagged truncated ...]"}
    lo, hi = 0, len(keep_msgs) // 2
    while lo < hi and len(keep_msgs) > 2:
        head = max(1, len(keep_msgs) // 4)
        tail = max(1, len(keep_msgs) - head - 1)
        candidate = keep_msgs[:head] + [marker] + keep_msgs[-(len(keep_msgs) - tail):]
        if est_tokens(json.dumps(candidate), bytes_per_token) <= limit_tokens:
            keep_msgs = candidate
            break
        keep_msgs = keep_msgs[:head] + keep_msgs[head + 1:]
        lo += 1

    if est_tokens(json.dumps(keep_msgs), bytes_per_token) > limit_tokens:
        # Character-level fallback: keep the head and tail of the serialised form. Coarse, but
        # it is a hard cap and a hard cap that can be exceeded is not one.
        budget_bytes = int(limit_tokens * bytes_per_token)
        head_b = blob[: budget_bytes // 2]
        tail_b = blob[-(budget_bytes // 2):]
        keep_msgs = [{"role": "harness", "content": head_b + "\n[... elided ...]\n" + tail_b}]

    return keep_msgs, True, est_tokens(json.dumps(keep_msgs), bytes_per_token)


def call_cost(in_tok: int, out_tok: int, price: dict) -> float:
    return in_tok * price["input"] / 1e6 + out_tok * price["output"] / 1e6


@dataclass
class ArmProjection:
    arm: str
    model_id: str
    calls: int
    input_tokens: int
    output_tokens: int
    input_usd: float
    output_usd: float

    @property
    def total_usd(self) -> float:
        return self.input_usd + self.output_usd


def project(selected_traces: list[dict], cfg: dict, repeats_neg: int, repeats_pos: int,
            is_negative: dict[tuple, bool]) -> dict[str, Any]:
    """Project the judge spend from the **measured** payload of the selected traces.

    No API call is made. This is what ``--dry-run`` reports and what the contingency in
    PREREGISTRATION.md 10 is evaluated against.
    """
    from corpus import trace_key

    c = cfg["cost"]
    bpt = c["bytes_per_token"]
    overhead = c["rubric_overhead_tokens"]
    out_per_call = c["output_tokens_per_call"]
    cap = c["transcript_truncation_tokens"]

    per_trace: list[dict] = []
    for t in selected_traces:
        raw_b = payload_bytes(t)
        raw_tok = math.ceil(raw_b / bpt)
        _, truncated, after = truncate_transcript(t.get("transcript", []), cap, bpt)
        tc_tok = est_tokens(json.dumps(t.get("tool_calls", [])), bpt)
        in_tok = min(raw_tok, after + tc_tok) + overhead
        k = trace_key(t)
        per_trace.append({
            "key": list(k),
            "negative": is_negative.get(k, False),
            "raw_bytes": raw_b,
            "raw_tokens": raw_tok,
            "truncated": truncated,
            "input_tokens": in_tok,
            "repeats": repeats_neg if is_negative.get(k, False) else repeats_pos,
        })

    arms: dict[str, ArmProjection] = {}
    for arm_key in ("b", "b_prime"):
        spec = cfg["judge_arms"][arm_key]
        price = spec["price_usd_per_mtok"]
        calls = sum(p["repeats"] for p in per_trace)
        in_tok = sum(p["input_tokens"] * p["repeats"] for p in per_trace)
        out_tok = calls * out_per_call
        arms[arm_key] = ArmProjection(
            arm=arm_key, model_id=spec["id"], calls=calls,
            input_tokens=in_tok, output_tokens=out_tok,
            input_usd=in_tok * price["input"] / 1e6,
            output_usd=out_tok * price["output"] / 1e6,
        )

    combined = sum(a.total_usd for a in arms.values())
    reserve = c["repair_reserve_usd"]
    n_trunc = sum(1 for p in per_trace if p["truncated"])
    return {
        "arms": {k: vars(v) | {"total_usd": v.total_usd} for k, v in arms.items()},
        "judge_subtotal_usd": combined,
        "repair_reserve_usd": reserve,
        "planned_total_usd": combined + reserve,
        "hard_ceiling_usd": c["hard_ceiling_usd"],
        "contingency_trigger_usd": c["contingency_trigger_usd"],
        "contingency_scope": c["contingency_scope"],
        "contingency_fires": combined > c["contingency_trigger_usd"],
        "truncated_records": n_trunc,
        "n_traces": len(per_trace),
        "mean_input_tokens": (sum(p["input_tokens"] for p in per_trace) / len(per_trace))
        if per_trace else 0,
        "max_raw_bytes": max((p["raw_bytes"] for p in per_trace), default=0),
        "per_trace": per_trace,
    }


def format_projection(proj: dict, cfg: dict) -> str:
    """The arithmetic, shown. A projection a reader cannot check is a number, not a projection."""
    lines = ["", "=== projected spend (no API call made) ===",
             f"  traces {proj['n_traces']}   mean input {proj['mean_input_tokens']:,.0f} tok/call"
             f"   max raw payload {proj['max_raw_bytes']:,} B"
             f"   truncated {proj['truncated_records']}"]
    for k, a in proj["arms"].items():
        spec = cfg["judge_arms"][k]
        p = spec["price_usd_per_mtok"]
        label = "b" if k == "b" else "b'"
        lines.append(f"  ({label}) {spec['id']}")
        lines.append(
            f"      input  {a['calls']:>4} calls x avg  = {a['input_tokens'] / 1e6:>7.4f} M "
            f"@ ${p['input']:>5.2f}/M = ${a['input_usd']:>6.3f}")
        lines.append(
            f"      output {a['calls']:>4} calls x {cfg['cost']['output_tokens_per_call']:>3} "
            f"= {a['output_tokens'] / 1e6:>7.4f} M @ ${p['output']:>5.2f}/M = ${a['output_usd']:>6.3f}")
        lines.append(f"      arm total                                        = ${a['total_usd']:>6.3f}")
    lines += [
        f"  judge subtotal                                       = ${proj['judge_subtotal_usd']:.3f}",
        f"  repair reserve                                       = ${proj['repair_reserve_usd']:.3f}",
        f"  PLANNED TOTAL                                        = ${proj['planned_total_usd']:.3f}",
        f"  preregistered expected $6.85 / pessimistic $8.62 / hard ceiling "
        f"${proj['hard_ceiling_usd']:.2f} (S7)",
        f"  contingency ({proj['contingency_scope']} > ${proj['contingency_trigger_usd']:.2f}): "
        f"{'FIRES — positives drop to 2 repeats' if proj['contingency_fires'] else 'does not fire'}",
    ]
    return "\n".join(lines)


@dataclass
class Ledger:
    """Live spend. Checked before every call; bills measured usage after every call."""

    ceiling_usd: float
    spent_usd: float = 0.0
    calls: int = 0
    by_arm: dict[str, float] = field(default_factory=dict)

    def check_before(self, projected_call_usd: float) -> None:
        if self.spent_usd >= self.ceiling_usd:
            raise BudgetExceeded(
                f"S7: hard ceiling ${self.ceiling_usd:.2f} reached (spent ${self.spent_usd:.4f}). "
                "Abort; report partial results against the frozen manifest."
            )
        if self.spent_usd + projected_call_usd > self.ceiling_usd:
            raise BudgetExceeded(
                f"S7: the next call (~${projected_call_usd:.4f}) would cross the "
                f"${self.ceiling_usd:.2f} ceiling at ${self.spent_usd:.4f} spent. "
                "Abort before the call, not after."
            )

    def bill(self, arm: str, in_tok: int, out_tok: int, price: dict) -> float:
        usd = call_cost(in_tok, out_tok, price)
        self.spent_usd += usd
        self.calls += 1
        self.by_arm[arm] = self.by_arm.get(arm, 0.0) + usd
        return usd
