package main

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"strings"
)

// The seven-stage sequencer.
//
// Fail-closed is STRUCTURAL here, not a convention:
//
//   - A stage returns a stageResult whose ZERO VALUE IS DENY. A stage that returns without
//     explicitly calling allowResult therefore denies. There is no "return nil for OK" path.
//   - A stage that returns a non-nil error denies with EG-PIPE-001.
//   - A stage that panics is recovered and denies with EG-PIPE-002.
//   - The sequencer counts explicit allows and compares the count to the number of registered
//     gate stages. Reaching the end without every stage having allowed denies with EG-PIPE-003,
//     which is also what an empty stage list produces.
//   - Stage 7 is not in the loop and is not reachable except through that count.

// stageResult is a stage's disposition. The zero value — allowed false, ruleID empty — is a deny
// that the sequencer normalises onto EG-PIPE-003.
type stageResult struct {
	allowed bool
	ruleID  string
	detail  string
}

// allowResult is the only way to produce an allow.
func allowResult() stageResult {
	return stageResult{allowed: true, ruleID: RuleAllowed}
}

// denyResult is the only way to produce a named deny. An unregistered rule id fails closed onto
// EG-PIPE-003 rather than producing a denial with an id nothing can interpret.
func denyResult(ruleID, detail string) stageResult {
	if !knownRule(ruleID) {
		return stageResult{
			allowed: false,
			ruleID:  RuleNoStageAllowed,
			detail:  joinDetail(sanitizeDetail(detail), "unregistered_rule_id="+quoteForDetail(sanitizeDetail(ruleID))),
		}
	}
	return stageResult{allowed: false, ruleID: ruleID, detail: sanitizeDetail(detail)}
}

// denyResultWithPolicyRule is used where the policy file supplies the rule id (a deny-list entry).
// The pipeline rule id is what is recorded; the policy rule id travels in the detail, because the
// registry is closed and a policy file must not be able to mint pipeline rule identifiers.
func denyResultWithPolicyRule(pipelineRuleID, policyRuleID, detail string) stageResult {
	return denyResult(pipelineRuleID, joinDetail(detail, "policy_rule_id="+quoteForDetail(sanitizeDetail(policyRuleID))))
}

// requestContext is everything the stages see.
//
// It deliberately carries NO field describing where the request came from. FR-015 requires the
// allowlists to be applied identically whether the request originated in the runtime or in a
// command the agent composed, and the way to guarantee that is for the information not to exist.
// TestNoProvenanceField asserts this by reflection.
type requestContext struct {
	Method string
	Path   string // URL path only. The query string is deliberately not recorded: it is
	// attacker-influenceable and is a common carrier of credential-shaped values.
	RawTarget        string // r.RequestURI, the request-target exactly as received
	Query            string
	Header           http.Header
	Proto            string
	ProtoMajor       int
	ProtoMinor       int
	TransferEncoding []string
	ContentLength    int64

	// RawHead is this component's own parse of the bytes of the request head, independent of
	// net/http's. RawHeadAvailable is false when the head could not be recorded, which stage 2
	// treats as a refusal rather than as an absent check.
	RawHead          rawHead
	RawHeadAvailable bool

	CapabilityHandle string
	SessionID        string
	Tier             string
	OperationID      string
	MatchedTemplate  string
	SpecMetadata     string

	Request *http.Request
}

func newRequestContext(r *http.Request) *requestContext {
	path := r.URL.Path
	if path == "" {
		path = "/"
	}
	head, headOK := rawHeadFrom(r.Context())
	return &requestContext{
		RawHead:          head,
		RawHeadAvailable: headOK,
		Method:           r.Method,
		Path:             path,
		RawTarget:        r.RequestURI,
		Query:            r.URL.RawQuery,
		Header:           r.Header,
		Proto:            r.Proto,
		ProtoMajor:       r.ProtoMajor,
		ProtoMinor:       r.ProtoMinor,
		TransferEncoding: r.TransferEncoding,
		ContentLength:    r.ContentLength,
		CapabilityHandle: r.Header.Get(capabilityHeader),
		Tier:             tierUnresolved,
		Request:          r,
	}
}

// Stage is one of the six gate stages.
type Stage interface {
	Name() string
	Evaluate(ctx context.Context, rc *requestContext) (stageResult, error)
}

// FinalStage is stage 7. It is a separate type from Stage because it is not a gate: it is only
// reachable when every gate stage has allowed, and the sequencer cannot loop over it by accident.
type FinalStage interface {
	Name() string
	Deliver(ctx context.Context, w http.ResponseWriter, rc *requestContext) error
}

// Pipeline sequences the seven stages and records every disposition.
type Pipeline struct {
	stages []Stage
	final  FinalStage
	log    DecisionSink
	policy *Policy

	// credentialFingerprint identifies which credential was injected, on records for requests
	// that were re-originated. A truncated SHA-256, never a value.
	credentialFingerprint string
}

// NewPipeline registers the six gate stages in order plus stage 7.
func NewPipeline(stages []Stage, final FinalStage, log DecisionSink, policy *Policy, credFingerprint string) *Pipeline {
	return &Pipeline{
		stages:                stages,
		final:                 final,
		log:                   log,
		policy:                policy,
		credentialFingerprint: credFingerprint,
	}
}

// runGuarded runs one stage under the fail-closed contract. Every abnormal exit becomes a deny.
func runGuarded(ctx context.Context, st Stage, rc *requestContext) (res stageResult) {
	defer func() {
		if r := recover(); r != nil {
			// A panicking stage decided nothing. It denies, and it says which stage.
			res = denyResult(RuleStagePanic, "stage="+quoteForDetail(sanitizeDetail(st.Name())))
		}
	}()

	out, err := st.Evaluate(ctx, rc)
	if err != nil {
		return denyResult(RuleStageError,
			joinDetail("stage="+quoteForDetail(sanitizeDetail(st.Name())), "error="+quoteForDetail(sanitizeDetail(err.Error()))))
	}
	if !out.allowed {
		if !knownRule(out.ruleID) {
			// The zero value, or a stage that named a rule the registry does not contain.
			// Either way the denial stands and it is attributed to EG-PIPE-003, because a
			// denial nothing can interpret is not a denial anyone can act on (FR-011).
			return denyResult(RuleNoStageAllowed,
				joinDetail("stage="+quoteForDetail(sanitizeDetail(st.Name())),
					"unnamed_or_unregistered_deny="+quoteForDetail(sanitizeDetail(out.ruleID))))
		}
		return out
	}
	if out.ruleID == "" {
		out.ruleID = RuleAllowed
	}
	return out
}

// Decide runs the six gate stages. It returns the first deny, or an allow only when every
// registered stage explicitly allowed.
func (p *Pipeline) Decide(ctx context.Context, rc *requestContext) stageResult {
	if len(p.stages) == 0 {
		// An empty pipeline has not evaluated anything, so it cannot have allowed anything.
		return denyResult(RuleNoStageAllowed, "no_stages_registered")
	}
	allowed := 0
	for _, st := range p.stages {
		res := runGuarded(ctx, st, rc)
		if !res.allowed {
			return res
		}
		allowed++
	}
	if allowed != len(p.stages) {
		return denyResult(RuleNoStageAllowed,
			sanitizeDetail(fmt.Sprintf("allowed=%d registered=%d", allowed, len(p.stages))))
	}
	return allowResult()
}

const capabilityHeader = "X-F2A-Capability"

// ServeHTTP is the enforcement point. It decides, records the decision before anything is sent
// (FR-008), and only then re-originates.
func (p *Pipeline) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	rc := newRequestContext(r)

	res := p.Decide(ctx, rc)

	rec := p.record(res, rc, "")
	if err := p.log.Write(ctx, rec); err != nil {
		// An unrecordable decision is not a permitted decision. FR-011 requires the record;
		// failing to write it fails the request closed rather than proceeding unrecorded.
		p.writeDenial(w, denyResult(RuleStageError,
			joinDetail("stage=\"decision-log\"", "error="+quoteForDetail(sanitizeDetail(err.Error())))), rc,
			http.StatusServiceUnavailable)
		return
	}
	if !res.allowed {
		p.writeDenial(w, res, rc, http.StatusForbidden)
		return
	}

	// Stage 7. Reachable only through Decide's allow.
	if err := p.final.Deliver(ctx, w, rc); err != nil {
		follow := classifyDeliveryError(err)
		_ = p.log.Write(ctx, p.record(follow, rc, p.credentialFingerprint))
		// The response may already be partly written; only send a body if it is not.
		p.writeDenial(w, follow, rc, http.StatusBadGateway)
	}
}

// classifyDeliveryError maps a stage-7 failure onto a rule. An address-class refusal is FR-017's
// denial, not a generic upstream failure, and is recorded as such.
func classifyDeliveryError(err error) stageResult {
	var addrErr *AddressClassError
	if errors.As(err, &addrErr) {
		return denyResult(RuleAddressClassDenied,
			joinDetail("class="+quoteForDetail(addrErr.Class), "addr="+quoteForDetail(sanitizeDetail(addrErr.Addr))))
	}
	var tierErr *tierGuardError
	if errors.As(err, &tierErr) {
		return denyResult(RuleTierNotReadOnly, "stage7_guard tier="+quoteForDetail(sanitizeDetail(tierErr.Tier)))
	}
	return denyResult(RuleReoriginationFailed, "error="+quoteForDetail(sanitizeDetail(err.Error())))
}

func (p *Pipeline) record(res stageResult, rc *requestContext, credFingerprint string) DecisionRecord {
	disposition := dispositionDeny
	if res.allowed {
		disposition = dispositionAllow
	}
	policyVersion := ""
	if p.policy != nil {
		policyVersion = p.policy.PolicyVersion
	}
	return newDecisionRecord(res.ruleID, DecisionRecord{
		Disposition:           disposition,
		Method:                sanitizeDetail(rc.Method),
		Path:                  sanitizeDetail(rc.Path),
		ResolvedTier:          rc.Tier,
		SessionID:             rc.SessionID,
		PolicyVersion:         policyVersion,
		Detail:                res.detail,
		AbsoluteHTTPSDenied:   AbsoluteHTTPSDeniedCount(),
		CredentialFingerprint: credFingerprint,
		MatchedTemplate:       sanitizeDetail(rc.MatchedTemplate),
		SpecMetadata:          rc.SpecMetadata,
	})
}

// denialBody is what the agent sees. FR-011 requires a reason legible enough for the agent to find
// a safer path, so the rule, the named reason and the requirement are all returned. Nothing in
// here is derived from a credential.
type denialBody struct {
	Error struct {
		RuleID      string `json:"rule_id"`
		Reason      string `json:"reason"`
		Requirement string `json:"requirement"`
		Detail      string `json:"detail,omitempty"`
		Method      string `json:"method"`
		Path        string `json:"path"`
		Tier        string `json:"resolved_tier"`
	} `json:"error"`
}

func (p *Pipeline) writeDenial(w http.ResponseWriter, res stageResult, rc *requestContext, status int) {
	ruleID := res.ruleID
	if !knownRule(ruleID) {
		ruleID = RuleNoStageAllowed
	}
	var body denialBody
	body.Error.RuleID = ruleID
	body.Error.Reason = ruleReason(ruleID)
	body.Error.Requirement = ruleRequirement(ruleID)
	body.Error.Detail = res.detail
	body.Error.Method = sanitizeDetail(rc.Method)
	body.Error.Path = sanitizeDetail(rc.Path)
	body.Error.Tier = rc.Tier

	payload, err := json.Marshal(body)
	if err != nil {
		payload = []byte(`{"error":{"rule_id":"` + RuleNoStageAllowed + `","reason":"no_stage_allowed"}}`)
	}
	h := w.Header()
	h.Set("Content-Type", "application/json")
	h.Set("X-F2A-Rule-Id", ruleID)
	h.Set("X-F2A-Reason", ruleReason(ruleID))
	w.WriteHeader(status)
	_, _ = w.Write(payload)
}

// stageName is a small helper for the stage types below.
type stageName string

func (s stageName) Name() string { return string(s) }

// headerValues returns the raw, unjoined values for a header key. net/http canonicalises keys, so
// a lookup by canonical key is the whole multimap for that field.
func headerValues(h http.Header, key string) []string {
	if h == nil {
		return nil
	}
	return h[http.CanonicalHeaderKey(key)]
}

func trimAll(in []string) []string {
	out := make([]string, 0, len(in))
	for _, s := range in {
		out = append(out, strings.TrimSpace(s))
	}
	return out
}
