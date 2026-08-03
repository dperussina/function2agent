"""SPIKE - E8 verifier-vs-judge. Delete after 2026-11-30. Do not import from product code.

Arm (c1): the schema-derived verifier. **QUARANTINED 2026-08-03 — DO NOT SCORE WITH THIS ARM.**

=============================================================================================
QUARANTINE. :func:`verify` raises :class:`Quarantined` and returns no verdict. Every clause
below is preserved **byte-for-byte as preregistered** and none is repaired, because amendment
rule 2 forbids altering a clause after seeing which traces it would catch, and because E8 will
not run. The clause walk survives at :func:`verify_clauses_quarantined`, which exists so the
self-test can keep proving the clauses were not touched — never so that a result can be
obtained from them.

Why: clause C1.5 fires three times on the frozen corpus and is wrong all three times.

  * It selects its comparand as the **last** ``"total": N`` occurring anywhere in the
    serialised transcript (``totals[-1]``) and its provenance path as the operation of the
    **last non-submit tool call**. Nothing associates the two. On the one oracle-negative it
    fires on, it compares a 60-member submission against ``total=8`` read from the
    *categories* listing while its provenance string names ``/api/recipes`` — which returned
    60, equal to the submission, so a correct comparison passes.
  * The clause's premise is false besides. Where the total *does* come from the cited
    operation, the submitted answer is a filtered subset of the collection the envelope
    counts, so length != total is the normal case for a correct answer. It raises a false
    alarm on two oracle-**positive** traces for exactly this reason.

Corpus-wide C1.5 precision is 0 of 3. Repairing the envelope selection would not save it; it
would leave the two false alarms and remove the one apparent detection.

The full derivation is in
``specs/001-discovery-validation/findings/015-verifier-vs-judge-not-run.md`` and the amendment
of record is PREREGISTRATION.md **Amendment B5**.
=============================================================================================

Implements the seven clauses of ``derivation-rules.md`` (PREREGISTRATION.md 4.4) over the
frozen OpenAPI document and the synthesized tool signatures. It sees a
:func:`redact.scoring_view` and nothing else; :func:`redact.assert_no_oracle_leak` runs on its
input before every invocation, on the same code path a judge call takes.

**c1 is predicted to detect zero numeric value errors** (4.6, 7.5, S3). Nothing in these
clauses compares a submitted magnitude to anything, because there is nothing to compare it
to at the schema level — that is the structural point c1 exists to demonstrate, and the
predicted-null control in ``controls.py`` is what makes the prediction falsifiable rather
than decorative.

Every verdict carries ``provenance`` (the schema construct it was derived from) and
``status`` (``validated`` or ``provisional``), because 6.6 forbids stating a derived verdict
as fact without both.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

import redact

HERE = os.path.dirname(os.path.abspath(__file__))

PASS, FAIL, UNVERIFIABLE = "pass", "fail", "unverifiable"

#: Tool name -> the declared operation path it wraps. Derived from the synthesized tool
#: signatures in ``ceiling-test/tools/mealie_tools.py``, which PREREGISTRATION.md 4.4 names as
#: a permitted derivation input. It contains no task identifier and no expected value; it is a
#: statement about the tool surface, readable without learning anything about the battery.
TOOL_OPERATIONS: dict[str, str] = {
    "search_recipes": "/api/recipes",
    "aggregate_recipes": "/api/recipes",
    "get_recipe": "/api/recipes/{slug}",
    "find_recipes_by_ingredient": "/api/recipes",
    "list_tags": "/api/organizers/tags",
    "list_categories": "/api/organizers/categories",
    "list_cooking_tools": "/api/organizers/tools",
    "list_ingredients": "/api/foods",
    "list_units": "/api/units",
    "get_meal_plan": "/api/households/mealplans",
    "list_shopping_lists": "/api/households/shopping/lists",
    "get_shopping_list": "/api/households/shopping/lists",
    "list_cookbooks": "/api/households/cookbooks",
    "list_users": "/api/admin/users",
    "create_shopping_list": "/api/households/shopping/lists",
    "add_shopping_list_item": "/api/households/shopping/items",
    "set_shopping_list_items_checked": "/api/households/shopping/items",
    "add_meal_plan_entry": "/api/households/mealplans",
    "create_recipe": "/api/recipes",
    "update_recipe": "/api/recipes/{slug}",
    "set_recipe_tags": "/api/recipes/{slug}",
}

#: The shell arm calls one tool. Its operation is whatever URL the command reached, which is
#: recovered from the command text when it is unambiguous and abstained on when it is not.
SHELL_TOOL = "bash"
SUBMIT_TOOL = "submit_answer"

STATUS_RE = re.compile(r"\b(?:HTTP[/ ]?\S*\s*)?([45]\d{2})\b")
#: Tool results are embedded in a transcript message as a JSON *string*, so by the time the
#: transcript is re-serialised the envelope's quotes are escaped: `\"total\": 0`. Matching on
#: the unescaped form makes clause C1.5 silently vacuous on every real trace — a clause that
#: never fires, which is this repository's recurring failure mode and is caught here by the
#: planted cardinality-mismatch fixture rather than by nobody.
TOTAL_RE = re.compile(r'\\?"total\\?"\s*:\s*(\d+)')
URL_PATH_RE = re.compile(r"(/api/[A-Za-z0-9/_.{}-]+)")

ABSTENTION_STATUSES = {"impossible", "needs_clarification", "clarification", "abstained",
                       "cannot_answer", "unanswerable", "none"}

#: Words that are structural rather than attribute-bearing. Clause C1.6 asks whether the
#: requested *attribute* exists in the schema; matching on these would make every request
#: look satisfiable.
STOPWORDS = frozenset("""
a an and are as at be by can could do does for from get give had has have how i if in into is
it its list me my not of on or please report return show than that the their them there these
this those to using was were what when where which who why will with you your all any each
every many much number count total sum average mean across between over under about
""".split())


class Schema:
    """The frozen OpenAPI document, reduced to the lookups the clauses need."""

    def __init__(self, doc: dict) -> None:
        self.doc = doc
        self.paths: dict[str, Any] = doc.get("paths", {})
        self.components: dict[str, Any] = doc.get("components", {}).get("schemas", {})
        self.field_names: set[str] = set()
        self.enums: dict[str, list[str]] = {}
        for name, sch in self.components.items():
            for prop, spec in (sch.get("properties") or {}).items():
                self.field_names.add(prop.lower())
                if isinstance(spec, dict) and isinstance(spec.get("enum"), list):
                    self.enums[f"{name}.{prop}"] = [str(x) for x in spec["enum"]]
            if isinstance(sch.get("enum"), list):
                self.enums[name] = [str(x) for x in sch["enum"]]
        for p, item in self.paths.items():
            for seg in re.findall(r"\{(\w+)\}", p):
                self.field_names.add(seg.lower())
            for op in item.values():
                if not isinstance(op, dict):
                    continue
                for param in op.get("parameters") or []:
                    if isinstance(param, dict) and param.get("name"):
                        self.field_names.add(str(param["name"]).lower())
        # Clause C1.6 asks whether any declared **operation**, parameter, or schema property
        # matches the requested attribute. All three are enumerated here. Path segments are
        # the operations: omitting them made `/api/units` fail to declare "units", which
        # turned a satisfiable request into an abstention failure. That is a derivation
        # defect, not a threshold to be tuned, and it is fixed on the clause's own terms.
        self.vocabulary: set[str] = set()
        for f in self.field_names:
            self.vocabulary.update(re.split(r"[^a-z0-9]+", f))
        for p in self.paths:
            for seg in re.split(r"[^a-z0-9]+", p.lower()):
                if seg and seg not in ("api", "id", "v1"):
                    self.vocabulary.add(seg)
        # Naive plural folding, both directions. A schema declaring `units` declares the
        # attribute a request calls a `unit`, and neither spelling is more canonical.
        for w in list(self.vocabulary):
            if w.endswith("s") and len(w) > 3:
                self.vocabulary.add(w[:-1])
            else:
                self.vocabulary.add(w + "s")
        self.vocabulary.discard("")

    def declared_error_codes(self, path: str) -> set[str]:
        item = self.paths.get(path) or {}
        codes: set[str] = set()
        for op in item.values():
            if isinstance(op, dict):
                for code in (op.get("responses") or {}):
                    if str(code)[:1] in "45":
                        codes.add(str(code))
        return codes

    def paginated(self, path: str) -> bool:
        """Does any operation on this path declare a paginated envelope carrying `total`?"""
        item = self.paths.get(path) or {}
        blob = json.dumps(item)
        for ref in set(re.findall(r'"#/components/schemas/([A-Za-z0-9_.]+)"', blob)):
            sch = self.components.get(ref) or {}
            if "total" in (sch.get("properties") or {}):
                return True
        return "total" in blob and "page" in blob

    def response_types(self, path: str) -> set[str]:
        """Every JSON type the operation's response model can yield, resolved transitively.

        Transitive resolution matters more than it looks. Collecting only the top-level
        properties of directly ``$ref``-ed schemas under-reports the model — a paginated
        envelope's numeric fields live inside its ``items`` schema, not on the envelope — and
        an under-reported model makes clause C1.3 declare a perfectly well-typed number
        categorically impossible. That is a wrong detection, and a wrong detection in c1's
        column is indistinguishable at the point of use from the ground-truth leak the
        predicted-null control exists to catch. The control caught exactly this during
        construction, before any judge call and before any result was visible.
        """
        item = self.paths.get(path) or {}
        types: set[str] = {"object", "array"}
        seen: set[str] = set()

        def walk(node: Any, depth: int = 0) -> None:
            if depth > 12 or not isinstance(node, (dict, list)):
                return
            if isinstance(node, list):
                for v in node:
                    walk(v, depth + 1)
                return
            ref = node.get("$ref")
            if isinstance(ref, str) and ref.startswith("#/components/schemas/"):
                name = ref.rsplit("/", 1)[-1]
                if name not in seen:
                    seen.add(name)
                    walk(self.components.get(name) or {}, depth + 1)
            t = node.get("type")
            if isinstance(t, str):
                types.add("number" if t == "integer" else t)
            for v in node.values():
                walk(v, depth + 1)

        walk(item)
        return types

    def enums_for(self, path: str) -> list[list[str]]:
        item = self.paths.get(path) or {}
        blob = json.dumps(item)
        out: list[list[str]] = []
        for ref in set(re.findall(r'"#/components/schemas/([A-Za-z0-9_.]+)"', blob)):
            for key, vals in self.enums.items():
                if key.split(".")[0] == ref:
                    out.append(vals)
        return out


def load_schema(cfg: dict) -> Schema:
    path = os.path.abspath(os.path.join(HERE, cfg["battery"]["openapi_rel"]))
    with open(path, encoding="utf-8") as fh:
        return Schema(json.load(fh))


# ------------------------------------------------------------------ trace readers

def _tool_calls(view: dict) -> list[dict]:
    return list(view.get("tool_calls") or [])


def _submitted(view: dict) -> Any:
    return view.get("submitted")


def _transcript_text(view: dict) -> str:
    return json.dumps(view.get("transcript") or [], default=str)


def _invoked_path(view: dict, schema: Schema) -> str | None:
    """The declared operation of the last non-submit read, or None if not recoverable."""
    for call in reversed(_tool_calls(view)):
        name = call.get("name")
        if name == SUBMIT_TOOL:
            continue
        if name in TOOL_OPERATIONS:
            return TOOL_OPERATIONS[name]
        if name == SHELL_TOOL:
            found = URL_PATH_RE.findall(json.dumps(call.get("args") or {}))
            for candidate in reversed(found):
                base = candidate.split("?")[0].rstrip("/")
                if base in schema.paths:
                    return base
                trimmed = re.sub(r"/[0-9a-f-]{8,}$", "/{slug}", base)
                if trimmed in schema.paths:
                    return trimmed
    return None


# ------------------------------------------------------------------ the clauses

def _c1_1_output_presence(view: dict) -> dict | None:
    has_submit = any(c.get("name") == SUBMIT_TOOL for c in _tool_calls(view))
    status = view.get("submitted_status")
    if not has_submit and not status:
        return {"verdict": FAIL, "clause": "C1.1",
                "detail": "no terminal submit_answer in the trace",
                "provenance": "submit contract (submit_answer / submitted_status)"}
    return None


def _c1_2_status_class(view: dict, schema: Schema) -> dict | None:
    text = _transcript_text(view)
    for call in _tool_calls(view):
        if call.get("ok") is not False:
            continue
        path = TOOL_OPERATIONS.get(str(call.get("name")))
        if path is None:
            continue
        codes = {m for m in STATUS_RE.findall(text)}
        if not codes:
            return None  # clause abstains: no status class recoverable
        declared = schema.declared_error_codes(path)
        undeclared = sorted(codes - declared)
        if undeclared:
            return {"verdict": FAIL, "clause": "C1.2",
                    "detail": f"tool call returned undeclared error class {undeclared[0]} "
                              f"on {path}",
                    "provenance": f"openapi paths[{path}].responses"}
    return None


def _c1_3_type_conformance(view: dict, schema: Schema) -> dict | None:
    path = _invoked_path(view, schema)
    if path is None:
        return None
    sub = _submitted(view)
    if sub is None:
        return None
    types = schema.response_types(path)
    got = ("array" if isinstance(sub, list) else
           "boolean" if isinstance(sub, bool) else
           "number" if isinstance(sub, (int, float)) else
           "object" if isinstance(sub, dict) else "string")
    # A submitted string that parses as a number is treated as a number: the submit contract
    # serialises scalars as text, so refusing it would fire on serialisation, not on type.
    if got == "string" and isinstance(sub, str):
        try:
            float(sub.strip())
            got = "number"
        except (TypeError, ValueError):
            pass
    compatible = {"number": {"number", "integer"}, "string": {"string"},
                  "array": {"array"}, "boolean": {"boolean"}, "object": {"object"}}[got]
    # Fires only where the submitted type is CATEGORICALLY absent from everything the response
    # model can yield. Which field the answer projects is not recoverable without task
    # knowledge, which this clause may not use (derivation-rules.md C1.3), so the clause
    # checks the weaker property it can actually derive and abstains otherwise. It is
    # deliberately near-vacuous on scalars: that vacuity is the structural blindness the
    # predicted-null control pre-registers, not a defect to be engineered away.
    if types and not (compatible & types):
        return {"verdict": FAIL, "clause": "C1.3",
                "detail": f"submitted {got}; response model for {path} yields {sorted(types)}",
                "provenance": f"openapi paths[{path}] response model property types"}
    return None


def _c1_4_enum_membership(view: dict, schema: Schema) -> dict | None:
    path = _invoked_path(view, schema)
    if path is None:
        return None
    vocabs = schema.enums_for(path)
    if len(vocabs) != 1:
        return None  # "which enum" would be a choice, not a derivation
    vocab = {v.lower() for v in vocabs[0]}
    members = _as_collection(_submitted(view))
    if not members:
        return None
    outside = [m for m in members if m.lower() not in vocab]
    if outside:
        return {"verdict": FAIL, "clause": "C1.4",
                "detail": f"{len(outside)} submitted member(s) outside the declared vocabulary",
                "provenance": f"openapi enum declared on the response model of {path}"}
    return None


def _c1_5_cardinality(view: dict, schema: Schema) -> dict | None:
    path = _invoked_path(view, schema)
    if path is None or not schema.paginated(path):
        return None
    totals = [int(x) for x in TOTAL_RE.findall(_transcript_text(view))]
    if not totals:
        return None
    members = _as_collection(_submitted(view))
    if members is None:
        return None
    total = totals[-1]
    if len(members) != total:
        return {"verdict": FAIL, "clause": "C1.5",
                "detail": f"submitted collection has {len(members)} member(s); the paginated "
                          f"envelope the app returned declared total={total}",
                "provenance": f"openapi paginated envelope `total` on {path}"}
    return None


def _as_collection(sub: Any) -> list[str] | None:
    """The submitted answer read as a collection, or None if it is not one.

    The submit contract serialises **every** answer as text, so a submitted collection reaches
    the record as a delimited string, never as a JSON array. Testing ``isinstance(sub, list)``
    makes clauses C1.4 and C1.5 unable to fire on any trace in the corpus — a second silent
    vacuity of the same kind as the escaped-``total`` one, and equally invisible from a green
    run. This is a reader for the contract's serialisation, not a new clause: it changes what
    C1.4 and C1.5 can *see*, not what they assert.

    Conservative on purpose. A scalar that merely contains a comma — a thousands separator, a
    sentence — must not become a two-member collection, so a split is accepted only when it
    yields at least two non-numeric parts.
    """
    if isinstance(sub, list):
        return [str(x) for x in sub]
    if not isinstance(sub, str) or not sub.strip():
        return None
    for delim in ("\n", ";", ","):
        if delim in sub:
            parts = [p.strip() for p in sub.split(delim)]
            parts = [p for p in parts if p]
            if len(parts) >= 2 and not all(_is_numeric(p) for p in parts):
                return parts
    return None


def _is_numeric(s: str) -> bool:
    try:
        float(s.replace(",", ""))
    except ValueError:
        return False
    return True


def _requested_attributes(prompt: str) -> set[str]:
    words = re.split(r"[^A-Za-z0-9]+", (prompt or "").lower())
    return {w for w in words if len(w) > 3 and w not in STOPWORDS}


def vocabulary_coverage(prompt: str, schema: Schema) -> dict:
    """Diagnostic for C1.6: which requested attributes the schema declares. No verdict."""
    attrs = _requested_attributes(prompt)
    return {"attributes": sorted(attrs), "declared": sorted(attrs & schema.vocabulary),
            "undeclared": sorted(attrs - schema.vocabulary)}


def _c1_6_abstention(view: dict, schema: Schema) -> dict | None:
    attrs = _requested_attributes(str(view.get("task_prompt") or ""))
    if not attrs:
        return None
    if attrs & schema.vocabulary:
        return None  # some requested attribute is declared; the request is expressible
    status = str(view.get("submitted_status") or "").lower()
    if status in ABSTENTION_STATUSES:
        return None
    return {"verdict": FAIL, "clause": "C1.6",
            "detail": "no declared operation, parameter, or schema property matches any "
                      "requested attribute, and the answer was submitted confidently",
            "provenance": "openapi declared parameters and component schema properties"}


CLAUSES = ("C1.1", "C1.2", "C1.3", "C1.4", "C1.5", "C1.6")

#: The quarantine notice, raised and printed verbatim. Kept as a module constant so the
#: self-test can assert that the pointer to the finding has not been dropped in a refactor.
QUARANTINE_NOTICE = (
    "arm (c1) is QUARANTINED and produces no verdict.\n\n"
    "Clause C1.5 fires three times on the frozen corpus and is wrong all three times: once by\n"
    "reading a `total` from an endpoint its own provenance string does not name, and twice by\n"
    "raising a false alarm on a correct answer that is a filtered subset of the collection the\n"
    "envelope counts. Corpus-wide C1.5 precision is 0 of 3. The single apparent detection is\n"
    "fabricated, and it is the whole of c1's marginal contribution to E8.\n\n"
    "The defect is NOT repaired: PREREGISTRATION.md amendment rule 2 forbids altering a clause\n"
    "after seeing which traces it would catch, and E8 will not run.\n\n"
    "  finding:   specs/001-discovery-validation/findings/015-verifier-vs-judge-not-run.md\n"
    "  amendment: PREREGISTRATION.md Amendment B5\n\n"
    "If you are reading this because you tried to score with c1: the number you were about to\n"
    "obtain is not a measurement. Do not report it, and do not repair the clause to obtain it."
)


class Quarantined(RuntimeError):
    """Raised by :func:`verify`. c1 may not be scored; see :data:`QUARANTINE_NOTICE`."""


def verify(view: dict, record: dict, schema: Schema) -> dict:
    """**Quarantined.** Always raises :class:`Quarantined`; never returns a verdict.

    This is the entry point every caller uses — ``runner.py``, and anything a future reader
    writes. It refuses loudly rather than returning ``unverifiable``, because an
    ``unverifiable`` would flow into ``UNV_c1`` and look like a measurement.
    """
    raise Quarantined(QUARANTINE_NOTICE)


def verify_clauses_quarantined(view: dict, record: dict, schema: Schema) -> dict:
    """The preregistered clause walk, unaltered, behind a name no one calls by accident.

    Reachable only from ``selftest.py``, whose job is to prove that quarantining the arm did
    not silently edit a clause. Its verdicts are **not results** and must not be scored,
    aggregated, or reported. Raises :class:`redact.OracleLeak` if ground truth reached the
    input, exactly as before.
    """
    view = redact.scorer_content(view)
    redact.assert_no_oracle_leak(
        {"arm": "c1", "content": view}, record, where=f"c1 input {record.get('task_id')}"
    )
    for fn, needs_schema in (
        (_c1_1_output_presence, False),
        (_c1_2_status_class, True),
        (_c1_3_type_conformance, True),
        (_c1_4_enum_membership, True),
        (_c1_5_cardinality, True),
        (_c1_6_abstention, True),
    ):
        hit = fn(view, schema) if needs_schema else fn(view)
        if hit:
            return hit | {"arm": "c1", "status": "validated"}
    return {"arm": "c1", "verdict": UNVERIFIABLE, "clause": "C1.7",
            "detail": "no clause applies",
            "provenance": "openapi + submit contract; no clause matched",
            "status": "provisional"}
