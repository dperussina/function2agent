#!/usr/bin/env bash
# Reproduce finding 007 — contract extraction (E4).
#
# Assumes the recall harness (../recall-adk-fastapi/run.sh) has already run and
# left a fresh index and an isolated virtualenv in $SCRATCH. Everything happens
# on copies and nothing under examples/ is written to.
#
#   ./run.sh [scratch-dir]
#   TS_DB=/path/to/.codegraph/codegraph.db ./run.sh   # adds the secondary measurement

set -euo pipefail

SCRATCH="${1:-/tmp/f2a-recall}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="$HERE/results"
REPO="$SCRATCH/adk-python"
DB="$REPO/.codegraph/codegraph.db"
PY="$SCRATCH/.venv-adk/bin/python"

# The TypeScript corpus behind the secondary measurement is a private production
# monorepo that is deliberately not vendored, so there is no default here and a
# stranger simply skips step 4. Point TS_DB at any codegraph index of a
# TypeScript repository to run it; the index is opened read-only and only
# structural columns are touched.
#
# The path that used to sit here as a default named a specific private
# repository on the author's laptop. Reproducibility was intact — the variable
# was always overridable — but the path leak was not acceptable.
TS_DB="${TS_DB:-}"

mkdir -p "$OUT"

for required in "$PY" "$DB" "$REPO"; do
  [ -e "$required" ] || {
    echo "missing $required — run ../recall-adk-fastapi/run.sh first" >&2
    exit 1
  }
done

# ---------------------------------------------------------------------------
# 1. Ground truth: the contract FastAPI publishes for itself.
#    Regenerating requires network-free instantiation of the ADK app and takes
#    about a minute; contract-key.json is committed so scoring can run without
#    it. Pass REBUILD_KEY=1 to regenerate.
# ---------------------------------------------------------------------------
KEY="$HERE/contract-key.json"
if [ "${REBUILD_KEY:-0}" = "1" ]; then
  F2A_AGENTS_DIR="$SCRATCH/fixture-agents" \
  GOOGLE_CLOUD_PROJECT=probe-project \
  GOOGLE_CLOUD_LOCATION=us-central1 \
  GOOGLE_API_KEY=unused-probe-key \
    "$PY" "$HERE/build_contract_key.py" > "$OUT/contract-key.json"
  KEY="$OUT/contract-key.json"
fi

# ---------------------------------------------------------------------------
# 2. Primary measurement: derive contracts statically, score against the key.
# ---------------------------------------------------------------------------
"$PY" "$HERE/extract_contracts.py" \
  --repo "$REPO" --db "$DB" --out "$OUT/derived.json"

"$PY" "$HERE/score_contracts.py" \
  --derived "$OUT/derived.json" --key "$KEY" \
  --out "$OUT/contract-scores.json" | tee "$OUT/scores-stdout.txt"

# ---------------------------------------------------------------------------
# 3. Ablation: what each framework-specific rule is worth.
# ---------------------------------------------------------------------------
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
: > "$OUT/ablation-stdout.txt"
for RULE in "" field_defaults complex_is_body aliases alias_generator response_class all; do
  LBL="${RULE:-none}"
  "$PY" "$HERE/extract_contracts.py" --repo "$REPO" --db "$DB" \
    --disable "$RULE" --out "$TMP/derived-off-$LBL.json" > /dev/null
  {
    echo "### rule disabled: $LBL"
    "$PY" "$HERE/score_contracts.py" \
      --derived "$TMP/derived-off-$LBL.json" --key "$KEY" \
      --out "$OUT/scores-off-$LBL.json"
    echo
  } >> "$OUT/ablation-stdout.txt"
done
cat "$OUT/ablation-stdout.txt"

# ---------------------------------------------------------------------------
# 4. Signature-string capability ceiling, same parser over both corpora.
# ---------------------------------------------------------------------------
"$PY" "$HERE/signature_parse.py" --db "$DB" --language python \
  --route-prefix "src/" --out "$OUT/sig-python.json" \
  --label "ADK Python, promoted endpoints (fresh index)" \
  | tee "$OUT/sig-stdout.txt"

if [ -n "$TS_DB" ] && [ -e "$TS_DB" ]; then
  "$PY" "$HERE/signature_parse.py" --db "$TS_DB" --language typescript \
    --verb-filter --out "$OUT/sig-typescript.json" \
    --label "TypeScript monorepo, verb-filtered routes (stale index, read-only)" \
    | tee -a "$OUT/sig-stdout.txt"
elif [ -n "$TS_DB" ]; then
  echo "TS_DB is set but no index exists there — skipping the secondary measurement"
else
  echo "TS_DB unset — skipping the secondary measurement."
  echo "  Finding 007's TypeScript column came from a private monorepo's index and"
  echo "  cannot be reproduced. Set TS_DB=/path/to/.codegraph/codegraph.db to run"
  echo "  the same parser against a TypeScript index of your own."
fi

echo
echo "results written to $OUT"
