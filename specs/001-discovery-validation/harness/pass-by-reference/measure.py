"""SPIKE - E17 pass-by-reference. Delete after 2026-11-30. Do not import from product code.

Measure the battery against the generated corpus. No provider, no network, $0.00.

This is the step that stops the projection being a guess. The quantity the whole
experiment turns on is *how many bytes a bulk command prints*, and that is knowable
for free: generate the corpus, run the plans, count the bytes. The projection then
divides measured bytes by a declared divisor instead of asserting a token count.

It also runs the cross-check that licenses the battery at all: for every task, the
shell plan's answer and the Python checker's answer must agree. They are two
independent computations sharing no code, and a disagreement means the battery is
broken — which is a thing to find now, not after buying tokens.

Usage:  python3 measure.py [--root DIR] [--json]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile

import corpus
import tasks

HERE = os.path.dirname(os.path.abspath(__file__))


def load_config() -> dict:
    with open(os.path.join(HERE, "config.json")) as fh:
        return json.load(fh)


def measure(root: str, cfg: dict) -> dict:
    """Run every plan step, record its stdout size, and cross-check every answer."""
    threshold = cfg["turn_model"]["bulk_threshold_bytes"]
    out: dict = {"dry_run": True, "model_calls": 0, "spend_usd": 0.0, "tasks": {}}

    for task in list(tasks.TASKS) + [tasks.SENTINEL]:
        steps = []
        for step in task.plan:
            stdout, stderr, rc = tasks.run_step(root, step.cmd)
            steps.append({
                "label": step.label,
                "cmd": step.cmd,
                "stdout_bytes": len(stdout),
                "stderr_bytes": len(stderr),
                "returncode": rc,
                "bulk": len(stdout) > threshold,
            })
        plan_answer = tasks.answer_from_plan(root, task)
        check_answer = task.check(root)
        out["tasks"][task.id] = {
            "family": task.family,
            "steps": steps,
            "bulk_steps": sum(1 for s in steps if s["bulk"]),
            "total_stdout_bytes": sum(s["stdout_bytes"] for s in steps),
            "plan_answer": plan_answer,
            "check_answer": check_answer,
            "cross_check": "agree" if plan_answer == check_answer else "DISAGREE",
        }
    out["cross_check_failures"] = sorted(
        tid for tid, t in out["tasks"].items() if t["cross_check"] != "agree")
    return out


def build(root: str | None = None) -> tuple[dict, dict]:
    """Generate the corpus and measure it. Returns ``(manifest, measurements)``."""
    cfg = load_config()
    spec = corpus.CorpusSpec(seed=cfg["corpus"]["seed"],
                             expected_total_bytes=cfg["corpus"]["expected_total_bytes"])
    tmp = root or os.path.join(tempfile.gettempdir(), f"e17-corpus-{spec.seed}")
    man = corpus.generate(tmp, spec)
    meas = measure(tmp, cfg)
    meas["corpus_root"] = tmp
    meas["corpus_total_bytes"] = man["total_bytes"]
    meas["corpus_file_count"] = man["file_count"]
    return man, meas


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=None, help="where to generate the corpus")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    man, meas = build(args.root)
    if args.json:
        print(json.dumps({"manifest": man, "measurements": meas}, indent=2))
        return 0

    print(f"corpus root        : {meas['corpus_root']}")
    print(f"corpus files       : {man['file_count']}")
    print(f"corpus bytes       : {man['total_bytes']:,}")
    print()
    print(f"{'task':<6} {'family':<9} {'bulk':>5} {'stdout bytes':>14}  answer")
    for tid, t in meas["tasks"].items():
        mark = "" if t["cross_check"] == "agree" else "  <-- CROSS-CHECK DISAGREE"
        print(f"{tid:<6} {t['family']:<9} {t['bulk_steps']:>5} "
              f"{t['total_stdout_bytes']:>14,}  {t['plan_answer'][:32]}{mark}")
    print()
    if meas["cross_check_failures"]:
        print(f"cross-check FAILURES: {meas['cross_check_failures']}")
        return 1
    print(f"cross-check        : all {len(meas['tasks'])} tasks agree "
          f"(shell plan vs independent Python checker)")
    print("model calls        : 0    spend: $0.00")
    return 0


if __name__ == "__main__":
    sys.exit(main())
