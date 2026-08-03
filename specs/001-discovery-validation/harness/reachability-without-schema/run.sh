#!/usr/bin/env bash
# E15 — reachability without a published schema. End-to-end reproduction.
#
# Two virtual environments are needed and they are deliberately separate:
#   $ADK_VENV      the E14 environment, with the vendored adk-python copy installed
#   $FIXTURE_VENV  starlette, flask, django, uvicorn, httpx — for the three non-FastAPI targets
#
# Nothing under examples/ is read or written (FR-018); the FastAPI target is reached through the
# copy E14's harness already made.
#
#   ADK_VENV=/tmp/f2a-recall/.venv-adk \
#   FIXTURE_VENV=/tmp/f2a-e15/.venv \
#   ./run.sh
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="${OUT:-$HERE/results}"
ADK_VENV="${ADK_VENV:?set ADK_VENV to the E14 virtualenv}"
FIXTURE_VENV="${FIXTURE_VENV:?set FIXTURE_VENV to the fixture virtualenv}"
E14="$HERE/../deployment-reachability"

export F2A_AGENTS_DIR="${F2A_AGENTS_DIR:-$HERE/../recall-adk-fastapi/fixture-agents}"
export ADK_DISABLE_TELEMETRY=1
export GOOGLE_API_KEY="${GOOGLE_API_KEY:-unused-probe-key}"
export PYTHONUNBUFFERED=1

mkdir -p "$OUT"

# Create the fixture environment if it is not already present.
if [ ! -x "$FIXTURE_VENV/bin/python" ]; then
  echo "== creating fixture virtualenv at $FIXTURE_VENV"
  uv venv "$FIXTURE_VENV" --python 3.12
  uv pip install --python "$FIXTURE_VENV/bin/python" flask django starlette uvicorn httpx
fi

echo "== 0. candidate set S and null set N for the FastAPI target, carried over from E14 unchanged"
cp "$E14/results/static-set.json" "$OUT/static-set.json"

echo "== 1. candidate, null and served sets for the three non-FastAPI fixtures"
#     S from source by AST walk; A_c read from each framework's own router.
"$FIXTURE_VENV/bin/python" "$HERE/fixture_sets.py" --out "$OUT/fixture-sets.json"

echo "== 2. served route tables for the four FastAPI schema configurations"
rm -f "$OUT/served-key.json"
for c in web web_no_schema web_schema_401 web_empty_schema; do
  "$ADK_VENV/bin/python" "$HERE/serve_fastapi.py" --config "$c" --port 1 \
      --dump-routes --out "$OUT/served-key.json" 2>/dev/null | grep -E "routes ->" || true
done

echo "== 3. probe the four FastAPI configurations (schema state + both arms, one process per arm)"
"$ADK_VENV/bin/python" "$HERE/probe.py" \
  --targets web,web_no_schema,web_schema_401,web_empty_schema --kind fastapi \
  --static-set "$OUT/static-set.json" --venv-bin "$ADK_VENV/bin" \
  --out "$OUT/probe-fastapi.json"

echo "== 4. probe the three non-FastAPI fixtures, plus the declared adversarial probe"
#     --extra-paths /anymethod exercises Django's undecorated view, which never enters the
#     candidate set because static analysis cannot recover its methods. Reported, never gated.
"$FIXTURE_VENV/bin/python" "$HERE/probe.py" \
  --targets starlette,flask,django --kind fixture \
  --fixture-sets "$OUT/fixture-sets.json" --venv-bin "$FIXTURE_VENV/bin" \
  --extra-paths /anymethod --out "$OUT/probe-fixtures.json"

echo "== 5. score and adjudicate both gates"
"$FIXTURE_VENV/bin/python" "$HERE/score.py" \
  --probe-fastapi "$OUT/probe-fastapi.json" --probe-fixtures "$OUT/probe-fixtures.json" \
  --served-key "$OUT/served-key.json" --static-set "$OUT/static-set.json" \
  --fixture-sets "$OUT/fixture-sets.json" --out "$OUT/scores.json" \
  | tee "$OUT/scores-stdout.txt"

echo
echo "== 6. determinism: a second independent run, gates compared byte-for-byte"
"$ADK_VENV/bin/python" "$HERE/probe.py" \
  --targets web,web_no_schema,web_schema_401,web_empty_schema --kind fastapi \
  --static-set "$OUT/static-set.json" --venv-bin "$ADK_VENV/bin" \
  --out "$OUT/probe-fastapi-run2.json" >/dev/null
"$FIXTURE_VENV/bin/python" "$HERE/probe.py" \
  --targets starlette,flask,django --kind fixture \
  --fixture-sets "$OUT/fixture-sets.json" --venv-bin "$FIXTURE_VENV/bin" \
  --extra-paths /anymethod --out "$OUT/probe-fixtures-run2.json" >/dev/null
"$FIXTURE_VENV/bin/python" "$HERE/score.py" \
  --probe-fastapi "$OUT/probe-fastapi-run2.json" --probe-fixtures "$OUT/probe-fixtures-run2.json" \
  --served-key "$OUT/served-key.json" --static-set "$OUT/static-set.json" \
  --fixture-sets "$OUT/fixture-sets.json" --out "$OUT/scores-run2.json" >/dev/null

"$FIXTURE_VENV/bin/python" - "$OUT/scores.json" "$OUT/scores-run2.json" <<'PY'
import json, sys
a, b = (json.load(open(p)) for p in sys.argv[1:3])
k = lambda d: json.dumps({"g1": d["gate_1_path_level_precision"],
                          "g2": d["gate_2_schema_state"]}, sort_keys=True)
print("gate adjudication byte-identical across two independent runs:", k(a) == k(b))
# The Allow header's byte order is NOT reproducible — Werkzeug and Starlette build it from a
# set — so raw probe output differs between runs. Every scored metric parses it into a set.
PY

echo
echo "== done. results in $OUT"
echo "   model spend: \$0.00 — no model was called at any point"
