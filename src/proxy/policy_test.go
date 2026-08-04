package main

import (
	"strings"
	"testing"
)

// The versioned policy file (FR-012). Every one of these must fail startup rather than be
// interpreted on a best-effort basis.

func TestPolicyLoadsAndValidates(t *testing.T) {
	p, err := ParsePolicy([]byte(testPolicyJSON))
	if err != nil {
		t.Fatalf("valid policy must parse: %v", err)
	}
	if p.PolicyVersion != "2026-08-03.1" {
		t.Fatalf("policy_version = %q", p.PolicyVersion)
	}
	if !p.MethodAllowed("GET") || !p.MethodAllowed("HEAD") {
		t.Fatal("allowlist not honoured")
	}
	if p.MethodAllowed("POST") || p.MethodAllowed("get") {
		t.Fatal("allowlist too permissive")
	}
}

func TestPolicyRejectsBadConfiguration(t *testing.T) {
	cases := []struct {
		name    string
		body    string
		wantSub string
	}{
		{
			name: "served_operation_without_rule_id",
			body: `{"schema_version":"1.0.0","policy_version":"v1","method_allowlist":["GET"],
			        "served_operations":[{"operation_id":"getOrder","method":"GET","path_template":"/orders/{id}","safe":true}],
			        "deny_list":[]}`,
			wantSub: "has no rule_id",
		},
		{
			name: "deny_entry_without_rule_id",
			body: `{"schema_version":"1.0.0","policy_version":"v1","method_allowlist":["GET"],
			        "served_operations":[],
			        "deny_list":[{"method":"GET","path_template":"/x","justification":"j"}]}`,
			wantSub: "has no rule_id",
		},
		{
			name:    "unknown_schema_version",
			body:    `{"schema_version":"2.0.0","policy_version":"v1","method_allowlist":["GET"],"served_operations":[],"deny_list":[]}`,
			wantSub: "unknown schema_version",
		},
		{
			name:    "missing_schema_version",
			body:    `{"policy_version":"v1","method_allowlist":["GET"],"served_operations":[],"deny_list":[]}`,
			wantSub: "unknown schema_version",
		},
		{
			name:    "allowlist_contains_post",
			body:    `{"schema_version":"1.0.0","policy_version":"v1","method_allowlist":["GET","POST"],"served_operations":[],"deny_list":[]}`,
			wantSub: "non-safe method",
		},
		{
			name:    "allowlist_contains_delete",
			body:    `{"schema_version":"1.0.0","policy_version":"v1","method_allowlist":["DELETE"],"served_operations":[],"deny_list":[]}`,
			wantSub: "non-safe method",
		},
		{
			name:    "empty_allowlist",
			body:    `{"schema_version":"1.0.0","policy_version":"v1","method_allowlist":[],"served_operations":[],"deny_list":[]}`,
			wantSub: "method_allowlist is required",
		},
		{
			name:    "empty_policy_version",
			body:    `{"schema_version":"1.0.0","policy_version":"","method_allowlist":["GET"],"served_operations":[],"deny_list":[]}`,
			wantSub: "policy_version is required",
		},
		{
			name: "path_template_not_absolute",
			body: `{"schema_version":"1.0.0","policy_version":"v1","method_allowlist":["GET"],
			        "served_operations":[{"operation_id":"o","method":"GET","path_template":"orders","safe":true,"rule_id":"R"}],
			        "deny_list":[]}`,
			wantSub: "must begin with",
		},
		{
			name: "deny_entry_rule_id_collides_with_pipeline_rule",
			body: `{"schema_version":"1.0.0","policy_version":"v1","method_allowlist":["GET"],
			        "served_operations":[],
			        "deny_list":[{"rule_id":"EG-EFFECT-002","method":"GET","path_template":"/x","justification":"j"}]}`,
			wantSub: "collides",
		},
		{
			name: "duplicate_operation_id",
			body: `{"schema_version":"1.0.0","policy_version":"v1","method_allowlist":["GET"],
			        "served_operations":[
			          {"operation_id":"o","method":"GET","path_template":"/a","safe":true,"rule_id":"R1"},
			          {"operation_id":"o","method":"GET","path_template":"/b","safe":true,"rule_id":"R2"}],
			        "deny_list":[]}`,
			wantSub: "duplicate operation_id",
		},
		{
			name:    "unknown_field",
			body:    `{"schema_version":"1.0.0","policy_version":"v1","method_allowlist":["GET"],"served_operations":[],"deny_list":[],"escape_hatch":true}`,
			wantSub: "malformed JSON",
		},
		{
			name:    "not_json",
			body:    `not json at all`,
			wantSub: "malformed JSON",
		},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			_, err := ParsePolicy([]byte(tc.body))
			if err == nil {
				t.Fatalf("policy must be rejected")
			}
			if !strings.Contains(err.Error(), tc.wantSub) {
				t.Fatalf("error %q does not mention %q", err, tc.wantSub)
			}
		})
	}
}

// TestPolicyLoadedOnceNeverRereadPerRequest: the policy in force is fixed at startup, so a
// decision record's policy_version is the version that actually decided it. Overwriting the file
// under a running proxy changes nothing until it restarts.
func TestPolicyLoadedOnceNeverRereadPerRequest(t *testing.T) {
	path := writePolicyFile(t, testPolicyJSON)
	p, err := LoadPolicy(path)
	if err != nil {
		t.Fatalf("load: %v", err)
	}
	h := newHarness(t, harnessOpts{Policy: p})

	resp := h.do("GET", "/orders/1", map[string]string{capabilityHeader: testHandle})
	resp.Body.Close()
	if resp.StatusCode != 200 {
		t.Fatalf("expected the read to be allowed, got %d", resp.StatusCode)
	}

	// Widen the file on disk to permit DELETE. FR-019 makes widening an operator action; it is
	// not something that takes effect because a file changed.
	widened := strings.Replace(testPolicyJSON, `"method_allowlist": ["GET", "HEAD"]`,
		`"method_allowlist": ["GET", "HEAD", "OPTIONS"]`, 1)
	if err := writeOver(path, widened); err != nil {
		t.Fatalf("rewrite policy: %v", err)
	}

	resp2 := h.do("OPTIONS", "/orders/1", map[string]string{capabilityHeader: testHandle})
	rule := ruleOf(t, resp2)
	if rule != RuleMethodNotAllowed {
		t.Fatalf("the running proxy re-read the policy file: rule = %q", rule)
	}
}

func writeOver(path, body string) error {
	return osWriteFile(path, body)
}
