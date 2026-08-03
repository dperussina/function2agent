"""Primitive 3, part A: does ADK enforce any *graph step* limit of its own?

Runs the non-termination trap with no external guard except a wall-clock timeout
imposed by the probe. If ADK had a built-in step ceiling the run would end by itself
with some named condition; if it does not, only our timeout stops it.

Zero model spend: every node is a pure Python function.
"""
import asyncio
import sys

import e6_graph
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.runners import InMemoryRunner
from google.genai import types

WALL_SECONDS = 20.0


async def main():
    e6_graph.reset(stop_after=None)  # trap armed: never terminates on its own
    runner = InMemoryRunner(agent=e6_graph.build(), app_name="e6")
    s = await runner.session_service.create_session(app_name="e6", user_id="u")
    msg = types.Content(role="user", parts=[types.Part.from_text(text="go")])

    events = 0

    async def drive():
        nonlocal events
        async for _ in runner.run_async(
            user_id="u", session_id=s.id, new_message=msg,
            run_config=RunConfig(streaming_mode=StreamingMode.NONE),
        ):
            events += 1

    outcome = "completed on its own"
    try:
        await asyncio.wait_for(drive(), timeout=WALL_SECONDS)
    except asyncio.TimeoutError:
        outcome = f"still running when the probe's {WALL_SECONDS}s timeout fired"
    except Exception as exc:  # noqa: BLE001
        outcome = f"raised {type(exc).__name__}: {str(exc)[:160]}"

    print(f"outcome              : {outcome}")
    print(f"work node executions : {e6_graph.COUNTERS['work']}")
    print(f"check node executions: {e6_graph.COUNTERS['check']}")
    print(f"finish executions    : {e6_graph.COUNTERS['finish']}")
    print(f"events yielded       : {events}")
    if e6_graph.COUNTERS["work"]:
        print(f"iterations/sec       : {e6_graph.COUNTERS['work'] / WALL_SECONDS:,.0f}")


asyncio.run(main())
sys.exit(0)
