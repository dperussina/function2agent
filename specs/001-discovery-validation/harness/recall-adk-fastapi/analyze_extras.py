"""Supplementary measurements against the Python AST as ground truth.

Two questions the route comparison does not answer:

  1. Symbol-level recall — of the functions Python's own parser finds in the
     repository, how many does the index contain?
  2. Docstring fidelity — of the functions that genuinely carry a PEP 257
     docstring, how many does the index record one for, and is the recorded
     text actually the docstring?

Both use `ast` from the standard library as the authority. No model is called.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import sqlite3

SKIP_DIRS = {".codegraph", ".git", "__pycache__", "node_modules", ".venv"}


def walk_ast(root):
    functions = {}
    parse_failures = []
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in files:
            if not f.endswith(".py"):
                continue
            p = os.path.join(dirpath, f)
            rel = os.path.relpath(p, root)
            try:
                src = open(p, encoding="utf-8", errors="replace").read()
                tree = ast.parse(src)
            except SyntaxError as exc:
                parse_failures.append({"file": rel, "error": str(exc)})
                continue
            for n in ast.walk(tree):
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    functions[(rel, n.lineno, n.name)] = ast.get_docstring(n)
    return functions, parse_failures


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--db", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    truth, parse_failures = walk_ast(args.repo)

    con = sqlite3.connect(args.db)
    rows = con.execute(
        "SELECT file_path, start_line, name, docstring FROM nodes "
        "WHERE kind IN ('function','method') AND language='python'"
    ).fetchall()
    con.close()

    idx = {(f, l, n): d for f, l, n, d in rows}

    tp = set(truth) & set(idx)
    fn = set(truth) - set(idx)
    fp = set(idx) - set(truth)

    with_doc = {k for k, v in truth.items() if v}
    scorable = with_doc & set(idx)
    recorded = {k for k in scorable if idx[k] and idx[k].strip()}
    # Of those recorded, does the recorded text actually begin the real docstring?
    faithful = {
        k
        for k in recorded
        if truth[k] and idx[k].strip()[:40] in " ".join(truth[k].split())
    }

    result = {
        "symbol_level": {
            "ast_functions": len(truth),
            "index_function_nodes": len(idx),
            "true_positives": len(tp),
            "false_negatives": len(fn),
            "false_positives": len(fp),
            "recall": round(len(tp) / len(truth), 4) if truth else 0.0,
            "precision": round(len(tp) / len(idx), 4) if idx else 0.0,
            "missed_files": sorted({k[0] for k in fn}),
            "missed_symbols": sorted(f"{f}:{l} {n}" for f, l, n in fn),
        },
        "docstring_fidelity": {
            "ast_functions_with_docstring": len(with_doc),
            "of_those_present_in_index": len(scorable),
            "index_recorded_some_docstring": len(recorded),
            "coverage": (
                round(len(recorded) / len(scorable), 4) if scorable else 0.0
            ),
            "recorded_text_matches_real_docstring": len(faithful),
            "fidelity_of_recorded": (
                round(len(faithful) / len(recorded), 4) if recorded else 0.0
            ),
            "examples_of_recorded_text": [
                {"symbol": f"{f}:{l} {n}", "recorded": (idx[(f, l, n)] or "")[:90]}
                for (f, l, n) in sorted(recorded)[:5]
            ],
        },
        "ast_parse_failures": parse_failures,
    }

    json.dump(result, open(args.out, "w"), indent=2, sort_keys=True)
    s = result["symbol_level"]
    d = result["docstring_fidelity"]
    print(
        f"symbols: {s['true_positives']}/{s['ast_functions']} recovered "
        f"(recall {s['recall']:.4f}, precision {s['precision']:.4f}); "
        f"{s['false_negatives']} missed in {len(s['missed_files'])} file(s)"
    )
    print(
        f"docstrings: {d['index_recorded_some_docstring']}/"
        f"{d['of_those_present_in_index']} functions with a real docstring got "
        f"one recorded ({d['coverage']:.4f}); of those recorded, "
        f"{d['recorded_text_matches_real_docstring']} match the real docstring "
        f"({d['fidelity_of_recorded']:.4f})"
    )


if __name__ == "__main__":
    main()
