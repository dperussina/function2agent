"""Primitive 2, follow-up: can a cancelled run be distinguished from a completed one?

`end_of_agent` is only emitted when is_resumable is True (see Workflow._emit_end_of_agent,
which returns early otherwise). So the fair test of ADK's terminal reporting runs with
that flag on, and asks whether the marker is present after a clean finish and absent
after a cancellation.

If both look the same to the caller, then "the agent finished" and "the agent was cut
off mid-loop" are the same observation — the false-success shape that FR-002 exists to
prevent.

Zero model spend.
"""
import asyncio

import e6_graph
from google.adk.apps.app import App, ResumabilityConfig
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.runners import Runner
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.genai import types


def make_runner():
    return Runner(
        app=App(name="e6c", root_agent=e6_graph.build(),
                resumability_config=ResumabilityConfig(is_resumable=True)),
        session_service=InMemorySessionService(),
    )


async def scenario(label, stop_after, cut_after=None, timeout=12.0):
    e6_graph.reset(stop_after=stop_after)
    r = make_runner()
    s = await r.session_service.create_session(app_name="e6c", user_id="u")
    msg = types.Content(role="user", parts=[types.Part.from_text(text="go")])
    markers, n = [], 0

    async def go():
        nonlocal n
        async for ev in r.run_async(user_id="u", session_id=s.id, new_message=msg,
                                    run_config=RunConfig(streaming_mode=StreamingMode.NONE)):
            n += 1
            a = getattr(ev, "actions", None)
            if a is not None and getattr(a, "end_of_agent", None):
                markers.append(f"end_of_agent from author={ev.author!r}")
            if cut_after and n >= cut_after:
                break

    ended = "stream ended"
    try:
        await asyncio.wait_for(go(), timeout=timeout)
    except asyncio.TimeoutError:
        ended = "probe timeout"
    except Exception as exc:  # noqa: BLE001
        ended = f"{type(exc).__name__}"

    print(f"  {label}")
    print(f"      events={n}  how={ended}")
    print(f"      end_of_agent markers: {markers if markers else 'NONE'}")
    print(f"      finish node ran: {bool(e6_graph.COUNTERS['finish'])}")
    return bool(markers)


async def main():
    print("resumability ON:")
    done = await scenario("clean completion (trap disarmed at 3)", stop_after=3)
    cut = await scenario("consumer cancels after 5 events, trap still armed",
                         stop_after=None, cut_after=5)
    print()
    if done and not cut:
        print("VERDICT: completion and cancellation ARE distinguishable "
              "(end_of_agent present only on clean finish)")
    elif done == cut:
        print("VERDICT: completion and cancellation are NOT distinguishable "
              "from the marker alone")
    else:
        print("VERDICT: unexpected - marker on cancellation but not completion")


asyncio.run(main())
