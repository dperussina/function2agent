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
        PASS=0; FAIL=0; SKIP=0; TIMEOUT=0; UNREADABLE=0
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
        echo "F2A-COUNTERS=PASS=$PASS FAIL=$FAIL SKIP=$SKIP TIMEOUT=$TIMEOUT UNREADABLE=$UNREADABLE"
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
