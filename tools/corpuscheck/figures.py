"""Extracting measurement-shaped numbers from prose.

The provenance check rests entirely on this module deciding what counts as a
quoted measurement. Get it too wide and every version string and page count
becomes a violation; get it too narrow and the check silently passes, which is
the failure mode this whole tool exists to prevent. The shapes below were
chosen by reading what the corpus actually writes when it quotes a result.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Figure:
    kind: str
    #: What we look for in an authority document. Digits only, no unit — the
    #: rule is "does this digit string occur in a findings document", which is
    #: cheap to explain and hard to get subtly wrong.
    key: str
    #: Alternative keys that mean the same measurement written another way.
    aliases: tuple[str, ...]
    #: The text as it appears, for the violation message.
    literal: str
    line: int
    col: int


# A score or rate reported to four decimal places. The corpus's house style for
# precision/recall/F1, and by far the highest-signal shape. The integer part is
# capped at three digits because nothing this corpus measures is in the
# thousands and a longer one is always an identifier — `Preprints 202606.0238`.
_RATIO4 = re.compile(r"(?<![\d.])(\d{1,3}\.\d{4})(?!\d)")

# Money with cents. Whole-dollar figures are deliberately excluded: $120 and
# $300 are authorized budgets, not measurements, and they dominate by volume.
_MONEY_CENTS = re.compile(r"\$\s?(\d[\d,]*\.\d{2})(?!\d)")

# A price, not a spend. research/05 and research/13 survey vendor pricing and
# quote dozens of these; every one is external and none belongs in a findings
# document. The per-unit suffix is what distinguishes "we spent $2.49" from
# "they charge $2.49/task".
_PER_UNIT = re.compile(
    r"^\s*(?:/\s?\d|/[A-Za-z]|\s?per\s+[\w-]|\s?(?:each|apiece)\b)", re.IGNORECASE
)

# The same distinction, one layer out. A pricing *table* states the denominator
# once in the column header — "| Tool | Cost / 1k calls |" — and then writes bare
# figures in the cells, so `_PER_UNIT` never sees it. The denominator must be
# explicit: a slash followed by a quantity, or the word "per". A header cell
# reading "Model spend" is not a rate and must keep its figures checked.
_RATE_HEADER = re.compile(
    r"/\s*\d[\w]*(?:\s+[\w-]+)?"  # "/ 1k calls", "/1M tokens"
    r"|\bper\s+[\d\w-]+"  # "per call", "per 1k tokens"
    r"|\b(?:cost|price|rate)\s*/\s*\w",  # "Cost / call"
    re.IGNORECASE,
)

# "5.0×", "40×", "9.3x". The corpus uses the multiplication sign; the ASCII
# form is accepted so a check does not turn off when someone types 'x'.
#
# The sign must be **adjacent** to the digits, because a space in front of it
# turns it from a suffix into the binary operator. Counted: seven spaced
# occurrences corpus-wide, of which two are in the findings — `0.9109 × 0.9475 =
# 0.8630` and `5.059 × 0.8630` in finding 014 — and five in consumer documents,
# the `5 × 5 × 5 = 125 model calls` cap arithmetic and research/11's `0.5 × A0`
# success condition. Seven operators, no multiplier among them. The space was
# admitting only noise, and on the authority side it was putting an *operand* of
# somebody's arithmetic into the accept pool as though the finding had measured
# it: that is how `0.9475` would have become provenance for a ratio claim.
_MULTIPLIER = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)[×x](?![\w])")

# --- the same question asked of an authority document ------------------------
#
# `_MULTIPLIER` says what a *quoted* multiplier looks like. These say what a
# *measured* one looks like in a findings document, which is a different and
# wider question: a finding states the same multiplicative fact in four shapes,
# and `multiplier_values` is what lets the provenance lookup compare kind to
# kind instead of comparing digits to digits.
#
# Each form below has a counted site in the 15 findings documents. The two that
# were surveyed and deliberately left out are recorded with their counts in
# `multiplier_values`, because an accept-list entry that never matches reads as
# coverage and is not.

# "a factor of 2.6", "a factor of 1.0000". `\s+` rather than a literal space
# because finding 004 wraps the phrase: "by a factor \n of 2.6".
_FACTOR_OF = re.compile(r"\bfactor\s+of\s+~?\*{0,2}(\d+(?:\.\d+)?)", re.IGNORECASE)

# "a ratio of 2.73×". One site, and its value is also suffixed, so this form
# adds nothing today; it is here because the corpus writes it and a future
# "a ratio of 2.73" with no sign is the same statement.
_RATIO_OF = re.compile(r"\bratio\s+of\s+~?\*{0,2}(\d+(?:\.\d+)?)", re.IGNORECASE)

# "1/35th of the cost" — the reciprocal, and the *only* authority form behind
# the corpus's eight `35×` claims. Nothing else in any finding states that
# figure multiplicatively, so a typed rule that missed this shape would strip
# provenance from eight correct claims.
#
# It contributes the **denominator**, which looks wrong and is not: "1/35th of
# the cost" and "35× cheaper" are the same measured fact written from opposite
# ends, and 35 is the magnitude both of them carry. A reciprocal is the one form
# here whose captured digits are not the value a document would quote.
_RECIPROCAL = re.compile(r"(?<![\w.])1\s?/\s?(\d+(?:\.\d+)?)\s?(?:th|st|nd|rd)\b")

_MULTIPLICATIVE = (_MULTIPLIER, _FACTOR_OF, _RATIO_OF, _RECIPROCAL)


def multiplier_values(text: str) -> tuple[float, ...]:
    """Every value `text` states as a multiplicative quantity.

    Four forms, all counted against the 15 findings documents: 160 suffixed
    (`2.20×`, `40x`), 8 `factor of N`, 1 `ratio of N`, 1 reciprocal `1/35th` —
    170 occurrences, 57 of them distinct.

    Two surveyed forms are **excluded**, and both exclusions are measured rather
    than assumed:

    `N-fold` — zero occurrences. An accept pattern with no site cannot be
    falsified by any fixture, which is the shape of safeguard this repository
    has already recorded as reading like a satisfied one.

    `N times` — ten occurrences, of which **nine are counts of things, not
    multiples**: "69 times out of 69", "16 times", "9 times", "3 times out of
    3", and "35 times", which finding 003 carries a dated correction against
    saying in terms that it is "a count of matching source lines". The tenth,
    "40 times the input context", is genuinely multiplicative and is redundant:
    finding 003 writes `40×` six times, so admitting the form adds **zero**
    values to the pool. Admitting it would let a count of source lines supply
    provenance for a cost multiplier, which is the same type confusion as
    letting a dollar amount do it.
    """
    out: list[float] = []
    for rx in _MULTIPLICATIVE:
        for m in rx.finditer(text):
            try:
                out.append(float(m.group(1)))
            except ValueError:
                continue
    return tuple(out)


# Percentages carrying a decimal. "70%" and "100%" are rhetorical or trivially
# round; "53.6%" is a measurement.
_PERCENT_DECIMAL = re.compile(r"(?<![\d.])(\d+\.\d+)\s?%")

# "60/69", "27/27", and the spelled form "60 of 69".
_FRACTION_SLASH = re.compile(r"(?<![\d./])(\d[\d,]*)\s?/\s?(\d[\d,]*)(?![\d./])")
_FRACTION_OF = re.compile(r"(?<![\d,.])(\d[\d,]*)\s+of\s+(\d[\d,]*)(?![\d,.])")

# Shapes that look like a figure but never are.
_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_SEMVER = re.compile(r"\bv?\d+\.\d+\.\d+\b")
_SECTION = re.compile(r"§\s?[\d.]+")
_CITATION_ID = re.compile(
    r"(?:arXiv|doi|preprints?|RFC|ISBN|ISSN)[:\s]\s?[\d./]+", re.IGNORECASE
)
_ISO_DURATION = re.compile(r"\b\d{4}-\d{2}\b")

_SUPPRESS = (_DATE, _SEMVER, _SECTION, _CITATION_ID, _ISO_DURATION)


def _suppressed_spans(line: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    for rx in _SUPPRESS:
        spans.extend((m.start(), m.end()) for m in rx.finditer(line))
    return spans


def _inside(spans: list[tuple[int, int]], start: int, end: int) -> bool:
    return any(s <= start and end <= e for s, e in spans)


def _denorm(num: str) -> str:
    return num.replace(",", "")


def _trim_zeros(value: str) -> str:
    if "." not in value:
        return value
    return value.rstrip("0").rstrip(".") or "0"


def _ratio_aliases(value: str) -> tuple[str, ...]:
    """0.8961 also reads as 89.61% and as 0.8961 with trailing zeros trimmed.

    Every alias here is **lossless**, and that is a rule rather than an accident.
    A one-decimal percentage used to be emitted as well, and it made the last
    digit of a four-decimal ratio unguarded: finding 004 writes `89.6`, so
    `0.8960` through `0.8965` all had provenance and only `0.8966` upward was
    reported. Six of the ten values a transcription error can produce in the most
    quoted figure in this corpus read as sourced. Removing it reports nothing on
    the current corpus, because the findings that are cited as percentages are
    cited to two decimals.

    `1.0000` still reaches `100` — `.4f` and `.2f` both trim to it — so the case
    the coarse form was added for never needed it.
    """
    out = {_trim_zeros(value)}
    try:
        pct = float(value) * 100.0
    except ValueError:
        return tuple(sorted(out))
    out.add(_trim_zeros(f"{pct:.4f}"))
    out.add(_trim_zeros(f"{pct:.2f}"))
    return tuple(sorted(out))


def _percent_aliases(value: str) -> tuple[str, ...]:
    out = {_trim_zeros(value)}
    try:
        frac = float(value) / 100.0
    except ValueError:
        return tuple(sorted(out))
    out.add(f"{frac:.4f}")
    out.add(_trim_zeros(f"{frac:.4f}"))
    return tuple(sorted(out))


def extract(line: str, lineno: int, kinds: set[str]) -> list[Figure]:
    """Pull every measurement-shaped token out of one already-masked line."""
    figures: list[Figure] = []
    dead = _suppressed_spans(line)

    def emit(kind: str, m: re.Match, key: str, aliases: tuple[str, ...], literal: str) -> None:
        if _inside(dead, m.start(), m.end()):
            return
        figures.append(
            Figure(
                kind=kind,
                key=key,
                aliases=aliases,
                literal=literal,
                line=lineno,
                col=m.start() + 1,
            )
        )

    if "ratio4" in kinds:
        for m in _RATIO4.finditer(line):
            v = m.group(1)
            emit("ratio4", m, v, _ratio_aliases(v), v)

    if "money_cents" in kinds:
        for m in _MONEY_CENTS.finditer(line):
            if _PER_UNIT.match(line[m.end() : m.end() + 24]):
                continue
            v = _denorm(m.group(1))
            emit("money_cents", m, v, (m.group(1),), f"${m.group(1)}")

    if "multiplier" in kinds:
        for m in _MULTIPLIER.finditer(line):
            v = m.group(1)
            emit("multiplier", m, v, (_trim_zeros(v),), m.group(0).strip())

    if "percent_decimal" in kinds:
        for m in _PERCENT_DECIMAL.finditer(line):
            v = m.group(1)
            emit("percent_decimal", m, v, _percent_aliases(v), f"{v}%")

    if "fraction" in kinds:
        for m in _FRACTION_SLASH.finditer(line):
            a, b = _denorm(m.group(1)), _denorm(m.group(2))
            emit("fraction", m, f"{a}/{b}", (f"{a} of {b}", f"{a} / {b}"), m.group(0))
        for m in _FRACTION_OF.finditer(line):
            a, b = _denorm(m.group(1)), _denorm(m.group(2))
            emit("fraction", m, f"{a}/{b}", (f"{a} of {b}", f"{a} / {b}"), m.group(0))

    return figures


_STRUCK = re.compile(r"~~(?:(?!~~).)+~~", re.DOTALL)


def struck_spans(line: str) -> list[tuple[int, int]]:
    """Character ranges inside `~~…~~`.

    The house convention is that a superseded claim stays visible with a dated
    note beside it rather than being deleted. A check that reads the struck text
    as a live claim therefore punishes the convention, and the only way to
    satisfy it would be to delete the history.
    """
    return [(m.start(), m.end()) for m in _STRUCK.finditer(line)]


def inside_spans(spans: list[tuple[int, int]], start: int, end: int) -> bool:
    return any(s <= start and end <= e for s, e in spans)


def table_cells(line: str) -> list[tuple[int, int, str]]:
    """`(start, end, text)` for each pipe-delimited cell in one table row.

    Offsets are into the original line so a figure's column can be recovered
    from the column it was found at.
    """
    if "|" not in line:
        return []
    spans: list[tuple[int, int, str]] = []
    pos = 0
    for part in line.split("|"):
        spans.append((pos, pos + len(part), part))
        pos += len(part) + 1
    if line.lstrip().startswith("|"):
        spans = spans[1:]
    if line.rstrip().endswith("|") and spans:
        spans = spans[:-1]
    return spans


def is_table_delimiter(line: str) -> bool:
    body = line.strip()
    return bool(body) and "|" in body and "---" in body and set(body) <= set("|:- \t")


def rate_columns(header: str) -> set[int]:
    """Indices of header cells that declare a per-unit denominator."""
    return {
        i
        for i, (_, _, text) in enumerate(table_cells(header))
        if _RATE_HEADER.search(text)
    }


def column_of(line: str, col: int) -> int | None:
    """Which table column a 1-based character offset falls in, if any."""
    for i, (start, end, _) in enumerate(table_cells(line)):
        if start <= col - 1 < end:
            return i
    return None


# --- figures this corpus did not measure -------------------------------------
#
# `numeric-provenance` asks where a measurement came from. A vendor's list price
# and a third party's published benchmark are not measurements this corpus took,
# so a findings document is the wrong place to look for them. Two signals say so
# on the line itself, which is where the house style already puts provenance.

# An inline external link. The house style in research/ puts the source
# immediately after the claim it supports, so a URL on the line is the
# attribution this check is asking for — from the right place, since a findings
# document is not where a third party's published number would ever be.
_EXTERNAL_LINK = re.compile(r"<https?://|\]\(https?://", re.IGNORECASE)


def rate_keys(line: str) -> set[str]:
    """Digit keys of money on this line that carries a per-unit denominator.

    `extract` already drops "$0.08/hr". It cannot drop the sentence's later
    back-reference to "the $0.08 line", which is the same price with the unit
    left implicit. Naming the rate once on the line is enough.
    """
    out: set[str] = set()
    for m in _MONEY_CENTS.finditer(line):
        if _PER_UNIT.match(line[m.end() : m.end() + 24]):
            out.add(_denorm(m.group(1)))
    return out


def externally_attributed(line: str) -> bool:
    """Whether the line carries an inline external source link."""
    return bool(_EXTERNAL_LINK.search(line))


# --- totals that show their working -----------------------------------------
#
# "the component figures sum to $18.15 ($7.59 + $10.56)". Two checks read this
# shape: `sum-arithmetic` verifies it, and `numeric-provenance` treats a total
# whose working is shown and correct as derived rather than unsourced.

_SUM_NUM = r"\$?\s?\d[\d,]*(?:\.\d+)?"
_SUM = re.compile(
    r"(?<![\w.])(" + _SUM_NUM + r")[*~\s]*\(\s*[*~]*(" + _SUM_NUM + r")"
    r"((?:[*~\s]*\+[*~\s]*" + _SUM_NUM + r")+)[*~\s]*\)"
)
_SUM_TERM = re.compile(_SUM_NUM)


@dataclass(frozen=True)
class ShownSum:
    total: str
    terms: tuple[str, ...]
    start: int
    text: str


def shown_sums(line: str) -> list[ShownSum]:
    if "+" not in line or "(" not in line:
        return []
    out: list[ShownSum] = []
    for m in _SUM.finditer(line):
        terms = tuple([m.group(2)] + _SUM_TERM.findall(m.group(3)))
        if len(terms) < 2:
            continue
        out.append(
            ShownSum(
                total=m.group(1),
                terms=terms,
                start=m.start(),
                text=" ".join(m.group(0).split()),
            )
        )
    return out


def numeric_value(text: str) -> float:
    return float(text.replace("$", "").replace(",", "").strip())


def decimal_places(text: str) -> int:
    body = text.replace("$", "").replace(",", "").strip()
    return len(body.split(".", 1)[1]) if "." in body else 0


def sum_holds(shown: ShownSum) -> bool:
    total = numeric_value(shown.total)
    tol = 0.5 * 10 ** -max(decimal_places(shown.total), 0)
    return abs(sum(numeric_value(t) for t in shown.terms) - total) <= tol


def digit_key(text: str) -> str:
    """The digits-only form the provenance check matches against findings."""
    return text.replace("$", "").replace(",", "").strip()


def digit_neighbours(value: str) -> set[str]:
    """Digit strings one single-character substitution or transposition away.

    A stale-after-correction figure and its corrected form are usually one digit
    apart, so naming the near neighbour turns "this number is unsupported" into
    "this number is probably 0.8961 mistyped".
    """
    out: set[str] = set()
    chars = list(value)
    for i, ch in enumerate(chars):
        if not ch.isdigit():
            continue
        for d in "0123456789":
            if d == ch:
                continue
            out.add("".join(chars[:i] + [d] + chars[i + 1 :]))
    for i in range(len(chars) - 1):
        if chars[i].isdigit() and chars[i + 1].isdigit() and chars[i] != chars[i + 1]:
            swapped = chars[:]
            swapped[i], swapped[i + 1] = swapped[i + 1], swapped[i]
            out.add("".join(swapped))
    out.discard(value)
    return out
