"""T023 — the invariant runner. Runs the whole set, in milliseconds, with no
model in it.

Two jobs, and the second is the one that keeps the file honest:

1. Run every test named in `invariants.yaml`.
2. **Reconcile** — every invariant has a test file that exists, and every test
   file in `tests/invariants/` is named by an invariant. An invariants file
   that drifts from its tests is worse than no invariants file, because it
   reports a guarantee nobody is checking.

Exit code is 0 only when both pass. Wired into T005's CI.

Run it directly:

    python3 tests/invariants/runner.py
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover - dependency is declared
    sys.exit(
        "PyYAML is required to read the invariants file.\n"
        "  pip install -r requirements.lock   (or: pip install -e '.[dev]')"
    )

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
INVARIANTS = HERE / "invariants.yaml"

# `runner.py` is not an invariant test; `conftest.py` and `__init__.py` are
# scaffolding. Everything else under tests/invariants/ must be named by an
# entry.
NOT_A_TEST = {"runner.py", "conftest.py", "__init__.py"}


def load() -> dict:
    with INVARIANTS.open() as handle:
        return yaml.safe_load(handle)


def reconcile(
    document: dict,
    here: Path | None = None,
    repo: Path | None = None,
) -> list[str]:
    """Every invariant names a test that exists; every test file has a row.

    `here` and `repo` default to this directory and the repository root.
    Tests pass a planted tree so an emptied checker fails the plant rather
    than passing over the live set (T198).
    """
    here = here if here is not None else HERE
    repo = repo if repo is not None else REPO
    problems: list[str] = []
    declared: set[str] = set()

    for entry in document["invariants"]:
        for field in ("id", "discharges", "statement", "test", "removal_proof"):
            if not entry.get(field):
                problems.append(f"{entry.get('id', '<no id>')}: missing {field}")
        if entry.get("model_in_loop") is not False:
            problems.append(
                f"{entry['id']}: model_in_loop must be false — an invariant a "
                "model evaluates is not machine-checkable "
                "(constitution Principle I)"
            )
        test = entry.get("test")
        if not test:
            continue
        declared.add(Path(test).name)
        if not (repo / test).exists():
            problems.append(f"{entry['id']}: names {test}, which does not exist")

        # `also` names an arm this runner cannot execute — a Go test, say.
        # Its existence is still checked, because an invariant whose second
        # arm has been deleted is an invariant that quietly halved.
        also = entry.get("also")
        if also and not (repo / also).exists():
            problems.append(
                f"{entry['id']}: names a second arm {also}, which does not "
                "exist. Run it with the toolchain it belongs to."
            )

    present = {
        path.name for path in here.glob("test_*.py")
    } | {
        path.name for path in here.glob("*.py") if path.name.startswith("test")
    }
    for name in sorted(present - declared - NOT_A_TEST):
        problems.append(
            f"tests/invariants/{name} is not named by any invariant. Add an "
            "entry or move the test out of tests/invariants/."
        )
    return problems


def outcome_shortfall(report: Path, targets: list[str]) -> list[tuple[str, str]]:
    """Which named test files contributed no executed outcome.

    Reads the JUnit report rather than pytest's exit code, because the exit
    code is one bit for the whole run and the question here is per file. A file
    is silent if it produced no test cases at all, or if every case it produced
    was skipped — a facility-gated invariant that skips everywhere is an
    invariant with no evidence behind it, however green the run looks.
    """
    try:
        import xml.etree.ElementTree as ET
        tree = ET.parse(report)
    except ImportError as exc:  # pragma: no cover - interpreter without expat
        return [("<report>", f"cannot read the JUnit report: {exc}")]
    except (OSError, Exception) as exc:  # noqa: BLE001 - includes ParseError
        return [(str(report), f"no readable JUnit report was produced: {exc}")]

    # pytest's JUnit writer emits no `file` attribute — only `classname`, the
    # dotted module path, with a class name appended when the test lives in one.
    # Match on that rather than assuming an attribute that is not there; an
    # attribute lookup that silently returns None for every case would mark all
    # nine invariants silent, which is this function's own version of the defect
    # it exists to catch. (It did exactly that on the first attempt.)
    module_of = {
        t: t[: -len(".py")].replace("/", ".") for t in targets
    }
    ran: dict[str, int] = {t: 0 for t in targets}
    skipped: dict[str, int] = {t: 0 for t in targets}
    for case in tree.iter("testcase"):
        classname = case.get("classname") or ""
        for target, module in module_of.items():
            if classname == module or classname.startswith(module + "."):
                if case.find("skipped") is not None:
                    skipped[target] += 1
                else:
                    ran[target] += 1
                break

    problems: list[tuple[str, str]] = []
    for target in targets:
        if ran[target] == 0:
            if skipped[target]:
                problems.append(
                    (target, f"collected {skipped[target]} test(s) and skipped "
                             "every one of them")
                )
            else:
                problems.append(
                    (target, "collected no tests at all — the file exists, so "
                             "reconciliation passed, but there is nothing in it")
                )
    return problems


def main() -> int:
    document = load()
    print(f"invariants.yaml version {document['version']} "
          f"({len(document['invariants'])} invariants)")

    problems = reconcile(document)
    if problems:
        print("\nReconciliation failed:")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print("reconciliation OK — every invariant has a test, every test an "
          "invariant")

    # Run the tests the document NAMES, not the directory it lives in. Those
    # were the same set until an invariant's test was placed outside
    # tests/invariants/, at which point running the directory silently stopped
    # running one of the invariants while still reporting success.
    targets = sorted({entry["test"] for entry in document["invariants"]})
    unrunnable = [entry["also"] for entry in document["invariants"] if entry.get("also")]

    started = time.perf_counter()
    # `-rs` because a skipped invariant and a passing one are the same line in
    # `-q` output, and an invariant that skipped for want of a facility is an
    # invariant nobody checked. `--junitxml` because the reconciliation below
    # needs per-file outcome counts, which the human-readable output does not
    # carry.
    report = REPO / "tests" / "invariants" / ".invariants-report.xml"
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-rs",
         f"--junitxml={report}", *targets],
        cwd=REPO,
    )
    elapsed = (time.perf_counter() - started) * 1000
    print(f"\ninvariant suite ran in {elapsed:.0f} ms "
          f"({len(targets)} files named by {len(document['invariants'])} invariants)")

    # **The line above counts files, and a file is not a check.** Reconciliation
    # proves each invariant NAMES a file that EXISTS; it never proved the file
    # contains a test. Blanking the body of `test_result_constructor.py` while
    # leaving the file in place was measured on 2026-08-04: the runner printed
    # `reconciliation OK` and `9 files named by 9 invariants`, pytest reported
    # the remaining tests as passed, and the runner exited 0 — INV-001 was
    # checked by nothing and the fastest job in CI was green over it. pytest
    # cannot catch this either; exit code 5 needs the collection to be *empty*,
    # and here eight of nine files still collect.
    silent = outcome_shortfall(report, targets)
    if silent:
        print("\nAn invariant's test file exists and ran nothing:")
        for path, why in silent:
            print(f"  - {path}: {why}")
        print("\nThe invariant it discharges is currently unchecked. This is "
              "not a pytest failure — pytest has nothing to fail on.")
        return 1
    if unrunnable:
        print("\nSecond arms this runner cannot execute — run them yourself:")
        for path in sorted(unrunnable):
            print(f"  {path}    (cd src/proxy && go test ./...)")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
