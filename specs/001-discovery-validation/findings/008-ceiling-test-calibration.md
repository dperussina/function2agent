# Finding 008 — E7 remediation and calibration: the battery is still not ready

**Date**: 2026-08-02
**User Story**: 1 (does a curated tool surface beat a capable general agent?)
**Model spend**: $4.80 this session, $7.59 across both sessions. **The $120 authorised for
the full battery was not spent and the full battery did not run.**

> **Basis note added 2026-08-03.** Summed directly from the committed per-attempt and
> negative-control rows in `results/`, the two-session figure is **$7.5123 → $7.51**, so the $7.59
> reported here runs about eight cents high. The excess is consistent with roughly $0.05 of
> negative-control spend that was incurred but never committed to `results/`, plus rounding. **$7.51
> is the artifact-verifiable floor; $7.59 is spend actually incurred**, and it is the figure the
> downstream $18.15 and $24.73 totals inherit. See
> [finding 009](009-ceiling-test.md)'s spend correction. No calibration verdict depends on this.
**Method**: five pre-agreed remediations to the E7 harness, then a Phase 2 calibration pass
of the tool-equipped arm alone over the whole battery, then a battery revision, then a
second calibration pass. Every task outcome decided programmatically against the
application's observable state; no model judged any result.

The harness is at [`harness/ceiling-test/`](../harness/ceiling-test/) and is described in
[Finding 005](005-ceiling-test-harness.md). Thresholds are in
[`PREREGISTRATION.md`](../harness/ceiling-test/PREREGISTRATION.md), now carrying two dated
amendments.

---

## The headline

**Phase 2 did not clear, twice, and I did not run Phase 3.**

The calibration pass put the tool-equipped arm at 44 of 46 tasks (96%). The pre-registered
decision table voids a run when that arm exceeds 85%, because a ceiling leaves nothing to
measure. I rebuilt a third of the battery around multi-hop composition tasks and
re-calibrated: 53 of 57 (93%). Still above the bar. The full battery remains unrunnable as
a measurement instrument and the $120 is untouched.

**Along the way the remediation work found four more defects in the harness, three of them
capable of corrupting a result silently.** One of them failed the tool arm for giving a
demonstrably correct answer. Another baked contaminated values into the frozen expected
answers. Neither would have announced itself in a $120 run; both would have shown up as
plausible numbers.

The single most useful thing to take from this session is not the calibration figure. It is
that **an adversarial check found a real defect on every occasion it was run**, four
sessions out of four. That rate does not suggest a harness that is nearly finished.

## Phase 1 — the five remediations

All five were completed before any calibration ran.

**1. The negative control now sweeps the whole battery.** An agent with no tools, told to
claim success from guesswork, is run against every task through the same adjudicator and
the same live state as a real arm. Across 43 tasks it correctly failed 42 and passed one:
`R2.010`, whose true answer of 47 collided with a number the bluffing model reaches for.
The check was sound; the expected *value* was guessable. It now asks for a different total.

**2. Every write check was exercised against a genuine completion.** `verify_write_checks.py`
performs each write for real over HTTP using the tool arm's own tools, then requires the
check to pass; then performs a near miss that violates exactly one stated requirement and
requires the check to fail. Fifteen assertions across five tasks, all holding: an unchecked
item wrongly checked off, a meal scheduled in the wrong slot, a tag added by destroying the
existing tags, the wrong shopping list emptied, and a recipe created with the wrong
servings are each caught. Four of these five checks had never been scored by the current
adjudicator before this ran.

**3. Near-miss tasks were added.** These are well-formed queries whose subject demonstrably
exists and which legitimately match nothing, so that *"I checked and there is nothing"*
becomes distinguishable from *"this capability does not exist."* They exist to remove the
shortcut identified in Finding 005, where an arm holding twenty tools can see absence at a
glance while a shell agent must prove a negative across 259 operations. The count of
genuinely impossible tasks was held at six throughout, so their share fell from 6/43 (14.0%)
to 6/57 (10.5%); the battery was never inflated in the tool arm's favour.

**4. The baseline's budget was tripled**, to 60 turns, 450,000 tokens, $1.80 and 900 seconds
against the tool arm's 20 turns, 150,000 tokens, $0.60 and 300 seconds. Budget exhaustion is
now reported per arm as a first-class metric, and an exhausted attempt is described as
*"could not finish within budget"* and never as getting the answer wrong.

**5. Attempts fixed at three per task per arm**, with per-task variance, `pass^3` and the
per-round spread that defines the noise floor now computed by the reporting code.

Both budget and battery changes are recorded as dated amendments A1 and A2 to the
pre-registration, made before any full-battery result existed, as FR-006 requires. **The
decision table itself was not touched.**

## Phase 2 — calibration, twice

### First pass: 44 of 46 (96%)

| Family | Passed | | Family | Passed |
|---|---|---|---|---|
| R1 single-hop reads | 12/12 | | N impossible | 6/6 |
| R2 multi-hop reads | 15/15 | | NM near-miss | 2/3 |
| R3 underspecified | 4/5 | | W1 writes | 5/5 |

Cost $1.57, no budget exhaustion, 2.4 turns per task on average.

The diagnosis is in the shape of the run rather than the score. **33 of 46 tasks (72%) were
solved in a single tool call plus a submission, and 36 of 46 (78%) used exactly one distinct
tool.** A task that one tool call answers measures tool coverage, not agent capability, and
cannot discriminate between arms. The `R2` family had been written as multi-hop, but the
tools collapse those hops into one call.

Of the two failures, one was a harness bug (below) and one was genuine: asked to "rename the
list" when five lists exist, the arm answered `impossible` where the correct response is to
ask which list. That is a real distinction and the check is right to enforce it.

### The revision

Ten composition tasks were added as a new `R4` family. Each requires joining at least two
collections and doing arithmetic across the join — the meal plan against recipe ratings,
scheduled meal slots against ingredient counts, shopping lists against exclusions.

**The difficulty was deliberately capped in a way that protects the tool arm, and this is
the part of my work most open to challenge.** Tasks were *not* built on fields exposed only
by a per-recipe detail fetch, such as instruction counts, because the tool arm would need
sixty tool calls against a twenty-turn budget while the shell arm could do it in one `bash`
loop. Building those tasks would have rigged the battery against the tool arm as surely as
the original battery flattered it. The consequence is that `R4` difficulty is bounded by
what a twenty-turn agent can reach, which limits how hard the battery can become without
also revisiting the budget.

### Second pass: 53 of 57 (93%)

| Family | Passed | | Family | Passed |
|---|---|---|---|---|
| R1 single-hop reads | 12/12 | | N impossible | 6/6 |
| R2 multi-hop reads | 15/15 | | NM near-miss | 4/4 |
| R3 underspecified | 4/5 | | W1 writes | 5/5 |
| **R4 composition** | **7/10** | | | |

Cost $2.41. Budget exhaustion 0 of 57. False successes 3 of 4 failures. 12,582 tokens per
solved task, $0.0423 per task, 2.5 turns per task on average.

**The new family worked exactly as intended and the rest of the battery did not move.** All
three `R4` failures were confident wrong answers from arithmetic or join errors: 12 where
the answer was 13, 3.23 where the answer was 3.20, and 36 ingredient lines where the answer
was 33. That is the failure mode worth measuring, and it is invisible in a battery of
single-call lookups.

But 27 of 57 tasks are still `R1` and `R2`, all 27 passed, and the aggregate stayed above
the threshold. Reaching the pre-registered band needs composition tasks to *dominate* the
battery, which is a redesign rather than a patch.

## The four defects found while remediating

**A silently permissive query engine, which failed the tool arm for being right.** The
reference-query engine resolved fields with `row.get(field)`, so a misspelled field name
matched nothing — indistinguishable from a query that legitimately matches nothing. A
near-miss task had been written against a field called `tools` where the oracle calls it
`cooking_tools`. It was believed empty. It is not: eight recipes require the Wok. The
calibration pass marked the tool arm **wrong for giving the correct answer**, and the
degeneracy screen that would have caught an unexpectedly empty result had been waived for
exactly that family, because emptiness is what a near-miss task is for. The two mistakes
concealed each other. The engine now rejects unknown fields outright; re-validating under
the strict engine showed that one task was the only one affected out of 46.

**Near-miss tasks were passable by abstaining.** On the full sweep, the tool-less bluffing
agent passed the reformulated near-miss task by answering "none" — which is the correct
answer. An empty result is cheap to guess. All four near-miss tasks are now **corroborated
pairs**: they ask for a count that can only come from querying alongside the count that is
legitimately zero. The bluffing agent now fails all four.

**The runner left the application dirty.** The fixture is restored *before* each attempt, so
a run ending on a write task leaves its changes in place. The battery validator then froze
expected answers against that contaminated state, recording nine recipes tagged `budget`
where the true fixture has eight, because a recipe created by the last write task was still
present. The runner now restores on exit, and the validator refuses to freeze when the live
fingerprint disagrees with the one already recorded.

**A guessable expected value.** `R2.010` is described above. Its check was correct and its
answer was a number a bluffing model volunteers.

The first of these would have produced a wrong result that looked entirely reasonable. The
third would have shifted an unknown number of expected answers. Neither is the kind of thing
a run reports on itself.

## What this does NOT license

- **No claim about the thesis, in either direction.** Only one arm has run the amended
  battery. There is no comparison and no result.
- **No claim that the tool arm is 93% effective.** That figure is the ceiling artefact, not
  a capability measurement. It is high because I wrote the tasks and the tools, and the
  tasks land inside what the tools already do well. Finding 005 named task/tool co-design as
  a threat; this session measured it at 93 to 96 percent.
- **No claim that the `R4` family is fair.** The shell arm has never run it. Composition
  tasks may well suit `bash` and `jq` better than they suit a twenty-turn tool agent, since
  aggregating sixty records is one pipeline in a shell and several calls through a tool
  surface. **The revision could have introduced a bias against the tool arm, and nothing
  here rules that out.** That is the first thing the next run must check.
- **No noise floor.** Both calibration passes used a single attempt. No variance figure
  exists and no difference of any size may yet be called real.
- **No claim about the near-miss reformulation's scoring.** The corroborated pairs are
  scored by strict numeric extraction, so a correct but verbose answer that mentions other
  numbers would be marked wrong. The prompts now demand two numbers and nothing else, and
  observed answers have been terse, but this is an untested scoring artefact.

## What I recommend, and the decision that is not mine

The battery needs a structural rebalance rather than another patch: the single-call families
have to shrink and the composition family has to grow until the tool arm lands inside the
0.25 to 0.85 band.

**That is a scoping decision rather than an engineering one, which is why I stopped.**
Replacing single-hop lookups with multi-hop analytics changes what E7 measures — from
"operating this application the way someone actually would" toward "multi-step analytical
reasoning over its data." The second is more discriminating and may be less representative
of the product. Both readings are defensible and the choice belongs to whoever owns the
product question, not to the person whose tools are being graded.

Three options, in the order I would rank them:

1. **Rebalance toward composition and re-calibrate.** Cut `R1` and `R2` to roughly six each,
   grow `R4` to about twenty-five, keep the impossible, near-miss, underspecified and write
   families as they are. Roughly one working session plus about $3 of calibration.
2. **Raise the tool arm's turn budget and add per-record tasks.** Lifting it from 20 to 40
   turns admits tasks that need a detail fetch per recipe, which are hard for both arms. It
   also weakens the "tools are efficient" claim by construction, so it trades one bias for
   another.
3. **Accept a ceiling and change the primary metric** from task success rate to cost per
   solved task. This is the least appealing: the pre-registration names success rate as
   primary, and switching the primary metric after seeing that success rate saturates is
   precisely the manoeuvre pre-registration exists to prevent. I raise it only to reject it.

## Immediate next steps

1. Decide between the three options above. Nothing else should proceed first.
2. Rebalance the battery, re-freeze, and re-run the negative control and the write-check
   verifier over the result. Both have found a defect every time they have been run.
3. Re-calibrate the tool arm and require the 0.25 to 0.85 band before anything else.
4. **Run one calibration pass of the shell arm over the `R4` family alone**, at about $2,
   before the full run. It is the only way to know whether the revision biased the battery
   toward the baseline, and it is far cheaper than discovering it inside a $120 result.
5. Only then run the full battery: 57 tasks, both arms, three attempts, ceiling $120.
