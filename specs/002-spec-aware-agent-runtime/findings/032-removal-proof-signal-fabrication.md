# Finding 032 — the removal-proof harness scored a **killed** arm as `proved`, so a hang bought a green tick. Measured by planting a self-signalling arm, not inferred. Ten archives audited: **exactly one fabricated entry**, and the audit **cannot be completed** — archiving began at 14:07 on 2026-08-05 and the route is as old as `proof()`. The cost-table pass's "all twelve proved first run" is **true as recorded and false as meant**

**Date**: 2026-08-06
**Feature**: 002. Measures [`tests/removal_proofs.sh`](../../../tests/removal_proofs.sh) — this
repository's own instrument for deciding whether its tests are load-bearing — against the ten
per-run records archived under `tests/batteries/results/removal-proofs-history/`. **Reports; decides
nothing.**
**User Story**: none directly. This is an instrument audit; its subject is the evidence every
mechanism claim in feature 002 rests on.
**Owner decision**: **none is minted here and no register was edited.** One question below is stated
without a number attached, on [finding 026](./026-pivot-root-check-measured.md)'s rule that a number
copied into a finding goes stale in the direction that tells the next author to reuse a taken one.
**Model spend**: **$0.0000.** No model was called and no credential was read. Local process runs
only; the longest single one is the 90-second cap in §3.2.
**Method**: **planted cases and re-measurement, not source reading.**
[`tools/README.md`](../../../tools/README.md)'s rule — *"reading an instrument is not measuring it —
plant the case instead"* — is the one this document is built on, and it is also the rule the defect
below defeated for a day. The fabrication was established by planting an arm whose tamper sends its
own process `SIGTERM`; the audit was done by re-running all 147 arms under the repaired scorer and by
rebuilding the archived tree for the one arm repaired in between.
**Reproduction**: every command is given in full in the section that uses it. The archive this
document is about is committed as an exhibit at
[`tests/batteries/results/removal-proofs-history/removal-proofs-20260805T215946-4479acefc95f.json`](../../../tests/batteries/results/removal-proofs-history/removal-proofs-20260805T215946-4479acefc95f.json)
— see §2.3 for why one file out of an ignored directory is tracked, and for how to verify it is the
file the run produced.
**Numbering note**: `031` was the high-water mark across `specs/*/findings/`, established by listing
every file matching `specs/*/findings/*.md` **and** by a corpus-wide boundary-anchored search for
bare `finding NNN` citations (`rg -oNI -i -P '(?<![A-Za-z0-9-])finding[ -]0*\d+'`, match-only before
sorting, per `tools/README.md`'s note that piping `rg`'s default output to `sort -V` sorts by path
and not by number). Both return `031`. `032` was free at that moment and re-checked free immediately
before saving. **No "next free number" written in any other document was consulted**, and none was
trusted.

---

> ## THE RESULT IN ONE PARAGRAPH
>
> `proof()` read **any non-zero exit** as the tampered test having noticed the mechanism was removed.
> A killed process is also non-zero. So an arm that hung and was then killed — by a person, by a
> parent, by anything — was printed `proved`, recorded `proved`, and left the run green. **This was
> measured, not argued**: a planted arm whose tamper sends its own process `SIGTERM` printed `proved`
> and the harness exited **0**. One real arm took that route. The archived record from 21:59 on
> 2026-08-05 scores `T065 wiring — the backstop is built by the loop and never consulted` as
> `proved`, in a run recorded `status: complete` with **141 entries, 135 proved, 0 unproven** — and
> on the tree that run was taken from, that arm's tampered test **cannot return at all**. Re-measured
> here at `1208e06`: exit `124` at the 90-second cap.

> ## THE DISTINCTION THAT DECIDES THE FIX, STATED FIRST BECAUSE IT IS THE PART A READER WILL GET WRONG
>
> Three fixes landed. **The timeout is the visible repair and the signal scoring is the load-bearing
> one**, and a future reader will assume the opposite, because a hang is the symptom everybody saw
> and a cap is the obvious answer to a hang.
>
> | | what it changes | what it leaves standing |
> |---|---|---|
> | **A cap** (`tools/proof_timeout.py`) | a hang now ends in 300s with exit `124`, scored `timed-out` | **the fabrication route itself.** The cap only governs the hangs *it* ends. Any other route to a killed child — a person losing patience, an OOM kill, a segfault in tampered source, a CI runner tearing the job down — still hands `proof()` a non-zero status it reads as a demonstrated failure |
> | **Signal scoring** (`proof()` and `go_proof()`) | a status above 128 is `unproven`, reason `proof-killed-by-signal` | nothing on this route. A signalled child evaluated no assertion, and the scorer now says so regardless of who killed it or why |
>
> **The sharp way to put it: a cap makes the hang rarer; it does not make the fabricated `proved`
> impossible.** With only the cap, the arm that hung for 56 minutes would have been killed at 300
> seconds and scored correctly — and the arm somebody killed by hand at 200 seconds would still have
> been scored `proved`. The cap narrows the window. The scoring closes the hole.
>
> **And a third fix is needed because neither of the first two can manufacture a proof.** A cap turns
> a hang into a red run; it does not turn it into evidence that the mechanism is load-bearing. The
> `T065 wiring` arm still has to be *able to fail*, so its stub provider now refuses past
> `MAX_MODEL_CALLS * 10`. Untampered, the backstop trips at 3 calls and the guard is never reached;
> tampered, it raises and the arm fails in **2.46 s** (§3.2).

---

## 1. The fabrication route

### 1.1 The scorer, as it stood at `1208e06`

```sh
  output=$(python3 -m pytest "$test" -q -p no:cacheprovider 2>&1)
  status=$?
  if [ "$status" -eq 0 ]; then
    echo "  UNPROVEN  $name — the test still passes with the mechanism removed"
    ...
  elif echo "$output" | grep -qE '^(ERROR|INTERNALERROR)' && ! echo "$output" | grep -qE '[0-9]+ failed'; then
    echo "  BROKEN    $name — the tamper broke collection rather than the mechanism"
    ...
  else
    echo "  proved    $name"
```

Three branches: zero is `unproven`, a collection error is `unproven`, **everything else is
`proved`**. The `else` is the defect. It is a classifier stated as a complement — the accepting set
is "not 0 and not a collection error" — and the set it actually accepts includes every way a process
can end that has nothing to do with an assertion.

A shell reports a signalled child as `128 + signum`. `SIGTERM` is 143, `SIGINT` is 130, `SIGKILL` is
137. All three land in the `else`.

### 1.2 The planted measurement

The pass that found this did not reason about the branch. It planted an arm whose tamper makes the
tampered test send **its own process** `SIGTERM` — which is exactly what an externally killed hang
looks like from `proof()`'s side, since `proof()` sees only a status and a string.

**The harness printed `proved` and exited `0`.**

That is the whole finding in one observation: the instrument reports a positive result for an arm
that evaluated no assertion.

### 1.3 Why this is the tenth silent instrument and the first of a new kind

This corpus keeps a running count of instruments found silent on exactly what they claimed. **The
last count written into the corpus is "at least eight"**, at
[finding 030](./030-provider-state-chain-derived-not-measured.md):309 — and a phrase-anchored search
of the whole tree (`rg -i 'silent on exactly what'`) returns only that sentence and the docstring it
quotes. **This pass was briefed as the tenth. The ninth is not written down under that phrase and I
could not locate it, so the increment from eight to ten is not reconstructible from the corpus.** The
ordinal is recorded here as the brief gave it and **must not be quoted as measured**; what is
measured is the instance, not its position in the sequence.

**What is new about this one, and it is a change of kind rather than of degree.** Every prior member
of that set was *vacuous*: it passed without measuring anything — an invariant that scanned no files,
a roundtrip whose fixture handed the subject the answer, a `go test` replaying a cached result. A
vacuous instrument is silent. **This one is not silent. It speaks, and what it says is false.** It
reports `proved` — a positive claim that a named mechanism is load-bearing — for an arm that
evaluated no assertion at all.

The practical difference is who catches it. A vacuous instrument can be caught by asking *did
anything actually run*, which is the question this repository already built several checks around:
the harness's own baseline abort, `pytest_outcomes.py`, the `(cached)` assertion in the Go job. **A
false green passes every one of those.** Something ran. It produced output. It exited non-zero. Only
the *reason* for the non-zero was wrong, and the reason is exactly what the record does not keep.

---

## 2. The evidence, and how it was kept

### 2.1 The exhibit

The archive that carries the fabricated entry is
`removal-proofs-20260805T215946-4479acefc95f.json`. Its load-bearing fields, quoted so this document
reads without the file:

```json
{
  "measured_at": "2026-08-05T21:59:46-0600",
  "instrument": "tests/removal_proofs.sh",
  "status": "complete",
  "totals": { "entries_recorded": 141, "proved": 135, "skipped": 6, "unproven": 0 },
  "unproven_titles": [],
  "baseline": { "python_outcomes": 980, "python_not_passing": 0,
                "go_outcomes": 223, "go_not_passing": 0 },
  "environment": { "platform": "macOS-26.2-arm64-arm-64bit", "euid": 501,
                   "privileged": false, "python": "3.12.11", "pytest": "pytest 8.3.4" },

  "the T065 wiring entry": {
    "outcome": "proved",
    "title": "T065 wiring — the backstop is built by the loop and never consulted",
    "target_file": "src/runtime/loop.py",
    "target_test": "tests/unit/test_budget_backstop.py::test_the_loop_is_stopped_by_the_backstop_with_every_ceiling_out_of_reach"
  }
}
```

Note `status: complete` and `unproven: 0` beside a `proved` entry that could not have been earned.
The record is not damaged, not partial and not flagged. **It is a clean record of a run that
completed, and it is wrong.**

### 2.2 The archive is 78 seconds older than the commit that made it possible

`1208e06` is dated `2026-08-05 22:01:04`; the archive is stamped `21:59:46`. So this record is the
cost-table pass's own working tree, run **immediately before** it committed. That is why §3.2
rebuilds `1208e06` rather than some later tree: it is the closest committed tree to the one the
record was taken from, and it carries the arm and its tamper verbatim.

### 2.3 Why the file is committed rather than only quoted

`tests/batteries/results/removal-proofs-history/` is gitignored, and correctly so — it grows by about
40KB a run. The archive existed on one laptop and nowhere else.

Three options were available and the chosen one is a combination of two:

| option | why not, or why |
|---|---|
| **Quote the fields inline only** | Insufficient **on its own**. Findings are an `authority` namespace: `numeric-provenance` does not run here, so a quotation in a finding is self-certifying and no reader downstream can check it. The central claim of this document is a claim *about a file*, and quoting the file is not evidence of the file. Done anyway, in §2.1, so the record survives if the exhibit is ever lost |
| **Un-ignore the directory** | Rejected, and explicitly out of scope. It reopens the accumulation the ignore exists to prevent |
| **Narrow the ignore to this one file, and commit it** | **Chosen.** One exhibit is 43KB once, not per run |

**A mechanical detail that matters, because the obvious narrowing does not work.** The rule was
`tests/batteries/results/removal-proofs-history/`, a *directory* pattern, and **git does not descend
into an excluded directory** — so a `!` line naming a file inside it is never consulted. The
directory pattern had to become `dir/*` before the exemption could take effect. Verified rather than
assumed: `git add -An` over the directory now lists exactly one path, and the other eleven records
remain ignored.

**The exhibit is self-verifying, which is what makes committing it worth more than quoting it.**
`removal_proofs_summary.py::_archive` names each record with the first 12 hex digits of the SHA-256
of its own bytes. So the committed copy can be shown to be the file the run produced:

```sh
python3 -c 'import hashlib;print(hashlib.sha256(open("tests/batteries/results/removal-proofs-history/removal-proofs-20260805T215946-4479acefc95f.json","rb").read()).hexdigest()[:12])'
# 4479acefc95f — the suffix in the filename
```

All twelve records present at audit time reproduce their own suffix.

---

## 3. The audit of the existing archives

### 3.1 Population and integrity

**Ten archives existed before this pass** (two more were produced by this pass's own gate runs and
are not part of the audited set).

| | count | note |
|---|---:|---|
| Archives | 10 | earliest `14:07:21`, latest `22:48:35`, all 2026-08-05 |
| `status: aborted` | 3 | no totals written at all — the harness's designed refusal, and the correct behaviour. Nothing to audit in them |
| `status: complete` | 7 | 128, 129, 129, 129, **141**, 147, 147 entries |
| Content digests reproduced | 10 of 10 | no record has been altered since it was written |

**Population identity, which is what makes the audit tractable.** Across all seven complete
archives there are **147 distinct arm titles**, and **every one is still declared in the working
tree** — no arm was ever retired or renamed. **141 titles were recorded `proved` at least once; the
other 6 were only ever `skipped`.** And **no title carries two different outcomes across archives**:
every arm reads the same everywhere it appears. So the audited population is exactly today's arm set,
and a run of today's arm set is a run over the whole of it.

### 3.2 The screen, and the two arms it returns

The fabrication route requires one specific thing: **the tampered test must not return on its own.**
An arm whose tampered test reports — pass or fail — never reaches the `else`. So the audit reduces to
finding every arm that can fail to return. Two independent methods were used.

**Method A — behavioural, and the stronger of the two.** Re-run all 147 arms under the repaired
scorer, which now separates the three endings that the old `else` collapsed. Any arm that could only
end by being killed now scores `unproven` (`proof-killed-by-signal`) or `timed-out`.

```sh
PATH="$PWD/.venv/bin:$PATH" bash tests/removal_proofs.sh
# 141 proved, 0 unproven, 6 skipped   — exit 0
# record: entries_recorded 147, proved 141, skipped 6, unproven 0, timed_out 0
```

**Zero signalled, zero timed out.** Every arm that scored `proved` did so by the tampered test
reporting a failure.

**Method B — structural, and independent of today's tree.** Screen every declared arm for the shape
rather than the behaviour: the tamper's target is a terminator (a ceiling, backstop, cap, limit or
guard) **and** the arm's test drives something unbounded. Over all 147 arms this returns **exactly
two**:

```
FR-048 watch-set guard — the listener stops consulting it     src/supervisor/seccomp.py
T065 wiring — the backstop is built by the loop and never …   src/runtime/loop.py
```

The two methods agree, and Method B's candidate set is the same one arrived at independently by
reading. Method B is a regex screen and is reported as a screen; Method A is the evidence.

### 3.3 `T065 wiring` — **fabricated**, and re-measured on the archived tree

Method A clears this arm *today*, but today is not the tree the archive was taken from — this is the
one arm repaired between the archive and now, so the clearance is worthless for the archive. It was
re-measured directly instead: `1208e06` was rebuilt with `git archive`, that commit's own tamper was
applied with that commit's own matcher, and the arm's test was run under a **90-second** cap.

```
arm at 1208e06: T065 wiring — the backstop is built by the loop and never consulted
   tamper src/runtime/loop.py
   exit=124 after 90.1s -> DID NOT RETURN (capped)
```

The tamper removes the loop's only `backstop.check` call while the arm's own ceilings are all set out
of reach on purpose — which is precisely what makes it a second guard rather than the first one
counted twice. With the backstop gone the loop has **no terminator of any kind**. The test cannot
fail; it can only not return. **So the `proved` in the 21:59 archive was not earned by anything.**

Today, with the test's own bound in place, the same arm fails in **2.46 s** with exit `1` — an
ordinary pytest failure. It is a real proof now; it was not one then.

### 3.4 `FR-048 watch-set guard` — **legitimate**, verified at the mechanism rather than the title

This arm reads `proved` in all seven complete archives, and a hang is documented immediately above it
in the harness. The documented hang is what makes it a candidate; **the documented hang is about a
different call site.**

`tests/removal_proofs.sh`:919–923 says so in terms. The hazard is *"tampering the `install_filter`
call site"*, which with the guard gone would make the test install a `USER_NOTIF` filter **on the
pytest process itself** and block forever in `seccomp_do_user_notification` with nobody holding the
descriptor. **The author deliberately did not write that arm.** The shipped arm tampers the *third*
call site instead:

```
tamper:  check_watch_set_is_wired(watched)\n        self._names  ->  self._names
in:      src/supervisor/seccomp.py
test:    test_the_listener_asks_the_guard_before_reading_any_notification
```

And the test that arm points at cannot block, for a reason its own docstring states: the guard runs
**before** `notif_sizes()`, so the test constructs `NotificationListener(-1, ...)` and *"`fd=-1` is
never touched"*. No descriptor, no kernel, no filter. That is also consistent with the archives
themselves — every one was taken on `macOS-26.2-arm64` at `euid 501`, where there is no seccomp to
block on at all, and this arm ran and scored rather than being skipped.

**Measured rather than accepted**, by applying the shipped tamper to a copy of the tree and running
the arm's test under the cap:

```
FR-048 watch-set guard — the listener stops consulting it
   exit=1    pytest reported a failure      0.50s   (test itself: 0.07s)
```

Exit 1, in half a second, from pytest reporting. Not 124, not >128. **Legitimate.**

Two further points that raise confidence without being the argument. The arm also reads `proved` in
the two archives taken *after* the scorer was repaired (22:42 and 22:48), where a signalled child
would have scored `unproven` and a hang `timed-out`. And the 6 arms that are only ever `skipped`
cannot carry a fabricated *proof* at all, since the fabrication route runs through the `proved`
branch.

### 3.5 The result of the audit

**Exactly one fabricated entry across the ten archives: `T065 wiring` in
`removal-proofs-20260805T215946-4479acefc95f.json`.** The other 140 proved entries in that record,
and every proved entry in the other six complete records, are of arms that terminate by reporting.

---

## 4. The permanent limit — this audit **cannot be completed**, and the finding is not complete without saying so

**Archiving landed on 2026-08-05 and the earliest surviving record is stamped `14:07:21`. The
fabrication route has existed for as long as `proof()` has.**

There is therefore **no way to say how many arms were scored `proved` on the kill route before
14:07 on 2026-08-05**, and no way to bound it either. Every run before that point wrote to
`removal-proofs.latest.json`, which the next run overwrote. §3 audits the window for which records
exist; it says nothing whatever about the window before it, and *"one fabricated entry"* is a
statement about ten archives and not about the harness's history.

**Three narrower limits on §3 itself, stated so the audit is not read as stronger than it is.**

- Method A measures **today's tree**. For six of the arms the population identity in §3.1 is doing
  the work, not the re-run.
- All ten archives were taken **unprivileged on macOS**, so the same 6 arms are `skipped` in every
  one of them. Those arms have never been exercised on any surface the archives cover, in either
  direction.
- The screen in Method B is a regex over titles, tamper targets and test bodies. It agrees with
  Method A and with an independent reading, and it is still a screen.

**This is the same shape as [finding 022](./022-e7-tool-result-truncation-cap.md)'s pre-truncation
output size** — *"every question of the form what would E7's shell arm have cost with no cap is
unanswerable from the committed artifacts, and re-asking it needs a new run at a new price."* Here it
is worse in one respect and better in another: worse, because a new run cannot recover the answer at
any price — the runs are gone, not merely unrecorded; better, because the route is now closed, so the
unanswerable window is closed-ended rather than growing.

**The transferable rule, which is the part worth keeping.** An instrument's archive can only audit
the instrument back to the day the archive started. Archiving is therefore not a nice-to-have added
after an instrument is trusted — **it is the thing that makes an instrument auditable at all**, and
the interval between an instrument shipping and its archive starting is permanently dark. This one
was dark for the whole of the instrument's life up to its last day.

---

## 5. Where the cost-table pass's claim lands

That pass reported **"all twelve new proofs proved first run"**.

**Checked against the record.** The 141-entry archive contains exactly **12 arms** not present in the
129-entry archive before it, and **all twelve are recorded `proved`**:

```
proved  T063 fail-closed lookup — a family prefix is priced as one of its members
proved  T062 sourced entries — a citation nobody can open is accepted
proved  T063 date window — a date no entry covers is priced from the nearest one
proved  T062 prompt-length bands — every request is priced at the lowest band
proved  T062 unit gate — a non-integer token count is priced instead of refused
proved  T064 reservation figure — the spend reservation is derived at the cheaper rate
proved  T065 independence — the backstop is made downstream of the cost table
proved  T065 unraisable maximum — the backstop can be widened by its caller
proved  T065 metric — tool steps are counted as model calls
proved  T065 boundary — the backstop permits one call past its maximum
proved  T065 wiring — the backstop is built by the loop and never consulted
proved  T065 default — a loop constructed without a backstop gets none
```

**So the claim is true as recorded and false as meant.** That phrasing is the pass's own and it is
kept because it is the right one. Read as *"the harness recorded twelve `proved`"*, it is exactly
correct and the exhibit shows it. Read as it was meant — *"twelve mechanisms were demonstrated to be
load-bearing"* — it is false, because one of the twelve demonstrated nothing.

**This is not a defect in that pass's honesty, and the finding should not be cited as if it were.**
The pass ran the instrument, read its output, and reported what it said, without embellishment. It
had no way to know that one of the twelve words was manufactured: the record it read is clean, the
run completed, the totals reconcile, and nothing in the output distinguishes the fabricated entry
from the eleven beside it. **The instrument lied and the pass repeated it faithfully.** The
generalisable point is that faithful reporting of an instrument's output is not the same act as
measuring, and no amount of care in the first substitutes for auditing the second — which is
[`tools/README.md`](../../../tools/README.md)'s *"reading an instrument is not measuring it"*, arrived
at from the reporting side.

---

## 6. What was fixed, and one shape to carry forward

| fix | where | what it scores |
|---|---|---|
| Signal scoring | `proof()`, `go_proof()` | status > 128 → `unproven`, reason `proof-killed-by-signal` |
| Wall-clock cap | `tools/proof_timeout.py`, 300s per arm | exit `124` → `timed-out`, its own counter and exit-status weight |
| The test's own bound | `tests/unit/test_budget_backstop.py` | the tampered `T065 wiring` test can now fail, in 2.46 s |

`tools/proof_timeout.py` exists as a script rather than a `timeout(1)` invocation because macOS ships
no `timeout(1)`; it runs the command with `start_new_session=True` so the cap kills the process group
rather than one process.

**The shape to carry forward, stated generally because it will recur.** *Whenever a tamper removes
the only thing that stops a loop, the tampered test has no failure mode left.* Ask it of every arm
whose test runs something unbounded, and give the test its own bound — one that cannot be mistaken
for the mechanism under proof. `_STUB_GUARD = MAX_MODEL_CALLS * 10` is tied to the constant rather
than written as a literal for exactly that reason, and the untampered arm asserts `_STUB_GUARD > 3`
so that a reader can see the guard took no part in the result.

**And the more general one, which is about scoring rather than about loops.** `proof()`'s defect was
a classifier written as a complement: *not zero and not a collection error is proved*. The accepting
set was never enumerated, so every ending nobody thought of landed in it. This is
[`tools/README.md`](../../../tools/README.md)'s *"never state a classifier as a complement —
enumerate the accepting set"*, and the removal-proof harness is now the case that establishes it for
process exit statuses.

---

## 7. The question this leaves, stated without a register number

**`tools/proof_attribution.py` applies every tamper and runs every arm's test with no cap of any
kind**, and `.github/workflows/ci.yml` runs it in the same job as the harness under `if: always()`.
It is not the harness and it scores nothing, so it cannot fabricate a proof — but it can hang, and it
is the one remaining uncapped path over the same tampered arms. It does not hang today only because
the `T065 wiring` test now carries its own bound, which is the test-level fix doing the work rather
than the cap.

Whether that tool should take the same cap is left to an owner. It is stated here rather than
numbered, and rather than fixed, because CI was explicitly out of this pass's scope.
