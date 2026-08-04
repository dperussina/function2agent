package main

// The single rule registry (FR-011).
//
// Every disposition the enforcement point produces — allow or deny — names one of these
// identifiers. The registry lives in exactly one file and in exactly one Go map so that the
// invariants suite in tests/invariants/ can read it as data.

// Rule identifiers. Referenced by constant everywhere else in the package so that a typo is a
// compile error rather than an unregistered rule id discovered at run time.
const (
	RuleCapabilityAbsent      = "EG-CAP-001"
	RuleCapabilityNotHonoured = "EG-CAP-002"
	RuleSessionTerminated     = "EG-CAP-003"
	RuleLeaseExpired          = "EG-CAP-004"

	RuleConnectDenied    = "EG-FORM-001"
	RuleUpgradeDenied    = "EG-FORM-002"
	RuleAmbiguousFraming = "EG-FORM-003"
	RuleNonHTTPBytes     = "EG-FORM-004"

	RuleAbsoluteHTTPSDenied          = "EG-DEST-001"
	RuleDestinationNotAllowed        = "EG-DEST-002"
	RuleRequestTargetFormUnsupported = "EG-DEST-003"

	RuleAddressClassDenied = "EG-ADDR-001"

	RuleMethodNotAllowed = "EG-METH-001"

	RuleOperationUnresolvable  = "EG-EFFECT-001"
	RuleKnownSideEffectingRead = "EG-EFFECT-002"
	RuleTierNotReadOnly        = "EG-EFFECT-003"

	RuleReoriginationFailed = "EG-ORIGIN-001"

	RuleStageError     = "EG-PIPE-001"
	RuleStagePanic     = "EG-PIPE-002"
	RuleNoStageAllowed = "EG-PIPE-003"

	RuleAllowed = "EG-ALLOW-000"
)

// Rule is the registry entry: the named reason the egress-policy contract requires, and the
// requirement the rule discharges.
type Rule struct {
	Reason      string
	Requirement string
}

// ruleRegistry is the single source of truth for rule identifiers and their named reasons.
// Keep this map in this file. The invariants suite reads it from source.
var ruleRegistry = map[string]Rule{
	RuleCapabilityAbsent:      {Reason: "capability_absent", Requirement: "FR-050"},
	RuleCapabilityNotHonoured: {Reason: "capability_not_honoured", Requirement: "FR-050"},
	RuleSessionTerminated:     {Reason: "session_terminated", Requirement: "FR-050"},
	RuleLeaseExpired:          {Reason: "lease_expired", Requirement: "FR-050"},

	RuleConnectDenied:    {Reason: "connect_denied", Requirement: "FR-018"},
	RuleUpgradeDenied:    {Reason: "upgrade_denied", Requirement: "FR-018"},
	RuleAmbiguousFraming: {Reason: "ambiguous_framing", Requirement: "FR-018"},
	RuleNonHTTPBytes:     {Reason: "non_http_bytes", Requirement: "FR-018"},

	RuleAbsoluteHTTPSDenied:          {Reason: "absolute_https_denied", Requirement: "FR-018"},
	RuleDestinationNotAllowed:        {Reason: "destination_not_allowed", Requirement: "FR-015"},
	RuleRequestTargetFormUnsupported: {Reason: "request_target_form_unsupported", Requirement: "FR-018"},

	RuleAddressClassDenied: {Reason: "address_class_denied", Requirement: "FR-017"},

	RuleMethodNotAllowed: {Reason: "method_not_allowed", Requirement: "FR-015"},

	RuleOperationUnresolvable:  {Reason: "operation_unresolvable", Requirement: "FR-010"},
	RuleKnownSideEffectingRead: {Reason: "known_side_effecting_read", Requirement: "FR-010"},
	RuleTierNotReadOnly:        {Reason: "tier_not_read_only", Requirement: "FR-009"},

	RuleReoriginationFailed: {Reason: "reorigination_failed", Requirement: "FR-014"},

	RuleStageError:     {Reason: "stage_error_fail_closed", Requirement: "FR-008"},
	RuleStagePanic:     {Reason: "stage_panic_fail_closed", Requirement: "FR-008"},
	RuleNoStageAllowed: {Reason: "no_stage_allowed", Requirement: "FR-008"},

	RuleAllowed: {Reason: "allowed", Requirement: "FR-011"},
}

// knownRule reports whether id is in the registry.
func knownRule(id string) bool {
	_, ok := ruleRegistry[id]
	return ok
}

// ruleReason returns the named reason for id, or the empty string when id is not registered.
// Callers must not construct a disposition from an unregistered id; denyResult and
// newDecisionRecord both fail closed onto EG-PIPE-003 instead.
func ruleReason(id string) string {
	return ruleRegistry[id].Reason
}

// ruleRequirement returns the requirement id the rule discharges.
func ruleRequirement(id string) string {
	return ruleRegistry[id].Requirement
}
