"""SPIKE - E8 verifier-vs-judge. Delete after 2026-11-30. Do not import from product code.

The five negative controls of PREREGISTRATION.md 4.6. All mandatory, all free.

| Control | Expectation | Fires when violated |
|---|---|---|
| Label-shuffle | AUROC over 1000 permuted label vectors must centre on 0.500 | metric implementation bug — **void the run** |
| Constant-fail verifier | MD = 100%, FPR = 100% | the degenerate reference row |
| Constant-pass verifier | MD = 0%, FPR = 0% | the opposite anchor |
| Oracle-leak assertion | no ground truth in any scorer input, asserted per call | **abort, discard prior calls** (S2) |
| Predicted-null (c1 blindness) | c1 catches 0 numeric value errors | a leak exists — **void c1** (S3) |

Each returns a :class:`ControlResult` with ``ok`` set. A control that cannot fail is not a
control, so every one of these is exercised against planted-bad input in ``selftest.py``: the
label-shuffle control is run against a deliberately broken AUROC, the constant-verifier
anchors against a metric that ignores its verdicts, the leak assertion against a payload that
embeds the oracle record, and the predicted-null against a c1 stub that cheats.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Callable

import redact


@dataclass
class ControlResult:
    name: str
    ok: bool
    detail: str
    numbers: dict[str, Any] = field(default_factory=dict)
    fatal: bool = False
    #: False when the control had no input to run over. A control that did not run must not
    #: read as one that passed: the predicted-null control returned ``ok=True`` for an absent
    #: c1 arm, which is exactly the shape of a check that cannot fail.
    ran: bool = True

    def verdict(self) -> str:
        if not self.ran:
            return "NOT RUN"
        return "PASS" if self.ok else "FAIL"

    def line(self) -> str:
        return f"  {self.verdict():<7} {self.name:<24} {self.detail}"


# ------------------------------------------------------------------ 1. label shuffle

def label_shuffle(scores: list[float], labels: list[int], auroc_fn: Callable,
                  permutations: int = 1000, seed: int = 20260803,
                  tolerance: float = 0.05) -> ControlResult:
    """Score the judge against a permuted oracle label vector.

    ``labels``: 1 for oracle-positive, 0 for oracle-negative. Under permutation the score
    carries no information about the label, so AUROC must centre on 0.500. A mean that does
    not is a bug in the metric, not a finding about the judge, and it voids the run.
    """
    if len(scores) != len(labels) or len(set(labels)) < 2:
        return ControlResult("label-shuffle", False,
                             "cannot run: need both classes present and equal lengths",
                             fatal=True)
    rng = random.Random(seed)
    perm = list(labels)
    vals: list[float] = []
    for _ in range(permutations):
        rng.shuffle(perm)
        a = auroc_fn(scores, perm)
        if a is not None:
            vals.append(a)
    if not vals:
        return ControlResult("label-shuffle", False, "no permutation produced an AUROC",
                             fatal=True)
    mean = sum(vals) / len(vals)
    lo, hi = min(vals), max(vals)
    ok = abs(mean - 0.5) <= tolerance
    return ControlResult(
        "label-shuffle", ok,
        f"mean AUROC over {len(vals)} permutations = {mean:.4f} "
        f"(range {lo:.3f}–{hi:.3f}); must centre on 0.500 ± {tolerance}",
        {"mean": mean, "min": lo, "max": hi, "permutations": len(vals)},
        fatal=not ok,
    )


# ------------------------------------------------------------------ 2/3. constant verifiers

def constant_fail_verifier(view: dict, record: dict, *_a, **_k) -> dict:
    return {"arm": "constant-fail", "verdict": "fail", "clause": "CONTROL",
            "detail": "fails everything by construction", "provenance": "control",
            "status": "validated"}


def constant_pass_verifier(view: dict, record: dict, *_a, **_k) -> dict:
    return {"arm": "constant-pass", "verdict": "pass", "clause": "CONTROL",
            "detail": "passes everything by construction", "provenance": "control",
            "status": "validated"}


def check_constant_anchors(md_fail: float, fpr_fail: float,
                           md_pass: float, fpr_pass: float,
                           fo_judge_n: int) -> list[ControlResult]:
    """The two degenerate anchors, checked rather than merely printed.

    The constant-fail verifier's MD is `#{oracle=fail and judge=pass}` over the denominator,
    which equals the judge's fail-open rate — not necessarily 100%. Its **fail-open capture**
    is what must be 100%, and its FPR must be 100%. That distinction is why this is a checked
    control and not a printed row: an implementation that reported MD = 100% here would be
    computing something other than PREREGISTRATION.md 6.2's `MD_c`.
    """
    out = [
        ControlResult(
            "constant-fail FPR", abs(fpr_fail - 1.0) < 1e-9,
            f"FPR = {fpr_fail:.3f}; a verifier that flags everything must score 1.000, which "
            f"is why the <= 5 pp admissibility constraint is not optional",
            {"fpr": fpr_fail, "md": md_fail},
        ),
        ControlResult(
            "constant-pass MD", abs(md_pass) < 1e-9,
            f"MD = {md_pass:.3f}, FPR = {fpr_pass:.3f}; both must be 0.000",
            {"md": md_pass, "fpr": fpr_pass},
        ),
        ControlResult(
            "constant-pass FPR", abs(fpr_pass) < 1e-9,
            f"FPR = {fpr_pass:.3f}; must be 0.000", {"fpr": fpr_pass},
        ),
    ]
    if fo_judge_n > 0:
        out.append(ControlResult(
            "constant-fail MD", md_fail > 0,
            f"MD = {md_fail:.3f}; with {fo_judge_n} fail-open trace(s) the anchor must be "
            f"strictly positive, and equal to the judge's fail-open rate",
            {"md": md_fail, "fail_open_n": fo_judge_n},
        ))
    else:
        out.append(ControlResult(
            "constant-fail MD", abs(md_fail) < 1e-9,
            "MD = 0.000 because the judge failed open on nothing; S5 territory, not a bug",
            {"md": md_fail},
        ))
    return out


# ------------------------------------------------------------------ 4. oracle-leak assertion

def leak_assertion_selfcheck() -> list[ControlResult]:
    """Prove the assertion fires on a leaking payload and stays silent on a clean one.

    Run at the start of every run, not only in the self-test. An assertion that has been
    quietly disabled by a refactor must not be discovered after 480 calls have been paid for.
    """
    record = {"run_id": "r", "task_id": "T.001", "arm": "A", "attempt": 1,
              "expected": 3.201754, "reason": "expected 3.201754, got 3.23",
              "outcome": "fail", "false_success": True, "detectors": ["D1"],
              "submitted": "3.23", "submitted_status": "answered",
              "transcript": [{"role": "assistant", "content": "the reason I chose this "
                                                              "outcome was the data"}],
              "tool_calls": []}
    out: list[ControlResult] = []

    # Direction 1: the naive serialisation of the whole record must abort.
    try:
        redact.assert_no_oracle_leak({"user": record}, record, where="control")
        out.append(ControlResult("leak-assert fires (record)", False,
                                 "a payload embedding the oracle record did NOT abort",
                                 fatal=True))
    except redact.OracleLeak:
        out.append(ControlResult("leak-assert fires (record)", True,
                                 "a payload embedding the oracle record aborts"))

    # Direction 2: the expected value pasted into harness-authored text must abort.
    try:
        redact.assert_no_oracle_leak(
            {"user": "The correct answer is 3.201754."}, record, where="control")
        out.append(ControlResult("leak-assert fires (value)", False,
                                 "the expected value in harness text did NOT abort", fatal=True))
    except redact.OracleLeak:
        out.append(ControlResult("leak-assert fires (value)", True,
                                 "the expected value in harness text aborts"))

    # Direction 3: the oracle's reason string anywhere must abort, even tagged as agent text.
    try:
        redact.assert_no_oracle_leak(
            {"user": redact.AgentText("expected 3.201754, got 3.23")}, record, where="control")
        out.append(ControlResult("leak-assert fires (reason)", False,
                                 "the oracle reason string did NOT abort", fatal=True))
    except redact.OracleLeak:
        out.append(ControlResult("leak-assert fires (reason)", True,
                                 "the oracle reason string aborts wherever it appears"))

    # Direction 4: silence on a clean payload whose agent text contains the English words
    # "reason" and "outcome" and whose submitted answer is the agent's own wrong number.
    clean = {"system": "Judge whether the agent succeeded.",
             "user_parts": {"transcript": redact.AgentText(
                 "the reason I chose this outcome was the data; result 3.23"),
                 "submitted": redact.AgentText("3.23")}}
    try:
        redact.assert_no_oracle_leak(clean, record, where="control")
        out.append(ControlResult("leak-assert stays quiet", True,
                                 "a clean payload containing the English words 'reason' and "
                                 "'outcome' in agent text does not abort"))
    except redact.OracleLeak as exc:
        out.append(ControlResult("leak-assert stays quiet", False,
                                 f"false positive on a clean payload: {exc}", fatal=True))
    return out


# ------------------------------------------------------------------ 5. predicted null

def predicted_null(c1_verdicts: dict[tuple, dict], numeric_keys: list[tuple],
                   preregistered_n: int) -> ControlResult:
    """c1 must catch 0 of the numeric value errors (4.6, 7.5, S3).

    A detection means a leak: no clause of c1 compares a submitted magnitude to anything, so a
    numeric value error is not reachable by c1 without ground truth. **Void c1.**

    ``preregistered_n`` is compared against the mechanically classified count and a mismatch is
    reported. The control still runs over the *measured* subclass — silently substituting the
    preregistered count for the measured one would be an unrecorded amendment, and silently
    shrinking the subclass to match would be worse.

    **With c1 quarantined (Amendment B5) there are no c1 verdicts, so this control does not
    run.** It reports ``NOT RUN`` rather than ``PASS``. Before the quarantine it returned
    ``ok=True`` on an empty verdict map, which made "the arm was not scored" indistinguishable
    from "the arm was scored and the prediction held" — the same failure mode as a clause whose
    regex never matches.
    """
    if not c1_verdicts:
        return ControlResult(
            "predicted-null (c1)", True,
            "NOT RUN — arm (c1) is quarantined (Amendment B5) and produced no verdict, so "
            "there is nothing to test the prediction against. S3 is neither satisfied nor "
            "violated; it is undischarged.",
            {"caught": None, "n_numeric": len(numeric_keys),
             "preregistered_n": preregistered_n, "caught_keys": []},
            ran=False,
        )
    caught = [k for k in numeric_keys if (c1_verdicts.get(k) or {}).get("verdict") == "fail"]
    note = ""
    if len(numeric_keys) != preregistered_n:
        note = (f"  [preregistration says {preregistered_n} numeric value errors; the "
                f"mechanical classification counts {len(numeric_keys)} — amendment required, "
                f"the control ran over the measured set]")
    ok = not caught
    detail = (f"c1 detected {len(caught)} of {len(numeric_keys)} numeric value errors; "
              f"predicted 0.{note}")
    if caught:
        detail += (" VOID c1 — a structurally impossible detection means a ground-truth leak. "
                   f"Clauses fired: "
                   + ", ".join(sorted({(c1_verdicts[k] or {}).get('clause', '?') for k in caught})))
    return ControlResult("predicted-null (c1)", ok, detail,
                         {"caught": len(caught), "n_numeric": len(numeric_keys),
                          "preregistered_n": preregistered_n,
                          "caught_keys": [list(k) for k in caught]},
                         fatal=bool(caught))
