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

> ## CORRECTED IN PART, 2026-08-05 — the `EBUSY` cell was one errno of a class, and pinning it turned CI red on a host that permits the syscall
>
> CI run **30970910828** at `6df7da0` — the commit this finding documents — failed its gating
> `pytest (kernel mechanisms included)` job at *Confirm the Linux facilities are present*. The
> preflight has been red since. Nothing was blocked (this repository has no branch protection), but a
> red preflight gate makes every other measurement in the job unreadable.
>
> **Everything measured below stands.** All six arms of §1 reproduce their recorded layer against the
> corrected classifier, checked arm by arm. No row moved. What was wrong was not a reading; it was the
> **width of the class** one reading was generalised into.
>
> ### 1. `EBUSY` is not the permitted answer — it is *one* of them, and the other one is `EINVAL`
>
> All six arms in §1 ran under Docker Desktop, and all six permitting arms answered `EBUSY`. The
> classifier resolved `EBUSY` and nothing else, and reported every other errno
> `refused-unattributed`. The `ubuntu-latest` runner answered **`EINVAL`**:
>
> ```
> privileged (sudo): euid=0 CapEff=000001ffffffffff seccomp_mode=0 namespaces=available pivot_root=refused-unattributed
> ```
>
> **Confirmed fixed, run 31016201724.** The same runner, same errno, after the correction:
>
> ```
> [ok  ] pivot_root (FR-048): pivot_root("/", "/") EINVAL (errno 22: Invalid argument). this process
>        holds CAP_SYS_ADMIN ..., and no seccomp filter is installed (Seccomp: 0, ...). pivot_root
>        reached the kernel, which is the whole question.
> privileged (sudo): euid=0 CapEff=000001ffffffffff seccomp_mode=0 namespaces=available pivot_root=available
> ```
>
> All five jobs green, including the gating `pytest (kernel mechanisms included)` — the first green
> preflight since `6df7da0`. The unprivileged arm still reads `refused-unattributed`, and **that is
> correct rather than residual**: it is `EPERM` at `CapEff=0000000000000000`, an ambiguous reading
> reported as ambiguous, which is the distinction the brief's symptom description collapsed.
>
> `CapEff=000001ffffffffff` holds `CAP_SYS_ADMIN`; `Seccomp: 0` means **no filter was installed at
> all**. A syscall that no filter can have touched, past a capability gate that is satisfied, reported
> as refused. That is the **inverted verdict on a working host** that §5's second removal proof was
> written to catch — and the proof did not catch it, because *the proof pinned `EBUSY`* and reality
> supplied its sibling.
>
> **The kernel's ordering is the whole explanation, and it is a property of mount topology rather than
> of authority.** `path_pivot_root()` in `fs/namespace.c` runs its authority gates first and its
> argument checks after:
>
> | order | check | errno | kind |
> |---|---|---|---|
> | 1 | `if (!may_mount())` | `EPERM` | **authority** — the `CAP_SYS_ADMIN` gate |
> | 2 | `security_sb_pivotroot(old, new)` | whatever the LSM returns | **authority** — the LSM hook |
> | 3 | `IS_MNT_SHARED(old_mnt) \|\| IS_MNT_SHARED(ex_parent) \|\| IS_MNT_SHARED(root_parent)` | `EINVAL` | argument/state |
> | 4 | `check_mnt`, `MNT_LOCKED` | `EINVAL` | argument/state |
> | 5 | `d_unlinked(new->dentry)` | `ENOENT` | argument/state |
> | 6 | `new_mnt == root_mnt \|\| old_mnt == root_mnt` | `EBUSY` | argument/state |
> | 7 | `path_mounted`, `mnt_has_parent`, `is_path_reachable` | `EINVAL` | argument/state |
>
> Step **3 precedes step 6**. On a systemd host `/` is mounted shared, so the propagation check fires
> first and `pivot_root("/", "/")` answers `EINVAL`; inside a container whose root propagation is
> private it does not fire and the same call falls through to step 6 and answers `EBUSY`. Docker gave
> `EBUSY`, the runner gives `EINVAL`, and **the two hosts differ in mount propagation, not in whether
> the syscall is permitted.** The man page documents both — `EBUSY` for "`new_root` or `put_old` is on
> the current root mount (this error covers the pathological case where `new_root` is `/`)" and, among
> four `EINVAL` causes, "either the mount point at `new_root`, or the parent mount of that mount
> point, has propagation type `MS_SHARED`". Which one a host reports is settled by the source ordering
> above, not by the man page's list order.
>
> ### 2. `EPERM` is **not** the only authority refusal, and the obvious fix walks into that
>
> The rule "any errno other than `EPERM` proves the call reached the kernel" is **false**, and adopting
> it would have replaced one inverted verdict with another. Step 2 above is an authority gate that runs
> *before every argument check*, and it returns whatever the LSM returns:
>
> - **AppArmor returns `EACCES`.** `security/apparmor/mount.c`'s `build_pivotroot()` sets
>   `error = -EACCES` and clears it only for a profile carrying `AA_MAY_PIVOTROOT`.
> - **TOMOYO** is the only other LSM that registers an `sb_pivotroot` hook.
> - **SELinux and Smack register no hook for it at all** — a reading worth having on its own, since it
>   means SELinux cannot refuse `pivot_root` by this route.
>
> So an `EACCES` under no filter would have read as `available` on a host where an LSM refuses the
> syscall outright. The corrected classifier therefore resolves a **closed list of errnos the kernel is
> known to produce after both authority gates** (`EBUSY`, `EINVAL`) rather than a complement of `EPERM`,
> and treats `EPERM` and `EACCES` as authority refusals at **every** filter posture.
>
> ### 3. The seccomp mode is what makes the unknown-errno guard resolvable, and the guard survives
>
> The refusal to resolve an unfamiliar errno was **correct and is kept**: a profile's `defaultErrnoRet`
> can carry any errno, so under an installed filter an `EINVAL` is indistinguishable from a filter
> refusal wearing one. What the check never did was *read whether a filter was installed*. It reads
> `CapEff` out of `/proc/self/status` already; `Seccomp` is three lines further down the same file.
>
> | errno | `Seccomp` | layer | changed? | measured? |
> |---|---:|---|---|---|
> | `EBUSY`, or `rc == 0` | any | `available` | no — three arms closed this cell | yes, +arm A |
> | `EINVAL` | `0` | **`available`** | **new** — the cell CI produced | **yes** — CI, and arm B |
> | `EINVAL` | non-zero, or unreadable | `refused-unattributed` | new message; the guard, intact | **yes** — arm C |
> | `EPERM` + `CAP_SYS_ADMIN` | non-zero, or unreadable | `runtime-seccomp-profile` | no — B1, P1 both read `2` | yes, +arm D |
> | `EPERM` + `CAP_SYS_ADMIN` | `0` | **`refused-unattributed`** | **new** — see below | no — injection only |
> | `EPERM`, capability not held | any | `refused-unattributed` | no | yes, +arm E |
> | `EACCES` | any | `refused-unattributed`, LSM named | **new** | no — needs an LSM |
> | anything else | any | `refused-unattributed` | new message, same verdict | no — injection only |
>
> The `measured?` column names the arms of result 4's controlled experiment, which was run after this
> table was first written and moved three of its cells. Two cells remain injection-only, and both are
> honest about why: the narrowed `EPERM` cell needs a host that refuses `pivot_root` with `EPERM` while
> holding `CAP_SYS_ADMIN` and running no filter, and the `EACCES` cell needs an enforcing AppArmor or
> TOMOYO policy. No surface available to this project provides either.
>
> **An unreadable `Seccomp` is not `0`.** `0` licenses resolving an errno; "I could not read it"
> licenses nothing, and defaulting it to `0` would let a container that hides `/proc` turn a refusal
> into a permit. Three states, same discipline as `_read_cap_sys_admin`'s.
>
> **`ENOSYS` is deliberately *not* resolved even with no filter installed.** With nothing filtering,
> `ENOSYS` means the kernel does not implement the syscall — the opposite of available. This is why the
> resolved set is a closed list rather than a complement: an errno nobody has placed in
> `path_pivot_root()`'s control flow fails closed, and a red gate somebody reads beats a green one
> nobody checks.
>
> **The narrowed `EPERM` cell costs no measured row, which is why it was in scope.** §1's own
> arms B6 and T207's P5 measured an `EPERM` under `seccomp=unconfined` with `Seccomp: 0` — the
> observation §1 records as the reason not to name a profile. The check could never act on it, because
> it did not read the mode. It can now. B1 and P1, the arms that *do* produce
> `runtime-seccomp-profile`, both read `Seccomp: 2`, so no arm in this document sits in the narrowed
> cell and no recorded layer moves. Verified by replaying all six arms' readings through the corrected
> classifier.
>
> ### 4. The mount-topology claim is not a source-read — it is a controlled experiment, and so is the guard
>
> The ordering in result 1 was first established by reading `fs/namespace.c`, which is an argument and
> not a measurement. It was then **tested by changing the one variable it names.** Five arms, all on
> `6.12.76-linuxkit` under Docker Desktop, `CapEff=000001ffffffffff` where the capability is held:
>
> | arm | `/` propagation | seccomp | `CAP_SYS_ADMIN` | errno | layer |
> |---|---|---:|---|---|---|
> | **A** | `private` (Docker default) | `0` | yes | **`EBUSY`** (16) | `available` |
> | **B** | **`shared`** (`mount --make-shared /`) | `0` | yes | **`EINVAL`** (22) | `available` |
> | **C** | `private` | **`2`**, `errnoRet: 22` | yes | **`EINVAL`** (22) | **`refused-unattributed`** |
> | **D** | `private` | `2`, Docker default | yes | `EPERM` (1) | `runtime-seccomp-profile` |
> | **E** | `private` | `0` (`unconfined`) | **no** (`--user 1001`) | `EPERM` (1) | `refused-unattributed` |
> | **F** | **`shared`** | `2`, **permits `pivot_root`** | yes | **`EINVAL`** (22) | **`refused-unattributed`** ⚠︎ |
> | **G** | `private` | **`2`**, **`errnoRet: 16`** | yes | **`EBUSY`** (16) | **`available`** ⚠︎ |
>
> **A and B differ in exactly one variable and the errno changes.** Same kernel, same container image,
> same capability set, same seccomp mode, same syscall, same arguments — `mount --make-shared /` and
> nothing else. `EBUSY` becomes `EINVAL`. This is the mount-topology explanation **measured** rather
> than argued, and it is the reading that makes the `ubuntu-latest` runner's `EINVAL` unremarkable: a
> systemd host mounts `/` shared, so it takes B's branch, and a container takes A's.
>
> **C is the arm that matters more.** It is the attack the unknown-errno guard was written against,
> built deliberately: a seccomp profile whose only rule is `pivot_root → SCMP_ACT_ERRNO, errnoRet: 22`,
> so the filter *manufactures the very errno the permissive branch resolves*. It reads
> `refused-unattributed`. The permissive cell added for `EINVAL` did **not** open the hole it was
> required not to open, and that is now a measurement rather than a claim about a code path.
>
> **F and G are the two marked arms, and they are the most consequential thing in this correction.**
> Both were built after A–E, to attack the fix rather than to confirm it.
>
> - **F is a measured false refusal.** `/` shared *and* a filter installed that **permits**
>   `pivot_root`. The kernel produces `EINVAL` because propagation is shared; the check reads
>   `refused-unattributed` because a filter is installed. A working host reported as refused — the same
>   shape as the `6df7da0` bug this correction removes, in a different cell.
> - **G is a measured false permit, and it is the worse of the two.** A profile whose only rule is
>   `pivot_root → SCMP_ACT_ERRNO, errnoRet: 16`. The syscall never reaches `path_pivot_root()`, and the
>   check reads **`available`** — containment reported as working while a filter refuses the syscall
>   outright. It also printed, as its justification, *"a syscall refused by a seccomp filter never gets
>   that far"*, which arm G is the direct counterexample to.
>
> **Why neither verdict is changed here, stated as a decision and not an omission.** F and C are
> indistinguishable in every reading this check has — errno 22, `Seccomp: 2`, `CapEff` full — and one is
> the kernel while the other is a forgery. G and **B2** are indistinguishable the same way. So there is
> no reading available that separates the good case from the bad one in either pair, and the classifier
> is choosing *which failure to prefer*, not discovering a fact:
>
> | if the post-authority errno cell is… | the cost | who pays |
> |---|---|---|
> | gated on `Seccomp: 0` (what `EINVAL` does) | arm F: a red gate on a hardened host that permits the syscall | anyone shipping a permitting profile |
> | resolved at any posture (what `EBUSY` does) | arm G: a green gate while a filter refuses the syscall | anyone trusting the gate |
>
> **That is an operator's choice about which failure is worse, so it is escalated rather than settled
> inside a classifier.** The verdicts are left as they are — `EBUSY` resolves at any posture, `EINVAL`
> only at `Seccomp: 0` — because changing either moves a measured row (`EBUSY` moves B2; `EINVAL` would
> reopen the CI failure). **What was fixed is the false sentence**, which is indefensible either way:
> under a filter the `EBUSY` message no longer claims a filter could not have produced the errno, and
> now names the ambiguity and the way out of it (`seccomp=unconfined`). Arm A confirms the true form of
> the claim is still printed when `Seccomp: 0`, where it is sound.
>
> **What this does to the derived/measured split.** Three cells move — `EINVAL` + no filter (B, and the
> CI runner independently), `EINVAL` + filter installed (C and F), and the `EBUSY` cell gains two arms
> (A, and G as a **negative** reading rather than a confirming one). The §3 table below is updated
> accordingly. The `EACCES` cell does **not** move and cannot be moved here: linuxkit carries no
> AppArmor, which is the same wall result 7 hits.
>
> ### 5. Five removal proofs added, because a proof that pins one errno of a class proves only that errno
>
> §5's `EBUSY` proof is left exactly as it is — it is still a correct proof of a real mechanism. It was
> simply not a proof of the *class*. Five were added and each was run and watched to fail its named
> test, then restored:
>
> | tamper | test that catches it | the failure it is a proof of |
> |---|---|---|
> | the resolved class narrowed back to `EBUSY` alone | `test_einval_with_no_filter_installed_reached_the_kernel` | **this is exactly the state `6df7da0` was in** |
> | the `Seccomp: 0` gate dropped from the resolved class | `test_einval_with_a_filter_installed_or_unreadable_stays_unresolved` | a real seccomp refusal reads as available |
> | `EACCES` admitted to the resolved class | `test_eacces_is_never_read_as_reaching_the_kernel` | the mistake the obvious fix makes |
> | the withheld-errno branch collapsed into the unrecognised one | `test_einval_under_a_filter_is_not_described_as_an_unrecognised_errno` | a recognised errno reported as one nobody has a reading for, with the wrong remedy attached |
> | the `EBUSY` message's filter claim restored unconditionally | `test_ebusy_under_a_filter_does_not_claim_a_filter_could_not_have_caused_it` | **a measured falsehood (arm G) printed as the reason for a green gate** |
>
> The fourth exists because **arm C found a defect the verdict column hid.** Its layer was right, but
> the message it printed was the *unrecognised errno* text — "this errno is not one this check has a
> reading for" — which is false for `EINVAL` and carries the wrong remedy: the unrecognised cell has no
> remedy, whereas a withheld post-authority errno has an obvious one (re-read with the filter removed;
> if the errno then resolves, the filter was not the refusing layer). Same verdict, different sentence,
> and the sentence is what an operator acts on. That branch and its message are new.
>
> The asymmetry between the two cells — `EBUSY` resolved at any posture, `EINVAL` only at `Seccomp: 0`
> — is deliberate, is not a principle, and is argued in result 4 above with the two arms (F, G) that
> measure what each choice costs. It is escalated there rather than resolved.
>
> The declared count is **95**, observed from `tools/check_tampers.py` rather than computed from a
> baseline. Every cell of the table in result 3 is exercised by **injecting** the errno, the capability
> posture and the seccomp mode, so the whole table runs on a macOS laptop that can issue none of these
> calls. Read from the host, the seccomp mode on such a laptop is `None` — the conservative branch — so
> every permissive cell would have passed there without ever being evaluated.
>
> ### 6. What was wrong in the brief that commissioned this correction
>
> Recorded because the reasoning was supplied to be falsified rather than confirmed, and two thirds of
> it survived.
>
> - **Survived:** `EPERM` is an authority refusal; `EBUSY` and `EINVAL` both prove the call reached the
>   kernel; which of the two a host reports is a property of its mount topology and not of its
>   authority; `Seccomp: 0` removes the ambiguity the unknown-errno guard exists for.
> - **Wrong on the mechanism:** the brief derived the runner's `EINVAL` from "`new_root` is not a valid
>   mount point". For `("/", "/")`, `/` **is** a valid mount point. The `EINVAL` that fires is step 3's
>   `MS_SHARED` propagation check, which is a different documented cause and — decisively — the one
>   that *precedes* the `EBUSY` check. The conclusion was right; the stated reason was not, and the
>   reason is what would have gone into a code comment.
> - **Wrong on the premise:** "`EPERM` is the only authority refusal" omits step 2. AppArmor's hook
>   denies with `EACCES`, before every argument check. Result 2 above is that correction, and the third
>   new removal proof exists because of it.
> - **Wrong on the symptom:** the brief reports both CI arms as showing the same defect. They do not.
>   The **privileged** arm produced `EINVAL` and is the inverted verdict. The **unprivileged** arm
>   produced `EPERM` at `CapEff=0000000000000000`, which was classified `refused-unattributed`
>   correctly — an ambiguous reading reported as ambiguous. Both arms printed the same layer string for
>   different reasons, and only one of them was a defect.
>
> ### 7. The LSM prediction is falsified, and the sysctl being *enabled* is what makes it interesting
>
> §4 predicted `kernel-sysctl-or-lsm` for the unprivileged arm, derived from Ubuntu 24.04 shipping
> `kernel.apparmor_restrict_unprivileged_userns` enabled and from no observation of the runner. Run
> 30970910828 published the reading and **the prediction did not hold**:
>
> ```
> unprivileged: euid=1001 CapEff=0000000000000000 seccomp_mode=0 namespaces=available pivot_root=refused-unattributed
> ```
>
> `max_user_namespaces=63838`, `unshare(0)` ok, `unshare(0x10000000)` ok. **The unprivileged user
> namespace was permitted and AppArmor did not refuse.** `PREDICTED_LAYER` in
> [`tools/unshare_pair_observation.py`](../../../tools/unshare_pair_observation.py) is deliberately left
> unedited: changing it to match the result is the one thing that file's own instructions forbid.
>
> **This is not "the runner does not have the restriction", and the two must not be collapsed.** The
> same arms read, from the artifact rather than from the log line:
>
> | reading | unprivileged arm | privileged arm |
> |---|---|---|
> | `kernel.apparmor_restrict_unprivileged_userns` | **`1`** | **`1`** |
> | `kernel.unprivileged_userns_clone` | `1` | `1` |
> | `user.max_user_namespaces` | `63838` | `63838` |
> | `/sys/kernel/security/lsm` | `lockdown,capability,landlock,yama,apparmor,ima,evm` | same |
> | `/sys/module/apparmor/parameters/enabled` | **`Y`** | **`Y`** |
> | `/sys/module/apparmor/parameters/mode` | unreadable | **`enforce`** |
> | `unprivileged_userns` profile loaded | unreadable | **`true`**, of `123` profiles |
> | `CapEff` | `0000000000000000` | `000001ffffffffff` |
> | `Seccomp` / `Seccomp_filters` | `0` / `0` | `0` / `0` |
>
> So the switch is **on**, AppArmor is **loaded, enforcing, and in the active LSM list**, the
> restriction's own profile is **loaded**, the process held **no capabilities at all**, and the namespace
> was created anyway. That is a materially different and more consequential result than the sysctl being
> absent, which is how every arm taken locally read (§4's table: *absent*, on a linuxkit kernel with no
> AppArmor). The last two rows come from run **31016201724**, which is the first run carrying the
> readings this correction added; the rest are from 30970910828.
>
> **Two mechanisms could explain it. The readings added by this correction ran, and they eliminate the
> first.**
>
> 1. ~~**The restriction's profile is not loaded.**~~ **FALSIFIED, run 31016201724.** Ubuntu implements
>    the restriction by transitioning an unconfined process onto a hard-coded profile named
>    `unprivileged_userns`, which the AppArmor *userspace* package ships. The hypothesis was that the
>    sysctl was on with nothing to transition to. It is not: the profile **is** loaded.
> 2. **The restriction does not refuse `unshare(CLONE_NEWUSER)` in the first place.** On the published
>    reading of Ubuntu's patch, the hook **permits** the namespace and confines the result; the denial
>    lands afterwards, on the `CAP_SYS_ADMIN` the confining profile withholds, which surfaces at the
>    `uid_map` write rather than at the `unshare`. **This is now the surviving explanation**, and if it is
>    right, this probe cannot construct `kernel-sysctl-or-lsm` on any Ubuntu 24.04 host — the mechanism
>    the cell was written for is not a refusal of the syscall the probe issues, so the cell needs a
>    different *probe*, not a different host. That failure lands in finding 023's `uid_map`/`CAP_SETUID`
>    territory instead.
>
> The readings that separated them, from run **31016201724**'s privileged arm — the unprivileged arm
> cannot read the profile list, which is why the reading is carried on both:
>
> | reading | privileged arm | unprivileged arm |
> |---|---|---|
> | `restriction_profile_loaded` (`unprivileged_userns`) | **`true`** | `null` (list unreadable) |
> | `loaded_profile_count` | **`123`** | `null` |
> | `/sys/module/apparmor/parameters/mode` | **`enforce`** | `null` |
> | `/proc/self/attr/current` | `unconfined` | `unconfined` |
> | `profiles_readable` | `true` | `false` |
>
> So on this runner AppArmor is **enforcing**, the restriction's profile **is loaded**, the sysctl reads
> **`1`**, the process label is `unconfined` — the branch Ubuntu's hook keys on — and an unprivileged
> user namespace was **still created** at `CapEff=0000000000000000`. Every precondition for the
> restriction to fire was present and the namespace was permitted anyway. That is as far as this probe
> can take it: mechanism 2 is now **DERIVED and unfalsified** rather than one of two guesses, and
> confirming it requires probing the `uid_map` write, which is a different mechanism and a different
> finding. Mainline's `apparmor_userns_create()` carries no such sysctl, so mainline source cannot
> settle it either.
>
> Note the `null`s in the unprivileged column are the design working, not data missing:
> `/sys/kernel/security/apparmor/profiles` is root-readable only, so the arm under test reports
> `restriction_profile_loaded: null` — **not `false`**. Reporting `false` there would have let the arm
> that cannot see the policy assert the policy is absent, which is the exact inversion that produced
> this whole correction.
>
> **The consequence for the classifier, stated plainly.** The `kernel-sysctl-or-lsm` cell remains
> **UNCONSTRUCTED on every surface available to this project**: Docker Desktop's linuxkit VM carries no
> AppArmor and no SELinux, and the GitHub runner has AppArmor loaded with the restriction enabled and
> does not refuse. The single most consequential refusal path for the most likely self-hosted OS is
> still underived, and there is now a live possibility that it is not reachable by this probe at all.
>
> ---
>
> ## Read this first: four results, and the third is a correction to the brief that produced this work
>
> **1. The `pivot_root` check's discriminating cells are measured.** Under Docker's unmodified
> default profile with `--cap-add=SYS_ADMIN`, our check sees a real `EPERM` **while holding the
> capability**, classifies it `runtime-seccomp-profile`, and emits the remedy. A custom profile that
> allows `pivot_root` flips the same arm to `EBUSY` and the same check to `available`. One variable,
> and the verdict moves.
>
> **2. ~~`EBUSY` is the permitted answer~~ `EBUSY` is *a* permitted answer, and it is measured twice.**
> **(Narrowed 2026-08-05: `EINVAL` is the other one, and which of the two a host reports depends on its
> mount propagation. Result 1 of the correction block above.)** `pivot_root("/", "/")` cannot
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
| `available` via `EBUSY` | `EBUSY` | **MEASURED** | B2 and B3, controlled by B1; a fourth arm 2026-08-05 (correction result 4, arm A) |
| `refused-unattributed` | `EPERM` **and** capability not held | **MEASURED** | B4, controlled by B5 and B6 — the filter removed, the result unchanged |
| `refused-unattributed` | `EPERM` and posture **unreadable** | **DERIVED** | no arm; `/proc/self/status` was readable in all six. Unit-tested by injection |
| `available` via `rc == 0` | the call succeeds | **DERIVED** | **never observed**, and see below |
| ~~unexpected errno (e.g. `ENOSYS`)~~ | ~~any other errno~~ | ~~**DERIVED**~~ | ~~no arm produced one; its string says so~~ |
| **`available` via `EINVAL`** | **`EINVAL` and `Seccomp: 0`** | **MEASURED, 2026-08-05** | **twice, independently: CI run 30970910828's privileged arm on `ubuntu-latest` (`CapEff=000001ffffffffff`, `Seccomp: 0`), and correction result 4's arm B, which reaches it by making `/` shared and is controlled by arm A on the same kernel and image** |
| **`refused-unattributed` via `EINVAL`** | **`EINVAL` and a filter installed** | **MEASURED, 2026-08-05** | **correction result 4's arms C and F. C forges the errno (`pivot_root → errnoRet: 22`); F reaches it from the kernel on a shared-`/` host whose filter *permits* `pivot_root`. C is the cell working; **F is the cell wrong** — a false refusal — and the two are indistinguishable from here** |
| **`available` via `EBUSY` under a filter** | **`EBUSY` and a filter installed** | **MEASURED, 2026-08-05 — and measured WRONG** | **correction result 4's arm G: `pivot_root → errnoRet: 16` reads `available` while the filter refuses the syscall. A false permit, indistinguishable from measured arm B2. The verdict is escalated in result 4, not changed; the false justification it printed was removed** |
| **unexpected errno under a filter** | **`ENOSYS` or anything unlisted, any posture** | **DERIVED** | **no arm produced one; its string says so** |
| **`refused-unattributed` via `EACCES`** | **`EACCES`, any filter posture** | **DERIVED** | **no arm; no surface available to this project carries an enforcing LSM. Source-read of `security/apparmor/mount.c`, unit-tested by injection** |
| not attempted — non-Linux | `platform.system() != "Linux"` | **DERIVED** | guard, exercised by unit test only |
| not attempted — unknown arch | no recorded syscall number | **DERIVED** | guard, exercised by unit test only |

> **Superseded 2026-08-05, and this is the row that mattered.** The struck row collapsed `EINVAL` into
> "any other errno" alongside `ENOSYS`, and the two are not alike: `EINVAL` is produced by
> `path_pivot_root()` *after* both authority gates and `ENOSYS` is not produced by it at all. CI run
> 30970910828 produced `EINVAL` on a host that permits the syscall and the check reported it refused.
> The three replacement rows are the split. See the correction block at the head of this document for
> the kernel ordering that decides which of `EINVAL` and `EBUSY` a given host reports.

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

~~**It has not produced the `kernel-sysctl-or-lsm` cell, and this finding does not claim it will.**~~
**Superseded 2026-08-05 — it has now run, and it did not produce the cell.** The prediction is written
into the tool as `PREDICTED_LAYER` and is **DERIVED** from Ubuntu 24.04's documented default for
`kernel.apparmor_restrict_unprivileged_userns` and from **no observation of the runner**. ~~Until a CI
run publishes a reading, that cell stays derived in T206's note.~~ **CI run 30970910828 published the
reading: the unprivileged arm reported `available` at `euid=1001` with `CapEff=0000000000000000`, with
the AppArmor sysctl reading `1` and AppArmor loaded. The cell stays derived, and the reason is now a
measured refusal-to-refuse rather than an absent run.** Result 7 of the correction block at the head of
this document carries the full readings, the two candidate mechanisms, and the readings added to the
tool to separate them.

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

- ~~**`kernel-sysctl-or-lsm` remains DERIVED.** T208 is the attempt, not the answer. If the CI run
  reports something else, that is the result and the cell stays derived.~~ **Superseded 2026-08-05 —
  the CI run reported something else, and that is the result.** The cell remains **DERIVED** and is now
  **UNCONSTRUCTED on every surface available to this project**: linuxkit carries no LSM, and the
  `ubuntu-latest` runner carries AppArmor with the restriction *enabled* and permits the namespace
  anyway. It is also now open whether the cell is reachable by this probe at all — Ubuntu's restriction
  may permit `unshare(CLONE_NEWUSER)` and confine the result rather than refuse the call. Result 7 of
  the correction block has the evidence and the two readings added to settle it.
- **The `EACCES` cell is DERIVED and needs an enforcing LSM to measure.** It is the `pivot_root`
  sibling of the gap above, and it has the same cause: no measuring surface here carries an enforcing
  AppArmor or SELinux policy. Worth recording that SELinux cannot close it either — SELinux registers
  no `sb_pivotroot` hook, so only AppArmor and TOMOYO can produce this cell at all.
- **The wholly-green form of the trap arm was not constructed**, because cgroup delegation could not
  be arranged inside a container on this host. The FR-048 claim is measured; the whole-preflight
  claim is not, and is not made.
- **The `rc == 0` cell is derived and is expected to stay derived**, for the reason in §3.
- **`ENOSYS` and the two guards are derived.** Their strings say so.
