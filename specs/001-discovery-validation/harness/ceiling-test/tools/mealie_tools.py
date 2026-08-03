"""SPIKE - E7 ceiling test. Delete after 2026-11-30. Do not import from product code.

Arm A's tool set: hand-written, deliberately good domain tools over Mealie's external
HTTP API. This arm measures the *ceiling* of the product idea, so these are written the
way a careful engineer who knows both the application and how models read tool schemas
would write them, not the way a first-pass generator would.

Design rules applied, and the one deliberately not applied
----------------------------------------------------------
* Names are verb-first and domain-shaped; descriptions are written for a model reader and
  say when to use the tool and what it returns.
* Parameter schemas are tight: enums where the domain is closed, required fields marked,
  no free-form "options" bag.
* Errors are actionable. "No recipe matches 'stew'" is useless; "'stew' matches 5 recipes:
  ... - call again with the full name" tells the model its next move.
* Returns are compact line-oriented text rather than raw JSON, because raw API envelopes
  are mostly punctuation and burn context for nothing.
* A tool may **compose** several of the application's own operations and shape the result
  (that composition is precisely the value under test). A tool may **not** implement
  analysis the application does not itself perform: there is deliberately no generic
  "group by X and sum Y" tool, because that would embed the oracle in the tool set and
  make a positive result meaningless. Arithmetic over returned rows is left to the model,
  exactly as it is for the baseline.

Every call goes over HTTP to the running application. Nothing is executed in-process
against the target and nothing touches its database.
"""

from __future__ import annotations

import datetime
from typing import Any, Callable

from mealie_client import MealieClient, MealieError

# ---------------------------------------------------------------------------
# a small cache so composed tools do not re-fetch 60 recipes per call
# ---------------------------------------------------------------------------


class RecipeIndex:
    def __init__(self, api: MealieClient):
        self.api = api
        self._detail: dict[str, dict] = {}
        self._summaries: list[dict] | None = None

    def invalidate(self) -> None:
        self._detail.clear()
        self._summaries = None

    def summaries(self) -> list[dict]:
        if self._summaries is None:
            self._summaries = self.api.get_all("/api/recipes")
        return self._summaries

    def detail(self, slug: str) -> dict:
        if slug not in self._detail:
            self._detail[slug] = self.api.get(f"/api/recipes/{slug}")
        return self._detail[slug]

    def all_details(self) -> list[dict]:
        return [self.detail(s["slug"]) for s in self.summaries()]


def _minutes(text: str | None) -> float | None:
    if not text:
        return None
    digits = "".join(c for c in text if c.isdigit() or c == ".")
    try:
        return float(digits) if digits else None
    except ValueError:
        return None


def _row(d: dict) -> str:
    tags = "|".join(sorted(t["name"] for t in (d.get("tags") or []))) or "-"
    cats = "|".join(sorted(c["name"] for c in (d.get("recipeCategory") or []))) or "-"
    tools = "|".join(sorted(t["name"] for t in (d.get("tools") or []))) or "-"
    prep = _minutes(d.get("prepTime"))
    cook = _minutes(d.get("cookTime"))
    rating = d.get("rating")
    return (
        f"{d['name']} [slug={d['slug']}] prep={prep or 0:g}min cook={cook or 0:g}min "
        f"serves={float(d.get('recipeServings') or 0):g} rating={rating if rating is not None else 'none'} "
        f"tags={tags} categories={cats} tools={tools}"
    )


def _resolve_recipe(idx: RecipeIndex, ref: str) -> dict:
    ref_l = ref.strip().lower()
    summaries = idx.summaries()
    exact = [s for s in summaries if s["name"].lower() == ref_l or s["slug"].lower() == ref_l]
    if len(exact) == 1:
        return idx.detail(exact[0]["slug"])
    partial = [s for s in summaries if ref_l in s["name"].lower()]
    if len(partial) == 1:
        return idx.detail(partial[0]["slug"])
    if not partial:
        raise ValueError(
            f"No recipe matches {ref!r}. Use search_recipes with a name fragment to find the "
            f"correct name first."
        )
    names = ", ".join(sorted(s["name"] for s in partial)[:12])
    raise ValueError(
        f"{ref!r} is ambiguous: {len(partial)} recipes match ({names}). "
        f"Call again with the exact recipe name."
    )


# ---------------------------------------------------------------------------
# tool implementations
# ---------------------------------------------------------------------------


def build_tools(
    api: MealieClient, surface: str = "v2"
) -> tuple[list[dict], dict[str, Callable[..., str]]]:
    idx = RecipeIndex(api)

    # -- reads ---------------------------------------------------------------

    def _select(
        name_contains: str | None = None,
        tag: str | None = None,
        category: str | None = None,
        cooking_tool: str | None = None,
        ingredient: str | None = None,
        max_prep_minutes: float | None = None,
        max_total_minutes: float | None = None,
        min_servings: float | None = None,
        has_rating: bool | None = None,
        untagged_only: bool | None = None,
    ) -> list[dict]:
        """The one filter vocabulary. search_recipes and aggregate_recipes share it, so the
        aggregation tool has exactly the selectivity the search tool already had and no more."""
        rows = idx.all_details()
        if name_contains:
            rows = [r for r in rows if name_contains.lower() in r["name"].lower()]
        if tag:
            rows = [r for r in rows if any(t["name"].lower() == tag.lower() for t in (r.get("tags") or []))]
        if category:
            rows = [r for r in rows if any(c["name"].lower() == category.lower() for c in (r.get("recipeCategory") or []))]
        if cooking_tool:
            rows = [r for r in rows if any(t["name"].lower() == cooking_tool.lower() for t in (r.get("tools") or []))]
        if ingredient:
            rows = [
                r for r in rows
                if any(i.get("food") and ingredient.lower() == i["food"]["name"].lower()
                       for i in (r.get("recipeIngredient") or []))
            ]
        if max_prep_minutes is not None:
            rows = [r for r in rows if (_minutes(r.get("prepTime")) or 0) <= max_prep_minutes]
        if max_total_minutes is not None:
            rows = [
                r for r in rows
                if (_minutes(r.get("prepTime")) or 0) + (_minutes(r.get("cookTime")) or 0) <= max_total_minutes
            ]
        if min_servings is not None:
            rows = [r for r in rows if float(r.get("recipeServings") or 0) >= min_servings]
        if has_rating is not None:
            rows = [r for r in rows if (r.get("rating") is not None) == has_rating]
        if untagged_only:
            rows = [r for r in rows if not (r.get("tags") or [])]
        rows.sort(key=lambda r: r["name"])
        return rows

    def search_recipes(count_only: bool = False, limit: int = 60, **filters) -> str:
        rows = _select(**filters)
        if count_only:
            return f"matches={len(rows)}"
        head = f"matches={len(rows)}" + (f" (showing first {limit})" if len(rows) > limit else "")
        return head + "\n" + "\n".join(_row(r) for r in rows[:limit])

    # Scalar properties of a single recipe. This is a complete enumeration of what one recipe
    # yields as a number, not a selection: any subset would have to be justified by something,
    # and the only thing available to justify one would be the tasks.
    _FIELDS: dict[str, Callable[[dict], float]] = {
        "prep_minutes": lambda r: _minutes(r.get("prepTime")) or 0.0,
        "cook_minutes": lambda r: _minutes(r.get("cookTime")) or 0.0,
        "total_minutes": lambda r: (_minutes(r.get("prepTime")) or 0.0) + (_minutes(r.get("cookTime")) or 0.0),
        "servings": lambda r: float(r.get("recipeServings") or 0),
        "rating": lambda r: float(r["rating"]) if r.get("rating") is not None else float("nan"),
        "ingredient_count": lambda r: float(len(r.get("recipeIngredient") or [])),
        "instruction_count": lambda r: float(len(r.get("recipeInstructions") or [])),
        "tag_count": lambda r: float(len(r.get("tags") or [])),
        "category_count": lambda r: float(len(r.get("recipeCategory") or [])),
        "tool_count": lambda r: float(len(r.get("tools") or [])),
        "total_ingredient_quantity": lambda r: sum(
            float(i.get("quantity") or 0) for i in (r.get("recipeIngredient") or [])
        ),
    }

    def aggregate_recipes(metric: str, field: str | None = None, **filters) -> str:
        rows = _select(**filters)
        metric = (metric or "").strip().lower()
        if metric not in {"count", "sum", "mean", "min", "max", "argmax", "argmin"}:
            return ("metric must be one of: count, sum, mean, min, max, argmax, argmin.")
        if metric == "count":
            return f"count={len(rows)}"
        if field not in _FIELDS:
            return (f"field must be one of: {', '.join(sorted(_FIELDS))}. "
                    f"Got {field!r}.")
        get = _FIELDS[field]
        pairs = [(r["name"], get(r)) for r in rows]
        pairs = [(n, v) for n, v in pairs if v == v]  # drop NaN (unrated) for rating
        if not pairs:
            return f"{metric}({field})=undefined: no recipe matched the filters."
        vals = [v for _, v in pairs]
        if metric == "sum":
            return f"sum({field})={sum(vals):g} over {len(vals)} recipes"
        if metric == "mean":
            return f"mean({field})={sum(vals) / len(vals):.6g} over {len(vals)} recipes"
        if metric == "min":
            return f"min({field})={min(vals):g} over {len(vals)} recipes"
        if metric == "max":
            return f"max({field})={max(vals):g} over {len(vals)} recipes"
        best = max(vals) if metric == "argmax" else min(vals)
        winners = sorted(n for n, v in pairs if v == best)
        if len(winners) > 1:
            return (f"{metric}({field}) is a tie at {best:g} between {len(winners)} recipes: "
                    + ", ".join(winners))
        return f"{metric}({field})={winners[0]!r} (value {best:g}, over {len(vals)} recipes)"

    def get_recipe(recipe: str) -> str:
        d = _resolve_recipe(idx, recipe)
        ings = d.get("recipeIngredient") or []
        lines = [_row(d), f"description: {d.get('description') or '-'}"]
        lines.append(f"ingredients ({len(ings)}):")
        for i in ings:
            food = (i.get("food") or {}).get("name") or (i.get("note") or "?")
            unit = (i.get("unit") or {}).get("name") or ""
            lines.append(f"  {float(i.get('quantity') or 0):g} {unit} {food}".rstrip())
        steps = d.get("recipeInstructions") or []
        lines.append(f"instruction steps: {len(steps)}")
        lines.append(f"last made: {d.get('lastMade') or 'never'}; added: {d.get('dateAdded')}")
        return "\n".join(lines)

    def find_recipes_by_ingredient(ingredient: str) -> str:
        matches = []
        for d in idx.all_details():
            for i in d.get("recipeIngredient") or []:
                if i.get("food") and i["food"]["name"].lower() == ingredient.lower():
                    matches.append((d["name"], float(i.get("quantity") or 0),
                                    (i.get("unit") or {}).get("name") or ""))
                    break
        if not matches:
            known = sorted({f["name"] for f in api.get_all("/api/foods")})
            return (f"No recipe uses {ingredient!r}. Known ingredient names include: "
                    + ", ".join(known[:30]))
        matches.sort()
        body = "\n".join(f"{n} ({q:g} {u})".rstrip() for n, q, u in matches)
        return f"count={len(matches)}\n{body}"

    def list_tags() -> str:
        details = idx.all_details()
        out = []
        for t in api.get_all("/api/organizers/tags"):
            n = sum(1 for d in details if any(x["name"] == t["name"] for x in (d.get("tags") or [])))
            out.append(f"{t['name']} (recipes={n})")
        return "\n".join(sorted(out))

    def list_categories() -> str:
        details = idx.all_details()
        out = []
        for c in api.get_all("/api/organizers/categories"):
            n = sum(1 for d in details if any(x["name"] == c["name"] for x in (d.get("recipeCategory") or [])))
            out.append(f"{c['name']} (recipes={n})")
        return "\n".join(sorted(out))

    def list_cooking_tools() -> str:
        details = idx.all_details()
        out = []
        for t in api.get_all("/api/organizers/tools"):
            n = sum(1 for d in details if any(x["name"] == t["name"] for x in (d.get("tools") or [])))
            out.append(f"{t['name']} (recipes={n})")
        return "\n".join(sorted(out))

    def list_ingredients() -> str:
        details = idx.all_details()
        out = []
        for f in api.get_all("/api/foods"):
            n = sum(
                1 for d in details
                if any(i.get("food") and i["food"]["name"] == f["name"] for i in (d.get("recipeIngredient") or []))
            )
            out.append(f"{f['name']} (recipes={n})")
        return f"count={len(out)}\n" + "\n".join(sorted(out))

    def list_units() -> str:
        us = api.get_all("/api/units")
        return f"count={len(us)}\n" + "\n".join(
            sorted(f"{u['name']} ({u.get('abbreviation') or '-'})" for u in us)
        )

    def get_meal_plan(start_date: str | None = None, end_date: str | None = None) -> str:
        entries = api.get_all("/api/households/mealplans")
        by_id = {s["id"]: s["name"] for s in idx.summaries()}
        rows = []
        for e in entries:
            if start_date and e["date"] < start_date:
                continue
            if end_date and e["date"] > end_date:
                continue
            d = datetime.date.fromisoformat(e["date"])
            rows.append(
                f"{e['date']} ({d.strftime('%A')}) {e.get('entryType')}: "
                f"{by_id.get(e.get('recipeId'), e.get('title') or 'untitled')}"
            )
        rows.sort()
        return f"entries={len(rows)}\n" + "\n".join(rows)

    def list_shopping_lists() -> str:
        out = []
        for meta in api.get_all("/api/households/shopping/lists"):
            d = api.get(f"/api/households/shopping/lists/{meta['id']}")
            items = d.get("listItems") or []
            checked = sum(1 for i in items if i.get("checked"))
            out.append(
                f"{d['name']}: items={len(items)} checked={checked} unchecked={len(items) - checked} "
                f"total_quantity={sum(float(i.get('quantity') or 0) for i in items):g}"
            )
        return f"lists={len(out)}\n" + "\n".join(sorted(out))

    def _find_list(name: str) -> dict:
        lists = api.get_all("/api/households/shopping/lists")
        exact = [x for x in lists if x["name"].lower() == name.strip().lower()]
        if exact:
            return api.get(f"/api/households/shopping/lists/{exact[0]['id']}")
        near = [x["name"] for x in lists if name.strip().lower() in x["name"].lower()]
        raise ValueError(
            f"No shopping list named {name!r}. Existing lists: "
            + ", ".join(sorted(x["name"] for x in lists))
            + (f". Did you mean {near[0]!r}?" if near else "")
        )

    def get_shopping_list(list_name: str) -> str:
        d = _find_list(list_name)
        items = d.get("listItems") or []
        body = "\n".join(
            f"  [{'x' if i.get('checked') else ' '}] {float(i.get('quantity') or 0):g} "
            f"{i.get('note') or (i.get('food') or {}).get('name') or '?'} "
            f"(label={(i.get('label') or {}).get('name') or '-'})"
            for i in items
        )
        return f"{d['name']}: items={len(items)}\n{body}"

    def list_cookbooks() -> str:
        cbs = api.get_all("/api/households/cookbooks")
        return f"count={len(cbs)}\n" + "\n".join(
            sorted(f"{c['name']} [slug={c.get('slug')}] filter={c.get('queryFilterString') or '-'}" for c in cbs)
        )

    def list_users() -> str:
        us = api.get("/api/admin/users")["items"]
        return f"count={len(us)}\n" + "\n".join(
            sorted(f"{u['username']} ({u.get('fullName')}) admin={bool(u.get('admin'))}" for u in us)
        )

    # -- writes --------------------------------------------------------------

    def create_shopping_list(name: str) -> str:
        created = api.post("/api/households/shopping/lists", {"name": name})
        return f"created shopping list {created['name']!r}"

    def add_shopping_list_item(list_name: str, item: str, quantity: float = 1) -> str:
        d = _find_list(list_name)
        api.post(
            "/api/households/shopping/items",
            {"shoppingListId": d["id"], "note": item, "quantity": quantity,
             "isFood": False, "checked": False},
        )
        return f"added {quantity:g} x {item!r} to {d['name']!r} (unchecked)"

    def set_shopping_list_items_checked(list_name: str, checked: bool, item: str | None = None) -> str:
        d = _find_list(list_name)
        items = d.get("listItems") or []
        targets = items if item is None else [
            i for i in items if item.lower() in (i.get("note") or "").lower()
        ]
        if not targets:
            return (f"No item on {d['name']!r} matches {item!r}. Items present: "
                    + ", ".join((i.get("note") or "?") for i in items))
        for i in targets:
            body = dict(i)
            body["checked"] = checked
            api.put(f"/api/households/shopping/items/{i['id']}", body)
        return f"set checked={checked} on {len(targets)} item(s) of {d['name']!r}"

    def add_meal_plan_entry(date: str, entry_type: str, recipe: str) -> str:
        d = _resolve_recipe(idx, recipe)
        api.post(
            "/api/households/mealplans",
            {"date": date, "entryType": entry_type, "title": "", "text": "", "recipeId": d["id"]},
        )
        return f"scheduled {d['name']!r} on {date} as {entry_type}"

    def create_recipe(
        name: str,
        servings: float | None = None,
        prep_minutes: float | None = None,
        cook_minutes: float | None = None,
        description: str | None = None,
        tags: list[str] | None = None,
        categories: list[str] | None = None,
    ) -> str:
        slug = api.post("/api/recipes", {"name": name})
        idx.invalidate()
        full = api.get(f"/api/recipes/{slug}")
        if servings is not None:
            full["recipeServings"] = servings
            full["recipeYield"] = f"{servings:g} servings"
        if prep_minutes is not None:
            full["prepTime"] = f"{prep_minutes:g} minutes"
        if cook_minutes is not None:
            full["cookTime"] = f"{cook_minutes:g} minutes"
        if description is not None:
            full["description"] = description
        if tags:
            full["tags"] = _resolve_organizers("/api/organizers/tags", tags)
        if categories:
            full["recipeCategory"] = _resolve_organizers("/api/organizers/categories", categories)
        api.put(f"/api/recipes/{slug}", full)
        idx.invalidate()
        return f"created recipe {name!r} [slug={slug}]"

    def _resolve_organizers(path: str, names: list[str]) -> list[dict]:
        existing = {o["name"].lower(): o for o in api.get_all(path)}
        out = []
        for n in names:
            o = existing.get(n.strip().lower())
            if o is None:
                o = api.post(path, {"name": n.strip()})
            out.append(o)
        return out

    def update_recipe(
        recipe: str,
        servings: float | None = None,
        prep_minutes: float | None = None,
        cook_minutes: float | None = None,
        description: str | None = None,
    ) -> str:
        full = dict(_resolve_recipe(idx, recipe))
        changed = []
        if servings is not None:
            full["recipeServings"] = servings
            changed.append("servings")
        if prep_minutes is not None:
            full["prepTime"] = f"{prep_minutes:g} minutes"
            changed.append("prep")
        if cook_minutes is not None:
            full["cookTime"] = f"{cook_minutes:g} minutes"
            changed.append("cook")
        if description is not None:
            full["description"] = description
            changed.append("description")
        if not changed:
            return "Nothing to change: supply at least one of servings, prep_minutes, cook_minutes, description."
        api.put(f"/api/recipes/{full['slug']}", full)
        idx.invalidate()
        return f"updated {full['name']!r}: {', '.join(changed)}"

    def set_recipe_tags(recipe: str, tags: list[str], mode: str = "add") -> str:
        full = dict(_resolve_recipe(idx, recipe))
        resolved = _resolve_organizers("/api/organizers/tags", tags)
        if mode == "add":
            have = {t["name"] for t in (full.get("tags") or [])}
            full["tags"] = (full.get("tags") or []) + [t for t in resolved if t["name"] not in have]
        elif mode == "replace":
            full["tags"] = resolved
        else:
            return "mode must be 'add' or 'replace'."
        api.put(f"/api/recipes/{full['slug']}", full)
        idx.invalidate()
        return f"{full['name']!r} now tagged: " + ", ".join(sorted(t["name"] for t in full["tags"]))

    # -- registry ------------------------------------------------------------

    def S(**props):
        return props

    specs: list[dict] = [
        {
            "name": "search_recipes",
            "description": (
                "Find recipes by any combination of filters and get a one-line summary of each "
                "(name, slug, prep and cook minutes, servings, rating, tags, categories, tools). "
                "This is the main read tool: prefer it over fetching recipes one at a time. Set "
                "count_only=true when you only need how many match. Filters combine with AND. "
                "Filter values are matched case-insensitively and, for tag/category/tool/"
                "ingredient, must be the exact name - use list_tags, list_categories, "
                "list_cooking_tools or list_ingredients to discover valid values."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "name_contains": S(type="string", description="Substring of the recipe name."),
                    "tag": S(type="string", description="Exact tag name, e.g. 'weeknight'."),
                    "category": S(type="string", description="Exact category name, e.g. 'Dessert'."),
                    "cooking_tool": S(type="string", description="Exact tool name, e.g. 'Air Fryer'."),
                    "ingredient": S(type="string", description="Exact ingredient (food) name, e.g. 'sumac'."),
                    "max_prep_minutes": S(type="number", description="Keep recipes whose prep time is at most this."),
                    "max_total_minutes": S(type="number", description="Keep recipes whose prep+cook time is at most this."),
                    "min_servings": S(type="number", description="Keep recipes serving at least this many."),
                    "has_rating": S(type="boolean", description="true keeps only rated recipes; false keeps only unrated."),
                    "untagged_only": S(type="boolean", description="true keeps only recipes with no tags at all."),
                    "count_only": S(type="boolean", description="Return only the match count. Cheap; use it for counting questions."),
                    "limit": S(type="integer", description="Maximum rows to return. Default 60 (the whole collection)."),
                },
            },
            "fn": search_recipes,
            "effect": "read",
        },
        {
            "name": "aggregate_recipes",
            "description": (
                "Compute one number over a set of recipes and return only that number, without "
                "returning the recipes themselves. Takes the same filters as search_recipes, "
                "combined with AND, and applies the metric to the recipes that match. Use this "
                "instead of fetching recipes and adding them up yourself. metric=count needs no "
                "field; every other metric needs one. argmax and argmin return the name of the "
                "recipe holding the extreme value, and say so explicitly if there is a tie."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "metric": S(
                        type="string",
                        enum=["count", "sum", "mean", "min", "max", "argmax", "argmin"],
                        description="Which statistic to compute over the matching recipes.",
                    ),
                    "field": S(
                        type="string",
                        enum=sorted(_FIELDS),
                        description="Which per-recipe number to aggregate. Not needed for count.",
                    ),
                    "name_contains": S(type="string", description="Substring of the recipe name."),
                    "tag": S(type="string", description="Exact tag name, e.g. 'weeknight'."),
                    "category": S(type="string", description="Exact category name, e.g. 'Dessert'."),
                    "cooking_tool": S(type="string", description="Exact tool name, e.g. 'Air Fryer'."),
                    "ingredient": S(type="string", description="Exact ingredient (food) name, e.g. 'sumac'."),
                    "max_prep_minutes": S(type="number", description="Keep recipes whose prep time is at most this."),
                    "max_total_minutes": S(type="number", description="Keep recipes whose prep+cook time is at most this."),
                    "min_servings": S(type="number", description="Keep recipes serving at least this many."),
                    "has_rating": S(type="boolean", description="true keeps only rated recipes; false keeps only unrated."),
                    "untagged_only": S(type="boolean", description="true keeps only recipes with no tags at all."),
                },
                "required": ["metric"],
            },
            "fn": aggregate_recipes,
            "effect": "read",
            "surface": "v2",
        },
        {
            "name": "get_recipe",
            "description": (
                "Full detail for one recipe: times, servings, rating, tags, categories, tools, the "
                "complete ingredient list with quantities and units, and the number of instruction "
                "steps. Accepts a recipe name or slug; a unique partial name also works, and an "
                "ambiguous one returns the candidates."
            ),
            "input_schema": {
                "type": "object",
                "properties": {"recipe": S(type="string", description="Recipe name or slug.")},
                "required": ["recipe"],
            },
            "fn": get_recipe,
            "effect": "read",
        },
        {
            "name": "find_recipes_by_ingredient",
            "description": (
                "List every recipe that uses a given ingredient, with the quantity and unit each "
                "uses. Answers 'which recipes contain X' without fetching recipes one by one. If "
                "the ingredient is unknown, the error lists valid ingredient names."
            ),
            "input_schema": {
                "type": "object",
                "properties": {"ingredient": S(type="string", description="Exact ingredient name, e.g. 'black garlic'.")},
                "required": ["ingredient"],
            },
            "fn": find_recipes_by_ingredient,
            "effect": "read",
        },
        {
            "name": "list_tags",
            "description": "Every tag defined on this instance, each with the number of recipes carrying it.",
            "input_schema": {"type": "object", "properties": {}},
            "fn": list_tags,
            "effect": "read",
        },
        {
            "name": "list_categories",
            "description": "Every recipe category defined on this instance, each with its recipe count.",
            "input_schema": {"type": "object", "properties": {}},
            "fn": list_categories,
            "effect": "read",
        },
        {
            "name": "list_cooking_tools",
            "description": "Every cooking tool (equipment) defined on this instance, each with its recipe count.",
            "input_schema": {"type": "object", "properties": {}},
            "fn": list_cooking_tools,
            "effect": "read",
        },
        {
            "name": "list_ingredients",
            "description": (
                "Every ingredient (food) defined on this instance, each with the number of recipes "
                "that use it. Use this to discover exact ingredient names before filtering."
            ),
            "input_schema": {"type": "object", "properties": {}},
            "fn": list_ingredients,
            "effect": "read",
        },
        {
            "name": "list_units",
            "description": "Every measurement unit defined on this instance, with its abbreviation.",
            "input_schema": {"type": "object", "properties": {}},
            "fn": list_units,
            "effect": "read",
        },
        {
            "name": "get_meal_plan",
            "description": (
                "The meal plan as scheduled entries, one line each: date, weekday, meal slot, and "
                "the recipe scheduled. Optionally restrict to a date range (inclusive, ISO "
                "YYYY-MM-DD). Omit both dates to get the whole plan."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "start_date": S(type="string", description="Earliest date to include, ISO YYYY-MM-DD."),
                    "end_date": S(type="string", description="Latest date to include, ISO YYYY-MM-DD."),
                },
            },
            "fn": get_meal_plan,
            "effect": "read",
        },
        {
            "name": "list_shopping_lists",
            "description": (
                "Every shopping list with its item count, how many are checked off, how many are "
                "still outstanding, and the sum of item quantities."
            ),
            "input_schema": {"type": "object", "properties": {}},
            "fn": list_shopping_lists,
            "effect": "read",
        },
        {
            "name": "get_shopping_list",
            "description": (
                "The items on one shopping list, each with its quantity, checked state and label. "
                "If the name does not match, the error lists the lists that exist."
            ),
            "input_schema": {
                "type": "object",
                "properties": {"list_name": S(type="string", description="Exact shopping list name.")},
                "required": ["list_name"],
            },
            "fn": get_shopping_list,
            "effect": "read",
        },
        {
            "name": "list_cookbooks",
            "description": "Every cookbook, with its slug and the filter expression that populates it.",
            "input_schema": {"type": "object", "properties": {}},
            "fn": list_cookbooks,
            "effect": "read",
        },
        {
            "name": "list_users",
            "description": "Every user account on this instance, with full name and whether it is an administrator.",
            "input_schema": {"type": "object", "properties": {}},
            "fn": list_users,
            "effect": "read",
        },
        {
            "name": "create_shopping_list",
            "description": "Create an empty shopping list. Add items to it afterwards with add_shopping_list_item.",
            "input_schema": {
                "type": "object",
                "properties": {"name": S(type="string", description="Name for the new list.")},
                "required": ["name"],
            },
            "fn": create_shopping_list,
            "effect": "write",
        },
        {
            "name": "add_shopping_list_item",
            "description": "Add one item to an existing shopping list. The item is created unchecked.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "list_name": S(type="string", description="Exact name of an existing shopping list."),
                    "item": S(type="string", description="What to buy, e.g. 'red lentils'."),
                    "quantity": S(type="number", description="How many. Defaults to 1."),
                },
                "required": ["list_name", "item"],
            },
            "fn": add_shopping_list_item,
            "effect": "write",
        },
        {
            "name": "set_shopping_list_items_checked",
            "description": (
                "Check off or un-check items on a shopping list. Omit `item` to apply to every item "
                "on the list; supply it to target the items whose text contains that substring."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "list_name": S(type="string", description="Exact name of an existing shopping list."),
                    "checked": S(type="boolean", description="true marks bought, false marks outstanding."),
                    "item": S(type="string", description="Optional substring selecting which items to change."),
                },
                "required": ["list_name", "checked"],
            },
            "fn": set_shopping_list_items_checked,
            "effect": "write",
        },
        {
            "name": "add_meal_plan_entry",
            "description": "Schedule an existing recipe on the meal plan for a given date and meal slot.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "date": S(type="string", description="ISO date, YYYY-MM-DD."),
                    "entry_type": S(type="string", enum=["breakfast", "lunch", "dinner", "side"],
                                    description="Which meal slot."),
                    "recipe": S(type="string", description="Recipe name or slug."),
                },
                "required": ["date", "entry_type", "recipe"],
            },
            "fn": add_meal_plan_entry,
            "effect": "write",
        },
        {
            "name": "create_recipe",
            "description": (
                "Create a new recipe. Only the name is required; anything else supplied is set in "
                "the same operation. Tags and categories that do not yet exist are created."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "name": S(type="string", description="Recipe name."),
                    "servings": S(type="number", description="How many people it serves."),
                    "prep_minutes": S(type="number", description="Preparation time in minutes."),
                    "cook_minutes": S(type="number", description="Cooking time in minutes."),
                    "description": S(type="string", description="Short description."),
                    "tags": S(type="array", items={"type": "string"}, description="Tag names to apply."),
                    "categories": S(type="array", items={"type": "string"}, description="Category names to apply."),
                },
                "required": ["name"],
            },
            "fn": create_recipe,
            "effect": "write",
        },
        {
            "name": "update_recipe",
            "description": (
                "Change servings, prep time, cook time or description on an existing recipe. "
                "Fields left out are untouched. Use set_recipe_tags for tags."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "recipe": S(type="string", description="Recipe name or slug."),
                    "servings": S(type="number"),
                    "prep_minutes": S(type="number"),
                    "cook_minutes": S(type="number"),
                    "description": S(type="string"),
                },
                "required": ["recipe"],
            },
            "fn": update_recipe,
            "effect": "write",
        },
        {
            "name": "set_recipe_tags",
            "description": (
                "Add tags to a recipe or replace its tag set. mode='add' keeps existing tags "
                "(the safe default); mode='replace' discards them. Tags that do not exist are created."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "recipe": S(type="string", description="Recipe name or slug."),
                    "tags": S(type="array", items={"type": "string"}, description="Tag names."),
                    "mode": S(type="string", enum=["add", "replace"], description="Defaults to 'add'."),
                },
                "required": ["recipe", "tags"],
            },
            "fn": set_recipe_tags,
            "effect": "write",
        },
    ]

    # Surface v1 is the twenty tools frozen at 15:10 on 2026-08-02, before the per-record task
    # family existed. Surface v2 adds aggregate_recipes under preregistration A5.1. v1 is kept
    # runnable so both surfaces can be reported side by side rather than one superseding the other.
    if surface == "v1":
        specs = [s for s in specs if s.get("surface") != "v2"]
    elif surface != "v2":
        raise ValueError(f"tool surface must be 'v1' or 'v2', got {surface!r}")

    schemas = [{k: v for k, v in s.items() if k in ("name", "description", "input_schema")} for s in specs]
    fns = {s["name"]: s["fn"] for s in specs}
    return schemas, fns


def tool_effects(api: MealieClient) -> dict[str, str]:
    """Effect class per tool, for the record. Not enforced here: enforcement is the
    disposable container (FR-019)."""
    return {}
