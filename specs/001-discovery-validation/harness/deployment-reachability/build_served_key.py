"""Ground truth for E14: what each deployment configuration actually serves.

Machine-generated (FR-008). For every configuration this instantiates the ADK
FastAPI application and reads its own dispatch table off `app.routes`, then also
records what `app.openapi()` publishes for the same app. The two are recorded
separately because the whole point of the OpenAPI secondary measurement is that
they may differ.

Configurations 1-5 are finding 004's, byte-for-byte, so E14's numbers are
comparable to that finding's. Configurations 6 and 7 are added by E14 and each
exists to falsify a specific claim; see PREREGISTRATION.md.

Nothing under examples/ is touched. No model is called.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import warnings

warnings.filterwarnings("ignore")

from fastapi.routing import APIRoute  # noqa: E402
from starlette.routing import Mount, Route, WebSocketRoute  # noqa: E402


def _endpoint_name(route):
    """The handler function the framework will actually invoke."""
    ep = getattr(route, "endpoint", None)
    if ep is None:
        return ""
    seen = 0
    while hasattr(ep, "__wrapped__") and seen < 10:
        ep = ep.__wrapped__
        seen += 1
    return getattr(ep, "__name__", "")


def enumerate_routes(app):
    """(kind, method, path, handler) for everything the app will dispatch.

    Identical rules to finding 004's build_key.py: HEAD entries Starlette adds
    beside every GET are dropped because they are not separately declared
    operations; everything else the framework holds is kept.
    """
    out = []
    for r in app.routes:
        if isinstance(r, (APIRoute, Route)):
            for m in sorted(r.methods or []):
                if m == "HEAD":
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


def enumerate_openapi(app):
    """(method, path) pairs the app's own OpenAPI document publishes."""
    try:
        schema = app.openapi()
    except Exception as exc:  # noqa: BLE001
        return None, f"{type(exc).__name__}: {exc}"
    out = []
    for path, ops in (schema.get("paths") or {}).items():
        for method in ops:
            if method.lower() in (
                "get",
                "post",
                "put",
                "patch",
                "delete",
                "options",
                "head",
                "trace",
            ):
                out.append((method.upper(), path))
    return sorted(set(out)), None


FIXTURE_AGENTS = os.environ.get("F2A_AGENTS_DIR", "")


def _agents_dir(config_name):
    return FIXTURE_AGENTS or tempfile.mkdtemp(prefix=f"agents-{config_name}-")


def build_via_get_fast_api_app(config_name, **kwargs):
    from google.adk.cli.fast_api import get_fast_api_app

    return get_fast_api_app(agents_dir=_agents_dir(config_name), **kwargs)


def build_devserver_direct(config_name, **kwargs):
    """Configuration 7: the documented embedding path, DevServer constructed directly.

    This decorrelates `web_assets_dir` from the `web` flag. It is a different
    entry point from get_fast_api_app and PREREGISTRATION.md records that.
    """
    from google.adk.artifacts.in_memory_artifact_service import InMemoryArtifactService
    from google.adk.auth.credential_service.in_memory_credential_service import (
        InMemoryCredentialService,
    )
    from google.adk.cli.dev_server import DevServer
    from google.adk.cli.utils.agent_loader import AgentLoader
    from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
    from google.adk.sessions.in_memory_session_service import InMemorySessionService

    agents_dir = _agents_dir(config_name)
    server = DevServer(
        agent_loader=AgentLoader(agents_dir=agents_dir),
        session_service=InMemorySessionService(),
        artifact_service=InMemoryArtifactService(),
        memory_service=InMemoryMemoryService(),
        credential_service=InMemoryCredentialService(),
        eval_sets_manager=None,
        eval_set_results_manager=None,
        agents_dir=agents_dir,
        **kwargs,
    )
    return server.get_fast_api_app(web_assets_dir=None)


# The declared configuration each arm is allowed to read. Keys are the public
# get_fast_api_app parameter names; values are what a deployment would set.
CONFIGS = {
    "api_server": dict(web=False),
    "web": dict(web=True),
    "web_a2a": dict(web=True, a2a=True),
    "web_triggers": dict(web=True, trigger_sources=["pubsub", "eventarc"]),
    "enterprise": dict(web=False, gemini_enterprise_app_name="probe_app"),
    # Added by E14 — element-wise membership discriminator.
    "api_server_pubsub": dict(web=False, trigger_sources=["pubsub"]),
    # Added by E14 — decorrelates web_assets_dir from web. Different entry point.
    "devserver_no_assets": dict(web=True, web_assets_dir=None),
}

BUILDERS = {name: build_via_get_fast_api_app for name in CONFIGS}
BUILDERS["devserver_no_assets"] = build_devserver_direct

# Kwargs that are configuration facts for the arms but are not accepted by the
# builder for that configuration.
BUILDER_KWARG_DROP = {"devserver_no_assets": {"web", "web_assets_dir"}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--only", default="", help="comma-separated config subset")
    args = ap.parse_args()

    os.environ.setdefault("ADK_DISABLE_TELEMETRY", "1")
    wanted = set(args.only.split(",")) if args.only else set(CONFIGS)

    result = {}
    for name, kwargs in CONFIGS.items():
        if name not in wanted:
            continue
        drop = BUILDER_KWARG_DROP.get(name, set())
        call_kwargs = {k: v for k, v in kwargs.items() if k not in drop}
        try:
            app = BUILDERS[name](name, **call_kwargs)
            routes = enumerate_routes(app)
            openapi, openapi_err = enumerate_openapi(app)
            result[name] = {
                "ok": True,
                "entry_point": (
                    "DevServer.get_fast_api_app"
                    if name == "devserver_no_assets"
                    else "fast_api.get_fast_api_app"
                ),
                # The configuration as an arm may read it, not as the builder was called.
                "declared_config": {k: v for k, v in kwargs.items()},
                "routes": [list(t) for t in routes],
                "openapi": [list(t) for t in openapi] if openapi else [],
                "openapi_error": openapi_err,
            }
            print(
                f"{name}: {len(routes)} served, "
                f"{len(openapi or [])} in openapi",
                file=sys.stderr,
            )
        except Exception as exc:  # noqa: BLE001
            result[name] = {
                "ok": False,
                "declared_config": {k: v for k, v in kwargs.items()},
                "error": f"{type(exc).__name__}: {exc}",
            }
            print(f"{name}: FAILED {type(exc).__name__}: {exc}", file=sys.stderr)

    with open(args.out, "w") as fh:
        json.dump(result, fh, indent=2, sort_keys=True, default=str)
    print(f"wrote {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
