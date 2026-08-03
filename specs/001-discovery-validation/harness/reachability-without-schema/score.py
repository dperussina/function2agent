#!/usr/bin/env python3
"""E15 scorer. Adjudicates the two pre-registered gates and reports the two measurements.

Gate 1  schema-free path-level served-set precision >= 0.95 on every configuration
Gate 2  schema state detected and distinguished, 1.0000 absolute

Measurements, deliberately ungated (see PREREGISTRATION.md): method-level recall of the
schema-free path, contract components retained, and handler invocations during probing.

Every reading is computed over the pre-registered candidate set. Two granularities are
reported for the path-level arms and the difference between them is the point:

  operation granularity   a prediction is a (method, path) pair. This is what "served-set
                          precision" means and what finding 010 reported, so it is the gate.
  path granularity        a prediction is a path. A path-level probe answers this question and
                          only this question, so it is reported as the mechanism's ceiling.

Usage: score.py --probe-fastapi ... --probe-fixtures ... --served-key ... --static-set ...
                --fixture-sets ... --out scores.json
"""

import argparse
import json
import re

GATE_PRECISION = 0.95
AUTO_METHODS = {"HEAD", "OPTIONS"}  # framework-added, never author-declared


def normalise(p):
    p = p.replace("<", "{").replace(">", "}")
    for conv in ("string:", "str:", "int:", "path:", "slug:", "uuid:"):
        p = p.replace("{" + conv, "{")
    return re.sub(r"\{([^}:]+):[^}]*\}", r"{\1}", p)


def rate(num, den):
    return None if den == 0 else round(num / den, 4)


def score_arm(probe_arm, candidates, served, nulls, allow_filter=False):
    """Precision, recall and null false-inclusion at both granularities.

    `allow_filter=True` scores the DERIVED arm `P-global+Allow`: the same requests, with the
    405 response's `Allow` header used to reject candidate methods the header does not list.
    Derived from data already collected, so it costs no extra request. Added after the two
    pre-registered arms were scored, because both of their false positives turned out to be
    method-level rather than path-level, and this is the only schema-free refinement that
    addresses that. **Labelled post-hoc everywhere it appears.**
    """
    routed_paths = {p for p, r in probe_arm.items() if r.get("routed")}

    # Operation granularity: predict every candidate operation whose path is routed.
    pred = {(m, p) for (m, p) in candidates if p in routed_paths}
    if allow_filter:
        allowed = {}
        for path, rec in probe_arm.items():
            hdr = rec.get("allow")
            allowed[path] = (
                {x.strip().upper() for x in hdr.split(",")} if hdr else None
            )
        # A routed path with no Allow header cannot be filtered, so its operations are dropped:
        # fail-closed, which costs recall rather than precision.
        pred = {(m, p) for (m, p) in pred
                if allowed.get(p) is not None and m in allowed[p]}
    tp = pred & served
    fp = pred - served
    reachable = served & candidates

    # Path granularity: predict every candidate path that is routed.
    served_paths = {p for _, p in served}
    cand_paths = {p for _, p in candidates}
    pred_paths = routed_paths & cand_paths
    tp_paths = pred_paths & served_paths

    null_pred = pred & nulls

    return {
        "operation_granularity": {
            "predicted": len(pred),
            "true_positive": len(tp),
            "false_positive": len(fp),
            "precision": rate(len(tp), len(pred)),
            "recall": rate(len(tp), len(reachable)),
            "reachable_in_candidates": len(reachable),
            "false_positive_examples": sorted(f"{m} {p}" for m, p in fp)[:8],
        },
        "path_granularity": {
            "predicted": len(pred_paths),
            "true_positive": len(tp_paths),
            "precision": rate(len(tp_paths), len(pred_paths)),
            "recall": rate(len(tp_paths), len(served_paths & cand_paths)),
        },
        "null_set": {
            "size": len(nulls),
            "falsely_included": len(null_pred),
            "false_inclusion_rate": rate(len(null_pred), len(nulls)),
            "which": sorted(f"{m} {p}" for m, p in null_pred),
        },
    }


def score_methods(probe_arm, served):
    """Method-level discrimination from the `Allow` header. Measurement, never a gate.

    Framework-added HEAD and OPTIONS are stripped from both sides, because neither is ever
    author-declared and leaving them in would score the framework rather than the mechanism.
    """
    served_by_path = {}
    for m, p in served:
        served_by_path.setdefault(p, set()).add(m)

    tp = fp = fn = 0
    paths_with_allow = paths_routed = 0
    wrong = []
    for p, r in probe_arm.items():
        if not r.get("routed"):
            continue
        paths_routed += 1
        actual = served_by_path.get(p, set()) - AUTO_METHODS
        if not actual:
            continue
        allow = r.get("allow")
        if not allow:
            fn += len(actual)
            continue
        paths_with_allow += 1
        got = {x.strip().upper() for x in allow.split(",")} - AUTO_METHODS
        tp += len(got & actual)
        fp += len(got - actual)
        fn += len(actual - got)
        if got != actual:
            wrong.append({"path": p, "allow_reports": sorted(got), "actually_serves": sorted(actual)})
    return {
        "paths_routed": paths_routed,
        "paths_with_allow_header": paths_with_allow,
        "allow_method_precision": rate(tp, tp + fp),
        "allow_method_recall": rate(tp, tp + fn),
        "methods_correct": tp, "methods_overreported": fp, "methods_missed": fn,
        "paths_where_allow_is_wrong": len(wrong),
        "examples": wrong[:8],
    }


def handler_stats(target, arm):
    a = target["arms"][arm]
    detected = sorted(p for p, r in a.items()
                      if r.get("handler_ran_provable") or r.get("handler_ran_calibrated"))
    provable = sorted(p for p, r in a.items() if r.get("handler_ran_provable"))
    counted = target.get("handler_log", {}).get(arm)
    return {
        "detected": len(detected),
        "detected_paths": detected,
        "by_provable_status_rule": len(provable),
        "counted_from_server_log": (None if counted is None else len(counted)),
        "counted_detail": counted,
        "instrument": ("counted from the server's own log"
                       if counted else "detector validated against counted fixtures"),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe-fastapi", required=True)
    ap.add_argument("--probe-fixtures", required=True)
    ap.add_argument("--served-key", required=True)
    ap.add_argument("--static-set", required=True)
    ap.add_argument("--fixture-sets", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    pf = json.load(open(args.probe_fastapi))
    px = json.load(open(args.probe_fixtures))
    sk = json.load(open(args.served_key))
    st = json.load(open(args.static_set))
    fs = json.load(open(args.fixture_sets))

    scores = {"targets": {}}

    # ---- FastAPI configurations: E14's candidate set, unchanged
    S = {(m, normalise(p)) for m, p in st["static_set"]}
    N = {(m, normalise(p)) for m, p in st["null_set"]["phantoms"]}
    N |= {(m, normalise(p)) for m, p in st["null_set"]["foreign_apps"]}
    cand = S | N

    for cfg, target in sorted(pf.items()):
        served = {(m, normalise(p)) for kind, m, p in sk[cfg]["routes"]
                  if kind in ("api", "starlette")}
        entry = {
            "framework": "FastAPI (Starlette router)",
            "schema": target["schema"],
            "candidate_set_size": len(cand),
            "static_set_size": len(S), "null_set_size": len(N),
            "served_total": sk[cfg]["route_count"],
            "served_in_candidates": len(served & cand),
            "arms": {}, "methods": {}, "handlers": {},
            "R0_baseline": {
                "operation_granularity": {
                    "predicted": len(cand),
                    "precision": rate(len(cand & served), len(cand)),
                    "recall": rate(len(cand & served), len(served & cand)),
                }
            },
        }
        for arm in ("P-e14", "P-global"):
            entry["arms"][arm] = score_arm(target["arms"][arm], cand, served, N)
            entry["methods"][arm] = score_methods(target["arms"][arm], served)
            entry["handlers"][arm] = handler_stats(target, arm)
        entry["arms"]["P-global+Allow"] = score_arm(
            target["arms"]["P-global"], cand, served, N, allow_filter=True)
        entry["arms"]["P-global+Allow"]["provenance"] = "DERIVED, post-hoc, no extra requests"
        entry["handlers"]["P-global+Allow"] = entry["handlers"]["P-global"]
        # R2-openapi, scored only where a schema is actually readable.
        ops = target["schema"].get("operations")
        if ops:
            r2 = {(m, normalise(p)) for m, p in ops} & cand
            entry["R2_openapi"] = {
                "predicted": len(r2),
                "precision": rate(len(r2 & served), len(r2)),
                "recall": rate(len(r2 & served), len(served & cand)),
                "schema_operation_count": target["schema"]["operation_count"],
            }
        else:
            entry["R2_openapi"] = {
                "predicted": 0, "precision": None, "recall": 0.0,
                "note": f"schema state {target['schema']['state']}: no operations readable",
            }
        scores["targets"][cfg] = entry

    # ---- Fixtures: each target's own pre-registered sets
    for fw, target in sorted(px.items()):
        f = fs[fw]
        S2 = {(m, normalise(p)) for m, p in f["static_set"]}
        N2 = {(m, normalise(p)) for m, p in f["null_set"]}
        cand2 = S2 | N2
        served2 = {(m, normalise(p)) for m, p in f["served_set"]}
        entry = {
            "framework": {"starlette": "Starlette (control)", "flask": "Flask / Werkzeug",
                          "django": "Django"}[fw],
            "schema": target["schema"],
            "candidate_set_size": len(cand2),
            "static_set_size": len(S2), "null_set_size": len(N2),
            "served_total": len(served2),
            "served_in_candidates": len(served2 & cand2),
            "static_unresolved": f["static_unresolved"],
            "declared_not_served": f["declared_not_served"],
            "arms": {}, "methods": {}, "handlers": {},
            "R0_baseline": {
                "operation_granularity": {
                    "predicted": len(cand2),
                    "precision": rate(len(cand2 & served2), len(cand2)),
                    "recall": rate(len(cand2 & served2), len(served2 & cand2)),
                }
            },
            "R2_openapi": {"predicted": 0, "precision": None, "recall": 0.0,
                           "note": "framework publishes no schema"},
        }
        for arm in ("P-e14", "P-global"):
            entry["arms"][arm] = score_arm(target["arms"][arm], cand2, served2, N2)
            entry["methods"][arm] = score_methods(target["arms"][arm], served2)
            entry["handlers"][arm] = handler_stats(target, arm)
        entry["arms"]["P-global+Allow"] = score_arm(
            target["arms"]["P-global"], cand2, served2, N2, allow_filter=True)
        entry["arms"]["P-global+Allow"]["provenance"] = "DERIVED, post-hoc, no extra requests"
        entry["handlers"]["P-global+Allow"] = entry["handlers"]["P-global"]
        if target.get("adversarial_probe"):
            entry["adversarial_probe"] = target["adversarial_probe"]
        scores["targets"][fw] = entry

    # ------------------------------------------------------------------ gate adjudication
    expected_state = {
        "web": "PRESENT", "web_no_schema": "ABSENT", "web_schema_401": "FORBIDDEN",
        "web_empty_schema": "EMPTY", "starlette": "ABSENT", "flask": "ABSENT",
        "django": "ABSENT",
    }
    g2_rows, g2_ok, g2_ok3 = [], True, True
    for name, exp in expected_state.items():
        got = scores["targets"][name]["schema"]["state"]
        naive = scores["targets"][name]["schema"].get("naive_2xx_reading")
        ok4 = got == exp
        # The plan's three-state reading collapses EMPTY into PRESENT.
        exp3 = "PRESENT" if exp == "EMPTY" else exp
        got3 = "PRESENT" if got == "EMPTY" else got
        g2_ok &= ok4
        g2_ok3 &= (got3 == exp3)
        g2_rows.append({"target": name, "expected": exp, "got": got, "correct": ok4,
                        "naive_2xx_reading": naive,
                        "naive_reading_correct": (naive == "present") == (exp == "PRESENT")})
    scores["gate_2_schema_state"] = {
        "threshold": "1.0000 absolute",
        "four_state_reading": {"correct": sum(r["correct"] for r in g2_rows),
                               "of": len(g2_rows),
                               "rate": rate(sum(r["correct"] for r in g2_rows), len(g2_rows)),
                               "verdict": "CLEARS" if g2_ok else "MISSES"},
        "plan_three_state_reading": {"verdict": "CLEARS" if g2_ok3 else "MISSES"},
        "naive_2xx_pipeline": {
            "correct": sum(r["naive_reading_correct"] for r in g2_rows),
            "of": len(g2_rows),
            "rate": rate(sum(r["naive_reading_correct"] for r in g2_rows), len(g2_rows)),
            "note": "not an arm under test; the reading a pipeline that only checks whether "
                    "the fetch succeeded would produce",
        },
        "rows": g2_rows,
    }

    g1 = {}
    for arm in ("P-e14", "P-global", "P-global+Allow"):
        rows = []
        for name, e in sorted(scores["targets"].items()):
            og = e["arms"][arm]["operation_granularity"]
            pg = e["arms"][arm]["path_granularity"]
            rows.append({
                "target": name, "framework": e["framework"],
                "operation_precision": og["precision"], "operation_recall": og["recall"],
                "path_precision": pg["precision"], "path_recall": pg["recall"],
                "null_false_inclusion": e["arms"][arm]["null_set"]["false_inclusion_rate"],
                "handler_invocations": e["handlers"][arm]["detected"],
                "clears_operation": (og["precision"] or 0) >= GATE_PRECISION,
                "clears_path": (pg["precision"] or 0) >= GATE_PRECISION,
            })
        g1[arm] = {
            "threshold": GATE_PRECISION,
            "operation_granularity_verdict":
                "CLEARS" if all(r["clears_operation"] for r in rows) else "MISSES",
            "operation_granularity_worst": min(
                (r["operation_precision"] for r in rows if r["operation_precision"] is not None),
                default=None),
            "path_granularity_verdict":
                "CLEARS" if all(r["clears_path"] for r in rows) else "MISSES",
            "path_granularity_worst": min(
                (r["path_precision"] for r in rows if r["path_precision"] is not None),
                default=None),
            "targets_missing_operation_gate":
                [r["target"] for r in rows if not r["clears_operation"]],
            "total_handler_invocations": sum(r["handler_invocations"] for r in rows),
            "rows": rows,
        }
    scores["gate_1_path_level_precision"] = g1

    json.dump(scores, open(args.out, "w"), indent=2, sort_keys=True, default=str)

    # ------------------------------------------------------------------------- report
    print("=" * 96)
    print("GATE 2 — schema state detected and distinguished (threshold 1.0000, absolute)")
    print("=" * 96)
    print(f"{'target':20s} {'expected':10s} {'got':10s} {'ok':>4s}   "
          f"{'naive 2xx pipeline':>20s} {'ok':>4s}")
    for r in g2_rows:
        print(f"{r['target']:20s} {r['expected']:10s} {r['got']:10s} "
              f"{'YES' if r['correct'] else 'NO':>4s}   {r['naive_2xx_reading']:>20s} "
              f"{'YES' if r['naive_reading_correct'] else 'NO':>4s}")
    g2 = scores["gate_2_schema_state"]
    print(f"\n  four-state reading: {g2['four_state_reading']['verdict']} "
          f"({g2['four_state_reading']['correct']}/{g2['four_state_reading']['of']})")
    print(f"  plan's three-state reading: {g2['plan_three_state_reading']['verdict']}")
    print(f"  a 2xx-only pipeline would be correct on "
          f"{g2['naive_2xx_pipeline']['correct']}/{g2['naive_2xx_pipeline']['of']} "
          f"({g2['naive_2xx_pipeline']['rate']})")

    for arm in ("P-e14", "P-global", "P-global+Allow"):
        print()
        print("=" * 96)
        tag = "  [DERIVED, post-hoc]" if arm == "P-global+Allow" else ""
        print(f"GATE 1 — schema-free path-level precision, arm {arm} (threshold 0.95){tag}")
        print("=" * 96)
        print(f"{'target':18s} {'framework':26s} {'op-prec':>8s} {'op-rec':>7s} "
              f"{'path-prec':>10s} {'null-FI':>8s} {'handlers':>9s}")
        for r in g1[arm]["rows"]:
            flag = "" if r["clears_operation"] else "  <-- MISS"
            print(f"{r['target']:18s} {r['framework']:26s} "
                  f"{str(r['operation_precision']):>8s} {str(r['operation_recall']):>7s} "
                  f"{str(r['path_precision']):>10s} {str(r['null_false_inclusion']):>8s} "
                  f"{r['handler_invocations']:>9d}{flag}")
        print(f"  operation granularity (THE GATE): "
              f"{g1[arm]['operation_granularity_verdict']}, worst "
              f"{g1[arm]['operation_granularity_worst']}")
        print(f"  path granularity (the mechanism's ceiling): "
              f"{g1[arm]['path_granularity_verdict']}, worst "
              f"{g1[arm]['path_granularity_worst']}")
        print(f"  handler invocations across all seven targets: "
              f"{g1[arm]['total_handler_invocations']}")

    print()
    print("=" * 96)
    print("MEASUREMENT — method-level discrimination from the Allow header (no gate)")
    print("=" * 96)
    print(f"{'target':18s} {'framework':26s} {'allow-prec':>11s} {'allow-rec':>10s} "
          f"{'paths wrong':>12s} {'no header':>10s}")
    for name, e in sorted(scores["targets"].items()):
        m = e["methods"]["P-global"]
        print(f"{name:18s} {e['framework']:26s} "
              f"{str(m['allow_method_precision']):>11s} {str(m['allow_method_recall']):>10s} "
              f"{m['paths_where_allow_is_wrong']:>12d} "
              f"{m['paths_routed'] - m['paths_with_allow_header']:>10d}")

    print()
    print("=" * 96)
    print("MEASUREMENT — reachability with the schema removed (R2 vs the schema-free arms)")
    print("=" * 96)
    print(f"{'target':18s} {'schema':10s} {'R0-prec':>8s} {'R2-prec':>8s} {'R2-rec':>7s} "
          f"{'P-global-prec':>14s} {'P-global-rec':>13s}")
    for name, e in sorted(scores["targets"].items()):
        r0 = e["R0_baseline"]["operation_granularity"]
        r2 = e["R2_openapi"]
        pg = e["arms"]["P-global"]["operation_granularity"]
        print(f"{name:18s} {e['schema']['state']:10s} {str(r0['precision']):>8s} "
              f"{str(r2['precision']):>8s} {str(r2['recall']):>7s} "
              f"{str(pg['precision']):>14s} {str(pg['recall']):>13s}")

    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
