#!/usr/bin/env python3
"""Prove every numeric threshold in the checker is pinned by a fixture.

`selftest.py` proves each check *fires*. That is not the same as proving the
number a check compares against is the number the fixtures require, and the
difference is not academic. `catalog-line-count` carried `TOLERANCE = 2` for its
whole life; restoring it left the entire self-test green, because every planted
line-count drift in `known-bad` was at least 26 lines wide. The fixture could
not tell a tolerance of 2 from a tolerance of 0. It read as proof and was not
proof.

A threshold is **discriminated** when moving it one unit breaks the self-test.
That is the only evidence that a fixture sits against the threshold rather than
somewhere comfortably past it. This module moves each one and reports.

    python3 tools/threshold_probe.py             # every threshold, both directions
    python3 tools/threshold_probe.py -k orphan   # only thresholds matching a substring
    python3 tools/threshold_probe.py -v          # print the self-test output of each run

Exit status is 0 when every perturbation listed as `must-break` broke the
self-test and the restored tree passes.

## The stale-`.pyc` trap, which cost the prior audit a whole battery

`TOLERANCE = 0` and `TOLERANCE = 2` are the same number of bytes. CPython
validates a cached `.pyc` against the source's **mtime and size**, both at
one-second granularity, so an edit-and-restore inside the same second produces a
file whose mtime and size match a `.pyc` compiled from the *other* value. The
interpreter then loads the stale cache. What that looks like from outside is a
reversion battery in which failures leak across unrelated cases: a threshold
that was already restored still reports broken, and a perturbation that should
break reports clean.

Three defences, all applied together on every run below, because any one of them
alone is a single point of failure in a harness whose whole job is to be
trustworthy:

  * every `__pycache__` under `tools/` is deleted before each interpreter starts
  * the child runs with `PYTHONDONTWRITEBYTECODE=1`, so none is written back
  * the child runs with `-B`, which is the same instruction by another route

Do not remove these because the runs look fast enough without them. The failure
they prevent is silent, plausible, and points at the wrong file.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
SELFTEST = HERE / "selftest.py"

MUST_BREAK = "must-break"
MAY_HOLD = "may-hold"


@dataclass(frozen=True)
class Perturbation:
    #: What moving the threshold this way means, in one clause.
    label: str
    #: Exact text to substitute in.
    new: str
    #: `must-break` — a fixture is supposed to sit against the threshold in this
    #: direction, so the self-test must fail. `may-hold` — recorded for the
    #: matrix, not asserted, and the reason is in `why`.
    expect: str = MUST_BREAK
    why: str = ""


@dataclass(frozen=True)
class Threshold:
    name: str
    #: Path relative to the repository root.
    relpath: str
    #: Exact text that carries the threshold.
    old: str
    #: What the number governs.
    governs: str
    perturbations: tuple[Perturbation, ...] = field(default_factory=tuple)
    #: How many times `old` must occur. Normally 1 — an anchor that matches twice
    #: usually means it also matched a docstring, and rewriting prose alongside a
    #: constant is how a battery starts lying. Set it higher only when a single
    #: bound genuinely lives at more than one call site and they must move
    #: together; `numeric-provenance per-unit lookahead` is the one such case, and
    #: the fact that moving one of its two sites alone changes nothing is why it
    #: read as unpinnable at first.
    occurrences: int = 1


#: Every numeric threshold, tolerance, window, bound and distance the checker
#: compares against, and what one unit of movement means for each.
#:
#: Two shapes of threshold, and the direction that must break differs between
#: them. A **slack** bound (`TOLERANCE`, `MAX_EXEMPTION_DISTANCE`, a rounding
#: allowance) suppresses violations as it grows, so the fixture must sit just
#: past it and *widening* must break. A **window** bound (`MAX_ORPHAN_GAP`, a
#: run length, a word gap) admits violations as it grows, so widening reports
#: more and it is *narrowing* that must break — plus, where `known-good` carries
#: the construct just outside the window, widening breaks too.
THRESHOLDS: tuple[Threshold, ...] = (
    Threshold(
        name="catalog-line-count TOLERANCE",
        relpath="tools/corpuscheck/checks/catalog.py",
        # Anchored with its newlines: the docstring quotes `TOLERANCE = 0` too,
        # and a two-hit anchor would rewrite the prose along with the constant.
        old="\nTOLERANCE = 0\n",
        governs="how far a stated line count may drift from the file it describes",
        perturbations=(
            Perturbation("allow a 1-line drift", "\nTOLERANCE = 1\n"),
            Perturbation(
                "allow a 2-line drift (the value the audit restored)", "\nTOLERANCE = 2\n"
            ),
        ),
    ),
    Threshold(
        name="table-integrity MAX_ORPHAN_GAP",
        relpath="tools/corpuscheck/checks/tables.py",
        old="MAX_ORPHAN_GAP = 2",
        governs="how many blank lines after a table still count as inside it",
        perturbations=(
            Perturbation("reach one blank line further", "MAX_ORPHAN_GAP = 3"),
            Perturbation("reach one blank line less far", "MAX_ORPHAN_GAP = 1"),
        ),
    ),
    Threshold(
        name="table-integrity no-delimiter run length",
        relpath="tools/corpuscheck/checks/tables.py",
        old="if run_len >= 2:",
        governs="how many consecutive pipe rows with no delimiter constitute a table",
        perturbations=(
            Perturbation("demand a third row", "if run_len >= 3:"),
            Perturbation("speak on a lone pipe row", "if run_len >= 1:"),
        ),
    ),
    Threshold(
        name="dry-run-verdict MAX_EXEMPTION_DISTANCE",
        relpath="tools/corpuscheck/checks/dry_run_verdict.py",
        old="MAX_EXEMPTION_DISTANCE = 120",
        governs="how far an exemption token may sit from the claim it licenses",
        perturbations=(
            Perturbation("reach one character further", "MAX_EXEMPTION_DISTANCE = 121"),
            Perturbation("reach one character less far", "MAX_EXEMPTION_DISTANCE = 119"),
        ),
    ),
    Threshold(
        name="min_definitions (identifier-resolution, identifier-gap, register-range)",
        relpath="tools/corpuscheck/config.json",
        old='"min_definitions": 3,',
        governs="how few definitions disable a namespace entirely",
        perturbations=(
            Perturbation("demand a fourth definition", '"min_definitions": 4,'),
            Perturbation("accept a namespace of two", '"min_definitions": 2,'),
        ),
    ),
    Threshold(
        name="ratio-arithmetic _MIN_DECIMALS_BARE",
        relpath="tools/corpuscheck/checks/ratio_arithmetic.py",
        old="_MIN_DECIMALS_BARE = 2",
        governs="how many decimals a bare rate needs before it is read as a rate",
        perturbations=(
            Perturbation("demand a third decimal", "_MIN_DECIMALS_BARE = 3"),
            Perturbation("accept a single decimal", "_MIN_DECIMALS_BARE = 1"),
        ),
    ),
    Threshold(
        name="ratio-arithmetic rounding allowance",
        relpath="tools/corpuscheck/checks/ratio_arithmetic.py",
        old='        return 0.5 * 10 ** -len(text.split(".", 1)[1])',
        governs="how far a quoted rate may sit from the count beside it",
        perturbations=(
            Perturbation(
                "allow a whole unit in the last place",
                '        return 1.5 * 10 ** -len(text.split(".", 1)[1])',
            ),
            Perturbation(
                "allow four tenths of a unit",
                '        return 0.4 * 10 ** -len(text.split(".", 1)[1])',
                expect=MAY_HOLD,
                why="considered and deliberately not pinned. 0.5 is not a tuning knob "
                "but the definition of 'quoted to this many places', so the only "
                "meaningful neighbour is a whole unit — and that direction is pinned "
                "above. Pinning the narrow side needs a known-good rate whose residual "
                "lands in the sliver between 0.4 and 0.5 ulp, which asserts on "
                "floating-point behaviour at the bound rather than on the rule",
            ),
        ),
    ),
    Threshold(
        name="ratio-arithmetic count-then-rate word gap",
        relpath="tools/corpuscheck/checks/ratio_arithmetic.py",
        old=r"]*){0,4}[,;\s*~]*",
        governs="how many words may sit between a count and its parenthesised rate",
        perturbations=(
            Perturbation("reach one word further", r"]*){0,5}[,;\s*~]*"),
            Perturbation("reach one word less far", r"]*){0,3}[,;\s*~]*"),
        ),
    ),
    Threshold(
        name="ratio-arithmetic rate-then-count word gap",
        relpath="tools/corpuscheck/checks/ratio_arithmetic.py",
        old=r"\s+){0,3}",
        governs="how many words may precede the count inside the parenthesis",
        perturbations=(
            Perturbation("reach one word further", r"\s+){0,4}"),
            Perturbation("reach one word less far", r"\s+){0,2}"),
        ),
    ),
    Threshold(
        name="register-range ranges-listed-together count",
        relpath="tools/corpuscheck/checks/register_ranges.py",
        old="            in_list = len({m.group(1) for m in found}) >= 2",
        governs="how many distinct registers on one line make it a register summary",
        perturbations=(
            Perturbation(
                "demand a third register",
                "            in_list = len({m.group(1) for m in found}) >= 3",
            ),
            Perturbation(
                "accept a lone register range",
                "            in_list = len({m.group(1) for m in found}) >= 1",
                expect=MAY_HOLD,
                why="considered: 1 makes `in_list` vacuous, which is the requirement "
                "the rule dropped on purpose — a lone range needs the parenthesis "
                "instead. `known-good`'s subset ranges are all subsets rather than "
                "first-entry ranges, so they stay silent either way, and the "
                "counterexample that justified the requirement (research/14's struck "
                "'U-01 through U-06') is struck and therefore exempt",
            ),
        ),
    ),
    Threshold(
        name="numeric-provenance ratio4 integer-part cap",
        relpath="tools/corpuscheck/figures.py",
        old=r"(\d{1,3}\.\d{4})",
        governs="how many integer digits a four-decimal figure may carry before it is an identifier",
        perturbations=(
            Perturbation("admit a four-digit integer part", r"(\d{1,4}\.\d{4})"),
            Perturbation(
                "admit only a two-digit integer part",
                r"(\d{1,2}\.\d{4})",
                expect=MAY_HOLD,
                why="considered: every four-decimal figure this corpus measures is a "
                "rate or a recall in [0, 2), so no fixture carries a three-digit "
                "integer part to lose. The cap exists to exclude identifiers above "
                "it, not to admit anything at it",
            ),
        ),
    ),
    Threshold(
        name="numeric-provenance per-unit lookahead",
        relpath="tools/corpuscheck/figures.py",
        # Two call sites, and they must move together. `extract` uses the window to
        # drop "$0.08 per session-hour" and `rate_keys` uses it to remember that
        # 0.08 was named as a rate on this line, so a later bare "$0.08" back-
        # reference stays exempt. Narrow one and the other still exempts the
        # figure, which is why one-site perturbation reported this as unpinnable.
        old="m.end() + 24]",
        occurrences=2,
        governs="how far past a money figure a per-unit denominator may sit",
        perturbations=(
            Perturbation(
                "reach one character less far",
                "m.end() + 23]",
                expect=MAY_HOLD,
                why="not pinnable at one unit, and measured rather than assumed: "
                "`_PER_UNIT` is anchored at the slice start, and across the 63 money "
                "figures in this repository that carry a per-unit denominator its "
                "longest match is 6 characters, so the window has 18 characters of "
                "headroom no prose reaches — only ~18 spaces between a figure and "
                "its denominator would. The effective bound is 6, and the "
                "perturbation below pins that",
            ),
            Perturbation(
                "cut the window below the longest real denominator (6 → 5)",
                "m.end() + 5]",
            ),
        ),
    ),
    Threshold(
        name="sum-arithmetic rounding allowance",
        relpath="tools/corpuscheck/figures.py",
        old="    tol = 0.5 * 10 ** -max(decimal_places(shown.total), 0)",
        governs="how far a shown total may sit from its components",
        perturbations=(
            Perturbation(
                "allow a whole unit in the last place",
                "    tol = 1.5 * 10 ** -max(decimal_places(shown.total), 0)",
            ),
            Perturbation(
                "allow four tenths of a unit",
                "    tol = 0.4 * 10 ** -max(decimal_places(shown.total), 0)",
                expect=MAY_HOLD,
                why="same reasoning as the ratio-arithmetic allowance: half a unit in "
                "the last place is what the phrase means, and the widening direction "
                "is the one that can hide a wrong sum",
            ),
        ),
    ),
    Threshold(
        name="numeric-provenance multiplier rounding allowance",
        relpath="tools/corpuscheck/checks/numeric_provenance.py",
        old="_ROUNDING_ULPS = 0.5",
        governs="how far an authority multiplier may sit from the figure quoted from it",
        perturbations=(
            Perturbation("allow a whole unit in the last place", "_ROUNDING_ULPS = 1.5"),
            Perturbation(
                "allow six tenths of a unit",
                "_ROUNDING_ULPS = 0.6",
                expect=MAY_HOLD,
                why="the pinning fixture sits 0.6 ulp out, and floating-point equality "
                "at exactly the bound is not something to assert on",
            ),
        ),
    ),
    # Not a distance but a *set*, and it belongs here for the same reason the
    # distances do: the accept set is what decides whether a quantity is the kind
    # of thing a multiplier claim may be sourced from, and a set with an unpinned
    # member reads as coverage without being it. Four perturbations — one that
    # defeats typing altogether and one per accepted form.
    Threshold(
        name="numeric-provenance multiplier accept set",
        relpath="tools/corpuscheck/figures.py",
        old="_MULTIPLICATIVE = (_MULTIPLIER, _FACTOR_OF, _RATIO_OF, _RECIPROCAL)",
        governs="which authority shapes count as stating a multiplicative quantity",
        perturbations=(
            Perturbation(
                "admit any bare decimal, which is the untyped rule this replaced",
                '_MULTIPLICATIVE = (_MULTIPLIER, _FACTOR_OF, _RATIO_OF, _RECIPROCAL,\n'
                '                   re.compile(r"(?<![\\w.])(\\d+(?:\\.\\d+)?)"))',
            ),
            Perturbation(
                "drop `a factor of N`",
                "_MULTIPLICATIVE = (_MULTIPLIER, _RATIO_OF, _RECIPROCAL)",
            ),
            Perturbation(
                "drop `a ratio of N`",
                "_MULTIPLICATIVE = (_MULTIPLIER, _FACTOR_OF, _RECIPROCAL)",
            ),
            Perturbation(
                "drop the reciprocal `1/Nth`",
                "_MULTIPLICATIVE = (_MULTIPLIER, _FACTOR_OF, _RATIO_OF)",
            ),
        ),
    ),
    Threshold(
        name="numeric-provenance multiplier suffix adjacency",
        relpath="tools/corpuscheck/figures.py",
        old=r'_MULTIPLIER = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)[×x](?![\w])")',
        governs="whether a multiplication sign must touch its digits to be a suffix",
        perturbations=(
            Perturbation(
                "admit one space, turning the binary operator into a suffix",
                r'_MULTIPLIER = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)\s?[×x](?![\w])")',
            ),
        ),
    ),
    Threshold(
        name="numeric-provenance money type gate",
        relpath="tools/corpuscheck/checks/numeric_provenance.py",
        old="        hit = _money_typed",
        governs="whether a spend claim must be sourced from a figure marked as money",
        perturbations=(
            Perturbation(
                "accept any standalone occurrence of the digits, money or not",
                "        hit = _standalone",
            ),
        ),
    ),
)


def _purge_pycache(root: Path) -> int:
    """Delete every `__pycache__` under `root`. See the module docstring."""
    n = 0
    for path in sorted(root.rglob("__pycache__"), reverse=True):
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
            n += 1
    return n


def _run_selftest(verbose: bool) -> tuple[bool, str]:
    """Run `selftest.py` in a fresh interpreter that cannot read or write a `.pyc`."""
    _purge_pycache(HERE)
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    proc = subprocess.run(
        [sys.executable, "-B", str(SELFTEST)],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(HERE.parent),
    )
    if verbose:
        print(proc.stdout)
        if proc.stderr:
            print(proc.stderr, file=sys.stderr)
    return proc.returncode == 0, proc.stdout + proc.stderr


def _failures_of(output: str) -> list[str]:
    out: list[str] = []
    for line in output.splitlines():
        if line.startswith("  - "):
            out.append(line[4:])
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("-k", "--filter", default="", help="only thresholds whose name contains this")
    ap.add_argument("-v", "--verbose", action="store_true", help="print each self-test run")
    ap.add_argument(
        "--show-failures",
        action="store_true",
        help="print which self-test assertions a perturbation broke",
    )
    args = ap.parse_args(argv)

    root = HERE.parent
    problems: list[str] = []

    print("baseline — the unperturbed tree must pass")
    ok, output = _run_selftest(args.verbose)
    print(f"  {'PASS' if ok else 'FAIL'}  selftest on the restored thresholds")
    if not ok:
        print("\nthe tree does not pass before any perturbation; fix that first")
        if args.show_failures:
            for f in _failures_of(output):
                print(f"    - {f}")
        return 1

    selected = [t for t in THRESHOLDS if args.filter.lower() in t.name.lower()]
    if not selected:
        print(f"\nno threshold matches {args.filter!r}")
        return 1

    for th in selected:
        path = root / th.relpath
        original = path.read_text(encoding="utf-8")
        count = original.count(th.old)
        print(f"\n{th.name}")
        print(f"  {th.relpath} — {th.governs}")
        if count != th.occurrences:
            problems.append(
                f"{th.name}: anchor text occurs {count} time(s) in {th.relpath}, "
                f"expected exactly {th.occurrences}"
            )
            print(f"  FAIL  anchor text occurs {count} time(s), expected {th.occurrences}")
            continue
        if th.occurrences > 1:
            print(f"  note  one bound at {th.occurrences} call sites; they move together")

        for p in th.perturbations:
            try:
                path.write_text(original.replace(th.old, p.new), encoding="utf-8")
                passed, output = _run_selftest(args.verbose)
            finally:
                path.write_text(original, encoding="utf-8")

            broke = not passed
            if p.expect == MUST_BREAK:
                verdict = "PASS" if broke else "FAIL"
                note = "self-test failed, as it must" if broke else "SELF-TEST STILL GREEN — not pinned"
                if not broke:
                    problems.append(
                        f"{th.name}: {p.label} — self-test still passes, so no fixture "
                        "sits against this threshold"
                    )
            else:
                verdict = "note"
                note = ("self-test failed" if broke else "self-test held") + f" — {p.why}"
            print(f"  {verdict:<4}  {p.label:<48} {note}")
            if broke and args.show_failures:
                for f in _failures_of(output)[:6]:
                    print(f"          broke: {f}")

    print("\nrestored — the tree must pass again")
    ok, output = _run_selftest(args.verbose)
    print(f"  {'PASS' if ok else 'FAIL'}  selftest on the restored thresholds")
    if not ok:
        problems.append("the tree does not pass after the battery; a restore did not take")
        if args.show_failures:
            for f in _failures_of(output):
                print(f"    - {f}")

    print()
    if problems:
        print(f"{len(problems)} unpinned threshold(s) or harness problem(s):")
        for p in problems:
            print(f"  - {p}")
        return 1
    print(f"all {sum(len(t.perturbations) for t in selected)} perturbation(s) behaved as declared")
    return 0


if __name__ == "__main__":
    sys.exit(main())
