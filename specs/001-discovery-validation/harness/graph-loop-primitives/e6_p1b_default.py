"""Primitive 1, control arm: what does the *default* configuration do?

`ResumabilityConfig.is_resumable` defaults to False and the class is decorated
@experimental. The main resume probe turned it on. This arm repeats the identical
crash-and-resume sequence with it left at its default, because that is what a caller
gets if they do not know the flag exists.
"""
import asyncio
import json
import os
import signal
import sys

import e6_graph
import e6_paths
from google.adk.apps.app import App
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.runners import Runner
from google.adk.sessions.sqlite_session_service import SqliteSessionService
from google.genai import types

DB = e6_paths.path("e6_default.db")
LEDGER = e6_paths.path("e6_default_ledger.json")
APP, USER, KILL_AT, STOP_AFTER = "e6def", "u", 3, 6


def make_runner():
    # No resumability_config at all -> is_resumable is False.
    app = App(name=APP, root_agent=e6_graph.build())
    return Runner(app=app, session_service=SqliteSessionService(db_path=DB))


async def phase1():
    e6_graph.reset(stop_after=STOP_AFTER)
    r = make_runner()
    s = await r.session_service.create_session(app_name=APP, user_id=USER)
    msg = types.Content(role="user", parts=[types.Part.from_text(text="go")])
    inv = None
    async for ev in r.run_async(user_id=USER, session_id=s.id, new_message=msg,
                                run_config=RunConfig(streaming_mode=StreamingMode.NONE)):
        if inv is None and getattr(ev, "invocation_id", None):
            inv = ev.invocation_id
        if e6_graph.COUNTERS["work"] >= KILL_AT:
            json.dump({"session_id": s.id, "invocation_id": inv,
                       "work_before_kill": e6_graph.COUNTERS["work"]}, open(LEDGER, "w"))
            print(f"phase1: work executed {e6_graph.COUNTERS['work']}x, SIGKILL now")
            sys.stdout.flush()
            os.kill(os.getpid(), signal.SIGKILL)


async def phase2():
    led = json.load(open(LEDGER))
    e6_graph.reset(stop_after=STOP_AFTER)
    r = make_runner()
    sess = await r.session_service.get_session(app_name=APP, user_id=USER,
                                               session_id=led["session_id"])
    print(f"phase2: {len(sess.events)} persisted events")
    err = None
    try:
        async for _ in r.run_async(user_id=USER, session_id=led["session_id"],
                                   new_message=None, invocation_id=led["invocation_id"],
                                   run_config=RunConfig(streaming_mode=StreamingMode.NONE)):
            pass
    except Exception as exc:  # noqa: BLE001
        err = f"{type(exc).__name__}: {str(exc)[:220]}"
    s2 = await r.session_service.get_session(app_name=APP, user_id=USER,
                                             session_id=led["session_id"])
    print(f"phase1 work before kill : {led['work_before_kill']}")
    print(f"phase2 work executions  : {e6_graph.COUNTERS['work']}")
    print(f"phase2 trace            : {e6_graph.TRACE}")
    print(f"final state             : {dict(s2.state) if s2 else None}")
    print(f"error                   : {err}")


if __name__ == "__main__":
    asyncio.run(phase1() if sys.argv[1] == "phase1" else phase2())
