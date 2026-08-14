# Operator obligations — T197

This is the checkable record, not an essay.
`tests/contract/test_operator_obligations.py` walks this file. Dropping
either obligation, or weakening FR-050 or OD-17, fails that test.

The Assumptions section of
[`specs/002-spec-aware-agent-runtime/spec.md`](../specs/002-spec-aware-agent-runtime/spec.md)
states two operational obligations. Both are stated here rather than
discovered at install. The first was once described as the one obligation
v1 placed on a self-hosted operator; FR-048 through FR-050 superseded that
on 2026-08-03. What changed is what the operator is *told*, not what they
would have had to do.

## 1. Enforcement point

The operator can run the enforcement point and route the agent's
environment through it.

## 2. Execution environment

The operator must also run the agent's commands inside an environment that
is filesystem-scoped, processor- and memory-bounded, and holds no
credential outliving the session.

That environment is **Linux only, no degraded mode (OD-17)**. Every other
platform is unsupported rather than best-effort (FR-053). A configuration
missing any of FR-048, FR-049 or FR-050 does not satisfy constitution
Principle IV bullet 1.

**FR-050 is not weakened here.** No credential that outlives a session may
be present in, or retrievable from, the agent's execution environment —
not as an environment variable, not as a file inside FR-048's declared
set, and not as process state. The operator's own long-lived provider and
target credentials stay outside that environment entirely.
