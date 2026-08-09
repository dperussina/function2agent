"""T081 — FR-010's rule set and deny list as versioned configuration.

Every arm here is written to fail for one reason. Where two guards could
satisfy one assertion, there are two tests, because a proof arm that removed
either would otherwise be scored against whichever the message happened to
name.
"""

from __future__ import annotations

import pytest

from src.analysis import effect_rules as er
from src.contracts import envelope
from src.contracts.schemas import EFFECT_GATE_RULE_SET

PUBLISHED_AT = "2026-08-09T12:00:00Z"


def _rule(rule_id="EFF-OP-001", method="GET", path="/orders/{id}", safe=True,
          operation_id="getOrder", justification="declared safe by the target's "
          "published specification") -> er.ServedOperationRule:
    return er.ServedOperationRule(
        rule_id=rule_id,
        operation_id=operation_id,
        matcher=er.Matcher(method=method, path_template=path),
        safe=safe,
        justification=justification,
    )


def _deny(rule_id="EFF-DENY-001", method="GET", path="/orders/{id}/resend",
          tier=er.TIER_IRREVERSIBLE, declared_by="ops@example",
          justification="this GET re-sends the confirmation email"
          ) -> er.DenyListEntry:
    return er.DenyListEntry(
        rule_id=rule_id,
        matcher=er.Matcher(method=method, path_template=path),
        tier=tier,
        declared_by=declared_by,
        justification=justification,
    )


# ---------------------------------------------------------------------------
# FR-010's sentence, in both directions.


def test_a_safe_method_of_a_served_operation_resolves_read_only() -> None:
    """The positive half. Without it every arm below passes on a rule set that
    resolves nothing, which is the vacuous pass this file's siblings warn about.
    """
    assert _rule(method="GET", safe=True).tier == er.TIER_READ_ONLY
    assert _rule(method="HEAD", safe=True).tier == er.TIER_READ_ONLY


def test_an_operation_the_target_does_not_declare_safe_is_not_read_only() -> None:
    assert _rule(method="POST", safe=False).tier != er.TIER_READ_ONLY
    assert _rule(method="GET", safe=False).tier != er.TIER_READ_ONLY, (
        "a GET the target does not declare safe resolved read-only. FR-010 "
        "requires the method to be a safe method **of a served operation**, "
        "and the operation's own declaration is the second half of that."
    )


def test_a_rule_cannot_declare_an_unsafe_method_safe() -> None:
    """The single worst misconfiguration this artifact can carry.

    A `POST` entry with `safe=True` resolves a write to `read_only`, and the
    enforcement point reads the tier this artifact carries — so nothing
    downstream could catch it. Constitution Principle IV's
    *zero destructive-classified-as-read* is this assertion.
    """
    with pytest.raises(er.EffectRuleError, match="declared safe"):
        _rule(method="POST", safe=True)
    with pytest.raises(er.EffectRuleError, match="declared safe"):
        _rule(method="DELETE", safe=True)


def test_the_tier_is_not_a_settable_field() -> None:
    """It is computed from `safe`, so there is no second place to disagree."""
    rule = _rule()
    with pytest.raises(AttributeError):
        rule.tier = er.TIER_READ_ONLY  # type: ignore[misc]


def test_a_deny_entry_cannot_declare_a_permitted_tier() -> None:
    """A deny-list entry at `read_only` denies nothing.

    FR-010's deny list is of *known side-effecting reads*: the content of an
    entry is that this read is not one. An entry admitted at a permitted tier
    turns the list into an allowlist that the enforcement point reads as a
    deny list.
    """
    with pytest.raises(er.EffectRuleError, match="denies nothing"):
        _deny(tier=er.TIER_READ_ONLY)


def test_a_deny_entry_may_declare_either_write_tier() -> None:
    """The control for the arm above: the refusal is about `read_only`, not
    about the tier being declared at all."""
    assert _deny(tier=er.TIER_REVERSIBLE_WRITE).tier == er.TIER_REVERSIBLE_WRITE
    assert _deny(tier=er.TIER_IRREVERSIBLE).tier == er.TIER_IRREVERSIBLE


def test_an_unknown_tier_is_refused() -> None:
    with pytest.raises(er.EffectRuleError, match="not one of the declared"):
        _deny(tier="probably_fine")


# ---------------------------------------------------------------------------
# Rule identifiers.


def test_every_entry_carries_a_rule_identifier_in_its_own_namespace() -> None:
    with pytest.raises(er.EffectRuleError, match="served-operation rule"):
        _rule(rule_id="EG-EFFECT-002")
    with pytest.raises(er.EffectRuleError, match="deny-list namespace"):
        _deny(rule_id="DEP-001")


def test_the_namespace_does_not_collide_with_the_enforcement_points() -> None:
    """`src/proxy/policy.go` refuses a deny entry whose identifier collides
    with a pipeline rule, and those are all `EG-`. An artifact produced here
    with an `EG-` identifier would be refused at the proxy's startup rather
    than at authoring time, which is the wrong end of the pipeline.
    """
    assert not er.NAMESPACE.startswith("EG-")
    assert er.SERVED_RULE_PREFIX.startswith(er.NAMESPACE)
    assert er.DENY_RULE_PREFIX.startswith(er.NAMESPACE)
    assert er.SERVED_RULE_PREFIX != er.DENY_RULE_PREFIX


def test_one_identifier_may_not_answer_to_two_entries() -> None:
    """FR-011 requires a decision to name the rule that produced it.

    The two lists share one identifier space on purpose — a decision record
    carries a rule identifier and does not say which list it came from — so
    the collision that matters is across them, and that is what is asserted.
    """
    with pytest.raises(er.EffectRuleError, match="declared twice"):
        er.rule_set_from(
            "d-1",
            [_rule(rule_id="EFF-OP-001"), _rule(rule_id="EFF-OP-001",
                                                operation_id="other")],
            [],
        )


# ---------------------------------------------------------------------------
# Reviewability. FR-012's word, made into a constructor precondition.


def test_an_entry_with_no_justification_is_not_constructible() -> None:
    with pytest.raises(er.EffectRuleError, match="reviewable"):
        _rule(justification="   ")
    with pytest.raises(er.EffectRuleError, match="reviewable justification"):
        _deny(justification="")


def test_a_deny_entry_names_who_declared_it() -> None:
    """Nothing derives a deny entry, so 'who says so' is all of its provenance."""
    with pytest.raises(er.EffectRuleError, match="accountable party"):
        _deny(declared_by="  ")


def test_the_two_entry_types_carry_distinct_provenances() -> None:
    """OD-27's discipline: a derived entry and a declared one are two types.

    The provenances differ so that a reader of a stored document can tell a
    rule the target's specification produced from one a human asserted.
    """
    assert _rule().provenance == er.PROVENANCE_SERVED_SET
    assert _deny().provenance == er.PROVENANCE_OPERATOR
    assert _rule().provenance != _deny().provenance
    assert er.PROVENANCES == {er.PROVENANCE_SERVED_SET, er.PROVENANCE_OPERATOR}


# ---------------------------------------------------------------------------
# Matchers.


def test_a_matcher_rejects_a_template_that_could_never_fire() -> None:
    with pytest.raises(er.EffectRuleError, match="begin with"):
        er.Matcher(method="GET", path_template="orders")
    with pytest.raises(er.EffectRuleError, match="malformed parameter"):
        er.Matcher(method="GET", path_template="/orders/{id")
    with pytest.raises(er.EffectRuleError, match="unnamed parameter"):
        er.Matcher(method="GET", path_template="/orders/{}")
    with pytest.raises(er.EffectRuleError, match="HTTP method token"):
        er.Matcher(method="get", path_template="/orders")


def test_coverage_relates_a_template_to_what_it_generalizes() -> None:
    general = er.Matcher(method="GET", path_template="/orders/{id}")
    specific = er.Matcher(method="GET", path_template="/orders/7")

    assert general.subsumes(specific)
    assert not specific.subsumes(general), (
        "coverage is symmetric, so a generalization and a specialization are "
        "indistinguishable and the widening predicate built on it cannot tell "
        "them apart"
    )
    assert general.subsumes(general)


def test_coverage_does_not_cross_a_method_or_a_segment_count() -> None:
    assert not er.Matcher(method="GET", path_template="/orders/{id}").subsumes(
        er.Matcher(method="POST", path_template="/orders/7"))
    assert not er.Matcher(method="GET", path_template="/orders/{id}").subsumes(
        er.Matcher(method="GET", path_template="/orders/7/items"))


# ---------------------------------------------------------------------------
# The artifact.


def _document() -> dict:
    return er.rule_set_from("d-1", [_rule()], [_deny()]).document(
        published_at=PUBLISHED_AT)


def test_the_set_is_one_of_the_eight_kinds_and_wraps() -> None:
    wrapped = envelope.wrap(EFFECT_GATE_RULE_SET.kind, _document())
    assert wrapped.kind == "effect_gate_rule_set"
    assert wrapped.address.startswith("sha256:")
    assert "published_at" in wrapped.context, (
        "the publication instant was hashed, so two publications of an "
        "unchanged rule set land on two content addresses"
    )
    assert "rules" in wrapped.payload and "deny_list" in wrapped.payload


def test_two_publications_of_an_unchanged_set_land_on_one_address() -> None:
    first = envelope.wrap(EFFECT_GATE_RULE_SET.kind, _document())
    later = er.rule_set_from("d-1", [_rule()], [_deny()]).document(
        published_at="2026-09-01T09:30:00Z")
    assert envelope.wrap(EFFECT_GATE_RULE_SET.kind, later).address == first.address


def test_a_changed_entry_moves_the_address() -> None:
    changed = er.rule_set_from(
        "d-1", [_rule(), _rule(rule_id="EFF-OP-002", operation_id="listOrders",
                               path="/orders")], [_deny()],
    ).document(published_at=PUBLISHED_AT)
    assert (envelope.wrap(EFFECT_GATE_RULE_SET.kind, changed).address
            != envelope.wrap(EFFECT_GATE_RULE_SET.kind, _document()).address)


def test_the_document_says_it_is_a_stated_rule_set_and_not_a_proof() -> None:
    """FR-010's last sentence binds *interfaces*, not only prose.

    A stored artifact is read by a consumer, so it is one. The basis also
    names U-43 — the gate's precision is unmeasured against anything — and
    carries no precision figure, because FR-041 forbids inheriting the
    superseded per-tool threshold by default.
    """
    basis = _document()["basis"]
    assert "not a proof" in basis
    assert "U-43" in basis
    assert "0.98" not in basis


def test_the_permitted_surface_holds_only_permitted_tiers() -> None:
    rule_set = er.rule_set_from(
        "d-1",
        [_rule(), _rule(rule_id="EFF-OP-002", operation_id="createOrder",
                        method="POST", path="/orders", safe=False)],
        [_deny()],
    )
    assert rule_set.permitted == (
        er.Matcher(method="GET", path_template="/orders/{id}"),)
    assert rule_set.denied == (
        er.Matcher(method="GET", path_template="/orders/{id}/resend"),)


def test_a_stored_document_reads_back_to_the_same_surface() -> None:
    """The reader T082 uses on bytes must agree with the writer here."""
    rule_set = er.rule_set_from("d-1", [_rule()], [_deny()])
    permitted, denied = er.surfaces_of(rule_set.document(published_at=PUBLISHED_AT))
    assert permitted == rule_set.permitted
    assert denied == rule_set.denied


def test_a_set_with_no_deployment_is_refused() -> None:
    with pytest.raises(er.EffectRuleError, match="names the deployment"):
        er.rule_set_from("", [_rule()], [])


def test_the_entry_field_names_are_the_ones_the_enforcement_point_reads() -> None:
    """`src/proxy/policy.go` decodes `rule_id`, `method`, `path_template`,
    `safe` and `operation_id` on a served operation, and `rule_id`, `method`,
    `path_template` and `justification` on a deny entry. The outer shape of the
    policy file differs from this artifact and is not produced here; the entry
    field names are shared, so a rename on this side is a silently empty field
    on that one.
    """
    rule = _rule().document()
    assert {"rule_id", "method", "path_template", "operation_id", "safe"} <= set(rule)
    entry = _deny().document()
    assert {"rule_id", "method", "path_template", "justification"} <= set(entry)
