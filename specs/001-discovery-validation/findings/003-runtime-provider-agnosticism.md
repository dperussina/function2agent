# Finding 003 — Can the candidate runtimes actually be driven by a non-default provider?

**Date**: 2026-08-02
**User Story**: 3 (choose the substrate that makes this work most efficiently)
**Model spend**: ≈ $0.09 total against a $2.00 ceiling. Roughly $0.025 estimated across ~50
trivial Google ADK turns on cheap models plus a handful of direct endpoint probes, and $0.064
reported across six Claude Agent SDK sessions, four of which billed and two of which failed
before reaching a model. The asymmetry between those two buckets is itself a finding — see
§The 40x context tax.
**Method**: An isolated virtualenv at `/tmp/f2a-probe-runtime` (Python 3.12.11, `google-adk`
2.6.1, `litellm` 1.91.4, `claude-agent-sdk` 0.2.128, Claude Code CLI 2.1.220). Credentials
were parsed from the target's dotenv files and assigned to `os.environ` in-process; no key
value was printed, logged, copied, or written anywhere. Tool-calling outcomes were decided
programmatically by a side effect recorded inside the Python tool body and by the recorded
call order and arguments, never by reading the model's prose. Structured-output outcomes were
decided by `json.loads` plus pydantic `model_validate`. The vendored repositories under
`examples/` were read but not modified, and `git status --porcelain examples/` reports clean
(FR-018).

## Why this probe

Research tentatively settled on a two-layer substrate: **Google ADK as the outer runtime and
HTTP/SSE serving layer, with the Claude Agent SDK as the executor inside coding nodes.** Both
are *documented* as supporting multiple providers. Neither claim had been verified.

Model-agnosticism is not a nice-to-have here. End users bring their own LLM credentials and
the product cannot dictate which provider they use. Finding 002 closed half of uncertainty
U-03 by proving that raw provider credentials authenticate and enumerate. It explicitly did
not close the other half: whether a candidate *orchestration runtime* can be driven by a
non-default provider. That is this probe.

Tool-calling is the load-bearing capability. The entire product is the synthesis of tools from
a target codebase, so a runtime whose tool-calling only works on its home provider is
disqualified regardless of how well anything else works.

## Results

**Google ADK 2.6.1 via `google.adk.models.lite_llm.LiteLlm`**

| Provider | Model | Completion | Single tool call | Chained 2-tool call | Streaming | Structured output |
|---|---|---|---|---|---|---|
| Anthropic | `claude-haiku-4-5-20251001` | pass | pass | pass | **coalesced, not incremental** | pass |
| OpenAI | `gpt-4.1-mini` | pass | pass | pass | pass (79 deltas) | pass |
| xAI | `grok-4.3` | pass | pass | pass | pass (79 deltas) | **fail** |
| xAI | `grok-4.20-0309-non-reasoning` | not tested | not tested | not tested | pass | pass |
| Google | `gemini-2.5-flash-lite` | pass | pass | pass | pass (4 deltas) | pass |

**ADK drives all four providers, including tool-calling, including chained multi-turn
tool-calling.** Every cell above was decided programmatically. In the chained test the model
had to call `lookup_project("Atlas")`, receive `PRJ-8829`, and pass that exact id to
`get_build_number`; all four providers produced the correct call order with the correct
threaded argument.

**Claude Agent SDK 0.2.128 (Claude Code CLI 2.1.220)**

| Target | Verdict | Evidence |
|---|---|---|
| First-party Anthropic, `claude-haiku-4-5` | **works** | Tool invoked once with the correct argument, result reached the final answer, `provider='firstParty'` |
| xAI `grok-4.3` via `ANTHROPIC_BASE_URL=https://api.x.ai` | **fails** | `terminal_reason: api_error`, `api_error_status: 400`, body `{"code":"invalid-argument","error":"Invalid request content: Invalid message role."}` |
| OpenAI `gpt-4.1-mini` via `ANTHROPIC_BASE_URL=https://api.openai.com` | **fails** | `terminal_reason: api_error`, `api_error_status: 404`. `POST https://api.openai.com/v1/messages` independently returns 404 — the endpoint does not exist |
| Google Gemini via base-URL redirection | **fails** | `POST https://generativelanguage.googleapis.com/v1/messages` returns 404 — the endpoint does not exist |
| Bedrock, Vertex, Foundry, `anthropicAws`, `anthropicGoogleCloud`, Mantle, gateway | **not tested** | No AWS account, no GCP project, no LLM gateway. Recorded as untested, not inferred |

## What this establishes

1. **Google ADK's documented multi-provider support is real, and it survives the capability
   that matters most.** Tool-calling worked on Anthropic, OpenAI, xAI, and Google through the
   same `LiteLlm` adapter and the same agent definition, with only the model string changed.
   Chained two-step tool use, where the second call is only reachable if the first result
   round-tripped intact, also worked on all four. This is the single most important positive
   result in the probe, because it means the outer runtime does not have to be rebuilt to
   satisfy the model-agnosticism requirement.

2. **The Claude Agent SDK cannot be driven by a genuinely different model family, and the
   distinction the documentation invites you to blur is the whole answer.** The SDK's own type
   definition enumerates its provider set as `firstParty`, `bedrock`, `vertex`, `foundry`,
   `anthropicAws`, `anthropicGoogleCloud`, `mantle`, and `gateway`, with `canonicalModel`
   examples like `claude-opus-4-7`. Every one of those is **a different hosting surface for
   Claude models**, not a different model family. Bedrock passthrough means "your Claude
   tokens are billed by AWS," not "you can run Llama." Testing Bedrock or Vertex would
   therefore not have changed this verdict even had credentials been available, which is why
   their absence is recorded as untested rather than treated as a gap in the argument.

3. **The only genuinely cross-family route into the Claude Agent SDK that exists today is
   base-URL redirection, and it failed on the one provider where it could even be attempted.**
   xAI publishes an Anthropic-Messages-compatible endpoint at `https://api.x.ai/v1/messages`,
   which I verified independently returns `200` for `grok-4.3` and handles top-level `system`,
   list-of-blocks content, `cache_control`, and — importantly — **tool definitions, returning a
   `tool_use` block**. Pointing the Claude Agent SDK at it nonetheless failed with HTTP 400
   `Invalid message role`. Probing seven Anthropic request shapes against that endpoint, the
   only one that reproduces that exact error is sending `system` as a *message role* inside the
   `messages` array rather than as the top-level `system` parameter. The incompatibility is
   therefore in the message envelope Claude Code emits, not in tool-calling and not in
   authentication — the request authenticated fine, or it would have returned 401.

4. **OpenAI and Google cannot be reached by the Claude Agent SDK at all, by construction.**
   Neither publishes an Anthropic-Messages endpoint; both return 404 for `POST /v1/messages`.
   There is no configuration that fixes this, because there is nothing on the other end to
   configure against. Worth noting for operability: Claude Code reports this 404 as *"There's
   an issue with the selected model (gpt-4.1-mini). It may not exist or you may not have access
   to it."* That message misattributes a missing-endpoint error to a model-permissions problem,
   and it would cost an operator real time.

5. **Structured output is a property of the (provider, model) pair, not of the runtime, and
   ADK fails at it silently.** ADK does the right thing on the wire: `_to_litellm_response_format`
   emits `{"type": "json_schema", "strict": true, ...}` for OpenAI-compatible providers.
   Despite that, `grok-4.3` returned `'The task is: "Return JSON matching the schema." The
   schema is:\n{\n  "city": "Paris", ...'` — reasoning prose wrapped around the JSON, which
   fails `json.loads` at line 1 column 1. The same code against xAI's
   `grok-4.20-0309-non-reasoning` parsed and validated cleanly. So the failure is the reasoning
   model leaking its chain of thought into `content`, not a hole in ADK's plumbing. **ADK raised
   no exception and surfaced no warning in either case.** A caller who trusts `output_schema`
   gets unparseable text and no signal.

6. **Streaming survives the provider switch in the sense of "events arrive," but not in the
   sense of "the user sees tokens sooner," and Anthropic is the one that degrades.** Asking for
   a 110-character answer, OpenAI and xAI each emitted 79 single-character deltas and Gemini
   emitted 4 growing chunks. Anthropic emitted exactly **2 deltas of 87 and 23 characters, with
   the first arriving at 92–97% of total wall time**, reproducibly across five runs
   (ratios 0.96, 0.97, 0.92, 0.93, 0.93). That is coalescing, not streaming: the time-to-first-token
   benefit is approximately zero on the provider whose models we would otherwise default to.

7. **ADK explicitly handles provider-opaque reasoning state, with one gap that maps exactly onto
   constitution Principle V.** The LiteLlm adapter references `thought_signature` 35 times,
   `thinking_blocks` 16 times, and `reasoning_content` 9 times. It references
   `encrypted_content` — xAI's opaque reasoning field — **zero times.** Principle V requires
   that provider-opaque reasoning state be round-tripped verbatim and warns that dropping it
   "degrades multi-turn tool use silently rather than erroring." Chained tool use did work on
   xAI in this probe, so the gap did not bite at two hops on a trivial task; that is a weak
   result and should not be read as clearance.

   > **Correction, 2026-08-02 — "35 times" is a count of matching source lines, not of
   > references, and the distinction was not stated. See
   > [`harness/runtime-provider-agnosticism/count_reasoning_fields.py`](../harness/runtime-provider-agnosticism/count_reasoning_fields.py).**
   >
   > What was believed: that "references `thought_signature` 35 times" was unambiguous.
   >
   > What is now known: it is not, and the three figures are reproducible under exactly one
   > of the three defensible readings. Against `google/adk/models/lite_llm.py` at the pinned
   > `google-adk==2.6.1`:
   >
   > | counting rule | `thought_signature` | `thinking_blocks` | `reasoning_content` |
   > |---|---|---|---|
   > | **source lines containing the identifier** (`grep -c`) | **35** | **16** | **9** |
   > | textual occurrences | 38 | 18 | 11 |
   > | whole-word identifier occurrences | 30 | 17 | 11 |
   >
   > **The reported figures are matching-line counts and are correct as such.** Read
   > literally, "references N times" means occurrences, which is 38 / 18 / 11; read strictly
   > as identifier references it is 30 / 17 / 11, because seven of the 35 lines mention
   > `thought_signature` only inside the longer names `_decode_thought_signature` and
   > `_extract_thought_signature_from_tool_call`. Substitute "on 35 lines of" for "35 times"
   > wherever these numbers are quoted.
   >
   > What caused the difference: the original script did not survive and the finding recorded
   > the integers without recording the rule. The rule was re-derived by testing candidates
   > against the four reported values; the matching-line rule reproduces all four exactly and
   > no other candidate reproduces any of the three non-zero ones.
   >
   > **Scope of this correction.** No claim moves. `encrypted_content` is **zero under every
   > rule**, and that zero is the whole of result 7's argument. One clarification worth
   > carrying: zero is a property of the **LiteLlm adapter**, which is how this result is
   > scoped, and not of `google-adk` as a whole — the same 2.6.1 wheel mentions
   > `encrypted_content` on **8 lines** (10 occurrences) of exactly one other file,
   > `google/adk/labs/openai/_openai_responses_llm.py`, where it decodes OpenAI's field
   > into `part.thought_signature`. That is the round-trip Principle V asks for, on a
   > different code path, and it does nothing for xAI on the path this probe measured.

8. **Licensing is clean on the ADK path and has one unresolved edge.** `google-adk` 2.6.1 is
   Apache-2.0, verified from the `LICENSE` file and the `pyproject.toml` classifier in the
   vendored repository rather than from documentation. `claude-agent-sdk` 0.2.128 declares MIT
   in its package metadata, consistent with prior work; the Claude Code CLI it drives remains
   proprietary and must be a declared peer dependency, never vendored. **LiteLLM is the ragged
   one: its PyPI metadata declares no license at all** — the `License` field is empty and there
   are no license classifiers. The repository `LICENSE` is MIT except for everything under
   `enterprise/`, which is covered by a separate proprietary license. Any emitted pack that
   depends on ADK's multi-provider path inherits that split, and an automated license scan of
   the installed wheel will find nothing to scan.

   > **Acted on 2026-08-03 — [`plan.md` OD-16](../plan.md): `litellm` is not shipped.** The
   > undeclared package license is the reason, and it is a *shipping* question rather than a
   > development one: a component whose license cannot be determined is a legal exposure in a
   > product sold to customers, and this finding is the only place it was ever recorded. v1 reaches
   > each provider through that vendor's own SDK behind a driver of ours. **OD-15**, dropping ADK,
   > is what made the removal cheap — `litellm` was in the tree as a transitive dependency of the
   > documented multi-provider path.

## The catch: LiteLLM does not ship a macOS wheel, and nothing says so

**The documented ADK multi-provider path cannot be installed on macOS without a Rust
toolchain.** `pip install litellm` for the current release, 1.95.0, fails on this machine with:

```
error: could not execute process `rustc -vV` (never executed)
💥 maturin failed
```

LiteLLM 1.95.0 publishes 15 wheels: `manylinux_2_28_aarch64`, `manylinux_2_28_x86_64`, and
`win_amd64`, for CPython 3.10 through 3.14. **Zero macOS wheels.** Scanning the release history,
the last version to ship a pure-Python `py3-none-any` wheel was **1.91.4**; from 1.92.0 onward
LiteLLM switched to compiled platform-specific wheels and left macOS out. On macOS the resolver
therefore falls back to the sdist and demands `maturin` and `rustc`.

This probe ran on `litellm==1.91.4`, the last pure-Python release, which still satisfies ADK's
declared `litellm>=1.84` constraint. **Every ADK result above is therefore measured against
1.91.4, not against current LiteLLM**, and that is a real limit on what the results cover.

Three consequences worth carrying forward. First, this is exactly the class of undocumented
prerequisite User Story 3 exists to find: ADK's docs describe `LiteLlm` as the multi-provider
answer and say nothing about needing a Rust compiler on the most common developer laptop
platform. Second, if generated agent packs depend on ADK's multi-provider path, they inherit
this: a customer on an Apple-silicon laptop hits a Rust build failure on install, and the error
text mentions neither ADK nor providers. Third, it is a live argument for keeping the bottom
provider tier ours and thin, per Principle V — the two-tier abstraction exists precisely so that
a packaging decision inside a third-party middleware dependency is not a customer-facing install
failure.

> **Where this landed, 2026-08-03, and the ordering matters.** The wheel gap was **found first, was
> correct, and is what put anybody on the packaging question at all** — the third consequence above
> is the argument [`plan.md` OD-16](../plan.md) ultimately acted on. **But it is not why `litellm`
> was dropped.** OD-16 drops it for the **undeclared license** recorded in result 8, and the wheel
> gap is **moot as a shipping question**: production is a Linux container, and **OD-17** makes Linux
> the only supported platform, so this was always the developer-environment problem this section
> classifies it as. **The license is the reason it became a shipping decision; the wheels are the
> reason somebody was already looking.** This note exists so the record is not later read as though
> the license had been the only concern.

## The 40x context tax

Running the identical task — one tool call, report the number — on the identical model
(`claude-haiku-4-5-20251001`) through both runtimes:

| Runtime | Input tokens | Output tokens | Cost (USD) |
|---|---|---|---|
| ADK 2.6.1 + LiteLLM | 1,336 | 73 | 0.0017 (computed at list price) |
| Claude Agent SDK 0.2.128 | 53,859 | 344 | 0.0083 (reported by the SDK, warm cache) |

The Claude Agent SDK consumed **40 times the input context** for the same work. On a separate
cold-cache run the same task reported 53,811 input tokens at **$0.0284**; the warm figure above
is the steady state. The breakdown on a third run was 28 fresh input tokens, 440 cache-creation
tokens, and **53,418 cache-read tokens** — that is the Claude Code harness system prompt and its
built-in tool definitions, which are cached and therefore discounted, but which still occupy the
window. So the cost penalty is 4.9x warm and 16.7x cold, while the *context* penalty is a flat
40x regardless.

This is a fair comparison in the one respect that matters — same model, same provider, same
task, one variable — but it is not a criticism of the SDK on its own terms. That 53k of context
is the harness: the tool suite, the context-management behavior, and the coding competence that
made it the top-rated harness in the survey. You are paying for something. The point is that
**you pay it per node**, and `function2agent` proposes to emit many nodes. Roughly 54k tokens of
harness context is spent before a single synthesized tool from the customer's codebase enters
the window, which directly constrains how large a synthesized tool catalog a coding node can
hold.

## What this does NOT license

- **Nothing about ADK on current LiteLLM.** Every ADK result was measured on `litellm==1.91.4`
  because 1.95.0 will not install here without Rust. Provider behavior may differ on the
  current release, and this probe cannot say.
- **Nothing about providers beyond the one model tested on each.** One model per provider was
  exercised: `claude-haiku-4-5`, `gpt-4.1-mini`, `grok-4.3`, `gemini-2.5-flash-lite`. Result 5
  is the direct proof that this does not generalize — two models from the *same* vendor
  disagreed on structured output. Do not read "xAI works" or "xAI fails" into this document;
  read "grok-4.3 did this, grok-4.20-non-reasoning did that."
- **Nothing about Bedrock, Vertex, Foundry, Mantle, or gateway routing for the Claude Agent
  SDK.** Untested for want of credentials. The argument in result 2 is that they are
  Claude-hosting surfaces and so cannot answer the model-agnosticism question, but that is an
  inference from the SDK's own type definitions, not a measurement.
- **Nothing about whether a shim could rescue the Claude Agent SDK.** Per User Story 3
  acceptance scenario 3 the xAI 400 was recorded as a disqualification and not engineered
  around. A proxy that rewrote the offending `system` message might well work; that is an
  untested hypothesis, and it would mean owning a proxy in the customer's prompt path.
- **Nothing about quality, latency at scale, rate limits, or cost at realistic prompt sizes.**
  Every prompt here was trivial by design. The 40x context figure is a floor measured on an
  empty task, not a projection for a real one.
- **Nothing about ADK's HTTP/SSE serving layer, sessions, graph workflows, or Agent Engine
  coupling.** This probe exercised `LiteLlm` plus `InMemoryRunner` only. The serving layer that
  motivated the ADK recommendation in the first place is still unverified.
- **Nothing about concurrency, parallel tool calls, or long-running sessions.** Single-threaded,
  one session per cell, at most three model turns.

## Immediate next steps

1. **Treat the two-layer substrate as confirmed on the outer layer and unresolved on the inner
   one.** ADK is verified model-agnostic for tool-calling across four families, so the
   adopt-for-the-runtime-layer recommendation survives. The Claude Agent SDK is verified
   Anthropic-only for any genuinely different model family, which means the inner executor
   cannot be the sole coding-node implementation if model-agnosticism is a hard requirement.
   Either the requirement is relaxed for coding nodes specifically, and that is written down as
   a deliberate trade, or coding nodes need a second executor. This is now a decision the owner
   has to make, not an open research question.
2. **Verify ADK's HTTP/SSE serving layer next.** It is the other half of why ADK was chosen and
   it is entirely unprobed. A runtime that is model-agnostic but whose serving surface does not
   fit the integration-surface requirements would move the recommendation again.
3. **Re-run the ADK matrix against current LiteLLM on Linux.** That removes the 1.91.4 caveat
   and simultaneously confirms whether the macOS wheel gap is the only packaging problem. Do it
   in a container so the result is portable and reproducible per SC-005.
4. **Add a structured-output validation gate to the harness, and eventually to emitted packs.**
   Result 5 shows a provider can silently return unparseable text under a strict schema request.
   Parsing and validating the response, then failing loudly, is a few lines and is the same
   fail-loudly posture constitution Principle IV requires at startup and finding 002 recommended
   for credentials.
5. **Record `encrypted_content` as a known gap in ADK's LiteLlm adapter** against Principle V,
   and design a test that would actually catch opaque-state loss — a long chained tool sequence
   on a reasoning model, not the two-hop trivial case that passed here.
6. **Price the coding-node design against the 40x context tax before committing to it.** If a
   coding node carries roughly 54k tokens of harness before any synthesized tool, that is a
   budget constraint on tool-catalog size per node and it belongs in the decomposition
   decision, not discovered later.
