"""SPIKE - E7 ceiling test. Delete after 2026-11-30. Do not import from product code.

The experiment driver. Runs (arm x task x attempt), adjudicates every attempt against the
application's observable state, and records everything.

Per attempt it records outcome, the terminal condition **by name**, wall-clock time,
turns, tokens (input/output/cache split), and cost (FR-002). It enforces a per-attempt and
a whole-run spend ceiling and halts rather than exceeding either (FR-021).

The Anthropic credential is read from the process environment, or from a dotenv tree the
operator names with ``--env-root`` / ``F2A_ENV_ROOT``. There is no default path; see
``envroot.py``.

Usage
  python3 runner.py --tasks smoke --arms A B --max-usd 10
  python3 runner.py --tasks all   --arms A B --attempts 3 --max-usd 120
  python3 runner.py --tasks R2.001,N.003 --arms B
  F2A_ENV_ROOT=/path/to/tree python3 runner.py --tasks smoke
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import agent  # noqa: E402
import arms as arms_mod  # noqa: E402
import checks  # noqa: E402
import envroot  # noqa: E402
import snapshot as snap  # noqa: E402
import state as S  # noqa: E402
from mealie_client import connect, load_config  # noqa: E402

TASKS_PATH = os.path.join(HERE, "tasks", "tasks.json")
EXPECTED_PATH = os.path.join(HERE, "tasks", "expected.json")
RESULTS_DIR = os.path.join(HERE, "results")
SNAP_DIR = "/tmp/f2a-ceiling/fixture-snapshot"

API_KEY_VAR = "ANTHROPIC_API_KEY"


def harness_fingerprint(tool_surface: str = "v2") -> str:
    """Hash of every harness source file that can change a result. Results with different
    fingerprints must not be pooled (research/11-validation-plan.md 9.3).

    The tool surface is folded in because v1 and v2 share one source file and would otherwise
    fingerprint identically while being different treatments."""
    h = hashlib.sha256()
    h.update(f"tool_surface={tool_surface}\n".encode())
    for rel in sorted(
        [
            "agent.py", "arms.py", "checks.py", "runner.py", "state.py",
            "mealie_client.py", "snapshot.py",
            os.path.join("tools", "mealie_tools.py"),
            os.path.join("tasks", "tasks.json"),
            "config.json",
        ]
    ):
        with open(os.path.join(HERE, rel), "rb") as fh:
            h.update(rel.encode())
            h.update(fh.read())
    return h.hexdigest()[:16]


def select_tasks(battery: dict, spec: str) -> list[dict]:
    tasks = battery["tasks"]
    if spec == "all":
        return tasks
    if spec == "smoke":
        return [t for t in tasks if t.get("smoke")]
    wanted = {x.strip() for x in spec.split(",") if x.strip()}
    chosen = [t for t in tasks if t["id"] in wanted]
    missing = wanted - {t["id"] for t in chosen}
    if missing:
        raise SystemExit(f"unknown task ids: {sorted(missing)}")
    return chosen


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", default="smoke", help="'all', 'smoke', or a comma-separated id list")
    ap.add_argument("--arms", nargs="+", default=["A", "B"], choices=["A", "B"])
    ap.add_argument("--attempts", type=int, default=None)
    ap.add_argument("--max-usd", type=float, default=None, help="whole-run spend ceiling")
    ap.add_argument("--label", default="", help="short label for the results directory")
    ap.add_argument("--tool-surface", default="v2", choices=["v1", "v2"],
                    help="arm A's tool set: v1 = the twenty tools frozen 2026-08-02 15:10; "
                         "v2 = v1 plus aggregate_recipes (preregistration A5)")
    ap.add_argument("--env-root", default=None,
                    help="directory tree to search for the .env file holding "
                         f"{API_KEY_VAR}; or set F2A_ENV_ROOT. No default, and unnecessary "
                         "if the variable is already in the environment")
    args = ap.parse_args()

    cfg = load_config()
    with open(TASKS_PATH, encoding="utf-8") as fh:
        battery = json.load(fh)
    with open(EXPECTED_PATH, encoding="utf-8") as fh:
        frozen = json.load(fh)

    attempts = args.attempts or cfg["attempts_per_task"]
    run_ceiling = args.max_usd if args.max_usd is not None else cfg["budgets"]["run_total_max_usd"]
    tasks = select_tasks(battery, args.tasks)
    api_key = envroot.load_key(
        API_KEY_VAR, ["--env-root", args.env_root] if args.env_root else []
    )

    run_id = datetime.datetime.now().strftime("%Y%m%dT%H%M%S") + (f"-{args.label}" if args.label else "")
    out_dir = os.path.join(RESULTS_DIR, run_id)
    os.makedirs(out_dir, exist_ok=True)
    fingerprint = harness_fingerprint(args.tool_surface)

    # baseline fixture: snapshot it once, verify it matches the frozen battery
    api = connect()
    base_state = S.snapshot(api)
    base_fp = S.fingerprint(base_state)
    if base_fp != frozen["fixture_fingerprint"]:
        raise SystemExit(
            "FIXTURE DRIFT: the running instance does not match the frozen battery.\n"
            f"  expected {frozen['fixture_fingerprint']}\n  got      {base_fp}\n"
            "Re-run target/up.sh then seed/apply.py, or re-freeze with tasks/validate_battery.py.\n"
            "Running against a drifted fixture would void the result."
        )
    for tid, want in frozen["expected"].items():
        task = next((t for t in battery["tasks"] if t["id"] == tid), None)
        if task and checks.expected_value(task, base_state) != want:
            raise SystemExit(f"FIXTURE DRIFT: expected value for {tid} no longer matches the frozen file.")
    if not os.path.exists(os.path.join(SNAP_DIR, "mealie.db")):
        print("taking fixture snapshot for write-task restore ...")
        snap.take(cfg, SNAP_DIR)

    manifest = {
        "run_id": run_id,
        "started": datetime.datetime.now().isoformat(timespec="seconds"),
        "harness_fingerprint": fingerprint,
        "harness_version": cfg["harness_version"],
        "battery_version": battery["battery_version"],
        "tool_surface": args.tool_surface,
        "fixture_fingerprint": base_fp,
        "model": cfg["model"],
        "pricing_usd_per_mtok": cfg["pricing_usd_per_mtok"],
        "budgets": cfg["budgets"],
        "run_ceiling_usd": run_ceiling,
        "attempts_per_task": attempts,
        "arms": args.arms,
        "task_ids": [t["id"] for t in tasks],
        "target": {k: cfg["target"][k] for k in ("name", "image", "app_version", "internal_url")},
    }
    with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=1)

    print(f"run {run_id}")
    print(f"  harness {fingerprint}  battery {battery['battery_version']}  fixture {base_fp[:16]}")
    print(f"  model {cfg['model']['id']}  arms {args.arms}  tasks {len(tasks)}  attempts {attempts}")
    if "A" in args.arms:
        print(f"  arm A tool surface {args.tool_surface}")
    print(f"  run ceiling ${run_ceiling:.2f}")
    print()

    results_path = os.path.join(out_dir, "results.jsonl")
    traces_path = os.path.join(out_dir, "traces.jsonl")
    spent = 0.0
    halted = False

    for attempt_no in range(1, attempts + 1):
        for task in tasks:
            for arm in args.arms:
                if spent >= run_ceiling:
                    print(f"\nHALT: run ceiling ${run_ceiling:.2f} reached (spent ${spent:.4f}). "
                          f"Remaining work not attempted.")
                    halted = True
                    break

                # identical start state before every attempt
                api = connect()
                pre_state = S.snapshot(api)
                pre_fp = S.fingerprint(pre_state)
                if pre_fp != base_fp:
                    print("   (restoring fixture)", flush=True)
                    snap.restore(cfg, SNAP_DIR)
                    api = connect()
                    pre_state = S.snapshot(api)
                    pre_fp = S.fingerprint(pre_state)
                    if pre_fp != base_fp:
                        raise SystemExit("fixture restore did not reproduce the baseline state")

                budget = cfg["budgets"]["arm_a" if arm == "A" else "arm_b"]
                if arm == "A":
                    capability, schemas, fns = arms_mod.build_arm_a(api, surface=args.tool_surface)
                else:
                    arms_mod.start_shell_sandbox(cfg, api.token)
                    capability, schemas, fns = arms_mod.build_arm_b(cfg)

                print(f"[{attempt_no}] {task['id']:<8} arm {arm} ...", end=" ", flush=True)
                t0 = time.time()
                try:
                    rec = agent.run_attempt(
                        api_key=api_key,
                        model_cfg=cfg["model"],
                        pricing=cfg["pricing_usd_per_mtok"],
                        budget=budget,
                        capability_block=capability,
                        tool_schemas=schemas,
                        tool_fns=fns,
                        task_prompt=task["prompt"],
                        truncation_chars=cfg["tool_result_truncation_chars"],
                        remaining_run_usd=run_ceiling - spent,
                    )
                except Exception as exc:  # noqa: BLE001
                    rec = {
                        "submission": None, "terminal": "harness_error", "turns": 0,
                        "tokens": {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0},
                        "tokens_total": 0, "cost_usd": 0.0, "wall_s": round(time.time() - t0, 2),
                        "tool_calls": [], "distinct_tools_used": [],
                        "transcript": [{"role": "harness", "error": f"{type(exc).__name__}: {exc}"}],
                    }
                finally:
                    if arm == "B":
                        arms_mod.stop_shell_sandbox(cfg)

                spent += rec["cost_usd"]
                post_state = S.snapshot(connect())
                post_fp = S.fingerprint(post_state)
                verdict = checks.adjudicate(
                    task, rec["submission"], pre_state, post_state, pre_fp, post_fp, rec["terminal"]
                )

                row = {
                    "run_id": run_id, "attempt": attempt_no, "arm": arm,
                    "task_id": task["id"], "family": task["family"],
                    "outcome": verdict["outcome"],
                    "false_success": verdict["false_success"],
                    "detectors": verdict["detectors"],
                    "reason": verdict["reason"],
                    "expected": verdict["expected"],
                    "submitted_status": verdict["submitted_status"],
                    "submitted": verdict["submitted"],
                    "terminal": rec["terminal"],
                    "turns": rec["turns"],
                    "tokens": rec["tokens"],
                    "tokens_total": rec["tokens_total"],
                    "cost_usd": rec["cost_usd"],
                    "wall_s": rec["wall_s"],
                    "tool_call_count": len(rec["tool_calls"]),
                    "distinct_tools_used": rec["distinct_tools_used"],
                    "state_changed": pre_fp != post_fp,
                    "harness_fingerprint": fingerprint,
                    "tool_surface": args.tool_surface if arm == "A" else None,
                    "model_id": cfg["model"]["id"],
                }
                with open(results_path, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps(row) + "\n")
                with open(traces_path, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps({**row, "tool_calls": rec["tool_calls"],
                                         "transcript": rec["transcript"]}) + "\n")

                flag = " FALSE-SUCCESS" if verdict["false_success"] else ""
                print(
                    f"{verdict['outcome'].upper():4s}{flag}  {rec['terminal']}  "
                    f"turns={rec['turns']} tok={rec['tokens_total']} ${rec['cost_usd']:.4f} "
                    f"{rec['wall_s']:.0f}s"
                )
                if verdict["outcome"] == "fail" and verdict["reason"]:
                    print(f"          -> {verdict['reason'][:150]}")
            if halted:
                break
        if halted:
            break

    # Leave the application on the frozen baseline. The loop restores *before* an attempt,
    # so without this a run that ends on a write task leaves the fixture dirty, and anything
    # that reads live state afterwards -- including the battery validator -- silently works
    # from contaminated data.
    if S.fingerprint(S.snapshot(connect())) != base_fp:
        print("restoring the fixture to the frozen baseline ...")
        snap.restore(cfg, SNAP_DIR)
        if S.fingerprint(S.snapshot(connect())) != base_fp:
            print("WARNING: could not restore the baseline fixture; re-seed before the next run")

    print(f"\nspent ${spent:.4f} of ${run_ceiling:.2f} ceiling")
    print(f"results: {results_path}")
    summarise(results_path)


EXHAUSTION_TERMINALS = {
    "max_turns_exhausted", "token_budget_exhausted", "cost_budget_exhausted",
    "wall_clock_exhausted",
}


def summarise(results_path: str) -> None:
    """Every rate is printed with the raw counts that produced it.

    Budget exhaustion is reported separately from failure throughout. "Could not finish
    within budget" and "got it wrong" are different outcomes and mean different things for
    the product; conflating them would flatter whichever arm has the tighter allowance.
    """
    rows = [json.loads(x) for x in open(results_path, encoding="utf-8")]
    if not rows:
        return
    arms_seen = sorted({r["arm"] for r in rows})

    print("\n=== per arm ===")
    print(f"{'arm':<4}{'n':>5}{'pass':>6}{'TSR':>17}{'false success':>20}"
          f"{'budget exhausted':>21}{'tok/solved':>12}{'$/task':>9}{'$/solved':>10}{'turns':>7}")
    for arm in arms_seen:
        a = [r for r in rows if r["arm"] == arm]
        passed = [r for r in a if r["outcome"] == "pass"]
        failed = [r for r in a if r["outcome"] == "fail"]
        fs = [r for r in a if r["false_success"]]
        ex = [r for r in a if r["terminal"] in EXHAUSTION_TERMINALS]
        tsr = f"{len(passed)}/{len(a)} ({len(passed) / len(a):.0%})"
        fsr = (f"{len(fs)}/{len(failed)} ({len(fs) / len(failed):.0%})") if failed else "0/0 (n/a)"
        exr = f"{len(ex)}/{len(a)} ({len(ex) / len(a):.0%})"
        spend = sum(r["cost_usd"] for r in a)
        tps = round(sum(r["tokens_total"] for r in a) / len(passed)) if passed else float("inf")
        # Cost per solved task is the secondary metric (OD-04). It charges an arm for the
        # attempts it wasted as well as the ones it landed, which is the honest way to keep
        # the efficiency question alive now that the budget asymmetry has narrowed.
        cps = f"{spend / len(passed):.4f}" if passed else "n/a"
        print(f"{arm:<4}{len(a):>5}{len(passed):>6}{tsr:>17}{fsr:>20}{exr:>21}"
              f"{tps:>12}{spend / len(a):>9.4f}{cps:>10}"
              f"{sum(r['turns'] for r in a) / len(a):>7.1f}")

    print("\n=== per family (pass / attempts) ===")
    fams = sorted({r["family"] for r in rows})
    print(f"{'arm':<4}" + "".join(f"{f:>14}" for f in fams))
    for arm in arms_seen:
        cells = []
        for f in fams:
            a = [r for r in rows if r["arm"] == arm and r["family"] == f]
            p = sum(1 for r in a if r["outcome"] == "pass")
            cells.append(f"{p}/{len(a)}" if a else "-")
        print(f"{arm:<4}" + "".join(f"{c:>14}" for c in cells))

    print("\n=== terminal conditions ===")
    for arm in arms_seen:
        counts: dict[str, int] = {}
        for r in rows:
            if r["arm"] == arm:
                counts[r["terminal"]] = counts.get(r["terminal"], 0) + 1
        parts = ", ".join(f"{k} {v}" for k, v in sorted(counts.items(), key=lambda kv: -kv[1]))
        print(f"  arm {arm}: {parts}")

    # Per-task variance across attempts: how often the same arm disagrees with itself on
    # the same task. This is the noise floor the pre-registration requires an effect to clear.
    print("\n=== model variance across attempts ===")
    for arm in arms_seen:
        by_task: dict[str, list[str]] = {}
        for r in rows:
            if r["arm"] == arm:
                by_task.setdefault(r["task_id"], []).append(r["outcome"])
        repeated = {k: v for k, v in by_task.items() if len(v) > 1}
        if not repeated:
            print(f"  arm {arm}: single attempt per task; no variance measurable")
            continue
        split = {k: v for k, v in repeated.items() if len(set(v)) > 1}
        n_att = max(len(v) for v in repeated.values())
        all_pass = sum(1 for v in repeated.values() if all(x == "pass" for x in v))
        per_round = []
        for i in range(n_att):
            got = [v[i] for v in repeated.values() if len(v) > i]
            per_round.append(sum(1 for g in got if g == "pass") / len(got))
        floor = (max(per_round) - min(per_round)) if len(per_round) > 1 else 0.0
        print(f"  arm {arm}: {len(split)}/{len(repeated)} tasks unstable across attempts; "
              f"pass^{n_att} = {all_pass}/{len(repeated)} ({all_pass / len(repeated):.0%}); "
              f"per-round TSR " + ", ".join(f"{p:.0%}" for p in per_round) +
              f"; noise floor {floor * 100:.1f} pp")
        if split:
            print(f"    unstable: {sorted(split)}")


if __name__ == "__main__":
    main()
