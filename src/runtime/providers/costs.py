"""T062, T063 — the per-provider token cost table, and the refusal for a model nobody priced.

**Why this table exists at all.** It was on nobody's list because the removed
dependency supplied one (**OD-15**). Nothing now converts a provider's reported
token counts into money, and FR-005's spend ceiling is denominated in money —
so without this the ceiling is compared against a number that is always zero.
`src/runtime/providers/base.py::ParsedTurn.cost_usd` records the same gap from
the other side: three of the four providers report tokens and no cost.

**Every entry states an address and a date, and an entry that cannot is absent.**
A price recalled from memory is an invented default wearing a source's clothes,
and it is worse than no entry at all: the absent entry fails closed by
construction and the recalled one silently makes the ceiling wrong for exactly
as long as nobody re-derives it. FR-005 forbids a ceiling *"filled from a
default this specification invented"*; a ceiling correctly configured and
compared against a fabricated conversion rate is that same failure one level
down. So `source`, `model_id_source`, `retrieved` and `scope` are required
fields and `PriceEntry` refuses without them.

**Two addresses per entry, not one, and the second is not pedantry.** Vendors
publish prices against *display names* — "Claude Sonnet 5" — and accept requests
against *API identifiers* — `claude-sonnet-5`. The mapping between the two is a
claim, and it is the claim most likely to be filled in from memory while the
number beside it is dutifully cited. Each entry therefore names the page the
rate came from and the page the identifier came from, and they are usually
different pages.

**No uniformity is assumed, because the four sources do not offer any.**
[Finding 003](../../../specs/001-discovery-validation/findings/003-runtime-provider-agnosticism.md)
recorded that per-provider cost cannot be assumed uniform. Read on 2026-08-05,
the four vendors' own pages are more different than that: the *shapes* differ,
not just the numbers.

- **Anthropic** prices a flat rate per model, and schedules a *dated change* for
  one of them. A table with one rate per model is wrong on one side of
  2026-08-31 whichever rate it holds.
- **xAI** prices in two *prompt-length tiers* with a stated threshold, and its
  page states that reaching the threshold re-rates **every token in the
  request** rather than the excess.
- **Google** prices flat, but per *modality* and per *service tier*, with four
  tiers listed side by side and a free tier beside those.
- **OpenAI is not priced here at all.** See `UNPRICED`.

`Rate.min_input_tokens` and the several-entries-per-model schedule exist to
carry the first two of those. A single `(input, output)` pair per model would
have been an assumption of uniformity in the shape of a data structure.

**What these figures are scoped to, stated because it is not enforceable here.**
Every entry is the **standard synchronous tier, uncached input, text**. Three
consequences, and they do not all point the same way:

- *Cached input is cheaper on all four vendors and is priced here as uncached.*
  `ParsedTurn` reports one `input_tokens` figure and does not split it, so a
  cached prompt is **over**-charged. That is the direction a ceiling should err
  in, and it is the same argument `ledger.py` makes for reserving before a call.
- *Batch and other discounted tiers are cheaper and are priced here as
  standard.* Over-charged again.
- *Google's audio input and OpenAI's Fast mode are dearer than the figures
  here.* Those would be **under**-charged. Neither is reachable: no driver in
  `src/runtime/providers/` sends audio or sets a service tier. This is a stated
  limitation and not a guarded one — nothing in this module can detect a
  modality the caller never reports.

**The unit is tokens, and only tokens reach this module.** FR-058 disqualifies
an average bytes-per-token divisor by name, and the reasoning transfers
unchanged: the ratio varies with content and varies in the direction that
defeats the bound. `price_usd` refuses anything that is not an `int`, so a body,
a byte count or a float cannot be divided on the way in. There is no divisor in
this file. *(The `4.0` in
[finding 022](../../../specs/002-spec-aware-agent-runtime/findings/022-e7-tool-result-truncation-cap.md)
is a vendored constant describing a third party's configuration, not ours, and
is not a source for anything here.)*

**What this does not do, and must not be read as doing.**
[`research/14`](../../../research/14-architecture-synthesis.md) §5.1 records
**U-30** as still open on whether an in-process budget channel can be trusted at
all. This module is in-process. It closes nothing of U-30: a correct conversion
rate on an untrusted channel is a correct rate on an untrusted channel.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from src.runtime.providers.base import ANTHROPIC, GOOGLE, XAI, require_provider


class CostTableError(RuntimeError):
    """A cost entry, or a request to price one, that cannot be as described."""


class MissingPriceError(CostTableError):
    """T063 — no priced entry covers this model, so nothing is priced.

    A distinct type because the remedy is a sourced table entry rather than a
    code change, and because a caller must be able to tell *unpriced* from
    *priced at zero*. Those are the two readings an untyped failure collapses,
    and the second is the one that makes a spend ceiling unenforceable.
    """


# --------------------------------------------------------------------------
# The addresses. Named once so that an entry cites a constant rather than a
# string a reader has to compare character by character against its neighbours.

ANTHROPIC_PRICING = "https://docs.claude.com/en/docs/about-claude/pricing"
ANTHROPIC_MODELS = "https://docs.claude.com/en/docs/about-claude/models/overview"
XAI_MODELS = "https://docs.x.ai/docs/models"
GOOGLE_PRICING = "https://ai.google.dev/gemini-api/docs/pricing"
OPENAI_PRICING = "https://platform.openai.com/docs/pricing"

#: The day every page in this file was read. One date rather than one per entry
#: because they were read in one sitting, and a per-entry date that is really
#: the same date is a field that will drift into being decorative.
READ_ON = "2026-08-05"

#: What every rate in this table covers. See the module docstring for the three
#: consequences and for which of them err in which direction.
STANDARD_SCOPE = (
    "standard synchronous tier, uncached input, text tokens; batch, cached, "
    "priority/fast and non-text rates are not these figures"
)


@dataclass(frozen=True)
class Rate:
    """One band of a model's schedule, in USD per million tokens.

    `min_input_tokens` is the **inclusive** prompt-token floor at which this
    band starts applying, and it applies to the output rate too. That is xAI's
    stated rule — *"requests whose prompt reaches the listed token threshold
    are billed at the higher rate for all tokens in the request"* — and not a
    generalisation invented here. A provider with one flat rate has one band
    with a floor of zero, which is the degenerate case rather than a special
    one.
    """

    input_usd_per_mtok: float
    output_usd_per_mtok: float
    min_input_tokens: int = 0

    def __post_init__(self) -> None:
        for name in ("input_usd_per_mtok", "output_usd_per_mtok"):
            value = getattr(self, name)
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise CostTableError(f"{name} is not a number: {value!r}")
            if value < 0:
                raise CostTableError(
                    f"{name} is negative ({value}). A negative rate lowers a "
                    "running total, which is a ceiling walked back under."
                )
        if not isinstance(self.min_input_tokens, int) or self.min_input_tokens < 0:
            raise CostTableError(
                f"min_input_tokens is {self.min_input_tokens!r}; a band starts "
                "at a token position, and the lowest band starts at zero"
            )


@dataclass(frozen=True)
class PriceEntry:
    """One model's rate over one interval, with the addresses it came from.

    `effective_from` defaults to `retrieved` and the asymmetry with
    `effective_until` is deliberate. A price list stands until it is changed,
    so an open end *forward* is what the source actually says. An open end
    *backwards* would be a claim about a period nobody read the page in, and
    the whole point of this table is that a figure nobody read is not a figure.
    So a date before the retrieval date is priced by nothing, and
    `price_usd` refuses rather than extrapolating.
    """

    provider: str
    model: str
    tiers: tuple[Rate, ...]
    #: Where the *rate* was read.
    source: str
    #: Where the *API model identifier* was read. Usually a different page.
    model_id_source: str
    #: ISO date the two pages above were read.
    retrieved: str
    #: What the rate covers, since every one of these pages prices several
    #: things at once.
    scope: str
    effective_from: str | None = None
    effective_until: str | None = None
    #: Free text for anything a reader would otherwise have to re-derive.
    note: str = ""

    def __post_init__(self) -> None:
        require_provider(self.provider)
        if not self.model:
            raise CostTableError("a price entry must name a model")
        for name in ("source", "model_id_source"):
            value = getattr(self, name)
            if not value.startswith("https://"):
                raise CostTableError(
                    f"{self.provider}/{self.model}: {name} is {value!r}. It "
                    "must be an address a reader can open. Prose naming a "
                    "page reads as a citation and cannot be checked, which is "
                    "the failure mode a price recalled from memory takes."
                )
        if not self.scope:
            raise CostTableError(
                f"{self.provider}/{self.model}: no scope. Every vendor page "
                "prices several things at once — service tier, modality, "
                "cache state — so a figure that does not say which one it is "
                "cannot be checked against the page it came from."
            )
        dt.date.fromisoformat(self.retrieved)
        if not self.tiers:
            raise CostTableError(
                f"{self.provider}/{self.model}: no rate bands")
        floors = [tier.min_input_tokens for tier in self.tiers]
        if floors[0] != 0:
            raise CostTableError(
                f"{self.provider}/{self.model}: the lowest band starts at "
                f"{floors[0]}, so a request below that is priced by nothing"
            )
        if floors != sorted(set(floors)):
            raise CostTableError(
                f"{self.provider}/{self.model}: bands {floors} are not in "
                "strictly ascending order, so which one applies depends on "
                "the order they happen to be written in"
            )
        for name in ("effective_from", "effective_until"):
            value = getattr(self, name)
            if value is not None:
                dt.date.fromisoformat(value)
        if self.starts > self.ends:
            raise CostTableError(
                f"{self.provider}/{self.model}: the interval "
                f"{self.starts}..{self.ends} is empty"
            )

    @property
    def starts(self) -> dt.date:
        return dt.date.fromisoformat(self.effective_from or self.retrieved)

    @property
    def ends(self) -> dt.date:
        if self.effective_until is None:
            return dt.date.max
        return dt.date.fromisoformat(self.effective_until)

    def covers(self, day: dt.date) -> bool:
        return self.starts <= day <= self.ends


def validate_schedule(entries: Sequence[PriceEntry]) -> None:
    """Refuse a model whose entries overlap, or that has none.

    Overlap is refused rather than resolved by order. Two rates in force on one
    day is not a table a reader can check against a page, and picking the first
    would make the answer depend on which line somebody pasted above the other.
    """
    if not entries:
        raise CostTableError("a model with no entries is not priced")
    ordered = sorted(entries, key=lambda entry: entry.starts)
    for earlier, later in zip(ordered, ordered[1:]):
        if later.starts <= earlier.ends:
            raise CostTableError(
                f"{earlier.provider}/{earlier.model}: two rates are in force "
                f"on {later.starts}. A schedule with an overlap answers "
                "differently depending on which line was written first."
            )


def _schedule(*entries: PriceEntry) -> tuple[PriceEntry, ...]:
    validate_schedule(entries)
    return entries


def _anthropic(model: str, *, rate_in: float, rate_out: float,
               effective_from: str | None = None,
               effective_until: str | None = None,
               note: str = "") -> PriceEntry:
    return PriceEntry(
        provider=ANTHROPIC, model=model,
        tiers=(Rate(rate_in, rate_out),),
        source=ANTHROPIC_PRICING, model_id_source=ANTHROPIC_MODELS,
        retrieved=READ_ON, scope=STANDARD_SCOPE,
        effective_from=effective_from, effective_until=effective_until,
        note=note,
    )


# ---------------------------------------------------------------------------
# The table.
#
# **Small on purpose.** Every model priced here is one this repository's own
# drivers, fixtures or findings name. Filling the table out to cover a vendor's
# whole catalogue would put rows in it that nobody has a reason to check, and a
# row nobody checks is where a remembered number survives.

PRICES: Mapping[tuple[str, str], tuple[PriceEntry, ...]] = {
    # -- Anthropic ----------------------------------------------------------
    # Rates: the "Base Input Tokens" and "Output Tokens" columns of the model
    # pricing table. Identifiers: the "Claude API ID" row of the models
    # overview. The *alias* row of that same page is deliberately not priced —
    # see `UNPRICED`'s note on aliases.
    ("anthropic", "claude-opus-5"): _schedule(
        _anthropic("claude-opus-5", rate_in=5.0, rate_out=25.0)),
    ("anthropic", "claude-opus-4-8"): _schedule(
        _anthropic("claude-opus-4-8", rate_in=5.0, rate_out=25.0)),
    ("anthropic", "claude-opus-4-7"): _schedule(
        _anthropic("claude-opus-4-7", rate_in=5.0, rate_out=25.0)),
    # The scheduled change, and the reason this table carries intervals at all.
    # The source states both rows and states the boundary date in words:
    # "Introductory pricing of $2/$10 ... through August 31, 2026, after which
    # the standard pricing of $3/$15 ... will take effect."
    ("anthropic", "claude-sonnet-5"): _schedule(
        _anthropic("claude-sonnet-5", rate_in=2.0, rate_out=10.0,
                   effective_until="2026-08-31",
                   note="introductory rate, stated by the source as ending on "
                        "this date"),
        _anthropic("claude-sonnet-5", rate_in=3.0, rate_out=15.0,
                   effective_from="2026-09-01",
                   note="the standard rate the source states takes effect the "
                        "day after the introductory one ends"),
    ),
    ("anthropic", "claude-sonnet-4-5-20250929"): _schedule(
        _anthropic("claude-sonnet-4-5-20250929", rate_in=3.0, rate_out=15.0,
                   note="priced on the source as 'Claude Sonnet 4.5'; the "
                        "dated identifier is that model's Claude API ID")),
    ("anthropic", "claude-haiku-4-5-20251001"): _schedule(
        _anthropic("claude-haiku-4-5-20251001", rate_in=1.0, rate_out=5.0,
                   note="priced on the source as 'Claude Haiku 4.5'; the "
                        "dated identifier is that model's Claude API ID")),

    # -- xAI ----------------------------------------------------------------
    # One page carries both the identifiers and the rates, and it carries two
    # rows per model. Its own note: "Models listed with two rows use long
    # context pricing: requests whose prompt reaches the listed token threshold
    # are billed at the higher rate for all tokens in the request."
    ("xai", "grok-4.5"): _schedule(PriceEntry(
        provider=XAI, model="grok-4.5",
        tiers=(Rate(2.00, 6.00), Rate(4.00, 12.00, min_input_tokens=200_000)),
        source=XAI_MODELS, model_id_source=XAI_MODELS,
        retrieved=READ_ON, scope=STANDARD_SCOPE,
        note="two bands, threshold stated by the source at 200k prompt "
             "tokens, re-rating the whole request",
    )),
    ("xai", "grok-4.3"): _schedule(PriceEntry(
        provider=XAI, model="grok-4.3",
        tiers=(Rate(1.25, 2.50), Rate(2.50, 5.00, min_input_tokens=200_000)),
        source=XAI_MODELS, model_id_source=XAI_MODELS,
        retrieved=READ_ON, scope=STANDARD_SCOPE,
        note="the model finding 003 drove on this provider",
    )),

    # -- Google -------------------------------------------------------------
    # One page carries both, and prices four service tiers side by side. The
    # figures below are the "Standard / Paid Tier" column, and the input figure
    # is the "text / image / video" one — the page states a dearer audio rate
    # beside it, which no driver here can reach.
    ("google", "gemini-3-flash-preview"): _schedule(PriceEntry(
        provider=GOOGLE, model="gemini-3-flash-preview",
        tiers=(Rate(0.50, 3.00),),
        source=GOOGLE_PRICING, model_id_source=GOOGLE_PRICING,
        retrieved=READ_ON, scope=STANDARD_SCOPE,
        note="the model finding 016 drove on this provider; the source's "
             "audio input rate of $1.00 is not this figure",
    )),
    ("google", "gemini-2.5-flash-lite"): _schedule(PriceEntry(
        provider=GOOGLE, model="gemini-2.5-flash-lite",
        tiers=(Rate(0.10, 0.40),),
        source=GOOGLE_PRICING, model_id_source=GOOGLE_PRICING,
        retrieved=READ_ON, scope=STANDARD_SCOPE,
        note="the model finding 003 drove on this provider; the source's "
             "audio input rate of $0.30 is not this figure",
    )),
}


#: Why a provider or a model that a reader would expect to find is absent.
#:
#: **An absence is recorded rather than left as a gap**, because a gap reads as
#: an oversight and the next reader fills it. Every line here is a decision.
UNPRICED: Mapping[str, str] = {
    "openai": (
        "Unpriced, and deliberately, on two grounds read from "
        f"{OPENAI_PRICING} on {READ_ON}. (1) Neither model this repository's "
        "own driver branches on — `gpt-5-mini` and `gpt-5-nano`, in "
        "`wire_openai._LOW_EFFORT_MODELS` — appears anywhere on that page as "
        "a priced row, so there is no rate to cite for either. (2) For the "
        "models the page does price, it prices them in two columns headed "
        "'Short context' and 'Long context' and states no threshold between "
        "them. An entry carrying only the short-context column would "
        "under-charge every long request, and an entry carrying both would "
        "have to invent the boundary. Under-charging is the direction that "
        "makes a spend ceiling fail to fire, so neither is available. T063 "
        "refuses this provider's models, which is the correct outcome and not "
        "a defect."
    ),
    "anthropic-aliases": (
        f"{ANTHROPIC_MODELS} states a 'Claude API alias' beside each 'Claude "
        "API ID' — `claude-sonnet-4-5` for `claude-sonnet-4-5-20250929`, and "
        "so on. The aliases are sourced and are still not priced here. The "
        "same page states why: for models before the 4.6 generation an alias "
        "is 'a convenience pointer that resolves to a dated model ID', so the "
        "model it names can move without the alias moving, and a price "
        "attached to the alias would then be a price for whatever it resolves "
        "to next. A caller configuring an alias gets T063's refusal, which is "
        "a worse startup experience and a correct one."
    ),
    "xai-cost-in-usd-ticks": (
        "xAI is the one provider that reports a server-side cost, and "
        "`wire_xai.parse_response` deliberately leaves `cost_usd` unset "
        "because the tick scale behind `cost_in_usd_ticks` has never been "
        "observed in our hands — finding 016 read the SDK's already-converted "
        f"attribute. {XAI_MODELS} does not document the scale either, so this "
        "table cannot supply the divisor that comment says is owed a source. "
        "The per-token rates above are what xAI's spend is computed from here."
    ),
}


#: Which of `ReservationPolicy`'s estimated figures this table can derive.
#:
#: **Stated as the accepting set, never as a complement.** *"It cannot derive
#: wall clock"* is a claim about everything this module does not contain, and
#: it would silently stop being true the day somebody added a per-hour price.
#: This is the list, and `tasks.md`'s T064 note records the argument.
DERIVABLE_RESERVATION_FIELDS: frozenset[str] = frozenset({"spend_usd"})


def priced_models() -> frozenset[tuple[str, str]]:
    """The enumerated accepting set: every pair this module will price.

    Exposed so a caller, a test and an error message all read the same list
    rather than three descriptions of it.
    """
    return frozenset(PRICES)


def _require_token_count(name: str, value: Any) -> int:
    """The unit gate. Tokens are integers and nothing else is admitted.

    `bool` is refused explicitly because it is an `int` in Python, and `True`
    arriving where a token count belongs is a wiring fault rather than a
    one-token call.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise CostTableError(
            f"{name} is {value!r}. This table prices tokens, and only an int "
            "is admitted: FR-058 disqualifies an average bytes-per-token "
            "divisor by name, and refusing everything but an integer is what "
            "stops a body or a byte count being divided on the way in."
        )
    if value < 0:
        raise CostTableError(f"{name} is negative ({value})")
    return value


def entry_in_force(provider: str, model: str, *, as_of: dt.date) -> PriceEntry:
    """The one entry covering `as_of`, or a refusal (T063).

    **Enumerated, never complemented.** The lookup is an exact key into
    `PRICES`. There is no prefix match, no alias resolution, no family
    fallback and no case folding: a rule of the form *"anything that looks
    close enough is priced"* fails open on the first model nobody anticipated,
    and that is precisely the model nobody priced.
    """
    require_provider(provider)
    entries = PRICES.get((provider, model))
    if entries is None:
        known = sorted(m for p, m in PRICES if p == provider)
        raise MissingPriceError(
            f"{provider}/{model or '<empty model name>'} has no cost entry. "
            "Nothing prices it, so its spend ceiling cannot be enforced and "
            "the call is refused rather than counted at zero. Priced for this "
            f"provider: {known or 'nothing — see costs.UNPRICED'}. Add an "
            "entry with the address the rate was read at and the day it was "
            "read; do not supply a rate from memory."
        )
    covering = [entry for entry in entries if entry.covers(as_of)]
    if not covering:
        windows = ", ".join(f"{e.starts}..{e.ends}" for e in entries)
        raise MissingPriceError(
            f"{provider}/{model} has no price in force on {as_of}. Recorded "
            f"intervals: {windows}. The nearest interval is not used: a rate "
            "outside the period it was read for is a guess about a period "
            "nobody checked, and the direction of the error is unknowable. "
            "This costs a refusal, and the spend ceiling stays enforceable."
        )
    if len(covering) > 1:
        raise MissingPriceError(
            f"{provider}/{model} has {len(covering)} rates in force on "
            f"{as_of}; the schedule is ambiguous and no rate is chosen"
        )
    return covering[0]


def tier_for(entry: PriceEntry, *, input_tokens: int) -> Rate:
    """The dearest band whose floor this prompt reaches.

    Ascending floors are enforced at construction, so the last band at or
    below `input_tokens` is the one in force.
    """
    chosen = entry.tiers[0]
    for tier in entry.tiers:
        if tier.min_input_tokens <= input_tokens:
            chosen = tier
    return chosen


def price_usd(*, provider: str, model: str, input_tokens: Any,
              output_tokens: Any, as_of: dt.date) -> float:
    """What one call cost, in USD, from the provider's own reported usage.

    `as_of` is required and has no default. A default of *today* would make
    the answer depend on the clock of whichever process asked, and on a
    scheduled boundary that is the difference between two rates the source
    states.
    """
    inputs = _require_token_count("input_tokens", input_tokens)
    outputs = _require_token_count("output_tokens", output_tokens)
    entry = entry_in_force(provider, model, as_of=as_of)
    tier = tier_for(entry, input_tokens=inputs)
    return (inputs / 1_000_000 * tier.input_usd_per_mtok
            + outputs / 1_000_000 * tier.output_usd_per_mtok)


def reservation_spend_usd(*, provider: str, model: str, tokens: int,
                          as_of: dt.date) -> float:
    """T064's residue: the spend reservation, derived rather than declared.

    `ReservationPolicy` carries three estimated figures and this derives one of
    them from another. The operator still declares how many tokens a call is
    expected to consume; the dollar figure beside it stops being a second,
    independent guess that can disagree with the first.

    **Derived at the dearer of the two rates, and at the band the reserved
    total could reach.** The split between input and output is not known before
    the call, and `ledger.py`'s whole argument is that a reservation must
    over-count: *"the crash counts the reservation, which is too much rather
    than too little."* The band is selected against `tokens` because a reserved
    total is an upper bound on the prompt inside it.

    **This does not derive `wall_clock_seconds`, and no argument here could.**
    A table of dollars per token has no time dimension:
    `DERIVABLE_RESERVATION_FIELDS` is the enumerated answer and `tasks.md`'s
    T064 note carries the reasoning.
    """
    reserved = _require_token_count("tokens", tokens)
    entry = entry_in_force(provider, model, as_of=as_of)
    tier = tier_for(entry, input_tokens=reserved)
    dearer = max(tier.input_usd_per_mtok, tier.output_usd_per_mtok)
    return reserved / 1_000_000 * dearer


# Every schedule is validated as the table is built, by `_schedule`. This is the
# second half: that the key a schedule is filed under is the one its entries
# name. A row filed under the wrong key would be priced for a model it is not
# the price of, and nothing else here would notice.
for _key, _entries in PRICES.items():
    for _entry in _entries:
        if (_entry.provider, _entry.model) != _key:
            raise CostTableError(
                f"{_key} holds an entry for "
                f"{(_entry.provider, _entry.model)}"
            )
