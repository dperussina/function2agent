#!/usr/bin/env python3
"""Apply one removal-proof tamper to one file, and say precisely what happened.

`tests/removal_proofs.sh` names a source location and a literal string to edit
out of it. The string is matched against source text, so it rots whenever the
source moves — and a tamper that matches nothing applies no edit, which used to
leave the test passing for the ordinary reason and the proof reported as an
ordinary result. Fifteen proofs reached that state in a single day.

Two of the fifteen rotted for a reason no amount of care prevents: adding a
second entry to a Go map made gofmt realign it, turning `classPrivate: true,`
into `classPrivate:  true,`, and every tamper matching the single-space form
stopped applying. The next edit that changes the longest key in that map would
do it again.

So matching here is **exact first, whitespace-tolerant second**, and a match is
required to be **unique**:

* An exact match, occurring exactly once, is applied as written. Nothing about
  the historical behaviour changes for a tamper that is still correct.
* Failing that, both sides are normalized — runs of spaces and tabs *after* the
  first non-whitespace character of a line collapse to one space, and trailing
  horizontal whitespace is dropped — and the edit is applied at the mapped span
  in the original text. This is the gofmt case, and it heals rather than
  reporting.
* Leading indentation is **not** normalized. It is the one whitespace that
  carries meaning in the languages here, and collapsing it would let a tamper
  land at a differently-nested site that happens to read the same.
* Zero matches is `NO_MATCH` and more than one is `AMBIGUOUS`. Both are
  failures. The second is new: `str.replace` edits every occurrence, so a
  tamper that had silently grown a second site was breaking the test somewhere
  the proof does not claim.

A tamper may declare multiplicity by passing an explicit count, which is how
`s.replace(a, b, 1)` states that `a` legitimately occurs more than once.

After the edit, a Python file must still compile. A tamper that produces a
SyntaxError makes every test in the module fail, which reads as "the mechanism
was load-bearing" and is not evidence of anything.
"""

from __future__ import annotations

import argparse
import pathlib
import sys

OK_EXACT = "OK_EXACT"
OK_NORMALIZED = "OK_NORMALIZED"
NO_MATCH = "NO_MATCH"
AMBIGUOUS = "AMBIGUOUS"
UNCHANGED = "UNCHANGED"
SNIPPET_ERROR = "SNIPPET_ERROR"
SYNTAX_BROKEN = "SYNTAX_BROKEN"

# The shell reads these. Keep them in step with `tests/removal_proofs.sh`.
EXIT_CODES = {
    OK_EXACT: 0,
    OK_NORMALIZED: 0,
    NO_MATCH: 3,
    AMBIGUOUS: 4,
    UNCHANGED: 5,
    SNIPPET_ERROR: 6,
    SYNTAX_BROKEN: 7,
}


class TamperError(Exception):
    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


def normalize(text: str) -> tuple[str, list[int]]:
    """Collapse intra-line whitespace runs, preserving leading indentation.

    Returns the normalized text and an offset map: `offsets[i]` is the index in
    `text` of the character that produced `normalized[i]`, with a sentinel at
    the end so a half-open span maps back to a half-open span.
    """
    out: list[str] = []
    offsets: list[int] = []
    i = 0
    n = len(text)
    in_indent = True
    while i < n:
        c = text[i]
        if c == "\n":
            out.append(c)
            offsets.append(i)
            i += 1
            in_indent = True
            continue
        if c in " \t":
            if in_indent:
                out.append(c)
                offsets.append(i)
                i += 1
                continue
            j = i
            while j < n and text[j] in " \t":
                j += 1
            # Whitespace that runs to a line end or to the end of the text is
            # dropped: gofmt and every Python formatter strip it, so keeping it
            # significant would make trailing spaces a rot cause of their own.
            if j >= n or text[j] == "\n":
                i = j
                continue
            out.append(" ")
            offsets.append(i)
            i = j
            continue
        out.append(c)
        offsets.append(i)
        i += 1
        in_indent = False
    offsets.append(n)
    return "".join(out), offsets


def _find_all(haystack: str, needle: str) -> list[int]:
    if not needle:
        return []
    found = []
    start = 0
    while True:
        at = haystack.find(needle, start)
        if at < 0:
            return found
        found.append(at)
        # Overlapping occurrences are still separate sites for our purposes.
        start = at + 1


class Source(str):
    """A `str` whose `replace` insists it matched, and matched once.

    Substituted for the plain string the tamper snippets operate on, so the
    snippets themselves are unchanged — the tamper strings in
    `tests/removal_proofs.sh` are still the literal source text an author would
    write, and every one of them is byte-identical to what it was.
    """

    mode: str = OK_EXACT
    # Set to reproduce the pre-2026-08-03 behaviour, in which whitespace was
    # significant. Used to score this change against the rots it is answering.
    exact_only: bool = False

    def replace(self, old, new, count=-1):  # type: ignore[override]
        exact = _find_all(self, old)
        wanted = None if count in (-1, None) else int(count)

        if wanted is None:
            if len(exact) == 1:
                return self._spliced(exact[0], exact[0] + len(old), new, OK_EXACT)
            if len(exact) > 1:
                raise TamperError(
                    AMBIGUOUS,
                    f"{len(exact)} exact occurrences of {old!r}; a tamper must name one "
                    f"site, or declare its multiplicity with an explicit count",
                )
        else:
            if len(exact) >= wanted:
                text = str(self)
                for _ in range(wanted):
                    text = text.replace(old, new, 1)
                return self._replaced(text, OK_EXACT)

        if self.exact_only:
            raise TamperError(
                NO_MATCH,
                f"no exact occurrence of {old!r}; the source moved under this proof",
            )

        # No exact match (or not enough of them). Try the whitespace-tolerant
        # form, which is the gofmt-realignment case.
        norm_hay, offsets = normalize(str(self))
        norm_needle, _ = normalize(old)
        hits = _find_all(norm_hay, norm_needle)
        if not hits:
            raise TamperError(
                NO_MATCH,
                f"no occurrence of {old!r}, with or without whitespace normalization; "
                f"the source moved under this proof",
            )
        if wanted is None and len(hits) > 1:
            raise TamperError(
                AMBIGUOUS,
                f"{len(hits)} whitespace-insensitive occurrences of {old!r}; "
                f"the tamper does not identify one site",
            )
        if wanted is not None and len(hits) < wanted:
            raise TamperError(
                NO_MATCH,
                f"{len(hits)} occurrences of {old!r}, fewer than the {wanted} "
                f"this tamper declares",
            )
        take = 1 if wanted is None else wanted
        text = str(self)
        # Splice back-to-front so earlier offsets stay valid.
        for at in reversed(hits[:take]):
            start = offsets[at]
            end = offsets[at + len(norm_needle)]
            text = text[:start] + new + text[end:]
        return self._replaced(text, OK_NORMALIZED)

    def _spliced(self, start: int, end: int, new: str, mode: str) -> "Source":
        return self._replaced(str(self)[:start] + new + str(self)[end:], mode)

    def _replaced(self, text: str, mode: str) -> "Source":
        out = Source(text)
        out.exact_only = self.exact_only
        # A normalized match anywhere in the snippet is the interesting fact.
        out.mode = OK_NORMALIZED if OK_NORMALIZED in (self.mode, mode) else mode
        return out


def apply_snippet(
    text: str, snippet: str, path: str = "<source>", exact_only: bool = False
) -> tuple[str, str]:
    """Run one tamper snippet against `text`. Returns (new_text, mode)."""
    source = Source(text)
    source.exact_only = exact_only
    namespace: dict = {"s": source, "__name__": "__tamper__"}
    try:
        exec(snippet, namespace)  # noqa: S102 — the snippet is repository source
    except TamperError:
        raise
    except Exception as exc:  # pragma: no cover — a broken snippet is a bug, not a result
        raise TamperError(SNIPPET_ERROR, f"the tamper snippet raised {exc!r}") from exc

    result = namespace.get("s")
    if not isinstance(result, str):
        raise TamperError(SNIPPET_ERROR, "the tamper snippet did not leave a string in `s`")
    if str(result) == text:
        raise TamperError(UNCHANGED, "the tamper ran but changed nothing")

    mode = getattr(result, "mode", OK_EXACT)

    if path.endswith(".py"):
        try:
            compile(str(result), path, "exec")
        except SyntaxError as exc:
            raise TamperError(
                SYNTAX_BROKEN,
                f"the tampered file no longer parses ({exc.msg} at line {exc.lineno}); "
                f"every test in it would fail for a reason the proof does not claim",
            ) from exc

    return str(result), mode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path")
    parser.add_argument("snippet")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report what would happen; write nothing",
    )
    args = parser.parse_args(argv)

    p = pathlib.Path(args.path)
    if not p.is_file():
        print(f"NO_FILE {args.path}", file=sys.stderr)
        return 8
    try:
        text, mode = apply_snippet(p.read_text(), args.snippet, str(p))
    except TamperError as exc:
        print(f"{exc.code} {exc.detail}", file=sys.stderr)
        return EXIT_CODES[exc.code]
    if not args.dry_run:
        p.write_text(text)
    print(mode)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
