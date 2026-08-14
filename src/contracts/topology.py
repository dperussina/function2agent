"""T162 — analysis / runtime / target as three configured identities (FR-034).

The boundary is explicit in configuration even when all three run on one
host. Co-location is not assumed: a missing analysis address is a
fail-loud, not the runtime's host. Same-host is allowed and is still
three addresses, not "localhost means one process".

The enforcement point is the path to the target (`F2A_PROXY_LISTEN` in
Go), not a fourth colocated role. That listen address is a Go env and is
not declared as a Python key. The target identity consumed here is
`F2A_PROXY_UPSTREAM_ADDR`, the name the enforcement point already reads.

T159/T160 consume this. This module does not assume Docker, compose, or a
network namespace, and it does not open a client.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from src.contracts.config import TOPOLOGY_KEYS, ConfigError, load

ANALYSIS = "analysis"
RUNTIME = "runtime"
TARGET = "target"
ROLES: tuple[str, ...] = (ANALYSIS, RUNTIME, TARGET)

ANALYSIS_ADDR_KEY = "F2A_ANALYSIS_ADDR"
RUNTIME_ADDR_KEY = "F2A_RUNTIME_ADDR"
#: The target's pinned address — Go already requires this name. Not
#: `F2A_PROXY_LISTEN` (the enforcement point's listen address).
TARGET_ADDR_KEY = "F2A_PROXY_UPSTREAM_ADDR"

_KEY_FOR_ROLE = {
    ANALYSIS: ANALYSIS_ADDR_KEY,
    RUNTIME: RUNTIME_ADDR_KEY,
    TARGET: TARGET_ADDR_KEY,
}


class TopologyError(RuntimeError):
    """A role is missing or is not an identity. Nothing is started."""


def _address(role: str, key: str, raw: str) -> str:
    """One role's identity, or a fail-loud. Never another role's address."""
    value = raw.strip()
    if not value:
        raise TopologyError(
            f"{key} is unset. Co-location is not assumed: the "
            f"{role} address is not filled from another role (FR-034)."
        )
    host, sep, port = value.rpartition(":")
    if not sep or not host or not port:
        raise TopologyError(
            f"{key}={value!r} is not host:port. Three identities, even "
            f"on one host (FR-034)."
        )
    return value


@dataclass(frozen=True)
class Topology:
    """Three role identities. Same-host is allowed; inference is not."""

    analysis: str
    runtime: str
    target: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "analysis",
            _address(ANALYSIS, ANALYSIS_ADDR_KEY, self.analysis),
        )
        object.__setattr__(
            self, "runtime",
            _address(RUNTIME, RUNTIME_ADDR_KEY, self.runtime),
        )
        object.__setattr__(
            self, "target",
            _address(TARGET, TARGET_ADDR_KEY, self.target),
        )


def load_topology(env: Mapping[str, str] | None = None) -> Topology:
    """Resolve the three role keys, or fail loud naming every absence.

    A missing analysis address is not replaced by the runtime's. `load()`
    already treats empty as unset; construction then refuses any blank that
    reached it.
    """
    try:
        config = load(TOPOLOGY_KEYS, env=env)
    except ConfigError as exc:
        raise TopologyError(str(exc)) from exc
    return Topology(
        analysis=str(config[ANALYSIS_ADDR_KEY]),
        runtime=str(config[RUNTIME_ADDR_KEY]),
        target=str(config[TARGET_ADDR_KEY]),
    )
