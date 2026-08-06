"""T070 — the thin HTTP/SSE surface (T-03; **Q-05** subsumed rather than chosen).

Two things, which is what T-03 says the surface carries: the **caller-visible
result record** and the **session event stream**.

    GET /sessions/<id>/result   → application/json, one result record
    GET /sessions/<id>/events   → text/event-stream, the session's events

## What "thin" is holding out against

`dependencies = []` in `pyproject.toml`, and its comment says why: *"the runtime
path deliberately has no third-party dependency"*, and FR-021 pins everything
that is resolved at build time because the egress policy denies a package fetch
at run time anyway. So this is `http.server` and nothing else. A framework here
would be the first runtime dependency in the tree, taken for routing two paths.

It is also thin in a second sense that matters more. **This surface starts
nothing, admits nothing, and opens no store.** It renders what a caller already
holds. Admission is the supervisor's, the loop is `AgentLoop`'s, and the session
row is `SessionTable`'s — a serving layer that reached any of them would be the
process this tree does not have, arriving through the least-examined door.

> ### ⚠️ THIS MODULE IS NOT A PROCESS ENTRY POINT, AND THAT IS DELIBERATE
>
> There is no `def main`, no `__main__` block, no `[project.scripts]` entry and
> no socket bound at import. `build_server` binds when a caller calls it, and in
> this tree the callers are two contract-test modules.
>
> **Two things hang off that and both are recorded rather than acted on.**
>
> The startup seam recorded at `f167d7e` against T029 is **untouched**. Four
> authorities — `_NO_DEFAULT_BOUND` (FR-049, Q-10), `_NO_DEFAULT_CEILING`
> (FR-005), `_NO_DEFAULT_RESULT_BOUND` (FR-058) and `_NO_DEFAULT_OPERATOR_PRICES`
> (OD-27) — require a required-value-with-no-default to fail loudly at startup,
> `src/contracts/config.py::_report` already writes the operator's report, and
> none of it is reachable because the startup it names does not exist. **This
> module does not make it reachable.** It reads no configuration key: it takes a
> `Registry` and a bind address from its caller, and `config.load()` is still
> called from nowhere in `src/`. `require_priceable` is likewise still uncalled.
>
> **OD-28's ground ① is untouched for the same reason.** That deferral expires
> *"the moment a supervisor process constructs a `SessionTable` against a store
> that may be cold"*. Nothing here constructs one, imports one, or opens a
> `Repository`; a `SessionView` is handed over already built. The
> concurrent-first-open WAL race stays unreachable and the migration stays
> deferred on the ground OD-28 states.
>
> **What that costs, stated rather than left as an omission.** An operator
> cannot run this. Serving a session needs a process that loads configuration,
> builds the runtime, registers a view and calls `build_server` — and that
> process is the seam, not this file. Delivering T070 with one would have
> wired the startup preflight and retired OD-28's ground ① in the same commit,
> on this pass's own authority, which is three decisions this task does not
> carry.

## Refusals are composed from a registry and never from the request

`src/proxy/rules.go` is the precedent and it is a close one: it stamps a rule
identifier and the requirement that rule discharges into the decision-log record
**and** into the client-visible error body. Two consequences taken here.

**A refusal names its rule.** A body saying only *"not found"* tells a caller
nothing about which of four different not-founds happened.

**A refusal is a pure function of the rule identifier.** `refusal_body` reads
`REFUSALS` and nothing else — not the path, not a header, not the exception.
That is what makes an error body structurally unable to echo a caller's input,
and the input here is not hypothetical: **the session identifier travels in the
path**, so a 404 rendered with the path in it publishes whatever the caller
sent, into a body that is logged at both ends. FR-036 does not stop at the
success payload.

## What of `contracts/result-record.md` is here, and what is not

`src/contracts/result.py::Result` is the caller-visible result as it exists —
the verification outcome, the payload, the reason and the provisional flag —
and its own docstring records the rest as owed: *"the result's payload schema,
its storage and its trace linkage are Phase 6's and are still owed."* So
`render_result` renders `Result` and the end-of-run marker beside it. The
contract's `evidence`, `stale`/`staleness_reason` and `refusal` blocks are
**absent rather than stubbed**, on the same argument `TurnRecord.to_record()`
makes about the opaque state: a field that is present and empty is one somebody
later fills in without noticing there was nothing behind it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Mapping

from src.contracts.canonical import dumps
from src.contracts.result import Result
from src.runtime.events import SessionEvent, EventStream
from src.runtime.signals import EndOfRun


class SurfaceError(RuntimeError):
    """A surface that cannot be built or served as described."""


# ---------------------------------------------------------------------------
# The refusal registry. See the module docstring: a body is a function of the
# rule identifier and of nothing the caller sent.

RULE_ROUTE_UNKNOWN = "SV-ROUTE-001"
RULE_METHOD_NOT_ALLOWED = "SV-METHOD-001"
RULE_SESSION_UNKNOWN = "SV-SESSION-001"
RULE_RESULT_ABSENT = "SV-RESULT-001"
RULE_SURFACE_FAULT = "SV-FAULT-001"


@dataclass(frozen=True)
class Refusal:
    """One refusal, with the requirement it discharges.

    `Rule` in `src/proxy/rules.go` carries `Reason` and `Requirement` for the
    same purpose, and the shape is copied rather than reinvented so a reader
    crossing the two languages sees one vocabulary.
    """

    rule_id: str
    status: int
    reason: str
    requirement: str


REFUSALS: Mapping[str, Refusal] = {
    refusal.rule_id: refusal
    for refusal in (
        Refusal(RULE_ROUTE_UNKNOWN, 404, "route_unknown", "FR-033"),
        Refusal(RULE_METHOD_NOT_ALLOWED, 405, "method_not_allowed", "FR-033"),
        Refusal(RULE_SESSION_UNKNOWN, 404, "session_unknown", "FR-035"),
        # 409 rather than 404: the session exists and has produced no result
        # yet. A 404 here would let a caller polling for a result read "this
        # run produced nothing" off a run that has not finished, which is the
        # false-success shape T068 measures one channel over.
        Refusal(RULE_RESULT_ABSENT, 409, "result_absent", "FR-025"),
        Refusal(RULE_SURFACE_FAULT, 500, "surface_fault", "FR-006"),
    )
}


def refusal_body(rule_id: str) -> bytes:
    """The bytes for one refusal. **A function of `rule_id` alone.**

    Nothing from the request reaches here — no path, no header, no exception
    text. That is the mechanism behind
    `tests/contract/test_event_stream_redaction.py`'s assertion that a refusal
    cannot echo a credential a caller put in the path, and it is why that
    assertion is a property rather than a coincidence of today's wording.
    """
    refusal = REFUSALS.get(rule_id)
    if refusal is None:
        raise SurfaceError(
            f"{rule_id!r} is not a registered refusal. A body composed for an "
            "unregistered rule would be composed from something other than "
            "the registry, which is the only thing keeping a caller's input "
            "out of an error body."
        )
    return dumps({
        "rule_id": refusal.rule_id,
        "reason": refusal.reason,
        "requirement": refusal.requirement,
    })


# ---------------------------------------------------------------------------
# What the surface serves.


@dataclass(frozen=True)
class SessionView:
    """One session as this surface can see it: a stream, and maybe a result.

    `result` is `None` for a session still running. That is a **state**, served
    as `SV-RESULT-001`, and not an absence served as an empty record.
    """

    session_id: str
    stream: EventStream
    result: Result | None = None
    end_of_run: EndOfRun | None = None

    def __post_init__(self) -> None:
        if not self.session_id:
            raise SurfaceError("a view belongs to a session or to nothing")
        if self.stream.session_id != self.session_id:
            raise SurfaceError(
                f"view {self.session_id!r} holds {self.stream.session_id!r}'s "
                "event stream. Served together, one session's result would sit "
                "beside another session's events and both halves would look "
                "internally consistent."
            )
        if self.end_of_run is not None \
                and self.end_of_run.session_id != self.session_id:
            raise SurfaceError(
                f"view {self.session_id!r} holds {self.end_of_run.session_id!r}"
                "'s end-of-run marker"
            )


class Registry:
    """The sessions this surface will serve. Handed over, never discovered.

    Deliberately not a store lookup. A registry that went to disk for a session
    it had not been told about would be this module opening the session store,
    which is the thing the entry-point note in the module docstring says it does
    not do.
    """

    __slots__ = ("_views",)

    def __init__(self) -> None:
        self._views: dict[str, SessionView] = {}

    def register(self, view: SessionView) -> None:
        if view.session_id in self._views:
            raise SurfaceError(
                f"{view.session_id!r} is already registered. A second "
                "registration would replace a live stream with another, and "
                "a caller mid-read would silently change sessions."
            )
        self._views[view.session_id] = view

    def view(self, session_id: str) -> SessionView | None:
        return self._views.get(session_id)


def _end_of_run(view: SessionView) -> EndOfRun | None:
    """The marker, from the view or from the stream's last event.

    Read off the stream rather than required on the view, because the stream is
    where `end()` puts it and a second required copy would be a second thing to
    keep equal.
    """
    if view.end_of_run is not None:
        return view.end_of_run
    return None


def render_result(view: SessionView) -> dict[str, Any]:
    """The caller-visible result record. See the module docstring for the parts
    of `contracts/result-record.md` that are Phase 6's and are absent here."""
    if view.result is None:
        raise SurfaceError(RULE_RESULT_ABSENT)

    events = view.stream.events
    marker = _end_of_run(view)
    ended = events[-1].data.get("end_of_run") if events and view.stream.closed \
        else None
    if marker is not None:
        ended = marker.to_record()

    return {
        "session_id": view.session_id,
        "verification": view.result.verification.value,
        "payload": view.result.payload,
        "reason": view.result.reason,
        "provisional": view.result.provisional,
        # Both, and from one source. `RunOutcome` keeps the two apart for the
        # same reason: a caller asking *did this end?* and a caller asking
        # *why did it end?* are asking different questions, and the marker is
        # what answers the second without a second resolution of the first.
        "terminal_state": None if ended is None else ended["terminal_state"],
        "end_of_run": ended,
        "events": len(events),
    }


def sse_frame(event: SessionEvent) -> bytes:
    """One event as an SSE frame.

    `id` is the sequence, which is what a caller reconnecting sends back in
    `Last-Event-ID` and what orders the stream — not `at`, because two events
    in one clock tick tie.

    **The `data:` line is one line, and that is a property of the encoder
    rather than of this function.** `SessionEvent.encode` goes through the
    canonical serializer, whose string escaping turns every control character
    including a newline into an escape sequence; the only newline left is the
    one `dumps` appends, which is stripped here. A payload newline reaching the
    wire would terminate the line early and split one event into two.
    """
    return (
        f"id: {event.sequence}\n"
        f"event: {event.kind}\n"
    ).encode("utf-8") + b"data: " + event.encode().rstrip(b"\n") + b"\n\n"


# ---------------------------------------------------------------------------
# The server.


def build_handler(registry: Registry) -> type[BaseHTTPRequestHandler]:
    """A handler class bound to one registry. Nothing global."""

    class SurfaceHandler(BaseHTTPRequestHandler):
        # A version string that names the product rather than the interpreter.
        # `BaseHTTPRequestHandler` otherwise advertises `Python/3.12.11` on
        # every response, which is a build detail on a caller-visible header.
        server_version = "f2a-surface/1"
        sys_version = ""
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:  # noqa: N802 - http.server's spelling
            try:
                self._route()
            except Exception:  # noqa: BLE001 - see below
                # The fault is refused from the registry like any other, so a
                # traceback cannot reach a caller. `src/supervisor/lease.py`
                # already records at length why a traceback is a poor operator
                # interface; on a caller-visible surface it is also a
                # disclosure, because the frames carry paths and arguments.
                self._refuse(RULE_SURFACE_FAULT)

        def _route(self) -> None:
            parts = [p for p in self.path.split("?")[0].split("/") if p]
            if len(parts) != 3 or parts[0] != "sessions":
                self._refuse(RULE_ROUTE_UNKNOWN)
                return
            view = registry.view(parts[1])
            if view is None:
                self._refuse(RULE_SESSION_UNKNOWN)
                return
            if parts[2] == "result":
                self._result(view)
            elif parts[2] == "events":
                self._events(view)
            else:
                self._refuse(RULE_ROUTE_UNKNOWN)

        def _result(self, view: SessionView) -> None:
            try:
                record = render_result(view)
            except SurfaceError:
                self._refuse(RULE_RESULT_ABSENT)
                return
            self._send(200, "application/json", dumps(record))

        def _events(self, view: SessionView) -> None:
            body = b"".join(sse_frame(event) for event in view.stream.events)
            self._send(200, "text/event-stream", body, extra={
                # An intermediary caching a session's event stream would replay
                # one session's events to another caller.
                "Cache-Control": "no-store",
                "X-Accel-Buffering": "no",
            })

        def _refuse(self, rule_id: str) -> None:
            self._send(REFUSALS[rule_id].status, "application/json",
                       refusal_body(rule_id))

        def _send(
            self, status: int, content_type: str, body: bytes,
            extra: Mapping[str, str] | None = None,
        ) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            for name, value in (extra or {}).items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(body)

        def _method_not_allowed(self) -> None:
            self._refuse(RULE_METHOD_NOT_ALLOWED)

        # Every other method, named rather than left to `501 Unsupported`, so
        # the refusal carries a rule identifier like every other refusal here.
        do_POST = do_PUT = do_PATCH = do_DELETE = _method_not_allowed  # noqa: N815

        def log_message(self, fmt: str, *args: Any) -> None:
            """Silenced, and not because logging is noisy.

            `BaseHTTPRequestHandler` writes the **request line** to stderr on
            every request, and the request line holds the path — which is where
            the session identifier travels. That is the same leak
            `refusal_body` is written to avoid, arriving on a different
            channel. A logging facility that redacts is a larger thing than
            this task builds; refusing to write is what is available here, and
            it is recorded as a narrowing rather than a decision that no
            request should ever be logged.
            """

    return SurfaceHandler


def build_server(
    registry: Registry, *, host: str, port: int
) -> ThreadingHTTPServer:
    """Bind and return the server. **The caller starts it.**

    `host` is required and has no default, which is FR-033's treatment applied
    to the one piece of this surface's configuration that has no safe value.
    `""` and `0.0.0.0` mean *every interface on this host*, and a surface that
    reaches them by omission is exposed by an operator who typed nothing —
    the same shape as a ceiling filled from an invented default, which
    `src/contracts/config.py` refuses for FR-005 and FR-049. Binding
    everywhere has to be typed.

    This function is the whole of the surface's lifecycle and it stops here: it
    does not serve, does not spawn a thread, and is not called from anywhere in
    `src/`. See the entry-point note in the module docstring.
    """
    if not host or host in ("0.0.0.0", "::", "*"):
        raise SurfaceError(
            f"host={host!r} is not an address to bind to. An empty host and "
            "the wildcards mean every interface on this host, so a surface "
            "carrying session results would be reachable from wherever this "
            "process can be reached — by an operator who typed nothing. "
            "FR-033's treatment: required configuration, refused rather than "
            "defaulted. Pass '127.0.0.1' for a local surface, or the specific "
            "address the deployment intends to expose."
        )
    return ThreadingHTTPServer((host, port), build_handler(registry))
