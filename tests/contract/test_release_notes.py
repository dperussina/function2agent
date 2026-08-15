"""Pin the 0.1.0 release note so it cannot silently claim more than shipped.

Dropping T205-deferred / NOT TESTED, claiming a live vendor SDK, or
claiming writes, fails. Follows T189/T197: the scan succeeds by finding
nothing; a plant-firing control proves the scan is not vacuous.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RELEASE_NOTE = Path("docs/release-0.1.0.md")

T205_DEFERRED = "T205 is deferred for this release; the matrix was not built."
#: Preflight's own pairing, quoted rather than paraphrased. Weakening
#: this sentence is the plant that claims a tested floor.
KERNEL_WORDING = (
    "DERIVED from documented feature introduction and NOT TESTED on that "
    "kernel; every run to date was on 6.12 or 6.17"
)
NOT_TESTED = "NOT TESTED"
DERIVED = "DERIVED"
KERNEL_FLOOR = "5.14"
LINUX_ONLY = "Linux only"
PRODUCT_FLOOR = "1e40936"
VERSION = "0.1.0"

LIVE_VENDOR = re.compile(
    r"vendor[ ]SDK[ ]is[ ]in[ ]requirements\.lock"
    r"|live[ ]vendor[ ](?:SDK|call|transport)"
    r"|ProviderDriver\.call[ ]succeeds",
    re.I,
)

WRITES_ENABLED = re.compile(
    r"writes[ ]are[ ]enabled"
    r"|v1[ ]performs[ ]writes"
    r"|write[ ]ships",
    re.I,
)

VENDOR_REFUSAL = re.compile(
    r"not[ ]in[ ](?:the[ ])?lock"
    r"|TransportUnavailableError"
    r"|T058"
    r"|no[ ]vendor[ ]SDK",
    re.I,
)

WRITES_REFUSAL = re.compile(
    r"blocked"
    r"|OD-10"
    r"|read-only"
    r"|read[ ]only"
    r"|no[ ]writes"
    r"|denies",
    re.I,
)


def _collapsed(text: str) -> str:
    text = re.sub(r"[*_`~]+", "", text)
    return re.sub(r"\s+", " ", text)


def _window(collapsed: str, start: int, end: int, radius: int = 220) -> str:
    lo = max(0, start - radius)
    hi = min(len(collapsed), end + radius)
    return collapsed[lo:hi]


def live_vendor_hits(text: str) -> list[str]:
    collapsed = _collapsed(text)
    hits: list[str] = []
    for match in LIVE_VENDOR.finditer(collapsed):
        window = _window(collapsed, match.start(), match.end())
        if VENDOR_REFUSAL.search(window):
            continue
        snippet = collapsed[max(0, match.start() - 48) : match.end() + 48]
        hits.append(snippet)
    return hits


def writes_enabled_hits(text: str) -> list[str]:
    collapsed = _collapsed(text)
    hits: list[str] = []
    for match in WRITES_ENABLED.finditer(collapsed):
        window = _window(collapsed, match.start(), match.end())
        if WRITES_REFUSAL.search(window):
            continue
        snippet = collapsed[max(0, match.start() - 48) : match.end() + 48]
        hits.append(snippet)
    return hits


def test_the_release_note_exists_and_names_the_cut() -> None:
    path = REPO / RELEASE_NOTE
    assert path.is_file(), f"{RELEASE_NOTE} is gone; it was the 0.1.0 record"
    collapsed = _collapsed(path.read_text())
    assert VERSION in collapsed
    assert PRODUCT_FLOOR in collapsed
    assert LINUX_ONLY in collapsed
    assert KERNEL_FLOOR in collapsed
    assert DERIVED in collapsed


def test_t205_stays_deferred_and_not_tested_is_not_dropped() -> None:
    text = (REPO / RELEASE_NOTE).read_text()
    collapsed = _collapsed(text)
    assert T205_DEFERRED in collapsed, (
        "release-0.1.0.md dropped the T205 deferral; ticking the box "
        "or deleting the sentence would claim the matrix ran"
    )
    assert KERNEL_WORDING in collapsed, (
        "release-0.1.0.md dropped or weakened the preflight pairing; "
        "5.14 would then read as a tested floor"
    )
    assert NOT_TESTED in collapsed, (
        "release-0.1.0.md dropped NOT TESTED; 5.14 would then read as "
        "a tested floor"
    )
    assert "- [X] T205" not in text
    assert "T205 is done" not in collapsed


def test_the_note_does_not_claim_a_live_vendor_sdk_or_writes() -> None:
    text = (REPO / RELEASE_NOTE).read_text()
    vendor = live_vendor_hits(text)
    assert vendor == [], (
        "release-0.1.0.md claims a live vendor SDK:\n  "
        + "\n  ".join(vendor)
    )
    writes = writes_enabled_hits(text)
    assert writes == [], (
        "release-0.1.0.md claims writes:\n  " + "\n  ".join(writes)
    )


def test_the_release_note_scanners_fire_on_a_plant() -> None:
    """The control. The scans above succeed by finding nothing."""
    assert live_vendor_hits(
        "The live vendor SDK is in requirements.lock.\n"
    )
    assert not live_vendor_hits(
        "No vendor SDK is in requirements.lock. "
        "ProviderDriver.call raises TransportUnavailableError (T058).\n"
    )
    assert writes_enabled_hits("v1 performs writes.\n")
    assert not writes_enabled_hits(
        "Writes are blocked (OD-10). v1 is read-only.\n"
    )
    assert T205_DEFERRED in _collapsed(
        "T205 is deferred for this release; the matrix was not built.\n"
    )
    assert KERNEL_WORDING in (
        "DERIVED from documented feature introduction and NOT TESTED on that "
        "kernel; every run to date was on 6.12 or 6.17"
    )
    assert KERNEL_WORDING not in (
        "DERIVED from documented feature introduction on that kernel; "
        "every run to date was on 6.12 or 6.17"
    )
