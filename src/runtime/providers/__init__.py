"""Capability 5 — provider transport and tool-schema translation (T057–T061).

Four modules and four drivers, and the split between them is the one thing worth
reading before the code.

`schema.py` (T057) is the **tool-shape** translation: one internal tool call, four
wire formats, both directions. `state.py` (T059) is the **opaque-state** carrier:
provider-opaque reasoning state as bytes we never look inside. `base.py` is the one
interface every driver implements. `wire_*.py` are the drivers themselves (T058),
one per vendor, each split into a pure half that a cassette can replay and a
transport half that touches the vendor's SDK.

**Why the driver is split in two, and what that costs.** The pure half —
`build_request` and `parse_response` — is a function over dictionaries and imports
nothing. It is the half [finding 016](../../../specs/001-discovery-validation/findings/016-provider-sdk-roundtrip.md)
says is ours: *"the driver's job is to not lose it rather than to reconstruct it."*
The transport half is a lazily-imported SDK call. Everything in
`tests/conformance/` exercises the first and **nothing exercises the second**, which
is stated in `tests/conformance/cassettes/README.md` rather than left for a reader
to discover from a green run.

**Why the driver modules are named `wire_*` and not after their vendors.** A module
at `src/runtime/providers/anthropic.py` that does `import anthropic` resolves to the
top-level package under Python 3's absolute imports and works — until something
inside the package walks `sys.modules` by basename, or a tool reads the tree by
filename. The shared basename buys nothing and costs a class of failure that is
hard to see, so the files say what they hold instead.

**OD-16**: no `litellm`, and the reason is licensing rather than quality. Nothing
here may take a dependency that vendors it.
"""

from __future__ import annotations

from src.runtime.providers.base import (
    ANTHROPIC,
    GOOGLE,
    OPENAI,
    PROVIDERS,
    ROLE_ASSISTANT,
    ROLE_TOOL,
    ROLE_USER,
    XAI,
    ModelCapabilities,
    ParsedTurn,
    ProviderDriver,
    ProviderError,
    TransportUnavailableError,
    UnknownProviderError,
    WireTurn,
    require_provider,
)
from src.runtime.providers.wire_anthropic import AnthropicDriver
from src.runtime.providers.wire_google import GoogleDriver
from src.runtime.providers.wire_openai import OpenAIDriver
from src.runtime.providers.wire_xai import XaiDriver

#: One instance per provider. The drivers hold no per-session state — every
#: method is a function of its arguments — so a shared instance is a fact about
#: them rather than an optimisation, and a driver that grew a field would have
#: to change this line to say so.
_DRIVERS: dict[str, ProviderDriver] = {
    ANTHROPIC: AnthropicDriver(),
    OPENAI: OpenAIDriver(),
    GOOGLE: GoogleDriver(),
    XAI: XaiDriver(),
}


def driver_for(provider: str) -> ProviderDriver:
    """The driver for one provider, or a refusal naming the set.

    The registry is closed. An open one would let a configuration name a
    provider with no driver and fail at the first model call, several minutes
    and one reservation into a session, rather than at startup where FR-033
    puts every other configuration error.
    """
    require_provider(provider)
    return _DRIVERS[provider]


__all__ = [
    "ANTHROPIC",
    "AnthropicDriver",
    "GOOGLE",
    "GoogleDriver",
    "ModelCapabilities",
    "OPENAI",
    "OpenAIDriver",
    "PROVIDERS",
    "ParsedTurn",
    "ProviderDriver",
    "ProviderError",
    "ROLE_ASSISTANT",
    "ROLE_TOOL",
    "ROLE_USER",
    "TransportUnavailableError",
    "UnknownProviderError",
    "WireTurn",
    "XAI",
    "XaiDriver",
    "driver_for",
    "require_provider",
]
