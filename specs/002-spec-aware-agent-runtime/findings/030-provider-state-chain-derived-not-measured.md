# Finding 030 — the per-turn opaque-state chain landed on **four determinations none of which is measured**, and the brief's framing of that gap is too generous in one place and too harsh in another: the sharp claim is not merely unrun, because the one live arm in this corpus that comes near it **contradicts the xAI limb**; and finding 016 is no evidence about chain length for a sharper reason than the one alleged — its arms have no persistence boundary at all, so nothing was ever at risk of being dropped

**Date**: 2026-08-05
**Feature**: 002. Audits the evidential basis of the four per-provider determinations that
`c25b85b` — *"Carry every turn's opaque provider state, not only the newest"* — rests on, as they
stand in [`src/runtime/context.py`](../../../src/runtime/context.py)`::states_for` and
[`src/runtime/providers/state.py`](../../../src/runtime/providers/state.py)`::reinject` in the working
tree. Also records the two defects that commit closed and a second blindness in the conformance
fixture. **Reports; decides nothing**, except one source-comment correction disclosed in
[§8](#8-the-one-edit-this-pass-did-make-and-why-it-is-not-a-register-edit).
**User Story**: US1, by way of **FR-037**. Bears on **SC-010** and on **T164**.
**Owner decision**: **none is minted here and the register was not edited.** Two register entries and
one requirement question are **quoted, not made**, in
[§7](#7-owed-register-entries-and-one-requirement-question-quoted-not-made). Where an unminted
`U-` or `C-` number is written down it sits inside a code span, on
[finding 027](./027-lifecycle-edge-set-divergence.md)'s rule — a number written as a live token before
the register carries the entry is a hard `identifier-resolution` error, and
[finding 026](./026-pivot-root-check-measured.md) records that a number copied into a document goes
stale in the direction that tells the next author to reuse a taken one.
**Model spend**: **$0.0000.** No model was called, no credential was read, and **no spend was
authorised for the probe designed in [§6](#6-the-probe-that-would-convert-this-designed-and-not-run)**.
Everything below is source reading, artifact reading and `git`.
**Method**: **artifact reading against committed evidence, not summary.** Every claim about finding
016 is checked against that finding's own committed arm modules and result JSON rather than against
its prose, because the question here is *what its arms did*, and a finding's prose is a claim about
its arms rather than a record of them. Both `git log -S` attributions were re-derived. The one
behavioural reading — that the byte-fidelity fixture runs against synthetic payloads — is taken from
the guard that enforces it and from the fixture arm that exercises the guard.
**Reproduction**: every command is given inline. No harness was built and none is committed; this
finding adds no runnable artifact, which is itself the result.
**Numbering note**: `029` was the high-water mark across `specs/*/findings/`, established by listing
the whole tree rather than by reading a number out of a document or out of the brief that
commissioned this pass, and `030` was free at that moment and re-checked free immediately before
saving.

---

> ## READ THIS FIRST: **all four per-provider determinations rest on vendor documentation and none on measurement** — and one of them is contradicted by the only live arm in this corpus that bears on it
>
> [`states_for`](../../../src/runtime/context.py)'s docstring carries the per-provider evidence with
> quotes and it is not restated here. What is stated here is the **status** of that evidence, which
> the docstring does not carry:
>
> | determination | basis | measured? |
> |---|---|---|
> | **All four vendors want every assistant turn's opaque state in the current turn** | vendor documentation, four quotes | **No** |
> | **OpenAI errors on a miss** | vendor documentation, and the quote carries **explicit error language** — *"The API will error if these are not included"* | **No** |
> | **Google 400s on a miss** | vendor documentation, and the quote carries **an explicit status code** | **No** |
> | **xAI errors on a miss** | vendor documentation — but the quote is an **imperative**, *"always pass the full `output` array back verbatim"*, which says nothing about what happens if you do not | **No — and see below** |
> | **Anthropic degrades quietly on a miss** | vendor documentation, plus the two-way correction to the old premise | **No, in either direction** |
>
> **The sentence that does not survive.** `states_for`'s docstring says *"Only Anthropic degrades
> quietly on a miss; the other three fail the request."* **The xAI limb of that is contradicted by a
> live measurement already committed in this repository**, and the contradiction is inside the
> sentence's scope because the sentence attaches no condition to *"a miss"*.
> [Finding 016](../../001-discovery-validation/findings/016-provider-sdk-roundtrip.md)'s negative
> control drove `grok-4.5` through `xai-sdk` 1.17.0 with `use_encrypted_content=True`, blanked
> `encrypted_content` on **every** assistant message in the conversation before each subsequent
> sample, and recorded
> [`provider_errored: false`](../../001-discovery-validation/harness/provider-sdk-roundtrip/results/negative-control.json).
> See [§2](#2-the-xai-limb-is-not-unmeasured--it-is-contradicted-and-the-condition-matters).
>
> **What that does and does not do to the decision:
> [nothing, and this finding is not an argument for reverting `c25b85b`](#4-why-none-of-this-reopens-the-decision).**
> FR-037 says *never dropped* whatever any provider does; the **mis-attachment** defect is independent
> of every per-provider question; two of the four limbs carry explicit error language; and the error
> direction is conservative in exactly the shape
> [`plan.md`](../plan.md)'s managed-container verdict uses.

> ## AND TWO CORRECTIONS TO THE BRIEF THAT COMMISSIONED THIS PASS, BOTH OF WHICH MAKE ITS ARGUMENT STRONGER
>
> **1. Finding 016's arms did not rely on the SDKs accumulating the conversation, and three of the
> four SDKs do not.** The brief's conclusion — *every arm carried every state by construction* — is
> **right**. Its mechanism is wrong, and the true mechanism is a sharper version of the same point:
> `anthropic.messages.create(messages=…)`, `openai.responses.create(input=…)` and `google-genai`'s
> `generate_content(contents=…)` are **stateless with respect to conversation** and take the whole
> history from the caller on every call. The accumulation is in each **arm module's own local list**,
> which appends the full dumped response — opaque field intact — and never removes anything. So
> **finding 016's harness has no persistence boundary at all**: there is no strip, no rebuild, no
> journal. The state was never at risk because it was never taken out of the object it arrived in.
> That is the *same* by-reference blindness `_persisted` was later written to remove from the
> conformance fixture — see [§5](#5-the-conformance-fixture-was-blind-twice-in-the-same-place-one-level-apart).
> [§3](#3-what-finding-016-is-and-is-not-evidence-for-checked-against-its-arms-and-not-its-prose).
>
> **2. Rule 8 is not recorded in [`tools/README.md`](../../../tools/README.md).** That file contains
> **no `Rule N` text at any site** — `rg 'Rule \d' tools/README.md` returns nothing. Rule 8 is a rule
> of the [`experiment-design`](../../../.cursor/skills/experiment-design/SKILL.md) skill, and its
> heading there reads, verbatim: **"Rule 8: an experiment whose positive result is a failure signal
> needs a negative control"**. `tools/README.md` cites *negative controls* in two places and neither
> is this rule. Cited correctly throughout below.

---

## 1. What is measured and what is derived, in one table

The rule this table applies is the corpus's own, and the closest precedent is
[`plan.md`](../plan.md)'s managed-container verdict — a load-bearing conclusion resting on one
derived, unmeasured claim, labelled as such in its own text: *"derived from vendor documentation,
which is the weakest basis finding 024 carries"*, followed by an explicit statement of what the
derivation does **not** settle and an owner ruling that the error direction is conservative. This
finding follows that precedent and does not improve on it.

| proposition | status | evidence |
|---|---|---|
| The four drivers carry **every kept turn's** state into the next request byte-identically | **MEASURED**, offline | [`tests/conformance/test_provider_state_roundtrip.py`](../../../tests/conformance/test_provider_state_roundtrip.py), six-turn chain, four providers |
| …but against **payloads this repository wrote** | — | every cassette is `derived-shape-synthetic-payload`; `require_recorded()` raises for **all six**, asserted by `test_no_cassette_may_stand_in_for_a_live_measurement` |
| Each vendor SDK's response→request conversion preserves the field byte-identically | **MEASURED LIVE**, 4/4 | finding 016 results 3 and 5, SHA-256 on receipt against SHA-256 in request shape |
| A provider **accepts** a request carrying the full chain | **MEASURED LIVE**, 4/4 | finding 016 result 4 — under that finding's own caveat *"acceptance is not use"* |
| Dropping the field is **invisible in the answer** at two hops | **MEASURED LIVE** | finding 016 result 7: the stripped xAI chain *"still chained and still answered 149.99"* |
| All four vendors **want** the whole chain | **DERIVED** — vendor documentation | `states_for`'s docstring |
| OpenAI **errors** on a miss | **DERIVED** — explicit error language in the vendor doc | `states_for`'s docstring |
| Google **400s** on a miss | **DERIVED** — explicit status code in the vendor doc | `states_for`'s docstring |
| xAI **errors** on a miss | **DERIVED from an imperative**, and **CONTRADICTED** for the drop-all condition | [§2](#2-the-xai-limb-is-not-unmeasured--it-is-contradicted-and-the-condition-matters) |
| Anthropic **degrades quietly** on a miss | **DERIVED**, and never observed in either direction | `states_for`'s docstring |

**The load-bearing negative, stated plainly: no request with a state deliberately withheld has ever
been sent to OpenAI, Google or Anthropic from this repository.** One has been sent to xAI, once, in a
different condition from the one the prediction is about, and it did not error.

## 2. The xAI limb is not unmeasured — it is **contradicted**, and the condition matters

[`negative_control.py`](../../001-discovery-validation/harness/provider-sdk-roundtrip/negative_control.py)
is committed, and the mutation is at its own comment marked `THE MUTATION`:

```python
# THE MUTATION. Strip the opaque field off every assistant message
# now in the conversation, which is what an adapter that rebuilds
# the message from role/content/tool_calls does by omission.
for m in conv.proto.messages:
    if getattr(m, "encrypted_content", ""):
        m.encrypted_content = ""
```

The strip runs **after** the response is appended and **before** the next `conv.sample()`, so every
subsequent request went out with the prior assistant turns' state removed. The committed artifact:

```json
{
  "control": "drop-opaque-field-on-reinjection",
  "provider": "xai",
  "model": "grok-4.5",
  "digests_in": ["a5e95e4f…", "e7b2c8ec…"],
  "digests_out": [],
  "detector_fired": true,
  "chained_without_opaque_state": true,
  "answer_correct_without_opaque_state": true,
  "provider_errored": false,
  "error": null
}
```

Two responses carried the field (`digests_in` has two entries) and `chained_without_opaque_state` is
`true`, so at least one request was sent whose prior assistant turn had been stripped, and the
provider did not reject it. The control's own `except` branch — which exists precisely to record *"the
provider rejected the mutated conversation"* — did not fire.

### Why this falsifies the sentence as written and not the narrower claim underneath it

**Two conditions, and only one of them has been run.**

| condition | description | xAI | the other three |
|---|---|---|---|
| **drop-all** | no assistant turn carries state | **measured, no error** | never run |
| **drop-one** | a chain with a hole in the middle | never run | never run |

These are not the same request and a validator could reasonably distinguish them: a conversation
carrying **no** encrypted content reads as an ordinary unencrypted conversation, whereas a chain with
a hole is internally inconsistent, and inconsistency is the thing a validator is for. So the honest
position is:

- **`states_for`'s sentence *"the other three fail the request"* is wrong as written**, because it
  attaches no condition and the measured case falls inside it.
- **The narrower prediction — xAI rejects a chain with a hole — survives, unmeasured.**
- **This is exactly what a negative control is for, and finding 016 already built one.** Rule 8's
  concern is that *"every way the instrument itself can break produces that same bit"*; here the
  instrument did not break and the bit did not appear, which is the informative case and is why the
  artifact is worth this much attention four days later.

## 3. What finding 016 is and is not evidence for, checked against its arms and not its prose

**Finding 016 drove real providers with real credentials and its round-trip results are sound.** What
it cannot speak to is **how many** states a request needs, and the reason is structural rather than a
matter of scope.

`arm_anthropic.py`, lines 101 and 129:

```python
messages: list[dict] = [{"role": "user", "content": scenario.QUESTION}]
...
    messages.append({"role": "assistant", "content": wire})
```

`arm_openai.py`, lines 77 and 105:

```python
conversation: list = [{"role": "user", "content": scenario.QUESTION}]
...
    # Every output item goes back verbatim, reasoning items included.
    conversation.extend(wire)
```

`arm_google.py`, line 102: `contents.append(cand.content)`.

**Three observations, in the order they bind.**

1. **The SDK is not the accumulator on three of the four arms.** All three calls above hand the whole
   conversation to a stateless create-call. Only xAI's `chat` object holds history internally, and
   even there the arm appends the response proto itself. So the brief's *"the vendor SDKs accumulate
   the conversation internally"* is false for three of four.
2. **The arms have no persistence boundary, which is the stronger version of the same point.**
   Nothing strips the opaque field, nothing serialises the turn, nothing rebuilds a request from
   stored bodies. The field is never separated from the message it arrived on, so a code path that
   *lost* one has no opportunity to exist. Every arm carried every state **by construction**, exactly
   as the brief says, but for this reason rather than the one given.
3. **That is not a defect in finding 016.** Its question was *does the SDK's own response→request
   conversion preserve the bytes*, and for that question holding the object is correct. It becomes a
   limitation only when the finding is read as evidence about chain length, which nothing in finding
   016 claims and which this document is recording so nothing starts to.

**Finding 016's own "What this does not establish" section already anticipated the shape without
naming it**: *"Two hops, one task, one shape. Nothing here speaks to long conversations…"* and
*"Acceptance is not use. `provider_accepted` is inferred from the next turn not erroring."* Both
apply directly and neither was written with this question in view.

## 4. Why none of this reopens the decision

Recorded prominently because a finding whose subject is *the evidence is thinner than it reads* is
one sentence away from being cited as an argument to revert.

1. **FR-037 does not depend on any of it.** *"Provider-opaque reasoning state MUST be a first-class
   value on every turn, round-tripped verbatim, **never dropped** and never merged across providers"*
   ([`spec.md`](../spec.md):1677–1680). *Never dropped* is a requirement on this runtime, not a
   prediction about a vendor. The pre-`c25b85b` behaviour dropped states, and it violated FR-037
   whatever any provider would have done about it.
2. **The mis-attachment defect is orthogonal to every per-provider question.** Writing one turn's
   signed value onto a later turn's `tool_use` block is wrong on a provider that errors, on a
   provider that degrades quietly, and on a provider that ignores the field entirely.
3. **Two of the four limbs carry explicit error language.** OpenAI's *"The API will error"* and
   Google's 400 are not inferences from imperatives. On those two the derived claim is as strong as a
   documentation-derived claim gets.
4. **The error direction is conservative, and this is the precedent's own test.** Being wrong about
   *they all need the whole chain* costs input tokens. Being wrong about *only the newest is needed*
   costs a rejected request on two documented providers and, on Anthropic, a silently degraded turn
   that finding 016 result 7 measured to be **undetectable from the answer**. `plan.md`'s owner ruling
   on the managed-container verdict turns on exactly this: *"the error direction here is
   conservative — a wrong derivation **excludes** a surface the product could have served, rather than
   promising one it cannot."* Same shape, same direction.

**And being wrong about Anthropic specifically is worse rather than safer.** It is the only one of the
four predicted to fail *quietly*, so it is the only one where the derived claim being wrong produces
no signal at all. A wrong prediction about OpenAI or Google announces itself the first time a session
runs. A wrong prediction about Anthropic never announces itself.

## 5. The conformance fixture was blind **twice, in the same place, one level apart**

This is worth recording as a pattern rather than as an incident: **a fixture repaired once for this
exact class of defect was still blind to the same class.**

| # | The blindness | Found by | Fix |
|---|---|---|---|
| **1** | The parsed assistant turn was appended **by reference**, so the opaque field was still sitting in the dict the driver had just read it out of. Re-injection was writing a value that was already there | a removal proof reporting `UNPROVEN` with `reinject`'s write disabled | `_persisted` — delete the declared opaque leaves, then round-trip through JSON |
| **2** | `_persisted` stripped the field **once, when the turn was first appended**, and the same `WireTurn` objects were reused for every later request — so `reinject`'s in-place write on turn N survived into turn N+1 | the pass that changed `states_for` | `_rebuilt` — rebuild every request from persisted bodies |

**What the second blindness reported.** A runtime carrying **exactly one state per request** produced
a fixture reporting **full accumulation**, because the earlier states had been left behind in the
dicts by the previous turn's write. The fixture could not tell the defective runtime from the correct
one, on the single property it exists to assert.

`_rebuilt`'s own docstring names it as a recurrence rather than a new fault — *"That is the
by-reference blindness `_persisted` was written to remove, reappearing one level up"* — and gives the
reason the rebuild is the right model: *"A journal-backed runtime does not hold a mutable
conversation… a conversation that only survives in process memory is one a resumed session does not
have."*

**The transferable part.** Both defects are the same shape: **the fixture shared mutable state with
the thing under test**, so the thing under test could satisfy an assertion using state the fixture had
handed it. Removing the sharing at one level left it at the next. The general form is that *aliasing
is not removed by a deep copy at one boundary if the copied object is then reused across iterations* —
and the only reliable check is the one `_rebuilt` implements, which is to reconstruct the input from
its persisted form on every iteration rather than to sanitise it once.

**This makes at least eight instruments in this corpus found silent on exactly what they claimed** —
[`test_provider_state_roundtrip.py`](../../../tests/conformance/test_provider_state_roundtrip.py)'s
own `_persisted` docstring counts itself as *"an eighth instrument silent on exactly what it
claimed"*, and this is the same instrument counting itself again one level up.

## 6. The probe that would convert this, designed and **not run**

**It was not run. No spend was authorised for it. Nothing in this section was executed and no artifact
from it exists.**

### Construction

Four providers × three conditions, over the six-turn chain of five dependent hops that
[T061's cassettes](../../../tests/conformance/cassettes/README.md) already describe — the same shape,
so the live result is directly comparable with the offline fixture rather than being a second
unrelated scenario.

| arm | condition | prediction |
|---|---|---|
| **A1–A4** | **full chain** — every assistant turn's state present | all four succeed |
| **B1–B4** | **drop-one** — one intermediate turn's state withheld, the rest present | OpenAI errors · Google 400s · xAI errors · **Anthropic succeeds** |
| **C1–C4** | **drop-all** — no assistant turn carries state | reconciles [§2](#2-the-xai-limb-is-not-unmeasured--it-is-contradicted-and-the-condition-matters) against the other three in one harness |

**The brief proposed the 8-arm version (A and B only), and that version is sound but leaves the one
contradiction this finding found unresolved.** Row C is what separates *xAI tolerates a hole* from
*xAI tolerates absence but not a hole*, which is the whole of why the derived claim is in doubt. Row C
also asks the same question of the other three, which finding 016 never did on any of them.

**A correction to the brief's arithmetic, in its own favour.** *"8 calls"* is 8 **arms**, not 8 calls:
each arm is a conversation of roughly six model calls, so the 8-arm version is ~48 calls and the
12-arm version is ~72.

### Anthropic is a genuine negative control, not a fourth repetition

Rule 8 of [`experiment-design`](../../../.cursor/skills/experiment-design/SKILL.md) — **"an experiment
whose positive result is a failure signal needs a negative control"** — governs rows B and C directly,
because for three of the four arms the positive result *is* an error. Rule 8's stated reason applies
without modification: *"every way the instrument itself can break produces that same bit"* — a
malformed request, a stale credential, a model that rejects the request shape, a tool schema the
provider will not accept. Each is indistinguishable from success and each would be scored as success.

**Anthropic is the control because it is predicted to behave in the opposite direction.** The
prediction is that it does **not** error where the other three do, so:

- **all four error** ⇒ the probe is measuring something other than the withheld state, and no arm is
  readable;
- **three error and Anthropic does not** ⇒ the prediction holds and the direction is attributable;
- **fewer than three error** ⇒ the docstring's claim is narrowed, in the direction [§2](#2-the-xai-limb-is-not-unmeasured--it-is-contradicted-and-the-condition-matters)
  already found evidence for.

**Row A is the second control and it is not optional.** Without a full-chain arm on the same provider,
same model, same credential and same conversation, a 400 in row B is attributable to nothing. Row A
is what makes rows B and C one-variable deltas.

**One thing the probe cannot do, stated so nobody expects it to.** It cannot measure Anthropic
*degrading quietly*, only Anthropic *not erroring*. Those are different claims and the second does not
entail the first. Separating them needs a task whose answer depends on the withheld reasoning, and
finding 016 already recorded that its scenario is *"too small to supply one"*. A probe of this shape
leaves the quiet-degradation half exactly where it is.

### Cost, and the one dollar figure that is available

**Denominated in tokens, deliberately.** Finding 016 refused to convert three of its four arms to
dollars because *"the per-provider cost table is one of the nine capabilities **U-48** records as
having no owner. Inventing four price lists to close a spend line would be exactly the unsourced number
that register exists to prevent."* That refusal governs here and this finding does not depart from it.

**Basis, measured**: finding 016's four arms totalled **7,616 input and 823 output tokens** over
3-turn chains with two tools
([`SUMMARY.json`](../../001-discovery-validation/harness/provider-sdk-roundtrip/results/SUMMARY.json)),
averaging ~1,900 input tokens per arm.

**Estimate, derived**: the proposed arm is a 6-turn chain with five tool schemas, and input grows
faster than turn count because each turn resends the whole conversation. At 4–6× finding 016's per-arm
input, that is **~8,000–11,000 input tokens per arm**, so:

| version | arms | input tokens | output tokens |
|---|---:|---:|---:|
| 8-arm (A + B) | 8 | ~65,000–90,000 | ~3,000–6,000 |
| **12-arm (A + B + C)** | 12 | **~100,000–150,000** | **~5,000–10,000** |

**The one dollar figure.** Only xAI reports a server-side cost (`usage.cost_in_usd_ticks`). Finding 016
measured **$0.001860** for its 3-turn xAI arm; three 6-turn xAI arms are therefore on the order of
**$0.01–0.03**. **No figure is offered for the other three and none should be inferred.**

**A self-imposed ceiling should be set before any arm runs**, in finding 016's shape — that finding
declared **$2.00** and reported against it. Rows B and C error by design, so a retry loop on a 400 is
the failure mode that would spend the ceiling without producing a reading.

## 7. Owed register entries and one requirement question, **quoted, not made**

~~Nothing in this section was applied.~~ **Superseded in part 2026-08-05: the two register entries were
approved and landed by a later pass, as recorded in the banners under [§7.1](#71-to-research14-architecture-synthesismd-52--a-new-uncertainty-entry)
and [§7.2](#72-to-research14-architecture-synthesismd-4--a-contradiction-row). Nothing in
[§7.3](#73-a-question-about-fr-037-with-candidate-text--and-the-recommendation-is-to-make-no-edit) was
applied and no requirement was touched.** All three are the owner's.

**The formatting escape, so it does not read as a mistake.** Inside each quoted block the identifier
is written in a code span and the link path is the one correct **from the destination file**, not from
here. `link-target` resolves every live link relative to the document it appears in, and
`identifier-resolution` refuses a register identifier that the register does not yet carry — so both
must be escaped while they sit in a finding. Strip the backticks when the text is pasted into its
destination. Same escape and same reason as
[finding 029](./029-wall-clock-ceiling-unenforced.md) §7 and
[finding 026](./026-pivot-root-check-measured.md).

### 7.1 To [`research/14-architecture-synthesis.md`](../../../research/14-architecture-synthesis.md) §5.2 — a new uncertainty entry

> **LANDED 2026-08-05 as U-52**, in [`14-architecture-synthesis.md`](../../../research/14-architecture-synthesis.md)
> §5.2, which is where this section said it belonged. **The mark was re-read at landing rather than
> taken from this document**, and it was still **U-51**, so the number proposed here is the number
> assigned. **The method is worth recording, because the obvious one is wrong in the dangerous
> direction:** a backtick-anchored search for `` `U-NN` `` over that file returns **U-49** as its highest
> hit, because register rows write the identifier **bare** in the first table cell and only *prose
> citations* wrap it in a code span — so the anchor sees the citations and misses the register. The same
> search for C-numbers returns nothing at all. What works is a boundary-anchored search with no markup
> assumption, `rg -oP '(?<![A-Za-z0-9-])U-\d+'`, run over the whole corpus and not only over the
> register file; it returns U-50 and U-51, which a correct method must.
>
> **The §5.2 placement was verified against the section's own text rather than inherited from this
> argument, and it holds** — with one reason available here that this section did not use. §5's preamble
> defines blocking as *"do not commit architecture or make a customer promise until resolved"*, and the
> second limb is as unmet as the first: the unmeasured thing is a prediction about **vendor** behaviour,
> and no customer promise rests on it. Stronger still, [finding 016](../../001-discovery-validation/findings/016-provider-sdk-roundtrip.md)
> result 4 measured all four providers **accepting** the full chain live, so the direction the runtime
> committed to is the measured-accepted one and the open question is only about the condition it does
> not send.
>
> **Four changes were needed to make the quoted row correct in its destination, and they are listed so
> the next author quoting a row into a register expects them.** ① The identifier is written **bare**,
> `| U-52 |`, not in a code span — the code span was the escape for sitting in a finding, and every row
> in §5.2 writes it bare. ② `finding 016` was quoted here as a bare code span with no link; it had never
> been cited in `14-architecture-synthesis.md` before, so it landed as a real link. ③ *"~100–150k input
> tokens"* is written **~100,000–150,000**, the form [§6](#6-the-probe-that-would-convert-this-designed-and-not-run)
> uses, so `numeric-provenance` can find the figure in the document that derived it. ④ The row gained a
> closing **non-blocking** clause naming why §5.2 and not §5.1, and a sentence saying **T164 is not a
> route to converting it** — both are house format in §5.2 and both are [§7.4](#74-sc-010-and-t164-need-nothing-and-the-reason-is-worth-stating)'s
> content rather than new reasoning.
>
> **Propagation, which the landing pass owed and this one did not know about:**
> `specs/001-discovery-validation/VERDICT.md` §SC-004 advances to `U-01…U-52` and gains an eighth
> refresh entry. `gen_claims.py` classifies that site `MANUAL` and refuses to write it, by design.

**§5.2 and not §5.1.** §5.1's own definition is *"do not commit architecture or make a customer promise
until resolved"*; the architecture is committed, the error direction is conservative, and
[§4](#4-why-none-of-this-reopens-the-decision) gives four independent reasons the decision stands. This
is high-impact and non-blocking. The next free number is one past the register's high-water mark, which
was `U-51` when this was written — **read the mark and add one rather than taking this number.**

> | `U-52` | **NEWLY OPENED 2026-08-05 — the provider layer's request shape rests on vendor documentation alone, and one of its four limbs is contradicted by the only live arm that bears on it.** `src/runtime/context.py::states_for` sends every kept turn's opaque state on the strength of four documentation readings; none has been measured, and no request with a state deliberately withheld has ever been sent to OpenAI, Google or Anthropic from this repository. The sharp form — *three of the four error on a miss, Anthropic degrades quietly* — is a falsifiable prediction that has never been run. **For xAI it has been run in the adjacent condition and it failed**: `finding 016`'s negative control stripped `encrypted_content` from every assistant message on a live `grok-4.5` chain and recorded `provider_errored: false`. | The request shape is the same on all four providers and is the only thing standing between a session and a silently degraded turn on the one provider predicted not to error. Being wrong about **Anthropic** is the worst case and produces no signal: `finding 016` result 7 measured a stripped chain answering correctly. | The 12-arm probe designed in `[finding 030](../specs/002-spec-aware-agent-runtime/findings/030-provider-state-chain-derived-not-measured.md)` §6 — four providers × {full chain, one state dropped, all states dropped}, with Anthropic as the negative control and the full-chain arm as the one-variable baseline. ~100–150k input tokens; the only measurable dollar figure is xAI's, on the order of $0.01–0.03. **Not run; no spend authorised.** | `[finding 030](../specs/002-spec-aware-agent-runtime/findings/030-provider-state-chain-derived-not-measured.md)` |

### 7.2 To [`research/14-architecture-synthesis.md`](../../../research/14-architecture-synthesis.md) §4 — a contradiction row

> **LANDED 2026-08-05 as C-21**, in [`14-architecture-synthesis.md`](../../../research/14-architecture-synthesis.md)
> §4, **partially resolved**, which is the disposition this section proposed. **The mark was re-read at
> landing and was still C-20**, by the boundary-anchored method [§7.1](#71-to-research14-architecture-synthesismd-52--a-new-uncertainty-entry)
> records; the backtick-anchored search that fails on U-numbers fails *worse* on C-numbers, returning
> **nothing at all**, because that file never writes a C identifier inside a code span.
>
> **Partially resolved is house format in §4 and was checked rather than assumed** — C-10 carries
> *"Partially discharged 2026-08-02"*, C-16 stays open having been narrowed three times, and C-17 closes
> on a mechanism while its residue is recorded as untouched. A row that closes one half and names the
> other as unmeasured is what that section already does.
>
> **One change to the quoted row was mandatory rather than stylistic, and it would have been caught by
> the checker rather than by a reader.** The row as drafted here has **four** cells, and §4 is a
> **three-column** table — `#`, `Contradiction`, `Resolution` — so `table-integrity` refuses it. The
> source cell is folded into the resolution as a trailing `**Sources:**` clause, which is what C-14
> through C-20 all do. The landed row also cites [finding 016](../../001-discovery-validation/findings/016-provider-sdk-roundtrip.md)
> by name and links `.cursor/skills/experiment-design/SKILL.md` Rule 8 — the rule this document had to
> correct the commissioning brief about — so the citation lands where the rule actually lives.

§4's subject is *"Where the corpus disagrees"* and two committed artifacts in this repository disagree
in terms. The high-water mark was `C-20` when this was written.

> | `C-21` | **NEWLY OPENED 2026-08-05 — a source docstring and a committed live artifact disagree about whether xAI rejects a conversation with its opaque field missing.** `src/runtime/context.py::states_for` states *"Only Anthropic degrades quietly on a miss; the other three fail the request."* `specs/001-discovery-validation/harness/provider-sdk-roundtrip/results/negative-control.json` records `"provider_errored": false` for a live `grok-4.5` chain with `encrypted_content` blanked on every assistant message. | **Partially resolved, and the docstring loses on the point of overlap.** The docstring's claim carries no condition, so the measured drop-all case falls inside its scope and the sentence is wrong as written. The narrower claim it was reaching for — that xAI rejects a chain with a *hole* rather than a chain with *nothing* — is untouched by the measurement and remains unmeasured; those are different requests and a validator could distinguish them. The docstring was corrected on 2026-08-05 to say what the evidence supports; the register row is retained because the *narrow* claim still has no measurement behind it. | `[finding 030](../specs/002-spec-aware-agent-runtime/findings/030-provider-state-chain-derived-not-measured.md)` §2 |

### 7.3 A question about FR-037, with candidate text — **and the recommendation is to make no edit**

**FR-037 needs no change to condemn either defect, and that is worth recording as a positive result
about the requirement.** *Never dropped* condemns the drop directly. The requirement was doing its job;
the implementation did not match it, and no amount of specification would have caught that.

**The genuine gap, which is small.** FR-037 forbids dropping and forbids **cross-provider** merging. It
does not in terms forbid **cross-turn mis-attachment within one provider** — the worse of the two
defects. *"Round-tripped verbatim"* arguably reaches it, since a value written onto a different message
is not that message's state round-tripped, but the reading is not forced by the words and the register
contains no entry saying so.

Candidate text, **not applied**, offered only so the question is answerable without re-deriving it:

> - **FR-037**: … Provider-opaque reasoning state MUST be a first-class value on every turn,
>   round-tripped verbatim, never dropped, **never re-attached to a turn other than the one that
>   emitted it**, and never merged across providers.

**Against making it**, and this is the stronger side: the mechanism already refuses the case —
`reinject` raises on a length mismatch and on a slot with no path to land at, and three removal proofs
hold those refusals — so the requirement would be documenting a property already enforced, and this
corpus has recorded specification text added after the fact as the weakest kind of guard. **The owner
decides; this finding recommends no edit and states the gap so the recommendation is checkable.**

### 7.4 SC-010 and T164 need nothing, and the reason is worth stating

**SC-010** reads: *"The full User Story 1 battery completes against at least four independent model
providers with configuration as the only difference between runs"* ([`spec.md`](../spec.md):2159–2160).
Under **OD-16** it is *"a test v1 must pass rather than a result it inherits"*, discharged by **T164**.

**No edit is warranted and none is proposed. What is worth writing down is that T164 cannot convert
this and nobody should wait for it to.** SC-010's criterion is *completion*, and its stated variable is
*configuration*. T164 varies the provider; it does not vary the state chain. So:

- with the runtime correct — as it now is — **T164 passes and learns nothing about a miss**, because
  every arm carries the full chain;
- T164 would have been an *accidental* detector of the erroring limbs only while the runtime was
  broken, and only on the two providers whose documentation promises an error.

A criterion that can only detect a defect while the defect is present is not a route to confirming the
prediction. The probe in [§6](#6-the-probe-that-would-convert-this-designed-and-not-run) is, and it is
a different experiment from T164 rather than an extension of it.

## 8. The one edit this pass **did** make, and why it is not a register edit

**`states_for`'s docstring and the assertion message in `check_roundtrip` were corrected**, and this is
disclosed rather than folded into the finding, because a pass commissioned to *report* should be
visible where it changed something.

**Why it was changed rather than filed as owed.** It is **source**, not a register entry and not a
requirement — the brief's constraint names those two. And leaving a claim in the tree that this
finding measures to be contradicted, while filing a document saying so, produces the worst of both:
the docstring is what a future contributor reads, and the finding is what they do not.

**What changed**: only the xAI limb and the unconditioned *"the other three fail the request"*
sentence, plus a dated note pointing here. **No behaviour changed, no quote was removed, and the three
limbs the evidence supports are untouched.** The two removal proofs over `state.py` and the one over
`test_provider_state_roundtrip.py` target code lines rather than message prose and are unaffected;
`check_tampers.py` was re-run and reports **0 errors, 0 warnings**.

## 9. The two defects `c25b85b` closed, with attributions re-derived

Both attributions were re-derived here rather than carried over from the brief, and both hold.

**Defect 1 — the drop.** `states_for`'s predecessor returned the most recent non-`None` state, so every
earlier turn's was discarded. Against FR-037's *never dropped*.

```
$ git log --oneline -S "state_for" -- src/runtime/context.py
c25b85b Carry every turn's opaque provider state, not only the newest
95ffacd Read the turn count off the journal, so a rebuilt loop cannot restart a ceiling
```

Two commits touch the identifier: the one that removed it and **`95ffacd`** (2026-08-04 12:55:01 -0600),
which introduced it. **Attribution confirmed.**

**Defect 2 — the mis-attachment, which is worse and was not anticipated.** The backward scan **skipped**
a turn that emitted no state and returned an older turn's; `reinject` then wrote whatever it was handed
onto the **last** assistant entry. So in any conversation with an intervening stateless turn, an older
turn's opaque value was written onto a later turn's message — on Anthropic, a `signature` key appearing
on a `tool_use` block. **The provider signed neither**, and the result is well-formed JSON it accepts
and cannot detect on the way in.

```
$ git log --oneline -S "reinject" -- src/runtime/providers/
6a27a98 Translate one tool call into four wire formats, both directions (T057, T058)
```

**`6a27a98`** (2026-08-05 13:37:20 -0600). **Attribution confirmed for the `reinject` half**, which is
the half the brief attributes to it. The other half — the backward scan that skips — is `95ffacd`'s, so
the defect is **jointly owned and existed for under seven hours**: `6a27a98` landed the write-onto-the-last-entry
behaviour at 13:37 on 2026-08-05 and `c25b85b` removed it the same day.

**A property of this defect that neither commit message states.** It required **two** independently
reasonable pieces of code to meet. A backward scan returning the newest non-`None` state is defensible
in isolation; writing a single blob onto the newest assistant entry is defensible in isolation. Neither
author was wrong about their own function's contract, because **there was no contract** — the
positional alignment `reinject` now checks did not exist to be violated. That is why the repair is an
alignment invariant and a refusal rather than a corrected scan.

## 10. The premise that was wrong, and why being wrong about it was worse than it looked

The previous pass and the brief both held: *"Anthropic wants the signature on the immediately preceding
assistant turn and strips older ones server-side."* **It is wrong in two independent ways**, either of
which is sufficient:

1. **A tool-use loop is one assistant turn.** Within one, *"you must pass the thinking blocks from the
   assistant message back to the API, complete and unmodified."* The old behaviour was not carrying
   "the previous turn"; it was carrying a fragment of the current one.
2. **On Opus 4.5 / Sonnet 4.6 and later nothing is stripped at all.** The server-side stripping is
   about turns before the current one, and on those models it does not apply.

**So Anthropic never justified the old behaviour** — it was the provider the old code was written for
and the provider whose documentation least supports it.

**And it is the only one of the four that fails quietly, which makes being wrong about it worse rather
than safer.** The intuition the premise rested on runs the other way: *Anthropic is the lenient one, so
it is the safe one to be approximately right about.* The opposite holds. A wrong prediction about
OpenAI or Google surfaces as a 400 on the first session. A wrong prediction about Anthropic surfaces as
nothing — and finding 016 result 7 measured that the answer is no help, because a chain with the field
stripped entirely *"still chained and still answered 149.99."*

## 11. What this does **not** establish

- **It does not establish that any provider tolerates a missing state.** One condition on one provider
  was measured not to error. That is one cell of a twelve-cell table.
- **It does not establish that any provider rejects one.** No such request has been sent from this
  repository to OpenAI, Google or Anthropic in any condition.
- **It does not establish anything about quiet degradation on Anthropic, in either direction.** Nothing
  has measured it and [§6](#6-the-probe-that-would-convert-this-designed-and-not-run) records that the
  designed probe would not either.
- **It does not establish that the vendor documentation is wrong.** Two of the four limbs carry
  explicit error language and this finding offers no evidence against them. What it establishes is that
  the corpus holds **no measurement** of any of the four, and that one limb's *quoted* evidence does not
  support the claim built on it.
- **It does not establish that the byte-fidelity result is unsound.** T061's chain is measured and its
  assertions are on the bytes. It establishes that the payloads are ours, so the result is about the
  drivers and not about any provider — which is what `require_recorded()` says and what the fixture's
  own arm asserts.
- **It does not re-run finding 016.** Every figure attributed to it is read from its committed
  artifacts, taken 2026-08-03 on one credential set, one run per arm for three of the four.
- **It does not establish that `_rebuilt` is the last level of the aliasing defect.** It removed the
  second occurrence. Nothing here searched for a third, and the pattern in
  [§5](#5-the-conformance-fixture-was-blind-twice-in-the-same-place-one-level-apart) is the reason that
  is worth saying rather than assuming.

## 12. Errors in the brief that commissioned this pass

Listed explicitly, because the reasoning was supplied to be falsified and most of it survived.

- **Wrong on the mechanism, right on the conclusion, and the truth is stronger.** *"Its arms used the
  vendor SDKs, which accumulate the conversation internally."* Three of the four SDKs are stateless
  with respect to conversation and take the whole history from the caller. The accumulation is in the
  arm modules' own local lists. The conclusion — every arm carried every state by construction — holds
  for the better reason that **the arms have no persistence boundary at all**. [§3](#3-what-finding-016-is-and-is-not-evidence-for-checked-against-its-arms-and-not-its-prose).
- **Wrong on where Rule 8 lives.** *"`tools/README.md` records a rule, added as Rule 8."* It does not;
  that file contains no `Rule N` text at any site. Rule 8 is a rule of the `experiment-design` skill.
  Its heading is quoted verbatim in the banner above.
- **Too generous to the sharp claim.** *"A falsifiable prediction that has never been run."* For xAI
  the adjacent condition **has** been run, live, and the result points the other way.
  [§2](#2-the-xai-limb-is-not-unmeasured--it-is-contradicted-and-the-condition-matters).
- **Understated on the four determinations, in the brief's own favour.** The brief treats the four
  limbs as uniformly documentation-derived. They are not uniform: OpenAI's and Google's quotes carry
  explicit error language, xAI's carries only an imperative that the docstring silently upgrades into
  an enforcement claim, and Anthropic's claim is a *negative* nobody has looked for. Three different
  evidential strengths in one sentence.
- **Arithmetic, minor.** *"8 calls"* is 8 **arms** of roughly six calls each — ~48 calls, or ~72 for
  the 12-arm version this finding recommends.
- **Right, and confirmed:** both `git log -S` attributions; that the conformance fixture runs against
  synthetic cassettes and `require_recorded()` refuses all six; both fixture blindnesses and the
  `_persisted` / `_rebuilt` repairs; both halves of the correction to the Anthropic premise; that
  Anthropic is a genuine negative control rather than a fourth repetition, and that all-four-erroring
  would indicate the probe is measuring something else; that the mis-attachment is the worse defect and
  that it produces JSON the provider accepts and cannot detect.
- **Right about the baseline this time, against its own expectation.** The brief warned that
  `EXPECTED_PROOFS` *"reads 128 as I write this"* and that its baselines *"have gone stale on every one
  of the last four passes."* It was **not** stale: `check_tampers.py` reported `128 proofs declared`
  before this pass and the guard's own message reported the transition as *"the proof set moved from
  128 to 129."*
