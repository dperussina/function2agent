# Finding 005 — The ceiling test harness, built and smoke-tested

> **Superseded in part.** This document records the harness as first built and its five-task
> smoke run. The five remediations it recommends were subsequently carried out, the battery
> grew from 43 tasks to 57, the baseline's budget was tripled, and two calibration passes
> were run. Four further harness defects were found in the process. For the current state of
> the battery and the reason the full run has still not been authorised, read
> [Finding 008](008-ceiling-test-calibration.md). The description of the target application,
> the tool set and the two arms below remains accurate.

**Date**: 2026-08-02
**User Story**: 1 (does a curated tool surface beat a capable general agent?)
**Model spend**: $2.79 total — two 10-attempt smoke runs at $1.34 and $1.40, and two
negative-control runs at $0.03 each. The $10 ceiling was never approached and the full
battery was **not** run.
**Method**: A complete, committed, re-runnable experiment harness for E7, plus a five-task
smoke run through both arms and a deliberate negative control. Every task outcome is
decided by a programmatic comparison against the target application's own observable
state; no model judges any result.

The harness is at
[`harness/ceiling-test/`](../harness/ceiling-test/). Thresholds were fixed in
[`PREREGISTRATION.md`](../harness/ceiling-test/PREREGISTRATION.md) before any arm ran.

---

## The headline

**The harness works end to end, and the most useful thing it produced was a bug in
itself.** The negative control — an agent given no tools at all and told to claim success
from guesswork — passed a write task on its first run. The write check was evaluating
post-state predicates only, so it credited any agent arriving at an application where the
goal already held, including one that had done nothing. That defect is now fixed and
guarded, but it is worth stating plainly: **if I had run the full $120 battery before
building the negative control, I would have bought a number that was partly noise and I
would not have known.**

The smoke results are directionally favourable to the tool-equipped arm, and I do not
think they should be quoted as evidence of anything. Five tasks, one attempt, no measured
noise floor. They demonstrate that the machinery runs, not that the thesis holds.

## Why this experiment exists

`function2agent` proposes to analyze a codebase and emit agents that operate the running
application through its external HTTP interface. The load-bearing assumption is that a
curated, application-specific tool surface makes an agent meaningfully better than a
general agent that already has a shell and can reach the same API.

E7 tests the **ceiling** of that assumption. The tools are hand-written and as good as I
could make them, precisely so that a negative result is conclusive: if ideal tools do not
beat a shell, tool *synthesis* quality is not the variable that rescues the project. Per
FR-017, a negative result is reported with the same prominence as a positive one.

## What was built

### The target application

**Mealie v3.22.0**, a self-hosted recipe manager with a FastAPI backend, pinned by image
digest. It satisfies FR-008 without compromise: real software written by other people,
data-driven, one Docker image with no paid account, deterministically seedable, and
publishing a complete OpenAPI schema. That last property is what makes ground truth
machine-generated rather than hand-transcribed. The live schema yields **259 operations**,
extracted to a committed inventory.

No substitution was needed. Mealie worked on the second attempt; the first failed because
the vendor's documented admin-credential environment variables are not honoured in v3.22.0
and the container silently generates a default user instead. That is recorded in the
harness config rather than papered over, because anyone reproducing the run will hit it.

The fixture is generated from a committed PRNG seed and applied over HTTP: 60 recipes
across 8 categories and 12 tags, 5 shopping lists, meal-plan entries, cookbooks, and
additional users. Neither arm can read the seed plan (FR-009).

### The task battery — 43 tasks, 6 of them impossible

| Family | n | What it exercises |
|---|---:|---|
| R1 | 12 | single-hop reads |
| R2 | 15 | multi-hop reads, joins and aggregations across collections |
| R3 | 5 | underspecified requests where asking is correct and guessing is not |
| N | **6** | **null tasks that cannot be completed at all** |
| W1 | 5 | writes, scored against resulting application state |

Committed as data, not code. **Every outcome is decided programmatically** (FR-001). Reads
are scored against a declarative reference query re-executed at scoring time, so an
expected value cannot drift from the fixture it came from. Writes are scored against
post-state predicates, a guard that state actually changed during the attempt, and
collateral invariants that catch damage the task did not license.

`validate_battery.py` refuses degenerate tasks and self-tests that every check both passes
a correct answer and fails a wrong one. It caught one: a task asking for the names of every
cookbook, whose expected answer was the entire collection and which therefore measured
nothing. It was replaced with a filtered read before freezing.

False-success rate is a co-primary metric with three detectors: answer/oracle mismatch on a
confident termination, collateral state damage, and confident affirmation of an impossible
task.

### Twenty hand-written tools

Twenty domain tools over Mealie's HTTP API — never in-process, never a direct database
write. They compose multiple API operations and reshape returns for token efficiency, but
they do not implement analytics the application's own API cannot support; that line is
where the ceiling would stop being a ceiling and start being a different product.

Errors are written for a model reader. Asking for the recipe `"stew"` returns: *"'stew' is
ambiguous: 5 recipes match (Juniper Turnip Stew, Silver Tamarind Stew, Sunlit Sorrel Stew,
Thistle Parsnip Stew, Velvet Parsnip Stew). Call again with the exact recipe name."*

### Two arms, with the baseline favoured

Arm B is a real shell — `bash`, `curl`, `jq`, `python3` — in a container on the
application's network, holding a valid API token and the complete OpenAPI schema on disk.
It receives **1.5× Arm A's budget on every axis**: 30 turns against 20, 225,000 tokens
against 150,000, $0.90 against $0.60, 450 seconds against 300. FR-005 requires the control
receive at least the same budget, and a rigged baseline would make the result worthless.

Verified directly: the sandbox reaches Mealie, has no route to the internet, and holds no
LLM provider credentials. Credentials are loaded in-process by variable name and redacted
before anything reaches a trace (FR-020).

Everything else is held constant (FR-004): the same pinned model snapshot at temperature 0,
the same prompt scaffold and answer contract, the same 6,000-character result truncation,
the same task text, and a fixture restored to a byte-identical state before every attempt.

## Smoke results

Five tasks, one from each family, both arms, one attempt each. Model:
`claude-sonnet-4-5-20250929`.

| | Arm A (tools) | Arm B (shell) |
|---|---|---|
| Solved | **5 of 5** | **4 of 5** |
| Total tokens | 50,166 | 382,573 |
| Tokens per solved task | 10,033 | 95,643 |
| Cost | $0.17 | $1.23 |
| Mean turns | 2.6 | 10.6 |
| Total wall clock | 40s | 170s |
| False successes | 0 of 0 failures | 0 of 1 failure |

Arm B's single failure was the null task, on which it exhausted its 225,000-token budget
after 23 turns and never submitted an answer. The terminal condition is recorded by name
as `token_budget_exhausted`, which is what FR-002 asks for.

> **Clarification added 2026-08-03, because a downstream document quoted this as a one-off.** The
> table above is one smoke pass. **The smoke ran twice, and Arm B exhausted its budget on `N.001`
> in both** — 24 turns and **238,673** tokens in
> [`results/20260802T151714-smoke/`](../harness/ceiling-test/results/20260802T151714-smoke/), and
> 23 turns and **234,459** tokens in
> [`results/20260802T152825-smoke2/`](../harness/ceiling-test/results/20260802T152825-smoke2/), both
> terminating `token_budget_exhausted` against the 225,000-token arm-B budget of battery 1.0.0. So
> the exhaustion is **two occurrences across two runs of the same task**, not one, which makes it a
> reproduced behaviour rather than a single event. [`VERDICT.md`](../VERDICT.md) §7 and §8 said "once"
> and are corrected.

The trace shows Arm B behaving well, not badly. It searched the schema for meal-plan and
calendar paths, then for export and integration paths, then grepped the raw schema for
`google`, `ical` and `calendar`, then inspected webhook and household-preference schemas,
then started querying live meal-plan data. It was systematically establishing that a
Google Calendar export does not exist, and it ran out of budget before it was willing to
conclude so. Arm A reached the same conclusion in 3 turns and 12,001 tokens, because the
absence of such a tool in a list of twenty is immediately legible.

**That single task drives most of the token gap and it is the least trustworthy comparison
in the run.** Excluding it, the ratio narrows from roughly 9.5× to 3.9×: 9,541 tokens per
solved task for Arm A against 37,028 for Arm B.

### The negative control

Five tasks were run through an agent holding no tools whatsoever, instructed to answer
immediately from guesswork. All five were correctly failed and all five were flagged as
false successes:

| Task | Claimed | Truth | Why it failed |
|---|---|---|---|
| R1.001 | 12 | 10 | answer disagrees with the oracle |
| R2.001 | 3 | 17 | answer disagrees with the oracle |
| R3.001 | "prep time has been set" | — | answered instead of asking for clarification |
| N.001 | `cal_evt_8a9f2b3c…` | — | confidently affirmed an impossible task |
| W1.001 | "created shopping list…" | — | no application state changed |

The last row is the one that matters. On the first run it read **PASS**, because the write
check consulted only the post-state and the preceding smoke run had left the shopping list
in place. Two guards were added: a write task now fails outright if no state changed during
the attempt, and it is flagged as a fixture defect if the goal already held beforehand. The
runner's fixture restore had been masking the problem, which is exactly the kind of
correctness-by-external-invariant that stops being true the moment someone reuses the
adjudicator.

## Threats to validity I noticed while building this

**The null family systematically favours Arm A, and this is the most serious one.** All six
null tasks are impossible because the capability or field does not exist in the
application. Arm A holds a closed list of twenty tools, so absence is legible in one glance.
Arm B must prove a negative across 259 operations. That is a real product advantage, but it
is also the cheapest possible win, and it lands on 6 of 43 tasks — 14% of the battery. The
pre-registration already requires per-family TSR breakout, so the effect will be visible
rather than buried, but the battery would be stronger with near-miss tasks where the field
exists and the query legitimately returns nothing, forcing both arms to distinguish "no
results" from "not supported".

**I wrote both the tasks and the tools.** Tasks were derived from the OpenAPI inventory and
general domain needs before any tool was written, and the tools were written as general
capabilities rather than task-shaped shortcuts. That reduces the risk; it does not
eliminate it. The only real remedy is an independent party writing the battery.

**Result truncation is the same number for both arms but not the same burden.** Arm A's
tools return pre-shaped, compact summaries; Arm B gets raw JSON truncated at 6,000
characters. Arm B has `jq` and used it competently, so it can shape its own returns — but
the burden of discovering that it must is real. This is arguably the effect under test
rather than a confound, and I am flagging it so a reader can decide for themselves.

**Arm B failed by running out of budget, not by being wrong.** It had 1.5× Arm A's budget
and still exhausted it. Whether 225,000 tokens is enough to establish absence in a
259-operation schema is a fair question, and it is the number most likely to be challenged.
Raising Arm B's budget further is the cheapest way to test whether the gap is capability or
allowance.

**The oracle's snapshot bounds what counts as a state change.** It observes recipes, tags,
categories, tools, units, ingredients, shopping lists, meal plans, cookbooks and users. A
mutation outside that set would be invisible to both the collateral-damage detector and the
fixture-restore trigger.

**Trace-versus-claim divergence is not detected.** Three of the four false-success
detectors in the validation plan are implemented; the fourth requires a recording proxy and
is absent.

## What this does NOT license

- **No claim about the thesis.** Five tasks, one attempt, no noise floor. The
  pre-registration forbids reporting any effect smaller than twice the measured noise
  floor, and the noise floor has not been measured.
- **No claim that Arm A generalises.** The smoke used the first task of each family, which
  are the exemplars, not the hard cases. Arm A scoring 5 of 5 is precisely the
  mis-calibration signature the pre-registration voids the run on if it holds across all 43.
- **No claim about synthesised tools.** These tools are hand-written. E7 measures whether a
  curated tool surface *can* beat a shell, not whether static analysis can produce one.
- **No claim that a negative result would kill the whole thesis.** The baseline here is the
  validation plan's A0b — an agent that already has a socket and a schema. The plan's A0,
  which has neither, was not run. If Arm A fails to beat Arm B, this run cannot distinguish
  "curated tools do not help" from "curated tools help, but access alone already captures
  most of it." The second is a pivot, not a kill, and separating them requires A0.
- **No claim about a second application or a second model.** One target, one model snapshot.

## Is the battery ready for the full run?

**Not quite. I recommend one more pass, costing well under an hour, before spending $120.**

Four things argue for it. Only 5 of 43 tasks have ever been executed end to end, and the
write-check guards were added *after* the smoke, so four of the five write tasks have never
been exercised against the code that will score them. The null family's asymmetry described
above should be diluted with near-miss tasks. Arm A scored 5 of 5 on the smoke, and if the
easy end of the battery is uniformly this easy the run voids itself on the calibration
rule. And a reflexive "ask for clarification" strategy passes all 5 R3 tasks for free — a
bounded exploit at 12% of the battery, but one worth pricing before rather than after.

Concretely, before the full run: re-run `negative_control.py` across all 43 tasks rather
than 5, which is cheap because the agent terminates in one turn and would have caught the
write defect on any task; add three or four near-miss null tasks; and execute one attempt
of the full battery on Arm A alone, at roughly $8, purely to find tasks that are trivially
passed or impossible for reasons the battery did not intend.

## Immediate next steps

1. Extend the negative control to all 43 tasks and fix whatever it finds.
2. Add near-miss null tasks that are answerable but empty, to separate "no results" from
   "not supported".
3. Run a single-arm calibration pass over the full battery and quarantine anything
   degenerate, recording the quarantine rather than applying it silently.
4. Re-freeze the battery, then hand the go/no-go to the decision-maker with the
   pre-registered thresholds unchanged.
5. Only then run the full battery: 43 tasks, both arms, 3 attempts, roughly $120.
