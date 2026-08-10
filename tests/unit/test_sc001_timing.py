"""T118 — the SC-001 timing instrument's own floors.

Every clock here is a fake one. A timing test whose expectation is a property
of the host it happens to run on is a recurring defect in this tree, so the
splits below are exact integers everywhere rather than tolerances that hold on
a fast machine and not on a loaded one.

Each refusal is matched against **the wording of the mechanism it is aimed
at**, never against a generic error word. A test matching "invalid" would pass
against a completely different guard producing the same word, which is the
defect that shipped once already in the redaction tests.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.analysis.timing import (
    NO_CODEGRAPH_CAVEAT,
    NOT_INDEPENDENTLY_ASSESSABLE,
    SC001_WINDOW_SECONDS,
    NotVerifiableShare,
    Sc001Report,
    Sc001ReportError,
    Sc001Timer,
    Sc001Verdict,
    Sc001Window,
    SubjectSize,
)

REPO = Path(__file__).resolve().parents[2]
SIZE_DOCUMENT = REPO / "tests" / "fixtures" / "reference-app" / "size.json"


class FakeClock:
    """A clock that only moves when a test moves it."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def a_size(**overrides) -> SubjectSize:
    fields = {
        "files": 3,
        "lines": 606,
        "code_lines": 442,
        "definitions": 32,
        "measured_by": "a test",
    }
    fields.update(overrides)
    return SubjectSize(**fields)


def a_share(**overrides) -> NotVerifiableShare:
    fields = {"attempted": 4, "not_verifiable": 0, "by_reason": {}}
    fields.update(overrides)
    return NotVerifiableShare(**fields)


def a_window(total=100.0, analysis=40.0, first=60.0) -> Sc001Window:
    return Sc001Window(
        total_seconds=total,
        analysis_seconds=analysis,
        first_verified_answer_seconds=first,
    )


def a_report(**overrides) -> Sc001Report:
    fields = {
        "window": a_window(),
        "subject_size": a_size(),
        "not_verifiable": a_share(),
        "subject": "reference-app",
    }
    fields.update(overrides)
    return Sc001Report(**fields)


# --- the split ------------------------------------------------------------


def test_the_two_spans_are_reported_separately_and_the_remainder_is_named():
    payload = a_report(window=a_window(total=100.0, analysis=40.0)).to_dict()
    assert payload["analysis_seconds"] == 40.0
    assert payload["remainder_seconds"] == 60.0
    assert payload["total_seconds"] == 100.0


def test_a_window_with_no_analysis_span_is_a_fused_total_and_is_refused():
    """The defect T118 exists for: one figure over a bounded step and an
    unbounded one, true on small inputs and false on large ones."""
    clock = FakeClock()
    timer = Sc001Timer(clock=clock)
    timer.start()
    clock.advance(30.0)
    timer.first_verified_answer()
    with pytest.raises(Sc001ReportError, match="fused total"):
        timer.close()


def test_the_timer_subtracts_only_the_analysis_span():
    clock = FakeClock()
    timer = Sc001Timer(clock=clock)
    timer.start()
    clock.advance(5.0)
    with timer.analysis():
        clock.advance(20.0)
    clock.advance(7.0)
    timer.first_verified_answer()
    clock.advance(3.0)
    window = timer.close()
    assert window.total_seconds == 35.0
    assert window.analysis_seconds == 20.0
    assert window.remainder_seconds == 15.0
    assert window.first_verified_answer_seconds == 32.0


def test_two_analysis_spans_accumulate_into_one_figure():
    clock = FakeClock()
    timer = Sc001Timer(clock=clock)
    timer.start()
    with timer.analysis():
        clock.advance(4.0)
    clock.advance(1.0)
    with timer.analysis():
        clock.advance(6.0)
    timer.first_verified_answer()
    window = timer.close()
    assert window.analysis_seconds == 10.0
    assert window.total_seconds == 11.0


def test_an_analysis_span_larger_than_its_window_is_refused():
    with pytest.raises(Sc001ReportError, match="part larger than the whole"):
        Sc001Window(
            total_seconds=10.0,
            analysis_seconds=11.0,
            first_verified_answer_seconds=None,
        )


def test_a_window_that_was_never_started_measures_nothing():
    timer = Sc001Timer(clock=FakeClock())
    with pytest.raises(Sc001ReportError, match="from starting configuration"):
        timer.close()


def test_a_later_verified_answer_does_not_move_the_first():
    """SC-001 names the *first* verified answer. A harness that kept the last
    one would report the slowest question and call it the criterion."""
    clock = FakeClock()
    timer = Sc001Timer(clock=clock)
    timer.start()
    with timer.analysis():
        clock.advance(1.0)
    clock.advance(9.0)
    timer.first_verified_answer()
    clock.advance(500.0)
    timer.first_verified_answer()
    assert timer.close().first_verified_answer_seconds == 10.0


# --- the size -------------------------------------------------------------


def test_a_report_cannot_be_built_without_the_subject_size():
    with pytest.raises(Sc001ReportError, match="size of the application"):
        a_report(subject_size={"files": 3})


def test_every_serialized_report_states_the_subject_size():
    payload = a_report().to_dict()
    assert payload["subject_size"]["files"] == 3
    assert payload["subject_size"]["code_lines"] == 442
    assert payload["subject_size"]["measured_by"]


def test_a_size_of_zero_is_not_a_size():
    with pytest.raises(Sc001ReportError, match="divides nothing"):
        a_size(files=0)


def test_a_size_document_missing_a_field_is_not_defaulted():
    with pytest.raises(Sc001ReportError, match="drifted apart"):
        SubjectSize.from_document({"application_files": 3})


def test_the_reference_applications_committed_size_document_is_readable():
    """T116 measures it, T118 reads it. If the two shapes drift apart this is
    where it surfaces, rather than inside an SC-001 run."""
    size = SubjectSize.from_document(json.loads(SIZE_DOCUMENT.read_text()))
    assert size.files > 0 and size.code_lines > 0
    assert size.codegraph_nodes is None, (
        "size.json has grown a codegraph node count. Nothing has run "
        "codegraph against this application (T119 does not exist), so a "
        "number here would be derived from U-21's single datapoint."
    )


# --- FR-045's share -------------------------------------------------------


def test_a_report_cannot_be_built_without_the_not_verifiable_share():
    with pytest.raises(Sc001ReportError, match="FR-045"):
        a_report(not_verifiable=0.0)


def test_the_share_is_taken_over_the_attempted_set():
    share = NotVerifiableShare(
        attempted=4, not_verifiable=3, by_reason={"no_attestation": 3}
    )
    assert share.share == 0.75


def test_a_share_over_an_empty_population_is_refused():
    with pytest.raises(Sc001ReportError, match="not a low share"):
        NotVerifiableShare(attempted=0, not_verifiable=0)


def test_a_numerator_above_its_denominator_names_two_populations():
    with pytest.raises(Sc001ReportError, match="different populations"):
        NotVerifiableShare(
            attempted=2, not_verifiable=3, by_reason={"no_attestation": 3}
        )


def test_a_breakdown_that_does_not_sum_to_its_total_describes_neither():
    with pytest.raises(Sc001ReportError, match="broken down by refusal reason"):
        NotVerifiableShare(
            attempted=4, not_verifiable=3, by_reason={"no_attestation": 1}
        )


def test_no_threshold_is_applied_to_the_share():
    """FR-045 pre-registers none. A number invented in the instrument would be
    the inherited-number failure this corpus catches elsewhere."""
    payload = a_report(
        not_verifiable=a_share(
            not_verifiable=3, by_reason={"no_attestation": 3}
        )
    ).to_dict()
    assert payload["not_verifiable"]["threshold"] is None
    assert payload["not_verifiable"]["share"] == 0.75


# --- assessability --------------------------------------------------------


def test_a_harness_run_is_not_independently_assessable():
    """The vacuity shape this criterion invites: a green timing quoted with no
    mention of the refusal share that produced it."""
    payload = a_report().to_dict()
    assert payload["verdict"] == "first_verified_answer_within_window"
    assert payload["assessable"] is False
    assert payload["not_assessable_because"] == NOT_INDEPENDENTLY_ASSESSABLE


def test_a_production_window_makes_the_criterion_assessable():
    """The predicate can move — this is what separates it from a constant
    nobody can disagree with."""
    payload = a_report(not_verifiable=a_share(production=True)).to_dict()
    assert payload["assessable"] is True
    assert "not_assessable_because" not in payload


def test_no_verdict_says_the_criterion_was_met():
    values = {member.value for member in Sc001Verdict}
    assert values == {
        "no_verified_answer",
        "first_verified_answer_within_window",
        "first_verified_answer_outside_window",
    }


def test_a_run_that_verified_nothing_is_not_a_slow_run():
    window = a_window(first=None)
    assert window.verdict() is Sc001Verdict.NO_VERIFIED_ANSWER


def test_a_first_answer_past_the_window_is_outside_it():
    window = a_window(
        total=SC001_WINDOW_SECONDS + 10, analysis=1.0,
        first=SC001_WINDOW_SECONDS + 5,
    )
    assert window.verdict() is Sc001Verdict.FIRST_VERIFIED_ANSWER_OUTSIDE_WINDOW


# --- codegraph coverage ---------------------------------------------------


def test_an_analysis_figure_taken_without_codegraph_says_so():
    """T004 leaves the schema hash unset and T119 does not exist, so an
    analysis span today times a step that excludes the work U-21 is about."""
    payload = a_report().to_dict()
    assert payload["codegraph_invoked"] is False
    assert payload["analysis_coverage_caveat"] == NO_CODEGRAPH_CAVEAT
    assert "U-21" in NO_CODEGRAPH_CAVEAT


def test_a_run_that_did_invoke_codegraph_drops_the_caveat():
    payload = a_report(codegraph_invoked=True).to_dict()
    assert "analysis_coverage_caveat" not in payload
