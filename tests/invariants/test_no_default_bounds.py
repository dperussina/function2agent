"""INV-006 — no bound and no ceiling ships a default (FR-005, FR-049, Q-10).

Q-10 was accepted as recommended: required configuration, startup fails loudly.
FR-005 was extended the same day to take Q-10's treatment rather than FR-047's,
on the reasoning the plan records — an unvalidated staleness ceiling is a number
nobody checked, but an invented spend ceiling is an unbounded liability wearing
one.

So the assertion is about the *schema*, not about a particular call. A test that
only checked `load()` with an empty environment would keep passing if a default
were added and the test's environment happened to set the key.
"""

from __future__ import annotations

import pytest

from src.contracts.config import SUPERVISOR_KEYS, ConfigError, Key, load

BOUND_KEYS = (
    "SANDBOX_MEMORY_MAX",
    "SANDBOX_CPU_MAX",
    "SANDBOX_CPU_TOTAL",
    "SANDBOX_PIDS_MAX",
)
CEILING_KEYS = (
    "SESSION_CEILING_SPEND_USD",
    "SESSION_CEILING_TOKENS",
    "SESSION_CEILING_WALL_CLOCK_SECONDS",
    "SESSION_CEILING_TURNS",
)

BY_NAME = {key.name: key for key in SUPERVISOR_KEYS}


@pytest.mark.parametrize("name", BOUND_KEYS + CEILING_KEYS)
def test_no_default_is_declared(name: str) -> None:
    key = BY_NAME[name]
    assert key.default is None, (
        f"{name} has acquired the default {key.default!r}. Q-10 requires "
        "startup to fail rather than default, and FR-005/FR-049 state none."
    )
    assert key.no_default_reason, (
        f"{name} has no default and no stated reason. The operator sees the "
        "reason at startup; without it the failure is just an absence."
    )


@pytest.mark.parametrize("name", BOUND_KEYS + CEILING_KEYS)
def test_every_declared_bound_is_present_in_the_schema(name: str) -> None:
    """A key silently dropped from the schema is a bound nobody sets."""
    assert name in BY_NAME


def test_loading_with_nothing_set_reports_every_missing_key_at_once() -> None:
    with pytest.raises(ConfigError) as caught:
        load(SUPERVISOR_KEYS, env={})
    message = str(caught.value)
    for name in BOUND_KEYS + CEILING_KEYS:
        assert name in message, f"{name} was not named in the failure"
    assert "Nothing has been started" in message


def test_a_key_with_a_default_must_be_marked_unvalidated() -> None:
    """FR-043 — a default nobody measured is a claim, and must say so."""
    for key in SUPERVISOR_KEYS:
        if key.default is not None:
            assert key.unvalidated, (
                f"{key.name} ships the default {key.default!r} without "
                "unvalidated=True. FR-043 requires it be marked wherever it "
                "is emitted."
            )


def test_cpu_max_of_max_is_rejected_as_an_unset_bound() -> None:
    """`cpu.max = max` is the unset bound that looks set."""
    env = _complete_env() | {"SANDBOX_CPU_MAX": "max 100000"}
    with pytest.raises(ConfigError, match="unset bound"):
        load(SUPERVISOR_KEYS, env=env)


def test_a_complete_environment_loads_so_the_test_is_not_vacuous() -> None:
    config = load(SUPERVISOR_KEYS, env=_complete_env())
    assert config["SANDBOX_MEMORY_MAX"] == 512 * 2**20
    assert config["SANDBOX_CPU_MAX"] == "50000 100000"
    assert config.is_unvalidated("CAPABILITY_LEASE_INTERVAL_SECONDS")


def test_zero_is_not_accepted_as_a_bound() -> None:
    """A zero bound is not a tight bound; it is a stopped session."""
    for name, value in (("SANDBOX_MEMORY_MAX", "0"),
                        ("SANDBOX_CPU_MAX", "0 100000")):
        with pytest.raises(ConfigError):
            load(SUPERVISOR_KEYS, env=_complete_env() | {name: value})


def _complete_env() -> dict[str, str]:
    return {
        "SANDBOX_MEMORY_MAX": "512MiB",
        "SANDBOX_CPU_MAX": "50000/100000",
        "SANDBOX_CPU_TOTAL": "120",
        "SANDBOX_PIDS_MAX": "256",
        "SESSION_CEILING_SPEND_USD": "5.00",
        "SESSION_CEILING_TOKENS": "500000",
        "SESSION_CEILING_WALL_CLOCK_SECONDS": "900",
        "SESSION_CEILING_TURNS": "40",
        "F2A_STATE_DIR": "/var/lib/f2a",
        "F2A_LOCATION_SET": "/etc/f2a/locations.json",
        "F2A_TENANT_ID": "t-1",
        "F2A_DEPLOYMENT_ID": "d-1",
    }


def test_key_dataclass_cannot_hold_a_default_without_a_reason_field() -> None:
    """Guards the schema's own shape, so the checks above stay meaningful."""
    fields = Key.__dataclass_fields__
    assert "default" in fields and "no_default_reason" in fields
    assert "unvalidated" in fields
