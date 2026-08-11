"""SPIKE - E17 pass-by-reference. Delete after 2026-11-30. Do not import from product code.

Self-test. No provider, no network, $0.00.

E19's harness shipped with 95 self-tests and its dry run found three defects in the
harness before any money was spent. That is the standard this file is written to.
Four of the defects this suite now pins were found the same way here — an inline arm
projected past the context window, a corpus size the config asserted and the
generator never produced, a negative control that carried a treatment effect, and a
traceback specimen that was silently ``None``.

The single most important group is `battery cross-check`: for every task, the shell
plan's answer and the independent Python checker's answer must agree. They share no
code. Constitution Principle I requires a derived verifier to be validated against
an artefact its own derivation did not produce, and that group is the validation.

Usage:  python3 selftest.py [-v]
"""

from __future__ import annotations

import json
import math
import os
import sys
import tempfile

import analysis
import corpus
import cost
import measure
import picklability_census as pc
import tasks
import tokens

HERE = os.path.dirname(os.path.abspath(__file__))

_PASS = 0
_FAIL: list[str] = []
_VERBOSE = "-v" in sys.argv


def check(name: str, cond: bool, detail: str = "") -> None:
    global _PASS
    if cond:
        _PASS += 1
        if _VERBOSE:
            print(f"  ok   {name}")
    else:
        _FAIL.append(f"{name}{(' — ' + detail) if detail else ''}")
        print(f"  FAIL {name}{(' — ' + detail) if detail else ''}")


def raises(name: str, fn, exc) -> None:
    try:
        fn()
    except exc:
        check(name, True)
        return
    except Exception as e:  # noqa: BLE001
        check(name, False, f"raised {type(e).__name__}, expected {exc.__name__}")
        return
    check(name, False, f"did not raise {exc.__name__}")


# ===========================================================================
# 1. token estimation
# ===========================================================================
def test_est_tokens() -> None:
    check("est_tokens(0) == 0", tokens.est_tokens(0, 4.0) == 0)
    check("est_tokens(1,4) == 1 (ceiling, nothing rounds to free)",
          tokens.est_tokens(1, 4.0) == 1)
    check("est_tokens(4,4) == 1", tokens.est_tokens(4, 4.0) == 1)
    check("est_tokens(5,4) == 2", tokens.est_tokens(5, 4.0) == 2)
    check("est_tokens(4000,4) == 1000", tokens.est_tokens(4000, 4.0) == 1000)
    check("est_tokens is monotone in bytes",
          all(tokens.est_tokens(n, 4.0) <= tokens.est_tokens(n + 1, 4.0)
              for n in range(0, 200)))
    check("est_tokens shrinks as the divisor grows",
          tokens.est_tokens(1000, 8.0) < tokens.est_tokens(1000, 4.0))
    raises("est_tokens rejects negative bytes", lambda: tokens.est_tokens(-1, 4.0), ValueError)
    raises("est_tokens rejects a zero divisor", lambda: tokens.est_tokens(10, 0.0), ValueError)
    raises("est_tokens rejects a negative divisor", lambda: tokens.est_tokens(10, -4.0), ValueError)


# ===========================================================================
# 2. cap semantics — the arm that got this wrong is the one that blew up
# ===========================================================================
def test_result_tokens() -> None:
    rt = tokens.result_tokens
    check("uncapped returns the whole payload",
          rt(40000, bytes_per_token=4.0, cap_tokens=None) == 10000)
    check("a cap truncates a payload above it",
          rt(40000, bytes_per_token=4.0, cap_tokens=400) == 400)
    check("a cap does NOT inflate a payload below it",
          rt(400, bytes_per_token=4.0, cap_tokens=400) == 100)
    check("cap exactly equal to the payload is a no-op",
          rt(1600, bytes_per_token=4.0, cap_tokens=400) == 400)
    check("cap of 0 yields 0", rt(40000, bytes_per_token=4.0, cap_tokens=0) == 0)
    check("empty payload under a cap is 0",
          rt(0, bytes_per_token=4.0, cap_tokens=400) == 0)
    check("the inline cap is larger than the handle cap in every config reading",
          8000 > 400)
    raises("a negative cap is refused",
           lambda: rt(10, bytes_per_token=4.0, cap_tokens=-1), ValueError)


# ===========================================================================
# 3. turn sequencing
# ===========================================================================
def _tm() -> tokens.TurnModel:
    return tokens.TurnModel(120, 120, 200, 150, 4096)


def test_ordered_results() -> None:
    tm = _tm()
    inline = tokens.Treatment("A-inline", 8000, 0, 1200, False)
    handle = tokens.Treatment("A-handle", 400, 1, 1320, True)
    steps = [100, 200000, 100]          # one bulk step in the middle

    oi = tokens.ordered_result_tokens(steps, tm, inline, 4.0)
    oh = tokens.ordered_result_tokens(steps, tm, handle, 4.0)
    check("inline arm adds no turns", len(oi) == 3)
    check("handle arm adds one turn per bulk step", len(oh) == 4)
    check("the extra turn lands immediately after the bulk step",
          oh[2] == tm.small_result_tokens and oh[1] == 400)
    check("inline caps the bulk step at its own cap", oi[1] == 8000)
    check("small steps are identical in both arms", oi[0] == oh[0] == 25)
    check("bulk classification uses the byte threshold, not the cap",
          tokens.is_bulk(4097, 4096) and not tokens.is_bulk(4096, 4096))
    check("two bulk steps earn two extra turns",
          len(tokens.ordered_result_tokens([200000, 200000], tm, handle, 4.0)) == 4)
    check("a task with no bulk step earns no extra turn",
          len(tokens.ordered_result_tokens([100, 100], tm, handle, 4.0)) == 2)


# ===========================================================================
# 4. accumulation — hand-computed, because the loop is the projection
# ===========================================================================
def test_project_run() -> None:
    tm = tokens.TurnModel(task_prompt_tokens=100, output_tokens_per_working_turn=100,
                          output_tokens_final_turn=200, small_result_tokens=50,
                          bulk_threshold_bytes=4096)
    tr = tokens.Treatment("t", None, 0, 1000, False)
    # One step of 400 bytes = 100 result tokens. prefix = 1100.
    #   call 1: in 1100, out 100, acc = 100 + 100 = 200
    #   call 2: in 1300, out 200   (the answer)
    #   totals: in 2400, out 300, peak 1300
    p = tokens.project_run([400], tm, tr, 4.0)
    check("project_run turn count = steps + answer", p.turns == 2)
    check("project_run input sums the accumulation (hand-computed 2400)",
          p.input_tokens == 2400, f"got {p.input_tokens}")
    check("project_run output = working turns + final (hand-computed 300)",
          p.output_tokens == 300, f"got {p.output_tokens}")
    check("project_run peak is the last call (hand-computed 1300)",
          p.peak_input_tokens == 1300, f"got {p.peak_input_tokens}")
    check("peak never exceeds the sum", p.peak_input_tokens <= p.input_tokens)

    zero = tokens.project_run([], tm, tr, 4.0)
    check("a plan with no steps still pays one answering call",
          zero.turns == 1 and zero.input_tokens == 1100 and zero.output_tokens == 200)

    big = tokens.project_run([400, 400], tm, tr, 4.0)
    check("input accumulates superlinearly in turns (a later result is paid again)",
          big.input_tokens > 2 * 2400 - 1100)
    check("more steps never reduce total input", big.input_tokens > p.input_tokens)

    price_a = p.cost_usd(3.0, 15.0)
    check("cost_usd matches the price arithmetic",
          math.isclose(price_a, 2400 * 3.0 / 1e6 + 300 * 15.0 / 1e6, rel_tol=1e-12))
    check("call_cost and cost_usd agree",
          math.isclose(price_a, tokens.call_cost(2400, 300, 3.0, 15.0), rel_tol=1e-12))


# ===========================================================================
# 5. the ledger
# ===========================================================================
def test_ledger() -> None:
    led = tokens.Ledger(ceiling_usd=1.0)
    check("a fresh ledger has spent nothing", led.spent_usd == 0.0 and led.calls == 0)
    led.check(0.5)
    check("a call inside the ceiling passes the pre-check", True)
    led.bill(100000, 1000, 3.0, 15.0)
    check("billing accumulates", led.spent_usd > 0 and led.calls == 1)
    raises("the ceiling is checked BEFORE the call, and refuses",
           lambda: led.check(10.0), tokens.BudgetExceeded)
    led2 = tokens.Ledger(ceiling_usd=0.0)
    raises("a zero ceiling refuses any positive call",
           lambda: led2.check(0.01), tokens.BudgetExceeded)
    check("BudgetExceeded is a RuntimeError",
          issubclass(tokens.BudgetExceeded, RuntimeError))


# ===========================================================================
# 6. populations and exclusion — the eleven-site defect
# ===========================================================================
def _pair(tid="T01", ok=(True, True), tok=(1000, 500), succ=(True, True),
          rep=1, sess="s1") -> analysis.Pair:
    return analysis.Pair(
        tid, "log", rep, sess,
        analysis.Limb("ok" if ok[0] else "error_provider", tok[0], succ[0]),
        analysis.Limb("ok" if ok[1] else "error_provider", tok[1], succ[1]))


def test_population() -> None:
    good = [_pair("T01"), _pair("T02")]
    bad = [_pair("T03", ok=(True, False))]
    keep, pop = analysis.partition(good + bad)
    check("a pair with a failed limb is excluded whole", len(keep) == 2)
    check("attempted counts every pair", pop.attempted == 3)
    check("analysed counts only complete pairs", pop.analysed == 2)
    check("excluded is recorded by reason",
          pop.excluded == 1 and pop.excluded_by_reason.get("error_provider") == 1)
    check("the population reconciles", pop.reconciles())
    check("a Rate cannot be printed without its denominator",
          "n=" in str(analysis.Rate(0.5, 4)))
    check("an all-excluded set analyses nothing and says so",
          analysis.partition([_pair(ok=(False, False))])[1].analysed == 0)
    check("Pair.complete requires BOTH limbs ok", not _pair(ok=(False, True)).complete)
    check("every terminal status in analysis matches the config list",
          set(analysis.TERMINAL_STATUSES) == set(_cfg()["exclusions"]["terminal_statuses"]))
    check("'ok' is a terminal status", analysis.OK in analysis.TERMINAL_STATUSES)
    check("an empty input reconciles trivially", analysis.partition([])[1].reconciles())


# ===========================================================================
# 7. calibration — the E7 defect
# ===========================================================================
def test_calibration() -> None:
    band = (0.25, 0.85)
    # every task succeeds in both arms: pooled 1.00 and every task pinned
    sat = [_pair(f"T{i:02d}", succ=(True, True)) for i in range(1, 9)]
    v = analysis.calibration_verdict(sat, band, 0.25, 0.25)
    check("a saturated set is outside the band", not v.within_band)
    check("a saturated set voids the run", v.voids_run)
    check("saturation is reported as pinning, not only as a mean",
          any("pinned at 1.00" in r for r in v.reasons))
    check("pooled success on a saturated set is 1.00", v.pooled.value == 1.0)
    check("the pooled rate carries its denominator", v.pooled.n == 16)

    floor = [_pair(f"T{i:02d}", succ=(False, False)) for i in range(1, 9)]
    v0 = analysis.calibration_verdict(floor, band, 0.25, 0.25)
    check("a floored set also voids the run", v0.voids_run)
    check("flooring is reported as pinning at 0.00",
          any("pinned at 0.00" in r for r in v0.reasons))

    mixed = ([_pair(f"A{i}", succ=(True, False)) for i in range(6)]
             + [_pair(f"B{i}", succ=(False, True)) for i in range(6)])
    vm = analysis.calibration_verdict(mixed, band, 0.25, 0.25)
    check("a 50% discriminating set sits inside the band", vm.within_band)
    check("a discriminating set does not void the run", not vm.voids_run)
    check("no reasons are recorded when the gate passes", vm.reasons == ())
    check("an empty calibration block voids the run",
          analysis.calibration_verdict([], band, 0.25, 0.25).voids_run)
    check("calibration ignores pairs it had to exclude",
          analysis.calibration_verdict(mixed + [_pair("X", ok=(False, True))],
                                       band, 0.25, 0.25).pooled.n == 24)


# ===========================================================================
# 8. the two limbs
# ===========================================================================
def test_limbs() -> None:
    pairs = [_pair("T01", tok=(1000, 400)), _pair("T02", tok=(2000, 1000))]
    r = analysis.median_token_ratio(pairs)
    check("token ratio is handle over inline", math.isclose(r.value, 0.45, rel_tol=1e-9))
    check("the ratio carries its denominator", r.n == 2)
    check("a within-pair ratio is invariant to a session-wide multiplier",
          math.isclose(
              analysis.median_token_ratio(
                  [_pair("T01", tok=(2550, 1020)), _pair("T02", tok=(5100, 2550))]).value,
              r.value, rel_tol=1e-9))
    raises("a zero-token inline limb is refused rather than divided by",
           lambda: analysis.token_ratios([_pair("T01", tok=(0, 100))]), ValueError)

    d = analysis.success_delta_pp([_pair(succ=(True, False)), _pair(succ=(True, True))])
    check("success delta is handle minus inline, in pp", math.isclose(d.value, -50.0))
    check("the delta carries its denominator", d.n == 2)
    check("an empty set yields nan rather than 0",
          math.isnan(analysis.success_delta_pp([]).value))

    lo, hi, n = analysis.bootstrap_ci_pp(
        [_pair(succ=(True, True)) for _ in range(40)], 2000, 1)
    check("a no-difference sample bootstraps to a zero-width CI at 0",
          lo == 0.0 and hi == 0.0 and n == 40)
    lo2, hi2, _ = analysis.bootstrap_ci_pp(
        [_pair(succ=(True, False)) for _ in range(40)], 2000, 1)
    check("an all-loss sample bootstraps entirely below zero", hi2 < 0)
    check("the bootstrap is seeded and reproducible",
          analysis.bootstrap_ci_pp(pairs, 500, 7) == analysis.bootstrap_ci_pp(pairs, 500, 7))


# ===========================================================================
# 9. the decision rule — every branch, including the one that says no
# ===========================================================================
def _cfg() -> dict:
    with open(os.path.join(HERE, "config.json")) as fh:
        return json.load(fh)


def test_decide() -> None:
    dc = _cfg()["decision"]
    band = (0.25, 0.85)
    good_calib = analysis.calibration_verdict(
        [_pair(f"A{i}", succ=(True, False)) for i in range(6)]
        + [_pair(f"B{i}", succ=(False, True)) for i in range(6)], band, 0.25, 0.25)
    bad_calib = analysis.calibration_verdict(
        [_pair(f"T{i}", succ=(True, True)) for i in range(8)], band, 0.25, 0.25)

    win = [_pair(f"W{i}", tok=(1000, 400), succ=(True, True)) for i in range(40)]
    d = analysis.decide(win, good_calib, dc)
    check("cheap and non-inferior recommends the change", d.outcome == analysis.RECOMMEND)
    check("the recommendation states its ratio and its margin",
          "non-inferiority margin" in d.reason)

    lose = [_pair(f"L{i}", tok=(1000, 400), succ=(True, False)) for i in range(40)]
    d2 = analysis.decide(lose, good_calib, dc)
    check("a big token saving with a big success loss recommends AGAINST",
          d2.outcome == analysis.AGAINST, d2.reason)
    check("the against-reason names the success loss, not the saving",
          "task success fell" in d2.reason)
    check("the against branch fires even at a 0.4 token ratio",
          d2.token_ratio.value < 0.5)

    flat = [_pair(f"F{i}", tok=(1000, 990), succ=(True, True)) for i in range(40)]
    d3 = analysis.decide(flat, good_calib, dc)
    check("no token benefit recommends AGAINST on cost-without-benefit",
          d3.outcome == analysis.AGAINST, d3.reason)
    check("the no-benefit reason names the threshold it crossed",
          "no-benefit threshold" in d3.reason)

    d4 = analysis.decide(win, bad_calib, dc)
    check("a missed calibration band suppresses any outcome",
          d4.outcome == analysis.NONE)
    check("the void reason names the band", "calibration band missed" in d4.reason)

    # Ratio 0.80 sits between the 0.75 recommend threshold and the 0.95 no-benefit
    # threshold, with no success movement at all: neither branch may fire.
    mid = [_pair(f"M{i}", tok=(1000, 800), succ=(True, True)) for i in range(40)]
    d5 = analysis.decide(mid, good_calib, dc)
    check("an in-between result yields no recommendation rather than a guess",
          d5.outcome == analysis.NONE, d5.reason)
    check("the in-between reason refuses to invent a rule now",
          "no rule may be chosen now" in d5.reason)
    check("an empty analysable set yields no recommendation",
          analysis.decide([], good_calib, dc).outcome == analysis.NONE)
    check("exactly three outcomes exist",
          {analysis.RECOMMEND, analysis.AGAINST, analysis.NONE} == {
              "recommend", "recommend_against", "no_recommendation"})


# ===========================================================================
# 10. drift sentinel
# ===========================================================================
def test_sentinel() -> None:
    f = analysis.sentinel_flags
    check("a steady sentinel is not flagged", f({"s1": [1000, 1050, 1010]}, 0.15)["s1"] is False)
    check("a sentinel moving 2.55x is flagged", f({"s1": [1000, 2550]}, 0.15)["s1"] is True)
    check("exactly at tolerance is not flagged", f({"s1": [1000, 1150]}, 0.15)["s1"] is False)
    check("just past tolerance is flagged", f({"s1": [1000, 1151]}, 0.15)["s1"] is True)
    check("a single reading cannot clear the check", f({"s1": [1000]}, 0.15)["s1"] is True)
    check("a zero reading is treated as broken, not as steady",
          f({"s1": [0, 1000]}, 0.15)["s1"] is True)
    check("sessions are flagged independently",
          f({"a": [1000, 1010], "b": [1000, 3000]}, 0.15) == {"a": False, "b": True})


# ===========================================================================
# 11. the corpus is reproducible, and the config pins what it produces
# ===========================================================================
_MEAS_CACHE: dict = {}


def _measured() -> tuple[dict, dict]:
    if not _MEAS_CACHE:
        man, meas = measure.build()
        _MEAS_CACHE["man"], _MEAS_CACHE["meas"] = man, meas
    return _MEAS_CACHE["man"], _MEAS_CACHE["meas"]


def test_corpus() -> None:
    cfg = _cfg()
    man, _ = _measured()
    check("the corpus total size matches the pinned config value",
          man["total_bytes"] == cfg["corpus"]["expected_total_bytes"],
          f"{man['total_bytes']} vs {cfg['corpus']['expected_total_bytes']}")
    check("the corpus file count matches the pinned config value",
          man["file_count"] == cfg["corpus"]["expected_file_count"])
    spec = corpus.CorpusSpec(cfg["corpus"]["seed"], cfg["corpus"]["expected_total_bytes"])
    tmp = os.path.join(tempfile.gettempdir(), "e17-corpus-selftest")
    m2 = corpus.generate(tmp, spec)
    check("regenerating from the same seed reproduces every file hash",
          m2["files"] == man["files"])
    m3 = corpus.generate(tmp, corpus.CorpusSpec(spec.seed + 1, spec.expected_total_bytes))
    check("a different seed produces a different tree", m3["files"] != man["files"])
    check("the manifest hashes every file", len(man["files"]) == man["file_count"])
    check("no generated answer sits on a round generator bound",
          "4000" not in {t["plan_answer"] for t in _measured()[1]["tasks"].values()})


# ===========================================================================
# 12. the battery cross-check — Principle I's validation
# ===========================================================================
def test_battery_cross_check() -> None:
    _, meas = _measured()
    for tid in sorted(meas["tasks"]):
        t = meas["tasks"][tid]
        check(f"battery cross-check {tid}: shell plan == independent checker",
              t["cross_check"] == "agree",
              f"plan={t['plan_answer']!r} checker={t['check_answer']!r}")
    check("no task produced an empty answer",
          all(t["plan_answer"] for t in meas["tasks"].values()))
    check("every plan step exited cleanly",
          all(s["returncode"] == 0 for t in meas["tasks"].values() for s in t["steps"]))
    check("no plan step wrote to stderr",
          all(s["stderr_bytes"] == 0 for t in meas["tasks"].values() for s in t["steps"]))
    check("the sentinel is not one of the battery tasks",
          tasks.SENTINEL.id not in {t.id for t in tasks.TASKS})
    check("task ids are unique", len({t.id for t in tasks.TASKS}) == len(tasks.TASKS))
    check("every task carries a prompt", all(t.prompt.strip() for t in tasks.TASKS))
    check("every task's last plan step is the answering step",
          all(t.plan[-1].label == "answer" for t in tasks.TASKS))
    raises("by_id refuses an unknown task", lambda: tasks.by_id("ZZZ"), KeyError)


# ===========================================================================
# 13. the config describes the corpus it is committed with
# ===========================================================================
def test_config_matches_measurement() -> None:
    cfg = _cfg()
    _, meas = _measured()
    a = cost.project_arm_a(cfg, meas)
    strata: dict[str, list[str]] = {}
    for tid, v in a["per_task"].items():
        strata.setdefault(v["set"], []).append(tid)
    for key in ("cap_binding", "cap_clearing", "null_control"):
        check(f"config analysis_sets.{key} matches the measured split",
              sorted(cfg["analysis_sets"][key]) == sorted(strata.get(key, [])),
              f"config={sorted(cfg['analysis_sets'][key])} measured={sorted(strata.get(key, []))}")
    check("the three strata partition the battery",
          sum(len(v) for v in strata.values()) == len(a["per_task"]))
    check("design.tasks matches the battery size", cfg["design"]["tasks"] == len(tasks.TASKS))
    check("primary + control equals the battery size",
          cfg["design"]["primary_tasks"] + cfg["design"]["null_control_tasks"]
          == cfg["design"]["tasks"])
    check("the calibration band is E7's band",
          cfg["calibration"]["pooled_success_band"] == [0.25, 0.85])
    check("a missed band voids rather than warns", cfg["calibration"]["on_miss"] == "void")
    check("the exclusion unit is the pair", cfg["exclusions"]["unit"] == "pair")
    check("the inline cap is larger than the handle cap",
          cfg["treatments"]["inline"]["cap_tokens"]
          > cfg["treatments"]["handle"]["cap_tokens"])
    check("only the handle arm keeps data reachable past its cap",
          cfg["treatments"]["handle"]["data_reachable_after_cap"]
          and not cfg["treatments"]["inline"]["data_reachable_after_cap"])
    check("the handle arm carries the larger static prefix, and pays for it",
          cfg["treatments"]["handle"]["static_prefix_tokens"]
          > cfg["treatments"]["inline"]["static_prefix_tokens"])
    check("the primary cap appears in the sensitivity list",
          cfg["treatments"]["inline"]["cap_tokens"] in cfg["cost"]["cap_sensitivity"])
    check("credentials are inventoried by name only, and no value looks like a key",
          all(len(n) < 40 and n.isupper() for n in cfg["credentials"]["known_working_names"]))
    check("the credential the harness needs is one finding 002 found working",
          set(cfg["credentials"]["required_names"])
          <= set(cfg["credentials"]["known_working_names"]))
    check("the dead Gemini name is not in the working list",
          set(cfg["credentials"]["known_dead_names"]).isdisjoint(
              cfg["credentials"]["known_working_names"]))


# ===========================================================================
# 14. the projection itself
# ===========================================================================
def test_projection() -> None:
    cfg = _cfg()
    _, meas = _measured()
    a = cost.project_arm_a(cfg, meas)
    b = cost.project_arm_b(cfg)

    check("no projected run exceeds the context window", a["over_context_window"] == [],
          str(a["over_context_window"]))
    for tid in cfg["analysis_sets"]["null_control"]:
        v = a["per_task"][tid]
        lo, hi = cfg["analysis_sets"]["null_control_expected_ratio_band"]
        check(f"null control {tid} projects a ratio in [{lo}, {hi}] — the treatment is inert",
              lo <= v["projected_token_ratio"] <= hi,
              f"got {v['projected_token_ratio']:.3f}")
        check(f"null control {tid} loses nothing to the inline cap",
              v["inline_tokens_lost_to_cap"] == 0)
    for tid in cfg["analysis_sets"]["cap_binding"]:
        check(f"cap-binding task {tid} loses bytes the inline arm cannot recover",
              a["per_task"][tid]["inline_tokens_lost_to_cap"] > 0)
    for tid in cfg["analysis_sets"]["cap_clearing"]:
        check(f"cap-clearing task {tid} loses nothing to the inline cap",
              a["per_task"][tid]["inline_tokens_lost_to_cap"] == 0)

    check("the projected total sits under the configured hard ceiling",
          a["total_usd"] < a["hard_ceiling_usd"],
          f"${a['total_usd']:.2f} vs ${a['hard_ceiling_usd']:.2f}")
    check("the hard ceiling sits under the budget", a["hard_ceiling_usd"] < a["budget_usd"])
    check("irreducible plus margin equals the total",
          math.isclose(a["irreducible_usd"] + a["margin_usd"], a["total_usd"], rel_tol=1e-9))
    check("the irreducible minimum is the larger half of the projection",
          a["irreducible_usd"] > a["margin_usd"])
    check("stage 2 costs twice stage 1 at three replicates",
          math.isclose(a["stage2_usd"], 2 * a["stage1_usd"], rel_tol=1e-9))
    check("the sentinel is cheap relative to a battery pass",
          a["sentinels_usd"] < 0.1 * a["stage1_usd"])
    check("every task's pair cost is positive",
          all(v["pair_usd"] > 0 for v in a["per_task"].values()))
    check("the battery pair cost is the sum of its tasks",
          math.isclose(a["battery_pair_usd"],
                       sum(v["pair_usd"] for v in a["per_task"].values()), rel_tol=1e-9))

    sens = a["cap_sensitivity"]
    caps = sorted(int(k) for k in sens)
    check("cap sensitivity covers every configured cap",
          caps == sorted(cfg["cost"]["cap_sensitivity"]))
    check("a lower inline cap makes the measured saving smaller — monotone",
          all(sens[str(caps[i])]["median_projected_ratio"]
              > sens[str(caps[i + 1])]["median_projected_ratio"]
              for i in range(len(caps) - 1)))
    check("at the tightest cap the projected benefit nearly vanishes",
          sens[str(caps[0])]["median_projected_ratio"] > 0.9)
    check("at the loosest cap the projected benefit is large",
          sens[str(caps[-1])]["median_projected_ratio"] < 0.25)
    check("the decision rule would flip between the tightest and loosest cap",
          sens[str(caps[0])]["median_projected_ratio"]
          >= cfg["decision"]["token_ratio_no_benefit_at_or_above"]
          and sens[str(caps[-1])]["median_projected_ratio"]
          <= cfg["decision"]["token_ratio_recommend_at_or_below"])
    check("every sensitivity point still fits the context window",
          all(s["fits_context_window"] for s in sens.values()))

    check("arm B is projected so it can be declined with a number",
          b["total_usd"] > 0)
    check("arm B's sandbox limb costs more than its in-process limb, as the confound implies",
          b["sandbox"]["usd"] > b["inprocess"]["usd"])
    check("arm B carries its own ceiling, separate from arm A's",
          b["hard_ceiling_usd"] != a["hard_ceiling_usd"])
    check("arm B's projection sits under arm B's ceiling",
          b["total_usd"] < b["hard_ceiling_usd"])
    check("arm B is marked not-recommended in the config it is projected from",
          "not recommended" in b["status"])
    check("the two arms are never summed into one headline",
          "total_usd" not in {k for k in a if k.startswith("combined")})


# ===========================================================================
# 15. arm B' — the picklability census
# ===========================================================================
def test_census() -> None:
    c = pc.census()
    check("the census is marked dry-run and zero-spend",
          c["dry_run"] is True and c["model_calls"] == 0 and c["spend_usd"] == 0.0)
    check("the predicate is named in the output", "pickle.dumps" in c["predicate"])
    check("every specimen is classified", len(c["rows"]) == c["n_shapes"])
    check("crossing plus blocked equals the census",
          c["n_cross"] + c["n_blocked"] == c["n_shapes"])
    check("the census is large enough to say something", c["n_shapes"] >= 40)
    check("every plain-data shape crosses the boundary",
          c["by_category"]["plain data"]["crosses"] == c["by_category"]["plain data"]["n"])
    check("no locally defined type crosses",
          c["by_category"]["locally defined"]["crosses"] == 0)
    check("an open file object does not cross",
          not next(r for r in c["rows"] if r["shape"] == "open file object")["crosses"])
    check("a socket does not cross",
          not next(r for r in c["rows"] if r["shape"] == "socket")["crosses"])
    check("a database connection does not cross",
          not next(r for r in c["rows"] if r["shape"] == "sqlite3 connection")["crosses"])
    check("a generator does not cross",
          not next(r for r in c["rows"] if r["shape"] == "generator")["crosses"])
    check("a lambda does not cross",
          not next(r for r in c["rows"] if r["shape"] == "lambda")["crosses"])
    check("a module-level function does cross",
          next(r for r in c["rows"] if r["shape"] == "module-level function")["crosses"])
    check("the traceback specimen is a real traceback, not None",
          not next(r for r in c["rows"] if r["shape"] == "traceback")["crosses"])
    check("is_picklable agrees with pickle on a known-good value", pc.is_picklable({"a": 1}))
    check("is_picklable agrees with pickle on a known-bad value",
          not pc.is_picklable(lambda: None))
    check("is_picklable swallows every exception type, as NOOA's does",
          pc.is_picklable(pc.Ordinary(1)))


def main() -> int:
    groups = [
        ("token estimation", test_est_tokens),
        ("cap semantics", test_result_tokens),
        ("turn sequencing", test_ordered_results),
        ("accumulation", test_project_run),
        ("ledger", test_ledger),
        ("populations and exclusion", test_population),
        ("calibration gate", test_calibration),
        ("the two limbs", test_limbs),
        ("the decision rule", test_decide),
        ("drift sentinel", test_sentinel),
        ("corpus reproducibility", test_corpus),
        ("battery cross-check", test_battery_cross_check),
        ("config vs measurement", test_config_matches_measurement),
        ("the projection", test_projection),
        ("arm B' picklability census", test_census),
    ]
    for name, fn in groups:
        print(f"[{name}]")
        fn()
    print()
    total = _PASS + len(_FAIL)
    print(f"{_PASS}/{total} self-tests passed; no model was called; spend $0.00")
    if _FAIL:
        print(f"{len(_FAIL)} FAILED:")
        for f in _FAIL:
            print(f"  - {f}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
