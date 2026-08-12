"""T132 — the shape-and-type-only control verifier, and the zero it is allowed to report.

**Criterion**: SC-006 — *"A verifier restricted to shape and type conformance
detects **none** of the value faults in SC-005's corpus, demonstrating that the
shipped verifier's detection comes from independent recomputation rather than
from conformance checking."*

The corpus is T131's, at `tests/fixtures/value-faults/`. Its README states which
file each task owns and why the matched corpus is a pairing.

## WHY A ZERO IS THE HARDEST RESULT TO REPORT HONESTLY

SC-006's positive result is **a failure to detect**, which is the
experiment-design skill's Rule 8 in its exact shape: the reading is one bit, and
every way the instrument can break produces that same bit. A control verifier
that cannot run, that is handed an empty corpus, that errors on every input, or
that is pointed at the wrong file all report *"detected none"* and all clear a
naive assertion.

So the zero here is made **discriminating** by four arms that are load-bearing
rather than decorative, and none of them is a comment:

| Arm | Corpus | Detector | Expected | What its absence would let through |
|---|---|---|---|---|
| negative | `corpus.json`, faulted values | `shape_and_type_conformance` | **0** | — this is the claim |
| **positive control** | `shape-faults.json` | **the same function** | **all of them** | a control that detects nothing because it detects nothing |
| reference | `corpus.json`, both halves | `reference_value_check` | separates them | a corpus of faults that are not faults |
| shipped | `corpus.json`, numeric subset | `src.runtime.verify.verify_quantity` | `Disagreement` / `Verified` | a corpus nothing in the product can see |

The positive control turns **exactly one variable**. `corpus.json` carries a
right shape with a wrong value; `shape-faults.json` carries a right value
wearing a wrong shape. Same detector, same harness, same call. If the control
were broken the second arm would report zero too, and the pair would be
inconsistent rather than quietly clean.

## THE CLASS THE NULL BOUNDS, WHICH IS A RECORDED LESSON AND NOT A PRECAUTION

This control has an ancestor and the ancestor has a recorded defect. E8's
predicted-null control (`c1`) asserted that a schema-derived arm detected zero
**numeric** value errors. It passed, correctly, and the arm's real defect was in
the **set-typed** class — a cardinality clause that certified the wrong answer
as correct, at precision 0 of 3, which the control was structurally incapable of
seeing.
[Finding 015](../../specs/001-discovery-validation/findings/015-verifier-vs-judge-not-run.md)
opens that as a new contradiction and states the resolution: *"every negative
control must state the class it bounds."*

`BOUNDED_CLASSES` is that statement, and
`test_the_null_states_the_classes_it_bounds` refuses a corpus carrying a class
the control does not claim to bound. Adding a fault class to `corpus.json`
without widening the declaration turns the arm red instead of silently
shrinking what the zero covers.

## THE FIGURE THIS TASK RESTS ON, AND THE TWO MODULES THAT STILL QUOTE IT WRONG

The design constraint T132 converts from reasoning into measurement is that *a
shipping verifier cannot be schema-only and must recompute postconditions via
the application's own API*. Its evidence is the false-success split measured in
feature 001, which is **9 numeric-typed and 2 set-typed** —
[`E8-VIABILITY.md` §6 and §B1.1](../../specs/001-discovery-validation/E8-VIABILITY.md)
records the correction from an earlier 8-and-3, recomputed independently by two
agents from the frozen corpus.

⚠️ **`src/analysis/derive.py` and `src/analysis/provenance.py` both still quote
the superseded 8**, and `provenance.py` additionally attributes the census to
*finding 001*, which is the structure-recovery study and contains no false
success at all. Neither is corrected from here — they are other tasks' files and
this one does not need them to be right — but neither is inherited either: this
module cites the artifact rather than the docstring beside it. Nothing in this
repository would have caught the drift, because a bare integer is not a shape
`tools/check_corpus.py` extracts, and `tests/` is outside its walk entirely.

## WHAT THIS BATTERY DELIBERATELY DOES NOT REPORT

**No detection rate and no false-alarm rate.** SC-005 pre-registers two — at
least 95% detection, no worse than 1% false alarms — and neither is reported
here, on the denominator rather than on the thresholds. Both are computed over
*"the faults injected into quantities the precision ladder does not refuse"*,
and the ladder is unfinished: its admissible **sources** are closed (FR-024
property 4, `ADMISSIBLE_PRECISION_SOURCES`, shipped under T125) while the
**caller-declared rung** that decides which quantities refuse is open under
T212. A rate computed now would be a rate over a population T212 can still
move, and this corpus's whole subject is figures nobody recomputed.

SC-006 asks for a **count of zero** with the class stated, which is what is
reported, and a count needs no threshold to read.

Run:
    python -m pytest tests/batteries/test_conformance_control.py -v
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import pytest

from src.analysis.derive import (
    AGGREGATES,
    CheckKind,
    DerivedCheck,
    DerivedContract,
    Recomputation,
)
from src.analysis.provenance import (
    Provenance,
    ValidationStatus,
    hash_source_construct,
)
from src.analysis.validate import ValidatedContract
from src.runtime.verify import (
    Disagreement,
    PathUnavailable,
    ReportedResult,
    Verified,
    verify_quantity,
)
from tests.batteries.evidence import record_evidence

REPO = Path(__file__).resolve().parents[2]
CORPUS_DIR = REPO / "tests" / "fixtures" / "value-faults"

#: SC-005's own boundary, quoted rather than chosen: *"faults smaller than one
#: percent of the correct value"*. It is a **stratum label**, not a tolerance —
#: nothing here compares a value against it, and no detector below reads it.
#: FR-024 property 2 forbids a numeric rung in the precision ladder and this is
#: not one: it partitions the corpus for reporting, which is what SC-005
#: requires be done separately.
SUB_ONE_PERCENT = 0.01

#: The fault classes this control's zero is a statement about. Declared, because
#: finding 015 records a predicted-null control that was correct about the class
#: it tested and silent about the class its subject was broken in.
BOUNDED_CLASSES: frozenset[str] = frozenset(
    {"numeric_value_error", "set_cardinality_error", "set_membership_error"}
)


class _Absent:
    """The quantity was not in the payload. Not `None` — that is a value.

    `shape-faults.json` carries both cases separately, because a detector
    reading only key presence passes the null and a detector reading only
    nullity passes the absence.
    """

    def __repr__(self) -> str:  # pragma: no cover - diagnostic only
        return "<absent>"


ABSENT = _Absent()


# ---------------------------------------------------------------------------
# THE CONTROL VERIFIER.
#
# **It takes no collection, and that is the mechanism rather than a convention.**
# `src/runtime/verify.py` holds FR-022's independence as a signature — `recompute`
# is not given the reported result and `reported_quantity` is not given the path
# — and the same construction is what makes this control's zero structural. It
# cannot detect a value fault because nothing hands it anything to compare a
# value against. `test_the_control_cannot_reach_a_collection` asserts that over
# the signature, so a later edit cannot quietly wire one in and leave the zero
# reading as a measurement of shape-blindness when it has become something else.


def shape_and_type_conformance(
    declared_shape: Mapping[str, Any], reported: Any
) -> tuple[str, ...]:
    """Conformance of one reported quantity to its declared shape. No values.

    Returns the violations found, which is empty for a conformant quantity.
    """
    kind = declared_shape["kind"]

    if isinstance(reported, _Absent):
        return (f"the payload carries no quantity to check against `{kind}`",)

    if kind == "integer":
        # `isinstance(True, int)` is True in Python, so the bool exclusion is
        # not pedantry: without it a boolean conforms to an integer declaration
        # and `True == 1` then agrees with a count of one.
        # `RefusalReason.QUANTITY_NOT_A_MAGNITUDE` refuses the same thing in the
        # shipped verifier, and a control weaker than its subject would make the
        # comparison between them unreadable.
        if isinstance(reported, bool) or not isinstance(reported, int):
            return (
                f"declared `integer`, got {type(reported).__name__} "
                f"{reported!r}",
            )
        return ()

    if kind == "list":
        if not isinstance(reported, list):
            return (f"declared `list`, got {type(reported).__name__}",)
        element_kind = declared_shape["element_kind"]
        expected = {"string": str, "integer": int}[element_kind]
        wrong = [
            f"element {index} is {type(value).__name__} {value!r}"
            for index, value in enumerate(reported)
            if isinstance(value, bool) or not isinstance(value, expected)
        ]
        if wrong:
            return (
                f"declared a list of `{element_kind}`: " + "; ".join(wrong),
            )
        # Deliberately nothing about length and nothing about membership. A
        # cardinality clause is where E8's schema arm certified the wrong answer
        # as correct, and a control that grew one would stop being a control for
        # the set-typed class.
        return ()

    raise AssertionError(f"no conformance rule for declared kind {kind!r}")


# ---------------------------------------------------------------------------
# THE VALUE-AWARE REFERENCE.
#
# Not the shipped verifier, and not a rival to it. Its only job is to establish
# that the corpus's faults are real: a corpus of faults nothing can detect is
# indistinguishable from an empty one, and without this arm the control's zero
# and the corpus's population would be each other's only evidence.
#
# It performs the `project` operator the shipped `Recomputation` cannot express
# — see `test_the_shipped_recomputation_cannot_express_the_set_typed_class`.


def reference_value_check(
    recomputation: Mapping[str, Any],
    collection: Sequence[Mapping[str, Any]],
    reported: Any,
) -> tuple[str, ...]:
    """Recompute the quantity from the collection and compare. No shapes."""
    recomputed = _recompute(recomputation, collection)
    if reported == recomputed and type(reported) is type(recomputed):
        return ()
    return (
        f"reported {reported!r}; recomputed {recomputed!r} by "
        f"{recomputation['operator']} over {recomputation['over']!r}",
    )


def _recompute(
    recomputation: Mapping[str, Any], collection: Sequence[Mapping[str, Any]]
) -> Any:
    operator = recomputation["operator"]
    field = recomputation["element_field"]
    if operator == "count":
        return len(collection)
    values = [row[field] for row in collection]
    if operator == "sum":
        return sum(values)
    if operator == "min":
        return min(values)
    if operator == "max":
        return max(values)
    if operator == "project":
        return values
    raise AssertionError(f"no reference implementation for {operator!r}")


# ---------------------------------------------------------------------------
# THE CORPUS, LOADED AND RE-DERIVED.


class Case:
    """One corpus entry, with everything derived rather than read."""

    def __init__(self, raw: Mapping[str, Any], collections: Mapping[str, Any]) -> None:
        self.raw = raw
        self.case_id = raw["case_id"]
        self.quantity = raw["quantity"]
        self.fault_class = raw["fault_class"]
        self.declared_shape = raw["declared_shape"]
        self.recomputation = raw["recomputation"]
        self.correct_value = raw["correct_value"]
        self.faulted_value = raw["faulted_value"]
        self.collection = collections[self.recomputation["over"]]

    @property
    def derived_correct_value(self) -> Any:
        return _recompute(self.recomputation, self.collection)

    @property
    def relative_magnitude(self) -> float | None:
        """`|faulted − correct| / |correct|`, or `None` where undefined.

        Computed, never declared. A declared stratum is a claim about a case
        that survives the case being edited underneath it.
        """
        if not isinstance(self.correct_value, int) or isinstance(
            self.correct_value, bool
        ):
            return None
        return abs(self.faulted_value - self.correct_value) / abs(self.correct_value)

    @property
    def stratum(self) -> str:
        magnitude = self.relative_magnitude
        if magnitude is None:
            return "not_applicable"
        return (
            "sub_one_percent"
            if magnitude < SUB_ONE_PERCENT
            else "at_or_above_one_percent"
        )


def _load_corpus() -> list[Case]:
    document = json.loads((CORPUS_DIR / "corpus.json").read_text())
    return [Case(raw, document["collections"]) for raw in document["cases"]]


def _load_shape_faults() -> list[dict[str, Any]]:
    return list(json.loads((CORPUS_DIR / "shape-faults.json").read_text())["cases"])


CORPUS = _load_corpus()
SHAPE_FAULTS = _load_shape_faults()


def _shape_fault_value(case: Mapping[str, Any]) -> Any:
    return ABSENT if case.get("quantity_absent") else case["faulted_value"]


# ---------------------------------------------------------------------------
# THE CORPUS IS NOT EMPTY, AND ITS ORACLE IS NOT A COMMITTED NUMBER.
#
# Every arm below the negative one is worthless if these fail, so they come
# first. An assertion of zero detections over an empty corpus is true.


def test_the_corpus_is_populated_in_both_halves() -> None:
    """A zero over an empty corpus is free, and reads exactly like a result."""
    assert CORPUS, "tests/fixtures/value-faults/corpus.json yielded no cases"
    assert SHAPE_FAULTS, "shape-faults.json yielded no cases, so the positive control is vacuous"
    for case in CORPUS:
        assert case.collection, f"{case.case_id}: the collection is empty"
        assert (
            case.faulted_value != case.correct_value
        ), f"{case.case_id}: the fault equals the correct value, so nothing was injected"


def test_the_matched_correct_corpus_is_the_same_size_as_the_fault_corpus() -> None:
    """SC-005's false-alarm denominator, held by construction.

    Each case carries both halves, so the two populations cannot drift apart.
    This asserts the property the pairing is supposed to buy rather than
    assuming the pairing delivered it.
    """
    faulted = [case.faulted_value for case in CORPUS]
    correct = [case.correct_value for case in CORPUS]
    assert len(faulted) == len(correct) == len(CORPUS)
    assert len(CORPUS) == len({case.case_id for case in CORPUS}), "duplicate case_id"


def test_every_committed_correct_value_is_recomputed_from_its_collection() -> None:
    """The oracle is derived, and the committed figure is checked against it.

    A committed `correct_value` nobody recomputes is a number, and a corpus
    built to catch numbers nobody recomputed cannot rest on one.
    """
    for case in CORPUS:
        assert case.correct_value == case.derived_correct_value, (
            f"{case.case_id}: the committed correct_value "
            f"{case.correct_value!r} is not what "
            f"{case.recomputation['operator']} over "
            f"{case.recomputation['over']!r} produces "
            f"({case.derived_correct_value!r})"
        )


def test_the_sub_one_percent_stratum_is_populated_and_computed() -> None:
    """T131 names this stratum explicitly, so an unpopulated one fails the task.

    The stratum is read off `relative_magnitude`, which is computed from the
    two values. Nothing in the corpus declares it.
    """
    strata = [case.stratum for case in CORPUS]
    assert "sub_one_percent" in strata, (
        "the corpus carries no fault smaller than one percent of the correct "
        "value, which is the stratum T131 names by hand"
    )
    assert "at_or_above_one_percent" in strata, (
        "the corpus is entirely sub-one-percent, so SC-005's requirement that "
        "the stratum be reported *separately* has nothing to separate it from"
    )
    for case in CORPUS:
        if case.stratum == "sub_one_percent":
            assert case.relative_magnitude is not None
            assert case.relative_magnitude < SUB_ONE_PERCENT


# ---------------------------------------------------------------------------
# SC-006's NEGATIVE ARM, AND THE POSITIVE CONTROL THAT MAKES IT READABLE.


def test_the_control_detects_none_of_the_value_faults() -> None:
    """SC-006 itself. Read only alongside the positive control below."""
    detected = {
        case.case_id: shape_and_type_conformance(
            case.declared_shape, case.faulted_value
        )
        for case in CORPUS
        if shape_and_type_conformance(case.declared_shape, case.faulted_value)
    }
    assert detected == {}, (
        "a shape-and-type-only verifier detected a value fault, which SC-006 "
        f"says it cannot: {detected}"
    )


def test_the_control_cannot_tell_the_faulted_value_from_the_correct_one() -> None:
    """Stronger than two zeroes, and it is the actual content of SC-006.

    Both halves reporting no violation is consistent with a detector that
    happens to be silent on each. Asserting the two answers are **identical**
    says the control has no state in which it distinguishes them.
    """
    for case in CORPUS:
        on_correct = shape_and_type_conformance(
            case.declared_shape, case.correct_value
        )
        on_faulted = shape_and_type_conformance(
            case.declared_shape, case.faulted_value
        )
        assert on_correct == on_faulted == (), (
            f"{case.case_id}: the control answered {on_correct!r} on the "
            f"correct value and {on_faulted!r} on the faulted one, so it is "
            "distinguishing them"
        )


def test_the_positive_control_is_caught_naming_the_shape() -> None:
    """THE ARM THAT MAKES THE ZERO ABOVE MEAN ANYTHING.

    The same function, the same call, the same harness — over values that are
    **correct** and wear the wrong shape. Every entry must be caught. If this
    reports zero, so does the arm above, and the pair is then a statement about
    the detector rather than about the corpus.
    """
    caught: dict[str, tuple[str, ...]] = {}
    missed: list[str] = []
    for case in SHAPE_FAULTS:
        violations = shape_and_type_conformance(
            case["declared_shape"], _shape_fault_value(case)
        )
        if violations:
            caught[case["case_id"]] = violations
        else:
            missed.append(case["case_id"])

    record_evidence(
        "t132-positive-control-sc006",
        {
            "criterion": "SC-006",
            "detector": "shape_and_type_conformance",
            "shape_faults_presented": len(SHAPE_FAULTS),
            "shape_faults_caught": len(caught),
            "caught": caught,
            "missed": missed,
        },
    )

    assert not missed, (
        "the shape-and-type control missed a wrong shape carrying a correct "
        f"value: {missed}. Its zero on the value-fault corpus is then "
        "unfalsifiable — a detector that detects nothing detects no value "
        "faults for free."
    )
    assert len(caught) == len(SHAPE_FAULTS)


def _unwrap(recovery: str, value: Any) -> Any:
    """Undo the wrapping a control entry declares. Total over the declared set.

    The entry declares *how* it is wrapped and never *what* it should equal, so
    this recovers a value the comparison below can be wrong about.
    """
    if recovery == "cast_int":
        return int(value)
    if recovery == "unwrap_value_key":
        return value["value"]
    if recovery == "unwrap_single_element":
        (only,) = value
        return only
    if recovery.startswith("unwrap_element_key:"):
        key = recovery.split(":", 1)[1]
        return [element[key] for element in value]
    raise AssertionError(f"no unwrapping for recovery {recovery!r}")


def test_the_positive_controls_entries_really_do_carry_the_correct_value() -> None:
    """One variable, asserted rather than intended.

    The contrast between the two arms is *shape wrong* against *value wrong*.
    An entry in the control corpus whose value was also wrong could be caught
    for the other reason, and the pair would then differ in two things.

    `none_carried` is the honest exception rather than a hole: a null and an
    absent key carry no value, so there is nothing to recover — and equally
    nothing a value comparison could have flagged, which is what the arm needs.
    """
    for case in SHAPE_FAULTS:
        recovery = case["recovery"]
        if recovery == "none_carried":
            value = _shape_fault_value(case)
            assert value is None or isinstance(value, _Absent), (
                f"{case['case_id']}: declares `none_carried` and carries "
                f"{value!r}, which is a value"
            )
            continue
        recovered = _unwrap(recovery, _shape_fault_value(case))
        assert recovered == case["correct_value"], (
            f"{case['case_id']}: unwrapping by {recovery!r} recovers "
            f"{recovered!r}, not the correct value {case['correct_value']!r}. "
            "This entry is a value fault as well as a shape fault, so it turns "
            "two variables instead of one."
        )


# ---------------------------------------------------------------------------
# THE CORPUS'S FAULTS ARE REAL — a value-aware reading separates them.


def test_a_value_aware_reference_separates_the_two_halves() -> None:
    """Without this, the control's zero and the corpus are circular.

    `shape_and_type_conformance` reporting nothing is evidence about the
    detector only if something else can see the faults. This is that something,
    and it is deliberately not the shipped verifier: the arm below is.
    """
    undetected: list[str] = []
    false_alarms: dict[str, tuple[str, ...]] = {}
    for case in CORPUS:
        if not reference_value_check(
            case.recomputation, case.collection, case.faulted_value
        ):
            undetected.append(case.case_id)
        alarm = reference_value_check(
            case.recomputation, case.collection, case.correct_value
        )
        if alarm:
            false_alarms[case.case_id] = alarm

    assert not undetected, (
        f"a value-aware check could not see these injected faults: "
        f"{undetected}. A fault nothing detects is indistinguishable from no "
        "fault, and the control's zero over it would be free."
    )
    assert not false_alarms, (
        f"the value-aware reference flagged correct results: {false_alarms}. "
        "The matched corpus is then not a corpus of correct results."
    )


# ---------------------------------------------------------------------------
# THE SHIPPED PATH — SC-006's second clause.
#
# SC-006 does not only ask for a zero; it asks the zero to demonstrate *"that
# the shipped verifier's detection comes from independent recomputation"*. That
# needs the shipped verifier run over the same corpus, which is this arm.


class _CorpusPath:
    """An independent path serving the corpus's committed collection.

    Labelled, on `tests/unit/test_verify.py::StaticCollectionPath`'s precedent:
    this is **not** a deployment. It exists so a recomputation can be executed
    at all. What the arm claims is about the comparison, not about a served
    target.
    """

    def __init__(self, name: str, rows: Sequence[Any]) -> None:
        self._name = name
        self._rows = list(rows)

    def source(self) -> str:
        return f"value-fault corpus collection {self._name!r}"

    def collection(self, name: str) -> Sequence[Any]:
        if name != self._name:
            raise PathUnavailable(f"this path serves {self._name!r}, not {name!r}")
        return list(self._rows)


def _validated_contract_for(case: Case) -> tuple[ValidatedContract, DerivedCheck]:
    """A promoted contract and its check, **constructed rather than promoted**.

    Exactly `tests/unit/test_verify.py::_validated`'s position and for the same
    inherited reason: the one published specification in this tree declares no
    parameters, so `validate_contract` reads it as silent and promotes nothing.
    Promotion is not what this arm claims anything about — the comparison is.
    """
    provenance = Provenance(
        derivation_rule="aggregate_binding",
        source_symbol=case.raw["operation_id"].split(":", 1)[1],
        source_file="inventory/service.py",
        content_hash=hash_source_construct(case.case_id),
        validation_status=ValidationStatus.PROVISIONAL,
    )
    check = DerivedCheck(
        operation_id=case.raw["operation_id"],
        quantity=case.quantity,
        check_kind=CheckKind.RECOMPUTATION,
        expression=(
            f"{case.quantity} == {case.recomputation['operator']}"
            f"({case.recomputation['over']})"
        ),
        recomputation=Recomputation(
            operator=case.recomputation["operator"],
            over=case.recomputation["over"],
            element_field=case.recomputation["element_field"],
            reads=tuple(case.recomputation["reads"]),
        ),
        precision_source=f"aggregate_over:{case.recomputation['operator']}",
        provenance=provenance,
    )
    contract = ValidatedContract(
        contract=DerivedContract(
            operation_id=case.raw["operation_id"],
            reads=(case.recomputation["over"],),
            writes=(),
            preconditions=(),
            postconditions=(check.expression,),
            failure_taxonomy=(),
            provenance=provenance,
            checks=(check,),
        ),
        validated_against="file://tests/fixtures/value-faults/corpus.json",
        agreed_on=(case.recomputation["over"],),
        deployment_id="d-value-fault-corpus",
    )
    return contract, check


def _shipped_verifiable() -> list[Case]:
    """The cases the shipped `Recomputation` can express a check for."""
    return [case for case in CORPUS if case.recomputation["operator"] in AGGREGATES]


def test_the_shipped_verifier_disagrees_on_every_fault_it_can_express() -> None:
    """SC-006's second clause: the detection comes from recomputation.

    The same corpus the control was blind to, through
    `src/runtime/verify.py::verify_quantity`. A fault must produce a
    `Disagreement` carrying both operands and the correct value must produce a
    `Verified`, so the arm reads the discrimination and not merely a non-agreement.
    """
    expressible = _shipped_verifiable()
    assert expressible, "no corpus case reaches the shipped verifier at all"

    faults_seen: dict[str, str] = {}
    for case in expressible:
        contract, check = _validated_contract_for(case)
        path = _CorpusPath(case.recomputation["over"], case.collection)

        on_fault = verify_quantity(
            contract=contract,
            check=check,
            result=ReportedResult(
                source=f"agent answer {case.case_id}",
                payload={case.quantity: case.faulted_value},
            ),
            path=path,
        )
        assert isinstance(on_fault, Disagreement), (
            f"{case.case_id}: the shipped verifier returned "
            f"{type(on_fault).__name__} on an injected fault, not a Disagreement"
        )
        faults_seen[case.case_id] = on_fault.detail

        on_correct = verify_quantity(
            contract=contract,
            check=check,
            result=ReportedResult(
                source=f"agent answer {case.case_id}",
                payload={case.quantity: case.correct_value},
            ),
            path=path,
        )
        assert isinstance(on_correct, Verified), (
            f"{case.case_id}: the shipped verifier returned "
            f"{type(on_correct).__name__} on the matched correct result, so "
            "its disagreement above is not evidence of discrimination"
        )

    record_evidence(
        "t132-shipped-verifier-over-the-corpus",
        {
            "criterion": "SC-006, second clause",
            "cases_expressible_by_the_shipped_recomputation": len(expressible),
            "cases_in_corpus": len(CORPUS),
            "cases_not_expressible": [
                case.case_id for case in CORPUS if case not in expressible
            ],
            "disagreements": faults_seen,
        },
    )


def test_the_shipped_recomputation_cannot_express_the_set_typed_class() -> None:
    """A gap, asserted so that closing it forces the note to move.

    `Recomputation` admits `count`, `sum`, `min` and `max`. None of them
    projects a collection onto a member list, so the shipped verifier can
    derive no check for the set-typed class — the class E8's arm was actually
    broken in. The battery's own reference performs the projection instead.

    This is not a defect in this task and it is not repaired here. It is
    asserted because the README beside the corpus states it, and a stated gap
    that nothing checks goes stale the moment somebody closes it.
    """
    assert "project" not in AGGREGATES, (
        "`project` is now a recomputable aggregate, so the shipped verifier "
        "can express the set-typed class. Update this arm and the paragraph in "
        "tests/fixtures/value-faults/README.md that says it cannot."
    )
    set_typed = [case for case in CORPUS if case.recomputation["operator"] == "project"]
    assert set_typed, "the corpus carries no set-typed case, so this gap is untested"
    assert not any(case in _shipped_verifiable() for case in set_typed)


# ---------------------------------------------------------------------------
# WHAT THE ZERO COVERS, AND WHAT THE CONTROL STRUCTURALLY CANNOT DO.


def test_the_null_states_the_classes_it_bounds() -> None:
    """Finding 015's recorded resolution, as a gate rather than a habit.

    A control scoped to one failure class certifies nothing about the others
    and reads as a clean pass while the subject is broken elsewhere. So the
    classes present in the corpus must be covered by the declaration, and a new
    class arriving in `corpus.json` turns this red instead of silently
    shrinking what the zero means.
    """
    present = {case.fault_class for case in CORPUS}
    unbounded = present - BOUNDED_CLASSES
    assert not unbounded, (
        f"the corpus carries fault classes {sorted(unbounded)} that "
        "BOUNDED_CLASSES does not claim. The zero would then be silent about "
        "them, which is exactly the defect finding 015 opened against E8's c1 "
        "control."
    )
    assert len(present) > 1, (
        "the corpus carries one fault class, so the bounded-class declaration "
        "is not doing any work and the zero covers less than it appears to"
    )
    unexercised = BOUNDED_CLASSES - present
    assert not unexercised, (
        f"BOUNDED_CLASSES claims {sorted(unexercised)}, which no case in the "
        "corpus exercises. A control may not claim to bound a class it was "
        "never shown."
    )


def test_the_control_cannot_reach_a_collection() -> None:
    """The zero is structural, not behavioural, and this is where that is held.

    `src/runtime/verify.py` keeps FR-022's independence in the signatures —
    `recompute` takes no result and `reported_quantity` takes no path. The same
    construction here: the control is handed a declared shape and one value, so
    there is nothing it could recompute against even if its body tried.
    """
    parameters = list(inspect.signature(shape_and_type_conformance).parameters)
    assert parameters == ["declared_shape", "reported"], (
        f"the control's parameters are {parameters}. A collection, a corpus or "
        "a recomputation among them would make its zero a fact about its body "
        "rather than about its inputs."
    )
    reference = list(inspect.signature(reference_value_check).parameters)
    assert "collection" in reference, (
        "the value-aware reference no longer takes a collection, so the arm "
        "that proves the faults are real has stopped recomputing anything"
    )


def test_the_control_reports_zero_over_the_whole_corpus_with_its_strata() -> None:
    """The reported artifact, and the shape SC-005 requires a run to have.

    SC-005 refuses a run that reports rates without the refusal share broken
    out for the sub-one-percent stratum. **No rate is reported here** — see this
    module's docstring — so what is written is the population by stratum and by
    class beside the zero, which is what makes the zero readable.
    """
    by_stratum: dict[str, list[str]] = {}
    by_class: dict[str, list[str]] = {}
    for case in CORPUS:
        by_stratum.setdefault(case.stratum, []).append(case.case_id)
        by_class.setdefault(case.fault_class, []).append(case.case_id)

    detections = sum(
        1
        for case in CORPUS
        if shape_and_type_conformance(case.declared_shape, case.faulted_value)
    )

    record_evidence(
        "t132-conformance-control-sc006",
        {
            "criterion": "SC-006",
            "detector": "shape_and_type_conformance",
            "value_faults_presented": len(CORPUS),
            "value_faults_detected": detections,
            "bounded_classes": sorted(BOUNDED_CLASSES),
            "population_by_fault_class": by_class,
            "population_by_stratum": by_stratum,
            "relative_magnitudes": {
                case.case_id: case.relative_magnitude for case in CORPUS
            },
            "detection_rate": None,
            "detection_rate_withheld_because": (
                "SC-005's percentages are scored against the precision-ladder "
                "extraction FR-024 property 4 leaves open (T125, T212). A rate "
                "against an unfinished denominator is a figure nobody can "
                "recompute. SC-006 asks for a count of zero, which is reported."
            ),
        },
    )

    assert detections == 0


@pytest.mark.parametrize("kind", ["integer", "list"])
def test_the_control_has_a_rule_for_every_declared_kind_in_both_corpora(
    kind: str,
) -> None:
    """No corpus entry may reach the control's `AssertionError` fallthrough.

    A detector that raises on an input is not a detector that found nothing,
    but a battery collecting exceptions could report either as a zero.
    """
    declared = {case.declared_shape["kind"] for case in CORPUS} | {
        case["declared_shape"]["kind"] for case in SHAPE_FAULTS
    }
    assert declared <= {"integer", "list"}, (
        f"a corpus declares kind(s) {sorted(declared - {'integer', 'list'})} "
        "that the control has no rule for"
    )
    if kind in declared:
        sample = next(
            case for case in CORPUS if case.declared_shape["kind"] == kind
        )
        assert shape_and_type_conformance(sample.declared_shape, ABSENT), (
            f"the control passed an absent quantity declared `{kind}`"
        )
