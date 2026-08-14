"""T188 — FR-045's reporting window, as configuration, marked when emitted.

**Requirement**: FR-045. **Also**: loose requirements item 5, FR-043, Q-10.

FR-045 and SC-019 speak of "each reporting window" and "the first production
reporting window" with no window length defined. The *absence of a threshold*
on the share is deliberate (T130 / `NO_THRESHOLD`). The absence of a window
is not stated as deliberate anywhere. This module is the window type that
absence owed, and it is not a default length.

## WHAT THIS MODULE WILL NOT DO

**1. It will not invent a length.** `REPORTING_WINDOW_SECONDS` is required
configuration with no default. `_NO_DEFAULT_REPORTING_WINDOW` is why: an
unset window is a single window covering all of time, which FR-045 rules
out along with "unbounded" and "a figure this specification invented".
Choosing 3600 or 86400 here would collapse "nobody was asked" into "we
shipped a guess". An unset window is a startup failure, not an
unvalidated default.

**2. It will not wrap the key at load.** `Key.unvalidated=True` plus a
default is the other way to invent a number. The key stays required. The
*value*, once an operator has typed one, is marked when a surface emits
it as a number — because a typed length is still a number with no
measurement behind it.

**3. It will not invent a report surface FR-045 never defined.** T130
already emits the share over this window. This module is the window
definition and the marking. It is not an SC-019 dashboard.

T130 constructs a window through `from_config` and through the
constructor. Both live here. `not_verifiable.py` re-exports
`ReportingWindow` so existing call sites keep working. There is one
constructor.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any

from src.contracts.unvalidated import Unvalidated, mark

WINDOW_KEY = "REPORTING_WINDOW_SECONDS"


class WindowError(ValueError):
    """A window the report will not compute over."""


class ModuleTextUnavailable(RuntimeError):
    """This module's own text could not be located for the arm that reads it."""


@dataclass(frozen=True)
class ReportingWindow:
    """A fixed-length interval, and whether it has closed.

    FR-045 requires the length to be **fixed** rather than per-report, so that
    two consecutive reports are comparable. It is required configuration with
    no default — `REPORTING_WINDOW_SECONDS` in `RUNTIME_KEYS`, whose
    `no_default_reason` is quoted back to the operator at startup.
    """

    #: Seconds since the epoch. A number rather than a `datetime` because the
    #: document is machine-readable and a timezone-naive datetime in JSON is a
    #: second way to be wrong about an interval.
    starts_at: float
    length_seconds: float

    def __post_init__(self) -> None:
        if self.length_seconds <= 0:
            raise WindowError(
                f"the reporting window is {self.length_seconds!r} seconds. "
                "FR-045 rules out an unbounded window and a single window "
                "covering all of time; a non-positive one is both at once."
            )

    @property
    def ends_at(self) -> float:
        return self.starts_at + self.length_seconds

    def has_closed(self, now: float) -> bool:
        return now >= self.ends_at

    @property
    def marked_length(self) -> Unvalidated[float]:
        """The length as an FR-043 value. The emission path, not the arithmetic.

        Arithmetic uses `length_seconds`. A surface that emits the number
        uses this, so the marking travels with the value rather than beside
        it in a comment a reader can skip.
        """
        return mark(WINDOW_KEY, self.length_seconds)

    @classmethod
    def from_config(cls, config: Any, starts_at: float) -> "ReportingWindow":
        """Read the length from FR-033's resolved schema and nowhere else.

        Going through `Config` rather than taking a float is what makes the
        unset case a *startup* failure with its reason quoted, instead of a
        caller's default arriving here already looking like a decision.
        """
        raw = config["REPORTING_WINDOW_SECONDS"]
        if isinstance(raw, Unvalidated):
            raw = raw.value
        return cls(starts_at=starts_at, length_seconds=float(raw))


def interval_document(window: ReportingWindow, *, closed: bool) -> dict[str, Any]:
    """The interval block T130 emits. Length is marked; starts/ends are not.

    `starts_at` is an observation (when this window opened), not a configured
    guess. `length_seconds` is the operator-typed FR-045 value and is the
    number FR-043 requires marked.
    """
    return {
        "starts_at": window.starts_at,
        "ends_at": window.ends_at,
        "length_seconds": window.marked_length.marked_record(),
        "closed": closed,
        "partial": not closed,
    }


def module_source() -> str:
    """This module's own text, for the arm that reads it for a default."""
    module = inspect.getmodule(ReportingWindow)
    if module is None:
        raise ModuleTextUnavailable(
            "inspect.getmodule() could not locate the module defining "
            "ReportingWindow, so this module's own text cannot be read. "
            "Refused rather than returned empty: the arm that calls this "
            "searches the text for an invented default length and reports "
            "finding none, and text that was never read finds none either."
        )
    return inspect.getsource(module)
