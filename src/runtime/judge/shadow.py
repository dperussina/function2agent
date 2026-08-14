"""T173 — shadow judge over the trace stream, never in the request path.

**Requirement**: FR-039. **Boundary**: FR-052, Principle I (success-path
reading). **Ownership**: `judge_verdict` is written by `ROLE_SHADOW_JUDGE`
and read by nobody on the success path — `src/contracts/ownership.py`
declares the empty reader set, and that emptiness is the point.

For every result the verifier evaluates, record a general-purpose-model
judge verdict in shadow over the same trace. The verdict MUST NOT affect
what the caller sees, what the gate permits, or any other behaviour.

## What this is, and what it is not

This is a typed verdict writer driven by an injectable function
(`src/runtime/judge/inject.py`). It is not a live vendor SDK call — T058
is still PARTIAL and `call` still raises `TransportUnavailableError`. It
is not T214: no run produces a `Result`, and this module does not invent
that call site so the judge has a live one. A caller that has a result id
— a test, or T214 when it lands — hands the id in. The join at
`src/runtime/result_join.py` exists; nothing here calls it.

It is not folded into `src/runtime/reports/not_verifiable.py`. That
module reports a share; this one writes a measurement row.

## Asynchronously, and what that word is required to mean

`EventStream.emit` hands each event to subscribers on the emitter's
thread after releasing its lock. A sink that inserted a row would put
the verdict write on the request path: the caller of `emit` would wait
on the store. `attach` therefore only enqueues. `consider` only
enqueues. The insert runs on a worker thread this object owns. The
request path cannot observe the row, because it does not wait for the
queue and it cannot read the table.

Off mode (`decide is None`) starts no thread, subscribes to nothing, and
schedules nothing. That is "not running at all", not a quiet write.

## Why the stream and not the `trace_span` table

`ROLE_SHADOW_JUDGE` is not a declared reader of `trace_span`. Reading
that table from this role would add a success-path-adjacent reader to
the audit store, or add this role to `trace_span`'s reader set. The
in-memory stream is the consumption path that does not cross that map.
"""

from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass
from typing import Callable

from src.contracts.ownership import ROLE_SHADOW_JUDGE
from src.contracts.repository import Repository
from src.runtime.events import EventStream, SessionEvent
from src.runtime.judge.inject import VERDICTS, DecideFn

TABLE = "judge_verdict"

COLUMNS = {
    "result_id": "text not null",
    "session_id": "text not null",
    "verdict": "text not null",
    "event_count": "int not null",
    "at": "real not null",
}


class JudgeError(ValueError):
    """A verdict this writer refuses to schedule or persist."""


@dataclass(frozen=True)
class _EventJob:
    event: SessionEvent


@dataclass(frozen=True)
class _VerdictJob:
    result_id: str
    session_id: str
    verifier_label: str


class _Stop:
    """Queue sentinel. A dedicated type so a job cannot be mistaken for it."""


_STOP = _Stop()


class ShadowJudge:
    """Consumes an event stream off the request path; writes `judge_verdict`.

    Constructed as `ROLE_SHADOW_JUDGE` or refused. The decide function is
    injected: agree, disagree, or `None` for off. T214 residual — no run
    produces a `Result` — is why `consider` takes a result id rather than
    a `Result`.
    """

    def __init__(
        self,
        repository: Repository,
        decide: DecideFn | None,
        *,
        clock: Callable[[], float] | None = None,
    ) -> None:
        if repository.role != ROLE_SHADOW_JUDGE:
            raise JudgeError(
                f"{repository.role!r} may not write {TABLE}; its sole "
                f"writer is {ROLE_SHADOW_JUDGE!r}. The empty reader set "
                "on this table is FR-052: a success-path role that could "
                "open it for write could also open it for read."
            )
        self._repo = repository
        self._decide = decide
        self._clock = clock if clock is not None else time.time
        self._queue: queue.Queue[_EventJob | _VerdictJob | _Stop] = queue.Queue()
        self._seen: list[SessionEvent] = []
        self._thread: threading.Thread | None = None
        self._ensure_schema()
        if self._decide is not None:
            self._thread = threading.Thread(
                target=self._worker,
                name="shadow-judge",
                daemon=True,
            )
            self._thread.start()

    def _ensure_schema(self) -> None:
        self._repo.create_table(
            TABLE, COLUMNS, unique=[("result_id",)],
        )

    def attach(self, stream: EventStream) -> None:
        """Subscribe. The sink only enqueues; it never inserts.

        Off mode does not subscribe. A judge that is not running must not
        sit on the stream.
        """
        if self._decide is None:
            return  # off: the judge does not subscribe
        stream.subscribe(self._enqueue)

    def _enqueue(self, event: SessionEvent) -> None:
        self._queue.put(_EventJob(event))

    def consider(
        self, result_id: str, session_id: str, verifier_label: str,
    ) -> None:
        """Schedule a verdict write keyed to `result_id`. Returns at once.

        The insert happens on the worker, after this returns. The caller
        cannot wait on the verdict: there is no future, no callback into
        the success path, and no read of `judge_verdict` from any role
        that is not this writer.

        T214 residual: no run produces a `Result`. The id is supplied,
        not constructed here, and this module does not import
        `src.contracts.result`.
        """
        if self._decide is None:
            return  # off: the judge does not schedule
        if not result_id:
            raise JudgeError(
                "a verdict is keyed to a result; an empty id keys nothing"
            )
        if not session_id:
            raise JudgeError(
                "a verdict belongs to a session or to nothing"
            )
        if verifier_label not in VERDICTS:
            raise JudgeError(
                f"{verifier_label!r} is not a judge verdict "
                f"({sorted(VERDICTS)}). The judge's vocabulary is not "
                "VerificationOutcome; that type is the success-path record."
            )
        self._queue.put(_VerdictJob(result_id, session_id, verifier_label))

    def wait_idle(self) -> None:
        """Block until the queue is empty. Tests use this; the success path must not."""
        self._queue.join()

    def verdicts(self) -> list[dict[str, object]]:
        """Rows this writer persisted. The writer may read its own table."""
        rows = self._repo.select(TABLE, order_by="at")
        return [dict(row) for row in rows]

    def close(self) -> None:
        if self._thread is None:
            return
        self._queue.put(_STOP)
        self._thread.join(timeout=5.0)
        self._thread = None

    def __enter__(self) -> "ShadowJudge":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def _worker(self) -> None:
        while True:
            item = self._queue.get()
            try:
                if isinstance(item, _Stop):
                    return
                if isinstance(item, _EventJob):
                    self._seen.append(item.event)
                    continue
                self._write_verdict(item)
            finally:
                self._queue.task_done()

    def _write_verdict(self, job: _VerdictJob) -> None:
        if self._decide is None:
            return
        verdict = self._decide(job.verifier_label)
        if verdict not in VERDICTS:
            raise JudgeError(
                f"decide returned {verdict!r}, which is not a judge verdict"
            )
        self._repo.insert(TABLE, {
            "result_id": job.result_id,
            "session_id": job.session_id,
            "verdict": verdict,
            "event_count": len(self._seen),
            "at": self._clock(),
        })
