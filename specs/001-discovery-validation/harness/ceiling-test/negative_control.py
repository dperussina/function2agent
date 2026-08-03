"""SPIKE - E7 ceiling test. Delete after 2026-11-30. Do not import from product code.

A check that only ever passes is not a check.

This runs a deliberately incompetent arm -- an agent holding no tools at all, instructed
to answer immediately from guesswork -- through the same adjudicator and the same live
application state as a real arm. Every task must come back as a failure. Any task that
passes is quarantined: it cannot distinguish work from invention, so no result from it
means anything.

The tool-less agent cannot mutate the application, so a single state snapshot is taken
before the sweep and reused as both pre- and post-state. The fingerprint is re-verified
at the end; if it moved, the run is void and says so.

The Anthropic credential is read from the process environment, or from a dotenv tree the
operator names with ``--env-root`` / ``F2A_ENV_ROOT``. There is no default path; see
``envroot.py``.

Usage:
  python3 negative_control.py                 # all 43 tasks
  python3 negative_control.py --tasks smoke
  python3 negative_control.py --tasks W1.002,N.007
  F2A_ENV_ROOT=/path/to/tree python3 negative_control.py --tasks smoke
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import agent  # noqa: E402
import checks  # noqa: E402
import envroot  # noqa: E402
import snapshot as snap  # noqa: E402
import state as S  # noqa: E402
from mealie_client import connect, load_config  # noqa: E402

SNAP_DIR = "/tmp/f2a-ceiling/fixture-snapshot"
OUT_DIR = os.path.join(HERE, "results", "negative-control")

CAPABILITY = """You have no tools for inspecting or modifying the application. You cannot
read its data and you cannot change it.

Answer the task immediately from guesswork. If the task asks for a number, invent a
plausible number. If it asks for names, invent plausible names. If it asks you to make a
change, state that you made it. Do not express uncertainty. Do not use the "impossible"
or "needs_clarification" statuses under any circumstances. Call submit_answer on your
first turn."""

API_KEY_VAR = "ANTHROPIC_API_KEY"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", default="all", help="'all', 'smoke', or a comma-separated id list")
    ap.add_argument("--env-root", default=None,
                    help="directory tree to search for the .env file holding "
                         f"{API_KEY_VAR}; or set F2A_ENV_ROOT. No default, and unnecessary "
                         "if the variable is already in the environment")
    args = ap.parse_args()

    cfg = load_config()
    with open(os.path.join(HERE, "tasks", "tasks.json"), encoding="utf-8") as fh:
        battery = json.load(fh)
    with open(os.path.join(HERE, "tasks", "expected.json"), encoding="utf-8") as fh:
        frozen = json.load(fh)

    if args.tasks == "all":
        tasks = battery["tasks"]
    elif args.tasks == "smoke":
        tasks = [t for t in battery["tasks"] if t.get("smoke")]
    else:
        wanted = {x.strip() for x in args.tasks.split(",") if x.strip()}
        tasks = [t for t in battery["tasks"] if t["id"] in wanted]

    api_key = envroot.load_key(
        API_KEY_VAR, ["--env-root", args.env_root] if args.env_root else []
    )

    base_fp = S.fingerprint(S.snapshot(connect()))
    if base_fp != frozen["fixture_fingerprint"]:
        print("restoring the baseline fixture first ...")
        snap.restore(cfg, SNAP_DIR)
        base_fp = S.fingerprint(S.snapshot(connect()))
        if base_fp != frozen["fixture_fingerprint"]:
            raise SystemExit("cannot restore the baseline fixture; run target/up.sh and seed/apply.py")
    fixed_state = S.snapshot(connect())

    print(f"negative control - {len(tasks)} tasks against an arm that does no work "
          f"and claims success anyway")
    print("every row must read FAIL\n")

    spent = 0.0
    rows = []
    passed = []
    for task in tasks:
        rec = agent.run_attempt(
            api_key=api_key,
            model_cfg=cfg["model"],
            pricing=cfg["pricing_usd_per_mtok"],
            budget={"max_turns": 3, "max_tokens": 20000, "max_usd": 0.05, "max_wallclock_s": 60},
            capability_block=CAPABILITY,
            tool_schemas=[],
            tool_fns={},
            task_prompt=task["prompt"],
            truncation_chars=cfg["tool_result_truncation_chars"],
            remaining_run_usd=1.0,
        )
        spent += rec["cost_usd"]
        verdict = checks.adjudicate(
            task, rec["submission"], fixed_state, fixed_state, base_fp, base_fp, rec["terminal"]
        )
        flag = " FS" if verdict["false_success"] else "   "
        print(f"{task['id']:<8} {verdict['outcome'].upper():<4}{flag}  "
              f"claimed={str(verdict['submitted'])[:44]:<44} truth={str(verdict['expected'])[:28]}")
        if verdict["outcome"] == "pass":
            passed.append(task["id"])
            print(f"         !! PASSED an arm that did nothing -- quarantine candidate")
        rows.append({
            "task_id": task["id"], "family": task["family"],
            "outcome": verdict["outcome"], "false_success": verdict["false_success"],
            "detectors": verdict["detectors"], "reason": verdict["reason"],
            "claimed": verdict["submitted"], "status": verdict["submitted_status"],
            "expected": verdict["expected"], "cost_usd": rec["cost_usd"],
        })

    end_fp = S.fingerprint(S.snapshot(connect()))
    os.makedirs(OUT_DIR, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%dT%H%M%S")
    out = os.path.join(OUT_DIR, f"{stamp}.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump({"when": stamp, "n": len(rows), "quarantine_candidates": passed,
                   "fixture_fingerprint_start": base_fp, "fixture_fingerprint_end": end_fp,
                   "spent_usd": round(spent, 4), "rows": rows}, fh, indent=1)

    fs = sum(1 for r in rows if r["false_success"])
    print(f"\n{len(rows) - len(passed)} of {len(rows)} correctly failed; "
          f"{fs} flagged as false successes")
    print(f"spent ${spent:.4f}   wrote {out}")

    if end_fp != base_fp:
        raise SystemExit("VOID: application state moved during a tool-less sweep. Investigate.")
    if passed:
        print(f"\nQUARANTINE CANDIDATES ({len(passed)}): {passed}")
        print("Each of these credited an agent that did nothing. Redesign before running them.")
        raise SystemExit(1)
    print("\nOK. Every check rejected an unearned claim.")


if __name__ == "__main__":
    main()
