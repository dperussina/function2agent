"""inventory-count — "14 research documents" must be how many there are.

Another failure class nobody had named. The README and the research index make
countable claims about the repository: how many research documents, how many
findings, how many committed harnesses, how many skills. Every one of those
goes stale the moment a file is added, and none of them is anywhere near the
file that changed, so no reviewer of the change ever sees the claim.

Unlike the other checks this one is driven entirely by config: a rule is a
regex whose single capture group holds the claimed count, plus a glob whose
match count is the truth. Adding a rule is a JSON entry, not code.

A count inside `~~…~~` is not a claim. The corpus supersedes by striking through
and dating rather than by deleting, so reading struck text as live would make
the convention unsatisfiable.

**A rule with no live site in its own scope reports nothing and is
indistinguishable from a rule that passes**, which is why the tail of this
function announces one rather than contributing a silent zero. The floor is the
one `definition-count` already carries, and it is here for the same reason: a
count check's clean output and its blind output are the same output. Measured
2026-08-10 over all six rules, two were reporting on nothing — `findings` and
`committed-harnesses` — and both had been silent through every green run.
~~`committed-harnesses`'s only in-scope site was struck on 2026-08-02 and re-stated
without a count on 2026-08-03.~~ **Corrected 2026-08-11 by replay — that sentence
is wrong on its date and stale on "only", and it is the third invented history
this docstring has produced.** Replayed through this module's own masking and its
own `struck_spans` over all 28 revisions of the four paths that have ever fallen
inside the rule's `files` scope: the phrase appears in **no** in-scope document on
2026-08-02, because `specs/001-discovery-validation/VERDICT.md` did not exist —
`deea4f3`, the initial commit of that date, holds `.gitignore`, `LICENSE` and
`README.md` and nothing else. Its first appearance anywhere in scope is
`cee7ff8`, that document's own first revision, dated 2026-08-03, and it is
**already struck in the revision that introduces it**. It was never live. What is
dated 2026-08-02 is the prose *inside* the strike — `**Corrected 2026-08-02:**` —
an editorial date the document records about itself, which this docstring read as
a commit. The re-statement without a count is the same paragraph's unstruck
parenthetical and is correctly dated 2026-08-03. **"Only" was true at the
2026-08-10 measurement and is not true now**: `specs/*/harness/README.md` entered
scope in that same pass, and `specs/001-discovery-validation/harness/README.md`
has carried a live `thirteen committed harnesses` since `3adf935` on 2026-08-10,
against a glob that counts thirteen directories.

**`findings` was recorded here as a rule whose
scoped documents "stopped stating a total", and that was wrong: they never stated
one.** Replayed on 2026-08-11 against this module's own masking over ~~all 266
revisions of~~ **all 14 revisions of** `README.md` and `research/README.md`, the
rule matched nothing in every revision before its current site — it had no live
site for its whole life, not a lost one. It has one now: the repository map
states the corpus-wide total across both `findings/` directories, which is the
scope this rule's glob actually spans.

**The 266 is corrected 2026-08-11 and it is a fourth wrong figure in this
docstring, of the same class as the three above.** The two documents have seven
revisions each. 266 is the repository's *total commit count* at `c9e42ad`, the
commit that wrote this rule's scope-widening comment — a commit count relabelled
as a document-revision count, with the operands never stated. Re-replayed at 14
file-revisions the conclusion is unchanged and is now checkable: zero live
matches before `451725f`, one at it, which is the site the rule reads today.

**Three narrated histories in one docstring, two invented and one stale, is a
pattern rather than three slips, and the pattern is recorded where the checker's
limits are rather than here.** See `tools/README.md` § *What this cannot catch*,
under *Anything outside markdown*: a docstring explaining why a rule went quiet
is read by no check, quoted by briefs as though it were, and cheaper to invent
than to replay. This paragraph is itself unread, which is the point.

The announcement is a skip and not an error, which is where this parts company
with `gen_claims.py`'s floor of one. A generator that matches nothing is dead by
construction, because writing claims is the whole of its job. A count rule that
matches nothing may instead be describing a corpus that makes no such claim, and
a corpus is not required to state its own inventory. What transfers is the
visibility; the severity does not.

Scope is read from the rule's own `files`, and the difference that makes is not
decorative. `tools/README.md` documents this check with the example phrase
*"five committed harnesses" when there are eight*, which matches
`committed-harnesses` and is not struck — so a search of the corpus at large
reports that rule as live while the rule itself, which never looks at
`tools/README.md`, sees nothing at all.

**A rule whose glob counts zero has two causes, and until now they printed the
same word.** A glob that matches nothing because the corpus moved under it is a
defect in the rule. A glob that matches nothing because its subject is not in
the tree — `vendored-repos` reads `examples/`, which is git-ignored, so no
checkout can contain it — is the rule being out of scope by construction, and it
is the state every CI run has been in. A rule may declare that condition as a
`precondition`, and where the declared path is absent the announcement says so
instead of reporting an incident. `disabled` is now reserved for the case where
the precondition held and the glob still found nothing, which is the one worth
reading as a fault.
"""

from __future__ import annotations

import fnmatch
import re

from ..corpus import Corpus
from ..figures import inside_spans, struck_spans
from ..registry import check
from ..report import ERROR, WARNING, Violation

_UNITS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
    "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19,
}

_TENS = {
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}


def _vocabulary() -> dict[str, int]:
    words = dict(_UNITS)
    for tens_word, tens in _TENS.items():
        words[tens_word] = tens
        for unit_word, unit in _UNITS.items():
            if unit < 10:
                words[f"{tens_word}-{unit_word}"] = tens + unit
    return words


#: Every English number word below one hundred, generated rather than typed.
#: The bound is the grammar's and not this corpus's: at one hundred the token
#: shape changes from a single hyphenated compound to a phrase with a scale word
#: and an "and", which is a different parse rather than a longer table. Picking
#: the bound where the grammar changes is what stops it being re-picked each time
#: a register grows.
_WORDS = _vocabulary()

#: The largest count a claim may state and still be verified — ninety-nine.
CEILING = max(_WORDS.values())


def _to_int(token: str) -> int | None:
    t = " ".join(token.strip().lower().replace(",", "").split())
    if t.isdigit():
        return int(t)
    return _WORDS.get(t)


#: A spelled count at or above `CEILING` + 1, matched so that it can be refused
#: out loud. Without it the pattern simply fails and the site disappears: no
#: match, no parse, no announcement, and a report that reads exactly like a
#: verified count. Matching the shape and refusing to resolve it is what makes
#: the ceiling audible.
_ABOVE_CEILING = (
    r"(?:[a-z]+(?:-[a-z]+)?\s+)?(?:hundred|thousand|million|billion)"
    r"(?:\s+and\s+[a-z]+(?:-[a-z]+)?)?"
)

#: The one spelled-number alternation every count rule shares, longest word
#: first so `twenty-one` wins over `twenty`. A rule writes `{{COUNT}}` in its
#: pattern and gets this; before that placeholder existed each rule carried its
#: own alternation and each stopped somewhere different — at ten, at twelve, at
#: twenty, at twenty-two — so the ceiling that bound was whichever rule was
#: being read rather than the one this module documents.
COUNT = (
    r"\b(?:"
    + "|".join(
        [r"[0-9][0-9,]*", _ABOVE_CEILING]
        + sorted(_WORDS, key=len, reverse=True)
    )
    + r")"
)

_PLACEHOLDER = "{{COUNT}}"


def expand_pattern(pattern: str) -> str:
    """Substitute the shared count alternation into a configured pattern."""
    return pattern.replace(_PLACEHOLDER, COUNT)


def unparseable(check_name: str, relpath: str, lineno: int, literal: str,
                token: str, rule_name: str, col: int | None = None) -> Violation:
    """The violation raised where a count matched but did not resolve.

    An `error`, on the split this repository already applies. A mismatch is a
    `warning` because it can be a deliberate historical claim and the strike
    convention is its escape — and the strike test runs before this one, so a
    count deliberately left in history never arrives here. An unresolved count
    has no such reading: the document stated a number, the check did not read
    it, and the run reports success. That is the same false green as a blind
    extractor returning `0`, which is already an error here, and it is the shape
    this checker exists to catch rather than to produce.
    """
    return Violation(
        check=check_name,
        severity=ERROR,
        path=relpath,
        line=lineno,
        col=col,
        found=f"{literal!r}: the count {token!r} is above the "
        f"{CEILING} this parser resolves",
        expected=f"a count at or below {CEILING}, or the vocabulary in "
        "tools/corpuscheck/checks/inventory.py extended past it",
        hint=f"rule {rule_name}; this is the instrument's limit and not the "
        "document's defect — the claim was read and left unverified, which "
        "reports identically to a verified one unless it is said out loud",
    )


def _count(root, glob: str, glob_exclude: str | None) -> int:
    want_dirs = glob.endswith("/")
    pattern = glob.rstrip("/")
    hits = []
    for p in root.glob(pattern):
        if want_dirs and not p.is_dir():
            continue
        if not want_dirs and not p.is_file():
            continue
        rel = p.relative_to(root).as_posix()
        if glob_exclude and fnmatch.fnmatch(rel, glob_exclude.rstrip("/")):
            continue
        hits.append(rel)
    return len(hits)


@check("inventory-count", "Prose counts of repository contents match the filesystem.")
def run(corpus: Corpus, ctx: dict) -> list[Violation]:
    config = ctx["config"]
    rules = config.get("inventory_rules", [])
    default_files = config.get("inventory_default_files", ["README.md"])
    out: list[Violation] = []

    for rule in rules:
        actual = _count(corpus.root, rule["glob"], rule.get("glob_exclude"))
        if actual == 0:
            pre = rule.get("precondition")
            if pre and not (corpus.root / pre["path"]).exists():
                ctx["skip"](
                    "inventory-count",
                    f"rule {rule['name']} is out of scope in this tree, as declared: "
                    f"{pre['path']} is absent, which is the rule's stated precondition "
                    f"and not a fault — {pre['why']}",
                )
            else:
                ctx["skip"](
                    "inventory-count",
                    f"rule {rule['name']} disabled: glob {rule['glob']} matched nothing",
                )
            continue
        scope = rule.get("files", default_files)
        rx = re.compile(expand_pattern(rule["pattern"]), re.IGNORECASE)
        sites = 0
        for doc in corpus.markdown():
            if not any(fnmatch.fnmatch(doc.relpath, p) for p in scope):
                continue
            for lineno, masked in enumerate(doc.masked_lines, start=1):
                if not masked.strip():
                    continue
                struck = struck_spans(masked)
                for m in rx.finditer(masked):
                    # Struck first, and the order is load-bearing. The parse can
                    # now refuse a count out loud, and the corpus supersedes by
                    # striking rather than deleting — `plan.md`'s OD header
                    # carries fourteen struck counts on one line — so refusing
                    # before reading struck-ness would announce against the
                    # convention at every superseded figure in the corpus.
                    if inside_spans(struck, m.start(), m.end()):
                        continue
                    # Counted before the comparison: a claim that agrees with the
                    # filesystem is the case this check exists to keep true, and
                    # it is evidence the rule is reading something. A claim that
                    # did not resolve is evidence of the same thing.
                    sites += 1
                    claimed = _to_int(m.group(1))
                    if claimed is None:
                        out.append(
                            unparseable(
                                "inventory-count", doc.relpath, lineno,
                                m.group(0).strip(), m.group(1).strip(),
                                rule["name"], col=m.start() + 1,
                            )
                        )
                        continue
                    if claimed == actual:
                        continue
                    out.append(
                        Violation(
                            check="inventory-count",
                            severity=WARNING,
                            path=doc.relpath,
                            line=lineno,
                            col=m.start() + 1,
                            found=f"{m.group(0).strip()}  (claims {claimed})",
                            expected=f"{actual}, the number matching {rule['glob']}",
                            hint=f"rule {rule['name']}; "
                            + (
                                "the claim is stale — files were added"
                                if claimed < actual
                                else "the claim is stale — files were removed or the glob is wrong"
                            ),
                        )
                    )

        if sites == 0:
            ctx["skip"](
                "inventory-count",
                f"rule {rule['name']} matched no live claim in "
                + ", ".join(scope)
                + f" (glob {rule['glob']} counts {actual}): its zero findings mean "
                "'nothing read', not 'nothing wrong'",
            )
    return out
