"""identifier-resolution — every D-17, U-40, OD-06, FR-018, E15 has a definition.

Dangling identifiers are how a superseded decision keeps getting cited: the row
is struck or renumbered somewhere, the citations are not, and the reference
still reads like an authority. The check resolves each reference against a
definition index built from the places this corpus actually defines things:

  * the first column of a register table — `| D-17 | ... |`, including struck
    and bolded forms like `| ~~**P-02**~~ |`
  * a heading that *leads* with the identifier — `### OD-01 — ADK's role`
  * a bold-lead bullet — `- **FR-018**: Analysis MUST operate on copies`

All three shapes are lead-anchored, and the heading shape is deliberately the
strictest reading of the example above: only the identifier the heading opens
with defines. A heading that merely *names* identifiers in prose — `### The
execution environment — FR-048, FR-049 and FR-050's mechanisms` — announces a
section about them, it does not define them. Counting those as definitions is
not a harmless over-read: it manufactures exactly the phantom register that
defeats the `min_definitions` guard below. See the note in `tools/README.md`
under **Narrowing and the definition index** for the measurement.

A namespace is only enforced once at least `min_definitions` of its members are
found. If a register is deleted or renamed, the check turns itself off with a
stated reason rather than reporting every reference in the corpus as dangling —
a checker that produces two hundred violations gets switched off permanently,
which costs more than the errors it found.

That guard is load-bearing under `--path`: narrowing removes the register from
the corpus, the namespace falls under the threshold, and the check declares
itself skipped instead of reporting every surviving reference as unresolved.
The cost of the guard is stated in the same README section — a skip cannot tell
"narrowed away" from "deleted", so a green narrowed run is not evidence that
the registers still exist.

`identifier-gap` is the companion: a namespace with a hole in it (D-01…D-14,
D-16…) usually means an entry was deleted rather than struck, and struck-with-a
-tombstone is this corpus's own convention.
"""

from __future__ import annotations

import re

from ..corpus import Corpus, load as load_corpus, split_row
from ..registry import check
from ..report import ERROR, WARNING, Violation

_DECOR = re.compile(r"[*~`_\s]+")
_HEADING = re.compile(r"^#{1,6}\s+(.*)$")
# Leading decoration only — `### **OD-01** — role` and `### ~~D-05~~ superseded`
# still lead with their identifier once the markup is stripped.
_LEAD_DECOR = re.compile(r"^[*~`_\s]+")
_BULLET_DEF = re.compile(r"^\s*[-*+]\s+\*\*([A-Za-z]{1,3}-?\d{1,3})\*\*\s*[:.\u2014-]")


def _namespaces(config: dict) -> dict[str, re.Pattern]:
    return {
        name: re.compile(r"(?<![A-Za-z0-9-])" + spec["pattern"] + r"(?![A-Za-z0-9-])")
        for name, spec in config["identifier_namespaces"].items()
    }


def definitions_in(doc, patterns: dict[str, re.Pattern]) -> dict[str, set[str]]:
    """Map namespace -> identifiers *this one document* defines.

    The single definition of "defines" in this tool. `_collect_definitions`
    unions it over the corpus and `definition-count` asks it about one file;
    both have to agree about the three shapes below, and a second copy of the
    rule would drift from the first, which is the failure class this directory
    exists to prevent.
    """
    defined: dict[str, set[str]] = {ns: set() for ns in patterns}

    def note(text: str) -> None:
        for ns, rx in patterns.items():
            for m in rx.finditer(text):
                defined[ns].add(m.group(0))

    def note_lead(text: str) -> None:
        """Only an identifier the text *opens* with defines it.

        The namespace patterns already carry a trailing boundary lookahead, so
        an anchored `match` is the whole rule.
        """
        head = _LEAD_DECOR.sub("", text)
        for ns, rx in patterns.items():
            m = rx.match(head)
            if m:
                defined[ns].add(m.group(0))

    for i, line in enumerate(doc.lines):
        if i in doc.fenced:
            continue

        hm = _HEADING.match(line)
        if hm:
            note_lead(hm.group(1))
            continue

        bm = _BULLET_DEF.match(line)
        if bm:
            note(bm.group(1))
            continue

        if line.lstrip().startswith("|"):
            cells = split_row(line)
            if cells:
                head = _DECOR.sub("", cells[0])
                # Only an exact first-cell match defines; a cell of prose
                # that happens to mention D-17 does not.
                for ns, rx in patterns.items():
                    m = rx.fullmatch(head)
                    if m:
                        defined[ns].add(m.group(0))
    return defined


def _collect_definitions(corpus: Corpus, patterns: dict[str, re.Pattern]) -> dict[str, set[str]]:
    """Map namespace -> set of identifiers the corpus defines."""
    defined: dict[str, set[str]] = {ns: set() for ns in patterns}
    for doc in corpus.markdown():
        for ns, ids in definitions_in(doc, patterns).items():
            defined[ns] |= ids
    return defined


def _unnarrowed_definitions(
    corpus: Corpus, config: dict, patterns: dict[str, re.Pattern]
) -> dict[str, set[str]]:
    """The definition index the *whole tree* yields, ignoring any `--path`.

    Read off the filesystem under `corpus.root` rather than off the corpus that
    was handed in, which is the same move `lifecycle-taxonomy` makes to tell a
    missing document from a narrowed-away one. This is what keeps the skip
    below from being vacuous: the deletion test is asked of the unnarrowed
    tree, so no combination of `--path` arguments can answer it.
    """
    return _collect_definitions(load_corpus(corpus.root, config), patterns)


def _activation(corpus: Corpus, ctx: dict) -> tuple[dict[str, set[str]], dict[str, re.Pattern], list[str]]:
    """Which namespaces this run may enforce, decided once and shared.

    Both checks in this module need the same answer, and the runner executes
    them in name order, so `identifier-gap` runs *first*. The older arrangement
    had `identifier-gap` read an index that `identifier-resolution` was
    expected to have left in `ctx`; that handoff ran in the wrong direction and
    the fallback branch was therefore the only branch ever taken, which is how
    the gap check kept reporting on namespaces the resolution check had
    disabled. Computing it here makes the order irrelevant.

    Returns the narrowed definition index, the enforceable namespaces, and the
    reasons for every namespace left out, for the caller to announce.
    """
    cached = ctx.get("_identifier_activation")
    if cached is not None:
        return cached

    config = ctx["config"]
    patterns = _namespaces(config)
    minimum = config["min_definitions"]
    defined = _collect_definitions(corpus, patterns)

    # Under `--path`, `defined` is only what survived the narrowing. Every
    # deletion test below is asked of `whole` instead, which is read off the
    # unnarrowed tree, so narrowing can suppress a namespace but can never make
    # a deleted register look present.
    whole = (
        _unnarrowed_definitions(corpus, config, patterns)
        if ctx.get("narrowed_paths")
        else defined
    )

    active: dict[str, re.Pattern] = {}
    reasons: list[str] = []
    for ns, rx in patterns.items():
        if len(whole[ns]) < minimum:
            # Asked of the whole tree: the register is absent, deleted or
            # renamed, and this reads the same with or without `--path`.
            reasons.append(
                f"namespace {ns} disabled: found {len(whole[ns])} definition(s), "
                f"need {minimum} ({config['identifier_namespaces'][ns]['what']})"
            )
            continue

        missing = whole[ns] - defined[ns]
        if missing:
            # The register exists; this run just cannot see all of it. Resolving
            # against a partial index would report every reference to the part
            # that was narrowed away as dangling — hundreds of errors naming
            # identifiers that resolve perfectly well in a full run.
            reasons.append(
                f"namespace {ns} not enforced: {len(missing)} of {len(whole[ns])} "
                f"definition(s) are outside the --path selection, so the register "
                f"({config['identifier_namespaces'][ns]['what']}) was only partly "
                "read — a full run enforces it"
            )
            continue

        active[ns] = rx

    out = (defined, active, reasons)
    ctx["_identifier_activation"] = out
    ctx["identifiers_defined"] = defined
    ctx["identifiers_active"] = set(active)
    return out


@check("identifier-resolution", "Register identifiers (D-17, U-40, OD-06, FR-018, E15) resolve.")
def resolution(corpus: Corpus, ctx: dict) -> list[Violation]:
    config = ctx["config"]
    defined, active, reasons = _activation(corpus, ctx)
    for reason in reasons:
        ctx["skip"]("identifier-resolution", reason)

    out: list[Violation] = []
    for doc in corpus.markdown():
        for lineno, masked in enumerate(doc.masked_lines, start=1):
            if not masked.strip():
                continue
            for ns, rx in active.items():
                for m in rx.finditer(masked):
                    token = m.group(0)
                    if token in defined[ns]:
                        continue
                    out.append(
                        Violation(
                            check="identifier-resolution",
                            severity=ERROR,
                            path=doc.relpath,
                            line=lineno,
                            col=m.start() + 1,
                            found=token,
                            expected=f"a definition of {token} in the {ns} register "
                            f"({config['identifier_namespaces'][ns]['what']})",
                            hint=f"{ns} currently runs to "
                            f"{max(sorted(defined[ns]), default='—')}; "
                            "struck entries keep their row, deleted ones do not",
                        )
                    )
    return out


@check("identifier-gap", "A register with a missing member usually means a deleted row.")
def gaps(corpus: Corpus, ctx: dict) -> list[Violation]:
    config = ctx["config"]
    # Same activation decision `identifier-resolution` uses, so a namespace
    # whose register was narrowed away is not reported here as a register full
    # of holes. Announcing the reasons is left to that check, which is where
    # they have always been printed.
    defined, active, _reasons = _activation(corpus, ctx)

    out: list[Violation] = []
    for ns in sorted(active):
        nums = sorted(int(re.sub(r"\D", "", i)) for i in defined[ns])
        if len(nums) < config["min_definitions"]:
            continue
        missing = [n for n in range(min(nums), max(nums) + 1) if n not in nums]
        if not missing:
            continue
        width = len(re.sub(r"\D", "", sorted(defined[ns])[0]))
        pretty = ", ".join(f"{ns}-{n:0{width}d}" if "-" in sorted(defined[ns])[0] else f"{ns}{n}" for n in missing)
        out.append(
            Violation(
                check="identifier-gap",
                severity=WARNING,
                path=config["identifier_namespaces"][ns]["what"],
                line=0,
                found=f"{ns} register has no definition for {pretty}",
                expected=f"a contiguous {ns} register from {min(nums)} to {max(nums)}",
                hint="a superseded entry should keep its row with a strike-through, "
                "so a gap usually means a deleted row that is still cited elsewhere",
            )
        )
    return out
