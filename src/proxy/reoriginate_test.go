package main

import (
	"crypto/x509"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

// Stage 7 — re-origination (T091, OD-12).

func TestReoriginationHappyPath(t *testing.T) {
	h := newHarness(t, harnessOpts{})
	resp := h.do("GET", "/orders/1", map[string]string{capabilityHeader: testHandle})
	body := readAllString(t, resp)

	if resp.StatusCode != 200 {
		t.Fatalf("status = %d, body %s", resp.StatusCode, body)
	}
	if !strings.Contains(body, `"upstream":"ok"`) {
		t.Fatalf("body was not the upstream's: %s", body)
	}
	if h.Capture.count() != 1 {
		t.Fatalf("upstream saw %d requests", h.Capture.count())
	}
	dialled, asked := h.Dialer.calls()
	if dialled != 1 {
		t.Fatalf("dialled %d times", dialled)
	}
	// The transport asks for the pinned origin's authority; the dialer is what decides where
	// the packets go, and in production it ignores this and dials F2A_PROXY_UPSTREAM_ADDR.
	if len(asked) != 1 || asked[0] != "example.com:443" {
		t.Fatalf("transport asked to dial %v", asked)
	}
}

func TestCredentialInjectedAndCapabilityStripped(t *testing.T) {
	h := newHarness(t, harnessOpts{})
	resp := h.do("GET", "/orders/1", map[string]string{
		capabilityHeader:  testHandle,
		testCredentialHdr: "attacker-chosen-credential",
		"X-Harmless":      "kept",
	})
	resp.Body.Close()

	up := h.Capture.lastHeader()
	if up == nil {
		t.Fatal("upstream received nothing")
	}
	if got := up.Get(testCredentialHdr); got != testCredentialValue {
		t.Fatalf("credential header = %q, want the operator's credential", got)
	}
	if len(up.Values(testCredentialHdr)) != 1 {
		t.Fatalf("credential header appears %d times; the inbound one must be stripped, not appended to",
			len(up.Values(testCredentialHdr)))
	}
	if got := up.Get(capabilityHeader); got != "" {
		t.Fatalf("the capability handle escaped the enforcement boundary: %q", got)
	}
	if got := up.Get("X-Harmless"); got != "kept" {
		t.Fatalf("ordinary headers must be forwarded, got %q", got)
	}
}

func TestNoResponseBodyRewriting(t *testing.T) {
	// A response body full of absolute URLs at the target's real origin. Rewriting them would
	// be a content transformation on untrusted bytes at the enforcement point; OD-12 rejects it.
	const payload = `{"next":"https://api.example.com/orders?page=2","self":"https://api.example.com/orders?page=1"}`
	h := newHarness(t, harnessOpts{
		UpstreamHandler: func(w http.ResponseWriter, r *http.Request) {
			w.Header().Set("Content-Type", "application/json")
			w.Header().Set("Link", `<https://api.example.com/orders?page=2>; rel="next"`)
			_, _ = io.WriteString(w, payload)
		},
	})
	resp := h.do("GET", "/orders", map[string]string{capabilityHeader: testHandle})
	body := readAllString(t, resp)
	if body != payload {
		t.Fatalf("the body was transformed:\n got %s\nwant %s", body, payload)
	}
	if got := resp.Header.Get("Link"); !strings.Contains(got, "https://api.example.com/orders?page=2") {
		t.Fatalf("the Link header was transformed: %q", got)
	}
}

func TestCertificateValidationIsOrdinary(t *testing.T) {
	// The same upstream, but with no trust anchor supplied: validation must fail rather than be
	// skipped. InsecureSkipVerify appears nowhere in this component.
	upstream := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(200)
	}))
	defer upstream.Close()

	reo := NewReoriginator(ReoriginatorConfig{
		Origin:           PinnedOrigin{Scheme: "https", Host: "example.com", Port: "443"},
		CredentialHeader: testCredentialHdr,
		Credential:       NewSecret(testCredentialValue),
		Dialer:           &stubDialer{target: strings.TrimPrefix(upstream.URL, "https://")},
		RootCAs:          x509.NewCertPool(), // deliberately empty
		Timeout:          5 * time.Second,
	})
	rc := &requestContext{Method: "GET", Path: "/orders/1", Tier: tierReadOnly}
	err := reo.Deliver(t.Context(), httptestRecorder(), rc)
	if err == nil {
		t.Fatal("an untrusted certificate must fail the handshake")
	}
	assertResult(t, classifyDeliveryError(err), false, RuleReoriginationFailed)
	if strings.Contains(err.Error(), testCredentialValue) {
		t.Fatal("the error leaked the credential")
	}
}

func TestRedirectsAreNotFollowed(t *testing.T) {
	h := newHarness(t, harnessOpts{
		UpstreamHandler: func(w http.ResponseWriter, r *http.Request) {
			http.Redirect(w, r, "https://elsewhere.example.net/x", http.StatusFound)
		},
	})
	resp := h.do("GET", "/orders/1", map[string]string{capabilityHeader: testHandle})
	resp.Body.Close()
	if resp.StatusCode != http.StatusFound {
		t.Fatalf("status = %d, want the redirect returned verbatim", resp.StatusCode)
	}
	if h.Capture.count() != 1 {
		t.Fatalf("upstream saw %d requests; the redirect must not have been followed", h.Capture.count())
	}
}

func TestUpstreamFailureIsRecordedAsAReoriginationDenial(t *testing.T) {
	h := newHarness(t, harnessOpts{UseRealDecisionLog: true})
	// Point the stub dialer at a closed port.
	h.Dialer.target = "127.0.0.1:1"

	resp := h.do("GET", "/orders/1", map[string]string{capabilityHeader: testHandle})
	resp.Body.Close()
	if resp.StatusCode != http.StatusBadGateway {
		t.Fatalf("status = %d, want 502", resp.StatusCode)
	}
	n, err := h.Log.Count(t.Context(), RuleReoriginationFailed)
	if err != nil {
		t.Fatal(err)
	}
	if n != 1 {
		t.Fatalf("EG-ORIGIN-001 records = %d, want 1", n)
	}
}

func TestHopByHopHeadersNotForwarded(t *testing.T) {
	h := newHarness(t, harnessOpts{})
	resp := h.do("GET", "/orders/1", map[string]string{
		capabilityHeader:      testHandle,
		"Proxy-Authorization": "Basic Zm9v",
		"X-Custom-Hop":        "should-be-dropped",
		"Connection":          "X-Custom-Hop",
	})
	resp.Body.Close()
	up := h.Capture.lastHeader()
	for _, k := range []string{"Proxy-Authorization", "X-Custom-Hop"} {
		if v := up.Get(k); v != "" {
			t.Fatalf("hop-by-hop header %s was forwarded: %q", k, v)
		}
	}
}
