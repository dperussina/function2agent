"""SPIKE - E16 supplementary. Is opaque state emitted *deterministically*?

The four main arms each ran once and each found opaque state present. That is
enough to establish the round-trip works, and not enough to establish that a
conformance fixture asserting `opaque_state_present == true` would be stable.

Anthropic's newer models replace `thinking={"type":"enabled"}` with
`{"type":"adaptive"}`, under which the model decides for itself whether to
think. On a task as small as this scenario it sometimes does and sometimes does
not — so the field's *presence* is a model decision, not a configuration
guarantee.

This repeats one arm N times and reports the distribution. It exists because a
fixture built on the single-run result would be flaky, and finding out from a
flaky fixture later is more expensive than measuring it now.

Usage:  python3 repeat_adaptive.py [--model M] [--repeats N]
"""
from __future__ import annotations

import json
import subprocess
import sys
import os

DEFAULT_MODEL = "claude-sonnet-5"
DEFAULT_REPEATS = 6


def main() -> int:
    model = DEFAULT_MODEL
    repeats = DEFAULT_REPEATS
    if "--model" in sys.argv:
        model = sys.argv[sys.argv.index("--model") + 1]
    if "--repeats" in sys.argv:
        repeats = int(sys.argv[sys.argv.index("--repeats") + 1])

    here = os.path.dirname(os.path.abspath(__file__))
    runs = []
    for _ in range(repeats):
        proc = subprocess.run(
            [sys.executable, os.path.join(here, "arm_anthropic.py"), "--model", model],
            capture_output=True,
            text=True,
            cwd=here,
        )
        try:
            body = proc.stdout[proc.stdout.index("{") :]
            d = json.loads(body)
        except Exception:
            runs.append({"error": proc.stderr[-300:] or "unparseable"})
            continue
        runs.append(
            {
                "opaque_state_present": d.get("opaque_state_present"),
                "sdk_preserved": d.get("sdk_preserved"),
                "chained": d.get("chained"),
                "answer_correct": d.get("answer_correct"),
                "n_digests": len(d.get("digests_in") or []),
                "input_tokens": d.get("input_tokens", 0),
                "output_tokens": d.get("output_tokens", 0),
            }
        )

    present = sum(1 for r in runs if r.get("opaque_state_present") is True)
    absent = sum(1 for r in runs if r.get("opaque_state_present") is False)
    chained = sum(1 for r in runs if r.get("chained") is True)
    preserved_when_present = sum(
        1 for r in runs if r.get("opaque_state_present") and r.get("sdk_preserved")
    )

    out = {
        "probe": "does an adaptive-thinking model emit opaque state deterministically?",
        "model": model,
        "repeats": repeats,
        "opaque_state_present": present,
        "opaque_state_absent": absent,
        "chained": chained,
        "preserved_whenever_present": preserved_when_present,
        "deterministic": present == repeats or absent == repeats,
        "input_tokens": sum(r.get("input_tokens", 0) for r in runs),
        "output_tokens": sum(r.get("output_tokens", 0) for r in runs),
        "runs": runs,
        "reading": (
            "If `deterministic` is false, a conformance fixture that asserts opaque "
            "state is present will be flaky on this model. The fixture must assert "
            "the conditional instead: whenever the field IS present it must survive "
            "the round-trip byte-identical. `preserved_whenever_present` is that "
            "conditional, and it is the assertion worth shipping."
        ),
    }
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
