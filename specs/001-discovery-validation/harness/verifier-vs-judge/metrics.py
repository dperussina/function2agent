"""SPIKE - E8 verifier-vs-judge. Delete after 2026-11-30. Do not import from product code.

Metrics, exactly as PREREGISTRATION.md 6 defines them.

Three things here are deliberate and load-bearing:

* ``unverifiable`` counts as **not-fail** (6.2 preamble). It does not detect, and it is
  counted separately as provisional.
* ``FOC_c`` is **undefined** when the judge fails open on nothing, and is returned as ``None``
  rather than as 0 or 1 (6.2). A zero there would read as "the verifier caught none of them"
  when the truth is "there were none to catch".
* Every proportion is returned with its **raw counts**, its **Wilson 95% interval**, and the
  **population its denominator is drawn from**, because 6.9 requires every report of `MD` to
  print the counts, the interval, and the family composition of the numerator in the same
  sentence — and because Amendment B3.2 shrinks that population, so a rate whose denominator
  is unlabelled is no longer interpretable. One case is 9.1 pp at this sample size.

Accuracy, PPV, NPV and F1 are **not implemented**. 6.7 makes them invalid under the stratified
positive sample unless reweighted to the corpus base rate, and states the preference plainly:
not reported. A function that does not exist cannot be called by accident.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any


#: Used when a caller builds a Proportion outside the analysis path. It is deliberately not
#: an empty string: an unlabelled population reads as "the corpus", which after Amendment
#: B3.2 is exactly the wrong default.
UNSTATED_POPULATION = "population not stated"


@dataclass
class Proportion:
    """A rate that always travels with the counts, the interval, and the population."""

    numerator: int
    denominator: int
    label: str = ""
    families: dict[str, int] = field(default_factory=dict)
    population: str = UNSTATED_POPULATION

    @property
    def value(self) -> float | None:
        return (self.numerator / self.denominator) if self.denominator else None

    @property
    def pp(self) -> float | None:
        v = self.value
        return None if v is None else v * 100.0

    def wilson(self, z: float = 1.96) -> tuple[float, float] | None:
        n = self.denominator
        if not n:
            return None
        p = self.numerator / n
        d = 1 + z * z / n
        centre = (p + z * z / (2 * n)) / d
        half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
        return max(0.0, centre - half), min(1.0, centre + half)

    def sentence(self) -> str:
        """The full form 6.9 requires — rate, counts, interval, family composition — plus the
        population B3.2 requires, because the denominator no longer means "the corpus"."""
        if self.denominator == 0:
            return f"{self.label}: undefined (denominator 0; over {self.population})"
        ci = self.wilson()
        fam = ", ".join(f"{k} {v}" for k, v in sorted(self.families.items())) or "none"
        return (f"{self.label}: {self.pp:.1f} pp ({self.numerator}/{self.denominator}; "
                f"Wilson 95% {ci[0] * 100:.1f}–{ci[1] * 100:.1f} pp; "
                f"numerator families: {fam}; over {self.population})")

    def as_dict(self) -> dict:
        ci = self.wilson()
        return {"label": self.label, "numerator": self.numerator,
                "denominator": self.denominator, "pp": self.pp,
                "wilson_95_pp": [ci[0] * 100, ci[1] * 100] if ci else None,
                "numerator_families": self.families, "population": self.population}


def _families(keys: list[tuple], family_of: dict[tuple, str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for k in keys:
        f = family_of.get(k, "?")
        out[f] = out.get(f, 0) + 1
    return out


# ------------------------------------------------------------------ AUROC

def auroc(scores: list[float], labels: list[int]) -> float | None:
    """Mann–Whitney U with mid-ranks for ties. ``labels``: 1 = oracle-positive, 0 = negative.

    Oriented so that a judge whose ``p_success`` is higher on oracle-passing traces scores
    above 0.5. Below 0.5 is the anti-correlation the constitutional gate is looking for.
    """
    pos = [s for s, y in zip(scores, labels) if y == 1]
    neg = [s for s, y in zip(scores, labels) if y == 0]
    if not pos or not neg:
        return None
    order = sorted(range(len(scores)), key=lambda i: scores[i])
    ranks = [0.0] * len(scores)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and scores[order[j + 1]] == scores[order[i]]:
            j += 1
        mid = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = mid
        i = j + 1
    rank_sum_pos = sum(r for r, y in zip(ranks, labels) if y == 1)
    u = rank_sum_pos - len(pos) * (len(pos) + 1) / 2
    return u / (len(pos) * len(neg))


def auroc_ci(scores: list[float], labels: list[int], resamples: int = 10000,
             seed: int = 20260803) -> tuple[float | None, tuple[float, float] | None]:
    """Point estimate with a stratified bootstrap 95% interval (6.1).

    The point estimate is never returned without the interval; callers get both or neither.
    """
    point = auroc(scores, labels)
    if point is None:
        return None, None
    pos_idx = [i for i, y in enumerate(labels) if y == 1]
    neg_idx = [i for i, y in enumerate(labels) if y == 0]
    rng = random.Random(seed)
    vals: list[float] = []
    for _ in range(resamples):
        p = [scores[rng.choice(pos_idx)] for _ in pos_idx]
        n = [scores[rng.choice(neg_idx)] for _ in neg_idx]
        a = auroc(p + n, [1] * len(p) + [0] * len(n))
        if a is not None:
            vals.append(a)
    if not vals:
        return point, None
    vals.sort()
    lo = vals[int(0.025 * (len(vals) - 1))]
    hi = vals[int(0.975 * (len(vals) - 1))]
    return point, (lo, hi)


# ------------------------------------------------------------------ judge metrics

def judge_metrics(neg_keys: list[tuple], pos_keys: list[tuple],
                  judge: dict[tuple, dict], family_of: dict[tuple, str],
                  confident_p: float, bootstrap: int, seed: int,
                  population: str = UNSTATED_POPULATION) -> dict[str, Any]:
    def v(k: str) -> str | None:
        return (judge.get(k) or {}).get("verdict")

    det = [k for k in neg_keys if v(k) == "fail"]
    fo = [k for k in neg_keys if v(k) == "pass"]
    cfo = [k for k in fo if ((judge.get(k) or {}).get("p_success_mean") or 0.0) >= confident_p]
    fa = [k for k in pos_keys if v(k) == "fail"]

    scored = [k for k in neg_keys + pos_keys if (judge.get(k) or {}).get("p_success_mean") is not None]
    scores = [judge[k]["p_success_mean"] for k in scored]
    labels = [1 if k in set(pos_keys) else 0 for k in scored]
    point, ci = auroc_ci(scores, labels, bootstrap, seed) if scored else (None, None)

    all_keys = neg_keys + pos_keys
    flips = [k for k in all_keys if (judge.get(k) or {}).get("flip")]
    per_rep = _per_replicate_detection(neg_keys, judge)

    return {
        "D_judge": Proportion(len(det), len(neg_keys), "D_judge",
                              _families(det, family_of), population),
        "FO_judge": Proportion(len(fo), len(neg_keys), "FO_judge",
                               _families(fo, family_of), population),
        "CFO_judge": Proportion(len(cfo), len(neg_keys), "CFO_judge",
                                _families(cfo, family_of), population),
        "FPR_judge": Proportion(len(fa), len(pos_keys), "FPR_judge",
                                _families(fa, family_of), population),
        "flip_rate": Proportion(len(flips), len(all_keys), "flip_rate",
                                _families(flips, family_of), population),
        "population": population,
        "auroc": point,
        "auroc_ci_95": list(ci) if ci else None,
        "fail_open_keys": [list(k) for k in fo],
        "per_replicate_detection": per_rep,
        "noise_floor_pp": (max(per_rep) - min(per_rep)) * 100 if len(per_rep) > 1 else 0.0,
        "unparsed_calls": sum(1 for k in all_keys
                              if (judge.get(k) or {}).get("verdict") is None),
    }


def _per_replicate_detection(neg_keys: list[tuple], judge: dict[tuple, dict]) -> list[float]:
    """Detection rate computed from each single replicate alone (5.3's noise floor)."""
    reps = max((len((judge.get(k) or {}).get("succeeded_per_repeat") or []) for k in neg_keys),
               default=0)
    out: list[float] = []
    for i in range(reps):
        vals = [(judge.get(k) or {}).get("succeeded_per_repeat") or [] for k in neg_keys]
        got = [v[i] for v in vals if len(v) > i]
        if got:
            out.append(sum(1 for s in got if s is False) / len(got))
    return out


# ------------------------------------------------------------------ verifier metrics

def verifier_metrics(arm: str, neg_keys: list[tuple], pos_keys: list[tuple],
                     verdicts: dict[tuple, dict], judge: dict[tuple, dict],
                     family_of: dict[tuple, str], all_keys: list[tuple],
                     population: str = UNSTATED_POPULATION) -> dict[str, Any]:
    def vv(k: tuple) -> str | None:
        return (verdicts.get(k) or {}).get("verdict")

    def jv(k: tuple) -> str | None:
        return (judge.get(k) or {}).get("verdict")

    det = [k for k in neg_keys if vv(k) == "fail"]
    md = [k for k in neg_keys if jv(k) == "pass" and vv(k) == "fail"]
    fo = [k for k in neg_keys if jv(k) == "pass"]
    fa = [k for k in pos_keys if vv(k) == "fail"]
    unv = [k for k in all_keys if vv(k) in ("unverifiable", "not_run", None)]

    foc = (Proportion(len(md), len(fo), f"FOC_{arm}", _families(md, family_of), population)
           if fo else None)  # undefined when FO_judge = 0 (6.2), never 0 or 1

    return {
        "arm": arm,
        "population": population,
        "D": Proportion(len(det), len(neg_keys), f"D_{arm}",
                        _families(det, family_of), population),
        "MD": Proportion(len(md), len(neg_keys), f"MD_{arm}",
                         _families(md, family_of), population),
        "FOC": foc,
        "FPR": Proportion(len(fa), len(pos_keys), f"FPR_{arm}",
                          _families(fa, family_of), population),
        "UNV": Proportion(len(unv), len(all_keys), f"UNV_{arm}",
                          _families(unv, family_of), population),
        "detected_keys": [list(k) for k in det],
        "marginal_keys": [list(k) for k in md],
    }


def admissible(vm: dict, fpr_ceiling_pp: float) -> bool:
    """`MD_c` counts only if `FPR_c <= 5 pp` (6.2). A verifier that flags everything is not one."""
    fpr = vm["FPR"].pp
    return fpr is not None and fpr <= fpr_ceiling_pp


def discounted(p: Proportion, factor: float) -> float | None:
    """Pipeline discount (6.4). The decision table reads this, never the raw figure."""
    return None if p.pp is None else p.pp * factor
