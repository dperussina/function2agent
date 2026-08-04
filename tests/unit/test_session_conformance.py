"""The Python arm of the cross-language capability conformance check.

Asserts that the committed fixture is exactly what today's supervisor code
produces. If someone changes the digest convention, the schema, or the state
machine, this fails and says to regenerate — and regenerating is what makes
the Go arm fail, which is the point. The two arms are a tripwire on a boundary
that otherwise has nothing holding it together.
"""

from __future__ import annotations

import json
import sqlite3

import pytest

from src.supervisor.capability import issue
from src.supervisor.session_table import SessionTable, capability_digest
from tests.fixtures import session_conformance as fixture

_REGENERATE = (
    "the committed conformance fixture no longer matches what the supervisor "
    "produces. If the change was intended, regenerate with "
    "`python tests/fixtures/session_conformance.py` — and expect the Go arm "
    "(TestSupervisorWrittenSessionTableIsReadable) to fail until the "
    "enforcement point is updated to match."
)


def _committed() -> dict:
    return json.loads(fixture.VECTORS_PATH.read_text())


def test_the_committed_fixture_exists() -> None:
    assert fixture.DB_PATH.exists(), (
        "the conformance database is not committed; the Go arm has nothing "
        "to read and would silently cover nothing"
    )
    assert fixture.VECTORS_PATH.exists()


def test_the_digest_convention_has_not_moved(tmp_path) -> None:
    """SHA-256 over the presented string, not over the decoded bytes.

    The convention itself, isolated from the schema, because this is the half
    of the boundary that has no type to enforce it: both sides pass a hex
    string around and neither can tell which convention produced it.
    """
    for session in _committed()["sessions"]:
        assert capability_digest(session["handle"]) == session["capability_sha256"], (
            f"{_REGENERATE}\n(session {session['session_id']})"
        )


def test_the_issued_handle_uses_the_same_convention() -> None:
    """The production issuer, not just the fixture, computes it this way."""
    cap = issue("sess-live")
    assert cap.digest == capability_digest(cap.header_value())


def test_regenerating_reproduces_the_committed_rows(tmp_path) -> None:
    """Schema and rows, built fresh, byte-compared against what is committed."""
    rebuilt = tmp_path / "rebuilt.sqlite3"
    fixture.build(rebuilt)

    def dump(path) -> tuple[list, list]:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        schema = [r[0] for r in conn.execute(
            "SELECT sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY name")]
        rows = [dict(r) for r in conn.execute(
            "SELECT * FROM session ORDER BY session_id")]
        conn.close()
        return schema, rows

    assert dump(rebuilt) == dump(fixture.DB_PATH), _REGENERATE


def test_the_fixture_covers_every_state_the_proxy_distinguishes() -> None:
    """A fixture that only carries the happy path proves nothing about denial."""
    states = {s["state"] for s in _committed()["sessions"]}
    assert states == {"RUNNING", "STARTING", "TERMINATED"}
    honoured = [s for s in _committed()["sessions"] if s["honoured_at_now"]]
    assert len(honoured) == 1, (
        "exactly one row should be honoured; more than one and a broken "
        "predicate could still pass by accident"
    )


def test_honoured_at_agrees_with_the_recorded_expectation() -> None:
    """The Python predicate, against the same instant the Go arm will use.

    `SessionRow.honoured_at` is the sentence stage 1 re-implements in Go. If
    the two ever say different things about the same row, this and its Go
    counterpart disagree about the same fixture.
    """
    with SessionTable(fixture.DB_PATH) as table:
        for session in _committed()["sessions"]:
            row = table.resolve(session["capability_sha256"])
            assert row is not None, f"{_REGENERATE}\n(missing {session['session_id']})"
            assert row.honoured_at(fixture.NOW) is session["honoured_at_now"], (
                f"{session['session_id']}: {session['why']}"
            )


def test_a_handle_that_was_never_issued_resolves_to_nothing() -> None:
    with SessionTable(fixture.DB_PATH) as table:
        assert table.resolve(capability_digest("ff" * 32)) is None
