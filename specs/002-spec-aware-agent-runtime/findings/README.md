# Feature 002 findings — measurements taken while building

**Opened**: 2026-08-03, after Phase 2 completed.
**Feature**: `002-spec-aware-agent-runtime` ·
**Plan**: [`../plan.md`](../plan.md) ·
**Specification**: [`../spec.md`](../spec.md) ·
**Tasks**: [`../tasks.md`](../tasks.md)

This is the corpus's **second** authority namespace. The first is
[`../../001-discovery-validation/findings/`](../../001-discovery-validation/findings/), and both are
authoritative in the same sense and by the same rule: `tools/corpuscheck/config.json` classifies
`specs/*/findings/*.md` as `authority`, so `numeric-provenance` treats every figure written here as
a source of record rather than as a quotation needing one.

---

## Numbering: this namespace continues feature 001's sequence rather than restarting

Feature 001 issued 001 through 018. **Feature 002 starts at 019.** Finding numbers are unique across
the whole repository, not per feature.

Three reasons, in the order they bind:

1. **The checker already requires it.** `findings-numbering` collects every document matching
   `specs/*/findings/*.md` into one map keyed by numeric prefix, so a feature 002 document numbered
   `001` is a duplicate prefix and an **error**, not a new namespace. The rule's own docstring gives
   the reason it is an error rather than a warning: *"every citation of 'finding 008' downstream
   becomes ambiguous and stays ambiguous — nothing in the prose says which one was meant, so the
   ambiguity cannot be resolved later by reading."*
2. **This corpus cites findings by bare number.** The citation the tooling recognises is
   `finding NNN`, and that is also how the prose reads throughout `research/`, `VERDICT.md` and both
   specifications. There is no field in the citation form where a namespace could go, so a restarted
   sequence would have to be disambiguated by a convention every future author remembers — which is
   the class of safeguard this repository has already recorded as failing.
3. **A globally unique number is self-disambiguating.** Under this scheme the number names exactly
   one document anywhere in the corpus, so a citation of "finding 019" resolves without a namespace
   qualifier. ~~Under this scheme the number *is* the namespace marker: 001–018 are feature 001, 019
   and upward are feature 002. A reader who encounters "finding 019" with no surrounding context can
   tell which feature produced it.~~

   **Retired 2026-08-05 by owner decision — the uniqueness stands and the feature-partition does
   not. A number identifies a document; it never identified a feature, and this claim is what said
   otherwise.** The reason it was retired rather than patched is that it is **unsatisfiable for any
   measurement of the world taken during a later feature**, which is a standing shape rather than a
   one-off. The borderline rule below files a measurement by *what it is of*, not by when it was
   taken; a number is minted from the single corpus-wide sequence at *the moment it is written*. So
   a provider, library or benchmark measured during feature 002 gets a feature-002-era number and a
   feature 001 filing, and the partition breaks by construction. The first case is
   [finding 031](../../001-discovery-validation/findings/031-provider-state-chain-measured.md),
   which measures four commercial LLM providers and now lives in feature 001's directory. **Do not
   reinstate the partition to tidy this up**: the only repair that would restore it is renumbering
   on relocation, and a renumber invalidates every existing citation of the number — the precise
   harm `findings-numbering` exists to prevent.

   **What still holds, and it is measured rather than argued.** Prefix uniqueness is enforced
   **corpus-wide, not per directory**. Established on 2026-08-05 by planting
   `specs/001-discovery-validation/findings/031-PLANT-cross-directory-duplicate.md` against the
   then-extant `specs/002-spec-aware-agent-runtime/findings/031-provider-state-chain-measured.md`
   and running `.venv/bin/python tools/check_corpus.py --check findings-numbering
   --warnings-as-errors`: **2 errors, exit 1**, `findings-duplicate` naming both paths. The plant
   was deleted and the tree returned to 0 errors. So numbers from one sequence living in two
   directories does **not** open a duplicate-number hole, and reasons 1 and 2 above are untouched.
   The consequence for reading the tree: feature 001's directory holds 001–018 **and 031**, and the
   sentence above about what each feature *issued* describes issuance, not directory contents.

**How a citation disambiguates, and the convention that goes with it.** Cite the number and link the
file, exactly as feature 001 does — `[finding 019](./019-phase-2-defect-density.md)` from inside this
directory, and
`[finding 019](../002-spec-aware-agent-runtime/findings/019-phase-2-defect-density.md)` or the
equivalent relative path from outside it. The number resolves on its own; the link states the owning
feature without the reader having to know the ranges.

**The cost of this choice, stated because it is real.** A single sequence means a new finding needs
the repository-wide high-water mark, not this directory's. Two features filing on the same day can
collide. The mitigation is the one feature 001 already uses and this namespace inherits: every
finding opens with a **numbering note** recording that the identifier was checked free across the
whole tree before the file was created. It is a convention, not a mechanism — the duplicate is caught
after the fact by `findings-numbering`, never before.

## What belongs here, and what belongs in feature 001

The two directories are not "old" and "new". They hold different kinds of measurement, and the
distinction is the thing to get right:

| | feature 001 `findings/` | feature 002 `findings/` (here) |
|---|---|---|
| What is measured | the world the product must work in — model providers, code graphs, agent loops, contract extraction, a ceiling on achievable task success | **this project's own output and its own process** — what the build produced, how it behaved, what it cost |
| Typical subject | an external system, a vendored corpus, a hypothesis from the experiment ladder | a phase's source, a shipped mechanism, a harness this repository wrote |
| What a figure licenses | a claim about feasibility, or about what a design may assume | a claim about this codebase, or about how the remaining work should be sized |
| Whether it can be re-run | usually yes, often at a stated model spend | usually yes, usually at `$0.0000`, against the working tree or a named commit |

**The rule that decides a borderline case.** Ask what the measurement is *of*. A measurement of
something outside this repository — a provider, a library, a benchmark, a corpus we did not write —
belongs in feature 001, whatever date it was taken on, because feature 001 is where this corpus's
model of the world lives. A measurement of something this repository produced belongs here.

**Feature 001 is closed to new findings and its documents are not.** Nothing forbids correcting or
extending an existing feature 001 finding; what does not happen is a *new* feature 001 finding
about production work.

## Two properties of this directory that follow from the tooling

**Everything written here is self-certifying, and that is what an authority namespace means.**
`numeric-provenance` does not run on `authority` documents — they *are* the provenance. A figure
invented here will pass every check and can then be quoted anywhere in the corpus. The obligation
that replaces the check is the one feature 001's findings discharge in prose: state the method, state
the population, and give a reproduction command that a reader can run.

**Opening a second namespace widened the accept surface for every consumer document in the corpus,
including feature 001's.** The provenance lookup concatenates *all* authority documents into one text
and asks whether a quoted figure occurs in it, with no test that the finding and the claim belong to
the same feature. So a figure measured here can now silently supply provenance for a sentence about
feature 001's validation work, and the reverse. Nothing in the tooling will notice. The mitigation is
the citation convention above — quote a finding by number **and** link it, so a reader can see which
namespace the number came from even where the checker cannot.

## Supersession here is visible from inside the document it supersedes, so the kind is not named

[Feature 001's index](../../001-discovery-validation/findings/README.md) names, for each superseded
finding, whether it was **overtaken by later work** or **self-corrected by its own author**. That
split earns its place there because feature 001 holds a case nothing else reaches:
[finding 016](../../001-discovery-validation/findings/016-provider-sdk-roundtrip.md) carries no
strike, no correction and no forward reference, while
[finding 030](./030-provider-state-chain-derived-not-measured.md) records that its arms have no
persistence boundary at all and
[finding 031](../../001-discovery-validation/findings/031-provider-state-chain-measured.md) measured
the question it was read as answering. A reader inside 016 cannot tell.

**This directory holds no counterpart, measured 2026-08-11 over the eighteen documents it then held,
and the split is declined here on that measurement rather than on taste.** Every supersession that
reaches a feature 002 finding is disclosed in the finding itself. The eight carriers above disclose in
place by construction, and each supersession arriving from outside is recorded at its target: `024`'s
derived pair cells by a dated note naming
[finding 025](./025-preflight-unshare-pair-measured.md), `030`'s load-bearing negative by a
`SUPERSEDED IN PART` banner naming finding 031, `027`'s §5 platform ambiguity by the note
[finding 034](./034-removal-proof-skip-collapse-and-toolchain-degradation.md) amended into it, and
`019`'s headline rate by the strike under its own `## The headline` that
[finding 020](./020-phase-2-defect-density-adjudicated.md) adjudicated. The ten documents carrying no
in-place marker carry no inbound supersession either;
[033](./033-session-table-wal-race-unreachable-and-owed-to-migration.md) is the nearest case and
records the later owner ruling **as confirming it**, unstruck and on purpose. So naming the kind here
would add a column that changes no reader's reach, which is the whole of what feature 001's split
buys.

**One row is a live instance of the harm the paragraph under `## Index` names, and it is recorded here
rather than repaired.** `029`'s row states *"FR-005's wall-clock ceiling does not fire"* and *"The
ceiling is reachable **only by crashing**"*. Both were true on 2026-08-05 and both were discharged the
same day by that document's own block: the numerator landed, and 7 of 7 arms now terminate on the
dimension where 3 of 7 did. Restating a finding's current authority in a row is an owner call rather
than an index edit, so the row stands and this sentence is what a reader meets first.

## Index

The table below carries one row per finding filed in this directory. There are eighteen; the
corpus-wide total across both namespaces is stated in the root
[`README.md`](../../../README.md), which is where `inventory-count`'s `findings` rule reads it.

**The sequence skips `031` and that is not a gap in this index.** Finding 031 was minted from the
same corpus-wide sequence and filed in feature 001's directory, because the borderline rule above
files a measurement by what it is *of* — see
[Numbering](#numbering-this-namespace-continues-feature-001s-sequence-rather-than-restarting) for
why the number never identified a feature.

~~**Six of the eighteen carry a dated in-place supersession, and two of those six supersede their own
headline.**~~ **Eight of the eighteen carry a dated in-place supersession, and two of the eight
supersede their own headline** *(recounted 2026-08-11 over the eighteen documents this directory then
held; the earlier six was low by two)*. A row that restated an original claim where the document has
since struck it would
propagate a retracted claim out of an authority namespace, so where the two disagree the row below
states the current text and says that it superseded something. `019` and `030` are the two: `019`'s
headline is struck under its own `## The headline`, and `030`'s load-bearing negative is marked
DISCHARGED. **`019`'s own title still states the superseded rate**, which is the sharpest reason not
to build an index out of titles.

**The eight are `019`, `023`, `024`, `026`, `027`, `029`, `030` and `036`, and the two the earlier
count missed were missed for one reason: neither strikes the words it supersedes.** `029` carries a
dated `⚠️ BOTH DISCHARGED 2026-08-05` block that retracts its own premise for asking
[§8](./029-wall-clock-ceiling-unenforced.md)'s first question and rescopes §6's framing of the
crash-only route, and `036` carries a `Superseded in part 2026-08-11` note beneath a struck
limitation. `027`'s marker is a strike spanning a line boundary, so a reading of this directory taken
one line at a time reports seven rather than eight.

| Finding | Subject | Spend |
|---|---|---|
| [019](./019-phase-2-defect-density.md) | Phase 2's defect density — this project's first calibration anchor for its own output, and the denominator question it raises about itself. **Its headline is struck by its own text**: five defects at about one per 467 is superseded by six in the same 2,337 lines, about one per 389, after two were re-attributed to Phase 1 and three more were added. The document keeps the paragraph as written because the reasoning below it is unaffected | `$0.0000` |
| [020](./020-phase-2-defect-density-adjudicated.md) | The Phase 2 defect count does not survive adjudication: seven defects, not five, two of the recorded five belong to Phase 1, and four Phase 2 defects are still present. The durable artifact is the severity bar, written and committed **before** 019 was opened and before the sources were read | `$0.0000` |
| [021](./021-openat2-audit-gap-and-two-authority-gaps.md) | `openat2` is an audit gap and not an authority gap, and the search for it found two authority gaps that are not syscall-shaped. Three options are costed at the end without a recommendation; no watch set, path map or flags map was changed | `$0.0000` |
| [022](./022-e7-tool-result-truncation-cap.md) | E7's shell baseline never inlined bulk output: every tool result in both arms was capped at 6,000 characters, and no uncapped baseline can be reconstructed from the corpus. Two register premises are corrected and three counts restated; the conclusions those premises support are unchanged | `$0.0000` |
| [023](./023-user-namespace-privilege-model.md) | The user namespace works for all three mechanisms, the doubted one was never at risk, and the namespace on its own closes neither authority gap it was chosen to close. Carries a dated correction that is explicitly *"a label, not a result. Every measurement in this document stands"*, and one struck line of reasoning about who must hold `CAP_SETUID` | `$0.0000` |
| [024](./024-deployment-surface-permission-census.md) | The self-hosted commitment survives, because the choice was never default-profile-versus-unconfined; a custom profile buys the namespace for one added syscall, and the mechanism that looked most at risk was never blocked at all. Its *"the unconstructible LSM layer is carried with all four"* is struck and rescoped to what **this host** could not construct — the contradiction that later argued for, and was refused by, a scope-qualifier check | `$0.0000` |
| [025](./025-preflight-unshare-pair-measured.md) | T206's seccomp cell is measured, and so is the misreport it replaced: the pre-T206 check returns a byte-identical green string on a refusing host and a permitting one. The operator-trap arm reports green, correctly about `unshare`, on a configuration where the containment step is still refused — so **the check set, not the check, is what has the gap** | `$0.0000` |
| [026](./026-pivot-root-check-measured.md) | The `pivot_root` check, measured: four of its five cells against real container arms, its `EPERM` disambiguation controlled by removing the filter rather than by reasoning about it, and one correction to the defect's own description — the pre-T207 preflight is green on **every FR-048 check** rather than *wholly* green. Three claims are superseded in place on 2026-08-05, including a table row that collapsed `EINVAL` and a prediction that a CI run then overtook | `$0.0000` |
| [027](./027-lifecycle-edge-set-divergence.md) | `data-model.md` §2.1 declares no `RUNNING → TERMINATED` edge because it declares no `TERMINATED` state: ten branches out of `RUNNING` named by terminal state, three taxonomy members the runtime already reaches absent from them, two declared names absent from the taxonomy, and `attach()`'s refusal citing a §2.1 property that holds only vacuously. Its own reserved decision number is struck as *"the reservation's sharpest failure"* | `$0.0000` |
| [028](./028-od24-deferral-re-examination.md) | `OD-24`'s deferral survives, but only one of its two stated grounds does: the first is untouched, the second is *spent* rather than falsified, and the `newuidmap` route the decision offers as its least-authority option is measured here for the first time and is the **most**-authority option of the three | `$0.0000` |
| [029](./029-wall-clock-ceiling-unenforced.md) | FR-005's wall-clock ceiling does not fire, measured against three controls that do — and the claim commissioning the pass **breaks at its conclusion**: the constitutional wall-time term is *supplied* by FR-005 and *unmet* by the runtime, a different defect with a different owner from the "unsupplied" one alleged. The ceiling is reachable **only by crashing** | `$0.0000` |
| [030](./030-provider-state-chain-derived-not-measured.md) | The per-turn opaque-state chain landed on four determinations, none of them measured at the time, and finding 016 is no evidence about chain length because its arms have no persistence boundary at all. **Its load-bearing negative is struck and marked DISCHARGED 2026-08-05** by [finding 031](../../001-discovery-validation/findings/031-provider-state-chain-measured.md) — eight requests, four providers × two withholding conditions — and the narrower xAI prediction it had left standing *"fails too"* | `$0.0000` |
| [032](./032-removal-proof-signal-fabrication.md) | The removal-proof harness scored a **killed** arm as `proved`, so a hang bought a green tick — established by planting an arm that signals its own process, not inferred. Ten archives audited, **exactly one fabricated entry**, and the audit **cannot be completed** because archiving began after the route was already as old as `proof()`. An earlier pass's *"all twelve proved first run"* is **true as recorded and false as meant** | `$0.0000` |
| [033](./033-session-table-wal-race-unreachable-and-owed-to-migration.md) | The WAL first-open race and the engine-exception leak both exist at `SessionTable`, measured; the race is **unreachable by current usage and by nothing else**, and the leak is **not owed a local repair** because obligation 2's own scanner exempts the file as a known migration. The load-bearing result is negative — the correct repair is the migration onto `Repository`. A later owner ruling is recorded in the document as **confirming** it, and its sentences are deliberately left unstruck | `$0.0000` |
| [034](./034-removal-proof-skip-collapse-and-toolchain-degradation.md) | Two more green runs over proofs that never ran, both **confirmed by planting**: `baseline_py` collapsed every unreadable baseline line into `SKIPPED`, the one outcome where a lost arm is invisible, and a missing Go toolchain silently deleted **12 of 222** arms while the harness exited **0**. The lost arm and the legitimate skip **were** distinguishable, in the baseline text the classifier was discarding. The relayed *mechanism* for the first route is **false and committed** | `$0.0000` |
| [035](./035-orphaned-supervisor-children-and-the-reaper-that-was-never-the-mechanism.md) | The orphans came from **one unguarded spawn site**, not from `LeaseRenewer` and not from the basetemp reaper. Two of the three relayed consequences are **false, measured** — a live orphan does not make its tree unreapable, and it cannot write into a recycled live run's directory. The third, that nothing was looking, is **true**, and was the only one worth a repair | `$0.0000` |
| [036](./036-the-instrument-absent-from-the-list-of-instruments.md) | The sixth gate was **not** invisible to CI: CI ran it, CI failed on it, and CI failed on nothing else for three consecutive runs while every pass reported "all five gates green". The briefing's premise that CI was green is **false, measured**. What was missing was the *list* — nothing in the repository had the job of noticing that the list and the set had come apart | `$0.0000` |
| [037](./037-the-contract-stage-with-no-gate-stage.md) | The egress contract numbers **eight** request-pipeline stages and the enforcement point registers **six gate stages and one final stage**. The stage with no counterpart is stage 4, the address class, and its absence is **sound only because FR-016 pins exactly one address** — a conditional nobody had written down, so a future widening of FR-016 would open a hole no test named | `$0.0000` |
