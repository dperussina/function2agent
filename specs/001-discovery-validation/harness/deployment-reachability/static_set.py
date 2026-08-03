"""The static candidate set S, and the null set N, read from the codegraph index.

S = the distinct (method, path) pairs codegraph recovers from `route` nodes under
`src/`. This is finding 004's true-positive set of 69 and is not recomputed here:
it is read from the same index finding 004 scored, so E14 measures reachability
handling and nothing else (FR-004).

N = the null set. Two parts, per PREREGISTRATION.md:
  - three synthetic phantoms that appear nowhere in the repository;
  - real route declarations codegraph recovers from elsewhere in the repository
    that belong to other applications (the demonstration servers under
    contributing/samples/). Real source, correctly parsed, wrong application.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3

PHANTOMS = [
    ["GET", "/f2a-phantom-alpha"],
    ["POST", "/apps/{app_name}/f2a-phantom-beta"],
    ["DELETE", "/f2a/phantom/gamma"],
]


def load_routes(db_path, prefix):
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    rows = con.execute(
        "SELECT name, file_path, start_line FROM nodes "
        "WHERE kind='route' AND file_path LIKE ? ORDER BY file_path, start_line",
        (prefix + "%",),
    ).fetchall()
    con.close()
    out = []
    for name, file_path, line in rows:
        m = re.match(r"^([A-Z]+)\s+(\S.*)$", name)
        method, path = (m.group(1), m.group(2)) if m else ("", name)
        out.append({"method": method, "path": path, "file": file_path, "line": line})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    src = load_routes(args.db, "src/")
    static_pairs = sorted({(r["method"], r["path"]) for r in src})

    # Foreign applications: real HTTP routes elsewhere in the repository that are
    # not part of the application under test.
    everything = load_routes(args.db, "")
    foreign = sorted(
        {
            (r["method"], r["path"])
            for r in everything
            if r["path"].startswith("/")
            and not r["file"].startswith("src/")
            and (r["method"], r["path"]) not in set(static_pairs)
        }
    )

    payload = {
        "static_set": [list(p) for p in static_pairs],
        "static_set_size": len(static_pairs),
        # Sorted on the whole tuple, not on the file alone: sorting on a partial key
        # leaves ties in set-iteration order and the artefact then fails FR-007's
        # byte-identity check even though the measurement is unaffected.
        "static_by_file": sorted(
            {(r["file"], r["method"], r["path"]) for r in src}
        ),
        "null_set": {
            "phantoms": PHANTOMS,
            "foreign_apps": [list(p) for p in foreign],
        },
        "null_set_size": len(PHANTOMS) + len(foreign),
    }
    with open(args.out, "w") as fh:
        json.dump(payload, fh, indent=2, default=str)
    print(f"static set: {len(static_pairs)}")
    print(f"null set: {len(PHANTOMS)} phantoms + {len(foreign)} foreign = "
          f"{payload['null_set_size']}")
    from collections import Counter

    for f, n in sorted(Counter(r["file"] for r in src).items()):
        print(f"  {n:3d}  {f}")


if __name__ == "__main__":
    main()
