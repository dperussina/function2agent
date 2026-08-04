# Specification Quality Checklist: Spec-Aware Agent Runtime

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-08-03
**Status**: ~~**Re-validated 2026-08-03 after `/speckit-clarify`.** 15/16 → 15/16 items passing, with
no item changing state. The three original `[NEEDS CLARIFICATION]` markers are resolved and one new
one was opened at FR-047 by the interaction of two of the answers, so the same item fails for a
different reason. See *Validation run 2* under Notes.~~
~~**Superseded 2026-08-03 by validation run 3 — the state it described was accurate and has moved.**
**16/16 items passing.** FR-047's marker is resolved and no marker remains anywhere in the
specification, in bracketed or weakened prose form. See *Validation run 3* under Notes.
**Ready for `/speckit-plan`,** with three Constitution Check exposures recorded below that the plan
phase must dispose of rather than discover.~~
**Superseded 2026-08-03 by validation run 4 — accurate when written, and the three exposures it
recorded are now closed in the specification rather than carried into the plan.**
**16/16 items passing**, unchanged, because closing the exposures added requirements rather than
resolving a failing item. FR-048 through FR-054 and SC-022 through SC-028 were added, the four
principles that had no disposition now have deviation records in Dependencies, and no
`[NEEDS CLARIFICATION]` marker exists in any form. See *Validation run 4* under Notes.
**Ready for `/speckit-plan`,** with no Constitution Check exposure outstanding.
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs)
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [x] Success criteria are technology-agnostic (no implementation details)
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions identified

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows
- [x] Feature meets measurable outcomes defined in Success Criteria
- [x] No implementation details leak into specification

## Notes

- Items marked incomplete require spec updates before `/speckit-plan`.

**Validation run 1 — 2026-08-03.** One item failed: three `[NEEDS CLARIFICATION]` markers, at
FR-002, FR-025 and FR-029. None had a defensible default, so all three went to the owner rather than
being guessed.

**Validation run 2 — 2026-08-03, after `/speckit-clarify`. All three original markers are resolved,
the same item still fails, and it fails for a different reason.** Resolving the three surfaced a
fourth question that only exists because two of the answers interact, and it is marked at FR-047
rather than guessed. The count of failing items is unchanged at 15/16; what it means has changed
completely, so the table below is retained with its resolutions rather than deleted.

**Validation run 3 — 2026-08-03, after the FR-047 decision. All 16 items pass and the specification
is plan-ready.** The fourth marker is resolved rather than deferred, the marker item flips for the
first time since run 1, and no other item changes state. What run 3 also did, because asserting
readiness is not verifying it, is re-check the whole reference set rather than only the references
this session touched — the run-2 defect was three identifiers that all *resolved* and all named the
wrong requirement, which no mechanical checker can see. Results are under *What run 3 verified*.

**Validation run 4 — 2026-08-03, after the Constitution Check exposures were closed in the
specification. All 16 items pass, and the count is unchanged for a reason worth stating: the
exposures run 3 recorded were never checklist items.** They were a warning attached to a passing
checklist, so closing them adds requirements and moves no item. What changed is that the specification
now *requires* the three sandbox terms it previously assumed the plan would supply (**FR-048**,
**FR-049**, **FR-050**), states the scope on which FR-039's shadow judge is compliant with
Principle I instead of leaving it to be inferred (**FR-052**), carries deviation records for the four
principles that had none, and closes the two clauses of Principles VII and VIII that apply to v1 and
were partly met (**FR-053**, **FR-054**). **FR-051** closes an admission-only reading of FR-020 that
no exposure had named. Results are under *What run 4 verified*.

### The four markers, resolved

| Marker | Requirement | The decision it needed | Resolved 2026-08-03 |
|---|---|---|---|
| 1 | FR-002 | ~~What the product supports when a target publishes no machine-readable specification.~~ Probing establishes served *paths* and cannot establish served *methods* without an introspectable target or an unverifiable declaration (**U-39**), and FR-009 denies what it cannot resolve. This sets the supported-target population | **A published machine-readable specification is an admission criterion.** Targets without one are rejected at admission by **FR-044**, which fails closed and states its reason; the exclusion is recorded in Out of Scope and the narrowing of the addressable population is stated in Assumptions. Probing is excluded for *method* discovery only — it executes handlers on at least one measured framework — and remains available at *path* level to FR-046 |
| 2 | FR-025 | ~~Whether a result the verifier cannot verify is returned marked unverifiable, or refused.~~ Refusal on a substantial share of results changes the usable surface; returning weakens the claim the product is sold on | **Returned, marked not verifiable.** FR-024 is unchanged and is what creates the state. The share of results in that state becomes a measurement under **FR-045** and **SC-019**, with no threshold pre-registered because nothing estimates it |
| 3 | FR-029 | ~~What triggers a deployment-drift check~~, given that the deployment moves under configuration, rollout and its installed package set and produces no commit (**O-04**). The choice sets the detection latency FR-042 must later measure | **Both manual and automated, with at least one automated trigger configurable.** The default is a scheduled re-fetch of the target's published specification at a five-minute interval, giving a stated detection window of one interval plus one check (**FR-046**, **SC-020**). A customer-emitted deployment event is admissible as a configured trigger and may not be the only one, because the ability to emit one cannot be assumed under self-hosting |
| 4 | FR-047 | ~~What the runtime does while an *admitted* target is no longer publishing the specification that admitted it.~~ Opened by markers 1 and 3 interacting: FR-002 made a published specification an admission criterion and FR-046 re-checks it on a schedule, neither of which was true when FR-030 was written, so FR-030's disable-the-affected-operation clause resolved to denying everything while also declining to stop the runtime. The two candidates were **(a)** continue on the last-known-good set marked stale under a configured staleness ceiling, and **(b)** deny on the first failed re-fetch. This sets an availability property and no feature 001 evidence bears on it | **(a) — serve the last-known-good set marked stale, deny past a configured staleness ceiling.** Recorded as a *consistency* argument, not a preference: it is the third time the specification returns something marked rather than withholding it (FR-025, and FR-026 from **D-17**). The ceiling default is **fifteen minutes from the last successful fetch**, stated as a configured default and bound to **FR-043** so it cannot travel externally as a validated number. Marked stale on the same caller-visible record as FR-025's verification state and by the same machine-distinguishable discipline, as a separate field rather than a fourth verification value. FR-047 is a **specialization** of FR-030, not an exception, and FR-030, FR-031 and FR-001 are each marked where FR-047 narrowed them. **Recorded as an owner decision later the same day: `plan.md` OD-21**, after the propagation that wrote OD-18 through OD-20 declined to record it on the grounds that doing so was an owner act |

Feature 001 carried two such markers and resolving them with the owner materially changed its scope.
These were recorded rather than guessed for the same reason, and resolving marker 1 narrowed this
feature's supported-target population in exactly that way.

### ~~The one failing item, restated~~ — closed 2026-08-03

> ~~**One `[NEEDS CLARIFICATION]` marker remains, at FR-047, and it did not exist before this
> session.** An admitted target can stop publishing the specification that admitted it. That is
> deployment-clock drift affecting every operation at once, and FR-030 — written before a published
> specification was an admission criterion and before anything re-checked it on a schedule — gives no
> rule for it: its disable-the-affected-operation clause resolves to denying everything, while it
> also declines to require stopping the runtime. The two candidate dispositions trade a
> self-inflicted outage on a transient blip against serving a set the deployment may no longer
> honour. It sets an availability property of the product, no feature 001 evidence bears on it, and
> it is marked rather than defaulted for the same reason the original three were.~~
>
> **Superseded 2026-08-03 — the diagnosis was correct and the marker is answered.** Marker 4 in the
> table above carries the decision. Nothing in the reasoning above turned out to be wrong; the owner
> chose (a), and the argument that closed it was not a weighing of the two candidates but the
> observation that (b) would have been the one place this corpus reversed a rule it had already
> applied twice.
>
> **And recorded as a decision 2026-08-03, later the same day: `plan.md` **OD-21**.** For the interval
> between the clarify session and that entry, the answer above lived only in requirement text and in
> this table — the same defect OD-18, OD-19 and OD-20 close for the session's other three answers.
> The decision is unchanged; **FR-047**, the narrowings at **FR-001**, **FR-030** and **FR-031**, and
> **SC-021** now name an authority instead of recording their own.

### What run 3 verified

- **Marker sweep.** No `[NEEDS CLARIFICATION]` marker survives in `spec.md`, and no weakened prose
  form of one either — the three phrasings this corpus has used for a deferred decision ("open
  question", "the disposition is", "awaits the owner") appear only inside struck text carrying a
  dated resolution note.
- **Reference sweep, every identifier occurrence in `spec.md`.** Every `FR-`, `SC-`, `OD-`,
  `D-`, `C-`, `U-` and `O-` reference was re-checked against the *substance* of what it names, not
  merely against whether it resolves — the run-2 defect being three references that all resolved and
  all named one requirement lower than intended. **No further mis-pointed reference was found**,
  including in the three rows run 2 corrected, in the material run 2 added, and in the
  success-criteria references. The registers outside this feature — **OD-01** through **OD-14** in
  feature 001's `plan.md`, and the `D-`, `C-`, `U-` and `O-` registers in
  `research/14-architecture-synthesis.md` — were each read at their defining row and matched against
  the use made of them here. *(**Scope note added 2026-08-03**, and the bound above is deliberately
  **not** advanced. It records what run 3 read, and run 3 read fourteen; the OD register now runs to
  **OD-21**. Advancing it would claim a coverage this run did not have. **OD-15** through **OD-21**
  are therefore outside every sweep on this list, and the four recorded retroactively — OD-18 through
  OD-21 — are the ones whose references in `spec.md` were written before the decisions they cite
  existed.)*
- **Reachability of everything added after the specify phase.** **FR-044** is reachable from FR-002,
  FR-020, the Edge Cases, Out of Scope and Key Entities, and is exercised by **SC-018** and User
  Story 1 scenario 6. **FR-045** is reachable from FR-024, FR-025 and the Edge Cases, and is
  exercised by **SC-019**. **FR-046** is reachable from FR-002, FR-029 and the Edge Cases, and is
  exercised by **SC-020** and User Story 3 scenario 5. **FR-047** was reachable only from an Edge
  Case and is now reachable from FR-001, FR-030, FR-031 and the Clarifications, and is exercised by
  the new **SC-021** and the new User Story 3 scenario 6 — added because its three siblings each
  carry a criterion and a scenario and it carried neither.
- **One reachability gap closed outside FR-047.** The Dependencies section mapped principles to
  FR-008 through FR-038 and was never extended when FR-044 through FR-047 were added, so four
  requirements would have reached the Constitution Check unmapped. The mapping is extended in place
  with a dated note.
- **FR-045 and the Context table.** Considered and deliberately not added. That table's selection
  rule is *the differentiating claim of a v1 capability*, and the not-verifiable share is a coverage
  property rather than a differentiating claim. It follows FR-046's pattern instead — declared in
  place and bound to FR-043 — and FR-046's detection window is not in that table either.

### What run 4 verified

- **Principle IV bullet 1, term by term.** The bullet has four terms and the specification now
  requires all four. Filesystem scoping is **FR-048**, the CPU and memory caps are **FR-049**, and
  the credential term is **FR-050**; the egress term was already discharged by FR-014 through FR-019
  under **OD-13**. FR-005 is marked *extended* where it supplies the wall-time cap only, and FR-013
  is marked where it delegated command containment to a "sandbox boundary" that this specification
  had never defined — six requirements stood behind its other delegate and none behind that one.
- **The credential term is stated as something observable rather than restated.** "Does not outlive
  the run" is a lifetime and a lifetime cannot be inspected at a point in time, so FR-050 decomposes
  it into three checkable properties — nothing secret readable from inside the environment, whatever
  authority it holds refused once the session reaches a terminal state, and nothing carried into a
  later session — each of which **SC-024** measures directly. The first of the three closes a gap
  nothing had named: FR-036 keeps secrets out of model context, artifacts, traces and persisted
  state, and the environment a shell runs in is none of those four.
- **No invented thresholds.** FR-049 states **no default value** for either bound and says why —
  nothing in the evidence base bears on an agent's working set — and binds whatever ships to FR-043,
  the same treatment FR-046's detection window and FR-047's staleness ceiling already carry. No new
  measured-looking figure enters the specification: every criterion added in run 4 is stated in
  *zero* and *100%*, which are the two values that assert an absolute rather than report a result.
- **Principle I's clause is scoped, not waived.** FR-039 carries a dated *Scoped* note saying the
  clause governs judges in the success path, that FR-039's judge is outside it by construction, and
  that the clause applies in full to any model judgement that can change behaviour. **FR-052** is the
  standing requirement that keeps the boundary, **SC-025** makes it testable as a differential, and
  the Open Risks entry on the never-performed human adjudication pass is marked as the missing
  precondition rather than left as a write-up caveat.
- **Four deviation records, in Dependencies, in the form the plan's Constitution Check needs.** Each
  names what does not apply, to which scope, on whose decision, and what reinstates it. Two guards
  are written into the preamble of that table: they do not narrow the constitution, whose preamble
  still describes the generator product, and **OD-09 deferred synthesis and decomposition to v2
  rather than cancelling them**, so every disposition reads *not applicable to v1* and never *not
  applicable to the product*.
- **Dependencies extended a second time.** Run 3 mapped FR-044 through FR-047; FR-048 through FR-054
  postdate that sentence and would have reached the gate unmapped in exactly the same way. They are
  mapped in place with a dated note, and the sentence deferring the four unmapped principles to the
  plan is struck as superseded rather than deleted.
- **One reachability check on everything run 4 added.** FR-048 and FR-049 are reachable from FR-013,
  the Assumptions obligation and the co-location Edge Case, and are exercised by **SC-022**,
  **SC-023** and User Story 1 scenarios 7 and 8. FR-050 is reachable from FR-032, FR-033, FR-036 and
  a new Edge Case, and is exercised by **SC-024** and User Story 4 scenario 5. FR-051 is reachable
  from FR-020 — which is marked where FR-051 extended it, so the extension is visible from the
  requirement it extends rather than only from the extension — and from the confused-deputy Edge Case
  and the **U-44** entry in Open Risks; it is exercised by **SC-026** and User Story 3 scenario 7.
  FR-052 is reachable from the *Scoped* note at FR-039 and from Open Risks, and is exercised by
  **SC-025** and, in substance, by User Story 5 scenario 2, which already asserted that a disagreeing
  judge changes nothing. FR-053 is reachable from the Assumptions bullet it was
  promoted from and is exercised by **SC-027**. FR-054 is reachable from FR-012, FR-019, FR-026 and
  FR-027 and is exercised by **SC-028**.

### ~~Constitution Check exposures — for the plan phase, not adjudicated here~~ — closed 2026-08-03 by run 4

> ~~The binding gate is the Constitution Check in `/speckit-plan`, against **v1.2.0**. This checklist
> does not run it. It records three places where the specification would meet that gate with nothing
> to say, because finding them here costs a paragraph and finding them there costs a phase.~~

**Superseded 2026-08-03 — the diagnosis was correct in all three cases and all three are now closed
in `spec.md`.** The table below is retained with its reasoning and gains a resolution column, because
the reasoning is what the plan's Constitution Check will restate. The largest of the three was
correctly called a **spec** fix rather than a plan fix in run 3's closing note, and that is why it
came back to this document before `/speckit-plan` ran rather than after.

| Exposure | Why it bites | Closed by |
|---|---|---|
| **Principle IV bullet 1's three unsatisfied sandbox terms** | The bullet is four terms wide, a configuration missing any one of them does not satisfy it, and the specification required only the egress term | **FR-048** (declared filesystem scope, everything outside it unreadable and unwritable, the rule set and egress policy outside the set), **FR-049** (processor and memory bounds enforced from outside the environment, exhaustion ending in a named terminal state, no default value stated and FR-043 applied to whatever ships), **FR-050** (three observable properties standing in for the lifetime claim). Criteria **SC-022** through **SC-024**; scenarios US1.7, US1.8, US4.5 |
| **Principle I's model-judge clause against FR-039** | The clause requires pairwise evaluation with order-swapping and calibration against human labels; FR-039 requires neither, and the labels do not exist | The *Scoped* note at **FR-039** states the success-path reading, its precise scope, and what changes if the judge gains influence; **FR-052** makes the boundary a standing requirement with Principle I's three conditions as its exit criteria and human labels as an unstarted precondition; **SC-025** tests the boundary differentially |
| **Four principles with no disposition** | II, III, VII and VIII were unmapped, and the constitution's preamble describes a product OD-09 removed from v1 | Four deviation records in **Dependencies**, each with scope and authority, each reading *not applicable to v1* rather than to the product because **OD-09 deferred rather than cancelled**. VII's fixture clause closes with **FR-053** / **SC-027**; VIII's versioning-and-rollback clause closes with **FR-054** / **SC-028**, which is the one-command rollback nothing required anywhere. The `/speckit-analyze` obligation is restated in the spec itself |

<details>
<summary>The three exposures as run 3 recorded them, retained verbatim</summary>

| Exposure | Why it bites |
|---|---|
| **Principle IV bullet 1 is four requirements wide and the specification satisfies one of them.** The bullet requires a sandbox that is *filesystem-scoped*, *CPU/memory/wall-time capped*, holds *no credentials outliving the run*, **and** has the four-term egress allowlist. FR-014 through FR-019 discharge the egress terms completely and **OD-13** was written for exactly that. Nothing in the specification requires a scoped filesystem or a CPU or memory cap on the agent's execution environment, and FR-005 caps wall-clock only. FR-036 keeps secrets out of context and artifacts but never says a credential does not outlive the run | The agent holds command execution (FR-004) inside that environment. The bullet's own words are that "a configuration missing any one of them does not satisfy this bullet," so three-quarters of a sandbox is a fail, and the specification would have to **require** the missing terms rather than assume the plan will supply them |
| **Principle I's clause on model judges is unsatisfiable as the specification stands.** Where a model must judge, the principle requires it to be "pairwise with order-swapping, calibrated against human labels, and reported as an estimate." FR-039 introduces a shadow model judge. FR-039 and FR-040 require neither order-swapping nor human calibration — and the Open Risks section records that the human adjudication pass over the frozen oracle negatives was never performed, so human labels do not exist to calibrate against | The shadow judge is out of the success path, which is what the principle's *prohibition* governs, so the honest reading is that the clause does not bite. That reading needs to be **stated** in the plan's Constitution Check, because the alternative reading makes FR-039 non-compliant on a NON-NEGOTIABLE principle |
| **Four principles have no disposition in the specification at all.** Dependencies maps I, IV, V and VI. Principles **II** (topology encodes protocol), **III** (default to the loop), **VII** (test-first and fixture-backed) and **VIII** (versioned artifacts) are unaddressed. The constitution's own preamble describes a product that emits a multi-agent system — which **OD-09** removed from v1 | II, III and much of VII's generator clause are *not applicable by scope* rather than satisfied, and saying so is a deviation record the plan must write. VII's fixture clause and VIII's versioning clause **do** apply and are only partly met: the Assumptions section carries the fixture discipline, and FR-026 and FR-027 carry content hashing and versioning, but nothing requires one-command rollback. Separately, the constitution's compliance-review section makes `/speckit-analyze` **mandatory** before `/speckit-implement` for any feature adding a permission tier, which this one does |

</details>

### ~~A fourth exposure, found 2026-08-03 and **open** — Principle VI~~ — **RETIRED 2026-08-03 by constitution amendment v1.3.0 (`OD-22`)**

> **Retired, not deleted, and retired by the instrument this entry said it needed.** The entry below
> was correct in every particular, it named the two clauses accurately, it named both available
> remedies, and it correctly refused to close itself. **The owner took the second remedy — an
> amendment — on 2026-08-03**, and `.specify/memory/constitution.md` is at **v1.3.0**. The field list
> is restated over a **traced unit** whose kind the shipping tier declares, and the ship gate binds
> attributability to that tier's own declared unit rather than to *a versioned node*. v1's declared
> unit is the span, FR-038 declares the closed seven-kind set, and **SC-012** measures the gate. So
> the exposure is discharged **at its source** rather than covered by a record: Principle VI needs no
> deviation record, and the graph wording that a v1-scoped record would have left armed for v2 is
> gone from the text.
>
> **Two things this retirement does not claim.** It does not add a fourth row to the table above —
> that table's three exposures closed *in `spec.md`*, and this one closed *in the constitution*, which
> is a different instrument and a different authority. And it does not revise the diagnosis: the
> pass that wrote the three deviation records genuinely missed this one, for the reason stated below,
> and that remains the useful thing in this entry. **Mapped is not the same as satisfied** is the
> sentence worth keeping.
>
> The text below is unedited.

**The heading above says three exposures and says they are closed. Both remain true of those three.
This is a fourth, found later and by a different route**, while rewriting FR-038 against a v1
subject, and it is recorded here rather than folded into the table above because **it is not closed
and this checklist cannot close it.**

Principle VI was never on the unmapped list — Dependencies maps it to FR-038 — so the previous runs
had no reason to look at it. Mapped is not the same as satisfied. **Its terms presuppose a graph**,
and it splits into two clauses with different scopes:

- **The field list** opens *"Every **emitted system** MUST produce, from day one: one span per
  node…"* and then names versioned node identity, the routing decision with its predicate inputs for
  every conditional edge, and per-node cost. v1 emits no system, so this clause has **no v1 subject
  at all** — which is the identical scope argument the table above accepted for Principles II, III
  and VII. **It should have produced a fourth deviation record and did not**, because Principle VI
  was mapped and the run that wrote those records was working from the unmapped list.
- **The ship gate** — *"A capability that cannot be attributed to a versioned node MUST NOT ship"* —
  carries **no scope qualifier**. Read literally, no v1 capability may ship, because v1 has no nodes.
  A deviation record aimed only at the field list would leave this sentence standing.

**What has been done, and what has not.** FR-038 and SC-012 were rewritten on 2026-08-03 against the
**span**, which is the unit v1 actually executes and — worth noting — the unit the principle's own
sentence already uses. The rewrite satisfies the principle's evident intent, which is a trace from
which a failure can be attributed without re-running the session. **It does not settle the mapping**,
and this checklist must not record it as though it did. The remedies are a v1-scoped deviation record
covering both clauses, or an amendment restating identity and cost in unit-neutral terms; **both are
owner acts under the constitution's governance section**, and the choice has a consequence beyond v1
— an amendment binds v2's emitted graphs to the unit-neutral wording, a deviation record does not.

~~**Status: open, and it is the plan phase's Constitution Check that meets it.** It is stated as a
question under `spec.md`'s Clarifications and set out clause by clause in Dependencies.~~
**Status 2026-08-03: CLOSED by amendment.** `spec.md`'s Clarifications entry is marked answered, its
Dependencies reading is marked resolved, and the plan's Constitution Check for Principle VI now
records a pass on the principle's own terms. **One consequence for whoever builds the tracing
code**: the amendment separates *unit identity* from *artifact version*, so a trace carrying the
versions in force but no span kind and no intra-turn position satisfies the superseded wording and
fails the current one.

### What resolving the markers changed elsewhere in the spec

- **FR-002** gained the admission criterion; **FR-044** is the check; **FR-020**'s inspection is now
  explicitly the second stage of one admission sequence, because the operation list it inspects is
  the one FR-044 supplies.
- **FR-010**'s method-level read-only rule was already unimplementable against a target that
  publishes nothing, so marker 1 made an existing dependency explicit rather than adding a new
  constraint. The run-1 framing of it as an open choice of supported-target population understated
  how far the choice had already been made.
- Two Edge Cases were corrected in place rather than deleted — the no-specification case is now
  unreachable, and the high-refusal-share case is half-settled — and one was added for an admitted
  target that stops publishing.
- Three cross-references in Context were **wrong** and are corrected: they each named one
  requirement lower than the one they meant. Every identifier resolved, so nothing had flagged them.

**Added by run 3, for marker 4.** These are narrowings of existing requirements rather than new
constraints, and each is marked in place under the house convention rather than rewritten:

- **FR-030** is marked **narrowed**. Its disable-the-affected-operation clause governs an operation
  *observed* to have drifted; a failed re-fetch observes none. FR-047 is a **specialization** of it —
  below the ceiling there is no affected member to disable, at the ceiling every member is affected
  and FR-030 applies to all of them unchanged.
- **FR-031** is marked **narrowed**. A failed re-fetch has no "after" artifact version to state, so
  in that one case the after term is FR-044's specification state plus the last successful fetch
  time.
- **FR-001** is marked **narrowed**. A restart inside the ceiling may start from the persisted
  last-known-good set marked stale; that set is neither empty nor assumed, and the fail-loudly rule
  is unchanged where none exists or the ceiling has been crossed. Without this, a restart during a
  blip would be indistinguishable from a decommissioned specification — the confusion FR-047 exists
  to prevent.
- Two Edge Cases were marked in place: *an admitted target stops publishing* is **resolved**, and
  *the specification is stale relative to the deployment* is **narrowed**, because its freshness
  bound was FR-046's detection window and that bound only holds while re-fetches succeed.

### Notes on the items that pass, where the pass is qualified

- **Written for non-technical stakeholders.** The domain is technical and the reader is the project
  owner, so the specification uses domain vocabulary — served operations, effect tiers, drift clocks
  — that is defined in Context and Key Entities. It names no language, framework, library, product or
  wire protocol. Assessed as a pass on that standard, which is the standard the item exists to
  enforce.
- **Requirements are testable.** Every functional requirement is stated as an observable behaviour
  with a corresponding acceptance scenario or measurable outcome. The four requirements that are
  obligations to *measure* something — FR-040 through FR-043, joined 2026-08-03 by **FR-045** — are
  testable as artifacts: the report exists with the gate applied, or it does not. ~~**Qualified again
  2026-08-03:** FR-047 carries an open marker and is therefore testable only in its settled half —
  detection, clock attribution, and the prohibition on reading a vanished specification as an empty
  one. Its disposition clause is not testable until the owner answers it.~~ **Qualification withdrawn
  2026-08-03 by run 3 — superseded, not wrong.** FR-047 is now testable end to end: **SC-021** and
  User Story 3 scenario 6 assert the stale marking, the ceiling, the denial past it, the named
  terminal state, and the diff on recovery. Its staleness ceiling is a configured value rather than
  a measured one, which makes the *ceiling* not falsifiable — but that is the same status FR-046's
  detection window already carries, and both are bound to FR-043 so the untestable half cannot be
  claimed. This item is scored the way run 1 scored it, with the marker item carrying the markers.
- **Success criteria are technology-agnostic.** No criterion names a technology. Several name
  corpora and batteries, which are test instruments rather than implementation choices.
- **No implementation details, re-checked for run 4's additions — the item most at risk from them.**
  A sandbox requirement is the easiest place in a specification to name a mechanism, and the three
  added here name none: no container runtime, no isolation technology, no resource-control facility,
  no credential-issuance protocol. FR-048 states which locations are reachable and what happens on
  an access outside them; FR-049 states that bounds exist, are enforced from outside the environment,
  and end a session in a named terminal state; FR-050 states three properties an observer can check
  from outside. Which mechanism supplies each is the plan phase's question and is flagged as such in
  the specification's own preamble to those requirements.
- **Requirements are testable, re-checked for run 4.** FR-048 through FR-052 and FR-054 are stated as
  observable behaviours with a criterion each (**SC-022** through **SC-026**, **SC-028**). **FR-053**
  joins FR-040 through FR-043 and FR-045 as an obligation about what may be *claimed*, testable as an
  artifact in the same way: the fixture exists for a claimed support, or it does not, and **SC-027**
  audits exactly that.

### What this checklist does not assess

Whether the specification is *right* about the product. Three of its capabilities ship with their
differentiating claims unmeasured, which the specification states in Context and converts into
requirements FR-040 through FR-043 and criteria SC-013 through SC-016. **A fourth unmeasured quantity
joined them on 2026-08-03 and it was created by a clarification rather than inherited**: the share of
results returned not verifiable, now FR-045 and SC-019. **A fifth joined on the same day, from
marker 4**: FR-047's staleness ceiling, which is a configured default with nothing measured behind
it and which — unlike the other four — is not scheduled to become a measurement, because no
experiment would tell an operator what staleness they will tolerate. It is bound to FR-043 instead,
which is the weaker remedy and the honest one. **A sixth joined on the same day from run 4, and it is
the same shape as the fifth**: FR-049's processor and memory bounds. The specification deliberately
states *no default value* for either, because nothing in the evidence base bears on an agent's
working set, and whatever value ships is bound to FR-043 rather than scheduled to become a
measurement. A checklist can confirm that the gap is declared; it
cannot confirm that building anyway is the right call. That judgement is recorded at **OD-14** as a
deliberate departure from feature 001's discipline and belongs to the owner.

~~**And whether the plan phase will pass.** Run 3 records three Constitution Check exposures above.
That is a warning, not an adjudication, and the largest of them — Principle IV bullet 1's sandbox
terms, of which the specification requires the egress ones and not the others — is a **spec** fix
rather than a plan fix, so it may come back to this document before `/speckit-plan` completes.~~

**Superseded 2026-08-03 by run 4 — the prediction in its last clause is what happened.** The
exposures came back to this document before `/speckit-plan` ran, and all three are closed in
`spec.md`. What this checklist still does not assess is whether the plan phase will pass: it records
dispositions and requirements that the Constitution Check must adjudicate, and an adjudication is
the plan's act, not this document's. Two things are worth carrying into it. The four deviation
records are **arguments from scope**, and a reviewer who disagrees that v1 emits no topology should
reject them on that ground rather than on their form. And FR-048 through FR-050 are stated as
observable properties with no mechanism named, deliberately, so the plan owes a mechanism for each —
including one that makes FR-050's *bounded* term hold against a crash, which is where a
session-scoped authority is most likely to survive its session.
