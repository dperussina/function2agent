"""SPIKE - E8 verifier-vs-judge. Delete after 2026-11-30. Do not import from product code.

Arm (c2): the postcondition-derived verifier — the arm that carries the product claim.

The rule is committed in ``derivation-rules.md`` (PREREGISTRATION.md 4.5): recompute the
projection from the application's own current state through the same declared operations, and
compare under the type's own equality. c1 is structurally blind to a wrong-but-well-typed
number because nothing in it compares a magnitude. c2 is the arm that compares a magnitude,
and it is therefore the only arm that can reach the 9 numeric false successes the product
claim rests on.

Four properties of this module matter more than its arithmetic.

**It refuses rather than pretends.** A trace with no recorded derivation returns
``unverifiable`` with provenance — never a pass, never a fail. ``MD_c2`` counts fails in its
numerator, so a manufactured fail is a manufactured product claim.

**It refuses rather than degenerates.** Recomputation needs a source. With none the arm
reports ``not_run``, because "the container was not up" and "the contract could not be
derived" are different findings.

**A derivation cannot contain an answer.** The projection is a bounded declarative pipeline
over declared operations and declared response fields, evaluated by :func:`_evaluate` here —
never code supplied by the derivation file. Every literal a pipeline compares against must be
declared in the entry's ``literals`` list with a source, and :func:`validate_derivation`
mechanically verifies that a ``prompt``-sourced literal really does occur in the request text.
An expected value does not occur in a request text, so it cannot enter a derivation. This is
the enforcement behind protocol commitment 3, and it is the mechanism that separates c2 from
the hand-written checks PREREGISTRATION.md 3 retired.

**Tolerance is derived, not chosen.** :data:`PRECISION_LADDER` is the ordered set of places a
comparison precision may come from. It is fixed in ``derivation-rules.md`` in advance, it
contains no per-task rule, and its last rung is a refusal rather than a default. On this
target the first rung is empty: ``groundtruth/openapi.json`` declares no ``multipleOf`` and no
numeric ``format`` in any of its 243 component schemas, so schema-declared precision — the
thing PREREGISTRATION.md 4.5 instructs c2 to use — does not exist here. See Amendment B2.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from decimal import Decimal
from typing import Any

import redact
import recompute_source
from recompute_source import (  # noqa: F401 - re-exported for the runner's convenience
    NoRecomputationSource,
    RecomputationSource,
    open_source,
)

HERE = os.path.dirname(os.path.abspath(__file__))
DERIVATIONS_PATH = os.path.join(HERE, "c2_derivations.json")

PASS, FAIL, UNVERIFIABLE, NOT_RUN = "pass", "fail", "unverifiable", "not_run"

#: The comparison vocabulary. There is no per-task tolerance and none can be supplied.
COMPARISONS = ("exact_int", "exact_decimal", "decimal_at_declared_precision",
               "exact_set", "exact_text", "sequence")

#: Where a comparison precision may be derived from, in order. ``derivation-rules.md`` fixes
#: this ladder in advance; a derivation names the rung it used and the validator checks the
#: rung is consistent with the comparison.
PRECISION_LADDER = (
    "P0_exact_identity",       # the comparison is over text or set identity; no precision applies
    "P1_schema_declared",      # multipleOf / numeric format on the projected field
    "P2_integer_closed",       # projection closed over `type: integer` fields -> exact
    "P3_app_serialisation",    # closed over the app's own serialised decimals -> exact decimal
    "P4_request_declared",     # the request declares an output precision
    "P5_refuse",               # none of the above: `unverifiable`, never a default tolerance
)

LITERAL_SOURCES = ("prompt", "schema_enum", "schema_field", "schema_operation")

#: A task identifier in the corpus renders as e.g. two-to-three capitals, digits, a dot,
#: digits. Protocol commitment 3 forbids one appearing in a derivation; this is the check.
TASK_ID_RE = re.compile(r"\b[A-Z]{1,3}\d*\.\d{3}\b")

#: Number words, so that a request saying "more than five ingredients" can source the literal
#: 5 from its own text. General English, no task knowledge.
NUMBER_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirty": 30, "sixty": 60,
    "ninety": 90, "hundred": 100,
}


class DerivationInvalid(ValueError):
    """A derivation names something the contract does not declare, or a literal the request
    does not contain. Refused loudly: a derivation that fails this check is the exact
    substitution PREREGISTRATION.md 3 exists to prevent."""


# ------------------------------------------------------------------ keying

def request_signature(task_prompt: str) -> str:
    """A stable key for a request, derived from the prompt text alone.

    Derivations are keyed by this rather than by a task identifier so that
    ``c2_derivations.json`` stays a rule application and cannot become a per-task answer key
    (protocol commitment 3).
    """
    norm = re.sub(r"\s+", " ", (task_prompt or "").strip().lower())
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]


def load_derivations() -> dict:
    if not os.path.isfile(DERIVATIONS_PATH):
        return {"_comment": "missing", "derivations": {}}
    with open(DERIVATIONS_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def derivations_hash() -> str:
    if not os.path.isfile(DERIVATIONS_PATH):
        return "absent"
    with open(DERIVATIONS_PATH, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()[:16]


# ------------------------------------------------------------------ field access

def _get_path(rec: Any, path: str) -> Any:
    """Read a dotted field path over declared response fields. ``[]`` flattens an array.

    ``tags[].name`` over a recipe yields the list of tag names; ``recipe.slug`` yields one
    value. Nothing here evaluates a string from the derivation file as code.
    """
    cur: Any = rec
    for seg in path.split("."):
        flatten = seg.endswith("[]")
        key = seg[:-2] if flatten else seg
        if key:
            if isinstance(cur, list):
                cur = [(_x.get(key) if isinstance(_x, dict) else None) for _x in cur]
                cur = [x for x in cur if x is not None]
                if flatten:
                    out: list = []
                    for x in cur:
                        out.extend(x if isinstance(x, list) else [x])
                    cur = out
                continue
            cur = cur.get(key) if isinstance(cur, dict) else None
        if flatten and isinstance(cur, list):
            continue
        if flatten and cur is None:
            cur = []
    return cur


def _norm(v: Any) -> Any:
    return v.strip().lower() if isinstance(v, str) else v


def _as_number(v: Any) -> float | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v.strip().replace(",", ""))
        except ValueError:
            return None
    return None


DURATION_RE = re.compile(r"(-?\d+(?:\.\d+)?)\s*(minute|min|hour|hr)", re.I)


def _duration_minutes(v: Any) -> float | None:
    """Minutes out of the free text the app serialises a duration as.

    ``prepTime`` and ``cookTime`` are declared ``anyOf: [string, null]`` with no format, so a
    duration has to be read out of the application's own rendering. This is a reader for that
    rendering, not a tolerance and not a task rule.
    """
    if v is None:
        return None
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    m = DURATION_RE.search(str(v))
    if not m:
        return None
    n = float(m.group(1))
    return n * 60 if m.group(2).lower().startswith(("hour", "hr")) else n


def _weekday(v: Any) -> str | None:
    import datetime  # noqa: PLC0415
    try:
        return datetime.date.fromisoformat(str(v)[:10]).strftime("%A").lower()
    except (ValueError, TypeError):
        return None


TESTS = {
    "eq": lambda a, b: _norm(a) == _norm(b),
    "ne": lambda a, b: _norm(a) != _norm(b),
    "gt": lambda a, b: _as_number(a) is not None and _as_number(a) > float(b),
    "gte": lambda a, b: _as_number(a) is not None and _as_number(a) >= float(b),
    "lt": lambda a, b: _as_number(a) is not None and _as_number(a) < float(b),
    "lte": lambda a, b: _as_number(a) is not None and _as_number(a) <= float(b),
    "contains": lambda a, b: any(_norm(b) == _norm(x) for x in (a or [])),
    "not_contains": lambda a, b: not any(_norm(b) == _norm(x) for x in (a or [])),
    "contains_substr": lambda a, b: any(str(b).lower() in str(x).lower() for x in (a or [])),
    "is_null": lambda a, _b: a is None,
    "not_null": lambda a, _b: a is not None,
    "is_empty": lambda a, _b: not a,
    "not_empty": lambda a, _b: bool(a),
}

#: Tests that take no literal at all. Used by the literal audit.
NULLARY_TESTS = ("is_null", "not_null", "is_empty", "not_empty")

DERIVE_FNS = ("duration_minutes", "weekday", "length", "sum_field", "add", "count_where",
              "distinct_count")

AGGREGATES = ("count", "count_distinct", "sum", "mean", "min", "max", "set", "argmax",
              "argmin", "single")

STEP_OPS = ("read", "join", "semi_join", "anti_join", "explode", "group", "filter",
            "derive", "dedupe", "project", "aggregate")

#: ``group`` introduces exactly these two names into the row shape. Named here so the
#: validator can tell a legitimately introduced field from an undeclared one.
GROUP_FIELDS = ("key", "count")


# ------------------------------------------------------------------ pipeline evaluation

def _evaluate(pipeline: list[dict], source: RecomputationSource) -> Any:
    """Run a bounded declarative pipeline. The vocabulary is fixed by :data:`STEP_OPS`.

    A derivation file that could execute arbitrary code would be a per-task check with extra
    steps, and protocol commitment 3 forbids that. Every operation, field and literal a step
    names has already been checked by :func:`validate_derivation`.
    """
    rows: Any = []
    for step in pipeline:
        op = step["op"]
        if op == "read":
            data = source.read(step["operation"], step.get("params"))
            rows = list(data.values()) if isinstance(data, dict) else list(data or [])
        elif op == "join":
            side = source.read(step["operation"])
            index = side if isinstance(side, dict) else {
                str(_get_path(x, step["side_key"])): x for x in (side or [])}
            merged = []
            for r in rows:
                key = str(_get_path(r, step["on"]))
                hit = index.get(key)
                merged.append(r | {step["as"]: hit} if hit is not None else r | {step["as"]: None})
            rows = merged
        elif op in ("semi_join", "anti_join"):
            side = source.read(step["operation"])
            side_rows = list(side.values()) if isinstance(side, dict) else list(side or [])
            keys = {str(_get_path(x, step["side_key"])) for x in side_rows}
            keep = (op == "semi_join")
            rows = [r for r in rows if (str(_get_path(r, step["on"])) in keys) is keep]
        elif op == "explode":
            out = []
            for r in rows:
                nested = _get_path(r, step["field"]) or []
                out.extend(nested if isinstance(nested, list) else [nested])
            rows = out
        elif op == "group":
            buckets: dict[str, int] = {}
            for r in rows:
                buckets[str(_get_path(r, step["by"]))] = \
                    buckets.get(str(_get_path(r, step["by"])), 0) + 1
            rows = [{"key": k, "count": n} for k, n in sorted(buckets.items())]
        elif op == "filter":
            test = TESTS[step["test"]]
            rows = [r for r in rows if test(_get_path(r, step["field"]), step.get("value"))]
        elif op == "derive":
            rows = [r | {step["as"]: _derive(r, step)} for r in rows]
        elif op == "dedupe":
            seen, out = set(), []
            for r in rows:
                k = json.dumps(_get_path(r, step["field"]), sort_keys=True, default=str)
                if k not in seen:
                    seen.add(k)
                    out.append(r)
            rows = out
        elif op == "project":
            rows = [_get_path(r, step["field"]) for r in rows]
        elif op == "aggregate":
            return _aggregate(rows, step)
        else:  # pragma: no cover - validate_derivation rejects this first
            raise DerivationInvalid(f"unknown step op {op!r}")
    return rows


def _derive(rec: dict, step: dict) -> Any:
    fn = step["fn"]
    if fn == "duration_minutes":
        return _duration_minutes(_get_path(rec, step["field"]))
    if fn == "weekday":
        return _weekday(_get_path(rec, step["field"]))
    if fn == "length":
        v = _get_path(rec, step["field"])
        return len(v) if isinstance(v, (list, str)) else 0
    if fn == "sum_field":
        vals = _get_path(rec, step["field"]) or []
        nums = [_as_number(v) for v in vals]
        return sum(n for n in nums if n is not None)
    if fn == "add":
        total = 0.0
        for f in step["fields"]:
            n = _as_number(_get_path(rec, f))
            total += n if n is not None else 0.0
        return total
    if fn in ("count_where", "distinct_count"):
        items = _get_path(rec, step["field"]) or []
        where = step.get("where")
        if where:
            test = TESTS[where["test"]]
            items = [i for i in items if test(_get_path(i, where["field"]), where.get("value"))]
        if fn == "distinct_count":
            return len({json.dumps(i, sort_keys=True, default=str) for i in items})
        return len(items)
    raise DerivationInvalid(f"unknown derive fn {fn!r}")  # pragma: no cover


def _aggregate(rows: Any, step: dict) -> Any:
    kind = step["kind"]
    field = step.get("field")
    if kind == "count":
        return len(rows or [])
    if kind == "count_distinct":
        keys = [_get_path(r, field) if field else r for r in (rows or [])]
        return len({json.dumps(k, sort_keys=True, default=str) for k in keys})
    if kind == "set":
        vals = [_get_path(r, field) if field else r for r in (rows or [])]
        flat: list = []
        for v in vals:
            flat.extend(v if isinstance(v, list) else [v])
        return sorted({str(v) for v in flat if v is not None})
    vals = [_as_number(_get_path(r, field) if field else r) for r in (rows or [])]
    vals = [v for v in vals if v is not None]
    if kind == "sum":
        return _decimal_sum(vals)
    if kind == "mean":
        return (sum(vals) / len(vals)) if vals else None
    if kind == "min":
        return min(vals) if vals else None
    if kind == "max":
        return max(vals) if vals else None
    if kind in ("argmax", "argmin"):
        scored = [(_as_number(_get_path(r, field)), r) for r in (rows or [])]
        scored = [(s, r) for s, r in scored if s is not None]
        if not scored:
            return None
        pick = (max if kind == "argmax" else min)(scored, key=lambda t: t[0])[1]
        return _get_path(pick, step["label"])
    if kind == "single":
        vals2 = [_get_path(r, field) if field else r for r in (rows or [])]
        return vals2[0] if len(vals2) == 1 else None
    raise DerivationInvalid(f"unknown aggregate {kind!r}")  # pragma: no cover


def _decimal_sum(vals: list[float]) -> float:
    """Sum in decimal, so a sum of the app's own serialised decimals is exact.

    Binary floating point makes ``0.25 + 1.5 + 6`` order-dependent in the last bits, which
    would turn rung P3 of the precision ladder into a coin flip. The values summed are the
    decimals the application serialised, so decimal arithmetic is the arithmetic of the
    representation rather than a tolerance.
    """
    total = Decimal("0")
    for v in vals:
        total += Decimal(str(v))
    return float(total)


# ------------------------------------------------------------------ comparison

def _decimals_emitted(vals: list[Any]) -> int:
    best = 0
    for v in vals:
        s = str(v)
        if "." in s and "e" not in s.lower():
            best = max(best, len(s.split(".")[-1].rstrip("0")))
    return best


def compare(submitted: Any, recomputed: Any, comparison: str,
            decimals: int | None) -> tuple[bool, str]:
    """The rule's comparison. No per-task tolerance exists or can be supplied."""
    if comparison == "sequence":
        parts = _split_sequence(submitted)
        want = list(recomputed or [])
        if parts is None or len(parts) != len(want):
            return False, (f"submitted {len(parts) if parts is not None else 0} part(s) vs "
                           f"recomputed {len(want)}")
        for got, exp in zip(parts, want):
            ok, why = compare(got, exp, "exact_int", None)
            if not ok:
                return False, f"part mismatch: {why}"
        return True, f"all {len(want)} part(s) equal"
    if comparison == "exact_set":
        a, b = _as_set(submitted), _as_set(recomputed)
        if a is None or b is None:
            return False, "one side is not a collection"
        return (a == b), (f"submitted |{len(a)}| vs recomputed |{len(b)}|; "
                          f"{len(a - b)} unexpected, {len(b - a)} missing")
    if comparison == "exact_text":
        if recomputed is None:
            return False, "recomputation produced no value"
        return (_norm(str(submitted)) == _norm(str(recomputed))), \
            f"submitted {str(submitted)!r} vs recomputed {str(recomputed)!r}"
    a, b = _as_number(submitted), _as_number(recomputed)
    if a is None or b is None:
        return False, f"one side is not a number (submitted {submitted!r}, recomputed {recomputed!r})"
    if comparison == "exact_int":
        return (a == b), f"submitted {a!r} vs recomputed {b!r}, exact equality"
    if comparison == "exact_decimal":
        dp = decimals if decimals is not None else _decimals_emitted([recomputed])
        return (round(a, dp) == round(b, dp)), \
            f"submitted {a!r} vs recomputed {b!r} at {dp} decimal place(s) of app serialisation"
    if comparison == "decimal_at_declared_precision":
        if decimals is None:
            raise DerivationInvalid(
                "decimal_at_declared_precision with no declared precision; the ladder's last "
                "rung is a refusal, not a default tolerance")
        return (round(a, decimals) == round(b, decimals)), \
            f"submitted {a!r} vs recomputed {b!r} at the {decimals} decimal place(s) declared"
    raise DerivationInvalid(f"unknown comparison {comparison!r}; expected one of {COMPARISONS}")


def _as_set(v: Any) -> set[str] | None:
    if v is None:
        return None
    if isinstance(v, (list, tuple, set)):
        return {str(x).strip().lower() for x in v}
    if isinstance(v, str):
        parts = [p.strip().lower() for p in re.split(r"[,;\n]", v)]
        return {p for p in parts if p}
    return None


def _split_sequence(v: Any) -> list[str] | None:
    if isinstance(v, (list, tuple)):
        return [str(x) for x in v]
    if isinstance(v, str):
        parts = [p.strip() for p in re.split(r"[,;\n]", v)]
        return [p for p in parts if p]
    return None


# ------------------------------------------------------------------ the integrity audit

def _walk_literals(pipeline: list[dict]) -> list[Any]:
    """Every literal a pipeline compares against, with the nullary tests excluded."""
    out: list[Any] = []

    def visit(step: dict) -> None:
        if step.get("op") == "filter" or "test" in step:
            if step.get("test") not in NULLARY_TESTS and "value" in step:
                out.append(step["value"])
        if isinstance(step.get("where"), dict):
            visit(step["where"])
        for v in step.values():
            if isinstance(v, list):
                for x in v:
                    if isinstance(x, dict):
                        visit(x)
    for s in pipeline:
        visit(s)
    return out


def _prompt_tokens(prompt: str) -> set[str]:
    text = (prompt or "").lower()
    toks = set(re.split(r"[^a-z0-9.']+", text))
    for word, n in NUMBER_WORDS.items():
        if re.search(rf"\b{word}\b", text):
            toks.add(str(n))
            toks.add(f"{n}.0")
    # bare digits already present as tokens; add their float rendering too
    for m in re.findall(r"\b\d+(?:\.\d+)?\b", text):
        toks.add(m)
        toks.add(str(float(m)))
    # A request that names a unit of time names the magnitude in the unit the application
    # serialises durations in. General English, no task knowledge.
    if re.search(r"\bhours?\b", text):
        toks.update({"60", "60.0"})
    return {t for t in toks if t}


def validate_derivation(entry: dict, prompt: str, declared_fields: set[str]) -> list[str]:
    """Every reason this derivation may not be used. Empty list means it is admissible.

    This is protocol commitment 3 made mechanical. The checks, in the order they matter:

    1. No task identifier anywhere in the entry.
    2. Every operation is one the OpenAPI document declares.
    3. Every field path segment is a declared response property, or a name an earlier
       ``derive`` step in the same pipeline introduced.
    4. Every literal a filter compares against is declared in ``literals`` with a source, and
       a ``prompt``-sourced literal really does occur in the request text.
    5. The comparison and the precision rung are consistent, and no rung below the ladder is
       invented.

    Check 4 is the one that does the work. An expected value does not appear in the text of
    the request that produced it, so it cannot pass. That is the difference between this arm
    and the hand-written checks PREREGISTRATION.md 3 retired.
    """
    problems: list[str] = []
    blob = json.dumps(entry)
    for hit in set(TASK_ID_RE.findall(blob)):
        problems.append(f"task identifier {hit!r} appears in the derivation")

    if entry.get("refused"):
        # A refusal asserts nothing about a value, so the comparison and precision checks
        # have nothing to check. It must sit on the ladder's refusal rung and carry no
        # pipeline, so that "c2 declined" can never be mistaken for "c2 passed it".
        if (entry.get("precision") or {}).get("rule") != "P5_refuse":
            problems.append("a refusal must record precision rung P5_refuse")
        if entry.get("pipeline") or entry.get("parts"):
            problems.append("a refusal must carry no pipeline")
        return problems

    pipelines = entry.get("parts") or [entry.get("pipeline") or []]
    tokens = _prompt_tokens(prompt)
    declared_literals = {json.dumps(x.get("value"), sort_keys=True): x
                         for x in (entry.get("literals") or [])}

    for lit in entry.get("literals") or []:
        src = lit.get("source")
        if src not in LITERAL_SOURCES:
            problems.append(f"literal {lit.get('value')!r} has source {src!r}, "
                            f"expected one of {LITERAL_SOURCES}")
        elif src == "prompt":
            tok = str(lit.get("token", "")).lower().strip()
            if not tok:
                problems.append(f"literal {lit.get('value')!r} claims the prompt but names no token")
            elif tok not in tokens and tok not in re.sub(r"\s+", " ", (prompt or "").lower()):
                problems.append(
                    f"literal {lit.get('value')!r} claims prompt token {tok!r}, which the "
                    "request does not contain")

    for pipeline in pipelines:
        introduced: set[str] = set()
        for step in pipeline:
            op = step.get("op")
            if op not in STEP_OPS:
                problems.append(f"unknown step op {op!r}")
                continue
            for key in ("operation",):
                if key in step and step[key] not in recompute_source.DECLARED_OPERATIONS:
                    problems.append(f"{step[key]!r} is not a declared operation")
            if op == "derive":
                if step.get("fn") not in DERIVE_FNS:
                    problems.append(f"unknown derive fn {step.get('fn')!r}")
                introduced.add(step.get("as", ""))
            if op == "join":
                introduced.add(step.get("as", ""))
            if op == "group":
                introduced.update(GROUP_FIELDS)
                if isinstance(step.get("by"), str):
                    problems += _check_path(step["by"], declared_fields, introduced)
            if op == "aggregate" and step.get("kind") not in AGGREGATES:
                problems.append(f"unknown aggregate {step.get('kind')!r}")
            for key in ("field", "on", "side_key", "label"):
                path = step.get(key)
                if isinstance(path, str):
                    problems += _check_path(path, declared_fields, introduced)
            for f in step.get("fields") or []:
                problems += _check_path(f, declared_fields, introduced)
            where = step.get("where")
            if isinstance(where, dict) and isinstance(where.get("field"), str):
                problems += _check_path(where["field"], declared_fields, introduced)

        for lit in _walk_literals(pipeline):
            key = json.dumps(lit, sort_keys=True)
            if key not in declared_literals:
                problems.append(
                    f"literal {lit!r} is compared against but is not declared in `literals`; "
                    "an undeclared literal is exactly how an expected value would enter")

    comparison = entry.get("comparison")
    if comparison not in COMPARISONS:
        problems.append(f"unknown comparison {comparison!r}")
    rung = (entry.get("precision") or {}).get("rule")
    if rung not in PRECISION_LADDER:
        problems.append(f"precision rung {rung!r} is not on the ladder {PRECISION_LADDER}")
    if comparison == "decimal_at_declared_precision":
        if rung not in ("P1_schema_declared", "P4_request_declared"):
            problems.append(
                f"comparison {comparison!r} needs a declared precision; rung {rung!r} declares none")
        if (entry.get("precision") or {}).get("decimals") is None:
            problems.append("declared-precision comparison with no decimals recorded")
    if comparison in ("exact_int", "sequence") and \
            rung not in ("P2_integer_closed", "P1_schema_declared"):
        problems.append(
            f"exact integer comparison claims rung {rung!r}; exactness must come from the "
            "projection being closed over integer-declared fields")
    if comparison == "exact_decimal" and rung not in ("P3_app_serialisation", "P1_schema_declared"):
        problems.append(
            f"exact decimal comparison claims rung {rung!r}; it must come from the "
            "application's own serialisation or from a schema-declared precision")
    if comparison in ("exact_set", "exact_text") and rung != "P0_exact_identity":
        problems.append(
            f"identity comparison claims rung {rung!r}; no numeric precision applies to it")
    if rung == "P5_refuse" and not entry.get("refused"):
        problems.append("rung P5 is a refusal; an entry on P5 must carry a `refused` reason "
                        "and score nothing")
    return problems


def _check_path(path: str, declared: set[str], introduced: set[str]) -> list[str]:
    bad = []
    for seg in path.split("."):
        name = seg[:-2] if seg.endswith("[]") else seg
        if not name:
            continue
        if name.lower() not in declared and name not in introduced:
            bad.append(f"field {name!r} in path {path!r} is not a declared response property")
    return bad


def declared_field_names(openapi_path: str) -> set[str]:
    """Every property name any component schema declares, lower-cased."""
    with open(openapi_path, encoding="utf-8") as fh:
        doc = json.load(fh)
    names: set[str] = set()
    for sch in (doc.get("components", {}).get("schemas") or {}).values():
        for prop in (sch.get("properties") or {}):
            names.add(str(prop).lower())
    return names


def audit_all(derivations: dict, battery: dict, declared_fields: set[str]) -> dict:
    """Validate every recorded derivation against the request it claims to derive from."""
    prompts = {request_signature(t["prompt"]): t["prompt"] for t in battery.values()}
    problems: dict[str, list[str]] = {}
    for sig, entry in (derivations.get("derivations") or {}).items():
        prompt = entry.get("request") or prompts.get(sig, "")
        if request_signature(prompt) != sig:
            problems[sig] = ["the recorded request text does not hash to this key"]
            continue
        found = validate_derivation(entry, prompt, declared_fields)
        if found:
            problems[sig] = found
    return {"n_derivations": len(derivations.get("derivations") or {}),
            "n_invalid": len(problems), "problems": problems}


# ------------------------------------------------------------------ the arm

def verify(view: dict, record: dict, source: RecomputationSource | None,
           derivations: dict | None = None) -> dict:
    """Score one trace. Raises :class:`redact.OracleLeak` if ground truth reached the input."""
    view = redact.scorer_content(view)
    redact.assert_no_oracle_leak(
        {"arm": "c2", "content": view}, record, where=f"c2 input {record.get('task_id')}"
    )
    if source is None:
        return {"arm": "c2", "verdict": NOT_RUN, "clause": None,
                "detail": "no recomputation source was supplied",
                "provenance": None, "status": "provisional"}

    derivations = derivations if derivations is not None else load_derivations()
    sig = request_signature(str(view.get("task_prompt") or ""))
    entry = (derivations.get("derivations") or {}).get(sig)
    if not entry:
        return {"arm": "c2", "verdict": UNVERIFIABLE, "clause": None,
                "detail": "no derivation recorded for this request signature; the projection "
                          "is not expressible over declared operations, or has not been derived",
                "provenance": f"request_signature={sig}", "status": "provisional"}
    if entry.get("refused"):
        return {"arm": "c2", "verdict": UNVERIFIABLE, "clause": entry.get("rule"),
                "detail": entry["refused"], "provenance": entry.get("provenance"),
                "status": "provisional"}
    if view.get("submitted") in (None, ""):
        return {"arm": "c2", "verdict": UNVERIFIABLE, "clause": entry.get("rule"),
                "detail": "no answer was submitted; there is no value to compare a "
                          "postcondition against",
                "provenance": entry.get("provenance"), "status": "provisional"}

    try:
        recomputed = _recompute(entry, source)
    except Exception as exc:  # noqa: BLE001 - a failed re-read is unverifiable, never a fail
        return {"arm": "c2", "verdict": UNVERIFIABLE, "clause": entry.get("rule"),
                "detail": f"recomputation could not complete: {type(exc).__name__}: {exc}",
                "provenance": entry.get("provenance"), "status": "provisional"}

    if recomputed is None:
        return {"arm": "c2", "verdict": UNVERIFIABLE, "clause": entry.get("rule"),
                "detail": "the recomputation produced no value",
                "provenance": entry.get("provenance"), "status": "provisional"}

    decimals = (entry.get("precision") or {}).get("decimals")
    try:
        ok, detail = compare(view.get("submitted"), recomputed,
                             entry.get("comparison", "exact_int"), decimals)
    except DerivationInvalid as exc:
        return {"arm": "c2", "verdict": UNVERIFIABLE, "clause": entry.get("rule"),
                "detail": str(exc), "provenance": entry.get("provenance"),
                "status": "provisional"}
    return {
        "arm": "c2",
        "verdict": PASS if ok else FAIL,
        "clause": entry.get("rule"),
        "detail": detail,
        "recomputed": recomputed,
        "provenance": entry.get("provenance"),
        "precision": entry.get("precision"),
        "status": entry.get("status", "provisional"),
    }


def _recompute(entry: dict, source: RecomputationSource) -> Any:
    """Re-issue the declared reads and apply the recorded projection."""
    if entry.get("parts"):
        return [_evaluate(p, source) for p in entry["parts"]]
    return _evaluate(entry["pipeline"], source)


def main() -> int:
    import freeze  # noqa: PLC0415
    import corpus  # noqa: PLC0415

    cfg = freeze.load_config()
    battery = corpus.load_battery(cfg)
    fields = declared_field_names(
        os.path.abspath(os.path.join(HERE, cfg["battery"]["openapi_rel"])))
    rep = audit_all(load_derivations(), battery, fields)
    print(json.dumps(rep, indent=1))
    return 1 if rep["n_invalid"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
