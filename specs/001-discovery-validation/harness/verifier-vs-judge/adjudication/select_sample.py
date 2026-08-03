"""E8 oracle adjudication - sample selection and BLIND view construction.

PREREGISTRATION.md 4.1 fixes the composition: all 20 oracle-negatives plus a random 20 of
the 226 oracle-positives, 40 traces total. This script materialises that sample and splits
it into two artifacts:

  blind/cases.md     - task prompt, transcript, tool calls, submitted answer. NOTHING ELSE.
  sealed/key.json    - case_id -> trace key, oracle outcome, reason, expected, false_success.

The 40 cases are SHUFFLED together and given opaque ids (A01..A40) so that the adjudicator
cannot tell, while reading any single case, which bucket it was drawn from. Knowing "this
one is from the negatives pile" would leak the oracle verdict just as surely as reading it.
That is why the buckets are not preserved in the reading order.

The adjudicator commits verdicts to blind_verdicts.md before sealed/key.json is opened.
"""

from __future__ import annotations

import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(HERE)
RESULTS = os.path.abspath(os.path.join(PARENT, "..", "ceiling-test", "results"))
TASKS = os.path.abspath(os.path.join(PARENT, "..", "ceiling-test", "tasks", "tasks.json"))

# freeze.SCOPE_RUNS - the 11 complete run directories PREREGISTRATION.md 2 pins the
# scoring set to. Copied rather than imported so this script does not drag in the
# harness modules the independence requirement keeps me away from.
SCOPE_RUNS = [
    "20260802T151714-smoke",
    "20260802T152825-smoke2",
    "20260802T154826-calibration",
    "20260802T160705-recalibration",
    "20260802T163319-bias-probe",
    "20260802T164929-bias-probe-perrecord",
    "20260802T165903-ambiguity-recheck",
    "20260802T173226-reprobe-perrecord-v2",
    "20260802T173614-baseline-lookup-R1R2",
    "20260803T064400-smoke-paired-precheck",
    "20260803T064550-paired-lookup-R1R2-A3budgets",
]

SEED = 20260803          # config.json scoring_set.rng_seed, fixed before any selection
SHUFFLE_SEED = 8811403   # reading-order shuffle; distinct so order carries no bucket signal
N_POSITIVES = 20         # PREREGISTRATION.md 4.1: "a random 20 of the 226 positives"
TOOL_RESULT_CAP = 8000   # per tool result, in the rendered view; flagged where it bites

ORACLE_FIELDS = ("expected", "reason", "outcome", "false_success", "detectors", "state_changed")

#: The only record fields the blind view is built from. Enforced structurally, on keys, not
#: by grepping the rendered text - "expected" and "reason" are ordinary English and appear in
#: task prompts and agent notes for innocent reasons.
BLIND_RECORD_FIELDS = frozenset({
    "family", "arm", "attempt", "terminal", "turns", "tool_call_count",
    "transcript", "submitted", "submitted_status",
})
BLIND_TASK_FIELDS = frozenset({"prompt", "answer_kind"})


def blind_record(tr: dict, task: dict) -> tuple[dict, dict]:
    """Project a trace and its task down to exactly the fields an adjudicator may see."""
    r = {k: tr.get(k) for k in BLIND_RECORD_FIELDS}
    t = {k: task.get(k) for k in BLIND_TASK_FIELDS}
    assert set(r) == BLIND_RECORD_FIELDS and set(t) == BLIND_TASK_FIELDS
    assert not (set(r) | set(t)) & set(ORACLE_FIELDS)
    return r, t


def load() -> list[dict]:
    traces: list[dict] = []
    for run in SCOPE_RUNS:
        with open(os.path.join(RESULTS, run, "traces.jsonl"), encoding="utf-8") as fh:
            traces += [json.loads(x) for x in fh if x.strip()]
    return traces


def battery() -> dict[str, dict]:
    with open(TASKS, encoding="utf-8") as fh:
        b = json.load(fh)
    return {t["id"]: t for t in b["tasks"]}


def render(case_id: str, tr_full: dict, task_full: dict) -> str:
    """The blind view. Every field written here is something an honest adjudicator may see."""
    tr, task = blind_record(tr_full, task_full)
    out = [f"## {case_id}", ""]
    out.append(f"- family: `{tr['family']}`  arm: `{tr['arm']}`  attempt: `{tr['attempt']}`")
    out.append(f"- declared answer_kind: `{task.get('answer_kind')}`")
    out.append(f"- terminal: `{tr.get('terminal')}`  turns: {tr.get('turns')}  "
               f"tool_calls: {tr.get('tool_call_count')}")
    out.append("")
    out.append("**Task prompt**")
    out.append("")
    out.append("> " + str(task["prompt"]).replace("\n", "\n> "))
    out.append("")
    out.append("**Transcript**")
    out.append("")

    truncated = False
    for msg in tr.get("transcript") or []:
        content = msg["content"]
        if isinstance(content, str):
            out.append(f"- *{msg['role']}*: {content}")
            continue
        for blk in content:
            t = blk.get("type")
            if t == "tool_use":
                args = json.dumps(blk.get("input"), sort_keys=True)
                out.append(f"- **CALL** `{blk.get('name')}`({args})")
            elif t == "tool_result":
                c = blk.get("content")
                c = c if isinstance(c, str) else json.dumps(c)
                if len(c) > TOOL_RESULT_CAP:
                    truncated = True
                    c = c[:TOOL_RESULT_CAP] + f"\n...[TRUNCATED, {len(c)} chars total]"
                err = " (is_error)" if blk.get("is_error") else ""
                out.append(f"  - RESULT{err}: ```\n{c}\n```")
            elif t == "text":
                out.append(f"- *{msg['role']} text*: {blk.get('text')}")
            else:
                out.append(f"- *{msg['role']} {t}*: {json.dumps(blk)[:400]}")
    out.append("")
    out.append("**Submitted**")
    out.append("")
    out.append(f"- submitted_status: `{tr.get('submitted_status')}`")
    out.append(f"- submitted: `{json.dumps(tr.get('submitted'))}`")
    if truncated:
        out.append("")
        out.append("> NOTE: at least one tool result was truncated in this view.")
    out.append("")
    out.append("---")
    out.append("")
    return "\n".join(out)


def main() -> int:
    traces = load()
    tasks = battery()
    negs = [t for t in traces if t["outcome"] == "fail"]
    poss = [t for t in traces if t["outcome"] != "fail"]
    print(f"corpus: {len(traces)} traces, {len(negs)} negatives, {len(poss)} positives")

    rng = random.Random(SEED)
    keyed = sorted(poss, key=lambda r: (r["run_id"], r["task_id"], r["arm"], r["attempt"]))
    pos_sample = rng.sample(keyed, N_POSITIVES)

    sample = negs + pos_sample
    assert len(sample) == 40, len(sample)

    order = list(sample)
    random.Random(SHUFFLE_SEED).shuffle(order)

    os.makedirs(os.path.join(HERE, "blind"), exist_ok=True)
    os.makedirs(os.path.join(HERE, "sealed"), exist_ok=True)

    key = {}
    body = []
    for i, tr in enumerate(order, 1):
        cid = f"A{i:02d}"
        task = tasks[tr["task_id"]]
        body.append(render(cid, tr, task))
        key[cid] = {
            "run_id": tr["run_id"], "task_id": tr["task_id"], "arm": tr["arm"],
            "attempt": tr["attempt"], "family": tr["family"],
            "oracle_outcome": tr["outcome"], "oracle_reason": tr.get("reason"),
            "expected": tr.get("expected"), "false_success": tr.get("false_success"),
            "submitted": tr.get("submitted"), "submitted_status": tr.get("submitted_status"),
            "bucket": "negative" if tr["outcome"] == "fail" else "positive",
        }

    head = [
        "# E8 oracle adjudication - BLIND case views",
        "",
        "40 cases: all 20 oracle-negatives + 20 seeded-random oracle-positives "
        "(PREREGISTRATION.md 4.1), shuffled together under opaque ids so that no case's",
        "bucket is visible while it is being read.",
        "",
        f"Selection seed {SEED} (config.json scoring_set.rng_seed); reading-order shuffle "
        f"seed {SHUFFLE_SEED}.",
        "",
        "Contains NO `expected`, `reason`, `outcome`, `false_success`, `detectors` or "
        "`state_changed` field from any record.",
        "",
        "---",
        "",
    ]
    with open(os.path.join(HERE, "blind", "cases.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(head) + "".join(body))

    with open(os.path.join(HERE, "sealed", "key.json"), "w", encoding="utf-8") as fh:
        json.dump(key, fh, indent=1, sort_keys=True)

    with open(os.path.join(HERE, "blind", "cases.md"), encoding="utf-8") as fh:
        blind_text = fh.read()
    print(f"blind/cases.md: {len(blind_text)} chars, {len(order)} cases "
          f"(field whitelist enforced in blind_record)")

    bykey = {}
    for v in key.values():
        bykey[v["bucket"]] = bykey.get(v["bucket"], 0) + 1
    print(f"sealed/key.json written: {bykey}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
