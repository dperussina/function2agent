"""SPIKE - E8 verifier-vs-judge. Delete after 2026-11-30. Do not import from product code.

The scoring set: all 20 oracle-negatives plus 60 seeded, stratified oracle-positives.

PREREGISTRATION.md 9.1. **All 20 negatives are taken** — they are the entire discriminative
signal and none may be sampled away. The 60 positives are drawn by seeded RNG, stratified
proportionally by ``family`` and by ``arm``, with the seed recorded in the manifest *before*
selection. Allocation across strata uses largest-remainder so the proportions are exact and
deterministic rather than dependent on iteration order.

9.1 also permits extending the positive sample later, "but only by re-running the *same*
prompt with the *same* seed extension — never by re-selecting." :func:`select_positives`
therefore produces a **seeded ordering** of every positive and takes a prefix, so extending
the sample from 60 to 80 keeps the first 60 identical by construction rather than by
promise. Re-selection is not expressible through this interface.

**Selection runs over the eligible population, never the raw corpus** (Amendment B3.2).
:func:`select` requires the eligibility partition as an argument and refuses without one, so
"forgot to apply the rule" is not a reachable state. Excluding a record here rather than
subtracting it from a denominator later is the difference between a trace that was never
scored and a trace that was scored against the wrong question and then quietly dropped.
"""

from __future__ import annotations

import json
import random
from typing import Any

from corpus import trace_key


def _strata(rows: list[dict], keys: tuple[str, ...]) -> dict[tuple, list[dict]]:
    out: dict[tuple, list[dict]] = {}
    for r in rows:
        out.setdefault(tuple(r[k] for k in keys), []).append(r)
    return out


def _largest_remainder(sizes: dict[tuple, int], total: int) -> dict[tuple, int]:
    """Proportional allocation with exact totals, deterministic under ties."""
    pool = sum(sizes.values())
    if pool == 0:
        return {k: 0 for k in sizes}
    total = min(total, pool)
    exact = {k: total * n / pool for k, n in sizes.items()}
    alloc = {k: min(int(v), sizes[k]) for k, v in exact.items()}
    remaining = total - sum(alloc.values())
    order = sorted(
        sizes,
        key=lambda k: (-(exact[k] - int(exact[k])), -sizes[k], str(k)),
    )
    i = 0
    while remaining > 0 and i < len(order) * 4:
        k = order[i % len(order)]
        if alloc[k] < sizes[k]:
            alloc[k] += 1
            remaining -= 1
        i += 1
    return alloc


def select_positives(rows: list[dict], n: int, seed: int,
                     stratify_by: tuple[str, ...] = ("family", "arm")) -> list[dict]:
    positives = [r for r in rows if r["outcome"] == "pass"]
    strata = _strata(positives, stratify_by)
    sizes = {k: len(v) for k, v in strata.items()}
    alloc = _largest_remainder(sizes, n)

    ordered: list[dict] = []
    for k in sorted(strata, key=str):
        bucket = sorted(strata[k], key=trace_key)
        rng = random.Random(f"{seed}|{'|'.join(map(str, k))}")
        rng.shuffle(bucket)
        ordered.append({"stratum": k, "take": alloc[k], "bucket": bucket})

    chosen: list[dict] = []
    for s in ordered:
        chosen.extend(s["bucket"][: s["take"]])
    return sorted(chosen, key=trace_key)


def select(rows: list[dict], cfg: dict, partition: dict | None = None) -> dict[str, Any]:
    """Select from ``rows``, which MUST be the eligible population.

    ``partition`` is :func:`corpus.partition`'s output and is required. Making it required
    rather than optional is the point: the defect Amendment B3 records was not a wrong
    computation, it was a step nobody knew to take.
    """
    if partition is None:
        raise SystemExit(
            "select() requires the Amendment B3.2 eligibility partition.\n"
            "  Call corpus.eligible_records(rows, cfg) and pass both results.\n"
            "  Selecting from the raw corpus scores traces whose agents were asked a "
            "different question."
        )
    eligible_keys = {trace_key(r) for r in partition["eligible"]}
    intruders = [trace_key(r) for r in rows if trace_key(r) not in eligible_keys]
    if intruders:
        raise SystemExit(
            f"select() was handed {len(intruders)} record(s) the eligibility rule excluded, "
            f"e.g. {intruders[0]}. Pass corpus.eligible_records(...)[0], not the raw rows."
        )

    sc = cfg["scoring_set"]
    seed = sc["rng_seed"]
    negatives = sorted([r for r in rows if r["outcome"] == "fail"], key=trace_key)
    positives = select_positives(rows, sc["positives"], seed, tuple(sc["stratify_by"]))

    if not negatives:
        raise SystemExit(
            "no eligible oracle-negatives remain. PREREGISTRATION.md 9.1 takes all of them; "
            "with none there is no discriminative signal and nothing to score."
        )
    if len(positives) != sc["positives"]:
        raise SystemExit(
            f"stratified allocation produced {len(positives)} positives, wanted "
            f"{sc['positives']}, from an eligible pool of "
            f"{sum(1 for r in rows if r['outcome'] == 'pass')}"
        )

    comp: dict[str, int] = {}
    for r in positives:
        comp[f"{r['family']}/{r['arm']}"] = comp.get(f"{r['family']}/{r['arm']}", 0) + 1

    return {
        "seed": seed,
        "stratify_by": list(sc["stratify_by"]),
        "n_negatives": len(negatives),
        "n_positives": len(positives),
        "negatives": [list(trace_key(r)) for r in negatives],
        "positives": [list(trace_key(r)) for r in positives],
        "positive_strata": dict(sorted(comp.items())),
        "population": partition["population"],
        "eligibility_rule": partition["rule"],
        "n_excluded": len(partition["excluded"]),
        "_selection_note": (
            "Positives are a seeded prefix of a per-stratum shuffle. Extending the sample "
            "takes a longer prefix of the same ordering; the first 60 cannot change."
        ),
        "_population_note": (
            "PREREGISTRATION.md 9.1 preregistered 'all 20 oracle-negatives'. Amendment B3.2 "
            "removes the ineligible ones before selection, so n_negatives is the count of "
            "ELIGIBLE negatives. The two figures are not interchangeable and the difference "
            "is itemised in the run manifest's `eligibility` block."
        ),
    }


def main() -> int:
    import corpus
    import freeze

    cfg = freeze.load_config()
    rows, _ = corpus.load_records(cfg)
    eligible, part = corpus.eligible_records(rows, cfg)
    sel = select(eligible, cfg, part)
    print(json.dumps({k: v for k, v in sel.items()
                      if k not in ("negatives", "positives")}, indent=1))
    print(f"\nfirst 5 positives: {sel['positives'][:5]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
