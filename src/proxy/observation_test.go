package main

import (
	"context"
	"database/sql"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// T178 — FR-041 corpus row at the enforcement point.

type observationRow struct {
	DecisionSeq     int64
	ResolvedTier    string
	RuleID          string
	MatchedTemplate string
	Method          string
	SpecMetadata    string
	Disposition     string
}

func readObservations(t *testing.T, path string) []observationRow {
	t.Helper()
	db, err := sql.Open("sqlite", path)
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	cur, err := db.Query(`SELECT decision_seq, resolved_tier, rule_id, matched_template,
	                             method, spec_metadata, disposition
	                      FROM effect_gate_observation ORDER BY seq`)
	if err != nil {
		t.Fatal(err)
	}
	defer cur.Close()
	var out []observationRow
	for cur.Next() {
		var row observationRow
		if err := cur.Scan(&row.DecisionSeq, &row.ResolvedTier, &row.RuleID, &row.MatchedTemplate,
			&row.Method, &row.SpecMetadata, &row.Disposition); err != nil {
			t.Fatal(err)
		}
		out = append(out, row)
	}
	if err := cur.Err(); err != nil {
		t.Fatal(err)
	}
	return out
}

func readDecisionSeqs(t *testing.T, path string) []int64 {
	t.Helper()
	db, err := sql.Open("sqlite", path)
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	cur, err := db.Query(`SELECT seq FROM egress_decision ORDER BY seq`)
	if err != nil {
		t.Fatal(err)
	}
	defer cur.Close()
	var out []int64
	for cur.Next() {
		var seq int64
		if err := cur.Scan(&seq); err != nil {
			t.Fatal(err)
		}
		out = append(out, seq)
	}
	return out
}

func closeLog(t *testing.T, h *harness) {
	t.Helper()
	if h.Log == nil {
		return
	}
	if err := h.Log.Close(); err != nil {
		t.Fatal(err)
	}
	h.Log = nil
}

// TestEveryDecisionHasAnObservation is the 1:1: every request the decision log
// records, allow and deny, produces one observation keyed to that decision.
func TestEveryDecisionHasAnObservation(t *testing.T) {
	h := newHarness(t, harnessOpts{UseRealDecisionLog: true})
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
	closeLog(t, h)

	decisions := readDecisionSeqs(t, h.LogPath)
	obs := readObservations(t, h.LogPath)
	if len(decisions) != len(probes) {
		t.Fatalf("decisions = %d, want %d", len(decisions), len(probes))
	}
	if len(obs) != len(decisions) {
		t.Fatalf("observations = %d, decisions = %d; FR-041 records every request", len(obs), len(decisions))
	}
	for i := range decisions {
		if obs[i].DecisionSeq != decisions[i] {
			t.Errorf("observation %d decision_seq = %d, want %d", i, obs[i].DecisionSeq, decisions[i])
		}
		if obs[i].RuleID == "" || !knownRule(obs[i].RuleID) {
			t.Errorf("observation %d rule_id %q", i, obs[i].RuleID)
		}
		if obs[i].Method == "" {
			t.Errorf("observation %d has no method", i)
		}
		if obs[i].ResolvedTier == "" {
			t.Errorf("observation %d has no resolved tier", i)
		}
	}
}

// TestObservationFiresForAllowAndDeny names both dispositions so dropping
// either arm is a failing test rather than a quieter corpus.
func TestObservationFiresForAllowAndDeny(t *testing.T) {
	h := newHarness(t, harnessOpts{UseRealDecisionLog: true})
	allow := h.do("GET", "/orders/1", map[string]string{capabilityHeader: testHandle})
	allow.Body.Close()
	deny := h.do("POST", "/orders/1", map[string]string{capabilityHeader: testHandle})
	deny.Body.Close()
	closeLog(t, h)

	obs := readObservations(t, h.LogPath)
	sawAllow, sawDeny := false, false
	for _, row := range obs {
		switch row.Disposition {
		case dispositionAllow:
			sawAllow = true
		case dispositionDeny:
			sawDeny = true
		default:
			t.Errorf("disposition %q is outside the pair the decision log records", row.Disposition)
		}
	}
	if !sawAllow || !sawDeny {
		t.Fatalf("corpus missing a disposition (allow=%v deny=%v, n=%d)", sawAllow, sawDeny, len(obs))
	}
}

func TestObservationCarriesMatchedTemplate(t *testing.T) {
	h := newHarness(t, harnessOpts{UseRealDecisionLog: true})
	resp := h.do("GET", "/orders/1", map[string]string{capabilityHeader: testHandle})
	resp.Body.Close()
	closeLog(t, h)

	obs := readObservations(t, h.LogPath)
	if len(obs) != 1 {
		t.Fatalf("observations = %d, want 1", len(obs))
	}
	if obs[0].MatchedTemplate != "/orders/{id}" {
		t.Fatalf("matched_template = %q, want /orders/{id}", obs[0].MatchedTemplate)
	}
}

func TestObservationCarriesSpecificationMetadata(t *testing.T) {
	h := newHarness(t, harnessOpts{UseRealDecisionLog: true})
	resp := h.do("GET", "/orders/1", map[string]string{capabilityHeader: testHandle})
	resp.Body.Close()
	closeLog(t, h)

	obs := readObservations(t, h.LogPath)
	if len(obs) != 1 {
		t.Fatalf("observations = %d, want 1", len(obs))
	}
	var meta struct {
		OperationID string `json:"operation_id"`
		Safe        bool   `json:"safe"`
		OpRuleID    string `json:"operation_rule_id"`
	}
	if err := json.Unmarshal([]byte(obs[0].SpecMetadata), &meta); err != nil {
		t.Fatalf("spec_metadata %q: %v", obs[0].SpecMetadata, err)
	}
	if meta.OperationID != "getOrder" || !meta.Safe || meta.OpRuleID != "OPSET-getOrder" {
		t.Fatalf("spec_metadata = %+v, want getOrder/true/OPSET-getOrder", meta)
	}
}

func TestObservationKeysBackToTheDecision(t *testing.T) {
	h := newHarness(t, harnessOpts{UseRealDecisionLog: true})
	resp := h.do("GET", "/orders/1", map[string]string{capabilityHeader: testHandle})
	resp.Body.Close()
	closeLog(t, h)

	decisions := readDecisionSeqs(t, h.LogPath)
	obs := readObservations(t, h.LogPath)
	if len(decisions) != 1 || len(obs) != 1 {
		t.Fatalf("decisions = %d observations = %d, want 1 and 1", len(decisions), len(obs))
	}
	if obs[0].DecisionSeq == 0 {
		t.Fatal("decision_seq is 0; the observation is not keyed to a decision")
	}
	if obs[0].DecisionSeq != decisions[0] {
		t.Fatalf("decision_seq = %d, egress_decision.seq = %d", obs[0].DecisionSeq, decisions[0])
	}
}

// TestUnwritableObservationFailsClosed: an unobserved decision is not a
// permitted decision. Dropping the measurement table must fail the request
// closed and roll the decision back with it.
func TestUnwritableObservationFailsClosed(t *testing.T) {
	h := newHarness(t, harnessOpts{UseRealDecisionLog: true})
	if _, err := h.Log.db.Exec(`DROP TABLE effect_gate_observation`); err != nil {
		t.Fatal(err)
	}
	resp := h.do("GET", "/orders/1", map[string]string{capabilityHeader: testHandle})
	body := readAllString(t, resp)
	if resp.StatusCode != 503 {
		t.Fatalf("status = %d, want 503 (body %s)", resp.StatusCode, body)
	}
	if h.Capture.count() != 0 {
		t.Fatal("stage 7 ran although the observation could not be recorded")
	}
	closeLog(t, h)
	if n := len(readDecisionSeqs(t, h.LogPath)); n != 0 {
		t.Fatalf("egress_decision still has %d rows; the observation failure must roll the decision back", n)
	}
}

func TestObservationIsNotASecondDecisionLog(t *testing.T) {
	h := newHarness(t, harnessOpts{UseRealDecisionLog: true})
	closeLog(t, h)

	db, err := sql.Open("sqlite", h.LogPath)
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	cur, err := db.Query(`PRAGMA table_info(effect_gate_observation)`)
	if err != nil {
		t.Fatal(err)
	}
	defer cur.Close()
	var cols []string
	for cur.Next() {
		var cid int
		var name, ctype string
		var notnull, pk int
		var dflt any
		if err := cur.Scan(&cid, &name, &ctype, &notnull, &dflt, &pk); err != nil {
			t.Fatal(err)
		}
		cols = append(cols, name)
	}
	want := []string{
		"seq", "decision_seq", "resolved_tier", "rule_id",
		"matched_template", "method", "spec_metadata", "disposition",
	}
	if strings.Join(cols, ",") != strings.Join(want, ",") {
		t.Fatalf("columns = %v, want %v", cols, want)
	}
	forbidden := []string{
		"credential_fpr", "session_id", "reason", "requirement",
		"path", "policy_version", "absolute_https_denied", "detail", "ts",
	}
	have := map[string]bool{}
	for _, c := range cols {
		have[c] = true
	}
	for _, c := range forbidden {
		if have[c] {
			t.Errorf("observation copied decision-log column %q", c)
		}
	}
}

func TestCredentialNeverInObservation(t *testing.T) {
	h := newHarness(t, harnessOpts{UseRealDecisionLog: true})
	resp := h.do("GET", "/orders/1", map[string]string{
		capabilityHeader:  testHandle,
		testCredentialHdr: testCredentialValue,
	})
	resp.Body.Close()
	closeLog(t, h)

	for _, row := range readObservations(t, h.LogPath) {
		blob := row.MatchedTemplate + row.SpecMetadata + row.RuleID + row.Method
		if strings.Contains(blob, testCredentialValue) {
			t.Fatalf("observation carried the credential value")
		}
	}
	raw, err := os.ReadFile(h.LogPath)
	if err != nil {
		t.Fatal(err)
	}
	if strings.Contains(string(raw), testCredentialValue) {
		t.Fatal("decision database file contains the credential value")
	}
}

func observationSuccessPathReads(src string) []string {
	var hits []string
	for _, line := range strings.Split(src, "\n") {
		upper := strings.ToUpper(line)
		if strings.Contains(upper, "SELECT") && strings.Contains(upper, "EFFECT_GATE_OBSERVATION") {
			hits = append(hits, strings.TrimSpace(line))
		}
	}
	return hits
}

func TestObservationIsNotReadToDecide(t *testing.T) {
	entries, err := os.ReadDir(".")
	if err != nil {
		t.Fatal(err)
	}
	var hits []string
	for _, e := range entries {
		name := e.Name()
		if !strings.HasSuffix(name, ".go") || strings.HasSuffix(name, "_test.go") {
			continue
		}
		body, err := os.ReadFile(name)
		if err != nil {
			t.Fatal(err)
		}
		for _, hit := range observationSuccessPathReads(string(body)) {
			hits = append(hits, name+": "+hit)
		}
	}
	if len(hits) != 0 {
		t.Fatalf("success path reads the observation table:\n  %s", strings.Join(hits, "\n  "))
	}
}

func TestTheObservationReadScanFiresOnAPlantedSelect(t *testing.T) {
	planted := "rows, _ := tx.Query(`SELECT decision_seq FROM effect_gate_observation`)"
	hits := observationSuccessPathReads(planted)
	if len(hits) == 0 {
		t.Fatal("the scanner matches nothing; a planted success-path read is free")
	}
}

func TestUnresolvedObservationCarriesEmptyTemplate(t *testing.T) {
	h := newHarness(t, harnessOpts{UseRealDecisionLog: true})
	resp := h.do("GET", "/nope", map[string]string{capabilityHeader: testHandle})
	resp.Body.Close()
	closeLog(t, h)
	obs := readObservations(t, h.LogPath)
	if len(obs) != 1 {
		t.Fatalf("observations = %d, want 1", len(obs))
	}
	if obs[0].MatchedTemplate != "" {
		t.Fatalf("unmatched call carried template %q", obs[0].MatchedTemplate)
	}
	if obs[0].SpecMetadata != emptySpecMetadata {
		t.Fatalf("unmatched spec_metadata = %q, want %q", obs[0].SpecMetadata, emptySpecMetadata)
	}
	if obs[0].Disposition != dispositionDeny {
		t.Fatalf("disposition = %q, want deny", obs[0].Disposition)
	}
}

func TestDenyListObservationCarriesTheDenyTemplate(t *testing.T) {
	h := newHarness(t, harnessOpts{UseRealDecisionLog: true})
	resp := h.do("GET", "/orders/1/resend-receipt", map[string]string{capabilityHeader: testHandle})
	resp.Body.Close()
	closeLog(t, h)
	obs := readObservations(t, h.LogPath)
	if len(obs) != 1 {
		t.Fatalf("observations = %d, want 1", len(obs))
	}
	if obs[0].MatchedTemplate != "/orders/{id}/resend-receipt" {
		t.Fatalf("matched_template = %q, want the deny-list template", obs[0].MatchedTemplate)
	}
}

func TestObservationFromDirectWriteStillKeysTheDecision(t *testing.T) {
	path := filepath.Join(t.TempDir(), "d.db")
	dl, err := OpenDecisionLog(path)
	if err != nil {
		t.Fatal(err)
	}
	rec := newDecisionRecord(RuleAllowed, DecisionRecord{
		Disposition: dispositionAllow, Method: "GET", Path: "/orders/1",
		ResolvedTier: tierReadOnly, MatchedTemplate: "/orders/{id}",
		SpecMetadata: `{"operation_id":"getOrder","safe":true,"operation_rule_id":"OPSET-getOrder"}`,
	})
	if err := dl.Write(context.Background(), rec); err != nil {
		t.Fatal(err)
	}
	if err := dl.Close(); err != nil {
		t.Fatal(err)
	}
	obs := readObservations(t, path)
	if len(obs) != 1 || obs[0].DecisionSeq == 0 || obs[0].MatchedTemplate != "/orders/{id}" {
		t.Fatalf("direct Write did not persist the corpus row: %+v", obs)
	}
}
