"""register-range — "D-01 … D-19" must name the register's real last entry.

A failure class this corpus produces and nobody had named. Prose summarises a
register by its endpoints — "a decision register (D-01 … D-19)", "the five
owner decisions (OD-01 through OD-05)". Adding an entry to the register does
not touch the summary, so the summary quietly becomes an under-count, and a
reader who trusts it never looks for the entries past the stated end. It is the
same defect as a dangling identifier with the sign reversed: instead of citing
something that does not exist, it fails to cite something that does.

Cheap to check, because both halves are already in the file: the range's upper
bound, and the register itself.

**Amended 2026-08-03 — `tools/gen_claims.py` now writes most of these, and this
check is retained. The reason it is retained differs from
`catalog-line-count`'s, and the difference is the whole point.** A line count is
a bare fact: once the generator has written it the claim is complete, and the
check survives only as the thing that notices the generator was not run. A
register range is *not* always a bare fact. At the corpus's principal site —
`VERDICT.md` §SC-004 — the range sits inside a dated refresh log that names
which entry landed on which day and strikes the ranges it superseded. There the
digits are half the claim and the narrative is the other half, so a generator
that silently advanced `C-01…C-19` to `C-01…C-20` would leave a refresh log
that still ends at C-19 — and would have removed the only signal that the log
needed a new line. **That converts a detectable staleness into an undetectable
inconsistency, which is strictly worse than the hand-maintained version.**

So `gen_claims.py` writes only the ranges that stand alone, and reports the
narrated ones as `MANUAL` for a human. This rule is what fires at both kinds,
and at the narrated ones it is the *only* mechanism. Retiring it would leave
that site unguarded.
"""

from __future__ import annotations

import re

from ..corpus import Corpus
from ..figures import inside_spans, struck_spans
from ..registry import check
from ..report import WARNING, Violation
from .identifiers import _collect_definitions, _namespaces

# "D-01 … D-19", "D-01 through D-19", "D-01–D-19", "D-01 to D-19", "OD-01 -- OD-05"
_RANGE = re.compile(
    r"(?<![A-Za-z0-9-])([A-Z]{1,3})-(\d{2,3})\s*(?:\u2026|\.\.\.|\u2013|\u2014|--|-|through|to)\s*\1-(\d{2,3})(?![A-Za-z0-9-])"
)


@check("register-range", "A quoted register range ends at the register's real last entry.")
def run(corpus: Corpus, ctx: dict) -> list[Violation]:
    config = ctx["config"]
    defined = ctx.get("identifiers_defined")
    if defined is None:
        defined = _collect_definitions(corpus, _namespaces(config))
        ctx["identifiers_defined"] = defined

    maxima: dict[str, int] = {}
    for ns, ids in defined.items():
        if len(ids) < config["min_definitions"]:
            continue
        maxima[ns] = max(int(re.sub(r"\D", "", i)) for i in ids)

    out: list[Violation] = []
    for doc in corpus.markdown():
        for lineno, masked in enumerate(doc.masked_lines, start=1):
            if not masked.strip():
                continue
            found = list(_RANGE.finditer(masked))
            # A line listing several registers' ranges is a register summary
            # regardless of punctuation: "D-01…D-19, C-01…C-15, U-01…U-42".
            in_list = len({m.group(1) for m in found}) >= 2
            struck = struck_spans(masked)
            for m in found:
                ns, lo, hi = m.group(1), int(m.group(2)), int(m.group(3))
                if ns not in maxima or hi <= lo:
                    continue
                # A struck range is a superseded claim, kept visible on purpose.
                if inside_spans(struck, m.start(), m.end()):
                    continue
                if not _is_whole_register_claim(masked, m, in_list):
                    continue
                real = maxima[ns]
                if hi == real:
                    continue
                width = len(m.group(3))
                out.append(
                    Violation(
                        check="register-range",
                        severity=WARNING,
                        path=doc.relpath,
                        line=lineno,
                        col=m.start() + 1,
                        found=m.group(0),
                        expected=f"{ns}-{lo:0{len(m.group(2))}d} … {ns}-{real:0{width}d}",
                        hint=(
                            f"the {ns} register defines {len(defined[ns])} entries and runs to "
                            f"{ns}-{real:0{width}d}; this range "
                            + ("under-counts it" if hi < real else "over-counts it")
                        ),
                    )
                )
    return out


def _is_whole_register_claim(line: str, m: re.Match, in_list: bool) -> bool:
    """Distinguish "the register is D-01 … D-19" from "U-26 through U-29 are new".

    Prose describing a *subset* of a register is extremely common here and is
    not a defect. Two signals separate the two, and both are structural rather
    than lexical, because the lexical ones do not work — "U-01 through U-06 are
    the ones that cost real money" sits four words after the phrase "the whole
    register" and is still a subset.

      * the range starts at the register's first entry, **and**
      * it is either parenthesised or one of several ranges listed together.
    """
    if int(m.group(2)) != 1:
        return False
    if in_list:
        return True
    before = line[: m.start()].rstrip(" *~_")
    return before.endswith(("(", "[", "—", "–", ":"))
