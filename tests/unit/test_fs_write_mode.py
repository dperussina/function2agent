"""The write-mode half of a filesystem decision (FR-048, SC-022, FS-002).

`decide()` classified by syscall name alone. `openat` is not a read syscall —
it is a read syscall or a write syscall depending on a flag word the classifier
never received — so `openat("/workspace/x", O_WRONLY)` against a location
declared read-only was recorded as an **allow**.

That is not a missing denial. The mount namespace makes the location read-only,
so the kernel refuses the open and the workload gains nothing. What it gains is
an *audit record that says the opposite of what happened*: SC-022 requires 100%
of filesystem attempts to be recorded with the rule that decided them, and a
write attempt recorded as an allow with `rule_id=None` is a recorded attempt
whose record is wrong. An operator reading the trace of a session that tried to
overwrite the analyzed application sees a successful read.

It also left FS-002 `write_to_readonly_location` unreachable — a rule whose own
description then claimed it "fires on the whole write set" and which had never
fired once. A registry entry no path reaches is documentation, not a rule.

That description outlived the reordering that made the rule reachable and was
false from the moment it did: the write set at a declared *writable* location
is FS-003 and at an undeclared path is FS-001. It was corrected on 2026-08-04,
along with FS-003's. Nothing anywhere reads `Rule.description` — not this file,
not the runtime — which is why both strings went stale with every test green.
"""

from __future__ import annotations

import pytest

from src.supervisor import fs_decisions as fs
from src.supervisor.fs_decisions import ALLOW, DENY, decide
from tests.fixtures.locations import document, scratch_entry
from src.supervisor.location_set import parse


# The Linux flag values, written out rather than taken from `os`.
#
# `os.O_APPEND` is 0o2000 on Linux and 0o10 on Darwin, and this suite runs on
# both. The supervisor classifies a *Linux target's* syscall whatever host it
# runs on, so the host's `os` module is the wrong authority — using it made
# this file pass on Linux and fail on macOS for a reason that had nothing to
# do with the code under test.
#
# Source: include/uapi/asm-generic/fcntl.h.
LINUX = {
    "O_RDONLY": 0o0, "O_WRONLY": 0o1, "O_RDWR": 0o2,
    "O_CREAT": 0o100, "O_TRUNC": 0o1000, "O_APPEND": 0o2000,
}


def test_the_modules_flag_constants_match_the_linux_abi() -> None:
    """The literals above and the module's must not drift apart silently."""
    for name, value in LINUX.items():
        if name == "O_RDONLY":
            continue
        assert getattr(fs, name) == value, name


def _ro_set():
    return parse(document())


def _rw_set():
    return parse(document(locations=[
        {"source": "/srv/app", "target": "/workspace", "mode": "ro",
         "rule_id": "FS-DECL-001", "justification": "the analyzed application"},
        scratch_entry("/var/lib/f2a/scratch"),
    ]))


def _decide(syscall: str, path: str, *, flags: int | None = None,
            location_set=None):
    return decide(
        _ro_set() if location_set is None else location_set,
        session_id="s1", syscall=syscall, path=path, pid=7, now=0.0,
        flags=flags,
    )


# --- the defect itself -----------------------------------------------------

@pytest.mark.parametrize("flag_name", ["O_WRONLY", "O_RDWR"])
def test_an_open_for_writing_at_a_readonly_location_is_denied(flag_name) -> None:
    """The reproduction. Recorded as an allow before this test existed."""
    decision = _decide("openat", "/workspace/main.py",
                       flags=LINUX[flag_name])
    assert decision.disposition == DENY, (
        f"openat({flag_name}) against a read-only declared location was "
        "recorded as an allow. The record then states the opposite of what "
        "the kernel did."
    )
    assert decision.rule_id == "FS-002"
    assert decision.reason == "write_to_readonly_location"


@pytest.mark.parametrize("flag_name", ["O_CREAT", "O_TRUNC", "O_APPEND"])
def test_the_modifying_flags_are_writes_even_without_o_wronly(flag_name) -> None:
    """`O_RDONLY` is zero, so a flag word can be "read" and still modify.

    `open(path, O_RDONLY|O_TRUNC)` truncates. A classifier that tested only
    the access-mode bits would call these reads and be wrong three times.
    """
    decision = _decide("openat", "/workspace/main.py",
                       flags=LINUX["O_RDONLY"] | LINUX[flag_name])
    assert decision.disposition == DENY
    assert decision.rule_id == "FS-002"


def test_fs_002_is_reachable_at_all() -> None:
    """The rule had never fired. A registry entry no path reaches is prose."""
    reached = {
        _decide("openat", "/workspace/main.py", flags=LINUX["O_WRONLY"]).rule_id,
    }
    assert "FS-002" in reached, (
        "FS-002 write_to_readonly_location is unreachable. Its description "
        "claimed it 'fires on the whole write set' for the entire period it "
        "fired on nothing."
    )


def test_the_audit_record_names_the_declared_mode_it_violated() -> None:
    """A denial that says `absent` would misdescribe a location that exists.

    FS-002's whole content is *this location is declared, and declared
    read-only*. Recording `mode="absent"` — what the pre-existing write branch
    does — throws that away and makes FS-002 indistinguishable from FS-001 in
    the record.
    """
    decision = _decide("openat", "/workspace/main.py", flags=LINUX["O_WRONLY"])
    record = decision.to_record()
    assert record["mode"] == "ro"
    assert record["disposition"] == DENY
    assert record["rule_id"] == "FS-002"
    assert record["syscall"] == "openat"
    assert record["path"] == "/workspace/main.py"


# --- the positive controls, so none of the above is vacuous ----------------

def test_an_open_for_reading_is_still_allowed() -> None:
    decision = _decide("openat", "/workspace/main.py", flags=LINUX["O_RDONLY"])
    assert decision.disposition == ALLOW
    assert decision.rule_id is None
    assert decision.mode == "ro"


def test_a_read_at_an_undeclared_path_is_still_fs_001() -> None:
    decision = _decide("openat", "/etc/shadow", flags=LINUX["O_RDONLY"])
    assert decision.rule_id == "FS-001"


def test_a_write_at_an_undeclared_path_is_still_undeclared() -> None:
    """Absence is the more fundamental fact and stays the reported one.

    There is nothing at the path to write to, and saying "you tried to write
    to a read-only location" about a location that does not exist would be a
    second wrong record in place of the first.
    """
    decision = _decide("openat", "/etc/shadow", flags=LINUX["O_WRONLY"])
    assert decision.rule_id == "FS-001"


def test_a_write_syscall_at_a_writable_location_is_still_refused() -> None:
    """OD-10: no write path ships. FS-003 is the clause that says so, and it
    stays reachable — it is now the *only* thing it was ever about."""
    decision = _decide("unlinkat", "/scratch/x", location_set=_rw_set())
    assert decision.disposition == DENY
    assert decision.rule_id == "FS-003"


def test_a_write_syscall_at_a_readonly_location_is_fs_002() -> None:
    decision = _decide("unlinkat", "/workspace/main.py")
    assert decision.disposition == DENY
    assert decision.rule_id == "FS-002"


# --- the flags must actually arrive ----------------------------------------

def test_a_flagless_open_is_not_assumed_to_be_a_read() -> None:
    """`flags=None` means the supervisor could not classify the attempt.

    Defaulting an unknown flag word to "read" is how the defect would come
    back: a caller that forgets to pass flags gets the old behaviour and no
    error. Refusing is the only answer that cannot be silently wrong, and it
    is consistent with FS-005 already refusing an unreadable path.
    """
    decision = _decide("openat", "/workspace/main.py", flags=None)
    assert decision.disposition == DENY
    assert decision.rule_id == "FS-006"
    assert decision.reason == "open_flags_unreadable"


def test_every_open_syscall_has_a_flags_argument_index() -> None:
    """The listener must know where the flag word is for each watched open.

    An open syscall missing from this map would reach `decide()` with
    `flags=None` forever, which is the defect with a refusal in front of it
    rather than the defect fixed.
    """
    from src.supervisor.seccomp import _FLAGS_ARG, _PATH_ARG

    opens = {name for name in _PATH_ARG if name.startswith("open")}
    assert opens, "no open syscalls are watched; the parser found nothing"
    assert opens <= set(_FLAGS_ARG), (
        f"watched open syscalls with no flags argument index: "
        f"{sorted(opens - set(_FLAGS_ARG))}"
    )


def test_the_listener_reads_the_flag_word_from_the_right_argument() -> None:
    """openat's flags are argument 2; open's are argument 1. Off by one here
    reads the mode word and classifies every `O_CREAT` open by its umask."""
    from src.supervisor.seccomp import _FLAGS_ARG

    assert _FLAGS_ARG["openat"] == 2
    assert _FLAGS_ARG["open"] == 1


def test_the_rule_registry_still_agrees_with_itself() -> None:
    assert fs.WRITE_TO_READONLY.rule_id == "FS-002"
    assert fs.RULES_BY_ID["FS-002"] is fs.WRITE_TO_READONLY
    assert all(r.rule_id in fs.RULES_BY_ID for r in fs.RULES)
