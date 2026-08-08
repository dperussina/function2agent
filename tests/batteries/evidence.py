"""Where a battery's positive control writes what it caught.

**Why not `print`.** Capture is off across this repository, and
`removal_proofs.sh` decides whether a proof's target test is runnable by
reading the verdict off the *same line* as the node id in a `pytest -v`
baseline. A test that writes to stdout while it runs splits that line: the node
id lands on one, `PASSED` on another, `baseline_py` finds a line carrying no
verdict and falls through to `SKIPPED`, and every proof aimed at that test is
then counted in the population the run did not cover rather than attempted.
That is not hypothetical — on 2026-08-08 the T115 detector proof read `SKIPPED`
for a whole harness run for exactly this, while the test it named passed when
run by hand.

So the evidence goes to a file. `results/*.latest.json` is already this
repository's name for "the record of the run that just happened, never a
committed figure", and `.gitignore` carries the pattern.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

RESULTS = Path(__file__).resolve().parent / "results"


def record_evidence(name: str, payload: dict[str, Any]) -> Path:
    """Write one battery's evidence, returning where it went."""
    RESULTS.mkdir(parents=True, exist_ok=True)
    path = RESULTS / f"{name}.latest.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n")
    return path
