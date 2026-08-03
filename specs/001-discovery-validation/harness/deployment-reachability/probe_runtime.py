"""R2 and R3 — what a probe of the running deployment can actually establish.

For each configuration this starts a real uvicorn server on a loopback port and
talks to it over HTTP. Three things are measured:

R2-openapi   GET /openapi.json, the credential-free mechanism findings 004 and 007
             both proposed. Recorded as the set of (method, path) it publishes.

R3-path      A reachability precondition that must not invoke the operation. The
             mechanism is method mismatch: request the path with a verb the static
             catalogue does not declare for it. Starlette answers 404 when no route
             matches the path and 405 when a route matches but the method does not,
             so a routed path is distinguishable from an unrouted one *without any
             handler running*. Whether the 405 carries an `Allow` header — which
             would make the check exact rather than path-level — is recorded, since
             that decides whether R3 can verify a specific operation or only its
             path.

R3-exact     The same check using the operation's own method. Recorded for
             comparison and explicitly **not** proposed as a product mechanism,
             because it invokes the handler and DELETE means DELETE.

Path parameters are filled with a sentinel that no agent directory can match.
No model is called.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import socket
import sys
import threading
import time
import warnings

warnings.filterwarnings("ignore")

import httpx  # noqa: E402
import uvicorn  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_served_key as bsk  # noqa: E402

SENTINEL = "__f2a_probe__"
ALL_VERBS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]


def concretise(path):
    """Replace {param} and {param:converter} with a sentinel value."""
    return re.sub(r"\{[^}]+\}", SENTINEL, path)


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class Server(uvicorn.Server):
    def install_signal_handlers(self):
        return


def serve(app, port):
    cfg = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="critical",
                         lifespan="off")
    srv = Server(cfg)
    t = threading.Thread(target=srv.run, daemon=True)
    t.start()
    for _ in range(200):
        if srv.started:
            return srv, t
        time.sleep(0.05)
    raise RuntimeError("server did not start")


def probe_config(name, declared, candidates, static_methods_by_path):
    drop = bsk.BUILDER_KWARG_DROP.get(name, set())
    call_kwargs = {k: v for k, v in declared.items() if k not in drop}
    builder = bsk.BUILDERS.get(name, bsk.build_via_get_fast_api_app)
    app = builder(name, **call_kwargs)
    port = free_port()
    srv, _t = serve(app, port)
    base = f"http://127.0.0.1:{port}"
    out = {"ok": True, "port": port}
    try:
        with httpx.Client(base_url=base, timeout=20.0) as c:
            # --- R2-openapi ---
            try:
                r = c.get("/openapi.json")
                out["openapi_status"] = r.status_code
                if r.status_code == 200:
                    doc = r.json()
                    pairs = sorted(
                        {
                            (m.upper(), p)
                            for p, ops in (doc.get("paths") or {}).items()
                            for m in ops
                            if m.lower() in
                            ("get", "post", "put", "patch", "delete", "options", "head")
                        }
                    )
                    out["openapi_pairs"] = [list(x) for x in pairs]
                else:
                    out["openapi_pairs"] = []
            except Exception as exc:  # noqa: BLE001
                out["openapi_status"] = None
                out["openapi_error"] = f"{type(exc).__name__}: {exc}"
                out["openapi_pairs"] = []

            # --- R3: one mismatch probe per distinct path ---
            path_probe = {}
            for path in sorted({p for _m, p in candidates}):
                declared_methods = static_methods_by_path.get(path, set())
                probe_verb = next(
                    (v for v in ALL_VERBS if v not in declared_methods), "OPTIONS"
                )
                url = concretise(path)
                rec = {"probe_verb": probe_verb, "url": url}
                try:
                    r = c.request(probe_verb, url)
                    rec["status"] = r.status_code
                    rec["allow"] = r.headers.get("allow")
                    rec["routed"] = r.status_code != 404
                except Exception as exc:  # noqa: BLE001
                    rec["status"] = None
                    rec["error"] = f"{type(exc).__name__}: {exc}"
                    rec["routed"] = None
                path_probe[path] = rec
            out["path_probe"] = path_probe

            # --- R3-exact: the operation's own method. Invokes the handler. ---
            exact = {}
            for method, path in sorted(candidates):
                if method == "WS":
                    continue
                url = concretise(path)
                try:
                    r = c.request(method, url)
                    exact[f"{method} {path}"] = {
                        "status": r.status_code,
                        "routed": r.status_code != 404,
                    }
                except Exception as exc:  # noqa: BLE001
                    exact[f"{method} {path}"] = {
                        "status": None,
                        "error": f"{type(exc).__name__}: {exc}",
                        "routed": None,
                    }
            out["exact_probe"] = exact
    finally:
        srv.should_exit = True
        time.sleep(0.4)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--served-key", required=True)
    ap.add_argument("--static-set", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--only", default="")
    ap.add_argument(
        "--exact",
        action="store_true",
        help="also run R3-exact, which invokes handlers on a throwaway instance",
    )
    ap.add_argument(
        "--block",
        default="",
        help="make a top-level package unimportable, for configuration 8",
    )
    args = ap.parse_args()

    os.environ.setdefault("ADK_DISABLE_TELEMETRY", "1")
    if args.block:
        from config8_environment import _Blocker

        for mod in list(sys.modules):
            if mod == args.block or mod.startswith(args.block + "."):
                del sys.modules[mod]
        sys.meta_path.insert(0, _Blocker(args.block))
    key = json.load(open(args.served_key))
    st = json.load(open(args.static_set))
    candidates = {tuple(p) for p in st["static_set"]}
    for p in st["null_set"]["phantoms"] + st["null_set"]["foreign_apps"]:
        candidates.add(tuple(p))

    methods_by_path = {}
    for m, p in candidates:
        methods_by_path.setdefault(p, set()).add(m)

    wanted = set(args.only.split(",")) if args.only else set(key)
    result = {}
    for name, cfg in key.items():
        if name not in wanted or not cfg.get("ok"):
            continue
        try:
            result[name] = probe_config(
                name, cfg["declared_config"], candidates, methods_by_path
            )
            if not args.exact:
                result[name].pop("exact_probe", None)
            routed = sum(1 for v in result[name]["path_probe"].values() if v["routed"])
            with_allow = sum(
                1 for v in result[name]["path_probe"].values() if v.get("allow")
            )
            print(
                f"{name}: openapi={result[name]['openapi_status']} "
                f"pairs={len(result[name]['openapi_pairs'])} "
                f"paths_routed={routed}/{len(result[name]['path_probe'])} "
                f"allow_header={with_allow}",
                flush=True,
            )
        except Exception as exc:  # noqa: BLE001
            result[name] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
            print(f"{name}: FAILED {type(exc).__name__}: {exc}", flush=True)

    with open(args.out, "w") as fh:
        json.dump(result, fh, indent=2, sort_keys=True, default=str)


if __name__ == "__main__":
    main()
