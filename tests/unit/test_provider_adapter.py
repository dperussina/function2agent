"""The seam that carries a driver's `ParsedTurn` into the loop's `ModelResponse`.

**What these arms are for.** Before this seam existed, `costs.py` priced nine
models and nothing called it: no code in `src/` built a `ModelResponse` from a
`ParsedTurn`, so `spend_usd` was the field's `0.0` default on every path and
FR-005's spend ceiling was compared against zero. The arms here assert the two
halves of the fix — that a priced turn arrives with the vendor's own arithmetic
on it, and that a turn nothing can price **stops** rather than arriving with a
zero.

The arm to read first is `test_the_only_things_in_src_that_build_a_model_response`.
Every other arm here can be satisfied by a correct adapter that some other
module quietly bypasses, and bypassing it is exactly how the zero got in.
"""

from __future__ import annotations

import ast
import datetime as dt
import pathlib

import pytest

from src.runtime.dispatch import ToolCall
from src.runtime.providers import costs
from src.runtime.providers.adapter import AdapterError, model_response
from src.runtime.providers.base import ParsedTurn, UnknownProviderError
from src.runtime.turn import LoopError, ModelResponse, UnpricedTurnError

#: Inside every entry's window: the table was read on 2026-08-05 and no entry
#: opens later. Stated as a constant because `price_usd` takes no default and
#: an arm that passed `dt.date.today()` would change answer on 2026-09-01.
TODAY = dt.date(2026, 8, 5)


def _parsed(provider: str = "anthropic", *, inputs: int = 0, outputs: int = 0,
            cost_usd: float | None = None,
            calls: tuple[ToolCall, ...] = ()) -> ParsedTurn:
    return ParsedTurn(
        provider=provider, text="hello", tool_calls=calls,
        provider_state=b"opaque", input_tokens=inputs, output_tokens=outputs,
        cost_usd=cost_usd)


# ---------------------------------------------------------------------------
# The three things pricing needs, one arm each.


def test_a_parsed_turn_arrives_priced_from_the_vendors_own_rates() -> None:
    """The whole point: token counts in, dollars out, from a sourced row.

    `claude-sonnet-5` is $2.00/Mtok in and $10.00/Mtok out inside the
    introductory window. One million of each is therefore $12.00 exactly, which
    is a figure a reader can check against the row without running anything.
    """
    response = model_response(
        _parsed(inputs=1_000_000, outputs=1_000_000),
        model="claude-sonnet-5", as_of=TODAY)

    assert response.spend_usd == pytest.approx(12.0)
    assert response.is_priced
    assert response.model == "claude-sonnet-5"
    assert response.tokens == 2_000_000
    assert (response.input_tokens, response.output_tokens) == (1_000_000, 1_000_000)
    # The opaque state rides across the seam untouched (FR-037): the adapter
    # translates the accounting and nothing else.
    assert response.provider_state == b"opaque"


def test_the_input_count_selects_the_band_and_not_only_the_product() -> None:
    """xAI's threshold re-rates **every** token, so the split drives the rate.

    `grok-4.5` is $2.00/$6.00 below 200k prompt tokens and $4.00/$12.00 at or
    above it, and the vendor's own note says the higher band applies to all
    tokens in the request rather than to the excess. So one token more of
    *prompt* doubles the price of the *output* too, and an adapter that took a
    single total and halved it would land in the wrong band as readily as at
    the wrong product.
    """
    below = model_response(
        _parsed("xai", inputs=199_999, outputs=1_000_000),
        model="grok-4.5", as_of=TODAY)
    at_threshold = model_response(
        _parsed("xai", inputs=200_000, outputs=1_000_000),
        model="grok-4.5", as_of=TODAY)

    assert below.spend_usd == pytest.approx(199_999 / 1e6 * 2.00 + 6.00)
    assert at_threshold.spend_usd == pytest.approx(200_000 / 1e6 * 4.00 + 12.00)
    # One extra prompt token roughly doubles the bill, because the output half
    # was re-rated too. That is the property a per-token multiplication with no
    # band selection cannot reproduce.
    assert at_threshold.spend_usd > 2 * below.spend_usd


def test_the_price_epoch_is_the_callers_and_not_the_processs_clock() -> None:
    """The same call, the same tokens, two rates either side of a stated date.

    The source states the introductory rate ending on 2026-08-31 and the
    standard rate taking effect the day after. A default of *today* would make
    a session's recorded cost depend on which machine asked.
    """
    introductory = model_response(
        _parsed(inputs=1_000_000, outputs=1_000_000),
        model="claude-sonnet-5", as_of=dt.date(2026, 8, 31))
    standard = model_response(
        _parsed(inputs=1_000_000, outputs=1_000_000),
        model="claude-sonnet-5", as_of=dt.date(2026, 9, 1))

    assert introductory.spend_usd == pytest.approx(12.0)
    assert standard.spend_usd == pytest.approx(18.0)


# ---------------------------------------------------------------------------
# Failing closed.


def test_an_openai_turn_fails_closed_rather_than_pricing_at_zero() -> None:
    """T063 reaching the wired path, on the provider `costs.UNPRICED` names.

    Neither model `wire_openai._LOW_EFFORT_MODELS` branches on is a priced row
    on that vendor's page, and the models it does price give a short-context
    and a long-context column with no stated threshold. So there is nothing to
    cite, the adapter does not catch the refusal, and the session stops. **This
    arm asserts the refusal, not a defect**: a spend ceiling that cannot be
    computed is an unenforceable ceiling, and stopping is the correct outcome.
    """
    for model in ("gpt-5-mini", "gpt-5-nano"):
        with pytest.raises(costs.MissingPriceError, match="no cost entry"):
            model_response(_parsed("openai", inputs=10, outputs=10),
                           model=model, as_of=TODAY)


def test_an_anthropic_alias_is_refused_because_the_table_prices_ids() -> None:
    """The alias is sourced and deliberately unpriced; the seam inherits that.

    `costs.UNPRICED["anthropic-aliases"]` records the reason — the vendor's own
    page calls an alias a pointer that resolves to a dated id, so a price
    attached to one is a price for whatever it resolves to next.
    """
    with pytest.raises(costs.MissingPriceError):
        model_response(_parsed(inputs=10, outputs=10),
                       model="claude-sonnet-4-5", as_of=TODAY)


def test_a_turn_that_cannot_say_which_model_ran_is_refused() -> None:
    with pytest.raises(AdapterError, match="no model identifier"):
        model_response(_parsed(inputs=10, outputs=10), model="", as_of=TODAY)


def test_a_provider_outside_the_declared_set_is_refused() -> None:
    with pytest.raises(UnknownProviderError):
        model_response(_parsed("bedrock", inputs=1, outputs=1),
                       model="claude-sonnet-5", as_of=TODAY)


def test_a_rate_outside_its_recorded_window_is_not_extrapolated() -> None:
    """A day before the pages were read is priced by nothing, and says so."""
    with pytest.raises(costs.MissingPriceError, match="no price in force"):
        model_response(_parsed(inputs=10, outputs=10),
                       model="claude-sonnet-5", as_of=dt.date(2020, 1, 1))


# ---------------------------------------------------------------------------
# The vendor's own figure.


def test_a_provider_reported_cost_is_used_in_place_of_the_table() -> None:
    """A vendor's own billing figure beats our transcription of its price page.

    No driver populates `ParsedTurn.cost_usd` today —
    `costs.UNPRICED["xai-cost-in-usd-ticks"]` records why the one provider that
    reports a cost deliberately does not — so this branch is exercised here
    rather than by a driver. It exists so that a driver which later *does*
    populate the field changes the answer instead of being silently ignored.
    """
    response = model_response(
        _parsed("xai", inputs=1_000_000, outputs=1_000_000, cost_usd=0.5),
        model="grok-4.5", as_of=TODAY)

    assert response.spend_usd == pytest.approx(0.5)


def test_a_provider_reported_cost_prices_a_model_the_table_does_not() -> None:
    """And it is a price, so it does not fail closed."""
    response = model_response(
        _parsed("openai", inputs=10, outputs=10, cost_usd=0.25),
        model="gpt-5-mini", as_of=TODAY)

    assert response.spend_usd == pytest.approx(0.25)


# ---------------------------------------------------------------------------
# `ModelResponse`'s own guards.


def test_an_unpriced_response_refuses_to_produce_a_spend_figure() -> None:
    response = ModelResponse(provider="anthropic", provider_state=None, text="")

    assert response.is_priced is False
    assert response.spend_usd is None
    with pytest.raises(UnpricedTurnError, match="counted at zero"):
        response.require_spend_usd()


def test_a_priced_zero_is_a_figure_and_not_an_absence() -> None:
    """The distinction the whole `float | None` type exists to carry."""
    response = ModelResponse(provider="anthropic", provider_state=None, text="",
                             spend_usd=0.0,
                             spend_provenance=costs.PROVENANCE_VENDOR)

    assert response.is_priced is True
    assert response.require_spend_usd() == 0.0


def test_a_half_supplied_token_split_is_refused() -> None:
    with pytest.raises(LoopError, match="half-supplied"):
        ModelResponse(provider="anthropic", provider_state=None, text="",
                      input_tokens=5, tokens=5)


def test_a_split_that_disagrees_with_the_total_is_refused() -> None:
    with pytest.raises(LoopError, match="sums to"):
        ModelResponse(provider="anthropic", provider_state=None, text="",
                      input_tokens=5, output_tokens=5, tokens=99)


def test_a_negative_spend_is_refused() -> None:
    with pytest.raises(LoopError, match="walked back under"):
        ModelResponse(provider="anthropic", provider_state=None, text="",
                      spend_usd=-0.01,
                      spend_provenance=costs.PROVENANCE_VENDOR)


# ---------------------------------------------------------------------------
# OD-27 — the provenance the seam carries, and the record it lands on.


#: An operator's own rate for the model this repository refuses to price, in
#: the shape OD-27 requires of that provider: both context columns and the
#: threshold between them.
_OPENAI_DECLARED = costs.OperatorPriceBook([costs.OperatorPrice(
    provider="openai", model="gpt-5-mini", display_name="GPT-5 mini",
    tiers=(costs.Rate(0.25, 2.00),
           costs.Rate(0.50, 4.00, min_input_tokens=128_000)),
    declared_by="platform-eng@example.invalid",
    declaration_ref="contracts/openai-2026-q3.md",
    declared_on="2026-08-01",
    scope="standard synchronous tier, uncached input, text",
)])


def test_a_declaration_reaches_the_seam_and_the_response_says_it_was_one() -> None:
    """OD-27's whole point, end to end.

    Before it, this provider's session could not run at all. After it, the
    session runs *and* the record says the figure came from a declaration —
    the second half being what stops a declared total reading as a sourced
    one months later, when the reader who has to check it goes looking for
    the row in `costs.PRICES` and does not find it.
    """
    response = model_response(
        _parsed("openai", inputs=1_000_000, outputs=0),
        model="gpt-5-mini", as_of=TODAY, operator_prices=_OPENAI_DECLARED)

    # A million prompt tokens is past the threshold the declaration states, so
    # this is the long-context column — the one a single-rate declaration
    # would have under-charged by half.
    assert response.spend_usd == pytest.approx(0.50)
    assert response.spend_provenance == costs.PROVENANCE_OPERATOR


def test_a_turn_priced_from_the_table_says_vendor_on_the_same_field() -> None:
    """The comparison arm. A seam hardcoding `operator` would satisfy the one
    above, and a seam hardcoding `vendor` would satisfy this one; only the two
    together say the field is carrying the lookup's answer."""
    response = model_response(
        _parsed("anthropic", inputs=1_000_000, outputs=0),
        model="claude-opus-5", as_of=TODAY,
        operator_prices=_OPENAI_DECLARED)

    assert response.spend_provenance == costs.PROVENANCE_VENDOR


def test_a_provider_reported_cost_is_the_vendors_and_not_the_operators() -> None:
    """The branch that does not consult the table at all.

    A vendor's server-side billing figure is the vendor's provenance even on a
    call where an operator declared a rate — nothing the operator wrote was
    read to produce it, and marking it `operator` would attribute a figure to
    somebody who did not supply it.
    """
    response = model_response(
        _parsed("openai", inputs=10, outputs=10, cost_usd=0.25),
        model="gpt-5-mini", as_of=TODAY, operator_prices=_OPENAI_DECLARED)

    assert response.spend_usd == pytest.approx(0.25)
    assert response.spend_provenance == costs.PROVENANCE_VENDOR


def test_the_seam_still_fails_closed_for_a_model_nobody_declared() -> None:
    """OD-27 is not a relaxation of T063: the book is an enumerated addition
    to the accepting set and everything outside it still refuses."""
    with pytest.raises(costs.MissingPriceError):
        model_response(_parsed("openai", inputs=10, outputs=10),
                       model="gpt-5-nano", as_of=TODAY,
                       operator_prices=_OPENAI_DECLARED)


def test_a_spend_figure_without_a_provenance_is_refused() -> None:
    """Present-or-absent together, on the record type itself.

    A figure with nothing beside it saying where its rate came from is a
    number a later reader cannot check and cannot tell from a sourced one.
    That is the `0.0` defect this type already closed, one field over.
    """
    with pytest.raises(LoopError, match="Both or neither"):
        ModelResponse(provider="anthropic", provider_state=None, text="",
                      spend_usd=1.0)


def test_a_provenance_without_a_figure_is_refused() -> None:
    """The other half, which is not the same mistake: it describes a price
    that was never computed."""
    with pytest.raises(LoopError, match="Both or neither"):
        ModelResponse(provider="anthropic", provider_state=None, text="",
                      spend_provenance=costs.PROVENANCE_VENDOR)


def test_an_undeclared_provenance_is_refused_rather_than_carried() -> None:
    """The vocabulary is closed and has one owner.

    A free string would be carried into a span and a journal payload that
    nothing downstream can interpret, and it would be carried *silently* —
    the reader who has to interpret it is not the author who wrote it.
    """
    with pytest.raises(LoopError, match="declared values are"):
        ModelResponse(provider="anthropic", provider_state=None, text="",
                      spend_usd=1.0, spend_provenance="contract")


# ---------------------------------------------------------------------------
# The structural arm.


#: **The enumerated accepting set**, never a complement. Stated as *these two
#: modules may build a `ModelResponse`* rather than *no other module may*: a
#: complement is a claim about every file that does not yet exist, and it reads
#: as satisfied right up until somebody adds the one that matters.
MAY_BUILD_A_MODEL_RESPONSE: frozenset[str] = frozenset({
    # Prices the turn from the table. The only thing in `src/` that does.
    "runtime/providers/adapter.py",
    # Rebuilds one from a committed journal payload; carries the spend the
    # original attempt recorded, or `None` where the payload predates it.
    "runtime/resume.py",
})


def test_the_only_things_in_src_that_build_a_model_response() -> None:
    """No third site, because a third site is how the zero would come back.

    Every other arm in this file describes a correct adapter. None of them can
    see a module that builds a `ModelResponse` around it — which is precisely
    what the code did before this seam existed, and the symptom was a spend
    ceiling compared against zero on every path with no test failing.
    """
    root = pathlib.Path(__file__).resolve().parents[2] / "src"
    found: set[str] = set()
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "ModelResponse"):
                found.add(path.relative_to(root).as_posix())

    assert found == MAY_BUILD_A_MODEL_RESPONSE, (
        f"`src/` builds a ModelResponse in {sorted(found)}; the declared set "
        f"is {sorted(MAY_BUILD_A_MODEL_RESPONSE)}. A site outside it either "
        "prices a turn without the table or leaves `spend_usd` at its "
        "unpriced default and lets the loop refuse a turn that should have "
        "been priced. Adding a site is a decision to record here, not a "
        "detail."
    )
