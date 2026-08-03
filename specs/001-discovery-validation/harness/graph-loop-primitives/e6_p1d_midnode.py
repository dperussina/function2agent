"""Primitive 1, the case that matters: crash *inside* a node, not at a boundary.

The previous arms killed the process at a node boundary, right after an output event.
Real crashes happen mid-node, while a tool is talking to something. This arm models a
node that performs an externally-visible side effect and then keeps working; the kill
lands during the work, after the side effect has already happened.

Side effects are appended to a file, so the count survives SIGKILL and can be compared
across both phases. Exactly-once would mean each iteration's side effect appears once.

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
from google.adk.runners import Runner
from google.adk.sessions.sqlite_session_service import SqliteSessionService
from google.genai import types

DB = e6_paths.path("e6_mid.db")
LEDGER = e6_paths.path("e6_mid_ledger.json")
SIDE_EFFECTS = e6_paths.path("e6_side_effects.log")
APP, USER, STOP_AFTER = "e6mid", "u", 4
RESUMABLE = os.environ.get("E6_RESUMABLE", "1") == "1"


def record(tag):
    with open(SIDE_EFFECTS, "a") as fh:
        fh.write(tag + "\n")
        fh.flush()
        os.fsync(fh.fileno())


def seed(node_input: str):
    yield Event(state={"iterations": 0})


async def work(ctx):
    n = ctx.state.get("iterations", 0) + 1
    # The externally-visible side effect: durable, happens before the node returns.
    record(f"work:{n}")
    # The node keeps working after its side effect. This is the window a crash
    # lands in for any node that calls out and then post-processes.
    await asyncio.sleep(0.6)
    ctx.state["iterations"] = n
    return f"work-{n}"


def check(ctx):
    n = ctx.state.get("iterations", 0)
    if n >= STOP_AFTER:
        yield Event(route="done")
    else:
        yield Event(route="again")


def finish(ctx):
    record("finish")
    return f"done after {ctx.state.get('iterations', 0)}"


def make_runner():
    wf = Workflow(name="e6_mid",
                  edges=[("START", seed, work, check),
                         (check, {"again": work, "done": finish})])
    kw = {"resumability_config": ResumabilityConfig(is_resumable=True)} if RESUMABLE else {}
    return Runner(app=App(name=APP, root_agent=wf, **kw),
                  session_service=SqliteSessionService(db_path=DB))


async def phase1():
    r = make_runner()
    s = await r.session_service.create_session(app_name=APP, user_id=USER)
    msg = types.Content(role="user", parts=[types.Part.from_text(text="go")])
    inv = {"v": None}

    async def killer():
        # Lands inside work:3's sleep window: seed + two full iterations (~1.2s)
        # plus part of the third.
        await asyncio.sleep(1.5)
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
    r = make_runner()
    err = None
    try:
        async for _ in r.run_async(user_id=USER, session_id=led["session_id"],
                                   new_message=None, invocation_id=led["invocation_id"],
                                   run_config=RunConfig(streaming_mode=StreamingMode.NONE)):
            pass
    except Exception as exc:  # noqa: BLE001
        err = f"{type(exc).__name__}: {str(exc)[:200]}"
    s2 = await r.session_service.get_session(app_name=APP, user_id=USER,
                                             session_id=led["session_id"])
    effects = [l.strip() for l in open(SIDE_EFFECTS) if l.strip()]
    dupes = {e: effects.count(e) for e in set(effects) if effects.count(e) > 1}
    print(f"  resumability      : {'ON' if RESUMABLE else 'OFF (default)'}")
    print(f"  side effects       : {effects}")
    print(f"  duplicated effects : {dupes if dupes else 'none'}")
    print(f"  final state        : {dict(s2.state) if s2 else None}")
    print(f"  error              : {err}")


if __name__ == "__main__":
    if sys.argv[1] == "phase1":
        try:
            os.remove(SIDE_EFFECTS)
        except FileNotFoundError:
            pass
        asyncio.run(phase1())
    else:
        asyncio.run(phase2())
