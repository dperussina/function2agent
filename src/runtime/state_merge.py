"""T044 — explicit per-key merge rules for state a concurrent step writes (T-08).

**Last-write-wins is forbidden, and the reason is measured.** Finding 006 ran
two parallel branches writing one shared key and observed one of the two writes
**vanish with no error and no warning**. Nothing in that run was slow, wrong or
loud; a value was simply not there afterwards. That is the defect this module
exists to make unrepresentable, and it is unrepresentable in exactly one way:
every shared key names a rule in advance, and every rule either reflects every
contribution or refuses.

**There is no default rule.** A key with no declared rule raises
`UndeclaredMergeKey`. A default would be a rule, the only rule anyone reaches
for is "take the last one", and a default that is the forbidden behaviour is
worse than no default — it makes the failure the path of least resistance.

**Refusing is a permitted outcome and discarding is not.** `single_writer` does
not combine anything: it says this key has one author per turn, and two authors
is a defect to report rather than a value to compute. What it may not do is pick
one. The distinction is the whole of T-08: a lost update is invisible, and a
refusal is not.

**Contributions are applied in declared index order** (`Contribution.index`,
which is `ToolCall.index`), so the merged value is a function of the fan-out and
not of the scheduler. Sorting by arrival order would make the result
reproducible only for as long as the latencies stayed the same, which is the
condition finding 006 varied.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

# What a rule may do when more than one branch writes a key. There is no third
# value: "discard" is the behaviour T-08 forbids, and it is absent here rather
# than present-and-unused so that writing it requires editing this line.
COMBINE = "combine"
REFUSE = "refuse"


class MergeError(RuntimeError):
    """A merge that cannot be performed as declared."""


class UndeclaredMergeKey(MergeError):
    """A shared key with no declared rule. Fail closed, never last-write-wins."""


class ConcurrentWriteError(MergeError):
    """Two branches wrote a key whose rule permits one.

    Names both branches. A refusal that says only "conflict on `answer`" leaves
    an operator to find the two writers by reading the fan-out, and the point of
    refusing rather than discarding is that the collision is actionable.
    """


class MergeRuleError(MergeError):
    """A rule that cannot be applied to the values it was given."""


@dataclass(frozen=True)
class MergeRule:
    """One declared way to combine a shared key's contributions.

    `sample_a` and `sample_b` are two *differing* values the rule accepts, and
    they are part of the rule rather than part of a test on purpose. The
    invariant in `tests/invariants/test_fanout_ordering.py` walks this registry
    and checks each rule against T-08's requirement; if the samples lived in the
    test, a rule added later would be silently uncovered — and the coverage gap
    would be in the one mechanism whose failure mode is silence. Here the
    registry's shape is the coverage, on the same reasoning as the span guard in
    `src/runtime/trace.py`.
    """

    name: str
    on_conflict: str
    why: str
    combine: Callable[[Sequence[Any]], Any]
    sample_a: Any
    sample_b: Any


def _append(values: Sequence[Any]) -> list[Any]:
    merged: list[Any] = []
    for value in values:
        if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
            raise MergeRuleError(
                f"append_in_declared_order needs a sequence per contribution, "
                f"got {type(value).__name__}. A string is a sequence of "
                "characters and concatenating one here is almost never what a "
                "caller meant, so it is refused rather than accepted."
            )
        merged.extend(value)
    return merged


def _sum_numeric(values: Sequence[Any]) -> Any:
    for value in values:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise MergeRuleError(
                f"sum_numeric needs a number per contribution, got "
                f"{type(value).__name__}. `bool` is excluded deliberately: "
                "summing two flags yields 2, which is neither flag."
            )
    return sum(values)


def _union(values: Sequence[Any]) -> frozenset[Any]:
    merged: set[Any] = set()
    for value in values:
        if not isinstance(value, (set, frozenset)):
            raise MergeRuleError(
                f"union_set needs a set per contribution, got "
                f"{type(value).__name__}"
            )
        merged |= set(value)
    return frozenset(merged)


def _disjoint_mapping(values: Sequence[Any]) -> dict[Any, Any]:
    merged: dict[Any, Any] = {}
    for value in values:
        if not isinstance(value, Mapping):
            raise MergeRuleError(
                f"merge_mapping_disjoint needs a mapping per contribution, got "
                f"{type(value).__name__}"
            )
        for key, item in value.items():
            if key in merged:
                raise ConcurrentWriteError(
                    f"two contributions both set the inner key {key!r}. This "
                    "rule merges mappings that do not overlap; an overlap is "
                    "the same lost update one level down, so it is refused "
                    "rather than resolved by position."
                )
            merged[key] = item
    return merged


def _single_writer(values: Sequence[Any]) -> Any:
    if len(values) != 1:
        # Reached only through `MergePolicy.merge`, which raises the
        # branch-naming error before getting here. Kept as a guard because a
        # future caller reaching `combine` directly must not get a value.
        raise ConcurrentWriteError(
            f"single_writer received {len(values)} contributions. This rule "
            "never picks one."
        )
    return values[0]


APPEND_IN_DECLARED_ORDER = MergeRule(
    name="append_in_declared_order",
    on_conflict=COMBINE,
    why="Every contribution survives, in the provider's declared index order "
        "so the result does not depend on which branch finished first.",
    combine=_append,
    sample_a=["a"],
    sample_b=["b"],
)

SUM_NUMERIC = MergeRule(
    name="sum_numeric",
    on_conflict=COMBINE,
    why="Counters and accrued cost. Addition is the one operation for which "
        "losing a contribution is arithmetically visible rather than silent.",
    combine=_sum_numeric,
    sample_a=1,
    sample_b=2,
)

UNION_SET = MergeRule(
    name="union_set",
    on_conflict=COMBINE,
    why="Sets of observed things — visited paths, denied destinations — where "
        "order carries nothing and every member has to be present.",
    combine=_union,
    sample_a=frozenset({"a"}),
    sample_b=frozenset({"b"}),
)

MERGE_MAPPING_DISJOINT = MergeRule(
    name="merge_mapping_disjoint",
    on_conflict=REFUSE,
    why="Per-call results keyed by call id. Disjoint by construction; an "
        "overlap means two branches claimed one identity and is refused.",
    combine=_disjoint_mapping,
    sample_a={"a": 1},
    sample_b={"b": 2},
)

SINGLE_WRITER = MergeRule(
    name="single_writer",
    on_conflict=REFUSE,
    why="The turn's answer, and anything else with one author. Two authors is "
        "a defect to report, and reporting it is the only alternative to "
        "losing one of them.",
    combine=_single_writer,
    sample_a="left",
    sample_b="right",
)

RULES: tuple[MergeRule, ...] = (
    APPEND_IN_DECLARED_ORDER,
    SUM_NUMERIC,
    UNION_SET,
    MERGE_MAPPING_DISJOINT,
    SINGLE_WRITER,
)
RULES_BY_NAME = {rule.name: rule for rule in RULES}


@dataclass(frozen=True)
class Contribution:
    """One branch's writes, carrying the position that orders them.

    `index` is the `ToolCall.index` the branch ran for. It is required, and it
    is what `merge` sorts on — the branch name is an identity for the error
    message, not an order.
    """

    branch: str
    index: int
    writes: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.branch:
            raise MergeError(
                "a contribution needs a branch identity, so that a refusal can "
                "name who collided with whom"
            )
        if self.index < 0:
            raise MergeError("a contribution's index is a declared position")


@dataclass(frozen=True)
class MergePolicy:
    """The per-key rule table for one piece of shared state."""

    rules: Mapping[str, str]

    def __post_init__(self) -> None:
        for key, name in self.rules.items():
            if name not in RULES_BY_NAME:
                raise MergeError(
                    f"key {key!r} names merge rule {name!r}, which is not "
                    f"declared ({sorted(RULES_BY_NAME)}). Add it to RULES in "
                    "src/runtime/state_merge.py with the reason it is safe, "
                    "rather than passing a string through."
                )

    def rule_for(self, key: str) -> MergeRule:
        try:
            return RULES_BY_NAME[self.rules[key]]
        except KeyError:
            raise UndeclaredMergeKey(
                f"{key!r} was written by a concurrent step and has no declared "
                "merge rule. T-08 forbids last-write-wins, and an undeclared "
                "key has no other resolution — finding 006 measured one of two "
                "parallel writes to a shared key vanishing with no error and "
                "no warning. Declare the key's rule in the MergePolicy."
            ) from None

    def merge(
        self,
        base: Mapping[str, Any],
        contributions: Sequence[Contribution],
    ) -> dict[str, Any]:
        """Fold `contributions` into `base`, by declared rule and declared order.

        `base` is never mutated: a merge that edited its input would make the
        pre-merge state unrecoverable, and the pre-merge state is what a resumed
        turn needs.
        """
        merged = dict(base)
        by_key: dict[str, list[Contribution]] = {}
        for contribution in sorted(contributions, key=lambda c: c.index):
            for key in contribution.writes:
                by_key.setdefault(key, []).append(contribution)

        for key, writers in by_key.items():
            rule = self.rule_for(key)
            if rule.on_conflict == REFUSE and len(writers) > 1 and rule is SINGLE_WRITER:
                names = ", ".join(f"{c.branch}(index={c.index})" for c in writers)
                raise ConcurrentWriteError(
                    f"{len(writers)} branches wrote {key!r}, whose declared "
                    f"rule is {rule.name}: {names}. {rule.why} Nothing is "
                    "discarded and nothing is picked — this is the refusal "
                    "T-08 requires in place of a lost update."
                )
            values = [c.writes[key] for c in writers]
            if key in merged and rule is not SINGLE_WRITER:
                # The prior value is a contribution too, and it is first: a
                # merge that dropped it would lose the state the turn started
                # with, which is the same defect with a longer fuse.
                values = [merged[key], *values]
            merged[key] = rule.combine(values)
        return merged
