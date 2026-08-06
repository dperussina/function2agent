"""SPIKE - E18. Fold the twelve artifacts into one record and one table. No model spend.

`python3 summarize.py [results-dir] [--text]`

**On the spend column.** Only xAI reports a server-side cost
(`usage.cost_in_usd_ticks`, read through `xai_sdk.chat.cost_usd_from_usage`).
The other three report tokens and leave the conversion to a per-provider price
table, which is one of the nine capabilities `U-48` records as having **no
owner**. [Finding 016](../../../001-discovery-validation/findings/016-provider-sdk-roundtrip.md)
refused to invent one and this harness does not depart from that: a `null` in
the cost column means *the provider reported none*, never *zero*.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

PROVIDERS = ("anthropic", "openai", "google", "xai")
CONDITIONS = ("A", "B", "C")
CONDITION_NAMES = {"A": "full chain", "B": "one state held",
                   "C": "all states held"}


def load(results: Path) -> dict[tuple[str, str], dict]:
    cells: dict[tuple[str, str], dict] = {}
    for provider in PROVIDERS:
        for condition in CONDITIONS:
            path = results / f"arm-{provider}-{condition}.json"
            if not path.is_file():
                continue
            try:
                cells[(provider, condition)] = json.loads(path.read_text())
            except json.JSONDecodeError:
                cells[(provider, condition)] = {"verdict": "UNPARSEABLE",
                                                "error": path.read_text()[:400]}
    return cells


def summarize(cells: dict[tuple[str, str], dict]) -> dict:
    rows = []
    for provider in PROVIDERS:
        for condition in CONDITIONS:
            cell = cells.get((provider, condition))
            if cell is None:
                rows.append({"provider": provider, "condition": condition,
                             "verdict": "MISSING"})
                continue
            rows.append({
                "provider": provider,
                "condition": condition,
                "model": cell.get("model"),
                "verdict": cell.get("verdict"),
                "provider_errored": cell.get("provider_errored"),
                "error_status": cell.get("error_status"),
                "last_request_shape": cell.get("last_request_shape"),
                "request_shapes": cell.get("request_shapes"),
                "state_turns": cell.get("state_turns"),
                "treatment_applied": cell.get("treatment_applied"),
                "turns": cell.get("turns"),
                "hops_linked": cell.get("hops_linked"),
                "chained": cell.get("chained"),
                "answer_correct": cell.get("answer_correct"),
                "input_tokens": cell.get("input_tokens", 0),
                "output_tokens": cell.get("output_tokens", 0),
                "cost_usd_reported_by_provider":
                    cell.get("cost_usd_reported_by_provider"),
                "credential_var": cell.get("credential_var"),
                "credential_fp": cell.get("credential_fp"),
                "error": (cell.get("error") or "")[:200] or None,
            })

    reported = [r["cost_usd_reported_by_provider"] for r in rows
                if r.get("cost_usd_reported_by_provider") is not None]
    controls = {r["provider"]: r["verdict"] for r in rows if r["condition"] == "A"}
    errored = {c: sorted(r["provider"] for r in rows
                         if r["condition"] == c and r["verdict"] == "ERRORED")
               for c in ("B", "C")}
    tolerated = {c: sorted(r["provider"] for r in rows
                           if r["condition"] == c and r["verdict"] == "TOLERATED")
                 for c in ("B", "C")}
    untestable = sorted(f"{r['provider']}-{r['condition']}" for r in rows
                        if str(r.get("verdict", "")).startswith("UNTESTABLE"))

    return {
        "experiment": "E18 — provider opaque-state chain, three conditions",
        "designed_in": ("specs/002-spec-aware-agent-runtime/findings/"
                        "030-provider-state-chain-derived-not-measured.md §6"),
        "rows": rows,
        "controls": controls,
        "all_controls_ok": all(v == "OK" for v in controls.values())
                           and len(controls) == len(PROVIDERS),
        "errored": errored,
        "tolerated": tolerated,
        "untestable": untestable,
        "totals": {
            "arms": len(rows),
            "input_tokens": sum(r.get("input_tokens") or 0 for r in rows),
            "output_tokens": sum(r.get("output_tokens") or 0 for r in rows),
            "provider_reported_cost_usd": round(sum(reported), 6) if reported else None,
            "providers_reporting_cost": sorted(
                {r["provider"] for r in rows
                 if r.get("cost_usd_reported_by_provider") is not None}),
            "providers_reporting_no_cost": sorted(
                set(PROVIDERS) - {r["provider"] for r in rows
                                  if r.get("cost_usd_reported_by_provider")
                                  is not None}),
            "cost_note": (
                "A null cost is 'the provider reported none', never zero. "
                "Converting tokens to dollars needs a per-provider price table, "
                "which U-48 records as an unowned capability; finding 016 "
                "declined to invent one and so does this."),
        },
    }


def render(summary: dict) -> str:
    lines = ["", "E18 — twelve cells: four providers x {A full, B one held, C all held}", ""]
    header = f"{'provider':<11}{'cond':<6}{'verdict':<24}{'errored':<9}{'shape at end':<15}{'states':<8}{'turns':<7}{'answer'}"
    lines += [header, "-" * len(header)]
    for row in summary["rows"]:
        errored = row.get("provider_errored")
        lines.append(
            f"{row['provider']:<11}"
            f"{row['condition']:<6}"
            f"{str(row.get('verdict')):<24}"
            f"{('-' if errored is None else str(errored)):<9}"
            f"{str(row.get('last_request_shape')):<15}"
            f"{str(row.get('state_turns')):<8}"
            f"{str(row.get('turns')):<7}"
            f"{row.get('answer_correct')}")
    totals = summary["totals"]
    lines += [
        "",
        f"controls (row A): {summary['controls']}",
        f"all controls OK: {summary['all_controls_ok']}",
        f"errored under B: {summary['errored']['B']}",
        f"errored under C: {summary['errored']['C']}",
        f"tolerated under B: {summary['tolerated']['B']}",
        f"tolerated under C: {summary['tolerated']['C']}",
        f"untestable: {summary['untestable'] or 'none'}",
        "",
        f"tokens: {totals['input_tokens']} in, {totals['output_tokens']} out",
        f"provider-reported cost: {totals['provider_reported_cost_usd']} USD "
        f"from {totals['providers_reporting_cost']}",
        f"no cost figure from: {totals['providers_reporting_no_cost']} "
        "(tokens only; null is not zero)",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    results = Path(args[0]) if args else Path(__file__).resolve().parent / "results"
    summary = summarize(load(results))
    if "--text" in sys.argv:
        print(render(summary))
    else:
        print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
