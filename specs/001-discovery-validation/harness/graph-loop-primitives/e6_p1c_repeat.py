"""Is the resume boundary stable, or does it depend on what happened to flush?

Repeats the identical crash-and-resume sequence N times per configuration and records,
for each trial, where phase 2 picked up and how many total `work` executions occurred
across both phases. The graph is deterministic and there is no model, so any variation
across trials is attributable to the crash-recovery mechanism alone.

Expected if resume is exactly-once  : total work == 6 every trial
Expected if resume is at-least-once : total work >= 6, varying with flush timing
"""
import json
import os
import re
import subprocess
import sys

import e6_paths

# The interpreter running this file, so the child phases land in the same
# virtualenv without a hardcoded path.
PY = sys.executable
HERE = os.path.dirname(os.path.abspath(__file__))
TRIALS = 5


def run(script, db, ledger):
    for f in (db, ledger):
        if os.path.exists(f):
            os.remove(f)
    script = os.path.join(HERE, script)
    p1 = subprocess.run([PY, script, "phase1"], capture_output=True, text=True)
    p2 = subprocess.run([PY, script, "phase2"], capture_output=True, text=True)
    out = p2.stdout
    trace = re.search(r"phase2 trace\s*:\s*(\[.*?\])", out)
    work2 = re.search(r"phase2 work executions\s*:\s*(\d+)", out)
    state = re.search(r"final state\s*:\s*(\{.*?\})", out)
    led = json.load(open(ledger))
    trace_list = eval(trace.group(1)) if trace else []
    return {
        "killed": p1.returncode == -9 or p1.returncode == 137,
        "work_before_kill": led.get("work_before_kill"),
        "phase2_first_node": trace_list[0] if trace_list else None,
        "phase2_work": int(work2.group(1)) if work2 else None,
        "final_state": state.group(1) if state else None,
    }


for label, script, db, ledger in [
    ("is_resumable=True ", "e6_p1_resume.py", e6_paths.path("e6_sessions.db"),
     e6_paths.path("e6_resume_ledger.json")),
    ("default (False)   ", "e6_p1b_default.py", e6_paths.path("e6_default.db"),
     e6_paths.path("e6_default_ledger.json")),
]:
    print(f"\n{label}")
    totals = []
    for i in range(TRIALS):
        r = run(script, db, ledger)
        total = (r["work_before_kill"] or 0) + (r["phase2_work"] or 0)
        totals.append(total)
        print(f"  trial {i+1}: killed_at_work={r['work_before_kill']} "
              f"phase2_resumed_at={r['phase2_first_node']!r} "
              f"phase2_work={r['phase2_work']} total_work={total} "
              f"state={r['final_state']}")
    print(f"  total work executions across {TRIALS} trials: {totals} "
          f"(exactly-once would be 6 every time)")
