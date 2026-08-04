package main

import (
	"bufio"
	"context"
	"crypto/x509"
	"database/sql"
	"encoding/json"
	"io"
	"log"
	"net"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"time"
)

// Shared test scaffolding. Nothing here uses an absolute path outside t.TempDir().

const (
	testCredentialValue = "SUPERSECRET-TARGET-CREDENTIAL-b7f3a1"
	testCredentialHdr   = "X-Target-Authorization"
	testHandle          = "8f14e45fceea167a5a36dedd4bea2543deadbeefcafe0001"
	testSessionID       = "sess-0001"
)

// ---------------------------------------------------------------------------
// Session table
// ---------------------------------------------------------------------------

// sessionSeed is one row of the supervisor-owned session table.
type sessionSeed struct {
	SessionID      string
	TenantID       string
	DeploymentID   string
	State          string
	TerminalState  any
	CapabilitySHA  string
	LeaseExpiresAt float64
}

// newSessionDB writes the supervisor's schema into a temporary database and seeds it. The proxy
// only ever opens this read-only; the test is standing in for the supervisor as its writer.
func newSessionDB(t *testing.T, rows ...sessionSeed) string {
	t.Helper()
	path := filepath.Join(t.TempDir(), "session.db")
	db, err := sql.Open("sqlite", path)
	if err != nil {
		t.Fatalf("open session db: %v", err)
	}
	defer db.Close()
	const schema = `
CREATE TABLE session (
  session_id        TEXT PRIMARY KEY,
  tenant_id         TEXT NOT NULL,
  deployment_id     TEXT NOT NULL,
  state             TEXT NOT NULL,
  terminal_state    TEXT,
  capability_sha256 TEXT NOT NULL UNIQUE,
  lease_expires_at  REAL NOT NULL,
  created_at        REAL NOT NULL
);
CREATE INDEX session_by_capability ON session(capability_sha256);`
	if _, err := db.Exec(schema); err != nil {
		t.Fatalf("create session schema: %v", err)
	}
	for _, r := range rows {
		_, err := db.Exec(
			`INSERT INTO session (session_id, tenant_id, deployment_id, state, terminal_state, capability_sha256, lease_expires_at, created_at)
			 VALUES (?,?,?,?,?,?,?,?)`,
			r.SessionID, r.TenantID, r.DeploymentID, r.State, r.TerminalState, r.CapabilitySHA, r.LeaseExpiresAt,
			float64(time.Now().Unix()))
		if err != nil {
			t.Fatalf("seed session row: %v", err)
		}
	}
	return path
}

// runningSeed is a RUNNING session whose lease is an hour away.
func runningSeed() sessionSeed {
	return sessionSeed{
		SessionID:      testSessionID,
		TenantID:       "tenant-a",
		DeploymentID:   "dep-a",
		State:          sessionStateRunning,
		TerminalState:  nil,
		CapabilitySHA:  capabilityDigest(testHandle),
		LeaseExpiresAt: float64(time.Now().Add(time.Hour).Unix()),
	}
}

// stubSessions is an in-memory SessionLookup for stage tests that do not need a database.
type stubSessions struct {
	rows map[string]SessionRow
	err  error
}

func (s *stubSessions) LookupByCapability(_ context.Context, digest string) (SessionRow, error) {
	if s.err != nil {
		return SessionRow{}, s.err
	}
	row, ok := s.rows[digest]
	if !ok {
		return SessionRow{}, ErrSessionNotFound
	}
	return row, nil
}

// ---------------------------------------------------------------------------
// Policy
// ---------------------------------------------------------------------------

const testPolicyJSON = `{
  "schema_version": "1.0.0",
  "policy_version": "2026-08-03.1",
  "method_allowlist": ["GET", "HEAD"],
  "served_operations": [
    {"operation_id": "getOrder", "method": "GET", "path_template": "/orders/{id}", "safe": true, "rule_id": "OPSET-getOrder"},
    {"operation_id": "listOrders", "method": "GET", "path_template": "/orders", "safe": true, "rule_id": "OPSET-listOrders"},
    {"operation_id": "headOrder", "method": "HEAD", "path_template": "/orders/{id}", "safe": true, "rule_id": "OPSET-headOrder"},
    {"operation_id": "getOrderExport", "method": "GET", "path_template": "/orders/{id}/export", "safe": false, "rule_id": "OPSET-getOrderExport"}
  ],
  "deny_list": [
    {"rule_id": "DENY-SER-001", "method": "GET", "path_template": "/orders/{id}/resend-receipt", "justification": "issues an email"}
  ]
}`

func mustTestPolicy(t *testing.T) *Policy {
	t.Helper()
	p, err := ParsePolicy([]byte(testPolicyJSON))
	if err != nil {
		t.Fatalf("test policy must parse: %v", err)
	}
	return p
}

func writePolicyFile(t *testing.T, body string) string {
	t.Helper()
	path := filepath.Join(t.TempDir(), "policy.json")
	if err := os.WriteFile(path, []byte(body), 0o600); err != nil {
		t.Fatalf("write policy: %v", err)
	}
	return path
}

// ---------------------------------------------------------------------------
// Decision sink
// ---------------------------------------------------------------------------

// recordingSink captures decisions in memory.
type recordingSink struct {
	mu       sync.Mutex
	records  []DecisionRecord
	failWith error
}

func (s *recordingSink) Write(_ context.Context, rec DecisionRecord) error {
	notifyDecisionObserver(rec)
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.failWith != nil {
		return s.failWith
	}
	s.records = append(s.records, rec)
	return nil
}

func (s *recordingSink) all() []DecisionRecord {
	s.mu.Lock()
	defer s.mu.Unlock()
	out := make([]DecisionRecord, len(s.records))
	copy(out, s.records)
	return out
}

func (s *recordingSink) last() (DecisionRecord, bool) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if len(s.records) == 0 {
		return DecisionRecord{}, false
	}
	return s.records[len(s.records)-1], true
}

// ---------------------------------------------------------------------------
// Dialer stub
// ---------------------------------------------------------------------------

// stubDialer redirects the pinned dial to a test upstream. It exists because the enforcement
// point's own PinnedDialer refuses loopback under FR-017, so a test upstream on 127.0.0.1 is not
// reachable through it. Substituting a Dialer is the injection point the production code offers;
// no production code branches on a test flag.
type stubDialer struct {
	target string

	mu      sync.Mutex
	asked   []string
	dialled int
}

func (d *stubDialer) DialContext(ctx context.Context, network, addr string) (net.Conn, error) {
	d.mu.Lock()
	d.asked = append(d.asked, addr)
	d.dialled++
	d.mu.Unlock()
	return (&net.Dialer{Timeout: 5 * time.Second}).DialContext(ctx, network, d.target)
}

func (d *stubDialer) calls() (int, []string) {
	d.mu.Lock()
	defer d.mu.Unlock()
	out := make([]string, len(d.asked))
	copy(out, d.asked)
	return d.dialled, out
}

// ---------------------------------------------------------------------------
// Full enforcement-point harness
// ---------------------------------------------------------------------------

// upstreamCapture records what the pinned upstream actually received.
type upstreamCapture struct {
	mu      sync.Mutex
	seen    []*http.Request
	seenHdr []http.Header
}

func (u *upstreamCapture) record(r *http.Request) {
	u.mu.Lock()
	defer u.mu.Unlock()
	u.seen = append(u.seen, r.Clone(context.Background()))
	u.seenHdr = append(u.seenHdr, r.Header.Clone())
}

func (u *upstreamCapture) count() int {
	u.mu.Lock()
	defer u.mu.Unlock()
	return len(u.seen)
}

func (u *upstreamCapture) lastHeader() http.Header {
	u.mu.Lock()
	defer u.mu.Unlock()
	if len(u.seenHdr) == 0 {
		return nil
	}
	return u.seenHdr[len(u.seenHdr)-1]
}

func (u *upstreamCapture) paths() []string {
	u.mu.Lock()
	defer u.mu.Unlock()
	out := make([]string, 0, len(u.seen))
	for _, r := range u.seen {
		out = append(out, r.URL.Path)
	}
	return out
}

type harness struct {
	t *testing.T

	Origin     PinnedOrigin
	Policy     *Policy
	Sink       *recordingSink
	Log        *DecisionLog
	LogPath    string
	Pipeline   *Pipeline
	Upstream   *httptest.Server
	Capture    *upstreamCapture
	Dialer     *stubDialer
	ListenAddr string
	Credential Secret
	Sessions   SessionLookup
}

type harnessOpts struct {
	// UseRealDecisionLog writes to a real SQLite database instead of the in-memory sink.
	UseRealDecisionLog bool
	// Sessions overrides the session lookup.
	Sessions SessionLookup
	// Policy overrides the policy.
	Policy *Policy
	// Now overrides the clock stage 1 reads.
	Now Clock
	// Stages overrides the registered gate stages entirely.
	Stages []Stage
	// Final overrides stage 7.
	Final FinalStage
	// UpstreamHandler overrides what the pinned upstream replies.
	UpstreamHandler http.HandlerFunc
}

// newHarness assembles a complete enforcement point over a TLS test upstream, listening on a real
// loopback socket through the production listener wrapper and the production server settings.
func newHarness(t *testing.T, opts harnessOpts) *harness {
	t.Helper()

	capture := &upstreamCapture{}
	handler := opts.UpstreamHandler
	if handler == nil {
		handler = func(w http.ResponseWriter, r *http.Request) {
			capture.record(r)
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusOK)
			_, _ = io.WriteString(w, `{"upstream":"ok","path":"`+r.URL.Path+`"}`)
		}
	} else {
		inner := handler
		handler = func(w http.ResponseWriter, r *http.Request) {
			capture.record(r)
			inner(w, r)
		}
	}

	upstream := httptest.NewTLSServer(handler)
	t.Cleanup(upstream.Close)

	pool := x509.NewCertPool()
	pool.AddCert(upstream.Certificate())

	// httptest's certificate is issued for example.com; the pinned origin names it, and the TLS
	// client validates that name normally.
	origin := PinnedOrigin{Scheme: "https", Host: "example.com", Port: "443"}

	policy := opts.Policy
	if policy == nil {
		policy = mustTestPolicy(t)
	}

	sessions := opts.Sessions
	if sessions == nil {
		sessions = &stubSessions{rows: map[string]SessionRow{
			capabilityDigest(testHandle): {
				SessionID:      testSessionID,
				TenantID:       "tenant-a",
				DeploymentID:   "dep-a",
				State:          sessionStateRunning,
				LeaseExpiresAt: float64(time.Now().Add(time.Hour).Unix()),
			},
		}}
	}

	dialer := &stubDialer{target: strings.TrimPrefix(upstream.URL, "https://")}
	cred := NewSecret(testCredentialValue)

	var final FinalStage = opts.Final
	if final == nil {
		final = NewReoriginator(ReoriginatorConfig{
			Origin:           origin,
			CredentialHeader: testCredentialHdr,
			Credential:       cred,
			Dialer:           dialer,
			RootCAs:          pool,
			Timeout:          10 * time.Second,
		})
	}

	stages := opts.Stages
	if stages == nil {
		stages = defaultStages(origin, policy, sessions, opts.Now)
	}

	h := &harness{
		t:          t,
		Origin:     origin,
		Policy:     policy,
		Upstream:   upstream,
		Capture:    capture,
		Dialer:     dialer,
		Credential: cred,
		Sessions:   sessions,
	}

	var sink DecisionSink
	if opts.UseRealDecisionLog {
		h.LogPath = filepath.Join(t.TempDir(), "decisions.db")
		dl, err := OpenDecisionLog(h.LogPath)
		if err != nil {
			t.Fatalf("open decision log: %v", err)
		}
		t.Cleanup(func() { dl.Close() })
		h.Log = dl
		sink = dl
	} else {
		h.Sink = &recordingSink{}
		sink = h.Sink
	}

	h.Pipeline = NewPipeline(stages, final, sink, policy, cred.Fingerprint())

	cfg := Config{Listen: "127.0.0.1:0"}
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("listen: %v", err)
	}
	srv := NewEnforcementServer(cfg, h.Pipeline, log.New(io.Discard, "", 0))
	go func() { _ = srv.Serve(recordingListener{ln}) }()
	t.Cleanup(func() { _ = srv.Close() })
	h.ListenAddr = ln.Addr().String()

	return h
}

// send writes raw bytes to the enforcement point and returns the raw response bytes.
func (h *harness) sendRaw(raw string) (string, error) {
	h.t.Helper()
	conn, err := net.Dial("tcp", h.ListenAddr)
	if err != nil {
		return "", err
	}
	defer conn.Close()
	_ = conn.SetDeadline(time.Now().Add(5 * time.Second))
	if _, err := conn.Write([]byte(raw)); err != nil {
		return "", err
	}
	var sb strings.Builder
	br := bufio.NewReader(conn)
	buf := make([]byte, 4096)
	for {
		n, err := br.Read(buf)
		sb.Write(buf[:n])
		if err != nil {
			break
		}
		if sb.Len() > 1<<20 {
			break
		}
	}
	return sb.String(), nil
}

// get performs an ordinary request through the enforcement point.
func (h *harness) do(method, target string, headers map[string]string) *http.Response {
	h.t.Helper()
	req, err := http.NewRequest(method, "http://"+h.ListenAddr+"/", nil)
	if err != nil {
		h.t.Fatalf("build request: %v", err)
	}
	// The request-target is set verbatim so absolute-form and origin-form can both be exercised.
	req.URL.Opaque = target
	for k, v := range headers {
		req.Header.Set(k, v)
	}
	client := &http.Client{
		Timeout: 10 * time.Second,
		// The test client must not follow a redirect the upstream returned: the assertion is
		// about what the enforcement point did, not about where a browser would end up.
		CheckRedirect: func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse },
	}
	resp, err := client.Do(req)
	if err != nil {
		h.t.Fatalf("request failed: %v", err)
	}
	return resp
}

// httptestRecorder is a response recorder for handler-level tests.
func httptestRecorder() *httptest.ResponseRecorder { return httptest.NewRecorder() }

// mustRequest builds a request whose RequestURI is exactly target, so absolute-form and
// asterisk-form targets can be exercised without a socket.
func mustRequest(t *testing.T, method, target string) *http.Request {
	t.Helper()
	u := target
	if !strings.HasPrefix(target, "http://") && !strings.HasPrefix(target, "https://") {
		u = "http://proxy.invalid" + strings.TrimPrefix(target, "*")
	}
	r := httptest.NewRequest(method, u, nil)
	r.RequestURI = target
	return r
}

// ruleOf reads the rule identifier off a denial response.
func ruleOf(t *testing.T, resp *http.Response) string {
	t.Helper()
	defer resp.Body.Close()
	if id := resp.Header.Get("X-F2A-Rule-Id"); id != "" {
		return id
	}
	var body denialBody
	if err := json.NewDecoder(resp.Body).Decode(&body); err != nil {
		return ""
	}
	return body.Error.RuleID
}

// ---------------------------------------------------------------------------
// Assertions shared across stage tests
// ---------------------------------------------------------------------------

// assertResult checks a stage result against an expected rule id, and records the denial with the
// suite-wide rule-identifier observer so TestMain's check covers direct stage calls too.
func assertResult(t *testing.T, got stageResult, wantAllowed bool, wantRule string) {
	t.Helper()
	if !got.allowed {
		notifyDecisionObserver(newDecisionRecord(got.ruleID, DecisionRecord{Detail: got.detail}))
	}
	if got.allowed != wantAllowed {
		t.Fatalf("allowed = %v, want %v (rule %q detail %q)", got.allowed, wantAllowed, got.ruleID, got.detail)
	}
	if wantRule != "" && got.ruleID != wantRule {
		t.Fatalf("rule = %q, want %q (detail %q)", got.ruleID, wantRule, got.detail)
	}
	if !got.allowed && !knownRule(got.ruleID) {
		t.Fatalf("denial carries unregistered rule id %q", got.ruleID)
	}
}
