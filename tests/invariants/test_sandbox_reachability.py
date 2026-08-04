"""INV-003 — no HTTP client reachable from the sandbox can name any address but
the enforcement point (FR-014).

**What this checks and what it does not.** The real guarantee is topological:
one route, no `NET_ADMIN`, no raw sockets, a static hosts entry, and the
enforcement point's configuration in a different mount namespace
(`contracts/egress-policy.md`, "Reachability of the enforcement point itself").
That is proved by the integration battery against a running container, not by a
static scan.

What *this* invariant catches is the cheap, common regression the topology
cannot catch on its own: a literal hostname or URL appearing in sandbox-side
source, which is how a second destination gets introduced — and, under **OD-12**,
how the drift scheduler becomes a second continuous path to the target. It runs
in milliseconds and it fires on the edit, not on the deployment.

Both are needed. Neither substitutes for the other, and this file says so
rather than letting a passing static scan read as a reachability proof.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent.parent

# Everything that runs inside the sandbox, plus the scheduler, which OD-12
# routes through the same enforcement point precisely so that FR-014 is true of
# the system and not only of the sandbox.
SANDBOX_ROOTS = (
    REPO / "src" / "sandbox",
    REPO / "src" / "runtime" / "drift",
)

# The enforcement point is named by configuration, never by a literal. These
# are the only literals a sandbox-side module may contain.
PERMITTED_LITERALS = {
    "127.0.0.1",
    "localhost",
    "http://enforcement-point",
    "enforcement-point",
}

URL_PATTERN = re.compile(r"""["'](https?://[^"'\s]+)["']""")
HOST_PATTERN = re.compile(
    r"""["']([a-z0-9][a-z0-9.-]*\.(?:com|net|org|io|ai|dev|internal|local))["']""",
    re.IGNORECASE,
)


def _sandbox_sources() -> list[Path]:
    found: list[Path] = []
    for root in SANDBOX_ROOTS:
        if root.is_dir():
            found.extend(sorted(root.rglob("*.py")))
    return found


def literal_destinations(paths: list[Path]) -> list[str]:
    offenders: list[str] = []
    for path in paths:
        text = path.read_text()
        for match in URL_PATTERN.finditer(text):
            value = match.group(1)
            if not any(value.startswith(ok) for ok in PERMITTED_LITERALS):
                offenders.append(f"{path.name}: {value}")
        for match in HOST_PATTERN.finditer(text):
            value = match.group(1)
            if value not in PERMITTED_LITERALS:
                offenders.append(f"{path.name}: {value}")
    return offenders


def test_no_sandbox_module_names_a_destination() -> None:
    assert literal_destinations(_sandbox_sources()) == []


def test_the_scanner_fires_on_a_planted_destination(tmp_path: Path) -> None:
    """The removal proof. A scanner over an empty tree passes vacuously."""
    planted = tmp_path / "client.py"
    planted.write_text(
        'BASE = "https://api.vendor.example.com/v1"\n'
        "def fetch():\n    return BASE\n"
    )
    offenders = literal_destinations([planted])
    assert offenders, "the scanner did not report a planted destination"
    assert "api.vendor.example.com" in offenders[0]


def test_the_scanner_permits_the_enforcement_point(tmp_path: Path) -> None:
    permitted = tmp_path / "client.py"
    permitted.write_text('BASE = "http://enforcement-point:8080"\n')
    assert literal_destinations([permitted]) == []


def test_the_scan_reports_whether_it_covered_anything() -> None:
    """Records that the invariant is currently *true and vacuous*.

    `src/sandbox/` and `src/runtime/drift/` are directories in T001's tree with
    no modules in them yet, so the scan above passes over an empty set. That is
    a different fact from passing over a populated one, and a reader should not
    have to infer which. When the first sandbox-side module lands this stops
    being a skip and the invariant starts carrying weight.
    """
    sources = _sandbox_sources()
    if not sources:
        pytest.skip(
            "vacuous: no sandbox-side modules exist yet, so INV-003's static "
            "arm scans nothing. The topological arm (one route, no NET_ADMIN, "
            "no raw sockets) is what carries FR-014 until then."
        )
    assert sources
