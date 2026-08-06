#!/usr/bin/env python3
"""For each removal proof, name the test that actually fails once it lands.

A proof that applies its tamper and then observes a failing test has *not* shown
that the mechanism was load-bearing. It has shown that something broke. The
difference is the second vacuity class this repository has hit — a proof whose
tamper edits the wrong thing, or whose test file fails somewhere unrelated to
the claim, fails exactly like a real proof and reads exactly like one in the
harness output.

`tests/removal_proofs.sh` closes the cases it can decide mechanically: a tamper
that matches nothing, a tamper that matches two sites, a tamper that leaves the
file unparseable, a test that was already failing, a test that no longer exists.
What is left needs a human to read, and reading fifty-one proofs against the
harness's one-word verdicts is not a review anybody performs honestly.

So this prints the evidence that review needs: for each proof, the node ids that
went from passing to failing. A proof whose claim names one mechanism and whose
failure names an unrelated test is the thing to look at.

    python3 tools/proof_attribution.py
    python3 tools/proof_attribution.py --only FR-017

It is a reading aid and not a check. It has no threshold, it decides nothing,
and nothing imports it — the same disposition as `tools/cite_advisor.py`, for
the same reason: there is no rule separating "an unexpected test failed" from
"this test file covers the mechanism from two angles".

---------------------------------------------------------------------------
THE BASELINE, AND WHY READING ONLY THE POST-TAMPER STATE MEASURES NOTHING

Every verdict below is a *comparison*, and until 2026-08-04 only one side of it
was ever taken. `fails NOTHING — the test still passes` was printed whenever no
`FAILED` line came back, and the environments that produce no `FAILED` line
include the two where nothing ran at all:

  - the interpreter cannot import pytest, so every arm produces no outcomes;
  - the test named by the proof was renamed, so the selector collects zero
    items and the run reports no failure for the same reason an empty file
    would.

The first was run for real. On a host whose `python3` lacks pytest this tool
reported `fails NOTHING` for **every** proof in the file — a sweep that reads
as total collapse of the test suite and is in fact the tool measuring nothing.
`tests/removal_proofs.sh` was hardened against the identical failure two
commits earlier and this was the one instrument that never got the fix; the
general rule is Rule 8 in `.cursor/skills/experiment-design/SKILL.md`, and its
tell is exactly a suspiciously clean sweep.

So the suite is run **once, untampered, before any proof**, and the two failure
modes are separated because they call for different answers:

  - **no outcomes at all in the baseline** — the tool cannot run. It says so
    and exits 2 without printing a single per-proof result, because a baseline
    that yields nothing cannot support any later conclusion.
  - **the baseline ran but this proof's selector matched nothing in it** — an
    error against that one proof (`NO TEST`), distinguishable from `fails
    NOTHING`. This is the Python form of a rot the Go side already had a name
    for: `go test -run PATTERN` exits 0 when the pattern matches nothing, and
    scored renamed tests as unproven.

The baseline costs one `pytest` invocation and one `go test` invocation for the
whole file, against the fifty-one of each the proof loop makes.

---------------------------------------------------------------------------
THE CAP, AND WHY A KILLED RUN IS ITS OWN OUTCOME RATHER THAN A THIRD SILENCE

This tool applies **every** tamper in the file and runs the arm's test. Some of
those tampers remove the only thing that stops a loop, and the tampered test
then has no failure mode left: it does not fail, it does not return. Two such
arms are on record and `tools/proof_timeout.py` names both. Finding 032 records
what one costs uncapped — 56 minutes of continuous CPU on a laptop, and here,
in CI, against a job limit rather than somebody's patience.

So every tampered run goes through `tools/proof_timeout.py`, at the same
`REMOVAL_PROOF_TIMEOUT` `tests/removal_proofs.sh` puts on the same arms. That
script rather than `subprocess.run(timeout=)`, for the reason its own docstring
gives: `subprocess.run` kills the direct child only, and a tampered arm can
leave children behind (`tests/unit/test_supervisor_lease.py` spawns
interpreters that outlive a killed parent). The cap runs the command in its own
session and kills the **group**. A partial kill is the shape that let the
original hang survive being killed.

**A cap without its own outcome would be the shallower half of the fix.**
Finding 032's keeper distinction is that the cap only made the hang rarer, and
the *scoring* is what closed the hole: what fabricated a proof in the harness
was reading a killed process as a result. The identical shape is available
here. A killed run emits no `FAILED` line, and no `FAILED` line prints `fails
NOTHING — the test still passes` — a claim about the mechanism, made by a run
that never reached an assertion. That is the harness's fabricated `proved` one
tool over, pointing the other way and with the same cause.

A killed run therefore gets its own report and never the `fails` line:

  - **TIMED OUT** — the cap fired (exit 124).
  - **SIGNALLED** — the run died on a signal (exit > 128) without reporting: an
    OOM kill, a segfault in tampered source, a runner tearing the job down. The
    cap does not govern those, which is the whole of finding 032's point.

Neither is `NO TEST`, which says the baseline never had that test, and neither
is the `CANNOT RUN` refusal above, which says there is no baseline at all and
so nothing can be attributed. These are per-proof, because every other proof in
the file was attributed fine.

**The exit status stays 0.** This tool decides nothing (see the head of this
docstring) and these are the harness's own arms: `tests/removal_proofs.sh` runs
the same tamper against the same test under the same cap and *does* gate,
scoring `timed-out` with its own counter or `unproven` for a signal. A second
red light on the same fact would be a second place to tune. What is added
instead is a tail block naming the affected proofs, because one line inside a
hundred-and-fifty-proof listing in a collapsed CI `<details>` block is not
somewhere a reader finds anything.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from check_tampers import extract  # noqa: E402
from tamper import TamperError, apply_snippet  # noqa: E402

REPO = pathlib.Path(__file__).resolve().parent.parent
_FAILED = re.compile(r"^(?:FAILED|ERROR) (\S+)", re.M)
_GO_FAIL = re.compile(r"^ *--- FAIL: (\S+)", re.M)

# The wall-clock cap on one tampered run. See the docstring section above for
# why this script and not `subprocess.run(timeout=)`.
CAP = REPO / "tools" / "proof_timeout.py"
TIMED_OUT = 124  # what `proof_timeout.py` exits, and GNU `timeout(1)` before it

# The harness's own knob, shared on purpose. These are the harness's arms, and
# a cap raisable in one tool but not the other would let the same arm be
# bounded in one place and run unbounded in the other — which is the state this
# tool was in until now.
PROOF_TIMEOUT = os.environ.get("REMOVAL_PROOF_TIMEOUT", "300")

# The baseline outcome lines. `pytest -v` writes `NODE_ID OUTCOME`; `go test -v`
# writes `--- OUTCOME: TestName`, indented for a subtest and not for a parent.
#
# The node id is `.*?` rather than `\S+` because a parametrized id may carry a
# space inside its brackets — `test_each_key_malformed_fails_and_names_itself
# [SANDBOX_CPU_MAX-max 100000]` is one in this suite. Reading `\S+` dropped that
# line from the baseline, which would report a proof naming it as `NO TEST`:
# the guard inventing the rot it exists to detect. Anchoring on a non-space
# first character keeps the indented summary blocks out, and requiring
# something *before* the outcome keeps pytest's own `FAILED node - reason`
# short-summary lines from being counted a second time.
_PY_OUTCOME = re.compile(
    r"^(\S.*?) (PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS)\b", re.M)
_GO_OUTCOME = re.compile(r"^ *--- (PASS|FAIL|SKIP): (\S+)", re.M)

ABSENT, FAILED, SKIPPED, PASSED = "ABSENT", "FAILED", "SKIPPED", "PASSED"


def _run_baseline_py(work: pathlib.Path) -> tuple[str, list[tuple[str, str]]]:
    """The whole suite, untampered. Returns the raw output and its outcomes."""
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests", "-v", "--tb=no",
         "-p", "no:cacheprovider"],
        cwd=work, capture_output=True, text=True,
    )
    out = proc.stdout + proc.stderr
    return out, [(node, outcome) for node, outcome in _PY_OUTCOME.findall(out)]


def _run_baseline_go(work: pathlib.Path) -> list[tuple[str, str]]:
    proc = subprocess.run(
        ["go", "test", "-v", "./..."],
        cwd=work / "src" / "proxy", capture_output=True, text=True,
    )
    out = proc.stdout + proc.stderr
    return [(name, outcome) for outcome, name in _GO_OUTCOME.findall(out)]


def baseline_py(outcomes: list[tuple[str, str]], selector: str) -> str:
    """PASSED | SKIPPED | FAILED | ABSENT, for a node id or a test file.

    ABSENT is the one with no detection at all before: a selector that collects
    zero items produces no failure after the tamper either, which read as
    `fails NOTHING` — a claim about the mechanism made by a run that never
    reached it.
    """
    if "::" in selector:
        matched = [o for node, o in outcomes
                   if node == selector or node.startswith(selector + "[")]
    else:
        matched = [o for node, o in outcomes if node.startswith(selector + "::")]
    if not matched:
        return ABSENT
    if any(o in ("FAILED", "ERROR") for o in matched):
        return FAILED
    if PASSED in matched:
        return PASSED
    return SKIPPED


def baseline_go(outcomes: list[tuple[str, str]], pattern: str) -> str:
    """The same question for a `-run` alternation. Every named test must exist."""
    verdict = PASSED
    for wanted in pattern.split("|"):
        wanted = wanted.strip()
        matched = [o for name, o in outcomes if name == wanted]
        if not matched:
            return ABSENT
        if "FAIL" in matched:
            verdict = FAILED
        elif verdict == PASSED and "SKIP" in matched:
            verdict = SKIPPED
    return verdict


def _capped(argv: list[str], cwd: pathlib.Path) -> tuple[str, int]:
    """One tampered run, under the cap. Returns its output and its status.

    stdout and stderr are read together because the cap merges them anyway, and
    because `_run_baseline_py` above already reads them together for the same
    reason: a tampered run's diagnosis is in whichever stream it chose.
    """
    proc = subprocess.run(
        [sys.executable, str(CAP), PROOF_TIMEOUT, *argv],
        cwd=cwd, capture_output=True, text=True,
    )
    return proc.stdout + proc.stderr, proc.returncode


def _report_unobserved(status: int) -> str | None:
    """The lines for a run that was killed, or None if it reported for itself.

    Kept apart from `_report_unrunnable` below because the two answer different
    questions. That one asks whether the arm was worth attempting, from the
    baseline, before the tamper. This one asks whether the attempt produced an
    observation at all — and the answer `no` must not be spelled `fails
    NOTHING`, which is a reading of a run that finished.
    """
    if status == TIMED_OUT:
        return (f"    TIMED OUT did not return within {PROOF_TIMEOUT}s and was "
                "killed, so it names nothing\n"
                "              Not `fails NOTHING` — that describes a run that "
                "finished and this one did not.")
    if status > 128:
        return (f"    SIGNALLED died on signal {status - 128} without reporting, "
                "so it names nothing\n"
                "              Not `fails NOTHING` — no assertion was evaluated, "
                "so nothing was observed to pass.")
    return None


def _report_unrunnable(verdict: str, test: str) -> str | None:
    """The one line saying why a proof was not attempted, or None to attempt it."""
    if verdict == ABSENT:
        return (f"    NO TEST {test} matched nothing in the baseline; the test "
                "was renamed or removed")
    if verdict == FAILED:
        return (f"    UNUSABLE {test} already fails before the tamper, so its "
                "failure after names nothing")
    if verdict == SKIPPED:
        return "    SKIPPED (the test did not run here — privilege or platform)"
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--only", default="", help="substring filter on the proof name")
    args = parser.parse_args(argv)

    # Before anything is copied or run. An unparseable cap makes
    # `proof_timeout.py` exit 2 on every arm, which reads here as a run that
    # produced no failure — the `fails NOTHING` sweep this tool's own docstring
    # was written about. Refusing is the same answer as the baseline abort's,
    # for the same reason: the tool cannot do the thing it prints.
    try:
        float(PROOF_TIMEOUT)
    except ValueError:
        print(f"REMOVAL_PROOF_TIMEOUT={PROOF_TIMEOUT!r} is not a number of "
              "seconds. Refusing to run uncapped.", file=sys.stderr)
        return 2

    proofs = [
        p
        for p in extract((REPO / "tests" / "removal_proofs.sh").read_text())
        if args.only in p.name
    ]

    work = pathlib.Path(tempfile.mkdtemp())
    try:
        for name in ("src", "tests", "tools"):
            shutil.copytree(REPO / name, work / name)
        shutil.copy(REPO / "pyproject.toml", work / "pyproject.toml")

        have_go = shutil.which("go") is not None

        # --- the baseline. Nothing below is attempted until this says the
        # suite runs. See the module docstring for what a missing one costs.
        py_outcomes: list[tuple[str, str]] = []
        if any(p.kind == "py" for p in proofs):
            raw, py_outcomes = _run_baseline_py(work)
            if not py_outcomes:
                print("CANNOT RUN — pytest produced no test outcomes at all in "
                      "this environment.\n")
                for line in raw.splitlines()[-20:]:
                    print(f"    {line}")
                print(
                    "\n  Every proof below would have printed `fails NOTHING` for"
                    "\n  this reason, which reads as the whole suite failing to"
                    "\n  cover anything. Refusing to attribute. Install the pinned"
                    "\n  dependencies (pip install --require-hashes -r"
                    "\n  requirements.lock) or run inside the dev image."
                )
                return 2

        go_outcomes: list[tuple[str, str]] = []
        go_baseline_empty = False
        if have_go and any(p.kind == "go" for p in proofs):
            go_outcomes = _run_baseline_go(work)
            go_baseline_empty = not go_outcomes

        # Said in words rather than as a zero, because `0 python outcomes` is
        # exactly the shape of the number this guard exists to refuse to print.
        def _arm(selected: bool, present: bool, outcomes, label: str,
                 failing: tuple[str, ...], absent: str) -> str:
            if not selected:
                return f"no {label} proofs selected"
            if not present:
                return absent
            bad = sum(1 for _, o in outcomes if o in failing)
            return f"{len(outcomes)} {label} outcomes ({bad} not passing)"

        print("baseline   " + ", ".join((
            _arm(any(p.kind == "py" for p in proofs), True, py_outcomes,
                 "python", ("FAILED", "ERROR"), ""),
            _arm(any(p.kind == "go" for p in proofs), have_go, go_outcomes,
                 "go", ("FAIL",), "no Go toolchain"),
        )))
        print()

        # Proofs whose run was killed rather than finished, for the tail block.
        killed: list[tuple[str, int]] = []

        for proof in proofs:
            # The baseline lookup. A proof whose test did not run untampered
            # cannot be scored by whether it fails tampered.
            if proof.kind == "py":
                unrunnable = _report_unrunnable(
                    baseline_py(py_outcomes, proof.test), proof.test)
            elif not have_go:
                unrunnable = None
            elif go_baseline_empty:
                unrunnable = ("    CANNOT RUN the Go suite produced no test "
                              "outcomes; the package did not build")
            else:
                unrunnable = _report_unrunnable(
                    baseline_go(go_outcomes, proof.test), proof.test)
            if unrunnable is not None:
                print(proof.name)
                print(f"    claims  {proof.test}")
                print(unrunnable)
                print()
                continue

            target = work / proof.path
            original = target.read_text()
            try:
                tampered, _ = apply_snippet(original, proof.snippet, str(target))
            except TamperError as exc:
                print(f"{proof.name}\n    TAMPER {exc.code}: {exc.detail}\n")
                continue
            target.write_text(tampered)
            try:
                status = 0
                if proof.kind == "py":
                    out, status = _capped(
                        [sys.executable, "-m", "pytest", proof.test, "-q", "--tb=no",
                         "-p", "no:cacheprovider"],
                        work,
                    )
                    failed = _FAILED.findall(out)
                    if not failed and re.search(r"\d+ skipped", out) and " passed" not in out:
                        failed = ["(the test did not run here — privilege or platform)"]
                elif have_go:
                    out, status = _capped(
                        ["go", "test", "-v", "-run", proof.test, "./..."],
                        work / "src" / "proxy",
                    )
                    failed = _GO_FAIL.findall(out)
                else:
                    failed = ["(no Go toolchain)"]
            finally:
                target.write_text(original)

            print(proof.name)
            print(f"    claims  {proof.test}")
            # Before the `fails` lines and not beside them: a killed run has no
            # findall result worth printing, and printing one anyway is how a
            # non-observation gets read as an observation.
            unobserved = _report_unobserved(status)
            if unobserved is not None:
                killed.append((proof.name, status))
                print(unobserved)
                print()
                continue
            if not failed:
                print("    fails   NOTHING — the test still passes")
            for node in failed:
                print(f"    fails   {node}")
            print()

        if killed:
            # Named again here because the per-proof line above is one of a
            # hundred and fifty, inside a collapsed `<details>` block on the run
            # page. An outcome nobody scrolls to is the quiet form of not having
            # one.
            print(f"{len(killed)} proof(s) produced no observation — the run was "
                  "killed rather than finished:")
            for name, status in killed:
                label = "TIMED OUT" if status == TIMED_OUT else "SIGNALLED"
                print(f"    {label} {name}")
            print()
            print("  None of these is `fails NOTHING`. `tests/removal_proofs.sh`")
            print("  runs the same arms under the same cap and does gate on them:")
            print("  a timeout scores `timed-out` there, a signal `unproven`.")
            print()
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
