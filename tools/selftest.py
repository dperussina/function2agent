#!/usr/bin/env python3
"""Prove the checks fire, and prove they stay quiet.

A validator that passes everything because its regex never matches is the exact
failure mode this repository keeps hitting, so a green run of `check_corpus.py`
against the corpus is not evidence of anything. This is the evidence.

Two directions, both required:

  known-bad   Every check must produce at least one violation, and for most
              checks a specific one identified by file, line and content. If a
              check produces nothing here it is broken or vacuous.

  known-good  No check may produce anything. The good tree deliberately
              contains every construct that has produced a false positive —
              an escaped pipe in a table cell, a DOI, a preprint identifier, a
              vendor price, a subset range in running prose, an HTTP status
              pair, a fenced block full of decoys, a stub artifact saying so on
              every line that names a number, and a live run stating the same
              outcome the dry run beside it is forbidden to state.

    python3 tools/selftest.py            # both directions
    python3 tools/selftest.py -v         # plus every violation found
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import gen_claims  # noqa: E402
from corpuscheck.registry import all_checks  # noqa: E402
from corpuscheck.report import format_text  # noqa: E402
from corpuscheck.runner import run_checks  # noqa: E402

HERE = Path(__file__).resolve().parent
BAD = HERE / "fixtures" / "known-bad"
GOOD = HERE / "fixtures" / "known-good"

#: (check, path, line, substring that must appear in `found` or `hint`).
#: line=None means "anywhere in that file".
EXPECTED: list[tuple[str, str, int | None, str]] = [
    # 1 — numeric claim provenance
    ("numeric-provenance", "README.md", 8, "0.7734"),
    ("numeric-provenance", "README.md", 8, "appears nowhere else"),
    ("numeric-provenance", "README.md", 11, "$41.03"),
    ("numeric-provenance", "README.md", 11, "also in: specs/001-fixture/plan.md"),
    # A figure that a substring test read as authoritative because a finding
    # contains `0.53127`. Exactness is the whole assertion: drop the standalone
    # match and this row goes quiet while the number stays unsourced.
    ("numeric-provenance", "README.md", 32, "0.5312"),
    ("numeric-provenance", "README.md", 32, "appears nowhere else"),
    # And one the *alias* rule read as authoritative: a finding writing `89.6%`
    # covered six different four-decimal ratios while a one-decimal percentage
    # was an alias. Every alias must be lossless.
    ("numeric-provenance", "README.md", 36, "0.8964"),
    ("numeric-provenance", "README.md", 36, "appears nowhere else"),
    # Multipliers. The lookup for this kind cannot be exact — `2.9×` is
    # legitimately quoted from a finding writing `2.94×`, and `known-good`
    # carries that case — so all three of these are about *where* the looseness
    # is allowed to reach.
    #
    # Left edge: an unanchored substring is unanchored at both ends, so `3.7×`
    # was satisfied by a finding writing `13.7×`. This is the negative fixture
    # for the anchor: drop it and the row goes quiet.
    ("numeric-provenance", "README.md", 48, "3.7×"),
    # Right edge: a left anchor alone accepts `4.8×` from `4.8999×`, which
    # rounds to 4.9. Sharing a prefix is not being the same figure.
    ("numeric-provenance", "README.md", 52, "4.8×"),
    # And the bound on the right edge, planted six tenths of a unit out so that
    # widening the allowance to a whole unit makes this row disappear.
    ("numeric-provenance", "README.md", 57, "3.4×"),
    # Type, which is a different question from reach and was the actual cause of
    # the `3.7×` defect. Both rows below are inside every distance bound above —
    # the authority value is 0.013 and 0.0 units away respectively — and both are
    # unsourced anyway, because what the authority states there is not a ratio.
    # Revert the lookup from `figures.multiplier_values` to a text match and both
    # go quiet.
    ("numeric-provenance", "README.md", 108, "2.6×"),  # authority: `$2.6134`, a spend
    ("numeric-provenance", "README.md", 112, "5.3×"),  # authority: bare `5.3`, a count
    # The symmetric case. No live instance in the real corpus, so this fixture is
    # the only thing holding it: restore `_standalone` for money and it is silent.
    ("numeric-provenance", "README.md", 119, "$7.42"),
    # 2 — markdown table integrity
    ("table-integrity", "research/14-fixture-synthesis.md", 28, "blank line inside the table"),
    ("table-integrity", "research/14-fixture-synthesis.md", 28, "renders as body text"),
    ("table-integrity", "research/14-fixture-synthesis.md", 36, "2 cell(s)"),
    ("table-integrity", "research/14-fixture-synthesis.md", 40, "no delimiter row"),
    # Two blank lines, not one. The gap bound used to stop at one and this row
    # was invisible; nothing follows it that would make it a new table.
    ("table-integrity", "research/14-fixture-synthesis.md", 55, "blank line inside the table"),
    ("table-integrity", "research/14-fixture-synthesis.md", 55, "line 57 renders as body text"),
    # Exactly two pipe rows, which is the shortest run the delimiter rule speaks
    # on. Raise its floor by one and this block goes quiet.
    ("table-integrity", "README.md", 73, "2 consecutive pipe rows"),
    # 3 — cross-reference resolution
    ("link-target", "README.md", 21, "research/99-nope.md"),
    ("link-anchor", "README.md", 22, "#9-the-conclusion"),
    ("link-label", "README.md", 20, "finding 010"),
    ("link-label", "README.md", 20, "findings/010-"),
    ("identifier-resolution", "research/14-fixture-synthesis.md", 16, "D-99"),
    ("identifier-gap", None, None, "D-03"),
    # 4 — findings numbering
    ("findings-numbering", "specs/001-fixture/findings/005-epsilon.md", None, "prefix 005"),
    ("findings-numbering", "specs/001-fixture/findings/005-zeta.md", None, "prefix 005"),
    ("findings-numbering", None, None, "no document numbered 003"),
    ("findings-numbering", "README.md", 23, "finding 013"),
    # Additional classes
    ("ratio-arithmetic", "research/01-fixture-metrics.md", 6, "53/69 = 0.7681"),
    ("ratio-arithmetic", "research/01-fixture-metrics.md", 9, "15/69"),
    ("ratio-arithmetic", "research/01-fixture-metrics.md", 11, "16,655/16,777"),
    # Four cases planted one unit outside the bound that catches each, so that
    # widening any of the four by a unit takes one of them away.
    #   85 — seven tenths of a unit out, inside a whole one
    #   88 — two decimals, the coarsest bare rate read as a rate at all
    #   94 — four words between count and parenthesised rate
    #   99 — three words inside the parenthesis before the count
    ("ratio-arithmetic", "README.md", 85, "60/69 = 0.8695"),
    ("ratio-arithmetic", "README.md", 88, "60/69 = 0.92"),
    ("ratio-arithmetic", "README.md", 94, "15 of 69 measured Python route handlers (12.7%)"),
    ("ratio-arithmetic", "README.md", 99, "0.9987 (matched against ast 16,655 of 16,777)"),
    ("numeric-provenance", "README.md", 85, "0.8695"),
    ("sum-arithmetic", "README.md", 14, "18.15"),
    ("register-range", "README.md", 18, "D-01 … D-02"),
    ("register-range", "README.md", 18, "D-01 … D-04"),
    # A stale range inside a correction record. `gen_claims.py` refuses to
    # write this one, so the check is the only thing that fires on it.
    ("register-range", "README.md", 24, "D-01 … D-03"),
    ("identifier-resolution", "README.md", 24, "D-03"),
    # Exactly two ranges on the line, which is the whole bound for reading it as
    # a register summary rather than a sentence that happens to name a range.
    ("register-range", "README.md", 81, "D-01 … D-02"),
    ("inventory-count", "README.md", 3, "claims 3"),
    # The `findings` rule, whose pattern demanded a trailing comma the natural
    # sentence never has, and which therefore had no site in the real corpus.
    ("inventory-count", "README.md", 28, "claims 9"),
    ("inventory-count", "README.md", 28, "rule findings"),
    ("catalog-line-count", "research/README.md", 8, "14-fixture-synthesis.md"),
    ("catalog-line-count", "research/README.md", 13, "01-fixture-metrics.md"),
    ("catalog-line-count", "research/README.md", 13, "listed at 40 lines"),
    # Wrong by one — the size of the drift that shipped past `TOLERANCE = 2`.
    # Every other planted drift here is at least 26 lines, so without this row
    # the tolerance can be restored and the whole self-test still passes.
    ("catalog-line-count", "research/README.md", 15, "listed at 56 lines"),
    ("catalog-line-count", "research/README.md", 15, "drift of +1"),
    ("toc-coverage", "research/14-fixture-synthesis.md", 44, "table of contents"),
    # Verdict-shaped claims in a run that called no model. One entry per pattern,
    # because a rule of seven alternatives is seven rules and a single smoke test
    # would let six of them rot.
    (
        "dry-run-verdict",
        "specs/001-fixture/harness/probe/results/20260101T000000-dryrun/analysis.json",
        11,
        "is a headline feature",
    ),
    (
        "dry-run-verdict",
        "specs/001-fixture/harness/probe/results/20260101T000000-dryrun/analysis.json",
        12,
        "clears the gate",
    ),
    (
        "dry-run-verdict",
        "specs/001-fixture/harness/probe/results/20260101T000000-dryrun/analysis.json",
        13,
        "materially better",
    ),
    (
        "dry-run-verdict",
        "specs/001-fixture/harness/probe/results/20260101T000000-dryrun/analysis.json",
        None,
        "declares dry_run: true",
    ),
    (
        "dry-run-verdict",
        "specs/001-fixture/harness/probe/results/20260101T000000-dryrun/report.md",
        13,
        "H2 confirmed",
    ),
    (
        "dry-run-verdict",
        "specs/001-fixture/harness/probe/results/20260101T000000-dryrun/report.md",
        14,
        "statistically significant",
    ),
    (
        "dry-run-verdict",
        "specs/001-fixture/harness/probe/results/20260101T000000-dryrun/report.md",
        16,
        "VERDICT:",
    ),
    # The two exemptions, shaped to fit through themselves. `avoid` contains the
    # disclosure token `void`, and a prohibition token used to exempt every claim
    # on its line however far away — the `H2 confirmed` this line does disclaim
    # is still exempt, and that is the control.
    (
        "dry-run-verdict",
        "specs/001-fixture/harness/probe/results/20260101T000000-dryrun/report.md",
        20,
        "H2 supported",
    ),
    (
        "dry-run-verdict",
        "specs/001-fixture/harness/probe/results/20260101T000000-dryrun/report.md",
        22,
        "VERDICT:",
    ),
    # A real disclosure and a real verdict 121 characters apart — one character
    # past the proximity bound. Its opposite number sits in `known-good` at
    # exactly 120, so the bound is pinned from both sides: widen it by one and
    # this line goes quiet, narrow it by one and that one turns false positive.
    (
        "dry-run-verdict",
        "specs/001-fixture/harness/probe/results/20260101T000000-dryrun/report.md",
        28,
        "VERDICT:",
    ),
]


#: `gen_claims.py` sites that must be found in known-bad, identified the same
#: way the check fixtures are: by file, line, the wrong value, the value the
#: generator computes, and whether it is allowed to write it.
#:
#:   STALE   the generator owns the whole claim and rewrites it
#:   MANUAL  the claim sits in a correction record where the digits are half of
#:           it, so the generator reports and refuses
GEN_EXPECTED: list[tuple[str, str, int, str, str, str]] = [
    ("register-range", "README.md", 18, "02", "04", "STALE"),
    ("register-range", "README.md", 24, "03", "04", "MANUAL"),
    ("line-count", "research/README.md", 8, "12", "57", "STALE"),
    ("line-count", "research/README.md", 13, "40", "14", "STALE"),
    ("line-count", "research/README.md", 15, "56", "57", "STALE"),
]

#: Sites in known-good that must be found and must be reported clean. The
#: hedged `(~57 lines)` is here because a `~` is accepted in the text and
#: ignored in the arithmetic; `(3 sections)` must not be found at all.
GEN_GOOD_SITES = 3

_DIGITS = re.compile(r"\d+")


def _generator_selftest(verbose: bool) -> list[str]:
    """Three directions: it fires, it stays quiet, and it writes only digits."""
    failures: list[str] = []
    config = gen_claims.load_config(None)

    # Direction 1: every expected site is found in known-bad, with the right
    # replacement and the right disposition.
    sites = gen_claims.collect(BAD, config)
    print("\nknown-bad — the generator must find every stale claim")
    for gen, path, line, current, generated, status in GEN_EXPECTED:
        hit = next(
            (
                s
                for s in sites
                if s.generator == gen and s.relpath == path and s.line == line
            ),
            None,
        )
        ok = hit is not None and (hit.current, hit.generated, hit.status) == (
            current,
            generated,
            status,
        )
        got = f"{hit.current}→{hit.generated} {hit.status}" if hit else "not found"
        print(
            f"  {'PASS' if ok else 'FAIL'}  {gen:<14} {path}:{line:<3} "
            f"{current}→{generated} {status:<6}  got {got}"
        )
        if not ok:
            failures.append(f"generator: {gen} at {path}:{line} expected {current}→{generated} {status}, got {got}")

    # Direction 2: silence on known-good, including the hedged count and the
    # parenthetical that follows a link without being a length.
    good = gen_claims.collect(GOOD, config)
    stale_good = [s for s in good if s.stale]
    print("\nknown-good — the generator must find sites and call them all clean")
    ok = len(good) == GEN_GOOD_SITES and not stale_good
    print(
        f"  {'PASS' if ok else 'FAIL'}  {len(good)} site(s) (expected {GEN_GOOD_SITES}), "
        f"{len(stale_good)} stale (expected 0)"
    )
    if not ok:
        for s in stale_good:
            failures.append(f"generator false positive: {s.relpath}:{s.line} {s.current}→{s.generated}")
        if len(good) != GEN_GOOD_SITES:
            failures.append(f"generator found {len(good)} known-good sites, expected {GEN_GOOD_SITES}")

    # Direction 3: write into a copy of known-bad and hold the result to three
    # properties — every writable claim settles, nothing but digits moves, and
    # a second pass is a no-op. Idempotence is the one a generator most often
    # fails silently, and a corpus gate that rewrites on every run is useless.
    print("\nknown-bad (copy) — write, then prove idempotence and prose preservation")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "known-bad"
        shutil.copytree(BAD, root)
        before_text = {s.relpath: (root / s.relpath).read_text(encoding="utf-8") for s in sites}

        changed = gen_claims.rewrite(root, gen_claims.collect(root, config))
        for relpath, (_, after) in changed.items():
            (root / relpath).write_text(after, encoding="utf-8")

        after_sites = gen_claims.collect(root, config)
        residue = [s for s in after_sites if s.stale and not s.manual]
        left = [s for s in after_sites if s.stale and s.manual]
        second = gen_claims.rewrite(root, after_sites)

        # Only digits may differ, on every line the generator touched.
        prose_ok = True
        for relpath, text in before_text.items():
            b = text.split("\n")
            a = (root / relpath).read_text(encoding="utf-8").split("\n")
            if len(a) != len(b):
                prose_ok = False
                break
            for x, y in zip(b, a):
                if x != y and _DIGITS.sub("", x) != _DIGITS.sub("", y):
                    prose_ok = False
                    break

        for label, ok, detail in (
            ("every writable claim settles", not residue, f"{len(residue)} still stale"),
            ("the MANUAL claim is untouched", len(left) == 1, f"{len(left)} left for a human"),
            ("second pass writes nothing", not second, f"{len(second)} file(s) would change again"),
            ("only digits changed", prose_ok, "a non-digit character moved"),
        ):
            print(f"  {'PASS' if ok else 'FAIL'}  {label:<34} {'' if ok else detail}")
            if not ok:
                failures.append(f"generator: {label} — {detail}")

        if verbose:
            for s in after_sites:
                print(f"        {s.status:<6} {s.relpath}:{s.line} {s.current}")
    return failures


def _matches(v, path, line, needle) -> bool:
    if path is not None and v.path != path:
        return False
    if line is not None and v.line != line:
        return False
    return needle in v.found or needle in v.expected or needle in v.hint


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    failures: list[str] = []

    bad, _ = run_checks(BAD)
    good, _ = run_checks(GOOD)

    if args.verbose:
        print("=" * 72)
        print("known-bad")
        print("=" * 72)
        print(format_text(bad))
        print("=" * 72)
        print("known-good")
        print("=" * 72)
        print(format_text(good))

    # Direction 1: every registered check must fire somewhere in known-bad.
    fired = {v.check for v in bad.violations}
    width = max(len(c.name) for c in all_checks())
    print("known-bad — every check must fire")
    for chk in all_checks():
        n = sum(1 for v in bad.violations if v.check == chk.name)
        ok = chk.name in fired
        print(f"  {'PASS' if ok else 'FAIL'}  {chk.name:<{width}}  {n} violation(s)")
        if not ok:
            failures.append(f"check {chk.name} produced nothing on known-bad")

    # Direction 2: the specific expected violations.
    print("\nknown-bad — specific violations")
    for chk, path, line, needle in EXPECTED:
        hit = any(v.check == chk and _matches(v, path, line, needle) for v in bad.violations)
        loc = f"{path}:{line}" if path else "(corpus-level)"
        print(f"  {'PASS' if hit else 'FAIL'}  {chk:<{width}}  {loc:<48} {needle!r}")
        if not hit:
            failures.append(f"expected {chk} at {loc} matching {needle!r}, not found")

    # Direction 3: silence on known-good.
    print("\nknown-good — no check may fire")
    if good.violations:
        for v in sorted(good.violations, key=lambda x: x.sort_key()):
            print(f"  FAIL  {v.check:<{width}}  {v.path}:{v.line}  {v.found}")
            failures.append(f"false positive: {v.check} at {v.path}:{v.line} — {v.found}")
    else:
        print(f"  PASS  {len(all_checks())} checks, 0 violations")

    # Direction 4: the generator that now writes two of those claim classes.
    failures.extend(_generator_selftest(args.verbose))

    print()
    if failures:
        print(f"{len(failures)} failure(s):")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("all self-tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
