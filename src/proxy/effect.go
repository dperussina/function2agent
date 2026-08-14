package main

import "context"

// Stages 5 and 6 — effect (T088, T089; FR-008, FR-009, FR-010).
//
// Stage 5 resolves the call to an effect tier PER CALL and blocks: the disposition is decided
// before anything is sent (FR-008). It matches the path against the served-operation set, consults
// the maintained deny list of known side-effecting reads, and denies anything that resolves to a
// tier other than read_only. Only read_only may be permitted; reversible_write, irreversible and
// unresolved are all denied outright and nothing escalates to a human (FR-009).
//
// Stage 6 denies an operation the served set does not describe, with operation_unresolvable. It is
// a separate stage because FR-010's "denied, not guessed" is a distinct claim from FR-009's tier
// rule, and it must have its own rule identifier in the log. Stage 5 resolves the tier to
// "unresolved" and allows; stage 6 is what refuses it. That is safe because the pipeline is a
// conjunction — every gate stage must allow — and it is proved by TestUnresolvedNeverReachesFinal.

// resolution is what stage 5 computes and stage 6 and stage 7 read.
type resolution struct {
	Tier            string
	OperationID     string
	DenyRuleID      string // set only when the deny list matched
	MatchedTemplate string
	SpecMetadata    string
}

// resolveEffect is the tier resolution, as a pure function of the policy and the call.
//
// FR-010: a call resolves read_only when its method is a safe method of a served operation in the
// set AND it matches no entry in the deny list. Everything else is not read_only.
func resolveEffect(policy *Policy, method, path string) resolution {
	if policy == nil {
		return resolution{Tier: tierUnresolved, SpecMetadata: emptySpecMetadata}
	}
	// Observation looks the served operation up regardless of the deny-list
	// hit: the corpus needs the template and the specification metadata even
	// when the call is denied. The deny list is still what decides the tier.
	// Returning early from a served-set match would make the deny list
	// unreachable for exactly the calls it exists to stop; this lookup does
	// not return.
	op := policy.MatchOperation(method, path)
	template := ""
	opID := ""
	if op != nil {
		template = op.PathTemplate
		opID = op.OperationID
	}
	meta := specMetadataOf(op)
	if d := policy.MatchDenyEntry(method, path); d != nil {
		if template == "" {
			template = d.PathTemplate
		}
		return resolution{
			Tier:            tierReversibleWrite,
			DenyRuleID:      d.RuleID,
			OperationID:     opID,
			MatchedTemplate: template,
			SpecMetadata:    meta,
		}
	}
	if op == nil {
		return resolution{Tier: tierUnresolved, SpecMetadata: emptySpecMetadata}
	}
	if !op.Safe || !safeMethods[method] {
		// The served set describes it, but not as a read. The tier is not read_only and the
		// call is denied; nothing here tries to distinguish reversible from irreversible,
		// because both are denied and guessing between them would be a claim with nothing
		// behind it.
		return resolution{
			Tier:            tierReversibleWrite,
			OperationID:     op.OperationID,
			MatchedTemplate: template,
			SpecMetadata:    meta,
		}
	}
	return resolution{
		Tier:            tierReadOnly,
		OperationID:     op.OperationID,
		MatchedTemplate: template,
		SpecMetadata:    meta,
	}
}

// EffectStage is stage 5.
type EffectStage struct {
	stageName
	policy *Policy
}

// NewEffectStage builds stage 5.
func NewEffectStage(policy *Policy) *EffectStage {
	return &EffectStage{stageName: "effect", policy: policy}
}

// Evaluate resolves the tier per call and denies anything resolved as not read_only. It writes the
// resolution onto the request context so that the tier appears on the decision record whatever the
// eventual disposition is.
func (s *EffectStage) Evaluate(_ context.Context, rc *requestContext) (stageResult, error) {
	res := resolveEffect(s.policy, rc.Method, rc.Path)
	rc.Tier = res.Tier
	rc.OperationID = res.OperationID
	rc.MatchedTemplate = res.MatchedTemplate
	rc.SpecMetadata = res.SpecMetadata

	if res.DenyRuleID != "" {
		return denyResultWithPolicyRule(RuleKnownSideEffectingRead, res.DenyRuleID,
			"path="+quoteForDetail(sanitizeDetail(rc.Path))), nil
	}
	switch res.Tier {
	case tierReadOnly:
		return allowResult(), nil
	case tierUnresolved:
		// Left for stage 6, whose whole subject this is. Stage 6 immediately follows and
		// denies it; the pipeline is a conjunction, so allowing here permits nothing.
		return allowResult(), nil
	default:
		return denyResult(RuleTierNotReadOnly,
			joinDetail("tier="+quoteForDetail(res.Tier), "operation_id="+quoteForDetail(sanitizeDetail(res.OperationID)))), nil
	}
}

// UnresolvableStage is stage 6.
type UnresolvableStage struct {
	stageName
}

// NewUnresolvableStage builds stage 6.
func NewUnresolvableStage() *UnresolvableStage {
	return &UnresolvableStage{stageName: "unresolvable"}
}

// Evaluate permits only a call stage 5 resolved to read_only. An unresolved call is denied with
// operation_unresolvable — denied, not guessed. Any other non-read_only tier that reached here
// (it should not have) is denied too, so removing stage 5 does not open the gate.
func (s *UnresolvableStage) Evaluate(_ context.Context, rc *requestContext) (stageResult, error) {
	switch rc.Tier {
	case tierReadOnly:
		return allowResult(), nil
	case tierUnresolved:
		return denyResult(RuleOperationUnresolvable,
			joinDetail("method="+quoteForDetail(sanitizeDetail(rc.Method)),
				"path="+quoteForDetail(sanitizeDetail(rc.Path)))), nil
	default:
		return denyResult(RuleTierNotReadOnly, "tier="+quoteForDetail(sanitizeDetail(rc.Tier))), nil
	}
}
