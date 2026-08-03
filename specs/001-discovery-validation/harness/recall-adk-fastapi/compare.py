"""Score codegraph's `route` nodes against the machine-generated answer key.

Reads:
  --key      JSON produced by build_key.py (per-configuration route tables)
  --db       a codegraph SQLite index of the same repository

Writes a JSON result with precision, recall, and the individually enumerated
false negatives and false positives. No model is called.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from collections import Counter

HTTP_VERBS = {"GET", "POST", "PUT", "PATCH", "DELETE"}
# Verbs FastAPI/Starlette can serve that the finding-001 filter excludes.
EXTENDED_VERBS = HTTP_VERBS | {"OPTIONS", "HEAD"}


def load_key(path):
    raw = json.load(open(path))
    union = {}
    per_config = {}
    handlers = {}
    for name, cfg in raw.items():
        if not cfg.get("ok"):
            per_config[name] = None
            continue
        entries = set()
        for row in cfg["routes"]:
            kind, method, p = row[0], row[1], row[2]
            handler = row[3] if len(row) > 3 else ""
            entries.add((method, p))
            union[(method, p)] = kind
            handlers.setdefault((method, p), handler)
        per_config[name] = entries
    return union, per_config, raw, handlers


def load_predictions(db_path, path_prefix=None):
    con = sqlite3.connect(db_path)
    q = "SELECT id, name, file_path, start_line FROM nodes WHERE kind='route'"
    args = []
    if path_prefix:
        q += " AND file_path LIKE ?"
        args.append(path_prefix + "%")
    rows = con.execute(q + " ORDER BY file_path, start_line", args).fetchall()
    con.close()
    preds = []
    for node_id, name, file_path, line in rows:
        m = re.match(r"^([A-Z]+)\s+(\S.*)$", name)
        if m:
            method, route_path = m.group(1), m.group(2)
        else:
            method, route_path = "", name
        preds.append(
            {
                "id": node_id,
                "raw_name": name,
                "method": method,
                "path": route_path,
                "file": file_path,
                "line": line,
            }
        )
    return preds


def score(preds, key_union, verb_filter=None, require_leading_slash=False):
    """Return precision/recall over (method, path) pairs."""
    if verb_filter is not None:
        preds = [p for p in preds if p["method"] in verb_filter]
    if require_leading_slash:
        preds = [p for p in preds if p["path"].startswith("/")]
    pred_pairs = {(p["method"], p["path"]) for p in preds}
    key_pairs = set(key_union)

    tp = pred_pairs & key_pairs
    fp = pred_pairs - key_pairs
    fn = key_pairs - pred_pairs

    precision = len(tp) / len(pred_pairs) if pred_pairs else 0.0
    recall = len(tp) / len(key_pairs) if key_pairs else 0.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall)
        else 0.0
    )
    return {
        "n_predicted_unique": len(pred_pairs),
        "n_predicted_nodes": len(preds),
        "n_key": len(key_pairs),
        "true_positives": len(tp),
        "false_positives": len(fp),
        "false_negatives": len(fn),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "fp_list": sorted(fp),
        "fn_list": sorted(fn),
        "tp_list": sorted(tp),
    }


def classify_fn(pair, kind):
    """Deterministic cause label for a missed route."""
    method, path = pair
    if method == "WS":
        return "websocket decorator not in extractor verb list"
    if method == "MOUNT":
        return "sub-application mount, not a decorator"
    if kind == "starlette" and path.startswith("/a2a/"):
        return "registered at runtime by a third-party library under a computed prefix"
    if kind == "starlette":
        return "added by the framework itself; no source declaration exists"
    return "unclassified - inspect by hand"


def score_handlers(db_path, key_handlers):
    """Score route -> handler linkage against the framework's own endpoint table.

    Ground truth is `route.endpoint.__name__` read off the instantiated app, so
    "the tool named the right handler" is decided by the framework, not by a
    model and not by inspection.
    """
    con = sqlite3.connect(db_path)
    rows = con.execute(
        """
        SELECT n.name, n.file_path, n.start_line,
               t.name, t.kind, t.signature, e.kind
        FROM nodes n
        LEFT JOIN edges e ON e.source = n.id
        LEFT JOIN nodes t ON t.id = e.target
        WHERE n.kind = 'route' AND n.file_path LIKE 'src/%'
        ORDER BY n.file_path, n.start_line
        """
    ).fetchall()
    con.close()

    per_route = {}
    for name, fpath, line, tname, tkind, tsig, ekind in rows:
        m = re.match(r"^([A-Z]+)\s+(\S.*)$", name)
        if not m:
            continue
        pair = (m.group(1), m.group(2))
        rec = per_route.setdefault(
            (pair, fpath, line), {"pair": pair, "targets": []}
        )
        if tname is not None:
            rec["targets"].append(
                {
                    "name": tname,
                    "kind": tkind,
                    "edge": ekind,
                    "typed": bool(tsig and tsig.strip() not in ("", "()")),
                }
            )

    n = len(per_route)
    callee_hist = Counter(len(r["targets"]) for r in per_route.values())
    correct = wrong = unscorable = 0
    mismatches = []
    typed = 0
    for (pair, fpath, line), rec in sorted(per_route.items()):
        truth = key_handlers.get(pair)
        if len(rec["targets"]) == 1 and rec["targets"][0]["typed"]:
            typed += 1
        if not truth:
            unscorable += 1
            continue
        names = [t["name"] for t in rec["targets"]]
        if len(names) == 1 and names[0] == truth:
            correct += 1
        else:
            wrong += 1
            mismatches.append(
                {
                    "route": f"{pair[0]} {pair[1]}",
                    "file": fpath,
                    "line": line,
                    "expected": truth,
                    "linked": names,
                }
            )

    scorable = correct + wrong
    return {
        "n_routes": n,
        "callees_per_route": {str(k): v for k, v in sorted(callee_hist.items())},
        "routes_reaching_exactly_one_typed_handler": typed,
        "scorable": scorable,
        "unscorable_no_ground_truth": unscorable,
        "handler_correct": correct,
        "handler_wrong": wrong,
        "handler_accuracy": round(correct / scorable, 4) if scorable else 0.0,
        "mismatches": mismatches,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--key", required=True)
    ap.add_argument("--db", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    key_union, per_config, raw, key_handlers = load_key(args.key)

    scopes = {
        "whole_repo": None,
        "src_only": "src/",
        "server_module_only": "src/google/adk/cli/",
    }

    results = {"key_size": len(key_union), "scopes": {}}
    for scope_name, prefix in scopes.items():
        preds = load_predictions(args.db, prefix)
        entry = {
            "n_route_nodes": len(preds),
            "by_file": dict(Counter(p["file"] for p in preds).most_common()),
            "no_filter": score(preds, key_union),
            "http_verb_filter": score(preds, key_union, HTTP_VERBS),
            "extended_verb_filter": score(preds, key_union, EXTENDED_VERBS),
            "leading_slash_filter": score(
                preds, key_union, require_leading_slash=True
            ),
            "verb_and_slash_filter": score(
                preds, key_union, HTTP_VERBS, require_leading_slash=True
            ),
        }
        entry["no_filter"]["fn_causes"] = {
            f"{m} {p}": classify_fn((m, p), key_union[(m, p)])
            for m, p in entry["no_filter"]["fn_list"]
        }
        results["scopes"][scope_name] = entry

    # Per-configuration recall, using the server-module scope with the HTTP
    # verb filter (the configuration a product would ship).
    preds = load_predictions(args.db, "src/google/adk/cli/")
    pred_pairs = {
        (p["method"], p["path"]) for p in preds if p["method"] in HTTP_VERBS
    }
    results["per_config_recall"] = {}
    for name, entries in per_config.items():
        if entries is None:
            results["per_config_recall"][name] = {"ok": False}
            continue
        hit = pred_pairs & entries
        over = pred_pairs - entries
        results["per_config_recall"][name] = {
            "ok": True,
            "key_size": len(entries),
            "predicted": len(pred_pairs),
            "recovered": len(hit),
            "recall": round(len(hit) / len(entries), 4) if entries else 0.0,
            "precision": (
                round(len(hit) / len(pred_pairs), 4) if pred_pairs else 0.0
            ),
            "missed": sorted(entries - pred_pairs),
            "declared_but_not_served_in_this_config": sorted(over),
        }

    results["handler_linkage"] = score_handlers(args.db, key_handlers)

    json.dump(results, open(args.out, "w"), indent=2, sort_keys=True)
    s = results["scopes"]
    print(f"answer key: {results['key_size']} unique (method, path) pairs")
    for name in scopes:
        e = s[name]
        print(f"\n-- scope: {name} ({e['n_route_nodes']} route nodes)")
        for fname in (
            "no_filter",
            "http_verb_filter",
            "leading_slash_filter",
            "verb_and_slash_filter",
        ):
            f = e[fname]
            print(
                f"   {fname:22} unique={f['n_predicted_unique']:4} "
                f"TP={f['true_positives']:3} FP={f['false_positives']:3} "
                f"FN={f['false_negatives']:3}  "
                f"P={f['precision']:.4f} R={f['recall']:.4f} F1={f['f1']:.4f}"
            )


if __name__ == "__main__":
    main()
