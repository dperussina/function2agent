"""identifier-resolution — every D-17, U-40, OD-06, FR-018, E15 has a definition.

Dangling identifiers are how a superseded decision keeps getting cited: the row
is struck or renumbered somewhere, the citations are not, and the reference
still reads like an authority. The check resolves each reference against a
definition index built from the places this corpus actually defines things:

  * the first column of a register table — `| D-17 | ... |`, including struck
    and bolded forms like `| ~~**P-02**~~ |`
  * a heading — `### OD-01 — ADK's role`
  * a bold-lead bullet — `- **FR-018**: Analysis MUST operate on copies`

A namespace is only enforced once at least `min_definitions` of its members are
found. If a register is deleted or renamed, the check turns itself off with a
stated reason rather than reporting every reference in the corpus as dangling —
a checker that produces two hundred violations gets switched off permanently,
which costs more than the errors it found.

`identifier-gap` is the companion: a namespace with a hole in it (D-01…D-14,
D-16…) usually means an entry was deleted rather than struck, and struck-with-a
-tombstone is this corpus's own convention.
"""

from __future__ import annotations

import re

from ..corpus import Corpus, split_row
from ..registry import check
from ..report import ERROR, WARNING, Violation

_DECOR = re.compile(r"[*~`_\s]+")
_HEADING = re.compile(r"^#{1,6}\s+(.*)$")
_BULLET_DEF = re.compile(r"^\s*[-*+]\s+\*\*([A-Za-z]{1,3}-?\d{1,3})\*\*\s*[:.\u2014-]")


def _namespaces(config: dict) -> dict[str, re.Pattern]:
    return {
        name: re.compile(r"(?<![A-Za-z0-9-])" + spec["pattern"] + r"(?![A-Za-z0-9-])")
        for name, spec in config["identifier_namespaces"].items()
    }


def _collect_definitions(corpus: Corpus, patterns: dict[str, re.Pattern]) -> dict[str, set[str]]:
    """Map namespace -> set of identifiers the corpus defines."""
    defined: dict[str, set[str]] = {ns: set() for ns in patterns}

    def note(text: str) -> None:
        for ns, rx in patterns.items():
            for m in rx.finditer(text):
                defined[ns].add(m.group(0))

    for doc in corpus.markdown():
        for i, line in enumerate(doc.lines):
            if i in doc.fenced:
                continue

            hm = _HEADING.match(line)
            if hm:
                note(hm.group(1))
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


@check("identifier-resolution", "Register identifiers (D-17, U-40, OD-06, FR-018, E15) resolve.")
def resolution(corpus: Corpus, ctx: dict) -> list[Violation]:
    config = ctx["config"]
    patterns = _namespaces(config)
    defined = _collect_definitions(corpus, patterns)
    minimum = config["min_definitions"]

    active: dict[str, re.Pattern] = {}
    for ns, rx in patterns.items():
        if len(defined[ns]) >= minimum:
            active[ns] = rx
        else:
            ctx["skip"](
                "identifier-resolution",
                f"namespace {ns} disabled: found {len(defined[ns])} definition(s), "
                f"need {minimum} ({config['identifier_namespaces'][ns]['what']})",
            )
    ctx["identifiers_defined"] = defined
    ctx["identifiers_active"] = set(active)

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
    defined = ctx.get("identifiers_defined")
    if defined is None:
        defined = _collect_definitions(corpus, _namespaces(config))
    active = ctx.get("identifiers_active")
    if active is None:
        active = {ns for ns, ids in defined.items() if len(ids) >= config["min_definitions"]}

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
