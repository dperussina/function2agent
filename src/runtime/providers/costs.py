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

**Two provenances, and they are two types rather than one type with a flag.**
`PriceEntry` is a rate read off a vendor's page. `OperatorPrice` is a rate an
operator declares under **OD-27**, for a model no vendor page priced here. They
share the band arithmetic and share nothing else, because the whole point is
that a spend figure derived from a declaration must not be confusable with one
derived from a published rate. A discriminant field on one type is confusable by
any caller that forgets to read it; two types carry the distinction to every call
site. `price_usd` therefore returns `PricedSpend` — the figure *and* where the
rate came from — and reaching the bare number is `.usd`, an explicit act in the
shape `Config.raw()` already establishes for FR-043's markings.

**What an operator may declare, and the one thing they may not.** See
`OperatorPrice`. The refusal that matters is the context-tiered one: OpenAI's
page prices in a *"Short context"* and a *"Long context"* column and states no
boundary, so a single rate for one of those models is the invented boundary
wearing the operator's name — which is worse than today's refusal, because it
looks authorised. `CONTEXT_TIERED_WITHOUT_THRESHOLD` is the enumerated list and
`OperatorPrice` refuses a single band for anything on it.

**What this does not do, and must not be read as doing.**
[`research/14`](../../../research/14-architecture-synthesis.md) §5.1 records
**U-30** as still open on whether an in-process budget channel can be trusted at
all. This module is in-process. It closes nothing of U-30: a correct conversion
rate on an untrusted channel is a correct rate on an untrusted channel. An
operator-declared rate does not close it either and is not offered as doing so:
it moves who is accountable for the number, not whether the channel carrying it
can be trusted.
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


class OperatorPriceError(CostTableError):
    """OD-27 — an operator declaration that cannot be as described.

    Distinct from `MissingPriceError` because the two land on different people.
    A missing price is a gap in this table and its remedy is a sourced entry; a
    refused declaration is a gap in what the *operator* supplied and its remedy
    is a corrected declaration. Collapsing them would tell an operator who
    declared half a rate card that the model is unpriced, which is true and
    useless.
    """


# --------------------------------------------------------------------------
# Provenance. Two values, and neither is a default anywhere: the provenance of
# a rate is a property of the type that holds it, so there is no field for a
# later entry to leave unset or set wrongly.

#: Read off a vendor's published page, on a stated date. `PriceEntry`.
PROVENANCE_VENDOR = "vendor"
#: Declared by an operator under OD-27, against no published page.
#: `OperatorPrice`.
PROVENANCE_OPERATOR = "operator"

PROVENANCES: frozenset[str] = frozenset({PROVENANCE_VENDOR, PROVENANCE_OPERATOR})


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


def _validate_bands(label: str, tiers: Sequence[Rate]) -> None:
    """The band schedule's own shape, shared by both provenances.

    Written once rather than twice because a vendor's bands and an operator's
    bands are the same arithmetic — `tier_for` cannot tell them apart and must
    not have to. What differs between the two is *which* declarations are
    admitted at all, and that lives on the types.
    """
    if not tiers:
        raise CostTableError(f"{label}: no rate bands")
    floors = [tier.min_input_tokens for tier in tiers]
    if floors[0] != 0:
        raise CostTableError(
            f"{label}: the lowest band starts at {floors[0]}, so a request "
            "below that is priced by nothing"
        )
    if floors != sorted(set(floors)):
        raise CostTableError(
            f"{label}: bands {floors} are not in strictly ascending order, so "
            "which one applies depends on the order they happen to be written "
            "in"
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
        _validate_bands(f"{self.provider}/{self.model}", self.tiers)
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
    def provenance(self) -> str:
        """Always `PROVENANCE_VENDOR`, and a property rather than a field.

        A field would be a place an operator entry could claim a vendor's
        provenance, which is the one confusion this distinction exists to make
        impossible. The provenance of a rate is which type holds it.
        """
        return PROVENANCE_VENDOR

    @property
    def attribution(self) -> str:
        """Where a reader goes to check this rate. The page and the day."""
        return f"{self.source} (read {self.retrieved})"

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


# ---------------------------------------------------------------------------
# OD-27 — the operator-declared path, and the three absences above measured
# against it.
#
# The corpus forbids *invented* defaults, not *operator-declared* values.
# **FR-058** is the precedent this follows in shape: required configuration
# with no default, startup failing loudly when it is absent, and a
# configuration outside what the requirement permits **refused rather than
# clamped**. `ReservationPolicy` refuses an unset spend or token figure on the
# same reasoning. What is added here is the third instance of that one pattern
# and not a new one, which is what keeps it a decision rather than a loophole.


#: Providers whose published rate card prices by context length in **two
#: columns with no stated boundary between them**.
#:
#: **This is the list that makes the refusal executable rather than advisory.**
#: An operator declaring a rate for one of these models must supply both
#: columns and the threshold; a single rate is refused. The reasoning is
#: `UNPRICED["openai"]`'s second ground, unchanged and now load-bearing in a
#: second place: picking either column requires inventing the boundary, the
#: cheap column under-charges, and under-charging is the direction that makes a
#: ceiling **fail to fire** — the failure the spend ceiling exists to remove.
#: Letting an operator supply one number here would recreate that defect with
#: the operator's name on it, which is worse than the present refusal because
#: it looks authorised.
CONTEXT_TIERED_WITHOUT_THRESHOLD: Mapping[str, str] = {
    "openai": (
        f"{OPENAI_PRICING}, read {READ_ON}, prices this provider's models in "
        "a 'Short context' and a 'Long context' column and states no "
        "threshold between them. A declaration carrying one rate is a claim "
        "that the boundary does not exist, which the vendor's own page "
        "contradicts; a declaration carrying one rate *twice* is equally "
        "consistent with having read the card and with having read one column "
        "twice, and this module cannot tell those apart. Supply both columns "
        "and the prompt-token threshold your own rate card states."
    ),
}


#: `(provider, model)` pairs no declaration may address, and why each is
#: refused rather than reached.
#:
#: **An alias is refused because the defect is the address, not the number.**
#: An operator can supply the rate an alias is billed at today; nobody can
#: supply the model it will name tomorrow. `UNPRICED["anthropic-aliases"]`
#: quotes the vendor: an alias is *"a convenience pointer that resolves to a
#: dated model ID"*, so a rate attached to one becomes a rate for whatever it
#: resolves to next, silently and with no event this table could observe. The
#: two-address property is what fails: the second address is not an address.
#: The remedy is available and cheap, which is why this is a refusal rather
#: than a hardship — declare against the dated identifier, which is stable, is
#: what the request is actually made against, and is already priced here.
REFUSED_ADDRESSES: Mapping[tuple[str, str], str] = {
    ("anthropic", "claude-sonnet-4-5"): "alias for claude-sonnet-4-5-20250929",
    ("anthropic", "claude-haiku-4-5"): "alias for claude-haiku-4-5-20251001",
}


#: Every key of `UNPRICED`, measured against this path: what a declaration can
#: and cannot reach. **Stated for all three rather than for the one that
#: changed**, because a reader who finds two of three answered will assume the
#: third was overlooked.
OPERATOR_REACH: Mapping[str, str] = {
    "openai": (
        "REACHABLE, conditionally. This is the absence that forced OD-27: "
        "with the table wired to a running session, an OpenAI session fails "
        "closed on spend and cannot run at all. A declaration is admitted — "
        "and only with both context columns and the threshold between them, "
        "per CONTEXT_TIERED_WITHOUT_THRESHOLD."
    ),
    "anthropic-aliases": (
        "NOT REACHABLE, and enumerated in REFUSED_ADDRESSES so the refusal is "
        "executed rather than described. The absence is an unstable address "
        "and no rate fixes an address. Nothing is blocked by the refusal: the "
        "dated identifier the alias resolves to is priced above."
    ),
    "xai-cost-in-usd-ticks": (
        "OUT OF SCOPE by construction, which is neither reachable nor "
        "refused, and the distinction is worth the word. That absence is a "
        "missing *unit scale* — what one `cost_in_usd_ticks` tick is worth — "
        "and this path declares USD per million tokens. There is nothing an "
        "operator could type here that would engage it, so there is nothing "
        "to refuse; and xAI's per-token rates are already sourced above, so "
        "no session is blocked. A tick scale is owed a source, not a "
        "declaration."
    ),
}


@dataclass(frozen=True)
class OperatorPrice:
    """OD-27 — a rate an operator declares, for a model no page here priced.

    **Why this is a separate type from `PriceEntry` and not a flag on it.** A
    spend figure derived from a declaration has to stay distinguishable from
    one derived from a published rate, at the point where somebody decides
    whether to trust the total. A discriminant field is distinguishable only to
    a caller that remembers to read it; a separate type is distinguishable to
    the type checker at every call site, and `price_usd` returns the
    provenance beside the figure so that a caller cannot record one without
    the other.

    **Two addresses here as well, and for the same reason they are on
    `PriceEntry`.** Vendors publish against display names and accept requests
    against API identifiers, and an operator's own contract is a document
    written against whichever of the two their vendor put on it. A declaration
    naming only the contract's name would match nothing the runtime ever calls
    — landing back at unpriced *while looking configured*, which is the worst
    of the three states. `model` is the identifier the request is made
    against and is what the lookup is keyed on; `display_name` is what the
    declaration was read from. `require_priceable` is what turns a mismatch
    between them into a startup failure instead of a first-call surprise.

    **What stands in for a source, given there is not one.** A vendor entry
    cites a page and a date. A declaration cannot, and pretending otherwise —
    an `https://` field holding an internal wiki link — would make the two
    look alike in exactly the field that is supposed to tell them apart. So
    the substitute is not a weaker citation but a different kind of one:
    `declared_by` names an accountable party and `declaration_ref` names where
    the declaration lives. *Who says so* is what replaces *which page says so*,
    and both are required.

    **A declared rate of zero is a declaration and is admitted.** It is not
    the same state as no declaration, which refuses. That distinction is the
    one `b2d124f` made by typing `spend_usd` as `float | None`, and collapsing
    it here would put it straight back: a model an operator forgot would be
    priced at nothing and the ceiling would never fire. A zero that was
    *declared* is accountable, is carried as operator-provenance on every
    record it produces, and is named by `require_priceable` at startup, which
    is where a rate that disables the spend dimension has to be read.

    **What this type may not do**, each refused in `__post_init__`:

    - *Address a model already priced from its vendor's page.* Nothing is
      unblocked by it — that session already runs — and what is risked is a
      sourced rate silently displaced by an unsourced one. It is the same
      ambiguity `validate_schedule` refuses between two vendor rates: two
      rates in force is not a table a reader can check.
    - *Address one of `REFUSED_ADDRESSES`.*
    - *Carry a single band where the vendor's card has two columns and no
      stated boundary.* See `CONTEXT_TIERED_WITHOUT_THRESHOLD`.
    """

    provider: str
    #: The API identifier requests are made against. What the lookup is keyed
    #: on, because it is the string that reaches the vendor.
    model: str
    #: The name the operator's own rate card prices against.
    display_name: str
    tiers: tuple[Rate, ...]
    #: The accountable party. This is what stands where `source` stands on a
    #: vendor entry, and it is a name rather than an address on purpose.
    declared_by: str
    #: Where the declaration itself lives, so a reader can go and read it.
    declaration_ref: str
    #: ISO date the declaration was made.
    declared_on: str
    #: What the rate covers. Required for the same reason `PriceEntry.scope`
    #: is: a contract prices several things at once too.
    scope: str
    effective_from: str | None = None
    effective_until: str | None = None
    note: str = ""

    def __post_init__(self) -> None:
        require_provider(self.provider)
        label = f"{self.provider}/{self.model or '<empty model name>'}"
        if not self.model:
            raise OperatorPriceError(
                "a declaration must name the API identifier requests are made "
                "against. A declaration keyed on nothing matches nothing, and "
                "the session it was written for stays unpriced while the "
                "configuration reads as complete."
            )
        if not self.display_name:
            raise OperatorPriceError(
                f"{label}: no display name. Vendors publish against display "
                "names and accept requests against API identifiers, and a "
                "declaration that records only one of the two cannot be "
                "checked against the rate card it was read from — which is "
                "the claim most likely to have been filled in from memory."
            )
        for name in ("declared_by", "declaration_ref"):
            if not getattr(self, name):
                raise OperatorPriceError(
                    f"{label}: no {name}. A declared rate cites no vendor "
                    "page by construction, so what stands in its place is who "
                    "declared it and where the declaration lives. Without "
                    "both, a figure nobody can trace is carrying a spend "
                    "ceiling."
                )
        if not self.scope:
            raise OperatorPriceError(
                f"{label}: no scope. A rate card prices several things at "
                "once — tier, modality, cache state — so a figure that does "
                "not say which one it is cannot be checked against the "
                "declaration it came from."
            )
        dt.date.fromisoformat(self.declared_on)
        if (self.provider, self.model) in PRICES:
            raise OperatorPriceError(
                f"{label} is already priced from its vendor's page, so this "
                "declaration is refused rather than allowed to displace it. "
                "Nothing is unblocked by admitting it — that session already "
                "runs — and what it risks is a sourced rate silently replaced "
                "by an unsourced one. This is the ambiguity `validate_schedule` "
                "refuses between two vendor rates, arriving from the other "
                "side: two rates in force on one day is not a table a reader "
                "can check. OD-27 authorises declarations for models nothing "
                "prices; a negotiated rate for a listed model is a different "
                "question and is not decided by it."
            )
        refused = REFUSED_ADDRESSES.get((self.provider, self.model))
        if refused is not None:
            raise OperatorPriceError(
                f"{label} is not an address a declaration may use: "
                f"{refused}. The absence here is the address and not the "
                "number, so no rate repairs it — the identifier can start "
                "naming a different model with no event this table could "
                "observe. Declare against the dated identifier instead, which "
                "is what the request is made against and is priced already. "
                "See costs.UNPRICED['anthropic-aliases']."
            )
        _validate_bands(label, self.tiers)
        _require_stated_threshold(self)
        for name in ("effective_from", "effective_until"):
            value = getattr(self, name)
            if value is not None:
                dt.date.fromisoformat(value)
        if self.starts > self.ends:
            raise OperatorPriceError(
                f"{label}: the interval {self.starts}..{self.ends} is empty")

    @property
    def provenance(self) -> str:
        return PROVENANCE_OPERATOR

    @property
    def attribution(self) -> str:
        """Where a reader goes to check this rate: who declared it, and where.

        Deliberately not shaped like `PriceEntry.attribution`'s address. The
        two are read by the same reader and must not look alike.
        """
        return (f"declared by {self.declared_by} at {self.declaration_ref} "
                f"on {self.declared_on}")

    @property
    def starts(self) -> dt.date:
        return dt.date.fromisoformat(self.effective_from or self.declared_on)

    @property
    def ends(self) -> dt.date:
        if self.effective_until is None:
            return dt.date.max
        return dt.date.fromisoformat(self.effective_until)

    def covers(self, day: dt.date) -> bool:
        return self.starts <= day <= self.ends


def _require_stated_threshold(price: OperatorPrice) -> None:
    """The context-tiered refusal, and the two ways round it that are closed.

    A provider on `CONTEXT_TIERED_WITHOUT_THRESHOLD` prices in two columns and
    publishes no boundary. A declaration for one of its models is admitted only
    if it supplies what the page withheld:

    1. **At least two bands.** One band is the invented boundary — an assertion
       that the rate does not change, which the vendor's own page contradicts.
    2. **A threshold above zero.** `_validate_bands` already fixes the lowest
       band at zero, so the second band's floor *is* the boundary, and a second
       band starting at zero would be two rates in force at once.
    3. **An upper band that is actually dearer.** Two identical bands are
       equally consistent with having read the rate card and with having read
       one column twice, and nothing here can tell those apart; the second
       reading produces exactly the under-charge this gate exists to stop. A
       *cheaper* upper band is refused too — `Rate.min_input_tokens` means "re-
       rate the whole request at this band", so a cheaper one inverts the
       direction the shape asserts.

    **A genuinely flat contract rate is refused by this gate, and that is the
    intended outcome rather than a gap.** If an operator's card holds one
    number for a model the vendor prices in two columns, that is a discrepancy
    to settle with the vendor, not one for this table to resolve by picking a
    reading. Refusing costs a startup failure with a message naming the
    remedy. Admitting costs a ceiling that does not fire, discovered from a
    bill.

    This rule is **not** applied to `PriceEntry`. A vendor page says what it
    says, and a table that refused a published shape would be second-guessing
    the source it exists to transcribe.
    """
    reason = CONTEXT_TIERED_WITHOUT_THRESHOLD.get(price.provider)
    if reason is None:
        return
    label = f"{price.provider}/{price.model}"
    if len(price.tiers) < 2:
        raise OperatorPriceError(
            f"{label}: a single rate is refused for this provider. {reason}"
        )
    for lower, upper in zip(price.tiers, price.tiers[1:]):
        cheaper = (upper.input_usd_per_mtok < lower.input_usd_per_mtok
                   or upper.output_usd_per_mtok < lower.output_usd_per_mtok)
        dearer = (upper.input_usd_per_mtok > lower.input_usd_per_mtok
                  or upper.output_usd_per_mtok > lower.output_usd_per_mtok)
        if cheaper or not dearer:
            raise OperatorPriceError(
                f"{label}: the band at {upper.min_input_tokens} prompt tokens "
                f"is ({upper.input_usd_per_mtok}, {upper.output_usd_per_mtok}) "
                f"against ({lower.input_usd_per_mtok}, "
                f"{lower.output_usd_per_mtok}) below it. A long-context band "
                "must be dearer than the band beneath it on at least one rate "
                "and cheaper on neither. Two identical bands assert a boundary "
                "at which nothing changes, which is not a boundary and is "
                "what one column read twice looks like. A cheaper upper band "
                f"inverts the re-rating the shape asserts. {reason}"
            )


class OperatorPriceBook:
    """Every declaration one deployment supplies, validated as a set.

    **Constructed, not registered.** There is no module-level mutable table an
    import could add to. A declaration reaches a price lookup because a caller
    passed this object to it, which is what makes *"which prices were in
    force"* answerable from the call rather than from whichever imports ran.

    The set-level check is the one an individual declaration cannot make:
    two declarations for one model whose intervals overlap. `validate_schedule`
    already refuses that between vendor entries and the argument transfers
    unchanged — two rates in force on one day answers differently depending on
    which line was written first.
    """

    def __init__(self, prices: Sequence[OperatorPrice] = ()) -> None:
        by_key: dict[tuple[str, str], list[OperatorPrice]] = {}
        for price in prices:
            by_key.setdefault((price.provider, price.model), []).append(price)
        for key, group in by_key.items():
            ordered = sorted(group, key=lambda p: p.starts)
            for earlier, later in zip(ordered, ordered[1:]):
                if later.starts <= earlier.ends:
                    raise OperatorPriceError(
                        f"{key[0]}/{key[1]}: two declarations are in force on "
                        f"{later.starts}. A schedule with an overlap answers "
                        "differently depending on which line was written "
                        "first, so neither is used."
                    )
        self._by_key: Mapping[tuple[str, str], tuple[OperatorPrice, ...]] = {
            key: tuple(sorted(group, key=lambda p: p.starts))
            for key, group in by_key.items()
        }

    def get(self, provider: str, model: str) -> tuple[OperatorPrice, ...]:
        return self._by_key.get((provider, model), ())

    def declared_models(self) -> frozenset[tuple[str, str]]:
        """The enumerated accepting set this book adds, stated positively."""
        return frozenset(self._by_key)

    def __len__(self) -> int:
        return len(self._by_key)


#: A deployment that declares nothing. **Named rather than spelled `None`.**
#: An empty book and an absent one produce the same outcome here — a refusal,
#: which is the safe direction — so the distinction that matters is not at this
#: layer. It is at configuration, where `MODEL_PRICES_OPERATOR` is required
#: with no default so that *"the operator declares nothing"* is a thing somebody
#: wrote down rather than a key nobody set.
NO_OPERATOR_PRICES = OperatorPriceBook()


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


@dataclass(frozen=True)
class PricedSpend:
    """A spend figure and where its rate came from, as one value.

    **The two travel together because separating them is the defect.** A
    number that reads as authoritative because nothing beside it says otherwise
    is the same shape as the `0.0` that made *"nobody priced this"* and *"this
    cost nothing"* one state. `.usd` reaches the bare figure, and reaching it
    is an explicit act in the shape `Config.raw()` already establishes for
    FR-043's markings: possible, because these are numbers and have to be
    added up, and written down, which is the whole difference between an
    omission and a decision.

    There is deliberately no `__float__`. An implicit coercion would let a
    caller drop the provenance without writing anything, which is the one
    thing this type exists to prevent.
    """

    usd: float
    #: `PROVENANCE_VENDOR` or `PROVENANCE_OPERATOR`.
    provenance: str
    provider: str
    model: str
    #: Where a reader goes to check the rate this was computed at.
    attribution: str

    def __post_init__(self) -> None:
        if self.provenance not in PROVENANCES:
            raise CostTableError(
                f"{self.provenance!r} is not a declared provenance; the two "
                f"are {sorted(PROVENANCES)}"
            )

    @property
    def is_operator_declared(self) -> bool:
        """Stated positively, never as *"not vendor"*.

        A complement over a field that later grows a third provenance answers
        the wrong way round on the value nobody thought of, and the wrong way
        round here is the one that reads a declared rate as a published one.
        """
        return self.provenance == PROVENANCE_OPERATOR


def entry_in_force(
    provider: str,
    model: str,
    *,
    as_of: dt.date,
    operator_prices: OperatorPriceBook = NO_OPERATOR_PRICES,
) -> PriceEntry | OperatorPrice:
    """The one entry covering `as_of`, or a refusal (T063).

    **Enumerated, never complemented.** The lookup is an exact key into
    `PRICES`, then into the book. There is no prefix match, no alias
    resolution, no family fallback and no case folding: a rule of the form
    *"anything that looks close enough is priced"* fails open on the first
    model nobody anticipated, and that is precisely the model nobody priced.

    **The vendor table is consulted first and a declaration cannot displace
    it**, which is enforced twice over: `OperatorPrice` refuses to be
    constructed for a key `PRICES` holds, and this lookup would not reach it
    if one existed. Two enforcements because the first is the one that gives a
    good message and the second is the one that holds if the table grows a row
    after a book was built.

    **The book's default is empty and that is not a silent fallback.** An
    absent book produces a refusal, not a figure; the default that would be
    dangerous is one that fills in a number. Where *"the operator declared
    nothing"* has to be distinguished from *"nobody was asked"* is at
    configuration, and `MODEL_PRICES_OPERATOR` is required there with no
    default for exactly that reason.
    """
    require_provider(provider)
    entries: tuple[PriceEntry, ...] | tuple[OperatorPrice, ...] | None
    entries = PRICES.get((provider, model))
    if entries is None:
        entries = operator_prices.get(provider, model) or None
    if entries is None:
        known = sorted(m for p, m in PRICES if p == provider)
        declared = sorted(m for p, m in operator_prices.declared_models()
                          if p == provider)
        raise MissingPriceError(
            f"{provider}/{model or '<empty model name>'} has no cost entry. "
            "Nothing prices it, so its spend ceiling cannot be enforced and "
            "the call is refused rather than counted at zero. Priced for this "
            f"provider: {known or 'nothing — see costs.UNPRICED'}. Declared "
            f"by the operator for this provider: {declared or 'nothing'}. Add "
            "an entry with the address the rate was read at and the day it "
            "was read; do not supply a rate from memory. Where no page prices "
            "it, OD-27's operator declaration is the other route, and "
            "costs.OPERATOR_REACH says which absences it reaches."
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


def tier_for(entry: PriceEntry | OperatorPrice, *, input_tokens: int) -> Rate:
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
              output_tokens: Any, as_of: dt.date,
              operator_prices: OperatorPriceBook = NO_OPERATOR_PRICES,
              ) -> PricedSpend:
    """What one call cost, in USD, from the provider's own reported usage.

    `as_of` is required and has no default. A default of *today* would make
    the answer depend on the clock of whichever process asked, and on a
    scheduled boundary that is the difference between two rates the source
    states.

    **Returns `PricedSpend` rather than a float**, so that the provenance of
    the rate travels with the figure to every place the figure is recorded.
    A caller wanting the number writes `.usd`.
    """
    inputs = _require_token_count("input_tokens", input_tokens)
    outputs = _require_token_count("output_tokens", output_tokens)
    entry = entry_in_force(provider, model, as_of=as_of,
                           operator_prices=operator_prices)
    tier = tier_for(entry, input_tokens=inputs)
    return PricedSpend(
        usd=(inputs / 1_000_000 * tier.input_usd_per_mtok
             + outputs / 1_000_000 * tier.output_usd_per_mtok),
        provenance=entry.provenance,
        provider=provider,
        model=model,
        attribution=entry.attribution,
    )


def require_priceable(*, provider: str, model: str, as_of: dt.date,
                      operator_prices: OperatorPriceBook = NO_OPERATOR_PRICES,
                      ) -> str:
    """OD-27's startup gate. Returns a line naming the rate that will be used.

    **Why a preflight exists at all, when the price lookup already refuses.**
    Without one, a deployment configured against an unpriced model starts,
    accepts a session, builds a request, calls a provider — and *then* refuses,
    after the money for that call has been spent. FR-058's treatment is the one
    this follows: an unset bound *"MUST make startup fail loudly, naming what
    is missing"*, and the reason transfers exactly. Absence must not be
    discovered from the first turn.

    **It is also the only thing that catches a declaration written against the
    wrong address.** An operator whose contract prices *"GPT-5 mini"* and who
    declares that string as the identifier has configured a book that matches
    no request this runtime will ever make. Nothing at construction can see
    that, because the declaration is well formed. What sees it is asking, at
    startup, whether *the model in force* is priced — which is this function.
    The failure is loud and names both addresses, so the mismatch reads as a
    mismatch rather than as an unpriced model.

    The returned line is for the startup log, and it names the provenance and
    the rate. That matters most for a declared **zero**: a rate that disables
    the spend dimension is a thing to read before a session runs, not to infer
    afterwards from a total that never moved.
    """
    entry = entry_in_force(provider, model, as_of=as_of,
                           operator_prices=operator_prices)
    bands = "; ".join(
        f"from {tier.min_input_tokens} prompt tokens: "
        f"${tier.input_usd_per_mtok}/MTok in, ${tier.output_usd_per_mtok}/MTok out"
        for tier in entry.tiers
    )
    return (f"{provider}/{model} — {entry.provenance} rate in force on "
            f"{as_of}, {entry.attribution}. {bands}.")


def reservation_spend_usd(*, provider: str, model: str, tokens: int,
                          as_of: dt.date,
                          operator_prices: OperatorPriceBook = NO_OPERATOR_PRICES,
                          ) -> PricedSpend:
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

    **Returns `PricedSpend` for the same reason `price_usd` does, and the
    reason is not symmetry.** A reservation is normally released and replaced
    by the reconciled figure, so it looks like a number whose provenance does
    not survive. It survives on exactly the path this ledger is built for: a
    crash leaves the reservation outstanding and *it* becomes the durable
    total. A figure that can end up being the recorded one carries where it
    came from.
    """
    reserved = _require_token_count("tokens", tokens)
    entry = entry_in_force(provider, model, as_of=as_of,
                           operator_prices=operator_prices)
    tier = tier_for(entry, input_tokens=reserved)
    dearer = max(tier.input_usd_per_mtok, tier.output_usd_per_mtok)
    return PricedSpend(
        usd=reserved / 1_000_000 * dearer,
        provenance=entry.provenance,
        provider=provider,
        model=model,
        attribution=entry.attribution,
    )


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

# OD-27's coverage invariant, checked as the module loads rather than left to a
# test. Every recorded absence has to have been measured against the operator
# path — reachable, refused, or out of scope — because the failure this guards
# is a *fourth* absence being added later and quietly inheriting whichever
# answer the reader assumes. An absence with no answer is the gap that reads as
# an oversight, which is the thing `UNPRICED` exists to stop one level up.
if set(OPERATOR_REACH) != set(UNPRICED):
    raise CostTableError(
        f"OPERATOR_REACH answers {sorted(OPERATOR_REACH)} and UNPRICED "
        f"records {sorted(UNPRICED)}. Every recorded absence states whether "
        "an operator declaration reaches it; one that does not will be read "
        "as whichever answer the reader already had in mind."
    )
