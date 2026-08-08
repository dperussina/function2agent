# Finding 023 — the user namespace works for all three mechanisms, the doubted one was never at risk, and the namespace on its own closes neither authority gap it was chosen to close

**Date**: 2026-08-04
**Feature**: 002. Measures the privilege model proposed for
[`src/supervisor/mounts.py`](../../../src/supervisor/mounts.py),
[`src/supervisor/cgroup.py`](../../../src/supervisor/cgroup.py) and
[`src/supervisor/seccomp.py`](../../../src/supervisor/seccomp.py) against the kernel, before any of
them is changed.
**User Story**: US1, by way of FR-048, FR-049, FR-017 and SC-022.
**Owner decision**: **none is recorded here, and the register was deliberately not edited.** The
owner's decision is not yet in the register; where it appears below it is written as `OD-24` in a
code span, which the corpus checker does not read as an identifier, because writing it as a live
identifier is an error until the register carries it. See
[Where the decision is recorded](#where-the-decision-is-recorded-and-why-this-pass-did-not-write-it).
**Updated 2026-08-04: the register now carries OD-24 and OD-25, so the constraint described above
has lifted.** The code spans below are left exactly as written, because they record the state this
pass ran under; text *added* after the register landed — the dated correction blocks — uses the live
token instead, and the difference is deliberate rather than an inconsistency.
**Model spend**: **$0.0000.** No model was called and no credential was read. Nine containers were
run locally; the only network requests were pulls of one public Python image and six reads of
`kernel/seccomp.c` from a public git mirror.
**Method**: seven probes inside Linux containers on the local Docker host, plus a source read of the
one capability gate that decides the doubted mechanism, taken at six kernel tags rather than one.
**No probe ran `--privileged`**, and every result below carries the posture it was taken under.
Claims are labelled observed, read-from-source, inferred or unverified, and the four are not
blended. The limits of the host are in
[What remains unverified](#what-remains-unverified-and-where-the-host-is-not-the-target).

Numbering note, and **the convention's advertised failure mode fired on this pass**: `021` was the
high-water mark when the probes started, checked by listing `specs/*/findings/` over the whole tree,
and `022` was still free when this file was written. Another pass filed
[`022-e7-tool-result-truncation-cap.md`](./022-e7-tool-result-truncation-cap.md) in the interval, and
`findings-numbering` caught the duplicate on the first checker run. Renumbered to `023`, re-checked
free. `findings/README.md` says of the single-sequence scheme that *"two features filing on the same
day can collide"* and that the numbering note is *"a convention, not a mechanism — the duplicate is
caught after the fact"*. That is exactly what happened, and the after-the-fact catch worked.

> ### ⚠️ Corrected 2026-08-04 — a label, not a result. Every measurement in this document stands.
>
> Seven sites below cited FR-050 for seccomp user-notification. FR-050 is the credential-lifetime
> requirement; the seccomp listener serves **FR-048**, whose recording clause requires an attempted
> read or write outside the declared set to be recorded with the rule that produced it, and which
> `spec.md` names directly: `SECCOMP_USER_NOTIF_FLAG_CONTINUE` is what *"FR-048's whole recording
> design rests on."* No probe, posture, verdict or cost figure changes — this document measured the
> right mechanism under the wrong heading. Surfaced by
> [finding 024](./024-deployment-surface-permission-census.md).
>
> **Corrected in place rather than struck.** This file's strike-and-supersede convention is reserved
> for a claim that fell — a number, or an inferential limb, as at the `⚠️ CORRECTED` block further
> down. Nothing here fell, and two of the seven sites cannot carry a strikethrough at all: one is a
> heading, whose anchor a strike would corrupt, and one is a comment inside a fenced `bash` block,
> where `~~` does not render. The seven read correctly below; this note is the record that they
> once did not.

---

> ## EXTENDED 2026-08-05 — the LSM refusal cell is CONSTRUCTIBLE after all, it lands on this document's `uid_map` write, and "two independent constraints" is wrong about the independence rather than about the count
>
> **Nothing below is struck.** Every measurement in this document reproduces exactly, on a second
> host, including on the arm that has an LSM. What is added is a mechanism this document could not
> see, because no surface available when it was written had AppArmor enforcing.
>
> [Finding 026](./026-pivot-root-check-measured.md) measured, on `ubuntu-latest`:
> `kernel.apparmor_restrict_unprivileged_userns` = `1`, AppArmor **enforcing**, the
> `unprivileged_userns` profile **loaded** among 123, the process label `unconfined`, `CapEff=0` — and
> `unshare(CLONE_NEWUSER)` **permitted anyway**. Every precondition for the restriction to fire was
> present and the namespace was created. The surviving explanation was that Ubuntu permits the
> `unshare` and confines the *result*, which would move the denial to this document's `uid_map` write.
> The probe was extended past the `unshare` and run on that runner (run **31022713003**).
>
> **It is confirmed, and by direct observation of the mechanism rather than by inference from a
> denial.**
>
> ### 1. The readings
>
> Both arms read their label *inside* the new namespace, which is what separates an LSM from the
> capability check that was always there:
>
> | reading | unprivileged arm (`CapEff=0`) | privileged arm (`sudo`) |
> |---|---|---|
> | label **before** `unshare` | `unconfined` | `unconfined` |
> | `unshare(CLONE_NEWUSER)` | **ok** | ok |
> | label **inside** the new namespace | **`unprivileged_userns (enforce)`** | `unconfined` |
> | `CapEff` inside the new namespace | **`000001ffffffffff`** — full | `000001ffffffffff` |
> | write `deny` to `setgroups` | **`EACCES`** | ok |
> | write self-map `0 1001 1` | **`EPERM`** | ok |
> | write distinct map `0 100000 1`, by the parent | `EPERM` | **ok** |
>
> **The third row is the whole finding.** The process enters `unshare` labelled `unconfined` and comes
> out labelled `unprivileged_userns` in **enforce** mode. That is Ubuntu's restriction, observed doing
> the thing it does: it does not refuse the namespace, it transitions the creator onto a confining
> profile. `apparmor_userns_create()` in mainline carries no such sysctl, so no source read could have
> settled this — only a host with the patched kernel and the profile loaded, which is why the cell
> looked unconstructible.
>
> ### 2. The refusal is AppArmor's, and the `CapEff` row proves it without needing a control
>
> `CapEff` **inside** the new namespace is `000001ffffffffff` — the full set, which is what a fresh
> user namespace always grants its creator — and the writes fail anyway. A refusal at a full effective
> capability set is not the ordinary capability check. Two further separations:
>
> - **`setgroups` answers `EACCES`, which is AppArmor's errno**, not `EPERM`. Writing `deny` to
>   `setgroups` is the *permissive* direction and is exactly what an unprivileged process is supposed
>   to be able to do before writing a map.
> - **The same two writes were measured on a host with no LSM at all.** On `6.12.76-linuxkit` under
>   Docker at `CapEff=0`: `setgroups` **ok**, self-map **ok**. Same operations, same posture, opposite
>   answers. The variable is AppArmor.
>
> So this is a **`kernel-sysctl-or-lsm` refusal, measured** — the cell
> [finding 024](./024-deployment-surface-permission-census.md) and finding 026 both recorded as
> unconstructed on every available surface. It is constructible; it was being looked for at the wrong
> syscall.
>
> ### 3. Are the LSM refusal and the `CAP_SETUID` question one constraint or two?
>
> The framing this document has been read with is *two independent constraints that must both hold*.
> **The count is right and the independence is wrong**, and the distinction matters because it changes
> what a green deployment surface buys.
>
> **Mechanically they are two, and they are not the same check:**
>
> | | what fires it | what it refuses | present on |
> |---|---|---|---|
> | **A — the LSM** | an `unconfined` process without `CAP_SYS_ADMIN` creating a user namespace | *everything* — `setgroups`, and even the self-map that needs no capability | only a host with Ubuntu's patch, the sysctl on, and the profile loaded |
> | **B — `CAP_SETUID`** | a map naming a uid other than the writer's | only the distinct map; the self-map is permitted | **every** Linux host, LSM or not |
>
> They refuse different things, with different errnos, from different subsystems, and B is the one
> this document measured on a host that has no A at all.
>
> **Operationally they collapse to one question, and this is the correction.** They are not
> independent, because a single posture change disables both and no posture binds exactly one:
>
> - At `CapEff=0`, **A fires first and B is never reached.** A refuses the self-map, so the writer
>   never gets as far as the distinct map that B guards. Measured above: self-map `EPERM`.
> - Holding capabilities in the initial user namespace **disables A as a side effect**, because
>   Ubuntu's hook only transitions a process that lacks `CAP_SYS_ADMIN` there. Measured above: the
>   privileged arm's label inside the namespace stayed `unconfined`, and every write succeeded.
>
> So there is **no posture on this host where A binds and B does not, or B binds and A does not.**
> Both answer to *does the supervisor hold capabilities in the initial user namespace?* — which is
> already this document's [`OD-24`/`OD-25`](#where-the-decision-is-recorded-and-why-this-pass-did-not-write-it)
> question. Two mechanisms, one remedy, one decision.
>
> **What this changes for a deployment surface.** Treating them as independent invites a plan that
> satisfies one and reports partial progress — "we have `CAP_SETUID`, the LSM is a separate work
> item". That plan is incoherent: a supervisor holding `CAP_SETUID` in the initial namespace is
> already outside A's trigger, and a supervisor holding nothing fails A before B is legible. The
> honest statement is that the multi-line uid map needs a capable writer, and that on Ubuntu 24.04
> the LSM makes the *incapable* case fail earlier and harder than this document measured.
>
> > #### ✅ THE ONE QUESTION IS ANSWERED 2026-08-08 AS OD-29 — "yes", and it retires **both** mechanisms at once
> >
> > **This section's central claim is what made the answer a single act, and it held.** *Does the
> > supervisor hold capabilities in the initial user namespace?* is answered **yes** at
> > [`plan.md`](../../001-discovery-validation/plan.md)'s **OD-29**: the supervisor **may** hold
> > `CAP_SETUID` and `CAP_SETGID`, and it writes the map **directly** rather than through a helper.
> > Because no posture binds exactly one of A and B, that one answer disposes of both — **two
> > mechanisms, one remedy, one decision**, as this section put it. Nothing here is corrected.
> >
> > **The side effect this section measured is recorded by OD-29 as a cost rather than a solution.**
> > Holding capabilities disables A, so the resulting namespace is **not** AppArmor-confined. That is a
> > real widening accepted deliberately, and an entry claiming A had been *satisfied* would be claiming
> > a property the posture gives up.
> >
> > **What the answer does not do is start the build.** OD-29 retires OD-24's *replacement* second
> > ground; OD-24's ground ① is untouched, is sufficient alone, and retires only on a requirement. **The
> > 13–20 day build stays deferred.**
>
> - **Whether A can be satisfied without capabilities**, by a `newuidmap` setuid helper — the third
>   option in this document's [decision](#where-the-decision-is-recorded-and-why-this-pass-did-not-write-it).
>   `newuidmap` is itself AppArmor-profiled on Ubuntu and was not run here.
>   - ⚠️ **Measured 2026-08-05, and the answer is the opposite of the way this bullet frames the
>     question** — [finding 028](./028-od24-deferral-re-examination.md). **A cannot be satisfied
>     without capabilities by this route: the helper needs *more* authority, not less.** `newuidmap`
>     requires `CAP_SYS_ADMIN` in the bounding set (`EACCES` at `CapBnd 0`, `EPERM` under Docker's
>     default 14, `ok` with that one bit added), where a direct map write by the namespace's creator
>     needs only `CAP_SETUID`+`CAP_SETGID`. The reason is not packaging: `map_write()` demands
>     `CAP_SYS_ADMIN` over the *target* namespace judged at open time, and a namespace's creator
>     satisfies that for free because the owner is judged **by euid** — a setuid helper forfeits the
>     shortcut by the very act of becoming euid 0. **This bullet's own caveat still stands**: that
>     measurement is on the no-LSM host, so it remains unrun under an enforcing AppArmor profile.
> - **The privileged arm is `sudo` on a runner, not a supervisor design.** It shows the trigger
>   condition, not that holding capabilities is the right answer.
> - **One distribution, one kernel.** A is Ubuntu's patch. It is not upstream and says nothing about
>   RHEL, Debian or SUSE.


> ## Read this first: the mechanism you doubted is fine, and the reason you gave for it being fine is not the reason
>
> **Seccomp user-notification was never at risk, and the listener's position is irrelevant to
> whether it works.** Both shapes work — listener outside *and* listener inside. The kernel has
> never gated `SECCOMP_FILTER_FLAG_NEW_LISTENER` on `CAP_SYS_ADMIN`; it gates *installing any
> filter at all*, and it gates it on **`no_new_privs` OR `CAP_SYS_ADMIN` in the caller's own user
> namespace**. Our code always sets `no_new_privs`, so the first disjunct is satisfied and the
> capability question never arises. Read from source at v5.0, v5.4, v5.5, v5.9, v5.14 and v6.12,
> and measured as a four-cell table on 6.12.
>
> Three things that were *not* on the list did not survive.
>
> 1. **The user namespace closes neither of finding 021's authority gaps.** Both reproduce
>    identically inside it, because the workload keeps in-namespace root and in-namespace root owns
>    the `tmpfs` it just mounted. The closure is still the `setuid` drop. Observed: with the
>    workload at in-namespace uid 0, `mkdir` at an undeclared path in the session root returned
>    `ok`; after dropping to a second mapped uid, `EACCES`.
> 2. **A single-entry map has no uid to drop to.** `setuid(65534)` inside a namespace mapping only
>    uid 0 returns `EINVAL`. So the mitigation from finding 021 requires a **multi-line** map — and
>    an unprivileged writer cannot write one. Observed: `EPERM` from a uid-1000 writer, `ok` from a
>    writer holding `CAP_SETUID`.
> 3. **Under a self-map the workload can `SIGKILL` the supervisor.** In-namespace root maps to the
>    supervisor's own kernel uid, so they are the same uid to the signal check. Observed: the
>    workload killed an out-of-namespace process, status 9. Under a distinct map the same call
>    returns `EPERM`, and adding `CLONE_NEWPID` (with the workload forked *after* the unshare)
>    returns `ESRCH`.
>
> **`OD-24` as literally worded — "root inside, unprivileged outside" — is not buildable, and the
> word that fails is "unprivileged".** Every one of the three above is repaired by the same thing:
> the supervisor must hold `CAP_SETUID`/`CAP_SETGID` long enough to write a multi-line map. The
> nearest buildable variant is in
> [The verdict](#the-verdict-not-buildable-as-worded-and-the-nearest-variant).

## The direct answer, per mechanism

| Mechanism | Verdict | Posture the evidence was taken under |
|---|---|---|
| **FR-048 mount namespaces** | **Works with a named change.** The full `enter()` sequence runs, but the `mode="rw"` remount fails with `EPERM` when the source lies under a mount inherited read-only from the parent namespace | uid 1000, `--cap-drop=ALL`, no `--privileged` |
| **FR-049 cgroup v2** | **Works with a named change.** The pre-exec barrier and `cgroup.kill` are unaffected; delegation requires an explicit `chown` of four files to the mapped uid, and without it every write is `EACCES` | container root with the default capability set, `--cgroupns=host`, writable cgroupfs, no `--privileged` |
| **FR-048 seccomp user-notification** — the recording half | **Works unchanged, in both listener positions.** `RECV`, `ID_VALID`, `SEND` with `SECCOMP_USER_NOTIF_FLAG_CONTINUE` and `ADDFD` all succeed with the workload in a user namespace. FR-048 has two mechanisms and this is the second: the mount namespace above **enforces** the boundary, this listener **records** the attempt, and they are deliberately not collapsed | uid 1000, `--cap-drop=ALL`, no `--privileged` |

All three rows are **observed on `6.12.76-linuxkit`, aarch64.** None is an x86_64 claim; see
[What remains unverified](#what-remains-unverified-and-where-the-host-is-not-the-target).

## FR-048's recorder — the one you doubted, and why the doubt was misdirected

### The source, read at six tags rather than one

There is exactly one capability check on the path that installs a filter, and it is not on the
listener flag. At v6.12, `seccomp_prepare_user_filter`:

```c
	/*
	 * Installing a seccomp filter requires that the task has
	 * CAP_SYS_ADMIN in its namespace or be running with no_new_privs.
	 */
	if (!task_no_new_privs(current) &&
			!ns_capable_noaudit(current_user_ns(), CAP_SYS_ADMIN))
		return ERR_PTR(-EACCES);
```

At v5.5 and v5.9 the same test is spelled
`security_capable(current_cred(), current_user_ns(), CAP_SYS_ADMIN, CAP_OPT_NOAUDIT) != 0`, and at
v5.0 the same call without the audit flag. **All four forms are scoped to `current_user_ns()`, not
to the initial namespace.** `init_listener()` contains no capability check at any of the six tags.
`seccomp_notify_addfd()` contains no capability check at v6.12 — it validates flags, resolves the
source fd, and matches the notification id. The three `capable(CAP_SYS_ADMIN)` sites that do exist
in the file at every tag are `seccomp_get_filter`, `seccomp_get_metadata` and the
`actions_logged` sysctl writer, none of which is on our path.

**Read-from-source, not measured**, for v5.0 through v5.14; measured at v6.12.

### The measured gate, as a four-cell table

Installing a `NEW_LISTENER` filter, uid 1000, `--cap-drop=ALL`:

| `no_new_privs` | in a user namespace | result |
|---|---|---|
| set | no | listener fd returned |
| set | yes | listener fd returned |
| **not set** | **no** | **`EACCES`** |
| not set | yes | listener fd returned |

The one failing cell is the one the source predicts, and it is a cell our code never enters —
`install_filter` sets `no_new_privs` unconditionally. The fourth row is the interesting one: **a
workload that is root in its own user namespace can install a seccomp filter without setting
`no_new_privs`**, because the second disjunct is satisfied. That is a property of the model worth
writing down; it does not affect the supervisor's filter, but it means the namespace hands the
workload a facility it did not have before.

### Both listener positions work, and the constraint is not where it was expected

| Arm | `RECV` | `ID_VALID` | `SEND` with `FLAG_CONTINUE` | `ADDFD` | path read from the target's memory |
|---|---|---|---|---|---|
| no namespace, listener outside (baseline) | ok | ok | ok | ok, new fd 6 in target | `/tmp/sc-marker-dir` |
| **workload in a namespace, listener outside (the chosen shape)** | ok | ok | ok | ok, new fd 7 in target | resolved |
| workload in a namespace, listener inside | ok | ok | ok | ok | resolved |
| listener inside, after `pivot_root` | ok | ok | ok | **`ENOENT`** | **`ENOENT`** |

`SECCOMP_USER_NOTIF_FLAG_CONTINUE` was verified by effect, not by return code: after the
continue, `getppid()` returned 1 with `errno` 0 and `mkdirat()` returned 0 in the baseline arm and
`EEXIST` on the repeat. SC-022's dependency is intact.

**So the design constraint you asked me to look for exists, but it is not "listener inside does not
work".** Listener inside works right up to the moment the workload calls `pivot_root`, at which
point `/proc` is no longer in the mount tree and every `ADDFD` and every `/proc/<pid>/mem` read
returns `ENOENT`. The listener is not blocked by a capability; it is blocked by having pivoted away
from the filesystem it needs. **Observed**, in the fourth arm above: `proc_present_after_pivot` was
`false` and both operations failed with errno 2.

**The constraint that should be written down is therefore about the mount tree, not about
privilege:** *the notification listener must hold a `/proc` that shows the notifying process, and a
process that has pivoted into a session root does not.* An in-tree listener could satisfy that by
mounting `proc` inside the session, which is a filesystem this repository has no reason to expose to
a workload. Keeping the listener outside is the right call — for a reason that is one layer down
from the one that motivated it.

## FR-048 — mounts

### What works, at uid 1000 with no capabilities at all

`unshare(CLONE_NEWUSER | CLONE_NEWNS)` followed by the whole of `enter()`'s sequence, replayed
step by step: `mount(/, MS_REC|MS_PRIVATE)`, the root `tmpfs` with `MS_NOSUID|MS_NODEV`, a
`MS_BIND|MS_REC` bind, the `MS_REMOUNT|MS_BIND|MS_RDONLY` remount, the
`nosuid|nodev|noexec` variant, `pivot_root`, and `umount2(MNT_DETACH)` of the old root. **Every
step returned `ok`.** That is the answer to the filesystem-type worry: `tmpfs` and `bind` are both
mountable in a user namespace, and the sequence needs nothing else.

One expectation did *not* hold, and it matters for a defence someone may be tempted to rely on:
**`MS_RDONLY` is not locked on a mount the namespace created itself.** Remounting the probe's own
read-only bind back to writable returned `ok`. Locked flags protect mounts *inherited* from the
parent namespace, not ones you make.

### The named change: `mode="rw"` under an inherited read-only mount

Binding Docker's read-only `/probe` and remounting it with `nosuid|nodev` only — the flag set
`enter()` uses for `mode="rw"` — returned **`EPERM`**, and the mount's options still read `ro`
afterwards. Outside a user namespace the same remount silently drops the read-only flag. So a
session that declares a writable location whose source lies under a read-only inherited mount
**fails at `enter()` under this model where it succeeds today**, and it fails with an errno that
says nothing about which declaration caused it.

This is a *correctness improvement* — a location declared writable that silently was not is worse
than a refusal — but it is a behaviour change with a diagnostics obligation attached, and it is the
change most likely to surface as a confusing CI failure.

### The authority gaps: not closed, and this is the finding's most consequential result

Finding 021 established two authority gaps and closed both with `setuid(65534)`. Re-measured inside
the user namespace, with a two-entry map (`0 100000 1` and `65534 100001 1`) and the workload
building the tree as in-namespace root:

| Gap | workload stays in-namespace root (`OD-24` as chosen) | workload drops to the second mapped uid |
|---|---|---|
| Write or `mkdir` at an undeclared path in the session root | **`ok` — gap open** | `EACCES` — closed |
| Write inside a submount under a `mode="ro"` location | **`ok` — gap open** | `EACCES` — closed |
| Control: write at the top of a `mode="ro"` location | `EROFS` | `EROFS` |

**Observed.** The reason is mechanical and should have been predictable: the session root `tmpfs` is
mounted *by* the workload at in-namespace uid 0, so in-namespace uid 0 owns it. Being root of a
namespace you built the filesystem in confers exactly the authority over that filesystem that being
root confers anywhere.

**The user namespace was chosen over a plain `setuid` drop, and on this evidence it is not a
substitute for one.** What it does buy is the *identity to drop to*: outside a namespace,
`setuid(65534)` makes the workload the host's `nobody`, shared with anything else on the box;
inside, the drop lands on a mapped kernel uid that belongs to this session alone. That is a real
gain over the plain drop. It is not the gain of not needing the drop.

## FR-049 — cgroups

### The pre-exec barrier survives, and `cgroup.kill` survives

Observed, container root, `--cgroupns=host`: the supervisor wrote the child's pid to
`cgroup.procs` while the child was held at the barrier, and the child read
`0::/f2a/session-probe` from its own `cgroup` file at release — attached before `execve`, across
the namespace boundary, unchanged. `cgroup.kill=1` against a session holding three members from a
distinct map returned `ok`, `cgroup.procs` went from three pids to empty, and all three reaped with
status 9.

### The named change: delegation needs an explicit `chown`, and the first measurement of it was wrong

**A warning about how easy this one is to get wrong, because this pass got it wrong first.** The
initial delegation probe ran the workload as container root with a `0 -> 0` map. Every write
succeeded, and none of those successes was about delegation: the workload's kernel uid was 0, the
cgroup files were owned by uid 0, and the writes went through on ordinary file permissions. **Any
delegation probe whose map is the identity map measures nothing.** The corrected probe maps
in-namespace 0 to kernel uid 100000 and has the workload call `setuid(0)` inside the namespace to
assume it.

With that correction, writing as in-namespace root at kernel uid 100000:

| Operation | no `chown` | after `chown` of the directory, `cgroup.procs`, `cgroup.subtree_control` and `cgroup.threads` |
|---|---|---|
| `mkdir` a child cgroup under the session | `EACCES` | `ok` |
| Write `cgroup.subtree_control` | `EACCES` | `ok` |
| Write the session's `memory.max` | `EACCES` | **`EACCES`** |
| Write the session's `pids.max` | `EACCES` | **`EACCES`** |
| Write the parent's `cgroup.procs` (escape) | `EACCES` | `EACCES` |
| Write the root's `cgroup.procs` (escape) | `EACCES` | `EACCES` |
| `mkdir` under the parent (escape) | `EACCES` | `EACCES` |

**The two rows in bold are the ones FR-049 needs and they behave correctly.** The bounds stay
supervisor-owned after delegation, because the documented delegation set does not include the
controller interface files — so the workload can organise its own subtree and cannot raise its own
limits. Every escape attempt is refused in both columns.

One row measured a limit this pass did not isolate: after the full `chown`, the workload still
could not write its own pid into a sub-cgroup it had just created (`EACCES`). The likely cause is
cgroup v2's requirement of write access to the common ancestor's `cgroup.procs` as well as the
destination's, but **the probe did not separate the candidate causes and this is inferred, not
observed.** It does not block FR-049, which attaches the workload once from outside.

## The reachability hazard, which was not on the brief's list

`CLONE_NEWUSER` changes who the workload is to the kernel's signal check, and the direction of that
change depends entirely on the map.

| Map | Workload `SIGKILL`s an out-of-namespace process | Workload reads its `/proc/<pid>/mem` |
|---|---|---|
| Self-map (`0 <own uid> 1`) — all an unprivileged supervisor can write | **succeeds, status 9** | `EACCES` |
| Distinct map (`0 100000 1`) — needs `CAP_SETUID` in the writer | `EPERM` | `EACCES` |
| Self-map plus `CLONE_NEWPID`, workload forked after the unshare | `ESRCH` | — |

**Observed.** The first row is the hazard: a self-mapped namespace gives the workload in-namespace
root whose kernel uid is the supervisor's own, and same-uid is all the signal check asks for. **The
workload can kill its own supervisor.** Today, without a namespace, it also can — both run as uid 0
— so this is not a regression; it is a gap the chosen model was assumed to close and does not.

`CLONE_NEWPID` closes it independently of the map, and the way it is added matters: `unshare` does
not move the caller into the new pid namespace, only its subsequent children. An earlier version of
this probe added the flag without the extra fork and the kill still landed, which reads exactly like
"the mitigation does not work". The workload must be forked after the unshare.

## Does the kernel floor move?

**No.** Nothing in this model needs a kernel newer than the existing derived floor of 5.14.

| Facility | Introduced | Basis |
|---|---|---|
| Unprivileged `unshare(CLONE_NEWUSER)`, `tmpfs` and `bind` mountable in a user namespace | well below 5.14 | read, not verified here |
| `/proc/<pid>/setgroups` and the `deny`-before-`gid_map` protocol | well below 5.14 | read, not verified here |
| `no_new_privs`-or-namespace-scoped `CAP_SYS_ADMIN` gate on filter install | present at v5.0, unchanged in substance through v6.12 | **read from source at six tags** |
| `SECCOMP_USER_NOTIF_FLAG_CONTINUE` | 5.5 | inherited from the existing floor derivation |
| `SECCOMP_IOCTL_NOTIF_ADDFD` | 5.9 | inherited from the existing floor derivation |
| `cgroup.kill` | 5.14 | inherited; this is what binds the floor |

`cgroup.kill` still binds, and the user-namespace requirement adds nothing above it. **The floor
stays 5.14 and stays DERIVED and NOT TESTED**; T205 is not made more urgent by this model, and it is
not made less so. One caveat belongs on the record: T205's own text names *"cgroup delegation
semantics"* and *"`pivot_root` in a user namespace"* as things that moved across the intervening
releases, and both are now on the critical path where before only one was. The floor does not move;
the value of testing it goes up.

## Preflight and CI under this model

Do not read the table as a change list — `preflight.py` was not edited and nothing here has been
implemented.

| Check | Under this model |
|---|---|
| `platform` | **Unchanged.** Asks whether this is Linux; the answer does not depend on privilege |
| `kernel_version` | **Unchanged**, floor and provenance string included. See above |
| `cgroup_v2` | **Unchanged.** Reads `cgroup.controllers`, which is world-readable |
| `cgroup_delegation` | **Changes shape, and is the only check that still needs elevation.** Creating a child cgroup under the root needs write access to a root-owned directory. It should also grow a second assertion — that the supervisor can `chown` the delegation set to the mapped uid — because that is the operation the model adds and it is the one that will fail on a host where the supervisor is not root |
| `cgroup_kill` | **Unchanged in intent, inherits `cgroup_delegation`'s privilege**, since it probes by creating a child cgroup |
| `namespaces` | **Becomes load-bearing rather than advisory, and needs a third assertion.** It reads `max_user_namespaces` today. Under this model it should additionally attempt an actual `unshare(CLONE_NEWUSER)` in a forked child, because a distribution can permit the namespace and still refuse it by LSM or by `sysctl`, and it should check that the supervisor holds `CAP_SETUID` — the capability the multi-line map needs |
| `seccomp_user_notification` | **Unchanged and correct as written.** It probes `SECCOMP_GET_NOTIF_SIZES`, which needs no privilege and no filter install. The source read above says the facility's availability does not depend on the caller's capabilities |

**What `sudo -E` becomes.** The two seccomp and mount jobs no longer need it: every FR-048 result in
this document — mount and seccomp both — was taken at uid 1000 with `--cap-drop=ALL`. The cgroup work still
does, for the same reason the CI comment already gives — the cgroup root is root-owned. So the
honest end state is **a split, not a removal**: the mount and seccomp batteries run unprivileged and
are stronger for it, because running them as root asserts a capability the supervisor will not have;
the cgroup battery keeps `sudo -E`; and `preflight` keeps it too, because `cgroup_delegation` is one
of its seven.

**Running the mount and seccomp tests unprivileged is not a cost-free simplification.** Under
`sudo -E` those tests currently exercise a path this model will not use. Moving them to unprivileged
changes what they prove, and the removal proofs behind them were written against the privileged
path.

## Cost

Sized the way `tasks.md` sizes its rows: per task, from task shape, each anchored to a result above.

| task | days | derivation |
|---|---|---|
| Mount tree under `CLONE_NEWUSER`, plus the locked-flag diagnostic | 1–2 | The sequence ran unmodified at uid 1000 with no capabilities, so the mechanism is free. The work is the `EPERM` from the `mode="rw"` remount under an inherited read-only mount, which needs a diagnostic naming the declaration rather than an errno |
| uid/gid map plumbing and the `CAP_SETUID` decision | 3–4 | **The largest row, and it is a design decision before it is code.** A multi-line map is mandatory — a single-entry map has no uid to drop to and makes the workload the supervisor's own kernel uid — and writing one needs `CAP_SETUID`. That means choosing between a supervisor that holds it, a `newuidmap` helper, and a subuid allocation scheme, then the `setgroups`-`deny`-first protocol and the child barrier that keeps the parent from writing the map before the namespace exists. Two of this pass's probes were invalid on ordering alone |
| `CLONE_NEWPID` and the post-unshare fork | 2–3 | The flag is one constant; the fork placement is the whole task, and getting it wrong produces a mitigation that silently does not mitigate. Carries a `/proc` remount inside the session, because a workload in a new pid namespace looking at the host's `/proc` still sees processes it cannot signal |
| cgroup delegation `chown` set | 2–3 | Measured small: four paths, and the bounds correctly stay unwritable. Costed above one day because the failure mode is a probe that passes for the wrong reason, so the test needs a distinct map and a negative arm proving the un-`chown`ed case refuses |
| FR-048 listener-position constraint written down and tested | 1–2 | The mechanism needs no change. The work is the `pivot_root`-versus-`/proc` constraint recorded as a constraint, with a test that fails if a future change moves the listener inside |
| Preflight reshape | 2–3 | Two checks grow assertions, one of which is a real `unshare` in a forked child; five are unchanged. Each new assertion needs a removal proof |
| CI posture split | 2–3 | Mount and seccomp batteries move off `sudo -E`, cgroup and `preflight` keep it. The residue is the removal proofs written against the privileged path |
| | **13–20** | low 1+3+2+2+1+2+2; high 2+4+3+3+2+3+3 |

**No band on this row, and one caveat instead.** Every mechanism here was measured rather than
assumed, so there is no probe outstanding that could move the figure. The caveat is that the whole
estimate is for the model *as corrected below*. Sizing "root inside, unprivileged outside" as
worded is not possible, because it does not resolve.

## The verdict: not buildable as worded, and the nearest variant

**As worded — root inside the namespace, the supervisor unprivileged outside — the model is not
buildable.** Not because a mechanism refuses, but because "unprivileged outside" and the properties
the model was chosen for are in direct contradiction. An unprivileged supervisor can write only a
single-entry self-map, and a single-entry self-map:

- has no second uid, so finding 021's closure is unavailable (`setuid(65534)` → `EINVAL`, observed);
- makes in-namespace root the supervisor's own kernel uid, so the workload can `SIGKILL` the
  supervisor (observed);
- cannot `chown` the cgroup delegation set to a uid the supervisor does not own, so FR-049's
  delegation cannot be established (inferred from the `chown`-versus-no-`chown` measurement, which
  was taken with a writer that did have the capability).

**The nearest buildable variant, which keeps everything the choice was made for:**

> The **workload** is root inside a user namespace and unprivileged outside it, mapped to a
> **dedicated kernel uid range that is not the supervisor's**, in a **pid namespace of its own**,
> and it **drops to a second mapped uid** after the mount tree is built. The **supervisor** holds
> `CAP_SETUID` and `CAP_SETGID` long enough to write the map — or delegates that to a `newuidmap`
> helper — and holds enough authority over the cgroup root to `chown` the delegation set.

Three differences from the wording, and none is a retreat from it:

1. **"Unprivileged" describes the workload, not the supervisor.** The property that mattered — a
   workload with no authority on the host — is fully delivered. What is not delivered is a
   supervisor that needs nothing, and nothing in the three mechanisms ever offered that:
   ~~FR-049's enforced-from-outside clause already requires a supervisor that can write the cgroup
   root.~~ **writing the multi-line uid map requires `CAP_SETUID` in the writer — `EPERM` from a
   uid-1000 writer, `ok` from a writer holding it, both observed above — and a single-entry
   self-map has no second uid to `setuid` to (`EINVAL`, observed). The map, not the cgroup, is what
   makes an unprivileged supervisor unbuildable.**

   > #### ⚠️ CORRECTED 2026-08-04 — the conclusion stands, on a different and stronger limb than the one this sentence gave
   >
   > **The struck clause read a requirement as saying something it does not say.** FR-049 requires
   > processor and memory bounds *"enforced from outside the environment so that nothing running
   > inside it … can raise, extend or evade them"*, and its 2026-08-03 pre-exec-barrier extension
   > requires the session cgroup created and every bound written before the workload process is
   > created. Both clauses constrain **where** enforcement sits and **when** it must hold. **Neither
   > says what authority the enforcer holds.** The base clause names no mechanism at all — not a
   > cgroup, not a supervisor — and the extension names a cgroup without naming its owner. An
   > operator who delegates a cgroup subtree to the supervisor by unit file satisfies every clause
   > with a supervisor holding no capability whatever.
   >
   > **The contradiction is real, but three inferential steps were presented as one textual one.**
   > Reaching it needs FR-049's text, *plus* feature 002's own choice of a cgroup **owned** by the
   > supervisor, *plus* the host fact that creating one under a root-owned root needs elevation.
   > Only the first of the three is a requirement; the second is a design decision this feature took
   > and the third is a property of this host. Written as *"already requires"*, the sentence
   > attributes to the specification a constraint the specification never imposed.
   >
   > **This is an argument error and not a measurement error, and the distinction is the reason the
   > verdict survives intact.** The decisive fact was measured by this pass, in this document, and
   > then not used: the uid-map results — `EPERM` for a multi-line map from an unprivileged writer,
   > `ok` from one holding `CAP_SETUID`, `EINVAL` for `setuid(65534)` under a single-entry self-map —
   > are first-hand observations that carry the verdict on their own, with no requirement cited and
   > no delegation route left unexamined. The instrument was sound and the inference drawn beside it
   > was not, so what needed correcting is the reasoning and not a result.
   >
   > **The document already contradicted itself on this point.** *What this changes downstream*
   > below states the corrected reading in terms — *"FR-049's enforced-from-outside clause is
   > satisfied under delegation"* — which is incompatible with the struck sentence and was written
   > on the same pass. **OD-24** now records the corrected attribution, in the same terms: the
   > cgroup limb is a tension, the map limb is the flat contradiction.
   >
   > **Nothing else in this document moves.** The verdict, the cost table and the corrected model
   > are unchanged, and the third bullet of the verdict list above — which reaches the cgroup
   > delegation limb and labels it `inferred` — was already correctly ranked below the two observed
   > uid-map limbs it follows.
2. **The `setuid` drop stays.** The namespace was chosen over a plain drop; on this evidence it is
   a *complement* to one, not a replacement. It changes the drop from "become the host's shared
   `nobody`" to "become a kernel uid belonging to this session", which is strictly better, and it
   is the reason to prefer this over the plain drop the owner ruled out — just not the reason
   given.
3. **`CLONE_NEWPID` is not optional.** It was not in the wording and it is the only measured
   mitigation that holds regardless of the map.

**If the supervisor genuinely cannot hold `CAP_SETUID`** — a constraint no document in this
repository currently states — then the fallback is the plain `setuid(65534)` drop from finding 021
with no namespace, which closes both authority gaps and needs nothing. It gives up per-session uid
isolation and gives up the mount-tree control the namespace provides. That is a real loss, and it is
the price of the unprivileged-supervisor constraint, not of the namespace.

> **Dated note, 2026-08-08 — a document now states the constraint, and it states it the other way.**
> [`plan.md`](../../001-discovery-validation/plan.md)'s **OD-29** records that the supervisor **may**
> hold `CAP_SETUID` and `CAP_SETGID` in the initial user namespace, so the antecedent above is one the
> owner has decided against: the product is willing to require the two-bit grant. **The paragraph is
> left as written**, because it is what makes the fallback legible and OD-29 keeps the fallback rather
> than deleting it — it remains the named route for an operator who will not make the grant, at exactly
> the price this paragraph states. What is no longer accurate is the *implication* that nothing in the
> corpus has an opinion; the opinion now exists and is "yes".

## Where the decision is recorded, and why this pass did not write it

**The register is `specs/001-discovery-validation/plan.md`**, under the heading
**`## Owner decisions recorded during execution`**, and it holds the whole sequence OD-01 through
OD-23 for both features. It is not a table. Each decision is a prose section:

> **Dated note, 2026-08-04 — the observation above is left standing and is no longer current.** The
> register ran to OD-23 when this pass read it; it now runs to **OD-25**, extended the same day by
> OD-24 (this document's own subject) and OD-25. The sentence is not amended because it records what
> a dated pass observed, and the count it gives was correct when taken.



```markdown
### OD-NN — <the decision, stated as a sentence, with any later revision struck inline>

**Decided <date>**, answering <what question, and where it was put>.

**The decision.** <what was chosen>

**Why <the alternative> was not taken.** <...>
```

A revision keeps the row and strikes the superseded text — `OD-23`'s heading carries both its
original and revised forms, with a `> #### ⚠️ REVISED` block above the original explaining that it
is *"revised, not wrong"*. `specs/002-spec-aware-agent-runtime/plan.md` carries only a citation
line, not the definitions.

**The file is untouched in `git status`, so this pass could have written the entry, and chose not
to, for two reasons.** First, the evidence above changes what the entry should say: an entry reading
"unprivileged user namespace, root inside, unprivileged outside" would record a decision that does
not resolve, and would need revising the day it was written. Second, the register's own precedent is
that recording an owner decision is an owner act — the note under OD-21 says recording it *"required
owner authority rather than a propagation pass"*.

**One mechanical warning for whoever does write it.** The corpus checker resolves `OD-NN` against
this register, so *any* document containing the bare token before the register entry exists is a
hard `identifier-resolution` **error**, not a warning. This was confirmed by writing a scratch file
containing the bare token and running the checker: it errored, and the same token inside a code span
did not. That is why every occurrence in this document is in a code span. **Write the register entry
first, then the citations.**

## What remains unverified, and where the host is not the target

- **aarch64 only.** Every probe ran on `6.12.76-linuxkit`, aarch64. Finding 021 declined to quote an
  x86_64 measurement because `qemu-user` reported `openat2` as `ENOSYS`, and the same restraint
  applies: **no result here is an x86_64 measurement.** The seccomp gate is architecture-independent
  in the source read, which is a source claim and not a measurement.
- **This host is macOS.** The privileged pytest suite is deselected locally and was not run. Nothing
  above came from `pytest`; all of it came from containers and from reading kernel source.
- **One kernel.** Six source tags were read; one kernel was executed. Nothing here is evidence about
  5.14, 5.15, 6.1 or 6.6 — the kernels T205 would cover.
- **Docker's namespace posture is not a host's.** The unprivileged probes ran inside a container
  that already permits user namespaces. A host with `kernel.unprivileged_userns_clone=0`, or an
  AppArmor profile restricting `userns`, refuses `unshare(CLONE_NEWUSER)` outright, and neither was
  reproduced here. This is the strongest argument for the `namespaces` preflight check attempting a
  real `unshare` rather than reading a `sysctl`.
- **The `chown`-less delegation arm proves refusal, not the converse.** It shows that without the
  `chown` everything is `EACCES`. It does not show that a supervisor lacking `CAP_CHOWN` cannot
  arrange delegation some other way; no such route was looked for.
- **No `SECCOMP_ADDFD_FLAG_SETFD` collision test.** `ADDFD` and `ADDFD_FLAG_SEND` were exercised and
  the returned fd number was checked against the target's `/proc/<pid>/fd`. Injecting onto an
  occupied descriptor was not tested.
- **The sub-cgroup `cgroup.procs` refusal is uncaused.** Recorded above as inferred.

## Reproduction

The probes are standalone and were written to `/tmp/f2a-od24/`; they are not committed, in keeping
with finding 021, and each prints its own posture as part of its output. The container shapes:

```bash
# FR-048, both halves (mount and seccomp): the unprivileged posture.
# No --privileged, no capabilities.
docker run --rm --user 1000:1000 --cap-drop=ALL --security-opt seccomp=unconfined \
  -v /tmp/f2a-od24:/probe:ro python:3.12-slim python3 -u /probe/p1_mounts.py

# FR-049 and anything needing a multi-line map: container root, for CAP_SETUID
# and a writable cgroupfs. Still not --privileged.
docker run --rm --cgroupns=host -v /sys/fs/cgroup:/sys/fs/cgroup:rw \
  --security-opt seccomp=unconfined -v /tmp/f2a-od24:/probe:ro \
  python:3.12-slim python3 -u /probe/p4b_delegation.py

# The source read behind the seccomp answer.
for v in v5.0 v5.4 v5.5 v5.9 v5.14 v6.12; do
  curl -sS "https://raw.githubusercontent.com/torvalds/linux/$v/kernel/seccomp.c" \
    | rg -n "CAP_SYS_ADMIN"
done
```

`--security-opt seccomp=unconfined` is present because Docker's default profile blocks `unshare`
with `CLONE_NEWUSER`. **That is a real deployment constraint and not a probe artefact**: a
supervisor running inside a container under a default seccomp profile cannot create a user
namespace at all. It is not `--privileged` and grants no capabilities; it removes one filter.

## What this changes downstream, stated for the documents this pass may not edit

Nothing here was applied. Four places carry statements this finding bears on:

- **`filesystem-decision.md`** still says a location outside the declared set is *absent*. Finding
  021 falsified that; this document shows the user namespace does not repair it. The repair is the
  drop, or `MS_RDONLY` on the root `tmpfs`, or `MS_REC` on the read-only remount.
- **FR-048 and SC-022** are unaffected in substance and gain a constraint: the listener must retain
  a `/proc` that shows the notifying process.
- **FR-049's** enforced-from-outside clause is satisfied under delegation, and the delegation set is
  now a named list of four paths rather than an unstated one.
- **T205** does not become more urgent, and two of the three things its own text names as having
  moved across releases are now both on the critical path.
