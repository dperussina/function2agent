"""T191 — SC-017's per-runtime adoption report.

**Criterion**: SC-017.

For each deployed runtime, whether it is still serving traffic four weeks
after installation is measured and reported. A runtime that is installed,
demonstrated and then unused is recorded as a **non-adoption** rather than
as an install.

## What this module will not do

**1. It will not start a server.** This is a report in the same family as
`margin.py` and `unvalidated.py`. It classifies observations it is handed.
It does not construct a `Registry`, call `build_server`, import the loop,
or invent the T215 serve path. OD-36 still holds: `src/runtime/main.py` is
report+exit.

**2. It will not count installs as the success metric.** The sentence
SC-017 exists for is the unused-after-demo runtime. Recording that row as
an install is the lie. `non_adoption` is a distinct recorded outcome.

**3. It will not apply a fleet-percentage gate.** SC-017 is a per-runtime
classification. No threshold is pre-registered, and none is applied. See
`NO_THRESHOLD`.

**4. It will not report a green adoption share over an empty live set.**
No production runtime is serving (OD-36). A census handed no observations
has no assessable runtime. A share of 1.0 over zero is a claim; a share
of 0.0 over zero is a different claim. Both are refused. `adoption_share`
is `None` and `share_absent_because` names the absence.

**5. It will not invent an install row.** No install evidence is expected.
Absence is reported as `no_install`, not filled in.

**6. It will not collapse "installed, never demonstrated" into
non-adoption.** Non-adoption is specifically *installed, demonstrated,
then unused*. A row that never served is `not_demonstrated`: not yet an
adoption measurement.

The four-week window is the criterion's, derived from SC-017's text, not
FR-045's configured reporting window and not a figure this module
invented. `now`, install time and last-served time are arguments, the
same way other reports take `starts_at`.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

SCHEMA_VERSION = "1.0.0"

#: SC-017: *"four weeks after installation"*. The criterion's window,
#: not `REPORTING_WINDOW_SECONDS` and not a silent default.
FOUR_WEEKS_SECONDS = 4 * 7 * 24 * 60 * 60

FOUR_WEEKS_BASIS = (
    "SC-017: For each deployed runtime, whether it is still serving "
    "traffic four weeks after installation is measured and reported."
)

STATE_NO_INSTALL = "no_install"
STATE_NOT_DEMONSTRATED = "not_demonstrated"
STATE_NOT_YET_ASSESSABLE = "not_yet_assessable"
STATE_NON_ADOPTION = "non_adoption"
STATE_STILL_SERVING = "still_serving"

STATES: tuple[str, ...] = (
    STATE_NO_INSTALL,
    STATE_NOT_DEMONSTRATED,
    STATE_NOT_YET_ASSESSABLE,
    STATE_NON_ADOPTION,
    STATE_STILL_SERVING,
)

STATE_MEANINGS: Mapping[str, str] = {
    STATE_NO_INSTALL: (
        "no install evidence. Absence is expected. Not an install and "
        "not a non-adoption; no row is invented."
    ),
    STATE_NOT_DEMONSTRATED: (
        "installed, never demonstrated. Not yet an adoption measurement. "
        "Not adopted, and not a non-adoption: non-adoption is installed, "
        "demonstrated, then unused."
    ),
    STATE_NOT_YET_ASSESSABLE: (
        "installed and demonstrated, but four weeks have not elapsed. "
        "SC-017's window has not opened; day-1 unused is not a "
        "non-adoption."
    ),
    STATE_NON_ADOPTION: (
        "installed, demonstrated and then unused at four weeks. Recorded "
        "as a non-adoption rather than as an install."
    ),
    STATE_STILL_SERVING: (
        "still serving traffic four weeks after installation"
    ),
}

#: Classifications that can answer SC-017's boolean. The other three
#: states are named absences, not a fleet of zeros.
ASSESSABLE = frozenset({STATE_NON_ADOPTION, STATE_STILL_SERVING})

NO_THRESHOLD = (
    "No threshold is applied and none is pre-registered. SC-017 is a "
    "per-runtime classification — whether this deployed runtime is still "
    "serving traffic four weeks after installation — not a fleet "
    "percentage gate. A share with a number beside it is "
    "indistinguishable from a share that was compared against it."
)

EMPTY_CENSUS_ABSENCE = (
    "No deployed runtime is assessable. OD-36: no production runtime is "
    "serving; an empty observation set is not a fleet of zero "
    "non-adoptions and not a green adoption rate over zero. Reported as "
    "an absence rather than as 1.0 or 0.0."
)

OD36_RESIDUAL = (
    "OD-36 still holds. Registry is constructed nowhere. "
    "src/runtime/main.py is report+exit. serving.py is not a process "
    "entry point; build_server is only called from contract tests. This "
    "module classifies observations it is handed. It does not start a "
    "server and does not close T214 or T215."
)

# ---------------------------------------------------------------------------
# Planted flags. Each one is a removal-proof needle. Flipping it is the
# defect the named T191 test exists to catch. Do not "fix" a proof by
# making the flag unused: the test reads the flag, then the behaviour.
# ---------------------------------------------------------------------------

NON_ADOPTION_COUNTED_AS_INSTALL = False
FOUR_WEEK_WAIT_IS_DROPPED = False
EMPTY_LIVE_CENSUS_IS_GREEN = False


class AdoptionInputError(ValueError):
    """A row this report will not classify."""


class ModuleTextUnavailable(RuntimeError):
    """This module's own text could not be located for the arm that reads it."""


@dataclass(frozen=True)
class RuntimeObservation:
    """One deployed runtime, as the report is handed it.

    Constructed by a caller that already holds install and serve
    evidence. This module does not start a session, bind a surface, or
    invent a serve.
    """

    deployment_id: str
    installed_at: float | None = None
    demonstrated_at: float | None = None
    last_served_at: float | None = None

    def __post_init__(self) -> None:
        if not self.deployment_id:
            raise AdoptionInputError(
                "a runtime observation carries a deployment_id. Without "
                "it the classification belongs to no installed identity."
            )
        if self.installed_at is None:
            if self.demonstrated_at is not None or self.last_served_at is not None:
                raise AdoptionInputError(
                    f"{self.deployment_id!r} has serve evidence and no "
                    "install. A serve without an install is not a row "
                    "this report will invent an install for."
                )
            return
        if self.demonstrated_at is None:
            if self.last_served_at is not None:
                raise AdoptionInputError(
                    f"{self.deployment_id!r} has a last_served_at and no "
                    "demonstration. A serve is a demonstration; the two "
                    "are not independent facts."
                )
            return
        if self.demonstrated_at < self.installed_at:
            raise AdoptionInputError(
                f"{self.deployment_id!r} was demonstrated before it was "
                "installed"
            )
        if self.last_served_at is None:
            raise AdoptionInputError(
                f"{self.deployment_id!r} was demonstrated and has no "
                "last_served_at. A demonstration is a serve."
            )
        if self.last_served_at < self.demonstrated_at:
            raise AdoptionInputError(
                f"{self.deployment_id!r} last served before it was "
                "demonstrated"
            )


@dataclass(frozen=True)
class RuntimeAdoption:
    """SC-017's classification of one deployed runtime."""

    deployment_id: str
    classification: str
    counted_as_install: bool
    installed_at: float | None
    demonstrated_at: float | None
    last_served_at: float | None
    four_week_mark: float | None

    def document(self) -> dict[str, Any]:
        return {
            "deployment_id": self.deployment_id,
            "classification": self.classification,
            "counted_as_install": self.counted_as_install,
            "installed_at": self.installed_at,
            "demonstrated_at": self.demonstrated_at,
            "last_served_at": self.last_served_at,
            "four_week_mark": self.four_week_mark,
        }


@dataclass(frozen=True)
class AdoptionCensus:
    """SC-017's artifact. Per-runtime classifications, no fleet gate."""

    now: float
    live: bool
    synthetic: bool
    runtimes: tuple[RuntimeAdoption, ...]
    by_classification: Mapping[str, int]

    def __post_init__(self) -> None:
        missing = set(STATES) - set(self.by_classification)
        if missing:
            raise AdoptionInputError(
                f"the breakdown omits {sorted(missing)}. Every named "
                "state appears, zeroes included: an omitted key and a "
                "key nothing can produce are indistinguishable."
            )

    @property
    def assessable_count(self) -> int:
        return sum(
            self.by_classification[state] for state in ASSESSABLE
        )

    @property
    def install_count(self) -> int:
        return sum(
            1 for row in self.runtimes if row.counted_as_install
        )

    @property
    def non_adoption_count(self) -> int:
        return self.by_classification[STATE_NON_ADOPTION]

    @property
    def adoption_share(self) -> float | None:
        """Still-serving share of assessable runtimes, or `None`.

        `None` over an empty live census rather than `1.0` or `0.0`. A
        share of 1.0 over zero is a green adoption rate; a share of 0.0
        over zero is a claim that runtimes arrived and none was still
        serving. Neither happened.
        """
        n = self.assessable_count
        if n == 0:
            if EMPTY_LIVE_CENSUS_IS_GREEN:
                return 1.0
            return None
        return self.by_classification[STATE_STILL_SERVING] / n

    @property
    def share_absent_because(self) -> str | None:
        if self.assessable_count:
            return None
        if EMPTY_LIVE_CENSUS_IS_GREEN:
            return None
        return EMPTY_CENSUS_ABSENCE

    def document(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "criterion": "SC-017",
            "four_weeks_seconds": FOUR_WEEKS_SECONDS,
            "four_weeks_basis": FOUR_WEEKS_BASIS,
            "now": self.now,
            "live": self.live,
            "synthetic": self.synthetic,
            "runtimes": [row.document() for row in self.runtimes],
            "by_classification": {
                state: self.by_classification[state] for state in STATES
            },
            "state_meanings": dict(STATE_MEANINGS),
            "install_count": self.install_count,
            "non_adoption_count": self.non_adoption_count,
            "assessable_count": self.assessable_count,
            "adoption_share": self.adoption_share,
            "share_absent_because": self.share_absent_because,
            "threshold_applied": None,
            "threshold_absent_because": NO_THRESHOLD,
            "od36": OD36_RESIDUAL,
        }


def _counted_as_install(classification: str) -> bool:
    if classification == STATE_NON_ADOPTION:
        return NON_ADOPTION_COUNTED_AS_INSTALL
    return classification in {
        STATE_NOT_DEMONSTRATED,
        STATE_NOT_YET_ASSESSABLE,
        STATE_STILL_SERVING,
    }


def classify(observation: RuntimeObservation, now: float) -> RuntimeAdoption:
    """One runtime, against SC-017's four-week criterion."""
    if observation.installed_at is not None and now < observation.installed_at:
        raise AdoptionInputError(
            f"{observation.deployment_id!r} has now={now} before "
            f"installed_at={observation.installed_at}. A classification "
            "against a future install is not a measurement."
        )

    installed_at = observation.installed_at
    four_week_mark = (
        None if installed_at is None else installed_at + FOUR_WEEKS_SECONDS
    )
    classification = _state(observation, now, four_week_mark)
    return RuntimeAdoption(
        deployment_id=observation.deployment_id,
        classification=classification,
        counted_as_install=_counted_as_install(classification),
        installed_at=installed_at,
        demonstrated_at=observation.demonstrated_at,
        last_served_at=observation.last_served_at,
        four_week_mark=four_week_mark,
    )


def _state(
    observation: RuntimeObservation,
    now: float,
    four_week_mark: float | None,
) -> str:
    if observation.installed_at is None:
        return STATE_NO_INSTALL
    if observation.demonstrated_at is None:
        return STATE_NOT_DEMONSTRATED
    assert four_week_mark is not None
    if not FOUR_WEEK_WAIT_IS_DROPPED and now < four_week_mark:
        return STATE_NOT_YET_ASSESSABLE
    last = observation.last_served_at
    if last is not None and last >= four_week_mark:
        return STATE_STILL_SERVING
    return STATE_NON_ADOPTION


def report(
    observations: Iterable[RuntimeObservation] = (),
    *,
    now: float,
    live: bool = False,
    synthetic: bool | None = None,
) -> AdoptionCensus:
    """Classify each handed runtime, or report that none is assessable.

    An empty sequence is the honest production state (OD-36). It is not
    a green adoption rate. `live` defaults to False: no production
    runtime is serving. A fixture may supply synthetic observations to
    prove the classifier; those are marked `synthetic=True`, `live=False`.
    """
    rows: Sequence[RuntimeObservation] = tuple(observations)
    seen: set[str] = set()
    classified: list[RuntimeAdoption] = []
    by_classification: dict[str, int] = {state: 0 for state in STATES}
    for observation in rows:
        if observation.deployment_id in seen:
            raise AdoptionInputError(
                f"{observation.deployment_id!r} appears twice. SC-017 "
                "classifies each deployed runtime once."
            )
        seen.add(observation.deployment_id)
        row = classify(observation, now)
        classified.append(row)
        by_classification[row.classification] += 1

    if synthetic is None:
        synthetic = bool(rows) and not live

    return AdoptionCensus(
        now=now,
        live=live,
        synthetic=synthetic,
        runtimes=tuple(classified),
        by_classification=by_classification,
    )


def module_source() -> str:
    """This module's own text, for the arm that reads it for a substitution."""
    module = inspect.getmodule(report)
    if module is None:
        raise ModuleTextUnavailable(
            "inspect.getmodule() could not locate the module defining "
            "report(), so this module's own text cannot be read. "
            "Refused rather than returned empty: the arm that calls "
            "this searches the text for an invented window or a green "
            "share, and text that was never read finds none either."
        )
    return inspect.getsource(module)
