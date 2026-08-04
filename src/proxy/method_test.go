package main

import (
	"net/http"
	"testing"
)

// Stage 4 — method, evaluated together with the destination (T087, FR-015).

func TestMethodAndDestinationEvaluatedTogether(t *testing.T) {
	origin := testOrigin()
	policy := mustTestPolicy(t) // allowlist is GET, HEAD

	cases := []struct {
		name     string
		method   string
		target   string
		allowed  bool
		wantRule string
	}{
		{name: "allowed_method_pinned_destination", method: "GET", target: "/orders/1", allowed: true},
		{name: "allowed_method_pinned_destination_head", method: "HEAD", target: "/orders/1", allowed: true},
		{name: "allowed_method_absolute_pinned", method: "GET", target: "http://api.example.com:443/orders/1", allowed: true},

		// A permitted method to a non-pinned destination is denied.
		{name: "allowed_method_other_host", method: "GET", target: "http://evil.example.net:80/x", wantRule: RuleDestinationNotAllowed},
		{name: "allowed_method_absolute_https", method: "GET", target: "https://api.example.com:443/x", wantRule: RuleAbsoluteHTTPSDenied},
		{name: "allowed_method_authority_form", method: "GET", target: "api.example.com:443", wantRule: RuleRequestTargetFormUnsupported},

		// A non-permitted method to the pinned destination is denied.
		{name: "denied_method_pinned_destination", method: "POST", target: "/orders/1", wantRule: RuleMethodNotAllowed},
		{name: "delete_pinned_destination", method: "DELETE", target: "/orders/1", wantRule: RuleMethodNotAllowed},
		{name: "options_not_in_allowlist", method: "OPTIONS", target: "/orders/1", wantRule: RuleMethodNotAllowed},
		{name: "lowercase_get_is_not_GET", method: "get", target: "/orders/1", wantRule: RuleMethodNotAllowed},

		// Both wrong: the destination is reported, because it is evaluated first in the same
		// predicate and there is no path that reaches the method check with a bad destination.
		{name: "denied_method_and_destination", method: "POST", target: "http://evil.example.net:80/x", wantRule: RuleDestinationNotAllowed},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			resetAbsoluteHTTPSDeniedCount()
			want := tc.wantRule
			if tc.allowed {
				want = RuleAllowed
			}
			assertResult(t, checkMethodAndDestination(tc.method, tc.target, origin, policy), tc.allowed, want)
		})
	}
}

// TestMethodStageWithNoPolicyDenies: no allowlist permits nothing.
func TestMethodStageWithNoPolicyDenies(t *testing.T) {
	assertResult(t, checkMethodAndDestination("GET", "/orders/1", testOrigin(), nil), false, RuleMethodNotAllowed)
}

// TestIdenticalDispositionRegardlessOfApparentProvenance is FR-015's second clause. The same
// method and target must be decided identically however the request is dressed up to look as
// though it came from the runtime rather than from a command the agent composed.
func TestIdenticalDispositionRegardlessOfApparentProvenance(t *testing.T) {
	provenanceDisguises := []map[string]string{
		{},
		{"User-Agent": "f2a-runtime/1.0"},
		{"User-Agent": "curl/8.0.1"},
		{"X-F2A-Origin": "runtime"},
		{"X-F2A-Origin": "agent-command"},
		{"X-Forwarded-For": "10.0.0.1"},
		{"Via": "1.1 f2a-runtime"},
		{"X-Requested-With": "shell"},
	}

	probes := []struct {
		method, target string
	}{
		{"GET", "/orders/1"},
		{"POST", "/orders/1"},
		{"GET", "/orders/1/resend-receipt"},
		{"GET", "/not-served"},
		{"GET", "https://api.example.com:443/orders/1"},
	}

	for _, probe := range probes {
		var baselineRule string
		var baselineStatus int
		for i, disguise := range provenanceDisguises {
			h := newHarness(t, harnessOpts{})
			hdr := map[string]string{capabilityHeader: testHandle}
			for k, v := range disguise {
				hdr[k] = v
			}
			resp := h.do(probe.method, probe.target, hdr)
			status := resp.StatusCode
			rule := resp.Header.Get("X-F2A-Rule-Id")
			resp.Body.Close()

			if i == 0 {
				baselineRule, baselineStatus = rule, status
				continue
			}
			if rule != baselineRule || status != baselineStatus {
				t.Fatalf("%s %s decided differently under headers %v: rule %q/%q status %d/%d",
					probe.method, probe.target, disguise, rule, baselineRule, status, baselineStatus)
			}
		}
	}
	_ = http.MethodGet
}
