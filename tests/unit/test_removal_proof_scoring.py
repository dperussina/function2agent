"""How `tests/removal_proofs.sh` scores a baseline it cannot read, driven rather
than read.

`tests/unit/test_tamper_matching.py` checks that the harness's *declarations* have
not rotted. Nothing checked that its **scorer** classified correctly, and the
scorer is where every silent failure this instrument has had so far lived:

- finding 032 — a signalled child scored `proved`, because the accepting set for
  `proved` was stated as a complement (`not 0 and not a collection error`);
- this file's subject — a passing test scored `SKIPPED`, because the accepting
  set for `SKIPPED` was stated the same way: `baseline_py` ended `echo SKIPPED`
  with no test in front of it, so every baseline line that carried no verdict
  landed there. `skipped` is a legitimate outcome that occurs in most runs, so a
  proof lost this way hides among correctly-skipped ones and reads green.

**Every test below runs the harness's real shell functions.** They are extracted
from `tests/removal_proofs.sh` verbatim and `eval`ed, so a change to the harness
changes what these assert — which is the only reason a removal proof against them
means anything. Re-implementing the classifier in Python here would produce a test
that agrees with itself forever.

Two vacuity floors, because the extraction is the load-bearing step and a failure
to extract would otherwise read as a pass:

- `_extract` raises when a function is missing or looks truncated, rather than
  returning an empty string that would make every driver below trivially succeed;
- `test_the_extraction_this_file_depends_on_actually_finds_the_scorer` asserts the
  extraction finds all four functions and that each contains the line that makes
  it the function under test.
"""

from __future__ import annotations

import json
import pathlib
import re
import shutil
import subprocess
import sys
import textwrap

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent.parent
PROOF_FILE = REPO / "tests" / "removal_proofs.sh"

#: The functions this file drives, and one substring each that must survive in
#: the extracted text. The substrings are what stop `_extract` from returning
#: some *other* function that happens to be named similarly, and they are the
#: reason a truncated extraction fails loudly instead of quietly.
_WANTED = {
    "_escape": "sed",
    "baseline_py": "UNREADABLE",
    "baseline_skip_reason": "SKIPPED",
    "go_toolchain_verdict": "NO-GO-ARMS",
    "unlisted_top_level": "NOT_NEEDED_PATHS",
}


def _extract(name: str) -> str:
    """The named shell function, verbatim.

    Two shapes, because the harness uses both: `_escape` is a one-liner and the
    rest open with `{` and close on a `}` at column zero.
    """
    text = PROOF_FILE.read_text(encoding="utf-8")
    anchor = r"^" + re.escape(name) + r" \(\) \{"
    match = re.search(anchor + r".*\}$", text, re.M) or re.search(
        anchor + r"\n(?:.*?\n)*?^\}$", text, re.M
    )
    if match is None:
        raise AssertionError(
            f"`{name}` could not be extracted from {PROOF_FILE}. Every test in "
            "this file drives that function, so an empty extraction would make "
            "all of them pass while checking nothing. If the function was "
            "renamed, rename it here; if it was deleted, the proof it carries "
            "went with it."
        )
    body = match.group(0)
    if len(body) < 20 or not body.rstrip().endswith("}"):
        raise AssertionError(
            f"`{name}` extracted as {body!r}, which is not a function body. "
            "Refusing to drive it."
        )
    return body


def _driver(*functions: str) -> str:
    return "\n".join(_extract(name) for name in functions)


def _score(baseline: str, selector: str, tmp_path: pathlib.Path) -> dict[str, str]:
    """Run `baseline_py` and then `report_unrunnable` over a planted baseline.

    Returns the verdict, the bucket each counter landed in, and the tab-separated
    record line the harness would have written. Driving `report_unrunnable` as
    well as `baseline_py` is deliberate: the *verdict* and the *bucket it is
    counted in* are two separate decisions, and folding an unreadable baseline
    into the skip count would be a correct verdict recorded in the one place a
    lost arm is invisible.
    """
    baseline_file = tmp_path / "baseline.txt"
    baseline_file.write_text(baseline, encoding="utf-8")
    records = tmp_path / "records.tsv"

    script = textwrap.dedent(
        """
        set -uo pipefail
        BASELINE_PY="$1"
        RECORDS="$2"
        : >"$RECORDS"
        PASS=0; FAIL=0; SKIP=0; TIMEOUT=0; UNREADABLE=0; UNUSABLE=0
        _P_NAME="planted arm"; _P_FILE="planted.py"; _P_TEST="$3"; _P_DRIFTED=no
        """
    ) + _driver(
        "_record", "_escape", "baseline_py", "baseline_skip_reason",
        "report_unrunnable",
    ) + textwrap.dedent(
        """
        v=$(baseline_py "$3")
        report_unrunnable "$v" "planted arm" "$3"
        echo "F2A-VERDICT=$v"
        echo "F2A-COUNTERS=PASS=$PASS FAIL=$FAIL SKIP=$SKIP TIMEOUT=$TIMEOUT UNREADABLE=$UNREADABLE UNUSABLE=$UNUSABLE"
        """
    )

    done = subprocess.run(
        ["bash", "-c", script, "bash", str(baseline_file), str(records), selector],
        capture_output=True,
        text=True,
    )
    assert done.returncode == 0, f"the driver itself failed:\n{done.stderr}"
    out = done.stdout
    verdict = re.search(r"^F2A-VERDICT=(\S*)$", out, re.M)
    counters = re.search(r"^F2A-COUNTERS=(.*)$", out, re.M)
    assert verdict and counters, f"the driver produced no readable result:\n{out}"
    return {
        "verdict": verdict.group(1),
        "counters": counters.group(1),
        "stdout": out,
        "record": records.read_text(encoding="utf-8").strip(),
    }


# ---------------------------------------------------------------------------
# Planted baselines. The split line in `_UNREADABLE` is not invented: it is what
# `pytest -v` writes when a test reaches the real file descriptor 1 while it runs.
# Reproduced on 2026-08-08 with `capfd.disabled()` under default capture, and
# identically with `-s` and with `PYTEST_ADDOPTS=-s`.

_PASSED = "tests/unit/test_thing.py::test_the_mechanism PASSED                  [ 50%]\n"

_SKIPPED = (
    "tests/unit/test_thing.py::test_the_mechanism SKIPPED                 [ 50%]\n"
    "SKIPPED [1] ../../tests/unit/test_thing.py:12: OD-17: Linux only\n"
)

_UNREADABLE = (
    "tests/unit/test_thing.py::test_the_mechanism a line the test wrote itself\n"
    "PASSED                                                               [ 50%]\n"
)

_ALREADY_FAILING = (
    "tests/unit/test_thing.py::test_the_mechanism FAILED                  [ 50%]\n"
)


def test_the_extraction_this_file_depends_on_actually_finds_the_scorer():
    """The floor. Every other test here is vacuous if this one is not true."""
    for name, must_contain in _WANTED.items():
        body = _extract(name)
        assert must_contain in body, (
            f"`{name}` was extracted but does not contain {must_contain!r}, so "
            "either the wrong function was matched or the mechanism this file "
            "drives has been removed from it"
        )


def test_a_passing_test_reads_PASSED_and_the_arm_is_attempted(tmp_path):
    """Control. `report_unrunnable` must decline to stop the caller."""
    result = _score(_PASSED, "tests/unit/test_thing.py::test_the_mechanism", tmp_path)
    assert result["verdict"] == "PASSED", result["stdout"]
    assert result["record"] == "", (
        "an attemptable arm recorded an outcome before its tamper was applied"
    )
    assert "SKIP=0" in result["counters"] and "UNREADABLE=0" in result["counters"]


def test_a_genuinely_skipped_test_still_reads_SKIPPED(tmp_path):
    """Control, and the one that makes the test below a discrimination.

    An environment declining to run a test is a real outcome and must keep
    reading as one. If this and the next test agreed, the repair would have
    replaced one indistinguishable pair with another.
    """
    result = _score(_SKIPPED, "tests/unit/test_thing.py::test_the_mechanism", tmp_path)
    assert result["verdict"] == "SKIPPED", result["stdout"]
    assert result["record"].startswith("skipped\ttest-skipped-in-baseline\t"), (
        result["record"]
    )
    assert "SKIP=1" in result["counters"] and "UNREADABLE=0" in result["counters"]


def test_a_passing_test_whose_verdict_moved_to_the_next_line_is_not_scored_skipped(
    tmp_path,
):
    """The defect this file exists for.

    `baseline_py` used to end `echo SKIPPED` with nothing testing for a skip, so
    this baseline — a test that PASSED — was scored as one the environment
    declined, its proof was never attempted, and the run stayed green with the
    loss hidden among the runs' ordinary 2-13 legitimate skips.
    """
    result = _score(
        _UNREADABLE, "tests/unit/test_thing.py::test_the_mechanism", tmp_path
    )
    assert result["verdict"] == "UNREADABLE", (
        "a passing test whose baseline line carries no verdict was classified "
        f"{result['verdict']!r}. If that is SKIPPED, the fall-through is back "
        "and a lost proof is once again indistinguishable from an arm the "
        "environment declined.\n" + result["stdout"]
    )


def test_an_unreadable_baseline_is_counted_apart_from_the_skips(tmp_path):
    """The verdict and the bucket are two decisions; this is the second one.

    Counting it as a skip would be the whole defect restored one layer down: the
    classification would be right and the number a reader looks at would still
    say "the environment declined some arms".
    """
    result = _score(
        _UNREADABLE, "tests/unit/test_thing.py::test_the_mechanism", tmp_path
    )
    assert "UNREADABLE=1" in result["counters"], result["counters"]
    assert "SKIP=0" in result["counters"], (
        "an unreadable baseline was counted as a skip: " + result["counters"]
    )
    assert result["record"].startswith("unreadable\tbaseline-verdict-unreadable\t"), (
        result["record"]
    )


def test_a_baseline_that_already_failed_is_counted_apart_from_the_unproven(tmp_path):
    """`unproven` means the mechanism is dead. This arm learned nothing.

    The same second decision as the test above, one condition over. An arm whose
    named test was already failing before the tamper was **never attempted** — the
    harness read the baseline, saw no usable verdict to score against, and
    refused. Folding it into `unproven` spends the one word in this harness that
    means *your mechanism is dead* on a run that established nothing either way,
    and that has now happened for at least four unrelated causes: a transiently
    dirty baseline reported "236 proved, 58 unproven" with zero vacuous arms, and
    the `specs/` copy-list omission produced three of these with nothing in the
    summary naming the copy list as the cause.
    """
    result = _score(
        _ALREADY_FAILING, "tests/unit/test_thing.py::test_the_mechanism", tmp_path
    )
    assert result["verdict"] == "FAILED", result["stdout"]
    assert "UNUSABLE=1" in result["counters"], result["counters"]
    assert "FAIL=0" in result["counters"], (
        "an arm whose baseline was already failing was counted as unproven, so a "
        "reader of the total cannot tell it from a mechanism that has died: "
        + result["counters"]
    )
    assert result["record"].startswith("unusable\ttest-already-failing\t"), (
        result["record"]
    )


def test_a_renamed_test_is_still_unproven_and_not_folded_in_here(tmp_path):
    """The scope boundary of the change above, pinned rather than left implied.

    `test-absent` shares the property that nothing was learned about the
    mechanism, so it is a candidate for the same treatment — but it is a
    different fact with a different owner: an absent test means the **proof
    declaration** is broken and points at nothing, which `tools/check_tampers.py`
    catches statically and which a reader should fix in the proof rather than in
    the environment. It was left where it was deliberately. If a later pass moves
    it, this assertion is the record of the boundary it is crossing, not an
    argument that the boundary is right forever.
    """
    result = _score(_PASSED, "tests/unit/test_other.py::test_gone", tmp_path)
    assert result["verdict"] == "ABSENT", result["stdout"]
    assert result["record"].startswith("unproven\ttest-absent\t"), result["record"]
    assert "UNUSABLE=0" in result["counters"], result["counters"]


def test_a_file_level_selector_survives_the_bare_node_ids_pytest_prints(tmp_path):
    """The regression the repair could plausibly have caused, asserted.

    A file-level selector matches `^file::`, which the **warnings summary** also
    matches — pytest repeats node ids there on bare lines with no verdict. So the
    question `baseline_py` asks has to be "did any matched line carry a verdict",
    in precedence order, and not "did every matched line carry one". Get that
    wrong and roughly thirty file-level arms become UNREADABLE at once.
    """
    baseline = (
        _PASSED
        + "\n=============================== warnings summary ===============================\n"
        + "tests/unit/test_thing.py::test_the_mechanism\n"
        + "  /x/y.py:1: DeprecationWarning: something\n"
    )
    result = _score(baseline, "tests/unit/test_thing.py", tmp_path)
    assert result["verdict"] == "PASSED", (
        "a file-level selector was made unreadable by the warnings summary, "
        "which every run with a warning in it prints\n" + result["stdout"]
    )


def test_the_skip_reason_reported_is_the_one_pytest_recorded(tmp_path):
    """The harness must quote a reason, never supply one.

    Measured on 2026-08-08: invoked through a login shell that drops the Go
    toolchain off PATH, two T114 arms were skipped because the enforcement point
    could not be built, and the harness printed "(privilege or platform)" for
    both. pytest had recorded the real reason and the harness discarded it.
    """
    baseline = (
        "tests/batteries/test_adversarial_egress.py::test_the_allowed_arms_reached_the_target SKIPPED [ 50%]\n"
        "SKIPPED [1] ../../tests/batteries/test_adversarial_egress.py:490: the "
        "enforcement point is a Go binary: set F2A_PROXY_BIN or install a Go "
        "toolchain.\n"
    )
    result = _score(
        baseline,
        "tests/batteries/test_adversarial_egress.py::test_the_allowed_arms_reached_the_target",
        tmp_path,
    )
    assert result["verdict"] == "SKIPPED", result["stdout"]
    assert "install a Go toolchain" in result["stdout"], (
        "the harness did not report the reason pytest recorded\n" + result["stdout"]
    )
    assert "privilege or platform" not in result["stdout"], (
        "the harness named a cause it had not established\n" + result["stdout"]
    )


def test_a_skip_with_no_recorded_reason_says_so_rather_than_inventing_one(tmp_path):
    """The other direction, so the assertion above is not satisfiable by luck.

    A baseline with no `-rs` block cannot yield a reason. The honest output is
    that none was recorded; the dishonest one is the old sentence.
    """
    result = _score(
        "tests/unit/test_thing.py::test_the_mechanism SKIPPED [ 50%]\n",
        "tests/unit/test_thing.py::test_the_mechanism",
        tmp_path,
    )
    assert result["verdict"] == "SKIPPED", result["stdout"]
    assert "no reason" in result["stdout"], result["stdout"]
    assert "privilege or platform" not in result["stdout"], result["stdout"]


# ---------------------------------------------------------------------------
# The copy list, whose omissions were silent by construction three times.


def _path_lists() -> tuple[set[str], set[str]]:
    """`REQUIRED_PATHS` and `NOT_NEEDED_PATHS`, read off the harness."""
    text = PROOF_FILE.read_text(encoding="utf-8")
    out = []
    for name in ("REQUIRED_PATHS", "NOT_NEEDED_PATHS"):
        match = re.search(rf'^{name}="([^"]*)"$', text, re.M)
        assert match, (
            f"`{name}` is not declared in {PROOF_FILE}. The copy list's two "
            "halves are what `unlisted_top_level` classifies against, so an "
            "absent one would make every test below vacuous."
        )
        out.append(set(match.group(1).split()))
    return out[0], out[1]


def _unlisted(directory: pathlib.Path) -> list[str]:
    """Drive the harness's own `unlisted_top_level` over a planted directory."""
    text = PROOF_FILE.read_text(encoding="utf-8")
    declarations = "\n".join(
        m.group(0)
        for m in re.finditer(r'^(REQUIRED_PATHS|NOT_NEEDED_PATHS)="[^"]*"$', text, re.M)
    )
    script = (
        "set -uo pipefail\n"
        + declarations
        + "\n"
        + _extract("unlisted_top_level")
        + '\nunlisted_top_level "$1"\n'
    )
    done = subprocess.run(
        ["bash", "-c", script, "bash", str(directory)],
        capture_output=True,
        text=True,
    )
    assert done.returncode == 0, done.stderr
    return sorted(done.stdout.split())


def test_the_two_path_lists_between_them_account_for_this_tree():
    """The check that closes the copy list's silent-omission direction.

    Three top-level directories — `deploy/`, `.github/` and `specs/` — were each
    added to the harness's copy list retroactively, after a pass found N arms
    reporting `test-already-failing` and nothing in the output naming the copy
    list as the cause. The harness's own comments called the third "third
    instance of the same failure and the same fix".

    Nothing made the fourth instance any louder than the first three, because an
    omission is invisible: a path that was never listed and a path that failed to
    copy produced identical silence. This asserts the two lists between them
    account for every top-level entry, so a new directory is named the first time
    the harness runs after it appears.
    """
    required, not_needed = _path_lists()
    assert _unlisted(REPO) == [], (
        "top-level path(s) of this repository appear in neither REQUIRED_PATHS "
        "nor NOT_NEEDED_PATHS in tests/removal_proofs.sh. If the suite reads it, "
        "add it to the first and the harness will copy it; if not, add it to the "
        "second to record that it was looked at. Leaving it out is how the copy "
        f"list has silently lost a directory three times.\nrequired={sorted(required)}"
        f"\nnot_needed={sorted(not_needed)}"
    )


def test_the_three_directories_that_were_added_retroactively_are_all_required():
    """The historical replay, so the check above is not satisfied by luck.

    Each of these was absent from the copy list once, and each cost a pass a
    debugging session. If a future edit drops one back out, the assertion above
    still passes — `unlisted_top_level` would report it, but only if it is also
    missing from `NOT_NEEDED_PATHS`, and the cheap way to silence a note is to
    add the path there. This closes that route for the three known cases.
    """
    required, not_needed = _path_lists()
    for path in ("deploy", ".github", "specs"):
        assert path in required, (
            f"`{path}` is not in REQUIRED_PATHS. It was added to the copy list "
            "retroactively after its absence made dependent arms report "
            "`test-already-failing`; removing it reinstates that."
        )
        assert path not in not_needed, (
            f"`{path}` is recorded as not needed, and the suite reads it."
        )


def test_a_planted_top_level_directory_is_named(tmp_path):
    """The positive control. Without it the assertion above passes on an empty
    extraction, which is the failure mode `_extract` exists to refuse."""
    (tmp_path / "src").mkdir()
    (tmp_path / ".venv").mkdir()
    (tmp_path / "a_directory_nobody_listed").mkdir()
    (tmp_path / ".a_hidden_one_nobody_listed").mkdir()
    assert _unlisted(tmp_path) == [
        ".a_hidden_one_nobody_listed",
        "a_directory_nobody_listed",
    ], (
        "the classifier did not name a planted top-level entry, so it cannot "
        "report the next directory to go missing from the copy list either"
    )


def test_the_work_tree_copy_does_not_discard_its_own_errors():
    """`2>/dev/null` is what made a failed copy read as a path nobody listed.

    The two are different facts wanting opposite responses — one is a renamed or
    unreadable source directory, the other is an omission from the list — and the
    redirection collapsed them into the same silence. Both then presented as N
    arms scored `test-already-failing`, which is the bucket this file's other
    tests exist to get out from under.
    """
    text = PROOF_FILE.read_text(encoding="utf-8")
    offenders = [
        line
        for line in text.splitlines()
        if line.strip().startswith("cp -r") and "2>/dev/null" in line
    ]
    assert offenders == [], (
        "the harness copies its work tree with its errors discarded, so a copy "
        "that failed is indistinguishable from a path that was never listed:\n"
        + "\n".join(offenders)
    )


def test_the_required_paths_are_all_present_in_this_tree():
    """The other direction of `2>/dev/null`: a listed path that is not there.

    A renamed or deleted source directory used to be indistinguishable from one
    that was never listed, because the copy discarded its own errors. The harness
    now aborts at setup; this catches the same rot in the ordinary suite, without
    needing a sweep.
    """
    required, _ = _path_lists()
    missing = sorted(p for p in required if not (REPO / p).exists())
    assert missing == [], (
        f"the copy list names path(s) that do not exist: {missing}. Every test "
        "reading one of them would fail in the baseline for a missing file, and "
        "its arms would be refused rather than scored."
    )


# ---------------------------------------------------------------------------
# The Go toolchain, which is an environment and not a result.


def _go_verdict(declared_arms: int, path: str) -> str:
    bash = shutil.which("bash")
    assert bash, "no bash on PATH"
    script = _extract("go_toolchain_verdict") + '\ngo_toolchain_verdict "$1"\n'
    done = subprocess.run(
        [bash, "-c", script, "bash", str(declared_arms)],
        capture_output=True,
        text=True,
        env={"PATH": path},
    )
    assert done.returncode == 0, done.stderr
    return done.stdout.strip()


@pytest.fixture(scope="module")
def path_without_go(tmp_path_factory) -> str:
    """A PATH that is *constructed* empty rather than assumed to lack `go`.

    The first version of this fixture used the directory bash lives in, which on
    a Homebrew host is also the directory `go` lives in — so the ABORT test below
    read OK and would have passed for the wrong reason had the assertion been the
    other way round. An empty directory cannot contain a toolchain by accident.
    `bash` itself is invoked by absolute path, so it does not need to be on it.
    """
    empty = tmp_path_factory.mktemp("no-go-here")
    assert not list(empty.iterdir())
    return str(empty)


def test_a_missing_toolchain_aborts_when_go_arms_are_declared(path_without_go):
    """The asymmetry this closes, and the reason it is an abort.

    `0caf257` — "Stop the removal-proof harness from scoring an environment as a
    result" — settled the Python side: a suite that cannot run gets a refusal to
    report a number. The Go side skipped instead, so on 2026-08-08 the same tree
    in the same image read `222 proved, 0 unproven` through `bash -c` and
    `210 proved, 0 unproven, 12 skipped` through `bash -lc`, both exit 0.
    """
    assert _go_verdict(10, path_without_go) == "ABORT", (
        "a missing Go toolchain with Go arms declared did not abort, so the run "
        "would report a clean sweep over a population smaller than the one it "
        "declares"
    )


def test_a_toolchain_that_is_present_is_not_an_abort(path_without_go):
    """Control. Without this the test above is satisfied by always aborting."""
    go = shutil.which("go")
    if go is None:
        pytest.skip(
            "no Go toolchain on this PATH, so the present-toolchain control "
            "cannot be constructed. The ABORT direction above still holds."
        )
    assert _go_verdict(10, f"{pathlib.Path(go).parent}:{path_without_go}") == "OK"


def test_a_tree_with_no_go_arms_needs_no_toolchain(path_without_go):
    """The third answer, which is why this is enumerated rather than a boolean.

    Pinning the requirement to the declarations means deleting the Go arms
    removes the requirement, instead of leaving a check that fails for nothing.
    """
    assert _go_verdict(0, path_without_go) == "NO-GO-ARMS"


def test_the_baseline_asks_pytest_for_the_reasons_it_will_later_quote():
    """`-rs` is the request; `baseline_skip_reason` is the reading.

    The behavioural tests above plant a baseline that already contains an `-rs`
    block, so they establish that the harness quotes a recorded reason and not
    that it asks pytest to record one. Without the flag the block is absent, every
    skip reports "no reason recorded", and the improvement collapses back to the
    harness knowing nothing about why an arm was lost.
    """
    text = PROOF_FILE.read_text(encoding="utf-8")
    invocation = [
        line for line in text.splitlines()
        if "python3 -m pytest tests" in line and ">" in line
    ]
    assert len(invocation) == 1, (
        f"expected exactly one pytest baseline invocation, found {invocation}"
    )
    assert " -rs" in invocation[0], (
        "the baseline does not ask pytest to report its skip reasons, so every "
        f"skipped arm will report that none was recorded. Line: {invocation[0]!r}"
    )


def test_the_record_counts_an_unreadable_arm_in_a_total_of_its_own(tmp_path):
    """The JSON record, driven — it had no test of any kind before this.

    Two properties in one run, because they fail in opposite directions. If the
    `unreadable` total is missing, a reader of the record cannot see the lost arm
    at all; if it is present but left out of the reconciliation sum, the record
    marks itself `inconsistent` and every number in it becomes unreliable — which
    would be a real signal spent on a state that is not actually inconsistent.
    """
    records = tmp_path / "records.tsv"
    records.write_text(
        "proved\t\tarm one\ta.py\ta.py::test_one\tno\n"
        "unreadable\tbaseline-verdict-unreadable\tarm two\tb.py\tb.py::test_two\tno\n",
        encoding="utf-8",
    )
    out = tmp_path / "record.json"
    done = subprocess.run(
        [sys.executable, str(REPO / "tools" / "removal_proofs_summary.py"), str(out)],
        capture_output=True,
        text=True,
        env={
            "PATH": "/usr/bin:/bin",
            "F2A_STATUS": "complete",
            "F2A_RECORDS": str(records),
            "F2A_PASS": "1",
            "F2A_FAIL": "0",
            "F2A_SKIP": "0",
            "F2A_TIMEOUT": "0",
            "F2A_UNREADABLE": "1",
            "F2A_HAVE_GO": "1",
            "F2A_EUID": "0",
            # The archive lands beside the record, which tmp_path already isolates.
            "HOME": str(tmp_path),
        },
    )
    assert done.returncode == 0, done.stderr
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["totals"].get("unreadable") == 1, (
        "the record does not count the unreadable arm in a total of its own, so "
        f"a reader cannot see it: {doc['totals']}"
    )
    assert doc["status"] == "complete", (
        "the record marks itself inconsistent for a run that reconciles, which "
        "means the unreadable count is missing from the sum: "
        f"{doc['totals']}"
    )
    assert doc["unreadable_titles"] == ["arm two"], doc.get("unreadable_titles")


def test_the_record_counts_an_already_failing_arm_in_a_total_of_its_own(tmp_path):
    """The same two opposed properties as the `unreadable` case above.

    A missing `unusable` total hides the arm inside `unproven`, which is the
    defect. A present total left out of the reconciliation sum marks the record
    `inconsistent` and burns a real signal on a run that reconciles fine.
    """
    records = tmp_path / "records.tsv"
    records.write_text(
        "proved\t\tarm one\ta.py\ta.py::test_one\tno\n"
        "unusable\ttest-already-failing\tarm two\tb.py\tb.py::test_two\tno\n",
        encoding="utf-8",
    )
    out = tmp_path / "record.json"
    done = subprocess.run(
        [sys.executable, str(REPO / "tools" / "removal_proofs_summary.py"), str(out)],
        capture_output=True,
        text=True,
        env={
            "PATH": "/usr/bin:/bin",
            "F2A_STATUS": "complete",
            "F2A_RECORDS": str(records),
            "F2A_PASS": "1",
            "F2A_FAIL": "0",
            "F2A_SKIP": "0",
            "F2A_TIMEOUT": "0",
            "F2A_UNREADABLE": "0",
            "F2A_UNUSABLE": "1",
            "F2A_HAVE_GO": "1",
            "F2A_EUID": "0",
            "HOME": str(tmp_path),
        },
    )
    assert done.returncode == 0, done.stderr
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["totals"].get("unusable") == 1, (
        "the record does not count the already-failing arm in a total of its "
        f"own, so it is indistinguishable from a dead mechanism: {doc['totals']}"
    )
    assert doc["totals"].get("unproven") == 0, (
        f"the already-failing arm was also counted as unproven: {doc['totals']}"
    )
    assert doc["status"] == "complete", (
        "the record marks itself inconsistent for a run that reconciles, which "
        f"means the unusable count is missing from the sum: {doc['totals']}"
    )
    assert doc["unusable_titles"] == ["arm two"], doc.get("unusable_titles")


def test_a_record_written_before_this_outcome_existed_still_renders(tmp_path):
    """The compatibility direction, for the reason `timed_out` states in place.

    Every record archived before this outcome existed has no `unusable` key, and
    `render` is run over archived records. A missing key must mean *this run
    predates the outcome*, never a crash — the archive exists so that a run which
    disagreed with its neighbours can still be read.
    """
    out = tmp_path / "old.json"
    out.write_text(
        json.dumps(
            {
                "status": "complete",
                "environment": {
                    "kernel": "6.12.76",
                    "system": "Linux",
                    "privileged": True,
                    "python": "3.12.11",
                },
                "totals": {
                    "proved": 3,
                    "unproven": 1,
                    "skipped": 0,
                    "entries_recorded": 4,
                },
                "proofs": [],
                "what_this_is_a_property_of": [],
            }
        ),
        encoding="utf-8",
    )
    done = subprocess.run(
        [
            sys.executable,
            str(REPO / "tools" / "removal_proofs_summary.py"),
            "--render",
            str(out),
        ],
        capture_output=True,
        text=True,
    )
    assert done.returncode == 0, done.stderr
    assert "3" in done.stdout, done.stdout


def test_an_unreadable_baseline_carries_weight_in_the_exit_status():
    """The last line of the harness, which is the only thing CI reads.

    Read from the text rather than driven, because the alternative is a full
    harness run; `test_the_harness_drops_cached_bytecode_around_every_tamper` in
    `test_tamper_matching.py` is the precedent. The classification tests above
    are the behavioural ones — this asserts the number reaches the verdict.
    """
    text = PROOF_FILE.read_text(encoding="utf-8")
    final = [line for line in text.splitlines() if line.strip()][-1]
    assert '[ "$UNREADABLE" -eq 0 ]' in final, (
        "the harness's exit status does not consult the unreadable count, so a "
        f"run that lost arms exits 0. Last line: {final!r}"
    )
    assert 'BASELINE UNREADABLE' in text, (
        "the summary line does not name the unreadable count. One line about a "
        "lost arm, 222 lines down inside a collapsed CI details block, is the "
        "quiet form of having no outcome at all."
    )


def test_an_already_failing_baseline_keeps_the_weight_it_already_had():
    """The constraint on the repair, and the direction it could have failed in.

    Splitting this outcome out of `unproven` moves a number that the exit status
    was already consulting, because `FAIL` carries the verdict. Move it without
    adding the new counter to the last line and every run with a dirty baseline
    goes from red to **green** — which is finding 032's fabrication pointing the
    other way, and strictly worse than the mislabelling being repaired. A dirty
    baseline genuinely means the sweep is not a result; only the label was wrong.
    """
    text = PROOF_FILE.read_text(encoding="utf-8")
    final = [line for line in text.splitlines() if line.strip()][-1]
    assert '[ "$UNUSABLE" -eq 0 ]' in final, (
        "the harness's exit status does not consult the unusable count. Because "
        "these arms used to be counted in FAIL, which the exit status does "
        "consult, splitting them out without this clause makes a dirty-baseline "
        f"run exit 0. Last line: {final!r}"
    )
    # `UNUSABLE` alone would be VACUOUS here: the per-arm branch has printed that
    # word since it was written — three occurrences at `e3f3912`, before any of
    # this — and the whole defect was that the per-arm line said it while the
    # aggregate did not. So the token asserted is the one the SUMMARY LINE adds.
    assert 'UNUSABLE BASELINE' in text, (
        "the summary line does not name the unusable count, so the outcome is "
        "reachable only by reading 300+ per-arm lines inside a collapsed CI "
        "details block, which is the quiet form of having no outcome at all."
    )
