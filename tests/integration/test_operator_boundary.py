"""T169 — FR-032: every component runs inside the operator's boundary.

**Requirement**: every component — analysis, the enforcement point, the
runtime and the credentials — MUST be able to run entirely inside the
operator's own boundary, and no target data or credential MUST be
required to leave it for the product to function.

## What this file is, and what it is not

**Do.** Static, in-process. Compose already wires the planes (T160).
Credential holders are typed (T161). Topology is three identities
(T162). Runtime Plane B `guarded()` is T113 and is not weakened here.
This file asks the FR-032 question those artifacts jointly answer: can
the product function without sending target data or a credential out of
the operator's boundary?

**Do not.** Duplicate T160's compose wiring tests. Duplicate T113's live
socket arms. Invent a live network-isolation test whose only CI outcome
is skip. Tick T166 / T167 / T170 / T214 / T215. Put the target
credential on runtime, or the provider credential on analysis /
supervisor / sandbox.

CI has no Docker compose-up. A missing daemon is not a pass on
isolation. There is no live half in this file: a skip-only isolation
test is the vacuity FR-032 would inherit.
"""

from __future__ import annotations

import ast
from pathlib import Path

import yaml

from src.contracts.credentials import (
    HOLDER_ANALYSIS,
    HOLDER_ENFORCEMENT,
    HOLDER_RUNTIME,
    HOLDER_SANDBOX,
    HOLDER_SUPERVISOR,
    NEVER_HOLD,
    PLANE_PROVIDER,
    PLANE_TARGET,
    PROVIDER_KEY,
    TARGET_KEY,
    hold,
)
from src.contracts.secret import Secret
from src.contracts.topology import (
    ANALYSIS_ADDR_KEY,
    RUNTIME_ADDR_KEY,
    TARGET_ADDR_KEY,
)

REPO = Path(__file__).resolve().parents[2]
COMPOSE_FILE = REPO / "deploy" / "compose" / "compose.yaml"
RUNTIME_MAIN = REPO / "src" / "runtime" / "main.py"
EGRESS = REPO / "src" / "runtime" / "egress.py"
T113 = REPO / "tests" / "contract" / "test_runtime_egress.py"

#: FR-032's four named components. Shrinking this set is a silent pass
#: over a component the requirement still names.
OPERATOR_COMPONENTS = (
    "analysis",
    "enforcement_point",
    "runtime",
    "credentials",
)

#: The claim. Flipping it is the plant.
TARGET_DATA_MUST_LEAVE = False

#: Compose DNS identities in the shipped bundle. Fixture (FR-043), not
#: a vendor SaaS hostname the product requires.
FIXTURE_TOPOLOGY = {
    ANALYSIS_ADDR_KEY: "analysis:8080",
    RUNTIME_ADDR_KEY: "runtime:8081",
    TARGET_ADDR_KEY: "target:9000",
}

VENDOR_MARKERS = (".com", "https://", "http://")

COMPONENT_SERVICE = {
    "analysis": "analysis",
    "runtime": "runtime",
    "enforcement_point": "enforcement",
}


def _load_compose() -> dict:
    loaded = yaml.safe_load(COMPOSE_FILE.read_text())
    assert isinstance(loaded, dict)
    return loaded


def _env(service: dict) -> dict[str, str]:
    raw = service.get("environment") or {}
    if isinstance(raw, list):
        out: dict[str, str] = {}
        for item in raw:
            key, _, value = str(item).partition("=")
            out[key] = value
        return out
    return {str(k): str(v) for k, v in raw.items()}


def test_every_named_component_is_inside_the_operator_bundle() -> None:
    """Analysis, enforcement, runtime, credentials — all inside, none SaaS."""
    assert OPERATOR_COMPONENTS == (
        "analysis",
        "enforcement_point",
        "runtime",
        "credentials",
    )
    compose = _load_compose()
    services = compose["services"]
    for component, service in COMPONENT_SERVICE.items():
        assert service in services, (
            f"{component} has no compose service {service}; it cannot run "
            "inside the operator's boundary (FR-032)"
        )
        image = services[service].get("image", "")
        assert str(image).startswith("f2a-"), (
            f"{service} image {image!r} is not a local f2a image; the "
            "component would have to leave the bundle to run"
        )
    # Credentials are not a fifth service. They are held on the two
    # planes already inside the bundle.
    provider = Secret("t169-provider-plain", name=PROVIDER_KEY)
    target = Secret("t169-target-plain", name=TARGET_KEY)
    hold(secret=provider, plane=PLANE_PROVIDER, holder=HOLDER_RUNTIME)
    hold(secret=target, plane=PLANE_TARGET, holder=HOLDER_ENFORCEMENT)
    assert HOLDER_ANALYSIS in NEVER_HOLD
    assert HOLDER_SUPERVISOR in NEVER_HOLD
    assert HOLDER_SANDBOX in NEVER_HOLD


def test_no_target_data_or_credential_is_required_to_leave() -> None:
    """The product functions without shipping target data or a credential out."""
    assert TARGET_DATA_MUST_LEAVE is False
    compose = _load_compose()
    services = compose["services"]
    runtime_env = _env(services["runtime"])
    assert TARGET_KEY not in runtime_env, (
        f"runtime holds {TARGET_KEY}; the target credential would have to "
        "leave the enforcement point for the product to function (FR-032)"
    )
    for name in ("analysis", "supervisor", "sandbox"):
        assert TARGET_KEY not in set(_env(services[name])), (
            f"{name} holds {TARGET_KEY}; target credential is not required "
            "to leave the enforcement point (FR-032)"
        )
    enforcement_env = _env(services["enforcement"])
    assert TARGET_KEY in enforcement_env
    assert enforcement_env.get(TARGET_ADDR_KEY) == "target:9000"
    assert FIXTURE_TOPOLOGY[TARGET_ADDR_KEY] == "target:9000"


def test_provider_credential_is_not_required_on_analysis_supervisor_or_sandbox() -> None:
    compose = _load_compose()
    for name in ("analysis", "supervisor", "sandbox"):
        keys = set(_env(compose["services"][name]))
        assert PROVIDER_KEY not in keys, (
            f"{name} holds {PROVIDER_KEY}; the provider plane is runtime "
            "only and is not required to leave it (FR-032)"
        )
        assert TARGET_KEY not in keys


def test_target_credential_is_not_required_on_runtime() -> None:
    compose = _load_compose()
    keys = set(_env(compose["services"]["runtime"]))
    assert TARGET_KEY not in keys
    assert PROVIDER_KEY in keys


def test_topology_identities_are_operator_local_not_a_vendor_saas() -> None:
    text = COMPOSE_FILE.read_text()
    for key, value in FIXTURE_TOPOLOGY.items():
        assert f"{key}: {value}" in text, (
            f"{key} is not the operator-local identity {value}; a vendor "
            "hostname here is target data required to leave (FR-032)"
        )
        for marker in VENDOR_MARKERS:
            assert marker not in value.lower(), (
                f"{key}={value!r} names a vendor marker {marker!r}"
            )
    compose = _load_compose()
    runtime_env = _env(compose["services"]["runtime"])
    for key, value in FIXTURE_TOPOLOGY.items():
        assert runtime_env[key] == value


def test_the_product_does_not_require_runtime_egress_to_function() -> None:
    """Plane B exists (T113) and is not a startup requirement.

    `src/runtime/main.py` is report+exit (OD-36). Installing `guarded()`
    there with a pin would make the product require an outbound destination
    to start. T058's transport is still unavailable; there is nothing to
    pin. FR-032 is that target data is not *required* to leave.
    """
    source = RUNTIME_MAIN.read_text()
    tree = ast.parse(source, filename=str(RUNTIME_MAIN))
    calls: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == "guarded":
                calls.append("guarded(")
            elif isinstance(func, ast.Attribute) and func.attr == "guarded":
                calls.append("egress.guarded(")
    assert calls == [], (
        "runtime main installs Plane B at startup; the product would "
        f"require egress to function: {calls}"
    )
    assert "def guarded(" not in source


def test_runtime_egress_guarded_is_not_weakened() -> None:
    """T113's Plane B stays. This file does not retarget its live arms."""
    egress = EGRESS.read_text()
    assert "def guarded(" in egress
    t113 = T113.read_text()
    assert "def test_a_connection_to_an_unpinned_destination_is_refused_on_the_wire" in t113
    assert "def test_a_connection_to_the_pinned_destination_is_let_through_to_the_network" in t113
    assert "def test_the_same_connection_is_not_refused_when_no_plane_is_installed" in t113


def test_held_credentials_construct_without_a_network() -> None:
    """The credentials component runs in-process. No socket, no SaaS."""
    held = hold(
        secret=Secret("t169-in-process-provider", name=PROVIDER_KEY),
        plane=PLANE_PROVIDER,
        holder=HOLDER_RUNTIME,
    )
    assert held.holder == HOLDER_RUNTIME
    assert held.plane == PLANE_PROVIDER
    assert "t169-in-process-provider" not in str(held)


def test_compose_declares_no_external_control_plane() -> None:
    compose = _load_compose()
    networks = compose.get("networks") or {}
    for name, spec in networks.items():
        if isinstance(spec, dict):
            assert spec.get("external") is not True, (
                f"network {name} is external; the bundle would require a "
                "control plane outside the operator's boundary (FR-032)"
            )
    for name, spec in compose["services"].items():
        image = str(spec.get("image") or "")
        for marker in VENDOR_MARKERS:
            assert marker not in image.lower(), (
                f"{name} image {image!r} names {marker!r}; that is a "
                "required leave of the operator's boundary"
            )
        extra = spec.get("extra_hosts") or []
        assert extra == [], f"{name} extra_hosts {extra} is a required egress"
