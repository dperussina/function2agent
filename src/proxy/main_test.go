package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"net/http"
	"net/netip"
	"os"
	"reflect"
	"regexp"
	"strings"
	"sync"
	"testing"
)

// ---------------------------------------------------------------------------
// Suite-wide invariant: every disposition produced anywhere carries a registered rule id
// ---------------------------------------------------------------------------

var (
	observedMu        sync.Mutex
	observedDecisions []DecisionRecord
)

// TestMain installs an observer that every decision written through a sink, and every denial
// asserted through assertResult, passes through. After the whole suite has run it asserts the
// FR-011 invariant over all of them at once, which is the only way to make the claim about
// "every denial produced anywhere in the suite" rather than about the ones a single test looked at.
func TestMain(m *testing.M) {
	setDecisionObserver(func(rec DecisionRecord) {
		observedMu.Lock()
		observedDecisions = append(observedDecisions, rec)
		observedMu.Unlock()
	})

	code := m.Run()

	observedMu.Lock()
	all := observedDecisions
	observedMu.Unlock()

	if code == 0 {
		// The vacuity guard applies to a full run. Under -run it would fire on any subset that
		// happens to produce no dispositions, which would make partial runs useless.
		filtered := false
		if f := flag.Lookup("test.run"); f != nil && f.Value.String() != "" {
			filtered = true
		}
		if len(all) == 0 && !filtered {
			fmt.Fprintln(os.Stderr, "FR-011 invariant check is vacuous: no dispositions were observed")
			code = 1
		}
		bad := 0
		for i, rec := range all {
			if rec.RuleID() == "" {
				fmt.Fprintf(os.Stderr, "FR-011 violation: disposition %d has an empty rule identifier: %+v\n", i, rec)
				bad++
				continue
			}
			if !knownRule(rec.RuleID()) {
				fmt.Fprintf(os.Stderr, "FR-011 violation: disposition %d carries unregistered rule id %q\n", i, rec.RuleID())
				bad++
			}
			if rec.Reason == "" {
				fmt.Fprintf(os.Stderr, "FR-011 violation: disposition %d (%s) has no named reason\n", i, rec.RuleID())
				bad++
			}
		}
		if bad > 0 {
			code = 1
		} else {
			fmt.Fprintf(os.Stderr, "FR-011 invariant: %d dispositions observed, all carry a registered rule id and a named reason\n", len(all))
		}
	}
	os.Exit(code)
}

// ---------------------------------------------------------------------------
// The credential never appears anywhere
// ---------------------------------------------------------------------------

func testConfigWithCredential() Config {
	return Config{
		Listen:           "127.0.0.1:8080",
		UpstreamOrigin:   PinnedOrigin{Scheme: "https", Host: "api.example.com", Port: "443"},
		UpstreamAddr:     "203.0.113.10:443",
		PolicyPath:       "policy.json",
		SessionDBPath:    "session.db",
		DecisionDBPath:   "decisions.db",
		CredentialHeader: testCredentialHdr,
		TargetCredential: NewSecret(testCredentialValue),
	}
}

func TestCredentialNeverRenders(t *testing.T) {
	cfg := testConfigWithCredential()
	sec := cfg.TargetCredential

	renderings := map[string]string{
		"cfg %v":     fmt.Sprintf("%v", cfg),
		"cfg %+v":    fmt.Sprintf("%+v", cfg),
		"cfg %#v":    fmt.Sprintf("%#v", cfg),
		"cfg %s":     fmt.Sprintf("%s", cfg),
		"cfg %q":     fmt.Sprintf("%q", cfg),
		"&cfg %v":    fmt.Sprintf("%v", &cfg),
		"&cfg %+v":   fmt.Sprintf("%+v", &cfg),
		"secret %v":  fmt.Sprintf("%v", sec),
		"secret %+v": fmt.Sprintf("%+v", sec),
		"secret %#v": fmt.Sprintf("%#v", sec),
		"secret %s":  fmt.Sprintf("%s", sec),
		"secret %q":  fmt.Sprintf("%q", sec),
		"&secret %v": fmt.Sprintf("%v", &sec),
		"slice %v":   fmt.Sprintf("%v", []Secret{sec}),
		"map %v":     fmt.Sprintf("%v", map[string]Secret{"k": sec}),
		"error":      fmt.Errorf("wrapping %v and %s", cfg, sec).Error(),
	}
	for name, s := range renderings {
		if strings.Contains(s, testCredentialValue) {
			t.Errorf("%s leaked the credential: %s", name, s)
		}
	}

	b, err := json.Marshal(cfg)
	if err != nil {
		t.Fatalf("marshal config: %v", err)
	}
	if strings.Contains(string(b), testCredentialValue) {
		t.Errorf("json.Marshal(Config) leaked the credential: %s", b)
	}
	b2, err := json.Marshal(struct {
		S Secret `json:"s"`
	}{sec})
	if err != nil {
		t.Fatalf("marshal secret: %v", err)
	}
	if strings.Contains(string(b2), testCredentialValue) {
		t.Errorf("json.Marshal(Secret) leaked the credential: %s", b2)
	}

	if got := sec.Reveal(); got != testCredentialValue {
		t.Fatalf("Reveal must still return the value, got %q", got)
	}
	if fp := sec.Fingerprint(); fp == "" || strings.Contains(fp, testCredentialValue) || len(fp) > 24 {
		t.Fatalf("fingerprint must be a short non-empty non-value, got %q", fp)
	}
}

// TestCredentialNeverInDecisionLog drives a mix of allows and denies through a real enforcement
// point with a real SQLite decision log, then scans the whole database file — not just the rows —
// for the credential value.
func TestCredentialNeverInDecisionLog(t *testing.T) {
	h := newHarness(t, harnessOpts{UseRealDecisionLog: true})

	reqs := []struct {
		method, target string
		hdr            map[string]string
	}{
		{"GET", "/orders/1", map[string]string{capabilityHeader: testHandle}},
		{"GET", "/orders/1", nil},
		{"DELETE", "/orders/1", map[string]string{capabilityHeader: testHandle}},
		{"GET", "/nope", map[string]string{capabilityHeader: testHandle}},
		{"GET", "https://api.example.com/orders/1", map[string]string{capabilityHeader: testHandle}},
		{"GET", "/orders/1/resend-receipt", map[string]string{capabilityHeader: testHandle}},
		// An agent that guesses the credential header name must not get it echoed back either.
		{"GET", "/orders/1", map[string]string{capabilityHeader: testHandle, testCredentialHdr: "attacker-supplied"}},
	}
	for _, r := range reqs {
		resp := h.do(r.method, r.target, r.hdr)
		body := readAllString(t, resp)
		if strings.Contains(body, testCredentialValue) {
			t.Fatalf("response body for %s %s leaked the credential", r.method, r.target)
		}
		for k, vs := range resp.Header {
			for _, v := range vs {
				if strings.Contains(v, testCredentialValue) {
					t.Fatalf("response header %s leaked the credential", k)
				}
			}
		}
	}

	if err := h.Log.Close(); err != nil {
		t.Fatalf("close decision log: %v", err)
	}
	for _, suffix := range []string{"", "-wal", "-shm"} {
		raw, err := os.ReadFile(h.LogPath + suffix)
		if err != nil {
			continue
		}
		if strings.Contains(string(raw), testCredentialValue) {
			t.Fatalf("decision database file %s contains the credential value", h.LogPath+suffix)
		}
	}
}

func readAllString(t *testing.T, resp *http.Response) string {
	t.Helper()
	defer resp.Body.Close()
	b, err := io.ReadAll(resp.Body)
	if err != nil {
		t.Fatalf("read body: %v", err)
	}
	return string(b)
}

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

func fullEnv() map[string]string {
	return map[string]string{
		envListen:           "127.0.0.1:8080",
		envUpstreamOrigin:   "https://api.example.com:443",
		envUpstreamAddr:     "203.0.113.10:443",
		envPolicy:           "policy.json",
		envSessionDB:        "session.db",
		envDecisionDB:       "decisions.db",
		envCredentialHeader: testCredentialHdr,
		envCredential:       testCredentialValue,
	}
}

func getenvFrom(m map[string]string) func(string) string {
	return func(k string) string { return m[k] }
}

func TestConfigRequiresEveryKeyWithNoDefaults(t *testing.T) {
	for _, key := range requiredEnv {
		t.Run("missing_"+key, func(t *testing.T) {
			env := fullEnv()
			delete(env, key)
			_, err := LoadConfig(getenvFrom(env))
			if err == nil {
				t.Fatalf("%s missing: startup must fail, and it did not", key)
			}
			if !strings.Contains(err.Error(), key) {
				t.Fatalf("error must name the missing key %q, got: %v", key, err)
			}
			if strings.Contains(err.Error(), testCredentialValue) {
				t.Fatalf("config error leaked the credential")
			}
		})
	}

	t.Run("all_missing_named_together", func(t *testing.T) {
		_, err := LoadConfig(func(string) string { return "" })
		if err == nil {
			t.Fatal("empty environment must fail startup")
		}
		for _, key := range requiredEnv {
			if !strings.Contains(err.Error(), key) {
				t.Errorf("error must name %q; got %v", key, err)
			}
		}
	})

	t.Run("complete_environment_loads", func(t *testing.T) {
		cfg, err := LoadConfig(getenvFrom(fullEnv()))
		if err != nil {
			t.Fatalf("complete environment must load: %v", err)
		}
		if cfg.UpstreamOrigin.HostPort() != "api.example.com:443" {
			t.Fatalf("origin = %q", cfg.UpstreamOrigin.HostPort())
		}
		if cfg.TargetCredential.Reveal() != testCredentialValue {
			t.Fatal("credential not carried through")
		}
	})
}

func TestConfigRejectsBadValues(t *testing.T) {
	cases := []struct {
		name    string
		mutate  func(map[string]string)
		wantSub string
	}{
		{"origin_not_https", func(e map[string]string) { e[envUpstreamOrigin] = "http://api.example.com:80" }, "scheme https"},
		{"origin_no_port", func(e map[string]string) { e[envUpstreamOrigin] = "https://api.example.com" }, "explicit port"},
		{"origin_with_path", func(e map[string]string) { e[envUpstreamOrigin] = "https://api.example.com:443/v1" }, "no path"},
		{"origin_with_userinfo", func(e map[string]string) { e[envUpstreamOrigin] = "https://u:p@api.example.com:443" }, "userinfo"},
		{"addr_is_a_name", func(e map[string]string) { e[envUpstreamAddr] = "api.example.com:443" }, "literal IP"},
		{"addr_no_port", func(e map[string]string) { e[envUpstreamAddr] = "203.0.113.10" }, "ip:port"},
		{"addr_loopback", func(e map[string]string) { e[envUpstreamAddr] = "127.0.0.1:443" }, "loopback"},
		// addr_rfc1918 is deliberately absent: an RFC1918 target origin is now PERMITTED
		// under the owner's 2026-08-03 decision, and TestDeclaredRFC1918OriginStarts below
		// asserts it starts. The class stays denied for every other address.
		{"addr_metadata", func(e map[string]string) { e[envUpstreamAddr] = "169.254.169.254:80" }, "cloud_metadata"},
		{"addr_ipv6_ula", func(e map[string]string) { e[envUpstreamAddr] = "[fd00::1]:443" }, "unique_local"},
		{"listen_not_hostport", func(e map[string]string) { e[envListen] = "8080" }, envListen},
		{"credential_header_not_token", func(e map[string]string) { e[envCredentialHeader] = "Bad Header" }, "header field name"},
		{"credential_header_is_capability", func(e map[string]string) { e[envCredentialHeader] = capabilityHeader }, capabilityHeader},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			env := fullEnv()
			tc.mutate(env)
			_, err := LoadConfig(getenvFrom(env))
			if err == nil {
				t.Fatalf("expected startup refusal")
			}
			if !strings.Contains(err.Error(), tc.wantSub) {
				t.Fatalf("error %q does not mention %q", err, tc.wantSub)
			}
			if strings.Contains(err.Error(), testCredentialValue) {
				t.Fatal("config error leaked the credential")
			}
		})
	}
}

// TestDeclaredRFC1918OriginStarts is the other half of the decision: the co-located topology OD-08
// makes the default must actually come up, and the running proxy must carry an exemption for
// exactly the address that was declared.
func TestDeclaredRFC1918OriginStarts(t *testing.T) {
	env := fullEnv()
	env[envUpstreamAddr] = "10.1.2.3:443"
	cfg, err := LoadConfig(getenvFrom(env))
	if err != nil {
		t.Fatalf("a declared RFC1918 target origin must start (OD-08): %v", err)
	}
	if !cfg.AddressExemption.exempts(netip.MustParseAddr("10.1.2.3")) {
		t.Fatal("the loaded config does not exempt the address it was pinned to")
	}
	if cfg.AddressExemption.exempts(netip.MustParseAddr("10.1.2.4")) {
		t.Fatal("the loaded config exempts an address that was never declared")
	}
	if strings.Contains(cfg.String(), "exempt") {
		t.Log("note: Config.String mentions the exemption; check it discloses no more than the address")
	}
}

// ---------------------------------------------------------------------------
// FR-015: nothing distinguishes a runtime request from an agent-composed one
// ---------------------------------------------------------------------------

var provenancePattern = regexp.MustCompile(`(?i)(provenance|origin(ated|ator)|source|caller|issuer|composed|runtime|agent|client|actor|principal|from)`)

// TestNoProvenanceField asserts by reflection that requestContext carries no field a stage could
// branch on to tell a runtime request from an agent-composed one. FR-015 requires the allowlists
// to be applied identically to both; the guarantee is that the information does not exist.
func TestNoProvenanceField(t *testing.T) {
	rt := reflect.TypeOf(requestContext{})
	allowed := map[string]bool{
		"RawTarget": true, // the request-target, not a provenance claim
	}
	for i := 0; i < rt.NumField(); i++ {
		name := rt.Field(i).Name
		if allowed[name] {
			continue
		}
		if provenancePattern.MatchString(name) {
			t.Errorf("requestContext.%s looks like a provenance field; FR-015 forbids a code path that distinguishes a runtime request from an agent-composed one", name)
		}
	}
}
