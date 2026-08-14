"""T191 — SC-017's per-runtime adoption report.

A runtime that is installed, demonstrated and then unused at four weeks
is a non-adoption, not an install. An empty live census is not a green
adoption rate over zero. The four-week window is the criterion's.

Run:
    python -m pytest tests/unit/test_adoption_report.py -v
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

from src.runtime.reports import adoption as ad
from tests.invariants.test_import_graph import forbidden_edges

REPO = Path(__file__).resolve().parents[2]
ADOPTION = REPO / "src" / "runtime" / "reports" / "adoption.py"
SUCCESS_PATH = (
    REPO / "src" / "runtime" / "loop.py",
    REPO / "src" / "runtime" / "runner.py",
    REPO / "src" / "runtime" / "serving.py",
    REPO / "src" / "runtime" / "main.py",
    REPO / "src" / "contracts" / "result.py",
)
FORBIDDEN_FROM_ADOPTION = (
    "src.contracts.result",
    "src.runtime.loop",
    "src.runtime.runner",
    "src.runtime.serving",
    "src.runtime.main",
    "src.runtime.judge",
    "src.runtime.batteries",
)

INSTALL = 1_000_000.0
DEMO = INSTALL + 60.0
DAY = 24 * 60 * 60
FOUR = ad.FOUR_WEEKS_SECONDS


def _imported(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return names


def _obs(
    deployment_id: str = "d-1",
    *,
    installed_at: float | None = INSTALL,
    demonstrated_at: float | None = DEMO,
    last_served_at: float | None = DEMO,
) -> ad.RuntimeObservation:
    return ad.RuntimeObservation(
        deployment_id=deployment_id,
        installed_at=installed_at,
        demonstrated_at=demonstrated_at,
        last_served_at=last_served_at,
    )


def _census(
    observations: list[ad.RuntimeObservation],
    *,
    now: float,
    live: bool = False,
) -> ad.AdoptionCensus:
    return ad.report(observations, now=now, live=live)


# ---------------------------------------------------------------------------
# The four-week constant is SC-017's, not an invented default.


def test_the_four_week_constant_is_the_criterions_not_an_invented_default() -> None:
    """Four weeks, derived from the criterion text, not a silent 86400.

    Plant-adjacent: changing `FOUR_WEEKS_SECONDS` to a day, a week, or
    FR-045's reporting window would pass a classifier that no longer
    measures what SC-017 named.
    """
    assert ad.FOUR_WEEKS_SECONDS == 4 * 7 * 24 * 60 * 60
    assert ad.FOUR_WEEKS_SECONDS == 2_419_200
    assert ad.FOUR_WEEKS_SECONDS != 86400
    assert ad.FOUR_WEEKS_SECONDS != 3600
    source = ad.module_source()
    assert "4 * 7 * 24 * 60 * 60" in source
    assert "four weeks" in ad.FOUR_WEEKS_BASIS
    assert "SC-017" in ad.FOUR_WEEKS_BASIS
    imported = _imported(ADOPTION)
    assert "src.runtime.reports.windows" not in imported
    assert "src.contracts.config" not in imported


# ---------------------------------------------------------------------------
# Installed, demonstrated, unused at four weeks → non_adoption, not an install.


def test_installed_demonstrated_then_unused_is_a_non_adoption_not_an_install() -> None:
    """The sentence SC-017 exists for.

    Plant: `NON_ADOPTION_COUNTED_AS_INSTALL = True`. The unused-after-demo
    runtime is counted as an install, which is the lie the criterion names.
    """
    assert ad.NON_ADOPTION_COUNTED_AS_INSTALL is False
    produced = _census(
        [_obs(last_served_at=DEMO)],
        now=INSTALL + FOUR,
    )
    assert len(produced.runtimes) == 1
    row = produced.runtimes[0]
    assert row.classification == ad.STATE_NON_ADOPTION
    assert row.counted_as_install is False
    assert produced.non_adoption_count == 1
    assert produced.install_count == 0
    document = produced.document()
    assert document["runtimes"][0]["classification"] == "non_adoption"
    assert document["runtimes"][0]["counted_as_install"] is False
    assert document["install_count"] == 0
    assert document["non_adoption_count"] == 1
    assert "non-adoption rather than as an install" in document["state_meanings"][
        ad.STATE_NON_ADOPTION
    ]


# ---------------------------------------------------------------------------
# Installed, demonstrated, still serving at four weeks.


def test_installed_demonstrated_and_still_serving_at_four_weeks() -> None:
    produced = _census(
        [_obs(last_served_at=INSTALL + FOUR)],
        now=INSTALL + FOUR,
    )
    row = produced.runtimes[0]
    assert row.classification == ad.STATE_STILL_SERVING
    assert row.counted_as_install is True
    document = produced.document()
    assert document["runtimes"][0]["classification"] == "still_serving"
    assert "still serving traffic four weeks after installation" in (
        document["state_meanings"][ad.STATE_STILL_SERVING]
    )
    assert produced.adoption_share == 1.0
    assert produced.assessable_count == 1


def test_serving_after_the_four_week_mark_is_still_serving() -> None:
    produced = _census(
        [_obs(last_served_at=INSTALL + FOUR + DAY)],
        now=INSTALL + FOUR + DAY,
    )
    assert produced.runtimes[0].classification == ad.STATE_STILL_SERVING


# ---------------------------------------------------------------------------
# Empty / live-absent: not a green rate over zero.


def test_an_empty_live_census_is_not_a_green_adoption_share() -> None:
    """OD-36: no production runtime is serving. Zero runtimes is not 100%.

    Plant: `EMPTY_LIVE_CENSUS_IS_GREEN = True`. The empty census reports
    `adoption_share = 1.0`, which is a green adoption rate over zero.
    """
    assert ad.EMPTY_LIVE_CENSUS_IS_GREEN is False
    produced = ad.report([], now=INSTALL, live=False)
    assert produced.live is False
    assert produced.synthetic is False
    assert produced.runtimes == ()
    assert produced.assessable_count == 0
    assert produced.install_count == 0
    assert produced.non_adoption_count == 0
    assert produced.adoption_share is None
    document = produced.document()
    assert document["live"] is False
    assert document["adoption_share"] is None
    assert document["share_absent_because"] == ad.EMPTY_CENSUS_ABSENCE
    assert "green adoption rate over zero" in document["share_absent_because"]
    assert document["threshold_applied"] is None
    assert all(document["by_classification"][state] == 0 for state in ad.STATES)


def test_an_empty_census_does_not_invent_an_install_row() -> None:
    produced = ad.report(now=INSTALL)
    assert produced.document()["runtimes"] == []
    assert produced.by_classification[ad.STATE_NO_INSTALL] == 0


def test_no_install_evidence_is_not_an_install_and_not_a_non_adoption() -> None:
    produced = _census(
        [_obs(installed_at=None, demonstrated_at=None, last_served_at=None)],
        now=INSTALL + FOUR,
    )
    row = produced.runtimes[0]
    assert row.classification == ad.STATE_NO_INSTALL
    assert row.counted_as_install is False
    assert produced.install_count == 0
    assert produced.non_adoption_count == 0
    assert produced.assessable_count == 0
    assert produced.adoption_share is None


# ---------------------------------------------------------------------------
# Installed, never demonstrated: not adopted, not a non-adoption.


def test_an_install_only_row_is_not_classified_as_adopted() -> None:
    produced = _census(
        [_obs(demonstrated_at=None, last_served_at=None)],
        now=INSTALL + FOUR,
    )
    row = produced.runtimes[0]
    assert row.classification == ad.STATE_NOT_DEMONSTRATED
    assert row.classification != ad.STATE_STILL_SERVING
    assert row.classification != ad.STATE_NON_ADOPTION
    assert produced.assessable_count == 0
    assert produced.adoption_share is None
    assert produced.install_count == 1
    assert produced.non_adoption_count == 0


# ---------------------------------------------------------------------------
# Four-week wait: day-1 unused is not a non-adoption.


def test_day_one_unused_is_not_a_non_adoption() -> None:
    """The four-week wait is the criterion. Dropping it is the plant.

    Plant: `FOUR_WEEK_WAIT_IS_DROPPED = True`. Day-1 unused is recorded
    as a non-adoption, so the measurement no longer waits four weeks.
    """
    assert ad.FOUR_WEEK_WAIT_IS_DROPPED is False
    produced = _census(
        [_obs(last_served_at=DEMO)],
        now=INSTALL + DAY,
    )
    row = produced.runtimes[0]
    assert row.classification == ad.STATE_NOT_YET_ASSESSABLE
    assert row.classification != ad.STATE_NON_ADOPTION
    assert produced.non_adoption_count == 0
    assert produced.assessable_count == 0
    assert produced.adoption_share is None


def test_a_fixture_marks_synthetic_and_not_live() -> None:
    produced = _census(
        [_obs(last_served_at=INSTALL + FOUR)],
        now=INSTALL + FOUR,
        live=False,
    )
    assert produced.live is False
    assert produced.synthetic is True
    assert produced.document()["live"] is False
    assert produced.document()["synthetic"] is True


def test_the_document_is_json() -> None:
    document = _census(
        [_obs(last_served_at=DEMO)],
        now=INSTALL + FOUR,
    ).document()
    assert json.loads(json.dumps(document)) == document
    assert document["schema_version"] == ad.SCHEMA_VERSION
    assert document["criterion"] == "SC-017"
    assert document["four_weeks_seconds"] == ad.FOUR_WEEKS_SECONDS


def test_all_named_states_appear_even_at_zero() -> None:
    document = ad.report([], now=INSTALL).document()
    assert set(document["by_classification"]) == set(ad.STATES)
    assert set(document["state_meanings"]) == set(ad.STATES)


# ---------------------------------------------------------------------------
# The report does not import the success path, the judge, or serving.


def test_the_report_does_not_import_the_success_path_or_the_judge() -> None:
    edges: list[str] = []
    for imported in sorted(_imported(ADOPTION)):
        for forbidden in FORBIDDEN_FROM_ADOPTION:
            if imported == forbidden or imported.startswith(forbidden + "."):
                edges.append(f"adoption.py imports {imported}")
    assert edges == [], (
        "the adoption report imported a success-path or judge module:\n  "
        + "\n  ".join(edges)
    )


def test_the_success_path_does_not_import_the_adoption_report() -> None:
    found: list[str] = []
    for path in SUCCESS_PATH:
        relative = path.relative_to(REPO).as_posix()
        for imported in sorted(_imported(path)):
            if imported == "src.runtime.reports.adoption" or imported.startswith(
                    "src.runtime.reports.adoption."):
                found.append(f"{relative} imports {imported}")
    assert found == [], (
        "a success-path module imported the adoption report:\n  "
        + "\n  ".join(found)
    )


def test_the_adoption_import_scan_fires_on_a_planted_result_import(
        tmp_path: Path) -> None:
    planted = tmp_path / "adoption.py"
    planted.write_text("from src.contracts.result import Result\n")
    found: list[str] = []
    for imported in _imported(planted):
        if imported == "src.contracts.result" or imported.startswith(
                "src.contracts.result."):
            found.append(imported)
    assert found, "the adoption→result scan did not report a planted import"


def test_forbidden_edges_stay_empty() -> None:
    assert forbidden_edges(REPO) == []
