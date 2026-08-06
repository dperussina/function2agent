"""The seam between a driver's `ParsedTurn` and the loop's `ModelResponse`.

**This module exists because nothing joined those two types.** The driver layer
has produced `ParsedTurn` since `6a27a98` (T057/T058), carrying `input_tokens`
and `output_tokens` separately. The loop has consumed `ModelResponse` since
`ce64490` (T052), which had one undifferentiated `tokens` field and no model
identifier. `src/runtime/providers/costs.py` landed a sourced price table at
`1208e06` (T062/T063). **No code in `src/` built the second type from the
first** — the only `ModelResponse(` construction outside tests was
`resume.py`'s, rebuilding one from a journal payload — so the table reached
nothing, and FR-005's spend ceiling was compared against `0.0` on every path.
The gap fell between two completed tasks and no task named it.

**Pricing needs three things, and each is here for a separate reason.**

- *Which model.* `costs.PRICES` is keyed on `(provider, model)` with no prefix
  match and no family fallback, so the identifier has to be exact. It is
  supplied by the **caller** rather than read off the response, and that is a
  measurement rather than a preference: no response body in
  `tests/conformance/cassettes/` carries a model identifier at all. All four
  cassettes record it as metadata beside the payload — Anthropic's responses
  hold `content, id, role, type, usage`, Google's hold `candidates,
  usage_metadata` — so a driver reading `payload["model"]` would be asserting a
  wire contract nothing in this repository has observed, on four providers whose
  key would differ anyway. What *is* observed is that every `build_request` here
  writes the caller's model into the request. That string is what a price is
  owed against.
- *Input against output.* The two rates differ on every priced row, by between
  2x and 5x. This is the field `ModelResponse` could not supply, and inventing
  the split for a caller that has only a total is what this module refuses to
  do — see `model_response`.
- *Which price epoch.* `costs.PRICES` holds two Anthropic Sonnet 5 entries
  either side of a boundary the vendor states in words, so `as_of` is required
  and has no default. A default of *today* would make a session's cost depend
  on the clock of whichever process asked.

**The input count is load-bearing for the rate, not only for the
multiplication.** xAI's page states that a request whose prompt reaches 200k
tokens is billed at the higher rate *for every token in the request*, so
`costs.tier_for` selects the band from `input_tokens` before either figure is
multiplied. A total split down the middle would land in the wrong band as
readily as at the wrong product.

**This module fails closed, and OpenAI is where that shows.** `costs.UNPRICED`
records why neither model `wire_openai` branches on has a rate that could be
cited. `price_usd` therefore raises `MissingPriceError` for that provider, this
module does not catch it, and an OpenAI session stops rather than running with
an unenforceable spend ceiling. That is T063 working, not a defect here.
"""

from __future__ import annotations

import datetime as dt

from src.runtime.providers import costs
from src.runtime.providers.base import ParsedTurn, ProviderError, require_provider
from src.runtime.turn import ModelResponse


class AdapterError(ProviderError):
    """A parsed turn that cannot be carried into the loop as described."""


def model_response(
    parsed: ParsedTurn, *, model: str, as_of: dt.date
) -> ModelResponse:
    """Carry one parsed provider turn up to the loop, priced.

    `model` is the API identifier the request was made against — the same
    string the caller passed to `ProviderDriver.build_request`. It is required
    and may not be empty: an empty identifier matches no key in `costs.PRICES`
    and would arrive at `MissingPriceError` anyway, but it would arrive there
    describing a missing table entry rather than a caller that never said which
    model it called.

    **The provider's own cost figure wins where it exists.** `ParsedTurn.cost_usd`
    is populated only where the vendor reports a cost server-side, and a
    vendor's own billing figure is better evidence than this repository's
    transcription of that vendor's price page. No driver populates it today —
    `costs.UNPRICED["xai-cost-in-usd-ticks"]` records why the one provider that
    reports a cost deliberately does not — so this branch is exercised by test
    rather than by a driver. It is here rather than omitted because a field that
    can never do anything is a field a future driver would populate to no
    effect.

    Raises `costs.MissingPriceError` when nothing prices the model. Not caught:
    a spend ceiling that cannot be computed is FR-005 unenforceable, and the
    call is refused rather than counted at zero.
    """
    require_provider(parsed.provider)
    if not model:
        raise AdapterError(
            f"{parsed.provider}: no model identifier. A turn is priced against "
            "an exact `(provider, model)` key, so a response that cannot say "
            "which model produced it cannot be priced — and pricing it at zero "
            "is the FR-005 defect this seam exists to close. Pass the same "
            "identifier the request was built with."
        )
    inputs = parsed.input_tokens
    outputs = parsed.output_tokens
    if parsed.cost_usd is not None:
        spend = float(parsed.cost_usd)
    else:
        spend = costs.price_usd(
            provider=parsed.provider, model=model,
            input_tokens=inputs, output_tokens=outputs, as_of=as_of)
    return ModelResponse(
        provider=parsed.provider,
        provider_state=parsed.provider_state,
        text=parsed.text,
        tool_calls=parsed.tool_calls,
        model=model,
        spend_usd=spend,
        tokens=inputs + outputs,
        input_tokens=inputs,
        output_tokens=outputs,
    )
