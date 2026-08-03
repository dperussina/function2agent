"""numeric-provenance — a quoted measurement must exist in a findings document.

Findings under `specs/*/findings/` are the source of record for measured
numbers. Everything else quotes them. This check extracts measurement-shaped
figures from the quoting documents and asks whether the digit string occurs in
any finding.

Two severities, because two very different things fail here:

  error   The figure occurs in no finding *and* nowhere else in the repository
          outside the file quoting it. Nothing produced it. This is the
          transcription-error case and the stale-after-correction case.

  warning The figure occurs in no finding but does occur elsewhere — a claim
          that has been propagated between documents without ever touching a
          measurement.

Three shapes are exempt, because the figure is not a measurement this corpus
took and a findings document is therefore the wrong place to look for it.

  A **price**, not a spend. The per-unit suffix normally gives that away, but a
  pricing table states the denominator once in the column header, and a sentence
  that has already written "$0.08/hr" refers back to "the $0.08 line" with the
  unit left implicit. Both are read off the same line.

  An **externally attributed** figure — a third party's published benchmark,
  carrying the inline source link the house style requires. The link is the
  provenance; no finding of ours will ever contain it.

  A **total that shows its working** — `$24.82 ($24.73 + $0.09 + $0.0003)` — has
  provenance even though no single finding can report a figure spanning several
  of them. This one is narrow on purpose: the arithmetic must be right and every
  component must itself be authoritative.

**Amended 2026-08-03 — a match must be the whole number, for the kinds where
every digit is significant.** The lookup was a substring test, so `0.8961` was
satisfied by `0.89612` sitting in some finding and `$4.37` by `$14.37`. Enumerating
all ten thousand four-decimal values showed 576 of them accepted by a findings
corpus that reports none of them: a transcription error landing inside another
figure's digits read exactly like a figure with provenance. `ratio4` and
`money_cents` now require a standalone occurrence.

**Amended again, same date — `multiplier` was left unanchored, and an unanchored
substring is unanchored at *both* ends.** The reason for the exception was real:
a multiplier is the one kind this corpus legitimately quotes coarser than it
measured, so `2.9x` must go on being satisfied by a finding that writes `2.94x`,
and requiring a standalone match would reject it. But the same looseness made
`3.7x` satisfied by an authority writing `13.7x` — a different figure by an order
of magnitude, reading as sourced. So the left edge is now a hard word boundary
and only the right edge is open.

**The right edge is bounded too, and by rounding rather than by digit count.**
Left-anchoring alone still accepted `3.7x` from anything beginning `3.7`,
including `3.7999x`, which rounds to `4.0` and is not the same figure quoted
coarsely — it is a different figure sharing a prefix. A quoted multiplier is
therefore accepted only where some authority figure *rounds to it* at the
precision it was quoted to: within `_ROUNDING_ULPS` of the quoted value, in units
of the quoted value's last decimal place.

That bound is what surfaced the four `3.7×` claims in `research/07`,
`research/11`, `research/14` and `plan.md`. They had no multiplier provenance at
all: the only authority string they ever matched is `$3.7687`, the baseline arm's
total spend over ten solved tasks in E7, which is a dollar amount and not a
ratio. They are arithmetically sound — the two denominators are 220 and 60, and
220/60 is 3.67 — but they are derived in the consuming document, not quoted from
a finding, and the rule now says so.

**Amended 2026-08-03 — the lookup is typed, which is the thing none of the three
amendments above did.** Every one of them bounded *distance*: how far from the
quoted value an authority figure may sit, and from which side. Distance was never
the whole question. `$3.7687` was rejected for sitting 0.069 units away, so the
right answer arrived for the wrong reason and the same document writing `$3.72`
would have been accepted at 0.02 units — a dollar amount sourcing a ratio, which
is the defect that actually occurred. A multiplier claim is now matched against
the authority's *multiplicative figures*, parsed by `figures.multiplier_values`,
rather than against its text. `money_cents` is typed the same way and for the
same reason, though that hole had no live instance: see `_money_typed`.

Re-enumerated against the concatenated text of the 15 findings documents, all
four rules measured today by one implementation:

    rule                              0.0–99.9 (1000)   0.00–99.99 (10000)
    substring                                     166                  215
    left-anchored                                 148                  186
    left anchor + rounding                        130                  151
    typed                                          38                   49

Typing removes about 70% of what the distance bounds left, in both spaces and by
comparable proportions — an order of magnitude more than either of them removed.
The two middle rows sit 2 to 4 below the figures the amendment above recorded for
them; `tools/` carries no history, so that pass's exact anchor cannot be
recovered to reconcile the difference, and the rows are reported as re-measured
rather than as corrections. The direction and the magnitudes are unaffected.

The three cases the previous residue named, tested by injecting each into an
authority text and asking both rules, because two of them occur nowhere in the
findings and asking the live text would answer nothing:

    authority writes      left anchor + rounding      typed
    $3.7687                              rejected   rejected
    $3.72                                accepted   rejected
    figure 3.7                           accepted   rejected
    3.7×                                 accepted   accepted
    a factor of 3.7                      accepted   accepted

Three further confusions fall out with them, none of which was the reported
defect and all of which were reachable by exactly the same route: `§3.7`, `3.7%`
and `3.7 GB` all satisfied a claim of `3.7×` under the old rule and none does
now.

**Amended 2026-08-03 — a struck figure is a retracted claim, and this rule was
the only figure-reading check that did not know it.** The four `3.7×` claims
above were corrected in the house style: the multiplier struck, `220 against 60`
stated in its place, a dated note beside it. The rule kept firing, because it
read the struck text as live — so the only way to satisfy it would have been to
delete the retraction, which is exactly the outcome `figures.struck_spans` exists
to prevent and which `inventory`, `register-ranges` and `dry-run-verdict` already
avoid. A figure whose start offset falls inside a `~~…~~` span is now skipped.
**The exemption is narrow and cannot be used to launder a live figure**: the
strike is visible in the rendered document, so hiding an unsourced number behind
it means printing it struck, which is a retraction and not a claim.
"""

from __future__ import annotations

import re

from ..corpus import Corpus, Document, ROLE_AUTHORITY, ROLE_CONSUMER
from ..figures import (
    Figure,
    column_of,
    digit_key,
    digit_neighbours,
    externally_attributed,
    extract,
    inside_spans,
    is_table_delimiter,
    multiplier_values,
    rate_columns,
    rate_keys,
    shown_sums,
    struck_spans,
    sum_holds,
)
from ..registry import check
from ..report import ERROR, WARNING, Violation


def _derived_totals(doc: Document, authority_text: str) -> set[str]:
    """Totals the document derives, in the open, from authoritative components.

    A program total spanning several findings cannot appear in any one of them,
    so requiring it to is a rule gap rather than a missing source. The escape is
    narrow on purpose: the document must show the addition, the addition must be
    right, and every component must itself be authoritative.
    """
    out: set[str] = set()
    for masked in doc.masked_lines:
        for shown in shown_sums(masked):
            if not sum_holds(shown):
                continue
            if not all(digit_key(t) in authority_text for t in shown.terms):
                continue
            out.add(digit_key(shown.total))
    return out


def _rate_columns_by_line(doc: Document) -> dict[int, set[int]]:
    """For each table-body line, the columns whose header declares a rate."""
    out: dict[int, set[int]] = {}
    header: str | None = None
    active: set[int] = set()
    previous = ""
    for i, masked in enumerate(doc.masked_lines, start=1):
        if "|" not in masked:
            header, active, previous = None, set(), masked
            continue
        if is_table_delimiter(masked):
            header = previous
            active = rate_columns(header)
        elif header is not None and active:
            out[i] = active
        previous = masked
    return out


#: Kinds whose every digit is significant, so a match must be the whole number.
#: `0.8961` occurring inside `0.89612`, and `$4.37` inside `$14.37`, are not
#: occurrences of the quoted figure — but a substring test says they are, and
#: that test was accepting 576 four-decimal values the findings never report.
#:
#: `money_cents` is listed for the record and no longer routed here: `_money_typed`
#: supersedes `_standalone` for it and is strictly stronger, anchoring the left
#: edge on a `$` rather than on "not a digit or a dot". Exactness is not lost by
#: the change, only subsumed.
_EXACT_KINDS = frozenset({"ratio4", "money_cents"})

#: Kinds a document may legitimately quote to fewer decimal places than the
#: finding measured them to, so an exact match is the wrong test. A multiplier is
#: the corpus's one such kind: `2.9x` from a measured `2.94x` is the same figure
#: rounded, whereas a four-decimal recall or a cent-precise cost is quoted whole
#: or is a different number.
_ROUNDED_KINDS = frozenset({"multiplier"})

#: How far an authority figure may sit from a figure quoted from it, in units of
#: the quoted figure's last decimal place.
#:
#: 0.5 is not a tuning knob — it is what "quoted to this many places" means, and
#: it is the same constant `ratio-arithmetic` and `sum-arithmetic` already use for
#: the same reason. A digit-count cap was the obvious alternative and is worse: it
#: would accept `3.7x` from `3.79x` (which rounds to 3.8) and reject it from
#: `3.7001x` (which does not), getting both cases the wrong way round. Half a unit
#: in the last place gets both right, and it answers the question a bare
#: left-anchor cannot — `3.7999x` is rejected, because it is not `3.7x` measured
#: more precisely, it is `4.0x`.
_ROUNDING_ULPS = 0.5


def _standalone(key: str, text: str) -> bool:
    return re.search(r"(?<![0-9.])" + re.escape(key) + r"(?![0-9])", text) is not None


def _money_typed(key: str, text: str) -> bool:
    """A spend claim must be sourced from a figure the authority marks as money.

    The symmetric case to the multiplier hole: `_standalone` asked only whether
    the digit string stood alone, so a bare `0.53` — a ratio, a turn count, a
    share — satisfied a claim of `$0.53`. Requiring the `$` is the whole rule,
    because this corpus never writes a spend without one.

    **This one had no live instance, and the distinction matters.** Every one of
    the 118 sourced `money_cents` claims already resolves to a `$`-prefixed
    occurrence; reverting this function to `_standalone` moves the corpus not at
    all. It is closed here because it is reachable, not because it fired, and
    the reachability is pinned by fixture rather than by a corpus violation —
    which is the only honest way to hold a rule that nothing currently needs.

    A thousands separator needs no handling here: `extract` already emits the
    grouped spelling as an alias, so `$1,204.50` reaches this function as both
    `1204.50` and `1,204.50` and `_authoritative` tries each.
    """
    return re.search(r"\$\s?" + re.escape(key) + r"(?![0-9])", text) is not None


def _multiplier_typed(key: str, values: tuple[float, ...]) -> bool:
    """Whether some authority *multiplier* rounds to `key` at `key`'s precision.

    Two conditions, and until 2026-08-03 only the second was checked.

    **Type.** The candidate must be a value the authority document itself states
    multiplicatively — suffixed with `×`, named as a factor or a ratio, or
    written as a reciprocal. `figures.multiplier_values` decides that, and it
    decides it by *parsing the authority side into figures* rather than by
    running the claim's digits through the authority's text. That is the whole
    change: a digit-string lookup cannot tell `2.20×` from `$2.20` from `§2.20`,
    because the thing that distinguishes them is never part of the digits.

    **Magnitude.** Within `_ROUNDING_ULPS` of the quoted value, in units of the
    quoted value's last decimal place — unchanged, and it is what still lets
    `2.9x` be satisfied by a measured `2.94×` while `3.7999×` is rejected.

    Parsing the authority side also retires the left-anchor regex, and gets the
    same answer for a better reason: `3.7` was previously not-found-inside-`13.7`
    by a lookbehind, and is now simply a different number from 13.7.
    """
    try:
        claimed = float(key)
    except ValueError:
        return False
    places = len(key.split(".", 1)[1]) if "." in key else 0
    tolerance = _ROUNDING_ULPS * 10.0**-places
    return any(abs(value - claimed) <= tolerance for value in values)


def _authoritative(fig: Figure, authority_text: str, mult: tuple[float, ...]) -> bool:
    if fig.kind in _ROUNDED_KINDS:
        keys = (fig.key, *fig.aliases)
        return any(k and _multiplier_typed(k, mult) for k in keys)
    if fig.kind == "money_cents":
        hit = _money_typed
    elif fig.kind in _EXACT_KINDS:
        hit = _standalone
    else:
        hit = lambda k, t: k in t  # noqa: E731
    if hit(fig.key, authority_text):
        return True
    return any(alias and hit(alias, authority_text) for alias in fig.aliases)


def _nearest(fig: Figure, authority_text: str, limit: int = 3) -> list[str]:
    if fig.kind not in {"ratio4", "money_cents", "percent_decimal"}:
        return []
    near = sorted(n for n in digit_neighbours(fig.key) if n in authority_text)
    return near[:limit]


@check(
    "numeric-provenance",
    "A measurement quoted outside findings/ must appear in a findings document.",
)
def run(corpus: Corpus, ctx: dict) -> list[Violation]:
    config = ctx["config"]
    index = ctx["search"]

    authority_docs = corpus.by_role(ROLE_AUTHORITY)
    if not authority_docs:
        ctx["skip"]("numeric-provenance", "no authority documents matched specs/*/findings/*.md")
        return []
    authority_text = "\n".join(d.text for d in authority_docs)
    authority_paths = {d.relpath for d in authority_docs}
    # Typed multiplicative figures, parsed once. The multiplier lookup runs
    # against these rather than against the text, so a dollar amount cannot
    # supply provenance for a ratio.
    authority_multipliers = multiplier_values(authority_text)

    kinds = set(config["numeric_kinds"])
    allow = config["numeric_allow"]
    violations: list[Violation] = []

    for doc in corpus.markdown(ROLE_CONSUMER):
        derived = _derived_totals(doc, authority_text)
        rates = _rate_columns_by_line(doc)
        for i, masked in enumerate(doc.masked_lines, start=1):
            if not masked.strip():
                continue
            priced = rate_keys(masked)
            struck = struck_spans(masked)
            # Masking blanks URLs, which is exactly what this test looks for.
            sourced = externally_attributed(doc.lines[i - 1])
            for fig in extract(masked, i, kinds):
                if fig.key in allow or fig.literal in allow:
                    continue
                if inside_spans(struck, fig.col - 1, fig.col - 1):
                    continue
                if _authoritative(fig, authority_text, authority_multipliers):
                    continue
                if fig.key in derived:
                    continue
                # An externally attributed figure. The docstring above declares
                # this exemption for *any* figure this corpus did not measure,
                # and it was wired to `money_cents` alone — which went unnoticed
                # only because the untyped multiplier lookup was matching bare
                # digits and exempting these by accident. Typing removed the
                # accident, so the declared exemption has to do the work.
                if sourced and fig.kind in {"money_cents", "multiplier"}:
                    continue
                if fig.kind == "money_cents" and (
                    fig.key in priced
                    or column_of(masked, fig.col) in rates.get(i, ())
                ):
                    continue

                elsewhere = [
                    p
                    for p in index.where(fig.key)
                    if p != doc.relpath and p not in authority_paths
                ]
                near = _nearest(fig, authority_text)

                if elsewhere:
                    severity = WARNING
                    hint = "also in: " + index.summarise(elsewhere)
                else:
                    severity = ERROR
                    hint = "appears nowhere else in the corpus"
                if near:
                    hint += "; nearest authoritative figure(s): " + ", ".join(near)

                violations.append(
                    Violation(
                        check="numeric-provenance",
                        severity=severity,
                        path=doc.relpath,
                        line=fig.line,
                        col=fig.col,
                        found=f"{fig.literal}  ({fig.kind})",
                        expected="the same figure in some specs/*/findings/*.md",
                        hint=hint,
                    )
                )
    return violations
