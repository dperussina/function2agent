"""T120 — static derivation of contracts and checks from source. No model in it.

**Requirement**: T-13 and FR-023 — *"Every verification check MUST derive from
an artifact the target codebase already contains — signatures, return types,
preconditions, postconditions, invariants, exception classes, existing tests, or
observable state. A model's assessment MUST NOT be the success signal for any
result."*

## The constraint that decides this module's shape

A schema-only verifier is blind to the faults that matter. Feature 001 measured
**11 false successes, of which 8 were numeric-typed and schema-blind** — the
value was wrong and the shape was right — and the recorded v1 constraint is that
a shipping verifier **cannot be schema-only and must recompute postconditions by
an independent path**.

T120 is the derivation half of that, so the requirement lands here as: what this
module emits must be **capable of expressing a recomputation**, not merely a
shape assertion. That is why `CheckKind` has two members and why
`Recomputation` is a structured value rather than a string — T124 has to be able
to *run* it without parsing English, and T132 is a negative control asserting
that a shape-and-type-only verifier detects **none** of an injected fault
corpus. If everything here were a shape check, T132 would be unsatisfiable and
this whole capability would reduce to the thing it exists to beat.

## Independence is a constructor rule, not a convention

A check on `total_units` that recomputed `total_units` by reading `total_units`
would be conformant, cheap, and worth nothing. `DerivedCheck.__post_init__`
refuses it: a `RECOMPUTATION` must carry a `Recomputation`, and the quantity
under check may not appear in what that recomputation reads. T129 still owes the
corpus-wide contract test over real derivations; this is the degenerate case
being made unconstructible so that test has less to find.

## Why the source is Python's own `ast` and not `codegraph`'s index

**D-14** has the analysis layer reading `codegraph`'s SQLite artifact, and T119
is that invocation. This module reads source text with `ast` instead, and the
reason is measured rather than preferred: finding 007 records that Python
reached 100% on parameters *only* because the harness walks models through
inheritance with `ast`, **capability that does not exist in the index**, and
that the index's dedicated `return_type` column is empty across all 48,154
Python nodes. The index is the symbol graph; the contract lives in the syntax.
The two are complementary and neither is a substitute.

## What the rules deliberately do not read

**Docstrings.** Finding 004 measured `codegraph`'s `docstring` field populated
with *wrong* values rather than left empty (**U-27**) — a different and worse
risk class than a coverage gap, because a missing field is visibly missing and a
plausible wrong one is not. Prose describing a postcondition is not a
postcondition, and no rule here reads one.

## What "no model call anywhere in it" means operationally

It is a property of the **transitive first-party import closure**, and
`tests/unit/test_derive.py` walks it: a derivation that imports a helper that
imports a provider adapter still has a model in it. The scan is verified to fire
by planting an import one hop away and two hops away, because a scan nobody has
seen fail is a scan that might be reading the wrong tree.

## Scope, stated so nothing here is over-read

Five rules over Python. That is a *supported shape* under FR-053 only to the
extent the committed fixtures in `tests/fixtures/analyzer/` cover it, and they
cover exactly these five over hand-written synthetic source. This is not a
general contract extractor and finding 007's 0.8696/0.7681 figures are about a
different artifact against a real framework; they are not a claim about this
module.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Iterable

from src.analysis.provenance import (
    Provenance,
    ValidationStatus,
    hash_source_construct,
)
from src.contracts.schemas import DERIVED_CHECK, DERIVED_CONTRACT

__all__ = [
    "CheckKind",
    "DerivationError",
    "DerivedCheck",
    "DerivedContract",
    "Precondition",
    "Recomputation",
    "derive_module",
]

#: The name a check uses for the value the operation returns, where the source
#: gives it no name of its own. Not a valid identifier on purpose, so it cannot
#: collide with a quantity the source does name.
RETURN = "<return>"

#: The aggregates a recomputation can express. Each one is independently
#: computable from a collection the response carries, which is the whole
#: property: the verifier recomputes from the collection and never reads the
#: number under check.
AGGREGATES = {"count", "sum", "min", "max"}


class DerivationError(ValueError):
    """A derived artifact that does not hold together."""


class CheckKind(Enum):
    """Two kinds, and the distinction is the product.

    `SHAPE` is what feature 001's 8 schema-blind numeric false successes passed.
    It is emitted anyway — a wrong shape is still worth catching — but it is
    labelled so a consumer can filter on it, and T132's control verifier is
    exactly the subset that survives that filter.
    """

    SHAPE = "shape"
    RECOMPUTATION = "recomputation"


@dataclass(frozen=True)
class Recomputation:
    """An independent path to a reported quantity, as data rather than as prose.

    `reads` is every observable the recomputation touches, and it is what makes
    independence checkable: the quantity under check must not be in it.
    """

    operator: str
    over: str
    element_field: str | None
    reads: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.operator not in AGGREGATES:
            raise DerivationError(
                f"{self.operator!r} is not a recomputable aggregate. "
                f"Known: {sorted(AGGREGATES)}. A recomputation the verifier "
                "cannot execute is a description of one."
            )
        if not self.reads:
            raise DerivationError(
                "a recomputation that reads nothing computes nothing"
            )

    def to_payload(self) -> dict[str, Any]:
        return {
            "operator": self.operator,
            "over": self.over,
            "element_field": self.element_field,
            "reads": list(self.reads),
        }


@dataclass(frozen=True)
class Precondition:
    expression: str
    raises: str
    derivation_rule: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "expression": self.expression,
            "raises": self.raises,
            "derivation_rule": self.derivation_rule,
        }


@dataclass(frozen=True)
class DerivedCheck:
    """One check, with its provenance and — where it has one — its independent path."""

    operation_id: str
    quantity: str
    check_kind: CheckKind
    expression: str
    provenance: Provenance
    recomputation: Recomputation | None = None
    precision_source: str | None = None

    def __post_init__(self) -> None:
        if self.check_kind is CheckKind.RECOMPUTATION:
            if self.recomputation is None:
                raise DerivationError(
                    f"{self.operation_id}/{self.quantity}: check_kind is "
                    "`recomputation` and no recomputation is attached. The "
                    "kind is what T124 dispatches on and what T132 filters on; "
                    "a label with nothing behind it makes both wrong."
                )
            if self.quantity in self.recomputation.reads:
                raise DerivationError(
                    f"{self.operation_id}/{self.quantity}: the recomputation "
                    f"reads {self.quantity!r}, which is the quantity under "
                    "check. FR-022 requires an **independent** path — "
                    "recomputing a value from itself agrees with itself "
                    "whatever the value is."
                )
        elif self.recomputation is not None:
            raise DerivationError(
                f"{self.operation_id}/{self.quantity}: a `{self.check_kind.value}` "
                "check carries a recomputation. Either it recomputes and says "
                "so, or it does not and must not carry one — a consumer "
                "filtering on the kind would otherwise get a different answer "
                "from one reading the field."
            )
        if self.precision_source is not None and _is_numeric(self.precision_source):
            raise DerivationError(
                f"precision_source {self.precision_source!r} is a number. "
                "FR-024 property 2: every rung names a source of precision and "
                "no rung names a numeric value, because a ladder containing a "
                "constant is a default tolerance with extra steps."
            )

    def recomputes(self) -> bool:
        return self.check_kind is CheckKind.RECOMPUTATION

    def to_expected(self) -> dict[str, Any]:
        """The comparable form the committed fixtures are written in."""
        return {
            "quantity": self.quantity,
            "check_kind": self.check_kind.value,
            "expression": self.expression,
            "recomputation": (
                self.recomputation.to_payload() if self.recomputation else None
            ),
            "precision_source": self.precision_source,
            "derivation_rule": self.provenance.derivation_rule,
            "source_symbol": self.provenance.source_symbol,
        }

    def to_document(self, *, deployment_id: str) -> dict[str, Any]:
        """The FR-054 `derived_check` document. `confidence` is not a number.

        It is the validation status, spelled as the schema's field. A numeric
        confidence here would be invented — nothing in a static derivation
        measures one — and an invented number is worse than an absent one
        because it survives being copied.
        """
        return {
            "schema_version": DERIVED_CHECK.version,
            "deployment_id": deployment_id,
            "operation_id": self.operation_id,
            "check_kind": self.check_kind.value,
            "expression": self.expression,
            "quantity": self.quantity,
            "recomputation": (
                self.recomputation.to_payload() if self.recomputation else None
            ),
            "precision_source": self.precision_source,
            "provenance": self.provenance.to_payload(),
            "confidence": self.provenance.validation_status.value,
        }


@dataclass(frozen=True)
class DerivedContract:
    """What one operation requires and returns, plus the checks over it."""

    operation_id: str
    reads: tuple[str, ...]
    writes: tuple[str, ...]
    preconditions: tuple[Precondition, ...]
    postconditions: tuple[str, ...]
    failure_taxonomy: tuple[str, ...]
    provenance: Provenance
    checks: tuple[DerivedCheck, ...]

    def to_expected(self) -> dict[str, Any]:
        return {
            "operation_id": self.operation_id,
            "reads": list(self.reads),
            "writes": list(self.writes),
            "preconditions": [p.to_payload() for p in self.preconditions],
            "postconditions": list(self.postconditions),
            "failure_taxonomy": list(self.failure_taxonomy),
            "checks": [c.to_expected() for c in self.checks],
        }

    def to_document(self, *, deployment_id: str) -> dict[str, Any]:
        """The FR-054 `derived_contract` document.

        **`provenance` is carried and the schema does not require it.**
        `DERIVED_CONTRACT` at 1.0.0 lists `provenance` in neither `required` nor
        `volatile`, while FR-026 requires it on every derived contract *and*
        every derived check. So this producer satisfies FR-026 and the schema
        does not yet enforce it for any producer. Closing that is a schema
        change with a migration and it belongs with T133's coverage test; it is
        named here rather than done quietly.
        """
        return {
            "schema_version": DERIVED_CONTRACT.version,
            "deployment_id": deployment_id,
            "operation_id": self.operation_id,
            "reads": list(self.reads),
            "writes": list(self.writes),
            "preconditions": [p.to_payload() for p in self.preconditions],
            "postconditions": list(self.postconditions),
            "failure_taxonomy": list(self.failure_taxonomy),
            "provenance": self.provenance.to_payload(),
        }


# ---------------------------------------------------------------------------
# The rules. One function each, named for the rule it implements, so that a
# provenance record naming a rule points at code a reader can open.


def _is_numeric(text: str) -> bool:
    try:
        float(text)
    except ValueError:
        return False
    return True


def _unparse(node: ast.AST) -> str:
    return ast.unparse(node)


def _collection_of(node: ast.expr) -> tuple[str, str | None] | None:
    """`(collection, element_field)` for a generator over a named collection.

    Handles the two element accesses the fixtures use and nothing else:
    `x['field']` and `x.field`. Anything more is not recognised, and not
    recognising something is the correct outcome — an unrecognised expression
    produces no check rather than a guessed one.
    """
    if not isinstance(node, ast.GeneratorExp) or len(node.generators) != 1:
        return None
    comprehension = node.generators[0]
    if comprehension.ifs or not isinstance(comprehension.iter, ast.Name):
        return None
    collection = comprehension.iter.id
    target = comprehension.target
    if not isinstance(target, ast.Name):
        return None

    element = node.elt
    if (
        isinstance(element, ast.Subscript)
        and isinstance(element.value, ast.Name)
        and element.value.id == target.id
        and isinstance(element.slice, ast.Constant)
        and isinstance(element.slice.value, str)
    ):
        return collection, element.slice.value
    if (
        isinstance(element, ast.Attribute)
        and isinstance(element.value, ast.Name)
        and element.value.id == target.id
    ):
        return collection, element.attr
    if isinstance(element, ast.Name) and element.id == target.id:
        return collection, None
    return None


def _aggregate_of(node: ast.expr) -> Recomputation | None:
    """A `len`/`sum`/`min`/`max` over a named collection, as a `Recomputation`."""
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
        return None
    if len(node.args) != 1 or node.keywords:
        return None

    name = node.func.id
    argument = node.args[0]

    if name == "len" and isinstance(argument, ast.Name):
        return Recomputation(
            operator="count",
            over=argument.id,
            element_field=None,
            reads=(argument.id,),
        )
    if name in {"sum", "min", "max"}:
        # `max(ages)` over a local list is not independent of how `ages` was
        # built, so only a generator naming its own collection qualifies.
        found = _collection_of(argument)
        if found is None:
            return None
        collection, element_field = found
        return Recomputation(
            operator=name,
            over=collection,
            element_field=element_field,
            reads=(collection,),
        )
    return None


def _render(quantity: str, recomputation: Recomputation) -> str:
    if recomputation.element_field is None:
        inner = recomputation.over
    else:
        inner = f"{recomputation.over}[].{recomputation.element_field}"
    return f"{quantity} == {recomputation.operator}({inner})"


def _precondition_guards(body: list[ast.stmt]) -> list[tuple[str, str]]:
    """Leading `if <cond>: raise <E>(...)` statements, in source order.

    Leading only. A guard buried after work has been done is not a
    precondition, and reading one as such would attach a claim to the wrong
    part of the operation.
    """
    found: list[tuple[str, str]] = []
    for index, statement in enumerate(body):
        # The docstring is a statement and it is not work, so it does not end
        # the leading run. Nothing else is skipped: a guard that follows an
        # assignment is guarding something already computed and is not a
        # precondition on the operation.
        if index == 0 and _is_docstring(statement):
            continue
        if not isinstance(statement, ast.If) or statement.orelse:
            break
        if len(statement.body) != 1 or not isinstance(statement.body[0], ast.Raise):
            break
        exception = _raised_name(statement.body[0])
        if exception is None:
            break
        found.append((_unparse(statement.test), exception))
    return found


def _is_docstring(statement: ast.stmt) -> bool:
    return (
        isinstance(statement, ast.Expr)
        and isinstance(statement.value, ast.Constant)
        and isinstance(statement.value.value, str)
    )


def _raised_name(node: ast.Raise) -> str | None:
    exc = node.exc
    if isinstance(exc, ast.Call) and isinstance(exc.func, ast.Name):
        return exc.func.id
    if isinstance(exc, ast.Name):
        return exc.id
    return None


def _raised_exception_classes(function: ast.FunctionDef) -> list[str]:
    names: list[str] = []
    for node in ast.walk(function):
        if isinstance(node, ast.Raise):
            name = _raised_name(node)
            if name is not None and name not in names:
                names.append(name)
    return names


def _returned_mapping(function: ast.FunctionDef) -> ast.Dict | None:
    for node in ast.walk(function):
        if isinstance(node, ast.Return) and isinstance(node.value, ast.Dict):
            return node.value
    return None


def _postcondition_asserts(function: ast.FunctionDef) -> list[tuple[str, Recomputation]]:
    """`assert <name> == <aggregate>` — the author's own independent path."""
    found: list[tuple[str, Recomputation]] = []
    for node in ast.walk(function):
        if not isinstance(node, ast.Assert) or not isinstance(node.test, ast.Compare):
            continue
        compare = node.test
        if len(compare.ops) != 1 or not isinstance(compare.ops[0], ast.Eq):
            continue
        if not isinstance(compare.left, ast.Name):
            continue
        recomputation = _aggregate_of(compare.comparators[0])
        if recomputation is None:
            continue
        found.append((compare.left.id, recomputation))
    return found


# ---------------------------------------------------------------------------
# The entry point.


def derive_module(
    source_path: str | Path, *, relative_to: str | Path | None = None
) -> tuple[DerivedContract, ...]:
    """Derive a contract per module-level function, statically and offline.

    A function from which no rule fires produces **no contract**. That is the
    load-bearing default: an analyzer that emits something for everything it
    sees cannot be told apart from one that is right, and *fluent, plausible and
    wrong* is the failure class this corpus has measured twice by two different
    mechanisms.
    """
    path = Path(source_path)
    root = Path(relative_to) if relative_to is not None else path.parent
    relative = path.relative_to(root).as_posix()
    module = path.stem

    text = path.read_text()
    tree = ast.parse(text, filename=str(path))

    contracts: list[DerivedContract] = []
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef) or node.name.startswith("_"):
            continue
        contract = _derive_function(node, text, module=module, relative=relative)
        if contract is not None:
            contracts.append(contract)
    return tuple(contracts)


def _derive_function(
    function: ast.FunctionDef, text: str, *, module: str, relative: str
) -> DerivedContract | None:
    # `module:function`, setuptools' entry-point syntax, and deliberately not
    # `module.function`. The dotted form is hostname-shaped — `service.reserve`
    # reads as `name.tld` to `envelope.scan` — and excusing it would weaken the
    # scanner over a field that, for a served HTTP target, is `GET /parts/{id}`
    # and would never have tripped it. The separator is the cheaper fix.
    operation_id = f"{module}:{function.name}"
    segment = ast.get_source_segment(text, function) or ""
    content_hash = hash_source_construct(segment)

    def provenance(rule: str) -> Provenance:
        # `PROVISIONAL` is not a default that was left alone: a static
        # derivation holds no artifact its own derivation did not produce, so
        # under FR-026 and Principle I there is no other status it may claim.
        return Provenance(
            derivation_rule=rule,
            source_symbol=function.name,
            source_file=relative,
            content_hash=content_hash,
            validation_status=ValidationStatus.PROVISIONAL,
        )

    checks: list[DerivedCheck] = []
    postconditions: list[str] = []

    # -- return_annotation -------------------------------------------------
    if function.returns is not None:
        checks.append(
            DerivedCheck(
                operation_id=operation_id,
                quantity=RETURN,
                check_kind=CheckKind.SHAPE,
                expression=f"isinstance({RETURN}, {_unparse(function.returns)})",
                provenance=provenance("return_annotation"),
            )
        )

    # -- aggregate_binding -------------------------------------------------
    mapping = _returned_mapping(function)
    if mapping is not None:
        for key, value in zip(mapping.keys, mapping.values):
            if not (isinstance(key, ast.Constant) and isinstance(key.value, str)):
                continue
            recomputation = _aggregate_of(value)
            if recomputation is None:
                continue
            expression = _render(key.value, recomputation)
            postconditions.append(expression)
            checks.append(
                DerivedCheck(
                    operation_id=operation_id,
                    quantity=key.value,
                    check_kind=CheckKind.RECOMPUTATION,
                    expression=expression,
                    recomputation=recomputation,
                    precision_source=f"aggregate_over:{recomputation.operator}",
                    provenance=provenance("aggregate_binding"),
                )
            )

    # -- postcondition_assert ----------------------------------------------
    for quantity, recomputation in _postcondition_asserts(function):
        expression = _render(quantity, recomputation)
        postconditions.append(expression)
        checks.append(
            DerivedCheck(
                operation_id=operation_id,
                quantity=quantity,
                check_kind=CheckKind.RECOMPUTATION,
                expression=expression,
                recomputation=recomputation,
                precision_source=f"aggregate_over:{recomputation.operator}",
                provenance=provenance("postcondition_assert"),
            )
        )

    # -- precondition_guard and raises_statement ---------------------------
    preconditions = tuple(
        Precondition(
            expression=expression,
            raises=exception,
            derivation_rule="precondition_guard",
        )
        for expression, exception in _precondition_guards(function.body)
    )
    failures = tuple(_raised_exception_classes(function))

    if not checks and not preconditions and not failures:
        return None

    return DerivedContract(
        operation_id=operation_id,
        reads=tuple(argument.arg for argument in function.args.args),
        writes=(),
        preconditions=preconditions,
        postconditions=tuple(postconditions),
        failure_taxonomy=failures,
        provenance=provenance("return_annotation" if function.returns else "raises_statement"),
        checks=tuple(checks),
    )
