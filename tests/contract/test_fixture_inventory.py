"""T200 — the fixture inventory matches the tree FR-053 named.

`tests/fixtures/README.md` is T008's inventory. A Present location that
is not on disk, or a committed child of `tests/fixtures/` the table
forgot, is a claim. T190's support-audit shape: walk the record against
the filesystem, and the filesystem against the record.

Do not invent a fixture to close an Owed row.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
INVENTORY = Path("tests/fixtures/README.md")
FIXTURES = REPO / "tests" / "fixtures"

SCAFFOLDING = frozenset({"README.md", "__init__.py", "__pycache__"})

#: Sets capabilities name that live outside tests/fixtures/. Each must
#: appear in the inventory and exist. A silent shrink is the walk
#: passing over nothing.
NAMED_OUTSIDE = (
    Path("tests/conformance/cassettes"),
    Path("tests/batteries/effect_gate_oracle.py"),
    Path("tests/batteries/test_bounds_exhaustion.py"),
    Path("tests/batteries/test_seccomp_overhead.py"),
    Path("tests/batteries/test_ceilings_under_resume.py"),
    Path("tests/integration/test_resume_sigkill.py"),
    Path("tests/integration/test_store_concurrent_writers.py"),
    Path("src/runtime/drift/scheduler.py"),
    Path("src/proxy/framing_test.go"),
    Path("tests/invariants"),
    Path("deploy/images/sandbox.Dockerfile"),
)

STALE_ABSENCE = re.compile(
    r"The scheduler does not exist"
    r"|v1 has no measured resume",
)

PRESENT_HEADING = re.compile(r"^Present,", re.M)
OWED_HEADING = re.compile(r"^Owed,", re.M)
LOCATION_CELL = re.compile(r"`([^`]+)`")
BRACE = re.compile(r"\{([^}]+)\}")
TABLE_ROW = re.compile(r"^\| ([^|]+) \| ([^|]+) \| ([^|]+) \|", re.M)


def _inventory_text() -> str:
    path = REPO / INVENTORY
    assert path.is_file(), f"{INVENTORY} is gone; it was FR-053's inventory"
    return path.read_text()


def _section(text: str, start: re.Pattern[str], end: re.Pattern[str] | None) -> str:
    match = start.search(text)
    assert match, f"inventory is missing {start.pattern}"
    stop = end.search(text, match.end()) if end is not None else None
    return text[match.start() : stop.start() if stop else None]


def expand_location(token: str) -> list[str]:
    """Turn `foo.{py,json}` into the paths the brace names."""
    match = BRACE.search(token)
    if not match:
        return [token]
    return [
        token[: match.start()] + part + token[match.end() :]
        for part in match.group(1).split(",")
    ]


def present_locations(text: str) -> list[str]:
    """Backtick paths in the Present *table*, braces expanded.

    The prose under the table is full of backticks (`SIGKILL`,
    `terminate()`). Those are not locations. Only the third cell of a
    three-column row is.
    """
    section = _section(text, PRESENT_HEADING, OWED_HEADING)
    found: list[str] = []
    for row in TABLE_ROW.finditer(section):
        fixture, _requirement, cell = (part.strip() for part in row.groups())
        if fixture in {"Fixture", "---"}:
            continue
        for raw in LOCATION_CELL.findall(cell):
            found.extend(expand_location(raw))
    return found


def fixture_children() -> list[str]:
    return sorted(
        path.name
        for path in FIXTURES.iterdir()
        if path.name not in SCAFFOLDING and not path.name.startswith(".")
    )


def location_exists(token: str) -> bool:
    relative = token.rstrip("/")
    path = REPO / relative
    if path.exists():
        return True
    if any(ch in relative for ch in "*?["):
        return any(REPO.glob(relative))
    return False


def inventory_mentions(text: str, name: str) -> bool:
    """A child is inventoried when a *path* names it, not a prose word.

    ``admission`` appearing in "admission sets" is not the directory
    ``tests/fixtures/admission/``. Dropping the Present row must fail.
    """
    if f"tests/fixtures/{name}" in text:
        return True
    if f"`{name}`" in text or f"`{name}/`" in text:
        return True
    for raw in LOCATION_CELL.findall(text):
        for expanded in expand_location(raw):
            if Path(expanded.rstrip("/")).name == name:
                return True
    return False


def test_every_present_location_exists() -> None:
    """A named fixture that is not in the tree fails."""
    text = _inventory_text()
    locations = present_locations(text)
    assert len(locations) >= 20, (
        f"the Present table named {len(locations)} locations; T200 "
        "walked more than that. A shorter table is the inventory "
        "passing over nothing."
    )
    missing = [token for token in locations if not location_exists(token)]
    assert missing == [], (
        "Present location(s) are not in the tree (FR-053):\n  "
        + "\n  ".join(missing)
    )


def test_every_committed_fixture_child_is_inventoried() -> None:
    """A committed fixture the inventory forgot is listed."""
    text = _inventory_text()
    children = fixture_children()
    assert len(children) >= 12, (
        f"tests/fixtures/ held {len(children)} children; T200 walked "
        "more than that. Check SCAFFOLDING."
    )
    missing = [name for name in children if not inventory_mentions(text, name)]
    assert missing == [], (
        "committed fixture(s) under tests/fixtures/ are not in the "
        "inventory (FR-053):\n  "
        + "\n  ".join(missing)
    )


def test_named_sets_outside_fixtures_are_inventoried_and_present() -> None:
    text = _inventory_text()
    assert len(NAMED_OUTSIDE) >= 11, (
        "NAMED_OUTSIDE shrank below the set T200 walked. A shorter "
        "list is the catalog passing over nothing."
    )
    missing: list[str] = []
    for relative in NAMED_OUTSIDE:
        path = REPO / relative
        if not path.exists():
            missing.append(f"{relative}: gone from the tree")
        if relative.as_posix() not in text and relative.name not in text:
            missing.append(f"{relative}: not named in the inventory")
    assert missing == [], (
        "named corpus / battery / fixture set(s) drifted (FR-053):\n  "
        + "\n  ".join(missing)
    )


def test_owed_does_not_claim_a_built_fixture_is_absent() -> None:
    """The scheduler exists; resume is measured. Those sentences are stale."""
    owed = _section(_inventory_text(), OWED_HEADING, re.compile(r"^## Running", re.M))
    hits = STALE_ABSENCE.findall(owed)
    assert hits == [], (
        "Owed still claims a built fixture is absent:\n  "
        + "\n  ".join(hits)
        + "\nMove the row to Present and record the residual. Do not "
        "leave 'The scheduler does not exist' after T141."
    )


def test_reference_application_overhead_stays_owed() -> None:
    """T101 did not discharge the reference-app clause. T199 named this."""
    owed = _section(_inventory_text(), OWED_HEADING, re.compile(r"^## Running", re.M))
    assert "Reference-application overhead" in owed
    assert "T101" in owed
    assert "does **not** discharge" in owed or "does not discharge" in owed


def test_the_stale_absence_scanner_fires_on_a_plant() -> None:
    """The control. The scan above succeeds by finding nothing."""
    assert STALE_ABSENCE.search("The scheduler does not exist.")
    assert STALE_ABSENCE.search("so **v1 has no measured resume**.")
    assert STALE_ABSENCE.search(
        "The scheduler exists; T144's additional triggers are unwired."
    ) is None
