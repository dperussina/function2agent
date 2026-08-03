"""Build an authoritative (method, path) answer key from a live FastAPI app.

The key is machine-generated: it is read off the instantiated application's own
route table (starlette/fastapi `app.routes`), not transcribed by hand. Several
configurations are enumerated because the ADK API server registers different
route sets depending on its constructor flags, and static analysis is blind to
those flags.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import warnings

warnings.filterwarnings("ignore")

from fastapi.routing import APIRoute  # noqa: E402
from starlette.routing import Mount, Route, WebSocketRoute  # noqa: E402


def _endpoint_name(route):
    """The handler function the framework will actually invoke.

    Unwraps functools.wraps chains so a decorated handler reports the name of
    the function as written in source rather than the wrapper's.
    """
    ep = getattr(route, "endpoint", None)
    if ep is None:
        return ""
    seen = 0
    while hasattr(ep, "__wrapped__") and seen < 10:
        ep = ep.__wrapped__
        seen += 1
    return getattr(ep, "__name__", "")


def enumerate_routes(app):
    """Return (kind, method, path, handler) tuples for everything the app serves."""
    out = []
    for r in app.routes:
        if isinstance(r, (APIRoute, Route)):
            for m in sorted(r.methods or []):
                if m == "HEAD":
                    # Starlette auto-adds HEAD alongside every GET; it is not a
                    # separately declared operation.
                    continue
                kind = "api" if isinstance(r, APIRoute) else "starlette"
                out.append((kind, m, r.path, _endpoint_name(r)))
        elif isinstance(r, WebSocketRoute):
            out.append(("websocket", "WS", r.path, _endpoint_name(r)))
        elif isinstance(r, Mount):
            out.append(("mount", "MOUNT", r.path, ""))
        else:
            out.append((type(r).__name__, "?", getattr(r, "path", "?"), ""))
    return out


FIXTURE_AGENTS = os.environ.get("F2A_AGENTS_DIR", "")


def build(config_name, **kwargs):
    agents_dir = FIXTURE_AGENTS or tempfile.mkdtemp(prefix=f"agents-{config_name}-")
    from google.adk.cli.fast_api import get_fast_api_app

    app = get_fast_api_app(agents_dir=agents_dir, **kwargs)
    return enumerate_routes(app)


CONFIGS = {
    # `adk api_server` — headless API, no dev UI, no A2A.
    "api_server": dict(web=False),
    # `adk web` — the dev UI server; DevServer subclasses ApiServer.
    "web": dict(web=True),
    # A2A protocol surface enabled.
    "web_a2a": dict(web=True, a2a=True),
    # Pub/Sub + Eventarc trigger routes.
    "web_triggers": dict(web=True, trigger_sources=["pubsub", "eventarc"]),
    # Gemini Enterprise / Agent Engine surface.
    "enterprise": dict(web=False, gemini_enterprise_app_name="probe_app"),
}


def main():
    os.environ.setdefault("ADK_DISABLE_TELEMETRY", "1")
    result = {}
    for name, kwargs in CONFIGS.items():
        try:
            routes = build(name, **kwargs)
            result[name] = {
                "ok": True,
                "kwargs": {k: str(v) for k, v in kwargs.items()},
                "routes": [list(t) for t in routes],
            }
            print(f"{name}: {len(routes)} entries", file=sys.stderr)
        except Exception as exc:  # noqa: BLE001
            result[name] = {
                "ok": False,
                "kwargs": {k: str(v) for k, v in kwargs.items()},
                "error": f"{type(exc).__name__}: {exc}",
            }
            print(f"{name}: FAILED {type(exc).__name__}: {exc}", file=sys.stderr)

    json.dump(result, sys.stdout, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
