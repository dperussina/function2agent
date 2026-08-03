# E6 harness — does ADK supply the loop-safety machinery, or do we build it?

Produces the numbers in
[`findings/006-graph-loop-primitives.md`](../../findings/006-graph-loop-primitives.md),
the probe behind **OD-01** (adopt Google ADK for graph execution and build our own
safety layer on top).

Run `./run.sh`. Model spend is about **$0.0003**: twelve of the fourteen arms use pure
Python function nodes and cost nothing, and only the two budget arms call a model.

> **Recovered, not reconstructed.** Every script here is the one that produced the
> finding, recovered from `/tmp/f2a-probe-runtime/` on **2026-08-02**. Changes made
> during recovery are enumerated in [§What changed](#what-changed-during-recovery) and
> none of them touch a measurement.
>
> Finding 006 §Reproduction and [`VERDICT.md`](../../VERDICT.md) both state these are
> "scratch artifacts, not committed code." That was true when written. They survived
> and are committed here; the finding's Reproduction section is now out of date.

## Several arms kill themselves on purpose

`Killed: 9` in the output is the measurement, not a failure. Crashes are a real
`SIGKILL` to the probe's own PID, chosen so that no `finally` block, no `atexit` hook,
and no graceful shutdown path can run. The resume arms therefore span **two OS
processes against one persistent SQLite session**, which is why they are invoked as
`phase1` then `phase2`.

## The graph under test

Four nodes, one cycle, one deliberate non-termination trap. `check` unconditionally
routes `again`, so nothing in the graph ever terminates on its own:

```
START -> seed -> work -> check
                  ^        |
                  +--again-+          <- the trap
                           +--done--> finish   (unreachable while trapped)
```

`e6_graph.reset(stop_after=N)` disarms the trap after N iterations, which is how the
same graph serves both the "does it ever stop" arms and the "does it resume correctly"
arms without changing anything else.

**Every verdict is decided programmatically** — by a node-execution ledger appended to
inside the node bodies, by `fsync`ed side-effect logs that survive `SIGKILL`, by
exception types, and by comparing session state dictionaries. No verdict is decided by
reading model output (FR-001).

## What each piece does

| File | Primitive | Purpose |
|---|---|---|
| `run.sh` | — | End-to-end reproduction. Arms: `./run.sh p1 p2 p4 p5` (default, zero cost) or `./run.sh p3` (needs a credential). |
| `e6_graph.py` | — | The shared four-node graph, the execution ledger, and the trap. |
| `e6_paths.py` | — | Scratch paths, honouring `F2A_PROBE_DIR`. |
| `envload.py` | — | Delegates to the E5 harness's credential loader, which is the same module the original probes imported. Only the `p3` arms need it. |
| `e6_p1_resume.py` | 1 | `SIGKILL` at a node boundary with `is_resumable=True`; a fresh process reopens the session and resumes. |
| `e6_p1b_default.py` | 1 | The identical crash with the flag left at its **default of False** — what a caller gets who does not know the flag exists. |
| `e6_p1c_repeat.py` | 1 | Five trials per configuration, to show the resume boundary is stable rather than a flush-timing accident. |
| `e6_p1d_midnode.py` | 1 | **The case that matters.** The kill lands *inside* a node, after its durable side effect and before it returns. |
| `e6_p2_terminals.py` | 2 | Four scenarios — clean, node raises, consumer cancels, trap — and what the caller can observe from each. |
| `e6_p2b_cancel.py` | 2 | Whether `end_of_agent` separates completion from cancellation, run with the experimental flag **on**, which is the only configuration where it could. |
| `e6_p3a_steps.py` | 3 | The trap with no guard but a probe timeout. If ADK had a step ceiling the run would end by itself. |
| `e6_p3b_budget.py` | 3 | Puts a real LLM agent in the trap with `max_llm_calls=3`. **Calls a model** — this is the one question that cannot be answered without one. |
| `e6_p3c_budget_resume.py` | 3 | Exhausts the ceiling, then resumes the same invocation and counts again. **Calls a model.** |
| `e6_p4_replay.py` | 4 | Four resumes from byte-identical copies of one post-crash snapshot. The model is stubbed out, so any divergence is graph mechanics. |
| `e6_p4b_parallel.py` | 4 | Fan-out with well-separated branch latencies (0.02s / 0.15s / 0.30s). |
| `e6_p4c_jitter.py` | 4 | Fan-out with **overlapping** jittered latencies — the case that shows the first result was determinism by construction. |
| `e6_p5_hostloop.py` | — | Hosting our own loop inside an ADK node: inner-loop granularity across a crash, plus concurrent state writes. |
| `e6_p5b_race.py` | — | The corrected concurrent-write arm. See below. |
| `results/` | — | Three genuine raw artifacts. See [`results/PROVENANCE.md`](results/PROVENANCE.md). |

### `e6_p5b_race.py` supersedes `e6_p5_hostloop.py` for part B

The two files are identical except for the writer node. In `e6_p5_hostloop.py` the
branch sleeps and *then* reads shared state; in `e6_p5b_race.py` it reads first, sleeps,
then writes back — the classic lost-update shape a reducer exists to prevent. **The
finding's `['B']` result is the latter.** Part A is byte-identical in both. Both are
kept because the pair is the evidence that the result is about read-modify-write
ordering rather than about ADK dropping writes at random.

## Verification: which arms were re-run during recovery

Re-run on 2026-08-02 against `google-adk 2.6.1` in the surviving virtualenv, into a
separate scratch directory so the original artifacts were not overwritten.

| Arm | Finding says | Observed on re-run | |
|---|---|---|---|
| `e6_p1_resume` | 17 persisted events, resumed at `work:3`, 7 total `work`, state `{'iterations': 6, 'topic': 'go'}` | identical on all four | ✅ |
| `e6_p1b_default` | 7 persisted events, resumed at `check:3`, 6 total `work` | identical | ✅ |
| `e6_p1d_midnode` | `['work:1','work:2','work:3','work:3','work:4','finish']`, dup `{'work:3': 2}`, state `{'iterations': 4}` | character-for-character identical | ✅ |
| `e6_p2_terminals` | 8 events clean / 2 with `error_code='RuntimeError'`, `error_message='deliberate node failure'` / cancellation yields nothing / trap never ends | all four rows identical | ✅ |
| `e6_p2b_cancel` | completion and cancellation distinguishable with the flag on | identical, and the OpenTelemetry teardown defect reproduced verbatim | ✅ |
| `e6_p4b_parallel` | 1 distinct ordering across 5 runs | 1 of 5 | ✅ |
| `e6_p5_hostloop` A | `4 of 4` inner turns re-executed | character-for-character identical | ✅ |
| `e6_p5b_race` B | `final value of state['log'] : ['B']` | identical | ✅ |
| `e6_p3a_steps` | **1,292** `work` iterations in 20s, 2,584 events, `finish` never ran | **1,352** iterations, 2,704 events, `finish` never ran | ⚠️ see below |

**Not re-run:** `e6_p1c_repeat` and `e6_p4_replay` (long; they drive the arms above as
subprocesses), `e6_p4c_jitter` (unseeded, see below), and `e6_p3b_budget` /
`e6_p3c_budget_resume` (need a credential).

⚠️ **`e6_p3a_steps` measures throughput, so its integer is machine-dependent.** 1,292
and 1,352 are the same result — "ADK's graph layer counts nothing, and the only thing
that stopped the run was our own wall clock." Read the qualitative verdict, not the
count. `finish` never running and the run still going at the timeout are the parts that
carry the primitive-3 conclusion.

`e6_p4c_jitter`'s RNG is **unseeded and partly evaluated at import time**, so the
finding's "5 distinct orderings in 8 runs" is a sample, not a target. Any result
greater than 1 supports the claim; exactly 5 should not be expected. This is left as it
ran rather than seeded, because seeding it would make it a different experiment from
the one the finding reports.

## `results/` holds three real artifacts and no run log

`e6_side_effects.log`, `e6_host_effects.log`, and `e6_replay_snapshot.db` are genuine
raw output recovered from the original run — the first two are byte-identical to blocks
quoted in the finding, and the third is the 49,152-byte snapshot whose
`sha256=11fa3ec8…` the finding cites, so that citation is now checkable.

**The original stdout was never captured to a file.** The verdict lines in finding 006
were transcribed from a terminal. Nothing has been fabricated to fill that space. See
[`results/PROVENANCE.md`](results/PROVENANCE.md).

## Gaps — claims in finding 006 that this harness does not reproduce

| Claim | Status | Why |
|---|---|---|
| §Primitive 3 — "searching the whole package for a cost, token, or wall-clock ceiling across `agents/`, `runners.py`, and `workflow/` returns nothing" | **No script.** | A source search whose exact form was not recorded. Mechanically checkable against the pinned package; nothing is shipped that would imply the original method is known. |
| §State and session model — "searching for any reducer, merge-function, or annotated-channel concept across `workflow/` and `agents/` returns nothing" | **No script.** | Same. The *consequence* — the lost update — is measured by `e6_p5b_race.py`; the absence-of-concept search is not. |
| §Primitive 3 — `LoopAgent.max_iterations` exists in the legacy template-agent tier and was not carried across, default `None` | **Not exercised.** | The finding already labels this source-verified rather than runtime-verified. The legacy tier is not touched by any arm here. |
| §Defect — the OpenTelemetry teardown error "reproduced 3 times out of 3" | **Partial.** | It reproduces reliably (and did again during recovery), but no arm loops it three times and counts. |
| §Model spend — ≈$0.0003 across nine LLM calls | **Partial.** | The `p3` arms make the calls; no cost accounting is written out. The figure was read from provider usage after the fact. |
| §Build items — 2–3 days, 4–5 days, 1–1.5 weeks, 2.5–3.5 weeks total | **Not measurable, and correctly labelled.** | The finding states these are engineering judgment calibrated against measured behaviour, not measurements. Nothing here should be read as reproducing them. |

## Warts, left as they ran

- **`e6_p1_resume.py` prints `VERDICT: AMBIGUOUS`** on a correct run. Its classifier was
  written expecting exactly-once semantics; at-least-once resume re-runs the in-flight
  node, giving 7 total `work` executions against an expected 6, which falls through to
  the ambiguous branch. **That output is the primitive-1 result, not a malfunction.**
  Read the event count and the trace.
- **`e6_p5_hostloop.py` and `e6_p5b_race.py` write the same scratch filenames**
  (`e6_host.db`, `e6_host_ledger.json`, `e6_host_effects.log`). Running one's `phase1`
  and the other's `phase2` would interleave. `run.sh` does not do that; a manual
  invocation could.
- **`e6_p4c_jitter.py`'s branch names are vestigial.** `slow`, `medium`, and `fast` all
  receive the same base delay expression, evaluated once at import, so the labels no
  longer describe the durations. That is what makes the latencies overlap, which is the
  point of the arm, but the names mislead on a first read.
- `e6_p4b_parallel.py` imports `random` and never uses it.

## What changed during recovery

| Change | Why | Affects a measurement? |
|---|---|---|
| Hardcoded `/tmp/f2a-probe-runtime/...` paths for session DBs, ledgers, and side-effect logs → `e6_paths.path(...)`, honouring `F2A_PROBE_DIR` | So a third party can run this without writing into one machine's scratch directory. The default is unchanged, so a bare run behaves exactly as the original. | No. |
| `PY = "/tmp/f2a-probe-runtime/.venv/bin/python"` → `sys.executable` in the two subprocess-spawning arms | The child phases land in whatever virtualenv the parent is running in. | No — same interpreter when invoked correctly. |
| The same two arms now resolve sibling scripts relative to their own directory | They previously assumed a fixed absolute location. | No. |
| `e6_p1c_repeat.py`: `subprocess.run(["rm", "-f", ...])` → `os.remove` | Removes a shell dependency from a cleanup step. | No. |
| Added `envload.py` shim delegating to the E5 loader | The original shared one `envload.py` across both experiments; the shim preserves that rather than forking a second copy. | No. |
| Added `run.sh`, `results/PROVENANCE.md`, this README | None of the three existed. | No. |

Dependency pins live in
[`../runtime-provider-agnosticism/requirements.txt`](../runtime-provider-agnosticism/requirements.txt),
because the two experiments shared one virtualenv and finding 006's method note says it
was "reused rather than rebuilt." **The LiteLLM macOS wheel hazard documented there
applies to this harness too** — E6 does not import LiteLLM directly, but `google-adk`
does, so the install path is the same.

## Prerequisites

Python 3.12 and a local filesystem that supports `fsync`. Twelve arms need nothing
else. The two `p3` arms need `F2A_ENV_ROOT` and a Google credential.

The resume results are **specific to `SqliteSessionService` on a local filesystem**.
`DatabaseSessionService` and `VertexAiSessionService` were not exercised at all, and
SQLite was not exercised under concurrent writers.
