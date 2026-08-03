"""SPIKE - E8 verifier-vs-judge. Delete after 2026-11-30. Do not import from product code.

Analysis: the metrics, the five controls, and the binding assertions.

Everything PREREGISTRATION.md declares as a check on the experiment's own honesty is executed
here as code, not left as a note for a human to remember:

* **S3 / the predicted-null control** — if c1 detects any numeric value error, c1 is voided
  automatically and the report says so at the top.
* **The label-shuffle control** — an AUROC that does not centre on 0.500 under permutation
  voids the run.
* **The constant-fail / constant-pass anchors** — checked, not merely printed.
* **The `MD` upper bound identity** — the retired arm (d) is printed once, under its true name,
  with the identity next to it, and is structurally unable to reach the decision table because
  the gate reads only `MD_best` over the admissible derived arms.
* **The pipeline discount** — the decision table reads `MD_c2 × 0.7681`. The raw figure is
  printed beside it and is never the input to a gate.
* **The three denominators** — all reported; the gate reads N; divergence is called out.
* **Near-miss sensitivity** — every verifier metric with and without the sub-1% near-misses,
  and a tolerance-dependent downgrade if the verdict changes between them.
* **The advisory rider (6.9)** — printed on the gate verdict unconditionally, because the
  false-success base is n = 11 across 6 tasks with 8 in one family.
* **The eligibility ledger (Amendment B3.2)** — printed *above* every metric, itemising which
  records were excluded and why. Every denominator carries the population it is over, and
  each is shown against the size 6.3 preregistered, because those figures were counted before
  the eligibility rule existed and no longer describe the same set.
"""

from __future__ import annotations

import json
import math
from typing import Any

import controls
import corpus
import metrics


def _by_key(rows: list[dict]) -> dict[tuple, dict]:
    return {(r["run_id"], r["task_id"], r["arm"], r["attempt"]): r for r in rows}


def analyse(cfg: dict, records: list[dict], selection: dict,
            judge_by_arm: dict[str, dict[tuple, dict]],
            verifier_by_arm: dict[str, dict[tuple, dict]],
            partition: dict | None = None) -> dict[str, Any]:
    """``records`` is the ELIGIBLE population; ``partition`` is the ledger that defines it.

    ``partition`` is required in practice — a report that shows metrics without showing what
    was excluded from them is the thing Amendment B3.2 exists to prevent — and its absence is
    recorded as fatal rather than defaulted away.
    """
    gate = cfg["gate"]
    rec = _by_key(records)
    family_of = {k: r["family"] for k, r in rec.items()}
    population = (partition or {}).get("population", metrics.UNSTATED_POPULATION)

    neg_keys = [tuple(x) for x in selection["negatives"]]
    pos_keys = [tuple(x) for x in selection["positives"]]
    all_keys = neg_keys + pos_keys

    dens = corpus.denominators([rec[k] for k in neg_keys])
    numeric_keys = corpus.numeric_value_error_keys([rec[k] for k in neg_keys])
    near_keys = set(corpus.near_miss_keys([rec[k] for k in neg_keys]))
    tax = corpus.taxonomy(records)
    tax_disc = corpus.taxonomy_discrepancies(tax)

    out: dict[str, Any] = {
        "eligibility": _serialise_eligibility(partition),
        "taxonomy": tax,
        "taxonomy_discrepancies": tax_disc,
        "denominator_sizes": {k: len(v) for k, v in dens.items()},
        "denominator_populations": corpus.denominator_populations(dens, population, cfg),
        "controls": [],
        "fatal": [],
        "judge": {},
        "verifiers": {},
        "decision": {},
    }
    if partition is None:
        out["fatal"].append(
            "the Amendment B3.2 eligibility ledger was not supplied to analyse(); every "
            "denominator below is over an unstated population and none of them is reportable"
        )
    else:
        for alarm in partition["integrity_alarms"]:
            out["fatal"].append(
                f"eligibility integrity alarm — {alarm}. A record disagrees with the battery "
                "its own run declares, so the battery did not change: the fixture drifted or "
                "expected.json was edited."
            )

    # ---- controls that do not need a judge verdict -----------------------------------
    for cr in controls.leak_assertion_selfcheck():
        out["controls"].append(vars(cr))
        if not cr.ok:
            out["fatal"].append(f"{cr.name}: {cr.detail}")

    # ---- judge arms -------------------------------------------------------------------
    for arm_key, judge in judge_by_arm.items():
        jm = metrics.judge_metrics(neg_keys, pos_keys, judge, family_of,
                                   gate["confident_fail_open_p"],
                                   gate["auroc_bootstrap_resamples"],
                                   cfg["scoring_set"]["rng_seed"], population)
        scored = [k for k in all_keys if (judge.get(k) or {}).get("p_success_mean") is not None]
        if scored:
            cr = controls.label_shuffle(
                [judge[k]["p_success_mean"] for k in scored],
                [1 if k in set(pos_keys) else 0 for k in scored],
                metrics.auroc, gate["label_shuffle_permutations"],
                cfg["scoring_set"]["rng_seed"],
            )
            cr.name = f"label-shuffle ({arm_key})"
            out["controls"].append(vars(cr))
            if not cr.ok:
                out["fatal"].append(f"{cr.name}: {cr.detail} — VOID THE RUN")
        out["judge"][arm_key] = _serialise_judge(jm)

    primary = judge_by_arm.get("b", {})

    # ---- retired arm (d): the identity, printed under its true name -------------------
    fo = [k for k in neg_keys if (primary.get(k) or {}).get("verdict") == "pass"]
    out["md_upper_bound"] = {
        "label": "MD upper bound == judge fail-open rate",
        "value_pp": (len(fo) / len(neg_keys) * 100) if neg_keys else None,
        "counts": f"{len(fo)}/{len(neg_keys)}",
        "identity": ("MD(oracle-as-verifier) = |{oracle=fail and judge=pass and oracle=fail}| "
                     "/ |{oracle=fail}| = |{oracle=fail and judge=pass}| / |{oracle=fail}| "
                     "= FO_judge, exactly"),
        "binding_note": ("PREREGISTRATION.md 3.3(1): this is a statement about the JUDGE. It "
                         "MUST NOT appear in any sentence whose subject is the verifier, and "
                         "it does not feed the decision table."),
    }

    # ---- verifier arms, incl. the two constant anchors --------------------------------
    anchors = {
        "constant-fail": {k: controls.constant_fail_verifier(None, rec[k]) for k in all_keys},
        "constant-pass": {k: controls.constant_pass_verifier(None, rec[k]) for k in all_keys},
    }
    for arm_key, verdicts in {**verifier_by_arm, **anchors}.items():
        entry: dict[str, Any] = {}
        for den_name, den_keys in dens.items():
            vm = metrics.verifier_metrics(arm_key, den_keys, pos_keys, verdicts, primary,
                                          family_of, all_keys, population)
            entry[den_name] = _serialise_verifier(vm, gate, arm_key)
        # near-miss sensitivity (6.5), on the primary denominator
        excl = [k for k in dens["N"] if k not in near_keys]
        vm_excl = metrics.verifier_metrics(arm_key, excl, pos_keys, verdicts, primary,
                                           family_of, all_keys, population)
        entry["N_excl_near_miss"] = _serialise_verifier(vm_excl, gate, arm_key)
        out["verifiers"][arm_key] = entry

    anchor_vm_fail = metrics.verifier_metrics("constant-fail", dens["N"], pos_keys,
                                              anchors["constant-fail"], primary, family_of,
                                              all_keys, population)
    anchor_vm_pass = metrics.verifier_metrics("constant-pass", dens["N"], pos_keys,
                                              anchors["constant-pass"], primary, family_of,
                                              all_keys, population)
    for cr in controls.check_constant_anchors(
        anchor_vm_fail["MD"].value or 0.0, anchor_vm_fail["FPR"].value or 0.0,
        anchor_vm_pass["MD"].value or 0.0, anchor_vm_pass["FPR"].value or 0.0, len(fo),
    ):
        out["controls"].append(vars(cr))
        if not cr.ok:
            out["fatal"].append(f"{cr.name}: {cr.detail}")

    # ---- predicted-null: S3, asserted, not noted --------------------------------------
    pn = controls.predicted_null(verifier_by_arm.get("c1", {}), numeric_keys,
                                 cfg["predicted_null"]["preregistered_n"])
    out["controls"].append(vars(pn))
    if not pn.ok:
        out["fatal"].append(f"S3 — {pn.detail}")
        out["c1_void"] = True

    # ---- the gate ---------------------------------------------------------------------
    out["decision"] = _decide(cfg, out, primary, neg_keys, population)
    return out


def _serialise_eligibility(partition: dict | None) -> dict:
    """The B3.2 ledger, minus the record objects, so it can live in analysis.json."""
    if partition is None:
        return {"applied": False,
                "_note": "analyse() was called without the eligibility partition"}
    return {
        "applied": True,
        "rule": partition["rule"],
        "battery_version": partition["battery_version"],
        "on_unattested": partition["on_unattested"],
        "population": partition["population"],
        "by_status": partition["by_status"],
        "ledger": partition["ledger"],
        "family_cost": partition.get("family_cost"),
        "integrity_alarms": partition["integrity_alarms"],
    }


def _serialise_judge(jm: dict) -> dict:
    d = {}
    for k, v in jm.items():
        d[k] = v.as_dict() if isinstance(v, metrics.Proportion) else v
    d["_sentences"] = [v.sentence() for v in jm.values() if isinstance(v, metrics.Proportion)]
    return d


def _serialise_verifier(vm: dict, gate: dict, arm_key: str) -> dict:
    adm = metrics.admissible(vm, gate["fpr_ceiling_pp"])
    disc_applies = arm_key in gate["discount_applies_to"]
    md_disc = (metrics.discounted(vm["MD"], gate["pipeline_discount"])
               if disc_applies else vm["MD"].pp)
    foc_disc = (metrics.discounted(vm["FOC"], gate["pipeline_discount"])
                if disc_applies and vm["FOC"] else (vm["FOC"].pp if vm["FOC"] else None))
    return {
        "D": vm["D"].as_dict(), "MD_raw": vm["MD"].as_dict(),
        "MD_gate_pp": md_disc,
        "MD_discount_applied": gate["pipeline_discount"] if disc_applies else None,
        "FOC_raw": vm["FOC"].as_dict() if vm["FOC"] else None,
        "FOC_gate_pct": foc_disc,
        "FPR": vm["FPR"].as_dict(), "UNV": vm["UNV"].as_dict(),
        "admissible": adm,
        "detected_keys": vm["detected_keys"], "marginal_keys": vm["marginal_keys"],
        "_sentences": [vm["D"].sentence(), vm["MD"].sentence(), vm["FPR"].sentence(),
                       vm["UNV"].sentence()] + ([vm["FOC"].sentence()] if vm["FOC"] else
                                                ["FOC: undefined — the judge failed open on nothing"]),
    }


def _decide(cfg: dict, out: dict, primary: dict, neg_keys: list[tuple],
            population: str = "") -> dict:
    gate = cfg["gate"]
    rows: list[str] = []

    candidates = {}
    for arm in ("c1", "c2"):
        v = (out["verifiers"].get(arm) or {}).get("N")
        if v and v["admissible"] and not out.get("c1_void" if arm == "c1" else "", False):
            candidates[arm] = v["MD_gate_pp"]
    md_best = max(candidates.values(), default=None) if candidates else None
    md_best_arm = max(candidates, key=candidates.get) if candidates else None

    jb = out["judge"].get("b") or {}
    auroc = jb.get("auroc")
    ci = jb.get("auroc_ci_95")
    flip = (jb.get("flip_rate") or {}).get("pp")
    floor = jb.get("noise_floor_pp")

    if md_best is None:
        rows.append("No verifier arm satisfies FPR <= 5 pp (or none ran). "
                    "H2 falsified on this corpus — same action as < 10 pp: contract-derived "
                    "verification is a CI detail, not a headline differentiator.")
    elif md_best >= gate["md_threshold_pp"]:
        foc = (out["verifiers"][md_best_arm]["N"]["FOC_gate_pct"])
        fpr = out["verifiers"][md_best_arm]["N"]["FPR"]["pp"]
        if foc is not None and foc >= gate["foc_threshold_pct"] and fpr <= gate["fpr_ceiling_pp"]:
            rows.append(f"MD_best (discounted) = {md_best:.1f} pp on arm {md_best_arm}, "
                        f"FOC = {foc:.1f}%, FPR = {fpr:.1f} pp: verifier is a headline feature "
                        "— SUBJECT TO 6.9's advisory rider below.")
        else:
            rows.append(f"MD_best (discounted) = {md_best:.1f} pp clears 10 pp but FOC/FPR do "
                        "not both hold; the headline row does not fire.")
    else:
        rows.append(f"MD_best (discounted) = {md_best:.1f} pp < 10 pp. H2 false on this corpus. "
                    "Per 6.9 a null at this sample size triggers E9 rather than an immediate "
                    "product-narrative rewrite.")

    if ci:
        if ci[1] < 0.5:
            rows.append(f"AUROC_judge upper 95% bound {ci[1]:.3f} < 0.5: replicates the "
                        "published anti-correlation on a code/API domain. No LLM judge "
                        "anywhere in the product's success path. Encode in the constitution.")
        elif ci[0] > 0.7:
            rows.append(f"AUROC_judge lower 95% bound {ci[0]:.3f} > 0.7: surprising and "
                        "important. Investigate why this domain differs. Do not relax the "
                        "evaluation design on one result.")
        elif ci[0] <= 0.5 <= ci[1]:
            rows.append(f"AUROC_judge 95% CI [{ci[0]:.3f}, {ci[1]:.3f}] contains 0.5: no "
                        "transfer claim in either direction. Principle I's default stands on "
                        "the inherited evidence, now labelled 'not replicated locally'.")
        else:
            rows.append(f"AUROC_judge 95% CI [{ci[0]:.3f}, {ci[1]:.3f}]: no decision-table row "
                        "fires.")
    if flip is not None and flip > gate["flip_rate_ban_pct"]:
        rows.append(f"flip_rate {flip:.1f}% > 30%: no stable judge verdict exists. "
                    "Independently sufficient for the ban row (S4).")
    if floor is not None and floor > cfg["stop_conditions"]["S8_noise_floor_pp"]:
        rows.append(f"S8 — judge noise floor {floor:.1f} pp > 5 pp: the 10 pp gate is reported "
                    "as NOT MEASURABLE at this set size, rather than as fired or not fired.")

    for arm in ("c1", "c2"):
        v = (out["verifiers"].get(arm) or {}).get("N")
        if v and (v["UNV"]["pp"] or 0) > 50:
            rows.append(f"UNV_{arm} = {v['UNV']['pp']:.1f}% > 50%: arm {arm} may not be "
                        "described as covering the corpus, whatever its MD (6.6).")

    for arm in ("c1", "c2"):
        e = out["verifiers"].get(arm) or {}
        a, b = e.get("N"), e.get("N_excl_near_miss")
        if a and b and a["MD_gate_pp"] is not None and b["MD_gate_pp"] is not None:
            if (a["MD_gate_pp"] >= gate["md_threshold_pp"]) != \
               (b["MD_gate_pp"] >= gate["md_threshold_pp"]):
                rows.append(f"TOLERANCE-DEPENDENT ({arm}): the gate verdict changes when the "
                            "sub-1% near-misses are excluded. Per 6.5 the verifier claim is "
                            "downgraded to provisional regardless of which side of 10 pp it "
                            "lands on.")

    # 6.9's rider is computed from the population that actually ran, not quoted from the
    # preregistration. B3.2 moved every one of these numbers, and a rider that still says
    # "2 traces out of 20" after the denominator fell to 15 is a rider that misleads.
    tax = out["taxonomy"]
    n_fs = tax["classes"].get(corpus.CLASS_FALSE_SUCCESS, 0)
    n_fs_tasks = tax.get("false_success_tasks", 0)
    fam = tax.get("false_success_families") or {}
    biggest = max(fam.items(), key=lambda kv: kv[1], default=(None, 0))
    n_N = out["denominator_sizes"].get("N", 0)
    gate_at = math.ceil(gate["md_threshold_pp"] / 100 * n_N) if n_N else None
    per_case_fs = (100.0 / n_fs) if n_fs else None

    return {
        "MD_best_discounted_pp": md_best,
        "MD_best_arm": md_best_arm,
        "rows": rows,
        "population": population,
        "advisory_rider": (
            "UNDERPOWERED — ADVISORY. The gate's verdict is advisory-only until the "
            "false-success base reaches n >= 30 across >= 3 families (6.9, 9.3). Measured on "
            f"the population actually scored — {population} — that base is {n_fs} false "
            f"success(es) across {n_fs_tasks} task(s)"
            + (f", {biggest[1]} of them in family {biggest[0]}" if biggest[0] else "")
            + (f"; one case is {per_case_fs:.1f} pp on N_fs" if per_case_fs else "")
            + (f" and the gate fires at {gate_at} trace(s) out of {n_N} on N" if gate_at else "")
            + ". A positive result licenses only 'consistent with H2, underpowered'; it does "
              "not license 'H2 confirmed'."
        ),
        "prevalence_warning": (
            "Positives are stratified-sampled, so the scoring set's base rate is not the "
            "population base rate. AUROC is prevalence-invariant and unbiased here. Accuracy, "
            "PPV, NPV and F1 are not computed at all (6.7)."
        ),
    }


def format_report(out: dict) -> str:
    L: list[str] = ["# E8 verifier-vs-judge — results", ""]
    if (out.get("spend") or {}).get("dry_run"):
        L += ["> ## DRY RUN — NOT RESULTS", ">",
              "> No model was called. Every judge verdict below comes from `judge.StubJudge`, a "
              "deterministic hash of the trace key. The judge metrics, the AUROC, the fail-open "
              "rate and every decision-table row derived from them are **meaningless as "
              "findings** and exist only to prove the pipeline runs end to end.",
              ">",
              "> The verifier arms, the taxonomy, the denominators, the controls and the cost "
              "projection are computed from the frozen corpus and are real.", ""]
    if out["fatal"]:
        L += ["## RUN IS VOID", ""]
        L += [f"- {f}" for f in out["fatal"]]
        L += ["", "Nothing below is interpretable until these are resolved.", ""]

    L += _eligibility_section(out)

    if out["taxonomy_discrepancies"]:
        L += ["## Amendment required — the measured taxonomy disagrees with PREREGISTRATION.md 2.1",
              ""]
        L += [f"- {d}" for d in out["taxonomy_discrepancies"]]
        L += ["", "The counts above are mechanical, read off the oracle's own recorded reason "
                  "strings. They are reported rather than reconciled: editing either side to "
                  "agree would defeat the point of pre-registering the split.", ""]

    L += ["## Controls", ""]
    for c in out["controls"]:
        # A control that did not run is reported as NOT RUN, never as PASS. `ran` is absent
        # from any analysis.json written before Amendment B5, so it defaults to True.
        state = "PASS" if c["ok"] else "FAIL"
        if not c.get("ran", True):
            state = "NOT RUN"
        L.append(f"- {state}  **{c['name']}** — {c['detail']}")
    L.append("")

    L += ["## Retired arm (d)", "",
          f"- **{out['md_upper_bound']['label']}** = "
          f"{_fmt(out['md_upper_bound']['value_pp'])} pp ({out['md_upper_bound']['counts']})",
          f"  - `{out['md_upper_bound']['identity']}`",
          f"  - {out['md_upper_bound']['binding_note']}", ""]

    for arm, jm in out["judge"].items():
        L += [f"## Judge arm ({arm})", ""]
        for s in jm["_sentences"]:
            L.append(f"- {s}")
        ci = jm.get("auroc_ci_95")
        L.append(f"- AUROC = {_fmt(jm.get('auroc'), 3)}"
                 + (f", 95% CI [{ci[0]:.3f}, {ci[1]:.3f}]" if ci else " (interval unavailable)"))
        L.append(f"- judge noise floor = {_fmt(jm.get('noise_floor_pp'))} pp "
                 f"(per-replicate detection {jm.get('per_replicate_detection')})")
        L.append(f"- unparsed verdicts = {jm.get('unparsed_calls')}")
        L.append("")

    L += ["## Verifier arms", ""]
    for arm, dens in out["verifiers"].items():
        L.append(f"### {arm}")
        for den, v in dens.items():
            L.append(f"- **{den}** — MD gate figure {_fmt(v['MD_gate_pp'])} pp"
                     + (f" (raw {_fmt(v['MD_raw']['pp'])} pp × {v['MD_discount_applied']})"
                        if v["MD_discount_applied"] else "")
                     + f", admissible={v['admissible']}")
            for s in v["_sentences"]:
                L.append(f"  - {s}")
        L.append("")

    d = out["decision"]
    L += ["## Decision table", ""]
    for r in d["rows"]:
        L.append(f"- {r}")
    L += ["", f"> {d['advisory_rider']}", "", f"> {d['prevalence_warning']}", ""]
    return "\n".join(L)


def _eligibility_section(out: dict) -> list[str]:
    """The exclusion, above the metrics rather than implied by them.

    A reader who sees ``MD_c2 = 20.0 pp (3/15)`` and no eligibility block has been shown a
    denominator that silently shrank from 20, which is exactly the reporting failure
    Amendment B3.2 was written to stop.
    """
    e = out.get("eligibility") or {}
    L = ["## Eligibility — Amendment B3.2", ""]
    if not e.get("applied"):
        return L + ["- **NOT APPLIED.** Every denominator below is over an unstated "
                    "population and none of them is reportable.", ""]
    led = e["ledger"]
    L += [f"- Rule: {e['rule']}",
          f"- Battery under test: `{e['battery_version']}`",
          f"- Population: **{e['population']}**",
          f"- Policy on unattested records: `{e['on_unattested']}`", ""]
    L += ["| Status | n | negatives | positives | false successes |", "|---|---|---|---|---|"]
    for status, v in led.items():
        if status.startswith("_"):
            continue
        L.append(f"| `{status}` | {v['n']} | {v['negatives']} | {v['positives']} | "
                 f"{v['false_successes']} |")
    L.append("")
    for alarm in e.get("integrity_alarms") or []:
        L.append(f"- **INTEGRITY ALARM** — {alarm}")
    fc = e.get("family_cost") or {}
    if fc.get("families_lost"):
        counts = ", ".join(f"{f} ({fc['lost_counts'][f]})" for f in fc["families_lost"])
        L += ["**Cost in task families.** The exclusion is not spread evenly. "
              f"{len(fc['families_lost'])} of {len(fc['families_before'])} families go to "
              f"zero — {counts} — leaving {', '.join(fc['families_after'])}.", ""]
        if not fc["recoverable_by_policy"]:
            L += ["Every record of every lost family lives in a run that executed a "
                  "superseded battery, so **no setting of `eligibility.on_unattested` "
                  "recovers any of them**; only re-running the battery does. Read every "
                  "arm's coverage below as coverage of "
                  f"{'/'.join(fc['families_after'])} traces, not of the corpus.", ""]
        else:
            L += ["Recoverable by relaxing `eligibility.on_unattested`: "
                  f"{', '.join(fc['recoverable_by_policy'])}.", ""]

    excluded = led.get("_excluded_records") or []
    if excluded:
        L += [f"{len(excluded)} record(s) were excluded before selection, so no arm scored "
              "them.", ""]
        stale = [x for x in excluded if x["status"] == corpus.INELIGIBLE_STALE]
        rest = [x for x in excluded if x["status"] != corpus.INELIGIBLE_STALE]
        if stale:
            L += [f"**Stale — B3.2's own exclusion ({len(stale)}).** Each of these agents was "
                  "graded against an expectation the battery no longer holds, so it answered a "
                  "different question from the one every arm is shown. Itemised in full "
                  "because this is the defect, not a side effect:", ""]
            for x in stale:
                L.append(f"  - `{'/'.join(map(str, x['key']))}` [{x['outcome']}"
                         + (", false_success" if x["false_success"] else "")
                         + f"] — {x['detail']}")
            L.append("")
        if rest:
            L += [f"**Unattested ({len(rest)}).** Cross-battery records with nothing to compare, "
                  "so the join can be shown neither sound nor unsound. Grouped by run and "
                  "cause; the full list is in `analysis.json`:", "",
                  "| Run | Cause | n | negatives |", "|---|---|---|---|"]
            groups: dict[tuple[str, str], list[dict]] = {}
            for x in rest:
                groups.setdefault((x["key"][0], _cause(x["detail"])), []).append(x)
            for (run, cause), members in sorted(groups.items()):
                L.append(f"| `{run}` | {cause} | {len(members)} | "
                         f"{sum(1 for m in members if m['outcome'] == 'fail')} |")
            L.append("")

    dp = out.get("denominator_populations") or {}
    if dp:
        L += ["Denominators, against the sizes 6.3 preregistered before this rule existed:", "",
              "| Denominator | n | 6.3 preregistered | difference | over |",
              "|---|---|---|---|---|"]
        for name, v in dp.items():
            diff = v["shrunk_by"]
            L.append(f"| `{name}` | {v['n']} | {v['preregistered_n']} | "
                     f"{'—' if diff is None else f'−{diff}' if diff > 0 else f'+{-diff}'} | "
                     f"{v['population']} |")
        L.append("")
    return L


def _cause(detail: str) -> str:
    """The short form of an unattested record's reason, for the grouped table."""
    if "check kind is" in detail:
        return f"check kind {detail.split('check kind is')[1].split(',')[0].strip()}"
    if "no expected value was recorded" in detail:
        return "no submission, so no expected was computed"
    if "not pinned" in detail:
        return "run not pinned in the freeze"
    return "unattested"


def _fmt(x: Any, nd: int = 1) -> str:
    return "undefined" if x is None else f"{x:.{nd}f}"


def main() -> int:
    import sys
    if len(sys.argv) < 2:
        print("usage: python3 analyze.py results/<run_id>")
        return 2
    d = sys.argv[1]
    with open(f"{d}/analysis.json", encoding="utf-8") as fh:
        print(format_report(json.load(fh)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
