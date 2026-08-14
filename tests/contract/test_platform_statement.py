"""T172 — every supported-platform surface states Linux only with no degraded mode.

**OD-17**, FR-053, SC-027. A degraded mode is a sandbox missing one of
constitution Principle IV bullet 1's terms, and the bullet's own words are
that a configuration missing any term does not satisfy it.

Two complementary checks, because each one alone is vacuous in a different
direction:

1. Every live surface that already claims a supported platform still states
   Linux only. Dropping the claim from preflight, the quickstart, or the
   README would otherwise be invisible to a scan that only looks for
   contradictions.
2. A contradiction scan over those same trees. A new sentence that adds
   ``or macOS``, an offered degraded mode, or a ``best-effort sandbox``
   without the OD-17 refusal fails.

Dated records that correctly describe a past host are outside the walk
(frozen-sites ruling). ``deploy/compose/`` is an empty placeholder; T160
will ship the files. An empty directory is not a pass on compose — a
named assertion fails the day a compose file appears, forcing it onto
the walk.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

#: Surfaces that already claim a supported platform. Each must keep a
#: Linux-only statement. The list is the population, not an example: a
#: silent shrink is the required-surface test passing over nothing.
REQUIRED_SURFACES = (
    Path("src/supervisor/preflight.py"),
    Path("src/supervisor/main.py"),
    Path("src/supervisor/_linux.py"),
    Path("src/supervisor/cgroup.py"),
    Path("README.md"),
    Path("specs/002-spec-aware-agent-runtime/quickstart.md"),
    Path("specs/002-spec-aware-agent-runtime/plan.md"),
    Path("specs/002-spec-aware-agent-runtime/tasks.md"),
)

#: Live product-and-plan trees a new platform sentence would land in.
#: Findings, research, harness results and tests are dated records or
#: skip reasons, not product claims, and stay off this list.
LIVE_TREES = (
    Path("README.md"),
    Path("docs"),
    Path("deploy"),
    Path("src/supervisor"),
    Path("specs/002-spec-aware-agent-runtime/quickstart.md"),
    Path("specs/002-spec-aware-agent-runtime/plan.md"),
    Path("specs/002-spec-aware-agent-runtime/spec.md"),
    Path("specs/002-spec-aware-agent-runtime/tasks.md"),
    Path("pyproject.toml"),
    Path(".github/workflows/ci.yml"),
)

_LIVE_SUFFIXES = {".py", ".md", ".toml", ".yml", ".yaml"}

LINUX_ONLY_CLAIM = re.compile(
    r"Linux only|Linux-only|linux_only|"
    r"only supported platform|"
    r"Prerequisite\*\*: Linux|"
    r"fails on macOS by design|"
    r"unsupported rather than",
    re.I,
)

#: Offers, not definitions and not refusals. ``no degraded mode`` and
#: ``A degraded mode would be`` / ``is a sandbox`` are the OD-17 wording
#: itself; matching them would make every surface that states the rule
#: fail the scan that exists to protect it.
OFFER = re.compile(
    r"""
    \bor[ ]macOS\b
    | \bbest-effort[ ]sandbox\b
    | \bworks[ ]without[ ]Landlock\b
    | \bsupported[ ]on[ ](?:macOS|Darwin|Windows)\b
    | (?<!no[ ])(?<!not[ ]a[ ])degraded[ ]mode
      (?![ ]would)(?![ ]is[ ]a[ ]sandbox)
    """,
    re.I | re.X,
)

REFUSAL = re.compile(
    r"OD-17|"
    r"no degraded|"
    r"unsupported rather than|"
    r"Linux only|"
    r"Linux-only|"
    r"fails on macOS by design|"
    r"every other platform is (?:\*\*)?unsupported",
    re.I,
)


def _collapsed(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def _states_linux_only(text: str) -> bool:
    return bool(LINUX_ONLY_CLAIM.search(_collapsed(text)))


def unrefused_offers(text: str) -> list[str]:
    """Contradiction phrases that do not sit next to an OD-17 refusal."""
    collapsed = _collapsed(text)
    hits: list[str] = []
    for match in OFFER.finditer(collapsed):
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


def test_every_required_surface_states_linux_only() -> None:
    """The claim cannot be deleted from a surface that already makes it."""
    assert len(REQUIRED_SURFACES) >= 8, (
        "REQUIRED_SURFACES shrank below the set that stated the rule at "
        "0376820. A shorter list is the required-surface test passing over "
        "nothing."
    )
    missing: list[str] = []
    for relative in REQUIRED_SURFACES:
        path = REPO / relative
        assert path.is_file(), f"{relative} is gone; it was a platform surface"
        if not _states_linux_only(path.read_text()):
            missing.append(relative.as_posix())
    assert missing == [], (
        "supported-platform surface(s) no longer state Linux only:\n  "
        + "\n  ".join(missing)
        + "\nOD-17: Linux is the only supported platform; every other "
        "platform is unsupported rather than best-effort."
    )


def test_live_trees_do_not_add_an_unrefused_platform_contradiction() -> None:
    """A new 'or macOS' / offered degraded mode / best-effort sandbox fails."""
    offenders: list[str] = []
    scanned = 0
    for path in live_files():
        scanned += 1
        for snippet in unrefused_offers(path.read_text()):
            offenders.append(f"{path.relative_to(REPO)}: …{snippet}…")
    assert scanned >= 12, (
        f"the platform-statement walk covered {scanned} files, which is "
        "fewer than the live trees have ever held. It is passing because "
        "it read almost nothing. Check LIVE_TREES."
    )
    assert offenders == [], (
        "live surface(s) offer a non-Linux platform or a degraded mode "
        "without the OD-17 refusal:\n  "
        + "\n  ".join(offenders)
        + "\nA degraded mode is a sandbox missing one of Principle IV "
        "bullet 1's terms. Do not invent one to make a host pass."
    )


def test_the_contradiction_scan_fires_on_a_planted_offer() -> None:
    """The control. The scan above succeeds by finding nothing."""
    for planted in (
        "Supported on Linux or macOS.\n",
        "The agent uses a best-effort sandbox.\n",
        "The sandbox works without Landlock.\n",
        "enable degraded mode for developers\n",
        "supported on Darwin with a fallback\n",
    ):
        assert unrefused_offers(planted), planted
    for refused in (
        "Linux only, no degraded mode (OD-17).\n",
        "preflight() fails on macOS by design (OD-17, no degraded mode)\n",
        "A degraded mode would be a sandbox missing one term.\n",
        "A degraded mode is a sandbox missing one of the terms.\n",
        "Every other platform is unsupported rather than best-effort.\n",
        "OD-17 has no degraded mode. If the runner lacks a facility\n",
    ):
        assert unrefused_offers(refused) == [], refused


def test_the_linux_only_claim_matcher_accepts_the_known_forms() -> None:
    """The other control: a matcher that accepts everything is as silent."""
    assert _states_linux_only("**OD-17**: Linux only, no degraded mode.")
    assert _states_linux_only("import of this module is Linux-only")
    assert _states_linux_only("fails on macOS by design (OD-17)")
    assert _states_linux_only("Linux is the only supported platform")
    assert _states_linux_only("**Prerequisite**: Linux with cgroup v2")
    assert _states_linux_only("unsupported rather than best-effort")
    assert not _states_linux_only("runs anywhere you have Python")
    assert not _states_linux_only("supported on macOS")


def _compose_files() -> list[Path]:
    compose = REPO / "deploy" / "compose"
    if not compose.is_dir():
        return []
    return [path for path in compose.rglob("*") if path.is_file()]


def test_compose_has_no_files_until_t160() -> None:
    """T160 ships deploy/compose/. An empty directory is not that.

    ``deploy/compose/`` exists as an empty placeholder. Walking
    existing files would pass over it for free. This assertion fails
    the day a compose file appears, which is the named reason that
    forces those files onto LIVE_TREES rather than treating absence
    as a compose audit.
    """
    files = [path.relative_to(REPO).as_posix() for path in _compose_files()]
    assert files == [], (
        "T160 shipped compose files; add deploy/compose/ to LIVE_TREES "
        "and REQUIRED_SURFACES and delete this assertion. Absence of "
        "compose files was not a pass on compose. Found:\n  "
        + "\n  ".join(files)
    )


def test_dated_records_are_outside_the_walk() -> None:
    """Frozen-sites ruling: a correctly-scoped dated host record stays.

    Findings, research and harness results describe past hosts
    (Darwin measurements, macOS wheel gaps). They are not product
    support claims. If one of them enters the walk, a true dated
    record starts failing as a contradiction.
    """
    walked = [p.relative_to(REPO).as_posix() for p in live_files()]
    leaked = [
        path
        for path in walked
        if "/findings/" in path
        or path.startswith("research/")
        or "/harness/" in path
        or path.startswith("tests/")
    ]
    assert leaked == [], (
        "the platform-statement walk reached a dated record:\n  "
        + "\n  ".join(leaked)
    )
    assert walked, "the walk is empty; dated-record exclusion is free"
