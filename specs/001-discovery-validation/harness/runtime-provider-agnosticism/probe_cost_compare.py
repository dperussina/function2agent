"""Same task, same model, two runtimes: what does each charge?

Task: call one tool, report the number. Model: claude-haiku-4-5 on first-party
Anthropic in both arms. The only variable is the runtime, so the token delta is
attributable to what each harness puts in front of the model.

Recovered from /tmp/f2a-probe-runtime/probe_cost_compare.py on 2026-08-02, with the
scratch `cwd` changed from a hardcoded path to envload.workdir(). Produces finding
003 §The 40x context tax. See the README.
"""
import asyncio
import os

import envload

envload.load()

MODEL = "claude-haiku-4-5-20251001"
PROMPT = "What is the build number for project 'atlas'?"

# ---------- arm 1: ADK + LiteLLM ----------
from google.adk.agents.llm_agent import Agent  # noqa: E402
from google.adk.agents.run_config import RunConfig, StreamingMode  # noqa: E402
from google.adk.models.lite_llm import LiteLlm  # noqa: E402
from google.adk.runners import InMemoryRunner  # noqa: E402
from google.genai import types  # noqa: E402

ADK_CALLS = []


def get_build_number(project: str) -> dict:
    """Returns the current build number for a named project.

    Args:
        project: The name of the project to look up.
    """
    ADK_CALLS.append(project)
    return {"status": "success", "build_number": 4711}


async def adk_arm():
    a = Agent(
        name="t",
        model=LiteLlm(model=f"anthropic/{MODEL}"),
        instruction="You look up build numbers. Call the tool, then state the number.",
        tools=[get_build_number],
    )
    r = InMemoryRunner(agent=a, app_name="p")
    s = await r.session_service.create_session(app_name="p", user_id="u")
    c = types.Content(role="user", parts=[types.Part.from_text(text=PROMPT)])
    pt = ct = 0
    async for ev in r.run_async(
        user_id="u", session_id=s.id, new_message=c,
        run_config=RunConfig(streaming_mode=StreamingMode.NONE),
    ):
        um = getattr(ev, "usage_metadata", None)
        if um:
            pt += um.prompt_token_count or 0
            ct += um.candidates_token_count or 0
    return pt, ct


# ---------- arm 2: Claude Agent SDK ----------
from claude_agent_sdk import (  # noqa: E402
    ClaudeAgentOptions, ResultMessage, create_sdk_mcp_server, query, tool,
)

CAS_CALLS = []


@tool("get_build_number", "Get the current build number for a named project.",
      {"project": str})
async def cas_tool(args):
    CAS_CALLS.append(args.get("project"))
    return {"content": [{"type": "text", "text": '{"build_number": 4711}'}]}


async def cas_arm():
    opts = ClaudeAgentOptions(
        model=MODEL,
        mcp_servers={"probe": create_sdk_mcp_server(name="probe", tools=[cas_tool])},
        allowed_tools=["mcp__probe__get_build_number"],
        max_turns=4,
        permission_mode="bypassPermissions",
        setting_sources=[],
        system_prompt="You look up build numbers. Call the tool, then state the number.",
        env={"ANTHROPIC_API_KEY": os.environ["ANTHROPIC_API_KEY"]},
        cwd=envload.workdir(),
    )
    res = None
    async for m in query(prompt=PROMPT, options=opts):
        if isinstance(m, ResultMessage):
            res = m
    u = res.usage or {}
    return (
        (u.get("input_tokens", 0) or 0)
        + (u.get("cache_creation_input_tokens", 0) or 0)
        + (u.get("cache_read_input_tokens", 0) or 0),
        u.get("output_tokens", 0) or 0,
        res.total_cost_usd,
    )


ap, ac = asyncio.run(adk_arm())
# Anthropic list pricing for haiku-4.5: $1.00/Mtok in, $5.00/Mtok out.
adk_cost = ap / 1e6 * 1.00 + ac / 1e6 * 5.00
cp, cc, ccost = asyncio.run(cas_arm())

print(f"\nsame task, same model ({MODEL}), tool invoked "
      f"ADK={len(ADK_CALLS)}x CAS={len(CAS_CALLS)}x\n")
print(f"{'runtime':<26} {'input_tok':>10} {'output_tok':>11} {'cost_usd':>10}")
print(f"{'ADK 2.6.1 + LiteLLM':<26} {ap:>10} {ac:>11} {adk_cost:>10.5f}  (computed at list price)")
print(f"{'Claude Agent SDK 0.2.128':<26} {cp:>10} {cc:>11} {ccost:>10.5f}  (reported by the SDK)")
print(f"\ninput-token ratio CAS/ADK: {cp / ap:.1f}x")
