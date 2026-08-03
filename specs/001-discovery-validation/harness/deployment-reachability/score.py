"""Score every arm against every configuration, per PREREGISTRATION.md.

served-set precision = |P n A_c| / |P|
served-set recall    = |P n A_c| / |A_c n (S u N)|

P is what the arm declares reachable at catalogue-generation time. For R3 a second,
runtime reading is computed and reported alongside; the pre-registered gate is the
emission-time one.

Candidates are S u N. Anything an arm nominates outside that set is ignored: what an
extractor recovers is finding 004's measurement, not this one. Anything inside it that
the arm does not positively judge served is excluded (fail-closed, as pre-registered).

No model is called.
"""

from __future__ import annotations

import argparse
import json
import re

GATE = 0.95


def norm(path):
    """Strip Starlette's path-converter suffix, per finding 007."""
    return re.sub(r"\{([A-Za-z_][A-Za-z0-9_]*):[a-z]+\}", r"{\1}", path)


def pair(m, p):
    return (m, norm(p))


def load(path):
    return json.load(open(path))


def prf(P, served, candidates_served):
    tp = P & served
    precision = len(tp) / len(P) if P else 0.0
    recall = len(tp) / len(candidates_served) if candidates_served else 0.0
    return {
        "predicted": len(P),
        "tp": len(tp),
        "fp": len(P - served),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "fp_examples": [list(x) for x in sorted(P - served)[:8]],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--static-set", required=True)
    ap.add_argument("--served-key", required=True)
    ap.add_argument("--r1-naive", required=True)
    ap.add_argument("--r1-tuned", required=True)
    ap.add_argument("--probe", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    st = load(args.static_set)
    key = load(args.served_key)
    naive = load(args.r1_naive)["configs"]
    tuned = load(args.r1_tuned)["configs"]
    probe = load(args.probe)

    S = {pair(*p) for p in st["static_set"]}
    N = {pair(*p) for p in st["null_set"]["phantoms"]} | {
        pair(*p) for p in st["null_set"]["foreign_apps"]
    }
    candidates = S | N

    report = {
        "gate": GATE,
        "gate_reading": "emission-time precision, pre-registered",
        "static_set_size": len(S),
        "null_set_size": len(N),
        "configs": {},
        "openapi_coverage": {},
        "r3_mechanism": {},
    }

    for cname, cfg in key.items():
        if not cfg.get("ok"):
            report["configs"][cname] = {"ok": False}
            continue

        served_all = {pair(r[1], r[2]) for r in cfg["routes"]}
        served_candidates = served_all & candidates

        arms = {}

        # --- R0: emit everything static analysis recovered ---
        arms["R0_baseline"] = prf(set(S), served_all, served_candidates)

        # --- R1-naive ---
        nv = naive.get(cname, {})
        P = {pair(*p) for p in nv.get("certain", [])} & candidates
        arms["R1_naive"] = prf(P, served_all, served_candidates)
        arms["R1_naive"]["unresolvable_guards"] = len(
            {pair(*p) for p in nv.get("uncertain", [])} & candidates
        )
        # secondary: fail-open on unresolvable
        Po = P | ({pair(*p) for p in nv.get("uncertain", [])} & candidates)
        arms["R1_naive_failopen"] = prf(Po, served_all, served_candidates)

        # --- R1-tuned ---
        tn = tuned.get(cname, {})
        P = {pair(*p) for p in tn.get("certain", [])} & candidates
        arms["R1_tuned"] = prf(P, served_all, served_candidates)
        arms["R1_tuned"]["unresolvable_guards"] = len(
            {pair(*p) for p in tn.get("uncertain", [])} & candidates
        )
        Po = P | ({pair(*p) for p in tn.get("uncertain", [])} & candidates)
        arms["R1_tuned_failopen"] = prf(Po, served_all, served_candidates)

        pr = probe.get(cname, {})
        if pr.get("ok"):
            # --- R2-openapi: intersect the static set with what /openapi.json says ---
            oa = {pair(*p) for p in pr["openapi_pairs"]}
            arms["R2_openapi"] = prf(S & oa, served_all, served_candidates)
            arms["R2_openapi"]["openapi_pairs"] = len(oa)
            # what the static set loses by trusting openapi alone
            arms["R2_openapi"]["served_static_ops_dropped"] = sorted(
                [list(x) for x in (served_candidates & S) - oa]
            )

            # --- R2-routetable: upper bound, tautological ---
            arms["R2_routetable_upperbound"] = prf(
                S & served_all, served_all, served_candidates
            )

            # --- R3: precondition checked before first use ---
            pp = pr["path_probe"]
            # path-level: the side-effect-free check. A candidate is admitted when
            # its path is routed.
            P3_path = {
                (m, p)
                for (m, p) in candidates
                if pp.get(p, {}).get("routed") or pp.get(_denorm(p, pp), {}).get("routed")
            }
            P3_path &= S
            arms["R3_precondition_path_level"] = prf(
                P3_path, served_all, served_candidates
            )
            # exact: the Allow header names the methods the path serves.
            P3_exact = set()
            for (m, p) in S:
                rec = pp.get(p) or pp.get(_denorm(p, pp)) or {}
                if not rec.get("routed"):
                    continue
                allow = rec.get("allow")
                if allow:
                    allowed = {
                        v.strip().upper() for v in allow.split(",") if v.strip()
                    }
                    if m in allowed:
                        P3_exact.add((m, p))
                else:
                    # No Allow header: the check degrades to path level.
                    P3_exact.add((m, p))
            arms["R3_precondition_allow_header"] = prf(
                P3_exact, served_all, served_candidates
            )
            # R3 emission-time: the catalogue still contains everything.
            arms["R3_emission_time"] = prf(set(S), served_all, served_candidates)

            report["openapi_coverage"][cname] = {
                "served_total": len(served_all),
                "in_openapi": len(served_all & oa),
                "coverage": round(len(served_all & oa) / len(served_all), 4),
                "served_not_in_openapi": sorted(
                    [list(x) for x in served_all - oa]
                ),
            }
            routed = [v for v in pp.values() if v.get("routed")]
            report["r3_mechanism"][cname] = {
                "paths_probed": len(pp),
                "paths_routed": len(routed),
                "routed_with_allow_header": sum(1 for v in routed if v.get("allow")),
                "routed_without_allow_header": [
                    p for p, v in sorted(pp.items()) if v.get("routed") and not v.get("allow")
                ],
                "distinct_status_codes": sorted(
                    {v.get("status") for v in pp.values() if v.get("status")}
                ),
            }

        # false inclusion over the null set
        for aname, a in arms.items():
            a["gate_pass"] = a["precision"] >= GATE

        arms_null = {}
        for aname, P in (
            ("R0_baseline", set(S)),
            ("R1_naive", {pair(*p) for p in nv.get("certain", [])} & candidates),
            ("R1_tuned", {pair(*p) for p in tn.get("certain", [])} & candidates),
        ):
            arms_null[aname] = {
                "null_included": sorted([list(x) for x in P & N]),
                "false_inclusion_rate": round(len(P & N) / len(N), 4) if N else 0.0,
            }
        if pr.get("ok"):
            oa = {pair(*p) for p in pr["openapi_pairs"]}
            arms_null["R2_openapi"] = {
                "null_included": sorted([list(x) for x in (S & oa) & N]),
                "false_inclusion_rate": 0.0,
            }
            # R3's precondition applied to the null set directly, not intersected
            # with S: this is what the check would say if asked about a phantom.
            pp = pr["path_probe"]
            n_routed = {
                (m, p) for (m, p) in N if (pp.get(p) or {}).get("routed")
            }
            arms_null["R3_precondition"] = {
                "null_included": sorted([list(x) for x in n_routed]),
                "false_inclusion_rate": round(len(n_routed) / len(N), 4) if N else 0.0,
            }

        report["configs"][cname] = {
            "ok": True,
            "declared_config": cfg["declared_config"],
            "served_total": len(served_all),
            "served_in_candidates": len(served_candidates),
            "arms": arms,
            "null": arms_null,
        }

    # gate adjudication across every configuration
    verdict = {}
    arm_names = set()
    for c in report["configs"].values():
        if c.get("ok"):
            arm_names |= set(c["arms"])
    for aname in sorted(arm_names):
        precisions = {
            cname: c["arms"][aname]["precision"]
            for cname, c in report["configs"].items()
            if c.get("ok") and aname in c["arms"]
        }
        worst = min(precisions.values()) if precisions else 0.0
        verdict[aname] = {
            "configs_scored": len(precisions),
            "min_precision": round(worst, 4),
            "max_precision": round(max(precisions.values()), 4) if precisions else 0.0,
            "clears_gate_everywhere": all(v >= GATE for v in precisions.values())
            and len(precisions) > 0,
            "per_config": {k: round(v, 4) for k, v in sorted(precisions.items())},
        }
    report["verdict"] = verdict

    with open(args.out, "w") as fh:
        json.dump(report, fh, indent=2, sort_keys=True, default=str)

    # ---- human-readable summary ----
    cfgs = [c for c in report["configs"] if report["configs"][c].get("ok")]
    print(f"static set S = {len(S)}   null set N = {len(N)}   "
          f"configurations = {len(cfgs)}\n")
    hdr = f"{'arm':34s}" + "".join(f"{c[:11]:>13s}" for c in cfgs) + f"{'min':>8s}  gate"
    print(hdr)
    print("-" * len(hdr))
    for aname in sorted(arm_names):
        v = verdict[aname]
        row = f"{aname:34s}"
        for c in cfgs:
            p = report["configs"][c]["arms"].get(aname, {}).get("precision")
            row += f"{p:>13.4f}" if p is not None else f"{'-':>13s}"
        row += f"{v['min_precision']:>8.4f}  "
        row += "PASS" if v["clears_gate_everywhere"] else "MISS"
        print(row)

    print("\nrecall (same arms, same order)")
    for aname in sorted(arm_names):
        row = f"{aname:34s}"
        for c in cfgs:
            r = report["configs"][c]["arms"].get(aname, {}).get("recall")
            row += f"{r:>13.4f}" if r is not None else f"{'-':>13s}"
        print(row)

    print("\nfalse inclusion over the null set (target 0.0000)")
    for aname in sorted(next(iter(report["configs"].values()))["null"]):
        row = f"{aname:34s}"
        for c in cfgs:
            fr = report["configs"][c]["null"].get(aname, {}).get(
                "false_inclusion_rate"
            )
            row += f"{fr:>13.4f}" if fr is not None else f"{'-':>13s}"
        print(row)

    print("\nunresolvable guards (fail-closed, so these are excluded from P)")
    for aname in ("R1_naive", "R1_tuned"):
        row = f"{aname:34s}"
        for c in cfgs:
            u = report["configs"][c]["arms"][aname].get("unresolvable_guards")
            row += f"{u:>13d}" if u is not None else f"{'-':>13s}"
        print(row)

    print("\nOpenAPI coverage of the served set")
    for c in cfgs:
        oc = report["openapi_coverage"].get(c)
        if oc:
            print(f"  {c:22s} {oc['in_openapi']:3d}/{oc['served_total']:3d} = "
                  f"{oc['coverage']:.4f}")


def _denorm(p, pp):
    """The probe recorded raw framework paths; try the un-normalised key too."""
    for k in pp:
        if norm(k) == p:
            return k
    return p


if __name__ == "__main__":
    main()
