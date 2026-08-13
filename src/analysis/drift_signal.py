"""T139 and T140 — the drift signal, as a **sum over two shapes** (FR-031, FR-047).

**Requirement**: FR-031 — *"Every drift signal MUST state which of the two clocks
moved, the artifact versions before and after, and the deployment identity it
applies to."*

**Narrowed by FR-047**, and the narrowing is the whole reason this module holds
two types rather than one: *"Where the drift signal is a failed re-fetch under
FR-047 there is no 'after' artifact version to state, because no artifact was
obtained. In that one case the after term is the specification state found,
named from FR-044's four-state classification, together with the timestamp of
the last successful fetch."* **The authorising decision is OD-21.**

## Why this is a sum and not a product with an optional `after`

The cheap encoding is one record with `version_after: str | None`. It is
rejected here, and not on taste.

A `None` in that field has two readings that no consumer can tell apart: *no
artifact was obtained* — FR-047's case, a fact about the world — and *nobody
filled it in*, a fact about the code path that built the record. This
repository's recorded worst defect class is exactly that collapse. The
wall-clock numerator was a missing quantity indistinguishable from a measured
zero; `spend_usd: float | None` exists in `src/runtime/providers/` precisely to
hold UNPRICED apart from COST NOTHING. An optional `version_after` would
reintroduce it at the one place where the distinction is the requirement rather
than an implementation detail: FR-047's whole content is that the fetch
**failed**, and a record that cannot distinguish a failed fetch from an
unfilled field cannot state it.

So `FailedRefetch` **has no `version_after` attribute at all**. Reading one is
an `AttributeError` at runtime and an error under `mypy`, rather than a `None`
that flows onward. Absence of the field is the mechanism; a validator saying
*"this field must be None on this variant"* would be the product type again
with a rule bolted on, and rules can be removed while a missing attribute
cannot.

`Reading` was already built for this at T137: it *"names no successor and
nothing here requires that it get one"*, and `compare` is a module function
rather than a method so that a before-reading is a complete value. This module
is the consumer that construction was for.

## What each shape consumes rather than restates

**`ArtifactDrift` (T139)** is built from T137's `Movement` and from nothing
else. `compare_each` already answers FR-031's *which of the two clocks moved*,
one movement per clock, each computed from that clock's own pair. Restating
that comparison here would be a second detector that can disagree with the
first.

**`FailedRefetch` (T140)** is built from a deployment-clock `Reading` and
FR-044's classifier vocabulary. Both come from elsewhere:

- the three FR-031 terms that survive the narrowing — clock, deployment
  identity, version before — all come off the one `Reading`, so they cannot
  disagree with each other. `reading()` has already refused a blank deployment
  identity and a blank version, so nothing here re-guards them;
- the specification state is `src/analysis/admission.py`'s vocabulary,
  subtracted rather than re-listed. See below.

## The specification-state vocabulary, and the corpus that decided its extent

FR-031's narrowing says the state is *"named from FR-044's four-state
classification"*, and FR-047's entering-stale clause says *"any of FR-044's
three non-admissible states"*. Read literally that is a three-member domain:
`absent`, `unreadable_by_credential`, `readable_no_operations`.

**Three is too narrow, and the committed corpus is what shows it.** T157's
`tests/fixtures/spec-withdrawn/corpus.json` declares the `withdraw-past-ceiling`
scenario with two fetches in state `unreachable`, and calls whose
`specification_state_last_found` is `unreachable`. `unreachable` is not one of
FR-044's four: `admission.py` declares it and `unparseable` as two additions its
classifier can return beyond the requirement's list. A three-member domain here
could not represent a scenario the repository has already committed, which is
the falsification test that decided this.

**Widening to all six is also wrong**, and for the reason this module exists.
`published_non_empty` is a *successful* fetch. Admitting it would let a success
be recorded in the shape that means *no artifact was obtained*, which is the two
arms of the sum overlapping — the same collapse the optional field would have
caused, arriving through the value domain instead of through the type.

So the domain is the classifier's states **minus the admissible one**:
`SPECIFICATION_STATE_FOUND` below is that subtraction, computed from
`admission.py` rather than written out, so a seventh state cannot appear here
unassigned and the list cannot fall behind the classifier.

**The residual, named rather than closed.** That is five members where FR-047's
own sentence says three. The two extra are states FR-047's text does not
enumerate and the corpus does exercise one of them. Whether a target going
`unreachable` should enter the stale state on the same rule as one going
`absent` is **T147's** disposition to state, not this module's — this module
records the state that was found and refuses only the one that would make the
record false. The gap is visible here rather than silently resolved in either
direction.

## Three fields `data-model.md` §2.6 lists that are deliberately not built here

§2.6 gives `DriftSignal` a `detected_at`, a `trigger` — *"scheduled, event, or
path-level probe (FR-046)"* — and a `change_at`, *"present on the synthetic
corpora, which control it; generally absent for the deployment clock on real
traffic"*. None of the three is a term of FR-031, and none is built here.

That is a scope statement rather than an oversight. `trigger`'s vocabulary is
FR-046's, and the scheduler that would produce a value for it is **T141**;
inventing the three names now would fix a vocabulary with no producer against
it, which is how a field ends up meaning whatever the first caller assumed.
`change_at` is a property of a corpus that controls the change time, and the
same §2.6 says it is generally absent on real traffic — a field that is absent
in production and present in fixtures is one the tests would assert on and
nothing would supply.

Adding them later is an addition to these two shapes and not a rewrite of them,
because neither is part of the before/after distinction the sum encodes.

## Where this deliberately stops: the caller-visible marking is T148's

`src/contracts/result.py` carries `Staleness`, FR-047's *"What the caller
sees"* — the marking, the age, the state last found. **Nothing here builds
that**, and the two are not the same record: this is what the drift channel
raises, that is what a result carries.

They do share one fact and they must not carry two vocabularies for it.
`Staleness.specification_state` validates against
`src/contracts/result.SPECIFICATION_STATES`, and
`tests/contract/test_drift_signal.py` asserts that frozenset agrees with the
classifier this module subtracts from — so the drift signal cannot admit a
state the marking would reject, nor the reverse.

**The second fact is not shared, and the difference is load-bearing.** FR-047
asks the caller-visible marking for *"the age of that set"*; FR-031's narrowing
asks this record for *"the timestamp of the last successful fetch"*. Those are
an interval and an instant, and the instant is the primitive: age is
`now - timestamp` and cannot be stored, because it is a fact about a moment
somebody is asking about rather than about the fetch. Carrying age here would
mean storing a number that is wrong immediately after it is written.
`FailedRefetch.age_seconds(now)` derives it instead, on the same signature and
the same no-default-clock rule as `ServedOperationSet.age_seconds`, so the two
records agree by construction rather than by two writers being careful.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, assert_never

from src.analysis.admission import ADMISSIBLE_STATES, STATES
from src.analysis.clocks import CLOCKS, DEPLOYMENT, SOURCE, Movement, Reading

#: The discriminant, carried in `document()` so a serialized signal says which
#: shape it is. Without it the two are told apart only by which keys are
#: present, which is the optional-field ambiguity re-entering at the
#: serialization boundary after the type system was used to exclude it.
ARTIFACT_DRIFT = "artifact_drift"
FAILED_REFETCH = "failed_refetch"

#: The states a *failed* re-fetch can have found: everything the FR-044
#: classifier can report except the admissible one. Subtracted from
#: `admission.STATES` rather than written out — see the module docstring for
#: why the domain is neither FR-047's literal three nor the classifier's six.
SPECIFICATION_STATE_FOUND: frozenset[str] = frozenset(STATES) - ADMISSIBLE_STATES


class DriftSignalError(RuntimeError):
    """A drift signal that would state something untrue about drift."""


def _instant(value: str, *, field: str) -> float:
    """An ISO-8601 instant as epoch seconds, or a refusal naming the value.

    Two branches and not one, because they fail differently. A value that does
    not parse is a value nobody can read; a value that parses **naive** reads
    fine and is wrong by the offset between two machines that nobody wrote
    down. FR-047's ceiling is measured in seconds from this instant, so the
    second is the more dangerous of the two: it produces an age, and an age
    produced from a naive timestamp is compared against the ceiling and
    believed.

    Refuses rather than returning a sentinel, on `served_operations._epoch`'s
    reasoning: a sentinel age flows into the ceiling comparison and answers its
    question with a number nobody computed.
    """
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        raise DriftSignalError(
            f"{field} {value!r} is not an ISO-8601 instant. FR-031's narrowing "
            "carries the timestamp of the last successful fetch so that "
            "FR-047's ceiling can be measured from it, and a value nothing can "
            "parse leaves the ceiling uncomputable against this signal."
        ) from None
    if parsed.tzinfo is None:
        raise DriftSignalError(
            f"{field} {value!r} names no timezone. An age computed from a "
            "naive instant is off by the offset between two machines nobody "
            "recorded, and FR-047's staleness ceiling is measured in seconds "
            "from this instant — so the error is not visible in the answer."
        )
    return parsed.timestamp()


@dataclass(frozen=True)
class ArtifactDrift:
    """T139 — a drift signal where **both** artifact versions were obtained.

    FR-031 unnarrowed: which of the two clocks moved, the versions before and
    after, and the deployment identity. Built from T137's `Movement` through
    `from_movement`, which is the only constructor that should be used — the
    comparison lives in `clocks.compare` and a second one here could disagree
    with it.
    """

    clock: str
    deployment_id: str
    version_before: str
    version_after: str
    #: Which artifact kinds on that clock moved. Beside FR-031's single version
    #: pair rather than instead of it, so a signal can say which artifact moved
    #: as well as which clock.
    kinds_moved: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.clock not in CLOCKS:
            raise DriftSignalError(
                f"{self.clock!r} is not a clock. FR-031 requires a drift "
                f"signal to state which of the **two** clocks moved, and "
                f"data-model.md §2.6 names them {list(CLOCKS)}; a signal on a "
                "third attributes movement to a clock nothing else reads, so "
                "no responder can act on it."
            )
        if not self.deployment_id:
            raise DriftSignalError(
                "a drift signal was raised for no deployment. FR-031 requires "
                "every drift signal to state the deployment identity it "
                "applies to; without one, a responder disabling the affected "
                "operation under FR-030 does not know whose."
            )
        if self.version_before == self.version_after:
            raise DriftSignalError(
                f"a drift signal on the {self.clock!r} clock carries "
                f"{self.version_before!r} as both the before and the after "
                "version. FR-031's content is that the artifact version "
                "changed; a signal whose two versions are equal reports drift "
                "and states none, and the phase's negative control requires "
                "that re-analysing unchanged input produce no signal at all."
            )
        if not self.kinds_moved:
            raise DriftSignalError(
                f"a drift signal on the {self.clock!r} clock names no artifact "
                "kind as moved. A clock's composed version moves only because "
                "some kind on it moved, so a signal that can name none was "
                "built from something other than a comparison — and FR-030's "
                "responder has no affected artifact to act on."
            )

    @classmethod
    def from_movement(cls, movement: Movement) -> "ArtifactDrift":
        """The one constructor: a signal from T137's comparison.

        Refuses an **unmoved** movement. `compare_each` returns one `Movement`
        per clock whether or not it moved, so the unmoved ones are the normal
        case and not an error — but turning one into a signal is a false alarm,
        and this phase's Independent Test names the negative outright:
        *re-analysing unchanged input produces no signal at all*. Use
        `signals_from_movements` to map a comparison to the signals it warrants.
        """
        if not movement.moved:
            raise DriftSignalError(
                f"the {movement.clock!r} clock did not move between "
                f"{movement.version_before!r} and {movement.version_after!r}, "
                "and a drift signal was raised for it anyway. A detector that "
                "signals on an unmoved clock reports drift on a system at "
                "rest, which is the false alarm the phase's negative control "
                "exists to catch."
            )
        return cls(
            clock=movement.clock,
            deployment_id=movement.deployment_id,
            version_before=movement.version_before,
            version_after=movement.version_after,
            kinds_moved=movement.kinds_moved,
        )

    def document(self) -> dict[str, Any]:
        return {
            "signal_kind": ARTIFACT_DRIFT,
            "clock": self.clock,
            "deployment_id": self.deployment_id,
            "version_before": self.version_before,
            "version_after": self.version_after,
            "kinds_moved": list(self.kinds_moved),
        }


@dataclass(frozen=True)
class FailedRefetch:
    """T140 — a drift signal where **no artifact was obtained** (FR-047).

    The narrowed shape. There is deliberately **no `version_after` attribute**:
    reading one raises `AttributeError` and fails `mypy`, rather than yielding
    a `None` that a consumer cannot tell apart from a field nobody filled in.
    See the module docstring — that collapse is the defect class this shape
    exists to avoid.

    The clock is a property rather than a field. FR-047 requires this condition
    *"reported as deployment-clock drift under FR-031"*, and there is no such
    thing as failing to re-fetch source: the re-fetch is of the target's
    published specification. A field that can hold only one value is a field
    that can be set to the other one, so it is not a field.
    """

    deployment_id: str
    #: The last-known-good deployment reading's version. FR-031's *before*
    #: term, which the narrowing leaves unchanged.
    version_before: str
    #: FR-044's classification of what the re-fetch found. One of
    #: `SPECIFICATION_STATE_FOUND`.
    specification_state: str
    #: FR-031's narrowed *after* term, second half: an ISO-8601 instant with a
    #: timezone. An instant and not an age — see the module docstring.
    last_successful_fetch: str

    @property
    def clock(self) -> str:
        """Always the deployment clock (FR-047). See the class docstring."""
        return DEPLOYMENT

    def __post_init__(self) -> None:
        if self.specification_state in ADMISSIBLE_STATES:
            raise DriftSignalError(
                f"a failed re-fetch was recorded as having found "
                f"{self.specification_state!r}, which FR-044 admits. This "
                "shape means *no artifact was obtained*; a successful fetch "
                "recorded in it makes the two arms of the drift signal overlap, "
                "so a success and a failure become indistinguishable — which is "
                "the collapse the sum type was chosen to prevent. A fetch that "
                "succeeded is compared under FR-027 and reported, if it moved, "
                "as an ArtifactDrift."
            )
        if self.specification_state not in SPECIFICATION_STATE_FOUND:
            raise DriftSignalError(
                f"{self.specification_state!r} is not a specification state "
                "src/analysis/admission.py can report. FR-031's narrowing asks "
                "for the state **found**, named from FR-044's classification, "
                "and a string no classifier produces was not found by one."
            )
        _instant(self.last_successful_fetch, field="last_successful_fetch")

    def age_seconds(self, now: float) -> float:
        """Seconds since the last successful fetch, at the moment `now`.

        FR-047's ceiling is *"measured from the last successful fetch"* and its
        caller-visible marking carries *"the age of that set"*. This derives
        that age from the instant this record already holds, so the drift
        signal and the `Staleness` marking cannot state two different ages.

        `now` has no default, on `ServedOperationSet.age_seconds`'s reasoning:
        the age is a fact about a moment the caller is asking about, and a
        module that reads the clock itself cannot be tested against a specific
        one. Negative is possible and is not clamped — a fetch stamped in the
        future is a clock disagreement, and presenting it as age zero would
        report the set as freshly fetched on precisely the evidence that its
        timestamp cannot be trusted.
        """
        return now - _instant(self.last_successful_fetch, field="last_successful_fetch")

    def document(self) -> dict[str, Any]:
        """The record. Note there is no `version_after` key, on purpose.

        A key carrying `null` would restore at the serialization boundary the
        ambiguity the type removed: a consumer reading the document could not
        tell *no artifact was obtained* from *this writer did not set it*. The
        `signal_kind` discriminant is what tells a reader which shape this is,
        and it is present rather than inferred from which keys are missing.
        """
        return {
            "signal_kind": FAILED_REFETCH,
            "clock": self.clock,
            "deployment_id": self.deployment_id,
            "version_before": self.version_before,
            "specification_state": self.specification_state,
            "last_successful_fetch": self.last_successful_fetch,
        }


#: The drift signal, as FR-031-narrowed-by-FR-047 defines it: a sum over the
#: two shapes above. A consumer must handle both arms; there is no member of
#: this type from which `version_after` can be read unconditionally.
DriftSignal = ArtifactDrift | FailedRefetch


def failed_refetch(
    before: Reading,
    *,
    specification_state: str,
    last_successful_fetch: str,
) -> FailedRefetch:
    """T140's constructor, from the last-known-good **deployment** reading.

    Taking a `Reading` rather than three strings is what keeps FR-031's
    surviving terms consistent: the deployment identity and the before version
    come off one object that `reading()` has already refused to build blank, so
    a signal cannot name one deployment's identity beside another's version.
    """
    if before.clock != DEPLOYMENT:
        raise DriftSignalError(
            f"a failed re-fetch was built from a {before.clock!r}-clock "
            "reading. FR-047 requires this condition reported as "
            "**deployment-clock** drift under FR-031, and the re-fetch is of "
            "the target's published specification: there is nothing to fail to "
            f"re-fetch on the {SOURCE!r} clock. Such a reading here would "
            "report a source-derived version as the last-known-good served "
            "surface, which is the two clocks back in one field."
        )
    return FailedRefetch(
        deployment_id=before.deployment_id,
        version_before=before.version,
        specification_state=specification_state,
        last_successful_fetch=last_successful_fetch,
    )


def signals_from_movements(movements: Iterable[Movement]) -> tuple[ArtifactDrift, ...]:
    """The signals a comparison warrants — and **nothing for a clock at rest**.

    `compare_each` returns one `Movement` per clock whether or not it moved.
    This is the filter, and it is the phase's Independent Test in code: *"the
    negative: re-analysing unchanged input produces no signal at all"*. A
    mapping that emitted one signal per movement would report drift on every
    run of a system where nothing changed, and every downstream count of
    *operations disabled* would be measured against a detector that fires
    always.
    """
    return tuple(
        ArtifactDrift.from_movement(movement) for movement in movements if movement.moved
    )


def document_of(signal: DriftSignal) -> Mapping[str, Any]:
    """One dispatch point over the sum, so the arms are enumerated once.

    Written as an exhaustive `match` closed by `assert_never` rather than as a
    call to `signal.document()`, so that `mypy` reports a third variant added
    without a case here. A duck-typed call would accept one silently and the
    new shape would serialize by whatever method it happened to have — which
    is how a variant carrying an unfilled `version_after` would arrive.
    """
    match signal:
        case ArtifactDrift():
            return signal.document()
        case FailedRefetch():
            return signal.document()
        case _:
            assert_never(signal)
