"""T176 — a sampling rule pre-registered before the window it governs.

**Requirement**: FR-040's third branch. **Boundary**: FR-052.

The rule is the thing that selects which results an adjudicator sees.
Registering it after the window opens is selecting on the traffic that
already arrived, which is not pre-registration: the sample then depends
on what happened, and a later reader cannot tell a designed sample from
a convenient one.

This module does not write `human_label`. It does not invent a label.
It does not import the judge. A rule is a rate, a registration time,
and a window that has not yet opened.
"""

from __future__ import annotations

from dataclasses import dataclass


class SamplingError(ValueError):
    """A rule this module refuses to register."""


@dataclass(frozen=True)
class SamplingRule:
    """One pre-registered sampling rule.

    `registered_at` must be strictly before `window_starts_at`. That
    inequality is the whole of pre-registration; a rule constructed
    the other way around is not a rule.
    """

    rate: float
    registered_at: float
    window_starts_at: float
    window_length_seconds: float

    def __post_init__(self) -> None:
        if not (0.0 < self.rate <= 1.0):
            raise SamplingError(
                f"a sampling rate is in (0, 1], got {self.rate!r}. "
                "A rate of 0 samples nothing and is not a rule; a rate "
                "above 1 is not a share of the window."
            )
        if self.window_length_seconds <= 0:
            raise SamplingError(
                f"the sampling window is {self.window_length_seconds!r} "
                "seconds. A non-positive window is already closed."
            )
        if self.registered_at >= self.window_starts_at:
            raise SamplingError(
                "a sampling rule must be registered before the window "
                "opens. Registering after the window opens is selecting "
                "on the traffic that already arrived, which is not "
                "pre-registration."
            )

    @property
    def window_ends_at(self) -> float:
        return self.window_starts_at + self.window_length_seconds


def register_rule(
    *,
    rate: float,
    window_starts_at: float,
    window_length_seconds: float,
    now: float,
) -> SamplingRule:
    """Register a rule at `now` for a window that has not opened.

    `now` is the registration time. Passing a `now` at or after
    `window_starts_at` is the defect this function exists to refuse.
    """
    return SamplingRule(
        rate=rate,
        registered_at=now,
        window_starts_at=window_starts_at,
        window_length_seconds=window_length_seconds,
    )
