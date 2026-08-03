# E5 harness — can the candidate runtimes be driven by a non-default provider?

Produces the numbers in
[`findings/003-runtime-provider-agnosticism.md`](../../findings/003-runtime-provider-agnosticism.md),
the probe behind **OD-02** (do not use the Claude Agent SDK as the coding-node executor).

Run `F2A_ENV_ROOT=/path/to/tree ./run.sh`. Model spend is roughly **$0.09** against the
finding's $2.00 ceiling: every prompt is trivial and every model is a cheap tier.

> **Recovered, not reconstructed.** Eight of the nine scripts here are the ones that
> produced the finding, recovered from `/tmp/f2a-probe-runtime/` on **2026-08-02**.
> The ninth, `count_reasoning_fields.py`, is a reconstruction and says so in its own
> docstring. Changes made during recovery are enumerated in
> [§What changed](#what-changed-during-recovery); none of them touch a measurement.
>
> The VERDICT and finding 006 both state these scripts were "not committed." That was
> true when written. They survived in `/tmp` and are committed here.

## Credentials

`envload.py` reads a dotenv tree **you name** and assigns values straight to
`os.environ`. No script prints, logs, or writes a credential value, and there is no
result artifact that could contain one.

```bash
export F2A_ENV_ROOT=/path/to/tree        # required, no default
export F2A_GEMINI_VAR=GEMINI_API_KEY_2   # optional; see below
./run.sh
```

`F2A_GEMINI_VAR` exists because of
[finding 002](../../findings/002-provider-credentials.md): on the tree this probe
originally ran against, the canonically-named `GEMINI_API_KEY` was one of ten dead
credentials and the working one was called `GEMINI_API_KEY_2`. The original loader
hardcoded that name and the file it lived in. **A generated stack cannot assume
canonical credential names, and neither does this harness** — it searches the tree and
takes the first of `GEMINI_API_KEY`, `GEMINI_API_KEY_2`, `GOOGLE_API_KEY` it finds,
unless you override the order.

## What each piece does

| File | Purpose |
|---|---|
| `run.sh` | End-to-end reproduction. Builds the virtualenv on first use, prints the interpreter and package versions it resolved, then runs each arm. Individual arms: `./run.sh stream cas`. |
| `requirements.txt` | The exact pins. **Read it before relaxing the LiteLLM version** — see below. |
| `envload.py` | Credential loading. Run it directly to see which variable names resolved, without values. |
| `pick_models.py` | The model-selection step, not a measured arm: how the four model strings were chosen. Zero cost. |
| `probe_adk.py` | **The ADK matrix.** Four capability cells per provider: completion, tool-calling, streaming, structured output. Tool success is decided by a side effect recorded inside the Python tool body, never by reading prose. |
| `probe_adk_multiturn.py` | **Chained two-step tool use** — `lookup_project` returns `PRJ-8829`, which must be threaded into `get_build_number`. The single most important positive result: step two is only reachable if step one round-tripped intact. |
| `probe_adk_stream.py` | Result 6. Asks for a 110-character answer and counts partial events, so "streaming works" is decided by observed increments rather than by a flag. |
| `probe_adk_strict.py` | Result 5, and the corrected structured-output cell. Decides by `json.loads` + pydantic `model_validate`. |
| `probe_xai_nr.py` | Result 5's control: the same strict check against xAI's non-reasoning model, which passes where `grok-4.3` fails. This is what makes result 5 a statement about the model rather than about ADK or about xAI. |
| `probe_cas.py` | **The Claude Agent SDK table.** Baseline first-party Anthropic, then xAI and OpenAI via `ANTHROPIC_BASE_URL` redirection. The subprocess gets a clean environment and no filesystem or shell tools. |
| `probe_cost_compare.py` | §The 40x context tax. Same task, same model, same provider; the runtime is the only variable. |
| `count_reasoning_fields.py` | Result 7. **Reconstructed** — see below. |

### Two arms disagree on purpose

`probe_adk.py`'s `structured_output` cell uses a substring check, and **it is wrong**.
It credited `grok-4.3` with a pass for output that was reasoning prose wrapped around a
schema echo. `probe_adk_strict.py` is the corrected instrument and it is the one the
finding's structured-output column reports. Both are kept because the disagreement
between them *is* result 5: a provider can silently return unparseable text under a
strict schema request, and a lax checker will not notice. Do not read
`probe_adk.py`'s fourth column as a result.

## Re-runnability hazards

Three things will bite anyone re-running this, and all three are load-bearing rather
than incidental.

**1. LiteLLM does not ship a macOS wheel, and nothing says so.** `litellm==1.91.4` is
the last release publishing a pure-Python `py3-none-any` wheel. From 1.92.0 onward
LiteLLM ships compiled platform-specific wheels — `manylinux_2_28_aarch64`,
`manylinux_2_28_x86_64`, `win_amd64` — and **zero for macOS**, so on a Mac the resolver
falls back to the sdist and demands `maturin` and `rustc`:

```
error: could not execute process `rustc -vV` (never executed)
💥 maturin failed
```

The pin in `requirements.txt` is therefore not conservatism, it is the only version
that installs on the platform the probe ran on. **Every ADK result in finding 003 is
measured against 1.91.4, not against current LiteLLM**, and the finding says so. Its
own next-step 3 is to re-run this matrix on current LiteLLM in a Linux container; that
has not been done.

**2. A reasoning model silently returned unparseable text under a strict schema.**
`grok-4.3` responded to an `output_schema` request with prose wrapping the JSON, which
fails `json.loads` at line 1 column 1. **ADK raised no exception and logged no
warning.** If you re-run and see the structured-output cell pass on `grok-4.3`, the
model changed — that is a real possibility and not a harness failure.

**3. Every model string in this harness is a moving target.**
`claude-haiku-4-5-20251001`, `gpt-4.1-mini`, `grok-4.3`,
`grok-4.20-0309-non-reasoning`, and `gemini-2.5-flash-lite` were reachable on
2026-08-02. Retirements will surface as errors in the affected cell, not as a wrong
number. Run `./run.sh models` first to see what your credentials can currently reach.

The Claude Agent SDK arms additionally need the **Claude Code CLI at 2.1.220** on
`PATH`; the SDK drives it as a subprocess. It is proprietary, must stay a peer
dependency, and must never be vendored (result 8).

## There is no `results/` directory

The probes were run interactively and **their stdout was never captured to a file**.
The finding's tables were transcribed from the terminal. Nothing survives that could
honestly be committed as a run record, and fabricating one would make this harness look
more reproducible than it is. Re-running is the only way to check the integers.

## Gaps — claims in finding 003 that this harness does not reproduce

These are recorded rather than filled. Writing a plausible-looking script for a method
that was not recorded would produce a harness that silently differs from what ran,
which is the failure mode this project has already been bitten by.

| Finding 003 claim | Status | Why |
|---|---|---|
| Result 3 — "probing **seven Anthropic request shapes** against `api.x.ai/v1/messages`, the only one reproducing `Invalid message role` is `system` sent as a message role" | **No script survives.** | The seven shapes are not enumerated in the finding, so which seven were tried cannot be recovered. This is the evidence that the incompatibility is in Claude Code's message envelope rather than in tool-calling or auth — the sharpest claim in the document, and the one with the least surviving support. |
| Result 3 — xAI's endpoint independently returns `200` for `grok-4.3` and handles top-level `system`, list-of-blocks content, `cache_control`, and tool definitions | **No script survives.** | Same probe as above. |
| Result 4 — `POST https://api.openai.com/v1/messages` and `POST https://generativelanguage.googleapis.com/v1/messages` independently return 404 | **No script survives.** | Two one-line HTTP checks, made outside the SDK. `probe_cas.py` covers the OpenAI case *through* the SDK but not the direct verification, and does not cover Gemini at all — the finding's Gemini row was established by the direct check only. |
| Result 6 — Anthropic's two deltas are **87 and 23 characters**, first arriving at **92–97%** of wall time, across **five runs** (0.96, 0.97, 0.92, 0.93, 0.93) | **Partial.** | `probe_adk_stream.py` records partial counts, first-delta timing, and a chunk-length progression for **one** run per provider. The five-run repeat that produced the ratio series was done by hand and no loop survives. One invocation gives you one ratio. |
| Result 8 — licensing: `google-adk` Apache-2.0, `claude-agent-sdk` MIT, **LiteLLM's PyPI metadata declares no license at all** | **No script.** | Established by reading `LICENSE`, `pyproject.toml`, and package metadata. Mechanically checkable, but the exact inspection was not recorded, so nothing is shipped that would imply it was. |
| §Model spend — $0.09 total, $0.064 across six Claude Agent SDK sessions, four billed and two failed before reaching a model | **Partial.** | `probe_cas.py` and `probe_cost_compare.py` print per-run cost. The six-session total was accumulated across an interactive session and is not re-derivable from one pass. |

### One internal inconsistency in the finding, left as found

Finding 003's results table attributes **streaming: pass (79 deltas)** to
`xai/grok-4.3`, while §6's 79-delta figure comes from the 110-character prompt — and
`probe_adk_stream.py`, the script that used that prompt, runs
`xai/grok-4.20-0309-non-reasoning`. `probe_adk.py` does exercise streaming on
`grok-4.3`, but with a short prompt that would not produce 79 deltas.

So the 79 for xAI most likely came from the non-reasoning model and is attributed in
the table to the reasoning one. This is a labelling question, not a change to any
verdict — both xAI models streamed. It is recorded here rather than corrected in the
finding, which is outside this harness's scope.

### A wart in `probe_adk_stream.py`

Its `incremental=YES/NO` column is a heuristic (`len(set(lens)) > 2 and partials > 3`)
and can print `NO` for a provider that emitted many equal-sized deltas. The finding
reports **delta counts and timings**, not that column. Read the counts.

## What changed during recovery

| Change | Why | Affects a measurement? |
|---|---|---|
| `envload.py`: hardcoded private-repo path → `F2A_ENV_ROOT`, required, no default | The original pointed into an unrelated private repository holding live production keys. It must not be committed. | No. |
| `envload.py`: hardcoded `(variable, file)` pairs → tree search with `F2A_GEMINI_VAR` override | The original encoded one machine's layout, including `GEMINI_API_KEY_2` in `control_tower/.env`. | No — same variables, resolved portably. |
| `probe_cas.py`, `probe_cost_compare.py`: `cwd="/tmp/f2a-probe-runtime"` → `envload.workdir()` | Subprocess working directory, honours `F2A_PROBE_DIR`. | No. |
| Provenance paragraph added to each docstring | So a reader opening one script knows where it came from. | No. |
| Added `requirements.txt`, `run.sh` | The original venv was built by hand; no installer survived. Versions are read from the surviving venv, not guessed. | No. |
| Added `count_reasoning_fields.py` | **Reconstructed.** See below. | See below. |

The pins in `requirements.txt` were read directly from the surviving virtualenv at
`/tmp/f2a-probe-runtime/.venv` — `google-adk 2.6.1`, `litellm 1.91.4`,
`claude-agent-sdk 0.2.128`, `google-genai 2.16.0`, `pydantic 2.13.4`, `openai 2.52.0`,
`httpx 0.28.1`, Python 3.12.11 — and match finding 003's method note exactly. The
Claude Code CLI on this machine reports 2.1.220, also matching.

### The one reconstruction, and how far to trust it

`count_reasoning_fields.py` rebuilds result 7's field counts. The original script did
not survive and the finding records the four integers without recording the method.

**The rule it uses is matching source lines** — what `grep -c` reports — over the single
module `google/adk/models/lite_llm.py`. A line mentioning a field twice counts once.
Three defensible rules give three answers against `google-adk==2.6.1`:

| counting rule | `thought_signature` | `thinking_blocks` | `reasoning_content` | `encrypted_content` |
|---|---|---|---|---|
| **source lines containing it** | **35** | **16** | **9** | **0** |
| textual occurrences | 38 | 18 | 11 | 0 |
| whole-word occurrences | 30 | 17 | 11 | 0 |

Only the line rule reproduces the reported integers, and it reproduces all four exactly;
neither other rule matches any of the three non-zero ones. So **35 is a line count, and
finding 003's wording "references … 35 times" is imprecise** — read literally it means
occurrences, which is 38. The finding carries a
[correction](../../findings/003-runtime-provider-agnosticism.md) recording that, dated
2026-08-02; the accurate phrasing is "on 35 lines of".

That still leaves the rule itself an inference **fitted to the numbers it is meant to
reproduce**. One rule matching four integers with no free parameters is strong; it is not
the same as holding the original script. The script prints all three columns so the
choice stays visible.

The claim result 7 actually rests on — that `encrypted_content`, xAI's opaque reasoning
field, appears **zero** times — holds under every rule. **Scope it to the adapter, not to
ADK:** the same 2.6.1 wheel mentions `encrypted_content` on 8 lines (10 occurrences) of
exactly one other file, `google/adk/labs/openai/_openai_responses_llm.py`, where it
decodes OpenAI's field into `part.thought_signature`. That is a different code path and
does nothing for xAI on the one this probe measured.

## Prerequisites

Python 3.12, outbound HTTPS, credentials for Anthropic, OpenAI, xAI, and Google, and
the Claude Code CLI for the two Claude Agent SDK arms. On macOS, do not relax the
LiteLLM pin without reading the hazard above.
