"""SPIKE - E16. Free static count: does each vendor SDK reference its own opaque field?

Zero model spend. Reads installed package source and counts.

**The comparison this exists to make.** Finding 003 result 7 counted ADK's
LiteLLM adapter referencing `encrypted_content` — xAI's opaque reasoning field
— **zero times**, against 35, 16 and 9 for the other three providers' fields.
**OD-16** replaced that adapter with each vendor's own SDK. This script asks
the same question of the replacement.

The counting rule is deliberately identical to the one
`../runtime-provider-agnosticism/count_reasoning_fields.py` reconstructed:
**source lines containing the identifier**, which is what `grep -c` reports. A
line mentioning a field twice counts once. Using a different rule here would
make the two numbers incomparable, which is the whole point of printing them
side by side.

One asymmetry worth stating rather than hiding: finding 003 counted **one
module** (`lite_llm.py`), because that was the whole adapter. Here the unit is
**one package**, because a vendor SDK spreads its wire types across several
files. A package is a larger surface than a module, so a non-zero count here is
weaker evidence of *good* handling than zero there was of *absent* handling.
Zero remains decisive in either direction; a large number is not proportionally
reassuring. The behavioural arms are what establish the field is carried — this
script only establishes it is *named*.
"""
from __future__ import annotations

import importlib.util
import json
import pathlib
import re
import sys

# provider -> (import name, the opaque field that provider uses)
TARGETS = {
    "anthropic": ("anthropic", "signature"),
    "openai": ("openai", "encrypted_content"),
    "google": ("google.genai", "thought_signature"),
    "xai": ("xai_sdk", "encrypted_content"),
}

# Compiled artifacts and vendored copies would double-count.
SKIP_SUFFIXES = (".pyc", ".pyo", ".so", ".dylib")
SKIP_PARTS = {"__pycache__", "tests", "test"}


def package_root(import_name: str) -> pathlib.Path | None:
    spec = importlib.util.find_spec(import_name)
    if spec is None:
        return None
    if spec.submodule_search_locations:
        return pathlib.Path(list(spec.submodule_search_locations)[0])
    return pathlib.Path(spec.origin).parent if spec.origin else None


def count_lines(root: pathlib.Path, field: str) -> tuple[int, int, int]:
    """(source lines containing it, files containing it, total .py files scanned)."""
    pattern = re.compile(re.escape(field))
    lines = files = scanned = 0
    for path in sorted(root.rglob("*.py")):
        if any(part in SKIP_PARTS for part in path.parts):
            continue
        if path.suffix in SKIP_SUFFIXES:
            continue
        scanned += 1
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        hits = sum(1 for line in text.splitlines() if pattern.search(line))
        if hits:
            files += 1
            lines += hits
    return lines, files, scanned


def main() -> int:
    out = {
        "counting_rule": "source lines containing the identifier (grep -c), per package",
        "comparison": {
            "source": "finding 003 result 7, google-adk==2.6.1, module google/adk/models/lite_llm.py",
            "adk_litellm_adapter": {
                "thought_signature": 35,
                "thinking_blocks": 16,
                "reasoning_content": 9,
                "encrypted_content": 0,
            },
        },
        "vendor_sdks": {},
    }
    for provider, (import_name, field) in TARGETS.items():
        root = package_root(import_name)
        if root is None:
            out["vendor_sdks"][provider] = {"error": f"{import_name} not installed"}
            continue
        lines, files, scanned = count_lines(root, field)
        out["vendor_sdks"][provider] = {
            "package": import_name,
            "field": field,
            "source_lines": lines,
            "files_containing": files,
            "py_files_scanned": scanned,
        }
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
