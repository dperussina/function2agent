# Provider cassettes — T060

**Task**: T060. **Requirement**: constitution Principle VII, which names cassette-backed
provider tests by name. **Read by**:
[`tests/conformance/test_provider_state_roundtrip.py`](../test_provider_state_roundtrip.py) (T061)
and [`tests/unit/test_cassette_harness.py`](../../unit/test_cassette_harness.py).

## What these establish, and what they do not

**Do**: the four drivers in [`src/runtime/providers/`](../../../src/runtime/providers/) extract a
provider's opaque reasoning field from a response of that provider's shape, carry it as bytes
through an internal representation, and put it back into the next request **byte-identically**,
across a six-turn chain of five dependent tool hops — including a payload containing a NUL and a
bare UTF-8 continuation byte.

**Do not**: establish that any provider emitted, accepted or validated one of these. The wire
*shapes* are transcribed from a harness that ran live; the opaque *payloads* are synthetic. Every
file declares `provenance.kind` as `derived-shape-synthetic-payload`, and
`Cassette.require_recorded()` raises for all six — asserted in
`test_no_cassette_may_stand_in_for_a_live_measurement`, so the distinction cannot be forgotten by a
reader who never opens this file.

**Do not**: exercise any vendor SDK. `ProviderDriver.call` is the transport half and nothing here
reaches it. See [`base.py`](../../../src/runtime/providers/base.py) for why the driver is split.

## Why the payloads are synthetic, and what a recording would cost

[Finding 016](../../../specs/001-discovery-validation/findings/016-provider-sdk-roundtrip.md) drove
all four vendor SDKs against the live APIs on 2026-08-03 and **committed no transcripts**. Its
artifacts in
[`results/`](../../../specs/001-discovery-validation/harness/provider-sdk-roundtrip/results/) hold
SHA-256 digests of the opaque fields, the four verdicts per arm, token counts and one dollar figure.
There is no recorded provider response anywhere in this repository to build a cassette from.

So the shapes here are transcribed from that harness's four arm modules, which are committed and
which did drive the real APIs:

| provider | shape transcribed from | opaque field | carrier |
| --- | --- | --- | --- |
| Anthropic | `arm_anthropic.py` | `content[].signature` on a `thinking` block | text |
| OpenAI | `arm_openai.py` | `output[].encrypted_content` on a `reasoning` item | text |
| Google | `arm_google.py` | `parts[].thought_signature` | **binary** |
| xAI | `arm_xai.py` | `message.encrypted_content` | text |

### What a recording would add

`KIND_RECORDED` provenance, and with it the ability to say that these payloads are shaped the way a
provider actually shapes them rather than the way our transcription says. That is worth having and
it is **not** worth taking without an owner deciding to spend, for one reason: finding 016 already
measured what a live run establishes — all four vendors chain, emit, preserve and accept their
opaque field — so a recording re-measures a measured thing. The one claim it would newly support is
about our transcription, and the four arm modules are committed source that a reader can check
against the vendors' documentation without spending anything.

`harness.record_stub()` raises rather than being absent, so the gap is a named surface.

## The two cassettes that are not providers

`anthropic-adaptive-sparse.json` and `anthropic-adaptive-silent.json` describe an assertion shape,
not a vendor.

Finding 016 result 8 measured `claude-sonnet-5` under adaptive thinking emitting opaque state on
**2 of 6** runs in the committed batch. So:

- **sparse** carries state on 2 of 6 turns. It is what makes T061's assertion a *conditional* —
  *whenever the field is present it survives byte-identical* — rather than an unconditional presence
  check, which would be flaky against a real provider and would be deleted the first week it went
  red.
- **silent** carries it on **0 of 6**, and exists only so that the conditional's own trap is
  exercised. A conditional is vacuously true over an empty population, so a run where the field
  never appeared passes every byte-identity assertion while testing nothing.
  `check_roundtrip` refuses that case and `test_the_vacuity_guard_refuses_a_cassette_that_never_carries_state`
  is what runs the refusal.

## The file format

```jsonc
{
  "cassette_version": 1,
  "provider": "anthropic",
  "model": "claude-sonnet-4-5-20250929",
  "provenance": { "kind": "derived-shape-synthetic-payload", ... },
  "opaque_selectors": [["messages", "*", "content", "*", "signature"]],
  "interactions": [
    {
      "turn": 0,
      "request_turns": 1,
      "opaque": [{"path": ["content", 0, "signature"], "carrier": "text", "b64": "..."}],
      "expected_state_digest": "sha256:...",
      "response": { "content": [{"type": "thinking", "signature": {"$opaque": 0}}] }
    }
  ]
}
```

Four fields carry the load.

**`opaque`** is the declared list of what the provider emitted, and it is the single source of
truth. The response payload points at it with `{"$opaque": n}` markers, materialized at load, so the
two cannot disagree.

**`expected_state_digest`** is a **pin**, frozen by `build_cassettes.py`, not a value the fixture
recomputes. A change to `src/runtime/providers/state.py`'s framing stops every cassette matching and
forces a deliberate re-pin in the same commit. A one-bit flip in a payload fails the fixture; that
was run, and the proof is in `tests/removal_proofs.sh`.

**`request_turns`** is the conversation length the turn was recorded against. Without it replay is
purely ordinal, and a driver that dropped an assistant entry would be handed exactly the response it
would have been handed anyway.

**`opaque_selectors`** is a declarative route into a *request*, walked by `harness.walk` — which
knows no provider, asserted in `test_the_walker_is_not_the_drivers_injector`. T061 reads a driver's
built request back through that rather than through the driver's own injector, because an assertion
that used the injector would be satisfied by an injector that wrote nowhere.

## Regenerating

```bash
.venv/bin/python tests/conformance/cassettes/build_cassettes.py
```

Deliberate, not automatic. The output is the fixture (FR-053), and the digests it writes are pins.
