# Finding 025 — T206's seccomp cell is measured now, and so is the misreport it replaced: the pre-T206 check returns a byte-identical green string on a refusing host and a permitting one. The operator-trap arm reports green, correctly about `unshare` and on a configuration where the containment step is still refused — and the check set, not the check, is what has the gap

**Date**: 2026-08-04
**Feature**: 002. Converts the discriminating path of
[`src/supervisor/preflight.py`](../../../src/supervisor/preflight.py)'s `namespaces` check from
derived to measured, against a real seccomp refusal, by running **that check** rather than a
re-implementation of it.
**User Story**: US1, by way of FR-048 and [`tasks.md`](../tasks.md) **T206**.
**Owner decision**: **none is recorded here and the register was not edited.** The next free owner
decision number is `OD-26` — written inside a code span, which the corpus checker does not resolve
as an identifier, because writing it as a live token before the register carries the entry is a hard
`identifier-resolution` error. Nothing in this document rests on it. Same escape and same reason as
[finding 024](./024-deployment-surface-permission-census.md)'s header.
**Model spend**: **$0.0000.** No model was called and no credential was read. Twelve containers were
run locally; the only network requests were one image pull and one fetch of a public seccomp profile.
**Method**: our committed `namespaces` check, run unchanged inside eight container configurations
that differ from one another in one variable at a time, plus the **same check at the pre-T206
revision** run in two of those same configurations. **No arm ran `--privileged`**, and every row
below carries the privilege posture it was taken under, read from `/proc/self/status` in the arm
itself rather than inferred from the flag line.

**Revision discipline.** Every measurement was taken in a detached worktree at `c25b451`, because
the working tree could not collect the suite while a concurrent worker built the Phase 3 runtime
core. `main` reached `0661ab1` during the pass. `src/supervisor/preflight.py`,
`tests/unit/test_namespace_probe.py` and [`tasks.md`](../tasks.md) are **byte-identical between
`c25b451` and `0661ab1`**, and clean in the working tree, so nothing here is provisional on the
revision it was taken at. That is Rule 6 step 3 of the `experiment-design` skill, and it is stated
out loud because it is what licenses the numbers rather than being a formality.

Numbering note: `024` was the high-water mark across `specs/*/findings/`, checked by listing the
whole tree, and `025` was free at that moment and re-checked free immediately before saving.
[`findings/README.md`](../findings/README.md) records that this is a convention rather than a
mechanism.

---

> ## Read this first: four results, and the third is the one that is not in the brief
>
> **1. The seccomp cell is measured.** Our check, run under Docker's unmodified default profile at
> uid 1000 with `--cap-drop=ALL`, saw a real `EPERM` on **both** arms, classified it
> `runtime-seccomp-profile`, and emitted the full remedy — the 426→427 profile, the
> `--cap-add=SYS_ADMIN` warning, `pivot_root`, `IT DOES NOT WORK`, and the warning off
> `seccomp=unconfined`. Three independent arms produce that cell; five produce the permissive one.
>
> **2. The misreport it replaced is measured too, and it is worse than "wrong on a refusing host."**
> The pre-T206 check at `8e44aa5`, run in the *same two containers*, returns `ok=True` with the
> detail string **`mnt/user/pid/net present; max_user_namespaces=31337` in both** — byte-identical
> whether `unshare` is refused or permitted. It was not merely reporting the wrong answer; **it was
> constant across the entire treatment.** This is the untreated reading Rule 8 requires, and without
> it "T206 fixed a live misreport" is one bit that every instrument fault also produces.
>
> **3. The operator-trap arm reports green, and the gap it exposes is in the check *set*, not in the
> check.** Under `--cap-add=SYS_ADMIN` both arms are permitted, so the check reports
> `ok=True, layer=available` and emits no remedy at all — a 198-character detail with **0 of the 8**
> warning markers in it. That is *correct about `unshare`*, and the preventive warning is correctly
> placed on the arm the operator actually reads. But `pivot_root` is **still refused by seccomp in
> that arm** (measured here, independently of finding 024, with a control that moves), and
> **`run_checks()` contains no `pivot_root` check**. So the wrong grant is invisible to the whole
> preflight, not just to this one row. The remedy did not misfire; the coverage is incomplete.
>
> **4. The LSM cell remains unconstructible here and is not claimed.** Re-verified on this host
> rather than inherited: no `/sys/kernel/security/lsm`, no AppArmor, no SELinux, and `docker info`
> reports `seccomp` and `cgroupns` only. The sysctl cell could not be constructed either, and this
> pass adds two *observed* refusals of the construction route where finding 024 had one inferred one.

## The measured table, one row per arm

Every arm ran the same image (`python@sha256:57cd7c3a…`), the same mounted worktree at `c25b451`,
and the same driver, which contains **no probe of its own** — every syscall attempt and every layer
attribution below comes from `preflight._attempt_unshare` and `preflight._classify_unshare_pair`,
reached through the public `preflight.run_checks()`. Posture is read in the arm, before any attempt.

| Arm | Privilege posture (read in the arm) | Seccomp | `unshare(0)` | `unshare(CLONE_NEWUSER)` | check `ok` | check `layer` | remedy text |
|---|---|---|---|---|---|---|---|
| **A1** default profile (daemon builtin) | uid/gid 1000, `CapEff=0`, `CapBnd=0` | mode 2, 1 filter | **EPERM** | **EPERM** | **False** | `runtime-seccomp-profile` | **full, 7 of 8 markers** |
| **A2** custom profile (default + 1 name) | uid/gid 1000, `CapEff=0`, `CapBnd=0` | mode 2, 1 filter | ok | ok | True | `available` | none (198 chars) |
| **A3** fetched default, **unmodified** | uid/gid 1000, `CapEff=0`, `CapBnd=0` | mode 2, 1 filter | **EPERM** | **EPERM** | **False** | `runtime-seccomp-profile` | **full, 7 of 8 markers** |
| **A4** default profile, root, default caps | uid/gid 0, `CapEff=a80425fb` | mode 2, 1 filter | **EPERM** | **EPERM** | **False** | `runtime-seccomp-profile` | **full, 7 of 8 markers** |
| **A5** default profile **+ `--cap-add=SYS_ADMIN`** | uid/gid 0, `CapEff=a82425fb` | mode 2, 1 filter | ok | ok | **True** | `available` | **none** |
| **A6** default profile + `SYS_ADMIN`, **uid 1000** | uid/gid 1000, `CapEff=0`, `CapBnd=a82425fb` | mode 2, 1 filter | ok | ok | **True** | `available` | **none** |
| **A7** default + appended rule **only** | uid/gid 1000, `CapEff=0`, `CapBnd=0` | mode 2, 1 filter | ok | ok | True | `available` | none |
| **A8** `seccomp=unconfined` | uid/gid 1000, `CapEff=0`, `CapBnd=0` | **mode 0, 0 filters** | ok | ok | True | `available` | none |
| **U1** *pre-T206 code*, A1's flags | uid/gid 1000, `CapEff=0` | mode 2, 1 filter | not attempted | not attempted | **True** | *no `layer` field* | n/a |
| **U2** *pre-T206 code*, A2's flags | uid/gid 1000, `CapEff=0` | mode 2, 1 filter | not attempted | not attempted | **True** | *no `layer` field* | n/a |

**The eight markers, and why seven is the right number rather than eight.** The remedy text was
read for eight literal substrings: `426`, `427`, `--cap-add=SYS_ADMIN`, `pivot_root`, `does not
work`, `seccomp=unconfined`, `the bundle ships one`, and `DERIVED, NOT MEASURED`. The first seven
fire in A1, A3 and A4 and the eighth does not — correctly, because it belongs to the
`kernel-sysctl-or-lsm` branch, which no arm here reached. **All five permissive arms carry 0 of the
8**, and their details are byte-identical to one another. Marker presence is recorded as data; the
driver renders no verdict on whether presence is right for the arm.

**No arm is `--privileged`.** `CapEff=0` is the empty effective capability set;
`CapEff=a80425fb` is Docker's default set; `a82425fb` is that set with bit 21 — `CAP_SYS_ADMIN` —
added. **`Seccomp` mode is read from `/proc/self/status`**, so "a filter is installed" is a
measurement rather than a property of the flag line: mode 2 with one filter in every arm except A8,
which reports mode 0 and zero filters, exactly as `seccomp=unconfined` should.

Every row is `6.12.76-linuxkit`, aarch64, Docker Desktop server 29.4.1, `max_user_namespaces=31337`.
**No row is an x86-64 measurement and no row is a claim about x86-64.**

### The invariance guard, because the trap here has already cost a probe

Finding 024's probe read the outer uid *after* `unshare`, where it returns the overflow uid 65534,
and wrote a map naming a uid the process did not own. **Our probe cannot hit that**, because
`_attempt_unshare` forks and the child never returns — but that was asserted rather than assumed.
The driver reads uid, gid and all four `/proc/self/ns/` links before the first attempt and again
after `run_checks()` returns. **Unchanged in all eight treated arms.** The same property is what
`test_the_probe_does_not_move_the_process_that_ran_it` asserts, and in this pass that test stopped
being skipped: see [The committed suite](#the-committed-suite-passes-identically-on-both-hosts-and-that-is-the-gap-restated).

## The deliverable: which cells moved, and which did not

T206's classifier has seven outcomes — five cells of the pair and two pre-gates that short-circuit
before the pair is attempted. Precisely:

| Outcome in `preflight.py` | Before this pass | After this pass | Evidential basis |
|---|---|---|---|
| `runtime-seccomp-profile` — both arms refused | **Derived** from finding 024's separate probe | **MEASURED** | A1, A3, A4. Real `EPERM` from a real installed filter, classified by our code |
| `available` — both arms permitted | **Derived** | **MEASURED** | A2, A5, A6, A7, A8. Five arms, three different mechanisms of permission |
| **The discriminator itself** — that `unshare(0)` tracks the *profile* and not the *namespace* | **Derived** from finding 024's table | **MEASURED through our code** | `EPERM` in A1/A3/A4, `ok` in A2/A7/A8, same image, same uid, same capability set, profile the only difference |
| The seccomp branch's **remedy text** firing | Asserted against an injected pair | **MEASURED on a real refusal** | A1/A3/A4 carry `426`, `427`, `--cap-add=SYS_ADMIN`, `pivot_root`, `IT DOES NOT WORK`, `seccomp=unconfined` |
| The remedy text **not** firing on the permissive cell | Asserted against an injected pair | **MEASURED** | A2/A5/A6/A7/A8: 198 characters, **0 of 8 markers**, and all five details byte-identical |
| `kernel-sysctl-or-lsm` — no-op permitted, flag refused | **Derived** (source read of `create_user_ns()` at v6.12) | **STILL DERIVED. Unchanged.** | No arm produced it. No LSM exists on this host and the sysctl route was refused twice |
| `incoherent` — no-op refused, flag permitted | Derived, and **unconstructible in principle** | **Still unconstructed, and it should stay that way** | No layer produces it; that is the cell's entire premise |
| `not-attempted` — the call could not be made | Asserted against an injected attempt | **Still derived** | Constructible (a libc without the symbol, a failing `fork`) but not constructed here |
| `kernel-build` pre-gate — `/proc/self/ns/<n>` absent | Asserted against a fixture | **Still derived** | Needs a kernel built without namespaces |
| `sysctl-administratively-disabled` pre-gate — limit is `0` | Asserted against a fixture | **Still derived** | Two construction routes tried, both refused; see below |

**Read the second-to-last block as the honest limit.** Two of the five pair cells are measured, and
they are the two an operator on a container runtime will actually meet. The third —
`kernel-sysctl-or-lsm` — is the one that fires on Ubuntu 24.04, the most likely self-hosted host, and
**it is exactly as derived today as it was yesterday.** Its message still says `DERIVED, NOT
MEASURED` and that string is still accurate.

### The two construction routes for the sysctl cell, and how each was refused

Finding 024 could not construct a sysctl-layer refusal and recorded that **the cause of the failure
was itself inferred**. This pass tried two different routes and both produced an observed,
attributable refusal rather than an inferred one:

| Route | Result |
|---|---|
| `docker run --sysctl user.max_user_namespaces=0` | Refused by the Docker CLI: *"sysctl 'user.max_user_namespaces=0' is not allowed"*. `user.*` is not in the runtime's namespaced-sysctl allowlist |
| Bind-mount a file reading `0` over `/proc/sys/user/max_user_namespaces` | Refused by `runc`: *"cannot be mounted because it is inside /proc"* — the proc-safety check |

Neither would have produced a real kernel refusal in any case; the second would only have exercised
the *read* while leaving the kernel's limit untouched, and that is a weaker thing than a refusal.
**Both are recorded as failures to construct, not as evidence about the layer.**

## The untreated reading, which is what Rule 8 actually asks for

Our treatment's positive result is a **failure signal**: the check says `ok=False`. Every way the
instrument could itself be broken produces that same bit — a wrong worktree, an import that resolved
to different code, a probe that always reports refused. The A2/A3/A7/A8 arms exclude the last of
those. The reading below excludes the rest, and it is the one that turns *"T206 fixed a live
misreport"* from a claim into a measurement.

`_check_namespaces` at `8e44aa5`, the commit immediately before T206, reads `/proc/self/ns/` and the
sysctl and nothing else. Run in A1's container and in A2's container:

| | U1 — default profile (`unshare` **refused**) | U2 — custom profile (`unshare` **permitted**) |
|---|---|---|
| `namespaces` check `ok` | **`True`** | `True` |
| `detail` | `mnt/user/pid/net present; max_user_namespaces=31337` | `mnt/user/pid/net present; max_user_namespaces=31337` |

**The two strings are byte-identical.** The pre-T206 check is not a check that gets this host wrong;
it is a check whose output does not depend on the variable under test at all. The same two
containers, run against `c25b451`, produce `False`/`runtime-seccomp-profile` and
`True`/`available`. **That delta is the whole of T206, and it is now observed rather than argued.**

## The operator-trap arm, and the thing it exposes that the brief did not ask about

The brief's question was narrow and its answer is clean: **the remedy did not misfire.** The check
never says "add `SYS_ADMIN`"; it says `DO NOT USE --cap-add=SYS_ADMIN … IT DOES NOT WORK`, and it
says it on A1/A3/A4 — the arms an operator reads *before* making the change, which is the only place
a preventive warning is any use. Against the brief's second failure mode, though, the answer is yes:
**the check does go quiet when the capability is present.** A5 and A6 both report
`ok=True, layer=available` with no warning.

**Whether that is a defect turns on a distinction worth making carefully, and I do not think it is a
defect of this check.** The `namespaces` check's subject is `unshare`, and under `SYS_ADMIN`
`unshare` genuinely works — reporting a refusal there would be false. The problem is one level up.

### `pivot_root` is still refused in that arm, measured here with a control that moves

Our preflight has no `pivot_root` probe, so this was measured by a small auxiliary probe that is
**not** a test of our classifier — it asks the host one question with one syscall. The reading is
only unambiguous in an arm holding `CAP_SYS_ADMIN`, because the kernel's own `pivot_root` gate is
`CAP_SYS_ADMIN` and *also* returns `EPERM`; in an arm that holds it, an `EPERM` can only be seccomp.

| Probe arm | Posture | `pivot_root("/", "/")` | Reading |
|---|---|---|---|
| **P1** default profile, `--cap-add=SYS_ADMIN` | uid 0, `CapEff=a82425fb` | **`EPERM`** | The kernel's capability gate is satisfied, so **seccomp refused it** |
| **P2** custom profile, `--cap-add=SYS_ADMIN` | uid 0, `CapEff=a82425fb` | **`EBUSY`** | The call **reached the kernel**, which rejected the arguments |

**P2 is the negative control for P1** and it is the reason P1 is worth anything: an instrument whose
positive result is `EPERM` must be shown capable of returning something else. It returns `EBUSY`
under a one-flag change. This reproduces finding 024's `pivot_root` result on the same host **by a
different method** — a bare syscall rather than the full mount sequence — which is a genuine
corroboration rather than a restatement, because the two methods share no code.

### So the gap is in the check set

`run_checks()` runs seven checks: `platform`, `kernel_version`, `cgroup_v2`, `cgroup_delegation`,
`cgroup_kill`, `namespaces`, `seccomp_user_notification`. **None of them touches `pivot_root`**, and
`pivot_root` is the step FR-048's containment rests on. In A5 the `namespaces` row is green and the
two failing rows are `cgroup_delegation` and `cgroup_kill` — which fail because this arm has no
`--cgroupns=host` and no writable `/sys/fs/cgroup`, and which are exactly what finding 024's
condition 2 and [`tasks.md`](../tasks.md) **T160** commit the bundle to fixing.

**So the hazard is conditional and should be stated as conditional.** An operator who applies the
cgroup half of the bundle and reaches for `--cap-add=SYS_ADMIN` instead of the profile half gets an
**all-green preflight on a host where the mount sequence fails at the containment step** — which is
precisely the "reads as a broken mechanism rather than as a wrong grant" failure T206's remedy text
exists to pre-empt, arrived at by the one route the remedy text cannot reach, because by then it is
no longer being printed. Not measured end-to-end: the all-green claim is a composition of this
pass's A5 row with finding 024's cgroup row and was not run as a single arm.

## The committed suite passes identically on both hosts, and that is the gap restated

[`tests/unit/test_namespace_probe.py`](../../../tests/unit/test_namespace_probe.py), unchanged, run
inside the two containers:

| Arm | Result |
|---|---|
| A1 — real seccomp refusal | **14 passed** |
| A2 — real permission | **14 passed** |

**14 in both, and the same 14.** Every classification test injects the attempt function, so the
suite's verdict is independent of what the host does — which is the T206 caveat stated as a
measurement rather than as a description. Two things follow, and they point in opposite directions.
The suite **did not break** on a real host, which was not guaranteed and is worth having. And the
suite **cannot distinguish** the two hosts, so it can never be the artifact that closes this caveat.

Worth noting separately: `test_the_probe_does_not_move_the_process_that_ran_it` is marked
`linux_only` and skips on the developer host — 13 passed, 1 skipped there, named by
`tools/pytest_outcomes.py`. Inside these containers it **ran**, on both a refusing and a permitting
host, and passed. That is a small independent confirmation that the forked probe leaves the caller's
namespaces intact even when the syscall is refused.

## Negative controls

| # | What it controls | Construction | Reading |
|---|---|---|---|
| **NC-1** | That the fetched profile is the daemon's profile | A3: the profile fetched from `moby/profiles` run **unmodified** via `--security-opt`, beside A1's daemon builtin | **Identical on every cell** — same errno on both arms, same layer, and a **byte-identical 1402-character detail** — A4 matches them byte for byte too. This is what makes A2 a one-variable delta rather than a comparison across two unknown profiles. Reproduces finding 024's NC-1 |
| **NC-2** | That the treatment was actually applied | `Seccomp` and `Seccomp_filters` read from `/proc/self/status` in every arm | **mode 2 / 1 filter in seven arms, mode 0 / 0 filters under `seccomp=unconfined`.** A posture stated by the flag line is a claim; this is a reading |
| **NC-3** | That the permissive result comes from the **added rule** and not from the other edit | A7: the fetched default plus the appended rule, with the `clone` argument mask **left in place** | **ok on both arms.** The appended rule alone is sufficient, so A2's delta from A3 is one variable for this question |
| **NC-4** | That the probe does not always report refused | A2, A7, A8 — three different mechanisms of permission | **ok on both arms in all three.** An instrument that only ever produces the failure signal has no evidence about its own failure modes |
| **NC-5** | The **untreated state** (Rule 8 step 4) | U1 and U2: the pre-T206 check in the same two containers | **`True` in both, with byte-identical detail.** The claim is *A because B* and this is B |
| **NC-6** | That the `pivot_root` probe can report anything but `EPERM` | P2: the same probe, same capability, one profile changed | **`EBUSY`.** Without this, P1's `EPERM` is indistinguishable from a probe that cannot succeed |
| **NC-7** | That the probe did not move the process it measured | uid, gid and all four `/proc/self/ns/` links compared across each arm | **Unchanged in all eight treated arms.** Closes finding 024's overflow-uid trap by measurement rather than by inspection |

### The control I could not construct, stated plainly

**A refusal at the LSM layer.** Re-verified on this host rather than inherited from finding 024:
`/sys/kernel/security/lsm`, `/sys/kernel/security/apparmor`, `/sys/fs/selinux` and
`/sys/module/apparmor/parameters/enabled` are **all absent**, and `docker info` reports
`SecurityOptions` as `["name=seccomp,profile=builtin","name=cgroupns"]`. Docker Desktop's linuxkit VM
carries no LSM. **The LSM is what refuses on Ubuntu 24.04, the most likely operating system for a
self-hosted install, so the most consequential refusal our classifier can report is the one this host
cannot produce.** This is unchanged from finding 024 and it is the largest single gap in T206's
evidence. It is not closeable on this machine.

**One route to closing it that costs no new hardware, offered as a hypothesis and not as a result.**
`.github/workflows/ci.yml` runs the preflight as `sudo -E env "PATH=$PATH" python -m
src.supervisor.preflight` on a bare `ubuntu-latest` runner with no `container:` key — so there is no
runtime seccomp profile, the process is root, and both arms pass, exactly as the brief says. The
runner is Ubuntu 24.04 (`6.17.0-1020-azure`, per the note in `preflight.py`), which ships
`kernel.apparmor_restrict_unprivileged_userns` enabled by default; root under `sudo` is exempt from
it, which is why the current step sees nothing. **An additional, non-gating step that runs the pair
*unprivileged* on that same runner would plausibly produce the `kernel-sysctl-or-lsm` cell** — the
one cell nobody here can construct. **DERIVED: this rests on Ubuntu 24.04's documented default and
on no observation, the sysctl was not read on the runner, and the cell has not been produced. It is
a cheap experiment worth running, not a result.**

## What was wrong in the brief

Three things, in decreasing order of how much they matter. The brief asked for this and it is worth
more than agreement.

**1. "Does the remedy text fire?" framed the `SYS_ADMIN` arm as a test of the check, and the defect
it points at is not in the check.** The brief's stated failure modes were *reports "add SYS_ADMIN"*
and *goes quiet when it is present*. The second is literally true — A5 and A6 emit no warning — but
treating that as the check misbehaving is a category error, and acting on it would make the check
worse. Reporting a refusal where `unshare` succeeds would be a false statement about the syscall the
check measures, and the preventive warning is already on the only arm where an operator can act on
it. **The real finding is that `run_checks()` has no `pivot_root` check at all**, so the wrong grant
is invisible to the entire preflight rather than to one row. That is a coverage gap with a different
owner and a different fix, and the brief's framing would have routed it to the wrong place.

**2. "Docker's own default plus one added syscall name" is arithmetically exact and misleading about
mechanism.** The count reproduces perfectly — 426 distinct `SCMP_ACT_ALLOW` names across all rules
becomes 427, and the single newly allow-listed name is `pivot_root`, asserted rather than eyeballed
in the profile builder. But **`pivot_root` is not what unblocks the treatment.** `unshare` was
already among the 426; it sits in the 26-name rule gated on `CAP_SYS_ADMIN`. What makes A2 permit
`unshare` is the *seven names moved out of the capability gate*, which changes no count at all. So
"one added name" is the right number attached to the wrong cause for the arm this pass measures.
Finding 024's own cost table gets this right — *"one added syscall name **and seven moved out of the
capability gate**"* — and the brief dropped the second clause. A reader who built a profile by adding
only `pivot_root` would reproduce the count and not the result.

**3. "So 025 should be next" was correct, and one adjacent premise in the source it inherits from is
not.** Finding 024 writes that *"`seccomp` is name 0 of 361 in the profile's unconditional allow
list."* The 361 is right — that is `syscalls[0]`, the unconditional rule. `seccomp` is at **index
258** of it, not index 0; the list is alphabetically sorted. If "name 0" was meant as "one name
among 361" it is fine and ambiguous; if it was meant as an index it is wrong. Nothing depends on it
either way, and it is recorded rather than corrected because that document is not this pass's to
edit.

**What was right and worth saying so.** The host facts (29.4.1, aarch64, Docker Desktop), the CI
description (`sudo`, bare `ubuntu-latest`, no seccomp filter, both arms pass, silent on filtered
hosts), the `unshare(0)` discriminator's necessity, the overflow-uid trap, the LSM cell's
unconstructibility, the numbering, and `OD-26` being next free and not this pass's to take — all
confirmed, several of them by measurement rather than by assent.

## What remains unverified

- **One kernel, one architecture, one runtime, one profile family.** `6.12.76-linuxkit`, aarch64,
  Docker Desktop 29.4.1, moby's profile. **A result here is a point, not a floor**, and nothing
  above is a claim about x86-64, about containerd, about Podman, or about any other kernel.
- **The `kernel-sysctl-or-lsm` cell is unmeasured**, and it is the cell that fires on the most likely
  self-hosted host. Its `DERIVED, NOT MEASURED` label is still accurate and must stay.
- **The `incoherent`, `not-attempted`, `kernel-build` and `sysctl-administratively-disabled` outcomes
  were not constructed.** One of them — `incoherent` — is unconstructible by design; the other three
  are constructible and were not constructed.
- **The all-green hazard in A5 was not run as a single arm.** It composes this pass's A5 row with
  finding 024's cgroup measurement. Running it would need a container with `--cgroupns=host`, a
  writable `/sys/fs/cgroup` and `--cap-add=SYS_ADMIN` together, which was not done.
- **`pivot_root` was probed for syscall reachability, not exercised.** `pivot_root("/", "/")` cannot
  succeed; it distinguishes seccomp from the kernel and says nothing about whether a real mount
  sequence completes. Finding 024 measured that and this pass did not re-measure it.
- **The custom profile was not audited for escape**, and nothing here revisits finding 024's
  statement of what the eight exposed syscalls cost.
- **The CI hypothesis above is a hypothesis.** No unprivileged run was taken on the runner.
- **Docker Desktop's VM is not a self-hosted Linux host**, which is the same caveat finding 024
  carries and the reason result 4 in the box above is a limit rather than a finding.

## Reproduction

Probes are standalone and were written to `/tmp/f2a-t207/`; they are not committed, in keeping with
findings 021, 023 and 024. Measurements were taken in `git worktree add --detach /tmp/f2a-t207-wt
c25b451` and `… /tmp/f2a-t207-pre c69c38e^`.

```bash
# The profile. Asserts 426 -> 427 and that the one new name is pivot_root.
curl -sS -o default.json https://raw.githubusercontent.com/moby/profiles/main/seccomp/default.json
python3 build_profile.py            # appends the 8-name rule; strips the clone arg mask

# The eight treated arms. None is --privileged. Only the flag line varies.
COMMON=(--rm -e PYTHONDONTWRITEBYTECODE=1 -v /tmp/f2a-t207-wt:/repo:ro -v /tmp/f2a-t207:/probe:ro)
DRIVER=(python3 -u /probe/run_preflight_arm.py)

docker run "${COMMON[@]}" --user 1000:1000 --cap-drop=ALL           python:3.12-slim "${DRIVER[@]}" A1
docker run "${COMMON[@]}" --user 1000:1000 --cap-drop=ALL \
  --security-opt seccomp=/tmp/f2a-t207/profile_ns.json              python:3.12-slim "${DRIVER[@]}" A2
docker run "${COMMON[@]}" --user 1000:1000 --cap-drop=ALL \
  --security-opt seccomp=/tmp/f2a-t207/default.json                 python:3.12-slim "${DRIVER[@]}" A3
docker run "${COMMON[@]}" --user 0:0                                python:3.12-slim "${DRIVER[@]}" A4
docker run "${COMMON[@]}" --user 0:0 --cap-add=SYS_ADMIN            python:3.12-slim "${DRIVER[@]}" A5
docker run "${COMMON[@]}" --user 1000:1000 --cap-add=SYS_ADMIN      python:3.12-slim "${DRIVER[@]}" A6
docker run "${COMMON[@]}" --user 1000:1000 --cap-drop=ALL \
  --security-opt seccomp=/tmp/f2a-t207/profile_addedrule_only.json  python:3.12-slim "${DRIVER[@]}" A7
docker run "${COMMON[@]}" --user 1000:1000 --cap-drop=ALL \
  --security-opt seccomp=unconfined                                 python:3.12-slim "${DRIVER[@]}" A8

# The untreated reading: same containers, pre-T206 worktree.
docker run --rm -v /tmp/f2a-t207-pre:/repo:ro -v /tmp/f2a-t207:/probe:ro \
  --user 1000:1000 --cap-drop=ALL python:3.12-slim python3 -u /probe/run_untreated_arm.py U1

# The pivot_root reachability probe and its control.
docker run --rm -v /tmp/f2a-t207:/probe:ro --user 0:0 --cap-add=SYS_ADMIN \
  python:3.12-slim python3 -u /probe/pivot_root_reachability.py P1
docker run --rm -v /tmp/f2a-t207:/probe:ro --user 0:0 --cap-add=SYS_ADMIN \
  --security-opt seccomp=/tmp/f2a-t207/profile_ns.json \
  python:3.12-slim python3 -u /probe/pivot_root_reachability.py P2

# The committed suite, on a real refusing host and a real permitting one.
docker run --rm -v /tmp/f2a-t207-wt:/repo:ro -w /repo -e HOME=/tmp \
  --user 1000:1000 --cap-drop=ALL python:3.12-slim \
  sh -c 'pip install -q pytest; python -m pytest tests/unit/test_namespace_probe.py -q \
         -p no:cacheprovider -o cache_dir=/tmp/pc --basetemp=/tmp/pt'
```

Digests, so a re-run can confirm it used the same inputs: `default.json`
`536529b665dd0972c37bfb569f5d4ac8a53592e7b00752bc39ff063ca9864c74`, `profile_ns.json`
`7f1b0a4ed03313e5a4219da9cba29acd362b94e7637af6ce07d9112ae5e1a2c7`, image
`python@sha256:57cd7c3a7a273101a6485ba99423ee568157882804b1124b4dd04266317710de`.

## What this changes downstream

**Nothing outside this document and [`tasks.md`](../tasks.md)'s T206 record was edited by this pass.**
T206's ⚠️ note said *"The mechanism is untested against a real refusal"* and that the classification
was derived from finding 024 rather than re-measured; the first clause is now false for two of the
five pair cells and the second is now false for the same two. Both are struck and superseded there,
dated, with the part that survives — the `kernel-sysctl-or-lsm` branch and the LSM caveat — left
standing rather than swept along with them.

**Two items are recorded here and are not this pass's to apply**, in keeping with finding 024's
practice of naming them rather than reaching into documents it does not own:

- **The absent `pivot_root` check.** [The operator-trap arm](#so-the-gap-is-in-the-check-set)
  establishes that no check in `run_checks()` covers the step FR-048's containment rests on, and that
  the configuration where this bites is reachable by an operator following half the bundle. Whether
  that becomes a new preflight check, a note on T160, or a documented non-goal is a scoping decision
  and not a measurement.
- **The unprivileged CI arm.** Derived, cheap, and the only route identified to the
  `kernel-sysctl-or-lsm` cell that does not need a different machine.
