#!/usr/bin/env bash
#
# Reproduce Finding 003 — E5, can the candidate runtimes be driven by a
# non-default provider?
#
# Model spend: roughly $0.09 against the finding's $2.00 ceiling. Every prompt is
# trivial by design and every model is a cheap tier. The Claude Agent SDK arm is
# the expensive one, for the reason the finding calls the 40x context tax.
#
# Credentials are read from a dotenv tree you name, assigned to os.environ
# in-process, and never printed, logged, or written (FR-020).
#
# Usage:  F2A_ENV_ROOT=/path/to/tree ./run.sh [arm ...]
#
# Arms:  models cost adk multiturn stream strict xai_nr cas fields
#        (default: everything except `models`, which is the selection step)

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRATCH="${F2A_PROBE_DIR:-/tmp/f2a-probe-runtime}"
VENV="$SCRATCH/.venv"

if [ -z "${F2A_ENV_ROOT:-}" ]; then
  cat >&2 <<'EOF'
F2A_ENV_ROOT is not set.

  F2A_ENV_ROOT=/path/to/tree ./run.sh

The tree is read-only to this harness and must contain .env files defining
ANTHROPIC_API_KEY, OPENAI_API_KEY, XAI_API_KEY, and a Google credential. If your
Google key is not called GEMINI_API_KEY, name it with F2A_GEMINI_VAR — finding
002 is the story of why that option exists.
EOF
  exit 2
fi

# ------------------------------------------------------------------ virtualenv
mkdir -p "$SCRATCH"
if [ ! -x "$VENV/bin/python" ]; then
  echo "== building the isolated virtualenv at $VENV"
  echo "   (Python 3.12 is what finding 003 measured on)"
  "${PYTHON:-python3.12}" -m venv "$VENV"
  "$VENV/bin/pip" install --quiet --upgrade pip
  "$VENV/bin/pip" install --quiet -r "$HERE/requirements.txt"
fi
PY="$VENV/bin/python"

echo "== interpreter : $("$PY" --version)"
echo "== adk/litellm : $("$PY" -c 'import importlib.metadata as m; print("google-adk", m.version("google-adk"), "| litellm", m.version("litellm"))')"
echo "== credentials : "
"$PY" "$HERE/envload.py" | sed 's/^/   /'

ARMS=("$@")
if [ ${#ARMS[@]} -eq 0 ]; then
  ARMS=(adk multiturn stream strict xai_nr cas cost fields)
fi

run_arm() {
  echo
  echo "======================================================================"
  echo "== $1"
  echo "======================================================================"
  shift
  "$PY" "$@" || echo "   (arm exited non-zero; the output above is the record)"
}

for arm in "${ARMS[@]}"; do
  case "$arm" in
    models)
      run_arm "model selection — what each credential can reach (zero cost)" \
              "$HERE/pick_models.py" ;;
    adk)
      run_arm "ADK matrix: completion / tool-calling / streaming / structured" \
              "$HERE/probe_adk.py" ;;
    multiturn)
      run_arm "ADK chained two-step tool use (the load-bearing capability)" \
              "$HERE/probe_adk_multiturn.py" ;;
    stream)
      run_arm "ADK streaming: incremental or coalesced? (result 6)" \
              "$HERE/probe_adk_stream.py" ;;
    strict)
      run_arm "ADK structured output, decided by json.loads + model_validate (result 5)" \
              "$HERE/probe_adk_strict.py" ;;
    xai_nr)
      run_arm "structured output control: xAI non-reasoning model (result 5)" \
              "$HERE/probe_xai_nr.py" ;;
    cas)
      run_arm "Claude Agent SDK against xAI and OpenAI via base-URL redirection" \
              "$HERE/probe_cas.py" ;;
    cost)
      run_arm "same task, same model, two runtimes: the 40x context tax" \
              "$HERE/probe_cost_compare.py" ;;
    fields)
      run_arm "reasoning-field counts in ADK's LiteLlm adapter (result 7, RECONSTRUCTED)" \
              "$HERE/count_reasoning_fields.py" ;;
    *)
      echo "unknown arm: $arm" >&2; exit 2 ;;
  esac
done

echo
echo "== done. Nothing was captured to a results/ directory — see the README for why."
