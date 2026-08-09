# Finding 036 — the sixth gate was **not** invisible to CI. CI ran it, CI failed on it, and CI failed on **nothing else** for three consecutive runs while every pass reported "all five gates green". The briefing's premise that CI was green is **false, measured**. What was missing was not a check and not a CI wiring — it was the *list*, and nothing in the repository had the job of noticing that the list and the set had come apart

**Date**: 2026-08-09
**Feature**: 002. Measures [`tests/invariants/runner.py`](../../../tests/invariants/runner.py),
[`.github/workflows/ci.yml`](../../../.github/workflows/ci.yml) and the GitHub Actions run history at
`6beb9ae`, and the repair on top of it.
**Reports and repairs.** The repairs are described in §4 and §5; nothing in the decision register was
edited.
**User Story**: none directly. This is an instrument audit prompted by a live red gate.
**Owner decision**: **none is minted here and no register was edited.**
**Model spend**: **$0.0000.** No model was called and no credential was read. Container runs, local
process runs and `gh api` reads only; the longest is the removal-proof harness run in §6.
**Method**: **planting and reproduction, never a source read.**
[`tools/README.md`](../../../tools/README.md)'s named tell for an unmeasured claim is that the claim
describes *behaviour* while the evidence is a reading of source. Every behavioural claim below was
produced by planting the case and watching the instrument fire. The CI history claims are `gh api`
readings of specific run and job records, named by id.
**Reproduction**: every command is given in full in the section that uses it.
**Numbering note**: `035` was the high-water mark across `specs/*/findings/`, established two ways
and no "next free number" in any other document was consulted. (1) The numeric prefix of every file
matching `specs/*/findings/*.md`: max `035`. (2) A corpus-wide boundary-anchored citation search,
`rg -oNI -i -P '(?<![A-Za-z0-9-])finding[ -]0*\d+'`, match-only before sorting: max `035`. `036` was
free at that moment and re-checked free immediately before saving. Numbering is corpus-wide: `031` is
under `specs/001-discovery-validation/findings/`.

---

> ## THE RESULT IN ONE PARAGRAPH
>
> `tests/invariants/runner.py` has failed reconciliation since `7349e31` (T096, 2026-08-08), because
> that commit added `tests/invariants/test_sandbox_image.py` and all **six** of its removal-proof
> arms to [`tests/removal_proofs.sh`](../../../tests/removal_proofs.sh) — and did not write the
> `invariants.yaml` entry that names the test. The mechanism was whole; only the declaration was
> missing. The repair is therefore **INV-011**, not a move of the test out of `tests/invariants/`:
> FR-021 was discharged by no invariant, the test is a millisecond static reading with no model in
> it, and the harness had already been taught to copy `deploy/` and `requirements.lock` into its work
> tree *for this test*. An entry was what T096 owed.

> ## THE CORRECTION THAT MATTERS MOST, STATED FIRST
>
> **The briefing's central premise — "CI has been green throughout", and the consequent worry that a
> red instrument could not turn the tree red — is false, and the opposite is true.**
> `.github/workflows/ci.yml`'s `invariants` job runs `python tests/invariants/runner.py` as its third
> step and has done since T005. CI did not miss this. CI has been **red on it, and on nothing else**,
> for every completed run since it landed:
>
> | run | head | conclusion | which job failed |
> |---|---|---|---|
> | [`31273151364`](https://github.com/dperussina/function2agent/actions/runs/31273151364) | `abca043` | failure | `invariants` only; other four green |
> | [`31275273663`](https://github.com/dperussina/function2agent/actions/runs/31275273663) | `821ef70` | failure | `invariants` only; other four green |
> | [`31323555590`](https://github.com/dperussina/function2agent/actions/runs/31323555590) | `6cdd4a5` | failure | `invariants` only; other four green |
> | [`31325764987`](https://github.com/dperussina/function2agent/actions/runs/31325764987) | `6beb9ae` | failure | `invariants` only; other four green |
>
> The last of those was still in flight when this investigation opened and is
> recorded after it completed, so the sequence is unbroken from `7349e31` to the
> commit this document is written against. **Four consecutive red runs, one job
> each, the same one.**
>
> The job log for `31273151364` carries the exact text the local runner prints, and nothing else:
> `Reconciliation failed: - tests/invariants/test_sandbox_image.py is not named by any invariant.`
>
> So the defect is not an instrument CI cannot see. It is a **red instrument nobody read**, and the
> reason nobody read it is that it was not on the list every pass was working from. The failure was
> maximally visible and completely unobserved for four days.

---

## 1. The shape, and why it is not findings 032 or 034 again

Findings 032 and 034 are instruments that produced a clean bit over a measurement they had not
taken — a signal fabricated, a skip collapsed into a pass. Both are *instruments that lied*.

Nothing lied here. `tests/invariants/runner.py` said exactly what was wrong, in one sentence, on
every run. `ci.yml` ran it in the job it was designed for. The five instruments the briefing named
were all genuinely green, and each pass that reported "all five green" was telling the truth.

The defect lives entirely in a place this repository had never treated as an artifact: **the list of
instruments**. It was carried in prose, from brief to brief, by the person writing the briefs. It was
five items long. The set was larger. And there was no mechanism anywhere whose job was to compare
the two — so the list could not be wrong in a way anything would report, which is the same standing
as a check that is never run.

That is worth naming as a class, because the repair for it is not "add a check". Every check needed
already existed. The repair is a *census*, and a census is only worth anything if something
reconciles it against reality.

## 2. What the census found — and it is not one instrument, it is fourteen

The briefing predicted "at least one more I do not know about". The count is larger than that and the
useful part is the categories rather than the total. Full table in
[`tools/instruments.py`](../../../tools/instruments.py); the honest summary is
**26 entries — 19 gates, 5 advisories, 2 libraries** — against a working list of five.

The five the briefing named: `pytest`, `check_corpus.py`, `gen_claims.py --check`,
`check_tampers.py`, `removal_proofs.sh`. The sixth it had just learned: `tests/invariants/runner.py`.
**The other thirteen gates, every one of which can fail a CI job today:**

| gate | job | what it catches that nothing else does |
|---|---|---|
| `tools/selftest.py` | `corpus` | a corpus check whose regex stopped matching, which passes everything |
| `tools/threshold_probe.py` | `corpus` | a check that fires at the wrong constant. 34 perturbations |
| `src.supervisor.preflight` | `python` | a runner missing a kernel facility. OD-17 has no degraded mode |
| `tools/pytest_outcomes.py` | `python` | a half that collected nothing, or collected and skipped everything |
| seccomp figure present | `python` | the privileged suite ran and left no measurement |
| `if-no-files-found: error` ×2 | `python`, `go` | a run that published no record of what it ran |
| `go vet` | `go` | — |
| `go test` + its three assertions | `go` | a replayed `(cached)` result, a package with no test files, zero outcomes |
| `go build` | `go` | the enforcement point stops building as one static binary |
| `tools/removal_proofs_summary.py --render` | `removal-proofs` | a harness step green with no record behind it |
| runner-identity composite action | every job | `set -euo pipefail`; it can fail the job it labels |
| `tools/instruments.py --check` | `corpus` | added here; see §5 |

Plus five advisories that deliberately cannot fail anything — `check_corpus.py --report-only`,
`tools/unshare_pair_observation.py` (`continue-on-error`, because it measures a runner-image
property and not this repository), `tools/proof_attribution.py`, `tools/cite_advisor.py` (unwired by
a decision, not an oversight), `tools/wall_clock_ceiling_probe.py` — and two libraries,
`tools/tamper.py` and `tools/proof_timeout.py`, which are listed because "not an instrument" is an
answer somebody has to give.

**The instruments neither party had listed** are `selftest.py`, `threshold_probe.py`,
`pytest_outcomes.py`, `removal_proofs_summary.py`, the preflight, the seccomp-figure check, the two
artifact-upload gates, the runner-identity action, and the three assertions bolted onto `go test`.
Eleven of the thirteen are *inside* CI shell steps or workflow properties rather than files, which is
why a file-shaped mental model of "the gates" missed them.

## 3. Branch protection, re-verified rather than relayed — and why it is a separate question

Three reads at `6beb9ae`, 2026-08-09:

```sh
gh api repos/dperussina/function2agent/branches/main --jq '.protected'   # false
gh api repos/dperussina/function2agent/branches/main/protection          # 404 Branch not protected
gh api repos/dperussina/function2agent/rulesets                          # []
gh api repos/dperussina/function2agent/rules/branches/main               # []
```

So the standing fact holds: **nothing blocks a merge, and every check in `ci.yml` is advisory in that
sense.**

**That is not the same question as whether CI runs the instrument, and conflating them would have
produced the wrong repair.** Had CI *not* run the invariants runner, the fix would have been to wire
it in. CI does run it, and the failure was still invisible for four days — so wiring was never the
gap, and adding branch protection would not have closed this one either. A required check turns a red
tick into a merge block; it does not make anybody read the tick. What this episode needed was
something that turns "which instruments exist" into a question with a checkable answer.

## 4. The reconciliation, and why an entry rather than a move

The runner named two remedies: add an entry, or move the test out of `tests/invariants/`. They are
not equivalent, and the evidence decides it rather than convenience.

**The reasoning the briefing offered as a possible precedent does not carry.** T096 deliberately
excluded `src/sandbox/image_policy.py` from INV-003's *coverage count*
([`tests/invariants/test_sandbox_reachability.py`](../../../tests/invariants/test_sandbox_reachability.py),
`NOT_SANDBOX_RESIDENT`) because a build-time Dockerfile linter never executes inside a sandbox and so
cannot reach a second destination — counting it would have let INV-003 read as a live reachability
check on strength it does not have. That is a statement about **INV-003's denominator**. It says
nothing about whether "the shipped image satisfies FR-021" is itself an invariant, which is a
different proposition about a different artifact.

**What decides it is that T096 already built the whole mechanism and stopped one file short.**
`tests/removal_proofs.sh` carries **six** arms for this test — one over
`deploy/images/sandbox.Dockerfile` and five over `src/sandbox/image_policy.py` — and the harness's
own working-copy step was extended under T096 to `cp -r "$SRC/deploy" "$SRC/requirements.lock"`
*because this test reads them*. A test with six committed removal proofs and a bespoke harness
accommodation is not a stray unit test that wandered into the wrong directory.

It also meets every condition the file's own rules impose: it discharges **FR-021**, which no
invariant discharged; `model_in_loop: false`; 28 tests in **0.05 s** (privileged Linux container
`f2a-dev` on `6.12.76-linuxkit`, though the figure is platform-insensitive — it is a text parse);
and every prohibition it checks is paired with a synthetic Dockerfile that violates it, so the
scanner is shown to fire rather than merely to find nothing.

**The statement written into INV-011 carries the limit rather than eliding it**, which is the part
that would have made this a bad entry if skipped. It says in the entry itself that the reading is
static over the committed Dockerfile, that it is **not** an egress claim (FR-021 and the egress
policy are one control, research.md §T-11), and that two things are invisible to it: a package
manager arriving from a base-image change, and whatever the built image actually contains. CI builds
no images, so the Dockerfile's own build-time `RUN` block — the arm that covers the first — runs only
on a laptop, and `test_the_image_asserts_its_own_properties_at_build_time` is what stops it being
deleted as redundant.

**`also:` was considered and rejected.** The build-time `RUN` block is genuinely a second arm this
runner cannot execute, which is what `also` is for. But `also` names a *test file*, a Dockerfile is
not one, and the runner's hint for an `also` entry is hard-coded to `cd src/proxy && go test ./...` —
so declaring one here would print a Go instruction beside a Dockerfile. The Python arm already
guards that half.

`invariants.yaml` went `1.3.0` → `1.4.0`, `updated: 2026-08-09`. No document in the corpus quotes the
invariant count or the file version, checked with a case-insensitive search for `(ten|10|nine|9)
invariants` and for `1.3.0`; the only hits are two comments inside `runner.py` describing a 2026-08-04
measurement, which are historical and correct as written.

### 4.1 The vacuity floor was planted against the new entry, not assumed

`tools/README.md`'s standing trap is that **a file is not a check** — blanking a test file's body
while leaving the file gave `reconciliation OK` at exit 0 in a previous episode. So the new invariant
was subjected to it rather than trusted:

```sh
docker exec f2a-dev bash -c 'cd /work && cp tests/invariants/test_sandbox_image.py /tmp/tsi.bak \
  && printf "# body removed on purpose\n" > tests/invariants/test_sandbox_image.py \
  && python tests/invariants/runner.py; echo "EXIT=$?"; cp /tmp/tsi.bak tests/invariants/test_sandbox_image.py'
```

Observed: `reconciliation OK`, `146 passed`, and then

```
An invariant's test file exists and ran nothing:
  - tests/invariants/test_sandbox_image.py: collected no tests at all — the file exists, so
    reconciliation passed, but there is nothing in it
EXIT=1
```

INV-011 is covered by the outcome floor, measured.

## 5. The census, and the four cases planted against it

[`tools/instruments.py`](../../../tools/instruments.py) is the repair for §1. It is standard-library
only — `ci.yml` is read as text, no PyYAML — which is what lets `--check` run in the `corpus` job,
the one job that installs nothing and therefore the only thing still checking that the toolchain
claim in `tools/README.md` is true.

It makes exactly one machine-checkable claim: **the census and `ci.yml` agree**, in three directions.
All four failure modes were planted at `6beb9ae` + the working change and **observed firing**:

| planted | observed |
|---|---|
| `run: python3 tools/gen_claims.py --check` replaced with `run: true` | `generated claims: job 'corpus' does not contain 'run: python3 tools/gen_claims.py --check'` — exit 1 |
| a synthetic `run: python3 tools/brand_new_gate.py` added to the `corpus` job | `job 'corpus' runs tools/brand_new_gate.py, which no census entry names` — exit 1 |
| an empty `tools/an_unclassified_tool.py` dropped into the directory | `tools/an_unclassified_tool.py is named by no census entry. Classify it: gate, advisory or library` — exit 1 |
| the `corpus:` job key renamed to `corpus-gates:` | six entries reported as naming a job the workflow does not define — exit 1 |

The tree was restored and `--check` returned to
`census OK — every declared gate is in the workflow, every instrument the workflow runs is declared,
every entry point is classified` after each.

**`--run` was planted too**, because a runner that stops at the first failure would reproduce the
original defect in miniature. With INV-011 deleted from `invariants.yaml`, `--run` executed all seven
fast gates, exited **1**, and printed:

```
ran 7 gate(s); 1 failed
  FAILED  invariants runner
```

which is the line whose absence cost four days. It then named all twelve gates it did **not** run and
why, with the statement that this is not a clean bill of health for the set.

### 5.1 The census is itself put under the floor it exists to raise

A hand-run transcript is a measurement that happened once. The four
perturbations above, plus two more, are committed as
[`tests/unit/test_instrument_census.py`](../../../tests/unit/test_instrument_census.py) — nine
tests including two negative controls, in 0.05 s — and each is backed by a
removal-proof arm, so the proof set moves **237 → 243**. The two that are not
in the hand-run list are the ones that would leave the census green forever
rather than merely unhelpful:

- **the comment exclusion.** `ci.yml` discusses several instruments in prose,
  including `tools/cite_advisor.py`, which it deliberately does not wire. A
  scanner that matched comment text would report the reverse of the truth about
  that one on every push, and a checker that cries wolf on the committed tree
  gets switched off. The arm removes the exclusion.
- **the entry-point scan looking anywhere at all.** A candidate list that came
  back empty satisfies direction 3 for every input, and *no other test would
  notice* — the planted case supplies its own candidates and the clean tree
  reconciles either way. This is `check_tampers.py`'s vacuity floor one file
  over, and the arm makes `_entry_point_candidates` return `[]`.

**The first run of those arms reported `238 proved, 5 unproven`, and the
harness was right.** Five came back `UNUSABLE — the test already fails before
the tamper, so its failure after proves nothing`. The cause is that
`tests/removal_proofs.sh` copies `src`, `tests`, `tools`, `pyproject.toml`,
`deploy` and `requirements.lock` into its work tree and **not `.github/`**, so
a test that reads `ci.yml` had nothing to read there. That is T096's
`deploy/` problem repeated with a different directory, and the repair is the
same one line. It is worth recording that the harness produced the diagnosis
by itself: `UNUSABLE` is a distinct outcome from `unproven` precisely so that
"the tamper did not prove anything" cannot be confused with "the mechanism is
missing", and here it named the difference without anyone reading source.

**Two things `instruments.py` deliberately does not contain**, both because the briefing was right
that inventing them would be worse than omitting them. No duration: not one number in the file is a
timeout, because no duration in it has been measured, and `proof_timeout.py` plus `ci.yml`'s job
bounds already carry the two that were. No gate ordering: `--run` reports every verdict and the order
changes nothing, and the one place order is load-bearing — `selftest.py` before `check_corpus.py` —
is inherited from `ci.yml`'s own stated argument. And `--run` is **not wired into CI**: CI already
runs these in jobs whose bounds were derived for them, and collapsing that split would make a
four-minute instrument mandatory in a nine-second job.

**Where the authority lives.** `tools/README.md` is **not** read by `check_corpus.py` — the include
list is `README.md`, `research`, `docs`, `specs`, `.cursor/skills`, `.specify/memory`, and `tools/`
is never walked. Verified by reading `tools/corpuscheck/config.json`'s `include` and `search_roots`
keys directly. So a census maintained in that README would have been a second folklore list with
better prose. The authority is the Python table, reconciled by a gate; the only pointer outside it is
in the top-level `README.md`, which *is* in the include list and therefore has its link checked.

## 6. What everything reads at `6beb9ae` + this change

**Every figure below names platform *and* privilege, and one of them is here specifically because the
first reading was wrong for want of that discipline.**

Privileged Linux container `f2a-dev`, kernel `6.12.76-linuxkit`, `aarch64`, euid 0, started
**with** `--cgroupns=host -v /sys/fs/cgroup:/sys/fs/cgroup:rw`:

| instrument | reading |
|---|---|
| `pytest tests -q` | **1311 passed, 1 skipped** in 98 s. The +10 over the pre-change 1301 is `tests/unit/test_instrument_census.py` |
| `bash tests/removal_proofs.sh` | **243 proved / 0 unproven / 0 skipped / 0 timed-out / 0 unreadable**, 243 recorded, in 261 s. Baseline 1312 Python outcomes and 225 Go outcomes, both with 0 not-passing |
| `python tests/invariants/runner.py` | **11 invariants**, reconciliation OK, 174 passed / 1 skipped, exit 0 |
| `tools/check_tampers.py` | 243 declared, 0 errors, 0 warnings |
| `tools/check_corpus.py` | 0 errors, 0 warnings |
| `tools/gen_claims.py --check` | 39 claims, 0 stale |
| `tools/selftest.py` | all self-tests passed |
| `tools/threshold_probe.py` | all 34 perturbations behaved as declared |
| `tools/instruments.py --check` | 26 instruments; census OK |

The pre-change readings on the same container, for the comparison: **1301 passed, 1 skipped**;
**237 proved / 0 unproven / 0 skipped**; 237 declared. Both totals reproduce the figures relayed in
the briefing exactly, so those relays were sound.

**The same container without the cgroup mount read `1292 passed, 10 skipped`** — same 1302 outcomes,
nine of them declining in `tests/batteries/test_bounds_exhaustion.py` with
`cannot write '+memory +cpu +pids' to /sys/fs/cgroup/cgroup.subtree_control: [Errno 16]`. Both runs
are privileged, both are Linux, both are `f2a-dev`, and they differ by a `docker run` flag. So
**"privileged Linux container `f2a-dev`" is not a sufficient label for a figure from this repository**
— the cgroup delegation has to be named too. The removal-proof harness moved the same way and by the
same cause: **235 proved / 0 unproven / 2 skipped** without the mount, the two skips being exactly
`test_process_bound_exhaustion_names_its_terminal_state` and
`test_the_workload_is_in_the_cgroup_from_its_first_instruction`, both scored
`test-skipped-in-baseline` and neither scored `proved` — the harness behaving exactly as finding 034
rebuilt it to.

`go test` carries its own version of this. **`-race` cannot run inside `f2a-dev` at all**: the image
sets `CGO_ENABLED=0` and ships no C compiler, so `CGO_ENABLED=1 go test -race` fails with
`cgo: C compiler "gcc" not found`. Without `-race` the suite is `ok` in 0.394 s. The local
reproduction of the `go` job is therefore **strictly weaker than CI's**, which runs `-race` on
`ubuntu-latest`, and a green local Go run is not evidence about the race detector.

## 7. What this does not license

- **It does not say the instrument set is sufficient.** `instruments.py` is a census, not a verdict.
  Direction 3 forces a *classification* of every entry point; `library` is a legitimate answer and
  four files use it. Nothing in the file asserts that any instrument checks the right thing.
- **It does not close the reading problem.** A red CI run was ignored for four days by people with
  `gh` on their path. A census makes the set enumerable; it does not make anybody look. The only
  mechanism here that acts without being asked is `--check`, and all it can prove is that the list
  matches the workflow.
- **It does not make INV-011 a reachability or egress guarantee.** The entry says so itself, and the
  build-time arm it depends on still runs only where somebody builds an image.
- **It says nothing about branch protection.** `main` remains unprotected with empty rulesets, and
  §3 is a re-verification of that, not a change to it.
- **The findings index is stale and was not repaired here.** `README.md` in this directory carries a
  one-row index against seventeen findings. Nothing checks it, which makes it another artifact of
  exactly the class this document is about — noted rather than fixed, because fixing it is not this
  change.
