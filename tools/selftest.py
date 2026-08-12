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

#: (check, path, line, substring that must appear in `found`, `expected` or
#: `hint`). `expected` was omitted here while `_matches` had always read it, which
#: hid that a needle could hold a violation's expectation and not only its finding;
#: corrected 2026-08-11 when `preserved-evidence` needed exactly that.
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
    # The near-neighbour hint, which turns "this number is unsupported" into
    # "this number is probably 0.8961 mistyped". Both plants below were already
    # here and no needle read them, so a 2026-08-11 census found all three of
    # `figures.digit_neighbours`'s decision branches removable with every row
    # green — the two rows above stay satisfied by the hint's prefix. One row per
    # loop: a single substitution, and a transposition of adjacent digits, which
    # no substitution reaches. They also hold the wiring, which is two further
    # branches that census found unheld: `_nearest`'s kind guard and the `if
    # near` that appends the clause.
    ("numeric-provenance", "README.md", 36, "nearest authoritative figure(s): 0.8961"),
    (
        "numeric-provenance",
        "research/01-fixture-metrics.md",
        6,
        "nearest authoritative figure(s): 0.7681",
    ),
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
    # The filename branch, which until 2026-08-10 was held only in the direction
    # that passes: every planted filename label agreed with its target, so the
    # branch could have been deleted outright and Direction 1 would still have
    # been satisfied by the two `finding NNN` rows above. This row is what makes
    # resolving the target before comparing a change that can be checked.
    #
    # It holds the filename branch and it does **not** hold the numeric branch
    # eleven lines above it in the same function, which a 2026-08-11 census found
    # unheld in both of its decision points. This comment claimed otherwise by
    # sitting alone over the pair. The label below is a backticked filename, so
    # `_FILENAME_IN_TEXT` matches it and `_NUMERIC_TEXT` — which requires the label
    # be exactly two digits — never can, and control never enters the numeric
    # branch from this row. The row beneath it is the one that does.
    ("link-label", "README.md", 127, "research/01-fixture-metrics.md"),
    # The numeric branch, whose two decision points were `crossrefs#023` and
    # `crossrefs#024` in that census and were both removable with every row here
    # still green — `#024` was never evaluated at all. A bare two-digit label
    # enters at the first and violates at the second, because the target's
    # basename begins `14-` and the label reads `01`. Delete either branch and
    # this row goes quiet.
    ("link-label", "README.md", 133, "a filename beginning 01-"),
    ("identifier-resolution", "research/14-fixture-synthesis.md", 16, "D-99"),
    # `path` is pinned to a relpath, which the row above it deliberately left
    # unpinned with `None`. Until 2026-08-12 this violation carried the
    # configured `what` prose in the field every other violation prints an
    # openable file in, so the report's own grouping heading read `decision
    # register, research/14 §3.1` — a document that does not exist in this
    # fixture tree, whose register is `research/14-fixture-synthesis.md`. Revert
    # `path` to the config string and this row fails on the path alone.
    ("identifier-gap", "research/14-fixture-synthesis.md", 0, "D-03"),
    # And the label has to survive the move rather than be dropped: it now reads
    # in `found`, where prose belongs. Delete it from the message and this fails.
    ("identifier-gap", "research/14-fixture-synthesis.md", 0, "decision register, research/14 §3.1"),
    # The single-document branch of the register's own address, computed from
    # this run's corpus rather than read from config — which is what makes it
    # right in a fixture tree at all.
    ("identifier-gap", "research/14-fixture-synthesis.md", 0, "defined in research/14-fixture-synthesis.md"),
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
    # A prose count of a register against the specification that defines it.
    # Three rows, and the third is the one that matters.
    #
    # An ordinary stale count: the spec defines three success criteria and the
    # tasks header says four. Any comparison catches this.
    ("definition-count", "specs/001-fixture/tasks.md", 3, "claims 4"),
    # The extractor is blind — those FR bullets lost their bold markers — so the
    # truth it computes is 0 against a claim of 9. An implementation copying
    # `inventory-count`'s `if actual == 0: skip` reports this file clean.
    ("definition-count", "specs/001-fixture/tasks.md", 3, "no FR definition was found"),
    # The negative control, and the only row here a bare *equality* test also
    # passes: the claim is 0, the computed truth is 0, and they agree because
    # nothing was read. Drop the zero guard and this row goes quiet while the
    # two rows above keep passing, which is exactly how a vacuous check looks
    # from the outside.
    ("definition-count", "specs/001-fixture/tasks.md", 17, "no FR definition was found"),
    ("definition-count", "specs/001-fixture/tasks.md", 17, "means 'not found', not 'none exist'"),
    # A register's stated size against the range quoted beside it. Two rows,
    # because the pair is what the check reads and either half alone is already
    # guarded: `register-range` reads the range against the register and passes
    # here, and `definition-count` has no rule for owner decisions at all.
    ("count-versus-range", "specs/001-fixture/plan.md", 3, "three owner decisions"),
    ("count-versus-range", "specs/001-fixture/plan.md", 3, "the number of OD entries in OD-01 through OD-04"),
    # The lifecycle against the taxonomy, one row per branch of the check so
    # that removing any branch takes exactly one row away. The two markings are
    # the important pair: both are checked in the *forbidding* direction, and a
    # marking that only exempted would pass those two rows forever.
    ("lifecycle-taxonomy", "specs/001-fixture/data-model.md", 23, "turn_ceiling_reached is declared a member"),
    ("lifecycle-taxonomy", "specs/001-fixture/data-model.md", 24, "no_progress is marked 'owed', but it IS in"),
    ("lifecycle-taxonomy", "specs/001-fixture/data-model.md", 25, "denied_operation is marked 'struck', but it IS in"),
    ("lifecycle-taxonomy", "specs/001-fixture/data-model.md", 26, "carries status 'pending'"),
    ("lifecycle-taxonomy", "specs/001-fixture/data-model.md", 1, "declares terminated.operator_terminated, and the lifecycle does not mention it"),
    ("catalog-line-count", "research/README.md", 8, "14-fixture-synthesis.md"),
    ("catalog-line-count", "research/README.md", 13, "01-fixture-metrics.md"),
    ("catalog-line-count", "research/README.md", 13, "listed at 40 lines"),
    # Wrong by one — the size of the drift that shipped past `TOLERANCE = 2`.
    # Every other planted drift here is at least 26 lines, so without this row
    # the tolerance can be restored and the whole self-test still passes.
    ("catalog-line-count", "research/README.md", 15, "listed at 64 lines"),
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
        "threshold was met",
    ),
    (
        "dry-run-verdict",
        "specs/001-fixture/harness/probe/results/20260101T000000-dryrun/analysis.json",
        14,
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
    # Bytes-level attestation over preserved evidence. One row per kind, because
    # the five are different events with different remedies and a single smoke
    # test would let four of them rot. The two that matter most are the last
    # two: `unratified` is the rule that a rebuild does not clear the gate on
    # its own, which is the whole thing standing between this check and the
    # vacuity it was built to close, and `malformed` is the rule that the
    # record reconciles with itself before it is used to judge anything.
    (
        "preserved-evidence",
        "specs/001-fixture/harness/attested-edited/records/20260101T000000-run/manifest.json",
        1,
        "(edited)",
    ),
    (
        "preserved-evidence",
        "specs/001-fixture/harness/attested-edited/records/20260101T000000-run/records.jsonl",
        1,
        "(removed)",
    ),
    (
        "preserved-evidence",
        "specs/001-fixture/harness/attested-edited/records/20260101T000000-run/traces.jsonl",
        1,
        "(added)",
    ),
    (
        "preserved-evidence",
        "specs/001-fixture/harness/attested-unratified/attestation.json",
        1,
        "(unratified)",
    ),
    (
        "preserved-evidence",
        "specs/001-fixture/harness/attested-malformed/attestation.json",
        1,
        "declares 2 file(s), lists 1",
    ),
    # The second `malformed` branch, and it is here because a probe found it
    # removable with everything else still green. `file_count` alone covered one
    # of the two self-consistency rules, so deleting the summary-digest rule left
    # the self-test passing over a checker that would accept a hand-ratified
    # attestation disagreeing with its own entries — the sloppy-correction case,
    # which is the one `unratified` cannot see because the pin was moved on
    # purpose.
    (
        "preserved-evidence",
        "specs/001-fixture/harness/attested-malformed/attestation.json",
        1,
        "tree_sha256 does not cover the entries beside it",
    ),
    # A whole tree going missing, reported once against the tree instead of once
    # per attested file. The same probe that found the summary-digest rule
    # removable found this one removable too: with the tree absent, `present` is
    # empty and the per-file loop would have called every attested file
    # `removed`, so the self-test stayed green over a checker that had lost the
    # ability to say the directory itself was gone.
    (
        "preserved-evidence",
        "specs/001-fixture/harness/attested-treegone/records",
        1,
        "the attested tree is absent",
    ),
    # Matched against `expected` rather than `found`, and here because the arm
    # above does not hold the field it reads. A tree-level loss states how many
    # records the absent directory held; every other `removed` states the sentence
    # about a single file. Without this the per-kind sentence could be restored for
    # both and a deleted directory would again read "the attested file, present"
    # while pointing at a directory, with the self-test green.
    (
        "preserved-evidence",
        "specs/001-fixture/harness/attested-treegone/records",
        1,
        "2 attested file(s)",
    ),
    # The witness itself absent, which is a different event from every kind above
    # and was **unreportable** until the unit list gained a declared root. Scope
    # was keyed on `attestation.is_file()`, so a unit whose witness was missing or
    # whose path carried a typo was filtered out of the run and produced nothing:
    # `0 error(s), 0 warning(s)` and, because the per-check skip fires only when no
    # unit survives the filter, no skip line either. That is what a fully attested
    # tree prints, so a tree could be believed attested while nothing read it —
    # the class this whole check exists to close, reproduced inside the check. Key
    # scope back onto the witness and this row goes quiet.
    (
        "preserved-evidence",
        "specs/001-fixture/harness/attested-witnessgone/attestation.json",
        1,
        "the attestation is missing",
    ),
    # And the expectation beside it, because the arm above does not hold this
    # field. A missing witness states the tree it should have covered; restore the
    # per-kind sentence for it and a reader is told to look for `an attestation
    # that agrees with itself` when there is no attestation to agree with anything.
    (
        "preserved-evidence",
        "specs/001-fixture/harness/attested-witnessgone/attestation.json",
        1,
        "a committed attestation over specs/001-fixture/harness/attested-witnessgone/records",
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
    # The `57`s moved to `65` on 2026-08-11 when `14-fixture-synthesis.md` gained
    # the self-link that holds `toc.py`'s TOC-locating branch. It was appended at
    # end of file on purpose, so that line 44 and the two `table-integrity` rows
    # at line 55 did not move and only the document's own length did.
    ("line-count", "research/README.md", 8, "12", "65", "STALE"),
    ("line-count", "research/README.md", 13, "40", "14", "STALE"),
    ("line-count", "research/README.md", 15, "64", "65", "STALE"),
]

#: Sites in known-good that must be found and must be reported clean. The
#: hedged `(~57 lines)` is here because a `~` is accepted in the text and
#: ignored in the arithmetic; `(3 sections)` must not be found at all.
#:
#: Moved 3 → 5 on 2026-08-11, read off this guard's own message rather than
#: computed from a baseline and a delta. The two new ones are in
#: `specs/001-fixture/plan.md`, which arrived with the `count-versus-range`
#: unit: that check needs a fixture where a count and a range *agree* and a set
#: where each naive misreading would disagree, and two of those ranges are
#: whole-register claims this generator owns. Both are found and both are
#: clean, which is the state this arm asserts.
GEN_GOOD_SITES = 5

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


#: `lifecycle-taxonomy`'s two vacuity floors, and why they are here rather than
#: in a fixture corpus. Both are properties of a *whole corpus* — "the taxonomy
#: parsed to nothing" and "no scoped document declares anything" — so neither can
#: be planted in `known-bad` beside the row-level defects without destroying
#: them: emptying the taxonomy silences every row check, and deleting the table
#: silences all five. They are the branches that most need pinning, because each
#: one is a state in which the check reads nothing and two things that were never
#: read agree perfectly. Each entry perturbs a copy of `known-good` — the corpus
#: that must otherwise be silent — and requires exactly this violation out of it.
LIFECYCLE_FLOORS: list[tuple[str, str, str, str]] = [
    (
        "an unreadable taxonomy",
        "src/contracts/terminal.py",
        "# every binding gone; the module still imports and declares nothing\n",
        "no TAXONOMY member could be read out of this file",
    ),
    (
        "a taxonomy that does not parse",
        "src/contracts/terminal.py",
        "TAXONOMY = (\n",
        "this file does not parse as Python",
    ),
    (
        "a renamed header column",
        "specs/001-fixture/data-model.md",
        None,
        "no terminal-state branch table",
    ),
]


def _inventory_floor_selftest(verbose: bool) -> list[str]:
    """Prove a rule that stops matching announces itself instead of passing.

    Not plantable in a fixture corpus for the same reason the lifecycle floors
    are not: the state under test is *the absence of a claim*, and a fixture
    that contains no claim is indistinguishable from a fixture whose rule has
    rotted. So the claim is deleted out of a copy of `known-bad` — the corpus
    where the rule is known to be reading — and the announcement is required.

    The perturbation is the one the corpus performed on itself twice. `findings`
    stopped matching when its scoped documents ceased stating a total, and
    `committed-harnesses` stopped when its only in-scope site was struck. Both
    then ran silently through every green gate, which is the failure this arm
    makes impossible to repeat unnoticed.
    """
    failures: list[str] = []
    print("\nknown-bad (perturbed) — a rule whose site is deleted must announce")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "known-bad"
        shutil.copytree(BAD, root)
        readme = root / "README.md"
        before = readme.read_text(encoding="utf-8")
        # Both claims on the line go, the stale one and the correct one. A rule
        # reading a claim that happens to be right is still reading, so removing
        # only the violation would leave the rule live and test nothing.
        after = before.replace("Nine findings", "Some findings").replace(
            "five findings", "several findings"
        )
        for gone in ("Nine findings", "five findings"):
            assert gone in before, f"known-bad no longer states {gone!r}; this arm reads nothing"
            assert gone not in after, f"{gone!r} survived the perturbation"
        readme.write_text(after, encoding="utf-8")

        report, _ = run_checks(root)
        # The needle names the rule. `"findings" in r` was the earlier test and it
        # did not hold this arm: every rule's vacuity message ends in the same
        # boilerplate about zero findings meaning "nothing read" rather than
        # "nothing wrong", so the word `findings` occurs in *any* rule's
        # announcement. Under a neutralised `sites == 0` the `research-documents`
        # rule announced instead, satisfied both needles, and this arm went green
        # having never touched the rule it names — it asserted that something
        # announced, which was not the claim. `rule findings matched no live claim`
        # is the prefix `inventory.py` writes for this rule and no other.
        skips = [
            r
            for c, r in report.skipped
            if c == "inventory-count" and "rule findings matched no live claim" in r
        ]
        announced = [r for r in skips if "nothing read" in r]
        fired = [v for v in report.violations if v.check == "inventory-count"]

        ok = bool(announced)
        print(f"  {'PASS' if ok else 'FAIL'}  {'the deleted claim is announced':<32} "
              f"{'skip reported' if ok else 'SILENT'}")
        if not ok:
            failures.append(
                "inventory floor: deleting the only `findings` claim produced no skip; "
                f"skips were {[r for _, r in report.skipped] or 'none'}"
            )

        # The floor must not swallow the rules that are still reading.
        still = any("research-documents" in v.hint for v in fired)
        print(f"  {'PASS' if still else 'FAIL'}  {'the rules still reading still fire':<32} "
              f"{len(fired)} violation(s)")
        if not still:
            failures.append(
                "inventory floor: the surviving research-documents claim stopped firing"
            )
        if verbose:
            for _, r in report.skipped:
                print(f"        skip {r}")
    return failures


def _lifecycle_floor_selftest(verbose: bool) -> list[str]:
    """Prove the two states in which this check reads nothing are errors."""
    from corpuscheck import corpus as corpus_mod

    failures: list[str] = []
    print("\nknown-good (perturbed) — lifecycle-taxonomy's vacuity floors must fire")
    for label, relpath, replacement, needle in LIFECYCLE_FLOORS:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "known-good"
            shutil.copytree(GOOD, root)
            target = root / relpath
            if replacement is None:
                # The header column renamed, which is all it takes: the table
                # still renders, still reads correctly to a human, and is
                # invisible to the check that reconciles it.
                target.write_text(
                    target.read_text(encoding="utf-8").replace(
                        "| Terminal state |", "| Outcome |"
                    ),
                    encoding="utf-8",
                )
            else:
                target.write_text(replacement, encoding="utf-8")

            report, _ = run_checks(root)
            hits = [
                v
                for v in report.violations
                if v.check == "lifecycle-taxonomy" and needle in v.found
            ]
            ok = bool(hits)
            print(f"  {'PASS' if ok else 'FAIL'}  {label:<32} {needle!r}")
            if not ok:
                other = [v for v in report.violations if v.check == "lifecycle-taxonomy"]
                failures.append(
                    f"lifecycle floor: {label} produced no violation matching "
                    f"{needle!r} (got {[v.found for v in other] or 'nothing'})"
                )
            if verbose:
                for v in report.violations:
                    print(f"        {v.check} {v.path}:{v.line} {v.found}")
        # `run_checks` caches nothing across roots today; asserted rather than
        # assumed, because a cache keyed on relpath would make every floor above
        # read the previous corpus and pass for the wrong reason.
        assert not getattr(corpus_mod, "_CACHE", None), "corpus load grew a cache"
    return failures


# `slugify`'s two roles for one character. Every expected value below was read
# off GitHub's own rendered `id` attribute on 2026-08-10, not off its documented
# algorithm — the earlier claim rested on the documentation plus five authorings
# and was never checked against a renderer. The entries marked RENDERED are
# verbatim ids fetched from the contents endpoint; the rest follow the mechanism
# those establish. `*` and `~` need no case pair because their markup role and
# their literal role have the same outcome: both vanish, one consumed and one
# dropped for not being a word character. `_` is the only character where the two
# roles disagree, and it disagrees in the direction that invents an anchor no
# page has.
#
# **These are a pinned sample of an oracle that lives outside this file**, and
# both halves of that sentence carry an obligation.
#
# The oracle is
# `specs/001-discovery-validation/harness/slug-differential/`, which walks the
# corpus, fetches each document's rendered HTML, and compares position by
# position. Its three runs are dated to named commits — `2534` headings at
# `7a60dd3`, `2537` at `58a6277`, `2548` at `ac99926`, `0` diverged each time.
# The values below are a thirteen-case subset of that population, and the four
# added on 2026-08-10 are the three defects it found.
#
# This repository declines literal-string assertions on the ground that they are
# change-detectors an editor satisfies by updating both sides. **That objection
# does not reach these, and the reason is structural rather than a matter of
# degree.** It holds where both sides are ours, because the assertion then
# restates an internal fact and adds nothing. Here the expected value's authority
# is external: an editor who moves one to match a failing `slugify` is not
# restating a fact in two places, they are overwriting a measurement with a
# prediction, and the `RENDERED` label is the claim that edit falsifies.
#
# **Re-derivation at test time is unavailable and a committed id table is
# refused.** `tools/` is standard-library-only with no network, which is the
# stated reason the differential is not in this tree at all. Recording its output
# here instead was considered and declined at
# `slug-differential/README.md` § What it cannot reproduce: a recorded ground
# truth stops being ground truth the moment the renderer changes, and the
# renderer is not ours. So the honest form is the one
# `tools/README.md` § When a figure may be a live total prescribes for a figure
# nothing recomputes — a pinned sample, dated, naming the set and the oracle it
# was drawn from.
#
# What is recomputed is how many of them claim that provenance. `RENDERED_IDS`
# below is the `EXPECTED_PROOFS` pattern at sample scale: the count was prose
# reading "the two marked RENDERED" while six carried the label, stale by four
# and read by none of the nineteen corpus checks, because this is Python and
# they read markdown.
SLUG_ROLES = [
    # (heading, expected slug, what the case pins)
    (
        "## The advisory — `cite_advisor.py`",
        "the-advisory--cite_advisorpy",
        "RENDERED: literal `_` in a code span survives",
    ),
    (
        "#### _Note_: Multiple entry points",
        "note-multiple-entry-points",
        "RENDERED: `_emphasis_` is consumed as markup",
    ),
    (
        "## Bare snake_case_identifier heading",
        "bare-snake_case_identifier-heading",
        "intraword `_` outside code is literal",
    ),
    (
        "## A __strong__ heading",
        "a-strong-heading",
        "`__strong__` is consumed as markup",
    ),
    (
        "## Mixed `cite_advisor` and _emph_ together",
        "mixed-cite_advisor-and-emph-together",
        "both roles in one heading",
    ),
    (
        "## OD-26 — `terminated.denied_operation` is struck",
        "od-26--terminateddenied_operation-is-struck",
        "`.` dropped and `_` kept in one token",
    ),
    (
        "## An unpaired _ delimiter",
        "an-unpaired-_-delimiter",
        "an unpaired `_` is literal, not markup",
    ),
    (
        "## Strike ~~gone~~ heading",
        "strike-gone-heading",
        "`~` vanishes in either role",
    ),
    (
        "## Star *emph* heading",
        "star-emph-heading",
        "`*` vanishes in either role",
    ),
    # The three defects repaired on 2026-08-10. Each expected value is a
    # verbatim rendered `id`, and each case fires on the code it replaced:
    # the first two lost their hyphen to trimming after the character drop
    # instead of before, the third kept a `No` the renderer removes, and the
    # fourth lost a U+FE0F the renderer keeps.
    (
        "## Exception 1 — `adk-python` itself. **A genuine Class B target.** \u2605",
        "exception-1--adk-python-itself-a-genuine-class-b-target-",
        "RENDERED: a trailing dropped char keeps its hyphen",
    ),
    (
        "## \u26d4 QUARANTINED 2026-08-03 — this arm may not be scored",
        "-quarantined-2026-08-03--this-arm-may-not-be-scored",
        "RENDERED: a leading dropped char keeps its hyphen",
    ),
    (
        "## 1. Ground \u2460 — survives, and it is the ground actually carrying the deferral",
        "1-ground---survives-and-it-is-the-ground-actually-carrying-the-deferral",
        "RENDERED: a circled digit is dropped, not kept",
    ),
    (
        "## \u26a0\ufe0f THE EXPIRY CONDITION, WHICH IS THIS ENTRY'S MOST IMPORTANT CONTENT",
        "\ufe0f-the-expiry-condition-which-is-this-entrys-most-important-content",
        "RENDERED: U+FE0F survives the pictograph that carried it",
    ),
]


#: How many entries above carry a verbatim rendered `id` rather than a value
#: derived from the mechanism those entries establish. Live rather than dated,
#: because the line below recomputes it from the table itself; the prose form of
#: this number sat at "two" while six entries carried the label.
RENDERED_IDS = 6


#: What *defines* an identifier, pinned in both directions. No fixture corpus can
#: hold these: the failure they pin is a heading contributing a definition, and a
#: fixture that contains the heading also contains the definition, so the corpus
#: run cannot tell the two readings apart. The first row is the regression that
#: produced 304 false `identifier-resolution` errors under `--path` at `2979c31`
#: — a heading naming three identifiers in prose read as three definitions, which
#: is exactly `min_definitions`, so the namespace stayed enforced against a
#: phantom register. Each row is (markdown, namespace, expected identifiers, why).
DEFINITION_SHAPES: list[tuple[str, str, set[str], str]] = [
    (
        "### The execution environment — FR-048, FR-049 and FR-050's mechanisms",
        "FR",
        set(),
        "a heading naming identifiers in prose defines none",
    ),
    ("### OD-01 — ADK's role", "OD", {"OD-01"}, "a heading leading with one defines it"),
    ("### **OD-02** — a bolded lead", "OD", {"OD-02"}, "bold markup on the lead"),
    ("### ~~D-05~~ — superseded", "D", {"D-05"}, "a struck lead keeps its row"),
    ("# E19 — verifier vs judge", "E", {"E19"}, "the harness README form"),
    (
        "### OD-31 — the experiment is renumbered **E19** and keeps **E8**",
        "E",
        set(),
        "a lead of one namespace does not define another it cites",
    ),
    (
        "- **FR-018**: Analysis MUST operate on copies",
        "FR",
        {"FR-018"},
        "the bold-lead bullet",
    ),
    ("| D-17 | a register row |", "D", {"D-17"}, "the register table's first cell"),
    (
        "| a cell of prose mentioning D-17 | x |",
        "D",
        set(),
        "prose in a first cell does not define",
    ),
    (
        "```\n### FR-001 — inside a fence\n```",
        "FR",
        set(),
        "a fenced heading defines nothing",
    ),
]


def _slug_role_selftest(verbose: bool) -> list[str]:
    """Prove `slugify` separates a character's markup role from its literal one."""
    from corpuscheck.corpus import slugify

    failures: list[str] = []
    print("\nslugify — markup role and literal role, both directions")
    width = max(len(why) for _, _, why in SLUG_ROLES)
    for heading, expected, why in SLUG_ROLES:
        got = slugify(heading)
        ok = got == expected
        print(f"  {'PASS' if ok else 'FAIL'}  {why:<{width}}  {got}")
        if not ok:
            failures.append(f"slugify({heading!r}) == {got!r}, expected {expected!r}")
        if verbose:
            print(f"        heading {heading!r}")

    # The sample's provenance claim, counted rather than described. An expectation
    # bent to match a failing `slugify` keeps its RENDERED label and stays silent
    # here; one that is honestly demoted, or a new pin added without a run behind
    # it, moves this count and says so.
    rendered = sum(1 for _, _, why in SLUG_ROLES if why.startswith("RENDERED:"))
    ok = rendered == RENDERED_IDS
    print(
        f"  {'PASS' if ok else 'FAIL'}  {'the pinned sample states its provenance':<{width}}  "
        f"{rendered} of {len(SLUG_ROLES)} verbatim from the renderer"
    )
    if not ok:
        failures.append(
            f"{rendered} entries are marked RENDERED, RENDERED_IDS says {RENDERED_IDS}. "
            "Each RENDERED value is a verbatim id from the slug-differential harness; "
            "if one was added or demoted on purpose, update RENDERED_IDS and name the "
            "run it came from."
        )
    return failures


def _definition_shape_selftest(verbose: bool) -> list[str]:
    """Prove which markdown shapes define an identifier, and which only cite one."""
    from corpuscheck.corpus import ROLE_CONSUMER, Document, build_masked
    from corpuscheck.checks.identifiers import _namespaces, definitions_in
    from corpuscheck.runner import load_config

    patterns = _namespaces(load_config())
    failures: list[str] = []
    print("\ndefinition shapes — what defines an identifier and what merely cites one")
    width = max(len(why) for _, _, _, why in DEFINITION_SHAPES)
    for markdown, ns, expected, why in DEFINITION_SHAPES:
        lines = markdown.split("\n")
        masked, fenced = build_masked(lines)
        doc = Document(
            path=Path("fixture.md"),
            relpath="fixture.md",
            role=ROLE_CONSUMER,
            text=markdown,
            lines=lines,
            masked_lines=masked,
            fenced=fenced,
        )
        got = definitions_in(doc, patterns)[ns]
        ok = got == expected
        shown = ", ".join(sorted(got)) if got else "—"
        print(f"  {'PASS' if ok else 'FAIL'}  {why:<{width}}  {ns}: {shown}")
        if not ok:
            failures.append(
                f"{markdown!r} defines {sorted(got)} in {ns}, expected {sorted(expected)}"
            )
        if verbose:
            print(f"        markdown {markdown!r}")
    return failures


def _gap_path_selftest(verbose: bool) -> list[str]:
    """Prove `identifier-gap` names an openable file for a register that has none.

    Neither fixture tree can hold this. Measured 2026-08-12, no namespace spans
    more than one document in either of them — every register there is defined by
    exactly one file — so the corpus rows above hold only the single-document
    branch, and reverting the plural branch leaves them all green. The real
    corpus is where the plurality lives: seven of its nine namespaces are defined
    by more than one document and `E` by thirty, which is the same reason the
    namespace-to-owning-document map recorded in `tools/README.md` cannot have
    one document per namespace as its schema.

    Two properties, and the first is the one the repair is for: `path` carries a
    relpath, never the configured `what` prose. The second is that a register
    with no single file says so instead of picking one silently.
    """
    from corpuscheck.corpus import ROLE_CONSUMER, Corpus, Document, build_masked
    from corpuscheck.checks.identifiers import gaps
    from corpuscheck.runner import load_config

    config = load_config()

    def doc(relpath: str, body: str) -> Document:
        lines = body.split("\n")
        masked, fenced = build_masked(lines)
        return Document(
            path=Path(relpath), relpath=relpath, role=ROLE_CONSUMER,
            text=body, lines=lines, masked_lines=masked, fenced=fenced,
        )

    # D-02 is defined nowhere, so the union D-01, D-03, D-04 has a hole in it,
    # and the three definitions are split across two documents on purpose.
    corpus = Corpus(
        root=Path("/nonexistent-selftest-root"),
        documents=[
            doc("beta/second-register.md", "- **D-04**: split across two files\n"),
            doc("alpha/first-register.md", "- **D-01**: one\n- **D-03**: three\n"),
        ],
    )
    skips: list[tuple[str, str]] = []
    ctx = {"config": config, "skip": lambda c, r: skips.append((c, r))}
    found = gaps(corpus, ctx)

    failures: list[str] = []
    print("\nidentifier-gap — a register with no single file still names a file")
    checks: list[tuple[str, bool, str]] = []
    if len(found) != 1:
        failures.append(f"identifier-gap returned {len(found)} violation(s) on the split register, expected 1")
        print(f"  FAIL  one violation for the split D register  got {len(found)}")
        return failures
    v = found[0]
    checks.append((
        "`path` is the densest defining document, not the config prose",
        v.path == "alpha/first-register.md",
        v.path,
    ))
    checks.append((
        "`path` is not the configured `what` string",
        v.path != config["identifier_namespaces"]["D"]["what"],
        v.path,
    ))
    checks.append((
        "the plural branch says the register has no single file",
        "has no single file: 2 documents" in v.expected,
        v.expected,
    ))
    checks.append((
        "both defining documents are named",
        "alpha/first-register.md defines 2" in v.expected
        and "beta/second-register.md defines 1" in v.expected,
        v.expected,
    ))
    checks.append((
        "the `what` label survives the move, in the message",
        config["identifier_namespaces"]["D"]["what"] in v.found,
        v.found,
    ))
    checks.append(("the gap itself is still reported", "D-02" in v.found, v.found))
    width = max(len(why) for why, _, _ in checks)
    for why, ok, shown in checks:
        print(f"  {'PASS' if ok else 'FAIL'}  {why:<{width}}")
        if not ok:
            failures.append(f"identifier-gap: {why} — got {shown!r}")
        if verbose:
            print(f"        {shown!r}")
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

    # Direction 4: the two states in which `lifecycle-taxonomy` reads nothing.
    # Neither is plantable in a fixture corpus; see LIFECYCLE_FLOORS.
    failures.extend(_lifecycle_floor_selftest(args.verbose))

    # Direction 4b: the state in which an `inventory-count` rule reads nothing.
    # Direction 1 proves the check fires; it cannot prove that each of its six
    # config-driven rules still has something to read, and two of them did not.
    failures.extend(_inventory_floor_selftest(args.verbose))

    # Direction 5: the generator that now writes two of those claim classes.
    failures.extend(_generator_selftest(args.verbose))

    # Direction 6: the anchor slugger, which no fixture corpus can pin in both
    # directions at once — a fixture proves a link resolves, and a link that
    # resolves to a wrong-but-self-consistent slug is exactly the failure here.
    failures.extend(_slug_role_selftest(args.verbose))

    # Direction 7: the definition index's shapes. A fixture corpus cannot pin
    # these — a fixture holding the heading holds the definition too, so the
    # corpus run cannot separate "this heading defines FR-048" from "this
    # heading mentions it". That conflation is what let a prose heading stand in
    # for a register under `--path`.
    failures.extend(_definition_shape_selftest(args.verbose))

    # Direction 8: `identifier-gap`'s `path` field, and its plural-register
    # branch. Neither fixture tree defines any namespace in more than one
    # document, so the corpus rows reach only the single-document branch.
    failures.extend(_gap_path_selftest(args.verbose))

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
