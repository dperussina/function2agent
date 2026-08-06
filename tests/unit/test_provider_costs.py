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

**A fourth family was added 2026-08-06 under OD-27 and lives at the bottom of
this file: the operator-declared path.** It is here rather than in a file of
its own because a declared rate and a sourced one are read through the same
lookup and priced by the same arithmetic, and the assertions that matter are
the ones comparing the two — a file boundary between them would make the
comparison arms pick a side to live on. The arm to read first is
`test_a_single_rate_is_refused_where_the_vendors_card_has_two_columns`.
"""

from __future__ import annotations

import datetime as dt

import pytest

from src.runtime.providers import costs
from src.runtime.providers.base import PROVIDERS
from src.runtime.providers.costs import (
    DERIVABLE_RESERVATION_FIELDS,
    PRICES,
    PROVENANCE_VENDOR,
    MissingPriceError,
    OperatorPrice,
    OperatorPriceBook,
    OperatorPriceError,
    PriceEntry,
    Rate,
    priced_models,
    price_usd,
    require_priceable,
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
    assert charged.usd == pytest.approx(30.0)
    assert charged.provenance == PROVENANCE_VENDOR


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
    assert last_day.usd == pytest.approx(12.0), "the introductory $2/$10"
    assert first_day_after.usd == pytest.approx(18.0), "the standard $3/$15"
    assert first_day_after.usd > last_day.usd


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

    assert under.usd == pytest.approx(199_999 / 1e6 * 2.00 + 6.00)
    assert at.usd == pytest.approx(200_000 / 1e6 * 4.00 + 12.00), (
        "the higher tier must re-rate the output too; the source says all "
        "tokens in the request"
    )
    assert at.usd > under.usd


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
                     input_tokens=0, output_tokens=0, as_of=DAY).usd == 0.0


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
    assert derived.usd == pytest.approx(2_000 / 1e6 * 25.0)


def test_the_reservation_is_derived_at_the_dearer_of_the_two_rates() -> None:
    """Asserted as a comparison rather than as a constant, so that a table
    edit cannot quietly make the reservation the cheaper figure."""
    entry = PRICES[("anthropic", "claude-opus-5")][0]
    cheapest = min(entry.tiers[0].input_usd_per_mtok,
                   entry.tiers[0].output_usd_per_mtok)
    derived = reservation_spend_usd(provider="anthropic",
                                    model="claude-opus-5", tokens=1_000_000,
                                    as_of=DAY)
    assert derived.usd > cheapest


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
                                        tokens=8_000, as_of=DAY).usd,
        tokens=8_000,
        wall_clock_seconds=30.0,
    )
    assert policy.spend_usd == pytest.approx(8_000 / 1e6 * 6.00)


# ---------------------------------------------------------------------------
# OD-27 — the operator-declared path.
#
# Read `test_a_single_rate_is_refused_where_the_vendors_card_has_two_columns`
# first. It is the arm the decision turns on, and every other arm below is
# about keeping the two provenances apart once one has been admitted.


def _declared(model: str = "gpt-5-mini", *, tiers: tuple[Rate, ...],
              provider: str = "openai", **kw) -> OperatorPrice:
    """A well-formed declaration, so each arm below varies one thing."""
    kw.setdefault("display_name", "GPT-5 mini")
    kw.setdefault("declared_by", "platform-eng@example.invalid")
    kw.setdefault("declaration_ref", "contracts/openai-2026-q3.md")
    kw.setdefault("declared_on", "2026-08-01")
    kw.setdefault("scope", "standard synchronous tier, uncached input, text")
    return OperatorPrice(provider=provider, model=model, tiers=tiers, **kw)


#: Two columns and the boundary between them, which is what OpenAI's page
#: withholds and what a declaration for that provider has to supply.
_TWO_COLUMNS = (Rate(0.25, 2.00), Rate(0.50, 4.00, min_input_tokens=128_000))


def test_a_single_rate_is_refused_where_the_vendors_card_has_two_columns() -> None:
    """OD-27 limb ②, and the arm the whole decision turns on.

    `costs.UNPRICED["openai"]` records that the vendor prices in a *"Short
    context"* and a *"Long context"* column and states no threshold. A
    declaration carrying one number asserts the boundary does not exist, which
    the vendor's own page contradicts — and picking the cheap column
    under-charges, which is the direction that makes a ceiling **fail to
    fire**. Admitting it would recreate that defect with the operator's name
    on it, which is worse than the present refusal because it looks
    authorised.
    """
    with pytest.raises(OperatorPriceError, match="a single rate is refused"):
        _declared(tiers=(Rate(0.25, 2.00),))


def test_the_same_rate_twice_is_refused_because_it_is_one_column_read_twice() -> None:
    """The way round limb ② that a well-meaning author reaches for first.

    Two identical bands satisfy *"supply both columns"* by shape and supply
    one column by content, and nothing here can tell a card that genuinely
    quotes the same figure twice from a reader who copied one row. The first
    reading produces exactly the under-charge the limb exists to stop, so the
    shape is refused rather than resolved.
    """
    flat = (Rate(0.25, 2.00), Rate(0.25, 2.00, min_input_tokens=128_000))
    with pytest.raises(OperatorPriceError, match="must be dearer"):
        _declared(tiers=flat)


def test_a_cheaper_long_context_band_is_refused_as_well() -> None:
    """The other direction, refused for a reason the first arm does not give.

    `Rate.min_input_tokens` means *re-rate the whole request at this band*, so
    a cheaper upper band inverts what the shape asserts. Left admitted it
    would be a discount that grows with prompt length, which under-charges in
    the same direction as the single rate.
    """
    inverted = (Rate(0.50, 4.00), Rate(0.25, 2.00, min_input_tokens=128_000))
    with pytest.raises(OperatorPriceError, match="must be dearer"):
        _declared(tiers=inverted)


def test_the_refusal_names_the_remedy_rather_than_only_the_rule() -> None:
    """An operator told *"refused"* supplies the same thing again.

    The message has to say the vendor prices in two columns and that the
    threshold is what is owed, because the operator holds a rate card and this
    module does not.
    """
    with pytest.raises(OperatorPriceError) as raised:
        _declared(tiers=(Rate(0.25, 2.00),))

    message = str(raised.value)
    assert "Short context" in message and "Long context" in message
    assert "threshold" in message


def test_both_columns_and_the_threshold_are_admitted_and_the_band_switches() -> None:
    """Limb ② is a gate rather than a wall: supplying what the page withheld
    gets the model priced, and the threshold the operator stated is the one
    that re-rates the request."""
    book = OperatorPriceBook([_declared(tiers=_TWO_COLUMNS)])
    common = dict(provider="openai", model="gpt-5-mini", output_tokens=0,
                  as_of=DAY, operator_prices=book)

    under = price_usd(input_tokens=127_999, **common)
    at = price_usd(input_tokens=128_000, **common)

    assert under.usd == pytest.approx(127_999 / 1e6 * 0.25)
    assert at.usd == pytest.approx(128_000 / 1e6 * 0.50)
    assert at.usd > under.usd


def test_a_provider_with_no_published_columns_may_declare_a_single_rate() -> None:
    """The refusal is scoped to the enumerated providers and is not a general
    ban on flat rates.

    Stated because a rule that refused every single-band declaration would be
    refusing the shape most vendors publish, and the next reader would relax
    it in the wrong place.
    """
    flat = OperatorPriceBook([_declared(
        provider="google", model="gemini-4-experimental",
        display_name="Gemini 4 Experimental", tiers=(Rate(1.0, 4.0),))])

    priced = price_usd(provider="google", model="gemini-4-experimental",
                       input_tokens=1_000_000, output_tokens=0, as_of=DAY,
                       operator_prices=flat)

    assert priced.usd == pytest.approx(1.0)


def test_a_declared_figure_says_it_was_declared() -> None:
    """OD-27's record limb: the provenance travels with the figure.

    Asserted on the value `price_usd` returns rather than on a log line,
    because a log is gone with the process that wrote it and the reader who
    needs this is holding a total months later.
    """
    book = OperatorPriceBook([_declared(tiers=_TWO_COLUMNS)])

    priced = price_usd(provider="openai", model="gpt-5-mini",
                       input_tokens=1_000, output_tokens=1_000, as_of=DAY,
                       operator_prices=book)

    assert priced.provenance == costs.PROVENANCE_OPERATOR
    assert priced.is_operator_declared is True
    assert "platform-eng@example.invalid" in priced.attribution


def test_a_sourced_figure_and_a_declared_one_are_not_the_same_value() -> None:
    """The comparison, because each half asserted alone would pass against a
    constant. A `PricedSpend` that answered `operator` for everything would
    satisfy the arm above."""
    declared = price_usd(provider="openai", model="gpt-5-mini",
                         input_tokens=1_000, output_tokens=0, as_of=DAY,
                         operator_prices=OperatorPriceBook(
                             [_declared(tiers=_TWO_COLUMNS)]))
    sourced = price_usd(provider="anthropic", model="claude-opus-5",
                        input_tokens=1_000, output_tokens=0, as_of=DAY)

    assert declared.provenance != sourced.provenance
    assert sourced.provenance == PROVENANCE_VENDOR
    assert sourced.is_operator_declared is False


def test_the_figure_cannot_be_reached_by_an_implicit_coercion() -> None:
    """No `__float__`, on purpose.

    An implicit coercion would let a caller drop the provenance without
    writing anything, which is the one thing `PricedSpend` exists to prevent.
    `.usd` is the explicit act, in the shape `Config.raw()` establishes.
    """
    priced = price_usd(provider="anthropic", model="claude-opus-5",
                       input_tokens=1_000, output_tokens=0, as_of=DAY)

    with pytest.raises(TypeError):
        float(priced)
    assert priced.usd == pytest.approx(1_000 / 1e6 * 5.0)


def test_a_declaration_cannot_displace_a_rate_read_off_a_vendors_page() -> None:
    """Refused at construction, so the operator learns at startup rather than
    discovering a sourced rate had quietly stopped being used.

    Nothing is unblocked by admitting it — that session already runs — and
    what is risked is the ambiguity `validate_schedule` refuses between two
    vendor rates, arriving from the other side.
    """
    with pytest.raises(OperatorPriceError, match="already priced"):
        _declared(provider="anthropic", model="claude-opus-5",
                  display_name="Claude Opus 5", tiers=(Rate(1.0, 1.0),))


def test_the_vendor_table_wins_when_it_grows_a_row_under_a_built_book(
        monkeypatch: pytest.MonkeyPatch) -> None:
    """The second enforcement, which holds where the first cannot.

    `OperatorPrice` refuses a key `PRICES` holds *at construction*, so a book
    can only come to shadow a sourced rate if the table grows the row
    afterwards — which is what the next sourced entry to land does to every
    deployment already holding a declaration for that model. The lookup order
    is what covers it, and it is asserted separately because the two failures
    happen at different times and only this one happens after shipping.
    """
    key = ("google", "gemini-4-preview")
    book = OperatorPriceBook([_declared(
        provider="google", model="gemini-4-preview",
        display_name="Gemini 4 Preview", tiers=(Rate(99.0, 99.0),))])

    monkeypatch.setitem(PRICES, key, (PriceEntry(
        provider="google", model="gemini-4-preview", tiers=(Rate(1.0, 4.0),),
        source=costs.GOOGLE_PRICING, model_id_source=costs.GOOGLE_PRICING,
        retrieved=costs.READ_ON, scope=costs.STANDARD_SCOPE),))

    priced = price_usd(provider="google", model="gemini-4-preview",
                       input_tokens=1_000_000, output_tokens=0, as_of=DAY,
                       operator_prices=book)

    assert priced.provenance == PROVENANCE_VENDOR
    assert priced.usd == pytest.approx(1.0), "the sourced rate, not 99.0"


def test_an_alias_is_not_an_address_a_declaration_may_use() -> None:
    """OD-27 limb ③, first half.

    The absence at an alias is **the address and not the number**, so no rate
    repairs it: the vendor's own page says an alias resolves to a dated id,
    which can move with no event this table observes.
    """
    with pytest.raises(OperatorPriceError, match="not an address"):
        _declared(provider="anthropic", model="claude-sonnet-4-5",
                  display_name="Claude Sonnet 4.5", tiers=(Rate(3.0, 15.0),))


def test_the_alias_refusal_names_the_dated_identifier_that_works() -> None:
    """A refusal with no remedy reads as a product that cannot serve the
    model. The dated identifier is priced already, so the cost of this
    refusal is a rewritten line rather than a blocked session."""
    with pytest.raises(OperatorPriceError) as raised:
        _declared(provider="anthropic", model="claude-haiku-4-5",
                  display_name="Claude Haiku 4.5", tiers=(Rate(1.0, 5.0),))

    assert "dated identifier" in str(raised.value)
    assert ("anthropic", "claude-haiku-4-5-20251001") in priced_models()


def test_every_recorded_absence_says_whether_a_declaration_reaches_it() -> None:
    """Limb ③'s coverage rule, asserted rather than left to the module guard.

    A reader who finds two of three absences answered assumes the third was
    overlooked. The module refuses to import without this, and this arm is
    what says so out loud — including that the answers are three *different*
    ones, since three copies of *"reachable"* would satisfy a set comparison.
    """
    assert set(costs.OPERATOR_REACH) == set(costs.UNPRICED)
    assert costs.OPERATOR_REACH["openai"].startswith("REACHABLE")
    assert costs.OPERATOR_REACH["anthropic-aliases"].startswith("NOT REACHABLE")
    assert costs.OPERATOR_REACH["xai-cost-in-usd-ticks"].startswith(
        "OUT OF SCOPE")


def test_a_declaration_states_who_made_it_and_where_it_lives() -> None:
    """What stands in for a source, given a declaration has none.

    A vendor entry cites a page and a date; this cites a party and a
    document. Both are required, because a figure nobody can trace is
    carrying a spend ceiling either way.
    """
    for blank in ("declared_by", "declaration_ref"):
        with pytest.raises(OperatorPriceError, match=f"no {blank}"):
            _declared(tiers=_TWO_COLUMNS, **{blank: ""})


def test_a_declaration_records_both_addresses() -> None:
    """The two-address property, carried over from `PriceEntry`.

    Vendors publish against display names and accept requests against API
    identifiers, and an operator's contract is written against whichever one
    their vendor put on it. A declaration recording only one cannot be
    checked against the card it was read from.
    """
    with pytest.raises(OperatorPriceError, match="no display name"):
        _declared(tiers=_TWO_COLUMNS, display_name="")
    with pytest.raises(OperatorPriceError, match="matches nothing"):
        _declared(model="", tiers=_TWO_COLUMNS)


def test_two_declarations_in_force_on_one_day_are_refused() -> None:
    """The set-level check no single declaration can make.

    `validate_schedule` refuses this between vendor entries and the argument
    transfers unchanged: two rates in force answers differently depending on
    which line was written first.
    """
    with pytest.raises(OperatorPriceError, match="two declarations"):
        OperatorPriceBook([
            _declared(tiers=_TWO_COLUMNS),
            _declared(tiers=_TWO_COLUMNS, declared_on="2026-08-07"),
        ])


def test_a_declared_zero_is_a_declaration_and_not_an_absence() -> None:
    """The distinction `spend_usd: float | None` made one layer down.

    A model an operator *forgot* must not price at nothing. A zero an
    operator *wrote* is accountable, is carried as operator provenance, and is
    named at startup — which is where a rate that disables the spend
    dimension has to be read.
    """
    free = OperatorPriceBook([_declared(
        provider="google", model="gemini-4-internal",
        display_name="Gemini 4 (internal allocation)",
        tiers=(Rate(0.0, 0.0),))])

    priced = price_usd(provider="google", model="gemini-4-internal",
                       input_tokens=1_000_000, output_tokens=1_000_000,
                       as_of=DAY, operator_prices=free)
    assert priced.usd == 0.0
    assert priced.provenance == costs.PROVENANCE_OPERATOR

    with pytest.raises(MissingPriceError):
        price_usd(provider="google", model="gemini-4-forgotten",
                  input_tokens=1_000_000, output_tokens=1_000_000,
                  as_of=DAY, operator_prices=free)


def test_an_empty_book_prices_nothing_rather_than_pricing_at_zero() -> None:
    """The default that would be dangerous is one that produces a figure."""
    with pytest.raises(MissingPriceError):
        price_usd(provider="openai", model="gpt-5-mini", input_tokens=1,
                  output_tokens=1, as_of=DAY,
                  operator_prices=costs.NO_OPERATOR_PRICES)


def test_a_declaration_outside_its_stated_interval_is_not_extrapolated() -> None:
    """A contract has an end date and the rate after it is not this rate.

    Same treatment as a vendor entry outside its interval: refuse rather than
    reach for the nearest, because the direction of the error is unknowable.
    """
    expired = OperatorPriceBook([_declared(
        tiers=_TWO_COLUMNS, declared_on="2026-01-01",
        effective_until="2026-06-30")])

    with pytest.raises(MissingPriceError, match="no price in force"):
        price_usd(provider="openai", model="gpt-5-mini", input_tokens=1,
                  output_tokens=1, as_of=DAY, operator_prices=expired)


# ---------------------------------------------------------------------------
# OD-27 limb ④ — the startup preflight.


def test_an_unpriceable_model_is_refused_at_startup_not_at_its_first_call() -> None:
    """FR-058's treatment: absence makes startup fail loudly.

    Without this the deployment starts, accepts a session, builds a request,
    calls the provider — and refuses *after* the money for that call is
    spent.
    """
    with pytest.raises(MissingPriceError):
        require_priceable(provider="openai", model="gpt-5-mini", as_of=DAY)


def test_the_preflight_catches_a_declaration_written_against_the_wrong_address() -> None:
    """The failure nothing at construction can see.

    An operator whose contract prices *"GPT-5 mini"* and who declares that
    string as the identifier has a well-formed book matching no request this
    runtime will make — unpriced *while looking configured*, the worst of the
    three states. What sees it is asking at startup whether the model in
    force is priced.
    """
    mis_addressed = OperatorPriceBook([_declared(
        model="GPT-5 mini", display_name="GPT-5 mini", tiers=_TWO_COLUMNS)])

    with pytest.raises(MissingPriceError):
        require_priceable(provider="openai", model="gpt-5-mini", as_of=DAY,
                          operator_prices=mis_addressed)
    # And the same book is fine for the address it was actually written for,
    # so the arm above is about the mismatch rather than about the book.
    require_priceable(provider="openai", model="GPT-5 mini", as_of=DAY,
                      operator_prices=mis_addressed)


def test_the_startup_line_names_the_provenance_and_the_rate() -> None:
    """What the operator reads before a session runs.

    It matters most for a declared zero: a rate that disables the spend
    dimension is a thing to read up front, not to infer afterwards from a
    total that never moved.
    """
    free = OperatorPriceBook([_declared(
        provider="google", model="gemini-4-internal",
        display_name="Gemini 4 (internal allocation)",
        tiers=(Rate(0.0, 0.0),))])

    line = require_priceable(provider="google", model="gemini-4-internal",
                             as_of=DAY, operator_prices=free)

    assert costs.PROVENANCE_OPERATOR in line
    assert "platform-eng@example.invalid" in line
    assert "$0.0/MTok in" in line


def test_the_startup_line_for_a_sourced_rate_points_at_the_page_and_the_day() -> None:
    """The comparison arm. A line that said `operator` for everything would
    satisfy the one above."""
    line = require_priceable(provider="anthropic", model="claude-opus-5",
                             as_of=DAY)

    assert PROVENANCE_VENDOR in line
    assert costs.ANTHROPIC_PRICING in line
    assert costs.READ_ON in line
