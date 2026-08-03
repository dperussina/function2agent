"""Shared four-node ADK graph with a deliberate non-termination trap.

Topology (one cycle, four nodes):

    START -> seed -> work -> check
                      ^        |
                      +--again-+        <- the trap: `check` always routes "again"
                               |
                               +--done--> finish   (unreachable while trapped)

`work` and `check` are pure Python function nodes, so the trap is deterministic and
costs nothing. A separate LLM-backed variant lives in e6_budget.py, because the only
runtime-enforced ceiling ADK exposes counts LLM calls rather than graph steps.
"""
from __future__ import annotations

from google.adk import Event, Workflow

# Execution ledger. Every node append is the programmatic evidence for the
# verdicts; nothing is decided by reading model prose.
TRACE: list[str] = []
COUNTERS = {"work": 0, "check": 0, "seed": 0, "finish": 0}
STOP_AFTER: int | None = None  # when set, `check` routes "done" after N iterations


def reset(stop_after: int | None = None) -> None:
    global STOP_AFTER
    TRACE.clear()
    for k in COUNTERS:
        COUNTERS[k] = 0
    STOP_AFTER = stop_after


def seed(node_input: str):
    COUNTERS["seed"] += 1
    TRACE.append("seed")
    yield Event(state={"iterations": 0, "topic": node_input})


def work(ctx):
    COUNTERS["work"] += 1
    n = ctx.state.get("iterations", 0) + 1
    TRACE.append(f"work:{n}")
    ctx.state["iterations"] = n
    return f"work-{n}"


def check(ctx):
    COUNTERS["check"] += 1
    n = ctx.state.get("iterations", 0)
    TRACE.append(f"check:{n}")
    if STOP_AFTER is not None and n >= STOP_AFTER:
        yield Event(route="done")
    else:
        # The trap. Nothing here ever terminates on its own.
        yield Event(route="again")


def finish(ctx):
    COUNTERS["finish"] += 1
    TRACE.append("finish")
    return f"finished after {ctx.state.get('iterations', 0)} iterations"


def build() -> Workflow:
    return Workflow(
        name="e6_trap",
        edges=[
            ("START", seed, work, check),
            (check, {"again": work, "done": finish}),
        ],
    )
