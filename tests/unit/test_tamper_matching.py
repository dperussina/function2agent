"""The removal proofs' own removal proof: does the tamper matcher still match?

`tests/removal_proofs.sh` is this repository's evidence that its tests are
load-bearing. It decays, because a tamper string is matched against source text
and any edit to that source can stop it applying. Fifteen proofs reached that
state on 2026-08-03 — thirteen found at once, then two more.

The two later ones are the instructive pair and they are reproduced below
verbatim. Adding a second entry to `exemptibleClasses` made gofmt realign the
map, `classPrivate: true,` became `classPrivate:  true,`, and both proofs
matching the single-space form silently applied nothing. Nobody wrote a wrong
string; the formatter moved the source underneath two correct ones.

So this module asserts both directions, in the shape `tools/selftest.py` uses
for the corpus checks:

**Must heal.** Whitespace that only a formatter cares about must not be able to
break a proof. The historical needle is checked against the historical realigned
source, and is required to apply.

**Must refuse.** Tolerance that swallows a genuine miss would be worse than the
rot it replaces, so a needle matching nothing, a needle matching two sites, a
needle at the wrong nesting depth, and a tamper that leaves the source
unparseable must each be a named failure and not an edit.

The last test is the one that does the work day to day: it runs the static rot
check over the real proof file. That puts tamper rot inside the ordinary `pytest`
run, which is what the person who *causes* it runs — the harness itself needs a
Go toolchain, a Linux kernel and root, and is therefore not.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent.parent
PROOF_FILE = REPO / "tests" / "removal_proofs.sh"
CHECKER = REPO / "tools" / "check_tampers.py"
sys.path.insert(0, str(REPO / "tools"))

#: The proof set as it stands. Pinned rather than bounded, in the shape
#: `tools/selftest.py` pins `GEN_EXPECTED`: a number no tool can derive from
#: the file it is reading, held in the one place that knows which revision
#: this is.
#:
#: `check_tampers.py` carries the constant-free half of the floor — zero
#: extracted proofs is an error, and a declaration-shaped line that produced
#: no proof is an error — and deliberately carries no minimum count, because
#: `--proofs` exists to score older revisions that legitimately declare fewer.
#: This is the half that needs to know the number, so it lives here.
#:
#: Changing the proof set is meant to edit this line. That coupling is the
#: mechanism and not an inconvenience: a silent drop from 66 to 65 is the rot.
EXPECTED_PROOFS = 170

from tamper import (  # noqa: E402
    AMBIGUOUS,
    NO_MATCH,
    OK_EXACT,
    OK_NORMALIZED,
    SYNTAX_BROKEN,
    UNCHANGED,
    TamperError,
    apply_snippet,
)

# The map as gofmt rewrote it when the second entry landed. Two spaces after
# `classPrivate:`, one after the longer `classLoopback:`.
REALIGNED_MAP = (
    "var exemptibleClasses = map[string]bool{\n"
    "\tclassPrivate:  true,\n"
    "\tclassLoopback: true,\n"
    "}\n"
)

# The two tampers exactly as they stood at 1618266^, written against the
# one-entry map and matching nothing after the realignment.
ROTTED_TAMPERS = [
    's = s.replace("\\tclassPrivate: true,\\n", "")',
    's = s.replace("\\tclassPrivate: true,\\n", '
    '"\\tclassPrivate: true,\\n\\tclassLinkLocal: true,\\n\\tclassMetadata: true,\\n")',
]


@pytest.mark.parametrize("snippet", ROTTED_TAMPERS, ids=["exemption", "link-local"])
def test_the_gofmt_realignment_that_rotted_two_proofs_no_longer_rots_them(snippet):
    """Both real rots of 2026-08-03, against the source that caused them."""
    out, mode = apply_snippet(REALIGNED_MAP, snippet, "addresses.go")
    assert mode == OK_NORMALIZED, (
        "the needle carries one space and the source carries two, so this must "
        "match on the whitespace-tolerant path"
    )
    assert out != REALIGNED_MAP, "the tamper applied nothing; this is the rot itself"
    assert "classPrivate" not in out or "classLinkLocal" in out


def test_the_drift_is_announced_rather_than_swallowed():
    """Healing quietly would trade a loud rot for a silent one.

    `OK_NORMALIZED` is what makes the harness print `drifted` and the static
    check emit a warning. A matcher that returned `OK_EXACT` here would leave
    the proof surviving on tolerance with nobody told to repair the string.
    """
    _, mode = apply_snippet(REALIGNED_MAP, ROTTED_TAMPERS[0], "addresses.go")
    assert mode != OK_EXACT


def test_a_correct_tamper_still_matches_exactly():
    """Nothing changes for a proof that has not rotted."""
    snippet = 's = s.replace("\\tclassLoopback: true,\\n", "")'
    _, mode = apply_snippet(REALIGNED_MAP, snippet, "addresses.go")
    assert mode == OK_EXACT


def test_a_needle_that_matches_nothing_is_refused():
    snippet = 's = s.replace("\\tclassNoSuchThing: true,\\n", "")'
    with pytest.raises(TamperError) as caught:
        apply_snippet(REALIGNED_MAP, snippet, "addresses.go")
    assert caught.value.code == NO_MATCH


def test_a_needle_that_matches_two_sites_is_refused():
    """`str.replace` edits every occurrence, so this used to pass unnoticed.

    A tamper that has quietly grown a second site is no longer removing the
    mechanism it names — it is removing that one and something else — and the
    test failing afterwards says nothing about either.
    """
    doubled = "if False:\n    pass\nif False:\n    pass\n"
    snippet = 's = s.replace("if False:", "if True:")'
    with pytest.raises(TamperError) as caught:
        apply_snippet(doubled, snippet, "x.go")
    assert caught.value.code == AMBIGUOUS


def test_a_declared_multiplicity_is_still_allowed():
    """An explicit count is an author saying the string legitimately repeats."""
    doubled = "if False:\n    pass\nif False:\n    pass\n"
    snippet = 's = s.replace("if False:", "if True:", 1)'
    out, _ = apply_snippet(doubled, snippet, "x.go")
    assert out.count("if True:") == 1
    assert out.count("if False:") == 1


def test_leading_indentation_is_not_normalized_away():
    """The precision cost of tolerance, held to zero where it would hurt.

    Collapsing every whitespace run would make a needle written for one nesting
    depth match a same-looking line at another, and in Python it would then
    splice a replacement in at the wrong depth. Indentation is the one
    whitespace that carries meaning here, so it stays significant; only runs
    *after* the first non-whitespace character of a line are collapsed.

    The needle below is written for one level of nesting and the source sits at
    two. Under a matcher that normalized leading whitespace too, this would be a
    single clean match, and the four-space replacement would be spliced in at
    eight-space depth — an `IndentationError`, which is to say a proof that
    reports `proved` because the file stopped parsing. Refusing is correct.
    """
    source = "def f():\n    if outer:\n        if guard:\n            pass\n"
    snippet = 's = s.replace("\\n    if guard:", "\\n    if False:")'
    with pytest.raises(TamperError) as caught:
        apply_snippet(source, snippet, "x.py")
    assert caught.value.code == NO_MATCH


def test_a_tamper_that_leaves_python_unparseable_is_refused():
    """The `T014` failure, which reported `proved` for as long as it existed.

    `raise MigrationError(` occurs five times in the migrations module and the
    first is at module scope, so inserting a `return` before it put a `return`
    outside a function. The module stopped importing, every test in it errored
    during collection, and a non-zero exit read as the mechanism being
    load-bearing.
    """
    source = "X = 1\nfor i in (1,):\n    raise ValueError(i)\n"
    snippet = 's = s.replace("    raise ValueError(i)", "    return None\\n    raise ValueError(i)")'
    with pytest.raises(TamperError) as caught:
        apply_snippet(source, snippet, "m.py")
    assert caught.value.code == SYNTAX_BROKEN


def test_a_tamper_that_changes_nothing_is_refused():
    snippet = 's = s.replace("\\tclassLoopback: true,\\n", "\\tclassLoopback: true,\\n")'
    with pytest.raises(TamperError) as caught:
        apply_snippet(REALIGNED_MAP, snippet, "addresses.go")
    assert caught.value.code == UNCHANGED


def test_every_declared_removal_proof_still_names_a_live_site_and_a_live_test():
    """The rot check itself, over the real proof file.

    This is the assertion that makes rot cheap to find. `tests/removal_proofs.sh`
    needs pytest, a Go toolchain, a Linux kernel and root; thirteen proofs rotted
    in a single session because nothing that ran during that session looked at
    them. This runs in the ordinary suite, in under a second, and fails the build
    on the same push that causes the rot.
    """
    result = subprocess.run(
        [sys.executable, str(CHECKER), "--root", str(REPO)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "a removal proof no longer identifies its site or its test:\n"
        + result.stdout
        + result.stderr
    )


def test_the_declared_proof_count_is_what_it_is_expected_to_be():
    """The half of the floor that needs a number, kept where the number is known.

    Everything above is per-proof, so the whole file's verdict is only as
    strong as the number of proofs that reached it. `check_tampers.py` refuses
    zero and refuses a declaration it could not read, and neither of those
    notices a proof being *deleted*. This does.
    """
    import check_tampers

    proofs = check_tampers.extract(PROOF_FILE.read_text())
    assert len(proofs) == EXPECTED_PROOFS, (
        f"the proof set moved from {EXPECTED_PROOFS} to {len(proofs)}. If a "
        "proof was added or removed on purpose, update EXPECTED_PROOFS in the "
        "same commit; if not, extraction has degraded and the proofs that "
        "went missing are being reported as no news."
    )


def _indented_except_first(text: str) -> str:
    """The realistic degradation: declarations wrapped in a loop or a function.

    `_INVOCATION` is anchored at `^` and allows no leading whitespace, so two
    spaces are the whole of it. One declaration is left at column zero so the
    result reads as *partial* loss — the all-but-one case, which a bare
    `if not proofs` floor would wave through. Written without the count on
    purpose: `EXPECTED_PROOFS` is the one place that knows it, and a second
    copy here would rot every time the proof set moves.
    """
    seen = False
    out = []
    for line in text.splitlines(keepends=True):
        if re.match(r"^(go_)?proof \"", line):
            if seen:
                out.append("  " + line)
                continue
            seen = True
        out.append(line)
    return "".join(out)


@pytest.mark.parametrize(
    "build,expect_in_output",
    [
        (lambda _: "", "no proof declarations could be extracted"),
        (_indented_except_first, "declaration-shaped lines"),
    ],
    ids=["nothing-extractable", "one-of-many-extractable"],
)
def test_the_gate_fails_on_a_proofs_file_it_cannot_read(
    tmp_path, build, expect_in_output
):
    """A guard against vacuity that is itself unverified proves nothing.

    Until 2026-08-04 both of these exited 0 with `0 errors, 0 warnings`, which
    is a gate reporting success for having checked nothing. Both directions of
    the floor are asserted here because they catch different faults: the empty
    file reaches only the zero-check, and the indented file reaches only the
    declaration cross-check once one proof survives to keep the count non-zero.
    """
    degraded = tmp_path / "removal_proofs.sh"
    degraded.write_text(build(PROOF_FILE.read_text()))

    result = subprocess.run(
        [sys.executable, str(CHECKER), "--root", str(REPO), "--proofs", str(degraded)],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0, (
        "the gate passed a proofs file it could not read:\n" + result.stdout
    )
    assert expect_in_output in result.stdout, result.stdout
