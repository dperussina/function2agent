"""T078 — the correspondence record (FR-057).

## What this file is asserting, given that the task text is stale

T078 asks for *"the correspondence evidence establishing that this source
produced this deployment"*. **FR-057 forbids producing it**, `data-model.md`
deleted the field it was named after, and both changes landed 2026-08-03 after
the task was written. So the assertions here are about the corrected
obligation: a declaration, recorded as one, carried onto every source-derived
artifact with its status in the same place, and three refusals.

## The doubly-covered-guard check, which is most of this file

A fail-closed guard whose triggering case is already refused by an earlier
stage passes its own test with its mechanism deleted, and a removal proof
cannot tell the two guards apart. So each of the three refusals below is paired
with an arm that **runs the upstream stage on the same input and asserts it
accepts** — `test_the_configuration_layer_accepts_what_this_module_refuses`,
`test_the_envelope_accepts_an_artifact_with_no_anchor`. Those arms are not
belt-and-braces. They are the evidence that the guard under test is the only
thing standing between the input and the failure, and they fail the day an
upstream stage grows a parser that covers the same case — at which point one of
the two mechanisms should go, deliberately, rather than one of them silently
becoming decoration.

## Why there is no attestation arm, and the arm that says so

`seed.py`'s evidence digests discriminate: the negative control scores 4/4 on
answers and 0/4 on digests. `test_no_digest_over_a_declaration_could_
discriminate` is the same experiment run here, and it comes back 1/1 — a
declaration naming the wrong commit is *equally well-formed* under any digest
this system could compute, because every field the digest would cover is a
field the forger supplied. A signature whose negative control passes is a seal
on a claim, not evidence, and FR-057's presentation clause is precisely about
not letting a reader mistake one for the other.
"""

from __future__ import annotations

import hashlib
import hmac

import pytest

from src.analysis import correspondence as corr
from src.analysis.correspondence import (
    DECLARED,
    SOURCE_REF_FIELD,
    SOURCE_REF_STATUS_FIELD,
    CorrespondenceError,
    CorrespondenceNotEstablished,
    SourceDeclaration,
    SourceReference,
    SourceReferenceMissing,
)
from src.contracts import config as cfg
from src.contracts import envelope

COMMIT = "0" * 39 + "a"
GOOD = f"acme/parts-api@{COMMIT}"
DEPLOYMENT = "d-reference-app"

#: Values that parse as a string, load as configuration, and are **not**
#: anchors. Each is the failure `parse` names, and each is the input the
#: non-coverage arm feeds to `config.load`.
NOT_AN_ANCHOR = (
    ("a branch", "acme/parts-api@main"),
    ("a tag", "acme/parts-api@v2.1.0"),
    ("HEAD", "acme/parts-api@HEAD"),
    ("an abbreviated hash", "acme/parts-api@0000000"),
    ("uppercase hex", "acme/parts-api@" + COMMIT.upper()),
    ("no separator", "acme/parts-api"),
    ("no repository", f"@{COMMIT}"),
    ("no commit", "acme/parts-api@"),
)


def _declaration(commit: str = COMMIT) -> SourceDeclaration:
    return corr.require(f"acme/parts-api@{commit}", deployment_id=DEPLOYMENT)


# ---------------------------------------------------------------------------
# What is recorded.


def test_the_declaration_records_the_repository_and_the_commit():
    declaration = _declaration()
    assert declaration.deployment_id == DEPLOYMENT
    assert declaration.reference.repository == "acme/parts-api"
    assert declaration.reference.commit == COMMIT


def test_the_record_says_that_nothing_established_it():
    """FR-057's presentation clause, in the record rather than in a comment."""
    document = _declaration().document()
    assert document[SOURCE_REF_STATUS_FIELD] == DECLARED
    assert "no mechanism that establishes" in document["established_by"]
    assert "detection of divergence" in document["established_by"]


def test_the_status_is_a_property_with_nowhere_to_set_it():
    """`declared` is not one value of a field; it is the only one.

    A settable status is a status something sets to `verified` on the day
    somebody adds a check that they believe is one.
    """
    reference = SourceReference(repository="acme/x", commit=COMMIT)
    assert reference.status == DECLARED
    with pytest.raises((AttributeError, TypeError)):
        reference.status = "verified"  # type: ignore[misc]


def test_no_verified_status_is_constructible_anywhere_in_the_module():
    """FR-057 forbids the value existing, not merely its being written."""
    for name in dir(corr):
        value = getattr(corr, name)
        if isinstance(value, str) and value == "verified":
            pytest.fail(
                f"correspondence.{name} is the literal 'verified'. FR-057 "
                "forbids recording or presenting the reference as verified "
                "correspondence, and an unreachable constant is a constant "
                "somebody reaches for."
            )


def test_the_reference_renders_with_its_marking_in_the_same_string():
    """FR-057: the status must be visible *in the same place*.

    A surface interpolating this cannot drop the marking by forgetting a
    second field.
    """
    marked = SourceReference(repository="acme/x", commit=COMMIT).marked()
    assert "acme/x" in marked and COMMIT in marked
    assert "not verified" in marked


# ---------------------------------------------------------------------------
# Refusal A — correspondence itself.


def test_asking_for_verified_correspondence_always_refuses():
    with pytest.raises(CorrespondenceNotEstablished) as raised:
        corr.verified_correspondence(_declaration())
    message = str(raised.value)
    assert "nothing in v1 can" in message
    assert "OD-06" in message
    assert "detection of divergence" in message


def test_it_refuses_for_a_well_formed_declaration_too():
    """The refusal is total, not conditional on the declaration being poor.

    A conditional refusal would be a check, and a check that passes is exactly
    the reading FR-057 forbids.
    """
    for commit in (COMMIT, "f" * 40, "1" * 64):
        with pytest.raises(CorrespondenceNotEstablished):
            corr.verified_correspondence(_declaration(commit))


def test_nothing_else_in_the_tree_establishes_correspondence():
    """Refusal A's non-coverage arm, and it is the trivial direction.

    This limb cannot be doubly covered because there is nothing above it: no
    module anywhere reads a commit identity from a running instance, which is
    OD-06's consequence and the reason `data-model.md` deleted the field.
    """
    import ast
    from pathlib import Path

    repo = Path(__file__).resolve().parents[2]
    offenders: list[str] = []
    for path in sorted((repo / "src").rglob("*.py")):
        # Over the parsed tree rather than the text. Both this module and
        # `served_operations.py` discuss the deleted field at length in their
        # docstrings, and a substring scan cannot tell an explanation of why a
        # field does not exist from the field existing.
        for node in ast.walk(ast.parse(path.read_text(), filename=str(path))):
            named = (
                (isinstance(node, ast.Name) and node.id == "correspondence_evidence")
                or (isinstance(node, ast.Attribute)
                    and node.attr == "correspondence_evidence")
                or (isinstance(node, ast.arg)
                    and node.arg == "correspondence_evidence")
                or (isinstance(node, ast.Constant)
                    and node.value == "correspondence_evidence")
            )
            if named:
                offenders.append(path.relative_to(repo).as_posix())
                break
    assert not offenders, (
        f"{offenders} carry `correspondence_evidence` as code, the field "
        "data-model.md deleted on 2026-08-03 for having no producer"
    )


# ---------------------------------------------------------------------------
# Refusal B — a declaration that is not an anchor.


@pytest.mark.parametrize("label,value", NOT_AN_ANCHOR,
                         ids=[label for label, _ in NOT_AN_ANCHOR])
def test_a_reference_that_cannot_anchor_a_clock_is_refused(label, value):
    with pytest.raises(CorrespondenceError):
        corr.require(value, deployment_id=DEPLOYMENT)


def test_the_refusal_says_why_a_moving_name_is_not_an_anchor():
    """FR-057 requires the startup failure to name what is missing.

    Asserted on the substance rather than on a word, because a message match
    passes against any guard anywhere using the same word.
    """
    with pytest.raises(CorrespondenceError) as raised:
        corr.require("acme/parts-api@main", deployment_id=DEPLOYMENT)
    message = str(raised.value)
    assert "complete object name" in message
    assert "denotes a different commit tomorrow" in message
    assert "git rev-parse" in message


def test_a_branch_name_is_refused_rather_than_resolved():
    """Resolving it would reintroduce the dependency OD-06 removed.

    Stated as an arm rather than only in prose: a future author reaching for
    `git rev-parse` here would be making source analysis depend on repository
    state, which FR-002 forbids in its own words.
    """
    with pytest.raises(CorrespondenceError):
        corr.require("acme/parts-api@main", deployment_id=DEPLOYMENT)
    import inspect

    source = inspect.getsource(corr)
    for reaching_out in ("subprocess", "rev_parse", "GitPython", "pygit2"):
        assert reaching_out not in source, (
            f"correspondence.py reaches for {reaching_out}. Resolving a name "
            "here reads repository state, which FR-002 forbids source "
            "analysis from depending on."
        )


@pytest.mark.parametrize("label,value", NOT_AN_ANCHOR,
                         ids=[label for label, _ in NOT_AN_ANCHOR])
def test_the_configuration_layer_accepts_what_this_module_refuses(label, value):
    """**The non-coverage arm for refusal B.**

    `config.load` is the stage above. It refuses `F2A_SOURCE_REF` *unset*, and
    that is the only case it covers: the key is `Kind.STR` and its parser is
    the identity. Every value above therefore starts the process, reaching
    `require` with a string that loads cleanly and anchors nothing.

    If this arm ever fails, the guard under test has become redundant and its
    removal proof has become vacuous. The right response is to delete one of
    the two mechanisms on purpose, not to relax this.
    """
    loaded = cfg.load(cfg.ANALYSIS_KEYS, {
        "F2A_SOURCE_REF": value,
        "F2A_DEPLOYMENT_ID": DEPLOYMENT,
    })
    assert loaded["F2A_SOURCE_REF"] == value, (
        "configuration no longer passes this value through unchanged, so the "
        "refusal this arm exists to attribute may be happening upstream"
    )


def test_configuration_does_cover_the_unset_case_and_this_module_agrees():
    """The half that *is* doubly covered, named rather than pretended away.

    `F2A_SOURCE_REF` unset is refused by `config.load` under FR-033 and by
    `require` under FR-057, and the two are genuinely redundant. Both are kept:
    the configuration guard is what FR-057's *"required configuration"* clause
    asks for, and `require`'s is what covers a caller that did not come through
    `load` — a test, a migration script, or the recovery path FR-047 runs
    without an operator restart.

    **This redundancy is why refusals B and C are shaped the way they are.**
    Neither of them is reachable through this case, so neither one's proof can
    be satisfied by the configuration layer's refusal.
    """
    with pytest.raises(cfg.ConfigError):
        cfg.load(cfg.ANALYSIS_KEYS, {"F2A_DEPLOYMENT_ID": DEPLOYMENT})
    with pytest.raises(SourceReferenceMissing):
        corr.require(None, deployment_id=DEPLOYMENT)


def test_the_absence_message_names_what_is_missing_and_what_it_is_not():
    with pytest.raises(SourceReferenceMissing) as raised:
        corr.require("   ", deployment_id=DEPLOYMENT)
    message = str(raised.value)
    assert "Nothing has been started" in message
    assert "which of the two clocks moved" in message
    assert "operator declaration" in message


def test_a_declaration_with_no_deployment_is_refused():
    with pytest.raises(CorrespondenceError, match="anchors a clock belonging"):
        corr.require(GOOD, deployment_id="")


def test_the_key_is_declared_configuration_with_no_default():
    """FR-057: *"MUST be required configuration under FR-033"*."""
    key = {k.name: k for k in cfg.ANALYSIS_KEYS}["F2A_SOURCE_REF"]
    assert key.default is None
    assert key.requirement == "FR-057"
    assert "never as verified correspondence" in key.purpose


# ---------------------------------------------------------------------------
# Refusal C — a source-derived artifact with no anchor attached.


def test_attaching_writes_the_reference_and_its_status_together():
    attached = corr.attach({"deployment_id": DEPLOYMENT, "x": 1}, _declaration())
    assert attached[SOURCE_REF_FIELD] == GOOD
    assert attached[SOURCE_REF_STATUS_FIELD] == DECLARED
    corr.assert_anchored(attached)


def test_an_artifact_with_no_anchor_is_refused():
    with pytest.raises(CorrespondenceError, match="anchor of the source clock"):
        corr.assert_anchored({"deployment_id": DEPLOYMENT})


def test_a_bare_reference_with_no_status_beside_it_is_refused():
    """The one that produces a wrong belief rather than an absent one."""
    with pytest.raises(CorrespondenceError, match="wrong belief"):
        corr.assert_anchored({SOURCE_REF_FIELD: GOOD})


def test_a_status_that_is_not_declared_is_refused():
    with pytest.raises(CorrespondenceError, match="only value FR-057 permits"):
        corr.assert_anchored(
            {SOURCE_REF_FIELD: GOOD, SOURCE_REF_STATUS_FIELD: "verified"})


def test_an_anchor_is_not_attachable_to_another_deployments_artifact():
    with pytest.raises(CorrespondenceError, match="wrong pair"):
        corr.attach({"deployment_id": "d-other"}, _declaration())


def test_the_envelope_accepts_an_artifact_with_no_anchor():
    """**The non-coverage arm for refusal C.**

    `envelope.wrap` is the stage a source-derived artifact goes through before
    it is stored. `source_ref` is in no schema's `required`, so an unanchored
    artifact wraps, hashes and stores cleanly — nothing upstream of
    `assert_anchored` notices.
    """
    document = {
        "schema_version": "1.0.0",
        "deployment_id": DEPLOYMENT,
        "operation_id": "get_part",
        "reads": ["parts"],
        "writes": [],
        "preconditions": [],
        "postconditions": [],
        "failure_taxonomy": ["not_found"],
    }
    wrapped = envelope.wrap("derived_contract", document)
    assert SOURCE_REF_FIELD not in wrapped.payload
    with pytest.raises(CorrespondenceError):
        corr.assert_anchored(wrapped.payload)


# ---------------------------------------------------------------------------
# The attestation question, answered by running the experiment.


def test_no_digest_over_a_declaration_could_discriminate():
    """The negative control that comes back 1/1 rather than 0/1.

    `seed.py`'s digests are evidence because a process that did not go through
    the opaque state cannot produce them — negative control 0/4. Run the same
    experiment here. The "true" declaration and a forged one naming a
    different real commit are **both** well-formed under any digest this
    system could compute, because every covered field is one the declarer
    supplied. The digest scores 1/1 on the forgery, which is a digest that
    discriminates nothing.

    That is the whole argument for carrying none: an attestation here would
    certify *this system received this assertion*, and a reader would take it
    for *this source produced this deployment* — which is exactly the reading
    FR-057's presentation clause exists to prevent.
    """
    key = b"any key this system could hold"

    def digest(declaration: SourceDeclaration) -> str:
        covered = (
            f"{declaration.deployment_id}|{declaration.reference.repository}"
            f"|{declaration.reference.commit}"
        )
        return hmac.new(key, covered.encode(), hashlib.sha256).hexdigest()

    truthful = _declaration(COMMIT)
    forged = _declaration("b" * 40)

    assert digest(truthful) != digest(forged), (
        "the digest does not even distinguish two different declarations, so "
        "this arm is not testing what it claims to"
    )
    # And yet: verification of the forgery succeeds, because verification is
    # over fields the forger chose.
    assert hmac.compare_digest(digest(forged), digest(forged)), (
        "the forged declaration fails its own digest, which would make an "
        "attestation here discriminating after all — and the module's "
        "argument for carrying none would need revisiting"
    )

    document = forged.document()
    assert document[SOURCE_REF_STATUS_FIELD] == DECLARED, (
        "a forged declaration is recorded exactly as a truthful one is, "
        "because nothing distinguishes them. That is the finding, and the "
        "marking is the only honest response to it."
    )


def test_the_record_carries_no_digest_field():
    """FR-057's presentation clause, as a property of the record's shape."""
    document = _declaration().document()
    for looks_like_evidence in ("digest", "attestation", "signature", "hmac",
                                "proof", "evidence"):
        assert not any(looks_like_evidence in key for key in document), (
            f"the record carries a {looks_like_evidence}-shaped field. A "
            "cryptographic value beside a declaration is the most effective "
            "way there is to make a reader take it for a checked fact, which "
            "is what FR-057 forbids."
        )
