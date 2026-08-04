"""SC-022 narrowed to the record's existence; the path marked best-effort.

Owner decision, 2026-08-03. The mount namespace is the enforcement and the
supervisor is only the recorder, so a workload that wins the TOCTOU in
`read_target_path` misattributes an audit entry and gains no reach. What it
must not be able to do is produce a record that presents the misattributed path
as fact.

These tests assert the marking is structural — that a record cannot be built
without stating where its path came from — rather than a convention the next
call site can forget.
"""

from __future__ import annotations

import pytest

from src.supervisor import fs_decisions as fs
from tests.fixtures.locations import location_set


def _decide(path: str | None, syscall: str = "openat", flags: int | None = 0):
    return fs.decide(
        location_set(),
        session_id="sess-1",
        syscall=syscall,
        path=path,
        pid=1234,
        # O_RDONLY. Provenance is orthogonal to the read/write classification,
        # so these cases pick the read direction and hold it fixed rather than
        # letting the direction vary underneath a provenance assertion.
        flags=flags,
        now=1_760_000_000.0,
    )


def test_a_record_cannot_be_built_without_stating_its_path_provenance() -> None:
    """No default. A writer must decide, not inherit."""
    with pytest.raises(ValueError, match="path_provenance"):
        fs.FilesystemDecision(
            session_id="s", disposition=fs.ALLOW, syscall="openat",
            path="/srv/app/main.py", mode="ro", rule_id=None, reason=None,
            pid=1, at=0.0,
        )


def test_an_unknown_provenance_is_refused() -> None:
    with pytest.raises(ValueError, match="path_provenance"):
        fs.FilesystemDecision(
            session_id="s", disposition=fs.ALLOW, syscall="openat",
            path="/srv/app/main.py", mode="ro", rule_id=None, reason=None,
            pid=1, at=0.0, path_provenance="probably_right",
        )


def test_everything_v1_emits_is_marked_unverified() -> None:
    """The supervisor reads the path out of another process's memory.

    There is no path through `decide` that produces an authoritative path,
    because there is no mechanism in v1 that could justify one.
    """
    for path, syscall in [
        ("/srv/app/main.py", "openat"),
        ("/etc/shadow", "openat"),
        ("/srv/app/x", "unlink"),
        ("/srv/app/../etc/passwd", "openat"),
        (None, "openat"),
    ]:
        decision = _decide(path, syscall)
        assert decision.path_provenance == fs.PATH_SUPERVISOR_READ
        assert decision.path_is_authoritative is False, (
            "v1 uses SECCOMP_USER_NOTIF_FLAG_CONTINUE, so the kernel resolves "
            "the pointer itself after the supervisor has read it. No record "
            "produced under that design may claim its path is what the kernel "
            "resolved."
        )


def test_the_provenance_reaches_the_serialized_record() -> None:
    """A marking that does not survive serialization is not a marking.

    The record is what an auditor reads; if the caveat lives only on the
    in-process object, the reader gets the path as a bare fact.
    """
    record = _decide("/etc/shadow").to_record()
    assert record["path_provenance"] == fs.PATH_SUPERVISOR_READ
    assert "path" in record


def test_the_provenance_changes_the_content_address() -> None:
    """Two records differing only in provenance are different records.

    Otherwise a later design that produced authoritative paths would collide
    with the records this one wrote, and the distinction would be unrecoverable
    from storage.
    """
    unverified = _decide("/etc/shadow")
    authoritative = fs.FilesystemDecision(
        **{**unverified.__dict__, "path_provenance": fs.PATH_KERNEL_RESOLVED}
    )
    assert unverified.content_address() != authoritative.content_address()


def test_only_kernel_resolved_is_authoritative() -> None:
    """The set is closed and `supervisor_read_unverified` is not in it."""
    assert fs.AUTHORITATIVE_PATH_PROVENANCES == {fs.PATH_KERNEL_RESOLVED}
    assert fs.PATH_SUPERVISOR_READ not in fs.AUTHORITATIVE_PATH_PROVENANCES
    assert fs.PATH_SUPERVISOR_READ in fs.PATH_PROVENANCES


def test_the_record_exists_even_when_the_path_could_not_be_read() -> None:
    """SC-022 counts records, and this is the case that tests that reading.

    An unreadable path is the extreme of best-effort: there is no string at
    all. The attempt is still recorded, with a rule naming why.
    """
    decision = _decide(None)
    assert decision.disposition == fs.DENY
    assert decision.rule_id == fs.UNREADABLE_PATH.rule_id
    assert decision.path is None
    assert decision.path_provenance == fs.PATH_SUPERVISOR_READ


def test_the_toctou_is_documented_where_it_occurs() -> None:
    """The reasoning has to live at the race, not in a design document.

    Asserted rather than trusted, because the next reader of
    `read_target_path` is the person who would otherwise add a
    'the path is verified' comment.

    **This test used to require the word "absent" and that requirement was
    wrong.** The docstring's argument was *"an undeclared location is absent —
    there is nothing at it to open"*, and finding 021 falsified the second
    clause: as uid 0 a workload created files directly in the session root,
    because the root `tmpfs` carried no `MS_RDONLY`. A path a workload can
    create is a path there is something at. Pinning the old word would have
    held the docstring to the false version, so the phrases below pin the two
    halves the argument actually needs — that the namespace refuses, and that
    nothing can be created at an undeclared path — rather than the wording
    that happened to be there when the test was written.
    """
    from src.supervisor import seccomp

    doc = seccomp.read_target_path.__doc__ or ""
    for phrase in [
        "TOCTOU",
        "mount namespace is the enforcement",
        "not present in the session's root",
        "cannot put one there",
    ]:
        assert phrase in doc, (
            f"read_target_path's docstring no longer explains {phrase!r}; the "
            "race is undocumented where it occurs"
        )
