#!/usr/bin/env bash
#
# Reproduce Finding 002 — bring-your-own provider credentials, probed live.
#
# Model-list endpoints only: zero tokens generated, zero model spend. Every call
# is a GET that enumerates what a credential may reach.
#
# No credential value is printed, logged, copied, or written anywhere (FR-020).
# The dotenv tree is read and never written to.
#
# The search root is YOURS to name. There is no default and the probe refuses to
# guess, because scanning the wrong tree silently is the worse failure.
#
# Usage:  ./run.sh /path/to/tree/containing/dotenv/files
#         F2A_ENV_ROOT=/path/to/tree ./run.sh

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="${1:-${F2A_ENV_ROOT:-}}"

if [ -z "$ROOT" ]; then
  cat >&2 <<'EOF'
No dotenv search root given.

  ./run.sh /path/to/tree            or    F2A_ENV_ROOT=/path/to/tree ./run.sh

The tree is read-only to this harness. It should contain the .env files holding
the provider credentials you want probed. Nothing is written to it, and no key
value is printed by any script here.
EOF
  exit 2
fi

export F2A_ENV_ROOT="$ROOT"
PY="${PYTHON:-python3}"

echo "== 1. canonical-name probe: one model-list call per provider"
echo "     (finding 002 §Results — five providers, all 200)"
"$PY" "$HERE/probe_providers.py"

echo
echo "== 2. credential discovery: every Google-shaped value in every dotenv file"
echo "     (finding 002 §Credential discovery — 12 distinct values, exactly one works)"
"$PY" "$HERE/probe_gemini_discovery.py"

echo
echo "== 3. name inventory, names only, no values"
echo "     (regenerates the reconnaissance step; see README)"
"$PY" "$HERE/inventory_env_names.py"

echo
echo "== done. Nothing was written; no key value was emitted."
