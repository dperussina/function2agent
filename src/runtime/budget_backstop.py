"""T065 — the call-count backstop, independent of the cost table by construction.

**Why a second ceiling when FR-005 already has four.** Three of FR-005's four
are denominated in something the runtime has to *compute*, and the spend one is
computed from `costs.py`. A model with no entry there is refused by T063 — which
is correct, and which means no spend figure accrues for it. Meanwhile the turn,
token and wall-clock ceilings are numbers an operator supplied, on the same
configuration channel, in the same file, at the same time. A misconfiguration
that reaches one plausibly reaches all four, and then nothing stops the loop.
T065's stated reason is exactly this: *"a missing price cannot remove every
ceiling at once."*

**What makes this a backstop rather than a fifth ceiling.** Three properties,
each of which is a test and a removal proof:

1. It reads **nothing** that the priced path touches — not `costs`, not
   `ledger`, not `trace_budget`. Its only input is the journal.
2. It reads **no configuration**. There is no environment key, and the maximum
   may be lowered by a caller but never raised past `MAX_MODEL_CALLS`. A limit
   the same channel can widen is not a backstop for that channel.
3. It counts off **disk**, so it is not the thing finding 006 measured:
   *"an agent that crashes and resumes in a retry loop has no effective ceiling
   at all."*

**Where the number came from, and why 20 rather than a round guess.** This
occupies the position the removed dependency's one enforced ceiling held, and
[research/02](../../research/02-agent-harnesses.md) §ADK measured what that
position was actually worth: `LoopAgent.max_iterations` *"did not survive the
supersession"*, the graph tier that replaced it *"has no step ceiling of any
kind"* — a four-node graph ran **1,292 iterations in 20 seconds** and was still
going — and the ceiling that did exist **defaulted to `None`**. So the
requirement here is not merely *a* limit; it is a limit that is on by default
and cannot be turned off.

The figure itself is the only published one for this exact ceiling:
[research/13](../../research/13-claude-managed-agents.md) §4.4 records
Anthropic's Managed Agents capping `outcome max_iterations` at **≤ 20**
([reference](https://platform.claude.com/docs/en/managed-agents/reference)).
It is cited rather than chosen for the same reason `costs.py` cites its rates:
a number recalled or picked is an invented default, and FR-005 is about not
having those.

**This is not a spend estimate and must never be reported as one.**
[research/14](../../research/14-architecture-synthesis.md) §5 measured the trap
directly: the removed dependency's *"one enforced ceiling counts model calls"*,
and finding 003 measured a **40× spread in input context for identical work**
between two runtimes, so *"any observability surface that reports 'calls' as a
proxy for spend will be confidently wrong by roughly the ratio of context sizes
between nodes."* A call count bounds how many times the loop can go round. It
says nothing about the bill, and `BackstopTripped`'s message says so, because
an operator who reads a call count as a spend figure will size the real ceiling
from it.

**U-30 is untouched.** [research/14](../../research/14-architecture-synthesis.md)
§5.1 holds it open on whether an in-process budget channel can be trusted at
all. This counter is in-process and reads a store the same process writes. A
second in-process ceiling is redundancy against *misconfiguration*, which is
what it claims; it is not redundancy against the channel itself, which is what
U-30 asks about.
"""

from __future__ import annotations

from typing import Protocol, Sequence

from src.runtime.journal import STEP_MODEL_CALL

#: The largest a backstop may be, from the one vendor that publishes a figure
#: for this exact ceiling. See the module docstring. A caller may go below it
#: and `CallCountBackstop` refuses to go above it.
MAX_MODEL_CALLS = 20


class BackstopError(RuntimeError):
    """A backstop that cannot be configured as asked."""


class BackstopTripped(RuntimeError):
    """The session has made as many model calls as it is allowed to.

    An exception rather than a terminal state, and deliberately. FR-006's
    taxonomy is a closed set in `src/contracts/terminal.py` and adding a member
    is T067's, not this task's. More importantly, the two shapes say different
    things: a terminal state is *the session concluded*, and this is *the
    session was stopped without concluding*. Collapsing them would make a
    halted run indistinguishable from a finished one from the caller's side,
    which is the false-success shape T068 exists to rule out.
    """


class StepSource(Protocol):
    """The one thing this module reads.

    Structural rather than `TurnJournal` by name, so that the dependency is
    visible as a single method in this file. Anything wider would make the
    independence claim above a matter of reading the imports of whatever got
    passed in.
    """

    def steps(self, session_id: str) -> Sequence[object]: ...


class CallCountBackstop:
    """A durable count of a session's model calls, against a ceiling nobody can raise."""

    def __init__(self, journal: StepSource, *,
                 maximum: int = MAX_MODEL_CALLS) -> None:
        if isinstance(maximum, bool) or not isinstance(maximum, int):
            raise BackstopError(
                f"maximum is {maximum!r}. It is a count of model calls and "
                "must be an int. `None` in particular is refused: it is the "
                "value the removed dependency defaulted to, and it meant "
                "unbounded (research/02)."
            )
        if maximum < 1:
            raise BackstopError(
                f"maximum is {maximum}; a backstop that permits no calls at "
                "all stops every session, which an operator will respond to "
                "by removing the backstop"
            )
        if maximum > MAX_MODEL_CALLS:
            raise BackstopError(
                f"maximum {maximum} cannot be raised above {MAX_MODEL_CALLS}. "
                "This is a backstop for the configured ceilings, so a caller "
                "able to widen it has removed the thing it backs up. Lower it "
                "freely; to run longer, raise FR-005's turn ceiling, which is "
                "the ceiling for that."
            )
        self.journal = journal
        self.maximum = maximum

    def calls_made(self, session_id: str) -> int:
        """Model calls this session has begun, read off the journal every time.

        **Begun, not finished.** The loop journals a model call's intent before
        making it, so a row with no outcome is a call that may have reached the
        provider. Counting it over-counts, which is the direction `ledger.py`
        argues for on the same facts: *"the crash counts the reservation, which
        is too much rather than too little."*

        Tool steps are not counted. The metric is the one the removed
        dependency enforced, and a backstop that fired on tool-heavy work
        costing nothing is a backstop an operator would take out.
        """
        return sum(1 for step in self.journal.steps(session_id)
                   if getattr(step, "step_kind", None) == STEP_MODEL_CALL)

    def remaining(self, session_id: str) -> int:
        """Calls left before `check` refuses. Floored at zero.

        Floored because a negative would read as headroom to anything that
        summed it, and the over-counting above can put the real figure past the
        maximum.
        """
        return max(0, self.maximum - self.calls_made(session_id))

    def check(self, session_id: str) -> None:
        """Refuse the next model call once `maximum` are already on disk.

        Called at the **top** of a turn, before the call it guards, so the
        comparison is `>=`: at `maximum` calls recorded, the next one would be
        the (maximum + 1)-th.
        """
        made = self.calls_made(session_id)
        if made >= self.maximum:
            raise BackstopTripped(
                f"{session_id} has begun {made} model calls and the backstop "
                f"allows {self.maximum}. The run is stopped, not concluded. "
                "**This is a call count and not a spend figure** — research/14 "
                "§5 measured a 40x spread in context size for identical work "
                "between runtimes, so sizing a spend ceiling from this number "
                "would be wrong by about that ratio. The ceilings denominated "
                "in money and tokens are FR-005's, and this backstop firing "
                "before any of them usually means one of them is unset, "
                "mis-set, or priced by a model with no cost entry."
            )
