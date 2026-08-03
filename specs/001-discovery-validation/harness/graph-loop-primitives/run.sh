#!/usr/bin/env bash
#
# Reproduce Finding 006 — E6, does ADK supply the loop-safety machinery?
#
# Model spend: roughly $0.0003. Twelve of the fourteen arms use pure Python
# function nodes and cost nothing; only the two budget arms call a model, and
# they call it nine times with single-word prompts. The trap that proves ADK has
# no step ceiling burns over a thousand graph iterations for $0.
#
# Several arms SIGKILL their own process on purpose. That is the measurement:
# no finally block, no atexit hook, no graceful shutdown, which is what a crash
# actually looks like. A "Killed: 9" line in the output is expected.
#
# Usage:  ./run.sh [arm ...]
#
# Arms:  p1 p2 p3 p4 p5          (default: p1 p2 p4 p5 — the zero-cost set)
#        p3 additionally needs credentials; see below.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
E5="$(cd "$HERE/../runtime-provider-agnosticism" && pwd)"
SCRATCH="${F2A_PROBE_DIR:-/tmp/f2a-probe-runtime}"
VENV="$SCRATCH/.venv"

export F2A_PROBE_DIR="$SCRATCH"
mkdir -p "$SCRATCH"

# E6 reuses E5's virtualenv, exactly as the original probe did — finding 006's
# method note says the environment was "reused rather than rebuilt".
if [ ! -x "$VENV/bin/python" ]; then
  echo "== building the shared virtualenv at $VENV from the E5 pins"
  "${PYTHON:-python3.12}" -m venv "$VENV"
  "$VENV/bin/pip" install --quiet --upgrade pip
  "$VENV/bin/pip" install --quiet -r "$E5/requirements.txt"
fi
PY="$VENV/bin/python"

echo "== interpreter : $("$PY" --version)"
echo "== google-adk  : $("$PY" -c 'import importlib.metadata as m; print(m.version("google-adk"))')"
echo "== scratch     : $SCRATCH"

ARMS=("$@")
if [ ${#ARMS[@]} -eq 0 ]; then
  ARMS=(p1 p2 p4 p5)
fi

banner() {
  echo
  echo "======================================================================"
  echo "== $*"
  echo "======================================================================"
}

# A two-phase arm: phase 1 kills itself, phase 2 resumes from the persisted
# session. The `|| true` is load-bearing — phase 1 exiting 137 is the point.
crash_and_resume() {
  local script="$1"; shift
  local label="$1"; shift
  echo
  echo "-- $label"
  "$PY" "$HERE/$script" phase1 || true
  "$PY" "$HERE/$script" phase2
}

for arm in "${ARMS[@]}"; do
  case "$arm" in
    p1)
      banner "Primitive 1 — checkpoint and resume"
      rm -f "$SCRATCH"/e6_sessions.db "$SCRATCH"/e6_resume_ledger.json
      crash_and_resume e6_p1_resume.py "kill at a node boundary, is_resumable=True"
      rm -f "$SCRATCH"/e6_default.db "$SCRATCH"/e6_default_ledger.json
      crash_and_resume e6_p1b_default.py "the same crash, default config (is_resumable=False)"
      rm -f "$SCRATCH"/e6_mid.db "$SCRATCH"/e6_mid_ledger.json
      crash_and_resume e6_p1d_midnode.py "kill INSIDE a node, after its durable side effect"
      echo
      echo "-- is the resume boundary stable? 5 trials per configuration"
      "$PY" "$HERE/e6_p1c_repeat.py"
      ;;
    p2)
      banner "Primitive 2 — named terminal conditions"
      "$PY" "$HERE/e6_p2_terminals.py"
      echo
      echo "-- can a cancelled run be told from a completed one? (flag on)"
      "$PY" "$HERE/e6_p2b_cancel.py"
      ;;
    p3)
      banner "Primitive 3 — budget enforcement  (THIS ARM CALLS A MODEL)"
      if [ -z "${F2A_ENV_ROOT:-}" ]; then
        echo "   SKIPPED: F2A_ENV_ROOT is not set."
        echo "   The two budget arms need a Google credential — whether max_llm_calls"
        echo "   actually halts a run is the one question a model must answer."
        echo "   See ../runtime-provider-agnosticism/README.md."
        continue
      fi
      echo "-- does ADK enforce any graph-step ceiling of its own? (zero cost, 20s)"
      "$PY" "$HERE/e6_p3a_steps.py"
      echo
      echo "-- is max_llm_calls real enforcement? (ceiling of 3)"
      "$PY" "$HERE/e6_p3b_budget.py"
      echo
      echo "-- does that budget survive a resume?"
      "$PY" "$HERE/e6_p3c_budget_resume.py"
      ;;
    p4)
      banner "Primitive 4 — deterministic replay"
      echo "-- 4 replays from byte-identical copies of one post-crash snapshot"
      "$PY" "$HERE/e6_p4_replay.py"
      echo
      echo "-- fan-out, well-separated branch latencies"
      "$PY" "$HERE/e6_p4b_parallel.py"
      echo
      echo "-- fan-out, overlapping jittered latencies"
      "$PY" "$HERE/e6_p4c_jitter.py"
      ;;
    p5)
      banner "Hosting our own loop inside an ADK node"
      rm -f "$SCRATCH"/e6_host.db "$SCRATCH"/e6_host_ledger.json
      crash_and_resume e6_p5_hostloop.py "A) inner-loop granularity across a crash"
      echo
      echo "-- B) two parallel branches append to one state key (lost update)"
      "$PY" "$HERE/e6_p5b_race.py" stateonly
      ;;
    *)
      echo "unknown arm: $arm" >&2; exit 2 ;;
  esac
done

echo
echo "== done. Compare against the quoted output in findings/006-graph-loop-primitives.md"
echo "== and the raw artifacts in $HERE/results/ (see the README for what they are)."
