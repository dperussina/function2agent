"""Battery drift across the E8 frozen corpus.

corpus_freeze.json pins the SHA-256 of every results.jsonl and traces.jsonl in scope, but it does
not pin the task battery, and the trace records do not store the prompt the agent was shown. Any
downstream consumer therefore joins a trace to whatever tasks/tasks.json says *today*. This script
reports where that join is wrong.
"""

from __future__ import annotations

import json
import os
from collections import Counter, defaultdict

import select_sample as S

HARNESS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CT = os.path.join(os.path.dirname(HARNESS), "ceiling-test")


def battery_versions() -> dict[str, str]:
    out = {}
    for run in S.SCOPE_RUNS:
        with open(os.path.join(CT, "results", run, "manifest.json"), encoding="utf-8") as fh:
            out[run] = json.load(fh)["battery_version"]
    return out


def main() -> None:
    bat = battery_versions()
    with open(os.path.join(CT, "tasks", "tasks.json"), encoding="utf-8") as fh:
        battery = json.load(fh)
    current = battery["battery_version"] if isinstance(battery, dict) else "?"
    tasks = battery if isinstance(battery, list) else battery["tasks"]
    amended = {t["id"] for t in tasks if t.get("quarantine_history")}

    recs = S.load()
    print(f"current battery_version = {current}")
    print(f"corpus = {len(recs)} traces over {len(S.SCOPE_RUNS)} runs")
    print("\ntraces by battery version at run time:")
    for k, v in sorted(Counter(bat[r['run_id']] for r in recs).items()):
        print(f"  {k:<14} {v}")

    print("\ntasks carrying a quarantine_history (prompt and/or check was revised):")
    print(
        "  PROVABLE  - frozen `expected` is structurally incompatible with the current answer_kind,"
        "\n              so the trace cannot have been produced under the current prompt."
        "\n  BEHAVIOURAL - `expected` is unchanged (only the prompt was amended, not the answer), but"
        "\n              in-scope runs predate the amendment and their answers track the old reading."
        "\n  CLEAN     - the revision predates every in-scope run; nothing in the corpus is affected.\n"
    )
    for tid in sorted(amended):
        tk = next(t for t in tasks if t["id"] == tid)
        seen = defaultdict(set)
        for r in recs:
            if r["task_id"] == tid:
                seen[bat[r["run_id"]]].add(json.dumps(r["expected"]))
        all_exp = {x for v in seen.values() for x in v}
        # structural: a numbers task whose frozen expected is not a 2-element list
        provable = tk["answer_kind"] == "numbers" and any(
            not (isinstance(json.loads(e), list) and len(json.loads(e)) == len(tk["check"]["queries"]))
            for e in all_exp
        )
        stale_runs = sorted(k for k in seen if k != current)
        # Whether a revision moved the *answer* or only the *wording* cannot be read off the
        # record, so it is annotated by hand from each task's quarantine_history. A revision
        # that moved the answer is self-dating: if the frozen `expected` already equals the
        # current one at the earliest in-scope run, that revision predates the corpus.
        moved_the_answer = tid in {"R2.010", "NM.001", "NM.002", "NM.003", "NM.004"}
        if provable:
            verdict = "PROVABLE"
        elif not stale_runs:
            verdict = "CLEAN"
        elif moved_the_answer and len(all_exp) == 1:
            verdict = "CLEAN"  # re-pointing predates every in-scope run
        else:
            verdict = "BEHAVIOURAL"
        line = "  ".join(f"{k}->{sorted(v)}" for k, v in sorted(seen.items()))
        print(f"  {verdict:<12} {tid:<8} {line}")

    print("\nper-trace verdict on drift, for traces on amended tasks:")
    for r in sorted(recs, key=lambda r: (r["task_id"], bat[r["run_id"]])):
        if r["task_id"] not in amended:
            continue
        tk = next(t for t in tasks if t["id"] == r["task_id"])
        shape_ok = not (
            (tk["answer_kind"] == "numbers" and not isinstance(r["expected"], list))
            or (tk["answer_kind"] == "number" and isinstance(r["expected"], list))
        )
        print(
            f"  {r['task_id']:<8} bat={bat[r['run_id']]:<13} arm={r['arm']} "
            f"expected={json.dumps(r['expected']):<10} answer_kind={tk['answer_kind']:<8} "
            f"{'ok' if shape_ok else 'SHAPE MISMATCH -> prompt provably differs'}"
        )


if __name__ == "__main__":
    main()
