"""SPIKE - E7 ceiling test. Delete after 2026-11-30. Do not import from product code.

Fixture snapshot and restore for the write-task family. Every write attempt starts from a
byte-identical database, so an arm cannot inherit the previous arm's changes and a
collateral-damage check means something.

This is the only path in the harness that touches the database file rather than the HTTP
API, and it is fixture management, not agent capability. No arm can reach it.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request

SIDE_FILES = ("-wal", "-shm")


def _docker(*args: str, check: bool = True) -> str:
    out = subprocess.run(["docker", *args], capture_output=True, text=True)
    if check and out.returncode != 0:
        raise RuntimeError(f"docker {' '.join(args)} failed: {out.stderr.strip()[:300]}")
    return out.stdout.strip()


def _wait_healthy(base_url: str, timeout_s: int = 120) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(base_url + "/api/app/about", timeout=5) as r:
                if r.status == 200:
                    return
        except Exception:  # noqa: BLE001
            pass
        time.sleep(1.5)
    raise RuntimeError(f"target did not become healthy within {timeout_s}s")


def take(cfg: dict, dest_dir: str) -> str:
    """Stop the app, copy the database out, start it again. Returns the snapshot dir."""
    tgt = cfg["target"]
    os.makedirs(dest_dir, exist_ok=True)
    _docker("stop", tgt["container"])
    try:
        _docker("cp", f"{tgt['container']}:{tgt['db_path_in_container']}",
                os.path.join(dest_dir, "mealie.db"))
        for suffix in SIDE_FILES:
            subprocess.run(
                ["docker", "cp", f"{tgt['container']}:{tgt['db_path_in_container']}{suffix}",
                 os.path.join(dest_dir, "mealie.db" + suffix)],
                capture_output=True, text=True,
            )
    finally:
        _docker("start", tgt["container"])
    _wait_healthy(tgt["base_url"])
    return dest_dir


def restore(cfg: dict, src_dir: str) -> None:
    tgt = cfg["target"]
    _docker("stop", tgt["container"])
    try:
        # remove any journal side files first so a stale WAL cannot replay over the restore
        for suffix in SIDE_FILES:
            subprocess.run(
                ["docker", "exec", tgt["container"], "rm", "-f",
                 tgt["db_path_in_container"] + suffix],
                capture_output=True, text=True,
            )
        _docker("cp", os.path.join(src_dir, "mealie.db"),
                f"{tgt['container']}:{tgt['db_path_in_container']}")
        for suffix in SIDE_FILES:
            p = os.path.join(src_dir, "mealie.db" + suffix)
            if os.path.exists(p):
                subprocess.run(
                    ["docker", "cp", p, f"{tgt['container']}:{tgt['db_path_in_container']}{suffix}"],
                    capture_output=True, text=True,
                )
        _docker("exec", "-u", "0", tgt["container"], "chown", "1000:1000",
                tgt["db_path_in_container"], check=False)
    finally:
        _docker("start", tgt["container"])
    _wait_healthy(tgt["base_url"])


def discard(dest_dir: str) -> None:
    shutil.rmtree(dest_dir, ignore_errors=True)
