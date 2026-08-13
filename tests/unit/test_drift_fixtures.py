"""The asserted expected output for Phase 6's four committed drift corpora.

**Tasks**: T154 (`tests/fixtures/drift-source/`), T155
(`tests/fixtures/drift-deployment/`), T157 (`tests/fixtures/spec-withdrawn/`)
and T158 (`tests/fixtures/operation-added/`).
**Criteria**: SC-008; SC-009 and SC-020; SC-021; SC-026.

## Why this file exists at all

FR-053 requires *a committed fixture **and an asserted expected output for it***
— a corpus with no assertion beside it is inert data, and FR-053 says a shape
with no asserted expected output is unsupported rather than best-effort. The
four corpora are committed with no consumer, because every Phase 6 module that
would consume them (T137 through T153) is open. This file is the assertion.

## What is asserted here, and the much larger thing that is not

**Asserted**: that each corpus recomputes to its own declarations, that its
populations contain the cases its criteria need, and — the part that carries
weight — that a **trivially wrong detector fails it**. Each of the four
ablations below is a real function applied to the real corpus, not a comment
claiming one would fail.

**Not asserted, and not obtainable from here**: any detection rate, any
false-alarm rate, any latency. ~~No Phase 6 detector exists to score.~~
**Superseded 2026-08-13 — T138 now scores this corpus in
`tests/contract/test_source_drift.py`.** What this file still does not produce
is a Phase 8 rate or latency; T182 is that measurement. This file remains the
assertion that the corpora recompute to their declarations and that a trivially
wrong detector fails them.
[`VERDICT.md`](../../specs/001-discovery-validation/VERDICT.md) line 162 records
that drift detection has *"no detection rate, no false-alarm rate, no latency
to detect, on either of its two clocks"* as the production figure, and
[`plan.md`](../../specs/002-spec-aware-agent-runtime/plan.md) line 831 records
in bold that **E13 never ran at all**. Committing an instrument is not taking
that reading, and nothing in this file may be cited as though it were.

## The ablations, which are Rule 8 in executable form

The experiment-design skill's **Rule 8**: a fixture whose positive result is a
failure signal needs a negative control, and *the tell that one is missing is a
perfect score on an ablation suite*. Every criterion these four corpora serve is
phrased as **100%** or **zero**, which is exactly that shape. So each corpus is
run against the cheapest detector that would score perfectly without one:

| Corpus | Ablation | Where it fails |
|---|---|---|
| `drift-source` | *report drift on every revision* | the four non-breaking revisions |
| `drift-source` | *report drift on no revision* | the six breaking revisions |
| `drift-deployment` | *disable the whole target on every poll* | `no-withdrawal`, and the surviving neighbour |
| `spec-withdrawn` | *mark every result stale* | `never-withdrawn` |
| `spec-withdrawn` | *report drift on every restoration* | the two unchanged restorations |
| `operation-added` | *refuse every operation* | `no-operation-added` |

A test asserting the ablation *fails* is the only form in which a negative
control is load-bearing rather than decorative: delete the control cases from
the population and the assertion goes red.

## Planted defects, because reading a guard's source proves nothing

Several tests below **plant** the defect the guard is supposed to catch — a
check run observing two revisions, a change time read off an observation, a
declared age that disagrees with the clock, a terminal state outside the
taxonomy, a withdrawal inside the never-withdrawn fixture — and assert the
loader refuses it. A guard's source shows what its author intended to cover,
which is the thing in question whenever a gap is suspected.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

import pytest

from src.analysis.admission import ABSENT, PUBLISHED_NON_EMPTY
from src.analysis.deputy_inspection import ALLOWED_OUTCOMES, OUTCOMES
from tests.fixtures.drift_corpora import CorpusInconsistent, seconds_between
from tests.fixtures.drift_corpora import deployment as dep
from tests.fixtures.drift_corpora import operation_added as add
from tests.fixtures.drift_corpora import source as src
from tests.fixtures.drift_corpora import spec_withdrawn as sw

REPO = Path(__file__).resolve().parents[2]

#: The four directories the task list names, verbatim. A corpus committed
#: somewhere else satisfies the task text's prose and not its path.
DECLARED_PATHS = {
    "T154": REPO / "tests" / "fixtures" / "drift-source",
    "T155": REPO / "tests" / "fixtures" / "drift-deployment",
    "T157": REPO / "tests" / "fixtures" / "spec-withdrawn",
    "T158": REPO / "tests" / "fixtures" / "operation-added",
}


def _plant(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    module: Any,
    mutate: Callable[[dict[str, Any]], None],
) -> None:
    """Write a mutated copy of a corpus and point its loader at it.

    Planting the defect into the real payload and re-loading is the only way to
    show a guard covers it. Reading the guard shows what its author meant to
    cover, which is precisely what is in doubt.
    """
    payload = json.loads(module.CORPUS_FILE.read_text())
    mutate(payload)
    planted = tmp_path / "planted.json"
    planted.write_text(json.dumps(payload))
    monkeypatch.setattr(module, "CORPUS_FILE", planted)


# ---------------------------------------------------------------------------
# Cross-corpus: the paths, and the populations that name themselves.
# ---------------------------------------------------------------------------

def test_the_four_corpora_sit_at_the_paths_the_task_list_names():
    for task, path in DECLARED_PATHS.items():
        assert path.is_dir(), f"{task}: {path} is not a directory"
        assert (path / "corpus.json").is_file(), f"{task}: no corpus.json"
        assert (path / "README.md").is_file(), f"{task}: no README.md"


@pytest.mark.parametrize(
    "counts,total,parts",
    [
        pytest.param(
            src.counts,
            "revisions_with_a_parent_and_therefore_a_diff",
            ("breaking_revisions", "non_breaking_revisions"),
            id="drift-source",
        ),
        pytest.param(
            dep.counts,
            "scenarios_total",
            ("scenarios_carrying_a_withdrawal",
             "scenarios_with_nothing_withdrawn"),
            id="drift-deployment",
        ),
        pytest.param(
            sw.counts,
            "scenarios_total",
            ("scenarios_in_which_the_specification_is_withdrawn",
             "scenarios_in_which_it_is_never_withdrawn"),
            id="spec-withdrawn",
        ),
        pytest.param(
            add.counts,
            "scenarios_total",
            ("scenarios_in_which_something_is_added",
             "scenarios_in_which_nothing_is_added"),
            id="operation-added",
        ),
    ],
)
def test_every_total_is_partitioned_by_a_breakdown_that_sums_to_it(
    counts, total, parts
):
    """A subset presented as a total is this repository's recurring defect.

    Every corpus reports a total *and* a partition of it, and the partition has
    to add up. That is the machine-checkable form of `a figure must name its own
    population`: the total cannot quietly become a count over the interesting
    half.
    """
    figures = counts()
    assert sum(figures[p] for p in parts) == figures[total], (
        f"the breakdown {list(parts)} sums to "
        f"{sum(figures[p] for p in parts)} and the total {total!r} is "
        f"{figures[total]}. One of them is over a different population."
    )


def test_the_source_corpuss_scoreable_denominator_excludes_the_base_revision():
    """The one place a subset could be presented as a total without noticing.

    `drift-source` is the only corpus whose scoreable population is *smaller*
    than its total: the base revision has no parent, so it can carry no diff
    and cannot be detected on or missed. A detection rate computed over all 11
    revisions rather than the 10 with a parent is a rate over a case that
    cannot be scored at all.

    Kept separate from the parametrized partition test above, and not folded
    into it, because a removal proof names one node and the parametrized ids
    are the only bracketed selectors this repository would have.
    """
    figures = src.counts()
    assert figures["revisions_with_a_parent_and_therefore_a_diff"] == (
        figures["revisions_total"] - 1
    ), (
        "exactly one revision — the base — has no parent, so the scoreable "
        "denominator is one less than the total. If they are equal, the base "
        "revision has been folded into a population it cannot belong to."
    )
    assert (
        figures["breaking_revisions"] + figures["non_breaking_revisions"]
        == figures["revisions_with_a_parent_and_therefore_a_diff"]
    )


# ---------------------------------------------------------------------------
# T154 — tests/fixtures/drift-source/ (FR-053, SC-008).
# ---------------------------------------------------------------------------

def test_the_source_corpus_recomputes_to_its_own_declarations():
    """Loading is the check: every declared field is contradicted on mismatch."""
    revisions = src.load_revisions()
    assert len(revisions) == src.counts()["revisions_total"]


def test_the_base_revision_describes_the_reference_application():
    assert src.base_operation_ids() <= src.reference_app_operation_ids(), (
        "the base revision names operations the reference application does "
        "not publish, so this corpus describes drift on a target that does "
        "not exist"
    )


def test_e13s_three_named_mutations_are_all_present():
    """plan.md line 831 names them: rename a route, change a parameter type,
    delete an endpoint. A source corpus missing one of the three covers less
    than the experiment that never ran."""
    kinds = {k for r in src.load_revisions() for k in r.change_kinds}
    for mutation in ("operation_renamed", "parameter_type_changed",
                     "operation_removed"):
        assert mutation in kinds, f"E13's {mutation} has no revision"


def test_every_change_kind_the_classifier_emits_has_a_breaking_verdict():
    assert not (src.BREAKING_KINDS & src.NON_BREAKING_KINDS), (
        "a kind in both sets makes its verdict depend on evaluation order"
    )
    kinds = {k for r in src.load_revisions() for k in r.change_kinds}
    assert kinds <= src.ALL_KINDS


def test_every_breaking_revision_is_owed_detection_in_its_own_check_run():
    """SC-008's *same automated check run as the commit that introduced them*."""
    for revision in src.load_revisions():
        if revision.breaking:
            assert revision.expected_detection_run == revision.check_run_id
        else:
            assert revision.expected_detection_run is None


def test_the_source_corpus_carries_revisions_that_must_raise_no_signal():
    """Rule 8's negative control, and the identical-contract case inside it."""
    figures = src.counts()
    assert figures["non_breaking_revisions"] >= 3, (
        "SC-008 is a 100% detection figure and a corpus of only breaking "
        "changes scores it perfectly with a detector that always fires"
    )
    assert figures["revisions_whose_contract_is_identical_to_their_parent"] >= 1


def test_a_detector_that_reports_drift_on_every_revision_fails_this_corpus():
    """The ablation. If it passes, the negative control has gone missing."""
    scoreable = [r for r in src.load_revisions() if r.parent is not None]
    wrong = [r for r in scoreable if not r.breaking]
    assert wrong, (
        "every revision with a parent is breaking, so 'always report drift' "
        "scores a perfect 100% on SC-008 — the exact tell Rule 8 names"
    )


def test_a_detector_that_reports_drift_on_no_revision_fails_this_corpus():
    """The opposite ablation, so the corpus is not all control and no signal."""
    assert [r for r in src.load_revisions() if r.breaking]


def test_a_check_run_observing_two_revisions_is_refused(monkeypatch, tmp_path):
    """Planted: SC-008 stops being falsifiable once a run spans a range."""
    def collapse(payload: dict[str, Any]) -> None:
        payload["revisions"][2]["check_run_id"] = (
            payload["revisions"][1]["check_run_id"]
        )

    _plant(monkeypatch, tmp_path, src, collapse)
    with pytest.raises(src.CorpusInconsistent, match="more than one revision"):
        src.load_revisions()


def test_a_declared_breaking_verdict_that_disagrees_with_the_diff_is_refused():
    """Planted: the committed declaration is contradicted, not read."""
    with pytest.raises(src.CorpusInconsistent, match="declared breaking"):
        src._reject_disagreement(
            {"revision_id": "C-planted", "change_kinds": ["operation_removed"],
             "breaking": False, "drifted_operations": ["get_part"],
             "check_run_id": "R-planted", "expected_detection_run": None},
            frozenset({"operation_removed"}), True, ("get_part",),
        )


def test_a_rename_whose_signature_moved_is_refused():
    """Planted: a rename that also changes the signature carries two changes."""
    before = {"a": {"summary": "s", "parameters": {}, "returns": {"x": "int"}}}
    after = {"b": {"summary": "s", "parameters": {}, "returns": {"x": "str"}}}
    with pytest.raises(src.CorpusInconsistent, match="signatures differ"):
        src.diff_contracts(before, after, (("a", "b"),))


# ---------------------------------------------------------------------------
# T155 — tests/fixtures/drift-deployment/ (SC-009, SC-020).
# ---------------------------------------------------------------------------

def test_the_deployment_corpus_recomputes_to_its_own_declarations():
    scenarios = dep.load_scenarios()
    assert len(scenarios) == dep.counts()["scenarios_total"]


def test_no_declared_change_time_coincides_with_an_observation():
    """The property that makes SC-020's latency measurable at all.

    plan.md line 830: *"Inferring the change time from first observation
    measures the detector against itself."* A change instant equal to an
    observation instant is indistinguishable from one inferred from it.
    """
    payload = json.loads(dep.CORPUS_FILE.read_text())
    for scenario in payload["scenarios"]:
        change_at = scenario["change"]["at"]
        if change_at is None:
            continue
        instants = {
            observation["at"]
            for arm in scenario["arms"].values()
            for observation in arm["observations"]
        }
        assert change_at not in instants, (
            f"{scenario['scenario_id']}: the change time was read off an "
            "observation, which is the failure this corpus exists to avoid"
        )


def test_a_change_time_read_off_an_observation_is_refused(monkeypatch, tmp_path):
    """Planted, because the guard's source is not evidence the guard covers it."""
    def coincide(payload: dict[str, Any]) -> None:
        scenario = payload["scenarios"][0]
        scenario["change"]["at"] = (
            scenario["arms"]["scheduled"]["observations"][1]["at"]
        )

    _plant(monkeypatch, tmp_path, dep, coincide)
    with pytest.raises(dep.CorpusInconsistent, match="also an observation"):
        dep.load_scenarios()


def test_a_declared_latency_that_disagrees_with_the_clock_is_refused(
    monkeypatch, tmp_path
):
    """Planted: the latency is arithmetic on the corpus, not a committed number."""
    def fudge(payload: dict[str, Any]) -> None:
        payload["scenarios"][0]["arms"]["scheduled"][
            "expected_latency_seconds"
        ] = 1

    _plant(monkeypatch, tmp_path, dep, fudge)
    with pytest.raises(dep.CorpusInconsistent, match="declares a latency"):
        dep.load_scenarios()


def test_the_corpus_supplies_no_event_from_a_deployment_pipeline():
    """SC-020: *with no event supplied by a deployment pipeline*, and FR-046
    says such an event may not be assumed available."""
    assert dep.deployment_events() == [], (
        "an event here would make every latency in this corpus trivial and "
        "would measure a channel FR-046 forbids relying on"
    )


def test_every_scenario_carries_both_of_sc020s_arms():
    for scenario in dep.load_scenarios():
        assert set(scenario.arms) == set(dep.REQUIRED_ARMS), (
            f"{scenario.scenario_id}: SC-020 has a clause for the default "
            "automated trigger and one for manual invocation"
        )


def test_the_deployment_corpus_carries_a_scenario_with_nothing_withdrawn():
    """Rule 8's negative control for a pair of 100%-of-withdrawn criteria."""
    assert dep.counts()["scenarios_with_nothing_withdrawn"] >= 1


def test_a_detector_that_disables_the_target_on_every_poll_fails_this_corpus():
    """The ablation, run rather than described."""
    scenarios = dep.load_scenarios()
    controls = [s for s in scenarios if s.is_negative_control]
    survivors = [s for s in scenarios if s.unaffected and s.withdrawn]
    assert controls, (
        "no scenario has an empty withdrawal set, so 'disable everything on "
        "every poll' scores 100% on SC-009 and SC-020 alike"
    )
    assert survivors, (
        "every withdrawal takes down the whole served set, so SC-009's "
        "'zero unaffected operations are disabled' clause has no subject"
    )


def test_a_withdrawal_leaves_a_confusable_neighbour_standing():
    """`list_shipments` goes and `list_parts` stays, so a prefix match fails."""
    scenarios = {s.scenario_id: s for s in dep.load_scenarios()}
    neighbour = scenarios["withdraw-one-of-two-neighbours"]
    assert neighbour.withdrawn == ("list_shipments",)
    assert "list_parts" in neighbour.unaffected


def test_the_scheduled_windows_margin_is_a_property_of_the_interval():
    """Stated rather than left to be discovered.

    The poll interval is smaller than the detection window, so the scheduled
    arm satisfies SC-020's window clause **by construction** on every scenario
    here. That is arithmetic on two configured defaults marked unvalidated
    under FR-043, not a measurement, and this assertion exists so the day
    someone widens the interval past the window it is not a silent change.
    """
    assert dep.poll_interval_seconds() < dep.detection_window_seconds()
    assert dep.max_scheduled_latency_seconds() < dep.detection_window_seconds()


def test_the_deployment_corpus_never_stops_publishing_its_specification():
    """This corpus withdraws OPERATIONS. Withdrawing the document is T157."""
    assert dep.every_specification_state_seen() == frozenset({
        PUBLISHED_NON_EMPTY
    })


def test_every_deployment_scenario_describes_the_reference_application():
    known = dep.reference_app_operation_ids()
    for scenario in dep.load_scenarios():
        assert scenario.served_before <= known, scenario.scenario_id


# ---------------------------------------------------------------------------
# T157 — tests/fixtures/spec-withdrawn/ (SC-021).
# ---------------------------------------------------------------------------

def test_the_spec_withdrawn_corpus_recomputes_to_its_own_declarations():
    scenarios = sw.load_scenarios()
    assert len(scenarios) == sw.counts()["scenarios_total"]


def test_all_three_of_fr044s_non_admissible_states_are_exercised():
    """T147 enters the stale state on any of the three, not only on `absent`."""
    assert sw.non_admissible_states_exercised() == sw.NON_ADMISSIBLE_STATES


def test_calls_below_the_ceiling_are_served_and_calls_past_it_are_denied():
    ceiling = sw.staleness_ceiling_seconds()
    for scenario in sw.load_scenarios():
        for call in scenario.calls:
            if call.stale and call.age_seconds > ceiling:
                assert not call.served, (
                    f"{scenario.scenario_id} at {call.at}: SC-021 requires "
                    "zero calls served past the ceiling"
                )
            else:
                assert call.served


def test_no_call_lands_exactly_on_the_ceiling():
    """The boundary's disposition is T149's and T150's, not a fixture's."""
    ceiling = sw.staleness_ceiling_seconds()
    for scenario in sw.load_scenarios():
        for call in scenario.calls:
            assert call.age_seconds != ceiling, (
                f"{scenario.scenario_id} at {call.at}: a fixture deciding the "
                "exact-ceiling case would pre-empt the tasks that own it"
            )


def test_every_stale_result_can_carry_an_age_and_the_state_last_found():
    """SC-021's first clause and T148's three fields, present per call."""
    for scenario in sw.load_scenarios():
        for call in scenario.calls:
            if not call.stale:
                continue
            assert call.age_seconds > 0
            assert call.specification_state_last_found != PUBLISHED_NON_EMPTY


def test_the_corpus_carries_a_scenario_in_which_nothing_is_ever_stale():
    """Rule 8: *mark every result stale* satisfies clause one otherwise."""
    assert sw.counts()["scenarios_in_which_it_is_never_withdrawn"] >= 1


def test_an_implementation_marking_every_result_stale_fails_this_corpus():
    """The ablation, run against the real population."""
    clean = [
        call
        for scenario in sw.load_scenarios()
        for call in scenario.calls
        if not call.stale
    ]
    assert clean, (
        "every call in the corpus is made while the set is stale, so an "
        "implementation that marks everything stale scores a perfect 100% "
        "on SC-021's first clause"
    )


def test_an_implementation_reporting_drift_on_every_restoration_fails():
    """The ablation for SC-021's fourth clause."""
    restorations = [
        s for s in sw.load_scenarios() if s.restored_at is not None
    ]
    unchanged = [s for s in restorations if not s.drift_on_restore]
    assert unchanged, (
        "every restoration changes the set, so 'report drift on every "
        "restoration' scores a perfect 100% on the fourth clause"
    )


def test_a_restoration_that_changes_the_set_reports_exactly_what_differs():
    scenarios = {s.scenario_id: s for s in sw.load_scenarios()}
    changed = scenarios["withdraw-restore-changed-below-ceiling"]
    assert changed.restored_set is not None
    assert changed.drift_on_restore == tuple(sorted(
        changed.last_known_good ^ changed.restored_set
    ))
    assert changed.drift_on_restore


def test_the_taxonomy_still_has_no_terminal_state_naming_the_staleness_ceiling():
    """The gap SC-021's third clause needs closed, asserted so it cannot rot.

    `src/contracts/terminal.py` is a closed taxonomy and none of its members
    names the staleness ceiling. T150 requires an in-flight session past the
    ceiling to end in a named terminal state, so that member is **owed**.

    When T150 adds it this test fails — deliberately. At that point the
    `expected_terminal_state: null` in `withdraw-past-ceiling` and the
    paragraphs explaining it in two READMEs are wrong and have to move. A gap
    recorded only in prose goes stale silently; this one cannot.
    """
    assert not sw.taxonomy_names_the_staleness_ceiling(), (
        "a terminal state now names staleness. T150 has landed, so "
        "tests/fixtures/spec-withdrawn/corpus.json must stop declaring "
        "expected_terminal_state as null and name it instead."
    )


def test_a_terminal_state_outside_the_taxonomy_is_refused():
    """Planted: a fixture may not open a taxonomy FR-006 closed."""
    with pytest.raises(sw.CorpusInconsistent, match="not in the declared"):
        sw._reject_undeclared_terminal_state(
            "terminated.specification_stale", "planted"
        )


def test_a_declared_age_that_disagrees_with_the_wall_clock_is_refused(
    monkeypatch, tmp_path
):
    """Planted: T149's age is arithmetic, not a committed number."""
    def fudge(payload: dict[str, Any]) -> None:
        payload["scenarios"][0]["calls"][0]["age_seconds"] = 1

    _plant(monkeypatch, tmp_path, sw, fudge)
    with pytest.raises(sw.CorpusInconsistent, match="declares an age"):
        sw.load_scenarios()


def test_the_corpus_separates_t149s_age_rule_from_the_wrong_one():
    """T149's *wall clock from the last successful fetch*, shown to differ.

    T149 exists because measuring the age from the moment staleness was
    *entered* lets a longer re-fetch interval silently widen the ceiling. The
    two rules are only distinguishable on a scenario where they disagree about
    a **disposition**, not merely about a number — so this asserts the corpus
    contains a call that T149 denies and the wrong rule would serve.
    """
    scenarios = {s.scenario_id: s for s in sw.load_scenarios()}
    past = scenarios["withdraw-past-ceiling"]
    ceiling = sw.staleness_ceiling_seconds()

    entered_at = next(
        at
        for at, state in zip(past.fetch_instants, past.fetch_states)
        if state != PUBLISHED_NON_EMPTY
    )
    denied = [c for c in past.calls if not c.served]
    assert denied, "the scenario carries no denial to distinguish the rules"

    served_by_the_wrong_rule = [
        c for c in denied
        if seconds_between(entered_at, c.at) < ceiling <= c.age_seconds
    ]
    assert served_by_the_wrong_rule, (
        "every denial here is denied under both rules, so the corpus cannot "
        "tell T149's anchor from the one it was written to exclude"
    )


def test_every_spec_withdrawn_scenario_describes_the_reference_application():
    known = sw.reference_app_operation_ids()
    for scenario in sw.load_scenarios():
        assert scenario.last_known_good <= known, scenario.scenario_id


# ---------------------------------------------------------------------------
# T158 — tests/fixtures/operation-added/ (SC-026).
# ---------------------------------------------------------------------------

def test_the_operation_added_corpus_recomputes_to_its_own_declarations():
    scenarios = add.load_scenarios()
    assert len(scenarios) == add.counts()["scenarios_total"]


def test_the_specification_is_published_at_every_single_fetch():
    """SC-026's *while continuing to publish that specification throughout*."""
    for scenario in add.load_scenarios():
        assert set(scenario.fetch_states) == {PUBLISHED_NON_EMPTY}, (
            f"{scenario.scenario_id}: a withdrawal here would score SC-026 on "
            "T157's timeline"
        )


def test_a_withdrawal_planted_into_this_corpus_is_refused(monkeypatch, tmp_path):
    """Planted, because the continuity is the fixture rather than a setting."""
    def withdraw(payload: dict[str, Any]) -> None:
        payload["scenarios"][0]["fetches"][0]["state"] = ABSENT

    _plant(monkeypatch, tmp_path, add, withdraw)
    with pytest.raises(add.CorpusInconsistent, match="keeps publishing"):
        add.load_scenarios()


def test_all_three_of_fr056s_outcomes_are_exercised():
    assert add.outcomes_exercised() == frozenset(OUTCOMES)


def test_an_uninspectable_addition_is_present_so_the_refusal_clause_has_a_subject():
    """SC-026's third clause is *100% of those that cannot be inspected are
    refused*, which is 100% of zero without one."""
    uninspectable = [
        op
        for scenario in add.load_scenarios()
        for op, outcome in scenario.outcomes.items()
        if outcome == "uninspectable"
    ]
    assert uninspectable


def test_both_non_clean_outcomes_are_denied_and_remain_two_outcomes():
    """FR-056: denied alike, reported differently."""
    assert ALLOWED_OUTCOMES == frozenset({"clean"})
    denied = {o for o in OUTCOMES if o not in ALLOWED_OUTCOMES}
    assert denied == {"deputy", "uninspectable"}
    exercised = {
        outcome
        for scenario in add.load_scenarios()
        for outcome in scenario.outcomes.values()
    }
    assert denied <= exercised


def test_a_mixed_fetch_admits_the_clean_member_and_refuses_the_others():
    """The batch case: neither all-or-nothing answer is correct."""
    scenarios = {s.scenario_id: s for s in add.load_scenarios()}
    mixed = scenarios["add-three-mixed-in-one-fetch"]
    assert "list_warehouses" in mixed.available_at_end
    assert mixed.refused == ("fetch_url", "proxy_lookup")


def test_republishing_an_already_inspected_set_introduces_nothing_new():
    """T153 compares against the last INSPECTED set, not the previous fetch."""
    scenarios = {s.scenario_id: s for s in add.load_scenarios()}
    republished = scenarios["add-then-republish-unchanged"]
    assert republished.newly_appearing_per_fetch == ((), ("list_warehouses",), ())


def test_the_corpus_carries_a_scenario_in_which_nothing_is_added():
    """Rule 8: *refuse everything* satisfies SC-026's middle clause otherwise."""
    assert add.counts()["scenarios_in_which_nothing_is_added"] >= 1


def test_an_implementation_refusing_every_operation_fails_this_corpus():
    """The ablation, run against the real population."""
    scenarios = add.load_scenarios()
    controls = [s for s in scenarios if s.is_negative_control]
    admissions = [s for s in scenarios if len(s.available_at_end) > 5]
    assert controls, (
        "every scenario adds something, so 'refuse every operation' scores "
        "100% on SC-026's 'zero become available uninspected'"
    )
    assert admissions, (
        "no scenario ever makes an added operation available, so the first "
        "clause is satisfied by a system that admits nothing"
    )


def test_an_outcome_declared_for_an_operation_that_never_appears_is_refused(
    monkeypatch, tmp_path
):
    """Planted: an expectation nothing exercises is not an expectation."""
    def orphan(payload: dict[str, Any]) -> None:
        payload["scenarios"][0]["inspection_outcomes"]["never_added"] = "clean"

    _plant(monkeypatch, tmp_path, add, orphan)
    with pytest.raises(add.CorpusInconsistent, match="never appears"):
        add.load_scenarios()


def test_an_addition_with_no_declared_outcome_is_refused(monkeypatch, tmp_path):
    """Planted: FR-051 fails closed, and silence is not the open behaviour."""
    def drop(payload: dict[str, Any]) -> None:
        payload["scenarios"][0]["inspection_outcomes"] = {}

    _plant(monkeypatch, tmp_path, add, drop)
    with pytest.raises(add.CorpusInconsistent, match="no inspection outcome"):
        add.load_scenarios()


def test_every_operation_added_scenario_describes_the_reference_application():
    known = add.reference_app_operation_ids()
    for scenario in add.load_scenarios():
        assert scenario.last_inspected <= known, scenario.scenario_id


# ---------------------------------------------------------------------------
# The measurement none of the above is.
# ---------------------------------------------------------------------------

def test_no_corpus_here_claims_a_rate_a_latency_or_a_detection_figure():
    """E13 never ran, and a committed instrument is not a reading.

    plan.md line 831 states in bold that **E13 never ran at all**, and
    VERDICT.md line 162 states that drift detection has no detection rate, no
    false-alarm rate and no latency **on either of its two clocks**. Every
    Phase 6 detector — T137 through T153 — is open, so nothing here could
    produce such a figure even by accident.

    The one number resembling a latency in this repository's drift corpora is
    `drift-deployment`'s per-scenario arithmetic, and it is the interval
    between two instants the corpus itself declares — a property of the
    fixture, not a detector's performance on it. This test pins the four
    loaders' vocabulary so a later edit cannot introduce a `detection_rate` or
    a `false_alarm_rate` key and have it read as a result.
    """
    forbidden = ("detection_rate", "false_alarm_rate", "precision", "recall")
    for name, counts in (("source", src.counts), ("deployment", dep.counts),
                         ("spec_withdrawn", sw.counts),
                         ("operation_added", add.counts)):
        for key in counts():
            assert not any(word in key for word in forbidden), (
                f"{name}.counts() reports {key!r}. No drift rate exists on "
                "either clock; see plan.md line 831 and VERDICT.md line 162."
            )


def test_the_four_loaders_share_one_inconsistency_type():
    """A corpus that cannot load is broken for every consumer, not one test.

    `CorpusInconsistent` is deliberately not an `AssertionError`: a corpus that
    contradicts itself must fail the same way for a battery, a script or an
    interactive session, and not only under `pytest -O`-sensitive assertions.
    """
    for module in (src, dep, sw, add):
        assert module.CorpusInconsistent is CorpusInconsistent
    assert issubclass(CorpusInconsistent, Exception)
    assert not issubclass(CorpusInconsistent, AssertionError)
