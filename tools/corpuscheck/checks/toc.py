"""toc-coverage — a document with a table of contents lists all of its sections.

The research documents carry a hand-maintained `## Table of contents` of
same-file anchor links. `link-anchor` catches a TOC entry pointing at a heading
that no longer exists; this catches the other direction, which is more common
and less visible: a section added without a TOC entry. The section is then
unreachable from the top of a 800-line document, which for a corpus that is
navigated by cross-reference is close to the section not existing.

Only `##`-level headings are considered. Deeper levels are inconsistently
listed across the corpus and enforcing them would be noise.

**Blockquoted headings are deliberately not enumerated here, and this is the
one enumerator where that is a decision rather than an oversight.**
`crossrefs._anchors_for` was widened on 2026-08-10 to reach `> ## Title`,
because an anchor set that omits a heading the renderer emits an `id` for
produces a false positive against a correct link. The same widening applied to
`_H2` produces **three** warnings, and all three are banner boxes — the
findings convention of opening a document with `> ## READ THIS FIRST`. A banner
is not a section, it is not navigated to, and requiring it in a table of
contents would make the convention itself the violation. The two enumerators
answer different questions: one asks *what can be linked to*, which the
renderer decides, and this one asks *what a reader needs to reach from the
top*, which the corpus's own conventions decide.
"""

from __future__ import annotations

import re

from ..corpus import Corpus, slugify
from ..registry import check
from ..report import WARNING, Violation

_H2 = re.compile(r"^##\s+(.*?)\s*#*\s*$")
_ANY_H = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_SELF_LINK = re.compile(r"\]\(#([^)]+)\)")

_TOC_TITLES = {"table of contents", "contents", "toc"}
#: Headings that conventionally sit outside a table of contents.
_EXEMPT = re.compile(r"^(tl;dr|table of contents|contents|toc)\b", re.IGNORECASE)


@check("toc-coverage", "A document with a table of contents lists every ## section.")
def run(corpus: Corpus, ctx: dict) -> list[Violation]:
    out: list[Violation] = []
    for doc in corpus.markdown():
        toc_start = None
        for i, line in enumerate(doc.lines):
            if i in doc.fenced:
                continue
            m = _ANY_H.match(line)
            if m and m.group(2).strip().lower().rstrip(":") in _TOC_TITLES:
                toc_start = i
                break
        if toc_start is None:
            continue

        # The TOC runs to the next heading of the same or higher level.
        level = len(_ANY_H.match(doc.lines[toc_start]).group(1))
        listed: set[str] = set()
        j = toc_start + 1
        while j < len(doc.lines):
            if j not in doc.fenced:
                hm = _ANY_H.match(doc.lines[j])
                if hm and len(hm.group(1)) <= level:
                    break
                listed.update(_SELF_LINK.findall(doc.lines[j]))
            j += 1

        if not listed:
            continue

        for i, line in enumerate(doc.lines):
            if i in doc.fenced or i <= toc_start:
                continue
            hm = _H2.match(line)
            if not hm:
                continue
            title = hm.group(1)
            if _EXEMPT.match(title.strip().lstrip("#").strip()):
                continue
            slug = slugify(title)
            if slug in listed:
                continue
            out.append(
                Violation(
                    check="toc-coverage",
                    severity=WARNING,
                    path=doc.relpath,
                    line=i + 1,
                    found=f"## {title.strip()}  (slug #{slug})",
                    expected=f"an entry in the table of contents at line {toc_start + 1}",
                    hint="section is unreachable from the top of the document",
                )
            )
    return out
