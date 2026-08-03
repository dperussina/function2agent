#!/usr/bin/env python3
"""Serve one of E15's FastAPI schema configurations from the read-only vendored target.

Four configurations, all built on E14's `web` configuration so schema availability is the only
variable that moves (FR-004):

  `web`              E14 configuration 2, unchanged. The **positive control** — `PRESENT`.
  `web_no_schema`    `openapi_url=None`. `ABSENT`.
  `web_schema_401`   `/openapi.json` and `/docs` behind middleware answering 401. `FORBIDDEN`.
  `web_empty_schema` `/openapi.json` answers 200 with a valid, pathless schema. `EMPTY`.

**Why middleware and not a route dependency for the 401 case.** FastAPI adds the schema route in
`FastAPI.setup()` as a plain Starlette route, not an `APIRoute`, so a dependency cannot be
attached to it without replacing it — which would change the route table and break the
one-variable rule. Middleware runs before routing, leaves `app.routes` byte-identical to `web`,
and is also the more faithful production shape: an authenticating proxy in front of the schema.

**Why the empty case replaces rather than removes.** `EMPTY` must be a *successful* fetch, so the
route has to exist and answer 200. It is built by disabling the generated schema and adding one
route at the same path, which keeps the served path set identical to `web`.

Nothing under `examples/` is read except through the copy E14's harness made (FR-018).
"""

import argparse
import os
import sys

SCHEMA_PATHS = ("/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc")


def _strip_schema_routes(app):
    """Remove the four framework-generated schema and documentation routes."""
    app.openapi_url = None
    app.docs_url = None
    app.redoc_url = None
    app.router.routes = [
        r for r in app.router.routes
        if getattr(r, "path", None) not in SCHEMA_PATHS
    ]


def build(config, agents_dir):
    from google.adk.cli.fast_api import get_fast_api_app

    if config == "web":
        return get_fast_api_app(agents_dir=agents_dir, web=True)

    if config == "web_no_schema":
        # `openapi_url=None` is FastAPI's own switch, and **this target's factory does not
        # expose it** — `get_fast_api_app()` accepts no such argument and passes no
        # `**kwargs` through to the `FastAPI` constructor. That is a recorded finding, not a
        # harness limitation: an operator using the documented entry point cannot turn the
        # schema off through it. The state is therefore produced the way an operator actually
        # would, by removing the four schema routes from the constructed application, which is
        # exactly what `openapi_url=None` does inside FastAPI.
        app = get_fast_api_app(agents_dir=agents_dir, web=True)
        _strip_schema_routes(app)
        return app

    if config == "web_schema_401":
        app = get_fast_api_app(agents_dir=agents_dir, web=True)
        from starlette.responses import JSONResponse

        @app.middleware("http")
        async def gate_schema(request, call_next):
            if request.url.path in SCHEMA_PATHS:
                return JSONResponse(
                    {"detail": "Not authenticated"},
                    status_code=401,
                    headers={"WWW-Authenticate": "Bearer"},
                )
            return await call_next(request)

        return app

    if config == "web_empty_schema":
        app = get_fast_api_app(agents_dir=agents_dir, web=True)
        _strip_schema_routes(app)
        from starlette.responses import JSONResponse
        from starlette.routing import Route

        async def empty_schema(request):
            # Syntactically valid OpenAPI. Zero operations. Status 200.
            return JSONResponse({
                "openapi": "3.1.0",
                "info": {"title": "probe", "version": "0.0.0"},
                "paths": {},
            })

        app.router.routes.append(Route("/openapi.json", empty_schema, methods=["GET"]))
        return app

    raise SystemExit(f"unknown config {config}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--dump-routes", action="store_true",
                    help="write the machine-read route table and exit without serving")
    ap.add_argument("--out", help="destination for --dump-routes; stdout carries import "
                                  "warnings from the target, so a file is used instead")
    args = ap.parse_args()

    agents_dir = os.environ.get("F2A_AGENTS_DIR")
    if not agents_dir:
        raise SystemExit("F2A_AGENTS_DIR must point at the fixture agents directory")

    app = build(args.config, agents_dir)

    if args.dump_routes:
        import json

        from fastapi.routing import APIRoute
        from starlette.routing import Mount, Route, WebSocketRoute

        rows = []
        for r in app.routes:
            if isinstance(r, (APIRoute, Route)):
                for m in sorted(r.methods or []):
                    if m == "HEAD":
                        continue
                    rows.append(["api" if isinstance(r, APIRoute) else "starlette", m, r.path])
            elif isinstance(r, WebSocketRoute):
                rows.append(["websocket", "WS", r.path])
            elif isinstance(r, Mount):
                rows.append(["mount", "MOUNT", r.path])
        payload = {"config": args.config, "routes": sorted(rows),
                   "route_count": len(rows)}
        if args.out:
            existing = {}
            if os.path.exists(args.out):
                existing = json.load(open(args.out))
            existing[args.config] = payload
            json.dump(existing, open(args.out, "w"), indent=2, sort_keys=True)
            print(f"{args.config}: {len(rows)} routes -> {args.out}")
        else:
            print(json.dumps(payload, indent=2))
        return

    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
