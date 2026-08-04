package main

import (
	"encoding/json"
	"fmt"
	"os"
	"sort"
	"strings"
)

// The versioned policy file (FR-012). Loaded once at startup and never re-read per request:
// re-reading would make the policy in force at the time of a decision unknowable, and FR-012
// requires the operator to be able to review a version before it takes effect.

// policySchemaVersion is the only schema version this build understands. An unknown value fails
// startup rather than being interpreted on a best-effort basis.
const policySchemaVersion = "1.0.0"

// safeMethods is the set of methods that may appear in a method allowlist. FR-009 permits only
// read-only calls, so an allowlist naming a non-safe method is a configuration error.
var safeMethods = map[string]bool{
	"GET":     true,
	"HEAD":    true,
	"OPTIONS": true,
	"TRACE":   true,
}

// Effect tiers. Only tierReadOnly may be permitted (FR-009).
const (
	tierReadOnly        = "read_only"
	tierReversibleWrite = "reversible_write"
	tierIrreversible    = "irreversible"
	tierUnresolved      = "unresolved"
)

// ServedOperation is one entry in the served-operation set (FR-001, resolved against by FR-010).
type ServedOperation struct {
	OperationID  string `json:"operation_id"`
	Method       string `json:"method"`
	PathTemplate string `json:"path_template"`
	Safe         bool   `json:"safe"`
	RuleID       string `json:"rule_id"`
}

// DenyEntry is one entry in the maintained deny list of known side-effecting reads (FR-010).
type DenyEntry struct {
	RuleID        string `json:"rule_id"`
	Method        string `json:"method"`
	PathTemplate  string `json:"path_template"`
	Justification string `json:"justification"`
}

// Policy is the loaded, validated policy file.
type Policy struct {
	SchemaVersion    string            `json:"schema_version"`
	PolicyVersion    string            `json:"policy_version"`
	MethodAllowlist  []string          `json:"method_allowlist"`
	ServedOperations []ServedOperation `json:"served_operations"`
	DenyList         []DenyEntry       `json:"deny_list"`

	methodSet map[string]bool
}

// LoadPolicy reads and validates the policy file at path.
func LoadPolicy(path string) (*Policy, error) {
	raw, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("policy: cannot read %q: %w", path, err)
	}
	return ParsePolicy(raw)
}

// ParsePolicy validates policy bytes. Every failure below is loud: the process does not start.
func ParsePolicy(raw []byte) (*Policy, error) {
	var p Policy
	dec := json.NewDecoder(strings.NewReader(string(raw)))
	dec.DisallowUnknownFields()
	if err := dec.Decode(&p); err != nil {
		return nil, fmt.Errorf("policy: malformed JSON: %w", err)
	}

	if p.SchemaVersion != policySchemaVersion {
		return nil, fmt.Errorf("policy: unknown schema_version %q (this build understands only %q)",
			p.SchemaVersion, policySchemaVersion)
	}
	if strings.TrimSpace(p.PolicyVersion) == "" {
		return nil, fmt.Errorf("policy: policy_version is required and must be non-empty")
	}
	if len(p.MethodAllowlist) == 0 {
		return nil, fmt.Errorf("policy: method_allowlist is required and must be non-empty")
	}

	p.methodSet = make(map[string]bool, len(p.MethodAllowlist))
	for _, m := range p.MethodAllowlist {
		up := strings.ToUpper(strings.TrimSpace(m))
		if up == "" {
			return nil, fmt.Errorf("policy: method_allowlist contains an empty method")
		}
		if !safeMethods[up] {
			// FR-009 permits only read-only calls. An allowlist containing POST is a
			// configuration error, not a policy the operator may express.
			return nil, fmt.Errorf(
				"policy: method_allowlist contains non-safe method %q; FR-009 permits only read-only calls, safe methods are %s",
				up, sortedSafeMethods())
		}
		p.methodSet[up] = true
	}

	seenOps := map[string]bool{}
	for i := range p.ServedOperations {
		op := &p.ServedOperations[i]
		if strings.TrimSpace(op.RuleID) == "" {
			return nil, fmt.Errorf("policy: served_operations[%d] (operation_id %q) has no rule_id", i, op.OperationID)
		}
		if strings.TrimSpace(op.OperationID) == "" {
			return nil, fmt.Errorf("policy: served_operations[%d] has no operation_id", i)
		}
		if strings.TrimSpace(op.Method) == "" {
			return nil, fmt.Errorf("policy: served_operations[%d] (operation_id %q) has no method", i, op.OperationID)
		}
		if err := validatePathTemplate(op.PathTemplate); err != nil {
			return nil, fmt.Errorf("policy: served_operations[%d] (operation_id %q): %w", i, op.OperationID, err)
		}
		op.Method = strings.ToUpper(strings.TrimSpace(op.Method))
		if seenOps[op.OperationID] {
			return nil, fmt.Errorf("policy: duplicate operation_id %q", op.OperationID)
		}
		seenOps[op.OperationID] = true
	}

	for i := range p.DenyList {
		d := &p.DenyList[i]
		if strings.TrimSpace(d.RuleID) == "" {
			return nil, fmt.Errorf("policy: deny_list[%d] (path_template %q) has no rule_id", i, d.PathTemplate)
		}
		if strings.TrimSpace(d.Method) == "" {
			return nil, fmt.Errorf("policy: deny_list[%d] has no method", i)
		}
		if err := validatePathTemplate(d.PathTemplate); err != nil {
			return nil, fmt.Errorf("policy: deny_list[%d]: %w", i, err)
		}
		d.Method = strings.ToUpper(strings.TrimSpace(d.Method))
		// A deny-list entry carries its own rule id, so it must not collide with a pipeline
		// rule id: a denial must be attributable to exactly one rule.
		if knownRule(d.RuleID) {
			return nil, fmt.Errorf("policy: deny_list[%d] rule_id %q collides with a pipeline rule identifier", i, d.RuleID)
		}
	}

	return &p, nil
}

func sortedSafeMethods() string {
	out := make([]string, 0, len(safeMethods))
	for m := range safeMethods {
		out = append(out, m)
	}
	sort.Strings(out)
	return strings.Join(out, ", ")
}

func validatePathTemplate(t string) error {
	if t == "" {
		return fmt.Errorf("path_template is required")
	}
	if !strings.HasPrefix(t, "/") {
		return fmt.Errorf("path_template %q must begin with %q", t, "/")
	}
	for _, seg := range strings.Split(strings.TrimPrefix(t, "/"), "/") {
		if strings.HasPrefix(seg, "{") != strings.HasSuffix(seg, "}") {
			return fmt.Errorf("path_template %q has a malformed parameter segment %q", t, seg)
		}
		if seg == "{}" {
			return fmt.Errorf("path_template %q has an unnamed parameter segment", t)
		}
	}
	return nil
}

// MethodAllowed reports whether method is in the allowlist. The comparison is on the method token
// exactly as received, upper-cased; HTTP methods are case-sensitive, so a lower-case "get" is not
// the safe method GET and is not allowed.
func (p *Policy) MethodAllowed(method string) bool {
	return p.methodSet[method]
}

// matchPathTemplate reports whether path matches template. A "{param}" segment matches exactly one
// non-empty segment. A template never matches a path with a different segment count: without that
// rule "/orders/{id}" would match "/orders/1/resend-receipt" and the deny list would be bypassed by
// appending a segment.
func matchPathTemplate(template, path string) bool {
	if template == "" || path == "" {
		return false
	}
	if !strings.HasPrefix(template, "/") || !strings.HasPrefix(path, "/") {
		return false
	}
	tSegs := strings.Split(strings.TrimPrefix(template, "/"), "/")
	pSegs := strings.Split(strings.TrimPrefix(path, "/"), "/")
	if len(tSegs) != len(pSegs) {
		return false
	}
	for i, t := range tSegs {
		if strings.HasPrefix(t, "{") && strings.HasSuffix(t, "}") && len(t) > 2 {
			if pSegs[i] == "" {
				return false
			}
			continue
		}
		if t != pSegs[i] {
			return false
		}
	}
	return true
}

// MatchOperation returns the served operation matching method and path, or nil.
func (p *Policy) MatchOperation(method, path string) *ServedOperation {
	for i := range p.ServedOperations {
		op := &p.ServedOperations[i]
		if op.Method == method && matchPathTemplate(op.PathTemplate, path) {
			return op
		}
	}
	return nil
}

// MatchDenyEntry returns the deny-list entry matching method and path, or nil.
func (p *Policy) MatchDenyEntry(method, path string) *DenyEntry {
	for i := range p.DenyList {
		d := &p.DenyList[i]
		if d.Method == method && matchPathTemplate(d.PathTemplate, path) {
			return d
		}
	}
	return nil
}
