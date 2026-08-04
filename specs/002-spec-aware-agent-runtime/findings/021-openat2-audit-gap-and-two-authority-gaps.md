# Finding 021 — `openat2` is an audit gap and not an authority gap, and the search for it found two authority gaps that are not syscall-shaped

**Date**: 2026-08-04
**Feature**: 002. Measures a mechanism this repository shipped —
[`src/supervisor/mounts.py`](../../../src/supervisor/mounts.py),
[`src/supervisor/seccomp.py`](../../../src/supervisor/seccomp.py) and
[`src/supervisor/fs_decisions.py`](../../../src/supervisor/fs_decisions.py) — against the kernel it
runs on.
**User Story**: US1, by way of FR-048 and SC-022.
**Owner decision**: **none is taken here, and none should be read out of this document.** The owner
asked for the question settled before a code decision. No enforcement behaviour was changed, no
syscall was added to any watch set, path map or flags map, and no source file outside this directory
was edited. The three options are costed at the end without a recommendation.
**Model spend**: **$0.0000.** No model was called and no credential was read. Six containers were
run locally; no network request was made beyond pulling two public Python images.
**Method**: source read first, then six probes inside Linux containers on the local Docker host —
four against the kernel directly, two importing `src/supervisor` unmodified from a read-only bind of
the working tree. Every claim below is labelled observed, inferred or unverified, and the three are
not blended. The limits of the host are in
[What remains unverified](#what-remains-unverified-and-where-the-host-is-not-the-target).

Numbering note: `020` was the high-water mark across both namespaces, checked by ripgrep over the
whole tree before this file was created. `021` was free.

---

> ## Read this first: the thing I was sent to check is the least serious thing I found
>
> `openat2` is an **audit gap**. It is refused exactly as `openat` is refused, by the mount, and the
> refusal is simply not written down. That is the owner's hypothesis and it survived every attempt to
> break it.
>
> Two other things did not survive, and both are **authority gaps** — places where a write *succeeds*
> inside a session:
>
> 1. **The empty root is writable.** `mounts.enter()` mounts the session's root `tmpfs` with
>    `MS_NOSUID | MS_NODEV` and **not** `MS_RDONLY`. A workload can create files and directories at
>    undeclared paths in it. Observed against the real `mounts.enter()`: after the probe ran, the
>    session root listed `decl`, `undeclared-dir`, `undeclared.txt` and `undeclared2.txt`, of which
>    only `decl` was declared.
> 2. **A read-only declared location is only read-only at its top mount.** The bind is
>    `MS_BIND | MS_REC`; the remount that actually applies `MS_RDONLY` carries no `MS_REC`. Any
>    submount inside a declared source therefore stays writable. Observed: a write to a file inside a
>    submount under a location declared `mode="ro"` returned `OK` through both `openat` and `openat2`,
>    while the same write one directory up returned `EROFS`.
>
> **Both are conditional on the workload running as uid 0, and today it does**, because nothing in
> `src/` drops privileges and `enter()` needs `CAP_SYS_ADMIN` to run at all. Re-running the identical
> probe after `setuid(65534)` turned every one of those successes into `EACCES`. That conditionality
> is the finding's most useful part and is why this is stated as a measured hazard rather than as an
> exploit.
>
> Neither of these is about `openat2`, neither is mentioned in
> [`filesystem-decision.md`](../contracts/filesystem-decision.md), and both
> falsify one sentence that document and two source files rely on: *"a location outside the set is
> **absent**, not permission-denied, so there is nothing at it to open."* A workload that can create
> a file at an undeclared path can put something there to open.

## The direct answer

**Audit gap.** For every write mode tested, on a read-only mount built the way the supervisor builds
one, `openat2` and `openat` return the identical errno. `openat2` buys a workload nothing the mount
does not already refuse. What it buys is silence: the attempt produces no `filesystem_decision`
record at all, so SC-022's attempt count is incomplete by exactly the `openat2` attempts made.

The two qualifications the owner asked me to look for, answered directly:

- **`openat2` is not intercepted at all.** It is not merely unmapped for flags; it is absent from
  the watch set, so the seccomp filter never traps it. There is no fail-open-versus-fail-closed
  disposition to read, because no code path runs. This is what
  [`filesystem-decision.md`](../contracts/filesystem-decision.md) already says, and the
  measurement confirms it rather than correcting it.
- **The resolution flags change nothing about the write outcome.** `RESOLVE_IN_ROOT`,
  `RESOLVE_NO_SYMLINKS` and `RESOLVE_CACHED` all returned `EROFS` against a read-only mount, exactly
  as the flagless call did. `RESOLVE_NO_XDEV` returned `EXDEV`, which is *more* restrictive: it
  refuses to cross a mount boundary. None of them is a way past the mount, and the TOCTOU discussion
  in `read_target_path` is untouched by them because no `openat2` argument is ever read.

## What was observed

Host for every run: Docker server `29.4.1`, kernel `6.12.76-linuxkit`, `aarch64`, container uid 0.

### `openat2` is syscall 437 on this architecture, established two ways

The brief said to verify rather than trust the number. `/usr/include/asm-generic/unistd.h` in a
Debian `arm64` image defines `__NR_openat2 437`. Behaviourally, syscall 437 on this kernel shows the
error semantics that belong to `openat2` and to nothing else:

| Call through syscall 437 | Result | Why it identifies `openat2` |
|---|---|---|
| open an existing file, `open_how` of 24 bytes | fd returned | it opens |
| same, `size` argument of 0 | `EINVAL` | `openat2` validates the struct size; `openat` has no size argument |
| same, `size` argument of 8 | `EINVAL` | a short `open_how` is rejected |
| `RESOLVE_BENEATH` with an absolute path | `EXDEV` | a resolve-flag semantic with no analogue anywhere else |
| an undefined `resolve` bit | `EINVAL` | `openat2` rejects unknown bits rather than ignoring them |
| an undefined open flag | `EINVAL` | `openat` silently ignores unknown flags; `openat2` does not |

### `openat2` against a read-only mount, compared with `openat`

A bind mount then remounted `MS_REMOUNT | MS_BIND | MS_RDONLY`, which is the two-step
`mounts.enter()` performs. Both syscalls issued raw through `syscall()`, so this compares two
syscalls and not two libc wrappers.

| Attempt | `openat` | `openat2` |
|---|---|---|
| `O_RDONLY` | fd returned | fd returned |
| `O_WRONLY` | `EROFS` | `EROFS` |
| `O_RDWR` | `EROFS` | `EROFS` |
| `O_RDONLY \| O_TRUNC` | `EROFS` | `EROFS` |
| `O_CREAT \| O_WRONLY`, new file | `EROFS` | `EROFS` |
| `O_WRONLY` with `RESOLVE_NO_SYMLINKS` | not applicable | `EROFS` |
| `O_WRONLY` with `RESOLVE_IN_ROOT` | not applicable | `EROFS` |
| `O_WRONLY` with `RESOLVE_CACHED` | not applicable | `EROFS` |
| `O_WRONLY` with `RESOLVE_NO_XDEV` | not applicable | `EXDEV` |

**No divergence in any write mode.** The same comparison repeated inside the real
`mounts.run_in_namespace()` gave the same answer: `EROFS` from both, at the top of a location
declared `mode="ro"`.

One row here was originally an `EINVAL` and it was the probe's own defect, recorded because it is a
trap for anyone repeating this work: **`openat2` rejects a nonzero `mode` when `O_CREAT` is not
set**, where `openat` ignores it. Passing `0o644` unconditionally produces an `EINVAL` that looks
exactly like a kernel difference between the two syscalls and is not one.

### What the supervisor's own listener records

`src/supervisor` was imported unmodified. The watch set the shipped code produces on this
architecture has twelve entries — `chdir`, `faccessat`, `faccessat2`, `fchmodat`, `mkdirat`,
`newfstatat`, `openat`, `readlinkat`, `renameat2`, `statx`, `truncate`, `unlinkat` — and the BPF
program built from it compares against twelve syscall numbers, none of which is 437.

A child was then run under the real listener issuing one raw `openat` and one raw `openat2` at
marker paths inside a declared read-only location:

| Watch set | Notifications total | Records for the marker paths |
|---|---|---|
| as shipped | 353 | one, for `openat`: `deny`, `FS-002`, `write_to_readonly_location` |
| as shipped plus `openat2` | 354 | two, for `openat` and for `openat2` |

The counterfactual arm passed `openat2` through the `syscalls=` parameter the API already exposes;
no source file was edited to produce it. **Adding `openat2` to the watch set produced exactly one
additional notification**, which is the arithmetic confirmation that the shipped filter is silent on
it rather than trapping it and discarding it somewhere later.

### Whether `openat2` reaches FS-006

**It does not, and it would not even if it were watched.** This is a stronger answer than the source
alone suggests and it came out of the counterfactual arm.

`decide()` tests `path is None` **before** it tests the open-family flags case. `openat2` has no
entry in `_PATH_ARG`, so the listener builds an `Attempt` with `path=None`, and the classifier
returns **FS-005 `path_unreadable_at_notification`** — not FS-006. Observed directly in the
counterfactual arm:

| Syscall | `path` | `flags` | `rule_id` | `reason` |
|---|---|---|---|---|
| `openat` | `/f2a/marker/via-openat.txt` | 1 | `FS-002` | `write_to_readonly_location` |
| `openat2` | `null` | `null` | `FS-005` | `path_unreadable_at_notification` |

So there are two independent barriers between `openat2` and FS-006, not one. FS-006 becomes
reachable for `openat2` only if it is added to the watch set **and** to `_PATH_ARG` **and** left out
of `_FLAGS_ARG`. Called directly with a readable path and no flags, the classifier does return
FS-006 — so the rule works; it is the wiring that never delivers that shape.

This matters for costing option two below: an implementer who adds `openat2` to the watch set
expecting FS-006 would silently get FS-005, which says *the path could not be read* about a syscall
whose path was never looked for.

### Whether every declared read-only location is backed by a read-only mount

**This is the crux question and the answer is no.** Two location classes are not.

**The session root itself.** `enter()` mounts it as `tmpfs` with `MS_NOSUID | MS_NODEV` and no
`MS_RDONLY`. It is not a declared location and has no `mode`, so no classifier rule governs it
either — for anything created there, the classifier is not even a weak authority, it is a recorder
that will call the attempt FS-001 while the kernel completes it. Observed inside the real namespace,
as uid 0: `openat` with `O_CREAT` returned `OK`, `openat2` with `O_CREAT` returned `OK`, and `mkdir`
succeeded. The root listing went from one entry to four.

**Any submount inside a declared read-only source.** The bind carries `MS_REC`, the read-only
remount does not, and `MS_REMOUNT | MS_BIND` applies to one mount rather than to a tree. Observed,
with one location declared `mode="ro"`:

| Path, relative to the declared read-only location | `openat` `O_WRONLY` | `openat2` `O_WRONLY` |
|---|---|---|
| a file at the top of it | `EROFS` | `EROFS` |
| a file inside a submount under it | `OK` | `OK` |
| a new file inside that submount, `O_CREAT` | `OK` | `OK` |

The replica probe read `/proc/self/mountinfo` and shows the mechanism plainly: the outer mount
carries `ro` and the inner one carries `rw`. Whether this reaches production depends on whether any
declared source contains a submount, which this finding does not establish and cannot — it is a
property of the deployment's host tree, not of the code.

**Both close under an unprivileged uid.** Re-running the identical in-namespace probe after
`setgroups([]); setgid(65534); setuid(65534)` returned `EACCES` for every one of those writes and
left the root listing unchanged. Nothing in `src/` performs that drop; `CLONE_NEWUSER` is defined in
`_linux.py` and never used, and `enter()` unshares only `CLONE_NEWNS`.

### Audit completeness beyond `openat2`

`openat2` is one of twelve, not one of one. Against a list of thirty-three write-capable path-taking
syscalls, on this kernel and this architecture, eighteen are wired, **six are watched, and twelve are
wired and unwatched**: `openat2`, `renameat`, `mknodat`, `linkat`, `symlinkat`, `fchmodat2`,
`fchownat`, `utimensat`, `setxattr`, `lsetxattr`, `removexattr`, `lremovexattr`.

**And unlike `openat2`, four of them are reached by ordinary library calls.** A child under the real
listener made ten unremarkable writes inside a declared read-only location. Six produced a
`filesystem_decision`; four produced nothing at all:

| Call | Syscall the listener saw | Recorded |
|---|---|---|
| `os.rename` | none | **no** |
| `os.symlink` | none | **no** |
| `os.link` | none | **no** |
| `os.utime` | none | **no** |
| `os.chmod` | `fchmodat` | yes — `FS-002` |
| `os.mkdir` | `mkdirat` | yes — `FS-002` |
| `os.rmdir` | `unlinkat` | yes — `FS-002` |
| `os.unlink` | `unlinkat` | yes — `FS-002` |
| `os.truncate` | `truncate` | yes — `FS-002` |
| `open(path, "w")` | `openat` | yes — `FS-002` |

`os.rename` is the one worth pausing on: `renameat2` **is** watched, and glibc on this architecture
issued `renameat`, which is not. The watch set contains the newer syscall and misses the one the
platform's own C library actually calls.

## What is inferred

Marked separately because none of it was directly observed.

- **The mount namespace, not the classifier, is the authority for every location backed by a
  read-only mount.** The identical errno from two syscalls of which only one is intercepted admits
  no other reading: the refusing mechanism cannot be the one that saw only one of them.
- **`openat2`'s effect on SC-022 is an undercount and not a miscount.** No wrong record is produced;
  a record is absent. This follows from the filter never trapping the syscall, and is weaker than an
  observation only in that I did not enumerate every downstream consumer of the sink.
- **The twelve unwatched write syscalls are audit gaps wherever the target is a read-only mount, and
  authority gaps wherever it is not.** They inherit the classification of the location, not of the
  syscall. That is a deduction from the two mechanisms being independent, which the `openat2` result
  establishes.
- **Adding `openat2` to `_PATH_ARG` would carry the same TOCTOU the path read already documents, and
  reading `open_how` would carry a worse one.** The contract's reasoning here is sound and I did not
  find a way around it: the path pointer is re-resolved by the kernel after `CONTINUE`, and so would
  the `open_how` struct be.

## What remains unverified, and where the host is not the target

- **One architecture, one kernel.** Everything empirical is `aarch64` on `6.12.76-linuxkit`. I ran
  the static half of the completeness probe under emulated `linux/amd64` and **its liveness column is
  not trustworthy**: `openat2` reported `ENOSYS` and three probes segfaulted, both of which are
  artifacts of `qemu-user` rather than facts about an x86_64 kernel. What is architecture-independent
  and certain from source is that neither `openat2` nor `creat` appears in
  `_SYSCALL_NUMBERS["x86_64"]` or in the name tuple `path_taking_syscalls()` filters, so both are
  unwatched on x86_64 too — but the x86_64 *counts* in this document are not measurements and are not
  quoted as any.
- **A linuxkit kernel is not a production kernel.** `MS_REMOUNT | MS_BIND` semantics, and whether a
  read-only remount can be undone, have both moved within the 5.x and 6.x series. The direction of
  the submount result is a documented property of `MS_REMOUNT` rather than a quirk, but I did not run
  it anywhere else.
- **Overlayfs underneath.** The bind mounts in the replica probes sit on Docker's overlay filesystem.
  The in-namespace probes using the real `mounts.enter()` did too. A production deployment on ext4 or
  xfs was not tested, and `EROFS` is a VFS-level answer that should not depend on it — should, not
  shown.
- **Whether any production declared source contains a submount.** Not knowable from this repository.
  Nothing in `LocationSet` can express or detect it.
- **Whether the sink's consumers behave differently on a missing record.** I measured what reaches
  `DecisionSink`, not what the storage tier does with it.
- **Concurrency.** Every probe was single-threaded. The TOCTOU that `read_target_path` documents was
  not exercised and no claim here bears on it.
- **`RESOLVE_BENEATH` and `RESOLVE_IN_ROOT` as a containment tool.** I tested that they do not defeat
  a read-only mount. I did not test whether they would be *useful* to the supervisor, which is a
  different question and a live one.

## What the three options cost, given the above

Stated as tradeoffs. The owner decides.

**Leave unwatched and documented.** Cost is now precisely known and it is not zero: SC-022
undercounts by the `openat2` attempts made, and the same is already true of eleven other syscalls,
four of which ordinary code reaches without trying. The honest version of this option is not
"document `openat2`" but "document that the watch set is a named subset and state the subset" —
because a reader of the current contract would reasonably infer that `openat2` is the exception.
Cheapest in code, and it leaves the largest gap between what SC-022 claims and what it measures.

**Deny `openat2` outright.** Note first that this is *not* the same shape as the other two options:
it changes enforcement, and the listener currently does not enforce anything. Answering
`SECCOMP_RET_ERRNO` for `openat2` would make the supervisor an enforcement point for one syscall and
a recorder for the rest, which is a division that has to be explained to every future reader of
`seccomp.py`. Against that, it is genuinely safe against the TOCTOU, because refusing needs no
argument read. The compatibility cost is real but small today: glibc does not route ordinary opens
through `openat2`, so what breaks is code that calls it deliberately, which for a read-only v1 is
approximately nothing. **The trap to avoid is doing this by adding `openat2` to the watch set and
expecting FS-006** — measured above, that yields FS-005 and a record that says the path was
unreadable when it was never read.

**Read `open_how` from target memory.** Buys a correct flag word and a correct path, and pays the
TOCTOU on a value the classifier acts on rather than only records — the contract's objection, which I
could not defeat. It is worth adding that this option is *only* worth its cost if the classifier is
the authority for something, and for every location backed by a read-only mount it is not. The
places where the classifier's answer would actually matter are the two authority gaps in the box at
the top, and both of those are fixed by a mount flag or a `setuid` rather than by a better read.

**A fourth thing is worth costing beside these three, because it is cheaper than all of them.**
`MS_RDONLY` on the root `tmpfs`, `MS_REC` on the read-only remount, and a privilege drop before the
workload runs would close both authority gaps, and none of the three touches the classifier or the
listener. They are not `openat2` fixes and they are not free — a read-only session root may break
workloads that expect a writable `/tmp`, which is a declared-location question — but the owner should
see them on the same page as the three above rather than in a separate conversation.

## Reproduction

Six probes, all offline apart from two public image pulls, all `$0.0000`. The scripts live in
`/tmp/f2a-openat2/` on the host they were run on and are not committed — nothing was written into the
repository outside this file. Each is reproducible from the description above; the two that import
the supervisor are the ones worth reconstructing, and both take the same shape:

```sh
docker run --rm --privileged \
  -v /path/to/scripts:/probe:ro \
  -v /path/to/function2agent:/repo:ro \
  python:3.12-slim python3 -u /probe/probeN.py
```

with `sys.path.insert(0, "/repo")` and no other change to the tree. The two supervisor probes use
`seccomp.spawn_with_listener(argv, on_attempt, syscalls)` and
`mounts.run_in_namespace(mounts.plan(...), body)` as they ship; the counterfactual arm supplies its
extra syscall through the existing `syscalls=` parameter rather than by editing `_linux.py`.

Two cautions for anyone repeating this, both of which cost a run here:

- **Do not build a syscall-number table by concatenating several `unistd.h` headers.** On `aarch64`
  that pulled in x86_64 numbers, under which 94 reads as `lchown` and is `exit_group`. The probe
  called it and exited 255 with no output. Use the one header the architecture owns, and run each
  liveness probe in a forked child so a wrong number kills the child and is reported.
- **`openat2` rejects a nonzero `mode` without `O_CREAT`.** See the note under the read-only mount
  table; it produces a false difference between the two syscalls.
