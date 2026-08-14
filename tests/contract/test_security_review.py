"""T202 — enforcement-point review against its four named failure classes.

Parser differential, request smuggling, ambiguous framing, and the
confused-deputy composition where the proxy holds the target credential
and stacks with U-44. A review, not a new mechanism. U-44 stays open.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
REVIEW = Path("docs/security-review.md")

#: The four classes are the population. A silent shrink is the review
#: passing over nothing. A fifth is not added to look complete.
REQUIRED_CLASSES = (
    "parser differential",
    "request smuggling",
    "ambiguous framing",
    "confused-deputy composition",
)

REQUIRED_SURFACES = (
    Path("src/proxy/form.go"),
    Path("src/proxy/framing_test.go"),
    Path("src/proxy/method.go"),
    Path("src/proxy/reoriginate.go"),
    Path("src/proxy/capability.go"),
    Path("src/proxy/pipeline.go"),
    Path("src/analysis/deputy_inspection.py"),
    Path("tests/contract/test_deputy_inspection.py"),
)

U44_CLOSED = re.compile(
    r"U-44.{0,40}(?:is\s+)?(?:closed|discharged|resolved|met)\b"
    r"|(?:closed|discharged|resolved)\s+U-44",
    re.I | re.S,
)

SECURE_VERDICT = re.compile(
    r"\benforcement point is secure\b"
    r"|\breview verdict:\s*secure\b"
    r"|\bmarked secure\b",
    re.I,
)

REFUSAL = re.compile(
    r"U-44 is \*\*open\*\*"
    r"|U-44 stays open"
    r"|not discharged"
    r"|not declared \*\*secure\*\*"
    r"|no class is marked closed",
    re.I,
)


def _collapsed(text: str) -> str:
    text = re.sub(r"[*_`~]+", "", text)
    return re.sub(r"\s+", " ", text)


def u44_closed_hits(text: str) -> list[str]:
    collapsed = _collapsed(text)
    hits: list[str] = []
    for match in U44_CLOSED.finditer(collapsed):
        window = collapsed[max(0, match.start() - 80) : match.end() + 80]
        if REFUSAL.search(window):
            continue
        hits.append(collapsed[max(0, match.start() - 48) : match.end() + 48])
    return hits


def secure_verdict_hits(text: str) -> list[str]:
    collapsed = _collapsed(text)
    hits: list[str] = []
    for match in SECURE_VERDICT.finditer(collapsed):
        window = collapsed[max(0, match.start() - 80) : match.end() + 80]
        if REFUSAL.search(window):
            continue
        hits.append(collapsed[max(0, match.start() - 48) : match.end() + 48])
    return hits


def test_the_review_exists_and_names_all_four_classes() -> None:
    path = REPO / REVIEW
    assert path.is_file(), f"{REVIEW} is gone; it was the T202 record"
    collapsed = _collapsed(path.read_text()).lower()
    missing = [name for name in REQUIRED_CLASSES if name not in collapsed]
    assert missing == [], (
        "security-review.md dropped named failure class(es):\n  "
        + "\n  ".join(missing)
    )
    assert len(REQUIRED_CLASSES) == 4, (
        "REQUIRED_CLASSES is not the four named classes. A longer list "
        "invents a fifth; a shorter list drops one."
    )


def test_every_required_surface_exists_and_is_named() -> None:
    text = (REPO / REVIEW).read_text()
    missing = [
        relative.as_posix()
        for relative in REQUIRED_SURFACES
        if relative.as_posix() not in text
    ]
    assert missing == [], (
        "security-review.md does not name required surface(s):\n  "
        + "\n  ".join(missing)
    )
    for relative in REQUIRED_SURFACES:
        assert (REPO / relative).is_file(), (
            f"{relative} is gone; it was an enforcement-point surface"
        )


def test_u44_is_not_claimed_closed() -> None:
    text = (REPO / REVIEW).read_text()
    hits = u44_closed_hits(text)
    assert hits == [], (
        "security-review.md claims U-44 closed:\n  " + "\n  ".join(hits)
    )
    assert "U-44 is **open**" in text or "U-44 is open" in _collapsed(text)


def test_the_review_does_not_invent_a_secure_verdict() -> None:
    hits = secure_verdict_hits((REPO / REVIEW).read_text())
    assert hits == [], (
        "security-review.md invents a green secure verdict:\n  "
        + "\n  ".join(hits)
    )


def test_the_class_and_u44_scanners_fire_on_a_plant() -> None:
    """The control. The scans above succeed by finding nothing."""
    assert u44_closed_hits("U-44 is closed and the egress guarantee holds.\n")
    assert not u44_closed_hits("U-44 is **open**. It is not discharged.\n")
    assert secure_verdict_hits("The enforcement point is secure.\n")
    assert not secure_verdict_hits(
        "The enforcement point is not declared **secure**.\n"
    )
