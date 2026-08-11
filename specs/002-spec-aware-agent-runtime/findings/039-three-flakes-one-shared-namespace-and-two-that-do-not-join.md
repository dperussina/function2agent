# Finding 039 — three non-reproducing failures were asked whether they share a cause. **They do not.** One of them — today's lease-revocation flake — is not a race at all once planted: it is a **machine-wide process-table namespace keyed on a constant string**, and it fails **10 of 10** on demand with a decoy process carrying that string. Both halves are established by planting: a concurrent run's supervisor makes this test **fail**, and this test **SIGKILLs a concurrent run's supervisor**. The other two are not joined to it and are not closed by it: one carries two candidate mechanisms on the record, neither bound to the sweep that produced it, and the other **predates `e4ef6e6` by 67 minutes**, which bounds the shared-basetemp story off it entirely

**Date**: 2026-08-11
**Feature**: 002. Measures
[`tests/integration/test_lease_revocation.py`](../../../tests/integration/test_lease_revocation.py)
against [`tests/conftest.py`](../../../tests/conftest.py), and dates three recorded
incidents against commit `e4ef6e6`.
**Reports. Repairs nothing.** No source was changed. The defect in §3 is left standing
deliberately — see §7 for why a repair is owed an owner and not this pass.
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
| 2 | A sweep took a baseline with **234 of 1653 outcomes failing**, reported *"236 proved, 58 unproven"* | `tests/removal_proofs.sh:297`, added `f3f1c89` | 2026-08-10 08:00:14 −0600 |
| 3 | One arm reported `BROKEN` on a first run and not on three subsequent ones; the classifying output had been discarded | `tests/removal_proofs.sh:766`, added `ce64490` | 2026-08-05 12:47:25 −0600 |

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
