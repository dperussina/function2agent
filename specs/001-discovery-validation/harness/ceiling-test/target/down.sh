#!/usr/bin/env bash
# SPIKE - E7 ceiling test. Delete after 2026-11-30. Do not import from product code.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$HERE")"
NAME=$(python3 -c "import json;print(json.load(open('$ROOT/config.json'))['target']['container'])")
SHELL_NAME=$(python3 -c "import json;print(json.load(open('$ROOT/config.json'))['shell_arm']['container'])")
docker rm -f "$SHELL_NAME" >/dev/null 2>&1 || true
docker rm -f "$NAME" >/dev/null 2>&1 || true
echo "torn down"
