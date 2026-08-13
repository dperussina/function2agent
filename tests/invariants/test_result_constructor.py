"""INV-001 — no caller-visible result without a verification outcome (FR-025).

## Two readings of one sentence, and the second one arrived late

The arms above `THE CONSTRUCTION SITES` below check the **type**: `Result` has
no default for `verification`, so the absence is a `TypeError` from the
constructor rather than a `None` a later reader has to notice. That half is not
vacuous and was measured rather than assumed — a default on `Result.verification`
was planted on 2026-08-12 and fails two of those arms.

**What it did not range over was code paths, which is what the invariant's own
sentence names.** The same pass planted a second defect: a new `src/` module
constructing `Result(VerificationOutcome.VERIFIED, …)` with no verifier
reachable from it. It **passed all 200 invariants and all three static gates in
silence.** So *no code path constructs a caller-visible result without a
verification outcome* was true in the **field-presence** reading and unmeasured
in the **provenance** reading, and a field that is present because the author
typed a member of the enum is not a verification outcome in any sense FR-025
cares about.

The construction-site arms below close that. They could not have been written
earlier and the reason is not scheduling: until T213 built the seam at
`src/runtime/result_join.py` there was no join from a `VerificationReport` to a
`Result` for them to range over, and an authorised-site list whose every entry
was a `to_result` method would have been the vacuity it exists to prevent.

## What the construction-site arms can and cannot establish

**Can.** That the set of `src/` modules constructing a `Result` is exactly the
declared set, that every declared module holds a verification artifact, and that
both facts are checked by a scanner observed firing on a planted defect.

**Cannot.** That an authorised module's outcome is *earned*. Nothing static can
tell `Result(VerificationOutcome.VERIFIED, …)` inside `Verified.to_result` —
where the enclosing token has no constructor that does not take a
`ValidatedContract` and a check that recomputes — from the same line written by
hand in a module that imported `Verified` and never used it. What the arms make
expensive is the **naive** form of that defect, which is the one that was
actually planted and the one that actually passed: adding a construction site
now requires editing this file and naming a verification artifact in the module,
and both of those are visible acts in a diff.

**Also cannot.** See `dataclasses.replace`, which rebuilds a frozen dataclass
without a `Result(` call site. It re-runs `__post_init__`, so the type-level
half still holds over it; the scanner does not see it, and no arm here claims
otherwise.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path
from typing import Mapping

import pytest

from src.contracts import result as result_module
from src.contracts.result import (
    STALENESS_NOT_STATED,
    Corroboration,
    MissingVerification,
    Result,
    StaleMarking,
    VerificationOutcome,
)

REPO = Path(__file__).resolve().parent.parent.parent

#: The module the type lives in, as an import path. A site is a call to the name
#: this module's `Result` is bound to, however it was imported.
RESULT_MODULE = "src.contracts.result"

#: Every `src/` module permitted to construct a `Result`, and the verification
#: artifact that makes its outcome something other than the author's opinion.
#:
#: A list an author can add themselves to is a change-detector, which is why it
#: is not the only arm: `test_every_authorised_site_holds_a_verification_artifact`
#: requires the module to also hold one of `VERIFICATION_ARTIFACTS`, and plant 2
#: held none.
AUTHORISED_CONSTRUCTION_SITES: Mapping[str, str] = {
    "src/analysis/validate.py": (
        "Two sites, both inside a `to_result` method. `Verified.to_result` "
        "writes VERIFIED, and `Verified` has no constructor that does not take "
        "a ValidatedContract and a check that recomputes. "
        "`ProvisionalContract.to_result` reads its outcome off "
        "`NotVerifiable.outcome()` rather than naming one."
    ),
    "src/runtime/result_join.py": (
        "T213's seam, and the composition root OD-34 ② puts the join in. Its "
        "one site reads the outcome and the corroboration out of tables keyed "
        "on the VerificationReport member it was handed, so the values are a "
        "function of the report and not of the call site."
    ),
}

#: Types whose existence is itself a verification fact — none of them is
#: constructible without a contract, a comparison or a named refusal. A module
#: that constructs a `Result` and holds none of these got its outcome from
#: nowhere, which is plant 2's exact shape.
VERIFICATION_ARTIFACTS = frozenset(
    {
        "Verified",
        "ProvisionallyVerified",
        "Disagreement",
        "Refusal",
        "NotVerifiable",
        "ValidatedContract",
        "ProvisionalContract",
        "VerificationReport",
        "QuantityVerification",
    }
)


def _dotted(node: ast.expr) -> str:
    """`a.b.c` as a string, or `""` for anything that is not a dotted name."""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return ""
    parts.append(node.id)
    return ".".join(reversed(parts))


def _result_names(tree: ast.Module) -> tuple[set[str], set[str]]:
    """The local names `Result` reaches this module under.

    Returned as two sets because there are two spellings and an arm that read
    only the first would miss `import src.contracts.result as r; r.Result(...)`
    — which is a rename away from being the way a plant is written.
    """
    bare: set[str] = set()
    module_paths: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == RESULT_MODULE:
            bare.update(a.asname or a.name for a in node.names if a.name == "Result")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == RESULT_MODULE:
                    module_paths.add(alias.asname or alias.name)
    return bare, module_paths


def _names_in_scope(tree: ast.Module) -> set[str]:
    """Everything this module imported by name or defined as a class.

    Both, because `validate.py` **defines** the artifacts it vouches with and
    `result_join.py` **imports** them, and an arm reading only one of those
    would authorise exactly one of the two real sites.
    """
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names.update(alias.asname or alias.name for alias in node.names)
        elif isinstance(node, ast.ClassDef):
            names.add(node.name)
    return names


def construction_sites(root: Path) -> list[str]:
    """Every `Result(...)` call under `src/`, as `path:line`.

    Sorted, and reported with the line so that an unauthorised site is
    actionable from the failure message rather than from a second search.
    """
    found: list[str] = []
    for path in sorted((root / "src").rglob("*.py")):
        tree = ast.parse(path.read_text(), filename=str(path))
        bare, module_paths = _result_names(tree)
        if not bare and not module_paths:
            continue
        relative = path.relative_to(root).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            hit = (isinstance(func, ast.Name) and func.id in bare) or (
                isinstance(func, ast.Attribute)
                and func.attr == "Result"
                and _dotted(func.value) in module_paths
            )
            if hit:
                found.append(f"{relative}:{node.lineno}")
    return found


def verification_artifacts_held(root: Path, relative: str) -> set[str]:
    """The verification artifacts a module imports or defines."""
    tree = ast.parse((root / relative).read_text(), filename=relative)
    return _names_in_scope(tree) & VERIFICATION_ARTIFACTS


def test_verification_is_required() -> None:
    with pytest.raises(TypeError):
        Result(  # type: ignore[call-arg]
            payload={"ok": True}, corroboration=Corroboration.NOT_STATED
        )


def test_verification_must_be_a_member_not_a_string() -> None:
    with pytest.raises(MissingVerification):
        Result(  # type: ignore[arg-type]
            "verified",
            payload={"ok": True},
            corroboration=Corroboration.CORROBORATED,
        )


def test_no_absent_member_exists() -> None:
    """There is no value of the field meaning 'not verified yet'.

    A `PENDING` or `UNKNOWN` member would reintroduce exactly the state FR-025
    forbids, wearing a name that looks deliberate.
    """
    names = {member.name for member in VerificationOutcome}
    for forbidden in ("PENDING", "UNKNOWN", "NONE", "ABSENT", "UNSET"):
        assert forbidden not in names


def test_non_verified_outcome_requires_a_reason() -> None:
    with pytest.raises(MissingVerification):
        Result(
            VerificationOutcome.NOT_VERIFIABLE,
            payload=None,
            corroboration=Corroboration.NOT_STATED,
        )
    ok = Result(
        VerificationOutcome.NOT_VERIFIABLE,
        payload=None,
        corroboration=Corroboration.PROVISIONAL,
        reason="contract marked provisional",
    )
    assert not ok.is_verified


def test_model_assessment_is_not_a_verification() -> None:
    """Principle I: a model's opinion does not satisfy FR-025."""
    assessed = Result(
        VerificationOutcome.MODEL_ASSESSED,
        payload={"summary": "looks right"},
        corroboration=Corroboration.NOT_STATED,
        reason="no contract to check against",
    )
    assert not assessed.is_verified


def test_provisional_can_never_be_verified() -> None:
    with pytest.raises(MissingVerification):
        Result(
            VerificationOutcome.VERIFIED,
            payload=1,
            corroboration=Corroboration.PROVISIONAL,
        )


def test_corroboration_has_no_default_in_the_source() -> None:
    """The removal proof for T126's required argument, read off the source.

    Every behavioural arm here would keep passing if `corroboration` were given
    a default of `CORROBORATED`: nothing above omits it. This one fails on that
    edit, which is the edit that would restore the defect T126 removed — a
    caller reaching a verified-looking result by saying nothing.
    """
    source = Path(inspect.getfile(result_module)).read_text()
    tree = ast.parse(source)
    (cls,) = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.ClassDef) and n.name == "Result"
    ]
    fields = {
        n.target.id: n
        for n in cls.body
        if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name)
    }
    assert "corroboration" in fields, (
        "Result no longer carries a corroboration field. FR-025's verified "
        "state must say what established it."
    )
    assert fields["corroboration"].value is None, (
        "Result.corroboration has acquired a default. Whatever the default "
        "were, it would be a claim a caller makes by omission, which is the "
        "bool-defaulting-to-False defect T126 removed."
    )


def test_the_staleness_default_makes_no_claim() -> None:
    """FR-047's field may default; what it may not default to is a claim.

    `staleness` is the one field here that does have a default, and the
    asymmetry with `corroboration` is the whole design: `NOT_STATED` says
    nothing, where `FRESH` would say the served-operation set was current on
    the strength of a caller having omitted an argument. That is the boolean
    defect moved one field over, and this arm is what stops it moving.
    """
    assert Result(
        VerificationOutcome.VERIFIED,
        payload=None,
        corroboration=Corroboration.CORROBORATED,
    ).staleness.marking is StaleMarking.NOT_STATED

    assert STALENESS_NOT_STATED.marking is StaleMarking.NOT_STATED


def test_verification_has_no_default_in_the_source() -> None:
    """The removal proof, read off the source rather than the behaviour.

    Behaviour tests above would keep passing if someone gave `verification` a
    default of `VERIFIED` — the constructor would accept a missing argument and
    every assertion above still holds. This one fails on that edit.
    """
    source = Path(inspect.getfile(result_module)).read_text()
    tree = ast.parse(source)
    (cls,) = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.ClassDef) and n.name == "Result"
    ]
    fields = [n for n in cls.body if isinstance(n, ast.AnnAssign)]
    assert fields, "Result has no annotated fields"
    first = fields[0]
    assert isinstance(first.target, ast.Name)
    assert first.target.id == "verification", (
        "verification must be the first field, so a later field with a "
        "default cannot make it optional"
    )
    assert first.value is None, (
        "Result.verification has acquired a default. FR-025 admits no result "
        "without a verification outcome, and a default is one."
    )


# ---------------------------------------------------------------------------
# THE CONSTRUCTION SITES — T213, the half of INV-001's sentence the arms above
# do not reach. See the module docstring for what was planted, what passed, and
# why this could not be written before the seam existed.


def test_no_unauthorised_module_constructs_a_result() -> None:
    """Plant 2's arm. A `Result` built anywhere undeclared fails here.

    This is the whole of the provenance reading and it is deliberately a
    membership test rather than a judgement about the outcome passed: what makes
    an outcome sound is the artifact behind it, and no scanner reads that. What
    this makes impossible is the silent case — a construction site nobody
    declared, which is the one that was planted and passed.
    """
    declared = set(AUTHORISED_CONSTRUCTION_SITES)
    unauthorised = [
        site for site in construction_sites(REPO) if site.rsplit(":", 1)[0] not in declared
    ]
    assert unauthorised == [], (
        "FR-025 / INV-001: a caller-visible Result is constructed at a site "
        "nothing authorises, so its verification outcome is whatever the "
        "author typed. Either route it through the seam at "
        "src/runtime/result_join.py, or add the module to "
        "AUTHORISED_CONSTRUCTION_SITES in this file naming the verification "
        "artifact behind its outcome.\n  " + "\n  ".join(unauthorised)
    )


def test_every_authorised_site_still_constructs_one() -> None:
    """A dead entry silently widens the allowlist, so it is a failure.

    An authorised module that stopped constructing a `Result` leaves a name in
    the table that any later file at that path inherits. The list has to
    describe the tree rather than a tree somebody remembers.
    """
    live = {site.rsplit(":", 1)[0] for site in construction_sites(REPO)}
    dead = sorted(set(AUTHORISED_CONSTRUCTION_SITES) - live)
    assert dead == [], (
        "these modules are authorised to construct a Result and construct "
        "none. A stale entry pre-authorises whatever is written there next.\n"
        "  " + "\n  ".join(dead)
    )


def test_the_construction_site_scan_is_not_empty() -> None:
    """A scanner matching nothing passes every arm above it.

    `INV-003` is the standing example in this suite of an invariant that is
    true over an empty set and carries no weight. This is the check that keeps
    the construction-site arms from becoming another.
    """
    sites = construction_sites(REPO)
    assert sites, (
        "the scan found no Result construction anywhere in src/. Two of them "
        "are committed, so the scanner is broken and every arm reading it is "
        "passing over nothing."
    )


def test_the_checker_fires_on_an_unverified_construction_site(tmp_path: Path) -> None:
    """The removal proof: plant 2's exact shape, and require the scanner to see it.

    A checker that never fires is indistinguishable from no checker, and this
    is the fixture that tells them apart. The planted module is the one that
    passed all 200 invariants and all three static gates on 2026-08-12 — a
    `src/` module naming `VerificationOutcome.VERIFIED` with no verifier
    anywhere in it.
    """
    module = tmp_path / "src" / "runtime" / "summariser.py"
    module.parent.mkdir(parents=True)
    module.write_text(
        "from src.contracts.result import Corroboration, Result, "
        "VerificationOutcome\n\n\n"
        "def summarise(payload):\n"
        "    return Result(\n"
        "        VerificationOutcome.VERIFIED,\n"
        "        payload=payload,\n"
        "        corroboration=Corroboration.CORROBORATED,\n"
        "    )\n"
    )
    sites = construction_sites(tmp_path)
    assert sites == ["src/runtime/summariser.py:5"], sites
    assert not verification_artifacts_held(tmp_path, "src/runtime/summariser.py"), (
        "the planted module holds a verification artifact, so it is not "
        "plant 2's shape and this fixture is testing something else"
    )


def test_the_checker_sees_a_site_reached_through_the_module_path(
    tmp_path: Path,
) -> None:
    """`import src.contracts.result as r; r.Result(...)` is the same defect.

    Written as its own arm because the two spellings are read by two different
    branches, and a scanner that handled only the `from … import` form would be
    defeated by an import style rather than by an argument.
    """
    module = tmp_path / "src" / "runtime" / "aliased.py"
    module.parent.mkdir(parents=True)
    module.write_text(
        "import src.contracts.result as r\n\n\n"
        "def build(payload):\n"
        "    return r.Result(r.VerificationOutcome.VERIFIED, payload=payload,\n"
        "                    corroboration=r.Corroboration.CORROBORATED)\n"
    )
    assert construction_sites(tmp_path) == ["src/runtime/aliased.py:5"]


def test_the_checker_ignores_a_module_that_only_names_the_type(
    tmp_path: Path,
) -> None:
    """And a checker that fires on everything is also no checker.

    `src/runtime/serving.py` is the real instance: it imports `Result` for an
    annotation and constructs none. Reporting it would make the allowlist a
    list of importers, which is a different and much weaker property.
    """
    module = tmp_path / "src" / "runtime" / "serving.py"
    module.parent.mkdir(parents=True)
    module.write_text(
        "from src.contracts.result import Result\n\n\n"
        "class Frame:\n"
        "    result: Result | None = None\n"
    )
    assert construction_sites(tmp_path) == []


def test_every_authorised_site_holds_a_verification_artifact() -> None:
    """What stops the allowlist from being pure bookkeeping.

    Adding a module to `AUTHORISED_CONSTRUCTION_SITES` is not sufficient: the
    module must also import or define a type that cannot exist unless a
    verification, a validation or a named refusal happened. Plant 2 held none,
    so plant-2-plus-an-allowlist-edit still fails here.
    """
    for relative in sorted(AUTHORISED_CONSTRUCTION_SITES):
        held = verification_artifacts_held(REPO, relative)
        assert held, (
            f"{relative} is authorised to construct a caller-visible Result "
            "and holds no verification artifact — no Verified, no "
            "ValidatedContract, no VerificationReport, nothing. Its outcome "
            f"came from nowhere. Artifacts: {sorted(VERIFICATION_ARTIFACTS)}"
        )


def test_the_artifact_check_fires_on_a_module_that_holds_none(
    tmp_path: Path,
) -> None:
    """The removal proof for the arm above, over a tree it does not own."""
    module = tmp_path / "src" / "runtime" / "summariser.py"
    module.parent.mkdir(parents=True)
    module.write_text(
        "from src.contracts.result import Result\n\n\n"
        "def summarise(payload):\n    return Result\n"
    )
    assert verification_artifacts_held(tmp_path, "src/runtime/summariser.py") == set()

    module.write_text(
        "from src.analysis.validate import Verified\n"
        "from src.contracts.result import Result\n\n\n"
        "def summarise(token: Verified, payload):\n"
        "    return token.to_result(payload=payload)\n"
    )
    assert verification_artifacts_held(tmp_path, "src/runtime/summariser.py") == {
        "Verified"
    }


def test_the_seam_is_authorised_and_is_the_only_runtime_site() -> None:
    """OD-34 ② put the join in a composition root; this is that, as a fact.

    Stated separately from the membership arm because the two fail for
    different reasons and a reader of a red run needs to know which. This one
    fails when a **second** `src/runtime/` module starts building records — the
    shape where the seam exists and is bypassed, which the membership arm would
    report as an unauthorised site with no hint that a sanctioned route was
    already there.
    """
    runtime_sites = {
        site.rsplit(":", 1)[0]
        for site in construction_sites(REPO)
        if site.startswith("src/runtime/")
    }
    assert runtime_sites == {"src/runtime/result_join.py"}, (
        "src/runtime/result_join.py is the seam OD-34 minted T213 for. A "
        f"second runtime construction site bypasses it: {sorted(runtime_sites)}"
    )
