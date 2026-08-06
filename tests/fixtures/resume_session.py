"""A session that can be killed at a named point, for T054, T055 and T056.

**Why this is a committed fixture and not three copies of a `textwrap.dedent`
string.** Three batteries need the same thing — a real process that runs real
turns against a real store and stops dead at a chosen instant — and they need it
to be the *same* process shape, because the interesting comparison is between
what one attempt wrote and what the next one does about it. Two nearly-identical
inline children would drift, and the drift would be invisible: both would still
pass, over slightly different sessions.

It is run as a script, from a separate OS process, and killed with `SIGKILL`
delivered by a **third** process. `tests/integration/test_lease_revocation.py`
established that technique and its reason: a signal sent from inside the victim,
or a `sys.exit`, leaves an argument that the victim's runtime cooperated in its
own death. Nothing here runs on the way down — no `finally`, no `atexit`, no
flush — which is the only crash shape that tests FR-007's hard clause.

## The three kill points, and why each is a different test

| `--pause`   | the journal at that instant                              | the question |
| ----------- | -------------------------------------------------------- | ------------ |
| `turn:N`    | turn N-1 complete, turn N *nothing at all*               | does a completed **turn** re-execute? |
| `model:N`   | turn N's model intent and reservation written, no outcome | is the spend counted, or lost? |
| `step:N:K`  | turn N's model done, calls 0..K-1 done, call K performed and unrecorded | does a completed **step** re-execute? |

Those are not three settings of one knob. `turn:N` and `step:N:K` are finding
006's 4-of-4 measurement at the two granularities T052 distinguishes; `model:N`
is the only one of the three at which a **reservation is outstanding when the
process dies**, which is U-30's window and the whole subject of T053.

`step:N:K` deliberately does *not* claim anything about call K itself. Its intent
is on disk and its outcome is not, which the journal's docstring records as the
ambiguous row: the effect may or may not have happened. A resumed attempt runs it
again, and that is correct. The assertion the batteries make is about calls
`0..K-1`, whose outcomes *are* recorded.

## What is written where, and why the parent reads files rather than asking

Three artefacts, all under `--root`, all appended with an `fsync` so a `SIGKILL`
cannot lose the last line:

| file        | one line per                        | read by                        |
| ----------- | ----------------------------------- | ------------------------------ |
| `effects`   | local effect actually performed     | *did a recorded effect repeat* |
| `injected`  | model call, with the state it saw   | T056's opaque-state identity   |
| `attempts`  | process that started                | how many attempts really ran   |

The parent never asks the child what it did. A child reporting its own turn count
is the shape finding 006's defect wore — a count living somewhere an attempt
rebuilds — and a fixture that asked for one would be unable to detect it.

`injected` records the state as **hex**, which is a reversible encoding of the
bytes rather than an interpretation of them: FR-037 forbids the second and says
nothing about the first. `NONE` is a distinct token from the empty string,
because a provider that returned no state and one that returned zero bytes are
different facts and `provider_state` is nullable for that reason. It records the
**whole carried chain**, comma-joined, because `context.provider_states` holds
one entry per kept turn; `-` is the token for a chain with nothing in it.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parents[2]))

from src.contracts.repository import Repository  # noqa: E402
from src.contracts.transition import (  # noqa: E402
    STATE_INTERRUPTED,
    STATE_RUNNING,
    STATE_STARTING,
)
from src.runtime.dispatch import ToolCall  # noqa: E402
from src.runtime.journal import TurnJournal, tool_step_index  # noqa: E402
from src.runtime.ledger import BudgetLedger, ReservationPolicy  # noqa: E402
from src.runtime.loop import AgentLoop, ModelResponse  # noqa: E402
from src.runtime.providers.costs import PROVENANCE_OPERATOR  # noqa: E402
from src.runtime.result_bound import ResultBound, RetentionStore  # noqa: E402
from src.runtime.session_state import SessionStateMachine  # noqa: E402
from src.runtime.session_store import Ceilings, SessionStore  # noqa: E402
from src.runtime.trace import ArtifactVersions, SpanWriter  # noqa: E402
from src.runtime.trace_budget import BudgetJournal  # noqa: E402
from src.supervisor.session_table import SessionTable, capability_digest  # noqa: E402

TENANT = "t-1"
DEPLOYMENT = "d-1"
LEASE = 2_000_000_000.0

# Every attempt spends this much per turn, so the parent can predict a total
# without asking the child. Deliberately not round in binary: a figure like 0.5
# would make a lost accrual and a halved one produce the same total.
SPEND_PER_TURN = 0.03
# OD-27 requires a spend figure to say where its rate came from, and this one
# came from the line above rather than from any vendor's page — which is a
# declaration, and is the state `PROVENANCE_OPERATOR` names. Writing `vendor`
# would be this fixture claiming a source it does not have, in the one field
# that exists to tell those apart.
SPEND_PROVENANCE = PROVENANCE_OPERATOR
TOKENS_PER_TURN = 7
RESERVE_SPEND = 0.01
RESERVE_TOKENS = 3

# How long a paused child waits to be killed before giving up. It is generous
# because the alternative failure — a child that exits on its own and reports a
# clean run — would read as the crash having been survived.
PAUSE_TIMEOUT_SECONDS = 120.0
POLL_SECONDS = 0.005


class Paused(Exception):
    """Raised nowhere. The child never leaves a pause; it is killed there."""


class WorkClock:
    """A clock that moves when the session does work, and not when it is read.

    **Why the fixture needs one, now that the loop accrues elapsed time.** The
    wall-clock arm of T055 has to state how many turn positions its ceiling can
    pay for, and that number has to be *derived* — an expectation copied off a
    run is a change detector. Under `time.time` the figure is a property of how
    fast the machine was, so the arm would assert something about the host and
    pass or fail accordingly. That is the defect this corpus has recorded twice.

    Reading is free and advancing is explicit, so a turn costs
    `step × (1 + tools)` on every machine. It is not a read-counter, which the
    previous comment here rejected and was right to: a counter that moved on
    every read would make the accrued figure a property of how many times the
    loop happened to ask, and a refactor adding one `self.clock()` would change
    the measurement.

    Seeded from the real clock so lease and transition timestamps stay
    plausible and stay ordered across the four processes an arm runs.
    """

    def __init__(self, step: float) -> None:
        self.step = step
        self.t = time.time()

    def __call__(self) -> float:
        return self.t

    def advance(self) -> None:
        self.t += self.step


def _clock(step: float):
    """The real clock, or a work-advanced one when a step is declared.

    `0.0` means `time.time` rather than a `WorkClock` with a zero step: the two
    differ for every arm that is *not* about wall clock, and a frozen clock
    would give every span in a session the same timestamp.
    """
    return time.time if step <= 0.0 else WorkClock(step)


def _append(path: Path, line: str) -> None:
    """Append one line and force it to the platter before returning.

    Without the `fsync` the last few lines live in a buffer the `SIGKILL`
    discards, and the parent would read a file that under-reports what the
    child did — which is the direction that makes a repeated effect look like a
    first one.
    """
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(line + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def state_for(turn: int) -> bytes:
    """Opaque provider state, containing bytes no text codec round-trips.

    `0x80` is a continuation byte with nothing in front of it, so any path that
    decoded this as UTF-8 — or stored it in the JSON payload rather than the
    `provider_state` column — raises rather than quietly substituting U+FFFD.

    **Public, and derived from the turn index rather than random.** T056 imports
    it to compute what a resumed process *should* have been handed, without
    reading anything the run under test wrote. An expectation taken from the
    run's own output would be satisfied by a run that lost the state and
    regenerated it consistently.
    """
    return b"\x00\x80\xfe" + f"turn-{turn}".encode("ascii")


def _hex(state: bytes | None) -> str:
    return "NONE" if state is None else state.hex()


def _hexes(states: "tuple[bytes | None, ...]") -> str:
    """The whole carried chain, comma-joined, `-` when nothing is carried.

    The chain rather than its last element: `context.provider_states` holds one
    entry per kept turn (FR-037, *never dropped*), and a fixture that recorded
    only the last one would report the same line for a resume that rebuilt the
    whole chain off disk and for one that rebuilt a single turn of it.
    """
    return ",".join(_hex(state) for state in states) or "-"


class Child:
    def __init__(self, args: argparse.Namespace) -> None:
        self.root = Path(args.root)
        self.session = args.session
        self.turns = args.turns
        self.tools = args.tools
        self.pause = _parse_pause(args.pause)
        # All three estimates are stated. `ReservationPolicy` refuses an
        # omitted one, including `wall_clock_seconds`, which used to default to
        # zero and therefore left the crash window on that dimension uncovered.
        self.policy = ReservationPolicy(
            spend_usd=args.reserve_spend, tokens=args.reserve_tokens,
            wall_clock_seconds=args.reserve_wall_clock)
        self.effects = self.root / "effects"
        self.injected = self.root / "injected"
        self.attempts = self.root / "attempts"
        self.ceilings = Ceilings(
            spend_usd=args.ceiling_spend, tokens=args.ceiling_tokens,
            wall_clock_seconds=args.ceiling_seconds, turns=args.ceiling_turns)
        self.clock = _clock(args.clock_step)
        self.model_calls = 0

    # -- construction ------------------------------------------------------

    def build(self) -> AgentLoop:
        lifecycle = SessionTable(self.root / "session.sqlite3")
        # One flag for both rows. `SessionStore.load` refuses a lifecycle row
        # with no ceiling row rather than inventing an unbounded session, so
        # asking it whether the session exists is only safe once both are
        # written — and the two are written together, here, before any pause
        # point is reachable.
        fresh = lifecycle.get(self.session) is None
        if fresh:
            lifecycle.create(
                session_id=self.session, tenant_id=TENANT,
                deployment_id=DEPLOYMENT,
                capability_sha256=capability_digest("h"),
                lease_expires_at=LEASE, now=self.clock())
        repo = Repository(self.root / "runtime.sqlite3", role="runtime",
                          tenant_id=TENANT, deployment_id=DEPLOYMENT)
        store = SessionStore(repo, lifecycle=lifecycle)
        if fresh:
            store.create(session_id=self.session, ceilings=self.ceilings)
        self.lifecycle = lifecycle
        self.repo = repo
        self.journal = TurnJournal(repo)
        self.machine = SessionStateMachine(lifecycle)
        self.budget = BudgetLedger(
            BudgetJournal(repo, session_root=self.root / "session-root"),
            policy=self.policy)
        return AgentLoop(
            session_id=self.session,
            store=store,
            budget=self.budget,
            journal=self.journal,
            spans=SpanWriter(repo),
            machine=self.machine,
            bound=ResultBound(bound_tokens=400, context_window_tokens=40_000),
            retention=RetentionStore(root=self.root / "scratch",
                                     session_id=self.session,
                                     max_bytes=1_000_000),
            model=self.model,
            execute=self.execute,
            versions=ArtifactVersions(
                TENANT, DEPLOYMENT, {"prompt": "sha256:" + "0" * 64}),
            clock=self.clock,
            assembler=_HookedAssembler(self.on_turn_boundary),
        )

    # -- the three hooks the pause points live in --------------------------

    def on_turn_boundary(self, turns: int) -> None:
        """Called with the number of *completed* turns, before turn N is begun.

        This is the seam the turn-boundary kill needs and the only place it
        exists. Pausing inside the model callable would be one line too late:
        `_one_turn` journals the intent and takes the reservation before it
        calls the provider, so a kill there is a kill inside a step whose
        effect had not started — a third state, and not the one being asked
        about.
        """
        kind, first, second = self.pause
        if kind == "turn" and turns == first:
            self._wait_to_be_killed(f"turn:{first}")

    def _tick(self) -> None:
        """One unit of declared time, if this arm declared one.

        Called from the two places the session does work the loop times: the
        provider call and a tool body. A no-op under the real clock.
        """
        if isinstance(self.clock, WorkClock):
            self.clock.advance()

    def model(self, context) -> ModelResponse:
        self._tick()
        # One *behind* `next_turn_index`, because the loop journals this turn's
        # model intent before calling the provider: the highest journalled turn
        # is already this one. Reading it forward was the fixture's own first
        # defect — every call_id and every `provider_state` came out labelled
        # with the turn after the one that produced it.
        turn = self.journal.next_turn_index(self.session) - 1
        _append(self.injected, f"{turn} {_hexes(context.provider_states)}")
        self.model_calls += 1
        kind, want_turn, _ = self.pause
        if kind == "model" and turn == want_turn:
            # Intent journalled, reservation on the ledger, no outcome and no
            # release. This is U-30's window and the only pause point at which
            # a reservation is outstanding when the process dies.
            self._wait_to_be_killed(f"model:{want_turn}")
        if turn >= self.turns - 1:
            return ModelResponse(
                provider="fixture", provider_state=state_for(turn),
                text=f"done after {turn + 1} turns", tool_calls=(),
                spend_usd=SPEND_PER_TURN, spend_provenance=SPEND_PROVENANCE,
                tokens=TOKENS_PER_TURN)
        return ModelResponse(
            provider="fixture", provider_state=state_for(turn), text="",
            tool_calls=tuple(
                ToolCall(index=i, call_id=f"t{turn}c{i}", name=f"tool-{i}")
                for i in range(self.tools)
            ),
            spend_usd=SPEND_PER_TURN, spend_provenance=SPEND_PROVENANCE,
            tokens=TOKENS_PER_TURN)

    def execute(self, call: ToolCall) -> str:
        self._tick()
        turn = self.journal.next_turn_index(self.session) - 1
        kind, want_turn, want_call = self.pause
        if kind == "step" and turn == want_turn and call.index == want_call:
            # The effect happens *first*, so the parent is looking at the state
            # the journal's ambiguous row describes: performed, unrecorded.
            _append(self.effects, f"{turn}/{call.call_id}")
            self._await_earlier_steps(turn, want_call)
            self._wait_to_be_killed(f"step:{want_turn}:{want_call}")
        _append(self.effects, f"{turn}/{call.call_id}")
        return f"body of {call.call_id}"

    def _await_earlier_steps(self, turn: int, index: int) -> None:
        """Hold until calls 0..index-1 have *committed outcomes*.

        Without this the kill point is a property of thread scheduling.
        `_run_calls` fans the calls out, so call `index`'s body can be running
        before call 0's outcome has been written, and the arm's assertion —
        *a recorded effect does not repeat* — would be asserted over a run in
        which nothing had been recorded yet. That is the vacuous shape: the
        test passes because there was nothing for it to catch.
        """
        deadline = time.time() + PAUSE_TIMEOUT_SECONDS
        while time.time() < deadline:
            if all(
                self.journal.is_step_complete(
                    self.session, turn, tool_step_index(i))
                for i in range(index)
            ):
                return
            time.sleep(POLL_SECONDS)
        raise Paused(
            f"turn {turn}: calls 0..{index - 1} never recorded an outcome, so "
            "the kill point this fixture claims to reach was not reached"
        )

    def _wait_to_be_killed(self, marker: str) -> None:
        print(f"READY {marker}", flush=True)
        deadline = time.time() + PAUSE_TIMEOUT_SECONDS
        while time.time() < deadline:
            time.sleep(POLL_SECONDS)
        raise Paused(
            f"nothing killed this process at {marker} within "
            f"{PAUSE_TIMEOUT_SECONDS}s. Exiting on its own would let the "
            "battery read a clean shutdown as a survived crash."
        )

    # -- run ---------------------------------------------------------------

    def _into_running(self) -> None:
        """Get the session to `RUNNING`, whichever of three states it is in.

        **The `RUNNING` branch is the crash branch, and it is the interesting
        one.** A `SIGKILL`ed process leaves the row reading `RUNNING`, because
        nothing ran on the way down — `test_lease_revocation.py` asserts exactly
        that and calls it the reason a state check alone would honour a dead
        session's handle. So the resuming process has to make the interruption
        explicit before it can take the resume edge, which is the sweep a
        supervisor performs when the lease lapses.

        Enumerated over the three states a resumable session can be in, and
        anything else raises. `STATE_TERMINATED` is deliberately absent: a
        terminated session is not resumable, and treating "not one of the three"
        as "try to resume anyway" is the complement-shaped classifier
        `tools/README.md` refuses.
        """
        state = self.lifecycle.get(self.session).state
        if state == STATE_STARTING:
            self.machine.start(self.session, at=self.clock())
            return
        if state == STATE_RUNNING:
            self.machine.interrupt(self.session, at=self.clock())
            self.machine.resume(
                self.session, at=self.clock(), lease_expires_at=LEASE)
            return
        if state == STATE_INTERRUPTED:
            self.machine.resume(
                self.session, at=self.clock(), lease_expires_at=LEASE)
            return
        raise SystemExit(
            f"{self.session!r} reads {state!r}, which is not a state this "
            "fixture can start or resume from"
        )

    def run(self) -> int:
        _append(self.attempts, str(os.getpid()))
        loop = self.build()
        self._into_running()
        outcome = loop.run("prompt")
        totals = self.budget.totals(self.session)
        print("DONE " + json.dumps({
            "terminal_state": outcome.terminal_state,
            "turns": [record.turn_index for record in outcome.turns],
            "model_calls": self.model_calls,
            "spend_usd": totals.spend_usd,
            "tokens": totals.tokens,
            "wall_clock_seconds": totals.wall_clock_seconds,
            "turn_total": totals.turns,
        }), flush=True)
        self.repo.close()
        self.lifecycle.close()
        return 0


class _HookedAssembler:
    """A `ContextAssembler` with one call-out, taken before anything is written.

    Delegation rather than a subclass, so the assembler under test is the real
    one: a subclass that overrode `assemble` would be testing the override.
    """

    def __init__(self, hook) -> None:
        from src.runtime.context import ByteTokenizer, ContextAssembler
        self._inner = ContextAssembler(
            budget_tokens=30_000, tokenizer=ByteTokenizer())
        self._hook = hook

    def assemble(self, *, prompt, turns, provider):
        self._hook(len(turns))
        return self._inner.assemble(prompt=prompt, turns=turns, provider=provider)


def _parse_pause(spec: str) -> tuple[str, int, int]:
    """`none`, `turn:N`, `model:N` or `step:N:K`. Enumerated, never complemented.

    An unrecognised spec is refused rather than read as `none`. A fixture that
    fell back to running to completion when its pause point was misspelled
    would report a clean run for a battery that thought it had crashed one.
    """
    if spec == "none":
        return ("none", -1, -1)
    parts = spec.split(":")
    if parts[0] in ("turn", "model") and len(parts) == 2:
        return (parts[0], int(parts[1]), -1)
    if parts[0] == "step" and len(parts) == 3:
        return ("step", int(parts[1]), int(parts[2]))
    raise SystemExit(
        f"unrecognised pause spec {spec!r}; the declared set is 'none', "
        "'turn:N', 'model:N' and 'step:N:K'"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    parser.add_argument("--session", default="s-resume")
    parser.add_argument("--turns", type=int, default=4)
    parser.add_argument("--tools", type=int, default=2)
    parser.add_argument("--pause", default="none")
    parser.add_argument("--ceiling-spend", type=float, default=100.0)
    parser.add_argument("--ceiling-tokens", type=int, default=1_000_000)
    parser.add_argument("--ceiling-seconds", type=float, default=1e12)
    parser.add_argument("--ceiling-turns", type=int, default=100)
    parser.add_argument("--reserve-spend", type=float, default=RESERVE_SPEND)
    parser.add_argument("--reserve-tokens", type=int, default=RESERVE_TOKENS)
    parser.add_argument("--reserve-wall-clock", type=float, default=0.0)
    parser.add_argument("--clock-step", type=float, default=0.0)
    return Child(parser.parse_args(argv)).run()


if __name__ == "__main__":
    raise SystemExit(main())
