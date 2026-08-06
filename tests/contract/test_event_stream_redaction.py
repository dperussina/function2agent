"""T072 — no secret value and no readable `provider_state` on the event stream.

FR-036 (*"no secret value MAY appear in model context, in an emitted artifact,
in a trace, or in persisted state"*) and FR-037 (*"provider-opaque reasoning
state ... never dropped and never merged"*, and — `src/runtime/providers/state.py`
— never rendered). `tests/contract/test_trace_redaction.py` holds the same two
requirements over the trace. **This file is not that file with a different
import.** The trace is the machine-readable audit channel written to a
`Repository`; the event stream is what a caller reads over HTTP. Different
reader, different transport, and the second one is the one an untrusted browser
can hold.

**Three disciplines, each of which a redaction test here has previously lacked
somewhere in this repository.**

1. **Rebuilt from serialized bytes, never asserted over live objects.** A
   fixture in this tree was blind to the very defect it existed for, twice in
   the same place, because it appended parsed turns *by reference* — so a
   re-injection rewrote a value that was already present and the comparison
   compared an object with itself. Opaque state is exactly the shape that
   failure hides: the object graph is correct and the bytes are what leaks.
   `parse_frames` below goes through `json.loads` on the wire body, and
   `_reconstructed` is the only thing asserted over.

2. **Non-vacuity is asserted, not assumed.** A redaction scan over zero events
   passes for a system that publishes every credential it holds. Every test
   below states what it expected to find and fails if that was absent, and
   `test_the_scanner_catches_a_planted_credential` is the control that makes
   "no findings" mean something.

3. **Error bodies are part of the surface.** `src/proxy/rules.go` stamps a
   requirement identifier into the client-visible error body as well as into
   the decision log, which is the precedent: a refusal is a response and a
   response is a place a value can leak. The session identifier travels in the
   *path*, so a 404 that echoes the path echoes whatever the caller put there.
"""

from __future__ import annotations

import json
import re
import threading
import urllib.error
import urllib.request

import pytest

from src.contracts.result import Result, VerificationOutcome
from src.contracts.secret import Secret
from src.runtime import events, serving
from src.runtime.dispatch import ToolCall, ToolResult
from src.runtime.events import EventError, EventStream
from src.runtime.result_bound import (
    DISPOSITION_RETAINED,
    UNIT_TOKENS,
    BoundFields,
)
from src.runtime.serving import Registry, SessionView
from src.runtime.signals import REASON_COMPLETED, EndOfRun
from src.runtime.trace import OUTCOME_OK
from src.runtime.turn import TurnRecord, state_digest

SESSION = "sess-redaction-1"

TEST_CREDENTIAL = "sk-live-0123456789abcdefghij"

#: Genuinely binary and containing a NUL, for the same reason
#: `tests/unit/test_provider_state.py` plants one: a value that survives a
#: separator-framed carrier by accident is not evidence about a value that does
#: not, and Google's `thought_signature` is arbitrary bytes.
OPAQUE_STATE = b"\x00\xff\x1bthinking-signature-payload\x00\xfe"

# The same shapes `tests/contract/test_trace_redaction.py` scans for. Held
# separately rather than imported: two channels agreeing because they share one
# detector is two artifacts with one gap, which is the corroboration failure
# that file's own docstring records.
CREDENTIAL_PATTERNS = {
    "openai_key": re.compile(r"sk-[A-Za-z0-9_-]{16,}"),
    "anthropic_key": re.compile(r"sk-ant-[A-Za-z0-9_-]{16,}"),
    "google_key": re.compile(r"AIza[0-9A-Za-z_-]{30,}"),
    "aws_access_key": re.compile(r"AKIA[0-9A-Z]{12,}"),
    "bearer_header": re.compile(r"[Bb]earer\s+[A-Za-z0-9._-]{20,}"),
    "jwt": re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"),
    "private_key_block": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
}


def credential_findings(text: str) -> list[tuple[str, str]]:
    return [(name, match.group(0))
            for name, pattern in CREDENTIAL_PATTERNS.items()
            for match in pattern.finditer(text)]


class _Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        self.now += 1.0
        return self.now


def _bound_fields() -> BoundFields:
    return BoundFields(
        bound_applied=True, bound_in_force=64, unit=UNIT_TOKENS,
        byte_proxy=False, full_size=4, admitted=4,
        disposition=DISPOSITION_RETAINED, tokenizer_name="stub")


def build_stream(session_id: str = SESSION, *, body: str = "ok") -> EventStream:
    """A session that really did carry opaque provider state.

    The turn holds `OPAQUE_STATE`, so the assertions below about the state not
    being readable are made over a stream that had state to leak. A stream
    built with `provider_state=None` would pass every one of them and measure
    nothing.
    """
    stream = EventStream(session_id, clock=_Clock())
    stream.start()
    stream.turn_started(0)
    call = ToolCall(index=0, call_id="call-a", name="run_command",
                    arguments={"command": "env"})
    stream.tool_started(0, call)
    stream.tool_finished(
        0,
        ToolResult(call=call, outcome=OUTCOME_OK, body=body,
                   started_at=1.0, finished_at=2.0),
        _bound_fields())
    stream.turn_completed(TurnRecord(
        turn_index=0, provider="anthropic", provider_state=OPAQUE_STATE,
        tool_calls=(call,), tool_results=(), text="finished", at=3.0))
    stream.end(EndOfRun(session_id=session_id, reason=REASON_COMPLETED, at=4.0))
    return stream


class _Server:
    def __init__(self, registry: Registry) -> None:
        self.http = serving.build_server(registry, host="127.0.0.1", port=0)
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()

    @property
    def base(self) -> str:
        host, port = self.http.server_address[:2]
        return f"http://{host}:{port}"

    def get(self, path: str) -> tuple[int, bytes]:
        try:
            with urllib.request.urlopen(self.base + path, timeout=10) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as failure:
            return failure.code, failure.read()

    def close(self) -> None:
        self.http.shutdown()
        self.http.server_close()
        self.thread.join(timeout=5)


def _serve(view: SessionView) -> _Server:
    registry = Registry()
    registry.register(view)
    return _Server(registry)


def _view(session_id: str = SESSION, **kwargs) -> SessionView:
    return SessionView(
        session_id=session_id,
        stream=build_stream(session_id, **kwargs),
        result=Result(VerificationOutcome.NOT_VERIFIABLE, payload={"answer": 41},
                      reason="no derived contract covers this operation"))


def parse_frames(body: bytes) -> list[dict]:
    """**The persistence boundary.** Everything asserted comes back through here.

    Nothing in this module reads a `SessionEvent`. The objects are correct by
    construction — that is what `EventError` is for — and the question this
    file asks is what reached the wire.
    """
    frames = []
    for block in body.decode("utf-8").split("\n\n"):
        if not block.strip():
            continue
        fields = dict(line.partition(": ")[::2] for line in block.split("\n"))
        frames.append({"event": fields["event"],
                       "data": json.loads(fields["data"])})
    return frames


@pytest.fixture()
def wire() -> list[dict]:
    """The reconstructed stream, and proof that it is not empty."""
    server = _serve(_view())
    try:
        status, body = server.get(f"/sessions/{SESSION}/events")
    finally:
        server.close()
    assert status == 200
    frames = parse_frames(body)
    assert len(frames) == 6, (
        f"the stream carried {len(frames)} frames; every assertion in this "
        "file would be vacuous over a short one"
    )
    return frames


# -- the control -------------------------------------------------------------

def test_the_scanner_catches_a_planted_credential() -> None:
    """Without this, every "no findings" below passes for a plaintext surface."""
    for sample in (
        TEST_CREDENTIAL,
        "sk-ant-api03-abcdefghijklmnopqrst",
        "AIzaSyA0123456789abcdefghijklmnopqrstu",
        "AKIAIOSFODNN7EXAMPLE",
        "Authorization: Bearer abcdefghijklmnopqrstuvwxyz012345",
        "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abcdefghijk",
        "-----BEGIN RSA PRIVATE KEY-----",
    ):
        assert credential_findings(sample), f"the scanner misses {sample[:20]!r}"
    assert not credential_findings("an ordinary session event payload")


# -- FR-036 ------------------------------------------------------------------

def test_no_credential_shaped_value_reaches_the_wire(wire) -> None:
    findings = credential_findings(json.dumps(wire))
    assert not findings, f"credential-shaped values on the event stream: {findings}"


#: The FR-036 guard's own wording, and **matched on rather than on `"Secret"`.**
#: The removal harness found the difference: `src/contracts/canonical.py` also
#: refuses a `Secret` — with a message about key order that happens to contain
#: the word — so an assertion on `"Secret"` passed with the FR-036 walk deleted.
#: A test that cannot tell which of two guards fired is not evidence about
#: either, and the serializer's refusal is incidental: it is about canonical
#: form and would not survive the type acquiring one.
FR036_REFUSAL = "must not reach"


def test_a_secret_cannot_be_placed_on_an_event_at_all() -> None:
    """The structural half, over every field of the event and at three depths.

    Named "at all" and checked that way. `tests/contract/test_trace_redaction.py`
    records what happens otherwise: a guard that scanned one field under a test
    whose name claimed the type.
    """
    def secret() -> Secret:
        return Secret(TEST_CREDENTIAL, name="F2A_MODEL_KEY")

    stream = EventStream(SESSION, clock=_Clock())
    stream.start()

    with pytest.raises(EventError, match=FR036_REFUSAL):
        stream.emit(events.KIND_TURN_STARTED, auth=secret())
    with pytest.raises(EventError, match=FR036_REFUSAL):
        stream.emit(events.KIND_TURN_STARTED,
                    request={"headers": {"authorization": secret()}})
    with pytest.raises(EventError, match=FR036_REFUSAL):
        stream.emit(events.KIND_TURN_STARTED, chain=[{"auth": secret()}])
    with pytest.raises(EventError, match=FR036_REFUSAL):
        stream.emit(events.KIND_TURN_STARTED, **{"a-key": secret()})

    # The fields beside `data`, which a `data`-only guard would walk past.
    with pytest.raises(EventError, match=FR036_REFUSAL):
        events.SessionEvent(kind=events.KIND_TURN_STARTED, session_id=secret(),
                            sequence=0, at=1.0)
    with pytest.raises(EventError, match=FR036_REFUSAL):
        events.SessionEvent(kind=secret(), session_id=SESSION, sequence=0,
                            at=1.0)

    assert len(stream.events) == 1, "a refused event was recorded anyway"


def test_a_secret_used_as_a_mapping_key_is_refused() -> None:
    """The half of the descent a values-only walk silently skips.

    `{Secret(...): "x"}` is a credential in the record exactly as much as
    `{"x": Secret(...)}` is, and it is the shape a walk written as
    `for v in mapping.values()` walks straight past. Kept separate from the
    depth cases above so a proof that removes the key descent has a test that
    can only fail for that reason.
    """
    secret = Secret(TEST_CREDENTIAL, name="F2A_MODEL_KEY")
    stream = EventStream(SESSION, clock=_Clock())
    stream.start()

    with pytest.raises(EventError, match=FR036_REFUSAL):
        stream.emit(events.KIND_TURN_STARTED, headers={secret: "bearer"})
    with pytest.raises(EventError, match=FR036_REFUSAL):
        stream.emit(events.KIND_TURN_STARTED,
                    request={"headers": {secret: "bearer"}})

    assert len(stream.events) == 1, "a refused event was recorded anyway"

    # The same mapping without the key is admitted, so the refusal above is
    # about the key rather than about mappings.
    stream.emit(events.KIND_TURN_STARTED, headers={"authorization": "bearer"})
    assert len(stream.events) == 2


def test_a_bare_credential_string_would_be_caught_by_the_scan() -> None:
    """The residual case, and the proof the scan reads the right artifact.

    Nothing structurally stops a caller putting a credential into a tool body —
    a `str` is a `str`. This asserts that when one does reach the wire the scan
    above is what sees it, rather than the scan being pointed somewhere the
    payload never goes.
    """
    server = _serve(_view(body=f"AWS_SECRET={TEST_CREDENTIAL}"))
    try:
        _, body = server.get(f"/sessions/{SESSION}/events")
    finally:
        server.close()
    assert credential_findings(json.dumps(parse_frames(body))), (
        "a credential in a tool body did not reach the wire, so "
        "test_no_credential_shaped_value_reaches_the_wire is scanning an "
        "artifact the payload never enters"
    )


# -- FR-037 ------------------------------------------------------------------

def test_the_opaque_state_is_on_the_stream_only_as_a_digest(wire) -> None:
    """The claim, and the evidence that there was something to claim it about.

    Two halves. The **digest is present**, which is what makes the run one that
    carried opaque state at all; and the **payload is absent**, in every
    encoding a byte string could have reached the wire in.
    """
    completed = [f for f in wire if f["event"] == events.KIND_TURN_COMPLETED]
    assert len(completed) == 1
    turn = completed[0]["data"]["data"]["turn"]

    assert turn["provider_state_digest"] == state_digest(OPAQUE_STATE), (
        "the turn frame carries no state digest, so this test cannot "
        "distinguish a redacted stream from a session that had no state"
    )
    assert "provider_state" not in turn, (
        "the event stream carries provider_state itself. FR-037 makes it "
        "opaque; carry the digest."
    )

    rendered = json.dumps(wire)
    for encoding in (
        OPAQUE_STATE.decode("latin-1"),
        OPAQUE_STATE.hex(),
        repr(OPAQUE_STATE),
        "thinking-signature-payload",
    ):
        assert encoding not in rendered, (
            f"the opaque payload reached the wire as {encoding[:24]!r}. A "
            "reader who can read it will parse it, and the provider's next "
            "format change becomes a break in this system."
        )


def test_raw_bytes_cannot_be_placed_on_an_event() -> None:
    """The structural half of FR-037, derived from the type rather than a name.

    A key check would be defeated by a rename; `provider_state` is `bytes` by
    type, and `src/runtime/turn.py::state_digest` is the only form of it that
    may reach a record. So the refusal is on the type, at every depth an event
    can nest to.
    """
    stream = EventStream(SESSION, clock=_Clock())
    stream.start()
    for payload in (
        {"provider_state": OPAQUE_STATE},
        {"renamed_entirely": OPAQUE_STATE},
        {"turn": {"state": OPAQUE_STATE}},
        {"turns": [{"state": OPAQUE_STATE}]},
    ):
        with pytest.raises(EventError, match="FR-037"):
            stream.emit(events.KIND_TURN_STARTED, **payload)
    assert len(stream.events) == 1

    # And the permitted form goes through, so the refusal above is a rule about
    # bytes rather than a module that refuses everything.
    stream.emit(events.KIND_TURN_STARTED,
                provider_state_digest=state_digest(OPAQUE_STATE))
    assert len(stream.events) == 2


# -- error bodies are part of the redaction surface --------------------------

def test_a_refusal_does_not_echo_what_the_caller_put_in_the_path() -> None:
    """`src/proxy/rules.go`'s precedent: a client-visible error body is a
    surface. The session identifier is a path segment, so a 404 rendered with
    the path in it publishes whatever the caller sent — and a caller who sends
    a credential by mistake gets it back in a body that is logged at both ends.
    """
    server = _serve(_view())
    try:
        status, body = server.get(f"/sessions/{TEST_CREDENTIAL}/events")
        route_status, route_body = server.get(f"/{TEST_CREDENTIAL}/nope")
    finally:
        server.close()

    assert status == 404 and route_status == 404
    for label, refused in (("session", body), ("route", route_body)):
        assert TEST_CREDENTIAL.encode() not in refused, (
            f"the {label} refusal echoes the path back to the caller"
        )
        assert not credential_findings(refused.decode()), (
            f"credential-shaped value in the {label} refusal body"
        )
        parsed = json.loads(refused)
        assert parsed["rule_id"] and parsed["reason"], (
            "the refusal carries no rule identifier, so this test asserted "
            "the absence of a credential in a body that says nothing at all"
        )


def test_the_refusal_body_is_composed_only_from_the_registry() -> None:
    """Why the test above holds rather than happens to hold.

    A body assembled from a format string over the request would pass the
    assertion above on the day it was written and fail on the first refusal
    someone added a detail to. This asserts the mechanism: the bytes are a
    function of the rule identifier alone.
    """
    for rule_id in serving.REFUSALS:
        first = serving.refusal_body(rule_id)
        assert serving.refusal_body(rule_id) == first
        assert json.loads(first)["rule_id"] == rule_id
    with pytest.raises(serving.SurfaceError):
        serving.refusal_body("SV-NOT-A-RULE")


def test_the_result_endpoint_is_scanned_too(wire) -> None:
    """The stream is not the only thing this surface serves.

    `wire` is requested so this test runs against a session whose stream was
    non-empty; the assertion is over the other endpoint, which carries the
    caller-visible result record and has the same obligation.
    """
    server = _serve(_view())
    try:
        status, body = server.get(f"/sessions/{SESSION}/result")
    finally:
        server.close()
    assert status == 200
    record = json.loads(body)
    assert record["session_id"] == SESSION, "scanned the wrong session"
    assert not credential_findings(body.decode())
    assert "provider_state" not in body.decode()
