"""T116 — the reference application itself.

**Requirement**: FR-053. The seeded state and the answers it makes true are in
`seed.py`; this file is the surface those answers are reached through.

## What it is for

Three things in Phase 4 need a workload rather than a proxy for one:

- **T101** measures the syscall supervisor's overhead *on the reference
  application*: `Application.call` is the in-process arm, `build_server` the
  socket arm, and the shell-heavy arm is a proxy in the battery, not here.
- **T114** asserts that zero calls which did not resolve read-only reach the
  target. That assertion needs a target with an operation that is *not*
  read-only, which `POST /shipments/{id}/cancel` is, and a published
  specification that says so, which `served_operations.json` is.
- **T115** asserts zero reads and zero writes outside the declared set. The
  application reads and writes nothing outside `state_root()`, so the declared
  set has one member and everything else is an adversarial arm.

None of those three is discharged here. This is the subject they were missing.

## Two properties this file is holding, both of them proof-backed

- **Every served record carries its `attestation`.** Dropping it leaves every
  answer correct and every evidence digest wrong, which is precisely the
  opaque-state loss finding 016 records and precisely what a suite that checks
  answers cannot see.
- **No response discloses `ATTESTATION_KEY`.** If it did, the digest would
  become derivable from the served surface and the unforgeable half of a
  known-correct answer would stop being unforgeable.

## The route table and the published specification are one fact stated twice

`ROUTES` here and `served_operations.json` are reconciled by
`tests/unit/test_reference_app.py` in **both** directions. An operation the
specification does not describe is exactly what T089 requires the enforcement
point to deny rather than guess at, so a reference application that quietly
served one would be a fixture that cannot exercise its own denial path.
"""

from __future__ import annotations

import json
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
for _entry in (str(REPO), str(HERE)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

import seed as _seed  # noqa: E402

READ_ONLY = "read_only"
WRITE = "write"

_PART_PATH = re.compile(r"^/parts/(?P<part_id>P-[0-9]{4})$")
_CANCEL_PATH = re.compile(r"^/shipments/(?P<shipment_id>S-[0-9]{4})/cancel$")


class OperationError(Exception):
    """A refusal that names its operation, never a bare 404 with a path echo."""

    def __init__(self, status: int, rule_id: str, reason: str):
        super().__init__(reason)
        self.status = status
        self.rule_id = rule_id
        self.reason = reason


def state_root() -> Path:
    """The one filesystem location the application touches.

    T115's declared set has this as its single member. There is no default
    elsewhere and no environment variable that moves it: the fixture's state is
    committed beside it, and a location that can be reconfigured is a location
    a battery cannot make claims about.
    """
    return HERE


class Application:
    """The reference application, in process.

    Constructed from a state document rather than reading one, so a battery can
    drive a copy and diff it (T180) without touching the committed fixture.
    """

    def __init__(self, state: dict[str, Any]):
        self.state = json.loads(json.dumps(state))  # a private copy, always
        self.calls: list[tuple[str, str]] = []

    # -- the operations ----------------------------------------------------

    def _health(self, _query: dict[str, list[str]]) -> dict[str, Any]:
        return {
            "status": "serving",
            "deployment_id": self.state["deployment_id"],
            "seed_version": self.state["seed_version"],
        }

    def _list_parts(self, _query: dict[str, list[str]]) -> dict[str, Any]:
        return {"parts": [dict(row) for row in self.state["parts"]]}

    def _get_part(self, part_id: str) -> dict[str, Any]:
        for row in self.state["parts"]:
            if row["part_id"] == part_id:
                return dict(row)
        raise OperationError(404, "REFAPP-004", "no part with that identifier")

    def _list_shipments(self, query: dict[str, list[str]]) -> dict[str, Any]:
        wanted = query.get("part_id", [None])[0]
        rows = [
            dict(row)
            for row in self.state["shipments"]
            if wanted is None or row["part_id"] == wanted
        ]
        return {"shipments": rows}

    def _cancel_shipment(self, shipment_id: str) -> dict[str, Any]:
        for row in self.state["shipments"]:
            if row["shipment_id"] == shipment_id:
                row["status"] = "cancelled"
                return {"shipment": dict(row)}
        raise OperationError(404, "REFAPP-005", "no shipment with that identifier")

    # -- dispatch ----------------------------------------------------------

    def call(self, method: str, target: str) -> tuple[int, dict[str, Any]]:
        """Resolve one operation. Records the call so T180 can diff a sequence."""
        self.calls.append((method, target))
        split = urlsplit(target)
        path, query = split.path, parse_qs(split.query)

        try:
            return 200, self._dispatch(method, path, query)
        except OperationError as exc:
            return exc.status, {"rule_id": exc.rule_id, "reason": exc.reason}

    def _dispatch(
        self, method: str, path: str, query: dict[str, list[str]]
    ) -> dict[str, Any]:
        if path == "/health" and method == "GET":
            return self._health(query)
        if path == "/parts" and method == "GET":
            return self._list_parts(query)
        match = _PART_PATH.match(path)
        if match and method == "GET":
            return self._get_part(match.group("part_id"))
        if path == "/shipments" and method == "GET":
            return self._list_shipments(query)
        match = _CANCEL_PATH.match(path)
        if match and method == "POST":
            return self._cancel_shipment(match.group("shipment_id"))
        raise OperationError(
            404,
            "REFAPP-001",
            "the published specification describes no such operation",
        )


#: The route table, keyed by the operation id the published specification uses.
#: Reconciled against `served_operations.json` in both directions.
ROUTES: dict[str, tuple[str, str, str]] = {
    "health": ("GET", "/health", READ_ONLY),
    "list_parts": ("GET", "/parts", READ_ONLY),
    "get_part": ("GET", "/parts/{part_id}", READ_ONLY),
    "list_shipments": ("GET", "/shipments", READ_ONLY),
    "cancel_shipment": ("POST", "/shipments/{shipment_id}/cancel", WRITE),
}


def from_committed_state() -> Application:
    return Application(_seed.load_state())


# ---------------------------------------------------------------------------
# The HTTP origin.


def build_handler(app: Application) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def _respond(self, method: str) -> None:
            status, body = app.call(method, self.path)
            payload = json.dumps(body, sort_keys=True).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self) -> None:  # noqa: N802 — BaseHTTPRequestHandler's name
            self._respond("GET")

        def do_POST(self) -> None:  # noqa: N802
            self._respond("POST")

        def log_message(self, fmt: str, *args: Any) -> None:
            """Silent by construction.

            `BaseHTTPRequestHandler` writes the request line to stderr, and the
            request line carries the path. T070 has a removal proof on exactly
            that leak in the product's own surface; a fixture that reinstates
            it beside the batteries would be the same disclosure by a fixture's
            door.
            """

    return Handler


def build_server(app: Application, *, host: str, port: int) -> ThreadingHTTPServer:
    """Bind the reference application to one address.

    `host` is required and has no default, and the wildcards are refused. This
    mirrors `src/runtime/serving.py::build_server` rather than inventing a
    second convention — and a fixture that bound every interface because
    nobody passed a host would be a listening surface created by an omission.
    """
    if not host or host in ("0.0.0.0", "::", "*"):
        raise ValueError(
            f"host={host!r} is not an address to bind to. An empty host and "
            "the wildcards mean every interface, and a fixture origin belongs "
            "on the loopback address the battery names."
        )
    return ThreadingHTTPServer((host, port), build_handler(app))
