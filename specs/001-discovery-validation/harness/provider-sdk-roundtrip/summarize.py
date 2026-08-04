"""SPIKE - E16. Fold the arm artifacts into one summary. No model spend.

Reports measured tokens. It deliberately does **not** convert them to dollars.

That is not fastidiousness — it is the finding pointing at itself. Converting
tokens to a cost requires a per-provider price table, and the per-provider cost
table is one of the nine capabilities **U-48** records as having no owner,
precisely because the removed dependency used to supply it. Hardcoding four
price lists into a harness would manufacture exactly the kind of unsourced
number this corpus refuses. Where a provider's own SDK returns a cost, that
figure is carried through as measured and labelled with its source.
"""
from __future__ import annotations

import glob
import json
import os
import sys

ARMS = ["anthropic", "openai", "google", "xai"]

CHECKS = [
    ("opaque_state_present", "provider emitted opaque reasoning state"),
    ("sdk_preserved", "vendor SDK round-tripped it without mutation"),
    ("provider_accepted", "provider accepted the re-injected state"),
    ("chained", "hop 2 ran with the id hop 1 returned"),
    ("answer_correct", "final answer correct"),
]


def load(path: str):
    try:
        raw = open(path, encoding="utf-8").read()
        return json.loads(raw[raw.index("{"):])
    except Exception:
        return None


def main() -> int:
    out_dir = sys.argv[1] if len(sys.argv) > 1 else "results"
    text_mode = "--text" in sys.argv

    arms = {}
    for name in ARMS:
        arms[name] = load(os.path.join(out_dir, f"arm-{name}.json"))
    control = load(os.path.join(out_dir, "negative-control.json"))
    counts = load(os.path.join(out_dir, "field-counts.json"))

    tok_in = sum((a or {}).get("input_tokens", 0) for a in arms.values())
    tok_out = sum((a or {}).get("output_tokens", 0) for a in arms.values())
    if control:
        tok_in += control.get("input_tokens", 0)
        tok_out += control.get("output_tokens", 0)

    measured = [n for n, a in arms.items() if a and a.get("ok")]
    environmental = [
        n for n, a in arms.items() if a and a.get("failure_kind") == "environmental"
    ]
    capability = [
        n for n, a in arms.items() if a and a.get("failure_kind") == "capability"
    ]

    roundtrip_holds = [
        n
        for n, a in arms.items()
        if a
        and a.get("opaque_state_present")
        and a.get("sdk_preserved")
        and a.get("provider_accepted")
    ]

    summary = {
        "experiment": "E16 - provider-SDK opaque-state round-trip under chained tool use",
        "arms_run": len([a for a in arms.values() if a]),
        "arms_measured": measured,
        "environmental_failures": environmental,
        "capability_failures": capability,
        "fr037_roundtrip_holds": roundtrip_holds,
        "sc010_four_providers_chained": [
            n for n, a in arms.items() if a and a.get("chained") and a.get("answer_correct")
        ],
        "negative_control": {
            "detector_fired": (control or {}).get("detector_fired"),
            "chained_without_opaque_state": (control or {}).get(
                "chained_without_opaque_state"
            ),
        },
        "tokens": {
            "input": tok_in,
            "output": tok_out,
            "total": tok_in + tok_out,
            "note": (
                "Tokens are measured from each provider's own usage field. They are NOT "
                "converted to dollars: that needs a per-provider price table, which is one "
                "of the nine capabilities U-48 records as unowned. No price is invented here."
            ),
        },
        "cost_usd_reported_by_provider": {
            "xai": (arms.get("xai") or {}).get("cost_usd_reported_by_provider"),
            "note": (
                "Only xAI reports a server-side cost (usage.cost_in_usd_ticks). The other "
                "three report tokens only. A null is 'not reported', never 'zero'."
            ),
        },
        "per_arm": {
            n: {
                k: (a or {}).get(k)
                for k in (
                    "model",
                    "sdk",
                    "sdk_version",
                    "opaque_field",
                    "ok",
                    "failure_kind",
                    "opaque_state_present",
                    "sdk_preserved",
                    "provider_accepted",
                    "chained",
                    "answer_correct",
                    "turns",
                    "input_tokens",
                    "output_tokens",
                )
            }
            for n, a in arms.items()
        },
        "vendor_field_counts": (counts or {}).get("vendor_sdks"),
    }

    if not text_mode:
        print(json.dumps(summary, indent=2))
        return 0

    w = 12
    print()
    print("E16 - opaque-state round-trip through each vendor's own SDK")
    print("=" * 72)
    hdr = "check".ljust(46) + "".join(n[:w].rjust(11) for n in ARMS)
    print(hdr)
    print("-" * 72)
    for key, label in CHECKS:
        row = label.ljust(46)
        for n in ARMS:
            v = (arms[n] or {}).get(key)
            row += {True: "yes", False: "NO", None: "n/a"}.get(v, str(v)).rjust(11)
        print(row)
    print("-" * 72)
    print("negative control".ljust(46))
    print(
        "  detector fires on a dropped field".ljust(46)
        + str((control or {}).get("detector_fired")).rjust(11)
    )
    print(
        "  chaining survives the drop anyway".ljust(46)
        + str((control or {}).get("chained_without_opaque_state")).rjust(11)
    )
    print("-" * 72)
    print(f"tokens: {tok_in} in + {tok_out} out = {tok_in + tok_out} total")
    xai_cost = (arms.get("xai") or {}).get("cost_usd_reported_by_provider")
    if xai_cost is not None:
        print(f"xai server-reported cost: ${xai_cost:.6f} (the only provider here that reports one)")
    print("no total dollar figure: the per-provider price table is unowned (U-48)")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
