# Finding 033 — the WAL first-open race and the engine-exception leak both exist at `SessionTable`, measured; the race is **unreachable by current usage and by nothing else**, and the leak is **not owed a local repair** because obligation 2's own scanner exempts this file as *a known migration*. The load-bearing result is negative: the correct repair is the migration onto `Repository`, and a local patch here is work the migration deletes

**Date**: 2026-08-06
**Feature**: 002. Measures [`src/supervisor/session_table.py`](../../../src/supervisor/session_table.py)
as it stands at `ff202ae`, against the defect closed one module over at the same commit in
[`src/contracts/repository.py`](../../../src/contracts/repository.py). **Reports; decides nothing,
and changed no behaviour.**
**User Story**: US1, by way of FR-050 layer 1 and layer 2, T-06's single-writer ownership map, and
T016's second obligation.
**Owner decision**: **none is minted here and the register was not edited.** The one question this
raises for an owner — *when does `session_table.py` migrate onto `Repository`* — already has a
recorded answer and an existing home (see [§5](#5-job-3--the-answer-is-already-recorded-and-it-says-migrate));
no new number is attached, on [finding 026](./026-pivot-root-check-measured.md)'s rule that a number
copied into a finding goes stale in the direction that tells the next author to reuse a taken one.
**Model spend**: **$0.0000.** No model was called and no credential was read. Four local process
runs totalling about 55 seconds of wall clock, most of it spent deliberately waiting out busy
timeouts.
**Method**: **planted locks, not raced conditions.** The race measured at the repository layer never
approaches certainty — 24 of 40 trials at three parties, 28 of 40 at eight, plateauing near two
thirds — so every arm here *constructs* the losing condition with a second connection holding a real
lock, exactly as
[`tests/integration/test_store_concurrent_writers.py`](../../../tests/integration/test_store_concurrent_writers.py)
does, and reads the outcome rather than hoping for it. The reachability census in
[§3](#3-job-1b--is-it-reachable-a-census-of-every-constructor-in-the-tree) is source reading, and is
labelled as such because it is the one part of this document not carried by a measurement.
**Reproduction**: the three probe scripts are quoted in full in
[§7](#7-reproduction-the-three-probes-in-full). They were run from the repository root with
`PATH="$PWD/.venv/bin:$PATH"` and are **not** committed — they measure a defect that is not being
repaired, so committing them would add three files the migration also deletes.
**Revision discipline**: `main` was at `ff202ae`, clean, when this pass began. Every arm was taken
with `src/` clean of any edit by this pass. The only source file this pass touches is a **comment**
in `session_table.py` correcting a sentence this finding falsifies; no behaviour changed, and the
suite's totals are identical before and after.
**Numbering note**: `032` was the high-water mark across `specs/*/findings/`, established by listing
the whole tree (`ls specs/*/findings/*.md`) rather than by reading a number out of a document or out
of the brief that commissioned this pass. `033` was free at that moment and re-checked free
immediately before saving.

---

> ## THE SHORT VERSION
>
> Four questions were asked. Three have affirmative answers that do not add up to a repair, and the
> fourth is why.
>
> | Question | Answer | Evidence |
> |---|---|---|
> | Does the busy-handler bypass reach `executescript`? | **Yes, identically.** `executescript` changes nothing. | Refused in **0.165 ms** with `SQLITE_BUSY` under a held `RESERVED`; **5139 ms** — the whole busy timeout — under `EXCLUSIVE`. The bare `execute` form measured 0.132 ms / 5147 ms on the same runs. |
> | Do methods leak `sqlite3` exceptions? | **Yes — all six writes, plus construction. Neither read does.** | `create`, `mark_running`, `mark_interrupted`, `mark_resumed`, `renew`, `terminate` each raised `sqlite3.OperationalError` against a real `EXCLUSIVE` holder; `get` and `resolve` both returned normally. |
> | Is the race reachable in this system? | **No — and by *current usage*, not by construction.** | The race needs a **brand-new** file. A second opener on an **already-WAL** file succeeds in **0.28 ms even under an `EXCLUSIVE` lock**, and the crash fixture's real shape gave **0 failures in 200 second-opens**. Every one of the eight constructors in the tree creates the file sequentially first. |
> | Does the derived engine-exception obligation bind this module? | **No.** Obligation 2's own check *names this file and skips it*. | [`tests/invariants/test_writer_ownership.py`](../../../tests/invariants/test_writer_ownership.py):282 — `root / "supervisor" / "session_table.py",   # predates T016; see below`. |
>
> **So the repair is not here.** The exemption is not a carve-out on the merits; it is a deferral,
> and the invariant test says so in its own failure message: *"it is a **known migration**, recorded
> here rather than hidden by widening the scan."* The recorded path to compliance is moving this file
> **inside** the repository layer, which already has the translation and the convergence loop. Adding
> a second copy of both to `SessionTable` would be building the thing the migration removes.
>
> **What this pass therefore changed: one comment.** The module carried a note reading *"the
> cross-process case is still unmeasured."* It is measured now, and that sentence would otherwise
> keep telling the next reader there is nothing to know.

---

## 1. What was already known, and what was open

At `ff202ae`, [`Repository._enter_wal`](../../../src/contracts/repository.py) closed a measured
defect: `PRAGMA journal_mode=WAL` on a brand-new database file is refused with `SQLITE_BUSY`
**immediately** when several processes run it at once — 21 of 120 concurrent first opens, 0 of 120
once the file is already in WAL. The refusal arrives in about 100 microseconds with a five-second
busy timeout in force, because the conversion runs inside a read transaction and SQLite deliberately
bypasses the busy retry on that path. That pass repaired the repository layer and was correctly
scoped to it.

`SessionTable.__init__` does not use `Repository`. It calls `sqlite3.connect` directly and then
`self._conn.executescript(SCHEMA)`, and `SCHEMA`'s **first statement** is `PRAGMA journal_mode=WAL`:

```python
SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS session (
...
```

So the protection does not reach it. Two things were open, and they are independent: whether the
*mechanism* survives the change of call form, and whether the *configuration* it needs occurs.

## 2. Job 1a — the mechanism reaches `executescript` unchanged

`executescript` is not `execute`. CPython issues a `COMMIT` before running the script and then steps
the statements in sequence, and whether that alters the busy behaviour was unverified. It does not.

Measured on CPython 3.12.11 / SQLite 3.53.3, against a store that exists, has never been in WAL, and
has a second connection holding a real lock:

| call form | holder | outcome | time |
|---|---|---|---|
| `execute("PRAGMA journal_mode=WAL")` | `IMMEDIATE` (RESERVED) | `OperationalError` / `SQLITE_BUSY` | **0.132 ms** |
| `executescript(SCHEMA)` | `IMMEDIATE` (RESERVED) | `OperationalError` / `SQLITE_BUSY` | **0.165 ms** |
| `SessionTable(path)` | `IMMEDIATE` (RESERVED) | `OperationalError` / `SQLITE_BUSY` | **0.216 ms** |
| `execute("PRAGMA journal_mode=WAL")` | `EXCLUSIVE` | `OperationalError` / `SQLITE_BUSY` | **5146.543 ms** |
| `executescript(SCHEMA)` | `EXCLUSIVE` | `OperationalError` / `SQLITE_BUSY` | **5139.532 ms** |
| `SessionTable(path)` | `EXCLUSIVE` | `OperationalError` / `SQLITE_BUSY` | **5178.812 ms** |

Both classifications the repository layer distinguishes are reproduced exactly. Under `RESERVED` the
busy handler is bypassed and the refusal is four orders of magnitude inside the timeout; under
`EXCLUSIVE` the shared lock underneath the conversion is also blocked, the handler *is* consulted,
and it runs to exhaustion. `executescript` sits on the same side of both.

**One consequence is worse here than at the repository.** The pragma is the script's first statement,
so the abort happens before `CREATE TABLE session` runs. Measured: after a failed construction the
file contains `['_seed']` and no `session` table at all. Construction raises either way, so no
half-built object escapes today — but a caller that ever caught and continued would be reading a
store with no schema in it.

## 3. Job 1b — is it reachable? A census of every constructor in the tree

The defect needs two processes to first-open the same **brand-new** file simultaneously. That is a
configuration, and it either occurs or it does not.

**First, the boundary is sharper than "brand-new helps".** A second opener on a file that is already
in WAL succeeds *even against an `EXCLUSIVE` holder*:

| file state | holder | outcome |
|---|---|---|
| brand-new (rollback mode) | `IMMEDIATE` | refused, 0.16 ms |
| **already WAL** | `IMMEDIATE` | **succeeded, 0.16 ms** |
| brand-new (rollback mode) | `EXCLUSIVE` | refused, 5185 ms |
| **already WAL** | `EXCLUSIVE` | **succeeded, 0.28 ms** |

`PRAGMA journal_mode=WAL` is a no-op when the mode already matches, and `CREATE TABLE IF NOT EXISTS`
against an existing table writes nothing — so a warm open takes no write lock and has nothing to
contend for. The race is not "concurrency on this file"; it is specifically **concurrency on the
conversion**, which happens once in a file's life.

**Second, the census.** Source reading, not measurement. Every construction of `SessionTable` in the
tree:

| site | processes | file state at open |
|---|---|---|
| **`src/` — none.** No production code constructs it. `lease.py` imports the type for annotation; `runner.py` and `capability.py` import only `capability_digest`. | — | — |
| `tests/unit/test_runner.py`, `test_cancellation.py`, `test_loop.py`, `test_session_store.py` | one | per-test `tmp_path`, created by that process |
| `tests/fixtures/resume_session.py`, `tools/wall_clock_ceiling_probe.py` | one | own root, created by that process |
| `tests/fixtures/session_conformance.py` (regeneration) | one | `unlink` then create, single process |
| `tests/unit/test_session_conformance.py` | one | the **committed** fixture — header bytes 18/19 are `2,2`, i.e. already WAL, so the conversion never runs |
| `tests/integration/test_lease_revocation.py` — the SIGKILL crash arm | **two** | parent creates it, *then* spawns the child; the child's open is warm |

The crash arm is the only genuine two-process configuration, and it is the one worth testing rather
than arguing. Measured in its actual shape — a creator holding a live read-write connection while a
second opener runs, no planted lock — **0 failures in 200 second-opens.**

**Third, what enforces this.** The brief asked for the distinction between *unreachable by current
usage* and *unreachable by construction*, because only the second is durable. The honest answer is
that it is almost entirely the first:

- **By construction:** the proxy. It is the other party the class docstring names, and
  [`src/proxy/session.go`](../../../src/proxy/session.go):58–64 opens `mode=ro&_pragma=query_only(1)`
  — doubly enforced, with the comment saying why — so it can neither create the file nor convert it.
  A `mode=ro` open of a nonexistent file fails outright. The proxy can never be a party to this race.
- **By current usage only, with nothing enforcing it:** everything else. No rule, test or assertion
  anywhere says the file must be created before a second writer attaches. It is true of all eight
  constructors because each happens to do it, and it would stop being true the moment a supervisor
  daemon existed that two processes could start — which is exactly the deployment the class docstring
  already anticipates ("Opens read-write; the proxy opens `?mode=ro`") and which does not exist yet.
- **Incidentally:** no `pytest-xdist` is installed, so no parallel test run can collide two
  constructors on the one fixed shared path.

So: **not reachable today, and not protected against tomorrow.** The reason it is nonetheless not
repaired here is [§5](#5-job-3--the-answer-is-already-recorded-and-it-says-migrate), not the
unreachability alone.

## 4. Job 2 — the leak inventory, and whether the obligation reaches this module

### 4a. What leaks

Against a second connection holding a real `EXCLUSIVE` lock, with a 1-second busy timeout:

| method | outcome |
|---|---|
| `get` | **returned normally** |
| `resolve` | **returned normally** |
| `create` | `sqlite3.OperationalError` — `SQLITE_BUSY: database is locked` |
| `mark_running` | `sqlite3.OperationalError` — `SQLITE_BUSY: database is locked` |
| `mark_interrupted` | `sqlite3.OperationalError` — `SQLITE_BUSY: database is locked` |
| `mark_resumed` | `sqlite3.OperationalError` — `SQLITE_BUSY: database is locked` |
| `renew` | `sqlite3.OperationalError` — `SQLITE_BUSY: database is locked` |
| `terminate` | `sqlite3.OperationalError` — `SQLITE_BUSY: database is locked` |
| `__init__` | `sqlite3.OperationalError` — `SQLITE_BUSY: database is locked` |

This is structurally the same shape the repository layer had: **every write leaks, no read does.**
The reads survive for the reason WAL was chosen — a WAL reader does not block on a writer — which is
the same reason `Repository.select` was the one method that never leaked.

**The consequence worth naming, if a second writer ever existed.**
[`LeaseRenewer._loop`](../../../src/supervisor/lease.py):99–107 catches `Exception`, records it in
`stopped_because`, and **returns** — permanently. A momentary `SQLITE_BUSY`, which is precisely the
class the repository layer labels *"retrying is reasonable"*, would therefore end a live session's
renewal for good. That is fail-closed and so not unsafe; it would revoke a healthy session's
authority on transient contention. It is unreachable for the same reason the rest of this is — the
renewer is the only writer in the only two-process configuration — and it is recorded because it is
the concrete harm the migration removes, not a hypothetical one.

### 4b. Does the derived obligation bind here? No — and the reason is in the check itself

The obligation is derived, not written in the contract's own words. `repository.py`:17–28 is explicit
that obligation 2 *"is about SQL and its check is a scanner over source text"*, and that the
exception rule is an extension from its **reason**: a caller writing `except sqlite3.OperationalError`
is edited when the substrate moves for exactly the reason a caller holding SQL is. The question is
whether that reasoning reaches a module that never claimed to be the repository layer.

**It does not, and the decisive evidence is that obligation 2's own check already answered.**
[`test_no_engine_specific_sql_lives_above_the_repository`](../../../tests/invariants/test_writer_ownership.py):280–305
enumerates the files the scanner skips, and `session_table.py` is the second entry. This is not an
oversight — the file is full of `SELECT`, `INSERT INTO`, `UPDATE ` and `PRAGMA `, every one a token
`_SQL_TOKENS` matches, so it was exempted deliberately and with a stated reason.

The argument, in three steps:

1. **A derived rule cannot bind more widely than what it is derived from.** The exception rule's
   entire warrant is obligation 2's reason. Where obligation 2 does not apply, the reason is not in
   force, and the derivative has nothing to stand on. Obligation 2 does not apply to this file, by
   the explicit decision recorded in its own check.
2. **The reason itself is currently vacuous here.** Obligation 2's reason is about *callers* being
   coupled. Grepping the tree for `except sqlite3` and `sqlite3.OperationalError` outside
   `repository.py` and the concurrent-writer probe returns **exactly one hit**, and it is a removal
   proof's description string, not code. Nobody catches an engine exception from `SessionTable`. The
   coupling the obligation exists to prevent has not occurred.
3. **But the exemption is a deferral, not a carve-out — which is what settles the repair.** The
   invariant test's failure message reads: *"`session_table.py` is permitted because it was built
   before T016 and is the supervisor's own store; it is a **known migration**, recorded here rather
   than hidden by widening the scan."* The file is not outside the layer on the merits. It is
   outside it **pending relocation into it**. So the recorded route to compliance is not "extend the
   rule to this module from outside" but "move this module inside the layer that already holds the
   rule."

**Where that lands.** The obligation does not bind today, and it will bind the moment the migration
happens — by the file becoming part of the layer, not by the rule being copied. Both readings point
away from a local patch.

## 5. Job 3 — the answer is already recorded, and it says migrate

The larger question was whether `SessionTable` should simply use `Repository`, or whether it
deliberately sidesteps that layer for a reason recorded somewhere. **It is recorded, in two places,
and both say the same thing.**

- The module's own docstring: *"What is pulled forward is one table and its writer; the repository
  interface of T016, the ownership map of T017 and the concurrent-writer probe of T050 are **not**
  here and are still owed."*
- The invariant test's exemption, quoted above: *"a known migration."*

So this is not a deliberate architectural separation. It is a pull-forward with a recorded debt, made
because FR-050 layer 1 needed the table before the layer under it existed. Two of the three things it
named as owed have since landed: T050's probe is
[`tests/integration/test_store_concurrent_writers.py`](../../../tests/integration/test_store_concurrent_writers.py),
and T016's interface is `Repository`. The migration is the remaining one.

**Recommendation, and no refactor performed.** `SessionTable` should move onto `Repository`, and
that move — not a patch here — is what closes everything in [§4a](#4a-what-leaks). It is not folded
into this pass, for reasons that are about sequencing rather than effort:

- The migration is not mechanical. `Repository` prepends `tenant_id` and `deployment_id` to **every**
  table it creates and filters every read by them; `session` already carries both as ordinary columns
  written by the caller, and `resolve()` looks a row up by `capability_sha256` **without** a tenant
  predicate — which is the point, because the proxy resolves an opaque handle before it knows whose
  it is. Reconciling that with FR-035's scope columns is a design question, not an edit.
- The Go proxy reads this exact schema by column name, and
  [`tests/fixtures/session_conformance.sqlite3`](../../../tests/fixtures/) is a **committed
  cross-language conformance vector** keyed to it. A schema change is a two-language change plus a
  regenerated fixture.
- `Repository` requires a declared role and the T017 ownership map; `session` is not in it.

**A local patch is therefore throwaway.** Reproducing `_engine_errors`, the four `StoreUnavailableError`
subclasses and the `_enter_wal` convergence loop inside `SessionTable` would be roughly 120 lines
duplicating a module this file is scheduled to start using, plus removal proofs for each new
mechanism, all of which the migration then deletes. That is the outcome the brief asked to avoid
paying for, and this finding exists so it is not paid twice.

## 6. What this pass changed, and what it did not

**Changed: one comment**, in `session_table.py`. The note at lines 87–89 read:

> This is not a substitute for T050's concurrent-writer probe. One process with one lock is the
> single-writer case T-06 assumes; the cross-process case is still unmeasured.

The last clause is now false in both halves — T050's probe has landed, and the cross-process case is
measured above. A stale "unmeasured" is worse than silence: it tells the next reader there is nothing
to find. It is replaced with what was measured and where the repair belongs.

**Not changed: any behaviour.** No error translation, no convergence loop, no busy-timeout constant,
no schema. Suite totals are identical either side of the edit.

**No removal proof added, and the reason.** Proofs guard *removable mechanisms* — a guard that could
be deleted while the suite stayed green. This pass added no mechanism. `EXPECTED_PROOFS` in
[`tests/unit/test_tamper_matching.py`](../../../tests/unit/test_tamper_matching.py) is unchanged at
**163**, read from the guard's own transition message rather than computed.

**No test added, and the reason.** The only tests that could be written here are the two bad ones. A
test pinning the *current* behaviour would enshrine six leaking methods as expected and turn the
migration into a test failure; a test pinning the *desired* behaviour would require the local patch
this finding argues against. The measurement is carried by this document and reproducible from
[§7](#7-reproduction-the-three-probes-in-full), which is what a finding is for.

## 7. Reproduction: the three probes in full

Run from the repository root with `PATH="$PWD/.venv/bin:$PATH" python <file>`. None is committed; each
is a dozen lines around a planted lock.

**Probe A — does the bypass reach `executescript`** ([§2](#2-job-1a--the-mechanism-reaches-executescript-unchanged)).
Create a store, run `CREATE TABLE _seed`, commit, close — this is a file that exists, has never been
in WAL, and is unlocked. Open a second connection and `BEGIN IMMEDIATE` (or `EXCLUSIVE`). Then time
each of `execute("PRAGMA journal_mode=WAL")`, `executescript(SCHEMA)` and `SessionTable(path)` on a
third connection, recording `type(exc).__name__` and `exc.sqlite_errorname`. Finally, after a failed
`SessionTable(path)`, release the lock and read
`SELECT name FROM sqlite_master WHERE type='table'` to see the schema was never created.

**Probe B — the leak inventory** ([§4a](#4a-what-leaks)). Build a store with `SessionTable`, seed one
row, open a second `SessionTable` as the victim, and take `BEGIN EXCLUSIVE` on a third connection
with `timeout=1.0`. Call each of the eight methods in turn inside
`try/except sqlite3.Error/except Exception`, appending to `leaked` or `succeeded`. Six writes land in
`leaked`; `get` and `resolve` land in `succeeded`. Expect about 30 seconds of wall clock — each
leaking write waits out the busy timeout, which is itself part of the observation.

**Probe C — the warm case and the crash fixture's real shape**
([§3](#3-job-1b--is-it-reachable-a-census-of-every-constructor-in-the-tree)). For each of
`IMMEDIATE` and `EXCLUSIVE`, and for each of a rollback-mode file and one already converted by a
prior `SessionTable(path).close()`, hold the lock and time a second `SessionTable(path)`. Then, with
no planted lock at all, have a creator hold a live read-write connection while 200 second-opens run,
and count failures. The committed fixture's mode is read directly:
`python -c "print(open('tests/fixtures/session_conformance.sqlite3','rb').read(20)[18:20])"` — `2,2`
is WAL, `1,1` is rollback.

## 8. What this finding does not establish

- **It measures one platform and one substrate**: CPython 3.12.11, SQLite 3.53.3, macOS (darwin
  25.2.0), APFS. The repository layer's own probe carries the same caveat, and network filesystems in
  particular are known to arbitrate SQLite locks differently.
- **The census in [§3](#3-job-1b--is-it-reachable-a-census-of-every-constructor-in-the-tree) is
  source reading**, and it is a claim about the tree at `ff202ae`. It is falsified by any new
  constructor, and nothing enforces it — which is itself the finding.
- **It says nothing about whether the migration is correctly sized.** [§5](#5-job-3--the-answer-is-already-recorded-and-it-says-migrate)
  names three obstacles found by reading; it does not estimate the work, and no band is collapsed
  here.
- **It does not establish that the leak is harmless** — only that it is currently unreached. Those
  differ, and the difference is the whole reason this is written down rather than dropped.
