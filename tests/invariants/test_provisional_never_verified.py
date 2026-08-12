"""INV-012 / T123 — a provisional contract can produce NOT VERIFIABLE and never VERIFIED.

**Requirement**: constitution Principle I as amended at v1.1.0, which was
amended *specifically* to cover the derived-but-wrong verifier — a verifier
derived from the same source as the thing it checks can be confidently wrong.
`provisional` is the status that names that case, and this file is the half that
makes the status load-bearing rather than decorative.

## Why a runtime refusal was not enough, and what already existed

`src/contracts/result.py` has held a runtime refusal since T021:

    if self.provisional and self.verification is VerificationOutcome.VERIFIED:
        raise MissingVerification(...)

That satisfies the sentence's letter. It does not satisfy its point, for two
reasons this file's arms assert separately:

1. **A later caller can construct the forbidden combination and only find out at
   run time.** The refusal lives inside a constructor a caller reaches with the
   wrong pair already in hand.
2. **`Result.provisional` is a `bool` that defaults to `False`** — the unsafe
   value. A caller holding a provisional contract who does not pass the flag
   gets a `Result` that reads `VERIFIED` and trips nothing, because `False`
   means both *this contract was corroborated* and *nobody said*. That is the
   `spend_usd is None` against a measured zero defect, in a boolean.

So T123's contribution is **unreachability**, not a second check.
`src/analysis/validate.py` carries two distinct types with no inheritance
between them, and `Verified` names `ValidatedContract` in its own constructor.
A `ProvisionalContract` therefore cannot reach `Verified` — there is no argument
to pass and no method that returns one.

## What is type-enforced and what is refused at run time

**Honest split, because this repository's accepted form is a named partial.**

- *Type-enforced*: the return annotations, and `Verified`'s dependence on
  `ValidatedContract`. A checker rejects the forbidden program. **No type
  checker is in this repository's gate set** — mypy is not in the project venv —
  so the arm that exercises this skips with a named reason where mypy is
  absent rather than passing over nothing.
- *Construction-enforced, needing no checker*: `Verified` has no constructor
  that does not take a `ValidatedContract`, and `ValidatedContract` has one
  producer. This holds under a bare interpreter and is what the arms below
  mostly assert.
- *Runtime-refused*: an `isinstance` backstop for the case Python permits and a
  checker would have caught. Named as a backstop, not as the mechanism.

## The trap in this file, and how each arm avoids it

An arm asserting *this raises* is satisfied by a module that raises for any
reason — including one that does not import. **Every negative arm here pairs
with a positive one over the same mechanism**: the permitted construction is
built and asserted to succeed in the same test or its neighbour, so a broken
module fails the positive arm rather than silently confirming the negative one.
The mypy arms are the sharpest case and carry an explicit clean-control file.

`Verified` additionally requires a check that **recomputes**. That is not
decoration and it is what keeps T124 and T132 open: a shape-and-type-only
verifier holds no recomputation, so it cannot construct `Verified` at all, which
is precisely what T132 will assert about a control verifier over an injected
fault corpus. Promotion to `validated` is a **necessary** condition for
`Verified` and never a sufficient one — conformance to a declared shape is not
verification (T124, FR-022).
"""

from __future__ import annotations

import inspect
import shutil
import subprocess
import sys
import tempfile
import typing
from pathlib import Path

import pytest

from src.analysis.derive import CheckKind, DerivedCheck, derive_module
from src.analysis.validate import (
    ProvisionalContract,
    ProvisionalReason,
    RecomputationAgreement,
    ValidatedContract,
    Verified,
    validate_contract,
)
from src.contracts.result import Result, VerificationOutcome

REPO = Path(__file__).resolve().parent.parent.parent
FIXTURES = REPO / "tests" / "fixtures" / "analyzer"


def _contract(name: str = "stock_report"):
    """`stock_report` rather than `reserve`, and the choice is load-bearing.

    It is the one fixture function carrying **both** kinds: a declared return
    type (a `SHAPE` check) and two aggregate bindings (`RECOMPUTATION` checks).
    Both arms below need a real check of each kind off the same contract, and
    `reserve` deliberately has no recomputation — its own docstring says the
    return value is accumulated in a loop that no rule can turn into one.
    """
    contracts = derive_module(
        FIXTURES / "inventory-service" / "service.py",
        relative_to=FIXTURES / "inventory-service",
    )
    for contract in contracts:
        if contract.operation_id.endswith(f":{name}"):
            return contract
    raise AssertionError(
        f"no contract for {name!r}; the fixture derived "
        f"{[c.operation_id for c in contracts]}"
    )


def _provisional() -> ProvisionalContract:
    outcome = validate_contract(
        _contract(), specification=None, served_operation_id=None
    )
    assert isinstance(outcome, ProvisionalContract), (
        "the positive half of this fixture: a contract with no specification "
        "must come back provisional, or the arms below are asserting over the "
        "wrong object."
    )
    return outcome


def _validated() -> ValidatedContract:
    """A validated contract, built directly and deliberately.

    Constructed rather than promoted through `validate_contract` because these
    arms are about what `Verified` requires, not about promotion — and because a
    `ValidatedContract` a caller can build by hand is the residual this file
    names rather than hides. Python has no sealed constructor; what it has is a
    constructor that will not accept an empty artifact name.
    """
    contract = _contract()
    return ValidatedContract(
        contract=contract,
        validated_against="https://target.example/openapi.json",
        agreed_on=("sku", "quantity"),
        deployment_id="dep-1",
    )


def _recomputation_check() -> DerivedCheck:
    for check in _contract().checks:
        if check.recomputes():
            return check
    raise AssertionError(
        "the inventory-service fixture holds no recomputation check; T120's "
        "fixture expectation says three of its six checks recompute."
    )


def _shape_check() -> DerivedCheck:
    for check in _contract().checks:
        if not check.recomputes():
            return check
    raise AssertionError("the fixture holds no shape check")


# ---------------------------------------------------------------------------
# The two types are distinct, and neither is the other.


def test_provisional_and_validated_are_unrelated_types():
    """No inheritance either way.

    If `ProvisionalContract` were a subclass of `ValidatedContract`, every
    signature demanding the second would accept the first and the whole gate
    would be a naming convention.
    """
    assert not issubclass(ProvisionalContract, ValidatedContract)
    assert not issubclass(ValidatedContract, ProvisionalContract)


def test_no_method_on_a_provisional_contract_returns_verified():
    """The type-level statement, read off the annotations themselves.

    Asserted by introspection rather than by reading the file, so a method
    added later is covered without anyone remembering to update a list.
    """
    for name, member in inspect.getmembers(ProvisionalContract, inspect.isfunction):
        if name.startswith("__"):
            continue
        hints = typing.get_type_hints(member)
        returned = hints.get("return")
        reachable = set(typing.get_args(returned)) or {returned}
        assert Verified not in reachable, (
            f"ProvisionalContract.{name} can return Verified. A provisional "
            "contract must be able to produce NOT VERIFIABLE and never "
            "VERIFIED (constitution Principle I, v1.1.0)."
        )


def test_a_validated_contract_does_have_a_path_to_verified():
    """The positive control for the arm above.

    Without this, a `validate.py` in which *nothing* returns `Verified` — or in
    which `Verified` had been deleted — would pass the negative arm. The gate
    has to separate the two contracts, not forbid verification outright.
    """
    hints = typing.get_type_hints(ValidatedContract.verified)
    returned = hints.get("return")
    reachable = set(typing.get_args(returned)) or {returned}

    assert Verified in reachable


# ---------------------------------------------------------------------------
# Unreachability at run time, which needs no checker.


def test_verified_cannot_be_constructed_from_a_provisional_contract():
    provisional = _provisional()
    check = _recomputation_check()
    agreement = RecomputationAgreement(reported=2, recomputed=2)

    with pytest.raises(TypeError, match="provisional"):
        Verified(
            issued_by=provisional,  # type: ignore[arg-type]
            check=check,
            agreement=agreement,
        )


def test_verified_is_constructible_from_a_validated_contract():
    """The positive control for the arm above — the same three arguments.

    Only `issued_by` differs, which is what makes the pair evidence that the
    refusal is about the contract's validation status and not about one of the
    other two arguments being unacceptable.
    """
    verified = Verified(
        issued_by=_validated(),
        check=_recomputation_check(),
        agreement=RecomputationAgreement(reported=2, recomputed=2),
    )

    assert verified.outcome() is VerificationOutcome.VERIFIED


def test_a_provisional_contract_produces_not_verifiable_with_a_reason():
    """The permitted half of the sentence. It must actually work."""
    outcome = _provisional().not_verifiable()

    assert outcome.outcome() is VerificationOutcome.NOT_VERIFIABLE
    assert ProvisionalReason.NO_SPECIFICATION.value in outcome.reason


# ---------------------------------------------------------------------------
# `Verified` needs a recomputation, which is what keeps T124 and T132 open.


def test_a_shape_only_check_cannot_produce_verified():
    """T132's control verifier, blocked by construction rather than by policy.

    A shape-and-type-only verifier holds no recomputation. If this arm failed,
    T132 would be unsatisfiable: its control would be able to report VERIFIED
    and would stop being distinguishable from the real verifier at exactly the
    layer meant to separate them.
    """
    with pytest.raises(TypeError, match="recomput"):
        Verified(
            issued_by=_validated(),
            check=_shape_check(),
            agreement=RecomputationAgreement(reported=2, recomputed=2),
        )


def test_the_shape_check_this_arm_used_is_genuinely_a_shape_check():
    """Guards the arm above from passing for the wrong reason."""
    assert _shape_check().check_kind is CheckKind.SHAPE
    assert _recomputation_check().check_kind is CheckKind.RECOMPUTATION


# ---------------------------------------------------------------------------
# The agreement carries two values and compares them. No tolerance anywhere.


def test_an_agreement_refuses_two_values_that_are_not_equal():
    with pytest.raises(ValueError, match="3"):
        RecomputationAgreement(reported=2, recomputed=3)


def test_an_agreement_cannot_be_asserted_without_the_two_values():
    """No `agreed=True` shortcut exists.

    A boolean would let a caller assert agreement it never computed, which is
    the whole failure this type is shaped against.
    """
    parameters = set(inspect.signature(RecomputationAgreement.__init__).parameters)

    assert {"reported", "recomputed"} <= parameters
    assert not any("agree" in name for name in parameters if name != "self")


def test_an_agreement_refuses_a_float_and_names_precision_as_undecided():
    """FR-024 — no default tolerance is introduced here.

    Exact equality is the only comparison this type performs, so a float pair is
    refused rather than compared under a precision no source stated.

    **The refusal carries no named reason and is not expected to.** It is a
    construction error; FR-024's machine-readable reason for an unstated
    precision is `RefusalReason.PRECISION_NOT_STATED`, produced in
    `src/runtime/verify.py` before a pair reaches this type. This arm therefore
    matches on the message and not on an enum member — there is none to match.
    """
    with pytest.raises(ValueError, match="precision"):
        RecomputationAgreement(reported=2.0, recomputed=2.0)


def test_an_agreement_refuses_a_boolean_dressed_as_a_count():
    """`True == 1` in Python, so a boolean would compare equal to a count."""
    with pytest.raises(ValueError, match="bool"):
        RecomputationAgreement(reported=True, recomputed=1)


# ---------------------------------------------------------------------------
# The bridge to the existing Result, which is where the old runtime guard lives.


def test_the_bridge_marks_a_provisional_result_provisional():
    """`Result.provisional` defaults to the unsafe value, so it is passed here.

    The bridge is the sanctioned path from a contract to a `Result`. It exists
    because the flag's default is `False` and a caller that forgets it gets a
    result that reads VERIFIED and trips nothing.
    """
    result = _provisional().to_result(payload=None)

    assert result.provisional is True
    assert result.verification is VerificationOutcome.NOT_VERIFIABLE


def test_the_old_runtime_guard_still_refuses_the_hand_built_combination():
    """Not this file's mechanism, and asserted so the two are not confused.

    This is `src/contracts/result.py`'s check. It remains the backstop for a
    caller who bypasses the bridge, and the residual it does **not** cover is
    the caller who bypasses the bridge *and* leaves `provisional` defaulted.
    """
    with pytest.raises(Exception, match="provisional"):
        Result(VerificationOutcome.VERIFIED, payload=None, provisional=True)


def test_the_uncovered_residual_is_real_and_is_named_here():
    """The honest half: the default makes a wrong VERIFIED constructible.

    This arm asserts the **defect**, not the fix. `Result(VERIFIED, payload)`
    with `provisional` left at its default succeeds, and nothing in
    `src/contracts/result.py` can tell that caller apart from one whose
    contract really was validated. The fix is a required field on a type
    T126/T127 own; recording it as an executable statement is what stops it
    being rediscovered.
    """
    result = Result(VerificationOutcome.VERIFIED, payload=None)

    assert result.provisional is False
    assert result.is_verified is True


# ---------------------------------------------------------------------------
# Rule 8 — the negative control over the type-level claim itself.
#
# A green type-check is a positive result whose meaning is "no failure signal",
# so it needs a planted failure. Both arms below refuse to pass over nothing:
# where mypy is absent they skip with a named reason, because a `not ok` that is
# true only because of the host is not evidence.

_FORBIDDEN = '''
from src.analysis.validate import ProvisionalContract, Verified, RecomputationAgreement
from src.analysis.derive import DerivedCheck


def forbidden(p: ProvisionalContract, c: DerivedCheck) -> Verified:
    return Verified(
        issued_by=p,
        check=c,
        agreement=RecomputationAgreement(reported=1, recomputed=1),
    )
'''

_PERMITTED = '''
from src.analysis.validate import ValidatedContract, Verified, RecomputationAgreement
from src.analysis.derive import DerivedCheck


def permitted(v: ValidatedContract, c: DerivedCheck) -> Verified:
    return Verified(
        issued_by=v,
        check=c,
        agreement=RecomputationAgreement(reported=1, recomputed=1),
    )
'''


def _mypy() -> str:
    found = shutil.which("mypy")
    if found is None:
        pytest.skip(
            "mypy is not on PATH and is not in this project's venv, so the "
            "static half of T123 cannot be exercised here. It is NOT enforced "
            "by any of this repository's gates. This is a skip and not a pass: "
            "nothing was checked. Install mypy to run this arm."
        )
    return found


def _typecheck(source: str) -> subprocess.CompletedProcess:
    mypy = _mypy()
    with tempfile.TemporaryDirectory() as directory:
        planted = Path(directory) / "planted.py"
        planted.write_text(source)
        return subprocess.run(
            [mypy, "--no-incremental", "--cache-dir", directory, str(planted)],
            capture_output=True,
            text=True,
            cwd=REPO,
            env={"PATH": str(Path(sys.executable).parent), "MYPYPATH": str(REPO)},
        )


def test_the_permitted_construction_type_checks_clean():
    """The clean control. Without it, the arm below proves nothing.

    A module that fails to import, a wrong `MYPYPATH`, or a missing stub makes
    mypy report errors on **both** files, and the forbidden arm would then be
    green for a reason that has nothing to do with the type-level guarantee.
    """
    completed = _typecheck(_PERMITTED)

    assert completed.returncode == 0, (
        "the permitted construction does not type-check, so this environment "
        "cannot score the forbidden one either:\n"
        f"{completed.stdout}\n{completed.stderr}"
    )


def test_the_forbidden_construction_is_rejected_by_the_type_checker():
    """The planted failure, and it must fail for its own reason.

    The assertion is not merely that mypy exited non-zero — it is that the
    reported error names the argument the gate turns on. An exit code alone
    would be satisfied by a syntax error or an unresolved import.
    """
    completed = _typecheck(_FORBIDDEN)

    assert completed.returncode != 0, (
        "mypy accepted a Verified constructed from a ProvisionalContract. The "
        "type-level half of T123 is not holding.\n"
        f"{completed.stdout}"
    )
    assert "issued_by" in completed.stdout, (
        "mypy rejected the planted file but not for the reason this arm names. "
        "A rejection with a different cause is not evidence about the gate:\n"
        f"{completed.stdout}\n{completed.stderr}"
    )
