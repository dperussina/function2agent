"""Independent ground truth, computed from the seeding fixture rather than from the oracle.

The Mealie instance the traces ran against was built by ceiling-test/seed/apply.py from
ceiling-test/seed/fixture_plan.json. Recomputing each task's answer from that fixture gives an
adjudication basis that shares no code and no constant with the oracle's `expected` values, so
agreement between the two is evidence rather than tautology.

Recipe-level rating is the mean of that recipe's per-user rating rows; recipes with no rows are
unrated. That reading is checked against ratings observed in the transcripts (see check_ratings).
"""

from __future__ import annotations

import json
import os
from collections import defaultdict

FIXTURE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "ceiling-test",
    "seed",
    "fixture_plan.json",
)


def load() -> dict:
    with open(FIXTURE, encoding="utf-8") as fh:
        return json.load(fh)


D = load()
RECIPES = {r["name"]: r for r in D["recipes"]}
MEALPLAN = D["mealplan"]


def ratings() -> dict[str, float]:
    acc = defaultdict(list)
    for row in D["ratings"]:
        acc[row["recipe"]].append(row["rating"])
    return {k: sum(v) / len(v) for k, v in acc.items()}


RATING = ratings()
PLAN_RECIPES = sorted({e["recipe"] for e in MEALPLAN})


def q(label: str, value) -> None:
    print(f"{label:<58} {value}")


def main() -> None:
    print(f"# fixture seed={D['seed']} sha={D['plan_sha256'][:16]}  recipes={len(RECIPES)}\n")

    # -- A01
    q("A01 recipes tagged 'weeknight'", sum(1 for r in RECIPES.values() if "weeknight" in r["tags"]))
    # -- A02 / A34
    q("A02/A34 distinct units", len(D["units"]))
    # -- A05
    q("A05 mealplan entries", len(MEALPLAN))
    # -- A36
    q("A36 shopping lists", len(D["shopping_lists"]))

    # -- A03/A04/A15/A20/A33  mean rating of plan recipes, unique, ignoring unrated
    rated = [RATING[n] for n in PLAN_RECIPES if n in RATING]
    mean = sum(rated) / len(rated)
    q("A03.. unique plan recipes", len(PLAN_RECIPES))
    q("A03.. of those, rated", len(rated))
    q("A03.. exact mean", f"{mean!r}  -> 2dp {mean:.2f}")

    # -- A06 sum prep times, Dessert category
    dess = [r for r in RECIPES.values() if "Dessert" in r["categories"]]
    q("A06 Dessert recipes", len(dess))
    q("A06 sum prep_minutes", sum(r["prep_minutes"] or 0 for r in dess))

    # -- A07/A11/A37 ingredient lines of breakfast-slot recipes, each recipe once
    bfast = sorted({e["recipe"] for e in MEALPLAN if e["entry_type"] == "breakfast"})
    q("A07.. distinct breakfast-slot recipes", len(bfast))
    q("A07.. sum ingredient lines (dedup)", sum(len(RECIPES[n]["ingredients"]) for n in bfast))
    occ = [e["recipe"] for e in MEALPLAN if e["entry_type"] == "breakfast"]
    q("A07.. (per-occurrence variant)", sum(len(RECIPES[n]["ingredients"]) for n in occ))

    # -- A08/A30 >=1 cup ingredient and >=1 gram ingredient
    def units_of(r):
        return {i["unit"] for i in r["ingredients"]}

    q(
        "A08/A30 cup AND gram",
        sum(1 for r in RECIPES.values() if "cup" in units_of(r) and "gram" in units_of(r)),
    )

    # -- A09/A25 >4 instruction steps
    q("A09/A25 >4 instruction steps", sum(1 for r in RECIPES.values() if len(r["instructions"]) > 4))

    # -- A10 Wok / Wok+Air Fryer
    wok = [r for r in RECIPES.values() if "Wok" in r["tools"]]
    both = [r for r in wok if "Air Fryer" in r["tools"]]
    q("A10 Wok count", len(wok))
    q("A10 Wok+AirFryer count", len(both))
    q("A10 wok names", ", ".join(sorted(r["name"] for r in wok)))

    # -- A12 plan recipes rated below three stars, unique
    below = [n for n in PLAN_RECIPES if n in RATING and RATING[n] < 3]
    q("A12 plan recipes rated <3 (unique)", len(below))
    q("A12    names", ", ".join(below))

    # -- A14 black garlic
    def uses(r, food):
        return any(i["food"] == food for i in r["ingredients"])

    bg = sorted(n for n, r in RECIPES.items() if uses(r, "black garlic"))
    q("A14 black garlic recipes", f"{len(bg)}: {', '.join(bg)}")

    # -- A16 cook==0 and tagged no-oven
    q(
        "A16 cook==0 & no-oven",
        sum(1 for r in RECIPES.values() if (r["cook_minutes"] or 0) == 0 and "no-oven" in r["tags"]),
    )

    # -- A17 longest prep+cook among plan recipes
    tot = {n: (RECIPES[n]["prep_minutes"] or 0) + (RECIPES[n]["cook_minutes"] or 0) for n in PLAN_RECIPES}
    best = max(tot.items(), key=lambda kv: kv[1])
    runner = sorted(tot.items(), key=lambda kv: -kv[1])[:3]
    q("A17 longest total on plan", f"{best}  top3={runner}")

    # -- A18 rating>=4 and not on plan
    hi = [n for n, v in RATING.items() if v >= 4]
    notplan = sorted(n for n in hi if n not in set(PLAN_RECIPES))
    q("A18 rating>=4 total", len(hi))
    q("A18 rating>=4 not on plan", f"{len(notplan)}")

    # -- A22 Breakfast category names
    bfc = sorted(n for n, r in RECIPES.items() if "Breakfast" in r["categories"])
    q("A22 Breakfast category", f"{len(bfc)}: {', '.join(bfc)}")

    # -- A23 batch-cook AND Dessert
    q(
        "A23 batch-cook & Dessert",
        sum(1 for r in RECIPES.values() if "batch-cook" in r["tags"] and "Dessert" in r["categories"]),
    )

    # -- A24 sumac AND wild rice
    q(
        "A24 sumac & wild rice",
        sum(1 for r in RECIPES.values() if uses(r, "sumac") and uses(r, "wild rice")),
    )

    # -- A26 >5 ingredients and servings>=6
    q(
        "A26 >5 ingredients & serves>=6",
        sum(1 for r in RECIPES.values() if len(r["ingredients"]) > 5 and (r["servings"] or 0) >= 6),
    )

    # -- A27 largest sum of ingredient quantities
    sums = {n: sum(i["quantity"] or 0 for i in r["ingredients"]) for n, r in RECIPES.items()}
    q("A27 largest quantity sum", sorted(sums.items(), key=lambda kv: -kv[1])[:3])

    # -- A28 sum of checked quantities across shopping lists
    checked = [(sl["name"], sum(i["quantity"] or 0 for i in sl["items"] if i["checked"])) for sl in D["shopping_lists"]]
    q("A28 checked total", f"{sum(v for _, v in checked)}  per-list={checked}")

    # -- A38 most unchecked items
    unchecked = sorted(
        ((sl["name"], sum(1 for i in sl["items"] if not i["checked"])) for sl in D["shopping_lists"]),
        key=lambda kv: -kv[1],
    )
    q("A38 most unchecked", unchecked)

    # -- A40 sumac
    q("A40 sumac recipes", sum(1 for r in RECIPES.values() if uses(r, "sumac")))

    # -- A35 dinner entries; of those batch-cook & total>60
    dinners = [e for e in MEALPLAN if e["entry_type"] == "dinner"]
    hits = [
        e
        for e in dinners
        if "batch-cook" in RECIPES[e["recipe"]]["tags"]
        and (RECIPES[e["recipe"]]["prep_minutes"] or 0) + (RECIPES[e["recipe"]]["cook_minutes"] or 0) > 60
    ]
    q("A35 dinner entries", len(dinners))
    q("A35 of those batch-cook & >60min", f"{len(hits)}  {[e['recipe'] for e in hits]}")

    check_ratings()


def check_ratings() -> None:
    """Cross-check the mean-of-user-rows reading against values quoted in the transcripts."""
    observed = {
        "Blistered Parsnip Crumble": 2.33,
        "Marbled Sorrel Bisque": 2.33,
        "Blistered Turnip Gratin": 1.67,
        "Silver Pepita Ragout": 1.67,
        "Velvet Parsnip Stew": 3.33,
        "Blistered Quince Pilaf": 3.33,
        "Hazel Parsnip Tartine": 4.5,
        "Amber Sumac Bisque": 5.0,
        "Charred Quince Chowder": 1.0,
    }
    print("\n# rating-model cross-check (transcript-quoted vs fixture-derived)")
    bad = 0
    for name, want in observed.items():
        got = RATING.get(name)
        ok = got is not None and abs(got - want) < 0.01
        bad += not ok
        print(f"  {'ok ' if ok else 'MISMATCH'} {name:<28} transcript={want}  fixture={got}")
    print(f"  -> {'model confirmed' if not bad else f'{bad} mismatches'}")


if __name__ == "__main__":
    main()
