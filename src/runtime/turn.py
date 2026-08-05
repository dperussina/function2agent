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


@dataclass(frozen=True)
class ModelResponse:
    """One provider turn, above the adapter.

    `provider_state` is **opaque bytes, ours** (T-02, FR-037): captured
    verbatim, re-injected verbatim, never merged across providers, never
    interpreted. `None` is a provider that returned none, which is different
    from empty bytes.
    """

    provider: str
    provider_state: bytes | None
    text: str
    tool_calls: tuple[ToolCall, ...] = ()
    spend_usd: float = 0.0
    tokens: int = 0

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
