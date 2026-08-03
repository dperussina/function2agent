"""Primitive 4, harder case: is the trajectory deterministic under fan-out?

The sequential trap has only one possible ordering, so it cannot distinguish "the graph
mechanics are deterministic" from "there was nothing to reorder". This arm fans out to
three concurrent branches with deliberately unequal, jittered durations and fans back
in, then repeats the whole run N times comparing the observed node-completion order.

If ADK's scheduler is deterministic the completion order is identical every run. If it
is completion-order driven, the trace tracks the durations and will vary when the
durations do. Either answer is informative; what matters for replay is knowing which.

Zero model spend.
"""
import asyncio
import json
import random

from google.adk import Event, Workflow
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.runners import InMemoryRunner
from google.genai import types

TRACE = []
RUNS = 8


def fan(node_input: str):
    TRACE.append("fan")
    yield Event(state={"seed": node_input})


def _branch(name, delay):
    async def b(ctx):
        await asyncio.sleep(delay + random.uniform(0, 0.05))
        TRACE.append(name)
        return name
    b.__name__ = name
    return b


slow = _branch("slow", 0.10 + random.uniform(0, 0.06))
medium = _branch("medium", 0.10 + random.uniform(0, 0.06))
fast = _branch("fast", 0.10 + random.uniform(0, 0.06))


def join(ctx):
    TRACE.append("join")
    return "joined"


def build():
    return Workflow(
        name="e6_par",
        edges=[("START", fan), (fan, [slow, medium, fast]),
               (slow, join), (medium, join), (fast, join)],
    )


async def once():
    TRACE.clear()
    r = InMemoryRunner(agent=build(), app_name="e6p")
    s = await r.session_service.create_session(app_name="e6p", user_id="u")
    msg = types.Content(role="user", parts=[types.Part.from_text(text="go")])
    async for _ in r.run_async(user_id="u", session_id=s.id, new_message=msg,
                               run_config=RunConfig(streaming_mode=StreamingMode.NONE)):
        pass
    return list(TRACE)


async def main():
    seen = []
    for i in range(RUNS):
        t = await once()
        seen.append(t)
        print(f"  run {i+1}: {t}")
    distinct = {json.dumps(t) for t in seen}
    print(f"\ndistinct orderings: {len(distinct)} of {RUNS}")
    print("VERDICT:", "deterministic under fan-out"
          if len(distinct) == 1 else "ordering varies across runs")


asyncio.run(main())
