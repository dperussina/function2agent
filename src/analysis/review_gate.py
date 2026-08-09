"""T082 — the operator review an effect rule set, its deny list and an egress
policy must pass before they take effect (FR-012, FR-019, FR-054).

FR-012's second clause, on the deny list and the safe-method rule set:

    **reviewable by the operator before it takes effect**

FR-019, on the enforcement point's allowlist:

    Any widening of the destination or method allowlist MUST be an explicit
    operator action, recorded as configuration and subject to the same review
    as FR-012.

FR-054, on every one of the eight kinds:

    A restoration MUST be recorded exactly as a widening is under FR-019 — the
    operator, the version restored from, the version restored to — and MUST be
    subject to the same review as FR-012.

## Reviewable is a mechanism here, not an adjective

*"Reviewable before it takes effect"* is satisfiable by a document a human
could read, which is a property nothing can fail. This module reads it as the
stronger thing the sentence is for: **a version that has not been approved
cannot become the version in force**, and the only difference between the two
outcomes is the approval.

So the path is three steps and they are three calls:

1. `propose(...)` wraps the candidate, computes its content address, and
   assesses it against the version currently in force. Nothing is stored and
   no reference moves. **The proposal is what the operator reads** — it names
   the address, whether the change is a widening, and each widening witness.
2. `record_review(...)` writes an approval or a rejection **against that
   address and that direction of travel**. Against the address rather than
   against the kind, because an approval that outlived the bytes it was given
   would let an approved review admit a document nobody read: change one
   character and the address moves, and the approval no longer matches
   anything. Against the direction as well, because the same bytes going up
   and coming back down are two decisions — the approval that let a version
   take effect must not silently authorise a rollback to it later, and it did
   until the restoration test's positive arm was written beside its negative
   one.
3. `apply(...)` refuses unless an approval for that exact address exists, and
   otherwise publishes and records the change.

`propose` and `apply` wrap the same document with the same function, so the
address the operator approved is the address that is checked. Two code paths
computing "the address" would be a place for them to disagree, and the
disagreement would show up as an approval that mysteriously does not apply.

## What a widening is

Stated here so a test can disagree with it. A configuration is read as two sets
of matchers — the calls it **permits** and the calls it **denies** — and a call
is permitted when some permitted matcher covers it and no denied matcher does.
`m` **covers** `n` when their methods are equal and every segment of `m`'s path
template is either a parameter or literally `n`'s; so `/orders/{id}` covers
`/orders/7` and the reverse does not hold.

**A change from A to B is a widening exactly when B permits something A did
not.** Since the two sets are finite and the calls are not, that is decided on
the declared matchers as witnesses, in two clauses:

- **W1, a permission added or generalized** — some matcher in `B.permitted` is
  covered by nothing in `A.permitted`.
- **W2, a denial removed or specialized** — some matcher in `A.denied` is
  covered by nothing in `B.denied`. Removing a deny entry permits what it
  denied, and narrowing `/mail/{id}` to `/mail/7` permits every other `id`, so
  both land here and both are widenings.

**Four changes are narrowings and none of them fires either clause**, which is
what makes the predicate a predicate rather than a label:

- removing a permitted matcher — W1 quantifies over `B.permitted`, and a
  matcher that is gone is not in it;
- specializing a permitted matcher, `/orders/{id}` → `/orders/7` — `/orders/7`
  is covered by `/orders/{id}`, which is still what `A.permitted` holds;
- adding a deny entry — W2 quantifies over `A.denied`;
- generalizing a deny entry, `/mail/7` → `/mail/{id}` — `/mail/7` is covered
  by `/mail/{id}`.

A change that is neither is `unchanged`, and republishing identical content is
the degenerate case of it.

**The predicate errs towards reporting a widening and never away from one.**
Coverage is sound and incomplete: it relates a template to what it generalizes
and answers `False` for a pair it cannot relate — two different parameter
namings of the same path, for instance. A `False` there produces a witness and
therefore a widening on a change that may not be one, which costs the operator
a review. The opposite error, a widening reported as `unchanged`, is the one
that matters, and it is not reachable by answering `False` too often.

## Restoration is a widening by requirement rather than by predicate

FR-054 says a restoration is *"recorded exactly as a widening is under
FR-019"*. So `restore(...)` records the change with `widening=True`
unconditionally and does not run the predicate. **This is deliberate and is not
the predicate being bypassed.** A restoration can perfectly well move to a
*narrower* configuration, and the predicate would say so; the requirement
records it as a widening anyway, because the property being recorded is not
"more is permitted" but "an operator changed what is in force outside the
ordinary path". The predicate's answer is kept as `assessed_widening` on the
record, so the two are distinguishable to anyone reading it and neither is
lost.

## Which objects this gate covers, and which cite FR-012 and are not here

`GATED_KINDS` is the two artifact kinds T082 names — `effect_gate_rule_set`,
which holds both the rule set and the deny list FR-012 names, and
`egress_policy`, which holds FR-019's allowlist. Three further objects in this
tree say they are reviewable under FR-012 and are **not** gated here, recorded
rather than quietly absorbed:

- **FR-054's restoration clause covers all eight kinds**, not the two.
  `restore` accepts any kind and gates the two; a restoration of the other six
  through `src/analysis/rollback.py` is still unreviewed. Extending is
  `GATED_KINDS`, but it is a scope change to T082 rather than a line, because
  five of those six have no operator surface that produces a review at all.
- **FR-056's confused-deputy catalogue** (`src/analysis/deputy_inspection.py`,
  `CATALOGUE_VERSION`, `DEP-` identifiers) is *"versioned configuration under
  FR-012 and reviewable before it takes effect"*, and it is not one of
  FR-054's eight artifact kinds. This gate keys on artifact kind, so gating the
  catalogue means first making it an artifact — a schema, a ninth kind or a
  home inside an existing one — and FR-054 asserts eight.
- **FR-024's precision ladder** is *"versioned configuration under FR-012"* by
  its own property 1, and has the same problem for the same reason (T125).

## Double coverage, and why the removal proof can tell the gate apart

A gate whose case something else already refuses cannot be shown to do
anything. Everything that could refuse an unreviewed `apply` before the review
check does was checked and none of it can:

- **Schema validation** (`envelope.wrap`) — `propose` already wrapped the same
  document successfully, so a document that reaches `apply` at all is valid.
  Both arms of the test use one document.
- **The object store's absent-object refusal** (`ArtifactStore.set_ref`) —
  reachable only after `put`, and the review check runs before `put`.
- **`rollback.restore_previous`'s two refusals** — no current version, and only
  one version ever held. Both arms of the restoration test publish twice, so
  neither is reachable.
- **The Go enforcement point's policy validation** (`src/proxy/policy.go`) —
  another process, and it reads a policy file rather than this artifact.

What remains is that the reviewed arm succeeds and the unreviewed arm does not,
on one fixture with the review as the only difference. That is asserted in both
directions in `tests/contract/test_review_gate.py`, because the negative alone
passes just as well when nothing takes effect for some other reason.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from src.analysis import effect_rules, rollback
from src.analysis.artifact_store import ArtifactStore, StoredArtifact
from src.contracts.envelope import wrap
from src.contracts.repository import Repository
from src.contracts.schemas import EFFECT_GATE_RULE_SET, EGRESS_POLICY, require

REVIEW_TABLE = "configuration_review"
CHANGE_TABLE = "configuration_change"

#: The kinds that may not take effect without an approval. T082's three named
#: objects live in two of FR-054's eight kinds — the deny list is inside the
#: effect-gate rule set, because FR-054 joins them with "and its".
GATED_KINDS: frozenset[str] = frozenset({EFFECT_GATE_RULE_SET.kind, EGRESS_POLICY.kind})

DECISION_APPROVED = "approved"
DECISION_REJECTED = "rejected"
DECISIONS = frozenset({DECISION_APPROVED, DECISION_REJECTED})

CHANGE_PUBLICATION = "publication"
CHANGE_RESTORATION = "restoration"

#: The three answers the widening predicate gives.
WIDENING = "widening"
NARROWING = "narrowing"
UNCHANGED = "unchanged"


class ReviewGateError(RuntimeError):
    """The base for everything this module refuses."""


class ReviewRequired(ReviewGateError):
    """A version was about to take effect with no approval behind it."""


class ReviewNotApplicable(ReviewGateError):
    """A review was recorded for a kind this gate does not cover."""


# ---------------------------------------------------------------------------
# Reading a configuration as two sets of matchers.


@dataclass(frozen=True)
class Surface:
    """What a configuration permits and what it denies, as matchers.

    One representation for both gated kinds, so the widening predicate is one
    function rather than one per kind. Two predicates would be two places for
    the definition above to be true.
    """

    permitted: tuple[effect_rules.Matcher, ...]
    denied: tuple[effect_rules.Matcher, ...]


def surface_of(kind: str, document: Mapping[str, Any]) -> Surface:
    """The two matcher sets for a stored or candidate document of `kind`."""
    if kind == EFFECT_GATE_RULE_SET.kind:
        permitted, denied = effect_rules.surfaces_of(document)
        return Surface(permitted=permitted, denied=denied)
    if kind == EGRESS_POLICY.kind:
        return _egress_surface(document)
    raise ReviewNotApplicable(
        f"{kind!r} has no declared permitted surface, so a change to it "
        f"cannot be assessed for widening. Gated kinds are {sorted(GATED_KINDS)}."
    )


def _egress_surface(document: Mapping[str, Any]) -> Surface:
    """FR-019's two axes, crossed into matchers.

    The policy declares methods and paths on separate lists, so the calls it
    permits are their product — which is also why adding one method widens by
    as many matchers as there are paths, and the operator sees every one of
    them as a witness rather than a count.
    """
    methods = [str(m) for m in document.get("allowed_methods", ())]
    paths = [str(p) for p in document.get("allowed_paths", ())]
    permitted = tuple(
        effect_rules.Matcher(method=method, path_template=path)
        for method in methods
        for path in paths
    )
    denied: list[effect_rules.Matcher] = []
    for rule in document.get("deny_rules", ()):
        path = str(rule["path"])
        rule_method = rule.get("method")
        # A deny rule with no method denies that path on every method the
        # policy allows. Expanded here rather than represented as a wildcard,
        # because a wildcard would need its own coverage rule and a second
        # coverage rule is a second definition of the thing this module exists
        # to define once.
        for method in ([str(rule_method)] if rule_method else methods):
            denied.append(effect_rules.Matcher(method=method, path_template=path))
    return Surface(permitted=permitted, denied=tuple(denied))


# ---------------------------------------------------------------------------
# The predicate.


@dataclass(frozen=True)
class Assessment:
    """The predicate's answer, and every witness that produced it."""

    verdict: str
    #: Matchers `after` permits that nothing in `before` covered. Clause W1.
    permissions_added: tuple[effect_rules.Matcher, ...] = ()
    #: Matchers `before` denied that nothing in `after` covers. Clause W2.
    denials_lifted: tuple[effect_rules.Matcher, ...] = ()
    #: Matchers `before` permitted that nothing in `after` covers, and matchers
    #: `after` denies that nothing in `before` covered. Recorded because an
    #: operator reviewing a change wants to see what it took away as well, and
    #: because a change with neither these nor the two above is `unchanged`.
    permissions_withdrawn: tuple[effect_rules.Matcher, ...] = ()
    denials_added: tuple[effect_rules.Matcher, ...] = ()

    @property
    def widening(self) -> bool:
        return self.verdict == WIDENING

    def witnesses(self) -> tuple[str, ...]:
        """Every widening witness as text, for the record and the operator."""
        return tuple(
            f"W1 permits {m.method} {m.path_template}, which nothing in the "
            "version in force covered"
            for m in self.permissions_added
        ) + tuple(
            f"W2 no longer denies {m.method} {m.path_template}, which the "
            "version in force denied"
            for m in self.denials_lifted
        )


def _uncovered(
    subjects: Sequence[effect_rules.Matcher],
    covers: Sequence[effect_rules.Matcher],
) -> tuple[effect_rules.Matcher, ...]:
    return tuple(m for m in subjects if not effect_rules.subsumed_by_any(m, covers))


def assess(before: Surface, after: Surface) -> Assessment:
    """Apply the definition in this module's docstring to two surfaces."""
    added = _uncovered(after.permitted, before.permitted)
    lifted = _uncovered(before.denied, after.denied)
    withdrawn = _uncovered(before.permitted, after.permitted)
    newly_denied = _uncovered(after.denied, before.denied)

    if added or lifted:
        verdict = WIDENING
    elif withdrawn or newly_denied:
        verdict = NARROWING
    else:
        verdict = UNCHANGED

    return Assessment(
        verdict=verdict,
        permissions_added=added,
        denials_lifted=lifted,
        permissions_withdrawn=withdrawn,
        denials_added=newly_denied,
    )


# ---------------------------------------------------------------------------
# Storage.


def ensure_schema(repository: Repository) -> None:
    repository.create_table(REVIEW_TABLE, {
        "artifact_kind": "text not null",
        "content_hash": "text not null",
        "change_kind": "text not null",
        "reviewer": "text not null",
        "decision": "text not null",
        "verdict": "text not null",
        "witnesses": "text not null",
        "note": "text not null",
        "reviewed_at": "real not null",
    })
    repository.create_table(CHANGE_TABLE, {
        "artifact_kind": "text not null",
        "change_kind": "text not null",
        "operator": "text not null",
        # FR-019's and FR-054's three fields: the operator, the version moved
        # from, the version moved to. Empty rather than null on a first
        # publication, because there is no prior version and a null would be
        # indistinguishable from a value nobody wrote.
        "changed_from": "text not null",
        "changed_to": "text not null",
        # Whether this change is *recorded as* a widening. Always 1 for a
        # restoration (FR-054), the predicate's answer otherwise.
        "widening": "int not null",
        # What the predicate said, kept even where `widening` overrides it.
        "assessed_verdict": "text not null",
        "witnesses": "text not null",
        "review_hash": "text not null",
        "reviewer": "text not null",
        "at": "real not null",
    })


@dataclass(frozen=True)
class Proposal:
    """A candidate version, its address, and what changing to it would do."""

    kind: str
    content_hash: str
    assessment: Assessment
    #: `publication` or `restoration`. Part of what a review is bound to, and
    #: **not** cosmetic: without it, the approval that let a version take
    #: effect on the way up would silently authorise a rollback to it on the
    #: way back down. Those are two decisions taken against two different
    #: comparands — the same bytes are a widening in one direction and a
    #: narrowing in the other — and one approval must not answer for both.
    #: Found by `test_a_restoration_without_a_review_does_not_move_the_
    #: reference`, which passed vacuously until the positive arm beside it
    #: was written.
    change_kind: str = CHANGE_PUBLICATION
    document: Mapping[str, Any] = field(repr=False, default_factory=dict)

    @property
    def widening(self) -> bool:
        return self.assessment.widening


@dataclass(frozen=True)
class Change:
    """One recorded configuration change. FR-019's record."""

    kind: str
    change_kind: str
    operator: str
    changed_from: str
    changed_to: str
    widening: bool
    assessed_verdict: str
    witnesses: tuple[str, ...]
    reviewer: str
    at: float


# ---------------------------------------------------------------------------
# The three steps.


def require_gated(kind: str) -> None:
    require(kind)
    if kind not in GATED_KINDS:
        raise ReviewNotApplicable(
            f"{kind!r} is not gated. FR-012 covers the deny list and the "
            "safe-method rule set, and FR-019 the enforcement point's "
            f"allowlist; those are {sorted(GATED_KINDS)}. Gating a kind whose "
            "operators have no way to produce a review would stop it being "
            "publishable at all, which is a scope change rather than a "
            "stricter default."
        )


def _document_at(store: ArtifactStore, kind: str, address: str | None) -> Mapping[str, Any]:
    """The stored payload at `address`, or an empty surface where there is none."""
    if address is None:
        return {}
    return json.loads(store.get_bytes(address))


def propose(
    store: ArtifactStore,
    kind: str,
    document: Mapping[str, Any],
) -> Proposal:
    """Assess a candidate against the version in force. Stores nothing.

    The operator reads this. It is deliberately side-effect free: a proposal
    that published would make the review a formality performed after the fact,
    which is the thing FR-012's *"before it takes effect"* rules out.
    """
    require_gated(kind)
    envelope = wrap(kind, document)
    current = store.current_ref(kind)
    before = surface_of(kind, _document_at(store, kind, current))
    after = surface_of(kind, envelope.payload)
    return Proposal(
        kind=kind,
        content_hash=envelope.address,
        assessment=assess(before, after),
        change_kind=CHANGE_PUBLICATION,
        document=dict(document),
    )


def record_review(
    repository: Repository,
    proposal: Proposal,
    *,
    reviewer: str,
    decision: str,
    at: float,
    note: str = "",
) -> None:
    """Record that a named human approved or rejected this exact version."""
    require_gated(proposal.kind)
    if decision not in DECISIONS:
        raise ReviewGateError(
            f"{decision!r} is not a review decision ({sorted(DECISIONS)}). A "
            "third value would be a review that neither admits nor refuses, "
            "and `apply` would have to guess which."
        )
    if not reviewer.strip():
        raise ReviewGateError(
            "a review names the reviewer. FR-012 asks for review *by the "
            "operator*, and an anonymous approval records that somebody "
            "approved rather than that the operator did."
        )
    repository.insert(REVIEW_TABLE, {
        "artifact_kind": proposal.kind,
        "content_hash": proposal.content_hash,
        "change_kind": proposal.change_kind,
        "reviewer": reviewer,
        "decision": decision,
        "verdict": proposal.assessment.verdict,
        "witnesses": "\n".join(proposal.assessment.witnesses()),
        "note": note,
        "reviewed_at": at,
    })


def approval_for(
    repository: Repository,
    kind: str,
    content_hash: str,
    change_kind: str,
) -> dict[str, Any] | None:
    """The most recent approval of this version *for this kind of change*.

    A rejection recorded after an approval withdraws it: the rows are read
    newest first and only the newest decision for the address is consulted.
    Anything else would make a rejection unable to undo a mistake.
    """
    rows = repository.select(
        REVIEW_TABLE,
        where={"artifact_kind": kind, "content_hash": content_hash, "change_kind": change_kind},
        order_by="reviewed_at", descending=True)
    if not rows:
        return None
    latest = rows[0]
    return latest if latest["decision"] == DECISION_APPROVED else None


def apply(
    store: ArtifactStore,
    proposal: Proposal,
    *,
    produced_by: str,
    operator: str,
    now: float,
) -> tuple[StoredArtifact, Change]:
    """Publish an approved version and record the change. Refuses otherwise.

    The refusal happens before anything is written, so a refused apply leaves
    the object store and the reference exactly as it found them.
    """
    require_gated(proposal.kind)
    if not operator.strip():
        raise ReviewGateError(
            "a configuration change names the operator who made it (FR-019). "
            "An unattributed change is one nobody can be asked about."
        )

    approval = approval_for(
        store.repo, proposal.kind, proposal.content_hash, CHANGE_PUBLICATION)
    if approval is None:
        raise ReviewRequired(
            f"{proposal.kind} {proposal.content_hash} has no recorded "
            "approval, so it does not take effect (FR-012: reviewable by the "
            "operator **before** it takes effect). The version in force is "
            f"unchanged at {store.current_ref(proposal.kind)}. If this "
            "version was reviewed, it was reviewed at a different address — "
            "an approval is bound to the bytes it was shown, so editing the "
            "document after review invalidates it, which is the point."
        )

    before = store.current_ref(proposal.kind)
    stored = store.publish(
        proposal.kind, proposal.document,
        produced_by=produced_by, moved_by=operator, now=now)
    change = _record_change(
        store.repo,
        kind=proposal.kind,
        change_kind=CHANGE_PUBLICATION,
        operator=operator,
        changed_from=before or "",
        changed_to=stored.content_hash,
        widening=proposal.assessment.widening,
        assessed_verdict=proposal.assessment.verdict,
        witnesses=proposal.assessment.witnesses(),
        review_hash=proposal.content_hash,
        reviewer=str(approval["reviewer"]),
        at=now,
    )
    return stored, change


def propose_restore(store: ArtifactStore, kind: str) -> Proposal:
    """The proposal an operator reviews before a rollback.

    The candidate is the immediately prior version, which is already stored, so
    this reads it rather than wrapping anything. Its address is the address the
    review binds to, exactly as for a publication.
    """
    require_gated(kind)
    previous = store.previous_ref(kind)
    if previous is None:
        raise ReviewGateError(
            f"{kind} has no immediately prior version to restore, so there is "
            "nothing to review (FR-054)."
        )
    current = store.current_ref(kind)
    before = surface_of(kind, _document_at(store, kind, current))
    after = surface_of(kind, _document_at(store, kind, previous))
    return Proposal(
        kind=kind, content_hash=previous, assessment=assess(before, after),
        change_kind=CHANGE_RESTORATION)


def restore(
    store: ArtifactStore,
    proposal: Proposal,
    *,
    operator: str,
    now: float,
) -> tuple[rollback.Restoration, Change]:
    """FR-054's single operator action, behind FR-012's review.

    Still one action from the operator's side — one call, one kind, one named
    human, and no argument through which an entry could be supplied. The review
    is a precondition rather than a second action, in the sense FR-054 itself
    uses when it makes a restoration *"subject to the same review as FR-012"*:
    if the review counted as part of the action, that sentence would contradict
    the one above it.
    """
    require_gated(proposal.kind)
    approval = approval_for(
        store.repo, proposal.kind, proposal.content_hash, CHANGE_RESTORATION)
    if approval is None:
        raise ReviewRequired(
            f"restoring {proposal.kind} to {proposal.content_hash} has no "
            "recorded approval. FR-054 makes a restoration subject to the "
            "same review as FR-012, and the version in force is unchanged at "
            f"{store.current_ref(proposal.kind)}. An approval recorded when "
            "these bytes were first published is not one: that decision was "
            "taken against a different comparand, and in the other direction."
        )

    restoration = rollback.restore_previous(
        store, proposal.kind, operator=operator, now=now)
    if restoration.restored_to != proposal.content_hash:
        # The prior version moved between the review and the restoration —
        # somebody published in between. Raising after the fact would be too
        # late, so this is a loud inconsistency rather than a guard: the
        # transaction has committed. Recorded as its own change either way.
        raise ReviewGateError(
            f"{proposal.kind} was restored to {restoration.restored_to} but "
            f"the approval was for {proposal.content_hash}. The prior version "
            "moved between the review and the restoration."
        )

    change = _record_change(
        store.repo,
        kind=proposal.kind,
        change_kind=CHANGE_RESTORATION,
        operator=operator,
        changed_from=restoration.restored_from,
        changed_to=restoration.restored_to,
        # FR-054: "recorded exactly as a widening is under FR-019". Not the
        # predicate's answer, and the predicate's answer is kept beside it.
        widening=True,
        assessed_verdict=proposal.assessment.verdict,
        witnesses=proposal.assessment.witnesses(),
        review_hash=proposal.content_hash,
        reviewer=str(approval["reviewer"]),
        at=now,
    )
    return restoration, change


def _record_change(
    repository: Repository,
    *,
    kind: str,
    change_kind: str,
    operator: str,
    changed_from: str,
    changed_to: str,
    widening: bool,
    assessed_verdict: str,
    witnesses: tuple[str, ...],
    review_hash: str,
    reviewer: str,
    at: float,
) -> Change:
    repository.insert(CHANGE_TABLE, {
        "artifact_kind": kind,
        "change_kind": change_kind,
        "operator": operator,
        "changed_from": changed_from,
        "changed_to": changed_to,
        "widening": 1 if widening else 0,
        "assessed_verdict": assessed_verdict,
        "witnesses": "\n".join(witnesses),
        "review_hash": review_hash,
        "reviewer": reviewer,
        "at": at,
    })
    return Change(
        kind=kind,
        change_kind=change_kind,
        operator=operator,
        changed_from=changed_from,
        changed_to=changed_to,
        widening=widening,
        assessed_verdict=assessed_verdict,
        witnesses=witnesses,
        reviewer=reviewer,
        at=at,
    )


def changes(repository: Repository, kind: str | None = None) -> list[dict[str, Any]]:
    where = {"artifact_kind": kind} if kind else None
    return repository.select(CHANGE_TABLE, where=where, order_by="at")


def reviews(repository: Repository, kind: str | None = None) -> list[dict[str, Any]]:
    where = {"artifact_kind": kind} if kind else None
    return repository.select(REVIEW_TABLE, where=where, order_by="reviewed_at")
