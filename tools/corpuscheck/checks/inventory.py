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
"""

from __future__ import annotations

import fnmatch
import re

from ..corpus import Corpus
from ..figures import inside_spans, struck_spans
from ..registry import check
from ..report import WARNING, Violation

_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
    "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20, "twenty-one": 21, "twenty-two": 22,
}


def _to_int(token: str) -> int | None:
    t = token.strip().lower().replace(",", "")
    if t.isdigit():
        return int(t)
    return _WORDS.get(t)


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
            ctx["skip"](
                "inventory-count",
                f"rule {rule['name']} disabled: glob {rule['glob']} matched nothing",
            )
            continue
        scope = rule.get("files", default_files)
        rx = re.compile(rule["pattern"], re.IGNORECASE)
        for doc in corpus.markdown():
            if not any(fnmatch.fnmatch(doc.relpath, p) for p in scope):
                continue
            for lineno, masked in enumerate(doc.masked_lines, start=1):
                if not masked.strip():
                    continue
                struck = struck_spans(masked)
                for m in rx.finditer(masked):
                    claimed = _to_int(m.group(1))
                    if claimed is None or claimed == actual:
                        continue
                    if inside_spans(struck, m.start(), m.end()):
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
    return out
