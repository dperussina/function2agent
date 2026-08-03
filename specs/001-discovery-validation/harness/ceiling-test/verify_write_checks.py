"""SPIKE - E7 ceiling test. Delete after 2026-11-30. Do not import from product code.

Exercises every write task's check against a *genuine* completion.

The negative control proves a write check rejects an agent that did nothing. That is only
half the requirement. This proves the other half: that the check accepts the change when
the change is actually made, and that it does so through the same HTTP path a real arm
would use. A write check that rejects everything is as useless as one that accepts
everything, and until this ran, four of the five write tasks had never been scored by the
current adjudicator at all.

For each write task:
  1. restore the fixture to the frozen baseline
  2. adjudicate a confident claim against an unchanged application  -> must FAIL
  3. perform the completion for real, over HTTP, using the Arm A tools
  4. adjudicate a confident claim against the changed application   -> must PASS
  5. perform a near-miss variant where one requirement is violated  -> must FAIL
  6. restore the fixture

Runs no model and costs nothing.

Usage:  python3 verify_write_checks.py
"""

from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import arms as arms_mod  # noqa: E402
import checks  # noqa: E402
import snapshot as snap  # noqa: E402
import state as S  # noqa: E402
from mealie_client import connect, load_config  # noqa: E402

SNAP_DIR = "/tmp/f2a-ceiling/fixture-snapshot"
CLAIM = {"status": "answered", "value": "Done.", "note": "confident"}


def completions(fns: dict):
    """The genuine completion for each write task, and a near-miss that violates exactly
    one stated requirement. The near-miss is what catches a check that is too loose."""
    return {
        "W1.001": (
            lambda: (
                fns["create_shopping_list"](name="Ceiling Test List"),
                fns["add_shopping_list_item"](list_name="Ceiling Test List", item="red lentils", quantity=3),
                fns["add_shopping_list_item"](list_name="Ceiling Test List", item="tahini", quantity=1),
            ),
            "quantity 3 and 1, both unchecked",
            lambda: (
                fns["create_shopping_list"](name="Ceiling Test List"),
                fns["add_shopping_list_item"](list_name="Ceiling Test List", item="red lentils", quantity=3),
                fns["add_shopping_list_item"](list_name="Ceiling Test List", item="tahini", quantity=1),
                fns["set_shopping_list_items_checked"](list_name="Ceiling Test List", checked=True, item="tahini"),
            ),
            "same list but one item wrongly checked off",
        ),
        "W1.002": (
            lambda: fns["add_meal_plan_entry"](date="2026-09-14", entry_type="dinner", recipe="Wild Millet Pilaf"),
            "correct date, slot and recipe",
            lambda: fns["add_meal_plan_entry"](date="2026-09-14", entry_type="lunch", recipe="Wild Millet Pilaf"),
            "right date and recipe, wrong meal slot",
        ),
        "W1.003": (
            lambda: fns["set_recipe_tags"](recipe="Ember Chard Ragout", tags=["weeknight"], mode="add"),
            "tag added, existing tags kept",
            lambda: fns["set_recipe_tags"](recipe="Ember Chard Ragout", tags=["weeknight"], mode="replace"),
            "tag added but the existing tags were destroyed",
        ),
        "W1.004": (
            lambda: fns["set_shopping_list_items_checked"](list_name="Holiday Prep", checked=True),
            "every item on the list checked off",
            lambda: fns["set_shopping_list_items_checked"](list_name="Farmers Market", checked=True),
            "the wrong list was checked off",
        ),
        "W1.005": (
            lambda: fns["create_recipe"](name="Ceiling Probe Casserole", servings=4, prep_minutes=35, tags=["budget"]),
            "recipe created with the stated servings, prep time and tag",
            lambda: fns["create_recipe"](name="Ceiling Probe Casserole", servings=6, prep_minutes=35, tags=["budget"]),
            "created but with the wrong servings",
        ),
    }


def reset(cfg) -> tuple[dict, str]:
    snap.restore(cfg, SNAP_DIR)
    st = S.snapshot(connect())
    return st, S.fingerprint(st)


def main() -> None:
    cfg = load_config()
    with open(os.path.join(HERE, "tasks", "tasks.json"), encoding="utf-8") as fh:
        battery = json.load(fh)
    writes = [t for t in battery["tasks"] if t["check"]["kind"] == "state"]

    print(f"verifying {len(writes)} write checks against genuine completions\n")
    failures: list[str] = []

    for task in writes:
        tid = task["id"]
        pre_state, pre_fp = reset(cfg)
        fns = arms_mod.build_arm_a(connect())[2]
        do_right, right_desc, do_wrong, wrong_desc = completions(fns)[tid]

        # 1. nothing done
        v = checks.adjudicate(task, CLAIM, pre_state, pre_state, pre_fp, pre_fp, "submitted_answer")
        ok_noop = v["outcome"] == "fail"
        print(f"{tid}  no-op claim            -> {v['outcome'].upper():4s} "
              f"{'ok' if ok_noop else 'WRONG'}   {v['reason'][:70]}")
        if not ok_noop:
            failures.append(f"{tid}: a no-op passed")

        # 2. genuine completion
        do_right()
        post_state = S.snapshot(connect())
        post_fp = S.fingerprint(post_state)
        v = checks.adjudicate(task, CLAIM, pre_state, post_state, pre_fp, post_fp, "submitted_answer")
        ok_real = v["outcome"] == "pass"
        print(f"{tid}  genuine completion     -> {v['outcome'].upper():4s} "
              f"{'ok' if ok_real else 'WRONG'}   ({right_desc})")
        if not ok_real:
            failures.append(f"{tid}: a genuine completion FAILED - {v['reason']}")
            print(f"        reason: {v['reason'][:150]}")

        # 3. near miss
        pre_state, pre_fp = reset(cfg)
        fns = arms_mod.build_arm_a(connect())[2]
        do_wrong = completions(fns)[tid][2]
        do_wrong()
        post_state = S.snapshot(connect())
        post_fp = S.fingerprint(post_state)
        v = checks.adjudicate(task, CLAIM, pre_state, post_state, pre_fp, post_fp, "submitted_answer")
        ok_near = v["outcome"] == "fail"
        print(f"{tid}  near miss              -> {v['outcome'].upper():4s} "
              f"{'ok' if ok_near else 'WRONG'}   ({wrong_desc})")
        if not ok_near:
            failures.append(f"{tid}: a near miss PASSED - the check is too loose ({wrong_desc})")
        print()

    reset(cfg)
    if failures:
        print("FAILURES:")
        for f in failures:
            print(" ", f)
        raise SystemExit(1)
    print("OK. Every write check rejects inaction, accepts a genuine completion, "
          "and rejects a near miss.")


if __name__ == "__main__":
    main()
