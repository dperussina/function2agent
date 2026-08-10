package main

import (
	"context"
	"database/sql"
	"os"
	"path/filepath"
	"testing"
)

// T093 — the decision log, written by the REAL writer, made available to the runtime's ingest.
//
// The runtime side (`src/runtime/proxy_ingest.py`) reads this database across a process and a
// language boundary. Its own fixture derives the schema from `decisionSchema` rather than
// transcribing it, which catches a column rename but NOT a mismatch between the schema constant
// and what `Write` actually stores. This test closes that: it produces a log through
// `OpenDecisionLog` and `Write` — the same path production takes — and, when
// F2A_DECISIONLOG_EXPORT names a path, leaves it there for the Python side to ingest.
//
// It is a real test in both modes. Without the environment variable it still writes and reads
// back, so `go test ./src/proxy/...` exercises it rather than skipping to a pass.

// exportedDecisionRows are dispositions chosen to span what the ingest has to represent: an allow
// and a deny, a resolved and an unresolved tier, a record with a credential fingerprint and one
// without, and a rule whose requirement differs from its neighbours'.
func exportedDecisionRows() []DecisionRecord {
	return []DecisionRecord{
		newDecisionRecord(RuleAllowed, DecisionRecord{
			Disposition: dispositionAllow, Method: "GET", Path: "/orders/O-1",
			ResolvedTier: "read_only", SessionID: "sess-ingest", PolicyVersion: "sha256:" + repeat64('a'),
			CredentialFingerprint: "sha256:0123456789abcdef",
		}),
		newDecisionRecord(RuleMethodNotAllowed, DecisionRecord{
			Disposition: dispositionDeny, Method: "POST", Path: "/orders/O-1/cancel",
			SessionID: "sess-ingest", PolicyVersion: "sha256:" + repeat64('a'),
			AbsoluteHTTPSDenied: 3,
		}),
		newDecisionRecord(RuleNoStageAllowed, DecisionRecord{
			Disposition: dispositionDeny, Method: "GET", Path: "/elsewhere",
			SessionID: "sess-other", PolicyVersion: "sha256:" + repeat64('a'),
		}),
	}
}

func repeat64(c byte) string {
	b := make([]byte, 64)
	for i := range b {
		b[i] = c
	}
	return string(b)
}

func TestDecisionLogExportForRuntimeIngest(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "decisions.sqlite3")

	dl, err := OpenDecisionLog(path)
	if err != nil {
		t.Fatal(err)
	}
	rows := exportedDecisionRows()
	if len(rows) == 0 {
		t.Fatal("no rows to write; the export would be an empty database and would prove nothing")
	}
	for _, rec := range rows {
		if err := dl.Write(context.Background(), rec); err != nil {
			t.Fatalf("write %s: %v", rec.RuleID(), err)
		}
	}
	if err := dl.Close(); err != nil {
		t.Fatal(err)
	}

	// Read back through a plain read-only connection, which is the footing the runtime reads on.
	db, err := sql.Open("sqlite", "file:"+path+"?mode=ro")
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	var n int
	if err := db.QueryRow(`SELECT COUNT(*) FROM egress_decision`).Scan(&n); err != nil {
		t.Fatal(err)
	}
	if n != len(rows) {
		t.Fatalf("read back %d rows, wrote %d", n, len(rows))
	}
	seen := map[string]bool{}
	cur, err := db.Query(`SELECT rule_id, reason, requirement, disposition FROM egress_decision`)
	if err != nil {
		t.Fatal(err)
	}
	defer cur.Close()
	for cur.Next() {
		var ruleID, reason, requirement, disposition string
		if err := cur.Scan(&ruleID, &reason, &requirement, &disposition); err != nil {
			t.Fatal(err)
		}
		if ruleID == "" || reason == "" || requirement == "" {
			t.Fatalf("row %q has an empty label triple (%q/%q/%q); the runtime refuses such a row rather than completing it",
				ruleID, ruleID, reason, requirement)
		}
		if disposition != dispositionAllow && disposition != dispositionDeny {
			t.Fatalf("disposition %q is outside the pair the runtime maps; a third member has to be added on both sides at once", disposition)
		}
		seen[ruleID] = true
	}
	if err := cur.Err(); err != nil {
		t.Fatal(err)
	}
	if len(seen) < 2 {
		t.Fatalf("the export carries %d distinct rules; an ingest fixture over one rule cannot show a per-rule label travelling", len(seen))
	}

	dest := os.Getenv("F2A_DECISIONLOG_EXPORT")
	if dest == "" {
		return
	}
	body, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	if len(body) == 0 {
		t.Fatal("the written log is empty")
	}
	if err := os.WriteFile(dest, body, 0o600); err != nil {
		t.Fatalf("export to %q: %v", dest, err)
	}
}
