"""T065 — the call-count backstop, and the independence that is the whole point of it.

Four families, and the third is the one this file exists for.

**It counts, and it counts off disk.** A backstop holding its own integer is a
backstop a resume resets, and finding 006 measured exactly that: *"an agent that
crashes and resumes in a retry loop has no effective ceiling at all."* So the
count is a read of the journal, and the tests below crash the counter and read
it again.

**It cannot be widened.** `research/02`'s measurement of the removed dependency
is that its ceiling *defaulted to `None`*, and unbounded-by-default is the
failure this occupies the position of. So the maximum has no environment key, is
refused above the sourced figure, and refuses a caller who tries.

**It does not read the cost table — proved by planting, not by reading.** The
static half walks this module's imports. The static half is not sufficient on
its own: an import is one of several ways to reach another module, and a test
that only reads source is a test that describes behaviour rather than observing
it. So the dynamic half empties `costs.PRICES`, makes `price_usd` raise on
everything, and asserts the backstop is unmoved. `tests/removal_proofs.sh`
carries the same case as a tamper.

**It is distinguishable from the ceiling it backs up.** A backstop that can only
fire when FR-005's turn ceiling would also have fired is not a second guard, it
is the first one counted twice. So the loop arm sets every configured ceiling
out of reach and asserts the backstop still stops the run.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

import tests.unit.test_loop as loop_fixtures
from src.runtime import budget_backstop
from src.runtime.providers.costs import PROVENANCE_OPERATOR
from src.runtime.budget_backstop import (
    MAX_MODEL_CALLS,
    BackstopError,
    BackstopTripped,
    CallCountBackstop,
)
from src.runtime.journal import (
    MODEL_STEP_INDEX,
    STEP_MODEL_CALL,
    STEP_TOOL_CALL,
    TurnJournal,
    tool_step_index,
)

SESSION = "s-backstop"


def _repository(tmp_path):
    from src.contracts.ownership import ROLE_RUNTIME
    from src.contracts.repository import Repository

    return Repository(tmp_path / "runtime.db", role=ROLE_RUNTIME,
                      tenant_id="t", deployment_id="d")


def _make_journal(tmp_path) -> TurnJournal:
    return TurnJournal(_repository(tmp_path))


def _model_call(journal: TurnJournal, session_id: str, turn: int) -> None:
    journal.intend(
        session_id=session_id, turn_index=turn, step_index=MODEL_STEP_INDEX,
        step_kind=STEP_MODEL_CALL, effect_id="model",
        effectful=True, payload={"prompt": "x"}, at=1.0)


def _tool_call(journal: TurnJournal, session_id: str, turn: int,
               declared: int = 0) -> None:
    journal.intend(
        session_id=session_id, turn_index=turn,
        step_index=tool_step_index(declared),
        step_kind=STEP_TOOL_CALL, effect_id=f"c{declared}",
        effectful=True, payload={"tool": "t"}, at=1.0)


# ---------------------------------------------------------------------------
# The count itself, and where it comes from.


def test_a_fresh_session_has_made_no_calls(tmp_path) -> None:
    backstop = CallCountBackstop(_make_journal(tmp_path))
    assert backstop.calls_made(SESSION) == 0
    backstop.check(SESSION)  # does not raise


def test_the_count_is_the_journal_and_not_a_counter_here(tmp_path) -> None:
    """The durability property, asserted by discarding the object.

    A second `CallCountBackstop` over the same store reads the same number. An
    implementation keeping its own integer passes every other test in this file
    and fails this one, which is the point of it being separate.
    """
    journal = _make_journal(tmp_path)
    first = CallCountBackstop(journal)
    for turn in range(3):
        _model_call(journal, SESSION, turn)
    assert first.calls_made(SESSION) == 3

    reopened = CallCountBackstop(TurnJournal(journal.repo))
    assert reopened.calls_made(SESSION) == 3, (
        "the count did not survive a new object over the same store, so it is "
        "held in memory and a resume resets it — finding 006's 'no effective "
        "ceiling at all'"
    )


def test_tool_calls_are_not_counted(tmp_path) -> None:
    """The metric is model calls. A turn with eight tool calls is one call.

    Counting steps rather than model calls would make the backstop fire on
    tool-heavy work that spends almost nothing, and the operator would raise
    it — which is how a backstop gets disabled.
    """
    journal = _make_journal(tmp_path)
    _model_call(journal, SESSION, 0)
    for declared in range(8):
        _tool_call(journal, SESSION, 0, declared)
    assert CallCountBackstop(journal).calls_made(SESSION) == 1


def test_another_sessions_calls_are_not_counted(tmp_path) -> None:
    journal = _make_journal(tmp_path)
    for turn in range(5):
        _model_call(journal, "other", turn)
    _model_call(journal, SESSION, 0)
    assert CallCountBackstop(journal).calls_made(SESSION) == 1


def test_an_intent_with_no_outcome_still_counts(tmp_path) -> None:
    """The over-counting direction, and the same argument `ledger.py` makes.

    The loop journals the intent *before* the call, so a row with no outcome is
    a call that may have reached the provider. Counting it is too much rather
    than too little, and only one of those two errors lets a run continue past
    the backstop.
    """
    journal = _make_journal(tmp_path)
    _model_call(journal, SESSION, 0)
    step = journal.step(SESSION, 0, MODEL_STEP_INDEX)
    assert step is not None and step.outcome is None
    assert CallCountBackstop(journal).calls_made(SESSION) == 1


# ---------------------------------------------------------------------------
# The maximum, and that it cannot be widened.


def test_the_maximum_is_low_and_sourced() -> None:
    """Asserted as a bound rather than as equality, so the sourced figure can
    move without this test dictating it — but not to a number that stops being
    a backstop."""
    assert 1 <= MAX_MODEL_CALLS <= 20, (
        f"the backstop's maximum is {MAX_MODEL_CALLS}. T065 asks for a *low* "
        "call count; the only published figure for this exact ceiling is "
        "Anthropic's max_iterations <= 20 (research/13 §4.4)."
    )


def test_the_maximum_cannot_be_raised(tmp_path) -> None:
    """The measured failure this exists to not repeat.

    research/02 measured the removed dependency's ceiling defaulting to `None`.
    A backstop an operator can widen is that ceiling with more steps, so the
    constructor takes a maximum that may only go *down*.
    """
    journal = _make_journal(tmp_path)
    with pytest.raises(BackstopError, match="cannot be raised"):
        CallCountBackstop(journal, maximum=MAX_MODEL_CALLS + 1)


def test_the_maximum_may_be_lowered(tmp_path) -> None:
    journal = _make_journal(tmp_path)
    assert CallCountBackstop(journal, maximum=2).maximum == 2


@pytest.mark.parametrize("bad", [0, -1, None, 2.5, "3", True])
def test_a_maximum_that_is_not_a_positive_integer_is_refused(tmp_path, bad) -> None:
    """`None` is in this list on purpose: it is the removed dependency's actual
    default, and it is the one value that must not read as 'no limit'."""
    journal = _make_journal(tmp_path)
    with pytest.raises(BackstopError):
        CallCountBackstop(journal, maximum=bad)


def test_the_backstop_reads_no_environment_variable() -> None:
    """Enumerated over the source, because a key added later would silently
    reintroduce the widening this module refuses in its constructor."""
    tree = ast.parse(pathlib.Path(budget_backstop.__file__).read_text())
    # Over the *code*, not the file. A substring scan would trip on the module
    # docstring, which says at length that there is no environment key — and a
    # test that a file does not contain a word is a test that forbids
    # explaining why.
    names = {node.attr for node in ast.walk(tree)
             if isinstance(node, ast.Attribute)}
    names |= {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.add(node.module or "")
    offenders = names & {"os", "environ", "getenv", "dotenv", "config",
                         "load_config", "Settings"}
    assert not offenders, (
        f"the backstop reads configuration: {sorted(offenders)}. A maximum the "
        "same channel supplies is not a backstop for that channel."
    )


# ---------------------------------------------------------------------------
# Firing.


def test_it_does_not_fire_below_the_maximum(tmp_path) -> None:
    journal = _make_journal(tmp_path)
    backstop = CallCountBackstop(journal, maximum=3)
    for turn in range(2):
        _model_call(journal, SESSION, turn)
    backstop.check(SESSION)
    assert backstop.remaining(SESSION) == 1


def test_it_fires_at_the_maximum_not_one_past_it(tmp_path) -> None:
    """The off-by-one, asserted from both sides.

    `check` runs at the *top* of a turn, before the call it is guarding. So the
    call that would be the (maximum + 1)-th must be refused, which means
    `check` refuses once `maximum` calls are already on disk.
    """
    journal = _make_journal(tmp_path)
    backstop = CallCountBackstop(journal, maximum=3)
    for turn in range(2):
        _model_call(journal, SESSION, turn)
    backstop.check(SESSION)

    _model_call(journal, SESSION, 2)
    with pytest.raises(BackstopTripped):
        backstop.check(SESSION)
    assert backstop.remaining(SESSION) == 0


def test_the_refusal_names_the_count_the_maximum_and_the_session(tmp_path) -> None:
    journal = _make_journal(tmp_path)
    backstop = CallCountBackstop(journal, maximum=1)
    _model_call(journal, SESSION, 0)
    with pytest.raises(BackstopTripped) as caught:
        backstop.check(SESSION)
    message = str(caught.value)
    for expected in (SESSION, "1"):
        assert expected in message
    assert "spend" in message, (
        "the refusal does not say that a call count is not a spend figure. "
        "research/14 §5 measured a 40x context spread between runtimes for "
        "identical work, so an operator reading this as 'you spent 20 calls' "
        "will size the next ceiling from it and be wrong by that ratio."
    )


def test_remaining_never_goes_negative(tmp_path) -> None:
    journal = _make_journal(tmp_path)
    backstop = CallCountBackstop(journal, maximum=1)
    for turn in range(4):
        _model_call(journal, SESSION, turn)
    assert backstop.remaining(SESSION) == 0


def test_the_backstop_survives_the_crash_that_resets_a_counter(tmp_path) -> None:
    """Finding 006's case, run rather than cited.

    The object is discarded between the calls and the check, which is what a
    `SIGKILL` and a resume do to anything held in memory.
    """
    journal = _make_journal(tmp_path)
    for turn in range(3):
        _model_call(journal, SESSION, turn)
    del journal

    resumed = CallCountBackstop(TurnJournal(_repository(tmp_path)), maximum=3)
    with pytest.raises(BackstopTripped):
        resumed.check(SESSION)


# ---------------------------------------------------------------------------
# T065's actual subject: independence from the cost table.


def test_the_backstop_imports_nothing_from_the_cost_table() -> None:
    """The static half. Necessary, and on its own not sufficient — see the
    planted case below."""
    tree = ast.parse(pathlib.Path(budget_backstop.__file__).read_text())
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
            imported.update(f"{node.module}.{a.name}" for a in node.names)
    offenders = {name for name in imported if "cost" in name or "ledger" in name
                 or "trace_budget" in name}
    assert not offenders, (
        f"the backstop imports {sorted(offenders)}. T065's stated purpose is "
        "that a missing price cannot remove every ceiling at once, which it "
        "can if this module is downstream of the priced one."
    )


def test_the_backstop_fires_with_the_cost_table_emptied(tmp_path, monkeypatch) -> None:
    """The planted half. The table is emptied *and* the entry point is made to
    raise, because either alone leaves the other path untested."""
    from src.runtime.providers import costs

    monkeypatch.setattr(costs, "PRICES", {})

    def refuse(**_: object) -> float:
        raise costs.MissingPriceError("planted: nothing is priced")

    monkeypatch.setattr(costs, "price_usd", refuse)
    monkeypatch.setattr(costs, "reservation_spend_usd", refuse)
    assert costs.priced_models() == frozenset()
    with pytest.raises(costs.MissingPriceError):
        costs.price_usd(provider="anthropic", model="claude-opus-5",
                        input_tokens=1, output_tokens=1, as_of=None)

    journal = _make_journal(tmp_path)
    backstop = CallCountBackstop(journal, maximum=2)
    for turn in range(2):
        _model_call(journal, SESSION, turn)
    with pytest.raises(BackstopTripped):
        backstop.check(SESSION)


def test_the_backstop_does_not_consult_the_budget_ledger(tmp_path) -> None:
    """Independence from the *other* thing a missing price disables.

    A price that cannot be computed is a spend total that stays at zero. If the
    backstop asked the ledger anything, it would be reading that zero.
    """
    journal = _make_journal(tmp_path)
    backstop = CallCountBackstop(journal, maximum=1)
    _model_call(journal, SESSION, 0)
    with pytest.raises(BackstopTripped):
        backstop.check(SESSION)


# ---------------------------------------------------------------------------
# In the loop, with FR-005's four ceilings put out of reach.


class StubExhausted(RuntimeError):
    """The stub was asked for a turn that no correctly-wired ceiling permits.

    Deliberately not a `BackstopTripped` and deliberately not caught: it exists
    to make the arm below fail, and a guard the assertion could mistake for the
    mechanism would be worse than no guard at all.
    """


# Ten times the largest maximum `CallCountBackstop.__init__` will accept — it
# refuses anything above `MAX_MODEL_CALLS` — so no correctly-configured backstop
# can reach this, and the untampered path never sees it. Tied to the constant
# rather than written as a literal so that raising the sourced figure cannot
# quietly move the guard underneath the thing it is guarding.
_STUB_GUARD = MAX_MODEL_CALLS * 10


def _runaway_loop(harness, *, backstop, guard_at: int = _STUB_GUARD):
    """A loop whose provider always asks for another tool, so only a ceiling
    stops it — and a provider that counts, so a *removed* ceiling stops the
    test rather than the machine.

    **The counter is not scaffolding; it is what makes the arm below provable.**
    Without it the loop had no terminator of any kind once its backstop was
    disarmed, which is the exact configuration `tests/removal_proofs.sh` puts it
    in: the tamper for "T065 wiring" replaces `if pending_turn is None:` with
    `if False:`, removing the only `backstop.check` call, while the arm's own
    ceilings are all set out of reach on purpose. A test with nothing left to
    stop it cannot fail. It can only not return — and `proof()` reads a
    non-return as neither proved nor unproven but as nothing at all, so the run
    hangs. Measured on 2026-08-05 at `1208e06` with the tamper applied by hand:
    no return in 90s, and a concurrent pass recorded 56 minutes of continuous
    CPU on the same arm.

    So the provider refuses past `guard_at`. Untampered, the backstop trips at
    its maximum and this is never reached. Tampered, it raises,
    `pytest.raises(BackstopTripped)` does not match it, and the arm fails in
    seconds — which is what the proof needed all along.
    """
    from src.runtime.loop import AgentLoop
    from src.runtime.turn import ModelResponse, ToolCall

    asked = {"n": 0}

    def model(_context):
        asked["n"] += 1
        if asked["n"] > guard_at:
            raise StubExhausted(
                f"the stub provider was asked for model call {asked['n']}, past "
                f"the {guard_at} it will answer. Nothing stopped this loop: the "
                f"backstop is the only guard configured to reach, and it did "
                f"not. Failing here rather than running forever."
            )
        # `spend_usd=0.0` stated, not defaulted: the default means *unpriced*
        # and the loop refuses it, which would stop this session for the wrong
        # reason. The point of this arm is that the **backstop** stops it while
        # every configured ceiling is out of reach.
        return ModelResponse(
            provider="test", provider_state=b"s", text="more", spend_usd=0.0,
            spend_provenance=PROVENANCE_OPERATOR,
            tool_calls=(ToolCall(call_id=f"c{asked['n']}", name="t",
                                 arguments={}, index=0),))

    counter = {"n": 0.0}

    def clock() -> float:
        counter["n"] += 1.0
        return counter["n"]

    return AgentLoop(
        session_id=loop_fixtures.SESSION, store=harness.store,
        budget=harness.budget, journal=harness.journal, spans=harness.spans,
        machine=harness.machine, bound=harness.bound,
        retention=harness.retention, model=model, execute=lambda _call: "ok",
        versions=loop_fixtures.VERSIONS, clock=clock, backstop=backstop)


def test_the_loop_is_stopped_by_the_backstop_with_every_ceiling_out_of_reach(
    tmp_path,
) -> None:
    """The claim that makes this a *second* guard rather than the first one
    counted twice.

    All four of FR-005's ceilings are set where nothing can reach them — which
    is what one bad configuration file looks like — and the loop is still
    stopped. A backstop that could only fire when the turn ceiling would also
    have fired would pass every other test in this file, and
    `tests/removal_proofs.sh` would not be able to tell the two apart.
    """
    harness = loop_fixtures.Harness(tmp_path, ceilings=loop_fixtures._ceilings(
        spend_usd=1e12, tokens=10**12, wall_clock_seconds=1e12, turns=10**9))
    harness.machine.start(loop_fixtures.SESSION, at=1.0)
    try:
        loop = _runaway_loop(harness, backstop=CallCountBackstop(
            harness.journal, maximum=3))
        with pytest.raises(BackstopTripped) as caught:
            loop.run("go")
        assert "3" in str(caught.value)
        # Exactly the permitted number of calls reached the provider, so the
        # backstop stopped the run *before* the fourth rather than after it.
        #
        # This doubles as the statement that `_runaway_loop`'s stub guard took
        # no part in the result: it answers 200 calls and only 3 were asked for,
        # so what stopped this run was the backstop and nothing else. The guard
        # is there for the tampered path, and an arm that could not tell the two
        # apart would be the vacuity the guard was added to prevent.
        assert CallCountBackstop(harness.journal).calls_made(
            loop_fixtures.SESSION) == 3
        assert _STUB_GUARD > 3
    finally:
        harness.close()


def test_the_default_loop_carries_a_backstop_nobody_had_to_pass(tmp_path) -> None:
    """A guard that construction sites opt into is absent from every site that
    predates it, which is how the removed dependency's ceiling defaulted off."""
    harness = loop_fixtures.Harness(tmp_path)
    try:
        loop = _runaway_loop(harness, backstop=None)
        assert isinstance(loop.backstop, CallCountBackstop)
        assert loop.backstop.maximum == MAX_MODEL_CALLS
    finally:
        harness.close()
