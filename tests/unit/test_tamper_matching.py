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

import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
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
#: mechanism and not an inconvenience: a silent drop from 530 to 529 is the rot.
#: The illustration has twice been left behind by the constant — it read
#: `66 to 65`, then `351 to 350`, while the number above moved past both — which
#: made the coupling read as an example of the rule rather than as the rule
#: operating on the number directly above. Move it with the constant.
EXPECTED_PROOFS = 530

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


# ---------------------------------------------------------------------------
# The recorded title, and the shell that rewrites it on the way in.


def _gate_over(proofs_text: str, tmp_path) -> subprocess.CompletedProcess:
    """Run the gate over a planted proofs file, scoring this tree's sources."""
    planted = tmp_path / "removal_proofs.sh"
    planted.write_text(proofs_text)
    return subprocess.run(
        [sys.executable, str(CHECKER), "--root", str(REPO), "--proofs", str(planted)],
        capture_output=True,
        text=True,
    )


def _retitled(title: str) -> str:
    """The real proofs file with the first declaration's title replaced.

    The real file rather than a synthetic one, because the defect this is about
    is a *live* declaration wearing a title nobody can tell is wrong, and the
    surrounding proof has to stay intact for the run to reach the title check
    at all.
    """
    return re.sub(
        r'^proof "[^"]*"',
        f'proof "{title}"',
        PROOF_FILE.read_text(),
        count=1,
        flags=re.M,
    )


@pytest.mark.parametrize(
    "title,expect_in_output",
    [
        ("FR-048 mount namespace — `pivot_root` removed",
         "a backtick, so the shell ran what it enclosed as a command"),
        ("FR-048 mount namespace — $HOME removed",
         "a `$`, so the shell expanded what followed it"),
    ],
    ids=["command-substitution", "parameter-expansion"],
)
def test_a_title_the_shell_rewrites_is_refused(tmp_path, title, expect_in_output):
    """The defect that shipped once, in both of its shapes.

    A proof title is a double-quoted shell string, so the shell interprets what
    is in it. The failure is not that an arm scores wrongly — it scores
    correctly — but that the title archived beside the verdict is no longer the
    one an author wrote, and it announces itself as an environment fault:
    `required: command not found`, with the word silently gone from the record.

    The two arms are the two constructs that reach it, and the second is the
    worse of the two: an expansion does not fail at all, so nothing is printed
    and the recorded identity of the proof quietly becomes a property of the
    machine that ran the gate.

    Asserted through the gate's own exit status and message rather than by
    calling the comparison, because a rule that fires without failing the run
    is the vacuity this file's floor tests are about.
    """
    result = _gate_over(_retitled(title), tmp_path)
    assert result.returncode != 0, (
        "the gate accepted a title the shell rewrote:\n" + result.stdout
    )
    assert "the recorded title is not the written one" in result.stdout, result.stdout
    assert expect_in_output in result.stdout, result.stdout


def test_a_title_carrying_an_escape_is_not_reported(tmp_path):
    """The skip, asserted — because without it this rule invents its own rot.

    `\\"` inside a double-quoted title is legitimate and the shell strips the
    backslash, so written and produced differ for a reason that is nobody's
    defect. The comparison declines to judge a written title holding a
    backslash, which keeps it looser than the shell instead of a second
    implementation of the shell's quoting. Planted here so that removing the
    skip is a red test rather than a plausible simplification.
    """
    result = _gate_over(
        _retitled('FR-048 mount namespace — \\"pivot_root\\" removed'), tmp_path
    )
    assert result.returncode == 0, (
        "an escaped quote in a title was reported as rot:\n" + result.stdout
    )
    assert "the recorded title is not the written one" not in result.stdout


# ---------------------------------------------------------------------------
# The stale-bytecode collision, and the harness line that closes it.

_GUARDED = (
    "def reachable(per_row, scoped):\n"
    "    if per_row and scoped is not None:\n"
    "        return False\n"
    "    return True\n"
)
#: The *same length*, a different mechanism removed. Two `if <cond>:` sites
#: rewritten to `if False:` differ from their originals by the same number of
#: bytes far more often than not, and this pair is the shape that actually
#: occurred in `repository.py`.
_TAMPERED = (
    "def reachable(per_row, scoped):\n"
    "    if False:  # noqa                 \n"
    "        return False\n"
    "    return True\n"
)


def _import_and_ask(package: pathlib.Path) -> str:
    """Import `guarded` in a child that is *required* to cache bytecode.

    The child's bytecode policy is set here rather than inherited, because the
    dev and sandbox images both ship `PYTHONDONTWRITEBYTECODE=1`
    (`deploy/images/dev.Dockerfile`, `deploy/images/sandbox.Dockerfile`) and an
    inheriting child writes no `.pyc` at all — so the arm below could not plant
    the collision it is named for, and failed inside the container as shipped.

    **Why this is forced rather than skipped, and rather than fixed in the
    image.** The arm does not exist to detect the hazard in the environment it
    happens to be run in; it exists so that `drop_bytecode` in
    `tests/removal_proofs.sh` cannot be deleted as tidying. That is a property of
    CPython, and it has to be checkable wherever the suite runs — most of all in
    the container, because the container is the documented environment for the
    harness the mitigation belongs to, and whoever deletes the `rm` may never run
    the suite anywhere else. A skip keyed on `PYTHONDONTWRITEBYTECODE` would put
    the blind spot exactly there.

    Unsetting the variable in the image was the other candidate and is worse in
    two ways. The tree is bind-mounted, so the container would start writing
    `.pyc` files into it; and it would make the collision *live* in the harness's
    own run environment in order to make a test about the collision pass, which
    is backwards. Forcing it for one child in `tmp_path` leaves the image's
    property intact and writes nothing outside the temporary directory.
    """
    env = dict(os.environ)
    env.pop("PYTHONDONTWRITEBYTECODE", None)
    return subprocess.run(
        [sys.executable, "-c",
         "import guarded; print(guarded.reachable(True, 'tenant'))"],
        cwd=str(package), capture_output=True, text=True, check=True, env=env,
    ).stdout.strip()


def test_a_tampered_module_of_the_same_size_is_read_from_a_stale_pyc(tmp_path):
    """The hazard, planted — because the harness scored an arm on it.

    CPython decides a cached `.pyc` is current from the source's
    `(mtime-in-whole-seconds, size)`. Two removal proofs that tamper one file
    inside the same second with edits of equal byte length therefore make the
    second import the **first one's** compiled module: it reports on a
    mechanism it never removed, `UNPROVEN` when the stale bytecode still holds
    the guard and `proved` when it does not.

    This is not a story about clock resolution. It is asserted here because
    the harness has no way to notice — both readings are ordinary outcomes —
    and because the mitigation below is one `rm` that reads like tidying and
    would be removed by anyone who did not know this.
    """
    package = tmp_path / "pkg"
    package.mkdir()
    source = package / "guarded.py"
    source.write_text(_GUARDED)
    assert _import_and_ask(package) == "False", "the guard is not being read"
    assert (package / "__pycache__").is_dir(), (
        "no bytecode was cached, so this arm cannot be about stale bytecode. "
        "_import_and_ask clears PYTHONDONTWRITEBYTECODE for the child precisely "
        "so that this holds inside the images, which set it"
    )

    stamp = source.stat().st_mtime
    source.write_text(_TAMPERED)
    assert source.stat().st_size == len(_GUARDED), (
        "the two versions differ in size, so this arm is not reproducing the "
        "collision it is named for"
    )
    os.utime(source, (stamp, stamp))

    assert _import_and_ask(package) == "False", (
        "the tampered source was actually imported, so the collision this "
        "arm plants did not occur and the assertion below proves nothing "
        "about the mitigation"
    )

    shutil.rmtree(package / "__pycache__")
    assert _import_and_ask(package) == "True", (
        "dropping the cached bytecode did not make the tampered source take "
        "effect, so removing __pycache__ is not the mitigation"
    )


def test_the_stale_pyc_arm_plants_its_hazard_where_the_images_disable_bytecode():
    """The arm above must not go quiet in the environment the harness runs in.

    Both images set `PYTHONDONTWRITEBYTECODE=1`, so a child that inherits the
    environment writes no `.pyc` and the collision cannot be planted — the arm
    above failed inside the container as shipped, on a tree whose suite was
    otherwise green. This asserts the *forcing* rather than the outcome: the
    variable is set here deliberately, so the assertion fails on any host once
    `_import_and_ask` stops clearing it, and not only on the hosts that happen to
    set it.

    Skipping the arm when the variable is set was the obvious repair and is the
    wrong one. It would put the blind spot precisely in the container, which is
    the documented environment for `tests/removal_proofs.sh` — the instrument the
    mitigation belongs to — so the one person who could delete the `rm` without
    being told is the one who only ever runs the suite there.
    """
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("PYTHONDONTWRITEBYTECODE", "1")
        with tempfile.TemporaryDirectory() as raw:
            package = pathlib.Path(raw) / "pkg"
            package.mkdir()
            (package / "guarded.py").write_text(_GUARDED)
            assert _import_and_ask(package) == "False", "the guard is not read"
            assert (package / "__pycache__").is_dir(), (
                "PYTHONDONTWRITEBYTECODE was set and reached the child, so no "
                "bytecode was cached and the arm above cannot plant the stale-pyc "
                "collision it is named for. It would pass on a host that does not "
                "set the variable and fail inside both images, which is the "
                "opposite of where the check is needed."
            )


def test_the_harness_drops_cached_bytecode_around_every_tamper():
    """The mitigation is three call sites, and one of them is not enough.

    The tamper edits the file, and so does the restore — a proof that put the
    original back inside the same second, at the same size as some later
    tamper, collides in exactly the same way. So the drop has to happen on the
    way in and on both ways out, and this counts them rather than looking for
    the function once.
    """
    text = PROOF_FILE.read_text()
    assert "drop_bytecode () {" in text, (
        "the harness has no bytecode drop at all; see the arm above for what "
        "that costs"
    )
    calls = len(re.findall(r"^\s*drop_bytecode \"\$file\"", text, re.M))
    assert calls >= 3, (
        f"drop_bytecode is called at {calls} site(s). It belongs after the "
        f"tamper and after each restore; a missing one is a silent collision "
        f"between whichever two proofs happen to land next to each other"
    )
