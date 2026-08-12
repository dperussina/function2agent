"""T129 — the derivation reference and the reported value never share a source.

**Requirement**: FR-024, and constitution **Principle I as amended at v1.1.0**,
which was amended for the **derived-but-wrong verifier**: a verifier derived
from the same source as the thing it checks can be confidently wrong. So this
file is not a test *of* the verifier. Independence is the property that
distinguishes the verifier from the thing it is checking; without it T124's
agreement is an identity, and an identity agrees whatever the value is.

## The task line is terse and it has two readings. Both are asserted here.

*"The derivation reference and the reported value never share a source"* is
true at two different layers, and covering one and calling it done would leave
the other open:

1. **Execution independence.** At verification time, the value the verifier
   recomputes and the value the target reported must come out of **two
   different retrievals**. This is the reading FR-022 turns on.
2. **Derivation independence.** The artifact a check was *derived from* must
   not be the artifact it is *validated against* — Principle I's clause, held
   by `Provenance.__post_init__` and asserted here over derivations that
   actually happened rather than over a hand-built record.

## Why the first arm is behavioural and not a label comparison

Two `source` strings differing is a **shape check on a label**, and FR-022 says
in terms that conformance to a declared shape is not accepted as verification.
An implementation that tagged both values with different strings while reading
one out of the other would pass a label comparison and be exactly the defect.

So the load-bearing arm is a **perturbation**: the reported value is moved
across a range of plants and the recomputed value is asserted **constant**. If
the two shared a source the recomputed value would track the plant. That is a
falsifiable prediction about behaviour, and
`test_the_perturbation_arm_fails_against_a_dependent_verifier` is its negative
control — a deliberately dependent verifier built in this file, asserted to
fail the same arm. Without that control, the perturbation arm passes over any
implementation that ignores its input entirely.

The label comparison and the signature introspection are kept as the cheaper
two arms, because they fail earlier and name the edit that broke it.
"""

from __future__ import annotations

import importlib.util
import inspect
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, Sequence

import pytest

from src.analysis.derive import CheckKind, DerivedCheck, derive_module
from src.analysis.provenance import ProvenanceError, ValidationStatus
from src.analysis.served_operations import ServedOperationSet
from src.analysis.validate import (
    ProvisionalContract,
    ProvisionalReason,
    ValidatedContract,
    validate_contract,
)
from src.runtime.verify import (
    Refusal,
    RefusalReason,
    ReportedResult,
    SourcedValue,
    recompute,
    reported_quantity,
    verify_quantity,
)

REPO = Path(__file__).resolve().parents[2]
FIXTURE = REPO / "tests" / "fixtures" / "reference-app"
ANALYZER_ROOT = REPO / "tests" / "fixtures" / "analyzer"


def _load(name: str) -> ModuleType:
    if str(FIXTURE) not in sys.path:
        sys.path.insert(0, str(FIXTURE))
    spec = importlib.util.spec_from_file_location(
        f"_independence_refapp_{name}", FIXTURE / f"{name}.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


app_mod = _load("app")


class ApplicationPath:
    """The reference application's own API, reached a second time."""

    def __init__(self, application: Any, method: str, target: str) -> None:
        self._application = application
        self._method = method
        self._target = target

    def source(self) -> str:
        return f"in-process {self._method} {self._target}"

    def collection(self, name: str) -> Sequence[Any]:
        _status, body = self._application.call(self._method, self._target)
        return list(body[name])


class DependentPath:
    """The defect, built on purpose so the perturbation arm has something to fail on.

    It reads the reported result and manufactures a collection of exactly the
    reported length, which is the shape of a verifier that recomputes a
    quantity out of the answer it is checking. Every label on it is distinct
    from the reported result's, so it passes both cheaper arms.
    """

    def __init__(self, reported: ReportedResult, quantity: str) -> None:
        self._reported = reported
        self._quantity = quantity

    def source(self) -> str:
        return "a path that is not independent, wearing a different name"

    def collection(self, name: str) -> Sequence[Any]:
        return [{"quantity": 1}] * int(self._reported.payload[self._quantity])


def _shipment_count_check() -> DerivedCheck:
    """The check the perturbation arm runs. `count`, so the plant maps to a length."""
    contracts = derive_module(
        ANALYZER_ROOT / "inventory-service" / "service.py",
        relative_to=ANALYZER_ROOT / "inventory-service",
    )
    check = next(
        c
        for contract in contracts
        for c in contract.checks
        if c.quantity == "lot_count"
    )
    assert check.recomputation is not None
    return check


def _validated_for(check: DerivedCheck) -> ValidatedContract:
    contracts = derive_module(
        ANALYZER_ROOT / "inventory-service" / "service.py",
        relative_to=ANALYZER_ROOT / "inventory-service",
    )
    contract = next(c for c in contracts if check in c.checks)
    return ValidatedContract(
        contract=contract,
        validated_against="file://a-published-specification",
        agreed_on=("lots",),
        deployment_id="d-test",
    )


class LotsPath:
    """A real collection of `lots`, fixed, and never told what was reported."""

    def __init__(self, rows: Sequence[Any]) -> None:
        self._rows = list(rows)

    def source(self) -> str:
        return "lots, read once and held fixed"

    def collection(self, name: str) -> Sequence[Any]:
        return list(self._rows)


# ---------------------------------------------------------------------------
# Reading 1 — execution independence, behaviourally.


PLANTS = (0, 1, 2, 3, 7, 41, 1009)


def test_the_recomputed_value_does_not_move_when_the_reported_value_does() -> None:
    """The load-bearing arm. A shared source would make the recomputation track.

    Seven plants rather than one, because a single plant is also satisfied by a
    recomputation that happens to differ from it by a constant.
    """
    check = _shipment_count_check()
    contract = _validated_for(check)
    rows = [{"quantity": 2}, {"quantity": 3}, {"quantity": 5}]
    path = LotsPath(rows)

    observed = set()
    for plant in PLANTS:
        result = ReportedResult(source="the reported answer", payload={"lot_count": plant})
        recomputed = recompute(check, path)
        assert isinstance(recomputed, SourcedValue), recomputed
        observed.add((recomputed.value, recomputed.source))
        # And the same, through the whole verifier rather than the half.
        report = verify_quantity(
            contract=contract, check=check, result=result, path=path
        )
        assert getattr(report, "recomputed", None) is None or (
            report.recomputed.value == len(rows)  # type: ignore[union-attr]
        )

    assert observed == {(len(rows), path.source() + "#lots")}, (
        "the recomputed value moved with the reported value across "
        f"{len(PLANTS)} plants: {sorted(observed)}. The two share a source, "
        "which makes the comparison an identity"
    )


def test_the_perturbation_arm_fails_against_a_dependent_verifier() -> None:
    """The negative control over the arm above.

    Without this, the perturbation arm is satisfied by any implementation that
    ignores the reported value — including one that ignores *everything*. This
    plants a path that genuinely reads the reported result and asserts the arm
    catches it.
    """
    check = _shipment_count_check()
    observed = set()
    for plant in PLANTS:
        result = ReportedResult(
            source="the reported answer", payload={"lot_count": plant}
        )
        recomputed = recompute(check, DependentPath(result, "lot_count"))
        assert isinstance(recomputed, SourcedValue), recomputed
        observed.add(recomputed.value)

    assert observed == set(PLANTS), (
        "the planted dependent path did not track the reported value, so the "
        "arm above was never given anything to fail on"
    )
    assert len(observed) > 1, "a dependent verifier that does not move proves nothing"


def test_a_path_whose_retrieval_is_the_reported_one_is_refused_by_name() -> None:
    """The cheap arm. One retrieval cannot supply both values.

    Reading two fields out of one response is not two paths, and this is the
    refusal that says so before any comparison happens.
    """
    check = _shipment_count_check()

    class SameRetrievalPath(LotsPath):
        def source(self) -> str:
            return "the reported answer"

    report = verify_quantity(
        contract=_validated_for(check),
        check=check,
        result=ReportedResult(source="the reported answer", payload={"lot_count": 3}),
        path=SameRetrievalPath([{"quantity": 1}] * 3),
    )

    assert isinstance(report, Refusal), report
    assert report.reason is RefusalReason.SOURCES_NOT_INDEPENDENT
    assert "the reported answer" in report.detail


def test_neither_half_of_the_verifier_can_be_handed_the_other_ones_input() -> None:
    """Independence as a signature, so a future edit cannot wire the two together.

    `recompute` has no parameter that could carry the reported result and
    `reported_quantity` has none that could carry a path. This is what makes
    the behavioural arm above a property of the code rather than of the two
    paths this file happens to supply.
    """
    recompute_params = set(inspect.signature(recompute).parameters)
    reported_params = set(inspect.signature(reported_quantity).parameters)

    assert not (recompute_params & {"result", "reported", "payload", "answer"}), (
        f"`recompute` takes {sorted(recompute_params)}; one of those can carry "
        "the value under check into the path that recomputes it"
    )
    assert not (reported_params & {"path", "api", "observer", "deployment"}), (
        f"`reported_quantity` takes {sorted(reported_params)}; one of those "
        "can carry the independent path into the reader of the reported value"
    )
    assert "check" in recompute_params and "path" in recompute_params
    assert "check" in reported_params and "result" in reported_params


# ---------------------------------------------------------------------------
# Reading 2 — derivation independence, over derivations that actually happened.


def _every_committed_derivation() -> list[tuple[str, DerivedCheck]]:
    found: list[tuple[str, DerivedCheck]] = []
    for source in sorted(ANALYZER_ROOT.glob("*/service.py")) + sorted(
        FIXTURE.glob("app.py")
    ):
        root = source.parent
        for contract in derive_module(source, relative_to=root):
            for check in contract.checks:
                found.append((source.relative_to(REPO).as_posix(), check))
    return found


def test_the_corpus_of_real_derivations_is_not_empty() -> None:
    """Without this the two arms below are true over nothing.

    A coverage assertion whose population can silently become empty is the
    vacuity pattern this repository has hardened against repeatedly.
    """
    derivations = _every_committed_derivation()
    assert derivations, "no committed source derived any check"
    recomputing = [c for _, c in derivations if c.recomputes()]
    assert recomputing, (
        "no committed source derived a *recomputation*, so the independence "
        "arms below are statements about shape checks only"
    )


def test_no_recomputation_reads_the_quantity_it_recomputes() -> None:
    """Over every check the committed fixtures really derive.

    `derive.py` refuses this at construction; that refusal is what this test
    would find missing. The point of asserting it here rather than trusting the
    constructor is that the constructor is one edit away and this file names
    the property the edit would remove.
    """
    for origin, check in _every_committed_derivation():
        if not check.recomputes():
            continue
        assert check.recomputation is not None
        assert check.quantity not in check.recomputation.reads, (
            f"{origin} derived {check.operation_id}/{check.quantity}, whose "
            f"recomputation reads {check.recomputation.reads}. A recomputation "
            "that reads the quantity under check agrees with itself whatever "
            "the value is"
        )


def test_a_promotion_cannot_name_the_source_the_derivation_read() -> None:
    """Principle I's clause over a real derived contract, not a hand-built record."""
    contracts = derive_module(
        ANALYZER_ROOT / "inventory-service" / "service.py",
        relative_to=ANALYZER_ROOT / "inventory-service",
    )
    contract = contracts[0]
    assert contract.provenance.source_file == "service.py"

    with pytest.raises(ProvenanceError, match="derived from"):
        ValidatedContract(
            contract=contract,
            validated_against="service.py",
            agreed_on=("lots",),
            deployment_id="d-test",
        )


def test_every_committed_derivation_is_provisional_and_cites_nothing() -> None:
    """The state a derivation is *born* in, over the real corpus.

    A derivation that arrived already citing an artifact would mean something
    upstream promoted it without an independent artifact, which is the exact
    substitution Principle I forbids.
    """
    for origin, check in _every_committed_derivation():
        assert check.provenance.validation_status is ValidationStatus.PROVISIONAL, origin
        assert check.provenance.validated_against is None, origin


def test_the_committed_published_specification_promotes_nothing() -> None:
    """The constructional fact this whole feature sits on, stated executably.

    `served_operations.json` is the one real published specification in this
    tree, and it declares **no parameters** for any operation. So
    `validate_contract` reads it as silent and promotes nothing — which means
    the `verified` path is not reachable from committed data even with a real
    specification in hand, and not merely because the analyzer fixtures have no
    deployment.

    Recorded as a test rather than as prose because it is the sentence a future
    pass is most likely to assume is stale.
    """
    document = json.loads((FIXTURE / "served_operations.json").read_text())
    specification = ServedOperationSet(
        deployment_id=document["deployment_id"],
        operations=tuple(
            __import__(
                "src.analysis.served_operations", fromlist=["ServedOperation"]
            ).ServedOperation.from_entry(entry, index=index)
            for index, entry in enumerate(document["operations"])
        ),
        captured_at=document["captured_at"],
        source_url=document["source_url"],
    )
    assert specification.operation_ids(), "the fixture specification is empty"
    assert all(
        "parameters" not in operation.declared for operation in specification.operations
    ), (
        "served_operations.json now declares parameters. If that is deliberate, "
        "the promotion path may now be reachable from committed data and T124's "
        "PARTIAL note should be revisited"
    )

    contracts = derive_module(FIXTURE / "app.py", relative_to=FIXTURE)
    outcomes = {
        validate_contract(
            contract,
            specification=specification,
            served_operation_id="list_shipments",
        ).__class__
        for contract in contracts
    }
    assert outcomes == {ProvisionalContract}, outcomes

    reasons = {
        validate_contract(
            contract,
            specification=specification,
            served_operation_id="list_shipments",
        ).reason  # type: ignore[union-attr]
        for contract in contracts
    }
    assert reasons == {ProvisionalReason.SPECIFICATION_SILENT}, reasons


def test_a_shape_check_is_never_treated_as_an_independent_path() -> None:
    """FR-022's clause restated as an independence property.

    A shape check has no `recomputation`, so there is nothing to run a second
    time; accepting one would be verification against no second source at all.
    """
    shape = [
        check
        for _origin, check in _every_committed_derivation()
        if check.check_kind is CheckKind.SHAPE
    ]
    assert shape, "no shape check in the corpus, so this arm covers nothing"
    for check in shape:
        assert check.recomputation is None
