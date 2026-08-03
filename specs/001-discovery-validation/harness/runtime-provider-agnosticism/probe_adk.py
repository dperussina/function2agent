"""Probe: can Google ADK 2.6.1 be driven by non-default model providers, end to end?

Four capability cells per provider: plain completion, tool-calling, streaming, and
structured output. Tool-calling success is decided programmatically by a side effect
recorded inside the Python tool function, not by reading the model's prose.

Never prints a credential value. Cheap models only; prompts are trivial.

Recovered verbatim from /tmp/f2a-probe-runtime/probe_adk.py on 2026-08-02. Produces
the ADK matrix in findings/003-runtime-provider-agnosticism.md. See the README.
"""
import asyncio
import os
import sys
import time
import traceback

import envload

envload.load()

from google.adk.agents.llm_agent import Agent  # noqa: E402
from google.adk.agents.run_config import RunConfig, StreamingMode  # noqa: E402
from google.adk.models.lite_llm import LiteLlm  # noqa: E402
from google.adk.runners import InMemoryRunner  # noqa: E402
from google.genai import types  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

PROVIDERS = {
    "anthropic": "anthropic/claude-haiku-4-5-20251001",
    "openai": "openai/gpt-4.1-mini",
    "xai": "xai/grok-4.3",
    "gemini": "gemini/gemini-2.5-flash-lite",
}

TOOL_CALLS = {"n": 0, "args": []}


def get_build_number(project: str) -> dict:
    """Returns the current build number for a named project.

    Args:
        project: The name of the project to look up.
    """
    TOOL_CALLS["n"] += 1
    TOOL_CALLS["args"].append(project)
    return {"status": "success", "project": project, "build_number": 4711}


class Summary(BaseModel):
    city: str = Field(description="Name of the city.")
    country: str = Field(description="Country the city is in.")


USAGE = []


async def run(agent, prompt, streaming=False):
    """Runs one agent turn. Returns (final_text, n_partial_events, usage_tuple)."""
    runner = InMemoryRunner(agent=agent, app_name="probe")
    session = await runner.session_service.create_session(
        app_name="probe", user_id="u"
    )
    content = types.Content(role="user", parts=[types.Part.from_text(text=prompt)])
    cfg = RunConfig(
        streaming_mode=StreamingMode.SSE if streaming else StreamingMode.NONE
    )
    text, partials, pt, ct = "", 0, 0, 0
    async for ev in runner.run_async(
        user_id="u", session_id=session.id, new_message=content, run_config=cfg
    ):
        if getattr(ev, "partial", False):
            partials += 1
        um = getattr(ev, "usage_metadata", None)
        if um:
            pt = max(pt, um.prompt_token_count or 0)
            ct += um.candidates_token_count or 0
        if ev.content and ev.content.parts and not getattr(ev, "partial", False):
            for p in ev.content.parts:
                if p.text:
                    text += p.text
    USAGE.append((pt, ct))
    return text.strip(), partials


def cell(name, fn):
    """Runs one capability cell, capturing the exact failure text if it fails."""
    t0 = time.time()
    try:
        ok, detail = asyncio.run(fn())
        return (name, "PASS" if ok else "FAIL", detail, round(time.time() - t0, 1))
    except Exception as exc:  # noqa: BLE001
        tb = traceback.extract_tb(sys.exc_info()[2])
        frame = ""
        for f in reversed(tb):
            if "/site-packages/" in (f.filename or ""):
                frame = f"{os.path.basename(f.filename)}:{f.lineno}"
                break
        msg = str(exc).replace("\n", " ")[:240]
        return (
            name,
            "ERROR",
            f"{type(exc).__name__} at {frame}: {msg}",
            round(time.time() - t0, 1),
        )


def probe(provider, model_id):
    print(f"\n{'=' * 78}\n{provider}  ->  LiteLlm(model={model_id!r})\n{'=' * 78}")
    results = []

    async def completion():
        a = Agent(
            name="c",
            model=LiteLlm(model=model_id),
            instruction="Reply with exactly the word OK. Nothing else.",
        )
        txt, _ = await run(a, "Say OK.")
        return ("ok" in txt.lower(), f"returned {txt[:60]!r}")

    async def toolcall():
        TOOL_CALLS["n"] = 0
        TOOL_CALLS["args"] = []
        a = Agent(
            name="t",
            model=LiteLlm(model=model_id),
            instruction=(
                "You look up build numbers. Always call the get_build_number tool"
                " before answering. Then state the number."
            ),
            tools=[get_build_number],
        )
        txt, _ = await run(a, "What is the build number for project 'atlas'?")
        # Programmatic check: the Python function actually ran, with the right arg,
        # and the result reached the model's final answer.
        ran = TOOL_CALLS["n"] > 0
        arg_ok = any("atlas" in a.lower() for a in TOOL_CALLS["args"])
        echoed = "4711" in txt
        return (
            ran and arg_ok and echoed,
            f"tool invoked {TOOL_CALLS['n']}x args={TOOL_CALLS['args']} "
            f"result_in_answer={echoed}",
        )

    async def streaming():
        a = Agent(
            name="s",
            model=LiteLlm(model=model_id),
            instruction="Answer in one short sentence.",
        )
        txt, partials = await run(a, "Name one primary color.", streaming=True)
        return (partials > 0 and bool(txt), f"{partials} partial events, final {txt[:40]!r}")

    async def structured():
        a = Agent(
            name="o",
            model=LiteLlm(model=model_id),
            instruction="Return JSON matching the schema.",
            output_schema=Summary,
        )
        txt, _ = await run(a, "Paris.")
        good = "paris" in txt.lower() and "{" in txt
        return (good, f"returned {txt[:90]!r}")

    for name, fn in [
        ("completion", completion),
        ("tool_calling", toolcall),
        ("streaming", streaming),
        ("structured_output", structured),
    ]:
        r = cell(name, fn)
        results.append(r)
        print(f"  {r[0]:<18} {r[1]:<6} {r[3]:>5}s  {r[2][:150]}")
    return results


if __name__ == "__main__":
    only = sys.argv[1:] or list(PROVIDERS)
    all_results = {}
    for p in only:
        all_results[p] = probe(p, PROVIDERS[p])
    print(f"\n\n{'=' * 78}\nSUMMARY (ADK 2.6.1 + litellm 1.91.4)\n{'=' * 78}")
    print(f"{'provider':<12} {'completion':<12} {'tools':<12} {'stream':<12} {'struct':<12}")
    for p, rs in all_results.items():
        print(f"{p:<12} " + " ".join(f"{r[1]:<12}" for r in rs))
    tot_p = sum(u[0] for u in USAGE)
    tot_c = sum(u[1] for u in USAGE)
    print(f"\ntokens observed: prompt={tot_p} completion={tot_c} across {len(USAGE)} turns")
