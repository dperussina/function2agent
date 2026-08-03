"""SPIKE - E7 ceiling test. Delete after 2026-11-30. Do not import from product code.

The two experimental arms. The capability set is the independent variable and the only
thing that differs between them (FR-022).

Arm A - tool-equipped. The hand-written ideal domain tools in tools/mealie_tools.py.

Arm B - baseline. A capable general agent with a real shell, `curl`, `jq`, `python3`, and
the usual text tools, running in a container on the same network as the application, with
the application's complete OpenAPI schema on disk and a valid auth token in its
environment. It is told exactly how to reach the application. This is the mean control
from research/11-validation-plan.md 4.1 (arm A0b), and it is deliberately not handicapped:
a rigged baseline would make the entire result worthless.

The sandbox has no route off the internal Docker network, so the shell can reach the
target application and nothing else. That is a safety property, not a capability
restriction - the task set needs no internet access.
"""

from __future__ import annotations

import os
import shlex
import subprocess
from typing import Callable

from mealie_client import MealieClient

HERE = os.path.dirname(os.path.abspath(__file__))

ARM_A_CAPABILITY = """You reach the application through the tools listed below. They are the only way to \
reach it, and between them they cover everything the task set needs."""

ARM_B_CAPABILITY = """You reach the application through a shell. The `bash` tool runs a command in a Linux \
container on the same private network as the application and returns its combined output.

- The application's HTTP API is at {internal_url}. It is a Mealie {app_version} server.
- A valid bearer token is already in the environment variable MEALIE_TOKEN. Send it as
  `Authorization: Bearer $MEALIE_TOKEN`.
- The application's complete OpenAPI schema is on disk at /work/openapi.json. Read it to
  find out which endpoints exist and what they accept and return.
- curl, jq, python3, grep, sed, awk, sort, uniq and wc are installed.
- The container has no internet access. It can reach the application and nothing else.
- Each command runs in a fresh shell, so `cd` and shell variables do not persist between
  calls. Files you write under /work do persist for the rest of this task."""


# ---------------------------------------------------------------------------
# arm A
# ---------------------------------------------------------------------------


def build_arm_a(api: MealieClient, surface: str | None = None):
    from tools.mealie_tools import build_tools

    surface = surface or os.environ.get("F2A_TOOL_SURFACE", "v2")
    schemas, fns = build_tools(api, surface=surface)
    return ARM_A_CAPABILITY, schemas, fns


# ---------------------------------------------------------------------------
# arm B
# ---------------------------------------------------------------------------


def _docker(*args: str, check: bool = True) -> str:
    out = subprocess.run(["docker", *args], capture_output=True, text=True)
    if check and out.returncode != 0:
        raise RuntimeError(f"docker {' '.join(args)} failed: {out.stderr.strip()[:300]}")
    return out.stdout.strip()


def start_shell_sandbox(cfg: dict, token: str) -> None:
    """(Re)create arm B's sandbox. Fresh per attempt, so nothing carries between tasks."""
    sh = cfg["shell_arm"]
    tgt = cfg["target"]
    _docker("rm", "-f", sh["container"], check=False)
    openapi = os.path.join(HERE, "groundtruth", "openapi.json")
    _docker(
        "run", "-d", "--name", sh["container"],
        "--network", tgt["network"] + "-internal",
        "-v", f"{openapi}:/work/openapi.json:ro",
        "-e", f"MEALIE_TOKEN={token}",
        "-e", f"MEALIE_URL={tgt['internal_url']}",
        "-w", sh["workdir"],
        sh["image"], "sleep", "infinity",
    )


def stop_shell_sandbox(cfg: dict) -> None:
    _docker("rm", "-f", cfg["shell_arm"]["container"], check=False)


def build_arm_b(cfg: dict) -> tuple[str, list[dict], dict[str, Callable[..., str]]]:
    sh = cfg["shell_arm"]
    tgt = cfg["target"]

    def bash(command: str) -> str:
        proc = subprocess.run(
            ["docker", "exec", sh["container"], "bash", "-lc", command],
            capture_output=True, text=True, timeout=sh["command_timeout_s"],
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        if not out.strip():
            out = f"(no output, exit status {proc.returncode})"
        elif proc.returncode != 0:
            out += f"\n(exit status {proc.returncode})"
        return out

    schema = [
        {
            "name": "bash",
            "description": (
                "Run a shell command in the sandbox container and get its combined stdout and "
                "stderr back. Use it to call the application's HTTP API with curl, to read its "
                "OpenAPI schema, and to process results with jq, python3 or the usual text tools."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The command line to run, e.g. "
                                       "curl -s -H \"Authorization: Bearer $MEALIE_TOKEN\" "
                                       "\"$MEALIE_URL/api/recipes?perPage=5\" | jq '.total'",
                    }
                },
                "required": ["command"],
            },
        }
    ]
    capability = ARM_B_CAPABILITY.format(
        internal_url=tgt["internal_url"], app_version=tgt["app_version"]
    )
    return capability, schema, {"bash": bash}
