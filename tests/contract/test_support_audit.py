"""T190 — language / framework / target-shape support, fixture-backed or not.

FR-053, SC-027. A language, a framework or a target shape is supported
only where a committed fixture and an asserted expected output exist.
Anything else is unsupported rather than best-effort.

T172 already walked the Linux-only platform statement. This file does
not retarget it. Implementation languages (Python 3.12, Go at the
enforcement point) are how the product is built, not a customer-language
support claim.

Dated records stay off the walk (frozen-sites, same ruling as T172).
"""

from __future__ import annotations

import re
from pathlib import Path

from src.analysis.admission import SUPPORTED_SPECIFICATION_SHAPES

REPO = Path(__file__).resolve().parents[2]

AUDIT = Path("docs/support-audit.md")

REQUIRED_SURFACES = (
    Path("README.md"),
    Path("docs/spec-kit-workflow.md"),
    Path("deploy/compose/compose.yaml"),
    Path("src/supervisor/main.py"),
    Path("src/runtime/main.py"),
    Path("src/analysis/admission.py"),
    Path("specs/002-spec-aware-agent-runtime/quickstart.md"),
    Path("specs/002-spec-aware-agent-runtime/plan.md"),
    Path("pyproject.toml"),
)

LIVE_TREES = (
    Path("README.md"),
    Path("docs"),
    Path("deploy"),
    Path("src/supervisor/main.py"),
    Path("src/runtime/main.py"),
    Path("src/analysis/admission.py"),
    Path("specs/002-spec-aware-agent-runtime/quickstart.md"),
    Path("specs/002-spec-aware-agent-runtime/plan.md"),
    Path("pyproject.toml"),
)

_LIVE_SUFFIXES = {".py", ".md", ".toml", ".yml", ".yaml"}

#: Names that are never fixture-backed in v1. A live sentence that
#: claims support for one of these, without the FR-053 refusal, fails.
#: Python is fixture-backed (analyzer) and is not on this list.
#: ``served_operation_set`` is fixture-backed and is not on this list.
UNSUPPORTED_NAMES = (
    "TypeScript",
    "FastAPI",
    "Flask",
    "Django",
    "gRPC",
    "GraphQL",
    "OpenAPI",
    "JSON Schema",
    "WSDL",
    "Ruby",
    "PHP",
    "Java",
    "Kotlin",
    "Swift",
    "Rust",
)

_UNSUPPORTED_ALT = "|".join(re.escape(name) for name in UNSUPPORTED_NAMES)

SUPPORT_OFFER = re.compile(
    rf"""
    \bsupports?\s+(?:the\s+)?(?:language\s+|framework\s+)?({_UNSUPPORTED_ALT})
    | \b({_UNSUPPORTED_ALT})\s+is\s+supported\b
    | \bsupported\s+(?:language|framework|target[ ]shape)\s*[:=]\s*({_UNSUPPORTED_ALT})
    """,
    re.I | re.X,
)

REFUSAL = re.compile(
    r"unsupported"
    r"|not[ ]supported"
    r"|rather[ ]than[ ]best-effort"
    r"|no[ ]committed[ ]fixture"
    r"|not[ ]a[ ]framework"
    r"|not[ ]a[ ]support[ ]claim"
    r"|FR-053"
    r"|SC-027"
    r"|none[ ]found"
    r"|OD-15",
    re.I,
)

#: Fixture-backed support we may state. Inventing a row without both
#: files is the dishonest close this audit exists to refuse.
FIXTURE_BACKED = (
    (
        "language",
        "hand-written Python",
        Path("tests/fixtures/analyzer/inventory-service/service.py"),
        Path("tests/fixtures/analyzer/inventory-service/expected.json"),
    ),
    (
        "language",
        "hand-written Python (negative)",
        Path("tests/fixtures/analyzer/no-derivable-checks/opaque.py"),
        Path("tests/fixtures/analyzer/no-derivable-checks/expected.json"),
    ),
    (
        "target_shape",
        "served_operation_set",
        Path("tests/fixtures/reference-app/served_operations.json"),
        Path("tests/fixtures/admission/published-reference-app/expected.json"),
    ),
    (
        "target_shape",
        "HTTP reference application",
        Path("tests/fixtures/reference-app/app.py"),
        Path("tests/fixtures/reference-app/questions.json"),
    ),
)


def _collapsed(text: str) -> str:
    text = re.sub(r"[*_`~]+", "", text)
    return re.sub(r"\s+", " ", text)


def support_offers(text: str) -> list[str]:
    """Support claims for a name that has no fixture, without the FR-053 refusal."""
    collapsed = _collapsed(text)
    hits: list[str] = []
    for match in SUPPORT_OFFER.finditer(collapsed):
        start = max(0, match.start() - 160)
        end = min(len(collapsed), match.end() + 160)
        window = collapsed[start:end]
        if REFUSAL.search(window):
            continue
        snippet = collapsed[max(0, match.start() - 48) : match.end() + 48]
        hits.append(snippet)
    return hits


def live_files() -> list[Path]:
    found: list[Path] = []
    for root in LIVE_TREES:
        path = REPO / root
        if path.is_file():
            found.append(path)
            continue
        if not path.is_dir():
            continue
        for child in sorted(path.rglob("*")):
            if not child.is_file():
                continue
            if child.suffix in _LIVE_SUFFIXES or child.name.endswith("Dockerfile"):
                found.append(child)
    return found


def test_the_audit_file_names_every_required_surface() -> None:
    text = (REPO / AUDIT).read_text()
    missing = [
        relative.as_posix()
        for relative in REQUIRED_SURFACES
        if relative.as_posix() not in text
    ]
    assert missing == [], (
        "support-audit.md does not name required surface(s):\n  "
        + "\n  ".join(missing)
    )


def test_every_required_surface_exists_and_is_walked() -> None:
    assert len(REQUIRED_SURFACES) >= 9, (
        "REQUIRED_SURFACES shrank below the set T190 walked. A shorter "
        "list is the required-surface test passing over nothing."
    )
    walked = {path.relative_to(REPO) for path in live_files()}
    missing: list[str] = []
    for relative in REQUIRED_SURFACES:
        path = REPO / relative
        assert path.is_file(), f"{relative} is gone; it was a support surface"
        if relative not in walked:
            missing.append(relative.as_posix())
    assert missing == [], (
        "required support surface(s) are not on the walk:\n  "
        + "\n  ".join(missing)
    )


def test_live_trees_do_not_claim_unsupported_names_as_supported() -> None:
    """SC-027: zero support claims without a fixture."""
    offenders: list[str] = []
    scanned = 0
    for path in live_files():
        scanned += 1
        for snippet in support_offers(path.read_text()):
            offenders.append(f"{path.relative_to(REPO)}: …{snippet}…")
    assert scanned >= 9, (
        f"the support-audit walk covered {scanned} files, which is fewer "
        "than the live trees have ever held. It is passing because it "
        "read almost nothing. Check LIVE_TREES."
    )
    assert offenders == [], (
        "live surface(s) claim support for a language, framework or "
        "target shape with no committed fixture (FR-053, SC-027):\n  "
        + "\n  ".join(offenders)
        + "\nRecording 'no fixture, therefore not a support claim we may "
        "make' is the honest close. Do not invent a language as supported "
        "to close a gap."
    )


def test_the_support_offer_scanner_fires_on_a_planted_claim() -> None:
    """The control. The scan above succeeds by finding nothing."""
    for planted in (
        "the product supports TypeScript.\n",
        "FastAPI is supported.\n",
        "the product supports gRPC.\n",
        "supported language: OpenAPI\n",
        "supports Django as a target framework\n",
    ):
        assert support_offers(planted), planted
    for refused in (
        "OpenAPI, JSON Schema, gRPC reflection and WSDL are unsupported "
        "rather than best-effort (FR-053).\n",
        "There is no TypeScript fixture, so TypeScript is unsupported "
        "rather than best-effort.\n",
        "Not a framework. No FastAPI, no decorators (FR-053).\n",
        "RPC / gRPC as a target shape does not, so it is not a support "
        "claim we may make.\n",
    ):
        assert support_offers(refused) == [], refused


def test_every_fixture_backed_entry_has_a_committed_fixture_and_expected_output() -> None:
    """Do not invent a language or framework as supported to close a gap."""
    assert len(FIXTURE_BACKED) >= 4, (
        "FIXTURE_BACKED shrank below the set that had a fixture at T190. "
        "A shorter list is the catalog passing over nothing."
    )
    kinds = {row[0] for row in FIXTURE_BACKED}
    assert "framework" not in kinds, (
        "a framework row entered FIXTURE_BACKED. No framework fixture "
        "exists; adding one here invents support."
    )
    missing: list[str] = []
    for kind, name, fixture, expected in FIXTURE_BACKED:
        if not (REPO / fixture).is_file():
            missing.append(f"{name} ({kind}): fixture {fixture} is gone")
        if not (REPO / expected).is_file():
            missing.append(f"{name} ({kind}): expected {expected} is gone")
    assert missing == [], (
        "fixture-backed support with no file on disk:\n  "
        + "\n  ".join(missing)
        + "\nNo fixture, therefore not a support claim we may make."
    )


def test_supported_specification_shapes_are_exactly_the_fixture_backed_target() -> None:
    """Admission's declaration cannot grow past the fixture catalog."""
    assert SUPPORTED_SPECIFICATION_SHAPES == ("served_operation_set",), (
        "SUPPORTED_SPECIFICATION_SHAPES changed. A new member is a "
        "target-shape support claim and needs a committed fixture and "
        "asserted expected output in the same change (FR-053). Do not "
        "invent OpenAPI or gRPC as supported to close a gap."
    )
    names = {row[1] for row in FIXTURE_BACKED}
    assert "served_operation_set" in names


def test_http_rpc_is_not_read_as_grpc_support() -> None:
    """D-01 names the invocation convention; that is not a gRPC support claim."""
    readme = (REPO / "README.md").read_text()
    assert "HTTP/RPC" in readme
    assert support_offers(readme) == []


def test_dated_records_are_outside_the_walk() -> None:
    walked = [p.relative_to(REPO).as_posix() for p in live_files()]
    leaked = [
        path
        for path in walked
        if "/findings/" in path
        or path.startswith("research/")
        or "/harness/" in path
        or path.startswith("tests/")
        or "/judge/" in path
    ]
    assert leaked == [], (
        "the support-audit walk reached a dated record or a sibling tree:\n  "
        + "\n  ".join(leaked)
    )
    assert walked, "the walk is empty; dated-record exclusion is free"
