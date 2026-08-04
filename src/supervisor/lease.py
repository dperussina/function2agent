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

from src.supervisor.session_table import SessionTable

# The lease is granted for a multiple of the renewal interval so that one
# missed renewal — a slow disk, a scheduler hiccup — does not revoke a live
# session. Two is the smallest multiple that tolerates a single miss, and it is
# a *ratio*, not a duration: it inherits the interval's unvalidated status
# rather than adding a second unmeasured number.
LEASE_TTL_MULTIPLE = 2.0


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
        while not self._stop.wait(self.terms.interval_seconds):
            try:
                if not self.renew_once():
                    self.stopped_because = "session is no longer RUNNING"
                    return
            except Exception as exc:  # noqa: BLE001 - recorded, then stop
                # A renewer thread that dies silently makes the lease lapse for
                # a reason nobody can see. Lapsing is the fail-closed
                # direction, so this is not unsafe — it is undiagnosable, and
                # that is its own defect. It cost real time during the crash
                # fixture: `sqlite3`'s same-thread guard killed this thread and
                # the only symptom was a lease that would not renew.
                self.stopped_because = f"{type(exc).__name__}: {exc}"
                return

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
