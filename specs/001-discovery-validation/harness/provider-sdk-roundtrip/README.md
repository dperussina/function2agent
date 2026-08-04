# E16 — opaque-state round-trip through each vendor's own SDK

Produces [finding 016](../../findings/016-provider-sdk-roundtrip.md).

**What it measures.** Whether a chained tool sequence and a verbatim
round-trip of provider-opaque reasoning state both survive when each of
SC-010's four providers is driven through *that vendor's own SDK*, with no
abstraction layer anywhere in the path.

**Why it exists.** [`OD-16`](../../plan.md) replaced `litellm` with direct
vendor SDKs, and [`OD-15`](../../plan.md) removed ADK. Between them they
removed both layers that [finding 003](../../findings/003-runtime-provider-agnosticism.md)'s
four-provider result was measured through, which is why **SC-010 is now a test
v1 must pass rather than a result it inherits**. Nothing in this corpus had
driven a chained sequence with an opaque-state round-trip through a vendor SDK
before this harness.

The specific thing under test is the one finding 003 result 7 measured
non-compliant: ADK's LiteLLM adapter referenced `encrypted_content` — xAI's
opaque reasoning field — **zero times under every counting rule**, while
chained tool use kept working, so the gap did not announce itself.

## Running it

```bash
export F2A_ENV_ROOT=/path/to/tree        # required, no default
export F2A_GEMINI_VAR=GEMINI_API_KEY_2   # optional; see finding 002
./run.sh [output-dir]                    # defaults to results/
```

`F2A_PYTHON` selects the interpreter. The environment used for the committed
results was a dedicated Python 3.12.11 virtualenv at `/tmp/f2a-probe-e16`,
built separately from the shared `/tmp/f2a-probe-runtime` one so that
installing four vendor SDKs could not disturb the pinned `google-adk` /
`litellm` environment that findings 003 and 006 depend on.

SDK versions used, from the committed artifacts: `anthropic` 0.120.2,
`openai` 2.52.1, `google-genai` 2.16.0, `xai-sdk` 1.17.0.

## The scenario

One scenario, four SDKs, deliberately *dependent* so that a pass means chaining
rather than two independent calls that both happened to fire:

```
lookup_customer_order("Dana Whitfield") -> {"order_id": "ORD-7731"}
get_order_total("ORD-7731")             -> {"total_usd": 149.99}
```

`ORD-7731` appears nowhere in the prompt and is not derivable from it, and
`get_order_total` returns an error for any id it was not given, so a guessed id
is a visible failure rather than a silent pass. `scenario.ToolLog.chained()`
asserts hop 2 ran with the id hop 1 returned; it does not infer chaining from
the final answer.

## What each arm asserts, and why they are separate

| check | what it establishes |
|---|---|
| `opaque_state_present` | the provider emitted an opaque field at all. If not, the round-trip is **untestable** here and the arm says so rather than passing by default |
| `sdk_preserved` | the field is hashed on receipt and again after the SDK has put it into the shape the next request needs. Equal digests mean the SDK's own round-trip did not mutate it. **This is the half an adapter breaks** |
| `provider_accepted` | the next request carrying the re-injected state succeeded. Providers that sign their opaque field reject a corrupted one, so this is independent of the digest check rather than a restatement |
| `chained` | hop 2 ran with hop 1's id |
| `answer_correct` | the final text states the total |

An arm can pass `chained` and fail `sdk_preserved` — that combination is
exactly what finding 003 observed on xAI, and it is why the columns are not
collapsed into one verdict.

## Files

| file | what it does | model spend |
|---|---|---|
| `envroot.py` | credential resolution, `--env-root` / `F2A_ENV_ROOT`, no default | none |
| `scenario.py` | the two-hop dependent tool surface, shared by all arms | none |
| `verdict.py` | the result record and the digest rule | none |
| `list_models.py` | free probe: what each credential can actually reach | none |
| `count_vendor_fields.py` | free static count of each vendor SDK's references to its own opaque field, against finding 003's counting rule | none |
| `arm_anthropic.py` | arm 1 — `thinking.signature` | yes |
| `arm_openai.py` | arm 2 — `reasoning.encrypted_content`, `store=False` | yes |
| `arm_google.py` | arm 3 — `Part.thought_signature` | yes |
| `arm_xai.py` | arm 4 — `message.encrypted_content` | yes |
| `negative_control.py` | drops the field on re-injection and checks the detector fires | yes |
| `repeat_adaptive.py` | is opaque state emitted *deterministically*? | yes |
| `summarize.py` | folds artifacts into `SUMMARY.json` | none |

## The negative control is not optional

Four arms reporting `sdk_preserved: true` is worth nothing unless that field
can be false. `negative_control.py` drives the same scenario through the same
SDK, strips `encrypted_content` off every assistant message before
re-injection, and asserts the digest comparison notices.

It does — and it also establishes the more useful half: **chaining still
succeeded with the field dropped.** The two-hop behavioural test is *not*
sensitive to opaque-state loss. Only the digest check is. That confirms finding
003's caution by direct measurement instead of inheriting it, and it bounds
what the four positive arms prove.

## Credential handling

No credential value is printed, logged, returned, or written to any artifact.
Each arm records the *variable name* it read and a twelve-hex SHA-256
fingerprint of the value, the same handle convention
[`provider-credentials`](../provider-credentials/) uses. There is no absolute
path to anyone's filesystem anywhere in this directory, and no default search
root — `run.sh` exits `64` if `F2A_ENV_ROOT` is unset.

## Scratch

Nothing here writes outside its own `results/` directory and the operator's
chosen virtualenv. The repository and `examples/` are untouched (FR-018).

## Scope — what this harness does not establish

- **Two hops, not a long chain.** This is the same depth finding 003 drove, and
  finding 003 explicitly declined to read a two-hop pass as clearance. The
  negative control shows why that caution was right: chaining survived the
  field being dropped entirely. **A two-hop scenario cannot detect opaque-state
  loss behaviourally.** The conformance fixture v1 ships must assert the digest,
  not the answer — and `tasks.md` T061's longer chain is not decoration.
- **One task, one shape.** Every arm answers one small question with two tools.
  Nothing here speaks to long conversations, many tools, parallel tool calls in
  a single turn, or streaming.
- **Presence is not guaranteed.** `repeat_adaptive.py` measured Anthropic's
  adaptive-thinking mode emitting opaque state on some runs and not others for
  this task. A fixture asserting presence unconditionally would be flaky; the
  assertion that holds is the conditional one.
- **No dollar total.** Tokens are measured from each provider's own usage
  field. Only xAI reports a server-side cost. Converting the other three needs a
  per-provider price table, which is one of the nine capabilities **U-48**
  records as unowned — so this harness reports tokens and declines to invent
  prices.
- **One credential set.** Like [finding 002](../../findings/002-provider-credentials.md),
  the specific keys are one person's. A third party supplies their own.

## Gaps

- The four main arms ran **once each** in the committed run. `repeat_adaptive.py`
  repeats only the Anthropic arm. Per-arm variance for the other three is
  unmeasured.
- `provider_accepted` is inferred from the absence of an API error on the
  following turn rather than from a provider-side confirmation that the state
  was *used*. A provider that silently ignored a valid-looking field would pass
  this check. Distinguishing acceptance from use needs a task whose answer
  depends on the reasoning content, which this scenario is too small to supply.
- `count_vendor_fields.py` counts a whole package where finding 003 counted one
  module. A non-zero count is weaker evidence of good handling than zero was of
  absent handling; the behavioural arms are what establish the field is carried.
