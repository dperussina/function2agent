"""The cross-language conformance fixture for the capability boundary.

The supervisor writes the session table in Python; the enforcement point reads
it in Go. Nothing in either language forces the two to agree, and the two ways
they can disagree — the digest convention and the column names — both fail
*totally*: every request denied `capability_not_honoured`, with no partial
signal to notice it by.

They agree today. They agree by coincidence rather than by construction, which
is the state this fixture exists to end. It is built by the supervisor's own
code, so a change on the Python side changes the fixture; it is read by the
proxy's own `SessionStore`, so a change on the Go side stops reading it.

The digest convention this pins, stated once so it is greppable from both
sides: **the SHA-256 is taken over the presented handle string as bytes, not
over the bytes the hex decodes to.** The handle is documented as opaque, so
decoding it would be a structural assumption about a value that is defined to
have no structure.

Regenerate with:

    python tests/fixtures/session_conformance.py
"""

from __future__ import annotations

import json
from pathlib import Path

from src.supervisor import session_table
from src.supervisor.session_table import SessionTable, capability_digest

HERE = Path(__file__).parent
DB_PATH = HERE / "session_conformance.sqlite3"
VECTORS_PATH = HERE / "session_conformance.json"

# Fixed synthetic handles, not `secrets.token_bytes`, because a conformance
# vector has to be reproducible byte-for-byte. These authorise nothing: they
# name rows in a fixture database. `capability.issue()`'s real entropy is
# covered separately by the unit tests for that module.
_HANDLES = {
    "honoured": "00" * 32,
    "starting": "11" * 32,
    "terminated": "22" * 32,
    "expired": "33" * 32,
    "terminated_live": "44" * 32,
}

# A fixed instant, so `lease_expires_at` is a committed number rather than
# whatever the clock said when someone last regenerated the fixture. The Go
# arm evaluates the lease against this same instant.
NOW = 1_760_000_000.0
LEASE_SECONDS = 300.0
LEASE_AT_CREATION = NOW + LEASE_SECONDS


def rows() -> list[dict]:
    """The four session states the proxy's stage 1 has to tell apart."""
    return [
        {
            "session_id": "sess-honoured",
            "handle": _HANDLES["honoured"],
            "state": "RUNNING",
            "lease_expires_at": NOW + LEASE_SECONDS,
            "honoured_at_now": True,
            "why": "running, lease in the future — the only shape that is honoured",
        },
        {
            "session_id": "sess-starting",
            "handle": _HANDLES["starting"],
            "state": "STARTING",
            "lease_expires_at": NOW + LEASE_SECONDS,
            "honoured_at_now": False,
            "why": "not yet RUNNING; the lease is irrelevant while the state is not",
        },
        {
            "session_id": "sess-terminated",
            "handle": _HANDLES["terminated"],
            "state": "TERMINATED",
            # `terminate()` also drives the lease to zero, so the value here is
            # 0 rather than the lease it was created with. That is deliberate
            # defence in depth on the supervisor's side — and it is exactly why
            # `sess-terminated-live-lease` below has to exist.
            "lease_expires_at": 0.0,
            "honoured_at_now": False,
            "why": "terminated by the supervisor, which also zeroes the lease",
        },
        {
            "session_id": "sess-terminated-live-lease",
            "handle": _HANDLES["terminated_live"],
            "state": "TERMINATED",
            "lease_expires_at": NOW + LEASE_SECONDS,
            "honoured_at_now": False,
            "why": (
                "the SC-024 replay shape. The supervisor does not currently "
                "produce this row — `terminate()` zeroes the lease — so it is "
                "written directly, bypassing that writer. Without it the "
                "fixture cannot tell a state check from an expiry check, and "
                "an enforcement point that only checked expiry would pass "
                "every other row here."
            ),
        },
        {
            "session_id": "sess-expired",
            "handle": _HANDLES["expired"],
            "state": "RUNNING",
            "lease_expires_at": NOW - 1.0,
            "honoured_at_now": False,
            "why": "running but the lease lapsed — FR-050's ceasing-to-act revocation",
        },
    ]


def _force_lease(table: SessionTable, row: dict) -> None:
    """Set `lease_expires_at` with none of the writer's state guards.

    Deliberately reaching past `SessionTable` — the two rows that need this
    are exactly the ones the supervisor's own writer refuses to produce, which
    is why they are in the fixture at all.
    """
    table._repo.update(  # noqa: SLF001 — deliberate, see the rows' `why`
        session_table.TABLE,
        where={"session_id": row["session_id"]},
        values={"lease_expires_at": row["lease_expires_at"]},
    )


def build(db_path: Path) -> list[dict]:
    """Write the fixture database using the supervisor's own writer.

    Deliberately not hand-written SQL: the point is that the schema and the
    digest come from the production code path, so drift in either shows up
    here rather than at integration.
    """
    db_path.unlink(missing_ok=True)
    vectors = []
    with SessionTable(db_path) as table:
        for row in rows():
            digest = capability_digest(row["handle"])
            table.create(
                session_id=row["session_id"],
                tenant_id="tenant-conformance",
                deployment_id="deploy-conformance",
                capability_sha256=digest,
                lease_expires_at=LEASE_AT_CREATION,
                now=NOW,
            )
            if row["state"] in ("RUNNING", "TERMINATED"):
                table.mark_running(row["session_id"])
            if row["state"] == "TERMINATED":
                table.terminate(row["session_id"], "terminated.operator_terminated")
            # The adversarial row: put the lease back after termination, which
            # the supervisor's own writer will not do. Written through the
            # repository but around `SessionTable`'s state guards — visibly so,
            # and no longer as raw SQL, because since the T016 migration there
            # is no SQL above the repository layer to write.
            if row["session_id"] == "sess-terminated-live-lease":
                _force_lease(table, row)
            if row["state"] == "RUNNING" and row["session_id"] == "sess-expired":
                # `renew` refuses a past instant, and a past instant is the
                # whole point of this row.
                _force_lease(table, row)

            # Read the row back rather than trusting the declaration above: the
            # first version of this fixture recorded what it intended to write,
            # not what the supervisor actually wrote, and hid `terminate()`'s
            # lease zeroing for exactly as long as nothing compared them.
            stored = table.get(row["session_id"])
            assert stored is not None
            if stored.lease_expires_at != row["lease_expires_at"]:
                raise AssertionError(
                    f"{row['session_id']}: declared lease "
                    f"{row['lease_expires_at']}, supervisor stored "
                    f"{stored.lease_expires_at}. Update rows() to record what "
                    f"the supervisor does, do not adjust the supervisor to "
                    f"match the fixture."
                )
            if stored.state != row["state"]:
                raise AssertionError(
                    f"{row['session_id']}: declared state {row['state']}, "
                    f"supervisor stored {stored.state}"
                )
            vectors.append({
                **row,
                "capability_sha256": digest,
                "terminal_state": stored.terminal_state,
            })
    return vectors


def main() -> None:
    vectors = build(DB_PATH)
    VECTORS_PATH.write_text(
        json.dumps(
            {
                "comment": (
                    "Cross-language conformance vectors for the capability "
                    "boundary. Regenerate with "
                    "`python tests/fixtures/session_conformance.py`. The "
                    "digest is SHA-256 over the presented handle string as "
                    "bytes, hex-encoded."
                ),
                "now": NOW,
                "database": DB_PATH.name,
                "sessions": vectors,
            },
            indent=2,
        )
        + "\n"
    )
    print(f"wrote {DB_PATH.name} and {VECTORS_PATH.name}: {len(vectors)} sessions")


if __name__ == "__main__":
    main()
