package main

import (
	"context"
	"testing"
)

// Stage 3 — destination (T086, T-09, Q-07).

func testOrigin() PinnedOrigin {
	return PinnedOrigin{Scheme: "https", Host: "api.example.com", Port: "443"}
}

func TestDestinationStage(t *testing.T) {
	origin := testOrigin()

	cases := []struct {
		name     string
		target   string
		allowed  bool
		wantRule string
	}{
		{name: "origin_form_path", target: "/orders/1", allowed: true},
		{name: "origin_form_root", target: "/", allowed: true},
		{name: "origin_form_with_query", target: "/orders?page=2", allowed: true},

		// T-09 part 2: an absolute-form http target naming the pinned origin is accepted, so a
		// URL echoed out of a response body still works.
		{name: "absolute_http_pinned_origin", target: "http://api.example.com:443/orders/2", allowed: true},
		{name: "absolute_http_pinned_origin_case_insensitive_host", target: "http://API.EXAMPLE.COM:443/orders/2", allowed: true},

		// T-09 part 3 and the Q-07 instrument.
		{name: "absolute_https_pinned_origin", target: "https://api.example.com:443/orders/2", wantRule: RuleAbsoluteHTTPSDenied},
		{name: "absolute_https_other_host", target: "https://evil.example.net/x", wantRule: RuleAbsoluteHTTPSDenied},

		{name: "absolute_http_other_host", target: "http://evil.example.net:80/x", wantRule: RuleDestinationNotAllowed},
		{name: "absolute_http_right_host_wrong_port", target: "http://api.example.com:8443/x", wantRule: RuleDestinationNotAllowed},
		{name: "absolute_http_implicit_port_80", target: "http://api.example.com/orders/2", wantRule: RuleDestinationNotAllowed},
		{name: "absolute_other_scheme", target: "ftp://api.example.com:443/x", wantRule: RuleDestinationNotAllowed},
		{name: "absolute_file_scheme", target: "file:///etc/passwd", wantRule: RuleDestinationNotAllowed},

		{name: "authority_form", target: "api.example.com:443", wantRule: RuleRequestTargetFormUnsupported},
		{name: "asterisk_form", target: "*", wantRule: RuleRequestTargetFormUnsupported},
		{name: "empty_target", target: "", wantRule: RuleRequestTargetFormUnsupported},
		{name: "protocol_relative", target: "//evil.example.net/x", wantRule: RuleRequestTargetFormUnsupported},
		{name: "absolute_with_userinfo", target: "http://u:p@api.example.com:443/x", wantRule: RuleRequestTargetFormUnsupported},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			want := tc.wantRule
			if tc.allowed {
				want = RuleAllowed
			}
			assertResult(t, checkDestination(tc.target, origin), tc.allowed, want)
		})
	}
}

// TestAbsoluteHTTPSCounter is the Q-07 instrument. The counter is what makes "does this reason
// dominate real traffic?" answerable, so it is asserted to move exactly once per denial and to
// appear on the decision record.
func TestAbsoluteHTTPSCounter(t *testing.T) {
	resetAbsoluteHTTPSDeniedCount()
	if got := AbsoluteHTTPSDeniedCount(); got != 0 {
		t.Fatalf("counter did not reset: %d", got)
	}

	origin := testOrigin()
	stage := NewDestinationStage(origin)

	// Denials that are not absolute-https must not move it.
	for _, target := range []string{"/orders/1", "http://evil.example.net:80/x", "*"} {
		_, _ = stage.Evaluate(context.Background(), &requestContext{RawTarget: target})
	}
	if got := AbsoluteHTTPSDeniedCount(); got != 0 {
		t.Fatalf("counter moved on an unrelated denial: %d", got)
	}

	for i := 1; i <= 3; i++ {
		res, _ := stage.Evaluate(context.Background(), &requestContext{RawTarget: "https://api.example.com:443/orders/1"})
		assertResult(t, res, false, RuleAbsoluteHTTPSDenied)
		if got := AbsoluteHTTPSDeniedCount(); got != uint64(i) {
			t.Fatalf("after %d denials the counter is %d", i, got)
		}
	}

	// And it reaches the decision record.
	sink := &recordingSink{}
	p := NewPipeline([]Stage{stage}, &countingFinal{stageName: "final"}, sink, mustTestPolicy(t), "")
	rec := httptestRecorder()
	p.ServeHTTP(rec, mustRequest(t, "GET", "https://api.example.com:443/orders/1"))
	last, ok := sink.last()
	if !ok {
		t.Fatal("no decision recorded")
	}
	if last.RuleID() != RuleAbsoluteHTTPSDenied {
		t.Fatalf("rule = %q", last.RuleID())
	}
	if last.AbsoluteHTTPSDenied != AbsoluteHTTPSDeniedCount() || last.AbsoluteHTTPSDenied == 0 {
		t.Fatalf("record carries counter %d, accessor says %d", last.AbsoluteHTTPSDenied, AbsoluteHTTPSDeniedCount())
	}
	resetAbsoluteHTTPSDeniedCount()
}

// TestDependencyFetchIsDeniedByStageThree is FR-021 discharged by the same control: a package
// index is a destination that is not the target.
func TestDependencyFetchIsDeniedByStageThree(t *testing.T) {
	origin := testOrigin()
	for _, target := range []string{
		"https://pypi.org/simple/requests/",
		"http://registry.npmjs.org:80/left-pad",
		"http://proxy.golang.org:80/modernc.org/sqlite/@v/list",
	} {
		res := checkDestination(target, origin)
		if res.allowed {
			t.Fatalf("%s was allowed; FR-021 relies on stage 3 denying it", target)
		}
		if !knownRule(res.ruleID) {
			t.Fatalf("%s denied with unregistered rule %q", target, res.ruleID)
		}
	}
}
