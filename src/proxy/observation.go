package main

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
)

// T178 — the FR-041 corpus row, recorded at the enforcement point.
//
// This is not a second decision log. DecisionRecord already carries the resolved
// tier, the rule identifier, the method, and the disposition. The observation
// row is the typed projection those four fields become for the corpus, plus the
// two fields the decision log does not have — the matched operation template
// and the specification metadata that operation carried — and a key back to
// the decision (decision_seq). T179 exports this table; T180 labels it; T181
// records the threshold unset. None of those are this file.
//
// The table is measurement. Nothing on the success path reads it to decide
// allow or deny. A write failure fails the request closed: an unobserved
// decision is not a permitted decision, for the same reason FR-011 refuses an
// unrecordable one.

// ObservationRecord is one FR-041 corpus row.
type ObservationRecord struct {
	DecisionSeq     int64
	ResolvedTier    string
	RuleID          string
	MatchedTemplate string
	Method          string
	SpecMetadata    string
	Disposition     string
}

const emptySpecMetadata = "{}"

// observationSchema is a second table in the proxy's database, not a second
// schema for egress_decision. decisionSchema stays one CREATE TABLE so the
// runtime ingest fixture that lifts it does not become ambiguous.
const observationSchema = `
CREATE TABLE IF NOT EXISTS effect_gate_observation (
  seq               INTEGER PRIMARY KEY AUTOINCREMENT,
  decision_seq      INTEGER NOT NULL,
  resolved_tier     TEXT NOT NULL,
  rule_id           TEXT NOT NULL,
  matched_template  TEXT NOT NULL,
  method            TEXT NOT NULL,
  spec_metadata     TEXT NOT NULL,
  disposition       TEXT NOT NULL,
  CHECK (length(rule_id) > 0)
);
CREATE INDEX IF NOT EXISTS effect_gate_observation_by_decision
  ON effect_gate_observation(decision_seq);
`

// observationShouldPersist reports whether this disposition belongs in the
// corpus. FR-041's record is every request the decision log already records,
// allow and deny alike. A third disposition is not one of those.
func observationShouldPersist(disposition string) bool {
	return disposition == dispositionAllow || disposition == dispositionDeny
}

func specMetadataOf(op *ServedOperation) string {
	if op == nil {
		return emptySpecMetadata
	}
	body, err := json.Marshal(struct {
		OperationID string `json:"operation_id"`
		Safe        bool   `json:"safe"`
		OpRuleID    string `json:"operation_rule_id"`
	}{OperationID: op.OperationID, Safe: op.Safe, OpRuleID: op.RuleID})
	if err != nil {
		return emptySpecMetadata
	}
	return string(body)
}

func observationFrom(rec DecisionRecord, seq int64) ObservationRecord {
	meta := rec.SpecMetadata
	if meta == "" {
		meta = emptySpecMetadata
	}
	return ObservationRecord{
		DecisionSeq:     seq,
		ResolvedTier:    rec.ResolvedTier,
		RuleID:          rec.RuleID(),
		MatchedTemplate: rec.MatchedTemplate,
		Method:          rec.Method,
		SpecMetadata:    meta,
		Disposition:     rec.Disposition,
	}
}

func persistObservation(ctx context.Context, tx *sql.Tx, rec ObservationRecord) error {
	if rec.RuleID == "" {
		return fmt.Errorf("observation: refusing to write a record with no rule identifier")
	}
	_, err := tx.ExecContext(ctx, `
		INSERT INTO effect_gate_observation
		  (decision_seq, resolved_tier, rule_id, matched_template, method, spec_metadata, disposition)
		VALUES (?,?,?,?,?,?,?)`,
		rec.DecisionSeq,
		rec.ResolvedTier,
		rec.RuleID,
		rec.MatchedTemplate,
		rec.Method,
		rec.SpecMetadata,
		rec.Disposition,
	)
	return err
}
