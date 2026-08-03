# E7 ceiling test — pre-registered thresholds

**Recorded**: 2026-08-02, before any arm ran against the frozen battery.

**Authority**: FR-006. Nothing below may be revised once results are visible. A revision
requires a dated entry naming who changed what and why, and the report must then state
both the pre-registered and the revised number.

**Source**: thresholds are taken from
[`research/11-validation-plan.md`](../../../../research/11-validation-plan.md) §1 (H0, H0′)
and §7 (Phase 0), and from [`plan.md`](../../plan.md) Stage C. Where this document names a
number that those sources do not, it is marked **newly set here** with the reason.

---

## What is being compared

| Arm | Capability | Budget |
|---|---|---|
| **A** — tool-equipped | 20 hand-written ideal domain tools over the application's HTTP API | 20 turns, 150k tokens, $0.60, 300s per attempt |
| **B** — baseline | A real shell with `curl`, `jq`, `python3` and text tools, in a container on the application's network, holding a valid auth token and the application's complete OpenAPI schema on disk | 30 turns, 225k tokens, $0.90, 450s per attempt |

Arm B receives **1.5× Arm A's budget on every axis**. FR-005 requires the control receive
at least the same budget; the asymmetry is deliberate and favours the control.

Everything else is held constant (FR-004): the same pinned model snapshot, the same
sampling parameters, the same system-prompt template, the same `submit_answer` contract,
the same tool-result truncation limit, the same fixture restored to a byte-identical state
before every attempt, and the same task text.

### The control we are running, and the one we are not

Arm B is **A0b** in the validation plan's matrix — the baseline that already has network
access to the running application and its specification. It is the meaner of the two
controls the plan defines and the one most likely to embarrass the product.

We are **not** running **A0** (shell and code search with no access to the running
application). That has a direct consequence for what a negative result means, and it is
recorded here rather than discovered afterwards:

- If Arm A beats Arm B by the margin below, it necessarily also beats A0, so H0 clears.
- If Arm A does **not** beat Arm B, this run cannot distinguish "curated domain tools do
  not help" from "curated domain tools help, but a socket plus a schema already captures
  most of that help." The second is a pivot, not a kill. Separating them requires A0 and
  is out of scope for this run.

## Primary metric

**Task success rate (TSR), pass@1**, pooled over all 43 tasks, per arm. An attempt
succeeds only when the programmatic check passes: the reference query's value matches, or
the state predicates hold and no collateral invariant moved. No model judges any outcome
(FR-001).

Reported with a bootstrap 95% confidence interval resampled over tasks.

## Co-primary metric

**False-success rate (FSR)** = (failed attempts in which the arm terminated voluntarily
and confidently asserted an answer or a completed change) ÷ (failed attempts). Reported
pooled and per detector:

- **D1** — answer disagrees with the oracle on a confident, voluntary termination
- **D3** — collateral damage: state changed in a way the task did not license
- **D4** — null-task affirmation: a confident answer to an impossible task

D2 (trace/claim divergence via a recording proxy) is not implemented in this version.

## Secondary metrics

Tokens per solved task; dollars per solved task; turns per attempt; wall clock p50 and
p95; the distribution of named terminal conditions; TSR broken out by family
(R1 / R2 / R3 / N / W1).

## Decision table — binding

Let `Δ = TSR(A) − TSR(B)` in percentage points, and `ρ = tokens-per-solved(A) ÷
tokens-per-solved(B)`.

| Condition | Verdict | Consequence |
|---|---|---|
| `Δ ≥ 15` **or** (`ρ ≤ 0.5` and `Δ ≥ −3`) | **CLEAR** | E7 clears. Proceed to Stage D. |
| `5 ≤ Δ < 15` and `ρ > 0.5` | **PIVOT** | Curated tools help, but not by the margin the thesis assumed against an agent that already has a socket and a schema. Re-scope toward a spec-aware runtime plus verification before any Stage D work. |
| `Δ < 5` and `ρ > 0.5` | **STOP** | The thesis as stated is not supported. Report it plainly as a negative result, with equal prominence (FR-017). |
| `TSR(A) > 0.85` **or** `TSR(A) < 0.25` | **VOID** | The battery is mis-calibrated (§3.6). Fix the task set and re-run before quoting any number, including the ones above. |
| `FSR(A) > 0.25` **or** `FSR(B) > 0.25` | **INVESTIGATE FIRST** | Investigate before any other result is quoted. A system that is confidently wrong a quarter of the time it fails is not shippable at any success rate. |

The `Δ ≥ 15` and `ρ ≤ 0.5` figures are H0 in §1 of the validation plan. The 5 pp boundary
between PIVOT and STOP is §7's "TSR(A0b) within 5 pp of TSR(A8) → PIVOT", read in the
direction this two-arm run can evaluate. **The FSR threshold of 0.25 is newly set here**:
`plan.md` requires a threshold but §7 names none, and it is recorded now rather than
chosen after the numbers arrive.

## Attempts, noise, and what may be claimed

- **Attempts per task per arm: 3** for the full run. Fixed before running (edge case
  "model nondeterminism"), and reported alongside every model-dependent number.
- **Noise floor.** With three attempts, the noise floor is the largest TSR difference
  between any two single-attempt passes of the *same* arm. **No effect smaller than twice
  that floor may be reported as a difference** (§9.3). If the floor exceeds 7.5 pp, the
  15 pp threshold is too tight to be measurable at this battery size, and that fact is
  reported rather than worked around.
- **Statistical power.** 43 tasks gives roughly ±7 pp at 95% confidence around a 50%
  success rate. A 15 pp effect is detectable; a 5 pp effect is not and will not be
  claimed (§9.7). Where confidence intervals overlap, the reported result is "no
  detectable difference", not a winner.
- **`pass^3`** — the fraction of tasks where all three attempts pass — is reported
  alongside pass@1, because a system with pass@1 = 0.6 and pass^3 = 0.1 is not a 60%
  system in any operational sense.

## Protocol commitments

1. The battery is frozen. `tasks.json` carries `battery_version` and the fixture hash;
   `expected.json` carries the expected values computed at freeze time, and the runner
   refuses to start if the live fixture no longer reproduces them.
2. Per-arm prompt tuning is forbidden (§9.6). Both capability blocks were written in one
   sitting, before any arm ran.
3. If a task's check turns out to be satisfiable by an unintended shortcut, the task is
   quarantined and every result that depended on it is invalidated and re-run. The
   quarantine is recorded in the finding, not silently applied.
4. A tie is reported as a tie. A negative result is reported with the same prominence as
   a positive one (FR-017).
5. The person empowered to call the kill is the project's decision-maker, not the engineer
   who built the harness (§9.8).

---

# Amendment A1 — 2026-08-02, before any full-battery result was visible

**Authorised by**: the project owner, on reviewing Finding 005 (the harness build and its
five-task smoke run).

**Status**: permitted under FR-006 because no full-battery result existed when it was
made. The only results in evidence were the smoke run and the negative control, both of
which are reported in Finding 005. **The decision table above is unchanged.** Every
threshold, boundary and metric definition in the original document stands exactly as
written.

## A1.1 — Arm B's budget raised from 1.5× to 3× Arm A

| Axis | Arm A | Arm B before | Arm B now |
|---|---|---|---|
| Turns | 20 | 30 | **60** |
| Tokens | 150,000 | 225,000 | **450,000** |
| Spend | $0.60 | $0.90 | **$1.80** |
| Wall clock | 300s | 450s | **900s** |

**Why.** In the smoke run Arm B lost its single failed task by exhausting 225,000 tokens
after 23 turns, not by answering incorrectly. Its trace showed systematic, competent
behaviour throughout: it searched the OpenAPI schema for meal-plan and calendar paths, then
for export and integration paths, then grepped the raw schema, then inspected webhook and
household-preference schemas, then began querying live data. It was establishing a negative
across 259 operations and ran out of room before it was willing to conclude.

A baseline that loses on headroom is a weak baseline, and a weak baseline is the most
common way to manufacture a positive result. Raising the allowance removes the cheapest
objection to any finding in Arm A's favour. If Arm B still exhausts frequently at 3×, that
is a legitimate and interesting result about the cost of operating an application through a
raw shell — but it is a statement about **cost**, not about **correctness**.

## A1.2 — Budget exhaustion is now a first-class reported metric

**Budget-exhaustion rate** = (attempts whose terminal condition is one of
`token_budget_exhausted`, `max_turns_exhausted`, `cost_budget_exhausted`,
`wall_clock_exhausted`) ÷ (attempts), reported per arm and per family alongside TSR.

An exhausted attempt is reported as **"could not finish within budget"** and is never
described as the arm getting the answer wrong. The two mean different things for the
product: the first says the approach is expensive, the second says it is unreliable. Note
that an exhausted attempt still counts as a non-success in TSR, because the task was not
completed — but the exhaustion rate must be quoted next to any TSR gap so a reader can see
how much of the gap is cost rather than capability.

## A1.3 — Attempts fixed at three per task per arm

Already required by the original document under "Attempts, noise, and what may be claimed",
and restated here because the smoke run used one attempt and therefore produced no noise
floor at all. Per-task variance across the three attempts is reported alongside every
model-dependent number (FR-007), together with `pass^3` and the per-round TSR spread that
defines the noise floor.

## A1.4 — Battery amended from 43 to 46 tasks

Three **near-miss** tasks were added as a new family, `NM`. A near-miss task is a
well-formed query whose subject demonstrably exists in the application and which
legitimately matches nothing:

- `NM.001` — which recipes require the Wok, when the Wok is one of six cooking tools the
  application defines and no recipe references it
- `NM.002` — how many recipes serve twelve or more, when servings is populated on every
  recipe and ranges from two to eight
- `NM.003` — which recipes carry both the `budget` and `celebration` tags, when each tag
  exists and is applied to eight recipes

**Why.** Finding 005 identified the null family as the most serious threat to validity in
the battery. All six null tasks are impossible because a capability or field is absent from
the application, which makes absence legible at a glance to an arm holding a closed list of
twenty tools while the baseline must prove a negative across 259 operations. Near-miss
tasks remove that shortcut: the tool exists, the field exists, the tag exists, and the only
way to answer is to actually query and find nothing. They distinguish *"I checked and there
is nothing"* from *"this capability does not exist"*, which is a distinction the original
battery could not make.

The count of genuinely impossible tasks is unchanged at six, so the impossible share falls
from 6/43 (14.0%) to 6/46 (13.0%) rather than rising. The battery was not inflated in
Arm A's favour.

`R2.010` was also re-pointed. Its check was sound, but its expected value of 47 collided
with a number the negative control's bluffing agent reached for, and it passed a task
nobody had done. It now asks for the checked-item total instead. The quarantine and its
reason are recorded in the task file itself.

## A1.5 — Whole-run ceiling for the full battery (superseded by A2.4)

$120, enforced by the runner, which halts rather than exceeds it (FR-021). Attempt rounds
are the outermost loop, so a halt leaves whole rounds complete rather than truncating a
round part-way and biasing whichever tasks happen to sort last.

---

# Amendment A2 — 2026-08-02, after the calibration pass, before any full-battery result

**Trigger**: the Phase 2 calibration pass (Arm A alone, one attempt, 46 tasks) returned a
task success rate of 44/46 (96%). The decision table above voids a run at `TSR(A) > 0.85`.
The battery was mis-calibrated and the full run did not proceed.

**Status**: permitted under FR-006. No two-arm full-battery result existed when this was
written, and **the decision table is again unchanged**. Every threshold stands as
originally written; what changed is the instrument being measured with, not the bar.

## A2.1 — The oracle now rejects unknown field names

The calibration pass exposed a defect more serious than the calibration itself. The
reference-query engine resolved a field with `row.get(field)`, so a **misspelled field name
silently matched nothing** — indistinguishable from a query that legitimately matches
nothing.

`NM.001` had been written against a field named `tools`; the oracle calls it
`cooking_tools`. The task was therefore believed to be a near-miss with an empty answer.
It is not: eight recipes require the Wok. The calibration pass marked Arm A **wrong for
giving the correct answer**, and the degeneracy screen that would have caught an
unexpectedly empty result had been waived for exactly this family of task, because
emptiness is what a near-miss task is for. The two mistakes concealed each other.

`run_query` now raises on any field not present on the source collection. Re-validating the
whole battery under the strict engine found that `NM.001` was the only affected task; the
other 45 referenced valid fields. `NM.001` was re-pointed at a genuinely empty intersection
— recipes requiring both the Wok and the Air Fryer, where eight recipes require each tool
and none require both — and its history is recorded in the task file.

## A2.2 — A composition family, `R4`, was added

The calibration diagnosis was not that the tasks were badly written but that **they were
too shallow for the tool set**. Arm A solved 33 of 46 tasks (72%) in a single tool call
plus a submission, and used exactly one distinct tool on 36 of 46 (78%). A task that one
tool call answers measures tool coverage, not agent capability, and cannot discriminate
between arms.

Ten `R4` tasks were added. Each requires joining at least two collections and doing
arithmetic across the join — the meal plan against recipe ratings, scheduled slots against
ingredient counts, shopping lists against exclusions.

**Both arms were considered when setting the difficulty, and this is the part most open to
challenge.** Tasks were deliberately *not* built on fields that only a per-recipe detail
fetch exposes, such as instruction counts, because Arm A would need sixty tool calls
against a twenty-turn budget while Arm B could do it in one `bash` loop. That would have
rigged the battery against the tool arm just as surely as the original battery flattered
it. Every `R4` task is answerable from collection-level reads that both arms can obtain
cheaply; the difficulty lies in the join and the arithmetic, which is where language models
actually fail.

## A2.3 — A fourth near-miss task

`NM.004` asks how many dinner entries are for a `batch-cook` recipe taking over an hour.
Dinner entries exist, `batch-cook` recipes exist, and recipes over an hour exist; no entry
satisfies all three. It is a near-miss reachable only by composing the join, which is a
harder shape than the three existing near-miss tasks.

## A2.4 — Battery size and the resulting ceiling

The battery is now **57 tasks**: 12 `R1`, 15 `R2`, 10 `R4`, 5 `R3`, 6 `N`, 4 `NM`, 5 `W1`.
The genuinely impossible share is 6/57 (10.5%), down from 6/43 (14.0%) at the original
freeze; the battery has not been inflated in the tool arm's favour at any point.

The Phase 3 ceiling of **$120 stands**, and the runner still halts rather than exceeding it.
With 57 tasks, two arms and three attempts the run is 342 attempts. At observed rates the
expected cost is roughly $70 to $90, so the ceiling is real but should not bind. If it does
bind, whole attempt rounds complete before any partial round begins.

## A2.5 — What re-calibration must show before Phase 3 runs

`TSR(A)` must fall inside the pre-registered band of 0.25 to 0.85, and the share of tasks
solved in a single tool call must fall materially below the 72% observed at the first
calibration. If either fails, the battery is revised again rather than run.

---

# Amendment A3 — 2026-08-02, budgets, recorded before the bias probe ran

**Authorised by**: owner decision OD-04 in `specs/001-discovery-validation/plan.md`.

**Status**: permitted under FR-006. No full-battery result exists. **The decision table is
untouched.** Success rate remains the primary metric; OD-04 explicitly rejected switching
to cost per solved task after watching success rate saturate.

## A3.1 — The tool arm's budget doubles on every axis

| Axis | Arm A before | Arm A now | Arm B before | Arm B now |
|---|---|---|---|---|
| Turns | 20 | **40** | 60 | **120** |
| Tokens | 150,000 | **300,000** | 450,000 | **900,000** |
| Spend | $0.60 | **$1.20** | $1.80 | **$3.60** |
| Wall clock | 300s | **600s** | 900s | **1800s** |

OD-04 raises the tool arm from 20 turns to 40 so that per-record tasks — ones needing a
detail fetch per recipe — become admissible. **Raising turns alone would have been
cosmetic.** The agent loop executes every tool call the model emits in a turn, so sixty
detail fetches can be issued in two or three turns; the constraint that actually binds is
the token budget, because the whole transcript is resent each turn and sixty fetched records
stay in context. A 40-turn allowance against a 150,000-token cap would still have been a
150,000-token allowance. Both axes therefore double, along with spend and wall clock, so
that the raise means what OD-04 intends it to mean.

Arm B is scaled with it to preserve the 3× ratio that amendment A1 committed to. A1's
purpose was that the baseline must never lose on headroom; letting the ratio fall to 1.5×
by holding Arm B still while doubling Arm A would quietly undo it. The exhaustion rate at
450,000 tokens has never been measured over a full battery, so there is no evidence on which
to relax the ratio, and inventing some to save money would be the exact error A1 exists to
prevent.

## A3.2 — What this knowingly trades, per OD-04

Raising the tool arm's budget **weakens the "tools are efficient" claim by construction**,
since efficiency was partly expressed as the tighter budget. That is accepted deliberately.
**Cost per solved task is now reported per arm as a secondary metric**, so the efficiency
question survives as something measured directly rather than as an artefact of asymmetric
budgets.

## A3.3 — Cost exposure this creates, stated before it is incurred

At 900,000 tokens an exhausting Arm B attempt costs roughly $2.80. A full battery of 57
tasks, two arms and three attempts is 342 attempts; if Arm B exhausts often, the $120
ceiling will bind. **The ceiling is not being raised.** The runner halts rather than
exceeding it, attempt rounds are the outermost loop so whole rounds complete before any
partial round begins, and a halt is reported as a halt. The bias probe below measures real
per-attempt cost at these budgets, and that measurement — not an estimate — decides whether
the full battery is affordable as configured.

---

# Amendment A4 — 2026-08-02, battery changes made during the bias probe

**Status**: permitted under FR-006. No full-battery result exists and none has ever been
run. **The decision table is untouched.** This records changes made to the battery while
executing the OD-04 bias probe, and records that **the rebalance authorised by OD-04 was
not executed**, because the probe met its own stop condition.

## A4.1 — Four per-record tasks added, as probe instruments

`R4.011` to `R4.014` require a detail fetch per recipe: instruction-step counts, ingredient
units, and summed ingredient quantities. OD-04 admits this task type at the raised budget,
and they were built first so the probe could measure the type actually at issue rather than
only the join-and-arithmetic tasks that already existed. They remain in the battery, frozen
and validated, so the result is reproducible.

**The battery therefore stands at 61 tasks, which is an intermediate state that no full run
should use.** It is neither the 57-task composition of battery 1.3.0 nor the rebalanced
composition OD-04 describes. The next battery decision belongs to the owner.

## A4.2 — Three prompts disambiguated

`R4.005`, `R4.006` and `R4.008` asked about "recipes on the meal plan" without saying
whether a recipe scheduled twice counts once or twice. The oracle counted distinct recipes.
Both arms read them per entry, and **Arm B's answers were exactly the per-entry values** —
3.35 where the distinct-recipe mean is 3.20, and 11 where the distinct-recipe count is 9.
The baseline was being scored wrong for a defensible reading of an ambiguous question.

`R4.007` had already been written with "Count each recipe once" and both arms passed it,
which isolates the cause. All three now carry the same disambiguation. Re-measured after the
fix, Arm B answered all three correctly and Arm A two of three.

**This is the first defect found in this harness whose direction favours the tool arm.**
Every earlier one either penalised the tool arm or was neutral. An ambiguous question scored
against the baseline manufactures a win for the product thesis, which is the most dangerous
direction an error in this experiment can take, and it would have been replicated across
every task built in the same style.

## A4.3 — The rebalance was not executed

OD-04's stop condition — the shell arm beating or matching the tool arm on the composition
family — was met. The probe result is in
[finding 009](../../findings/009-ceiling-test.md). No task was cut from `R1` or `R2`, `R4`
was not grown toward 25, and no calibration or full battery was run against a rebalanced
battery. The composition target itself is now the open question.

---

# Amendment A5 — 2026-08-02, per OD-05

Recorded **before** the tool it authorizes was written. `tools/mealie_tools.py` carried a
modification time of 15:10 when this section was appended at 17:29; the ordering is checkable
against the file's timestamps and against this repository's history.

## A5.1 — The admissibility rule for the tool surface (declared before anything is added)

**The hand-written surface may contain any tool a competent engineer would write knowing the
application domain but blind to the specific tasks in the battery.**

A tool is admissible only if its justification can be stated without naming any task. Server-side
aggregation over a recipe collection qualifies: it is the scalar-returning counterpart to a
row-returning search, and every data-backed application client acquires one. A tool shaped like
`count_distinct_recipes_in_breakfast_slots` is inadmissible, and so is any tool whose reason for
existing is a task it is known to solve.

Three consequences bind:

1. **A tool's parameter vocabulary is subject to the same rule as the tool.** Adding a filter,
   field, or operator because a task needs it is inadmissible even inside an admissible tool. The
   permitted move is to enumerate a category completely — *every scalar property of a recipe* — and
   accept whatever coverage falls out.
2. **One addition is authorized, not a class of them.** If a second or third tool starts to look
   necessary, the work stops and reports rather than adding it.
3. **Coverage gaps are results, not defects.** If the admissible tool fails to reach a task, that is
   reported as a limit of aggregation-as-a-tool. It is not grounds for extending the tool.

## A5.2 — Why a treatment change is admissible here at all

Changing a treatment to chase a result on a fixed design is p-hacking. Updating a treatment after
the *design* changed underneath it is repairing the manipulation. This is the second case, and the
distinction rests on a fact checkable against artifact history rather than on anyone's judgment:

**The per-record family did not exist when the tool set was frozen.** The twenty tools were written
at 15:10 on 2026-08-02. The `R4` composition family was created between 15:48 and 16:07, and the
four per-record tasks `R4.011`–`R4.014` were created at approximately 16:49, under
[OD-04](../../plan.md). The treatment was therefore never designed for the tasks it is losing,
because those tasks postdate it by an owner decision.

The weaker justification — *aggregation is obviously part of an ideal surface and its absence was
an oversight* — is available to anyone rescuing any result and is **not** what authorizes this.

## A5.3 — The v1 surface is preserved, not superseded

The twenty-tool surface remains a scored arm. Both surfaces are reported side by side, and the v1
per-record result stands on its own evidence: *these twenty hand-written tools push aggregation
through the context window and lose to a `jq` pipeline.* If the aggregation-equipped surface wins
the limb, the claim that may be made is **tools that return answers help; tools that return records
do not** — a constraint on tool synthesis, not a win for the product thesis.

## A5.4 — E7 reports per family, not as a single verdict

The OD-04 probe measured the tool arm at 2.8× cheaper per solved join task and 12× more expensive
per solved per-record task. One aggregate score averages those into a number describing nothing.

> **Correction of the cited figure, 2026-08-03. The amendment's text above is left as written,
> because a pre-registration records what was committed to and when; only the figure it cites is
> corrected here.** The join ratio of 2.8× divided a post-fix cost total by a *pre-fix* solved
> count of 8 and 7, while the success counts quoted everywhere else are the post-fix 9 and 10. On
> the post-fix basis the tool arm spent $1.5444 over 9 solved and the baseline $3.7687 over 10
> solved — **$0.1716 against $0.3769, or 2.20×**. See
> [finding 009](../../findings/009-ceiling-test.md) §Limb 1. **A5.4's rationale is unaffected and
> is if anything stronger**: the argument for per-family reporting is that the two ratios point in
> opposite directions, and 2.20× against 12× spans a wider interval than 2.8× against 12× did.
**Every E7 result is reported per family**, and the decision table's thresholds are read per family
rather than against a pooled score.

This obliges scoring the shell baseline on `R1` and `R2` — 27 lookup tasks, never run against the
baseline, and the region most favourable to the product thesis, since the baseline must locate the
right endpoint among 259 operations while the tool arm sees twenty named ones. Reporting E7 without
it would be as one-sided as the composition family was in the opposite direction.

## A5.5 — Cost priced before it is spent

From 27 scored Arm B attempts, observed cost is $0.047/task on `R1` and $0.113/task on `R2`, against
an all-family mean of $0.299. Scoring 12 `R1` and 15 `R2` tasks at one attempt each projects to
**≈$2.30**, and **≈$6–8** under a conservative assumption that the raised 900k-token budget invites
more exploration than the smoke-run tasks did. The aggregation re-probe adds ≈$3–4. Both limbs are
priced at **≈$10, against the ~$25 authorized.**

## A5.6 — What remains unchanged

The decision table is untouched. Thresholds are not revised. The 0.25–0.85 calibration band stands,
a third failed calibration escalates to the owner rather than to another iteration, and the 61-task
intermediate battery may not be used for any full run.

## A5.7 — The tool as built (recorded after A5.1, before it was scored)

`aggregate_recipes` computes one statistic over a filtered recipe set and returns only the
statistic. Its filters are **the same function** `search_recipes` uses — the two share `_select`,
so the aggregation tool cannot have selectivity the search tool lacked. It adds `metric` ∈
{count, sum, mean, min, max, argmax, argmin} and `field` drawn from a complete enumeration of the
eleven scalars a single recipe yields.

Surface **v1** (twenty tools, frozen 15:10) remains runnable via `--tool-surface v1`. The tool
surface is folded into the harness fingerprint, so v1 and v2 results cannot be pooled by accident.

Two of the four per-record tasks are unreachable under this tool, because reaching them requires
a threshold filter on a derived field and a filter on ingredient units. Neither was added: the
only available justification for either is a task that needs it, which A5.1 forbids. Recorded
here **before** the re-probe was scored.
