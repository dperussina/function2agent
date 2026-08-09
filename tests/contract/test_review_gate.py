"""T082 — the review gate, and the widening predicate it records against.

**Both halves of every absence are asserted here**, because a test that an
unreviewed version does not take effect passes just as well when nothing takes
effect at all. Every gate arm publishes a first version successfully, then runs
the same second version twice — once with an approval and once without — and
asserts that the reference moved in exactly one of them. The review is the only
difference between the two runs.

**The widening predicate has a narrowing control.** A predicate that only ever
sees widenings cannot show it discriminates, so the four narrowing shapes the
definition names are each asserted to be *not* a widening, against the same
comparison function that flags the widenings above them.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from src.analysis import effect_rules as er
from src.analysis import review_gate as rg
from src.analysis import rollback
from src.analysis.artifact_store import ArtifactStore
from src.contracts.repository import Repository

KIND = "egress_policy"
RULES_KIND = "effect_gate_rule_set"


def _policy(methods, paths, deny=(), at="2026-08-09T10:00:00Z") -> dict:
    return {
        "schema_version": "1.0.0",
        "deployment_id": "d-1",
        "allowed_methods": list(methods),
        "allowed_paths": list(paths),
        "deny_rules": [dict(rule) for rule in deny],
        "published_at": at,
    }


BASE = _policy(["GET"], ["/orders/7"])
GENERALIZED = _policy(["GET"], ["/orders/{id}"], at="2026-08-09T11:00:00Z")


@pytest.fixture()
def store(tmp_path):
    repo = Repository(
        tmp_path / "store.sqlite3", role="analysis",
        tenant_id="t-1", deployment_id="d-1")
    rollback.ensure_schema(repo)
    rg.ensure_schema(repo)
    yield ArtifactStore(tmp_path / "artifacts", repo)
    repo.close()


def _approved(store: ArtifactStore, document, *, at: float):
    proposal = rg.propose(store, KIND, document)
    rg.record_review(
        store.repo, proposal, reviewer="ops@example",
        decision=rg.DECISION_APPROVED, at=at)
    return proposal


def _seed(store: ArtifactStore) -> str:
    """One approved, applied version, so nothing below starts from empty."""
    proposal = _approved(store, BASE, at=90.0)
    stored, _ = rg.apply(
        store, proposal, produced_by="test@1.0.0", operator="ops@example",
        now=100.0)
    return stored.content_hash


# ---------------------------------------------------------------------------
# The gate. Positive and negative on one fixture.


def test_an_approved_version_takes_effect_and_an_unapproved_one_does_not(
        store) -> None:
    """FR-012's 'reviewable by the operator **before** it takes effect'.

    One document, two runs, one difference. Asserted in both directions
    because the negative alone holds whenever nothing takes effect, and it
    holds most easily when the gate does nothing at all.
    """
    first = _seed(store)

    unapproved = rg.propose(store, KIND, GENERALIZED)
    with pytest.raises(rg.ReviewRequired):
        rg.apply(store, unapproved, produced_by="test@1.0.0",
                 operator="ops@example", now=200.0)
    assert store.current_ref(KIND) == first, (
        "an unapproved version moved the reference, so review is advisory"
    )

    approved = _approved(store, GENERALIZED, at=210.0)
    assert approved.content_hash == unapproved.content_hash, (
        "the two arms proposed different bytes, so they are not one document "
        "with the review as the only difference"
    )
    stored, _ = rg.apply(store, approved, produced_by="test@1.0.0",
                         operator="ops@example", now=220.0)
    assert store.current_ref(KIND) == stored.content_hash != first, (
        "an approved version did not take effect either, so the negative arm "
        "above proves nothing about the review"
    )


def test_a_refused_apply_writes_nothing_at_all(store) -> None:
    """The refusal happens before the object is stored, not after."""
    first = _seed(store)
    changes_before = len(rg.changes(store.repo, KIND))

    proposal = rg.propose(store, KIND, GENERALIZED)
    with pytest.raises(rg.ReviewRequired):
        rg.apply(store, proposal, produced_by="test@1.0.0",
                 operator="ops@example", now=200.0)

    assert store.current_ref(KIND) == first
    assert len(rg.changes(store.repo, KIND)) == changes_before
    with pytest.raises(Exception):
        store.get_bytes(proposal.content_hash)


def test_proposing_stores_nothing_and_moves_nothing(store) -> None:
    """A proposal that published would make the review a formality after."""
    first = _seed(store)
    proposal = rg.propose(store, KIND, GENERALIZED)
    assert store.current_ref(KIND) == first
    assert proposal.content_hash != first


def test_an_approval_does_not_survive_an_edit_to_the_document(store) -> None:
    """The approval binds to the bytes, not to the kind.

    Without this, an operator approves one document and a different one takes
    effect under it, which is the review being performed on something nobody
    applied.
    """
    first = _seed(store)
    _approved(store, GENERALIZED, at=210.0)

    edited = {**GENERALIZED, "allowed_methods": ["GET", "DELETE"]}
    proposal = rg.propose(store, KIND, edited)
    with pytest.raises(rg.ReviewRequired):
        rg.apply(store, proposal, produced_by="test@1.0.0",
                 operator="ops@example", now=300.0)
    assert store.current_ref(KIND) == first


def test_a_rejection_recorded_after_an_approval_withdraws_it(store) -> None:
    first = _seed(store)
    proposal = _approved(store, GENERALIZED, at=210.0)
    rg.record_review(store.repo, proposal, reviewer="ops@example",
                     decision=rg.DECISION_REJECTED, at=215.0)

    with pytest.raises(rg.ReviewRequired):
        rg.apply(store, proposal, produced_by="test@1.0.0",
                 operator="ops@example", now=220.0)
    assert store.current_ref(KIND) == first


def test_a_change_records_fr_019s_three_fields(store) -> None:
    first = _seed(store)
    proposal = _approved(store, GENERALIZED, at=210.0)
    stored, change = rg.apply(store, proposal, produced_by="test@1.0.0",
                              operator="ops@example", now=220.0)

    assert change.operator == "ops@example"
    assert change.changed_from == first
    assert change.changed_to == stored.content_hash
    assert change.widening is True
    assert change.witnesses, "a widening was recorded with no witness"

    rows = rg.changes(store.repo, KIND)
    assert rows[-1]["widening"] == 1
    assert rows[-1]["reviewer"] == "ops@example"


def test_a_change_is_recorded_even_where_it_is_not_a_widening(store) -> None:
    """FR-019 requires widenings recorded; recording only widenings would make
    the flag unreadable, because an absent row and a narrowing look the same.
    """
    _seed(store)
    widened = _approved(store, GENERALIZED, at=210.0)
    rg.apply(store, widened, produced_by="t", operator="ops@example", now=220.0)

    narrowed = _approved(store, _policy(["GET"], ["/orders/7"],
                                        at="2026-08-09T12:00:00Z"), at=230.0)
    _, change = rg.apply(store, narrowed, produced_by="t",
                         operator="ops@example", now=240.0)
    assert change.widening is False
    assert change.assessed_verdict == rg.NARROWING
    assert len(rg.changes(store.repo, KIND)) == 3


def test_an_unattributed_change_is_refused(store) -> None:
    _seed(store)
    proposal = _approved(store, GENERALIZED, at=210.0)
    with pytest.raises(rg.ReviewGateError, match="names the operator"):
        rg.apply(store, proposal, produced_by="t", operator="  ", now=220.0)


def test_an_anonymous_approval_is_refused(store) -> None:
    _seed(store)
    proposal = rg.propose(store, KIND, GENERALIZED)
    with pytest.raises(rg.ReviewGateError, match="names the reviewer"):
        rg.record_review(store.repo, proposal, reviewer=" ",
                         decision=rg.DECISION_APPROVED, at=210.0)


def test_a_kind_with_no_operator_surface_is_not_silently_gated(store) -> None:
    with pytest.raises(rg.ReviewNotApplicable):
        rg.propose(store, "bounds", {"schema_version": "1.0.0"})
    assert rg.GATED_KINDS == {"effect_gate_rule_set", "egress_policy"}


# ---------------------------------------------------------------------------
# The predicate. Widenings, then the narrowing control.


def _surface(permitted, denied=()) -> rg.Surface:
    return rg.Surface(
        permitted=tuple(er.Matcher(method=m, path_template=p) for m, p in permitted),
        denied=tuple(er.Matcher(method=m, path_template=p) for m, p in denied),
    )


def test_a_permission_added_is_a_widening() -> None:
    before = _surface([("GET", "/orders")])
    after = _surface([("GET", "/orders"), ("GET", "/invoices")])
    assert rg.assess(before, after).verdict == rg.WIDENING


def test_a_permission_generalized_is_a_widening() -> None:
    """W1's non-obvious half: no matcher was added, one grew."""
    before = _surface([("GET", "/orders/7")])
    after = _surface([("GET", "/orders/{id}")])
    assessment = rg.assess(before, after)
    assert assessment.verdict == rg.WIDENING
    assert assessment.permissions_added == (
        er.Matcher(method="GET", path_template="/orders/{id}"),)


def test_a_denial_removed_is_a_widening() -> None:
    before = _surface([("GET", "/mail/{id}")], [("GET", "/mail/7")])
    after = _surface([("GET", "/mail/{id}")])
    assessment = rg.assess(before, after)
    assert assessment.verdict == rg.WIDENING
    assert assessment.denials_lifted


def test_a_denial_specialized_is_a_widening() -> None:
    """W2's non-obvious half: the deny entry survives and covers less."""
    before = _surface([("GET", "/mail/{id}")], [("GET", "/mail/{id}")])
    after = _surface([("GET", "/mail/{id}")], [("GET", "/mail/7")])
    assert rg.assess(before, after).verdict == rg.WIDENING


def test_a_permission_withdrawn_is_a_narrowing_and_is_not_flagged() -> None:
    """The control. A predicate that answered `widening` unconditionally would
    pass every arm above and fail this one.
    """
    before = _surface([("GET", "/orders"), ("GET", "/invoices")])
    after = _surface([("GET", "/orders")])
    assessment = rg.assess(before, after)
    assert assessment.verdict == rg.NARROWING
    assert assessment.widening is False


def test_a_permission_specialized_is_a_narrowing_and_is_not_flagged() -> None:
    """The mirror of `test_a_permission_generalized_is_a_widening`.

    Same two surfaces, swapped. If coverage were symmetric both would be
    widenings and the predicate would be a constant with extra steps.
    """
    before = _surface([("GET", "/orders/{id}")])
    after = _surface([("GET", "/orders/7")])
    assert rg.assess(before, after).verdict == rg.NARROWING


def test_a_denial_added_is_a_narrowing_and_is_not_flagged() -> None:
    before = _surface([("GET", "/mail/{id}")])
    after = _surface([("GET", "/mail/{id}")], [("GET", "/mail/7")])
    assert rg.assess(before, after).verdict == rg.NARROWING


def test_a_denial_generalized_is_a_narrowing_and_is_not_flagged() -> None:
    before = _surface([("GET", "/mail/{id}")], [("GET", "/mail/7")])
    after = _surface([("GET", "/mail/{id}")], [("GET", "/mail/{id}")])
    assert rg.assess(before, after).verdict == rg.NARROWING


def test_an_unchanged_configuration_is_neither() -> None:
    same = _surface([("GET", "/orders/{id}")], [("GET", "/mail/7")])
    assert rg.assess(same, same).verdict == rg.UNCHANGED


def test_a_first_publication_onto_an_empty_surface_is_a_widening() -> None:
    assert rg.assess(_surface([]), _surface([("GET", "/orders")])).verdict == (
        rg.WIDENING)


def test_adding_a_method_widens_every_path_and_names_each_one(store) -> None:
    """FR-019's two axes: a method added widens the product, not one entry."""
    before = rg.surface_of(KIND, _policy(["GET"], ["/a", "/b"]))
    after = rg.surface_of(KIND, _policy(["GET", "DELETE"], ["/a", "/b"]))
    assessment = rg.assess(before, after)
    assert assessment.verdict == rg.WIDENING
    assert {m.path_template for m in assessment.permissions_added} == {"/a", "/b"}
    assert {m.method for m in assessment.permissions_added} == {"DELETE"}


def test_the_effect_rule_set_reads_through_the_same_predicate(store) -> None:
    """One surface representation for both gated kinds, asserted on the other
    one — otherwise `surface_of` is only ever exercised on the egress policy.
    """
    def rules(path: str) -> dict:
        rule = er.ServedOperationRule(
            rule_id="EFF-OP-001", operation_id="getOrder",
            matcher=er.Matcher(method="GET", path_template=path),
            safe=True, justification="declared safe by the specification")
        return er.rule_set_from("d-1", [rule], []).document(
            published_at="2026-08-09T10:00:00Z")

    before = rg.surface_of(RULES_KIND, rules("/orders/7"))
    after = rg.surface_of(RULES_KIND, rules("/orders/{id}"))
    assert rg.assess(before, after).verdict == rg.WIDENING
    assert rg.assess(after, before).verdict == rg.NARROWING


# ---------------------------------------------------------------------------
# Restoration. FR-054.


def _seed_two(store: ArtifactStore) -> tuple[str, str]:
    first = _seed(store)
    proposal = _approved(store, GENERALIZED, at=210.0)
    stored, _ = rg.apply(store, proposal, produced_by="t",
                         operator="ops@example", now=220.0)
    return first, stored.content_hash


def test_a_restoration_without_a_review_does_not_move_the_reference(store) -> None:
    """FR-054: a restoration is 'subject to the same review as FR-012'.

    The restore target here is a version that *was* approved — `_seed`
    approved it before publishing it — so this also asserts that a publication
    approval does not authorise the rollback back to it. The two are decisions
    about opposite directions of travel, taken against different comparands.
    """
    _, second = _seed_two(store)
    proposal = rg.propose_restore(store, KIND)
    with pytest.raises(rg.ReviewRequired):
        rg.restore(store, proposal, operator="ops@example", now=300.0)
    assert store.current_ref(KIND) == second
    assert rollback.restorations(store.repo, KIND) == []


def test_a_reviewed_restoration_moves_the_reference_back(store) -> None:
    first, second = _seed_two(store)
    proposal = rg.propose_restore(store, KIND)
    assert proposal.content_hash == first
    rg.record_review(store.repo, proposal, reviewer="ops@example",
                     decision=rg.DECISION_APPROVED, at=310.0)

    restoration, change = rg.restore(store, proposal, operator="ops@example",
                                     now=320.0)
    assert store.current_ref(KIND) == first
    assert restoration.restored_from == second
    assert restoration.restored_to == first
    assert change.change_kind == rg.CHANGE_RESTORATION


def test_a_restoration_is_recorded_as_a_widening_even_where_it_narrows(
        store) -> None:
    """FR-054's exact words: 'recorded **exactly as a widening is** under
    FR-019'.

    The restoration here moves from `/orders/{id}` back to `/orders/7`, which
    the predicate reads as a narrowing — and the record still says widening,
    with the predicate's own answer kept beside it so neither is lost. An
    implementation that ran the predicate instead would record `widening=0`
    here and would be wrong about the requirement rather than about the
    configuration.
    """
    _seed_two(store)
    proposal = rg.propose_restore(store, KIND)
    assert proposal.assessment.verdict == rg.NARROWING
    rg.record_review(store.repo, proposal, reviewer="ops@example",
                     decision=rg.DECISION_APPROVED, at=310.0)

    _, change = rg.restore(store, proposal, operator="ops@example", now=320.0)
    assert change.widening is True
    assert change.assessed_verdict == rg.NARROWING

    row = rg.changes(store.repo, KIND)[-1]
    assert row["widening"] == 1 and row["assessed_verdict"] == rg.NARROWING


def test_a_restoration_writes_both_records(store) -> None:
    """`restoration_record` says a rollback happened; `configuration_change`
    says the configuration widened. Two questions, two rows.
    """
    _seed_two(store)
    proposal = rg.propose_restore(store, KIND)
    rg.record_review(store.repo, proposal, reviewer="ops@example",
                     decision=rg.DECISION_APPROVED, at=310.0)
    rg.restore(store, proposal, operator="ops@example", now=320.0)

    assert len(rollback.restorations(store.repo, KIND)) == 1
    assert rg.changes(store.repo, KIND)[-1]["change_kind"] == rg.CHANGE_RESTORATION


def test_there_is_nothing_to_review_where_there_is_no_prior_version(store) -> None:
    _seed(store)
    with pytest.raises(rg.ReviewGateError, match="no immediately prior"):
        rg.propose_restore(store, KIND)


# ---------------------------------------------------------------------------
# Containment. The gate is only a gate if it is the only door.


def _gated_publish_calls(tree: Path) -> list[str]:
    """Every call in `tree` that moves a gated kind's reference directly.

    A structural scan rather than a convention, for the reason
    `test_writer_ownership.py` gives about its SQL scan: a convention has no
    failure mode until somebody needs to publish one in a hurry. Scoped to
    `src/` — a test fixture publishing an egress policy through the store is
    exercising the store, which is what `tests/contract/test_rollback.py` does.
    """
    offenders: list[str] = []
    for source in sorted(tree.rglob("*.py")):
        if source.name in {"review_gate.py", "rollback.py", "artifact_store.py"}:
            continue
        parsed = ast.parse(source.read_text())
        for node in ast.walk(parsed):
            if not isinstance(node, ast.Call):
                continue
            function = node.func
            if not isinstance(function, ast.Attribute):
                continue
            if function.attr in {"publish", "set_ref"} and node.args:
                first = node.args[0]
                if isinstance(first, ast.Constant) and first.value in rg.GATED_KINDS:
                    offenders.append(
                        f"{source.name}:{node.lineno}: "
                        f"{function.attr}({first.value!r})")
            if function.attr == "restore_previous":
                offenders.append(f"{source.name}:{node.lineno}: restore_previous")
    return offenders


def test_no_module_publishes_a_gated_kind_around_the_gate() -> None:
    root = Path(__file__).resolve().parents[2] / "src"
    offenders = _gated_publish_calls(root)
    assert not offenders, (
        "a gated kind's reference is moved without a review:\n  "
        + "\n  ".join(offenders)
        + "\nRoute it through src/analysis/review_gate.py. FR-012 puts the "
        "review before the version takes effect, and a second door makes the "
        "gate advisory."
    )


def test_the_containment_scan_would_actually_catch_something(tmp_path) -> None:
    """The control. A scan with a broken matcher passes silently."""
    planted = tmp_path / "planted.py"
    planted.write_text(
        'store.publish("egress_policy", document, produced_by="x")\n'
        'rollback.restore_previous(store, "bounds", operator="o", now=1.0)\n')
    found = _gated_publish_calls(tmp_path)
    assert len(found) == 2, f"the containment scan matched {found}"

    ignored = tmp_path / "clean.py"
    ignored.write_text('store.publish("bounds", document)\n')
    ignored_hits = [f for f in _gated_publish_calls(tmp_path)
                    if f.startswith("clean.py")]
    assert not ignored_hits, "the scan flags an ungated kind"
