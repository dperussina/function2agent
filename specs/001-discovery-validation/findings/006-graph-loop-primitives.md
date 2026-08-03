# Finding 006 — Does ADK supply the loop-safety machinery, or do we build it?

**Date**: 2026-08-02
**User Story**: 3 (choose the substrate that makes this work most efficiently)
**Model spend**: ≈ $0.0003 against a $5.00 ceiling. Nine LLM calls total, all on
`gemini-2.5-flash-lite` with single-word prompts, and every one of them spent on the single
question that cannot be answered without a model — whether `max_llm_calls` actually halts a
run. The other twelve arms used pure Python function nodes and cost nothing. The trap that
proves ADK has no step ceiling burned 1,292 graph iterations for $0.
**Method**: The existing isolated virtualenv at `/tmp/f2a-probe-runtime` (Python 3.12.11,
`google-adk` 2.6.1, `litellm` 1.91.4), reused rather than rebuilt. Every verdict below is
decided programmatically — by a node-execution ledger appended to inside the node bodies, by
`fsync`ed side-effect logs that survive `SIGKILL`, by exception types, and by comparing
session state dictionaries. No verdict is decided by reading model output. Crashes are real
`SIGKILL` to the probe's own PID in a separate OS process, chosen so that no `finally` block,
no `atexit` hook, and no graceful shutdown path can run. Resume arms therefore span two
processes against one persistent SQLite session. The vendored repositories under `examples/`
were read but not modified, and `git status --porcelain examples/` reports clean (FR-018).

## Why this probe

Finding 003 adopted Google ADK as the outer runtime on verified evidence that it drives all
four providers including chained tool-calling. That settled *whether ADK can talk to models*.
It said nothing about whether ADK can safely run the thing we actually intend to put inside
it: graph-structured agent systems whose nodes run loops.

The constitution and [`research/03-graph-and-loop-architecture.md`](../../../research/03-graph-and-loop-architecture.md)
§3 assume four pieces of machinery — checkpoint and resume, typed terminal conditions, hard
budgets, and deterministic replay. FR-002 specifically requires the terminal condition to be
recorded *by name*. If the runtime does not supply these, we build them, and that is a
schedule item that has to be sized now rather than discovered halfway through implementation.

## The graph under test

Four nodes, one cycle, one deliberate non-termination trap. `check` unconditionally routes
`again`, so nothing in the graph itself ever terminates:

```
START -> seed -> work -> check
                  ^        |
                  +--again-+          <- the trap
                           +--done--> finish   (unreachable while trapped)
```

## Results

| # | Primitive | Verdict | Evidence | If absent, what building it costs |
|---|---|---|---|---|
| 1 | **Checkpoint and resume** | **Present, at-least-once** | `SIGKILL` at iteration 3 of 6; a fresh process reopened the SQLite session, fast-forwarded the completed nodes, and finished at `iterations: 6` with state intact. Reproducible 5/5. But a crash *inside* a node re-executed that node's durable side effect in both configurations, and a loop hosted inside a node lost **4 of 4** completed inner turns. | Idempotency and inner-loop journaling: **1–1.5 weeks**. Not an ADK deficiency — see §The largest build item is not ADK's fault. |
| 2 | **Named terminal conditions** | **Absent as a taxonomy** | Errors are named (`error_code='RuntimeError'`, `error_message='deliberate node failure'`). Budget exhaustion is named by exception type. Clean completion versus cancellation is separable only by the boolean `actions.end_of_agent`, and only when an experimental flag is on. There is no field carrying a terminal *name*, and no notion of goal-satisfied, max-steps, wall-clock, or no-progress. | Terminal-condition wrapper over `run_async`: **2–3 days**. |
| 3 | **Budget enforcement** | **One dimension of four, and it resets on resume** | LLM-call count is genuinely enforced: the trap halted at exactly 3 cycles with `LlmCallsLimitExceededError`. Graph steps are not: the same trap ran **1,292 iterations in 20 seconds** and was still going. Token and cost ceilings do not exist anywhere in the codebase. Resuming a budget-exhausted invocation reset the counter — **6 cycles under a ceiling of 3**. | Budget channel plus enforcement plugin, persisted in session state: **4–5 days**. |
| 4 | **Deterministic replay** | **Present for sequential mechanics, absent under fan-out** | Four replays from byte-identical checkpoints (`sha256=11fa3ec8…`, 49,152 bytes) produced **1 distinct trace out of 4** and identical final state. But fan-out ordering is completion-time driven: with well-separated branch latencies, 1 distinct ordering in 5 runs; with overlapping latencies, **5 distinct orderings in 8 runs**. | Only needed if replayable *parallel* trajectories are required: **1–2 days**, or nothing if we accept order-insensitive joins. |

### Missing count against the pre-registered threshold

**Two of four missing. The threshold was three.** ADK clears it.

The counting rule: a primitive is missing when the runtime does not supply it and we must
build it. Named terminal conditions are missing. Budget enforcement is missing in the sense
the constitution needs — a ceiling on steps and cost that survives the run — even though the
LLM-call dimension is real. Checkpoint/resume and deterministic replay are supplied and were
observed working.

**The one judgment call that would flip this.** If the owner counts checkpoint/resume as
missing on the grounds that it is at-least-once, gated behind an `@experimental` flag that
defaults to off, and provides no granularity inside a node, the count becomes three and the
architecture conclusion inverts. That is a defensible reading and it is the single most
consequential line in this document. It is called out rather than buried because the gate was
pre-registered and this probe is what decides it. The recommendation below argues for two, but
the evidence for either reading is in §Primitive 1.

## Primitive 1 — checkpoint and resume, in detail

Resume works, and it works better than expected. A process killed with `SIGKILL` at iteration
3 of 6 was replaced by a fresh process that reopened the same SQLite session, replayed the
persisted event log, skipped the already-completed nodes, and ran through to `finish` with
`{'iterations': 6, 'topic': 'go'}`. No restart from the beginning, no state loss, no error.
Five trials, five identical outcomes.

The mechanism is worth naming precisely because it is not what the class name suggests.
`Workflow._run_impl` carries the comment `# TODO: resume from checkpoint event.` and then does
something else: `replay_mgr.scan_workflow_events(ctx)` reconstructs progress by scanning the
session's event history. Recovery is event-sourced replay, not checkpoint-blob loading.

Two configurations behave differently and both are reproducible 5/5:

| Configuration | Persisted events | Resumed at | Total `work` executions |
|---|---|---|---|
| `ResumabilityConfig(is_resumable=True)` | 17 | `work:3` (re-ran the in-flight node) | 7 |
| default, `is_resumable=False` | 7 | `check:3` (fast-forwarded past it) | 6 |

The resumable configuration emits checkpoint events and restores to the boundary *before* the
interrupted node, so it re-runs it. The default has no checkpoint events and reconstructs from
node output events, so a node whose output was flushed before the crash is skipped. Neither is
exactly-once; the difference is only where the boundary happens to land.

That is demonstrable. When the kill lands *inside* a node rather than at a boundary — the case
that matters, because that is when a node is mid-way through talking to something external —
the side effect is duplicated in **both** configurations:

```
side effects: ['work:1', 'work:2', 'work:3', 'work:3', 'work:4', 'finish']
duplicated  : {'work:3': 2}
final state : {'iterations': 4}
```

Final state is correct. The externally visible side effect ran twice. ADK's own documentation
says so plainly, in the `ResumabilityConfig` docstring: *"Tool call to resume needs to be
idempotent because we only guarantee an at-least-once behavior once resumed"* and *"Any
temporary / in-memory state will be lost upon resumption."* That is unusually candid and it is
accurate.

**The measurement that matters most for our intended usage.** We plan to host our own agent
loop inside a node. A node running a five-turn internal loop, killed during turn four,
re-executed **all four completed turns** on resume:

```
completed before the kill : ['inner:1', 'inner:2', 'inner:3', 'inner:4']
executed after resume     : ['inner:1', 'inner:2', 'inner:3', 'inner:4', 'inner:5', 'after']
inner turns re-executed   : 4 of 4
```

Zero inner-loop granularity. ADK checkpoints at node boundaries and a hosted loop is opaque to
it. This is exactly what [`research/03`](../../../research/03-graph-and-loop-architecture.md) §9
predicted for "loop inside a node," now measured rather than assumed.

## Primitive 3 — the trap, and what a real ceiling looks like

Run with no budget at all, the four-node graph executed **1,292 `work` iterations and 1,291
`check` iterations in 20 seconds**, emitted 2,584 events, and was still running when the
probe's own timeout fired. `finish` never ran. Nothing in ADK's graph layer counts steps.

Searching the whole package for a cost, token, or wall-clock ceiling across `agents/`,
`runners.py`, and `workflow/` returns nothing. `RunConfig` has exactly one ceiling:
`max_llm_calls`, default 500.

That one is real enforcement, not a warning. Putting an LLM agent inside the same trap with
`max_llm_calls=3` halted the run at exactly three cycles:

```
LlmCallsLimitExceededError: Max number of llm calls limit of `3` exceeded
trace: ['seed', 'check:1', 'check:2', 'check:3']
```

This is the point of comparison flagged in the brief. Prior research found the Claude Agent
SDK genuinely enforces a budget and was unique among surveyed SDKs in doing so. ADK also
genuinely enforces one — but it enforces the *count of model calls*, which is a proxy for cost
that stops being a good one the moment context sizes differ between nodes. Finding 003 already
measured a 40× spread in input context for identical work between two runtimes; a call-count
ceiling cannot see that.

**The budget does not survive resume.** The counter lives on `_InvocationCostManager`, which
hangs off the `InvocationContext`, which is rebuilt per attempt. Resuming an invocation that
had already exhausted a ceiling of 3 ran three more cycles, for **6 total under a ceiling of
3**. An agent that crashes and resumes in a retry loop has no effective ceiling at all. This
is the sharpest single gap in the probe.

There is a step ceiling in ADK, but not where we would use it. `LoopAgent.max_iterations`
enforces one in the template-agent tier — the tier ADK 2.0 explicitly supersedes in favour of
graph workflows. It was not carried across. Its default is also `None`, which is unbounded.
This is source-verified rather than runtime-verified; the legacy tier was not exercised.

## Primitive 2 — what ADK tells you when a run ends

Four scenarios through the same graph:

| Scenario | How the stream ended | What the caller can observe |
|---|---|---|
| Clean completion | generator returned, 8 events | Last event is a plain node output. With `is_resumable=True`, an `actions.end_of_agent=True` marker |
| Node raises | exception out of `run_async`, 2 events | `error_code='RuntimeError'`, `error_message='deliberate node failure'` on the event **and** the exception propagates |
| Consumer cancels after 5 events | generator returned | Nothing. No marker, no signal |
| Trap, probe timeout | never ended | Nothing |

Errors are named, and named well — both as an event field and as a propagating exception.
Budget exhaustion is named by exception type. Everything else is inference.

Completion and cancellation *are* separable, but only under the experimental flag:
`Workflow._emit_end_of_agent` returns early unless `is_resumable` is true. With it on, a clean
run carried the marker and a cancelled run did not. With it off — the default — a run that
finished and a run that was cut off mid-loop produce the same observation from the caller's
side. That is the false-success shape that [`research/03`](../../../research/03-graph-and-loop-architecture.md)
§3 identifies as "a very common and very expensive bug," and it is why FR-002 exists.

What does not exist in any form: a terminal *name*, and the conditions
`goal_satisfied`, `max_steps`, `budget_cost`, `wall_clock`, and `no_progress`. The raw signals
to derive two of them are present. The taxonomy is ours to build.

## Primitive 4 — replay is deterministic until you add concurrency

Four resumes from byte-identical copies of one post-crash snapshot produced one distinct trace
and one distinct final state. Graph mechanics replay deterministically given fixed node
outputs. The model was stubbed out entirely for this arm, so model nondeterminism — expected,
and not what was being tested — could not contaminate the result.

Fan-out is a different story. Three parallel branches with well-separated latencies (0.02s,
0.15s, 0.30s) produced 1 distinct ordering across 5 runs. The same three branches with
overlapping jittered latencies produced **5 distinct orderings across 8 runs**:

```
run 1: ['fan', 'slow', 'join', 'fast', 'join', 'medium', 'join']
run 2: ['fan', 'fast', 'join', 'medium', 'join', 'slow', 'join']
run 3: ['fan', 'slow', 'join', 'medium', 'join', 'fast', 'join']
```

The first result was determinism by construction, not by design: the scheduler dispatches
downstream work in completion order, so the trajectory is a function of wall-clock timing.
Real nodes make network calls with variable latency, so any graph of ours with parallel
branches will have a non-reproducible node ordering. Whether that matters depends entirely on
whether our joins are order-sensitive. If they are, that is a correctness bug waiting to
happen and not merely a replay inconvenience.

## ADK's state and session model, for hosting our own loop

Four properties that would make a hosted loop awkward, beyond the granularity problem above.

**There are no state reducers.** LangGraph's most useful export — per-channel merge functions,
so `messages` appends while `current_plan` overwrites — has no analogue here. Searching for any
reducer, merge-function, or annotated-channel concept across `workflow/` and `agents/` returns
nothing. `Workflow.state_schema` exists but only validates that a `FunctionNode`'s parameter
names appear in the schema; it says nothing about how concurrent writes combine.

The consequence is a silent lost update. Two parallel branches that read a shared key, do
work, then write it back:

```
final value of state['log'] : ['B']
```

Branch A's write vanished with no error and no warning. Any parallel branch that accumulates
into shared state needs its own merge discipline, and `research/03` §3 argues that explicit
per-channel merge functions are what make parallel branches safe in the first place.

> **Widened 2026-08-03, and this paragraph turned out to reach further than the experiment that
> produced it.** The *measurement* here is of ADK's completion-order scheduler and its reducer-free
> state model, and `plan.md` **OD-15** removes both from v1. **The hazard is not ADK's and does not
> go with it.** Every provider in the production spec's SC-010 set can emit **parallel tool calls in
> a single turn**, so a v1 that emits no graph at all still fans out, and a silent lost update is
> therefore a **single-agent hazard** rather than a graph-engine one. Nobody had connected those two
> facts until the production plan phase. **Owner: v1 owns the mitigation outright** — ordering
> discipline plus a write path that cannot lose a concurrent update — recorded at
> [14](../../../research/14-architecture-synthesis.md) §2.6's fourth build item and as T-08 in
> [the production research](../../002-spec-aware-agent-runtime/research.md). The 1–2 day estimate
> beside that item was ADK-shaped and is not re-derived (**U-48**).

**The budget context is per-invocation**, so it resets on resume, as measured above. Any
budget we carry must live in session state, not in the runtime's context object.

**Fan-out ordering is completion-time driven**, so a hosted loop that fans out internally
cannot assume a stable ordering.

**One defect worth reporting upstream.** Cancelling the consumer of `run_async` — breaking out
of the `async for` — reliably raises an OpenTelemetry context error during generator teardown,
reproduced 3 times out of 3:

```
ValueError: <Token var=<ContextVar name='current_context' ...>> was created in a different Context
```

It does not corrupt state and the run's results are unaffected, but it means clean cancellation
is not clean, and it pollutes any log stream where cancellation is routine. Cancellation is
routine in an agent product.

## The largest build item is not ADK's fault

The idempotency and inner-loop journaling work is over half the total estimate, and it is
worth being explicit that **switching runtimes would not avoid it**. LangGraph checkpoints at
super-step boundaries with the same consequence: a node that dies partway re-runs from the top
of the function, side effects and all ([`research/03`](../../../research/03-graph-and-loop-architecture.md)
§6.3). Only a durable-execution engine underneath — Temporal or Restate — journals each step so
that resume skips what already completed.

So the honest framing of that estimate is not "ADK costs us 1.5 weeks." It is "node-boundary
checkpointing costs 1.5 weeks in any agent framework, and buying it back requires a durable
execution layer we have not scoped." That is a separate architectural question and this probe
does not answer it.

## Build items and total

| Item | Why | Estimate |
|---|---|---|
| Terminal-condition wrapper | FR-002 requires a named terminal. ADK names errors and the call-count budget; everything else is ours. Wrap `run_async`, catch `LlmCallsLimitExceededError` and node error events, watch `end_of_agent`, apply our own step/cost/wall-clock predicates, emit one typed terminal. | 2–3 days |
| Budget channel and enforcement plugin | Step, token, and cost ceilings do not exist, and the one that does resets on resume. Build on `BasePlugin.before_model_callback` / `after_model_callback` for token accumulation and `on_event_callback` for step counting, persisted in session state so it survives resume. Needs a per-provider cost table, which finding 003 showed cannot be assumed uniform. | 4–5 days |
| Idempotency and inner-loop journaling | Resume is at-least-once and hosted loops lose all inner progress. Either require stable idempotency keys on every side-effecting node, or journal inner-loop turns to session state so a resumed node skips completed turns. | 1–1.5 weeks |
| Deterministic fan-out ordering | Contingent. Only if replayable parallel trajectories turn out to be required. | 1–2 days, or nothing |

**Total: roughly 2.5–3.5 weeks for one engineer**, of which the journaling layer is over half
and is not ADK-specific.

## What this does NOT establish

This probe used pure Python function nodes for twelve of its fourteen arms. It did not test
checkpoint and resume across nodes that are LLM agents with substantial conversation state,
and provider-opaque reasoning state — the thinking blocks and thought signatures flagged in
finding 003 — is exactly the kind of thing that could fail to survive a resume boundary. That
is untested and should not be assumed.

It did not test the `SqliteSessionService` under concurrent writers, nor
`DatabaseSessionService` or `VertexAiSessionService` at all. The resume results are specific to
SQLite on a local filesystem.

It did not exercise the dynamic-workflow tier (`ctx.run_node()`), which research describes as
having automatic checkpointing and may have different granularity than the graph tier measured
here. If the journaling estimate above is the deciding number for a schedule, that tier is worth
30 minutes before the estimate is committed.

It did not measure ADK's HTTP/SSE serving layer under any of these conditions, and finding 003
already noted that graph-based workflows do not support live streaming — which means the
terminal-condition wrapper and the serving surface interact in a way this probe did not touch.

The build estimates are engineering judgment calibrated against the measured behaviour, not
measurements. They assume familiarity with ADK's plugin surface, which was read but not
written against.

## Immediate next steps

1. ~~**The adopt recommendation for ADK as outer runtime survives, qualified.**~~ **Superseded
   2026-08-03 by [`plan.md` OD-15](../plan.md): ADK is dropped from v1 entirely, and not on this
   document's gate.** Two of four primitives missing against a threshold of three — **that
   measurement is unchanged and OD-15 does not overturn it**; the owner did not take the *missing*
   reading. Three of OD-01's four *grounds* lost their subject or their evidence against a
   single-agent, read-only v1 (OD-09), and lifecycle alone did not justify the dependency. **Two
   consequences for how this finding may be cited from here on.** *"Two of four missing against a
   threshold of three"* is a statement about ADK and **is not a statement about v1's substrate in
   either direction**; and the **2.5–3.5 weeks was scoped to loop safety with the runtime adopted**,
   so it covers none of the nine capabilities that moved to build — no re-derived figure exists in
   any committed artifact
   ([14](../../../research/14-architecture-synthesis.md) **U-48**). What survives intact is this
   document's measurements and the reasoning drawn from them, including that checkpoint and resume
   was the one primitive measured **present and working, 5/5 reproducible** — on ADK's event-sourced
   replay over `SqliteSessionService`, which v1 does not ship, so **v1 has no measured resume
   machinery at all.**

2. **Record the counting sensitivity as an owner decision.** If checkpoint/resume is judged
   missing on at-least-once and experimental-flag grounds, the count is three and ADK becomes a
   library we call. This should be settled explicitly rather than inherited from this document's
   recommendation.

3. **Never ship with `ResumabilityConfig` unset.** Without `is_resumable=True` there is no
   `end_of_agent` marker, and a cancelled run is indistinguishable from a completed one. Accept
   the at-least-once re-execution and build idempotency, rather than accepting silent
   false-success. The flag is `@experimental`, so pin the ADK version and re-verify on upgrade.

4. **Treat `max_llm_calls` as a backstop, not a budget.** It is real enforcement and worth
   setting, but it counts calls rather than cost and it resets on resume. Set it low as a safety
   net and build the real budget in session state.

5. **Decide whether a durable execution layer is in scope** before committing the journaling
   estimate. That decision changes the size of the largest build item and is not answered here.

## Reproduction

~~Probe scripts are in `/tmp/f2a-probe-runtime/` (`e6_graph.py` and `e6_p1*` through `e6_p5*`).
They are scratch artifacts, not committed code, and depend on the virtualenv described in the
method note.~~ Each script prints its own verdict line and the counts quoted above.

> **Correction, 2026-08-02 — the scripts are committed. See
> [`harness/graph-loop-primitives/`](../harness/graph-loop-primitives/).**
>
> What was believed: that the probes would remain scratch artifacts in `/tmp`, so E6's numbers
> were not reproducible from committed configuration. [`VERDICT.md`](../VERDICT.md) adjudicated
> SC-005 partly on that basis, and the requirements checklist repeated it.
>
> What is now known: every script named above survived in `/tmp/f2a-probe-runtime/` and was
> recovered on 2026-08-02. **They are recovered, not rewritten** — the committed code is what
> actually ran, sanitized only where it hardcoded a private path (`envload.py`) and a scratch
> directory. The pins in
> [`harness/runtime-provider-agnosticism/requirements.txt`](../harness/runtime-provider-agnosticism/requirements.txt)
> were read out of the surviving virtualenv rather than guessed, and E5 and E6 share it exactly
> as the method note records.
>
> **Scope of this correction.** Recovery is not a complete run record, and the harness README's
> **Gaps** section names what it does not reproduce — three surviving raw artifacts are
> committed under `results/` with a `PROVENANCE.md`, and the rest of the probes' stdout was
> never captured. The build estimates in this finding remain engineering judgment, not
> measurement, exactly as originally marked.
