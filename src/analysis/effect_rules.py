"""T081 — FR-010's rule set and its deny list, as the versioned configuration
FR-012 requires and FR-054 enumerates.

**What FR-010 says a read-only resolution is**, in its own words:

    A call resolves read-only when its method is a safe method of a served
    operation in the set from FR-001 **and** it matches no entry in a
    maintained deny list of known side-effecting reads. This is a stated rule
    set, not a proof, and the system's documentation and interfaces MUST NOT
    describe it as one.

Two clauses, two provenances, and this module is where they are written down
so an operator can read them before they take effect.

## Which of FR-012's three clauses this module discharges, and which it does not

FR-012 asks for three things. They are discharged in three different places
and that is stated here so nobody looks for all three in one file:

1. **Versioned configuration.** Here, by producing the `effect_gate_rule_set`
   document of `src/contracts/schemas.py` — one of FR-054's eight kinds — which
   `src/analysis/artifact_store.py` content-addresses and keeps a ref history
   for, and which `src/analysis/rollback.py` can restore in one operator action.
2. **Reviewable by the operator before it takes effect.** **T082**, in
   `src/analysis/review_gate.py`. This module makes a rule set *reviewable* —
   every entry names its rule identifier, its matcher, its resolved tier and
   why it is there — and does not decide whether anything was reviewed.
3. **Where the agent has no write path to it.** Already discharged, and
   **recorded as covered rather than claimed here**: FR-048 requires the
   effect-gate rule set to lie outside the declared location set, and
   `src/supervisor/location_set.py`'s `load()` fails closed when a declared
   location would contain it. A second check here would be a second definition
   of one boundary, which is the drift this tree's tooling exists to prevent.

## Two provenances, and they are two types rather than one type with a flag

This is **OD-27**'s discipline, taken from `src/runtime/providers/costs.py`
where a vendor-published rate and an operator-declared one are `PriceEntry` and
`OperatorPrice` rather than one type carrying a `provenance` field. FR-010's two
clauses have exactly that shape:

- `ServedOperationRule` is **derived** from the served-operation set FR-001
  obtains. Its method and its safety come from what the target published.
- `DenyListEntry` is **operator-declared**. Nothing derives it: it exists
  because a human knows that this particular GET sends an email, and no
  artifact in this system says so.

A field would be a place a declared entry could claim derived provenance, which
is the one confusion the distinction exists to make impossible.

**The resolved tier follows the same split, and the asymmetry is the point.**
On a served rule the tier is a **property**, computed from FR-010's own
sentence: safe method ⇒ `read_only`, anything else ⇒ not. It is not settable,
because an entry that could declare `read_only` for a `POST` is precisely the
misconfiguration FR-009 exists to prevent. On a deny entry the tier is a
**field**, because whether a known side-effecting read is reversible or
irreversible is knowledge only the declaring operator has and nothing here can
derive. What is *not* declarable there either is `read_only`: an entry
declaring it would deny nothing and would make the deny list unreadable as the
thing FR-010 says it is.

**The tier distinction inside the deny list is reportable, not operative.**
The enforcement point permits `read_only` and denies everything else
(FR-009), so `reversible_write` and `irreversible` are treated identically by
it. They are distinguished so the reason is reportable — the same disposition
FR-056 gives `deputy` and `uninspectable`.

## What this module deliberately does not do

**It does not match a request.** There is no `matches(method, path)` here. A
live request is resolved against this configuration by the enforcement point,
in Go, at `src/proxy/effect.go` and `src/proxy/policy.go` — and a second
implementation of that matching in Python would be an unenforced duplicate that
can disagree with the one that actually decides. What this module answers is
the *set-containment* question a review needs and a request never asks:
`Matcher.subsumes`, whether one declared matcher's calls are a subset of
another's. T082's widening predicate is its only caller.

**It does not compute a rule-set version of its own**, and the reason is worth
recording because T077 did the opposite for the served-operation set. There,
`set_version` is a content address over the operations alone, deliberately
distinct from the artifact's content address, because the artifact's address
moves when `schema_version` moves and FR-028 would read our own schema release
as the deployment clock ticking. **That reason does not apply here.**
`effect_gate_rule_set` is `source_derived=False`, so no drift channel reads its
content address at all, and a second version number with no reader is a field
that can only go wrong. The versioning FR-012 asks for is the artifact store's.

## This is a stated rule set and not a proof

FR-010 requires that in its own words, and `basis()` below is the surface
string that carries it. Two things it names, neither of them decoration:

- **U-43** — the effect gate's read-only **precision is unmeasured against
  anything**. This is why v1 is read-only (**OD-10**), and FR-041 makes the
  measurement the exit condition. Nothing in this module measures it, and a
  rule set that validates here is not evidence that its tiers are right.
- **FR-041's own prohibition**: the threshold for that measurement must be
  pre-registered for a **per-call** gate and *"MUST NOT be inherited by
  default"* from the superseded per-tool gate. So no precision figure appears
  anywhere in this module, and none should be added to it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from src.contracts.schemas import EFFECT_GATE_RULE_SET

# ---------------------------------------------------------------------------
# The tiers and the safe methods.

#: The four effect tiers. Mirrors `src/proxy/policy.go`'s constants by value,
#: because the two processes exchange this artifact and a tier name that
#: differs by a character is a tier the enforcement point cannot resolve.
TIER_READ_ONLY = "read_only"
TIER_REVERSIBLE_WRITE = "reversible_write"
TIER_IRREVERSIBLE = "irreversible"
TIER_UNRESOLVED = "unresolved"

TIERS: tuple[str, ...] = (
    TIER_READ_ONLY, TIER_REVERSIBLE_WRITE, TIER_IRREVERSIBLE, TIER_UNRESOLVED,
)

#: FR-009: *"Only a call resolving read-only MAY be permitted."* A one-member
#: frozenset for `ADMISSIBLE_STATES`'s reason: a second permitted tier has to
#: be a visible edit here rather than an `or` inside a branch.
PERMITTED_TIERS = frozenset({TIER_READ_ONLY})

#: The safe methods, by the same value-agreement rule as the tiers above.
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})

#: The rule-identifier namespace this registry declares, and its two halves.
#: Disjoint from admission `ADM-`, deputy inspection `DEP-`, filesystem `FS-`
#: and the enforcement point's own `EG-` pipeline registry — one shared
#: namespace would make a rule identifier in a record ambiguous about which
#: registry declared it. The `EG-` namespace is specifically avoided because
#: `src/proxy/policy.go` refuses a deny-list entry whose identifier collides
#: with a pipeline rule, and an artifact this module produced would be refused
#: at the enforcement point's startup rather than here.
NAMESPACE = "EFF-"
SERVED_RULE_PREFIX = "EFF-OP-"
DENY_RULE_PREFIX = "EFF-DENY-"


class EffectRuleError(ValueError):
    """A rule set that cannot be as FR-010 and FR-012 describe."""


# ---------------------------------------------------------------------------
# The matcher.


@dataclass(frozen=True)
class Matcher:
    """One method and one path template — what an entry matches on.

    The template grammar is `src/proxy/policy.go`'s: segments separated by
    `/`, a segment of the form `{name}` standing for exactly one non-empty
    segment, and a template never matching a path with a different segment
    count. It is validated here and **applied** there.
    """

    method: str
    path_template: str

    def __post_init__(self) -> None:
        if not self.method or self.method != self.method.upper():
            raise EffectRuleError(
                f"{self.method!r} is not an HTTP method token. Methods are "
                "case-sensitive and are compared as received, so a "
                "lower-case `get` is not the safe method GET — normalizing "
                "it here would make this configuration disagree with the "
                "enforcement point that reads it."
            )
        template = self.path_template
        if not template.startswith("/"):
            raise EffectRuleError(
                f"{template!r} does not begin with '/'. A relative template "
                "matches nothing at the enforcement point, so an entry "
                "carrying one is a rule that silently never fires."
            )
        for segment in template.lstrip("/").split("/"):
            if segment.startswith("{") != segment.endswith("}"):
                raise EffectRuleError(
                    f"{template!r} has a malformed parameter segment "
                    f"{segment!r}. Half a brace is read as a literal by the "
                    "enforcement point, which is a rule that matches one "
                    "path nobody will ever request."
                )
            if segment == "{}":
                raise EffectRuleError(
                    f"{template!r} has an unnamed parameter segment. A "
                    "parameter with no name cannot be reported as the input "
                    "a rule matched on (FR-038)."
                )

    @property
    def segments(self) -> tuple[str, ...]:
        return tuple(self.path_template.lstrip("/").split("/"))

    def subsumes(self, other: "Matcher") -> bool:
        """Whether every call `other` matches is also matched by `self`.

        The one question a review asks and a request never does. It is
        **sound and deliberately incomplete**: `self` subsumes `other` when
        the methods are identical, the segment counts agree, and every
        segment of `self` is either a parameter or literally equal to
        `other`'s. `/orders/{id}` subsumes `/orders/7`; the reverse does not
        hold, and that asymmetry is what makes T082's widening predicate able
        to tell a generalization from a specialization.

        Incompleteness is in the safe direction for the caller it has. A pair
        this fails to relate is reported by T082 as a change rather than as no
        change, and an unrelated pair reported as a change is a review the
        operator did not strictly need. The reverse — a widening reported as
        no change — is the failure that matters, and it is not reachable by
        answering `False` too often.
        """
        return self.method == other.method and path_subsumes(
            self.path_template, other.path_template)

    def document(self) -> dict[str, Any]:
        return {"method": self.method, "path_template": self.path_template}


def path_subsumes(general: str, specific: str) -> bool:
    """Whether every path `specific` matches is also matched by `general`.

    Method-free, because FR-019 widens *"the destination or method allowlist"*
    as two axes and an egress policy declares its paths on one of them with no
    method attached. `Matcher.subsumes` is this plus method equality.
    """
    mine = tuple(general.lstrip("/").split("/"))
    theirs = tuple(specific.lstrip("/").split("/"))
    if len(mine) != len(theirs):
        return False
    return all(
        _is_parameter(segment) or segment == counterpart
        for segment, counterpart in zip(mine, theirs)
    )


def _is_parameter(segment: str) -> bool:
    return segment.startswith("{") and segment.endswith("}") and len(segment) > 2


# ---------------------------------------------------------------------------
# The two entry types.


@dataclass(frozen=True)
class ServedOperationRule:
    """FR-010's first clause: a safe method of a served operation.

    Derived from the served-operation set FR-001 obtains, which is why
    `tier` is a property below and not a field.
    """

    rule_id: str
    operation_id: str
    matcher: Matcher
    #: Whether the target's published specification describes this operation
    #: as safe. Comes from the served-operation set; not an opinion formed
    #: here.
    safe: bool
    justification: str

    def __post_init__(self) -> None:
        if not self.rule_id.startswith(SERVED_RULE_PREFIX):
            raise EffectRuleError(
                f"{self.rule_id!r} is not in the served-operation rule "
                f"namespace ({SERVED_RULE_PREFIX}...). Admission rules are "
                "`ADM-`, deputy rules `DEP-`, filesystem rules `FS-` and the "
                "enforcement point's pipeline rules `EG-`; one shared "
                "namespace would make a rule identifier in a decision record "
                "ambiguous about which registry declared it."
            )
        if not self.operation_id:
            raise EffectRuleError(
                f"{self.rule_id}: a rule names the operation it resolves. "
                "FR-002 requires the served set at operation granularity, and "
                "a rule with no operation cannot be denied by name, inspected "
                "under FR-020, or compared against a later set under FR-051."
            )
        if not self.justification.strip():
            raise EffectRuleError(
                f"{self.rule_id}: FR-012 requires this set to be reviewable "
                "before it takes effect, and an entry with no justification "
                "is not reviewable. An operator reading it can see what it "
                "matches and cannot see why anybody thought that was right."
            )
        if self.safe and self.matcher.method not in SAFE_METHODS:
            raise EffectRuleError(
                f"{self.rule_id}: {self.matcher.method} is declared safe and "
                f"is not one of {sorted(SAFE_METHODS)}. FR-010 resolves "
                "read-only only where the method **is a safe method**, so "
                "this entry would resolve a write to read_only — which is the "
                "single failure FR-009 and OD-10 exist to prevent, and which "
                "the enforcement point could not catch because it reads the "
                "tier this artifact carries."
            )

    @property
    def tier(self) -> str:
        """FR-010's sentence, as a computed value rather than a field.

        A field would be somewhere an entry could claim `read_only` for an
        unsafe method independently of `safe`, which is the same confusion
        `PriceEntry.provenance` is a property to prevent.

        Not-safe resolves to `reversible_write` and never to `irreversible`.
        Both are denied, and choosing between them here would be a claim
        about the target with nothing behind it — the same reason
        `src/proxy/effect.go` does not try to tell them apart.
        """
        return TIER_READ_ONLY if self.safe else TIER_REVERSIBLE_WRITE

    @property
    def provenance(self) -> str:
        return PROVENANCE_SERVED_SET

    def document(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "operation_id": self.operation_id,
            "provenance": self.provenance,
            "safe": self.safe,
            "tier": self.tier,
            "justification": self.justification,
            **self.matcher.document(),
        }


@dataclass(frozen=True)
class DenyListEntry:
    """FR-010's second clause: one known side-effecting read.

    Operator-declared. `declared_by` and `justification` are both required for
    OD-27's reason: where a derived entry cites the artifact it came from, a
    declaration can only cite **who says so**, and an unattributable
    declaration is one nobody can be asked about.
    """

    rule_id: str
    matcher: Matcher
    #: The tier the operator declares this read actually has. Declared rather
    #: than derived, because nothing in this system knows it.
    tier: str
    #: The accountable party. A name, not an address — the same substitution
    #: `costs.OperatorPrice.declared_by` makes.
    declared_by: str
    justification: str

    def __post_init__(self) -> None:
        if not self.rule_id.startswith(DENY_RULE_PREFIX):
            raise EffectRuleError(
                f"{self.rule_id!r} is not in the deny-list namespace "
                f"({DENY_RULE_PREFIX}...). See ServedOperationRule for why "
                "the registries do not share one."
            )
        if self.tier not in TIERS:
            raise EffectRuleError(
                f"{self.rule_id}: {self.tier!r} is not one of the declared "
                f"tiers ({list(TIERS)}). A tier outside the set is one the "
                "enforcement point cannot resolve, and an unresolvable tier "
                "reaching it is a denial with no legible reason (FR-011)."
            )
        if self.tier in PERMITTED_TIERS:
            raise EffectRuleError(
                f"{self.rule_id}: a deny-list entry declaring "
                f"{self.tier!r} denies nothing. FR-010's deny list is of "
                "**known side-effecting reads** — the whole content of an "
                "entry is that this read is not one — so an entry at a "
                "permitted tier is either a mistake or an attempt to express "
                "an allowlist in the one structure that cannot hold one."
            )
        if not self.declared_by.strip():
            raise EffectRuleError(
                f"{self.rule_id}: a declaration names an accountable party. "
                "Nothing derives a deny-list entry — it is here because "
                "somebody knows this read writes — so 'who says so' is the "
                "whole of its provenance, and an entry without it cannot be "
                "reviewed under FR-012 or questioned later."
            )
        if not self.justification.strip():
            raise EffectRuleError(
                f"{self.rule_id}: FR-012 requires a reviewable justification. "
                "For this entry it is the only statement of what the side "
                "effect actually is."
            )

    @property
    def provenance(self) -> str:
        return PROVENANCE_OPERATOR

    def document(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "provenance": self.provenance,
            "tier": self.tier,
            "declared_by": self.declared_by,
            "justification": self.justification,
            **self.matcher.document(),
        }


#: Derived from the served-operation set FR-001 obtains. `ServedOperationRule`.
PROVENANCE_SERVED_SET = "served_operation_set"
#: Declared by an operator against no artifact. `DenyListEntry`.
PROVENANCE_OPERATOR = "operator"

PROVENANCES: frozenset[str] = frozenset({PROVENANCE_SERVED_SET, PROVENANCE_OPERATOR})


# ---------------------------------------------------------------------------
# The set.


@dataclass(frozen=True)
class EffectRuleSet:
    """The rule set and the deny list it ships with — one artifact.

    FR-054 joins them with *"and its"*, and `src/contracts/schemas.py` records
    why separating them would be a hole: a rule set could then be rolled back
    to a version whose deny list it never shipped with.
    """

    deployment_id: str
    rules: tuple[ServedOperationRule, ...]
    deny_list: tuple[DenyListEntry, ...]

    def __post_init__(self) -> None:
        if not self.deployment_id:
            raise EffectRuleError(
                "a rule set names the deployment it governs (FR-035, FR-002). "
                "A set with no subject resolves calls against a target nobody "
                "can name."
            )
        seen: dict[str, str] = {}
        for entry in (*self.rules, *self.deny_list):
            previous = seen.get(entry.rule_id)
            if previous is not None:
                raise EffectRuleError(
                    f"{entry.rule_id} is declared twice ({previous} and "
                    f"{type(entry).__name__}). FR-011 requires a decision to "
                    "name the rule that produced it, and an identifier two "
                    "entries answer to names nothing. The identifier space is "
                    "shared across both lists on purpose: a decision record "
                    "carries one rule identifier and does not say which list "
                    "it came from."
                )
            seen[entry.rule_id] = type(entry).__name__

    @property
    def permitted(self) -> tuple[Matcher, ...]:
        """Every matcher this set resolves to a permitted tier.

        The read-only surface, and the thing T082 compares between versions.
        Stated positively — the matchers whose tier **is** in
        `PERMITTED_TIERS` — rather than as the complement of the denied ones,
        which would answer the wrong way round for a tier nobody thought of.
        """
        return tuple(r.matcher for r in self.rules if r.tier in PERMITTED_TIERS)

    @property
    def denied(self) -> tuple[Matcher, ...]:
        """Every matcher the deny list removes from the permitted surface."""
        return tuple(entry.matcher for entry in self.deny_list)

    def document(self, *, published_at: str) -> dict[str, Any]:
        """The `effect_gate_rule_set` payload, ready for `envelope.wrap`.

        `published_at` is a parameter with no default for the reason nothing
        in this tree reads a clock by default, and it is declared volatile by
        the schema, so it travels in the envelope beside the hash and two
        publications of an unchanged set land on one content address.
        """
        return {
            "schema_version": EFFECT_GATE_RULE_SET.version,
            "deployment_id": self.deployment_id,
            "rules": [rule.document() for rule in self.rules],
            "deny_list": [entry.document() for entry in self.deny_list],
            "basis": basis(),
            "published_at": published_at,
        }


def basis() -> str:
    """FR-010's *"a stated rule set, not a proof"*, carried in the artifact.

    On the payload rather than in a comment, because FR-010's prohibition is
    on what *"the system's documentation and interfaces"* say, and an artifact
    a consumer reads is an interface.
    """
    return (
        "a stated rule set, not a proof (FR-010). The deny list is "
        "maintained by an operator rather than derived, and the safe-method "
        "clause is what the target's published specification declares rather "
        "than what its handlers do. The effect gate's read-only precision is "
        "unmeasured against anything (U-43), which is why v1 is read-only "
        "(OD-10); FR-041 makes that measurement the exit condition and "
        "forbids inheriting the superseded per-tool threshold, so no "
        "precision figure appears here."
    )


def rule_set_from(
    deployment_id: str,
    rules: Iterable[ServedOperationRule],
    deny_list: Iterable[DenyListEntry],
) -> EffectRuleSet:
    return EffectRuleSet(
        deployment_id=deployment_id,
        rules=tuple(rules),
        deny_list=tuple(deny_list),
    )


# ---------------------------------------------------------------------------
# Reading a stored document back.


def surfaces_of(document: Mapping[str, Any]) -> tuple[tuple[Matcher, ...], tuple[Matcher, ...]]:
    """`(permitted, denied)` for a stored `effect_gate_rule_set` payload.

    T082 compares the version in force against the incoming one, and the
    version in force is bytes in the object store rather than a live
    `EffectRuleSet`. This is the reader for those bytes, and it lives beside
    the writer so that the two cannot drift apart in different files.

    **It re-reads rather than re-validates.** A stored payload was validated
    when it was built; re-running the constructors here would refuse a
    document that a *previous* schema version legitimately produced, which
    would make FR-054's rollback refuse to assess a restoration target it is
    about to install.
    """
    permitted = tuple(
        Matcher(method=str(rule["method"]), path_template=str(rule["path_template"]))
        for rule in document.get("rules", ())
        if rule.get("tier") in PERMITTED_TIERS
    )
    denied = tuple(
        Matcher(method=str(entry["method"]), path_template=str(entry["path_template"]))
        for entry in document.get("deny_list", ())
    )
    return permitted, denied


def rule_ids(document: Mapping[str, Any]) -> tuple[str, ...]:
    """Every rule identifier a stored payload declares, both lists together."""
    return tuple(
        str(entry["rule_id"])
        for entry in (*document.get("rules", ()), *document.get("deny_list", ()))
    )


def subsumed_by_any(matcher: Matcher, candidates: Sequence[Matcher]) -> bool:
    """Whether any of `candidates` subsumes `matcher`."""
    return any(candidate.subsumes(matcher) for candidate in candidates)
