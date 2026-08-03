# Contract — The Caller-Visible Result Record

**Requirements**: FR-022–FR-026, FR-045, FR-047, FR-052
**Constitution**: Principle I, including the v1.1.0 validate-or-mark-provisional clause and the
model-judge clause

---

## Shape

```text
ResultRecord
├── verification_state : verified | not_verifiable | refused      (FR-025, exhaustive)
├── value                                                          (absent when refused)
├── evidence
│   ├── reported_value
│   ├── recomputed_value                                           (present iff verified)
│   ├── derivation_ref        → DerivedContract.content_hash
│   └── derivation_validation : validated | provisional            (FR-026)
│       └── provenance, confidence                                 (required iff provisional)
├── stale : bool + staleness_reason                                (FR-047 — a FIELD, not a state)
├── refusal : rule_id + named_reason                               (present iff refused)
└── deployment_id, session_id, artifact_versions[]                 (FR-031)
```

## The three states are exhaustive and mutually exclusive

**verified** — the value was recomputed against an independently derived path and agreed (FR-023).
The derivation and the reported value do not share a source (FR-024).

**not verifiable** — no derived contract covers this, or the contract covering it is `provisional`.
This is a **first-class outcome and not a failure**: FR-045 makes the share of results in this state
a reported measurement with no threshold, precisely so that suppressing it is visible rather than
rewarded.

**refused** — the operation was denied, with the rule that denied it (FR-011).

**Staleness is a separate field** because a stale verified result and a stale unverifiable result are
different things, and collapsing them into a fourth state would lose which (FR-047).

## The model-judge boundary, and how it is enforced

Constitution Principle I forbids a model judgement reaching caller-visible behaviour unless it is
pairwise and calibrated against human labels. The specification scopes the clause to the success path
and declares the shadow judge outside it.

**The plan does not rely on that being a policy.** Three structural facts:

1. `ResultRecord` has **exactly one constructor**, and it takes a `VerificationOutcome`. There is no
   other way to produce one. A model verdict is not a `VerificationOutcome` and cannot be converted
   into one.
2. The module defining `ResultRecord` **does not import the judge module**, and neither does the
   gate-decision module. Asserted by an import-graph test in `tests/invariants/`.
3. The judge consumes the trace stream **asynchronously**, after the fact, and writes to a table
   nothing on the success path reads.

So no model judgement can reach caller-visible behaviour, with or without the pairwise-and-calibrated
conditions. The conditions are not the only thing standing in the way — which is what FR-052 asks
for.

## Validated versus provisional

A derived contract is `validated` when it agrees with the target's **published specification** — an
artifact the derivation did not produce, which FR-002 already requires at admission, so it is in hand
for every admitted target before any session starts. Otherwise `provisional`, with provenance and
confidence.

**A provisional contract can produce `not_verifiable` and never `verified`.** Enforced at the type
level.

Finding 007 measured this comparison on one target and one framework: the literal reading is
**0.8696** and the validated reading **0.7681**. A comparable target would leave roughly a quarter
provisional. Recorded so the share is expected rather than alarming; not generalized to other
frameworks.

## Tests owed

- Every state reachable, and the three exhaustive over a fixture battery.
- A provisional contract never yields `verified`.
- `derivation_ref` and `reported_value` never share a source (FR-024).
- Import-graph: the judge module is unreachable from the result-record and gate-decision modules.
- A differential battery running identical sessions with the judge agreeing, disagreeing, and absent:
  **caller-visible output byte-identical across all three** (SC-025).
- Stale-and-verified and stale-and-unverifiable both representable and distinguishable.
