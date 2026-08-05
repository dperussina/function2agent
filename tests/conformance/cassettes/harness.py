"""T060 — cassette record and replay for provider fixtures.

Constitution Principle VII names cassette-backed provider tests by name. This is
that harness, and it is built on the assumption that **it is itself an
instrument**: a replay harness that matches no cassette, or a recorder that
records nothing, is green by default and says so to nobody.

So four things are refusals rather than fallbacks, and each has a test that
plants it:

1. **A missing cassette file is an error**, never an empty cassette. A fixture
   whose data went missing must fail, not pass over zero interactions.
2. **A cassette with no interactions is an error at load.** Same reason.
3. **A turn with no recorded interaction raises `CassetteMiss`.** It does not
   return an empty payload, and it does not fall through to the next
   interaction in the file — a player that slid forward would answer turn 3
   with turn 4's response and every assertion downstream would be about the
   wrong turn.
4. **`assert_exhausted()` exists and the fixtures call it.** A test that
   consumed one of six interactions and passed has tested one turn while
   reading a file that describes six.

## The provenance field, and why it is not decoration

Finding 016 ran **live and committed no transcripts** — its artifacts hold
SHA-256 digests of the opaque fields, the verdicts, and the token counts, and
nothing else. There is therefore no recorded provider response anywhere in this
repository to build a cassette from. The wire *shapes* here are transcribed from
that harness's four arms, which did drive the real APIs on 2026-08-03; the
opaque *payloads* are synthetic.

`provenance.kind` records that, and `require_recorded()` is the guard that stops
a derived cassette being cited as evidence of provider behaviour. See
`README.md` for the full statement of what these fixtures do and do not
establish.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

CASSETTE_VERSION = 1

#: A cassette whose payloads came off a real provider response. Nothing in this
#: directory carries it yet, and `require_recorded()` is what makes the
#: difference load-bearing rather than a comment.
KIND_RECORDED = "recorded"
#: Wire shape transcribed from a harness that ran live; opaque payloads
#: synthetic. Every cassette here is one of these.
KIND_DERIVED = "derived-shape-synthetic-payload"

_KINDS = (KIND_RECORDED, KIND_DERIVED)

#: The marker a response payload uses to point at a declared opaque value.
#: `{"$opaque": 0}` in the JSON becomes `interactions[i].opaque[0]`'s carrier
#: when the cassette is loaded. The indirection exists so that the declared list
#: is the single source of truth for what the provider emitted — a test can read
#: it without walking the payload, and the payload cannot disagree with it.
OPAQUE_MARKER = "$opaque"

HERE = Path(__file__).resolve().parent


class CassetteError(RuntimeError):
    """A cassette that cannot be used as described."""


class CassetteMiss(CassetteError):
    """A request with no recorded interaction.

    A distinct type because it is the one failure a replay harness must never
    absorb: absorbing it is how a harness reports green over a cassette it never
    matched.
    """


class ProvenanceError(CassetteError):
    """A derived cassette used where a recorded one was required."""


@dataclass(frozen=True)
class OpaqueValue:
    """One opaque field as the cassette declares it.

    `carrier` is `text` or `binary` and it is not cosmetic: Google's
    `thought_signature` is genuinely `bytes` and the other three are strings, so
    a cassette that lost the distinction would hand a driver the wrong type and
    the round-trip would be a type coercion rather than a copy.
    """

    path: tuple[Any, ...]
    carrier: str
    raw: bytes

    def native(self) -> str | bytes:
        if self.carrier == "text":
            return self.raw.decode("utf-8")
        return self.raw


@dataclass(frozen=True)
class Interaction:
    """One recorded turn.

    `expected_state_digest` is a **pin**, not a computation. It is written into
    the file when the cassette is authored and compared against whatever the
    driver produces. If `src/runtime/providers/state.py`'s framing changes, this
    stops matching and has to be re-pinned deliberately — which is the coupling,
    not an inconvenience.

    `request_turns` is the number of conversation entries the driver is expected
    to have accumulated by this turn. It is the player's only precondition on
    the request, and it exists so that replay is not purely ordinal: a driver
    that dropped an assistant turn would otherwise be answered as though it had
    not.
    """

    turn: int
    request_turns: int
    opaque: tuple[OpaqueValue, ...]
    expected_state_digest: str | None
    response: Mapping[str, Any]

    @property
    def state_present(self) -> bool:
        return bool(self.opaque)


@dataclass(frozen=True)
class Cassette:
    provider: str
    model: str
    sdk: str
    sdk_version: str
    provenance: Mapping[str, Any]
    #: A declarative route into a **request** for every opaque field, with `*`
    #: meaning "every index or key at this level". Walked by the conformance
    #: fixture's own reader, which is deliberately a second implementation: an
    #: assertion that read the request back through the driver's own injector
    #: would be satisfied by an injector that wrote nowhere and read nowhere.
    opaque_selectors: tuple[tuple[Any, ...], ...]
    interactions: tuple[Interaction, ...]
    path: Path

    @property
    def kind(self) -> str:
        return str(self.provenance.get("kind", ""))

    def require_recorded(self) -> None:
        """Refuse to let a derived cassette stand in for a measurement."""
        if self.kind != KIND_RECORDED:
            raise ProvenanceError(
                f"{self.path.name} is {self.kind!r}: its wire shape is "
                "transcribed from finding 016's live harness and its opaque "
                "payloads are synthetic. It establishes that this driver does "
                "not lose a field it was given. It does **not** establish that "
                "a provider emitted, accepted or validated one — finding 016 "
                "measured that, and re-measuring it is T164's four-provider "
                "battery, not a replay."
            )

    def turns_with_state(self) -> int:
        return sum(1 for i in self.interactions if i.state_present)

    def turns_without_state(self) -> int:
        return sum(1 for i in self.interactions if not i.state_present)


def load(path: Path) -> Cassette:
    """Read a cassette, refusing every shape that would replay as nothing."""
    if not path.is_file():
        raise CassetteError(
            f"no cassette at {path}. A fixture whose data is missing must fail "
            "here; returning an empty cassette would let it pass over zero "
            "interactions and report that as a provider round-trip."
        )
    try:
        raw = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise CassetteError(f"{path.name} is not JSON: {exc}") from exc

    version = raw.get("cassette_version")
    if version != CASSETTE_VERSION:
        raise CassetteError(
            f"{path.name} is cassette version {version!r}; this reader is "
            f"{CASSETTE_VERSION}. Refused rather than read optimistically.")

    provenance = raw.get("provenance") or {}
    if provenance.get("kind") not in _KINDS:
        raise CassetteError(
            f"{path.name} declares provenance kind {provenance.get('kind')!r}, "
            f"which is not one of {_KINDS}. A cassette with no provenance is "
            "one whose payloads cannot be told from a recording.")

    raw_interactions = raw.get("interactions") or []
    if not raw_interactions:
        raise CassetteError(
            f"{path.name} holds no interactions. A player over an empty "
            "cassette answers nothing and asserts nothing.")

    interactions: list[Interaction] = []
    for position, entry in enumerate(raw_interactions):
        values = tuple(
            OpaqueValue(
                path=tuple(v["path"]),
                carrier=v["carrier"],
                raw=base64.b64decode(v["b64"]),
            )
            for v in entry.get("opaque") or ()
        )
        for value in values:
            if value.carrier not in ("text", "binary"):
                raise CassetteError(
                    f"{path.name} interaction {position}: carrier "
                    f"{value.carrier!r} is neither text nor binary")
        digest = entry.get("expected_state_digest")
        if values and not digest:
            raise CassetteError(
                f"{path.name} interaction {position} declares opaque values "
                "and no expected_state_digest. The digest is the pin; without "
                "it the fixture can only assert that something was carried, "
                "not that it was the right something.")
        if digest and not values:
            raise CassetteError(
                f"{path.name} interaction {position} pins a digest with no "
                "opaque values to produce it")
        interactions.append(Interaction(
            turn=int(entry["turn"]),
            request_turns=int(entry["request_turns"]),
            opaque=values,
            expected_state_digest=digest,
            response=_materialize(entry["response"], values),
        ))

    turns = [i.turn for i in interactions]
    if turns != list(range(len(turns))):
        raise CassetteError(
            f"{path.name} numbers its turns {turns}; they must be dense from "
            "zero, or a player matching by turn silently answers nothing.")

    return Cassette(
        provider=raw["provider"],
        model=raw["model"],
        sdk=raw.get("sdk", ""),
        sdk_version=raw.get("sdk_version", ""),
        provenance=provenance,
        opaque_selectors=tuple(tuple(s) for s in raw.get("opaque_selectors") or ()),
        interactions=tuple(interactions),
        path=path,
    )


def _materialize(node: Any, values: Sequence[OpaqueValue]) -> Any:
    """Replace `{"$opaque": n}` markers with the declared carrier."""
    if isinstance(node, dict):
        if set(node) == {OPAQUE_MARKER}:
            index = node[OPAQUE_MARKER]
            try:
                return values[index].native()
            except IndexError as exc:
                raise CassetteError(
                    f"a response references opaque value {index} and the "
                    f"interaction declares {len(values)}") from exc
        return {k: _materialize(v, values) for k, v in node.items()}
    if isinstance(node, list):
        return [_materialize(v, values) for v in node]
    return node


@dataclass
class Player:
    """Replays one cassette, and refuses everything it was not recorded for."""

    cassette: Cassette
    #: Every request the player was handed, in order. Exposed so a fixture can
    #: assert over what the driver actually built rather than over what it
    #: hoped the driver built.
    requests: list[Mapping[str, Any]] = field(default_factory=list)
    _served: set[int] = field(default_factory=set)

    def respond(
        self, turn: int, request: Mapping[str, Any], *, conversation_length: int
    ) -> Mapping[str, Any]:
        """The recorded response for one turn, or a refusal.

        `conversation_length` is checked against the interaction's
        `request_turns`. Without it replay is purely ordinal and a driver that
        dropped a turn from the conversation would be answered exactly as
        though it had not — which is the failure the cassette is supposed to
        catch.
        """
        if turn < 0 or turn >= len(self.cassette.interactions):
            raise CassetteMiss(
                f"{self.cassette.path.name} has no interaction for turn "
                f"{turn}; it records "
                f"{len(self.cassette.interactions)}. Refused rather than "
                "answered with the nearest one.")
        interaction = self.cassette.interactions[turn]
        if conversation_length != interaction.request_turns:
            raise CassetteMiss(
                f"{self.cassette.path.name} turn {turn} was recorded against a "
                f"conversation of {interaction.request_turns} entries and this "
                f"request carries {conversation_length}. A turn dropped or "
                "duplicated on the way in makes the recorded answer an answer "
                "to a different question.")
        self.requests.append(request)
        self._served.add(turn)
        return interaction.response

    def assert_exhausted(self) -> None:
        """Every recorded interaction was played.

        The guard against the quietest failure of all: a fixture that consumed
        the first interaction, passed, and reported a six-turn chain.
        """
        missing = sorted(
            set(range(len(self.cassette.interactions))) - self._served)
        if missing:
            raise CassetteError(
                f"{self.cassette.path.name}: turns {missing} were never "
                f"played. The cassette describes "
                f"{len(self.cassette.interactions)} turns and the run used "
                f"{len(self._served)}, so whatever passed did not exercise the "
                "chain this file records.")


def walk(node: Any, selector: Sequence[Any]) -> list[Any]:
    """Every value at a declared route, with `*` meaning every child.

    Fifteen lines and no knowledge of any provider, which is the point: the
    conformance fixture reads a driver's request back through *this* rather than
    through the driver's own injector, so an injector that wrote nowhere cannot
    also be the thing that reports nothing was expected.
    """
    if not selector:
        return [node]
    step, rest = selector[0], selector[1:]
    children: list[Any] = []
    if step == "*":
        if isinstance(node, Mapping):
            children = list(node.values())
        elif isinstance(node, (list, tuple)):
            children = list(node)
    else:
        try:
            children = [node[step]]
        except (KeyError, IndexError, TypeError):
            return []
    out: list[Any] = []
    for child in children:
        out.extend(walk(child, rest))
    return [v for v in out if v is not None]


def opaque_in_request(cassette: Cassette, request: Mapping[str, Any]) -> list[Any]:
    """Every opaque value the request carries, found by the cassette's routes."""
    found: list[Any] = []
    for selector in cassette.opaque_selectors:
        found.extend(walk(request, selector))
    return found


def cassette_paths() -> list[Path]:
    """Every committed cassette, sorted. Used by the fixtures to enumerate."""
    return sorted(HERE.glob("*.json"))


def record_stub(provider: str) -> None:  # pragma: no cover - costs money
    """The recorder, and the one thing it does today: refuse.

    Recording a cassette means driving a real provider, which costs money and
    needs `F2A_ENV_ROOT` credentials. That is not done here and the reason is
    not thrift: finding 016 already measured what a live run would establish —
    all four vendors chain, emit, preserve and accept their opaque field — and
    a second live run would re-measure it rather than measure anything new.

    What a recording *would* add is `KIND_RECORDED` provenance on these
    payloads, which is worth having and is not worth taking without an owner
    saying so. The stub is here so the absence is a named surface rather than a
    missing function.
    """
    raise NotImplementedError(
        f"recording a {provider} cassette makes paid API calls. It is not "
        "wired up: see README.md, 'What a recording would add'."
    )
