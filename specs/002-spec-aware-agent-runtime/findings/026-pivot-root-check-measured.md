# Finding 026 — the `pivot_root` check, measured: four of its five cells against real container arms, its `EPERM` disambiguation controlled by removing the filter rather than by reasoning about it, and one correction to the defect's own description — the pre-T207 preflight is not *wholly* green in the trap arm, it is green on **every FR-048 check**, which is the sharper and fully measured claim

**Date**: 2026-08-04
**Feature**: 002. Adds a `pivot_root` check to
[`src/supervisor/preflight.py`](../../../src/supervisor/preflight.py)'s `run_checks()` and converts
four of its five classification cells from derived to measured, by running **that check** inside
container arms rather than a re-implementation of it.
**User Story**: US1, by way of FR-048 and [`tasks.md`](../tasks.md) **T207** and **T208**.
**Owner decision**: **none is recorded here and the register was not edited.** The next free owner
decision number is `OD-26` — written inside a code span, which the corpus checker does not resolve
as an identifier, because writing it as a live token before the register carries the entry is a hard
`identifier-resolution` error. Same escape and same reason as
[finding 025](./025-preflight-unshare-pair-measured.md)'s header. Nothing here rests on it.
**Model spend**: **$0.0000.** No model was called and no credential was read. Roughly two dozen
containers were run locally, counting re-runs; the only network requests were two image pulls.
**Method**: our committed `_check_pivot_root`, `_attempt_pivot_root` and `_classify_pivot_root`, run
unchanged inside six container configurations that differ from one another in one variable at a
time; the **pre-T207 check set** run in the same trap configuration; and the observation tool run in
two further arms. **No arm ran `--privileged`.** Every row carries the privilege posture it was
taken under, read from `/proc/self/status` **in the arm itself** rather than inferred from the flag
line — finding 024's overflow-uid bug is why that distinction is worth a sentence.

**Revision discipline, and an incident that nearly cost the whole table.** Every arm was taken
against the working tree at the revision this finding is committed in, with
`src/supervisor/preflight.py` clean apart from T207's own change. `main` was at `95c871d` when the
pass began and had not moved when it ended.

The arm that measures the pre-T207 behaviour copies `git show 95c871d:src/supervisor/preflight.py`
into the container. **The first attempt at it wrote that file into the repository**, because the
repository was bind-mounted read-write and the copy's fallback-to-scratch logic only ran if the
first copy *failed* — and it succeeded. T207's implementation was silently reverted to `95c871d`.
The check for this was `git diff --stat src/supervisor/preflight.py`, which **printed nothing and
was read as "unchanged"** when what it actually meant was "now identical to `HEAD`" — the check was
exactly inverted with respect to the failure it was supposed to catch. It was caught two steps later
by `tools/check_tampers.py` reporting `NO_MATCH` on all three new proofs, which is a mechanism
noticing a thing a human eye had already passed over.

The file was restored from a pre-tamper backup (401 insertions, confirmed against `HEAD`), and
**every arm in §1 and §2 was then re-run from scratch with the repository mounted `:ro`**. All
values reproduced identically. The table below is from the re-run, not from the first pass, so
nothing here rests on the compromised interval. Recording it because the near-miss is the
instructive part: a mounted-writable source tree makes a measurement able to destroy its own
subject, and an emptiness test cannot distinguish "no change" from "changed back".

Numbering note: `025` was the high-water mark across `specs/*/findings/`, checked by listing the
whole tree, and `026` was free at that moment and re-checked free immediately before saving.

---

> ## Read this first: four results, and the third is a correction to the brief that produced this work
>
> **1. The `pivot_root` check's discriminating cells are measured.** Under Docker's unmodified
> default profile with `--cap-add=SYS_ADMIN`, our check sees a real `EPERM` **while holding the
> capability**, classifies it `runtime-seccomp-profile`, and emits the remedy. A custom profile that
> allows `pivot_root` flips the same arm to `EBUSY` and the same check to `available`. One variable,
> and the verdict moves.
>
> **2. `EBUSY` is the permitted answer, and it is measured twice.** `pivot_root("/", "/")` cannot
> succeed — `/` is not a valid new root — so a *permitted* call fails with `EBUSY` rather than
> returning 0. Both permitting arms produced `EBUSY` and both classified `available`. A check that
> scored `EBUSY` as a refusal would report a refusal on every host where the mechanism works.
>
> **3. The defect is not "a wholly green preflight" — it is "a green FR-048".** The brief that
> commissioned this work, and T206's own note, describe the trap arm as producing a wholly green
> preflight. In every containerized arm that could be built, the pre-T207 check set reports **5 of 7
> green**, and both failures are FR-049 cgroup-delegation artifacts of the container
> (`Read-only file system: '/sys/fs/cgroup'`) that have nothing to do with the mount sequence. What
> **is** measured, and is the sharper claim: **every FR-048 check is green at `95c871d` in the arm
> where `pivot_root` is refused.** FR-048 is the requirement that owns the mount and containment
> sequence, so the operator reading it is being told the thing that is broken is fine. Whether the
> *whole* preflight is green depends on cgroup delegation on the host, and that was not constructed.
>
> **4. The `EPERM` ambiguity is resolved by a control, not by an argument.** `EPERM` comes from both
> the seccomp filter and the kernel's `CAP_SYS_ADMIN` gate, so it is only attributable when the
> capability is held. The claim that it is *not* attributable otherwise is measured by **removing
> the filter**: at uid 1000 with `--cap-drop=ALL`, the default profile, a custom profile and
> `seccomp=unconfined` all return `EPERM` with an identical classification. The filter is not what
> refused, and the arms say so rather than the reasoning.

---

## 1. The arms

`python:3.12-slim`, Docker 29.4.1, host kernel `6.12.76-linuxkit` (Docker Desktop). Each arm runs
`_attempt_pivot_root()`, `_read_cap_sys_admin()`, `_classify_pivot_root()` and the assembled
`_check_pivot_root()`, and prints the posture it read.

| arm | seccomp | caps | uid | `CapEff` | `Seccomp` | errno | `CAP_SYS_ADMIN` read | **layer** | `check.ok` |
|---|---|---|---:|---|---:|---|---|---|---|
| **B1** | default (unmodified) | `--cap-add=SYS_ADMIN` | 0 | `00000000a82425fb` | 2 | **`EPERM`** (1) | `True` | **`runtime-seccomp-profile`** | `False` |
| **B2** | custom, `pivot_root` allowed | `--cap-add=SYS_ADMIN` | 0 | `00000000a82425fb` | 2 | **`EBUSY`** (16) | `True` | **`available`** | `True` |
| **B3** | `unconfined` | `--cap-add=SYS_ADMIN` | 0 | `00000000a82425fb` | 0 | **`EBUSY`** (16) | `True` | **`available`** | `True` |
| **B4** | default (unmodified) | `--cap-drop=ALL` | 1000 | `0000000000000000` | 2 | **`EPERM`** (1) | `False` | **`refused-unattributed`** | `False` |
| **B5** | custom, `pivot_root` allowed | `--cap-drop=ALL` | 1000 | `0000000000000000` | 2 | **`EPERM`** (1) | `False` | **`refused-unattributed`** | `False` |
| **B6** | `unconfined` | `--cap-drop=ALL` | 1000 | `0000000000000000` | 0 | **`EPERM`** (1) | `False` | **`refused-unattributed`** | `False` |

Reproduction, as run:

```bash
# B1 — the trap arm. Default profile, capability held.
docker run --rm -v "$PWD:/w" -w /w --cap-add=SYS_ADMIN python:3.12-slim python3 /d/arm.py B1
# B2 — one variable moved: the profile.
docker run --rm -v "$PWD:/w" -w /w --cap-add=SYS_ADMIN \
  --security-opt seccomp=./profile_ns.json python:3.12-slim python3 /d/arm.py B2
# B4/B5/B6 — one variable moved three ways: the filter, with the capability dropped.
docker run --rm -v "$PWD:/w" -w /w --cap-drop=ALL --user 1000:1000 python:3.12-slim ...
docker run --rm ... --security-opt seccomp=./profile_ns.json ...
docker run --rm ... --security-opt seccomp=unconfined ...
```

### What each pair licenses

**B1 → B2 is the seccomp cell.** Same capability, same uid, same image; the profile is the only
change, and `EPERM` becomes `EBUSY` and the layer becomes `available`. This is the control
[finding 025](./025-preflight-unshare-pair-measured.md) recorded as NC-6, re-run here through the
committed check rather than through a standalone probe. Without it, `EPERM` under the default
profile would be indistinguishable from a probe that could never have succeeded — Rule 8's shape.

**B2 → B3 is the negative control on the *custom profile itself*.** `seccomp=unconfined` removes the
filter entirely and reaches the same `EBUSY`. So B2's permitted reading is not an artifact of
something the hand-built profile allows by accident; it is what the kernel does when nothing is
filtering.

**B4 → B5 → B6 is the one that matters for the ambiguity, and it is the arm I expected to be
derived.** Three seccomp postures — default, custom-allowing-`pivot_root`, and none at all — at uid
1000 with every capability dropped. All three return `EPERM`, all three classify
`refused-unattributed`, and B5 and B6 differ from B4 in exactly the variable that would have to
matter if the filter were the refuser. **It does not matter.** The refusal in this posture is the
kernel's capability gate, and the check's refusal to name seccomp there is measured rather than
cautious.

## 2. The pre-T207 behaviour, in the same arm

`git show 95c871d:src/supervisor/preflight.py` in a scratch tree, same container flags as B1:

```
checks=7  ok=5
  FAIL FR-049  cannot create a child cgroup under /sys/fs/cgroup: [Errno 30] Read-only file system
  FAIL FR-049  cannot create a child cgroup at /sys/fs/cgroup/.f2a-preflight-kill-probe to probe cgroup.kill
```

Per-check, at `95c871d`, in the trap arm:

| requirement | `ok` | layer | what it said |
|---|---|---|---|
| OD-17 | `True` | — | `platform.system()='Linux' release='6.12.76-linuxkit'` |
| OD-17, FR-048, FR-049 | `True` | — | kernel floor satisfied |
| FR-049 | `True` | — | controllers available |
| FR-049 | `False` | — | **container artifact** — cgroupfs mounted read-only |
| FR-049 | `False` | — | **container artifact** — same cause |
| FR-048 | `True` | `available` | `unshare(0)` ok, `unshare(CLONE_NEWUSER)` ok — **correct** |
| FR-048 | `True` | — | seccomp user notification sizes ok |

With T207, the same arm: **8 checks, 5 ok**, and the new row reads
`FR-048 · ok=False · layer=runtime-seccomp-profile`.

**This is the correction in result 3.** The two red rows at `95c871d` are FR-049 and are caused by
Docker mounting `/sys/fs/cgroup` read-only; a `tmpfs` remount was tried and produces a *different*
FR-049 failure (`cgroup.controllers absent — cgroup v2 is not mounted`) rather than a green one, so
the wholly-green form of the trap arm was **not constructed and is not claimed**. What is measured
is that **FR-048 was entirely green** — including a `namespaces` check correctly reporting
`available`, which is exactly why T207 is a separate check and not an edit to that one.

## 3. Which cells are measured and which are derived

| cell | condition | status | evidence |
|---|---|---|---|
| `runtime-seccomp-profile` | `EPERM` **and** `CAP_SYS_ADMIN` held | **MEASURED** | B1, controlled by B2 and B3 |
| `available` via `EBUSY` | `EBUSY` | **MEASURED** | B2 and B3, controlled by B1 |
| `refused-unattributed` | `EPERM` **and** capability not held | **MEASURED** | B4, controlled by B5 and B6 — the filter removed, the result unchanged |
| `refused-unattributed` | `EPERM` and posture **unreadable** | **DERIVED** | no arm; `/proc/self/status` was readable in all six. Unit-tested by injection |
| `available` via `rc == 0` | the call succeeds | **DERIVED** | **never observed**, and see below |
| unexpected errno (e.g. `ENOSYS`) | any other errno | **DERIVED** | no arm produced one; its string says so |
| not attempted — non-Linux | `platform.system() != "Linux"` | **DERIVED** | guard, exercised by unit test only |
| not attempted — unknown arch | no recorded syscall number | **DERIVED** | guard, exercised by unit test only |

**On the `rc == 0` cell, which is derived and should stay that way.** `pivot_root("/", "/")` cannot
succeed: `/` is not a valid new root for itself. So every arm that was *permitted* returned `EBUSY`,
and that is the correct kernel behaviour rather than a missing measurement. **The permitted verdict
is measured** — twice, by B2 and B3. Only the `rc == 0` route into it is derived, and constructing
it would require a probe that actually pivots, which is a different and more dangerous mechanism
than the one that ships. The child is forked precisely so that if it ever *does* succeed, the
process that gets moved is one that is about to exit.

## 4. The observation step, and what it is not

`tools/unshare_pair_observation.py` runs the committed `_check_namespaces` and `_check_pivot_root`
under a posture read from `/proc/self/status`, and `.github/workflows/ci.yml` runs it twice —
unprivileged and under `sudo` — as a **non-gating** step.

**It has not produced the `kernel-sysctl-or-lsm` cell, and this finding does not claim it will.**
The prediction is written into the tool as `PREDICTED_LAYER` and is **DERIVED** from Ubuntu 24.04's
documented default for `kernel.apparmor_restrict_unprivileged_userns` and from **no observation of
the runner**. Until a CI run publishes a reading, that cell stays derived in T206's note.

Two arms of the tool were run locally, and both confirm the instrument rather than the prediction:

| arm | container | euid | `Seccomp` | `apparmor_restrict_…` | LSM | `namespaces` |
|---|---|---:|---:|---|---|---|
| unprivileged | `ubuntu:24.04`, default profile | 1001 | 2 | *absent* | *absent* | `runtime-seccomp-profile` |
| privileged | `ubuntu:24.04`, default profile | 0 | 2 | *absent* | *absent* | `runtime-seccomp-profile` |
| unprivileged | `ubuntu:24.04`, `seccomp=unconfined` | 1001 | 0 | *absent* | *absent* | **`available`** |
| privileged | `ubuntu:24.04`, `seccomp=unconfined` | 0 | 0 | *absent* | *absent* | **`available`** |

The third row is the negative control **on the instrument**: the tool is not hard-wired to report a
refusal, and it reports `available` when nothing refuses. The absent LSM and absent sysctl re-confirm
on an `ubuntu:24.04` userland what finding 025 recorded about this host — the guest distribution is
irrelevant, the kernel is linuxkit's, and **this host cannot construct the cell**. That is the whole
reason the step exists on a runner instead.

**Absence is the signal.** The renderer exits non-zero when a record is missing and emits a
`::warning::`, and `continue-on-error: true` keeps that from gating. Tested with the exact workflow
shell under `bash -e`, with one record deleted: the summary block reads
`### NO RECORD — THE OBSERVATION DID NOT HAPPEN`, names the missing path, and the annotation fires.
This repository has already lost a measurement to a silent pass — the native seccomp-overhead figure
— and that is the failure this guards.

## 5. Removal proofs

Three added to [`tests/removal_proofs.sh`](../../../tests/removal_proofs.sh), taking the declared
count from 86 to **89** (observed via `tools/check_tampers.py`, not computed). Each was run and each
fails its named test:

| tamper | test that catches it | why it is the right target |
|---|---|---|
| `_check_pivot_root()` removed from `run_checks()` | `test_run_checks_asks_about_pivot_root_after_it_asks_about_unshare` | this **is** the state `95c871d` was in |
| `EBUSY` scored as a refusal | `test_ebusy_is_permitted_because_the_call_reached_the_kernel` | inverts the verdict on a working host |
| `EPERM` blamed on seccomp without reading the capability | `test_eperm_without_the_capability_is_not_attributed_to_seccomp` | corrupts the attribution while leaving the verdict right, which is harder to see |

The last two are the ones worth having. Losing a check is visible; **inverting one is not**, and both
of those tampers leave a check present, running, and confidently wrong.

## 6. What is still open

- **`kernel-sysctl-or-lsm` remains DERIVED.** T208 is the attempt, not the answer. If the CI run
  reports something else, that is the result and the cell stays derived.
- **The wholly-green form of the trap arm was not constructed**, because cgroup delegation could not
  be arranged inside a container on this host. The FR-048 claim is measured; the whole-preflight
  claim is not, and is not made.
- **The `rc == 0` cell is derived and is expected to stay derived**, for the reason in §3.
- **`ENOSYS` and the two guards are derived.** Their strings say so.
