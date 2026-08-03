"""E15 fixture — plain Starlette. The CONTROL target.

Its only job is to isolate whether finding 010's two instrumentation defects belong to
Starlette's router or to FastAPI. If they reproduce here, they are the router's.

Every handler prints a line on execution so that handler invocation during probing is
**counted from the server's own log** rather than inferred from a status code.

Four route shapes are deliberate:

  A. `/items/special` is a literal path with a parameterised sibling `/items/{name}`.
     This is finding 010 defect B's shape.
  B. `/both` carries two separate registrations, one per method. Defect A's shape.
  C. `/gated` serves GET unconditionally and POST only when ENABLE_ADMIN is true.
     **This is the shape adk-python does not contain**, and it is the one that decides
     whether a path-level probe can clear an operation-granularity precision gate: the
     path is routed, so a path-level probe predicts POST served, and POST is not served.
  D. `/admin/purge` is gated as a whole path, so a path-level probe excludes it correctly.

ENABLE_ADMIN is false. Shapes C and D therefore put two declared-but-unserved operations
in the static set, which is what allows precision to be less than 1.0. A fixture where
every declared route is served cannot falsify anything.
"""

from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

ENABLE_ADMIN = False


def _log(name, extra=""):
    print(f"HANDLER-INVOKED {name} {extra}".rstrip(), flush=True)


async def item(request):
    _log("GET /items/{name}", request.path_params["name"])
    return JSONResponse({"detail": "Item not found"}, status_code=404)


async def special(request):
    _log("POST /items/special")
    return JSONResponse({"ok": True})


async def both_get(request):
    _log("GET /both")
    return JSONResponse({"ok": "get"})


async def both_post(request):
    _log("POST /both")
    return JSONResponse({"ok": "post"})


async def multi(request):
    _log(f"{request.method} /multi")
    return JSONResponse({"ok": request.method})


async def health(request):
    _log("GET /health")
    return JSONResponse({"status": "ok"})


async def gated_get(request):
    _log("GET /gated")
    return JSONResponse({"ok": "get"})


async def gated_post(request):
    _log("POST /gated")
    return JSONResponse({"ok": "post"})


async def admin_purge(request):
    _log("POST /admin/purge")
    return JSONResponse({"purged": True})


routes = [
    Route("/items/special", special, methods=["POST"]),
    Route("/items/{name}", item, methods=["GET"]),
    Route("/both", both_get, methods=["GET"]),
    Route("/both", both_post, methods=["POST"]),
    Route("/multi", multi, methods=["GET", "DELETE"]),
    Route("/health", health, methods=["GET"]),
    Route("/gated", gated_get, methods=["GET"]),
]

if ENABLE_ADMIN:
    routes.append(Route("/gated", gated_post, methods=["POST"]))
    routes.append(Route("/admin/purge", admin_purge, methods=["POST"]))

app = Starlette(routes=routes)
