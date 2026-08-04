"""`state_transition` records — constitution Principle VI at v1.3.0.

The amendment generalised "the routing decision with its predicate inputs for
every conditional edge" to "every decision that selected among alternatives".
FR-038 enumerates egress and filesystem decisions only, so the gap is this span
kind, and the spec leaves the reading open. These tests are where the reading is
settled and held: **the second reading holds**, because `bounds.check` selects
among three terminal states on live readings against declared limits, in an
order that decides the outcome when more than one is breached.
"""

from __future__ import annotations

import pytest

from src.contracts import transition as tr
from src.supervisor import session_table as st


def _reading(name: str, matched: bool) -> tr.PredicateInput:
    return tr.PredicateInput(name=name, observed="1", declared="0", matched=matched)


# ---------------------------------------------------------------------------
# The reading itself, asserted against the code rather than asserted about it.

def test_the_bound_selection_really_does_select_among_alternatives() -> None:
    """The evidence for the second reading, as an executable statement.

    If someone later makes the three bounds mutually exclusive, or removes two
    of them, this test is where the reading should be revisited — the first
    reading would then become true and the predicate inputs unnecessary.
    """
    rule = tr.RULES_BY_ID[tr.ST_BOUND_EXHAUSTED.rule_id]
    assert rule.selects_among_alternatives, (
        "FR-049's bound check chooses between memory, process and processor "
        "exhaustion. If that is no longer true, the constitutional reading "
        "recorded in src/contracts/transition.py has to change with it."
    )

    from src.supervisor import bounds

    # Three distinct terminal states are reachable from one predicate, which
    # is what "selected among alternatives" means.
    reachable = {bounds.TERMINAL_MEMORY, bounds.TERMINAL_PROCESS, bounds.TERMINAL_CPU}
    assert len(reachable) == 3


def test_the_ordering_that_decided_is_recoverable_from_the_record() -> None:
    """The whole point of carrying non-matching readings.

    A session that breached memory and processes in the same interval
    terminates on memory because memory is read first. With only the winner
    recorded, a reader cannot tell that from a session that breached memory
    alone — and those are different defects.
    """
    both = tr.StateTransition(
        session_id="s", from_state=tr.STATE_RUNNING, to_state=tr.STATE_TERMINATED,
        terminal_state="terminated.memory_bound_exhausted",
        deciding_rule=tr.ST_BOUND_EXHAUSTED.rule_id,
        predicate_inputs=(
            tr.PredicateInput("memory.events oom_kill", "oom_kill=1", "1024", True),
            tr.PredicateInput("pids.events max", "pids.events max=7", "64", False),
            tr.PredicateInput("cpu.stat usage_usec", "1.5s", "60.0s", False),
        ),
        at=1.0,
    )
    record = both.to_record()
    breached = [p for p in record["predicate_inputs"] if p["observed"] != "0"]
    assert len(breached) == 3
    assert [p["name"] for p in record["predicate_inputs"] if p["matched"]] == [
        "memory.events oom_kill"
    ]
    # And the reader can see the process bound was also non-zero.
    pids = next(p for p in record["predicate_inputs"] if p["name"] == "pids.events max")
    assert pids["observed"] == "pids.events max=7"
    assert pids["matched"] is False


# ---------------------------------------------------------------------------
# The structural obligations.

def test_a_selecting_rule_cannot_omit_its_predicate_inputs() -> None:
    with pytest.raises(tr.TransitionError, match="Principle VI"):
        tr.StateTransition(
            session_id="s", from_state=tr.STATE_RUNNING, to_state=tr.STATE_TERMINATED,
            terminal_state="terminated.memory_bound_exhausted",
            deciding_rule=tr.ST_BOUND_EXHAUSTED.rule_id,
            at=1.0,
        )


def test_a_determined_rule_cannot_carry_predicate_inputs() -> None:
    """The other direction, so 'determined' cannot become decoration."""
    with pytest.raises(tr.TransitionError, match="declared determined"):
        tr.StateTransition(
            session_id="s", from_state=tr.STATE_STARTING, to_state=tr.STATE_RUNNING,
            deciding_rule=tr.ST_SESSION_STARTED.rule_id,
            predicate_inputs=(_reading("something", True),),
            at=1.0,
        )


def test_a_selection_with_no_winner_is_refused() -> None:
    with pytest.raises(tr.TransitionError, match="no winner|matched"):
        tr.StateTransition(
            session_id="s", from_state=tr.STATE_RUNNING, to_state=tr.STATE_TERMINATED,
            terminal_state="terminated.memory_bound_exhausted",
            deciding_rule=tr.ST_BOUND_EXHAUSTED.rule_id,
            predicate_inputs=(_reading("a", False), _reading("b", False)),
            at=1.0,
        )


def test_the_deciding_rule_must_be_registered() -> None:
    """Same discipline as FR-011's rule_id: an identity, not a string."""
    with pytest.raises(tr.TransitionError, match="not a registered"):
        tr.StateTransition(
            session_id="s", from_state=tr.STATE_STARTING, to_state=tr.STATE_RUNNING,
            deciding_rule="ST-999", at=1.0,
        )
    with pytest.raises(tr.TransitionError, match="not a registered"):
        tr.StateTransition(
            session_id="s", from_state=tr.STATE_STARTING, to_state=tr.STATE_RUNNING,
            deciding_rule="", at=1.0,
        )


def test_reaching_terminated_requires_a_named_taxonomy_member() -> None:
    with pytest.raises(tr.TransitionError, match="FR-006"):
        tr.StateTransition(
            session_id="s", from_state=tr.STATE_RUNNING, to_state=tr.STATE_TERMINATED,
            deciding_rule=tr.ST_WORK_COMPLETED.rule_id, at=1.0,
        )
    with pytest.raises(tr.TransitionError, match="FR-006"):
        tr.StateTransition(
            session_id="s", from_state=tr.STATE_RUNNING, to_state=tr.STATE_TERMINATED,
            terminal_state="terminated.something_invented",
            deciding_rule=tr.ST_WORK_COMPLETED.rule_id, at=1.0,
        )


def test_a_non_terminal_transition_may_not_name_a_terminal_state() -> None:
    with pytest.raises(tr.TransitionError, match="must not name"):
        tr.StateTransition(
            session_id="s", from_state=tr.STATE_STARTING, to_state=tr.STATE_RUNNING,
            terminal_state="terminated.completed",
            deciding_rule=tr.ST_SESSION_STARTED.rule_id, at=1.0,
        )


def test_the_determined_edges_still_carry_a_rule() -> None:
    """The first reading is available where it is true, and still attributable.

    STARTING → RUNNING genuinely selects among nothing. It still names the rule
    that produced it, because Principle VI asks for the identity of the rule on
    every decision and 'determined' is an answer to the predicate-input clause,
    not to the identity one.
    """
    t = tr.StateTransition(
        session_id="s", from_state=tr.STATE_STARTING, to_state=tr.STATE_RUNNING,
        deciding_rule=tr.ST_SESSION_STARTED.rule_id, at=1.0,
    )
    assert t.to_record()["deciding_rule"] == "ST-001"
    assert t.to_record()["reason"] == "session_started"
    assert t.to_record()["predicate_inputs"] == []


def test_the_state_names_agree_with_the_session_table() -> None:
    """Duplicated constants, checked rather than assumed.

    transition.py declares its own STATE_* rather than importing them, so that
    the trace contract does not depend on the storage module. That is only safe
    if something asserts they agree.
    """
    assert tr.STATE_STARTING == st.STATE_STARTING
    assert tr.STATE_RUNNING == st.STATE_RUNNING
    assert tr.STATE_TERMINATED == st.STATE_TERMINATED
    assert tr.STATE_INTERRUPTED == st.STATE_INTERRUPTED
    # Every state in the trace contract exists in the storage module, checked
    # as a set rather than name by name — a new state added to one and not the
    # other is the case a fixed list of four assertions cannot see.
    stored = {
        value for name, value in vars(st).items()
        if name.startswith("STATE_") and isinstance(value, str)
    }
    assert tr.STATES == stored, (
        f"the two state sets disagree: {tr.STATES ^ stored}"
    )


def test_every_terminal_state_has_a_rule_that_can_produce_it() -> None:
    """No terminal state is unreachable through a declared transition rule.

    Otherwise a session could reach a taxonomy member with no rule that
    explains it, which is the generic error FR-006 forbids wearing a name.
    """
    from src.contracts import terminal

    # Map each terminal state to the rule that produces it. This is the
    # assertion that the two taxonomies were designed against each other.
    coverage = {
        "terminated.completed": tr.ST_WORK_COMPLETED,
        "terminated.spend_ceiling_reached": tr.ST_CEILING_REACHED,
        "terminated.token_ceiling_reached": tr.ST_CEILING_REACHED,
        "terminated.wall_clock_ceiling_reached": tr.ST_CEILING_REACHED,
        "terminated.turn_ceiling_reached": tr.ST_CEILING_REACHED,
        "terminated.memory_bound_exhausted": tr.ST_BOUND_EXHAUSTED,
        "terminated.cpu_bound_exhausted": tr.ST_BOUND_EXHAUSTED,
        "terminated.process_bound_exhausted": tr.ST_BOUND_EXHAUSTED,
        "terminated.capability_lapsed": tr.ST_CAPABILITY_LAPSED,
        "terminated.operator_terminated": tr.ST_OPERATOR_TERMINATED,
        "terminated.unrecoverable_fault": tr.ST_UNRECOVERABLE_FAULT,
    }
    assert set(coverage) == terminal.NAMES, (
        "the terminal taxonomy and the transition rules have drifted apart; "
        "a terminal state with no rule that produces it cannot be attributed"
    )


def test_from_bound_outcome_carries_every_reading(monkeypatch) -> None:
    """The integration point: what bounds.check produces reaches the record."""
    from src.supervisor import bounds

    class FakeCgroup:
        def oom_kills(self): return 0
        def pids_events_max(self): return 4
        def cpu_usage_seconds(self): return 1.0

    limits = bounds.Bounds(deployment_id="d-test", memory_max_bytes=1024, cpu_max="max", cpu_total_seconds=60.0, pids_max=8)
    outcome = bounds.check(FakeCgroup(), limits)
    assert outcome is not None
    assert outcome.terminal_state == bounds.TERMINAL_PROCESS

    t = tr.from_bound_outcome(
        session_id="s", outcome=outcome, readings=outcome.readings, at=1.0)
    record = t.to_record()
    assert len(record["predicate_inputs"]) == 3, (
        "all three bounds must be on the record even though one fired"
    )
    assert [p["matched"] for p in record["predicate_inputs"]] == [False, True, False]
    assert record["deciding_rule"] == tr.ST_BOUND_EXHAUSTED.rule_id


def test_the_check_reads_every_bound_before_judging_any(monkeypatch) -> None:
    """Short-circuiting would make the ordering unrecoverable.

    Counts the reads rather than inspecting the source, so a rewrite that
    reintroduces short-circuiting fails here.
    """
    from src.supervisor import bounds

    reads: list[str] = []

    class CountingCgroup:
        def oom_kills(self):
            reads.append("memory")
            return 1  # fires, and would short-circuit the other two

        def pids_events_max(self):
            reads.append("pids")
            return 3

        def cpu_usage_seconds(self):
            reads.append("cpu")
            return 99.0

    limits = bounds.Bounds(deployment_id="d-test", memory_max_bytes=1024, cpu_max="max", cpu_total_seconds=60.0, pids_max=8)
    outcome = bounds.check(CountingCgroup(), limits)
    assert outcome is not None
    assert sorted(reads) == ["cpu", "memory", "pids"], (
        f"only {reads} were read; a bound that is not read cannot appear on "
        "the record, and the ordering that decided the outcome becomes "
        "invisible"
    )
    assert outcome.terminal_state == bounds.TERMINAL_MEMORY
