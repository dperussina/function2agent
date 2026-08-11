"""count-versus-range — "thirty-one owner decisions (OD-01 through OD-31)".

A sentence that states a register's size *and* its bounds states the same fact
twice, and the two halves rot independently. `specs/001-discovery-validation/plan.md`
records the mechanism against itself: the parenthesised range is written by
`gen_claims.py` and advanced the day each entry lands, while the spelled count
beside it is prose a reader has to notice. The header contradicted itself two
lines apart across two entries — OD-30 on 2026-08-10 and OD-31 on 2026-08-11 —
and was corrected by hand on the second.

**Neither existing check can see it.** `register-range` reads the range and
compares it to the register, so it passes: the range was the half that stayed
current. `definition-count` reads a count and compares it to a register's
definitions, but its rules are keyed to *functional requirements* and *success
criteria*, and there is no rule for owner decisions — the site is in that
check's scoped documents and in none of its rules' populations. The defect sits
exactly in the gap: **the two halves of one sentence are never compared to each
other**, and the corpus says so in the entry that corrected it — *"`register-range`
cannot see the pairing, and the direction here is the opposite of the one it
guards: the range is current and the narrative count is stale."*

**Why the count is resolved against the register and not against the bounds.**
`hi - lo + 1` is arithmetic on two numbers in the prose and would report a gap
in the register as a defect in the sentence. The number of *defined* identifiers
inside the span is the same figure where the register is contiguous — every one
in this corpus is — and stays right where it is not.

**Three hiding mechanisms, each measured on this corpus before this pattern was
written.**

* *Emphasis between the count and its noun.* The live site reads
  `**thirty-one** owner decisions`, and a pattern run over the raw line finds
  **nothing**: measured at 0 pairings before the de-emphasising copy was added
  and 1 after. This is `definition-count`'s trap, arriving again — `~` is left
  alone, because struck-ness is read from it.
* *A struck intermediate bound.* `docs/spec-kit-workflow.md:137` writes
  `**OD-01** through ~~**OD-14**~~ ~~**OD-20**~~ … **OD-31**`, and a
  markup-tolerant pattern that stops at the first identifier after the
  connector reads **OD-14** — a superseded bound — as the live claim. That is a
  permanent false positive against the house convention rather than a
  transient one, so the live bound is taken as the *last unstruck* identifier
  in the chain rather than the next one.
* *A hard-wrapped range.* `findings/023-user-namespace-privilege-model.md:586`
  breaks `OD-01 through` at the end of one line and begins `OD-23` on the next,
  and a line-at-a-time scan matches neither half. The window spans the break.

**What keeps the frozen sites out is the noun, and it is doing more work than it
looks.** Thirty-two OD-range strings sit in this corpus and thirty-one of them
must not move: two are dated freezes recording what a validation run and a pass
each read, seven are worked examples inside `tools/README.md` — which the
include list now walks — and the rest are subset claims, register summaries and
narrative. Requiring the literal register noun beside the count reduces that
population to one. Dropping it to a bare *decisions* admits
`docs/spec-kit-workflow.md:137`, which is the struck-chain site, so the two
protections are not independent: the noun is what keeps the hardest false
positive out of scope entirely.
"""

from __future__ import annotations

import fnmatch
import re

from ..corpus import Corpus
from ..figures import inside_spans, struck_spans
from ..registry import check
from ..report import WARNING, Violation
from .identifiers import _collect_definitions, _namespaces
from .inventory import _to_int, expand_pattern, unparseable

#: Emphasis blanked to spaces before matching, offsets preserved. `~` is
#: excluded on purpose: struck-ness is read from it.
_EMPHASIS = re.compile(r"[*_`]")

#: Connector words and dashes that make two identifiers a range rather than a
#: list. Required between the first identifier and the next.
_CONNECTOR = re.compile(r"^[\s~*_]*(?:through|to|\u2026|\.\.\.|\u2013|\u2014|--|-)[\s~*_]*$")

#: How far past the noun the range may sit. Long enough to clear
#: "owner decisions\n(OD-01 through OD-31" and the struck chains, short enough
#: that the next sentence's identifiers are out of reach.
_REACH = 160


def _deemphasise(text: str) -> str:
    return _EMPHASIS.sub(" ", text)


def _live_bounds(window: str, struck: list[tuple[int, int]], ns: str, start: int):
    """The first and last *unstruck* `ns` identifiers of a range after `start`.

    Returns `(lo, hi, literal_end)` or `None`. The chain is walked rather than
    matched in one regex so a struck intermediate bound is stepped over instead
    of being read as the live one.
    """
    ids = [
        (m.start(), m.end(), int(m.group(1)))
        for m in re.finditer(rf"(?<![A-Za-z0-9-]){ns}-(\d{{2,3}})(?![A-Za-z0-9-])", window)
        if m.start() >= start
    ]
    if len(ids) < 2:
        return None
    # A connector must sit between the first identifier and the next, or the
    # two are a list rather than a range.
    if not _CONNECTOR.match(window[ids[0][1]:ids[1][0]]):
        return None
    unstruck = [t for t in ids if not inside_spans(struck, t[0], t[1])]
    if len(unstruck) < 2:
        return None
    return unstruck[0][2], unstruck[-1][2], unstruck[-1][1]


@check(
    "count-versus-range",
    "A register's stated size and the range quoted beside it agree with each other.",
)
def run(corpus: Corpus, ctx: dict) -> list[Violation]:
    config = ctx["config"]
    rules = config.get("count_range_rules", [])
    if not rules:
        ctx["skip"](
            "count-versus-range",
            "no count_range_rules configured, so nothing was read — this is "
            "not a clean result",
        )
        return []

    defined = ctx.get("identifiers_defined")
    if defined is None:
        defined = _collect_definitions(corpus, _namespaces(config))
        ctx["identifiers_defined"] = defined

    out: list[Violation] = []
    for rule in rules:
        ns = rule["namespace"]
        ids = {int(re.sub(r"\D", "", i)) for i in defined.get(ns, set())}
        if len(ids) < config["min_definitions"]:
            ctx["skip"](
                "count-versus-range",
                f"rule {rule['name']} disabled: the {ns} register defines "
                f"{len(ids)} entries, below min_definitions",
            )
            continue

        scope = rule.get("files", ["*"])
        rx = re.compile(
            expand_pattern(r"({{COUNT}})\s+" + rule["noun"]), re.IGNORECASE
        )
        seen = 0
        for doc in corpus.markdown():
            if not any(fnmatch.fnmatch(doc.relpath, p) for p in scope):
                continue
            masked = doc.masked_lines
            for i in range(len(masked)):
                if i in doc.fenced:
                    continue
                raw = masked[i]
                if i + 1 < len(masked) and (i + 1) not in doc.fenced:
                    raw = raw + "\n" + masked[i + 1]
                window = _deemphasise(raw)
                struck = struck_spans(raw)
                head = len(masked[i])
                for m in rx.finditer(window):
                    if m.start() >= head:
                        continue  # the next line's own pass owns it
                    if inside_spans(struck, m.start(), m.end()):
                        continue
                    bounds = _live_bounds(
                        window[: m.end() + _REACH], struck, ns, m.end()
                    )
                    if bounds is None:
                        continue
                    lo, hi, end = bounds
                    if lo != min(ids):
                        continue  # a subset claim, not a statement of size
                    seen += 1
                    claimed = _to_int(m.group(1))
                    if claimed is None:
                        out.append(
                            unparseable(
                                "count-versus-range", doc.relpath, i + 1,
                                " ".join(m.group(0).split()), m.group(1).strip(),
                                rule["name"], col=m.start() + 1,
                            )
                        )
                        continue
                    actual = len([n for n in ids if lo <= n <= hi])
                    if claimed == actual:
                        continue
                    out.append(
                        Violation(
                            check="count-versus-range",
                            severity=WARNING,
                            path=doc.relpath,
                            line=i + 1,
                            col=m.start() + 1,
                            # Reported from the de-emphasised copy, which is
                            # what the offsets index. Slicing the raw line at
                            # them starts mid-markup — `three** owner` — because
                            # the blanked `**` is where the word boundary landed.
                            found=" ".join(window[m.start():end].split()),
                            expected=f"{actual}, the number of {ns} entries in "
                            f"{ns}-{lo:02d} through {ns}-{hi:02d}",
                            hint=f"rule {rule['name']}; the count and the range "
                            "state the same fact and have drifted apart. The "
                            "range is generated and the count is prose, so the "
                            "count is usually the stale half. If the figure is "
                            "deliberately historical, strike it and advance it "
                            "in the house style",
                        )
                    )
        if seen == 0:
            ctx["skip"](
                "count-versus-range",
                f"rule {rule['name']} matched no count beside a {ns} range: its "
                "zero findings mean 'nothing read', not 'nothing wrong'",
            )
    return out
