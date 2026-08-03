#!/usr/bin/env bash
#
# Reproduce Finding 004 — route-extraction recall against an authoritative key.
#
# Everything happens under a scratch directory. The vendored repositories under
# examples/ are copied, never modified in place (spec FR-018), and no model is
# called at any point (SC-001).
#
# Usage:  ./run.sh [scratch-dir]     (default: /tmp/f2a-recall)

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/../../../.." && pwd)"
SCRATCH="${1:-/tmp/f2a-recall}"

TARGET_SRC="$REPO_ROOT/examples/adk-python"
TOOL_SRC="$REPO_ROOT/examples/codegraph"

echo "== scratch: $SCRATCH"
mkdir -p "$SCRATCH"

echo "== copying target and analysis tool out of examples/ (read-only source)"
rsync -a --exclude '.git' --exclude '.codegraph' "$TARGET_SRC/" "$SCRATCH/adk-python/"
rsync -a --exclude '.git' --exclude 'node_modules' --exclude 'dist' \
      "$TOOL_SRC/" "$SCRATCH/codegraph/"

echo "== building the analysis tool (node >=20 <25 required)"
( cd "$SCRATCH/codegraph" && npm install --no-audit --no-fund >/dev/null && npm run build >/dev/null )

echo "== indexing the target copy, fresh"
rm -rf "$SCRATCH/adk-python/.codegraph"
( cd "$SCRATCH" && CODEGRAPH_TELEMETRY=0 NO_COLOR=1 \
    node codegraph/dist/bin/codegraph.js init ./adk-python )

echo "== creating an isolated virtualenv and installing the target from the copy"
uv venv --python 3.12 "$SCRATCH/.venv-adk"
VIRTUAL_ENV="$SCRATCH/.venv-adk" uv pip install "$SCRATCH/adk-python[a2a]" >/dev/null
VIRTUAL_ENV="$SCRATCH/.venv-adk" uv pip install sse_starlette \
    "google-cloud-aiplatform[agent-engines]" >/dev/null
PY="$SCRATCH/.venv-adk/bin/python"

echo "== generating the answer key from the instantiated application"
# GOOGLE_* values are placeholders; the enterprise configuration reads them but
# the probe never authenticates against a real project.
F2A_AGENTS_DIR="$HERE/fixture-agents" \
GOOGLE_CLOUD_PROJECT=probe-project \
GOOGLE_CLOUD_LOCATION=us-central1 \
GOOGLE_API_KEY=unused-probe-key \
  "$PY" "$HERE/build_key.py" > "$SCRATCH/answer-key.json"

echo "== scoring"
"$PY" "$HERE/compare.py" \
      --key "$SCRATCH/answer-key.json" \
      --db  "$SCRATCH/adk-python/.codegraph/codegraph.db" \
      --out "$SCRATCH/results.json"

"$PY" "$HERE/analyze_extras.py" \
      --repo "$SCRATCH/adk-python" \
      --db   "$SCRATCH/adk-python/.codegraph/codegraph.db" \
      --out  "$SCRATCH/results-extras.json"

echo
echo "== wrote $SCRATCH/answer-key.json, $SCRATCH/results.json, $SCRATCH/results-extras.json"
echo "== compare against the committed copies to confirm reproduction:"
echo "     $HERE/answer-key.json"
echo "     $HERE/results/results.json"
echo "     $HERE/results/results-extras.json"
