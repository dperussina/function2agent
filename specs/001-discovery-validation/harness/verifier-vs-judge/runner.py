"""SPIKE - E8 verifier-vs-judge. Delete after 2026-11-30. Do not import from product code.

The experiment driver.

Order of operations is PREREGISTRATION.md 7.1's construction order, enforced rather than
documented: freeze and verify the corpus, apply the Amendment B3.2 eligibility rule, select
and record the scoring set with its seed, confirm the derivation rules and judge prompt are
committed, print the projection — and only then make a call.

The eligibility step sits between the freeze and the selection on purpose. An ineligible
record must never reach a payload; subtracting it from a denominator afterwards would mean it
had already been scored against a question its agent was never asked.

    python3 runner.py --dry-run                    # whole pipeline, stub judge, $0.00
    python3 runner.py --dry-run --leak-audit       # per-trace pre-flight of the leak assertion
    python3 runner.py --arms b b_prime c1 --env-root /path/to/dotenv/tree   # priced

``--dry-run`` needs no credential and no network. It exercises payload assembly, the oracle-leak
assertion, truncation, repeats, verdict parsing, the ledger, every control, and the whole
analysis, so the run can be validated for zero dollars before anyone authorises spend.

Nothing here reads, prints, logs, or writes a credential value. The key is a local variable
handed to the client; only the *name* of the variable ever appears in output.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import analyze  # noqa: E402
import c1_schema  # noqa: E402
import c2_postcond  # noqa: E402
import controls  # noqa: E402
import corpus  # noqa: E402
import cost as cost_mod  # noqa: E402
import freeze  # noqa: E402
import judge as judge_mod  # noqa: E402
import redact  # noqa: E402
import select as select_mod  # noqa: E402

RESULTS_DIR = os.path.join(HERE, "results")

FINGERPRINT_FILES = (
    "runner.py", "judge.py", "redact.py", "corpus.py", "select.py", "cost.py",
    "metrics.py", "controls.py", "analyze.py", "c1_schema.py", "c2_postcond.py",
    "config.json", "corpus_freeze.json", "c2_derivations.json",
    os.path.join("prompts", "judge_v1.md"), "derivation-rules.md",
)


def harness_fingerprint() -> str:
    """Hash of every file that can change a result. Results with different fingerprints must
    not be pooled (research/11-validation-plan.md 9.3, adopted from ceiling-test/runner.py).

    The judge prompt and both derivation rule files are hashed in, so a prompt tuned after
    first sight of results — which PREREGISTRATION.md 7.2 forbids — produces a different
    fingerprint and cannot be pooled with what came before by accident.
    """
    h = hashlib.sha256()
    for rel in sorted(FINGERPRINT_FILES):
        p = os.path.join(HERE, rel)
        if not os.path.isfile(p):
            h.update(f"{rel}=ABSENT\n".encode())
            continue
        with open(p, "rb") as fh:
            h.update(rel.encode())
            h.update(fh.read())
    return h.hexdigest()[:16]


def _die(msg: str) -> None:
    sys.exit(f"\nREFUSING TO RUN\n\n{msg}\n")


#: Arms that may not be scored, and why. c1's clause C1.5 fabricates its only non-trivial
#: detection; PREREGISTRATION.md Amendment B5 quarantines the arm rather than repairing it,
#: because amendment rule 2 forbids altering a clause after seeing what it would catch.
QUARANTINED_ARMS = {"c1": c1_schema.QUARANTINE_NOTICE}


def refuse_quarantined_arms(arms) -> None:
    """Refuse before the freeze, the credential, the projection, and any call.

    Placed first on purpose. Everything downstream of here is machinery that makes a number;
    the point of the quarantine is that no number is available, so the refusal must precede
    the machinery rather than sit inside it.
    """
    named = [a for a in arms if a in QUARANTINED_ARMS]
    if named:
        _die("\n\n".join(QUARANTINED_ARMS[a] for a in named))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true",
                    help="stub judge, recorded fixtures, no API call, no credential, $0.00")
    ap.add_argument("--leak-audit", action="store_true",
                    help="pre-flight the oracle-leak assertion over every selected trace and "
                         "report, rather than abort, so the audit can be read before spending")
    ap.add_argument("--arms", nargs="+", default=["b", "b_prime", "c2"],
                    choices=["b", "b_prime", "c1", "c2"],
                    help="c1 is QUARANTINED (Amendment B5) and is refused if named. It stays "
                         "in the accepted values so that asking for it produces the "
                         "explanation rather than an argparse error.")
    ap.add_argument("--label", default="", help="short label for the results directory")
    ap.add_argument("--env-root", default=None,
                    help="directory tree holding the .env that defines the provider key; or "
                         "set F2A_ENV_ROOT. No default and no guessing. Unnecessary with "
                         "--dry-run, and unnecessary if the variable is already exported.")
    ap.add_argument("--app-base-url", default=None,
                    help="arm (c2) recomputation source: the application's own API")
    ap.add_argument("--state-snapshot", default=None,
                    help="arm (c2) recomputation source: a recorded state snapshot")
    ap.add_argument("--state-fixture", default=None,
                    help="arm (c2) recomputation source: a recorded state fixture. Defaults "
                         "to the committed fixtures/mealie_state.json, which is what makes "
                         "the whole run validatable offline for $0.00.")
    ap.add_argument("--max-usd", type=float, default=None,
                    help="override the run ceiling; may only lower it, never raise it above "
                         "the preregistered $9.00 (S7)")
    args = ap.parse_args()

    # -- the quarantine, checked before anything else so it cannot be reached by accident -
    refuse_quarantined_arms(args.arms)

    cfg = freeze.load_config()

    # -- 7.1(i): the corpus freeze. Refuses to start on any hash change. -----------------
    frozen = freeze.verify_or_die(cfg)

    # -- the leak assertion must be demonstrably alive before anything is spent ----------
    pre = controls.leak_assertion_selfcheck()
    for cr in pre:
        print(cr.line())
    if any(not c.ok for c in pre):
        _die("the oracle-leak assertion did not behave correctly on its own fixtures. "
             "Every result of this run would be void (PREREGISTRATION.md 4.6, S2).")

    # -- 7.1(iii): the rules and the prompt must be committed before any arm runs --------
    system, user_template, prompt_hash = judge_mod.load_prompt(cfg)
    if not os.path.isfile(os.path.join(HERE, "derivation-rules.md")):
        _die("derivation-rules.md is missing. PREREGISTRATION.md 7.1 requires the c1 and c2 "
             "derivation rules to be committed before any arm runs.")

    # -- B3.2: eligibility, applied BEFORE selection so nothing ineligible is ever scored -
    all_records, traces = corpus.load_records(cfg, verify=False)
    records, eligibility = corpus.eligible_records(all_records, cfg, frozen)
    print("\n" + corpus.format_eligibility(eligibility))
    if eligibility["integrity_alarms"]:
        _die("a record disagrees with the battery its own run declares. The battery did not "
             "change, so either the fixture drifted or expected.json was edited. Neither is "
             "ordinary battery churn and neither may be scored past.\n\n"
             + "\n".join(f"  - {a}" for a in eligibility["integrity_alarms"]))

    # -- 7.1(ii): the scoring set, seeded, recorded before selection ---------------------
    battery = corpus.load_battery(cfg)
    selection = select_mod.select(records, cfg, eligibility)
    by_key = {corpus.trace_key(t): t for t in traces}
    rec_by_key = {corpus.trace_key(r): r for r in records}
    sel_keys = [tuple(x) for x in selection["negatives"]] + \
               [tuple(x) for x in selection["positives"]]
    neg_set = {tuple(x) for x in selection["negatives"]}

    # -- the projection, printed before the first call (10) ------------------------------
    repeats = cfg["repeats"]
    proj = cost_mod.project([by_key[k] for k in sel_keys], cfg,
                            repeats["negatives"], repeats["positives"],
                            {k: (k in neg_set) for k in sel_keys})
    print(cost_mod.format_projection(proj, cfg))

    pos_repeats = repeats["positives"]
    contingency = False
    if proj["contingency_fires"]:
        pos_repeats = repeats["positives_under_contingency"]
        contingency = True
        proj = cost_mod.project([by_key[k] for k in sel_keys], cfg,
                                repeats["negatives"], pos_repeats,
                                {k: (k in neg_set) for k in sel_keys})
        print("\n  contingency applied — positives drop to "
              f"{pos_repeats} repeats (pre-authorised, 10; not an amendment)")
        print(cost_mod.format_projection(proj, cfg))

    ceiling = cfg["cost"]["hard_ceiling_usd"]
    if args.max_usd is not None:
        if args.max_usd > ceiling:
            _die(f"--max-usd ${args.max_usd:.2f} exceeds the preregistered ${ceiling:.2f} "
                 "ceiling (S7). The ceiling may be lowered, never raised.")
        ceiling = args.max_usd
    if not args.dry_run and proj["arms"]["b"]["total_usd"] + proj["arms"]["b_prime"]["total_usd"] \
            > ceiling:
        _die(f"the projected judge spend ${proj['judge_subtotal_usd']:.2f} already exceeds the "
             f"${ceiling:.2f} ceiling before the repair reserve. S7 would abort mid-run and "
             "leave a partially scored set; decide the scope before spending, not during.")

    # -- arm (c2)'s recomputation source, or a loud not_run ------------------------------
    c2_source = None
    if "c2" in args.arms:
        try:
            c2_source = c2_postcond.open_source(
                args.app_base_url, args.state_fixture or args.state_snapshot)
            print(f"\n  arm (c2) recomputation source: {c2_source.describe()}")
        except c2_postcond.NoRecomputationSource as exc:
            if args.dry_run:
                print(f"\n  arm (c2): not_run — {str(exc).splitlines()[0]}")
            else:
                _die(str(exc))
    derivations = c2_postcond.load_derivations()
    if "c2" in args.arms and not derivations.get("derivations"):
        msg = ("c2_derivations.json records no derivation. Arm (c2) would return "
               "`unverifiable` for every trace, which is not the same finding as "
               "'the contract could not be derived'.")
        if args.dry_run:
            print(f"\n  arm (c2): {msg}")
        else:
            _die(msg + "\nApply derivation-rules.md 'c2' and commit the file before running.")

    # -- run identity --------------------------------------------------------------------
    run_id = datetime.datetime.now().strftime("%Y%m%dT%H%M%S") + \
        (f"-{args.label}" if args.label else ("-dryrun" if args.dry_run else ""))
    out_dir = os.path.join(RESULTS_DIR, run_id)
    os.makedirs(out_dir, exist_ok=True)

    manifest = {
        "run_id": run_id,
        "started": datetime.datetime.now().isoformat(timespec="seconds"),
        "experiment": "E8 verifier-vs-judge",
        "preregistration_sha256": _sha(os.path.join(HERE, "PREREGISTRATION.md")),
        "harness_fingerprint": harness_fingerprint(),
        "harness_version": cfg["harness_version"],
        "dry_run": args.dry_run,
        "arms": args.arms,
        "judge_arms": {k: {kk: vv for kk, vv in v.items() if not kk.startswith("_")}
                       for k, v in cfg["judge_arms"].items()},
        "judge_prompt_sha256_16": prompt_hash,
        "derivation_rules_sha256_16": _sha(os.path.join(HERE, "derivation-rules.md")),
        "c2_derivations_sha256_16": c2_postcond.derivations_hash(),
        "pricing_usd_per_mtok": {k: v["price_usd_per_mtok"] for k, v in cfg["judge_arms"].items()},
        "budgets": {
            "hard_ceiling_usd": cfg["cost"]["hard_ceiling_usd"],
            "effective_ceiling_usd": ceiling,
            "budget_usd": cfg["cost"]["budget_usd"],
            "repair_reserve_usd": cfg["cost"]["repair_reserve_usd"],
            "contingency_trigger_usd": cfg["cost"]["contingency_trigger_usd"],
            "contingency_applied": contingency,
            "repeats_negatives": repeats["negatives"],
            "repeats_positives": pos_repeats,
            "transcript_truncation_tokens": cfg["cost"]["transcript_truncation_tokens"],
        },
        "projection": {k: v for k, v in proj.items() if k != "per_trace"},
        "corpus_freeze": {
            "scope_runs": frozen["scope_runs"],
            "shape": frozen["shape"],
            "files": frozen["files"],
            "battery": frozen.get("battery"),
        },
        "eligibility": {
            "rule": eligibility["rule"],
            "battery_version": eligibility["battery_version"],
            "on_unattested": eligibility["on_unattested"],
            "population": eligibility["population"],
            "by_status": eligibility["by_status"],
            "ledger": eligibility["ledger"],
            "integrity_alarms": eligibility["integrity_alarms"],
        },
        "scoring_set": selection,
        "stop_conditions": cfg["stop_conditions"],
        "_credentials": (
            "resolved via ../provider-credentials/envroot.py: the process environment, else a "
            "dotenv tree named with --env-root / F2A_ENV_ROOT, no default. No credential value "
            "appears in this manifest, in any log, in any trace, or in any prompt."
        ),
    }
    _write(os.path.join(out_dir, "manifest.json"), manifest)
    print(f"\nrun {run_id}   harness {manifest['harness_fingerprint']}   "
          f"prompt {prompt_hash}   dry_run={args.dry_run}")

    # -- leak pre-flight -------------------------------------------------------------------
    if args.leak_audit:
        return _leak_audit(cfg, sel_keys, by_key, rec_by_key, battery, system,
                           user_template, out_dir)

    # -- scoring ---------------------------------------------------------------------------
    ledger = cost_mod.Ledger(ceiling_usd=ceiling)
    client = judge_mod.StubJudge(os.path.join(HERE, "fixtures", "stub_verdicts.json")) \
        if args.dry_run else judge_mod.AnthropicClient(
            judge_mod.load_api_key(cfg, args.env_root))

    calls_path = os.path.join(out_dir, "judge_calls.jsonl")
    verdicts_path = os.path.join(out_dir, "verdicts.jsonl")
    judge_by_arm: dict[str, dict[tuple, dict]] = {}
    verifier_by_arm: dict[str, dict[tuple, dict]] = {}
    schema = c1_schema.load_schema(cfg) if "c1" in args.arms else None

    try:
        for k in sel_keys:
            trace, record = by_key[k], rec_by_key[k]
            prompt = (battery.get(record["task_id"]) or {}).get("prompt", "")
            view = redact.scoring_view(trace, prompt)
            reps = repeats["negatives"] if k in neg_set else pos_repeats

            for arm in ("b", "b_prime"):
                if arm not in args.arms:
                    continue
                calls = judge_mod.score_trace(client, arm, cfg, view, record, system,
                                              user_template, reps, ledger, priced=not args.dry_run)
                _append(calls_path, calls)
                agg = judge_mod.aggregate(calls)
                agg["succeeded_per_repeat"] = [c["succeeded"] for c in calls]
                judge_by_arm.setdefault(arm, {})[k] = agg

            if "c1" in args.arms:
                verifier_by_arm.setdefault("c1", {})[k] = c1_schema.verify(view, record, schema)
            if "c2" in args.arms:
                verifier_by_arm.setdefault("c2", {})[k] = c2_postcond.verify(
                    view, record, c2_source, derivations)

            _append(verdicts_path, [{
                "key": list(k),
                **{f"judge_{a}": judge_by_arm.get(a, {}).get(k) for a in ("b", "b_prime")},
                **{a: verifier_by_arm.get(a, {}).get(k) for a in ("c1", "c2")},
            }])
    except redact.OracleLeak as exc:
        _write(os.path.join(out_dir, "ABORTED.json"),
               {"reason": "S2 oracle-leak assertion fired", "detail": str(exc),
                "calls_made": ledger.calls, "spent_usd": round(ledger.spent_usd, 6),
                "action": "Discard every call in this run. Investigate before any re-run."})
        print(f"\n{exc}\n\nS2 — ABORTED after {ledger.calls} call(s), "
              f"${ledger.spent_usd:.4f}. Every call in this run is discarded.")
        return 3
    except cost_mod.BudgetExceeded as exc:
        print(f"\nS7 — {exc}")
        _write(os.path.join(out_dir, "HALTED.json"),
               {"reason": "S7 spend ceiling", "detail": str(exc),
                "calls_made": ledger.calls, "spent_usd": round(ledger.spent_usd, 6)})

    # -- analysis --------------------------------------------------------------------------
    out = analyze.analyse(cfg, records, selection, judge_by_arm, verifier_by_arm, eligibility)
    out["spend"] = {"spent_usd": round(ledger.spent_usd, 6), "calls": ledger.calls,
                    "by_arm": {k: round(v, 6) for k, v in ledger.by_arm.items()},
                    "ceiling_usd": ceiling, "dry_run": args.dry_run}
    _write(os.path.join(out_dir, "analysis.json"), out)
    report = analyze.format_report(out)
    with open(os.path.join(out_dir, "report.md"), "w", encoding="utf-8") as fh:
        fh.write(report)
    print("\n" + report)
    print(f"\nspent ${ledger.spent_usd:.4f} of ${ceiling:.2f} in {ledger.calls} call(s)"
          + ("  [dry run — no API call was made]" if args.dry_run else ""))
    print(f"results: {out_dir}")
    return 1 if out["fatal"] else 0


def _leak_audit(cfg, sel_keys, by_key, rec_by_key, battery, system, user_template, out_dir) -> int:
    """Report which traces the leak assertion would abort on, instead of aborting.

    Every abort is a real leak that must be understood before the run, not an inconvenience to
    be flagged around. This exists so that understanding costs nothing.
    """
    findings = []
    for k in sel_keys:
        trace, record = by_key[k], rec_by_key[k]
        prompt = (battery.get(record["task_id"]) or {}).get("prompt", "")
        try:
            view = redact.scoring_view(trace, prompt)
            judge_mod.build_payload(view, record, system, user_template, cfg)
        except redact.OracleLeak as exc:
            findings.append({"key": list(k), "complaint": str(exc).splitlines()[0]})
    _write(os.path.join(out_dir, "leak_audit.json"),
           {"n_traces": len(sel_keys), "n_would_abort": len(findings), "findings": findings})
    print(f"\nleak pre-flight: {len(findings)} of {len(sel_keys)} selected traces would abort")
    for f in findings[:20]:
        print(f"  {f['key']}  {f['complaint']}")
    if not findings:
        print("  none — the assertion is silent on every selected trace, and controls.py "
              "proves it is not silent on a leaking one")
    return 0


def _sha(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()[:16]


def _write(path: str, obj) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=1, default=str)


def _append(path: str, rows: list[dict]) -> None:
    with open(path, "a", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, default=str) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
