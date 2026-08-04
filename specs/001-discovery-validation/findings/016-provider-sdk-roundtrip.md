# Finding 016 — Does the opaque-state round-trip survive each vendor's own SDK?

**Date**: 2026-08-03
**User Story**: 1 (drive the runtime against independent model providers)
**Model spend**: **25,214 tokens** across the committed artifacts — 23,222 in, 1,992 out —
against a self-imposed ceiling of **$2.00**. One provider reports a server-side cost:
xAI's usage proto carries `cost_in_usd_ticks`, and **the xAI arm's three turns total
$0.001860**. That is the only dollar figure measured anywhere in this experiment — it covers
one of the eight artifacts, and the xAI spend inside the negative control is *not* captured,
because cost extraction was added to the arm and not to the control. The other three providers
report tokens only, and **this finding does not convert them
to dollars**, because doing so needs a per-provider price table and the per-provider cost
table is one of the nine capabilities **U-48** records as having no owner. Inventing four
price lists to close a spend line would be exactly the unsourced number that register exists
to prevent. Two of the eight artifacts cost nothing at all: the model-list probe and the
static field count are free.
**Method**: A dedicated Python 3.12.11 virtualenv at `/tmp/f2a-probe-e16`, built separately
from the shared `/tmp/f2a-probe-runtime` so that installing four vendor SDKs could not
disturb the pinned `google-adk` / `litellm` environment findings 003 and 006 depend on. SDKs:
`anthropic` 0.120.2, `openai` 2.52.1, `google-genai` 2.16.0, `xai-sdk` 1.17.0 — **no
abstraction layer in any path**. Every verdict is decided programmatically: chaining by a
tool-dispatch ledger that records what each hop was called with, round-trip survival by
SHA-256 over the opaque field hashed on receipt and again after the SDK has put it into
request shape. No verdict is decided by reading model prose. Credentials resolve through
`F2A_ENV_ROOT` with no default; no value is printed, logged or written, and each arm records
only a variable name and a twelve-hex fingerprint. Harness:
[`harness/provider-sdk-roundtrip/`](../harness/provider-sdk-roundtrip/).

## Why this probe

[Finding 003](./003-runtime-provider-agnosticism.md) established that four providers could be
driven with chained tool calling. It measured that **through ADK and through `litellm`**.
[`OD-15`](../plan.md) removed ADK and [`OD-16`](../plan.md) removed `litellm`, which is why
OD-16 records that **SC-010 becomes a test v1 must pass rather than a result it inherits**.

Nothing in this corpus had driven a chained tool sequence with an opaque-state round-trip
through any vendor's own SDK. That left **FR-037** — provider-opaque reasoning state
round-tripped verbatim — resting on a result measured through two layers that no longer
exist, and it left the tool-schema-translation line of the U-48 re-derivation unsizeable.

The specific failure this is aimed at is finding 003 result 7: ADK's LiteLLM adapter
referenced `encrypted_content`, xAI's opaque reasoning field, **zero times under every
counting rule**, against 35, 16 and 9 for the other three providers' fields. Chained tool use
worked anyway, and finding 003 recorded that as *"a weak result and should not be read as
clearance."*

## The scenario

One scenario, four SDKs, deliberately dependent so a pass means chaining rather than two
independent calls that both fired:

```
lookup_customer_order("Dana Whitfield") -> {"order_id": "ORD-7731"}
get_order_total("ORD-7731")             -> {"total_usd": 149.99}
```

`ORD-7731` appears nowhere in the prompt and is not derivable from it; `get_order_total`
errors on any id it was not given. Chaining is asserted from the dispatch ledger — hop 2 ran
with the id hop 1 returned — not inferred from the final answer.

## Results

| # | Question | Verdict | Evidence |
|---|---|---|---|
| 1 | Does chained tool use work through each vendor's own SDK? | **Yes, 4 / 4** | `anthropic`, `openai`, `google-genai`, `xai-sdk` each ran both hops with the dependent id and answered 149.99 |
| 2 | Is provider-opaque reasoning state emitted at all? | **Yes, 4 / 4** on the models tested | `thinking.signature`, `reasoning.encrypted_content`, `Part.thought_signature`, `message.encrypted_content` |
| 3 | Does the SDK round-trip it without mutation? | **Yes, 4 / 4**, byte-identical | SHA-256 on receipt equals SHA-256 after conversion to request shape, every arm |
| 4 | Does the provider accept the re-injected state? | **Yes, 4 / 4** | the following turn succeeded in every arm; Anthropic and Google validate their field server-side |
| 5 | **Does xAI's `encrypted_content` survive — the field ADK dropped?** | **Yes** | three signatures across three turns, all byte-identical. `xai-sdk` names the field on **31 source lines across 5 files**; ADK's LiteLLM adapter named it on **0** |
| 6 | **Can the detector actually fail?** | **Yes — and this is what makes 3 meaningful** | the negative control strips the field before re-injection and the digest comparison fires |
| 7 | **Does dropping the field break anything observable at two hops?** | **No.** Chaining still succeeded and the answer was still correct | the negative control chained and answered 149.99 *with the opaque field removed entirely* |
| 8 | Is opaque state emitted *deterministically*? | **No** | `claude-sonnet-5` under adaptive thinking emitted it on **2 of 6** runs in the committed batch — one artifact containing both outcomes. An earlier batch ran 4 of 6 but was overwritten; see Gaps. Chaining succeeded 6/6 regardless |
| 9 | Does the request shape generalize across one vendor's own models? | **No** | `claude-sonnet-5` rejects `thinking={"type":"enabled","budget_tokens":N}` with HTTP 400 *"not supported for this model. Use `thinking.type.adaptive` and `output_config.effort`"* |

### Per-arm detail

| provider | SDK | model | opaque field | present | preserved | accepted | chained |
|---|---|---|---|---|---|---|---|
| Anthropic | `anthropic` 0.120.2 | `claude-sonnet-4-5-20250929` | `thinking.signature` | yes | yes | yes | yes |
| OpenAI | `openai` 2.52.1 | `gpt-5-mini` | `reasoning.encrypted_content` | yes | yes | yes | yes |
| Google | `google-genai` 2.16.0 | `gemini-3-flash-preview` | `Part.thought_signature` | yes | yes | yes | yes |
| xAI | `xai-sdk` 1.17.0 | `grok-4.5` | `message.encrypted_content` | yes | yes | yes | yes |

OpenAI's arm runs `store=False` with `include=["reasoning.encrypted_content"]`, which is the
configuration where the provider keeps nothing server-side and the round-trip is therefore
*ours* to get right. With `store=True` an adapter that drops the field is invisible.

### The static count, against finding 003's own rule

Same counting rule finding 003's reconstruction established — source lines containing the
identifier, what `grep -c` reports — applied to the replacement:

| provider | field | ADK LiteLLM adapter (finding 003) | vendor SDK (this finding) |
|---|---|---|---|
| Google | `thought_signature` | 35 | 28 |
| Anthropic | `thinking_blocks` → `signature` | 16 | 54 |
| OpenAI | `reasoning_content` → `encrypted_content` | 9 | 48 |
| **xAI** | **`encrypted_content`** | **0** | **31** |

One asymmetry, stated rather than hidden: finding 003 counted **one module**, because that
was the whole adapter; this counts **one package**, because a vendor SDK spreads its wire
types across files. A package is the larger surface, so a non-zero count here is weaker
evidence of good handling than zero was of absent handling. Zero remains decisive either way.
Results 1–5 are what establish the field is *carried*; this table only establishes it is
*named*.

## The result that matters most is result 7, and it is not the reassuring one

Results 1–5 say FR-037's round-trip holds on all four providers through their own SDKs. That
is the answer OD-16 needed, and it is a clean pass.

**Result 7 says the test that produced it is nearly insensitive.** With `encrypted_content`
stripped off every assistant message before re-injection, xAI still chained correctly and
still answered 149.99. Nothing in the observable behaviour of a two-hop task changes when the
opaque field is thrown away.

So finding 003's caution was right, and it is now measured rather than suspected:

> Chained tool use did work on xAI in this probe, so the gap did not bite at two hops on a
> trivial task; that is a weak result and should not be read as clearance.

Three consequences, all of which bind v1:

1. **A conformance fixture must assert the digest, not the answer.** A fixture that drives a
   chain and checks the output would have passed ADK's adapter while it was dropping the
   field. The assertion that catches it is byte-identity of the opaque field across the
   round-trip.
2. **Two hops is not enough to characterise the failure**, only enough to detect it
   structurally. Whatever depth actually makes opaque-state loss bite is **unmeasured**, and
   this finding does not claim to know it.
3. **The fixture must assert a conditional, not a presence.** Result 8 measured the field
   absent on 6 of 12 runs of one adaptive-thinking model. `assert opaque_state_present` would
   be flaky. The assertion that holds is *whenever the field is present, it survives
   byte-identical* — which held on 100% of runs where it was present.

## What this does not establish

- **Two hops, one task, one shape.** Nothing here speaks to long conversations, many tools,
  parallel tool calls within a single turn, or streaming. Result 7 is the direct evidence that
  this depth is not sufficient to characterise the risk.
- **Acceptance is not use.** `provider_accepted` is inferred from the next turn not erroring.
  A provider that silently ignored a well-formed field would pass. Separating the two needs a
  task whose answer depends on the reasoning content; this scenario is too small to supply one.
- **One run per arm.** Only the Anthropic arm was repeated. Per-arm variance for the other
  three is unmeasured.
- **Result 8's "6 of 12" is half committed.** The committed artifact
  [`results/repeat-adaptive.json`](../harness/provider-sdk-roundtrip/results/repeat-adaptive.json)
  holds one 6-run batch, which found 2 present and 4 absent. The earlier batch that found 4 present
  and 2 absent ran during harness development and **its artifact was overwritten by the final clean
  run**, so only the first batch's total survives in prose. The load-bearing claim — that emission
  is not deterministic — is established by the committed batch alone, which contains both outcomes.
  The 12-run denominator is not independently checkable and should be read as the weaker half.
- **One credential set**, as in [finding 002](./002-provider-credentials.md). All four
  authenticate; a third party supplies their own.
- **No environmental failures occurred.** All four credentials authenticated and all four arms
  completed, so the harness's environmental-versus-capability split — built because finding
  003 had a dead key that looked like a capability result — was never exercised in anger. It
  is present and untested.

## What this changes

**SC-010's provider-capability half now has direct evidence under OD-15 and OD-16.** All four
providers chain, and all four round-trip their opaque state through their own SDK. The
adapter-implementation half is ours to write, and this finding says the shape of it is a
per-provider field extractor plus a verbatim re-injection path, not a translation layer — each
SDK already carries its own field correctly, so the driver's job is to *not lose it* rather
than to reconstruct it.

**FR-037 is satisfiable on all four providers.** It was previously resting on a measurement
taken through two removed layers.

**Result 9 bounds how thin a "thin provider driver" can be.** The request shape for extended
thinking is model-specific *within one vendor* — `claude-sonnet-5` rejects the shape
`claude-sonnet-4-5` requires. A driver cannot be one function per provider; it needs a
per-model capability branch, and that branch is a maintenance surface that tracks vendor
releases.

## Reproduction

```bash
cd specs/001-discovery-validation/harness/provider-sdk-roundtrip
export F2A_ENV_ROOT=/path/to/tree
export F2A_GEMINI_VAR=GEMINI_API_KEY_2
./run.sh
```

Committed artifacts are in [`results/`](../harness/provider-sdk-roundtrip/results/), one JSON
per arm plus `SUMMARY.json`. The harness README carries the full
[Scope and Gaps](../harness/provider-sdk-roundtrip/README.md#scope--what-this-harness-does-not-establish)
sections.
