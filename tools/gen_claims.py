#!/usr/bin/env python3
"""Generate the corpus's derived claims. See tools/README.md § Generated claims.

Two claims in this corpus are hand-written summaries of facts that are
machine-readable from an artifact sitting right beside them:

  * a document's **line count**, quoted in an index that lives in a different
    file — `research/README.md`'s `Lines` column and `.cursor/skills/README.md`'s
    inline ``(185 lines)``;
  * a **register's extent**, quoted as ``D-01 … D-22`` in prose, where the
    register itself is in `research/14-architecture-synthesis.md`.

`check_corpus.py` guards both with `catalog-line-count` and `register-range`.
Guarding is the wrong shape of solution for a fact nobody should be
transcribing: between them those two rules have been tripped and hand-repaired
at least eight times, and every repair was a human retyping a number a script
can read. This writes them instead.

    python3 tools/gen_claims.py             # rewrite in place; idempotent
    python3 tools/gen_claims.py --check     # exit 1 if any claim is stale
    python3 tools/gen_claims.py --diff      # show the edit, write nothing
    python3 tools/gen_claims.py --list      # every site, with status

**It rewrites the number and nothing else.** Each site is located as a
character span inside its line and only that span is replaced, so the sentence,
the table cell, the emphasis and the dated refresh log around it survive
byte-for-byte. A generator that re-emitted the sentence would be worse than the
hand-maintained version it replaces.

**A struck claim is history, not a site.** The house convention keeps a
superseded value visible inside `~~…~~` with a dated note beside it, so a claim
that has been struck is skipped entirely — rewriting it would delete the
correction.

**And some live claims it deliberately will not write.** A register range
sharing its line with a *struck range* sits in a correction record: the digits
say where the register ends and the dated note beside them says which entry
landed when, so substituting the digits alone would silence the signal that the
note needs a new line, converting a *detectable* staleness into an
*undetectable* inconsistency. Those are reported as `MANUAL` and left alone;
`--check` still fails on them.

**Line counts have no such case, and that is the difference in kind between the
two generators.** A document's length has no narrative half — nothing beside it
says *why* it is 806 lines — so every line-count site is writable. The test is
scoped to the claim class for that reason: a `Lines` row whose *Key findings*
cell happens to contain a strikethrough is not a correction record about the
length, and treating it as one silently froze two counts in
`research/README.md` before this was tightened.

Site detection is imported from `corpuscheck` rather than reimplemented. A
second definition of "what counts as a whole-register claim" would drift from
the first, and this repository has the scar tissue to prove it.
"""

from __future__ import annotations

import argparse
import difflib
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote

sys.path.insert(0, str(Path(__file__).resolve().parent))

from corpuscheck.checks.catalog import (  # noqa: E402
    _COUNT_HEADER,
    _INLINE_COUNT,
    _INT,
    _LINK_IN_CELL,
    _count_lines,
)
from corpuscheck.checks.identifiers import _collect_definitions, _namespaces  # noqa: E402
from corpuscheck.checks.register_ranges import _RANGE, _is_whole_register_claim  # noqa: E402
from corpuscheck.runner import load_config  # noqa: E402
from corpuscheck.corpus import (  # noqa: E402
    Corpus,
    is_delimiter_row,
    load,
    looks_like_table_row,
    split_row_spans,
)
from corpuscheck.figures import inside_spans, struck_spans  # noqa: E402

GENERATORS = ("line-count", "register-range")


@dataclass(frozen=True)
class Site:
    """One derived claim, located precisely enough to rewrite in place."""

    generator: str
    relpath: str
    line: int  # 1-based
    start: int  # character offset of the digits within the line
    end: int
    current: str
    generated: str
    manual: bool
    what: str  # what the number is a fact about, for the report

    @property
    def stale(self) -> bool:
        return self.current != self.generated

    @property
    def status(self) -> str:
        if not self.stale:
            return "OK"
        return "MANUAL" if self.manual else "STALE"


def _struck_ranges(masked: str) -> list[tuple[int, int]]:
    """Spans of `~~…~~` on this line that contain a register range."""
    struck = struck_spans(masked)
    return [
        (s, e)
        for s, e in struck
        if any(inside_spans([(s, e)], m.start(), m.end()) for m in _RANGE.finditer(masked))
    ]


def display_path(target: Path, root: Path) -> str:
    """`target` relative to `root`, tolerating a root that is not resolved.

    `target` has been through `.resolve()` so a symlinked root — `/var` on
    macOS, a `--root` given as a relative path — makes a bare `relative_to`
    raise. A crash while building a label is a worse outcome than a long label.
    """
    for base in (root, root.resolve()):
        try:
            return target.relative_to(base).as_posix()
        except ValueError:
            continue
    return target.as_posix()


def _renumber(current: str, value: int) -> str:
    """Keep the site's zero-padding unless the new value needs more digits."""
    return f"{value:0{max(len(current), len(str(value)))}d}"


# --------------------------------------------------------------------------
# line-count — a document's length, quoted in an index in another file
# --------------------------------------------------------------------------


def collect_line_counts(corpus: Corpus) -> list[Site]:
    out: list[Site] = []
    for doc in corpus.markdown():
        out.extend(_inline_counts(doc, corpus))
        out.extend(_column_counts(doc, corpus))
    return out

def _count_site(doc, corpus, target: Path, lineno: int, start: int, end: int, digits: str) -> Site | None:
    actual = _count_lines(target)
    if actual is None:
        return None
    return Site(
        generator="line-count",
        relpath=doc.relpath,
        line=lineno,
        start=start,
        end=end,
        current=digits,
        generated=str(actual),
        # Always writable. A length has no narrative half to keep in step.
        manual=False,
        what=display_path(target, corpus.root),
    )


def _inline_counts(doc, corpus) -> list[Site]:
    """``[`skill`](skill/SKILL.md) (185 lines)`` — the skills roster's shape."""
    out: list[Site] = []
    for i, line in enumerate(doc.lines):
        if i in doc.fenced:
            continue
        struck = struck_spans(doc.masked_lines[i])
        for m in _INLINE_COUNT.finditer(line):
            # A struck count is a superseded value the convention keeps visible.
            if inside_spans(struck, m.start(), m.end()):
                continue
            target = (doc.path.parent / unquote(m.group(1))).resolve()
            if not target.is_file():
                continue
            site = _count_site(
                doc, corpus, target, i + 1, m.start(3), m.end(3), m.group(3).replace(",", "")
            )
            if site is not None:
                out.append(site)
    return out


def _column_counts(doc, corpus) -> list[Site]:
    """A `Lines` column in an index table — `research/README.md`'s shape."""
    out: list[Site] = []
    lines = doc.lines
    n = len(lines)
    i = 0
    while i < n - 1:
        if (
            i in doc.fenced
            or not looks_like_table_row(lines[i])
            or not is_delimiter_row(lines[i + 1])
        ):
            i += 1
            continue
        header = [text for text, _, _ in (split_row_spans(lines[i]) or [])]
        col = next((k for k, c in enumerate(header) if _COUNT_HEADER.match(c)), None)
        if col is None:
            i += 2
            continue

        j = i + 2
        while j < n and j not in doc.fenced and looks_like_table_row(lines[j]):
            cells = split_row_spans(lines[j]) or []
            if len(cells) > col and cells:
                link = _LINK_IN_CELL.search(cells[0][0])
                text, cell_start, _ = cells[col]
                digits = _INT.match(text)
                if link and digits:
                    start = cell_start + digits.start(1)
                    end = cell_start + digits.end(1)
                    target = (doc.path.parent / unquote(link.group(1))).resolve()
                    # Struck-ness is tested against the count's own span, not
                    # the row: a strikethrough in the Key findings cell is not
                    # a correction about the document's length.
                    if target.is_file() and not inside_spans(
                        struck_spans(doc.masked_lines[j]), start, end
                    ):
                        site = _count_site(
                            doc,
                            corpus,
                            target,
                            j + 1,
                            start,
                            end,
                            digits.group(1).replace(",", ""),
                        )
                        if site is not None:
                            out.append(site)
            j += 1
        i = j
    return out


# --------------------------------------------------------------------------
# register-range — "D-01 … D-22", against the register in research/14
# --------------------------------------------------------------------------


def register_maxima(corpus: Corpus, config: dict) -> dict[str, int]:
    defined = _collect_definitions(corpus, _namespaces(config))
    return {
        ns: max(int(re.sub(r"\D", "", i)) for i in ids)
        for ns, ids in defined.items()
        if len(ids) >= config["min_definitions"]
    }


def collect_register_ranges(corpus: Corpus, config: dict) -> list[Site]:
    defined = _collect_definitions(corpus, _namespaces(config))
    maxima = {
        ns: max(int(re.sub(r"\D", "", i)) for i in ids)
        for ns, ids in defined.items()
        if len(ids) >= config["min_definitions"]
    }
    out: list[Site] = []
    for doc in corpus.markdown():
        for lineno, masked in enumerate(doc.masked_lines, start=1):
            found = list(_RANGE.finditer(masked))
            if not found:
                continue
            # A line listing several registers' ranges is a register summary
            # regardless of punctuation — the check's rule, reused verbatim.
            in_list = len({m.group(1) for m in found}) >= 2
            struck = _struck_ranges(masked)
            for m in found:
                ns, lo, hi = m.group(1), int(m.group(2)), int(m.group(3))
                if ns not in maxima or hi <= lo:
                    continue
                # A struck range is a superseded claim the house convention
                # keeps visible on purpose. It is not a site; it is history,
                # and rewriting it would delete the correction.
                if inside_spans(struck, m.start(), m.end()):
                    continue
                if not _is_whole_register_claim(masked, m, in_list):
                    continue
                out.append(
                    Site(
                        generator="register-range",
                        relpath=doc.relpath,
                        line=lineno,
                        start=m.start(3),
                        end=m.end(3),
                        current=m.group(3),
                        generated=_renumber(m.group(3), maxima[ns]),
                        # A live range sharing a line with a struck one sits in
                        # a correction record: the digits are half the claim
                        # and the dated note beside them is the other half.
                        manual=bool(struck),
                        what=f"{ns} register, {len(defined[ns])} entries",
                    )
                )
    return out


# --------------------------------------------------------------------------


def collect(root: Path, config: dict, only: tuple[str, ...] = GENERATORS) -> list[Site]:
    corpus = load(root, config)
    sites: list[Site] = []
    if "line-count" in only:
        sites += collect_line_counts(corpus)
    if "register-range" in only:
        sites += collect_register_ranges(corpus, config)
    return sorted(sites, key=lambda s: (s.relpath, s.line, s.start))


def rewrite(root: Path, sites: list[Site]) -> dict[str, tuple[str, str]]:
    """Apply every writable stale site. Returns {relpath: (before, after)}.

    Edits run right-to-left within a line so earlier spans keep their offsets.
    """
    edits: dict[str, list[Site]] = {}
    for s in sites:
        if s.stale and not s.manual:
            edits.setdefault(s.relpath, []).append(s)

    changed: dict[str, tuple[str, str]] = {}
    for relpath, group in edits.items():
        path = root / relpath
        before = path.read_text(encoding="utf-8")
        rows = before.split("\n")
        for s in sorted(group, key=lambda x: (-x.line, -x.start)):
            idx = s.line - 1
            if idx >= len(rows):
                raise SystemExit(f"{relpath}:{s.line} is past the end of the file")
            row = rows[idx]
            if row[s.start : s.end] != s.current:
                raise SystemExit(
                    f"{relpath}:{s.line} moved under the generator "
                    f"(expected {s.current!r} at column {s.start + 1})"
                )
            rows[idx] = row[: s.start] + s.generated + row[s.end :]
        after = "\n".join(rows)
        if after != before:
            changed[relpath] = (before, after)
    return changed


def _report(sites: list[Site], *, verbose: bool) -> None:
    width = max((len(s.relpath) for s in sites), default=0)
    for s in sites:
        if s.status == "OK" and not verbose:
            continue
        detail = f"{s.current} → {s.generated}" if s.stale else s.current
        print(f"  {s.status:<6} {s.generator:<14} {s.relpath:<{width}}:{s.line}  {detail}  ({s.what})")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="write nothing; exit 1 if any claim is stale")
    mode.add_argument("--diff", action="store_true", help="write nothing; print the unified diff")
    mode.add_argument("--list", action="store_true", help="print every site and its status")
    ap.add_argument("--only", action="append", choices=GENERATORS, help="restrict to one generator; repeatable")
    ap.add_argument("--root", default=".", help="repository root")
    ap.add_argument("--config", default=None, help="path to config.json")
    args = ap.parse_args(argv)

    root = Path(args.root).resolve()
    config = load_config(Path(args.config) if args.config else None)
    only = tuple(args.only) if args.only else GENERATORS

    sites = collect(root, config, only)
    stale = [s for s in sites if s.stale]
    manual = [s for s in stale if s.manual]
    writable = [s for s in stale if not s.manual]

    if args.list:
        print(f"{len(sites)} generated claim(s) across {len({s.relpath for s in sites})} file(s)")
        _report(sites, verbose=True)
        return 0

    if args.diff:
        for relpath, (before, after) in sorted(rewrite(root, sites).items()):
            sys.stdout.writelines(
                difflib.unified_diff(
                    before.splitlines(keepends=True),
                    after.splitlines(keepends=True),
                    fromfile=f"a/{relpath}",
                    tofile=f"b/{relpath}",
                )
            )
        _report(manual, verbose=False)
        return 1 if stale else 0

    if args.check:
        found = {name: 0 for name in only}
        for s in sites:
            found[s.generator] = found.get(s.generator, 0) + 1
        silent = sorted(name for name, count in found.items() if count == 0)

        print(f"{len(sites)} generated claim(s); {len(stale)} stale ({len(manual)} needing a human)")
        for name in sorted(found):
            print(f"  {found[name]:>4}  {name}")
        _report(stale, verbose=False)

        # A generator that matches nothing reports nothing stale, and "0 stale"
        # is what a clean tree also prints. The two are indistinguishable in the
        # total, so the totals are broken out above and a silent generator is an
        # error here. This is not hypothetical: the sites are found by a regex
        # over prose, and renaming a marker or reflowing a table takes a
        # generator to zero without touching this file. There is no threshold
        # to tune — the floor is one, because a generator with no sites is
        # either dead or looking in the wrong place, and both are defects.
        if silent:
            print()
            for name in silent:
                print(
                    f"ERROR: the {name!r} generator matched no sites. It cannot "
                    "report a stale claim it cannot find, so its 0 above means "
                    "'not looked at', not 'correct'."
                )
            print(
                "\nEither its marker syntax changed, or the documents it reads "
                "moved. Run --list to see what is still matching."
            )

        if manual:
            print("\nMANUAL sites sit in a correction record. The digits are half the claim:")
            print("update the range *and* the dated note beside it, then re-run --check.")
        if stale:
            print("\nrun `python3 tools/gen_claims.py` to write the rest")
        return 1 if (stale or silent) else 0

    changed = rewrite(root, sites)
    for relpath, (_, after) in sorted(changed.items()):
        (root / relpath).write_text(after, encoding="utf-8")

    # Idempotence is a property worth asserting rather than assuming: re-collect
    # from what was just written and require every writable site to be settled.
    residue = [s for s in collect(root, config, only) if s.stale and not s.manual]
    if residue:
        print("generator is not idempotent — these are still stale after writing:")
        _report(residue, verbose=False)
        return 2

    print(f"{len(sites)} generated claim(s); wrote {len(writable)} across {len(changed)} file(s)")
    _report(writable, verbose=False)
    if manual:
        print(f"\n{len(manual)} site(s) left for a human — the digits are half the claim:")
        _report(manual, verbose=False)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
