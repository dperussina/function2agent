package main

import "context"

// Stage 4 — method (T087, FR-015).
//
// The method allowlist is evaluated TOGETHER WITH the destination, on the same request, in one
// predicate. Never separately: a proxy that sees a host and a port and applies a method allowlist
// somewhere else has silently degraded it into a destination allowlist, which is the exact failure
// OD-12 tested for and the reason a CONNECT-oriented proxy was rejected.
//
// Stage 3 has already classified the destination. This stage classifies it AGAIN, on the same
// request, and combines the two answers — because "evaluated together" is a property of the
// predicate, not of the ordering of two independent gates. Re-running is cheap and it means
// removing stage 3 does not silently make the method allowlist the only check.
//
// FR-015 also requires the allowlists to be applied identically whether the request originated in
// the runtime or in a command the agent composed. There is no code path here that distinguishes
// them, and there is nothing in requestContext to distinguish them with: see the comment on
// requestContext and TestNoProvenanceField.

// MethodStage is stage 4.
type MethodStage struct {
	stageName
	origin PinnedOrigin
	policy *Policy
}

// NewMethodStage builds stage 4.
func NewMethodStage(origin PinnedOrigin, policy *Policy) *MethodStage {
	return &MethodStage{stageName: "method", origin: origin, policy: policy}
}

// Evaluate applies the joint predicate.
func (s *MethodStage) Evaluate(_ context.Context, rc *requestContext) (stageResult, error) {
	return checkMethodAndDestination(rc.Method, rc.RawTarget, s.origin, s.policy), nil
}

// checkMethodAndDestination is the joint predicate: the request is permitted only if the
// destination resolves to the pinned origin AND the method is in the allowlist. A permitted method
// to a non-pinned destination is denied, and a non-permitted method to the pinned destination is
// denied.
func checkMethodAndDestination(method, rawTarget string, origin PinnedOrigin, policy *Policy) stageResult {
	dest := checkDestination(rawTarget, origin)
	if !dest.allowed {
		return dest
	}
	if policy == nil {
		// No policy is no allowlist, and no allowlist permits nothing.
		return denyResult(RuleMethodNotAllowed, "reason=\"no_policy_loaded\"")
	}
	if !policy.MethodAllowed(method) {
		return denyResult(RuleMethodNotAllowed, "method="+quoteForDetail(sanitizeDetail(method)))
	}
	return allowResult()
}
