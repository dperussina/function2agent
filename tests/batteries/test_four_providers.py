"""T164 — SC-010: the User Story 1 path against four independent providers.

**Criterion**: SC-010 — *the full User Story 1 battery completes against at
least four independent model providers with configuration as the only
difference between runs.* Under OD-16 this is a test v1 must pass rather than
a result it inherits.

## What this file is, and what it is not

**Do.** The same first-turn path is selectable for every member of
`PROVIDERS` with `MODEL_PROVIDER` / `MODEL_ID` as the only knobs. One battery
body, four configs. A provider-specific branch in this file or in the core
path (`loop.py`, `runner.py`, `turn.py`) is refused. Vendor names live in
`select` / `wire_*` / the closed `PROVIDERS` tuple — not here as string
constants, and not as an `if` on a vendor.

**Do not complete a live first verified answer.** T058 is PARTIAL:
`ProviderDriver.call` raises `TransportUnavailableError` because no vendor
SDK is in `requirements.lock`, and FR-021 forbids resolving one at run time.
That residual is asserted **identically** for all four; none is skipped, and
a green run on one provider with the other three skipped would not be this
criterion. Adding the SDKs and exercising `call` live is still owed — not
discharged here, and not discharged by inventing a network path.

**Do not rebuild the Phase 3 cassette suite.** `tests/conformance/` already
replays `build_request` / `parse_response` over synthetic payloads. T170 owns
cassette-backed tests *over the core path*. This file does not import that
harness and does not tick T170.

**Do not stand up T215.** No `Registry`, no `build_server`, no serve loop.
T117's SC-001 harness still records that no model provider is in *its* path;
this battery is the provider-selection half of US1, not a second copy of
that answering step.

## Why the transport residual is the claim rather than a skip

A skip on "SDK not installed" would make SC-010 inherit a hole: three arms
skip, one passes on a machine that happened to have a package, and the
criterion reads green. The four arms here must agree. Today they agree that
the first turn's translation runs and the first turn's transport does not.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from src.contracts.config import Config
from src.runtime.providers.base import (
    ANTHROPIC,
    GOOGLE,
    OPENAI,
    PROVIDERS,
    TransportUnavailableError,
    XAI,
)
from src.runtime.providers.schema import ToolSchema
from src.runtime.providers.select import SelectedProvider, select
from tests.batteries.evidence import record_evidence

REPO = Path(__file__).resolve().parents[2]
THIS = Path(__file__).resolve()
CORE = (
    REPO / "src/runtime/loop.py",
    REPO / "src/runtime/runner.py",
    REPO / "src/runtime/turn.py",
)

#: Configuration, not a code branch. Each id is the priced entry for that
#: provider where `costs.PRICES` has one, and the driver-known id where the
#: table records the provider as unpriced on purpose (OpenAI — `UNPRICED`).
#: Keys are the closed `PROVIDERS` members; a fifth name is a missing-key
#: failure rather than a skipped arm.
MODEL_BY_PROVIDER: dict[str, str] = {
    ANTHROPIC: "claude-sonnet-4-5-20250929",
    OPENAI: "gpt-5-mini",
    GOOGLE: "gemini-3-flash-preview",
    XAI: "grok-4.5",
}

#: SC-010's variable is configuration, not a code branch. The AST walk below
#: refuses a vendor name as a string constant in this file; this binding is
#: the plant site that makes that refusal load-bearing.
CONFIGURATION_ONLY = True

#: One US1-shaped tool, identical across the four runs. The driver translates
#: it; this file does not.
STOCK_TOOL = ToolSchema(
    name="get_stock",
    description="Return on-hand quantity for a part id.",
    parameters={
        "type": "object",
        "properties": {"part_id": {"type": "string"}},
        "required": ["part_id"],
    },
)

SYSTEM = "answer from the served surface"


def _config(provider: str) -> Config:
    """The only knobs this battery turns."""
    return Config(values={
        "MODEL_PROVIDER": provider,
        "MODEL_ID": MODEL_BY_PROVIDER[provider],
    })


def _select(provider: str) -> SelectedProvider:
    return select(_config(provider))


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return names


def _vendor_constants(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and node.value in PROVIDERS:
            found.append(repr(node.value))
    return found


# ---------------------------------------------------------------------------
# The four runs. One body.


@pytest.mark.parametrize("provider", PROVIDERS)
def test_the_us1_path_is_selectable_for_every_provider(provider: str) -> None:
    """FR-037: selected by configuration. The core path names no vendor."""
    selected = _select(provider)
    assert isinstance(selected, SelectedProvider)
    assert selected.provider == provider
    assert selected.model == MODEL_BY_PROVIDER[provider]
    assert selected.driver.provider == provider


@pytest.mark.parametrize("provider", PROVIDERS)
def test_the_first_turn_transport_is_unavailable(provider: str) -> None:
    """The honest first-answer residual, identical for every provider.

    Translation (`build_request`) runs. Transport (`call`) raises
    `TransportUnavailableError` naming FR-021 and the missing pin. A skip
    here would let SC-010 inherit a hole; an arm that completed a live call
    would mean T058's residual had closed without this battery noticing.
    """
    selected = _select(provider)
    request = selected.driver.build_request(
        model=selected.model,
        system=SYSTEM,
        turns=(),
        tools=(STOCK_TOOL,),
    )
    assert request["model"] == selected.model
    with pytest.raises(TransportUnavailableError, match="FR-021") as caught:
        selected.driver.call(request)
    assert "not a pinned dependency" in str(caught.value)
    assert selected.driver.sdk_module in str(caught.value)


def test_the_transport_residual_is_identical_across_providers() -> None:
    """Do not skip three and pass one. Four arms, one exception type."""
    kinds: list[type] = []
    for provider in PROVIDERS:
        selected = _select(provider)
        try:
            selected.driver.call({"model": selected.model})
        except TransportUnavailableError as exc:
            kinds.append(type(exc))
        else:
            raise AssertionError(
                f"{provider} completed a live call; T058's residual is gone"
            )
    assert len(kinds) == len(PROVIDERS)
    assert len(set(kinds)) == 1
    assert kinds[0] is TransportUnavailableError


def test_every_closed_provider_has_a_configured_model() -> None:
    """A missing key is a failure, not a skipped arm."""
    assert set(MODEL_BY_PROVIDER) == set(PROVIDERS)


def test_the_runs_differ_only_in_the_two_configuration_keys() -> None:
    """MODEL_PROVIDER and the matching MODEL_ID. Nothing else."""
    assert CONFIGURATION_ONLY is True
    runs = [_config(provider).values for provider in PROVIDERS]
    expected_keys = frozenset({"MODEL_PROVIDER", "MODEL_ID"})
    assert [frozenset(run) for run in runs] == [expected_keys] * len(PROVIDERS)
    named = [run["MODEL_PROVIDER"] for run in runs]
    assert named == list(PROVIDERS)
    assert len(set(named)) == len(PROVIDERS)


def test_sc010_requires_four_independent_providers() -> None:
    assert len(PROVIDERS) == 4, (
        "SC-010 is four independent providers, not a subset"
    )
    assert len(set(PROVIDERS)) == len(PROVIDERS)


# ---------------------------------------------------------------------------
# Structural: no vendor in the battery body or the core path.


def test_the_battery_and_core_path_name_no_vendor() -> None:
    """Vendor names as string constants belong in select / wire_* / PROVIDERS.

    Exact equality, not a substring: a docstring that mentions the residual
    is not a branch.
    """
    offenders: list[str] = []
    for path in (THIS, *CORE):
        found = _vendor_constants(path)
        if found:
            offenders.append(
                f"{path.relative_to(REPO)} names {', '.join(found)}"
            )
    assert offenders == [], (
        "a vendor named here is a provider-specific branch; the core path "
        "goes through select.py\n  " + "\n  ".join(offenders)
    )


def test_the_battery_does_not_import_a_wire_driver_or_vendor_sdk() -> None:
    imported = _imported_modules(THIS)
    assert all("wire_" not in name for name in imported), imported
    assert not any(name.startswith("tests.conformance") for name in imported), (
        "T170 owns cassette-backed tests over the core path; this battery "
        "is not a second cassette suite"
    )
    sdk_modules = {_select(provider).driver.sdk_module for provider in PROVIDERS}
    overlap = imported & (set(PROVIDERS) | sdk_modules)
    assert not overlap, overlap


def test_the_battery_does_not_skip_a_provider() -> None:
    """A skip is how SC-010 would inherit a hole. Refused in the AST."""
    tree = ast.parse(THIS.read_text(), filename=str(THIS))
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in {
            "skip", "skipIf", "importorskip", "xfail",
        }:
            raise AssertionError(
                "this battery skips or xfails; SC-010 cannot inherit a skip"
            )


def test_the_residual_is_recorded() -> None:
    record_evidence("sc010-four-providers", {
        "criterion": "SC-010",
        "task": "T164",
        "providers": list(PROVIDERS),
        "models": {provider: MODEL_BY_PROVIDER[provider] for provider in PROVIDERS},
        "residual": (
            "ProviderDriver.call raises TransportUnavailableError for every "
            "member of PROVIDERS; vendor SDKs are not in requirements.lock "
            "(T058 PARTIAL, FR-021). A live first verified answer is not "
            "what a green run of this file claims."
        ),
        "what_this_establishes": [
            "The US1 path is selectable for all four providers with "
            "MODEL_PROVIDER / MODEL_ID as the only difference.",
            "The first-turn translation (build_request) runs for all four.",
            "The core path and this battery name no vendor as a string constant.",
        ],
        "what_this_does_not": [
            "A live first verified answer. Transport is unexercised offline.",
            "Cassette-backed tests over the core path (T170).",
            "T215's Registry / build_server / serve loop.",
        ],
    })
