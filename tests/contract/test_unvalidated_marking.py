"""T034 — every FR-043 value appears marked on every external surface.

"External surface" is taken to mean anything a human or another system reads:
a log line, a trace span, an error message, a serialized artifact, a startup
banner. The test drives the value through each of those shapes rather than
inspecting intent, because the failure FR-043 is about is a number *arriving*
somewhere unmarked, not a developer meaning well.
"""

from __future__ import annotations

import json
import logging

import pytest

from src.contracts import config as cfg
from src.contracts.unvalidated import (
    MARKER,
    NAMES,
    Unvalidated,
    UnvalidatedError,
    is_marked,
    mark,
)
from tests.contract.test_configuration_failloud import VALID


@pytest.fixture()
def loaded():
    return cfg.load(cfg.SUPERVISOR_KEYS, VALID)


def test_every_declared_fr043_value_is_in_the_schema(loaded) -> None:
    assert set(loaded.unvalidated) == NAMES, (
        "the FR-043 registry and the configuration schema disagree about "
        f"which values are unmeasured: {set(loaded.unvalidated) ^ NAMES}"
    )
    assert NAMES == {
        "STALENESS_CEILING_SECONDS",
        "DRIFT_CHECK_INTERVAL_SECONDS",
        "CAPABILITY_LEASE_INTERVAL_SECONDS",
    }


@pytest.mark.parametrize("name", sorted(NAMES))
def test_string_interpolation_carries_the_marking(name: str, loaded) -> None:
    """The commonest external surface: an f-string in a log line."""
    value = loaded[name]
    assert is_marked(f"{value}"), f"f-string of {name} lost the marking"
    assert is_marked(str(value))
    assert is_marked(repr(value))
    assert is_marked("interval is %s" % (value,))
    assert is_marked("{}".format(value))


@pytest.mark.parametrize("name", sorted(NAMES))
def test_a_format_spec_does_not_strip_the_marking(name: str, loaded) -> None:
    """`f"{interval:.1f}"` is the subtle one: a format spec bypasses __str__."""
    value = loaded[name]
    assert is_marked(f"{value:.1f}"), (
        f"{name} rendered with a format spec dropped the marking, which is "
        "the path a developer takes when tidying up a log line"
    )


@pytest.mark.parametrize("name", sorted(NAMES))
def test_the_value_cannot_be_coerced_to_a_number_implicitly(name: str, loaded) -> None:
    """An implicit numeric conversion is an unmarked escape.

    Arithmetic on a marked value must be a TypeError, so the developer writes
    `.value` and the read is visible in review.
    """
    value = loaded[name]
    for operation in (lambda v: v + 1, lambda v: float(v), lambda v: int(v),
                      lambda v: v * 2, lambda v: round(v)):
        with pytest.raises(TypeError):
            operation(value)


@pytest.mark.parametrize("name", sorted(NAMES))
def test_a_log_record_carries_the_marking(name: str, loaded, caplog) -> None:
    with caplog.at_level(logging.INFO):
        logging.getLogger("f2a.test").info("configured %s = %s", name, loaded[name])
    assert caplog.records, "nothing was logged"
    assert is_marked(caplog.records[0].getMessage())


@pytest.mark.parametrize("name", sorted(NAMES))
def test_the_serialized_shape_carries_the_marking(name: str, loaded) -> None:
    record = loaded[name].marked_record()
    assert record[MARKER] is True
    assert record["provenance"]
    assert record["requirement"] == "FR-043"
    assert is_marked(record)
    assert is_marked(json.loads(json.dumps(record)))


def test_the_marked_values_map_covers_every_one(loaded) -> None:
    marked = loaded.marked_values()
    assert set(marked) == NAMES
    for name, record in marked.items():
        assert record[MARKER] is True, f"{name} emitted unmarked"


def test_the_bare_value_requires_an_explicit_call(loaded) -> None:
    """FR-043 does not make the number unusable, it makes reading it an act."""
    for name in NAMES:
        assert isinstance(loaded.raw(name), float)
        assert loaded.raw(name) == loaded[name].value


def test_an_unmarked_value_has_no_provenance_to_hide_behind() -> None:
    with pytest.raises(UnvalidatedError, match="provenance"):
        Unvalidated(value=1.0, name="X", provenance="")
    with pytest.raises(UnvalidatedError, match="name itself"):
        Unvalidated(value=1.0, name="", provenance="somewhere")


def test_marking_a_value_outside_the_registry_is_refused() -> None:
    """The registry is the list T034 scans against; a value marked outside it
    makes that list incomplete."""
    with pytest.raises(UnvalidatedError, match="not a declared FR-043 value"):
        mark("SOME_OTHER_CEILING", 1.0)


def test_the_detector_is_not_vacuous() -> None:
    """A marking test whose detector returns True for everything passes for a
    surface that emits nothing at all."""
    assert not is_marked("interval is 5.0")
    assert not is_marked(5.0)
    assert not is_marked({"value": 5.0})
    assert not is_marked({"value": 5.0, MARKER: True})  # provenance missing
    assert is_marked({"value": 5.0, MARKER: True, "provenance": "research §3.3"})


def test_every_provenance_says_where_the_number_came_from() -> None:
    """A marking that says 'unmeasured' and nothing else invites the reader to
    keep using it and stop asking."""
    from src.contracts.unvalidated import PROVENANCES

    for name, provenance in PROVENANCES.items():
        assert len(provenance) > 60, f"{name}'s provenance is too thin to act on"
        assert any(word in provenance.lower() for word in
                   ("no measurement", "not measured", "unmeasured", "chosen",
                    "stated default", "research")), (
            f"{name}'s provenance does not say what kind of number it is"
        )
