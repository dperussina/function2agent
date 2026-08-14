"""T170 — cassette-backed provider tests over the core path.

Constitution Principle VII names cassette-backed provider tests. T060 is the
harness; T061 drives `build_request` / `parse_response` over a fixture-local
conversation. This file is the remaining claim: the **core path**
(`AgentLoop.run`, the turn record, the journal) consumes a cassette-backed
driver the same way it would consume a live one, for all four providers,
without calling `ProviderDriver.call`.

## What the core-path hook is

`AgentLoop` never calls `build_request`. It calls a `ModelClient` with a
`Context` whose `provider_states` came from the `TurnRecord`s the loop itself
wrote (`_record` copies `response.provider_state`; the next `assemble` /
`states_for` hands those bytes back). This file's client is the narrowest
entry that is still that path: it takes those states from the `Context` the
loop assembled and passes them to `build_request`, plays the cassette instead
of `call`, applies `parse_response`, and returns a `ModelResponse` so the
loop journals the turn.

Removing that hook — `_record` dropping `provider_state`, or this client
passing `()` into `build_request` — leaves T061 green. T061 builds its own
`TurnRecord`s and never goes through `AgentLoop._record` or the journal.

## What T061 still uniquely owns

Driver-level conversation accumulation (`_persisted` / `_rebuilt`), the
conditional byte-identity assertion, the vacuity guard, and the
answer-cannot-detect-the-loss arm. This file reuses those helpers and does
not retick T060/T061.

## What this is not

Not a live SDK call (T058 PARTIAL). Not T164 (configuration-only selection).
Not T215 (`Registry` / `build_server`). Not a `KIND_RECORDED` cassette.
Not a third cassette harness — `Player` and the committed JSON stay T060's.

**Residual, named.** Nothing in `src/` is a `ModelClient` that accumulates
`WireTurn`s and calls `build_request`. The loop talks `Context` →
`ModelResponse`. Wire-shape conversation accumulation lives in T061's
helpers and in this test client. That adapter is not invented here as
product; it is the test-side stand-in that lets the loop consume a cassette
without a fake `call` or a serve loop.
"""

from __future__ import annotations

import ast
import datetime as dt
from pathlib import Path

import pytest

from src.contracts.config import Config
from src.runtime.context import Context
from src.runtime.dispatch import ToolCall, ToolResult
from src.runtime.journal import MODEL_STEP_INDEX, STEP_MODEL_CALL
from src.runtime.providers import ROLE_USER, WireTurn
from src.runtime.providers.adapter import model_response
from src.runtime.providers.base import PROVIDERS, TransportUnavailableError
from src.runtime.providers.costs import OperatorPrice, OperatorPriceBook, Rate
from src.runtime.providers.schema import results_to_wire
from src.runtime.providers.select import select
from src.runtime.turn import ModelResponse, state_digest
from tests.conformance.cassettes import harness
from tests.conformance.test_provider_state_roundtrip import (
    CASSETTES,
    PROMPT,
    PROVIDER_CASSETTES,
    SYSTEM,
    TOOLS,
    Report,
    ToolLedger,
    TurnObservation,
    _persisted,
    _rebuilt,
    _result_role,
    _user_turn,
    check_roundtrip,
)
from tests.unit.test_loop import SESSION, Harness, _ceilings

AS_OF = dt.date(2026, 8, 5)
THIS = Path(__file__).resolve()
T061 = THIS.with_name("test_provider_state_roundtrip.py")

#: The core-path hook in this client. `build_request` receives the states the
#: loop assembled from its own `TurnRecord`s. Passing `()` here is T061 in a
#: new filename: the driver still round-trips, the loop's bytes never leave.
CORE_PATH_STATES = True

#: Local alias so a missing cassette is a collection error here, not a quieter
#: T061 parametrization that shrank. T061 still owns `PROVIDER_CASSETTES`.
CORE_PATH_CASSETTES = PROVIDER_CASSETTES

#: OD-27's declared rate for the one cassette model `costs.PRICES` refuses.
#: Always passed; priced providers ignore it. Not a per-provider branch.
_OPENAI_DECLARED = OperatorPriceBook([OperatorPrice(
    provider="openai", model="gpt-5-mini", display_name="GPT-5 mini",
    tiers=(Rate(0.25, 2.00),
           Rate(0.50, 4.00, min_input_tokens=128_000)),
    declared_by="platform-eng@example.invalid",
    declaration_ref="contracts/openai-2026-q3.md",
    declared_on="2026-08-01",
    scope="standard synchronous tier, uncached input, text",
)])


def _config(cassette: harness.Cassette) -> Config:
    """`MODEL_PROVIDER` is the per-provider knob; `MODEL_ID` rides with it."""
    return Config(values={
        "MODEL_PROVIDER": cassette.provider,
        "MODEL_ID": cassette.model,
    })


class CassetteBackedClient:
    """`ModelClient` that plays a cassette instead of `ProviderDriver.call`.

    Conversation bodies are T061's persisted/rebuilt `WireTurn`s — the
    production path has no accumulator yet (named residual). Opaque state
    is **not** taken from that conversation: it comes from
    `context.provider_states`, which the loop assembled.
    """

    def __init__(
        self,
        cassette: harness.Cassette,
        player: harness.Player,
        ledger: ToolLedger,
    ) -> None:
        selected = select(_config(cassette))
        self.selected = selected
        self.cassette = cassette
        self.player = player
        self.ledger = ledger
        self.persisted: list[WireTurn] = [
            WireTurn(role=ROLE_USER, payload=_user_turn(cassette.provider)),
        ]
        self.observations: list[TurnObservation] = []
        self._pending_calls: tuple[ToolCall, ...] = ()
        self._bodies: dict[str, str] = {}
        self.final_text = ""

    def note_body(self, call_id: str, body: str) -> None:
        self._bodies[call_id] = body

    def execute(self, call: ToolCall) -> str:
        body = self.ledger.run(call.name, call.arguments)
        self.note_body(call.call_id, body)
        return body

    def __call__(self, context: Context) -> ModelResponse:
        if context.dropped_turns != 0:
            raise AssertionError(
                f"{self.cassette.provider}: the loop's assembler dropped "
                f"{context.dropped_turns} turns, so this arm is measuring "
                "truncation rather than the core-path round trip"
            )
        self._append_pending_results()
        turns = _rebuilt(self.persisted)
        index = len(self.observations)
        interaction = self.cassette.interactions[index]
        states = context.provider_states if CORE_PATH_STATES else ()
        request = self.selected.driver.build_request(
            model=self.selected.model, system=SYSTEM, turns=turns,
            tools=TOOLS, provider_states=states)
        carried = tuple(harness.opaque_in_request(self.cassette, request))
        previous = self.observations[-1].declared if self.observations else ()
        self.observations.append(TurnObservation(
            turn=index,
            declared=tuple(v.native() for v in interaction.opaque),
            carried=carried,
            reinjected=carried[-len(previous):] if previous else (),
            digest=None, pinned=interaction.expected_state_digest,
        ))
        payload = self.player.respond(
            index, request, conversation_length=len(turns))
        parsed = self.selected.driver.parse_response(payload)
        self.observations[-1].digest = state_digest(parsed.provider_state)
        assert parsed.assistant is not None
        self.persisted.append(_persisted(parsed.assistant, interaction))
        self._pending_calls = parsed.tool_calls
        if not parsed.tool_calls:
            self.final_text = parsed.text
        return model_response(
            parsed, model=self.selected.model, as_of=AS_OF,
            operator_prices=_OPENAI_DECLARED)

    def _append_pending_results(self) -> None:
        if not self._pending_calls:
            return
        results = tuple(
            ToolResult(
                call=call, outcome="ok",
                body=self._bodies[call.call_id],
                started_at=0.0, finished_at=0.0)
            for call in self._pending_calls
        )
        for entry in results_to_wire(self.cassette.provider, results):
            self.persisted.append(WireTurn(
                role=_result_role(self.cassette.provider), payload=entry))
        self._pending_calls = ()

    def report(self) -> Report:
        return Report(
            provider=self.cassette.provider, model=self.cassette.model,
            observations=self.observations, ledger=self.ledger,
            final_text=self.final_text, requests=self.player.requests)


def _run_core_path(tmp_path: Path, filename: str) -> tuple[
    harness.Cassette, CassetteBackedClient, Harness,
]:
    cassette = harness.load(CASSETTES / filename)
    player = harness.Player(cassette)
    ledger = ToolLedger()
    client = CassetteBackedClient(cassette, player, ledger)
    h = Harness(
        tmp_path,
        ceilings=_ceilings(spend_usd=1_000.0, tokens=10 ** 9, turns=20),
        bound_tokens=1_000,
    )
    h.machine.start(SESSION, at=1.0)
    outcome = h.loop(client, client.execute).run(PROMPT)
    assert outcome.terminal_state is not None
    player.assert_exhausted()
    return cassette, client, h


# ---------------------------------------------------------------------------
# The four providers, through the loop.


@pytest.mark.parametrize("filename", CORE_PATH_CASSETTES)
def test_the_loop_round_trips_cassette_state_for_every_provider(
    tmp_path, filename,
) -> None:
    """The loop's next-turn bytes match what T061 already checks at the driver.

    `CORE_PATH_STATES` and `AgentLoop._record`'s `provider_state=` are the
    hooks. A green T061 after either is removed is the proof this file is
    not a rename.
    """
    cassette, client, h = _run_core_path(tmp_path, filename)
    report = client.report()

    assert report.ledger.chained(), (
        f"{cassette.provider}: the chain did not run as recorded through "
        f"the loop. Calls were {[name for name, _ in report.ledger.calls]}"
    )
    assert "149.99" in report.final_text
    check_roundtrip(report)
    assert len(report.present_turns) == len(report.observations)

    model_steps = [
        step for step in h.journal.steps(SESSION)
        if step.step_kind == STEP_MODEL_CALL
        and step.step_index == MODEL_STEP_INDEX
        and step.outcome is not None
    ]
    assert len(model_steps) == len(cassette.interactions), (
        f"{cassette.provider}: the journal recorded {len(model_steps)} "
        f"model outcomes against {len(cassette.interactions)} cassette "
        "turns. T061 does not write a journal; this is the core-path claim."
    )
    for step, interaction in zip(model_steps, cassette.interactions):
        if interaction.expected_state_digest is None:
            assert step.provider_state is None
        else:
            assert step.provider_state is not None
            assert state_digest(step.provider_state) == (
                interaction.expected_state_digest
            )

    with pytest.raises(harness.ProvenanceError, match="synthetic"):
        cassette.require_recorded()
    h.close()


def test_every_closed_provider_has_a_core_path_cassette() -> None:
    covered = {
        harness.load(CASSETTES / name).provider for name in CORE_PATH_CASSETTES
    }
    assert covered == set(PROVIDERS)


def test_the_runs_differ_only_in_configuration() -> None:
    """`MODEL_PROVIDER` / matching `MODEL_ID`. No per-provider branch."""
    runs = [
        _config(harness.load(CASSETTES / name)).values
        for name in CORE_PATH_CASSETTES
    ]
    expected_keys = frozenset({"MODEL_PROVIDER", "MODEL_ID"})
    assert [frozenset(run) for run in runs] == [expected_keys] * len(runs)
    named = [run["MODEL_PROVIDER"] for run in runs]
    assert len(set(named)) == len(CORE_PATH_CASSETTES)


def test_this_file_drives_the_loop_and_t061_does_not() -> None:
    """A rename of T061 would import no `AgentLoop` and write no journal."""
    here = THIS.read_text()
    there = T061.read_text()
    assert "AgentLoop" in here or "h.loop(" in here
    assert ".run(" in here
    assert "CORE_PATH_STATES" in here
    assert "CORE_PATH_CASSETTES" in here
    assert "AgentLoop" not in there
    assert "TurnJournal" not in there
    assert "CORE_PATH_STATES" not in there


def test_call_is_not_the_cassette_player() -> None:
    """T058 PARTIAL: `call` still raises. This file must not become a fake."""
    cassette = harness.load(CASSETTES / CORE_PATH_CASSETTES[0])
    selected = select(_config(cassette))
    with pytest.raises(TransportUnavailableError, match="FR-021"):
        selected.driver.call({"model": selected.model})


def test_this_file_does_not_import_a_vendor_sdk() -> None:
    tree = ast.parse(THIS.read_text(), filename=str(THIS))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
    sdk_modules = {
        select(_config(harness.load(CASSETTES / name))).driver.sdk_module
        for name in CORE_PATH_CASSETTES
    }
    overlap = names & (set(PROVIDERS) | sdk_modules)
    assert not overlap, overlap
    assert "src.runtime.serving" not in names
    assert not any("build_server" in n for n in names)
