"""Primitive 1: kill the process mid-run. Can ADK resume with state intact?

Two phases in two separate OS processes against one persistent SQLite session.

  phase1 - run the graph with the trap disarmed at iteration 6, then SIGKILL this
           process at iteration 3. SIGKILL is used deliberately: no cleanup, no
           finally blocks, no graceful shutdown. That is what a crash looks like.
  phase2 - a fresh process opens the same SQLite session and calls run_async with
           the recorded invocation_id.

The verdict is decided programmatically from two numbers: how many times `work`
executes in phase 2, and what the final iteration count is.

  resumed correctly -> phase2 runs work 3 times (iterations 4,5,6), final count 6
  restarted         -> phase2 runs work 6 times, final count 6 but 9 total executions
  state lost        -> final count < 6 or the call errors

Zero model spend: pure function nodes.
"""
import asyncio
import json
import os
import signal
import sys

import e6_graph
import e6_paths
from google.adk.apps.app import App, ResumabilityConfig
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.runners import Runner
from google.adk.sessions.sqlite_session_service import SqliteSessionService
from google.genai import types

DB = e6_paths.path("e6_sessions.db")
LEDGER = e6_paths.path("e6_resume_ledger.json")
APP = "e6app"
USER = "u"
KILL_AT = 3
STOP_AFTER = 6


def make_runner():
    app = App(
        name=APP,
        root_agent=e6_graph.build(),
        resumability_config=ResumabilityConfig(is_resumable=True),
    )
    return Runner(app=app, session_service=SqliteSessionService(db_path=DB))


async def phase1():
    e6_graph.reset(stop_after=STOP_AFTER)
    runner = make_runner()
    s = await runner.session_service.create_session(app_name=APP, user_id=USER)
    msg = types.Content(role="user", parts=[types.Part.from_text(text="go")])

    inv = None
    async for ev in runner.run_async(
        user_id=USER, session_id=s.id, new_message=msg,
        run_config=RunConfig(streaming_mode=StreamingMode.NONE),
    ):
        if inv is None and getattr(ev, "invocation_id", None):
            inv = ev.invocation_id
            json.dump({"session_id": s.id, "invocation_id": inv},
                      open(LEDGER, "w"))
        if e6_graph.COUNTERS["work"] >= KILL_AT:
            json.dump({"session_id": s.id, "invocation_id": inv,
                       "work_before_kill": e6_graph.COUNTERS["work"],
                       "trace_before_kill": list(e6_graph.TRACE)},
                      open(LEDGER, "w"))
            sys.stdout.flush()
            print(f"phase1: work executed {e6_graph.COUNTERS['work']}x, SIGKILL now")
            sys.stdout.flush()
            os.kill(os.getpid(), signal.SIGKILL)
    print("phase1: finished WITHOUT being killed (unexpected)")


async def phase2():
    led = json.load(open(LEDGER))
    e6_graph.reset(stop_after=STOP_AFTER)
    runner = make_runner()
    sess = await runner.session_service.get_session(
        app_name=APP, user_id=USER, session_id=led["session_id"]
    )
    print(f"phase2: session reopened, {len(sess.events)} persisted events")
    print(f"phase2: resuming invocation_id={led['invocation_id']!r}")

    final_state, err = None, None
    try:
        async for ev in runner.run_async(
            user_id=USER, session_id=led["session_id"], new_message=None,
            invocation_id=led["invocation_id"],
            run_config=RunConfig(streaming_mode=StreamingMode.NONE),
        ):
            pass
    except Exception as exc:  # noqa: BLE001
        err = f"{type(exc).__name__}: {str(exc)[:200]}"

    sess2 = await runner.session_service.get_session(
        app_name=APP, user_id=USER, session_id=led["session_id"]
    )
    final_state = dict(sess2.state) if sess2 else {}

    print(f"\nphase1 work executions (before kill): {led['work_before_kill']}")
    print(f"phase1 trace                        : {led['trace_before_kill']}")
    print(f"phase2 work executions              : {e6_graph.COUNTERS['work']}")
    print(f"phase2 trace                        : {e6_graph.TRACE}")
    print(f"phase2 finish executions            : {e6_graph.COUNTERS['finish']}")
    print(f"final session state                 : {final_state}")
    print(f"error                               : {err}")

    total = led["work_before_kill"] + e6_graph.COUNTERS["work"]
    if err:
        verdict = "FAIL - resume raised"
    elif e6_graph.COUNTERS["work"] == STOP_AFTER - KILL_AT and total == STOP_AFTER:
        verdict = "PASS - resumed from the interruption, no work repeated"
    elif e6_graph.COUNTERS["work"] >= STOP_AFTER:
        verdict = f"FAIL - restarted from the beginning ({total} total work executions)"
    elif e6_graph.COUNTERS["work"] == 0:
        verdict = "FAIL - resume was a no-op, no further work executed"
    else:
        verdict = f"AMBIGUOUS - {e6_graph.COUNTERS['work']} in phase2, {total} total"
    print(f"\nVERDICT: {verdict}")


if __name__ == "__main__":
    asyncio.run(phase1() if sys.argv[1] == "phase1" else phase2())
