"""SPIKE - E8 verifier-vs-judge. Delete after 2026-11-30. Do not import from product code.

Arm (c2)'s false-alarm census, stratified by how each record's join is attested.

Finding 015 reports the census as a single pooled rate: over all 226 oracle-positives c2
raises 6 alarms, all 6 the stale positives of the packaging defect, so **0 of 220 clean
positives**. That number was computed by calling :func:`c2_postcond.verify` directly over the
frozen corpus; no script computing it was committed, so re-running it meant writing this one.
This module is that driver and nothing more — every verdict, every eligibility status and
every population boundary comes from the existing modules, and the only thing added here is
the *stratification*.

Why the stratification is the point (finding 017, S1)
-----------------------------------------------------
The pooled denominator of 220 is a mixed population. 143 of the 246 frozen records ran under a
battery version that no longer exists, and the only per-record evidence keeping most of them in
scope is :data:`corpus.ELIGIBLE_VALUE_ATTESTED` — a value comparison that finding 015 shows is
**blind to wording drift**, which is the drift a prompt amendment actually produces. Only
:data:`corpus.ELIGIBLE_SAME_BATTERY` attests the join with no cross-artifact join at all.

So the census is reported over both:

* **pooled** — every oracle-positive that is not ``ineligible_stale``. This is finding 015's 220
  and it is reproduced here rather than quoted.
* **narrow** — every oracle-positive whose run manifest declares the battery under test. No join
  is performed for these records, so nothing about them rests on the value test.

Read-only, model-free, credential-free. It reads the frozen corpus, the committed offline state
fixture, and nothing else; ``--verify-pooled`` additionally asserts that the pooled stratum
reproduces the figures finding 015 published, which is the contemporaneity check on the harness
itself.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import c2_postcond  # noqa: E402
import corpus  # noqa: E402
import freeze  # noqa: E402
import metrics  # noqa: E402
import redact  # noqa: E402

#: What finding 015 published. Asserted rather than quoted, so that a harness that has moved
#: since the census cannot silently reproduce a different number under the same label.
PUBLISHED = {"oracle_positives": 226, "alarms_all_positives": 6, "clean_positives": 220,
             "alarms_clean_positives": 0}


def census(cfg: dict | None = None) -> dict:
    """Score arm (c2) over every frozen record and stratify the positives by attestation."""
    cfg = cfg or freeze.load_config()
    rows, traces = corpus.load_records(cfg)
    battery = corpus.load_battery(cfg)
    part = corpus.partition(rows, cfg)
    trace_by_key = {corpus.trace_key(t): t for t in traces}

    source = c2_postcond.open_source()
    derivations = c2_postcond.load_derivations()

    scored: list[dict] = []
    for r in rows:
        key = corpus.trace_key(r)
        trace = trace_by_key[key]
        prompt = (battery.get(r["task_id"]) or {}).get("prompt", "")
        view = redact.scoring_view(trace, prompt)
        verdict = c2_postcond.verify(view, r, source, derivations)
        elig = part["verdicts"][key]
        scored.append({
            "key": list(key),
            "outcome": r["outcome"],
            "false_success": bool(r.get("false_success")),
            "family": r["family"],
            "c2_verdict": verdict["verdict"],
            "c2_clause": verdict.get("clause"),
            "c2_detail": verdict.get("detail"),
            "eligibility": elig["status"],
            "run_battery_version": elig["run_battery_version"],
        })

    positives = [s for s in scored if s["outcome"] == "pass"]
    strata = {
        "all_positives": positives,
        "pooled_clean": [s for s in positives
                         if s["eligibility"] != corpus.INELIGIBLE_STALE],
        "narrow_same_battery": [s for s in positives
                                if s["eligibility"] == corpus.ELIGIBLE_SAME_BATTERY],
        "value_attested_only": [s for s in positives
                                if s["eligibility"] == corpus.ELIGIBLE_VALUE_ATTESTED],
        "unattested_only": [s for s in positives
                            if s["eligibility"] == corpus.INELIGIBLE_UNATTESTED],
    }
    return {
        "battery_version": part["battery_version"],
        "source": source.describe(),
        "derivations_sha256_16": c2_postcond.derivations_hash(),
        "n_records": len(scored),
        "strata": {name: _rate(name, members) for name, members in strata.items()},
        "alarms": [s for s in positives if s["c2_verdict"] == c2_postcond.FAIL],
        "scored": scored,
    }


def _rate(name: str, members: list[dict]) -> dict:
    """Denominator, alarm count, rate, and the verdict spread the rate sits inside.

    The rate is a :class:`metrics.Proportion`, so it carries its Wilson interval and its
    population label under the harness's own §6.9 rule rather than being printed bare.

    ``unverifiable`` is reported alongside, and so is the ``compared`` count, because a
    stratum in which c2 declines most records can post a clean false-alarm rate without
    having compared anything. A false-alarm rate quoted without its refusal count invites
    exactly that misreading, and the pooled stratum is where it would bite.
    """
    alarms = [m for m in members if m["c2_verdict"] == c2_postcond.FAIL]
    spread: dict[str, int] = {}
    fams: dict[str, int] = {}
    for m in members:
        spread[m["c2_verdict"]] = spread.get(m["c2_verdict"], 0) + 1
    for a in alarms:
        fams[a["family"]] = fams.get(a["family"], 0) + 1
    compared = [m for m in members
                if m["c2_verdict"] in (c2_postcond.PASS, c2_postcond.FAIL)]
    prop = metrics.Proportion(
        numerator=len(alarms), denominator=len(members), label=f"FPR_c2 ({name})",
        families=fams, population=f"oracle-positives, {name}")
    prop_compared = metrics.Proportion(
        numerator=len(alarms), denominator=len(compared),
        label=f"FPR_c2 ({name}, compared only)", families=fams,
        population=f"oracle-positives c2 actually compared, {name}")
    return {
        "n": len(members),
        "alarms": len(alarms),
        "rate": prop.value,
        "wilson_95_pp": prop.as_dict()["wilson_95_pp"],
        "sentence": prop.sentence(),
        "verdicts": spread,
        "compared": len(compared),
        "compared_sentence": prop_compared.sentence(),
        "families": dict(sorted({m["family"]: sum(1 for x in members
                                                  if x["family"] == m["family"])
                                 for m in members}.items())),
        "compared_families": dict(sorted({m["family"]: sum(1 for x in compared
                                                           if x["family"] == m["family"])
                                          for m in compared}.items())),
        "compared_tasks": len({m["key"][1] for m in compared}),
        "alarm_keys": ["/".join(map(str, a["key"])) for a in alarms],
    }


def verify_pooled(rep: dict) -> list[str]:
    """Does the pooled stratum still reproduce what finding 015 published?

    This is the contemporaneity check the census is subject to. Re-running a census against a
    harness that has moved since the census was published reproduces the very defect finding
    017 is about, one level up. It cannot prove the published figures were produced by *this*
    code — the whole harness landed in one commit — but a disagreement here would prove they
    were not, and there is no disagreement to report.
    """
    got = {
        "oracle_positives": rep["strata"]["all_positives"]["n"],
        "alarms_all_positives": rep["strata"]["all_positives"]["alarms"],
        "clean_positives": rep["strata"]["pooled_clean"]["n"],
        "alarms_clean_positives": rep["strata"]["pooled_clean"]["alarms"],
    }
    return [f"{k}: finding 015 published {v}, this run computes {got[k]}"
            for k, v in PUBLISHED.items() if got[k] != v]


def format_report(rep: dict) -> str:
    L = [f"Arm (c2) false-alarm census — battery {rep['battery_version']}",
         f"  recomputation source: {rep['source']}",
         f"  derivations: sha256:{rep['derivations_sha256_16']}",
         f"  records scored: {rep['n_records']}", "",
         f"  {'stratum':<22} {'n':>4} {'alarms':>7} {'compared':>9} {'tasks':>6}   "
         "verdict spread"]
    for name, s in rep["strata"].items():
        spread = ", ".join(f"{k}={v}" for k, v in sorted(s["verdicts"].items()))
        L.append(f"  {name:<22} {s['n']:>4} {s['alarms']:>7} {s['compared']:>9} "
                 f"{s['compared_tasks']:>6}   {spread}")
    L += ["", "  rates, in the form 6.9 requires:"]
    for name, s in rep["strata"].items():
        L.append(f"    {s['sentence']}")
        L.append(f"      {s['compared_sentence']}")
        L.append(f"      families compared: "
                 + (", ".join(f"{k} {v}" for k, v in s["compared_families"].items()) or "none"))
    L += ["", "  alarms:"]
    L += [f"    - {'/'.join(map(str, a['key']))}  [{a['eligibility']}, "
          f"battery {a['run_battery_version']}]  {a['c2_detail']}"
          for a in rep["alarms"]] or ["    (none)"]
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", action="store_true", help="emit the full report as JSON")
    ap.add_argument("--per-record", action="store_true",
                    help="with --json, include the per-record scoring")
    ap.add_argument("--verify-pooled", action="store_true",
                    help="exit 1 unless the pooled stratum reproduces finding 015's figures")
    args = ap.parse_args()

    rep = census()
    if args.json:
        out = dict(rep)
        if not args.per_record:
            out.pop("scored")
        print(json.dumps(out, indent=1))
    else:
        print(format_report(rep))

    if args.verify_pooled:
        disagreements = verify_pooled(rep)
        print("\ncontemporaneity check against finding 015:")
        for d in disagreements:
            print(f"  DISAGREEMENT — {d}")
        if disagreements:
            return 1
        print("  the pooled stratum reproduces every published figure")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
