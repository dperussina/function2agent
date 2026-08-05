# Finding 028 — OD-24's deferral survives, but only one of its two stated grounds does: the first is untouched, the second is *spent* rather than falsified, and the `newuidmap` route the decision offers as its least-authority option is measured here for the first time and is the **most**-authority option of the three

**Date**: 2026-08-05
**Feature**: 002. Re-examines the deferral recorded at
[`plan.md`](../../001-discovery-validation/plan.md)'s **OD-24**, the owner decision governing the
user-namespace privilege model for
[`src/supervisor/`](../../../src/supervisor/)'s mount, cgroup and seccomp modules, against the
artifacts and against the kernel. **Reports; decides nothing.**
**User Story**: US1, by way of FR-048, FR-049 and FR-050.
**Owner decision**: **none is minted here and the register was not edited.** The question this pass
answers is whether an existing entry's grounds still hold, which is a reporting act; changing the
entry is the owner's. Where a new decision would be needed it is described in
[§8](#8-what-this-asks-the-owner-to-decide) as a decision needing taking, with no number attached —
on [finding 026](./026-pivot-root-check-measured.md)'s rule that a number copied into a finding goes
stale in the direction that tells the next author to reuse a taken one.
**Model spend**: **$0.0000.** No model was called and no credential was read. Five container arms
were run locally, plus two source reads from a public git mirror.
**Method**: five container arms differing in one variable at a time, on the same host finding 024
measured; two kernel source reads at **v6.12**, each cited to the file and line the claim rests on.
**No arm ran `--privileged`** — what is under test is what works *without* privilege, so an arm that
grants it answers a different question. Every arm's privilege posture is read from
`/proc/self/status` **inside the arm**, before any `unshare`, and is reproduced in full below rather
than inferred from the `docker run` flag line.
**Numbering note**: `027` was the high-water mark across `specs/*/findings/`, established by listing
the whole tree rather than by reading a number out of a document, and `028` was free at that moment
and re-checked free immediately before saving. Two documents in this corpus carry stale reservations
for numbers in this range, which is why the listing is the authority and no written reservation is.

---

## The ruling, per ground, in OD-24's own terms

OD-24 states its deferral rests on **two grounds**, and says the entry "must state both because either
alone would be weaker". They are ruled separately because they moved differently.

| | The ground, as OD-24 words it | Ruling | What carries the ruling |
|---|---|---|---|
| **①** | "The margin over the plain drop is real but is not what closes the gaps, and the thing that closes them has already landed" | **SURVIVES, untouched** | The two repairs are in [`mounts.py`](../../../src/supervisor/mounts.py); mount flags are privilege-indifferent; nothing measured since bears on it |
| **② a** | *measured half* — Docker's default seccomp profile blocks `unshare(CLONE_NEWUSER)` | **STANDS** | Re-measured by [finding 024](./024-deployment-surface-permission-census.md) across eight surfaces |
| **② b** | *inference* — "which under **OD-08**'s self-hosted model is not ours to choose" | **FALSIFIED**, and struck in one of the two places it appears | [Finding 024](./024-deployment-surface-permission-census.md)'s custom profile. **The strike never reached the register** — see [§7](#7-a-divergence-between-the-register-and-its-propagation) |
| **② c** | *the operative clause* — "the deployment surface may not permit the mechanism at all, **and the schedule waits on establishing it**" | **SPENT — discharged, not falsified** | The wider reading it waits on has landed. [Finding 024](./024-deployment-surface-permission-census.md) took eight surfaces; [finding 023](./023-user-namespace-privilege-model.md)'s extension took Ubuntu 24.04. The condition is satisfied, so the ground can no longer be cited as a reason to wait |

**The net answer, stated so it cannot be misread in either direction: the deferral survives, and it
does not survive on the grounds OD-24 gives for it.** It survives on ground ① plus a *replacement*
second ground that the register does not contain. That is not a quibble about wording. A register
entry half of whose stated reasoning is spent will be re-litigated by the next reader who checks it,
and the two available wrong answers — "ground ② is discharged, therefore build" and "the deferral
was never sound" — are both reachable from the entry as it currently reads.

## 1. Ground ① — survives, and it is the ground actually carrying the deferral

Ground ① is an argument about **what the build would buy**, and it has three limbs. All three hold.

**The repairs are landed.** [`mounts.py`](../../../src/supervisor/mounts.py) states both in its module
docstring — the session root remounted `MS_RDONLY` once the namespace is built, and the read-only
remount applied to every mount the recursive bind copied — and both are implemented rather than only
described: `_remount_tree()` walks the tree and applies `MS_REMOUNT | MS_RDONLY`, it is called with
the declaration's own flags at the bind site, and the root remount is the last step of the sequence,
after the steps that need to write into it.

**Mount flags are indifferent to privilege, so the closure holds under every model in play** —
including the plain `setuid(65534)` drop and including doing nothing. This is the load-bearing limb
and it is the reason ground ① cannot be moved by any measurement of the namespace, the map, the LSM
or the deployment surface: none of those is a mount flag.

**Nothing measured since bears on it.** Findings 023 (and its 2026-08-05 extension), 024, 025 and 026
all measure the namespace, the `uid_map` write, the seccomp profile or the `pivot_root` gate. Not one
of them measures the authority-gap closure, and none needs to: the gaps were closed by flag, and
[finding 021](./021-openat2-audit-gap-and-two-authority-gaps.md)'s closure is not conditional on the
privilege model.

**So ground ① is sufficient on its own**, which is worth saying because OD-24 says the opposite of its
own two grounds — that "either alone would be weaker". On the evidence, ① is the strong one and ② was
always the contingent one. ① says *this build does not buy a gap closure*; that is a statement about
value, it needs no host to remain true, and no measurement can retire it. Only a **new requirement**
can — see [§6](#6-the-trigger-that-would-retire-each-ground).

## 2. Ground ② — the measured half stands, the inference fell, and the operative clause is spent

Ground ② is three claims wearing one number, and separating them is the whole of the ruling.

**②a, the measurement, stands.** Docker's default profile blocks `unshare`. Finding 024 re-measured
it across eight surfaces and finding 025 saw the same refusal through the shipped preflight check.
Nothing here disturbs it.

**②b, the inference, is falsified.** "Not ours to choose" does not follow from the measurement,
because the bundle this product ships is exactly where the profile is chosen. Finding 024
demonstrated a custom profile that permits the mechanism, which is a construction rather than an
argument. This was already struck in [feature 002's `plan.md`](../plan.md) and **was never applied to
the register**, which is [§7](#7-a-divergence-between-the-register-and-its-propagation).

**②c, the operative clause, is spent — and this is the finding's ruling on ground ②.** Read it
exactly: *"The schedule waits on the wider reading."* OD-24 explicitly labels this "a sequencing
statement rather than a condition on the model", and says the one reading then available "establishes
the constraint exists rather than how wide it is". **That makes ground ② a wait for information.**
The information has since arrived, from two directions:

- **Finding 024** measured eight deployment surfaces — three container runtimes read at profile
  source, five arms executed — and answered the width question: the refusal is a property of default
  seccomp profiles, and a shipped profile removes it.
- **Finding 023's 2026-08-05 extension** measured the remaining unmeasured layer, an enforcing
  AppArmor host, and found the refusal is not at `unshare` at all: Ubuntu 24.04 **permits** the call
  and confines the result, so the process enters labelled `unconfined` and leaves labelled
  `unprivileged_userns (enforce)`, with the refusal landing downstream on `setgroups` (`EACCES`) and
  the `uid_map` write (`EPERM`).

A ground that says *wait until we know* stops being a reason to wait when we know. **Ground ② is
therefore discharged rather than falsified**, and the distinction matters: falsified would mean the
deferral lost a reason it was entitled to, whereas discharged means the reason was collected and
used up. What the collected reading *returned* was negative, and the negative answer is a real
constraint — but it is a **different ground**, of a different kind, and OD-24 does not state it.

**The replacement, which is already recorded in [feature 002's `plan.md`](../plan.md) and not in the
register.** Its 2026-08-05 correction states the live position: there are still two constraints and
both still bind, but they are **not independent**, because no posture binds exactly one. At
`CapEff=0` the LSM refuses even the self-map, so the distinct map that `CAP_SETUID` guards is never
reached; and holding capabilities in the initial user namespace disables the LSM as a side effect,
because Ubuntu's hook only transitions a process lacking `CAP_SYS_ADMIN` there. Both answer to one
question — *does the supervisor hold capabilities in the initial user namespace?* — and the
consequence is that **no partial progress is available on either**. That is a stronger reason to wait
than the sequencing clause it replaces, and it is substantive where the original was procedural.

## 3. The new measurement — the `newuidmap` route, closed as a least-authority option

OD-24's revised model offers three ways to get the multi-line map written: the supervisor holds
`CAP_SETUID`/`CAP_SETGID`, **or** "delegates that to a `newuidmap` helper", or the fallback plain
drop with no namespace. [Finding 023](./023-user-namespace-privilege-model.md) §4 lists the helper as
**unmeasured**, in terms — *"`newuidmap` is itself AppArmor-profiled on Ubuntu and was not run
here."* It is named in three places across this corpus and measured in none of them. This pass
measured it.

**The host.** `6.12.76-linuxkit`, `aarch64`, the same host finding 024 ran on: no
`/sys/kernel/security/lsm`, no `kernel.apparmor_restrict_unprivileged_userns`. **That is the right
instrument for this question and the wrong one for the other**: with no LSM present, constraint A
cannot fire, so the `CAP_SETUID` limb is measured in isolation. It also means **nothing here is
evidence about Ubuntu 24.04's helper behaviour**, which stays unmeasured.

Every arm runs the same two probe files and differs in the flag line only. `newuidmap` is
`/usr/bin/newuidmap`, mode `04755`, owner uid 0 — setuid-root, verified by `stat` in each arm — and
`/etc/subuid` grants the running user `100000:65536`.

| Arm | Posture, read from `/proc/self/status` before any `unshare` | Route | Result |
|---|---|---|---|
| **1** | `Uid 1000`, `CapEff 0`, **`CapBnd 0`** (`--cap-drop=ALL`) | setuid helper | **`EACCES`** — `newuidmap: open of uid_map failed`. Map read back: empty |
| **2** | `Uid 1000`, `CapEff 0`, `CapBnd 00000000a80425fb` — Docker's default 14, **`CAP_SETUID` present, `CAP_SYS_ADMIN` absent** | setuid helper | **`EPERM`** — `newuidmap: write to uid_map failed`. Map read back: empty |
| **3** | `Uid 1000`, `CapEff 0`, `CapBnd 00000000a82425fb` — arm 2's set **plus exactly `CAP_SYS_ADMIN`** | setuid helper | **`ok`.** Map read back from the kernel: `0 100000 1` / `1 100001 65535` → `multi-line-distinct` |
| **4** | arm 3's posture, first write asks a range outside `/etc/subuid` | setuid helper | **refused**, map empty. *Negative control at the accepting posture* |
| **5** | `Uid 0`, **`CapEff 00000000000000c0` — exactly `CAP_SETGID`+`CAP_SETUID`, no `CAP_SYS_ADMIN`** | direct write by the namespace's creator | **`ok`.** Map read back: `0 100000 1` / `1 100001 65535` → `multi-line-distinct` |

**Arm 2 → arm 3 is a one-bit delta, checked arithmetically rather than by eye**:
`0xa82425fb − 0xa80425fb = 0x200000 = 1 << 21 = CAP_SYS_ADMIN`. Nothing else about the two arms
differs. So the attribution is single-variable: **on this kernel the setuid-helper route requires
`CAP_SYS_ADMIN` in the supervisor's bounding set, and `CAP_SETUID` in it is not sufficient.**

## 4. Why, named to the kernel line, and predicted before it was measured

The mechanism was read from source **before** arm 3 was run, and arm 3 was run as the prediction's
test rather than as its illustration. Two gates, both at **v6.12**:

- **`kernel/user_namespace.c:976`**, inside `map_write()`:
  `if (cap_valid(cap_setid) && !file_ns_capable(file, map_ns, CAP_SYS_ADMIN)) goto out;` with
  `ret = -EPERM` set at line 968. Writing *any* id map demands **`CAP_SYS_ADMIN` over the target
  namespace**, judged against `file->f_cred` — the credentials at open time.
- **`security/commoncap.c:92`**, inside `cap_capable()`:
  `if ((ns->parent == cred->user_ns) && uid_eq(ns->owner, cred->euid)) return 0;` — the owner of a
  user namespace, judged **by euid**, has every capability in it without holding any bit.

**The two compose into the result, and the shape of it is counter-intuitive enough to state plainly.**
The namespace's creator passes line 976 for free, by the line-92 shortcut: it *is* the owner, so it
needs no `CAP_SYS_ADMIN` bit, and the only capability it still needs is the `CAP_SETUID` that
`new_idmap_permitted()` demands at lines 1197–1198 for a map naming ids other than its own. That is
arm 5, and it succeeds holding exactly two bits.

A setuid-root helper **forfeits that shortcut by the very act that makes it privileged**: becoming
euid 0 makes `uid_eq(ns->owner, cred->euid)` false, because the namespace's owner is uid 1000. The
shortcut misses, the loop falls through, and the helper must satisfy line 976's `CAP_SYS_ADMIN` on
its own merits. Docker's default set excludes `CAP_SYS_ADMIN`, which is arm 2's `EPERM`; adding it is
arm 3's `ok`; and emptying the bounding set entirely denies the helper even the open, which is arm
1's `EACCES`.

**So the helper is not a way of holding less authority. It is a way of holding more.**

| Route | Authority the supervisor's **container** must carry | Authority the supervisor **process** carries |
|---|---|---|
| Direct write (arm 5) | `CAP_SETUID` + `CAP_SETGID` | the same two, effective |
| `newuidmap` helper (arm 3) | `CAP_SETUID` + `CAP_SETGID` + **`CAP_SYS_ADMIN`** | **none — `CapEff` is `0`** |

The helper buys exactly one thing, and it is not nothing: the supervisor **process** can run at
`CapEff=0`. What it costs is that the *bounding set* must carry `CAP_SYS_ADMIN`, which any setuid
binary in the image can then pick up. Trading two narrow capabilities in one process for
`CAP_SYS_ADMIN` reachable by every setuid binary in the container is a worse least-authority position
than the direct route, and the decision offers it as though it were a lighter one.

## 5. Is there a buildable model? Yes — and it was already stated, which corrects a premise

**A buildable model exists and has existed since 2026-08-04.** OD-24's *revised* text is that model,
and it is [finding 023](./023-user-namespace-privilege-model.md)'s "nearest buildable variant"
verbatim: the workload root inside a user namespace and unprivileged outside it, mapped to a
dedicated per-session kernel uid range that is not the supervisor's, in a pid namespace of its own
with the workload forked after the unshare, dropping to a second mapped uid once the mount tree is
built; the supervisor **not** unprivileged.

So the framing that a recommendation to lift the deferral needs a buildable model *stated first* is
half a step behind the register. What finding 023 found unbuildable was the **struck original**
wording — "root inside, unprivileged outside", where the failing word is "unprivileged" applied to
the supervisor. The register carries that text struck and the corrected model live, and the corrected
model is adopted. **What is deferred is the build, not the statement**, which OD-24 says in its own
heading.

**What this pass changes about it is narrower and is a real narrowing.** The adopted model offers three
authority routes; arm 3 and arm 5 reduce them to two, and reorder the survivors:

1. **Supervisor holds `CAP_SETUID`+`CAP_SETGID`** — measured working, arm 5, and now established as
   the **least-authority** route that delivers the namespace.
2. **`newuidmap` helper** — measured working, arm 3, at the cost of `CAP_SYS_ADMIN` in the bounding
   set. Available, but **not** available as a way to hold less authority, which is the reason it was
   named. It survives as a route for a deployment that must keep the supervisor process at
   `CapEff=0` for an independent reason.
3. **Fallback: plain `setuid(65534)` drop, no namespace** — closes both authority gaps, needs
   nothing, gives up per-session uid isolation and the mount-tree control.

A supervisor that holds **nothing** in the initial user namespace and still enters a useful namespace
is **not** among them, and after arm 1 it has no measured route left on this host. That is the
sharpest single consequence for the build: the 3–4 day row OD-24 sizes as "the uid/gid map plumbing
and the `CAP_SETUID` decision" is a decision between routes 1 and 3, and route 2 is not the
compromise between them it reads as.

## 6. The trigger that would retire each ground

OD-24's deferral is stated with no schedule, so what the next re-examination needs is a trigger. Both
are conditions, not dates, and **neither is a measurement** — which is itself the useful result,
because it means no further probing of this kind will move the deferral.

**Ground ① retires when, and only when, a requirement asks for something a mount flag cannot deliver
and per-session kernel uid isolation can.** Ground ① is an argument that the build buys no gap
closure; it falls the moment the build buys a *requirement*. Concretely, a requirement that two
concurrent sessions must not be able to signal, `ptrace` or otherwise reach each other, or that
session-written objects must carry distinct on-disk ownership. **No requirement in this corpus states
that today** — FR-048 is about reachability, which the flags deliver. So this trigger is a
specification event, and it will arrive, if at all, from a multi-tenancy or credential-lifetime
clause rather than from a probe.

**The replacement second ground retires when the owner or an operator contract settles the single
question the 2026-08-05 correction identifies**: *may the supervisor hold capabilities in the initial
user namespace?* Because the two constraints collapse onto that one question, a **yes** retires both
at once — holding `CAP_SETUID` puts the supervisor outside Ubuntu's LSM trigger as a side effect — and
a **no** selects the fallback and closes the model out. This is a decision trigger, not a
measurement: no host reading answers it, because it is a statement about what the product is willing
to require of an operator.

**What would *not* retire either ground**, recorded because each is a plausible next probe that would
be wasted work: another deployment surface (②c is already discharged, and a ninth surface adds width
to a settled reading); the `newuidmap` route on Ubuntu (worth measuring for other reasons, but it
cannot make route 2 lower-authority than route 1, since line 976 is upstream of any LSM); or the
T205 boot matrix (it prices the 5.14 floor, and OD-24 adds no facility above it).

## 7. A divergence between the register and its propagation

**The strike of ②b landed in [feature 002's `plan.md`](../plan.md) and never reached the register.**
The register still reads, live and unstruck, that the constraint "lands squarely on **OD-08**'s
self-hosted model, where what the operator's container runtime permits is not ours to choose" —
the exact inference [finding 024](./024-deployment-surface-permission-census.md) falsified and
recorded itself as correcting. Finding 024's own propagation note says the correction was made to
"`plan.md`'s OD-24 note", and the relative link there resolves to feature 002's plan, not to the
register that holds the entry.

**Nothing automated will catch this.** `numeric-provenance` does not run on the register's own
reasoning, and no check compares a register entry against the document that propagates it. The
consequence is the ordinary one for this corpus: a reader who goes to the authoritative entry finds a
falsified inference presented as live, and the correction only in a document downstream of it.

**Repairing it is an edit to the register and this pass may not make it.** It is listed in
[§8](#8-what-this-asks-the-owner-to-decide) as the first item, because it is the cheapest and is
purely a propagation of an already-taken correction rather than a new decision.

## 8. What this asks the owner to decide

Four items. **None is taken here.**

1. **Propagate finding 024's already-made correction into the register**, striking ②b's "not ours to
   choose" inference at OD-24 while keeping the measured half. This is not a new decision; it is a
   correction that stopped one document short of its subject.
2. **Restate ground ② or replace it.** As written it is a sequencing clause whose condition is
   satisfied, and it should either be struck in favour of the substantive constraint the 2026-08-05
   correction states, or explicitly re-adopted with the new reading named. Leaving it as-is invites
   the reading *"the wider reading landed, therefore build"*, which the reading itself does not
   support.
3. **Record the `newuidmap` narrowing.** The model's three routes are now two-and-a-reordering, and
   the route the decision names as delegation is the highest-authority of them. A reader choosing
   between routes on the register's current text would choose the helper for a least-authority reason
   that is measurably backwards.
4. **Answer the single question, or state that it stays open**: may the supervisor hold
   `CAP_SETUID`+`CAP_SETGID` in the initial user namespace? A **yes** retires the replacement ground
   and leaves ① as the sole reason to wait — at which point the deferral becomes a pure
   value-for-effort judgement on a 13–20 day build. A **no** selects the plain-drop fallback and the
   model closes out. **This pass takes no position on which**, because it is a statement about what
   the product may require of an operator and nothing measured here bears on it.

## 9. What this changes downstream, stated for documents this pass may not edit

**No file outside this one was written.** [`tasks.md`](../tasks.md) and `src/runtime/` are held by a
concurrent pass and were not touched; the register was not edited on the rule above.

- **[`tasks.md`](../tasks.md), the `uid_map` obligation already recorded under T206.** That entry
  correctly records that `run_checks()` probes no `uid_map` write, that this is correct today because
  `mounts.py` unshares `CLONE_NEWNS` only, and that the build cannot land without an arm for it. This
  pass adds a requirement on the *shape* of that arm: it must distinguish **which** capability is
  missing, because arms 1, 2 and 3 return `EACCES`, `EPERM` and `ok` from three different bounding
  sets, and a check that reports "the map write failed" sends an operator to the wrong grant. In
  particular a remedy naming `newuidmap` must name `CAP_SYS_ADMIN` with it, or it prescribes a
  configuration that does not work — the same failure mode as the `--cap-add=SYS_ADMIN` warning
  already carried in T206's remedy text, arriving from the opposite direction.
- **[`tasks.md`](../tasks.md), T160's shipped profile.** Unaffected. The profile decides whether
  `unshare` is reachable; every arm here is downstream of a permitted `unshare` and none of them is a
  seccomp question.
- **[`plan.md`](../plan.md)'s privilege-model note.** Already carries the 2026-08-05 correction and is
  the most current statement in the corpus. What it does not yet carry is §3's narrowing of the
  helper route, which is item 3 above.
- **[`spec.md`](../spec.md).** **No requirement text changes and none should.** FR-048, FR-049 and
  FR-050 state properties; the privilege model is the mechanism they are delivered by, and nothing
  measured here moves a property.

## 10. What remains unverified, and where the host is not the target

- **One kernel, one architecture, no LSM.** Every arm is `6.12.76-linuxkit`, `aarch64`, a host with
  no AppArmor and no SELinux. **No claim here is an x86-64 measurement**, and **no claim here is
  evidence about `newuidmap` under an enforcing AppArmor profile** — finding 023 §4's note that
  `newuidmap` is itself AppArmor-profiled on Ubuntu is untouched by this pass and stays open.
- **The two kernel gates are read, not exercised in isolation.** Lines 976 and 92 were read at v6.12
  and are consistent with all five arms, and line 976's necessity is measured as a one-bit delta
  between arms 2 and 3. What is **not** measured is that line 976 is the specific `goto` taken in arm
  2 rather than a different `-EPERM` path in the same function; that attribution is
  **read-from-source**, and the ordering may differ at the 5.14 floor, which was not read.
- **`CAP_SYS_ADMIN` is shown necessary for the helper route, not shown sufficient in general.** Arm 3
  succeeds with Docker's default set plus that one bit. Whether some smaller set containing it also
  works was not enumerated.
- **The helper's exposure was not audited.** That a bounding set carrying `CAP_SYS_ADMIN` is
  reachable by any setuid binary in the image is a property of the capability model, stated in §4 as
  a consequence and **not** demonstrated by an escape here. No attempt was made.
- **Nothing here re-measures ground ①.** The mount repairs were verified as *present and implemented*
  by reading [`mounts.py`](../../../src/supervisor/mounts.py); their gap-closing behaviour is
  [finding 021](./021-openat2-audit-gap-and-two-authority-gaps.md)'s measurement and was not re-run.
  Ground ①'s ruling rests on that finding plus the privilege-indifference of mount flags, which is an
  argument rather than a measurement of this pass.
- **`CLONE_NEWPID` was set in every arm but is not what any arm tests.** The `SIGKILL` mitigation
  finding 023 measured was not re-measured.

## 11. Two method rules this pass exercised rather than cited

**The overflow-uid defect reproduced, and is worth recording as an observation rather than a warning.**
In all five arms the child's `/proc/self/status` **inside** the new namespace, before any map is
written, reads `Uid: 65534 65534 65534 65534` — the overflow uid — while the same file read
*outside*, before the `unshare`, reads `Uid: 1000`. That is the reading that misled an earlier pass
into a diagnosis three steps downstream, and it is the reason every posture in §3's table is taken
before the `unshare` and labelled as such. Corroborating, `CapEff` inside the fresh namespace reads
`000001ffffffffff` — 41 capabilities, the full set — in every arm, which reproduces
[finding 023](./023-user-namespace-privilege-model.md)'s extension exactly and is what makes a
refusal at that posture attributable to something other than the ordinary capability check.

**The classifier is a closed accepting set, and it was observed doing both jobs in the same run.**
`classify_map()` enumerates four accepting values — `multi-line-distinct`, `single-line-distinct`,
`single-line-self`, `empty` — over the map **read back from the kernel**, and everything else falls
to `unclassified`, which is a refusal. There is deliberately no rule of the form "not empty means
written", which is the complement construction
[`tools/README.md`](../../../tools/README.md) records as having twice nearly inverted a containment
gate. It classifies the map rather than the helper's exit status, because an exit status is the
helper's claim and the map is the kernel's.

**And the instrument was planted rather than read.** Arm 3 fired the accepting branch and arm 4 fired
the refusing branch **at the same posture**, differing only in the range requested, so the classifier
is observed distinguishing yes from no rather than assumed able to. **One confound is stated rather
than elided**: arm 3's own planted call ran *after* a successful write, where
`kernel/user_namespace.c:969–971` allows only one write to a map regardless of privilege, so that
particular refusal is over-determined and carries no weight. Arm 4 exists because of it — it makes
the out-of-range call the *first* write, leaving the requested range as the only variable.

## 12. Reproduction

Probes are standalone and were written to `/tmp/f2a-od24/`; they are **not committed**, in keeping
with findings 021, 023 and 024. All five arms run the same image and differ in the flag line only.
The image is `debian:12-slim` plus `uidmap` and `python3`, with a uid-1000 user granted
`100000:65536` in `/etc/subuid` and `/etc/subgid`.

```bash
# Arms 1-4: the setuid newuidmap route. None is --privileged.
docker run --rm --user 1000:1000 --cap-drop=ALL \
  --security-opt seccomp=unconfined f2a-od24                       # arm 1 -> EACCES
docker run --rm --user 1000:1000 \
  --security-opt seccomp=unconfined f2a-od24                       # arm 2 -> EPERM
docker run --rm --user 1000:1000 --cap-add=SYS_ADMIN \
  --security-opt seccomp=unconfined f2a-od24                       # arm 3 -> ok
docker run --rm --user 1000:1000 --cap-add=SYS_ADMIN \
  --security-opt seccomp=unconfined -e F2A_SUBUID_START=7777777 f2a-od24   # arm 4 -> refused

# Arm 5: the direct route, CAP_SETUID+CAP_SETGID and no CAP_SYS_ADMIN.
docker run --rm --user 0:0 --cap-drop=ALL --cap-add=SETUID --cap-add=SETGID \
  --security-opt seccomp=unconfined -v /tmp/f2a-od24:/probe:ro \
  --entrypoint python3 f2a-od24 -u /probe/probe_direct.py          # -> ok

# The two kernel gates, at the tag the claims are made against.
curl -sS https://raw.githubusercontent.com/torvalds/linux/v6.12/kernel/user_namespace.c \
  | sed -n '960,980p;1162,1202p'
curl -sS https://raw.githubusercontent.com/torvalds/linux/v6.12/security/commoncap.c \
  | sed -n '/^int cap_capable/,/^}/p'
```

`seccomp=unconfined` appears in every arm and is **not** the subject of any of them: it isolates the
map limb from the profile limb finding 024 already settled. Finding 024's custom profile permits the
same `unshare`, so no arm here depends on the unconfined posture for anything but keeping one
variable out of the table.
