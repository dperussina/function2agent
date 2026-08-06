"""SPIKE - E18. The three conditions, the persistence boundary, the result record.

Do not import from product code, and nothing here is imported by product code.

## The three conditions

[Finding 030](../../findings/030-provider-state-chain-derived-not-measured.md) §6
names them and this module is their only definition, so that four arms cannot
drift into applying four slightly different treatments:

| condition | what the next request carries |
|---|---|
| **A — full** | every assistant turn's opaque state, at the path it came off |
| **B — drop-one** | every state except the one at `DROP_ORDINAL`, withheld from the moment it is emitted and for the rest of the conversation |
| **C — drop-all** | no assistant turn's opaque state |

**A is a control, not a sanity check.** Without it a 400 in B or C is
attributable to nothing: a malformed request, a stale credential, a model that
rejects the request shape, and a tool schema the provider will not accept each
produce the same reading as the treatment working. That is Rule 8 of the
[`experiment-design`](../../../../.cursor/skills/experiment-design/SKILL.md)
skill — *"an experiment whose positive result is a failure signal needs a
negative control"* — and it is a rule of that skill and **not** of
`tools/README.md`, which contains no `Rule N` text at any site.

## The persistence boundary, which finding 016's arms did not have

Finding 030 §3 is the reason this module exists rather than the arms simply
blanking a field. Finding 016's arms appended each response object straight back
into a local list, so the opaque field was never separated from the message it
arrived on and **no code path that lost one had an opportunity to exist**.

Here every assistant turn crosses a boundary that models what the runtime does:
it is serialised to JSON with its declared opaque leaves **deleted**, and every
request is rebuilt from the persisted bodies with the states written back in.
That is `_persisted` and `_rebuilt` from
[`tests/conformance/test_provider_state_roundtrip.py`](../../../../tests/conformance/test_provider_state_roundtrip.py),
which exist because the fixture was blind to exactly this twice. It also means
condition B and condition C are produced by *not writing a value back*, which is
the shape the defect has in a journal-backed runtime, rather than by mutating a
field to an empty string.

**xAI is the documented exception.** `xai-sdk` carries the conversation as a
protobuf and offers no way to rebuild an assistant message with `tool_calls`
from a persisted body, so that arm applies the treatment by clearing
`encrypted_content` on the proto message — which is finding 016's negative
control's own mechanism, and which is byte-identical on the wire to omission,
because a proto3 scalar set to its default is not serialised. Recorded in the
arm and in the README rather than smoothed over.

## What a withheld state actually looks like in a request, which has three shapes and not two

Finding 030 §6 asks for *drop-one* and *drop-all*. Running it exposes a
distinction the design does not name: a conversation that has emitted two states
and withheld the second is missing its **newest** state, not carrying a hole —
the hole only appears once a third state lands after the gap. Those are
different requests and this harness classifies them separately rather than
reporting both as "drop-one", because if a provider rejects at the first gap the
reading is about a trailing gap and saying "hole" would overclaim.
"""
from __future__ import annotations

import base64
import copy
import dataclasses
import hashlib
import json
import time
from typing import Any, Sequence

FULL = "A"
DROP_ONE = "B"
DROP_ALL = "C"
CONDITIONS = (FULL, DROP_ONE, DROP_ALL)

#: Which state-carrying assistant turn condition B withholds, counting only the
#: turns that actually emitted state, 0-based. `1` and not `0`: withholding the
#: first produces a chain whose gap is at the start, and the condition finding
#: 030 §2 says is unmeasured is a chain with a hole *in the middle*.
DROP_ORDINAL = 1

#: Request shapes, in the order of severity a validator would plausibly see.
SHAPE_FULL = "full"
SHAPE_TRAILING_GAP = "trailing-gap"
SHAPE_INTERIOR_HOLE = "interior-hole"
SHAPE_ALL_ABSENT = "all-absent"
SHAPE_NO_STATE_YET = "no-state-yet"

#: Hard per-arm stops. Rows B and C error by design, so the failure mode that
#: spends a budget without producing a reading is a loop that keeps going — see
#: finding 030 §6's note about a retry loop on a 400. There is **no retry
#: anywhere in this harness**: the first provider error ends the arm.
MAX_TURNS = 8
MAX_INPUT_TOKENS = 20_000

#: Run-level ceiling, enforced across the twelve arms through a file the run
#: shares. Finding 030 §6 asks for a self-imposed ceiling declared before any
#: arm runs, in finding 016's shape, and a per-arm cap is not one: twelve arms
#: each stopping at their own cap is twelve times the number anybody declared.
#: An arm refuses to start once the ledger is over, so the worst case is the
#: cap plus one arm.
LEDGER_MAX_INPUT_TOKENS = 150_000
LEDGER_MAX_OUTPUT_TOKENS = 15_000
LEDGER_ENV = "F2A_E18_LEDGER"


def ledger_path() -> Any:
    """Where the run-level token ledger lives, or None if no run declared one."""
    import os
    from pathlib import Path

    raw = os.environ.get(LEDGER_ENV)
    return Path(raw) if raw else None


def ledger_read() -> dict[str, Any]:
    path = ledger_path()
    if path is None or not path.is_file():
        return {"input_tokens": 0, "output_tokens": 0,
                "provider_reported_cost_usd": 0.0, "arms": 0}
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {"input_tokens": 0, "output_tokens": 0,
                "provider_reported_cost_usd": 0.0, "arms": 0}


def ledger_exceeded() -> str | None:
    """The reason this arm must not start, or None."""
    if ledger_path() is None:
        return None
    spent = ledger_read()
    if spent["input_tokens"] >= LEDGER_MAX_INPUT_TOKENS:
        return (f"the run has spent {spent['input_tokens']} input tokens "
                f"against a declared ceiling of {LEDGER_MAX_INPUT_TOKENS}")
    if spent["output_tokens"] >= LEDGER_MAX_OUTPUT_TOKENS:
        return (f"the run has spent {spent['output_tokens']} output tokens "
                f"against a declared ceiling of {LEDGER_MAX_OUTPUT_TOKENS}")
    return None


def ledger_add(result: "ArmResult") -> None:
    path = ledger_path()
    if path is None:
        return
    spent = ledger_read()
    spent["input_tokens"] += result.input_tokens
    spent["output_tokens"] += result.output_tokens
    spent["provider_reported_cost_usd"] += (
        result.cost_usd_reported_by_provider or 0.0)
    spent["arms"] += 1
    path.write_text(json.dumps(spent, indent=2) + "\n")


def digest(value: Any) -> str | None:
    """A stable hash of an opaque field, whatever shape it arrives in."""
    if value is None:
        return None
    if isinstance(value, bytes):
        payload = value
    elif isinstance(value, str):
        payload = value.encode("utf-8")
    else:
        payload = json.dumps(value, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


def carries(condition: str, ordinal: int) -> bool:
    """Does the request carry the state emitted by the `ordinal`-th state turn?"""
    if condition == FULL:
        return True
    if condition == DROP_ALL:
        return False
    if condition == DROP_ONE:
        return ordinal != DROP_ORDINAL
    raise ValueError(f"unknown condition {condition!r}")


def shape_of(present: Sequence[bool]) -> str:
    """Classify the state pattern a request carries, in emission order.

    `present[i]` is whether the i-th state-carrying assistant turn's state is in
    this request. See the module docstring for why `trailing-gap` and
    `interior-hole` are not collapsed.
    """
    if not present:
        return SHAPE_NO_STATE_YET
    if all(present):
        return SHAPE_FULL
    if not any(present):
        return SHAPE_ALL_ABSENT
    last_present = max(i for i, ok in enumerate(present) if ok)
    if any(not ok for i, ok in enumerate(present) if i < last_present):
        return SHAPE_INTERIOR_HOLE
    return SHAPE_TRAILING_GAP


# ---------------------------------------------------------------------------
# The persistence boundary.


@dataclasses.dataclass
class PersistedTurn:
    """One assistant turn as a journal would hold it: body without its states.

    `body` is plain JSON with every declared opaque leaf **deleted**, so a
    request rebuilt from it and never re-injected carries no state at all. That
    is condition C by construction rather than by mutation.

    `slots` is `[(path, carrier, is_text)]` — the values that were removed, in
    the order the provider emitted them. `carrier` is base64 for a binary
    payload so that the whole record survives `json.dumps`, and only Google's
    `thought_signature` is binary.
    """

    body: Any
    slots: list[tuple[list[Any], str, bool]]

    @property
    def carried_state(self) -> bool:
        return bool(self.slots)


def _walk_to(node: Any, path: Sequence[Any]) -> Any:
    for step in path:
        try:
            node = node[step]
        except (KeyError, IndexError, TypeError):
            return None
    return node


def persist(body: Any, paths: Sequence[Sequence[Any]]) -> PersistedTurn:
    """Strip the declared opaque leaves out of a turn and round-trip through JSON.

    The JSON round-trip is not decoration. `_persisted`'s docstring in the
    conformance fixture records that appending the parsed turn *by reference*
    left the opaque field sitting in the dict the driver had just read it out
    of, so re-injection was writing a value that was already there and the
    fixture could not tell a runtime that dropped states from one that did not.
    """
    clone = copy.deepcopy(body)
    slots: list[tuple[list[Any], str, bool]] = []
    for path in paths:
        parent = _walk_to(clone, path[:-1])
        if parent is None:
            continue
        leaf = path[-1]
        try:
            value = parent[leaf]
        except (KeyError, IndexError, TypeError):
            continue
        if value is None or value == "" or value == b"":
            continue
        if isinstance(value, str):
            slots.append(([*path], value, True))
        else:
            slots.append(([*path], base64.b64encode(bytes(value)).decode(), False))
        if isinstance(parent, dict):
            del parent[leaf]
        else:
            parent[leaf] = None
    # The round-trip. A body that will not serialise is a body the journal
    # could not hold, and finding this at the boundary is the point of it.
    return PersistedTurn(body=json.loads(json.dumps(clone)), slots=slots)


def rebuild(turn: PersistedTurn, *, carry: bool) -> tuple[Any, list[str]]:
    """The persisted body as the next request needs it, states written back or not.

    Returns the body and the digests of the values actually written, so an arm
    can assert that condition A really did re-inject and conditions B and C
    really did not. **The digest is taken over the stored carrier**, which is
    the same basis `persist` records, so the two lists are comparable. It is an
    identity handle for a value, not a byte-fidelity assertion — finding 016
    measured byte fidelity and this harness does not re-measure it.
    """
    body = copy.deepcopy(turn.body)
    written: list[str] = []
    if not carry:
        return body, written
    for path, carrier, is_text in turn.slots:
        value: Any = carrier if is_text else base64.b64decode(carrier)
        written.append(digest(carrier))
        parent = _walk_to(body, path[:-1])
        if parent is None:
            raise RuntimeError(
                f"no path left to write {path!r} back to. The assistant turn was "
                "rebuilt rather than carried, which is the adapter defect "
                "FR-037 exists for — and it produces a request the provider "
                "accepts."
            )
        parent[path[-1]] = value
    return body, written


# ---------------------------------------------------------------------------
# The result record.


@dataclasses.dataclass
class ArmResult:
    """One cell of the twelve-cell table."""

    provider: str
    condition: str
    sdk: str
    sdk_version: str
    model: str
    credential_var: str = ""
    credential_fp: str = ""
    opaque_field: str = ""

    #: Did the arm reach a verdict at all? False only for a harness fault.
    ok: bool = False

    # ---- the reading the experiment is for -------------------------------
    #: The one bit rows B and C exist to produce. `None` until the arm ends.
    provider_errored: bool | None = None
    error_status: int | None = None
    error_kind: str | None = None  # "environmental" | "capability" | None
    error: str | None = None
    #: The state pattern in the last request that was actually sent.
    last_request_shape: str = SHAPE_NO_STATE_YET
    #: Every shape sent, in order, so a reader can see what was exercised.
    request_shapes: list[str] = dataclasses.field(default_factory=list)

    # ---- whether the treatment was applied at all ------------------------
    #: State-carrying assistant turns observed. 0 makes B and C vacuous.
    state_turns: int = 0
    #: Which assistant turns those were, 0-based. A provider that emits state
    #: on **one** turn cannot be given a chain with a hole in it at all, and
    #: that is a measured property of the provider rather than a harness fault.
    state_turn_indices: list[int] = dataclasses.field(default_factory=list)
    #: Was a state actually withheld from a request that was actually sent?
    treatment_applied: bool = False
    #: Which ordinal B withheld. Null for A and C.
    withheld_ordinal: int | None = None
    #: An arm whose treatment could not be applied is UNTESTABLE, not a pass.
    verdict: str = "unrun"

    # ---- behaviour, for the arms that survive ----------------------------
    turns: int = 0
    tool_calls: list[str] = dataclasses.field(default_factory=list)
    hops_linked: int = 0
    chained: bool = False
    answer_correct: bool = False
    final_text: str = ""

    digests_emitted: list[str] = dataclasses.field(default_factory=list)
    digests_reinjected: list[str] = dataclasses.field(default_factory=list)

    input_tokens: int = 0
    output_tokens: int = 0
    #: Only where the **provider** reports one. `None` means not reported and
    #: never zero: converting tokens to dollars needs a per-provider price
    #: table, which `U-48` records as an unowned capability, and finding 016
    #: refused to invent one. So does this.
    cost_usd_reported_by_provider: float | None = None

    elapsed_s: float = 0.0
    notes: list[str] = dataclasses.field(default_factory=list)

    def note(self, message: str) -> None:
        self.notes.append(message)

    def score(self) -> None:
        """Set `verdict` from what was observed. Never called before the arm ends."""
        if self.error_kind == "environmental":
            self.verdict = "ENVIRONMENTAL"
        elif self.condition == FULL:
            if self.provider_errored:
                self.verdict = "CONTROL-FAILED"
            elif self.state_turns == 0:
                self.verdict = "UNTESTABLE-NO-STATE"
            else:
                self.verdict = "OK"
        elif not self.treatment_applied:
            if self.state_turns == 0:
                self.verdict = "UNTESTABLE-NO-STATE"
            elif (self.condition == DROP_ONE
                  and self.provider_errored is False
                  and self.state_turns <= DROP_ORDINAL):
                # There was no second state to withhold, so a chain with a hole
                # in it does not exist on this provider for this chain. Named
                # separately from a mid-run abort, because the two are
                # different facts about different things.
                self.verdict = "UNTESTABLE-ONE-STATE-ONLY"
            else:
                self.verdict = "UNTESTABLE-NOT-APPLIED"
        elif self.provider_errored:
            self.verdict = "ERRORED"
        else:
            self.verdict = "TOLERATED"

    def as_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


class Timer:
    def __enter__(self):
        self.t0 = time.time()
        return self

    def __exit__(self, *exc):
        self.elapsed = time.time() - self.t0
        return False


def emit(result: ArmResult) -> int:
    """Print one JSON object. A provider error is a *result* and still exits 0."""
    if result.verdict == "unrun":  # pragma: no cover - `loop.run` scores first
        result.score()
    print(json.dumps(result.as_dict(), indent=2, default=str))
    return 2 if result.error_kind == "environmental" else 0


def condition_arg(argv: Sequence[str]) -> str:
    """`--condition A|B|C`, required. No default: the treatment is the experiment."""
    if "--condition" in argv:
        index = list(argv).index("--condition")
        if index + 1 < len(argv):
            value = argv[index + 1].upper()
            if value in CONDITIONS:
                return value
    raise SystemExit(
        "--condition A|B|C is required.\n"
        "  A  full chain      — every assistant turn's opaque state present\n"
        "  B  one state held  — the second state-carrying turn's withheld\n"
        "  C  all states held — no assistant turn carries state"
    )


def model_arg(argv: Sequence[str], default: str) -> str:
    if "--model" in argv:
        index = list(argv).index("--model")
        if index + 1 < len(argv):
            return argv[index + 1]
    return default
