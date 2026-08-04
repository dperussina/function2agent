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


def reconcile(document: dict) -> list[str]:
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
        if not (REPO / test).exists():
            problems.append(f"{entry['id']}: names {test}, which does not exist")

        # `also` names an arm this runner cannot execute — a Go test, say.
        # Its existence is still checked, because an invariant whose second
        # arm has been deleted is an invariant that quietly halved.
        also = entry.get("also")
        if also and not (REPO / also).exists():
            problems.append(
                f"{entry['id']}: names a second arm {also}, which does not "
                "exist. Run it with the toolchain it belongs to."
            )

    present = {
        path.name for path in HERE.glob("test_*.py")
    } | {
        path.name for path in HERE.glob("*.py") if path.name.startswith("test")
    }
    for name in sorted(present - declared - NOT_A_TEST):
        problems.append(
            f"tests/invariants/{name} is not named by any invariant. Add an "
            "entry or move the test out of tests/invariants/."
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
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", *targets],
        cwd=REPO,
    )
    elapsed = (time.perf_counter() - started) * 1000
    print(f"\ninvariant suite ran in {elapsed:.0f} ms "
          f"({len(targets)} files named by {len(document['invariants'])} invariants)")
    if unrunnable:
        print("\nSecond arms this runner cannot execute — run them yourself:")
        for path in sorted(unrunnable):
            print(f"  {path}    (cd src/proxy && go test ./...)")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
