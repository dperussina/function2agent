"""SPIKE - E17 pass-by-reference. Delete after 2026-11-30. Do not import from product code.

A deterministic target tree, generated rather than committed.

The measurement in arm A is *how many bytes a command prints*, so the target has to
be something a stranger can reproduce byte-for-byte. Committing six megabytes of
synthetic logs would satisfy that and nothing else; committing the generator and a
SHA-256 manifest satisfies it and stays greppable. `manifest()` is what
`selftest.py` pins, so a change to the generator that moves a single byte fails a
test rather than silently re-basing every projected figure.

Nothing here is random in the sense that matters: `random.Random(seed)` with the
seed pinned in `config.json` before any task was written. Two runs on two machines
produce identical bytes; `selftest.py` asserts that by regenerating twice.
"""

from __future__ import annotations

import hashlib
import os
import random
import shutil
from dataclasses import dataclass

SERVICES = ["auth", "billing", "search", "ingest", "render", "notify"]
REGIONS = ["us-east", "us-west", "eu-central", "ap-south"]
LEVELS = ["DEBUG", "INFO", "INFO", "INFO", "WARN", "ERROR"]
STATUSES = [200, 200, 200, 201, 204, 304, 400, 401, 404, 429, 500, 502, 503]

_MSGS = [
    "handled inbound request",
    "cache miss, falling through",
    "upstream latency above soft budget",
    "retrying after transient failure",
    "connection pool saturated",
    "wrote checkpoint to durable store",
]


@dataclass(frozen=True)
class CorpusSpec:
    seed: int
    expected_total_bytes: int


def _log_lines(rng: random.Random, n: int) -> list[str]:
    out = []
    for i in range(n):
        day = 1 + (i % 28)
        hour = (i * 7) % 24
        minute = (i * 13) % 60
        second = (i * 29) % 60
        level = rng.choice(LEVELS)
        svc = rng.choice(SERVICES)
        status = rng.choice(STATUSES)
        # Deliberately not a round bound: with `rng.randint(1, 4000)` the answer to
        # "largest dur_ms on a WARN line" is 4000, which a model can produce without
        # reading anything. A task answerable by guessing the generator's constants
        # measures the guess, not the treatment.
        dur = rng.randint(1, 3987)
        msg = rng.choice(_MSGS)
        out.append(
            f"2026-07-{day:02d}T{hour:02d}:{minute:02d}:{second:02d}Z "
            f"{level} {svc} req=r{i:08d} status={status} dur_ms={dur} msg=\"{msg}\""
        )
    return out


def _csv_rows(rng: random.Random, n: int) -> list[str]:
    rows = ["ts,region,service,requests,errors,latency_p95"]
    for i in range(n):
        region = rng.choice(REGIONS)
        svc = rng.choice(SERVICES)
        requests = rng.randint(10, 9000)
        errors = rng.randint(0, max(1, requests // 20))
        p95 = rng.randint(40, 1793)  # not round, for the reason given in _log_lines
        rows.append(f"2026-07-{1 + (i % 28):02d}T{(i * 3) % 24:02d}:00:00Z,{region},{svc},{requests},{errors},{p95}")
    return rows


def _py_module(rng: random.Random, idx: int, n_funcs: int, n_classes: int, todos: int) -> str:
    lines = [
        "# generated module — E17 target tree",
        "import os",
        "import sys",
        "from dataclasses import dataclass",
        "",
    ]
    for c in range(n_classes):
        lines.append(f"class Widget{idx}_{c}:")
        lines.append(f'    """A generated class."""')
        lines.append("    slot: int = 0")
        lines.append("")
    for f in range(n_funcs):
        lines.append(f"def handle_{idx}_{f}(payload, *, strict=False):")
        if todos > 0 and f < todos:
            lines.append("    # TODO: this path is not covered")
        lines.append(f"    total = {rng.randint(1, 999)}")
        lines.append("    for item in payload:")
        lines.append("        total += len(str(item))")
        lines.append("    return total")
        lines.append("")
    return "\n".join(lines) + "\n"


def generate(root: str, spec: CorpusSpec) -> dict:
    """(Re)generate the target tree at ``root``. Returns the manifest."""
    if os.path.isdir(root):
        shutil.rmtree(root)
    os.makedirs(os.path.join(root, "logs"))
    os.makedirs(os.path.join(root, "data"))
    os.makedirs(os.path.join(root, "src", "core"))
    os.makedirs(os.path.join(root, "src", "edge"))

    rng = random.Random(spec.seed)

    # Line counts chosen so the three artefact classes land near 50/25/25 of the
    # target size. They are constants, not a search: a search would make the tree
    # depend on the machine's rounding.
    log = _log_lines(rng, 28000)
    with open(os.path.join(root, "logs", "app.log"), "w") as fh:
        fh.write("\n".join(log) + "\n")

    csv = _csv_rows(rng, 24000)
    with open(os.path.join(root, "data", "metrics.csv"), "w") as fh:
        fh.write("\n".join(csv) + "\n")

    for i in range(40):
        sub = "core" if i % 2 == 0 else "edge"
        body = _py_module(rng, i, n_funcs=rng.randint(4, 18), n_classes=rng.randint(0, 4),
                          todos=rng.randint(0, 2))
        with open(os.path.join(root, "src", sub, f"mod_{i:02d}.py"), "w") as fh:
            fh.write(body)

    return manifest(root)


def manifest(root: str) -> dict:
    """Per-file size and SHA-256, sorted, for every file under ``root``."""
    out: dict[str, dict] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for fn in sorted(filenames):
            path = os.path.join(dirpath, fn)
            rel = os.path.relpath(path, root)
            with open(path, "rb") as fh:
                blob = fh.read()
            out[rel] = {"bytes": len(blob), "sha256": hashlib.sha256(blob).hexdigest()}
    return {
        "files": out,
        "file_count": len(out),
        "total_bytes": sum(v["bytes"] for v in out.values()),
    }
