"""T116 — the reference application's **stated size**, measured rather than estimated.

**Requirement**: FR-053. Read by T118 and T203.

## Why this is a module and not a sentence in a README

The size is a denominator. **U-21** records `codegraph`'s scale claim as
untested on a single small-repository datapoint — `adk-python` at 1,867 files
and 48,154 nodes in 7.8 seconds, which is a small fraction of the claimed file
count and extrapolates nothing — so **SC-001**'s fifteen-minute window contains
an unbounded step. A wall time reported without the size it was measured over
is a figure nobody can divide, and the criterion is then quietly true on small
inputs and quietly false on large ones.

So the size is computed from the files, committed to `size.json`, and asserted
against `README.md`'s stated table by `tests/unit/test_reference_app.py`. A
figure that goes stale silently is the failure class this repository's whole
`gen_claims.py` machinery exists for; the same discipline is applied here in
miniature, one directory wide.

## The unit, and why there is more than one

`codegraph` is described in **files**, **nodes** and **edges**, so a size in
lines alone would not be comparable to the one datapoint that exists. Four
figures are recorded and each says a different thing:

- `application_files` — Python files in `APPLICATION_SOURCES`. Directly
  comparable to U-21's file counts, which is the only reason it leads.
- `application_lines` — every line, blanks and comments included, so `wc -l`
  over those files reproduces it in one command.
- `application_code_lines` — neither blank nor a whole-line `#` comment. The
  closest cheap proxy for what an indexer walks.
- `application_definitions` — `def`, `async def` and `class` at any nesting,
  counted with `ast`. The closest cheap proxy for a symbol count.

**None of these is a `codegraph` node count**, and no arithmetic here turns one
into the other. That figure needs `codegraph` to have been run, which needs
T119, which does not exist. The gap is named rather than bridged by a ratio.

## What counts as *the application*

`APPLICATION_SOURCES` is an explicit list, not a glob, and it names three
files. The measuring script, the state, the questions and this README are the
*fixture around* the application and are excluded — a glob would fold them in
and inflate the denominator every time the fixture grew a helper. The seeded
state is reported separately as record counts, because a row is not a line and
adding them would produce a number of nothing.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
SIZE_PATH = HERE / "size.json"

#: Explicit, because a glob would silently absorb the next helper anyone adds.
APPLICATION_SOURCES = ("__init__.py", "app.py", "seed.py")


def _code_lines(text: str) -> int:
    """Lines that are neither blank nor a whole-line comment.

    A trailing comment on a code line still counts as code: stripping it would
    need a tokenizer, and the figure would then depend on a parse rather than
    on something a reader can reproduce.
    """
    count = 0
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        count += 1
    return count


def _definitions(text: str) -> int:
    tree = ast.parse(text)
    return sum(
        1
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    )


def measure() -> dict[str, Any]:
    files = 0
    lines = 0
    code_lines = 0
    definitions = 0
    for name in APPLICATION_SOURCES:
        text = (HERE / name).read_text()
        files += 1
        lines += len(text.splitlines())
        code_lines += _code_lines(text)
        definitions += _definitions(text)

    state = json.loads((HERE / "state.json").read_text())
    questions = json.loads((HERE / "questions.json").read_text())
    served = json.loads((HERE / "served_operations.json").read_text())

    return {
        "measured_by": "tests/fixtures/reference-app/size.py",
        "application_sources": list(APPLICATION_SOURCES),
        "application_files": files,
        "application_lines": lines,
        "application_code_lines": code_lines,
        "application_definitions": definitions,
        "seeded_parts": len(state["parts"]),
        "seeded_shipments": len(state["shipments"]),
        "served_operations": len(served["operations"]),
        "questions": len(questions["questions"]),
        "codegraph_nodes": None,
        "codegraph_edges": None,
        "codegraph_note": (
            "not measured. codegraph is invoked by T119, which does not exist, "
            "so no node or edge count for this application has ever been "
            "taken. U-21 records the scale claim as untested; nothing here "
            "extrapolates one figure into the other."
        ),
    }


def committed() -> dict[str, Any]:
    return json.loads(SIZE_PATH.read_text())


#: The figures the README states, in the order its table states them. Named
#: here so the README and the measurement cannot drift apart without a test
#: noticing which of the two moved.
STATED_IN_README = (
    "application_files",
    "application_lines",
    "application_code_lines",
    "application_definitions",
    "seeded_parts",
    "seeded_shipments",
    "served_operations",
    "questions",
)


def main() -> int:
    print(json.dumps(measure(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
