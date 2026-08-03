#!/usr/bin/env bash
#
# Reproduce Finding 010 — E14 deployment reachability.
#
# Everything happens under a scratch directory. The vendored repositories under
# examples/ are copied, never modified in place (spec FR-018), and no model is
# called at any point.
#
# This reuses the scratch tree finding 004 / E2 built, if present: the codegraph
# index of the target and the isolated virtualenv with the target installed. E14
# scores reachability handling against the *same* index finding 004 scored, so
# nothing about extraction quality is a free variable here (FR-004).
#
# Usage:  ./run.sh [scratch-dir]     (default: /tmp/f2a-recall)

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/../../../.." && pwd)"
SCRATCH="${1:-/tmp/f2a-recall}"
E="$SCRATCH/e14"
FIXTURES="$REPO_ROOT/specs/001-discovery-validation/harness/recall-adk-fastapi/fixture-agents"

mkdir -p "$E"

# ---------------------------------------------------------------- prerequisites
if [ ! -d "$SCRATCH/adk-python/.codegraph" ] || [ ! -x "$SCRATCH/.venv-adk/bin/python" ]; then
  echo "== E2 scratch tree not found; building it via the finding 004 harness"
  "$REPO_ROOT/specs/001-discovery-validation/harness/recall-adk-fastapi/run.sh" "$SCRATCH"
fi
PY="$SCRATCH/.venv-adk/bin/python"
REPO="$SCRATCH/adk-python"
ENTRY="src.google.adk.cli.fast_api:get_fast_api_app"

export ADK_DISABLE_TELEMETRY=1
export F2A_AGENTS_DIR="$FIXTURES"
export GOOGLE_CLOUD_PROJECT=probe-project
export GOOGLE_CLOUD_LOCATION=us-central1
export GOOGLE_API_KEY=unused-probe-key

# ------------------------------------------------- 1. ground truth per configuration
echo "== reading each configuration's own route table (machine-generated, FR-008)"
"$PY" "$HERE/build_served_key.py" --out "$E/served-key-6.json" \
      --only api_server,web,web_a2a,web_triggers,api_server_pubsub,devserver_no_assets
echo "== the enterprise configuration takes about a minute to construct"
"$PY" "$HERE/build_served_key.py" --out "$E/served-key-ent.json" --only enterprise
echo "== configuration 8, post-hoc: identical declared configuration, multipart absent"
"$PY" "$HERE/config8_environment.py" --out "$E/served-key-c8.json"
"$PY" - "$E" <<'PYEOF'
import json, sys
E = sys.argv[1]
out = {}
for f in ("served-key-6.json", "served-key-ent.json", "served-key-c8.json"):
    out.update(json.load(open(f"{E}/{f}")))
json.dump(out, open(f"{E}/served-key-plus8.json", "w"), indent=2, sort_keys=True,
          default=str)
print("configurations:", ", ".join(sorted(out)))
PYEOF

# ------------------------------------------------ 2. the candidate set and null set
echo "== reading the static candidate set S and the null set N from the E2 index"
"$PY" "$HERE/static_set.py" --db "$REPO/.codegraph/codegraph.db" \
      --out "$E/static-set.json"

# --------------------------------------------------------------------- 3. arm R1
echo "== R1-naive: lexical guard scan, whole repository in scope"
"$PY" "$HERE/extract_guards.py" --src "$REPO" --mode lexical \
      --served-key "$E/served-key-plus8.json" --out "$E/r1-naive-plus8.json"
echo "== R1-tuned: interprocedural configuration propagation, whole repository in scope"
"$PY" "$HERE/extract_guards.py" --src "$REPO" --entry "$ENTRY" \
      --served-key "$E/served-key-plus8.json" --out "$E/r1-tuned-plus8.json"

# ----------------------------------------------------------------- 4. arms R2, R3
echo "== R2 and R3: real uvicorn servers on loopback, probed over HTTP"
"$PY" "$HERE/probe_runtime.py" --served-key "$E/served-key-plus8.json" \
      --static-set "$E/static-set.json" --out "$E/probe-7.json" \
      --only api_server,api_server_pubsub,enterprise,web,web_a2a,web_triggers,devserver_no_assets
"$PY" "$HERE/probe_runtime.py" --served-key "$E/served-key-plus8.json" \
      --static-set "$E/static-set.json" --out "$E/probe-c8.json" \
      --only web_no_multipart --block multipart
"$PY" - "$E" <<'PYEOF'
import json, sys
E = sys.argv[1]
out = json.load(open(f"{E}/probe-7.json"))
out.update(json.load(open(f"{E}/probe-c8.json")))
json.dump(out, open(f"{E}/probe-plus8.json", "w"), indent=2, sort_keys=True, default=str)
PYEOF

echo "== verifying the two probe defects directly against a running instance"
"$PY" "$HERE/verify_probe_defects.py" > "$E/probe-defects.json"

# ------------------------------------------------------------------- 5. scoring
echo
echo "== scoring"
"$PY" "$HERE/score.py" --static-set "$E/static-set.json" \
      --served-key "$E/served-key-plus8.json" \
      --r1-naive "$E/r1-naive-plus8.json" --r1-tuned "$E/r1-tuned-plus8.json" \
      --probe "$E/probe-plus8.json" --out "$E/scores-plus8.json" \
      | tee "$E/scores-plus8-stdout.txt"

# ------------------------------------------------------------------ 6. ablation
echo
echo "== mechanism ablation (a few minutes)"
"$HERE/ablate.sh" "$SCRATCH" "$PY" | tee "$E/ablation-stdout.txt"

# --------------------------------------------------------------- 7. determinism
echo
echo "== determinism (FR-007): the static arms re-run and compared byte for byte"
"$PY" "$HERE/extract_guards.py" --src "$REPO" --entry "$ENTRY" \
      --served-key "$E/served-key-plus8.json" --out "$E/det-tuned-b.json" >/dev/null
"$PY" "$HERE/static_set.py" --db "$REPO/.codegraph/codegraph.db" \
      --out "$E/det-static-b.json" >/dev/null
for p in "r1-tuned-plus8.json det-tuned-b.json" "static-set.json det-static-b.json"; do
  set -- $p
  if cmp -s "$E/$1" "$E/$2"; then echo "  IDENTICAL  $1"; else echo "  DIFFERS    $1"; fi
done

echo
echo "== wrote $E; compare against the committed copies in $HERE/results/"
