# Finding 024 — the self-hosted commitment survives, because the choice was never default-profile-versus-unconfined; a custom profile buys the namespace for one added syscall, and the mechanism that looked most at risk was never blocked at all

**Date**: 2026-08-04
**Feature**: 002. Establishes what the deployment surfaces a self-hosted operator would actually
run permit, before the privilege model measured in
[finding 023](./023-user-namespace-privilege-model.md) is committed to.
**User Story**: US1, by way of FR-048, FR-049 and the Target Platform section of
[`plan.md`](../plan.md).
**Owner decision**: **none is recorded here, and the register was deliberately not edited.** Where
this document needs to refer to the decision the owner has not yet taken it writes ~~`OD-24`~~
**a code span reserving the next free number, and 2026-08-04 that number is no longer `OD-24`** inside a
code span, which the corpus checker does not resolve as an identifier. Writing it as a live token
before the register carries the entry is a hard `identifier-resolution` error, and this document is
using the code-span escape deliberately rather than quietly.
**Corrected 2026-08-04 by the propagation pass, because the reservation collided rather than being
free.** OD-24 was already taken by the privilege-model decision this document defers to throughout,
and OD-25 by the per-result output bound; ~~**the next free number is `OD-26`**~~ **the next free
number is the register's high-water mark plus one, read from the register and not from here**, and the
live `OD-24` tokens added to this document below denote the privilege-model entry rather than the
reservation.

> **Restated 2026-08-05 — the second time this one sentence has gone stale in as many days, which is
> what disqualifies the value from being written at all.** `OD-26` was taken on 2026-08-05 by the
> decision settling which artifact owns FR-006's terminal-state taxonomy, so the reservation named a
> number that is not free *and* named it for a decision unrelated to this document's subject. A written
> next-free number fails in the **dangerous** direction: it does not go quiet, it instructs the next
> author to reuse a taken number — the exact collision the reservation exists to prevent. Stated as the
> rule rather than the value it cannot rot. No generator guards it, and deliberately: the dated
> corrections here assert what a number *was*, so any pattern matching a live claim would fire on them,
> which is the `register-range` false-positive trap documented in `tools/README.md` one file over.

The
reserved token appears nowhere in the body, so nothing derived here rests on it and the correction is
to the reservation alone. The precedent is the note under OD-21
that recording an owner decision *"required owner authority rather than a propagation pass"*, and
[finding 023](./023-user-namespace-privilege-model.md) declined on the same grounds.
**Model spend**: **$0.0000.** No model was called and no credential was read. Eight containers were
run locally; network requests were one pull of a public Python image and five reads of public git
mirrors — three container-runtime seccomp profiles and one kernel source file.
**Method**: one probe binary run unchanged across eight container configurations that differ from
each other in one variable at a time, plus a source read of three runtimes' default seccomp profiles
and of `create_user_ns()` at v6.12. **No probe ran `--privileged`**, and every row below carries the
posture it was taken under and whether it is measured or derived. The four surfaces this host cannot
produce are labelled derived and are not blended with the four it can.

Numbering note: `023` was the high-water mark across `specs/*/findings/` when this file was written,
checked by listing the whole tree, and `024` was free at that moment and re-checked free immediately
before saving. `findings/README.md` records that this is a convention rather than a mechanism and
that the duplicate is caught after the fact — which is what happened to finding 023, whose first
number was taken mid-pass.

---

> ## Read this first: three of the brief's premises did not survive, and the load-bearing one is a false dichotomy
>
> **1. The operator's choice is not "Docker's default profile" versus `seccomp=unconfined`.** There
> is a third option and it is the one that decides the question. **A custom profile that is Docker's
> own default plus one added syscall name lets an unprivileged process create a user namespace and
> run the entire mount sequence to `pivot_root`, at uid 1000 with `--cap-drop=ALL`.** Measured: the
> default profile carries an `SCMP_ACT_ALLOW` rule for **426** syscall names; the custom profile
> carries **427**. `seccomp=unconfined` carries none, because it installs no filter at all.
>
> > **Dated note, 2026-08-04 — this headline understates the change, and the understatement is
> > load-bearing for anyone building the profile.** Every figure above reproduces, and the cost table
> > in §*The operator's options* below already carries the missing half — *"one added syscall name
> > **and seven moved out of the capability gate**"*. But the headline as written names only the
> > added name, and **the added name is not what unblocks the mechanism**: `unshare` was already
> > among the 426, inside the 26-name rule gated on `CAP_SYS_ADMIN`, so what makes the custom profile
> > permit it is the seven names becoming reachable without that capability — a change that moves no
> > count. Re-measured through our own preflight in
> > [finding 025](./025-preflight-unshare-pair-measured.md), which isolates it with a control (NC-3).
> > Nothing measured here is withdrawn; the omission is a cause, not a number.
>
> **2. The mechanism the brief was most worried about was never blocked.** Seccomp
> user-notification — which the brief calls FR-050 and which is in fact FR-048's — **works under
> Docker's unmodified default profile**, at uid 1000 with `--cap-drop=ALL`. `seccomp` is name 0 of
> 361 in the profile's unconditional allow list. Every arm below returned a listener fd, including
> the two where `unshare` was refused outright.
>
> **3. `seccomp=unconfined` does not fix the mechanism that is actually hardest to get.** Cgroup
> v2 delegation is refused by a **different layer** — `/sys/fs/cgroup` is mounted read-only in the
> container, so `mkdir` returns `EROFS` — and no seccomp change touches it. Conversely it works
> **under the unmodified default profile** once the cgroup filesystem is mounted writable, because
> cgroup operations are file writes and not gated syscalls. Two mechanisms, two unrelated layers,
> and a fix aimed at one does nothing for the other.
>
> **The self-hosted commitment survives, under conditions that are nameable and small.** They are in
> [The verdict](#the-verdict-the-commitment-survives-under-four-named-conditions).

## The surface population, and what I changed about the brief's list

The brief's list was six entries and asked not to be accepted as complete. It is not complete, and
one of its omissions is the one that changes the answer.

**Kept, all six.** Docker with its default profile; Docker with `seccomp=unconfined`; Podman
rootless; a plain systemd service on a host; Kubernetes with a default `PodSecurityContext`; a
managed container service that does not expose the seccomp profile.

**Added four, each for a reason that showed up in measurement rather than in reasoning.**

1. **Docker with a custom seccomp profile.** The decisive omission. Framing the choice as
   default-versus-unconfined presents the operator with a security cost they do not have to pay, and
   it is the framing under which the self-hosted commitment looks unsurvivable. A profile is a JSON
   file and `--security-opt seccomp=./profile.json` is one flag.
2. **Docker with `--cap-add=SYS_ADMIN` under the default profile.** This is what an operator reaches
   for first, because the profile's own rule is written as a capability gate and the error message
   invites it. It is worth measuring precisely because it is both far more dangerous than a custom
   profile **and insufficient** — it leaves the containment step broken. An unmeasured surface that
   people will actually try is a worse omission than an exotic one they will not.
3. **The cgroup filesystem mount as a separate axis rather than a property of a surface.** FR-049
   is refused by the mount configuration, independently of every seccomp decision. Treating each
   surface as a single switch would have produced a table in which "Docker default" has one answer,
   when it has two answers to two different questions.
4. **Kubernetes with `seccompProfile: RuntimeDefault`, as a surface distinct from Kubernetes
   default.** These are opposite answers on one platform, and the distinction is not cosmetic: Pod
   Security Standards `restricted` **rejects** a pod that does not request `RuntimeDefault`, and GKE
   Autopilot applies it with no opt-out. A reader told only "Kubernetes" would take the permissive
   answer and be wrong wherever the strict policy is in force.

**Reframed one.** "A plain systemd service on a host" is not a surface, it is a family, and the
variation inside it is larger than the variation between the container runtimes. The kernel is
willing; what refuses is distribution policy — Debian's out-of-tree
`kernel.unprivileged_userns_clone`, Ubuntu 24.04's
`kernel.apparmor_restrict_unprivileged_userns`, and systemd's own `RestrictNamespaces=` and
`PrivateUsers=` unit directives, each of which refuses at a different layer. **None of these could
be reproduced on this host**, for a reason given in
[Negative controls](#negative-controls-including-the-two-i-could-not-construct).

**Dropped nothing.**

## The direct answer, per surface

| Surface | `unshare(CLONE_NEWUSER)` | Refusing layer | Posture | Basis |
|---|---|---|---|---|
| **Docker, default profile** | **EPERM** | **Runtime seccomp profile.** The rule is named below | uid 1000, `--cap-drop=ALL`; and uid 0 with default caps | **Measured** |
| **Docker, `--cap-add=SYS_ADMIN`, default profile** | **ok** | — (but `pivot_root` still EPERM) | uid 0, default caps **+ CAP_SYS_ADMIN** | **Measured** |
| **Docker, `seccomp=unconfined`** | **ok** | — | uid 1000, `--cap-drop=ALL` | **Measured** |
| **Docker, custom profile (default + 1 name)** | **ok** | — | uid 1000, `--cap-drop=ALL` | **Measured** |
| **Podman rootless** | **ok** | — | rootless, default profile | **Derived** from the profile source |
| **Plain systemd service** | **depends on the distribution, not on systemd** | Kernel sysctl, or LSM, or unit directive | n/a | **Derived** |
| **Kubernetes, default `PodSecurityContext`** | **ok** | — (seccomp is `Unconfined` by default) | pod default | **Derived** from documentation |
| **Kubernetes, `seccompProfile: RuntimeDefault`** | **EPERM** | Runtime seccomp profile (containerd's, same rule shape) | pod default | **Derived** from the profile source |
| **Managed container service (Fargate, Cloud Run, ACI, GKE Autopilot)** | **EPERM** | Runtime seccomp profile, not operator-changeable | n/a | **Derived** |

Every **Measured** row was taken on `6.12.76-linuxkit`, aarch64, under Docker Desktop 4.71.0, server
29.4.1. **No row is an x86-64 measurement**, and nothing here is a claim about x86-64.

### The refusing layer, named exactly

Docker's default profile does **not** carry a rule about `CLONE_NEWUSER`. It carries a rule about
the whole `unshare` syscall:

```json
{ "names": ["bpf","clone","clone3","fanotify_init","fsconfig","fsmount","fsopen","fspick",
            "lookup_dcookie","lsm_get_self_attr","lsm_list_modules","lsm_set_self_attr",
            "mount","mount_setattr","move_mount","open_tree","perf_event_open","quotactl",
            "quotactl_fd","setdomainname","sethostname","setns","syslog","umount","umount2",
            "unshare"],
  "action": "SCMP_ACT_ALLOW",
  "includes": { "caps": ["CAP_SYS_ADMIN"] } }
```

with `"defaultAction": "SCMP_ACT_ERRNO"` and `"defaultErrnoRet": 1` — that is, `EPERM` — for
anything no rule allows. A container without `CAP_SYS_ADMIN` gets no allow rule for `unshare` and
falls through to the default action.

**That distinction is not pedantry; it is the whole layer-attribution method.** A rule on the
syscall refuses every call, so **`unshare(0)` — the no-op flag set, which creates no namespace —
also returns `EPERM`.** No kernel-side namespace check can produce that reading, because there is no
namespace to refuse. Measured, in the default-profile arms:

| Call | Docker default, uid 1000, `--cap-drop=ALL` | `seccomp=unconfined`, same uid and caps |
|---|---|---|
| `unshare(0)` **← the discriminator** | **EPERM** | **ok** |
| `unshare(CLONE_NEWUSER)` | EPERM | ok |
| `unshare(CLONE_NEWNS)` | EPERM | **EPERM** |
| `unshare(CLONE_NEWPID)` | EPERM | EPERM |
| `unshare(CLONE_NEWUTS)` | EPERM | EPERM |

**The right-hand column is doing two jobs and the second is the more interesting.** It is the
positive control for the left-hand column — same image, same uid, same capability set, one flag
different — and it simultaneously shows a *kernel* refusal sitting beside the seccomp one:
`unshare(0)` passes and `unshare(CLONE_NEWNS)` still returns `EPERM`, because an unprivileged
process may not create a mount namespace without also creating a user namespace. **Two layers, two
readings, one arm.** That is what licenses the attribution in the left-hand column rather than
merely asserting it.

One documentation discrepancy worth recording: Microsoft's AKS page describing the containerd
default profile annotates `unshare` as *"gated by CAP_SYS_ADMIN (except for `unshare --user`)"*. The
parenthetical does not match either the profile source or the measurement — there is no
argument-level rule on `unshare` in moby's profile or containerd's, and `unshare(CLONE_NEWUSER)`
returns `EPERM` here. Recorded as a discrepancy, not resolved.

### Two things the default profile blocks that a capability cannot rescue

`pivot_root` appears in **no rule of the profile at all** — not in the unconditional allow list, not
in the `CAP_SYS_ADMIN` list. It therefore falls to `defaultAction` and returns `EPERM` **even in the
`--cap-add=SYS_ADMIN` arm**, which is why that arm gets all the way through the mount sequence and
fails on the one step that establishes containment:

| Step of `enter()`'s sequence | default profile | `--cap-add=SYS_ADMIN` | custom profile | `seccomp=unconfined` |
|---|---|---|---|---|
| `unshare(CLONE_NEWUSER\|CLONE_NEWNS)` | **EPERM** | ok | ok | ok |
| write `setgroups`/`uid_map`/`gid_map` | — | ok | ok | ok |
| `mount(/, MS_REC\|MS_PRIVATE)` | — | ok | ok | ok |
| `tmpfs` on the session root | — | ok | ok | ok |
| bind mount, `MS_BIND\|MS_REC` | — | ok | ok | ok |
| remount read-only | — | ok | ok | ok |
| **`pivot_root`** | — | **EPERM** | **ok** | ok |
| `umount2(MNT_DETACH)` | — | — | ok | ok |
| **verdict** | **blocked at step 1** | **blocked at the containment step** | **full sequence ok** | **full sequence ok** |

**Measured**, uid 1000 `--cap-drop=ALL` for columns 1, 3 and 4; uid 0 with default caps plus
`CAP_SYS_ADMIN` for column 2.

**The `--cap-add=SYS_ADMIN` column is the one to put in front of an operator.** It is the change
most likely to be made, it is by a wide margin the most dangerous of the three, and it does not
work. An operator who makes it will observe the mount tree build correctly and fail at the last
step, which reads as "the mechanism is broken" rather than as "you granted the wrong thing."

## The three mechanisms, and the FR numbers the brief had wrong

**Correction first, because two of the three numbers in the brief do not denote what it says.**
FR-050 is not seccomp user-notification. FR-050 is the credential-lifetime requirement — *"No
credential that outlives a session MAY be present in, or retrievable from, the agent's execution
environment"* — stated as three observable properties. Seccomp user-notification serves **FR-048**:
`spec.md` says `SECCOMP_USER_NOTIF_FLAG_CONTINUE` is what *"FR-048's whole recording design rests
on"*. [Finding 023](./023-user-namespace-privilege-model.md) carries the same mis-mapping in its
headline table and the brief appears to inherit it from there. Nothing measured changes; the labels
do.

| Mechanism | Requirement it serves | Docker default profile | What actually decides it |
|---|---|---|---|
| **Mount namespace + `pivot_root`** | FR-048 | **Blocked** | The seccomp profile, twice over: the `CAP_SYS_ADMIN` gate on `unshare`/`mount`, and `pivot_root` being absent from the profile entirely |
| **cgroup v2 bounds and `cgroup.kill`** | FR-049 | **Blocked, for an unrelated reason** | The **mount configuration**. `/sys/fs/cgroup` is `ro` in a container, so `mkdir` returns `EROFS`. Seccomp is not involved at any point |
| **Seccomp user-notification** | FR-048's recording path | **Works, unmodified** | Nothing. `seccomp` is in the profile's unconditional allow list, and the kernel's only gate on installing a filter is satisfied by `no_new_privs`, which the runtime sets |

### FR-049 is orthogonal to every seccomp decision, and that is a result

Measured across four arms, varying the two axes independently:

| Arm | seccomp | `/sys/fs/cgroup` | `mkdir` child cgroup | `memory.max` | `pids.max` | attach to `cgroup.procs` | `cgroup.kill` present |
|---|---|---|---|---|---|---|---|
| uid 1000, `--cap-drop=ALL` | default | `ro` (default) | **EROFS** | — | — | — | at root only |
| uid 1000, `--cap-drop=ALL` | unconfined | `ro` (default) | **EROFS** | — | — | — | at root only |
| uid 0, default caps | **default** | **`rw`** | **ok** | **ok** | **ok** | **ok** | **in child** |
| uid 0, default caps | custom | `rw` | ok | ok | ok | ok | in child |

**Row 3 is the load-bearing one.** Cgroup delegation works under Docker's *unmodified* default
seccomp profile, with no added capability — `--cgroupns=host` and a writable bind of
`/sys/fs/cgroup` are the whole requirement. And row 2 shows that `seccomp=unconfined`, the change
the brief was weighing, **buys nothing at all here.** A reader who took "unconfined enables the
model" away from this document would have made the mechanism no more available than it was.

### FR-048's recorder was never at risk

| Arm | `SECCOMP_GET_NOTIF_SIZES` | Install filter with `NEW_LISTENER` | Negative control: same install with **no** `no_new_privs` |
|---|---|---|---|
| Docker default, uid 1000, `--cap-drop=ALL` | ok | **ok, fd 3** | **EACCES** |
| Docker default, uid 0, default caps | ok | ok, fd 3 | **EACCES** |
| `--cap-add=SYS_ADMIN`, uid 0 | ok | ok, fd 3 | **ok** |
| `seccomp=unconfined`, uid 1000, `--cap-drop=ALL` | ok | ok, fd 3 | **EACCES** |
| custom profile, uid 1000, `--cap-drop=ALL` | ok | ok, fd 3 | **EACCES** |

**Measured.** The third column is the negative control and it moves in both directions, which is
what makes the second column believable. `EACCES` where neither disjunct of the kernel's gate is
satisfied; `ok` in the one arm holding `CAP_SYS_ADMIN`, because that is the second disjunct. This is
the four-cell table finding 023 derived from a source read at six kernel tags, reproduced here as a
by-product across a different axis — and it agrees.

## The derived surfaces, kept separate from the measured ones

**Podman rootless — derived from the profile source, which is stronger than derived from prose.**
`containers/common/pkg/seccomp/seccomp.json` has a single 370-name allow rule with
`"includes": {}` — **no capability gate at all** — and that rule contains `unshare`, `clone`,
`clone3`, `mount`, `umount2`, `setns` **and `pivot_root`**. Its `defaultAction` is
`SCMP_ACT_ERRNO` with `errnoRet` 38 (`ENOSYS`) rather than Docker's `EPERM`. **Podman's default
profile therefore does not refuse any of the three mechanisms**, and the difference from Docker is
not a rootless-versus-rootful difference — it is a different profile with a different policy about
namespace syscalls. Not measured: Podman is not installed on this host and the brief forbade
installing system packages. What is **not** established by this read is whether rootless Podman's
outer user namespace leaves a nested one creatable in practice, or whether the `subuid` range a
rootless container is given is wide enough for the multi-line map finding 023 showed to be
mandatory. Both are open.

**Kubernetes — derived from documentation, and the default is the permissive one.** A pod with no
`seccompProfile` runs `Unconfined` unless the kubelet was started with `--seccomp-default`, which
defaults to false. So **a default `PodSecurityContext` is more permissive than Docker's default**,
and the mechanism is available. The strict case is the one to plan for: Pod Security Standards
`restricted` rejects a pod that does not name `RuntimeDefault` or `Localhost`, and GKE Autopilot
applies the containerd default with no opt-out. Under `RuntimeDefault` the profile is containerd's,
whose `CAP_SYS_ADMIN` block was read at source and contains the same syscall list as moby's, and
which contains no `pivot_root` rule either. **So Kubernetes is both the most permissive and one of
the most restrictive surfaces on this list, and which one an operator gets is a cluster policy
decision they may not control.** `Localhost` is the escape and it requires writing a profile to
`/var/lib/kubelet/seccomp` on every node — a node-level filesystem operation, not a manifest change.

**Managed container services — derived, and the answer is no.** AWS Fargate documents that
`CAP_SYS_ADMIN` is restricted and privileged mode unavailable, and AWS closed the
user-namespace request against Fargate specifically while directing it to a different compute
product. AKS documents that only `RuntimeDefault` and `Unconfined` are supported and **custom
seccomp profiles are not**. GKE Autopilot applies the containerd default and disallows custom
profiles. **On these surfaces the operator has no knob**, and the distinction the brief asked for —
between a floor and a configuration — collapses in an instructive way: the *kernel* permits it, so
it is not a floor, but it is not a configuration the operator can reach either. It is a third thing,
and the honest label is *foreclosed by the platform*.

**Plain systemd — derived, and the variance is in the distribution.** The kernel gate is
`create_user_ns()`, read at v6.12, and it refuses along four distinct paths before it allocates
anything: `-ENOSPC` when `parent_ns->level > 32`, `-ENOSPC` when the ucount limit is hit, `-EPERM`
when `current_chrooted()`, `-EPERM` when the creator's own uid has no mapping in the parent
namespace, and then whatever `security_create_user_ns()` returns — **which is the LSM hook, and is
the layer the brief correctly said may be neither a floor nor a configuration**. What sits on that
hook varies: Ubuntu 24.04 ships an AppArmor restriction switched by
`kernel.apparmor_restrict_unprivileged_userns`, Debian has historically carried the out-of-tree
`kernel.unprivileged_userns_clone`, and a systemd unit can refuse independently via
`RestrictNamespaces=` (which is itself implemented as a seccomp filter) or `PrivateUsers=`. The
probe reads all four knobs and reports them; on this host **all four are absent**, which is exactly
why the systemd row is derived.

## Negative controls, including the two I could not construct

Rule 8 of `experiment-design` says an experiment whose positive result is a failure signal needs a
negative control, and most of this document's results are failure signals. Six controls were
constructed and executed. Two could not be, and both are limits on the result rather than details.

| # | What it controls | Construction | Reading |
|---|---|---|---|
| **NC-1** | That the fetched profile is the daemon's profile | Run the profile fetched from source **unmodified** via `--security-opt`, beside the daemon's built-in default | **Identical on every measured cell.** This is what makes the custom-profile arm a one-variable delta rather than a comparison across two unknown profiles |
| **NC-2** | That a seccomp refusal is distinguishable from a kernel refusal | `unshare(0)`, the no-op flag set | **EPERM under the profile, ok without it.** A namespace check cannot refuse a call that creates no namespace |
| **NC-3** | That the probe reports layers rather than reporting "blocked" for everything | Nest user namespaces to exhaustion, writing a map at each level | **33 levels created, then `ENOSPC`** — a different errno from the seccomp `EPERM`. Corroborated by source: `create_user_ns()` at v6.12 sets `ret = -ENOSPC` before `if (parent_ns->level > 32)` |
| **NC-4** | That a kernel refusal is visible beside a seccomp one in the same arm | `unshare(CLONE_NEWNS)` alone, in the arm where `unshare(0)` and `unshare(CLONE_NEWUSER)` both return ok | **EPERM.** Two layers, one arm, opposite readings |
| **NC-5** | That the mount probe can report failure at all | Mount `ext4` inside the user namespace, which the kernel does not permit | **EPERM in every arm that got that far.** An `ok` here would have made every other `ok` in the sequence suspect |
| **NC-6** | That the seccomp probe exercises the gate it claims to | Install the same filter with `no_new_privs` unset | **EACCES in four arms, `ok` in the `CAP_SYS_ADMIN` arm.** The control varies with posture in both directions, which is stronger than a control that only ever fails |

### The two I could not construct, stated plainly

**A sysctl-layer refusal.** The design was to set `user.max_user_namespaces` to 0 inside a namespace
the probe owns and observe a nested `unshare` refused by the ucount limit rather than by seccomp.
Docker mounts `/proc/sys` read-only, so the write needs a fresh `procfs` in a private mount
namespace — and **that mount returns `EPERM`**, measured, even holding in-namespace root with the
mount namespace and a pid namespace of the probe's own. The cause is almost certainly the kernel's
refusal to let a user namespace mount a procfs that would reveal paths the existing one has masked,
which is what Docker's masked-path configuration produces; **the probe did not isolate that cause
and it is inferred, not observed.** The consequence is that every sysctl-layer claim in this
document is derived. NC-3 covers the adjacent ground — it is also a kernel-limit refusal with a
distinct errno — but it is not the same layer.

**An LSM-layer refusal.** Not merely unconstructed but unconstructible here: `docker info` reports
`SecurityOptions` as `seccomp` and `cgroupns` only, and the probe finds no AppArmor module
parameter, no `/sys/kernel/security/apparmor`, no `/sys/fs/selinux` and no `/sys/kernel/security/lsm`.
**Docker Desktop's linuxkit VM carries no LSM at all.** Since the LSM is precisely what refuses on
Ubuntu 24.04 — the single most likely host operating system for a self-hosted install of this
product — **the most consequential refusal on the list is the one this host cannot produce.** That
is the largest single gap in this finding and it is not closeable without a different machine.

**One probe bug found and fixed mid-pass, recorded because it is the failure mode this repository
keeps hitting.** The first version read the outer uid with `getuid()` *after* `unshare`, where it
already returns the overflow uid 65534, and wrote a map naming a uid the process did not own. The
process then appeared to be root of its namespace while holding no authority over the filesystem it
had just mounted, and the sequence failed three steps later with `ENOENT` — a reading indistinguishable
from a surface property. The fix is two lines; the guard against a recurrence is an added assertion
step that checks `getuid() == 0` after the map is written and fails loudly if not. **Any later `ok`
in that sequence, taken before the assertion existed, would have been meaningless.**

## What it costs the operator, with the security cost stated rather than sold

Three options make the mechanism available on Docker. They are not close to equivalent and the
cheapest to type is the most expensive to hold.

| Option | Operator action | What it gives up | Does it work? |
|---|---|---|---|
| **`--security-opt seccomp=unconfined`** | One flag | **The entire filter.** Not one rule — all of it. The default profile carries an allow rule for 426 syscall names and denies everything else; unconfined restores every one of the denied ones, including `keyctl`, `add_key`, `request_key`, `userfaultfd`, `kexec_load`, `kexec_file_load`, `swapon`, `swapoff`, `move_pages` and `migrate_pages`, plus all 50 that are capability-gated | Yes |
| **`--cap-add=SYS_ADMIN`** | One flag | `CAP_SYS_ADMIN`, which is widely and correctly described as approximating root, and which also un-gates `bpf`, `ptrace`, `perf_event_open`, `init_module`, `finit_module`, `delete_module` and `open_by_handle_at` in the same stroke | **No.** `pivot_root` is still refused |
| **A custom profile** | Ship a JSON file; one flag pointing at it | **One added syscall name and seven moved out of the capability gate.** 426 allow-listed names becomes 427. `keyctl`, `add_key`, `userfaultfd`, `kexec_*`, `swapon`, `move_pages` and the rest **stay denied** | **Yes** |

**The custom profile is not free and this document is not selling it as free.** The eight syscalls
it exposes — `unshare`, `mount`, `umount2`, `setns`, `pivot_root`, `mount_setattr`, `move_mount`,
`open_tree`, plus `clone` with namespace flags — are exactly the container-escape-relevant set, and
CVE-2022-0185 (cited by Google's own GKE documentation as the reason `unshare` is denied) is reached
through this surface. **The honest framing is that the operator trades a specific, named eight-syscall
widening for the mechanism, instead of trading the whole filter for it.** That is a defensible trade
and `seccomp=unconfined` is not, and the difference between them is a file.

**FR-049's cost is separate and additive**, and it is the larger one in blast radius: `--cgroupns=host`
plus a read-write bind of `/sys/fs/cgroup` gives the supervisor container write access to the host's
entire cgroup tree, not to a delegated subtree. Narrowing that to a single delegated subtree is not
something the runtime's flags express, and no route to it was looked for here.

## The verdict: the commitment survives, under four named conditions

**OD-08's self-hosted commitment survives contact with the deployment surface.** It survives because
the premise that made it look doubtful — that the mechanism requires `seccomp=unconfined` — is
false. Four conditions, and none is a research question:

1. **The bundle ships its own seccomp profile.** `plan.md` already commits to *"a compose bundle we
   author"*; the profile is one more file in it, and the operator's action is a flag that is already
   in the compose file we write. **This is the condition that does the work.**
2. **The bundle mounts `/sys/fs/cgroup` read-write with `--cgroupns=host`**, and this is a separate
   change from the profile, refused by a separate layer, and not fixed by any seccomp decision.
3. **Preflight attempts a real `unshare(CLONE_NEWUSER)` in a forked child and reports which layer
   refused it** — including the `unshare(0)` no-op arm, because that one call is what separates "your
   runtime's profile is blocking this, here is the profile to use" from "your distribution's LSM is
   blocking this, here is the sysctl". Finding 023 already recommended the real `unshare`; **this
   document adds that the no-op arm is what makes the diagnostic actionable**, and it costs one
   syscall.
4. **The managed-container-service tier is documented as unsupported, not as degraded.** Fargate,
   Cloud Run, ACI and GKE Autopilot expose no knob. Under FR-053's *unsupported rather than
   best-effort* discipline — the same discipline `plan.md` applies to non-Linux platforms under
   OD-17 — these belong on the unsupported list. **They are not a degraded tier**, ~~because two of
   the three mechanisms are entirely absent and the third alone provides no containment.~~
   **Corrected 2026-08-04: the condition stands and this ground for it does not, because this document
   never established it.** The set is the right one — the three kernel mechanisms of
   [The three mechanisms](#the-three-mechanisms-and-the-fr-numbers-the-brief-had-wrong), which
   correctly exclude FR-050 because only one of its four layers is kernel. What the struck clause adds
   to that set is a **per-mechanism availability claim about these four surfaces**, and of the three
   only the mount namespace is placed there at all, on vendor documentation, the weakest basis above.
   Both other terms are unestablished. **The listener is not shown present**: it works under the
   *unmodified* default profile, so a profile the operator cannot change is not on its face an obstacle
   — but that arm is moby's, and none of the four surfaces' profiles was read for `seccomp` on the
   unconditional allow list or for `no_new_privs`. **Cgroup v2 is not shown absent**: it is refused by
   the cgroup mount configuration, which no seccomp finding here reaches, and nothing above checks
   `/sys/fs/cgroup` or `--cgroupns=host` on any of the four. **So no count of absent or surviving
   mechanisms is available from this document, and the condition never needed one** — the mount
   namespace alone is a missing term of Principle IV bullet 1, which the paragraph below already gives
   as sufficient. FR-050 was never in this count and is unaffected: three of its layers are
   application code, and the fourth holds a descriptor inside a network namespace, which the
   syscall-level `unshare` rule reaches and which no arm here measured, `CLONE_NEWNET` being absent
   from the four flags in
   [The refusing layer](#the-refusing-layer-named-exactly).

**What a degraded tier would look like, for completeness.** A surface with the seccomp mechanism and
the cgroup mechanism but no mount namespace has bounds and a recorder but no filesystem containment,
which is FR-048 unsatisfied — and `spec.md` says of Principle IV bullet 1 that *"a configuration
missing any one of its terms does not satisfy it"*. **So there is no degraded tier here that the
specification would accept.** Each surface either supports the full model or supports none of it,
and that is a property of the requirement rather than of the surfaces.

**What this does not decide.** Whether the supervisor holds `CAP_SETUID` — finding 023's central
open question — is untouched by anything measured here, and it is the harder of the two. This
document establishes that the *runtime* will permit the namespace; finding 023 establishes that the
namespace is not useful without a multi-line uid map, and that writing one needs a capability. ~~**The
two constraints are independent and both must hold.** A surface that permits `unshare` and a
supervisor that cannot write a map produces the self-mapped namespace whose hazards finding 023
measured.~~

> #### ⚠️ CORRECTED 2026-08-05 — the count survives, the independence does not, and nothing measured in this document moves
>
> **The live statement.** Both constraints still exist and both still bind. What is false is that they
> can be satisfied separately: **no posture binds exactly one, so a plan cannot satisfy one constraint
> and report partial progress on the other.**
>
> [Finding 023](./023-user-namespace-privilege-model.md)'s 2026-08-05 extension measured, on the
> `ubuntu-latest` runner, that Ubuntu's AppArmor permits `unshare(CLONE_NEWUSER)` and confines the
> result — the process enters `unshare` labelled `unconfined` and comes out labelled
> `unprivileged_userns (enforce)` — so the refusal lands on the `setgroups` and `uid_map` writes.
> Two consequences follow, both observed there. At `CapEff=0` the LSM refuses even the *self*-map, so
> the distinct-map write `CAP_SETUID` guards is never reached. And holding capabilities in the initial
> user namespace disables the LSM as a side effect, because Ubuntu's hook only transitions a process
> that lacks `CAP_SYS_ADMIN` there. **Mechanically they remain two** — different subsystems, different
> errnos, refusing different things, and only `CAP_SETUID` exists on a host with no AppArmor — which
> is why the count is untouched and only the independence is struck.
>
> **The second struck sentence is surface-dependent rather than wrong.** On a surface without the
> restriction it holds exactly as written, and the kernel every arm of this document ran on is one of
> them — though the measurement is finding 023's and not this document's: its extension records
> `setgroups` and the self-map both succeeding at `CapEff=0` on `6.12.76-linuxkit`. On Ubuntu 24.04
> with the restriction in force the self-map answers `EPERM` instead, so an incapable supervisor gets
> a namespace with **no** map rather than a self-mapped one.
>
> **Nothing this document measured changes.** The falsified claim is a framing written in *What this
> does not decide* about a question this document explicitly did not decide, and the corrected framing
> makes that question harder rather than easier. The same correction is applied at
> [`plan.md`](../plan.md)'s OD-24 note, where the sentence also appeared.

## What remains unverified

- **aarch64 only, one kernel.** Every measurement is `6.12.76-linuxkit`, aarch64. **No claim here is
  an x86-64 measurement.** The two syscall numbers this probe needed were taken from the aarch64
  table alone (`uapi/asm-generic/unistd.h`: `pivot_root` 41, `seccomp` 277), no x86-64 numbers appear
  in the probe source, and it **aborts rather than running** on an architecture whose table it does
  not carry. The `seccomp` number was additionally validated by behaviour before use —
  `SECCOMP_GET_NOTIF_SIZES` returned 0 with `sizeof(struct seccomp_data) == 64`, a fingerprint no
  other syscall produces. The `pivot_root` number carries no equivalent validation and is the weaker
  of the two.
- **No LSM anywhere on this host**, so the AppArmor and SELinux refusal paths are entirely derived.
  See [Negative controls](#negative-controls-including-the-two-i-could-not-construct).
- **No sysctl-layer refusal was produced**, and the reason it could not be is itself inferred.
- **Podman, Kubernetes, systemd and the managed services were not executed.** Podman and Kubernetes
  rest on reads of the actual profile source, which is stronger than prose; systemd and the managed
  services rest on vendor documentation, which is weaker.
- **Docker Desktop's VM is not a self-hosted Linux host.** It carries no LSM, its `/proc` masking is
  Docker Desktop's, and its `user.max_user_namespaces` is 31337 at the container top level, which is
  a linuxkit value and not a distribution default.
- **The custom profile was not audited for escape.** It was shown to permit the mechanism and to
  leave 60-odd syscalls denied. Whether the eight it exposes are jointly exploitable from inside the
  session sandbox was not tested and no attempt was made.
- **`cgroup.kill` was observed present, not exercised.** Finding 023 exercised it; this pass checked
  only that the file exists in a delegated child cgroup.
- **One kernel source file, one tag.** `create_user_ns()` was read at v6.12 only. Finding 023's
  six-tag discipline was not applied here and the ordering of the `ENOSPC` and `EPERM` returns may
  differ at 5.14.

## Reproduction

Probes are standalone and were written to `/tmp/f2a-surfaces/`; they are not committed, in keeping
with findings 021 and 023. Each container arm runs the same file and differs in flags only.

```bash
# The measured arms. None is --privileged.
docker run --rm --user 1000:1000 --cap-drop=ALL \
  -v /tmp/f2a-surfaces:/probe:ro python:3.12-slim python3 -u /probe/probe.py   # default profile
docker run --rm --user 1000:1000 --cap-drop=ALL --security-opt seccomp=unconfined ...
docker run --rm --user 1000:1000 --cap-drop=ALL \
  --security-opt seccomp=/tmp/f2a-surfaces/profile_ns.json ...                 # the custom profile
docker run --rm --user 0:0 --cap-add=SYS_ADMIN ...
docker run --rm --user 0:0 --cgroupns=host -v /sys/fs/cgroup:/sys/fs/cgroup:rw ...

# The three profiles read at source.
curl -sS https://raw.githubusercontent.com/moby/profiles/main/seccomp/default.json
curl -sS https://raw.githubusercontent.com/containers/common/main/pkg/seccomp/seccomp.json
curl -sS https://raw.githubusercontent.com/containerd/containerd/main/contrib/seccomp/seccomp_default.go

# The kernel gate behind the nesting control.
curl -sS https://raw.githubusercontent.com/torvalds/linux/v6.12/kernel/user_namespace.c \
  | sed -n '/^int create_user_ns/,/^}/p'
```

The custom profile is the fetched default with one appended `SCMP_ACT_ALLOW` rule naming
`unshare`, `mount`, `umount2`, `pivot_root`, `setns`, `mount_setattr`, `move_mount` and `open_tree`,
and with the argument mask removed from the non-`CAP_SYS_ADMIN` `clone` rule so namespace flags pass.

## What this changes downstream, stated for documents this pass may not edit

~~Nothing here was applied and no file outside this one was touched.~~ **Superseded 2026-08-04 — a
later propagation pass applied all four conditions, and this section is annotated rather than
rewritten so that what the measuring pass wrote stays legible beside what was done with it.** Where
each landed:

| Condition | Where it landed |
|---|---|
| **1 — the bundle ships its own seccomp profile** | [`plan.md`](../plan.md)'s Target Platform note and Project Type line; [`tasks.md`](../tasks.md) **T160**, as `deploy/compose/seccomp/session.json` with the eight-name rule and the `clone` argument mask removed. T160 is also forbidden from reproducing the default-versus-unconfined framing |
| **2 — `/sys/fs/cgroup` read-write with `--cgroupns=host`** | The same two sites, recorded as a *separate* change refused by a separate layer, with the host-wide cgroup write access stated as the cost rather than elided |
| **3 — the real `unshare` plus the `unshare(0)` no-op arm** | **Not already discharged.** `src/supervisor/preflight.py`'s `namespaces` check reads `/proc/self/ns/` and `max_user_namespaces` only — presence and a sysctl, neither of which is a syscall attempt — so it cannot see a runtime-profile refusal at all. [`tasks.md`](../tasks.md) **T206** is the extension, and it carries the `--cap-add=SYS_ADMIN` warning in its remedy text |
| **4 — managed container services are unsupported, not degraded** | [`spec.md`](../spec.md) at **FR-053**, as a note naming the four surfaces and the absent degraded tier; [`plan.md`](../plan.md)'s Complexity Tracking row and Target Platform note |

~~**The unconstructible LSM layer is carried with all four**~~ **The LSM layer *this host* could not
construct is carried with all four**, at the Target Platform note, at the
FR-053 note and in T206's own text, under the same *DERIVED, NOT TESTED* discipline the 5.14 kernel
floor carries — because a condition derived from a layer nobody could measure must not read as a
measured one. **`CAP_SETUID` is recorded as still open** at [`plan.md`](../plan.md)'s OD-24 note: a
permissive deployment surface does not unblock finding 023's privilege model, and both constraints
must hold.

> #### ⚠️ SCOPED 2026-08-05 — an LSM refusal is constructible after all, and every claim in this document about *this* host still stands
>
> **Why the adjective was struck rather than the sentence.** *The unconstructible LSM layer* reads as a
> property of the layer. It was never more than a property of the measuring host, and
> [finding 023](./023-user-namespace-privilege-model.md)'s 2026-08-05 extension makes the wider reading
> plainly false: an enforcing AppArmor refusal **was** constructed, on the `ubuntu-latest` runner, at
> the `setgroups` and `uid_map` writes rather than at the `unshare` this document's probe issued. The
> cell was being looked for at the wrong syscall.
>
> **Everything scoped to this host is untouched and is not restated.** The sentence *not merely
> unconstructed but unconstructible here* in
> [Negative controls](#negative-controls-including-the-two-i-could-not-construct)
> is a true dated record of a host carrying no AppArmor and no SELinux, and it is left exactly as
> written. So are the equivalently scoped statements in
> [finding 025](./025-preflight-unshare-pair-measured.md), [`plan.md`](../plan.md) and
> [`tasks.md`](../tasks.md).
>
> **What the four conditions still carry is unchanged in substance.** They are derived from a refusal
> that nobody has measured **on these four surfaces**, of **FR-048's mount namespace** — a different
> syscall on a different surface from the `uid_map` write finding 023 reached. The *DERIVED, NOT
> TESTED* discipline stays, and it stays for that reason rather than because an LSM refusal is
> unreachable anywhere.

**One correction was made outside the four conditions.** [`plan.md`](../plan.md)'s OD-24 note carried
the same over-strong inference this document flags in finding 023's reproduction section — that
Docker's default profile blocking `unshare` is *"not ours to choose"* under OD-08's self-hosted
model. The measured half stands and the inference is struck there: the bundle is exactly where it is
ours to choose. **OD-24's deferral is undisturbed**, because its first ground is untouched and
finding 023's open `CAP_SETUID` question replaces the second.

**Two items in this section were not applied by this propagation, and neither is this pass's to
edit**: finding 023's own reproduction section and its FR-050 label, which belong to that document
and are being carried there; and the owner decision this document reserved a number for, which is untaken and
whose reservation is corrected to `OD-26` in the header above. **No register entry was created**, and
no condition applied here was written as though one had been.

- **`plan.md`'s Target Platform** names the three kernel facilities and the 5.14 floor. Neither
  moves. What it does not say, and what the evidence says it should, is that **the facilities being
  present in the kernel does not make them reachable from the runtime the operator uses**, and that
  the compose bundle it already commits to authoring is where that gets fixed.
- **FR-053's unsupported-rather-than-best-effort discipline** currently reaches non-Linux platforms.
  On this evidence it also reaches managed container services, which are Linux and still cannot run
  the model.
- **[Finding 023](./023-user-namespace-privilege-model.md)'s reproduction section** says
  `seccomp=unconfined` is present because Docker's default profile blocks `unshare`, and calls that
  *"a real deployment constraint and not a probe artefact"*. **The first half is right and the
  conclusion is too strong**: it is a constraint on the default profile, not on the deployment, and
  a profile the bundle ships removes it. That document's FR-050 label is also wrong, as above.
- **Preflight's `namespaces` check** should attempt the real `unshare` finding 023 already asked
  for, and should additionally attempt `unshare(0)`, because the pair distinguishes a
  runtime-profile refusal from a kernel or LSM one and only the first has an operator remedy the
  bundle can supply.
