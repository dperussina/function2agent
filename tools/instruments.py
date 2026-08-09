"""The instrument census — every check in this repository that can fail, in one
place, reconciled against the workflow that runs them.

## Why this file exists

For a week the brief handed to each pass carried a five-item list of gates —
`pytest`, `check_corpus.py`, `gen_claims.py --check`, `check_tampers.py`,
`removal_proofs.sh` — and every pass duly reported "all five green". There were
never five. `tests/invariants/runner.py` was the sixth, it went red at `7349e31`
on 2026-08-08, and it stayed red through three CI runs (`abca043`, `821ef70`,
`6cdd4a5`) that failed on it **and only on it**. Every one of those passes was
telling the truth about the five it had been told about.

That is a new shape of the same defect this repository keeps finding. Findings
032 and 034 are instruments that *lied*. This is an instrument that was
**absent from the list of instruments** — nothing lied, and nothing was
checking that the list was the set.

## The claim this file makes, and the one it does not

It makes exactly one machine-checkable claim: **the table below and
`.github/workflows/ci.yml` agree.** `--check` proves it in three directions, and
each closes a different way the two drift apart:

1. **Declared and absent.** An entry says it runs in CI job *J* and *J*'s block
   does not contain its invocation. This is a step deleted or a job renamed
   while the census went on advertising it.
2. **Present and undeclared.** A `run:` step names a repository instrument that
   no entry names. This is the defect above, mechanised: a new gate wired into
   CI cannot stay off the list.
3. **Unclassified.** A file that *looks* like an entry point — every top-level
   `tools/*.py`, plus the two harness entry points outside it — that no entry
   names at all. This is what catches a tool arriving in the tree before
   anybody decides whether it gates anything.

What it does **not** claim: that any instrument is correct, that the set is
sufficient, or that a green `--run` means anything about the repository. It is
a census, not a verdict. Direction 3 in particular forces a *classification*,
not an endorsement — `library` is a real answer and four files use it.

## What is deliberately not here

- **No timeout.** Not one number in this file is a duration, because no
  duration in it has been measured. `tests/removal_proofs.sh` already carries a
  measured per-arm cap (`tools/proof_timeout.py`) and CI carries measured job
  bounds; a third bound invented here would be the one nobody derived.
- **No ordering claim.** `--run` executes the table top to bottom and **does
  not stop at the first failure** — it runs everything and reports every
  verdict, so the order changes nothing about the outcome. The one place order
  is load-bearing is the corpus set, where `selftest.py` precedes
  `check_corpus.py`; that ordering is inherited from `ci.yml`'s own stated
  argument rather than invented here.
- **`--run` is never wired into CI.** CI already runs these, in the jobs whose
  bounds were derived for them, split so that a contributor does not wait on a
  container build to learn the model-judge boundary was crossed. Running the
  set again in one job would collapse that split and make a nine-minute
  instrument mandatory in a nine-second job. `--check` is the half that gates,
  and it is milliseconds and stdlib-only.

## Usage

    python3 tools/instruments.py              # the census
    python3 tools/instruments.py --check      # reconcile against ci.yml
    python3 tools/instruments.py --run        # run the fast gates
    python3 tools/instruments.py --run --all  # ... and the slow ones too

Standard library only, no network, no PyYAML — `ci.yml` is read as text, which
is also what keeps this runnable in the `corpus` job, the one job that installs
nothing and is therefore the only thing still checking that claim.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
WORKFLOW = REPO / ".github" / "workflows" / "ci.yml"

#: A gate's non-zero exit fails something. An advisory's does not — either
#: because the step carries `continue-on-error`, or because the tool has no
#: failing exit by design. A library is not invoked as a program at all; it is
#: listed so that direction 3 below forces every file to be classified rather
#: than merely not-noticed.
GATE, ADVISORY, LIBRARY = "gate", "advisory", "library"


@dataclass(frozen=True)
class Instrument:
    name: str
    kind: str
    checks: str
    #: The CI job key in `ci.yml` this runs under, or None for hand-run.
    job: str | None
    #: A substring that must appear inside that job's block. Empty for
    #: libraries and hand-run tools, which direction 1 does not apply to.
    anchor: str = ""
    #: What to execute for `--run`, as argv. Empty when there is nothing
    #: standalone to execute — an assertion inlined in a shell step, or a
    #: library.
    command: tuple[str, ...] = ()
    #: Files this entry accounts for under direction 3.
    files: tuple[str, ...] = ()
    #: True when the instrument costs minutes rather than seconds, or needs a
    #: facility a developer host may not have. Excluded from `--run` unless
    #: `--all`. No number attached: see the header.
    slow: bool = False
    needs: str = ""
    notes: str = ""
    #: Display override for the census table, for the one entry that runs in
    #: every job and so is neither `job`-shaped nor hand-run.
    where: str = ""


INSTRUMENTS: list[Instrument] = [
    # -- job `invariants` ----------------------------------------------------
    Instrument(
        name="invariants runner",
        kind=GATE,
        checks="Runs the ten-plus invariant tests named by invariants.yaml, and "
               "reconciles that file against tests/invariants/ in both "
               "directions. Also fails when a named file exists but collected "
               "no outcome, because a file is not a check.",
        job="invariants",
        anchor="run: python tests/invariants/runner.py",
        command=("python3", "tests/invariants/runner.py"),
        files=("tests/invariants/runner.py",),
        needs="PyYAML",
    ),
    Instrument(
        name="tamper rot check",
        kind=GATE,
        checks="Every removal proof's tamper still names exactly one live site, "
               "and every test it names still exists. Zero extracted proofs is "
               "an error, and a declaration-shaped line that produced no proof "
               "is an error.",
        job="invariants",
        anchor="run: python tools/check_tampers.py",
        command=("python3", "tools/check_tampers.py"),
        files=("tools/check_tampers.py",),
    ),
    # -- job `corpus` --------------------------------------------------------
    Instrument(
        name="corpus self-test",
        kind=GATE,
        checks="Every corpus check fires on a planted defect in known-bad and "
               "none fires on known-good. First in the corpus job because a "
               "validator whose regex stopped matching passes everything.",
        job="corpus",
        anchor="run: python3 tools/selftest.py",
        command=("python3", "tools/selftest.py"),
        files=("tools/selftest.py",),
    ),
    Instrument(
        name="threshold probe",
        kind=GATE,
        checks="Moves every tolerance, window, bound and distance in the check "
               "set by one unit and requires the self-test to break. A green "
               "self-test shows a check fires, not that its constant is right.",
        job="corpus",
        anchor="run: python3 tools/threshold_probe.py",
        command=("python3", "tools/threshold_probe.py"),
        files=("tools/threshold_probe.py",),
    ),
    Instrument(
        name="corpus check",
        kind=GATE,
        checks="Seventeen consistency checks over the document corpus. Errors "
               "only — warnings are printed by a separate step that cannot "
               "fail, because a gate that flaps gets worked around.",
        job="corpus",
        anchor="run: python3 tools/check_corpus.py\n",
        command=("python3", "tools/check_corpus.py"),
        files=("tools/check_corpus.py",),
    ),
    Instrument(
        name="corpus warnings report",
        kind=ADVISORY,
        checks="The same check set including warnings, rendered to the run "
               "page. `--report-only` always exits 0 and this step is not "
               "trying to fail.",
        job="corpus",
        anchor="python3 tools/check_corpus.py --report-only",
        command=("python3", "tools/check_corpus.py", "--report-only"),
    ),
    Instrument(
        name="generated claims",
        kind=GATE,
        checks="Line counts and register ranges in prose still match the "
               "artifacts they describe. Reports per generator and exits 1 when "
               "any generator matched no sites at all.",
        job="corpus",
        anchor="run: python3 tools/gen_claims.py --check",
        command=("python3", "tools/gen_claims.py", "--check"),
        files=("tools/gen_claims.py",),
    ),
    # -- job `python` --------------------------------------------------------
    Instrument(
        name="linux facility preflight",
        kind=GATE,
        checks="cgroup v2, mount namespaces and seccomp user notification are "
               "present. OD-17 has no degraded mode, so a missing facility "
               "fails the job rather than skipping the tests that need it.",
        job="python",
        anchor="python -m src.supervisor.preflight",
        command=("python3", "-m", "src.supervisor.preflight"),
        files=("src.supervisor.preflight",),
        slow=True,
        needs="privileged Linux",
    ),
    Instrument(
        name="pytest",
        kind=GATE,
        checks="The suite. Run in CI as two disjoint halves, unprivileged and "
               "privileged, so that the privileged half runs at the euid the "
               "supervisor actually uses.",
        job="python",
        anchor='python -m pytest tests -q -rs -m "not privileged"',
        command=("python3", "-m", "pytest", "tests", "-q", "-rs"),
        slow=True,
        needs="Linux for the kernel arms; privileges for the privileged half",
    ),
    Instrument(
        name="pytest outcome reader",
        kind=GATE,
        checks="Reads the JUnit reports back and fails for the three things a "
               "pytest exit status cannot express: a missing report, a half "
               "that collected nothing, and a half that collected work and "
               "skipped all of it.",
        job="python",
        anchor="python3 tools/pytest_outcomes.py",
        files=("tools/pytest_outcomes.py",),
        slow=True,
        needs="JUnit reports from a pytest run",
        notes="Takes reports as arguments; nothing to run standalone.",
    ),
    Instrument(
        name="seccomp figure present",
        kind=GATE,
        checks="The privileged suite left a seccomp-overhead figure. Absence "
               "is a failure rather than a warning, because the file is "
               "missing exactly when the measurement did not happen.",
        job="python",
        anchor="seccomp overhead — NOT PRODUCED",
        slow=True,
        needs="a privileged CI run",
        notes="Inlined in the workflow shell; no standalone command.",
    ),
    Instrument(
        name="pytest artifact upload",
        kind=GATE,
        checks="`if-no-files-found: error` on the outcome record. A run that "
               "published no record of what it ran does not get to be green.",
        job="python",
        anchor="name: pytest-outcomes-and-native-overhead",
        notes="A workflow property, not a program. Only CI can exercise it.",
    ),
    Instrument(
        name="unshare pair observation",
        kind=ADVISORY,
        checks="Whether an unprivileged user namespace can be created on the "
               "runner, against a privileged control on the same VM. Measures "
               "a property of the runner image and not of this repository, so "
               "`continue-on-error: true` is the design and not a convenience.",
        job="python",
        anchor="python3 tools/unshare_pair_observation.py",
        command=("python3", "tools/unshare_pair_observation.py",
                 "--label", "census", "--out", "/dev/null"),
        files=("tools/unshare_pair_observation.py",),
        slow=True,
        needs="Linux",
    ),
    # -- job `removal-proofs` ------------------------------------------------
    Instrument(
        name="removal proofs",
        kind=GATE,
        checks="Edits each mechanism out of a copy of the tree and requires the "
               "test that claims to depend on it to fail. Refuses to report at "
               "all when its untampered baseline produced no outcomes.",
        job="removal-proofs",
        anchor="bash tests/removal_proofs.sh",
        command=("bash", "tests/removal_proofs.sh"),
        files=("tests/removal_proofs.sh",),
        slow=True,
        needs="pytest, a Go toolchain, privileged Linux; minutes",
    ),
    Instrument(
        name="removal-proof record renderer",
        kind=GATE,
        checks="Renders the harness's per-arm JSON record, and exits non-zero "
               "when there is no record to read — a harness step that went "
               "green without leaving one is the unauditable state the job "
               "exists to repair.",
        job="removal-proofs",
        anchor="python3 tools/removal_proofs_summary.py",
        files=("tools/removal_proofs_summary.py",),
        slow=True,
        needs="a record from a removal-proofs run",
        notes="Takes a record path; nothing to run standalone.",
    ),
    Instrument(
        name="proof attribution",
        kind=ADVISORY,
        checks="Which test each tamper actually breaks. No finding it reports "
               "changes its status; its only non-zero exit is the same "
               "baseline refusal the harness makes.",
        job="removal-proofs",
        anchor="python3 tools/proof_attribution.py",
        command=("python3", "tools/proof_attribution.py"),
        files=("tools/proof_attribution.py",),
        slow=True,
        needs="pytest, a Go toolchain, privileged Linux; minutes",
    ),
    # -- job `go` ------------------------------------------------------------
    Instrument(
        name="go vet",
        kind=GATE,
        checks="Vet over the enforcement point.",
        job="go",
        anchor="run: go vet ./...",
        command=("go", "vet", "./..."),
        files=(),
        slow=True,
        needs="a Go toolchain; run from src/proxy",
        notes="Run with cwd=src/proxy.",
    ),
    Instrument(
        name="go test",
        kind=GATE,
        checks="The enforcement point's suite under `-race -count=1`, plus "
               "three assertions the exit status cannot make: no `(cached)` "
               "line came back, no package under ./... has no test files, and "
               "the outcome count is not zero.",
        job="go",
        anchor="go test ./... -race -count=1 -v",
        slow=True,
        needs="a Go toolchain, and cgo for -race",
        notes="Run with cwd=src/proxy. The three assertions are inlined in the "
              "workflow shell, so there is no standalone command that makes "
              "them.",
    ),
    Instrument(
        name="go artifact upload",
        kind=GATE,
        checks="`if-no-files-found: error` on the Go outcome list.",
        job="go",
        anchor="name: go-test-outcomes",
        notes="A workflow property, not a program.",
    ),
    Instrument(
        name="go build",
        kind=GATE,
        checks="The enforcement point still builds as a single static binary.",
        job="go",
        anchor="go build -o /tmp/f2a-proxy ./...",
        command=("go", "build", "-o", "/tmp/f2a-proxy", "./..."),
        slow=True,
        needs="a Go toolchain; run from src/proxy",
        notes="Run with cwd=src/proxy.",
    ),
    # -- every job -----------------------------------------------------------
    Instrument(
        name="runner identity",
        kind=GATE,
        checks="Writes the kernel, arch, image and euid each job's figures are "
               "a property of. `set -euo pipefail`, so it can fail the job it "
               "labels.",
        job=None,
        where="CI, every job",
        notes="A composite action used by all five jobs; direction 1 does not "
              "apply because it is a `uses:` and not a `run:`.",
    ),
    # -- hand-run ------------------------------------------------------------
    Instrument(
        name="instrument census",
        kind=GATE,
        checks="This file. Reconciles the census against ci.yml in three "
               "directions. It is wired into the corpus job, which installs "
               "nothing, because a census nothing checks is the folklore it "
               "replaces.",
        job="corpus",
        anchor="run: python3 tools/instruments.py --check",
        command=("python3", "tools/instruments.py", "--check"),
        files=("tools/instruments.py",),
    ),
    Instrument(
        name="citation advisor",
        kind=ADVISORY,
        checks="Ranks every requirement against each contract's subject and "
               "lists high scorers the contract does not name. Deliberately "
               "unwired: the gate rule underneath it was built, measured "
               "against 184 ablated clean cases, and rejected.",
        job=None,
        command=("python3", "tools/cite_advisor.py"),
        files=("tools/cite_advisor.py",),
    ),
    Instrument(
        name="wall-clock ceiling probe",
        kind=ADVISORY,
        checks="Plants FR-005's wall-clock ceiling against a real AgentLoop "
               "with three control dimensions on the same harness. A probe, "
               "not a gate: it reports what a session terminated on.",
        job=None,
        command=("python3", "tools/wall_clock_ceiling_probe.py"),
        files=("tools/wall_clock_ceiling_probe.py",),
        slow=True,
    ),
    # -- libraries -----------------------------------------------------------
    Instrument(
        name="tamper matcher",
        kind=LIBRARY,
        checks="The matcher the harness edits source with. Exercised by "
               "tests/unit/test_tamper_matching.py, which also pins "
               "EXPECTED_PROOFS.",
        job=None,
        files=("tools/tamper.py",),
    ),
    Instrument(
        name="per-arm wall-clock cap",
        kind=LIBRARY,
        checks="The cap the harness and the attribution tool run every arm "
               "under. Exits 124, which the harness scores as timed-out and "
               "never as proved or skipped.",
        job=None,
        files=("tools/proof_timeout.py",),
    ),
]


# ---------------------------------------------------------------------------
# Reconciliation.


def _jobs(text: str) -> dict[str, str]:
    """Split the workflow into per-job blocks.

    Textual on purpose: this file has no PyYAML, so that it runs in the one CI
    job that installs nothing. A job header is a two-space-indented key under
    `jobs:`, which is the only place that indentation occurs in this file.
    """
    body = text.split("\njobs:\n", 1)
    if len(body) != 2:
        raise ValueError("no `jobs:` block in the workflow")
    blocks: dict[str, str] = {}
    current: str | None = None
    lines: list[str] = []
    for line in body[1].splitlines(keepends=True):
        header = re.match(r"^  ([A-Za-z0-9_-]+):\s*$", line)
        if header:
            if current:
                blocks[current] = "".join(lines)
            current, lines = header.group(1), []
            continue
        lines.append(line)
    if current:
        blocks[current] = "".join(lines)
    return blocks


#: What a `run:` step referencing one of these is: an instrument, and therefore
#: something the census must name. Deliberately file-shaped — a bare `pytest`
#: or `go test` is caught by direction 1 instead, and inventing a pattern for
#: every possible command would be a classifier stated as a complement.
_REFERENCE = re.compile(
    r"tools/[\w-]+\.py|tests/[\w./-]+\.(?:py|sh)|src\.supervisor\.[\w.]+"
)

#: Everything that could be an entry point, for direction 3. `tools/fixtures/`
#: and `tools/corpuscheck/` are excluded because they are a corpus and a
#: package respectively, neither invoked as a program.
def _entry_point_candidates() -> list[str]:
    found = [
        f"tools/{path.name}"
        for path in sorted((REPO / "tools").glob("*.py"))
    ]
    found.append("tests/removal_proofs.sh")
    found.append("tests/invariants/runner.py")
    return found


def reconcile(text: str | None = None,
              candidates: list[str] | None = None) -> list[str]:
    """Both arguments exist so the three directions can be shown to fire.

    `tests/unit/test_instrument_census.py` perturbs a workflow and a candidate
    list and asserts each direction reports. A checker with no such test is the
    failure mode `tools/README.md` opens with — a validator that passes
    everything because its pattern never matches — and this file would be an
    unusually embarrassing place to reproduce it.
    """
    problems: list[str] = []
    text = WORKFLOW.read_text() if text is None else text
    blocks = _jobs(text)

    # 1. Declared and absent.
    for entry in INSTRUMENTS:
        if not entry.job or not entry.anchor:
            continue
        block = blocks.get(entry.job)
        if block is None:
            problems.append(
                f"{entry.name}: names CI job {entry.job!r}, which the workflow "
                "does not define. A renamed job detaches everything pointed at "
                "it."
            )
            continue
        if entry.anchor not in block:
            problems.append(
                f"{entry.name}: job {entry.job!r} does not contain "
                f"{entry.anchor!r}. Either the step went away or the census is "
                "advertising a gate that no longer runs."
            )

    # 2. Present and undeclared. Comment lines are dropped first: this file's
    #    own workflow discusses several instruments in prose, including one it
    #    deliberately does not wire, and a scanner that matched those would
    #    report the opposite of the truth about them.
    named = {name for entry in INSTRUMENTS for name in entry.files}
    for job, block in blocks.items():
        for line in block.splitlines():
            if line.lstrip().startswith("#"):
                continue
            for reference in _REFERENCE.findall(line):
                if reference not in named:
                    problems.append(
                        f"job {job!r} runs {reference}, which no census entry "
                        "names. Add it to INSTRUMENTS — a gate wired into CI "
                        "and missing from the list is exactly the defect this "
                        "file exists to close."
                    )

    # 3. Unclassified.
    for candidate in (_entry_point_candidates() if candidates is None else candidates):
        if candidate not in named:
            problems.append(
                f"{candidate} is named by no census entry. Classify it: "
                f"{GATE}, {ADVISORY} or {LIBRARY}. `{LIBRARY}` is a real "
                "answer; not deciding is not."
            )

    return problems


# ---------------------------------------------------------------------------
# Output.


def render() -> str:
    rows = ["| instrument | kind | runs in | invocation |",
            "|---|---|---|---|"]
    for entry in INSTRUMENTS:
        where = entry.where or (f"CI `{entry.job}`" if entry.job else "hand-run")
        if entry.kind == LIBRARY:
            where = "—"
        command = " ".join(entry.command) if entry.command else "—"
        rows.append(f"| {entry.name} | {entry.kind} | {where} | `{command}` |")
    return "\n".join(rows)


def run(include_slow: bool) -> int:
    selected = [
        entry for entry in INSTRUMENTS
        if entry.kind == GATE and entry.command and (include_slow or not entry.slow)
    ]
    skipped = [
        entry for entry in INSTRUMENTS
        if entry.kind == GATE and not (entry.command and (include_slow or not entry.slow))
    ]
    failed: list[str] = []
    for entry in selected:
        print(f"\n=== {entry.name}: {' '.join(entry.command)}", flush=True)
        cwd = REPO / "src" / "proxy" if entry.name.startswith("go ") else REPO
        result = subprocess.run(entry.command, cwd=cwd)
        print(f"--- {entry.name}: exit {result.returncode}", flush=True)
        if result.returncode != 0:
            failed.append(entry.name)

    print("\n" + "=" * 70)
    print(f"ran {len(selected)} gate(s); {len(failed)} failed")
    for name in failed:
        print(f"  FAILED  {name}")
    # Every gate this could not run is named, because a run that quietly
    # covered eleven of nineteen and printed one green line is the reporting
    # defect this file was written for.
    if skipped:
        print(f"\n{len(skipped)} gate(s) NOT run here, and they are still gates:")
        for entry in skipped:
            why = entry.notes or entry.needs or "slow"
            print(f"  {entry.name}: {why}")
        print("\nThis is not a clean bill of health for the set. CI runs all of "
              "them; `--check` is what proves the set is the set.")
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true",
                        help="reconcile the census against ci.yml")
    parser.add_argument("--run", action="store_true",
                        help="run the gates that have a standalone command")
    parser.add_argument("--all", action="store_true",
                        help="with --run, include the slow ones")
    args = parser.parse_args(argv)

    if args.run:
        return run(include_slow=args.all)

    if args.check:
        problems = reconcile()
        counts = {kind: sum(1 for e in INSTRUMENTS if e.kind == kind)
                  for kind in (GATE, ADVISORY, LIBRARY)}
        print(f"{len(INSTRUMENTS)} instrument(s): "
              f"{counts[GATE]} gate, {counts[ADVISORY]} advisory, "
              f"{counts[LIBRARY]} library")
        if problems:
            print("\nThe census and .github/workflows/ci.yml disagree:")
            for problem in problems:
                print(f"  - {problem}")
            return 1
        print("census OK — every declared gate is in the workflow, every "
              "instrument the workflow runs is declared, every entry point is "
              "classified")
        return 0

    print(render())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
