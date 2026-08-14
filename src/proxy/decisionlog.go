package main

import (
	"context"
	"database/sql"
	"fmt"
	"net/url"
	"path/filepath"
	"strings"
	"sync"
	"time"

	_ "modernc.org/sqlite"
)

// The decision log (FR-011, T-06).
//
// A record for EVERY disposition, allow and deny alike. The proxy owns this database and is its
// only writer; the runtime reads it and ingests it into the trace stream (T093, not this
// component). No credential value is ever written here — where a record must identify which
// credential was used it carries a truncated SHA-256 fingerprint of it and nothing else.

// DecisionRecord is one disposition. Its rule identifier is unexported and is set only by
// newDecisionRecord, so a record with no rule identifier cannot be constructed.
type DecisionRecord struct {
	ruleID string

	Disposition   string
	Reason        string
	Requirement   string
	Method        string
	Path          string
	ResolvedTier  string
	SessionID     string
	PolicyVersion string
	Timestamp     time.Time
	Detail        string

	// AbsoluteHTTPSDenied is the value of the absolute-https denial counter at the time of the
	// decision. Q-07 asks whether that reason dominates real traffic; carrying it on the record
	// is what makes the question answerable from the log alone.
	AbsoluteHTTPSDenied uint64

	// CredentialFingerprint is a truncated SHA-256 of the target credential, present only on
	// records for requests that were re-originated. Never the value.
	CredentialFingerprint string

	// FR-041 extras. Not columns of egress_decision. DecisionLog.Write persists
	// them on effect_gate_observation with a key back to this decision. The
	// typed projection (tier, rule, method, disposition) is copied from the
	// fields above; these two are what the decision log does not already carry.
	MatchedTemplate string
	SpecMetadata    string
}

// RuleID returns the rule identifier. There is no setter: FR-011 requires every disposition to
// name the rule that produced it, and a settable field is a field that can be cleared.
func (d DecisionRecord) RuleID() string { return d.ruleID }

// newDecisionRecord is the only constructor. ruleID is a required positional argument and it is
// validated: an empty or unregistered id fails closed onto EG-PIPE-003 rather than producing a
// record with no rule identifier. A denial with no rule identifier is therefore not constructible.
func newDecisionRecord(ruleID string, fields DecisionRecord) DecisionRecord {
	rec := fields
	rec.ruleID = ruleID
	if !knownRule(ruleID) {
		orig := sanitizeDetail(ruleID)
		rec.ruleID = RuleNoStageAllowed
		rec.Detail = joinDetail(rec.Detail, "rule_id_missing_or_unregistered="+quoteForDetail(orig))
	}
	rec.Reason = ruleReason(rec.ruleID)
	rec.Requirement = ruleRequirement(rec.ruleID)
	if rec.Disposition == "" {
		rec.Disposition = dispositionDeny
	}
	if rec.ResolvedTier == "" {
		rec.ResolvedTier = tierUnresolved
	}
	if rec.Timestamp.IsZero() {
		rec.Timestamp = time.Now().UTC()
	}
	return rec
}

const (
	dispositionAllow = "allow"
	dispositionDeny  = "deny"
)

// decisionObserver, when non-nil, is called for every record the log writes. It exists so that the
// test suite can assert a property over every disposition produced anywhere in it. Production
// leaves it nil and no production code branches on it.
var (
	decisionObserverMu sync.Mutex
	decisionObserver   func(DecisionRecord)
)

func setDecisionObserver(fn func(DecisionRecord)) {
	decisionObserverMu.Lock()
	defer decisionObserverMu.Unlock()
	decisionObserver = fn
}

func notifyDecisionObserver(rec DecisionRecord) {
	decisionObserverMu.Lock()
	fn := decisionObserver
	decisionObserverMu.Unlock()
	if fn != nil {
		fn(rec)
	}
}

const decisionSchema = `
CREATE TABLE IF NOT EXISTS egress_decision (
  seq                   INTEGER PRIMARY KEY AUTOINCREMENT,
  ts                    REAL NOT NULL,
  disposition           TEXT NOT NULL,
  rule_id               TEXT NOT NULL,
  reason                TEXT NOT NULL,
  requirement           TEXT NOT NULL,
  method                TEXT NOT NULL,
  path                  TEXT NOT NULL,
  resolved_tier         TEXT NOT NULL,
  session_id            TEXT NOT NULL,
  policy_version        TEXT NOT NULL,
  absolute_https_denied INTEGER NOT NULL,
  credential_fpr        TEXT NOT NULL,
  detail                TEXT NOT NULL,
  CHECK (length(rule_id) > 0)
);
CREATE INDEX IF NOT EXISTS egress_decision_by_rule ON egress_decision(rule_id);
CREATE INDEX IF NOT EXISTS egress_decision_by_session ON egress_decision(session_id);
`

// DecisionSink is the pipeline's dependency on the log.
type DecisionSink interface {
	Write(ctx context.Context, rec DecisionRecord) error
}

// DecisionLog is the proxy's own SQLite decision database.
type DecisionLog struct {
	db *sql.DB
	mu sync.Mutex
}

// OpenDecisionLog opens (creating if absent) the proxy's decision database.
func OpenDecisionLog(path string) (*DecisionLog, error) {
	abs, err := filepath.Abs(path)
	if err != nil {
		return nil, fmt.Errorf("decisionlog: cannot resolve %q: %w", path, err)
	}
	dsn := (&url.URL{
		Scheme:   "file",
		Path:     abs,
		RawQuery: "_pragma=journal_mode(WAL)&_pragma=busy_timeout(5000)&_pragma=synchronous(NORMAL)",
	}).String()
	db, err := sql.Open("sqlite", dsn)
	if err != nil {
		return nil, fmt.Errorf("decisionlog: cannot open %q: %w", abs, err)
	}
	if _, err := db.Exec(decisionSchema); err != nil {
		db.Close()
		return nil, fmt.Errorf("decisionlog: cannot initialise %q: %w", abs, err)
	}
	if _, err := db.Exec(observationSchema); err != nil {
		db.Close()
		return nil, fmt.Errorf("decisionlog: cannot initialise observation %q: %w", abs, err)
	}
	return &DecisionLog{db: db}, nil
}

// Close flushes and closes the database.
func (l *DecisionLog) Close() error {
	if l == nil || l.db == nil {
		return nil
	}
	return l.db.Close()
}

// Write persists one disposition. A write failure is returned to the caller, which fails the
// request closed: an unrecordable decision is not a permitted decision (FR-011).
func (l *DecisionLog) Write(ctx context.Context, rec DecisionRecord) error {
	if rec.RuleID() == "" {
		// Unreachable through newDecisionRecord; the CHECK constraint would also refuse it.
		// Refused before the observer runs, so a record the log will not accept is not counted
		// as a disposition the enforcement point produced.
		return fmt.Errorf("decisionlog: refusing to write a record with no rule identifier")
	}
	notifyDecisionObserver(rec)
	l.mu.Lock()
	defer l.mu.Unlock()
	tx, err := l.db.BeginTx(ctx, nil)
	if err != nil {
		return fmt.Errorf("decisionlog: begin: %w", err)
	}
	defer tx.Rollback()
	res, err := tx.ExecContext(ctx, `
		INSERT INTO egress_decision
		  (ts, disposition, rule_id, reason, requirement, method, path, resolved_tier,
		   session_id, policy_version, absolute_https_denied, credential_fpr, detail)
		VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)`,
		float64(rec.Timestamp.UTC().UnixNano())/1e9,
		rec.Disposition,
		rec.RuleID(),
		rec.Reason,
		rec.Requirement,
		rec.Method,
		rec.Path,
		rec.ResolvedTier,
		rec.SessionID,
		rec.PolicyVersion,
		int64(rec.AbsoluteHTTPSDenied),
		rec.CredentialFingerprint,
		rec.Detail,
	)
	if err != nil {
		return fmt.Errorf("decisionlog: write failed: %w", err)
	}
	seq, err := res.LastInsertId()
	if err != nil {
		return fmt.Errorf("decisionlog: no decision seq: %w", err)
	}
	if observationShouldPersist(rec.Disposition) {
		obs := observationFrom(rec, seq)
		if err := persistObservation(ctx, tx, obs); err != nil {
			return fmt.Errorf("observation: write failed: %w", err)
		}
	}
	if err := tx.Commit(); err != nil {
		return fmt.Errorf("decisionlog: commit: %w", err)
	}
	return nil
}

// Count returns the number of records carrying ruleID. Used by the test suite and by operators
// answering Q-07 from the log.
func (l *DecisionLog) Count(ctx context.Context, ruleID string) (int, error) {
	var n int
	err := l.db.QueryRowContext(ctx, `SELECT COUNT(*) FROM egress_decision WHERE rule_id = ?`, ruleID).Scan(&n)
	return n, err
}

// sanitizeDetail strips control characters and bounds the length of anything that reaches the log
// or an error body. Detail strings are built from bounded, already-classified values; this is the
// backstop that keeps an unexpected one from becoming a log-injection or an unbounded row.
func sanitizeDetail(s string) string {
	const max = 256
	var b strings.Builder
	for _, r := range s {
		if b.Len() >= max {
			b.WriteString("...")
			break
		}
		if r < 0x20 || r == 0x7f {
			b.WriteByte('_')
			continue
		}
		b.WriteRune(r)
	}
	return b.String()
}

func joinDetail(parts ...string) string {
	kept := make([]string, 0, len(parts))
	for _, p := range parts {
		if p != "" {
			kept = append(kept, p)
		}
	}
	return strings.Join(kept, " ")
}

func quoteForDetail(s string) string {
	if s == "" {
		return `""`
	}
	return `"` + s + `"`
}
