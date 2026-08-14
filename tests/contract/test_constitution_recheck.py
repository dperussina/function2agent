"""T204 — constitution re-check against all eight principles after implementation.

Held, Held with a named deviation, or Unmet. An unmet residual is not
quietly marked held. The constitution is not amended. There is no ninth
principle.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RECHECK = Path("docs/constitution-recheck.md")

EIGHT_PRINCIPLES = (
    "Contract-Derived Verification",
    "Topology Encodes Protocol",
    "Default to the Loop",
    "Structural Safety Boundaries",
    "Two-Tier Provider Abstraction",
    "Observability Is a Prerequisite",
    "Test-First and Fixture-Backed",
    "Versioned Artifacts, Earned Complexity",
)

#: Principle II's no-graph deviation is already accepted. The re-check
#: must still name it rather than absorb it into a bare Held.
PRINCIPLE_II_DEVIATION = "emits no graph"

#: Principle VI is Unmet: T193 / T194 open, retry-versus-repair undefined.
UNMET_PRINCIPLE = "Observability Is a Prerequisite"

CURRENT_HEAD_MARKERS = (
    "OD-36 is discharged",
    "T214",
    "Result",
    "T058",
    "PARTIAL",
    "5.14",
    "DERIVED NOT TESTED",
    "T205",
    "deferred",
    "E13 never ran",
    "FR-052",
    "T172",
    "Linux only",
)

STALE_REPORT_EXIT = re.compile(
    r"main\.py is report\+exit"
    r"|no agent loop is started and no surface is bound"
    r"|OD-36 (?:is )?(?:still )?(?:open|unmet|not discharged)",
    re.I,
)

STALE_REFUSAL = re.compile(
    r"planted-off"
    r"|superseded"
    r"|OD-36 is discharged"
    r"|binds a serving surface",
    re.I,
)

#: Em-dash heading only. A table row's next-cell Held is not this
#: principle's disposition; matching that would make the scan fail
#: the document it exists to protect.
UNMET_AS_HELD = re.compile(
    r"Observability Is a Prerequisite\s+[—-]\s+Held\b",
    re.I,
)


def _collapsed(text: str) -> str:
    text = re.sub(r"[*_`~]+", "", text)
    return re.sub(r"\s+", " ", text)


def unmet_marked_held(text: str) -> list[str]:
    collapsed = _collapsed(text)
    return [
        collapsed[max(0, match.start() - 48) : match.end() + 48]
        for match in UNMET_AS_HELD.finditer(collapsed)
    ]


def stale_report_exit_hits(text: str) -> list[str]:
    collapsed = _collapsed(text)
    hits: list[str] = []
    for match in STALE_REPORT_EXIT.finditer(collapsed):
        window = collapsed[max(0, match.start() - 80) : match.end() + 80]
        if STALE_REFUSAL.search(window):
            continue
        hits.append(collapsed[max(0, match.start() - 48) : match.end() + 48])
    return hits


def test_the_recheck_exists_and_names_all_eight_principles() -> None:
    path = REPO / RECHECK
    assert path.is_file(), f"{RECHECK} is gone; it was the T204 record"
    collapsed = _collapsed(path.read_text())
    missing = [name for name in EIGHT_PRINCIPLES if name not in collapsed]
    assert missing == [], (
        "constitution-recheck.md dropped principle(s):\n  "
        + "\n  ".join(missing)
    )
    assert len(EIGHT_PRINCIPLES) == 8, (
        "EIGHT_PRINCIPLES is not the eight. A ninth is invented; a "
        "shorter list drops one."
    )
    assert "ninth" not in collapsed or "no ninth" in collapsed


def test_principle_ii_names_the_accepted_no_graph_deviation() -> None:
    collapsed = _collapsed((REPO / RECHECK).read_text())
    assert PRINCIPLE_II_DEVIATION in collapsed, (
        "constitution-recheck.md dropped Principle II's accepted "
        "no-graph deviation"
    )
    assert "Held with a named deviation" in collapsed


def test_principle_vi_is_unmet_and_not_marked_held() -> None:
    text = (REPO / RECHECK).read_text()
    collapsed = _collapsed(text)
    assert UNMET_PRINCIPLE in collapsed
    assert "Unmet" in collapsed
    hits = unmet_marked_held(text)
    assert hits == [], (
        "constitution-recheck.md marks the unmet principle as held:\n  "
        + "\n  ".join(hits)
    )
    assert "T195" in text
    assert "undefined" in collapsed


def test_current_head_residuals_are_named() -> None:
    """Use current HEAD, not stale main.py-is-report+exit text."""
    text = (REPO / RECHECK).read_text()
    collapsed = _collapsed(text)
    missing = [marker for marker in CURRENT_HEAD_MARKERS if marker not in collapsed]
    assert missing == [], (
        "constitution-recheck.md dropped current-HEAD marker(s):\n  "
        + "\n  ".join(missing)
    )
    stale = stale_report_exit_hits(text)
    assert stale == [], (
        "constitution-recheck.md still treats main.py as report+exit "
        "or OD-36 as undischarged:\n  " + "\n  ".join(stale)
    )


def test_u44_u21_t205_e13_remain_residuals() -> None:
    collapsed = _collapsed((REPO / RECHECK).read_text())
    assert "U-44 remains open" in collapsed or "U-44 is open" in collapsed
    assert "U-21 remains open" in collapsed or "U-21 is open" in collapsed
    assert "T205 remains deferred" in collapsed or "T205 is deferred" in collapsed
    assert "E13 never ran" in collapsed


def test_the_unmet_as_held_scanner_fires_on_a_plant() -> None:
    """The control. The scan above succeeds by finding nothing."""
    assert unmet_marked_held(
        "VI. Observability Is a Prerequisite — Held\n"
    )
    assert not unmet_marked_held(
        "VI. Observability Is a Prerequisite — Unmet\n"
    )
    assert not unmet_marked_held(
        "Observability Is a Prerequisite | Unmet | VII | Held\n"
    )
    assert stale_report_exit_hits(
        "src/runtime/main.py is report+exit; OD-36 is not discharged.\n"
    )
    assert not stale_report_exit_hits(
        "OD-36 is discharged (T215). The runtime binds a serving surface.\n"
    )
