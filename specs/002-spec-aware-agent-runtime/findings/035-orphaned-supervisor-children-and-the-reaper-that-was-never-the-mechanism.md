# Finding 035 — the orphans came from **one unguarded spawn site**, not from `LeaseRenewer` and not from the basetemp reaper. Two of the three relayed consequences are **false, measured**: a live orphan does **not** make its tree unreapable, and it **cannot** write into a recycled live run's directory. The third — that nothing was looking — is **true**, and was the only one worth spending a repair on

**Date**: 2026-08-09
**Feature**: 002. Measures [`tests/conftest.py`](../../../tests/conftest.py)'s basetemp hook and
[`tests/integration/test_lease_revocation.py`](../../../tests/integration/test_lease_revocation.py)'s
crash battery at `6cdd4a5`, and the repair on top of it.
**Reports and repairs.** The repairs are described in §5; nothing in the register was edited.
**User Story**: none directly. This is a defect investigation into a process leak first observed, and
deliberately not chased, by an earlier pass.
**Owner decision**: **none is minted here and no register was edited.** [OD-28](../plan.md) and task
T108 are named in §7 only to record that this work does not touch them.
**Model spend**: **$0.0000.** No model was called and no credential was read. Local process runs and
container runs only; the longest is the 273-second removal-proof harness run in §6.
**Method**: **reproduction and planting, on both trees.** Every claim in the briefing that this
document contradicts was contradicted by re-enacting it, not by reading the source that implements
it — [`tools/README.md`](../../../tools/README.md)'s named tell for an unmeasured claim is that the
claim describes *behaviour* and the evidence is a source read, and three of the claims here arrived
in exactly that shape. A comparison tree at `6cdd4a5` was created with `git worktree add --detach`
so that "before" and "after" are the same script against two trees rather than one script and one
memory.
**Reproduction**: every command is given in full in the section that uses it. The reproduction
scripts live under `/tmp` and are **not committed**; their source is reproduced verbatim in §1 and
§3 so the measurement can be repeated without them. The two behaviours they establish are committed
as tests, which is the durable form — see §5 and §6.
**Numbering note**: `034` was the high-water mark across `specs/*/findings/`, established two ways
and **no "next free number" written in any other document was consulted or trusted**. (1) Listing
every file matching `specs/*/findings/*.md` and taking the numeric prefix: max `034`. (2) A
corpus-wide boundary-anchored search for bare citations,
`rg -oNI -i -P '(?<![A-Za-z0-9-])finding[ -]0*\d+'`, match-only before sorting, per
`tools/README.md`'s note that piping `rg`'s default output to `sort -V` sorts by path and not by
number: max `034`. `035` was free at that moment and re-checked free immediately before saving.
Numbering is corpus-wide: `031` is under `specs/001-discovery-validation/findings/` and `032`–`034`
under `specs/002-spec-aware-agent-runtime/findings/`, one sequence across both.

---

> ## THE RESULT IN ONE PARAGRAPH
>
> An orphan was reproduced deterministically at `6cdd4a5`: kill the session store while the crash
> battery is between its spawn and its kill, and the child is left with **PPID 1**, still renewing.
> The cause is not `LeaseRenewer` and not the reaper. It is that
> `tests/integration/test_lease_revocation.py` was **the one file of five** that spawns a
> never-exiting child without a `try/finally` around it, so every assertion between the spawn and
> the `SIGKILL` was a leak path. The two alarming consequences in the briefing are both **false, and
> both were measured false rather than argued**. A live orphan does **not** protect its basetemp
> tree: the tree is keyed by the *pytest* pid, which is dead, and `unlink` does not consult open file
> descriptors — the reaper removed a tree with a live child holding a file open inside it, first try.
> And an orphan **cannot** contaminate a recycled path: `Repository` calls `sqlite3.connect` exactly
> once in `__init__`, so the orphan holds descriptors on inodes that were unlinked out from under it,
> and a fresh store created at the byte-identical path was **unchanged in size and mtime** across 25
> of the orphan's renewal intervals. What *is* true is that the orphan renews forever — the lease
> expiry kept advancing at the 200 ms cadence straight through the unlink — and that **nothing was
> looking**, which is the only one of the three consequences that earned a repair.

> ## THE CORRECTION THAT MATTERS MOST, STATED FIRST
>
> The briefing frames this as a **reaper** problem, and the reaper is the one component that could
> never have been the mechanism. `_reap_abandoned_basetemps` reaps **directories**. The leak is a
> **process**. Those are different objects with different lifetimes and the reaper has no predicate,
> correct or otherwise, that reaches a process. The reason the framing is tempting is that the two
> things share a pid in the reader's mind — but they do not share one in the tree: the directory is
> named for the *pytest* pid and the orphan is a *child* of it with a different pid entirely. Once
> that is separated, consequence 1 collapses on inspection and consequence 2 collapses on
> measurement, and what is left is a test that forgot a `finally`.
>
> **A second correction, smaller but load-bearing for anyone re-running this.** The whole pid-keyed
> basetemp layout and its reaper are **macOS-only**. The redirect is conditional on
> `len(tempfile.gettempdir()) + 64 > 104`; on this host `$TMPDIR` is 48 characters so the test is
> `112 > 104` and the hook fires, and in the `f2a-dev` container `$TMPDIR` is `/tmp` so the test is
> `68 > 104` and `pytest_configure` returns before touching anything. So `e4ef6e6`, the reaper, the
> recycling question and this entire finding's §3 describe a **developer laptop**, never CI.

## Contents

1. [Reproducing an orphan](#1-reproducing-an-orphan)
2. [The mechanism, named precisely](#2-the-mechanism-named-precisely)
3. [The three relayed consequences, measured](#3-the-three-relayed-consequences-measured)
4. [The reaper's liveness predicate: the hole is real, inverted, and declined](#4-the-reapers-liveness-predicate-the-hole-is-real-inverted-and-declined)
5. [The repair, and why it is at two layers](#5-the-repair-and-why-it-is-at-two-layers)
6. [Gate figures, with platform and privilege named](#6-gate-figures-with-platform-and-privilege-named)
7. [What this does not touch](#7-what-this-does-not-touch)

---

## 1. Reproducing an orphan

**The first attempt failed, and how it failed is informative.** Sending `SIGINT` to pytest mid-test
never landed inside the window — the single test finished in 0.97 s and the run reported
`1 passed`. The second attempt removed the live basetemp tree, re-enacting the pre-`e4ef6e6`
collision, and leaked a child *sometimes*: the `rm -rf` has to land between the store being written
and the parent reading it back, and on one run it landed late and the test passed.

**A deterministic version.** The battery's shape is: create the session store, spawn a child that
runs a `LeaseRenewer` against it, assert the lease is advancing, and only *then* `SIGKILL` the child.
Make the assertion fail and the kill is never reached. Removing the store is the most direct way, and
it is not artificial — it is precisely what the pre-`e4ef6e6` shared-root `rmtree` did to a
concurrent run.

```bash
python -m pytest tests/integration/test_lease_revocation.py::test_a_sigkilled_supervisor_lets_the_lease_lapse -q &
PYTEST_PID=$!
BASE="/tmp/f2a-pytest-$(id -u)/$PYTEST_PID"
# wait for the child, which means the store exists and the parent is in its sleep
while ! pgrep -f "supervisor.lease import LeaseRenewer" >/dev/null; do sleep 0.01; done
CH=$(pgrep -f "supervisor.lease import LeaseRenewer")
rm -f "$(find "$BASE" -name sessions.db)"*
wait "$PYTEST_PID"
sleep 1.5
ps -o pid,ppid,state,etime -p "$CH"
```

**Against the `6cdd4a5` worktree** — one run, first try:

```
tree=/tmp/f2a-at-head  pytest=400  basetemp=/tmp/f2a-pytest-501/400
child pid: [457]
store: /tmp/f2a-pytest-501/400/test_a_sigkilled_supervisor_le0/sessions.db
removed the store
pytest exit=1
=== survivors ===
  457     1 S      00:02
ORPHANED: child 457 outlived pytest 400
```

`PPID 1` is the whole finding in one column: the child was reparented to `init` the moment pytest
exited, and nothing in the system has a handle on it any more. The failure pytest reported is the
assertion two lines above the kill:

```
>       assert before is not None and before.honoured_at(time.time()), (
            "the lease was not being renewed before the kill, so the arm proves "
            "nothing about the kill")
E       AssertionError: ...
E       assert (None is not None)
```

**Note the pytest pid: `400`.** Pids on this host wrap into the low hundreds routinely, which is the
fact §4 turns on.

## 2. The mechanism, named precisely

**It is not `LeaseRenewer`.** The renewer runs on a **daemon thread**, and a daemon thread cannot
outlive its process — so whatever survived for four days was a *process* that happened to contain a
renewer, not a renewer that escaped. The briefing's instruction not to assume `LeaseRenewer` was at
fault was correct, and the reason it is correct is a one-word type distinction.

**It is one unguarded spawn site.** A census of every test file that starts a child which does not
exit on its own, taken at `6cdd4a5`:

| File | `try/finally` | `.kill()`/`.terminate()` | Guarded |
|---|---:|---:|---|
| `tests/batteries/test_adversarial_egress.py` | 5 | 3 | yes |
| `tests/batteries/test_ceilings_under_resume.py` | 3 | 1 | yes |
| `tests/conformance/test_provider_state_resume.py` | 4 | 1 | yes |
| `tests/integration/test_resume_sigkill.py` | 2 | 2 | yes (also `with Popen`) |
| **`tests/integration/test_lease_revocation.py`** | **0** | **0** | **no** |

(`tests/unit/test_conftest_basetemp.py` also calls `Popen`, but its child is
`[sys.executable, "-c", ""]` followed immediately by `child.wait()` — it exits on its own and is
reaped, so it is not a member of this population.)

Four of five had the guard. The fifth is the file whose two arms exist *specifically* to kill a
child from outside, which is the file where a missed kill costs the most, and it is the one that
relied on reaching the kill statement.

**Why the child then runs forever rather than dying of its own accord.** Two independent reasons,
and both had to hold: the child's body is `while True: time.sleep(0.05)`, so it has no exit path;
and the renewer keeps succeeding, so nothing inside it raises. §3.1 measures the second.

## 3. The three relayed consequences, measured

### 3.1 "The reaper cannot clean up after the exact failure that produces orphans" — **false**

The claim was that an orphan holding a live pid keeps its whole basetemp tree unreapable forever, so
the leak is self-preserving against the only garbage collection there is.

**It is not the orphan's pid that names the tree.** The directory is
`/tmp/f2a-pytest-<uid>/<pytest-pid>`; the orphan is a *child*, with its own pid, and it appears
nowhere in the path. When pytest exits its pid is dead, and the reaper's predicate — `os.kill(pid, 0)`
— correctly reports it dead.

Measured, by loading the committed hook and calling its reaper against a planted tree owned by a
dead pid with a **live** child holding a file open inside it:

```
  dead pytest pid=13165   tree=/tmp/f2a-claims-root/13165
  live orphan child pid=13166 holding a file open inside it
  tree still present after the reaper ran: False
  VERDICT: REAPED — a live orphan does NOT protect the tree
  orphan still alive afterwards: True
```

The tree went away on the first try. POSIX `unlink` does not consult open descriptors, so an open
file does not pin a directory entry — it pins an *inode*, which is a different thing and is invisible
to `os.path.isdir`.

**What *is* true, and it is the part worth keeping.** The orphan goes on renewing after its tree is
unlinked, indefinitely. The lease expiry, printed by the orphan itself from its own connection,
across the moment of the `rm -rf`:

```
  t= 2.0s  lease_expires_at=1786294268.256
  t= 2.5s  lease_expires_at=1786294268.867
  --- unlinking the whole tree now (the reaper's rmtree) ---
  t= 3.0s  lease_expires_at=1786294269.275
  t= 3.5s  lease_expires_at=1786294269.885
  ...
  t= 6.5s  lease_expires_at=1786294272.935
```

Monotonic straight through, at the 200 ms cadence the briefing described. So the *symptom* the
earlier pass saw was real and precisely reported; only its attribution to the reaper was wrong.

### 3.2 "Recycled basetemp path" — **overstated; contamination is unreachable**

This was flagged as the part that should worry us most: a four-day-old orphan writing every 200 ms
into a path that a live run has since been handed would be cross-run contamination arriving by a
route `e4ef6e6` does not cover.

**It is unreachable, and the reason is a single line.** `Repository.__init__` calls
`sqlite3.connect(str(path), ...)` once and stores the connection; `SessionTable.__init__` builds one
`Repository`; the child builds one `SessionTable` before `renewer.start()`. Grepping the whole of
`src/` finds exactly two `sqlite3.connect` call sites, one of them a read-only codegraph pin. **The
path is resolved once, at construction, and never again.** Renewal goes through the already-open
connection.

Measured end to end — orphan renewing into a path, the tree unlinked, then a **fresh store created
at the byte-identical path**, then 25 more renewal intervals:

```
== step 1: the reaper removes the tree ==
  open sessions.db fds: 4
  /private/tmp/f2a-recycle/400/sessions.db-shm 426150482
  /private/tmp/f2a-recycle/400/sessions.db     426150479
  /private/tmp/f2a-recycle/400/sessions.db-wal 426150481

== step 2: a NEW run draws the same pid and recreates the identical path ==
  size(db) size(wal) = 20480

== step 3: let the orphan renew 25 more times (5s at 200ms) ==
  size(db) size(wal) = 20480
  mtime before=1786294205 after=1786294205
  VERDICT: the live run's store was NOT touched by the orphan.
```

Those inode numbers are the answer: the orphan's descriptors point at 426150479/481/482, which no
longer have a name. The new store at the same path is a different inode, and the orphan has no way
to reach it short of re-opening by path, which it never does.

**So the phrase overstated it.** "Renewing against a recycled basetemp path" is accurate about the
*path string* and wrong about the consequence — the writes go to unlinked inodes, which is a disk-space
and CPU leak, not a contamination one. The distinction matters for the repair: had contamination been
reachable, the fix would have had to live in the renewer or the store; because it is not, a test-local
`finally` is sufficient and nothing in `src/` needs to change.

**The cost that is real.** Unlinked inodes are not reclaimed until the last descriptor closes, so a
four-day orphan holds its store, WAL and shm off the filesystem's free list for four days, invisible
to `du` and to every directory listing, while burning a wakeup every 200 ms.

### 3.3 "Nothing noticed for four days" — **true**, and the only one that earned a repair

There was nothing to notice with. A leaked child is not in pytest's report, not in the exit status,
and not in any battery. Worse, the run that leaks one is *usually red for the failure that caused the
leak*, so the one signal a reader does get points somewhere else. That is what §5 fixes.

## 4. The reaper's liveness predicate: the hole is real, inverted, and declined

There **is** a hole, and it is the opposite of the briefing's. It is not that a live orphan keeps a
dead run's tree alive — §3.1 measures that it does not. It is that **pid reuse can make a dead run's
tree unreapable**: if some unrelated process is later assigned pid 400, `os.kill(400, 0)` succeeds and
`_reap_abandoned_basetemps` correctly-by-its-own-rule leaves `/tmp/f2a-pytest-501/400` alone. On this
host pytest was assigned pid `400` (§1), so wrap is not hypothetical.

**This is already in the tree as a feature, not a bug.**
`test_a_live_process_directory_survives_another_runs_configure` asserts exactly this behaviour, and
it cannot distinguish a live owner from a recycled pid, because at the level of `kill(pid, 0)` there
is nothing to distinguish.

**Declined, on three grounds.**

1. **The mtime alternative is still beaten by `e4ef6e6`'s stated reason.** An mtime rule deletes a
   long-idle run's live tree. Nothing measured here weakens that.
2. **A predicate that *would* beat it exists, and the consequence it buys does not justify it.**
   Pairing the pid with the directory's own creation time against the process's start time
   distinguishes a recycled pid from the original owner without using mtime as the sole signal. But
   what it buys is the removal of a **stale directory whose writer is already dead** — inert, bounded,
   and self-clearing: `pytest_configure` `rmtree`s its *own* path unconditionally before recreating
   it, so the first pytest run that draws pid 400 clears the tree regardless. No correctness property
   depends on it.
3. **`e4ef6e6`'s actual safety property cannot be touched by pid reuse at all.** Its guarantee is
   that no two *live* runs share a basetemp, and pids are unique among live processes by
   construction. Reuse can only ever cause a *dead* run's tree to be spared, never two live runs to
   collide.

And the framing point from the top: none of this is the leak. Changing the predicate in either
direction would not have prevented, detected, or cleaned up a single orphaned process.

## 5. The repair, and why it is at two layers

**Layer 1 — the spawn site, which is where the defect is.** Both crash arms in
`test_lease_revocation.py` now wrap the spawn in `try/finally`, matching what the other four files in
the §2 census already did:

```python
finally:
    if child.poll() is None:  # pragma: no cover — only on an assert above
        child.kill()
```

This is the right layer because the defect is local and the pattern is already the house style — the
fix makes the outlier conform rather than introducing a new mechanism. It is also the only layer that
kills the child *when it leaks* rather than at the end of the run.

**Layer 2 — a session-scoped backstop, which is what answers §3.3.** `pytest_terminal_summary` now
sweeps for live direct children of the pytest process, kills them, and prints what it killed. Four
design points, each of which is a way the sweep could have been wrong:

- **Session scope, not per test.** Per test it would cost a `ps` per outcome across ~1300 tests to
  catch a fault seen three times in a week, and it would be *wrong*: module-scoped fixtures
  legitimately hold a child across the tests that share them. By `pytest_terminal_summary` every
  fixture is finalized, so a surviving child is a child nobody owns.
- **Standard-library helpers are exempted by asking the module, not by matching argv.**
  `multiprocessing`'s resource tracker is a direct child by design and killing it breaks a running
  interpreter; an argv match would also wrongly exempt a test whose own command line mentions it.
- **Zombies are excluded.** A `Popen` whose child exited but was not waited on is still parented here
  and is not a leak.
- **A sweep that could not run says so.** An empty list and an unavailable `ps` are the same value
  and opposite facts. Reporting the second as the first is
  [finding 034](./034-removal-proof-skip-collapse-and-toolchain-degradation.md)'s shape exactly, so
  the reason is recorded and printed, and the run is explicitly *not* scored as clean.

**Verification that the layering works as intended.** The same deterministic script from §1, against
the repaired tree:

```
tree=/Users/djperussina/Code/function2agent  pytest=1710
child pid: [1733]
removed the store
pytest exit=1
=== survivors ===
(none) child 1733 did not outlive pytest
=== did the backstop have to fire? ===
(backstop reported nothing — the test-local finally reaped it)
```

Same failure, no orphan, and the backstop did not need to act — which is the correct division of
labour. The backstop's own behaviour is exercised separately by a nested pytest run that leaks a
child on purpose.

**Would anything now notice a recurrence?** Yes, and this is the direct answer to §3.3: a run that
leaks a child prints a `child processes this run left behind` block naming the pid and its command,
and the process is dead before the run exits. It is a report on every run rather than an assertion,
because the failure it accompanies is usually the more important one.

## 6. Gate figures, with platform and privilege named

All four instruments below were run in the **privileged Linux container `f2a-dev`**, invoked with
`bash -c` and `PATH="$PWD/.venv/bin:$PATH"` per finding 034's route 2.

| Instrument | `6cdd4a5` | with this change |
|---|---|---|
| `pytest -q` | 1294 passed, 1 skipped, 4 warnings | **1301 passed, 1 skipped, 5 warnings** |
| `tests/removal_proofs.sh` | 231 proved, 0 unproven, 0 skipped, 0 unreadable | **237 proved, 0 unproven, 0 skipped, 0 unreadable** |
| `tools/check_tampers.py` | 231 declared, 0 errors | **237 declared, 0 errors, 0 warnings** |
| `tools/check_corpus.py` | 0 errors, 0 warnings | **0 errors, 0 warnings** |

The `6cdd4a5` column was **re-measured here** against a detached worktree on the same host and the
same image rather than quoted from the briefing; it reproduced the briefing's figures exactly.

**The seven new tests** are six in `tests/unit/test_conftest_child_reaping.py` covering the backstop
(detection, the kill, zombie exclusion, the resource-tracker exemption, the unchecked-sweep report,
and the end-to-end wiring via a nested pytest run) and one in `test_lease_revocation.py` that
reproduces §1's leak and observes the child's fate.

**The six new removal proofs** are the crash-arm `finally`, the kill, the zombie exclusion, the
stdlib exemption, the unchecked recording, and the `pytest_terminal_summary` wiring. Each was
observed failing tampered and passing untampered. The guard's own transition message reported the
proof set moving from 231 to 237, which is the figure `EXPECTED_PROOFS` was set to — read off the
guard rather than computed as a baseline plus a delta.

**One gate in `.github/workflows/ci.yml` is red at `6cdd4a5` and the briefing's baseline does not
list it.** `python tests/invariants/runner.py` — the first step of the `invariants` job, and the
workflow's own description of it is "the fastest signal in the repository" — exits **1** with
`tests/invariants/test_sandbox_image.py is not named by any invariant`. Measured on both trees:
`exit 1`, byte-identical output, and `git status` reports no change under `tests/invariants/`, so
this work neither caused it nor touches it. The file arrived with T096 (`7349e31`) and was never
added to `invariants.yaml`. Left alone deliberately — it is unrelated to this investigation, and
fixing a reconciliation register in a commit about process leaks would bury it. Recorded here
because a baseline that lists five instruments as green while a sixth is red is the same shape as
everything else in this document: the instrument nobody was looking at.

**The fourth warning became a fifth, and it is not this change's.** The new entry is a
`DeprecationWarning: This process (pid=1) is multi-threaded, use of fork() may lead to deadlocks in
the child` at `src/supervisor/seccomp.py:373`. It is **pre-existing and order-sensitive**, measured
three ways: running `tests/batteries` alone produces it at `6cdd4a5` **and** on this tree (3 warnings
each, identical); the full run at `6cdd4a5` does not produce it; and adding the new unit module to a
two-file selection alongside `test_seccomp_overhead.py` *removes* it. So what varies is which daemon
threads happen to be alive when that battery forks, not anything this change introduces. It is left
alone deliberately — it is a real latent issue (forking from a multi-threaded interpreter) but its
subject is thread liveness inside the pytest process, which is §7's territory.

## 7. What this does not touch

**T108 and `LeaseRenewer._loop`.** This work does not change `src/supervisor/lease.py`, or any file
under `src/`. §3.2's reading of the connection lifecycle is a *read*, used to explain why
contamination is unreachable, and the conclusion it supports was then measured independently rather
than rested on the read. The interaction with T108 is one-directional and worth stating: T108 is
about a renewal thread that **dies too easily** (one planted `SQLITE_BUSY` kills it), and this
finding is about a child process that **lives too long**. A T108 repair that made `_loop` swallow
more exceptions would make the orphans *more* durable, not less — which is an argument for the
backstop in §5 existing independently of how T108 resolves, not an argument about T108's merits.

**OD-28.** Untouched. Named only because T108's fourth route depends on it.

**The `e4ef6e6` predicate.** Declined, with the reasoning in §4.
