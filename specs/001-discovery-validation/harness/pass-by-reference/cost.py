"""SPIKE - E17 pass-by-reference. Delete after 2026-11-30. Do not import from product code.

The projection. Prints its arithmetic, calls nothing, spends nothing.

Every prior experiment in this ladder was authorized by the owner against a
dry-run projection before a token was bought, and this is that artefact for E17.
Three commitments it keeps:

* **Measured, not asserted.** The bulk sizes come from `measure.py` running the
  battery against the generated corpus. The only invented numbers are the ones
  `config.json` names as model constants (turns, per-turn output, prefix sizes),
  and each of those is a single greppable key.
* **Arithmetic on the page.** `--verbose` prints the per-call accumulation for one
  task in both treatments, so a reader can check the accumulation by hand rather
  than trusting the loop.
* **Separately authorizable arms.** Arm A and arm B are projected independently and
  never summed into a single headline, because 12 of the preregistration says the
  owner may want one and not the other.

Usage:  python3 cost.py [--verbose] [--json] [--write]
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys

import measure
import tasks
import tokens

HERE = os.path.dirname(os.path.abspath(__file__))


def treatments(cfg: dict) -> tuple[tokens.Treatment, tokens.Treatment]:
    t = cfg["treatments"]
    return (
        tokens.Treatment("A-inline", t["inline"]["cap_tokens"],
                         t["inline"]["extra_turn_per_bulk_step"],
                         t["inline"]["static_prefix_tokens"],
                         t["inline"]["data_reachable_after_cap"]),
        tokens.Treatment("A-handle", t["handle"]["cap_tokens"],
                         t["handle"]["extra_turn_per_bulk_step"],
                         t["handle"]["static_prefix_tokens"],
                         t["handle"]["data_reachable_after_cap"]),
    )


def turn_model(cfg: dict) -> tokens.TurnModel:
    tm = cfg["turn_model"]
    return tokens.TurnModel(tm["task_prompt_tokens"], tm["output_tokens_per_working_turn"],
                            tm["output_tokens_final_turn"], tm["small_result_tokens"],
                            tm["bulk_threshold_bytes"])


def project_arm_a(cfg: dict, meas: dict) -> dict:
    bpt = cfg["cost"]["bytes_per_token"]
    price = cfg["model"]["price_usd_per_mtok"]
    tm = turn_model(cfg)
    inline, handle = treatments(cfg)

    window = cfg["cost"]["context_window_tokens"]
    per_task = {}
    over_window = []
    handle_cap_bytes = handle.cap_tokens * bpt
    inline_cap_bytes = inline.cap_tokens * bpt
    for tid, rec in meas["tasks"].items():
        if tid == "S00":
            continue
        step_bytes = [s["stdout_bytes"] for s in rec["steps"]]
        pi = tokens.project_run(step_bytes, tm, inline, bpt)
        ph = tokens.project_run(step_bytes, tm, handle, bpt)
        ci = pi.cost_usd(price["input"], price["output"])
        ch = ph.cost_usd(price["input"], price["output"])
        if pi.peak_input_tokens > window or ph.peak_input_tokens > window:
            over_window.append(tid)
        # How much of each bulk step the cap throws away. In the inline arm those
        # bytes are unrecoverable; in the handle arm they are on disk. Same number,
        # opposite consequence, and it is limb 2's whole mechanism.
        elided = sum(max(0, tokens.est_tokens(s["stdout_bytes"], bpt)
                         - (inline.cap_tokens or 10 ** 12))
                     for s in rec["steps"])
        # Stratum, assigned by measured bytes against the two caps — not by taste
        # and not by the "bulk" threshold, which is a different boundary.
        #   null_control  every step under the handle preview: neither arm acts
        #   cap_clearing  the handle arm saves tokens; the inline arm loses nothing
        #   cap_binding   the inline arm also loses bytes it cannot get back
        max_step = max(step_bytes) if step_bytes else 0
        if max_step <= handle_cap_bytes:
            stratum = "null_control"
        elif max_step <= inline_cap_bytes:
            stratum = "cap_clearing"
        else:
            stratum = "cap_binding"
        per_task[tid] = {
            "family": rec["family"],
            "bulk_steps": rec["bulk_steps"],
            "max_step_bytes": max_step,
            "set": stratum,
            "inline": {"turns": pi.turns, "in": pi.input_tokens, "out": pi.output_tokens,
                       "peak_in": pi.peak_input_tokens, "usd": ci},
            "handle": {"turns": ph.turns, "in": ph.input_tokens, "out": ph.output_tokens,
                       "peak_in": ph.peak_input_tokens, "usd": ch},
            "pair_usd": ci + ch,
            "inline_tokens_lost_to_cap": elided,
            "projected_token_ratio": (ph.input_tokens + ph.output_tokens)
                                     / (pi.input_tokens + pi.output_tokens),
        }

    battery_pair_usd = sum(v["pair_usd"] for v in per_task.values())

    sentinel_bytes = [s["stdout_bytes"] for s in meas["tasks"]["S00"]["steps"]]
    ps = tokens.project_run(sentinel_bytes, tm, inline, bpt)
    sentinel_usd = ps.cost_usd(price["input"], price["output"])

    d = cfg["design"]
    n_sentinels = d["sentinels_per_session"] * d["sessions_planned"]
    stage1 = battery_pair_usd
    stage2 = battery_pair_usd * (d["replicates_per_task"] - 1)
    sentinels = sentinel_usd * n_sentinels
    subtotal = stage1 + stage2 + sentinels
    # One permitted stage-1 retune, priced exactly. See config cost._contingency_note.
    contingency = stage1
    replicate_usd = battery_pair_usd
    # Irreducible: the gate, two replicates, the drift detector, and the retune the
    # design is most likely to need. Margin: the third replicate only.
    irreducible = stage1 + replicate_usd + sentinels + contingency
    margin = stage2 - replicate_usd

    return {
        "arm": "A",
        "per_task": per_task,
        "over_context_window": over_window,
        "context_window_tokens": window,
        "cap_sensitivity": cap_sensitivity(cfg, meas),
        "battery_pair_usd": battery_pair_usd,
        "sentinel_usd": sentinel_usd,
        "n_sentinels": n_sentinels,
        "stage1_usd": stage1,
        "stage2_usd": stage2,
        "sentinels_usd": sentinels,
        "subtotal_usd": subtotal,
        "contingency_usd": contingency,
        "total_usd": subtotal + contingency,
        "irreducible_usd": irreducible,
        "margin_usd": margin,
        "pairs_stage1": len(per_task),
        "pairs_stage2": len(per_task) * (d["replicates_per_task"] - 1),
        "hard_ceiling_usd": cfg["cost"]["arm_a_hard_ceiling_usd"],
        "budget_usd": cfg["cost"]["arm_a_budget_usd"],
    }


def cap_sensitivity(cfg: dict, meas: dict) -> dict:
    """Reprice the whole battery at every inline cap in the config. Costs nothing.

    The measured effect is conditional on where the inline arm truncates, so a
    single ratio quoted without its cap is not a result. These come out of the same
    measured bytes, so the sensitivity is free and there is no excuse for
    publishing one number.
    """
    bpt = cfg["cost"]["bytes_per_token"]
    price = cfg["model"]["price_usd_per_mtok"]
    tm = turn_model(cfg)
    _, handle = treatments(cfg)
    t = cfg["treatments"]["inline"]
    out = {}
    for cap in cfg["cost"]["cap_sensitivity"]:
        inline = tokens.Treatment("A-inline", cap, t["extra_turn_per_bulk_step"],
                                  t["static_prefix_tokens"], t["data_reachable_after_cap"])
        ratios, pair_usd, peak = [], 0.0, 0
        for tid, rec in meas["tasks"].items():
            if tid == "S00":
                continue
            sb = [s["stdout_bytes"] for s in rec["steps"]]
            pi = tokens.project_run(sb, tm, inline, bpt)
            ph = tokens.project_run(sb, tm, handle, bpt)
            ratios.append((ph.input_tokens + ph.output_tokens)
                          / (pi.input_tokens + pi.output_tokens))
            pair_usd += (pi.cost_usd(price["input"], price["output"])
                         + ph.cost_usd(price["input"], price["output"]))
            peak = max(peak, pi.peak_input_tokens)
        ratios.sort()
        out[str(cap)] = {
            "median_projected_ratio": ratios[len(ratios) // 2],
            "battery_pair_usd": pair_usd,
            "max_inline_peak_input_tokens": peak,
            "fits_context_window": peak <= cfg["cost"]["context_window_tokens"],
        }
    return out


def _accumulate(prefix: int, results: list[int], out_turn: int, out_final: int) -> tuple[int, int]:
    acc, tin, tout = 0, 0, 0
    for r in results:
        tin += prefix + acc
        tout += out_turn
        acc += out_turn + r
    tin += prefix + acc
    tout += out_final
    return tin, tout


def project_arm_b(cfg: dict) -> dict:
    """Arm B, projected so it can be declined with a number rather than a shrug."""
    b = cfg["arm_b"]["if_authorized_anyway"]
    price = cfg["model"]["price_usd_per_mtok"]

    def one(prefix_tokens: int, working_turns: int) -> tuple[int, int, float]:
        prefix = prefix_tokens + b["task_prompt_tokens"]
        results = [b["result_tokens_per_turn"]] * working_turns
        tin, tout = _accumulate(prefix, results, b["output_tokens_per_working_turn"],
                                b["output_tokens_final_turn"])
        return tin, tout, tokens.call_cost(tin, tout, price["input"], price["output"])

    in_tin, in_tout, in_usd = one(b["static_prefix_tokens_inprocess"], b["working_turns_inprocess"])
    sb_tin, sb_tout, sb_usd = one(
        b["static_prefix_tokens_inprocess"] + b["sandbox_context_block_tokens"],
        b["working_turns_sandbox"])

    pair = in_usd + sb_usd
    n_pairs = b["tasks"] * b["replicates_per_task"]
    subtotal = pair * n_pairs
    # Arm B has no calibration stage to retune, so its contingency is a flat 15%.
    # It is a nervousness number, and it is the only one in this file.
    contingency = subtotal * 0.15
    return {
        "arm": "B",
        "inprocess": {"in": in_tin, "out": in_tout, "usd": in_usd},
        "sandbox": {"in": sb_tin, "out": sb_tout, "usd": sb_usd},
        "pair_usd": pair,
        "n_pairs": n_pairs,
        "subtotal_usd": subtotal,
        "contingency_usd": contingency,
        "total_usd": subtotal + contingency,
        "hard_ceiling_usd": cfg["cost"]["arm_b_hard_ceiling_usd"],
        "budget_usd": cfg["cost"]["arm_b_budget_usd"],
        "status": cfg["arm_b"]["status"],
    }


def verbose_walkthrough(cfg: dict, meas: dict, task_id: str = "T09") -> list[str]:
    """Per-call accumulation for one task, so the loop can be checked by hand."""
    bpt = cfg["cost"]["bytes_per_token"]
    tm = turn_model(cfg)
    inline, handle = treatments(cfg)
    step_bytes = [s["stdout_bytes"] for s in meas["tasks"][task_id]["steps"]]
    lines = [f"per-call accumulation for {task_id} "
             f"(step stdout bytes: {step_bytes})", ""]
    for tr in (inline, handle):
        results = tokens.ordered_result_tokens(step_bytes, tm, tr, bpt)
        prefix = tr.static_prefix_tokens + tm.task_prompt_tokens
        lines.append(f"  {tr.name}: prefix={prefix} "
                     f"(static {tr.static_prefix_tokens} + prompt {tm.task_prompt_tokens})")
        acc, tin, tout = 0, 0, 0
        for i, r in enumerate(results, 1):
            call_in = prefix + acc
            tin += call_in
            tout += tm.output_tokens_per_working_turn
            acc += tm.output_tokens_per_working_turn + r
            lines.append(f"    call {i:>2}: in={call_in:>7}  out="
                         f"{tm.output_tokens_per_working_turn:>4}  result={r:>7}  acc={acc:>7}")
        call_in = prefix + acc
        tin += call_in
        tout += tm.output_tokens_final_turn
        lines.append(f"    call {len(results) + 1:>2}: in={call_in:>7}  out="
                     f"{tm.output_tokens_final_turn:>4}  (answer)")
        price = cfg["model"]["price_usd_per_mtok"]
        usd = tokens.call_cost(tin, tout, price["input"], price["output"])
        lines.append(f"    totals: in={tin:,}  out={tout:,}  "
                     f"= {tin:,}x{price['input']}/1e6 + {tout:,}x{price['output']}/1e6 "
                     f"= ${usd:.6f}")
        lines.append("")
    return lines


def render(cfg: dict, meas: dict, a: dict, b: dict, verbose: bool) -> str:
    L: list[str] = []
    L.append("E17 pass-by-reference — cost projection (dry run; no model was called)")
    L.append("=" * 78)
    L.append(f"generated       : {datetime.datetime.now(datetime.timezone.utc).isoformat()}")
    L.append(f"model           : {cfg['model']['provider']}/{cfg['model']['id']} "
             f"@ ${cfg['model']['price_usd_per_mtok']['input']}/M in, "
             f"${cfg['model']['price_usd_per_mtok']['output']}/M out")
    L.append(f"divisor         : {cfg['cost']['bytes_per_token']} bytes/token (estimate, not a tokenizer)")
    L.append(f"corpus          : {meas['corpus_file_count']} files, "
             f"{meas['corpus_total_bytes']:,} bytes, seed {cfg['corpus']['seed']}")
    L.append(f"model calls made by this script: 0    spend by this script: $0.00")
    L.append("")

    L.append("ARM A — inline vs handle+preview on a command-execution surface")
    L.append("-" * 78)
    L.append(f"inline cap {cfg['treatments']['inline']['cap_tokens']:,} tok/result "
             f"(bytes past it are LOST); handle cap "
             f"{cfg['treatments']['handle']['cap_tokens']:,} tok/result "
             f"(bytes past it stay on disk)")
    L.append(f"{'task':<6} {'stratum':<13} {'max step B':>11} {'inline in':>10} "
             f"{'handle in':>10} {'ratio':>7} {'lost tok':>9} {'pair $':>9}")
    for tid in sorted(a["per_task"]):
        v = a["per_task"][tid]
        L.append(f"{tid:<6} {v['set']:<13} {v['max_step_bytes']:>11,} "
                 f"{v['inline']['in']:>10,} {v['handle']['in']:>10,} "
                 f"{v['projected_token_ratio']:>7.3f} "
                 f"{v['inline_tokens_lost_to_cap']:>9,} {v['pair_usd']:>9.4f}")
    counts: dict[str, int] = {}
    for v in a["per_task"].values():
        counts[v["set"]] = counts.get(v["set"], 0) + 1
    L.append(f"strata          : " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    L.append("")
    if a["over_context_window"]:
        L.append(f"!! projected peak input exceeds the "
                 f"{a['context_window_tokens']:,}-token window on: "
                 f"{a['over_context_window']} — those runs cannot happen")
    else:
        L.append(f"context window : every projected run fits "
                 f"{a['context_window_tokens']:,} tokens")
    L.append("")
    L.append("cap sensitivity (same measured bytes, repriced; costs nothing)")
    for cap, s in a["cap_sensitivity"].items():
        fit = "fits" if s["fits_context_window"] else "DOES NOT FIT"
        L.append(f"  inline cap {int(cap):>6,} tok -> median projected ratio "
                 f"{s['median_projected_ratio']:.3f}, battery pair "
                 f"${s['battery_pair_usd']:.4f}, peak inline input "
                 f"{s['max_inline_peak_input_tokens']:,} ({fit})")
    L.append("")
    d = cfg["design"]
    L.append(f"one full battery pair-pass ({a['pairs_stage1']} pairs)        = ${a['battery_pair_usd']:.4f}")
    L.append(f"stage 1 (replicate 1, and the calibration gate)  = ${a['stage1_usd']:.4f}")
    L.append(f"stage 2 (replicates 2-{d['replicates_per_task']}, {a['pairs_stage2']} pairs)"
             f"{'':<12}= ${a['stage2_usd']:.4f}")
    L.append(f"drift sentinels ({a['n_sentinels']} x ${a['sentinel_usd']:.4f})"
             f"{'':<20}= ${a['sentinels_usd']:.4f}")
    L.append(f"{'':<49}  {'-' * 10}")
    L.append(f"subtotal{'':<41}= ${a['subtotal_usd']:.4f}")
    L.append(f"contingency (one permitted stage-1 retune)       = ${a['contingency_usd']:.4f}")
    L.append(f"{'':<49}  {'-' * 10}")
    L.append(f"ARM A TOTAL{'':<38}= ${a['total_usd']:.4f}")
    L.append(f"   hard ceiling ${a['hard_ceiling_usd']:.2f}, budget ${a['budget_usd']:.2f}")
    L.append("")
    L.append(f"   irreducible minimum for a readable result   = ${a['irreducible_usd']:.4f}")
    L.append(f"     = stage 1 (gate + replicate 1) + replicate 2 + sentinels + one retune")
    L.append(f"   buys statistical margin only                = ${a['margin_usd']:.4f}")
    L.append(f"     = replicate 3")
    L.append("")

    L.append("ARM B — NOOA inprocess vs sandbox")
    L.append("-" * 78)
    L.append(f"status: {b['status']} — see 11 of the preregistration")
    L.append(f"  inprocess run : in={b['inprocess']['in']:,}  out={b['inprocess']['out']:,}  "
             f"${b['inprocess']['usd']:.4f}")
    L.append(f"  sandbox run   : in={b['sandbox']['in']:,}  out={b['sandbox']['out']:,}  "
             f"${b['sandbox']['usd']:.4f}")
    L.append(f"  pair          : ${b['pair_usd']:.4f} x {b['n_pairs']} pairs "
             f"= ${b['subtotal_usd']:.4f}")
    L.append(f"  contingency   : ${b['contingency_usd']:.4f}")
    L.append(f"  ARM B TOTAL   : ${b['total_usd']:.4f}   "
             f"(ceiling ${b['hard_ceiling_usd']:.2f}, budget ${b['budget_usd']:.2f})")
    L.append("")

    if verbose:
        L.append("ARITHMETIC WALKTHROUGH")
        L.append("-" * 78)
        L.extend(verbose_walkthrough(cfg, meas))
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--write", action="store_true", help="write into results/")
    args = ap.parse_args()

    cfg = measure.load_config()
    man, meas = measure.build()
    if meas["cross_check_failures"]:
        print(f"battery cross-check failed on {meas['cross_check_failures']}; "
              f"refusing to project", file=sys.stderr)
        return 1

    a = project_arm_a(cfg, meas)
    b = project_arm_b(cfg)
    text = render(cfg, meas, a, b, args.verbose)

    if args.json:
        print(json.dumps({"dry_run": True, "model_calls": 0, "spend_usd": 0.0,
                          "arm_a": a, "arm_b": b}, indent=2))
    else:
        print(text)

    if args.write:
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d")
        out = os.path.join(HERE, "results", f"{stamp}-cost-projection")
        os.makedirs(out, exist_ok=True)
        with open(os.path.join(out, "projection.json"), "w") as fh:
            json.dump({"dry_run": True, "model_calls": 0, "spend_usd": 0.0,
                       "corpus_manifest": man, "measurements": meas,
                       "arm_a": a, "arm_b": b}, fh, indent=2)
        with open(os.path.join(out, "projection.txt"), "w") as fh:
            fh.write(text + "\n")
        print(f"\nwritten to {os.path.relpath(out, HERE)}/", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
