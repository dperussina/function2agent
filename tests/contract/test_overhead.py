"""T199 — T101's measured syscall-supervisor overhead, Q-09.

Quote the committed record, with its basis and scope. Do not invent a
percentage. Mechanism descriptions that already exist must not quote a
different number.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OVERHEAD = Path("docs/overhead.md")
RECORD = Path("tests/batteries/results/seccomp-overhead.json")

#: Surfaces that describe the syscall-supervisor mechanism. Dated
#: batteries, tasks notes and findings stay off this list: they are
#: records of runs, not operator-facing descriptions.
MECHANISM_SURFACES = (
    Path("src/supervisor/seccomp.py"),
    Path("src/supervisor/preflight.py"),
)

PERCENT_OVERHEAD = re.compile(
    r"(\d+(?:\.\d+)?)\s*%\s*overhead|overhead\s+(?:is|of|at)\s+(\d+(?:\.\d+)?)\s*%",
    re.I,
)
US_PER_NOTIFICATION = re.compile(
    r"(\d+(?:\.\d+)?)\s*µs/notification",
    re.I,
)


def _load_record() -> dict[str, object]:
    return json.loads((REPO / RECORD).read_text())


def _t101_rates(record: dict[str, object]) -> dict[str, str]:
    arms = record["arms"]
    assert isinstance(arms, dict)
    return {
        name: f"{arm['microseconds_per_notification']:.2f}"
        for name, arm in arms.items()
        if isinstance(arm, dict)
    }


def test_overhead_md_quotes_t101s_measured_figure() -> None:
    path = REPO / OVERHEAD
    assert path.is_file(), f"{OVERHEAD} is gone; it was the T199 record"
    text = path.read_text()
    record = _load_record()
    assert RECORD.as_posix() in text, (
        "overhead.md does not name the T101 record it is quoting"
    )
    assert record["measured_at"] in text
    environment = record["environment"]
    assert isinstance(environment, dict)
    assert environment["kernel"] in text
    rates = _t101_rates(record)
    missing = [f"{name}={rate}" for name, rate in rates.items() if rate not in text]
    assert missing == [], (
        "overhead.md does not quote T101's measured µs/notification "
        f"figure(s): {missing}"
    )
    assert "T101 did not measure a percentage. This file quotes none." in text


def test_overhead_md_does_not_invent_a_percentage() -> None:
    text = (REPO / OVERHEAD).read_text()
    hits = PERCENT_OVERHEAD.findall(text)
    assert hits == [], (
        "overhead.md quotes a percentage T101 did not measure: "
        f"{hits}"
    )


def test_mechanism_descriptions_do_not_quote_a_different_figure() -> None:
    """Existing mechanism prose quotes no competing number.

    The T101 figure lives in docs/overhead.md. seccomp.py and preflight.py
    describe the mechanism and currently quote none. A later sentence that
    installs a different µs/notification figure, or a percentage T101 did
    not measure, fails here.
    """
    record = _load_record()
    allowed = set(_t101_rates(record).values())
    offenders: list[str] = []
    for relative in MECHANISM_SURFACES:
        path = REPO / relative
        assert path.is_file(), f"{relative} is gone; it described the mechanism"
        text = path.read_text()
        rel = relative.as_posix()
        for match in PERCENT_OVERHEAD.finditer(text):
            offenders.append(f"{rel}: invented percentage {match.group(0)!r}")
        for match in US_PER_NOTIFICATION.finditer(text):
            rate = match.group(1)
            if rate not in allowed:
                offenders.append(
                    f"{rel}: µs/notification {rate} is not T101's measured figure"
                )
    assert offenders == [], (
        "mechanism description(s) quote a figure T101 did not measure:\n  "
        + "\n  ".join(offenders)
    )


def test_the_percentage_scanner_fires_on_a_plant() -> None:
    """The control. The scan above succeeds by finding nothing."""
    assert PERCENT_OVERHEAD.search("The syscall supervisor's overhead is 5%.")
    assert not PERCENT_OVERHEAD.search(
        "T101 did not measure a percentage. This file quotes none."
    )
