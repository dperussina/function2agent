# Finding 027 — `data-model.md` §2.1 declares no `RUNNING → TERMINATED` edge, because it declares no `TERMINATED` state: its lifecycle enumerates ten branches out of `RUNNING` by terminal-state name, three taxonomy members the runtime already reaches are absent from them, two names it declares are absent from the taxonomy, and `attach()`'s refusal message cites a §2.1 property that holds only vacuously

**Date**: 2026-08-05
**Feature**: 002. A census of the declared session lifecycle in
[`data-model.md`](../data-model.md) §2.1 against
[`src/contracts/terminal.py`](../../../src/contracts/terminal.py),
[`src/contracts/transition.py`](../../../src/contracts/transition.py) and
[`src/runtime/session_state.py`](../../../src/runtime/session_state.py), taken while routing
cancellation to a terminal state under [`tasks.md`](../tasks.md) **T047**.
**User Story**: none directly. Bears on **FR-006** (the named terminal state) and **FR-007** (resume).
**Owner decision**: **none is recorded here and the register was not edited.** The next free owner
decision number is `OD-26` — written inside a code span, which the corpus checker does not resolve as
an identifier, because writing it as a live token before the register carries the entry is a hard
`identifier-resolution` error. Same escape and same reason as
[finding 026](./026-pivot-root-check-measured.md)'s header. **§4 below is a question for the owner
and deliberately does not answer it.**
**Owner decision, second pass (2026-08-05)**: **OD-26**, now written and no longer escaped. It answers
§4 in favour of `src/contracts/terminal.py` and strikes `terminated.denied_operation`. The escape
above is left standing because it describes the state of the register when §1–§5 were written, and
that is what the sentence is about.
**Model spend**: **$0.0000.** No model was called and no credential was read. The census is `grep`
and reading; the two behavioural readings in §3 are `pytest` arms.
**Method**: read §2.1's lifecycle block literally, term by term, and compare its branch labels
against `TAXONOMY` in `src/contracts/terminal.py` and against the `to_state` of every rule in
`RULES` in `src/contracts/transition.py`. Both directions of the comparison are reported, because
only one of them was asked about.

Numbering note: `026` was the high-water mark across `specs/*/findings/`, checked by listing the
whole tree, and `027` was free at that moment and re-checked free immediately before saving.

---

> ## Read this first: four results, and the second is the one that was not asked for
>
> **1. §2.1 does not declare a `RUNNING → TERMINATED` edge, and the reason is not that the edge was
> omitted — it is that §2.1 has no state named `TERMINATED` at all.** Its lifecycle names two states,
> `CREATED` and `RUNNING`, plus `interrupted`, and every other branch is labelled with a **terminal
> state name** rather than with a state. So the question "does §2.1 declare `RUNNING → TERMINATED`"
> has no literal answer in §2.1's own vocabulary. What it declares is ten `RUNNING → ⟨named terminal
> state⟩` branches, which is the shape the code implements as one `RUNNING → TERMINATED` edge
> carrying a `terminal_state` column.
>
> **2. `terminated.operator_terminated` is not among the ten — and neither are
> `terminated.capability_lapsed` nor `terminated.unrecoverable_fault`, both of which the shipped
> runtime already reaches.** This is the result that matters, and it was not the question. The
> divergence is **pre-existing**: `unrecoverable_fault` has been the runner's teardown state for a
> fault it cannot classify since T046, with its own test arm, and it is as absent from §2.1 as
> `operator_terminated` is. So a rule that "§2.1's declared branch set is authoritative and a member
> outside it may not be reached" does not merely block cancellation-becomes-terminal; **applied
> evenly it invalidates a path that ships today.** That asymmetry is why this is filed rather than
> resolved.
>
> **3. The divergence runs in both directions.** §2.1 declares `terminated.no_progress` and
> `terminated.denied_operation`, and **neither is a member of `TAXONOMY`**. `no_progress` is a known
> gap — `tasks.md`'s loose-requirements table already records that its predicate is *unwritable as
> specified* and assigns it to **T067**. `denied_operation` is recorded nowhere as absent.
>
> **4. `attach()`'s refusal message cites a §2.1 property that is true only vacuously.** It reads
> *"data-model.md §2.1 has no edge out of it"*. §2.1 has no edge out of `TERMINATED` because §2.1 has
> no `TERMINATED`. The **conclusion is correct** — no branch in §2.1 leaves any terminal label, and
> the refusal is right — but the cited warrant is weaker than it reads, and a later contributor
> checking the citation will not find what the sentence promises.
>
> **All four repaired 2026-08-05 under `OD-26`; see the second pass at the foot of this document for
> what was done, what the new check reported before any of it, and one negative result.**

---

## 1. The census

§2.1's lifecycle block, quoted exactly:

```text
CREATED ─▶ RUNNING ─┬─▶ completed
                    ├─▶ terminated.turn_ceiling_reached
                    ├─▶ terminated.token_ceiling_reached
                    ├─▶ terminated.wall_clock_ceiling_reached
                    ├─▶ terminated.spend_ceiling_reached
                    ├─▶ terminated.memory_bound_exhausted
                    ├─▶ terminated.cpu_bound_exhausted
                    ├─▶ terminated.process_bound_exhausted
                    ├─▶ terminated.no_progress            (FR-006 stall condition — defined at FR-006)
                    ├─▶ terminated.denied_operation
                    └─▶ interrupted ─▶ RUNNING            (resume — the same session, FR-007)
```

Set against `TAXONOMY`, member by member. "Reached by the runtime" means a code path in `src/`
produces it, not that a requirement mentions it.

| Taxonomy member | In §2.1's branch set | Reached by the runtime |
|---|---|---|
| `terminated.completed` | yes, as the bare label `completed` | yes — `SessionStateMachine.complete()` |
| `terminated.turn_ceiling_reached` | yes | yes — `terminate_on_ceiling()` |
| `terminated.token_ceiling_reached` | yes | yes — `terminate_on_ceiling()` |
| `terminated.wall_clock_ceiling_reached` | yes | yes — `terminate_on_ceiling()` |
| `terminated.spend_ceiling_reached` | yes | yes — `terminate_on_ceiling()` |
| `terminated.memory_bound_exhausted` | yes | yes — `src/supervisor/bounds.py` |
| `terminated.cpu_bound_exhausted` | yes | yes — `src/supervisor/bounds.py` |
| `terminated.process_bound_exhausted` | yes | yes — `src/supervisor/bounds.py` |
| `terminated.capability_lapsed` | **no** | not yet — FR-050's crash path, no producer in `src/` |
| `terminated.operator_terminated` | **no** | yes — `terminate()`, and as of T047 the cancellation path |
| `terminated.unrecoverable_fault` | **no** | yes — `Runner._stand_down()` on a loop that raised |

And the other direction:

| §2.1 branch label | In `TAXONOMY` | Recorded as a gap anywhere |
|---|---|---|
| `terminated.no_progress` | **no** | yes — `tasks.md` loose-requirements row 6, assigned to **T067** |
| `terminated.denied_operation` | **no** | **no** |

**The bare `completed` is a third, smaller divergence and is called out rather than smoothed over.**
§2.1 writes `completed`; the taxonomy member is `terminated.completed`. Every other terminal branch in
the diagram carries the `terminated.` prefix, so the odd one out is the one the invariant test's
`state.name.startswith("terminated.")` assertion would reject if it were read off the diagram. Nothing
reads the diagram, which is exactly why it drifted.

## 2. What this does and does not license

**It does not license adding an undeclared edge, and none was added.** The `RUNNING → TERMINATED`
edge carrying `terminated.operator_terminated` existed in code before this pass in three places, all
of them checkable: `_RULE_BY_TERMINAL` in `src/runtime/session_state.py` maps the member to
`ST_OPERATOR_TERMINATED`; that rule's registry entry in `src/contracts/transition.py` describes
itself as `RUNNING → TERMINATED`; and `tests/fixtures/session_conformance.json` ships the name as a
cross-language conformance vector the Go enforcement point reads. T047 routed a **new caller** down
an existing edge. It added no rule, no state and no taxonomy member.

**It does license distrusting §2.1 as a complete edge set**, which is the narrower and more useful
claim. §2.1 is a specification of the *shape* of the lifecycle — one non-terminal state, a resume
edge back, and no edge out of any terminal label — and on that shape it is authoritative and the
routing conforms to it. It is **not** a maintained enumeration of the taxonomy, and it has not been
one for at least three members.

## 3. Two behavioural readings, for the record

Both taken with `.venv/bin/python -m pytest` against the working tree at the revision this finding is
committed in, on Darwin 25.2.0. Neither depends on the host: both read session rows out of a
temporary SQLite file the test creates.

**Before the routing change**, `attach()` on a cancelled session did not refuse. The arm
`test_a_cancelled_session_cannot_be_attached_to` failed with `DID NOT RAISE
<class 'src.runtime.runner.RunnerError'>` — the session sat in `INTERRUPTED`, which is FR-007's
resume state, and `attach()` resumed it.

**After**, the same arm reaches the pre-existing `STATE_TERMINATED` branch, not the fallback:

```text
src.runtime.runner.RunnerError: 'sess-1' is TERMINATED as
'terminated.operator_terminated'. data-model.md §2.1 has no edge out of it, and a
revived session would carry a second outcome for a run FR-006 says already has one.
```

**Which branch was reached is asserted rather than assumed.** `attach()` has two refusal branches and
both name a state, so matching `RunnerError` on the string `TERMINATED` would also pass on the
fallback `"is {state}, which has no edge"` branch. Only the `STATE_TERMINATED` branch interpolates
`row.terminal_state`, so the arm requires the taxonomy **name** in the message. Note 4 in the box
above is the caveat that goes with the quoted text: the sentence is right and its citation is
vacuous.

## 4. The question this left for the owner — answered 2026-08-05, see the second pass below

> **This section is preserved as it was asked.** The owner took the **third** option on 2026-08-05
> under [OD-26](../../001-discovery-validation/plan.md#od-26--srccontractsterminalpy-is-authoritative-for-terminal-state-membership-and-data-modelmd-21-is-a-derived-view-of-it-terminateddeniedoperation-is-struck-from-the-diagram),
> and `terminated.denied_operation` — the sub-question the first option left open — was **struck**.
> The options below are not edited, because a question is evidence about what was and was not obvious
> at the time, and rewriting it to match the answer destroys that.

**Does §2.1's lifecycle get reconciled with `TAXONOMY`, and in which direction?** Three members are
missing from the diagram and two labels in the diagram are not members. The options are not
equivalent and this finding picks none of them:

- **Reconcile the diagram to the taxonomy.** Add `capability_lapsed`, `operator_terminated` and
  `unrecoverable_fault` as branches; decide what becomes of `denied_operation`, which currently
  specifies a terminal state nothing produces and nothing records as owed.
- **Reconcile the taxonomy to the diagram.** This is **T067**'s remaining real work — `no_progress`
  and `denied_operation` are the members the taxonomy lacks — and `no_progress` is blocked on the
  unwritable predicate, so this direction cannot complete today.
- **Declare §2.1 a shape specification rather than an enumeration**, and say so in §2.1, so that a
  future reader checking a member against it learns that the diagram was never the closed set.
  `src/contracts/terminal.py` and its invariant test are the closed set, and `NAMES` is what every
  consumer actually reads.

**What is not an option is leaving `attach()`'s message citing §2.1 for a property §2.1 cannot
carry.** That is cheap to fix and is not fixed here, because rewording it to cite
`src/contracts/terminal.py` instead presumes the third option above.

> **Fixed 2026-08-05, and not in the direction this paragraph guessed.** The message now cites
> **`SessionStateMachine`**, not `terminal.py`. The reasoning: `terminal.py` is authoritative for
> *membership* — which names exist — and `attach()`'s refusal is about *transitions*, which
> `terminal.py` says nothing about. `SessionStateMachine._move` is what actually refuses every
> transition out of `TERMINATED`, unconditionally, with its own arms. Citing the taxonomy would have
> replaced a vacuous citation with a merely irrelevant one.

## 5. A negative result about `TerminalState.meaning`, since the routing widened one

**Nothing consumes `TerminalState.meaning` for its content.** Established by search rather than
assumed, across every file extension in the tree: the field is written in
`src/contracts/terminal.py`, named in that module's own `require()` error message as prose telling an
author what to supply, and read in exactly one place —
`tests/invariants/test_terminal_taxonomy.py`, as `assert state.meaning`, a non-emptiness check that
is indifferent to what the string says.

**No literal-string assertion was added to compensate, and that is a decision rather than an
omission.** An assertion pinning the widened wording would be a change-detector: the next editor
satisfies it by updating both sides, which is precisely the failure mode that left `Rule.description`
stale — a field with no consumer anywhere. Falsifying a field nothing reads breaks nothing, so
widening it is safe; pinning it would add a gate that cannot fail for the right reason.

**The direction this cuts is worth stating.** The reason to widen the meaning at all was not
correctness of a consumer — there is none — it was that the *name* `operator_terminated` is now
narrower than the set of events that produce it, and the meaning is the only place that discrepancy
can be recorded for a human. The name is a wire string in the conformance vectors and did not move.

---

# Second pass, 2026-08-05 — §4 answered, the divergence repaired, and an instrument built that would
have found it

> ## Read this second: four results, and the last one is negative
>
> **A. §4's question is answered by [OD-26](../../001-discovery-validation/plan.md#od-26--srccontractsterminalpy-is-authoritative-for-terminal-state-membership-and-data-modelmd-21-is-a-derived-view-of-it-terminateddeniedoperation-is-struck-from-the-diagram):
> `src/contracts/terminal.py` wins, §2.1 is a derived view.** This is §4's third option and it was
> taken on this finding's own §2 evidence — the asymmetry that a diagram-wins rule invalidates
> `terminated.unrecoverable_fault`, which ships. The consumer census the decision rests on was
> re-taken independently and is reported in **§7** below, because this finding's §4 asserted the
> imbalance without counting it.
>
> **B. `lifecycle-taxonomy` is the instrument, and it was observed failing on the unrepaired tree
> before anything was repaired.** Seven errors, quoted verbatim in **§6**. It names every discrepancy
> §1 catalogued, in both directions, and it names the bare-`completed` defect as a *pair* of errors
> rather than one — which is the shape that tells a reader a label was mistyped rather than a member
> forgotten.
>
> **C. `terminated.denied_operation` is struck, and the premise was checked rather than assumed.**
> **§8** reports the search: no requirement in this specification wants a denial to be terminal, and
> **SC-022** and [`contracts/filesystem-decision.md`](../contracts/filesystem-decision.md) both score
> a denial on the *record's existence*, which presupposes a session still running to hold it.
>
> **D. The exit-4 vacuity hole in the removal-proof harness does NOT reproduce.** Reported by the
> pass that wrote §1–§5 as a live defect. **§9** shows three independent guards catching it, two of
> them observed doing so on a deliberately-planted bogus proof. This is a **negative result** and it
> is recorded as one: nothing was changed in the harness, because nothing needed to be.

## 6. The negative control: what the check reported before anything was fixed

**Verbatim, `check_corpus.py --check lifecycle-taxonomy` against §2.1's HEAD content.** The ten branch
labels the diagram declared at `1446258` were transcribed into the table shape the check reads —
nothing renamed, nothing added, nothing dropped — and the check run against that tree:

```text
specs/002-spec-aware-agent-runtime/data-model.md
        1  error   lifecycle-taxonomy
           found:    src/contracts/terminal.py's TAXONOMY declares terminated.capability_lapsed, and the lifecycle does not mention it
           expected: a row for terminated.capability_lapsed with status 'member'
        1  error   lifecycle-taxonomy
           found:    src/contracts/terminal.py's TAXONOMY declares terminated.completed, and the lifecycle does not mention it
           expected: a row for terminated.completed with status 'member'
        1  error   lifecycle-taxonomy
           found:    src/contracts/terminal.py's TAXONOMY declares terminated.operator_terminated, and the lifecycle does not mention it
           expected: a row for terminated.operator_terminated with status 'member'
        1  error   lifecycle-taxonomy
           found:    src/contracts/terminal.py's TAXONOMY declares terminated.unrecoverable_fault, and the lifecycle does not mention it
           expected: a row for terminated.unrecoverable_fault with status 'member'
      157  error   lifecycle-taxonomy
           found:    completed is declared a member of the lifecycle, but is not in src/contracts/terminal.py's TAXONOMY
           expected: completed in TAXONOMY, or the row marked 'owed' against the task that owes it, or struck in the house style
      165  error   lifecycle-taxonomy
           found:    terminated.no_progress is declared a member of the lifecycle, but is not in src/contracts/terminal.py's TAXONOMY
           expected: terminated.no_progress in TAXONOMY, or the row marked 'owed' against the task that owes it, or struck in the house style
      166  error   lifecycle-taxonomy
           found:    terminated.denied_operation is declared a member of the lifecycle, but is not in src/contracts/terminal.py's TAXONOMY
           expected: terminated.denied_operation in TAXONOMY, or the row marked 'owed' against the task that owes it, or struck in the house style

7 error(s), 0 warning(s)
```

**Seven errors for six defects, and the arithmetic is the point.** §1 catalogued five names plus the
`completed`/`terminated.completed` label defect. The label defect surfaces **twice** — once as a
member with no row, once as a row with no member — because the check has no notion of a typo and
reports each direction separately. A reader seeing the same word in both lists learns more from that
than from a single "misspelled" error: it is the signature of a *renamed* member, which is the failure
mode this check exists for, and it is indistinguishable at the mechanical level from a member that was
genuinely dropped and a different one genuinely added.

**Why this run is reproducible rather than a transcript.** It is taken against a scratch tree built by
`git archive HEAD`, so anyone can rebuild it. That matters more than it sounds: a negative control
quoted from a session log is a claim about a run nobody else can make, and this repository's standing
complaint against its own instruments is exactly that they were believed rather than exercised.

**What the check does not catch, stated so nobody infers otherwise.** It reconciles *membership* and
nothing else. A row whose `Requirement` column cites the wrong FR passes. A member whose `meaning`
contradicts its name passes. The ASCII shape above the table is not parsed at all — if someone draws
an edge out of `TERMINATED` in it, this check is silent, and `session_state.py`'s own arms are what
would catch the code following.

## 7. The consumer census, re-taken rather than repeated

**OD-26's reasoning rests on `terminal.py` having consumers and §2.1 having none.** That claim was
verified independently rather than carried over.

**`src/contracts/terminal.py` is imported by seven modules under `src/`** —
`contracts/transition.py`, `runtime/loop.py`, `runtime/runner.py`, `runtime/session_state.py`,
`runtime/session_store.py`, `runtime/trace.py` and `supervisor/session_table.py` — plus seven test
modules, of which `tests/invariants/test_terminal_taxonomy.py` is the one asserting the closed-set
property FR-006 requires. **Seven is the count the brief predicted; the membership was not what this
pass first wrote down**, which is the reason it was recounted instead of quoted.

**`tests/fixtures/session_conformance.json` carries a terminal-state name as a wire string, and the Go
enforcement point reads it.** `src/proxy/conformance_test.go` loads the fixture by path, and the
fixture carries `terminated.operator_terminated`. So a member name is a **cross-language** interface,
which is the second independent reason the diagram cannot be the authority: nothing in `data-model.md`
is read by any program in either language.

**§2.1 has no consumer, and that was checked in the forbidding direction too** — nothing greps it,
nothing parses it, and no test names it. Before this pass, the single artifact in the repository that
*cited* §2.1 was `attach()`'s refusal message, and it cited a property §2.1 could not carry. That is a
consumer count of zero with one dangling reference, which is worse than zero.

## 8. `denied_operation`: the premise held, so the strike stands

**The instruction was to stop and report if any requirement wanted a denial to be terminal. None
does.** Searched: FR-006, the FR-011/FR-017 egress requirements, FR-048, SC-022, and
[`contracts/filesystem-decision.md`](../contracts/filesystem-decision.md).

**FR-006 names exactly one producer of its own** — the stall condition — and enumerates no denial.
Every other member traces to a ceiling (FR-005), a bound (FR-049), a lapse (FR-050) or a fault.

**SC-022 scores denials by counting records.** A criterion satisfied by *the existence of a recorded
decision* presupposes a session that survived to record it and to be measured. A terminal
`denied_operation` would make the criterion unmeasurable in the ordinary case: the first denial ends
the session, so a session can contribute at most one record and the count is a count of sessions.

**`filesystem-decision.md` is explicit that a refusal is a disposition, not an outcome.** The
supervisor returns a decision the loop reads and continues past; the contract's own worked examples
show a session taking a denial and proceeding.

**The strike is therefore on sound grounds and `denied_operation` did not survive.** The row is struck
in §2.1 in the dated house style rather than deleted, because a reader who relied on it needs to find
out that it went and why — the strike is inside a table cell, which renders, rather than inside the
fenced diagram, where `~~` would render literally.

## 9. Negative result: the exit-4 vacuity hole does not reproduce

**The claim.** The previous pass reported that one of its removal proofs named a test that no longer
existed, and that under the harness's own reasoning this would have scored `proved` on a `pytest`
exit 4 — a usage error rather than a test failure, and therefore possibly outside guards built for
exit 5 and zero-collection.

**It was reproduced deliberately and it did not fire.** Two bogus proofs were planted at the top of
`tests/removal_proofs.sh` — one naming a nonexistent test *inside a real file*, one naming a
nonexistent *file* — and the harness run:

```text
  NO TEST   EXIT4-EXPERIMENT-A nonexistent test name in a real file — tests/integration/test_mount_namespace.py::test_this_name_does_not_exist_anywhere matched nothing in the baseline; the test was renamed or removed
  NO TEST   EXIT4-EXPERIMENT-B nonexistent test file — tests/integration/test_no_such_file_at_all.py::test_nope matched nothing in the baseline; the test was renamed or removed
...
92 proved, 2 unproven, 6 skipped
```

Both scored **unproven**, and the harness exited non-zero. Restoring the file and re-running returns
`92 proved, 0 unproven, 6 skipped`.

**Three independent guards catch it, and each was checked separately rather than assumed from the
first one's success.**

1. **`tools/check_tampers.py`, statically, before the harness runs at all.** Pointing a live proof at
   a nonexistent test id produces:

   ```text
     ERROR    FR-048 mount namespace — pivot_root removed
              runs test_this_name_does_not_exist, which is not defined in tests/integration/test_mount_namespace.py — pytest exits 4 for a missing selector, which the harness reads as a failing test and reports as proved
   ```

   The guard **names exit 4 in its own error text**, so the hole was not merely closed by accident of
   a broader check — it was closed knowingly. This runs in the ordinary suite via
   `test_every_declared_removal_proof_still_names_a_live_site_and_a_live_test`, so it fails on the
   same push that causes the rot.

2. **`baseline_py()` returns `ABSENT`** for a selector that matched nothing in the full-suite
   baseline, and `report_unrunnable()` turns that into `NO TEST` / unproven. This is the layer the two
   planted proofs actually hit, and `baseline_py`'s own comment records that it was written for this
   case.

3. **`proof()`'s collection check would catch it even past the first two.** Real exit-4 output is:

   ```text
   ERROR: not found: .../tests/integration/test_mount_namespace.py::test_this_name_does_not_exist_anywhere
   (no match in any of [<Module test_mount_namespace.py>])
   ```

   which matches `^(ERROR|INTERNALERROR)` and contains no `N failed`, so the `tamper-broke-collection`
   branch takes it. Verified by grepping the captured output, not by reading the regex.

**Nothing was changed in the harness.** A guard that already works does not need a fourth copy, and
adding one would have produced a commit that looked like a fix for a defect that did not exist. **The
previous pass's report was wrong on this point** — most likely it observed a proof it had rotted and
inferred the harness's behaviour from the exit code rather than running it, since the static gate
would have caught the same proof on the next `pytest` run.
