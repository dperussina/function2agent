#!/usr/bin/env bash
# SPIKE - E7 ceiling test. Delete after 2026-11-30. Do not import from product code.
# Brings up a disposable Mealie instance and the disposable shell sandbox used by arm B.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$HERE")"

IMAGE=$(python3 -c "import json;print(json.load(open('$ROOT/config.json'))['target']['image'])")
NET=$(python3 -c "import json;print(json.load(open('$ROOT/config.json'))['target']['network'])")
NAME=$(python3 -c "import json;print(json.load(open('$ROOT/config.json'))['target']['container'])")
PORT=$(python3 -c "import json;print(json.load(open('$ROOT/config.json'))['target']['host_port'])")
SHELL_IMAGE=$(python3 -c "import json;print(json.load(open('$ROOT/config.json'))['shell_arm']['image'])")

docker network create "$NET" >/dev/null 2>&1 || true
# Arm B's shell sandbox lives on an --internal network: it can reach the target
# application and nothing else. No route to the internet, no route to the host.
docker network create --internal "${NET}-internal" >/dev/null 2>&1 || true
docker rm -f "$NAME" >/dev/null 2>&1 || true

echo "starting $NAME on port $PORT"
docker run -d --name "$NAME" --network "$NET" -p "${PORT}:9000" \
  -e ALLOW_SIGNUP=false -e PUID=1000 -e PGID=1000 -e TZ=UTC \
  -e BASE_URL="http://localhost:${PORT}" \
  "$IMAGE" >/dev/null
docker network connect "${NET}-internal" "$NAME" >/dev/null

echo -n "waiting for health"
for _ in $(seq 1 60); do
  if curl -fs "http://localhost:${PORT}/api/app/about" >/dev/null 2>&1; then
    echo " ok"
    break
  fi
  echo -n "."
  sleep 2
done

curl -fs "http://localhost:${PORT}/api/app/about" | python3 -c "import sys,json;d=json.load(sys.stdin);print('mealie version',d['version'])"

# Arm B's sandbox image: shell, curl, jq, grep, python. Built locally so the baseline
# is a genuinely capable general agent and not a crippled one.
if ! docker image inspect "$SHELL_IMAGE" >/dev/null 2>&1; then
  echo "building shell sandbox image $SHELL_IMAGE"
  docker build -q -t "$SHELL_IMAGE" -f "$HERE/Dockerfile.shell" "$HERE" >/dev/null
fi
echo "shell sandbox image ready: $SHELL_IMAGE"
