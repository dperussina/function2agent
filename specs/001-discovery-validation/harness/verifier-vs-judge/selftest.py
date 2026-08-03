#!/usr/bin/env python3
"""SPIKE - E8 verifier-vs-judge. Delete after 2026-11-30. Do not import from product code.

Prove the checks fire, and prove they stay quiet.

This repository has shipped a validator whose regex never matched and therefore passed
everything, and a write check that credited an agent holding no tools. A green run against
the corpus is not evidence that a check works. **This is the evidence.**

Two directions for every check, both required:

  known-bad    the check must fire, on input planted to trigger exactly it. A check that
               produces nothing here is broken or vacuous, whatever it looks like in source.

  known-good   the check must be silent, on input that contains every construct known to
               produce a false positive: the English words "reason" and "outcome" in agent
               prose, the correct answer inside the agent's own submission, the digits of an
               expected value inside a run-id timestamp, and a tool result carrying the
               application's true data.

    python3 selftest.py         # both directions
    python3 selftest.py -v      # plus the detail of each case

No credential and no network are needed, and nothing here spends money.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from typing import Any

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import c1_schema  # noqa: E402
import c2_postcond  # noqa: E402
import controls  # noqa: E402
import corpus  # noqa: E402
import cost as cost_mod  # noqa: E402
import freeze  # noqa: E402
import judge as judge_mod  # noqa: E402
import metrics  # noqa: E402
import recompute_source  # noqa: E402
import redact  # noqa: E402
import select as select_mod  # noqa: E402

FIX = os.path.join(HERE, "fixtures")

RESULTS: list[tuple[str, str, bool, str]] = []


def check(group: str, name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((group, name, bool(ok), detail))


def _load(name: str) -> dict:
    with open(os.path.join(FIX, name), encoding="utf-8") as fh:
        return json.load(fh)


def _hydrate(obj: Any, record: dict) -> Any:
    """Turn a JSON fixture into a payload: 'AGENT:' prefixes become redact.AgentText,
    and {"$RECORD": true} becomes the whole oracle record."""
    if isinstance(obj, dict):
        if obj.get("$RECORD") is True:
            return record
        return {k: _hydrate(v, record) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_hydrate(v, record) for v in obj]
    if isinstance(obj, str) and obj.startswith("AGENT:"):
        return redact.AgentText(obj[len("AGENT:"):])
    return obj


# ------------------------------------------------------------------ 1. oracle-leak assertion

def test_leak_assertion() -> None:
    bad = _load("leak-bad.json")
    for case in bad["cases"]:
        payload = _hydrate(case["payload"], bad["_record"])
        fired = redact.leak_audit(payload, bad["_record"], "selftest") is not None
        check("leak-bad", case["name"], fired,
              case["why"] if fired else f"DID NOT FIRE — {case['why']}")

    good = _load("leak-good.json")
    for case in good["cases"]:
        payload = _hydrate(case["payload"], good["_record"])
        complaint = redact.leak_audit(payload, good["_record"], "selftest")
        check("leak-good", case["name"], complaint is None,
              case["why"] if complaint is None else f"FALSE POSITIVE — {complaint}")

    # the whitelist itself must reject an oracle field rather than pass it through
    try:
        redact.scoring_view({"expected": 1, "transcript": []}, "p", ("expected", "transcript"))
        check("leak-bad", "whitelist-rejects-oracle-field", False,
              "scoring_view admitted `expected` when asked to")
    except redact.OracleLeak:
        check("leak-bad", "whitelist-rejects-oracle-field", True,
              "scoring_view refuses to project an oracle field even when named")

    # scorer_content must drop bookkeeping, so identifiers cannot become scorer input
    content = redact.scorer_content(
        {"run_id": "r", "task_id": "t", "arm": "A", "attempt": 1,
         "task_prompt": "p", "submitted": "s", "transcript": [], "tool_calls": []})
    check("leak-good", "scorer-content-drops-bookkeeping",
          not (set(content) & set(redact.BOOKKEEPING_FIELDS)),
          f"scorer sees {sorted(content)}")


# ------------------------------------------------------------------ 2. corpus freeze refusal

def test_freeze_refusal() -> None:
    root = freeze.corpus_root()
    frozen = freeze.load_freeze()

    check("freeze", "intact-corpus-verifies", not freeze.verify(root, frozen),
          "the committed freeze matches the corpus on disk")

    tampered = json.loads(json.dumps(frozen))
    run = freeze.SCOPE_RUNS[0]
    tampered["files"][run]["results.jsonl"] = "0" * 64
    problems = freeze.verify(root, tampered)
    check("freeze", "changed-hash-refuses",
          any("HASH CHANGED" in p for p in problems),
          f"{len(problems)} complaint(s) on a tampered hash")

    dropped = json.loads(json.dumps(frozen))
    dropped["files"][run].pop("traces.jsonl")
    check("freeze", "missing-hash-refuses",
          any("no frozen hash" in p for p in freeze.verify(root, dropped)),
          "a file with no recorded hash is refused, not skipped")

    check("freeze", "out-of-scope-run-excluded",
          all(not r.startswith(freeze.KNOWN_OUT_OF_SCOPE_PREFIX) for r in freeze.SCOPE_RUNS)
          and freeze.KNOWN_OUT_OF_SCOPE_PREFIX
          in " ".join(os.listdir(root)),
          "the in-progress run exists on disk and is not in scope")

    grown = json.loads(json.dumps(frozen))
    grown["shape"]["records"] = 304
    check("freeze", "shape-drift-refuses",
          any("shape" in p for p in freeze.verify(root, grown)),
          "a corpus that grew is refused even if every hash still matched")


# ------------------------------------------------------------------ 3. taxonomy classifier

def test_taxonomy() -> None:
    planted = _load("planted.json")["taxonomy_records"]
    for i, rec in enumerate(planted):
        got = corpus.classify(rec)
        ok = (got["class"] == rec["_want_class"]
              and got["subclass"] == rec["_want_subclass"]
              and got["near_miss"] == rec["_want_near_miss"])
        check("taxonomy", f"planted[{i}] {rec['_want_class'] or 'positive'}"
                          f"/{rec['_want_subclass'] or '-'}", ok,
              f"got class={got['class']} subclass={got['subclass']} near={got['near_miss']}")

    fake = {"n_negatives": 20, "classes": {"no_output": 7, "protocol": 2, "false_success": 11},
            "false_success_subclasses": {"numeric_value_error": 8, "set_cardinality_error": 3},
            "near_miss_n": 2,
            "preregistered": {"n_negatives": 20, "no_output": 7, "protocol": 2,
                              "false_success": 11, "numeric_value_error": 8,
                              "set_cardinality_error": 3, "near_miss_n": 2}}
    check("taxonomy", "discrepancy-silent-when-matching",
          not corpus.taxonomy_discrepancies(fake),
          "no complaint when the measured split equals the preregistered one")
    fake["false_success_subclasses"]["numeric_value_error"] = 9
    check("taxonomy", "discrepancy-fires-on-mismatch",
          bool(corpus.taxonomy_discrepancies(fake)),
          "a split that disagrees with the preregistration is reported")


# ------------------------------------------------------------------ 4. label-shuffle control

def test_label_shuffle() -> None:
    scores = [i / 40 for i in range(40)]
    labels = [1] * 20 + [0] * 20
    good = controls.label_shuffle(scores, labels, metrics.auroc, 400)
    check("controls", "label-shuffle-quiet-on-correct-auroc", good.ok, good.detail)

    def broken_auroc(_s, _l):
        return 0.92  # a metric that ignores its labels entirely

    bad = controls.label_shuffle(scores, labels, broken_auroc, 200)
    check("controls", "label-shuffle-fires-on-broken-auroc", not bad.ok and bad.fatal,
          "a metric that ignores its labels does not centre on 0.500 and voids the run")


# ------------------------------------------------------------------ 5. constant anchors

def test_constant_anchors() -> None:
    ok = controls.check_constant_anchors(0.5, 1.0, 0.0, 0.0, 10)
    check("controls", "anchors-quiet-when-correct", all(c.ok for c in ok),
          "; ".join(c.name for c in ok if not c.ok) or "all four anchors hold")

    broken = controls.check_constant_anchors(0.5, 0.04, 0.3, 0.2, 10)
    fired = {c.name for c in broken if not c.ok}
    check("controls", "anchors-fire-on-degenerate-metric",
          {"constant-fail FPR", "constant-pass MD", "constant-pass FPR"} <= fired,
          f"fired: {sorted(fired)}")

    check("controls", "constant-fail-verifier-fails-everything",
          controls.constant_fail_verifier({}, {})["verdict"] == "fail", "")
    check("controls", "constant-pass-verifier-passes-everything",
          controls.constant_pass_verifier({}, {})["verdict"] == "pass", "")


# ------------------------------------------------------------------ 6. predicted null

def test_predicted_null() -> None:
    numeric = [("r", "T.001", "A", 1), ("r", "T.002", "A", 1)]
    blind = {k: {"verdict": "unverifiable", "clause": "C1.7"} for k in numeric}
    res = controls.predicted_null(blind, numeric, 8)
    check("controls", "predicted-null-quiet-on-blind-c1", res.ok,
          "a c1 that returns unverifiable on numeric errors satisfies the prediction")
    check("controls", "predicted-null-reports-count-mismatch",
          "amendment required" in res.detail,
          "the 8-vs-measured count disagreement is surfaced, not silently absorbed")

    cheating = {k: {"verdict": "fail", "clause": "C1.3"} for k in numeric}
    res2 = controls.predicted_null(cheating, numeric, 8)
    check("controls", "predicted-null-fires-on-cheating-c1",
          (not res2.ok) and res2.fatal and "VOID c1" in res2.detail,
          "a c1 that detects a numeric value error voids the arm (S3)")

    absent = controls.predicted_null({}, numeric, 8)
    check("controls", "predicted-null-reports-not-run-when-c1-absent",
          (not absent.ran) and absent.verdict() == "NOT RUN" and "NOT RUN" in absent.detail,
          "with c1 quarantined the control has no verdicts to test; it must not read as a pass")
    check("controls", "predicted-null-not-run-is-not-fatal",
          not absent.fatal,
          "an undischarged S3 stops the arm being cited, not the run being analysed")


# ------------------------------------------------------------------ 7. c1 clauses

def test_c1_clauses() -> None:
    cfg = freeze.load_config()
    schema = c1_schema.load_schema(cfg)
    record = {"run_id": "r", "task_id": "X.001", "arm": "A", "attempt": 1,
              "expected": None, "reason": None}
    for t in _load("planted.json")["c1_traces"]:
        view = {k: v for k, v in t.items() if not k.startswith("_")}
        # The quarantined walk, not `verify`. These assertions exist to prove the clauses were
        # not edited when the arm was quarantined; they are not results (Amendment B5).
        got = c1_schema.verify_clauses_quarantined(view, record, schema)
        ok = got["verdict"] == t["_want_verdict"] and got["clause"] == t["_want_clause"]
        check("c1", t["_name"], ok,
              f"want {t['_want_verdict']}/{t['_want_clause']}, "
              f"got {got['verdict']}/{got['clause']}")

    check("c1", "every-corpus-tool-is-mapped-or-declared",
          "bash" not in c1_schema.TOOL_OPERATIONS,
          "the shell tool has no single declared operation and is resolved per call, not mapped")

    check("c1", "schema-declares-numeric-types",
          "number" in schema.response_types("/api/recipes"),
          "if the schema walk under-reports types, C1.3 turns well-typed numbers into "
          "detections and fakes the predicted-null failure")

    check("c1", "rules-contain-no-task-identifier",
          not _mentions_task_ids(os.path.join(HERE, "derivation-rules.md")),
          "protocol commitment 3: a reviewer must be able to read the rules without "
          "learning anything about the battery")
    check("c1", "c1-source-contains-no-task-identifier",
          not _mentions_task_ids(os.path.join(HERE, "c1_schema.py")), "")


# ------------------------------------------------------------------ 7a. the c1 quarantine

def test_c1_quarantine() -> None:
    """Prove the quarantine holds: c1 cannot be scored, and the pointer survives a refactor.

    The failure mode this exists to prevent is not a wrong number. It is someone finding this
    tree, running the arm, and believing its output. Every check below is a way that could
    still happen.
    """
    import runner  # noqa: PLC0415

    cfg = freeze.load_config()
    schema = c1_schema.load_schema(cfg)
    record = {"run_id": "r", "task_id": "X.001", "arm": "A", "attempt": 1,
              "expected": None, "reason": None}

    raised = None
    try:
        c1_schema.verify({"submitted": "3.23", "tool_calls": [], "transcript": []},
                         record, schema)
    except c1_schema.Quarantined as exc:
        raised = exc
    except Exception as exc:  # noqa: BLE001
        raised = exc
    check("quarantine", "c1-verify-raises", isinstance(raised, c1_schema.Quarantined),
          f"c1_schema.verify must raise Quarantined; got {type(raised).__name__}")
    check("quarantine", "c1-verify-returns-no-verdict", raised is not None,
          "an `unverifiable` return would flow into UNV_c1 and look like a measurement")
    check("quarantine", "quarantine-notice-names-the-finding",
          "findings/015-verifier-vs-judge-not-run.md" in c1_schema.QUARANTINE_NOTICE
          and "Amendment B5" in c1_schema.QUARANTINE_NOTICE,
          "the message must carry the pointer, or the refusal is a dead end")
    check("quarantine", "quarantine-notice-is-what-is-raised",
          "findings/015-verifier-vs-judge-not-run.md" in str(raised),
          "a refusal that does not print the pointer sends the reader to the source")

    referenced = os.path.join(HERE, "..", "..", "findings",
                              "015-verifier-vs-judge-not-run.md")
    check("quarantine", "the-finding-the-notice-points-at-exists",
          os.path.isfile(referenced),
          "a pointer to a file that does not exist is worse than no pointer")

    check("quarantine", "runner-refuses-c1",
          _exits(runner.refuse_quarantined_arms, ["b", "c1", "c2"]),
          "naming c1 in --arms must exit before the freeze, the credential and any call")
    check("quarantine", "runner-allows-the-live-arms",
          not _exits(runner.refuse_quarantined_arms, ["b", "b_prime", "c2"]),
          "the quarantine must not block the arms that can still be scored")
    check("quarantine", "c1-not-in-runner-default-arms",
          "c1" not in _runner_default_arms(),
          "a default that includes c1 makes the documented dry run refuse to start")
    check("quarantine", "c1-still-an-accepted-value",
          "c1" in _runner_arm_choices(),
          "removing it from the choices would answer a reasonable request with an argparse "
          "error instead of the explanation")

    # Amendment rule 2: the clauses may not be edited after their catches are visible.
    check("quarantine", "no-clause-was-removed", c1_schema.CLAUSES ==
          ("C1.1", "C1.2", "C1.3", "C1.4", "C1.5", "C1.6"),
          "quarantining the arm must not double as a silent clause edit")
    walk = c1_schema.verify_clauses_quarantined.__code__.co_names
    check("quarantine", "the-preregistered-walk-is-intact",
          all(n in walk for n in ("_c1_1_output_presence", "_c1_2_status_class",
                                  "_c1_3_type_conformance", "_c1_4_enum_membership",
                                  "_c1_5_cardinality", "_c1_6_abstention")),
          "all six clauses are still dispatched, in the preregistered order, unrepaired")
    check("quarantine", "c1-5-is-not-repaired",
          "totals[-1]" in _source(os.path.join(HERE, "c1_schema.py")).replace(" ", ""),
          "C1.5 still takes the last total in the transcript — the defect is recorded, not "
          "fixed (amendment rule 2)")


def _exits(fn, *args) -> bool:
    try:
        fn(*args)
    except SystemExit:
        return True
    return False


def _source(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _runner_arm_action() -> str:
    """The source text of runner.py's ``--arms`` declaration.

    Read from source rather than restated here. A check that copies the default cannot notice
    the default moving, which is the whole class of failure this file exists to catch.
    """
    src = _source(os.path.join(HERE, "runner.py"))
    return src.split('ap.add_argument("--arms"', 1)[1].split("ap.add_argument", 1)[0]


def _runner_default_arms() -> list[str]:
    seg = _runner_arm_action()
    body = seg.split("default=[", 1)[1].split("]", 1)[0]
    return [x.strip().strip('"\'') for x in body.split(",") if x.strip()]


def _runner_arm_choices() -> list[str]:
    seg = _runner_arm_action()
    body = seg.split("choices=[", 1)[1].split("]", 1)[0]
    return [x.strip().strip('"\'') for x in body.split(",") if x.strip()]


def _mentions_task_ids(path: str) -> bool:
    import re
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    return bool(re.search(r"\b(?:R1|R2|R3|R4|NM|W1|N)\.\d{3}\b", text))


# ------------------------------------------------------------------ 8. c2

def test_c2() -> None:
    try:
        c2_postcond.RecomputationSource(None, None)
        check("c2", "refuses-without-source", False, "constructed with no source")
    except c2_postcond.NoRecomputationSource:
        check("c2", "refuses-without-source", True,
              "no live app and no snapshot means not_run, never a corpus of unverifiables")

    record = {"run_id": "r", "task_id": "X", "arm": "A", "attempt": 1,
              "expected": 5, "reason": None}
    got = c2_postcond.verify({"task_prompt": "anything"}, record, None)
    check("c2", "no-source-is-not_run", got["verdict"] == "not_run", got["detail"])

    # The offline fixture, never a live instance: the whole experiment stays validatable at
    # zero cost, and the self-test cannot fail because a container is down.
    src = recompute_source.open_source()
    got = c2_postcond.verify({"task_prompt": "an underived request"}, record, src,
                             {"derivations": {}})
    check("c2", "no-derivation-is-unverifiable",
          got["verdict"] == "unverifiable" and got["status"] == "provisional",
          "an underived request is provisional with provenance, never a pass and never a fail")

    for sub, rec_, comp, dp, want in (
        (5, 5, "exact_int", None, True),
        ("5", 6, "exact_int", None, False),
        (["a", "B"], ["b", "A"], "exact_set", None, True),
        ([], ["a"], "exact_set", None, False),
        ("3.23", 3.201754, "exact_decimal", None, False),
        ("3.201754", 3.201754, "exact_decimal", None, True),
        ("3.20", 3.201754, "decimal_at_declared_precision", 2, True),
        ("3.23", 3.201754, "decimal_at_declared_precision", 2, False),
        ("21, 0", [21, 0], "sequence", None, True),
        ("0", [21, 0], "sequence", None, False),
    ):
        ok, detail = c2_postcond.compare(sub, rec_, comp, dp)
        check("c2", f"compare {comp} {sub!r} vs {rec_!r}", ok == want, detail)

    check("c2", "declared-precision-refuses-rather-than-defaults",
          _raises(c2_postcond.DerivationInvalid, c2_postcond.compare,
                  "3.20", 3.201754, "decimal_at_declared_precision", None),
          "the ladder's last rung is a refusal; a missing precision may not become a default")

    check("c2", "derivations-file-has-no-task-identifier",
          not _mentions_task_ids(os.path.join(HERE, "c2_derivations.json")), "")
    check("c2", "derivation-rules-have-no-task-identifier",
          not _mentions_task_ids(os.path.join(HERE, "derivation-rules.md")), "")

    cfg = freeze.load_config()
    fields = c2_postcond.declared_field_names(
        os.path.abspath(os.path.join(HERE, cfg["battery"]["openapi_rel"])))
    audit = c2_postcond.audit_all(c2_postcond.load_derivations(),
                                  corpus.load_battery(cfg), fields)
    check("c2", "every-derivation-validates", audit["n_invalid"] == 0,
          json.dumps(audit["problems"])[:300])
    check("c2", "every-request-in-the-battery-has-a-derivation",
          audit["n_derivations"] == len(corpus.load_battery(cfg)),
          f"{audit['n_derivations']} derivations for "
          f"{len(corpus.load_battery(cfg))} requests; deriving only where success was "
          f"expected would select MD_c2's numerator")

    check("c2", "precision-ladder-rung-P1-is-empty-on-this-target",
          not _schema_declares_precision(),
          "openapi.json declares no multipleOf and no numeric format; Amendment B2")


def _raises(exc: type, fn, *a) -> bool:
    try:
        fn(*a)
    except exc:
        return True
    except Exception:  # noqa: BLE001
        return False
    return False


def _schema_declares_precision() -> bool:
    """True if the target's OpenAPI document declares any numeric precision. Amendment B2."""
    path = os.path.join(HERE, "..", "ceiling-test", "groundtruth", "openapi.json")
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)

    def walk(node) -> bool:
        if isinstance(node, dict):
            if "multipleOf" in node:
                return True
            if node.get("type") in ("number", "integer") and "format" in node:
                return True
            return any(walk(v) for v in node.values())
        if isinstance(node, list):
            return any(walk(v) for v in node)
        return False

    return walk(doc.get("components", {}))


# --------------------------------------------------- 8b. c2 rules: fire and stay silent

def test_c2_rules_fire_and_stay_silent() -> None:
    """Every c2 rule family must be shown to fire on a planted-bad answer and stay silent on
    a known-good one.

    A clause that cannot fire is indistinguishable from one that correctly finds nothing, so
    an unfired rule is not evidence of anything. The known-good answer is the arm's **own**
    recomputation rendered back as a submission — never a value read from ``expected.json``,
    which would make the test an identity. The planted-bad answer is that same recomputation
    perturbed by a rule-appropriate mutation.
    """
    src = recompute_source.open_source()
    derivations = c2_postcond.load_derivations()
    entries = derivations["derivations"]

    fired: dict[str, bool] = {}
    silent: dict[str, bool] = {}
    for entry in entries.values():
        rule = entry.get("rule")
        if not rule or entry.get("refused"):
            continue
        try:
            recomputed = c2_postcond._recompute(entry, src)
        except Exception:  # noqa: BLE001
            continue
        if recomputed is None:
            continue

        good = _render_submission(recomputed, entry["comparison"])
        bad = _perturb(recomputed, entry["comparison"])
        if bad is None:
            continue

        one = {"derivations": {c2_postcond.request_signature(entry["request"]): entry}}
        record = {"run_id": "r", "task_id": "X", "arm": "A", "attempt": 1}
        g = c2_postcond.verify({"task_prompt": entry["request"], "submitted": good},
                               record, src, one)
        b = c2_postcond.verify({"task_prompt": entry["request"], "submitted": bad},
                               record, src, one)
        silent[rule] = silent.get(rule, True) and g["verdict"] == "pass"
        fired[rule] = fired.get(rule, False) or b["verdict"] == "fail"

    for rule in sorted(fired):
        check("c2-rules", f"{rule} fires on planted-bad", fired[rule],
              "a rule that cannot fire is indistinguishable from one that finds nothing")
        check("c2-rules", f"{rule} silent on known-good", silent.get(rule, False),
              "the arm must not fail its own recomputation")

    check("c2-rules", "every-rule-family-is-exercised",
          len(fired) == len({e["rule"] for e in entries.values()
                             if e.get("rule") and not e.get("refused")}),
          f"{len(fired)} rule families exercised")

    refusals = [e for e in entries.values() if e.get("refused")]
    record = {"run_id": "r", "task_id": "X", "arm": "A", "attempt": 1}
    ok = all(
        c2_postcond.verify({"task_prompt": e["request"], "submitted": "42"},
                           record, src, {"derivations": {
                               c2_postcond.request_signature(e["request"]): e}})["verdict"]
        == "unverifiable"
        for e in refusals
    )
    check("c2-rules", "refusals-are-unverifiable-never-fail", ok,
          f"{len(refusals)} refusals return unverifiable, keeping MD_c2's numerator honest")


def _render_submission(value, comparison: str) -> str:
    if comparison == "sequence":
        return ", ".join(str(v) for v in value)
    if comparison == "exact_set":
        return ", ".join(str(v) for v in value)
    return str(value)


def _perturb(value, comparison: str):
    """A rule-appropriate wrong answer, derived from the recomputation and nothing else."""
    if comparison == "sequence":
        return ", ".join(str(_bump(v)) for v in value)
    if comparison == "exact_set":
        items = list(value)
        return ", ".join(str(v) for v in items[:-1]) if len(items) > 1 else "nothing"
    if comparison == "exact_text":
        return f"{value} (not the answer)"
    return str(_bump(value))


def _bump(v):
    try:
        n = float(v)
    except (TypeError, ValueError):
        return f"{v}x"
    return int(n) + 1 if float(n).is_integer() else round(n + 0.03, 6)


# ------------------------------------------------------------------ 9. metrics

def test_metrics() -> None:
    check("metrics", "auroc-perfect-separation",
          metrics.auroc([0.1, 0.2, 0.8, 0.9], [0, 0, 1, 1]) == 1.0, "")
    check("metrics", "auroc-perfect-inversion",
          metrics.auroc([0.9, 0.8, 0.2, 0.1], [0, 0, 1, 1]) == 0.0,
          "the anti-correlated direction the constitutional gate is looking for")
    check("metrics", "auroc-all-ties-is-half",
          metrics.auroc([0.5] * 4, [0, 0, 1, 1]) == 0.5,
          "mid-rank handling; a degenerate boolean judge lands here")
    check("metrics", "auroc-undefined-with-one-class",
          metrics.auroc([0.1, 0.2], [1, 1]) is None, "")

    p = metrics.Proportion(2, 20, "MD_test", {"R4": 2})
    lo, hi = p.wilson()
    check("metrics", "wilson-brackets-the-point", lo < 0.10 < hi,
          f"2/20 = 10.0 pp, Wilson {lo * 100:.1f}–{hi * 100:.1f} pp")
    check("metrics", "sentence-carries-counts-interval-families",
          all(s in p.sentence() for s in ("2/20", "Wilson", "R4 2")),
          "PREREGISTRATION.md 6.9 requires all three in the same sentence")

    keys = [("r", f"T{i}", "A", 1) for i in range(4)]
    judge_all_fail = {k: {"verdict": "fail"} for k in keys}
    vm = metrics.verifier_metrics("x", keys[:2], keys[2:], {}, judge_all_fail,
                                  {k: "R4" for k in keys}, keys)
    check("metrics", "foc-undefined-not-zero-when-no-fail-open", vm["FOC"] is None,
          "reported as undefined rather than as 0 or 1 (6.2)")

    check("metrics", "unverifiable-counts-as-not-fail",
          metrics.verifier_metrics(
              "x", keys[:2], keys[2:],
              {k: {"verdict": "unverifiable"} for k in keys},
              {k: {"verdict": "pass"} for k in keys},
              {k: "R4" for k in keys}, keys)["MD"].numerator == 0,
          "an unverifiable verdict does not detect")

    check("metrics", "inadmissible-above-fpr-ceiling",
          not metrics.admissible({"FPR": metrics.Proportion(4, 60, "f")}, 5.0)
          and metrics.admissible({"FPR": metrics.Proportion(2, 60, "f")}, 5.0),
          "6.7 pp is inadmissible, 3.3 pp is admissible")

    check("metrics", "discount-lands-12pp-under-the-gate",
          abs(metrics.discounted(metrics.Proportion(12, 100, "MD"), 0.7681) - 9.2172) < 1e-3,
          "PREREGISTRATION.md 6.4: a raw 12 pp discounts to 9.2 pp and does NOT clear 10 pp")

    check("metrics", "accuracy-ppv-npv-f1-not-implemented",
          not any(hasattr(metrics, n) for n in ("accuracy", "ppv", "npv", "f1")),
          "6.7 prefers them not reported; a function that does not exist cannot be called")


# ------------------------------------------------------------------ 10. cost governance

def test_cost() -> None:
    led = cost_mod.Ledger(ceiling_usd=9.0)
    led.spent_usd = 8.999
    try:
        led.check_before(0.02)
        check("cost", "ceiling-aborts-before-the-call", False, "the call was allowed")
    except cost_mod.BudgetExceeded:
        check("cost", "ceiling-aborts-before-the-call", True,
              "S7 is checked before the call, so the ceiling cannot be crossed by one")

    led2 = cost_mod.Ledger(ceiling_usd=9.0)
    led2.check_before(0.02)
    check("cost", "ceiling-quiet-with-headroom", led2.spent_usd == 0.0, "")

    usd = led2.bill("b", 4065, 250, {"input": 3.0, "output": 15.0})
    check("cost", "per-call-price-matches-preregistration", abs(usd - 0.0159) < 5e-4,
          f"4,065 in + 250 out at $3/$15 per M = ${usd:.5f}; PREREGISTRATION.md 10 quotes "
          f"$0.01935 rising to $0.0194 at the pessimistic size")

    long_transcript = [{"role": "user", "content": "x" * 4000} for _ in range(40)]
    kept, truncated, after = cost_mod.truncate_transcript(long_transcript, 24000, 4.0)
    check("cost", "truncation-fires-and-flags", truncated and after <= 24000,
          f"160,000 chars -> {after:,} est. tokens, flagged={truncated}")
    short = [{"role": "user", "content": "x" * 100}]
    _, tr2, _ = cost_mod.truncate_transcript(short, 24000, 4.0)
    check("cost", "truncation-quiet-under-the-cap", not tr2, "")

    cfg = freeze.load_config()
    traces = [{"transcript": [{"role": "u", "content": "y" * 200000}], "tool_calls": [],
               "run_id": "r", "task_id": f"T{i}", "arm": "A", "attempt": 1} for i in range(80)]
    isneg = {corpus.trace_key(t): False for t in traces}
    proj = cost_mod.project(traces, cfg, 3, 3, isneg)
    check("cost", "contingency-fires-on-a-costly-set", proj["contingency_fires"],
          f"projected judge subtotal ${proj['judge_subtotal_usd']:.2f} > "
          f"${cfg['cost']['contingency_trigger_usd']:.2f}")
    check("cost", "truncation-counted-in-the-projection", proj["truncated_records"] == 80,
          f"{proj['truncated_records']} of 80 flagged")

    cheap = [{"transcript": [{"role": "u", "content": "y" * 100}], "tool_calls": [],
              "run_id": "r", "task_id": f"T{i}", "arm": "A", "attempt": 1} for i in range(80)]
    proj2 = cost_mod.project(cheap, cfg, 3, 3, {corpus.trace_key(t): False for t in cheap})
    check("cost", "contingency-quiet-on-a-cheap-set", not proj2["contingency_fires"],
          f"projected ${proj2['judge_subtotal_usd']:.2f}")


# ------------------------------------------------------------------ 11. judge plumbing

def test_judge() -> None:
    cfg = freeze.load_config()
    system, user, digest = judge_mod.load_prompt(cfg)
    check("judge", "prompt-loads-and-hashes", bool(system) and bool(user) and len(digest) == 16,
          f"prompt sha256[:16] = {digest}")
    check("judge", "prompt-has-no-oracle-field-literal",
          not any(lit in (system + user) for lit in ('"expected"', '"false_success"',
                                                     '"outcome"', '"reason"')),
          "the committed prompt cannot label a slot with an oracle field")
    check("judge", "prompt-has-no-task-identifier",
          not _mentions_task_ids(os.path.join(HERE, cfg["judge_prompt"]["path"])),
          "7.2: not tuned per family or per task")

    good = judge_mod.parse_verdict('{"succeeded": false, "p_success": 0.12, '
                                   '"justification": "wrong total"}')
    check("judge", "parses-a-well-formed-verdict",
          good.parse_ok and good.succeeded is False and abs(good.p_success - 0.12) < 1e-9, "")
    for bad_text, why in (
        ("not json at all", "prose"),
        ('{"succeeded": "yes", "p_success": 0.5}', "non-boolean succeeded"),
        ('{"succeeded": true, "p_success": 4}', "probability out of range"),
        ('{"succeeded": true}', "missing p_success"),
    ):
        v = judge_mod.parse_verdict(bad_text)
        check("judge", f"refuses-to-guess ({why})",
              (not v.parse_ok) and v.succeeded is None and v.p_success is None,
              "an unparseable reply is flagged, never coerced to pass or fail")

    calls = [{"parse_ok": True, "succeeded": False, "p_success": 0.1},
             {"parse_ok": True, "succeeded": False, "p_success": 0.2},
             {"parse_ok": True, "succeeded": True, "p_success": 0.7}]
    agg = judge_mod.aggregate(calls)
    check("judge", "majority-of-three", agg["verdict"] == "fail" and agg["flip"] is True
          and agg["any_fail"] and not agg["all_fail"],
          "majority fail, flip flagged, any/all variants recorded (5.3)")
    check("judge", "mean-p-success-across-repeats",
          abs(agg["p_success_mean"] - 0.3333) < 1e-3, "")

    stub = judge_mod.StubJudge()
    t1 = stub.complete("m", "s", "u", 0.0, 250)
    t2 = stub.complete("m", "s", "u", 0.0, 250)
    check("judge", "stub-is-deterministic", t1 == t2,
          "a dry run must be reproducible or it proves nothing")


# ------------------------------------------------------------------ 12. selection

def test_selection() -> None:
    cfg = freeze.load_config()
    rows, _ = corpus.load_records(cfg, verify=False)
    elig, part = corpus.eligible_records(rows, cfg)
    a = select_mod.select(elig, cfg, part)
    b = select_mod.select(elig, cfg, part)
    check("selection", "seeded-selection-is-reproducible", a["positives"] == b["positives"],
          f"seed {a['seed']}")
    n_elig_neg = sum(1 for r in elig if r["outcome"] == "fail")
    check("selection", "all-eligible-negatives-taken", a["n_negatives"] == n_elig_neg,
          f"9.1 takes every negative in the population: {a['n_negatives']} of "
          f"{n_elig_neg} eligible (the corpus holds 20 before Amendment B3.2)")
    check("selection", "positive-count-exact", a["n_positives"] == 60, "")
    check("selection", "no-negative-in-the-positive-sample",
          not (set(map(tuple, a["negatives"])) & set(map(tuple, a["positives"]))), "")

    wider = json.loads(json.dumps(cfg))
    wider["scoring_set"]["positives"] = 80
    c = select_mod.select(elig, wider, part)
    first60 = {tuple(x) for x in a["positives"]}
    check("selection", "extension-is-a-prefix-not-a-reselection",
          first60 <= {tuple(x) for x in c["positives"]},
          "9.1 permits extending the sample but never re-selecting; the first 60 are "
          "unchanged by construction rather than by promise")

    fams = {tuple(x)[1].split(".")[0] for x in a["positives"]}
    pool = {r["family"] for r in elig if r["outcome"] == "pass"}
    check("selection", "stratification-spans-every-family-in-the-population",
          fams == pool,
          f"positive sample spans {sorted(fams)}, the eligible pool holds {sorted(pool)}. "
          "The corpus holds 7 families; Amendment B3.2 leaves 3, and 9.1's stratification "
          "can only span what survived. See eligibility/families-lost-are-cross-battery-only "
          "for why this is not a selection bug.")


# ------------------------------------------------------- 14. Amendment B3.2 eligibility rule

def _elig(stored: Any, current: Any, kind: str = corpus.VALUED_CHECK_KIND,
          run_bv: str | None = "1.1.0", bv: str = "1.4.0-probe") -> dict:
    """One eligibility verdict on a synthetic record, so each branch is provable alone."""
    return corpus.eligibility(
        {"task_id": "T.1", "expected": stored},
        {"id": "T.1", "check": {"kind": kind}},
        {} if current is _ABSENT else {"T.1": current},
        bv, run_bv)


_ABSENT = object()


def test_eligibility_rule() -> None:
    """B3.2 must exclude what it should, retain what it should, and never guess.

    The planted cases below are the four verdicts plus the two readings that produced the
    defect: a null read as a value, and a missing comparison read as agreement.
    """
    # --- known-bad: the rule must fire ------------------------------------------------
    v = _elig(stored=0, current=[21, 0])
    check("eligibility-bad", "changed-value-is-stale",
          v["status"] == corpus.INELIGIBLE_STALE and not v["eligible"],
          "a scalar revised into a corroborated pair is a different question")

    v = _elig(stored=[8, 0], current=[0, 8])
    check("eligibility-bad", "reordered-pair-is-stale",
          v["status"] == corpus.INELIGIBLE_STALE,
          "list order is the answer for a multi-part expectation; it is not a set")

    v = _elig(stored=12, current=13, run_bv="1.4.0-probe")
    check("eligibility-bad", "same-battery-mismatch-raises-integrity-alarm",
          v["status"] == corpus.INELIGIBLE_STALE and v["integrity_alarm"],
          "the battery did not change, so the fixture drifted or expected.json was edited "
          "— louder than ordinary churn, and never silently reconciled")

    v = _elig(stored=13, current=13, run_bv=None)
    check("eligibility-bad", "unpinned-run-is-not-eligible",
          v["status"] == corpus.INELIGIBLE_UNATTESTED,
          "a run with no pinned battery version cannot be attested, and an unknown "
          "provenance is not a passing one")

    # --- known-good: the rule must stay quiet ----------------------------------------
    v = _elig(stored=13, current=13)
    check("eligibility-good", "matching-value-across-batteries-is-retained",
          v["status"] == corpus.ELIGIBLE_VALUE_ATTESTED and v["eligible"],
          "an unchanged answer attests the join even when the battery moved")

    v = _elig(stored=13, current=13.0)
    check("eligibility-good", "number-spelling-is-not-drift",
          v["eligible"], "13 and 13.0 are the same answer")

    v = _elig(stored=None, current=13, run_bv="1.4.0-probe")
    check("eligibility-good", "null-on-same-battery-is-not-stale",
          v["status"] == corpus.ELIGIBLE_SAME_BATTERY and v["eligible"],
          "checks.py returns before computing an expected when nothing was submitted; "
          "reading that null as a changed expectation is the misclassification "
          "Amendment B4 records")

    v = _elig(stored=None, current=13)
    check("eligibility-good", "null-cross-battery-is-unattested-not-stale",
          v["status"] == corpus.INELIGIBLE_UNATTESTED,
          "excluded, but for absence of evidence — not recorded as a disagreement that "
          "was never observed")

    v = _elig(stored=None, current=_ABSENT, kind="impossible")
    check("eligibility-good", "valueless-check-kind-is-unattested-not-stale",
          v["status"] == corpus.INELIGIBLE_UNATTESTED,
          "'impossible' yields no expected under ANY battery, so its null carries no "
          "information about drift")

    # --- the real corpus: the population is what the harness will actually score ------
    cfg = freeze.load_config()
    rows, _ = corpus.load_records(cfg, verify=False)
    elig, part = corpus.eligible_records(rows, cfg)
    led = part["ledger"]

    statuses = corpus.ELIGIBLE_STATUSES + corpus.INELIGIBLE_STATUSES
    check("eligibility", "partition-is-total",
          sum(led[s]["n"] for s in statuses) == len(rows) == 246,
          f"every one of {len(rows)} records gets exactly one of {len(statuses)} verdicts")
    check("eligibility", "eligible-plus-excluded-equals-corpus",
          len(part["eligible"]) + len(part["excluded"]) == len(rows),
          f"{len(part['eligible'])} eligible + {len(part['excluded'])} excluded")
    check("eligibility", "no-excluded-record-survives-into-the-population",
          not ({corpus.trace_key(r) for r in elig}
               & {corpus.trace_key(r) for r in part["excluded"]}),
          "the two sets are disjoint by construction, not by promise")
    check("eligibility", "no-integrity-alarm-on-the-committed-corpus",
          not part["integrity_alarms"],
          f"{len(part['integrity_alarms'])} same-battery mismatch(es); any at all mean a "
          "fixture drifted rather than a battery moving")

    stale = [v for v in part["verdicts"].values() if v["status"] == corpus.INELIGIBLE_STALE]
    stale_keys = [k for k, v in part["verdicts"].items()
                  if v["status"] == corpus.INELIGIBLE_STALE]
    check("eligibility", "stale-set-is-exactly-the-NM-revision",
          {k[1] for k in stale_keys} == {"NM.001", "NM.002", "NM.003", "NM.004"},
          f"{len(stale)} record(s) across {sorted({k[1] for k in stale_keys})} — the "
          "one-part-to-corroborated-pair revision, and nothing else")
    by_out = {}
    for k in stale_keys:
        r = next(x for x in rows if corpus.trace_key(x) == k)
        by_out[r["outcome"]] = by_out.get(r["outcome"], 0) + 1
    check("eligibility", "stale-split-is-1-negative-6-positive",
          by_out == {"fail": 1, "pass": 6},
          f"derived {by_out}; Amendment B3's table said 6 negatives and 6 positives, and "
          "B4 records why the negative count was wrong")

    same = [r for r in elig
            if part["verdicts"][corpus.trace_key(r)]["status"]
            == corpus.ELIGIBLE_SAME_BATTERY]
    check("eligibility", "same-battery-records-are-all-retained",
          len(same) == sum(1 for r in rows
                           if freeze.run_battery_version(r["run_id"])
                           == corpus.load_expected(cfg)[0]),
          f"{len(same)} record(s) ran the battery under test and none was excluded")

    # The cost of the rule, pinned so it cannot regress quietly in either direction.
    all_fams = {r["family"] for r in rows}
    elig_fams = {r["family"] for r in elig}
    lost = all_fams - elig_fams
    check("eligibility", "family-loss-is-measured-not-assumed",
          lost == {"N", "NM", "R3", "W1"} and elig_fams == {"R1", "R2", "R4"},
          f"B3.2 costs 4 of {len(all_fams)} families: {sorted(lost)} go to zero, leaving "
          f"{sorted(elig_fams)}. Not a rounding error — the refusal families "
          "(impossible / needs_clarification / state) are exactly the ones lost")

    same_battery_fams = {r["family"] for r in rows
                         if part["verdicts"][corpus.trace_key(r)]["status"]
                         == corpus.ELIGIBLE_SAME_BATTERY}
    check("eligibility", "families-lost-are-cross-battery-only",
          not (lost & same_battery_fams),
          "every record in a lost family lives in a run that executed a superseded battery, "
          "so no setting of eligibility.on_unattested recovers them. Only re-running the "
          "battery does. This bounds what E8 can conclude, and no policy debate changes it")

    check("eligibility", "population-label-states-both-numbers",
          "195" in part["population"] and "246" in part["population"]
          and "51" in part["population"],
          part["population"])


# ------------------------------------------------- 15. cross-battery joins fail loudly

def test_cross_battery_refusal() -> None:
    """The defect was silence. Every path that could join across batteries must now shout."""
    cfg = freeze.load_config()
    root = freeze.corpus_root(cfg)
    frozen = freeze.load_freeze()
    rows, _ = corpus.load_records(cfg, verify=False)

    check("cross-battery", "freeze-pins-the-battery-files",
          bool((frozen.get("battery") or {}).get("files")),
          "corpus_freeze.json hashes tasks.json and expected.json, which it did not do "
          "for the corpus's entire existence")
    check("cross-battery", "freeze-pins-per-run-battery-version",
          len((frozen["battery"].get("run_battery_versions") or {})) == len(freeze.SCOPE_RUNS),
          "every in-scope run's manifest battery_version is recorded")

    edited = json.loads(json.dumps(frozen))
    edited["battery"]["files"]["expected_rel"] = "0" * 64
    check("cross-battery", "edited-expected-json-refuses",
          any("BATTERY CHANGED" in p for p in freeze.verify(root, edited, cfg)),
          "editing expected.json under a frozen corpus is refused, so the join cannot be "
          "made sound by changing the answer key")

    dropped = json.loads(json.dumps(frozen))
    dropped["battery"]["files"].pop("tasks_rel")
    check("cross-battery", "unhashed-battery-file-refuses",
          any("no frozen hash" in p for p in freeze.verify(root, dropped, cfg)),
          "a battery file with no recorded hash is refused, not skipped")

    moved = json.loads(json.dumps(frozen))
    moved["battery"]["version"] = "9.9.9-not-this-one"
    check("cross-battery", "battery-version-drift-refuses",
          any("battery version" in p for p in freeze.verify(root, moved, cfg)),
          "a battery bump refuses rather than silently rescoring the corpus against it")

    blind = json.loads(json.dumps(frozen))
    blind.pop("battery")
    check("cross-battery", "freeze-with-no-battery-refuses",
          any("pins no battery" in p for p in freeze.verify(root, blind, cfg)),
          "the pre-B3 freeze format is rejected outright rather than treated as 'nothing "
          "to check' — that reading is what made the defect invisible for the corpus's "
          "entire existence")

    grew = json.loads(json.dumps(frozen))
    grew["battery"]["cross_battery_records"] = 0
    check("cross-battery", "cross-battery-census-drift-refuses",
          any("cross-battery" in p.lower() or "battery" in p.lower()
              for p in freeze.verify(root, grew, cfg)),
          "the count of cross-battery records is itself pinned, so the census cannot "
          "quietly change under a passing hash check")

    # The join is refused at the point of use, not only at the freeze.
    elig, part = corpus.eligible_records(rows, cfg)
    try:
        select_mod.select(rows, cfg, None)
        check("cross-battery", "select-without-a-partition-refuses", False,
              "select() ran on the raw corpus")
    except SystemExit as exc:
        check("cross-battery", "select-without-a-partition-refuses",
              "B3.2" in str(exc) or "eligibility" in str(exc),
              "select() cannot be called without the eligibility rule having run")
    try:
        select_mod.select(rows, cfg, part)
        check("cross-battery", "select-refuses-ineligible-input", False,
              "select() accepted 51 excluded record(s)")
    except SystemExit as exc:
        check("cross-battery", "select-refuses-ineligible-input", "excluded" in str(exc),
              "handing select() the raw rows is refused rather than quietly rescored")

    check("cross-battery", "eligible-input-is-accepted",
          select_mod.select(elig, cfg, part)["n_positives"] == 60,
          "the loud failures above do not block the legitimate path")


# ------------------------------------------------------------------ 13. credential hygiene

def test_credentials() -> None:
    cfg = freeze.load_config()
    var = cfg["credentials"]["api_key_var"]
    saved = os.environ.pop(var, None)
    saved_root = os.environ.pop("F2A_ENV_ROOT", None)
    try:
        judge_mod.load_api_key(cfg, None)
        check("credentials", "no-default-path-exits", False,
              "load_api_key returned without a credential source")
    except SystemExit as exc:
        msg = str(exc)
        check("credentials", "no-default-path-exits",
              "--env-root" in msg or "F2A_ENV_ROOT" in msg,
              "exits with a usage message rather than guessing a tree")
    finally:
        if saved is not None:
            os.environ[var] = saved
        if saved_root is not None:
            os.environ["F2A_ENV_ROOT"] = saved_root

    # Needles are assembled rather than written literally, so this scanner does not match
    # itself and does not have to exempt its own file — an exemption is a hole, and the file
    # holding the scanner is exactly where a hole would go unnoticed.
    needles = ["sk" + "-ant", "/Us" + "ers/", "/ho" + "me/", var + "="]
    offenders = []
    for fn in sorted(os.listdir(HERE)):
        if not fn.endswith((".py", ".json", ".md")):
            continue
        with open(os.path.join(HERE, fn), encoding="utf-8", errors="ignore") as fh:
            text = fh.read()
        for needle in needles:
            if needle in text:
                offenders.append(f"{fn}: {needle!r}")
    check("credentials", "no-credential-or-private-path-in-source", not offenders,
          "; ".join(offenders) or "no key material and no absolute home path anywhere")


# ------------------------------------------------------------------ report

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    for fn in (test_leak_assertion, test_freeze_refusal, test_taxonomy, test_label_shuffle,
               test_constant_anchors, test_predicted_null, test_c1_clauses,
               test_c1_quarantine, test_c2,
               test_c2_rules_fire_and_stay_silent,
               test_metrics, test_cost, test_judge, test_selection,
               test_eligibility_rule, test_cross_battery_refusal, test_credentials):
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            check(fn.__name__, "raised", False, f"{type(exc).__name__}: {exc}")

    width = max(len(n) for _, n, _, _ in RESULTS)
    group = None
    for g, n, ok, detail in RESULTS:
        if g != group:
            print(f"\n{g}")
            group = g
        line = f"  {'PASS' if ok else 'FAIL'}  {n:<{width}}"
        if args.verbose or not ok:
            line += f"  {detail}"
        print(line)

    failures = [(g, n, d) for g, n, ok, d in RESULTS if not ok]
    print(f"\n{len(RESULTS)} checks, {len(failures)} failure(s)")
    if failures:
        for g, n, d in failures:
            print(f"  - {g}/{n}: {d}")
        return 1
    print("all self-tests passed — every control fires on planted-bad input "
          "and stays silent on known-good")
    return 0


if __name__ == "__main__":
    sys.exit(main())
