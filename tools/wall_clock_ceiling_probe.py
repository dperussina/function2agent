"""A planted case for FR-005's wall-clock ceiling, with three controls.

**Why this exists rather than a reading of `src/runtime/loop.py`.** The question
is whether the wall-clock ceiling *fires*, and that is a claim about behaviour.
`tools/README.md`'s rule — *reading an instrument is not measuring it, plant the
case instead* — names two occasions on which a defect asserted from source did
not exist. So this probe runs a real `AgentLoop` against a real store, with a
tool that sleeps, under a wall-clock ceiling far smaller than the session's own
duration, and reports what the session actually terminated on.

**A run in which nothing fires proves nothing on its own**, which is why three of
the five arms are controls on the same harness: `turns`, `tokens` and `spend`
each get the same absurd treatment and must terminate on their own named member
of FR-006's taxonomy. If the controls fire and the wall-clock arm does not, the
difference is the dimension and not the harness.

The fifth arm is the interesting one for the *enforcement* question rather than
the *measurement* one: it sets a non-zero reservation on the wall-clock
dimension, so the estimate channel — the only channel that writes this dimension
at all — has something in it. What that arm terminates on is the difference
between "no enforcement" and "enforcement by estimate".

Every arm runs to a hard turn cap so that a session which never hits any ceiling
still stops; an arm that reports `MODEL_EXHAUSTED` ran out of script rather than
hitting a bound, and that is a distinct outcome from a ceiling firing.

Usage: `.venv/bin/python tools/wall_clock_ceiling_probe.py [arm ...]`
"""

from __future__ import annotations

import json
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parents[1]))

from src.contracts.repository import Repository  # noqa: E402
from src.runtime.dispatch import ToolCall  # noqa: E402
from src.runtime.journal import TurnJournal  # noqa: E402
from src.runtime.ledger import BudgetLedger, ReservationPolicy  # noqa: E402
from src.runtime.loop import AgentLoop, ModelResponse  # noqa: E402
from src.runtime.result_bound import ResultBound, RetentionStore  # noqa: E402
from src.runtime.session_state import SessionStateMachine  # noqa: E402
from src.runtime.session_store import Ceilings, SessionStore  # noqa: E402
from src.runtime.trace import ArtifactVersions, SpanWriter  # noqa: E402
from src.runtime.trace_budget import BudgetJournal  # noqa: E402
from src.supervisor.session_table import (  # noqa: E402
    SessionTable,
    capability_digest,
)

TENANT = "t-1"
DEPLOYMENT = "d-1"
LEASE = 2_000_000_000.0
SESSION = "s-wall"

SPEND_PER_TURN = 0.03
TOKENS_PER_TURN = 7

# Loose enough that only the dimension under test can fire.
LOOSE = Ceilings(spend_usd=1000.0, tokens=10_000_000,
                 wall_clock_seconds=1e12, turns=500)


@dataclass(frozen=True)
class Arm:
    name: str
    ceilings: Ceilings
    reserve_wall_clock: float
    sleep_seconds: float
    turns: int
    expect: str
    why: str


def _replace(base: Ceilings, **kw) -> Ceilings:
    fields = {
        "spend_usd": base.spend_usd, "tokens": base.tokens,
        "wall_clock_seconds": base.wall_clock_seconds, "turns": base.turns,
    }
    fields.update(kw)
    return Ceilings(**fields)


ARMS: tuple[Arm, ...] = (
    Arm(
        name="wall-clock-tight",
        ceilings=_replace(LOOSE, wall_clock_seconds=0.001),
        reserve_wall_clock=0.0,
        sleep_seconds=0.4,
        turns=6,
        expect="terminated.wall_clock_ceiling_reached",
        why="the session sleeps for seconds under a ceiling of one millisecond",
    ),
    Arm(
        name="wall-clock-tight-with-reservation",
        ceilings=_replace(LOOSE, wall_clock_seconds=0.001),
        reserve_wall_clock=0.5,
        sleep_seconds=0.4,
        turns=6,
        expect="terminated.wall_clock_ceiling_reached",
        why="the estimate channel alone already exceeds the ceiling 500-fold",
    ),
    Arm(
        name="wall-clock-absurd-reservation",
        ceilings=_replace(LOOSE, wall_clock_seconds=0.001),
        reserve_wall_clock=1e9,
        sleep_seconds=0.4,
        turns=6,
        expect="terminated.wall_clock_ceiling_reached",
        why="closes the magnitude explanation — a reservation of 10^9 seconds "
            "against a ceiling of 10^-3 cannot be too small to notice",
    ),
    Arm(
        name="wall-clock-zero-ceiling",
        ceilings=_replace(LOOSE, wall_clock_seconds=0.0),
        reserve_wall_clock=0.0,
        sleep_seconds=0.4,
        turns=6,
        expect="terminated.wall_clock_ceiling_reached",
        why="CONTROL ON THE COMPARISON — `evaluate_ceilings` is `>=`, so a "
            "total of 0.0 trips a ceiling of 0.0. If this fires, the "
            "comparison is wired to the dimension and it is the numerator "
            "that is dead, not the check",
    ),
    Arm(
        name="turns-tight",
        ceilings=_replace(LOOSE, turns=2),
        reserve_wall_clock=0.0,
        sleep_seconds=0.4,
        turns=6,
        expect="terminated.turn_ceiling_reached",
        why="CONTROL — the same harness, the same sleeping tool, a tight turn "
            "ceiling",
    ),
    Arm(
        name="tokens-tight",
        ceilings=_replace(LOOSE, tokens=8),
        reserve_wall_clock=0.0,
        sleep_seconds=0.4,
        turns=6,
        expect="terminated.token_ceiling_reached",
        why="CONTROL — one turn's tokens plus the reservation clears 8",
    ),
    Arm(
        name="spend-tight",
        ceilings=_replace(LOOSE, spend_usd=0.05),
        reserve_wall_clock=0.0,
        sleep_seconds=0.4,
        turns=6,
        expect="terminated.spend_ceiling_reached",
        why="CONTROL — two turns at $0.03 clears $0.05",
    ),
)


class Probe:
    """One arm: a real loop, a real store, a tool that actually takes time."""

    def __init__(self, arm: Arm, root: Path) -> None:
        self.arm = arm
        self.root = root
        self.clock = time.time
        self.model_calls = 0
        self.tool_calls = 0

    def build(self) -> AgentLoop:
        lifecycle = SessionTable(self.root / "session.sqlite3")
        lifecycle.create(
            session_id=SESSION, tenant_id=TENANT, deployment_id=DEPLOYMENT,
            capability_sha256=capability_digest("h"),
            lease_expires_at=LEASE, now=self.clock())
        repo = Repository(self.root / "runtime.sqlite3", role="runtime",
                          tenant_id=TENANT, deployment_id=DEPLOYMENT)
        store = SessionStore(repo, lifecycle=lifecycle)
        store.create(session_id=SESSION, ceilings=self.arm.ceilings)
        self.lifecycle = lifecycle
        self.repo = repo
        self.budget = BudgetLedger(
            BudgetJournal(repo, session_root=self.root / "session-root"),
            policy=ReservationPolicy(
                spend_usd=0.01, tokens=3,
                wall_clock_seconds=self.arm.reserve_wall_clock))
        self.machine = SessionStateMachine(lifecycle)
        return AgentLoop(
            session_id=SESSION,
            store=store,
            budget=self.budget,
            journal=TurnJournal(repo),
            spans=SpanWriter(repo),
            machine=self.machine,
            bound=ResultBound(bound_tokens=400, context_window_tokens=40_000),
            retention=RetentionStore(root=self.root / "scratch",
                                     session_id=SESSION, max_bytes=1_000_000),
            model=self.model,
            execute=self.execute,
            versions=ArtifactVersions(
                TENANT, DEPLOYMENT, {"prompt": "sha256:" + "0" * 64}),
            clock=self.clock,
        )

    def model(self, context) -> ModelResponse:
        turn = self.model_calls
        self.model_calls += 1
        if turn >= self.arm.turns - 1:
            # The hard stop. Reaching it means no ceiling fired.
            return ModelResponse(
                provider="probe", provider_state=None,
                text=f"MODEL_EXHAUSTED after {turn + 1} turns", tool_calls=(),
                spend_usd=SPEND_PER_TURN, tokens=TOKENS_PER_TURN)
        return ModelResponse(
            provider="probe", provider_state=None, text="",
            tool_calls=(ToolCall(index=0, call_id=f"t{turn}c0", name="sleeper"),),
            spend_usd=SPEND_PER_TURN, tokens=TOKENS_PER_TURN)

    def execute(self, call: ToolCall) -> str:
        """The tool that makes this a wall-clock question at all.

        It sleeps. Nothing else in the fixture corpus does, which is why the
        existing wall-clock arm could not have distinguished a ceiling that
        does not fire from a session that was simply too fast to trip it.
        """
        self.tool_calls += 1
        time.sleep(self.arm.sleep_seconds)
        return f"slept {self.arm.sleep_seconds}s in {call.call_id}"

    def run(self) -> dict:
        loop = self.build()
        self.machine.start(SESSION, at=self.clock())
        started = time.monotonic()
        outcome = loop.run("prompt")
        elapsed = time.monotonic() - started
        totals = self.budget.totals(SESSION)
        committed = self.budget.committed(SESSION)
        record = {
            "arm": self.arm.name,
            "why": self.arm.why,
            "ceiling_wall_clock_seconds": self.arm.ceilings.wall_clock_seconds,
            "ceiling_turns": self.arm.ceilings.turns,
            "ceiling_tokens": self.arm.ceilings.tokens,
            "ceiling_spend_usd": self.arm.ceilings.spend_usd,
            "reserved_wall_clock_per_turn": self.arm.reserve_wall_clock,
            "measured_elapsed_seconds": round(elapsed, 3),
            "tool_calls_that_slept": self.tool_calls,
            "terminal_state": outcome.terminal_state,
            "expected_terminal_state": self.arm.expect,
            "fired_as_expected": outcome.terminal_state == self.arm.expect,
            "ledger_total_wall_clock_seconds": totals.wall_clock_seconds,
            "ledger_committed_wall_clock_seconds": committed.wall_clock_seconds,
            "ledger_total_turns": totals.turns,
            "ledger_total_tokens": totals.tokens,
            "ledger_total_spend_usd": round(totals.spend_usd, 6),
        }
        self.repo.close()
        self.lifecycle.close()
        return record


def main(argv: list[str]) -> int:
    wanted = set(argv)
    arms = [a for a in ARMS if not wanted or a.name in wanted]
    if not arms:
        print(f"no arm matches {sorted(wanted)}; declared arms are "
              f"{[a.name for a in ARMS]}", file=sys.stderr)
        return 2
    failures = 0
    for arm in arms:
        with tempfile.TemporaryDirectory() as tmp:
            record = Probe(arm, Path(tmp)).run()
        print(json.dumps(record, indent=2), flush=True)
        if not record["fired_as_expected"]:
            failures += 1
    print(f"\n{len(arms) - failures}/{len(arms)} arms terminated on the "
          f"dimension the arm made absurd.", flush=True)
    # Exit 0 regardless: this is an observation tool, and an arm that does not
    # fire is the reading rather than a tool failure. The count above is what
    # a reader acts on.
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
