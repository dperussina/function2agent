"""Compare blind verdicts against the oracle. Run only after blind/verdicts.md is written."""

from __future__ import annotations

import json
import os
import re

import digest
import select_sample as S

HERE = os.path.dirname(os.path.abspath(__file__))

BLIND = os.path.join(HERE, "blind", "verdicts.md")


def mine() -> dict[str, str]:
    with open(BLIND, encoding="utf-8") as fh:
        text = fh.read()
    out = {}
    for cid, verdict in re.findall(r"^### (A\d\d) .*?\n(.*?)(?=\n### |\n---)", text, re.S | re.M):
        hits = re.findall(r"\*\*(PASS|FAIL)\*\*", verdict)
        assert len(hits) == 1, (cid, hits)
        out[cid] = hits[0]
    return out


def main() -> None:
    verdicts = mine()
    assert len(verdicts) == 40, len(verdicts)

    tasks_full = S.battery_full() if hasattr(S, "battery_full") else None
    order = digest.case_order()

    rows = []
    for i, tr in enumerate(order, 1):
        cid = f"A{i:02d}"
        oracle = "FAIL" if tr["outcome"] == "fail" else "PASS"
        rows.append(
            {
                "case": cid,
                "task_id": tr["task_id"],
                "family": tr["family"],
                "arm": tr["arm"],
                "mine": verdicts[cid],
                "oracle": oracle,
                "oracle_outcome": tr["outcome"],
                "oracle_reason": tr.get("reason"),
                "expected": (tasks_full or {}).get(tr["task_id"], {}).get("expected"),
                "submitted": tr.get("submitted"),
            }
        )

    agree = sum(r["mine"] == r["oracle"] for r in rows)
    print(f"agreement {agree}/40 = {agree/40:.1%}\n")

    a = sum(1 for r in rows if r["mine"] == "FAIL" and r["oracle"] == "FAIL")
    b = sum(1 for r in rows if r["mine"] == "FAIL" and r["oracle"] == "PASS")
    c = sum(1 for r in rows if r["mine"] == "PASS" and r["oracle"] == "FAIL")
    d = sum(1 for r in rows if r["mine"] == "PASS" and r["oracle"] == "PASS")
    print(f"  both FAIL {a} | I FAIL, oracle PASS {b} | I PASS, oracle FAIL {c} | both PASS {d}")

    po = (a + d) / 40
    pf = ((a + b) / 40) * ((a + c) / 40)
    pp = ((c + d) / 40) * ((b + d) / 40)
    pe = pf + pp
    print(f"  Cohen kappa: po={po:.4f} pe={pe:.4f} k={(po-pe)/(1-pe):.4f}\n")

    print("DISAGREEMENTS")
    for r in rows:
        if r["mine"] != r["oracle"]:
            print(f"  {r['case']} {r['task_id']} [{r['family']}/{r['arm']}]  mine={r['mine']} oracle={r['oracle']}")
            print(f"        reason={r['oracle_reason']!r}")
            print(f"        expected={r['expected']!r}  submitted={r['submitted']!r}")

    with open(os.path.join(HERE, "comparison.json"), "w", encoding="utf-8") as fh:
        json.dump(rows, fh, indent=1)

    print("\nALL")
    for r in rows:
        flag = "  " if r["mine"] == r["oracle"] else "**"
        print(
            f"{flag}{r['case']} {r['task_id']:<8} {r['family']:<3} {r['arm']}  "
            f"mine={r['mine']:<4} oracle={r['oracle']:<4} {str(r['oracle_reason'])[:60]}"
        )


if __name__ == "__main__":
    main()
