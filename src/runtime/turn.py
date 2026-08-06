"""The turn's own types: one provider response, and one `TurnRecord`.

**Why these are not in `loop.py`, where they were written.** T052 reconstructs
turns from the journal, so `resume.py` has to build a `TurnRecord` — and the loop
has to read a `ResumePlan`. With both types defined in `loop.py` that is a cycle,
and the two ways out of a cycle are worse than a move: a lazy import inside a
function hides the dependency from every tool that reads imports, and a
near-identical second dataclass in `resume.py` is two definitions of one record
that will eventually disagree.

So the types move down and `loop.py` re-exports them under the names they have
always had. Nothing that imported `ModelResponse`, `TurnRecord`, `LoopError` or
`state_digest` from `src.runtime.loop` has to change, and there is exactly one
definition of each.

`LoopError` is defined here rather than in `loop.py` for the same reason it is
raised here: `ModelResponse.__post_init__` and `TurnRecord.__post_init__` raise
it, and callers already catch it by that name.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from src.runtime.dispatch import ToolCall, ToolResult


class LoopError(RuntimeError):
    """A turn that cannot be run, or recorded, as described."""


class UnpricedTurnError(LoopError):
    """A turn whose spend nothing has priced, asked for as though it had.

    A distinct type, and a subclass so that callers already catching
    `LoopError` keep catching it. The distinction it carries is the one the
    whole pricing seam exists to hold open: **unpriced is not zero.** A turn
    that contributed `0.0` to the spend ceiling because nothing priced it is
    indistinguishable, at the ledger, from a turn that genuinely cost nothing —
    and the first makes FR-005's ceiling unenforceable while the second is a
    fact. `ModelResponse.spend_usd is None` is the first; raising this rather
    than coercing it is what stops the second from absorbing it.
    """


@dataclass(frozen=True)
class ModelResponse:
    """One provider turn, above the adapter.

    `provider_state` is **opaque bytes, ours** (T-02, FR-037): captured
    verbatim, re-injected verbatim, never merged across providers, never
    interpreted. `None` is a provider that returned none, which is different
    from empty bytes.

    **`spend_usd` is `float | None`, and `None` is the default, because the
    field used to default to `0.0` and that default was the defect.** Nothing
    in `src/` priced a turn — `src/runtime/providers/costs.py` landed a table
    and no caller reached it — so every response carried `0.0` and FR-005's
    spend ceiling was compared against zero on every path. Widening the type
    does not by itself price anything; what it does is make *unpriced* a state
    the ledger cannot silently add up. FR-005 forbids a ceiling *"treated as
    unbounded or filled from a default this specification invented"*, and a
    spend figure of zero standing in for a figure nobody computed is that
    default arriving one level below the ceiling. The same shape as
    `ParsedTurn.cost_usd`, whose docstring says it in one line: *"`None` here
    means not reported, never zero."*

    `model` is the API identifier the turn was priced against, and it is
    carried rather than derived. It is not read off the provider's response:
    **no response body in `tests/conformance/cassettes/` contains one** — the
    four cassettes record the model as cassette metadata beside the payload,
    not inside it — so a driver reading `payload["model"]` would be asserting a
    wire contract this repository has never observed. It is instead the string
    the caller already handed to `ProviderDriver.build_request`, which is
    measured by being in the request.

    `input_tokens` and `output_tokens` are the split pricing needs, and they
    are present-or-absent **together**. A half-split reads like a whole one and
    prices at whichever half survived.
    """

    provider: str
    provider_state: bytes | None
    text: str
    tool_calls: tuple[ToolCall, ...] = ()
    model: str = ""
    spend_usd: float | None = None
    tokens: int = 0
    input_tokens: int | None = None
    output_tokens: int | None = None

    def __post_init__(self) -> None:
        if not self.provider:
            raise LoopError("a model response must name the provider")
        if self.provider_state is not None and not isinstance(
            self.provider_state, (bytes, bytearray)
        ):
            raise LoopError(
                "provider_state is opaque bytes. A str would have to be "
                "encoded, and an encoding is an interpretation — FR-037 "
                "requires the state re-injected verbatim."
            )
        if self.spend_usd is not None:
            if (isinstance(self.spend_usd, bool)
                    or not isinstance(self.spend_usd, (int, float))):
                raise LoopError(
                    f"spend_usd is {self.spend_usd!r}. It is USD or it is "
                    "None, and None is the one way to say nothing priced "
                    "this turn."
                )
            if self.spend_usd < 0:
                raise LoopError(
                    f"spend_usd is {self.spend_usd}. A negative spend lowers "
                    "a running total, which is a ceiling walked back under."
                )
        halves = (self.input_tokens, self.output_tokens)
        if (self.input_tokens is None) != (self.output_tokens is None):
            raise LoopError(
                f"the token split is half-supplied ({halves}). Both halves or "
                "neither: a response carrying one of them reads as a split to "
                "anything that checks for presence, and would price at "
                "whichever half survived."
            )
        if self.input_tokens is not None and self.output_tokens is not None:
            total = self.input_tokens + self.output_tokens
            if total != self.tokens:
                raise LoopError(
                    f"the token split {halves} sums to {total} and `tokens` "
                    f"is {self.tokens}. They are one quantity written twice, "
                    "so a disagreement means one of them is wrong and nothing "
                    "here can say which."
                )

    @property
    def is_priced(self) -> bool:
        """Whether a spend figure exists for this turn.

        **The accepting condition, stated positively.** Not *"not unpriced"*:
        a complement over a field that later grows a third state answers the
        wrong way round on the state nobody thought of, and the wrong way round
        here is the one that lets an unpriced turn through.
        """
        return self.spend_usd is not None

    def require_spend_usd(self) -> float:
        """The spend figure, or a refusal naming why there is none.

        Called wherever a spend reaches a total. There is deliberately no
        `spend_usd_or_zero`: the coercion this refuses is the whole defect, and
        a helper offering it would be taken up by the first caller that found
        this inconvenient.
        """
        if self.spend_usd is None:
            raise UnpricedTurnError(
                f"{self.provider}/{self.model or '<no model recorded>'}: this "
                "turn has no spend figure, so it cannot be counted against "
                "FR-005's spend ceiling and is refused rather than counted at "
                "zero. A response reaches this state by two routes: it was "
                "built without going through "
                "`src/runtime/providers/adapter.py::model_response`, which is "
                "the only thing in `src/` that prices a turn; or it was "
                "reconstructed from a journal written before the model "
                "identifier and the token split were recorded, in which case "
                "the ledger already holds this turn's spend and "
                "`ResumePlan.unpriced_turns` names it."
            )
        return float(self.spend_usd)


def state_digest(state: bytes | None) -> str | None:
    """The only form of the opaque state that may reach a record.

    A digest is what makes "re-injected verbatim" assertable without putting
    provider reasoning into a trace. `trace-record.md`: never written in a
    readable form.
    """
    if state is None:
        return None
    return "sha256:" + hashlib.sha256(bytes(state)).hexdigest()


@dataclass(frozen=True)
class TurnRecord:
    """`data-model.md` §2.2."""

    turn_index: int
    provider: str
    provider_state: bytes | None
    tool_calls: tuple[ToolCall, ...]
    tool_results: tuple[ToolResult, ...]
    text: str
    at: float

    def __post_init__(self) -> None:
        if self.turn_index < 0:
            raise LoopError("turn_index is a position, not a counter")
        declared = [c.index for c in self.tool_calls]
        if declared != sorted(declared):
            raise LoopError(
                f"tool_calls are held {declared}; §2.2 says the field is in "
                "the provider's declared index order, so a record holding "
                "them in another order is a record of something else."
            )
        got = [r.index for r in self.tool_results]
        if got != sorted(got):
            raise LoopError(f"tool_results are out of declared order: {got}")

    @property
    def provider_state_digest(self) -> str | None:
        return state_digest(self.provider_state)

    def to_record(self) -> dict[str, Any]:
        """**The opaque state is not in here, by construction.**

        Not redacted on the way out — absent. A field that is present and
        emptied is one somebody later fills in.
        """
        return {
            "turn_index": self.turn_index,
            "provider": self.provider,
            "provider_state_digest": self.provider_state_digest,
            "tool_calls": [
                {"index": c.index, "call_id": c.call_id, "name": c.name}
                for c in self.tool_calls
            ],
            "text": self.text,
            "at": self.at,
        }
