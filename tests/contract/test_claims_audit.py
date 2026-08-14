"""T189 — four prohibited claim shapes on every live external surface.

FR-043, SC-016. Capability advantage for an application-specific tool
surface; synthesis being safer; a cost figure without basis and scope;
"provably" for effect resolution.

Two complementary checks, because each one alone is vacuous in a different
direction:

1. The named live surfaces still exist and are walked. Dropping README
   from the list would otherwise make "none found" free.
2. A contradiction scan over those same trees. A new sentence that adds
   one of the four shapes, without the FR-043 / SC-016 refusal, fails.

Dated records that correctly describe a past measurement stay off the
walk (frozen-sites ruling, same as T172). T172's Linux-only platform
statement is a different audit and is not retargeted here.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

AUDIT = Path("docs/claims-audit.md")

#: Surfaces the audit named. The list is the population, not an example:
#: a silent shrink is the required-surface test passing over nothing.
REQUIRED_SURFACES = (
    Path("README.md"),
    Path("docs/spec-kit-workflow.md"),
    Path("deploy/compose/compose.yaml"),
    Path("src/supervisor/main.py"),
    Path("src/runtime/main.py"),
    Path("specs/002-spec-aware-agent-runtime/quickstart.md"),
    Path("specs/002-spec-aware-agent-runtime/plan.md"),
)

#: Live product-and-plan trees a new prohibited sentence would land in.
#: Findings, research, harness results and tests are dated records or
#: skip reasons, not product claims, and stay off this list.
#: ``src/runtime`` is the operator entry point only: the rest of that
#: tree is not an external surface, and a sibling walk owns ``judge/``.
LIVE_TREES = (
    Path("README.md"),
    Path("docs"),
    Path("deploy"),
    Path("src/supervisor/main.py"),
    Path("src/runtime/main.py"),
    Path("specs/002-spec-aware-agent-runtime/quickstart.md"),
    Path("specs/002-spec-aware-agent-runtime/plan.md"),
)

_LIVE_SUFFIXES = {".py", ".md", ".toml", ".yml", ".yaml"}

CAPABILITY = re.compile(
    r"capability[ ]advantage"
    r"|more[ ]capable"
    r"|curated[ ]tool[ ]surface[ ](?:has[ ]a[ ]capability[ ]advantage|wins|outperforms)",
    re.I,
)

SYNTHESIS_SAFER = re.compile(
    r"synthesis[ ]is[ ]safer"
    r"|synthesi[sz]ed[ ](?:tools?|surfaces?)[ ](?:are|is)[ ]safer"
    r"|safer[ ](?:than|via|through)[ ]synthesis",
    re.I,
)

MONEY = re.compile(r"\$[0-9]")
COST_MULT = re.compile(
    r"(?:cost(?:s|ing)?|cheaper).{0,80}[0-9.]+\s*×",
    re.I | re.S,
)

#: Citations that are a cost figure's basis and scope, not a nearby
#: unrelated "measured". Bare "measured" / "basis" / "scope" are too
#: common to be a basis.
COST_BASIS = re.compile(
    r"finding[ ]\d{3}"
    r"|VERDICT\.md"
    r"|FR-005"
    r"|FR-043"
    r"|FR-049"
    r"|FR-058"
    r"|within[ ]session"
    r"|ceiling[ ]test"
    r"|unvalidated"
    r"|OD-27"
    r"|D-19"
    r"|E7[ ]measured"
    r"|replication"
    r"|dry-run",
    re.I,
)

PROVABLY = re.compile(r"provably", re.I)
EFFECT = re.compile(r"effect|read-only|read[ ]only|resolv", re.I)

#: Offers, not definitions and not refusals. Matching the prohibition
#: itself would make every surface that states SC-016 fail the scan
#: that exists to protect it.
REFUSAL = re.compile(
    r"none[ ]found"
    r"|zero[ ]claims"
    r"|zero[ ]uses"
    r"|no[ ]claim"
    r"|MUST[ ]NOT"
    r"|may[ ]not[ ]be[ ]asserted"
    r"|withdrawn"
    r"|prohibited"
    r"|not[ ]more[ ]capable"
    r"|never[ ]won"
    r"|capability[ ]claim[ ]is[ ]gone"
    r"|capability[ ]half[ ]of[ ]the[ ]thesis[ ]is[ ]not[ ]supported"
    r"|SC-016"
    r"|FR-043"
    r"|C-18",
    re.I,
)


def _collapsed(text: str) -> str:
    # Emphasis and strikeout are not part of the claim. ``**zero** uses``
    # is the SC-016 refusal; leaving the markers in would make that
    # restatement look like a use of "provably".
    text = re.sub(r"[*_`~]+", "", text)
    return re.sub(r"\s+", " ", text)


def _window(collapsed: str, start: int, end: int, radius: int = 220) -> str:
    lo = max(0, start - radius)
    hi = min(len(collapsed), end + radius)
    return collapsed[lo:hi]


def _unrefused(pattern: re.Pattern[str], collapsed: str) -> list[str]:
    hits: list[str] = []
    for match in pattern.finditer(collapsed):
        window = _window(collapsed, match.start(), match.end())
        if REFUSAL.search(window):
            continue
        snippet = collapsed[max(0, match.start() - 48) : match.end() + 48]
        hits.append(snippet)
    return hits


def capability_advantage_hits(text: str) -> list[str]:
    return _unrefused(CAPABILITY, _collapsed(text))


def synthesis_safer_hits(text: str) -> list[str]:
    return _unrefused(SYNTHESIS_SAFER, _collapsed(text))


def cost_without_basis_hits(text: str) -> list[str]:
    collapsed = _collapsed(text)
    hits: list[str] = []
    for pattern in (MONEY, COST_MULT):
        for match in pattern.finditer(collapsed):
            # Basis often follows the figure by a sentence or two
            # (README's closing spend cites VERDICT.md after the kill
            # criteria). A 220-char window made that citation look
            # absent. A planted bare ``$3.50`` still has no citation
            # in 480 chars.
            window = _window(collapsed, match.start(), match.end(), radius=480)
            if COST_BASIS.search(window) or REFUSAL.search(window):
                continue
            snippet = collapsed[max(0, match.start() - 48) : match.end() + 48]
            hits.append(snippet)
    return hits


def provably_effect_hits(text: str) -> list[str]:
    collapsed = _collapsed(text)
    hits: list[str] = []
    for match in PROVABLY.finditer(collapsed):
        window = _window(collapsed, match.start(), match.end())
        if not EFFECT.search(window):
            continue
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
    """The markdown is the record; a surface it does not name is unaudited."""
    text = (REPO / AUDIT).read_text()
    missing = [
        relative.as_posix()
        for relative in REQUIRED_SURFACES
        if relative.as_posix() not in text
    ]
    assert missing == [], (
        "claims-audit.md does not name required surface(s):\n  "
        + "\n  ".join(missing)
    )


def test_every_required_surface_exists_and_is_walked() -> None:
    """The claim cannot be deleted from a surface by deleting the surface."""
    assert len(REQUIRED_SURFACES) >= 7, (
        "REQUIRED_SURFACES shrank below the set T189 walked. A shorter "
        "list is the required-surface test passing over nothing."
    )
    walked = {path.relative_to(REPO) for path in live_files()}
    missing: list[str] = []
    for relative in REQUIRED_SURFACES:
        path = REPO / relative
        assert path.is_file(), f"{relative} is gone; it was a claims surface"
        if relative not in walked:
            missing.append(relative.as_posix())
    assert missing == [], (
        "required claims surface(s) are not on the walk:\n  "
        + "\n  ".join(missing)
    )


def test_live_trees_have_none_of_the_four_prohibited_shapes() -> None:
    """SC-016: zero of each shape, or the walk is not an audit."""
    offenders: list[str] = []
    scanned = 0
    for path in live_files():
        scanned += 1
        text = path.read_text()
        rel = path.relative_to(REPO).as_posix()
        for label, hits in (
            ("capability-advantage", capability_advantage_hits(text)),
            ("synthesis-safer", synthesis_safer_hits(text)),
            ("cost-without-basis", cost_without_basis_hits(text)),
            ("provably-effect", provably_effect_hits(text)),
        ):
            for snippet in hits:
                offenders.append(f"{rel} [{label}]: …{snippet}…")
    assert scanned >= 8, (
        f"the claims-audit walk covered {scanned} files, which is fewer "
        "than the live trees have ever held. It is passing because it "
        "read almost nothing. Check LIVE_TREES."
    )
    assert offenders == [], (
        "live surface(s) carry a prohibited claim shape (FR-043, SC-016):\n  "
        + "\n  ".join(offenders)
    )


def test_the_four_shape_scanners_fire_on_a_planted_claim() -> None:
    """The control. The scan above succeeds by finding nothing."""
    assert capability_advantage_hits(
        "The curated tool surface has a capability advantage on success rate.\n"
    )
    assert not capability_advantage_hits(
        "The capability half of the thesis is not supported and the spec "
        "may not assert it.\n"
    )
    assert not capability_advantage_hits(
        "cheaper within session and not more capable (C-18).\n"
    )
    assert synthesis_safer_hits(
        "synthesis is safer than a hand-written surface.\n"
    )
    assert not synthesis_safer_hits(
        '"synthesis is safer" may not be asserted at all (C-18).\n'
    )
    assert cost_without_basis_hits("A session costs $3.50.\n")
    assert not cost_without_basis_hits(
        "Feature spend ≈ $35.17; the two bases are in VERDICT.md.\n"
    )
    assert not cost_without_basis_hits(
        "costing 2.20× less within session (finding 012, D-19).\n"
    )
    assert provably_effect_hits(
        "the gate provably resolves every effect as a read.\n"
    )
    assert not provably_effect_hits(
        'zero uses of "provably" for effect resolution (SC-016).\n'
    )
    assert not provably_effect_hits("provably the best coffee in the office.\n")


def test_dated_records_are_outside_the_walk() -> None:
    """Frozen-sites ruling: a correctly-scoped dated record stays.

    Findings, research and harness results describe past measurements.
    They are not product claims. If one of them enters the walk, a true
    dated record starts failing as a contradiction.
    """
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
        "the claims-audit walk reached a dated record or a sibling tree:\n  "
        + "\n  ".join(leaked)
    )
    assert walked, "the walk is empty; dated-record exclusion is free"
