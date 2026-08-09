"""T079 — FR-020's confused-deputy inspection, as the second admission stage.

**The task text is stale on one point and it is the load-bearing one.** T079
and `tasks.md`'s Loose-requirements item 2 both say *"the inspection procedure
is unspecified"*. It was, when they were written. **FR-056**, added 2026-08-03
for exactly this reason — *"FR-020's fail-closed clause was not decidable, and
a fail-closed rule with an undecidable trigger fails open in practice: nothing
ever meets it"* — states a named procedure with three steps and a three-valued
outcome. This module implements FR-056's procedure rather than inventing one.
Loose item 2 is in the position item 6 was in before it was marked
**DISCHARGED**; the correction is reported in the final summary rather than
made here.

**What is still true from the task text**: the property is unmeasured on any
target (**U-44**), FR-020 is a default rather than a finding, and *"naming a
procedure for an unmeasured property does not measure it"*. Nothing here is
evidence that any target does or does not have the behaviour being inspected
for.

## Which confused deputy this is, because the name is ambiguous

Not the agent acting with its own authority on an end user's behalf
(`research/08` §3.1). **The target** issuing outbound requests on the caller's
behalf — the target as the agent's deputy. FR-020 sits inside the egress block,
and the distinction decides the whole design: FR-014's enforcement point
governs traffic leaving *the agent's execution environment*, and a request the
target originates from its own network position **never traverses it**. So the
enforcement point cannot substitute for this inspection, however good it is.
The requests this exists to prevent are invisible to it by construction.

## Where this sits, and why the order is fixed

    T073 (FR-044)  ->  operation list  ->  THIS (FR-020)  ->  admitted surface

FR-020: *"This inspection is the second stage of one admission sequence and
MUST run after FR-044, because the operation list it inspects is the one
FR-044's published specification supplies."* `inspect_admission` takes an
`AdmissionDecision` and refuses a rejected one — there is no operation list to
inspect, and building one here would be this stage inventing the input the
stage above it is responsible for.

## FR-056's procedure, and the one thing each step must not do

Three steps, each of which **MUST return a determinate answer or return
`uninspectable`**. That is why the procedure is decidable although the
underlying question is not: declining is a determinate answer with a defined
consequence.

**Step 1 — resolve the operation to a handler.** Exactly one handler symbol in
the analysed codebase. Zero (an operation served by something outside it, such
as a proxied upstream) or more than one is `uninspectable`.
*Must not*: fall back to a name match, or pick the first of several. Either
would inspect a symbol that may not be the one serving the operation, and
report `clean` about a handler nobody called.

**Step 2 — enumerate outbound call sites reachable from that handler.** The
constructs that count are drawn from a **declared catalogue**, versioned
configuration under FR-012. A call the analyser can classify as neither
outbound nor not-outbound — unresolved dynamic dispatch, reflection, evaluated
source, or a dependency whose body is not in the analysed codebase — makes the
operation `uninspectable`.
*Must not*: read an unresolved call as the absence of an outbound request.
FR-056 says so in its own words, and it is the failure that turns this whole
mechanism into a rubber stamp — most calls in most code are unresolvable to a
first-order analyser, and a procedure that shrugs at them returns `clean` for
everything.

**Step 3 — decide destination influence at each enumerated call site.** Fixed
at build time, or read only from the target's own configuration: not a deputy.
Influenced by any input to the operation: `deputy`. Traceable to neither:
`uninspectable`.
*Must not*: treat "I could not find where this URL came from" as "it is a
constant".

## This is a stated rule set and not a proof

FR-056 requires that in its own words, *"identically to FR-010, and for the
same reason: step 2's catalogue is enumerated rather than derived, and step 3's
question is undecidable in the general case."* Two consequences carried here:

- `CATALOGUE_VERSION` and per-entry `rule_id`s exist so that what the analyser
  counted as an outbound request is reviewable, and the surface strings below
  say *stated rule set* rather than *analysis* or *proof*.
- **The catalogue's review gate is T082's, not this module's.** FR-056 makes
  the catalogue *"versioned configuration under FR-012 and reviewable before it
  takes effect"*; T082 builds that gate. This module carries the version and
  the identifiers the gate will key on, and does not implement the gate.

## The unit of failing closed is the operation

FR-020 says a *target* fails closed and FR-051 says an *operation* does.
FR-056 resolves it: **the operation**. FR-020's target-level sentence is the
degenerate case — where the analysis precondition itself fails, step 1 returns
`uninspectable` for every operation, every operation is denied, and the target
has no callable operation left. No separate target-level threshold is invented
here, and `InspectionReport.denied` is the whole answer either way.

## Both non-clean outcomes are denied, and they are still two outcomes

FR-056: *"both `deputy` and `uninspectable` MUST be denied, and they are
distinguished so that the reason is reportable, not so that they are treated
differently."* `ALLOWED_OUTCOMES` is a one-member frozenset for the same reason
`ADMISSIBLE_STATES` is: a second permitted outcome must be a visible edit here
rather than an `or` inside a branch.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from src.analysis.admission import ADMISSIBLE_STATES, AdmissionDecision, AdmissionError

# ---------------------------------------------------------------------------
# The three outcomes.

#: The operation resolved, every reachable call site was classified, and no
#: enumerated outbound call site has a destination any input can influence.
CLEAN = "clean"
#: At least one enumerated outbound call site has a destination influenced by
#: an input to the operation.
DEPUTY = "deputy"
#: Some step declined. A determinate answer, and denied.
UNINSPECTABLE = "uninspectable"

#: FR-056's three, in the requirement's order.
OUTCOMES: tuple[str, ...] = (CLEAN, DEPUTY, UNINSPECTABLE)

#: FR-056: both `deputy` and `uninspectable` MUST be denied.
ALLOWED_OUTCOMES = frozenset({CLEAN})


class DeputyInspectionError(AdmissionError):
    """An inspection that could not be performed as FR-056 describes."""


class NotAdmittedForInspection(DeputyInspectionError):
    """Asked to inspect a target FR-044 refused."""


# ---------------------------------------------------------------------------
# Step 2's declared catalogue (FR-012, FR-056).


@dataclass(frozen=True)
class OutboundConstruct:
    """One construct the catalogue declares to be an outbound network request.

    `rule_id` is on the entry rather than derived from its position, on FR-011's
    discipline: the rule is part of the finding and not an annotation on it, so
    a `deputy` outcome names which catalogue entry decided it.
    """

    rule_id: str
    #: The dotted name as it is written at a call site, matched against the
    #: resolved qualified name of the callee.
    qualified_name: str
    #: Which argument carries the destination: an index, or a keyword.
    destination_argument: int | str
    justification: str

    def __post_init__(self) -> None:
        if not self.rule_id.startswith("DEP-"):
            raise DeputyInspectionError(
                f"{self.rule_id!r} is not in the deputy-inspection rule "
                "namespace. Deputy rules are `DEP-`, admission rules `ADM-`, "
                "filesystem rules `FS-` and egress rules `EG-`; one shared "
                "namespace would make a rule identifier in a record "
                "ambiguous about which registry declared it."
            )
        if not self.justification:
            raise DeputyInspectionError(
                f"{self.rule_id}: FR-012 requires a reviewable justification "
                "on every entry. An entry with none cannot be reviewed, and "
                "an unreviewable catalogue is the thing FR-056 calls a stated "
                "rule set to avoid calling a proof."
            )


#: The catalogue's version. FR-012 makes it versioned configuration; **T082
#: builds the review gate that must pass before a change to it takes effect**,
#: and this constant is what that gate keys on.
CATALOGUE_VERSION = "1.0.0"

#: **Python only, and stated as a narrowing rather than left to be discovered.**
#: FR-053's discipline applies: a construct is covered only where a committed
#: fixture and an asserted expected output exist. An operation whose handler is
#: not Python is `uninspectable` at step 1, because its symbol is not in the
#: analysed codebase this module can read — which is the correct answer and not
#: a gap, since FR-056 requires declining over answering at all costs.
OUTBOUND_CATALOGUE: tuple[OutboundConstruct, ...] = (
    OutboundConstruct(
        rule_id="DEP-001",
        qualified_name="urllib.request.urlopen",
        destination_argument=0,
        justification="the standard library's general HTTP client. Its first "
                      "argument is a URL or a Request, and either is a "
                      "destination the caller can supply.",
    ),
    OutboundConstruct(
        rule_id="DEP-002",
        qualified_name="urllib.request.Request",
        destination_argument=0,
        justification="constructing a Request does not itself open a socket, "
                      "and it is in the catalogue anyway: the destination is "
                      "fixed here and the opening happens somewhere this "
                      "analyser may not reach. Treating the construction as "
                      "the call site is what keeps a two-step "
                      "build-then-open pattern from reading as no outbound "
                      "request at all.",
    ),
    OutboundConstruct(
        rule_id="DEP-003",
        qualified_name="requests.get",
        destination_argument=0,
        justification="`requests` is the most widely used third-party HTTP "
                      "client; its verb helpers take the URL first.",
    ),
    OutboundConstruct(
        rule_id="DEP-004",
        qualified_name="requests.post",
        destination_argument=0,
        justification="as DEP-003. A POST is still an outbound request the "
                      "target makes on the caller's behalf.",
    ),
    OutboundConstruct(
        rule_id="DEP-005",
        qualified_name="requests.request",
        destination_argument=1,
        justification="the general form; the method is first and the URL "
                      "second.",
    ),
    OutboundConstruct(
        rule_id="DEP-006",
        qualified_name="httpx.get",
        destination_argument=0,
        justification="`httpx` is the common async-capable client and its "
                      "surface mirrors `requests`.",
    ),
    OutboundConstruct(
        rule_id="DEP-007",
        qualified_name="socket.create_connection",
        destination_argument=0,
        justification="below HTTP, and in the catalogue because a deputy "
                      "does not have to speak HTTP. The address is a "
                      "(host, port) tuple.",
    ),
)

CATALOGUE_BY_NAME: Mapping[str, OutboundConstruct] = {
    entry.qualified_name: entry for entry in OUTBOUND_CATALOGUE
}
if len(CATALOGUE_BY_NAME) != len(OUTBOUND_CATALOGUE):
    raise DeputyInspectionError(
        "two catalogue entries declare the same qualified name, so a finding "
        "naming one does not say which rule decided it"
    )

#: Constructs that make a call unresolvable, and therefore the operation
#: `uninspectable`. FR-056 names four; each is here with the name it is
#: recognised by.
UNRESOLVABLE_CONSTRUCTS: Mapping[str, str] = {
    "eval": "evaluated source — the callee is not in the tree",
    "exec": "evaluated source — the callee is not in the tree",
    "compile": "evaluated source — the callee is not in the tree",
    "getattr": "reflection — the attribute name is a value, not a name",
    "__import__": "reflection — the module is named by a value",
    "importlib.import_module": "reflection — the module is named by a value",
}


# ---------------------------------------------------------------------------
# The analysed codebase, and step 1's handler index.


@dataclass(frozen=True)
class Codebase:
    """The parsed source FR-002's analysis stage produced, as symbols.

    A mapping from a qualified symbol name to its function definition, built
    from a directory of Python files. Nothing here reaches the network or a
    running deployment: this is the *analysis* side of OD-06's line, and it is
    reproducible from the codebase alone.
    """

    symbols: Mapping[str, ast.FunctionDef | ast.AsyncFunctionDef]
    #: Every symbol name seen, including duplicates, so step 1 can tell "not
    #: found" from "found more than once". The two are the same outcome and
    #: different reasons, and FR-056 requires the reason to be reportable.
    definition_counts: Mapping[str, int]

    @classmethod
    def from_directory(cls, root: str | Path) -> "Codebase":
        symbols: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {}
        counts: dict[str, int] = {}
        for path in sorted(Path(root).rglob("*.py")):
            try:
                tree = ast.parse(path.read_text(), filename=str(path))
            except SyntaxError:
                # A file this analyser cannot parse contributes no symbols.
                # It is not silently skipped: every operation whose handler
                # was in it resolves to zero symbols and is `uninspectable`,
                # which is the fail-closed direction.
                continue
            for name, node in _definitions(tree):
                counts[name] = counts.get(name, 0) + 1
                symbols.setdefault(name, node)
        return cls(symbols=symbols, definition_counts=counts)

    @classmethod
    def from_sources(cls, sources: Mapping[str, str]) -> "Codebase":
        """A codebase from `{filename: source}`. For fixtures and tests."""
        symbols: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {}
        counts: dict[str, int] = {}
        for filename, source in sorted(sources.items()):
            for name, node in _definitions(ast.parse(source, filename=filename)):
                counts[name] = counts.get(name, 0) + 1
                symbols.setdefault(name, node)
        return cls(symbols=symbols, definition_counts=counts)


def _definitions(
    tree: ast.Module,
) -> Iterable[tuple[str, ast.FunctionDef | ast.AsyncFunctionDef]]:
    """Every function and method, by bare name and by `Class.method`.

    Both forms are indexed so a handler index may name either. A bare name that
    two classes both define resolves to two definitions and is `uninspectable`
    — which is the correct answer: the index did not say which one serves the
    operation.
    """
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield node.name, node
        elif isinstance(node, ast.ClassDef):
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    yield f"{node.name}.{child.name}", child


# ---------------------------------------------------------------------------
# The finding and the report.


@dataclass(frozen=True)
class CallSite:
    """One enumerated outbound call site, and what decided its destination."""

    rule_id: str
    qualified_name: str
    line: int
    #: `build_time`, `target_configuration`, `operation_input`, or `untraceable`.
    destination: str
    detail: str


@dataclass(frozen=True)
class OperationOutcome:
    """FR-056's per-operation outcome, recorded with the operation."""

    operation_id: str
    outcome: str
    #: Which of the three steps decided. Reportable, per FR-056's *"they are
    #: distinguished so that the reason is reportable"*.
    step: int
    reason: str
    call_sites: tuple[CallSite, ...] = ()

    def __post_init__(self) -> None:
        if self.outcome not in OUTCOMES:
            raise DeputyInspectionError(
                f"{self.outcome!r} is not one of FR-056's three outcomes "
                f"({list(OUTCOMES)}). The output space is closed: an outcome "
                "outside it is a fourth disposition nobody decided what to do "
                "with, and the fail-closed rule would not cover it."
            )
        if self.step not in (1, 2, 3):
            raise DeputyInspectionError(
                f"step {self.step} is not one of FR-056's three. An outcome "
                "that does not say which step decided it cannot be acted on: "
                "an operation uninspectable at step 1 needs a handler and one "
                "uninspectable at step 3 needs a traceable destination, and "
                "those are different pieces of work."
            )
        if not self.reason:
            raise DeputyInspectionError(
                f"{self.operation_id}: an outcome states its reason. FR-056 "
                "distinguishes `deputy` from `uninspectable` so the reason is "
                "reportable, and an outcome with no reason makes the "
                "distinction carry nothing."
            )

    @property
    def denied(self) -> bool:
        """FR-056: both `deputy` and `uninspectable` are denied."""
        return self.outcome not in ALLOWED_OUTCOMES

    def document(self) -> dict[str, Any]:
        return {
            "operation_id": self.operation_id,
            "outcome": self.outcome,
            "denied": self.denied,
            "step": self.step,
            "reason": self.reason,
            "catalogue_version": CATALOGUE_VERSION,
            "call_sites": [
                {
                    "rule_id": site.rule_id,
                    "qualified_name": site.qualified_name,
                    "line": site.line,
                    "destination": site.destination,
                    "detail": site.detail,
                }
                for site in self.call_sites
            ],
        }


@dataclass(frozen=True)
class InspectionReport:
    """Every operation's outcome, and the surface that survives it."""

    deployment_id: str
    outcomes: tuple[OperationOutcome, ...]

    @property
    def denied(self) -> tuple[str, ...]:
        return tuple(o.operation_id for o in self.outcomes if o.denied)

    @property
    def available(self) -> tuple[str, ...]:
        """The operations that become available to the agent (FR-051).

        The `clean` set and only the `clean` set. FR-051's *"last inspected
        set"* is *"the set of operations whose recorded outcome is `clean`"* —
        an operation previously found `uninspectable` and unchanged since is
        not silently re-admitted by a later fetch.
        """
        return tuple(o.operation_id for o in self.outcomes if not o.denied)

    def outcome_for(self, operation_id: str) -> OperationOutcome:
        for outcome in self.outcomes:
            if outcome.operation_id == operation_id:
                return outcome
        raise DeputyInspectionError(
            f"{operation_id!r} has no recorded outcome. FR-056 requires an "
            "operation's outcome to be recorded **with the operation**, and "
            "an operation with none is one FR-051 would later compare against "
            "nothing — which is how an uninspected operation becomes "
            "available."
        )

    def document(self) -> dict[str, Any]:
        return {
            "deployment_id": self.deployment_id,
            "catalogue_version": CATALOGUE_VERSION,
            "basis": (
                "a stated rule set, not a proof (FR-056). The catalogue is "
                "enumerated rather than derived and destination influence is "
                "undecidable in the general case, which is why the procedure "
                "answers `uninspectable` rather than answering at all costs. "
                "The property inspected for is unmeasured on any target "
                "(U-44) and FR-020 is a default rather than a finding."
            ),
            "outcomes": [o.document() for o in self.outcomes],
            "denied": list(self.denied),
            "available": list(self.available),
        }


# ---------------------------------------------------------------------------
# The procedure.


def inspect_operation(
    operation_id: str,
    *,
    handler_index: Mapping[str, str],
    codebase: Codebase,
) -> OperationOutcome:
    """FR-056's three steps for one operation.

    `handler_index` maps an operation identifier to the handler symbol the
    analysis stage says serves it. It is an **input** rather than something
    derived here: route extraction belongs to the analysis stage (T119), and
    an index this module built for itself would be this module marking its own
    homework at step 1.
    """
    # -- Step 1 ------------------------------------------------------------
    symbol = handler_index.get(operation_id)
    if not symbol:
        return OperationOutcome(
            operation_id=operation_id, outcome=UNINSPECTABLE, step=1,
            reason=(
                "the analysis stage resolved this operation to no handler "
                "symbol in the analysed codebase. FR-056 step 1 requires "
                "exactly one; zero is an operation served by something "
                "outside the codebase FR-002 analysed — a proxied upstream, a "
                "framework default, or a route this analyser did not "
                "recover — and there is nothing here to inspect."
            ),
        )
    definitions = codebase.definition_counts.get(symbol, 0)
    if definitions == 0:
        return OperationOutcome(
            operation_id=operation_id, outcome=UNINSPECTABLE, step=1,
            reason=(
                f"the handler index names {symbol!r} and the analysed "
                "codebase defines no such symbol. The index and the codebase "
                "disagree, and inspecting the nearest match would report a "
                "verdict about a handler nobody called."
            ),
        )
    if definitions > 1:
        return OperationOutcome(
            operation_id=operation_id, outcome=UNINSPECTABLE, step=1,
            reason=(
                f"the handler index names {symbol!r} and the analysed "
                f"codebase defines it {definitions} times. FR-056 step 1 "
                "requires exactly one. Picking the first would inspect a "
                "symbol that may not be the one serving this operation."
            ),
        )
    handler = codebase.symbols[symbol]

    # -- Step 2 ------------------------------------------------------------
    inputs = _operation_inputs(handler)
    sites: list[CallSite] = []
    for node in ast.walk(handler):
        if not isinstance(node, ast.Call):
            continue
        name = _callee_name(node.func)

        if name is None:
            return OperationOutcome(
                operation_id=operation_id, outcome=UNINSPECTABLE, step=2,
                reason=(
                    f"line {node.lineno}: the callee is not a resolvable "
                    "name — dynamic dispatch through a value this analyser "
                    "cannot follow. FR-056 forbids reading an unresolved call "
                    "as the absence of an outbound request, so the operation "
                    "declines rather than passing."
                ),
            )
        unresolvable = UNRESOLVABLE_CONSTRUCTS.get(name)
        if unresolvable:
            return OperationOutcome(
                operation_id=operation_id, outcome=UNINSPECTABLE, step=2,
                reason=(
                    f"line {node.lineno}: `{name}` is "
                    f"{unresolvable}. Whatever it reaches is outside the "
                    "call graph, so whether this handler issues an outbound "
                    "request is not answerable, and an unresolved call is not "
                    "the absence of one (FR-056 step 2)."
                ),
            )

        entry = CATALOGUE_BY_NAME.get(name)
        if entry is None:
            continue

        # -- Step 3 --------------------------------------------------------
        destination, detail = _destination_influence(node, entry, inputs)
        sites.append(CallSite(
            rule_id=entry.rule_id, qualified_name=name, line=node.lineno,
            destination=destination, detail=detail))

    if not sites:
        return OperationOutcome(
            operation_id=operation_id, outcome=CLEAN, step=2,
            reason=(
                f"{symbol}: every call reachable from the handler was "
                "classified, and none is a construct catalogue "
                f"{CATALOGUE_VERSION} declares to be an outbound network "
                "request. This is the catalogue's answer and not a proof "
                "(FR-056)."
            ),
        )

    influenced = [s for s in sites if s.destination == "operation_input"]
    if influenced:
        first = influenced[0]
        return OperationOutcome(
            operation_id=operation_id, outcome=DEPUTY, step=3,
            reason=(
                f"{symbol} line {first.line}: `{first.qualified_name}` "
                f"({first.rule_id}) issues an outbound request whose "
                f"destination is influenced by an input to the operation — "
                f"{first.detail}. FR-020 requires this operation to be "
                "denied: the agent that cannot reach the internet can "
                "otherwise ask the target to reach it, and the request never "
                "traverses the enforcement point."
            ),
            call_sites=tuple(sites),
        )

    untraceable = [s for s in sites if s.destination == "untraceable"]
    if untraceable:
        first = untraceable[0]
        return OperationOutcome(
            operation_id=operation_id, outcome=UNINSPECTABLE, step=3,
            reason=(
                f"{symbol} line {first.line}: `{first.qualified_name}` "
                f"({first.rule_id}) issues an outbound request whose "
                f"destination this analyser cannot trace to either a "
                f"build-time constant or the target's own configuration — "
                f"{first.detail}. FR-056 step 3 makes that `uninspectable` "
                "rather than clean: 'I could not find where this URL came "
                "from' is not 'it is a constant'."
            ),
            call_sites=tuple(sites),
        )

    return OperationOutcome(
        operation_id=operation_id, outcome=CLEAN, step=3,
        reason=(
            f"{symbol}: {len(sites)} outbound call site(s) enumerated, and "
            "every destination is fixed at build time or read from the "
            "target's own configuration. No input to the operation reaches "
            "any of them."
        ),
        call_sites=tuple(sites),
    )


def inspect_admission(
    decision: AdmissionDecision,
    *,
    handler_index: Mapping[str, str],
    codebase: Codebase,
) -> InspectionReport:
    """The second admission stage, over the list T073's stage supplied.

    Refuses a decision FR-044 rejected. There is no operation list on one, and
    manufacturing one here would make this stage responsible for the input the
    stage above it owns.
    """
    if decision.state not in ADMISSIBLE_STATES:
        raise NotAdmittedForInspection(
            f"{decision.deployment_id} was not admitted (state "
            f"{decision.state}, criterion {decision.rule_id}), so FR-044's "
            "published specification supplied no operation list and there is "
            "nothing for FR-020's inspection to run over. This inspection is "
            "the second stage of one admission sequence and runs after the "
            "first."
        )
    return InspectionReport(
        deployment_id=decision.deployment_id,
        outcomes=tuple(
            inspect_operation(
                str(entry["operation_id"]),
                handler_index=handler_index,
                codebase=codebase,
            )
            for entry in decision.operations
        ),
    )


def gate(report: InspectionReport, operation_id: str) -> None:
    """Refuse an operation the inspection denied.

    `raise` rather than a boolean, on `admission.gate`'s reasoning: a caller
    that ignores a return value calls the operation anyway, and a caller that
    ignores an exception does not exist.
    """
    outcome = report.outcome_for(operation_id)
    if outcome.denied:
        raise DeputyInspectionError(
            f"{report.deployment_id}/{operation_id} is denied.\n"
            f"  outcome    {outcome.outcome}\n"
            f"  decided at FR-056 step {outcome.step}\n"
            f"  reason     {outcome.reason}\n"
            "Both `deputy` and `uninspectable` are denied (FR-056); they are "
            "distinguished so the reason is reportable, not so they are "
            "treated differently."
        )


# ---------------------------------------------------------------------------
# The analyser's two questions.


def _callee_name(func: ast.expr) -> str | None:
    """The dotted name of a callee, or None if it is not a name at all.

    `None` is step 2's `uninspectable` trigger, and it is deliberately
    returned for anything that is not a plain dotted path: a call through a
    subscript, a call on a call's result, a call on an attribute of an
    expression. Each of those is dispatch through a value, and FR-056 requires
    declining rather than guessing.
    """
    parts: list[str] = []
    node: ast.expr = func
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return None


def _operation_inputs(handler: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    """Every name that is an input to the operation.

    The handler's parameters, and every name derived from one by assignment
    inside the body. `self` is excluded: it is the receiver, and treating it as
    an input would make every attribute read on it an influenced destination —
    which is the target's own configuration, explicitly *not* a deputy under
    FR-056 step 3.

    The derivation is transitive and deliberately over-inclusive. A name this
    misses is a destination reported as fixed when an input reaches it, and
    that is the direction that fails open; a name it over-includes is an
    operation denied that need not have been, which fails closed.
    """
    inputs = {
        argument.arg
        for group in (handler.args.posonlyargs, handler.args.args,
                      handler.args.kwonlyargs)
        for argument in group
        if argument.arg not in ("self", "cls")
    }
    for extra in (handler.args.vararg, handler.args.kwarg):
        if extra is not None:
            inputs.add(extra.arg)

    # Fixed point: an assignment whose right-hand side mentions an input makes
    # its targets inputs too. Iterated to a fixed point rather than in one
    # pass, because a chain a = p; b = a; c = b needs as many passes as it is
    # long and a single pass would report `c` as fixed.
    changed = True
    while changed:
        changed = False
        for node in ast.walk(handler):
            targets: list[ast.expr] = []
            if isinstance(node, ast.Assign):
                targets = list(node.targets)
            elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
                targets = [node.target]
            else:
                continue
            if node.value is None or not (_names_in(node.value) & inputs):
                continue
            for target in targets:
                for name in _names_in(target):
                    if name not in inputs:
                        inputs.add(name)
                        changed = True
    return inputs


def _names_in(node: ast.expr) -> set[str]:
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}


def _destination_influence(
    call: ast.Call,
    entry: OutboundConstruct,
    inputs: set[str],
) -> tuple[str, str]:
    """FR-056 step 3, for one enumerated call site.

    Returns one of `build_time`, `target_configuration`, `operation_input` or
    `untraceable`, with the detail that decided it.
    """
    argument = _destination_argument(call, entry)
    if argument is None:
        return ("untraceable", (
            f"the catalogue names argument {entry.destination_argument!r} as "
            "the destination and the call site does not supply it, so what "
            "this call connects to is not visible here. A missing argument is "
            "a default this analyser does not read, not an absent destination."
        ))

    mentioned = _names_in(argument)
    influenced = sorted(mentioned & inputs)
    if influenced:
        return ("operation_input", (
            f"the destination expression mentions {influenced}, which "
            "{} an input to the operation".format(
                "are" if len(influenced) > 1 else "is")
        ))

    if _is_literal(argument):
        return ("build_time", "the destination is a literal in the source")

    if _is_self_configuration(argument):
        return ("target_configuration", (
            "the destination is read from the target's own state or "
            "configuration and no input reaches it"
        ))

    return ("untraceable", (
        "the destination is an expression this analyser cannot trace to a "
        "build-time constant or to the target's own configuration"
    ))


def _destination_argument(
    call: ast.Call, entry: OutboundConstruct
) -> ast.expr | None:
    if isinstance(entry.destination_argument, int):
        if len(call.args) > entry.destination_argument:
            return call.args[entry.destination_argument]
        return None
    for keyword in call.keywords:
        if keyword.arg == entry.destination_argument:
            return keyword.value
    return None


def _is_literal(node: ast.expr) -> bool:
    """A destination fixed at build time.

    A joined string counts only when every part is itself literal, so an
    f-string with a hole is *not* a build-time constant. That is the case a
    laxer reading gets wrong: `f"https://{host}/x"` is a template, and whether
    `host` is an input is step 3's actual question rather than something the
    literal test should absorb.
    """
    if isinstance(node, ast.Constant):
        return True
    if isinstance(node, ast.JoinedStr):
        return all(isinstance(part, ast.Constant) for part in node.values)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _is_literal(node.left) and _is_literal(node.right)
    if isinstance(node, (ast.Tuple, ast.List)):
        return all(_is_literal(element) for element in node.elts)
    return False


def _is_self_configuration(node: ast.expr) -> bool:
    """A destination read only from the target's own state or configuration.

    Recognised as a chain rooted at `self` or at a module-level name, with no
    call anywhere in it. **A call disqualifies it**: `self.resolve(x)` reads
    like configuration and is a function of whatever `x` is, and FR-056 step 3
    is about influence rather than about syntax.

    `research/08` §3.1's warning is inherited here and is worth restating:
    finding a destination *"fixed at build time"* says nothing about whether
    the operation should have been callable by this caller at all. That is a
    different problem and v1 does not solve it.
    """
    if any(isinstance(child, ast.Call) for child in ast.walk(node)):
        return False
    root: ast.expr = node
    while isinstance(root, (ast.Attribute, ast.Subscript)):
        if isinstance(root, ast.Subscript) and not _is_literal(root.slice):
            return False
        root = root.value
    if not isinstance(root, ast.Name):
        return False
    # `self`/`cls` is the target's own state; an ALL-CAPS module-level name is
    # the settings-constant convention. A lowercase module-level name is
    # deliberately not recognised — it is as likely to be a rebound local this
    # analyser lost track of, and step 3's untraceable answer is the safe one.
    return root.id in ("self", "cls") or root.id.isupper()


def outcomes_by_operation(report: InspectionReport) -> dict[str, str]:
    """The recorded outcome per operation, which is what FR-051 compares."""
    return {o.operation_id: o.outcome for o in report.outcomes}


def handler_index_from(pairs: Sequence[tuple[str, str]]) -> dict[str, str]:
    """A handler index from `(operation_id, symbol)` pairs, refusing duplicates.

    An operation named twice in the index is the index being ambiguous about
    which symbol serves it, and resolving it here by last-write-wins would
    make step 1's *exactly one* depend on dictionary insertion order.
    """
    index: dict[str, str] = {}
    for operation_id, symbol in pairs:
        if operation_id in index and index[operation_id] != symbol:
            raise DeputyInspectionError(
                f"the handler index names two symbols for {operation_id!r} "
                f"({index[operation_id]!r} and {symbol!r}). Step 1 requires "
                "exactly one, and choosing between them here would hide an "
                "ambiguity the analysis stage should report."
            )
        index[operation_id] = symbol
    return index
