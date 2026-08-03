"""SPIKE - E8 verifier-vs-judge. Delete after 2026-11-30. Do not import from product code.

Arm (c2)'s recomputation source: where the postcondition's re-reads actually go.

PREREGISTRATION.md 4.5 requires c2 to "re-issue the reads named by the operation's declared
parameters" and recompute the projection "from the app's own current state through those same
operations". That needs a source. This module provides two, behind one interface:

* **live** — reads through the target's own HTTP API, reusing ``ceiling-test/mealie_client.py``
  rather than a second client. Requires a running instance and is never used by ``--dry-run``.
* **fixture** — reads from a recorded state file with the same response shapes. Costs $0.00,
  needs no network and no container, and is what keeps the whole experiment validatable
  offline (PREREGISTRATION.md 10: "c2's re-reads go to the local fixture").

**How the offline fixture is produced, and what that costs in validity.**

No snapshot of the running instance was ever committed, and the container is not up. The
fixture is therefore *rendered* from ``ceiling-test/seed/fixture_plan.json`` — the plan the
instance was seeded from — through the field mapping that ``ceiling-test/seed/apply.py``
itself used to write it, into the response shapes ``groundtruth/openapi.json`` declares. That
is a reconstruction of the application's state, not a recording of its responses, and the
difference is real:

* Anything the application computes or normalises at write time is reproduced only insofar as
  the mapping below reproduces it. Two such transforms were read off **real recorded responses
  in the frozen traces** rather than guessed — ``rating`` is ``null`` on the recipe collection
  because Mealie exposes ratings per principal, and ``totalTime`` is ``null`` because nothing
  populates it — and :func:`audit_against_traces` re-checks the rendering against every real
  API response the frozen traces contain, so a drift between fixture and application is
  reported rather than assumed away.
* The write family mutated state during the ceiling test. The ceiling test restored the
  database between write attempts, so the read families saw seed state; c2 declines write
  tasks anyway, because their pre-state is gone (derivation-rules.md).

The fixture contains no expected value, no oracle verdict, and no task identifier. It is a
description of a world, not of an answer.
"""

from __future__ import annotations

import json
import os
import re
import sys
import unicodedata
import uuid
from typing import Any

HERE = os.path.dirname(os.path.abspath(__file__))
CEILING = os.path.abspath(os.path.join(HERE, "..", "ceiling-test"))
PLAN_PATH = os.path.join(CEILING, "seed", "fixture_plan.json")
FIXTURE_PATH = os.path.join(HERE, "fixtures", "mealie_state.json")

#: A namespace for deterministic synthetic identifiers. Identifiers only ever serve as join
#: keys inside a recomputation; none is compared against anything the agent submitted.
NS = uuid.UUID("00000000-0000-4000-8000-000000000001")

RECIPES = "/api/recipes"
RECIPE_DETAIL = "/api/recipes/{slug}"
MEALPLANS = "/api/households/mealplans"
SHOPPING_LISTS = "/api/households/shopping/lists"
TAGS = "/api/organizers/tags"
CATEGORIES = "/api/organizers/categories"
TOOLS = "/api/organizers/tools"
FOODS = "/api/foods"
UNITS = "/api/units"
USERS = "/api/admin/users"
USER_RATINGS = "/api/users/{id}/ratings"

#: Every declared operation a derivation may name. Each is a path that appears in
#: ``groundtruth/openapi.json``; :func:`assert_operations_declared` proves it.
DECLARED_OPERATIONS = (
    RECIPES, RECIPE_DETAIL, MEALPLANS, SHOPPING_LISTS, TAGS, CATEGORIES, TOOLS,
    FOODS, UNITS, USERS, USER_RATINGS,
)


class NoRecomputationSource(RuntimeError):
    """No live app and no recorded state fixture. The arm does not run."""


def slugify(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    s = re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").lower()
    return s


def _id(*parts: str) -> str:
    return str(uuid.uuid5(NS, "|".join(parts)))


def _bootstrap_admin_email() -> str:
    """The address the seeder authenticates as, read from the target's own config."""
    with open(os.path.join(CEILING, "config.json"), encoding="utf-8") as fh:
        return json.load(fh)["target"]["admin_email"]


# ------------------------------------------------------------------ fixture rendering

def render_fixture(plan: dict) -> dict:
    """``fixture_plan.json`` -> the response shapes ``openapi.json`` declares.

    The field mapping is taken from ``ceiling-test/seed/apply.py``, which is how the
    application was actually written to. Where the application's own response differs from a
    naive rendering, the observed response wins and the divergence is commented:

    * ``rating`` on ``RecipeSummary`` is ``null``. Mealie stores ratings per principal
      (``UserRatingOut.rating`` reached through ``/api/users/{id}/ratings``); nothing
      back-fills the recipe-level column. Observed in the frozen traces.
    * ``totalTime`` is ``null``. Nothing populates it; ``prepTime`` and ``cookTime`` are free
      text (``anyOf: [string, null]``), which is why a duration has to be parsed rather than
      read.
    """
    ratings_by_recipe: dict[str, list[float]] = {}
    for r in plan["ratings"]:
        ratings_by_recipe.setdefault(r["recipe"], []).append(float(r["rating"]))

    tags = [{"id": _id("tag", t), "name": t, "slug": slugify(t), "groupId": _id("group")}
            for t in plan["tags"]]
    cats = [{"id": _id("cat", c), "name": c, "slug": slugify(c), "groupId": _id("group")}
            for c in plan["categories"]]
    tools = [{"id": _id("tool", t), "name": t, "slug": slugify(t), "groupId": _id("group"),
              "householdsWithTool": []} for t in plan["cooking_tools"]]
    foods = [{"id": _id("food", f), "name": f, "pluralName": None, "description": "",
              "label": None, "labelId": None, "aliases": []} for f in plan["foods"]]
    units = [{"id": _id("unit", u["name"]), "name": u["name"],
              "abbreviation": u.get("abbreviation", ""), "pluralName": None,
              "useAbbreviation": False, "fraction": True, "aliases": []}
             for u in plan["units"]]
    # The instance is not empty before the plan is applied. Mealie bootstraps one
    # administrator at first start, and ``ceiling-test/seed/apply.py`` authenticates as it to
    # write everything else — ``ceiling-test/config.json`` names its address in
    # ``target.admin_email``. An account it can log in as therefore exists on the instance,
    # and a fixture that renders only the plan's four users under-reports the collection by
    # one. Sourced from the target config, not from any expected value; see the fixture
    # fidelity note in README.md for how the omission was found.
    users = [{"id": _id("user", "bootstrap-admin"), "username": "admin",
              "fullName": "Change Me", "email": _bootstrap_admin_email(), "admin": True}]
    users += [{"id": _id("user", u["username"]), "username": u["username"],
               "fullName": u["full_name"], "email": u["email"], "admin": False}
              for u in plan["users"]]
    by_tag = {t["name"]: t for t in tags}
    by_cat = {c["name"]: c for c in cats}
    by_tool = {t["name"]: t for t in tools}
    by_food = {f["name"]: f for f in foods}
    by_unit = {u["name"]: u for u in units}
    by_user = {u["username"]: u for u in users}

    summaries: list[dict] = []
    details: dict[str, dict] = {}
    for r in plan["recipes"]:
        slug = slugify(r["name"])
        rid = _id("recipe", r["name"])
        summary = {
            "id": rid,
            "name": r["name"],
            "slug": slug,
            "description": r["description"],
            # apply.py writes these as free text; the schema declares string-or-null.
            "prepTime": f"{r['prep_minutes']} minutes",
            "cookTime": f"{r['cook_minutes']} minutes",
            "performTime": f"{r['cook_minutes']} minutes",
            "totalTime": None,          # observed null on the live instance
            # Observed non-null on the live instance for rated recipes and null for unrated
            # ones. Which statistic the application reduces multiple principals to is NOT
            # determined by the schema (`anyOf: [number, null]`, no description) and NOT
            # determined by the frozen traces (every rated recipe they recorded carries
            # exactly one principal's rating, so mean, max, min and last coincide). Rendered
            # as the arithmetic mean over principals, which is the reduction c2's own
            # cross-principal rule commits to in derivation-rules.md; every derivation that
            # touches a rating is marked provisional for exactly this reason.
            "rating": (sum(ratings_by_recipe[r["name"]]) / len(ratings_by_recipe[r["name"]])
                       if r["name"] in ratings_by_recipe else None),
            "recipeServings": float(r["servings"]),
            "recipeYield": f"{r['servings']} servings",
            "recipeYieldQuantity": float(r["servings"]),
            "tags": [by_tag[t] for t in r["tags"]],
            "recipeCategory": [by_cat[c] for c in r["categories"]],
            "tools": [by_tool[t] for t in r["tools"]],
        }
        summaries.append(summary)
        details[slug] = summary | {
            "recipeIngredient": [
                {"quantity": ing["quantity"], "unit": by_unit[ing["unit"]],
                 "food": by_food[ing["food"]], "note": "", "title": None,
                 "originalText": None, "display": "", "referenceId": _id("ing", slug, str(n))}
                for n, ing in enumerate(r["ingredients"])
            ],
            "recipeInstructions": [
                {"id": _id("step", slug, str(n)), "title": "", "summary": "", "text": step,
                 "ingredientReferences": []}
                for n, step in enumerate(r["instructions"])
            ],
        }
    by_recipe_name = {r["name"]: r for r in summaries}

    mealplan = [
        {"id": _id("plan", m["date"], m["entry_type"], m["recipe"]),
         "date": m["date"], "entryType": m["entry_type"], "title": "", "text": "",
         "recipeId": by_recipe_name[m["recipe"]]["id"],
         "recipe": by_recipe_name[m["recipe"]]}
        for m in plan["mealplan"]
    ]

    ratings = [
        {"id": _id("rating", r["username"], r["recipe"]),
         "userId": by_user[r["username"]]["id"],
         "recipeId": by_recipe_name[r["recipe"]]["id"],
         "rating": float(r["rating"]), "isFavorite": False}
        for r in plan["ratings"]
    ]

    lists = []
    for sl in plan["shopping_lists"]:
        lid = _id("list", sl["name"])
        lists.append({
            "id": lid, "name": sl["name"],
            "listItems": [
                {"id": _id("item", sl["name"], str(n)), "shoppingListId": lid,
                 "note": it["note"], "quantity": it["quantity"], "checked": it["checked"],
                 "label": ({"name": it["label"]} if it.get("label") else None),
                 "isFood": False, "food": None, "unit": None, "position": n}
                for n, it in enumerate(sl["items"])
            ],
        })

    return {
        "_provenance": (
            "rendered from ceiling-test/seed/fixture_plan.json through the field mapping in "
            "ceiling-test/seed/apply.py, into the response shapes declared by "
            "ceiling-test/groundtruth/openapi.json. Contains no expected value, no oracle "
            "verdict, and no task identifier."
        ),
        "_plan_sha256": plan.get("plan_sha256"),
        "_rating_semantics": (
            "RecipeSummary.rating is rendered as the arithmetic mean over principals. The "
            "reduction is underdetermined by the contract and by the recorded evidence; see "
            "the comment in render_fixture and the c2 cross-principal rule."
        ),
        "collections": {
            RECIPES: summaries,
            RECIPE_DETAIL: details,
            MEALPLANS: mealplan,
            SHOPPING_LISTS: lists,
            TAGS: tags,
            CATEGORIES: cats,
            TOOLS: tools,
            FOODS: foods,
            UNITS: units,
            USERS: users,
            USER_RATINGS: ratings,
        },
    }


def build_fixture(dest: str = FIXTURE_PATH) -> str:
    with open(PLAN_PATH, encoding="utf-8") as fh:
        plan = json.load(fh)
    state = render_fixture(plan)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=1, sort_keys=True)
        fh.write("\n")
    return dest


# ------------------------------------------------------------------ the source

class RecomputationSource:
    """One read interface over either a live instance or the recorded fixture."""

    def __init__(self, base_url: str | None = None, fixture_path: str | None = None,
                 snapshot_path: str | None = None) -> None:
        # ``snapshot_path`` is the name the runner already used for "a recorded state file".
        # Kept as an alias rather than renamed, so an operator's committed command line does
        # not silently change meaning.
        fixture_path = fixture_path or snapshot_path
        self.mode: str
        self._client = None
        self._state: dict | None = None
        if base_url:
            sys.path.insert(0, CEILING)
            from mealie_client import MealieClient, load_config  # noqa: PLC0415

            tgt = load_config()["target"]
            self._client = MealieClient(base_url, tgt["admin_email"], tgt["admin_password"])
            self.mode = "live"
        elif fixture_path:
            with open(fixture_path, encoding="utf-8") as fh:
                self._state = json.load(fh)["collections"]
            self.mode = "fixture"
        else:
            raise NoRecomputationSource(
                "arm (c2) needs a recomputation source.\n"
                "  --app-base-url URL     re-read through the application's own declared operations\n"
                "  --state-fixture PATH   re-read from the recorded state fixture (offline, $0.00)\n"
                "Without one, c2 cannot recompute a postcondition. It is reported as not_run\n"
                "rather than as a corpus of unverifiable traces, because 'the container was\n"
                "not up' and 'the contract could not be derived' are different findings."
            )

    def describe(self) -> dict:
        return {"mode": self.mode,
                "fixture_sha256": fixture_sha256() if self.mode == "fixture" else None}

    def read(self, operation: str, params: dict | None = None) -> Any:
        """Re-issue a declared read. Returns a list for collections, a dict for detail maps."""
        if operation not in DECLARED_OPERATIONS:
            raise ValueError(f"{operation!r} is not a declared operation")
        if self._state is not None:
            return self._state.get(operation)
        return self._live_read(operation, params)

    def _live_read(self, operation: str, params: dict | None) -> Any:
        api = self._client
        assert api is not None
        if operation == RECIPE_DETAIL:
            return {r["slug"]: api.get(f"/api/recipes/{r['slug']}")
                    for r in api.get_all(RECIPES)}
        if operation == USER_RATINGS:
            out: list[dict] = []
            for u in api.get_all(USERS):
                got = api.get(f"/api/users/{u['id']}/ratings")
                out += (got.get("ratings") or got.get("items") or []) if isinstance(got, dict) else got
            return out
        return api.get_all(operation, **(params or {}))


def fixture_sha256() -> str:
    import hashlib  # noqa: PLC0415
    if not os.path.isfile(FIXTURE_PATH):
        return "absent"
    with open(FIXTURE_PATH, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()[:16]


def open_source(base_url: str | None = None, fixture_path: str | None = None,
                allow_default_fixture: bool = True) -> RecomputationSource:
    if base_url:
        return RecomputationSource(base_url=base_url)
    path = fixture_path or (FIXTURE_PATH if allow_default_fixture else None)
    if path and os.path.isfile(path):
        return RecomputationSource(fixture_path=path)
    raise NoRecomputationSource(
        "no live instance and no recorded state fixture. Build one with "
        "`python3 recompute_source.py --build`."
    )


# ------------------------------------------------------------------ audits

def assert_operations_declared(openapi_path: str) -> list[str]:
    """Every operation a derivation may name must appear in the OpenAPI document."""
    with open(openapi_path, encoding="utf-8") as fh:
        paths = set(json.load(fh).get("paths", {}))
    missing = [op for op in DECLARED_OPERATIONS if op not in paths]
    return missing


def audit_against_traces(state: dict, traces: list[dict]) -> dict:
    """Compare the rendered fixture against every real API response the traces recorded.

    The fixture is a reconstruction. This is what stops the reconstruction being taken on
    trust: any recorded ``/api/recipes`` page in the frozen traces is a real response from the
    application, and every field of it that the fixture also carries must agree. Divergences
    are returned, never silently tolerated.
    """
    recipes = {r["slug"]: r for r in state["collections"][RECIPES]}
    compared = 0
    divergences: list[str] = []
    checked_fields = ("name", "prepTime", "cookTime", "performTime", "rating",
                      "recipeServings", "totalTime")
    observed_totals: dict[str, set] = {}

    for t in traces:
        for msg in t.get("transcript") or []:
            content = msg.get("content")
            if not isinstance(content, list):
                continue
            for block in content:
                if block.get("type") != "tool_result":
                    continue
                body = block.get("content")
                if not isinstance(body, str) or '"slug"' not in body:
                    continue
                try:
                    obj = json.loads(body)
                except (ValueError, TypeError):
                    continue
                items = obj.get("items") if isinstance(obj, dict) else None
                if isinstance(obj, dict) and obj.get("total") is not None and items is not None:
                    observed_totals.setdefault("items_envelope", set()).add(obj["total"])
                cands = items if isinstance(items, list) else ([obj] if isinstance(obj, dict) else [])
                for got in cands:
                    if not isinstance(got, dict) or "slug" not in got:
                        continue
                    want = recipes.get(got["slug"])
                    if want is None:
                        continue
                    compared += 1
                    for f in checked_fields:
                        if f in got and got[f] != want.get(f):
                            divergences.append(
                                f"{got['slug']}.{f}: application returned {got[f]!r}, "
                                f"fixture renders {want.get(f)!r}"
                            )
    return {
        "recipe_objects_compared": compared,
        "divergent_fields": sorted(set(divergences)),
        "observed_collection_totals": {k: sorted(v) for k, v in observed_totals.items()},
    }


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--build" in argv:
        path = build_fixture()
        with open(path, encoding="utf-8") as fh:
            state = json.load(fh)
        counts = {k: len(v) for k, v in state["collections"].items()}
        print(f"wrote {os.path.relpath(path, HERE)}  sha256[:16]={fixture_sha256()}")
        print(json.dumps(counts, indent=1))
        return 0
    if "--audit" in argv:
        import freeze  # noqa: PLC0415

        cfg = freeze.load_config()
        missing = assert_operations_declared(
            os.path.abspath(os.path.join(HERE, cfg["battery"]["openapi_rel"])))
        print(f"undeclared operations named by the source: {missing or 'none'}")
        import corpus  # noqa: PLC0415

        _, traces = corpus.load_records(cfg)
        with open(FIXTURE_PATH, encoding="utf-8") as fh:
            state = json.load(fh)
        rep = audit_against_traces(state, traces)
        print(json.dumps(rep, indent=1))
        return 0 if not rep["divergent_fields"] and not missing else 1
    print(__doc__)
    print("usage: python3 recompute_source.py [--build | --audit]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
