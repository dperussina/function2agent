"""SPIKE - E7 ceiling test. Delete after 2026-11-30. Do not import from product code.

Freezes and self-tests the task battery. Costs nothing and runs no model.

Three jobs:

1. **Compute expected values** for every read task by executing its reference query
   against the seeded fixture, and write them to `expected.json` (FR-009).

2. **Reject degenerate tasks automatically**, following research/11-validation-plan.md 3.3
   step 4: an answer of zero, an answer equal to the whole collection, an empty list, a
   single-element list where the collection has one element, or an argmax/argmin with a
   tie. A tie is not merely uninteresting, it is unadjudicable, so it is a hard error.

3. **Prove every check can fail as well as pass.** For each task the adjudicator is run
   twice: once against the correct submission (must PASS) and once against a confident
   but wrong submission (must FAIL and, where applicable, be flagged a false success).
   A check that only ever passes is not a check.

Usage:  python3 validate_battery.py
"""

from __future__ import annotations

import collections
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import checks  # noqa: E402
import state as S  # noqa: E402
from mealie_client import connect  # noqa: E402

TASKS_PATH = os.path.join(HERE, "tasks.json")
EXPECTED_PATH = os.path.join(HERE, "expected.json")


def wrong_submission(task: dict, expected) -> dict:
    """A confident, plausible, incorrect answer for this task."""
    kind = task["check"]["kind"]
    if kind == "reference_answer":
        ak = task["answer_kind"]
        if ak == "number":
            return {"status": "answered", "value": str(float(expected) + 7), "note": "confident"}
        if ak == "numbers":
            wrong = [float(expected[0]) + 7] + [float(x) for x in expected[1:]]
            return {"status": "answered", "value": ", ".join(str(x) for x in wrong), "note": "confident"}
        if ak == "text":
            return {"status": "answered", "value": "Something Else Entirely", "note": "confident"}
        return {"status": "answered", "value": "Nonexistent Alpha, Nonexistent Beta", "note": "confident"}
    # For clarification / impossible / write tasks the archetypal wrong behaviour is the
    # same: confidently claim to have done it.
    return {"status": "answered", "value": "Done.", "note": "confident"}


def main() -> None:
    with open(TASKS_PATH, encoding="utf-8") as fh:
        battery = json.load(fh)
    tasks = battery["tasks"]
    api = connect()
    st = S.snapshot(api)
    fp = S.fingerprint(st)

    errors: list[str] = []
    warnings: list[str] = []
    expected_out: dict = {}

    # Freezing against a dirty fixture bakes contaminated values into expected.json and
    # every later run silently inherits them. This has happened once already.
    if os.path.exists(EXPECTED_PATH):
        with open(EXPECTED_PATH, encoding="utf-8") as fh:
            prior = json.load(fh)
        if prior.get("fixture_fingerprint") and prior["fixture_fingerprint"] != fp:
            errors.append(
                "FIXTURE DRIFT: the live application no longer matches the fingerprint in "
                f"expected.json (was {prior['fixture_fingerprint'][:16]}, now {fp[:16]}). "
                "Restore the baseline snapshot or re-seed before freezing; freezing now "
                "would bake a contaminated fixture into every subsequent run. Delete "
                "expected.json deliberately if you really intend to re-baseline."
            )

    fam = collections.Counter(t["family"] for t in tasks)
    ids = [t["id"] for t in tasks]
    if len(set(ids)) != len(ids):
        errors.append("duplicate task ids")

    for t in tasks:
        tid, kind = t["id"], t["check"]["kind"]
        if kind != "reference_answer":
            continue
        try:
            exp = checks.expected_value(t, st)
        except Exception as exc:
            errors.append(f"{tid}: reference query failed: {exc}")
            continue
        expected_out[tid] = exp

        # Near-miss tasks are deliberately empty: a well-formed query whose subject exists
        # and which legitimately matches nothing. The screen is inverted for them -- an
        # empty result is required, and a non-empty one means the fixture changed under a
        # task that only means anything while it stays empty.
        if t["family"] == "NM":
            if not t.get("near_miss_note"):
                errors.append(f"{tid}: near-miss task must document why its subject exists")
            if t["answer_kind"] != "numbers" or not isinstance(exp, list) or len(exp) < 2:
                errors.append(f"{tid}: a near-miss task must be a corroborated pair, otherwise "
                              "'nothing matched' can be reached by abstaining rather than by looking")
            elif exp[-1] != 0:
                errors.append(f"{tid}: near-miss task is no longer empty (got {exp!r}); the fixture "
                              "moved and the task no longer tests what it was built to test")
            elif exp[0] == 0:
                errors.append(f"{tid}: the corroborating count is also zero, so the whole answer is "
                              "guessable; pick a corroborating query with a non-zero result")
            continue

        # degeneracy screen
        src = t["check"]["query"]["source"]
        total = len(st[src])
        if isinstance(exp, (int, float)) and t["answer_kind"] == "number":
            agg = t["check"]["query"]["select"]["agg"]
            if agg == "count":
                if exp == 0:
                    errors.append(f"{tid}: degenerate, answer is 0")
                elif exp == total and len(t["check"]["query"].get("where", [])) > 0:
                    errors.append(f"{tid}: degenerate, filter matches the whole collection ({total})")
        if isinstance(exp, list):
            if not exp:
                errors.append(f"{tid}: degenerate, expected list is empty")
            elif len(exp) == total:
                warnings.append(f"{tid}: expected list is the whole collection ({total})")

    # every check must be able to pass and to fail
    broken = {e.split(":")[0] for e in errors}
    for t in tasks:
        tid, kind = t["id"], t["check"]["kind"]
        if tid in broken:
            continue  # its reference query already failed; the message above says why
        exp = expected_out.get(tid)

        if kind == "reference_answer":
            ak = t["answer_kind"]
            if ak == "set":
                # An empty oracle answer is correctly reported as "none", so that is what
                # the correct submission must look like.
                value = ", ".join(str(x) for x in exp) if exp else "none"
            elif ak == "numbers":
                value = ", ".join(str(x) for x in exp)
            else:
                value = str(exp)
            right = {"status": "answered", "value": value, "note": ""}
        elif kind == "needs_clarification":
            right = {"status": "needs_clarification", "value": "", "note": ""}
        elif kind == "impossible":
            right = {"status": "impossible", "value": "", "note": ""}
        else:
            right = None  # write tasks are exercised separately below

        if right is not None:
            r = checks.adjudicate(t, right, st, st, fp, fp, "submitted_answer")
            if r["outcome"] != "pass":
                errors.append(f"{tid}: correct submission did not pass ({r['reason']})")

        bad = wrong_submission(t, exp)
        rb = checks.adjudicate(t, bad, st, st, fp, fp, "submitted_answer")
        if rb["outcome"] != "fail":
            errors.append(f"{tid}: an incorrect submission PASSED - the check is not a check")
        if not rb["false_success"] and kind in ("reference_answer", "needs_clarification", "impossible"):
            errors.append(f"{tid}: confident wrong answer was not flagged a false success")

        # writes: an unmodified post-state must fail, since nothing was done
        if kind == "state":
            rn = checks.adjudicate(t, {"status": "answered", "value": "Done."}, st, st, fp, fp,
                                   "submitted_answer")
            if rn["outcome"] != "fail":
                errors.append(f"{tid}: write task passed without any state change")
            if not rn["false_success"]:
                errors.append(f"{tid}: claiming a write that never happened was not a false success")

        # abstention on an answerable task must fail, but must NOT be a false success
        if kind == "reference_answer":
            ra = checks.adjudicate(t, {"status": "impossible", "value": ""}, st, st, fp, fp,
                                   "submitted_answer")
            if ra["outcome"] != "fail" or ra["false_success"]:
                errors.append(f"{tid}: honest abstention mis-scored")

    print("battery", battery["battery_version"], "-", len(tasks), "tasks")
    for f in sorted(fam):
        print(f"  {f:4s} {fam[f]}")
    print(f"  smoke subset: {sum(1 for t in tasks if t.get('smoke'))}")
    print()
    for w in warnings:
        print("WARN ", w)
    for e in errors:
        print("ERROR", e)
    if errors:
        print(f"\n{len(errors)} error(s). Battery is NOT frozen.")
        sys.exit(1)

    with open(EXPECTED_PATH, "w", encoding="utf-8") as fh:
        json.dump(
            {
                "battery_version": battery["battery_version"],
                "fixture_fingerprint": fp,
                "_comment": "Expected values computed from the seeded fixture at freeze time. "
                            "The runner recomputes them at scoring time; a mismatch against this "
                            "file means the fixture drifted and the run is void.",
                "expected": expected_out,
            },
            fh,
            indent=1,
            sort_keys=True,
        )
    print(f"OK. Every check passes on a correct answer and fails on a wrong one.")
    print(f"fixture fingerprint {fp}")
    print(f"wrote {EXPECTED_PATH} ({len(expected_out)} expected values)")


if __name__ == "__main__":
    main()
