"""T163 — provider selection by configuration (FR-037).

The core path calls this module so it never names a vendor. `driver_for`
stays the registry; this is the configuration → driver function. Unknown
providers are `UnknownProviderError` via `require_provider`. Vendor SDKs
are not imported here; T058's `call` still raises `TransportUnavailableError`
when they are absent. Opaque-state merge-across-providers is T059's.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.contracts.config import Config
from src.runtime.providers import driver_for
from src.runtime.providers.base import ProviderDriver, require_provider


@dataclass(frozen=True)
class SelectedProvider:
    """A driver and the model id configuration selected, or a startup refusal."""

    driver: ProviderDriver
    provider: str
    model: str


def select(config: Config) -> SelectedProvider:
    """Resolve `MODEL_PROVIDER` / `MODEL_ID` to a driver, or refuse.

    The core path names no vendor. A typo is a configuration error at
    selection, not a first-turn surprise.
    """
    provider = require_provider(str(config["MODEL_PROVIDER"]))
    model = str(config["MODEL_ID"])
    return SelectedProvider(
        driver=driver_for(provider),
        provider=provider,
        model=model,
    )
