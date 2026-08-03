"""Compact BLIND digest: prompt, agent's final reasoning, submitted answer.

Same field whitelist as select_sample.blind_record - this reads no oracle field. It exists
because several traces run to 1,600 rendered lines of repeated tool output, and the verdict
usually turns on the last reasoning block plus the numbers the agent fed into it. Full
transcripts stay in blind/cases.md and are re-read whenever the digest is not enough.
"""

from __future__ import annotations

import json
import os
import sys

import select_sample as S

HERE = os.path.dirname(os.path.abspath(__file__))


def main() -> int:
    want = set(sys.argv[1:]) or None
    tasks = S.battery()
    order = case_order()

    out = []
    for i, tr in enumerate(order, 1):
        cid = f"A{i:02d}"
        if want and cid not in want:
            continue
        rec, task = S.blind_record(tr, tasks[tr["task_id"]])
        out.append(f"## {cid}  [{rec['family']}/{rec['arm']}]  terminal={rec['terminal']}")
        out.append(f"PROMPT: {task['prompt']}")
        out.append(f"answer_kind={task['answer_kind']}")

        texts = []
        for msg in rec["transcript"] or []:
            c = msg["content"]
            if isinstance(c, list):
                for blk in c:
                    if blk.get("type") == "text":
                        texts.append(blk["text"])
        if texts:
            out.append("FINAL REASONING:\n" + texts[-1][:4000])
        out.append(f"SUBMITTED[{rec['submitted_status']}]: {json.dumps(rec['submitted'])}")
        out.append("")
    print("\n".join(out))
    return 0


def case_order() -> list[dict]:
    """Re-derive A01..A40 from the committed seeds, so the digest never opens sealed/."""
    import random

    traces = S.load()
    negs = [t for t in traces if t["outcome"] == "fail"]
    poss = [t for t in traces if t["outcome"] != "fail"]
    keyed = sorted(poss, key=lambda r: (r["run_id"], r["task_id"], r["arm"], r["attempt"]))
    sample = negs + random.Random(S.SEED).sample(keyed, S.N_POSITIVES)
    order = list(sample)
    random.Random(S.SHUFFLE_SEED).shuffle(order)
    return order


if __name__ == "__main__":
    raise SystemExit(main())
