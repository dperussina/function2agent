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
    """Every file the scan reads, package markers included."""
    found: list[Path] = []
    for root in SANDBOX_ROOTS:
        if root.is_dir():
            found.extend(sorted(root.rglob("*.py")))
    return found


def _sandbox_modules() -> list[Path]:
    """The files that count as *coverage*, which package markers do not.

    `src/sandbox/__init__.py` is a docstring and nothing else. Counting it
    would flip the vacuity report to "covered" on the strength of a file that
    cannot contain a destination, which is a worse failure than the vacuity it
    was meant to disclose.
    """
    return [p for p in _sandbox_sources() if p.name != "__init__.py"]


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


def test_a_package_marker_does_not_count_as_coverage() -> None:
    """The vacuity report must not be satisfiable by an empty `__init__.py`.

    Both declared roots currently hold exactly one, and if those counted the
    report would read "covered" on the strength of two docstrings.
    """
    markers = [p for p in _sandbox_sources() if p.name == "__init__.py"]
    assert markers, "the roots hold no package markers; this guard is testing nothing"
    assert not set(markers) & set(_sandbox_modules())


def test_the_scanner_permits_the_enforcement_point(tmp_path: Path) -> None:
    permitted = tmp_path / "client.py"
    permitted.write_text('BASE = "http://enforcement-point:8080"\n')
    assert literal_destinations([permitted]) == []


def test_every_declared_root_exists() -> None:
    """The failure mode a vacuous scan hides: a root that moved.

    Phase 2 did not give INV-003 a subject — `src/sandbox/` still holds only its
    package marker — so the scan is still vacuous, and a vacuous scan cannot
    tell "there is nothing to find" from "I am looking in the wrong place". If
    someone renames `src/sandbox/` the scan keeps passing forever over an
    absent directory, and the invariant is *permanently* switched off with no
    signal. Asserting the roots exist is what makes that a failure.

    `src/runtime/drift/` did not exist when this check was added. It is
    declared here because OD-12 routes the drift scheduler through the same
    enforcement point, so it is in INV-003's scope the moment it is created;
    creating the directory now means the check is asserting a real path rather
    than excusing a missing one.
    """
    missing = [str(root.relative_to(REPO)) for root in SANDBOX_ROOTS
               if not root.is_dir()]
    assert not missing, (
        f"INV-003 scans {missing}, which do not exist. Either the code moved "
        "and SANDBOX_ROOTS was not updated — in which case this invariant has "
        "been passing over nothing — or the root was deleted and the "
        "declaration should go with it."
    )


def test_the_scan_reports_whether_it_covered_anything(record_property) -> None:
    """Records that the invariant is currently *true and vacuous*, loudly.

    Phase 2 added no sandbox-side module, so the scan above still passes over
    an empty set. That is a different fact from passing over a populated one,
    and a reader should not have to infer which — so the vacuity is reported in
    the terminal summary rather than as one skip line among many. When the
    first sandbox-side module lands the summary stops printing and the
    invariant starts carrying weight.
    """
    sources = _sandbox_modules()
    record_property("inv003_modules_scanned", len(sources))
    if not sources:
        import tests.conftest as conftest

        conftest.note_vacuous_invariant(
            "INV-003",
            "no sandbox-side module exists, so the static arm scans nothing. "
            "The topological arm (one route, no NET_ADMIN, no raw sockets) is "
            "what carries FR-014 until then.",
        )
        pytest.skip("vacuous: see the terminal summary")
    assert sources
