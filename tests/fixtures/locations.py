"""Committed location-set fixtures (FR-053).

One builder, used by every test that needs a declared set, so that a change to
the schema breaks the fixture once rather than in nine places — and so that no
test quietly declares a *different* set than the one the mechanism tests use.
"""

from __future__ import annotations

from typing import Any

from src.supervisor.location_set import LocationSet, parse


def document(
    *,
    locations: list[dict[str, Any]] | None = None,
    set_version: str = "2026.08.03-1",
    deployment_id: str = "d-fixture",
) -> dict[str, Any]:
    if locations is None:
        locations = [
            {
                "source": "/srv/app",
                "target": "/workspace",
                "mode": "ro",
                "rule_id": "FS-DECL-001",
                "justification": "the analyzed application, read-only under OD-10",
            },
            {
                "source": "/opt/toolchain",
                "target": "/opt/toolchain",
                "mode": "ro",
                "rule_id": "FS-DECL-002",
                "justification": "the interpreter and its resolved dependencies "
                                 "(FR-021)",
            },
        ]
    return {
        "schema_version": "1.0.0",
        "set_version": set_version,
        "deployment_id": deployment_id,
        "locations": locations,
    }


def location_set(**kwargs: Any) -> LocationSet:
    return parse(document(**kwargs))


def scratch_entry(source: str, target: str = "/scratch") -> dict[str, Any]:
    """A writable scratch declaration, for tests that need a `rw` mode present.

    OD-10 makes v1 read-only end to end, so this exists to exercise the *mode*
    branch of the parser and the decision path — not to model a shipped write
    path.
    """
    return {
        "source": source,
        "target": target,
        "mode": "rw",
        "rule_id": "FS-DECL-003",
        "justification": "per-session scratch, keyed by session id (FR-050)",
    }
