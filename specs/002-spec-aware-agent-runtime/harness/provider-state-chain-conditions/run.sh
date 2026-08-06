#!/usr/bin/env bash
# SPIKE - E18. Twelve arms: four providers x {A full chain, B one state held,
# C all states held}, over the six-turn dependent chain T061's cassettes use.
#
# Designed in specs/002-spec-aware-agent-runtime/findings/
#   030-provider-state-chain-derived-not-measured.md §6.
#
#   export F2A_ENV_ROOT=/path/to/tree        # required, no default
#   export F2A_GEMINI_VAR=GEMINI_API_KEY_2   # required on some trees, finding 002
#   ./run.sh [output-dir]                    # defaults to results/
#
# `F2A_PYTHON` selects the interpreter; it needs the four vendor SDKs and must
# not be the repository's own .venv, which deliberately has none of them.
#
# ORDER IS LOAD-BEARING. Every provider's row A runs first, and B and C are
# skipped for any provider whose A did not come back OK. Row A is the control
# that makes a 400 in B or C attributable to the withheld state rather than to
# a malformed request, a dead credential or a rejected model — Rule 8 of the
# experiment-design skill. Spending on B and C behind a broken control buys
# twelve unreadable cells.
#
# There is no retry anywhere: B and C error by design, and a retry loop on a
# 400 is the failure mode that spends a ceiling without producing a reading.
# No credential value is printed, logged, or written by anything here.
set -uo pipefail

cd "$(dirname "$0")"

PYTHON="${F2A_PYTHON:-python3}"
OUT="${1:-results}"
mkdir -p "$OUT"

if [[ -z "${F2A_ENV_ROOT:-}" ]]; then
  echo "F2A_ENV_ROOT is not set. Name a tree holding the provider dotenv files:" >&2
  echo "  export F2A_ENV_ROOT=/path/to/tree" >&2
  echo "The tree is read, never written. No credential value is ever printed." >&2
  exit 64
fi

PROVIDERS=(anthropic openai google xai)

# The declared run-level ceiling lives in this file and every arm reads it
# before it starts. See conditions.py's LEDGER_MAX_* for the numbers and why a
# per-arm cap is not a ceiling.
export F2A_E18_LEDGER="$PWD/$OUT/budget.json"

echo "== selfcheck (no model spend) =="
"$PYTHON" selfcheck.py > "$OUT/selfcheck.txt" 2>&1
if [[ $? -ne 0 ]]; then
  echo "   SELFCHECK FAILED — see $OUT/selfcheck.txt. Nothing was spent." >&2
  exit 65
fi
echo "   ok"

verdict_of() {
  "$PYTHON" -c "import json,sys; print(json.load(open(sys.argv[1])).get('verdict','MISSING'))" "$1" 2>/dev/null || echo "UNPARSEABLE"
}

echo "== row A: the full-chain control, four providers =="
for provider in "${PROVIDERS[@]}"; do
  echo "-- $provider A"
  "$PYTHON" "arm_${provider}.py" --condition A \
    > "$OUT/arm-${provider}-A.json" 2>"$OUT/arm-${provider}-A.err"
  echo "   $(verdict_of "$OUT/arm-${provider}-A.json")"
done

echo "== rows B and C, only behind a control that came back OK =="
for condition in B C; do
  for provider in "${PROVIDERS[@]}"; do
    control="$(verdict_of "$OUT/arm-${provider}-A.json")"
    if [[ "$control" != "OK" ]]; then
      echo "-- $provider $condition SKIPPED — its control read $control"
      continue
    fi
    echo "-- $provider $condition"
    "$PYTHON" "arm_${provider}.py" --condition "$condition" \
      > "$OUT/arm-${provider}-${condition}.json" 2>"$OUT/arm-${provider}-${condition}.err"
    echo "   $(verdict_of "$OUT/arm-${provider}-${condition}.json")"
  done
done

echo "== summary =="
"$PYTHON" summarize.py "$OUT" > "$OUT/SUMMARY.json"
"$PYTHON" summarize.py "$OUT" --text | tee "$OUT/SUMMARY.txt"
