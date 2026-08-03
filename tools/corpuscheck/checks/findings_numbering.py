"""findings-numbering — the findings directory is a dense, unique sequence.

Two documents were once both numbered 008. A duplicate is worse than it looks
because every citation of "finding 008" downstream becomes ambiguous and stays
ambiguous — nothing in the prose says which one was meant, so the ambiguity
cannot be resolved later by reading.

Three failures:

  findings-duplicate  Two files share a numeric prefix.
  findings-gap        A number in the range is missing. Either a document was
                      lost or one was renumbered and its citations were not.
  findings-dangling   Prose cites "finding 013" and no such file exists.
"""

from __future__ import annotations

import re

from ..corpus import Corpus, ROLE_AUTHORITY
from ..registry import check
from ..report import ERROR, WARNING, Violation

_PREFIX = re.compile(r"^(\d+)-")
_CITE = re.compile(r"\bfinding\s+(\d{1,3})\b", re.IGNORECASE)


@check("findings-numbering", "findings/ prefixes are unique, dense, and every citation resolves.")
def run(corpus: Corpus, ctx: dict) -> list[Violation]:
    docs = corpus.by_role(ROLE_AUTHORITY)
    if not docs:
        ctx["skip"]("findings-numbering", "no findings documents matched specs/*/findings/*.md")
        return []

    by_number: dict[int, list[str]] = {}
    for d in docs:
        base = d.relpath.rsplit("/", 1)[-1]
        m = _PREFIX.match(base)
        if not m:
            continue
        by_number.setdefault(int(m.group(1)), []).append(d.relpath)

    out: list[Violation] = []
    directory = docs[0].relpath.rsplit("/", 1)[0]

    for number, paths in sorted(by_number.items()):
        if len(paths) > 1:
            for p in sorted(paths):
                out.append(
                    Violation(
                        check="findings-numbering",
                        severity=ERROR,
                        path=p,
                        line=0,
                        found=f"prefix {number:03d} is used by {len(paths)} documents: "
                        + ", ".join(sorted(x.rsplit('/', 1)[-1] for x in paths)),
                        expected="a numeric prefix used by exactly one document",
                        hint="findings-duplicate; every downstream citation of "
                        f"'finding {number:03d}' is ambiguous until one is renumbered",
                    )
                )

    if by_number:
        lo, hi = min(by_number), max(by_number)
        missing = [n for n in range(lo, hi + 1) if n not in by_number]
        for n in missing:
            out.append(
                Violation(
                    check="findings-numbering",
                    severity=WARNING,
                    path=directory,
                    line=0,
                    found=f"no document numbered {n:03d}",
                    expected=f"a dense sequence {lo:03d}..{hi:03d}",
                    hint="findings-gap; either a document was lost or one was renumbered",
                )
            )

        known = set(by_number)
        for doc in corpus.markdown():
            for lineno, masked in enumerate(doc.masked_lines, start=1):
                if "finding" not in masked.lower():
                    continue
                for m in _CITE.finditer(masked):
                    n = int(m.group(1))
                    if n in known or n == 0 or n > 999:
                        continue
                    out.append(
                        Violation(
                            check="findings-numbering",
                            severity=ERROR,
                            path=doc.relpath,
                            line=lineno,
                            col=m.start() + 1,
                            found=m.group(0),
                            expected=f"one of the documents numbered {lo:03d}..{hi:03d}",
                            hint="findings-dangling; no file in "
                            f"{directory} carries that prefix",
                        )
                    )
    return out
