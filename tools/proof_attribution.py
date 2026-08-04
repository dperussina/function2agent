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
        for proof in proofs:
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
