"""How far does parsing the index's `signature` string alone get?

This measures a capability ceiling, not accuracy. It asks one question of a
signature string: can structured parameters (a name and a declared type for
each) and a return type be read out of it? Whether the answer is *correct* is
not assessed here, and for the TypeScript corpus cannot be — there is no
published schema to check it against.

The same parser is run over both corpora so the two numbers mean the same
thing. It never reads a source file; only the `signature` and `return_type`
columns of the index are touched.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from collections import Counter

OPEN = "([{<"
CLOSE = ")]}>"


def split_top(text, sep=","):
    """Split on `sep` at bracket depth zero, ignoring string literals."""
    out, buf, depth, quote = [], [], 0, None
    for ch in text:
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in "'\"`":
            quote = ch
            buf.append(ch)
            continue
        if ch in OPEN:
            depth += 1
        elif ch in CLOSE:
            depth -= 1
        if ch == sep and depth == 0:
            out.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    if "".join(buf).strip():
        out.append("".join(buf))
    return [p.strip() for p in out if p.strip()]


def split_signature(sig, language):
    """Return (param_blob, return_text) or (None, None) if no call shape."""
    s = " ".join(sig.split())
    start = s.find("(")
    if start < 0:
        return None, None
    depth = 0
    end = -1
    for i in range(start, len(s)):
        if s[i] == "(":
            depth += 1
        elif s[i] == ")":
            depth -= 1
            if depth == 0:
                end = i
                break
    if end < 0:
        return None, None
    params = s[start + 1 : end]
    tail = s[end + 1 :].strip()
    if language == "python":
        m = re.match(r"^->\s*(.+?)\s*:?$", tail)
        ret = m.group(1).strip() if m else None
    else:
        m = re.match(r"^(?::|=>)\s*(.+?)\s*;?$", tail)
        ret = m.group(1).strip() if m else None
    if ret in ("", None):
        ret = None
    return params, ret


PY_SKIP = {"self", "cls", "*", "/"}
UNINFORMATIVE_RETURNS = {"any", "unknown", "object", "void", "Any", "None"}


def parse_params(blob, language):
    """(total, typed, names) for one parameter list."""
    if blob is None:
        return 0, 0, []
    parts = split_top(blob)
    total = typed = 0
    names = []
    for p in parts:
        p = p.strip()
        if not p or p in ("*", "/", "..."):
            continue
        if language == "python":
            p = re.sub(r"^\*{1,2}", "", p).strip()
            if p in PY_SKIP:
                continue
        else:
            p = re.sub(r"^\.{3}", "", p).strip()
        # Strip a default value before looking for an annotation.
        eq = None
        d = 0
        for i, ch in enumerate(p):
            if ch in OPEN:
                d += 1
            elif ch in CLOSE:
                d -= 1
            elif ch == "=" and d == 0 and (i == 0 or p[i - 1] not in "=!<>"):
                eq = i
                break
        head = p[:eq].strip() if eq is not None else p
        head = head.rstrip("?")
        total += 1
        colon = None
        d = 0
        for i, ch in enumerate(head):
            if ch in OPEN:
                d += 1
            elif ch in CLOSE:
                d -= 1
            elif ch == ":" and d == 0:
                colon = i
                break
        if colon is not None and head[colon + 1 :].strip():
            typed += 1
            names.append(head[:colon].strip())
        else:
            names.append(head)
    return total, typed, names


def measure(rows, language):
    c = Counter()
    for sig, ret_col in rows:
        c["n"] += 1
        if not sig:
            c["no_signature_recorded"] += 1
            continue
        blob, ret = split_signature(sig, language)
        if blob is None:
            c["no_call_shape"] += 1
            continue
        total, typed, _ = parse_params(blob, language)
        if total == 0:
            c["zero_parameters"] += 1
            c["parameters_fully_structured"] += 1
        elif typed == total:
            c["parameters_fully_structured"] += 1
            c["has_parameters_all_typed"] += 1
        elif typed > 0:
            c["parameters_partially_typed"] += 1
        else:
            c["parameters_none_typed"] += 1
        if ret:
            c["return_type_in_signature"] += 1
            if ret.split("<")[0].strip() in UNINFORMATIVE_RETURNS:
                c["return_type_uninformative"] += 1
        if ret_col:
            c["return_type_column_populated"] += 1
        if ret and (total == 0 or typed == total):
            c["both_components_parseable"] += 1
    return c


def rate(c, key):
    return round(c[key] / c["n"], 4) if c["n"] else 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--language", required=True, choices=["python", "typescript"])
    ap.add_argument("--out", required=True)
    ap.add_argument(
        "--label", default="", help="free-text label recorded in the output"
    )
    ap.add_argument(
        "--route-prefix",
        default="",
        help="restrict route handlers to routes declared under this path",
    )
    ap.add_argument(
        "--verb-filter",
        action="store_true",
        help=(
            "keep only routes whose name begins with an HTTP verb, the "
            "deterministic precision filter established in finding 001"
        ),
    )
    args = ap.parse_args()

    con = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)

    scopes = {}
    prefix_clause = ""
    params = []
    if args.route_prefix:
        prefix_clause = " AND n.file_path LIKE ?"
        params.append(args.route_prefix + "%")
    if args.verb_filter:
        prefix_clause += (
            " AND ("
            + " OR ".join("n.name LIKE ?" for _ in range(7))
            + ")"
        )
        params.extend(
            f"{v} %" for v in
            ("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD")
        )

    # Scope 1: functions reached from a route node by an outgoing edge, i.e.
    # the endpoint handlers a promotion step would actually care about.
    handlers = con.execute(
        """
        SELECT DISTINCT t.id, t.signature, t.return_type
        FROM nodes n
        JOIN edges e ON e.source = n.id
        JOIN nodes t ON t.id = e.target
        WHERE n.kind = 'route'
          AND t.kind IN ('function', 'method', 'component')
        """
        + prefix_clause,
        params,
    ).fetchall()
    scopes["route_handlers"] = measure(
        [(r[1], r[2]) for r in handlers], args.language
    )

    # Scope 2: every callable in the index, as a corpus-wide ceiling.
    allfn = con.execute(
        "SELECT signature, return_type FROM nodes "
        "WHERE kind IN ('function','method')"
    ).fetchall()
    scopes["all_callables"] = measure(allfn, args.language)

    # A parseable return type is not a resolved one. `Promise<ArticleDto>`
    # yields a name, not a field-level schema; the schema only exists if that
    # name resolves to a declared type in the index. This is the analogue of
    # expanding a Pydantic model on the Python side.
    declared = {
        r[0]
        for r in con.execute(
            "SELECT DISTINCT name FROM nodes WHERE kind IN "
            "('interface','type_alias','class','enum')"
        )
    }
    BUILTIN = {
        "string", "number", "boolean", "void", "any", "unknown", "never",
        "null", "undefined", "object", "Date", "Array", "Record", "Map",
        "Set", "Buffer", "Partial", "Pick", "Omit", "str", "int", "float",
        "bool", "dict", "list", "None", "Any", "bytes",
    }
    res = Counter()
    for _, sig, _rt in handlers:
        if not sig:
            continue
        _blob, ret = split_signature(sig, args.language)
        if not ret:
            continue
        res["with_return"] += 1
        inner = ret
        for wrapper in ("Promise", "Awaitable", "Coroutine", "Optional"):
            m = re.match(rf"^{wrapper}\s*<(.+)>$", inner) or re.match(
                rf"^{wrapper}\s*\[(.+)\]$", inner
            )
            if m:
                inner = m.group(1).strip()
        heads = {
            h.split("<")[0].split("[")[0].strip().lstrip("(").rstrip(")")
            for h in re.split(r"\||&", inner)
        }
        heads = {h for h in heads if h}
        if heads <= BUILTIN:
            res["builtin_only"] += 1
        elif any(h in declared for h in heads):
            res["resolves_to_declared_type"] += 1
        else:
            res["names_an_unresolvable_type"] += 1
    out_resolution = dict(res)

    # Is the dedicated return_type column populated anywhere at all?
    col = con.execute(
        "SELECT COUNT(*) FROM nodes WHERE return_type IS NOT NULL "
        "AND TRIM(return_type) != ''"
    ).fetchone()[0]
    total_nodes = con.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
    con.close()

    out = {
        "label": args.label,
        "language": args.language,
        "return_type_column_populated_nodes": col,
        "total_nodes": total_nodes,
        "route_handler_return_resolution": out_resolution,
        "scopes": {},
    }
    for name, c in scopes.items():
        out["scopes"][name] = {
            "counts": dict(c),
            "rates": {
                "parameters_fully_structured": rate(
                    c, "parameters_fully_structured"
                ),
                "return_type_in_signature": rate(c, "return_type_in_signature"),
                "both_components_parseable": rate(c, "both_components_parseable"),
            },
        }

    json.dump(out, open(args.out, "w"), indent=2, sort_keys=True)

    print(f"[{args.label or args.language}]")
    print(
        f"  return_type column populated on {col}/{total_nodes} nodes"
    )
    print(f"  route-handler return resolution: {out_resolution}")
    for name, c in scopes.items():
        n = c["n"]
        print(f"  {name}: n={n}")
        print(
            f"    parameters fully structured  "
            f"{c['parameters_fully_structured']}/{n} = "
            f"{rate(c, 'parameters_fully_structured'):.4f}"
            f"   (of which {c['zero_parameters']} take no parameters)"
        )
        print(
            f"    return type in signature     "
            f"{c['return_type_in_signature']}/{n} = "
            f"{rate(c, 'return_type_in_signature'):.4f}"
            f"   (uninformative: {c['return_type_uninformative']})"
        )
        print(
            f"    both components parseable    "
            f"{c['both_components_parseable']}/{n} = "
            f"{rate(c, 'both_components_parseable'):.4f}"
        )
        print(
            f"    partially typed params {c['parameters_partially_typed']}, "
            f"wholly untyped {c['parameters_none_typed']}, "
            f"no signature recorded {c['no_signature_recorded']}, "
            f"no call shape {c['no_call_shape']}"
        )


if __name__ == "__main__":
    main()
