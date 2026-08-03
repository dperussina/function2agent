"""How awkward is it to host our own loop inside an ADK node?

That is the intended usage: ADK supplies the outer graph, and each node runs an agent
loop of ours. Two properties are measured.

  A) inner-loop granularity - a node runs its own 5-iteration loop, each iteration
     making a durable side effect. The process is killed during iteration 4. On resume,
     how many inner iterations re-execute? ADK checkpoints at node boundaries, so the
     prediction is that all four re-run and the node's internal progress is lost.

  B) concurrent state writes - two parallel branches write the same state key. ADK has
     no reducer or merge-function concept (state_schema only validates field names), so
     the prediction is last-write-wins with no way to declare an append or sum channel.

Zero model spend.
"""
import asyncio
import json
import os
import signal
import sys

import e6_paths
from google.adk import Event, Workflow
from google.adk.apps.app import App, ResumabilityConfig
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.runners import InMemoryRunner, Runner
from google.adk.sessions.sqlite_session_service import SqliteSessionService
from google.genai import types

DB = e6_paths.path("e6_host.db")
LEDGER = e6_paths.path("e6_host_ledger.json")
EFFECTS = e6_paths.path("e6_host_effects.log")
APP, USER, INNER = "e6host", "u", 5


def record(tag):
    with open(EFFECTS, "a") as fh:
        fh.write(tag + "\n")
        fh.flush()
        os.fsync(fh.fileno())


# --- A) our own loop, hosted inside a single ADK node -----------------------


def start(node_input: str):
    yield Event(state={"done": False})


async def our_loop(ctx):
    """A node that hosts its own bounded agent loop."""
    for i in range(1, INNER + 1):
        record(f"inner:{i}")          # the durable side effect of one loop turn
        await asyncio.sleep(0.4)
    ctx.state["done"] = True
    return "loop complete"


def after(ctx):
    record("after")
    return "graph complete"


def build_host():
    return Workflow(name="e6_host", edges=[("START", start, our_loop, after)])


def make_runner():
    return Runner(
        app=App(name=APP, root_agent=build_host(),
                resumability_config=ResumabilityConfig(is_resumable=True)),
        session_service=SqliteSessionService(db_path=DB),
    )


async def phase1():
    for f in (EFFECTS,):
        if os.path.exists(f):
            os.remove(f)
    r = make_runner()
    s = await r.session_service.create_session(app_name=APP, user_id=USER)
    msg = types.Content(role="user", parts=[types.Part.from_text(text="go")])
    inv = {"v": None}

    async def killer():
        await asyncio.sleep(1.5)  # lands inside inner iteration 4
        json.dump({"session_id": s.id, "invocation_id": inv["v"]}, open(LEDGER, "w"))
        sys.stdout.flush()
        os.kill(os.getpid(), signal.SIGKILL)

    asyncio.create_task(killer())
    async for ev in r.run_async(user_id=USER, session_id=s.id, new_message=msg,
                                run_config=RunConfig(streaming_mode=StreamingMode.NONE)):
        if inv["v"] is None and getattr(ev, "invocation_id", None):
            inv["v"] = ev.invocation_id


async def phase2():
    led = json.load(open(LEDGER))
    before = [l.strip() for l in open(EFFECTS) if l.strip()]
    r = make_runner()
    async for _ in r.run_async(user_id=USER, session_id=led["session_id"],
                               new_message=None, invocation_id=led["invocation_id"],
                               run_config=RunConfig(streaming_mode=StreamingMode.NONE)):
        pass
    after_all = [l.strip() for l in open(EFFECTS) if l.strip()]
    replayed = after_all[len(before):]
    print("A) our own loop hosted inside one ADK node")
    print(f"   inner turns completed before the kill : {before}")
    print(f"   executed after resume                 : {replayed}")
    dup = [t for t in replayed if t in before]
    print(f"   inner turns RE-EXECUTED on resume     : {dup} ({len(dup)} of {len(before)})")
    print(f"   inner-loop progress preserved         : "
          f"{'none - the whole node re-ran' if len(dup) == len(before) else 'partial'}")


# --- B) concurrent writes to one state key ----------------------------------

def fan(node_input: str):
    yield Event(state={"log": []})


def _writer(name, delay, val):
    async def w(ctx):
        # Read first, then work, then write: the classic lost-update shape that a
        # reducer/merge channel exists to prevent.
        prior = list(ctx.state.get("log", []))
        await asyncio.sleep(delay)
        ctx.state["log"] = prior + [val]
        return name
    w.__name__ = name
    return w


wa = _writer("wa", 0.05, "A")
wb = _writer("wb", 0.05, "B")


def collect(ctx):
    return ctx.state.get("log")


async def concurrent_state():
    wf = Workflow(name="e6_state",
                  edges=[("START", fan), (fan, [wa, wb]), (wa, collect), (wb, collect)])
    r = InMemoryRunner(agent=wf, app_name="e6s")
    s = await r.session_service.create_session(app_name="e6s", user_id="u")
    msg = types.Content(role="user", parts=[types.Part.from_text(text="go")])
    async for _ in r.run_async(user_id="u", session_id=s.id, new_message=msg,
                               run_config=RunConfig(streaming_mode=StreamingMode.NONE)):
        pass
    s2 = await r.session_service.get_session(app_name="e6s", user_id="u", session_id=s.id)
    log = (s2.state or {}).get("log")
    print("\nB) two parallel branches append to the same state key")
    print(f"   final value of state['log'] : {log}")
    print(f"   both writes survived        : "
          f"{'yes' if log and len(log) == 2 else 'NO - one write was lost'}")


if __name__ == "__main__":
    if sys.argv[1] == "phase1":
        asyncio.run(phase1())
    elif sys.argv[1] == "phase2":
        asyncio.run(phase2())
    else:
        asyncio.run(concurrent_state())
