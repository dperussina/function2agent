"""ratio-arithmetic — a fraction and the rate quoted beside it must agree.

The corpus's house style is to quote a count and its rate together: "60/69 =
0.8696", "15 of 69 endpoints (21.7%)", "**0.9987** (16,655 of 16,677)". That
redundancy is a gift, because it makes a transcription error in *either* half
mechanically visible with no external authority at all. This is the only check
that can fail on a findings document, and it should be able to: the numerator,
the denominator and the rate are three statements of one fact.

**Pairing is deliberately strict.** A first attempt paired any rate within 60
characters of any fraction and produced sixteen violations, all of them false —
"route recall is 0.8961 (69 of 77) at precision 1.0000" pairs `69 of 77` with
the *precision*, and "the tool arm sits at 27 of 41 against a calibration band
of 0.25–0.85" pairs a count with a band edge. Only three constructions are
recognised now, all of which bind the two halves syntactically rather than by
distance:

    A/B = R                     an explicit equation
    A of B [<=4 words] (R)      the rate parenthesised right after the count
    R (A of B)                  the count parenthesised right after the rate

Anything looser is not checked rather than guessed at. A rate that belongs to a
count three clauses away is a real pairing this check misses, and that is the
correct trade: the cost of a false positive here is that the next person turns
the whole tool off.
"""

from __future__ import annotations

import re

from ..corpus import Corpus
from ..registry import check
from ..report import ERROR, Violation

_FRACTION = r"(?<![\d./$])(\d[\d,]*)\s*(?:/|\s+of\s+)\s*(\d[\d,]*)(?![\d,./])"
#: One decimal place is enough for a percentage ("21.7%") but not for a bare
#: ratio, where the corpus always writes four and a two-decimal number is far
#: more likely to be money or a version fragment.
_RATE_BODY = r"[*~≈\s]*(\d+\.\d{1,4})\s*(%?)[*~\s]*"
_MIN_DECIMALS_BARE = 2

#: A/B = 0.8696   or   A of B = 87%
_EQUATION = re.compile(_FRACTION + r"\s*(?:=|is|of)?\s*=\s*" + _RATE_BODY)

#: A of B [up to four ordinary words] (0.8696)   — the words are things like
#: "endpoints", "Python route handlers", "TypeScript callables".
_COUNT_THEN_RATE = re.compile(
    _FRACTION + r"(?:\s+[A-Za-z][A-Za-z*`'-]*){0,4}[,;\s*~]*\(" + _RATE_BODY + r"\)"
)

#: 0.9987 (16,655 of 16,677)
_RATE_THEN_COUNT = re.compile(
    r"(?<![\d.$])(\d+\.\d{1,4})\s*(%?)[*~\s]*\((?:[A-Za-z][A-Za-z*`'-]*\s+){0,3}"
    + _FRACTION
    + r"\s*\)"
)


def _num(s: str) -> int:
    return int(s.replace(",", ""))


def _tolerance(text: str) -> float:
    """Half a unit in the last quoted decimal place, which is what rounding costs."""
    if "." in text:
        return 0.5 * 10 ** -len(text.split(".", 1)[1])
    return 0.5


def _check_pair(num: int, den: int, rate_text: str, is_percent: bool) -> str | None:
    """Return the expected rendering when the pair disagrees, else None."""
    if den == 0 or num > den:
        # Not a rate: a status-code pair (404/405), a date, a score of one thing
        # against another (27/27 against 26/27). Skip rather than guess.
        return None
    if not is_percent and len(rate_text.split(".", 1)[1]) < _MIN_DECIMALS_BARE:
        return None
    actual = num / den
    quoted = float(rate_text)
    if is_percent:
        if abs(quoted - actual * 100.0) <= _tolerance(rate_text):
            return None
        return f"{actual * 100:.2f}".rstrip("0").rstrip(".") + "%"
    if abs(quoted - actual) <= _tolerance(rate_text):
        return None
    return f"{actual:.4f}"


@check("ratio-arithmetic", "A count and the rate quoted beside it must be consistent.")
def run(corpus: Corpus, ctx: dict) -> list[Violation]:
    violations: list[Violation] = []

    for doc in corpus.markdown():
        for lineno, masked in enumerate(doc.masked_lines, start=1):
            if "/" not in masked and " of " not in masked:
                continue

            for rx, order in (
                (_EQUATION, "count-first"),
                (_COUNT_THEN_RATE, "count-first"),
                (_RATE_THEN_COUNT, "rate-first"),
            ):
                for m in rx.finditer(masked):
                    if order == "count-first":
                        a, b, rate, pct = m.group(1), m.group(2), m.group(3), m.group(4)
                    else:
                        rate, pct, a, b = m.group(1), m.group(2), m.group(3), m.group(4)
                    expected = _check_pair(_num(a), _num(b), rate, pct == "%")
                    if expected is None:
                        continue
                    violations.append(
                        Violation(
                            check="ratio-arithmetic",
                            severity=ERROR,
                            path=doc.relpath,
                            line=lineno,
                            col=m.start() + 1,
                            found=" ".join(m.group(0).split()),
                            expected=f"{a}/{b} = {expected}",
                            hint="either the count or the rate is mistyped; "
                            "the two disagree by more than rounding",
                        )
                    )
    return violations
