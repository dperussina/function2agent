"""Does multi-turn, dependent tool use survive the provider switch in ADK?

Constitution Principle V warns that provider-opaque reasoning state (Anthropic
thinking blocks, OpenAI reasoning items, Gemini thought signatures, xAI encrypted
content), if dropped, "degrades multi-turn tool use silently rather than erroring."
A single tool call does not exercise that. This forces a chain: lookup_project ->
get_build_number(id from step 1) -> answer, so step two is only reachable if the
result of step one round-tripped correctly.

Success is decided programmatically from the recorded call order and arguments.

Recovered verbatim from /tmp/f2a-probe-runtime/probe_adk_multiturn.py on 2026-08-02.
Produces the "chained 2-tool call" column of finding 003's ADK matrix. See the README.
"""
import asyncio

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
    "xai": "xai/grok-4.3",
    "gemini": "gemini/gemini-2.5-flash-lite",
}

LOG = []


def lookup_project(name: str) -> dict:
    """Resolves a human project name to its internal project id.

    Args:
        name: The human-readable project name.
    """
    LOG.append(("lookup_project", name))
    return {"status": "success", "project_id": "PRJ-8829"}


def get_build_number(project_id: str) -> dict:
    """Returns the build number for an internal project id.

    Args:
        project_id: The internal project id, as returned by lookup_project.
    """
    LOG.append(("get_build_number", project_id))
    if project_id != "PRJ-8829":
        return {"status": "error", "reason": f"unknown project_id {project_id}"}
    return {"status": "success", "build_number": 4711}


async def one(model_id):
    LOG.clear()
    a = Agent(
        name="m",
        model=LiteLlm(model=model_id),
        instruction=(
            "You answer build-number questions. You must first call lookup_project to"
            " resolve the name to an id, then call get_build_number with that id."
            " Then state the build number."
        ),
        tools=[lookup_project, get_build_number],
    )
    runner = InMemoryRunner(agent=a, app_name="p")
    s = await runner.session_service.create_session(app_name="p", user_id="u")
    c = types.Content(
        role="user",
        parts=[types.Part.from_text(text="What is the build number for the Atlas project?")],
    )
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
    return text.strip(), list(LOG)


for name, mid in PROVIDERS.items():
    try:
        txt, log = asyncio.run(one(mid))
        names = [c[0] for c in log]
        ordered = names[:2] == ["lookup_project", "get_build_number"]
        chained = any(c[0] == "get_build_number" and c[1] == "PRJ-8829" for c in log)
        echoed = "4711" in txt
        ok = ordered and chained and echoed
        print(
            f"{name:<11} {'PASS' if ok else 'FAIL':<6} calls={log} "
            f"chained_id_ok={chained} answer_ok={echoed}"
        )
    except Exception as exc:  # noqa: BLE001
        print(f"{name:<11} ERROR  {type(exc).__name__}: {str(exc)[:150]}")
