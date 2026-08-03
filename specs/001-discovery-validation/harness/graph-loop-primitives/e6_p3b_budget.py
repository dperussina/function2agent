"""Primitive 3, part B: is `max_llm_calls` actually enforced, or only advisory?

Part A established that ADK's graph layer has no step ceiling of its own. The only
runtime-enforced ceiling anywhere in ADK is `RunConfig.max_llm_calls` (default 500),
checked in InvocationContext.increment_and_enforce_llm_calls_limit.

This arm puts a real LLM agent inside the cycle of the same non-termination trap and
sets the ceiling to 3. A ceiling that only warns would let the trap keep spinning; a
ceiling that is enforced halts the run. We also record *how* the halt surfaces, which
feeds the terminal-condition verdict.

Cost: bounded by the ceiling itself. Four calls on the cheapest available model.
"""
import asyncio
import os

import envload

envload.load()

from google.adk import Agent, Event, Workflow
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.models.lite_llm import LiteLlm
from google.adk.runners import InMemoryRunner
from google.genai import types

MODEL = "gemini/gemini-2.5-flash-lite"
MAX_LLM_CALLS = 3
WALL_SECONDS = 90.0

TRACE = []

think = Agent(
    name="think",
    model=LiteLlm(model=MODEL),
    instruction="Reply with exactly one short word. Nothing else.",
)


def seed(node_input: str):
    TRACE.append("seed")
    yield Event(state={"n": 0})


def check(ctx):
    n = ctx.state.get("n", 0) + 1
    ctx.state["n"] = n
    TRACE.append(f"check:{n}")
    yield Event(route="again")  # the trap: never terminates on its own


def finish(ctx):
    TRACE.append("finish")
    return "done"


def build():
    return Workflow(
        name="e6_budget",
        edges=[("START", seed, think, check),
               (check, {"again": think, "done": finish})],
    )


async def main():
    r = InMemoryRunner(agent=build(), app_name="e6b")
    s = await r.session_service.create_session(app_name="e6b", user_id="u")
    msg = types.Content(role="user", parts=[types.Part.from_text(text="say hi")])

    outcome, exc_type, exc_msg = "ran to completion on its own", None, None

    async def drive():
        async for _ in r.run_async(
            user_id="u", session_id=s.id, new_message=msg,
            run_config=RunConfig(streaming_mode=StreamingMode.NONE,
                                 max_llm_calls=MAX_LLM_CALLS),
        ):
            pass

    try:
        await asyncio.wait_for(drive(), timeout=WALL_SECONDS)
    except asyncio.TimeoutError:
        outcome = f"NOT ENFORCED - still running at {WALL_SECONDS}s"
    except BaseException as e:  # noqa: BLE001
        exc_type, exc_msg = type(e).__name__, str(e)[:200]
        outcome = "halted by exception"

    llm_nodes = sum(1 for t in TRACE if t.startswith("check"))
    print(f"  max_llm_calls set   : {MAX_LLM_CALLS}")
    print(f"  outcome             : {outcome}")
    print(f"  exception type      : {exc_type}")
    print(f"  exception message   : {exc_msg}")
    print(f"  trace               : {TRACE}")
    print(f"  cycles completed    : {llm_nodes}")
    print(f"  VERDICT             : "
          f"{'ENFORCED - run halted' if exc_type else 'NOT ENFORCED'}")


asyncio.run(main())
