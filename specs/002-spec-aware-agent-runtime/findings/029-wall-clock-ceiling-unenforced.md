# Finding 029 — FR-005's wall-clock ceiling does not fire, measured against three controls that do; and the claim commissioning this pass **breaks at its conclusion** — the constitutional wall-time term is *supplied* by FR-005 and *unmet* by the runtime, which is a different defect with a different owner from the "unsupplied" one alleged. The sharpest reading is the one nobody predicted: the ceiling is reachable **only by crashing**, on a figure nobody measured

**Date**: 2026-08-05
**Feature**: 002. Measures whether the wall-clock dimension of FR-005's four per-session ceilings
terminates a session, against [`src/runtime/loop.py`](../../../src/runtime/loop.py),
[`src/runtime/ledger.py`](../../../src/runtime/ledger.py) and
[`src/runtime/session_store.py`](../../../src/runtime/session_store.py) as they stand in the working
tree. **Reports; decides nothing.**
**User Story**: US1, by way of FR-005, FR-049 and constitution Principle IV bullet 1.
**Owner decision**: **none is minted here and the register was not edited.** Two questions below need
an owner and are stated as questions with no number attached, on
[finding 026](./026-pivot-root-check-measured.md)'s rule that a number copied into a finding goes
stale in the direction that tells the next author to reuse a taken one. Owed edits to
[`plan.md`](../../001-discovery-validation/plan.md) and [`tasks.md`](../tasks.md) are **quoted** in
[§7](#7-owed-edits-to-the-register-and-to-tasksmd-quoted-not-made) rather than made.
**Model spend**: **$0.0000.** No model was called and no credential was read. Nine local process runs
totalling under twenty seconds of wall clock.
**Method**: **planted cases, not source reading.** The central question — *does the ceiling fire* —
is a claim about behaviour, and [`tools/README.md`](../../../tools/README.md)'s rule *"reading an
instrument is not measuring it — plant the case instead"* names two occasions on 2026-08-05 when a
defect asserted from source did not exist. So a real `AgentLoop` was run against a real store with a
tool that sleeps, under a wall-clock ceiling three orders of magnitude below the session's own
duration, and what it terminated on was read from the loop's own outcome. **Three controls make the
same harness fire on `turns`, `tokens` and `spend`**, and a fourth control makes it fire on
`wall_clock_seconds` itself, so a non-firing arm is a fact about the dimension rather than about the
probe. Source was read only to build the probe and to name the writers in
[§4](#4-what-writes-the-dimension-one-site-and-it-is-an-estimate).
**Reproduction**: [`tools/wall_clock_ceiling_probe.py`](../../../tools/wall_clock_ceiling_probe.py),
committed with this finding, plus one two-attempt sequence over the existing committed fixture
[`tests/fixtures/resume_session.py`](../../../tests/fixtures/resume_session.py). Both command lines
are given in full below.
**Numbering note**: `028` was the high-water mark across `specs/*/findings/`, established by listing
the whole tree rather than by reading a number out of a document or out of the brief that
commissioned this pass, and `029` was free at that moment and re-checked free immediately before
saving.

---

> ## THE CLAIM UNDER TEST BROKE. Every link survived and the conclusion did not, and the difference decides who owns the repair
>
> The claim, as commissioned:
>
> > *"The runtime cannot enforce FR-005's wall-clock ceiling, and because Principle IV bullet 1's
> > wall-time term is supplied by nothing else, that constitutional term is currently unsupplied."*
>
> **First half: SURVIVES, and is now measured rather than derived.** A session that ran for
> **2.044 seconds** under a ceiling of **0.001 seconds** ended `terminated.completed`.
>
> **Second half: FALSE, in the register's own vocabulary.** "Supplies" is the relation between a
> constitutional term and a **requirement**, and it is the word
> [`spec.md`](../spec.md):759–765 itself uses: *"Constitution Principle IV bullet 1 requires a sandbox
> capped on CPU, memory and wall-time, and **this requirement supplies the wall-time term only**."*
> **FR-005 stands in that relation.** The term is supplied. What is missing is not a requirement but
> the enforcement the requirement already mandates.
>
> **Why this is not a quibble about a word.** The two readings have different owners, different
> repairs and different costs:
>
> | if the term were… | the defect is | the repair is | who owns it |
> |---|---|---|---|
> | **unsupplied** *(alleged)* | a specification gap — no requirement carries the term | author a requirement, or amend the constitution | the owner, as an authoring act |
> | **supplied and unmet** *(measured)* | an implementation gap against an existing `MUST` | measure elapsed time and reconcile it | a task, under the requirement that already exists |
>
> **And the alleged state is one option away from being created.** Option (b) in
> [§6](#6-the-three-options-and-what-each-actually-costs) — narrow FR-005 to declare the dimension
> reserved-only — would remove the only requirement supplying the term and **manufacture the
> constitutional vacancy this claim wrongly asserts already exists.** That is the strongest argument
> against option (b), and it is only visible once the claim is corrected.

> ## AND A SECOND RESULT, WHICH NOBODY PREDICTED AND WHICH IS WORSE THAN THE ONE COMMISSIONED
>
> The ceiling is not merely inert. **It is reachable, by exactly one route: crashing.**
>
> A clean session cannot reach it at any duration — measured at 2.044 s against 0.001 s, and again
> with an estimate of **10⁹ seconds** per turn against the same ceiling, which also completed. A
> session that crashes once inside a model call leaves an unreleased reservation on the dimension,
> and the **resumed** attempt terminates on it immediately:
>
> ```
> DONE {"terminal_state": "terminated.wall_clock_ceiling_reached", "turns": [], "model_calls": 0,
>       "spend_usd": 0.01, "tokens": 3, "wall_clock_seconds": 5.0, "turn_total": 1}
> ```
>
> `"wall_clock_seconds": 5.0` is the **configured estimate of a call that never returned**. Nothing
> timed anything. `"model_calls": 0` and `"turns": []` — the resumed attempt did no work at all.
>
> So the dimension's behaviour is the **inverse** of a ceiling: a session that runs unboundedly long
> without failing is never stopped, and a session that fails early is stopped by a number that
> measures nothing. Under-binding in the one direction a ceiling exists to prevent, and over-binding
> in the direction that destroys work.

---

## 1. The planted case and its four controls

`.venv/bin/python tools/wall_clock_ceiling_probe.py`, macOS, working tree at the revision this
finding is committed in. Each arm builds a fresh `AgentLoop` over a fresh store with a tool that
calls `time.sleep(0.4)`, makes one dimension absurd and leaves the other three loose.

| arm | ceiling on the dimension | measured elapsed | terminal state | fired? |
|---|---:|---:|---|---|
| **wall-clock-tight** | `0.001` s | **2.044 s** | `terminated.completed` | **NO** |
| **wall-clock-tight-with-reservation** | `0.001` s, estimate `0.5` s/turn | 2.038 s | `terminated.completed` | **NO** |
| **wall-clock-absurd-reservation** | `0.001` s, estimate **`1e9`** s/turn | 2.042 s | `terminated.completed` | **NO** |
| **wall-clock-zero-ceiling** *(control on the comparison)* | `0.0` s | 0.001 s | **`terminated.wall_clock_ceiling_reached`** | **yes** |
| **turns-tight** *(control)* | `2` turns | 0.818 s | **`terminated.turn_ceiling_reached`** | **yes** |
| **tokens-tight** *(control)* | `8` tokens | 0.834 s | **`terminated.token_ceiling_reached`** | **yes** |
| **spend-tight** *(control)* | `$0.05` | 0.825 s | **`terminated.spend_ceiling_reached`** | **yes** |

Verbatim, the arm the claim is about and the arm that proves the harness can fire on this dimension:

```json
{
  "arm": "wall-clock-tight",
  "why": "the session sleeps for seconds under a ceiling of one millisecond",
  "ceiling_wall_clock_seconds": 0.001,
  "ceiling_turns": 500,
  "ceiling_tokens": 10000000,
  "ceiling_spend_usd": 1000.0,
  "reserved_wall_clock_per_turn": 0.0,
  "measured_elapsed_seconds": 2.044,
  "tool_calls_that_slept": 5,
  "terminal_state": "terminated.completed",
  "expected_terminal_state": "terminated.wall_clock_ceiling_reached",
  "fired_as_expected": false,
  "ledger_total_wall_clock_seconds": 0.0,
  "ledger_committed_wall_clock_seconds": 0.0,
  "ledger_total_turns": 6,
  "ledger_total_tokens": 42,
  "ledger_total_spend_usd": 0.18
}
{
  "arm": "wall-clock-zero-ceiling",
  "why": "CONTROL ON THE COMPARISON — `evaluate_ceilings` is `>=`, so a total of 0.0 trips a ceiling of 0.0. If this fires, the comparison is wired to the dimension and it is the numerator that is dead, not the check",
  "ceiling_wall_clock_seconds": 0.0,
  "ceiling_turns": 500,
  "ceiling_tokens": 10000000,
  "ceiling_spend_usd": 1000.0,
  "reserved_wall_clock_per_turn": 0.0,
  "measured_elapsed_seconds": 0.001,
  "tool_calls_that_slept": 0,
  "terminal_state": "terminated.wall_clock_ceiling_reached",
  "expected_terminal_state": "terminated.wall_clock_ceiling_reached",
  "fired_as_expected": true,
  "ledger_total_wall_clock_seconds": 0,
  "ledger_committed_wall_clock_seconds": 0,
  "ledger_total_turns": 0,
  "ledger_total_tokens": 0,
  "ledger_total_spend_usd": 0
}
```

### What each control licenses, and why three were not enough

**The three consumption controls license "the harness can terminate a session".** Same probe, same
sleeping tool, same store, one variable moved. A run in which nothing fires proves nothing, and these
are what make the wall-clock arms readable as a fact about the dimension.

**The fourth control is the one that makes the finding precise, and it was added after the first
three.** Without it, three explanations survive the null result and only one of them is the defect:
the ceiling is never compared; the dimension is not wired to a terminal state; or the comparison and
the wiring are fine and the **numerator** is dead. `wall-clock-zero-ceiling` separates them — with
`evaluate_ceilings` at `>=`, a total of `0.0` trips a ceiling of `0.0`, and it does, in **1
millisecond**, before any tool ran. So the comparison runs, the dimension is wired, the terminal
state exists and is reachable. **What is missing is a measurement, and nothing else.** That is a
materially narrower defect than "the ceiling is not implemented", and it changes the repair from a
mechanism to a number.

**The `1e9` arm closes the last cheap explanation.** A reservation of one billion seconds against a
ceiling of one millisecond cannot be too small to notice. The reservation channel is not
under-sized; it is **not present at the moment ceilings are evaluated** in a session that does not
crash, because a reservation is released on reconcile and the ceiling is read between turns.

## 2. The crash arm — the only route to the ceiling, measured over the committed fixture

Run over [`tests/fixtures/resume_session.py`](../../../tests/fixtures/resume_session.py) **unmodified**,
so the mechanism is the shipped one and not one this finding built:

```bash
ROOT=$(mktemp -d)
ARGS="--root $ROOT --turns 400 --tools 1 --reserve-wall-clock 5.0 \
      --ceiling-spend 1000.0 --ceiling-tokens 10000000 \
      --ceiling-seconds 1.0 --ceiling-turns 500"
# attempt 1 — crash inside the model call, leaving a 5.0 s reservation outstanding
.venv/bin/python tests/fixtures/resume_session.py $ARGS --pause model:0 &
sleep 3; kill -KILL $!          # child exit: 137
# attempt 2 — resume and run to completion
.venv/bin/python tests/fixtures/resume_session.py $ARGS --pause none
```

Verbatim output of attempt 2:

```
DONE {"terminal_state": "terminated.wall_clock_ceiling_reached", "turns": [], "model_calls": 0, "spend_usd": 0.01, "tokens": 3, "wall_clock_seconds": 5.0, "turn_total": 1}
```

**Read this beside arm 1 of §1 and the shape is the whole finding.** Two sessions; one ran for
seconds under a millisecond ceiling and completed, the other did nothing at all under a
one-**second** ceiling and was terminated. The difference between them is not duration. It is
whether a crash happened to leave an estimate on the ledger.

This is consistent with, and sharpens,
[`tests/batteries/test_ceilings_under_resume.py`](../../../tests/batteries/test_ceilings_under_resume.py)'s
wall-clock arm, which measured the orphaned reservation moving the total and asserted that the
session did **not** end on the wall-clock ceiling. That arm crashes and does not resume past the
crash on this dimension; the sequence above resumes, and the resume is where the ceiling fires.

## 3. Link by link — every one survives, which is why the conclusion had to be checked separately

| link | as stated in the brief | verdict | evidence |
|---|---|---|---|
| **1** | [`spec.md`](../spec.md):747 — FR-005 requires ceilings on *"spend, token consumption, wall-clock time and turns"* | **HOLDS** | verbatim at that line |
| **2** | [`spec.md`](../spec.md):2380–2383 — Principle IV bullet 1 governs FR-005's wall-clock term; *"FR-049 supplies the first two"* | **HOLDS**, and is *stronger* than the brief realised | see below |
| **3** | nothing measures elapsed time; the only figure reaching the dimension is the reservation estimate | **HOLDS**, and is now measured rather than read | §1, §2, §4 |
| **conclusion** | *"that constitutional term is currently unsupplied"* | **FALSE** | FR-005 supplies it — [`spec.md`](../spec.md):762 in terms |

**Link 2 checked against the artifacts rather than taken.** The constitution
([`.specify/memory/constitution.md`](../../../.specify/memory/constitution.md):308) requires
*"Filesystem scoped, CPU/memory/wall-time capped"*. FR-005's reading of "the first two" is **correct**:
[`spec.md`](../spec.md):1037 gives FR-049 as *"a declared bound on processor time and a declared bound
on memory"* — CPU and memory, in that order.

**And FR-049 could not stand in for the wall-time term even if it were read generously, which is a
point in the brief's favour that the brief did not make.** `processor time` is CPU time.
[`src/supervisor/bounds.py`](../../../src/supervisor/bounds.py) implements it as `cpu_max` (a rate
quota) and `cpu_total_seconds` (cumulative CPU-seconds), plus `memory_max_bytes` and a `pids_max`
the module itself marks as *"beyond what FR-049 requires"*. **A session sleeping in a tool call
consumes no CPU seconds at all** — which is precisely the shape of arm 1, where 2.044 seconds of
wall clock passed inside `time.sleep`. So the two bounds are not merely a different pair of terms;
they are bounds the arm that broke this ceiling would also not have tripped.

### The candidates for "something else bounds wall time", each checked and each rejected

| candidate | checked | bounds wall time? |
|---|---|---|
| **FR-049 / `src/supervisor/bounds.py`** | full text and the module's four controls | **No** — CPU-seconds, a CPU rate, memory, pids |
| **`src/runtime/runner.py`** | every `class`/`def`; no `timeout`, `deadline` or `elapsed` symbol | **No** — it has a caller-driven `CancelToken`, which is cancellation, not a deadline |
| **`src/supervisor/lease.py`** | full file | **No** — the lease *renews* while the session is `RUNNING`; it revokes on a crash, never on duration |
| **`src/supervisor/listener.py`, `seccomp.py`** | the only other `timeout=` sites | **No** — a socket connect timeout and a thread join |
| **FR-006's stall threshold** | [`spec.md`](../spec.md):940–979 | **No** — a predicate over *consecutive turns*; a turn that makes progress resets it, so it bounds no duration |
| **FR-047's staleness ceiling** | [`spec.md`](../spec.md):1596–1606 | **No** — it is wall-clock, and its subject is the age of the served-operation set. It terminates in-flight sessions only when *that* set goes stale, which is unrelated to how long a session has run |
| **Config keys** | every `_SECONDS`, `_TIMEOUT`, `_DEADLINE` key in [`src/contracts/config.py`](../../../src/contracts/config.py) | **No** — the four `SESSION_CEILING_*`, FR-049's three `SANDBOX_*`, and three interval/staleness keys belonging to FR-050, FR-047 and FR-028 |
| **FR-049 acquiring a wall-time term after 2026-08-03** | `git log -S FR-049` on `spec.md`, and the full text as it stands | **No** — two commits touched FR-049 on 2026-08-04; neither added a time term. No occurrence of "wall" in FR-049 at any point |

**So `spec.md`:2382 is not stale.** The brief flagged it as possibly overtaken since 2026-08-03. It
was checked and it is current.

## 4. What writes the dimension: one site, and it is an estimate

Every assignment to `wall_clock_seconds` in `src/`, and what each is:

| site | what it is |
|---|---|
| [`ledger.py`](../../../src/runtime/ledger.py):175 | `float(self.policy.wall_clock_seconds)` — **the only non-zero source in the codebase**, and it is the reservation estimate |
| [`loop.py`](../../../src/runtime/loop.py):321, :565 | `wall_clock_seconds=0.0`, twice — the reconcile paths |
| `ledger.py`:214, :235, :276 · `trace_budget.py`:154 · `session_store.py`:138, :297 | carry, sum or read back whatever the two above produced |

**And the estimate's own default is zero.** `ReservationPolicy.wall_clock_seconds` defaults to `0.0`
([`ledger.py`](../../../src/runtime/ledger.py):84), so a deployment that does not set it explicitly
writes **literally nothing** to the dimension on any path — the ledger's committed total, its held
total and its reconciled total are all identically zero for the life of the session. The `0.0` in
every arm of §1's `ledger_total_wall_clock_seconds` column is that.

### Is a reserved estimate, never reconciled, "enforcement" under FR-005's `MUST`?

Argued both ways, because the brief asked for a conclusion and the conclusion should be visible as a
choice.

**For — the case that it is enforcement.** The figure is an operator's declared value, it is durable,
it survives a crash, it accrues against the same ceiling after a resume, and FR-005 nowhere says the
counted quantity must be *measured* rather than *declared*. Every other bound in this system is a
declared number.

**Against, and this is the conclusion.** Three reasons, in the order they bind:

1. **It is not a bound on the thing the requirement names.** FR-005's dimension is *wall-clock time*,
   which is a property of the world. A per-turn constant is a property of a config file. The two
   quantities can differ without limit, and §1 measured them differing by a factor of ∞ — 2.044
   seconds elapsed against 0.0 accrued.
2. **The direction of error is the fatal one, and it is unbounded on the side that costs money.** A
   ceiling that under-binds fails open. Where the estimate is systematically low the ceiling permits
   more real time than it names; where the estimate is `0.0` — the shipped default — it permits
   **infinite** real time. There is no configuration of the estimate that makes the ceiling bind a
   long session, because §1's `1e9` arm shows the reservation is not present at the moment ceilings
   are evaluated at all.
3. **The one case where it *does* fire is the case where it should not.** §2: a resumed session
   terminated on a figure describing a call that never returned. So the mechanism is not a weak
   version of the right thing; it is a different thing that fires on failure rather than on
   duration.

**Conclusion: no.** A reserved estimate that is never reconciled against elapsed time does not
enforce FR-005's wall-clock ceiling. FR-005's `MUST` is unmet on this dimension.

## 5. `ReservationPolicy`'s missing defaults — the refusal is right, and it rests on precedent

Recorded so that **T062**, the per-provider cost table, does not invent one.

**The measured state**, not read from the class but exercised:

```python
>>> ReservationPolicy()
TypeError: ReservationPolicy.__init__() missing 2 required positional arguments: 'spend_usd' and 'tokens'
>>> ReservationPolicy(spend_usd=0.01)
TypeError: ReservationPolicy.__init__() missing 1 required positional argument: 'tokens'
>>> ReservationPolicy(spend_usd=0.01, tokens=3)
ReservationPolicy(spend_usd=0.01, tokens=3, wall_clock_seconds=0.0, turns=1)
```

**The ruling: keep the refusal, and it does not need an owner decision.** But the ground is
**precedent, not governing text**, and that is stated plainly because a precedent argument dressed as
a requirement is the failure mode this corpus keeps recording.

| instrument | what it forbids a default for | does it govern `ReservationPolicy`? |
|---|---|---|
| **FR-005** ([`spec.md`](../spec.md):749–752) | a **ceiling** — *"MUST NOT be treated as unbounded or filled from a default this specification invented"* | **No.** A reservation is an estimate, not a ceiling |
| **FR-058 / OD-25** | the **output bound** | **No.** Different subject |
| **Q-10** (plan) | the treatment both of the above take | **No.** It is a treatment, not a scope |

`ReservationPolicy` is a **third instance of the same shape** — a number with no evidence base, whose
invention would be silently wrong in the under-counting direction — and the class's own docstring
already gives that as its reason. Nothing literally governs it. The refusal is nonetheless correct
and should stand, on the strength of the pattern rather than on a citation.

**Two observations that complicate the tidy version, both recorded rather than smoothed:**

- **The class is not uniform.** `wall_clock_seconds` and `turns` **do** carry defaults (`0.0` and
  `1`). `turns` is defensible and the docstring defends it — a call being made is exactly one turn,
  which is a measurement rather than an estimate. **`wall_clock_seconds = 0.0` is not defended
  anywhere**, and §4 shows it is the reason the shipped default writes nothing at all to the
  dimension. Whether that default is the identity element or an invented number is a real question
  and this finding does not settle it.
- **The refusal is Python's, not the module's.** `spend_usd` and `tokens` are refused by the
  dataclass as missing positional arguments, with no named error, while every *other* refusal in the
  class raises `LedgerError` with a sentence explaining the reason. A caller who forgets one gets a
  `TypeError`, not the argument. That is a smaller defect than a default would be, and it is not the
  same as the fail-loudly-naming-what-is-missing discipline FR-005 requires of ceilings.

## 6. The three options, and what each actually costs

Stated because the claim's first half survived. **The owner decides; this is not a recommendation.**

**(a) Measure elapsed wall clock in the loop and reconcile it.** The mechanism is already in place —
§1's fourth control proves the comparison, the wiring and the terminal state all work, so the change
is a numerator. **The cost is a specification question it forces open, and the question is real:
does the dead interval between a crash and its resume count against the ceiling?** FR-005 says *"a
crash MUST NOT reduce the total counted against any of the four ceilings"*, which settles the
direction for consumption but not for elapsed time — a session crashed at 09:00 and resumed at 17:00
has consumed eight hours of the world and zero hours of anything. Both answers are defensible and
they differ by orders of magnitude on exactly the deployments that crash.

**(b) Declare the dimension reserved-only and narrow FR-005.** **This is a constitution question and
not merely a spec edit**, and the reason is sharper than the brief stated it. FR-005 is not merely
*the only requirement supplying a constitutional term* — per the correction at the head of this
document, narrowing it **creates the vacancy** the commissioning claim wrongly believed already
existed. The constitution would then require a wall-time cap that no requirement supplies. That is a
strictly worse state than today, where the requirement exists and one task is owed against it.

**(c) Leave the registered vacuous invariant standing until a later task owns it.** **Checked, and a
task does own it — partly.** [`tasks.md`](../tasks.md) **T064** is unstarted and reads *"Budget
channel enforcing all four of FR-005's ceilings from session state rather than from a per-attempt
context"*. So option (c) has a landing site rather than being an indefinite deferral. **But T064's
text does not name the missing thing.** Its subject is *where the counter lives* — finding 006's
3-permitting-6 defect — which T053 and T055 already discharged on three dimensions. It says nothing
about *measuring* elapsed time, which is the whole of what is missing. An implementer taking T064
from its text would satisfy it without closing this gap. The owed edit is quoted in §7.

## 7. Owed edits to the register and to `tasks.md`, quoted, not made

Neither file was edited. Both edits are the owner's.

**One formatting note, because it would otherwise read as a mistake.** The link to this finding
inside each quoted block is written **inside a code span** and carries the path that is correct
**from the destination file**, not from here. `link-target` resolves every live link relative to the
document it appears in, so a live link written for `tasks.md` is a hard error when it sits in a
finding — the same escape, and the same reason, as
[finding 026](./026-pivot-root-check-measured.md)'s treatment of an unminted owner-decision number.
Strip the backticks when the text is pasted into its destination.

**To [`tasks.md`](../tasks.md), T064** — the text as it stands:

> - [ ] T064 Budget channel enforcing all four of FR-005's ceilings from **session state** rather than from a per-attempt context, in `src/runtime/budget.py` (FR-005, **U-30**)

The text that would carry this finding, appended as a note beneath it rather than replacing the line:

> **Extended 2026-08-05 by `[finding 029](./findings/029-wall-clock-ceiling-unenforced.md)` — extended, not narrowed, and the extension is the part nobody would derive from the line above.** This task's stated subject is *where the counter lives*, which T053 and T055 discharged on `spend_usd`, `tokens` and `turns`. **The fourth dimension has a different defect and this line does not name it: nothing measures elapsed wall clock at all.** Finding 029 measured a session run for 2.044 s under a ceiling of 0.001 s ending `terminated.completed`, against three controls on the same harness that fired, and a fourth control that fires the wall-clock ceiling itself at a ceiling of `0.0` — so the comparison, the wiring and `terminated.wall_clock_ceiling_reached` all work and **the numerator is what is absent**. An implementer satisfying this line as written would close nothing on this dimension. The task is not complete until a session's elapsed wall clock is measured and reconciled, **and the specification question that forces is not this task's to settle**: whether the dead interval between a crash and its resume counts against the ceiling. Finding 029 §6(a).

**To [`plan.md`](../../001-discovery-validation/plan.md), the U-30 area of
[`14`](../../../research/14-architecture-synthesis.md) §5.1** — no strike, an annotation, because U-30's
subject is the **spend** ceiling and nothing measured here touches it:

> **Annotated 2026-08-05 by `[finding 029](../002-spec-aware-agent-runtime/findings/029-wall-clock-ceiling-unenforced.md)`.** U-30 records that no layer of the stack has been shown to enforce a **spend** ceiling surviving a crash and resume. That entry is unchanged and its subject is untouched. What is now measured is the sibling case on FR-005's fourth dimension, and it is worse in kind rather than in degree: the **wall-clock** ceiling does not fire at all in a clean session, at any duration, and fires **only** on a resume following a crash that orphaned a reservation — on a figure that is a configured estimate of a call that never returned. Recorded here because U-30's remedy line — *"build our own ceiling regardless… it must be denominated in cost, and it must survive a crash"* — is satisfied on spend by T053 and T055 and is **not** satisfied on wall clock, and a reader arriving at U-30 would reasonably conclude otherwise from the fact that the ceiling battery is green.

## 8. What this asks the owner to decide

Two questions, no numbers attached.

1. **Does the interval between a crash and its resume count against FR-005's wall-clock ceiling?**
   This must be answered before option (a) can be implemented, and it cannot be answered by a task —
   FR-005's crash clause settles the direction for consumption and is silent for elapsed time. The
   answer changes the ceiling's meaning by orders of magnitude on any deployment that crashes.
2. **Is the current state acceptable until T064?** Today a session with a wall-clock ceiling
   configured is unbounded in wall clock, and the four gates are green while it is. A deployment
   reading `SESSION_CEILING_WALL_CLOCK_SECONDS=900` in its configuration is being told something that
   is not true of the runtime.

## 9. An open, unexplained, non-reproducing observation — the `BROKEN` classification

Recorded because it happened, not because it is understood.

A `BROKEN` verdict appeared once in
[`tests/removal_proofs.sh`](../../../tests/removal_proofs.sh) and did not reproduce on three
subsequent full runs. The branch at line 303 — *"the tamper broke collection rather than the
mechanism"* — now prints the `ERROR`/`INTERNALERROR` lines that produced the verdict, and the
comment beside it records why: with the output discarded there was no way to tell a genuinely
unparseable tamper from an environment flake, and those want opposite responses. That improvement is
already in the tree.

**Nothing here claims it is fixed, and no reproduction was attempted in this pass.** The diagnostics
change makes the *next* occurrence readable; it does not explain the one that happened. Status:
**open, unexplained, one occurrence, zero reproductions in three subsequent full runs.**

## 10. What this does **not** establish

- **It does not establish that anything is wrong with the three other ceilings.** All three fired,
  under three separate controls, and T053/T055 already carry them across crashes.
- **It does not establish how wall clock *should* be measured.** Session elapsed time including
  idle, or the sum of the model calls, are different quantities and this finding picks neither.
  [`tests/batteries/test_ceilings_under_resume.py`](../../../tests/batteries/test_ceilings_under_resume.py)'s
  docstring already records that as an owner's decision, and nothing here changes that.
- **It does not establish that a crash-orphaned reservation firing the ceiling is a defect** rather
  than a deliberate conservative choice. It establishes that it is the *only* path to the terminal
  state, which is a fact about coverage rather than a verdict on the design.
- **It does not establish anything about FR-049's bounds being enforced.** FR-049 was checked only
  for whether it carries a wall-time term. It does not. Whether its CPU and memory bounds work is
  `tests/batteries/test_bounds_exhaustion.py`'s subject and is not touched here.
- **It does not establish the behaviour under a real provider.** Every arm uses a fake model
  returning fixed figures. A real provider's latency would make the elapsed/accrued gap larger, not
  smaller, so the direction is safe — but the figures here are the probe's.
- **It does not establish anything on Linux.** Every arm ran on macOS. The dimension is a
  Python-level accrual with no kernel involvement, so no arm here has a platform dependency, but no
  arm was run under the container the supervisor targets.
- **It does not settle whether `ReservationPolicy.wall_clock_seconds = 0.0` is an invented default.**
  §5 raises it and leaves it open.

## 11. Errors in the brief that commissioned this pass

Listed explicitly, because the reasoning was supplied to be falsified and most of it survived.

- **Wrong, and it is the conclusion.** *"That constitutional term is currently unsupplied."* FR-005
  supplies it; `spec.md`:762 says so in the same word. The measured defect is enforcement, not
  supply. See the banner at the head of this document, including the consequence for option (b).
- **Wrong on a code fact.** *"The ceiling dimension is named `n_seconds` in code, not `wall_clock`."*
  There is **no** `n_seconds` symbol anywhere in the repository —
  `rg '\bn_seconds\b'` returns nothing. The dimension is named `wall_clock_seconds` at every site:
  the `Ceilings` field, the `ReservationPolicy` field, the ledger column, the trace field,
  `CEILING_ORDER`, and the config key `SESSION_CEILING_WALL_CLOCK_SECONDS`. The nearest thing is the
  fixture's CLI flag `--ceiling-seconds`, which is an abbreviation in one argument parser.
- **Understated, in the brief's own favour.** *"FR-049 supplies the first two."* True, and the brief
  did not notice that FR-049's first term is **processor** time — CPU-seconds and a CPU rate — which
  a sleeping session does not consume. So FR-049 is not merely the wrong pair of terms; it would not
  have caught arm 1 either.
- **Incomplete on option (c).** *"Leave the registered vacuous invariant standing until a later task
  owns it"* reads as an open-ended deferral. **T064 already owns it**, is unstarted, and is
  mis-scoped for it — which makes (c) cheaper than it sounded and more dangerous, since T064 can be
  completed as written without closing this.
- **Right about the reservation channel being the only writer, and understating how little it
  does.** The brief suspected the estimate might constitute enforcement. Measured: it is not present
  at the moment ceilings are evaluated in any session that does not crash, so even an estimate of
  10⁹ seconds against a ceiling of 10⁻³ does not fire it.
- **Correct and confirmed:** links 1, 2 and 3; that `spec.md`:2382 is not stale; that FR-049
  acquired no wall-time term after 2026-08-03; that `ReservationPolicy` refuses an unset `spend_usd`
  and `tokens`; that the ruling on it rests on precedent rather than on governing text.
