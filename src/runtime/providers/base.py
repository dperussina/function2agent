"""T058 — the one interface every provider driver implements.

**The interface is deliberately two-part, and the seam is where the SDK starts.**

`build_request` and `parse_response` are pure functions over mappings. They import
no vendor SDK, they touch no network, and they are the whole of what
`tests/conformance/` replays against a cassette. `call` is the transport: it
imports the vendor's own package and makes the request. Nothing offline exercises
it.

That is not a convenience. [Finding 016](../../../specs/001-discovery-validation/findings/016-provider-sdk-roundtrip.md)
drove all four vendor SDKs directly and found the transport half **already
correct on every provider** — each SDK round-tripped its own opaque field
byte-identically. What it found broken, historically, was an *adapter* rebuilding
a request from the fields it recognised: ADK's LiteLLM adapter referenced xAI's
`encrypted_content` zero times. So the half that needs a fixture is the half that
translates, and that is the half made pure.

**`ModelCapabilities` exists because a driver cannot be one function per vendor.**
Finding 016 result 9 measured `claude-sonnet-5` rejecting the extended-thinking
request shape `claude-sonnet-4-5` requires, with an HTTP 400 naming the
replacement. The request shape is model-specific *within a single vendor*, so the
per-model branch is a structural requirement rather than a nicety, and it is a
maintenance surface that tracks vendor releases.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from src.runtime.dispatch import ToolCall
from src.runtime.providers.schema import ToolSchema

#: The four providers **SC-010** names. Not an open registry: a provider with no
#: driver is an error at configuration time rather than a `KeyError` at the first
#: model call, and the set is what `state.py` keys opaque state against.
ANTHROPIC = "anthropic"
OPENAI = "openai"
GOOGLE = "google"
XAI = "xai"

PROVIDERS: tuple[str, ...] = (ANTHROPIC, OPENAI, GOOGLE, XAI)


class ProviderError(RuntimeError):
    """A provider interaction that cannot be performed as described."""


class UnknownProviderError(ProviderError):
    """A provider name outside `PROVIDERS`."""


class TransportUnavailableError(ProviderError):
    """The vendor SDK this driver drives is not installed.

    A distinct type because the remedy is a dependency pin and not a code
    change, and because a caller replaying cassettes must be able to tell this
    apart from a provider that refused.
    """


@dataclass(frozen=True)
class ModelCapabilities:
    """What one *model* — not one vendor — accepts and returns.

    `thinking_request` is merged into the request body verbatim. It is a mapping
    rather than a flag because finding 016 measured two incompatible shapes
    inside one vendor: `{"thinking": {"type": "enabled", "budget_tokens": N}}`
    against `{"thinking": {"type": "adaptive"}, "output_config": {...}}`, with
    the second model returning HTTP 400 on the first shape.

    `opt_in` is the separate matter of *asking* for opaque state. Two providers
    return none unless the request says so — OpenAI needs
    `include=["reasoning.encrypted_content"]` with `store=False`, xAI needs
    `use_encrypted_content=True` — and a driver that forgets it produces a
    session with no opaque state at all and no error to say so.

    `emits_opaque_state` is **not** a promise that state arrives. Finding 016
    result 8 measured `claude-sonnet-5` under adaptive thinking emitting it on
    2 of 6 runs. It records that this model *can*, which is what makes an
    absence worth reporting rather than expected.
    """

    provider: str
    model: str
    opaque_field: str
    thinking_request: Mapping[str, Any] = field(default_factory=dict)
    opt_in: Mapping[str, Any] = field(default_factory=dict)
    emits_opaque_state: bool = True
    #: Free text naming where this row came from. `derived` rows are the ones a
    #: reader must not cite as measurement.
    source: str = "derived"


#: The three roles a conversation entry can hold. `assistant` is the one that
#: matters here: it is the entry the opaque state was taken off and the entry it
#: has to go back onto, and every driver's recorded paths are relative to it.
ROLE_USER = "user"
ROLE_ASSISTANT = "assistant"
ROLE_TOOL = "tool"


@dataclass(frozen=True)
class WireTurn:
    """One conversation entry, already in a provider's own shape.

    **The driver does not accumulate the conversation; the caller does.** What
    the driver owns is the translation of one turn in each direction, and
    keeping accumulation out of it is what lets `build_request` be a pure
    function a cassette can drive.

    `payload` is a mapping on three providers and a *list* on OpenAI, whose
    Responses API splices an assistant turn's output items into the flat `input`
    array rather than nesting them under a message. Modelling that difference
    away would mean picking one shape and translating at the point a
    mistranslation is invisible.
    """

    role: str
    payload: Any

    def __post_init__(self) -> None:
        if self.role not in (ROLE_USER, ROLE_ASSISTANT, ROLE_TOOL):
            raise ProviderError(f"{self.role!r} is not a conversation role")


@dataclass(frozen=True)
class ParsedTurn:
    """One provider response, translated but not interpreted.

    `provider_state` is the packed opaque carrier from `state.py`, or `None`
    when the provider emitted none. `None` and `b""` are different facts and
    stay different all the way to the journal's nullable column.
    """

    provider: str
    text: str
    tool_calls: tuple[ToolCall, ...]
    provider_state: bytes | None
    #: The assistant entry the caller appends to the conversation, and the entry
    #: `provider_state`'s recorded paths are relative to. Carried on the parse
    #: result rather than rebuilt by the caller: rebuilding an assistant turn
    #: from the fields an adapter recognised is the exact defect finding 016
    #: exists to catch.
    assistant: WireTurn | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    #: Populated only where the provider itself reports a cost. xAI does; the
    #: other three report tokens and the conversion needs T062's price table,
    #: which does not exist. `None` here means *not reported*, never zero.
    cost_usd: float | None = None


class ProviderDriver(ABC):
    """One vendor, behind one interface.

    Subclasses implement the three pure methods. `call` has a default that
    raises, because a driver whose transport is unwritten should say so at the
    call site rather than at import.
    """

    #: The member of `PROVIDERS` this driver serves.
    provider: str = ""

    #: The vendor package `call` imports, named here so a missing dependency can
    #: be reported without importing anything.
    sdk_module: str = ""

    @abstractmethod
    def capabilities(self, model: str) -> ModelCapabilities:
        """The per-model branch finding 016 result 9 makes mandatory."""

    @abstractmethod
    def build_request(
        self,
        *,
        model: str,
        system: str,
        turns: Sequence[WireTurn],
        tools: Sequence[ToolSchema],
        provider_state: bytes | None = None,
    ) -> dict[str, Any]:
        """The request body, with the opaque state re-attached where it sat.

        `turns` is the conversation so far in this provider's own wire shape —
        the driver does not own conversation accumulation, the caller does. What
        the driver owns is that `provider_state`, if given, is unpacked and put
        back onto the **last assistant entry**, at the positions it was taken
        from, byte for byte.
        """

    @abstractmethod
    def parse_response(self, payload: Mapping[str, Any]) -> ParsedTurn:
        """The response body, translated into `ParsedTurn`."""

    def call(self, request: Mapping[str, Any]) -> Mapping[str, Any]:  # pragma: no cover - transport
        """The vendor SDK. **Not exercised by any cassette.**"""
        raise TransportUnavailableError(
            f"{self.provider}: the transport half of this driver requires "
            f"{self.sdk_module!r}, which is not a pinned dependency of this "
            "project. FR-021 forbids resolving it at run time, so adding it is "
            "a lock-file change and an image rebuild rather than an install. "
            "The pure half — build_request and parse_response — needs no SDK "
            "and is what tests/conformance/ replays."
        )

    def require_sdk(self) -> Any:  # pragma: no cover - transport
        """Import the vendor package or say precisely what is missing."""
        import importlib

        try:
            return importlib.import_module(self.sdk_module)
        except ImportError as exc:
            raise TransportUnavailableError(
                f"{self.provider}: {self.sdk_module!r} is not installed. "
                f"Pin it in pyproject.toml and requirements.lock; do not "
                f"install it at run time (FR-021)."
            ) from exc


def require_provider(provider: str) -> str:
    """Refuse a provider name outside the declared set.

    Refused rather than defaulted. A typo that fell through to a default would
    key opaque state under a provider that never produced it, which is the one
    thing T-02 forbids by name.
    """
    if provider not in PROVIDERS:
        raise UnknownProviderError(
            f"{provider!r} is not one of {', '.join(PROVIDERS)}. A provider "
            "with no driver is a configuration error, not a runtime surprise."
        )
    return provider
