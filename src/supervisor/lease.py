"""T108 — FR-050 layer 2: `RUNNING` is a **lease**, so ceasing to act revokes.

The design rule the plan states, and the one thing to keep in mind reading
this file: **revocation is the default and continuation is the thing that
requires work.** The supervisor renews on a short interval while the session is
live; the proxy honours `RUNNING` only while `lease_expires_at` is in the
future. On a crash of the runtime, the supervisor, or both, *nothing renews and
the authority lapses without any code having run*.

That last clause is the requirement. Finding 006 killed its probes with
`SIGKILL` from a separate process precisely so that no `finally` block, no
`atexit` hook and no graceful shutdown could run, and FR-050's bounded clause
has to survive exactly that. So there is deliberately **no** revocation call in
a shutdown path here that the mechanism depends on. `LeaseRenewer.stop()`
exists for the orderly case and the mechanism is correct without it — the
`SIGKILL` fixture is what proves the difference.

**The residual window, disclosed rather than denied.** Between the crash and
the lapse there is one lease interval during which the handle is still
honoured. The interval is a configured value with nothing behind it and carries
FR-043's marking (`CAPABILITY_LEASE_INTERVAL_SECONDS`, defaulted and marked
unvalidated in `src/contracts/config.py`). Layer 3 — the per-session listener
whose descriptor the kernel closes — is what narrows this to the case where the
supervisor survives but the session row was not updated, rather than every
crash.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from src.contracts.repository import StoreBusyError
from src.supervisor.session_table import SessionTable

# The lease is granted for a multiple of the renewal interval so that one
# missed renewal — a slow disk, a scheduler hiccup — does not revoke a live
# session. Two is the smallest multiple that tolerates a single miss, and it is
# a *ratio*, not a duration: it inherits the interval's unvalidated status
# rather than adding a second unmeasured number.
LEASE_TTL_MULTIPLE = 2.0

#: How many **consecutive** renewals may fail with `StoreBusyError` before the
#: renewer stops. **Derived from the constant above, not chosen** — which is
#: what distinguishes it from the "bound the retries" option T108 declined,
#: whose objection was that it mints an unmeasured number. The lease is granted
#: for `LEASE_TTL_MULTIPLE` intervals, so exactly that many minus one renewals
#: can be missed while the lease it extends is still live. Tolerating one more
#: would mean a renewal succeeding *after* its own lease had lapsed, which
#: revives authority FR-050 says should already be gone — so the bound is a
#: safety property of the lease and not a comfort setting.
#:
#: Floored on purpose: a fractional multiple does not buy a whole extra missed
#: renewal, and rounding up would spend a tolerance the lease has not granted.
TOLERATED_CONSECUTIVE_BUSY = int(LEASE_TTL_MULTIPLE) - 1


@dataclass(frozen=True)
class LeaseTerms:
    session_id: str
    interval_seconds: float

    @property
    def ttl_seconds(self) -> float:
        return self.interval_seconds * LEASE_TTL_MULTIPLE

    def expiry_from(self, now: float) -> float:
        return now + self.ttl_seconds


class LeaseRenewer:
    """Renews one session's lease until it stops being called.

    Runs on a daemon thread on purpose: a daemon thread does not keep the
    process alive, so a supervisor whose main work has ended stops renewing
    rather than holding a session's authority open behind a thread nobody is
    watching.
    """

    def __init__(self, table: SessionTable, terms: LeaseTerms) -> None:
        self.table = table
        self.terms = terms
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.renewals = 0
        # Why the loop stopped, when it stopped on its own. `None` means it is
        # running or was stopped in the orderly way.
        self.stopped_because: str | None = None

    def renew_once(self, now: float | None = None) -> bool:
        """One renewal. Returns False when the row is no longer renewable.

        A terminated session's row does not match the `state = RUNNING`
        predicate, so termination stops renewal without needing a separate
        signal to this object. That matters: a renewer that kept extending a
        terminated session's lease would defeat the whole layer, and it would
        do so silently.
        """
        moment = time.time() if now is None else now
        changed = self.table.renew(
            self.terms.session_id, self.terms.expiry_from(moment)
        )
        if changed:
            self.renewals += 1
        return bool(changed)

    def _loop(self) -> None:
        """Renew until the row stops being renewable, or the store stops being
        one this can wait out.

        **Two branches, and the split is the repair.** `StoreBusyError` means
        SQLite refused *without waiting* — which it does only where waiting
        could deadlock, so the lock was released and the contention was
        momentary. That is the case `LEASE_TTL_MULTIPLE` was chosen to absorb,
        and the loop absorbs `TOLERATED_CONSECUTIVE_BUSY` of them before
        giving up. Everything else — `StoreWedgedError`, `StoreUnusableError`,
        and anything that is not a store error at all — ends the loop on its
        first occurrence, because retrying a lock that outlasted the entire
        busy timeout, or a store that cannot be used, is waiting for something
        that is not coming.

        **Why the tolerant branch cannot spin forever, measured rather than
        argued.** The objection to `continue` was that it retries without
        bound. It does not, for a reason that is a property of the store: an
        ordinary statement *does* get the busy handler, so a lock that is never
        released exhausts it and reads as `StoreWedgedError`. Planted at both
        lock levels with the handler's timeout in force, five consecutive
        renewals against a permanently held lock returned `StoreWedgedError`
        five times out of five at each level, every one of them having waited
        out the whole timeout. **A permanently held lock cannot produce a
        `StoreBusyError` from this call site**, so the branch that retries is
        reachable only by contention that has already cleared. The bound above
        holds anyway, and is asserted against a planted source that cannot
        occur.

        **What this replaces.** Until the T016 migration, `SessionTable` raised
        raw `sqlite3.OperationalError` for both cases indistinguishably, so
        there was no branch to write and the loop re-raised on everything —
        landed explicitly as an interim, on the ground that all four durable
        routes were blocked. Two of those blocks were the migration's absence:
        *"`continue` retries forever"* and *"`SessionTable` cannot raise them
        from outside the repository layer"*. Both are gone. Measured either
        side, one planted momentary failure on the second of twelve scheduled
        renewals: re-raising everything gave **1 of 12** renewals with a dead
        thread and the lease 0.506s in the past; this loop gives **10 of 12**
        with the thread alive and the lease 0.065s in the future, against a
        control of 11 of 12. A planted wedged store still gives 1 of 12 and a
        dead thread, which is the branch working rather than the repair
        failing.

        **The raise is kept and is no longer an interim.** It is the terminal
        branch, reached only where retrying cannot help, and the raise is
        still the only channel library code has. **Nothing here is a logging
        facility and none of it should grow into one** — and note that nothing
        below changed a line of this file.

        **The vehicle the raise was waiting for now exists, and it was built
        at the delivery end rather than here.** The durable answer this note
        named — *a logger injected from an entry point on
        `src/proxy/main.go`'s pattern* — is `src/contracts/operator_log.py`,
        and `OperatorLog.adopt_thread_exceptions()` replaces
        `threading.excepthook` with one that writes through a single
        unbuffered `os.write`. The entry points install it before any thread
        starts. That is why this class neither imports it nor is passed it: a
        renewer that had to be handed a logger would only cover renewers, and
        the hook covers every thread the process starts, including the ones
        nobody enumerated.

        **What that changed, measured on both hooks.** The worst of the three
        failure modes is gone. The sweep recorded above — 41 of 87 clean, 14
        truncated, 32 silent, 4 aborted, with the main thread's exit swept
        across the raise instant — was re-run against a design that forces
        the overlap rather than sweeping for it, a daemon thread raising in a
        tight loop while the main thread exits 20 ms later: the stock hook
        aborts the process with `_enter_buffered_busy` and SIGABRT in **7 of
        120** trials, and this hook in **0 of 120**. Truncation goes with it,
        because a single `os.write` is not a buffer that can be torn in half.

        **What it did not change, disclosed rather than quietly dropped.**
        The silent case survives and belongs to neither hook: where the
        daemon thread is not scheduled at all before finalization completes,
        there is nothing to deliver. Swept in 0.5 ms steps, both hooks are
        silent in 20 of 20 trials at 0 ms and clean from 0.5 ms onward. So the
        remaining limit is a scheduling gap common to both, and swallowing
        would still lose the report in *every* case rather than in that one.

        `stopped_because` is set before raising rather than dropped. Nothing in
        `src/` reads it, but its documented `None` means *running, or stopped
        in the orderly way*, and leaving it `None` through a crash would make
        it report an orderly stop to the one reader it has.
        """
        consecutive_busy = 0
        while not self._stop.wait(self.terms.interval_seconds):
            try:
                if not self.renew_once():
                    self.stopped_because = "session is no longer RUNNING"
                    return
            except StoreBusyError as exc:
                consecutive_busy += 1
                if consecutive_busy > TOLERATED_CONSECUTIVE_BUSY:
                    self.stopped_because = f"{type(exc).__name__}: {exc}"
                    raise
                continue
            except Exception as exc:
                self.stopped_because = f"{type(exc).__name__}: {exc}"
                raise
            consecutive_busy = 0

    def start(self) -> None:
        if self._thread is not None:
            raise RuntimeError("renewer already started")
        self.renew_once()
        self._thread = threading.Thread(
            target=self._loop, name=f"lease-{self.terms.session_id}", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        """Orderly stop. The mechanism does not depend on this being reached.

        Nothing here revokes. Stopping simply stops renewing, which is the same
        thing a crash does — the orderly path and the crash path converge on
        one behaviour rather than on two that have to be kept in agreement.
        """
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self.terms.interval_seconds * 2)
            self._thread = None
