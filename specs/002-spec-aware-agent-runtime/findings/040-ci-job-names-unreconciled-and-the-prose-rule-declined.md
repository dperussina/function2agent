# Finding 040 — `ci.yml` declares **six** named jobs and nothing read one of those names. A job's `name:` was renamed in a scratch tree and **seven instruments stayed silent**; a seventh job appended was invisible to all of them. Renaming the mapping *key* fires the census's direction 1 and always did, so the blindness is exactly the string a human and a required status check read. The exposure in prose is **one** wrong site, not six — `tools/instruments.py` said *"all five jobs"* while **six** use the action — and on that one site the **prose rule is declined**: 34 candidate lines, **1** real defect, and **4** firings on dated readings that must stay frozen. The **reconciliation is built**, as a fourth direction over a second population

**Date**: 2026-08-11
**Feature**: 002. Measures [`.github/workflows/ci.yml`](../../../.github/workflows/ci.yml)'s job set
against every site in the repository that counts or names a CI job, and against the gate set as it
stood at `8d74942`.
**Reports, and repairs the one defect in §2.** The repair is a note in
[`tools/instruments.py`](../../../tools/instruments.py) that stated a count; it is replaced by a
condition direction 4 checks, so the sentence cannot go stale in the same way twice.
**User Story**: none directly. Prompted by a brief that carried *"all five jobs are in
`tools/README.md`"* — wrong twice, six rather than five and one named rather than all — which is the
same shape as the five-item list of gates that
[finding 036](./036-the-instrument-absent-from-the-list-of-instruments.md) is about, one level out.
**Owner decision**: **none is minted here and no register was edited.** §3 declines a rule and §4
builds a different one; both are measurement results rather than owner rulings.
**Model spend**: **$0.0000.** No model was called and no credential was read. Text reads of the
workflow, `git grep` over the corpus, and repeated runs of the gate set against a detached worktree.
**Method**: **planted, not inferred.** Three perturbations were applied to `ci.yml` in a detached
worktree at `8d74942` and the whole gate set was run against each. §1 names every instrument run and
what each said. Nothing in this document rests on reading a checker's source and concluding it cannot
see something.
**Reproduction**: every command is given in the section that uses it. The measured tree is
`8d74942`; the plants run against a clean detached worktree of it and cost under two minutes each.
**Numbering note**: `039` was the high-water mark across `specs/*/findings/`, established two ways
and **no "next free number" written in any other document was consulted or trusted**. (1) The numeric
prefix of every file matching `specs/*/findings/[0-9]*.md`: max `039`, over 39 numbered documents in
two directories. (2) A corpus-wide match-only citation search of the `finding NNN` form, taken before
sorting so that ripgrep's path-ordered output cannot be mistaken for a value order: max `039`. `040`
was free at that moment and re-checked free immediately before saving.

---

> ## THE RESULT IN ONE PARAGRAPH
>
> `ci.yml` declares six jobs and each carries two names: the mapping key under `jobs:`, and a `name:`
> value. They are different strings with different audiences — the key is what `needs:` and every
> `job=` field in the instrument census point at; the name is what a run page shows, what
> `gh run view` reports per job, and what a required status check is matched on. **`instruments.py`
> has always read the key and nothing has ever read the name.** Planted at `8d74942`: renaming
> `go`'s `name:` left **seven instruments silent** — `check_corpus.py` 0 errors 0 warnings,
> `gen_claims.py --check` 0 stale, `check_tampers.py` 346 proofs 0 errors, `tools/selftest.py` all
> passed, `instruments.py --check` census OK, `tests/invariants/runner.py` exit 0, `pytest` 1796
> passed 4 skipped. Appending a **seventh** job with a name of its own was equally invisible.
> Renaming the *key* fired direction 1 with four problems, which is what fixes the blindness at the
> `name:` field rather than at the census generally. **The prose exposure is one site**: of 34 lines
> in the repository matching a count-of-jobs phrase, 25 use *job* in an unrelated sense, 4 are dated
> readings that were true when taken and must stay frozen, 4 are correct singular references, and
> **1** is wrong — `instruments.py`'s note that the runner-identity action is *"used by all five
> jobs"*, when **six** jobs use it. So a rule scanning prose is **declined** on 1 real defect out of
> 34 firings, with 4 of those firings on sites that must never be changed. A **reconciliation** is
> built instead, on `instruments.py --check`'s own precedent: a declared job census, checked against
> `ci.yml` by key *and* by `name:`, in a population kept separate from the instrument population.

> ## WHAT THIS FINDING DOES NOT CLAIM
>
> It does **not** claim anything was broken in CI. Every job named below existed and ran; the six
> names are the workflow's own and were correct at `8d74942`. It does **not** claim a merge was ever
> gated on a stale name — this repository has **no branch protection and no rulesets**, verified, so
> nothing depends on those strings for merge gating today, and the mechanism `ci.yml` warns about is
> latent rather than live. It does **not** claim the one wrong site misled anybody: it is a comment
> in a census note, not a figure anything reads. It does **not** claim direction 4 catches a class of
> defect that has occurred; **it caught one wrong site and two planted perturbations, and that is the
> whole of its measured yield.** And it takes **no** owner decision.

---

## 1. The plant, and the seven instruments that said nothing

The six jobs `ci.yml` declares at `8d74942`, read out of the file rather than transcribed from a
brief. The extraction is a four-space-indented `name:`, which is the only indentation at which a
job's own keys sit — a step's name is `      - name:` at six:

| mapping key | `name:` value |
|---|---|
| `invariants` | `invariants (milliseconds, no model)` |
| `corpus` | `corpus gates (consistency, no model)` |
| `slug-differential` | `slugify vs GitHub's renderer (non-gating observation)` |
| `python` | `pytest (kernel mechanisms included)` |
| `removal-proofs` | `removal proofs (do the tests catch removal)` |
| `go` | `go test (the enforcement point)` |

**Six, and the workflow already knew it.** `ci.yml`'s job-duration table carries five rows and says
so in its own words — *"A sixth job exists and has no row, because one run is not a sample"* — so the
file is not the site that lost count. Nothing else was counting.

### 1.1 Plant A — rename a job's `name:`

In a detached worktree at `8d74942`, `go`'s name was changed from `go test (the enforcement point)`
to `go test (the egress enforcement point)`. One line, no key touched. The whole gate set was then
run against it:

| instrument | what it said under Plant A | verdict |
|---|---|---|
| `python -m tools.corpuscheck` | `0 error(s), 0 warning(s)` | silent |
| `python tools/gen_claims.py --check` | `39 generated claim(s); 0 stale` | silent |
| `python tools/check_tampers.py` | `346 proofs declared`, `0 errors, 0 warnings` | silent |
| `python -m tools.selftest` | `all self-tests passed` | silent |
| `python tools/instruments.py --check` | `27 instrument(s)`, `census OK` | silent |
| `python tests/invariants/runner.py` | exit 0 | silent |
| `python -m pytest tests -q -rs -m "not privileged"` | `1796 passed, 4 skipped` | silent |

**Seven of seven silent.** That is the copy-list disposition rather than a cosmetic one: the failure
produces a green bit indistinguishable from success, which is the ground the copy-list allowlist
guard was built on.

### 1.2 Plant B — rename the mapping key, which establishes where the blindness is

`\n  go:\n` → `\n  gotest:\n`, with the `name:` field untouched. `instruments.py --check` **fired**,
four problems, one per instrument declaring `job="go"`:

```
go vet: names CI job 'go', which the workflow does not define. A renamed job
detaches everything pointed at it.
```

So the census is not blind to renames in general. It is blind to precisely the string that direction
1 does not read, and the message it prints for the key case — *"A renamed job detaches everything
pointed at it"* — is a true sentence about the half it cannot see.

### 1.3 Plant C — append a seventh job

A `lint:` job with `name: shellcheck (a seventh job nobody enumerated)` was appended.
`instruments.py --check`, `check_corpus.py` and `selftest.py` were all **silent**. Nothing in the
repository counts jobs, so a job set can grow without any declaration noticing — and the one standing
count claim in the tree, §2's defect, would then have been wrong by two instead of one.

## 2. The exposure: one wrong site, three correct names, four readings that must stay frozen

The population is every line in the repository that counts or names a CI job. It was collected by
matching a number-word or digit followed by `jobs?` across every tracked file outside `examples/`,
and separately by matching each of the six literal names.

**34 lines match a count-of-jobs phrase.** They divide:

| class | count | disposition |
|---|---|---|
| a different sense of *job* entirely | 25 | *"one mechanism, two jobs"*, `Three jobs:` in a task validator, `#…-job-1b-…` section anchors. Not about CI at all |
| dated readings, true when taken | 4 | must stay frozen; see below |
| correct singular or in-context references | 4 | *"the one job that installs nothing"*, *"Three jobs finish in under a minute"* against a five-row table |
| **wrong** | **1** | §2.1 |
| **total** | **34** | |

**The four dated readings are the sharpest part of the measurement**, because a rule that fired on
them would be asking for them to be falsified. Each was taken before `slug-differential` first ran on
2026-08-10, when the job set genuinely was five:

- `ci.yml:124` — *"11 runs, 55 job observations"*, which is 11 × 5 over the excluded incident window.
- `ci.yml:128` — *"seven jobs cancelled at 901–902s"*.
- `ci.yml:135` — *"that run's five jobs were cancelled at ~902s"*.
- [`finding 026`](./026-pivot-root-check-measured.md)`:268` — *"All five jobs green"*, a reading of run
  31016201724 on 2026-08-05.

Updating any of those to *six* makes it false. This is the register-range disposition verbatim: a
rule that fires on a site which must stay frozen.

### 2.1 The one wrong site

`tools/instruments.py`, the `runner identity` census entry:

    notes="A composite action used by all five jobs; direction 1 does not "
          "apply because it is a `uses:` and not a `run:`.",

`uses: ./.github/actions/runner-identity` appears **six** times in `ci.yml`, at lines 168, 207, 342,
422, 838 and 929 — once in every job. The note is a standing claim rather than a dated reading, so
unlike the four above it is simply wrong.

**It is repaired by making it a condition rather than a count.** The note now says the action is used
by every job in the census and that direction 4 checks it, and 4d is that check. Writing *six* would
have reproduced the defect one digit later.

### 2.2 The job names, and the figure the brief was reaching for

Of the six names, at `8d74942`, established with `git grep -lF … 8d74942` excluding the workflow
itself:

| name | where it appeared outside `ci.yml` |
|---|---|
| `corpus gates (consistency, no model)` | [`tools/README.md`](../../../tools/README.md) |
| `pytest (kernel mechanisms included)` | [`finding 026`](./026-pivot-root-check-measured.md) |
| the other four | **nowhere** |

So **1 of 6** appeared in `tools/README.md` and **2 of 6** anywhere in the repository. All three
occurrences were **correct**; the gap was coverage, not accuracy. Four of the six names existed in
exactly one place in the repository, which is the workflow that defines them — and that is the state
§4 changes.

## 3. The prose rule is declined, on numbers

The candidate is a corpus check matching claims of the form *"N jobs"* and reconciling `N` against
the workflow's job count. **Declined.**

| measure | value |
|---|---|
| candidate firings across the tree | 34 |
| real defects among them | 1 |
| firings on a different sense of the word | 25 |
| firings on dated readings that must stay frozen | 4 |

The ground is **both** of the two this repository already records, in the same rule:

- **It fires almost entirely on false positives.** 1 of 34. That is a worse ratio than the
  duplicate-definition guard declined at 2 firings clean and 3 with a plant, and the false alarms
  have the same irreducible shape: nothing separates *job* meaning a CI job from *job* meaning a unit
  of work, and both appear in the same documents.
- **It fires on sites that must stay frozen.** Four dated readings, each true as taken. This is the
  register-range relaxation's exact failure — declined because it *"fires only on a false positive"*
  at a site that must not move — and here the frozen sites are 4 of the 9 CI-relevant firings.

**A scope narrowing does not rescue it**, and the reason is structural rather than a matter of
finding the right glob. The 4 frozen readings and the 1 defect are not separable by file: two of the
frozen readings are in `ci.yml`, and so is a third of the correct in-context references. A window
tight enough to exclude the frozen readings excludes the defect with them.

**What an owner would have to decide if this were reopened**: whether the one site is worth a rule
whose output a reader learns to skip. This document's answer is no, and the answer does not weaken
over time — the frozen readings accumulate rather than expire, because every dated CI observation
this repository records adds one.

## 4. What was built: direction 4, over a second population

The mechanism is a **declaration plus a reconciliation**, on `instruments.py --check`'s own
precedent, and it lives in [`tools/instruments.py`](../../../tools/instruments.py) — the file that
already parses `ci.yml` textually, already runs in the one CI job that installs nothing, and is
already standard-library-only for that reason.

`JOBS` is a tuple of `(key, name)` pairs. `reconcile_jobs()` checks four things:

| sub-direction | what it catches | fixture |
|---|---|---|
| 4a declared and absent | a declared key the workflow no longer defines | `test_a_declared_job_the_workflow_does_not_define_is_reported` |
| 4c the name disagrees | Plant A — the workflow's `name:` differs from the declaration, or the job declares no name at all | `test_a_renamed_job_name_is_reported`, `test_a_job_with_no_name_at_all_is_reported` |
| 4d no kernel on the figures | a job that does not use the runner-identity action, which is §2.1's note turned into a check | `test_a_job_that_drops_the_runner_identity_action_is_reported` |
| 4b present and undeclared | Plant C — a job in the workflow the census does not declare | `test_a_job_added_to_ci_and_missing_from_the_census_is_reported` |

Plus a **vacuity floor**: an empty declaration reconciles perfectly with any workflow, so
`reconcile_jobs` reports on it rather than returning clean. That is the same floor
`check_tampers.py` applies to zero extracted proofs.

Every branch is held by a fixture in
[`tests/unit/test_instrument_census.py`](../../../tests/unit/test_instrument_census.py) and four
carry removal proofs in [`tests/removal_proofs.sh`](../../../tests/removal_proofs.sh). The holds were
**probed rather than asserted**, as a differential over one variable — the same four nodes run
against the untampered file and against each tamper, with `PYTHONDONTWRITEBYTECODE=1` and `-B` so no
arm can read another's bytecode:

| branch tampered | untampered | tampered |
|---|---|---|
| the name comparison | exit 0 | exit 1 — held |
| present-and-undeclared | exit 0 | exit 1 — held |
| the identity action | exit 0 | exit 1 — held |
| the vacuity floor | exit 0 | exit 1 — held |

### 4.1 The two populations are kept separate, and the reason is a documented figure rather than taste

The obvious move is to add job entries to `INSTRUMENTS`. **It would break a figure this pass could
not repair.** `tools/README.md` states the instrument split as `19 + 6 + 2` and says outright that it
is *"read off `instruments.py --check` rather than counted by"* hand. Six job entries in
`INSTRUMENTS` moves that total to 33 and makes each class a mixture of two things being counted —
which is the defect this file is named after, committed inside the repair. So `JOBS` is its own
tuple, `reconcile_jobs` is its own function, and `--check` prints the two on separate lines:

```
27 instrument(s): 19 gate, 6 advisory, 2 library
6 CI job(s), reconciled by key and by `name:`
```

The instrument counts are **unchanged** at 27 / 19 / 6 / 2, verified against the clean tree after the
change. Disagreements from both populations land in one problem list, because a disagreement is a
disagreement; it is the *counts* that must not merge.

### 4.2 The fixtures are not in `tools/selftest.py`, and that is the file's own precedent

The standing rule is that a new check needs a `tools/selftest.py` fixture. `selftest.py` runs the
corpus check set against the two fixture corpora and carries **no instruments arm at all**; every
direction of this reconciliation has been held from `tests/unit/test_instrument_census.py` since
finding 036, and `tests/removal_proofs.sh` already carries a *"Finding 036 — the instrument census"*
section the four new proofs were added to. Putting a job-census arm into the corpus self-test would
be a category error and a second home for the same assertions. The deviation is recorded here rather
than left to be noticed.

## 5. Where the enumeration landed, and what it is now unable to do

The six names are now in `JOBS`, and the choice of home is the finding's smallest but least
reversible decision.

**A prose comment block listing six names — in `ci.yml` or anywhere else — is the artifact this
document is about.** It is a hand-maintained list beside a set, with nothing whose job is to notice
when they part; §1's plants measure exactly how quiet that state is. Adjacency to the source reduces
the chance a human misses it and changes nothing about what a machine sees. So the enumeration is a
*declaration under a reconciliation* rather than a comment, and it is the first arrangement in this
repository's history that cannot silently disagree with `ci.yml`.

**What §2.2's figure needs, and where it is.** The *1 of 6* and *2 of 6* readings are measurements
over the corpus at `8d74942` and they are recorded in §2.2 of this document, not in `tools/README.md`
— a concurrent pass held that file throughout this one, and a figure about a document is not owed a
home inside it.

## 6. What this does not close

**Nothing counts jobs in prose, and after this document nothing still does.** §3 declines that rule
and §4 does not build it: direction 4 reconciles a *declaration* against the workflow, so a sentence
in a research document claiming five jobs stays exactly as invisible as it was. The one such sentence
that was wrong is repaired in §2.1; the next one is not covered.

**Direction 4 reads one workflow.** `WORKFLOW` is `.github/workflows/ci.yml`, and a second workflow
file added beside it would carry jobs no census declares and nothing would notice — the same shape as
Plant C, one file over. That is a real gap and it is left open rather than closed by widening a glob,
because the repository has one workflow and a rule over a population of one is not measurable.

**The `name:` extraction is textual, and its blindness is stated rather than tested away.** A job
whose name were written as a YAML block scalar, or quoted across a line break, would not match
`^    name:\s*(.+?)\s*$` — and the failure direction is a *miss*, not a false alarm, so it would read
as a job that declares no name and fire 4c rather than pass. The committed tree has no such job, and
`test_the_job_name_pattern_cannot_match_a_step_name` pins that the pattern reads the six job names
and nothing else.
