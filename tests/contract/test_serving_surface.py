"""T071 — the contract of the HTTP/SSE surface and the event stream it renders.

Constitution Principle VII's integration-surface clause is *"closed by FR-033's
fail-loud configuration and FR-044's contract tests, over the HTTP/SSE surface
of T-03"*, so this file has to cover both halves: the surface refuses a
configuration it cannot honour, and the two things it carries — the
caller-visible result record and the session event stream — arrive in the shape
a caller can rely on.

**Everything below reads the wire, not the objects.** The surface's obligations
are properties of the bytes a caller receives; a test that asserted over the
`SessionEvent` instances the server happens to hold would pass for a renderer
that dropped every field on the way out. So each test starts an actual server
on an ephemeral port, makes an actual request, and asserts over the response.

**The framing tests are the ones that would otherwise be vacuous.** An SSE
`data:` line is newline-terminated, so a payload containing a newline splits one
event into two and the second is unparseable — and no ordinary payload contains
one, which is why the defect survives review. `_A_PAYLOAD_WITH_A_NEWLINE` is
planted for exactly that, and `test_the_frame_control_would_catch_an_unescaped_newline`
asserts the check can tell the two cases apart before the check is trusted.
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
import threading
import urllib.error
import urllib.request

import pytest

from src.contracts.result import Corroboration, Result, VerificationOutcome
from src.runtime import events, serving
from src.runtime.dispatch import ToolCall, ToolResult
from src.runtime.events import EventError, EventStream, SessionEvent
from src.runtime.result_bound import (
    DISPOSITION_RETAINED,
    UNIT_TOKENS,
    BoundFields,
)
from src.runtime.serving import Registry, SessionView
from src.runtime.signals import REASON_COMPLETED, EndOfRun
from src.runtime.trace import OUTCOME_OK
from src.runtime.turn import TurnRecord

SESSION = "sess-serving-1"

# A newline inside a payload. See the module docstring: this is the content that
# breaks SSE framing and that nothing ordinary contains.
_A_PAYLOAD_WITH_A_NEWLINE = "line one\nline two"


class _Clock:
    """Monotonic and explicit. A real clock would make `at` a property of the
    host, which is the shape this corpus keeps finding in expectations."""

    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        self.now += 1.0
        return self.now


def _bound_fields(full: int = 12, admitted: int = 12) -> BoundFields:
    return BoundFields(
        bound_applied=True,
        bound_in_force=64,
        unit=UNIT_TOKENS,
        byte_proxy=False,
        full_size=full,
        admitted=admitted,
        disposition=DISPOSITION_RETAINED,
        tokenizer_name="stub",
    )


def build_stream(session_id: str = SESSION, *, body: str = "ok") -> EventStream:
    """One complete session's stream: started, one turn with one tool, ended."""
    stream = EventStream(session_id, clock=_Clock())
    stream.start()
    stream.turn_started(0)
    call = ToolCall(index=0, call_id="call-a", name="run_command",
                    arguments={"command": "ls"})
    stream.tool_started(0, call)
    stream.tool_finished(
        0,
        ToolResult(call=call, outcome=OUTCOME_OK, body=body,
                   started_at=1.0, finished_at=2.0),
        _bound_fields(),
    )
    stream.turn_completed(TurnRecord(
        turn_index=0, provider="anthropic", provider_state=b"\x00opaque\xff",
        tool_calls=(call,), tool_results=(), text="done", at=3.0))
    stream.end(EndOfRun(session_id=session_id, reason=REASON_COMPLETED, at=4.0))
    return stream


def build_view(session_id: str = SESSION, **kwargs) -> SessionView:
    return SessionView(
        session_id=session_id,
        stream=build_stream(session_id, **kwargs),
        result=Result(VerificationOutcome.NOT_VERIFIABLE, payload={"answer": 41},
                      corroboration=Corroboration.NOT_STATED,
                      reason="no derived contract covers this operation"),
    )


class _Server:
    def __init__(self, registry: Registry) -> None:
        self.http = serving.build_server(registry, host="127.0.0.1", port=0)
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()

    @property
    def base(self) -> str:
        host, port = self.http.server_address[:2]
        return f"http://{host}:{port}"

    def get(self, path: str) -> tuple[int, dict[str, str], bytes]:
        try:
            with urllib.request.urlopen(self.base + path, timeout=10) as response:
                return response.status, dict(response.headers), response.read()
        except urllib.error.HTTPError as failure:  # a refusal is a response
            return failure.code, dict(failure.headers), failure.read()

    def close(self) -> None:
        self.http.shutdown()
        self.http.server_close()
        self.thread.join(timeout=5)


@pytest.fixture()
def server():
    registry = Registry()
    registry.register(build_view())
    running = _Server(registry)
    yield running
    running.close()


# -- FR-033's half of Principle VII: the surface refuses what it cannot honour --

def test_the_surface_refuses_to_bind_without_an_explicit_host() -> None:
    """A bind address has no safe default, so the surface ships none.

    `""` and `0.0.0.0` mean *every interface on this host*, and a surface that
    reaches them by omission is exposed by an operator who typed nothing. The
    treatment is FR-033's: required configuration, refused at construction,
    naming what is missing. This is the one arm of Principle VII's
    integration-surface clause that is about configuration rather than shape.
    """
    with pytest.raises(serving.SurfaceError, match="bind"):
        serving.build_server(Registry(), host="", port=0)


def test_a_view_whose_stream_belongs_to_another_session_is_refused() -> None:
    """The malformed-input half. Two identifiers that must agree, checked.

    A view registered under one id holding another session's stream would
    serve one session's result beside another session's events, and both halves
    would look internally consistent.
    """
    with pytest.raises(serving.SurfaceError, match="sess-other"):
        SessionView(session_id="sess-other", stream=build_stream(SESSION))


# -- the caller-visible result record ---------------------------------------

def test_the_result_endpoint_carries_the_verification_state(server) -> None:
    status, headers, body = server.get(f"/sessions/{SESSION}/result")
    assert status == 200
    assert headers["Content-Type"] == "application/json"

    record = json.loads(body)
    assert record["session_id"] == SESSION
    assert record["verification"] == "not_verifiable"
    assert record["reason"], (
        "FR-025's non-verified states carry a reason; an unexplained one is "
        "indistinguishable from an untried one"
    )
    assert record["payload"] == {"answer": 41}
    assert record["terminal_state"] == "terminated.completed"
    assert record["end_of_run"]["reason"] == "completed"


def test_a_result_that_does_not_exist_yet_is_a_refusal_and_not_an_empty_one(
) -> None:
    """A running session has no result. That is a state, not an absence.

    Serving `{}` or `null` here would let a caller polling for a result read
    *"the run produced nothing"* off a run that has not finished, which is the
    false-success shape T068 measured one channel over.
    """
    registry = Registry()
    registry.register(SessionView(session_id=SESSION, stream=build_stream()))
    running = _Server(registry)
    try:
        status, _, body = running.get(f"/sessions/{SESSION}/result")
    finally:
        running.close()
    assert status == 409
    refusal = json.loads(body)
    assert refusal["rule_id"] == serving.RULE_RESULT_ABSENT
    assert refusal["reason"] == "result_absent"


# -- the session event stream ------------------------------------------------

def test_the_event_endpoint_is_an_sse_stream_that_ends(server) -> None:
    status, headers, body = server.get(f"/sessions/{SESSION}/events")
    assert status == 200
    assert headers["Content-Type"] == "text/event-stream"
    assert headers["Cache-Control"] == "no-store", (
        "an intermediary caching a session's event stream would replay one "
        "session's events to another caller"
    )
    assert body.endswith(b"\n\n"), "the last frame is unterminated"


def parse_frames(body: bytes) -> list[dict]:
    """Rebuild the events from the wire. **Nothing here touches a live object.**

    This is the persistence boundary. A test that asserted over the
    `SessionEvent` instances the server holds would be blind to a renderer that
    dropped a field, and blind in exactly the direction that matters: the
    objects are correct by construction and the bytes are what a caller reads.
    """
    frames = []
    for block in body.decode("utf-8").split("\n\n"):
        if not block.strip():
            continue
        fields: dict[str, str] = {}
        for line in block.split("\n"):
            name, _, value = line.partition(": ")
            fields[name] = value
        frames.append({
            "id": fields["id"],
            "event": fields["event"],
            "data": json.loads(fields["data"]),
        })
    return frames


def test_every_declared_event_kind_reaches_the_wire(server) -> None:
    """The stream's shape, read back from the frames.

    Asserted as a set equality rather than a subset: a surface that emitted
    `session_started` and `run_ended` and nothing between them would satisfy
    every ordering assertion below, and would carry no session.
    """
    _, _, body = server.get(f"/sessions/{SESSION}/events")
    frames = parse_frames(body)
    assert frames, "the stream carried no frames at all"
    assert [f["event"] for f in frames] == [
        events.KIND_SESSION_STARTED,
        events.KIND_TURN_STARTED,
        events.KIND_TOOL_STARTED,
        events.KIND_TOOL_FINISHED,
        events.KIND_TURN_COMPLETED,
        events.KIND_RUN_ENDED,
    ]


def test_the_frames_carry_the_position_that_orders_them(server) -> None:
    """`id` is the sequence, and it is what orders the stream.

    Not the timestamp: `at` is data, and two events in one clock tick would tie.
    The same reading FR-038 takes for a span's ordinal, for the same reason.
    """
    _, _, body = server.get(f"/sessions/{SESSION}/events")
    frames = parse_frames(body)
    assert [f["id"] for f in frames] == [str(i) for i in range(len(frames))]
    assert [f["data"]["sequence"] for f in frames] == list(range(len(frames)))


def test_the_last_frame_names_the_terminal_state(server) -> None:
    """A caller reading only the stream can still tell how the run ended.

    T068's measurement is that a payload alone cannot separate a completion
    from a cancellation. The stream is a third channel and inherits the
    obligation: the marker rides on the last frame or the channel is one more
    place the two look alike.
    """
    _, _, body = server.get(f"/sessions/{SESSION}/events")
    last = parse_frames(body)[-1]
    assert last["event"] == events.KIND_RUN_ENDED
    marker = last["data"]["data"]["end_of_run"]
    assert marker["reason"] == "completed"
    assert marker["terminal_state"] == "terminated.completed"


def test_a_payload_newline_cannot_split_a_frame() -> None:
    """The framing hazard, planted.

    SSE terminates a `data:` line with a newline, so an unescaped newline in a
    payload produces a second line the parser reads as a new field — and the
    frame count silently goes up by one. The canonical serializer escapes it;
    this asserts the escaping is what the wire actually carries.
    """
    registry = Registry()
    registry.register(build_view(body=_A_PAYLOAD_WITH_A_NEWLINE))
    running = _Server(registry)
    try:
        _, _, body = running.get(f"/sessions/{SESSION}/events")
    finally:
        running.close()

    raw = body.decode("utf-8")
    assert "line one\\nline two" in raw, (
        "the payload newline reached the wire unescaped; the `data:` line is "
        "terminated by it and the frame is split"
    )
    assert _A_PAYLOAD_WITH_A_NEWLINE not in raw
    assert len([l for l in raw.split("\n") if l.startswith("data: ")]) == 6, (
        "one data line per event, and six events"
    )

    frames = parse_frames(body)
    assert len(frames) == 6, (
        f"{len(frames)} frames for a six-event stream — a payload newline "
        "split a frame"
    )
    carried = [f for f in frames if f["event"] == events.KIND_TOOL_FINISHED]
    assert carried, "no tool_finished frame; the planted payload never ran"
    # The parsed value, not the re-rendered one. `json.dumps` would escape the
    # newline again and the check would pass over a frame that had lost it.
    assert carried[0]["data"]["data"]["body"] == _A_PAYLOAD_WITH_A_NEWLINE, (
        "the planted payload never reached the wire intact, so this test "
        "asserted the framing of content that was not there"
    )


def test_the_frame_control_would_catch_an_unescaped_newline() -> None:
    """The control for the test above. Without it the count is unfalsifiable.

    A six-frame assertion over a parser that cannot produce seven is a green
    tick over an absent measurement.
    """
    split = parse_frames(
        b"id: 0\nevent: a\ndata: 1\n\nid: 1\nevent: b\ndata: 2\n\n")
    assert len(split) == 2


# -- refusals are a closed vocabulary ---------------------------------------

def test_an_unknown_route_is_refused_with_a_rule_identifier(server) -> None:
    status, _, body = server.get("/no/such/route")
    assert status == 404
    refusal = json.loads(body)
    assert refusal["rule_id"] == serving.RULE_ROUTE_UNKNOWN
    assert refusal["requirement"], (
        "src/proxy/rules.go stamps the requirement a rule discharges into "
        "every client-visible body; this surface is the same kind of "
        "enforcement point and takes the same treatment"
    )


def test_an_unknown_session_is_refused(server) -> None:
    status, _, body = server.get("/sessions/sess-nope/events")
    assert status == 404
    assert json.loads(body)["rule_id"] == serving.RULE_SESSION_UNKNOWN


def test_every_refusal_the_surface_can_emit_is_registered() -> None:
    """No refusal is composed anywhere but from the registry.

    The registry is what makes an error body unable to echo a request. A body
    assembled from a format string over the path would carry whatever the
    caller put in the path, which is the leak `tests/contract/
    test_event_stream_redaction.py` plants against.
    """
    assert serving.REFUSALS, "the refusal registry is empty"
    for rule_id, refusal in serving.REFUSALS.items():
        assert refusal.rule_id == rule_id
        assert refusal.reason and refusal.requirement
        assert 400 <= refusal.status < 600


def test_the_request_line_does_not_reach_stderr() -> None:
    """The same leak as an echoing error body, on a different channel.

    `BaseHTTPRequestHandler.log_message` writes the **request line** to stderr
    on every request, and the request line holds the path — which is where the
    session identifier travels. `refusal_body` keeps a caller's input out of
    the response; this keeps it out of the process's own output.

    The control comes first. Without it a redirect that captured nothing would
    make the assertion below true of a surface that logged everything.
    """
    registry = Registry()
    registry.register(build_view())
    captured = io.StringIO()
    running = _Server(registry)
    try:
        with contextlib.redirect_stderr(captured):
            print("a control line", file=sys.stderr)
            running.get(f"/sessions/{SESSION}/result")
            running.get("/no/such/route")
    finally:
        running.close()

    written = captured.getvalue()
    assert "a control line" in written, (
        "the redirect captured nothing, so the assertion below is about an "
        "output stream this test never read"
    )
    assert SESSION not in written, (
        "the request line reached stderr with the path in it, and the session "
        "identifier travels in the path"
    )


def test_a_method_other_than_get_is_refused(server) -> None:
    request = urllib.request.Request(
        f"{server.base}/sessions/{SESSION}/result", method="POST", data=b"{}")
    with pytest.raises(urllib.error.HTTPError) as caught:
        urllib.request.urlopen(request, timeout=10)
    assert caught.value.code == 405
    assert json.loads(caught.value.read())["rule_id"] == \
        serving.RULE_METHOD_NOT_ALLOWED


# -- the emitter's own contract ----------------------------------------------

def test_a_stream_cannot_begin_anywhere_but_at_the_start() -> None:
    """A stream that begins mid-run reads as a complete one.

    The same failure shape as a missing end-of-run marker, at the other end:
    a caller attaching to a stream whose first frame is `turn_started` cannot
    tell it from a session that had no earlier turns.
    """
    stream = EventStream(SESSION, clock=_Clock())
    with pytest.raises(EventError, match="session_started"):
        stream.turn_started(0)


def test_nothing_is_emitted_after_the_run_has_ended() -> None:
    stream = build_stream()
    assert stream.closed
    with pytest.raises(EventError, match="ended"):
        stream.turn_started(1)


def test_the_end_of_run_frame_cannot_be_forged_by_omission() -> None:
    """`run_ended` is the only kind that ends a stream, and it needs a marker.

    T066's rule one channel over: there is no value of any field that lets an
    un-ended run look like a finished one, because the kind that says a run
    ended is the kind that requires `EndOfRun`.
    """
    stream = EventStream(SESSION, clock=_Clock())
    stream.start()
    assert not stream.closed
    with pytest.raises(EventError):
        stream.emit(events.KIND_RUN_ENDED)


def test_an_undeclared_event_kind_is_refused() -> None:
    stream = EventStream(SESSION, clock=_Clock())
    stream.start()
    with pytest.raises(EventError, match="declared"):
        stream.emit("model_call")


def test_a_subscriber_sees_each_event_once_as_it_is_emitted() -> None:
    """The emitter half of T069: a live reader, not only a replay.

    A stream that only accumulated would make the SSE surface a poll, which is
    the thing SSE exists not to be.
    """
    seen: list[SessionEvent] = []
    stream = EventStream(SESSION, clock=_Clock())
    stream.subscribe(seen.append)
    stream.start()
    stream.turn_started(0)
    stream.end(EndOfRun(session_id=SESSION, reason=REASON_COMPLETED, at=4.0))
    assert [e.kind for e in seen] == [
        events.KIND_SESSION_STARTED,
        events.KIND_TURN_STARTED,
        events.KIND_RUN_ENDED,
    ]
    assert tuple(seen) == stream.events, (
        "the live stream and the replay disagree, so one of the two is not "
        "what a caller gets"
    )


def test_a_tool_result_arrives_with_its_bound_disclosed() -> None:
    """FR-058's *disclosure* obligation is written for the model, not for this
    reader — see the module docstring of `src/runtime/events.py` for the
    reading. The obligation is taken here anyway, and the reason is that a
    caller reading a bounded preview with nothing beside it saying so is the
    same wrong answer FR-058 describes, arriving at a different reader.

    Structural rather than conventional: `tool_finished` takes the fields.
    """
    stream = EventStream(SESSION, clock=_Clock())
    stream.start()
    call = ToolCall(index=0, call_id="c", name="run_command")
    result = ToolResult(call=call, outcome=OUTCOME_OK, body="x",
                        started_at=0.0, finished_at=1.0)
    with pytest.raises(TypeError):
        stream.tool_finished(0, result)  # type: ignore[call-arg]

    stream.tool_finished(0, result, _bound_fields(full=900, admitted=64))
    emitted = stream.events[-1]
    assert emitted.data["bound"]["full_size"] == 900
    assert emitted.data["bound"]["admitted"] == 64
    assert emitted.data["bound"]["bound_applied"] is True
