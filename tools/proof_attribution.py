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
"""

from __future__ import annotations

import argparse
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
                if proof.kind == "py":
                    out = subprocess.run(
                        [sys.executable, "-m", "pytest", proof.test, "-q", "--tb=no",
                         "-p", "no:cacheprovider"],
                        cwd=work, capture_output=True, text=True,
                    ).stdout
                    failed = _FAILED.findall(out)
                    if not failed and re.search(r"\d+ skipped", out) and " passed" not in out:
                        failed = ["(the test did not run here — privilege or platform)"]
                elif have_go:
                    out = subprocess.run(
                        ["go", "test", "-v", "-run", proof.test, "./..."],
                        cwd=work / "src" / "proxy", capture_output=True, text=True,
                    ).stdout
                    failed = _GO_FAIL.findall(out)
                else:
                    failed = ["(no Go toolchain)"]
            finally:
                target.write_text(original)

            print(proof.name)
            print(f"    claims  {proof.test}")
            if not failed:
                print("    fails   NOTHING — the test still passes")
            for node in failed:
                print(f"    fails   {node}")
            print()
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
