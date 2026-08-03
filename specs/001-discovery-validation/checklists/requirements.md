# Specification Quality Checklist: Discovery and Validation

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-08-02
**Status**: **FINAL — feature closed 2026-08-02 on [`plan.md`](../plan.md) OD-07.** The checklist
itself passed at the planning gate and is retained as written. What it looked like after contact
with fifteen experiments is recorded under *Final state* at the bottom; the binding adjudication of
the success criteria is [`VERDICT.md`](../VERDICT.md).
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

**Validation run 1 — 2026-08-02.** One item failed: two `[NEEDS CLARIFICATION]` markers, both
scope-level (evaluation target; authority of the outcome). Neither had a defensible default, so both
went to the decision-maker rather than being guessed.

**Validation run 2 — 2026-08-02. All items pass.** Both were answered and are now recorded in the
spec's *Resolved Decisions* section:

- **D1 — Evaluation target.** The ceiling test runs against a real, external, data-driven
  application. This run also corrected a **misframing in run 1**: the vendored reference material is
  *candidate substrate* — harnesses and libraries the product may be built on — not the evaluation
  corpus. That correction promoted substrate selection into a first-class goal, so User Story 3 was
  broadened from "verify claims" to "choose the substrate," gained adopt/extend/build and licensing
  acceptance scenarios, and gained a matching assumption.
- **D2 — Authority.** Scoped kill authority. Sub-claims (the write half, either agent class, the
  decomposition axis) are individually falsifiable, and the core thesis has a real gate. Because the
  best path is not known in advance and must be proven, the success criteria are written to resist
  reinterpretation after results land: FR-006 pre-registers thresholds, FR-017 gives negative and
  ambiguous results equal prominence, FR-015 requires stating what the evidence does not support.

No markers remain. Ready for `/speckit-plan`.

**Note on the "no implementation details" item.** This passes, but it deserves an explicit note
because the item is unusually load-bearing for a discovery feature. Candidate tools are the
*subject* of this feature, so naming them would have been defensible — the spec deliberately does
not, referring instead to "a candidate runtime component," "a vendored reference repository," and
"an authoritative artifact." Which specific components get probed is a planning decision and belongs
in `plan.md`. This keeps `/speckit-plan` free to change candidates without amending the spec.

**Constitution pre-check** (informational; the binding gate is the Constitution Check in
`/speckit-plan`):

| Principle | Status |
|---|---|
| I. Contract-Derived Verification | **Satisfied and central.** FR-001 forbids any model-decided outcome; SC-002 requires 0% model-decided. FR-003 measures false success directly. |
| II / III. Topology and loop defaults | **Not applicable.** This feature emits no agent topology. |
| IV. Structural Safety Boundaries | **Satisfied for the discovery context.** FR-019 requires disposable instances for any write-capable arm; FR-020 keeps credentials out of traces; FR-022 forbids granting unneeded capability. The integration surface is explicitly out of scope, which avoids assembling the trifecta during discovery. |
| VI. Observability Is a Prerequisite | **Satisfied.** FR-002 requires named terminal conditions, per-attempt cost, turns, and full configuration capture. |
| VII. Test-First and Fixture-Backed | **Satisfied in the form available.** FR-009 requires committed fixtures with hidden seeded state; FR-006 pre-registers thresholds; FR-007 requires determinism for non-model measurements. |
| VIII. Versioned Artifacts, Earned Complexity | **Satisfied.** FR-016 requires reproducibility from committed configuration. The assumption that the harness is a durable asset while arms are disposable prevents over-building either. |

**One-feature check.** "And" is not load-bearing: the four user stories are four measurements
feeding one deliverable — a decision record that determines whether and how to write the
implementation spec. They share one harness, one corpus, and one budget.

---

## Final state — 2026-08-02, feature closed

The checklist is not re-scored. It gated the *specification*, the specification was fit for
planning, and every box above was correctly ticked at that gate. What follows is the honest
retrospective on which of those ticks did work, which one did not survive execution, and where the
outcome is recorded — because a checklist that closes without saying that is decoration.

**The binding adjudication is [`VERDICT.md`](../VERDICT.md).** It rules on all nine success
criteria: seven met, one met on its integrity half with the delivered go/no-go differing from the
one specified (SC-002), and one missed (SC-005).

**One item did not survive contact: "Feature meets measurable outcomes defined in Success
Criteria."** SC-005 requires that an engineer who did not build the harness can reproduce any
reported number from the committed configuration.

> ~~Five harnesses are committed and re-runnable, and one experiment reports gate adjudication
> byte-identical across two independent full runs — but **E5's and E6's probe scripts live in
> `/tmp` and are explicitly not committed**
> ([finding 006](../findings/006-graph-loop-primitives.md) §Reproduction), so the runtime numbers
> behind two owner decisions cannot be reproduced from the repository.~~
>
> **Correction, 2026-08-02 — the count was wrong and E5 and E6 are committed. The verdict is
> unchanged. See [`VERDICT.md`](../VERDICT.md) §SC-005, re-adjudicated.**
>
> **Eight experiments ran and produced findings** — E1, E2, E4, E5, E6, E7, E14, E15. E3 was
> absorbed into E2 and never ran as its own experiment; E8–E13 never ran. That eight, plus finding
> 002's credential probe from outside the ladder, is SC-005's denominator, and **all nine positions
> now have a committed harness**. E5's and E6's probe scripts survived in `/tmp` and were recovered
> on 2026-08-02: the committed code is what ran, not a rewrite.
>
> **SC-005 still fails, for two reasons that no further work removes.** Finding 001's target is a
> private production monorepo that is not vendored, so its queries are committed as an inspectable
> method with no reproducible numbers; finding 002's integers report which of one person's specific
> credentials authenticate. The other seven positions are re-runnable, each disclosing its own gaps.
> No independent reproduction was attempted of anything.

The corresponding requirement, FR-016, is partly met for the same reason.

**One requirement was never exercised: FR-012**, preliminary effect-classification precision. It was
scheduled into this feature under User Story 4 and the reading was never taken, so the write half of
the product remains behind a gate with no measurement against it. That is a scheduling outcome
rather than a specification defect — the requirement was testable and unambiguous, which is what
this checklist was asking.

**One assumption in the spec turned out to be false as executed.** *"Both agent classes are
measured, not one"* — only the class operating **through the running application** was measured. The
other half is E10, deferred.

**What the constitution pre-check got right and what it could not see.** Principle I's row is the
one that paid: FR-001's ban on model-decided outcomes and SC-002's 0% requirement held absolutely
across every arm of every experiment, and the adversarial checks they motivated found a real defect
on all four occasions they were run. Principle IV's row reasoned that keeping the integration
surface out of scope avoided assembling the lethal trifecta *during discovery*, and that held — but
the ceiling test then produced an architecture requirement that assembles it in the **product**
(C-15, OD-07), which no specification-quality check could have anticipated and which the production
spec now inherits.

**Ready for the production specification.**
