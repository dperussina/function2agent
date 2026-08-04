"""SPIKE - E17 pass-by-reference. Delete after 2026-11-30. Do not import from product code.

Calibration gate, exclusion accounting, the two limbs, and the binding decision rule.

Written before the run, so that the rule cannot be chosen after seeing which way the
numbers went. Three things here exist because this corpus produced the defect they
prevent:

* :func:`calibration_verdict` — E7's tool arm pinned at 1.00 on 27 of 41 tasks
  against a pre-registered 0.25–0.85 band, and D-19 concedes two of three task
  families support no conclusion. The band is checked *before* the main run and it
  can void it.

* :class:`Population` — a numerator over completed pairs and a denominator over
  attempts was found at eleven sites in this corpus on 2026-08-03. Every rate this
  module returns is a :class:`Rate` carrying its own denominator, and there is no
  code path that produces a bare float.

* :func:`decide` — it can return ``recommend_against``. An analysis that can only
  confirm is not an analysis. The against-branch fires on a success loss *whatever
  the token saving is*, because a cheaper agent that gets the answer wrong is not a
  cheaper agent.
"""

from __future__ import annotations

import random
import statistics
from dataclasses import dataclass, field

OK = "ok"
TERMINAL_STATUSES = ("ok", "void_calibration", "error_harness", "error_provider",
                     "refused", "budget_stop")


@dataclass(frozen=True)
class Limb:
    status: str
    total_tokens: int
    success: bool


@dataclass(frozen=True)
class Pair:
    task_id: str
    family: str
    replicate: int
    session_id: str
    inline: Limb
    handle: Limb

    @property
    def complete(self) -> bool:
        return self.inline.status == OK and self.handle.status == OK


@dataclass(frozen=True)
class Rate:
    """A rate that cannot be quoted without the population it was computed over."""
    value: float
    n: int

    def __str__(self) -> str:
        return f"{self.value:.4f} (n={self.n})"


@dataclass
class Population:
    """Attempted, analysed, excluded — reconciled, and asserted to reconcile."""
    attempted: int = 0
    analysed: int = 0
    excluded_by_reason: dict[str, int] = field(default_factory=dict)

    @property
    def excluded(self) -> int:
        return sum(self.excluded_by_reason.values())

    def reconciles(self) -> bool:
        return self.attempted == self.analysed + self.excluded


def partition(pairs: list[Pair]) -> tuple[list[Pair], Population]:
    """Split into analysable pairs and an exclusion ledger. The unit is the PAIR.

    If either limb is not ``ok`` the pair leaves, and both limbs leave with it. A
    half-pair cannot enter a paired statistic, and letting it pad a denominator is
    exactly the eleven-site defect.
    """
    pop = Population(attempted=len(pairs))
    keep: list[Pair] = []
    for p in pairs:
        if p.complete:
            keep.append(p)
        else:
            bad = p.inline.status if p.inline.status != OK else p.handle.status
            pop.excluded_by_reason[bad] = pop.excluded_by_reason.get(bad, 0) + 1
    pop.analysed = len(keep)
    assert pop.reconciles(), "population does not reconcile; refusing to report"
    return keep, pop


# --- calibration -----------------------------------------------------------

@dataclass(frozen=True)
class CalibrationVerdict:
    pooled: Rate
    fraction_pinned_at_1: Rate
    fraction_pinned_at_0: Rate
    within_band: bool
    reasons: tuple[str, ...]

    @property
    def voids_run(self) -> bool:
        return not self.within_band


def calibration_verdict(pairs: list[Pair], band: tuple[float, float],
                        max_pinned_1: float, max_pinned_0: float) -> CalibrationVerdict:
    """Pooled over BOTH treatments, per 4 of the preregistration.

    Calibrating per-arm would set the instrument using the very difference the
    instrument exists to detect.
    """
    usable, _ = partition(pairs)
    outcomes: list[bool] = []
    per_task: dict[str, list[bool]] = {}
    for p in usable:
        for limb in (p.inline, p.handle):
            outcomes.append(limb.success)
            per_task.setdefault(p.task_id, []).append(limb.success)

    n = len(outcomes)
    pooled = Rate(sum(outcomes) / n if n else 0.0, n)
    t = len(per_task)
    pin1 = sum(1 for v in per_task.values() if v and all(v))
    pin0 = sum(1 for v in per_task.values() if v and not any(v))
    f1 = Rate(pin1 / t if t else 0.0, t)
    f0 = Rate(pin0 / t if t else 0.0, t)

    reasons: list[str] = []
    if n == 0:
        reasons.append("no complete pairs in the calibration block")
    else:
        if not (band[0] <= pooled.value <= band[1]):
            reasons.append(
                f"pooled success {pooled} outside the pre-registered band "
                f"[{band[0]}, {band[1]}]")
        if f1.value > max_pinned_1:
            reasons.append(f"{pin1}/{t} tasks pinned at 1.00, above the {max_pinned_1} cap")
        if f0.value > max_pinned_0:
            reasons.append(f"{pin0}/{t} tasks pinned at 0.00, above the {max_pinned_0} cap")
    return CalibrationVerdict(pooled, f1, f0, not reasons, tuple(reasons))


# --- the two limbs ---------------------------------------------------------

def token_ratios(pairs: list[Pair]) -> list[float]:
    """handle / inline, one per complete pair. A within-pair ratio, deliberately.

    A multiplicative session-wide effect — the shape of the 2.55x swing this corpus
    measured — cancels in a within-pair ratio. An additive or task-dependent effect
    does not, which is what the drift sentinel is for.
    """
    out = []
    for p in pairs:
        if p.inline.total_tokens <= 0:
            raise ValueError(f"{p.task_id}: inline limb reports {p.inline.total_tokens} tokens")
        out.append(p.handle.total_tokens / p.inline.total_tokens)
    return out


def median_token_ratio(pairs: list[Pair]) -> Rate:
    r = token_ratios(pairs)
    return Rate(statistics.median(r) if r else float("nan"), len(r))


def success_delta_pp(pairs: list[Pair]) -> Rate:
    """(handle − inline) in percentage points, paired."""
    if not pairs:
        return Rate(float("nan"), 0)
    d = [(1 if p.handle.success else 0) - (1 if p.inline.success else 0) for p in pairs]
    return Rate(100.0 * sum(d) / len(d), len(d))


def bootstrap_ci_pp(pairs: list[Pair], resamples: int, seed: int,
                    alpha: float = 0.05) -> tuple[float, float, int]:
    """Paired bootstrap CI on the success delta, in pp. Resamples PAIRS, not limbs."""
    if not pairs:
        return (float("nan"), float("nan"), 0)
    d = [(1 if p.handle.success else 0) - (1 if p.inline.success else 0) for p in pairs]
    rng = random.Random(seed)
    n = len(d)
    stats = []
    for _ in range(resamples):
        s = sum(d[rng.randrange(n)] for _ in range(n))
        stats.append(100.0 * s / n)
    stats.sort()
    lo = stats[int((alpha / 2) * resamples)]
    hi = stats[min(resamples - 1, int((1 - alpha / 2) * resamples))]
    return (lo, hi, n)


# --- drift sentinel --------------------------------------------------------

def sentinel_flags(readings: dict[str, list[int]], tolerance: float) -> dict[str, bool]:
    """Per session: True if the fixed sentinel task's token count moved beyond tolerance.

    Pairing cancels a session-wide multiplicative effect. It does not cancel one
    that moves *during* a session, and that is the case this detects.
    """
    out = {}
    for session, vals in readings.items():
        if len(vals) < 2 or min(vals) <= 0:
            out[session] = True
            continue
        out[session] = (max(vals) - min(vals)) / min(vals) > tolerance
    return out


# --- the decision ----------------------------------------------------------

RECOMMEND = "recommend"
AGAINST = "recommend_against"
NONE = "no_recommendation"


@dataclass(frozen=True)
class Decision:
    outcome: str
    reason: str
    token_ratio: Rate
    success_delta_pp: Rate
    ci_pp: tuple[float, float, int]


def decide(pairs: list[Pair], calib: CalibrationVerdict, cfg: dict) -> Decision:
    """The rule, as written before the run. 8.4 of the preregistration is this function."""
    ratio = median_token_ratio(pairs)
    delta = success_delta_pp(pairs)
    ci = bootstrap_ci_pp(pairs, cfg["bootstrap_resamples"], cfg["bootstrap_seed"])

    if calib.voids_run:
        return Decision(NONE, "calibration band missed: " + "; ".join(calib.reasons),
                        ratio, delta, ci)
    if not pairs:
        return Decision(NONE, "no complete pairs survived exclusion", ratio, delta, ci)

    lo, hi, _ = ci
    against_point = cfg["success_recommend_against_point_pp"]
    margin = cfg["success_noninferiority_margin_pp"]

    # Limb 2 dominates limb 1. A cheaper agent that answers wrong is not cheaper.
    if hi < 0 and delta.value <= against_point:
        return Decision(
            AGAINST,
            f"task success fell {abs(delta.value):.1f} pp (CI upper bound {hi:.1f} pp < 0), "
            f"at or beyond the {abs(against_point):.0f} pp against-threshold; the token "
            f"ratio {ratio} does not license the loss",
            ratio, delta, ci)

    if ratio.value >= cfg["token_ratio_no_benefit_at_or_above"]:
        return Decision(
            AGAINST,
            f"token ratio {ratio} is at or above the {cfg['token_ratio_no_benefit_at_or_above']} "
            f"no-benefit threshold: the mechanism costs turns and complexity and buys nothing",
            ratio, delta, ci)

    if ratio.value <= cfg["token_ratio_recommend_at_or_below"] and lo >= margin:
        return Decision(
            RECOMMEND,
            f"token ratio {ratio} at or below "
            f"{cfg['token_ratio_recommend_at_or_below']}, and the success CI lower bound "
            f"{lo:.1f} pp clears the {margin:.0f} pp non-inferiority margin",
            ratio, delta, ci)

    return Decision(
        NONE,
        f"token ratio {ratio} and success CI [{lo:.1f}, {hi:.1f}] pp satisfy neither branch; "
        f"the design does not resolve this case and no rule may be chosen now",
        ratio, delta, ci)
