"""T045 — the two fan-out invariants (T-08, FR-007, data-model.md §2.2).

Finding 006 measured parallel fan-out producing **5 distinct orderings in 8
runs** under overlapping latencies, and a **silent lost update** where one of
two branches writing a shared key vanished with no error and no warning. Those
were read as graph properties. They are not: every provider in SC-010's set can
emit several tool calls in one turn, so a single-agent loop fans out whether or
not it has a graph.

**The hazard is the providers'; the measurements were ADK's.** OD-15 dropped
ADK, so the mitigation is ours and T-08 is a design rule with a known-real
hazard and no measurement behind it. That is why these are invariants rather
than comments, and it is why both arms below are written to fail on a
mechanism that is merely *usually* right.

**Each arm asserts its own precondition, and that is the part a weak version of
this test omits.** An ordering assertion is vacuous whenever completion order
happened to equal declared order — which is the common case, and which is why a
fan-out defect survives review. So the first arm asserts that the two orders
*differed on this run* before asserting which one was recorded. The second arm
takes its expectation from T-08's rule ("reflects every contribution, or
refuses") and never from the registry's own behaviour, so a rule that quietly
started discarding could not make the test agree with it.
"""

from __future__ import annotations

import time

import pytest

from src.runtime.dispatch import (
    DeclaredOrderError,
    ToolCall,
    dispatch,
)
from src.runtime.state_merge import (
    ConcurrentWriteError,
    Contribution,
    MergePolicy,
    RULES,
    UndeclaredMergeKey,
)


def _call(index: int, name: str = "run", **arguments: object) -> ToolCall:
    return ToolCall(
        index=index,
        call_id=f"call-{index}",
        name=name,
        arguments=arguments,
    )


# ---------------------------------------------------------------------------
# Arm 1 — declared-order recording.


def test_recording_follows_declared_index_order_not_completion_order() -> None:
    """The ordering invariant, under latencies that reverse completion."""
    # Descending sleeps: the call the provider declared first finishes last.
    # 4 calls, 4 workers, so the reversal is forced rather than hoped for.
    delays = {0: 0.20, 1: 0.15, 2: 0.10, 3: 0.01}
    calls = tuple(_call(i) for i in range(4))

    def execute(call: ToolCall) -> str:
        time.sleep(delays[call.index])
        return f"body-{call.index}"

    recorded: list[int] = []
    outcome = dispatch(calls, execute, record=lambda r: recorded.append(r.call.index))

    # The precondition, asserted rather than assumed. Without this the run
    # below is consistent with a dispatcher that has no ordering discipline at
    # all and merely got lucky.
    assert outcome.completion_order != tuple(range(4)), (
        "completion order equalled declared order, so this run cannot "
        "distinguish declared-order recording from completion-order recording. "
        f"completion_order={outcome.completion_order}"
    )

    assert [r.call.index for r in outcome.results] == [0, 1, 2, 3]
    assert recorded == [0, 1, 2, 3]
    # And the bodies travel with their own call, so a dispatcher that sorted
    # the indexes while shuffling the payloads is caught too.
    assert [r.body for r in outcome.results] == [f"body-{i}" for i in range(4)]


def test_a_failing_branch_does_not_move_the_order_of_the_others() -> None:
    """A raise inside one branch is an outcome, not a reordering event."""
    calls = tuple(_call(i) for i in range(3))

    def execute(call: ToolCall) -> str:
        if call.index == 0:
            time.sleep(0.10)
            raise RuntimeError("the first call failed")
        return f"body-{call.index}"

    recorded: list[int] = []
    outcome = dispatch(calls, execute, record=lambda r: recorded.append(r.call.index))

    assert recorded == [0, 1, 2]
    assert outcome.results[0].outcome == "upstream_fault"
    assert outcome.results[0].body != ""
    assert [r.outcome for r in outcome.results[1:]] == ["ok", "ok"]


def test_a_gap_in_the_declared_indexes_is_refused() -> None:
    """"Declared order" has to be a total order, or it orders nothing."""
    with pytest.raises(DeclaredOrderError) as raised:
        dispatch((_call(0), _call(2)), lambda call: "body", record=lambda r: None)
    assert "dense" in str(raised.value)


def test_a_duplicate_declared_index_is_refused() -> None:
    with pytest.raises(DeclaredOrderError):
        dispatch((_call(0), _call(0)), lambda call: "body", record=lambda r: None)


# ---------------------------------------------------------------------------
# Arm 2 — a concurrent write that cannot be lost.


def test_every_declared_merge_rule_either_combines_or_refuses() -> None:
    """T-08's rule, checked over the whole registry rather than one key.

    The expectation is taken from the rule T-08 states — *reflect every
    contribution, or refuse* — and not from what the registry happens to do.
    A rule that started returning one of two differing contributions would
    fail here rather than redefine the assertion.
    """
    assert RULES, "the merge registry is empty, so this arm checks nothing"

    for rule in RULES:
        policy = MergePolicy({"shared": rule.name})
        left = rule.sample_a
        right = rule.sample_b
        assert left != right, (
            f"{rule.name}: the registry's two samples are equal, so this arm "
            "cannot tell a combine from a discard for this rule"
        )
        contributions = (
            Contribution(branch="branch-0", index=0, writes={"shared": left}),
            Contribution(branch="branch-1", index=1, writes={"shared": right}),
        )
        try:
            merged = policy.merge({}, contributions)
        except ConcurrentWriteError as refused:
            # Refusing is the permitted alternative, and the refusal has to
            # name both branches or an operator cannot find the collision.
            assert "branch-0" in str(refused) and "branch-1" in str(refused)
            continue

        result = merged["shared"]
        assert result != left, (
            f"{rule.name} returned the first contribution unchanged: the "
            "second was discarded. That is last-write-wins with the "
            "arguments the other way round, and T-08 forbids it."
        )
        assert result != right, (
            f"{rule.name} returned the second contribution unchanged, so the "
            "first was lost. This is exactly finding 006's silent lost "
            "update: no error, no warning, one branch's write gone."
        )


def test_an_undeclared_shared_key_is_refused_rather_than_defaulted() -> None:
    """No implicit rule, because the implicit rule is last-write-wins."""
    policy = MergePolicy({"declared": "append_in_declared_order"})
    with pytest.raises(UndeclaredMergeKey) as raised:
        policy.merge(
            {},
            (
                Contribution(branch="b0", index=0, writes={"undeclared": "x"}),
                Contribution(branch="b1", index=1, writes={"undeclared": "y"}),
            ),
        )
    assert "undeclared" in str(raised.value)


def test_a_single_writer_key_names_both_branches_when_two_write_it() -> None:
    policy = MergePolicy({"answer": "single_writer"})
    with pytest.raises(ConcurrentWriteError) as raised:
        policy.merge(
            {},
            (
                Contribution(branch="b0", index=0, writes={"answer": "left"}),
                Contribution(branch="b1", index=1, writes={"answer": "right"}),
            ),
        )
    message = str(raised.value)
    assert "b0" in message and "b1" in message and "answer" in message


def test_one_writer_on_a_single_writer_key_is_the_ordinary_case() -> None:
    policy = MergePolicy({"answer": "single_writer"})
    merged = policy.merge(
        {"answer": None},
        (Contribution(branch="b0", index=0, writes={"answer": "left"}),),
    )
    assert merged["answer"] == "left"


def test_merge_is_deterministic_in_declared_order_not_arrival_order() -> None:
    """Two arrival orders, one result. The order that decides is the index."""
    policy = MergePolicy({"log": "append_in_declared_order"})
    first = Contribution(branch="b0", index=0, writes={"log": ["a"]})
    second = Contribution(branch="b1", index=1, writes={"log": ["b"]})

    forwards = policy.merge({}, (first, second))
    backwards = policy.merge({}, (second, first))
    assert forwards == backwards
    assert forwards["log"] == ["a", "b"]
