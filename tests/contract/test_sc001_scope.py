"""T203 — SC-001 reports the reference-app size and the one codegraph datapoint.

U-21 stays open. No node count is invented for the reference application.
docs/sc001-scope.md is the place SC-001 reports cite.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCOPE = Path("docs/sc001-scope.md")

#: T116 done-note figures. Quoted, not re-derived. A derived node count
#: from these lines is the failure U-21 exists to prevent.
T116_FIGURES = (
    "3 application files",
    "606 lines",
    "442 non-blank non-comment lines",
    "32",
    "11 seeded parts",
    "44 seeded shipments",
    "5 served operations",
    "4 questions",
)

#: The one measured codegraph datapoint — not the reference app.
ADK_DATAPOINT = (
    "1,867 files",
    "48,154 nodes",
    "149,714 edges",
)

#: Surfaces that report SC-001 as a criterion or a window. spec.md
#: defines the criterion and is not amended. Dated findings stay off.
REPORT_SURFACES = (
    Path("docs/sc001-scope.md"),
    Path("src/analysis/timing.py"),
    Path("tests/fixtures/reference-app/README.md"),
    Path("tests/batteries/results/sc001-first-answer.json"),
    Path("specs/002-spec-aware-agent-runtime/quickstart.md"),
)

SIZE_MARKERS = (
    "606",
    "442",
    "codegraph_nodes",
)

INVENTED_REFAPP_NODES = re.compile(
    r"(?:reference application|this application|reference-app).{0,80}"
    r"(?:codegraph[_ ]nodes|node count)\s*(?:is|=|:)?\s*\d+"
    r"|\b(?:codegraph_nodes|node count)\s*(?:is|=|:)\s*\d+",
    re.I | re.S,
)

U21_CLOSED = re.compile(
    r"U-21.{0,40}(?:is\s+)?(?<!un)(?:closed|discharged|resolved|tested|met)\b"
    r"|(?:closed|discharged|resolved)\s+U-21",
    re.I | re.S,
)

#: Only the gap sentence and the audit's own description. "untested" and
#: "extrapolates nothing" sit next to both the open claim and a planted
#: closed claim, so they cannot be the refusal.
REFUSAL = re.compile(
    r"U-21 is \*\*open\*\*"
    r"|U-21 is open"
    r"|U-21 stays open"
    r"|fails that test"
    r"|claims U-21 closed",
    re.I,
)


def _collapsed(text: str) -> str:
    # Emphasis only. Underscores are identifiers (`codegraph_nodes`).
    text = re.sub(r"[*`~]+", "", text)
    return re.sub(r"\s+", " ", text)


def invented_node_counts(text: str) -> list[str]:
    collapsed = _collapsed(text)
    hits: list[str] = []
    for match in INVENTED_REFAPP_NODES.finditer(collapsed):
        snippet = collapsed[max(0, match.start() - 48) : match.end() + 48]
        # A nearby `null` is the gap sentence. A digit in the match is
        # an invented count; do not let the gap sentence hide it.
        if not re.search(r"\d", match.group(0)):
            continue
        hits.append(snippet)
    return hits


def u21_closed_hits(text: str) -> list[str]:
    collapsed = _collapsed(text)
    hits: list[str] = []
    for match in U21_CLOSED.finditer(collapsed):
        window = collapsed[max(0, match.start() - 80) : match.end() + 80]
        if REFUSAL.search(window):
            continue
        hits.append(collapsed[max(0, match.start() - 48) : match.end() + 48])
    return hits


def _carries_size_or_cites_scope(text: str) -> bool:
    if "docs/sc001-scope.md" in text:
        return True
    collapsed = _collapsed(text)
    return all(marker in collapsed for marker in SIZE_MARKERS)


def test_the_scope_file_quotes_the_t116_figures_and_the_gap() -> None:
    path = REPO / SCOPE
    assert path.is_file(), f"{SCOPE} is gone; it was the T203 record"
    text = path.read_text()
    collapsed = _collapsed(text)
    missing = [figure for figure in T116_FIGURES if figure not in collapsed]
    assert missing == [], (
        "sc001-scope.md does not quote T116 figure(s):\n  "
        + "\n  ".join(missing)
    )
    assert "null" in collapsed
    assert "no node count for this application has ever been taken" in collapsed
    assert "not a scale datapoint" in collapsed


def test_the_scope_file_records_the_one_codegraph_datapoint() -> None:
    collapsed = _collapsed((REPO / SCOPE).read_text())
    missing = [figure for figure in ADK_DATAPOINT if figure not in collapsed]
    assert missing == [], (
        "sc001-scope.md does not record the adk-python datapoint:\n  "
        + "\n  ".join(missing)
    )
    assert "adk-python" in collapsed
    assert "U-21 is open" in collapsed or "U-21 is **open**" in (
        REPO / SCOPE
    ).read_text()


def test_the_scope_file_does_not_invent_a_reference_app_node_count() -> None:
    hits = invented_node_counts((REPO / SCOPE).read_text())
    assert hits == [], (
        "sc001-scope.md invents a node count for the reference app:\n  "
        + "\n  ".join(hits)
    )


def test_u21_is_not_claimed_closed() -> None:
    hits = u21_closed_hits((REPO / SCOPE).read_text())
    assert hits == [], (
        "sc001-scope.md claims U-21 closed:\n  " + "\n  ".join(hits)
    )


def test_sc001_reports_cite_the_scope_or_carry_the_figures() -> None:
    """A report that names SC-001 without the size/gap, and without
    pointing here, is the failure T203 exists to catch."""
    missing: list[str] = []
    for relative in REPORT_SURFACES:
        path = REPO / relative
        assert path.is_file(), f"{relative} is gone; it was an SC-001 report"
        if not _carries_size_or_cites_scope(path.read_text()):
            missing.append(relative.as_posix())
    assert missing == [], (
        "SC-001 report(s) carry neither docs/sc001-scope.md nor the "
        "T116 size/gap figures:\n  " + "\n  ".join(missing)
    )


def test_the_node_count_and_u21_scanners_fire_on_a_plant() -> None:
    """The control. The scans above succeed by finding nothing."""
    assert invented_node_counts(
        "The reference application codegraph_nodes is 1842.\n"
    )
    assert not invented_node_counts(
        "codegraph_nodes are deliberately null — never taken.\n"
    )
    assert u21_closed_hits("U-21 is closed; the scale claim is tested.\n")
    assert not u21_closed_hits(
        "U-21 is **open**. The scale claim is untested and extrapolates "
        "nothing.\n"
    )
