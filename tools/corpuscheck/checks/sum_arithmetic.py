"""sum-arithmetic — a total shown with its components must equal them.

The corpus shows its working when it aggregates: "the component figures sum to
$18.15 ($7.59 + $10.56)". As with `ratio-arithmetic`, the redundancy makes an
error checkable with no external authority — and unlike a quoted measurement, a
wrong total cannot be defended as "a different metric", because the working is
right there.

Only the explicit `TOTAL (A + B [+ …])` form is recognised. A total stated
without its components is not checkable and is left to `numeric-provenance`.
"""

from __future__ import annotations

from ..corpus import Corpus
from ..figures import decimal_places, numeric_value, shown_sums, sum_holds
from ..registry import check
from ..report import ERROR, Violation


@check("sum-arithmetic", "A total shown with its components equals their sum.")
def run(corpus: Corpus, ctx: dict) -> list[Violation]:
    out: list[Violation] = []
    for doc in corpus.markdown():
        for lineno, masked in enumerate(doc.masked_lines, start=1):
            for shown in shown_sums(masked):
                if sum_holds(shown):
                    continue
                got = sum(numeric_value(t) for t in shown.terms)
                places = max(decimal_places(shown.total), 2)
                out.append(
                    Violation(
                        check="sum-arithmetic",
                        severity=ERROR,
                        path=doc.relpath,
                        line=lineno,
                        col=shown.start + 1,
                        found=shown.text,
                        expected=" + ".join(t.strip() for t in shown.terms)
                        + f" = {got:.{places}f}",
                        hint="the stated total and its listed components disagree",
                    )
                )
    return out
