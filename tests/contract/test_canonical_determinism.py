"""T012 / SC-029 first clause — byte-identity determinism, not address identity.

**Why this test compares bytes and not content addresses.** A serializer that is
stable only within a process produces identical addresses in a single test run
and different ones across restarts. Comparing addresses would pass for exactly
that serializer, which is the one that breaks the drift detector. SC-029 says
"compares payloads byte for byte, not by comparing the addresses alone", and the
distinction is the whole test.

**What this is defending.** FR-055's note: content addressing over a
non-canonical serialization yields a different address on every re-derivation of
identical input, and a changed address on a source-derived artifact is what
FR-028 reads as source drift. A non-canonical serializer is a false-alarm
generator aimed at the one v1 capability with no measured false-alarm rate.

**The cross-process arm matters most.** Python's `hash()` is randomized per
process by `PYTHONHASHSEED`, so any serialization that depends on set iteration
or on dict ordering derived from hashing is stable in-process and unstable
across restarts. `test_the_payload_is_identical_across_processes` runs the
derivation in two subprocesses with different hash seeds. That is the arm that
would catch it; the in-process arm alone would not.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from src.contracts import envelope, schemas
from src.contracts.canonical import content_address, dumps

REPO = Path(__file__).resolve().parents[2]


def _fixture_document() -> dict:
    """One committed fixture, derived twice.

    Deliberately contains every construct the serializer has to order or
    format: nested mappings, a list of mappings, keys that sort differently
    under a locale-aware collation than under UTF-8 code units, ints, floats,
    booleans, null, and non-ASCII text.
    """
    return {
        "schema_version": "1.0.0",
        "deployment_id": "d-fixture",
        "operations": [
            {
                "id": "listOrders",
                "method": "GET",
                "effect_tier": "read_only",
                "parameters": {"page": 1, "per_page": 50, "expand": None},
                "cost_estimate": 0.25,
                "deprecated": False,
            },
            {
                "id": "getOrder",
                "method": "GET",
                "effect_tier": "read_only",
                # Keys chosen to sort differently by locale than by code unit.
                "notes": {"Ä": "a-diaeresis", "Z": "zed", "a": "ay", "ä": "lower"},
                "parameters": {"order_id": "opaque"},
                "cost_estimate": 0.1,
                "deprecated": False,
            },
        ],
        # Volatile, and therefore expected in the envelope rather than the hash.
        "captured_at": "2026-08-03T12:00:00Z",
        "source_url": "https://api.example.com/openapi.json",
        "analyzer_host": "runner-7",
    }


def test_two_derivations_produce_identical_payload_bytes() -> None:
    first = envelope.wrap("served_operation_set", _fixture_document())
    second = envelope.wrap("served_operation_set", _fixture_document())
    assert first.payload_bytes() == second.payload_bytes(), (
        "the same input produced different payload bytes; every re-analysis "
        "would look like source drift (FR-055, FR-028)"
    )


def test_key_insertion_order_does_not_change_the_bytes() -> None:
    """The commonest way a payload becomes non-canonical.

    Two analyses that build the same mapping in a different order — because a
    dict comprehension ran over a different iteration order — must be the same
    artifact.
    """
    document = _fixture_document()
    reversed_document = {k: document[k] for k in reversed(list(document))}
    assert envelope.wrap("served_operation_set", document).payload_bytes() == \
        envelope.wrap("served_operation_set", reversed_document).payload_bytes()


def test_the_volatile_values_are_not_in_the_hashed_bytes() -> None:
    """The envelope is only doing its job if the hash actually excludes them."""
    wrapped = envelope.wrap("served_operation_set", _fixture_document())
    raw = wrapped.payload_bytes().decode()
    for volatile in ("2026-08-03T12:00:00Z", "api.example.com", "runner-7"):
        assert volatile not in raw, (
            f"{volatile!r} is inside the hashed payload; it varies between "
            "runs and would move the content address"
        )
    # And they are still recorded, beside the hash.
    assert wrapped.context["captured_at"] == "2026-08-03T12:00:00Z"
    assert wrapped.context["analyzer_host"] == "runner-7"


def test_changing_a_volatile_value_does_not_move_the_address() -> None:
    """The property FR-028 depends on, stated directly."""
    a = envelope.wrap("served_operation_set", _fixture_document())
    later = {**_fixture_document(),
             "captured_at": "2027-01-01T00:00:00Z",
             "analyzer_host": "runner-99"}
    b = envelope.wrap("served_operation_set", later)
    assert a.address == b.address, (
        "re-analysing unchanged input on a different host at a different time "
        "moved the content address. FR-028 would read that as source drift."
    )


def test_the_volatility_scanner_catches_an_undeclared_volatile_value() -> None:
    """The positive control for the scanner itself.

    Every other assertion here is about a document whose volatile fields were
    declared correctly, so the scanner could be returning the empty list
    unconditionally and nothing above would notice. The scanner is what stands
    between an author who forgets a `volatile` entry and a source-derived
    artifact whose address moves on every re-derivation — which FR-028 reads as
    source drift, aimed at the one capability with no measured false-alarm rate.
    """
    document = _fixture_document()
    document["derived_on_host"] = "runner-7.internal.example.com"

    with pytest.raises(envelope.VolatileValueError) as caught:
        envelope.wrap("served_operation_set", document)

    message = str(caught.value)
    assert "derived_on_host" in message, "the scanner did not name the field"
    assert "volatile" in message and "stable_despite_appearance" in message, (
        "the refusal does not tell the author which of the two fixes to apply"
    )


def test_the_scanner_does_not_fire_on_a_correctly_declared_document() -> None:
    """The other half of the control: a scanner that refuses everything would
    also pass the test above."""
    envelope.wrap("served_operation_set", _fixture_document())


def test_changing_a_real_value_does_move_the_address() -> None:
    """The other half. A determinism test that only asserts stability would
    pass for a serializer that returned a constant."""
    a = envelope.wrap("served_operation_set", _fixture_document())
    changed = _fixture_document()
    changed["operations"][0]["effect_tier"] = "reversible_write"
    b = envelope.wrap("served_operation_set", changed)
    assert a.address != b.address, (
        "a changed effect tier did not move the content address; the "
        "serializer is discarding payload content"
    )


@pytest.mark.parametrize("seed_a,seed_b", [("0", "1"), ("12345", "99999")])
def test_the_payload_is_identical_across_processes(seed_a: str, seed_b: str) -> None:
    """The arm that catches a serializer stable only within one process.

    `PYTHONHASHSEED` randomizes string hashing, so anything that reaches set
    iteration order or hash-derived dict ordering differs between these two
    subprocesses. Comparing content addresses alone would not distinguish this
    from success, which is why SC-029 asks for bytes.
    """
    script = (
        "import sys, json;"
        "sys.path.insert(0, %r);"
        "from tests.contract.test_canonical_determinism import _fixture_document;"
        "from src.contracts import envelope;"
        "w = envelope.wrap('served_operation_set', _fixture_document());"
        "sys.stdout.buffer.write(w.payload_bytes())"
    ) % str(REPO)

    def run(seed: str) -> bytes:
        env = {**os.environ, "PYTHONHASHSEED": seed, "PYTHONPATH": str(REPO)}
        result = subprocess.run(
            [sys.executable, "-c", script], capture_output=True, env=env, cwd=REPO)
        assert result.returncode == 0, result.stderr.decode()
        return result.stdout

    first, second = run(seed_a), run(seed_b)
    assert first == second, (
        f"payload bytes differ between PYTHONHASHSEED={seed_a} and "
        f"{seed_b}. The serializer is stable within a process and unstable "
        "across restarts, which is the exact defect address comparison hides."
    )
    assert first, "the subprocess produced no payload; the test is vacuous"


def test_every_source_derived_kind_is_covered_by_a_determinism_arm() -> None:
    """FR-055 applies to all eight; drift reads the source-derived ones.

    Rather than write eight near-identical tests, this asserts the serializer
    is exercised over each source-derived kind's declared shape, and fails if a
    new source-derived kind appears with no arm.
    """
    covered = set()
    for schema in schemas.SCHEMAS:
        if not schema.source_derived:
            continue
        document = {name: _placeholder(name) for name in schema.required}
        document["schema_version"] = schema.version
        first, second = dumps(document), dumps(dict(reversed(list(document.items()))))
        assert first == second, f"{schema.kind} is not order-stable"
        assert content_address(document)
        covered.add(schema.kind)
    assert covered == {s.kind for s in schemas.SCHEMAS if s.source_derived}
    assert covered, "no source-derived kinds; this test covers nothing"


def _placeholder(name: str):
    if name.endswith(("s", "list")):
        return []
    if name == "confidence":
        return 0.5
    return f"<{name}>"


def test_the_fixture_is_not_trivial() -> None:
    """A determinism test over `{}` passes and proves nothing."""
    document = _fixture_document()
    serialized = json.dumps(document)
    assert len(serialized) > 400, "the fixture is too small to exercise ordering"
    assert any(isinstance(v, list) for v in document.values())
    nested = document["operations"][1]["notes"]
    assert len(nested) >= 4 and "ä" in nested, (
        "the fixture no longer exercises non-ASCII key collation, which is "
        "where a locale-sensitive sort would differ from a code-unit sort"
    )
