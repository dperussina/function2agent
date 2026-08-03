"""Verify the two defects the probe measurement exposed, directly.

Defect A — Starlette's 405 `Allow` header names the methods of the first route whose
           path matched, not the union over every route sharing that path. A
           reachability check that trusts it marks real operations unreachable.

Defect B — a 404 does not distinguish "no route matches this path" from "a route
           matched and its handler answered 404". A sibling parameterised route can
           absorb the probe, which means (i) the reachability verdict is wrong and
           (ii) the probe invoked a handler it was designed not to invoke.

Both are checked against the running application, not inferred. No model is called.
"""

from __future__ import annotations

import json
import os
import sys
import warnings

warnings.filterwarnings("ignore")

import httpx  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_served_key as bsk  # noqa: E402
from probe_runtime import free_port, serve  # noqa: E402

SENTINEL = "__f2a_probe__"


def main():
    os.environ.setdefault("ADK_DISABLE_TELEMETRY", "1")
    app = bsk.build_via_get_fast_api_app("verify", web=True)
    port = free_port()
    srv, _ = serve(app, port)
    base = f"http://127.0.0.1:{port}"
    out = {}
    try:
        with httpx.Client(base_url=base, timeout=20.0) as c:
            # ---- Defect A ----
            # This path serves GET, POST, PATCH and DELETE. Probe with PUT.
            p = f"/apps/{SENTINEL}/users/u1/sessions/s1"
            r = c.request("PUT", p)
            out["defect_A"] = {
                "path": "/apps/{app_name}/users/{user_id}/sessions/{session_id}",
                "probe_verb": "PUT",
                "status": r.status_code,
                "allow_header": r.headers.get("allow"),
                "methods_the_route_table_serves": sorted(
                    {
                        m
                        for r2 in app.routes
                        for m in (getattr(r2, "methods", None) or [])
                        if getattr(r2, "path", None)
                        == "/apps/{app_name}/users/{user_id}/sessions/{session_id}"
                        and m != "HEAD"
                    }
                ),
            }

            # ---- Defect B ----
            # POST /dev/apps/{app_name}/tests/rebuild is served. Probing it with GET
            # is absorbed by GET /dev/apps/{app_name}/tests/{test_name}.
            r = c.get(f"/dev/apps/{SENTINEL}/tests/rebuild")
            body = r.text[:300]
            # A path that matches no route at all, for comparison.
            r2 = c.get("/f2a-definitely-not-a-route")
            out["defect_B"] = {
                "probed": "GET /dev/apps/{app_name}/tests/rebuild",
                "status": r.status_code,
                "body": body,
                "unrouted_control": {
                    "probed": "GET /f2a-definitely-not-a-route",
                    "status": r2.status_code,
                    "body": r2.text[:300],
                },
                "sibling_route_that_absorbs_it": (
                    "GET /dev/apps/{app_name}/tests/{test_name}"
                ),
                "post_is_actually_served": any(
                    getattr(rt, "path", None) == "/dev/apps/{app_name}/tests/rebuild"
                    and "POST" in (getattr(rt, "methods", None) or [])
                    for rt in app.routes
                ),
            }
            out["defect_B"]["two_404s_are_distinguishable_by_body"] = (
                body != r2.text[:300]
            )
    finally:
        srv.should_exit = True

    json.dump(out, sys.stdout, indent=2, default=str)
    print()


if __name__ == "__main__":
    main()
