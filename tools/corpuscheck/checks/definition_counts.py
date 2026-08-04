"""definition-count — "58 functional requirements" must be how many are defined.

A fifth instance of the class `register-range`, `inventory-count` and
`catalog-line-count` already name: **a claim about an artifact that lives in a
different file from the artifact**, so no reviewer of the change that
invalidated it ever sees it. Here the artifact is a specification and the claim
is how many requirements it states.

The catch history is why this exists. `specs/002-spec-aware-agent-runtime/`
carries the claim in exactly two documents, and on 2026-08-04 **both were stale
and neither had ever been checked**: `plan.md`'s header read *54 functional
requirements, 28 success criteria* against an actual 57 and 30 — wrong by three
and by two **before** FR-058 was added — and `tasks.md` read 55 against 58. Two
requirements had landed, then a third, and nothing anywhere connected the
register to the two documents that quote its size. `gen_claims.py` reported 39
generated claims and `check_corpus.py` ran its fifteen checks at 0 errors while
both figures were wrong, because neither instrument read them. Feature 001
carries a third site, in `checklists/requirements.md`, written as a number word;
it was correct and is now guarded too.

**Why this is a check and not a generator.** The house preference is to generate
a fact rather than guard a transcription, and it does not apply here for three
reasons, each sufficient on its own.

* `gen_claims.py` locates a site as a character span in **one line** and
  resolves what the number is a fact *about* from a markdown link in that same
  line or table cell. `plan.md:6` — the site that actually drifted — carries no
  link at all; it names the specification in inline code on the *previous* line,
  which masking blanks. The generator would have written the site that stayed
  correct and missed the one that did not.
* Both live sites are **correction records**: a struck figure, a live figure and
  a dated note, all on one line. That is precisely the shape `gen_claims.py`
  classifies `MANUAL` and refuses to write, on the register-range precedent —
  the digits are half the claim and the dated note beside them is the other
  half, so advancing the digits alone converts a *detectable* staleness into an
  *undetectable* one. A generator whose every site is `MANUAL` is this check
  wearing a rewriter's costume, plus the rewrite hazard.
* The house convention for a superseded figure is strike-and-advance, so every
  future site will be a correction record too. The `MANUAL` classification is
  not a temporary state of this corpus; it is what the convention produces.

**Zero definitions is an error and never a pass, which is the whole design.**
Four instruments in this repository were hardened in one week for reporting
success on input they had not actually read — `check_tampers.py` exiting 0 on 61
declaration-shaped lines and one extractable proof, `proof_attribution.py`
reporting a clean sweep when pytest was merely absent, `cite_advisor.py` still
printing *57 requirements scored against 0 contracts* at exit 0. A count check
is unusually exposed to that failure, because **the number it computes when its
extractor is blind is `0`, and `0` is also a number a document can legitimately
claim.** So a site whose target yields no definitions of the claimed kind is an
`error` here whatever was claimed, including where the claim is itself zero and
the two therefore agree. A bare implementation compares two numbers and passes
that case twice over — once because they are equal, and once more if it copies
`inventory-count`'s `if actual == 0: skip`. Equality is not verification when
one side is the absence of a reading.

`tools/fixtures/known-bad/specs/001-fixture/` pins both halves: a specification
whose requirement bullets lost their bold markers, so the extractor reads none
of them, under a tasks file that claims nine of one kind and zero of another.

**What it cannot be satisfied by editing.** The two numbers it compares are a
count in prose and a count of definitions in another document. There is no
expectation to relax: satisfying it means correcting the prose, striking it in
the house style, or actually adding requirements. It carries **no tolerance and
no threshold** — an exact count has no approximately-right value, and a constant
here would be one more thing `threshold_probe.py` has to pin.

**Severity is split, and the split is the README's rule applied.** A mismatch is
a `warning`, because it can be a deliberate historical claim — this corpus keeps
one, `checklists/requirements.md` frozen at the fourteenth owner decision because
advancing it would assert coverage a dated validation run did not have — and the
escape is the strike convention, which this check honours. Zero definitions is
an `error`, because a blind extractor is never a judgement call.

**Two blind spots, both from named traps in this repository rather than guessed
at.**

* *Emphasis between the count and its unit.* `tools/README.md` records at length
  how `_RANGE` silently stops matching when `**` sits between two identifiers,
  and how that is "a side effect of the pattern, not a marking". The same
  markup sits between the number and its noun the moment a figure is advanced in
  the house style — `**58** functional requirements` — so the scan runs over a
  copy with emphasis characters blanked to spaces, offsets preserved. `~` is
  deliberately left alone, because struck-ness is read from it.
* *Hard-wrapped prose.* The claim phrase is long enough to be split across a
  line break, and `plan.md`'s live success-criteria count is split exactly
  there: `30 success` ends one line and `criteria` begins the next. A
  line-at-a-time scan does not see it — which would have left unread the very
  figure that went stale by two. The scan therefore runs over a two-line window
  and attributes a match to the line its number sits on.

**Residue, stated rather than left to be found.** A count claim outside a
`specs/<feature>/` directory has no target to resolve against and is not read; a
claim about a *different* feature's specification is resolved against its own
feature's, so a cross-feature claim would be read wrongly rather than skipped —
there are none, and putting one in the root README would need this rule taught to
follow a link. And if a rule's pattern matches nothing anywhere in scope the
check announces a skip rather than contributing a silent zero, which makes a
regex that has stopped matching visible in the report; it does not fail the run,
because a corpus with no such claim in it is not a defect.
"""

from __future__ import annotations

import fnmatch
import re

from ..corpus import Corpus
from ..figures import inside_spans, struck_spans
from ..registry import check
from ..report import ERROR, WARNING, Violation
from .identifiers import _namespaces, definitions_in
from .inventory import _to_int

#: The first two path components of a document under `specs/`, which is where
#: its feature's specification sits.
_FEATURE = re.compile(r"^(specs/[^/]+)/")

#: Emphasis markers, blanked to spaces before matching so that the house style
#: for an advanced figure — `**58** functional requirements` — does not hide the
#: claim from the pattern that reads it. Length-preserving, so offsets computed
#: on the blanked copy index the original and `struck_spans` still lines up.
#: `~` is excluded on purpose: it is the strike marker this check reads.
_EMPHASIS = re.compile(r"[*_`]")


def _deemphasise(text: str) -> str:
    return _EMPHASIS.sub(" ", text)


def _target_of(relpath: str, target_name: str) -> str | None:
    m = _FEATURE.match(relpath)
    return f"{m.group(1)}/{target_name}" if m else None


def _sites(doc, rx: re.Pattern):
    """Yield `(lineno, claimed, literal)` for each live claim on this document.

    Scanned over a two-line window, because the phrase is long enough that the
    corpus's hard wrap splits it and the split site is a real one. A match is
    owned by the line its *number* starts on, so scanning every line as the head
    of its own window never double-counts.
    """
    masked = doc.masked_lines
    n = len(masked)
    for i in range(n):
        if i in doc.fenced:
            continue
        head = _deemphasise(masked[i])
        window = head
        joined_raw = None
        if i + 1 < n and (i + 1) not in doc.fenced:
            window = head + "\n" + _deemphasise(masked[i + 1])
            joined_raw = masked[i] + "\n" + masked[i + 1]

        line_struck = struck_spans(masked[i])
        window_struck = None

        for m in rx.finditer(window):
            if m.start() >= len(head):
                # The number sits on the next line; that line's own pass owns it.
                continue
            if m.end() <= len(head):
                struck = line_struck
            else:
                if window_struck is None:
                    window_struck = struck_spans(joined_raw)
                struck = window_struck
            if inside_spans(struck, m.start(), m.end()):
                continue
            claimed = _to_int(m.group(1))
            if claimed is None:
                continue
            yield i + 1, claimed, " ".join(m.group(0).split())


@check(
    "definition-count",
    "A prose count of a register — “58 functional requirements” — matches the definitions in the document it describes.",
)
def run(corpus: Corpus, ctx: dict) -> list[Violation]:
    config = ctx["config"]
    rules = config.get("definition_count_rules", [])
    scope = config.get("definition_count_files", [])
    target_name = config.get("definition_count_target", "spec.md")

    if not rules or not scope:
        ctx["skip"](
            "definition-count",
            "no definition_count_rules or definition_count_files configured, "
            "so nothing was read — this is not a clean result",
        )
        return []

    patterns = _namespaces(config)
    by_relpath = {d.relpath: d for d in corpus.markdown()}
    cache: dict[str, dict[str, set[str]]] = {}

    compiled: list[tuple[dict, re.Pattern]] = []
    for rule in rules:
        if rule["namespace"] not in patterns:
            ctx["skip"](
                "definition-count",
                f"rule {rule['name']} disabled: namespace {rule['namespace']} "
                "is not in identifier_namespaces",
            )
            continue
        compiled.append((rule, re.compile(rule["pattern"], re.IGNORECASE)))

    seen = {rule["name"]: 0 for rule, _ in compiled}
    out: list[Violation] = []

    for doc in corpus.markdown():
        if not any(fnmatch.fnmatch(doc.relpath, p) for p in scope):
            continue
        target_rel = _target_of(doc.relpath, target_name)
        if target_rel is None:
            continue
        target = by_relpath.get(target_rel)
        if target is None:
            ctx["skip"](
                "definition-count",
                f"{doc.relpath}: {target_rel} is not in the corpus, so the counts "
                "it quotes were not checked",
            )
            continue
        if target.relpath not in cache:
            cache[target.relpath] = definitions_in(target, patterns)
        defined = cache[target.relpath]

        for rule, rx in compiled:
            ns = rule["namespace"]
            what = rule.get("what", config["identifier_namespaces"][ns]["what"])
            for lineno, claimed, literal in _sites(doc, rx):
                seen[rule["name"]] += 1
                actual = len(defined.get(ns, set()))

                # The floor, and the reason this check exists in the shape it
                # does. `0` is what the extractor returns when it is blind, and
                # it is also a number a document may claim, so the two cases are
                # indistinguishable to an equality test. They are separated here
                # by refusing the reading rather than by comparing it.
                if actual == 0:
                    out.append(
                        Violation(
                            check="definition-count",
                            severity=ERROR,
                            path=doc.relpath,
                            line=lineno,
                            found=f"{literal!r}, but no {ns} definition was found "
                            f"in {target_rel}",
                            expected=f"at least one {ns} definition in {target_rel} "
                            "before any count of them can be verified",
                            hint=f"0 here means 'not found', not 'none exist', and it "
                            f"matches a claim of 0 without checking anything — "
                            f"{ns} is defined by a bold-lead bullet, a heading, or a "
                            f"register table's first cell ({what}), so this usually "
                            "means the definitions changed shape or the document moved",
                        )
                    )
                    continue

                if claimed != actual:
                    out.append(
                        Violation(
                            check="definition-count",
                            severity=WARNING,
                            path=doc.relpath,
                            line=lineno,
                            found=f"{literal!r} (claims {claimed})",
                            expected=f"{actual}, the number of {ns} definitions in "
                            f"{target_rel}",
                            hint=f"rule {rule['name']}; the register runs to "
                            f"{max(sorted(defined[ns]), default='—')}. "
                            "If the figure is deliberately historical, strike it and "
                            "advance it in the house style — a struck count is not "
                            "read as a claim",
                        )
                    )

    for rule, _ in compiled:
        if seen[rule["name"]] == 0:
            ctx["skip"](
                "definition-count",
                f"rule {rule['name']} matched no claim in {len(scope)} scoped path "
                "pattern(s): its zero findings mean 'nothing read', not 'nothing wrong'",
            )

    return out
