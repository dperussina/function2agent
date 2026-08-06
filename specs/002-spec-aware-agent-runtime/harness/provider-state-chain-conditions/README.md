# E18 — what four providers actually do when the opaque-state chain is broken

Produces [finding 031](../../findings/031-provider-state-chain-measured.md).
Runs the probe designed in [finding 030](../../findings/030-provider-state-chain-derived-not-measured.md)
§6 and not run there.

**What it measures.** Whether each of SC-010's four providers **rejects** a
request whose per-turn opaque reasoning state has been withheld, under two
distinct withholding conditions, against a full-chain baseline on the same
provider, model, credential and conversation.

**Why it exists.** [`src/runtime/context.py`](../../../../src/runtime/context.py)`::states_for`
sends every kept turn's opaque state on the strength of four vendor-documentation
readings, **none of which had been measured**. Finding 030 §1 records the
load-bearing negative in its own words:

> **no request with a state deliberately withheld has ever been sent to OpenAI,
> Google or Anthropic from this repository.**

One had been sent to xAI — [finding 016](../../../001-discovery-validation/findings/016-provider-sdk-roundtrip.md)'s
negative control — and it recorded `provider_errored: false`, which is the
contradiction registered as **C-21**. This harness sends the missing requests.

## Running it

```bash
export F2A_ENV_ROOT=/path/to/tree        # required, no default
export F2A_GEMINI_VAR=GEMINI_API_KEY_2   # required on some trees; see finding 002
./run.sh [output-dir]                    # defaults to results/
```

`F2A_PYTHON` selects the interpreter. The committed results came from a
dedicated Python 3.12.11 virtualenv holding only the four vendor SDKs, built
separately from `/tmp/f2a-probe-runtime` for the reason E16's README gives —
installing vendor SDKs must not disturb the pinned environment findings 003 and
006 depend on.

SDK and model versions used, from the committed artifacts:

| provider | SDK | model | opaque field |
|---|---|---|---|
| Anthropic | `anthropic` 0.120.2 | `claude-sonnet-4-5-20250929` | `thinking.signature` |
| OpenAI | `openai` 2.53.0 | `gpt-5-mini` | `reasoning.encrypted_content` |
| Google | `google-genai` 2.16.0 | `gemini-3-flash-preview` | `Part.thought_signature` |
| xAI | `xai-sdk` 1.17.0 | `grok-4.5` | `message.encrypted_content` |

`grok-4.5` is the model finding 016's negative control used, which is what makes
row C a reproduction rather than a similar experiment.

**Credentials are read and never written**, resolved by
[`credentials.py`](./credentials.py), which **imports** E16's
[`envroot.py`](../../../001-discovery-validation/harness/provider-sdk-roundtrip/envroot.py)
rather than copying it. Every artifact records the variable **name** and a
twelve-hex SHA-256 fingerprint. No value is printed, logged, returned or
written, and no absolute path into anybody's filesystem appears in any committed
file here.

## The scenario

One scenario for all twelve arms: the **six-turn, five-hop dependent chain**
that [T061's cassettes](../../../../tests/conformance/cassettes/README.md)
already describe, so the live result is comparable with the offline fixture
rather than being a second unrelated shape. [`chain.py`](./chain.py) holds it.

```
lookup_customer("Dana Whitfield") -> CUS-4417
list_orders("CUS-4417")           -> ORD-7731
get_order_lines("ORD-7731")       -> LN-22
get_line_price("LN-22")           -> 139.99
apply_tax(139.99)                 -> 149.99
```

Each hop's argument appears nowhere in the prompt and is derivable only from the
previous hop's return, and every tool errors on an id it was not given.
`chain.ToolLog.hops_linked()` asserts the linkage from the recorded call
arguments; it does not infer chaining from the final answer.

## The three conditions, and why B and C are not the same request

[`conditions.py`](./conditions.py) holds all three and the **persistence
boundary** they act at. Every assistant turn is serialised to JSON without its
opaque field and rebuilt from that JSON, which is what a journal-backed runtime
does — the treatment is *what gets written back*, not a mutation of a live SDK
object.

| condition | treatment | what it models |
|---|---|---|
| **A** — full chain | every turn's state reinjected | the control. Not a sanity check: without it a 400 in B is attributable to nothing |
| **B** — drop-one | exactly the state at `DROP_ORDINAL = 1` withheld, all others present | a chain with a **hole**. Internally inconsistent, which is the thing a validator is for |
| **C** — drop-all | no state reinjected on any turn | finding 016's negative control, reproduced on four providers instead of one |

`shape_of` classifies **every request** as `no-state-yet`, `full`,
`trailing-gap`, `interior-hole` or `all-absent`, and the classification is
recorded per turn. That is what lets a B arm prove it actually built an interior
hole rather than merely a trailing gap — a distinction the verdict alone would
hide, and the reason `arm-xai-B.json` is readable at all.

## Calibration, disclosed because it changed two arms

Condition B is unconstructible on a provider that emits state on only one turn:
withholding the single state *is* condition C. Two providers needed a setting
change before B meant anything, and both are recorded under
[`results/calibration/`](./results/calibration/) with the uncalibrated run kept:

| provider | default behaviour | change | file |
|---|---|---|---|
| Anthropic | thinking on turn 1 only | `anthropic-beta: interleaved-thinking-2025-05-14` | [`anthropic-A-enabled-thinking-no-beta.json`](./results/calibration/anthropic-A-enabled-thinking-no-beta.json) |
| OpenAI | no `encrypted_content` after turn 1 at low effort | `reasoning.effort = "medium"` | [`openai-A-effort-low.json`](./results/calibration/openai-A-effort-low.json) |

**Both changes were made against condition A and before any B or C arm ran**,
which is what keeps them calibration rather than post-hoc adjustment. Neither
changes what the treatment does; both change only whether there is more than one
state to withhold.

## Ordering, so a broken instrument cannot be read as a result

[`run.sh`](./run.sh) runs **all four A arms first** and runs B and C for a
provider **only if that provider's A arm returned `OK`**. An arm whose baseline
failed is recorded as unrun rather than as a tolerated or errored cell, because
Rule 8's concern — *"every way the instrument itself can break produces that same
bit"* — applies to the baseline as much as to the treatment.

## Verdicts

| verdict | meaning |
|---|---|
| `OK` | condition A: the full chain completed and answered correctly |
| `TOLERATED` | the treatment was applied and the provider did **not** reject the request |
| `ERRORED` | the provider rejected the request. `error_status` and the vendor's own message are recorded verbatim |
| `UNTESTABLE-NO-STATE` | the provider emitted no opaque state, so nothing could be withheld |
| `UNTESTABLE-ONE-STATE-ONLY` | condition B only: one state emitted, so B collapses into C |
| `UNTESTABLE-NOT-APPLIED` | the run ended before the treatment reached a request |

**`TOLERATED` means the provider accepted the request. It does not mean the
provider was undamaged** — see the limit below.

## The supplementary arm, which is not one of the twelve cells

[`supplementary_whole_block.py`](./supplementary_whole_block.py) omits the
**whole carrier** — Anthropic's `thinking` block, OpenAI's `reasoning` item —
rather than the opaque field on it. It exists because Anthropic's twelve-cell
error message is `thinking.signature: Field required`, which is a **schema**
complaint that a *malformed block* would produce whatever the field means, and
the twelve cells cannot separate that from a state-integrity rejection. Its two
results are in [`results/`](./results/) under `supplementary-*` and are reported
separately throughout. Reading them as cells of the table would be wrong.

## Spend

Denominated in tokens, and the refusal is inherited rather than invented.
Finding 016 declined to convert three of its four arms to dollars because *"the
per-provider cost table is one of the nine capabilities **U-48** records as
having no owner"*, and this harness does not depart from it.

[`conditions.py`](./conditions.py) keeps a file-backed ledger across arms
(`F2A_E18_LEDGER`) and refuses to start an arm once a cumulative ceiling is
passed, because rows B and C error by design and a retry loop on a 400 is the
failure mode that spends a budget without producing a reading. **`max_retries=0`
on every client**, for the same reason.

Its `arms` counter counts **invocations, not readable arms** — it reads 18 for
14 arms because four supplementary invocations aborted in the harness before any
call and are counted. The token totals are unaffected and are the figures the
finding reports.

## The result, in one table

Full reading in [finding 031](../../findings/031-provider-state-chain-measured.md);
machine-readable in [`results/SUMMARY.json`](./results/SUMMARY.json).

| | **A** full chain | **B** drop-one | **C** drop-all |
|---|---|---|---|
| **Anthropic** | `OK` | **`ERRORED` 400** `thinking.signature: Field required` | **`ERRORED` 400** same message |
| **OpenAI** | `OK` | `TOLERATED`, answered 149.99 | `TOLERATED`, answered 149.99 |
| **Google** | `OK` | **`ERRORED` 400** `missing a thought_signature` | **`ERRORED` 400** same message |
| **xAI** | `OK` | `TOLERATED`, answered 149.99 | `TOLERATED`, answered 149.99 |

All four A arms returned `OK`, so all eight treatment cells are readable.

**Anthropic's two errors are an artifact of the treatment shape, not a
rejection of the missing state**, and the supplementary arm is what shows it:
with the whole `thinking` block omitted the same model on the same chain
returned `TOLERATED` and answered correctly. A `thinking` block with no
`signature` violates the request schema whatever the field means.

## What this cannot do, stated so nobody reads it as more

**It measures a provider *not erroring*. It does not measure a provider *not
degrading*.** Every tolerated cell completed all five hops and returned 149.99,
and that is not evidence the withheld reasoning was unnecessary: the scenario has
no answer that depends on it. Finding 016 recorded the same limit about its own
scenario — *"too small to supply one"* — and this harness reuses that scenario's
successor rather than fixing the limit. A green Anthropic supplementary arm is
**not** evidence about quiet degradation, in either direction.

## Offline self-check

```bash
python3 selfcheck.py
```

Drives every condition against a scripted provider and asserts that the
treatment does what it claims — that A withholds nothing, that B leaves an
interior hole with exactly one state missing, that C leaves none, and that each
untestable verdict fires on the shape that should produce it. It calls no
provider and needs no credential. `run.sh` runs it first and stops if it fails.
