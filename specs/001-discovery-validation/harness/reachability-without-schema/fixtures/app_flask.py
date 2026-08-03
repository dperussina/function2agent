"""E15 fixture — Flask / Werkzeug. First genuinely different router.

Same seven served operations and same four route shapes as the Starlette fixture, so the
frameworks are comparable (FR-004). See `app_starlette.py` for what each shape tests.

Werkzeug matches paths through a compiled `Map` and raises `MethodNotAllowed` carrying
`valid_methods`, which is a different mechanism from Starlette's first-partial-match. That
difference is the point of this target.
"""

from flask import Flask, jsonify

ENABLE_ADMIN = False

app = Flask(__name__)


def _log(name, extra=""):
    print(f"HANDLER-INVOKED {name} {extra}".rstrip(), flush=True)


@app.get("/items/<name>")
def item(name):
    _log("GET /items/{name}", name)
    return jsonify({"detail": "Item not found"}), 404


@app.post("/items/special")
def special():
    _log("POST /items/special")
    return jsonify({"ok": True})


@app.get("/both")
def both_get():
    _log("GET /both")
    return jsonify({"ok": "get"})


@app.post("/both")
def both_post():
    _log("POST /both")
    return jsonify({"ok": "post"})


@app.route("/multi", methods=["GET", "DELETE"])
def multi():
    from flask import request

    _log(f"{request.method} /multi")
    return jsonify({"ok": request.method})


@app.get("/health")
def health():
    _log("GET /health")
    return jsonify({"status": "ok"})


@app.get("/gated")
def gated_get():
    _log("GET /gated")
    return jsonify({"ok": "get"})


if ENABLE_ADMIN:

    @app.post("/gated")
    def gated_post():
        _log("POST /gated")
        return jsonify({"ok": "post"})

    @app.post("/admin/purge")
    def admin_purge():
        _log("POST /admin/purge")
        return jsonify({"purged": True})
