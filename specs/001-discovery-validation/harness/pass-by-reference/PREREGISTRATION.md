# E17 pass-by-reference — pre-registered design, thresholds and budget

**Date**: 2026-08-04
**Status**: pre-registered, **not run**. No model has been called. Spend to date on this
experiment: **$0.00**.
**Authorization sought**: arm A only. Arm B is projected below so that it can be
declined against a number, and §11 recommends declining it.

---

## TL;DR of the design decisions a reader should not miss

1. **Both arms of arm A are capped.** An uncapped inline arm is not a baseline, it is
   a run that cannot happen: the measured battery projects a 726,766-token inline
   transcript for one task, three and a half times this model's context window. The
   factor under test is therefore *bounded and the bytes are gone* versus *bounded
   and the bytes are still reachable by name* — which is the actual product question.
2. **The answer depends almost entirely on where the inline arm truncates**, and that
   is knowable now, for free. At an 8,000-token cap the projected median token ratio
   is 0.429. At 2,000 it is 0.958 and the mechanism buys essentially nothing. At
   32,000 it is 0.160. The same decision rule returns *recommend* at one cap and
   *recommend against* at another. §8.6 makes publishing all three binding.
3. **A turn budget is the calibration knob**, and without one this design almost
   certainly voids. Every task is a deterministic shell question a competent model
   answers in either arm given unlimited turns — E7's exact defect.
4. **The battery has a real negative control**, three tasks on which the treatment is
   provably inert, projecting a ratio of 1.073–1.075 (above 1.00, because the handle
   arm pays a larger prompt and gets nothing back).
5. **The decision rule can return *recommend against*,** and it fires on a success
   loss whatever the token saving is.
6. **Arm B cannot measure what it was commissioned to measure**, established at $0.00
   by reading NOOA's source. §11. Its salvageable part costs nothing and is already
   run: §12.

---

## 1. The claim under test

NVIDIA's OO Agents reports parity-or-better on SWE-bench at roughly half the tokens
of its comparison harnesses and attributes the saving to *pass by reference* — tool
results stay live Python objects instead of being serialized into the transcript.
`research/15-nvidia-oo-agents.md` carries the detail and the quotations.

Our v1 cannot use that mechanism. **FR-004** gives the agent command execution plus a
general request capability; both return bytes across an enforcement boundary, so
there is no in-process object graph to share. The *economic* benefit is available
through a different mechanism — keep the bulk out of the transcript and refer to it
by name — and no requirement governs it, so the implicit default is to inline
everything a command prints. That default sits directly on the product's cost claim,
which is where **OD-09** repositioned it.

**H-E17.** On a command-execution surface, replacing inlined command output with a
bounded preview plus a filesystem handle reduces total tokens per task materially,
*without* reducing task success.

The hypothesis has two limbs and they can move in opposite directions. A model cannot
see data it was not shown.

---

## 2. Arm A — the surface and the two treatments

One factor, on a `run_command` tool over a generated target tree.

| | **A-inline** | **A-handle** |
|---|---|---|
| result content | stdout/stderr, truncated at the cap with an elision marker | head/tail preview, byte count, line count, SHA-256, **and the path** |
| cap | 8,000 tokens per result | 400 tokens per result |
| bytes past the cap | **gone** | on disk, addressable by the returned path |
| static prefix | 1,200 tokens | 1,320 tokens |
| extra turns | — | one per bulk step, charged in the projection |

### 2.1 Why the inline arm is capped, and why that is not a weakening

The first draft did not cap it, and the dry run showed why that was unrunnable. Every
real command-execution surface truncates; an uncapped one is not a default, it is a
bug that surfaces as a context-length error on the first large `grep`. Comparing a
completed handle run against an inline run that cannot physically exist is the same
error §11 identifies in arm B, and the uncapped projection produced a token ratio of
0.030 — a 97% "saving" that is an artefact of pricing an impossible transcript.

### 2.2 The static prefix delta is a necessary co-variant, and it is netted out

A-handle's tool description must document the preview envelope and the handle path or
the model cannot use the mechanism. That is a genuine second difference. It is
declared here at an estimated +120 tokens, it is **measured exactly with the
provider's tokenizer in pre-flight, before the first call**, and §8.3 requires both
the gross ratio and the prefix-net ratio to be reported. A saving that disappears
once the prefix delta is removed is not a saving.

---

## 3. The battery, the corpus, and the three strata

**Corpus.** Generated, not committed: `corpus.py` from seed `20260804` produces 42
files and 4,228,698 bytes of synthetic logs, CSV metrics and Python sources.
`selftest.py` regenerates and asserts both figures and every per-file SHA-256, so a
stranger reproduces the target from this directory and nothing else (**SC-005**).

**Battery.** 21 tasks. Each carries an *exploratory* oracle plan — orient, peek, cast
wide, narrow, answer — because a minimal plan prints eleven bytes and would make the
treatment unmeasurable by construction.

**Two independent computations of every answer.** Each task has a shell plan and a
Python checker that share no code. `selftest.py` asserts all 21 agree. Constitution
Principle I requires a derived verifier to be validated against an artefact its own
derivation did not produce, and that assertion is the validation. A disagreement
means the battery is broken and the run does not start.

**Strata, assigned by measurement against the two caps** — not by taste:

| stratum | n | largest step | what the treatment does |
|---|---:|---|---|
| `cap_binding` | 12 | > 32,000 B | handle saves tokens **and** inline loses bytes it cannot recover |
| `cap_clearing` | 6 | 1,600–32,000 B | handle saves tokens; inline loses nothing |
| `null_control` | 3 | ≤ 1,600 B | neither arm can act |

### 3.1 The negative control, and the one the dry run rejected

The first draft called T14/T16/T17 the controls because no step of theirs passed the
4,096-byte "bulk" threshold. That was wrong: the handle preview binds at 1,600 bytes,
so their 2.5–3.2 KB steps are still elided and they still project a real 5% saving. A
control that carries a treatment effect is worse than no control, because it reads as
evidence the instrument is clean.

C01–C03 keep **every** step under 1,600 bytes and project 1.073, 1.075 and 1.075 —
above 1.00, because the handle arm pays the larger prefix and gets nothing back.
**A null-control ratio below 1.00 in the live run means the instrument is saving
tokens somewhere the mechanism cannot reach, and the primary result is not readable.**

---

## 4. Calibration band, the turn budget, and the rule that voids the run

**Band, pre-registered.** Pooled success over both treatments on the 18 primary tasks
must land in **[0.25, 0.85]**, *and* no more than **25%** of tasks may be pinned at
1.00 pooled, *and* no more than **25%** pinned at 0.00.

0.25–0.85 is E7's own band, reused deliberately. E7 missed it — its tool arm pinned
at 1.00 on 27 of 41 tasks, and **D-19** concedes that two of three task families
support no conclusion as a result. The two pinning caps are what E7 did not have: a
set can sit inside a pooled band while most individual tasks are saturated, and a
saturated task discriminates nothing however the pool averages out.

Calibration is **pooled over both treatments**. Calibrating per-arm would set the
instrument using the very difference the instrument exists to detect.

**The gate is stage 1 — replicate 1 of the full battery**, not a separate purchase.
It calibrates the exact set that will be analysed, and if it passes, nothing was
bought twice. The double use is confined to the pooled success rate, which is not the
estimand; the estimand is the paired within-task contrast.

### 4.1 The turn budget, and the biggest risk in this design stated plainly

**The most likely single outcome of this experiment is that it voids at stage 1.**
Every task is a deterministic shell question that a competent model gets right in
*both* arms given enough turns. Left alone, this battery saturates exactly as E7's
did.

The turn budget is the knob, and it is also the mechanism the product cares about.
The inline arm spends turns recovering from truncation and fills its context faster;
under a budget it runs out. The handle arm keeps the bytes addressable and spends one
cheap turn filtering them. **If neither arm ever runs out of turns, this design
measures token cost and nothing else, and limb 2 is decorative.**

- Budget: **8 turns**.
- **Exactly one retune is permitted**, to 5 turns, only if stage 1 misses the band. It
  is declared here before stage 1 runs. A retune re-runs stage 1 in full and costs a
  full stage 1; that money is the contingency line in §10, not a percentage.
- If the retuned stage 1 also misses the band, **the run is void and the void is the
  reported result.** It is not quietly repaired, and no further retune is authorized
  without a new authorization.

---

## 5. Pairing, sessions, and the confound that invalidates the obvious design

Deterministic tasks in this repository have been measured swinging by a factor of
**2.55** across sessions for reasons never established. Any design comparing arm A's
cost in one session against another's in a different session is invalid before it
runs.

- **Both treatments of every task run in the same session, in the same process**,
  emitted as one record with a shared `pair_id` and `session_id`.
- **Interleaved ABBA** — inline, handle, handle, inline — so a monotone within-session
  drift does not load onto one treatment.
- **The estimand is a within-pair ratio.** A session-wide *multiplicative* effect,
  which is the shape of the 2.55× swing, cancels exactly in a ratio.

### 5.1 How the confound is detected if it appears anyway

A ratio does not cancel an *additive* or *task-dependent* drift, so pairing alone is
not a defence. `S00`, a fixed cheap task deliberately **not** drawn from the battery,
runs under A-inline at the start, middle and end of every session. If its total token
count moves by more than **±15%** within a session, that session is flagged and every
pair in it is reported separately, with its own denominator, alongside the pooled
figure. A sentinel drawn from the battery would carry its own treatment effect into
the drift reading it exists to isolate.

---

## 6. Exclusions, and the denominator rule

The unit of analysis is the **pair**. Terminal statuses: `ok`, `void_calibration`,
`error_harness`, `error_provider`, `refused`, `budget_stop`.

**If either limb is not `ok`, the whole pair is excluded and both limbs go with it.**
A half-pair cannot enter a paired statistic, and letting one pad a denominator is the
defect found at eleven sites in this corpus on 2026-08-03. `analysis.Population`
asserts that attempted = analysed + excluded and refuses to report otherwise; every
rate the module returns is a `Rate` carrying its own `n`, and there is no code path
that produces a bare float.

The three null-control tasks are **a separate population**, reported with their own
denominator. They enter neither the calibration band nor the decision statistic.

---

## 7. What is measured

- **Limb 1, cost.** Total billed input + output tokens per run, from the API response,
  never from the estimation divisor. Reported as the median paired ratio
  handle ÷ inline, with a paired bootstrap CI.
- **Limb 2, success.** A deterministic checker per task — exact string match after
  whitespace normalisation, against the independent Python computation of §3. **No
  LLM judge.** This project has been burned by one; the answers here are contract-
  derived and there is no reason to introduce a stochastic grader.
- **Turn count, context-overflow events, truncation events**, per run.
- **`data_unreachable` events**: the inline arm hit its cap on a step whose bytes the
  task needed. This is the mechanism by which limb 2 is expected to move.

---

## 8. The decision — binding, and written before the run

### 8.1 Limb 1

`R` = median over analysed pairs of (handle total tokens ÷ inline total tokens).

### 8.2 Limb 2

`Δ` = paired (handle − inline) success in percentage points, with a 95% paired
bootstrap CI over 10,000 resamples, seed `20260804`. **Pairs are resampled, not
limbs.**

### 8.3 Prefix-net reporting, mandatory

Both `R` (gross) and `R_net` — recomputed with the measured static-prefix delta
removed from both arms — are published. If they disagree about which side of 0.75
they fall on, that disagreement is the headline and neither branch of §8.4 fires.

### 8.4 The rule

| condition | outcome |
|---|---|
| calibration band missed (after the one permitted retune) | **void** — no outcome, and the void is reported |
| `Δ` CI upper bound < 0 **and** `Δ` ≤ −10 pp | **recommend against**, *whatever `R` is* |
| `R` ≥ 0.95 | **recommend against** — the mechanism costs turns and complexity and buys nothing |
| `R` ≤ 0.75 **and** `Δ` CI lower bound ≥ −10 pp | **recommend** |
| anything else | **no recommendation** — the design does not resolve this case, and no rule may be chosen after the fact |

**What argues against the change, stated as a sentence so it cannot be read past:** if
handle-plus-preview cuts tokens by 40% and loses 12 percentage points of task
success, the pre-registered answer is *do not make it the default*. Limb 2 dominates
limb 1. A cheaper agent that answers wrong is not a cheaper agent.

The margin is **−10 pp, not −5 pp**, because at 54 analysed pairs a paired bootstrap
CI on a success difference has a half-width near 13 pp under a plausible discordance
rate, and a 5 pp margin would be a margin this design cannot see. §9 says what a 5 pp
decision would cost.

### 8.5 Two checks that can invalidate the primary result

Both are computed and published regardless of outcome.

- **Negative control.** If any of C01–C03 shows a ratio below 1.00, the instrument is
  saving tokens somewhere the mechanism cannot reach. §8.4 does not fire.
- **Stratified reading.** On `cap_clearing` tasks the inline arm never lost anything,
  so the handle arm should save tokens at *no* success cost; on `cap_binding` tasks
  the inline arm is missing data, so the handle arm should if anything succeed *more*
  often. **If the success limb moves against the handle arm on `cap_clearing` tasks,
  the loss is not caused by missing data**, the stated mechanism is wrong, and the
  unstratified average would have hidden it.

### 8.6 Cap sensitivity, mandatory, and free

The effect is conditional on where the inline arm truncates and there is no cap-free
number to report. The ratio is recomputed at inline caps of 2,000, 8,000 and 32,000
tokens **from the same measured bytes at no extra spend**, and all three are published
together. The projected values already show the rule flipping across that range:

| inline cap | projected median ratio | §8.4 branch it would select |
|---:|---:|---|
| 2,000 | 0.958 | recommend against — no benefit |
| 8,000 | 0.429 | recommend, if limb 2 holds |
| 32,000 | 0.160 | recommend, if limb 2 holds |

**A single ratio quoted without its cap is not a result.** The primary cap is 8,000,
fixed here before the run. If v1's inline surface ends up truncating near 2,000
tokens, this mechanism buys almost nothing on tokens — though it still buys
reachability, which is limb 2.

---

## 9. What this size supports, and what it does not

The analysed set is 18 primary tasks × 3 replicates = **54 pairs**.

- **Limb 1 is comfortably powered.** The token ratio is near-deterministic given the
  plan; 54 pairs is far more than it needs.
- **Limb 2 can see a 10 pp shift and cannot see a 5 pp one.** At 54 pairs and a
  discordance rate near 0.25, the CI half-width is about 13 pp.
- **What a 5 pp decision would need.** Half-width 0.05 = 1.96·√(0.25/N) gives
  N ≈ 384 pairs, which at the measured $0.1642 per pair is about **$63.05** of model
  spend for the analysed set alone, before calibration, sentinels or contingency.
  That is the experiment to run *after* this one returns a direction, not instead of
  it.
- **One model, one provider.** The result speaks to `claude-sonnet-4-5-20250929`. A
  model with a different tool-use disposition may behave differently, and nothing here
  licenses a claim about models in general.

---

## 10. Cost — arm A, arithmetic shown

Model `anthropic/claude-sonnet-4-5-20250929` at **$3.00/M input, $15.00/M output** —
the same dated snapshot and the same list prices already pinned by E19's config, so no
price in this harness was invented by it. Token estimation divides measured bytes by
**4.0 bytes/token**, E19's divisor, reused so the two projections sit on one basis.

Bulk sizes are **measured**, not assumed: `measure.py` generates the corpus, runs
every plan step and counts the bytes, at $0.00.

**Per-call accumulation.** Input is re-sent every call, so a bulk result is paid on
that call *and every call after it*. Worked for T09 (`cap_binding`), inline cap 8,000:

```
prefix = 1200 static + 120 prompt = 1320
 call 1: in   1,320  out 120  result   1,254   acc   1,374
 call 2: in   2,694  out 120  result   8,000   acc   9,494
 call 3: in  10,814  out 120  result   8,000   acc  17,614
 call 4: in  18,934  out 120  result       3   acc  17,737
 call 5: in  19,057  out 200  (answer)
 totals: in  52,819  out 680
       = 52,819 x 3.00/1e6 + 680 x 15.00/1e6 = $0.168657
```

**Battery and run.**

| line | pairs | amount |
|---|---:|---:|
| one full battery pair-pass | 21 | $3.4479 |
| stage 1 — replicate 1, and the calibration gate | 21 | $3.4479 |
| stage 2 — replicates 2 and 3 | 42 | $6.8958 |
| drift sentinels — 9 × $0.0198 | — | $0.1780 |
| **subtotal** | | **$10.5218** |
| contingency — one permitted stage-1 retune (§4.1) | 21 | $3.4479 |
| **ARM A TOTAL** | | **$13.9697** |

**Hard ceiling $16.00, budget $17.00.** The ceiling is checked *before* each call
against the running ledger, never after; a ceiling that can be exceeded is not one.
Both figures were set **after** the measured projection. A hand estimate written
before it put a task pair at $0.34 against a measured $3.4479 for the whole battery
and $11.84 uncapped — wrong in both directions by more than an order of magnitude
each time, which is the argument for projecting from measurement rather than
intuition.

### 10.1 Irreducible minimum versus statistical margin

This is the trade being decided.

| | amount | why |
|---|---:|---|
| **Irreducible** | **$10.5218** | stage 1 (the gate — without it the run can be void and unknowably so) + replicate 2 (with one replicate there is no within-task variance estimate at all, and this corpus measured a 2.55× swing) + the drift sentinels at $0.18 + the one permitted retune, which §4.1 says is the outcome to expect |
| **Margin only** | **$3.4479** | replicate 3. It narrows the CI on Δ; it does not change what may be claimed, and it does not move the §8.4 branch unless the result is already borderline |

**Buying the irreducible $10.52 and stopping** yields both limbs, the negative
control, the stratified reading, the full cap sensitivity, and a decision at 2
replicates. It is a coherent purchase. The last $3.45 is the only genuinely optional
line.

---

## 11. Arm B — why it cannot measure what it was commissioned to measure

Arm B was to run the same NOOA task with `execution_backend="inprocess"` then
`"sandbox"`, one factor differing: under `"sandbox"` every brokered `self.*` result
crosses a fork boundary via pickle.

**Reading NOOA's source establishes, at $0.00, that the boundary does not put bytes in
the transcript.** In `nooa/runtime/sandbox/executor.py`, `_dispatch_tool_call`
executes the call on the parent's live agent, checks `is_picklable`, and returns
`{"ok": True, "result": value}`; the worker unpickles it and **binds it as a live
Python object in the cell namespace**. What reaches the transcript is
`ResultDTO.stdout / stderr / returned_value` — *the same set as in-process*.

So NOOA's sandbox trades away **object identity and liveness** — a fresh copy per
`self.<attr>` read, no in-place mutation, non-picklable returns refused or proxied —
and not **transcript inlining**. Pass-by-reference at the transcript level survives
the sandbox intact. Arm B varies a factor with no transcript-token consequence.

### 11.1 What arm B would actually measure — three factors, two pointing the wrong way

1. **A prompt difference.** With `sandbox.context_block` at its default, the sandbox
   arm gets an extra system-prompt block, roughly 1.1 KB, that the in-process arm does
   not. It is not neutral text. It says: *"Values returned from a cell must be
   picklable... Keep live objects in the namespace and return a summary instead."*
   **The sandbox arm's prompt instructs the model to economize** — which is the
   treatment arm A exists to test. The confound points the same way as the hypothesis.
2. **Semantic divergence.** The same block warns that `self.<attr>` reads a fresh copy
   and that in-place mutation is not persisted. The arms present different programming
   models, so trajectories diverge for reasons unrelated to serialization.
3. **Refusal recovery.** `CellSerializationError` costs turns the in-process arm never
   spends.

Setting `context_block=False` removes (1) and replaces it with a different confound:
the model is not told the constraints it faces, hits `PermissionError` and
`MemoryError`, and burns turns discovering them. **Either way arm B is at least
two-factor, and this is a property of NOOA's code, not of this host** — it would hold
on any machine.

### 11.2 The `CellSerializationError` classification, pre-registered anyway

Required by the brief and recorded in case the owner authorizes arm B over this
recommendation. A sandbox run that terminates in `CellSerializationError` where the
in-process run completed is **`refused`**, not `error_harness` and not a completed
run. Its pair is excluded whole, both limbs, and the count of refusals is published
with its own denominator beside every ratio. Comparing a finished run against a broken
one and reporting the token difference is the specific way this comparison goes wrong.

### 11.3 Arm B could be made single-factor, and it would then measure a known null

Hold the prompt identical by injecting the same block into the in-process arm; set
`network=True, filesystem=True` for capability parity; restrict the battery to tools
whose returns are all picklable so refusals cannot occur. The remaining single factor
is a pickle round-trip of brokered values — which, per §11, has no transcript-token
consequence at all. **You would be buying tokens to measure a null by construction.**

### 11.4 Cost if authorized anyway

12 tasks × 2 replicates = 24 pairs. In-process run projects 73,150 input / 2,300
output = $0.2540; sandbox run 99,450 / 2,700 = $0.3388, the difference being the
context block and two recovery turns — i.e. **the projected delta is the confound**.
Pair $0.5928 × 24 = $14.2272, plus 15% = **$16.3613**. Ceiling $16.50, budget $17.00.

**Recommendation: do not authorize.** Not because it is expensive, but because the
$16.36 buys a number whose largest component is a prompt difference.

### 11.5 arm64, and what it would have limited

Docker here is arm64 only; macOS is the host and v1 is Linux-only. Had arm B been
worth running, this would matter for the *sandbox mechanism* — Landlock and seccomp
behaviour is architecture-sensitive, and §13 found one live instance of that
(`prctl` is syscall 167 on arm64 and 157 on x86-64; assuming 157 made Landlock look
unsupported when it is enforced). It would matter much less for a *token* result,
which is a property of the model and the prompt. Since the recommendation is not to
run arm B, arm64 is not the binding limitation — §11.1 is.

---

## 12. Arm B′ — the part worth keeping, already run, $0.00

The brief notes that *which result shapes cannot cross a boundary at all* is itself an
informative finding. It is, and it costs nothing: NOOA's gate is literally
`pickle.dumps` in a `try/except`, so the census runs on the standard library with no
NOOA import — which also avoids `litellm`, removed under **OD-16**.

`picklability_census.py`, 49 realistic tool-return shapes, Python 3.13:

| category | cross | of | blocked |
|---|---:|---:|---|
| plain data | 18 | 18 | — |
| live resource handle | 2 | 9 | open file, socket, sqlite3 connection, sqlite3 cursor, `threading.Lock`, `threading.Thread`, `subprocess.Popen` |
| lazy sequence | 3 | 7 | generator, `itertools.chain`, `dict_keys` view, `memoryview` |
| callable | 3 | 6 | lambda, closure, partial of a lambda |
| locally defined | 0 | 2 | local class, local instance |
| runtime object | 1 | 7 | module, `re.Match`, traceback, weakref, ctypes pointer, ctypes CDLL |

**27 of 49 cross; 22 of 49 do not.** The shape of it is the finding: *every* plain-data
return crosses, and the blocked set is almost exactly "a handle to something live" —
open resources, un-materialised iterators, and anything whose type is not importable
by name. A tool that returns a cursor, a file, a generator or a closure cannot be
exposed across a process boundary at all, however the transcript is managed. That is
a **tool-design constraint** rather than a token one, and it applies to our
enforcement boundary as much as to NOOA's fork.

Two surprises worth recording: `io.BytesIO` and `io.StringIO` *do* cross, so "file-like"
is not the right predicate; and `map`, `filter` and `zip` cross while a generator does
not, so "lazy" is not the right predicate either. Picklability does not follow the
category an API author would reach for.

---

## 13. The Linux host, and T205

Probed with `kernel_probe.py`, four Docker invocations, results in
`results/20260804-kernel-facilities/`. Kernel `6.12.76-linuxkit`, aarch64,
`/proc/config.gz` present. Every reading is a **live syscall probe with an untreated
baseline first** — the probe opens the victim file *before* restricting, and refuses
to report enforcement if the baseline read fails.

| facility | verdict | evidence |
|---|---|---|
| **Landlock** | **ENFORCED** | ABI 6; `CONFIG_SECURITY_LANDLOCK=y`; `landlock` in `CONFIG_LSM`; open succeeds pre-restriction, `EACCES` post-restriction |
| **seccomp user-notification** | **ENFORCED** | listener fd obtained, notification received, response sent, `SECCOMP_IOCTL_NOTIF_ID_VALID` ok, trapped syscall 173 (`getppid` on aarch64) |
| **cgroup v2** | **PRESENT** | unified at `/sys/fs/cgroup`; controllers `cpuset cpu io memory hugetlb pids rdma`; `cgroup.kill` and `cgroup.freeze` present |
| **user namespaces** | kernel yes, runtime gated | `CONFIG_USER_NS=y`, `max_user_namespaces=31337` |

### 13.1 Required privileges, attributed one flag at a time

| invocation | Landlock | seccomp notif | cgroup delegation | `unshare(CLONE_NEWUSER)` |
|---|---|---|---|---|
| Docker defaults | ENFORCED | ENFORCED | read-only (`EROFS`) | `EPERM` |
| `--cgroupns=private` + rw bind of `/sys/fs/cgroup` | ENFORCED | ENFORCED | **writable** | `EPERM` |
| `--security-opt seccomp=unconfined` | ENFORCED | ENFORCED | read-only | **ok** |
| both | ENFORCED | ENFORCED | **writable** | **ok** |

- **Landlock and seccomp user-notification need no privileges at all.** They work under
  stock Docker defaults, under Docker's default seccomp profile, with no `--privileged`
  and no `--cap-add`. This is the load-bearing result.
- **Writable cgroup v2 delegation** needs `--cgroupns=private` plus a read-write bind
  of `/sys/fs/cgroup`. Under defaults the container's own `cgroup.kill` and
  `cgroup.freeze` are readable but no sub-cgroup can be created.
- **`unshare(CLONE_NEWUSER)` is blocked by Docker's default seccomp profile, not by the
  kernel**, and `--security-opt seccomp=unconfined` unblocks it.

### 13.2 Can this host discharge T205 and the untested 5.14 floor? A direct answer

**Partly, and the part it can discharge is the part that matters most — but it cannot
discharge T205 as written.**

- **What it can do.** T205 exists because the 5.14 kernel floor ships marked *DERIVED
  and NOT TESTED*. This host **tests the mechanisms at 6.12.76 and finds all three
  live and enforcing**, under privileges a normal Docker deployment already has. It
  converts "we believe Landlock, seccomp user-notification and cgroup v2 work" from
  derivation into measurement at one kernel version. It also fixes the *minimum
  privilege set*, which is separately load-bearing for deployment and was not
  previously established.
- **What it cannot do.** T205 is a kernel **boot matrix**. Proving a *floor* requires
  booting at or near 5.14 and showing the mechanisms still work — and, more usefully,
  booting *below* it and showing they fail. One kernel, above the floor, cannot
  establish a floor; it establishes a single point. Docker Desktop on macOS supplies
  one linuxkit VM whose kernel is not selectable per container, so the matrix is not
  reachable here without a different host or nested virtualisation.
- **Where the floor is likely wrong anyway.** The 5.14 figure looks derived from
  seccomp user-notification's `ADDFD` era. Landlock's ABI here is **6**; Landlock
  landed at ABI 1 in 5.13, and each later ABI added rules a filter may need. A
  requirement written against ABI 6 features would have a floor well above 5.14 and
  nothing in this probe would reveal that, because this kernel satisfies both.

**Recommendation, and no work started:** T205 should be amended to record 6.12.76/arm64
as a tested point and the minimum-privilege table above, and to state that the floor
remains untested. That amendment touches `specs/002-spec-aware-agent-runtime/tasks.md`,
`src/` and `tests/`, all outside this scope and currently being edited. **Nothing was
started.** `kernel_probe.py` is committed here and runs standalone in any container.

---

## 14. Credentials and spend discipline

**Names only. No value is read into anything that outlives the line that parsed it,
printed, logged, or written. That rule is absolute.**

- **How prior harnesses reached credentials.** `provider-credentials/envroot.py` and
  `ceiling-test/envroot.py`: the process environment first, then a dotenv tree the
  operator names with `--env-root` or `F2A_ENV_ROOT`. **There is no default and the
  probe refuses to guess** — the original probe hardcoded a path into a private
  repository on one laptop.
- **This repository holds no credentials.** No dotenv file exists at the root, and this
  session's environment contains no variable matching any provider-credential name
  pattern. `F2A_ENV_ROOT` is unset. The operator must supply one to run arm A.
- **Names finding 002 established as authenticating**: `ANTHROPIC_API_KEY`,
  `OPENAI_API_KEY`, `XAI_API_KEY`, `OPENROUTER_API_KEY`, `GEMINI_API_KEY_2`.
- **One name established as dead**: `GEMINI_API_KEY` — one of ten non-authenticating
  Google-shaped credentials on the tree finding 002 probed, while the working key sat
  under a non-canonical name. Name does not imply validity and presence does not imply
  validity (**U-03**).
- **Arm A needs exactly one**: `ANTHROPIC_API_KEY`.
- **Pre-flight, free.** The runner calls the model-list endpoint before the first token
  and refuses to start on a non-200. It costs nothing and it is the difference between
  failing at $0.00 and failing mid-battery.

---

## 15. Stop conditions

1. The battery cross-check disagrees on any task → do not start.
2. Pre-flight credential probe returns non-200 → do not start.
3. The corpus manifest does not match the pinned size, file count or hashes → do not
   start.
4. Calibration band missed after the one permitted retune → **void**, report the void.
5. Any null-control ratio below 1.00 → complete the run, publish, and §8.4 does not
   fire.
6. Running ledger would pass the hard ceiling on the next call → abort, report partial
   results against the frozen manifest with their own denominators.
7. More than one third of pairs excluded for any reason → the population is not the
   one that was designed; report both populations and withhold §8.4.

---

## Amendment convention

Amendments append; nothing above is edited in place. Superseded text is struck and
dated, never deleted. One change per subsection, each stating its cost or its trade.

```
# Amendment A<n> — <date>, <what was and was not visible when it was made>
## A<n>.1 — <the change, with its cost or trade stated>
```
