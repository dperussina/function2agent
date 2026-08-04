package main

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"net/url"
	"path/filepath"

	_ "modernc.org/sqlite"
)

// Read-only access to the session table.
//
// The supervisor owns and writes this table (T-06, single-writer-per-table). The proxy only reads
// it, and reads it on EVERY request: there is no cache, because a cache reintroduces exactly the
// window the lease exists to close — a session terminated or a lease expired between two requests
// would keep being honoured for the life of the cache entry (FR-050).

// Session state values written by the supervisor.
const (
	sessionStateStarting   = "STARTING"
	sessionStateRunning    = "RUNNING"
	sessionStateTerminated = "TERMINATED"
)

// ErrSessionNotFound is returned when no session row carries the presented capability digest.
var ErrSessionNotFound = errors.New("session: no row for capability digest")

// SessionRow is the subset of the session table this component reads.
type SessionRow struct {
	SessionID      string
	TenantID       string
	DeploymentID   string
	State          string
	TerminalState  string
	LeaseExpiresAt float64
}

// SessionLookup is the capability-resolution dependency of stage 1. It is an interface so that the
// stage can be tested without a database; the production implementation is *SessionStore.
type SessionLookup interface {
	LookupByCapability(ctx context.Context, digestHex string) (SessionRow, error)
}

// SessionStore is a read-only handle on the supervisor's session database.
type SessionStore struct {
	db *sql.DB
}

// OpenSessionStore opens path read-only. It never writes, and it holds no statement that could.
func OpenSessionStore(path string) (*SessionStore, error) {
	abs, err := filepath.Abs(path)
	if err != nil {
		return nil, fmt.Errorf("session: cannot resolve %q: %w", path, err)
	}
	// mode=ro asks SQLite itself to refuse writes; query_only makes the connection refuse them
	// too. Both, because the second holds even if a future driver drops the URI parameter.
	dsn := (&url.URL{
		Scheme:   "file",
		Path:     abs,
		RawQuery: "mode=ro&_pragma=query_only(1)",
	}).String()

	db, err := sql.Open("sqlite", dsn)
	if err != nil {
		return nil, fmt.Errorf("session: cannot open %q read-only: %w", abs, err)
	}
	if err := db.Ping(); err != nil {
		db.Close()
		return nil, fmt.Errorf("session: cannot open %q read-only: %w", abs, err)
	}
	return &SessionStore{db: db}, nil
}

// Close releases the read-only handle.
func (s *SessionStore) Close() error {
	if s == nil || s.db == nil {
		return nil
	}
	return s.db.Close()
}

// LookupByCapability resolves a capability digest to a session row. The digest, never the handle,
// is what crosses this boundary.
func (s *SessionStore) LookupByCapability(ctx context.Context, digestHex string) (SessionRow, error) {
	const q = `SELECT session_id, tenant_id, deployment_id, state, COALESCE(terminal_state, ''), lease_expires_at
	           FROM session WHERE capability_sha256 = ?`
	var row SessionRow
	err := s.db.QueryRowContext(ctx, q, digestHex).Scan(
		&row.SessionID, &row.TenantID, &row.DeploymentID, &row.State, &row.TerminalState, &row.LeaseExpiresAt)
	if errors.Is(err, sql.ErrNoRows) {
		return SessionRow{}, ErrSessionNotFound
	}
	if err != nil {
		return SessionRow{}, fmt.Errorf("session: lookup failed: %w", err)
	}
	return row, nil
}
