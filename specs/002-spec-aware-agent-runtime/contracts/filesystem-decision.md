# Contract — Filesystem Decisions at the Syscall Supervisor

**Requirements**: FR-011, FR-013, FR-038, FR-048, FR-054
**Success criterion**: **SC-022**, *as narrowed 2026-08-03 to the record's existence and its rule
identifier — narrowed on what the record vouches for, not on how many records there must be*
**Inherited decisions**: **OD-10** — v1 is read-only against the target, so no write path ships and
every write is refused whatever it names. **Owner decision, 2026-08-03** — FR-048 keeps
`SECCOMP_USER_NOTIF_FLAG_CONTINUE`, so the supervisor records and the mount namespace enforces.
**Source of record**: [`src/supervisor/fs_decisions.py`](../../../src/supervisor/fs_decisions.py) and
[`src/supervisor/seccomp.py`](../../../src/supervisor/seccomp.py). Where this document and the source
disagree, the source is right and this document is a defect.

---

## Posture

**Two mechanisms, deliberately not collapsed into one.** A per-session mount namespace containing
exactly the declared set is the *enforcement*: a location outside the set is **absent**, not
permission-denied, so there is nothing at it to open. That satisfies FR-048's containment clause
perfectly and records **nothing** — the syscall fails inside the container and nothing outside hears
about it. FR-048's recording clause and SC-022's 100% both need a `filesystem_decision` emitted for
every refusal, so a `seccomp` user-notification listener sits outside the container and observes each
path-taking syscall *before the kernel performs it*. This document specifies what that listener's
classifier decides and what it writes down.

**The listener does not enforce, and the division matters.** The supervisor reads the path argument
out of the notifying process's own memory, and another thread in that process can rewrite it between
the read and the kernel's resolution. Every deep-argument `seccomp` filter has this race. So the
listener records and answers `CONTINUE`, and the namespace — which resolves the path in the kernel,
after the race window, inside a root where the undeclared location does not exist — is what refuses.
A workload that wins the race obtains a **wrong log line** and no reach it did not already have.

**Shape is shared with the egress denial, on purpose.** FR-048 requires a filesystem denial recorded
*identically* to a denial under FR-011. Egress states rule identifier, method, path, resolved tier,
session and named reason; a filesystem decision states rule identifier, syscall, path, resolved mode,
session and named reason. `mode` is the filesystem analogue of the tier. One reader learns one shape;
see [`egress-policy.md`](./egress-policy.md).

**No classification of what a command looks like.** FR-013 forbids satisfying these requirements by
inspecting a composed command. Every decision here is taken on a syscall number, an argument register
and a declared location set — never on a command string.

## The rule set

Identifiers are stable strings, never indices: an index renumbers when a rule is inserted, and every
record already emitted then names a different rule. The namespace is `FS-*` and is asserted disjoint
from the enforcement point's `EG-*`, because a reader of a trace has no way to disambiguate a shared
identifier after the fact.

| Rule | Named reason | What it asserts | Serves |
|---|---|---|---|
| **FS-001** | `undeclared_location` | the path resolves outside every declared location | FR-048's positive-declaration clause |
| **FS-002** | `write_to_readonly_location` | a write-mode attempt against a location that *is* declared, and declared read-only | FR-048, **OD-10** |
| **FS-003** | `write_path_not_shipped` | a write-mode attempt against a location declared **writable** — refused because no write path ships in v1 | **OD-10** |
| **FS-004** | `path_escapes_declared_root` | the path carries a `..` component; refused in the form it arrived in rather than normalized and then matched | FR-048 |
| **FS-005** | `path_unreadable_at_notification` | the path argument could not be read out of the target at notification time | SC-022 |
| **FS-006** | `open_flags_unreadable` | an open-family syscall arrived with no flag word, so read-versus-write is unknown | FR-048, SC-022 |

**Every one of these denies.** There is no rule here whose disposition is `allow`; an allow carries
`rule_id = None` and `reason = None` and is the fall-through, not a rule.

**No default rule and no empty identifier.** A `deny` with no `rule_id` cannot be *constructed* —
`FilesystemDecision.__post_init__` raises — rather than being filtered out downstream, because a
downstream filter drops the record and a dropped denial is worse than an unlabelled one. Invariant
INV-004 holds both directions: every denial path produces a registered identifier, **and every
registered identifier is produced by some denial path**. The second direction is not decoration; it
was added because FS-002 sat in the registry unreached for its whole life while every test asked
"does this denial carry *a* rule id" and none asked "does every rule carry a denial".

**FS-004 and FS-005 are refusals of the *question*, not of the location.** Neither has resolved a
location, so both record `mode = "absent"` even where the path names a declared one. Refusing the
traversal form outright has no failure mode; normalizing an untrusted path and then matching it is
the standard way a traversal check is defeated.

## Precedence, as `decide()` actually evaluates it

**The evaluation order is not the numeric order of the identifiers, and nothing makes it so.** Read
top to bottom; the first row whose condition holds returns, and none falls through to a later one.

| Order | Condition | Disposition | `mode` | Rule |
|---|---|---|---|---|
| 1 | `path is None` | `deny` | `absent` | **FS-005** |
| 2 | `syscall in OPEN_SYSCALLS and flags is None` | `deny` | `absent` | **FS-006** |
| 3 | `".." in path.split("/")` | `deny` | `absent` | **FS-004** |
| 4 | `location_set.declaring(path) is None` | `deny` | `absent` | **FS-001** |
| 5 | *modifies* **and** the declaration is `ro` | `deny` | `ro` | **FS-002** |
| 6 | *modifies* **and** the declaration is `rw` | `deny` | `rw` | **FS-003** |
| 7 | otherwise | `allow` | the declared mode | none — `rule_id` is `None` |

So the identifiers fire in the order **FS-005, FS-006, FS-004, FS-001, then FS-002 or FS-003**. A
reader who assumes rules are consulted in numeric order will get rows 1 through 4 backwards.

*modifies* is one predicate over two disjoint syscall sets:

- **`WRITE_SYSCALLS`** — syscalls that modify by their name alone: `unlink`, `unlinkat`, `rename`,
  `renameat2`, `mkdir`, `mkdirat`, `truncate`, `chmod`, `fchmodat`. No argument is consulted.
- **`OPEN_SYSCALLS`** — syscalls whose direction is *not* in the name: `open`, `openat`, `openat2`,
  `creat`. These modify when `is_write_open(flags)` holds, which is true when the access-mode bits are
  `O_WRONLY` or `O_RDWR` **or** any of `O_CREAT`, `O_TRUNC`, `O_APPEND` is set. `O_RDONLY` is zero, so
  a flag word cannot be tested for "is a read", only for the absence of every write bit — and
  `open(path, O_RDONLY | O_TRUNC)` has read access mode and destroys the file, so a classifier masking
  with `O_ACCMODE` alone would call three destructive opens reads.

**Two orderings are load-bearing and are the reason this section exists.**

**Location resolution runs *before* the write branch.** It used to run after. While the write branch
came first, every write was refused as FS-003 with `mode = "absent"` without the classifier ever
asking which location was named — so FS-002, whose entire content is *this location is declared and
declared read-only*, could not fire, and the record could not say a declared location had been written
to. Ordering is the whole of FS-002's reachability.

**FS-006 runs before the traversal check and before resolution**, so an unclassifiable open is
refused without a location or a mode being attributed to it.

**The flag constants are written out in the source rather than taken from `os`.** The supervisor
classifies a *Linux target's* syscall on whatever host it runs on; the two processes agree on the ABI,
not on a Python module. `O_APPEND` is `0o2000` on Linux and `0o10` on Darwin, and reading the host's
value would make the classification silently wrong on a host that differed.

## What an audit record carries

`FilesystemDecision.to_record()` emits exactly these keys, and `content_address()` addresses that
mapping under the canonical form — the same addressing FR-054 requires of the declared location set
this decision was taken against, so a record and the version of the set that produced it are each
nameable by content rather than by position:

| Field | Value |
|---|---|
| `kind` | the constant `"filesystem_decision"` — one of FR-038's closed set of span kinds |
| `session_id` | the session the attempt was made from |
| `disposition` | `"allow"` or `"deny"`; nothing else constructs |
| `syscall` | the name the listener resolved from the syscall number |
| `path` | the string read out of the target — see `path_provenance` |
| `path_provenance` | `"supervisor_read_unverified"` or `"kernel_resolved"`; **no default** |
| `mode` | `"ro"`, `"rw"` or `"absent"` — the filesystem analogue of the egress tier |
| `rule_id` | the `FS-*` identifier, or `null` on an allow |
| `reason` | the rule's named reason, or `null` on an allow |
| `pid` | the notifying process |
| `at` | when the record was built, which is before the kernel acted |

**Ordering is the requirement, not an implementation detail.** The record is written **before the
kernel acts** — the listener sees the attempt while the calling thread is still suspended in
`SECCOMP_IOCTL_NOTIF_RECV`, the record is written, and only then does the response go back. A record
written after the syscall would be lost for exactly the syscalls that killed the process, which are
the ones worth having. `DecisionSink` exists so that this obligation has one call site a reviewer can
check.

**`path_provenance` has no default, and the omission is the point.** The honest answer for v1 is *read
out of the target's memory and never confirmed*; a default would let a future call site drop the caveat
by accident rather than by decision. Every provenance the schema admits is enumerated, exactly one is
authoritative, and it is **not** the one v1 emits — `kernel_resolved` would require
`SECCOMP_RET_ERRNO` with the supervisor supplying the answer, which is a different FR-048 design.
`path_is_authoritative` is exposed as a property so there is one place to change if that ever moves.

**This is what SC-022 is scored on.** The record's *existence* and its rule identifier are the
supervisor's own and the workload cannot influence either; the `path` string is best-effort and marked
as such. A battery arm asserting that the recorded `path` equals the path the adversary asked for is
measuring something this design does not claim and would fail against a correctly-behaving supervisor.

## The FS-002 / FS-003 boundary, and reading traces across the change that drew it

**Read this before comparing any two traces taken either side of the write-mode fix.** The identifier
recorded for a refusal moved for four distinct attempt shapes. **No enforcement behaviour changed for
any of them** — the mount namespace refused before and refuses now, identically — but a diff over
recorded `rule_id` and `mode` will show every one of these, and reading such a diff as a behaviour
change would be wrong.

| Attempt | Recorded before | Recorded now |
|---|---|---|
| a `WRITE_SYSCALLS` member at a declared **read-only** location | `FS-003`, `mode = "absent"` | **`FS-002`**, `mode = "ro"` |
| a `WRITE_SYSCALLS` member at a declared **writable** location | `FS-003`, `mode = "absent"` | `FS-003`, **`mode = "rw"`** |
| a `WRITE_SYSCALLS` member at an **undeclared** path | `FS-003`, `mode = "absent"` | **`FS-001`**, `mode = "absent"` |
| a `WRITE_SYSCALLS` member whose path carries `..` | `FS-003`, `mode = "absent"` | **`FS-004`**, `mode = "absent"` |

The cause of all four is one edit: the write branch used to sit ahead of the traversal check and the
location lookup, so it swallowed every named write syscall before anything else could be asked about
it. FS-003 was, in effect, *"a write syscall at all"*. It now means only *"a write to a location that
was declared, and declared writable"* — the clause that says **no write path exists in v1**, and now
the only thing it says.

**Two further changes in the same edit are behaviour changes and not identifier moves**, and the
distinction is the one a reader needs:

- An **open for writing** — `openat(O_WRONLY)`, or any of `O_CREAT`, `O_TRUNC`, `O_APPEND` — at a
  declared location was recorded as an **allow with `rule_id = null`**. It is now a **deny** under
  FS-002 or FS-003. The kernel always refused it at a read-only location; what was wrong was the
  record, which stated the opposite of what happened. An operator reading the trace of a session that
  tried to overwrite the analyzed application saw a successful read.
- An **open with no flag word** was, by the same route, an allow. It is now a deny under **FS-006**.

**FS-006 is refused rather than assumed, and recorded rather than raised.** Assuming an unclassifiable
open is a read is exactly how the defect returns silently: a call site that forgets to pass flags would
get the old behaviour and no error. It is recorded rather than raised because SC-022 counts attempts,
and an exception would drop the record for the one attempt nobody could classify. `decide()` therefore
takes `flags` as a **required** keyword with no default — a default of `None` would have left every
existing call site compiling unchanged and classifying unchanged, which is the defect with a parameter
added rather than the defect fixed.

**A write to an undeclared path reports FS-001, not FS-002.** Absence is the more fundamental fact:
there is nothing at the path to write to, and saying *"you tried to write to a read-only location"*
about a location that does not exist would be a second wrong record in place of the first.

> **The two registry `description` strings had not caught up with this boundary. Repaired
> 2026-08-04, and the reason they rotted is worth more than the repair.** FS-002's read that it
> *"fires on the whole write set"* and FS-003's that *"the disposition does not depend on which
> location was named"*. Both described the code before the reordering. FS-002's was wrong in **both**
> directions — the write set at a declared writable location is FS-003 and at an undeclared path is
> FS-001, so it fires on less than the write set; and an open-family syscall satisfying
> `is_write_open()` reaches it while sitting in no write set at all, so it fires on more. FS-003's
> was wrong under the reading a registry gets: the deny is indeed common to every modifying attempt,
> but *which rule and which mode are recorded* now turn entirely on the declared mode, which is
> resolved before the branch.
>
> **Nothing reads `Rule.description` — not the runtime, not a test, not this document's own
> generator, because it has none.** `reason` is what reaches a record, so nothing was ever
> misreported and nothing failed. That is precisely why the strings survived the edit that falsified
> them, and no test can close it: prose against semantics is the residue
> [`tools/README.md`](../../../tools/README.md#what-this-cannot-catch) names as the single largest
> gap. A string pinned by a test would be a change-detector an editor satisfies by updating both
> sides. The table above is the check that exists, and it is a human one.

## Where the flag word comes from

The listener reads it from `seccomp_data.args`, which the kernel copied out of the target's registers.
**Unlike `path`, it carries no TOCTOU**: it is a register value rather than a pointer into the
target's address space, so there is nothing for a second thread to rewrite and no way for it to be
unreadable. A `None` for an open therefore means *the listener is not wired for that syscall*, never
*the target raced*.

The argument index is per-syscall and is stated rather than guessed — `open(path, flags, mode)` puts
it at 1, `openat(dirfd, path, flags, mode)` at 2. Off by one here reads the mode word and classifies
every `O_CREAT` open by its umask. The word is masked to 32 bits, because the flag word is an `int` in
the ABI while `args[]` is a `__u64`, and a negative-looking value with the upper half set would
classify every open as a write.

`creat` has no flag word at all: it is `O_WRONLY | O_CREAT | O_TRUNC` by definition, so its flags are
supplied from a table of implied values rather than read.

An invariant test holds the listener to covering every watched open, which is what makes the FS-006
branch unreachable from a correctly wired listener rather than merely unlikely.

## What is not here

**No second path matcher.** `LocationSet.declaring()` answers *"which declaration makes this
reachable"* and there is deliberately no reimplementation of that question in the classifier. Two
matchers that disagree is how a path becomes allowed by the recorder and absent to the kernel, or
worse, the reverse.

**No deny list, no exclusion pattern, no wildcard.** FR-048 requires the set stated positively — *a
location is reachable because it was declared, never because nothing excluded it* — and the
configuration type can express only *this path, this mode, because of this rule*.

**No durability.** `DecisionSink` is in-memory; the storage tier owns durability.

**No write path.** **OD-10**. FS-003 exists to say so in the record, and FR-041 is the exit condition
from read-only, not this contract.

## Open questions

**`openat2` is in `OPEN_SYSCALLS` and cannot be given a flags-argument index.** Its third argument is
a pointer to a `struct open_how`, not a flag word, so there is nothing at a register index to read.
**Nothing is wrong today**: `openat2` is not in the listener's watch set and not in its path-argument
map, so no `openat2` notification is ever raised and the FS-006 branch is not reached by it. Reading
the struct out of target memory would reintroduce exactly the TOCTOU that the path read documents —
and would do it on a value the classifier *acts on*, rather than on one it only records, which is a
materially worse trade than the one already accepted. **Queued as an owner decision. Nothing is
implemented for it, and nothing should be until that decision is taken.**

**`creat` is in `OPEN_SYSCALLS`, is not watched, and would not be caught by the flags-index
invariant.** It has an implied-flags entry ready for the day it is watched, so the classifier would
answer correctly. The narrow gap is in the invariant rather than in the classifier: it derives the set
of open-family syscalls by matching the name prefix `open` against the path-argument map, so an
open-family syscall not named `open*` is outside what it asserts. `creat` is the only such name today.

**`LocationSet.rule_for_refusal()` returns a second identifier for the same refusal.** It yields
`FS-UNDECLARED-001@<set_version>` where `decide()` records `FS-001`. It has no callers anywhere in the
tree. Two vocabularies for one fact is how a trace reader ends up unable to join records; it should be
reconciled with the registry or removed.

## Tests owed

- Every rule in the registry produced by some `decide()` branch, and an allow that still allows — so
  a classifier that denied everything cannot satisfy the first assertion trivially.
- A deny with no rule identifier, and one with an empty string, both refused at construction.
- The write-mode arms in both directions: an open for writing at a read-only declaration denied under
  FS-002 with `mode = "ro"`; the same open for reading allowed; each of `O_CREAT`, `O_TRUNC` and
  `O_APPEND` classified as a write without `O_WRONLY` present.
- A write at an undeclared path recorded as FS-001, and a write at a declared writable location
  recorded as FS-003 — the two halves of the boundary above, asserted separately so neither can rot
  behind the other.
- A flagless open denied under FS-006 rather than allowed.
- The module's flag constants asserted against the Linux ABI values, written out in the test rather
  than read from the host's `os`.
- Every watched open syscall present in the listener's flags-argument map, and `openat`'s index
  asserted to be 2 and `open`'s to be 1.
- The `FS-*` and `EG-*` namespaces asserted disjoint.
- A record whose `path_provenance` is absent refused, and everything v1 emits marked unverified.
