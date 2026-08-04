# 15 — NVIDIA OO Agents: Does an Object-Oriented Harness Change What v1 Builds?

**Last researched: 2026-08-04**

---

## Why this is in `research/` and not `findings/`

`findings/` holds measurements this project took of its own system under a design written before
the run. This document takes no such measurement: it reads an external substrate against decisions
already recorded, which is the genre [`13-claude-managed-agents.md`](./13-claude-managed-agents.md)
established — same question shape (*does this hosted/external thing replace what we are building?*),
same method (read the source, not the marketing), same output (a coverage matrix and a recommendation).
The static counts below over the vendored tree are observations made in service of that synthesis,
not experiments, and they are labelled as such in §7. `research/` is where the registers live and
where §9's proposed entries have to land, which settles it.

---

## TL;DR — Key takeaways

> 1. **The one thing worth borrowing cannot be borrowed under our enforcement model, and NOOA's own
>    code says why.** NOOA's headline efficiency result — parity or better on SWE-bench at
>    ~~roughly half the tokens of the comparison harnesses~~ **corrected 2026-08-04 against
>    [the paper's §4.2](https://arxiv.org/abs/2607.20709), read directly, and the plural was the
>    error: half the tokens of *one* comparator and about fifteen percent fewer than the other.** With
>    GPT-5.5 at xhigh, NOOA takes ~28 calls and 1.1M tokens for 82.2%; **OpenCode takes a similar call
>    count and ~1.3M for 78.6%**; PI takes 66 calls and 2.2M for 78.2%. **PI's excess travels with a
>    call count more than twice NOOA's, so it is not attributable to serialization alone — and
>    OpenCode, not PI, is the pair that isolates the mechanism.** The saving is
>    attributed to *pass by reference*: tool results
>    stay live Python objects instead of being serialized into the transcript. Its paper states the
>    tradeoff outright: *"Executing in-process is what preserves pass by reference; sandboxed code
>    modes trade it away, receiving serialized copies at the sandbox boundary."* The code shows the
>    escape hatch it uses to keep both — `SandboxedExecutor._dispatch_tool_call` brokers every
>    `self.<path>` access and call **back to the unsandboxed parent process** — which means the
>    efficiency mechanism and the containment gap are the same mechanism. **A v1 that keeps its
>    kernel boundary cannot adopt the win as designed.** What is actionable is the question, not the
>    answer: ~~nobody here has measured how much of the token saving survives serialization at a
>    boundary. That is §10's one candidate for authorised work.~~ **Corrected 2026-08-04 — the
>    question is one level up, because under **FR-004** v1's surface returns bytes and holds no live
>    objects, so the mechanism is absent by construction rather than degraded.** What nobody has
>    measured, and what no requirement governs, is **the token cost of bulk tool output entering our
>    transcript at all**. Landed as `U-50`; §10 carries the two authorised arms, neither run.
>    **Added 2026-08-04, and it shrinks the prize rather than moving it: the paper undercuts its own
>    novelty on the mechanism, and E7's own traces show the baseline already improvising it.** §3
>    says *"Models already improvise this pattern in bash – spilling results to files and processing
>    them with follow-up commands; NOOA replaces the untyped text on disk with typed, live variables
>    that persist from cell to cell"*, and §6 calls file handles *"a variant of pass by reference"*
>    that is *"powerful"* but *"loses all type information."* So NOOA's increment over a
>    command-execution surface is **type preservation, not the token saving** — the saving is
>    available to a bytes-returning surface. And E7's shell arm did improvise it: ~~**36 of 109 arm-B
>    task-attempts spill output to a file** and 31 read one back~~ **corrected 2026-08-04 by
>    [finding 022](../specs/002-spec-aware-agent-runtime/findings/022-e7-tool-result-truncation-cap.md):
>    32 of 109 E7 arm-B (shell) attempts spill *command output* to a file and 31 read one back — the
>    four the published count added wrote only a heredoc script**, so part of the headroom `U-50` asks
>    about was already inside E7's measured figure. **The direction of `U-50` is unchanged and is not
>    reopened** — headroom above a measured baseline, never exposure to it. What changed is its size,
>    and it changed again the same day for a bigger reason: **E7's baseline never inlined bulk output
>    at all. It capped every tool result at 6,000 characters in both arms** — roughly 1,500 tokens —
>    so the surface D-19's advantage was measured on is a *truncating* one, and the prize `U-50`
>    tracks is the gap from that cap down to a bounded preview rather than the gap from an unbounded
>    result down to one.
> 2. **NOOA does not corroborate E7, and the reason is that it never ran the experiment.** There is
>    no arm anywhere in the paper isolating code-as-action against a curated per-application tool
>    surface. Every comparison is whole-harness against whole-harness with at least five co-varying
>    factors. It is *directionally consistent* with E7 and it is not independent evidence for it.
> 3. **Their capability instrument has the same defect ours does, and this is the useful result.**
>    E7's tool arm sat at 1.00 on 27 of 41 tasks against a pre-registered calibration band of
>    0.25–0.85, which is why D-19 says two of its three families support no conclusion in either
>    direction. NOOA's capability suite passes 4,309 of 4,400 records (97.9%), with GPT-5.5 at
>    440 of 440 (100%). **Our own pre-registered band would reject their instrument outright.**
>    Their evidence is broader and worse calibrated; ours is narrower and better calibrated; neither
>    tests the proposition. Rule 8's tell — a perfect score with no negative control — is present.
> 4. **Of U-48's nine capabilities it credibly supplies three, partially supplies four, and does not
>    supply two — but the accounting is worse than the count.** The per-provider cost table, one of
>    the three it supplies, arrives through `litellm.completion_cost`, which is the dependency
>    **OD-16** removed. Tool-schema translation, the largest row in the re-derived estimate, is
>    **measured non-compliant with FR-037 by the same counting rule finding 003 used on ADK**:
>    `thought_signature`, `encrypted_content` and `reasoning_details` occur **zero** times in the
>    entire NOOA tree, and the assistant message it puts back on the wire carries `role`, `content`
>    and `tool_calls` and nothing else. §4.
> 5. **Two of its capabilities are actively hazardous to inherit, not merely absent.**
>    `_map_completion_finish_reason` collapses every provider stop condition into four values with
>    `return "stop"` as the catch-all, so an unrecognised terminal reads as a normal completion —
>    the false-success shape [`03`](./03-graph-and-loop-architecture.md) §3 names as expensive, and
>    the shape finding 006 measured in ADK. And `SQLiteStorageManager`'s own docstring says
>    *"an attacker who can modify it gains arbitrary code execution on restore"*; snapshot restore
>    resolves stored dotted names through `importlib.import_module` and `markers.py` reaches `eval`.
>    A session store that is an RCE sink on resume is not a session store we can take.
> 6. **Tool synthesis is relocated, not removed, and NOOA's own ARC-AGI-3 and CyberGym agents are
>    the proof.** Both hand-place deterministic gates as ordinary typed methods — a submission
>    method, a summary-match judge, a re-submission check. Those *are* promotion selection and
>    effect classification, performed by a human. Making methods the tool interface removes schema
>    authoring, which D-06 already called the commodity part. It leaves which functions to promote,
>    what each one does to the world, and what a verifiable postcondition is exactly where D-21 put
>    them. §5.
> 7. **On safety the paper, the blog and the code agree, and they agree with our hypothesis.** NOOA's
>    §7 Limitations: *"NOOA executes model-written code in the agent's own process. The validator …
>    protects the agent loop, not the host … sandboxing … goes around the agent process."* The blog
>    says *"For production deployment, NOOA pairs with the NVIDIA OpenShell secure runtime."* The
>    `execution_backend` default is `"inprocess"`. **NOOA is a candidate for the layer above our
>    enforcement point and is not a candidate to replace it** — which is the distinction the brief
>    asked for, now supported by vendor testimony rather than inference. §6.
> 8. **Its evaluation carries one flat contradiction against its own tables.** *"Increasing reasoning
>    effort improves all three harnesses"* is false in at least four cells of Tables 3 and 4 — most
>    sharply OpenCode on Terminal-Bench GPT-5.5, which drops from 60.7 at high effort to 52.8 at
>    xhigh. On an 89-task single-run benchmark with no confidence intervals, that is a noise floor
>    announcing itself, and the margins the paper reads off those points are narrower than it. §7.
> 9. **For `function2agent`: interesting, and load-bearing in exactly one place.** Nothing here
>    changes OD-09, OD-15, OD-16, OD-17 or D-21. Nothing licenses reducing U-48's estimate. It is
>    **not** adoptable as a substrate: it hard-depends on the dependency OD-16 removed, NVIDIA calls
>    it a *research preview*, and its containment story terminates in a different NVIDIA product.
>    The one live consequence is bullet 1's unmeasured question, and §9's ~~proposed~~ **landed**
>    register entries carry it — `U-50` and `C-20` as new rows and an annotation on `U-48`, all three
>    in place 2026-08-04, with `U-50` landed under the corrected framing §9 records.

---

## Table of contents

1. [What NOOA is, from the source](#1-what-nooa-is-from-the-source)
2. [Q1 — does it corroborate E7?](#2-q1--does-it-corroborate-e7)
3. [Q2 — the nine U-48 capabilities, module by module](#3-q2--the-nine-u-48-capabilities-module-by-module)
4. [The two capabilities that are worse than absent](#4-the-two-capabilities-that-are-worse-than-absent)
5. [Q3 — does it make v2's tool synthesis unnecessary?](#5-q3--does-it-make-v2s-tool-synthesis-unnecessary)
6. [Q4 — safety, licence, and dependency posture](#6-q4--safety-licence-and-dependency-posture)
7. [Reading their evaluation](#7-reading-their-evaluation)
8. [The three-way split, and what adoption would cost](#8-the-three-way-split-and-what-adoption-would-cost)
9. [Proposed register entries](#9-proposed-register-entries)
10. [What can only be settled by running their code](#10-what-can-only-be-settled-by-running-their-code)
11. [Sources](#11-sources)

---

## 1. What NOOA is, from the source

Read-only from `examples/labs-OO-Agents/`, Apache-2.0, plus the
[technical report](https://arxiv.org/abs/2607.20709) and the
[developer blog](https://developer.nvidia.com/blog/six-agent-harness-capabilities-for-higher-model-performance/).

An agent is a Python class. Fields are state, methods are capabilities, docstrings are prompts,
type annotations are validated contracts. A method with an `...` body is completed at runtime by an
LLM loop; a method with a real body is ordinary Python. The model acts by writing Python in a
persistent REPL with `self` in scope, so a capability is invoked as `self.method(x)` rather than as
a JSON tool call against a schema.

The load-bearing modules, verified by reading them:

| Concern | Module | Size |
|---|---|---:|
| Agent base, method interception | `src/nooa/agent.py` | 2043 |
| Loop, cell execution, LLM bridge | `src/nooa/runtime/actor.py` | 2364 |
| CodeAct strategy (iterative REPL) | `src/nooa/strategies/codeact.py` | 1201 |
| Provider transport | `src/nooa/unifiedllm/unifiedllm.py` | 2810 |
| Session store and event backend | `src/nooa/storage/sqlite.py` | 1360 |
| Snapshot IR and restore | `src/nooa/storage/snapshot.py` | 219 |
| Opt-in OS sandbox | `src/nooa/runtime/sandbox/` | 10 files |
| AST cell guard | `src/nooa/runtime/code_validator.py` | 620 |
| Trace viewer (FastAPI + React) | `src/nooa/viewer/` | 10 modules |

Two structural facts decide most of what follows. **First, `execution_backend` defaults to
`"inprocess"`** (`src/nooa/config/strategy_config.py:80`); the OS sandbox is opt-in, and NVIDIA's own
ARC-AGI-3 appendix calls it *"an opt-in per-cell OS sandbox."* **Second, when the sandbox is on, it
does not contain the capability surface**: `SandboxedExecutor._dispatch_tool_call` walks
`self.<path>` and executes the call — or a `setattr` — against the parent's live agent, outside every
guard. `readonly.py`'s own docstring states the rule in one line: *"Only `self.*` brokers to the live
parent."*

---

## 2. Q1 — does it corroborate E7?

**No. It is directionally consistent and it is not corroboration, because the experiment that would
corroborate E7 does not appear anywhere in the paper.**

E7 compared a shell-and-spec baseline against a curated per-application tool surface, same model,
same target application, same task set, per family, with a pre-registered pivot criterion. It found
the curated surface never wins on success rate — lookups 27/27 against 26/27, joins 9/10 against
10/10, per-record 4/4 to the baseline against 2/4 — and the cost advantage replicating everywhere
(D-19, [finding 012](../specs/001-discovery-validation/findings/012-ceiling-test-per-family.md)).
That is a **within-application, single-factor** comparison of two action surfaces.

NOOA's benchmarks compare **NOOA against OpenCode 1.14.33 and PI v0.72.1**, whole harness against
whole harness. Its own §5 lists six co-varying interface ideas — typed I/O, pass-by-reference, code
as action, programmable loops, explicit object state, model-callable harness APIs — and the paper is
explicit that it is the *combination* it claims novelty for. So a NOOA win over OpenCode is
consistent with code-as-action mattering, with typed termination mattering (§4.2's own trace analysis
attributes a large share to exactly that), with the loop being better tuned, or with the baselines
being run at their defaults by the people who built the treatment. Nothing in the design separates
these. There is no NOOA-with-curated-tools arm and no NOOA-without-code-mode arm.

**Which evidence is stronger is not a single ordering, and the honest answer has two halves.**

| | E7 | NOOA capability suite |
|---|---|---|
| Isolates the action surface | **Yes**, single factor | No, at least five co-varying |
| Scale | 41 scored tasks, one model, one application | 88 tests, five runs, ten models |
| Repeats | Single attempt everywhere (U-42) | Five per pair; 94% of pairs pass all five |
| Instrument calibrated | **No** — 1.00 on 27 of 41 against a 0.25–0.85 band | **No** — 97.9% overall, one model at 100% |
| Negative control | None | None |

**The instrument defect is the finding, and it is symmetric.** OD-04 pre-registered a calibration
band of 0.25–0.85 for E7 and refused to swap the primary metric when the tool arm pinned at the
ceiling; D-19 records the consequence as *"the two tied families support no conclusion in either
direction."* NOOA's suite sits at 97.9% aggregate with a model at 440 of 440 — **far outside the
band this project uses to decide whether its own instruments can discriminate.** Applying our rule
to their number is not a rhetorical move; it is the same rule that forced us to disqualify two of
our own three families.

Rule 8 is satisfied in full: the positive result is the absence of a failure signal, the score is
perfect in one cell, and no negative control exists — no deliberately-degraded interface variant
scored by the same suite to demonstrate it can produce interface-attributable failures. Without
that, 97.9% is equally consistent with *the interface is easy* and *the tests are easy*.

Rule 6 is a live concern and the paper supplies the evidence against itself: the suite is *"included
in the NOOA repository"*, was written by the interface's authors, and is described as *"focused
integration tests."* Integration tests written during development are exactly the artifacts that
prompt repairs to the thing they test. The paper does not claim the suite was frozen before the
interface stabilised, and if it was not, the instrument postdates the repair.

Rule 7 bites on the denominator. 4,400 is 88 tests × 5 runs × 10 models. The unit of independent
evidence about *the interface* is the test family, of which there are 36. Rerunning one test on one
model five times measures sampling variance, not comprehension, and pooling across ten models pools
model capability into an interface claim. The paper's own honest framing is present — *"of the 880
(test, model) pairs, 94% pass all five runs"* — but the headline uses the inflated denominator.

**The one place NOOA gets closer to something we care about is cost, not capability.** §4.2 reports
82.2% on SWE-bench Verified with roughly 28 model calls and 1.1M tokens per task against PI's 78.2%
at 66 calls and 2.2M, and attributes the gap to tool outputs staying live rather than round-tripping
as text. Cost is where OD-09 repositioned the product. That is the transferable claim, and §10 says
what would have to be run to know whether it survives a sandbox boundary.

**Both comparators, because quoting only PI overstates the mechanism — added 2026-08-04 after
reading [§4.2](https://arxiv.org/abs/2607.20709) directly.** The same sentence continues:
*"OpenCode uses a similar number of calls but approximately 1.3 million tokens for 78.6%."* So the
saving is **half against PI and about fifteen percent against OpenCode**, and the second is the one
that isolates the mechanism, because it is the comparator whose call count matches NOOA's. PI's
2.2M travels with **66 calls against NOOA's 28** — two and a third times as many round trips — so
its excess cannot be attributed to serialization alone, and a document that quotes only the PI pair
is reading a call-count difference as a serialization difference. The paper itself quotes only the
PI pair when it makes the mechanism claim, three paragraphs later; the OpenCode figure appears once,
in the paragraph above it.

**What this does not license.** It is not a finding that NOOA contradicts E7. It is not a finding
that E7 is wrong. It is a finding that the two experiments do not speak to each other, and that
neither instrument was calibrated to discriminate on the question both are quoted for.

---

## 3. Q2 — the nine U-48 capabilities, module by module

U-48 names nine: the agent loop, the runner, the session store, checkpoint and resume, tool-schema
translation, the per-provider cost table, a spend backstop replacing `max_llm_calls`, the raw
terminal signals, and the event stream. The day figures below are `tasks.md`'s re-derived estimate,
quoted so a reader can see what a *supplies* verdict would actually be worth.

| # | Capability | Verdict | Module | Days at stake |
|---|---|---|---|---:|
| 1 | Agent loop | **Supplies** | `runtime/actor.py`, `strategies/codeact.py`, `agent.py` | 8–11 |
| 2 | Runner | **Partial** | `packages/nooa-cli/`, `packages/nooa-bench/` | 3–4 |
| 3 | Session store | **Supplies, with a disqualifying property** | `storage/sqlite.py`, `storage/snapshot.py` | 5–7 |
| 4 | Checkpoint and resume | **Partial** | `storage/snapshot.py` + event replay | 12–17 |
| 5 | Tool-schema translation | **Partial and measured non-compliant** | `unifiedllm/unifiedllm.py` | 15–20 |
| 6 | Per-provider cost table | **Supplies, via the removed dependency** | `tracing/_litellm_patch.py` | 2–3 |
| 7 | Spend backstop | **Does not supply** | — | 4–5 |
| 8 | Raw terminal signals | **Does not supply; normalises them away** | `unifiedllm/unifiedllm.py:1484` | 4–6 |
| 9 | Event stream and serving surface | **Partial, wrong surface** | `events.py`, `viewer/` | 6–9 |

**1 — Agent loop. Supplies.** `runtime/actor.py` is a real loop: LLM call, cell execution, event
append, state update, typed return validation. `strategies/codeact.py` is the iterative REPL variant
and `PredictStrategy` the single-shot one. It is a bare loop, which is the right shape for a v1 that
emits no graph (D-05, OD-15). This is the strongest of the nine.

**2 — Runner. Partial.** There are two runners and neither is the one U-48 means. `nooa-cli` is an
interactive CLI/TUI; `nooa-bench` is a benchmark harness whose `runtime/token_usage.py` docstring
addresses *"runner.py"* in a Harbor evaluation context. Neither is a service runner that accepts a
session handshake from a serving layer, which is what T046–T047 sizes.

**3 — Session store. Supplies the mechanism, with a property that disqualifies it.** `SQLiteStorageManager`
is a genuine event backend plus snapshot store on stdlib `sqlite3`, with a PID lock file preventing
two processes opening one session. It is more than we have. **But its own docstring reads:
*"Security: Snapshot restore executes stored Python source code via `exec()`. The database file must
be treated as trusted input — an attacker who can modify it gains arbitrary code execution on
restore."*** The mechanisms are `storage/serialization.py`'s `importlib.import_module` over dotted
names read from the database, and `storage/markers.py`'s `eval` of dynamic context expressions. See §4.

**4 — Checkpoint and resume. Partial, and partial in the way finding 006 already measured.**
`AgentSnapshot` captures context blocks, picklable attributes and a type allowlist; the SQLite event
log replays; `TuiSessionResumed` marks the seam. What is not captured is the CodeAct REPL namespace —
the live objects that pass-by-reference exists to hold. So resume is **session-level, not turn-level
and certainly not cell-level**, which is the same *"zero granularity inside a node"* verdict finding
006 returned against ADK's resumability. Row 4 was re-derived under OD-10 with a finer requirement
than this meets.

**5 — Tool-schema translation. Partial, and measured non-compliant.** `unifiedllm.py` normalises to
the OpenAI wire shape and hands off to litellm, with real per-provider repair work in it (a Bedrock/
Anthropic rule requiring `tools=` whenever tool-call blocks are present, an XML tool-call extractor
for Nemotron on vLLM). **Applying finding 003 result 7's counting rule to the whole NOOA tree —
`src/`, `packages/`, `tests/` — gives zero occurrences of `thought_signature`, zero of
`encrypted_content`, zero of `reasoning_details`, zero of `signature_delta`, zero of
`redacted_thinking`.** `reasoning_content` appears in ~~nine files~~ **thirteen files under `src/`
and twenty-three across `src/`, `packages/` and `tests/` — re-measured 2026-08-04 with `grep -rl`,
and the earlier figure named no directory at all, which is why it could not be checked.** The split:
`src/` 13, `packages/` **0**, `tests/` 10; of the thirteen, nine are Python, three are viewer
frontend sources and one is the committed minified bundle those three compile into, so **22 is the
hand-written-file count and 23 counts the build artifact**. **The substantive claim survives the
re-measurement and was re-verified rather than assumed: every one is observability** — tracing
spans, the ATIF export, the viewer, the event model, a retry trigger for a model that returns
reasoning with empty content, and a fallback that reads structured-output JSON out of the reasoning
field when a model puts it in the wrong place. The object that goes back on the wire is
built at `unifiedllm.py:1848` and carries `role`, `content`, `tool_calls`. Nothing else — confirmed
2026-08-04 by reading every construction site of `assistant_message` in `src/`, none of which
carries the field, and `_extract_reasoning_and_usage` returns it onto a sibling `LLMResponse.reasoning`
attribute that no request path reads. **This is
the identical defect, on the identical axis, that OD-15 cited as one of three grounds for dropping
ADK** — and it is the row worth 15–20 days, so this is the capability where a *supplies* verdict
would have mattered most and the evidence is the least favourable.

**6 — Per-provider cost table. Supplies, through `litellm`.** `tracing/_litellm_patch.py` calls
`litellm.completion_cost` and `litellm.cost_per_token` and stamps OpenInference `llm.cost.*` span
attributes. There is no NOOA-authored price map. So the one row where NOOA cleanly owns something we
sized as *data plus a fail-closed path* is owned by the package **OD-16** removed for its undeclared
licence. Taking the capability means taking the dependency.

**7 — Spend backstop. Does not supply.** Every ceiling in the configuration surface is a *token or
character* bound: `max_iterations`, `max_context_tokens`, `max_event_tokens`, the truncation budgets
in `config/truncation_config.py`. Cost is computed and *recorded* — `events.py:546` carries
`cost_usd`, `atif/exporter.py` sums it into `total_cost_usd` — and nowhere compared against a limit.
`runtime/token_usage.py` accumulates per-task tokens in a `ContextVar` for reporting. **There is no
money ceiling, cumulative or otherwise**, which leaves U-30 exactly where OD-15 left it and gives
FR-005's four cumulative-across-resume ceilings nothing to inherit.

**8 — Raw terminal signals. Does not supply, and destroys them.** See §4.

**9 — Event stream and serving surface. Partial, and it is the wrong surface.** `events.py` is a good
typed event model — `BeforeTurn`, `AfterTurn`, `LLMOutput`, `PythonOutput`, `Reasoning`, `Error`,
`Summary`, `Task` — and the SQLite backend persists it. But the only HTTP surface is
`src/nooa/viewer/`, a FastAPI trace explorer with a React frontend and an OTLP store, and the only
`StreamingResponse` in the tree is `viewer/trace_routes.py:413`. That is **observability, not agent
serving**: there is no endpoint that accepts a task and streams the agent's events to a caller. The
viewer's auth is better than the average vendored example — loopback-only by default, fail-closed for
non-loopback, `hmac.compare_digest` against `NOOA_VIEWER_AUTH_TOKEN` — and is worth noting because
credit is owed where it is due, but it does not make it the surface T069–T072 sizes.

**Score: three supplied, four partial, two absent — and the qualifications invert the count.** Of the
three supplied, one arrives via the dependency OD-16 removed and one is an RCE sink on resume. The
largest row in the estimate is the one that is measured non-compliant. **A framework that owns four
of nine would change the plan; this one does not reach that, and the two it most cleanly owns are the
two we cannot take.**

---

## 4. The two capabilities that are worse than absent

Recorded separately because *absent* and *present-and-hazardous* are different conditions and the
second is easier to inherit by accident.

**Terminal signals are normalised into four values with a silent catch-all.** `LLMResponse.finish_reason`
is `Literal["stop", "tool_calls", "length", "error"]`. `_map_completion_finish_reason` reads the
provider's raw string, maps `length`, `tool_calls`, `content_filter` and `error`, **and returns
`"stop"` for everything else**, including the `None` it substitutes when the field cannot be read.
A provider emitting a refusal, a pause, a safety stop, a max-turn signal, or any terminal NOOA does
not enumerate is therefore reported to the loop as a normal completion.
[`03`](./03-graph-and-loop-architecture.md) §3 names this shape *"a very common and very expensive
bug"*; finding 006 measured its ADK instance, where a completed run and a cancelled run were
indistinguishable without an experimental flag. U-48's capability is *raw terminal signals* precisely
because the taxonomy has to be built on top of a preserved raw signal. NOOA supplies the taxonomy and
discards the input to it, which is the wrong half.

**Session restore is a code-execution sink on its own database.** `SQLiteStorageManager`'s docstring
concedes it. Two mechanisms carry it: `storage/serialization.py:298` resolves a fully-qualified name
read from the database by walking `importlib.import_module` down progressively shorter module paths
and `getattr`-ing the remainder, and `storage/markers.py:72` reaches `eval(raw, ns)` for the dynamic
context expressions a snapshot stores as strings. Under our model the session store sits behind the
supervisor and holds agent-authored state, so *the database is trusted input* is not an assumption we
can make — an agent that can influence what lands in a snapshot influences what executes on the next
resume. Notably, NOOA's own memory subsystem takes the opposite approach for the equivalent problem:
Appendix C says memory references are resolved *"by strict name lookup (never eval)"*. The safer
pattern exists in the codebase; the session store does not use it.

---

## 5. Q3 — does it make v2's tool synthesis unnecessary?

**No. It removes the part D-06 already called commodity and leaves the three hard parts untouched.
Our position survives contact.**

The real gain is honest and should be stated plainly: if a capability is a typed method, there is no
JSON Schema to author, no name and description to word for an LLM audience, no argument-marshalling
layer, and no drift between the schema and the function. Type annotations are checked at runtime, so
a contract violation is an exception rather than a malformed call. For a codebase already written as
classes, this is a genuine reduction in mechanical work.

**It relocates the problem into the class boundary, and the relocation is visible in NOOA's own
agents.**

- **Which functions to promote.** Every method on `self` is model-visible. A class with two hundred
  methods is a two-hundred-tool surface, which is the failure [`01`](./01-agent-anatomy.md) records
  as tool-selection accuracy falling past roughly thirty to fifty tools, and which finding 013 priced
  at 541 to 557 tokens per tool per request. NOOA's answer is that a human writes a small class —
  the SWE-bench agent is 253 lines, the ARC-AGI-3 agent is one agent plus a short skill. **That is
  promotion selection, done by hand, and it is the whole of the answer.** A generator pointed at an
  arbitrary codebase has to decide what goes on the class, and NOOA offers no mechanism for that
  decision. Mechanical one-to-one conversion is *easier* here than with schemas, which makes the
  anti-pattern cheaper to fall into, not harder.
- **Effect classification.** A type annotation says what a method returns. It does not say whether
  calling it writes, whether the write is reversible, or whether it is irreversible and destructive.
  NOOA has no effect metadata on methods and no interception keyed on one. Its sandbox guards are
  *resource* guards — filesystem paths, sockets, memory, CPU — and per §1 they do not apply to
  brokered `self.*` calls at all. This is the same conclusion D-06 reached about MCP schemas, and it
  is the constitution Principle IV obligation D-22 records as not deferring with the differentiator.
- **Verifiable postconditions.** The paper's strongest engineering idea is that termination is a
  validated typed return — the model must produce a `TaskResult` carrying evidence and a verification
  command, and §4.2's trace analysis credits that for a real share of the Terminal-Bench gap over
  OpenCode, which *"stops whenever the model responds without a tool call."* This is a good idea and
  it converges with our contract-derived verification position. **But the `TaskResult` type is
  hand-written, and its verification command is supplied by the model.** Deriving a postcondition
  from the target application's own declared fields is the recomputation path D-21's fourth amendment
  identifies as what a schema-level check cannot reach. NOOA does not derive it; it declares a shape
  and asks the model to fill it.

**The clinching evidence is NOOA's own CyberGym agent.** §4.3 describes *"a deterministic layer around
the model"*: a submission method, a *"lightweight judge"* that checks the model's summary still
matches the described vulnerability, and re-submission a few times to reject non-deterministic
crashes. The blog calls these *"three deterministic gates."* Every one is a human deciding which
operation deserves promotion to a method, what effect it has, and what postcondition proves it
worked. **The object model made those gates cheap to express. It did not decide what they should be.**

---

## 6. Q4 — safety, licence, and dependency posture

### 6.1 What confines it

**In-process by default.** `execution_backend` is `"inprocess"`. Model-written Python then runs in
the agent's own process with `self` in scope and nothing between it and the host but
`runtime/code_validator.py`, an AST pass with a forbidden-builtin list, an import denylist, a dunder
check and an infinite-loop heuristic. That file and `sandbox/readonly.py` both say what they are:
*"not a security boundary — the OS layer … is."* The paper agrees; §7 Limitations says the validator
*"protects the agent loop, not the host."*

**Opt-in, and genuinely good when on.** `execution_backend="sandbox"` forks a worker that installs
four kernel guards before any cell bytecode runs — Landlock default-deny filesystem with an explicit
read set and an optional writable workspace, a seccomp block on `socket(AF_INET/AF_INET6)`,
`RLIMIT_AS`/`RLIMIT_CPU`, and a parent SIGKILL past `cell_timeout`. It is Linux-only by construction
(`check_enforceable` returns `["sandbox requires Linux"]` otherwise), which is convergent with OD-17.
**And `require` defaults to `True`, so it fails closed** — `SandboxUnavailable` is raised when a
requested guard cannot be enforced on the host, and the degraded path exists only when the caller
explicitly asks for it. That is better fail-closed discipline than most of the vendored corpus.

### 6.2 Why it is not our enforcement point

Three structural gaps, each verified in the source:

1. **The sandbox does not cover the tool surface.** `_dispatch_tool_call` executes `self.<path>`
   calls, and `setattr` on the parent's live agent, in the parent process. The declared capability
   surface — the thing the whole pitch is about — is outside every guard by design, because keeping
   it inside would mean serializing across the boundary and losing pass-by-reference.
2. **Egress is a switch, not a proxy.** `network: bool` maps to a seccomp block on internet sockets.
   There is no destination allowlist and no method policy, so an agent that must reach one endpoint
   requires `network=True`, which permits all of them. **OD-12's mandatory proxy enforcing destination
   and method together has no analogue here**, and cannot be built from this primitive.
3. **Credential authority is untouched.** `start_method` is `"fork"` only, because the worker must
   inherit the live agent. Nothing in `sandbox/worker.py` scrubs the environment, so provider keys in
   `os.environ` are readable from inside the guarded worker. The guards bound *resources*; they do
   not bound *authority*, which is what the lease model exists to do. Bounds are `RLIMIT_AS` rather
   than cgroup v2, Landlock rather than a mount namespace, and there is no PID namespace.

NVIDIA does not dispute any of this. The blog: *"For production deployment, NOOA pairs with the NVIDIA
OpenShell secure runtime."* The paper: *"Our preferred deployment is OpenShell."* Appendix D.2 records
that the ARC-AGI-3 fleet's hard layers were **external** to the agent — a `setpriv --no-new-privs` uid
drop and a bubblewrap namespace sandbox as *"the current default"* — and concedes *"a known cell-guard
gap (dynamic attribute lookup can evade the AST scan)"*, backstopped by the uid drop rather than by
the validator. **So the brief's hypothesis is confirmed by the vendor: NOOA is the layer above an
enforcement point, and NVIDIA ships a different product to be that point.**

The red-team result in D.2 is worth crediting: 18 rescans of a live 25-game fleet, zero network
invocations, zero game-source bytes returned, cross-game reads failing with `EACCES`, zero real game
identifiers across 13,335 logs, and one escape attempt caught before execution. That is a real
containment measurement and it is more than this project has run. It is also a measurement of
`setpriv` plus bubblewrap plus anonymisation, not of the in-repo sandbox alone, and the paper says so.

### 6.3 Licence and dependency posture

NOOA itself is Apache-2.0, verified from `LICENSE`. The problem is one line of `pyproject.toml`:

```
"litellm>=1.84.0",
```

A hard runtime dependency, not an extra, and `openinference-instrumentation-litellm` beside it.
**OD-16 removed `litellm` from v1 for its undeclared package licence**, recorded in finding 003
result 8: the PyPI `License` field is empty and there are no classifiers, and the repository `LICENSE`
is MIT *except* everything under `enterprise/`, which carries a separate proprietary licence.

NOOA's `THIRD_PARTY_NOTICES.md` declares *"litellm - MIT License."* **That is not a contradiction of
our finding and it does not resolve OD-16's objection.** It is a statement about the repository root,
and it is silent on both facts OD-16 turned on — the empty published metadata that an automated scan
reads, and the `enterprise/` carve-out. A downstream product cannot discharge a licence-scan obligation
by citing an upstream vendor's summary of a third party's licence.

Two further posture notes. The dependency pin carries its own security history in a comment —
`>=1.84.0` for a critical proxy-server RCE and to clear the yanked 1.82.7/1.82.8 backdoor releases —
which is the supply-chain surface OD-16 also declines. And NVIDIA labels NOOA a **research preview**
and *"an open experimental surface, not a replacement for existing harnesses."* That is the same
maturity tier [`13`](./13-claude-managed-agents.md) §1.3 found decisive for CMA, and the same
reasoning applies.

---

## 7. Reading their evaluation

Applied the way this project reads its own. Three defects, ordered by how much they cost the paper.

**A prose claim contradicted by the paper's own tables.** §4.2: *"Increasing reasoning effort improves
all three harnesses, but the interface matters most when the model provides less planning and
verification discipline of its own."* Against Tables 3 and 4, ~~at least four cells~~ **four
transitions — verified cell by cell 2026-08-04 against
[the paper](https://arxiv.org/abs/2607.20709), and *at least* is now exact: four of eighteen** —
fall the other way.
OpenCode on Terminal-Bench with GPT-5.5 goes 60.7 at high effort to 52.8 at xhigh. PI on
Terminal-Bench with Opus goes 65.2 with reasoning off to 58.4 at high. OpenCode on Terminal-Bench with
Opus goes 49.4 to 43.8. OpenCode on SWE-bench with Opus goes 76.0 to 75.2. **All four cells named
above are correct as printed.** The denominator is worth stating because it is what makes the
sentence a defect rather than a quibble: the two tables carry three harnesses × two backends, with
three reasoning settings on GPT-5.5 and two on Opus 4.6, so there are **eighteen adjacent-setting
transitions in total — thirteen rise, four fall, and one is flat** (NOOA on Terminal-Bench with
GPT-5.5, 73.0 at high and 73.0 at xhigh). **The defect holds, and it holds in a shape that is worse
for the baselines than for NOOA rather than the reverse: every one of the five non-rising
transitions belongs to a comparator except the flat one, and NOOA never falls.** So the sentence is
false about *"all three harnesses"* in exactly the place a reader would check it — the two arms the
paper is arguing against. **The claim holds for the
SWE-bench GPT-5.5 column and is stated as if it held generally.** This matters beyond the sentence:
Terminal-Bench 2.0 is 89 tasks, so one task is about 1.1 points, and a baseline that moves nearly
eight points in the wrong direction between adjacent settings is announcing a noise floor. The
margins the paper reads off those same points — including PI *beating* NOOA at xhigh, 75.3 to 73.0 —
are narrower than the movement. No confidence intervals and no repeat counts are reported for any
benchmark arm.

**A comparison drawn across a factor the authors name as material.** Table 5's `Network` column reads
`unknown`, `blocked`, `blocked`, `unknown`, `open`, `unknown`, `blocked`. The text beside it says
*"Monitoring network access affects performance."* The headline — NOOA *"beating the majority of
closed-source solutions"* — is drawn across three rows whose network condition is unknown. Credit
where due: **the column is in the table**, which is more disclosure than most papers offer, and the
cheat-check over trajectories is real work. But the only like-for-like pair is NOOA at 86.8 against
bare Codex at 64.9, both blocked, both GPT-5.5 — and those two differ by three interventions, not
one, since the NOOA agent carries a submission method, a summary-match judge and a re-submission
check. The arm that would isolate the interface, Codex plus the submission skill, ran with network
**open** at 83.5, so it cannot separate anything. **The clean contrast the paper needs is absent and
the one it has is confounded.**

**A headline effect the paper itself marks indicative.** The ARC-AGI-3 harness-effect figure compares
85.1% inside NOOA against ARC Prize's own 13.3% for the raw model, with the footnote *"evaluation
budgets differ, so the comparison is indicative."* A two-hour guarded fleet against a third party's
evaluation at an unstated budget is a spend comparison wearing a harness comparison's clothes. **The
internal ablation is the number to trust and it is good work**: same skill, same model, same cap,
memory subsystem swapped for markdown files, 50.2% against 38.4%. One factor, one arm difference.
That is the best-designed experiment in the paper and it is about memory, not about the interface.

**Minor, but they are the kind of thing that erodes a reader's trust in the figures they cannot
check.** The blog and the paper disagree on three artifacts describing the same runs: 29 LLM calls
against *"approximately 28"*, a 45-line skill against a 50-line skill, and per-game cost quoted to
one decimal in one place and two in the other. Individually trivial; collectively a sign that the
numbers were not reconciled across publications.

**What the paper does well, said plainly because the criticism above should not be read as a verdict
on the work.** The capability-suite consistency analysis is honest and reports the deflating framing
alongside the flattering one. The termination analysis is a real mechanism claim with trace evidence
behind it. The §7 Limitations paragraph on in-process execution is more candid than most vendor
documentation. The containment appendix reports a latent finding nobody exploited and a known guard
gap. And the entire suite, the benchmark agents and the evaluation code are released.

---

## 8. The three-way split, and what adoption would cost

| | Claim | Code | Verified here |
|---|---|---|---|
| Code as action reduces the need for tool schemas | Asserted, six-idea framing | True at the interface: methods called from cells, no JSON Schema authored | **Confirmed as a mechanism**; not tested against curated tools anywhere |
| Models are fluent in the interface | 97.9% of 4,400 records | Suite is in-repo, authored with the interface | **Instrument uncalibrated by our own standard**; no negative control |
| ~~Roughly half the tokens at parity or better~~ **Half against PI, ~15% against OpenCode** | 82.2% at ~1.1M vs PI 78.2% at 2.2M **and OpenCode 78.6% at ~1.3M** | Pass-by-reference is real; bounded previews in `context_blocks` | **Not verified** — single run, no CI, baselines run by the treatment's authors. **Corrected 2026-08-04: the plural was wrong.** PI's 2.2M carries 66 calls against NOOA's 28, so serialization is not the only live factor; OpenCode matches NOOA's call count and is the pair that isolates it |
| Increasing effort improves all three harnesses | Stated in §4.2 | — | **False in at least four cells of its own Tables 3 and 4** |
| Reaches four providers | Implied by `unifiedllm` breadth | Real per-provider repair work | **Opaque reasoning state: zero occurrences of four field names, tree-wide.** Assistant message carries `role`/`content`/`tool_calls` |
| Sandboxing goes *around* the agent | Stated in §7; blog names OpenShell | `execution_backend` defaults to `"inprocess"`; guards are opt-in | **Confirmed, and stronger than stated** — brokered `self.*` escapes the sandbox by design |
| litellm is MIT | `THIRD_PARTY_NOTICES.md` | Hard dependency `litellm>=1.84.0` | **Silent on both facts OD-16 turned on** — empty PyPI metadata, `enterprise/` carve-out |
| Session state persists | Memory and storage sections | `sqlite.py` + `snapshot.py` | **Confirmed, and restore is an RCE sink on its own DB, per its own docstring** |

### What we would stop building if we adopted it

Honestly: **almost nothing, and nothing on the critical path.** The most favourable reading gives us
the agent loop (8–11 days) and the session-store mechanism (5–7), and the second comes with §4's
restore property, so it would need replacing rather than adopting. Two to three days of cost table
would arrive attached to the dependency OD-16 removed. Rows 4, 5, 7, 8 and 9 — checkpoint granularity,
provider round-trip, spend ceiling, raw terminals, serving surface — stay ours, and they are 41 to 57
of the 59 to 82 days. **No document may quote a reduced U-48 figure on the strength of this
assessment.**

### What we would take on

- A hard dependency on `litellm`, reversing **OD-16**, and with it the empty-metadata licence problem
  and the pinned-past-a-critical-RCE supply-chain surface.
- A provider layer that fails **FR-037** on the axis **SC-010** is measured against, in a component we
  would not control.
- A session store whose restore path executes stored names, sitting behind our supervisor.
- A terminal taxonomy whose catch-all silently reports unknown stops as completions.
- A **research preview** as substrate, which is the maturity finding that disqualified CMA.
- An in-process execution model whose efficiency property is inseparable from an authority leak we
  would then have to re-plug at a boundary NVIDIA solves with a separate product.

### What we would gain that is real

One idea, and it is free: **termination as a validated typed return rather than a prompt convention.**
NOOA's `TaskResult` — evidence plus a verification command, enforced by the return validator — is the
mechanism its own trace analysis credits for the largest single behavioural difference against
OpenCode, and it is directly compatible with contract-derived verification and with FR-005's terminal
requirements. It costs nothing to adopt as a pattern because it is a pattern, not a dependency.

---

## 9. Proposed register entries

> **LANDED 2026-08-04, and one of the three landed under a corrected framing.** All three entries
> below are now definitions in [`14-architecture-synthesis.md`](./14-architecture-synthesis.md):
> **U-50** and **C-20** as new rows, and the U-48 annotation in place. The verified high-water marks
> at landing were U-49, C-19, OD-23 and D-22, so the numbers proposed here were the numbers assigned.
> Two further entries landed in the same pass from unrelated work — a second-instance annotation on
> **U-49** and a new **U-51** — which is why the U register advanced by two rather than by one.
>
> **The correction is to U-50 and it is not cosmetic.** This section framed the open question as *how
> much of the pass-by-reference saving survives a sandbox boundary*. **That framing has no referent
> for this product.** [`spec.md`](../specs/002-spec-aware-agent-runtime/spec.md) **FR-004** gives v1
> command execution plus a general request capability, and both return bytes across a boundary — so
> there is no in-process object graph here, and the mechanism is **absent by construction rather than
> degraded by our sandbox**. The landed entry is one level up and has two limbs: the token cost of
> bulk tool output entering the transcript is **unmeasured on our surface and governed by no
> requirement** — confirmed by search on 2026-08-04, no truncation rule, bounded preview, byte ceiling
> or handle appears anywhere in that role, so the operative default is to inline everything — and both
> measurement arms are now authorised and pre-registered separately, with **neither run**. §10 below
> is corrected to match.

Identifiers are in code spans below because **they were proposals when this section was written**. Landing
them means adding rows to §5 and §4 of [`14-architecture-synthesis.md`](./14-architecture-synthesis.md)
and then re-running `gen_claims.py`, which advances the register-extent claims at
`specs/001-discovery-validation/VERDICT.md` and `specs/001-discovery-validation/plan.md` — outside
this pass's write scope, and the VERDICT site is the narrated one the generator deliberately refuses
to write because its digits are half a claim and its dated refresh log is the other half. So these
are proposed, with the high-water marks checked rather than assumed: `U-49`, `C-19` and `OD-23` are
current, so the next free numbers are the ones used here.

**`U-50` — ~~pass-by-reference's token saving has never been measured across a sandbox boundary, and
our architecture requires one~~ — landed 2026-08-04 as: *the token cost of bulk tool output entering
the transcript is unmeasured on v1's action surface, and no requirement governs it*.** NOOA reports ~~roughly half the tokens of two comparison harnesses~~ **corrected 2026-08-04: half the tokens of PI
and about fifteen percent fewer than OpenCode** and
attributes it to tool results staying live rather than serializing into the transcript, then states
that in-process execution is what buys this and that *"sandboxed code modes trade it away, receiving
serialized copies at the sandbox boundary."* Its own workaround is to broker `self.*` calls to the
unsandboxed parent, which we cannot do. **Why it matters:** OD-09 repositioned the product on cost,
so a token mechanism worth a factor near two is directly on the thesis. ~~and we do not know whether
zero, some, or most of it survives a boundary that serializes.~~ **Corrected 2026-08-04 — that
sentence asks about a mechanism v1 does not have.** Under **FR-004** the action surface is command
execution and a general request capability, both returning bytes, so nothing here is *degraded* by a
boundary; there is no live-object baseline to degrade. **What is genuinely open, and what landed:**
bulk tool output enters the transcript at a cost nobody has measured on this surface, under **no
requirement at all** — the specification names no truncation rule, no bounded preview, no byte
ceiling and no handle, so the operative default is to inline everything, which is the expensive case
and was never chosen. **One thing the landed entry adds that this section missed:** ~~E7's cost
advantage was itself measured on a surface that inlines, so the inlining default is *inside* the
figure this product quotes rather than a regression against it — the open quantity is **headroom,
not exposure**.~~ **Premise corrected 2026-08-04 by
[finding 022](../specs/002-spec-aware-agent-runtime/findings/022-e7-tool-result-truncation-cap.md);
the conclusion is unchanged and is arguably stronger.** E7's cost advantage was **not** measured on a
surface that inlines. It was measured on one that **truncates**:
`ceiling-test/config.json` sets `tool_result_truncation_chars` to 6,000, `runner.py` hands that one
value to the single call site both arms share, and `agent.py` truncates the result *before* it
measures it — so E7 arm B (shell) inlined at most about **1,500 tokens** per result, at the 4.0
bytes/token divisor E17 itself uses. **A capped baseline is still a baseline, so the open quantity is
still headroom and not exposure** — nothing here puts the cost claim at risk. **What the premise was
doing, though, was *sizing* that headroom, and the correct sizing is much smaller.** Against
unbounded inlining the unclaimed prize is whatever bulk output costs; against a 1,500-token ceiling
it is only the gap between that ceiling and a bounded preview, which in E17's own treatment
parameters is 1,500 tokens down to 400. **Read the two together: the direction is unchanged, the
magnitude is a fraction of what the earlier premise invited, and a reader must not carry the old
sentence forward as the thing that sizes it.** **Narrowed 2026-08-04, in size and not in direction, on two grounds the paper and
our own traces supply between them.** ① **The paper undercuts its own novelty on the mechanism.** §3:
*"Models already improvise this pattern in bash – spilling results to files and processing them with
follow-up commands; NOOA replaces the untyped text on disk with typed, live variables that persist
from cell to cell."* Its pass-by-reference rendering is *"each argument's variable name paired with a
bounded preview: the concrete type, the true length, and a short head/tail sample"* — handle plus
preview, which is what a shell agent improvises. §6 says so again from the other side: file handles
are *"a variant of pass by reference"*, *"powerful"*, and what they lose is *"all type information"*.
**So NOOA's increment over a command-execution surface is type preservation, not the token saving**;
the saving is available to a bytes-returning surface and the type information is not. ② **E7's shell
baseline was already capturing part of it, and this is now checked rather than open.** Counted over
the fourteen committed `traces.jsonl` files under
`specs/001-discovery-validation/harness/ceiling-test/results/`, which record every `bash` call's
full command string: ~~**36 of 109 arm-B task-attempts spill output to a named file, 31 later read one
back, and 70 of 998 arm-B commands write one.**~~ **Re-derived 2026-08-04
([finding 022](../specs/002-spec-aware-agent-runtime/findings/022-e7-tool-result-truncation-cap.md)).
Every struck figure reproduces to the digit; what was wrong is the population each counts.** **32 of
109 E7 arm-B (shell) attempts spill command output to a named file, 31 later read one back, and 45 of
998 E7 arm-B commands write one** — the published counts folded in 4 attempts and 25 commands that
wrote only a heredoc script (`cat > /work/x.py << 'EOF'`), which is the model typing a file rather
than capturing what a command printed. So an unquantified share of the headroom is inside
E7's measured advantage already. **This is a count of the behaviour occurring and not a measurement
of what it saved** — ~~21 of the 70~~ **21 of 45** immediately `cat` the whole file back, which defeats it — and the
distinction is the whole of what E17 arm A (handle-vs-inline), this section's arm ②, would settle.
**The restatement of that last figure is [`14`](./14-architecture-synthesis.md) `U-49`'s defect for
the third time**: the numerator was computed over output-spills while the denominator was padded with
25 heredocs that could not have entered it, and the honest rate is the less flattering one — nearly
half the spills hand the whole file back, not three in ten. **And the pooled 109 must not be read as
a rate at all.** It crosses **seven** harness fingerprints, which `runner.py`'s own docstring forbids
pooling across; it includes 13 smoke attempts backing no published figure and 25 noise-floor attempts
that are 5 tasks weighted 5×; and across the six runs that *do* back a published figure the spill
rate spans **19% to 100%**. No pooled spill rate characterises any quoted cost multiplier, and the
run behind the cleanest one — the paired **4.366×** — has the lowest rate of the six.
**The direction of this entry is unchanged and
is not reopened: headroom above a measured baseline, never exposure to it.** What moved is the
expected size, downward, and possibly by a lot. **How to resolve:** §10, as corrected there — two arms, both now authorised, neither
run. **Blocking:** no — v1 ships without it either way. Related: OD-09, D-19, U-46, finding 013;
`spec.md` FR-004 and FR-005.

**`C-20` — NVIDIA ships `litellm` as a hard dependency of an Apache-2.0 product and declares it MIT,
against OD-16's finding that its published licence is undeclared.** Not a contradiction of fact —
NOOA's notice describes the repository root and finding 003 describes the package metadata and the
`enterprise/` carve-out, and both are true. It is a contradiction of *disposition*: a major vendor
treats as shippable a dependency we removed for a licence-scan exposure. **Why it matters:** OD-16 is
the only decision in the corpus taken on a licence ground, and this is the first external datapoint
against it. **Resolution:** re-read finding 003 result 8 against current `litellm` metadata before
any future reconsideration; the finding is dated and package metadata changes. **Weight:** low. OD-16
turned on what an automated scan of an emitted customer pack would find, which another vendor's
attribution file does not change. Recorded so the decision is not re-litigated from memory.

**Annotation on `U-48`, not a new entry.** The register should record that an external substrate was
assessed against all nine on 2026-08-04 and reduces none of them, with the two sharpest sub-findings
named so they are not rediscovered: the largest row (provider transport and tool-schema translation,
15–20 days) is **measured non-compliant with FR-037 on the same axis and by the same counting rule
that condemned ADK's adapter**, and the smallest row that a framework could plausibly own (the
per-provider cost table, 2–3 days) is **only ownable by re-adopting the dependency OD-16 removed**.
Together these say something more general than *NOOA is not adoptable*: **the two U-48 rows most
likely to be discharged by adopting somebody else's framework are the two where every candidate
framework will hit the same two obstacles**, because the opaque-reasoning round-trip is unrewarded
work for a middleware author and the cost table is exactly the thing middleware exists to supply.

**Considered and not proposed.** A contradiction against E7 — there is none, and §2 argues the two
experiments do not overlap. A new uncertainty about the capability-suite calibration — that is a
statement about their instrument, not ours, and U-42 already carries the calibration problem on our
side.

---

## 10. What can only be settled by running their code

> **AUTHORISED AND RESHAPED 2026-08-04. Read this before the section below it.** The owner authorised
> measurement, and what was authorised is **two arms rather than the one this section proposes**,
> because the arm below answers a question about *their* architecture and not about ours. ① The
> `inprocess`-versus-`sandbox` comparison described here, reframed as an **external upper bound**: it
> prices what serialization costs a harness built to avoid it, which is the most the mechanism could
> be worth to anyone, and it does not transfer, because our baseline never holds a live object
> (**FR-004**). ② An **achievable figure from our own harness** — inlined command output against a
> handle plus a bounded preview, on a command surface — which is the only arm whose result could be
> written into a requirement. **Both are being pre-registered by separate work under
> `specs/001-discovery-validation/harness/pass-by-reference/`. Neither has run, and no figure from
> either exists to quote.** The specification half of `U-50` — deciding what governs command-output
> size, or recording inlining as the chosen default — waits on neither arm and is the cheaper half.

> **⚠️ ARM NAMES COLLIDE ACROSS THREE DOCUMENTS, AND ONE OF THE COLLISIONS INVERTS. Added 2026-08-04
> with [finding 022](../specs/002-spec-aware-agent-runtime/findings/022-e7-tool-result-truncation-cap.md),
> which carries the same table.** Read it before moving any figure between these documents.
>
> | Write it as | It is | Called elsewhere |
> |---|---|---|
> | **E7 arm A (curated tools)** | the hand-written per-application tool surface | `arm: "A"` in E7's traces |
> | **E7 arm B (shell)** | the shell-and-spec baseline whose cost D-19 quotes | `arm: "B"` in E7's traces |
> | **E17 arm A (handle-vs-inline)** | inlined command output against a handle plus a bounded preview | `ARM A` in E17's pre-registration; **arm ②** in this document |
> | **E17 arm B (NOOA)** | NOOA at `execution_backend="inprocess"` against `"sandbox"` | `ARM B` in E17's pre-registration; **arm ①** in this document |
>
> So E17's `ARM A` is this document's arm ②, and **"arm B" means opposite things**: in E7 it is the
> shell baseline the whole cost claim rests on, in E17 it is the arm E17 declined at $0.00 as unable
> to measure what it was commissioned to measure. A figure moved across without translation lands on
> the wrong arm. **This document and [`14`](./14-architecture-synthesis.md) now write the
> experiment-qualified form and gloss every surviving ①/② against it.** The circled markers are kept
> rather than replaced because this document also uses ① and ② for *enumerated grounds* two sections
> up, so retiring them here would not remove the ambiguity and would break every inbound citation.
> **What is out of scope to change here and needs changing at its source** is named at the end of
> §10.

**One item, and it is the only one that would change a decision.** Everything else in this document
was settled by reading.

**Measure how much of the pass-by-reference token saving survives serialization at a process
boundary.** NOOA supplies the comparison for free and it needs no third-party benchmark: the same
task, the same agent class, the same model, run twice, with `execution_backend="inprocess"` and then
`execution_backend="sandbox"`. Under `"sandbox"` every `self.*` result must cross the fork boundary
via pickle, and non-picklable returns are refused outright with `CellSerializationError` — which is
itself the finding, because it tells us which shapes of tool result cannot cross a boundary at all.
One factor differs between arms.

**Why it cannot be read off the source.** The saving depends on what fraction of results are large,
how often a live object is re-used across turns rather than consumed once, and how much the bounded
preview shrinks a value that would otherwise be serialized in full. All three are properties of the
workload, not of the code.

**Why it is worth authorising and what it would cost.** It is the only place in this assessment where
NOOA bears on a decision we have not taken. If most of the saving survives serialization, the
mechanism transfers to a sandboxed v1 and belongs in the runtime design. If little survives, the
result closes `U-50` cheaply and stops a costly design from being attempted on the strength of a
number measured under conditions we cannot reproduce. It requires installing NOOA and its dependency
tree in a throwaway Linux environment, a Landlock-capable kernel, and a small number of paid model
calls on one short task at two settings — a handful of calls, not a benchmark sweep. ~~**Not started,
and not to be started without authorisation.**~~ **Authorised 2026-08-04 as arm ① — E17 arm B (NOOA)
— of two; still not started.** The `litellm` install is itself a dependency this
project has decided not to ship, so even the throwaway environment is a decision rather than a
detail.

**Settled by reading after all, and it belonged in the design of arm ② — E17 arm A (handle-vs-inline)
— rather than in a run — added
2026-08-04.** That arm prices a handle plus a bounded preview against inlined command output, and it
needs to know what its *baseline* already does, because a baseline that spontaneously spills to disk
is already part-way to the treatment. E7's committed traces answer this without a model call:
`tool_calls[].args.command` carries every `bash` invocation verbatim, so redirection, `tee`, heredocs
and read-backs are all greppable. Counted over the fourteen `traces.jsonl` files under
`ceiling-test/results/`: ~~**36 of 109 arm-B task-attempts spill output to a named file**~~
**re-derived 2026-08-04 —
[finding 022](../specs/002-spec-aware-agent-runtime/findings/022-e7-tool-result-truncation-cap.md)
reproduces every struck figure to the digit and corrects the population each counts: 32 of 109 E7
arm-B (shell) attempts spill command output to a named file** — the
`/work/all_recipes.json` shape, `curl … > file` and then `cat file | jq …` — **31 read one back, and
~~70 of 998 arm-B commands write one~~ 45 of 998 E7 arm-B commands write one**, the excluded 4
attempts and 25 commands being heredoc script writes rather than output captures. **Two things follow and they must not be merged.** The pattern
is present, so `U-50`'s headroom is smaller than NOOA's headline invites; and **nobody has measured
what it saved**, since ~~21 of the 70~~ **21 of 45** immediately `cat` the file back whole. That arm should therefore
report its baseline's spill rate alongside its result, or it will price a treatment against a
baseline that is partly the treatment — which is Rule 3's *tool result handling* row arriving in a
new place.

**And it must report that rate per fingerprint rather than pooled, which the struck figures did not
— added 2026-08-04.** The 109 attempts cross **seven** harness fingerprints, a pooling `runner.py`'s
own docstring forbids; 13 of them are smoke attempts behind no published figure and 25 are noise-floor
attempts that are 5 tasks weighted 5×. Across the six runs that back a published figure the spill rate
spans **19% to 100%**, so **no pooled rate describes any quoted cost multiplier** — and the run behind
the corpus's cleanest one, the paired **4.366×**, sits at the bottom of that range rather than in the
middle of it.

**The much larger correction that arrived with the same re-derivation, and it changes what this arm is
measuring against — added 2026-08-04.** **E7's baseline never inlined bulk output.** Both arms ran
under `tool_result_truncation_chars` of 6,000, applied at one call site with the truncation happening
*before* the measurement, so E7 arm B (shell) inlined at most about **1,500 tokens** per result.
E17's primary inline cap is 8,000 tokens — **5.3× that** — and returns a projected median ratio of
**0.429**; the lowest rung of its own pre-registered sensitivity table, 2,000 tokens, is already above
E7's empirical cap and returns **0.958**, which its §8.4 rule maps to *recommend against*. **E17 is
therefore not pricing a mechanism against the only inline setting this repository has ever run**, and
whatever it reports at 8,000 tokens should be read beside what it reports at 2,000.

**What this document cannot fix and where it has to be fixed — added 2026-08-04.** The arm letters
inside `specs/001-discovery-validation/harness/pass-by-reference/` and inside E7's harness are out of
scope for this correction and were not touched. Three sites carry the collision at its source and
each needs a one-line gloss rather than a rename: E17's `PREREGISTRATION.md` §2 and §11 headings and
its `config.json` `arm_a_*`/`arm_b_*` budget keys, which name the handle-vs-inline arm `A` and the
NOOA arm `B`; E17's `README.md`, which repeats them; and E7's `config.json` `budgets.arm_a`/`arm_b`
and `runner.py --arms A B`, which mean the opposite. **Renaming any of them would invalidate a
committed harness fingerprint and rewrite the arm field in every committed trace**, which is why the
proposal here is a gloss at each site and the qualified form in prose, not a rename.

**Explicitly not proposed:** reproducing SWE-bench Verified, Terminal-Bench 2.0, CyberGym L1 or
ARC-AGI-3, or re-running the capability suite. Those would cost far more than the questions are worth
to us, and §7's defects are visible without them — a contradiction against a paper's own table needs
no compute to find.

---

## 11. Sources

**Primary — the vendored repository**, read-only at `examples/labs-OO-Agents/`, Apache-2.0. Every
module path, default value and docstring quoted above was read from that tree on 2026-08-04. The
load-bearing ones: `pyproject.toml`, `THIRD_PARTY_NOTICES.md`, `src/nooa/config/strategy_config.py`,
`src/nooa/runtime/sandbox/{config,executor,readonly}.py`, `src/nooa/runtime/code_validator.py`,
`src/nooa/unifiedllm/unifiedllm.py`, `src/nooa/storage/{sqlite,snapshot,serialization,markers}.py`,
`src/nooa/tracing/_litellm_patch.py`, `src/nooa/runtime/token_usage.py`, `src/nooa/events.py`,
`src/nooa/viewer/main.py`.

**Paper.** [*NVIDIA OO Agents: Native Python Object-Oriented Agents*](https://arxiv.org/abs/2607.20709).
§3 programming model and pass by reference; §4.1 capability tests and Tables 1–2; §4.2 and Tables 3–4;
§4.3 and Table 5; §4.4; §5 harness
comparison; §6 related work; §7 Conclusion and Limitations; Appendices C.1 and D.2. Every figure attributed to the
paper in this document is quoted from it and is **not** a measurement this project took.

**Which paper figures have been read off the paper, and which have not — recorded 2026-08-04, because
until that date the paper was not vendored and nothing here was checkable from the tree.** The
paper was fetched and read directly on 2026-08-04. **Checked against it cell by cell:** the SWE-bench
and Terminal-Bench token and call counts in §4.2 (28 calls / 1.1M for NOOA, 66 / 2.2M for PI, similar
calls / 1.3M for OpenCode); every cell of Tables 3 and 4 named in §7; the *"increasing reasoning
effort improves all three harnesses"* sentence; the two §3 pass-by-reference passages quoted in §9;
the §6 file-handle passage; and the §7 Limitations sentence on in-process execution.

**Corroborated in-tree by a second artifact, and this document had it available all along:** NOOA's
own CyberGym row. `examples/labs-OO-Agents/examples/cybergym/Technical_Report.md` is vendored with
the code and independently states **1,308 of 1,507 tasks solved, 86.8% pass@1**, matching Table 5,
and its §3.5 describes the `blocked` condition concretely — an internal-only Docker network with a
`mitmproxy` sidecar as sole egress, allowlisting package repositories and LLM endpoints and stripping
hosted web-search, web-fetch, remote-execution and MCP tools. **This is a second source for one row
and its own `Network` cell, and for nothing else in the table:** the comparator rows, their `Network`
values, and the Codex arms at 64.9 and 83.5 that §7 turns on are not in the vendored report, so §7's
confounding argument still rests on the paper alone.

**Still resting on the paper alone, with no independent check available:** the capability-suite
denominators (4,400 records, 88 tests, five runs, ten models, 97.9%, 440 of 440, the 94%-of-880
restatement), **every CyberGym Table 5 row except NOOA's** and every `Network` cell except NOOA's,
the ARC-AGI-3 figures (85.1%, 13.3%, 50.2% against
38.4%, the per-game costs) and Appendix D.2's red-team counts. Those are outputs of runs this project
cannot reproduce and no vendored artifact carries them; they are quoted as the paper's claims and
nothing here corroborates them.

**Blog.** [*Six Agent Harness Capabilities for Higher Model Performance*](https://developer.nvidia.com/blog/six-agent-harness-capabilities-for-higher-model-performance/),
2026-07-27 — source for the *research preview* framing and the OpenShell deployment statement.

**This corpus.** [`VERDICT.md`](../specs/001-discovery-validation/VERDICT.md);
[`14-architecture-synthesis.md`](./14-architecture-synthesis.md) D-05, D-06, D-19, D-21, D-22, C-15,
C-18, C-19, U-30, U-31, U-42, U-46, U-48;
[`plan.md`](../specs/001-discovery-validation/plan.md) OD-04, OD-05, OD-07, OD-09, OD-10, OD-12,
OD-15, OD-16, OD-17;
[finding 003](../specs/001-discovery-validation/findings/003-runtime-provider-agnosticism.md) results
7 and 8; [finding 006](../specs/001-discovery-validation/findings/006-graph-loop-primitives.md);
[finding 012](../specs/001-discovery-validation/findings/012-ceiling-test-per-family.md);
[finding 013](../specs/001-discovery-validation/findings/013-ceiling-test-budget-parity.md);
[finding 016](../specs/001-discovery-validation/findings/016-provider-sdk-roundtrip.md);
[`spec.md`](../specs/002-spec-aware-agent-runtime/spec.md) FR-005, FR-037, SC-010, SC-030;
[`tasks.md`](../specs/002-spec-aware-agent-runtime/tasks.md) for the re-derived U-48 estimate quoted
in §3.
