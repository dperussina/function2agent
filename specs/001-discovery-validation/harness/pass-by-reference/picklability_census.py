"""SPIKE - E17 pass-by-reference. Delete after 2026-11-30. Do not import from product code.

Arm B', the free one: which result shapes cannot cross a process boundary at all.

The brief that commissioned E17 named this as an informative finding in its own
right rather than as noise, and it turns out to be the *only* part of arm B worth
having, for the reason set out in 11 of the preregistration: NOOA's sandbox
reconstitutes a brokered result as a live object in the worker namespace, so the
boundary costs object identity, not transcript bytes. What it does destroy is
addressability for anything pickle refuses — and that is measurable here, offline,
with the standard library, for nothing.

**Why this is a faithful reproduction and not an approximation.** NOOA's gate is,
verbatim from `nooa/runtime/sandbox/serialization.py`:

    def is_picklable(value: Any) -> bool:
        try:
            pickle.dumps(value)
            return True
        except Exception:
            return False

That is the whole predicate. :func:`is_picklable` below is the same three lines, so
the census does not depend on importing NOOA — which matters, because importing
NOOA pulls `litellm`, which owner decision OD-16 removed from this environment.

Usage:  python3 picklability_census.py [--json]
"""

from __future__ import annotations

import argparse
import collections
import ctypes
import datetime
import decimal
import enum
import functools
import io
import itertools
import json
import pathlib
import pickle
import re
import socket
import sqlite3
import subprocess
import sys
import threading
import weakref
from dataclasses import dataclass


def is_picklable(value) -> bool:
    """NOOA's gate, reproduced verbatim. See the module docstring."""
    try:
        pickle.dumps(value)
        return True
    except Exception:
        return False


# --- module-level shapes, so the "defined at module level" cases really are ---

@dataclass
class PlainRecord:
    name: str
    count: int


class Colour(enum.Enum):
    RED = 1
    BLUE = 2


Point = collections.namedtuple("Point", "x y")


def module_level_function(x):
    return x + 1


class Ordinary:
    def __init__(self, n):
        self.n = n


#: Category -> why an agent would ever return something of this shape.
CATEGORIES = {
    "plain data": "the shapes a tool is supposed to return",
    "live resource handle": "an open thing: file, socket, connection, lock",
    "lazy sequence": "an iterator or view that has not been materialised",
    "callable": "a function, closure or bound partial",
    "locally defined": "a class or instance whose type is not importable by name",
    "runtime object": "interpreter or framework machinery",
}


def build_specimens() -> list[tuple[str, str, object, object]]:
    """(name, category, value, keepalive). Keepalive holds resources open."""
    out: list[tuple[str, str, object, object]] = []

    def add(name, cat, value, keep=None):
        out.append((name, cat, value, keep))

    # plain data
    add("int", "plain data", 7)
    add("str", "plain data", "hello")
    add("bytes", "plain data", b"\x00\x01")
    add("list[dict]", "plain data", [{"a": 1}, {"b": 2}])
    add("nested dict", "plain data", {"rows": [[1, 2], [3, 4]], "ok": True})
    add("set", "plain data", {1, 2, 3})
    add("frozenset", "plain data", frozenset({1, 2}))
    add("tuple", "plain data", (1, "a", None))
    add("datetime", "plain data", datetime.datetime(2026, 8, 4, 12, 0, 0))
    add("Decimal", "plain data", decimal.Decimal("1.25"))
    add("pathlib.Path", "plain data", pathlib.Path("/tmp/x"))
    add("deque", "plain data", collections.deque([1, 2, 3]))
    add("namedtuple (module level)", "plain data", Point(1, 2))
    add("dataclass (module level)", "plain data", PlainRecord("a", 1))
    add("enum member", "plain data", Colour.RED)
    add("exception instance", "plain data", ValueError("boom"))
    add("class instance (module level)", "plain data", Ordinary(3))

    # live resource handles
    fh = open(__file__, "rb")
    add("open file object", "live resource handle", fh, fh)
    sock = socket.socket()
    add("socket", "live resource handle", sock, sock)
    conn = sqlite3.connect(":memory:")
    add("sqlite3 connection", "live resource handle", conn, conn)
    add("sqlite3 cursor", "live resource handle", conn.cursor(), conn)
    add("threading.Lock", "live resource handle", threading.Lock())
    add("threading.Thread", "live resource handle", threading.Thread(target=lambda: None))
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    add("subprocess.Popen", "live resource handle", proc, proc)
    add("io.BytesIO", "live resource handle", io.BytesIO(b"abc"))
    add("io.StringIO", "live resource handle", io.StringIO("abc"))

    # lazy sequences
    add("generator", "lazy sequence", (i for i in range(3)))
    add("map object", "lazy sequence", map(str, [1, 2, 3]))
    add("filter object", "lazy sequence", filter(None, [1, 2]))
    add("zip object", "lazy sequence", zip([1], [2]))
    add("itertools.chain", "lazy sequence", itertools.chain([1], [2]))
    add("dict_keys view", "lazy sequence", {"a": 1}.keys())
    add("memoryview", "lazy sequence", memoryview(b"abc"))
    # `range` looks lazy and is not: it is a value object with a __reduce__, and it
    # crosses. Filed under plain data so the "lazy sequence" row means what it says.
    add("range", "plain data", range(10))

    # callables
    add("lambda", "callable", lambda x: x)
    add("module-level function", "callable", module_level_function)
    add("closure", "callable", (lambda n: (lambda x: x + n))(3))
    add("partial of module function", "callable",
        functools.partial(module_level_function, 1))
    add("partial of lambda", "callable", functools.partial(lambda x: x, 1))
    add("bound method (module class)", "callable", Ordinary(1).__init__)

    # locally defined
    class LocalOnly:
        def __init__(self):
            self.v = 1

    add("locally defined class", "locally defined", LocalOnly)
    add("locally defined instance", "locally defined", LocalOnly())

    # runtime objects
    add("module object", "runtime object", json)
    add("re.Match", "runtime object", re.match("a", "a"))
    add("compiled regex", "runtime object", re.compile("a"))
    # A real traceback, from a real raise. The first draft wrote
    # `sys.exc_info()[2]` outside any except block, which is None — so the census
    # recorded "traceback crosses: yes" while pickling nothing at all. A specimen
    # that is silently None is a row of the census that is a lie.
    try:
        raise ValueError("specimen")
    except ValueError:
        add("traceback", "runtime object", sys.exc_info()[2])
    add("weakref", "runtime object", weakref.ref(Ordinary(1)))
    add("ctypes pointer", "runtime object", ctypes.pointer(ctypes.c_int(3)))
    add("ctypes CDLL", "runtime object", ctypes.CDLL(None))
    return out


def census() -> dict:
    specimens = build_specimens()
    rows = []
    for name, cat, value, _keep in specimens:
        rows.append({"shape": name, "category": cat, "crosses": is_picklable(value)})

    by_cat: dict[str, dict] = {}
    for r in rows:
        c = by_cat.setdefault(r["category"], {"n": 0, "crosses": 0, "blocked": []})
        c["n"] += 1
        if r["crosses"]:
            c["crosses"] += 1
        else:
            c["blocked"].append(r["shape"])

    return {
        "dry_run": True,
        "model_calls": 0,
        "spend_usd": 0.0,
        "python": sys.version.split()[0],
        "pickle_protocol": pickle.DEFAULT_PROTOCOL,
        "predicate": "pickle.dumps in try/except — NOOA's is_picklable, reproduced verbatim",
        "n_shapes": len(rows),
        "n_cross": sum(1 for r in rows if r["crosses"]),
        "n_blocked": sum(1 for r in rows if not r["crosses"]),
        "rows": rows,
        "by_category": by_cat,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    c = census()
    if args.json:
        print(json.dumps(c, indent=2))
        return 0

    print("E17 arm B' — which result shapes cross a fork boundary (dry run, $0.00)")
    print("=" * 74)
    print(f"python {c['python']}, pickle protocol {c['pickle_protocol']}")
    print(f"predicate: {c['predicate']}")
    print()
    print(f"{'shape':<32} {'category':<22} crosses")
    for r in c["rows"]:
        print(f"{r['shape']:<32} {r['category']:<22} {'yes' if r['crosses'] else 'NO'}")
    print()
    print(f"{'category':<22} {'crosses':>9} {'of':>4}   blocked")
    for cat, v in c["by_category"].items():
        print(f"{cat:<22} {v['crosses']:>9} {v['n']:>4}   {', '.join(v['blocked']) or '-'}")
    print()
    print(f"{c['n_cross']} of {c['n_shapes']} shapes cross; "
          f"{c['n_blocked']} of {c['n_shapes']} do not.")
    print("model calls: 0    spend: $0.00")
    return 0


if __name__ == "__main__":
    sys.exit(main())
