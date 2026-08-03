"""Is ADK SSE streaming genuinely incremental per provider, or coalesced?

The first pass saw only 2 partial events on a one-sentence answer, which is
consistent with coalescing rather than token streaming. This asks for a longer
answer and records partial-event count plus the growth of the accumulated text,
so 'streaming works' is decided by observed increments rather than by the flag.

Recovered verbatim from /tmp/f2a-probe-runtime/probe_adk_stream.py on 2026-08-02.
Produces finding 003 result 6 (the delta counts). One run per provider; the finding's
five-run Anthropic ratio series needs a loop this script does not have. See the README.
"""
import asyncio
import time

import envload

envload.load()

from google.adk.agents.llm_agent import Agent  # noqa: E402
from google.adk.agents.run_config import RunConfig, StreamingMode  # noqa: E402
from google.adk.models.lite_llm import LiteLlm  # noqa: E402
from google.adk.runners import InMemoryRunner  # noqa: E402
from google.genai import types  # noqa: E402

PROVIDERS = {
    "anthropic": "anthropic/claude-haiku-4-5-20251001",
    "openai": "openai/gpt-4.1-mini",
    "xai": "xai/grok-4.20-0309-non-reasoning",
    "gemini": "gemini/gemini-2.5-flash-lite",
}

PROMPT = "Count from 1 to 40, separated by spaces. Numbers only."


async def one(model_id):
    a = Agent(name="s", model=LiteLlm(model=model_id), instruction="Follow instructions exactly.")
    runner = InMemoryRunner(agent=a, app_name="p")
    s = await runner.session_service.create_session(app_name="p", user_id="u")
    c = types.Content(role="user", parts=[types.Part.from_text(text=PROMPT)])
    t0 = time.time()
    partials, first_partial_at, lens = 0, None, []
    final = ""
    async for ev in runner.run_async(
        user_id="u",
        session_id=s.id,
        new_message=c,
        run_config=RunConfig(streaming_mode=StreamingMode.SSE),
    ):
        txt = ""
        if ev.content and ev.content.parts:
            txt = "".join(p.text or "" for p in ev.content.parts)
        if getattr(ev, "partial", False):
            partials += 1
            if first_partial_at is None:
                first_partial_at = round(time.time() - t0, 2)
            lens.append(len(txt))
        elif txt:
            final = txt
    total = round(time.time() - t0, 2)
    return partials, first_partial_at, total, len(final), lens


for name, mid in PROVIDERS.items():
    p, first, total, flen, lens = asyncio.run(one(mid))
    incremental = len(set(lens)) > 2 and p > 3
    print(
        f"{name:<11} partials={p:<4} first_at={first}s total={total}s "
        f"final_len={flen:<5} incremental={'YES' if incremental else 'NO'} "
        f"chunk_len_progression={lens[:6]}{'...' if len(lens) > 6 else ''}"
    )
