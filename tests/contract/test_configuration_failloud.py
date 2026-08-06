"""T032 — every required key unset in turn, then malformed in turn.

Three assertions per key, and the third is the one that matters:

1. startup **fails**;
2. the message **names the key**, so an operator does not bisect the schema;
3. **nothing is started**.

The third is what distinguishes fail-closed from fail-noisy. A loader that
raises after opening a database, creating a cgroup or binding a socket has
already done the thing the missing configuration was supposed to bound, and
Q-10's whole point is that an unset bound must not run anything.
"""

from __future__ import annotations

import pytest

from src.contracts import config as cfg
from src.contracts.unvalidated import Unvalidated

VALID = {
    "SANDBOX_MEMORY_MAX": "512Mi",
    "SANDBOX_CPU_MAX": "200000 100000",
    "SANDBOX_CPU_TOTAL": "120.0",
    "SANDBOX_PIDS_MAX": "64",
    "SESSION_CEILING_SPEND_USD": "5.00",
    "SESSION_CEILING_TOKENS": "200000",
    "SESSION_CEILING_WALL_CLOCK_SECONDS": "900",
    "SESSION_CEILING_TURNS": "40",
    "F2A_STATE_DIR": "/var/lib/f2a",
    "F2A_LOCATION_SET": "/etc/f2a/locations.json",
    "F2A_TENANT_ID": "t-1",
    "F2A_DEPLOYMENT_ID": "d-1",
}

MALFORMED = {
    "SANDBOX_MEMORY_MAX": "lots",
    "SANDBOX_CPU_MAX": "max 100000",
    "SANDBOX_CPU_TOTAL": "soon",
    "SANDBOX_PIDS_MAX": "many",
    "SESSION_CEILING_SPEND_USD": "$5",
    "SESSION_CEILING_TOKENS": "2e5tokens",
    "SESSION_CEILING_WALL_CLOCK_SECONDS": "15m",
    "SESSION_CEILING_TURNS": "forty",
}

REQUIRED = tuple(k for k in cfg.SUPERVISOR_KEYS if k.default is None)


def test_the_fixture_is_complete() -> None:
    """A fail-loud suite whose 'valid' baseline is itself invalid proves
    nothing, because every case would fail for the wrong reason."""
    loaded = cfg.load(cfg.SUPERVISOR_KEYS, VALID)
    assert loaded["F2A_TENANT_ID"] == "t-1"
    assert set(VALID) == {k.name for k in REQUIRED}, (
        "the valid fixture and the required-key set have drifted: "
        f"{set(VALID) ^ {k.name for k in REQUIRED}}"
    )


@pytest.mark.parametrize("key", REQUIRED, ids=lambda k: k.name)
def test_each_required_key_unset_fails_and_names_itself(key) -> None:
    env = {k: v for k, v in VALID.items() if k != key.name}
    with pytest.raises(cfg.ConfigError) as caught:
        cfg.load(cfg.SUPERVISOR_KEYS, env)
    message = str(caught.value)
    assert key.name in message, f"the failure does not name {key.name}"
    assert key.requirement in message, (
        f"the failure does not cite the requirement behind {key.name}; an "
        "operator cannot tell whether it is safe to invent a value"
    )
    assert "Nothing has been started" in message


@pytest.mark.parametrize("key", REQUIRED, ids=lambda k: k.name)
def test_each_required_key_empty_is_treated_as_unset(key) -> None:
    """An empty environment variable is the commonest way a key goes missing —
    an unset shell variable expanded into a compose file. It must not parse."""
    env = {**VALID, key.name: ""}
    with pytest.raises(cfg.ConfigError) as caught:
        cfg.load(cfg.SUPERVISOR_KEYS, env)
    assert key.name in str(caught.value)


@pytest.mark.parametrize("name,bad", sorted(MALFORMED.items()))
def test_each_key_malformed_fails_and_names_itself(name: str, bad: str) -> None:
    env = {**VALID, name: bad}
    with pytest.raises(cfg.ConfigError) as caught:
        cfg.load(cfg.SUPERVISOR_KEYS, env)
    message = str(caught.value)
    assert name in message
    assert "malformed" in message


def test_every_problem_is_reported_at_once() -> None:
    """An operator who fixes one key and restarts to find a second is being
    made to discover the schema one failure at a time."""
    env = {k: v for k, v in VALID.items()
           if k not in {"SANDBOX_MEMORY_MAX", "SESSION_CEILING_TURNS"}}
    env["SANDBOX_CPU_TOTAL"] = "soon"
    with pytest.raises(cfg.ConfigError) as caught:
        cfg.load(cfg.SUPERVISOR_KEYS, env)
    message = str(caught.value)
    for name in ("SANDBOX_MEMORY_MAX", "SESSION_CEILING_TURNS", "SANDBOX_CPU_TOTAL"):
        assert name in message, f"{name} was not reported alongside the others"


def test_nothing_is_started_when_configuration_fails(tmp_path, monkeypatch) -> None:
    """The clause fail-loud and fail-closed differ on.

    `load` must not touch the filesystem, the cgroup tree, or a socket. Proved
    by making every one of those an error for the duration: if `load` reaches
    one, the test fails with that error rather than with ConfigError.
    """
    import socket

    def forbidden(*args, **kwargs):
        raise AssertionError(
            "configuration loading created a side effect before validating. "
            "Q-10 requires an unset bound to start nothing at all."
        )

    monkeypatch.setattr(socket.socket, "bind", forbidden)
    monkeypatch.setattr("os.mkdir", forbidden)
    monkeypatch.setattr("os.makedirs", forbidden)
    monkeypatch.setattr("sqlite3.connect", forbidden)

    env = {k: v for k, v in VALID.items() if k != "SANDBOX_MEMORY_MAX"}
    with pytest.raises(cfg.ConfigError):
        cfg.load(cfg.SUPERVISOR_KEYS, env)

    # And the successful path is equally side-effect free: configuration is
    # resolved, and acting on it is somebody else's call.
    cfg.load(cfg.SUPERVISOR_KEYS, VALID)


DECLARED: tuple[cfg.Key, ...] = tuple(
    {key.name: key for key in (*cfg.SUPERVISOR_KEYS, *cfg.RUNTIME_KEYS)}.values()
)
STATES_A_REASON = tuple(k for k in DECLARED if k.no_default_reason)


def test_no_key_that_states_a_no_default_reason_acquires_a_default() -> None:
    """Q-10 and FR-005, as a standing check rather than a review habit.

    **Selected on the reason field, over every declared tuple.** It used to be
    selected on `key.requirement in ("FR-049", "FR-005")` over
    `SUPERVISOR_KEYS` alone, which let a *citation string* decide what a
    *structural* property covered. Two consequences, and the second is why the
    selector moved rather than the container:

    * it reached eight of the twelve keys carrying a reason, the runtime-only
      four falling outside the container; and
    * retagging a key silently moved it in or out of the check.
      `MODEL_PRICES_OPERATOR` sat inside it only because it was mis-tagged
      `FR-005`, and correcting that tag to OD-27 would have dropped it out —
      so widening the container while keeping the requirement gate would have
      covered the one key it covered *because it was wrong*, and stopped the
      moment it was right.

    The property is the one the reason field states out loud: **a key whose
    schema says it deliberately ships no default must not ship one.** The
    regression that catches is a default appearing beside a reason text nobody
    thought to delete, which is an invented number wearing an argument against
    inventing it.
    """
    assert STATES_A_REASON, (
        "no declared key states a no-default reason. The selector has stopped "
        "selecting — this check now passes over nothing"
    )
    assert {k.name for k in STATES_A_REASON} & {k.name for k in cfg.RUNTIME_KEYS}, (
        "the selector reaches no runtime-only key. It has narrowed back to the "
        "supervisor's container, which is the gap it was widened to close"
    )
    for key in STATES_A_REASON:
        assert key.default is None, (
            f"{key.name} acquired the default {key.default!r} while still "
            f"declaring why it has none ({key.requirement}). A ceiling filled "
            "from an invented default is an unbounded liability wearing a "
            "number, and one filled beside its own no-default reason is that "
            "liability wearing an authorisation."
        )


def test_every_bound_and_ceiling_says_why_it_has_no_default() -> None:
    """The other half, and it keeps the requirement gate on purpose.

    Above asserts that a key stating a reason has no default; this asserts
    that a bound or a ceiling *states one at all* — which the selector above
    cannot do, since a key with neither a default nor a reason is exactly the
    key it does not select. FR-049 and FR-005 are named here because the
    obligation is theirs: `F2A_TENANT_ID` is also required and also defaults
    to nothing, and owes no argument, because nobody is tempted to guess it.
    """
    obliged = [k for k in DECLARED if k.requirement in ("FR-049", "FR-005")]
    assert len(obliged) == 8, (
        f"the bound-and-ceiling set moved to {len(obliged)}: "
        f"{sorted(k.name for k in obliged)}"
    )
    for key in obliged:
        assert key.no_default_reason, (
            f"{key.name} has no default and does not say why; the startup "
            "message would tell an operator to set it without telling "
            "them it is unsafe to guess"
        )


def test_a_key_outside_the_schema_is_not_readable() -> None:
    loaded = cfg.load(cfg.SUPERVISOR_KEYS, VALID)
    with pytest.raises(cfg.ConfigError, match="not in the declared schema"):
        loaded["SOME_KEY_SOMEBODY_ADDED"]


def test_the_defaulted_keys_are_exactly_the_marked_ones() -> None:
    """FR-043's boundary. A key with a default and no marking is an invented
    number presented as configuration."""
    defaulted = {k.name for k in cfg.SUPERVISOR_KEYS if k.default is not None}
    marked = {k.name for k in cfg.SUPERVISOR_KEYS if k.unvalidated}
    assert defaulted == marked, (
        f"keys with a default but no FR-043 marking: {sorted(defaulted - marked)}; "
        f"marked but with no default: {sorted(marked - defaulted)}"
    )


def test_the_marked_values_come_out_wrapped() -> None:
    loaded = cfg.load(cfg.SUPERVISOR_KEYS, VALID)
    for name in loaded.unvalidated:
        assert isinstance(loaded[name], Unvalidated), (
            f"{name} is marked in the schema but comes out of the loader bare; "
            "a surface emitting it would emit an unmeasured number unmarked"
        )
        assert isinstance(loaded.raw(name), float)
