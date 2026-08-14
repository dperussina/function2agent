"""T161 — two credential planes, a mix refused at construction (FR-036, FR-050)."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from src.contracts import config as cfg
from src.contracts.credentials import (
    ALLOWED_HOLDERS,
    HOLDER_ANALYSIS,
    HOLDER_ENFORCEMENT,
    HOLDER_EXECUTION,
    HOLDER_RUNTIME,
    HOLDER_TICK,
    NEVER_HOLD,
    PLANE_PROVIDER,
    PLANE_TARGET,
    PROVIDER_KEY,
    TARGET_KEY,
    HeldCredential,
    HolderRefusedError,
    PlaneMixError,
    hold,
)
from src.contracts.secret import Secret

REPO = Path(__file__).resolve().parents[2]
PLAINTEXT = "sk-test-provider-credential-t161"

_RUNTIME_ENV = {
    "SESSION_CEILING_SPEND_USD": "5.00",
    "SESSION_CEILING_TOKENS": "200000",
    "SESSION_CEILING_WALL_CLOCK_SECONDS": "900",
    "SESSION_CEILING_TURNS": "40",
    "TOOL_RESULT_BOUND_TOKENS": "8000",
    "MODEL_CONTEXT_WINDOW_TOKENS": "200000",
    "RESULT_RETENTION_MAX_BYTES": "64MiB",
    "MODEL_PROVIDER": "anthropic",
    "MODEL_ID": "claude-sonnet-4-5-20250929",
    "MODEL_PRICES_OPERATOR": "none",
    "F2A_PROVIDER_CREDENTIAL": PLAINTEXT,
    "REPORTING_WINDOW_SECONDS": "3600",
    "F2A_STATE_DIR": "/var/lib/f2a",
    "F2A_TENANT_ID": "t-1",
    "F2A_DEPLOYMENT_ID": "d-1",
}


def _provider() -> Secret:
    return Secret(PLAINTEXT, name=PROVIDER_KEY)


def _target() -> Secret:
    return Secret("target-plane-value", name=TARGET_KEY)


def test_the_runtime_may_hold_the_provider_plane() -> None:
    held = hold(secret=_provider(), plane=PLANE_PROVIDER, holder=HOLDER_RUNTIME)
    assert held.plane == PLANE_PROVIDER
    assert held.holder == HOLDER_RUNTIME
    assert held.name == PROVIDER_KEY
    assert held.fingerprint() == _provider().fingerprint()
    assert PLAINTEXT not in str(held)
    assert PLAINTEXT not in repr(held)


def test_the_enforcement_point_may_hold_the_target_plane() -> None:
    held = hold(secret=_target(), plane=PLANE_TARGET, holder=HOLDER_ENFORCEMENT)
    assert held.plane == PLANE_TARGET
    assert held.holder == HOLDER_ENFORCEMENT
    assert held.name == TARGET_KEY


def test_a_target_named_secret_is_refused_as_the_runtime_provider_credential() -> None:
    with pytest.raises(PlaneMixError, match="Mixing the planes"):
        hold(secret=_target(), plane=PLANE_PROVIDER, holder=HOLDER_RUNTIME)


def test_a_provider_named_secret_is_refused_as_the_target_plane() -> None:
    with pytest.raises(PlaneMixError, match="Mixing the planes"):
        hold(secret=_provider(), plane=PLANE_TARGET, holder=HOLDER_ENFORCEMENT)


def test_analysis_execution_and_tick_may_not_hold_either_plane() -> None:
    for holder in (HOLDER_ANALYSIS, HOLDER_EXECUTION, HOLDER_TICK):
        with pytest.raises(HolderRefusedError, match="may not hold a credential plane"):
            hold(secret=_provider(), plane=PLANE_PROVIDER, holder=holder)


def test_the_enforcement_point_may_not_hold_the_provider_credential() -> None:
    with pytest.raises(HolderRefusedError, match="may not hold the provider plane"):
        hold(secret=_provider(), plane=PLANE_PROVIDER, holder=HOLDER_ENFORCEMENT)


def test_a_session_capability_is_not_a_credential_plane() -> None:
    with pytest.raises(PlaneMixError, match="capability is not either"):
        hold(secret=_provider(), plane="capability", holder=HOLDER_RUNTIME)


def test_held_credential_has_no_reveal() -> None:
    assert "reveal" not in HeldCredential.__dict__


def test_the_runtime_provider_credential_is_a_secret_not_a_str() -> None:
    loaded = cfg.load(cfg.RUNTIME_KEYS, _RUNTIME_ENV)
    credential = loaded[PROVIDER_KEY]
    assert isinstance(credential, Secret)
    assert credential.name == PROVIDER_KEY
    assert PLAINTEXT not in str(credential)


def test_the_declared_provider_key_is_one_name_not_a_vendor_env() -> None:
    names = {key.name for key in cfg.RUNTIME_KEYS}
    assert PROVIDER_KEY in names
    assert TARGET_KEY not in names
    assert "ANTHROPIC_API_KEY" not in names
    assert "OPENAI_API_KEY" not in names
    key = next(k for k in cfg.RUNTIME_KEYS if k.name == PROVIDER_KEY)
    assert key.kind is cfg.Kind.SECRET
    assert key.default is None
    assert key.no_default_reason is None
    assert key.requirement == "FR-036"


def test_credentials_module_does_not_declare_vendor_env_names() -> None:
    """Docstrings may name the forbidden keys; declared identifiers may not."""
    tree = ast.parse(
        (REPO / "src/contracts/credentials.py").read_text(),
        filename="credentials.py",
    )
    constants = [
        node.value for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
        and node.value in {"ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GOOGLE_API_KEY"}
    ]
    assert constants == []
    assert PROVIDER_KEY == "F2A_PROVIDER_CREDENTIAL"
    assert TARGET_KEY == "F2A_TARGET_CREDENTIAL"
    assert ALLOWED_HOLDERS == {
        (PLANE_PROVIDER, HOLDER_RUNTIME),
        (PLANE_TARGET, HOLDER_ENFORCEMENT),
    }
    assert {HOLDER_ANALYSIS, HOLDER_EXECUTION, HOLDER_TICK} <= NEVER_HOLD
