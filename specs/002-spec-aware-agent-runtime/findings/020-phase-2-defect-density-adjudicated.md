# Finding 020 — the Phase 2 defect count does not survive adjudication: seven defects, not five, two of the recorded five belong to Phase 1, and four Phase 2 defects are still present

**Date**: 2026-08-04
**Feature**: 002. Adjudicates
[finding 019](./019-phase-2-defect-density.md), which recorded the count this document re-derives.
**User Story**: none. Like 019, this measures the project's own output rather than any product
behaviour.
**Owner decision**: none is changed. As in 019, no row in [`tasks.md`](../tasks.md) multiplies a
line count by a defect density, so a corrected rate invalidates no arithmetic. What it does
invalidate is a *classification*, and that is corrected in `tasks.md` and recorded below.
**Model spend**: **$0.0000.** No model was called and no credential was read. One network request
was made — to `docs.kernel.org`, to confirm the cgroup v2 documentation quoted below — and one local
container was run, unprivileged and read-only, to confirm the same fact empirically. Both are
reproduced at the end.
**Method**: a severity bar was written and committed to this file **before** finding 019 was opened
and before the Phase 2 sources were read. The sources were then reviewed against that bar. Only
afterwards was 019 read and the two lists reconciled. The ordering is the whole point of the
exercise and its weaknesses are stated in
[What this does not establish](#what-this-does-not-establish).

Numbering note: `019` was the high-water mark across both namespaces, checked by ripgrep over
`*.md` with `--hidden` before this file was created. `020` was free.

**BAR SECTION WRITTEN FIRST — the rest of this file was written after.** The section
[The bar, written before any defect was looked at](#the-bar-written-before-any-defect-was-looked-at)
below was committed to this file before finding 019 was opened and before the Phase 2 sources were
read for defects. Everything after it postdates that reading. **The title above was also written
after**, because a title written first would have had to guess the result.

---

> ## Read this first: four Phase 2 defects are still present, and one of them looks like it breaks CI
>
> This adjudication went looking for a number and found live defects, which is the more valuable
> result and is therefore stated before the arithmetic. The four are tabulated in
> [Still present](#still-present-and-this-is-the-part-that-matters-most). The one that should be
> looked at today:
>
> **`_check_cgroup_kill` looks for `cgroup.kill` in the root cgroup, where the kernel never puts
> it.** The kernel's own documentation says the file "exists in non-root cgroups". `preflight()`
> raises on any failing check and has no degraded mode, and `.github/workflows/ci.yml` runs
> `python -m src.supervisor.preflight` as a gating step on a bare `ubuntu-latest` runner. On a bare
> Linux host that check cannot pass. It passes on a developer's Docker Desktop VM only because a
> container gets a private cgroup namespace, in which the namespace root *is* a non-root cgroup —
> confirmed by running it both ways on `6.12.76-linuxkit`, the exact kernel `preflight.py`'s own
> comment names as the local one. The accompanying test asserts the check's `requirement` string and
> that its message contains the word `fork`; it never asserts `ok` in either direction, so nothing
> catches this.
>
> I could not run GitHub Actions and so cannot state as fact that CI is red. The evidence chain is
> in [Still present](#still-present-and-this-is-the-part-that-matters-most) and the one-line
> confirmation is in [Reproduction](#reproduction).

## The headline

**Seven defects, against the 6,290 lines commit `34e33d3` added — about one per 898.** The recorded
figure was five, and the count does not survive for three separate reasons, each of which moves it
in a different direction:

- **Two of the recorded five were introduced by Phase 1, not Phase 2.** The redaction marker and the
  self-overwriting benchmark were both authored in `d1f7d7a`; `34e33d3` *fixed* them. They are real
  defects and they are not Phase 2's production. This is checkable with `git log -S` and is a
  factual correction, not a judgement.
- **Four Phase 2 defects are still present** and were found by this pass, against a suite that is
  green. Together with a fifth still-present defect attributed to Phase 1, that is five live items no
  task in `tasks.md` owns.
- **A sixth defect the pass fixed is absent from the recorded five** — the `cgroup.kill` silent
  fallback, named in the commit's own message and belonging to Phase 1 rather than to this rate.

Restated over the narrower population 019 used, and with the same bar: **six defects in the 2,337
lines of new Python source — about one per 389**, against 019's one per 467. **The count is not
merely different; it is denser, on the population 019 chose, after removing two of its five.**

**The direction of 019's headline survives and strengthens. Its central explanation does not.** The
two-rate split argues that kernel-mechanism code is roughly six times cleaner because it fails
loudly at a named errno. Two defects in this same commit are in kernel-mechanism code and **neither
failed loudly**: a `cgroup.kill` fallback that silently degraded to a racy per-pid loop, and a
preflight check that looks in the wrong place and whose test cannot tell. See
[The two-rate split has counterexamples in its own commit](#the-two-rate-split-has-counterexamples-in-its-own-commit).

## The bar, written before any defect was looked at

This section fixes what counts as a defect **for the purpose of a defect-density anchor**, which is
a narrower question than "what is wrong with this code". The anchor exists to be cited when
reasoning about how much work remains, so the quantity it has to estimate is **the rate at which
this implementer introduces departures from obligations that were already binding**, per unit of
code authored.

### The core rule

> A **defect** is a discrete, attributable departure — in an artifact this phase authored or
> modified — from an obligation that was **already binding on the phase when the artifact was
> written**. An obligation is binding when it is stated in `spec.md`, in `plan.md` or `tasks.md`,
> in the constitution, or in a contract under `contracts/`; or when it is a correctness property of
> the language or platform the code itself depends on; or when it is the **declared purpose of the
> artifact itself**.

The third clause of the last sentence is the one that does the work in the hard cases below, and it
is stated up front rather than smuggled in: an artifact whose only reason to exist is to detect
something, and which cannot detect it, has departed from an obligation whether or not any external
document names that obligation.

### No severity floor, and why not

The recorded anchor has no severity bar. I am not supplying one, and that is a deliberate choice
rather than an omission. A floor invented here would be uncalibrated — nothing in this corpus
estimates the severity distribution of implementation defects — and an uncalibrated floor is
precisely the invented-threshold failure this project catches elsewhere (FR-045's refusal to
pre-register a share; FR-041's refusal to inherit a threshold).

Instead: **every item is labelled with its severity and its liveness, and the count is reported
without a floor.** A reader who wants a floor can apply one to the table and recompute. A count
behind an unstated floor cannot be recomputed by anyone, which is the failure this adjudication
exists to remove.

### The boundary cases, decided in advance

| # | Case | Decision | Why |
|---|---|---|---|
| B1 | A **missing test** | **Counts**, where a test was owed | Constitution Principle VII is NON-NEGOTIABLE and makes tests an obligation. FR-055 names a committed determinism test in the requirement text. A test that was owed and is absent is a departure from a binding obligation, exactly as wrong behaviour is. A test that merely *could* have existed does not count |
| B2 | An **instrument that could not have detected its own failure** — a test with no positive control, a benchmark overwriting its own baseline, a removal proof whose tamper matches nothing | **Counts**, at the same weight as wrong behaviour | The artifact's declared purpose is detection. An instrument that passes because it cannot fail is not a weak instrument, it is a wrong one, and it is worse than a missing one because a missing instrument announces itself. This is the corpus's own recorded class — *a safeguard that can no longer trigger reads exactly like one that has been satisfied* — and constitution Principle I's v1.1.0 amendment is the same argument for verifiers |
| B3 | A **correct-but-useless artifact** — the redaction marker that is safe but does not say which credential it stood for | **Counts**, where the artifact fails its own declared purpose, and **not** merely where a reviewer can imagine a better one | The redaction case fails two obligations at once, which is why it is the clean example: FR-036 is satisfied (no secret value in the trace) and FR-038 is not (the span must support attribution). Safe-and-purposeless is a departure from the purpose clause of the core rule. The limit is real: I will not count an artifact because it could be nicer, only where the artifact's stated job is not done |
| B4 | A **latent defect on a path no current caller exercises** | **Counts**, and is labelled `latent` | The anchor estimates defects *introduced*, not defects *observed*. Reachability is a property of today's caller set, which changes without anyone touching the defect; a count that moves when an unrelated caller is added is not a property of the phase. The cost of this choice is that dead code inflates the count, so liveness is a column rather than a filter |
| B5 | A defect **found and fixed inside the same authoring pass** | **Counts** | This is the choice that decides what the anchor *is*. Counting them makes it a **production rate** — how often this implementer goes wrong. Excluding them makes it an **escape rate** — how often something survives to review. Both are legitimate and they are different quantities over different populations, and the corpus's own rule (**U-49**) forbids merging them. The anchor is cited to predict remaining work, and remaining work is driven by how often the implementer goes wrong, not by how good its own second reading was. So: production rate, stated as such |

### Two counting rules that move the number more than any judgement above

**Unit of count — one defect is one wrong decision, not one wrong line and not one occurrence.**
Where a single root cause produced *N* mechanically identical instances, that is **one** defect.
Thirteen strings that rotted because one shared mechanism let them rot is one defect, not thirteen.
Conversely, two independent wrong decisions inside one function are two defects even if one edit
repairs both. This is stated before the count because it is the largest single lever on it.

**This boundary is not fully decidable, and I am saying so rather than dressing it up.** "One
decision or two" has no mechanical test. My rule where it is genuinely unclear is: **count as one,
and record the alternative split in the item**, so a reader who disagrees can recompute rather than
having to re-audit. That is an honest arbitrary line, chosen in the direction that makes the count
smaller — the conservative direction for an audit whose stated risk is confirming a number it went
looking to confirm.

### What does not count

- Style, naming, comment density, formatting, and anything a linter would call a preference.
- A design a reviewer would have made differently with **no binding obligation** behind the
  difference. Constitution Principle VIII makes *unjustified structure* a review defect, so an
  unjustified new layer would count; "I would have used a dataclass" would not.
- An obligation that **post-dates the phase**. A requirement written after the commit cannot be a
  departure by the commit.
- Anything in an artifact the phase neither authored nor modified.
- A **known and recorded** limitation that the phase states, prices, and defers with an owner
  decision behind it. A deferral recorded as a deferral is a decision, not a defect; a deferral
  recorded nowhere is a defect.

### Whether the bar moved after I saw the defects

Recorded here because an adjudication that silently retunes its bar has adjudicated nothing.

Answer given after the independent pass: see
[Did the bar move](#did-the-bar-move-asked-because-the-answer-is-not-automatically-no).

---

## The population, and the one thing the bar decides that nothing else does

The bar's core rule requires a defect to be a departure "in an artifact this phase authored or
modified" from an obligation "already binding on the phase **when the artifact was written**". Those
two clauses together decide the population, and they turn out to be the highest-leverage thing in
this whole document — higher than any severity judgement.

**Population P — the one this rate is over.** Every line commit `34e33d3` added, anywhere in the
repository: **6,290 lines across 48 files**, of which `src/` is 3,073, `tests/` is 3,162 and the
remaining 55 are `.github/workflows/ci.yml`, `.gitignore` and `tasks.md`. Counting rule: the `added`
column of `git show --numstat --format= 34e33d3`, summed over every text file, no exclusions.
Deleted lines (121) are not in it.

**The numerator is the defects that commit introduced into those lines.** Not the defects it
touched, not the defects it fixed. That is what makes numerator and denominator one population, and
it is the clause that removes two of 019's five.

**Why "introduced by", and not "fixed by".** The anchor's job is to predict how much review the
*next* phase of this project's own output will need. That is a production rate: departures per unit
of code authored. A defect written in Phase 1 and repaired in Phase 2 is evidence about Phase 1's
production and about Phase 2's *review*, and putting it in Phase 2's numerator measures neither.
Phase 2 gets no credit for the fix in this figure and takes no blame for the defect — both are true
and both are the point.

**This is decidable mechanically, which is unusual here.** `git log -S'<the introducing text>' --
<file>` names the commit that wrote the line. Every attribution below was made that way and the
commands are in [Reproduction](#reproduction).

## The independent list

Severity is mine and is not a filter — the bar declines to set a floor, so every item is listed and
labelled. `Live` means present in the working tree at the time of writing.

### Phase 2's own — the seven

| # | Defect | Site | Live | Severity | Class |
|---|---|---|---|---|---|
| P1 | **A non-reentrant lock.** `transaction()` holds the lock across the writes inside it, so a plain `Lock` deadlocks the moment a caller writes two rows in one transaction — the shape every ref move has | `src/contracts/repository.py`, the `RLock` and the comment above it | fixed in-pass | high | concurrency, silent until a nesting occurs |
| P2 | **A rollback split across two transactions.** The restoration record and the ref move committed separately, so a crash between them left a ref moved with no history entry | `src/analysis/rollback.py`, now one transaction | fixed in-pass | high | durability |
| P3 | **A volatility scanner with no positive control.** Nothing asserted the scanner ever returns a non-empty list, so an implementation returning `[]` unconditionally passed every test in the file | `tests/contract/test_canonical_determinism.py` | fixed in-pass | high | instrument that cannot fail |
| P4 | **The `cgroup.kill` preflight check reads the root cgroup**, where the kernel documents the file as absent, so it cannot pass on a bare Linux host; and its test asserts only the message text, so nothing catches that | `src/supervisor/preflight.py`, `tests/unit/test_kernel_floor.py` | **live** | **high** | wrong behaviour **and** an instrument that cannot fail |
| P5 | **Span position uniqueness lives in process memory, not in the store.** `SpanWriter` guards `(session, turn, ordinal)` with a per-instance Python set and the table carries no unique index, so two writers over one repository write the same position with no error, a resumed session re-issues ordinals from zero, and a failed insert permanently burns a position | `src/runtime/trace.py` | **live** | **high** | storage; FR-038's total-ordering clause is not held by the data |
| P6 | **The budget journal's location check is opt-in.** `BudgetJournal.__init__` calls `assert_outside_session_root` only when both optional arguments are supplied, and both default to `None`, so the default construction skips the check the module exists for | `src/runtime/trace_budget.py` | **live** | moderate-high | a declared safety property that is not enforced |
| P7 | **The trace's `Secret` refusal covers one field of six.** `_refuse_secrets` runs on `detail` only; `pre`, `post`, `decision.matched` and `transition` are unscanned, and the test named *a secret cannot be placed in a span at all* exercises `detail` three times and nothing else | `src/runtime/trace.py`, `tests/contract/test_trace_redaction.py` | **live** | low-moderate | incomplete mechanism **and** an instrument whose name overstates it |

Three fixed in the pass, four still present. **Numerator: 7. Denominator: 6,290. About one per 898.**

Restated over 019's population — the twelve Python files `34e33d3` added under `src/`, 2,337 added
lines, same counting rule — the defects *located there* are P1, P2, P3, P5, P6 and P7: **six in
2,337, about one per 389.** P4 is excluded from that figure because `preflight.py` was modified
rather than added; that is the only difference between the two rows, and both are stated so neither
is quoted without its population.

### Phase 1's, found here — not in the rate above

Real defects by the same bar, in the wrong numerator. Recorded because two of them are in 019's five
and one of them is the counterexample to its explanation.

| # | Defect | Introduced | Status |
|---|---|---|---|
| X1 | **A redaction marker that named no credential.** Safe and useless: an operator reading a redacted trace of a session that used three credentials cannot tell which one appeared where | `d1f7d7a` — `REDACTED = "<redacted:Secret>"` | fixed by `34e33d3`; **is 019's defect 4** |
| X2 | **A benchmark overwriting its own committed measurement** on every privileged run | `d1f7d7a` | fixed by `34e33d3`; **is 019's defect 5** |
| X3 | **`cgroup.kill` degrading silently to a per-pid signalling loop**, which loses exactly the fork race `cgroup.kill` exists to close, under precisely the forking workload FR-049's process bound is for | `d1f7d7a` | fixed by `34e33d3`; **absent from 019's five**, though named in the commit message |
| X4 | **Write-mode classification ignores the open flags.** `decide` classifies by syscall name, and `Attempt` carries no flags, so `openat(O_WRONLY)` against a read-only declared location is recorded as an **allow** — and `FS-002 WRITE_TO_READONLY` is unreachable despite a description asserting it "fires on the whole write set" | `d1f7d7a` | **still present** |

### Considered and rejected, with the reason

The bar asks for this explicitly, because 019's own *What this does not establish* names the absence
of a rejection record as one of its weaknesses.

| Candidate | Rejected because |
|---|---|
| `bounds.check` short-circuiting, so a session breaching memory and the process ceiling in one interval terminated as memory-bound with the other readings unrecorded | **The obligation postdates the artifact.** `bounds.py` was written in `d1f7d7a`; constitution Principle VI reached v1.3.0 in `1f5450b`, *after* it. Phase 2 is the first pass to author under the amended principle and it brought the function into compliance. Under the bar's exclusion of obligations that postdate the phase, this is neither phase's defect. It is the single largest item my bar excludes that a looser reading would count, and it is the commit message's own lead paragraph |
| Thirteen removal-proof tamper strings that had rotted, each reporting `unproven` and indistinguishable from a real gap | A genuine instrument defect by rule B2, and **one** defect by the unit-of-count rule rather than thirteen. Excluded from Phase 2's numerator because the rot accumulated across both commits as the source moved under the strings, so it is not attributable to a single phase. Flagged rather than counted |
| The RFC1918 pinned-origin exemption, and the `path_provenance` marking on filesystem decisions | Both are recorded owner decisions dated 2026-08-03, stated and priced in the source. The bar excludes a deferral or a decision recorded as one |
| `src/runtime/drift/__init__.py` claiming that declaring the package root "means INV-003's scan asserts a path that exists rather than passing silently over an absent one", when the invariant runner still reports INV-003 under *invariants that passed over nothing* | The runner discloses the vacuity in its own output on every run. A recorded limitation, not a hidden one. This is the closest call in the table and a reviewer who counts it gets eight |
| `WRITE_TO_READONLY` being dead code considered on its own | Merged into X4 rather than counted separately: one root cause — the classifier never sees the flags — produces both the unreachable rule and the wrong record. The alternative split is two, per the unit-of-count rule's instruction to record it |

## Still present, and this is the part that matters most

All four Phase 2 items and one Phase 1 item are live, and **the whole unprivileged suite passes**:
390 passed, 1 skipped, 35 deselected. Each of these sits on a path the suite does not exercise,
which is the class 019 itself identifies as the one requiring somebody to go looking.

**P4 — the preflight check that cannot pass on the platform it gates.** The chain, each link
checkable:

1. The kernel documentation for `cgroup.kill` reads: *"A write-only single value file which exists
   in non-root cgroups."*
2. `_check_cgroup_kill` tests `CGROUP2_ROOT / "cgroup.kill"`, and `CGROUP2_ROOT` is `/sys/fs/cgroup`
   — the root of whatever cgroup view the process has.
3. Confirmed empirically on `6.12.76-linuxkit`: in a container with the default private cgroup
   namespace the file is present; with `--cgroupns=host`, which is the view a process on a bare host
   has, it is absent.
4. `preflight()` raises `PreflightError` if any check fails, and the module's `__main__` exits 1.
   `.github/workflows/ci.yml` runs `python -m src.supervisor.preflight` as a gating step in the job
   that runs the entire pytest suite, on `ubuntu-latest` with no `container:` key — a bare VM.
5. `test_cgroup_kill_is_a_preflight_check` asserts `check.requirement` and that `"fork"` appears in
   `check.detail`. It never reads `check.ok`.

The correct check was five lines away: `_check_cgroup_delegation` already creates a probe child
cgroup under the root, which is exactly where `cgroup.kill` does exist. **What I could not
determine:** whether CI is actually red. I cannot run GitHub Actions from here. Step 4 is an
inference from the runner's documented shape, and it is the one link in the chain that is not
directly observed.

**P5 — two spans at one position, written.** Demonstrated, not argued: two `SpanWriter` instances
over one `Repository` — a construction the project's own test suite performs — each write a span at
`(0, 0)` and both land. `next_ordinal` on the second writer returns `0`, which is what a resumed
session does after the crash the budget journal three files away exists to survive. FR-038 asks for
"position sufficient to order every span in a session totally, without reference to a clock", and
the module docstring claims `SpanWriter` "refuses a duplicate, so two spans cannot tie". Both are
true of one writer in one process and of nothing else. Separately, `write()` records the position in
`_written` *before* the insert and never unwinds it, so a refused insert burns the position
permanently and a legitimate retry is rejected with "a span already occupies position". A unique
index on the table closes both, which is why they are counted as one defect.

**P6 — the journal accepted inside the session root.** `BudgetJournal(repo)` with no keyword
arguments creates the ledger at a path inside the session root with no complaint. The module's
opening docstring lists "journalled outside the container" as one of two properties and says
"`assert_outside_session_root` checks it". The test named
`test_the_journal_constructor_enforces_the_location` passes both arguments and so exercises only the
path where the check runs.

**P7 — the `Secret` refusal, and the test that overstates it.** A `Secret` in `decision.matched`
constructs without complaint and reaches `write()`, where it is caught by the canonical encoder as
`NonCanonicalValue` rather than by the named `SpanError`. **No credential reaches storage**, which is
why the severity is low — the outcome is fail-closed. What is wrong is the mechanism and the
instrument: the module says "Refusing it here means the credential never gets close", and it refuses
in one of six fields.

**X4 — a write recorded as an allow.** Enforcement is unaffected: the read-only bind mount is what
stops the write, and the recorder is not a permission. What is wrong is the record, and SC-022's
audit trail is the artifact this component exists to produce.

## Reconciliation with finding 019

Read only after the above was written.

| 019's item | My verdict | Kind of difference |
|---|---|---|
| 1 — non-reentrant lock | **Agree.** Counted as P1 | none |
| 2 — rollback split across two transactions | **Agree.** Counted as P2 | none |
| 3 — volatility scanner with no positive control | **Agree.** Counted as P3 | none, though I did not find it independently — see the contamination note below |
| 4 — redaction marker naming no credential | **Agree it is a defect; disagree it is Phase 2's.** Introduced in `d1f7d7a`, listed as X1 | **facts.** `git log -S` decides it |
| 5 — benchmark overwriting its own baseline | **Agree it is a defect; disagree it is Phase 2's.** Introduced in `d1f7d7a`, listed as X2 | **facts.** Same command |

**All five are real defects under my bar. Not one of them is a bar disagreement.** That is worth
stating plainly: the recorded list contains no item I would have thrown out on severity, and the bar
— the thing the exercise was really for — vindicates the implementer's judgement about what counts
completely. The count moves for a reason nobody was looking at.

**What 019 missed, and why its own method could not have caught it.** 019's stated method is that
"the defect list is the implementation pass's own, taken from `tasks.md` and re-located in the
working tree". Re-locating a defect finds where its *fix* sits. It cannot find where its *cause* was
authored, and it cannot find a defect the pass did not report. Both gaps are structural in that
method and neither is a lapse in applying it.

**The denominator problem 019 diagnosed is real but is the smaller half of the problem.** 019
correctly identifies that two of its five sit outside the 2,337 lines and restates the rate over
`src` plus `tests`. That fixes the arithmetic. It does not notice that the same two are outside the
*phase* — and once they are attributed correctly, the population mismatch mostly dissolves, because
the two defects that were in the wrong denominator were in the wrong numerator all along. **A
numerator-attribution error can masquerade as a denominator error, and restating the denominator
makes it worse, not better: it dilutes a correct numerator to accommodate two items that should have
been removed.** That is a generalisable failure and is the finding here most worth propagating.

### The two-rate split has counterexamples in its own commit

[`tasks.md`](../tasks.md) classifies work into roughly one defect per 500 lines for
storage-and-serialization and roughly one per 3,000 for "code the kernel checks for you — namespaces,
cgroups, `seccomp`, capabilities, file descriptors", and states that **all five** Phase 2 defects are
in the first class. The argument is that kernel-mechanism code fails loudly, at a named errno, on
first execution.

Two defects in this same commit contradict it directly:

- **X3, the `cgroup.kill` fallback.** Pure cgroup code. It did not fail at a syscall; it returned
  successfully having killed some of the processes, which is the definition of failing quietly.
- **P4, the preflight check.** Pure cgroup code. It reads a path, gets `False`, and reports a
  facility as absent that is present — and its test cannot tell.

The claim "all five are in the storage class" is true only of the five that were counted, and the
counting excluded the counterexamples. **The two-rate split is not merely unmeasured on its second
rate, as 019 says; it has observed counterexamples in the single phase that produced it.** That is a
stronger statement than 019's caveat and it is corrected in `tasks.md`.

### The contamination I have to declare

Independence was not perfect and pretending otherwise would defeat the exercise.

- **The commit message names defects.** `34e33d3`'s message describes the `bounds.check` ordering
  work, the `cgroup.kill` fallback, the path-provenance marking and the rotted tampers. I read it as
  part of reviewing the commit, which is legitimate, but three of my non-live items came from there
  rather than from the code.
- **One line of `tasks.md` leaked.** While grepping that file for its heading structure I saw a table
  cell reading *"the volatility-scanner defect is this class exactly"*. That is 019's defect 3. I did
  **not** find it independently from the code, and I have not claimed to. It is counted as P3 because
  my bar admits it on inspection, not because I discovered it.
- **P1 and P2 are not independent findings either.** Both were fixed inside the pass and are visible
  only as comments explaining why the code is shaped as it is. I read those comments; anyone would.
  Rule B5 counts them, so they are in.

Netting that out: of the seven Phase 2 defects, **four are genuinely independent findings** — P4, P5,
P6 and P7, all four of them live. The three fixed-in-pass items were read off the artifacts the pass
left behind.

## Did the bar move, asked because the answer is not automatically no

**The written bar did not move. One thing in it turned out to be load-bearing in a way I did not
anticipate, and one temptation was real.**

The clause that did the work was not any of the five boundary cases the brief asked about. It was the
unremarkable phrase **"already binding on the phase when the artifact was written"**, written to
handle a constitutional amendment landing mid-project. It is what removed two of the recorded five,
and I did not see that coming when I wrote it.

**The temptation, recorded honestly.** After finding that X1 and X2 belonged to Phase 1, the count
dropped to five for Phase 2 alone — the same number as the record — and there was an obvious pull to
stop there and report agreement with a better-founded composition. That is the confirmation failure
the brief warned about, arriving in the exact shape it warned about. What prevented it was that the
bar had already committed to counting latent defects (B4) and instrument defects (B2) without a
severity floor, so P4 through P7 had to be counted once found. **Had I written a severity floor, or
excluded latent defects, I would have reported five and called it agreement.** That is the strongest
argument in this document for writing the bar first.

**Where I applied the bar and remain unsure.** The `drift/__init__.py` vacuity call in the rejection
table, and the choice to merge two root causes into one item in each of P4, P5 and X4. Both are
recorded so a reader can recompute. A reviewer who splits all three and counts the drift stub gets
eleven rather than seven.

## What this does not establish

- **This is a second opinion, not a measurement.** Two reviewers applying judgement to the same code
  and arriving at nearby numbers is weak evidence, and it is not much strengthened by the second one
  having written its bar down. The bar reduces the variance a *third* reviewer would add; it does
  not make the count objective. See [What would make this a measurement](#what-would-make-this-a-measurement).
- **It does not establish that seven is the number.** It establishes that five was not, and that a
  stated bar plus mechanical attribution moves the count by more than severity judgement does. The
  residue is unbounded in the same way 019's was: four live defects were found in a pass of a few
  hours by one reviewer who had never seen this code, which is direct evidence that a longer pass
  finds more.
- **It does not establish the direction of the two-rate split, only that its stated support is
  contradicted.** Two kernel-mechanism counterexamples do not show kernel code is *not* cleaner. They
  show the phase that was cited as evidence for the claim contains evidence against it.
- **P4's effect on CI is inferred, not observed.** Steps 1 through 3 and 5 of the chain are directly
  checked; step 4 rests on GitHub's documented runner shape.
- **It says nothing about the correctness of the fixes.** Same caveat 019 records, for the same
  reason.
- **The line counts are added-lines, not file lengths.** 019's 2,337 happens to be both, because
  those twelve files were added whole. For a population that includes modified files the two
  measures diverge and "added lines" is the one that describes work authored.

## What would make this a measurement

Ranked by cost, and none of them is expensive relative to what the anchor is being asked to carry.

1. **A third reviewer applying this bar to the same commit, blind to both lists.** This is the
   cheapest and it is the only one that directly measures the thing in doubt: inter-rater agreement.
   Two independent applications of one written bar produce a spread. That spread *is* the error bar
   the anchor currently lacks, and without it "seven" is exactly as unfalsifiable as "five" was.
2. **Attribution by `git log -S`, made a required step rather than an available one.** It converted
   two of five, mechanically, with no judgement. It costs one command per item and it is the highest
   ratio of correction to effort in this whole exercise.
3. **A second phase counted the same way.** 019 says this and it remains true. One phase is a point;
   the anchor is being quoted as a rate.
4. **A defect ledger written as the work happens**, so discovery order and introducing commit are
   recorded at the time rather than reconstructed. Both findings state that the single-commit landing
   makes discovery order undecidable after the fact. It is only undecidable because nothing wrote it
   down.
5. **The residue estimated rather than disclaimed.** Both documents say "there may be more". A
   capture-recapture reading of two independent passes over one commit would put a number on it:
   with one overlap out of seven and five, the estimate is uncomfortable, which is the point of
   computing it. That is a genuine measurement and it needs exactly what item 1 needs.

Items 1, 2 and 4 together would make the next phase's figure a measurement. None needs a model, a
network or a container.

## Reproduction

Offline at `$0.0000`, except the two probes noted. From the repository root:

```bash
# the denominator: every line 34e33d3 added, and the split by area
git show --numstat --format= 34e33d3 | awk '
  $1 != "-" {all += $1}
  $3 ~ /^src\//   {src   += $1}
  $3 ~ /^tests\// {tests += $1}
  END {print "all added:", all; print "src:", src; print "tests:", tests}'

# 019's population, unchanged: the twelve files the commit added under src/
git diff-tree --no-commit-id --name-status -r 34e33d3 \
  | awk '$1=="A" && $2 ~ /^src\/.*\.py$/ {print $2}' | sort | xargs wc -l

# the attribution that moves the count — each names d1f7d7a, not 34e33d3
git log --oneline -S'REDACTED = "<redacted:Secret>"' -- src/contracts/secret.py
git log --oneline -S'for pid in self.live_pids()'    -- src/supervisor/cgroup.py
git log --oneline -S'WRITE_TO_READONLY'              -- src/supervisor/fs_decisions.py
git log --oneline -- tests/batteries/test_seccomp_overhead.py

# the amendment that postdates bounds.py, which is why bounds.check is not counted
git log --oneline --diff-filter=A -- src/supervisor/bounds.py   # d1f7d7a
git log --oneline -- .specify/memory/constitution.md            # 1f5450b is later

# P4, both halves. The second needs Docker and is read-only.
sed -n '/def _check_cgroup_kill/,/^$/p' src/supervisor/preflight.py
docker run --rm alpine               sh -c 'ls /sys/fs/cgroup/cgroup.kill; echo $?'
docker run --rm --cgroupns=host alpine sh -c 'ls /sys/fs/cgroup/cgroup.kill; echo $?'
# and the test that cannot tell:
sed -n '/def test_cgroup_kill_is_a_preflight_check/,/^$/p' tests/unit/test_kernel_floor.py

# P5, P6 and P7, all three demonstrated rather than argued
.venv/bin/python - <<'PY'
import pathlib, sys, tempfile
sys.path.insert(0, ".")
from src.contracts.repository import Repository
from src.contracts.secret import Secret
from src.runtime import trace
from src.runtime.trace import ArtifactVersions, Cost, DecisionFields, Span, SpanWriter
from src.runtime.trace_budget import BudgetJournal

tmp = pathlib.Path(tempfile.mkdtemp())
V = ArtifactVersions(tenant_id="t", deployment_id="d", by_kind={"bounds": "sha256:" + "0" * 64})
C = Cost(0, 0, 0.0, 0, 0, 0, 0.0, 0)
base = dict(kind=trace.MODEL_CALL, session_id="s", turn=0, ordinal=0,
            outcome=trace.OUTCOME_OK, attempt_kind=trace.ATTEMPT_FIRST,
            versions=V, cost=C, at=1.0)

repo = Repository(tmp / "a.sqlite3", role="runtime", tenant_id="t", deployment_id="d")
w1, w2 = SpanWriter(repo), SpanWriter(repo)
w1.write(Span(**base)); w2.write(Span(**base))
print("P5 positions:", [(r["turn"], r["ordinal"]) for r in w1.spans("s")],
      "next_ordinal after a fresh writer:", w2.next_ordinal("s", 0))

root = tmp / "session-root"; root.mkdir()
r2 = Repository(root / "budget.sqlite3", role="runtime", tenant_id="t", deployment_id="d")
BudgetJournal(r2)                       # no kwargs, so no location check
print("P6 journal inside the session root:", (root / "budget.sqlite3").exists())
r2.close()

s = Span(**{**base, "kind": trace.EGRESS_DECISION, "ordinal": 5,
            "decision": DecisionFields(rule_id="R", resolved_tier="t",
                                       matched={"authorization": Secret("x", name="K")})})
print("P7 constructed with a Secret outside `detail`: no SpanError")
try:
    w1.write(s)
except Exception as exc:
    print("P7 caught downstream as", type(exc).__name__, "- not the named SpanError")
repo.close()
PY

# the suite is green while all of the above is true
.venv/bin/python -m pytest tests -q -m "not privileged"
```

The kernel documentation quoted for P4 is
[Control Group v2](https://docs.kernel.org/admin-guide/cgroup-v2.html), §`cgroup.kill`.
