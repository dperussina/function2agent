"""T163 — provider selection by configuration; the core path names no vendor."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from src.contracts.config import Config
from src.runtime.providers import PROVIDERS, driver_for
from src.runtime.providers.base import ProviderDriver, UnknownProviderError
from src.runtime.providers.select import SelectedProvider, select

REPO = Path(__file__).resolve().parents[2]
SELECT = REPO / "src/runtime/providers/select.py"
CORE = (
    REPO / "src/runtime/loop.py",
    REPO / "src/runtime/runner.py",
    REPO / "src/runtime/dispatch.py",
    REPO / "src/runtime/turn.py",
    REPO / "src/runtime/serving.py",
    REPO / "src/runtime/main.py",
)
VENDORS = frozenset({"anthropic", "openai", "google", "xai"})


def _config(provider: str = "anthropic",
            model: str = "claude-sonnet-4-5-20250929") -> Config:
    return Config(values={"MODEL_PROVIDER": provider, "MODEL_ID": model})


def test_select_calls_driver_for_and_does_not_duplicate_the_registry() -> None:
    selected = select(_config())
    assert isinstance(selected, SelectedProvider)
    assert isinstance(selected.driver, ProviderDriver)
    assert selected.provider == "anthropic"
    assert selected.model == "claude-sonnet-4-5-20250929"
    assert selected.driver is driver_for("anthropic")


def test_an_unknown_provider_is_refused_at_selection() -> None:
    with pytest.raises(UnknownProviderError, match="not one of"):
        select(_config(provider="not-a-vendor"))


def test_select_does_not_import_a_wire_driver() -> None:
    tree = ast.parse(SELECT.read_text(), filename=str(SELECT))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
    assert all("wire_" not in name for name in imported), imported
    assert all(
        name not in {"anthropic", "openai", "google.genai", "xai_sdk"}
        for name in imported
    ), imported


def test_select_names_no_vendor_constant() -> None:
    tree = ast.parse(SELECT.read_text(), filename=str(SELECT))
    named = [
        node.value for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and node.value in VENDORS
    ]
    assert named == []


def test_the_core_path_does_not_import_a_wire_driver_or_name_a_vendor() -> None:
    for path in CORE:
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert "wire_" not in node.module, path
            if isinstance(node, ast.Constant) and node.value in VENDORS:
                raise AssertionError(
                    f"{path.relative_to(REPO)} names {node.value!r} as a "
                    "string constant; the core path goes through select.py"
                )


def test_the_registry_is_still_the_closed_providers_set() -> None:
    assert PROVIDERS == ("anthropic", "openai", "google", "xai")
    for name in PROVIDERS:
        assert driver_for(name) is driver_for(name)
