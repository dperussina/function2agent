package main

import (
	"context"
	"strings"
	"testing"
)

// Stages 5 and 6 — effect (T088, T089; FR-008, FR-009, FR-010).

func TestPathTemplateMatching(t *testing.T) {
	cases := []struct {
		template, path string
		want           bool
	}{
		{"/orders", "/orders", true},
		{"/orders/{id}", "/orders/1", true},
		{"/orders/{id}", "/orders/abc-def", true},
		{"/orders/{id}/export", "/orders/1/export", true},

		// A template must not match a path with a different segment count. Without this rule
		// "/orders/{id}" matches "/orders/1/resend-receipt" and the deny list is bypassed by
		// appending a segment.
		{"/orders/{id}", "/orders/1/resend-receipt", false},
		{"/orders/{id}", "/orders", false},
		{"/orders/{id}", "/orders/", false},
		{"/orders", "/orders/1", false},
		{"/orders/{id}", "/invoices/1", false},
		{"/orders/{id}/export", "/orders/1/EXPORT", false},
		{"/orders/{id}", "orders/1", false},
	}
	for _, tc := range cases {
		if got := matchPathTemplate(tc.template, tc.path); got != tc.want {
			t.Errorf("matchPathTemplate(%q, %q) = %v, want %v", tc.template, tc.path, got, tc.want)
		}
	}
}

func TestEffectResolution(t *testing.T) {
	policy := mustTestPolicy(t)

	cases := []struct {
		name     string
		method   string
		path     string
		wantTier string
		wantOp   string
	}{
		{"served_safe_get", "GET", "/orders/1", tierReadOnly, "getOrder"},
		{"served_safe_collection", "GET", "/orders", tierReadOnly, "listOrders"},
		{"served_safe_head", "HEAD", "/orders/1", tierReadOnly, "headOrder"},
		{"served_not_safe_flag", "GET", "/orders/1/export", tierReversibleWrite, "getOrderExport"},
		{"deny_listed_read", "GET", "/orders/1/resend-receipt", tierReversibleWrite, ""},
		{"not_served", "GET", "/customers/1", tierUnresolved, ""},
		{"served_path_wrong_method", "DELETE", "/orders/1", tierUnresolved, ""},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got := resolveEffect(policy, tc.method, tc.path)
			if got.Tier != tc.wantTier {
				t.Fatalf("tier = %q, want %q", got.Tier, tc.wantTier)
			}
			if got.OperationID != tc.wantOp {
				t.Fatalf("operation = %q, want %q", got.OperationID, tc.wantOp)
			}
		})
	}
}

func TestStageFiveDeniesEverythingNotReadOnly(t *testing.T) {
	policy := mustTestPolicy(t)
	stage := NewEffectStage(policy)

	cases := []struct {
		name     string
		method   string
		path     string
		allowed  bool
		wantRule string
		wantTier string
	}{
		{name: "read_only_allowed", method: "GET", path: "/orders/1", allowed: true, wantTier: tierReadOnly},
		{name: "known_side_effecting_read", method: "GET", path: "/orders/1/resend-receipt", wantRule: RuleKnownSideEffectingRead, wantTier: tierReversibleWrite},
		{name: "not_marked_safe", method: "GET", path: "/orders/1/export", wantRule: RuleTierNotReadOnly, wantTier: tierReversibleWrite},
		// Unresolved is left for stage 6, which is the stage that names it.
		{name: "unresolved_deferred_to_stage_six", method: "GET", path: "/nope", allowed: true, wantTier: tierUnresolved},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			rc := &requestContext{Method: tc.method, Path: tc.path, Tier: tierUnresolved}
			res, err := stage.Evaluate(context.Background(), rc)
			if err != nil {
				t.Fatal(err)
			}
			want := tc.wantRule
			if tc.allowed {
				want = RuleAllowed
			}
			assertResult(t, res, tc.allowed, want)
			if rc.Tier != tc.wantTier {
				t.Fatalf("resolved tier on the context = %q, want %q", rc.Tier, tc.wantTier)
			}
			if tc.wantRule == RuleKnownSideEffectingRead && !strings.Contains(res.detail, "DENY-SER-001") {
				t.Fatalf("the deny-list entry's own rule id must reach the record: %q", res.detail)
			}
		})
	}
}

func TestStageSixDeniesUnresolvedRatherThanGuessing(t *testing.T) {
	stage := NewUnresolvableStage()
	cases := []struct {
		tier     string
		allowed  bool
		wantRule string
	}{
		{tier: tierReadOnly, allowed: true},
		{tier: tierUnresolved, wantRule: RuleOperationUnresolvable},
		{tier: tierReversibleWrite, wantRule: RuleTierNotReadOnly},
		{tier: tierIrreversible, wantRule: RuleTierNotReadOnly},
		{tier: "", wantRule: RuleTierNotReadOnly},
	}
	for _, tc := range cases {
		t.Run("tier_"+tc.tier, func(t *testing.T) {
			rc := &requestContext{Method: "GET", Path: "/orders/1", Tier: tc.tier}
			res, err := stage.Evaluate(context.Background(), rc)
			if err != nil {
				t.Fatal(err)
			}
			want := tc.wantRule
			if tc.allowed {
				want = RuleAllowed
			}
			assertResult(t, res, tc.allowed, want)
		})
	}
}

// TestEffectResolutionBlocksBeforeAnythingIsSent is FR-008: the disposition is decided before the
// call reaches the target. Asserted by the upstream never having been contacted.
func TestEffectResolutionBlocksBeforeAnythingIsSent(t *testing.T) {
	for _, path := range []string{"/orders/1/resend-receipt", "/orders/1/export", "/not-served"} {
		h := newHarness(t, harnessOpts{})
		resp := h.do("GET", path, map[string]string{capabilityHeader: testHandle})
		rule := ruleOf(t, resp)
		if h.Capture.count() != 0 {
			t.Fatalf("%s reached the upstream although it was denied with %s", path, rule)
		}
		dialled, _ := h.Dialer.calls()
		if dialled != 0 {
			t.Fatalf("%s caused an outbound dial although it was denied with %s", path, rule)
		}
		if !knownRule(rule) {
			t.Fatalf("%s denied with %q which is not in the registry", path, rule)
		}
	}
}

// TestNothingEscalatesToAHuman: FR-009 forbids escalation during a session. There is no code path
// that can produce anything other than allow or deny, and the response is one of exactly two
// shapes. Asserted over every disposition the suite's own probes produce.
func TestNothingEscalatesToAHuman(t *testing.T) {
	h := newHarness(t, harnessOpts{})
	probes := [][2]string{
		{"GET", "/orders/1"},
		{"POST", "/orders/1"},
		{"GET", "/orders/1/resend-receipt"},
		{"GET", "/orders/1/export"},
		{"GET", "/nope"},
	}
	for _, p := range probes {
		resp := h.do(p[0], p[1], map[string]string{capabilityHeader: testHandle})
		code := resp.StatusCode
		resp.Body.Close()
		if code == 202 || code == 401 || code == 407 {
			t.Fatalf("%s %s returned %d, which is neither an allow nor a denial", p[0], p[1], code)
		}
		if code != 200 && code != 403 {
			t.Fatalf("%s %s returned %d; the only dispositions are 200 and 403", p[0], p[1], code)
		}
	}
}
