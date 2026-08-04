"""T011 — the envelope that holds volatile values BESIDE the hash, never under it.

FR-055: re-deriving a source-derived artifact from unchanged input must produce
a byte-identical payload. Every value that varies between two runs over the same
input — timestamps, filesystem paths, hostnames — has to be excluded from the
hashed payload.

**Why this module refuses rather than advises.** "Put volatile values in the
envelope" is a convention, and a convention is not a mechanism: the first author
who adds `generated_at` to a payload gets a new content address on every
re-analysis, the drift detector reads that as source change, and the capability
with no measured false-alarm rate starts producing false alarms. So the envelope
does two things, and the second is the load-bearing one:

1. It **moves** every field the schema declares volatile out of the payload.
2. It **scans what is left** and refuses to hash anything that still looks
   volatile — an absolute filesystem path, a hostname, an epoch-shaped number,
   an ISO-8601 timestamp, a UUID. A field that trips the scanner and is
   genuinely stable must be named in the schema's `stable_despite_appearance`
   with a justification.

The scanner is deliberately noisy in the safe direction. A false positive costs
one line in a schema and a sentence saying why; a false negative costs a
false-alarm channel nobody notices until the drift rate is wrong.

**What the scanner cannot catch**, stated because a scanner that is trusted
beyond its reach is worse than none: a value that varies between runs without
looking like anything — an iteration order, a dictionary hash seed, a random
identifier that is not UUID-shaped, a counter. T012's byte-identity determinism
test is what covers those, by deriving the same artifact twice and comparing
bytes. The scanner catches the common shapes at authoring time; the test catches
the rest at CI time. Neither substitutes for the other.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping

from src.contracts.canonical import content_address, dumps
from src.contracts.schemas import ArtifactSchema, SchemaError, require


class VolatileValueError(SchemaError):
    """A value that varies between runs was about to be hashed."""


# The shapes. Each carries the name used in the error, so a refusal says which
# rule fired rather than only that one did — the same discipline FR-011 applies
# to denials.
_ABSOLUTE_PATH = re.compile(r"^(/[^/\0]+){2,}/?$")
_WINDOWS_PATH = re.compile(r"^[A-Za-z]:[\\/]")
_ISO_TIMESTAMP = re.compile(
    r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:?\d{2})?$")
_UUID = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_HOSTNAME = re.compile(
    r"^(?=.{4,253}$)([a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+"
    r"[a-zA-Z]{2,63}$")

# Epoch seconds, roughly 2001-09-09 to 2065. Narrow on purpose: a bare integer
# is usually a count, and flagging every large integer would make the scanner
# noise rather than signal.
_EPOCH_LOW = 1_000_000_000
_EPOCH_HIGH = 3_000_000_000


def _volatile_shape(value: Any) -> str | None:
    """Name the volatile shape `value` has, or None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        if _EPOCH_LOW <= float(value) <= _EPOCH_HIGH:
            return "epoch_timestamp"
        return None
    if not isinstance(value, str):
        return None
    if _ISO_TIMESTAMP.match(value):
        return "iso_timestamp"
    if _UUID.match(value):
        return "uuid"
    if _WINDOWS_PATH.match(value) or _ABSOLUTE_PATH.match(value):
        return "filesystem_path"
    if _HOSTNAME.match(value):
        return "hostname"
    return None


def _walk(value: Any, path: str, findings: list[tuple[str, str, Any]]) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            _walk(item, f"{path}.{key}" if path else str(key), findings)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _walk(item, f"{path}[]", findings)
    else:
        shape = _volatile_shape(value)
        if shape is not None:
            findings.append((path, shape, value))


def scan(payload: Mapping[str, Any], schema: ArtifactSchema) -> list[tuple[str, str, Any]]:
    """Every value in `payload` that looks volatile and is not excused."""
    findings: list[tuple[str, str, Any]] = []
    _walk(payload, "", findings)
    excused = set(schema.stable_despite_appearance)
    return [f for f in findings if f[0] not in excused]


@dataclass(frozen=True)
class Envelope:
    """A hashed payload and the volatile context sitting beside it.

    `address` is over `payload` alone. Nothing in `context` is hashed, and
    nothing in `context` may be read as part of the artifact's identity — that
    is the entire reason it is a separate field rather than a marked subtree.
    """

    kind: str
    schema_version: str
    payload: Mapping[str, Any]
    context: Mapping[str, Any]
    address: str

    def payload_bytes(self) -> bytes:
        return dumps(self.payload)

    def to_record(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "schema_version": self.schema_version,
            "address": self.address,
            "payload": dict(self.payload),
            "context": dict(self.context),
        }


def wrap(kind: str, document: Mapping[str, Any]) -> Envelope:
    """Split `document` into a hashed payload and an unhashed envelope.

    Raises rather than guessing in three cases, all of them authoring errors
    that would otherwise surface as a drift false alarm weeks later:

    - the kind is not one of FR-054's eight;
    - the document does not satisfy its schema;
    - a value that still looks volatile survived into the payload.
    """
    schema = require(kind)
    schema.validate(document)

    payload = {k: v for k, v in document.items() if k not in schema.volatile}
    context = {k: v for k, v in document.items() if k in schema.volatile}

    findings = scan(payload, schema)
    if findings:
        lines = "\n".join(
            f"  {path or '<root>'}: looks like {shape} ({value!r})"
            for path, shape, value in findings
        )
        raise VolatileValueError(
            f"{kind}: {len(findings)} value(s) in the hashed payload vary "
            f"between runs over the same input:\n{lines}\n"
            "FR-055 requires these beside the hash, not underneath it. Either "
            f"add the field to {kind}'s `volatile` tuple so it moves into the "
            "envelope, or — if it really is stable across two runs — name it "
            "in `stable_despite_appearance` with the reason. Leaving it here "
            "gives the artifact a new content address on every re-derivation, "
            "which FR-028 reads as source drift."
        )

    return Envelope(
        kind=kind,
        schema_version=schema.version,
        payload=payload,
        context=context,
        address=content_address(payload),
    )
