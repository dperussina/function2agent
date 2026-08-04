"""T043 — the parallel tool-call dispatcher (T-08, FR-007, data-model.md §2.2).

Executes a turn's tool calls concurrently and records them in the **provider's
declared index order**, never in completion order.

**Why this is in a v1 that emits no graph.** Finding 006 measured fan-out
producing 5 distinct orderings in 8 runs under overlapping latencies. That was
read as a property of a graph runtime. It is not: every provider in SC-010's
set can emit several tool calls in one turn, so a single-agent loop fans out
whether or not it has a graph. FR-007 requires work performed in parallel to be
ordered deterministically **before it is recorded**, and the only order
available that does not depend on how long a call took is the one the provider
declared.

**Recording is in-order and eager, not in-order and deferred.** Results are
emitted through `record` as soon as the longest completed *prefix* extends —
a reorder buffer, not a barrier. Waiting for the whole fan-out before recording
anything would be simpler and would lose every completed call to a `SIGKILL`
mid-fan-out, which is the accounting failure U-30 and finding 006 both name.

**A branch that raises is an outcome, not an exception.** A raise propagating
out of the dispatcher would abandon the results of the branches that
succeeded — the same loss, arriving by a different door. So a failing branch
becomes a `ToolResult` with the `upstream_fault` outcome and a body naming what
went wrong, and it occupies its declared position like any other.
"""

from __future__ import annotations

import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

from src.runtime.trace import OUTCOME_OK, OUTCOME_UPSTREAM_FAULT


class DispatchError(RuntimeError):
    """A fan-out that cannot be dispatched as described."""


class DeclaredOrderError(DispatchError):
    """The provider's declared indexes do not form a total order.

    Raised rather than repaired. A gap or a duplicate means the recording order
    FR-007 requires is not recoverable from the call set, and picking one
    silently would reintroduce exactly the nondeterminism this module exists to
    remove.
    """


@dataclass(frozen=True)
class ToolCall:
    """One call as the provider declared it.

    `index` is the provider's own position in the turn and is the ordering key
    everything downstream uses. It is not our arrival order, not the order the
    calls finished in, and not a list position we assigned — `data-model.md`
    §2.2 says `tool_calls[]` is *in the provider's declared index order*, and a
    field that is only sometimes the provider's would be worse than none.
    """

    index: int
    call_id: str
    name: str
    arguments: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.index < 0:
            raise DeclaredOrderError(
                f"declared index {self.index} is negative; an index is a "
                "position in the turn"
            )
        if not self.call_id:
            raise DispatchError(
                "a tool call needs the provider's own call identity. Without "
                "it a result cannot be attributed back to the call the "
                "provider will expect it for."
            )
        if not self.name:
            raise DispatchError("a tool call needs the name of what to call")


@dataclass(frozen=True)
class ToolResult:
    """One call's outcome, at its declared position.

    `outcome` is drawn from FR-038's declared set rather than being a boolean,
    because the same set is what the `tool_call` span carries and a second
    vocabulary would have to be translated at the one place a mistranslation is
    invisible.
    """

    call: ToolCall
    outcome: str
    body: str
    started_at: float
    finished_at: float
    writes: Mapping[str, Any] = field(default_factory=dict)

    @property
    def index(self) -> int:
        return self.call.index

    @property
    def duration_seconds(self) -> float:
        return self.finished_at - self.started_at


@dataclass(frozen=True)
class DispatchOutcome:
    """The fan-out's results, plus the order they actually finished in.

    **`completion_order` is not diagnostics.** A test asserting that recording
    followed declared order is vacuous on any run where the two orders happened
    to coincide, and coincidence is the common case — which is why a fan-out
    ordering defect survives review. Exposing the completion order lets a test
    assert that this run could tell the two apart before asserting which one
    was used.
    """

    results: tuple[ToolResult, ...]
    completion_order: tuple[int, ...]

    @property
    def declared_order(self) -> tuple[int, ...]:
        return tuple(r.index for r in self.results)


def assert_declared_order(calls: Sequence[ToolCall]) -> None:
    """The declared indexes must be dense `0..n-1` and unique.

    Dense rather than merely sorted: a provider that emitted indexes 0 and 2
    has either dropped a call or is numbering something other than positions in
    this turn, and both are worth stopping for. `data-model.md` §2.2 makes
    `turn_index` "dense and monotonic" for the same reason one level up.
    """
    indexes = [call.index for call in calls]
    if len(set(indexes)) != len(indexes):
        duplicated = sorted({i for i in indexes if indexes.count(i) > 1})
        raise DeclaredOrderError(
            f"declared indexes repeat {duplicated}. Two calls at one position "
            "is a tie, and a tie is resolved by whichever finished first — "
            "which is the completion order T-08 forbids recording in."
        )
    if sorted(indexes) != list(range(len(indexes))):
        raise DeclaredOrderError(
            f"declared indexes {sorted(indexes)} are not dense over "
            f"0..{len(indexes) - 1}. A gap means a call was dropped or the "
            "indexes are not positions in this turn; either way the declared "
            "order FR-007 requires cannot be recovered from them."
        )


def dispatch(
    calls: Sequence[ToolCall],
    execute: Callable[[ToolCall], str],
    *,
    record: Callable[[ToolResult], None],
    max_workers: int | None = None,
    now: Callable[[], float] = time.monotonic,
) -> DispatchOutcome:
    """Run `calls` concurrently; record them in declared index order.

    `record` is called exactly once per call, in declared index order, and is
    called for a failing branch too. A recorder that raises is not caught: it
    is the journal, and a journal that failed to record a step is not something
    to carry on past.
    """
    calls = tuple(calls)
    assert_declared_order(calls)
    if not calls:
        return DispatchOutcome(results=(), completion_order=())

    by_index = {call.index: call for call in calls}
    completion: list[int] = []
    done: dict[int, ToolResult] = {}

    workers = len(calls) if max_workers is None else max_workers
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures: dict[Future[ToolResult], int] = {
            pool.submit(_run_one, by_index[index], execute, now): index
            for index in sorted(by_index)
        }
        # `as_completed` is deliberately not used: the emitted prefix has to
        # advance as results land, and the loop below is what makes recording
        # eager without making it completion-ordered.
        next_to_record = 0
        for future in _as_they_finish(futures):
            index = futures[future]
            completion.append(index)
            done[index] = future.result()
            while next_to_record in done:
                record(done[next_to_record])
                next_to_record += 1

    results = tuple(done[index] for index in range(len(calls)))
    return DispatchOutcome(results=results, completion_order=tuple(completion))


def _as_they_finish(futures: Mapping[Future[ToolResult], int]):
    """`concurrent.futures.as_completed`, named so the intent is greppable."""
    from concurrent.futures import as_completed

    return as_completed(list(futures))


def _run_one(
    call: ToolCall,
    execute: Callable[[ToolCall], str],
    now: Callable[[], float],
) -> ToolResult:
    """Execute one branch, turning a raise into a typed outcome.

    The exception text is carried in the body rather than discarded, because
    FR-011's reason clause — a denial legible enough for the agent to find a
    safer path — has the same shape here: an agent told only that a call failed
    retries the identical call.
    """
    started = now()
    try:
        body = execute(call)
    except Exception as exc:  # noqa: BLE001 — a branch fault is an outcome
        return ToolResult(
            call=call,
            outcome=OUTCOME_UPSTREAM_FAULT,
            body=f"{type(exc).__name__}: {exc}",
            started_at=started,
            finished_at=now(),
        )
    if isinstance(body, ToolResult):
        # An executor that already built the result — the FR-058 path does,
        # because bounding a result is part of producing it.
        return body
    return ToolResult(
        call=call,
        outcome=OUTCOME_OK,
        body=body,
        started_at=started,
        finished_at=now(),
    )
