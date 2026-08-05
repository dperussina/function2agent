"""T059 — `provider_state` as opaque bytes (T-02, FR-037).

Captured verbatim from the raw response, re-injected verbatim, **keyed by
provider, never merged, never interpreted, never logged in a form readable as
content**.

## What is opaque, and what is not

The payload is opaque. Its *location* is not, and it cannot be: on two of the
four providers the opaque field does not travel alone. Anthropic's `signature`
sits on a `thinking` block inside an assistant turn's content list; Google's
`thought_signature` sits on a `Part` beside the function call it belongs to.
Re-injecting those means putting each value back at the position it came off,
so the carrier records a path per value.

So the discipline this module holds is narrower than "we store a blob" and
sharper than it: **the bytes between the frames are never decoded, never
compared for content, never transformed, and never rendered**. A path is read.
A payload is moved.

## Why the framing is length-prefixed rather than separated

The obvious carrier for several values is a separator join. It is wrong here and
the failure is silent: Google's `thought_signature` is genuinely binary — the
`google-genai` SDK hands back `bytes`, not text — so any byte you pick as a
separator can occur inside a payload, and a value containing it comes back split
into two. Every digest comparison downstream still passes, because both halves
were hashed together. `tests/unit/test_provider_state.py` plants a NUL inside a
value for exactly this reason and a removal proof swaps the framing back.

## Why the carrier records whether the value was text

Three providers carry their opaque field as a JSON string; Google carries it as
bytes. Bytes are what the journal's column holds, so a string has to be encoded
to get in — and if the carrier does not remember which side it came from, the
value re-injected into an Anthropic request is `bytes` where the SDK wants
`str`, or Google's `Part` gets a `str` where the proto wants `bytes`. Neither is
verbatim. The flag is one bit and it is load-bearing.

## What a digest is for

`src/runtime/turn.py::state_digest` is the only form of this that may reach a
trace. Nothing here logs a payload, and `OpaqueSlot.__repr__` is overridden so
that the accident — a `print`, an f-string in an error message, a debugger
repr — cannot disclose one either. FR-037 makes that structural rather than a
review item, in the same shape `src/contracts/secret.py` does it for
credentials.
"""

from __future__ import annotations

import json
import struct
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

from src.runtime.providers.base import (
    ROLE_ASSISTANT,
    ProviderError,
    WireTurn,
    require_provider,
)

#: Magic and version. A blob that does not start with this is not ours, and the
#: version byte is what lets the framing change without a silent misread: an old
#: blob under a new reader fails loudly instead of unpacking to nonsense.
MAGIC = b"F2AP"
VERSION = 1
_HEADER = MAGIC + bytes([VERSION])

_FLAG_TEXT = 0x01

#: `str` values are encoded with this and decoded back with it. UTF-8 is
#: lossless and reversible over every string a JSON body can carry, which is
#: what makes the encode-decode pair not an interpretation.
_TEXT_CODEC = "utf-8"


class OpaqueStateError(ProviderError):
    """Opaque state that cannot be carried as described."""


class ProviderMismatchError(OpaqueStateError):
    """State produced by one provider offered to another.

    A distinct type because it is the failure T-02 names — *never merged* — and
    because the caller's remedy is to drop the state rather than to repair it.
    """


@dataclass(frozen=True)
class OpaqueSlot:
    """One opaque value and where on the turn it sat.

    `path` is a positional route into the provider's own response shape, e.g.
    `("content", 3, "signature")`. It is read and written; it is never used to
    decide anything about the payload.

    `text` records the carrier the provider used. See the module docstring.
    """

    path: tuple[Any, ...]
    value: bytes
    text: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.value, (bytes, bytearray)):
            raise OpaqueStateError(
                "an opaque value is bytes. Accepting a str here would mean "
                "choosing an encoding somewhere else, and the encoding is the "
                "interpretation FR-037 forbids."
            )
        if not self.path:
            raise OpaqueStateError(
                "an opaque value with no path cannot be put back where it came "
                "from, and re-injection is the whole of FR-037"
            )

    def __repr__(self) -> str:
        """**The payload is not in here, by construction.**

        Not truncated and not masked with a fixed string of the same length —
        absent, with only its size. A repr that showed a prefix would disclose
        content on every debugger frame and every unhandled traceback, which is
        the readable form FR-037 forbids.
        """
        return (
            f"OpaqueSlot(path={self.path!r}, "
            f"value=<{len(self.value)} opaque bytes>, text={self.text})"
        )

    __str__ = __repr__

    def carrier(self) -> str | bytes:
        """The value in the shape the provider handed it over in."""
        return self.value.decode(_TEXT_CODEC) if self.text else bytes(self.value)


def slot_from_carrier(path: Sequence[Any], carrier: str | bytes) -> OpaqueSlot:
    """The inverse of `OpaqueSlot.carrier`, and the only place a str is encoded."""
    if isinstance(carrier, str):
        return OpaqueSlot(path=tuple(path), value=carrier.encode(_TEXT_CODEC),
                          text=True)
    if isinstance(carrier, (bytes, bytearray)):
        return OpaqueSlot(path=tuple(path), value=bytes(carrier), text=False)
    raise OpaqueStateError(
        f"an opaque field arrived as {type(carrier).__name__}. The four "
        "providers carry it as str or bytes; anything else means the extractor "
        "picked up the wrong field."
    )


def pack(provider: str, slots: Iterable[OpaqueSlot]) -> bytes:
    """Frame a turn's opaque values into the bytes the journal column holds.

    Deterministic: the same slots in the same order produce the same bytes, so
    a digest over the result is a stable identity rather than a property of
    this process. Order is **preserved, never sorted** — the order is the
    provider's and sorting it would be an interpretation of a sequence we do not
    read.
    """
    require_provider(provider)
    name = provider.encode(_TEXT_CODEC)
    out = bytearray(_HEADER)
    out += struct.pack(">I", len(name))
    out += name
    materialized = list(slots)
    out += struct.pack(">I", len(materialized))
    for slot in materialized:
        route = json.dumps(list(slot.path), separators=(",", ":")).encode(
            _TEXT_CODEC)
        out += struct.pack("B", _FLAG_TEXT if slot.text else 0)
        # Length-prefixed, both of them. See the module docstring: a separator
        # is what loses a payload that contains it, and Google's payloads are
        # arbitrary bytes.
        out += struct.pack(">I", len(route))
        out += route
        out += struct.pack(">I", len(slot.value))
        out += slot.value
    return bytes(out)


def unpack(provider: str, blob: bytes) -> tuple[OpaqueSlot, ...]:
    """Read the frames back, refusing another provider's state.

    The provider is checked **here** rather than at the call site, because the
    call sites are four drivers and a check repeated four times is a check three
    of them can be written without.
    """
    require_provider(provider)
    recorded = provider_of(blob)
    if recorded != provider:
        raise ProviderMismatchError(
            f"opaque state recorded by {recorded!r} was offered to "
            f"{provider!r}. T-02: never merged across providers — the blob is "
            "not a portable format and the failure mode of handing it over is "
            "a silently degraded turn, not an error the provider raises."
        )

    view = memoryview(blob)
    at = len(_HEADER)
    at += 4 + struct.unpack_from(">I", view, at)[0]
    count, = struct.unpack_from(">I", view, at)
    at += 4

    slots: list[OpaqueSlot] = []
    for position in range(count):
        flags, = struct.unpack_from("B", view, at)
        at += 1
        route_len, = struct.unpack_from(">I", view, at)
        at += 4
        route = json.loads(bytes(view[at:at + route_len]).decode(_TEXT_CODEC))
        at += route_len
        value_len, = struct.unpack_from(">I", view, at)
        at += 4
        value = bytes(view[at:at + value_len])
        at += value_len
        if len(value) != value_len:
            raise OpaqueStateError(
                f"slot {position} declares {value_len} bytes and the blob holds "
                f"{len(value)}; it is truncated"
            )
        slots.append(OpaqueSlot(path=tuple(route), value=value,
                                text=bool(flags & _FLAG_TEXT)))
    if at != len(blob):
        raise OpaqueStateError(
            f"{len(blob) - at} trailing bytes after {count} slots. A blob with "
            "a tail is one that was concatenated with another, which is the "
            "merge T-02 forbids arriving as a byte operation."
        )
    return tuple(slots)


def provider_of(blob: bytes) -> str:
    """Which provider produced this blob, without unpacking its payloads."""
    if not isinstance(blob, (bytes, bytearray)):
        raise OpaqueStateError("opaque state is bytes")
    if not blob.startswith(MAGIC):
        raise OpaqueStateError(
            "this is not packed opaque state: no magic. A raw provider field "
            "reaching the column unwrapped would round-trip for one provider "
            "and be unattributable for the rest."
        )
    version = blob[len(MAGIC)]
    if version != VERSION:
        raise OpaqueStateError(
            f"opaque state framed at version {version}; this reader is "
            f"version {VERSION}. Refused rather than guessed."
        )
    at = len(_HEADER)
    name_len, = struct.unpack_from(">I", blob, at)
    at += 4
    return bytes(blob[at:at + name_len]).decode(_TEXT_CODEC)


def read_path(payload: Any, path: Sequence[Any]) -> Any:
    """Follow a recorded path into a payload, or return `None`.

    `None` rather than raising: a path that no longer resolves means the
    response shape moved, and the caller's job is to report an absent value —
    which is a legitimate outcome on every provider — rather than to crash a
    session over a field that is optional by measurement.
    """
    node = payload
    for step in path:
        try:
            node = node[step]
        except (KeyError, IndexError, TypeError):
            return None
    return node


def write_path(payload: Any, path: Sequence[Any], value: Any) -> bool:
    """Put a value back at a recorded path. False if the path does not exist.

    Refuses to *create* the route. A re-injection that built the missing
    structure would put an opaque value onto a turn the provider did not send,
    and the provider validates several of these server-side.
    """
    if not path:
        return False
    node = payload
    for step in path[:-1]:
        try:
            node = node[step]
        except (KeyError, IndexError, TypeError):
            return False
    last = path[-1]
    if isinstance(node, dict):
        node[last] = value
        return True
    if isinstance(node, list) and isinstance(last, int) and 0 <= last < len(node):
        node[last] = value
        return True
    return False


def reinject(
    provider: str, turns: Sequence[WireTurn], states: Sequence[bytes | None]
) -> int:
    """Put each turn's opaque values back onto **that turn's** assistant entry.

    Shared by all four drivers so that "re-injected verbatim" has one
    implementation. Four copies would be four chances for one provider's path
    to be written with a decode in it, and the arm that would catch it is the
    one provider-specific fixture nobody ran that week.

    `states` is `src/runtime/context.py::states_for`'s result: one entry per
    kept turn, in turn order, `None` where that turn emitted none. It is
    **positionally aligned** with the assistant entries in `turns`, and a
    length mismatch is refused rather than zipped short.

    **Why alignment is checked rather than assumed.** This took a single blob
    and wrote it onto the *last* assistant entry until 2026-08-05. Given a
    conversation where an intervening turn emitted no state, the caller handed
    over an older turn's blob and this wrote it onto a later turn's entry — at
    the recorded path, which on Anthropic meant a `signature` key appearing on a
    `tool_use` block. The provider had signed neither. Refusing a mismatch is
    what turns that back into an error.

    Returns the number of values written. `0` with a non-empty state is a
    failure: it means the state was carried across the boundary and then
    dropped on the floor at the last step, which is invisible in the response
    and is exactly finding 016's negative control.
    """
    carried = list(states)
    if not any(blob is not None for blob in carried):
        return 0

    targets = [turn.payload for turn in turns if turn.role == ROLE_ASSISTANT]
    if not targets:
        raise OpaqueStateError(
            f"{provider}: opaque state was given with no assistant turn to "
            "put it back on. The state belongs to a turn the conversation no "
            "longer holds, and injecting it anywhere else would attach one "
            "turn's reasoning to another."
        )
    if len(targets) != len(carried):
        raise OpaqueStateError(
            f"{provider}: {len(carried)} turns of opaque state against "
            f"{len(targets)} assistant entries in the conversation. The two "
            "are positionally aligned by construction, so a mismatch means the "
            "conversation and the turn history disagree about what happened — "
            "and pairing them off anyway would attach one turn's reasoning to "
            "another, which the provider signs and cannot detect."
        )

    written = 0
    for target, blob in zip(targets, carried):
        if blob is None:
            continue
        slots = unpack(provider, blob)
        landed = sum(
            1 for slot in slots
            if write_path(target, slot.path, slot.carrier())
        )
        if landed != len(slots):
            raise OpaqueStateError(
                f"{provider}: {len(slots) - landed} of {len(slots)} opaque "
                "values had no path left to write to. The assistant turn was "
                "rebuilt rather than carried, which is the adapter defect "
                "FR-037 exists for — and it produces a request the provider "
                "accepts."
            )
        written += landed
    return written
