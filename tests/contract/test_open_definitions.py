"""T195 — retry versus repair is undefined in this specification.

FR-038 and SC-012 name the distinction. Nothing in the corpus defines
either term. This file is the register; inventing a definition to close
the gap is the failure the walk exists to catch.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
REGISTER = Path("docs/open-definitions.md")

UNDEFINED = "The distinction between a retry and a repair is undefined in this specification."

# Definition-shaped, not the gap sentence. ``a repair is undefined`` is
# the register's own wording and must not fire the scanner that protects it.
INVENTED = re.compile(
    r"\ba retry is a\b"
    r"|\ba repair is a\b"
    r"|\bretry means\b"
    r"|\brepair means\b"
    r"|\bretry is defined\b"
    r"|\brepair is defined\b",
    re.I,
)


def _collapsed(text: str) -> str:
    text = re.sub(r"[*_`]+", "", text)
    return re.sub(r"\s+", " ", text)


def invented_definitions(text: str) -> list[str]:
    collapsed = _collapsed(text)
    return [
        collapsed[max(0, match.start() - 48) : match.end() + 48]
        for match in INVENTED.finditer(collapsed)
    ]


def test_the_register_exists_and_records_the_gap() -> None:
    path = REPO / REGISTER
    assert path.is_file(), f"{REGISTER} is gone; it was the T195 register"
    text = path.read_text()
    assert UNDEFINED in text, (
        "open-definitions.md no longer records retry versus repair as "
        "undefined in this specification"
    )
    assert "FR-038" in text
    assert "SC-012" in text


def test_the_register_does_not_invent_a_retry_or_repair_definition() -> None:
    text = (REPO / REGISTER).read_text()
    hits = invented_definitions(text)
    assert hits == [], (
        "open-definitions.md invents a definition FR-038 does not supply:\n  "
        + "\n  ".join(hits)
    )


def test_the_invented_definition_scanner_fires_on_a_plant() -> None:
    """The control. The scan above succeeds by finding nothing."""
    assert invented_definitions(
        "A retry is a repeated span and a repair is a compensating write.\n"
    )
    assert not invented_definitions(
        "The distinction between a retry and a repair is undefined in this "
        "specification.\n"
    )
