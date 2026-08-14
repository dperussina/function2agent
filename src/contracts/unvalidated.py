"""T033 — FR-043's marking machinery for values with no measurement behind them.

FR-043 exists because this corpus has repeatedly caught inherited figures being
presented as measured ones. The failure is not that a number is a guess — v1
needs several — it is that a guess travels to an external surface **shaped like a
finding**, and the next reader cites it.

**Structural, on the `Secret` precedent (T035/FR-036).** `Secret` has no
serializer, so a credential cannot be logged by a code path that forgot to
redact. `Unvalidated` is the same idea pointed the other way: it has no
rendering that produces the bare value. `str()`, `format()` and `repr()` all
carry the marker, so a value reaches an external surface marked *by default* and
unmarked only if somebody wrote `.value` — which is a visible, greppable,
reviewable act.

**What it does not do.** It does not stop `.value` being read and printed. That
would require the value never to be usable, and these values are configuration:
they have to reach a comparison. What it buys is that emitting one unmarked is
an act rather than an omission, and T034 scans the external surfaces for it.

**Provenance is required, not optional.** A marked value that does not say where
its number came from tells a reader it is unmeasured and nothing else; the next
question is always "so where did it come from", and the answer belongs with the
value rather than in a document somebody has to find.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Generic, TypeVar

T = TypeVar("T")

MARKER = "unvalidated"


class UnvalidatedError(ValueError):
    pass


@dataclass(frozen=True)
class Unvalidated(Generic[T]):
    """A configured value with no measurement behind it (FR-043)."""

    value: T
    name: str
    provenance: str
    requirement: str = "FR-043"

    def __post_init__(self) -> None:
        if not self.name:
            raise UnvalidatedError("an unvalidated value must name itself")
        if not self.provenance:
            raise UnvalidatedError(
                f"{self.name}: an unvalidated value must state where its "
                "number came from. 'Unmeasured' without a provenance tells a "
                "reader nothing they can act on, and the number will be cited "
                "anyway."
            )

    # Every rendering path carries the marker. There is deliberately no
    # `__int__`, `__float__` or `__index__`: an implicit numeric conversion is
    # exactly the unmarked escape this type exists to close.
    def __str__(self) -> str:
        return f"{self.value} ({MARKER}: {self.provenance})"

    def __repr__(self) -> str:
        return (f"Unvalidated({self.value!r}, name={self.name!r}, "
                f"{MARKER}={self.provenance!r})")

    def __format__(self, spec: str) -> str:
        # A format spec would otherwise render the bare value:
        # f"{interval:.1f}" must not silently drop the marking.
        if spec:
            return f"{self.value:{spec}} ({MARKER}: {self.provenance})"
        return str(self)

    def marked_record(self) -> dict[str, Any]:
        """The shape every external surface emits this value as."""
        return {
            "value": self.value,
            "name": self.name,
            MARKER: True,
            "provenance": self.provenance,
            "requirement": self.requirement,
        }


# ---------------------------------------------------------------------------
# The registry. Every configured value FR-043 covers, with its provenance.
#
# This is data rather than scattered call sites so T034's scan has one list to
# check the external surfaces against, and so adding an unmeasured value is a
# visible diff in one file.

# Keys that ship a default and are wrapped at load (`Key.unvalidated=True`).
# Config.unvalidated is exactly this set. Required-with-no-default keys are
# still FR-043 values — they are marked when reported, not at load — and
# putting them here would collapse "nobody was asked" into "we shipped a guess".
SHIPPED_DEFAULTS: frozenset[str] = frozenset({
    "STALENESS_CEILING_SECONDS",
    "DRIFT_CHECK_INTERVAL_SECONDS",
    "CAPABILITY_LEASE_INTERVAL_SECONDS",
})

# Required, no default (Q-10). An operator-typed number is still unmeasured.
# Not in Config.unvalidated. mark() wraps them when a surface emits the number.
MARKED_WHEN_REPORTED: frozenset[str] = frozenset({
    "REPORTING_WINDOW_SECONDS",
    "SANDBOX_MEMORY_MAX",
    "SANDBOX_CPU_MAX",
})

PROVENANCES: dict[str, str] = {
    "STALENESS_CEILING_SECONDS": (
        "FR-047's stated default. Bound to FR-043 by FR-047 itself so it "
        "cannot travel externally as a validated number. No measurement of an "
        "acceptable staleness window exists in feature 001's evidence base."
    ),
    "DRIFT_CHECK_INTERVAL_SECONDS": (
        "Chosen to make FR-028's detection latency bounded, not measured "
        "against a false-alarm rate. FR-028's false-alarm rate is itself "
        "unmeasured, which is why FR-055 treats a non-canonical serializer as "
        "a false-alarm generator aimed at it."
    ),
    "CAPABILITY_LEASE_INTERVAL_SECONDS": (
        "Introduced by research §3.3. The residual authority window after a "
        "supervisor crash is one interval; no measurement establishes what "
        "window is acceptable."
    ),
    "REPORTING_WINDOW_SECONDS": (
        "FR-045 and SC-019 speak of each reporting window with no length "
        "defined. Loose requirements item 5 records that the absence of a "
        "window is not stated as deliberate. An operator-typed length is "
        "still a number with no measurement behind it. Inventing 3600 or "
        "86400 as a shipped default is the thing Q-10 exists to prevent; "
        "the key stays required with no default, and the value is marked "
        "when reported."
    ),
    "SANDBOX_MEMORY_MAX": (
        "FR-049 states no default for either bound and Q-10 was accepted as "
        "required configuration. Nothing in feature 001's evidence base "
        "bears on an agent's working set, so any number an operator types "
        "is still unmeasured. Not a shipped default — Config.unvalidated "
        "does not list this key."
    ),
    "SANDBOX_CPU_MAX": (
        "FR-049's cpu.max rate. Same class as SANDBOX_MEMORY_MAX: required "
        "with no default, unmeasured, marked when reported rather than "
        "wrapped at load. No measurement of a safe co-located-host quota "
        "exists in feature 001's evidence base."
    ),
}

NAMES = frozenset(PROVENANCES)


def mark(name: str, value: T) -> Unvalidated[T]:
    """Wrap a configured value in its declared marking."""
    try:
        provenance = PROVENANCES[name]
    except KeyError:
        raise UnvalidatedError(
            f"{name!r} is not a declared FR-043 value ({sorted(NAMES)}). "
            "Marking a value not in the registry makes the registry an "
            "incomplete list of what is unmeasured, which is the list T034 "
            "scans the external surfaces against."
        ) from None
    return Unvalidated(value=value, name=name, provenance=provenance)


def is_marked(rendered: Any) -> bool:
    """Whether a rendered value carries the marking.

    Used by T034 over whatever an external surface actually emits, so the test
    checks the emitted shape rather than the intent behind it.
    """
    if isinstance(rendered, Unvalidated):
        return True
    if isinstance(rendered, dict):
        return rendered.get(MARKER) is True and bool(rendered.get("provenance"))
    if isinstance(rendered, str):
        return MARKER in rendered
    return False
