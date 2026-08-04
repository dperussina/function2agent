"""T010 (partial) — the one canonical serializer.

**Pulled forward, and only partly.** The enforcement-point slice needs a
deterministic byte form for two things it actually writes: the versioned
location set of FR-048 and the `filesystem_decision` records of FR-011. Without
one, every record this slice emits would need its own ad-hoc serialization that
T010 would then have to replace.

What is here: sorted keys, deterministic collation, fixed locale-independent
numeric formatting, `LF`, `UTF-8` without a byte-order mark.

What is **not** here and is still owed to T010/T011: the envelope of FR-055
that holds timestamps, paths and hostnames *beside* the hash rather than under
it, the eight artifact-kind schemas of T009, and T012's byte-identity
determinism test over a committed analysis fixture. This module is the
serializer only; the artifact discipline around it is Phase 2's.
"""

from __future__ import annotations

import hashlib
import math
from typing import Any

SCHEMA_VERSION = "1.0.0"


class NonCanonicalValue(TypeError):
    """A value with no deterministic representation. Never guessed at."""


def _num(value: float | int) -> str:
    """Locale-independent, round-trippable, and stable across platforms."""
    if isinstance(value, bool):  # bool is an int subclass; handled by caller
        raise NonCanonicalValue("bool must be encoded as a literal, not a number")
    if isinstance(value, int):
        return str(value)
    if math.isnan(value) or math.isinf(value):
        raise NonCanonicalValue(
            f"{value!r} has no canonical form; a hashed artifact must not "
            "contain one"
        )
    if value == int(value) and abs(value) < 1e16:
        return f"{int(value)}.0"
    return repr(value)


def _encode(value: Any, out: list[str]) -> None:
    if value is None:
        out.append("null")
    elif value is True:
        out.append("true")
    elif value is False:
        out.append("false")
    elif isinstance(value, (int, float)):
        out.append(_num(value))
    elif isinstance(value, str):
        out.append(_string(value))
    elif isinstance(value, (list, tuple)):
        out.append("[")
        for i, item in enumerate(value):
            if i:
                out.append(",")
            _encode(item, out)
        out.append("]")
    elif isinstance(value, dict):
        out.append("{")
        # Sort by the UTF-8 code-unit sequence of the key, not by a
        # locale-sensitive collation. Keys must be strings: a dict keyed by
        # anything else has no stable ordering across runs.
        for i, key in enumerate(sorted(value, key=_sort_key)):
            if i:
                out.append(",")
            out.append(_string(key))
            out.append(":")
            _encode(value[key], out)
        out.append("}")
    else:
        raise NonCanonicalValue(
            f"{type(value).__name__} has no canonical form. Convert it "
            "explicitly rather than letting a repr into a hashed artifact."
        )


def _sort_key(key: Any) -> bytes:
    if not isinstance(key, str):
        raise NonCanonicalValue(
            f"mapping key {key!r} is {type(key).__name__}, not str; key order "
            "would not be stable"
        )
    return key.encode("utf-8")


_ESCAPES = {
    '"': '\\"',
    "\\": "\\\\",
    "\n": "\\n",
    "\r": "\\r",
    "\t": "\\t",
    "\b": "\\b",
    "\f": "\\f",
}


def _string(value: str) -> str:
    out = ['"']
    for ch in value:
        esc = _ESCAPES.get(ch)
        if esc is not None:
            out.append(esc)
        elif ord(ch) < 0x20:
            out.append(f"\\u{ord(ch):04x}")
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def dumps(value: Any) -> bytes:
    """Canonical bytes: UTF-8, no BOM, `LF` terminated, sorted keys."""
    parts: list[str] = []
    _encode(value, parts)
    parts.append("\n")
    return "".join(parts).encode("utf-8")


def content_address(value: Any) -> str:
    """`sha256:<hex>` over the canonical bytes."""
    return "sha256:" + hashlib.sha256(dumps(value)).hexdigest()
