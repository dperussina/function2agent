# Feature Specification: Discovery and Validation

**Feature Branch**: `001-discovery-validation`

**Created**: 2026-08-02

**Status**: Draft

**Input**: User description: "Discovery and testing, looking for the best possible option to make this work the most efficiently. We'll generate a spec for that discovery, and then after we finish this testing and discovery, we'll start the spec for the actual implementation."

## Context

This feature produces **evidence and decisions, not product capability.** It exists because the
constitution forbids implementation before a spec, a plan, and a task list — and because the
research corpus closes some architectural questions but leaves others open in a way that only
measurement can settle.

The "user" throughout this specification is the **decision-maker**: the person who must choose
whether to build the product, and which of several viable options to build it on. The value
delivered is a defensible answer, produced cheaply enough that a negative answer is affordable.

A deliberate consequence: **only questions answerable before the generator exists are in scope.**
Anything that requires measuring generated output is necessarily deferred to a later feature,
because there is nothing to measure yet.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Prove or disprove the core value proposition (Priority: P1)

The decision-maker needs to know whether a small, curated set of application-specific tools makes an
agent measurably better at real tasks than a capable general agent that has only shell and search —
*before* anyone builds a pipeline to generate such tools.

**Why this priority**: This measures the **ceiling** of the product idea. If an ideal, hand-written
tool set does not beat the baseline, no amount of synthesis quality rescues the thesis, and every
other question in this specification is moot. It is also the cheapest experiment that can produce a
genuine "stop."

**Independent Test**: Stand up one real application in a disposable instance with seeded, known
state. Hand-write a small ideal tool set. Run a fixed task battery whose outcomes are checked
programmatically against the application's own observable state. Compare against a baseline agent
given at least the same budget. This delivers a go/no-go on its own and builds nothing reusable.

**Acceptance Scenarios**:

1. **Given** a running target with seeded state the arms cannot read in advance, **When** the task
   battery runs against each arm, **Then** every outcome is decided by a programmatic check of
   observable state and none is decided by a model's assessment.
2. **Given** both arms complete, **When** results are compared, **Then** task success rate, cost per
   task, and turns per task are reported for each arm, and the baseline received at least the same
   budget as the tool-equipped arm.
3. **Given** an arm reports success on a task, **When** the programmatic check disagrees, **Then** the
   attempt is recorded as a **false success** and counted separately from ordinary failure.
4. **Given** the battery contains tasks that are impossible to complete, **When** an arm claims
   success on one, **Then** that is recorded as a false success, requiring no separate correctness
   check beyond the task's known impossibility.
5. **Given** kill criteria recorded before any arm ran, **When** results fall below them, **Then**
   the recorded outcome is a plainly stated "no-go" rather than a re-interpretation.

---

### User Story 2 - Establish how much structure can be recovered from a codebase (Priority: P2)

The decision-maker needs to know whether the external operations of an arbitrary codebase can be
recovered accurately enough to build on — and therefore whether the analysis layer should be
adopted as-is, extended, or replaced.

**Why this priority**: It gates the entire analysis half of the product and determines a large
build-versus-adopt decision. It also costs nothing — no model, no running application — so it runs
first chronologically even though the ceiling test outranks it in importance.

**Independent Test**: Point the analysis at a corpus of known repositories, compare recovered
structure against an authoritative answer key, and report precision and recall. Delivers a
build/adopt/extend recommendation with no spend.

**Acceptance Scenarios**:

1. **Given** a repository whose external operations are enumerable from an authoritative artifact,
   **When** analysis runs, **Then** precision and recall for recovered operation-to-handler mappings
   are reported against that artifact.
2. **Given** operations declared in non-obvious forms (for example, declarations spanning multiple
   lines), **When** analysis runs, **Then** those cases are reported separately rather than counted
   as ordinary misses.
3. **Given** the full corpus, **When** analysis completes, **Then** per-repository coverage, runtime,
   and failure modes are recorded, and a crash on one repository does not abort the others.
4. **Given** an unchanged repository, **When** analysis is re-run, **Then** the result is identical.
5. **Given** the answer key and the analysis disagree, **When** the disagreement is adjudicated by
   hand, **Then** any error in the key itself is corrected and the corrected key is committed.

---

### User Story 3 - Choose the substrate that makes this work most efficiently (Priority: P3)

The decision-maker needs to know which of the available harnesses, libraries, and reference
implementations the product should be built **on** — and needs every load-bearing claim about each
candidate verified by direct probe rather than by its documentation, because several are documented
but unverified and at least one (model-agnosticism) is a stated product requirement.

**Why this priority**: This is the "most efficient path" question directly. Adopting a component
that turns out not to meet a requirement is among the most expensive mistakes available here, and
the alternative — building the equivalent — is a large, schedule-defining work item either way.
Individually the probes are cheap and quick, so this runs in parallel with User Story 2 despite
ranking below it in the decision chain. Finding a disqualification during discovery costs hours;
finding it during implementation costs weeks.

**Independent Test**: A set of small isolated probes, each answering exactly one question about one
candidate, each producing a written verdict with the evidence behind it. Together they yield an
adopt / extend / build recommendation per layer. Each answer also stands alone.

**Acceptance Scenarios**:

1. **Given** a component documented as supporting multiple model providers, **When** a probe drives
   it with a non-default provider, **Then** the outcome is recorded yes/no with the evidence that
   produced it.
2. **Given** a component with unverified prerequisites, **When** a probe runs it in the intended
   configuration, **Then** any blocking prerequisite is recorded as a disqualification for that use.
3. **Given** a probe fails, **Then** the failure is recorded as a disqualification for the
   requirement it tested, and is not worked around inside the probe.
4. **Given** all probes complete, **Then** every component under consideration has a recorded verdict
   per requirement, including "not tested" where that is the honest answer.
5. **Given** all verdicts are recorded, **When** the recommendation is produced, **Then** each
   architectural layer carries an **adopt / extend / build** recommendation citing the probes that
   support it, and any layer where adoption was rejected carries an estimate of what building the
   equivalent costs.
6. **Given** a candidate is adopted, **Then** the licensing and redistribution terms that apply to
   anything derived from it are recorded, because they constrain what the eventual product may ship.

---

### User Story 4 - Measure whether operation effects can be classified safely (Priority: P4)

The decision-maker needs a first real reading on whether an operation's effect — read-only,
reversible write, or irreversible — can be determined accurately enough to ever permit automated
writes.

**Why this priority**: The entire write half of the product is gated on this number, and it is
currently unmeasured on any codebase. It ranks last only because it cannot be measured properly
until the analyzer exists; a preliminary reading against a weak signal is still worth having,
because it distinguishes "plausible" from "fantasy" at no extra cost.

**Independent Test**: Label recovered operations by effect class, score against an authoritative
signal available from the target, and report precision per class. Delivers a go/no-go on pursuing
automated writes at all.

**Acceptance Scenarios**:

1. **Given** recovered operations and an authoritative effect signal, **When** labels are compared,
   **Then** precision is reported per effect class.
2. **Given** an operation that is in fact irreversible is labeled read-only or reversible, **Then**
   it is reported as a **critical misclassification** and counted separately from ordinary error.
3. **Given** measured precision falls below the threshold required to permit unattended writes,
   **Then** the recorded conclusion states that automated writes are not yet permissible, naming the
   measured number.
4. **Given** the signal used is weaker than the eventual production signal, **Then** the record says
   so and states what the number does and does not license.

---

### Edge Cases

- **The target application cannot be stood up.** Recorded as a blocked result with the blocker
  named, never a silent skip that leaves a gap in the comparison.
- **An arm exhausts its budget mid-task.** Counted as a failure, with the budget consumed recorded,
  so budget exhaustion is distinguishable from wrong answers.
- **Two arms tie within noise.** Reported as a tie, with the number of attempts and the observed
  spread stated. A tie is never rounded into a winner.
- **A task's check can be satisfied by an unintended shortcut.** The task is quarantined, redesigned,
  and any results that depended on it are invalidated and re-run.
- **The authoritative answer key is itself wrong.** Adjudicated by hand; the corrected key is
  committed with a note explaining the correction.
- **Model nondeterminism across repeated runs.** The number of attempts per task is fixed before
  running and reported alongside every model-dependent number.
- **A result is ambiguous rather than positive or negative.** Recorded as ambiguous. Ambiguity is a
  legitimate outcome and must not be resolved by preference.
- **Discovery reveals a question nobody thought to ask.** Added to the decision record as newly
  opened, rather than quietly absorbed.

## Requirements *(mandatory)*

### Functional Requirements

**Measurement integrity**

- **FR-001**: Every task outcome MUST be determined by a programmatic check against observable
  state. No outcome contributing to a reported result may be decided by a model's judgment.
- **FR-002**: The system MUST record for every attempt: outcome, the terminal condition **by name**,
  wall-clock time, number of turns, tokens consumed, and cost.
- **FR-003**: The task set MUST include tasks that cannot be completed, and the system MUST report a
  per-arm false-success rate.
- **FR-004**: Every factor MUST be held constant across arms except the single factor under test, and
  the full configuration of every run MUST be recorded with its results.
- **FR-005**: Every comparison MUST include a control given **at least** the same resource budget as
  the arm it is compared against.
- **FR-006**: Success thresholds and kill criteria MUST be recorded before any arm runs and MUST NOT
  be revised after results are visible. A revision requires a dated entry naming who changed what
  and why.
- **FR-007**: Re-running with unchanged inputs MUST produce identical results for measurements that
  do not involve a model, and MUST report observed variance across a fixed attempt count for those
  that do.
- **FR-008**: Where the target exposes an authoritative description of its own operations, ground
  truth MUST be derived from it rather than from hand transcription alone.
- **FR-009**: Task fixtures and expected outcomes MUST be committed, and any seeded state MUST NOT be
  visible to an arm in advance.

**Scope of measurement**

- **FR-010**: The system MUST measure structure-recovery accuracy against an authoritative key,
  reporting precision and recall separately.
- **FR-011**: The system MUST measure task success rate, cost, and turns for a tool-equipped arm and
  a general-purpose baseline arm over the same task set.
- **FR-012**: The system MUST measure preliminary effect-classification precision and MUST report
  critical misclassifications separately from ordinary error.
- **FR-013**: The system MUST answer each named component-viability question with a recorded verdict
  and the evidence behind it.

**Outputs**

- **FR-014**: The feature MUST produce a dated decision record that, for every open question in
  scope, either closes it with a citation to a specific measurement or records it as still open with
  the reason.
- **FR-015**: The decision record MUST state what the results **do not** license — the claims the
  evidence cannot support, including any population the corpus fails to represent.
- **FR-016**: The feature MUST produce a re-runnable harness such that an engineer other than the
  author can reproduce any reported number from a committed configuration.
- **FR-017**: Negative results, null results, and ambiguous results MUST be recorded with the same
  prominence as positive ones.
- **FR-018**: Analysis MUST operate on copies. Vendored reference repositories MUST NOT be modified
  in place.

**Safety during discovery**

- **FR-019**: Any arm holding write capability MUST operate against a disposable instance of the
  target, never a shared or production one.
- **FR-020**: Credentials used during discovery MUST be scoped to the disposable instance, revocable,
  and MUST NOT appear in any recorded trace, log, or artifact.
- **FR-021**: Per-run and total spend ceilings MUST be enforced by the harness. A run that would
  exceed a ceiling MUST halt and report rather than continue.
- **FR-022**: An arm MUST NOT be granted a capability it does not need for the task set under test;
  capability differences between arms MUST be deliberate and recorded, because they are the
  independent variable.

### Key Entities

- **Evaluation Target** — a codebase, optionally paired with a disposable running instance of the
  application it builds. Has an authoritative description of its own operations where one exists.
- **Answer Key** — the ground truth a measurement is scored against, with a recorded provenance
  (derived from an authoritative artifact, or hand-built and adjudicated).
- **Task** — a unit of work with a programmatic check that determines success without a model. Has a
  seeded precondition and an expected observable postcondition.
- **Null Task** — a task that cannot be completed, used to measure false success without needing a
  separate correctness check.
- **Experimental Arm** — one configuration under test: a capability set, a budget, and a fixed
  harness. Differs from its control in exactly one respect.
- **Run Record** — the full result of one attempt: outcome, named terminal, turns, tokens, cost,
  wall time, and the configuration that produced it.
- **Kill Criterion** — a threshold recorded before running, below which the recorded outcome is
  "stop."
- **Viability Probe** — a single yes/no question about a candidate component, with its verdict and
  evidence.
- **Decision Record** — the durable output: every in-scope question, its status, the measurement
  that closed it, and the claims the evidence does not support.

## Success Criteria *(mandatory)*

- **SC-001**: Structure-recovery precision and recall are reported at **zero** model spend.
- **SC-002**: A documented go/no-go on the core value proposition exists, in which **100%** of
  contributing task outcomes were decided programmatically and **0%** by a model's judgment.
- **SC-003**: The program completes within **one engineer-week and under $300** of model spend, or
  halts at the ceiling and reports the overrun rather than silently exceeding it.
- **SC-004**: **100%** of the open questions listed in scope are either closed with a cited
  measurement or explicitly recorded as still open with a stated reason. None is left unmentioned.
- **SC-005**: An engineer who did not build the harness can reproduce any reported number from the
  committed configuration without consulting the author.
- **SC-006**: A false-success rate is reported for every arm that ran.
- **SC-007**: Every claim in the decision record traces to a specific run record, or is explicitly
  marked as an inference rather than a measurement.
- **SC-008**: The decision record enumerates the claims the results do not support, including the
  populations the corpus does not represent.
- **SC-009**: The elapsed time from "results are in" to "the next specification can begin" is limited
  only by the decision itself — every input that decision needs is already written down.

## Assumptions

- **The decision-maker is the user.** This feature produces evidence and decisions; it ships no
  end-user capability, and its success is measured in questions closed per dollar.
- **Only pre-implementation questions are in scope.** Anything requiring measurement of *generated*
  output is deferred, because the generator does not exist. This is a hard constraint, not a
  scoping preference.
- **The existing research corpus is the input, not a subject of re-litigation.** Questions the corpus
  already closed with adequate evidence are treated as closed. This feature measures what remains
  genuinely open.
- **Vendored reference material is candidate substrate first and an analysis target second.** It is
  a set of harnesses, libraries, and reference implementations the product may be built on;
  evaluating them for that purpose is User Story 3. It is explicitly **not** the evaluation corpus
  for the ceiling test (D1), and nothing in it is modified in place (FR-018).
- **Priority ranks decision-criticality, not execution order.** The free, offline work (User Stories
  2 and 3) runs first because it costs nothing and informs how the ceiling test is set up. User
  Story 1 outranks both because it alone can retire the entire thesis.
- **Kill criteria come from the existing validation plan** unless deliberately amended before any
  run, per FR-006.
- **The harness is a durable measurement asset; the arms are disposable.** The harness must be
  re-runnable (SC-005) and will likely be reused by later features. Individual experimental arms are
  throwaway and are held to no such bar. Neither is product code, and no part of either may be
  promoted into the product without a from-scratch reimplementation under its own specification.
- **A disposable, locally-runnable instance of the target is available** without a paid third-party
  account.
- **Model provider credentials are supplied by the operator** and are subject to the spend ceilings
  in FR-021.
- **Both agent classes are measured, not one.** The choice between agents that operate *on the
  codebase* and agents that operate *through the running application* was deliberately deferred to
  this feature, so a comparison that measures only one cannot resolve it.

## Out of Scope

- **The deployment model** (self-hosted, hosted, or local-analysis-with-hosted-runtime). No
  experiment resolves this; it is a commercial decision. It remains open and must be settled before
  the implementation specification, but not here.
- **Any generated artifact's quality**, since generation does not exist yet. Measuring generated
  output requires a throwaway generator, which is deferred to a successor discovery feature rather
  than abandoned — see the amendment below.
- **The embeddable integration surface.** It is a delivery mechanism, not a thesis question, and
  exercising it during discovery would combine untrusted input, write capability, and shell access
  for no measurement benefit.
- **Multi-agent artifact trading and topology self-modification.**
- **Production-grade anything.** No availability, scale, or multi-tenancy requirement applies to a
  measurement harness.

### Amendment 2026-08-02 — memory topology and the synthesis spike

Recorded per FR-006. No threshold was revised and no result was visible for any affected
measurement when this was written; both changes are scope corrections made before the relevant
experiments ran.

**Knowledge and memory layer design is no longer wholly out of scope.** The product owner clarified
that the graph-and-loop paradigm is to be applied wherever it is most applicable, *including graph
memory*, which makes memory topology a thesis question rather than an implementation detail. What
remains out of scope is memory-layer **design**; what is now in scope is the narrow, falsifiable
question of whether graph-structured memory measurably outperforms flat memory for these agents.
Ranked as experiment E11 in [`plan.md`](./plan.md) and scheduled into the successor feature, because
it cannot be measured before a generator exists.

**Generated-artifact quality is deferred, not excluded.** The original exclusion reasoned that
generation does not exist yet, which is true and remains the constraint. But the governing goal is
empirical proof *before* the production specification, and synthesis quality is exactly what the
production specification most depends on. It therefore moves to a successor discovery feature that
builds a deliberately throwaway generator, gated on this feature's ceiling test passing.

## Resolved Decisions

Recorded here because each was a genuine fork with no defensible default, and each shapes what the
results are allowed to claim.

- **D1 — The evaluation target for the ceiling test is a real, external, data-driven application.**
  The measurement has to support a claim about *a customer's* application, and the vendored
  reference material contains no conventional data-driven web application, so a win there would
  license a much narrower claim than the decision requires.

  **The vendored reference material's primary role is different: it is candidate substrate.** These
  are harnesses, libraries, and reference implementations the product may be built *on*, and
  evaluating them is the subject of User Story 3, not a corpus exercise. Using a vendored repository
  as an *analysis target* in User Story 2 is permitted and useful — it is free, offline, and at
  least one of them publishes an authoritative description of its own operations — but it does not
  substitute for the external application in the ceiling test.

- **D2 — This discovery carries scoped kill authority.** Sub-claims can genuinely die: the write
  half of the product, either agent class, and the decomposition axis are each individually
  falsifiable, and a result below a pre-registered threshold retires that option rather than
  softening it. The core value proposition also has a real gate.

  The governing constraint is that the best path is **not known in advance and must be proven**. So
  the success criteria are written to protect against motivated reinterpretation after results
  arrive: thresholds are recorded before running (FR-006), negative and ambiguous results are
  reported with equal prominence (FR-017), and the record must state what the evidence does not
  support (FR-015).
