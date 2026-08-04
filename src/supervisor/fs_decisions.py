"""T100 — `filesystem_decision` records carrying the rule that produced the
refusal, **identical in shape to an egress denial** (FR-048, SC-022).

The shape is deliberately the same as the enforcement point's disposition
record. Egress states rule identifier, method, path, resolved tier, session and
named reason; a filesystem decision states rule identifier, syscall, path,
resolved mode, session and named reason. One reader learns one shape.

**Ordering is the requirement, not an implementation detail.** FR-048's
enforcement — an empty root — satisfies the requirement and *records nothing*,
which fails SC-022's 100%. So the supervisor emits the record **before the
kernel acts**: the seccomp listener sees the attempt while the calling thread
is still suspended in `SECCOMP_IOCTL_NOTIF_RECV`, the record is written, and
only then does the response go back and the kernel resolve the path. A record
written after the syscall would be lost for exactly the syscalls that killed
the process, which are the ones worth having.

**No default rule.** `deny` requires a `Rule`; there is no fallback identifier
and no empty string. A refusal that cannot name its rule is a defect the
invariant suite fails on, and constructing one here is impossible rather than
discouraged.

**The `path` is not a fact, and the record says so.** See `path_provenance`
below and the TOCTOU note in `seccomp.py`. SC-022 counts records; the record's
*existence* is exact and the path string in it is best-effort.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Iterable

from src.contracts.canonical import content_address
from src.supervisor.location_set import LocationSet

ALLOW = "allow"
DENY = "deny"

# ---------------------------------------------------------------------------
# Path provenance (owner decision 2026-08-03, narrowing SC-022 to the record's
# existence).
#
# WHY THIS FIELD EXISTS. The supervisor reads the path argument out of the
# notifying process's own memory. A second thread in that process can rewrite
# that memory between the supervisor's read and the kernel's resolution, so the
# path recorded can be a path the kernel never resolved. The record is then
# *wrong*, not merely imprecise.
#
# WHY IT IS NOT AN ACCESS-CONTROL HOLE. The mount namespace is the enforcement
# and the supervisor is only the recorder. An undeclared path is ABSENT — there
# is nothing at it to open — so a workload that wins this race misattributes an
# audit entry and gains no reach it did not already have. Nothing reads this
# field to decide anything.
#
# WHETHER PRINCIPLE I's VALIDATE-OR-MARK-PROVISIONAL RULE REACHES IT. By its
# terms, no: the clause governs a *derived verifier* — something that decides
# whether a thing succeeded — and this field verifies nothing and gates nothing.
# The rule's stated hazard does reach it exactly, though: "complete and wrong is
# indistinguishable from correct at the point of use" is true of an auditor
# reading a path. So the marking is applied on the hazard and NOT on a claim
# that the principle compels it. Recording the distinction because claiming
# principle coverage where there is none is its own kind of error.
PATH_SUPERVISOR_READ = "supervisor_read_unverified"
PATH_KERNEL_RESOLVED = "kernel_resolved"

# Every provenance a record may carry. `kernel_resolved` is declared but v1
# never emits it: it would require `SECCOMP_RET_ERRNO` with the supervisor
# supplying the answer, which is a different FR-048 design. It is here so that
# the field has a meaningful contrast and so the day someone builds that, the
# schema does not have to move.
PATH_PROVENANCES = frozenset({PATH_SUPERVISOR_READ, PATH_KERNEL_RESOLVED})

# The provenances under which the path may be read as fact. Exactly one, and it
# is not the one v1 emits.
AUTHORITATIVE_PATH_PROVENANCES = frozenset({PATH_KERNEL_RESOLVED})


@dataclass(frozen=True)
class Rule:
    """A filesystem rule. The identifier is what a disposition carries."""

    rule_id: str
    reason: str
    description: str


# The rule set. Identifiers are stable strings, not indices, because an index
# renumbers when a rule is inserted and every record already emitted then names
# a different rule.
UNDECLARED_LOCATION = Rule(
    "FS-001", "undeclared_location",
    "the path resolves outside every declared location (FR-048)",
)
WRITE_TO_READONLY = Rule(
    "FS-002", "write_to_readonly_location",
    "a write-mode syscall against a location declared read-only. v1 is "
    "read-only end to end (OD-10), so this fires on the whole write set.",
)
WRITE_PATH_ABSENT = Rule(
    "FS-003", "write_path_not_shipped",
    "a write syscall at all. OD-10: no write path ships in v1, so the "
    "disposition does not depend on which location was named.",
)
ESCAPING_PATH = Rule(
    "FS-004", "path_escapes_declared_root",
    "the path contains a traversal that leaves the declared location once "
    "resolved; refused rather than normalized",
)
UNREADABLE_PATH = Rule(
    "FS-005", "path_unreadable_at_notification",
    "the path argument could not be read out of the target at notification "
    "time. Recorded rather than assumed benign — SC-022 counts records, and "
    "an unreadable attempt is still an attempt.",
)

RULES: tuple[Rule, ...] = (
    UNDECLARED_LOCATION, WRITE_TO_READONLY, WRITE_PATH_ABSENT,
    ESCAPING_PATH, UNREADABLE_PATH,
)
RULES_BY_ID = {rule.rule_id: rule for rule in RULES}

# Syscalls that would modify. Under OD-10 every one of these is refused
# regardless of location, and the rule identifier says which clause did it.
WRITE_SYSCALLS = frozenset({
    "unlink", "unlinkat", "rename", "renameat2", "mkdir", "mkdirat",
    "truncate", "chmod", "fchmodat",
})


@dataclass(frozen=True)
class FilesystemDecision:
    """One decision. The same fields an egress disposition carries."""

    session_id: str
    disposition: str
    syscall: str
    path: str | None
    mode: str  # "ro" | "rw" | "absent" — the filesystem analogue of the tier
    rule_id: str | None
    reason: str | None
    pid: int
    at: float

    # No default. A writer must state where the path came from, because the
    # honest answer for v1 is "read out of the target's memory and never
    # confirmed", and a default would let a future call site omit the caveat
    # by accident rather than by decision.
    path_provenance: str = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        # The invariant, enforced at construction rather than checked later:
        # a deny with no rule identifier cannot be built.
        if self.disposition == DENY and not self.rule_id:
            raise ValueError(
                "a deny disposition must carry a rule identifier "
                "(egress-policy.md: 'A denial with no rule identifier fails "
                "the invariant suite')"
            )
        if self.disposition not in (ALLOW, DENY):
            raise ValueError(f"unknown disposition {self.disposition!r}")
        if self.path_provenance not in PATH_PROVENANCES:
            raise ValueError(
                f"path_provenance must be one of {sorted(PATH_PROVENANCES)}, "
                f"got {self.path_provenance!r}. There is no default: the path "
                "on a filesystem decision is read out of another process's "
                "memory and is best-effort, and a record that does not say so "
                "presents a guess as a fact."
            )

    @property
    def path_is_authoritative(self) -> bool:
        """Whether a reader may treat `path` as what the kernel resolved.

        False for everything v1 emits. Exposed as a property rather than left
        for each reader to work out from the provenance string, so there is one
        place to change if the enforcement design ever moves.
        """
        return self.path_provenance in AUTHORITATIVE_PATH_PROVENANCES

    def to_record(self) -> dict[str, Any]:
        return {
            "kind": "filesystem_decision",
            "session_id": self.session_id,
            "disposition": self.disposition,
            "syscall": self.syscall,
            "path": self.path,
            "path_provenance": self.path_provenance,
            "mode": self.mode,
            "rule_id": self.rule_id,
            "reason": self.reason,
            "pid": self.pid,
            "at": self.at,
        }

    def content_address(self) -> str:
        return content_address(self.to_record())


def decide(
    location_set: LocationSet,
    *,
    session_id: str,
    syscall: str,
    path: str | None,
    pid: int,
    now: float | None = None,
    path_provenance: str = PATH_SUPERVISOR_READ,
) -> FilesystemDecision:
    """Resolve one attempt. Every branch returns a record; none returns `None`.

    A path outside the declared set is denied *and recorded here* even though
    the mount namespace has already made it absent. The two are not redundant:
    the namespace is the enforcement, this is SC-022's record, and neither
    substitutes for the other.
    """
    moment = time.time() if now is None else now

    def built(disposition: str, mode: str, rule: Rule | None) -> FilesystemDecision:
        return FilesystemDecision(
            session_id=session_id,
            disposition=disposition,
            syscall=syscall,
            path=path,
            mode=mode,
            rule_id=None if rule is None else rule.rule_id,
            reason=None if rule is None else rule.reason,
            pid=pid,
            at=moment,
            path_provenance=path_provenance,
        )

    if path is None:
        return built(DENY, "absent", UNREADABLE_PATH)
    if syscall in WRITE_SYSCALLS:
        return built(DENY, "absent", WRITE_PATH_ABSENT)
    if ".." in path.split("/"):
        # Not normalized. Normalizing an untrusted path and then matching is
        # the standard way a traversal check is defeated; refusing the form
        # outright has no such failure mode.
        return built(DENY, "absent", ESCAPING_PATH)

    # The one resolver. `LocationSet.declaring()` answers "which declaration
    # makes this reachable", and there is deliberately no second implementation
    # of that question here — two matchers that disagree is how a path becomes
    # allowed by the recorder and absent to the kernel, or worse, the reverse.
    location = location_set.declaring(path)
    if location is None:
        return built(DENY, "absent", UNDECLARED_LOCATION)
    return built(ALLOW, location.mode, None)


class DecisionSink:
    """Where decisions go. In-memory here; T-06's storage tier owns durability.

    Named and separated so the ordering obligation has one call site: the
    seccomp listener writes here *before* answering the notification, and a
    reviewer can check that in one place.
    """

    def __init__(self) -> None:
        self.decisions: list[FilesystemDecision] = []

    def emit(self, decision: FilesystemDecision) -> None:
        self.decisions.append(decision)

    def denials(self) -> Iterable[FilesystemDecision]:
        return (d for d in self.decisions if d.disposition == DENY)

    def all_denials_carry_rule_id(self) -> bool:
        return all(d.rule_id for d in self.denials())
