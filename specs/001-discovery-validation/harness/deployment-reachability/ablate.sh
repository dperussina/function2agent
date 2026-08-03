#!/usr/bin/env bash
#
# Pre-registered secondary measurement 2: disable each named mechanism of R1-tuned
# individually and re-score, in the form finding 007 section 5 used. The
# all-mechanisms-off figure is reported as the honest expectation for a framework
# nobody has tuned the analysis for.
#
# Usage: ./ablate.sh <scratch-dir> <python>

set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRATCH="${1:-/tmp/f2a-recall}"
PY="${2:-$SCRATCH/.venv-adk/bin/python}"
E="$SCRATCH/e14"
REPO="$SCRATCH/adk-python"
ENTRY="src.google.adk.cli.fast_api:get_fast_api_app"

ALL="M1_class_dispatch,M2_kwarg_flow,M3_attribute_flow,M4_membership,M5_optional_import,M6_explicit_presence,M7_class_attrs,M8_comprehension"

mkdir -p "$E/ablation"

run () {  # $1 = label, $2 = mechanism list
  "$PY" "$HERE/extract_guards.py" --src "$REPO" --entry "$ENTRY" \
        --served-key "$E/served-key-all.json" \
        --out "$E/ablation/pred-$1.json" --mechanisms "$2" >/dev/null
  "$PY" "$HERE/score.py" --static-set "$E/static-set.json" \
        --served-key "$E/served-key-all.json" \
        --r1-naive "$E/r1-naive.json" --r1-tuned "$E/ablation/pred-$1.json" \
        --probe "$E/probe-all.json" --out "$E/ablation/scores-$1.json" >/dev/null
  "$PY" - "$E/ablation/scores-$1.json" "$1" <<'PYEOF'
import json, sys
r = json.load(open(sys.argv[1]))
label = sys.argv[2]
v = r["verdict"]["R1_tuned"]
cfgs = sorted(c for c in r["configs"] if r["configs"][c].get("ok"))
tp = sum(r["configs"][c]["arms"]["R1_tuned"]["tp"] for c in cfgs)
pred = sum(r["configs"][c]["arms"]["R1_tuned"]["predicted"] for c in cfgs)
unres = sum(r["configs"][c]["arms"]["R1_tuned"]["unresolvable_guards"] for c in cfgs)
recalls = [r["configs"][c]["arms"]["R1_tuned"]["recall"] for c in cfgs]
fi = max(r["configs"][c]["null"]["R1_tuned"]["false_inclusion_rate"] for c in cfgs)
print(f"{label:26s} predicted={pred:4d} tp={tp:4d} "
      f"min_precision={v['min_precision']:.4f} min_recall={min(recalls):.4f} "
      f"unresolvable={unres:3d} max_false_incl={fi:.4f} "
      f"{'PASS' if v['clears_gate_everywhere'] else 'MISS'}")
PYEOF
}

echo "R1-tuned mechanism ablation (totals pooled over all 7 configurations)"
echo
run "none-disabled" "$ALL"
for m in M1_class_dispatch M2_kwarg_flow M3_attribute_flow M4_membership \
         M5_optional_import M6_explicit_presence M7_class_attrs M8_comprehension; do
  SUB=$(echo "$ALL" | tr ',' '\n' | grep -v "^$m$" | paste -sd, -)
  run "off-$m" "$SUB"
done
run "all-disabled" "none"
