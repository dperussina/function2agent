"""INV-013 — the package layering is declared, and no module-level import goes
up it.

## What this replaces, and why prose was not enough

The FR-024 pass ruled that `RefusalReason` does not belong in
`src/analysis/validate.py`, and proved it by planting the import and reading a
hard `ImportError`. That proof was real and the ruling stands. **The enforcement
behind it was an accident.** `RefusalReason` lives in `src/runtime/verify.py`,
`verify.py` imports from `validate.py`, and so an import the other way is a
cycle. Delete that one import — for any reason, in any unrelated change — and
the cycle disappears, the layering becomes unenforced, and **nothing anywhere
would report it**. A rule that holds because of an import somebody else happens
to have written is not a rule.

`test_the_pin_does_not_depend_on_the_cycle_that_used_to_enforce_it` is the arm
that makes this file's mechanism independent of that accident: it plants a tree
in which the downward import has been removed, so no cycle exists, and asserts
the upward edge is still reported.

## Narrow or general — measured, not assumed

The rule could have been written as narrowly as *"`src/analysis/` must not
import `src/runtime/`"*. It is written more generally, and the generality was
measured over the tree at the revision this landed rather than hoped for. Every
module-level import edge between packages under `src/`:

    src/contracts    -> (none)
    src/analysis     -> src/contracts
    src/supervisor   -> src/contracts
    src/sandbox      -> (none)
    src/runtime      -> src/contracts, src/analysis, src/supervisor

`src/runtime` has **zero** inbound edges and `src/contracts` has fifty-one. That
is a three-layer order the tree already obeys with no exceptions, so `LAYERS`
declares it and the narrow rule falls out as a consequence rather than being
stated separately. Nothing here was stated more widely than the measurement
supports: each of the three forbidden directions into `src/runtime` is forbidden
for the same concrete reason — `src/runtime` already imports that package, so
the edge would be a cycle.

## Module-level only, and the one deferred edge that exists

The rule is about **module-level** imports, because that is what a load-time
cycle is made of. `src/contracts/migrations/__init__.py` holds one deliberate
deferred upward import, annotated `noqa: PLC0415`, and deferring it is exactly
how that cycle is avoided. Rather than leave the escape hatch unwatched,
`test_the_deferred_upward_imports_are_the_ones_declared_here` enumerates it — a
second one is then a visible edit rather than a quiet one, which is the
direction `lifecycle-taxonomy` had to learn to check as well.

## What it cannot catch

An upward dependency expressed without an import — a string passed to
`importlib`, a plugin registry, a subprocess. Nothing static sees those, and
claiming otherwise would be the wider-than-the-tree-obeys error in a different
place.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent.parent

#: Lowest first. A package may import from a **strictly lower** layer only.
#: Same-layer imports are permitted: no sibling imports another today, but
#: forbidding it would be a rule about the future rather than a reading of the
#: tree, and this file only states what it measured.
LAYERS: tuple[tuple[str, ...], ...] = (
    ("src/contracts",),
    ("src/analysis", "src/supervisor", "src/sandbox"),
    ("src/runtime",),
)

#: The deferred upward imports that exist on purpose, each avoiding a load-time
#: cycle. Enumerated so that a second one is a visible edit — a list checked
#: only in the exempting direction goes blind the moment it is added to.
DECLARED_DEFERRED_UPWARD: frozenset[tuple[str, str]] = frozenset(
    {("src/contracts/migrations/__init__.py", "src.analysis.served_operations")}
)

#: The named case the FR-024 pass ruled on. Stated as data so the ruling is
#: readable here rather than only in a task note.
FR_024_FORBIDDEN = ("src/analysis", "src.runtime.verify")


def _layer_of(package: str) -> int | None:
    for index, members in enumerate(LAYERS):
        if package in members:
            return index
    return None


def _packages(root: Path) -> set[str]:
    return {
        p.relative_to(root).parent.as_posix()
        for p in (root / "src").rglob("*.py")
        if len(p.relative_to(root).parts) > 2
    }


def upward_edges(root: Path) -> list[str]:
    """Every module-level import from a package into a strictly higher layer."""
    found: list[str] = []
    for path in sorted((root / "src").rglob("*.py")):
        parts = path.relative_to(root).parts
        if len(parts) < 3:
            continue
        package = "/".join(parts[:2])
        source = _layer_of(package)
        if source is None:
            continue
        tree = ast.parse(path.read_text(), filename=str(path))
        # Top-level statements only. A deferred import is not a load-time cycle
        # and is handled by its own declared list.
        for node in tree.body:
            modules: list[str] = []
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                modules = [node.module]
            for module in modules:
                if not module.startswith("src."):
                    continue
                target = "/".join(module.split(".")[:2])
                destination = _layer_of(target)
                if destination is None or destination <= source:
                    continue
                found.append(
                    f"{path.relative_to(root).as_posix()} imports {module} "
                    f"(layer {source} -> layer {destination})"
                )
    return found


# ---------------------------------------------------------------------------
# The rule over the real tree.


def test_no_module_level_import_goes_up_a_layer() -> None:
    edges = upward_edges(REPO)
    assert edges == [], (
        "an import runs up the declared layering, which is a load-time cycle "
        "waiting for the downward edge to be written:\n  " + "\n  ".join(edges)
    )


def test_the_named_fr_024_case_holds_without_relying_on_a_cycle() -> None:
    """`src/analysis/` does not reach `RefusalReason`'s module.

    Asserted directly rather than inferred from the layer rule, because this is
    the specific ruling a reader arrives here looking for, and because an
    assertion that survives a rewrite of `LAYERS` is worth having.
    """
    package, forbidden = FR_024_FORBIDDEN
    offenders = []
    for path in sorted((REPO / package).rglob("*.py")):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            modules: list[str] = []
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                modules = [node.module]
            if any(
                m == forbidden or m.startswith(forbidden + ".") for m in modules
            ):
                offenders.append(path.relative_to(REPO).as_posix())

    assert offenders == [], (
        f"{offenders} import {forbidden}. FR-024's refusal reasons are the "
        "runtime's, and a verification vocabulary reached from the analysis "
        "layer inverts the dependency the whole tree is built on."
    )


# ---------------------------------------------------------------------------
# The checker fires, and does not fire on everything.


def _plant(root: Path, relative: str, body: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)


def test_the_checker_fires_on_a_planted_upward_import(tmp_path: Path) -> None:
    """The removal proof. A checker that never fires is no checker."""
    _plant(
        tmp_path,
        "src/analysis/planted.py",
        "from src.runtime.verify import RefusalReason\n\n"
        "def why():\n    return RefusalReason\n",
    )

    edges = upward_edges(tmp_path)

    assert edges, "the checker did not report a planted upward import"
    assert "src/analysis/planted.py" in edges[0]


def test_the_pin_does_not_depend_on_the_cycle_that_used_to_enforce_it(
    tmp_path: Path,
) -> None:
    """The whole reason this file exists.

    The tree planted here has **no downward edge at all** — no module under
    `src/runtime/` imports `src/analysis/` — so importing the other way is not
    a cycle and a bare interpreter would accept it happily. The rule still
    reports it, which is what makes this an enforcement rather than a side
    effect of somebody else's import.
    """
    _plant(tmp_path, "src/runtime/verify.py", "class RefusalReason:\n    pass\n")
    _plant(
        tmp_path,
        "src/analysis/validate.py",
        "from src.runtime.verify import RefusalReason\n",
    )

    edges = upward_edges(tmp_path)

    assert edges, (
        "with the downward import absent there is no cycle, and the upward "
        "edge went unreported — which is the state the FR-024 pass's proof "
        "would silently have decayed into"
    )
    assert "src/analysis/validate.py" in edges[0]


def test_the_checker_ignores_a_downward_import(tmp_path: Path) -> None:
    """A checker that fires on everything is also no checker."""
    _plant(
        tmp_path,
        "src/runtime/consumer.py",
        "from src.analysis.validate import ValidatedContract\n"
        "from src.contracts.result import Result\n",
    )

    assert upward_edges(tmp_path) == []


def test_a_deferred_upward_import_is_not_reported(tmp_path: Path) -> None:
    """The scope of the rule, asserted rather than described.

    Module level is what a load-time cycle is made of. If this arm failed, the
    rule would be firing on the one escape hatch the tree deliberately uses.
    """
    _plant(
        tmp_path,
        "src/contracts/deferred.py",
        "def later():\n    from src.runtime.verify import RefusalReason\n"
        "    return RefusalReason\n",
    )

    assert upward_edges(tmp_path) == []


# ---------------------------------------------------------------------------
# Vacuity floors.


def test_every_package_under_src_has_a_declared_layer() -> None:
    """A package with no layer is skipped by the checker, silently.

    Without this, adding `src/whatever/` would produce a package the rule does
    not read — and a rule that reads nothing agrees with everything.
    """
    unplaced = sorted(
        package
        for package in _packages(REPO)
        if _layer_of("/".join(package.split("/")[:2])) is None
    )
    assert unplaced == [], (
        f"packages under src/ with no layer in LAYERS: {unplaced}. Place them "
        "rather than leaving them unchecked."
    )


def test_the_declared_layers_all_exist() -> None:
    """The other direction: a layer naming a package that is gone.

    Reported separately from the arm above and deliberately not collapsed into
    one set comparison, because a name in both lists is the signature of a
    **rename** and is mechanically indistinguishable from one drop plus one
    add — and the two want different fixes.
    """
    declared = {name for layer in LAYERS for name in layer}
    present = {"/".join(p.split("/")[:2]) for p in _packages(REPO)}

    assert not (declared - present), (
        f"LAYERS names packages that do not exist: {sorted(declared - present)}"
    )


def test_the_checker_actually_reads_the_tree() -> None:
    """The floor the planted-tree arms cannot provide.

    Every arm above either reads a synthetic tree or asserts an empty result,
    and an empty result is what a checker walking the wrong directory also
    returns. This one asserts the real walk sees the packages it is supposed to.
    """
    packages = {"/".join(p.split("/")[:2]) for p in _packages(REPO)}

    assert {"src/analysis", "src/contracts", "src/runtime"} <= packages
    assert len(list((REPO / "src").rglob("*.py"))) > 50


@pytest.mark.parametrize("edge", sorted(DECLARED_DEFERRED_UPWARD))
def test_the_deferred_upward_imports_are_the_ones_declared_here(edge) -> None:
    """Each declared deferred edge must still be there.

    Checked in the forbidding direction as well as the exempting one: a
    declaration that only ever excuses something goes blind the moment the
    thing it excuses is removed, and the list then describes a tree that no
    longer exists.
    """
    relative, module = edge
    source = (REPO / relative).read_text()

    assert f"from {module} import" in source, (
        f"{relative} no longer defers an import of {module}. If the import "
        "went away, drop the entry; if it moved to module level, the rule "
        "above should be failing and this list is hiding it."
    )


def test_no_undeclared_deferred_upward_import_exists() -> None:
    """And the set is closed.

    A deferred upward import is a legitimate escape from a load-time cycle and
    an illegitimate way around this rule. The difference is whether anybody
    declared it.
    """
    found: set[tuple[str, str]] = set()
    for path in sorted((REPO / "src").rglob("*.py")):
        parts = path.relative_to(REPO).parts
        if len(parts) < 3:
            continue
        source_layer = _layer_of("/".join(parts[:2]))
        if source_layer is None:
            continue
        tree = ast.parse(path.read_text(), filename=str(path))
        top = {id(node) for node in tree.body}
        for node in ast.walk(tree):
            if id(node) in top:
                continue
            modules: list[str] = []
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                modules = [node.module]
            for module in modules:
                if not module.startswith("src."):
                    continue
                target_layer = _layer_of("/".join(module.split(".")[:2]))
                if target_layer is not None and target_layer > source_layer:
                    found.add((path.relative_to(REPO).as_posix(), module))

    assert found == DECLARED_DEFERRED_UPWARD, (
        f"undeclared deferred upward imports: {sorted(found - DECLARED_DEFERRED_UPWARD)}"
    )
