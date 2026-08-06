# Finding 031 — the twelve-arm probe ran, and **two of the four determinations are wrong in the direction that costs tokens rather than correctness**: xAI tolerates a chain with a hole as well as a chain with nothing, OpenAI tolerates both despite the only vendor quote carrying explicit error language, Google is the one provider that rejects a broken chain *by name* — and Anthropic's two 400s are an artifact of the treatment shape, which the negative control is what caught

**Date**: 2026-08-05
**Feature**: 002. Runs the probe designed in
[finding 030](./030-provider-state-chain-derived-not-measured.md) §6 and **not run** there, against
the four determinations carried in [`src/runtime/context.py`](../../../src/runtime/context.py)`::states_for`.
Harness and every artifact: [`../harness/provider-state-chain-conditions/`](../harness/provider-state-chain-conditions/README.md).
**Reports; decides nothing.** No source, requirement or register was edited.
**User Story**: US1, by way of **FR-037**. Bears on **SC-010**, on **U-52** and on **C-21**.
**Owner decision**: **none is minted here.** What this result owes to `U-52`, `C-21` and
`states_for`'s docstring is **quoted, not made**, in
[§8](#8-owed-propagation-quoted-not-made). FR-037 is untouched: the owner declined the candidate text
in finding 030 §7.3 on 2026-08-05 and nothing here reopens it.
**Model spend**: **44,824 input and 3,326 output tokens over the twelve cells**; **66,854 input and
4,783 output** across every live call this pass made, the twelve cells plus two supplementary and two
calibration arms. **The only measured dollar figure is xAI's server-side `cost_in_usd_ticks`:
$0.014082 over three arms.** Anthropic, OpenAI and Google returned **no cost figure at all** and none
is inferred for them — see
[§7](#7-spend-measured-in-tokens-and-in-dollars-only-where-a-provider-supplied-them). Against the
authorised ceiling of **$5.00**.
**Method**: **live provider calls through each vendor's own SDK**, four providers × three conditions,
over the six-turn five-hop dependent chain
[T061's cassettes](../../../tests/conformance/cassettes/README.md) already describe. Every arm's
condition-A baseline ran first and B and C ran only where A returned `OK`. Every request's state
pattern is classified and recorded per turn, which is what makes
[§3](#3-row-b-built-an-interior-hole-on-exactly-one-provider-and-that-changes-what-row-b-establishes)
readable. Credentials were resolved by importing E16's `envroot.py`; only variable names and
twelve-hex SHA-256 fingerprints were recorded.
**Reproduction**: `cd specs/002-spec-aware-agent-runtime/harness/provider-state-chain-conditions && F2A_ENV_ROOT=/path/to/tree F2A_GEMINI_VAR=GEMINI_API_KEY_2 ./run.sh`.
Offline, with no credential and no spend: `python3 selfcheck.py`.
**Numbering note**: `030` was the high-water mark across `specs/*/findings/`, established by listing
the whole tree rather than by reading a number out of the brief, and `031` was free at that moment and
re-checked free immediately before saving. **The namespace choice is contestable and the argument is
recorded rather than hidden** — see
[§11.1](#111-this-finding-arguably-belongs-in-feature-001-and-goes-here-because-that-namespace-is-closed).

---

> ## READ THIS FIRST: **the load-bearing negative in finding 030 §1 is discharged, and it did not come back the way the docstring predicted**
>
> Finding 030 §1 stated the gap in one sentence: *"no request with a state deliberately withheld has
> ever been sent to OpenAI, Google or Anthropic from this repository."* Eight such requests have now
> been sent, four providers × two conditions, each against a full-chain baseline on the same provider,
> model, credential and conversation.
>
> | | **A** full chain | **B** drop-one | **C** drop-all |
> |---|---|---|---|
> | **Anthropic** | `OK` | **400** `thinking.signature: Field required` | **400** same message |
> | **OpenAI** | `OK` | **tolerated**, five hops, answered 149.99 | **tolerated**, five hops, answered 149.99 |
> | **Google** | `OK` | **400** `Function call is missing a thought_signature` | **400** same message |
> | **xAI** | `OK` | **tolerated**, five hops, answered 149.99 | **tolerated**, five hops, answered 149.99 |
>
> **Two errors and two tolerations is not the "three error, Anthropic does not" the docstring predicts,
> and it is not the "all four error" that would mean the instrument broke.** It is finding 030's third
> branch — *"fewer than three error ⇒ the docstring's claim is narrowed"* — and the narrowing is
> sharper than that branch anticipated, because **the two that errored are not the two the docstring
> names**, and one of the two is not rejecting the missing state at all.
>
> **Anthropic's 400 is a schema complaint, not a state rejection, and the negative control is what
> caught it.** A `thinking` block whose `signature` is absent is malformed whatever the field means.
> A supplementary arm that omits **the whole thinking block** — which is
> [finding 003](../../001-discovery-validation/findings/003-runtime-provider-agnosticism.md) result 7's
> actual defect shape — sends a *well-formed* request with the state gone, and Anthropic **tolerated
> it**, completed all five hops and answered correctly. Rule 8's concern is that a broken instrument
> produces the same bit as a real result; here it did, on one provider, and the control is the only
> reason this document does not report Anthropic as a provider that enforces state chaining.
>
> **`states_for`'s remaining error language now has one measured limb out of two.** Google's holds and
> is the only one that does. OpenAI's — *"The API will error if these are not included"* — did not
> reproduce, in either condition, nor with the reasoning items omitted outright.

---

## 1. The twelve cells, with what each request actually carried

Machine-readable in [`results/SUMMARY.json`](../harness/provider-state-chain-conditions/results/SUMMARY.json);
one JSON per arm alongside it. `shape` is this harness's per-request classification of the state
pattern the provider was sent, in turn order.

| arm | verdict | requests sent, by shape | hops | answer | in / out tokens |
|---|---|---|---|---|---|
| **anthropic A** | `OK` | `no-state-yet` · `full`×5 | 4/4 | 149.99 ✓ | 9,851 / 647 |
| **anthropic B** | **`ERRORED` 400** | `no-state-yet` · `full` · **`trailing-gap`** | 1/4 | — | 2,693 / 321 |
| **anthropic C** | **`ERRORED` 400** | `no-state-yet` · **`all-absent`** | 0/4 | — | 1,217 / 213 |
| **openai A** | `OK` | `no-state-yet` · `full`×5 | 4/4 | 149.99 ✓ | 3,586 / 417 |
| **openai B** | **`TOLERATED`** | `no-state-yet` · `full` · **`trailing-gap`×4** | 4/4 | 149.99 ✓ | 3,185 / 254 |
| **openai C** | **`TOLERATED`** | `no-state-yet` · **`all-absent`×5** | 4/4 | 149.99 ✓ | 2,610 / 167 |
| **google A** | `OK` | `no-state-yet` · `full`×5 | 4/4 | 149.99 ✓ | 4,675 / 391 |
| **google B** | **`ERRORED` 400** | `no-state-yet` · `full` · **`trailing-gap`** | 1/4 | — | 1,174 / 221 |
| **google C** | **`ERRORED` 400** | `no-state-yet` · **`all-absent`** | 0/4 | — | 490 / 162 |
| **xai A** | `OK` | `no-state-yet` · `full`×5 | 4/4 | 149.99 ✓ | 5,233 / 180 |
| **xai B** | **`TOLERATED`** | `no-state-yet` · `full` · `trailing-gap` · **`interior-hole`×3** | 4/4 | 149.99 ✓ | 5,191 / 175 |
| **xai C** | **`TOLERATED`** | `no-state-yet` · **`all-absent`×5** | 4/4 | 149.99 ✓ | 4,919 / 178 |

**All four A arms returned `OK`**, so all eight treatment cells are one-variable deltas against a
baseline that worked, which is the whole of what row A is for. The errored arms are short because they
stopped at the rejection; an errored arm's token count is the cost of reaching the 400, not of a
truncated conversation.

## 2. What each provider actually did, with the vendor's own words

### Google — the one limb that holds, and it holds by name

Google is the only provider that rejects a broken chain in language that is *about the state*:

> `Function call is missing a thought_signature in functionCall parts. This is required for tools to
> work correctly, and missing thought_signature may lead to degraded model performance. Additional
> data, function call ``default_api:list_orders`` , position 4.`

That is row B. Row C is the same message naming a different call: `` default_api:lookup_customer ``,
`position 2`.

**The two named calls are exactly the two the treatment emptied, and that is the strongest
confirmation in the probe that the conditions do what they claim.** Row B withholds the state at
`DROP_ORDINAL = 1` — the *second* state emitted, which rode on the turn that called `list_orders` —
and Google names `list_orders`. Row C withholds everything, so the first violation is the *first*
state-bearing turn, which called `lookup_customer` — and Google names `lookup_customer`. The provider
is pointing at the exact parts the harness blanked, in the order the conditions blank them.

`states_for`'s Google reading — *"Gemini 3 validates every step of the current turn and returns 400
when the first `functionCall` part of any step is missing its `thought_signature`"* — is **measured
correct**, on `gemini-3-flash-preview`.

### OpenAI — the only quote with explicit error language, and it did not reproduce

`states_for` carries the sharpest vendor claim in the docstring:

> the function-calling cookbook is blunter — *"The API will error if these are not included."*

**It did not error.** Not with one `encrypted_content` withheld, not with all of them withheld, and —
the supplementary arm in [§4](#4-the-supplementary-arm-what-happens-when-the-whole-carrier-goes) — not
with **the reasoning items omitted outright**, which is the condition the vendor sentence is
grammatically about. All three completed five hops and returned 149.99, under `store=False` with
`include=["reasoning.encrypted_content"]` on `gpt-5-mini`.

**What this narrows and what it leaves alone.** It falsifies *"will error"* as an unconditional claim
on this model and this shape. It says nothing about whether replaying the items is *better*, which is
the claim the cookbook is really making and which this probe cannot reach — see
[§9](#9-what-this-does-not-establish).

**One response-side observation that is not a request-side result.** In row B, OpenAI emitted
`encrypted_content` on turns 1 and 2 and then **stopped**, where in row A it emitted on all six. So
withholding one state changed what came back. That is a real difference and it is recorded, but it is
one arm with no repetition and no controlled comparison, and it is exactly the kind of single
observation this corpus has been burned by treating as a result. It is a hypothesis, not a finding.

### xAI — tolerates the hole as well as the absence

Row B is the arm finding 030 §2 was written to commission, and it is the only arm in this probe where
an **interior hole** was actually constructed and sent — three requests of the six, each carrying
state on turns before and after a turn whose state was empty. xAI accepted all three, chained all five
hops, and answered correctly.

Row C reproduces finding 016's negative control on the same model, `grok-4.5`, and reproduces its
result: `provider_errored: false`.

`states_for`'s xAI reading is an imperative — *"Always pass the full `output` array back verbatim"*,
*"do not parse, edit, or hand-merge multiple blobs"* — and finding 030 was already careful that an
imperative is not an error prediction. **What is now measured is that the imperative has no enforcement
behind it in either condition.**

### Anthropic — errored, and the error is not about the state

Row B and row C both return the same 400:

> `messages.3.content.0.thinking.signature: Field required`

Read as a cell of the table that is *"Anthropic rejects a withheld state"*, which would make Anthropic
the fourth provider to enforce and would sink the negative control. It is not that, and
[§4](#4-the-supplementary-arm-what-happens-when-the-whole-carrier-goes) is why.

## 3. Row B built an **interior hole** on exactly one provider, and that changes what row B establishes

This is the correction this document most wants a reader to carry, and it exists only because the
harness classifies every request rather than only the verdict.

| provider | did an interior hole ever reach the provider? | why not |
|---|---|---|
| **xAI** | **yes**, 3 requests | — |
| **Anthropic** | no | rejected the **trailing-gap** request, one turn before a hole could form |
| **Google** | no | rejected the **trailing-gap** request, one turn before a hole could form |
| **OpenAI** | no | the model stopped emitting state after the withheld turn, so nothing landed *after* the gap |

**Finding 030 §2's table is therefore half-filled, not filled.** Its `drop-one` row asks whether a
provider rejects *"a chain with a hole in the middle"*, and for three of four providers this probe
answers a weaker question — whether it rejects a chain whose most recent state is missing. That is
still a new measurement and still the one an adapter defect produces first, but it is not the interior
hole, and a later document that reads row B as "interior hole, four providers" will be wrong.

**For the provider the question was actually about, it is answered.** xAI was the whole reason row B
existed, and xAI got the interior hole and took it.

## 4. The supplementary arm: what happens when the **whole carrier** goes

Not one of the twelve cells, reported separately throughout, and run because Anthropic's error message
admits two readings the twelve cells cannot separate.

The twelve arms withhold **the opaque field** and leave the block or item it sat on in place, because
that is what a journal-backed runtime produces when `states_for` returns `None` for a turn, and it is
what [`tests/conformance/test_provider_state_roundtrip.py`](../../../tests/conformance/test_provider_state_roundtrip.py)
models. A `thinking` block with no `signature`, though, violates Anthropic's request schema *whatever
the field means*. [Finding 003](../../001-discovery-validation/findings/003-runtime-provider-agnosticism.md)
result 7's actual defect shape is different: an adapter rebuilding the assistant message from role,
content and tool calls drops **the whole block**, and sends a well-formed request with the state gone.

[`supplementary_whole_block.py`](../harness/provider-state-chain-conditions/supplementary_whole_block.py)
sends that request.

| provider | carrier omitted | verdict | hops | answer | in / out |
|---|---|---|---|---|---|
| **Anthropic** | the whole `thinking` block | **`TOLERATED`** | 4/4 | 149.99 ✓ | 7,939 / 545 |
| **OpenAI** | the whole `reasoning` item | **`TOLERATED`** | 4/4 | 149.99 ✓ | 2,610 / 204 |

**Anthropic does not reject a request because the reasoning state is absent. It rejects a request
because a block is malformed.** Those are different failures with the same status code, and the
difference decides whether the negative control held.

**One property of the Anthropic supplementary arm to state rather than gloss.** With prior thinking
blocks gone from the conversation, the model emitted a thinking block on turn 1 only, so the treatment
was applied to one assistant message and turns 2–6 had no carrier to omit. That is still the
finding-003 defect shape reaching the provider and being accepted; it is not six independent
applications of it, and the artifact records `state_turn_indices: [0]` so nobody has to infer that.

## 5. So did the negative control hold?

**Not in the form it was predicted, and it did its job anyway.** Finding 030 §6 set out three branches
and the observed result matches none of them cleanly, which is worth saying plainly rather than
rounding to the nearest one.

| finding 030's branch | observed |
|---|---|
| all four error ⇒ measuring something else, no arm readable | no — two tolerated, and their baselines passed |
| three error and Anthropic does not ⇒ prediction holds | **no** — Anthropic errored and two of the three predicted-to-error did not |
| fewer than three error ⇒ docstring narrowed | **closest**, but it under-describes: the *identity* of the erroring providers is wrong too |

**Rule 8's stated reason is what actually operated here**, and the quote is from
[`.cursor/skills/experiment-design/SKILL.md`](../../../.cursor/skills/experiment-design/SKILL.md), not
from `tools/README.md`:

> every way the instrument itself can break produces that same bit

Anthropic's 400 *is* the instrument breaking — a request the provider will not parse — and it is
indistinguishable from a real rejection at the level of the verdict. It was distinguishable one level
down, and only because the control's prediction failing was treated as a reason to go and look rather
than as a result to report.

**The honest summary is that the control fired.** It was predicted not to error, it errored, and the
follow-up found the artifact. A probe where Anthropic had quietly tolerated the field-level treatment
would have produced a cleaner table and a weaker document.

## 6. What `states_for`'s four determinations look like now

Restating finding 030 §1's table with the measured column filled. **Nothing in this section is an
edit; `src/runtime/context.py` was not touched.**

| determination as written | status now | evidence |
|---|---|---|
| **OpenAI** *"The API will error if these are not included"* | **MEASURED, and it did not** — in all three conditions | `arm-openai-B`, `arm-openai-C`, `supplementary-openai` |
| **Google** returns 400 when a `functionCall` part is missing its `thought_signature` | **MEASURED CORRECT** | `arm-google-B`, `arm-google-C`, error names the part |
| **xAI** *"Always pass the full `output` array back verbatim"* | **MEASURED to carry no enforcement**, in both conditions, including the interior hole finding 030 left open | `arm-xai-B`, `arm-xai-C` |
| **Anthropic** *"degrades quietly on a miss"* | **the *not-erroring* half is MEASURED**, once the malformed-block artifact is removed. **The *degrading* half is untouched and remains unmeasured in both directions** | `supplementary-anthropic`; [§9](#9-what-this-does-not-establish) |

**None of this is a reason to send less, and the asymmetry `states_for` already states is the reason.**
Two providers now measured to tolerate a broken chain is not two providers measured to be undamaged by
one. The cost of sending the whole chain is input tokens; the cost of not sending it is a rejected
request on Google and an unmeasured degradation on the other three. The direction the runtime committed
to is still the conservative one and **[finding 030 §4](./030-provider-state-chain-derived-not-measured.md#4-why-none-of-this-reopens-the-decision)
stands unchanged**.

## 7. Spend, measured in tokens and in dollars only where a provider supplied them

**The refusal to price is inherited, not invented.** Finding 016 declined to convert three of its four
arms to dollars because *"the per-provider cost table is one of the nine capabilities **U-48** records
as having no owner. Inventing four price lists to close a spend line would be exactly the unsourced
number that register exists to prevent."* This finding does not depart from it.

| | arms | provider calls | input tokens | output tokens | provider-reported cost |
|---|---:|---:|---:|---:|---|
| **the twelve cells** | 12 | 58 | **44,824** | **3,326** | **$0.014082**, xAI only |
| supplementary, [§4](#4-the-supplementary-arm-what-happens-when-the-whole-carrier-goes) | 2 | 12 | 10,549 | 749 | none reported |
| calibration, [§11.2](#112-calibration-disclosed-because-it-changed-two-arms) | 2 | 12 | 11,481 | 708 | none reported |
| **every live call this pass made** | **16** | **82** | **66,854** | **4,783** | **$0.014082** |

**Named plainly, as the brief asked: Anthropic, OpenAI and Google supplied no usable cost figure.**
Their SDK responses carry token counts and no price. A null in the cost column of any artifact here
means *the provider reported none*, never zero, and the harness records the distinction rather than
defaulting to `0.0`.

**xAI's three cells, from `usage.cost_in_usd_ticks`:** A $0.0056708 · B $0.0038160 · C $0.0045956.

**Against the projection and the ceiling.** Finding 030 §6 projected **~100,000–150,000 input** and
**~5,000–10,000 output** tokens for the twelve arms. Actual was **44,824 / 3,326** — **under half the
low end of the input projection**. The projection assumed 6-turn arms throughout; four of the twelve
arms terminated at a 400 after two or three turns, which is most of the gap, and the surviving arms
came in nearer 4–5k than the projected 8–11k. **The $5.00 ceiling was never approached**, and the only
dollars anyone can actually name are xAI's one and a half cents.

**Two notes on the ledger file, so its numbers reconcile.**
[`results/budget.json`](../harness/provider-state-chain-conditions/results/budget.json) reads
**55,373 / 4,075 over 18 arms**, and neither figure is the table above. It covers **14 arms, not 16** —
the two calibration arms ran before it existed — and its `arms` field counts **invocations**, so it
reads 18 because four supplementary invocations aborted inside the harness before any provider call
(the defect in [§10](#10-a-defect-in-this-harness-found-by-its-own-failure-and-worth-the-paragraph)).
Token totals are unaffected by the aborted four, which add zero. The table above is the sum over the
committed per-arm artifacts and is the figure to quote.

## 8. Owed propagation, **quoted, not made**

**Nothing in this section was applied.** `research/14-architecture-synthesis.md`,
`specs/002-spec-aware-agent-runtime/findings/030-*.md`, `src/runtime/context.py` and `spec.md` were all
left alone. These are the owner's.

**The formatting escape**, same as finding 030 §7 and finding 029 §7: identifiers inside quoted blocks
are written in code spans and link paths are the ones correct **from the destination file**, because
`identifier-resolution` refuses a register identifier a finding writes as a live token and
`link-target` resolves relative to the document a link sits in. Strip the backticks when pasting.

### 8.1 `U-52` in [`research/14-architecture-synthesis.md`](../../../research/14-architecture-synthesis.md) §5.2 — **the uncertainty is discharged and the row should close**

`U-52` was opened on 2026-08-05 to record that the four determinations were unmeasured and to name the
12-arm probe as the route to converting them. **The probe has run.** Its *Route to resolution* cell
says *"Not run; no spend authorised"*, which is now false, and its body claims *"no request with a
state deliberately withheld has ever been sent to OpenAI, Google or Anthropic"*, which is now false.

Suggested resolution clause, for the owner to place in whatever form §5.2 uses for a discharged row:

> **RESOLVED 2026-08-05 by `[finding 031](../specs/002-spec-aware-agent-runtime/findings/031-provider-state-chain-measured.md)`, and the answer is not the one this row expected.** The 12-arm probe ran: four providers × {full chain, one state dropped, all states dropped}, all four full-chain baselines `OK`. **Two providers reject a broken chain and two do not, and only one rejects it because of the state.** Google 400s in both conditions, naming the missing `thought_signature` and the part position — the one determination measured correct. **OpenAI does not error in either condition, nor with the reasoning items omitted outright**, which falsifies the cookbook's *"The API will error if these are not included"* on `gpt-5-mini` under `store=False`. **xAI tolerates the interior hole as well as the total absence**, which closes the narrow claim `C-21` was holding open. **Anthropic 400s on `thinking.signature: Field required`, and that is a malformed-block rejection rather than a state rejection**: a supplementary arm omitting the whole `thinking` block was tolerated and answered correctly. The request shape the runtime sends is unchanged and should be — being wrong in this direction costs input tokens; being wrong in the other costs a rejected request on Google. **The half this does not discharge is Anthropic's quiet degradation**, which stays unmeasured in both directions and needs a task whose answer depends on the withheld reasoning.

### 8.2 `C-21` in [`research/14-architecture-synthesis.md`](../../../research/14-architecture-synthesis.md) §4 — **the residue that kept it open is now measured, and the row can close fully**

`C-21` was landed *partially resolved*. Its resolution cell states exactly what kept it open:

> The narrower claim it was reaching for — that xAI rejects a chain with a *hole* rather than a chain
> with *nothing* — is untouched by the measurement and remains unmeasured; those are different
> requests and a validator could distinguish them. […] the register row is retained because the
> *narrow* claim still has no measurement behind it.

**It has one now, and the narrow claim fails too.** Suggested clause:

> **FULLY RESOLVED 2026-08-05 by `[finding 031](../specs/002-spec-aware-agent-runtime/findings/031-provider-state-chain-measured.md)`.** The narrow claim was measured and fails: on a live `grok-4.5` six-turn chain, three requests carried an **interior hole** — state present on turns before and after a turn whose `encrypted_content` was empty — and xAI accepted all three, chained all five hops and answered correctly. The drop-all condition reproduced `finding 016`'s negative control on the same model with the same outcome. **xAI's documented imperative has no enforcement behind it in either condition**, so the docstring's original sentence was wrong in both the broad and the narrow reading, and the correction landed on 2026-08-05 stands rather than being an over-correction.

### 8.3 [`src/runtime/context.py`](../../../src/runtime/context.py)`::states_for` — two limbs are now measured and the docstring still calls all four derived

The docstring's paragraph reads *"All four of those readings are vendor documentation and none of them
is measured. See finding 030, which is about exactly that."* That sentence is now wrong in the same way
the sentence it replaced was wrong. Suggested replacement, for the owner:

> **All four readings were vendor documentation when this was written and three of them have since been measured, by the 12-arm probe in `[finding 031](../../specs/002-spec-aware-agent-runtime/findings/031-provider-state-chain-measured.md)`. Google's is correct — it 400s, naming the missing part. OpenAI's error language did not reproduce in any condition, including with the reasoning items omitted outright. xAI's imperative carries no enforcement: it accepts both a chain with a hole and a chain with nothing. Anthropic's `not-erroring` half is measured — it accepts a conversation with the thinking blocks removed — while the `degrades quietly` half remains unmeasured in both directions. **None of that is a reason to send less**, and the asymmetry below is why.**

### 8.4 What is **not** owed

- **No requirement edit.** FR-037 says *never dropped* whatever a vendor does, and a measurement that
  two vendors tolerate dropping does not bear on it. The owner declined finding 030 §7.3 on
  2026-08-05 and this result strengthens that declination rather than reopening it.
- **No conformance-fixture change.** Finding 030 §5's two blindnesses are about cassettes standing in
  for live measurement; this finding supplies the live measurement beside them and removes none of the
  reasons the guard exists.
- **No new register entry.** Everything measured here lands on rows that already exist.

## 9. What this does **not** establish

1. **It does not establish that any tolerated provider was undamaged.** Every tolerated cell answered
   149.99 because the scenario has no answer that depends on the withheld reasoning. Finding 016
   recorded that limit about its own scenario — *"too small to supply one"* — and this probe reuses
   that scenario's six-turn successor rather than fixing it. **Tolerated means accepted, not
   equivalent.**
2. **It does not measure Anthropic degrading quietly**, in either direction, and a green supplementary
   arm is not evidence that it does not. That was stated as a limit before the probe ran and the result
   does not change it.
3. **It does not establish interior-hole behaviour for Anthropic, Google or OpenAI** — see
   [§3](#3-row-b-built-an-interior-hole-on-exactly-one-provider-and-that-changes-what-row-b-establishes).
4. **One arm per cell, no repetition.** Nothing here is a rate. A provider that rejects
   non-deterministically would show as a rejection or a toleration depending on the draw, and this
   probe cannot tell the difference. Finding 016 has the same property and named it.
5. **Four models, not four providers.** Every result is `claude-sonnet-4-5-20250929`,
   `gpt-5-mini`, `gemini-3-flash-preview`, `grok-4.5`. Validation behaviour is a property of an
   endpoint and a model generation, and none of this transfers to a sibling model by assumption.
6. **Two arms were calibrated before the treatment ran** — [§11.2](#112-calibration-disclosed-because-it-changed-two-arms).

## 10. A defect in **this harness**, found by its own failure, and worth the paragraph

`credentials.py` originally imported E16's `envroot.py` by putting E16's directory at the front of
`sys.path`. **E16's directory holds modules named `arm_anthropic`, `arm_openai`, `arm_google`,
`arm_xai` and `summarize` — the same five names this harness uses.** Every subsequent
`import arm_openai` resolved to *E16's* module.

It surfaced only because E16's arm happens not to define a constant this harness's arm does, and the
supplementary run died on an `AttributeError`. **A shadowed module with a compatible surface would have
run E16's two-hop scenario and reported it as this experiment's six-turn one**, and nothing in the
verdict would have looked wrong.

The twelve cells were **not** affected — E16's directory holds no `chain.py`, `conditions.py`,
`loop.py` or `credentials.py`, and the arms import those, not each other — and the committed artifacts
record six turns and five linked hops, which E16's scenario cannot produce. The fix loads the one file
by path via `importlib` and puts no directory on `sys.path` at all.

**The general shape, because this repository will meet it again:** a harness that reuses another
harness's helper by path insertion inherits that harness's entire namespace, and harness directories in
this corpus are deliberately named alike.

## 11. Two disclosures about how this was set up

### 11.1 This finding arguably belongs in feature 001, and goes here because that namespace is closed

[`README.md`](./README.md) gives the borderline rule: *"Ask what the measurement is of. A
measurement of something outside this repository — a provider, a library, a benchmark, a corpus we did
not write — belongs in feature 001."* **This is a measurement of four model providers**, so the rule
points at feature 001. The same document says *"Feature 001 is closed to new findings."*

The rules conflict on exactly this document. It is filed in feature 002 because the closure is
absolute where the borderline rule is a heuristic, because finding 030 — the same subject, the
document that designed this probe — is in feature 002, and because the brief directed the harness
here. **Recorded rather than resolved**; a reader looking for provider measurements in feature 001 will
not find this one.

### 11.2 Calibration, disclosed because it changed two arms

Condition B is unconstructible on a provider that emits state on only one turn: withholding the single
state *is* condition C. Two providers needed a setting change first, both are kept:

| provider | default | change | uncalibrated run |
|---|---|---|---|
| Anthropic | thinking on turn 1 only | `anthropic-beta: interleaved-thinking-2025-05-14` | [`anthropic-A-enabled-thinking-no-beta.json`](../harness/provider-state-chain-conditions/results/calibration/anthropic-A-enabled-thinking-no-beta.json) |
| OpenAI | no `encrypted_content` after turn 1 at low effort | `reasoning.effort = "medium"` | [`openai-A-effort-low.json`](../harness/provider-state-chain-conditions/results/calibration/openai-A-effort-low.json) |

**Both were decided against condition A and before any B or C arm ran**, which is what makes them
calibration rather than post-hoc adjustment. Neither changes the treatment; both change only whether
there is more than one state to withhold. Without them, Anthropic's and OpenAI's B cells would read
`UNTESTABLE-ONE-STATE-ONLY` — a verdict the harness carries precisely so that case cannot be silently
reported as a toleration.

## 12. Errors in the brief that commissioned this pass

Recorded because the brief asked for them, in descending order of how much they would have cost.

1. **The hold on `research/14-architecture-synthesis.md` and finding 030 had already cleared.** The
   brief describes a concurrent pass *"landing two register entries into the first and annotating the
   second right now"*. That pass had finished: `6e48729`, `3cbd006`, `1cf518f`, `e4b471b` and `fd2dd6c`
   are all committed on `main`, and `git status` showed a clean tree apart from this harness. **I found
   no uncommitted work anywhere in the tree that I did not create**, and I edited neither file
   regardless. Worth naming because a stale hold is a hazard in the useful direction only once.
2. **The predicted control outcome was wrong, and the brief's own safeguard is what caught it.** The
   brief says Anthropic *"is predicted **not** to error where the other three do"* and that *"if all
   four error"* the probe is measuring something else. **Two errored, Anthropic among them, and the
   other three did not.** The brief's instruction — say so rather than reporting a clean sweep —
   generalised correctly to a case it did not anticipate.
3. **The projection over-estimated input tokens by more than 2×.** *"~100–150k input"* against **44,824
   measured**. The estimate assumed six turns per arm; arms that 400 on turn two or three cost a
   fraction of that, and rows B and C error by design, so a third of the twelve arms were always going
   to be short. Not a defect in the brief so much as an unavoidable property of estimating an
   experiment whose point is that some arms stop early.
4. **The Rule 8 citation was right this time.** The brief flags *"I have mis-cited that twice"* and
   points at [`.cursor/skills/experiment-design/SKILL.md`](../../../.cursor/skills/experiment-design/SKILL.md)
   rather than `tools/README.md`. Checked against the source: the numbered rules are in the skill, Rule
   8 is *"an experiment whose positive result is a failure signal needs a negative control"*, and the
   quoted reason is *"every way the instrument itself can break produces that same bit."* The
   correction held.
5. **"Twelve arms" is twelve conversations, roughly seventy calls.** Finding 030 §6 already corrected
   this arithmetic for the design and the brief inherits the corrected form, so this is a note rather
   than an error: the measured run made **58** provider calls across the twelve cells against the ~72
   projected, short for the same reason the token count came in low — four arms stopped at a 400.
