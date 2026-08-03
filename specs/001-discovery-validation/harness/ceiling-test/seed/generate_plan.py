"""SPIKE - E7 ceiling test. Delete after 2026-11-30. Do not import from product code.

Deterministically generates the fixture plan for the ceiling test. Pure function of the
seed in config.json; no network, no clock, no randomness beyond the seeded PRNG.

Why generated rather than borrowed from Mealie's own demo data: an arm must not be able
to recall the answer from pretraining. Recipe names here are invented combinations that
do not exist in any published corpus, and every quantity, rating, time, and assignment is
drawn from the seeded PRNG (FR-009, and research/11-validation-plan.md 9.1).

Usage:  python3 generate_plan.py            # writes fixture_plan.json next to this file
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from mealie_client import load_config  # noqa: E402

PLAN_PATH = os.path.join(HERE, "fixture_plan.json")

ADJECTIVES = [
    "Charred", "Smoked", "Ember", "Velvet", "Copper", "Midnight", "Golden", "Rustic",
    "Amber", "Frosted", "Blistered", "Sunlit", "Wild", "Crimson", "Hazel", "Silver",
    "Bramble", "Thistle", "Juniper", "Marbled",
]
NOUNS = [
    "Fennel", "Barley", "Chard", "Pepita", "Quince", "Sorrel", "Millet", "Parsnip",
    "Farro", "Sumac", "Nettle", "Radish", "Chestnut", "Plantain", "Kohlrabi",
    "Tamarind", "Turnip", "Cardamom", "Persimmon", "Buckwheat",
]
FORMS = [
    "Skillet", "Pilaf", "Gratin", "Chowder", "Tartine", "Braise", "Crumble", "Galette",
    "Terrine", "Bisque", "Hash", "Loaf", "Stew", "Bake", "Ragout", "Fritters",
]

TAGS = [
    "weeknight", "make-ahead", "one-pot", "freezer-friendly", "high-protein",
    "low-sodium", "kid-approved", "picnic", "batch-cook", "no-oven",
    "budget", "celebration",
]
CATEGORIES = ["Breakfast", "Lunch", "Dinner", "Dessert", "Side", "Soup", "Snack", "Beverage"]
COOK_TOOLS = ["Air Fryer", "Dutch Oven", "Blender", "Stand Mixer", "Slow Cooker", "Wok"]

FOODS = [
    "red lentils", "smoked paprika", "greek yogurt", "sourdough starter", "pearl barley",
    "brown butter", "harissa paste", "preserved lemon", "sunflower seeds", "aged cheddar",
    "leeks", "celeriac", "black garlic", "fresh dill", "walnut oil", "rye flour",
    "buttermilk", "sherry vinegar", "sumac", "pomegranate molasses", "chickpea flour",
    "tahini", "wild rice", "sweet potato",
]
UNITS = [
    ("cup", "c"), ("tablespoon", "tbsp"), ("teaspoon", "tsp"), ("gram", "g"),
    ("milliliter", "ml"), ("clove", "clv"), ("sprig", "sprig"), ("pinch", "pinch"),
]
LABELS = ["Produce", "Pantry", "Dairy", "Bakery", "Frozen"]

USERS = [
    # (username, full name, email)
    ("dpike", "Dana Pike", "dana.pike@f2a.local"),
    ("nrowe", "Noor Rowe", "noor.rowe@f2a.local"),
    ("tvasquez", "Theo Vasquez", "theo.vasquez@f2a.local"),
    ("bfoley", "Bea Foley", "bea.foley@f2a.local"),
]

INSTRUCTION_VERBS = [
    "Heat the pan over medium heat and add the aromatics.",
    "Fold the dry ingredients into the wet mixture until just combined.",
    "Simmer uncovered, stirring occasionally, until reduced by half.",
    "Transfer to the prepared dish and level the surface.",
    "Rest off the heat for ten minutes before serving.",
    "Season to taste and finish with the reserved garnish.",
    "Toast the spices until fragrant, then grind coarsely.",
    "Deglaze the pan and scrape up the browned bits.",
]

N_RECIPES = 60
N_SHOPPING_LISTS = 5
N_COOKBOOKS = 4
MEALPLAN_START = "2026-08-03"
MEALPLAN_DAYS = 28


def _date(start: str, offset: int) -> str:
    import datetime

    d = datetime.date.fromisoformat(start) + datetime.timedelta(days=offset)
    return d.isoformat()


def build_plan(seed: int) -> dict:
    rng = random.Random(seed)

    names: list[str] = []
    seen: set[str] = set()
    while len(names) < N_RECIPES:
        n = f"{rng.choice(ADJECTIVES)} {rng.choice(NOUNS)} {rng.choice(FORMS)}"
        if n not in seen:
            seen.add(n)
            names.append(n)

    recipes = []
    for idx, name in enumerate(names):
        n_tags = rng.choice([0, 1, 1, 2, 2, 3])
        n_cats = rng.choice([1, 1, 2])
        n_tools = rng.choice([0, 0, 1, 2])
        n_ing = rng.randint(3, 8)
        ingredients = []
        used_foods: set[str] = set()
        for _ in range(n_ing):
            food = rng.choice(FOODS)
            if food in used_foods:
                continue
            used_foods.add(food)
            unit = rng.choice(UNITS)[0]
            qty = rng.choice([0.25, 0.5, 1, 1.5, 2, 2.5, 3, 4, 6, 8, 12, 100, 250])
            ingredients.append({"food": food, "unit": unit, "quantity": qty})
        prep = rng.choice([5, 10, 15, 20, 25, 30, 40, 45, 60])
        cook = rng.choice([0, 10, 15, 20, 25, 30, 45, 60, 90, 120])
        recipes.append(
            {
                "name": name,
                "description": (
                    f"A {rng.choice(['bright', 'hearty', 'delicate', 'smoky', 'brothy'])} dish "
                    f"built around {ingredients[0]['food']}."
                ),
                "prep_minutes": prep,
                "cook_minutes": cook,
                "servings": rng.choice([2, 3, 4, 4, 6, 8]),
                "yield_text": None,
                "tags": rng.sample(TAGS, n_tags),
                "categories": rng.sample(CATEGORIES, n_cats),
                "tools": rng.sample(COOK_TOOLS, n_tools),
                "ingredients": ingredients,
                "instructions": rng.sample(INSTRUCTION_VERBS, rng.randint(2, 5)),
                "order": idx,
            }
        )

    # user ratings and favourites -----------------------------------------
    ratings = []
    favorites = []
    for username, _full, _email in USERS:
        rated = rng.sample(names, rng.randint(10, 25))
        for rname in rated:
            ratings.append({"username": username, "recipe": rname, "rating": rng.randint(1, 5)})
        for fname in rng.sample(rated, rng.randint(2, 6)):
            favorites.append({"username": username, "recipe": fname})

    # meal plan ------------------------------------------------------------
    mealplan = []
    entry_types = ["breakfast", "lunch", "dinner", "side"]
    for day in range(MEALPLAN_DAYS):
        for etype in entry_types:
            if rng.random() < 0.32:
                mealplan.append(
                    {
                        "date": _date(MEALPLAN_START, day),
                        "entry_type": etype,
                        "recipe": rng.choice(names),
                    }
                )

    # shopping lists -------------------------------------------------------
    list_names = ["Weekly Staples", "Farmers Market", "Bulk Run", "Holiday Prep", "Quick Top-Up"]
    shopping_lists = []
    for lname in list_names[:N_SHOPPING_LISTS]:
        items = []
        for _ in range(rng.randint(4, 10)):
            items.append(
                {
                    "note": rng.choice(FOODS),
                    "quantity": rng.choice([1, 1, 2, 2, 3, 4, 6]),
                    "checked": rng.random() < 0.3,
                    "label": rng.choice(LABELS + [None, None]),
                }
            )
        shopping_lists.append({"name": lname, "items": items})

    # cookbooks ------------------------------------------------------------
    cookbook_specs = [
        ("Weeknight Rotation", "tags.name IN [\"weeknight\"]"),
        ("Freezer Stash", "tags.name IN [\"freezer-friendly\"]"),
        ("Soup Season", "recipeCategory.name IN [\"Soup\"]"),
        ("Sweet Endings", "recipeCategory.name IN [\"Dessert\"]"),
    ]
    cookbooks = [
        {"name": n, "query_filter": q, "description": f"Auto-collected: {n}."}
        for n, q in cookbook_specs[:N_COOKBOOKS]
    ]

    plan = {
        "seed": seed,
        "tags": TAGS,
        "categories": CATEGORIES,
        "cooking_tools": COOK_TOOLS,
        "foods": FOODS,
        "units": [{"name": n, "abbreviation": a} for n, a in UNITS],
        "labels": LABELS,
        "users": [{"username": u, "full_name": f, "email": e} for u, f, e in USERS],
        "recipes": recipes,
        "ratings": ratings,
        "favorites": favorites,
        "mealplan": mealplan,
        "shopping_lists": shopping_lists,
        "cookbooks": cookbooks,
    }
    payload = json.dumps(plan, sort_keys=True, separators=(",", ":")).encode()
    plan["plan_sha256"] = hashlib.sha256(payload).hexdigest()
    return plan


def main() -> None:
    seed = load_config()["fixture_seed"]
    plan = build_plan(seed)
    with open(PLAN_PATH, "w", encoding="utf-8") as fh:
        json.dump(plan, fh, indent=1, sort_keys=True)
    print(f"wrote {PLAN_PATH}")
    print(f"  seed              {plan['seed']}")
    print(f"  plan_sha256       {plan['plan_sha256']}")
    print(f"  recipes           {len(plan['recipes'])}")
    print(f"  ratings           {len(plan['ratings'])}")
    print(f"  favorites         {len(plan['favorites'])}")
    print(f"  mealplan entries  {len(plan['mealplan'])}")
    print(f"  shopping lists    {len(plan['shopping_lists'])}"
          f" ({sum(len(s['items']) for s in plan['shopping_lists'])} items)")
    print(f"  cookbooks         {len(plan['cookbooks'])}")


if __name__ == "__main__":
    main()
