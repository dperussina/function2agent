"""SPIKE - E7 ceiling test. Delete after 2026-11-30. Do not import from product code.

Applies fixture_plan.json to a freshly started Mealie instance, entirely over the
application's public HTTP API. Nothing is written to the database directly.

Run after target/up.sh. Idempotent only against a fresh container; re-seeding a dirty
instance is not supported and will produce duplicate organizers.

Usage:  python3 apply.py
"""

from __future__ import annotations

import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from mealie_client import MealieError, connect, load_config  # noqa: E402

PLAN_PATH = os.path.join(HERE, "fixture_plan.json")
USER_PASSWORD = "seed-Pass-123"


def main() -> None:
    with open(PLAN_PATH, encoding="utf-8") as fh:
        plan = json.load(fh)
    cfg = load_config()
    api = connect()
    t0 = time.time()

    print("organizers ...", end="", flush=True)
    tag_ids = {t: api.post("/api/organizers/tags", {"name": t})["id"] for t in plan["tags"]}
    cat_ids = {c: api.post("/api/organizers/categories", {"name": c})["id"] for c in plan["categories"]}
    tool_ids = {t: api.post("/api/organizers/tools", {"name": t})["id"] for t in plan["cooking_tools"]}
    for lab in plan["labels"]:
        api.post("/api/groups/labels", {"name": lab, "color": "#959595"})
    print(f" {len(tag_ids)} tags, {len(cat_ids)} categories, {len(tool_ids)} tools")

    print("foods and units ...", end="", flush=True)
    food_objs = {f: api.post("/api/foods", {"name": f}) for f in plan["foods"]}
    unit_objs = {u["name"]: api.post("/api/units", u) for u in plan["units"]}
    print(f" {len(food_objs)} foods, {len(unit_objs)} units")

    print("users ...", end="", flush=True)
    group = api.get("/api/admin/groups")["items"][0]["name"]
    household = api.get("/api/admin/households")["items"][0]["name"]
    users = {}
    for u in plan["users"]:
        created = api.post(
            "/api/admin/users",
            {
                "username": u["username"], "fullName": u["full_name"], "email": u["email"],
                "password": USER_PASSWORD, "group": group, "household": household,
                "admin": False, "advanced": False, "canInvite": False,
                "canManage": False, "canOrganize": True,
            },
        )
        users[u["username"]] = {"id": created["id"], "email": u["email"]}
    print(f" {len(users)}")

    print("recipes ...", end="", flush=True)
    tag_objs = {t["name"]: t for t in api.get_all("/api/organizers/tags")}
    cat_objs = {c["name"]: c for c in api.get_all("/api/organizers/categories")}
    ctool_objs = {t["name"]: t for t in api.get_all("/api/organizers/tools")}
    slug_by_name = {}
    for i, r in enumerate(plan["recipes"]):
        slug = api.post("/api/recipes", {"name": r["name"]})
        slug_by_name[r["name"]] = slug
        full = api.get(f"/api/recipes/{slug}")
        full["description"] = r["description"]
        full["prepTime"] = f"{r['prep_minutes']} minutes"
        full["cookTime"] = f"{r['cook_minutes']} minutes"
        full["performTime"] = f"{r['cook_minutes']} minutes"
        full["recipeServings"] = r["servings"]
        full["recipeYield"] = f"{r['servings']} servings"
        full["tags"] = [tag_objs[t] for t in r["tags"]]
        full["recipeCategory"] = [cat_objs[c] for c in r["categories"]]
        full["tools"] = [ctool_objs[t] for t in r["tools"]]
        full["recipeIngredient"] = [
            {
                "quantity": ing["quantity"],
                "unit": unit_objs[ing["unit"]],
                "food": food_objs[ing["food"]],
                "note": "",
                "title": None,
                "originalText": None,
                "display": "",
                "referenceId": f"{i:08d}-0000-4000-8000-{n:012d}",
            }
            for n, ing in enumerate(r["ingredients"])
        ]
        full["recipeInstructions"] = [
            {"title": "", "summary": "", "text": step, "ingredientReferences": []}
            for step in r["instructions"]
        ]
        api.put(f"/api/recipes/{slug}", full)
        if (i + 1) % 20 == 0:
            print(f" {i + 1}", end="", flush=True)
    print(f" -> {len(slug_by_name)} recipes")

    print("ratings and favourites ...", end="", flush=True)
    from mealie_client import MealieClient

    sessions = {
        name: MealieClient(cfg["target"]["base_url"], info["email"], USER_PASSWORD)
        for name, info in users.items()
    }
    for r in plan["ratings"]:
        s = sessions[r["username"]]
        s.post(f"/api/users/{users[r['username']]['id']}/ratings/{slug_by_name[r['recipe']]}",
               {"rating": r["rating"], "isFavorite": False})
    for f in plan["favorites"]:
        s = sessions[f["username"]]
        s.post(f"/api/users/{users[f['username']]['id']}/favorites/{slug_by_name[f['recipe']]}", None)
    print(f" {len(plan['ratings'])} ratings, {len(plan['favorites'])} favourites")

    print("meal plan ...", end="", flush=True)
    recipe_ids = {name: api.get(f"/api/recipes/{slug}")["id"] for name, slug in slug_by_name.items()}
    for m in plan["mealplan"]:
        api.post(
            "/api/households/mealplans",
            {"date": m["date"], "entryType": m["entry_type"], "title": "", "text": "",
             "recipeId": recipe_ids[m["recipe"]]},
        )
    print(f" {len(plan['mealplan'])} entries")

    print("shopping lists ...", end="", flush=True)
    labels = {lab["name"]: lab["id"] for lab in api.get_all("/api/groups/labels")}
    for sl in plan["shopping_lists"]:
        created = api.post("/api/households/shopping/lists", {"name": sl["name"]})
        for item in sl["items"]:
            body = {
                "shoppingListId": created["id"], "note": item["note"],
                "quantity": item["quantity"], "isFood": False, "checked": item["checked"],
            }
            if item["label"]:
                body["labelId"] = labels[item["label"]]
            api.post("/api/households/shopping/items", body)
    print(f" {len(plan['shopping_lists'])}")

    print("cookbooks ...", end="", flush=True)
    for cb in plan["cookbooks"]:
        created = api.post("/api/households/cookbooks", {"name": cb["name"]})
        created["description"] = cb["description"]
        created["queryFilterString"] = cb["query_filter"]
        created["public"] = False
        try:
            api.put(f"/api/households/cookbooks/{created['id']}", created)
        except MealieError as exc:
            print(f"\n  WARNING cookbook filter not applied for {cb['name']}: {exc}")
    print(f" {len(plan['cookbooks'])}")

    print(f"\nseeded in {time.time() - t0:.1f}s  (plan_sha256 {plan['plan_sha256'][:16]})")


if __name__ == "__main__":
    main()
