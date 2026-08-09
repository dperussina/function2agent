"""T076 — the admission contract (**SC-018**), over T075's fixture set.

SC-018, in full:

    Across a fixture set covering every specification state — published and
    non-empty, absent, unreadable, and present but carrying no operations —
    **100%** of the non-admissible targets are rejected at admission with a
    named state and a named criterion, **zero** reach an agent session, and
    **zero** are admitted on a specification that fetched successfully but
    carried no operations.

## The two ways this file could pass while measuring nothing

Both have happened in this repository, so both are closed here explicitly
rather than assumed away.

**1. "100% of non-admissible targets are rejected" is trivially true over a
population with no non-admissible targets.** So the population is asserted
before it is scored: `test_the_fixture_set_covers_every_state_the_requirement_
names` and `test_the_population_has_both_dispositions` fail if any state is
unrepresented or if either disposition is empty. The floor is stated over
`FR_044_STATES` — the requirement's own list — as well as over `STATES`, so
adding a state to the classifier cannot dilute the requirement's four.

**2. "Rejected" is trivially true if the rejection came from something other
than admission.** A redaction test in this tree once passed with its mechanism
deleted, because it matched `pytest.raises(..., match="Secret")` and a different
guard one layer down refused using the same word. Nothing here matches words in
a message. What is asserted instead:

- the **state** is one of the closed set and is the one the committed
  `expected.json` names, taken from `classify` directly;
- the **criterion** is the object the `CRITERIA` registry declares for that
  state, compared field by field — so a rejection carrying a generic criterion
  fails even though it names *a* criterion;
- the state-to-rule-id mapping over the whole population is **injective**, so a
  classifier that named one criterion for everything is caught;
- `check` **returns** for every case and never raises, so a rejection cannot
  have arrived as an exception from the parser, the transport, or anything else
  one layer down. If it had, `check` would raise instead of producing a
  classified decision, and `test_check_returns_a_decision_for_every_case_and_
  raises_for_none` fails;
- `NotAdmitted` carries `.state` and `.criterion` as **attributes**, and the
  gate arms assert on those rather than on `str(exc)`.

**And the controls are checked for carrying the treatment.** A negative control
that carried the treatment is the other failure recorded here: tasks were
labelled controls because no step crossed a threshold, while a second mechanism
bound at a lower one still produced the effect. The admissible cases are the
controls in this file — they are the population that must *not* be rejected —
so `test_every_admissible_case_is_admissible_for_the_stated_reason` mutates each
of them in exactly one recorded property and requires the state to move to one
named other state. That converts "this case is admitted" into "this case is
admitted because the status is 200, the document parses, and it describes at
least one operation", and it is the arm that would catch an admissible fixture
that was admitted for an incidental reason.

## "Zero reach an agent session" is asserted against a real session table

Not against a spy. The `start` callable handed to `gate` creates a row in a real
`src.supervisor.session_table.SessionTable` — the table the ownership map makes
the supervisor's sole property and the one a session's existence *is*. After the
whole population has been through the gate, every non-admissible case's session
id is absent from that table and every admissible case's is present. "Zero
reached a session" therefore means zero rows, in the store a session lives in,
rather than zero calls to a function written for this test.

What this file does **not** claim: that the runtime's startup path calls `gate`.
It does not yet — `src/runtime/main.py` says so in its own exit message, and
T077 through T082 are what build the sequence around this stage. The claim here
is about the gate, which is where FR-044's *"MUST NOT start an agent session
against that target"* is implemented.
"""

from __future__ import annotations

import hashlib
import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from src.analysis import admission
from src.analysis.admission import (
    ADMISSIBLE_STATES,
    CRITERIA,
    FR_044_STATES,
    PUBLISHED_NON_EMPTY,
    READABLE_NO_OPERATIONS,
    STATES,
    UNPARSEABLE,
    UNREACHABLE,
    UNREADABLE_BY_CREDENTIAL,
    ABSENT,
    AdmissionError,
    FetchResponse,
    NotAdmitted,
    UnclassifiableResponse,
    check,
    classify,
    fetch_from_file,
    fetch_over_http,
    gate,
)
from src.analysis.admission_record import AdmissionRecord, latest, record
from src.analysis.artifact_store import ArtifactStore
from src.contracts.ownership import ROLE_ANALYSIS
from src.contracts.repository import Repository
from src.supervisor.session_table import SessionTable
from tests.fixtures.admission import cases_by_state, load_cases

CASES = load_cases()
NON_ADMISSIBLE = tuple(c for c in CASES if not c.expected_admitted)
ADMISSIBLE = tuple(c for c in CASES if c.expected_admitted)

#: The mutation table for the controls. One recorded property changed, and the
#: state the change must produce. Every entry is a **single** property, because
#: two at once would not say which one was load-bearing.
MUTATIONS: tuple[tuple[str, dict[str, object], str], ...] = (
    ("the origin stops serving it", {"status": 404}, ABSENT),
    ("the credential is refused", {"status": 401}, UNREADABLE_BY_CREDENTIAL),
    ("the origin errors", {"status": 502}, UNREACHABLE),
    ("nothing answers",
     {"status": None, "transport_error": "URLError: refused"}, UNREACHABLE),
    ("the operation list is emptied",
     {"body_file": None, "body_text": '{"operations": []}'},
     READABLE_NO_OPERATIONS),
    ("the shape becomes one v1 does not support",
     {"body_file": None, "body_text": '{"openapi": "3.0.3", "paths": {}}'},
     UNPARSEABLE),
)


# ---------------------------------------------------------------------------
# The population. Everything below is scored over it, so it is asserted first.


def test_the_fixture_set_covers_every_state_the_requirement_names() -> None:
    """SC-018's *"a fixture set covering every specification state"*.

    Stated over FR-044's own four **and** over the classifier's full set. The
    first is what the requirement asks for; the second is what stops a state
    being added to `admission.py` and never exercised, which would make a green
    run cover less than the classifier can do.
    """
    covered = set(cases_by_state())
    missing_from_requirement = [s for s in FR_044_STATES if s not in covered]
    assert missing_from_requirement == [], (
        f"FR-044 enumerates {list(FR_044_STATES)} and the fixture set has no "
        f"case for {missing_from_requirement}. 100% of non-admissible targets "
        "rejected is trivially true over a population that omits a state."
    )
    missing_from_classifier = [s for s in STATES if s not in covered]
    assert missing_from_classifier == [], (
        f"the classifier can return {missing_from_classifier} and no committed "
        "case exercises it (FR-053: a state with no fixture is not covered)"
    )


def test_the_population_has_both_dispositions() -> None:
    """A set with no rejections, or no admissions, scores nothing.

    The first half is the vacuity floor on "100% rejected". The second is the
    floor on the *gate* — a gate that refused everything would satisfy every
    rejection assertion in this file.
    """
    assert len(NON_ADMISSIBLE) >= len(STATES) - len(ADMISSIBLE_STATES), (
        f"{len(NON_ADMISSIBLE)} non-admissible case(s) for "
        f"{len(STATES) - len(ADMISSIBLE_STATES)} non-admissible state(s)"
    )
    assert len(ADMISSIBLE) >= 2, (
        "fewer than two admissible cases. One admitted point cannot "
        "distinguish 'admits the right thing' from 'admits that one thing'."
    )
    assert len(CASES) == len(NON_ADMISSIBLE) + len(ADMISSIBLE) == 14, (
        f"the population moved to {len(CASES)} cases. If a case was added or "
        "removed on purpose, update this number — a floor that tracks the set "
        "it measures is not a floor."
    )


def test_the_only_admissible_state_is_the_first_one_fr_044_names() -> None:
    """FR-044: *"MUST admit only the first"*."""
    assert ADMISSIBLE_STATES == frozenset({PUBLISHED_NON_EMPTY})
    assert FR_044_STATES[0] == PUBLISHED_NON_EMPTY
    for case in CASES:
        assert case.expected_admitted == (
            case.expected_state in ADMISSIBLE_STATES), (
            f"{case.name}: expected.json says admitted={case.expected_admitted} "
            f"for state {case.expected_state}"
        )


# ---------------------------------------------------------------------------
# The classification, against the committed expected output.


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.name)
def test_each_case_classifies_into_the_state_its_expected_output_names(case) -> None:
    """FR-053's *asserted expected output*, one case at a time.

    The comparison is against `expected.json`, which was written from FR-044's
    text before the classifier was run against it. A test that compared against
    the classifier's own output would be a tautology with a fixture in front.
    """
    classification = classify(case.response())
    assert classification.state == case.expected_state, (
        f"{case.name} classified {classification.state}, expected "
        f"{case.expected_state}.\n  evidence: {classification.evidence}\n"
        f"  why this case is in that state: {case.expected['exercises']}"
    )


@pytest.mark.parametrize("case", ADMISSIBLE, ids=lambda c: c.name)
def test_each_admissible_case_yields_the_operations_its_expected_output_names(
    case,
) -> None:
    """The half of an admissible expectation that is not the state name.

    A classifier returning `published_non_empty` for every input satisfies the
    state assertion. It does not reproduce five specific operation identifiers
    in the order the committed document lists them.
    """
    classification = classify(case.response())
    found = tuple(str(op["operation_id"]) for op in classification.operations)
    assert found == case.expected_operation_ids, (
        f"{case.name} yielded {found}, expected {case.expected_operation_ids}"
    )


def _only(state: str):
    cases = cases_by_state()[state]
    assert cases, f"no case in the {state} state"
    return cases


def test_a_refused_credential_is_not_reported_as_an_absent_specification() -> None:
    """FR-044 distinguishes these two, and the remedies are opposite.

    `absent` tells the operator to publish a specification; `unreadable` tells
    them the specification is there and to grant access to it. Folding the
    second into the first sends an operator to change something that is already
    correct — a wrong answer rather than a coarse one. Asserted as its own test,
    not only inside the parametrized sweep, so a removal proof can name it.
    """
    for case in _only(UNREADABLE_BY_CREDENTIAL):
        classification = classify(case.response())
        assert classification.state == UNREADABLE_BY_CREDENTIAL
        assert classification.state != ABSENT, (
            f"{case.name}: a credential refusal is evidence the specification "
            "is *there*"
        )


def test_an_origin_that_never_answered_is_not_reported_as_publishing_nothing(
) -> None:
    """`unreachable` is the absence of an answer, not an answer of absence."""
    for case in _only(UNREACHABLE):
        classification = classify(case.response())
        assert classification.state == UNREACHABLE
        assert classification.state != ABSENT, (
            f"{case.name}: nothing answered, so whether a specification is "
            "published there is unknown — that is not evidence there is none"
        )


def test_an_unsupported_shape_is_not_reported_as_an_empty_specification() -> None:
    """FR-053's boundary, and the misreport it prevents.

    Returning an empty operation list for a document nobody could read would
    classify `readable_no_operations` and tell the operator their specification
    is empty. It is not empty; it is in a shape v1 does not read, and `ADM-005`
    says so.
    """
    for case in _only(UNPARSEABLE):
        classification = classify(case.response())
        assert classification.state == UNPARSEABLE
        assert classification.state != READABLE_NO_OPERATIONS, (
            f"{case.name}: nobody read this document, so nothing is known "
            "about how many operations it describes"
        )
        assert case.expected_rule_id == "ADM-005"


def test_the_reference_application_case_reads_the_document_t116_committed() -> None:
    """The admissible case is not a copy that could drift.

    `tests/unit/test_reference_app.py` reconciles `ROUTES` against
    `served_operations.json` in both directions. A copy of that document here
    would be outside that reconciliation and could come to describe a surface
    the reference application does not serve — while this file went on
    admitting it.
    """
    repo = Path(__file__).resolve().parent.parent.parent
    published = repo / "tests" / "fixtures" / "reference-app" / "served_operations.json"
    case = next(c for c in CASES if c.name == "published-reference-app")
    assert case.response().body == published.read_bytes(), (
        "the admissible case's body is not byte-identical to the reference "
        "application's committed specification"
    )
    document = json.loads(published.read_text())
    assert case.expected_operation_ids == tuple(
        op["operation_id"] for op in document["operations"])


# ---------------------------------------------------------------------------
# 100% rejected, with a named state and a named criterion.


def test_one_hundred_percent_of_non_admissible_cases_are_rejected() -> None:
    """SC-018's first clause, as a share rather than a per-case assertion.

    Computed and compared to 1.0 over a denominator asserted non-zero, because
    "every case in an empty list was rejected" is the shape this file exists to
    refuse.
    """
    assert NON_ADMISSIBLE, "no non-admissible cases; the share is undefined"
    rejected = [
        c for c in NON_ADMISSIBLE
        if not check(c.response(), deployment_id=f"d-{c.name}").admitted
    ]
    share = len(rejected) / len(NON_ADMISSIBLE)
    assert share == 1.0, (
        f"{len(rejected)}/{len(NON_ADMISSIBLE)} non-admissible cases rejected "
        f"({share:.0%}); SC-018 requires 100%. Admitted: "
        f"{[c.name for c in NON_ADMISSIBLE if c not in rejected]}"
    )


@pytest.mark.parametrize("case", NON_ADMISSIBLE, ids=lambda c: c.name)
def test_every_rejection_names_the_state_and_the_criterion_the_registry_declares(
    case,
) -> None:
    """SC-018's *"with a named state and a named criterion"*.

    The criterion is compared **field by field against the registry**, not
    checked for being non-empty. A rejection carrying a plausible generic
    criterion would satisfy "names a criterion" and would tell every operator
    the same thing; this fails it.
    """
    decision = check(case.response(), deployment_id=f"d-{case.name}")
    declared = CRITERIA[case.expected_state]

    assert decision.state in STATES
    assert decision.state == case.expected_state
    assert decision.rule_id == case.expected_rule_id == declared.rule_id
    assert decision.criterion is declared, (
        f"{case.name}: the decision carries a criterion object that is not the "
        f"registry's entry for {decision.state}. A criterion assembled at the "
        "call site can drift from the one a stored record names."
    )
    assert decision.criterion.criterion == declared.criterion
    assert decision.criterion.reason == declared.reason
    assert decision.criterion.operator_action == declared.operator_action
    assert decision.criterion.operator_action, (
        f"{case.name}: rejected with no operator action. FR-044 requires the "
        "rejection to say what the operator would have to change."
    )


def test_the_state_to_criterion_mapping_is_injective_over_the_population() -> None:
    """A generic rejection is not a named criterion.

    Every assertion above would hold if one criterion fired for every state:
    each rejection would name *a* state and *a* criterion. What distinguishes a
    classification from a refusal is that different states name different
    criteria, and that is what this asserts — over the states the fixtures
    actually produced, not over the registry, so an unreachable registry entry
    cannot supply the distinctness.
    """
    produced: dict[str, set[str]] = {}
    for case in NON_ADMISSIBLE:
        decision = check(case.response(), deployment_id=f"d-{case.name}")
        produced.setdefault(decision.state, set()).add(decision.rule_id)

    for state, rule_ids in produced.items():
        assert len(rule_ids) == 1, f"{state} produced several rule ids: {rule_ids}"
    flat = [next(iter(v)) for v in produced.values()]
    assert len(flat) == len(set(flat)), (
        f"the population produced {len(produced)} distinct state(s) and "
        f"{len(set(flat))} distinct rule id(s): {produced}. Two states sharing "
        "a criterion makes 'a named criterion' true and uninformative."
    )
    assert len(produced) >= 3, (
        f"only {len(produced)} rejected state(s) were produced, so injectivity "
        "is being asserted over almost nothing"
    )


def test_check_returns_a_decision_for_every_case_and_raises_for_none() -> None:
    """The direct answer to "did the rejection come from admission?"

    If any rejection in this file arrived as an exception from the parser, the
    transport, or a guard one layer down, then `check` would raise for that
    case rather than returning a classified decision — and this fails. A
    rejection that is a *returned value carrying a state* cannot have been
    produced by something that does not know about states.
    """
    for case in CASES:
        try:
            decision = check(case.response(), deployment_id=f"d-{case.name}")
        except Exception as exc:  # noqa: BLE001 - the point is that none is raised
            pytest.fail(
                f"{case.name}: check() raised {type(exc).__name__}: {exc}. A "
                "rejection must be a supportable answer that is recorded "
                "(FR-044, T074), and an exception here means the disposition "
                "was decided by something other than the classifier."
            )
        assert decision.state in STATES
        assert decision.criterion.state == decision.state


def test_zero_are_admitted_on_a_specification_that_fetched_and_carried_no_operations(
) -> None:
    """SC-018's third clause, and FR-044's own singled-out sentence.

    The case is asserted to be a **complete success up to emptiness** before the
    disposition is checked: status 200, a body present, and a body that parses
    into a supported shape. Without those three the test would pass for the
    wrong reason — a fixture that happened to 404 would also not be admitted,
    and nothing about the emptiness rule would have been exercised.
    """
    cases = cases_by_state()[READABLE_NO_OPERATIONS]
    assert cases, "no case in the readable_no_operations state"
    for case in cases:
        response = case.response()
        assert response.status == 200, (
            f"{case.name}: status {response.status}. This case has to be a "
            "successful fetch, or it is not testing the empty-specification "
            "rule."
        )
        assert response.body, f"{case.name}: no body, so nothing was read"
        # The body parses. Asserted through the parser rather than by eye, so
        # the case cannot silently become an `unparseable` one.
        assert admission.parse_operations(response.body) == ()

        decision = check(response, deployment_id=f"d-{case.name}")
        assert decision.admitted is False
        assert decision.state == READABLE_NO_OPERATIONS, (
            f"{case.name} classified {decision.state}. FR-044 forbids reading "
            "an empty specification as a deployment that serves nothing, and "
            "it also forbids reading it as absent — the fetch succeeded."
        )
        assert decision.state != ABSENT
        assert decision.rule_id == "ADM-004"


# ---------------------------------------------------------------------------
# Zero reach an agent session.


def _session_table(tmp_path: Path) -> SessionTable:
    return SessionTable(tmp_path / "sessions.db")


def _start_a_session(sessions: SessionTable, case_name: str) -> None:
    sessions.create(
        session_id=f"s-{case_name}",
        tenant_id="t-admission",
        deployment_id=f"d-{case_name}",
        # Distinct per case: the table holds one session per capability, and a
        # shared digest would make the *second* admissible case fail on
        # uniqueness rather than on admission.
        capability_sha256=hashlib.sha256(case_name.encode()).hexdigest(),
        lease_expires_at=1_000.0,
        now=1.0,
    )


def test_zero_non_admissible_targets_reach_an_agent_session(tmp_path: Path) -> None:
    """SC-018's second clause, against the table a session's existence is.

    `gate` is handed a callable that creates a real row in the supervisor's
    `session` table. Afterwards, no non-admissible case's session id is in it.
    The assertion is over stored rows rather than over a call counter, so a gate
    that called the callable and had the write fail for an unrelated reason
    would not read as a pass.
    """
    with _session_table(tmp_path) as sessions:
        refusals = []
        for case in NON_ADMISSIBLE:
            decision = check(case.response(), deployment_id=f"d-{case.name}")
            with pytest.raises(NotAdmitted) as raised:
                gate(decision, lambda c=case: _start_a_session(sessions, c.name))
            # The attributes, not the message. A message match would pass
            # against any guard anywhere that used the same words.
            assert raised.value.state == case.expected_state
            assert raised.value.criterion is CRITERIA[case.expected_state]
            assert raised.value.decision is decision
            refusals.append(case.name)

        assert len(refusals) == len(NON_ADMISSIBLE)
        reached = [c.name for c in NON_ADMISSIBLE
                   if sessions.get(f"s-{c.name}") is not None]
        assert reached == [], (
            f"{len(reached)} non-admissible target(s) reached a session: "
            f"{reached}. FR-044: no agent session is started against a target "
            "that did not pass admission."
        )


def test_an_admissible_target_does_reach_a_session(tmp_path: Path) -> None:
    """The gate's own vacuity floor.

    A `gate` whose body were `raise NotAdmitted(...)` unconditionally satisfies
    every assertion in the test above. This is the arm that separates "refuses
    the non-admissible" from "refuses".
    """
    with _session_table(tmp_path) as sessions:
        for case in ADMISSIBLE:
            decision = check(case.response(), deployment_id=f"d-{case.name}")
            gate(decision, lambda c=case: _start_a_session(sessions, c.name))

        started = [c.name for c in ADMISSIBLE
                   if sessions.get(f"s-{c.name}") is not None]
        assert started == [c.name for c in ADMISSIBLE], (
            f"only {started} of {[c.name for c in ADMISSIBLE]} admissible "
            "cases reached a session; the gate is refusing what it should admit"
        )


def test_the_gate_evaluates_nothing_before_it_refuses(tmp_path: Path) -> None:
    """Refusing after the side effect is not refusing.

    `gate` takes a nullary callable so that a rejection cannot have already run
    the work. Asserted with a callable that raises if it is reached at all,
    which distinguishes "the session was not created" from "the session was
    created and then rolled back".
    """
    case = NON_ADMISSIBLE[0]
    decision = check(case.response(), deployment_id=f"d-{case.name}")

    def must_not_run() -> None:
        raise AssertionError(
            "gate evaluated the start callable for a non-admissible decision")

    with pytest.raises(NotAdmitted):
        gate(decision, must_not_run)


# ---------------------------------------------------------------------------
# The controls, checked for carrying the treatment.


def test_every_admissible_case_is_admissible_for_the_stated_reason() -> None:
    """The controls do not carry the treatment.

    Each admissible case is mutated in **one** recorded property and the
    resulting state must be the one that property decides. Six mutations per
    case, and each names a different branch of the classifier — so "this case
    is admitted" becomes "this case is admitted because status is 200, the body
    parses into a supported shape, and it describes at least one operation".

    Without this arm, an admissible fixture that classified
    `published_non_empty` for an incidental reason — a classifier that admitted
    on a non-empty *body* rather than a non-empty *operation list*, say — would
    pass every other assertion in this file.
    """
    attempted = 0
    for case in ADMISSIBLE:
        baseline = classify(case.response())
        assert baseline.state == PUBLISHED_NON_EMPTY
        for label, override, expected in MUTATIONS:
            mutated = classify(case.response_with(**override))
            attempted += 1
            assert mutated.state == expected, (
                f"{case.name}: {label} ({override}) produced "
                f"{mutated.state}, expected {expected}. The case is therefore "
                "not admissible for the reason stated — the property that was "
                "changed is not what its admission turns on."
            )
            assert mutated.state != PUBLISHED_NON_EMPTY
            assert mutated.operations == ()
    assert attempted == len(ADMISSIBLE) * len(MUTATIONS) == 12, (
        f"{attempted} mutations attempted. A control loop that iterates "
        "nothing asserts nothing, and this is the count that says it ran."
    )


def test_every_mutation_names_a_distinct_branch_of_the_classifier() -> None:
    """A mutation table with two entries reaching the same state proves less.

    Not a bug on its own — two mutations legitimately reach `unreachable` — but
    the table must reach at least four distinct states, or the six entries are
    covering fewer branches than their count suggests.
    """
    reached = {expected for _, _, expected in MUTATIONS}
    assert len(reached) >= 4, (
        f"the six mutations reach only {sorted(reached)}; the table is "
        "narrower than it looks"
    )
    assert PUBLISHED_NON_EMPTY not in reached


# ---------------------------------------------------------------------------
# The classifier has no default state.


def test_an_unenumerated_status_is_refused_rather_than_defaulted() -> None:
    """A fall-through would make one state the accepting set of everything else.

    Finding 032's defect exactly: an outcome whose accepting set is "none of the
    others" swallows every shape nobody thought of. `classify` enumerates and
    raises for the residue, and a refusal here is a loud authoring signal rather
    than a silent misclassification.
    """
    for status in (204, 301, 302, 418):
        with pytest.raises(UnclassifiableResponse, match="matches no"):
            classify(FetchResponse(status=status, body=None, location="x"))


def test_a_success_with_no_body_is_a_transport_defect_not_a_state() -> None:
    with pytest.raises(UnclassifiableResponse, match="no body"):
        classify(FetchResponse(status=200, body=None, location="x"))


def test_every_state_has_exactly_one_criterion_and_a_distinct_rule_id() -> None:
    assert set(CRITERIA) == set(STATES)
    ids = [c.rule_id for c in CRITERIA.values()]
    assert len(ids) == len(set(ids)) == len(STATES)
    assert all(i.startswith("ADM-") for i in ids)
    for state, criterion in CRITERIA.items():
        assert criterion.state == state
        assert bool(criterion.operator_action) == (state not in ADMISSIBLE_STATES)


def test_a_rejected_classification_cannot_carry_an_operation_list() -> None:
    """A set a caller could act on after admission refused it.

    Separate from the test below, which refuses the opposite pairing, so that
    removing either guard is attributable to one assertion.
    """
    with pytest.raises(AdmissionError, match="can act on after admission"):
        admission.Classification(
            state=ABSENT, operations=({"operation_id": "x"},), evidence="e")


def test_the_admitted_state_cannot_be_recorded_with_no_operations() -> None:
    """The exact pairing FR-044 singles out, entering under the state that
    admits."""
    with pytest.raises(AdmissionError, match="singles out"):
        admission.Classification(
            state=PUBLISHED_NON_EMPTY, operations=(), evidence="e")


# ---------------------------------------------------------------------------
# The transports, exercised against real origins rather than recordings.


def test_the_file_transport_reports_the_three_filesystem_outcomes(
    tmp_path: Path,
) -> None:
    """Present, absent and refused, from a real filesystem.

    The recorded cases assert what the classifier does with each shape; this
    asserts that the transport actually produces them. A transport that mapped
    every failure onto 404 would leave every recorded 403 case scoring a shape
    nothing produces.
    """
    present = tmp_path / "served_operations.json"
    present.write_text('{"operations": [{"operation_id": "a"}]}')
    assert classify(fetch_from_file(present)).state == PUBLISHED_NON_EMPTY

    assert classify(fetch_from_file(tmp_path / "nope.json")).state == ABSENT
    # A directory is not a specification, and it is absent rather than
    # unreadable: nothing there refused a credential.
    assert classify(fetch_from_file(tmp_path)).state == ABSENT

    def refuse(_path: Path) -> bytes:
        raise PermissionError(13, "Permission denied")

    refused = fetch_from_file(present, read=refuse)
    assert refused.status == 403
    assert classify(refused).state == UNREADABLE_BY_CREDENTIAL


class _SpecHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    #: path -> (status, body). Set on the subclass built per test.
    ROUTES: dict[str, tuple[int, bytes]] = {}

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler's name
        status, body = self.ROUTES.get(self.path, (404, b"{}"))
        # The credential arrives in a header and is required by /gated, which
        # is how the 401 arm is produced by a real origin decision.
        if self.path == "/gated" and self.headers.get("Authorization") != "Bearer ok":
            status, body = 401, b'{"error": "authentication required"}'
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args: object) -> None:
        """Silent: the request line carries the path, and T070 has a removal
        proof on exactly that leak in the product's own surface."""


@pytest.fixture()
def origin():
    """A loopback origin that publishes a specification. Torn down always."""
    published = json.dumps({
        "schema_version": "1.0.0",
        "deployment_id": "d-live",
        "operations": [{"operation_id": "live_operation", "method": "GET",
                        "path_template": "/live"}],
    }).encode()

    handler = type("Handler", (_SpecHandler,), {"ROUTES": {
        "/served-operations": (200, published),
        "/gated": (200, published),
        "/empty": (200, b'{"operations": []}'),
    }})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_the_http_transport_classifies_a_live_origin(origin: str) -> None:
    """The four states a live origin can put the classifier in, over real HTTP.

    The recorded fixtures are the population SC-018 is measured over; this is
    the arm that says the shapes they record are shapes something produces. An
    HTTP transport whose only evidence was a recorded response would be an
    untested transport with a fixture in front of it.
    """
    ok = fetch_over_http(f"{origin}/served-operations", timeout_seconds=5.0)
    assert ok.status == 200
    assert classify(ok).state == PUBLISHED_NON_EMPTY

    missing = fetch_over_http(f"{origin}/absent", timeout_seconds=5.0)
    assert missing.status == 404
    assert classify(missing).state == ABSENT

    # The credential is what moves this one, and nothing else about the request.
    refused = fetch_over_http(f"{origin}/gated", timeout_seconds=5.0)
    assert refused.status == 401
    assert classify(refused).state == UNREADABLE_BY_CREDENTIAL
    accepted = fetch_over_http(
        f"{origin}/gated", credential="ok", timeout_seconds=5.0)
    assert accepted.status == 200
    assert classify(accepted).state == PUBLISHED_NON_EMPTY

    empty = fetch_over_http(f"{origin}/empty", timeout_seconds=5.0)
    assert classify(empty).state == READABLE_NO_OPERATIONS


def test_the_http_transport_reports_a_refused_connection_as_unreachable() -> None:
    """The recorded `unreachable-connection-refused` shape, produced live.

    Bound and closed rather than a fixed port, so the refusal is against an
    address nothing is listening on at this instant rather than against a port
    number that might be in use.
    """
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()

    response = fetch_over_http(
        f"http://127.0.0.1:{port}/served-operations", timeout_seconds=2.0)
    assert response.status is None
    assert response.transport_error
    assert classify(response).state == UNREACHABLE


def test_the_credential_never_reaches_the_url(origin: str) -> None:
    """FR-044's check runs with a credential, and a URL is what gets logged.

    Asserted on the location the decision records: a credential that travelled
    in the query string would be in the stored `specification_source` of every
    admission decision.
    """
    accepted = fetch_over_http(
        f"{origin}/gated", credential="a-secret-value", timeout_seconds=5.0)
    decision = check(accepted, deployment_id="d-live")
    assert "a-secret-value" not in decision.specification_source
    assert "a-secret-value" not in decision.evidence
    assert "a-secret-value" not in decision.operator_message()


# ---------------------------------------------------------------------------
# T074 — the decision is retained, both dispositions, and readable back.


def _store(tmp_path: Path) -> ArtifactStore:
    repository = Repository(
        tmp_path / "analysis.db", role=ROLE_ANALYSIS,
        tenant_id="t-admission", deployment_id="d-admission")
    return ArtifactStore(tmp_path, repository)


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.name)
def test_every_decision_is_retained_and_reads_back_with_its_three_named_things(
    case, tmp_path: Path
) -> None:
    """T074: *a rejection is a supportable answer and is retained, not an error*.

    Every case, both dispositions, through the real artifact store — and read
    back, because a record written and unreadable is not retained. The three
    fields FR-044 names are compared against the registry, so a record carrying
    a paraphrase written at the call site fails.
    """
    store = _store(tmp_path)
    decision = check(case.response(), deployment_id=f"d-{case.name}")
    stored = record(store, decision, now=1_700_000_000.0,
                    decided_by_host="runner-under-test",
                    decided_at="2026-08-09T00:00:00Z")
    assert stored.schema_version == "1.1.0"

    read_back = latest(store)
    assert read_back is not None
    assert read_back.specification_state == case.expected_state
    assert read_back.admitted == case.expected_admitted
    assert read_back.rule_id == case.expected_rule_id
    declared = CRITERIA[case.expected_state]
    assert read_back.criterion == declared.criterion
    assert read_back.reason == declared.reason
    assert read_back.operator_action == declared.operator_action
    assert read_back.specification_source == decision.specification_source


def test_a_rejection_is_not_lost_when_a_later_admission_replaces_it(
    tmp_path: Path,
) -> None:
    """FR-047's recovery path records a *new* decision; the old one stays.

    "New" is only meaningful against a stored old one, and past the staleness
    ceiling the recovery sequence has to be able to show what the previous
    admission said.
    """
    store = _store(tmp_path)
    rejected = next(c for c in NON_ADMISSIBLE if c.name == "absent-not-found")
    admitted = ADMISSIBLE[0]

    record(store, check(rejected.response(), deployment_id="d-t"),
           now=1.0, decided_by_host="h", decided_at="2026-08-09T00:00:00Z")
    first = latest(store)
    record(store, check(admitted.response(), deployment_id="d-t"),
           now=2.0, decided_by_host="h", decided_at="2026-08-09T00:00:01Z")
    second = latest(store)

    assert first is not None and second is not None
    assert first.admitted is False and second.admitted is True
    addresses = [row["content_hash"] for row in store.history("admission_decision")]
    assert len(addresses) == 2 and addresses[0] != addresses[1], (
        "the rejection's address is not in the retained history, so the "
        "previous decision cannot be shown"
    )


def test_a_rejection_record_without_a_remedy_cannot_be_constructed() -> None:
    """Guard 1 of T074's two. FR-044's third named term, enforced."""
    with pytest.raises(AdmissionError, match="what the operator would have"):
        AdmissionRecord(
            deployment_id="d-1", admitted=False, specification_state=ABSENT,
            rule_id="ADM-002", criterion="c", reason="r", operator_action="",
            specification_source="s", evidence="e")


def test_an_admitted_record_carrying_a_remedy_cannot_be_constructed() -> None:
    """Guard 2, and it is the opposite defect rather than the same one.

    A consumer reading `operator_action` to decide whether anything is
    outstanding would find an outstanding requirement against a target that
    passed. Separate from guard 1 so that removing either is attributable.
    """
    with pytest.raises(AdmissionError, match="carries an operator action"):
        AdmissionRecord(
            deployment_id="d-1", admitted=True,
            specification_state=PUBLISHED_NON_EMPTY, rule_id="ADM-001",
            criterion="c", reason="r", operator_action="do something",
            specification_source="s", evidence="e")


def test_a_record_cannot_disagree_with_its_own_state() -> None:
    with pytest.raises(AdmissionError, match="admits exactly"):
        AdmissionRecord(
            deployment_id="d-1", admitted=True, specification_state=ABSENT,
            rule_id="ADM-002", criterion="c", reason="r",
            operator_action="a", specification_source="s", evidence="e")


_LEGACY_DECISION = {
    "schema_version": "1.0.0", "deployment_id": "d-old", "admitted": False,
    "rule_id": "ADM-002", "reason": "no specification",
}


def test_the_migration_does_not_invent_a_state_a_1_0_0_record_never_named() -> None:
    """The migration marks the three fields unrecoverable rather than filling them.

    Supplying a plausible state would put a classification on a decision no
    classifier ever made — the same reason the location-set migration writes
    `FS-DECL-MIGRATED` rather than a plausible rule identifier.
    """
    from src.contracts import migrations

    migrated = migrations.migrate("admission_decision", dict(_LEGACY_DECISION))
    assert migrated["schema_version"] == "1.1.0"
    assert migrated["specification_state"] is None
    assert migrated["failed_criterion"] is None
    assert migrated["operator_action"] is None


def test_a_pre_1_1_0_record_is_refused_rather_than_read_as_a_classification(
) -> None:
    """Reading it back is refused, and separately from the migration above.

    Two mechanisms — the migration's honesty and the loader's refusal — with one
    assertion each, so removing either is attributable.
    """
    from src.contracts import migrations

    migrated = migrations.migrate("admission_decision", dict(_LEGACY_DECISION))
    with pytest.raises(AdmissionError, match="carries no specification state"):
        AdmissionRecord.from_document(migrated)
