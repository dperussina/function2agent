package main

import (
	"context"
	"errors"
	"net/http"
	"testing"
	"time"
)

// Stage 1 — capability (T084, FR-050).

func fixedClock(sec float64) Clock {
	return func() time.Time { return time.Unix(0, int64(sec*1e9)).UTC() }
}

// buildCapabilityStage wires stage 1 to a real read-only session store over a real database, so
// the test exercises the mode=ro open path and the digest the supervisor's schema is keyed by.
func buildCapabilityStage(t *testing.T, now float64, rows ...sessionSeed) *CapabilityStage {
	t.Helper()
	path := newSessionDB(t, rows...)
	store, err := OpenSessionStore(path)
	if err != nil {
		t.Fatalf("open session store read-only: %v", err)
	}
	t.Cleanup(func() { store.Close() })
	return NewCapabilityStage(store, fixedClock(now))
}

func capabilityRequest(handle string) *requestContext {
	h := http.Header{}
	if handle != "" {
		h.Set(capabilityHeader, handle)
	}
	return &requestContext{
		Method: "GET", Path: "/orders/1", RawTarget: "/orders/1",
		Header: h, CapabilityHandle: h.Get(capabilityHeader), Tier: tierUnresolved,
	}
}

func TestCapabilityStage(t *testing.T) {
	const now = 1_800_000_000

	cases := []struct {
		name     string
		seed     []sessionSeed
		handle   string
		wantRule string
		allowed  bool
	}{
		{
			name:     "header_absent",
			seed:     []sessionSeed{seedAt(sessionStateRunning, now+3600)},
			handle:   "",
			wantRule: RuleCapabilityAbsent,
		},
		{
			name:     "unknown_handle",
			seed:     []sessionSeed{seedAt(sessionStateRunning, now+3600)},
			handle:   "0000000000000000000000000000000000000000",
			wantRule: RuleCapabilityNotHonoured,
		},
		{
			name:     "session_starting",
			seed:     []sessionSeed{seedAt(sessionStateStarting, now+3600)},
			handle:   testHandle,
			wantRule: RuleSessionTerminated,
		},
		{
			name:     "session_terminated",
			seed:     []sessionSeed{seedAt(sessionStateTerminated, now+3600)},
			handle:   testHandle,
			wantRule: RuleSessionTerminated,
		},
		{
			name:     "lease_expired",
			seed:     []sessionSeed{seedAt(sessionStateRunning, now-1)},
			handle:   testHandle,
			wantRule: RuleLeaseExpired,
		},
		{
			name:     "lease_expiring_exactly_now_is_expired",
			seed:     []sessionSeed{seedAt(sessionStateRunning, now)},
			handle:   testHandle,
			wantRule: RuleLeaseExpired,
		},
		{
			name:    "happy_path",
			seed:    []sessionSeed{seedAt(sessionStateRunning, now+1)},
			handle:  testHandle,
			allowed: true,
		},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			stage := buildCapabilityStage(t, now, tc.seed...)
			rc := capabilityRequest(tc.handle)
			res, err := stage.Evaluate(context.Background(), rc)
			if err != nil {
				t.Fatalf("stage error: %v", err)
			}
			want := tc.wantRule
			if tc.allowed {
				want = RuleAllowed
			}
			assertResult(t, res, tc.allowed, want)
			if tc.handle != "" && tc.wantRule != RuleCapabilityNotHonoured && tc.wantRule != RuleCapabilityAbsent {
				if rc.SessionID != testSessionID {
					t.Fatalf("session id not recorded on the context: %q", rc.SessionID)
				}
			}
			// The handle itself must never appear in a denial detail.
			if tc.handle != "" && containsHandle(res.detail, tc.handle) {
				t.Fatalf("denial detail leaked the capability handle: %q", res.detail)
			}
		})
	}
}

func seedAt(state string, lease float64) sessionSeed {
	var terminal any
	if state == sessionStateTerminated {
		terminal = "SESSION_TERMINATED"
	}
	return sessionSeed{
		SessionID:      testSessionID,
		TenantID:       "tenant-a",
		DeploymentID:   "dep-a",
		State:          state,
		TerminalState:  terminal,
		CapabilitySHA:  capabilityDigest(testHandle),
		LeaseExpiresAt: lease,
	}
}

func containsHandle(s, handle string) bool {
	return handle != "" && len(s) > 0 && (s == handle || containsSub(s, handle))
}

func containsSub(s, sub string) bool {
	return len(sub) > 0 && len(s) >= len(sub) && (func() bool {
		for i := 0; i+len(sub) <= len(s); i++ {
			if s[i:i+len(sub)] == sub {
				return true
			}
		}
		return false
	})()
}

// TestCapabilityResolvedOnEveryRequest proves there is no cache: the session row is read again for
// the second request, so a session that terminates between two requests stops being honoured
// immediately rather than at the end of a cache interval.
func TestCapabilityResolvedOnEveryRequest(t *testing.T) {
	rows := map[string]SessionRow{
		capabilityDigest(testHandle): {
			SessionID: testSessionID, State: sessionStateRunning, LeaseExpiresAt: 2_000_000_000,
		},
	}
	stub := &stubSessions{rows: rows}
	stage := NewCapabilityStage(stub, fixedClock(1_800_000_000))

	res, err := stage.Evaluate(context.Background(), capabilityRequest(testHandle))
	if err != nil {
		t.Fatal(err)
	}
	assertResult(t, res, true, RuleAllowed)

	// The supervisor terminates the session. No proxy restart, no cache invalidation.
	rows[capabilityDigest(testHandle)] = SessionRow{
		SessionID: testSessionID, State: sessionStateTerminated, LeaseExpiresAt: 2_000_000_000,
	}
	res2, err := stage.Evaluate(context.Background(), capabilityRequest(testHandle))
	if err != nil {
		t.Fatal(err)
	}
	assertResult(t, res2, false, RuleSessionTerminated)
}

// TestCapabilityLookupErrorFailsClosed: a lookup that errors is not an allow. The stage returns
// the error and the sequencer denies with EG-PIPE-001.
func TestCapabilityLookupErrorFailsClosed(t *testing.T) {
	stage := NewCapabilityStage(&stubSessions{err: errors.New("database gone")}, fixedClock(1))
	res, err := stage.Evaluate(context.Background(), capabilityRequest(testHandle))
	if err == nil {
		t.Fatal("a lookup failure must be returned as an error, not swallowed")
	}
	if res.allowed {
		t.Fatal("a lookup failure must not allow")
	}
	assertResult(t, runGuarded(context.Background(), stage, capabilityRequest(testHandle)), false, RuleStageError)
}

// TestMultipleCapabilityHeadersDenied: two claims are not a capability.
func TestMultipleCapabilityHeadersDenied(t *testing.T) {
	stage := NewCapabilityStage(&stubSessions{rows: map[string]SessionRow{
		capabilityDigest(testHandle): {SessionID: testSessionID, State: sessionStateRunning, LeaseExpiresAt: 2e9},
	}}, fixedClock(1))
	rc := capabilityRequest(testHandle)
	rc.Header.Add(capabilityHeader, "second-handle")
	res, err := stage.Evaluate(context.Background(), rc)
	if err != nil {
		t.Fatal(err)
	}
	assertResult(t, res, false, RuleCapabilityNotHonoured)
}

// TestSessionStoreIsReadOnly proves the proxy cannot write the supervisor's table even if a future
// change tried to.
func TestSessionStoreIsReadOnly(t *testing.T) {
	path := newSessionDB(t, seedAt(sessionStateRunning, 2e9))
	store, err := OpenSessionStore(path)
	if err != nil {
		t.Fatalf("open: %v", err)
	}
	defer store.Close()
	_, err = store.db.Exec(`UPDATE session SET state = 'RUNNING' WHERE 1=1`)
	if err == nil {
		t.Fatal("the session store must refuse writes")
	}
	t.Logf("write refused as expected: %v", err)
}

// TestCapabilityDigestIsStableAndNotTheHandle documents the digest contract the supervisor must
// match, and asserts the digest is not the handle.
func TestCapabilityDigestIsStableAndNotTheHandle(t *testing.T) {
	d := capabilityDigest(testHandle)
	if len(d) != 64 {
		t.Fatalf("digest must be 64 hex characters, got %d", len(d))
	}
	if d == testHandle {
		t.Fatal("the digest must not be the handle")
	}
	if capabilityDigest(testHandle) != d {
		t.Fatal("digest must be stable")
	}
	if capabilityDigest(testHandle+"x") == d {
		t.Fatal("digest must be sensitive to the handle")
	}
}
