"""T162 — three configured identities; co-location is not assumed (FR-034)."""

from __future__ import annotations

import pytest

from src.contracts import config as cfg
from src.contracts.topology import (
    ANALYSIS_ADDR_KEY,
    ROLES,
    RUNTIME_ADDR_KEY,
    TARGET_ADDR_KEY,
    Topology,
    TopologyError,
    load_topology,
)

SAME_HOST = {
    ANALYSIS_ADDR_KEY: "127.0.0.1:7101",
    RUNTIME_ADDR_KEY: "127.0.0.1:7102",
    TARGET_ADDR_KEY: "127.0.0.1:7103",
}


def test_same_host_is_three_identities_not_one_process() -> None:
    topology = load_topology(SAME_HOST)
    assert topology.analysis == "127.0.0.1:7101"
    assert topology.runtime == "127.0.0.1:7102"
    assert topology.target == "127.0.0.1:7103"
    assert len({topology.analysis, topology.runtime, topology.target}) == 3
    assert ROLES == ("analysis", "runtime", "target")


def test_a_missing_analysis_address_is_not_filled_from_the_runtime() -> None:
    with pytest.raises(TopologyError, match="not filled from another role"):
        Topology(
            analysis="",
            runtime="127.0.0.1:7102",
            target="127.0.0.1:7103",
        )


def test_a_missing_analysis_key_is_a_fail_loud() -> None:
    env = {k: v for k, v in SAME_HOST.items() if k != ANALYSIS_ADDR_KEY}
    with pytest.raises(TopologyError, match=ANALYSIS_ADDR_KEY):
        load_topology(env)


def test_topology_keys_have_no_default() -> None:
    names = {key.name for key in cfg.TOPOLOGY_KEYS}
    assert names == {ANALYSIS_ADDR_KEY, RUNTIME_ADDR_KEY, TARGET_ADDR_KEY}
    for key in cfg.TOPOLOGY_KEYS:
        assert key.default is None, (
            f"{key.name} acquired the default {key.default!r}; a missing "
            "analysis address would then be filled rather than refused (FR-034)"
        )
        assert key.no_default_reason is None
        assert key.requirement == "FR-034"


def test_listen_address_is_not_a_python_topology_key() -> None:
    python_keys = {key.name for key in (
        *cfg.SUPERVISOR_KEYS, *cfg.RUNTIME_KEYS, *cfg.ANALYSIS_KEYS,
        *cfg.TOPOLOGY_KEYS,
    )}
    assert "F2A_PROXY_LISTEN" not in python_keys
    assert TARGET_ADDR_KEY == "F2A_PROXY_UPSTREAM_ADDR"
    assert not hasattr(Topology, "compose")
    assert not hasattr(Topology, "namespace")
    assert not hasattr(Topology, "docker")


def test_a_host_without_a_port_is_not_an_identity() -> None:
    with pytest.raises(TopologyError, match="not host:port"):
        Topology(analysis="127.0.0.1", runtime="127.0.0.1:7102",
                 target="127.0.0.1:7103")
