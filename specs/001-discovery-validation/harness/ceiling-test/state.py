"""SPIKE - E7 ceiling test. Delete after 2026-11-30. Do not import from product code.

The oracle. Two responsibilities:

1. `snapshot()` reads the application's observable state over exactly the same HTTP
   surface, with exactly the same credential, that both arms are given. That property is
   what guarantees every non-null task is answerable by both arms: the oracle can see
   nothing an arm cannot see. It also denormalises the state so a reference query can be
   a flat filter-and-aggregate over data that the *agent* still has to traverse across
   several endpoints.

2. `run_query()` executes a declarative reference query. Reference queries are data
   (they live in tasks/tasks.json), never code, so a task's expected value is computed by
   this engine against the live fixture at scoring time and can never drift away from it
   (research/11-validation-plan.md 3.1).

No model is involved anywhere in this file. That is the point of it (FR-001).
"""

from __future__ import annotations

import datetime
import hashlib
import json
import re
import statistics
from typing import Any

from mealie_client import MealieClient

_MINUTES = re.compile(r"(-?\d+(?:\.\d+)?)")


def _minutes(text: str | None) -> float | None:
    if not text:
        return None
    m = _MINUTES.search(text)
    return float(m.group(1)) if m else None


# ---------------------------------------------------------------------------
# snapshot
# ---------------------------------------------------------------------------


def snapshot(api: MealieClient) -> dict[str, list[dict[str, Any]]]:
    """Read the full observable state through the public API."""
    summaries = api.get_all("/api/recipes")
    recipes: list[dict[str, Any]] = []
    for s in summaries:
        full = api.get(f"/api/recipes/{s['slug']}")
        ings = full.get("recipeIngredient") or []
        foods = [i["food"]["name"] for i in ings if i.get("food")]
        units = [i["unit"]["name"] for i in ings if i.get("unit")]
        quantities = [float(i.get("quantity") or 0) for i in ings]
        prep = _minutes(full.get("prepTime"))
        cook = _minutes(full.get("cookTime"))
        recipes.append(
            {
                "slug": full["slug"],
                "name": full["name"],
                "description": full.get("description") or "",
                "prep_minutes": prep,
                "cook_minutes": cook,
                "total_minutes": (prep or 0) + (cook or 0),
                "servings": float(full.get("recipeServings") or 0),
                "rating": full.get("rating"),
                "tags": sorted(t["name"] for t in (full.get("tags") or [])),
                "categories": sorted(c["name"] for c in (full.get("recipeCategory") or [])),
                "cooking_tools": sorted(t["name"] for t in (full.get("tools") or [])),
                "tag_count": len(full.get("tags") or []),
                "category_count": len(full.get("recipeCategory") or []),
                "tool_count": len(full.get("tools") or []),
                "ingredient_count": len(ings),
                "ingredient_foods": sorted(set(foods)),
                "ingredient_units": sorted(set(units)),
                "max_ingredient_quantity": max(quantities) if quantities else 0.0,
                "total_ingredient_quantity": round(sum(quantities), 6),
                "instruction_count": len(full.get("recipeInstructions") or []),
                "date_added": full.get("dateAdded"),
                "last_made": full.get("lastMade"),
            }
        )
    by_slug = {r["slug"]: r for r in recipes}
    by_id = {}
    for s in summaries:
        by_id[s["id"]] = by_slug[s["slug"]]

    # meal plan, denormalised onto the recipe it points at
    mealplan = []
    for m in api.get_all("/api/households/mealplans"):
        rid = m.get("recipeId")
        r = by_id.get(rid) if rid else None
        d = datetime.date.fromisoformat(m["date"])
        mealplan.append(
            {
                "date": m["date"],
                "entry_type": m.get("entryType"),
                "recipe_name": r["name"] if r else None,
                "recipe_slug": r["slug"] if r else None,
                "recipe_tags": r["tags"] if r else [],
                "recipe_categories": r["categories"] if r else [],
                "recipe_total_minutes": r["total_minutes"] if r else None,
                "day_of_week": d.strftime("%A"),
                "iso_week": d.isocalendar()[1],
            }
        )
    for r in recipes:
        entries = [m for m in mealplan if m["recipe_slug"] == r["slug"]]
        r["mealplan_count"] = len(entries)
        r["mealplan_dates"] = sorted(e["date"] for e in entries)
        r["mealplan_entry_types"] = sorted({e["entry_type"] for e in entries})

    # shopping lists
    shopping_lists, shopping_items = [], []
    for meta in api.get_all("/api/households/shopping/lists"):
        detail = api.get(f"/api/households/shopping/lists/{meta['id']}")
        items = detail.get("listItems") or []
        for it in items:
            shopping_items.append(
                {
                    "list_name": detail["name"],
                    "note": it.get("note") or "",
                    "quantity": float(it.get("quantity") or 0),
                    "checked": bool(it.get("checked")),
                    "label": (it.get("label") or {}).get("name") if it.get("label") else None,
                }
            )
        shopping_lists.append(
            {
                "name": detail["name"],
                "item_count": len(items),
                "checked_count": sum(1 for i in items if i.get("checked")),
                "unchecked_count": sum(1 for i in items if not i.get("checked")),
                "total_quantity": round(sum(float(i.get("quantity") or 0) for i in items), 6),
                "item_notes": sorted((i.get("note") or "") for i in items),
            }
        )

    def _org(path: str, field: str) -> list[dict[str, Any]]:
        out = []
        for o in api.get_all(path):
            out.append(
                {
                    "name": o["name"],
                    "slug": o.get("slug"),
                    "recipe_count": sum(1 for r in recipes if o["name"] in r[field]),
                }
            )
        return out

    tags = _org("/api/organizers/tags", "tags")
    categories = _org("/api/organizers/categories", "categories")
    cooking_tools = _org("/api/organizers/tools", "cooking_tools")

    foods = [
        {"name": f["name"], "recipe_count": sum(1 for r in recipes if f["name"] in r["ingredient_foods"])}
        for f in api.get_all("/api/foods")
    ]
    units = [
        {
            "name": u["name"],
            "abbreviation": u.get("abbreviation"),
            "recipe_count": sum(1 for r in recipes if u["name"] in r["ingredient_units"]),
        }
        for u in api.get_all("/api/units")
    ]
    cookbooks = [
        {"name": c["name"], "slug": c.get("slug"), "query_filter": c.get("queryFilterString") or ""}
        for c in api.get_all("/api/households/cookbooks")
    ]
    users = [
        {
            "username": u["username"],
            "full_name": u.get("fullName"),
            "email": u.get("email"),
            "is_admin": bool(u.get("admin")),
        }
        for u in api.get("/api/admin/users")["items"]
    ]
    labels = [{"name": lab["name"]} for lab in api.get_all("/api/groups/labels")]

    return {
        "recipes": recipes,
        "tags": tags,
        "categories": categories,
        "cooking_tools": cooking_tools,
        "foods": foods,
        "units": units,
        "shopping_lists": shopping_lists,
        "shopping_items": shopping_items,
        "mealplan": mealplan,
        "cookbooks": cookbooks,
        "users": users,
        "labels": labels,
    }


# Fields excluded from the fingerprint because they move on any write without carrying
# semantic meaning. Everything else is included, so an unrelated mutation is detected.
_VOLATILE = {"date_added", "last_made"}


def fingerprint(state: dict) -> str:
    def clean(obj):
        if isinstance(obj, dict):
            return {k: clean(v) for k, v in sorted(obj.items()) if k not in _VOLATILE}
        if isinstance(obj, list):
            return [clean(v) for v in obj]
        return obj

    payload = json.dumps(clean(state), sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


def entity_counts(state: dict) -> dict[str, int]:
    return {k: len(v) for k, v in state.items()}


# ---------------------------------------------------------------------------
# reference query engine
# ---------------------------------------------------------------------------


class QueryError(RuntimeError):
    pass


def _cmp(value, op: str, target) -> bool:
    if op == "eq":
        return value == target
    if op == "ne":
        return value != target
    if op == "gt":
        return value is not None and value > target
    if op == "gte":
        return value is not None and value >= target
    if op == "lt":
        return value is not None and value < target
    if op == "lte":
        return value is not None and value <= target
    if op == "contains":
        if value is None:
            return False
        if isinstance(value, (list, tuple, set)):
            return target in value
        return str(target).lower() in str(value).lower()
    if op == "not_contains":
        return not _cmp(value, "contains", target)
    if op == "in":
        return value in target
    if op == "not_in":
        return value not in target
    if op == "between":
        return value is not None and target[0] <= value <= target[1]
    if op == "is_null":
        return value is None
    if op == "not_null":
        return value is not None
    if op == "empty":
        return not value
    if op == "nonempty":
        return bool(value)
    if op == "startswith":
        return str(value or "").lower().startswith(str(target).lower())
    raise QueryError(f"unknown operator {op!r}")


def _require_field(src: str, field: str, rows: list[dict]) -> None:
    """A misspelled field name is indistinguishable from a legitimately empty result: both
    match nothing. That is how a fabricated 'near-miss' task once entered this battery and
    failed an arm for giving the correct answer. Unknown fields are therefore a hard error.
    """
    if not rows:
        return  # an empty collection carries no schema to check against
    known: set[str] = set()
    for r in rows:
        known |= set(r.keys())
    if field not in known:
        raise QueryError(
            f"unknown field {field!r} on source {src!r}; known fields are {sorted(known)}"
        )


def run_query(state: dict, query: dict) -> Any:
    src = query["source"]
    if src not in state:
        raise QueryError(f"unknown source {src!r}")
    rows = state[src]
    for clause in query.get("where", []):
        field, op, target = clause["field"], clause["op"], clause.get("value")
        _require_field(src, field, state[src])
        rows = [r for r in rows if _cmp(r.get(field), op, target)]

    sel = query.get("select", {"agg": "count"})
    agg = sel["agg"]
    if sel.get("field"):
        _require_field(src, sel["field"], state[src])

    if agg == "count":
        return len(rows)
    if agg == "distinct_count":
        vals = []
        for r in rows:
            v = r.get(sel["field"])
            vals.extend(v if isinstance(v, list) else [v])
        return len({v for v in vals if v is not None})
    if agg in ("sum", "mean", "max", "min"):
        vals = [r.get(sel["field"]) for r in rows]
        vals = [float(v) for v in vals if v is not None]
        if not vals:
            raise QueryError(f"aggregate {agg} over empty set")
        out = {"sum": sum, "mean": statistics.mean, "max": max, "min": min}[agg](vals)
        return round(float(out), 6)
    if agg == "list":
        vals = []
        for r in rows:
            v = r.get(sel["field"])
            vals.extend(v if isinstance(v, list) else ([v] if v is not None else []))
        return sorted(set(vals)) if sel.get("distinct", True) else sorted(vals)
    if agg in ("argmax", "argmin"):
        field = sel["field"]
        cand = [r for r in rows if r.get(field) is not None]
        if not cand:
            raise QueryError(f"{agg} over empty set")
        best = (max if agg == "argmax" else min)(float(r[field]) for r in cand)
        winners = [r for r in cand if abs(float(r[field]) - best) < 1e-9]
        if len(winners) > 1:
            raise QueryError(
                f"{agg} on {field} is ambiguous: {len(winners)} rows tie at {best}. "
                "A task with a tied answer is not adjudicable and must be redesigned."
            )
        return winners[0][sel.get("return", "name")]
    if agg == "top":
        field, n = sel["field"], sel.get("n", 3)
        cand = [r for r in rows if r.get(field) is not None]
        ordered = sorted(cand, key=lambda r: float(r[field]), reverse=not sel.get("ascending", False))
        if len(ordered) > n and abs(float(ordered[n - 1][field]) - float(ordered[n][field])) < 1e-9:
            raise QueryError(
                f"top-{n} on {field} has a tie at the cutoff; the task is not adjudicable."
            )
        return sorted(r[sel.get("return", "name")] for r in ordered[:n])
    raise QueryError(f"unknown aggregate {agg!r}")
