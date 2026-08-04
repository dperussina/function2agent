package main

import (
	"context"
	"database/sql"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

// T092 — the decision log (FR-011).

func osWriteFile(path, body string) error { return os.WriteFile(path, []byte(body), 0o600) }

// TestRuleIdIsRequiredByTheConstructor: a denial with no rule identifier must be impossible to
// construct. The field is unexported, there is no setter, and the constructor takes it positionally
// and fails closed onto EG-PIPE-003 rather than accepting an empty one.
func TestRuleIdIsRequiredByTheConstructor(t *testing.T) {
	cases := []struct {
		name string
		in   string
		want string
	}{
		{"empty", "", RuleNoStageAllowed},
		{"unregistered", "EG-NOT-A-RULE", RuleNoStageAllowed},
		{"registered", RuleMethodNotAllowed, RuleMethodNotAllowed},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			rec := newDecisionRecord(tc.in, DecisionRecord{Method: "GET", Path: "/x"})
			if rec.RuleID() != tc.want {
				t.Fatalf("rule = %q, want %q", rec.RuleID(), tc.want)
			}
			if rec.Reason == "" {
				t.Fatal("a record must carry a named reason")
			}
			if rec.Requirement == "" {
				t.Fatal("a record must carry the requirement it discharges")
			}
			if rec.Timestamp.IsZero() {
				t.Fatal("a record must carry a timestamp")
			}
		})
	}

	// The zero value of DecisionRecord has no rule id, and the writer refuses it. This is the
	// backstop for a record built by struct literal rather than by the constructor.
	dir := t.TempDir()
	dl, err := OpenDecisionLog(filepath.Join(dir, "d.db"))
	if err != nil {
		t.Fatal(err)
	}
	defer dl.Close()
	if err := dl.Write(context.Background(), DecisionRecord{Method: "GET"}); err == nil {
		t.Fatal("the log must refuse a record with no rule identifier")
	}
}

// TestDecisionRecordCarriesEveryRequiredField is FR-011's list, checked against what is actually
// persisted and read back.
func TestDecisionRecordCarriesEveryRequiredField(t *testing.T) {
	h := newHarness(t, harnessOpts{UseRealDecisionLog: true})

	// One allow and one deny of each interesting kind.
	probes := []struct {
		method, target string
		hdr            map[string]string
	}{
		{"GET", "/orders/1", map[string]string{capabilityHeader: testHandle}},
		{"POST", "/orders/1", map[string]string{capabilityHeader: testHandle}},
		{"GET", "/orders/1", nil},
		{"GET", "/nope", map[string]string{capabilityHeader: testHandle}},
	}
	for _, p := range probes {
		resp := h.do(p.method, p.target, p.hdr)
		resp.Body.Close()
	}

	db, err := sql.Open("sqlite", h.LogPath)
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()

	rows, err := db.Query(`SELECT ts, disposition, rule_id, reason, requirement, method, path,
	                              resolved_tier, session_id, policy_version, absolute_https_denied
	                       FROM egress_decision ORDER BY seq`)
	if err != nil {
		t.Fatal(err)
	}
	defer rows.Close()

	n := 0
	sawAllow, sawDeny := false, false
	for rows.Next() {
		var ts float64
		var disposition, ruleID, reason, requirement, method, path, tier, session, policyVersion string
		var counter int64
		if err := rows.Scan(&ts, &disposition, &ruleID, &reason, &requirement, &method, &path,
			&tier, &session, &policyVersion, &counter); err != nil {
			t.Fatal(err)
		}
		n++
		if ruleID == "" || !knownRule(ruleID) {
			t.Errorf("row %d: rule_id %q", n, ruleID)
		}
		if reason == "" || reason != ruleReason(ruleID) {
			t.Errorf("row %d: reason %q does not match the registry", n, reason)
		}
		if requirement == "" {
			t.Errorf("row %d: no requirement", n)
		}
		if method == "" {
			t.Errorf("row %d: no method", n)
		}
		if path == "" {
			t.Errorf("row %d: no path", n)
		}
		if tier == "" {
			t.Errorf("row %d: no resolved tier", n)
		}
		if policyVersion != "2026-08-03.1" {
			t.Errorf("row %d: policy_version %q is not the version in force", n, policyVersion)
		}
		if ts <= 0 {
			t.Errorf("row %d: no timestamp", n)
		}
		switch disposition {
		case dispositionAllow:
			sawAllow = true
			if session == "" {
				t.Errorf("row %d: an allowed request must carry a session id", n)
			}
		case dispositionDeny:
			sawDeny = true
		default:
			t.Errorf("row %d: disposition %q", n, disposition)
		}
	}
	if n < len(probes) {
		t.Fatalf("recorded %d dispositions for %d requests; FR-011 requires a record for every one", n, len(probes))
	}
	if !sawAllow || !sawDeny {
		t.Fatalf("expected both allows and denies to be recorded (allow=%v deny=%v)", sawAllow, sawDeny)
	}
}

// TestEveryDispositionIsRecordedIncludingAllows: the log is not a denial log.
func TestEveryDispositionIsRecordedIncludingAllows(t *testing.T) {
	h := newHarness(t, harnessOpts{UseRealDecisionLog: true})
	resp := h.do("GET", "/orders/1", map[string]string{capabilityHeader: testHandle})
	body := readAllString(t, resp)
	if resp.StatusCode != 200 {
		t.Fatalf("expected the read to be allowed, got %d: %s", resp.StatusCode, body)
	}
	n, err := h.Log.Count(context.Background(), RuleAllowed)
	if err != nil {
		t.Fatal(err)
	}
	if n != 1 {
		t.Fatalf("allow records = %d, want 1", n)
	}
}

// TestDecisionLogPersistsAcrossReopen: the runtime reads this database out of process (T-06), so
// what matters is what is on disk.
func TestDecisionLogPersistsAcrossReopen(t *testing.T) {
	path := filepath.Join(t.TempDir(), "d.db")
	dl, err := OpenDecisionLog(path)
	if err != nil {
		t.Fatal(err)
	}
	rec := newDecisionRecord(RuleLeaseExpired, DecisionRecord{
		Disposition: dispositionDeny, Method: "GET", Path: "/orders/1",
		ResolvedTier: tierUnresolved, SessionID: "sess-x", PolicyVersion: "v1",
		Timestamp: time.Unix(1700000000, 0).UTC(),
	})
	if err := dl.Write(context.Background(), rec); err != nil {
		t.Fatal(err)
	}
	if err := dl.Close(); err != nil {
		t.Fatal(err)
	}

	again, err := OpenDecisionLog(path)
	if err != nil {
		t.Fatal(err)
	}
	defer again.Close()
	n, err := again.Count(context.Background(), RuleLeaseExpired)
	if err != nil {
		t.Fatal(err)
	}
	if n != 1 {
		t.Fatalf("records after reopen = %d, want 1", n)
	}
}

// TestSanitizeDetailBoundsAndStrips keeps the log from being a control-character injection surface.
func TestSanitizeDetailBoundsAndStrips(t *testing.T) {
	got := sanitizeDetail("a\r\nb\x00c")
	if strings.ContainsAny(got, "\r\n\x00") {
		t.Fatalf("control characters survived: %q", got)
	}
	long := sanitizeDetail(strings.Repeat("x", 4096))
	if len(long) > 300 {
		t.Fatalf("detail not bounded: %d", len(long))
	}
}
