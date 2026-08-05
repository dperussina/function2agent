"""T061 — per-provider opaque-state round-trip over a long chained tool sequence.

**The one thing this fixture must not be, and the reason it is not.**

An output-checking test is blind to opaque-state loss. That is not a worry;
[finding 016](../../specs/001-discovery-validation/findings/016-provider-sdk-roundtrip.md)
measured it. Its negative control stripped the opaque field entirely and the
chain **still ran and still answered correctly** — so a conformance fixture that
drives a chain and asserts the answer would have passed ADK's LiteLLM adapter
while that adapter was referencing xAI's `encrypted_content` zero times. Every
assertion below that matters is on the **bytes of the opaque field**, and
`test_the_answer_alone_cannot_detect_the_loss` is the arm that shows the
alternative is insensitive rather than merely weaker.

**And it must be a conditional, never a presence check.** Finding 016 result 8
measured `claude-sonnet-5` under adaptive thinking emitting opaque state on
**2 of 6** runs in the committed batch. `assert state_present` is flaky on a
real provider and would be deleted the first week it went red. The assertion
that holds is *whenever the field is present it survives byte-identical*, which
held on 100% of the runs where it was present.

**The trap in that pair, guarded here.** A conditional is vacuously true when
the field is never present, so a run that tested nothing looks exactly like a
run that tested everything. `roundtrip_report` therefore counts and returns both
populations, `check_roundtrip` **refuses** a report with zero present turns, and
`anthropic-adaptive-silent.json` exists solely so that refusal is exercised
rather than asserted about. A green run here reports how many turns carried the
field; a run where none did is a failure with a message saying so.

## What this establishes, and what it does not

**Does**: the four drivers extract a provider's opaque field from a response of
that provider's shape, carry it as bytes, and put it back into the next request
byte-identically, over a six-turn chain, including a payload containing a NUL
and a bare UTF-8 continuation byte.

**Does not**: that any provider emitted, accepted or validated one of these.
The cassettes' payloads are synthetic — see
`tests/conformance/cassettes/README.md`, and `Cassette.require_recorded()` is
the guard that stops this fixture being cited for the stronger claim. Finding
016 measured the provider half live on all four vendors; T164's four-provider
battery is where the shipped configuration re-establishes it.

**Does not**: exercise any vendor SDK. `ProviderDriver.call` is the transport
half and nothing offline reaches it.

**Does**, as of 2026-08-05: that **every** assistant turn's opaque field reaches
the next request, not only the previous turn's. It did not before. This fixture
recorded the limit — *"exactly one turn's opaque field is carried forward and
every earlier one is dropped"* — and left open whether any provider minded. All
four do, and three reject the request outright; the evidence is in
`src/runtime/context.py::states_for`. The premise the limit rested on was also
wrong: Anthropic does not want only the immediately preceding assistant turn,
because **a tool-use loop is one assistant turn** and within one *"you must pass
the thinking blocks from the assistant message back to the API, complete and
unmodified."* Server-side stripping is about turns before the current one, and
on Opus 4.5 / Sonnet 4.6 and later there is none.

**Two things had to change here for the fixture to see any of that**, and both
are the same failure in different clothes. `_persisted` models the runtime
stripping the field on the way to storage; `_rebuilt` models it building each
request from stored bodies rather than from a conversation it kept in memory.
Without the second, `reinject`'s in-place write on turn N survived into turn
N+1's request and the fixture reported full accumulation from a runtime that
carried one state per turn. And the states now come from `ContextAssembler`
rather than from a local variable, so the policy under test is the runtime's.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import pytest

from src.runtime.context import ByteTokenizer, ContextAssembler
from src.runtime.dispatch import ToolResult
from src.runtime.loop import TurnRecord
from src.runtime.providers import ROLE_TOOL, ROLE_USER, WireTurn, driver_for
from src.runtime.providers.schema import ToolSchema, results_to_wire
from src.runtime.turn import state_digest
from tests.conformance.cassettes import harness

CASSETTES = harness.HERE

#: The four providers, one cassette each. Named rather than globbed so that a
#: cassette going missing is a collection error here instead of a quieter
#: parametrization that shrinks by one.
PROVIDER_CASSETTES = (
    "anthropic.json",
    "openai.json",
    "google.json",
    "xai.json",
)

SPARSE = "anthropic-adaptive-sparse.json"
SILENT = "anthropic-adaptive-silent.json"

SYSTEM = (
    "You answer questions about orders using the supplied tools. Each tool's "
    "input must come from the previous tool's output."
)
PROMPT = "What is the order total for customer Dana Whitfield? Use the tools."


# ---------------------------------------------------------------------------
# The chain. Five dependent hops; every hop refuses an id it did not issue.


ISSUED = {
    "lookup_customer": ("customer_name", "Dana Whitfield",
                        {"customer_id": "CUS-4417"}),
    "list_orders": ("customer_id", "CUS-4417", {"order_id": "ORD-7731"}),
    "get_order_lines": ("order_id", "ORD-7731", {"line_id": "LN-22"}),
    "get_line_price": ("line_id", "LN-22", {"subtotal_usd": 139.99}),
    "apply_tax": ("subtotal_usd", 139.99, {"total_usd": 149.99}),
}

TOOLS = tuple(
    ToolSchema(name=name,
               description=f"Step of the order lookup keyed by {key}.",
               parameters={"type": "object",
                           "properties": {key: {"type": "string"}},
                           "required": [key]})
    for name, (key, _, _) in ISSUED.items()
)


class ToolLedger:
    """Records what each hop was called with, so chaining is asserted.

    Finding 016's own rule: chaining is decided from the dispatch ledger — hop
    N ran with the value hop N-1 returned — and never inferred from the final
    answer.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, Mapping[str, Any]]] = []

    def run(self, name: str, arguments: Mapping[str, Any]) -> str:
        self.calls.append((name, dict(arguments)))
        key, expected, result = ISSUED[name]
        if arguments.get(key) != expected:
            return json.dumps({
                "error": f"{name} was given {arguments.get(key)!r} for {key}; "
                         "that value was not issued by the previous hop"})
        return json.dumps(result)

    def chained(self) -> bool:
        """Every hop after the first ran on the previous hop's return value."""
        names = [name for name, _ in self.calls]
        if names != list(ISSUED):
            return False
        for (name, arguments) in self.calls:
            key, expected, _ = ISSUED[name]
            if arguments.get(key) != expected:
                return False
        return True


# ---------------------------------------------------------------------------
# Driving one cassette.


@dataclass
class TurnObservation:
    turn: int
    #: What the cassette declares the provider emitted, read off the cassette's
    #: own `opaque` list rather than off anything the driver produced.
    declared: tuple[Any, ...]
    #: Everything the request for this turn carried, found by walking the
    #: cassette's declared selector — a second implementation, not the driver's
    #: injector. **Every** prior turn's values, in conversation order, not only
    #: the previous turn's.
    carried: tuple[Any, ...]
    #: The tail of `carried` attributable to the immediately previous turn.
    reinjected: tuple[Any, ...]
    #: The driver's digest over its packed carrier, against the cassette's pin.
    digest: str | None
    pinned: str | None

    @property
    def present(self) -> bool:
        return bool(self.declared)


@dataclass
class Report:
    provider: str
    model: str
    observations: list[TurnObservation]
    ledger: ToolLedger
    final_text: str
    requests: list[Mapping[str, Any]]

    @property
    def present_turns(self) -> list[int]:
        return [o.turn for o in self.observations if o.present]

    @property
    def absent_turns(self) -> list[int]:
        return [o.turn for o in self.observations if not o.present]


def roundtrip_report(cassette: harness.Cassette) -> Report:
    """Drive the whole chain against one cassette and record what crossed.

    The loop here is deliberately the *shape* of `src/runtime/loop.py`'s turn
    loop and not that loop itself: this fixture is about the provider seam, and
    running it through the session store, the journal and the ledger would make
    a red arm ambiguous between four mechanisms. T056 is the fixture that drives
    the real loop across a crash; this one drives the driver.
    """
    driver = driver_for(cassette.provider)
    player = harness.Player(cassette)
    ledger = ToolLedger()

    persisted: list[WireTurn] = [WireTurn(role=ROLE_USER,
                                          payload=_user_turn(cassette.provider))]
    observations: list[TurnObservation] = []
    final_text = ""

    # **The state is routed through the assembler, not handed along in a local.**
    # `states_for` is where the per-turn selection lives, and a fixture that
    # short-circuited it by keeping `parsed.provider_state` in a variable would
    # be asserting over its own policy rather than over the runtime's. The
    # budget is deliberately enormous and `dropped_turns` asserted at zero, so
    # that this arm cannot quietly become a truncation test.
    assembler = ContextAssembler(budget_tokens=10_000_000,
                                 tokenizer=ByteTokenizer())
    records: list[TurnRecord] = []

    for index, interaction in enumerate(cassette.interactions):
        context = assembler.assemble(prompt=PROMPT, turns=records,
                                     provider=cassette.provider)
        assert context.dropped_turns == 0, (
            f"{cassette.provider} turn {index}: the assembler dropped "
            f"{context.dropped_turns} turns, so the states it returned cover "
            "fewer turns than the conversation holds and this arm is measuring "
            "truncation rather than the round trip")
        turns = _rebuilt(persisted)
        request = driver.build_request(
            model=cassette.model, system=SYSTEM, turns=turns, tools=TOOLS,
            provider_states=context.provider_states)

        # What this request carries, found by the cassette's route. Read
        # *before* the response is played, because the state under test is the
        # one the previous turns produced.
        carried = tuple(harness.opaque_in_request(cassette, request))
        previous = observations[-1].declared if observations else ()
        observations.append(TurnObservation(
            turn=index,
            declared=tuple(v.native() for v in interaction.opaque),
            carried=carried,
            # The tail is what the immediately previous turn contributed.
            reinjected=carried[-len(previous):] if previous else (),
            digest=None, pinned=interaction.expected_state_digest,
        ))

        payload = player.respond(index, request,
                                 conversation_length=len(turns))
        parsed = driver.parse_response(payload)
        observations[-1].digest = state_digest(parsed.provider_state)

        assert parsed.assistant is not None
        persisted.append(_persisted(parsed.assistant, interaction))
        records.append(TurnRecord(
            turn_index=index, provider=cassette.provider,
            provider_state=parsed.provider_state,
            tool_calls=parsed.tool_calls, tool_results=(),
            text=parsed.text, at=float(index)))

        if not parsed.tool_calls:
            final_text = parsed.text
            break

        results = tuple(
            ToolResult(call=call, outcome="ok",
                       body=ledger.run(call.name, call.arguments),
                       started_at=0.0, finished_at=0.0)
            for call in parsed.tool_calls
        )
        for entry in results_to_wire(cassette.provider, results):
            persisted.append(WireTurn(role=_result_role(cassette.provider),
                                      payload=entry))

    player.assert_exhausted()
    return Report(provider=cassette.provider, model=cassette.model,
                  observations=observations, ledger=ledger,
                  final_text=final_text, requests=player.requests)


def _persisted(assistant: WireTurn, interaction: harness.Interaction) -> WireTurn:
    """The assistant turn as the next turn actually receives it.

    **This function is the reason this fixture measures anything**, and it was
    added after a removal proof reported `UNPROVEN`: with `reinject`'s write
    disabled, the round-trip assertions still passed. They passed because the
    fixture had been appending the parsed assistant turn *by reference*, so the
    opaque field was still sitting in the dict the driver had just read it out
    of. Re-injection was writing a value that was already there. The fixture was
    an eighth instrument silent on exactly what it claimed.

    That is not what the runtime does. `src/runtime/context.py:render_turn` says
    it in as many words — *"The opaque state is not rendered"* — and the turn
    record keeps it in its own nullable bytes column (T-02). The conversation
    that reaches the next `build_request`, and every conversation reconstructed
    after a resume, is the body **without** the field. `reinject` is the only
    route back.

    So this models that boundary: delete the declared opaque leaves, then round
    trip through JSON. JSON rather than `deepcopy` because *persistable* is the
    property, and Google's `thought_signature` is raw bytes that `json.dumps`
    refuses — which is itself the reason the state travels in a bytes column
    rather than inside the message.
    """
    payload = copy.deepcopy(assistant.payload)
    for value in interaction.opaque:
        assert _delete_path(payload, value.path), (
            f"turn {interaction.turn}: the cassette declares opaque state at "
            f"{list(value.path)} and the driver's assistant turn has nothing "
            "there. Either the driver's path and the cassette's disagree, or "
            "the driver rebuilt the turn — and this fixture would then be "
            "asserting re-injection against a field it never removed."
        )
    return WireTurn(role=assistant.role, payload=json.loads(json.dumps(payload)))


def _rebuilt(persisted: "list[WireTurn]") -> list[WireTurn]:
    """The conversation as each request builds it: fresh from persisted bodies.

    **The second half of the boundary `_persisted` models, and it was missing.**
    `_persisted` strips the opaque field once, when the turn is first appended.
    If the same `WireTurn` objects are then reused for every subsequent request,
    `reinject`'s in-place write on turn N survives into turn N+1 — so a runtime
    that carries exactly one state per request still *looks* like one that
    carries all of them, because the earlier ones were left behind in the dicts.
    That is the by-reference blindness `_persisted` was written to remove,
    reappearing one level up.

    A journal-backed runtime does not hold a mutable conversation. It holds turn
    bodies and rebuilds the request from them — that is what `resume.py` must do
    after a crash, and a conversation that only survives in process memory is
    one a resumed session does not have. Rebuilding here per request makes the
    fixture measure the policy rather than the aliasing.
    """
    return [WireTurn(role=turn.role,
                     payload=json.loads(json.dumps(turn.payload)))
            for turn in persisted]


def _delete_path(payload: Any, path: Any) -> bool:
    node = payload
    for step in list(path)[:-1]:
        try:
            node = node[step]
        except (KeyError, IndexError, TypeError):
            return False
    try:
        del node[list(path)[-1]]
    except (KeyError, IndexError, TypeError):
        return False
    return True


def _user_turn(provider: str) -> Any:
    if provider == "openai":
        # A list, because Responses splices entries into a flat input array.
        return [{"role": "user", "content": PROMPT}]
    if provider == "google":
        return {"role": "user", "parts": [{"text": PROMPT}]}
    return {"role": "user", "content": PROMPT}


def _result_role(provider: str) -> str:
    # Anthropic and Google put tool results in a `user` turn; xAI uses a `tool`
    # role; OpenAI's `function_call_output` is roleless and rides in the flat
    # input array. What matters to `reinject` is only that none of these is
    # `assistant`, or the state would be written onto a results entry.
    return ROLE_TOOL if provider == "xai" else ROLE_USER


def check_roundtrip(report: Report) -> None:
    """FR-037's assertion, as a conditional, guarded against vacuity.

    Three claims and the third is the one that makes the first two mean
    anything:

    1. **Whenever the opaque field is present it survives byte-identical.**
       Asserted on the values, not on a digest of them, and separately against
       the digest the cassette pins.
    2. **When it is absent, nothing is fabricated.** A driver that invented a
       state for a turn the provider gave none for would be re-injecting
       something the provider never signed.
    3. **At least one turn carried it.** Without this the first claim is
       vacuously true and the fixture reports success over having tested
       nothing. This repository has found seven instruments silent on exactly
       what they claim; the message here says which of the two happened.
    """
    accumulated: list[Any] = []
    for observation in report.observations:
        assert observation.carried == tuple(accumulated), (
            f"{report.provider} turn {observation.turn}: the request carried "
            f"{_shape(observation.carried)} where turns 0..{observation.turn - 1} "
            f"together produced {_shape(tuple(accumulated))}. Every one of "
            "them belongs in this request. All four vendors say so and three "
            "of them say it as a hard error: OpenAI *\"preserve and replay "
            "every returned reasoning item\"*, Google validates every step of "
            "the current turn and 400s on a missing one, xAI *\"always pass "
            "the full output array back verbatim\"*, and Anthropic requires "
            "the thinking block on every assistant message inside a tool-use "
            "turn because the whole loop is one turn."
        )
        accumulated.extend(observation.declared)

    for observation in report.observations[1:]:
        previous = report.observations[observation.turn - 1]
        if previous.present:
            assert observation.reinjected == previous.declared, (
                f"{report.provider} turn {observation.turn}: the request "
                f"carried {_shape(observation.reinjected)} where turn "
                f"{previous.turn}'s response held {_shape(previous.declared)}. "
                "FR-037 requires the opaque state re-injected verbatim, and "
                "byte identity is the only assertion that can tell re-injected "
                "from regenerated — finding 016 measured the chain answering "
                "correctly with the field stripped entirely."
            )
        else:
            assert observation.reinjected == (), (
                f"{report.provider} turn {observation.turn}: turn "
                f"{previous.turn} carried no opaque state and the request "
                f"carries {_shape(observation.reinjected)} anyway. A state "
                "invented for a turn the provider gave none for is one the "
                "provider never signed."
            )

    for observation in report.observations:
        if observation.present:
            assert observation.digest == observation.pinned, (
                f"{report.provider} turn {observation.turn}: the driver packed "
                f"a carrier digesting to {observation.digest} against the "
                f"cassette's pin {observation.pinned}. The pin is frozen data; "
                "if the carrier format changed on purpose, re-pin with "
                "build_cassettes.py in the same commit."
            )
        else:
            assert observation.digest is None, (
                f"{report.provider} turn {observation.turn} emitted no opaque "
                f"state and the driver produced {observation.digest}. `None` "
                "and empty bytes are different facts and the journal's column "
                "is nullable to keep them apart."
            )

    assert report.present_turns, (
        f"{report.provider}/{report.model}: the opaque field was absent on "
        f"all {len(report.observations)} turns, so every byte-identity "
        "assertion above was vacuously true and this run tested nothing. A "
        "conditional is only evidence over the population it applied to. If "
        "this is genuinely a configuration that emits none, it is not a "
        "round-trip fixture — it is the arm "
        "`test_the_vacuity_guard_refuses_a_cassette_that_never_carries_state` "
        "exists to hold."
    )


def _shape(values: tuple[Any, ...]) -> str:
    """Sizes and types. **Never the payload** — FR-037 forbids the readable form."""
    if not values:
        return "nothing"
    return "[" + ", ".join(
        f"<{len(v)} {'chars' if isinstance(v, str) else 'bytes'}>"
        for v in values) + "]"


# ---------------------------------------------------------------------------
# Arm 1 — the four providers.


@pytest.mark.parametrize("filename", PROVIDER_CASSETTES)
def test_the_opaque_field_survives_the_chain_byte_identically(filename):
    cassette = harness.load(CASSETTES / filename)
    report = roundtrip_report(cassette)

    assert report.ledger.chained(), (
        f"{cassette.provider}: the chain did not run as recorded. Calls were "
        f"{[name for name, _ in report.ledger.calls]}; each hop's argument "
        "must be the previous hop's return value, and no value in it is "
        "derivable from the prompt."
    )
    assert "149.99" in report.final_text

    check_roundtrip(report)

    # The vacuity guard's own reading, printed into the assertion rather than
    # left implicit: this cassette is the all-present one.
    assert len(report.present_turns) == len(report.observations), (
        f"{filename} is the full-presence cassette and "
        f"{len(report.absent_turns)} turns carried nothing")


def test_every_provider_has_a_cassette_and_none_is_silently_missing():
    """The parametrization's own floor.

    A `glob` here would shrink by one when a file went missing and the suite
    would still be green over three providers. **SC-010** is a four-provider
    claim, so the count is asserted rather than derived from the directory.
    """
    from src.runtime.providers import PROVIDERS

    covered = {harness.load(CASSETTES / name).provider
               for name in PROVIDER_CASSETTES}
    assert covered == set(PROVIDERS), (
        f"cassettes cover {sorted(covered)} against the declared provider set "
        f"{sorted(PROVIDERS)}")


# ---------------------------------------------------------------------------
# Arm 2 — the conditional is genuinely conditional.


def test_a_model_that_emits_state_on_some_turns_passes_and_reports_which():
    """Finding 016 result 8, as a fixture rather than as a caveat.

    `claude-sonnet-5` under adaptive thinking emitted opaque state on 2 of 6
    runs in the committed batch. An unconditional presence assertion is flaky
    against that and would be deleted the first time it went red. This asserts
    the shape that is not flaky: the round-trip holds on the turns that carried
    it, and the turns that did not are counted rather than ignored.
    """
    cassette = harness.load(CASSETTES / SPARSE)
    report = roundtrip_report(cassette)

    check_roundtrip(report)

    assert report.present_turns == [1, 4], (
        f"the sparse cassette carried state on {report.present_turns}; the "
        "ratio is finding 016's measured 2 of 6 and changing it changes what "
        "this arm is evidence for")
    assert len(report.absent_turns) == 4
    # And the run is not the same run as the full-presence one: a fixture that
    # could not tell them apart would report the same thing for both.
    assert len(report.present_turns) < len(report.observations)


# ---------------------------------------------------------------------------
# Arm 3 — the vacuity guard. The arm that keeps arms 1 and 2 honest.


def test_the_vacuity_guard_refuses_a_cassette_that_never_carries_state():
    """A conditional over an empty population must not read as a pass.

    This is the arm the brief for this task calls the trap. Every assertion in
    `check_roundtrip`'s first two blocks is satisfied by a run in which the
    opaque field never appeared — there is nothing to compare and nothing to
    fabricate — so without the third block a silent provider produces a green
    fixture that has tested nothing at all.

    The cassette is committed rather than built here, so the refusal is
    exercised against the same loader, the same player and the same driver as
    the passing arms.
    """
    cassette = harness.load(CASSETTES / SILENT)
    report = roundtrip_report(cassette)

    assert report.present_turns == []
    assert len(report.absent_turns) == len(cassette.interactions) == 6

    with pytest.raises(AssertionError, match="tested nothing"):
        check_roundtrip(report)

    # And the run really did happen: a report from a cassette that failed to
    # load would also have no present turns, and would also raise here.
    assert report.ledger.chained(), (
        "the silent cassette's chain did not run, so this arm is exercising a "
        "broken fixture rather than an absent field")


# ---------------------------------------------------------------------------
# Arm 4 — the answer cannot detect the loss. Finding 016 result 7, replayed.


def test_the_answer_alone_cannot_detect_the_loss():
    """Why every assertion above is on the bytes.

    Finding 016 stripped the opaque field from a live xAI chain and it *"still
    chained and still answered 149.99."* This is the same demonstration against
    the shipped driver: with the carried state discarded between turns, the
    chain still runs, the tools still receive the right arguments, and the
    final answer is still correct — and `check_roundtrip` still fails.

    So it is not that byte identity is a stronger assertion than the answer. It
    is that the answer is **not an assertion about this at all**.
    """
    cassette = harness.load(CASSETTES / "xai.json")
    driver = driver_for(cassette.provider)
    player = harness.Player(cassette)
    ledger = ToolLedger()

    turns: list[WireTurn] = [WireTurn(role=ROLE_USER,
                                      payload=_user_turn(cassette.provider))]
    final_text = ""
    for index in range(len(cassette.interactions)):
        request = driver.build_request(
            model=cassette.model, system=SYSTEM, turns=turns, tools=TOOLS,
            # The negative control: the state is thrown away, exactly as ADK's
            # adapter threw it away.
            provider_states=())
        assert harness.opaque_in_request(cassette, request) == []

        parsed = driver.parse_response(
            player.respond(index, request, conversation_length=len(turns)))
        assert parsed.assistant is not None
        # And the assistant turn is rebuilt without its opaque field, which is
        # what an adapter that reconstructs from recognised fields produces.
        stripped = dict(parsed.assistant.payload)
        stripped.pop("encrypted_content", None)
        turns.append(WireTurn(role=parsed.assistant.role, payload=stripped))

        if not parsed.tool_calls:
            final_text = parsed.text
            break
        results = tuple(
            ToolResult(call=call, outcome="ok",
                       body=ledger.run(call.name, call.arguments),
                       started_at=0.0, finished_at=0.0)
            for call in parsed.tool_calls)
        for entry in results_to_wire(cassette.provider, results):
            turns.append(WireTurn(role=ROLE_TOOL, payload=entry))

    player.assert_exhausted()
    assert ledger.chained(), "the stripped run did not chain"
    assert "149.99" in final_text, (
        "the stripped run answered wrongly, which would make this arm evidence "
        "that the loss IS observable — the opposite of finding 016's result 7")


# ---------------------------------------------------------------------------
# Arm 5 — provenance. The cassettes may not be cited for the stronger claim.


@pytest.mark.parametrize("filename", PROVIDER_CASSETTES + (SPARSE, SILENT))
def test_no_cassette_may_stand_in_for_a_live_measurement(filename):
    """`require_recorded()` refuses every file here, and that is correct.

    Written as an assertion rather than as a README sentence because the
    sentence is what stops being true when somebody records one of these for
    real and forgets to change the other five.
    """
    cassette = harness.load(CASSETTES / filename)
    with pytest.raises(harness.ProvenanceError, match="synthetic"):
        cassette.require_recorded()
    assert cassette.provenance["payload_source"] == "synthetic"
    assert Path(cassette.provenance["shape_source"]).name.startswith("arm_")
