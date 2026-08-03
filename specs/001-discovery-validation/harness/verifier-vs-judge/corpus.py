"""SPIKE - E8 verifier-vs-judge. Delete after 2026-11-30. Do not import from product code.

Loading the frozen corpus, and the negative taxonomy PREREGISTRATION.md 2.1 turns on.

Everything here is **oracle-side**. It reads ``expected``, ``reason``, ``outcome`` and
``false_success`` on purpose, because the denominators (6.3), the predicted-null control
(4.6) and the near-miss sensitivity split (6.5) are all defined over them. None of it may
travel to a scorer: scorers receive :func:`redact.scoring_view` output and nothing else, and
:func:`redact.assert_no_oracle_leak` is what enforces that at the call site.

The taxonomy is **mechanical** — it is read off the oracle's own recorded ``reason`` string
by pattern, not hand-assigned per record — so that the numeric subclass the predicted-null
control depends on cannot be quietly adjusted to fit a result.

Eligibility (Amendment B3.2) lives here for the same reason
---------------------------------------------------------
B3.2 requires that "a trace whose recorded ``expected`` disagrees with the battery it is
being scored against is not eligible for any arm", and says the comparison "is oracle
material and so cannot live inside an arm; it belongs in the corpus layer that already
computes denominators". :func:`eligibility` is that comparison. It reads ``expected.json``,
which no scorer may see, and it runs **before** selection so that an excluded record never
reaches a payload rather than being subtracted from a denominator afterwards.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from typing import Any

import freeze

HERE = os.path.dirname(os.path.abspath(__file__))

NO_OUTPUT_RE = re.compile(r"^no answer submitted", re.I)
PROTOCOL_RE = re.compile(r"did not ask for clarification", re.I)
#: "expected 3.201754, got 3.23" — the oracle's numeric-mismatch rendering.
NUMERIC_RE = re.compile(r"^expected\s+(-?[\d.]+)\s*,\s*got\s+(-?[\d.]+)\s*$", re.I)
#: "missing [...], unexpected [...]" — the oracle's set-mismatch rendering.
SET_RE = re.compile(r"missing\s+\[.*\]\s*,\s*unexpected\s+\[", re.I | re.S)

CLASS_NO_OUTPUT = "no_output"
CLASS_PROTOCOL = "protocol"
CLASS_FALSE_SUCCESS = "false_success"

SUB_NUMERIC = "numeric_value_error"
SUB_SET = "set_cardinality_error"
SUB_OTHER = "unclassified_false_success"

NEAR_MISS_REL_TOL = 0.01  # PREREGISTRATION.md 6.5: "under 1% relative error"


def load_records(cfg: dict | None = None, verify: bool = True) -> tuple[list[dict], list[dict]]:
    """Returns (results rows, trace rows) for the frozen scope, in committed run order."""
    cfg = cfg or freeze.load_config()
    if verify:
        freeze.verify_or_die(cfg)
    root = freeze.corpus_root(cfg)
    rows: list[dict] = []
    traces: list[dict] = []
    for run in freeze.SCOPE_RUNS:
        with open(os.path.join(root, run, "results.jsonl"), encoding="utf-8") as fh:
            rows += [json.loads(x) for x in fh if x.strip()]
        with open(os.path.join(root, run, "traces.jsonl"), encoding="utf-8") as fh:
            traces += [json.loads(x) for x in fh if x.strip()]
    return rows, traces


def load_battery(cfg: dict | None = None) -> dict[str, dict]:
    """Task id -> task. Only ``prompt`` is ever passed onward; ``check`` is oracle material."""
    cfg = cfg or freeze.load_config()
    path = os.path.abspath(os.path.join(HERE, cfg["battery"]["tasks_rel"]))
    with open(path, encoding="utf-8") as fh:
        battery = json.load(fh)
    return {t["id"]: t for t in battery["tasks"]}


def load_expected(cfg: dict | None = None) -> tuple[str, dict[str, Any]]:
    """``(battery_version, task id -> expected value)`` from the battery's ``expected.json``.

    **Oracle material.** Used by :func:`eligibility` and by nothing that touches a scorer.
    """
    cfg = cfg or freeze.load_config()
    with open(freeze.battery_paths(cfg)["expected_rel"], encoding="utf-8") as fh:
        doc = json.load(fh)
    return doc["battery_version"], doc["expected"]


def trace_key(r: dict) -> tuple:
    return (r["run_id"], r["task_id"], r["arm"], r["attempt"])


# ------------------------------------------------------------- eligibility (Amendment B3.2)

#: The run executed the battery being scored against. No cross-artifact join occurs: the
#: prompt the arms are shown is the prompt the agent saw.
ELIGIBLE_SAME_BATTERY = "eligible_same_battery"
#: Cross-battery, but the record's stored ``expected`` still equals today's for its task.
#: Positive per-record evidence that the *answer* did not change. See the caveat in
#: :func:`eligibility` — this attests the answer, not the wording.
ELIGIBLE_VALUE_ATTESTED = "eligible_value_attested"
#: The record's stored ``expected`` disagrees with today's. B3.2: not eligible for any arm.
INELIGIBLE_STALE = "ineligible_stale"
#: Cross-battery with no ``expected`` to compare, so the join cannot be attested either way.
INELIGIBLE_UNATTESTED = "ineligible_unattested"

ELIGIBLE_STATUSES = (ELIGIBLE_SAME_BATTERY, ELIGIBLE_VALUE_ATTESTED)
INELIGIBLE_STATUSES = (INELIGIBLE_STALE, INELIGIBLE_UNATTESTED)

#: The check kind that produces a comparable ``expected``. Every other kind (``impossible``,
#: ``needs_clarification``, ``state``) legitimately has no entry in ``expected.json`` under
#: any battery version, so a null there carries no information about drift.
VALUED_CHECK_KIND = "reference_answer"


def _canonical(value: Any) -> tuple:
    """A comparison form that is indifferent to JSON number spelling and nothing else.

    ``13`` and ``13.0`` are the same answer; ``[]`` and ``0`` are not, and ``[8, 0]`` and
    ``[0, 8]`` are not — list order is the answer for a corroborated multi-part expectation.
    """
    if isinstance(value, bool):
        return ("bool", value)
    if isinstance(value, (int, float)):
        return ("num", float(value))
    if isinstance(value, str):
        return ("str", value)
    if isinstance(value, list):
        return ("list", tuple(_canonical(v) for v in value))
    if isinstance(value, dict):
        return ("dict", tuple(sorted((k, _canonical(v)) for k, v in value.items())))
    return ("null", None)


def eligibility(record: dict, task: dict | None, expected_map: dict[str, Any],
                battery_version: str, run_battery_version: str | None) -> dict:
    """Can this record be joined to today's battery? Amendment B3.2.

    Three ways the answer is yes-or-no, and one where it is *unanswerable*, which is the
    distinction the defect turned on:

    * **Same battery.** The run's manifest declares the version being scored against. There is
      no cross-battery join to attest.
    * **Stale.** A comparable ``expected`` is stored and it disagrees with today's. The agent
      answered a different question from the one every arm will be shown. B3.2 excludes it.
    * **Value-attested.** A comparable ``expected`` is stored and it agrees. Weaker than
      same-battery and labelled separately for that reason: it attests that the task's
      *answer* is unchanged, not that its *wording* is. A prompt can be reworded while the
      answer stays 13, and no artifact in this corpus would show it.
    * **Unattested.** Cross-battery, and there is nothing to compare — either the task's check
      kind never produces an ``expected`` (``impossible`` / ``needs_clarification`` /
      ``state``), or the record has no submission so ``ceiling-test/checks.py`` returned before
      computing one. **Absence of a disagreement is not evidence of agreement.** Reading a
      missing value as agreement is precisely how B3's own table came to describe five
      no-output records as "graded against a null expectation"; see Amendment B4.

    A same-battery record whose stored ``expected`` disagrees is a different and worse
    problem — the battery did not change, so either the fixture drifted or ``expected.json``
    was edited. That is reported as ``ineligible_stale`` with ``integrity_alarm`` set, so it
    cannot be read as ordinary battery churn.
    """
    task_id = record["task_id"]
    kind = ((task or {}).get("check") or {}).get("kind")
    stored = record.get("expected")
    same_battery = run_battery_version is not None and run_battery_version == battery_version

    # An unpinned run is refused before any value comparison, and deliberately so. Every
    # in-scope run is pinned, so reaching here means the freeze lost a run's battery version
    # — a broken freeze, not an old one. Letting a matching value attest it would let a
    # damaged freeze produce a scoreable population, which is the silent-join failure again
    # wearing a different hat.
    if run_battery_version is None:
        return {"status": INELIGIBLE_UNATTESTED, "eligible": False, "integrity_alarm": False,
                "run_battery_version": None, "stored_expected": stored,
                "current_expected": expected_map.get(task_id),
                "detail": ("the run is not pinned in corpus_freeze.json, so no battery "
                           "version is known and nothing attests the join")}

    comparable = kind == VALUED_CHECK_KIND and task_id in expected_map and stored is not None
    if comparable:
        current = expected_map[task_id]
        agrees = _canonical(stored) == _canonical(current)
        if not agrees:
            return {
                "status": INELIGIBLE_STALE, "eligible": False,
                "integrity_alarm": same_battery,
                "run_battery_version": run_battery_version,
                "stored_expected": stored, "current_expected": current,
                "detail": (
                    f"stored expected {json.dumps(stored)} disagrees with the battery's "
                    f"{json.dumps(current)}"
                    + (" — and the run declares TODAY'S battery version, so the battery did "
                       "not change: the fixture drifted or expected.json was edited"
                       if same_battery else
                       f" (run executed battery {run_battery_version})")
                ),
            }

    if same_battery:
        return {"status": ELIGIBLE_SAME_BATTERY, "eligible": True, "integrity_alarm": False,
                "run_battery_version": run_battery_version,
                "stored_expected": stored,
                "current_expected": expected_map.get(task_id),
                "detail": f"run executed the battery under test ({battery_version})"}

    if comparable:
        return {"status": ELIGIBLE_VALUE_ATTESTED, "eligible": True, "integrity_alarm": False,
                "run_battery_version": run_battery_version,
                "stored_expected": stored, "current_expected": expected_map[task_id],
                "detail": (f"run executed battery {run_battery_version}, but the stored "
                           "expected still equals the battery's. The answer is attested; the "
                           "prompt wording is not.")}

    if kind != VALUED_CHECK_KIND:
        why = (f"the task's check kind is {kind!r}, which yields no expected value under any "
               "battery version, so nothing attests the join")
    else:
        why = ("no expected value was recorded — checks.py returns before computing one when "
               "nothing was submitted — so nothing attests the join")
    return {"status": INELIGIBLE_UNATTESTED, "eligible": False, "integrity_alarm": False,
            "run_battery_version": run_battery_version,
            "stored_expected": stored, "current_expected": expected_map.get(task_id),
            "detail": f"run executed battery {run_battery_version}: {why}"}


def partition(rows: list[dict], cfg: dict | None = None,
              frozen: dict | None = None) -> dict[str, Any]:
    """Apply :func:`eligibility` to every record and return the population it defines.

    The returned ``ledger`` is what the harness reports. B3.2 says the exclusion must show up
    somewhere a reader sees it; a denominator that shrinks without explanation is the failure
    mode this replaces.
    """
    cfg = cfg or freeze.load_config()
    frozen = frozen or freeze.load_freeze()
    battery = load_battery(cfg)
    battery_version, expected_map = load_expected(cfg)
    policy = cfg.get("eligibility") or {}
    keep_unattested = policy.get("on_unattested") == "include"
    if policy.get("on_stale") != "exclude":
        raise SystemExit(
            "config.eligibility.on_stale must be 'exclude'. PREREGISTRATION.md Amendment B3.2 "
            "makes the stale exclusion mandatory: a trace graded against an expectation the "
            "battery no longer holds was answering a different question from the one every "
            "arm is shown. It is not a tunable."
        )

    verdicts: dict[tuple, dict] = {}
    eligible: list[dict] = []
    excluded: list[dict] = []
    by_status: dict[str, int] = {s: 0 for s in
                                 ELIGIBLE_STATUSES + INELIGIBLE_STATUSES}
    for r in rows:
        v = eligibility(r, battery.get(r["task_id"]), expected_map, battery_version,
                        freeze.run_battery_version(r["run_id"], frozen))
        by_status[v["status"]] = by_status.get(v["status"], 0) + 1
        keep = v["eligible"] or (keep_unattested and v["status"] == INELIGIBLE_UNATTESTED)
        verdicts[trace_key(r)] = v | {"kept": keep}
        (eligible if keep else excluded).append(r)

    alarms = [f"{trace_key(r)}: {verdicts[trace_key(r)]['detail']}"
              for r in rows if verdicts[trace_key(r)].get("integrity_alarm")]
    return {
        "rule": policy.get("rule", "PREREGISTRATION.md Amendment B3.2"),
        "battery_version": battery_version,
        "on_unattested": policy.get("on_unattested", "exclude"),
        "verdicts": verdicts,
        "eligible": eligible,
        "excluded": excluded,
        "by_status": by_status,
        "integrity_alarms": alarms,
        "ledger": _ledger(rows, verdicts),
        "family_cost": _family_cost(rows, eligible, verdicts),
        "population": population_label(len(eligible), len(rows)),
    }


def _family_cost(rows: list[dict], eligible: list[dict],
                 verdicts: dict[tuple, dict]) -> dict[str, Any]:
    """Which task families the rule costs, and whether any policy could have kept them.

    The exclusion is not spread evenly. Every record of every lost family lives in a run
    that executed a superseded battery, so ``recoverable_by_policy`` is empty and only
    re-running the battery changes it. An experiment that lost whole families is a narrower
    experiment, and a reader meeting a coverage number needs that before the number.
    """
    all_f = {r["family"] for r in rows}
    kept_f = {r["family"] for r in eligible}
    same_f = {r["family"] for r in rows
              if verdicts[trace_key(r)]["status"] == ELIGIBLE_SAME_BATTERY}
    lost = sorted(all_f - kept_f)
    return {
        "families_before": sorted(all_f),
        "families_after": sorted(kept_f),
        "families_lost": lost,
        "recoverable_by_policy": sorted(set(lost) & same_f),
        "lost_counts": {f: sum(1 for r in rows if r["family"] == f) for f in lost},
    }


def population_label(n_eligible: int, n_total: int) -> str:
    """The phrase every denominator in the report is qualified by."""
    return (f"eligible records only ({n_eligible} of {n_total}; "
            f"{n_total - n_eligible} excluded by Amendment B3.2)")


def _ledger(rows: list[dict], verdicts: dict[tuple, dict]) -> dict[str, Any]:
    """Counts by status, split by oracle outcome, plus the excluded records by name."""
    out: dict[str, Any] = {}
    for status in ELIGIBLE_STATUSES + INELIGIBLE_STATUSES:
        members = [r for r in rows if verdicts[trace_key(r)]["status"] == status]
        out[status] = {
            "n": len(members),
            "negatives": sum(1 for r in members if r["outcome"] == "fail"),
            "positives": sum(1 for r in members if r["outcome"] == "pass"),
            "false_successes": sum(1 for r in members if r.get("false_success")),
            "tasks": sorted({r["task_id"] for r in members}),
        }
    out["_excluded_records"] = [
        {"key": list(trace_key(r)), "outcome": r["outcome"],
         "false_success": bool(r.get("false_success")),
         "status": verdicts[trace_key(r)]["status"],
         "detail": verdicts[trace_key(r)]["detail"]}
        for r in rows if not verdicts[trace_key(r)]["kept"]
    ]
    return out


def eligible_records(rows: list[dict], cfg: dict | None = None,
                     frozen: dict | None = None) -> tuple[list[dict], dict]:
    """``(rows that may be scored, the partition)``. The pairing is deliberate: a caller
    cannot obtain the filtered rows without also obtaining the ledger it has to report."""
    part = partition(rows, cfg, frozen)
    return part["eligible"], part


def classify(record: dict) -> dict:
    """The negative taxonomy of PREREGISTRATION.md 2.1, derived from the oracle's own text."""
    if record["outcome"] != "fail":
        return {"class": None, "subclass": None, "near_miss": False, "rel_error": None}

    reason = record.get("reason") or ""
    if NO_OUTPUT_RE.search(reason):
        return {"class": CLASS_NO_OUTPUT, "subclass": None, "near_miss": False, "rel_error": None}
    if PROTOCOL_RE.search(reason) and not record.get("false_success"):
        return {"class": CLASS_PROTOCOL, "subclass": None, "near_miss": False, "rel_error": None}

    if record.get("false_success"):
        m = NUMERIC_RE.match(reason.strip())
        if m:
            want, got = float(m.group(1)), float(m.group(2))
            rel = abs(got - want) / abs(want) if want else float("inf")
            return {
                "class": CLASS_FALSE_SUCCESS,
                "subclass": SUB_NUMERIC,
                "near_miss": rel < NEAR_MISS_REL_TOL,
                "rel_error": rel,
            }
        if SET_RE.search(reason):
            return {
                "class": CLASS_FALSE_SUCCESS, "subclass": SUB_SET,
                "near_miss": False, "rel_error": None,
            }
        return {
            "class": CLASS_FALSE_SUCCESS, "subclass": SUB_OTHER,
            "near_miss": False, "rel_error": None,
        }

    # A negative that is neither no-output, protocol, nor flagged false-success. The
    # taxonomy in 2.1 claims to decompose N exhaustively, so this is reported rather than
    # absorbed into a bucket.
    return {"class": "unclassified_negative", "subclass": None,
            "near_miss": False, "rel_error": None}


def taxonomy(rows: list[dict]) -> dict[str, Any]:
    """The counted decomposition, with the preregistered figures alongside for comparison."""
    negs = [r for r in rows if r["outcome"] == "fail"]
    tagged = [(r, classify(r)) for r in negs]
    counts: dict[str, int] = {}
    subs: dict[str, int] = {}
    for _, c in tagged:
        counts[c["class"]] = counts.get(c["class"], 0) + 1
        if c["subclass"]:
            subs[c["subclass"]] = subs.get(c["subclass"], 0) + 1
    near = sum(1 for _, c in tagged if c["near_miss"])
    # 6.9's power rider is stated against whatever population survived eligibility, so the
    # spread of the false-success base has to be counted here rather than quoted from the
    # preregistration. B3.2 can move both the count and its concentration.
    fs = [r for r, c in tagged if c["class"] == CLASS_FALSE_SUCCESS]
    fams: dict[str, int] = {}
    for r in fs:
        fams[r["family"]] = fams.get(r["family"], 0) + 1
    return {
        "n_negatives": len(negs),
        "classes": counts,
        "false_success_subclasses": subs,
        "false_success_tasks": len({r["task_id"] for r in fs}),
        "false_success_families": fams,
        "near_miss_n": near,
        "preregistered": {
            "n_negatives": 20, "no_output": 7, "protocol": 2, "false_success": 11,
            "numeric_value_error": 8, "set_cardinality_error": 3, "near_miss_n": 2,
        },
    }


def taxonomy_discrepancies(tax: dict) -> list[str]:
    """Where the measured decomposition disagrees with PREREGISTRATION.md 2.1.

    Reported loudly and never silently reconciled. The preregistration is the specification;
    a builder who edits the numbers to match their code has invalidated the document.
    """
    pre = tax["preregistered"]
    out: list[str] = []
    got = {
        "n_negatives": tax["n_negatives"],
        "no_output": tax["classes"].get(CLASS_NO_OUTPUT, 0),
        "protocol": tax["classes"].get(CLASS_PROTOCOL, 0),
        "false_success": tax["classes"].get(CLASS_FALSE_SUCCESS, 0),
        "numeric_value_error": tax["false_success_subclasses"].get(SUB_NUMERIC, 0),
        "set_cardinality_error": tax["false_success_subclasses"].get(SUB_SET, 0),
        "near_miss_n": tax["near_miss_n"],
    }
    for k, want in pre.items():
        if got[k] != want:
            out.append(f"{k}: preregistration says {want}, mechanical classification counts {got[k]}")
    if tax["classes"].get("unclassified_negative"):
        out.append(
            f"{tax['classes']['unclassified_negative']} negative(s) fit no class in 2.1, "
            "which claims the decomposition is exhaustive"
        )
    if tax["false_success_subclasses"].get(SUB_OTHER):
        out.append(
            f"{tax['false_success_subclasses'][SUB_OTHER]} false success(es) match neither the "
            "numeric nor the set rendering"
        )
    return out


def denominators(rows: list[dict]) -> dict[str, list[tuple]]:
    """The three denominators of PREREGISTRATION.md 6.3, as trace-key sets.

    ``rows`` must already be the eligible population (:func:`eligible_records`). 6.3's
    preregistered sizes — N = 20, N_disc = 13, N_fs = 11 — were counted before Amendment B3.2
    existed and are over the *unfiltered* corpus; :func:`denominator_populations` records the
    difference rather than leaving a reader to assume the labels still mean what they did.
    """
    negs = [r for r in rows if r["outcome"] == "fail"]
    N = [trace_key(r) for r in negs]
    N_disc = [trace_key(r) for r in negs if classify(r)["class"] != CLASS_NO_OUTPUT]
    N_fs = [trace_key(r) for r in negs if classify(r)["class"] == CLASS_FALSE_SUCCESS]
    return {"N": N, "N_disc": N_disc, "N_fs": N_fs}


def denominator_populations(dens: dict[str, list[tuple]], population: str,
                            cfg: dict | None = None) -> dict[str, dict]:
    """For each denominator: its size, the size 6.3 preregistered, and what it is over.

    PREREGISTRATION.md 6.9 already requires every rate to print its counts. B3.2 adds the
    other half: a count is uninterpretable without the population it counts within, and the
    whole point of the eligibility rule is that the population changed.
    """
    cfg = cfg or freeze.load_config()
    declared = cfg.get("denominators") or {}
    out: dict[str, dict] = {}
    for name, keys in dens.items():
        spec = declared.get(name) or {}
        pre = spec.get("expected_n")
        out[name] = {
            "label": spec.get("label", name),
            "n": len(keys),
            "preregistered_n": pre,
            "population": population,
            "shrunk_by": None if pre is None else pre - len(keys),
        }
    return out


def numeric_value_error_keys(rows: list[dict]) -> list[tuple]:
    """The subclass the predicted-null control (4.6, 7.5, S3) is defined over."""
    return [
        trace_key(r) for r in rows
        if r["outcome"] == "fail" and classify(r)["subclass"] == SUB_NUMERIC
    ]


def near_miss_keys(rows: list[dict]) -> list[tuple]:
    """Sub-1% relative-error numeric false successes (6.5)."""
    return [trace_key(r) for r in rows if r["outcome"] == "fail" and classify(r)["near_miss"]]


def format_eligibility(part: dict) -> str:
    """The exclusion, rendered for a human. Never a bare denominator."""
    led = part["ledger"]
    L = [f"Eligibility (Amendment B3.2) — battery {part['battery_version']}",
         f"  population: {part['population']}",
         f"  policy on unattested records: {part['on_unattested']}", ""]
    for status in ELIGIBLE_STATUSES + INELIGIBLE_STATUSES:
        e = led[status]
        L.append(f"  {status:<26} n={e['n']:<4} negatives={e['negatives']:<3} "
                 f"positives={e['positives']:<3} false_successes={e['false_successes']}")
    if part["integrity_alarms"]:
        L += ["", "  INTEGRITY ALARM — a record disagrees with the battery its own run "
                  "declares:"]
        L += [f"    - {a}" for a in part["integrity_alarms"]]
    excluded = led["_excluded_records"]
    if excluded:
        L += ["", f"  {len(excluded)} excluded record(s):"]
        for e in excluded:
            L.append(f"    - {'/'.join(map(str, e['key']))}  [{e['outcome']}"
                     + (", false_success" if e["false_success"] else "")
                     + f"]  {e['status']}")
            L.append(f"        {e['detail']}")
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--eligibility", action="store_true",
                    help="print the Amendment B3.2 eligibility ledger and exit")
    args = ap.parse_args()

    rows, _ = load_records()
    if args.eligibility:
        print(format_eligibility(partition(rows)))
        return 0

    eligible, part = eligible_records(rows)
    print(format_eligibility(part))
    print()
    tax = taxonomy(eligible)
    print(json.dumps(tax, indent=1))
    disc = taxonomy_discrepancies(tax)
    if disc:
        print("\nDISCREPANCIES AGAINST PREREGISTRATION.md 2.1 — amendment required:")
        for d in disc:
            print(f"  - {d}")
    else:
        print("\ntaxonomy matches the preregistration exactly")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
