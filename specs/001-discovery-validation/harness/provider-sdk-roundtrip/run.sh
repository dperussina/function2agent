#!/usr/bin/env bash
# SPIKE - E16 provider-SDK opaque-state round-trip.
#
# Runs the four arms, the negative control, and the two free probes, writing
# one JSON artifact per step into results/.
#
# Requires a dotenv search root. There is no default and this script will not
# guess one:
#
#   export F2A_ENV_ROOT=/path/to/tree
#   export F2A_GEMINI_VAR=GEMINI_API_KEY_2   # optional; see finding 002
#   ./run.sh
#
# Model spend: four arms plus one control, three turns each, on small prompts.
# The measured total is in results/SUMMARY.json and in the finding. No
# credential value is printed, logged, or written by anything here.
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

echo "== free probes (no model spend) =="
"$PYTHON" list_models.py         > "$OUT/models.json"        2>"$OUT/models.err"        || true
"$PYTHON" count_vendor_fields.py > "$OUT/field-counts.json"  2>"$OUT/field-counts.err"  || true

echo "== four arms =="
for provider in anthropic openai google xai; do
  echo "-- $provider"
  "$PYTHON" "arm_${provider}.py" > "$OUT/arm-${provider}.json" 2>"$OUT/arm-${provider}.err"
  status=$?
  if [[ $status -eq 2 ]]; then
    echo "   ENVIRONMENTAL FAILURE - nothing was measured for $provider" >&2
  fi
done

echo "== supplementary: adaptive thinking emits no opaque state on a trivial task =="
# Not a fifth provider. Same provider, newer model, different thinking mode.
# claude-sonnet-5 rejects the enabled-thinking request shape and, under
# adaptive, declines to think about a task this small — so it emits nothing to
# round-trip. Committed because "the provider emitted no opaque state" is a
# state a driver must handle, and it is invisible if only the default model runs.
"$PYTHON" arm_anthropic.py --model claude-sonnet-5 \
  > "$OUT/supplementary-anthropic-sonnet5.json" 2>"$OUT/supplementary-anthropic-sonnet5.err"

echo "== supplementary: is opaque state emitted deterministically? =="
"$PYTHON" repeat_adaptive.py > "$OUT/repeat-adaptive.json" 2>"$OUT/repeat-adaptive.err"

echo "== negative control =="
"$PYTHON" negative_control.py > "$OUT/negative-control.json" 2>"$OUT/negative-control.err"

echo "== summary =="
"$PYTHON" summarize.py "$OUT" > "$OUT/SUMMARY.json"
"$PYTHON" summarize.py "$OUT" --text
