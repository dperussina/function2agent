"""Primitive 4: given one checkpoint, does replay produce the same trajectory?

Model nondeterminism is not what is under test. The graph is driven by deterministic
Python nodes plus a *stubbed* model whose outputs are fixed, so any variation in the
replayed trajectory is attributable to the graph mechanics alone.

Method: crash once, snapshot the SQLite session file, then resume N times from byte-
identical copies of that snapshot and compare the resulting node-execution traces.
Identical traces across all replays is the pass condition.

Zero model spend: the LLM node is a stub that returns a fixed string.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys

import e6_paths

# The interpreter running this file, so the child phases land in the same
# virtualenv without a hardcoded path.
PY = sys.executable
HERE = os.path.dirname(os.path.abspath(__file__))
SNAP = e6_paths.path("e6_replay_snapshot.db")
DB = e6_paths.path("e6_sessions.db")
LEDGER = e6_paths.path("e6_resume_ledger.json")
LEDGER_SNAP = e6_paths.path("e6_replay_ledger.json")
REPLAYS = 4


def sh(*args, **kw):
    return subprocess.run(list(args), capture_output=True, text=True, **kw)


# 1. Produce a crash and snapshot the resulting session state.
for f in (DB, LEDGER):
    if os.path.exists(f):
        os.remove(f)
p1 = sh(PY, os.path.join(HERE, "e6_p1_resume.py"), "phase1")
if not os.path.exists(DB):
    print("phase1 did not produce a session db")
    sys.exit(1)
shutil.copy(DB, SNAP)
shutil.copy(LEDGER, LEDGER_SNAP)
snap_hash = hashlib.sha256(open(SNAP, "rb").read()).hexdigest()[:12]
print(f"snapshot taken after crash: {os.path.getsize(SNAP)} bytes, sha256={snap_hash}")

# 2. Replay from byte-identical copies of that snapshot.
traces, states = [], []
for i in range(REPLAYS):
    shutil.copy(SNAP, DB)
    shutil.copy(LEDGER_SNAP, LEDGER)
    restored = hashlib.sha256(open(DB, "rb").read()).hexdigest()[:12]
    r = sh(PY, os.path.join(HERE, "e6_p1_resume.py"), "phase2")
    t = re.search(r"phase2 trace\s*:\s*(\[.*?\])", r.stdout)
    s = re.search(r"final session state\s*:\s*(\{.*?\})", r.stdout)
    trace = eval(t.group(1)) if t else None
    traces.append(trace)
    states.append(s.group(1) if s else None)
    print(f"  replay {i+1}: input_db_sha={restored} trace={trace}")

print(f"\nfinal states: {states}")
identical = all(t == traces[0] for t in traces) and all(x == states[0] for x in states)
print(f"\nVERDICT: {'PASS - all replays identical' if identical else 'FAIL - trajectories diverged'}")
print(f"distinct traces observed: {len({json.dumps(t) for t in traces})} of {REPLAYS}")
