"""Primitive 2: when a run ends, does ADK say *why*, by name?

Four scenarios are driven through the same four-node graph and the tail of the event
stream is dumped for each. FR-002 requires the terminal condition to be recorded by
name, so the test is whether a caller can distinguish these four outcomes from the
runtime's own output without inferring it from context.

  clean     - the trap is disarmed after 3 iterations and `finish` runs
  error     - `work` raises
  cancelled - the consumer stops reading (external cancellation)
  trapped   - the trap runs until the probe's timeout

Zero model spend: pure function nodes.
"""
import asyncio

import e6_graph
from google.adk import Event, Workflow
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.runners import InMemoryRunner
from google.genai import types

FIELDS = ("error_code", "error_message", "partial", "turn_complete", "finish_reason")


def describe(ev):
    bits = []
    for f in FIELDS:
        v = getattr(ev, f, None)
        if v not in (None, False):
            bits.append(f"{f}={v!r}")
    a = getattr(ev, "actions", None)
    for f in ("escalate", "end_of_agent", "route", "transfer_to_agent"):
        v = getattr(a, f, None) if a else None
        if v not in (None, False):
            bits.append(f"actions.{f}={v!r}")
    ni = getattr(ev, "node_info", None)
    if ni is not None:
        p = getattr(ni, "path", None)
        if p:
            bits.append(f"node={p!r}")
    return f"author={getattr(ev, 'author', '')!r} " + " ".join(bits)


async def drive(agent, label, timeout=15.0, stop_reading_after=None):
    runner = InMemoryRunner(agent=agent, app_name="e6")
    s = await runner.session_service.create_session(app_name="e6", user_id="u")
    msg = types.Content(role="user", parts=[types.Part.from_text(text="go")])
    tail, n, err = [], 0, None

    async def go():
        nonlocal n
        async for ev in runner.run_async(
            user_id="u", session_id=s.id, new_message=msg,
            run_config=RunConfig(streaming_mode=StreamingMode.NONE),
        ):
            n += 1
            tail.append(describe(ev))
            if stop_reading_after and n >= stop_reading_after:
                break

    try:
        await asyncio.wait_for(go(), timeout=timeout)
        ended = "generator completed normally"
    except asyncio.TimeoutError:
        ended = f"probe timeout at {timeout}s"
    except Exception as exc:  # noqa: BLE001
        ended = f"exception out of run_async: {type(exc).__name__}: {str(exc)[:120]}"
        err = type(exc).__name__

    print(f"\n=== {label} ===")
    print(f"  how the stream ended : {ended}")
    print(f"  events               : {n}")
    print(f"  last 3 events        :")
    for t in tail[-3:]:
        print(f"      {t}")
    return err


def boom(ctx):
    e6_graph.COUNTERS["work"] += 1
    raise RuntimeError("deliberate node failure")


async def main():
    e6_graph.reset(stop_after=3)
    await drive(e6_graph.build(), "clean completion (trap disarmed after 3)")

    e6_graph.reset(stop_after=None)
    err_wf = Workflow(
        name="e6_err",
        edges=[("START", e6_graph.seed, boom, e6_graph.check),
               (e6_graph.check, {"again": boom, "done": e6_graph.finish})],
    )
    await drive(err_wf, "node raises RuntimeError")

    e6_graph.reset(stop_after=None)
    await drive(e6_graph.build(), "consumer cancels after 5 events",
                stop_reading_after=5)

    e6_graph.reset(stop_after=None)
    await drive(e6_graph.build(), "non-termination trap, probe timeout", timeout=8.0)


asyncio.run(main())
