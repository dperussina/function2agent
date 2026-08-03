"""Probe: can the Claude Agent SDK be driven by a non-Anthropic model?

Cells:
  A. baseline      — default first-party Anthropic, custom in-process MCP tool.
  B. xai_gateway   — ANTHROPIC_BASE_URL pointed at xAI's Anthropic-Messages-compatible
                     endpoint with the xAI key and model grok-4.3. This is the only
                     genuinely different *model family* reachable without a cloud account.
  C. openai_gateway— same trick against OpenAI, which publishes no /v1/messages surface.

Tool-call success is decided programmatically by a side effect recorded inside the
Python tool body, plus the reported model/provider on the result message.

The subprocess is given a clean environment: no inherited Anthropic credential, no
filesystem or shell tools. Never prints a credential value.

Recovered from /tmp/f2a-probe-runtime/probe_cas.py on 2026-08-02, with the scratch
`cwd` changed from a hardcoded path to envload.workdir(). Produces the Claude Agent
SDK table in findings/003-runtime-provider-agnosticism.md. See the README.
"""
import asyncio
import os
import sys

import envload

envload.load()

from claude_agent_sdk import (  # noqa: E402
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    TextBlock,
    create_sdk_mcp_server,
    query,
    tool,
)

CALLS = {"n": 0, "args": []}


@tool("get_build_number", "Get the current build number for a named project.",
      {"project": str})
async def get_build_number(args):
    CALLS["n"] += 1
    CALLS["args"].append(args.get("project"))
    return {"content": [{"type": "text", "text": '{"build_number": 4711}'}]}


SERVER = create_sdk_mcp_server(name="probe", version="1.0.0", tools=[get_build_number])
PROMPT = "Call the get_build_number tool for project 'atlas', then state the number."


async def run_cell(label, env, model):
    CALLS["n"] = 0
    CALLS["args"] = []
    opts = ClaudeAgentOptions(
        model=model,
        mcp_servers={"probe": SERVER},
        allowed_tools=["mcp__probe__get_build_number"],
        disallowed_tools=["Bash", "Write", "Edit", "Read", "Glob", "Grep", "WebSearch",
                          "WebFetch", "NotebookEdit", "Task"],
        max_turns=4,
        permission_mode="bypassPermissions",
        setting_sources=[],          # ignore ~/.claude and project settings
        system_prompt="You are a build-number lookup assistant. Be terse.",
        env=env,
        cwd=envload.workdir(),
    )
    text, result = "", None
    try:
        async for msg in query(prompt=PROMPT, options=opts):
            if isinstance(msg, AssistantMessage):
                for b in msg.content:
                    if isinstance(b, TextBlock):
                        text += b.text
            elif isinstance(msg, ResultMessage):
                result = msg
    except Exception as exc:  # noqa: BLE001
        print(f"\n[{label}] EXCEPTION {type(exc).__name__}: {str(exc)[:400]}")
        return

    ran = CALLS["n"] > 0
    echoed = "4711" in text
    print(f"\n[{label}]")
    print(f"  tool invoked      : {CALLS['n']}x  args={CALLS['args']}")
    print(f"  result in answer  : {echoed}")
    print(f"  final text        : {text.strip()[:120]!r}")
    if result:
        print(f"  is_error          : {result.is_error}   turns={result.num_turns}"
              f"   cost_usd={getattr(result, 'total_cost_usd', None)}")
        mu = getattr(result, "model_usage", None) or {}
        for k, v in mu.items():
            prov = v.get("provider") if isinstance(v, dict) else getattr(v, "provider", None)
            print(f"  model_usage       : model={k!r} provider={prov!r}")
    print(f"  VERDICT           : {'PASS' if (ran and echoed) else 'FAIL'}")


async def main():
    which = sys.argv[1:] or ["baseline", "xai", "openai"]

    if "baseline" in which:
        await run_cell(
            "A. baseline / first-party Anthropic / claude-haiku-4-5",
            {"ANTHROPIC_API_KEY": os.environ["ANTHROPIC_API_KEY"]},
            "claude-haiku-4-5-20251001",
        )

    if "xai" in which:
        await run_cell(
            "B. xAI via ANTHROPIC_BASE_URL=https://api.x.ai / grok-4.3",
            {
                "ANTHROPIC_BASE_URL": "https://api.x.ai",
                "ANTHROPIC_API_KEY": os.environ["XAI_API_KEY"],
                "ANTHROPIC_AUTH_TOKEN": os.environ["XAI_API_KEY"],
            },
            "grok-4.3",
        )

    if "openai" in which:
        await run_cell(
            "C. OpenAI via ANTHROPIC_BASE_URL=https://api.openai.com / gpt-4.1-mini",
            {
                "ANTHROPIC_BASE_URL": "https://api.openai.com",
                "ANTHROPIC_API_KEY": os.environ["OPENAI_API_KEY"],
                "ANTHROPIC_AUTH_TOKEN": os.environ["OPENAI_API_KEY"],
            },
            "gpt-4.1-mini",
        )


asyncio.run(main())
