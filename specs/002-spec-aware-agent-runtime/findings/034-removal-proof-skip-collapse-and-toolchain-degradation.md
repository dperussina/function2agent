# Finding 034 — two more green runs over proofs that never ran, both **confirmed by planting**. `baseline_py` collapsed every unreadable baseline line into `SKIPPED`, the one outcome where a lost arm is invisible; and a missing Go toolchain silently deleted **12 of 222** arms while the harness exited **0**. The lost arm and the legitimate skip **were** distinguishable — in the baseline text, which the classifier was throwing away. The relayed *mechanism* for route 1 is **false and committed**: capture is **on** in this repository

**Date**: 2026-08-08
**Feature**: 002. Measures [`tests/removal_proofs.sh`](../../../tests/removal_proofs.sh) — this
repository's own instrument for deciding whether its tests are load-bearing — at `821ef70`.
**Reports and repairs.** The repairs are described in §6; nothing in the register was edited.
**User Story**: none directly. This is an instrument audit, and it is the direct successor to
[finding 032](./032-removal-proof-signal-fabrication.md), whose reasoning about what makes an outcome
*distinguishable* is the model followed throughout.
**Owner decision**: **none is minted here and no register was edited.**
**Model spend**: **$0.0000.** No model was called and no credential was read. Local process runs
only; the longest is the 239-second harness run in §6.4.
**Method**: **planted cases with negative controls, and re-measurement.** Both routes arrived as
relayed claims, described as behaviour and evidenced by a source read —
[`tools/README.md`](../../../tools/README.md)'s named tell for a claim that has not been measured.
Both turned out to be **real in their conclusion**, and route 1's stated **mechanism** turned out to
be **wrong** and to be sitting in a committed docstring. That combination is the reason the rule is
"plant it" and not "read it": a source read can reach a true conclusion through a false premise, and
the premise is what the next author inherits.
**Reproduction**: every command is given in full in the section that uses it. Both plants were
throwaway and are **not committed**; their source is reproduced verbatim in §1.2 and §2.1 so the
measurement can be repeated without them.
**Numbering note**: `033` was the high-water mark across `specs/*/findings/`, established three ways
and **no "next free number" written in any other document was consulted or trusted**. (1) Listing
every file matching `specs/*/findings/*.md`. (2) A corpus-wide boundary-anchored search for bare
citations, `rg -oNI -i -P '(?<![A-Za-z0-9-])finding[ -]0*\d+'`, match-only before sorting, per
`tools/README.md`'s note that piping `rg`'s default output to `sort -V` sorts by path and not by
number. (3) **`tools/corpuscheck` stated it independently and unprompted.** With the draft link to
`034` already written and the file not yet created, `findings-dangling` reported
`expected: one of the documents numbered 001..033` — the checker's own register, read out of the
checker rather than out of prose. `034` was free at that moment and re-checked free immediately
before saving. Numbering is corpus-wide: `031` is under `specs/001-discovery-validation/findings/`
and `032`/`033` under `specs/002-spec-aware-agent-runtime/findings/`, one sequence across both.

---

> ## THE RESULT IN ONE PARAGRAPH
>
> Two routes, both real, both measured by planting, both leaving the harness **exit 0**. **Route 1**:
> `baseline_py` classified a baseline line by *complement* — it ended `echo SKIPPED` with no test in
> front of it — so every way a line can fail to carry a verdict became `SKIPPED`. A planted arm whose
> target test writes past pytest's capture printed
> `SKIPPED … — the test did not run here (privilege or platform)` and the run reported
> **223 proved, 0 unproven, 1 skipped**, exit **0**. Its negative control, identical but for the
> write reaching the real file descriptor 1, scored `proved`. **Route 2**: on one tree, in one image,
> differing only in the shell, `bash -c` gave **222 proved, 0 unproven** and `bash -lc` gave
> **210 proved, 0 unproven, 12 skipped** — both exit **0**. `go` is at `/usr/local/go/bin/go` and
> `bash -l` sources `/etc/profile`, which rebuilds `PATH` without it. **The two routes intersect**:
> 10 of those 12 were labelled `no Go toolchain on PATH`, and the other **2 were labelled "privilege
> or platform" — a cause the harness invented, and the wrong one.**

> ## THE DISTINCTION THAT DECIDES THE FIX, STATED FIRST BECAUSE IT IS THE PART A READER WILL GET WRONG
>
> The relayed claim asked whether a lost proof and a legitimate skip can be told apart *at all*, and
> said that if they cannot, that is the finding. **They can, and they always could** — just not in
> the place anybody was looking. A legitimately skipped test has a baseline line carrying `SKIPPED`;
> a lost one has a line carrying **no verdict at all**. The information was present in
> `$BASELINE_PY` on every run. `baseline_py`'s fall-through was the only thing destroying it, by
> mapping two distinguishable inputs onto one output.
>
> So the fix is **not** a heuristic for telling a suspicious skip from an honest one, which is what
> the framing invites and which would have been unfounded. It is the removal of a lossy step. That is
> also why this is a *worse* defect than finding 032's and a *cheaper* repair: worse because
> `skipped` is legitimate 1–75 times a run depending on platform, so a lost arm hides in a crowd
> where 032's fabricated `proved` stood out; cheaper because no new evidence had to be found, only
> stopped from being discarded.

---

## 1. Route 1 — an unreadable baseline line was scored `SKIPPED`

### 1.1 The scorer, as it stood at `821ef70`

```bash
baseline_py () {
  # ...
  if [ -z "$out" ]; then echo ABSENT; return; fi
  if echo "$out" | grep -qE ' (FAILED|ERROR)'; then echo FAILED; return; fi
  if echo "$out" | grep -qE ' PASSED'; then echo PASSED; return; fi
  echo SKIPPED
}
```

The accepting set for `SKIPPED` is *"not absent, not failed, not passed"*. Nothing anywhere requires
pytest to have said the test was skipped. **This is precisely the defect finding 032 established for
`proof()`'s exit statuses — a classifier stated as a complement — and it was still standing twenty
lines above the repair, in the same file, having survived that pass untouched.**

### 1.2 The planted measurement

Two tests differing in exactly one thing: whether the write reaches the real file descriptor 1.

```python
POSITIVE_GUARD = True
NEGATIVE_GUARD = True


def test_planted_positive_writes_past_capture(capfd):
    """Splits its own -v line: capfd.disabled() reaches the real fd 1."""
    with capfd.disabled():
        print("planted output that reaches the real stdout")
    assert POSITIVE_GUARD, "the positive guard is gone"


def test_planted_negative_prints_under_capture():
    """Negative control: default capture buffers this, so the -v line is intact."""
    print("planted output that pytest captures")
    assert NEGATIVE_GUARD, "the negative guard is gone"
```

with one arm aimed at each, and **both tests pass**:

```bash
proof "PLANT positive — target test writes past capture" \
  tests/unit/test_r1_planted.py \
  "tests/unit/test_r1_planted.py::test_planted_positive_writes_past_capture" \
  's = s.replace("POSITIVE_GUARD = True", "POSITIVE_GUARD = False")'

proof "PLANT negative — target test prints under capture" \
  tests/unit/test_r1_planted.py \
  "tests/unit/test_r1_planted.py::test_planted_negative_prints_under_capture" \
  's = s.replace("NEGATIVE_GUARD = True", "NEGATIVE_GUARD = False")'
```

**What the unrepaired harness printed:**

```text
  SKIPPED   PLANT positive — target test writes past capture — the test did not run here (privilege or platform)
  proved    PLANT negative — target test prints under capture

223 proved, 0 unproven, 1 skipped
```

Exit **0**. The record written to `removal-proofs.latest.json` carried
`skipped_titles: ["PLANT positive — target test writes past capture"]` and
`status: "complete"`.

The baseline line the scorer was reading, and the reason it read it that way:

```text
tests/unit/test_r1_planted.py::test_planted_positive_writes_past_capture planted output that reaches the real stdout
PASSED                                                                  [ 66%]
```

`pytest -v` writes the node id, runs the test, then writes the verdict **on the same line**. A write
that reaches the real file descriptor 1 mid-test pushes the verdict onto a line of its own. The
harness matched the node id, found no verdict beside it, and fell through.

**Three things are established by the negative control specifically.** The arm is scoreable when the
line is intact, so the plant is not simply a broken arm; the tamper and the test are otherwise
identical, so nothing but the write is doing the work; and the failure is *silent* — the two arms
appear one line apart and only one of them ran.

### 1.3 The relayed mechanism is false, and it is committed

The claim as relayed, and as written into
[`tests/batteries/test_adversarial_filesystem.py`](../../../tests/batteries/test_adversarial_filesystem.py)
at `821ef70`, opens: *"Capture is off in this repository."*

**Measured, not argued: capture is on.**

| check | result |
| --- | --- |
| `addopts` or `-s` in `pyproject.toml` | **none**; `[tool.pytest.ini_options]` sets `testpaths`, `pythonpath`, `markers` only |
| `pytest.ini`, `setup.cfg`, `tox.ini`, root `conftest.py` | **do not exist** |
| capture handling in `tests/conftest.py` | **none** — no `capture`, `capfd`, `capsys`, `dup2`, `os.write`, `fileno` in 207 lines |
| ordinary `print` in a scratch test under `pytest -v` | `test_cap.py::test_ordinary_print_under_default_capture PASSED` — **line intact, output absent** |

The conclusion the false premise reached was nonetheless correct, which is exactly why this is worth
recording rather than quietly fixing. The premise matters in **both** directions:

- **It over-states the trigger.** If capture were off, every printing test in the suite would break
  its own proof, and the next author would have to treat every `print` as a hazard. It is not the
  hazard; a write that gets *past* capture is, and those are rarer and named — `capfd.disabled()`,
  `-s`, `PYTEST_ADDOPTS=-s`, a write from a thread outliving the capture window.
- **It under-states the defect.** The harness's fault was never about printing. It was a classifier
  that returned `SKIPPED` for *any* unreadable line, from any cause, including causes nobody has
  enumerated. Fixing "printing" would have left the class open.

The docstring is corrected in place rather than deleted, and the correction names both directions.
**The original symptom it records is not reproducible at `821ef70`** and this document does not claim
otherwise: the pass that found it had already changed the test to write to `results/` instead of
printing, and the pre-fix source is not in the history, so the route by which that particular write
reached file descriptor 1 **is not recoverable**. What is recoverable is the premise, and the premise
is wrong.

---

## 2. Route 2 — a login shell deleted 12 arms and the run stayed green

### 2.1 The planted measurement — one tree, one image, two shells

Nothing was planted in the sense of edited source. The variable is the shell, and the control is the
other shell. Both runs are `821ef70`, exported clean with `git archive`, in `f2a-dev`, privileged:

```bash
docker run --rm --privileged --cgroupns=host \
  -v /sys/fs/cgroup:/sys/fs/cgroup:rw -v "$PWD:/work" -w /work \
  f2a-dev bash -c  'bash tests/removal_proofs.sh'   # control
docker run --rm --privileged --cgroupns=host \
  -v /sys/fs/cgroup:/sys/fs/cgroup:rw -v "$PWD:/work" -w /work \
  f2a-dev bash -lc 'bash tests/removal_proofs.sh'   # degraded
```

| invocation | result | exit |
| --- | --- | --- |
| `bash -c` | `222 proved, 0 unproven` | **0** |
| `bash -lc` | `210 proved, 0 unproven, 12 skipped` | **0** |

`go` is at `/usr/local/go/bin/go`; `bash -l` sources `/etc/profile`, which rebuilds `PATH` without
it. **How the harness is invoked decided whether twelve proofs ran, and both runs were green.**

This is not a hypothetical second route, either. CI already carries a hand-written workaround for the
same hazard from the other direction — `sudo -E env "PATH=$PATH"` appears five times in
[`.github/workflows/ci.yml`](../../../.github/workflows/ci.yml), because plain `sudo` also resets
`PATH`. Two known routes into the state, which is why the guard belongs in the harness and not in
each invocation.

### 2.2 The two routes intersect, and this is the part worth keeping

The twelve lost arms were not twelve of a kind:

```text
  SKIPPED   T114 battery — every path template moved, … — the test did not run here (privilege or platform)
  SKIPPED   T114 instrument — the arm table is never attempted, … — the test did not run here (privilege or platform)
  SKIPPED   conformance — the proxy digests the decoded bytes instead — no Go toolchain on PATH
  … 9 more `no Go toolchain on PATH` …
```

Ten arms named the real cause. **Two named a cause the harness invented.** Those two are route 1
firing: their tests were genuinely skipped by pytest, for a reason connected to the missing
toolchain, and `report_unrunnable` printed the fixed string `(privilege or platform)` because that
was the only thing it had ever printed for a skip. **The harness had pytest's own recorded reason
available and was not asking for it.** A reader chasing those two arms would have gone looking at
privilege and platform, and neither was involved.

### 2.3 The asymmetry the relayed claim asked about is real

The claim asked whether "toolchain absent" should be a `SKIP` at all, noting that commit `0caf257` —
*"Stop the removal-proof harness from scoring an environment as a result"* — already ruled on the
Python side. It is real and it is stark. In the same file:

| the environment cannot run the **Python** suite | the environment cannot run the **Go** arms |
| --- | --- |
| `CANNOT RUN — pytest produced no test outcomes at all`, summary `aborted`, **exit 2** | `SKIPPED   <arm> — no Go toolchain on PATH`, summary `complete`, **exit 0** |

Same class of fault, opposite handling. **A missing toolchain is an environment, not a result**, and
the Go side was scoring it as one.

---

## 3. Can a lost proof be told from a legitimate skip?

**Before the repair: not in the output, and that is the whole defect.** The summary line reported one
integer. The per-arm lines were the same word with the same invented parenthetical. The JSON record
put both in `skipped_titles`. Nothing a reader sees distinguished them, and `skipped` is legitimate
1–75 times a run depending on platform (§5), so a lost arm sat inside a population of correct ones.

**But the underlying states were never identical, and this is the finding.** In `$BASELINE_PY`:

| | the baseline line for the named test |
| --- | --- |
| legitimately skipped | carries ` SKIPPED` |
| lost | carries **no verdict at all** |

Two distinguishable inputs, one output, because of one unguarded fall-through. **After the repair:**
`SKIPPED` requires pytest to have said so; the residue is `UNREADABLE`, with its own outcome name,
its own counter, its own paragraph in the tail block, its own key in the record, and **`FAIL`'s
weight in the exit status**. Measured, on the same plant:

```text
  NO VERDICT PLANT positive — target test writes past capture
            tests/unit/test_r1_planted.py::test_planted_positive_writes_past_capture appears in the baseline with NO outcome on its line.
            pytest -v writes the verdict on the same line as the node id, so
            anything the test writes to the real stdout splits them. This arm
            was NOT attempted, and it is not scored as skipped: a skip is an
            arm the environment declined, and nobody declined this one.
  proved    PLANT negative — target test prints under capture

232 proved, 0 unproven, 1 BASELINE UNREADABLE

  1 arm(s) name a test whose baseline line carries no verdict, so they
  were never attempted. This run is NOT green, and it is NOT a skip: a skip
  says the environment declined the test, and nothing declined these.
```

Exit **1**. Finding 032's requirement — name it in the tail block, because one line among 222 inside
a collapsed CI details block is the quiet form of having no outcome — is met by the summary line
carrying `1 BASELINE UNREADABLE`.

**The remaining limit, stated rather than papered over.** A skip pytest records with no reason is
still a skip nobody can check. The harness now prints the recorded reason when there is one and says
*"It recorded no reason this harness could attribute"* when there is not, which converts an invisible
gap into a visible one but does not fill it. Reason attribution is also **by file, not by node id**,
because that is how pytest's `-rs` block is keyed. That is weaker than per-test, and it is a
**reading rather than an invention**, which is the whole difference from what it replaced.

---

## 4. The third item — `PYTHONDONTWRITEBYTECODE`, and the ruling

`test_a_tampered_module_of_the_same_size_is_read_from_a_stale_pyc` exists because of a real harness
defect: two proofs tampering one file with equal-byte-length edits can make the second import the
first's cached module, since CPython's source-timestamp check has one-second granularity and the size
matches. The mitigation is a `find -name __pycache__ -exec rm -rf` around every tamper. The test's
job is to make that `rm` undeletable as tidying.

Both images set `PYTHONDONTWRITEBYTECODE=1`
([`deploy/images/dev.Dockerfile`](../../../deploy/images/dev.Dockerfile),
[`deploy/images/sandbox.Dockerfile`](../../../deploy/images/sandbox.Dockerfile)), the test's child
inherited it, no `.pyc` was written, and the collision could not be planted. **Measured at `821ef70`:
`1 failed, 1278 passed, 1 skipped` privileged, and `1 failed, 1204 passed, 75 skipped` unprivileged —
the container could not run the suite green as shipped, on either.**

**Ruling: the test forces bytecode on for its own child. Neither of the two options offered.**

```python
env = dict(os.environ)
env.pop("PYTHONDONTWRITEBYTECODE", None)
```

**Against skipping when the variable is set.** The arm does not exist to detect the hazard in
whatever environment it happens to run in; it exists so nobody deletes the `rm`. The hazard is a
property of CPython, present everywhere, so the check has to be available everywhere — **most of all
in the container, because the container is the documented invocation for `tests/removal_proofs.sh`,
the very instrument the mitigation protects.** A skip keyed on the variable puts the blind spot
exactly where the person who might delete the `rm` is working, and where they may never run the suite
any other way. It would also have been *self-concealing* in the same shape as route 1: a legitimate
skip absorbing a real gap.

**Against unsetting it in the image.** Two independent reasons, and the relayed briefing named the
first. The tree is bind-mounted, so the container would start writing `.pyc` files into the working
tree — its own hazard, and one that touches every run rather than one test. Worse: it would make the
stale-bytecode collision **live in the harness's own execution environment** in order to make a test
*about* that collision pass. That is backwards. The image's variable is doing real work and should
keep doing it.

Forcing it for one child under `tmp_path` leaves the image's property intact, writes nothing outside
the temporary directory, and makes the arm mean the same thing on every host.

**The forcing is itself proved, and the assertion is on the forcing rather than the outcome.**
`test_the_stale_pyc_arm_plants_its_hazard_where_the_images_disable_bytecode` sets
`PYTHONDONTWRITEBYTECODE=1` **deliberately** before calling the helper, so it fails on any host the
moment the helper stops clearing it — not only on hosts that happen to set it. Without that, the
guard would be vacuous everywhere the variable is unset, which is every developer's laptop.

---

## 5. Where the relayed briefing was wrong or stale

Measured, because the briefing asked to be corrected and asked for exposure to be measured before
anything was swept.

**1. "Capture is off in this repository" — false, and committed.** §1.3. The one correction that
changes what a future author does.

**2. The gate baseline is not the tree's behaviour, and contradicts the briefing's own item 4.** The
briefing gave `pytest 1270 passed / 10 skipped` for `821ef70` in the container. Measured on a clean
`git archive` export of `821ef70`:

| environment | failed | passed | skipped |
| --- | --- | --- | --- |
| **privileged** Linux container, `f2a-dev` | **1** | 1278 | **1** |
| **unprivileged** Linux container, `f2a-dev` | **1** | 1204 | **75** |

Neither is `1270 / 10`, and **both carry a failure the gate line omits** — the same failure the
briefing itself raised as item 4. The two halves of the briefing disagree: item 4 says the container
cannot run the suite green as shipped, and the gate baseline reports it green. `10 skipped` matches
neither privilege level, so the figure's provenance could not be reconstructed and is not guessed at
here.

**3. "Container" is not an environment.** The skip count moves **1 → 75** on one tree in one image on
privilege alone. Any figure naming "the container" without naming privilege is as ambiguous as one
not naming the platform, which is the defect class the briefing was warning about.

**4. Route 2's own numbers were close but not right.** Relayed: *"skips 13 proofs, where `bash -c`
finds 225 Go outcomes and skips only 2"*. Measured: **12** skipped under `bash -lc`, and **0** under
`bash -c` privileged, not 2. The `2` is a macOS-shaped figure — the kernel-only arms — reported as a
container one. 225 Go outcomes is correct.

**5. The exposure the briefing feared, measured before sweeping — and it is almost empty.** Searched
the corpus for the figures named as platform-ambiguous:

| figure | committed occurrences |
| --- | --- |
| `1202`, `48 skipped`, `209 proved`, `1270 passed`, `1240` | **none** (one `1202` is a `sed` line range; the rest are inside JSONL traces) |
| `6 skipped` | 2 — [finding 032](./032-removal-proof-signal-fabrication.md) §3.2, **which names its platform**, and [finding 027](./027-lifecycle-edge-set-divergence.md) §5, **which does not** |

**Net correctable: one document, two lines.** The briefing's instinct that a sweep would find nothing
was very nearly right again, and the one real instance is amended in place — naming the **ambiguity**
and explicitly **not resolving it**, because this pass did not re-run `027`'s tree and the platform
those figures were taken on is not recoverable from the document.

**6. Not stale, and worth saying because it was a stated risk.** The briefing said the tree was clean
at `821ef70` and warned that four passes this week swept up another pass's uncommitted work. The tree
*was* clean. A stale editor snapshot showed
`?? tests/batteries/test_adversarial_filesystem.py`, which is **tracked** at `821ef70`;
`git ls-files --error-unmatch` was used to establish that before anything was staged.

**7. Unrelated, incidental, and reported because it is a live flake source.** Three orphaned
`LeaseRenewer` children were found running from **Aug 4 and Aug 5**, renewing a lease every 200ms
against `/private/tmp/f2a-pytest-501/test_a_sigkilled_supervisor_le0/sessions.db`. pytest's numbered
basetemp scheme reuses that name, so a stale renewer can renew a lease a later run expects to expire.
They predate this pass by 3–4 days and were killed. **Not investigated** — the leak's cause is
untouched and no fix is claimed.

---

## 6. What was fixed

### 6.1 Route 1 — the classifier is enumerated, and the residue is named

`baseline_py` returns `PASSED | FAILED | SKIPPED | ABSENT | UNREADABLE`, **never by fall-through**.
`SKIPPED` requires pytest to have written a verdict; `XFAIL` and `XPASS` are named explicitly,
because omitting them would make them `UNREADABLE` — a true statement about the harness and a
misleading one about the test. `UNREADABLE` carries its own counter, its own tail-block paragraph,
its own key and title list in the record, and `FAIL`'s weight in the exit status.

The precedent is `TIMED OUT` from finding 032, and the reasoning is the same: an arm nobody measured
belongs in neither existing bucket, and folding it into one loses the only fact worth keeping.

### 6.2 Route 1's other half — the skip reason is read, not invented

The baseline now runs with `-rs`, and `baseline_skip_reason` quotes what pytest recorded. `-rs` is
load-bearing, not a nicety: without it the baseline records *that* a test was skipped and not *why*,
and the harness filled the gap with `(privilege or platform)` — the string that was measurably wrong
about two arms in §2.2. Where there is no reason to quote, the harness says so.

### 6.3 Route 2 — a missing toolchain aborts, on the Python baseline's terms

`go_toolchain_verdict` returns `OK | ABORT | NO-GO-ARMS`. The condition is **"this file declares Go
arms and there is no toolchain"**, not "Go is missing", so a tree with no Go arms needs no Go and
deleting the arms deletes the requirement. The arm count is read out of this file (`^go_proof "`)
rather than fixed. Measured: the repaired harness under `bash -lc` prints `CANNOT RUN`, writes
`status: aborted`, and exits **2**.

It is a **function with three enumerated answers rather than an inline `if`** so that the decision
can be driven directly by a test with `go` on and off `PATH` and with the arm count at zero. An
inline `if` could only have been checked by reading it, and this repository's position is that
reading an instrument is not measuring it.

`go_proof`'s old `HAVE_GO -eq 0` skip branch is now unreachable and was **kept and converted into a
refusal** rather than deleted: a `go_proof` declaration the guard's anchor does not match — an
indented one, the exact rot `tools/check_tampers.py` was written against — would still arrive there,
and scoring it as a skip is how twelve arms went missing in the first place.

### 6.4 The proofs, and the gate

**Nine new arms, each observed failing tampered and passing untampered.** They tamper
`tests/removal_proofs.sh` and `tools/removal_proofs_summary.py` — this instrument and its record,
which is a new target for this file. It is safe for the reason the file's header gives: every tamper
lands on the copy under `mktemp -d`, and the copy is **read** by the tests rather than executed.

They exist because **the scorer is where every silent failure this instrument has had has lived, and
until now nothing tested it.** Finding 032 repaired `proof()`'s classifier and shipped no test with
the repair; the defect in §1.1 was the same mistake twenty lines above it, and it survived.
`tests/unit/test_removal_proof_scoring.py` extracts the shell functions verbatim and drives them
against synthetic baselines, with a vacuity floor asserting the extraction found the scorer at all —
without which the whole file would pass over nothing the moment a function is renamed.

Gate, privileged `f2a-dev` on Linux `6.12.76-linuxkit`, non-login shell:

| gate | result |
| --- | --- |
| `pytest tests -q` | **1294 passed, 1 skipped**, 0 failed |
| `tests/removal_proofs.sh` | **231 proved, 0 unproven**, 0 skipped, 0 unreadable, exit **0** |
| `tools/check_tampers.py` | **231 proofs declared**, 0 errors, 0 warnings |
| `tools/corpuscheck` | 0 errors, 0 warnings |

The one remaining skip is the declared-vacuous `INV-003` invariant, which the suite reports in its
own terminal section so a green run is not mistaken for coverage of it.

---

## 7. The shape to carry forward

Three instrument defects now share one shape, and it is worth naming because the fourth will too.

| finding | the classifier | the accepting set |
| --- | --- | --- |
| 032 | `proof()` on exit status | *any non-zero* ⇒ mechanism was load-bearing |
| 034, route 1 | `baseline_py` on baseline text | *not absent, not failed, not passed* ⇒ skipped |
| 034, route 2 | the Go toolchain check | *absent* ⇒ skip the arms, keep the total |

**Every one is a classifier whose accepting set was written as a complement.** The residue always
lands somewhere, and it always lands in whichever outcome is spelled last. The two rules that follow:

1. **Enumerate the accepting set; never write the last branch as a fall-through.** If a case is
   genuinely unclassifiable it needs a name, a counter, and weight in the exit status.
2. **Prefer the residue to land in the outcome that is loudest, never the one that is legitimate.**
   Route 1 was worse than 032 for exactly this reason: `proved` over a hang was anomalous and
   noticed; `skipped` over a lost arm was ordinary and was not. **An outcome that is both legitimate
   and a dumping ground cannot be audited.**
