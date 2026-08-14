"""T197 — both Assumptions-section operator obligations, unweakened.

(1) run the enforcement point and route the environment through it;
(2) run the agent's commands inside an environment that is
filesystem-scoped, bounded, and holds no credential outliving the
session. T172 (Linux only, no degraded mode) and FR-050 are not
weakened here.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OBLIGATIONS = Path("docs/operator-obligations.md")

ENFORCEMENT = (
    "The operator can run the enforcement point and route the agent's "
    "environment through it."
)
ENVIRONMENT = (
    "filesystem-scoped, processor- and memory-bounded, and holds no "
    "credential outliving the session"
)
FR050 = "No credential that outlives a session may"
LINUX_ONLY = "Linux only, no degraded mode"


def _collapsed(text: str) -> str:
    text = re.sub(r"[*_`]+", "", text)
    return re.sub(r"\s+", " ", text)


def test_the_obligations_file_exists_and_states_both() -> None:
    path = REPO / OBLIGATIONS
    assert path.is_file(), f"{OBLIGATIONS} is gone; it was the T197 record"
    collapsed = _collapsed(path.read_text())
    assert _collapsed(ENFORCEMENT) in collapsed, (
        "operator-obligations.md dropped the enforcement-point obligation"
    )
    assert _collapsed(ENVIRONMENT) in collapsed, (
        "operator-obligations.md dropped the execution-environment obligation"
    )


def test_fr050_and_od17_are_not_weakened() -> None:
    collapsed = _collapsed((REPO / OBLIGATIONS).read_text())
    assert FR050 in collapsed, (
        "operator-obligations.md no longer states FR-050's no-credential-"
        "outliving-the-session clause"
    )
    assert "FR-050" in collapsed
    assert LINUX_ONLY in collapsed, (
        "operator-obligations.md dropped OD-17's Linux-only, no-degraded-mode "
        "constraint"
    )
    assert "OD-17" in collapsed
