"""T062, T063 — the cost table's sources, its shape, and its refusals.

Three families of assertion, and the second is the one this file exists for.

**The table's own shape.** Every entry states a source a reader can open and a
date it was read on. A price recalled from memory is an invented default wearing
a source's clothes, and it is *worse* than an absent entry, because the absent
entry fails closed by construction and the recalled one silently makes the
spend ceiling wrong.

**The accepting set is enumerated.** `price_usd` answers only for a
`(provider, model)` pair the table holds, and every near miss — an alias, a
dated variant of a dateless id, a family prefix, a case difference — lands in
the refusing branch. Stated this way round on purpose: a rule of the form
*"anything not on a deny list is priceable"* fails open on the first model
nobody anticipated, which is exactly the model nobody priced.

**No uniformity is assumed across providers, because the sources do not offer
any.** Three structurally different schedules are in the table at once and the
tests below read all three: Anthropic prices a flat rate per model but schedules
a *dated change* for one of them; xAI prices in two *prompt-length tiers* with a
stated threshold; Google prices flat but per modality and per service tier. A
later contributor flattening this to one rate per model breaks
`test_the_table_holds_three_structurally_different_schedules`.
"""

from __future__ import annotations

import datetime as dt

import pytest

from src.runtime.providers import costs
from src.runtime.providers.base import PROVIDERS
from src.runtime.providers.costs import (
    DERIVABLE_RESERVATION_FIELDS,
    PRICES,
    MissingPriceError,
    PriceEntry,
    Rate,
    priced_models,
    price_usd,
    reservation_spend_usd,
)

DAY = dt.date(2026, 8, 5)


# ---------------------------------------------------------------------------
# The table's own shape: a source per entry, and no entry without one.


def test_the_table_is_not_empty_so_nothing_below_passes_over_nothing() -> None:
    """The vacuity floor. Every assertion in this file iterates the table."""
    assert len(priced_models()) >= 8, (
        f"the priced set is {sorted(priced_models())}; the assertions in this "
        "file iterate it, and over an empty table they all pass"
    )


@pytest.mark.parametrize("key", sorted(PRICES), ids=lambda k: f"{k[0]}/{k[1]}")
def test_every_entry_states_a_source_a_reader_can_open(key) -> None:
    for entry in PRICES[key]:
        assert entry.source.startswith("https://"), (
            f"{entry.provider}/{entry.model}: the source is {entry.source!r}. "
            "A price with no address is a price nobody can check, which is "
            "the recalled-from-memory failure this field exists to prevent."
        )
        assert entry.model_id_source.startswith("https://"), (
            f"{entry.provider}/{entry.model}: the model identifier has no "
            "stated source. Vendors publish prices against display names and "
            "accept requests against API ids; the mapping between the two is "
            "a claim and needs its own address."
        )


@pytest.mark.parametrize("key", sorted(PRICES), ids=lambda k: f"{k[0]}/{k[1]}")
def test_every_entry_states_the_day_its_source_was_read(key) -> None:
    for entry in PRICES[key]:
        read_on = dt.date.fromisoformat(entry.retrieved)
        assert read_on <= dt.date(2100, 1, 1)
        assert entry.scope, (
            f"{entry.provider}/{entry.model}: no scope. Every one of these "
            "pages prices several things at once — service tier, modality, "
            "cache state — and a figure that does not say which one it is "
            "cannot be checked against the page it came from."
        )


@pytest.mark.parametrize("key", sorted(PRICES), ids=lambda k: f"{k[0]}/{k[1]}")
def test_every_entry_names_a_declared_provider(key) -> None:
    provider, model = key
    assert provider in PROVIDERS
    for entry in PRICES[key]:
        assert entry.provider == provider and entry.model == model


def test_an_entry_with_no_source_cannot_be_constructed() -> None:
    """The guard, not the table. Asserted against a fresh entry so that a
    table which happens to be complete today cannot make this pass."""
    with pytest.raises(costs.CostTableError, match="source"):
        PriceEntry(
            provider="anthropic", model="whatever",
            tiers=(Rate(input_usd_per_mtok=1.0, output_usd_per_mtok=2.0),),
            source="", model_id_source="https://example.invalid",
            retrieved="2026-08-05", scope="s")


def test_an_entry_whose_source_is_prose_rather_than_an_address_is_refused() -> None:
    """`source="the vendor's pricing page"` is the shape that reads as a
    citation and cannot be opened."""
    with pytest.raises(costs.CostTableError, match="source"):
        PriceEntry(
            provider="anthropic", model="whatever",
            tiers=(Rate(input_usd_per_mtok=1.0, output_usd_per_mtok=2.0),),
            source="the vendor's published pricing page",
            model_id_source="https://example.invalid",
            retrieved="2026-08-05", scope="s")


# ---------------------------------------------------------------------------
# T063 — the accepting set is enumerated, and every near miss refuses.


def test_the_accepting_set_is_exactly_the_table() -> None:
    assert priced_models() == frozenset(PRICES)


@pytest.mark.parametrize("provider,model", [
    # A whole provider nobody could price from its own page.
    ("openai", "gpt-5-mini"),
    ("openai", "gpt-5-nano"),
    # The alias the vendor documents for a dated id. Sourced as an alias, and
    # deliberately not an entry: for the generations that have one it is an
    # evergreen pointer, so its price can move without the id moving.
    ("anthropic", "claude-sonnet-4-5"),
    ("anthropic", "claude-haiku-4-5"),
    # A dated variant of a dateless id — the shape a caller invents.
    ("anthropic", "claude-sonnet-5-20260101"),
    # A family prefix. A prefix match would accept this and price it as
    # whichever member sorted first.
    ("anthropic", "claude-sonnet"),
    ("xai", "grok-4"),
    # Case. Model ids are matched byte for byte.
    ("anthropic", "Claude-Sonnet-5"),
    # The empty model, which a mis-wired caller supplies.
    ("google", ""),
])
def test_a_model_with_no_entry_fails_closed(provider: str, model: str) -> None:
    with pytest.raises(MissingPriceError) as caught:
        price_usd(provider=provider, model=model,
                  input_tokens=1_000, output_tokens=100, as_of=DAY)
    message = str(caught.value)
    assert model in message or "empty" in message, (
        "the refusal does not name the model that could not be priced")
    assert "spend ceiling" in message, (
        "the refusal does not say what the absence costs. An operator who "
        "sees only 'no price' will add one from memory."
    )


def test_a_family_prefix_is_not_priced_as_one_of_its_members() -> None:
    """The same case as the parametrized arm above, named on its own.

    `tests/removal_proofs.sh` targets this one because a proof cannot name a
    parametrized id: `tools/check_tampers.py` refuses it, on the grounds that
    pytest exits 4 for a selector it cannot resolve and the harness would read
    that as a passing proof. So the arm the proof depends on is a test with a
    name of its own.

    The case itself is rule 3 of the house methodology. `claude-sonnet` is a
    prefix of a priced id, and a lookup that accepted it would price it as
    whichever family member sorted first — a rate nobody chose, for a model
    nobody priced.
    """
    assert any(model.startswith("claude-sonnet")
               for provider, model in PRICES if provider == "anthropic"), (
        "no priced anthropic model begins with 'claude-sonnet', so a prefix "
        "match would refuse this too and the arm proves nothing")
    with pytest.raises(MissingPriceError):
        price_usd(provider="anthropic", model="claude-sonnet",
                  input_tokens=1, output_tokens=1, as_of=DAY)


def test_a_float_token_count_is_refused_rather_than_divided() -> None:
    """FR-058's disqualification, named on its own for the same reason.

    A float is the one non-integer that would price *cleanly* if the gate went
    — a str or a bytes raises `TypeError` on the arithmetic and would fail the
    arm for the wrong reason. It is also the shape a bytes-per-token divisor
    actually produces.
    """
    with pytest.raises(costs.CostTableError, match="tokens"):
        price_usd(provider="anthropic", model="claude-opus-5",
                  input_tokens=12.5, output_tokens=0, as_of=DAY)


def test_the_refusal_lists_what_is_priced_for_that_provider() -> None:
    """Enumerated in the message too. An operator told only that their model
    is unknown cannot tell a typo from an unpriced model."""
    with pytest.raises(MissingPriceError) as caught:
        price_usd(provider="anthropic", model="claude-sonnet-4-5",
                  input_tokens=1, output_tokens=1, as_of=DAY)
    message = str(caught.value)
    assert "claude-sonnet-4-5-20250929" in message


def test_an_undeclared_provider_is_refused_before_the_model_is_looked_up() -> None:
    from src.runtime.providers.base import UnknownProviderError

    with pytest.raises(UnknownProviderError):
        price_usd(provider="mistral", model="anything",
                  input_tokens=1, output_tokens=1, as_of=DAY)


def test_openai_is_unpriced_and_the_table_says_so_rather_than_omitting_it() -> None:
    """The absence is recorded, not merely a gap.

    OpenAI's own pricing page does not list either model this repository's
    driver branches on, and for the models it does list it tiers by context
    length without stating the threshold. Both facts are written down, so a
    later reader does not read the gap as an oversight and fill it.
    """
    assert not any(provider == "openai" for provider, _ in PRICES)
    assert "openai" in costs.UNPRICED
    reason = costs.UNPRICED["openai"]
    assert "gpt-5-mini" in reason and "https://" in reason


# ---------------------------------------------------------------------------
# The prices themselves, read off the sources named in the entries.


def test_a_flat_rate_model_prices_as_the_source_states() -> None:
    """Claude Opus 5 at $5/MTok in, $25/MTok out."""
    charged = price_usd(provider="anthropic", model="claude-opus-5",
                        input_tokens=1_000_000, output_tokens=1_000_000,
                        as_of=DAY)
    assert charged == pytest.approx(30.0)


def test_the_dated_change_the_anthropic_source_schedules_is_honoured() -> None:
    """Sonnet 5's introductory rate ends on a date the source states.

    A table that carried one rate per model would be wrong on one side of
    2026-08-31 whichever rate it carried, and wrong in the under-counting
    direction on the later side.
    """
    million = dict(input_tokens=1_000_000, output_tokens=1_000_000)
    last_day = price_usd(provider="anthropic", model="claude-sonnet-5",
                         as_of=dt.date(2026, 8, 31), **million)
    first_day_after = price_usd(provider="anthropic", model="claude-sonnet-5",
                                as_of=dt.date(2026, 9, 1), **million)
    assert last_day == pytest.approx(12.0), "the introductory $2/$10"
    assert first_day_after == pytest.approx(18.0), "the standard $3/$15"
    assert first_day_after > last_day


def test_a_date_no_entry_covers_fails_closed_rather_than_picking_the_nearest() -> None:
    """Extrapolating backwards would price a call at a rate that was not in
    force, and the direction of the error is unknowable."""
    with pytest.raises(MissingPriceError, match="no price in force"):
        price_usd(provider="anthropic", model="claude-sonnet-5",
                  input_tokens=1, output_tokens=1, as_of=dt.date(2020, 1, 1))


def test_the_xai_prompt_length_tier_switches_at_the_stated_threshold() -> None:
    """xAI's source states the threshold and states that it re-rates the
    *whole* request, not the excess."""
    under = price_usd(provider="xai", model="grok-4.5",
                      input_tokens=199_999, output_tokens=1_000_000,
                      as_of=DAY)
    at = price_usd(provider="xai", model="grok-4.5",
                   input_tokens=200_000, output_tokens=1_000_000, as_of=DAY)

    assert under == pytest.approx(199_999 / 1e6 * 2.00 + 6.00)
    assert at == pytest.approx(200_000 / 1e6 * 4.00 + 12.00), (
        "the higher tier must re-rate the output too; the source says all "
        "tokens in the request"
    )
    assert at > under


def test_the_table_holds_three_structurally_different_schedules() -> None:
    """The measured refutation of uniformity, asserted over the table.

    Finding 003 recorded that per-provider cost cannot be assumed uniform.
    What the four vendors' own pages show is stronger than differing numbers:
    the *shapes* differ. One provider schedules a dated change, one tiers by
    prompt length, and one cannot be priced at all from its own page.
    """
    multi_tier = {key for key, entries in PRICES.items()
                  if any(len(e.tiers) > 1 for e in entries)}
    scheduled = {key for key, entries in PRICES.items() if len(entries) > 1}

    assert {p for p, _ in multi_tier} == {"xai"}, (
        f"prompt-length tiers were expected on xAI alone, found on "
        f"{sorted(multi_tier)}"
    )
    assert {p for p, _ in scheduled} == {"anthropic"}, (
        f"a dated price change was expected on Anthropic alone, found on "
        f"{sorted(scheduled)}"
    )
    assert {p for p, _ in PRICES} == {"anthropic", "google", "xai"}, (
        "the priced provider set moved; if a provider was priced or unpriced "
        "on purpose, the reason belongs in UNPRICED in the same commit"
    )


# ---------------------------------------------------------------------------
# FR-058's disqualification, kept out of this module structurally.


@pytest.mark.parametrize("bad", ["1000", b"x" * 1000, 12.5, None, True])
def test_a_token_count_that_is_not_an_integer_is_refused(bad) -> None:
    """The unit is tokens, and only tokens reach this function.

    FR-058 disqualifies an average bytes-per-token divisor by name. This is
    the structural half of keeping one out: a body, a byte count or a float
    cannot be handed to the priced quantity by accident, so nobody can divide
    on the way in.
    """
    with pytest.raises(costs.CostTableError, match="tokens"):
        price_usd(provider="anthropic", model="claude-opus-5",
                  input_tokens=bad, output_tokens=0, as_of=DAY)


def test_a_negative_token_count_is_refused() -> None:
    with pytest.raises(costs.CostTableError, match="negative"):
        price_usd(provider="anthropic", model="claude-opus-5",
                  input_tokens=-1, output_tokens=0, as_of=DAY)


def test_zero_tokens_costs_nothing_and_is_not_an_error() -> None:
    """A turn that consumed nothing is priced, not refused: the fail-closed
    path is for a missing *price*, and conflating the two would make an empty
    turn look like an unpriced model."""
    assert price_usd(provider="anthropic", model="claude-opus-5",
                     input_tokens=0, output_tokens=0, as_of=DAY) == 0.0


# ---------------------------------------------------------------------------
# T064's residue: what this table can derive, stated as a set rather than as
# an absence.


def test_the_derivable_reservation_fields_are_enumerated() -> None:
    """`ReservationPolicy` has three estimated figures. This table derives one.

    Stated as the accepting set rather than as *"it cannot derive wall
    clock"*: a complement would silently grow an entry the day somebody adds
    a per-hour price to this module.
    """
    assert DERIVABLE_RESERVATION_FIELDS == frozenset({"spend_usd"})


def test_a_token_reservation_becomes_a_spend_reservation() -> None:
    """The derivation, run rather than asserted.

    The operator still declares how many tokens a call is expected to cost;
    what stops being a declaration is the dollar figure beside it.
    """
    derived = reservation_spend_usd(
        provider="anthropic", model="claude-opus-5",
        tokens=2_000, as_of=DAY)
    # Reserved at the *output* rate, which is the larger of the two: the split
    # between input and output is not known before the call, and the ledger's
    # whole argument is that a reservation must over-count.
    assert derived == pytest.approx(2_000 / 1e6 * 25.0)


def test_the_reservation_is_derived_at_the_dearer_of_the_two_rates() -> None:
    """Asserted as a comparison rather than as a constant, so that a table
    edit cannot quietly make the reservation the cheaper figure."""
    entry = PRICES[("anthropic", "claude-opus-5")][0]
    cheapest = min(entry.tiers[0].input_usd_per_mtok,
                   entry.tiers[0].output_usd_per_mtok)
    derived = reservation_spend_usd(provider="anthropic",
                                    model="claude-opus-5", tokens=1_000_000,
                                    as_of=DAY)
    assert derived > cheapest


def test_a_reservation_for_an_unpriced_model_fails_closed() -> None:
    with pytest.raises(MissingPriceError):
        reservation_spend_usd(provider="openai", model="gpt-5-mini",
                              tokens=1_000, as_of=DAY)


def test_the_derived_figure_is_accepted_by_the_ledger_it_is_for() -> None:
    """End to end, so the derivation is not merely a number of the right size.

    A figure the ledger refuses would be a derivation that reads correct and
    cannot be used.
    """
    from src.runtime.ledger import ReservationPolicy

    policy = ReservationPolicy(
        spend_usd=reservation_spend_usd(provider="xai", model="grok-4.5",
                                        tokens=8_000, as_of=DAY),
        tokens=8_000,
        wall_clock_seconds=30.0,
    )
    assert policy.spend_usd == pytest.approx(8_000 / 1e6 * 6.00)
