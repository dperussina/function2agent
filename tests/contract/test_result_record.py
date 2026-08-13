"""T134 — the result record's three states, its staleness field, and the
exhaustiveness of the three (FR-025, FR-047, OD-19).

## Where the record lives, and why not where T126 says

T126, T127 and T128 all name `src/runtime/result.py`. **That module does not
exist and must not.** `src/contracts/result.py` has held `Result` and
`VerificationOutcome` since T021, and the path in the task text is stale in the
same way `T067`'s `src/runtime/terminal.py` was stale against the live
`src/contracts/terminal.py`.

The decisive argument is not precedent but the import graph, and it is
measurable rather than stylistic. `src/analysis/validate.py` constructs a
`Result` at module scope. At module level `src/analysis/` imports **only**
`src/contracts/`, while `src/runtime/` imports `src/analysis/`. A result record
under `src/runtime/` would therefore make `src/analysis/` import `src/runtime/`
— a hard circular import, not a layering preference. `tests/invariants/
test_layering.py` is the pin that keeps that true after this file stops being
the only thing that noticed.

## The three states are a partition, not a list of three names

FR-025 requires *"exactly one of three states — verified, failed verification,
or not verifiable"*, distinguishable by a consuming system. `VerificationOutcome`
carries **four** members, because `MODEL_ASSESSED` is a distinct thing a caller
may be told and Principle I exists to keep it distinct. Four members and three
states are reconciled by `REPORTED_STATE`, a total and disjoint map from every
outcome onto one state.

**That is what makes the exhaustiveness assertions here fail on a fourth without
being told about it.** A test spelling out three names is a change-detector: an
editor adding a state satisfies it by editing both sides. These arms instead
assert that the map's domain *is* `VerificationOutcome` and its image *is*
`ReportedState`, so a fifth outcome with no row fails, a row naming no outcome
fails, and a fourth state nothing maps onto fails — none of them mentioned
anywhere in this file. The remaining hole, a fourth state that some outcome *is*
remapped onto, is closed by reconciling against FR-025's own sentence in
`spec.md`, which is the `lifecycle-taxonomy` corpus check's shape: the artifact
that declares the count and the artifact that implements it are read against
each other rather than trusted to agree.

## Staleness is exercised as a product, not as a fourth name

FR-047 requires the stale marking to be *"a field separate from the verification
state"* which *"MUST NOT become a fourth value of it"*. Asserting that by
checking a field exists would pass against a record where some combination had
quietly become unrepresentable. So every state is built against every staleness
marking — the full product — and the arm fails if any cell stops being
constructible.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.analysis import admission
from src.contracts import result as result_module
from src.contracts.result import (
    FR_025_PHRASES,
    PRECISION_NOT_STATED,
    REPORTED_STATE,
    STALENESS_NOT_STATED,
    Corroboration,
    MissingVerification,
    Precision,
    PrecisionBasis,
    ReportedState,
    Result,
    StaleMarking,
    Staleness,
    VerificationOutcome,
)

REPO = Path(__file__).resolve().parent.parent.parent
SPEC = REPO / "specs" / "002-spec-aware-agent-runtime" / "spec.md"


def _corroboration_for(outcome: VerificationOutcome) -> Corroboration:
    """The one corroboration each outcome admits, so the arms below build a
    legal record without encoding the rule they are testing twice."""
    if outcome is VerificationOutcome.VERIFIED:
        return Corroboration.CORROBORATED
    return Corroboration.NOT_STATED


def _build(
    outcome: VerificationOutcome,
    staleness: Staleness = STALENESS_NOT_STATED,
) -> Result:
    return Result(
        outcome,
        payload={"answer": 1},
        corroboration=_corroboration_for(outcome),
        reason=None if outcome is VerificationOutcome.VERIFIED else "no contract",
        staleness=staleness,
    )


# ---------------------------------------------------------------------------
# Every state.


@pytest.mark.parametrize("outcome", list(VerificationOutcome), ids=lambda o: o.name)
def test_every_outcome_reports_exactly_one_state(outcome) -> None:
    """Parametrised over the enum, not over a written-out list of four.

    A member added to `VerificationOutcome` is exercised here the day it lands,
    which is the difference between a coverage claim and a coverage fact.
    """
    result = _build(outcome)

    assert isinstance(result.state, ReportedState)
    assert result.state is REPORTED_STATE[outcome]


@pytest.mark.parametrize("state", list(ReportedState), ids=lambda s: s.name)
def test_every_state_is_reachable_from_a_constructible_record(state) -> None:
    """The non-vacuity floor for the three.

    Without it, a state no outcome can produce would satisfy every structural
    arm below while being unreachable — a declared outcome nothing emits, which
    is the defect `lifecycle-taxonomy` was written for one taxonomy over.
    """
    built = [
        _build(outcome)
        for outcome in VerificationOutcome
        if REPORTED_STATE[outcome] is state
    ]

    assert built, f"no VerificationOutcome produces {state.name}"
    assert all(r.state is state for r in built)


def test_only_the_verified_state_reads_as_verified() -> None:
    """`is_verified` and the state field must not be able to disagree."""
    for outcome in VerificationOutcome:
        result = _build(outcome)
        assert result.is_verified is (result.state is ReportedState.VERIFIED)


# ---------------------------------------------------------------------------
# Exhaustiveness and mutual exclusivity, asserted so a fourth fails untold.


def test_the_map_domain_is_exactly_the_outcome_enum() -> None:
    """Both directions, and deliberately not collapsed into one comparison.

    A symmetric difference reported as a single set cannot tell a **rename**
    from one drop plus one add, and the two need different fixes: a rename means
    the map has to follow the enum, a drop means a member lost its state. So the
    two directions are asserted and reported separately.
    """
    members = set(VerificationOutcome)
    keys = set(REPORTED_STATE)

    assert not (members - keys), (
        "VerificationOutcome members with no row in REPORTED_STATE: "
        f"{sorted(m.name for m in members - keys)}. FR-025 requires every "
        "reported result to carry one of three states; an outcome with no "
        "state is a result that carries none."
    )
    assert not (keys - members), (
        "REPORTED_STATE rows naming no VerificationOutcome member: "
        f"{sorted(str(k) for k in keys - members)}. If a member was renamed, "
        "the map has to follow it."
    )


def test_the_map_image_is_exactly_the_state_enum() -> None:
    """A fourth state nothing maps onto fails here, unnamed.

    This is the arm that makes `ReportedState` exhaustive over what the record
    can actually report, rather than over what someone wrote down.
    """
    image = set(REPORTED_STATE.values())

    assert image == set(ReportedState), (
        "declared states that no outcome produces: "
        f"{sorted(s.name for s in set(ReportedState) - image)}"
    )


def test_each_outcome_maps_to_one_state_and_the_states_do_not_overlap() -> None:
    """Mutual exclusivity as a partition property over the outcomes.

    The three states are disjoint **as sets of outcomes**; asserting that the
    three enum members are distinct would be true of any enum and would check
    nothing.
    """
    covered: dict[VerificationOutcome, ReportedState] = {}
    for state in ReportedState:
        block = {o for o in VerificationOutcome if REPORTED_STATE[o] is state}
        overlap = block & covered.keys()
        assert not overlap, (
            f"{sorted(o.name for o in overlap)} fall in more than one state"
        )
        covered.update({o: state for o in block})

    assert covered.keys() == set(VerificationOutcome)


def _fr_025_paragraph() -> str:
    """FR-025's bullet, whitespace-collapsed.

    Collapsed because the requirement wraps mid-phrase — *"failed"* ends one
    line and *"verification"* begins the next — so a reader that respects the
    source's line breaks cannot find the phrase the requirement names.
    """
    lines = SPEC.read_text(encoding="utf-8").splitlines()
    start = next(
        (i for i, line in enumerate(lines) if line.startswith("- **FR-025**")),
        None,
    )
    assert start is not None, (
        f"no FR-025 bullet in {SPEC.name}. This arm reconciles the code against "
        "the requirement; if the requirement moved, it was not read at all, and "
        "a check that reads nothing agrees with everything."
    )
    end = next(
        (
            i
            for i in range(start + 1, len(lines))
            if lines[i].startswith("- **FR-")
        ),
        len(lines),
    )
    return " ".join(" ".join(lines[start:end]).split())


_COUNT_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6}


def test_the_state_count_agrees_with_the_requirement_that_declares_it() -> None:
    """The arm that catches a fourth state the partition cannot see.

    Remapping an existing outcome onto a newly added fourth state keeps the map
    total and disjoint and its image complete, so every structural arm above
    stays green. What it cannot keep is agreement with FR-025's own numeral —
    and the numeral lives in a file nobody edits by accident while editing an
    enum, which is the whole reason the two are read against each other.
    """
    paragraph = _fr_025_paragraph()
    match = re.search(r"exactly one of (\w+) states", paragraph)

    assert match is not None, (
        "FR-025 no longer declares its state count in the form this arm reads "
        f"(“exactly one of N states”). Paragraph read:\n{paragraph[:400]}"
    )
    declared = _COUNT_WORDS.get(match.group(1))
    assert declared is not None, f"unrecognised count word {match.group(1)!r}"
    assert declared == len(ReportedState), (
        f"FR-025 declares {declared} states and ReportedState has "
        f"{len(ReportedState)}: {sorted(s.name for s in ReportedState)}"
    )


@pytest.mark.parametrize("state", list(ReportedState), ids=lambda s: s.name)
def test_every_state_is_named_by_the_requirement(state) -> None:
    """A state the requirement does not name is one nobody authorised.

    Paired with the count arm above this closes both directions: the count
    catches a state added to the requirement and not to the code, and this
    catches one added to the code and not to the requirement.
    """
    phrase = FR_025_PHRASES[state]
    assert phrase in _fr_025_paragraph(), (
        f"FR-025 does not contain {phrase!r}, which {state.name} claims to be "
        "the requirement's wording for it"
    )


def test_the_phrase_table_covers_the_states_exactly() -> None:
    assert set(FR_025_PHRASES) == set(ReportedState)


# ---------------------------------------------------------------------------
# Staleness: a separate field, exercised as a full product.


@pytest.mark.parametrize("marking", list(StaleMarking), ids=lambda m: m.name)
@pytest.mark.parametrize("state", list(ReportedState), ids=lambda s: s.name)
def test_every_state_and_staleness_combination_is_representable(
    state, marking
) -> None:
    """The orthogonality assertion, as a product rather than as a sentence.

    FR-047 names two cells specifically — verified-and-stale and
    unverifiable-and-stale — but naming two would leave the rest unwatched, and
    a combination that became unconstructible is exactly how a separate field
    turns back into a fourth state. Every cell is built.
    """
    outcome = next(o for o in VerificationOutcome if REPORTED_STATE[o] is state)
    staleness = (
        Staleness(
            StaleMarking.STALE,
            age_seconds=61.0,
            specification_state=admission.ABSENT,
        )
        if marking is StaleMarking.STALE
        else Staleness(marking)
    )

    result = _build(outcome, staleness=staleness)

    assert result.state is state
    assert result.staleness.marking is marking
    assert result.is_stale is (marking is StaleMarking.STALE)


def test_staleness_is_not_a_member_of_either_state_taxonomy() -> None:
    """FR-047's *"MUST NOT become a fourth value of it"*, read structurally."""
    stale_words = {m.value for m in StaleMarking} | {"stale"}
    for enum in (ReportedState, VerificationOutcome):
        collisions = {m.name for m in enum if m.value in stale_words}
        assert not collisions, (
            f"{enum.__name__} has acquired {sorted(collisions)}. Staleness is a "
            "separate field on the same record and never a state."
        )


def test_a_stale_marking_carries_its_age_and_the_state_last_found() -> None:
    """FR-047 asks for three facts, not one flag."""
    staleness = Staleness(
        StaleMarking.STALE,
        age_seconds=930.0,
        specification_state=admission.READABLE_NO_OPERATIONS,
    )

    assert staleness.age_seconds == 930.0
    assert staleness.specification_state == admission.READABLE_NO_OPERATIONS


def test_a_stale_marking_without_an_age_is_refused() -> None:
    """A stale marking with no age cannot be compared against the ceiling.

    FR-047's ceiling is measured from the last successful fetch, so a marking
    that cannot say how old it is records the risk without recording the thing
    that bounds it.
    """
    with pytest.raises(ValueError, match="age"):
        Staleness(StaleMarking.STALE, specification_state=admission.ABSENT)


def test_a_fresh_marking_carrying_an_age_is_refused() -> None:
    """The other direction, so the two fields cannot disagree silently."""
    with pytest.raises(ValueError, match="age"):
        Staleness(StaleMarking.FRESH, age_seconds=1.0)


@pytest.mark.parametrize("state", sorted(admission.STATES))
def test_every_specification_state_the_admission_check_can_report_is_accepted(
    state,
) -> None:
    """Reconciled against `admission.STATES` rather than importing it.

    `src/contracts/` is the bottom of the import graph and importing
    `src/analysis/admission` into it would invert that. The tree's own
    precedent for this is `src/contracts/transition.py`, which duplicates the
    session-lifecycle constants and has a test assert the two agree — *"a
    check, where an import would be an assumption"*.
    """
    staleness = Staleness(
        StaleMarking.STALE, age_seconds=1.0, specification_state=state
    )
    assert staleness.specification_state == state


def test_the_duplicated_specification_states_agree_with_the_admission_check() -> None:
    """The other direction of the same reconciliation, reported separately.

    Kept apart from the accept-each arm above because a set equality collapses
    a **rename** into one drop plus one add, and those need different fixes.
    """
    declared = set(result_module.SPECIFICATION_STATES)
    reported = set(admission.STATES)

    assert not (reported - declared), (
        "admission.py can report states src/contracts/result.py will refuse: "
        f"{sorted(reported - declared)}"
    )
    assert not (declared - reported), (
        "src/contracts/result.py accepts states nothing reports: "
        f"{sorted(declared - reported)}"
    )


def test_an_unknown_specification_state_is_refused() -> None:
    """The positive control's negative half.

    Without it the arm above would pass against a field that accepts any
    string, which is not the same as accepting the admission check's states.
    """
    with pytest.raises(ValueError, match="specification state"):
        Staleness(
            StaleMarking.STALE, age_seconds=1.0, specification_state="probably_fine"
        )


# ---------------------------------------------------------------------------
# The constructor: one, and it takes the verification's provenance.


def test_the_record_has_exactly_one_constructor() -> None:
    """T126. Alternative constructors are what let one of them skip a rule.

    A `classmethod` returning `Result` would be a second way in, and the rule
    this record turns on — no verified state without corroboration — would then
    hold only wherever someone remembered to route through `__init__`.
    """
    builders = [
        name
        for name, member in vars(Result).items()
        if isinstance(member, (classmethod, staticmethod))
    ]
    assert builders == [], f"Result has alternative constructors: {builders}"


def test_corroboration_is_required_and_has_no_default() -> None:
    """The defect this record was reshaped around.

    `provisional: bool = False` meant both *corroborated* and *nobody said*, and
    the safe-looking value was the default. There is now no value of the field
    a caller can omit their way into.
    """
    with pytest.raises(TypeError):
        Result(  # type: ignore[call-arg]
            VerificationOutcome.VERIFIED, payload={"answer": 1}
        )


def test_a_verified_state_cannot_be_built_without_corroboration() -> None:
    """T127's *unconstructible rather than merely nameable*.

    Both absent readings are refused: `NOT_STATED` is the caller who says
    nothing corroborated it, `PROVISIONAL` is T021's original refusal.
    """
    for corroboration in (Corroboration.NOT_STATED, Corroboration.PROVISIONAL):
        with pytest.raises(MissingVerification, match="corroborat|provisional"):
            Result(
                VerificationOutcome.VERIFIED,
                payload={"answer": 1},
                corroboration=corroboration,
            )


def test_a_corroborated_verified_record_is_constructible() -> None:
    """The positive control. Without it every arm above passes against a record
    that refuses everything, which is not the property being asserted."""
    result = Result(
        VerificationOutcome.VERIFIED,
        payload={"answer": 1},
        corroboration=Corroboration.CORROBORATED,
    )

    assert result.state is ReportedState.VERIFIED
    assert result.is_verified is True


def test_the_absent_case_is_a_named_member_and_not_a_falsy_value() -> None:
    """`spend_usd is None` against a measured zero, in the shape it was fixed.

    The absent case has a name a consumer can branch on. Asserted as a
    non-membership too: a boolean field would make *nobody said* and
    *corroborated* the same value again.
    """
    assert Corroboration.NOT_STATED in set(Corroboration)
    assert len({c.value for c in Corroboration}) == len(list(Corroboration))
    assert not isinstance(Corroboration.NOT_STATED.value, bool)


# ---------------------------------------------------------------------------
# FR-024 properties 5 and 6 — `OD-35`'s third subject.


def test_a_declared_precision_must_say_where_it_was_declared() -> None:
    """`Staleness`'s stale-needs-an-age arm, one field over.

    A record saying *this comparison rests on the caller's own word* and unable
    to say whose word records the exposure and withholds what closes it. FR-024
    property 5 names both nouns, *"the declaration and its source text"*.
    """
    for absent in (None, "", "   "):
        with pytest.raises(ValueError, match="source text"):
            Precision(PrecisionBasis.DECLARED, declared_in=absent)


def test_a_basis_that_is_not_declared_carries_no_source_text() -> None:
    """The mirror. Two fields that can disagree will.

    `PrecisionProvenance` refuses the same shape one layer up and calls it
    fabricated provenance: a source cited for a displacement that did not
    happen. Here it is a declaration cited for a comparison it did not act on.
    """
    for basis in set(PrecisionBasis) - {PrecisionBasis.DECLARED}:
        with pytest.raises(ValueError, match="fabricated provenance"):
            Precision(basis, declared_in="caller request: 2 decimal places")


def test_the_precision_default_makes_no_claim() -> None:
    """The `staleness` asymmetry a third time, and the member it is not.

    `NOT_REACHED` is a **claim** — a declaration was in hand and the ladder
    never got to it — so defaulting to it would be `FRESH` again: a producer
    that never saw a declaration recorded as having resolved one. `NOT_STATED`
    is *nobody told this record*, which is what omitting the argument means.
    """
    record = Result(
        VerificationOutcome.VERIFIED,
        payload={"answer": 1},
        corroboration=Corroboration.CORROBORATED,
    )

    assert record.precision is PRECISION_NOT_STATED
    assert record.precision.basis is PrecisionBasis.NOT_STATED
    assert record.precision.basis is not PrecisionBasis.DECLARATION_NOT_REACHED
    assert record.precision.declared_in is None


def test_a_declared_precision_cannot_sit_beside_a_provisional_contract() -> None:
    """`OD-35` ④ — the pair that is unconstructible rather than discouraged.

    The two fields have different subjects and this pair asserts contradictory
    things about one contract: a declaration is admissible only against a
    contract the ladder validated, and a provisional one refuses at
    `CONTRACT_PROVISIONAL` before the precision question is reached.

    It is what makes a **half-revert** to `OD-34` ③ fail at construction —
    restoring the struck corroboration cell while leaving `OD-35`'s precision
    cell in place raises here rather than producing a quietly wrong record.
    """
    with pytest.raises(MissingVerification, match="Both cannot be true"):
        Result(
            VerificationOutcome.NOT_VERIFIABLE,
            payload={"answer": 1},
            corroboration=Corroboration.PROVISIONAL,
            reason="contract_provisional: nothing validated it",
            precision=Precision(
                PrecisionBasis.DECLARED, declared_in="caller request"
            ),
        )


def test_a_provisional_contract_record_with_no_declaration_is_constructible() -> None:
    """The positive control for the arm above.

    Without it that refusal is satisfied by a `Result` that rejects every
    `PROVISIONAL` record, which is not the property being asserted:
    `ProvisionalContract.to_result` builds exactly this and must keep working.
    """
    record = Result(
        VerificationOutcome.NOT_VERIFIABLE,
        payload={"answer": 1},
        corroboration=Corroboration.PROVISIONAL,
        reason="contract_provisional: nothing validated it",
    )

    assert record.state is ReportedState.NOT_VERIFIABLE
    assert record.precision.basis is PrecisionBasis.NOT_STATED
