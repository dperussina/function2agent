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

## 4. The question this leaves for the owner, unanswered on purpose

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
