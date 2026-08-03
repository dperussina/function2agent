"""SPIKE - E7 ceiling test. Delete after 2026-11-30. Do not import from product code.

The fail-open probe: what does the target do with a `categories` value it cannot resolve?

Mealie answers **HTTP 200** and silently returns the entire unfiltered recipe collection for
any `categories` value it cannot resolve to a category UUID. There is no error, no empty
result, and nothing in the response body that distinguishes "your filter matched everything"
from "your filter was discarded". That is the mechanism behind the one false success in the
E7 record: the shell arm asked for the `Breakfast` category by display name, was handed all
60 recipes, and submitted them as the 7 that matched
(`results/20260802T173614-baseline-lookup-R1R2/`, task `R1.012`).

The hazard is dangerous rather than merely wrong because the parameter *does* work for two of
the three plausible identifier forms. An agent that gets it right once has no reason to doubt
it the next time.

Arm A cannot reach this path at all: `search_recipes` never passes `category` to the query
parameter, it fetches recipe details and filters in Python on
`c["name"].lower() == category.lower()` (`tools/mealie_tools.py`, `_select`). The immunity is
a property of human authorship at tool-writing time, not of the tool abstraction -- a tool
synthesized from `GET /api/recipes` would wrap the vulnerable parameter and inherit the defect
exactly as the shell agent did.

Runs no model and costs nothing. Every request is a GET; nothing here writes.

Provenance
----------
This script was written on 2026-08-03 to commit a probe that had until then been run **by
hand**, with its five rows surviving only as a table in
`results/20260803T072053-repeats5-noisefloor-R1012/NOTES.md` §Gap 1, and quoted from there by
`findings/014-ceiling-test-replication-and-noise-floor.md`, whose own threats-to-validity
section names the missing script. Against SC-005 a stranger could not reproduce two of those
rows without rewriting the probe from prose. `RECORDED` below is that table, transcribed
case-for-case, and the script asserts against it rather than merely printing what it finds.

`CASE_SLUG` is a **sixth case that was not in the hand run.** It is in
`findings/014`'s published table, sourced there from `findings/012`, and it is marked
`in_hand_run: false` in the output so the two provenances never merge. Pass `--recorded-only`
to probe exactly the five hand-run cases and nothing else.

Usage:
  python3 fail_open_probe.py                  # six cases; five recorded plus the slug
  python3 fail_open_probe.py --recorded-only  # exactly the five rows of the hand run
Writes:
  results/fail-open-probe/<timestamp>.json
Exits non-zero if the live target disagrees with any recorded row.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import state as S  # noqa: E402
from mealie_client import connect, load_config  # noqa: E402

OUT_DIR = os.path.join(HERE, "results", "fail-open-probe")
EXPECTED_PATH = os.path.join(HERE, "tasks", "expected.json")

ENDPOINT = "/api/recipes"
CATEGORY_NAME = "Breakfast"

# The UUID the hand run probed with. Resolved live rather than trusted, and compared against
# this constant, so that a fixture reseeded under different identifiers is reported rather
# than silently probed with the wrong value.
RECORDED_UUID = "906d5da2-b4c9-4aee-97c7-57a30013e22e"

OMITTED = object()  # distinct from "" -- the parameter absent, not the parameter empty

# results/20260803T072053-repeats5-noisefloor-R1012/NOTES.md, section "Gap 1 -- the mechanism".
# `total` is what the historical shell trajectory read via `jq '.total'` before submitting.
RECORDED = [
    ("uuid", "<resolved Breakfast UUID>", 7, "filtered", True),
    ("name", CATEGORY_NAME, 60, "fail-open", True),
    ("nonsense", "zzzz-not-real", 60, "fail-open", True),
    ("empty", "", 60, "fail-open", True),
    ("omitted", OMITTED, 60, "collection size", True),
]

# Not part of the hand run. findings/014 carries it, sourced from findings/012.
CASE_SLUG = ("slug", "breakfast", 7, "filtered", False)


def request_path(value) -> str:
    """The path actually requested. Same encoding as MealieClient.get, which drops a None
    parameter entirely and renders an empty string as a bare `categories=`."""
    if value is OMITTED:
        return ENDPOINT
    return ENDPOINT + "?" + urllib.parse.urlencode({"categories": value})


def probe(base_url: str, token: str, path: str) -> tuple[int, dict]:
    """GET one path and return the status code alongside the decoded body.

    "Mealie answers HTTP 200" is the claim under test, so the status is measured rather
    than inferred from the absence of an exception. `MealieClient` raises on a non-2xx and
    never surfaces the code, which is why this does not go through it -- but the path it
    requests is built by `request_path`, so the encoding is still stated in one place.
    """
    req = urllib.request.Request(
        base_url.rstrip("/") + path,
        headers={"Accept": "application/json", "Authorization": "Bearer " + token},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            return resp.status, json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode()
        try:
            return exc.code, json.loads(body or "{}")
        except json.JSONDecodeError:
            return exc.code, {"_body": body[:300]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--recorded-only", action="store_true",
                    help="probe only the five cases the 2026-08-03 hand run recorded, "
                         "omitting the slug case that findings/014 sources from findings/012")
    args = ap.parse_args()

    cfg = load_config()
    api = connect()

    # The recorded totals are properties of one fixture on one application version. Reporting
    # them from a drifted instance would look like a reproduction and be nothing of the kind.
    about = api.get("/api/app/about") or {}
    if about.get("version") != cfg["target"]["app_version"]:
        raise SystemExit(
            f"TARGET DRIFT: config.json pins {cfg['target']['app_version']}, "
            f"the instance reports {about.get('version')!r}."
        )
    with open(EXPECTED_PATH, encoding="utf-8") as fh:
        frozen = json.load(fh)
    fixture_fp = S.fingerprint(S.snapshot(api))
    if fixture_fp != frozen["fixture_fingerprint"]:
        raise SystemExit(
            "FIXTURE DRIFT: the running instance does not match the frozen battery.\n"
            f"  expected {frozen['fixture_fingerprint']}\n  got      {fixture_fp}\n"
            "Re-run target/up.sh then seed/apply.py. The recorded totals below are "
            "fixture-specific and mean nothing against a different one."
        )

    # Both arms opened with this call. It is where the shell arm got the display name it then
    # substituted for the UUID, so resolving the same way is part of reproducing the failure.
    categories = api.get_all("/api/organizers/categories")
    match = next((c for c in categories if c["name"] == CATEGORY_NAME), None)
    if match is None:
        raise SystemExit(f"no {CATEGORY_NAME!r} category on this instance; cannot probe")
    uuid = match["id"]

    cases = list(RECORDED) if args.recorded_only else list(RECORDED) + [CASE_SLUG]

    print(f"fail-open probe against {cfg['target']['base_url']}{ENDPOINT}")
    print(f"  target {cfg['target']['app_version']}  fixture {fixture_fp[:16]}  "
          f"collection {len(api.get_all(ENDPOINT))} recipes")
    print(f"  {CATEGORY_NAME} -> slug {match['slug']!r} uuid {uuid} "
          f"({'matches' if uuid == RECORDED_UUID else 'DIFFERS FROM'} the recorded UUID)")
    print()
    print(f"  {'categories= value':<40}{'HTTP':>5}{'total':>7}  {'recorded':>9}  behaviour")

    rows = []
    mismatches = []
    for kind, value, recorded_total, behaviour, in_hand_run in cases:
        sent = uuid if kind == "uuid" else value
        path = request_path(sent)
        status, out = probe(cfg["target"]["base_url"], api.token, path)
        total = out.get("total")

        if sent is OMITTED:
            shown = "(parameter omitted)"
        elif sent == "":
            shown = "(the empty string)"
        else:
            shown = repr(sent)
        agrees = total == recorded_total and status == 200
        if total != recorded_total:
            mismatches.append(f"{shown}: recorded total {recorded_total}, got {total}")
        if status != 200:
            mismatches.append(f"{shown}: recorded HTTP 200, got {status}")
        print(f"  {shown:<40}{status:>5}{total:>7}  {recorded_total:>9}  "
              f"{behaviour}{'' if agrees else '   <-- DISAGREES WITH THE RECORD'}"
              f"{'' if in_hand_run else '   (not in the hand run)'}")

        rows.append({
            "case": kind,
            "sent": None if sent is OMITTED else sent,
            "parameter_omitted": sent is OMITTED,
            "request_path": path,
            "http_status": status,
            "total": total,
            "items_returned": len(out.get("items") or []),
            "recorded_total": recorded_total,
            "agrees_with_record": agrees,
            "behaviour": behaviour,
            "in_hand_run": in_hand_run,
        })

    collection = next(r["total"] for r in rows if r["case"] == "omitted")
    fail_open = [r for r in rows if r["total"] == collection and r["case"] != "omitted"]
    filtered = [r for r in rows if r["total"] != collection]

    os.makedirs(OUT_DIR, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%dT%H%M%S")
    out_path = os.path.join(OUT_DIR, f"{stamp}.json")
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump({
            "when": stamp,
            "probe": "mealie GET /api/recipes?categories= fail-open",
            "target": {k: cfg["target"][k] for k in ("name", "image", "app_version", "base_url")},
            "app_version_reported": about.get("version"),
            "fixture_fingerprint": fixture_fp,
            "battery_version": frozen["battery_version"],
            "category_name": CATEGORY_NAME,
            "category_uuid": uuid,
            "category_uuid_recorded": RECORDED_UUID,
            "category_uuid_matches_record": uuid == RECORDED_UUID,
            "collection_size": collection,
            "recorded_in": "results/20260803T072053-repeats5-noisefloor-R1012/NOTES.md",
            "rows": rows,
            "mismatches": mismatches,
            "model_spend_usd": 0.0,
        }, fh, indent=1)

    print()
    print(f"{len(fail_open)} of {len(rows) - 1} filter values failed open "
          f"(returned the whole {collection}-recipe collection); "
          f"{len(filtered)} filtered correctly.")
    print(f"wrote {out_path}")

    if mismatches:
        print("\nDISAGREES WITH THE RECORDED PROBE:")
        for m in mismatches:
            print(" ", m)
        raise SystemExit(1)
    print("\nOK. Every row reproduces the value recorded by the 2026-08-03 hand run.")


if __name__ == "__main__":
    main()
