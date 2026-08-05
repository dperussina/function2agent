"""T059 — the opaque-state carrier (T-02, FR-037).

Four properties, and three of them are invisible to any test that hashes what
it just packed.

1. **Length-prefixed framing.** A separator join loses a payload containing the
   separator, and Google's payloads are arbitrary bytes. Every arm here plants
   a NUL.
2. **The carrier type is remembered.** A str re-injected as bytes is not
   verbatim, and neither is the reverse.
3. **Keyed by provider.** T-02 forbids merging across providers, and the
   failure mode of handing one provider another's blob is a silently degraded
   turn rather than an error the provider raises.
4. **Never readable.** `OpaqueSlot.__repr__` is what stops a payload reaching a
   log through an f-string nobody reviewed.
"""

from __future__ import annotations

import pytest

from src.runtime.providers.base import ROLE_ASSISTANT, ROLE_USER, WireTurn
from src.runtime.providers.state import (
    MAGIC,
    OpaqueSlot,
    OpaqueStateError,
    ProviderMismatchError,
    pack,
    provider_of,
    read_path,
    reinject,
    slot_from_carrier,
    unpack,
    write_path,
)

#: A payload no separator survives and no text codec round-trips: a NUL, a bare
#: UTF-8 continuation byte, and a trailing NUL so a strip is visible too.
HOSTILE = b"\x00\x80\xfe payload \x00"


def test_a_payload_containing_a_nul_survives_the_round_trip():
    """The framing's whole reason.

    A separator join is the obvious way to carry several values and it is
    silently wrong here: the value comes back split in two and every digest
    downstream still matches, because both halves were hashed together.
    """
    slots = (OpaqueSlot(path=("parts", 0, "sig"), value=HOSTILE),
             OpaqueSlot(path=("parts", 1, "sig"), value=b"\x00\x00\x00"))
    back = unpack("google", pack("google", slots))
    assert back == slots
    assert back[0].value == HOSTILE
    assert len(back) == 2, (
        "a separator-framed carrier reports four values here, or two whose "
        "boundaries fell in the wrong places")


def test_packing_is_deterministic_and_preserves_the_providers_order():
    """A digest over the carrier is only an identity if the bytes are stable.

    And the order is **not sorted**: it is the provider's, and sorting a
    sequence we do not read would be an interpretation of it.
    """
    slots = [OpaqueSlot(path=("b",), value=b"2"),
             OpaqueSlot(path=("a",), value=b"1")]
    assert pack("xai", slots) == pack("xai", slots)
    assert unpack("xai", pack("xai", slots))[0].path == ("b",)
    assert pack("xai", slots) != pack("xai", list(reversed(slots)))


def test_a_text_carrier_comes_back_as_text_and_a_binary_one_as_bytes():
    """One bit, and it is load-bearing.

    Three providers carry the field as a JSON string and Google carries it as
    bytes. Without the flag, Anthropic's signature is re-injected as `bytes`
    into a field the SDK serializes as a string, or Google's `Part` is handed a
    `str` where the proto wants bytes. Neither is verbatim, and neither is
    visible in a digest taken on our side of the wire.
    """
    text = slot_from_carrier(("content", 0, "signature"), "ErUBCkYIBRgCKkB")
    binary = slot_from_carrier(("parts", 0, "thought_signature"), HOSTILE)
    assert text.text is True and binary.text is False

    back = unpack("anthropic", pack("anthropic", [text, binary]))
    assert isinstance(back[0].carrier(), str)
    assert back[0].carrier() == "ErUBCkYIBRgCKkB"
    assert isinstance(back[1].carrier(), bytes)
    assert back[1].carrier() == HOSTILE


def test_one_providers_state_cannot_be_unpacked_by_another():
    """T-02: never merged across providers."""
    blob = pack("anthropic", [OpaqueSlot(path=("x",), value=b"s")])
    assert provider_of(blob) == "anthropic"
    with pytest.raises(ProviderMismatchError, match="never merged"):
        unpack("openai", blob)
    # And the same blob still reads for its own provider, so the arm above is
    # not passing because `unpack` refuses everything.
    assert len(unpack("anthropic", blob)) == 1


def test_two_blobs_concatenated_are_refused_rather_than_half_read():
    """The merge T-02 forbids, arriving as a byte operation.

    Without the trailing-bytes check the second blob is simply ignored: the
    frame count says one, one slot is read, and the rest is never looked at. A
    caller that appended state instead of replacing it would lose half of it
    with no error at all.
    """
    first = pack("xai", [OpaqueSlot(path=("a",), value=b"1")])
    second = pack("xai", [OpaqueSlot(path=("b",), value=b"2")])
    with pytest.raises(OpaqueStateError, match="trailing bytes"):
        unpack("xai", first + second)


def test_a_raw_provider_field_reaching_the_column_unwrapped_is_refused():
    """No magic, no read.

    The realistic version of this is a driver that stored `signature.encode()`
    directly. It round-trips fine for that one provider and is unattributable
    for every other, which is a defect that only shows up when a second
    provider is configured.
    """
    with pytest.raises(OpaqueStateError, match="not packed opaque state"):
        provider_of(b"ErUBCkYIBRgCKkB")
    assert provider_of(pack("google", [])) == "google"


def test_a_future_framing_version_is_refused_rather_than_guessed():
    blob = bytearray(pack("google", [OpaqueSlot(path=("a",), value=b"x")]))
    blob[len(MAGIC)] = 99
    with pytest.raises(OpaqueStateError, match="version 99"):
        provider_of(bytes(blob))


def test_the_payload_is_not_in_the_repr_or_the_str():
    """FR-037's third clause, made structural.

    Not truncated and not masked: absent. A repr showing a prefix discloses
    content on every debugger frame and in every unhandled traceback, which is
    the readable form the requirement forbids — and it is the path a redaction
    filter never covers, because nobody wrote the log line on purpose.
    """
    slot = OpaqueSlot(path=("content", 0, "signature"),
                      value=b"SECRET-REASONING-BLOB")
    for rendering in (repr(slot), str(slot), f"{slot}", "%s" % (slot,)):
        assert "SECRET" not in rendering
        assert "21 opaque bytes" in rendering
    # The path is *not* redacted, and that is deliberate: it is a position, it
    # is needed in the message that says re-injection failed, and it discloses
    # nothing about the payload.
    assert "signature" in repr(slot)


def test_a_str_offered_as_an_opaque_value_is_refused():
    """Accepting it would mean choosing an encoding somewhere else."""
    with pytest.raises(OpaqueStateError, match="opaque value is bytes"):
        OpaqueSlot(path=("a",), value="already text")  # type: ignore[arg-type]
    with pytest.raises(OpaqueStateError, match="no path"):
        OpaqueSlot(path=(), value=b"x")


def test_an_unexpected_carrier_type_names_the_extractor_rather_than_coercing():
    with pytest.raises(OpaqueStateError, match="arrived as int"):
        slot_from_carrier(("a",), 7)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Paths, and re-injection.


def test_reading_a_path_that_no_longer_resolves_returns_none():
    payload = {"content": [{"signature": "S"}]}
    assert read_path(payload, ("content", 0, "signature")) == "S"
    assert read_path(payload, ("content", 4, "signature")) is None
    assert read_path(payload, ("absent",)) is None


def test_writing_refuses_to_create_a_route_that_is_not_there():
    """A re-injection that built the missing structure would attach an opaque
    value to a turn the provider did not send — and several providers validate
    theirs server-side."""
    payload: dict = {"content": [{"type": "thinking"}]}
    assert write_path(payload, ("content", 0, "signature"), "S") is True
    assert payload["content"][0]["signature"] == "S"
    assert write_path(payload, ("content", 3, "signature"), "S") is False
    assert write_path(payload, ("missing", "deep", "x"), "S") is False
    assert len(payload["content"]) == 1


def test_reinjection_targets_each_turns_own_assistant_entry_and_counts_writes():
    first = {"role": "assistant", "content": [{"type": "thinking"}]}
    second = {"role": "assistant",
              "content": [{"type": "thinking"}, {"type": "text"}]}
    turns = [WireTurn(role=ROLE_USER, payload={"role": "user"}),
             WireTurn(role=ROLE_ASSISTANT, payload=first),
             WireTurn(role=ROLE_USER, payload={"role": "user"}),
             WireTurn(role=ROLE_ASSISTANT, payload=second),
             WireTurn(role=ROLE_USER, payload={"role": "user"})]
    states = [
        pack("anthropic",
             [slot_from_carrier(("content", 0, "signature"), "SIG-1")]),
        pack("anthropic",
             [slot_from_carrier(("content", 0, "signature"), "SIG-2")]),
    ]
    assert reinject("anthropic", turns, states) == 2
    # Each state lands on the entry it came off, in order. Swapping them would
    # produce a request every provider accepts and one of them validates.
    assert first["content"][0]["signature"] == "SIG-1"
    assert second["content"][0]["signature"] == "SIG-2"
    # The user turns are untouched: state on a results entry would attach one
    # turn's reasoning to another.
    assert turns[2].payload == {"role": "user"}
    assert turns[4].payload == {"role": "user"}


def test_a_turn_that_emitted_nothing_keeps_its_slot_and_gets_no_write():
    """The defect that made the drop worse than a drop, at this layer.

    `states_for` returned the most recent *non-`None`* state until 2026-08-05,
    and this wrote whatever it was given onto the *last* assistant entry. With
    a silent turn in the middle, an older turn's signature landed on a
    `tool_use` block — a value the provider signed for a different message and
    cannot detect on the way in.
    """
    thinking = {"role": "assistant", "content": [{"type": "thinking"}]}
    tool_use = {"role": "assistant", "content": [{"type": "tool_use"}]}
    turns = [WireTurn(role=ROLE_ASSISTANT, payload=thinking),
             WireTurn(role=ROLE_USER, payload={"role": "user"}),
             WireTurn(role=ROLE_ASSISTANT, payload=tool_use)]
    blob = pack("anthropic",
                [slot_from_carrier(("content", 0, "signature"), "SIG")])

    assert reinject("anthropic", turns, [blob, None]) == 1
    assert thinking["content"][0]["signature"] == "SIG"
    assert tool_use["content"][0] == {"type": "tool_use"}, (
        "an older turn's signature was written onto a tool_use block")


def test_a_chain_that_does_not_line_up_with_the_conversation_is_refused():
    """Alignment is checked, not assumed.

    Zipping short would pair each state with whichever entry happened to be at
    that index, which is the misattribution above with a different cause.
    """
    turns = [WireTurn(role=ROLE_ASSISTANT,
                      payload={"content": [{"type": "thinking"}]})]
    blob = pack("anthropic",
                [slot_from_carrier(("content", 0, "signature"), "SIG")])
    with pytest.raises(OpaqueStateError, match="positionally aligned"):
        reinject("anthropic", turns, [blob, blob])


def test_a_rebuilt_assistant_turn_makes_reinjection_fail_loudly():
    """The adapter defect, planted.

    An adapter that rebuilds the assistant turn from the fields it recognised
    produces a turn with no slot for the signature. Silently writing nothing
    there is exactly finding 016's negative control — the request is still
    well-formed, the provider still accepts it, and the chain still answers
    correctly.
    """
    rebuilt = {"role": "assistant", "content": [{"type": "text", "text": "hi"}]}
    turns = [WireTurn(role=ROLE_ASSISTANT, payload=rebuilt)]
    blob = pack("anthropic",
                [slot_from_carrier(("content", 4, "signature"), "SIG")])
    with pytest.raises(OpaqueStateError, match="rebuilt rather than carried"):
        reinject("anthropic", turns, [blob])


def test_reinjecting_with_no_assistant_turn_is_refused():
    blob = pack("xai", [slot_from_carrier(("encrypted_content",), "E")])
    with pytest.raises(OpaqueStateError, match="no assistant turn"):
        reinject("xai", [WireTurn(role=ROLE_USER, payload={})], [blob])


def test_no_state_and_empty_state_stay_different_all_the_way_down():
    """`None` is a provider that returned nothing; an empty slot list is a
    provider that returned an empty carrier. The journal's column is nullable
    to keep them apart and this is the layer above it."""
    assert reinject("xai", [], ()) == 0
    assert reinject("xai", [], [None]) == 0
    empty = pack("xai", [])
    assert empty != b""
    assert unpack("xai", empty) == ()
    assert reinject("xai", [WireTurn(role=ROLE_ASSISTANT, payload={})],
                    [empty]) == 0
