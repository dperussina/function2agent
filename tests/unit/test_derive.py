"""T120 — static derivation of contracts and checks, with no model call anywhere in it.

**Requirement**: T-13 and FR-023 — *"Every verification check MUST derive from
an artifact the target codebase already contains … A model's assessment MUST NOT
be the success signal for any result."*

## The design constraint this file exists to hold, and where it comes from

A schema-only verifier is blind to the faults that matter. Feature 001 measured
**11 false successes, 8 of them numeric-typed and schema-blind** — the value was
wrong and the shape was right — and the recorded v1 constraint is that a
shipping verifier cannot be schema-only and must recompute postconditions by an
independent path.

T120 is the *derivation* half of that. It is not enough for this module to emit
checks; it has to emit checks **capable of expressing a recomputation**. T124
builds the verifier that runs them and T132 is a negative control asserting a
shape-and-type-only verifier detects **none** of an injected fault corpus — so
if what comes out of here can only express shapes, T132 is unsatisfiable and the
whole story collapses into the thing it was supposed to beat.

`test_a_recomputation_check_reads_something_other_than_the_quantity` and
`test_the_shape_only_subset_cannot_express_the_numeric_fault` are the two arms
that keep that from happening quietly.

## "No model call anywhere in it" is checked, not asserted

`test_no_model_or_network_reaches_the_derivation` walks the **transitive**
first-party import closure of `src.analysis.derive` — a model call one import
away is still a model call in it — and `test_the_model_scan_fires_on_a_planted_
import` plants the violation so the scan is known to fire rather than assumed to.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from src.analysis import derive
from src.analysis.derive import CheckKind, DerivationError
from src.analysis.provenance import ValidationStatus

REPO = Path(__file__).resolve().parent.parent.parent
FIXTURES = REPO / "tests" / "fixtures" / "analyzer"


def _fixture(name: str):
    directory = FIXTURES / name
    expected = json.loads((directory / "expected.json").read_text())
    source = directory / expected["source_file"]
    return source, expected


# ---------------------------------------------------------------------------
# Against the committed fixtures (T135).


@pytest.mark.parametrize("name", ["inventory-service", "no-derivable-checks"])
def test_the_derivation_matches_the_committed_expected_output(name) -> None:
    source, expected = _fixture(name)
    contracts = derive.derive_module(source, relative_to=source.parent)

    actual = [c.to_expected() for c in contracts]
    want = expected["contracts"]

    assert [c["operation_id"] for c in actual] == [
        c["operation_id"] for c in want
    ], "the operation set differs from the hand-written expectation"

    for got, wanted in zip(actual, want):
        for key in (
            "reads",
            "writes",
            "preconditions",
            "postconditions",
            "failure_taxonomy",
            "checks",
        ):
            assert got[key] == wanted[key], (
                f"{wanted['operation_id']}: {key} differs\n"
                f"  derived : {got[key]}\n"
                f"  expected: {wanted[key]}"
            )


def test_the_committed_source_hashes_still_match_the_fixture() -> None:
    """The coupling arm. Editing `service.py` must turn this red.

    FR-028 needs a source change that invalidates a derived contract to be
    detected in the same run as the change. This is the fixture-scale version:
    the hash is committed, so the fixture cannot be edited without the
    expectation being revisited.
    """
    source, expected = _fixture("inventory-service")
    contracts = derive.derive_module(source, relative_to=source.parent)
    by_id = {c.operation_id: c for c in contracts}

    for wanted in expected["contracts"]:
        got = by_id[wanted["operation_id"]]
        assert got.provenance.content_hash == wanted["provenance"]["content_hash"], (
            f"{wanted['operation_id']}: the source construct changed. If that "
            "was deliberate, re-read the expected derivation before updating "
            "the hash — the point of this arm is that the two move together."
        )


def test_the_negative_fixture_derives_nothing() -> None:
    """Named separately from the parametrized arm because it is the whole test.

    An analyzer that emits something for every function it sees would pass every
    positive arm above.
    """
    source, _ = _fixture("no-derivable-checks")
    assert derive.derive_module(source, relative_to=source.parent) == ()


# ---------------------------------------------------------------------------
# Provenance on everything (T121's requirement, checked at the producer).


def test_every_derived_contract_and_check_carries_provenance() -> None:
    source, _ = _fixture("inventory-service")
    contracts = derive.derive_module(source, relative_to=source.parent)
    assert contracts

    for contract in contracts:
        assert contract.provenance is not None, contract.operation_id
        assert contract.provenance.source_file == "service.py"
        for check in contract.checks:
            assert check.provenance is not None, check.quantity
            assert check.provenance.source_symbol == contract.provenance.source_symbol


def test_nothing_the_derivation_produces_is_presented_as_validated() -> None:
    """FR-026 and Principle I. Static derivation holds no independent artifact,
    so `validated` here would be a claim with nothing behind it. T122 is what
    may promote one, and only with the target's published specification."""
    source, _ = _fixture("inventory-service")
    for contract in derive.derive_module(source, relative_to=source.parent):
        assert contract.provenance.validation_status is ValidationStatus.PROVISIONAL
        for check in contract.checks:
            assert check.provenance.validation_status is ValidationStatus.PROVISIONAL


# ---------------------------------------------------------------------------
# The recomputation property. This is the part T124 and T132 depend on.


def test_at_least_one_derived_check_expresses_a_recomputation() -> None:
    source, _ = _fixture("inventory-service")
    checks = [c for k in derive.derive_module(source, relative_to=source.parent)
              for c in k.checks]
    recomputing = [c for c in checks if c.recomputes()]
    assert recomputing, (
        "every derived check is a shape assertion. A shape-only derivation "
        "makes T132's negative control unsatisfiable and reproduces the 8 "
        "schema-blind numeric false successes feature 001 measured"
    )


def test_a_recomputation_check_reads_something_other_than_the_quantity() -> None:
    """Independence, enforced by the type rather than hoped for.

    A `total_units` check that recomputed by reading `total_units` would be
    conformant, cheap and worthless. T129 owes the corpus-wide contract test;
    this is the constructor refusing the degenerate case.
    """
    source, _ = _fixture("inventory-service")
    for contract in derive.derive_module(source, relative_to=source.parent):
        for check in contract.checks:
            if not check.recomputes():
                continue
            assert check.quantity not in check.recomputation.reads
            assert check.recomputation.reads


def test_a_self_referential_recomputation_is_refused() -> None:
    with pytest.raises(DerivationError) as excinfo:
        derive.DerivedCheck(
            operation_id="m.f",
            quantity="total",
            check_kind=CheckKind.RECOMPUTATION,
            expression="total == sum(total)",
            recomputation=derive.Recomputation(
                operator="sum", over="total", element_field=None, reads=("total",)
            ),
            provenance=_provenance("aggregate_binding"),
        )
    assert "independent" in str(excinfo.value).lower()


def test_a_recomputation_kind_without_a_recomputation_is_refused() -> None:
    with pytest.raises(DerivationError):
        derive.DerivedCheck(
            operation_id="m.f",
            quantity="total",
            check_kind=CheckKind.RECOMPUTATION,
            expression="total == ???",
            recomputation=None,
            provenance=_provenance("aggregate_binding"),
        )


def test_a_shape_check_may_not_smuggle_a_recomputation() -> None:
    """So `check_kind` stays a fact a consumer can filter on. T132 filters on it."""
    with pytest.raises(DerivationError):
        derive.DerivedCheck(
            operation_id="m.f",
            quantity="total",
            check_kind=CheckKind.SHAPE,
            expression="isinstance(total, int)",
            recomputation=derive.Recomputation(
                operator="count", over="rows", element_field=None, reads=("rows",)
            ),
            provenance=_provenance("return_annotation"),
        )


def test_the_shape_only_subset_cannot_express_the_numeric_fault() -> None:
    """T132's premise, stated here as a property of the derivation's output.

    Filter the derived checks to shape and type only — which is what T132's
    control verifier is — and no surviving check mentions any quantity whose
    correctness is numeric. That is the same statement as *the control detects
    none of the value faults*, made one layer earlier where it is cheap.
    """
    source, _ = _fixture("inventory-service")
    checks = [c for k in derive.derive_module(source, relative_to=source.parent)
              for c in k.checks]

    shape_only = [c for c in checks if c.check_kind is CheckKind.SHAPE]
    assert shape_only, "the control needs something to run, or it is vacuous"
    for check in shape_only:
        assert check.recomputation is None
        assert check.quantity == "<return>", (
            "a shape check on a named numeric quantity would let the control "
            "verifier appear to cover it"
        )

    numeric = {c.quantity for c in checks if c.recomputes()}
    assert numeric == {"lot_count", "total_units", "oldest"}
    assert numeric.isdisjoint({c.quantity for c in shape_only})


def test_no_precision_source_is_a_bare_number() -> None:
    """FR-024 property 2: no rung may name a numeric value.

    T125 owns the ladder. What T120 owes is that nothing it emits hands the
    ladder a constant to fall back to.
    """
    source, _ = _fixture("inventory-service")
    for contract in derive.derive_module(source, relative_to=source.parent):
        for check in contract.checks:
            if check.precision_source is None:
                continue
            assert not _looks_numeric(check.precision_source), check.precision_source


def test_a_numeric_precision_source_is_refused() -> None:
    with pytest.raises(DerivationError) as excinfo:
        derive.DerivedCheck(
            operation_id="m.f",
            quantity="total",
            check_kind=CheckKind.SHAPE,
            expression="isinstance(total, float)",
            recomputation=None,
            provenance=_provenance("return_annotation"),
            precision_source="0.01",
        )
    assert "default tolerance" in str(excinfo.value).lower()


def _looks_numeric(text: str) -> bool:
    try:
        float(text)
    except ValueError:
        return False
    return True


def _provenance(rule: str):
    from src.analysis.provenance import Provenance

    return Provenance(
        derivation_rule=rule,
        source_symbol="f",
        source_file="m.py",
        content_hash="sha256:" + "b" * 64,
    )


# ---------------------------------------------------------------------------
# The artifacts conform to FR-054's schemas and survive FR-055's scanner.


def test_a_derived_contract_wraps_as_its_declared_artifact_kind() -> None:
    from src.contracts.envelope import wrap

    source, _ = _fixture("inventory-service")
    for contract in derive.derive_module(source, relative_to=source.parent):
        envelope = wrap("derived_contract", contract.to_document(deployment_id="d-1"))
        assert envelope.address.startswith("sha256:")


def test_a_derived_check_wraps_as_its_declared_artifact_kind() -> None:
    from src.contracts.envelope import wrap

    source, _ = _fixture("inventory-service")
    for contract in derive.derive_module(source, relative_to=source.parent):
        for check in contract.checks:
            wrap("derived_check", check.to_document(deployment_id="d-1"))


def test_re_deriving_the_same_source_is_byte_identical() -> None:
    """FR-055 and FR-002. Two runs, same input, same address."""
    from src.contracts.envelope import wrap

    source, _ = _fixture("inventory-service")
    first = [wrap("derived_contract", c.to_document(deployment_id="d-1")).address
             for c in derive.derive_module(source, relative_to=source.parent)]
    second = [wrap("derived_contract", c.to_document(deployment_id="d-1")).address
              for c in derive.derive_module(source, relative_to=source.parent)]
    assert first == second


# ---------------------------------------------------------------------------
# No model call anywhere in it.

#: Anything through which a model's assessment, or a network round trip that
#: could fetch one, could reach the derivation.
FORBIDDEN_MODULES = (
    "src.runtime.providers",
    "src.runtime.loop",
    "src.runtime.turn",
    "src.runtime.dispatch",
    "anthropic",
    "openai",
    "google.genai",
    "httpx",
    "requests",
    "aiohttp",
    "urllib.request",
    "http.client",
    "socket",
)

FIRST_PARTY = "src."


def _imports_of(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
    return names


def _module_path(root: Path, module: str) -> Path | None:
    candidate = root / (module.replace(".", "/") + ".py")
    if candidate.is_file():
        return candidate
    package = root / module.replace(".", "/") / "__init__.py"
    return package if package.is_file() else None


def model_reachable_from(root: Path, entry: str = "src.analysis.derive") -> list[str]:
    """Every path from `entry` to a model or network module, transitively.

    Transitive on purpose: a derivation that imports a helper that imports a
    provider adapter still has a model in it, and a one-level scan would call
    that clean.
    """
    seen: set[str] = set()
    found: list[str] = []
    frontier = [(entry, (entry,))]
    while frontier:
        module, trail = frontier.pop()
        if module in seen:
            continue
        seen.add(module)
        path = _module_path(root, module)
        if path is None:
            continue
        for imported in sorted(_imports_of(path)):
            for forbidden in FORBIDDEN_MODULES:
                if imported == forbidden or imported.startswith(forbidden + "."):
                    found.append(" -> ".join(trail + (imported,)))
            if imported.startswith(FIRST_PARTY):
                frontier.append((imported, trail + (imported,)))
    return found


def test_no_model_or_network_reaches_the_derivation() -> None:
    paths = model_reachable_from(REPO)
    assert paths == [], (
        "T120 / FR-023: the derivation is static and has no model in it. "
        "A reachable model or network module means a check could be derived "
        "from an assessment rather than from an artifact the codebase "
        "contains:\n  " + "\n  ".join(paths)
    )


def test_the_model_scan_fires_on_a_planted_import(tmp_path) -> None:
    """One hop, so a direct import is caught."""
    (tmp_path / "src" / "analysis").mkdir(parents=True)
    (tmp_path / "src" / "analysis" / "derive.py").write_text(
        "from src.runtime.providers.adapter import complete\n"
    )
    assert model_reachable_from(tmp_path) == [
        "src.analysis.derive -> src.runtime.providers.adapter"
    ]


def test_the_model_scan_fires_two_hops_away(tmp_path) -> None:
    """The arm that makes the closure worth walking.

    A one-level scan reports this tree clean, and it has a provider in it.
    """
    (tmp_path / "src" / "analysis").mkdir(parents=True)
    (tmp_path / "src" / "analysis" / "derive.py").write_text(
        "from src.analysis.helper import thing\n"
    )
    (tmp_path / "src" / "analysis" / "helper.py").write_text("import anthropic\n")

    assert model_reachable_from(tmp_path) == [
        "src.analysis.derive -> src.analysis.helper -> anthropic"
    ]


def test_the_derivation_module_itself_declares_no_model_call() -> None:
    """A belt to the transitive scan's braces: no call named like a completion.

    Cheap, and it catches the case where a model is reached through a module
    that is already imported for another reason.
    """
    tree = ast.parse((REPO / "src" / "analysis" / "derive.py").read_text())
    called = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    for suspicious in ("complete", "completion", "chat", "generate", "invoke_model"):
        assert suspicious not in called, suspicious
