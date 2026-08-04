package main

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"time"
)

// Stage 1 — capability (T084, FR-050).
//
// The opaque session handle presented in X-F2A-Capability is resolved against the session table on
// EVERY request. There is nothing in the handle to verify offline: it is opaque random bytes, it
// carries no signature, no expiry claim and no self-describing field, and this stage deliberately
// adds none. Everything that decides whether it is honoured lives in the session row.
//
// It is honoured only while the row's state is RUNNING and lease_expires_at is strictly in the
// future. Both conditions are read fresh per request; a cache would keep honouring a handle for
// the life of the entry after the session terminated, which is the exact window the lease exists
// to close.

// capabilityDigest is the digest the session table is keyed by.
//
// AMBIGUITY, RESOLVED TOWARDS "VERIFY NOTHING": the contract says the handle is "opaque random
// bytes hex-encoded" and that the table stores "hex SHA-256 of the opaque handle". That admits two
// readings — hash the decoded bytes, or hash the presented string. This implementation hashes the
// PRESENTED STRING exactly as received. Hashing the decoded bytes would require the handle to be
// well-formed hex, which is a structural assumption about a value the contract says has nothing in
// it to verify. The supervisor must digest the same way; a mismatch fails closed (every request
// denied with capability_not_honoured) rather than open.
func capabilityDigest(handle string) string {
	sum := sha256.Sum256([]byte(handle))
	return hex.EncodeToString(sum[:])
}

// Clock is injectable so the lease boundary can be tested at an exact instant.
type Clock func() time.Time

// CapabilityStage is stage 1.
type CapabilityStage struct {
	stageName
	sessions SessionLookup
	now      Clock
}

// NewCapabilityStage builds stage 1. now may be nil, in which case time.Now is used.
func NewCapabilityStage(sessions SessionLookup, now Clock) *CapabilityStage {
	if now == nil {
		now = time.Now
	}
	return &CapabilityStage{stageName: "capability", sessions: sessions, now: now}
}

// Evaluate resolves the handle. Every exit that is not an explicit allowResult is a deny, and each
// failure mode has its own rule identifier so the operator can tell them apart in the log.
func (s *CapabilityStage) Evaluate(ctx context.Context, rc *requestContext) (stageResult, error) {
	handle := rc.CapabilityHandle
	if handle == "" {
		return denyResult(RuleCapabilityAbsent, "header="+quoteForDetail(capabilityHeader)), nil
	}
	// More than one capability header is not a capability: it is two claims, and honouring
	// either would be choosing one. net/http would join them; the raw multimap is checked.
	if vals := headerValues(rc.Header, capabilityHeader); len(vals) != 1 {
		return denyResult(RuleCapabilityNotHonoured, "reason=\"multiple_capability_headers\""), nil
	}

	row, err := s.sessions.LookupByCapability(ctx, capabilityDigest(handle))
	if errors.Is(err, ErrSessionNotFound) {
		// The digest is not in the table. The handle itself is never logged.
		return denyResult(RuleCapabilityNotHonoured, "reason=\"unknown_handle\""), nil
	}
	if err != nil {
		// A lookup failure is not an allow. Returning the error makes the sequencer deny with
		// EG-PIPE-001 rather than this stage guessing at a reason.
		return stageResult{}, err
	}

	rc.SessionID = row.SessionID

	if row.State != sessionStateRunning {
		// EG-CAP-003's registered reason is session_terminated. It is also the rule that fires
		// for STARTING, which is not terminated; the detail carries the actual state so the log
		// is not misleading. See the report: the rule set has no id for "not yet RUNNING".
		return denyResult(RuleSessionTerminated,
			joinDetail("state="+quoteForDetail(sanitizeDetail(row.State)),
				"terminal_state="+quoteForDetail(sanitizeDetail(row.TerminalState)))), nil
	}

	nowSecs := float64(s.now().UnixNano()) / 1e9
	if !(row.LeaseExpiresAt > nowSecs) {
		// Strictly in the future. A lease expiring exactly now has expired.
		return denyResult(RuleLeaseExpired, "reason=\"lease_not_strictly_future\""), nil
	}

	return allowResult(), nil
}
