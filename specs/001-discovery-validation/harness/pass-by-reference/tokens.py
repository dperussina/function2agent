"""SPIKE - E17 pass-by-reference. Delete after 2026-11-30. Do not import from product code.

The token-accounting model, kept as pure functions so it can be tested without a provider.

Two properties of this model are load-bearing and easy to lose:

* **Input accumulates.** Every call re-sends the whole conversation, so a bulk tool
  result is not paid once — it is paid on that call and on every call after it. A
  projection that charges a 6,000-token result once understates the treatment
  effect by roughly the number of remaining turns, which is most of the effect.
  :func:`project_run` accumulates.

* **The handle arm spends turns to save tokens.** Each bulk step it elides earns it
  an extra turn (the follow-up command that filters the file), charged at the same
  per-turn output rate and inserted *at the point the bulk step happened*, because
  where a turn lands changes what it accumulates behind it.

`bytes_per_token` is an estimation divisor from `config.json`, not a tokenizer.
Nothing here may be used to bill; the live ledger bills measured usage off the API
response. Keeping estimation and accounting in separate functions is the only thing
stopping an estimate from being laundered into an accounting figure.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


def est_tokens(n_bytes: int, bytes_per_token: float) -> int:
    """Estimated tokens for a payload of ``n_bytes``. Ceiling, so nothing rounds to free."""
    if n_bytes < 0:
        raise ValueError("n_bytes must be non-negative")
    if bytes_per_token <= 0:
        raise ValueError("bytes_per_token must be positive")
    return math.ceil(n_bytes / bytes_per_token)


def is_bulk(step_bytes: int, threshold_bytes: int) -> bool:
    return step_bytes > threshold_bytes


def result_tokens(step_bytes: int, *, bytes_per_token: float, cap_tokens: int | None) -> int:
    """Tokens a single tool result contributes, under one treatment.

    Both treatments cap. It is a *cap*, so a step already smaller than it is not
    inflated up to it — inflating small results would hand one arm a saving it does
    not have. ``cap_tokens=None`` means uncapped, which is retained only so the
    sensitivity analysis can price the arm the first draft of this harness
    projected; no treatment in `config.json` uses it.
    """
    raw = est_tokens(step_bytes, bytes_per_token)
    if cap_tokens is None:
        return raw
    if cap_tokens < 0:
        raise ValueError("cap_tokens must be non-negative or None")
    return min(raw, cap_tokens)


@dataclass(frozen=True)
class TurnModel:
    task_prompt_tokens: int
    output_tokens_per_working_turn: int
    output_tokens_final_turn: int
    small_result_tokens: int
    bulk_threshold_bytes: int


@dataclass(frozen=True)
class Treatment:
    name: str
    cap_tokens: int | None
    extra_turn_per_bulk_step: int
    static_prefix_tokens: int
    #: Whether bytes past the cap are still addressable. False for A-inline (they
    #: are gone), True for A-handle (they are on disk behind the returned path).
    #: Not used in the token arithmetic — it is limb 2's mechanism, recorded here
    #: so the two limbs are defined in one place.
    data_reachable_after_cap: bool = False


@dataclass(frozen=True)
class RunProjection:
    treatment: str
    turns: int
    input_tokens: int
    output_tokens: int
    #: The largest single call's input. Summed input says what a run costs; the peak
    #: says whether it can happen at all. Reporting only the sum is how the first
    #: draft priced a transcript three and a half times the context window.
    peak_input_tokens: int = 0

    def cost_usd(self, price_in: float, price_out: float) -> float:
        return self.input_tokens * price_in / 1e6 + self.output_tokens * price_out / 1e6


def ordered_result_tokens(step_bytes: list[int], tm: TurnModel, tr: Treatment,
                          bytes_per_token: float) -> list[int]:
    """The per-turn tool-result token sequence, with the handle arm's extra turns in place."""
    out: list[int] = []
    for nb in step_bytes:
        out.append(result_tokens(nb, bytes_per_token=bytes_per_token,
                                 cap_tokens=tr.cap_tokens))
        if is_bulk(nb, tm.bulk_threshold_bytes):
            out.extend([tm.small_result_tokens] * tr.extra_turn_per_bulk_step)
    return out


def project_run(step_bytes: list[int], tm: TurnModel, tr: Treatment,
                bytes_per_token: float) -> RunProjection:
    """Project one task, one treatment, one replicate."""
    results = ordered_result_tokens(step_bytes, tm, tr, bytes_per_token)
    prefix = tr.static_prefix_tokens + tm.task_prompt_tokens
    acc = 0
    total_in = 0
    total_out = 0
    peak = 0
    for r in results:
        call_in = prefix + acc
        peak = max(peak, call_in)
        total_in += call_in
        total_out += tm.output_tokens_per_working_turn
        acc += tm.output_tokens_per_working_turn + r
    # The answering call: it reads everything and emits the answer.
    call_in = prefix + acc
    peak = max(peak, call_in)
    total_in += call_in
    total_out += tm.output_tokens_final_turn
    return RunProjection(tr.name, len(results) + 1, total_in, total_out, peak)


def call_cost(in_tok: int, out_tok: int, price_in: float, price_out: float) -> float:
    return in_tok * price_in / 1e6 + out_tok * price_out / 1e6


class BudgetExceeded(RuntimeError):
    """The hard ceiling from config.json. Abort and report partial results."""


@dataclass
class Ledger:
    """Live accumulator. Checked BEFORE each call; bills measured usage, never the estimate."""
    ceiling_usd: float
    spent_usd: float = 0.0
    calls: int = 0

    def check(self, projected_next_usd: float) -> None:
        if self.spent_usd + projected_next_usd > self.ceiling_usd:
            raise BudgetExceeded(
                f"next call would take spend to "
                f"${self.spent_usd + projected_next_usd:.4f} against a "
                f"${self.ceiling_usd:.2f} ceiling"
            )

    def bill(self, in_tok: int, out_tok: int, price_in: float, price_out: float) -> float:
        amount = call_cost(in_tok, out_tok, price_in, price_out)
        self.spent_usd += amount
        self.calls += 1
        return amount
