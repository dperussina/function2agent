#!/usr/bin/env python3
"""Candidate set S and served set A_c for the three non-FastAPI fixtures.

**S is derived from source by AST walk**, mirroring what codegraph does on the FastAPI target:
it sees every route *declaration*, including the ones inside `if ENABLE_ADMIN:`, because a
static reader cannot evaluate that guard. This is deliberate — S must be a superset of A_c or
precision cannot fall below 1.0 and the gate cannot be failed.

**A_c is read from the framework's own router at runtime** (FR-008), never transcribed:
  Starlette   `app.routes`, each Route's own `.methods`
  Flask       `app.url_map`, each Rule's own `.methods`
  Django      the resolved URL patterns, plus each view's own declared method list recovered
              from `require_http_methods`' closure

The Django path has one documented exception, and it is a finding rather than a shortcut: for a
view with no method decorator, **the framework holds no method information anywhere**, so there
is nothing to read. That view declares its own list as a function attribute and this script
records it with `source: "author-declared"` so the report can say which single operation is not
framework-derived.

Usage:  fixture_sets.py --out fixture-sets.json
"""

import argparse
import ast
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURES = os.path.join(HERE, "fixtures")

# Four nulls per target (FR-003), disjoint from every S by construction. The second is shaped
# as a plausible member of a real route family, matching finding 010's null design.
NULLS = [
    ["GET", "/f2a-phantom-alpha"],
    ["POST", "/items/f2a-phantom-beta"],
    ["DELETE", "/f2a/phantom/gamma"],
    ["PATCH", "/f2a-phantom-delta"],
]

VERBS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}


def normalise(p):
    """One path shape across three frameworks: `<str:name>` and `<name>` both become `{name}`.

    Applied identically to S and to A_c so the normalisation cannot flatter either.
    """
    p = p.replace("<", "{").replace(">", "}")
    for conv in ("string:", "str:", "int:", "path:", "slug:", "uuid:"):
        p = p.replace("{" + conv, "{")
    return p


# ----------------------------------------------------------------- S, from source by AST walk
def _lit(node):
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _methods_from_kw(kws):
    for kw in kws:
        if kw.arg == "methods":
            if isinstance(kw.value, (ast.List, ast.Tuple)):
                got = [_lit(e) for e in kw.value.elts]
                return [m for m in got if m]
            # A non-literal methods= list is exactly the case a static reader cannot resolve.
            return None
    return []


def static_set(framework, src):
    """Every (method, path) the source *declares*, guards unevaluated."""
    tree = ast.parse(src)
    out = set()
    unresolved = []

    if framework == "starlette":
        # Route("/p", handler, methods=[...])
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == "Route"):
                continue
            p = _lit(node.args[0]) if node.args else None
            if p is None:
                continue
            ms = _methods_from_kw(node.keywords)
            if ms is None:
                unresolved.append(p)
                continue
            for m in ms or ["GET"]:
                out.add((m, normalise(p)))

    elif framework == "flask":
        # @app.get("/p") / @app.post("/p") / @app.route("/p", methods=[...])
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for d in node.decorator_list:
                if not (isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute)):
                    continue
                attr = d.func.attr
                p = _lit(d.args[0]) if d.args else None
                if p is None:
                    continue
                if attr.upper() in VERBS:
                    out.add((attr.upper(), normalise(p)))
                elif attr == "route":
                    ms = _methods_from_kw(d.keywords)
                    if ms is None:
                        unresolved.append(p)
                        continue
                    for m in ms or ["GET"]:
                        out.add((m, normalise(p)))

    elif framework == "django":
        # path("p", view) pairs with the view's @require_http_methods([...]) list. A view with
        # no such decorator is a *static* unknown too, and is recorded as one.
        decl = {}
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            ms, saw = None, False
            for d in node.decorator_list:
                if isinstance(d, ast.Call) and getattr(d.func, "id", None) == "require_http_methods":
                    saw = True
                    a = d.args[0] if d.args else None
                    if isinstance(a, (ast.List, ast.Tuple)):
                        ms = [x for x in (_lit(e) for e in a.elts) if x]
                    else:
                        ms = None  # e.g. require_http_methods(_GATED) — a name, not a literal
            prev_ms, prev_saw = decl.get(node.name, (None, False))
            if ms is not None and prev_ms is not None:
                ms = sorted(set(prev_ms) | set(ms))
            elif ms is None and prev_ms is not None:
                ms = prev_ms
            decl[node.name] = (ms, saw or prev_saw)
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == "path"):
                continue
            p = _lit(node.args[0]) if node.args else None
            view = getattr(node.args[1], "id", None) if len(node.args) > 1 else None
            if p is None or view is None:
                continue
            p = normalise("/" + p)
            ms, saw = decl.get(view, (None, False))
            if ms is None:
                unresolved.append(f"{p} (view {view}: "
                                  f"{'non-literal method list' if saw else 'no method decorator'})")
                continue
            for m in ms:
                out.add((m, p))
    else:
        raise SystemExit(f"unknown framework {framework}")

    return sorted(out), unresolved


# --------------------------------------------------- A_c, from the framework's own router
def served_starlette():
    sys.path.insert(0, FIXTURES)
    import app_starlette as m

    out, provenance = set(), {}
    for r in m.app.routes:
        for meth in sorted(r.methods or []):
            if meth == "HEAD":
                continue
            out.add((meth, r.path))
            provenance[f"{meth} {r.path}"] = "framework-read: Route.methods"
    return sorted(out), provenance


def served_flask():
    sys.path.insert(0, FIXTURES)
    import app_flask as m

    out, provenance = set(), {}
    for rule in m.app.url_map.iter_rules():
        p = rule.rule
        for meth in sorted(rule.methods or []):
            if meth in ("HEAD", "OPTIONS"):  # Werkzeug adds both automatically
                continue
            norm = normalise(p)
            out.add((meth, norm))
            provenance[f"{meth} {norm}"] = "framework-read: Rule.methods"
    return sorted(out), provenance


def served_django():
    sys.path.insert(0, FIXTURES)
    import app_django as m
    from django.urls import get_resolver

    def declared_methods(view):
        """Recover require_http_methods' list from its own closure."""
        for cell in view.__closure__ or ():
            try:
                val = cell.cell_contents
            except ValueError:
                continue
            if isinstance(val, (list, tuple)) and val and all(
                isinstance(x, str) and x.upper() in VERBS for x in val
            ):
                return [x.upper() for x in val], "framework-read: require_http_methods closure"
            if callable(val) and getattr(val, "__closure__", None):
                got = declared_methods(val)
                if got[0]:
                    return got
        declared = getattr(view, "f2a_serves", None)
        if declared:
            return list(declared), "author-declared: framework holds no method information"
        return None, "unrecoverable"

    out, provenance = set(), {}
    for pat in get_resolver(m.__name__).url_patterns:
        p = "/" + str(pat.pattern)
        norm = normalise(p)
        ms, how = declared_methods(pat.callback)
        for meth in ms or []:
            out.add((meth, norm))
            provenance[f"{meth} {norm}"] = how
    return sorted(out), provenance


BUILDERS = {
    "starlette": served_starlette,
    "flask": served_flask,
    "django": served_django,
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--only", default="starlette,flask,django")
    args = ap.parse_args()

    payload = {}
    for fw in args.only.split(","):
        src = open(os.path.join(FIXTURES, f"app_{fw}.py")).read()
        S, unresolved = static_set(fw, src)
        # Each framework gets its own subprocess-free import; Django must be last because it
        # calls settings.configure() at import time.
        served, provenance = BUILDERS[fw]()
        payload[fw] = {
            "static_set": [list(p) for p in S],
            "static_set_size": len(S),
            "static_unresolved": unresolved,
            "served_set": [list(p) for p in served],
            "served_set_size": len(served),
            "served_provenance": provenance,
            "null_set": NULLS,
            "null_set_size": len(NULLS),
            "declared_not_served": [list(p) for p in sorted(set(S) - set(served))],
        }
        print(f"{fw:10s} S={len(S):3d}  served={len(served):3d}  "
              f"declared-not-served={len(set(S) - set(served))}  "
              f"static-unresolved={len(unresolved)}")
        for u in unresolved:
            print(f"             static could not resolve: {u}")
        author = [k for k, v in provenance.items() if v.startswith("author-declared")]
        for a in author:
            print(f"             ground truth NOT framework-read: {a}")

    json.dump(payload, open(args.out, "w"), indent=2, sort_keys=True)
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
