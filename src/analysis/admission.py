"""T073 — the published-specification fetch and FR-044's state classification.

**Requirement**: FR-044, authorised by **OD-18**. FR-002 makes a published
machine-readable specification an admission criterion; this is the check that
enforces it, and the criterion it enforces is the only reason v1's supported
population is narrower than "any HTTP target".

## The shape of the classification, and why it has six members rather than four

FR-044 requires **at least** four distinguishable states and names them:

    published and non-empty; absent; present but not readable by the
    configured credential; and present, readable and carrying no operations

Those four are `PUBLISHED_NON_EMPTY`, `ABSENT`, `UNREADABLE_BY_CREDENTIAL` and
`READABLE_NO_OPERATIONS`, and only the first is admitted. Two more exist, both
because the alternative is **misclassifying evidence into one of the four**, and
a misclassification here is worse than an extra state: FR-047 makes the state
name the "after" term of a drift signal, and FR-044 requires the rejection to
say what the operator would have to change. Telling an operator to publish a
specification they already publish is a wrong answer, not a coarse one.

- **`UNPARSEABLE`** — the origin answered, the credential was accepted, and the
  bytes are not a specification this system can read. Folding it into
  `READABLE_NO_OPERATIONS` would report "your specification carries no
  operations" about a document nobody managed to read, and FR-044's own
  sentence — *a specification that fetches successfully but carries no
  operations MUST NOT be read as a deployment that serves nothing* — is the
  same mistake one step further along.
- **`UNREACHABLE`** — nothing answered at all: a transport failure, or a server
  error. Folding it into `ABSENT` would report "this target publishes no
  specification" on the evidence that the target was down.

Both additions are non-admissible, so the admitted set is unchanged and remains
exactly `PUBLISHED_NON_EMPTY`. `FR_044_STATES` names the four the requirement
enumerates so that a coverage floor can assert over the requirement's own list
rather than over whatever this module happens to define.

## The three layers, and why the classifier is the middle one

    transport  ->  FetchResponse  ->  classify  ->  Classification  ->  check
    (evidence)     (what an        (FR-044's       (state +          (the
                    origin said)    only judge)     operations)       decision)

**A transport never names a state.** It reports what an origin did — a status,
a body, a transport error — and nothing else. This is the whole reason
`classify` is testable: if a transport returned `ABSENT`, then a test that
asserts "the absent fixture classifies as absent" would be asserting that a
fixture is what it says it is. Two transports are supplied, `fetch_from_file`
and `fetch_over_http`, and both do the same narrow job.

**`classify` never raises for a classifiable response, and never falls
through.** Every branch is enumerated and the residue raises
`UnclassifiableResponse`. A fall-through would make one state the default, and
a default state is a classifier stated as a complement — the defect
[finding 032](../../specs/002-spec-aware-agent-runtime/findings/032-removal-proof-signal-fabrication.md)
records, where the accepting set for one outcome was "none of the others".

**`check` returns a decision and does not raise on rejection.** FR-044 and T074
both require a rejection to be a supportable answer that is recorded, not an
error that propagates. `gate` is the separate function that refuses to start
anything, and it is the only thing here that raises about a rejection.

## What is supported, and what is unsupported rather than best-effort

FR-053: a target shape is **supported** only where a committed fixture and an
asserted expected output exist. One specification shape has both — the
`served_operation_set` document of `src/contracts/schemas.py`, which is what
`tests/fixtures/reference-app/served_operations.json` is. **OpenAPI, JSON
Schema, gRPC reflection and WSDL are unsupported**, and a target publishing one
of them classifies `UNPARSEABLE` and is rejected with that state named. That is
a narrower product than "reads OpenAPI" and it is the honest one: an OpenAPI
reader written here would have no committed fixture and no asserted expected
output, which FR-053 forbids describing as support.

`SUPPORTED_SPECIFICATION_SHAPES` names the set, so widening it is an edit to a
declaration rather than a quiet consequence of a parser growing a branch.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

# ---------------------------------------------------------------------------
# The states.

#: Published and non-empty. The only admissible state (FR-044).
PUBLISHED_NON_EMPTY = "published_non_empty"
#: The origin answered and there is no specification at the named location, or
#: no location was configured at all.
ABSENT = "absent"
#: Present, and the configured credential does not open it.
UNREADABLE_BY_CREDENTIAL = "unreadable_by_credential"
#: Fetched, read, parsed — and carrying zero operations.
READABLE_NO_OPERATIONS = "readable_no_operations"
#: Fetched and read, and not a specification shape this system supports.
UNPARSEABLE = "unparseable"
#: Nothing answered: a transport failure or a server error.
UNREACHABLE = "unreachable"

#: The four FR-044 enumerates, in the requirement's own order. A coverage floor
#: asserts over this rather than over `STATES`, so that adding a state here
#: cannot dilute the requirement's list.
FR_044_STATES: tuple[str, ...] = (
    PUBLISHED_NON_EMPTY,
    ABSENT,
    UNREADABLE_BY_CREDENTIAL,
    READABLE_NO_OPERATIONS,
)

#: Every state this classifier can return, the two additions included.
STATES: tuple[str, ...] = (*FR_044_STATES, UNPARSEABLE, UNREACHABLE)

#: FR-044: "MUST admit only the first". One member, and it is a frozenset
#: rather than a bare comparison so that a second admissible state would be a
#: visible edit here rather than an `or` somewhere in a branch.
ADMISSIBLE_STATES = frozenset({PUBLISHED_NON_EMPTY})

#: FR-053's supported-shape declaration. See the module docstring.
SUPPORTED_SPECIFICATION_SHAPES: tuple[str, ...] = ("served_operation_set",)

#: What the evidence string says when nothing was configured. Written out
#: rather than left as an empty string, so a recorded decision distinguishes
#: "asked nowhere" from "asked somewhere and the name was lost".
_NO_LOCATION = "<no specification location configured>"


class AdmissionError(RuntimeError):
    """An admission check that could not be performed as described."""


class UnclassifiableResponse(AdmissionError):
    """Evidence that matches no enumerated state.

    Raised rather than defaulted. A classifier with a fall-through has one
    state whose accepting set is "not any of the others", and every unforeseen
    shape lands in it silently.
    """


class NotAdmitted(AdmissionError):
    """`gate` refused to start a session against a non-admissible target.

    Carries the state and the criterion as **attributes** rather than only in
    the message, so a caller — and a test — can assert on the named state and
    the named criterion instead of matching words in a string. A test that
    matched words would pass against any guard anywhere that used the same
    word, which is how a redaction test in this tree once passed with its
    mechanism deleted.
    """

    def __init__(self, decision: "AdmissionDecision") -> None:
        super().__init__(decision.operator_message())
        self.decision = decision
        self.state = decision.state
        self.criterion = decision.criterion


# ---------------------------------------------------------------------------
# The criteria.


@dataclass(frozen=True)
class AdmissionCriterion:
    """One admission criterion, and what a target must do to satisfy it.

    `rule_id` is in the record for the reason FR-011 puts one on every denial:
    the rule is part of the decision, not an annotation on it. The namespace is
    `ADM-`, disjoint from the filesystem `FS-` and egress `EG-` registries, so
    a rule identifier read out of a record is unambiguous about which registry
    declared it.
    """

    rule_id: str
    #: The state this criterion is the verdict for.
    state: str
    #: What the criterion requires. The same words whichever target fails it.
    criterion: str
    #: What was found, and why it fails the criterion above.
    reason: str
    #: What the operator would have to change (FR-044). Empty only for the
    #: admitted criterion, where nothing has to change.
    operator_action: str

    def __post_init__(self) -> None:
        if not self.rule_id.startswith("ADM-"):
            raise AdmissionError(
                f"{self.rule_id!r} is not in the admission rule namespace. "
                "Admission rules are `ADM-`, filesystem rules `FS-` and "
                "egress rules `EG-`; one shared namespace would make a rule "
                "identifier in a record ambiguous about which registry "
                "declared it."
            )
        if not self.criterion or not self.reason:
            raise AdmissionError(
                f"{self.rule_id}: a criterion needs both what it requires and "
                "what was found. FR-044 requires the rejection to name the "
                "criterion that failed, and a criterion with no text names "
                "nothing."
            )
        admissible = self.state in ADMISSIBLE_STATES
        if admissible and self.operator_action:
            raise AdmissionError(
                f"{self.rule_id}: an admissible state carries no operator "
                "action, because nothing has to change. An action here would "
                "be read as an outstanding requirement against an admitted "
                "target."
            )
        if not admissible and not self.operator_action:
            raise AdmissionError(
                f"{self.rule_id}: {self.state} is a rejection and FR-044 "
                "requires it to name what the operator would have to change. "
                "A rejection with no remedy is the failure mode the "
                "requirement's own Edge Cases section describes — a product "
                "that declines and explains nothing."
            )


_CRITERIA: tuple[AdmissionCriterion, ...] = (
    AdmissionCriterion(
        rule_id="ADM-001",
        state=PUBLISHED_NON_EMPTY,
        criterion="the target publishes a machine-readable specification of "
                  "what it serves, at operation granularity (FR-002, OD-18)",
        reason="the specification was fetched, read and parsed, and it "
               "describes at least one operation",
        operator_action="",
    ),
    AdmissionCriterion(
        rule_id="ADM-002",
        state=ABSENT,
        criterion="the target publishes a machine-readable specification of "
                  "what it serves, at operation granularity (FR-002, OD-18)",
        reason="there is no specification at the configured location, so "
               "nothing describes what this deployment serves",
        operator_action="publish a machine-readable specification at "
                        "operation granularity and configure its location, or "
                        "point the configured location at the one the target "
                        "already publishes. v1 does not discover operations "
                        "by probing the target and does not accept an "
                        "operator's declaration of them (FR-002).",
    ),
    AdmissionCriterion(
        rule_id="ADM-003",
        state=UNREADABLE_BY_CREDENTIAL,
        criterion="the configured credential can read the published "
                  "specification (FR-044)",
        reason="the specification is present and the configured credential "
               "was refused, so what the deployment serves is unknown to this "
               "system even though the target describes it",
        operator_action="grant the configured credential read access to the "
                        "specification, or configure a credential that "
                        "already has it. The specification is there; nothing "
                        "about the target has to change except who may read "
                        "it.",
    ),
    AdmissionCriterion(
        rule_id="ADM-004",
        state=READABLE_NO_OPERATIONS,
        criterion="the published specification describes at least one "
                  "operation (FR-044)",
        reason="the specification was fetched and read successfully and "
               "describes zero operations. FR-044 forbids reading this as a "
               "deployment that serves nothing: a fetch that succeeded and an "
               "empty result are two facts, and the second does not follow "
               "from the first",
        operator_action="find out why the specification is empty before "
                        "changing anything else — an empty document from a "
                        "deployment that is serving traffic usually means the "
                        "generator ran against the wrong build or the wrong "
                        "route table, and publishing operations into it "
                        "without establishing that would admit a target on a "
                        "specification nobody has reconciled against what it "
                        "serves.",
    ),
    AdmissionCriterion(
        rule_id="ADM-005",
        state=UNPARSEABLE,
        criterion="the published specification is in a shape this version "
                  "supports (FR-053: " + ", ".join(SUPPORTED_SPECIFICATION_SHAPES)
                  + ")",
        reason="the specification was fetched and read and is not a shape "
               "this version can parse, so no operation list could be "
               "obtained from it",
        operator_action="publish the specification as a "
                        "`served_operation_set` document, which is the one "
                        "shape v1 supports. OpenAPI, JSON Schema, gRPC "
                        "reflection and WSDL are unsupported rather than "
                        "best-effort (FR-053) — there is no committed fixture "
                        "and no asserted expected output for any of them, and "
                        "widening this is a v2 scope decision rather than a "
                        "configuration change.",
    ),
    AdmissionCriterion(
        rule_id="ADM-006",
        state=UNREACHABLE,
        criterion="the location the specification is published at answers "
                  "(FR-044)",
        reason="nothing answered at the configured location — a transport "
               "failure or a server error — so whether a specification is "
               "published there is unknown. This is not evidence that the "
               "target publishes none",
        operator_action="make the specification's location reachable from "
                        "wherever admission runs, then re-run admission. "
                        "Nothing about the specification itself is known to "
                        "be wrong: this state says the question was never "
                        "answered.",
    ),
)

CRITERIA: Mapping[str, AdmissionCriterion] = {c.state: c for c in _CRITERIA}
CRITERIA_BY_ID: Mapping[str, AdmissionCriterion] = {c.rule_id: c for c in _CRITERIA}

# Every state has exactly one criterion and every criterion a distinct rule id.
# Asserted at import, because a state with no criterion would reject with a
# `KeyError` — a generic failure wearing no state and no rule — and two states
# sharing a rule id would make "a named criterion" true and useless.
if set(CRITERIA) != set(STATES):
    raise AdmissionError(
        f"every state needs exactly one criterion; {set(CRITERIA) ^ set(STATES)} "
        "is on one side only"
    )
if len(CRITERIA_BY_ID) != len(_CRITERIA):
    raise AdmissionError(
        "two admission criteria share a rule identifier, so a record naming "
        "one does not say which criterion failed"
    )


def criterion_for(state: str) -> AdmissionCriterion:
    """The criterion for `state`, or a refusal naming the state.

    A lookup rather than a chain of branches, and a refusal rather than a
    default: the criterion is what FR-044 requires the rejection to name, and
    a fallback criterion would name the same thing for every state.
    """
    try:
        return CRITERIA[state]
    except KeyError:
        raise AdmissionError(
            f"{state!r} is not one of FR-044's classified states "
            f"({list(STATES)}), so no criterion declares what it fails."
        ) from None


# ---------------------------------------------------------------------------
# The transport layer: evidence, never a verdict.


@dataclass(frozen=True)
class FetchResponse:
    """What an origin said when asked for its published specification.

    Deliberately HTTP-shaped, because the target's own external interface is
    where FR-003 puts every access to it and status codes are the vocabulary
    that interface already has. The filesystem transport adapts onto the same
    shape rather than inventing a second one — two evidence types would need
    two classifiers, and the second one is the one nobody tests.

    `status` is `None` exactly when nothing answered. `location` is what was
    asked for, and an empty `location` means no location was configured, which
    is evidence in its own right rather than a missing argument.
    """

    status: int | None
    body: bytes | None
    location: str
    transport_error: str | None = None

    def __post_init__(self) -> None:
        if self.status is None and not self.transport_error:
            raise AdmissionError(
                "a response with no status has to say what went wrong. "
                "Without it the classifier cannot tell 'nothing answered' "
                "from 'nobody asked', and those are different states."
            )
        if self.status is not None and self.transport_error:
            raise AdmissionError(
                f"status {self.status} arrived together with a transport "
                f"error ({self.transport_error!r}). One of the two is wrong, "
                "and guessing which would put a state on evidence that "
                "contradicts itself."
            )


#: What no configured location looks like. A distinct constructor rather than
#: an empty string a caller might pass by accident.
def no_location_configured() -> FetchResponse:
    """The evidence that no specification location was configured at all.

    FR-001 makes an absent served-operation set a loud startup failure, and
    FR-044 makes an absent specification an admission rejection. This is the
    second of those: an operator who configured nothing gets the `ABSENT`
    criterion and its remedy, not a stack trace.
    """
    return FetchResponse(status=404, body=None, location="")


def fetch_from_file(
    path: str | Path,
    *,
    read: Callable[[Path], bytes] | None = None,
) -> FetchResponse:
    """Fetch a specification from the filesystem, as evidence.

    The three outcomes map onto the status vocabulary above: a missing file is
    404, a file the process may not read is 403, and a readable file is 200.
    The mapping is stated here, in the transport, precisely so that the
    classifier has one evidence shape to reason about.

    `read` is a seam for the one case a test cannot always reach — a file the
    test process is refused, which `chmod 000` does not produce for uid 0.
    """
    target = Path(path)
    reader = (lambda p: p.read_bytes()) if read is None else read
    location = f"file://{target}"
    try:
        return FetchResponse(status=200, body=reader(target), location=location)
    except FileNotFoundError:
        return FetchResponse(status=404, body=None, location=location)
    except IsADirectoryError:
        return FetchResponse(status=404, body=None, location=location)
    except PermissionError:
        return FetchResponse(status=403, body=None, location=location)
    except OSError as exc:
        return FetchResponse(
            status=None, body=None, location=location,
            transport_error=f"{type(exc).__name__}: {exc}")


def fetch_over_http(
    url: str,
    *,
    credential: str | None = None,
    timeout_seconds: float,
    opener: Callable[[urllib.request.Request, float], tuple[int, bytes]] | None = None,
) -> FetchResponse:
    """Fetch a specification over the target's own external interface.

    `timeout_seconds` has no default, for the reason `Ceilings` has none: a
    fetch with an unbounded timeout is an admission check that can hang
    forever, and the number belongs to whoever configured the deployment
    rather than to this module.

    **The credential travels in a header and never into a URL**, because a URL
    is what every layer between here and the origin logs.
    """
    request = urllib.request.Request(url, method="GET")
    request.add_header("Accept", "application/json")
    if credential:
        request.add_header("Authorization", f"Bearer {credential}")

    if opener is None:
        def opener(req: urllib.request.Request, timeout: float) -> tuple[int, bytes]:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return int(response.status), response.read()

    try:
        status, body = opener(request, timeout_seconds)
        return FetchResponse(status=status, body=body, location=url)
    except urllib.error.HTTPError as exc:
        # A status the origin chose. It is evidence, not a failure: 401 and 404
        # are two of FR-044's states and losing them into one exception type is
        # how `UNREADABLE_BY_CREDENTIAL` would collapse into `ABSENT`.
        try:
            body = exc.read()
        except Exception:  # pragma: no cover - the body is optional evidence
            body = None
        return FetchResponse(status=int(exc.code), body=body, location=url)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return FetchResponse(
            status=None, body=None, location=url,
            transport_error=f"{type(exc).__name__}: {exc}")


# ---------------------------------------------------------------------------
# The parser: one supported shape, and a refusal for everything else.


class SpecificationNotSupported(AdmissionError):
    """Bytes that are not a specification shape this version reads."""


def parse_operations(body: bytes) -> tuple[Mapping[str, Any], ...]:
    """The operation list a supported specification describes.

    Raises `SpecificationNotSupported` for anything else, including a document
    that is valid JSON in an unsupported shape. **An unsupported shape is not
    an empty operation list**: returning `()` for an OpenAPI document would
    classify it `READABLE_NO_OPERATIONS` and tell the operator their
    specification is empty, which is false and sends them to the wrong place.
    """
    try:
        document = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SpecificationNotSupported(
            f"the bytes are not UTF-8 JSON ({exc}). Supported shapes: "
            f"{list(SUPPORTED_SPECIFICATION_SHAPES)}."
        ) from None

    if not isinstance(document, Mapping):
        raise SpecificationNotSupported(
            f"the document is a {type(document).__name__} at its root; a "
            "`served_operation_set` is an object."
        )
    operations = document.get("operations")
    if operations is None:
        raise SpecificationNotSupported(
            "the document carries no `operations` key, so it is not a "
            "`served_operation_set`. OpenAPI, JSON Schema, gRPC reflection "
            "and WSDL are unsupported rather than best-effort (FR-053): there "
            "is no committed fixture and no asserted expected output for any "
            "of them."
        )
    if not isinstance(operations, Sequence) or isinstance(operations, (str, bytes)):
        raise SpecificationNotSupported(
            f"`operations` is a {type(operations).__name__}; a "
            "`served_operation_set` describes operations as a list."
        )
    for index, operation in enumerate(operations):
        if not isinstance(operation, Mapping):
            raise SpecificationNotSupported(
                f"operations[{index}] is a {type(operation).__name__}; each "
                "operation is an object."
            )
        if not operation.get("operation_id"):
            raise SpecificationNotSupported(
                f"operations[{index}] names no `operation_id`. FR-002 "
                "requires the served-operation set at **operation** "
                "granularity, and an operation with no identifier cannot be "
                "resolved against, inspected under FR-020, or denied by name."
            )
    return tuple(operations)


# ---------------------------------------------------------------------------
# The classifier. FR-044's only judge.


@dataclass(frozen=True)
class Classification:
    """The state a response was classified into, and what it yielded.

    `operations` is non-empty exactly when `state == PUBLISHED_NON_EMPTY`, and
    that pairing is enforced rather than documented: a classification carrying
    operations in a rejected state would be a set some caller could act on
    after admission refused.
    """

    state: str
    operations: tuple[Mapping[str, Any], ...]
    #: What the classifier read off the evidence, for the record. Never a
    #: verdict — the verdict is `state`.
    evidence: str

    def __post_init__(self) -> None:
        if self.state not in STATES:
            raise AdmissionError(
                f"{self.state!r} is not one of the classified states "
                f"({list(STATES)})"
            )
        if self.state == PUBLISHED_NON_EMPTY and not self.operations:
            raise AdmissionError(
                "PUBLISHED_NON_EMPTY with no operations is the state FR-044 "
                "singles out — a specification that fetched successfully and "
                "carries nothing — recorded under the one state that admits."
            )
        if self.state != PUBLISHED_NON_EMPTY and self.operations:
            raise AdmissionError(
                f"{self.state} carries {len(self.operations)} operation(s). A "
                "rejected classification that hands back an operation list is "
                "a set a caller can act on after admission refused it."
            )


def classify(response: FetchResponse) -> Classification:
    """FR-044's classification, over evidence and nothing else.

    Every branch is enumerated and the residue raises. The order matters and
    is the requirement's: reachability first, because an unanswered question
    has no other answer; then the credential, because a refusal says the
    specification is *there*; then absence; then the parse; then emptiness.

    **`READABLE_NO_OPERATIONS` is decided in exactly one place** — the
    `if not operations` below — so a removal proof that deletes it can be
    attributed to it. Two branches deciding the same thing would make each
    other's proof vacuous.
    """
    where = response.location or _NO_LOCATION
    if response.status is None:
        return Classification(
            state=UNREACHABLE, operations=(),
            evidence=f"nothing answered at {where}: {response.transport_error}")
    if response.status >= 500:
        return Classification(
            state=UNREACHABLE, operations=(),
            evidence=f"status {response.status} from {where}")
    if response.status in (401, 403, 407):
        return Classification(
            state=UNREADABLE_BY_CREDENTIAL, operations=(),
            evidence=f"status {response.status} from {where}")
    if response.status in (404, 410):
        return Classification(
            state=ABSENT, operations=(),
            evidence=f"status {response.status} from {where}")
    if response.status != 200:
        raise UnclassifiableResponse(
            f"status {response.status} from {where} matches no "
            "enumerated state. It is refused rather than folded into the "
            "nearest one: a classifier with a fall-through has one state "
            "whose accepting set is 'none of the others', and every "
            "unforeseen shape lands in it silently. Add a branch, and a "
            "state if the evidence needs one."
        )
    if response.body is None:
        raise UnclassifiableResponse(
            f"status 200 from {where} with no body. A transport "
            "reported success and produced nothing to read, which is a "
            "transport defect rather than a state of the specification."
        )

    try:
        operations = parse_operations(response.body)
    except SpecificationNotSupported as exc:
        return Classification(
            state=UNPARSEABLE, operations=(),
            evidence=f"status 200 from {where}, "
                     f"{len(response.body)} bytes: {exc}")

    if not operations:
        return Classification(
            state=READABLE_NO_OPERATIONS, operations=(),
            evidence=f"status 200 from {where}, parsed as a "
                     "served_operation_set describing 0 operations")
    return Classification(
        state=PUBLISHED_NON_EMPTY, operations=operations,
        evidence=f"status 200 from {where}, parsed as a "
                 f"served_operation_set describing {len(operations)} "
                 "operation(s)")


# ---------------------------------------------------------------------------
# The decision, and the gate that will not step past it.


@dataclass(frozen=True)
class AdmissionDecision:
    """FR-044's outcome for one target: admitted, or rejected and why.

    Every field FR-044 requires on a rejection is here and is checked for
    coherence in `__post_init__`. T074 persists this; nothing here writes.
    """

    deployment_id: str
    admitted: bool
    state: str
    criterion: AdmissionCriterion
    operations: tuple[Mapping[str, Any], ...]
    evidence: str
    specification_source: str

    def __post_init__(self) -> None:
        if self.criterion.state != self.state:
            raise AdmissionError(
                f"the decision found {self.state} and carries the criterion "
                f"for {self.criterion.state}. A record whose state and "
                "criterion disagree names two different findings and is "
                "evidence for neither."
            )
        if self.admitted != (self.state in ADMISSIBLE_STATES):
            raise AdmissionError(
                f"admitted={self.admitted} with state {self.state}; FR-044 "
                f"admits exactly {sorted(ADMISSIBLE_STATES)}. A decision that "
                "can disagree with its own state is a gate with two answers."
            )

    @property
    def rule_id(self) -> str:
        return self.criterion.rule_id

    def operator_message(self) -> str:
        """The rejection as FR-044 requires it to be stated.

        Three named things: the state found, the criterion that failed, and
        what the operator would have to change. Assembled from the criterion
        registry rather than written per call site, so that a rejection's
        wording cannot drift between the place it is raised and the place it is
        recorded.
        """
        if self.admitted:
            return (
                f"{self.deployment_id} admitted: state {self.state}, "
                f"criterion {self.criterion.rule_id} satisfied "
                f"({self.criterion.criterion}). {self.evidence}"
            )
        return (
            f"{self.deployment_id} NOT admitted.\n"
            f"  specification state   {self.state}\n"
            f"  criterion failed      {self.criterion.rule_id} — "
            f"{self.criterion.criterion}\n"
            f"  what was found        {self.criterion.reason}\n"
            f"  evidence              {self.evidence}\n"
            f"  to change this        {self.criterion.operator_action}\n"
            "No agent session is started against this target (FR-044)."
        )


def check(
    response: FetchResponse,
    *,
    deployment_id: str,
) -> AdmissionDecision:
    """Classify `response` and decide. Returns a rejection; never raises one.

    FR-044 and T074 both make a rejection a supportable answer that is
    retained. A `check` that raised would make the recorded population the
    admitted one, and the share of targets rejected — SC-018's subject —
    unrecoverable from the store.

    It still raises for evidence it cannot classify (`UnclassifiableResponse`),
    because that is not a state of the target.
    """
    if not deployment_id:
        raise AdmissionError(
            "an admission decision needs the deployment identity it is about "
            "(FR-035, FR-002). A decision with no subject cannot be read back "
            "for the target it admitted or refused."
        )
    classification = classify(response)
    return AdmissionDecision(
        deployment_id=deployment_id,
        admitted=classification.state in ADMISSIBLE_STATES,
        state=classification.state,
        criterion=criterion_for(classification.state),
        operations=classification.operations,
        evidence=classification.evidence,
        specification_source=response.location,
    )


def gate(decision: AdmissionDecision, start: Callable[[], Any]) -> Any:
    """Call `start` if and only if the decision admitted the target.

    This is FR-044's *"MUST NOT start an agent session against that target"*,
    as a mechanism. The refusal is `raise` rather than `return None`, because a
    caller that ignores a return value starts the session anyway and a caller
    that ignores an exception does not exist.

    `start` is a nullary callable so that this function cannot be mistaken for
    the thing that knows how to start a session. It knows one thing: whether
    anything may be started at all.
    """
    if not decision.admitted:
        raise NotAdmitted(decision)
    return start()
