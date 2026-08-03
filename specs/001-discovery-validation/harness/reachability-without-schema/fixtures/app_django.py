"""E15 fixture — Django. Second genuinely different router, and the structurally adversarial one.

Same seven served operations and same four route shapes as the other two fixtures, plus one
extra route that only Django can express.

**Why Django is the adversarial case.** Its URL resolver carries no method information at
all: `path("both", view)` maps a path to one callable, and method dispatch happens *inside*
application code. So a method mismatch is answered by whatever the view chooses to do.
`require_http_methods` answers 405, which makes the precondition mechanism work. A view that
dispatches internally answers whatever it likes — and **the handler runs first.**

`/anymethod` is that view: no method decorator, internal dispatch, and therefore reachable by
any verb including a fabricated one. Neither Starlette nor Flask can express it, because both
default an undecorated route to `GET` only. That asymmetry is a finding, not a fixture defect.
"""

import django
from django.conf import settings
from django.http import JsonResponse
from django.urls import path
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

ENABLE_ADMIN = False

settings.configure(
    DEBUG=False,
    ALLOWED_HOSTS=["*"],
    ROOT_URLCONF=__name__,
    SECRET_KEY="e15-probe-not-a-secret",
    MIDDLEWARE=[],
)
django.setup()


def _log(name, extra=""):
    print(f"HANDLER-INVOKED {name} {extra}".rstrip(), flush=True)


@require_http_methods(["GET"])
def item(request, name):
    _log("GET /items/{name}", name)
    return JsonResponse({"detail": "Item not found"}, status=404)


@csrf_exempt
@require_http_methods(["POST"])
def special(request):
    _log("POST /items/special")
    return JsonResponse({"ok": True})


@csrf_exempt
@require_http_methods(["GET", "POST"])
def both(request):
    _log(f"{request.method} /both")
    return JsonResponse({"ok": request.method})


@csrf_exempt
@require_http_methods(["GET", "DELETE"])
def multi(request):
    _log(f"{request.method} /multi")
    return JsonResponse({"ok": request.method})


@require_http_methods(["GET"])
def health(request):
    _log("GET /health")
    return JsonResponse({"status": "ok"})


# Django maps one path to one view, so it cannot express the other two fixtures' shape of two
# registrations on `/gated` with different methods. The gate is therefore expressed as two
# mutually exclusive definitions with *literal* method lists, which is the closest equivalent:
# a static reader sees both declarations and cannot evaluate the guard, so `POST /gated` lands
# in S; the runtime serves only one of them. That this required a different construct is itself
# recorded in the finding.
if ENABLE_ADMIN:

    @csrf_exempt
    @require_http_methods(["GET", "POST"])
    def gated(request):
        _log(f"{request.method} /gated")
        return JsonResponse({"ok": request.method})

else:

    @csrf_exempt
    @require_http_methods(["GET"])
    def gated(request):
        _log(f"{request.method} /gated")
        return JsonResponse({"ok": request.method})


@csrf_exempt
@require_http_methods(["POST"])
def admin_purge(request):
    _log("POST /admin/purge")
    return JsonResponse({"purged": True})


@csrf_exempt
def anymethod(request):
    """No method decorator. Dispatches internally, so any verb reaches this body."""
    _log(f"{request.method} /anymethod")
    if request.method not in ("GET", "POST"):
        return JsonResponse({"detail": "unsupported"}, status=400)
    return JsonResponse({"ok": request.method})


# The framework carries no method information for this view, so the key generator cannot
# read one off the router. It is declared here, on the view, and the finding discloses that
# this one route's ground truth is author-declared rather than framework-read.
anymethod.f2a_serves = ["GET", "POST"]

urlpatterns = [
    path("items/special", special),
    path("items/<str:name>", item),
    path("both", both),
    path("multi", multi),
    path("health", health),
    path("gated", gated),
    path("anymethod", anymethod),
]

if ENABLE_ADMIN:
    urlpatterns.append(path("admin/purge", admin_purge))

from django.core.handlers.wsgi import WSGIHandler  # noqa: E402

app = WSGIHandler()
