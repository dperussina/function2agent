"""T069 — the caller-visible session event stream (T-03, **OD-15**).

**Why this module exists at all.** T-03 decided v1 owns a thin operator-facing
HTTP/SSE surface and wrote that it would carry *"the caller-visible result
record and the session event stream"*. It assumed the stream was the removed
dependency's. **OD-15** removed the dependency and nothing replaced the stream,
so T-03's surface had one of its two halves supplied by nothing. This is that
half.

## The event stream is not the trace, and the distinction is load-bearing

`src/runtime/trace.py` writes FR-038's spans into a `Repository`. It is the
**machine-readable audit channel**: seven kinds, a closed set, `SpanError`
refusing anything else, positions that order a session totally, artifact
versions, four cost totals and a rule identifier on every decision. Its reader
is an operator reconstructing what happened after the fact.

This is the **caller-visible** channel. Its reader is whoever asked for the run
and is watching it happen. The two have different readers and different
obligations, and **neither is the other's transport**:

- **The kinds below are not span kinds and adding one here adds none.** FR-038's
  set is closed at seven, and a prior pass declined to add a kind on exactly that
  ground. The names here are deliberately *not* `model_call` and `tool_call`, so
  that a reader who sees `tool_started` cannot mistake this enumeration for
  FR-038's.
- **Nothing here is persisted.** A stream lives as long as the session does. The
  audit record is the trace, and a caller who missed an event reads the trace.
- **The trace carries what an attribution needs; this carries what a caller
  needs.** No artifact versions, no rule identifiers, no cost totals — those are
  attribution fields, and a caller-visible channel that carried them would be a
  second, unindexed, unbounded copy of the audit record.

## FR-058 is not applied here, and the reading is stated rather than assumed

FR-058 bounds *"every result either of FR-004's capabilities returns to the
agent … **before it enters the model's context**"*, and the resource it names is
the context window. Its three obligations are addressed to three places, and
**none of them is this one**: the bound is applied where the result is produced
(`AgentLoop._bounded_body`), the disclosure goes *"in the result the model
reads"*, and the field obligation is *"on the `tool_call` span of FR-038"*. The
event stream is a **third reader** that the requirement does not name.

So the bound does not reach here by force of FR-058. **What reaches here is the
bounded object**: `AgentLoop._bounded_body` replaces the body before anything
downstream sees it, so `ToolResult.body` on the record this module renders is
already `BoundedResult.text`. That is transitive, not an additional obligation
discharged, and this docstring says so rather than letting a later reader infer
FR-058 was satisfied here.

**One thing is taken by analogy and is marked as an analogy, not as a
requirement.** `tool_finished` **requires** the `BoundFields`, so a caller
reading a bounded preview always has the disclosure beside it. FR-058's second
obligation — *"a bounded result that reads as a complete one MUST NOT be
produced"* — is written about the model, but the failure it describes is a
property of the reader and not of the model: an answer composed from a silently
shortened result is a wrong answer carrying no signal that it is one, and a
caller composes answers too. Taking it costs one required argument. Not taking
it would have made the stream the one channel where a truncation is invisible.

## Three refusals, all at construction and all derived from the type

1. **FR-036 — no `Secret`, anywhere.** Through
   `src/contracts/secret.py::refuse_secrets`, over `dataclasses.fields(event)`
   rather than over a list of field names, so a field added later is scanned
   because nobody had to remember anything.
2. **FR-037 — no raw `bytes`, anywhere.** `provider_state` is `bytes` by type
   and `src/runtime/turn.py::state_digest` is the only form of it that may reach
   a record. The refusal is therefore on the **type** and not on the key name: a
   key check is defeated by a rename, and the rename is what an author does when
   a guard is in the way.
3. **Renderable, now rather than at the surface.** Every event is put through
   the canonical serializer at construction. An event that cannot be rendered is
   refused before it is recorded, on `trace.py`'s argument that *"a span that
   was written and then found invalid has already been written"* — here the
   equivalent is worse, because the failure would surface as a half-written
   response to a caller who is already reading.

## The stream has a beginning and an end, and neither can be faked by omission

`EndOfRun`'s rule, one channel over. T066 records why: the removed dependency's
end-of-run marker sat behind a default-off flag, so *absence* was ambiguous
between *this run did not end* and *nobody turned the marker on*.

- **`run_ended` is the only kind that closes a stream and it requires an
  `EndOfRun`.** There is no value of any field that lets an un-ended run look
  finished, because the kind that says a run ended is the kind that cannot be
  built without the marker.
- **`session_started` must be first.** The same failure at the other end: a
  caller attaching to a stream whose first event is `turn_started` cannot tell
  it from a session that had no earlier turns.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field, fields
from typing import Any, Callable, Mapping

from src.contracts.canonical import NonCanonicalValue, dumps
from src.contracts.secret import refuse_secrets
from src.runtime.dispatch import ToolCall, ToolResult
from src.runtime.result_bound import BoundFields
from src.runtime.signals import EndOfRun
from src.runtime.turn import TurnRecord

#: The closed set. **These are not FR-038's span kinds** — see the module
#: docstring. The names differ from the span kinds on purpose.
KIND_SESSION_STARTED = "session_started"
KIND_TURN_STARTED = "turn_started"
KIND_TOOL_STARTED = "tool_started"
KIND_TOOL_FINISHED = "tool_finished"
KIND_TURN_COMPLETED = "turn_completed"
KIND_RUN_ENDED = "run_ended"

KINDS: tuple[str, ...] = (
    KIND_SESSION_STARTED, KIND_TURN_STARTED, KIND_TOOL_STARTED,
    KIND_TOOL_FINISHED, KIND_TURN_COMPLETED, KIND_RUN_ENDED,
)

#: The one kind that ends a stream. Held as a name rather than compared inline
#: so that "which kind closes the stream" has one answer in one place.
TERMINAL_KIND = KIND_RUN_ENDED


class EventError(ValueError):
    """An event that must not reach a caller as described."""


@dataclass(frozen=True)
class SessionEvent:
    """One caller-visible event.

    `sequence` is the position and it is what orders the stream. Not `at`: a
    timestamp is data, two events in one clock tick tie, and FR-038 takes the
    same reading for a span's ordinal one channel over.
    """

    kind: str
    session_id: str
    sequence: int
    at: float
    data: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # FR-036 first and over every field, on `trace.py`'s ordering argument:
        # an event with a credential in `data` and a misspelled `kind` is a
        # credential, and reporting it as the typo would be the wrong finding.
        # Both walks enumerate `dataclasses.fields` rather than naming `data`.
        # Only `data` can plausibly hold either today — but that is a fact
        # about today's field list, and `trace.py`'s guard narrowed to exactly
        # one field for exactly that reason and stayed narrow through five
        # more fields arriving.
        for member in fields(self):
            value = getattr(self, member.name)
            refuse_secrets(value, member.name, raise_as=EventError,
                           destination="a caller-visible event stream")
            _refuse_opaque_bytes(value, member.name)

        if self.kind not in KINDS:
            raise EventError(
                f"{self.kind!r} is not one of this stream's declared event "
                f"kinds ({list(KINDS)}). This set is the caller-visible "
                "stream's and is **not** FR-038's seven span kinds; adding a "
                "kind here adds no span kind, and adding one there adds none "
                "here."
            )
        if not self.session_id:
            raise EventError("an event belongs to a session or to nothing")
        if self.sequence < 0:
            raise EventError("sequence is a position, not a counter")

        # Renderable now rather than at the surface. See the module docstring.
        try:
            dumps(self.to_record())
        except NonCanonicalValue as exc:
            raise EventError(
                f"a {self.kind} event holds a value with no canonical form "
                f"({exc}). Refused here rather than at the surface: a caller "
                "is already reading by then, and the failure arrives as a "
                "half-written response."
            ) from None

    @property
    def position(self) -> tuple[str, int]:
        """Total order within a session, with no clock in it."""
        return (self.session_id, self.sequence)

    def to_record(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "session_id": self.session_id,
            "sequence": self.sequence,
            "at": self.at,
            "data": dict(self.data),
        }

    def encode(self) -> bytes:
        """The canonical bytes. **The only form that crosses a boundary.**

        Canonical rather than `json.dumps` for two reasons, and the second is
        the one that matters here. Sorted keys make a frame comparable across
        two runs; and `src/contracts/canonical.py::_string` escapes every
        control character, so a newline inside a payload cannot terminate an
        SSE `data:` line early. That framing hazard is invisible in review —
        no ordinary payload contains a newline — and it splits one event into
        two, the second of which is unparseable.
        """
        return dumps(self.to_record())


def _refuse_opaque_bytes(value: Any, path: str) -> None:
    """FR-037: opaque provider state is a digest here or it is nothing.

    On the **type**, not on the key name. `provider_state` is `bytes` by type
    (`src/runtime/turn.py::ModelResponse`), a key check is defeated by a rename,
    and there is no other legitimate reason for a byte string to be on a
    caller-visible event: everything else the stream carries is text, a number
    or a structure of those.
    """
    if isinstance(value, (bytes, bytearray, memoryview)):
        raise EventError(
            f"{path} holds {len(bytes(value))} raw bytes. FR-037 makes "
            "provider continuation state opaque and "
            "`src/runtime/turn.py::state_digest` is the only form of it that "
            "may reach a record — a reader who can read it will parse it, and "
            "the provider's next format change becomes a break in this "
            "system. Nothing else on this stream is bytes."
        )
    if isinstance(value, Mapping):
        for key, item in value.items():
            _refuse_opaque_bytes(key, f"{path}.<key>")
            _refuse_opaque_bytes(item, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for item in value:
            _refuse_opaque_bytes(item, f"{path}[]")


class EventStream:
    """One session's events, emitted live and replayable.

    **Both, rather than one.** A stream that only accumulated would make the
    HTTP surface a poll, which is the thing SSE exists not to be; a stream that
    only pushed would give a caller who attached late nothing at all. So
    subscribers see each event as it is emitted and `events` holds the same
    tuple, and `tests/contract/test_serving_surface.py` asserts the two agree —
    two renderings of one sequence are two chances for one of them to be the
    one a caller actually gets.

    Thread-safe because the loop emits from whichever thread ran the turn and
    the surface reads from the one serving the request.
    """

    __slots__ = ("session_id", "_clock", "_lock", "_events", "_sinks", "_closed")

    def __init__(self, session_id: str, *, clock: Callable[[], float]) -> None:
        if not session_id:
            raise EventError("a stream belongs to a session or to nothing")
        self.session_id = session_id
        self._clock = clock
        self._lock = threading.Lock()
        self._events: list[SessionEvent] = []
        self._sinks: list[Callable[[SessionEvent], None]] = []
        self._closed = False

    # -- state ---------------------------------------------------------------

    @property
    def events(self) -> tuple[SessionEvent, ...]:
        with self._lock:
            return tuple(self._events)

    @property
    def opened(self) -> bool:
        return bool(self._events)

    @property
    def closed(self) -> bool:
        return self._closed

    def subscribe(self, sink: Callable[[SessionEvent], None]) -> None:
        with self._lock:
            self._sinks.append(sink)

    # -- emission ------------------------------------------------------------

    def emit(self, kind: str, **data: Any) -> SessionEvent:
        """Append one event and hand it to every subscriber.

        The two ordering rules live here rather than at each call site, so that
        a helper added later cannot be the one that skips them.
        """
        if kind == TERMINAL_KIND and "end_of_run" not in data:
            raise EventError(
                "a run_ended event is built from an EndOfRun marker, through "
                "`end()`. T066's rule: there is no value of any field that "
                "lets an un-ended run report a terminal state, so the kind "
                "that says a run ended cannot be built without the marker."
            )
        with self._lock:
            if self._closed:
                raise EventError(
                    f"session {self.session_id} has ended; a {kind!r} event "
                    "after the end-of-run marker would put a run that "
                    "finished back into progress on the one channel a caller "
                    "is watching."
                )
            if not self._events and kind != KIND_SESSION_STARTED:
                raise EventError(
                    f"the first event on a stream is {KIND_SESSION_STARTED!r}, "
                    f"not {kind!r}. A stream that begins mid-run reads to a "
                    "caller exactly like a session that had no earlier turns."
                )
            if self._events and kind == KIND_SESSION_STARTED:
                raise EventError(
                    f"session {self.session_id} has already started; a second "
                    "start would restart a run in the caller's view without "
                    "one having happened."
                )
            event = SessionEvent(
                kind=kind, session_id=self.session_id,
                sequence=len(self._events), at=self._clock(),
                data=dict(data))
            self._events.append(event)
            if kind == TERMINAL_KIND:
                self._closed = True
            sinks = list(self._sinks)
        for sink in sinks:
            sink(event)
        return event

    # -- the shapes the runtime already produces -----------------------------

    def start(self) -> SessionEvent:
        return self.emit(KIND_SESSION_STARTED)

    def turn_started(self, turn_index: int) -> SessionEvent:
        return self.emit(KIND_TURN_STARTED, turn_index=turn_index)

    def tool_started(self, turn_index: int, call: ToolCall) -> SessionEvent:
        """The call as the provider declared it, arguments included.

        `index` travels because it is the provider's declared position and the
        ordering key everything downstream uses (T-08); a caller shown the
        arrival order would be shown something this system deliberately does
        not record.
        """
        return self.emit(
            KIND_TOOL_STARTED, turn_index=turn_index, index=call.index,
            call_id=call.call_id, name=call.name,
            arguments=dict(call.arguments))

    def tool_finished(
        self, turn_index: int, result: ToolResult, bound: BoundFields
    ) -> SessionEvent:
        """`bound` is required. See the module docstring for why, and for the
        fact that this is an analogy to FR-058's second obligation rather than
        FR-058 binding on this channel."""
        return self.emit(
            KIND_TOOL_FINISHED, turn_index=turn_index, index=result.index,
            call_id=result.call.call_id, name=result.call.name,
            outcome=result.outcome, body=result.body,
            duration_seconds=result.duration_seconds,
            bound=bound.to_record())

    def turn_completed(self, record: TurnRecord) -> SessionEvent:
        """**Through `TurnRecord.to_record()`, which omits the opaque state by
        construction rather than by redacting it.**

        Its own docstring gives the reason and it is the reason this method
        does not build a dict of its own: *"not redacted on the way out —
        absent. A field that is present and emptied is one somebody later fills
        in."* A second rendering here would be a second chance to include it.
        """
        return self.emit(KIND_TURN_COMPLETED, turn=record.to_record())

    def end(self, marker: EndOfRun) -> SessionEvent:
        """The last event. `terminal_state` rides on the marker, never beside it.

        `EndOfRun.to_record()` already carries the reason, the taxonomy member,
        and the error identity or exhaustion cause where there is one. Copying
        the terminal state out alongside would be one figure recorded twice
        with nothing keeping the two equal — the argument T067 makes for not
        putting a second reading beside `no_progress`.
        """
        if marker.session_id != self.session_id:
            raise EventError(
                f"the marker ends {marker.session_id!r} and this stream is "
                f"{self.session_id!r}. One run's end on another run's channel "
                "is a completion a caller would read as their own."
            )
        return self.emit(KIND_RUN_ENDED, end_of_run=marker.to_record())
