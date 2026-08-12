"""T121 — provenance as data on every derived contract and every derived check.

**Requirement**: FR-026 — *"Every derived contract and every derived check MUST
carry, as data, the rule that derived it, the source symbol and file it came
from, the analyzer version, a content hash, and its validation status."*

Six fields. Each arm below is one of them refusing to be absent, wrong-shaped or
default-true, because "carry as data" is satisfied by a field that exists and
defeated by a field anything can put anything in.

The `validated` half is deliberately *not* built here. T122 owns the comparison
against the target's published specification; what T121 owes is that the status
is a field, that `provisional` is what a derivation produces on its own, and
that `validated` is unconstructible without naming the artifact that validated
it.
"""

from __future__ import annotations

import dataclasses

import pytest

from src.analysis import provenance as prov
from src.analysis.provenance import (
    DERIVATION_RULES,
    Provenance,
    ProvenanceError,
    ValidationStatus,
)

GOOD = dict(
    derivation_rule="return_annotation",
    source_symbol="stock_report",
    source_file="service/inventory.py",
    content_hash="sha256:" + "a" * 64,
)


def test_all_six_fields_fr_026_names_are_present() -> None:
    p = Provenance(**GOOD)
    fields = {f.name for f in dataclasses.fields(p)}
    for required in (
        "derivation_rule",
        "source_symbol",
        "source_file",
        "analyzer_version",
        "content_hash",
        "validation_status",
    ):
        assert required in fields, f"FR-026 names {required} and it is not a field"


# ---------------------------------------------------------------------------
# The rule that derived it.


def test_the_derivation_rule_must_name_a_registered_rule() -> None:
    """A free string names nothing a reader can look up."""
    with pytest.raises(ProvenanceError) as excinfo:
        Provenance(**{**GOOD, "derivation_rule": "seemed_right"})
    assert "seemed_right" in str(excinfo.value)
    assert "return_annotation" in str(excinfo.value), (
        "the refusal lists the rules that do exist, or it is a dead end"
    )


def test_every_registered_rule_states_what_it_reads_and_what_it_emits() -> None:
    assert DERIVATION_RULES, "an empty rule set makes the check above vacuous"
    for name, rule in DERIVATION_RULES.items():
        assert rule.name == name
        assert rule.reads, f"{name} does not say what artifact class it reads"
        assert rule.emits, f"{name} does not say what it produces"
        assert rule.reads in prov.FR_023_ARTIFACT_CLASSES, (
            f"{name} reads {rule.reads!r}, which FR-023 does not admit as a "
            "source. A check derived from anything else is not derived from an "
            "artifact the target codebase already contains"
        )


def test_no_rule_reads_a_model() -> None:
    """FR-023's prohibition, stated over the rule table rather than the code."""
    assert "model_assessment" not in prov.FR_023_ARTIFACT_CLASSES
    for name, rule in DERIVATION_RULES.items():
        assert "model" not in rule.reads, name


# ---------------------------------------------------------------------------
# The source symbol and file.


def test_the_source_symbol_is_required() -> None:
    with pytest.raises(ProvenanceError):
        Provenance(**{**GOOD, "source_symbol": ""})


def test_an_absolute_source_path_is_refused(tmp_path) -> None:
    """Not tidiness. An absolute path is volatile under FR-055.

    `src/contracts/envelope.py` scans the hashed payload and moves anything
    that looks like a filesystem path out beside the hash. A provenance record
    carrying `/Users/someone/checkout/service/inventory.py` would therefore be
    stripped from the artifact's identity, and FR-026's "as data" would hold
    only until the artifact was wrapped. A repository-relative path is stable
    across two checkouts and survives the scan.
    """
    with pytest.raises(ProvenanceError) as excinfo:
        Provenance(**{**GOOD, "source_file": "/Users/x/service/inventory.py"})
    assert "relative" in str(excinfo.value).lower()


def test_a_windows_style_path_is_refused_too() -> None:
    with pytest.raises(ProvenanceError):
        Provenance(**{**GOOD, "source_file": r"C:\src\inventory.py"})


def test_a_relative_source_path_survives_the_envelope_scan() -> None:
    """The property the arm above exists to protect, checked against the scanner."""
    from src.contracts.envelope import scan
    from src.contracts.schemas import DERIVED_CHECK

    payload = {"provenance": Provenance(**GOOD).to_payload()}
    assert scan(payload, DERIVED_CHECK) == [], (
        "a provenance record that trips the volatility scanner cannot be "
        "hashed with the check it belongs to"
    )


# ---------------------------------------------------------------------------
# The analyzer version and the content hash.


def test_the_analyzer_version_is_recorded_and_is_ours() -> None:
    p = Provenance(**GOOD)
    assert p.analyzer_version == prov.ANALYZER_VERSION
    assert prov.ANALYZER_VERSION != prov.CODEGRAPH_REVISION, (
        "the analyzer's version and the vendored indexer's revision are two "
        "facts. Collapsing them would make our own release read as an "
        "upstream one, which is exactly the confusion U-04 is about"
    )


def test_the_content_hash_must_be_a_content_address() -> None:
    with pytest.raises(ProvenanceError):
        Provenance(**{**GOOD, "content_hash": "abc"})
    with pytest.raises(ProvenanceError):
        Provenance(**{**GOOD, "content_hash": "sha256:" + "A" * 64})


def test_the_content_hash_is_over_the_source_construct() -> None:
    """So that FR-028 can see the symbol change and re-derive.

    Two different function bodies hash differently; the same body hashes the
    same however it was reached.
    """
    one = prov.hash_source_construct("def f():\n    return 1\n")
    same = prov.hash_source_construct("def f():\n    return 1\n")
    other = prov.hash_source_construct("def f():\n    return 2\n")
    assert one == same
    assert one != other
    assert one.startswith("sha256:")


# ---------------------------------------------------------------------------
# The validation status. Principle I's boundary, as a default.


def test_a_derivation_is_provisional_unless_something_says_otherwise() -> None:
    assert Provenance(**GOOD).validation_status is ValidationStatus.PROVISIONAL


def test_validated_cannot_be_claimed_without_naming_the_artifact() -> None:
    with pytest.raises(ProvenanceError) as excinfo:
        Provenance(**GOOD, validation_status=ValidationStatus.VALIDATED)
    assert "validated_against" in str(excinfo.value)


def test_naming_an_artifact_without_the_status_is_also_refused() -> None:
    """The pair moves together, or a record claims an artifact it did not use."""
    with pytest.raises(ProvenanceError):
        Provenance(**GOOD, validated_against="openapi.json#/paths/~1parts")


def test_a_validated_record_carries_both() -> None:
    p = Provenance(
        **GOOD,
        validation_status=ValidationStatus.VALIDATED,
        validated_against="openapi.json#/paths/~1parts",
    )
    assert p.validation_status is ValidationStatus.VALIDATED
    assert p.to_payload()["validated_against"] == "openapi.json#/paths/~1parts"


def test_the_validating_artifact_may_not_be_the_source_the_rule_read() -> None:
    """Principle I as amended at v1.1.0: validated against an artifact its own
    derivation did not produce. Naming the source file it was derived from is
    the degenerate case and it is the one that would happen by accident."""
    with pytest.raises(ProvenanceError) as excinfo:
        Provenance(
            **GOOD,
            validation_status=ValidationStatus.VALIDATED,
            validated_against="service/inventory.py",
        )
    assert "own derivation" in str(excinfo.value)


# ---------------------------------------------------------------------------
# As data, and serializable as such.


def test_the_payload_carries_all_six_and_is_canonical() -> None:
    from src.contracts.canonical import dumps

    payload = Provenance(**GOOD).to_payload()
    assert set(payload) == {
        "derivation_rule",
        "source_symbol",
        "source_file",
        "analyzer_version",
        "content_hash",
        "validation_status",
        "validated_against",
    }
    assert payload["validation_status"] == "provisional", (
        "the status serializes as its value, not as a repr of the enum"
    )
    assert dumps(payload) == dumps(Provenance(**GOOD).to_payload())


def test_provenance_is_frozen() -> None:
    p = Provenance(**GOOD)
    with pytest.raises(dataclasses.FrozenInstanceError):
        p.derivation_rule = "postcondition_assert"  # type: ignore[misc]
