#!/usr/bin/env python3
"""Static rot check for every removal proof. No pytest, no Go, no privileges.

`tests/removal_proofs.sh` is the repository's evidence that its tests are
load-bearing, and it decays. A tamper string is matched against source text, so
any edit to that source can silently stop it applying; fifteen proofs reached
that state on 2026-08-03, thirteen of them discovered at once. The harness now
fails a tamper that matches nothing — but only once somebody runs the harness,
which needs pytest, a Go toolchain, a Linux kernel and root, takes minutes, and
is therefore not what the person who *caused* the rot runs.

This is that check with everything expensive removed. It answers three
questions per proof and nothing else:

1. Does the tamper still identify exactly one site in the file it names?
2. Does it still identify that site *exactly*, or only after whitespace
   normalization — the second being a live signal that a formatter moved the
   source and that the proof is now surviving on tolerance rather than on
   accuracy?
3. Does the test it runs still exist?

Question 3 has no other guard anywhere and is the more dangerous of the two rot
classes it covers. A `pytest` selector naming a test that has been renamed
exits **4**, which the harness reads as a non-zero exit and therefore as
"the test failed with the mechanism removed" — a rotted selector reports
`proved`. A `go test -run` pattern matching nothing exits **0**, which reports
`UNPROVEN`. Neither is true and neither is visible in the harness output.

    python3 tools/check_tampers.py
    python3 tools/check_tampers.py --format summary
    python3 tools/check_tampers.py --root /some/checkout   # score a tree that is not this one

Runs in well under a second against the whole proof set, so it belongs in a
pre-commit hook and in every CI job, not only in the one that can afford the
harness.

---------------------------------------------------------------------------
THE FLOOR, AND WHY A ZERO-CHECK ALONE WOULD NOT BE ONE

This is a gate, and until 2026-08-04 it had the defect it exists to prevent.
Handed a proofs file it could extract nothing from, it printed `0 proofs
declared`, `0 errors, 0 warnings`, and exited 0 — green while checking
nothing. That is Rule 8 in `.cursor/skills/experiment-design/SKILL.md` read
from the other end: the reading a *pass* produces here is "no finding", and
every way extraction can break produces exactly that reading.

So zero extracted proofs is an error. That much is obvious and it is not
sufficient, because **extraction degrading from 61 proofs to 1 is the same
defect as degrading to 0**, and a zero-check waves it through. The concrete
route is not hypothetical: `_INVOCATION` is anchored at `^` and tolerates no
leading whitespace, so wrapping the declarations in a `for` loop or a
function — indenting them by two spaces — drops every one of them and is an
ordinary-looking refactor.

Two guards, because they fail in different directions and neither covers the
other:

  - **the vacuity floor** — zero extracted proofs is an error, unconditionally.
    A proofs file declaring no proofs is the wrong file or a broken extractor,
    and there is no third reading under which reporting success is honest.
  - **the declaration cross-check** — every declaration-shaped line in the file
    must have produced a proof. It carries **no constant**, which is what lets
    it travel to the older revisions `--proofs` and `--root` exist to score,
    and it is deliberately *looser* than `_INVOCATION` rather than a second
    strict implementation of it. A stricter second opinion would report rot it
    had invented, which is the failure this file is about.

The absolute count is pinned where the revision is known: `EXPECTED_PROOFS` in
`tests/unit/test_tamper_matching.py`, in the shape `tools/selftest.py` uses for
`GEN_EXPECTED`. It does not belong here, because a hard minimum in the tool
would fail the documented cross-revision workflow, where an older proofs file
legitimately declares fewer.
"""

from __future__ import annotations

import argparse
import pathlib
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from tamper import (  # noqa: E402
    AMBIGUOUS,
    NO_MATCH,
    OK_EXACT,
    OK_NORMALIZED,
    TamperError,
    apply_snippet,
)

REPO = pathlib.Path(__file__).resolve().parent.parent
PROOF_FILE = "tests/removal_proofs.sh"
GO_DIR = "src/proxy"

_INVOCATION = re.compile(r"^(go_)?proof\s+\"")

# The cross-check's own pattern, and every difference from `_INVOCATION` above
# is deliberate slack rather than a second opinion. Leading whitespace is
# allowed, the `go_` prefix is generalised to any prefix, and the opening quote
# is not required — so this matches a superset of what extraction reads, and
# the only signal it can produce is "a line that looks like a declaration did
# not become a proof". A pattern that were *stricter* anywhere could report rot
# that is not there, which is the mistake this whole file is written against.
#
# The negative lookahead drops the two definitions, `proof () {` and
# `go_proof () {`. `\b` is what keeps `proof_count=3` and similar out: `\w*`
# cannot end at `proof` when a word character follows it.
_DECLARATION_SHAPED = re.compile(r"^\s*\w*proof\b(?!\s*\(\))", re.M)


class Proof:
    def __init__(self, kind: str, name: str, path: str, test: str, snippet: str):
        self.kind = kind
        self.name = name
        self.path = path
        self.test = test
        self.snippet = snippet


def extract(proof_text: str) -> list[Proof]:
    """Pull the proof declarations out of the harness, using bash to unquote.

    The declarations are re-evaluated by `bash` with `proof` and `go_proof`
    redefined as emitters, so the quoting rules are the shell's own rather than
    a second implementation of them that would drift. Only the invocation lines
    are evaluated; nothing else in the harness runs.
    """
    lines = proof_text.splitlines()
    blocks: list[str] = []
    i = 0
    while i < len(lines):
        if _INVOCATION.match(lines[i]):
            block = [lines[i]]
            while block[-1].rstrip().endswith("\\") and i + 1 < len(lines):
                i += 1
                block.append(lines[i])
            blocks.append("\n".join(block))
        i += 1

    shim = (
        'proof() { printf "%s\\0" py "$1" "$2" "$3" "$4"; }\n'
        'go_proof() { printf "%s\\0" go "$1" "$2" "$3" "$4"; }\n'
    ) + "\n".join(blocks) + "\n"

    with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False) as fh:
        fh.write(shim)
        shim_path = fh.name
    try:
        out = subprocess.run(
            ["bash", shim_path], capture_output=True, text=True, check=True
        ).stdout
    finally:
        pathlib.Path(shim_path).unlink(missing_ok=True)

    fields = out.split("\0")[:-1]
    if len(fields) % 5:
        raise SystemExit(f"the proof listing came back malformed: {len(fields)} fields")
    return [Proof(*fields[i : i + 5]) for i in range(0, len(fields), 5)]


def _go_test_names(root: pathlib.Path) -> set[str]:
    names: set[str] = set()
    go_dir = root / GO_DIR
    if not go_dir.is_dir():
        return names
    for path in go_dir.rglob("*_test.go"):
        names.update(re.findall(r"^func (Test\w+)\(", path.read_text(), re.M))
    return names


def _python_test_names(path: pathlib.Path) -> set[str]:
    if not path.is_file():
        return set()
    return set(re.findall(r"^\s*def (test_\w+)\(", path.read_text(), re.M))


def check(
    root: pathlib.Path,
    proofs_from: pathlib.Path | None = None,
    exact_only: bool = False,
) -> list[tuple[str, str, str]]:
    """Return (severity, proof name, message) for everything worth saying."""
    proof_path = proofs_from or (root / PROOF_FILE)
    if not proof_path.is_file():
        return [("error", PROOF_FILE, "no proof file at this root")]

    proof_text = proof_path.read_text()
    proofs = extract(proof_text)
    go_names = _go_test_names(root)
    findings: list[tuple[str, str, str]] = []

    # The floor. See the module docstring: a run that extracted nothing, or
    # extracted less than the file declares, has checked correspondingly less
    # and must not be able to report success.
    shaped = [m.group(0).strip() for m in _DECLARATION_SHAPED.finditer(proof_text)]
    if not proofs:
        findings.append((
            "error", proof_path.name,
            f"no proof declarations could be extracted from {proof_path}. "
            f"{len(shaped)} line(s) in it are declaration-shaped. Refusing to "
            "report success: every check below is per-proof, so zero proofs "
            "means zero checks and a clean exit would say the opposite. Either "
            "this is not the proofs file, or the declaration syntax has moved "
            "away from the `^proof \"` / `^go_proof \"` form extraction reads.",
        ))
    elif len(shaped) > len(proofs):
        missed = ", ".join(sorted(set(shaped))[:5])
        findings.append((
            "error", proof_path.name,
            f"extraction read {len(proofs)} proofs from {len(shaped)} "
            f"declaration-shaped lines, so {len(shaped) - len(proofs)} "
            "declaration(s) are being skipped silently and whatever they prove "
            "is unchecked. `_INVOCATION` is anchored at the start of the line "
            "and allows no leading whitespace, so indenting a declaration is "
            f"the usual cause. Leading tokens seen: {missed}.",
        ))

    for proof in proofs:
        target = root / proof.path
        if not target.is_file():
            findings.append(("error", proof.name, f"names {proof.path}, which does not exist"))
            continue

        try:
            _, mode = apply_snippet(
                target.read_text(), proof.snippet, str(target), exact_only=exact_only
            )
        except TamperError as exc:
            severity = "error"
            findings.append((severity, proof.name, f"{exc.code}: {exc.detail}"))
        else:
            if mode == OK_NORMALIZED:
                findings.append(
                    (
                        "warning",
                        proof.name,
                        "the tamper matches only after whitespace normalization — a "
                        "formatter has moved this site; rewrite the string to the "
                        "source's current form",
                    )
                )

        # The test selector. Nothing else in the repository checks this.
        if proof.kind == "py":
            selector, _, test_name = proof.test.partition("::")
            test_file = root / selector
            if not test_file.is_file():
                findings.append(
                    ("error", proof.name, f"runs {selector}, which does not exist")
                )
            elif test_name:
                bare = test_name.split("::")[-1]
                if bare not in _python_test_names(test_file):
                    findings.append(
                        (
                            "error",
                            proof.name,
                            f"runs {bare}, which is not defined in {selector} — pytest "
                            f"exits 4 for a missing selector, which the harness reads as "
                            f"a failing test and reports as proved",
                        )
                    )
        else:
            for alternative in proof.test.split("|"):
                wanted = alternative.strip()
                if wanted and wanted not in go_names:
                    findings.append(
                        (
                            "error",
                            proof.name,
                            f"runs {wanted}, which is not defined under {GO_DIR} — "
                            f"`go test -run` exits 0 when it matches nothing",
                        )
                    )

    findings.insert(0, ("info", "", f"{len(proofs)} proofs declared"))
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(REPO), help="repository root to check")
    parser.add_argument("--format", choices=("text", "summary"), default="text")
    parser.add_argument(
        "--warnings-as-errors",
        action="store_true",
        help="a tamper surviving only on whitespace tolerance fails the run",
    )
    parser.add_argument(
        "--proofs",
        default=None,
        help="read the declarations from this file instead of the root's own; "
        "scores one revision's tampers against another revision's source",
    )
    parser.add_argument(
        "--exact-only",
        action="store_true",
        help="match as the harness did before 2026-08-03, with whitespace "
        "significant; reproduces the historical rot",
    )
    args = parser.parse_args(argv)

    findings = check(
        pathlib.Path(args.root).resolve(),
        pathlib.Path(args.proofs).resolve() if args.proofs else None,
        exact_only=args.exact_only,
    )
    errors = [f for f in findings if f[0] == "error"]
    warnings = [f for f in findings if f[0] == "warning"]
    declared = next((f[2] for f in findings if f[0] == "info"), "")

    if args.format == "summary":
        print(f"tamper-rot: {declared}, {len(errors)} errors, {len(warnings)} warnings")
    else:
        for severity, name, message in findings:
            if severity == "info":
                print(f"{message}")
            else:
                print(f"  {severity.upper():8} {name}\n           {message}")
        print()
        print(f"{len(errors)} errors, {len(warnings)} warnings")

    if errors:
        return 1
    if warnings and args.warnings_as_errors:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
