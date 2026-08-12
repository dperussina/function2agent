# Finding 039 — three non-reproducing failures were asked whether they share a cause. **They do not.** One of them — today's lease-revocation flake — is not a race at all once planted: it is a **machine-wide process-table namespace keyed on a constant string**, and it fails **10 of 10** on demand with a decoy process carrying that string. Both halves are established by planting: a concurrent run's supervisor makes this test **fail**, and this test **SIGKILLs a concurrent run's supervisor**. The other two are not joined to it and are not closed by it: one carries two candidate mechanisms on the record, neither bound to the sweep that produced it — and §9 now **measures one of them and rules it out at 3 arms against 58** — and the other **predates `e4ef6e6` by 67 minutes**, which bounds the shared-basetemp story off it entirely

**Date**: 2026-08-11
**Feature**: 002. Measures
[`tests/integration/test_lease_revocation.py`](../../../tests/integration/test_lease_revocation.py)
against [`tests/conftest.py`](../../../tests/conftest.py), and dates three recorded
incidents against commit `e4ef6e6`.
**Reports. Repairs nothing.** No source was changed. The defect in §3 is left standing
deliberately — see §7 for why a repair is owed an owner and not this pass. **Superseded in
part: §8 records the repair landing later the same day, and corrects two things §3 and §7
got wrong. §9 measures one of incident 2's two candidates and rules it out, and confirms a
work-tree baseline floor that neither candidate names. §10 REPAIRS that floor and reports it
at 0, which supersedes §9.5's "owed an owner" and §9.3's present-tense count of 2.**
**User Story**: none. Prompted by a brief asking whether three separately-recorded
non-reproducing failures share a mechanism.
**Owner decision**: **none is minted here and no register was edited.** §7 states the one
decision this finding makes owed and does not take it.
**Model spend**: **$0.0000.** No model was called and no credential was read.
**Method**: **every rate below is a count over stated trials, not an anecdote.** The
mechanism in §3 was established by *planting* a marker-bearing process and watching the
named test fail, not by reasoning about the source. The dating in §2 is `git log` against
the commit, not against any summary. Where this document could not obtain a clean control
it says so and does not report a control.
**Platform**: `macOS-26.2-arm64-arm-64bit`, `arm64`, euid `501`, CPython `3.12.11` from
`/Users/djperussina/Code/function2agent/.venv/bin/python`.
**Measurement tree**: every measurement was taken in a **detached worktree** at
`/tmp/flakeprobe-a770fb2d6750aef2` (and a sibling at `/tmp/sibling-e5f477c9fdaf8b1e`),
never in the shared tree, both at `0d8b2e4`.
**Other passes were running throughout.** This is stated per-arm in §4 because it is a
variable and not noise; one arm was contaminated by an unplanned sibling and is reported
as contaminated rather than as a control.
**Numbering note**: `038` was the high-water mark across `specs/*/findings/`, established
two ways, and no "next free number" written in any other document was consulted. (1)
Filename prefixes, match-only before sorting: `ls specs/*/findings/*.md | sed 's#.*/##' |
grep -oE '^[0-9]{3}' | sort -n | tail -1` → `038`. (2) A corpus-wide citation search with
match-only output taken **before** sorting → max `038`. `039` was free at that moment and
re-checked free immediately before saving. A concurrent pass owns `038`.

---

> ## THE RESULT IN ONE PARAGRAPH
>
> `tests/integration/test_lease_revocation.py` looks for its crash-arm child by scanning
> **the entire machine's process table** for the literal string `LeaseTerms('s-crash'`,
> and kills by the same scan. The comment defending that choice says *"nothing else in the
> tree constructs `LeaseTerms` in a subprocess"* — true within one tree, and false across
> the several checkouts this repository routinely runs at once, because `ps -e` does not
> stop at a tree boundary. With a decoy process carrying that string alive, the test fails
> **10 of 10**, every failure the identical `assert 'ALIVE' == 'DEAD'` that was recorded
> today, and the test's own `finally` **SIGKILLed the decoy 10 of 10 times**. This is the
> same defect class `e4ef6e6` fixed in `tests/conftest.py` four days earlier — a global
> namespace keyed on something not unique per run — and `conftest.py` gets it right by
> scoping its own sweep to `parent != mine`. The new file, added **after** that fix, does
> not scope at all.

> ## WHAT THIS FINDING DOES NOT CLAIM
>
> It does **not** claim the other two incidents share this mechanism; §5 argues they do
> not, and gives each one's separately-stated cause. It does **not** claim the
> shared-`/tmp` basetemp is still faulty — `e4ef6e6`'s repair was probed here and holds.
> It does **not** claim a rate for the *unplanted* incidence of this fault, because no
> uncontaminated control was obtainable while other passes were running; §4 reports the
> ambient figure with that limitation attached. And it **repairs nothing**.

---

## 1. The three incidents, as recorded

| # | Incident | Recorded in | Recorded at |
|---|---|---|---|
| 1 | `test_the_crash_arms_child_does_not_outlive_a_failing_test` failed once in a full-suite run, passed on isolation and on re-run | the test file itself, added `4eb66be` | 2026-08-09 11:09:53 −0600 |
| 2 | A sweep took a baseline with **234 of 1653 outcomes failing**, reported *"236 proved, 58 unproven"* | `tests/removal_proofs.sh:344`, added `f3f1c89` | 2026-08-10 08:00:14 −0600 |
| 3 | One arm reported `BROKEN` on a first run and not on three subsequent ones; the classifying output had been discarded | `tests/removal_proofs.sh:813`, added `ce64490` | 2026-08-05 12:47:25 −0600 |

*(Both line numbers were `297` and `766` when this table was written; §10's repair inserted
lines above each, and they are repointed rather than left to rot. The commits they are
attributed to are unchanged and are the durable half of each citation.)*

## 2. Dating against `e4ef6e6`, which bounds one of the three off it

`e4ef6e6` — *"Stop the basetemp redirect from deleting a concurrent run's directory"* —
is **2026-08-05 13:54:38 −0600**.

- **Incident 1 postdates it by four days.** The test did not exist until `4eb66be`.
- **Incident 2 postdates it by five days.**
- **Incident 3 PREDATES it by 67 minutes.** `ce64490` is `2026-08-05 12:47:25 −0600`, and
  `git merge-base --is-ancestor ce64490 e4ef6e6` confirms the order. The `BROKEN` it
  records happened *before* the comment was written, so it is strictly earlier still.

**What that bounds.** Incident 3 occurred while the **pre-`e4ef6e6`** basetemp bug was
live — the uid-keyed shared root that a second run deleted out from under a first. That
bug produces exactly incident 3's presentation: a collection-time explosion that leaves an
unparseable tamper and an environment flake indistinguishable. So incident 3 is
*consistent* with the shared-basetemp story **in its pre-repair form**, and is
**unavailable as evidence that the repair is incomplete**. It cannot be joined to incident
1, which is four days the other side of the fix.

## 3. Incident 1's mechanism, established by planting

Two sites in `tests/integration/test_lease_revocation.py` scan the **machine-wide** process
table for a constant marker, `_CRASH_CHILD_MARKER = "LeaseTerms('s-crash'"`:

- the nested run's observer (`pytest_runtest_logfinish`), which writes `ALIVE` if **any**
  process on the host matches — this is the read half;
- `_kill_children_matching`, called unconditionally in the test's `finally`, which
  **SIGKILLs every matching process on the host** — the destructive half.

Neither is scoped by pid, ppid, tree or tmp_path. `tests/conftest.py`'s own sweep, by
contrast, filters `parent != mine` and is therefore safe; the two files disagree about the
lesson `e4ef6e6` recorded.

**The plant.** A decoy holding the marker in its argv, alive across the trial:

```bash
nohup /usr/bin/python3 -c "
import time
# decoy argv contains: LeaseTerms('s-crash', decoy)
time.sleep(120)
" >/dev/null 2>&1 &
```

The decoy is visible to the observer's exact query — `ps -eo state=,command=` reports it in
state `S`, so it passes the zombie filter the observer applies.

## 4. Rates, with the concurrency conditions stated per arm

All arms ran the single named test in the detached worktree. `TRIALS` as stated.

| Arm | Condition | Other passes running? | Result |
|---|---|---|---|
| Isolated | no marker-bearing process | none visible | **1/1 passed**, 0.91 s |
| **Decoy** | fresh decoy alive each trial | yes, 4 concurrent `pytest` | **10/10 failed** — and **10/10 decoys SIGKILLed** by the subject |
| Sibling | a second worktree looping the whole lease file | yes | **2/20 failed** |
| "Control" | no sibling started by me | yes — **another pass was running the same file**; this arm is contaminated and is *not* a control | 2/20 failed |
| "Control" 2 | no sibling started by me | yes, 5 concurrent `pytest` | 2/20 failed |

**Every one of the 12 failures carries the identical signature**, `assert 'ALIVE' ==
'DEAD'` under `assert verdict.read_text() == "DEAD"`. There is one failure mode here, not
several.

**The ambient figure is 6/60 ≈ 10%, and it is a floor, not a rate.** No arm was free of
concurrent passes, so 10% is the incidence *under whatever load happened to be present*,
which was not controlled and not measured. The honest statement is the planted one: **with
a marker-bearing process alive, the failure is deterministic.**

**A correction to my own measurement, recorded because it nearly became the result.** My
first classifier grepped the failure text for the assertion *messages*, which pytest echoes
as source in the traceback — so it labelled failures "the observer never wrote a verdict"
when the failing line was `assert 'ALIVE' == 'DEAD'`. Classified on the `E  assert` line
instead, all failures are one mode. A baseline-plus-delta reading of that output would have
invented a second mechanism.

## 5. Ranking on shared cause

**1 and 3 do not join.** Four days and a repair separate them, and §2 shows incident 3 sits
on the pre-repair side.

**1 and 2 do not join.** Incident 2 is a *baseline* condition — 234 outcomes failing before
any tamper — i.e. the whole suite dirty. Incident 1 is a single assertion in a single test
with a specific string. Nothing in the process-table mechanism dirties a baseline.

**2 and 3 do not join to each other either, and 2 has two candidate mechanisms on the
record already — candidates, not established causes, and the distinction is load-bearing.**
`f3f1c89` records the 234 sweep's baseline only as *"transiently dirty"* and **does not name
what dirtied it**. In the same commit it separately names a mechanism capable of producing a
mass baseline failure — the work-tree copy list omitted `specs/`, `2>/dev/null` hid it, and
*"every dependent test then failed in the baseline for a missing file"* — but it attaches
that to *"three more of the same"*, not to the 58. Reading the second as the cause of the
first is the move this corpus keeps having to undo, so it is not made here: it is a
deterministic route that would produce this shape, and it is unbound. The **116-outcome**
sibling instance — which lives in
[`tests/unit/test_operator_log.py`](../../../tests/unit/test_operator_log.py), not in
`tests/conftest.py` — carries a fully stated mechanism: macOS runs a crash reporter per
`SIGABRT`, *"a dozen of them saturate the host while the rest of the suite is still
going"*. That was repaired in `a00f096` (2026-08-08 10:16:35 −0600) by stopping each arm at
its first abort.

**The ranking.** Incident 1: **mechanism established, by planting.** Incident 2: **two
candidate mechanisms already on the record, neither of them this one, and neither bound to
the 234 sweep**; its cause is still undetermined, and this finding does not close it. Incident 3: **bounded off the fix by date**; cause still undetermined
and now cheap to leave so, because the pre-repair bug is gone. **There is no shared cause.**

## 6. Is serialising runs still the cheapest fix?

**For incident 1, no — and it would be the wrong fix.** Serialising hides a defect that a
four-line pid scope removes. The test's own kill is destructive to concurrent runs, so
serialisation would suppress the symptom while leaving a test that SIGKILLs other people's
processes whenever it does run beside one.

**For incident 2, the argument the earlier pass made was wrong and the conclusion survives
anyway.** The brief is right that *"a probabilistic cause is not refuted by one clean run
under the same conditions"* — that shows contention is not sufficient, not that it is not
the cause — and that reasoning should not stand as recorded. But §5's two stated mechanisms
are both deterministic and both already repaired, so serialisation is not the cheapest fix
for incident 2 either; it is a fix for a cause nobody has evidence for.

**So serialisation is off the table as a *first* response, and is not refuted as a
backstop.** Nothing here rules contention out as a contributor to incident 2's residue.

## 7. What this makes owed, and to whom

**A repair to `test_lease_revocation.py` is owed an owner, and this pass did not take it.**
The obvious shape — scope both scans to descendants of the current process, as
`conftest.py` already does — is four lines. It is left undone because the destructive half
changes behaviour under concurrency and the file is not this pass's to change while another
pass may hold it.

**One operational consequence, worth more than the repair.** Until it is scoped, **any pass
running the full suite will fail another pass's `test_the_crash_arms_child_...` if their
windows overlap, and will SIGKILL that pass's supervisor child.** A green full-suite run
taken beside a concurrent one is, for this test, not evidence; and a red one may be
somebody else's run rather than a defect.

## 8. Amendment — the repair landed, and §7's prescription for it was wrong

**Date**: 2026-08-11, later the same day. Both scans are now scoped and the operational
consequence in §7 no longer holds. Two things this document got wrong are corrected here
rather than edited away, because the second one would have produced a vacuous green.

**§7 prescribed "scope both scans to descendants of the current process, as `conftest.py`
already does". That is wrong twice.** `tests/conftest.py` scopes to *direct children*
(`parent != mine`), not to descendants — the sentence misreads the file it cites. And a
descendant test is the wrong instrument at one of the two sites, for a reason that is
measured rather than argued:

| Site | Vantage point | What the child is from there | Scope used |
|---|---|---|---|
| read half | inside the nested `pytest`, while it runs | **direct child** — `Popen` from the test function, no shell, no re-exec | `ppid == os.getpid()` |
| kill half | this process, after the nested `pytest` returned | **orphan, reparented to init** — no ancestry left to test | this run's `tmp_path`, which the child carries in its argv |

An ancestry test at the kill site matches nothing, kills nothing, and says nothing — the
scan switched off while still reporting success, which is worse than the noisy red it
replaces. That is why the two sites are scoped on different things.

**A third measured fact §3 did not have.** On an ordinary run the kill half has **nothing
of its own to kill**: the nested run's own `tests/conftest.py` sweep reaps the child before
that process exits, which was observed directly in its terminal output. So every one of the
10 decoy kills §4 records was **purely collateral** — the scan's entire observed effect was
on other people's processes. What remains for it to catch is a nested run that died before
reaching its own sweep, and that is exactly the case with no ancestry.

**A stale quotation in this document.** §3 calls `ps -eo state=,command=` *"the observer's
exact query"*. It was, and is not any more: the read half now asks for `ppid` as well.

**The repair, and how it was proved.** Both halves carry a committed arm and a removal
proof, and each negative arm is paired with a positive one, because a scope tight enough to
find nothing satisfies the negative arm alone. Against the same plant this finding used:
**10 of 10 passed and 10 of 10 decoys survived**, against **0 of 3 and 0 of 3** for the
unrepaired file run beside it under the identical harness — same signature, `assert 'ALIVE'
== 'DEAD'`. The pre-existing proof for the crash arm still reports `proved`, which is the
positive control that the read half still finds its own child.

## 9. Amendment — incident 2's candidate A is measured and **ruled out**, and a third baseline dirtier is confirmed that neither recorded candidate names

**Date**: 2026-08-11, later the same day. §5 ranked incident 2 as *"two candidate
mechanisms, neither bound to the sweep"*. One of the two has now been **measured**, and its
cost is bound: **3 arms and 14 outcomes**, against the 58 arms and 234 outcomes it would
have to reach. §5's conclusion does not move; it now rests on a count instead of on a
reading. **Repairs nothing** — the defect in §9.3 is left standing and §9.5 states the
options rather than taking one.

**Platform**: `macOS-26.2-arm64`, euid `501`, CPython `3.12.11` from
`/Users/djperussina/Code/function2agent/.venv/bin/python3`. Measurements were taken in
`mktemp -d` work trees built the way the harness builds its own, never in the shared tree;
the shared tree's `tests/removal_proofs.sh` was **not modified** for either condition.

### 9.1 Why this cost two pytest runs and not two sweeps

Both quantities the candidate must reach are fixed by the **baseline**, which the harness
takes before any tamper. `_py_failed` is a count over the baseline text. An UNUSABLE arm is
decided by a lookup in `report_unrunnable` that returns **before** `apply_tamper` and before
the arm's own pytest invocation — so UNUSABLE arms are the *cheapest* arms in a sweep, not
the dearest. The sound measurement is therefore **one full-suite pytest run per condition**.
Each took ~65s and produced **1879 Python outcomes**.

The UNUSABLE counts in §9.2 are **derived from those two measured baselines using the
harness's own scorer**, not from a reimplementation of its rule: `_escape` and `baseline_py`
were extracted verbatim from `tests/removal_proofs.sh` and run under `bash` against each of
the **336 Python arms** (346 declared, 10 of them Go). **No sweep was completed, and this is
a derivation over a measured baseline rather than an observed sweep total.** Its fidelity has
one independent check: it reports **13 SKIPPED**, which is the `"skipped": 13` every
committed post-guard summary record carries.

### 9.2 Pre-registered against measured

The predictions were written before any measurement, in `/tmp/specsprobe-prereg.md`. They
are reported here unadjusted.

| Condition | Quantity | Pre-registered | Measured | |
|---|---|---|---|---|
| intact control | Python outcomes not passing | 1 | **2** | miss |
| broken run | Python outcomes not passing | 12 | **14** | miss |
| broken run | UNUSABLE arms | 3 | **3** | hit |
| intact control | UNUSABLE arms | 0 | **0** | hit |

**Both misses are the same `+1`, twice.** The broken run's 14 decompose as: **10**
`test_egress_policy.py` tests that call `_contract()` — exactly the 10 the pre-registration
enumerated; **1** retroactive-copy-list guard, as predicted; **2** for the floor in §9.3
where 1 was predicted; and **1** the pre-registration did not derive at all —
`test_every_declared_removal_proof_still_names_a_live_site_and_a_live_test`, because one
arm's **tamper target** is `specs/002-spec-aware-agent-runtime/contracts/egress-policy.md`.
The pre-registration enumerated every test that *reads* `specs/` and did not ask which arms
*write* there.

**Candidate A is ruled out as the cause of the 234/58 sweep.** 3 arms against 58 and 14
outcomes against 234 — one and a half to two orders of magnitude short in both dimensions,
in the direction that cannot be closed by a larger tree. This is also the prediction
`f3f1c89` already constrained: it attaches the `specs/` omission to *"three more of the
same"*, and the three arms measured here are exactly the three the pre-registration named.
**Incident 2's cause remains undetermined**, and this amendment does not reach for a third
mechanism for it.

### 9.3 A deterministic work-tree floor, confirmed on two platforms

**Every intact sweep has a baseline-failure floor of 2, and the verdict does not show it.**
Two tests resolve a repository root from `__file__`'s ancestors, which under the harness
resolves to the **work tree** and not to the repository:

| Test | Reads | Why it fails in `$WORK` |
|---|---|---|
| `test_removal_proof_scoring.py::test_the_two_path_lists_between_them_account_for_this_tree` | `_unlisted(REPO)` | `$WORK` holds `.summary-records` and `.baseline-pytest.txt`, in neither path list; `$WORK` is no repository, so `git check-ignore` exits **128** (measured) and `&& continue` is not taken, so both are **named** |
| `test_seccomp_overhead_record.py::test_the_durable_record_is_the_tracked_one_and_the_latest_is_not` | `REPO / ".gitignore"` | `.gitignore` is in `NOT_NEEDED_PATHS`, so it is never copied — `FileNotFoundError` |

Both dotfiles do exist when the baseline runs: `.summary-records` is truncated well before
it, and `.baseline-pytest.txt` is the baseline's own redirect target — **measured, not
assumed**, by having a process list its own working directory through the same redirect
shape and finding the target already present. `.baseline-go.txt` is created *after* the
Python baseline and so is not part of this floor. The assertion names **2** paths and costs
**1** outcome; the second row costs the other.

> **Corrected in §10, on two counts.** The harness wrote **four** scratch files into `$WORK`
> and not two — `.tamper-err` is the fourth — and only the two above exist by baseline time,
> which is why the floor was 2 and not 4. And the count in this section's heading is a
> property of the revisions it was measured at, not of the instrument: §10 takes it to **0**.

**Confirmed independently on CI.** The `removal proofs` job at `5fa07bb` printed `baseline
1879 python outcomes (2 not passing), 226 go outcomes (0 not passing)` and then `346 proved,
0 unproven`, and the job concluded **success**. Same total and same count as the local
control, on Linux rather than macOS, which is what a floor built out of `mktemp -d` and a
`NOT_NEEDED_PATHS` entry should do. *(The harness does not name its baseline failures, so
that CI's two are these two is inferred from the identical count and platform-independent
mechanisms, not observed.)*

**Why it is invisible, in two independent ways.** No proof arm names either test — verified
by extracting all 346 declarations and searching their test selectors — so the floor
produces baseline failures with **zero UNUSABLE arms**. And the tail block that would
surface `_py_failed` to a reader is gated on `[ "$UNUSABLE" -gt 0 ] && [ "$_py_failed" -gt 0
]`, so with `UNUSABLE=0` it never prints. The count appears once, mid-run, on the `baseline`
line, and nowhere in the verdict.

### 9.4 What the floor is **not** evidence for

**It cannot explain the 234.** The guard that produces the first row and the record of the
234 sweep **arrived in the same commit**, `f3f1c89` (`2026-08-10 08:00:14 −0600`); the test
did not exist while that sweep ran. The second row's test is later still — `73e9af3`,
`2026-08-10 16:47:20 −0600`, *after* the last committed summary record. So the floor is a
fourth condition presenting through the baseline, not a candidate for incident 2, and must
not be written up as one.

**One thing it leaves open.** The four committed post-guard summary records read
`python_not_passing` **1, 1, 2, 2** — and the two 2s are timestamped `10:17:54` and
`10:29:15`, both **before** `73e9af3`. So the second failure in those two sweeps is *not*
the `.gitignore` row and is **not established here**.

### 9.5 The repair is owed an owner, and this pass did not take it

> **Superseded by §10, which takes it.** Both rows are closed and the floor reads **0**. The
> options table below is left standing because §10 reports which option it took and which it
> declined, and that is unreadable without the alternatives it was choosing between.

Two rows, and the cheap fix reaches only one of them, which is why none was taken.

| Row | Options |
|---|---|
| partition test | (a) add the harness's own scratch dotfiles to `NOT_NEEDED_PATHS` — one line, but it teaches the guard to ignore names in the repository root too; (b) have the harness keep its scratch files **outside** `$WORK`, which is where they belong and is not one line; (c) assert against the repository root rather than `__file__`'s ancestor, which changes what the guard covers |
| `.gitignore` row | (a) move `.gitignore` into `REQUIRED_PATHS`, which changes the copy list the guard exists to police; (b) have the test decline when the file is absent, which weakens it in the shared tree too |

Option (a) on the first row alone would leave the floor at 1 and the headline unchanged — a
green verdict over a non-zero baseline-failure count — so a partial repair here buys
nothing and hides half the evidence for the other half.

## 10. Amendment — the floor is **repaired**, both rows, and it reached **0** rather than lower

**Date**: 2026-08-11, later the same day. §9.5 left this owed to an owner; it is taken here.
Both rows are closed in one commit, and the harness's own `baseline` line reads **0 not
passing** where it read **2**. The invisibility §9.3 describes is closed as a separate
mechanism from the failures themselves: what hid them now has a guard that fires in the
ordinary suite, not in a baseline nothing prints.

**Platform**: `macOS-26.2-arm64`, euid `501`, CPython `3.12.11` from
`/Users/djperussina/Code/function2agent/.venv/bin/python`. Every figure below is read off an
instrument's own output, never computed as a baseline plus a delta. The two sweeps are
end-to-end runs of `tests/removal_proofs.sh` in the shared tree: **before** at `7b809e9`,
**after** at `0c3c33c` plus this commit. The only commits between those two states are a
date-fragility fix in one test and a `tools/README.md` edit, neither of which moves either
figure.

### 10.1 Before and after, and the target was 0

| | before (`7b809e9`) | after (this commit) |
|---|---|---|
| `baseline … python outcomes (… not passing)` | `1887` outcomes, **2** not passing | `1888` outcomes, **0** not passing |
| go outcomes | `226`, 0 not passing | `226`, 0 not passing |
| verdict | `337 proved, 0 unproven, 13 skipped` | `338 proved, 0 unproven, 13 skipped` |

**Compared arm for arm and not on totals**, from each run's own JSON record: **0** arms lost,
**0** arms changed outcome, **1** arm added — the new guard's, and it scored `proved`. The one
extra Python outcome is that guard's own test. A change that moved one arm from proved to
refused while another moved the other way would leave both totals exactly where they are,
which is why a total is not evidence here.

### 10.2 The floor decomposed **1 + 1**, established on a second instrument

§9.3 attributes one outcome to each row by reading the two assertions. That is now measured,
because `tools/proof_attribution.py` builds a work tree from the **same** declared path set
and writes **no** scratch files into it. Read off that tool's own baseline line at `8c802e2`:

| Work tree | Scratch files in it at baseline time | `not passing` |
|---|---|---|
| the harness's | 2 | **2** |
| `proof_attribution`'s, copy list read off `REQUIRED_PATHS` | none | **1** |

The remaining 1 was **named rather than inferred**: in a work tree built from those eight
declared paths, `test_the_durable_record_is_the_tracked_one_and_the_latest_is_not` fails with
`FileNotFoundError` on `…/.gitignore`, and the partition test in the same run **passes**. So
the `.gitignore` row is worth 1 on an instrument that has no scratch files at all, the
partition row is worth the difference, and the two are additive.

### 10.3 Which of §9.5's options was taken, and what the cheap ones cost

| Row | Taken | Why not the cheaper one |
|---|---|---|
| partition test | **(b)** — `mktemp -d` now yields `$SCRATCH`, the work tree is `$SCRATCH/tree`, and all **four** scratch files live under `$SCRATCH` beside it. One trap on `$SCRATCH` still covers every exit path, including the two `exit 2` aborts | (a) declaring the four names in `NOT_NEEDED_PATHS` is one line, but that list is consulted for the **repository** root as well — the population `unlisted_top_level` exists to police — so it would teach the guard to ignore those names where they would be genuine omissions. (c) asserting against the repository root would make the work-tree run stop asserting about the work tree |
| `.gitignore` row | **(a)** — moved from `NOT_NEEDED_PATHS` into `REQUIRED_PATHS` | `REQUIRED_PATHS` means *the suite reads it*, and the suite demonstrably does; this corrects a miscategorisation rather than distorting the list. (b) having the test decline when the file is absent is a test that skips exactly where it would fail |

**The not-needed list's own comment was wrong, and how it was wrong is the transferable
part.** It recorded `.gitignore` as read by nothing under `tests/`, *"verified 2026-08-10 by
grep for path literals and for segment joins off a repo-root variable"*. The one reader
reaches it as `REPO / ".gitignore"` — a third form neither grep covered. The list is now
annotated with that, because a path sits on it because somebody looked once, and looking once
is not a guard.

### 10.4 The guard, so a fifth scratch file cannot reintroduce this quietly

`test_the_harness_writes_no_scratch_files_into_the_work_tree` greps the harness for a quoted
work-tree dotfile path and fails on any. Matched as a pattern rather than as the four known
names, so a name nobody has thought of is caught too.

It is asserted **statically, in the ordinary suite**, and that placement is the whole point.
The partition test already reports this defect — correctly — but it only runs inside a sweep,
and a sweep's baseline failures print nowhere a reader looks, which is how this survived every
run the instrument has ever made. The guard carries a removal proof, and that proof's tamper
puts `BASELINE_PY` back inside the work tree; it scored `proved`, which is the positive
control that the guard fails on the code it replaces.

Two things worth recording about writing it. Its proof's tamper spells `$WORK` as `\x24WORK`,
because a snippet spelling the path out puts the pattern in the **untampered** source — a
guard defeated by the declaration of its own proof. That was **observed, not foreseen**: the
first version of the comment explaining the escape quoted the pattern, and the guard fired on
the comment.

### 10.5 What §9.4 leaves open is unchanged by this

The two committed post-guard records at `10:17:54` and `10:29:15` read a baseline of 2 while
the `.gitignore` mechanism's test did not land until `73e9af3` at `16:47:20`, so their second
failure was something else and is still not established. Settling it needs one thing and not
an investigation: a sweep's baseline transcript from that window, which nothing retained —
`$WORK` is removed by the trap and only the counts reach the JSON record. Absent that, it
would have to be reconstructed by running the suite in a work tree built the way the harness
built one at those commits, which is a measurement nobody has asked for. **Left open,
deliberately, and cheap to close if a reason appears.**
