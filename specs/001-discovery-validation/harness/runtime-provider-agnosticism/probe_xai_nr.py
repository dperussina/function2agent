"""Strict re-check of ADK structured output: does the final text actually parse
as JSON and validate against the declared pydantic schema?

The first pass used a substring check, which credited xAI with a pass for output
that was prose wrapping a schema echo. This decides the cell by json.loads +
model_validate, not by eyeballing.

Recovered verbatim from /tmp/f2a-probe-runtime/probe_xai_nr.py on 2026-08-02. Identical
to probe_adk_strict.py except that it runs only xai/grok-4.20-0309-non-reasoning: the
control that shows finding 003 result 5 is a property of the model, not of ADK or xAI.
"""
import asyncio
import json

import envload

envload.load()

from google.adk.agents.llm_agent import Agent  # noqa: E402
from google.adk.agents.run_config import RunConfig, StreamingMode  # noqa: E402
from google.adk.models.lite_llm import LiteLlm  # noqa: E402
from google.adk.runners import InMemoryRunner  # noqa: E402
from google.genai import types  # noqa: E402
from pydantic import BaseModel, Field, ValidationError  # noqa: E402

PROVIDERS = {
    "xai": "xai/grok-4.20-0309-non-reasoning",
}


class Summary(BaseModel):
    city: str = Field(description="Name of the city.")
    country: str = Field(description="Country the city is in.")


async def one(model_id):
    a = Agent(
        name="o",
        model=LiteLlm(model=model_id),
        instruction="Return JSON matching the schema.",
        output_schema=Summary,
    )
    runner = InMemoryRunner(agent=a, app_name="p")
    s = await runner.session_service.create_session(app_name="p", user_id="u")
    c = types.Content(role="user", parts=[types.Part.from_text(text="Paris.")])
    text = ""
    async for ev in runner.run_async(
        user_id="u",
        session_id=s.id,
        new_message=c,
        run_config=RunConfig(streaming_mode=StreamingMode.NONE),
    ):
        if ev.content and ev.content.parts and not getattr(ev, "partial", False):
            for p in ev.content.parts:
                if p.text:
                    text += p.text
    return text.strip()


for name, mid in PROVIDERS.items():
    raw = asyncio.run(one(mid))
    try:
        obj = Summary.model_validate(json.loads(raw))
        verdict, detail = "PASS", f"parsed -> {obj.city}/{obj.country}"
    except (json.JSONDecodeError, ValidationError, TypeError) as exc:
        verdict = "FAIL"
        detail = f"{type(exc).__name__}: {str(exc).splitlines()[0][:80]} | raw={raw[:110]!r}"
    print(f"{name:<11} {verdict:<6} {detail}")
