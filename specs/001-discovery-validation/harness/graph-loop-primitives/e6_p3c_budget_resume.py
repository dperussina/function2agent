"""Primitive 3, part C: does the enforced budget survive a resume?

`max_llm_calls` is enforced by a counter on _InvocationCostManager, which lives on the
InvocationContext. If a resumed run builds a fresh context, the counter starts over and
the ceiling is per-attempt rather than per-goal — which means an agent that crashes and
resumes in a retry loop has no effective ceiling at all.

Run 1 exhausts a ceiling of 3. Run 2 resumes the same invocation with the same ceiling.
Counting total LLM calls across both runs answers it:

  3 total -> the budget is cumulative and survives resume
  6 total -> the budget resets, and the ceiling is per-attempt

Cost: at most 6 calls on the cheapest available model.
"""
import asyncio

import e6_paths
import envload

envload.load()

from google.adk import Agent, Event, Workflow
from google.adk.apps.app import App, ResumabilityConfig
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.models.lite_llm import LiteLlm
from google.adk.runners import Runner
from google.adk.sessions.sqlite_session_service import SqliteSessionService
from google.genai import types

DB = e6_paths.path("e6_budget.db")
APP, USER, MODEL, CEILING = "e6bud", "u", "gemini/gemini-2.5-flash-lite", 3

CALLS = {"n": 0}

think = Agent(name="think", model=LiteLlm(model=MODEL),
              instruction="Reply with exactly one short word.")


def seed(node_input: str):
    yield Event(state={"n": 0})


def check(ctx):
    n = ctx.state.get("n", 0) + 1
    ctx.state["n"] = n
    CALLS["n"] = n
    yield Event(route="again")


def finish(ctx):
    return "done"


def make_runner():
    wf = Workflow(name="e6_bud",
                  edges=[("START", seed, think, check),
                         (check, {"again": think, "done": finish})])
    return Runner(
        app=App(name=APP, root_agent=wf,
                resumability_config=ResumabilityConfig(is_resumable=True)),
        session_service=SqliteSessionService(db_path=DB),
    )


async def attempt(runner, session_id, invocation_id=None, msg=None):
    exc = None
    inv = invocation_id
    try:
        async for ev in runner.run_async(
            user_id=USER, session_id=session_id, new_message=msg,
            invocation_id=invocation_id,
            run_config=RunConfig(streaming_mode=StreamingMode.NONE,
                                 max_llm_calls=CEILING),
        ):
            if inv is None and getattr(ev, "invocation_id", None):
                inv = ev.invocation_id
    except BaseException as e:  # noqa: BLE001
        exc = type(e).__name__
    return inv, exc


async def main():
    import os
    if os.path.exists(DB):
        os.remove(DB)
    r = make_runner()
    s = await r.session_service.create_session(app_name=APP, user_id=USER)
    msg = types.Content(role="user", parts=[types.Part.from_text(text="say hi")])

    inv, exc1 = await attempt(r, s.id, msg=msg)
    after_run1 = CALLS["n"]
    print(f"  run 1: ceiling={CEILING} cycles={after_run1} halted_by={exc1}")

    _, exc2 = await attempt(r, s.id, invocation_id=inv)
    after_run2 = CALLS["n"]
    print(f"  run 2 (resume same invocation): cycles_now={after_run2} halted_by={exc2}")

    total = after_run2
    print(f"\n  total cycles across both attempts: {total}")
    print("  VERDICT:", "budget is cumulative across resume" if total <= CEILING
          else f"budget RESETS on resume - ceiling is per-attempt, not per-goal "
               f"({total} cycles under a ceiling of {CEILING})")


asyncio.run(main())
