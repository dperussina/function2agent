"""T060 — the cassette harness, tested as the instrument it is.

A replay harness is green by default when it is broken. A player that matches
nothing answers nothing and asserts nothing; a loader that tolerates an empty
file replays zero interactions and reports a pass; a fixture that consumed one
of six turns is indistinguishable from one that consumed six. None of those
raise, and none of them are visible in a green run.

So every refusal in `harness.py` has an arm here that plants the shape it
refuses, and `tests/conformance/test_provider_state_roundtrip.py` is separately
shown failing under a one-bit corruption of a committed cassette — recorded in
`tests/removal_proofs.sh` rather than described here, because a proof of that
kind has to be run rather than asserted.
"""

from __future__ import annotations

import base64
import copy
import json

import pytest

from tests.conformance.cassettes import harness


def _minimal() -> dict:
    payload = base64.b64encode(b"\x00opaque\xfe").decode()
    return {
        "cassette_version": harness.CASSETTE_VERSION,
        "provider": "anthropic",
        "model": "m",
        "sdk": "anthropic",
        "sdk_version": "0.120.2",
        "provenance": {"kind": harness.KIND_DERIVED,
                       "shape_source": "arm_anthropic.py",
                       "payload_source": "synthetic"},
        "opaque_selectors": [["messages", "*", "content", "*", "signature"]],
        "interactions": [
            {"turn": 0, "request_turns": 1,
             "opaque": [{"path": ["content", 0, "signature"],
                         "carrier": "binary", "b64": payload}],
             "expected_state_digest": "sha256:pinned",
             "response": {"content": [{"type": "thinking",
                                       "signature": {"$opaque": 0}}]}},
            {"turn": 1, "request_turns": 3, "opaque": [],
             "expected_state_digest": None,
             "response": {"content": [{"type": "text", "text": "done"}]}},
        ],
    }


def _write(tmp_path, document, name="c.json"):
    path = tmp_path / name
    path.write_text(json.dumps(document))
    return path


def test_a_well_formed_cassette_loads_and_materializes_its_markers(tmp_path):
    """The positive control. Without it every refusal below could be a loader
    that refuses everything, which is a different broken instrument."""
    cassette = harness.load(_write(tmp_path, _minimal()))
    assert cassette.provider == "anthropic"
    assert cassette.turns_with_state() == 1
    assert cassette.turns_without_state() == 1
    # The marker became the declared payload, in its declared carrier.
    signature = cassette.interactions[0].response["content"][0]["signature"]
    assert signature == b"\x00opaque\xfe"
    assert isinstance(signature, bytes)


def test_a_missing_cassette_is_an_error_and_not_an_empty_one(tmp_path):
    with pytest.raises(harness.CassetteError, match="no cassette at"):
        harness.load(tmp_path / "absent.json")


def test_a_cassette_with_no_interactions_is_refused_at_load(tmp_path):
    """The quietest possible cassette. A player over it answers nothing, every
    loop body runs zero times, and every assertion inside them is vacuous."""
    document = _minimal()
    document["interactions"] = []
    with pytest.raises(harness.CassetteError, match="no interactions"):
        harness.load(_write(tmp_path, document))


@pytest.mark.parametrize("kind", [None, "", "recorded-ish", "synthetic"])
def test_a_cassette_with_no_declared_provenance_is_refused(tmp_path, kind):
    """Provenance is what separates a transcript from a fabrication.

    A cassette whose payloads cannot be told from a recording is one that will
    eventually be cited as a measurement, which is the reclassification
    constitution Principle I exists to prevent.
    """
    document = _minimal()
    document["provenance"] = {} if kind is None else {"kind": kind}
    with pytest.raises(harness.CassetteError, match="provenance kind"):
        harness.load(_write(tmp_path, document))


def test_opaque_values_without_a_pinned_digest_are_refused(tmp_path):
    document = _minimal()
    document["interactions"][0]["expected_state_digest"] = None
    with pytest.raises(harness.CassetteError, match="no expected_state_digest"):
        harness.load(_write(tmp_path, document))


def test_a_pinned_digest_with_no_opaque_values_is_refused(tmp_path):
    """The inverse, and the one that would pass silently.

    A turn that pins a digest and declares no values makes the fixture's digest
    block compare `None` against a string and fail for the wrong reason, or —
    worse — skip the comparison entirely because the turn reads as absent.
    """
    document = _minimal()
    document["interactions"][1]["expected_state_digest"] = "sha256:x"
    with pytest.raises(harness.CassetteError, match="no opaque values"):
        harness.load(_write(tmp_path, document))


def test_turns_that_are_not_dense_from_zero_are_refused(tmp_path):
    """A player matches by turn. A gap means a turn nothing ever answers."""
    document = _minimal()
    document["interactions"][1]["turn"] = 5
    with pytest.raises(harness.CassetteError, match="dense from"):
        harness.load(_write(tmp_path, document))


def test_a_marker_pointing_past_the_declared_values_is_refused(tmp_path):
    document = _minimal()
    document["interactions"][0]["response"]["content"][0]["signature"] = {
        "$opaque": 7}
    with pytest.raises(harness.CassetteError, match="references opaque value"):
        harness.load(_write(tmp_path, document))


def test_a_wrong_cassette_version_is_refused_rather_than_read(tmp_path):
    document = _minimal()
    document["cassette_version"] = harness.CASSETTE_VERSION + 1
    with pytest.raises(harness.CassetteError, match="cassette version"):
        harness.load(_write(tmp_path, document))


# ---------------------------------------------------------------------------
# The player.


def test_a_turn_with_no_interaction_raises_rather_than_answering(tmp_path):
    """The failure a replay harness must never absorb.

    Returning an empty payload here is what makes a harness report green over a
    cassette it never matched, and sliding to the nearest interaction is worse:
    every assertion downstream would be about a different turn.
    """
    player = harness.Player(harness.load(_write(tmp_path, _minimal())))
    with pytest.raises(harness.CassetteMiss, match="no interaction for turn 2"):
        player.respond(2, {}, conversation_length=5)


def test_a_conversation_of_the_wrong_length_is_refused(tmp_path):
    """Replay that is purely ordinal cannot see a dropped turn.

    A driver that lost an assistant entry would be handed exactly the response
    it would have been handed anyway, and the recorded answer would be an
    answer to a question the driver did not ask.
    """
    player = harness.Player(harness.load(_write(tmp_path, _minimal())))
    with pytest.raises(harness.CassetteMiss, match="recorded against a conversation"):
        player.respond(1, {}, conversation_length=2)


def test_a_player_that_served_some_turns_reports_the_rest(tmp_path):
    """`assert_exhausted` against the partial run, which is the realistic one.

    A fixture that broke out of its loop after the first turn passes every
    assertion it reached. What it did not do is exercise the chain the file
    describes, and nothing but this says so.
    """
    cassette = harness.load(_write(tmp_path, _minimal()))
    player = harness.Player(cassette)
    player.respond(0, {"a": 1}, conversation_length=1)
    with pytest.raises(harness.CassetteError, match=r"turns \[1\] were never played"):
        player.assert_exhausted()
    # And the complete run does not raise, so the arm above is not passing
    # because `assert_exhausted` always raises.
    player.respond(1, {"a": 2}, conversation_length=3)
    player.assert_exhausted()
    assert player.requests == [{"a": 1}, {"a": 2}]


# ---------------------------------------------------------------------------
# The selector walker — a second implementation on purpose.


@pytest.mark.parametrize(
    "selector,expected",
    [
        (["messages", "*", "content", "*", "signature"], ["S1", "S2"]),
        (["messages", 0, "content", 0, "signature"], ["S1"]),
        (["messages", "*", "absent"], []),
        (["nothing", "*"], []),
    ],
)
def test_the_walker_finds_every_value_at_a_declared_route(selector, expected):
    request = {"messages": [
        {"content": [{"signature": "S1"}, {"text": "t"}]},
        {"content": [{"signature": "S2"}]},
        {"content": []},
    ]}
    assert harness.walk(request, selector) == expected


def test_the_walker_is_not_the_drivers_injector():
    """It knows no provider, which is the whole reason it is trustworthy here.

    An assertion that read a request back through the code that wrote it is
    satisfied by a writer that wrote nowhere and a reader that looked nowhere.
    """
    source = (harness.HERE / "harness.py").read_text()
    walk_body = source.split("def walk(", 1)[1].split("\ndef ", 1)[0]
    for provider in ("anthropic", "openai", "google", "xai",
                     "signature", "encrypted_content", "thought_signature"):
        assert provider not in walk_body, (
            f"`walk` mentions {provider!r}; it is supposed to be a route "
            "follower with no knowledge of any provider's shape")


def test_the_recorder_refuses_rather_than_spending(tmp_path):
    """The one thing the recorder does today, asserted so it stays deliberate."""
    with pytest.raises(NotImplementedError, match="paid API calls"):
        harness.record_stub("anthropic")


def test_every_committed_cassette_loads(tmp_path):
    """The directory's own floor.

    `cassette_paths()` is a glob, so a file added with a typo in its provenance
    would sit there unread by every parametrized fixture. This reads all of
    them.
    """
    paths = harness.cassette_paths()
    assert len(paths) == 6, (
        f"{len(paths)} cassettes in {harness.HERE.name}; the fixture set is "
        "four providers plus the sparse and silent arms")
    for path in paths:
        cassette = harness.load(path)
        assert cassette.interactions
        assert cassette.kind == harness.KIND_DERIVED


def test_a_deep_copy_of_a_cassette_is_not_shared_between_loads(tmp_path):
    """Two loads, two payloads.

    The drivers mutate the assistant turn in place when they re-inject, so a
    cassette handing out the same dict twice would let one test's re-injection
    show up in another's, and the second would pass on the first's work.
    """
    path = _write(tmp_path, _minimal())
    first = harness.load(path)
    second = harness.load(path)
    assert first.interactions[0].response is not second.interactions[0].response
    original = copy.deepcopy(first.interactions[0].response)
    first.interactions[0].response["content"][0]["signature"] = b"tampered"
    assert second.interactions[0].response == original
