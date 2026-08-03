# Phase 1 Quickstart — Spec-Aware Agent Runtime

**Feature**: `002-spec-aware-agent-runtime` | **Date**: 2026-08-03 | **Phase**: 1 (`/speckit-plan`)

**Plan**: [`plan.md`](./plan.md) · **Phase 0**: [`research.md`](./research.md) · **Contracts**:
[`contracts/`](./contracts/)

---

## What this document is

The operator path SC-001 measures, and the validation scenarios that close each user story. It
describes the intended shape of the experience so that the design can be checked against it; nothing
here is built yet.

**Prerequisite**: Linux with cgroup v2, user and mount namespaces, and `seccomp` user notification.
Every other platform is **unsupported** under FR-053, because all three of FR-048, FR-049 and
FR-050's mechanisms are kernel facilities (**Q-11**). Operators elsewhere run the bundle in a Linux
VM.

---

## The operator path

### 1 · Configure

Fill the environment file. Every key in
[`contracts/configuration.md`](./contracts/configuration.md)'s required table must be set — including
**both** processor bounds and the memory bound, which have **no defaults** because nothing in the
evidence base bears on an agent's working set (FR-049).

A missing or malformed key stops startup with a named reason. There is no permissive mode (FR-033).

### 2 · Admit the deployment

The system fetches the target's published specification, establishes correspondence between the
running deployment and the source commit, and either admits or **refuses with the missing criterion
named** (FR-001, FR-002, FR-003).

A target that publishes no specification is refused. That is not a limitation to work around: the
published specification is the independent artifact that validates derived contracts under
constitution Principle I as amended at v1.1.0 ([`research.md`](./research.md) T-14).

### 3 · Analyse

`codegraph` indexes the source; contracts and checks are derived statically, with **no model
involved** (T-13); artifacts are canonically serialized and content-addressed.

**Analysis wall time is reported separately**, and the reference application's size is stated
alongside it. SC-001's fifteen-minute window contains this step, and **U-21** records `codegraph`'s
scale claim as untested with one small-repository datapoint. Reporting the two separately is what
makes SC-001 assessable instead of quietly true on small inputs ([`research.md`](./research.md)
§7.2).

### 4 · Inspect before running

The operator reviews the served-operation set, the derived contracts with their `validated` or
`provisional` marking, the effect rule set with its per-rule justifications, and the declared
filesystem and bound sets — **before** any session starts (FR-012, FR-019, FR-020).

Expect a share of contracts to be `provisional`. Finding 007 measured the validated reading at
**0.7681** on one target and one framework, so roughly a quarter provisional on a comparable target
is the expectation rather than a fault.

### 5 · Ask a question

The agent runs one loop, read-only against the target (**OD-10**). Every outbound call is resolved
per call at the enforcement point before it is sent.

The answer comes back as a [result record](./contracts/result-record.md): **verified**,
**not verifiable**, or **refused**, with staleness as a separate field. *Not verifiable* is a
first-class outcome, and FR-045 makes its share a reported measurement precisely so that suppressing
it is visible rather than rewarded.

---

## Validation scenarios

Each scenario is the acceptance shape for a user story; the mechanisms are in
[`research.md`](./research.md) and the assertions in [`contracts/`](./contracts/).

### A · A verified answer, unattended — User Story 1, SC-001, SC-010

Run steps 1–5 against the reference application with no intervention. Assert a result record with
evidence, a recomputed value distinct in provenance from the reported one, and the artifact versions
in force. Repeat across **four independent providers** (SC-010), including the per-provider
**opaque-state round-trip conformance** fixture over a long chained tool sequence on a reasoning
model — finding 003 declined to read a passing two-hop case as clearance, and neither does this
(T-02).

### B · The write gate holds under an adversarial battery — User Story 2, SC-002, SC-014

Drive the agent with prompts designed to induce a side-effecting call. Assert **zero** reach the
target, every denial carries its rule identifier, and no denial was produced by inspecting what a
command looked like (FR-013).

Then the measurement, which is the part that is not the capability: the enforcement point's
observation corpus is labelled by **state diff** on the reference application — snapshot, call, diff
— which is observable evidence rather than a model judgement. The threshold for read-only precision
is **pre-registered before the measurement runs and is not set here**; **OD-10** records why the
superseded per-tool number does not travel (FR-041).

### C · The boundary holds — User Story 3, SC-022, SC-023, SC-024

Three arms, one per mechanism.

**Filesystem** — attempt access outside the declared set. Assert it fails, and assert the attempt is
**recorded with the rule that produced it**, in the same shape as an egress denial. A mount namespace
enforces this and records nothing, which is why a syscall supervisor exists; its overhead is measured
on the reference application before it is committed (**Q-09**).

**Bounds** — drive memory and processor past their declared bounds. Assert a **named** terminal state
(`terminated.memory_bound_exhausted`, `terminated.cpu_bound_exhausted`), assert consumption up to the
kill is still counted against FR-005's ceilings, and assert a co-located workload on the same host
keeps serving throughout. That last assertion is why FR-049's one bound is implemented as two — a
cumulative ceiling does not protect a co-tenant and a rate quota never ends a session
([`research.md`](./research.md) §3.2).

**Credential lifetime** — the replay fixture, both arms. Capture the capability handle during a
session; `SIGKILL` the session **from a separate process**, so no cleanup path can run — the
technique finding 006 used for exactly this reason. Then:

- replay from inside a **later session's** environment → **denied and recorded**;
- replay from a position with **no path** to the enforcement point → refused by unreachability,
  recorded only as a drop counter.

The two arms are reported separately rather than pooled, because the topology gives them different
recording properties ([`plan.md`](./plan.md) Complexity Tracking).

Assert also: no secret readable from inside the container at any point, and the residual lease window
measured against its configured value — a value marked unvalidated under FR-043.

### D · Drift is detected on both clocks — User Story 4, SC-008, SC-009, SC-015, SC-020

Two committed synthetic corpora, each controlling its own change time: one mutates source while the
deployment stands still, one changes what the deployment serves while source stands still. Assert a
signal on the correct clock, with both artifact versions and the deployment identity.

Assert also the **negative**: re-analysing unchanged input produces **no** signal. This is the
determinism test on the canonical serializer, and without it drift detection false-alarms every
interval (T-12).

Deployment-clock latency is measurable here because the corpus controls the change time. On real
traffic it generally is not, unless the customer emits a deployment event that FR-046 says may not be
assumed — a property of the world, recorded in [`plan.md`](./plan.md) Complexity Tracking.

### E · The verifier is compared to a judge, and the judge cannot reach the caller — User Story 5, SC-013, SC-025

Run identical sessions three ways: judge agreeing, judge disagreeing, judge absent. Assert the
caller-visible output is **byte-identical across all three**, and assert by import graph that the
result-record and gate-decision modules cannot reach the judge module at all (FR-052).

The margin measurement itself needs ground truth the verifier cannot supply without circularity. The
adjudication queue — pre-registered sampling, an operator surface, `human_label` rows — is built as
part of the instrumentation, and **SC-013's window opens only once labelling capacity exists**. This
is reported, not worked around; substituting the verifier's verdict would be circular and
substituting a model is what FR-052 exists to prevent
([`research.md`](./research.md) §4.1, §7.1).

---

## What an operator will not find here

Not because they are unfinished, but because **OD-09** deferred them to v2 and a quickstart is where
deferred scope reappears first: a generated tool catalogue, promotion selection, static per-tool
effect labels, a knowledge-graph memory layer, an embeddable iframe, and multi-agent artifact
trading. The full check is [`research.md`](./research.md) §6.
