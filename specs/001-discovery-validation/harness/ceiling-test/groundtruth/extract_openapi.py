"""SPIKE - E7 ceiling test. Delete after 2026-11-30. Do not import from product code.

Derives the authoritative operation list from the running application's own OpenAPI
document rather than from hand transcription (FR-008). This is both the source used to
design the task battery and the ground truth for what an operation is.

Usage:  python3 extract_openapi.py
Writes: openapi.json (verbatim), operations.csv, operations_summary.md
"""

from __future__ import annotations

import collections
import csv
import hashlib
import json
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from mealie_client import load_config  # noqa: E402

METHODS = ("get", "post", "put", "patch", "delete")
WRITE_METHODS = ("post", "put", "patch", "delete")


def main() -> None:
    cfg = load_config()["target"]
    url = cfg["base_url"] + "/openapi.json"
    raw = urllib.request.urlopen(url, timeout=30).read()
    schema = json.loads(raw.decode())

    with open(os.path.join(HERE, "openapi.json"), "wb") as fh:
        fh.write(raw)

    rows = []
    for path, methods in schema["paths"].items():
        for method, op in methods.items():
            if method not in METHODS:
                continue
            params = op.get("parameters", []) or []
            body = op.get("requestBody")
            rows.append(
                {
                    "method": method.upper(),
                    "path": path,
                    "operation_id": op.get("operationId", ""),
                    "tag": (op.get("tags") or ["(none)"])[0],
                    "summary": (op.get("summary") or "").replace("\n", " ").strip(),
                    "path_params": sum(1 for p in params if p.get("in") == "path"),
                    "query_params": sum(1 for p in params if p.get("in") == "query"),
                    "has_request_body": bool(body),
                    "effect_by_verb": "read" if method == "get" else "write",
                }
            )
    rows.sort(key=lambda r: (r["tag"], r["path"], r["method"]))

    out_csv = os.path.join(HERE, "operations.csv")
    with open(out_csv, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    by_tag = collections.Counter(r["tag"] for r in rows)
    reads = sum(1 for r in rows if r["effect_by_verb"] == "read")
    digest = hashlib.sha256(raw).hexdigest()

    lines = [
        "# Ground truth: Mealie operation inventory",
        "",
        "Machine-generated from the running instance's own OpenAPI document (FR-008).",
        "Do not hand-edit; re-run `extract_openapi.py` instead.",
        "",
        f"- Application version: `{schema['info']['version']}`",
        f"- OpenAPI version: `{schema.get('openapi')}`",
        f"- Source: `{url}`",
        f"- `openapi.json` sha256: `{digest}`",
        f"- Operations: **{len(rows)}** ({reads} GET, {len(rows) - reads} write-verb)",
        f"- Distinct paths: {len({r['path'] for r in rows})}",
        f"- Tag groups: {len(by_tag)}",
        "",
        "| Tag | Operations |",
        "|---|---|",
    ]
    for tag, n in sorted(by_tag.items(), key=lambda kv: (-kv[1], kv[0])):
        lines.append(f"| {tag} | {n} |")
    lines.append("")
    with open(os.path.join(HERE, "operations_summary.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))

    print(f"{len(rows)} operations -> operations.csv")
    print(f"openapi.json sha256 {digest}")


if __name__ == "__main__":
    main()
