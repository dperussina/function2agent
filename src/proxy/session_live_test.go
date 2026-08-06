package main

import (
	"bufio"
	"context"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

// The read-only open against a database the supervisor is holding open and writing.
//
// Everything else that opens a session database in this package — conformance_test.go,
// capability_test.go — reads a file nobody has open. That is the easy half. The deployed shape is
// the other one: one Python process holds a read-write connection in WAL mode and renews a lease
// on a timer, while this component opens the same file mode=ro and resolves a capability on every
// request.
//
// This exists because the supervisor's writer moved onto the repository layer (T016). That change
// replaced how the file is put into WAL and how every statement is issued, and nothing else in
// either language would notice if it had broken the reader — the conformance fixture is a closed
// file, so it cannot distinguish "still readable" from "still readable while held".
//
// Two things are asserted and they are different claims:
//
//  1. the reader sees the writer's committed rows, and sees them CHANGE. Reading one row once
//     would pass against a stale snapshot; requiring the lease to advance is what makes the
//     assertion about a live writer rather than about a file that happens to exist.
//  2. the connection still refuses to write. mode=ro and query_only are two independent guards on
//     that, and a test that only reads would not notice either being dropped.

const liveHandle = "5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a"

// liveSupervisor is run by python3 with PYTHONPATH at the repository root. It is the supervisor's
// own writer — not a hand-rolled schema — so a drift in session_table.py reaches this test.
const liveSupervisor = `
import sys, time
from src.supervisor.session_table import SessionTable, capability_digest

db = sys.argv[1]
now = time.time()
table = SessionTable(db)
table.create(
    session_id="sess-live",
    tenant_id="tenant-live",
    deployment_id="deploy-live",
    capability_sha256=capability_digest(sys.argv[2]),
    lease_expires_at=now + 60.0,
    now=now,
)
table.mark_running("sess-live")
print("READY", flush=True)
# Hold the connection open and keep writing, which is the state the reader has to survive.
deadline = time.time() + 30.0
bump = 60.0
while time.time() < deadline:
    bump += 1.0
    table.renew("sess-live", now + bump)
    time.sleep(0.02)
`

// startLiveSupervisor launches the Python writer and returns the database path it holds open.
func startLiveSupervisor(t *testing.T) string {
	t.Helper()
	python, err := exec.LookPath("python3")
	if err != nil {
		t.Skipf("no python3 on PATH, so the live writer cannot be started: %v", err)
	}
	root, err := filepath.Abs("../..")
	if err != nil {
		t.Fatalf("cannot resolve the repository root: %v", err)
	}
	if _, err := os.Stat(filepath.Join(root, "src", "supervisor", "session_table.py")); err != nil {
		t.Skipf("the supervisor's writer is not where this test expects it: %v", err)
	}

	db := filepath.Join(t.TempDir(), "sessions.db")
	cmd := exec.Command(python, "-c", liveSupervisor, db, liveHandle)
	cmd.Dir = root
	cmd.Env = append(os.Environ(), "PYTHONPATH="+root)
	stdout, err := cmd.StdoutPipe()
	if err != nil {
		t.Fatalf("stdout pipe: %v", err)
	}
	var stderr strings.Builder
	cmd.Stderr = &stderr
	if err := cmd.Start(); err != nil {
		t.Fatalf("cannot start the live writer: %v", err)
	}
	t.Cleanup(func() {
		_ = cmd.Process.Kill()
		_ = cmd.Wait()
	})

	ready := make(chan string, 1)
	go func() {
		scanner := bufio.NewScanner(stdout)
		for scanner.Scan() {
			if strings.TrimSpace(scanner.Text()) == "READY" {
				ready <- ""
				return
			}
		}
		ready <- "the writer exited without saying READY"
	}()
	select {
	case problem := <-ready:
		if problem != "" {
			t.Fatalf("%s:\n%s", problem, stderr.String())
		}
	case <-time.After(30 * time.Second):
		t.Fatalf("the live writer never became ready:\n%s", stderr.String())
	}
	return db
}

// TestReadOnlyOpenSeesALiveSupervisorsWrites is the constraint the T016 migration had to preserve:
// the proxy opens the supervisor's file while the supervisor holds it, and keeps reading.
func TestReadOnlyOpenSeesALiveSupervisorsWrites(t *testing.T) {
	db := startLiveSupervisor(t)

	store, err := OpenSessionStore(db)
	if err != nil {
		t.Fatalf("mode=ro open of a database a live supervisor holds open failed: %v\n"+
			"the proxy cannot resolve a capability while the supervisor is running", err)
	}
	defer store.Close()

	digest := capabilityDigest(liveHandle)
	row, err := store.LookupByCapability(context.Background(), digest)
	if err != nil {
		t.Fatalf("lookup against a live supervisor's table failed: %v", err)
	}
	if row.State != sessionStateRunning {
		t.Fatalf("state = %q, want %q", row.State, sessionStateRunning)
	}
	if row.TenantID != "tenant-live" || row.DeploymentID != "deploy-live" {
		t.Fatalf("scope columns = %q/%q, want tenant-live/deploy-live; the per-row scope the "+
			"migration introduced did not reach the reader",
			row.TenantID, row.DeploymentID)
	}

	// The lease has to MOVE. A single successful read proves the file is parseable; it does not
	// prove this connection sees anything the writer does after the open, which is the property
	// FR-050 rests on — a terminated session or a lapsed lease has to become visible here.
	first := row.LeaseExpiresAt
	deadline := time.Now().Add(10 * time.Second)
	var latest float64
	for time.Now().Before(deadline) {
		row, err := store.LookupByCapability(context.Background(), digest)
		if err != nil {
			t.Fatalf("a lookup that had been working started failing: %v", err)
		}
		latest = row.LeaseExpiresAt
		if latest > first {
			break
		}
		time.Sleep(20 * time.Millisecond)
	}
	if latest <= first {
		t.Fatalf("the lease read %v at the open and %v ten seconds later, so this connection "+
			"is serving a snapshot and cannot see the supervisor's writes", first, latest)
	}
}

// TestReadOnlyOpenStillRefusesToWrite pins the other half. mode=ro and query_only are separate
// guards; this asserts the pair still refuses, against the live file rather than a closed one,
// because a WAL database with an active writer is where a dropped guard would do the damage.
func TestReadOnlyOpenStillRefusesToWrite(t *testing.T) {
	db := startLiveSupervisor(t)

	store, err := OpenSessionStore(db)
	if err != nil {
		t.Fatalf("open: %v", err)
	}
	defer store.Close()

	if _, err := store.db.ExecContext(
		context.Background(), "UPDATE session SET state = 'TERMINATED'"); err == nil {
		t.Fatal("the read-only store executed an UPDATE against the supervisor's live table. " +
			"mode=ro and query_only are both meant to refuse it, so both are gone")
	}
}
